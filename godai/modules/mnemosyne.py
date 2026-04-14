"""
MNEMOSYNE — Immutable, append-only audit log with SHA256 hash chaining.

Implements EU AI Act Article 12 compliant audit trail.
Every routing, policy, auth, and validation decision must be logged here.
No updates, no deletes.  Breaking the chain signals tampering.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import List
from uuid import uuid4

from godai.models.audit import AuditEvent, LogEntry

# The genesis (sentinel) hash used as prev_hash for the very first entry.
GENESIS_HASH: str = "0" * 64

_logger = logging.getLogger("godai.mnemosyne")


class TamperDetectedError(Exception):
    """Raised when :meth:`Mnemosyne.verify_chain` finds a broken link."""


class Mnemosyne:
    """
    Append-only audit log with SHA256 hash chaining.

    Usage pattern (called from every module)::

        event = AuditEvent(event_type="auth", event_data={...},
                           source_module="HERMES", timestamp=now())
        entry = await mnemosyne.append(event)

    Chain verification::

        mnemosyne.verify_chain()   # raises TamperDetectedError if broken

    Thread safety: a single :class:`asyncio.Lock` serialises all appends so
    the chain index and prev_hash are always consistent.
    """

    def __init__(self) -> None:
        self._entries: List[LogEntry] = []
        self._lock: asyncio.Lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_hash(event_data: dict, prev_hash: str) -> str:  # type: ignore[type-arg]
        """
        Compute SHA256(canonical_json(event_data) + prev_hash).

        ``sort_keys=True`` and ``default=str`` guarantee a stable, canonical
        serialisation regardless of dict insertion order.
        """
        payload = json.dumps(event_data, sort_keys=True, default=str)
        raw = f"{payload}{prev_hash}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def append(self, event: AuditEvent) -> LogEntry:
        """
        Append an audit event to the chain.

        Acquires the internal lock to ensure sequential chain indices.
        This is the **only** write path — no update/delete methods exist.

        Args:
            event: The event to record.

        Returns:
            The newly created :class:`~godai.models.audit.LogEntry`.
        """
        async with self._lock:
            prev_hash = self._entries[-1].hash if self._entries else GENESIS_HASH
            chain_index = len(self._entries)
            computed_hash = self._compute_hash(event.event_data, prev_hash)

            entry = LogEntry(
                event_id=uuid4(),
                event_type=event.event_type,
                event_data=event.event_data,
                timestamp=event.timestamp,
                hash=computed_hash,
                prev_hash=prev_hash,
                chain_index=chain_index,
            )
            self._entries.append(entry)

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
        Verify integrity of the complete audit log chain in O(n).

        Recomputes every hash from scratch and checks both the hash value
        and the prev_hash back-pointer.

        Returns:
            ``True`` if the chain is intact.

        Raises:
            TamperDetectedError: With the chain index and details of the
                first broken link found.
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
        """Read-only snapshot of all log entries (returns a copy)."""
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)
