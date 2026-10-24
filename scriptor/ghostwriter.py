"""
Ghostwriter-Workflow.

  Idee → Bible (SSOT) → Outline (SSOT) → Kapitelentwurf (WORK)
       → Lektorat (separate Rolle) → Gate-Entscheidung (Code) → Revision …

Invariante aus G.O.D.A.I. übernommen: **Generator ≠ Arbiter.**
Das LLM schreibt und das Lektorat liefert Befunde; ob ein Kapitel besteht,
entscheidet ausschließlich :func:`gate` anhand von ``config.yaml``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from scriptor import voice
from scriptor.llm import LLM, LLMError
from scriptor.project import BookProject, ProjectError, _dump

CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return dict(yaml.safe_load(path.read_text(encoding="utf-8")))


# ---------------------------------------------------------------------------
# JSON-Schemas (Structured Outputs)
# ---------------------------------------------------------------------------


def _obj(props: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": props,
        "required": list(props),
        "additionalProperties": False,
    }


_STR = {"type": "string"}
_STRS = {"type": "array", "items": _STR}

BIBLE_SCHEMA = _obj(
    {
        "logline": _STR,
        "premise": _STR,
        "theme": _STR,
        "tone": _STR,
        "pov": _STR,
        "tense": _STR,
        "setting": _STR,
        "characters": {
            "type": "array",
            "items": _obj(
                {
                    "name": _STR,
                    "role": _STR,
                    "description": _STR,
                    "want": _STR,
                    "need": _STR,
                    "voice": _STR,
                }
            ),
        },
        "rules": _STRS,
        "series_arc": _STR,
        "open_questions": _STRS,
    }
)

OUTLINE_SCHEMA = _obj(
    {
        "chapters": {
            "type": "array",
            "items": _obj(
                {
                    "nr": {"type": "integer"},
                    "title": _STR,
                    "beat": _STR,
                    "pov": _STR,
                    "goal": _STR,
                    "conflict": _STR,
                    "outcome": _STR,
                    "summary": _STR,
                    "words_target": {"type": "integer"},
                }
            ),
        },
    }
)

REVIEW_SCHEMA = _obj(
    {
        "score": {"type": "integer"},
        "summary": _STR,
        "strengths": _STRS,
        "issues": {
            "type": "array",
            "items": _obj(
                {
                    "severity": {"type": "string", "enum": ["blocker", "major", "minor"]},
                    "category": _STR,
                    "quote": _STR,
                    "problem": _STR,
                    "fix": _STR,
                }
            ),
        },
        "checklist": {
            "type": "array",
            "items": _obj({"item": _STR, "ok": {"type": "boolean"}, "note": _STR}),
        },
    }
)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_WRITER_ROLE = (
    "Du bist ein professioneller Ghostwriter. Du schreibst im Namen der Autorin/des "
    "Autors, in deren Stimme, auf Verlagsniveau. Die Bible ist verbindliche Wahrheit: "
    "Namen, Fakten, Regeln und Ton niemals widersprechen. Erfinde bei Sachbuch, Ratgeber, "
    "Business und Memoir keine Fakten, Zahlen, Quellen, Zitate oder Ereignisse — markiere "
    "Lücken mit [UNVERIFIED], [QUELLE BENÖTIGT] oder [FRAGE AN AUTOR: …]."
)

_EDITOR_ROLE = (
    "Du bist eine unabhängige, strenge Verlagslektorin. Du hast den Text nicht geschrieben "
    "und bist niemandem verpflichtet. Bewerte hart und konkret: Dramaturgie, Figuren, "
    "Kontinuität zur Bible, Stil, Zielgruppe, Faktentreue. Jeder Befund braucht ein "
    "wörtliches Zitat aus dem Text und einen konkreten Fix. Score: 90+ druckreif, "
    "75–89 solide mit Feinschliff, 50–74 deutliche Überarbeitung, <50 Neuschreiben. "
    "'blocker' nur für: Widerspruch zur Bible, erfundene Fakten bei Non-Fiction, "
    "Zielgruppenverstoß, fehlender Kern-Beat des Kapitels."
)


def _bible_block(project: BookProject) -> str:
    return "BIBLE (SSOT, verbindlich):\n" + _dump(project.bible)


def _voice_block(project: BookProject) -> str:
    v = project.read_ssot("voice") or {}
    parts = []
    metrics = v.get("metrics")
    if metrics:
        parts.append(voice.profile_brief(metrics))
    if v.get("style_notes"):
        parts.append("STILBESCHREIBUNG:\n" + str(v["style_notes"]))
    return "\n".join(parts)


def _writer_system(project: BookProject) -> str:
    """Stabiler System-Prompt je Buch (cachebar: ändert sich nur bei SSOT-Commits)."""
    blocks = [_WRITER_ROLE, project.genre.brief(), _voice_block(project), _bible_block(project)]
    return "\n\n".join(b for b in blocks if b)


# ---------------------------------------------------------------------------
# Gate (Code entscheidet)
# ---------------------------------------------------------------------------


def gate(
    review: dict[str, Any],
    metrics: dict[str, Any],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Deterministische PASS/REVISE-Entscheidung mit Begründungen."""
    rc = cfg["review"]
    reasons: list[str] = []
    score = int(review.get("score", 0))
    if score < rc["pass_score"]:
        reasons.append(f"Score {score} < {rc['pass_score']}")
    blocking = [i for i in review.get("issues", []) if i.get("severity") in rc["block_on"]]
    if blocking:
        reasons.append(f"{len(blocking)} Blocker-Befund(e)")
    dev = metrics.get("word_deviation")
    if dev is not None and abs(dev) > rc["word_tolerance"]:
        reasons.append(f"Wortzahl weicht um {int(dev * 100)} % vom Ziel ab")
    for k, d in (metrics.get("voice_deviation") or {}).items():
        if d > rc["voice_tolerance"]:
            reasons.append(f"Voice-Abweichung {k}: {int(d * 100)} %")
    return {"verdict": "PASS" if not reasons else "REVISE", "reasons": reasons}


