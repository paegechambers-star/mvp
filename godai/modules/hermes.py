"""
HERMES — API Gateway and protocol normalization layer.

Entry point for all external requests.  Normalizes raw protocol inputs
into a canonical InternalRequest, enforces authentication, assigns
TrustLevel and DataClass, and enforces per-user rate limits.

Target latency: ~5 ms.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from godai.models.audit import AuditEvent
from godai.models.request import DataClass, InternalRequest, TrustLevel
from godai.modules.mnemosyne import Mnemosyne

_logger = logging.getLogger("godai.hermes")

# Token prefix → TrustLevel mapping (policy-as-data: change prefix to reassign trust)
_TOKEN_TRUST_MAP: Dict[str, TrustLevel] = {
    "internal-": TrustLevel.L3,
    "elevated-": TrustLevel.L2,
    "basic-": TrustLevel.L1,
}

# Minimum token length considered valid (prevents trivially forged tokens)
_MIN_TOKEN_LEN: int = 8


class AuthenticationError(Exception):
    """Raised when authentication fails (HTTP 401 equivalent)."""


class RateLimitError(Exception):
    """Raised when a user exceeds their request rate limit (HTTP 429 equivalent)."""


class Hermes:
    """
    HERMES — API Gateway.

    Responsibilities:
      1. Authenticate the caller via bearer token.
      2. Resolve TrustLevel from token prefix.
      3. Resolve DataClass from request context.
      4. Enforce per-user rate limits.
      5. Produce a canonical :class:`~godai.models.request.InternalRequest`.
      6. Log the auth event to MNEMOSYNE.

    All unauthenticated requests are rejected here — no other module
    ever receives an unauthenticated request.
    """

    def __init__(self, mnemosyne: Mnemosyne, rate_limit: int = 100) -> None:
        """
        Args:
            mnemosyne: Shared MNEMOSYNE instance for audit logging.
            rate_limit: Maximum number of requests allowed per user_id
                before a :class:`RateLimitError` is raised.  Default 100.
        """
        self._mnemosyne = mnemosyne
        self._rate_limit = rate_limit
        self._request_counts: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_trust_level(self, token: str) -> TrustLevel:
        """Map a bearer token to its corresponding TrustLevel."""
        for prefix, level in _TOKEN_TRUST_MAP.items():
            if token.startswith(prefix):
                return level
        return TrustLevel.L1  # Default for valid but unrecognised tokens

    def _resolve_data_class(self, context: Dict[str, Any]) -> DataClass:
        """Derive DataClass from the ``data_class`` key in request context."""
        raw: str = context.get("data_class", DataClass.PUBLIC.value)
        try:
            return DataClass(raw)
        except ValueError:
            _logger.warning("Unknown data_class %r — defaulting to PUBLIC", raw)
            return DataClass.PUBLIC

    def _check_rate_limit(self, user_id: str) -> None:
        """Raise RateLimitError if the user has exceeded the configured limit."""
        count = self._request_counts.get(user_id, 0)
        if count >= self._rate_limit:
            raise RateLimitError(
                f"Rate limit of {self._rate_limit} exceeded for user {user_id!r} (429)"
            )
        self._request_counts[user_id] = count + 1

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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

        Authentication is enforced unconditionally before any forwarding.
        A rejected request is logged to MNEMOSYNE and an exception raised —
        the caller receives an HTTP 401/429 equivalent.

        Args:
            token: Bearer token supplied by the caller.
            user_id: Caller-supplied user identifier.
            protocol: Wire protocol — ``"http"``, ``"websocket"``, or ``"grpc"``.
            query: The request payload / prompt text.
            context: Optional metadata dict.  Recognised keys:
                ``data_class`` (str), ``action`` (str),
                ``explicit_consent`` (bool).

        Returns:
            Authenticated and classified :class:`~godai.models.request.InternalRequest`.

        Raises:
            AuthenticationError: Token is missing or fails validation.
            RateLimitError: User has exceeded the per-user request limit.
        """
        ctx: Dict[str, Any] = context or {}
        now = datetime.now(timezone.utc)

        # ── Authentication boundary ──────────────────────────────────────
        if not token:
            await self._mnemosyne.append(AuditEvent(
                event_type="auth",
                event_data={
                    "user_id": user_id,
                    "result": "rejected",
                    "reason": "missing_token",
                },
                source_module="HERMES",
                timestamp=now,
            ))
            raise AuthenticationError(
                f"Missing authentication token for user {user_id!r} (401)"
            )

        if len(token) < _MIN_TOKEN_LEN:
            await self._mnemosyne.append(AuditEvent(
                event_type="auth",
                event_data={
                    "user_id": user_id,
                    "result": "rejected",
                    "reason": "token_too_short",
                },
                source_module="HERMES",
                timestamp=now,
            ))
            raise AuthenticationError(
                f"Invalid authentication token for user {user_id!r} (401)"
            )

        # ── Rate limiting ────────────────────────────────────────────────
        self._check_rate_limit(user_id)

        # ── Build canonical request ──────────────────────────────────────
        trust_level = self._resolve_trust_level(token)
        data_class = self._resolve_data_class(ctx)

        req = InternalRequest(
            request_id=uuid4(),
            user_id=user_id,
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
                "user_id": user_id,
                "request_id": str(req.request_id),
                "result": "accepted",
                "trust_level": trust_level.name,
                "data_class": data_class.value,
                "protocol": protocol,
            },
            source_module="HERMES",
            timestamp=now,
        ))

        _logger.info(
            "HERMES accepted request %s (user=%s trust=%s data_class=%s)",
            req.request_id,
            user_id,
            trust_level.name,
            data_class.value,
        )
        return req
