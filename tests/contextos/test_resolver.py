"""Tests for contextos/resolver.py — 6 tests."""

from __future__ import annotations

import pytest

from contextos.resolver import Resolver
from contextos.types import Citation, Cluster, TruthGate
from tests.contextos.conftest import make_mkid, make_nkid, make_ssot, make_work


def test_resolve_ssot_by_id(resolver: Resolver, register):
    nkid = make_nkid(0)
    register.insert_ssot(make_ssot(nkid, "knowledge fact"))
    result = resolver.get_ssot(nkid)
    assert result is not None
    assert result.content == "knowledge fact"


def test_resolve_work_by_id(resolver: Resolver, register):
    mkid = make_mkid(0)
    register.insert_work(make_work(mkid, "draft"))
    result = resolver.get_work(mkid)
    assert result is not None
    assert result.content == "draft"


def test_query_by_cluster(resolver: Resolver, register):
    nkid1 = make_nkid(0, cluster=Cluster.RESEARCH)
    nkid2 = make_nkid(1, cluster=Cluster.LEGAL)
    register.insert_ssot(make_ssot(nkid1, cluster=Cluster.RESEARCH))
    register.insert_ssot(make_ssot(nkid2, cluster=Cluster.LEGAL))
    result = resolver.query(cluster=Cluster.RESEARCH, kind="NK")
    ids = [e.nkid for e in result.ssot]
    assert nkid1 in ids
    assert nkid2 not in ids


def test_citation_graph_has_nodes(resolver: Resolver, register):
    nkid1 = make_nkid(0)
    nkid2 = make_nkid(1)
    register.insert_ssot(make_ssot(nkid1))
    cit = Citation(source_id=nkid1, relation="supports")
    register.insert_ssot(make_ssot(
        nkid2,
        truth_gate=TruthGate.SINGLE_SOURCE,
        citations=(cit,),
    ))
    G = resolver.build_citation_graph()
    assert nkid1 in G.nodes
    assert nkid2 in G.nodes
    assert G.has_edge(nkid2, nkid1)


def test_find_unverified(resolver: Resolver, register):
    nkid_unv = make_nkid(0)
    nkid_auth = make_nkid(1)
    register.insert_ssot(make_ssot(nkid_unv, truth_gate=TruthGate.UNVERIFIED))
    register.insert_ssot(make_ssot(
        nkid_auth,
        truth_gate=TruthGate.EMPTY_BUT_VERIFIED,
    ))
    unverified = resolver.find_unverified()
    ids = [e.nkid for e in unverified]
    assert nkid_unv in ids
    assert nkid_auth not in ids


def test_validate_citations_detects_violation(resolver: Resolver, register):
    # Insert a SINGLE_SOURCE entry without any citation via raw SQL
    # (bypassing the invariant check in register to test the resolver's checker)
    import sqlite3
    from datetime import datetime, timezone
    from contextos.store import sha256_of
    nkid = make_nkid(2)
    now = datetime.now(timezone.utc).isoformat()
    content = "bad assertion"
    with sqlite3.connect(str(register._db_path)) as conn:
        conn.execute(
            "INSERT INTO ssot (nkid,content,truth_gate,citations,content_hash,"
            "created_at,cluster,actor) VALUES (?,?,?,?,?,?,?,?)",
            (nkid, content, TruthGate.SINGLE_SOURCE.value, "[]",
             sha256_of(content), now, Cluster.GENERAL.value, "01"),
        )
    violations = resolver.validate_citations()
    assert any(v["nkid"] == nkid for v in violations)
