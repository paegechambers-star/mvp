"""
ContextOS™ → G.O.D.A.I. MNEMOSYNE bridge.

This is the ONLY file in the contextos/ package that imports from godai/.
All other contextos modules must not touch godai directly.

Design:
  - G.O.D.A.I. MNEMOSYNE.append() is an asyncio coroutine.
  - ContextOS is synchronous.
  - Bridge: a dedicated background event-loop thread processes MNEMOSYNE calls.
  - Fail-closed: if MNEMOSYNE is unreachable (timeout or exception), the
    caller receives a RuntimeError and the originating write is aborted.

source_module workaround:
  VALID_SOURCE_MODULES in godai does not include "CONTEXTOS".
  We use source_module="PIPELINE" with event_data["contextos_source"]="CONTEXTOS"
  so all ContextOS events are distinguishable in the audit trail.
"""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

_loop: Optional[asyncio.AbstractEventLoop] = None
_thread: Optional[threading.Thread] = None
_lock: threading.Lock = threading.Lock()

_DEFAULT_TIMEOUT: float = 2.0


def _get_loop() -> asyncio.AbstractEventLoop:
    """Return (and lazily create) the shared background event loop."""
    global _loop, _thread
    with _lock:
        if _loop is None or _loop.is_closed():
            _loop = asyncio.new_event_loop()
            _thread = threading.Thread(
                target=_loop.run_forever,
                daemon=True,
                name="contextos-godai-bridge",
            )
            _thread.start()
    return _loop


def audit_to_mnemosyne(
    mnemosyne: Any,
    event_type: str,
    event_data: Dict[str, Any],
    timeout: float = _DEFAULT_TIMEOUT,
) -> None:
    """
    Synchronously emit one AuditEvent to G.O.D.A.I. MNEMOSYNE.

    Args:
        mnemosyne:  A :class:`godai.modules.mnemosyne.Mnemosyne` instance.
        event_type: Event type string (e.g. "contextos_write", "contextos_promote").
        event_data: Arbitrary payload.  Will be enriched with ``contextos_source``.
        timeout:    Seconds to wait before raising RuntimeError (fail-closed).

    Raises:
        RuntimeError: If MNEMOSYNE does not respond within *timeout* seconds,
                      or if it raises any exception.  Callers MUST abort the
                      originating write on RuntimeError.
    """
    from godai.models.audit import AuditEvent  # deferred import — single bridge point

    enriched = {"contextos_source": "CONTEXTOS", **event_data}
    event = AuditEvent(
        event_type=event_type,
        event_data=enriched,
        source_module="PIPELINE",
        timestamp=datetime.now(timezone.utc),
    )

    loop = _get_loop()
    future = asyncio.run_coroutine_threadsafe(mnemosyne.append(event), loop)
    try:
        future.result(timeout=timeout)
    except TimeoutError as exc:
        raise RuntimeError(
            f"MNEMOSYNE audit timed out after {timeout}s (fail-closed)"
        ) from exc
    except Exception as exc:
        raise RuntimeError(
            f"MNEMOSYNE audit failed (fail-closed): {exc}"
        ) from exc


def shutdown_bridge() -> None:
    """Stop the background event-loop thread.  Call during application teardown."""
    global _loop, _thread
    with _lock:
        if _loop is not None and not _loop.is_closed():
            _loop.call_soon_threadsafe(_loop.stop)
            if _thread is not None:
                _thread.join(timeout=3.0)
            _loop = None
            _thread = None
