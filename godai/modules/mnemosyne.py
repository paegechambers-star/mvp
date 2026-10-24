"""
MNEMOSYNE — Immutable, append-only audit log with SHA256 hash chaining.

Implements EU AI Act Article 12 compliant audit trail.
Every routing, policy, auth, and validation decision must be logged here.
No updates, no deletes.  Breaking the chain signals tampering.

Optional SQLite persistence (B2): pass ``db_path`` to survive restarts.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from uuid import UUID, uuid4

from godai.models.audit import AuditEvent, LogEntry

GENESIS_HASH: str = "0" * 64

_logger = logging.getLogger("godai.mnemosyne")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS mnemosyne_log (
    chain_index  INTEGER PRIMARY KEY,
    event_id     TEXT    NOT NULL,
    event_type   TEXT    NOT NULL,
    source_module TEXT   NOT NULL,
    timestamp    TEXT    NOT NULL,
    event_data   TEXT    NOT NULL,
    hash         TEXT    NOT NULL,
    prev_hash    TEXT    NOT NULL
)
"""


class TamperDetectedError(Exception):
    """Raised when :meth:`Mnemosyne.verify_chain` finds a broken link."""


class Mnemosyne:
    """
    Append-only audit log with SHA256 hash chaining.

    Pass ``db_path`` for SQLite-backed persistence (EU AI Act Art. 12).
    Without it, the log lives in memory only (suitable for tests/dev).

    Usage::

        # In-memory (dev/tests)
        mnemosyne = Mnemosyne()

        # Persistent (production)
        mnemosyne = Mnemosyne(db_path=Path("data/mnemosyne.db"))
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self._entries: List[LogEntry] = []
        self._lock: asyncio.Lock = asyncio.Lock()
        self._db_path: Optional[Path] = db_path
        if db_path is not None:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._init_db()
            self._load_from_db()

    # ------------------------------------------------------------------
    # SQLite helpers (only active when db_path is set)
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        assert self._db_path is not None
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(_CREATE_TABLE)

    def _load_from_db(self) -> None:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT event_id, event_type, source_module, timestamp, "
                "event_data, hash, prev_hash, chain_index "
                "FROM mnemosyne_log ORDER BY chain_index"
            ).fetchall()
        for row in rows:
            eid, etype, src, ts, edata, h, ph, idx = row
            self._entries.append(LogEntry(
                event_id=UUID(eid),
                event_type=etype,
                event_data=json.loads(edata),
                source_module=src,
                timestamp=datetime.fromisoformat(ts),
                hash=h,
                prev_hash=ph,
                chain_index=idx,
            ))

    def _persist(self, entry: LogEntry) -> None:
        if self._db_path is None:
            return
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO mnemosyne_log "
                "(chain_index, event_id, event_type, source_module, timestamp, "
                "event_data, hash, prev_hash) VALUES (?,?,?,?,?,?,?,?)",
                (
                    entry.chain_index,
                    str(entry.event_id),
                    entry.event_type,
                    entry.source_module,
                    entry.timestamp.isoformat(),
                    json.dumps(entry.event_data, sort_keys=True, default=str),
                    entry.hash,
                    entry.prev_hash,
                ),
            )

    # ------------------------------------------------------------------
    # Hash computation
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_hash(event_data: dict, prev_hash: str) -> str:  # type: ignore[type-arg]
        payload = json.dumps(event_data, sort_keys=True, default=str)
        raw = f"{payload}{prev_hash}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def append(self, event: AuditEvent) -> LogEntry:
        """
        Append an audit event to the chain.

        Thread-safe via asyncio.Lock.  Persists to SQLite when db_path is set.
        """
        async with self._lock:
            prev_hash = self._entries[-1].hash if self._entries else GENESIS_HASH
            chain_index = len(self._entries)
            computed_hash = self._compute_hash(event.event_data, prev_hash)

            entry = LogEntry(
                event_id=uuid4(),
                event_type=event.event_type,
                event_data=event.event_data,
                source_module=event.source_module,
                timestamp=event.timestamp,
                hash=computed_hash,
                prev_hash=prev_hash,
                chain_index=chain_index,
            )
            self._entries.append(entry)
            self._persist(entry)

        _logger.debug(
            "MNEMOSYNE[%d] %s from %s hash=%s…",
            chain_index,
            event.event_type,
            event.source_module,
            computed_hash[:16],
        )
        return entry

    def verify_chain(self) -> bool:
        """
        Verify integrity of the complete audit log chain.

        Returns:
            ``True`` if the chain is intact.

        Raises:
            TamperDetectedError: On the first broken link found.
        """
        if not self._entries:
            return True

        prev_hash = GENESIS_HASH
        for entry in self._entries:
            expected = self._compute_hash(entry.event_data, prev_hash)

            if entry.prev_hash != prev_hash:
                raise TamperDetectedError(
                    f"Back-pointer mismatch at chain index {entry.chain_index}: "
                    f"stored prev_hash={entry.prev_hash[:16]}… "
                    f"expected={prev_hash[:16]}…"
                )
            if entry.hash != expected:
                raise TamperDetectedError(
                    f"Hash mismatch at chain index {entry.chain_index}: "
                    f"stored={entry.hash[:16]}… "
                    f"recomputed={expected[:16]}…"
                )
            prev_hash = entry.hash

        return True

    @property
    def entries(self) -> List[LogEntry]:
        """Read-only snapshot of all log entries."""
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)
