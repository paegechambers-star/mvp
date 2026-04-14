"""
APOLLON — Deterministic Model Router.

Selects the target LLM for a request based solely on the InternalRequest
and PolicyDecision.  Routing is a pure function: identical inputs always
produce identical outputs — no randomness, no load balancing, no state.

Invariants:
  - Routing rules live in YAML, never in Python code.
  - Every routing decision is logged to MNEMOSYNE.
  - A default fallback rule must exist in the routing config.

Target latency: ~10 ms.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from godai._condition_eval import build_eval_context, evaluate_condition
from godai.models.audit import AuditEvent
from godai.models.policy import PolicyDecision
from godai.models.request import InternalRequest
from godai.models.routing import RouteDecision
from godai.modules.mnemosyne import Mnemosyne

_logger = logging.getLogger("godai.apollon")


class RoutingConfigError(Exception):
    """Raised when the routing config file cannot be loaded, parsed, or is missing a default."""


class Apollon:
    """
    APOLLON — Deterministic Router.

    Routing config YAML format::

        version: "1.0"
        routes:
          - condition: "data_class == SENSITIVE and trust_level >= L2"
            model: "claude-sonnet-4-6"
            reason: "Sensitive data → trusted Anthropic model"
          - condition: "data_class == PUBLIC"
            model: "claude-haiku-4-5-20251001"
            reason: "Public data → efficient model"
          - default:
            model: "claude-sonnet-4-6"
            reason: "Default fallback"

    Rules are evaluated top-to-bottom.  The first matching condition wins.
    The ``default`` entry (no ``condition`` key) acts as the guaranteed
    catch-all.  Configs without a default raise :class:`RoutingConfigError`.
    """

    def __init__(self, mnemosyne: Mnemosyne, routing_path: str | Path) -> None:
        """
        Args:
            mnemosyne: Shared MNEMOSYNE instance for audit logging.
            routing_path: Path to the YAML routing config file.

        Raises:
            RoutingConfigError: If the config cannot be loaded or has no default rule.
        """
        self._mnemosyne = mnemosyne
        self._routing_path = Path(routing_path)
        self._routing_version: str = "unknown"
        self._routes: List[Dict[str, Any]] = []
        self._default_model: str = ""
        self._default_reason: str = ""
        self._load_routing_config()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_routing_config(self) -> None:
        """Read and parse the YAML routing config file."""
        try:
            raw = self._routing_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RoutingConfigError(
                f"Cannot read routing config {self._routing_path}: {exc}"
            ) from exc

        try:
            data: Dict[str, Any] = yaml.safe_load(raw) or {}
        except yaml.YAMLError as exc:
            raise RoutingConfigError(
                f"Invalid YAML in routing config {self._routing_path}: {exc}"
            ) from exc

        self._routing_version = str(data.get("version", "unknown"))
        raw_routes: List[Dict[str, Any]] = data.get("routes", [])

        # Separate conditional routes from the default
        self._routes = []
        self._default_model = ""
        self._default_reason = ""

        for route in raw_routes:
            if "default" in route:
                self._default_model = str(route["default"].get("model", ""))
                self._default_reason = str(route["default"].get("reason", "Default route"))
            elif "condition" in route:
                self._routes.append(route)

        if not self._default_model:
            raise RoutingConfigError(
                f"Routing config {self._routing_path} must contain a 'default' rule."
            )

        _logger.info(
            "APOLLON loaded %d conditional routes + default=%r (version=%s)",
            len(self._routes),
            self._default_model,
            self._routing_version,
        )

    def _build_context(self, request: InternalRequest) -> Dict[str, Any]:
        """Build evaluation context from InternalRequest."""
        return build_eval_context(
            data_class_value=request.data_class.value,
            trust_level_value=int(request.trust_level.value),
            action=request.context.get("action", ""),
            explicit_consent=bool(request.context.get("explicit_consent", False)),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def route(
        self,
        request: InternalRequest,
        policy_decision: PolicyDecision,
    ) -> RouteDecision:
        """
        Deterministically select the target model for the request.

        Evaluates conditional routes top-to-bottom; falls back to the
        default if no condition matches.  Identical inputs always return
        an identical RouteDecision.

        Args:
            request: The normalized InternalRequest from HERMES.
            policy_decision: The PolicyDecision from THEMIS (must be allowed).

        Returns:
            :class:`~godai.models.routing.RouteDecision` with selected model.

        Raises:
            ValueError: If the policy_decision is a denial (routing should
                not be called on denied requests).
        """
        if not policy_decision.allowed:
            raise ValueError(
                "APOLLON.route() called on a denied PolicyDecision — "
                "check pipeline ordering."
            )

        ctx = self._build_context(request)

        selected_model: Optional[str] = None
        selected_reason: Optional[str] = None
        alternatives: List[str] = []

        for route in self._routes:
            condition = str(route.get("condition", ""))
            model = str(route.get("model", ""))
            reason = str(route.get("reason", ""))

            try:
                matched = evaluate_condition(condition, ctx)
            except ValueError:
                _logger.warning("APOLLON skipping unresolvable condition: %r", condition)
                continue

            if matched:
                if selected_model is None:
                    selected_model = model
                    selected_reason = reason
                else:
                    alternatives.append(model)
            elif model:
                alternatives.append(model)

        if selected_model is None:
            selected_model = self._default_model
            selected_reason = self._default_reason

        decision = RouteDecision(
            model_id=selected_model,
            reason=selected_reason or "",
            alternatives=alternatives,
            timestamp=datetime.now(timezone.utc),
            policy_version=self._routing_version,
        )

        await self._mnemosyne.append(AuditEvent(
            event_type="routing",
            event_data={
                "request_id": str(request.request_id),
                "user_id": request.user_id,
                "model_id": selected_model,
                "reason": selected_reason,
                "alternatives": alternatives,
                "routing_version": self._routing_version,
            },
            source_module="APOLLON",
            timestamp=decision.timestamp,
        ))

        _logger.info(
            "APOLLON routed request %s → %s (%s)",
            request.request_id,
            selected_model,
            selected_reason,
        )
        return decision

    def reload_config(self) -> None:
        """Hot-reload routing config from disk."""
        self._load_routing_config()

    @property
    def routing_version(self) -> str:
        """Currently loaded routing config version string."""
        return self._routing_version
