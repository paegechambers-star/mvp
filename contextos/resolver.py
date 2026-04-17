"""
ContextOS™ query resolver with citation-graph support.

The resolver answers structured queries over the Register and Index.
It also builds networkx citation graphs for visualisation and cycle detection.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import networkx as nx

from contextos.index import ContextOSIndex
from contextos.register import Register
from contextos.types import Cluster, SSOTEntry, TruthGate, WorkEntry

_TRUTH_GATES_REQUIRING_CITATION = {
    TruthGate.SINGLE_SOURCE,
    TruthGate.CORROBORATED,
    TruthGate.AUTHORITATIVE,
}


class QueryResult:
    """Lightweight container for resolver query results."""

    def __init__(
        self,
        ssot: List[SSOTEntry],
        work: List[WorkEntry],
        query: str,
    ) -> None:
        self.ssot = ssot
        self.work = work
        self.query = query
        self.total = len(ssot) + len(work)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<QueryResult query={self.query!r} total={self.total}>"


class Resolver:
    """
    Query engine for ContextOS.

    Wraps Register + Index and provides higher-level retrieval methods.
    """

    def __init__(self, register: Register, index: ContextOSIndex) -> None:
        self._register = register
        self._index = index

    # ------------------------------------------------------------------
    # Basic lookups
    # ------------------------------------------------------------------

    def get_ssot(self, nkid: str) -> Optional[SSOTEntry]:
        return self._register.get_ssot(nkid)

    def get_work(self, mkid: str) -> Optional[WorkEntry]:
        return self._register.get_work(mkid)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def query(
        self,
        *,
        cluster: Optional[Cluster] = None,
        truth_gate: Optional[TruthGate] = None,
        kind: Optional[str] = None,          # "NK" or "MK"
        active_only: bool = True,
    ) -> QueryResult:
        """
        Flexible query over the Register.

        Args:
            cluster:     Filter by cluster.
            truth_gate:  Filter by truth_gate.
            kind:        "NK" → SSOT only, "MK" → WORK only, None → both.
            active_only: For SSOT, exclude superseded entries.

        Returns:
            :class:`QueryResult` with matching entries.
        """
        ssot_results: List[SSOTEntry] = []
        work_results: List[WorkEntry] = []

        if kind in (None, "NK"):
            entries = (
                self._register.ssot_by_cluster(cluster)
                if cluster else self._register.all_ssot()
            )
            for e in entries:
                if active_only and e.superseded_by:
                    continue
                if truth_gate and e.truth_gate != truth_gate:
                    continue
                ssot_results.append(e)

        if kind in (None, "MK"):
            entries_w = self._register.all_work()
            for e in entries_w:
                if cluster and e.cluster != cluster:
                    continue
                if truth_gate and e.truth_gate != truth_gate:
                    continue
                work_results.append(e)

        desc_parts = []
        if cluster:
            desc_parts.append(f"cluster={cluster.name}")
        if truth_gate:
            desc_parts.append(f"truth_gate={truth_gate.name}")
        if kind:
            desc_parts.append(f"kind={kind}")
        return QueryResult(ssot_results, work_results, query=" ".join(desc_parts) or "*")

    def find_unverified(self) -> List[SSOTEntry]:
        """Return all active SSOT entries with TruthGate.UNVERIFIED."""
        return [
            e for e in self._register.all_ssot()
            if e.truth_gate == TruthGate.UNVERIFIED and not e.superseded_by
        ]

    # ------------------------------------------------------------------
    # Citation-graph
    # ------------------------------------------------------------------

    def build_citation_graph(
        self,
        include_work: bool = False,
    ) -> nx.DiGraph:
        """
        Build a directed citation graph over SSOT (and optionally WORK) entries.

        Nodes are entry IDs; edges point from citing entry → cited entry.
        Edge attribute ``relation`` carries the citation relation string.

        Returns a :class:`networkx.DiGraph`.
        """
        G: nx.DiGraph = nx.DiGraph()

        ssot_entries = self._register.all_ssot()
        for entry in ssot_entries:
            G.add_node(
                entry.nkid,
                kind="NK",
                truth_gate=entry.truth_gate.value,
                cluster=entry.cluster.value,
                superseded_by=entry.superseded_by,
            )
            for cit in entry.citations:
                G.add_edge(entry.nkid, cit.source_id, relation=cit.relation, note=cit.note)

        if include_work:
            for entry in self._register.all_work():
                G.add_node(
                    entry.mkid,
                    kind="MK",
                    truth_gate=entry.truth_gate.value,
                    cluster=entry.cluster.value,
                )
                for cit in entry.citations:
                    G.add_edge(entry.mkid, cit.source_id, relation=cit.relation, note=cit.note)

        return G

    def citation_cycles(self, include_work: bool = False) -> List[List[str]]:
        """Return all citation cycles found in the graph (should be empty in healthy state)."""
        G = self.build_citation_graph(include_work=include_work)
        return list(nx.simple_cycles(G))

    def validate_citations(self) -> List[Dict[str, Any]]:
        """
        Check the No-Citation = No-Assertion invariant across all SSOT entries.

        Returns a list of violation dicts (empty list = all good).
        """
        violations: List[Dict[str, Any]] = []
        for entry in self._register.all_ssot():
            if (
                entry.truth_gate in _TRUTH_GATES_REQUIRING_CITATION
                and not entry.citations
                and not entry.superseded_by
            ):
                violations.append({
                    "nkid": entry.nkid,
                    "truth_gate": entry.truth_gate.value,
                    "issue": "No citations for non-empty assertion",
                })
        return violations
