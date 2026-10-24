"""
HTTP-level rate limiting for FraPP API.

Slowapi with Redis when REDIS_URL is set, in-memory otherwise.
The module-level `limiter` object is the singleton — import it directly.

Register with FastAPI app:
    from frapp.rate_limiter import limiter, rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

Then decorate endpoints:
    @router.post("/query")
    @limiter.limit("100/minute")
    async def query(request: Request, ...):
        ...
"""
from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

_logger = logging.getLogger("frapp.rate_limiter")


def _build_limiter():
    try:
        from slowapi import Limiter  # type: ignore[import]
        from frapp.settings import settings

        def _key_from_api_key(request: Request) -> str:
            return request.headers.get("X-API-Key") or (request.client.host if request.client else "unknown")

        storage_uri = settings.redis_url if settings.redis_url else "memory://"
        lim = Limiter(key_func=_key_from_api_key, storage_uri=storage_uri)
        backend = "Redis" if settings.redis_url else "in-memory"
        _logger.info("Rate limiter initialised (%s)", backend)
        return lim
    except ImportError:
        return None


limiter = _build_limiter()


async def rate_limit_exceeded_handler(request: Request, exc) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "type": "https://httpstatuses.com/429",
            "title": "Too Many Requests",
            "status": 429,
            "detail": "Rate limit exceeded. Slow down and retry.",
        },
    )
