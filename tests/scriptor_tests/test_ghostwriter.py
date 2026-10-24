import pytest

from scriptor.ghostwriter import Ghostwriter, gate, load_config
from scriptor.llm import LLMError
from scriptor.project import ProjectError

from .conftest import make_llm

CFG = load_config()


def test_gate_is_deterministic():
    ok = {"score": 80, "issues": []}
    assert gate(ok, {"word_deviation": 0.1}, CFG)["verdict"] == "PASS"
    low = gate({"score": 60, "issues": []}, {}, CFG)
    assert low["verdict"] == "REVISE" and "Score" in low["reasons"][0]
    blocker = {"score": 95, "issues": [{"severity": "blocker"}]}
    assert gate(blocker, {}, CFG)["verdict"] == "REVISE"
    assert gate(ok, {"word_deviation": 0.5}, CFG)["verdict"] == "REVISE"
    assert gate(ok, {"voice_deviation": {"dialog_ratio": 0.9}}, CFG)["verdict"] == "REVISE"


def test_outline_requires_bible(project):
    with pytest.raises(ProjectError):
        Ghostwriter(make_llm()).develop_outline(project)


def test_full_pipeline_with_revision(project):
    bad = {"score": 50, "summary": "schwach", "strengths": [], "checklist": [],
           "issues": [{"severity": "blocker", "category": "Bible", "quote": "q",
                       "problem": "Mila ist 17", "fix": "Alter 16"}]}
    llm = make_llm(n_chapters=3, reviews=[bad])
    gw = Ghostwriter(llm)
    gw.develop_bible(project, notes="Serie geplant")
    assert project.bible["premise"].startswith("Mila")
    assert project.bible["meta"]["title"] == "Die Stimmen der Stadt"

    gw.develop_outline(project, chapters=3)
    chs = project.outline
    assert [c["nr"] for c in chs] == [1, 2, 3]  # deterministisch renummeriert
    assert all(c["words_target"] == 1800 for c in chs)  # auf Genre-Minimum geklemmt

    results = gw.write_book(project)
    assert [r.verdict for r in results] == ["PASS", "PASS", "PASS"]
    assert results[0].version == 2  # Kapitel 1 wurde nach Blocker revidiert
    assert project.read_review(1, 1)["verdict"] == "REVISE"
    assert project.read_review(1, 2)["verdict"] == "PASS"

    revise_prompt = next(c for c in llm.calls if c["role"] == "revise")["prompt"]
    assert "Mila ist 17" in revise_prompt  # Befunde fließen in die Revision
    draft2 = [c for c in llm.calls if c["role"] == "draft"][1]["prompt"]
    assert "Zusammenfassung." in draft2  # Kontinuität: Vorkapitel-Summary
    assert "ENDE DES VORKAPITELS" in draft2
    assert "BIBLE" in [c for c in llm.calls if c["role"] == "draft"][0]["system"]

    st = project.status()
    assert st["words_total"] > 0 and st["audit_chain_ok"]
    assert project.export_markdown().exists()


def test_revision_limit_respected(project):
    always_bad = {"score": 10, "summary": "", "strengths": [], "checklist": [], "issues": []}
    gw = Ghostwriter(make_llm(n_chapters=1, reviews=[always_bad] * 10))
    gw.develop_bible(project)
    gw.develop_outline(project, chapters=1)
    [r] = gw.write_book(project, max_revisions=2)
    assert r.verdict == "REVISE" and r.version == 3


def test_outline_wrong_count_rejected(project):
    gw = Ghostwriter(make_llm(n_chapters=2))
    gw.develop_bible(project)
    with pytest.raises(LLMError):
        gw.develop_outline(project, chapters=5)


def test_nonfiction_uses_sources(workspace, tmp_path):
    from scriptor.project import BookProject

    p = BookProject.create(workspace, "Mein Leben", "memoir", "Kindheit in Kiel")
    src = tmp_path / "interview1.md"
    src.write_text("Geboren 1961 in Kiel.", encoding="utf-8")
    p.add_source(src)
    llm = make_llm(n_chapters=1)
    gw = Ghostwriter(llm)
    gw.develop_bible(p)
    gw.develop_outline(p, chapters=1)
    gw.draft_chapter(p, 1)
    draft = next(c for c in llm.calls if c["role"] == "draft")
    assert "Geboren 1961 in Kiel." in draft["prompt"]
    assert "FRAGE AN AUTOR" in draft["system"]


def test_learn_voice(project, tmp_path):
    sample = tmp_path / "probe.txt"
    sample.write_text("Ich renne. Der Wind ist kalt. „Warte!“, ruft sie. " * 60, encoding="utf-8")
    Ghostwriter(make_llm()).learn_voice(project, [sample])
    v = project.read_ssot("voice")
    assert v["metrics"]["avg_sentence_len"] > 0 and v["style_notes"]
    tiny = tmp_path / "tiny.txt"
    tiny.write_text("zu kurz", encoding="utf-8")
    with pytest.raises(ProjectError):
        Ghostwriter(make_llm()).learn_voice(project, [tiny])
