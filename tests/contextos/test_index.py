"""Tests for contextos/index.py — 6 tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from contextos.index import ContextOSIndex
from contextos.types import Cluster
from tests.contextos.conftest import make_mkid, make_nkid, make_ssot, make_work


def test_add_ssot_and_lookup(index: ContextOSIndex):
    nkid = make_nkid(0)
    entry = make_ssot(nkid)
    index.add_ssot(entry)
    meta = index.get(nkid)
    assert meta is not None
    assert meta["kind"] == "NK"


def test_add_work_and_lookup(index: ContextOSIndex):
    mkid = make_mkid(0)
    entry = make_work(mkid)
    index.add_work(entry)
    assert index.exists(mkid)


def test_by_cluster(index: ContextOSIndex):
    nkid1 = make_nkid(0, cluster=Cluster.RESEARCH)
    nkid2 = make_nkid(1, cluster=Cluster.COMPLIANCE)
    index.add_ssot(make_ssot(nkid1, cluster=Cluster.RESEARCH))
    index.add_ssot(make_ssot(nkid2, cluster=Cluster.COMPLIANCE))
    research = index.by_cluster(Cluster.RESEARCH)
    assert nkid1 in research
    assert nkid2 not in research


def test_persist_and_reload(tmp_base: Path, index: ContextOSIndex):
    nkid = make_nkid(0)
    index.add_ssot(make_ssot(nkid))
    index.save()
    # Reload from same path
    reloaded = ContextOSIndex(index_path=tmp_base / "index.json")
    assert reloaded.exists(nkid)


def test_build_from_register(index: ContextOSIndex, register):
    for i in range(3):
        register.insert_ssot(make_ssot(make_nkid(i), f"c{i}"))
    index.build_from_register(register.all_ssot(), register.all_work())
    assert len(index) == 3


def test_active_ssot_excludes_superseded(index: ContextOSIndex):
    nkid1 = make_nkid(0)
    nkid2 = make_nkid(1)
    from tests.contextos.conftest import make_ssot
    from contextos.types import SSOTEntry
    entry1 = make_ssot(nkid1)
    # Create a superseded variant
    import dataclasses
    superseded = dataclasses.replace(entry1, superseded_by=nkid2)
    index.add_ssot(superseded)
    index.add_ssot(make_ssot(nkid2))
    active = index.active_ssot()
    assert nkid2 in active
    assert nkid1 not in active
