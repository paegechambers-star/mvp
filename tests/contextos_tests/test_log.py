"""Tests for contextos/log.py — 8 tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from contextos.commit import make_commit
from contextos.log import GENESIS_HASH, ContextOSLog, TamperDetectedError
from contextos.types import Actor, CommitOp


def _append_one(log: ContextOSLog, db_path: Path, target: str = "NK00000000000000") -> None:
    commit = make_commit(
        operation=CommitOp.PATCH,
        target_id=target,
        actor=Actor.USER,
        new_content_hash="a" * 64,
    )
    with sqlite3.connect(str(db_path)) as conn:
        log.append(conn, commit)


def test_first_entry_uses_genesis_hash(tmp_path: Path):
    db = tmp_path / "test.db"
    log = ContextOSLog(db)
    _append_one(log, db)
    entries = log.entries()
    assert entries[0].prev_hash == GENESIS_HASH


def test_chain_links_correctly(tmp_path: Path):
    db = tmp_path / "test.db"
    log = ContextOSLog(db)
    _append_one(log, db, "NK00000000000001")
    _append_one(log, db, "NK00000000000002")
    entries = log.entries()
    assert entries[1].prev_hash == entries[0].hash


def test_verify_chain_passes(tmp_path: Path):
    db = tmp_path / "test.db"
    log = ContextOSLog(db)
    _append_one(log, db)
    _append_one(log, db)
    assert log.verify_chain() is True


def test_verify_chain_empty_passes(tmp_path: Path):
    db = tmp_path / "test.db"
    log = ContextOSLog(db)
    assert log.verify_chain() is True


def test_tamper_detection_hash(tmp_path: Path):
    db = tmp_path / "test.db"
    log = ContextOSLog(db)
    _append_one(log, db)
    # Directly corrupt the stored hash
    with sqlite3.connect(str(db)) as conn:
        conn.execute("UPDATE contextos_log SET hash='BADHASH' WHERE chain_index=0")
    with pytest.raises(TamperDetectedError):
        log.verify_chain()


def test_tamper_detection_prev_hash(tmp_path: Path):
    db = tmp_path / "test.db"
    log = ContextOSLog(db)
    _append_one(log, db)
    _append_one(log, db)
    with sqlite3.connect(str(db)) as conn:
        conn.execute("UPDATE contextos_log SET prev_hash='BADHASH' WHERE chain_index=1")
    with pytest.raises(TamperDetectedError):
        log.verify_chain()


def test_log_entry_has_correct_fields(tmp_path: Path):
    db = tmp_path / "test.db"
    log = ContextOSLog(db)
    _append_one(log, db, "NK00000000000099")
    entry = log.entries()[0]
    assert entry.chain_index == 0
    assert entry.target_id == "NK00000000000099"
    assert entry.operation == CommitOp.PATCH.value
    assert entry.actor == Actor.USER.value
    assert len(entry.hash) == 64


def test_len_returns_entry_count(tmp_path: Path):
    db = tmp_path / "test.db"
    log = ContextOSLog(db)
    assert len(log) == 0
    _append_one(log, db)
    _append_one(log, db)
    assert len(log) == 2
