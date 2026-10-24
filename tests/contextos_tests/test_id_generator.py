"""Tests for contextos/id_generator.py — 14 tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from contextos.id_generator import (
    BASE36,
    compute_checksum,
    decode_b36,
    encode_b36,
    encode_time_bucket,
    generate_id,
    next_sequence,
    parse_id,
    validate_id,
)
from contextos.types import Actor, Cluster, EntryType, Kind, TruthGate


# ─────────────────────────────── encode / decode ──────────────────────────────

def test_encode_b36_zero():
    assert encode_b36(0) == "00"


def test_encode_b36_max_2_char():
    assert encode_b36(1295) == "ZZ"


def test_encode_b36_round_trip():
    for n in (0, 1, 35, 36, 100, 999, 1295):
        assert decode_b36(encode_b36(n)) == n


def test_encode_b36_too_large_raises():
    with pytest.raises(ValueError):
        encode_b36(1296, width=2)


def test_decode_b36_invalid_char_raises():
    with pytest.raises(ValueError):
        decode_b36("!!")


# ─────────────────────────────── checksum ────────────────────────────────────

def test_compute_checksum_length():
    prefix = "NK" + "00" + "00" + "00" + "00" + "00" + "00"
    assert len(prefix) == 14
    cs = compute_checksum(prefix)
    assert len(cs) == 2
    assert all(c in BASE36 for c in cs)


def test_compute_checksum_different_prefixes():
    # Prefixes differing in the last character — guaranteed different checksums
    p1 = "NK000000000001"
    p2 = "NK000000000002"
    assert compute_checksum(p1) != compute_checksum(p2)


def test_compute_checksum_wrong_length_raises():
    with pytest.raises(ValueError):
        compute_checksum("NK00000")


# ─────────────────────────────── validate_id ──────────────────────────────────

def test_validate_id_accepts_valid():
    id_str = generate_id(
        Kind.NK, Actor.USER, Cluster.GENERAL, EntryType.FACT,
        TruthGate.UNVERIFIED, time_bucket="00", sequence=0,
    )
    assert validate_id(id_str) is True


def test_validate_id_rejects_wrong_length():
    assert validate_id("NKSHORT") is False


def test_validate_id_rejects_bad_checksum():
    id_str = generate_id(
        Kind.NK, Actor.USER, Cluster.GENERAL, EntryType.FACT,
        TruthGate.UNVERIFIED, time_bucket="00", sequence=1,
    )
    # Corrupt last character
    bad = id_str[:-1] + ("A" if id_str[-1] != "A" else "B")
    assert validate_id(bad) is False


def test_validate_id_rejects_non_string():
    assert validate_id(None) is False  # type: ignore[arg-type]


# ─────────────────────────────── parse_id ────────────────────────────────────

def test_parse_id_roundtrip():
    id_str = generate_id(
        Kind.MK, Actor.ADMIN, Cluster.COMPLIANCE, EntryType.DECISION,
        TruthGate.SINGLE_SOURCE,
        time_bucket="01",
        sequence=5,
    )
    parsed = parse_id(id_str)
    assert parsed.raw == id_str
    assert parsed.kind == Kind.MK
    assert parsed.actor == Actor.ADMIN
    assert parsed.cluster == Cluster.COMPLIANCE
    assert parsed.entry_type == EntryType.DECISION
    assert parsed.truth_gate == TruthGate.SINGLE_SOURCE
    assert parsed.sequence == 5


def test_parse_id_invalid_raises():
    with pytest.raises(ValueError):
        parse_id("TOOSHORT")


# ─────────────────────────────── generate_id ──────────────────────────────────

def test_generate_id_is_16_chars():
    id_str = generate_id(
        Kind.NK, Actor.USER, Cluster.GENERAL, EntryType.FACT,
        TruthGate.UNVERIFIED, time_bucket="00", sequence=0,
    )
    assert len(id_str) == 16


def test_generate_id_deterministic():
    a = generate_id(Kind.NK, Actor.USER, Cluster.GENERAL, EntryType.FACT,
                    TruthGate.UNVERIFIED, time_bucket="0A", sequence=7)
    b = generate_id(Kind.NK, Actor.USER, Cluster.GENERAL, EntryType.FACT,
                    TruthGate.UNVERIFIED, time_bucket="0A", sequence=7)
    assert a == b


def test_generate_id_different_actors_differ():
    a = generate_id(Kind.NK, Actor.USER, Cluster.GENERAL, EntryType.FACT,
                    TruthGate.UNVERIFIED, time_bucket="00", sequence=0)
    b = generate_id(Kind.NK, Actor.ADMIN, Cluster.GENERAL, EntryType.FACT,
                    TruthGate.UNVERIFIED, time_bucket="00", sequence=0)
    assert a != b


def test_generate_id_different_clusters_differ():
    a = generate_id(Kind.NK, Actor.USER, Cluster.GENERAL, EntryType.FACT,
                    TruthGate.UNVERIFIED, time_bucket="00", sequence=0)
    b = generate_id(Kind.NK, Actor.USER, Cluster.RESEARCH, EntryType.FACT,
                    TruthGate.UNVERIFIED, time_bucket="00", sequence=0)
    assert a != b


# ─────────────────────────────── encode_time_bucket ───────────────────────────

def test_encode_time_bucket_returns_2_chars():
    tb = encode_time_bucket()
    assert len(tb) == 2
    assert all(c in BASE36 for c in tb)


def test_encode_time_bucket_deterministic_for_same_ts():
    from datetime import datetime, timezone
    ts = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert encode_time_bucket(ts) == encode_time_bucket(ts)


# ─────────────────────────────── next_sequence ────────────────────────────────

def test_next_sequence_increments(tmp_path: Path):
    db = tmp_path / "seq.db"
    first = next_sequence(db)
    second = next_sequence(db)
    assert second == (first + 1) % 1296


def test_next_sequence_wraps_at_1296(tmp_path: Path):
    db = tmp_path / "seq.db"
    # Force counter to 1295
    import sqlite3
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE IF NOT EXISTS _seq (val INTEGER NOT NULL DEFAULT 0)")
    conn.execute("INSERT OR REPLACE INTO _seq VALUES (1294)")
    conn.commit()
    conn.close()
    v1 = next_sequence(db)   # → 1295
    v2 = next_sequence(db)   # → 0 (wrap)
    assert v1 == 1295
    assert v2 == 0
