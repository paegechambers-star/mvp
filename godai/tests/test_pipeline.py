"""Tests for GodaiPipeline — full request lifecycle integration."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import pytest

from godai.modules.athena import LLMProvider
from godai.modules.mnemosyne import Mnemosyne
from godai.pipeline import GodaiPipeline


# ---------------------------------------------------------------------------
# Test LLM provider
# ---------------------------------------------------------------------------


class MockProvider:
    """
    Controllable mock LLM provider for pipeline integration tests.

    Set ``fail_generation=True`` to simulate LLM errors.
    Set ``validation_verdict`` to control ATHENA output.
    """

    def __init__(
        self,
        response: str = "mocked response",
        fail_generation: bool = False,
        validation_verdict: str = "pass",
        validation_confidence: float = 0.9,
    ) -> None:
        self._response = response
        self._fail_generation = fail_generation
        self._validation_verdict = validation_verdict
        self._validation_confidence = validation_confidence
        self.calls: list[dict[str, Any]] = []

    async def generate(self, model_id: str, prompt: str, context: Dict[str, Any]) -> str:
        self.calls.append({"model_id": model_id, "prompt": prompt})
        if self._fail_generation:
            raise RuntimeError("Simulated LLM failure")
        # If this is a validation call (contains "validator" keywords), return verdict
        if "validator" in prompt.lower() or "quality" in prompt.lower() or "fact" in prompt.lower() or "policy" in prompt.lower():
            return (
                f'{{"verdict": "{self._validation_verdict}", '
                f'"confidence": {self._validation_confidence}, "issues": []}}'
            )
        return self._response


# ---------------------------------------------------------------------------
# Config paths
# ---------------------------------------------------------------------------

_POLICY_PATH = Path(__file__).parent.parent / "config" / "policies" / "default.yaml"
_ROUTING_PATH = Path(__file__).parent.parent / "config" / "routing" / "rules.yaml"


def _pipeline(provider: MockProvider | None = None, **kwargs: Any) -> GodaiPipeline:
    return GodaiPipeline.create(
        llm_provider=provider or MockProvider(),
        policy_path=_POLICY_PATH,
        routing_path=_ROUTING_PATH,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_request_succeeds_end_to_end() -> None:
    provider = MockProvider(response="Hello!")
    pipeline = _pipeline(provider)

    result = await pipeline.process(
        token="basic-tok123456",
        user_id="user-1",
        protocol="http",
        query="Say hello",
        context={"data_class": "PUBLIC"},
    )

    assert result.success is True
    assert result.output == "Hello!"
    assert result.error is None
    assert result.request is not None
    assert result.policy_decision is not None
    assert result.route_decision is not None
    assert result.validation_result is not None


@pytest.mark.asyncio
async def test_internal_l1_request_succeeds() -> None:
    pipeline = _pipeline()
    result = await pipeline.process(
        token="basic-tok123456",
        user_id="u",
        protocol="http",
        query="q",
        context={"data_class": "INTERNAL"},
    )
    assert result.success is True


@pytest.mark.asyncio
async def test_sensitive_l2_request_succeeds() -> None:
    pipeline = _pipeline()
    result = await pipeline.process(
        token="elevated-tok9999",
        user_id="u",
        protocol="http",
        query="q",
        context={"data_class": "SENSITIVE"},
    )
    assert result.success is True


@pytest.mark.asyncio
async def test_all_decisions_logged_to_mnemosyne() -> None:
    """Invariant 3: every decision must be logged."""
    pipeline = _pipeline()
    await pipeline.process(
        token="basic-tok123456",
        user_id="u",
        protocol="http",
        query="q",
        context={"data_class": "PUBLIC"},
    )
    # Expect at least: auth, policy_check, routing, validation + pipeline_success
    assert len(pipeline.mnemosyne) >= 5
    event_types = {e.event_type for e in pipeline.mnemosyne.entries}
    assert "auth" in event_types
    assert "policy_check" in event_types
    assert "routing" in event_types
    assert "validation" in event_types
    assert "pipeline_success" in event_types  # Invariant 3: pipeline logs its own outcome


@pytest.mark.asyncio
async def test_chain_integrity_after_full_pipeline() -> None:
    pipeline = _pipeline()
    await pipeline.process(
        token="basic-tok123456",
        user_id="u",
        protocol="http",
        query="q",
    )
    assert pipeline.mnemosyne.verify_chain() is True


# ---------------------------------------------------------------------------
# THEMIS denial
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sensitive_l1_denied_by_policy() -> None:
    """THEMIS must deny SENSITIVE data from L1 user — pipeline returns 403."""
    pipeline = _pipeline()
    result = await pipeline.process(
        token="basic-tok123456",
        user_id="u",
        protocol="http",
        query="q",
        context={"data_class": "SENSITIVE"},
    )
    assert result.success is False
    assert "denied" in result.error.lower() or "L2" in result.error
    assert result.route_decision is None
    assert result.validation_result is None


@pytest.mark.asyncio
async def test_policy_denial_still_logs_to_mnemosyne() -> None:
    """Even denied requests must be fully logged (Invariant 3)."""
    pipeline = _pipeline()
    await pipeline.process(
        token="basic-tok123456",
        user_id="u",
        protocol="http",
        query="q",
        context={"data_class": "SENSITIVE"},
    )
    event_types = {e.event_type for e in pipeline.mnemosyne.entries}
    assert "auth" in event_types
    assert "policy_check" in event_types
    assert "pipeline_error" in event_types  # pipeline logs its own failure outcome


# ---------------------------------------------------------------------------
# Authentication failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_token_returns_auth_failure() -> None:
    pipeline = _pipeline()
    result = await pipeline.process(
        token=None,
        user_id="u",
        protocol="http",
        query="q",
    )
    assert result.success is False
    assert result.request is None
    assert "401" in result.error or "Missing" in result.error


@pytest.mark.asyncio
async def test_short_token_returns_auth_failure() -> None:
    pipeline = _pipeline()
    result = await pipeline.process(
        token="short",
        user_id="u",
        protocol="http",
        query="q",
    )
    assert result.success is False


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_returns_failure() -> None:
    pipeline = _pipeline(rate_limit=2)
    for _ in range(2):
        await pipeline.process(token="basic-tok123456", user_id="u", protocol="http", query="q")

    result = await pipeline.process(token="basic-tok123456", user_id="u", protocol="http", query="q")
    assert result.success is False
    assert "429" in result.error or "Rate limit" in result.error or "rate" in result.error.lower()


# ---------------------------------------------------------------------------
# Validation failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validation_failure_returns_error() -> None:
    provider = MockProvider(validation_verdict="fail", validation_confidence=0.9)
    pipeline = _pipeline(provider, confidence_threshold=0.6)

    result = await pipeline.process(
        token="basic-tok123456",
        user_id="u",
        protocol="http",
        query="q",
        context={"data_class": "PUBLIC"},
    )
    assert result.success is False
    assert "Validation failed" in result.error


# ---------------------------------------------------------------------------
# LLM generation failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_generation_failure_returns_error() -> None:
    provider = MockProvider(fail_generation=True)
    pipeline = _pipeline(provider)

    result = await pipeline.process(
        token="basic-tok123456",
        user_id="u",
        protocol="http",
        query="q",
        context={"data_class": "PUBLIC"},
    )
    assert result.success is False
    assert "Generation failed" in result.error


# ---------------------------------------------------------------------------
# Routing correctness
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_request_routes_to_haiku() -> None:
    pipeline = _pipeline()
    result = await pipeline.process(
        token="basic-tok123456",
        user_id="u",
        protocol="http",
        query="q",
        context={"data_class": "PUBLIC"},
    )
    assert result.success is True
    assert "haiku" in result.route_decision.model_id.lower()


@pytest.mark.asyncio
async def test_sensitive_l2_routes_to_sonnet() -> None:
    pipeline = _pipeline()
    result = await pipeline.process(
        token="elevated-tok9999",
        user_id="u",
        protocol="http",
        query="q",
        context={"data_class": "SENSITIVE"},
    )
    assert result.success is True
    assert "sonnet" in result.route_decision.model_id.lower()
