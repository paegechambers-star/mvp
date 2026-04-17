"""Tests for APOLLON — Deterministic Model Router."""

from __future__ import annotations

import textwrap
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from godai.models.policy import PolicyDecision
from godai.models.request import DataClass, InternalRequest, TrustLevel
from godai.modules.apollon import Apollon, RoutingConfigError
from godai.modules.mnemosyne import Mnemosyne


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_routing(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "routing.yaml"
    p.write_text(textwrap.dedent(content))
    return p


def _make_request(
    trust: TrustLevel = TrustLevel.L1,
    dc: DataClass = DataClass.PUBLIC,
) -> InternalRequest:
    return InternalRequest(
        request_id=uuid4(),
        user_id="u1",
        trust_level=trust,
        protocol="http",
        query="q",
        data_class=dc,
        context={},
        timestamp=datetime.now(timezone.utc),
        authenticated=True,
    )


def _allow() -> PolicyDecision:
    return PolicyDecision(
        allowed=True,
        reason="ok",
        policy_version="1.0",
        rules_evaluated=[],
        timestamp=datetime.now(timezone.utc),
    )


def _deny() -> PolicyDecision:
    return PolicyDecision(
        allowed=False,
        reason="denied",
        policy_version="1.0",
        rules_evaluated=[],
        timestamp=datetime.now(timezone.utc),
    )


MINIMAL_CONFIG = """
version: "1.0"
routes:
  - default:
      model: "claude-sonnet-4-6"
      reason: "Default fallback"
"""

FULL_CONFIG = """
version: "1.0"
routes:
  - condition: "data_class == SENSITIVE and trust_level >= L2"
    model: "claude-sonnet-4-6"
    reason: "Sensitive + L2"
  - condition: "data_class == PUBLIC"
    model: "claude-haiku-4-5-20251001"
    reason: "Public data"
  - default:
      model: "claude-sonnet-4-6"
      reason: "Default fallback"
"""


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def test_missing_routing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(RoutingConfigError, match="Cannot read"):
        Apollon(Mnemosyne(), tmp_path / "missing.yaml")


def test_invalid_yaml_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("{ unclosed: [")
    with pytest.raises(RoutingConfigError, match="Invalid YAML"):
        Apollon(Mnemosyne(), bad)


def test_missing_default_raises(tmp_path: Path) -> None:
    p = _write_routing(tmp_path, """
        version: "1.0"
        routes:
          - condition: "data_class == PUBLIC"
            model: "claude-haiku-4-5-20251001"
            reason: "Public"
    """)
    with pytest.raises(RoutingConfigError, match="default"):
        Apollon(Mnemosyne(), p)


# ---------------------------------------------------------------------------
# Determinism — invariant verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_input_produces_same_output(tmp_path: Path) -> None:
    """Core invariant: routing is a pure function."""
    p = _write_routing(tmp_path, FULL_CONFIG)
    a = Apollon(Mnemosyne(), p)
    req = _make_request(trust=TrustLevel.L2, dc=DataClass.SENSITIVE)
    pd = _allow()

    result_1 = await a.route(req, pd)
    result_2 = await a.route(req, pd)

    assert result_1.model_id == result_2.model_id
    assert result_1.reason == result_2.reason


# ---------------------------------------------------------------------------
# Routing decisions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sensitive_l2_routes_to_sonnet(tmp_path: Path) -> None:
    p = _write_routing(tmp_path, FULL_CONFIG)
    a = Apollon(Mnemosyne(), p)
    req = _make_request(trust=TrustLevel.L2, dc=DataClass.SENSITIVE)
    decision = await a.route(req, _allow())
    assert decision.model_id == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_public_routes_to_haiku(tmp_path: Path) -> None:
    p = _write_routing(tmp_path, FULL_CONFIG)
    a = Apollon(Mnemosyne(), p)
    req = _make_request(trust=TrustLevel.L1, dc=DataClass.PUBLIC)
    decision = await a.route(req, _allow())
    assert decision.model_id == "claude-haiku-4-5-20251001"


@pytest.mark.asyncio
async def test_no_condition_match_uses_default(tmp_path: Path) -> None:
    p = _write_routing(tmp_path, """
        version: "1.0"
        routes:
          - condition: "data_class == RESTRICTED"
            model: "model-a"
            reason: "Restricted only"
          - default:
              model: "model-default"
              reason: "Default"
    """)
    a = Apollon(Mnemosyne(), p)
    req = _make_request(trust=TrustLevel.L1, dc=DataClass.PUBLIC)
    decision = await a.route(req, _allow())
    assert decision.model_id == "model-default"


@pytest.mark.asyncio
async def test_route_logs_to_mnemosyne(tmp_path: Path) -> None:
    m = Mnemosyne()
    p = _write_routing(tmp_path, MINIMAL_CONFIG)
    a = Apollon(m, p)
    await a.route(_make_request(), _allow())
    assert len(m) == 1
    assert m.entries[0].event_type == "routing"


@pytest.mark.asyncio
async def test_route_decision_includes_routing_version(tmp_path: Path) -> None:
    p = _write_routing(tmp_path, MINIMAL_CONFIG)
    a = Apollon(Mnemosyne(), p)
    decision = await a.route(_make_request(), _allow())
    assert decision.routing_version == "1.0"


# ---------------------------------------------------------------------------
# Invariant: denied policy must not reach APOLLON
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_raises_on_denied_policy(tmp_path: Path) -> None:
    p = _write_routing(tmp_path, MINIMAL_CONFIG)
    a = Apollon(Mnemosyne(), p)
    with pytest.raises(ValueError, match="denied PolicyDecision"):
        await a.route(_make_request(), _deny())


# ---------------------------------------------------------------------------
# Default routing config integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_routing_config_is_valid() -> None:
    rules_path = Path(__file__).parent.parent / "config" / "routing" / "rules.yaml"
    a = Apollon(Mnemosyne(), rules_path)
    req = _make_request(trust=TrustLevel.L1, dc=DataClass.PUBLIC)
    decision = await a.route(req, _allow())
    assert decision.model_id  # non-empty model selected
