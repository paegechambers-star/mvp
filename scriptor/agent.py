"""
SCRIPTOR-Agent: Auftrag in natürlicher Sprache → Claude plant und ruft Werkzeuge.

Werkzeuge:
  Buch      list_genres, list_books, create_book, book_status, develop_bible,
            develop_outline, draft_chapter, review_chapter, revise_chapter,
            write_book, update_bible, book_material, export_book
  Dateien   list_files, read_file, write_file  (nur innerhalb des Workspace)
  Web       web_search (serverseitig, optional)

Sicherheitsgrenzen:
  - Dateizugriff ist auf den Workspace beschränkt (kein Pfad-Ausbruch).
  - Keine Shell, kein E-Mail-Versand, keine Kalenderschreibzugriffe.
  - Teure Werkzeuge laufen nur nach Bestätigung (``approve``-Callback).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from scriptor.docks import DockRegistry
from scriptor.genres import all_genres
from scriptor.ghostwriter import Ghostwriter, load_config
from scriptor.llm import LLM, AgentTurn
from scriptor.project import BookProject, ProjectError, _dump

Approve = Callable[[str, dict[str, Any]], bool]

SYSTEM_PROMPT = """\
Du bist SCRIPTOR, der persönliche KI-Arbeitsagent von Chambi (Lucas). Schwerpunkt: \
Ghostwriting und Buchproduktion für alle Bucharten (Bilderbuch bis Business-Buch, YA-Serien, \
Memoir) sowie Text- und Dokumentarbeit drumherum (Exposés, Klappentexte, Anschreiben, \
Konzepte, Notizen).

Arbeitsweise:
- Direkt, kritisch, strukturiert. Keine Floskeln. Duzen.
- Kennzeichne Aussagen als VERIFIED / UNVERIFIED / ASSUMPTION, wenn es um Fakten geht. \
No-Citation = No-Assertion: Ohne Quelle keine Tatsachenbehauptung.
- SSOT/WORK: Bible, Outline und Voice sind Wahrheit (SSOT) und ändern sich nur über \
update_bible bzw. die Entwicklungswerkzeuge — immer mit Begründung. Kapitel und Material \
sind WORK.
- Fehlen Infos, die nur die Autorin/der Autor entscheiden kann: Annahme explizit nennen \
oder nachfragen, statt zu raten.
- Nutze die Werkzeuge statt Text im Chat zu erzeugen, wenn das Ergebnis eine Datei werden soll.
- Nach jedem Auftrag: kurzes Ergebnis, max. 3 nächste Schritte, Risiken.

