from __future__ import annotations

from typing import Any, Dict

import pytest

from scriptor.llm import FakeLLM
from scriptor.project import BookProject


def bible_json(system: str, prompt: str) -> Dict[str, Any]:
    return {
        "logline": "Ein Mädchen hört die Stimmen der Stadt.",
        "premise": "Mila (16) entdeckt, dass Berlin zu ihr spricht.",
        "theme": "Zugehörigkeit",
        "tone": "warm, spannend",
        "pov": "1. Person Präsens",
        "tense": "Präsens",
        "setting": "Berlin, heute",
        "characters": [
            {"name": "Mila", "role": "Protagonistin", "description": "16, Außenseiterin",
             "want": "dazugehören", "need": "sich selbst trauen", "voice": "trocken"},
        ],
        "rules": ["Mila ist 16", "Die Stadt spricht nur nachts"],
        "series_arc": "",
        "open_questions": ["Hat Mila Geschwister?"],
    }


def outline_json(n: int):
    def _fn(system: str, prompt: str) -> Dict[str, Any]:
        return {"chapters": [
            {"nr": 99, "title": f"Kapitel {i}", "beat": "Setup & Wunde", "pov": "Mila",
             "goal": "g", "conflict": "c", "outcome": "o", "summary": f"s{i}",
             "words_target": 10}
            for i in range(1, n + 1)
        ]}
    return _fn


def chapter_text(words: int = 2000) -> str:
    sentence = "Mila läuft durch die Nacht und hört die Stadt flüstern. "
    return (sentence * (words // 10)).strip()


@pytest.fixture
def workspace(tmp_path):
    return tmp_path / "ws"


@pytest.fixture
def project(workspace):
    return BookProject.create(workspace, "Die Stimmen der Stadt", "young_adult", "Berlin spricht", "Chambi")


def make_llm(n_chapters: int = 3, reviews=None) -> FakeLLM:
    reviews = list(reviews or [])

    def review(system, prompt):
        if reviews:
            return reviews.pop(0)
        return {"score": 85, "summary": "gut", "strengths": ["Stimme"], "issues": [], "checklist": []}

    return FakeLLM({
        "bible": bible_json,
        "outline": outline_json(n_chapters),
        "draft": lambda s, p: chapter_text(),
        "revise": lambda s, p: chapter_text(),
        "summary": lambda s, p: "Zusammenfassung.",
        "review": review,
        "document": lambda s, p: "Klappentext.",
        "voice": lambda s, p: "- kurze Sätze",
    })
