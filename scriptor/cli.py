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
from typing import Any

import typer

from scriptor.audit import AuditLog
from scriptor.genres import all_genres
from scriptor.ghostwriter import Ghostwriter, load_config
from scriptor.llm import LLM, LLMError
from scriptor.project import BookProject, ProjectError
from scriptor.runtime import Runtime
from scriptor.settings import Settings, api_key_status, set_api_key

app = typer.Typer(help="SCRIPTOR — KI-Ghostwriter & Arbeitsagent", no_args_is_help=True)

_state: dict[str, Any] = {"runtime": None}


@app.callback()
def _main(
    workspace: Path | None = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace-Ordner (Default: Einstellungen bzw. Dokumente/Scriptor)",
    ),
    model: str | None = typer.Option(None, "--model", help="Claude-Modell-ID"),
) -> None:
    rt = _rt()
    if workspace is not None:
        rt.settings.workspace = str(workspace.resolve())
    if model:
        rt.settings.model = model


def _rt() -> Runtime:
    if _state["runtime"] is None:
        _state["runtime"] = Runtime.create()
    rt: Runtime = _state["runtime"]
    return rt


def _ws() -> Path:
    return _rt().workspace


def _llm() -> LLM:
    return _rt().llm()


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
    typer.echo(
        f"Bible: {'ja' if s['has_bible'] else 'nein'}  Outline: {'ja' if s['has_outline'] else 'nein'}  "
        f"Audit-Kette: {'OK' if s['audit_chain_ok'] else 'GEBROCHEN'}"
    )
    for c in s["chapters"]:
        verdict = c["verdict"] or "—"
        typer.echo(
            f"  {c['nr']:>3}. {c['title'][:40]:<40} v{c['version']}  "
            f"{c['words']:>6}/{c['target'] or '?':<6} {verdict:<7} {c['score'] or ''}"
        )
    t = s["words_target"]
    typer.echo(f"Gesamt: {s['words_total']} Wörter (Ziel {t['min']}–{t['max']})")


@app.command()
def source(slug: str, files: list[Path]) -> None:
    """Quellen / Interviewnotizen (txt, md) ins SSOT übernehmen."""
    p = _book(slug)
    for f in files:
        typer.echo(f"{f.name} → {_run(p.add_source, f)}")


