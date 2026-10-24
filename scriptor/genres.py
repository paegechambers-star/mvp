"""
Genre-Profile (Policy = Data).

Jede Buchart ist eine YAML-Datei in ``scriptor/genres/``. Python lädt und
validiert sie nur — Struktur, Umfang, Stilregeln und Lektorats-Checklisten
werden ausschließlich in den YAML-Dateien gepflegt. Neue Buchart = neue Datei.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import yaml

GENRE_DIR = Path(__file__).parent / "genres"

_REQUIRED = ("id", "name", "fiction", "audience", "target_words", "chapters", "structure")


class GenreError(ValueError):
    """Genre-Datei fehlt oder ist ungültig."""


@dataclass(frozen=True)
class Genre:
    id: str
    name: str
    fiction: bool
    audience: str
    target_words: Dict[str, int]
    chapters: Dict[str, int]
    structure: List[Dict[str, Any]]
    pov_default: str = ""
    unit_label: str = "Kapitel"
    series_support: bool = False
    style_rules: List[str] = field(default_factory=list)
    avoid: List[str] = field(default_factory=list)
    qa_checklist: List[str] = field(default_factory=list)

    def brief(self) -> str:
        """Kompakter Prompt-Block mit allen Regeln dieser Buchart."""
        beats = "\n".join(
            f"  - {b['beat']} (~{int(b['share'] * 100)} %): {b['purpose']}" for b in self.structure
        )
        lines = [
            f"BUCHART: {self.name}",
            f"Zielgruppe: {self.audience}",
            f"Umfang gesamt: {self.target_words['min']}–{self.target_words['max']} Wörter",
            f"{self.unit_label}: {self.chapters['words_min']}–{self.chapters['words_max']} Wörter",
            f"Erzählperspektive (Standard): {self.pov_default}",
            "Dramaturgische Struktur:",
            beats,
            "Stilregeln:",
            *[f"  - {r}" for r in self.style_rules],
            "Vermeiden:",
            *[f"  - {a}" for a in self.avoid],
        ]
        return "\n".join(lines)


def _validate(data: Dict[str, Any], source: Path) -> None:
    missing = [k for k in _REQUIRED if k not in data]
    if missing:
        raise GenreError(f"{source.name}: Pflichtfelder fehlen: {missing}")
    total = sum(float(b["share"]) for b in data["structure"])
    if abs(total - 1.0) > 0.02:
        raise GenreError(f"{source.name}: Beat-Anteile summieren sich zu {total:.2f}, nicht 1.0")


def load_genre(genre_id: str, directory: Path = GENRE_DIR) -> Genre:
    path = directory / f"{genre_id}.yaml"
    if not path.exists():
        known = ", ".join(sorted(list_genre_ids(directory)))
        raise GenreError(f"Unbekannte Buchart '{genre_id}'. Verfügbar: {known}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    _validate(data, path)
    known_fields = Genre.__dataclass_fields__
    return Genre(**{k: v for k, v in data.items() if k in known_fields})


def list_genre_ids(directory: Path = GENRE_DIR) -> List[str]:
    return sorted(p.stem for p in directory.glob("*.yaml"))


def all_genres(directory: Path = GENRE_DIR) -> List[Genre]:
    return [load_genre(g, directory) for g in list_genre_ids(directory)]
