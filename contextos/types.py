"""
ContextOS™ core type definitions.

All dataclasses, enums, and type aliases used across the module.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


# ─────────────────────────────── Base36 ──────────────────────────────────────

BASE36: str = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# ─────────────────────────────── Enums ───────────────────────────────────────


class Kind(str, Enum):
    """First 2 chars of a ContextOS ID — the top-level knowledge classification."""
    NK = "NK"   # Node Knowledge — primary knowledge unit (canonical truth)
    MK = "MK"   # Meta Knowledge — annotations, queries, procedures


class Actor(str, Enum):
    """
    2-char base36 actor code — who wrote the entry.
    Values are direct base36 pairs embedded in the ID.
    """
    SYSTEM   = "00"
    USER     = "01"
    ADMIN    = "02"
    AI       = "03"
    EXTERNAL = "04"
    PIPELINE = "05"


class Cluster(str, Enum):
    """
    2-char base36 cluster code — logical domain grouping.
    """
    GENERAL    = "00"
    RESEARCH   = "01"
    COMPLIANCE = "02"
    OPERATIONS = "03"
    LEGAL      = "04"
    TECHNICAL  = "05"
    GOVERNANCE = "06"
    FINANCE    = "07"


class EntryType(str, Enum):
    """
    2-char base36 entry-type code — semantic kind of the payload.
    """
    FACT        = "00"
    CLAIM       = "01"
    DECISION    = "02"
    PROCEDURE   = "03"
    REFERENCE   = "04"
    ANNOTATION  = "05"
    QUESTION    = "06"
    ANSWER      = "07"


class TruthGate(str, Enum):
    """
    2-char base36 truth-gate code — epistemic status of the assertion.

    Invariant: TruthGate > EMPTY_BUT_VERIFIED requires ≥1 Citation.
    """
    UNVERIFIED         = "00"
    EMPTY_BUT_VERIFIED = "01"   # explicitly verified to be empty / N/A
    SINGLE_SOURCE      = "02"
    CORROBORATED       = "03"
    AUTHORITATIVE      = "04"


class CommitOp(str, Enum):
    """Operation recorded in a CommitBlock."""
    PATCH      = "PATCH"        # partial update to a WORK entry
    SUPERSEDE  = "SUPERSEDE"    # new SSOT replaces old SSOT
    PROMOTE    = "PROMOTE"      # WORK → SSOT
    DEPRECATE  = "DEPRECATE"    # mark SSOT entry as no longer active


# ─────────────────────────────── Value objects ───────────────────────────────


@dataclass(frozen=True)
class ContextID:
    """Parsed representation of a 16-char ContextOS ID."""
    raw:        str
    kind:       Kind
    actor:      Actor
    cluster:    Cluster
    entry_type: EntryType
    truth_gate: TruthGate
    time_bucket: int    # decoded base36 integer (0–1295)
    sequence:   int     # decoded base36 integer (0–1295)
    checksum:   str     # 2-char base36 checksum

    def __str__(self) -> str:
        return self.raw


@dataclass(frozen=True)
class Citation:
    """A directed reference from one entry to another."""
    source_id: str          # 16-char NKID/MKID of the cited entry
    relation:  str          # "supports" | "contradicts" | "extends" | "derived_from"
    note:      str = ""


# ─────────────────────────────── Storage entries ─────────────────────────────


@dataclass(frozen=True)
class SSOTEntry:
    """
    Immutable Single Source of Truth entry (SSOT partition).

    Once written, never updated — only superseded by a new SSOTEntry.
    """
    nkid:         str               # 16-char ID, Kind.NK
    content:      str               # the knowledge payload
    truth_gate:   TruthGate
    citations:    tuple             # tuple[Citation, ...]  (immutable)
    content_hash: str               # SHA256 hex of content
    created_at:   datetime
    cluster:      Cluster
    actor:        Actor
    superseded_by: Optional[str] = None   # NKID of the replacement, if any


@dataclass
class WorkEntry:
    """
    Mutable draft entry (WORK partition).

    Can be patched repeatedly, then promoted to SSOT via CommitOp.PROMOTE.
    """
    mkid:          str
    content:       str
    truth_gate:    TruthGate
    citations:     List[Citation]
    content_hash:  str
    created_at:    datetime
    modified_at:   datetime
    cluster:       Cluster
    actor:         Actor
    promoted:      bool = False
    promoted_nkid: Optional[str] = None  # set after PROMOTE


# ─────────────────────────────── CommitBlock ─────────────────────────────────


@dataclass(frozen=True)
class CommitBlock:
    """
    Immutable record of a single state-transition event.

    delta is stored as a JSON string to keep CommitBlock hashable.
    Use .delta_dict for dict access.
    """
    commit_id:        str          # UUID hex
    operation:        CommitOp
    target_id:        str          # NKID or MKID
    actor:            Actor
    timestamp:        datetime
    prev_content_hash: Optional[str]
    new_content_hash: str
    _delta_json:      str = field(default="{}", repr=False)

    @property
    def delta_dict(self) -> Dict[str, Any]:
        return json.loads(self._delta_json)

    @classmethod
    def make(
        cls,
        commit_id: str,
        operation: CommitOp,
        target_id: str,
        actor: Actor,
        timestamp: datetime,
        prev_content_hash: Optional[str],
        new_content_hash: str,
        delta: Dict[str, Any],
    ) -> "CommitBlock":
        return cls(
            commit_id=commit_id,
            operation=operation,
            target_id=target_id,
            actor=actor,
            timestamp=timestamp,
            prev_content_hash=prev_content_hash,
            new_content_hash=new_content_hash,
            _delta_json=json.dumps(delta, sort_keys=True, default=str),
        )