@app.command()
def voice(
    slug: str,
    samples: list[Path],
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
def outline(slug: str, chapters: int | None = typer.Option(None, "--chapters", "-c")) -> None:
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
def revise(
    slug: str, nr: int, instructions: str = typer.Option("", "--instructions", "-i")
) -> None:
    """Kapitel anhand des Lektorats überarbeiten."""
    v = _run(Ghostwriter(_llm()).revise_chapter, _book(slug), nr, instructions)
    typer.echo(f"Kapitel {nr} v{v} überarbeitet")


@app.command("write-book")
def write_book(
    slug: str,
    start: int = typer.Option(1, "--start"),
    end: int | None = typer.Option(None, "--end"),
    revisions: int | None = typer.Option(None, "--revisions", help="Max. Revisionsrunden"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Ohne Rückfrage starten"),
) -> None:
    """Komplettlauf: Entwurf → Lektorat → Revision bis PASS oder Limit."""
    p = _book(slug)
    last = end or len(p.outline)
    if not yes:
        typer.confirm(
            f"Kapitel {start}–{last} schreiben ({_rt().settings.model}). Das verursacht API-Kosten. Starten?",
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

    agent = Agent(_llm(), _ws(), docks=_rt().docks)
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

    def approve(name: str, args: dict[str, Any]) -> bool:
        if yes:
            return True
        return bool(
            typer.confirm(f"Werkzeug {name} {json.dumps(args, ensure_ascii=False)} ausführen?")
        )

    def on_event(kind: str, text: str) -> None:
        if kind == "tool":
            typer.secho(f"  → {text}", fg="cyan")

    return Agent(
        _llm(),
        _ws(),
        approve=approve,
        web_search=web or _rt().settings.web_search,
        config=load_config(),
        on_event=on_event,
        docks=_rt().docks,
    )


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


# ---------------------------------------------------------------------------
# App, Docks, Einstellungen
# ---------------------------------------------------------------------------


@app.command("app")
def run_app(
    port: int = typer.Option(0, help="Port (0 = frei wählen)"),
    browser: bool = typer.Option(
        False, "--browser", help="Im Browser statt eigenem Fenster öffnen"
    ),
) -> None:
    """Desktop-App starten (eigenes Fenster bzw. Browser)."""
    from scriptor.app.launcher import launch

    launch(_rt(), port=port, prefer_window=not browser)


@app.command()
def docks() -> None:
    """Geladene Docks (Plugins) und ihre Beiträge."""
    rt = _rt()
    for i in rt.docks.infos:
        state = "aktiv" if i.loaded else f"aus ({i.error or 'load() = False'})"
        typer.echo(f"{i.name:<16} {i.version:<8} {i.source:<10} {state}")
        if i.contributes:
            typer.echo(f"{'':<16} → {', '.join(i.contributes)}")
    typer.echo(f"\nPlugin-Ordner: {rt.settings.plugin_dir()}")


@app.command("config")
def config_cmd(
    workspace: Path | None = typer.Option(None, "--set-workspace"),
    model: str | None = typer.Option(None, "--set-model"),
    provider: str | None = typer.Option(None, "--provider", help="anthropic | ollama"),
    ollama_model: str | None = typer.Option(None, "--ollama-model", help="z. B. qwen3:8b"),
    ollama_url: str | None = typer.Option(None, "--ollama-url"),
    api_key: str | None = typer.Option(None, "--set-api-key", help="Im OS-Tresor speichern"),
    enable_plugin: str | None = typer.Option(None, "--enable-plugin"),
    disable_plugin: str | None = typer.Option(None, "--disable-plugin"),
) -> None:
    """Einstellungen anzeigen / ändern."""
    s = Settings.load()
    if workspace:
        s.workspace = str(workspace.resolve())
    if model:
        s.model = model
    if provider:
        if provider not in ("anthropic", "ollama"):
            typer.secho("--provider: anthropic oder ollama", fg="red", err=True)
            raise typer.Exit(2)
        s.provider = provider
    if ollama_model:
        s.ollama_model = ollama_model
    if ollama_url:
        s.ollama_url = ollama_url
    if enable_plugin and enable_plugin not in s.enabled_plugins:
        s.enabled_plugins.append(enable_plugin)
    if disable_plugin and disable_plugin in s.enabled_plugins:
        s.enabled_plugins.remove(disable_plugin)
    if api_key is not None and not set_api_key(api_key):
        typer.secho(
            "Kein OS-Tresor verfügbar (pip install keyring) — nutze ANTHROPIC_API_KEY.", fg="yellow"
        )
    s.save()
    typer.echo(f"Einstellungen: {Settings.path()}")
    typer.echo(f"Workspace:     {s.workspace_path()}")
    typer.echo(f"Anbieter:      {s.provider}")
    typer.echo(f"Modell:        {s.active_model()}")
    if s.provider == "ollama":
        from scriptor.llm import ollama_status

        st = ollama_status(s.ollama_url)
        state = f"läuft ({st['version']}), Modelle: {', '.join(st['models']) or '—'}"
        typer.echo(f"Ollama:        {state if st['reachable'] else 'nicht erreichbar'}")
    else:
        typer.echo(f"API-Key:       {api_key_status()}")
    typer.echo(f"Plugins frei:  {', '.join(s.enabled_plugins) or '—'}")


_cli_built = False


def build_app() -> typer.Typer:
    """Typer-App inkl. Dock-CLI-Befehle (einmalig eingehängt). Auch für ``frapp scriptor``."""
    global _cli_built
    if not _cli_built:
        for name, sub in _rt().docks.cli.items():
            app.add_typer(sub, name=name)
        _cli_built = True
    return app


def main() -> None:
    """Einstiegspunkt: Dock-CLI-Befehle einhängen, dann Typer starten."""
    build_app()()


if __name__ == "__main__":
    main()
