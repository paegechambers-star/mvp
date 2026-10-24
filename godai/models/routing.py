"""RouteDecision model for APOLLON."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List


@dataclass
class RouteDecision:
    """
    Deterministic model-selection result produced by APOLLON.

    Invariant: identical (InternalRequest, PolicyDecision) inputs always
    produce the identical RouteDecision — no randomness, no load balancing.
    """

    model_id: str           # e.g. "claude-sonnet-4-6", "claude-haiku-4-5-20251001"
    reason: str             # Human-readable routing rationale
    alternatives: List[str] # Other candidate models (for audit purposes only)
    timestamp: datetime
    routing_version: str    # Version of the routing config that was applied
