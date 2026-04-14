"""
G.O.D.A.I. Pipeline — Full Request Lifecycle Orchestration.

Wires together all five modules in the exact order specified:

  User Request
    → HERMES.normalize()           # Protocol + Auth
    → MNEMOSYNE.append(auth)       # (handled inside HERMES)
    → THEMIS.evaluate()            # Policy check
    → MNEMOSYNE.append(policy)     # (handled inside THEMIS)
    → if denied: return 403 result
    → APOLLON.route()              # Model selection
    → MNEMOSYNE.append(routing)    # (handled inside APOLLON)
    → LLM.generate()               # Actual model call (injected provider)
    → ATHENA.validate()            # Cross-validation
    → MNEMOSYNE.append(validation) # (handled inside ATHENA)
    → if invalid: return error result
    → Return validated output

Three Invariants enforced here:
  1. Generator ≠ Arbiter: LLM generates; pipeline decides.
  2. Policy = Data: only THEMIS evaluates policy; pipeline never hardcodes rules.
  3. All Decisions Logged: every module logs to MNEMOSYNE before returning.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from godai.models.policy import PolicyDecision
from godai.models.request import InternalRequest
from godai.models.routing import RouteDecision
from godai.models.validation import ValidationResult
from godai.modules.apollon import Apollon
from godai.modules.athena import Athena, LLMProvider
from godai.modules.hermes import AuthenticationError, Hermes, RateLimitError
from godai.modules.mnemosyne import Mnemosyne
from godai.modules.themis import Themis

_logger = logging.getLogger("godai.pipeline")

# Default config paths (relative to this file's location)
_DEFAULT_POLICY_PATH = Path(__file__).parent / "config" / "policies" / "default.yaml"
_DEFAULT_ROUTING_PATH = Path(__file__).parent / "config" / "routing" / "rules.yaml"


# ------------------------------------------------------------------
# Result model
# ------------------------------------------------------------------


@dataclass
class PipelineResult:
    """
    Full result of one request traversal through the G.O.D.A.I. pipeline.

    Includes the original request, every intermediate decision, and the
    final output (or error).  All fields are populated regardless of
    whether the request succeeded or was denied/failed — this enables
    complete audit reconstruction from the pipeline result alone.
    """

    success: bool
    output: Optional[str]               # None when denied or validation failed
    error: Optional[str]                # Human-readable error / denial reason
    request: Optional[InternalRequest]  # None only if HERMES raised an exception
    policy_decision: Optional[PolicyDecision]
    route_decision: Optional[RouteDecision]
    validation_result: Optional[ValidationResult]
    timestamp: datetime


# ------------------------------------------------------------------
# Pipeline class
# ------------------------------------------------------------------


class GodaiPipeline:
    """
    G.O.D.A.I. Pipeline — orchestrates the full request lifecycle.

    All five modules are constructed by the pipeline with shared
    MNEMOSYNE instance, ensuring every decision is audit-logged.

    Usage::

        pipeline = GodaiPipeline.create(llm_provider=my_provider)
        result = await pipeline.process(
            token="elevated-mytoken",
            user_id="user-123",
            protocol="http",
            query="Summarise this document",
            context={"data_class": "INTERNAL"},
        )
        if result.success:
            print(result.output)
        else:
            print(f"Denied: {result.error}")
    """

    def __init__(
        self,
        mnemosyne: Mnemosyne,
        hermes: Hermes,
        themis: Themis,
        apollon: Apollon,
        athena: Athena,
    ) -> None:
        self._mnemosyne = mnemosyne
        self._hermes = hermes
        self._themis = themis
        self._apollon = apollon
        self._athena = athena

    @classmethod
    def create(
        cls,
        llm_provider: LLMProvider,
        policy_path: str | Path = _DEFAULT_POLICY_PATH,
        routing_path: str | Path = _DEFAULT_ROUTING_PATH,
        rate_limit: int = 100,
        validation_strategy: str = "consistency_check",
        confidence_threshold: float = 0.7,
    ) -> "GodaiPipeline":
        """
        Convenience factory that wires all five modules with a shared MNEMOSYNE.

        Args:
            llm_provider: LLM backend for both generation and validation.
            policy_path: Path to the THEMIS YAML policy file.
            routing_path: Path to the APOLLON YAML routing config.
            rate_limit: Per-user request rate limit enforced by HERMES.
            validation_strategy: ATHENA validation strategy.
            confidence_threshold: ATHENA minimum confidence threshold.

        Returns:
            Fully wired :class:`GodaiPipeline` instance.
        """
        mnemosyne = Mnemosyne()
        hermes = Hermes(mnemosyne, rate_limit=rate_limit)
        themis = Themis(mnemosyne, policy_path=policy_path)
        apollon = Apollon(mnemosyne, routing_path=routing_path)
        athena = Athena(
            mnemosyne,
            llm_provider=llm_provider,
            strategy=validation_strategy,
            confidence_threshold=confidence_threshold,
        )
        return cls(mnemosyne, hermes, themis, apollon, athena)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def process(
        self,
        token: Optional[str],
        user_id: str,
        protocol: str,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> PipelineResult:
        """
        Process one request through the complete G.O.D.A.I. lifecycle.

        Authentication failures and rate-limit errors are caught and
        returned as unsuccessful PipelineResults (rather than propagating
        exceptions) so callers can translate them to HTTP 401/429.

        Args:
            token: Bearer token for authentication (passed to HERMES).
            user_id: Caller user identifier.
            protocol: Wire protocol — ``"http"``, ``"websocket"``, ``"grpc"``.
            query: Request payload / prompt.
            context: Optional metadata (``data_class``, ``action``, …).

        Returns:
            :class:`PipelineResult` — always returned; never raises.
        """
        now = datetime.now(timezone.utc)

        # ── Step 1: HERMES — normalize + authenticate ─────────────────
        try:
            request = await self._hermes.normalize(
                token=token,
                user_id=user_id,
                protocol=protocol,
                query=query,
                context=context,
            )
        except AuthenticationError as exc:
            _logger.warning("Pipeline: auth rejected for %s: %s", user_id, exc)
            return PipelineResult(
                success=False,
                output=None,
                error=str(exc),
                request=None,
                policy_decision=None,
                route_decision=None,
                validation_result=None,
                timestamp=now,
            )
        except RateLimitError as exc:
            _logger.warning("Pipeline: rate limit for %s: %s", user_id, exc)
            return PipelineResult(
                success=False,
                output=None,
                error=str(exc),
                request=None,
                policy_decision=None,
                route_decision=None,
                validation_result=None,
                timestamp=now,
            )

        # ── Step 2: THEMIS — policy evaluation ────────────────────────
        policy_decision = await self._themis.evaluate(request)

        # ── Step 3: Enforce THEMIS denial (Invariant 1) ───────────────
        if not policy_decision.allowed:
            _logger.info(
                "Pipeline: request %s denied by THEMIS: %s",
                request.request_id,
                policy_decision.reason,
            )
            return PipelineResult(
                success=False,
                output=None,
                error=f"Policy denied: {policy_decision.reason}",
                request=request,
                policy_decision=policy_decision,
                route_decision=None,
                validation_result=None,
                timestamp=now,
            )

        # ── Step 4: APOLLON — deterministic routing ───────────────────
        route_decision = await self._apollon.route(request, policy_decision)

        # ── Step 5: LLM generation ────────────────────────────────────
        # The pipeline delegates to the injected provider.
        # Invariant 1: the provider generates; the pipeline decides what to do.
        try:
            generator_output = await self._athena._provider.generate(
                model_id=route_decision.model_id,
                prompt=request.query,
                context=request.context,
            )
        except Exception as exc:
            _logger.error(
                "Pipeline: LLM generation failed for request %s: %s",
                request.request_id,
                exc,
            )
            return PipelineResult(
                success=False,
                output=None,
                error=f"Generation failed: {exc}",
                request=request,
                policy_decision=policy_decision,
                route_decision=route_decision,
                validation_result=None,
                timestamp=now,
            )

        # ── Step 6: ATHENA — cross-validation ────────────────────────
        validation_result = await self._athena.validate(
            generator_output=generator_output,
            request=request,
            generator_model=route_decision.model_id,
        )

        # ── Step 7: Enforce validation result ────────────────────────
        if not validation_result.passed:
            _logger.info(
                "Pipeline: validation FAILED for request %s: %s",
                request.request_id,
                validation_result.issues_found,
            )
            return PipelineResult(
                success=False,
                output=None,
                error=f"Validation failed: {'; '.join(validation_result.issues_found)}",
                request=request,
                policy_decision=policy_decision,
                route_decision=route_decision,
                validation_result=validation_result,
                timestamp=now,
            )

        _logger.info(
            "Pipeline: request %s completed successfully → model=%s",
            request.request_id,
            route_decision.model_id,
        )
        return PipelineResult(
            success=True,
            output=generator_output,
            error=None,
            request=request,
            policy_decision=policy_decision,
            route_decision=route_decision,
            validation_result=validation_result,
            timestamp=now,
        )

    @property
    def mnemosyne(self) -> Mnemosyne:
        """Access the shared MNEMOSYNE audit log."""
        return self._mnemosyne
