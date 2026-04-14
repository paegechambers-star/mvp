"""Tests for MNEMOSYNE — immutable audit log with SHA256 hash chaining."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from godai.models.audit import AuditEvent
from godai.modules.mnemosyne import GENESIS_HASH, Mnemosyne, TamperDetectedError


def _make_event(
    event_type: str = "auth",
    data: dict | None = None,  # type: ignore[type-arg]
    source: str = "HERMES",
) -> AuditEvent:
    return AuditEvent(
        event_type=event_type,
        event_data=data or {"key": "value"},
        source_module=source,
        timestamp=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_append_single_event_returns_entry() -> None:
    m = Mnemosyne()
    event = _make_event()
    entry = await m.append(event)

    assert entry.chain_index == 0
    assert entry.prev_hash == GENESIS_HASH
    assert len(entry.hash) == 64  # SHA256 hex digest
    assert entry.event_type == "auth"


@pytest.mark.asyncio
async def test_append_multiple_events_builds_chain() -> None:
    m = Mnemosyne()
    e1 = await m.append(_make_event("auth", source="HERMES"))
    e2 = await m.append(_make_event("policy_check", source="THEMIS"))
    e3 = await m.append(_make_event("routing", source="APOLLON"))

    assert e1.chain_index == 0
    assert e2.chain_index == 1
    assert e3.chain_index == 2

    assert e2.prev_hash == e1.hash
    assert e3.prev_hash == e2.hash


@pytest.mark.asyncio
async def test_verify_chain_intact() -> None:
    m = Mnemosyne()
    for i in range(5):
        await m.append(_make_event(data={"i": i}))

    assert m.verify_chain() is True


@pytest.mark.asyncio
async def test_verify_empty_chain() -> None:
    m = Mnemosyne()
    assert m.verify_chain() is True


@pytest.mark.asyncio
async def test_len_reflects_appended_entries() -> None:
    m = Mnemosyne()
    assert len(m) == 0
    await m.append(_make_event())
    assert len(m) == 1
    await m.append(_make_event())
    assert len(m) == 2


@pytest.mark.asyncio
async def test_entries_property_returns_copy() -> None:
    m = Mnemosyne()
    await m.append(_make_event())
    snapshot = m.entries
    assert len(snapshot) == 1
    # Modifying the snapshot must not affect the log
    snapshot.clear()
    assert len(m) == 1


# ---------------------------------------------------------------------------
# Tamper detection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_detects_hash_mutation() -> None:
    m = Mnemosyne()
    await m.append(_make_event(data={"x": 1}))
    await m.append(_make_event(data={"x": 2}))

    # Mutate the stored hash of entry 0
    m._entries[0] = m._entries[0].__class__(
        **{**m._entries[0].__dict__, "hash": "a" * 64}
    )

    with pytest.raises(TamperDetectedError):
        m.verify_chain()


@pytest.mark.asyncio
async def test_verify_detects_event_data_mutation() -> None:
    m = Mnemosyne()
    await m.append(_make_event(data={"secret": "original"}))

    # Mutate event_data in place — hash stays the same, recomputed hash differs
    m._entries[0].event_data["secret"] = "tampered"

    with pytest.raises(TamperDetectedError):
        m.verify_chain()


@pytest.mark.asyncio
async def test_verify_detects_prev_hash_mutation() -> None:
    m = Mnemosyne()
    await m.append(_make_event(data={"a": 1}))
    await m.append(_make_event(data={"b": 2}))

    # Corrupt the prev_hash back-pointer of entry 1
    entry1 = m._entries[1]
    m._entries[1] = entry1.__class__(
        **{**entry1.__dict__, "prev_hash": "b" * 64}
    )

    with pytest.raises(TamperDetectedError):
        m.verify_chain()


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_appends_maintain_chain_integrity() -> None:
    m = Mnemosyne()

    async def append_batch(n: int) -> None:
        for i in range(n):
            await m.append(_make_event(data={"n": i}))

    await asyncio.gather(append_batch(10), append_batch(10), append_batch(10))

    assert len(m) == 30
    assert m.verify_chain() is True


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_event_data_with_non_serialisable_values() -> None:
    """datetime values should be serialised via default=str without error."""
    m = Mnemosyne()
    event = AuditEvent(
        event_type="auth",
        event_data={"ts": datetime.now(timezone.utc), "uuid": "abc"},
        source_module="HERMES",
        timestamp=datetime.now(timezone.utc),
    )
    entry = await m.append(event)
    assert entry.hash  # must not raise


@pytest.mark.asyncio
async def test_invalid_source_module_raises() -> None:
    with pytest.raises(ValueError, match="source_module"):
        AuditEvent(
            event_type="auth",
            event_data={},
            source_module="UNKNOWN_MODULE",
            timestamp=datetime.now(timezone.utc),
        )
