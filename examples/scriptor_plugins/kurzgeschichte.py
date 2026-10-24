"""
Beispiel-Plugin (Ordner-Plugin) für SCRIPTOR.

Installation:
  1. Diese Datei UND den Ordner ``kurzgeschichte_genres`` in den Plugin-Ordner kopieren
     (Windows: %APPDATA%\\Scriptor\\plugins — in der App unter "Plugins" angezeigt).
  2. In der App unter "Plugins" freigeben (oder: scriptor config --enable-plugin kurzgeschichte).
  3. SCRIPTOR neu starten.

Beiträge:
  - Buchart "kurzgeschichte" (YAML im Nachbarordner)
  - Agent-Werkzeug "word_repetitions": findet Wortwiederholungen auf engem Raum
  - Materialart "pitch_tweet"
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from scriptor.docks import Dock, DockRegistry

_WORD = re.compile(r"[A-Za-zÄÖÜäöüß]{5,}")


def repetitions(text: str, window: int = 60, min_count: int = 3) -> list[tuple[str, int]]:
    """Wörter (≥5 Zeichen), die in einem Fenster von ``window`` Wörtern ≥ min_count-mal vorkommen."""
    words = [w.lower() for w in _WORD.findall(text)]
    hits: Counter[str] = Counter()
    for i in range(0, max(1, len(words) - window + 1), window // 2):
        for w, n in Counter(words[i : i + window]).items():
            if n >= min_count:
                hits[w] = max(hits[w], n)
    return hits.most_common(20)


class KurzgeschichteDock(Dock):
    name = "kurzgeschichte"
    version = "1.0.0"
    description = "Buchart Kurzgeschichte + Wortwiederholungs-Check"

    def load(self, registry: DockRegistry) -> bool:
        registry.add_genre_dir(Path(__file__).parent / "kurzgeschichte_genres")

        def tool(agent, slug: str, nr: int) -> str:  # agent = scriptor.agent.Agent
            latest = agent._book(slug).latest_chapter(nr)
            if latest is None:
                return "Kapitel hat noch keinen Text."
            hits = repetitions(latest[1])
            return (
                "\n".join(f"{w}: {n}x auf engem Raum" for w, n in hits)
                or "Keine auffälligen Wiederholungen."
            )

        registry.add_tool(
            "word_repetitions",
            "Findet Wortwiederholungen auf engem Raum in einem Kapitel (Lektorats-Hilfe).",
            {
                "type": "object",
                "properties": {"slug": {"type": "string"}, "nr": {"type": "integer"}},
                "required": ["slug", "nr"],
                "additionalProperties": False,
            },
            tool,
        )
        registry.add_material(
            "pitch_tweet", "Ein Pitch in max. 280 Zeichen, Hook zuerst, kein Spoiler."
        )
        return True


DOCK = KurzgeschichteDock
