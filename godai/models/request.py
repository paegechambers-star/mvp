"""InternalRequest model with TrustLevel and DataClass enumerations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum, Enum
from typing import Any, Dict
from uuid import UUID


class TrustLevel(IntEnum):
    """
    Trust level assigned to an authenticated request.

    Uses integer values so that comparisons like ``trust_level >= TrustLevel.L2``
    work naturally in policy evaluation expressions.
    """

    L0 = 0  # Unauthenticated / anonymous (should be blocked at HERMES)
    L1 = 1  # Basic authenticated user
    L2 = 2  # Verified / elevated trust (e.g. 2FA, signed token)
    L3 = 3  # Internal service / admin


class DataClass(str, Enum):
    """Data classification for request content, following a 4-tier model."""

    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    SENSITIVE = "SENSITIVE"
    RESTRICTED = "RESTRICTED"


@dataclass
class InternalRequest:
    """
    Canonical internal request produced by HERMES after protocol normalization.

    All downstream modules (THEMIS, APOLLON, ATHENA) consume this object.
    Never constructed outside of HERMES — callers use raw protocol inputs.
    """

    request_id: UUID
    user_id: str
    trust_level: TrustLevel
    protocol: str           # "http" | "websocket" | "grpc"
    query: str
    data_class: DataClass
    context: Dict[str, Any]
    timestamp: datetime
    authenticated: bool

    def __post_init__(self) -> None:
        if not self.user_id:
            raise ValueError("user_id must not be empty")
        if self.protocol not in {"http", "websocket", "grpc"}:
            raise ValueError(f"Unsupported protocol: {self.protocol!r}")