Grenzen (ehrlich kommunizieren): Du arbeitest nur im SCRIPTOR-Workspace. Du hast keinen \
Zugriff auf E-Mail, Kalender, Shell oder fremde Dateien.
"""


def _tool(
    name: str, description: str, props: dict[str, Any], required: list[str]
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": props,
            "required": required,
            "additionalProperties": False,
        },
    }


_S = {"type": "string"}
_I = {"type": "integer"}
_SLUG = {"type": "string", "description": "Projekt-Slug aus list_books"}

TOOLS: list[dict[str, Any]] = [
    _tool("list_genres", "Listet alle Bucharten mit ID, Name, Zielgruppe und Umfang.", {}, []),
    _tool("list_books", "Listet alle Buchprojekte im Workspace.", {}, []),
    _tool(
        "create_book",
        "Legt ein neues Buchprojekt an. genre muss eine ID aus list_genres sein.",
        {"title": _S, "genre": _S, "idea": _S, "author": _S},
        ["title", "genre", "idea"],
    ),
    _tool(
        "book_status",
        "Status eines Buchs: Bible, Outline, Kapitel, Scores, Wortzahlen.",
        {"slug": _SLUG},
        ["slug"],
    ),
    _tool(
        "show_ssot",
        "Zeigt eine SSOT-Datei (bible | outline | voice) eines Buchs.",
        {"slug": _SLUG, "name": {"type": "string", "enum": ["bible", "outline", "voice"]}},
        ["slug", "name"],
    ),
    _tool(
        "develop_bible",
        "Entwickelt die Bible (Prämisse, Figuren, Regeln) per Claude. Teuer.",
        {"slug": _SLUG, "notes": _S},
        ["slug"],
    ),
    _tool(
        "develop_outline",
        "Erstellt den Kapitelplan. chapters optional (sonst Genre-Standard).",
        {"slug": _SLUG, "chapters": _I},
        ["slug"],
    ),
    _tool(
        "draft_chapter",
        "Schreibt einen neuen Entwurf eines Kapitels.",
        {"slug": _SLUG, "nr": _I},
        ["slug", "nr"],
    ),
    _tool(
        "review_chapter",
        "Unabhängiges Lektorat + Gate-Entscheidung für die neueste Fassung.",
        {"slug": _SLUG, "nr": _I},
        ["slug", "nr"],
    ),
    _tool(
        "revise_chapter",
        "Überarbeitet ein Kapitel auf Basis des Lektorats + Anweisungen.",
        {"slug": _SLUG, "nr": _I, "instructions": _S},
        ["slug", "nr"],
    ),
    _tool(
        "write_book",
        "Komplettlauf Entwurf→Lektorat→Revision für Kapitel start..end. Sehr teuer.",
        {"slug": _SLUG, "start": _I, "end": _I},
        ["slug"],
    ),
    _tool(
        "update_bible",
        "SSOT-Commit auf die Bible. patch_yaml = YAML-Mapping der zu ändernden Top-Level-Felder. "
        "kind PATCH (mergen) oder SUPERSEDE (ersetzen). reason ist Pflicht.",
        {
            "slug": _SLUG,
            "patch_yaml": _S,
            "reason": _S,
            "kind": {"type": "string", "enum": ["PATCH", "SUPERSEDE"]},
        },
        ["slug", "patch_yaml", "reason"],
    ),
    _tool(
        "book_material",
        "Erzeugt Begleitmaterial (expose, synopsis, klappentext, query_letter, "
        "social_media, leseprobe_intro, kapitel_inhaltsverzeichnis) als Datei.",
        {"slug": _SLUG, "kind": _S},
        ["slug", "kind"],
    ),
    _tool("export_book", "Exportiert das Manuskript als Markdown.", {"slug": _SLUG}, ["slug"]),
    _tool("list_files", "Listet Dateien unter einem Workspace-Pfad.", {"path": _S}, []),
    _tool("read_file", "Liest eine Textdatei im Workspace.", {"path": _S}, ["path"]),
    _tool(
        "write_file",
        "Schreibt eine Textdatei im Workspace (legt Ordner an, überschreibt nicht "
        "— existiert die Datei, wird ein Versions-Suffix angehängt).",
        {"path": _S, "content": _S},
        ["path", "content"],
    ),
]


class WorkspaceError(PermissionError):
    """Pfad liegt außerhalb des Workspace."""


class Agent:
    """Agent-Loop über ein beliebiges :class:`~scriptor.llm.LLM`."""

    def __init__(
        self,
        llm: LLM,
        workspace: Path,
        approve: Approve | None = None,
        web_search: bool = False,
        config: dict[str, Any] | None = None,
        on_event: Callable[[str, str], None] | None = None,
        docks: DockRegistry | None = None,
    ) -> None:
        self.llm = llm
        self.workspace = workspace.resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.cfg = config or load_config()
        self.gw = Ghostwriter(llm, self.cfg)
        self.approve = approve or (lambda name, args: True)
        self.on_event = on_event or (lambda kind, text: None)
        self.messages: list[dict[str, Any]] = []
        self.docks = docks or DockRegistry()
        self.materials: dict[str, str] = {**self.cfg["materials"], **self.docks.materials}
        self.confirm_tools = set(self.cfg["agent"]["confirm_tools"]) | {
            n for n, t in self.docks.tools.items() if t.confirm
        }
        builtin = {t["name"] for t in TOOLS}
        clash = builtin & set(self.docks.tools)
        if clash:
            raise ValueError(f"Dock-Werkzeuge überschreiben eingebaute Werkzeuge: {sorted(clash)}")
        self.tools = list(TOOLS) + [t.schema for t in self.docks.tools.values()]
        if web_search:
            self.tools.append(
                {
                    "type": "web_search_20260209",
                    "name": "web_search",
                    "max_uses": int(self.cfg["agent"]["web_search_max_uses"]),
                }
            )

    # ------------------------------------------------------------------
    # Loop
    # ------------------------------------------------------------------

    def run(self, task: str) -> str:
        """Ein Auftrag (append-only Historie; mehrere Aufrufe = Chat)."""
        self.messages.append({"role": "user", "content": task})
        max_steps = int(self.cfg["agent"]["max_steps"])
        turn: AgentTurn | None = None
        for _ in range(max_steps):
            turn = self.llm.agent_turn(
                SYSTEM_PROMPT, self.messages, self.tools, effort=self.cfg["effort"]["agent"]
            )
            self.messages.append({"role": "assistant", "content": turn.content})
            if turn.text and turn.stop_reason in ("tool_use", "pause_turn"):
                self.on_event(
                    "text", turn.text
                )  # Zwischenstand; die Schlussantwort ist der Rückgabewert
            if turn.stop_reason == "pause_turn":
                continue  # serverseitiges Werkzeug (Websuche) läuft weiter
            if turn.stop_reason != "tool_use":
                return turn.text
            results = []
            for call in turn.tool_calls:
                self.on_event(
                    "tool", f"{call['name']} {json.dumps(call['input'], ensure_ascii=False)}"
                )
                output, is_error = self._execute(call["name"], dict(call["input"]))
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call["id"],
                        "content": output,
                        "is_error": is_error,
                    }
                )
            self.messages.append({"role": "user", "content": results})
        return (turn.text if turn else "") + f"\n[Abbruch: max. {max_steps} Schritte erreicht]"

    def _execute(self, name: str, args: dict[str, Any]) -> tuple[str, bool]:
        dock_tool = self.docks.tools.get(name)
        handler: Callable[..., Any] | None = getattr(self, f"_t_{name}", None)
        if dock_tool is not None:
            handler = lambda **kw: dock_tool.handler(self, **kw)
        if handler is None:
            return f"Unbekanntes Werkzeug: {name}", True
        if name in self.confirm_tools and not self.approve(name, args):
            return (
                "Vom Nutzer abgelehnt. Nicht erneut versuchen; nachfragen, was stattdessen.",
                True,
            )
        try:
            return str(handler(**args)), False
        except (ProjectError, WorkspaceError, ValueError, KeyError, TypeError, OSError) as exc:
            return f"{type(exc).__name__}: {exc}", True
        except Exception as exc:
            if dock_tool is None:
                raise
            return f"Plugin '{dock_tool.dock}' fehlgeschlagen: {type(exc).__name__}: {exc}", True

    # ------------------------------------------------------------------
    # Pfade
    # ------------------------------------------------------------------

    def _safe(self, rel: str) -> Path:
        target = (self.workspace / rel).resolve()
        if target != self.workspace and self.workspace not in target.parents:
            raise WorkspaceError(f"Pfad außerhalb des Workspace: {rel}")
        return target

    def _book(self, slug: str) -> BookProject:
        return BookProject.load(self.workspace, slug)

    # ------------------------------------------------------------------
    # Werkzeuge
    # ------------------------------------------------------------------

    def _t_list_genres(self) -> str:
        return "\n".join(
            f"{g.id}: {g.name} | {g.audience} | {g.target_words['min']}–"
            f"{g.target_words['max']} Wörter | {g.chapters['default']} {g.unit_label}"
            for g in all_genres()
        )

    def _t_list_books(self) -> str:
        slugs = BookProject.list_slugs(self.workspace)
        return "\n".join(slugs) if slugs else "Keine Buchprojekte."

    def _t_create_book(self, title: str, genre: str, idea: str, author: str = "") -> str:
        p = BookProject.create(self.workspace, title, genre, idea, author)
        return f"Angelegt: slug={p.slug}"

    def _t_book_status(self, slug: str) -> str:
        return json.dumps(self._book(slug).status(), ensure_ascii=False, indent=1)

    def _t_show_ssot(self, slug: str, name: str) -> str:
        return _dump(self._book(slug).read_ssot(name)) or "(leer)"

    def _t_develop_bible(self, slug: str, notes: str = "") -> str:
        rid = self.gw.develop_bible(self._book(slug), notes)
        return f"Bible committed ({rid}).\n" + _dump(self._book(slug).bible)

    def _t_develop_outline(self, slug: str, chapters: int | None = None) -> str:
        p = self._book(slug)
        rid = self.gw.develop_outline(p, chapters)
        lines = [f"{c['nr']}. {c['title']} [{c['beat']}] – {c['summary']}" for c in p.outline]
        return f"Outline committed ({rid}).\n" + "\n".join(lines)

    def _t_draft_chapter(self, slug: str, nr: int) -> str:
        v = self.gw.draft_chapter(self._book(slug), nr)
        return f"Kapitel {nr} v{v} geschrieben. Als Nächstes: review_chapter."

    def _t_review_chapter(self, slug: str, nr: int) -> str:
        p = self._book(slug)
        r = self.gw.review_chapter(p, nr)
        review = p.read_review(nr, r.version) or {}
        issues = "\n".join(
            f"- [{i['severity']}] {i['problem']} → {i['fix']}" for i in review.get("issues", [])
        )
        return (
            f"Kapitel {nr} v{r.version}: {r.verdict} (Score {r.score})\n"
            f"Gate: {r.reasons or 'ok'}\nBefunde:\n{issues or '—'}"
        )

    def _t_revise_chapter(self, slug: str, nr: int, instructions: str = "") -> str:
        v = self.gw.revise_chapter(self._book(slug), nr, instructions)
        return f"Kapitel {nr} v{v} überarbeitet. Erneut review_chapter ausführen."

    def _t_write_book(self, slug: str, start: int = 1, end: int | None = None) -> str:
        results = self.gw.write_book(self._book(slug), start, end)
        return "\n".join(
            f"Kap. {r.nr} v{r.version}: {r.verdict} ({r.score}) {'; '.join(r.reasons)}"
            for r in results
        )

    def _t_update_bible(self, slug: str, patch_yaml: str, reason: str, kind: str = "PATCH") -> str:
        import yaml

        data = yaml.safe_load(patch_yaml)
        if not isinstance(data, dict):
            # ValueError (nicht TypeError): ungültige Nutzereingabe, vom Agenten als Werkzeugfehler gemeldet
            raise ValueError("patch_yaml muss ein Mapping sein")  # noqa: TRY004
        if kind == "PATCH" and "meta" in data:
            raise ValueError("meta ist schreibgeschützt")
        return f"SSOT-Commit {self._book(slug).commit_ssot('bible', data, reason, kind)}"

    def _t_book_material(self, slug: str, kind: str) -> str:
        materials = self.materials
        if kind not in materials:
            raise ValueError(f"Unbekannte Materialart. Erlaubt: {sorted(materials)}")
        p = self._book(slug)
        self.gw._govern(p)
        summaries = p.summaries_before(len(p.outline) + 1)
        outline = "\n".join(f"{c['nr']}. {c['title']}: {c['summary']}" for c in p.outline)
        text = self.gw.llm.complete(
            "document",
            "Du bist Verlagsprofi für Buchvermarktung. Erfinde keine Rezensionen, Preise, "
            "Verkaufszahlen oder Auszeichnungen.",
            f"AUFTRAG: {materials[kind]}\n\n{p.genre.brief()}\n\nBIBLE:\n{_dump(p.bible)}\n"
            f"OUTLINE:\n{outline or '—'}\n\nKAPITELZUSAMMENFASSUNGEN:\n{summaries or '—'}",
            effort=self.cfg["effort"]["document"],
            max_tokens=16000,
        )
        out = p.root / "export" / f"{kind}.md"
        out.write_text(text.strip() + "\n", encoding="utf-8")
        return f"Gespeichert: {out.relative_to(self.workspace)}\n\n{text[:1500]}"

    def _t_export_book(self, slug: str) -> str:
        out = self._book(slug).export_markdown()
        return f"Exportiert: {out.relative_to(self.workspace)}"

    def _t_list_files(self, path: str = ".") -> str:
        base = self._safe(path)
        if not base.exists():
            return "(existiert nicht)"
        files = [str(p.relative_to(self.workspace)) for p in sorted(base.rglob("*")) if p.is_file()]
        return "\n".join(files[:300]) or "(leer)"

    def _t_read_file(self, path: str) -> str:
        target = self._safe(path)
        text = target.read_text(encoding="utf-8")
        if len(text) > 100_000:
            return text[:100_000] + f"\n[… gekürzt, Datei hat {len(text)} Zeichen]"
        return text

    def _t_write_file(self, path: str, content: str) -> str:
        target = self._safe(path)
        if "books" in target.relative_to(self.workspace).parts[:1] and "ssot" in target.parts:
            raise WorkspaceError(
                "SSOT-Dateien nur über update_bible / Entwicklungswerkzeuge ändern"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        n = 2
        final = target
        while final.exists():
            final = target.with_name(f"{target.stem}.v{n}{target.suffix}")
            n += 1
        final.write_text(content, encoding="utf-8")
        return f"Geschrieben: {final.relative_to(self.workspace)}"
