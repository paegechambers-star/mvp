"""AuditEvent and LogEntry models for MNEMOSYNE."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict
from uuid import UUID

# Valid source module identifiers — used for consistency checks in tests.
VALID_SOURCE_MODULES = frozenset({"HERMES", "THEMIS", "APOLLON", "ATHENA", "PIPELINE"})


@dataclass
class AuditEvent:
    """
    An event emitted by any G.O.D.A.I. module to be appended to MNEMOSYNE.

    All routing, policy, and validation decisions MUST produce an AuditEvent
    before their result is returned (EU AI Act Art. 12 compliance).
    """

    event_type: str         # "auth" | "policy_check" | "routing" | "validation"
    event_data: Dict[str, Any]
    source_module: str      # "HERMES" | "THEMIS" | "APOLLON" | "ATHENA" | "PIPELINE"
    timestamp: datetime

    def __post_init__(self) -> None:
        if self.source_module not in VALID_SOURCE_MODULES:
            raise ValueError(
                f"source_module must be one of {VALID_SOURCE_MODULES}, "
                f"got {self.source_module!r}"
            )


@dataclass
class LogEntry:
    """
    Immutable log entry stored in MNEMOSYNE with SHA256 hash chaining.

    The chain forms a tamper-evident audit trail:
      hash = SHA256(json(event_data) + prev_hash)

    Verifying the chain in O(n) detects any modification, deletion, or insertion.
    """

    event_id: UUID
    event_type: str
    event_data: Dict[str, Any]
    timestamp: datetime
    hash: str               # SHA256 hex digest of (event_data_json + prev_hash)
    prev_hash: str          # Hash of the preceding entry (GENESIS_HASH for index 0)
    chain_index: int        # 0-based position in the log
