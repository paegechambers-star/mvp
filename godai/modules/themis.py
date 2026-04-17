"""
THEMIS — Policy Engine.

Evaluates every InternalRequest against binding YAML/JSON policy rules.
A THEMIS denial is final — no downstream module may override it.

Invariants:
  - Policy rules live in YAML files, never in Python code.
  - Every decision (allow or deny) is logged to MNEMOSYNE.
  - ``policy_version`` is tracked in every PolicyDecision.

Target latency: ~20 ms for 50 rules.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from godai._condition_eval import build_eval_context, evaluate_condition
from godai.models.audit import AuditEvent
from godai.models.policy import PolicyDecision, PolicyRule
from godai.models.request import InternalRequest
from godai.modules.mnemosyne import Mnemosyne

_logger = logging.getLogger("godai.themis")


class PolicyLoadError(Exception):
    """Raised when a policy file cannot be loaded or parsed."""


class PolicyEvaluationError(Exception):
    """Raised when a policy condition expression cannot be evaluated."""


class Themis:
    """
    THEMIS — Policy Engine.

    Loads policy rules from a YAML file on construction.
    Call :meth:`reload_policy` for hot-reload without restarting.

    Example policy YAML::

        version: "1.0"
        rules:
          - id: "PII_REQUIRES_L2"
            condition: "data_class == SENSITIVE"
            requirement: "trust_level >= L2"
            action: "deny"
            message: "Sensitive data requires L2+ trust level"
    """

    def __init__(self, mnemosyne: Mnemosyne, policy_path: str | Path) -> None:
        """
        Args:
            mnemosyne: Shared MNEMOSYNE instance for audit logging.
            policy_path: Path to the YAML policy file.

        Raises:
            PolicyLoadError: If the file cannot be read or parsed.
        """
        self._mnemosyne = mnemosyne
        self._policy_path = Path(policy_path)
        self._policy_version: str = "unknown"
        self._rules: List[PolicyRule] = []
        self._load_policy()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_policy(self) -> None:
        """Read and parse the YAML policy file into PolicyRule objects."""
        try:
            raw = self._policy_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise PolicyLoadError(
                f"Cannot read policy file {self._policy_path}: {exc}"
            ) from exc

        try:
            data: Dict[str, Any] = yaml.safe_load(raw) or {}
        except yaml.YAMLError as exc:
            raise PolicyLoadError(
                f"Invalid YAML in policy file {self._policy_path}: {exc}"
            ) from exc

        self._policy_version = str(data.get("version", "unknown"))
        raw_rules: List[Dict[str, Any]] = data.get("rules", [])
        self._rules = [
            PolicyRule(
                id=str(r["id"]),
                condition=str(r["condition"]),
                requirement=str(r.get("requirement", "")),
                action=str(r.get("action", "deny")),
                message=str(r.get("message", "")),
            )
            for r in raw_rules
        ]
        _logger.info(
            "THEMIS loaded %d rules (policy_version=%s) from %s",
            len(self._rules),
            self._policy_version,
            self._policy_path,
        )

    def _build_context(self, request: InternalRequest) -> Dict[str, Any]:
        """Build the evaluation context from an InternalRequest."""
        return build_eval_context(
            data_class_value=request.data_class.value,
            trust_level_value=int(request.trust_level.value),
            action=request.context.get("action", ""),
            explicit_consent=bool(request.context.get("explicit_consent", False)),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reload_policy(self) -> None:
        """
        Hot-reload policy rules from disk.

        Use this to apply policy changes without restarting the process.
        Thread-safe for reads (Python GIL); concurrent requests during
        reload may observe the old or new policy — use a lock if strict
        atomicity is required.
        """
        self._load_policy()

    async def evaluate(self, request: InternalRequest) -> PolicyDecision:
        """
        Evaluate the request against all loaded policy rules.

        Rules are evaluated in declaration order.  The first rule whose
        ``condition`` matches AND whose ``requirement`` is NOT met causes
        an immediate denial.  If all rules pass, the request is allowed.

        The result (allow or deny) is always logged to MNEMOSYNE before
        being returned.

        Args:
            request: The normalized InternalRequest from HERMES.

        Returns:
            :class:`~godai.models.policy.PolicyDecision` — binding, no override.
        """
        ctx = self._build_context(request)
        rules_evaluated: List[str] = []

        for rule in self._rules:
            # Evaluate whether this rule applies to the current request
            try:
                condition_met = evaluate_condition(rule.condition, ctx)
            except ValueError as exc:
                raise PolicyEvaluationError(
                    f"Rule {rule.id!r} condition error: {exc}"
                ) from exc

            rules_evaluated.append(rule.id)

            if not condition_met:
                # Rule does not apply — continue
                continue

            # Rule applies: check whether the requirement is satisfied
            if rule.requirement:
                try:
                    requirement_met = evaluate_condition(rule.requirement, ctx)
                except ValueError as exc:
                    raise PolicyEvaluationError(
                        f"Rule {rule.id!r} requirement error: {exc}"
                    ) from exc
            else:
                requirement_met = True

            if not requirement_met and rule.action == "deny":
                decision = PolicyDecision(
                    allowed=False,
                    reason=rule.message,
                    policy_version=self._policy_version,
                    rules_evaluated=rules_evaluated,
                    timestamp=datetime.now(timezone.utc),
                )
                await self._mnemosyne.append(AuditEvent(
                    event_type="policy_check",
                    event_data={
                        "request_id": str(request.request_id),
                        "user_id": request.user_id,
                        "allowed": False,
                        "rule_id": rule.id,
                        "reason": rule.message,
                        "policy_version": self._policy_version,
                        "rules_evaluated": rules_evaluated,
                    },
                    source_module="THEMIS",
                    timestamp=decision.timestamp,
                ))
                _logger.info(
                    "THEMIS DENIED request %s — rule %s: %s",
                    request.request_id,
                    rule.id,
                    rule.message,
                )
                return decision

        # All rules passed
        decision = PolicyDecision(
            allowed=True,
            reason="All policy rules passed",
            policy_version=self._policy_version,
            rules_evaluated=rules_evaluated,
            timestamp=datetime.now(timezone.utc),
        )
        await self._mnemosyne.append(AuditEvent(
            event_type="policy_check",
            event_data={
                "request_id": str(request.request_id),
                "user_id": request.user_id,
                "allowed": True,
                "reason": "All policy rules passed",
                "policy_version": self._policy_version,
                "rules_evaluated": rules_evaluated,
            },
            source_module="THEMIS",
            timestamp=decision.timestamp,
        ))
        _logger.info("THEMIS ALLOWED request %s", request.request_id)
        return decision

    @property
    def policy_version(self) -> str:
        """Currently loaded policy version string."""
        return self._policy_version

    @property
    def rules(self) -> List[PolicyRule]:
        """Read-only copy of the loaded policy rules."""
        return list(self._rules)
