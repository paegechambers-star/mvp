"""Tests for contextos/mkid_runner.py — 5 tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from contextos.mkid_runner import MKIDRunner
from contextos.resolver import Resolver
from tests.contextos.conftest import make_mkid, make_nkid, make_ssot, make_work


def _runner(register, resolver) -> MKIDRunner:
    return MKIDRunner(register, resolver)


def test_seed_defaults_inserts_five_mkids(register, resolver):
    runner = _runner(register, resolver)
    inserted = runner.seed_defaults()
    assert len(inserted) == 5


def test_seed_defaults_is_idempotent(register, resolver):
    runner = _runner(register, resolver)
    runner.seed_defaults()
    second = runner.seed_defaults()
    assert second == []   # nothing inserted on second call


def test_list_mkids_shows_seeded(register, resolver):
    runner = _runner(register, resolver)
    runner.seed_defaults()
    mkids = runner.list_mkids()
    names = [m["name"] for m in mkids]
    assert "list_ssot_facts" in names
    assert "verify_chain" in names
    assert "find_unverified" in names


def test_execute_cluster_summary(register, resolver):
    runner = _runner(register, resolver)
    runner.seed_defaults()

    # Insert a couple of SSOT entries so summary is non-trivial
    for i in range(3):
        register.insert_ssot(make_ssot(make_nkid(i + 10), f"content {i}"))

    mkids = runner.list_mkids()
    cluster_mkid = next(m["mkid"] for m in mkids if m["name"] == "cluster_summary")
    result = runner.execute(cluster_mkid)
    assert "result" in result
    # GENERAL cluster should appear (from our 3 inserts)
    assert "GENERAL" in result["result"]


def test_execute_unknown_mkid_raises(register, resolver):
    runner = _runner(register, resolver)
    with pytest.raises(KeyError):
        runner.execute("NK00000000000000")  # doesn't exist