# ---------------------------------------------------------------------------
# Ghostwriter
# ---------------------------------------------------------------------------


@dataclass
class ChapterResult:
    nr: int
    version: int
    verdict: str
    score: int
    reasons: list[str] = field(default_factory=list)


class Ghostwriter:
    """Steuert alle Schreibschritte eines Buchprojekts."""

    def __init__(self, llm: LLM, config: dict[str, Any] | None = None) -> None:
        self.llm = llm
        self.cfg = config or load_config()

    def _govern(self, project: BookProject) -> None:
        """Datenklasse/Buch an eine G.O.D.A.I.-gesteuerte LLM-Schicht melden (falls vorhanden)."""
        setter = getattr(self.llm, "set_context", None)
        if setter is not None:
            setter(data_class=project.genre.data_class, book=project.slug)

    def _effort(self, step: str) -> str:
        return str(self.cfg["effort"].get(step, "high"))

    # -- Bible ---------------------------------------------------------

    def develop_bible(self, project: BookProject, notes: str = "") -> str:
        self._govern(project)
        g = project.genre
        sources = project.sources_text()
        prompt = (
            f"Entwickle die Story-/Buch-Bible für folgendes Projekt.\n\n"
            f"TITEL: {project.title}\nIDEE:\n{project.bible.get('idea', '')}\n\n"
            f"ZUSATZNOTIZEN DER AUTORIN/DES AUTORS:\n{notes or '—'}\n\n"
            f"{g.brief()}\n\n"
            + (f"QUELLEN (einzige Faktenbasis):\n{sources}\n\n" if sources else "")
            + "Anforderungen:\n"
            "- Figuren mit Want (äußeres Ziel) und Need (innere Wahrheit). Bei Non-Fiction: "
            "zentrale Personen/Fallbeispiele; Want/Need = Leser-Problem/Leser-Gewinn.\n"
            "- 'rules': harte Kontinuitäts- und Faktenregeln (Namen, Alter, Orte, Magie-/"
            "Weltregeln, Zeitleiste, Hitze-Level, Ansprache du/Sie).\n"
            "- 'series_arc': nur bei Serie, sonst leer.\n"
            "- 'open_questions': alles, was nur die Autorin/der Autor entscheiden kann.\n"
            "- Keine generischen Ideen: spezifisch, überraschend, marktfähig."
        )
        data = self.llm.complete_json(
            "bible", _WRITER_ROLE, prompt, BIBLE_SCHEMA, effort=self._effort("bible")
        )
        if not data.get("premise"):
            raise LLMError("Bible ohne Prämisse zurückgegeben")
        return project.commit_ssot("bible", data, "Bible entwickelt", kind="PATCH")

    # -- Outline -------------------------------------------------------

    def develop_outline(self, project: BookProject, chapters: int | None = None) -> str:
        self._govern(project)
        if "premise" not in project.bible:
            raise ProjectError("Erst die Bible entwickeln (scriptor bible)")
        g = project.genre
        n = chapters or g.chapters["default"]
        prompt = (
            f"Erstelle den vollständigen Plan mit genau {n} {g.unit_label}-Einheiten.\n"
            f"Verteile die Beats der Buchart gemäß ihren Anteilen. Jede Einheit braucht "
            f"Ziel, Konflikt und Ausgang (Ausgang verändert die Lage). 'words_target' "
            f"zwischen {g.chapters['words_min']} und {g.chapters['words_max']}; Summe "
            f"im Gesamtrahmen {g.target_words['min']}–{g.target_words['max']}.\n"
            f"'beat' muss exakt einer der Beat-Namen der Buchart sein."
        )
        data = self.llm.complete_json(
            "outline",
            _writer_system(project),
            prompt,
            OUTLINE_SCHEMA,
            effort=self._effort("outline"),
        )
        chs = data.get("chapters", [])
        if len(chs) != n:
            raise LLMError(f"Outline hat {len(chs)} statt {n} Einheiten")
        lo, hi = g.chapters["words_min"], g.chapters["words_max"]
        for i, ch in enumerate(chs, start=1):
            ch["nr"] = i  # deterministisch nummerieren
            ch["words_target"] = max(lo, min(hi, int(ch.get("words_target") or lo)))
        return project.commit_ssot(
            "outline", {"chapters": chs}, f"Outline mit {n} Einheiten", kind="SUPERSEDE"
        )

    # -- Voice ---------------------------------------------------------

    def learn_voice(self, project: BookProject, samples: list[Path], describe: bool = True) -> str:
        self._govern(project)
        text = "\n\n".join(p.read_text(encoding="utf-8") for p in samples)
        metrics = voice.analyze(text)
        if metrics.get("words", 0) < 300:
            raise ProjectError("Zu wenig Textprobe (< 300 Wörter) für ein belastbares Profil")
        data: dict[str, Any] = {
            "samples": [p.name for p in samples],
            "metrics": metrics,
            "top_words": voice.top_words(text),
        }
        if describe:
            data["style_notes"] = self.llm.complete(
                "voice",
                "Du bist Stilanalytiker:in für Ghostwriting.",
                "Beschreibe die Erzählstimme dieser Texte als präzise, umsetzbare Regeln "
                "(max. 12 Stichpunkte): Satzbau, Rhythmus, Wortwahl, Humor, Bilder, "
                "Dialogstil, typische Wendungen, was die Person nie tun würde.\n\n" + text,
                effort=self._effort("voice"),
                max_tokens=8000,
            ).strip()
        return project.commit_ssot("voice", data, "Voice-Profil aus Textproben", kind="SUPERSEDE")

    # -- Kapitel -------------------------------------------------------

    def _previous_tail(self, project: BookProject, nr: int) -> str:
        prev = project.latest_chapter(nr - 1) if nr > 1 else None
        if not prev:
            return ""
        words = prev[1].split()
        return " ".join(words[-int(self.cfg["context"]["previous_tail_words"]) :])

    def draft_chapter(self, project: BookProject, nr: int) -> int:
        self._govern(project)
        plan = project.chapter_plan(nr)
        g = project.genre
        sources = "" if g.fiction else project.sources_text()
        tail = self._previous_tail(project, nr)
        prompt = (
            f"Schreibe {g.unit_label} {nr} von {len(project.outline)}.\n\n"
            f"PLAN:\n{_dump(plan)}\n"
            f"BISHERIGER VERLAUF:\n{project.summaries_before(nr) or '— (Anfang)'}\n\n"
            + (f"ENDE DES VORKAPITELS (nahtlos anschließen):\n…{tail}\n\n" if tail else "")
            + (f"QUELLEN (einzige Faktenbasis):\n{sources}\n\n" if sources else "")
            + f"Ziel: ca. {plan['words_target']} Wörter. Gib NUR den Kapiteltext aus — "
            "keine Überschrift, keine Kommentare, keine Meta-Hinweise."
        )
        text = self.llm.complete(
            "draft", _writer_system(project), prompt, effort=self._effort("draft")
        )
        version, _ = project.write_chapter(nr, text.strip() + "\n", f"Entwurf Kapitel {nr}")
        self._summarize(project, nr, text)
        return version

    def _summarize(self, project: BookProject, nr: int, text: str) -> None:
        summary = self.llm.complete(
            "summary",
            "Du fasst Kapitel für die Kontinuitätsführung zusammen.",
            "Fasse in max. 120 Wörtern zusammen: Was passiert, wer weiß was, "
            "offene Fäden, Zustand der Figuren am Kapitelende.\n\n" + text,
            effort=self._effort("summary"),
            max_tokens=4000,
        )
        project.write_summary(nr, summary.strip())

    def _metrics(self, project: BookProject, nr: int, text: str) -> dict[str, Any]:
        target = project.chapter_plan(nr).get("words_target")
        words = len(text.split())
        v = (project.read_ssot("voice") or {}).get("metrics")
        return {
            "words": words,
            "words_target": target,
            "word_deviation": round((words - target) / target, 3) if target else None,
            "voice_deviation": voice.compare(v, text) if v else {},
            "markers": {
                m: text.count(m)
                for m in ("[UNVERIFIED]", "[QUELLE", "[FRAGE AN AUTOR", "[ILLU")
                if m in text
            },
        }

    def review_chapter(self, project: BookProject, nr: int) -> ChapterResult:
        self._govern(project)
        latest = project.latest_chapter(nr)
        if latest is None:
            raise ProjectError(f"Kapitel {nr} hat noch keinen Text")
        version, text = latest
        g = project.genre
        system = "\n\n".join([_EDITOR_ROLE, g.brief(), _bible_block(project)])
        checklist = "\n".join(f"- {q}" for q in g.qa_checklist)
        prompt = (
            f"Lektoriere {g.unit_label} {nr}.\n\nPLAN:\n{_dump(project.chapter_plan(nr))}\n"
            f"VERLAUF BIS HIER:\n{project.summaries_before(nr) or '—'}\n\n"
            f"CHECKLISTE DER BUCHART (jeden Punkt in 'checklist' beantworten):\n{checklist}\n\n"
            f"TEXT:\n<<<\n{text}\n>>>"
        )
        review = self.llm.complete_json(
            "review", system, prompt, REVIEW_SCHEMA, effort=self._effort("review")
        )
        metrics = self._metrics(project, nr, text)
        decision = gate(review, metrics, self.cfg)
        review.update({"metrics": metrics, **decision, "version": version})
        project.write_review(nr, version, review)
        return ChapterResult(
            nr, version, decision["verdict"], int(review.get("score", 0)), decision["reasons"]
        )

    def revise_chapter(self, project: BookProject, nr: int, instructions: str = "") -> int:
        self._govern(project)
        latest = project.latest_chapter(nr)
        if latest is None:
            raise ProjectError(f"Kapitel {nr} hat noch keinen Text")
        version, text = latest
        review = project.read_review(nr, version) or {}
        issues = "\n".join(
            f"- [{i['severity']}] {i['problem']} | Zitat: „{i['quote']}“ | Fix: {i['fix']}"
            for i in review.get("issues", [])
        )
        prompt = (
            f"Überarbeite {project.genre.unit_label} {nr} vollständig.\n\n"
            f"PLAN:\n{_dump(project.chapter_plan(nr))}\n"
            f"LEKTORATSBEFUNDE (alle Blocker und Major beheben):\n{issues or '—'}\n"
            f"GATE-GRÜNDE:\n" + "\n".join(f"- {r}" for r in review.get("reasons", [])) + "\n"
            f"ZUSÄTZLICHE ANWEISUNGEN:\n{instructions or '—'}\n\n"
            f"Stärken bewahren: {', '.join(review.get('strengths', [])) or '—'}\n"
            f"Ziel: ca. {project.chapter_plan(nr)['words_target']} Wörter.\n\n"
            f"AKTUELLE FASSUNG:\n<<<\n{text}\n>>>\n\n"
            "Gib NUR den vollständigen überarbeiteten Kapiteltext aus."
        )
        new = self.llm.complete(
            "revise", _writer_system(project), prompt, effort=self._effort("revise")
        )
        v, _ = project.write_chapter(
            nr, new.strip() + "\n", f"Revision Kapitel {nr} (aus v{version})"
        )
        self._summarize(project, nr, new)
        return v

    # -- Komplettlauf --------------------------------------------------

    def write_book(
        self,
        project: BookProject,
        start: int = 1,
        end: int | None = None,
        max_revisions: int | None = None,
        progress: Any = None,
    ) -> list[ChapterResult]:
        """Entwurf → Lektorat → Revision je Kapitel, bis PASS oder Revisionslimit."""
        if not project.outline:
            raise ProjectError("Erst die Outline erstellen (scriptor outline)")
        end = end or len(project.outline)
        rounds = self.cfg["review"]["max_revisions"] if max_revisions is None else max_revisions
        results = []
        for nr in range(start, end + 1):
            if project.latest_chapter(nr) is None:
                self.draft_chapter(project, nr)
            result = self.review_chapter(project, nr)
            for _ in range(rounds):
                if result.verdict == "PASS":
                    break
                self.revise_chapter(project, nr)
                result = self.review_chapter(project, nr)
            results.append(result)
            if progress:
                progress(result)
        return results
