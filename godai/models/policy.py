"""PolicyDecision and PolicyRule models for THEMIS."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List


@dataclass
class PolicyRule:
    """
    A single parsed policy rule loaded from a YAML/JSON policy file.

    Rules are never hardcoded in Python — they are data, not code.
    """

    id: str
    condition: str      # Expression: when this rule applies (e.g. "data_class == SENSITIVE")
    requirement: str    # Expression: what must be true to allow (e.g. "trust_level >= L2")
    action: str         # "deny" | "allow"
    message: str        # Human-readable explanation logged on match


@dataclass
class PolicyDecision:
    """
    Result of THEMIS policy evaluation.

    **Binding**: no downstream module may override a denial.
    Every PolicyDecision is logged to MNEMOSYNE before being returned.
    """

    allowed: bool
    reason: str
    policy_version: str
    rules_evaluated: List[str]
    timestamp: datetime
