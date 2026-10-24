"""Tests for DispatchBridge and CommandClassifier."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from godai.modules.command_classifier import CommandRisk, classify
from godai.modules.dispatch_bridge import CommandExpiredError, DispatchBridge
from godai.modules.mnemosyne import Mnemosyne


@pytest.fixture()
def bridge() -> DispatchBridge:
    return DispatchBridge(mnemosyne=Mnemosyne())


# ===========================================================================
# CommandClassifier
# ===========================================================================


def test_classify_read_commands():
    assert classify("show me the README") is CommandRisk.READ
    assert classify("list all Python files") is CommandRisk.READ
    assert classify("what does this function do?") is CommandRisk.READ
    assert classify("explain the pipeline") is CommandRisk.READ
    assert classify("status of the last deployment") is CommandRisk.READ


def test_classify_write_commands():
    assert classify("edit the README") is CommandRisk.WRITE
    assert classify("run pytest") is CommandRisk.WRITE
    assert classify("install requests") is CommandRisk.WRITE
    assert classify("git commit -m 'fix'") is CommandRisk.WRITE
    assert classify("delete the old log files") is CommandRisk.WRITE
    assert classify("curl https://example.com") is CommandRisk.WRITE
    assert classify("deploy to production") is CommandRisk.WRITE
    assert classify("create a new file called foo.py") is CommandRisk.WRITE
    assert classify("update the config") is CommandRisk.WRITE


def test_classify_is_case_insensitive():
    assert classify("EDIT the file") is CommandRisk.WRITE
    assert classify("Run tests") is CommandRisk.WRITE


# ===========================================================================
# Enqueue
# ===========================================================================


@pytest.mark.asyncio
async def test_enqueue_returns_command(bridge: DispatchBridge) -> None:
    cmd = await bridge.enqueue(user_id="alice", payload="show me the README")
    assert cmd.command_id is not None
    assert cmd.user_id == "alice"
    assert not cmd.completed


@pytest.mark.asyncio
async def test_enqueue_read_does_not_require_confirmation(bridge: DispatchBridge) -> None:
    cmd = await bridge.enqueue(user_id="alice", payload="list all files")
    assert cmd.requires_confirmation is False


@pytest.mark.asyncio
async def test_enqueue_write_requires_confirmation(bridge: DispatchBridge) -> None:
    cmd = await bridge.enqueue(user_id="alice", payload="edit config.yaml")
    assert cmd.requires_confirmation is True


@pytest.mark.asyncio
async def test_enqueue_sets_source(bridge: DispatchBridge) -> None:
    cmd = await bridge.enqueue(user_id="alice", payload="list files", source="mcp-chat")
    assert cmd.source == "mcp-chat"


@pytest.mark.asyncio
async def test_enqueue_stores_in_pending(bridge: DispatchBridge) -> None:
    await bridge.enqueue(user_id="alice", payload="check status")
    await bridge.enqueue(user_id="bob", payload="explain hermes.py")
    assert len(bridge.pending()) == 2


# ===========================================================================
# Complete
# ===========================================================================


@pytest.mark.asyncio
async def test_complete_marks_done(bridge: DispatchBridge) -> None:
    cmd = await bridge.enqueue(user_id="alice", payload="explain code")
    ok = await bridge.complete(cmd.command_id, result="Here is an explanation…", user_id="desktop")
    assert ok is True
    stored = bridge.get_result(cmd.command_id)
    assert stored.completed is True
    assert stored.result == "Here is an explanation…"


@pytest.mark.asyncio
async def test_complete_unknown_id_returns_false(bridge: DispatchBridge) -> None:
    ok = await bridge.complete(uuid4(), result="x", user_id="desktop")
    assert ok is False


@pytest.mark.asyncio
async def test_completed_removed_from_pending(bridge: DispatchBridge) -> None:
    cmd = await bridge.enqueue(user_id="alice", payload="check health")
    await bridge.complete(cmd.command_id, result="ok", user_id="desktop")
    assert bridge.pending() == []


# ===========================================================================
# Expiry — clear error signals
# ===========================================================================


@pytest.mark.asyncio
async def test_expired_command_not_in_pending(bridge: DispatchBridge) -> None:
    await bridge.enqueue(user_id="alice", payload="stale task", ttl_seconds=0)
    assert bridge.pending() == []


@pytest.mark.asyncio
async def test_expired_command_raises_clear_error(bridge: DispatchBridge) -> None:
    cmd = await bridge.enqueue(user_id="alice", payload="stale task", ttl_seconds=0)
    with pytest.raises(CommandExpiredError) as exc_info:
        bridge.get_result(cmd.command_id)
    assert cmd.command_id == exc_info.value.command_id


@pytest.mark.asyncio
async def test_never_seen_command_raises_key_error(bridge: DispatchBridge) -> None:
    with pytest.raises(KeyError):
        bridge.get_result(uuid4())


# ===========================================================================
# Wait-for-command
# ===========================================================================


@pytest.mark.asyncio
async def test_wait_returns_immediately_if_pending(bridge: DispatchBridge) -> None:
    await bridge.enqueue(user_id="alice", payload="show README")
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


# ===========================================================================
# to_dict includes new fields
# ===========================================================================


@pytest.mark.asyncio
async def test_to_dict_includes_requires_confirmation(bridge: DispatchBridge) -> None:
    cmd = await bridge.enqueue(user_id="alice", payload="run tests")
    d = cmd.to_dict()
    assert "requires_confirmation" in d
    assert d["requires_confirmation"] is True


@pytest.mark.asyncio
async def test_to_dict_includes_source(bridge: DispatchBridge) -> None:
    cmd = await bridge.enqueue(user_id="alice", payload="list files", source="web-chat")
    assert cmd.to_dict()["source"] == "web-chat"
