"""
HTTP-level rate limiting for FraPP API.

Uses slowapi with Redis storage when REDIS_URL is configured, falls back to
in-memory storage for single-process / dev environments.

Apply via the @limiter.limit() decorator on FastAPI route handlers, or use
`limit_middleware` as a starlette middleware.

Limits:
  - /v1/godai/query  : 100 requests / minute per API key
  - general endpoints: 300 requests / minute per IP
"""
from __future__ import annotations

import logging
from typing import Callable

from fastapi import Request

_logger = logging.getLogger("frapp.rate_limiter")

# ── Lazy initialisation so settings are resolved at import time ─────────────

_limiter = None


def get_limiter():
    global _limiter
    if _limiter is not None:
        return _limiter

    try:
        from slowapi import Limiter  # type: ignore[import]
        from frapp.settings import settings

        storage_uri = settings.redis_url if settings.redis_url else "memory://"

        def _key_from_api_key(request: Request) -> str:
            key = request.headers.get("X-API-Key") or request.client.host
            return key

        _limiter = Limiter(key_func=_key_from_api_key, storage_uri=storage_uri)
        backend = "Redis" if settings.redis_url else "in-memory"
        _logger.info("Rate limiter initialised (%s backend)", backend)
        return _limiter

    except ImportError:
        _logger.warning(
            "slowapi not installed — rate limiting disabled. "
            "Install with: pip install slowapi redis"
        )
        return None


def rate_limit(limit_string: str) -> Callable:
    """Decorator factory — returns the slowapi limit decorator or a no-op."""
    lim = get_limiter()
    if lim is not None:
        return lim.limit(limit_string)
    # No-op decorator when slowapi is not installed
    def _noop(fn: Callable) -> Callable:
        return fn
    return _noop
