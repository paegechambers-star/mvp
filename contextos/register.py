"""
ContextOS™ Register — SQLite WAL-mode knowledge store.

Two partitions in a single database:
  ssot  — immutable (INSERT only; G.O.D.A.I. Invariant 2: SSOT never mutated)
  work  — mutable (INSERT + UPDATE; no DELETE)

Mutual-dependency invariant (Invariant 1):
  Every write to ssot or work is wrapped in a single SQLite transaction that
  also appends a LogEntry via ContextOSLog.append().  If either half fails,
  the transaction rolls back entirely — there is no state where a register
  entry exists without a corresponding log entry, or vice-versa.

Citation invariant (Invariant 4 — No-Citation = No-Assertion):
  Entries with TruthGate > EMPTY_BUT_VERIFIED must carry ≥1 Citation.
  Enforced in _assert_citations() before any write.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from contextos.commit import make_commit, patch_commit, promote_commit
from contextos.log import ContextOSLog
from contextos.store import sha256_of
from contextos.types import (
    Actor,
    Citation,
    Cluster,
    CommitOp,
    EntryType,
    SSOTEntry,
    TruthGate,
    WorkEntry,
)

_DEFAULT_BASE: Path = Path.home() / ".frapp" / "contextos"

_TRUTH_GATES_REQUIRING_CITATION = {
    TruthGate.SINGLE_SOURCE,
    TruthGate.CORROBORATED,
    TruthGate.AUTHORITATIVE,
}


def _assert_citations(truth_gate: TruthGate, citations: list) -> None:  # type: ignore[type-arg]
    if truth_gate in _TRUTH_GATES_REQUIRING_CITATION and not citations:
        raise ValueError(
            f"TruthGate.{truth_gate.name} requires at least one Citation "
            "(No-Citation = No-Assertion invariant)"
        )


def _citations_to_json(citations: Any) -> str:
    return json.dumps(
        [{"source_id": c.source_id, "relation": c.relation, "note": c.note}
         for c in citations],
        default=str,
    )


def _citations_from_json(raw: Optional[str]) -> List[Citation]:
    if not raw:
        return []
    return [
        Citation(source_id=d["source_id"], relation=d["relation"], note=d.get("note", ""))
        for d in json.loads(raw)
    ]


class Register:
    """
    The central knowledge store for ContextOS.

    All writes are transactional and produce exactly one log entry each.
    """

    _CREATE_SSOT = """
        CREATE TABLE IF NOT EXISTS ssot (
            nkid         TEXT PRIMARY KEY,
            content      TEXT NOT NULL,
            truth_gate   TEXT NOT NULL,
            citations    TEXT,          -- JSON array
            content_hash TEXT NOT NULL,
            created_at   TEXT NOT NULL,
            cluster      TEXT NOT NULL,
            actor        TEXT NOT NULL,
            superseded_by TEXT          -- NKID of replacement
        )
    """
    _CREATE_WORK = """
        CREATE TABLE IF NOT EXISTS work (
            mkid         TEXT PRIMARY KEY,
            content      TEXT NOT NULL,
            truth_gate   TEXT NOT NULL,
            citations    TEXT,
            content_hash TEXT NOT NULL,
            created_at   TEXT NOT NULL,
            modified_at  TEXT NOT NULL,
            cluster      TEXT NOT NULL,
            actor        TEXT NOT NULL,
            promoted     INTEGER NOT NULL DEFAULT 0,
            promoted_nkid TEXT
        )
    """

    def __init__(self, db_path: Path, log: ContextOSLog) -> None:
        self._db_path = db_path
        self._log = log
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(self._CREATE_SSOT)
            conn.execute(self._CREATE_WORK)

    # ------------------------------------------------------------------
    # SSOT (immutable partition)
    # ------------------------------------------------------------------

    def insert_ssot(
        self,
        entry: SSOTEntry,
        *,
        actor: Optional[Actor] = None,
        prev_content_hash: Optional[str] = None,
        operation: CommitOp = CommitOp.PATCH,
    ) -> None:
        """
        Insert a new SSOT entry.  Raises if the NKID already exists.
        Mutual-dependency: log entry is written in the same transaction.
        """
        _assert_citations(entry.truth_gate, entry.citations)

        commit = make_commit(
            operation=operation,
            target_id=entry.nkid,
            actor=actor or entry.actor,
            new_content_hash=entry.content_hash,
            prev_content_hash=prev_content_hash,
            delta={"cluster": entry.cluster.value, "truth_gate": entry.truth_gate.value},
        )

        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            # Log first — mutual dependency
            self._log.append(conn, commit)
            conn.execute(
                """INSERT INTO ssot
                   (nkid,content,truth_gate,citations,content_hash,
                    created_at,cluster,actor,superseded_by)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    entry.nkid,
                    entry.content,
                    entry.truth_gate.value,
                    _citations_to_json(entry.citations),
                    entry.content_hash,
                    entry.created_at.isoformat(),
                    entry.cluster.value,
                    entry.actor.value,
                    entry.superseded_by,
                ),
            )

    def supersede_ssot(
        self,
        old_nkid: str,
        new_entry: SSOTEntry,
        actor: Actor,
    ) -> None:
        """
        Insert *new_entry* and mark *old_nkid* as superseded by it.

        Both operations occur in a single transaction.
        """
        _assert_citations(new_entry.truth_gate, new_entry.citations)

        old = self.get_ssot(old_nkid)
        if old is None:
            raise KeyError(f"SSOT entry not found: {old_nkid}")

        commit = make_commit(
            operation=CommitOp.SUPERSEDE,
            target_id=new_entry.nkid,
            actor=actor,
            new_content_hash=new_entry.content_hash,
            prev_content_hash=old.content_hash,
            delta={"supersedes": old_nkid},
        )

        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            self._log.append(conn, commit)
            conn.execute(
                "UPDATE ssot SET superseded_by=? WHERE nkid=?",
                (new_entry.nkid, old_nkid),
            )
            conn.execute(
                """INSERT INTO ssot
                   (nkid,content,truth_gate,citations,content_hash,
                    created_at,cluster,actor,superseded_by)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    new_entry.nkid,
                    new_entry.content,
                    new_entry.truth_gate.value,
                    _citations_to_json(new_entry.citations),
                    new_entry.content_hash,
                    new_entry.created_at.isoformat(),
                    new_entry.cluster.value,
                    new_entry.actor.value,
                    None,
                ),
            )

    def get_ssot(self, nkid: str) -> Optional[SSOTEntry]:
        """Return the SSOT entry for *nkid*, or None."""
        with sqlite3.connect(str(self._db_path)) as conn:
            row = conn.execute(
                "SELECT nkid,content,truth_gate,citations,content_hash,"
                "created_at,cluster,actor,superseded_by FROM ssot WHERE nkid=?",
                (nkid,),
            ).fetchone()
        if row is None:
            return None
        return SSOTEntry(
            nkid=row[0],
            content=row[1],
            truth_gate=TruthGate(row[2]),
            citations=tuple(_citations_from_json(row[3])),
            content_hash=row[4],
            created_at=datetime.fromisoformat(row[5]),
            cluster=Cluster(row[6]),
            actor=Actor(row[7]),
            superseded_by=row[8],
        )

    def all_ssot(self) -> List[SSOTEntry]:
        """Return all SSOT entries (no filter)."""
        with sqlite3.connect(str(self._db_path)) as conn:
            rows = conn.execute(
                "SELECT nkid,content,truth_gate,citations,content_hash,"
                "created_at,cluster,actor,superseded_by FROM ssot"
            ).fetchall()
        return [
            SSOTEntry(
                nkid=r[0], content=r[1], truth_gate=TruthGate(r[2]),
                citations=tuple(_citations_from_json(r[3])),
                content_hash=r[4],
                created_at=datetime.fromisoformat(r[5]),
                cluster=Cluster(r[6]), actor=Actor(r[7]), superseded_by=r[8],
            )
            for r in rows
        ]

    def ssot_by_cluster(self, cluster: Cluster) -> List[SSOTEntry]:
        with sqlite3.connect(str(self._db_path)) as conn:
            rows = conn.execute(
                "SELECT nkid,content,truth_gate,citations,content_hash,"
                "created_at,cluster,actor,superseded_by FROM ssot WHERE cluster=?",
                (cluster.value,),
            ).fetchall()
        return [
            SSOTEntry(
                nkid=r[0], content=r[1], truth_gate=TruthGate(r[2]),
                citations=tuple(_citations_from_json(r[3])),
                content_hash=r[4],
                created_at=datetime.fromisoformat(r[5]),
                cluster=Cluster(r[6]), actor=Actor(r[7]), superseded_by=r[8],
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # WORK (mutable partition)
    # ------------------------------------------------------------------

    def insert_work(self, entry: WorkEntry) -> None:
        """Insert a new WORK entry. Mutual-dependency: log entry in same transaction."""
        _assert_citations(entry.truth_gate, entry.citations)

        commit = make_commit(
            operation=CommitOp.PATCH,
            target_id=entry.mkid,
            actor=entry.actor,
            new_content_hash=entry.content_hash,
            delta={"cluster": entry.cluster.value, "action": "create"},
        )

        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            self._log.append(conn, commit)
            conn.execute(
                """INSERT INTO work
                   (mkid,content,truth_gate,citations,content_hash,
                    created_at,modified_at,cluster,actor,promoted,promoted_nkid)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    entry.mkid,
                    entry.content,
                    entry.truth_gate.value,
                    _citations_to_json(entry.citations),
                    entry.content_hash,
                    entry.created_at.isoformat(),
                    entry.modified_at.isoformat(),
                    entry.cluster.value,
                    entry.actor.value,
                    1 if entry.promoted else 0,
                    entry.promoted_nkid,
                ),
            )

    def update_work(
        self,
        mkid: str,
        content: str,
        actor: Actor,
        truth_gate: Optional[TruthGate] = None,
        citations: Optional[List[Citation]] = None,
    ) -> None:
        """
        Patch a WORK entry in-place.

        Only content, truth_gate, and citations can be updated.
        """
        existing = self.get_work(mkid)
        if existing is None:
            raise KeyError(f"WORK entry not found: {mkid}")
        if existing.promoted:
            raise ValueError(f"Cannot patch promoted WORK entry: {mkid}")

        new_tg = truth_gate or existing.truth_gate
        new_cits = citations if citations is not None else existing.citations
        _assert_citations(new_tg, new_cits)

        old_hash = existing.content_hash
        new_hash = sha256_of(content)
        now = datetime.now(timezone.utc)

        commit = patch_commit(mkid, actor, old_hash, new_hash, ["content"])

        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            self._log.append(conn, commit)
            conn.execute(
                """UPDATE work
                   SET content=?, truth_gate=?, citations=?,
                       content_hash=?, modified_at=?
                   WHERE mkid=?""",
                (
                    content,
                    new_tg.value,
                    _citations_to_json(new_cits),
                    new_hash,
                    now.isoformat(),
                    mkid,
                ),
            )

    def promote_work(self, mkid: str, nkid: str, actor: Actor) -> None:
        """
        Mark a WORK entry as promoted and record the resulting NKID.

        Does NOT insert into ssot — the caller must do that separately
        using insert_ssot() with operation=CommitOp.PROMOTE.
        """
        existing = self.get_work(mkid)
        if existing is None:
            raise KeyError(f"WORK entry not found: {mkid}")
        if existing.promoted:
            raise ValueError(f"Already promoted: {mkid}")

        commit = promote_commit(mkid, nkid, actor, existing.content_hash)

        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            self._log.append(conn, commit)
            conn.execute(
                "UPDATE work SET promoted=1, promoted_nkid=? WHERE mkid=?",
                (nkid, mkid),
            )

    def get_work(self, mkid: str) -> Optional[WorkEntry]:
        with sqlite3.connect(str(self._db_path)) as conn:
            row = conn.execute(
                "SELECT mkid,content,truth_gate,citations,content_hash,"
                "created_at,modified_at,cluster,actor,promoted,promoted_nkid "
                "FROM work WHERE mkid=?",
                (mkid,),
            ).fetchone()
        if row is None:
            return None
        return WorkEntry(
            mkid=row[0], content=row[1], truth_gate=TruthGate(row[2]),
            citations=_citations_from_json(row[3]),
            content_hash=row[4],
            created_at=datetime.fromisoformat(row[5]),
            modified_at=datetime.fromisoformat(row[6]),
            cluster=Cluster(row[7]), actor=Actor(row[8]),
            promoted=bool(row[9]), promoted_nkid=row[10],
        )

    def all_work(self) -> List[WorkEntry]:
        with sqlite3.connect(str(self._db_path)) as conn:
            rows = conn.execute(
                "SELECT mkid,content,truth_gate,citations,content_hash,"
                "created_at,modified_at,cluster,actor,promoted,promoted_nkid FROM work"
            ).fetchall()
        return [
            WorkEntry(
                mkid=r[0], content=r[1], truth_gate=TruthGate(r[2]),
                citations=_citations_from_json(r[3]),
                content_hash=r[4],
                created_at=datetime.fromisoformat(r[5]),
                modified_at=datetime.fromisoformat(r[6]),
                cluster=Cluster(r[7]), actor=Actor(r[8]),
                promoted=bool(r[9]), promoted_nkid=r[10],
            )
            for r in rows
        ]
