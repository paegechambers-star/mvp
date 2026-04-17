"""Tests for THEMIS — Policy Engine."""

from __future__ import annotations

import textwrap
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone

import pytest

from godai.models.request import DataClass, InternalRequest, TrustLevel
from godai.modules.mnemosyne import Mnemosyne
from godai.modules.themis import PolicyLoadError, Themis


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_policy(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "policy.yaml"
    p.write_text(textwrap.dedent(content))
    return p


def _make_request(
    trust: TrustLevel = TrustLevel.L1,
    dc: DataClass = DataClass.PUBLIC,
    action: str = "",
    consent: bool = False,
) -> InternalRequest:
    return InternalRequest(
        request_id=uuid4(),
        user_id="u1",
        trust_level=trust,
        protocol="http",
        query="q",
        data_class=dc,
        context={"action": action, "explicit_consent": consent},
        timestamp=datetime.now(timezone.utc),
        authenticated=True,
    )


@pytest.fixture()
def default_policy_path() -> Path:
    """Points to the real default policy shipped with G.O.D.A.I."""
    return Path(__file__).parent.parent / "config" / "policies" / "default.yaml"


@pytest.fixture()
def mnemosyne() -> Mnemosyne:
    return Mnemosyne()


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def test_load_nonexistent_file_raises(tmp_path: Path, mnemosyne: Mnemosyne) -> None:
    with pytest.raises(PolicyLoadError, match="Cannot read"):
        Themis(mnemosyne, tmp_path / "missing.yaml")


def test_load_invalid_yaml_raises(tmp_path: Path, mnemosyne: Mnemosyne) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("{ unclosed: [")
    with pytest.raises(PolicyLoadError, match="Invalid YAML"):
        Themis(mnemosyne, bad)


def test_policy_version_is_tracked(tmp_path: Path, mnemosyne: Mnemosyne) -> None:
    p = _write_policy(tmp_path, """
        version: "2.5"
        rules: []
    """)
    t = Themis(mnemosyne, p)
    assert t.policy_version == "2.5"


# ---------------------------------------------------------------------------
# Happy path — request allowed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_request_l1_passes(
    tmp_path: Path, mnemosyne: Mnemosyne
) -> None:
    p = _write_policy(tmp_path, """
        version: "1.0"
        rules:
          - id: "PII_REQUIRES_L2"
            condition: "data_class == SENSITIVE"
            requirement: "trust_level >= L2"
            action: "deny"
            message: "Need L2"
    """)
    t = Themis(mnemosyne, p)
    req = _make_request(trust=TrustLevel.L1, dc=DataClass.PUBLIC)
    decision = await t.evaluate(req)

    assert decision.allowed is True
    assert "PII_REQUIRES_L2" in decision.rules_evaluated
    assert len(mnemosyne) == 1


@pytest.mark.asyncio
async def test_sensitive_request_l2_passes(
    tmp_path: Path, mnemosyne: Mnemosyne
) -> None:
    p = _write_policy(tmp_path, """
        version: "1.0"
        rules:
          - id: "PII_REQUIRES_L2"
            condition: "data_class == SENSITIVE"
            requirement: "trust_level >= L2"
            action: "deny"
            message: "Need L2"
    """)
    t = Themis(mnemosyne, p)
    req = _make_request(trust=TrustLevel.L2, dc=DataClass.SENSITIVE)
    decision = await t.evaluate(req)

    assert decision.allowed is True


@pytest.mark.asyncio
async def test_no_rules_always_allows(
    tmp_path: Path, mnemosyne: Mnemosyne
) -> None:
    p = _write_policy(tmp_path, "version: '1.0'\nrules: []\n")
    t = Themis(mnemosyne, p)
    req = _make_request(trust=TrustLevel.L0, dc=DataClass.RESTRICTED)
    decision = await t.evaluate(req)
    assert decision.allowed is True


# ---------------------------------------------------------------------------
# Denial scenarios
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sensitive_request_l1_denied(
    tmp_path: Path, mnemosyne: Mnemosyne
) -> None:
    p = _write_policy(tmp_path, """
        version: "1.0"
        rules:
          - id: "PII_REQUIRES_L2"
            condition: "data_class == SENSITIVE"
            requirement: "trust_level >= L2"
            action: "deny"
            message: "Sensitive data requires L2+"
    """)
    t = Themis(mnemosyne, p)
    req = _make_request(trust=TrustLevel.L1, dc=DataClass.SENSITIVE)
    decision = await t.evaluate(req)

    assert decision.allowed is False
    assert "L2" in decision.reason
    assert decision.policy_version == "1.0"
    assert len(mnemosyne) == 1
    assert mnemosyne.entries[0].event_data["allowed"] is False


@pytest.mark.asyncio
async def test_email_action_without_consent_denied(
    tmp_path: Path, mnemosyne: Mnemosyne
) -> None:
    p = _write_policy(tmp_path, """
        version: "1.0"
        rules:
          - id: "EMAIL_REQUIRES_CONSENT"
            condition: "action == 'send_email'"
            requirement: "explicit_consent == true"
            action: "deny"
            message: "Email requires consent"
    """)
    t = Themis(mnemosyne, p)
    req = _make_request(trust=TrustLevel.L2, action="send_email", consent=False)
    decision = await t.evaluate(req)

    assert decision.allowed is False


@pytest.mark.asyncio
async def test_email_action_with_consent_allowed(
    tmp_path: Path, mnemosyne: Mnemosyne
) -> None:
    p = _write_policy(tmp_path, """
        version: "1.0"
        rules:
          - id: "EMAIL_REQUIRES_CONSENT"
            condition: "action == 'send_email'"
            requirement: "explicit_consent == true"
            action: "deny"
            message: "Email requires consent"
    """)
    t = Themis(mnemosyne, p)
    req = _make_request(trust=TrustLevel.L2, action="send_email", consent=True)
    decision = await t.evaluate(req)

    assert decision.allowed is True


# ---------------------------------------------------------------------------
# Default policy file integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_policy_restricted_requires_l3(
    default_policy_path: Path,
) -> None:
    m = Mnemosyne()
    t = Themis(m, default_policy_path)
    req = _make_request(trust=TrustLevel.L2, dc=DataClass.RESTRICTED)
    decision = await t.evaluate(req)
    assert decision.allowed is False


@pytest.mark.asyncio
async def test_default_policy_restricted_l3_allowed(
    default_policy_path: Path,
) -> None:
    m = Mnemosyne()
    t = Themis(m, default_policy_path)
    req = _make_request(trust=TrustLevel.L3, dc=DataClass.RESTRICTED)
    decision = await t.evaluate(req)
    assert decision.allowed is True


# ---------------------------------------------------------------------------
# Policy version in every decision
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_policy_version_in_allowed_decision(
    tmp_path: Path, mnemosyne: Mnemosyne
) -> None:
    p = _write_policy(tmp_path, "version: '9.9'\nrules: []\n")
    t = Themis(mnemosyne, p)
    req = _make_request()
    decision = await t.evaluate(req)
    assert decision.policy_version == "9.9"


# ---------------------------------------------------------------------------
# Hot reload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reload_policy_picks_up_changes(
    tmp_path: Path, mnemosyne: Mnemosyne
) -> None:
    policy_file = _write_policy(tmp_path, "version: '1.0'\nrules: []\n")
    t = Themis(mnemosyne, policy_file)
    assert t.policy_version == "1.0"

    # Update the file and reload
    policy_file.write_text("version: '2.0'\nrules: []\n")
    t.reload_policy()
    assert t.policy_version == "2.0"
