"""Tests for ATHENA — Cross-Validation Module."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
from uuid import uuid4

import pytest

from godai.models.request import DataClass, InternalRequest, TrustLevel
from godai.modules.athena import (
    Athena,
    LLMProvider,
    ValidatorModelError,
    ValidationStrategyError,
)
from godai.modules.mnemosyne import Mnemosyne


# ---------------------------------------------------------------------------
# Test LLM provider implementations
# ---------------------------------------------------------------------------


class PassingProvider:
    """Mock provider: always returns a valid passing verdict."""

    async def generate(self, model_id: str, prompt: str, context: Dict[str, Any]) -> str:
        return '{"verdict": "pass", "confidence": 0.95, "issues": []}'


class FailingProvider:
    """Mock provider: always returns a failing verdict."""

    async def generate(self, model_id: str, prompt: str, context: Dict[str, Any]) -> str:
        return '{"verdict": "fail", "confidence": 0.90, "issues": ["Factual error found"]}'


class LowConfidenceProvider:
    """Mock provider: passes verdict but low confidence (below default threshold)."""

    async def generate(self, model_id: str, prompt: str, context: Dict[str, Any]) -> str:
        return '{"verdict": "pass", "confidence": 0.4, "issues": []}'


class ErrorProvider:
    """Mock provider: raises an exception on generate."""

    async def generate(self, model_id: str, prompt: str, context: Dict[str, Any]) -> str:
        raise RuntimeError("LLM backend unreachable")


class FreeTextProvider:
    """Mock provider: returns free-form text instead of JSON."""

    async def generate(self, model_id: str, prompt: str, context: Dict[str, Any]) -> str:
        return "This answer looks correct to me."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request() -> InternalRequest:
    return InternalRequest(
        request_id=uuid4(),
        user_id="u1",
        trust_level=TrustLevel.L1,
        protocol="http",
        query="What is 2+2?",
        data_class=DataClass.PUBLIC,
        context={},
        timestamp=datetime.now(timezone.utc),
        authenticated=True,
    )


def _athena(provider: LLMProvider, strategy: str = "consistency_check", threshold: float = 0.7) -> Athena:
    return Athena(
        mnemosyne=Mnemosyne(),
        llm_provider=provider,
        strategy=strategy,
        confidence_threshold=threshold,
    )


GENERATOR = "claude-haiku-4-5-20251001"
EXPECTED_VALIDATOR = "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_passing_validation_returns_passed_true() -> None:
    a = _athena(PassingProvider())
    result = await a.validate("4", _make_request(), GENERATOR)

    assert result.passed is True
    assert result.confidence >= 0.7
    assert result.validator_model == EXPECTED_VALIDATOR
    assert result.strategy_used == "consistency_check"


@pytest.mark.asyncio
async def test_validation_logs_to_mnemosyne() -> None:
    m = Mnemosyne()
    a = Athena(m, PassingProvider())
    await a.validate("4", _make_request(), GENERATOR)

    assert len(m) == 1
    assert m.entries[0].event_type == "validation"


@pytest.mark.asyncio
async def test_all_three_strategies_succeed() -> None:
    for strategy in ("consistency_check", "fact_verification", "policy_compliance"):
        a = _athena(PassingProvider(), strategy=strategy)
        result = await a.validate("answer", _make_request(), GENERATOR)
        assert result.passed is True
        assert result.strategy_used == strategy


# ---------------------------------------------------------------------------
# Failure scenarios
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failing_provider_returns_passed_false() -> None:
    a = _athena(FailingProvider())
    result = await a.validate("wrong answer", _make_request(), GENERATOR)

    assert result.passed is False
    assert result.issues_found  # non-empty


@pytest.mark.asyncio
async def test_low_confidence_below_threshold_fails() -> None:
    a = _athena(LowConfidenceProvider(), threshold=0.7)
    result = await a.validate("answer", _make_request(), GENERATOR)

    assert result.passed is False
    assert any("Confidence" in issue for issue in result.issues_found)


@pytest.mark.asyncio
async def test_high_threshold_causes_passing_verdict_to_fail() -> None:
    """Provider returns 0.95 confidence but threshold is 0.99."""
    a = _athena(PassingProvider(), threshold=0.99)
    result = await a.validate("answer", _make_request(), GENERATOR)

    assert result.passed is False


@pytest.mark.asyncio
async def test_provider_exception_captured_as_failure() -> None:
    a = _athena(ErrorProvider())
    result = await a.validate("answer", _make_request(), GENERATOR)

    assert result.passed is False
    assert result.issues_found


@pytest.mark.asyncio
async def test_free_text_response_treated_as_informational_pass() -> None:
    a = _athena(FreeTextProvider())
    result = await a.validate("answer", _make_request(), GENERATOR)
    # FreeTextProvider returns non-JSON → parse fallback → pass at 0.75
    assert result.passed is True


# ---------------------------------------------------------------------------
# Invariant: validator ≠ generator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_generator_and_validator_raises() -> None:
    # Force the map so generator == validator
    a = Athena(
        mnemosyne=Mnemosyne(),
        llm_provider=PassingProvider(),
        validator_model_map={"some-model": "some-model"},
        default_validator="some-model",
    )
    req = _make_request()
    with pytest.raises(ValidatorModelError):
        await a.validate("output", req, generator_model="some-model")


# ---------------------------------------------------------------------------
# Strategy validation
# ---------------------------------------------------------------------------


def test_unknown_strategy_raises_at_construction() -> None:
    with pytest.raises(ValidationStrategyError):
        Athena(
            mnemosyne=Mnemosyne(),
            llm_provider=PassingProvider(),
            strategy="mind_reading",
        )


# ---------------------------------------------------------------------------
# Audit data correctness
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_entry_contains_both_models() -> None:
    m = Mnemosyne()
    a = Athena(m, PassingProvider())
    await a.validate("output", _make_request(), GENERATOR)

    entry_data = m.entries[0].event_data
    assert entry_data["generator_model"] == GENERATOR
    assert entry_data["validator_model"] == EXPECTED_VALIDATOR
    assert entry_data["passed"] is True
