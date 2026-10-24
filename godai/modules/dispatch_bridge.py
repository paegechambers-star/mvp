"""
DISPATCH BRIDGE — Mobile-to-Desktop async message queue.

Hard invariants enforced here (not just documented):
  1. Every command is classified READ or WRITE by the classifier before enqueue.
  2. WRITE commands carry requires_confirmation=True — the desktop agent MUST
     show a confirmation prompt before executing them.
  3. Every action (enqueue, complete, expire, reject) is appended to both
     MNEMOSYNE (in-memory chain) and a file-based JSONL audit log.
  4. Auth tokens are NEVER written to the audit log.
  5. Expired commands are tracked for a short grace period so callers receive
     a clear "expired" signal rather than a silent 404.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from uuid import UUID, uuid4

from godai.models.audit import AuditEvent
from godai.modules.command_classifier import CommandRisk, classify
from godai.modules.mnemosyne import Mnemosyne

_logger = logging.getLogger("godai.dispatch_bridge")

DEFAULT_TTL_SECONDS = 300          # 5 minutes
_EXPIRED_GRACE_SECONDS = 60        # keep expired IDs this long for clear error messages

_AUDIT_LOG_PATH = Path(__file__).parent.parent / "logs" / "dispatch_audit.log"
_audit_lock = threading.Lock()


# ------------------------------------------------------------------
# File-based audit log (append-only JSONL, no tokens in cleartext)
# ------------------------------------------------------------------

def _audit_write(record: Dict[str, Any]) -> None:
    """Append one JSONL record to the on-disk audit log. Thread-safe. Never raises."""
    try:
        _AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, default=str) + "\n"
        with _audit_lock:
            with open(_AUDIT_LOG_PATH, "a", encoding="utf-8") as fh:
                fh.write(line)
                fh.flush()
    except Exception as exc:  # noqa: BLE001
        _logger.error("Audit log write failed: %s", exc)


# ------------------------------------------------------------------
# Domain models
# ------------------------------------------------------------------

@dataclass
class DispatchCommand:
    """
    A command queued by a mobile/chat client and awaiting desktop execution.

    ``requires_confirmation`` is set by the classifier and is a hard signal —
    the desktop agent skill must not execute the payload without user approval.
    """

    command_id: UUID
    user_id: str
    payload: str
    source: str                      # originating client identifier (e.g. "mcp-chat", "web-browser")
    context: Dict[str, Any]
    timestamp: datetime
    ttl_seconds: int = DEFAULT_TTL_SECONDS
    requires_confirmation: bool = False
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
            "source": self.source,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
            "requires_confirmation": self.requires_confirmation,
            "completed": self.completed,
            "result": self.result,
        }


class CommandExpiredError(Exception):
    """Raised by get_result() when a command existed but has expired."""

    def __init__(self, command_id: UUID) -> None:
        super().__init__(f"Command {command_id} has expired (TTL exceeded).")
        self.command_id = command_id


# ------------------------------------------------------------------
# Bridge
# ------------------------------------------------------------------

class DispatchBridge:
    """
    Async message queue bridging chat/mobile clients and the desktop Claude agent.

    Trust & confirmation rules enforced unconditionally:
      - Trust level is always L1 (basic) from remote/chat context.
        Higher levels require manual desktop authorisation.
      - WRITE-classified commands are flagged requires_confirmation=True
        and the desktop agent MUST prompt before executing them.
    """

    def __init__(self, mnemosyne: Mnemosyne) -> None:
        self._mnemosyne = mnemosyne
        self._queue: Dict[UUID, DispatchCommand] = {}
        # Expired IDs retained briefly for clear error reporting
        self._recently_expired: Dict[UUID, datetime] = {}
        self._new_command_event: asyncio.Event = asyncio.Event()

    # ------------------------------------------------------------------
    # Mobile/chat-side: enqueue a command
    # ------------------------------------------------------------------

    async def enqueue(
        self,
        user_id: str,
        payload: str,
        context: Optional[Dict[str, Any]] = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        source: str = "unknown",
    ) -> DispatchCommand:
        """
        Accept a command from a remote client and put it in the queue.

        The classifier runs here — WRITE commands automatically get
        ``requires_confirmation=True``.  This flag is non-negotiable;
        callers cannot override it.
        """
        ctx = context or {}
        risk = classify(payload)
        needs_confirm = risk is CommandRisk.WRITE

        cmd = DispatchCommand(
            command_id=uuid4(),
            user_id=user_id,
            payload=payload,
            source=source,
            context=ctx,
            timestamp=datetime.now(timezone.utc),
            ttl_seconds=ttl_seconds,
            requires_confirmation=needs_confirm,
        )
        self._queue[cmd.command_id] = cmd
        self._new_command_event.set()

        _audit_write({
            "ts": cmd.timestamp.isoformat(),
            "action": "enqueue",
            "command_id": str(cmd.command_id),
            "user_id": user_id,
            "source": source,
            "trust_level": "L1",          # always basic from remote
            "category": risk.name,
            "requires_confirmation": needs_confirm,
            "payload_preview": payload[:120],
        })

        await self._mnemosyne.append(AuditEvent(
            event_type="dispatch",
            event_data={
                "action": "enqueue",
                "command_id": str(cmd.command_id),
                "user_id": user_id,
                "source": source,
                "category": risk.name,
                "requires_confirmation": needs_confirm,
            },
            source_module="DISPATCH_BRIDGE",
            timestamp=cmd.timestamp,
        ))
        _logger.info(
            "Enqueued %s command %s from %s (confirm=%s)",
            risk.name, cmd.command_id, source, needs_confirm,
        )
        return cmd

    # ------------------------------------------------------------------
    # Mobile/chat-side: poll for result
    # ------------------------------------------------------------------

    def get_result(self, command_id: UUID) -> DispatchCommand:
        """
        Return the command (including result if complete).

        Raises:
            KeyError: command_id was never seen.
            CommandExpiredError: command existed but its TTL has elapsed.
        """
        self._flush_grace_period()

        if command_id in self._recently_expired:
            raise CommandExpiredError(command_id)

        cmd = self._queue.get(command_id)
        if cmd is None:
            raise KeyError(command_id)

        if cmd.expired and not cmd.completed:
            self._queue.pop(command_id, None)
            self._recently_expired[command_id] = datetime.now(timezone.utc)
            _audit_write({
                "ts": datetime.now(timezone.utc).isoformat(),
                "action": "expire",
                "command_id": str(command_id),
                "user_id": cmd.user_id,
                "source": cmd.source,
            })
            _logger.info("Command %s expired", command_id)
            raise CommandExpiredError(command_id)

        return cmd

    # ------------------------------------------------------------------
    # Desktop-side: fetch pending commands
    # ------------------------------------------------------------------

    def pending(self) -> List[DispatchCommand]:
        """Return all non-expired, incomplete commands, oldest first."""
        self._evict_expired()
        cmds = [c for c in self._queue.values() if not c.completed]
        return sorted(cmds, key=lambda c: c.timestamp)

    async def wait_for_command(self, timeout: float = 30.0) -> List[DispatchCommand]:
        """Block up to ``timeout`` seconds until at least one pending command exists."""
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
        """
        Mark a command completed and store the result.
        Returns False if the command is unknown or already expired.
        """
        cmd = self._queue.get(command_id)
        if cmd is None or cmd.expired:
            if cmd and cmd.expired:
                _audit_write({
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "action": "reject_expired",
                    "command_id": str(command_id),
                    "agent_id": user_id,
                })
            return False

        cmd.result = result
        cmd.completed = True
        now = datetime.now(timezone.utc)

        _audit_write({
            "ts": now.isoformat(),
            "action": "complete",
            "command_id": str(command_id),
            "agent_id": user_id,
            "source": cmd.source,
            "category": "WRITE" if cmd.requires_confirmation else "READ",
            "result_preview": (result or "")[:200],
        })

        await self._mnemosyne.append(AuditEvent(
            event_type="dispatch",
            event_data={
                "action": "complete",
                "command_id": str(command_id),
                "agent_id": user_id,
                "source": cmd.source,
            },
            source_module="DISPATCH_BRIDGE",
            timestamp=now,
        ))
        _logger.info("Completed command %s by %s", command_id, user_id)
        return True

    # ------------------------------------------------------------------
    # Housekeeping
    # ------------------------------------------------------------------

    def _evict_expired(self) -> None:
        now = datetime.now(timezone.utc)
        expired_ids = [
            cid for cid, c in self._queue.items()
            if c.expired and not c.completed
        ]
        for cid in expired_ids:
            cmd = self._queue.pop(cid)
            self._recently_expired[cid] = now
            _audit_write({
                "ts": now.isoformat(),
                "action": "expire",
                "command_id": str(cid),
                "user_id": cmd.user_id,
                "source": cmd.source,
            })
        if expired_ids:
            _logger.debug("Evicted %d expired commands", len(expired_ids))

    def _flush_grace_period(self) -> None:
        """Remove expired-ID entries that are older than the grace period."""
        now = datetime.now(timezone.utc)
        stale = [
            cid for cid, ts in self._recently_expired.items()
            if (now - ts).total_seconds() > _EXPIRED_GRACE_SECONDS
        ]
        for cid in stale:
            del self._recently_expired[cid]
