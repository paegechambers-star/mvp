"""
HERMES — API Gateway and protocol normalization layer.

Authentication strategy:
  1. JWT (HS256, signed with secret_key) — production default.
     Claims: {"sub": user_id, "trust": "L1|L2|L3", "exp": unix_ts, "iat": unix_ts}
  2. Prefix-based legacy tokens (``basic-``, ``elevated-``, ``internal-``) —
     accepted only when ``dev_mode=True`` for backward compatibility with
     development and tests.  Never enable in production.

Use :func:`create_token` to issue valid JWT tokens.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

from godai.models.audit import AuditEvent
from godai.models.request import DataClass, InternalRequest, TrustLevel
from godai.modules.mnemosyne import Mnemosyne

_logger = logging.getLogger("godai.hermes")

_TOKEN_TRUST_MAP: Dict[str, TrustLevel] = {
    "internal-": TrustLevel.L3,
    "elevated-": TrustLevel.L2,
    "basic-": TrustLevel.L1,
}
_MIN_TOKEN_LEN: int = 8
_JWT_DEFAULT_EXPIRY_HOURS = 24


# ── Pure-stdlib JWT (HS256 only) ──────────────────────────────────────────────

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * (pad % 4))


def create_token(
    user_id: str,
    trust_level: TrustLevel,
    secret_key: str,
    expires_hours: int = _JWT_DEFAULT_EXPIRY_HOURS,
) -> str:
    """
    Issue a signed HS256 JWT for a given user and trust level.

    Args:
        user_id: Caller identifier (stored in ``sub`` claim).
        trust_level: Trust level to embed (``L1``, ``L2``, or ``L3``).
        secret_key: HMAC signing key (``SECRET_KEY`` env var in prod).
        expires_hours: Token lifetime in hours.

    Returns:
        Signed JWT string.
    """
    now = datetime.now(timezone.utc)
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "trust": trust_level.name,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=expires_hours)).timestamp()),
    }
    h = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{h}.{p}".encode("ascii")
    sig = hmac.new(secret_key.encode(), signing_input, hashlib.sha256).digest()
    return f"{h}.{p}.{_b64url_encode(sig)}"


def _decode_token(token: str, secret_key: str) -> Dict[str, Any]:
    """
    Decode and verify an HS256 JWT.

    Raises:
        ValueError: On invalid format, bad signature, or expired token.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Not a JWT (wrong segment count)")

    h_raw, p_raw, sig_raw = parts
    signing_input = f"{h_raw}.{p_raw}".encode("ascii")
    expected_sig = hmac.new(secret_key.encode(), signing_input, hashlib.sha256).digest()
    actual_sig = _b64url_decode(sig_raw)

    if not hmac.compare_digest(expected_sig, actual_sig):
        raise ValueError("JWT signature verification failed")

    payload: Dict[str, Any] = json.loads(_b64url_decode(p_raw))

    exp = payload.get("exp")
    if exp is not None and int(datetime.now(timezone.utc).timestamp()) > exp:
        raise ValueError("JWT token has expired")

    return payload


# ── Errors ────────────────────────────────────────────────────────────────────

class AuthenticationError(Exception):
    """Raised when authentication fails (HTTP 401 equivalent)."""


class RateLimitError(Exception):
    """Raised when a user exceeds their request rate limit (HTTP 429 equivalent)."""


# ── HERMES ────────────────────────────────────────────────────────────────────

