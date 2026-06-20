"""Tests for DispatchBridge — mobile-to-desktop async message queue."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from godai.modules.dispatch_bridge import DEFAULT_TTL_SECONDS, DispatchBridge
from godai.modules.mnemosyne import Mnemosyne


@pytest.fixture()
def bridge() -> DispatchBridge:
    return DispatchBridge(mnemosyne=Mnemosyne())


# ---------------------------------------------------------------------------
# Enqueue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enqueue_returns_command(bridge: DispatchBridge) -> None:
    cmd = await bridge.enqueue(user_id="alice", payload="run tests")
    assert cmd.command_id is not None
    assert cmd.user_id == "alice"
    assert cmd.payload == "run tests"
    assert not cmd.completed


@pytest.mark.asyncio
async def test_enqueue_stores_in_pending(bridge: DispatchBridge) -> None:
    await bridge.enqueue(user_id="alice", payload="task A")
    await bridge.enqueue(user_id="bob", payload="task B")
    pending = bridge.pending()
    assert len(pending) == 2
    payloads = {c.payload for c in pending}
    assert payloads == {"task A", "task B"}


@pytest.mark.asyncio
async def test_enqueue_passes_context(bridge: DispatchBridge) -> None:
    ctx = {"priority": "high", "source": "ios"}
    cmd = await bridge.enqueue(user_id="alice", payload="deploy", context=ctx)
    assert cmd.context == ctx


# ---------------------------------------------------------------------------
# Complete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_marks_done(bridge: DispatchBridge) -> None:
    cmd = await bridge.enqueue(user_id="alice", payload="build")
    ok = await bridge.complete(cmd.command_id, result="success", user_id="desktop")
    assert ok is True
    stored = bridge.get_result(cmd.command_id)
    assert stored is not None
    assert stored.completed is True
    assert stored.result == "success"


@pytest.mark.asyncio
async def test_complete_unknown_id_returns_false(bridge: DispatchBridge) -> None:
    ok = await bridge.complete(uuid4(), result="x", user_id="desktop")
    assert ok is False


@pytest.mark.asyncio
async def test_completed_removed_from_pending(bridge: DispatchBridge) -> None:
    cmd = await bridge.enqueue(user_id="alice", payload="anything")
    await bridge.complete(cmd.command_id, result="done", user_id="desktop")
    assert bridge.pending() == []


# ---------------------------------------------------------------------------
# Expiry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expired_command_not_in_pending(bridge: DispatchBridge) -> None:
    cmd = await bridge.enqueue(user_id="alice", payload="stale", ttl_seconds=0)
    # ttl=0 means it expires immediately
    assert bridge.pending() == []


@pytest.mark.asyncio
async def test_expired_command_not_returned_by_get_result(bridge: DispatchBridge) -> None:
    cmd = await bridge.enqueue(user_id="alice", payload="stale", ttl_seconds=0)
    result = bridge.get_result(cmd.command_id)
    assert result is None


# ---------------------------------------------------------------------------
# Wait-for-command
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wait_returns_immediately_if_pending(bridge: DispatchBridge) -> None:
    await bridge.enqueue(user_id="alice", payload="immediate")
    cmds = await bridge.wait_for_command(timeout=1.0)
    assert len(cmds) == 1


@pytest.mark.asyncio
async def test_wait_times_out_with_empty_queue(bridge: DispatchBridge) -> None:
    cmds = await bridge.wait_for_command(timeout=0.05)
    assert cmds == []


@pytest.mark.asyncio
async def test_wait_wakes_on_enqueue(bridge: DispatchBridge) -> None:
    async def _late_enqueue():
        await asyncio.sleep(0.05)
        await bridge.enqueue(user_id="alice", payload="wake-me")

    asyncio.create_task(_late_enqueue())
    cmds = await bridge.wait_for_command(timeout=2.0)
    assert len(cmds) == 1
    assert cmds[0].payload == "wake-me"
