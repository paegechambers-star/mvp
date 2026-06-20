"""
DISPATCH BRIDGE — Mobile-to-Desktop async message queue.

Mobile clients POST commands here; desktop Claude polls or subscribes via
WebSocket.  Results flow in the reverse direction.

Invariants:
  - Every enqueued command is assigned a UUID and logged to MNEMOSYNE.
  - Commands expire after TTL seconds to prevent stale queue build-up.
  - The bridge is protocol-agnostic: polling and WebSocket both work.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from godai.models.audit import AuditEvent
from godai.modules.mnemosyne import Mnemosyne

_logger = logging.getLogger("godai.dispatch_bridge")

DEFAULT_TTL_SECONDS = 300  # 5 minutes


@dataclass
class DispatchCommand:
    """A command dispatched from a mobile client, waiting for desktop execution."""

    command_id: UUID
    user_id: str
    payload: str
    context: Dict[str, Any]
    timestamp: datetime
    ttl_seconds: int = DEFAULT_TTL_SECONDS
    result: Optional[str] = None
    completed: bool = False

    @property
    def expired(self) -> bool:
        age = (datetime.now(timezone.utc) - self.timestamp).total_seconds()
        return age > self.ttl_seconds

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_id": str(self.command_id),
            "user_id": self.user_id,
            "payload": self.payload,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
            "completed": self.completed,
            "result": self.result,
        }


class DispatchBridge:
    """
    Async message queue bridging mobile clients and the desktop Claude agent.

    Thread-safety: all mutations go through asyncio; do not call from
    synchronous code without wrapping in ``asyncio.run_coroutine_threadsafe``.
    """

    def __init__(self, mnemosyne: Mnemosyne) -> None:
        self._mnemosyne = mnemosyne
        self._queue: Dict[UUID, DispatchCommand] = {}
        # Signalled whenever a new command is enqueued so WebSocket listeners wake.
        self._new_command_event: asyncio.Event = asyncio.Event()

    # ------------------------------------------------------------------
    # Mobile-side: enqueue a command
    # ------------------------------------------------------------------

    async def enqueue(
        self,
        user_id: str,
        payload: str,
        context: Optional[Dict[str, Any]] = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> DispatchCommand:
        """Accept a command from a mobile client and put it in the queue."""
        cmd = DispatchCommand(
            command_id=uuid4(),
            user_id=user_id,
            payload=payload,
            context=context or {},
            timestamp=datetime.now(timezone.utc),
            ttl_seconds=ttl_seconds,
        )
        self._queue[cmd.command_id] = cmd
        self._new_command_event.set()  # wake up any waiting desktop listeners

        await self._mnemosyne.append(AuditEvent(
            event_type="dispatch",
            event_data={
                "action": "enqueue",
                "command_id": str(cmd.command_id),
                "user_id": user_id,
            },
            source_module="DISPATCH_BRIDGE",
            timestamp=cmd.timestamp,
        ))
        _logger.info("Enqueued command %s from user %s", cmd.command_id, user_id)
        return cmd

    # ------------------------------------------------------------------
    # Mobile-side: poll for result
    # ------------------------------------------------------------------

    def get_result(self, command_id: UUID) -> Optional[DispatchCommand]:
        """Return the command (including result if complete) or None if unknown/expired."""
        cmd = self._queue.get(command_id)
        if cmd is None:
            return None
        if cmd.expired and not cmd.completed:
            self._queue.pop(command_id, None)
            return None
        return cmd

    # ------------------------------------------------------------------
    # Desktop-side: fetch pending commands
    # ------------------------------------------------------------------

    def pending(self) -> List[DispatchCommand]:
        """Return all non-expired, incomplete commands ordered by arrival time."""
        self._evict_expired()
        return [c for c in self._queue.values() if not c.completed]

    async def wait_for_command(self, timeout: float = 30.0) -> List[DispatchCommand]:
        """
        Block (up to ``timeout`` seconds) until at least one pending command exists.

        Used by WebSocket desktop handlers to avoid busy-polling.
        """
        self._new_command_event.clear()
        if not self.pending():
            try:
                await asyncio.wait_for(self._new_command_event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                pass
        return self.pending()

    # ------------------------------------------------------------------
    # Desktop-side: post result
    # ------------------------------------------------------------------

    async def complete(self, command_id: UUID, result: str, user_id: str) -> bool:
        """Mark a command as completed and store the result.  Returns False if not found."""
        cmd = self._queue.get(command_id)
        if cmd is None or cmd.expired:
            return False
        cmd.result = result
        cmd.completed = True

        await self._mnemosyne.append(AuditEvent(
            event_type="dispatch",
            event_data={
                "action": "complete",
                "command_id": str(command_id),
                "user_id": user_id,
            },
            source_module="DISPATCH_BRIDGE",
            timestamp=datetime.now(timezone.utc),
        ))
        _logger.info("Completed command %s by desktop agent %s", command_id, user_id)
        return True

    # ------------------------------------------------------------------
    # Housekeeping
    # ------------------------------------------------------------------

    def _evict_expired(self) -> None:
        expired_ids = [cid for cid, c in self._queue.items() if c.expired and not c.completed]
        for cid in expired_ids:
            self._queue.pop(cid, None)
        if expired_ids:
            _logger.debug("Evicted %d expired commands", len(expired_ids))
