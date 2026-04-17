"""Tests for HERMES — API Gateway and protocol normalization."""

from __future__ import annotations

import pytest

from godai.models.request import DataClass, TrustLevel
from godai.modules.hermes import AuthenticationError, Hermes, RateLimitError
from godai.modules.mnemosyne import Mnemosyne


def _hermes(rate_limit: int = 100) -> Hermes:
    return Hermes(Mnemosyne(), rate_limit=rate_limit)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_normalize_valid_token_returns_request() -> None:
    h = _hermes()
    req = await h.normalize(
        token="basic-abc123",
        user_id="user-1",
        protocol="http",
        query="Hello",
    )
    assert req.authenticated is True
    assert req.user_id == "user-1"
    assert req.protocol == "http"
    assert req.query == "Hello"


@pytest.mark.asyncio
async def test_normalize_logs_auth_event_to_mnemosyne() -> None:
    m = Mnemosyne()
    h = Hermes(m)
    await h.normalize(token="basic-tok123", user_id="u1", protocol="http", query="q")
    assert len(m) == 1
    assert m.entries[0].event_type == "auth"


@pytest.mark.asyncio
async def test_trust_level_internal_prefix() -> None:
    h = _hermes()
    req = await h.normalize(token="internal-xyz99", user_id="u", protocol="http", query="q")
    assert req.trust_level == TrustLevel.L3


@pytest.mark.asyncio
async def test_trust_level_elevated_prefix() -> None:
    h = _hermes()
    req = await h.normalize(token="elevated-abc", user_id="u", protocol="http", query="q")
    assert req.trust_level == TrustLevel.L2


@pytest.mark.asyncio
async def test_trust_level_basic_prefix() -> None:
    h = _hermes()
    req = await h.normalize(token="basic-abc123", user_id="u", protocol="http", query="q")
    assert req.trust_level == TrustLevel.L1


@pytest.mark.asyncio
async def test_trust_level_unknown_prefix_defaults_to_l1() -> None:
    h = _hermes()
    req = await h.normalize(token="xyzxyzxyz", user_id="u", protocol="http", query="q")
    assert req.trust_level == TrustLevel.L1


@pytest.mark.asyncio
async def test_data_class_resolved_from_context() -> None:
    h = _hermes()
    req = await h.normalize(
        token="elevated-tok",
        user_id="u",
        protocol="http",
        query="q",
        context={"data_class": "SENSITIVE"},
    )
    assert req.data_class == DataClass.SENSITIVE


@pytest.mark.asyncio
async def test_data_class_defaults_to_public_when_absent() -> None:
    h = _hermes()
    req = await h.normalize(token="basic-tok123", user_id="u", protocol="http", query="q")
    assert req.data_class == DataClass.PUBLIC


@pytest.mark.asyncio
async def test_data_class_unknown_value_defaults_to_public() -> None:
    h = _hermes()
    req = await h.normalize(
        token="basic-tok123",
        user_id="u",
        protocol="http",
        query="q",
        context={"data_class": "SUPER_SECRET"},
    )
    assert req.data_class == DataClass.PUBLIC


# ---------------------------------------------------------------------------
# Authentication failures
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_token_raises_auth_error() -> None:
    h = _hermes()
    with pytest.raises(AuthenticationError):
        await h.normalize(token=None, user_id="u", protocol="http", query="q")


@pytest.mark.asyncio
async def test_empty_token_raises_auth_error() -> None:
    h = _hermes()
    with pytest.raises(AuthenticationError):
        await h.normalize(token="", user_id="u", protocol="http", query="q")


@pytest.mark.asyncio
async def test_too_short_token_raises_auth_error() -> None:
    h = _hermes()
    with pytest.raises(AuthenticationError):
        await h.normalize(token="short", user_id="u", protocol="http", query="q")


@pytest.mark.asyncio
async def test_rejected_auth_is_logged_to_mnemosyne() -> None:
    m = Mnemosyne()
    h = Hermes(m)
    with pytest.raises(AuthenticationError):
        await h.normalize(token=None, user_id="u", protocol="http", query="q")

    assert len(m) == 1
    assert m.entries[0].event_data["result"] == "rejected"


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_raises_after_n_requests() -> None:
    h = _hermes(rate_limit=3)
    for _ in range(3):
        await h.normalize(token="basic-tok123", user_id="u1", protocol="http", query="q")
    with pytest.raises(RateLimitError):
        await h.normalize(token="basic-tok123", user_id="u1", protocol="http", query="q")


@pytest.mark.asyncio
async def test_rate_limit_is_per_user() -> None:
    h = _hermes(rate_limit=1)
    # user-A exhausts their limit
    await h.normalize(token="basic-tok123", user_id="user-A", protocol="http", query="q")
    with pytest.raises(RateLimitError):
        await h.normalize(token="basic-tok123", user_id="user-A", protocol="http", query="q")
    # user-B is unaffected
    req = await h.normalize(token="basic-tok123", user_id="user-B", protocol="http", query="q")
    assert req.authenticated is True


# ---------------------------------------------------------------------------
# Protocol support
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_websocket_protocol_accepted() -> None:
    h = _hermes()
    req = await h.normalize(token="basic-tok123", user_id="u", protocol="websocket", query="q")
    assert req.protocol == "websocket"


@pytest.mark.asyncio
async def test_grpc_protocol_accepted() -> None:
    h = _hermes()
    req = await h.normalize(token="basic-tok123", user_id="u", protocol="grpc", query="q")
    assert req.protocol == "grpc"


@pytest.mark.asyncio
async def test_invalid_protocol_raises_value_error() -> None:
    h = _hermes()
    with pytest.raises(ValueError):
        await h.normalize(token="basic-tok123", user_id="u", protocol="ftp", query="q")
