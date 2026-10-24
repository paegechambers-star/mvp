"""
SCRIPTOR CLI.

    python -m scriptor genres
    python -m scriptor new "Titel" --genre young_adult --idea "…"
    python -m scriptor bible <slug>
    python -m scriptor outline <slug>
    python -m scriptor write-book <slug>
    python -m scriptor agent "Schreib mir ein Exposé für <slug>"
    python -m scriptor chat
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer

from scriptor.audit import AuditLog
from scriptor.genres import all_genres
from scriptor.ghostwriter import Ghostwriter, load_config
from scriptor.llm import DEFAULT_MODEL, AnthropicLLM, LLMError
from scriptor.project import BookProject, ProjectError, default_workspace

app = typer.Typer(help="SCRIPTOR — KI-Ghostwriter & Arbeitsagent", no_args_is_help=True)

_state: Dict[str, Any] = {"workspace": None, "model": DEFAULT_MODEL}


@app.callback()
def _main(
    workspace: Optional[Path] = typer.Option(
        None, "--workspace", "-w", help="Workspace-Ordner (Default: $SCRIPTOR_HOME oder ./scriptor-workspace)"
    ),
    model: str = typer.Option(DEFAULT_MODEL, "--model", help="Claude-Modell-ID"),
) -> None:
    _state["workspace"] = (workspace or default_workspace()).resolve()
    _state["model"] = model


def _ws() -> Path:
    ws: Path = _state["workspace"]
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def _llm() -> AnthropicLLM:
    return AnthropicLLM(AuditLog(_ws() / "audit.jsonl"), model=_state["model"])


def _book(slug: str) -> BookProject:
    try:
        return BookProject.load(_ws(), slug)
    except ProjectError as exc:
        typer.secho(str(exc), fg="red", err=True)
        raise typer.Exit(1)


def _run(fn: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return fn(*args, **kwargs)
    except (ProjectError, LLMError, ValueError) as exc:
        typer.secho(f"Fehler: {exc}", fg="red", err=True)
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Projekt
# ---------------------------------------------------------------------------


@app.command()
def genres() -> None:
    """Alle Bucharten anzeigen."""
    for g in all_genres():
        typer.echo(
            f"{g.id:<16} {g.name:<34} {g.target_words['min']:>6}–{g.target_words['max']:<6} Wörter  "
            f"{g.chapters['default']:>3} {g.unit_label}"
        )


@app.command()
def new(
    title: str,
    genre: str = typer.Option(..., "--genre", "-g", help="Buchart-ID (siehe 'genres')"),
    idea: str = typer.Option(..., "--idea", "-i", help="Idee / Prämisse in eigenen Worten"),
    author: str = typer.Option("", "--author", "-a"),
) -> None:
    """Neues Buchprojekt anlegen."""
    p = _run(BookProject.create, _ws(), title, genre, idea, author)
    typer.echo(f"Angelegt: {p.slug}  ({p.root})")


@app.command()
def books() -> None:
    """Buchprojekte im Workspace."""
    for slug in BookProject.list_slugs(_ws()):
        typer.echo(slug)


@app.command()
def status(slug: str) -> None:
    """Fortschritt, Scores und Wortzahlen."""
    s = _book(slug).status()
    typer.echo(f"{s['title']} — {s['genre']}")
    typer.echo(f"Bible: {'ja' if s['has_bible'] else 'nein'}  Outline: {'ja' if s['has_outline'] else 'nein'}  "
               f"Audit-Kette: {'OK' if s['audit_chain_ok'] else 'GEBROCHEN'}")
    for c in s["chapters"]:
        verdict = c["verdict"] or "—"
        typer.echo(f"  {c['nr']:>3}. {c['title'][:40]:<40} v{c['version']}  "
                   f"{c['words']:>6}/{c['target'] or '?':<6} {verdict:<7} {c['score'] or ''}")
    t = s["words_target"]
    typer.echo(f"Gesamt: {s['words_total']} Wörter (Ziel {t['min']}–{t['max']})")


@app.command()
def source(slug: str, files: List[Path]) -> None:
    """Quellen / Interviewnotizen (txt, md) ins SSOT übernehmen."""
    p = _book(slug)
    for f in files:
        typer.echo(f"{f.name} → {_run(p.add_source, f)}")


@app.command()
def voice(
    slug: str,
    samples: List[Path],
    describe: bool = typer.Option(True, help="Zusätzlich Stilbeschreibung per Claude"),
) -> None:
    """Voice-Profil aus Textproben der Autorin/des Autors lernen."""
    rid = _run(Ghostwriter(_llm()).learn_voice, _book(slug), samples, describe)
    typer.echo(f"Voice-Profil committed ({rid})")


# ---------------------------------------------------------------------------
# Schreiben
# ---------------------------------------------------------------------------


@app.command()
def bible(slug: str, notes: str = typer.Option("", "--notes", "-n")) -> None:
    """Bible entwickeln (Prämisse, Figuren, Regeln)."""
    p = _book(slug)
    rid = _run(Ghostwriter(_llm()).develop_bible, p, notes)
    typer.echo(f"Bible committed ({rid}): {p.root / 'ssot' / 'bible.yaml'}")
    for q in p.bible.get("open_questions", []):
        typer.secho(f"  OFFEN: {q}", fg="yellow")


@app.command()
def outline(slug: str, chapters: Optional[int] = typer.Option(None, "--chapters", "-c")) -> None:
    """Kapitelplan erstellen."""
    p = _book(slug)
    rid = _run(Ghostwriter(_llm()).develop_outline, p, chapters)
    typer.echo(f"Outline committed ({rid})")
    for c in p.outline:
        typer.echo(f"  {c['nr']:>3}. {c['title']}  [{c['beat']}]  ~{c['words_target']} W.")


@app.command()
def draft(slug: str, nr: int) -> None:
    """Kapitel entwerfen."""
    v = _run(Ghostwriter(_llm()).draft_chapter, _book(slug), nr)
    typer.echo(f"Kapitel {nr} v{v} geschrieben")


@app.command()
def review(slug: str, nr: int) -> None:
    """Unabhängiges Lektorat + Gate."""
    p = _book(slug)
    r = _run(Ghostwriter(_llm()).review_chapter, p, nr)
    color = "green" if r.verdict == "PASS" else "yellow"
    typer.secho(f"Kapitel {nr} v{r.version}: {r.verdict} (Score {r.score})", fg=color)
    for reason in r.reasons:
        typer.echo(f"  - {reason}")
    for i in (p.read_review(nr, r.version) or {}).get("issues", []):
        typer.echo(f"  [{i['severity']}] {i['problem']} → {i['fix']}")


@app.command()
def revise(slug: str, nr: int, instructions: str = typer.Option("", "--instructions", "-i")) -> None:
    """Kapitel anhand des Lektorats überarbeiten."""
    v = _run(Ghostwriter(_llm()).revise_chapter, _book(slug), nr, instructions)
    typer.echo(f"Kapitel {nr} v{v} überarbeitet")


@app.command("write-book")
def write_book(
    slug: str,
    start: int = typer.Option(1, "--start"),
    end: Optional[int] = typer.Option(None, "--end"),
    revisions: Optional[int] = typer.Option(None, "--revisions", help="Max. Revisionsrunden"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Ohne Rückfrage starten"),
) -> None:
    """Komplettlauf: Entwurf → Lektorat → Revision bis PASS oder Limit."""
    p = _book(slug)
    last = end or len(p.outline)
    if not yes:
        typer.confirm(
            f"Kapitel {start}–{last} schreiben ({_state['model']}). Das verursacht API-Kosten. Starten?",
            abort=True,
        )

    def progress(r: Any) -> None:
        typer.echo(f"Kap. {r.nr:>3} v{r.version}: {r.verdict} ({r.score}) {'; '.join(r.reasons)}")

    results = _run(Ghostwriter(_llm()).write_book, p, start, end, revisions, progress)
    failed = [r.nr for r in results if r.verdict != "PASS"]
    if failed:
        typer.secho(f"Nicht bestanden (manuell prüfen): {failed}", fg="yellow")


@app.command()
def material(slug: str, kind: str) -> None:
    """Begleitmaterial: expose, synopsis, klappentext, query_letter, social_media, …"""
    from scriptor.agent import Agent

    agent = Agent(_llm(), _ws())
    typer.echo(_run(agent._t_book_material, slug, kind))


@app.command()
def export(slug: str) -> None:
    """Manuskript als Markdown exportieren."""
    typer.echo(str(_run(_book(slug).export_markdown)))


@app.command("audit-verify")
def audit_verify() -> None:
    """SHA256-Kette des Workspace-Audit-Logs prüfen."""
    ok = AuditLog(_ws() / "audit.jsonl").verify()
    typer.secho("Audit-Kette OK" if ok else "Audit-Kette GEBROCHEN", fg="green" if ok else "red")
    raise typer.Exit(0 if ok else 1)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


def _make_agent(web: bool, yes: bool) -> Any:
    from scriptor.agent import Agent

    def approve(name: str, args: Dict[str, Any]) -> bool:
        if yes:
            return True
        return bool(typer.confirm(f"Werkzeug {name} {json.dumps(args, ensure_ascii=False)} ausführen?"))

    def on_event(kind: str, text: str) -> None:
        if kind == "tool":
            typer.secho(f"  → {text}", fg="cyan")

    return Agent(_llm(), _ws(), approve=approve, web_search=web, config=load_config(), on_event=on_event)


@app.command()
def agent(
    task: str,
    web: bool = typer.Option(False, "--web", help="Websuche erlauben"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Teure Werkzeuge ohne Rückfrage"),
) -> None:
    """Einen Auftrag in natürlicher Sprache ausführen."""
    typer.echo(_run(_make_agent(web, yes).run, task))


@app.command()
def chat(
    web: bool = typer.Option(False, "--web"),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """Interaktive Sitzung mit dem Agenten (leere Zeile oder 'exit' beendet)."""
    a = _make_agent(web, yes)
    while True:
        task = typer.prompt("du", default="", show_default=False)
        if task.strip().lower() in ("", "exit", "quit"):
            break
        typer.echo(_run(a.run, task))


if __name__ == "__main__":
    app()
