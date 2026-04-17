"""
ContextOS™ CommitBlock factory.

Every state-transition in the Register is represented by a CommitBlock.
CommitBlocks are frozen (immutable) after creation — they are the unit of
change that flows into the ContextOS internal log.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from contextos.types import Actor, CommitBlock, CommitOp


def make_commit(
    operation: CommitOp,
    target_id: str,
    actor: Actor,
    new_content_hash: str,
    prev_content_hash: Optional[str] = None,
    delta: Optional[Dict[str, Any]] = None,
    *,
    timestamp: Optional[datetime] = None,
    commit_id: Optional[str] = None,
) -> CommitBlock:
    """
    Create an immutable CommitBlock for a register state-transition.

    Args:
        operation:         One of PATCH, SUPERSEDE, PROMOTE, DEPRECATE.
        target_id:         The NKID or MKID being modified.
        actor:             Who is making this change.
        new_content_hash:  SHA256 of the new content.
        prev_content_hash: SHA256 of the previous content (None for new entries).
        delta:             Dict of changed fields for audit trail.
        timestamp:         Override the commit timestamp (defaults to UTC now).
        commit_id:         Override the UUID (defaults to a new uuid4 hex).
    """
    return CommitBlock.make(
        commit_id=commit_id or uuid4().hex,
        operation=operation,
        target_id=target_id,
        actor=actor,
        timestamp=timestamp or datetime.now(timezone.utc),
        prev_content_hash=prev_content_hash,
        new_content_hash=new_content_hash,
        delta=delta or {},
    )


def patch_commit(
    target_id: str,
    actor: Actor,
    prev_hash: str,
    new_hash: str,
    changed_fields: Optional[Dict[str, Any]] = None,
) -> CommitBlock:
    """Convenience factory for a PATCH operation on a WORK entry."""
    return make_commit(
        operation=CommitOp.PATCH,
        target_id=target_id,
        actor=actor,
        new_content_hash=new_hash,
        prev_content_hash=prev_hash,
        delta={"changed_fields": changed_fields or []},
    )


def supersede_commit(
    old_nkid: str,
    new_nkid: str,
    actor: Actor,
    old_hash: str,
    new_hash: str,
) -> CommitBlock:
    """Convenience factory for a SUPERSEDE operation (new SSOT replaces old)."""
    return make_commit(
        operation=CommitOp.SUPERSEDE,
        target_id=new_nkid,
        actor=actor,
        new_content_hash=new_hash,
        prev_content_hash=old_hash,
        delta={"supersedes": old_nkid},
    )


def promote_commit(
    mkid: str,
    nkid: str,
    actor: Actor,
    content_hash: str,
) -> CommitBlock:
    """Convenience factory for a PROMOTE operation (WORK → SSOT)."""
    return make_commit(
        operation=CommitOp.PROMOTE,
        target_id=nkid,
        actor=actor,
        new_content_hash=content_hash,
        delta={"promoted_from": mkid},
    )


def deprecate_commit(
    nkid: str,
    actor: Actor,
    content_hash: str,
    reason: str = "",
) -> CommitBlock:
    """Convenience factory for a DEPRECATE operation."""
    return make_commit(
        operation=CommitOp.DEPRECATE,
        target_id=nkid,
        actor=actor,
        new_content_hash=content_hash,
        delta={"reason": reason},
    )
