"""ValidationResult model for ATHENA."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List


@dataclass
class ValidationResult:
    """
    Cross-validation result produced by ATHENA.

    The validator model MUST differ from the generator model — enforced in
    ATHENA before any validation call is made.
    """

    passed: bool
    confidence: float       # 0.0 – 1.0; below threshold → treat as failed
    strategy_used: str      # "consistency_check" | "fact_verification" | "policy_compliance"
    issues_found: List[str] # Populated when passed=False
    validator_model: str    # The model that performed validation (≠ generator)
    timestamp: datetime

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0.0, 1.0], got {self.confidence}")
