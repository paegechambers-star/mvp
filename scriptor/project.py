"""
Buchprojekt auf Dateisystem mit SSOT/WORK-Trennung.

  books/<slug>/
    ssot/bible.yaml        Wahrheit: Prämisse, Figuren, Welt, Regeln, Ton
    ssot/outline.yaml      Kapitelplan
    ssot/voice.yaml        Stilometrisches Voice-Profil
    ssot/sources/          Quellen / Interviewnotizen (Sachbuch, Memoir)
    work/chapters/         kap-01.v1.md, kap-01.v2.md … (nie überschrieben)
    work/reviews/          Lektoratsberichte je Version (JSON)
    work/summaries/        Kapitelzusammenfassungen für Kontinuität
    export/                Manuskript
    register.jsonl         Register aller SSOT-Commits und WORK-Outputs (mit IDs)
    audit.jsonl            LLM-Aufrufe (SHA256-Kette)

SSOT-Dateien ändern sich ausschließlich über :meth:`BookProject.commit_ssot`
(CREATE / PATCH / SUPERSEDE + Begründung) — keine stillen Edits.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from scriptor.audit import AuditLog
from scriptor.genres import Genre, load_genre

SSOT_FILES = ("bible", "outline", "voice")
COMMIT_KINDS = ("CREATE", "PATCH", "SUPERSEDE")


class ProjectError(RuntimeError):
    """Projekt fehlt, existiert schon, oder ungültige Operation."""


def default_workspace() -> Path:
    return Path(os.environ.get("SCRIPTOR_HOME", "scriptor-workspace")).resolve()


def slugify(title: str) -> str:
    norm = unicodedata.normalize("NFKD", title.replace("ß", "ss"))
    ascii_ = norm.encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")
    return slug[:60] or "buch"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BookProject:
    """Ein Buch im Workspace."""

    def __init__(self, root: Path) -> None:
        self.root = root
        if not (root / "ssot" / "bible.yaml").exists():
            raise ProjectError(f"Kein Buchprojekt unter {root}")
        self.audit = AuditLog(root / "audit.jsonl")

    # ------------------------------------------------------------------
    # Anlegen / Laden
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        workspace: Path,
        title: str,
        genre_id: str,
        idea: str,
        author: str = "",
        language: str = "de",
    ) -> BookProject:
        genre = load_genre(genre_id)  # validiert die Buchart
        root = workspace / "books" / slugify(title)
        if root.exists():
            raise ProjectError(f"Projekt existiert bereits: {root}")
        for sub in ("ssot/sources", "work/chapters", "work/reviews", "work/summaries", "export"):
            (root / sub).mkdir(parents=True, exist_ok=True)
        bible = {
            "meta": {
                "title": title,
                "slug": root.name,
                "genre": genre.id,
                "author": author,
                "language": language,
                "created": _now(),
            },
            "idea": idea,
        }
        (root / "ssot" / "bible.yaml").write_text(_dump(bible), encoding="utf-8")
        project = cls(root)
        project._register("CREATE", "ssot/bible.yaml", "Projekt angelegt", _dump(bible))
        return project

    @classmethod
    def load(cls, workspace: Path, slug: str) -> BookProject:
        return cls(workspace / "books" / slug)

    @staticmethod
    def list_slugs(workspace: Path) -> list[str]:
        books = workspace / "books"
        if not books.exists():
            return []
        return sorted(p.name for p in books.iterdir() if (p / "ssot" / "bible.yaml").exists())

    # ------------------------------------------------------------------
    # Register (NK.REGISTER ↔ NK.LOG)
    # ------------------------------------------------------------------

    @property
    def slug(self) -> str:
        return self.root.name

    def _register(self, kind: str, target: str, reason: str, content: str) -> str:
        entries = self.register()
        prefix = self.slug.upper().replace("-", "")[:12]
        entry_id = f"{prefix}-{len(entries) + 1:04d}"
        entry = {
            "id": entry_id,
            "ts": _now(),
            "kind": kind,
            "target": target,
            "reason": reason,
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        }
        with (self.root / "register.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self.audit.append("register", {"id": entry_id, "kind": kind, "target": target})
        return entry_id

    def register(self) -> list[dict[str, Any]]:
        path = self.root / "register.jsonl"
        if not path.exists():
            return []
        return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]

    # ------------------------------------------------------------------
    # SSOT
    # ------------------------------------------------------------------

    def _ssot_path(self, name: str) -> Path:
        if name not in SSOT_FILES:
            raise ProjectError(f"Unbekannte SSOT-Datei '{name}' (erlaubt: {SSOT_FILES})")
        return self.root / "ssot" / f"{name}.yaml"

    def read_ssot(self, name: str) -> Any:
        path = self._ssot_path(name)
        if not path.exists():
            return None
        return yaml.safe_load(path.read_text(encoding="utf-8"))

    def commit_ssot(self, name: str, data: Any, reason: str, kind: str = "PATCH") -> str:
        """
        Einziger Schreibweg für SSOT. ``PATCH`` merged Top-Level-Schlüssel
        (bei dict), ``SUPERSEDE`` ersetzt vollständig. Gibt die Register-ID zurück.
        """
        if kind not in COMMIT_KINDS:
            raise ProjectError(f"Ungültiger Commit-Typ {kind}")
        if not reason.strip():
            raise ProjectError("SSOT-Commit ohne Begründung ist nicht erlaubt")
        path = self._ssot_path(name)
        current = self.read_ssot(name)
        if kind == "PATCH" and isinstance(current, dict) and isinstance(data, dict):
            new = {**current, **data}
        else:
            new = data
        text = _dump(new)
        path.write_text(text, encoding="utf-8")
        return self._register(kind, f"ssot/{name}.yaml", reason, text)

    @property
    def bible(self) -> dict[str, Any]:
        return dict(self.read_ssot("bible") or {})

    @property
    def outline(self) -> list[dict[str, Any]]:
        data = self.read_ssot("outline") or {}
        return list(data.get("chapters", []))

    @property
    def genre(self) -> Genre:
        return load_genre(self.bible["meta"]["genre"])

    @property
    def title(self) -> str:
        return str(self.bible["meta"]["title"])

    def chapter_plan(self, nr: int) -> dict[str, Any]:
        for ch in self.outline:
            if int(ch["nr"]) == nr:
                return ch
        raise ProjectError(f"Kapitel {nr} ist nicht in der Outline")

    def sources_text(self, limit_chars: int = 200_000) -> str:
        """Alle Quellen-/Interviewdateien (txt/md) zusammengefügt."""
        parts = []
        for p in sorted((self.root / "ssot" / "sources").glob("*")):
            if p.suffix.lower() in (".txt", ".md"):
                parts.append(f"### QUELLE: {p.name}\n{p.read_text(encoding='utf-8')}")
        text = "\n\n".join(parts)
        if len(text) > limit_chars:
            raise ProjectError(
                f"Quellen zu groß ({len(text)} Zeichen > {limit_chars}). "
                "Bitte aufteilen oder zusammenfassen."
            )
        return text

    def add_source(self, path: Path) -> str:
        return self.add_source_text(path.name, path.read_text(encoding="utf-8"))

    def add_source_text(self, filename: str, content: str) -> str:
        name = Path(filename).name
        if not name or name.startswith("."):
            raise ProjectError(f"Ungültiger Dateiname: {filename!r}")
        dest = self.root / "ssot" / "sources" / name
        kind = "SUPERSEDE" if dest.exists() else "CREATE"
        dest.write_text(content, encoding="utf-8")
        return self._register(kind, f"ssot/sources/{name}", "Quelle hinzugefügt", content)

    # ------------------------------------------------------------------
    # WORK
    # ------------------------------------------------------------------

    def _chapter_versions(self, nr: int) -> list[tuple[int, Path]]:
        found = []
        for p in (self.root / "work" / "chapters").glob(f"kap-{nr:02d}.v*.md"):
            m = re.search(r"\.v(\d+)\.md$", p.name)
            if m:
                found.append((int(m.group(1)), p))
        return sorted(found)

    def latest_chapter(self, nr: int) -> tuple[int, str] | None:
        versions = self._chapter_versions(nr)
        if not versions:
            return None
        v, p = versions[-1]
        return v, p.read_text(encoding="utf-8")

    def write_chapter(self, nr: int, text: str, reason: str) -> tuple[int, str]:
        latest = self.latest_chapter(nr)
        version = (latest[0] + 1) if latest else 1
        rel = f"work/chapters/kap-{nr:02d}.v{version}.md"
        (self.root / rel).write_text(text, encoding="utf-8")
        return version, self._register("OUTPUT", rel, reason, text)

    def write_review(self, nr: int, version: int, review: dict[str, Any]) -> str:
        rel = f"work/reviews/kap-{nr:02d}.v{version}.json"
        text = json.dumps(review, ensure_ascii=False, indent=2)
        (self.root / rel).write_text(text, encoding="utf-8")
        return self._register("OUTPUT", rel, "Lektoratsbericht", text)

    def read_review(self, nr: int, version: int) -> dict[str, Any] | None:
        p = self.root / "work" / "reviews" / f"kap-{nr:02d}.v{version}.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def write_summary(self, nr: int, text: str) -> None:
        (self.root / "work" / "summaries" / f"kap-{nr:02d}.md").write_text(text, encoding="utf-8")

    def summaries_before(self, nr: int) -> str:
        parts = []
        for i in range(1, nr):
            p = self.root / "work" / "summaries" / f"kap-{i:02d}.md"
            if p.exists():
                parts.append(f"Kapitel {i}: {p.read_text(encoding='utf-8').strip()}")
        return "\n".join(parts)

    def status(self) -> dict[str, Any]:
        chapters = []
        total = 0
        for ch in self.outline:
            nr = int(ch["nr"])
            latest = self.latest_chapter(nr)
            words = len(latest[1].split()) if latest else 0
            review = self.read_review(nr, latest[0]) if latest else None
            total += words
            chapters.append(
                {
                    "nr": nr,
                    "title": ch.get("title", ""),
                    "version": latest[0] if latest else 0,
                    "words": words,
                    "target": ch.get("words_target"),
                    "score": review.get("score") if review else None,
                    "verdict": review.get("verdict") if review else None,
                }
            )
        g = self.genre
        return {
            "title": self.title,
            "genre": g.name,
            "has_bible": "premise" in self.bible,
            "has_outline": bool(self.outline),
            "chapters": chapters,
            "words_total": total,
            "words_target": g.target_words,
            "audit_chain_ok": self.audit.verify(),
        }

    def export_markdown(self) -> Path:
        meta = self.bible["meta"]
        parts = [f"# {meta['title']}", ""]
        if meta.get("author"):
            parts += [f"*{meta['author']}*", ""]
        missing = []
        for ch in self.outline:
            nr = int(ch["nr"])
            latest = self.latest_chapter(nr)
            if latest is None:
                missing.append(nr)
                continue
            parts += [f"## {nr}. {ch.get('title', '')}".rstrip(), "", latest[1].strip(), ""]
        if missing:
            raise ProjectError(f"Export abgebrochen — Kapitel ohne Text: {missing}")
        out = self.root / "export" / f"{self.slug}.md"
        text = "\n".join(parts)
        out.write_text(text, encoding="utf-8")
        self._register("OUTPUT", f"export/{out.name}", "Manuskript exportiert", text)
        return out


def _dump(data: Any) -> str:
    return str(yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=100))
