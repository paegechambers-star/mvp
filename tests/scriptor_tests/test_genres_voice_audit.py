import json

import pytest

from scriptor import voice
from scriptor.audit import AuditLog
from scriptor.genres import GenreError, all_genres, list_genre_ids, load_genre


def test_all_genres_load_and_shares_sum_to_one():
    genres = all_genres()
    assert len(genres) >= 10
    for g in genres:
        assert abs(sum(b["share"] for b in g.structure) - 1.0) <= 0.02, g.id
        assert g.qa_checklist, g.id
        assert g.chapters["words_min"] <= g.chapters["words_max"]


def test_unknown_genre_raises():
    with pytest.raises(GenreError):
        load_genre("gibtsnicht")


def test_bad_genre_file_rejected(tmp_path):
    (tmp_path / "x.yaml").write_text(
        "id: x\nname: X\nfiction: true\naudience: a\ntarget_words: {min: 1, max: 2}\n"
        "chapters: {default: 1, words_min: 1, words_max: 2}\n"
        "structure:\n  - {beat: a, share: 0.5, purpose: p}\n",
        encoding="utf-8",
    )
    assert list_genre_ids(tmp_path) == ["x"]
    with pytest.raises(GenreError, match="summieren"):
        load_genre("x", tmp_path)


def test_brief_contains_rules():
    brief = load_genre("bilderbuch").brief()
    assert "Doppelseite" in brief and "Refrain" in brief


def test_voice_analyze_and_compare():
    text = "Ich gehe. Du bleibst? „Nein!“ sagt sie.\n\nDann Stille. Lange Stille."
    m = voice.analyze(text)
    assert m["avg_sentence_len"] > 0
    assert m["question_ratio"] > 0
    assert m["dialog_ratio"] > 0
    assert voice.compare(m, text)["avg_sentence_len"] == 0.0
    long = "Dies ist ein deutlich längerer Satz mit sehr vielen zusätzlichen Wörtern darin. " * 5
    assert voice.compare(m, long)["avg_sentence_len"] > 1.0
    assert "VOICE-PROFIL" in voice.profile_brief(m)


def test_audit_chain_detects_tampering(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path)
    log.append("a", {"x": 1})
    log.append("b", {"x": 2})
    assert AuditLog(path).verify()
    lines = path.read_text().splitlines()
    entry = json.loads(lines[0])
    entry["data"]["x"] = 999
    lines[0] = json.dumps(entry)
    path.write_text("\n".join(lines) + "\n")
    assert not AuditLog(path).verify()


def test_audit_does_not_store_prompt_plaintext():
    log = AuditLog()
    log.llm_call("draft", "m", "GEHEIMES MANUSKRIPT", "end_turn", None)
    assert "GEHEIMES" not in json.dumps(log.entries)
