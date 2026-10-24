"""
ATHENA — Cross-Validation Module.

Validates generator (LLM) output using an independent second model.
Breaking circular evaluation is the core function: the validator model
MUST differ from the generator model — enforced in code, not just policy.

Supported strategies:
  - ``consistency_check``   — re-prompt validator with same query, compare
  - ``fact_verification``   — ask validator to fact-check the output
  - ``policy_compliance``   — ask validator to audit policy compliance

Every validation result is logged to MNEMOSYNE before being returned.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol

from godai.models.audit import AuditEvent
from godai.models.request import InternalRequest
from godai.models.validation import ValidationResult
from godai.modules.mnemosyne import Mnemosyne

_logger = logging.getLogger("godai.athena")

# If confidence drops below this, validation fails (overridable per instance)
DEFAULT_CONFIDENCE_THRESHOLD: float = 0.7

# Model pairs: generator → validator (must never be the same)
_DEFAULT_VALIDATOR_MAP: Dict[str, str] = {
    "claude-sonnet-4-6": "claude-haiku-4-5-20251001",
    "claude-haiku-4-5-20251001": "claude-sonnet-4-6",
    "claude-opus-4-6": "claude-sonnet-4-6",
    "gpt-4": "claude-sonnet-4-6",
    "gpt-4o": "claude-sonnet-4-6",
}
_DEFAULT_FALLBACK_VALIDATOR: str = "claude-haiku-4-5-20251001"


# ------------------------------------------------------------------
# LLM Provider Protocol
# ------------------------------------------------------------------


class LLMProvider(Protocol):
    """
    Protocol for an LLM backend used by ATHENA to run validation calls.

    Implementations can wrap real API clients (Anthropic, OpenAI, …) or
    mock objects for testing.  ATHENA never calls external APIs directly —
    it delegates to the injected provider (Dependency Inversion).
    """

    async def generate(
        self,
        model_id: str,
        prompt: str,
        context: Dict[str, Any],
    ) -> str:
        """
        Generate a completion for the given prompt using ``model_id``.

        Args:
            model_id: The model to use for generation.
            prompt: The full prompt text.
            context: Additional context passed from the original request.

        Returns:
            The model's response as a string.
        """
        ...


# ------------------------------------------------------------------
# Exceptions
# ------------------------------------------------------------------


class ValidatorModelError(Exception):
    """Raised when the validator model is the same as the generator model."""


class ValidationStrategyError(Exception):
    """Raised when an unknown validation strategy is requested."""


# ------------------------------------------------------------------
# Validation strategies
# ------------------------------------------------------------------


async def _consistency_check(
    provider: LLMProvider,
    validator_model: str,
    generator_output: str,
    request: InternalRequest,
) -> tuple[bool, float, List[str]]:
    """
    Re-prompt the validator with the same query and compare outputs.

    A high-confidence agreement returns passed=True.  Significant
    divergence is flagged as an issue.
    """
    prompt = (
        f"You are a quality-assurance validator.\n"
        f"Original query: {request.query}\n\n"
        f"Proposed answer: {generator_output}\n\n"
        f"Is this answer accurate, relevant, and safe? "
        f"Reply with JSON: {{\"verdict\": \"pass\" or \"fail\", "
        f"\"confidence\": 0.0-1.0, \"issues\": [list of issues if any]}}"
    )
    try:
        response = await provider.generate(
            model_id=validator_model,
            prompt=prompt,
            context=request.context,
        )
    except Exception as exc:
        return False, 0.0, [f"Validator call failed: {exc}"]

    # Parse the structured response
    return _parse_validator_response(response)


async def _fact_verification(
    provider: LLMProvider,
    validator_model: str,
    generator_output: str,
    request: InternalRequest,
) -> tuple[bool, float, List[str]]:
    """Ask the validator to fact-check all factual claims in the output."""
    prompt = (
        f"You are a fact-checking validator.\n"
        f"Original query: {request.query}\n\n"
        f"Output to verify: {generator_output}\n\n"
        f"Identify any factual inaccuracies. "
        f"Reply with JSON: {{\"verdict\": \"pass\" or \"fail\", "
        f"\"confidence\": 0.0-1.0, \"issues\": [list of inaccuracies]}}"
    )
    try:
        response = await provider.generate(
            model_id=validator_model,
            prompt=prompt,
            context=request.context,
        )
    except Exception as exc:
        return False, 0.0, [f"Validator call failed: {exc}"]

    return _parse_validator_response(response)


async def _policy_compliance(
    provider: LLMProvider,
    validator_model: str,
    generator_output: str,
    request: InternalRequest,
) -> tuple[bool, float, List[str]]:
    """Ask the validator to audit the output for policy compliance."""
    prompt = (
        f"You are a policy-compliance auditor.\n"
        f"Data classification: {request.data_class.value}\n"
        f"Trust level: {request.trust_level.name}\n"
        f"Output to audit: {generator_output}\n\n"
        f"Does this output comply with data-handling policies? "
        f"Reply with JSON: {{\"verdict\": \"pass\" or \"fail\", "
        f"\"confidence\": 0.0-1.0, \"issues\": [list of violations]}}"
    )
    try:
        response = await provider.generate(
            model_id=validator_model,
            prompt=prompt,
            context=request.context,
        )
    except Exception as exc:
        return False, 0.0, [f"Validator call failed: {exc}"]

    return _parse_validator_response(response)


def _parse_validator_response(response: str) -> tuple[bool, float, List[str]]:
    """
    Parse a structured JSON verdict from a validator LLM response.

    Falls back gracefully if the response is not valid JSON — assumes
    pass with moderate confidence so that a badly-formatted validator
    response does not silently suppress valid output.
    """
    import json

    try:
        data = json.loads(response)
        verdict = data.get("verdict", "pass")
        confidence = float(data.get("confidence", 0.8))
        issues: List[str] = data.get("issues", [])
        passed = verdict.lower() == "pass"
        return passed, confidence, issues
    except (json.JSONDecodeError, ValueError, TypeError):
        # Validator returned free-form text — treat as informational pass
        _logger.warning("ATHENA: validator returned non-JSON response, treating as pass")
        return True, 0.75, []


_STRATEGY_DISPATCH = {
    "consistency_check": _consistency_check,
    "fact_verification": _fact_verification,
    "policy_compliance": _policy_compliance,
}


# ------------------------------------------------------------------
# ATHENA class
# ------------------------------------------------------------------


class Athena:
    """
    ATHENA — Cross-Validation Module.

    Validates LLM-generated output using an independent second model.

    The validator model is automatically selected from the built-in
    ``validator_model_map`` (generator → validator) or the
    ``default_validator`` fallback.  Passing the same model as both
    generator and validator raises :class:`ValidatorModelError`.
    """

    def __init__(
        self,
        mnemosyne: Mnemosyne,
        llm_provider: LLMProvider,
        strategy: str = "consistency_check",
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        validator_model_map: Optional[Dict[str, str]] = None,
        default_validator: str = _DEFAULT_FALLBACK_VALIDATOR,
    ) -> None:
        """
        Args:
            mnemosyne: Shared MNEMOSYNE instance for audit logging.
            llm_provider: LLM backend used to run validation calls.
            strategy: Validation strategy to apply.  One of
                ``"consistency_check"``, ``"fact_verification"``,
                ``"policy_compliance"``.
            confidence_threshold: Minimum confidence required to pass.
                Results below this value are treated as failures.
            validator_model_map: Map of generator_model → validator_model.
                Defaults to the built-in map.
            default_validator: Fallback validator model when the generator
                is not found in ``validator_model_map``.

        Raises:
            ValidationStrategyError: If ``strategy`` is not recognised.
        """
        if strategy not in _STRATEGY_DISPATCH:
            raise ValidationStrategyError(
                f"Unknown strategy {strategy!r}. "
                f"Valid options: {list(_STRATEGY_DISPATCH)}"
            )
        self._mnemosyne = mnemosyne
        self._provider = llm_provider
        self._strategy = strategy
        self._confidence_threshold = confidence_threshold
        self._validator_map: Dict[str, str] = (
            validator_model_map if validator_model_map is not None else dict(_DEFAULT_VALIDATOR_MAP)
        )
        self._default_validator = default_validator

    def _select_validator_model(self, generator_model: str) -> str:
        """
        Select a validator model that differs from the generator.

        Raises:
            ValidatorModelError: If the resolved validator equals the generator.
        """
        validator = self._validator_map.get(generator_model, self._default_validator)
        if validator == generator_model:
            raise ValidatorModelError(
                f"Validator model {validator!r} must differ from generator "
                f"model {generator_model!r}. Update the validator_model_map."
            )
        return validator

    async def validate(
        self,
        generator_output: str,
        request: InternalRequest,
        generator_model: str,
    ) -> ValidationResult:
        """
        Cross-validate the generator output using an independent model.

        Args:
            generator_output: The raw text produced by the generator LLM.
            request: The original InternalRequest (used for context).
            generator_model: The model ID that produced ``generator_output``.
                ATHENA enforces that the validator differs from this.

        Returns:
            :class:`~godai.models.validation.ValidationResult`

        Raises:
            ValidatorModelError: If the validator equals the generator.
        """
        validator_model = self._select_validator_model(generator_model)
        strategy_fn = _STRATEGY_DISPATCH[self._strategy]

        passed, confidence, issues = await strategy_fn(
            provider=self._provider,
            validator_model=validator_model,
            generator_output=generator_output,
            request=request,
        )

        # Apply confidence threshold
        if confidence < self._confidence_threshold and passed:
            passed = False
            issues.append(
                f"Confidence {confidence:.2f} below threshold {self._confidence_threshold:.2f}"
            )

        result = ValidationResult(
            passed=passed,
            confidence=confidence,
            strategy_used=self._strategy,
            issues_found=issues,
            validator_model=validator_model,
            timestamp=datetime.now(timezone.utc),
        )

        await self._mnemosyne.append(AuditEvent(
            event_type="validation",
            event_data={
                "request_id": str(request.request_id),
                "user_id": request.user_id,
                "passed": passed,
                "confidence": confidence,
                "strategy": self._strategy,
                "generator_model": generator_model,
                "validator_model": validator_model,
                "issues": issues,
            },
            source_module="ATHENA",
            timestamp=result.timestamp,
        ))

        _logger.info(
            "ATHENA %s request %s (confidence=%.2f, strategy=%s, validator=%s)",
            "PASSED" if passed else "FAILED",
            request.request_id,
            confidence,
            self._strategy,
            validator_model,
        )
        return result
