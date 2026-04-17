"""
ContextOS™ internal SHA256-chained audit log.

Stored in SQLite (WAL mode) for durability and atomic writes, with an
NDJSON export for interoperability.  Every CommitBlock written to the
Register must produce exactly one LogEntry here (mutual dependency enforced
by the Register calling append() inside the same SQLite connection).

Chain structure:
  hash = SHA256(canonical_json(entry_data) + prev_hash)
  first entry uses GENESIS_HASH = "0" * 64
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from contextos.types import CommitBlock

GENESIS_HASH: str = "0" * 64

_DEFAULT_BASE: Path = Path.home() / ".frapp" / "contextos"


# ─────────────────────────────── LogEntry ────────────────────────────────────


class LogEntry:
    """An immutable row in the ContextOS internal audit log."""

    __slots__ = (
        "chain_index",
        "commit_id",
        "operation",
        "target_id",
        "actor",
        "timestamp",
        "content_hash",
        "prev_hash",
        "hash",
        "extra",
    )

    def __init__(
        self,
        chain_index: int,
        commit_id: str,
        operation: str,
        target_id: str,
        actor: str,
        timestamp: str,
        content_hash: str,
        prev_hash: str,
        hash_: str,
        extra: Optional[str] = None,
    ) -> None:
        self.chain_index = chain_index
        self.commit_id = commit_id
        self.operation = operation
        self.target_id = target_id
        self.actor = actor
        self.timestamp = timestamp
        self.content_hash = content_hash
        self.prev_hash = prev_hash
        self.hash = hash_
        self.extra = extra or "{}"

    def to_dict(self) -> dict:  # type: ignore[type-arg]
        return {
            "chain_index": self.chain_index,
            "commit_id": self.commit_id,
            "operation": self.operation,
            "target_id": self.target_id,
            "actor": self.actor,
            "timestamp": self.timestamp,
            "content_hash": self.content_hash,
            "prev_hash": self.prev_hash,
            "hash": self.hash,
            "extra": json.loads(self.extra),
        }


class TamperDetectedError(Exception):
    """Raised when verify_chain() finds a broken link."""


# ─────────────────────────────── ContextOSLog ────────────────────────────────


class ContextOSLog:
    """
    SHA256-chained append-only log for ContextOS.

    Usage:
        log = ContextOSLog(db_path)
        with sqlite3.connect(db_path) as conn:
            entry = log.append(conn, commit_block)
    """

    _CREATE = """
        CREATE TABLE IF NOT EXISTS contextos_log (
            chain_index  INTEGER PRIMARY KEY,
            commit_id    TEXT NOT NULL,
            operation    TEXT NOT NULL,
            target_id    TEXT NOT NULL,
            actor        TEXT NOT NULL,
            timestamp    TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            prev_hash    TEXT NOT NULL,
            hash         TEXT NOT NULL,
            extra        TEXT
        )
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(self._CREATE)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_hash(entry_data: dict, prev_hash: str) -> str:  # type: ignore[type-arg]
        payload = json.dumps(entry_data, sort_keys=True, default=str)
        raw = f"{payload}{prev_hash}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def _last_hash(self, conn: sqlite3.Connection) -> tuple[int, str]:
        """Return (next_chain_index, prev_hash) from the current connection."""
        row = conn.execute(
            "SELECT chain_index, hash FROM contextos_log ORDER BY chain_index DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return 0, GENESIS_HASH
        return row[0] + 1, row[1]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append(self, conn: sqlite3.Connection, commit: CommitBlock) -> LogEntry:
        """
        Append a CommitBlock to the log using an existing SQLite connection.

        Must be called inside an active transaction so the log write and the
        register write are committed atomically.
        """
        chain_index, prev_hash = self._last_hash(conn)
        ts = commit.timestamp.isoformat()
        entry_data = {
            "commit_id":   commit.commit_id,
            "operation":   commit.operation.value,
            "target_id":   commit.target_id,
            "actor":       commit.actor.value,
            "timestamp":   ts,
            "content_hash": commit.new_content_hash,
        }
        computed_hash = self._compute_hash(entry_data, prev_hash)

        conn.execute(
            """INSERT INTO contextos_log
               (chain_index, commit_id, operation, target_id, actor,
                timestamp, content_hash, prev_hash, hash, extra)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                chain_index,
                commit.commit_id,
                commit.operation.value,
                commit.target_id,
                commit.actor.value,
                ts,
                commit.new_content_hash,
                prev_hash,
                computed_hash,
                commit._delta_json,
            ),
        )
        return LogEntry(
            chain_index=chain_index,
            commit_id=commit.commit_id,
            operation=commit.operation.value,
            target_id=commit.target_id,
            actor=commit.actor.value,
            timestamp=ts,
            content_hash=commit.new_content_hash,
            prev_hash=prev_hash,
            hash_=computed_hash,
            extra=commit._delta_json,
        )

    def verify_chain(self) -> bool:
        """
        Recompute every hash from scratch and verify back-pointers.

        Returns True if intact; raises TamperDetectedError on first broken link.
        """
        with sqlite3.connect(str(self._db_path)) as conn:
            rows = conn.execute(
                "SELECT chain_index,commit_id,operation,target_id,actor,"
                "timestamp,content_hash,prev_hash,hash FROM contextos_log "
                "ORDER BY chain_index"
            ).fetchall()

        prev_hash = GENESIS_HASH
        for row in rows:
            (idx, commit_id, operation, target_id, actor,
             timestamp, content_hash, stored_prev, stored_hash) = row

            if stored_prev != prev_hash:
                raise TamperDetectedError(
                    f"Back-pointer mismatch at chain_index={idx}: "
                    f"stored={stored_prev[:16]}… expected={prev_hash[:16]}…"
                )
            entry_data = {
                "commit_id": commit_id,
                "operation": operation,
                "target_id": target_id,
                "actor": actor,
                "timestamp": timestamp,
                "content_hash": content_hash,
            }
            expected = self._compute_hash(entry_data, prev_hash)
            if stored_hash != expected:
                raise TamperDetectedError(
                    f"Hash mismatch at chain_index={idx}: "
                    f"stored={stored_hash[:16]}… recomputed={expected[:16]}…"
                )
            prev_hash = stored_hash
        return True

    def entries(self) -> List[LogEntry]:
        """Return all log entries in chain order."""
        with sqlite3.connect(str(self._db_path)) as conn:
            rows = conn.execute(
                "SELECT chain_index,commit_id,operation,target_id,actor,"
                "timestamp,content_hash,prev_hash,hash,extra "
                "FROM contextos_log ORDER BY chain_index"
            ).fetchall()
        return [
            LogEntry(
                chain_index=r[0], commit_id=r[1], operation=r[2],
                target_id=r[3], actor=r[4], timestamp=r[5],
                content_hash=r[6], prev_hash=r[7], hash_=r[8], extra=r[9],
            )
            for r in rows
        ]

    def __len__(self) -> int:
        with sqlite3.connect(str(self._db_path)) as conn:
            return conn.execute("SELECT COUNT(*) FROM contextos_log").fetchone()[0]

    def export_ndjson(self, dest: Path) -> None:
        """Write all log entries to *dest* as newline-delimited JSON."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("w", encoding="utf-8") as fh:
            for entry in self.entries():
                fh.write(json.dumps(entry.to_dict(), default=str) + "\n")