class Hermes:
    """
    HERMES — API Gateway.

    JWT primary authentication with prefix-based legacy fallback in dev mode.
    """

    def __init__(
        self,
        mnemosyne: Mnemosyne,
        rate_limit: int = 100,
        secret_key: str = "dev-secret",
        dev_mode: bool = True,
    ) -> None:
        self._mnemosyne = mnemosyne
        self._rate_limit = rate_limit
        self._secret_key = secret_key
        self._dev_mode = dev_mode
        self._request_counts: Dict[str, int] = {}

    def _validate_token(self, token: str) -> Tuple[str, TrustLevel]:
        """
        Validate token and return (user_id, TrustLevel).

        Tries JWT first; falls back to prefix matching when dev_mode=True.

        Raises:
            AuthenticationError: If invalid, expired, or not accepted.
        """
        # ── 1. Try JWT ────────────────────────────────────────────────
        try:
            payload = _decode_token(token, self._secret_key)
            trust_name = payload.get("trust", "L1")
            try:
                trust_level = TrustLevel[trust_name]
            except KeyError:
                trust_level = TrustLevel.L1
            return payload.get("sub", ""), trust_level
        except ValueError as jwt_exc:
            if "expired" in str(jwt_exc):
                raise AuthenticationError(f"Token has expired (401)") from jwt_exc
            # Other JWT parse errors — fall through to prefix fallback if dev_mode
            if not self._dev_mode:
                raise AuthenticationError(f"Invalid JWT token (401)") from jwt_exc

        # ── 2. Legacy prefix fallback (dev mode only) ─────────────────
        for prefix, level in _TOKEN_TRUST_MAP.items():
            if token.startswith(prefix):
                return "", level
        return "", TrustLevel.L1  # unknown prefix → default L1 in dev mode

    def _resolve_data_class(self, context: Dict[str, Any]) -> DataClass:
        raw: str = context.get("data_class", DataClass.PUBLIC.value)
        try:
            return DataClass(raw)
        except ValueError:
            _logger.warning("Unknown data_class %r — defaulting to PUBLIC", raw)
            return DataClass.PUBLIC

    def _check_rate_limit(self, user_id: str) -> None:
        count = self._request_counts.get(user_id, 0)
        if count >= self._rate_limit:
            raise RateLimitError(
                f"Rate limit of {self._rate_limit} exceeded for user {user_id!r} (429)"
            )
        self._request_counts[user_id] = count + 1

    async def normalize(
        self,
        token: Optional[str],
        user_id: str,
        protocol: str,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> InternalRequest:
        """
        Normalize a raw external request into a canonical InternalRequest.

        In production mode (``dev_mode=False``) only valid, non-expired JWTs
        are accepted.  In dev mode prefix tokens also work.

        Raises:
            AuthenticationError: Token missing, expired, or invalid.
            RateLimitError: User exceeded the per-user request limit.
        """
        ctx: Dict[str, Any] = context or {}
        now = datetime.now(timezone.utc)

        if not token:
            await self._mnemosyne.append(AuditEvent(
                event_type="auth",
                event_data={"user_id": user_id, "result": "rejected", "reason": "missing_token"},
                source_module="HERMES",
                timestamp=now,
            ))
            raise AuthenticationError(f"Missing authentication token for user {user_id!r} (401)")

        if len(token) < _MIN_TOKEN_LEN:
            await self._mnemosyne.append(AuditEvent(
                event_type="auth",
                event_data={"user_id": user_id, "result": "rejected", "reason": "token_too_short"},
                source_module="HERMES",
                timestamp=now,
            ))
            raise AuthenticationError(f"Invalid authentication token for user {user_id!r} (401)")

        try:
            token_user_id, trust_level = self._validate_token(token)
        except AuthenticationError:
            await self._mnemosyne.append(AuditEvent(
                event_type="auth",
                event_data={"user_id": user_id, "result": "rejected", "reason": "invalid_token"},
                source_module="HERMES",
                timestamp=now,
            ))
            raise

        resolved_user_id = token_user_id if token_user_id else user_id
        self._check_rate_limit(resolved_user_id)
        data_class = self._resolve_data_class(ctx)

        req = InternalRequest(
            request_id=uuid4(),
            user_id=resolved_user_id,
            trust_level=trust_level,
            protocol=protocol,
            query=query,
            data_class=data_class,
            context=ctx,
            timestamp=now,
            authenticated=True,
        )

        await self._mnemosyne.append(AuditEvent(
            event_type="auth",
            event_data={
                "user_id": resolved_user_id,
                "request_id": str(req.request_id),
                "result": "accepted",
                "trust_level": trust_level.name,
                "data_class": data_class.value,
                "protocol": protocol,
                "auth_method": "jwt" if token_user_id else "prefix_legacy",
            },
            source_module="HERMES",
            timestamp=now,
        ))

        _logger.info(
            "HERMES accepted request %s (user=%s trust=%s data_class=%s)",
            req.request_id, resolved_user_id, trust_level.name, data_class.value,
        )
        return req
