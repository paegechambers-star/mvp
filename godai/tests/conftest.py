"""
Shared pytest fixtures and factories for all G.O.D.A.I. tests.

These are automatically available to every test module under godai/tests/
without explicit imports.  Existing test files keep their own local helpers
(prefixed with ``_``) for backward compatibility — the shared versions here
use unprefixed names and are intended for new tests.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from godai.models.policy import PolicyDecision
from godai.models.request import DataClass, InternalRequest, TrustLevel
from godai.modules.hermes import Hermes
from godai.modules.mnemosyne import Mnemosyne
from godai.providers import EchoProvider

# Paths to the bundled config files
POLICY_PATH = Path(__file__).parent.parent / "config" / "policies" / "default.yaml"
ROUTING_PATH = Path(__file__).parent.parent / "config" / "routing" / "rules.yaml"


# ---------------------------------------------------------------------------
# Module fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mnemosyne() -> Mnemosyne:
    """Fresh MNEMOSYNE instance — reset between every test."""
    return Mnemosyne()


@pytest.fixture()
def echo_provider() -> EchoProvider:
    """EchoProvider instance for tests that need an LLMProvider."""
    return EchoProvider()


@pytest.fixture()
def policy_path() -> Path:
    """Path to the default bundled THEMIS policy YAML."""
    return POLICY_PATH


@pytest.fixture()
def routing_path() -> Path:
    """Path to the default bundled APOLLON routing YAML."""
    return ROUTING_PATH


# ---------------------------------------------------------------------------
# Request factory
# ---------------------------------------------------------------------------


def make_request(
    trust: TrustLevel = TrustLevel.L1,
    dc: DataClass = DataClass.PUBLIC,
    action: str = "",
    consent: bool = False,
    query: str = "q",
    user_id: str = "u1",
) -> InternalRequest:
    """
    Build a minimal authenticated InternalRequest for testing.

    All fields that are not semantically interesting for a given test can
    be left at their defaults.
    """
    return InternalRequest(
        request_id=uuid4(),
        user_id=user_id,
        trust_level=trust,
        protocol="http",
        query=query,
        data_class=dc,
        context={"action": action, "explicit_consent": consent},
        timestamp=datetime.now(timezone.utc),
        authenticated=True,
    )


# ---------------------------------------------------------------------------
# PolicyDecision factories
# ---------------------------------------------------------------------------


def make_allow(policy_version: str = "1.0") -> PolicyDecision:
    """PolicyDecision with ``allowed=True`` for use as THEMIS stub output."""
    return PolicyDecision(
        allowed=True,
        reason="ok",
        policy_version=policy_version,
        rules_evaluated=[],
        timestamp=datetime.now(timezone.utc),
    )


def make_deny(policy_version: str = "1.0") -> PolicyDecision:
    """PolicyDecision with ``allowed=False`` for use as THEMIS stub output."""
    return PolicyDecision(
        allowed=False,
        reason="denied",
        policy_version=policy_version,
        rules_evaluated=[],
        timestamp=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# HERMES factory (not a fixture — needs rate_limit parameter)
# ---------------------------------------------------------------------------


def make_hermes(rate_limit: int = 100) -> Hermes:
    """Create a HERMES instance with its own MNEMOSYNE for isolation."""
    return Hermes(Mnemosyne(), rate_limit=rate_limit)
