"""Tests for contextos/register.py — 10 tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from contextos.log import ContextOSLog
from contextos.register import Register
from contextos.store import sha256_of
from contextos.types import Actor, Citation, Cluster, EntryType, Kind, SSOTEntry, TruthGate, WorkEntry
from tests.contextos.conftest import make_mkid, make_nkid, make_ssot, make_work


def test_insert_and_get_ssot(register: Register):
    nkid = make_nkid(0)
    entry = make_ssot(nkid, "fact one")
    register.insert_ssot(entry)
    fetched = register.get_ssot(nkid)
    assert fetched is not None
    assert fetched.content == "fact one"
    assert fetched.nkid == nkid


def test_ssot_insert_emits_log_entry(register: Register, cos_log: ContextOSLog):
    nkid = make_nkid(1)
    register.insert_ssot(make_ssot(nkid))
    assert len(cos_log) == 1


def test_ssot_immutable_on_duplicate(register: Register):
    nkid = make_nkid(2)
    entry = make_ssot(nkid)
    register.insert_ssot(entry)
    with pytest.raises(Exception):  # sqlite UNIQUE constraint
        register.insert_ssot(entry)


def test_insert_and_get_work(register: Register):
    mkid = make_mkid(0)
    entry = make_work(mkid, "draft v1")
    register.insert_work(entry)
    fetched = register.get_work(mkid)
    assert fetched is not None
    assert fetched.content == "draft v1"


def test_work_insert_emits_log_entry(register: Register, cos_log: ContextOSLog):
    mkid = make_mkid(1)
    register.insert_work(make_work(mkid))
    assert len(cos_log) == 1


def test_update_work_changes_content(register: Register):
    mkid = make_mkid(2)
    register.insert_work(make_work(mkid, "original"))
    register.update_work(mkid, "updated", Actor.USER)
    updated = register.get_work(mkid)
    assert updated.content == "updated"
    assert updated.content_hash == sha256_of("updated")


def test_update_work_emits_two_log_entries(register: Register, cos_log: ContextOSLog):
    mkid = make_mkid(3)
    register.insert_work(make_work(mkid, "v1"))
    register.update_work(mkid, "v2", Actor.USER)
    assert len(cos_log) == 2


def test_no_citation_no_assertion_enforced(register: Register):
    nkid = make_nkid(4)
    bad_entry = make_ssot(nkid, truth_gate=TruthGate.SINGLE_SOURCE, citations=())
    with pytest.raises(ValueError, match="No-Citation"):
        register.insert_ssot(bad_entry)


def test_promote_work_marks_promoted(register: Register, cos_log: ContextOSLog):
    mkid = make_mkid(5)
    nkid = make_nkid(5)
    register.insert_work(make_work(mkid))
    register.promote_work(mkid, nkid, Actor.USER)
    w = register.get_work(mkid)
    assert w.promoted is True
    assert w.promoted_nkid == nkid


def test_all_ssot_returns_all(register: Register):
    for i in range(3):
        register.insert_ssot(make_ssot(make_nkid(i), f"content {i}"))
    assert len(register.all_ssot()) == 3
