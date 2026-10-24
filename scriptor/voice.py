"""
Voice-Profil: deterministische Stilometrie aus Textproben der Autorin/des Autors.

Die Kennzahlen werden ohne LLM berechnet (reproduzierbar, prüfbar) und dem
Ghostwriter als harte Zielwerte mitgegeben. Danach misst ``compare()``, wie
weit ein generiertes Kapitel vom Profil abweicht.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter

_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+")
_WORD = re.compile(r"[A-Za-zÄÖÜäöüß'-]+")
_DIALOG = re.compile(r"[„\"»«“”].+?[“\"«»”]", re.DOTALL)


def _sentences(text: str) -> list[str]:
    flat = re.sub(r"\s+", " ", text.strip())
    return [s for s in _SENT_SPLIT.split(flat) if _WORD.search(s)]


def analyze(text: str) -> dict[str, float]:
    """Stilometrische Kennzahlen eines Textes."""
    sents = _sentences(text)
    words = _WORD.findall(text)
    if not sents or not words:
        return {"words": float(len(words))}
    lengths = [len(_WORD.findall(s)) for s in sents]
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    dialog_chars = sum(len(m) for m in _DIALOG.findall(text))
    lower = [w.lower() for w in words]
    return {
        "words": float(len(words)),
        "avg_sentence_len": round(statistics.mean(lengths), 2),
        "sentence_len_stdev": round(statistics.pstdev(lengths), 2),
        "avg_word_len": round(statistics.mean(len(w) for w in words), 2),
        "avg_paragraph_sentences": round(len(sents) / max(len(paragraphs), 1), 2),
        "dialog_ratio": round(dialog_chars / max(len(text), 1), 3),
        "question_ratio": round(sum(s.endswith("?") for s in sents) / len(sents), 3),
        "exclamation_ratio": round(sum(s.endswith("!") for s in sents) / len(sents), 3),
        "type_token_ratio": round(len(set(lower)) / len(lower), 3),
    }


def top_words(text: str, n: int = 15, min_len: int = 5) -> list[str]:
    """Häufigste längere Wörter — Hinweis auf Lieblingswörter/Tics."""
    counts = Counter(w.lower() for w in _WORD.findall(text) if len(w) >= min_len)
    return [w for w, _ in counts.most_common(n)]


def profile_brief(profile: dict[str, float]) -> str:
    """Prompt-Block mit den Zielwerten."""
    if "avg_sentence_len" not in profile:
        return ""
    return (
        "VOICE-PROFIL (Zielwerte aus Originaltexten der Autorin/des Autors — einhalten):\n"
        f"  - Ø Satzlänge: {profile['avg_sentence_len']} Wörter "
        f"(Streuung {profile['sentence_len_stdev']})\n"
        f"  - Ø Sätze pro Absatz: {profile['avg_paragraph_sentences']}\n"
        f"  - Dialoganteil: {int(profile['dialog_ratio'] * 100)} %\n"
        f"  - Fragen: {int(profile['question_ratio'] * 100)} %, "
        f"Ausrufe: {int(profile['exclamation_ratio'] * 100)} % der Sätze\n"
        f"  - Wortschatzvielfalt (TTR): {profile['type_token_ratio']}"
    )


def compare(profile: dict[str, float], text: str) -> dict[str, float]:
    """Relative Abweichung (0.0 = identisch) je Kennzahl."""
    actual = analyze(text)
    keys = ("avg_sentence_len", "avg_paragraph_sentences", "dialog_ratio", "avg_word_len")
    out: dict[str, float] = {}
    for k in keys:
        if k in profile and k in actual and profile[k]:
            out[k] = round(abs(actual[k] - profile[k]) / profile[k], 3)
    return out
