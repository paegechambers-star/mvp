"""Tests for contextos/godai_audit.py — 4 tests."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, AsyncMock

import pytest

from contextos.godai_audit import audit_to_mnemosyne, shutdown_bridge


def _make_mnemosyne(delay: float = 0.0, fail: bool = False):
    """Build a minimal Mnemosyne mock."""
    m = MagicMock()
    if fail:
        async def _bad(*a, **kw):
            raise RuntimeError("MNEMOSYNE down")
        m.append = _bad
    else:
        async def _ok(*a, **kw):
            await asyncio.sleep(delay)
            return MagicMock()
        m.append = _ok
    return m


def test_audit_event_emitted_successfully():
    mnemosyne = _make_mnemosyne()
    # Should not raise
    audit_to_mnemosyne(mnemosyne, "contextos_write", {"target_id": "NK00000000000000"})


def test_audit_enriches_event_data():
    """Verify that contextos_source is injected into event_data."""
    captured = {}

    async def _capture(event):
        captured["data"] = event.event_data
        captured["source"] = event.source_module
        return MagicMock()

    mnemosyne = MagicMock()
    mnemosyne.append = _capture

    audit_to_mnemosyne(mnemosyne, "test_event", {"key": "val"})
    assert captured["data"]["contextos_source"] == "CONTEXTOS"
    assert captured["source"] == "PIPELINE"


def test_audit_uses_pipeline_source_module():
    """source_module must always be PIPELINE (workaround for VALID_SOURCE_MODULES)."""
    captured = {}

    async def _cap(event):
        captured["source"] = event.source_module
        return MagicMock()

    mnemosyne = MagicMock()
    mnemosyne.append = _cap
    audit_to_mnemosyne(mnemosyne, "contextos_promote", {})
    assert captured["source"] == "PIPELINE"


def test_fail_closed_on_exception():
    """If MNEMOSYNE raises, audit_to_mnemosyne must propagate a RuntimeError."""
    mnemosyne = _make_mnemosyne(fail=True)
    with pytest.raises(RuntimeError, match="fail-closed"):
        audit_to_mnemosyne(mnemosyne, "contextos_write", {})


def test_shutdown_bridge_is_safe_to_call_multiple_times():
    shutdown_bridge()
    shutdown_bridge()   # must not raise
