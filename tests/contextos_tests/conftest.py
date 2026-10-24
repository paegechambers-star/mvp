"""
Shared fixtures for ContextOS tests.

All tests use temporary directories — nothing touches ~/.frapp in CI.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from contextos.id_generator import generate_id
from contextos.index import ContextOSIndex
from contextos.log import ContextOSLog
from contextos.register import Register
from contextos.resolver import Resolver
from contextos.store import sha256_of
from contextos.types import (
    Actor,
    Citation,
    Cluster,
    EntryType,
    Kind,
    SSOTEntry,
    TruthGate,
    WorkEntry,
)


@pytest.fixture()
def tmp_base(tmp_path: Path) -> Path:
    """A temporary base directory that mimics ~/.frapp/contextos."""
    base = tmp_path / "contextos"
    base.mkdir()
    return base


@pytest.fixture()
def db_path(tmp_base: Path) -> Path:
    return tmp_base / "contextos.db"


@pytest.fixture()
def seq_db(tmp_base: Path) -> Path:
    return tmp_base / "seq.db"


@pytest.fixture()
def cos_log(db_path: Path) -> ContextOSLog:
    return ContextOSLog(db_path)


@pytest.fixture()
def register(db_path: Path, cos_log: ContextOSLog) -> Register:
    return Register(db_path, cos_log)


@pytest.fixture()
def index(tmp_base: Path) -> ContextOSIndex:
    return ContextOSIndex(index_path=tmp_base / "index.json")


@pytest.fixture()
def resolver(register: Register, index: ContextOSIndex) -> Resolver:
    return Resolver(register, index)


# ─────────────────────────────── Factories ───────────────────────────────────

def make_nkid(seq: int = 0, seq_db: Path = None, **kwargs) -> str:  # type: ignore[assignment]
    defaults = dict(
        kind=Kind.NK,
        actor=Actor.USER,
        cluster=Cluster.GENERAL,
        entry_type=EntryType.FACT,
        truth_gate=TruthGate.UNVERIFIED,
        time_bucket="00",
        sequence=seq,
    )
    defaults.update(kwargs)
    return generate_id(**defaults)


def make_mkid(seq: int = 0, **kwargs) -> str:
    defaults = dict(
        kind=Kind.MK,
        actor=Actor.USER,
        cluster=Cluster.GENERAL,
        entry_type=EntryType.ANNOTATION,
        truth_gate=TruthGate.UNVERIFIED,
        time_bucket="00",
        sequence=seq,
    )
    defaults.update(kwargs)
    return generate_id(**defaults)


def make_ssot(
    nkid: str,
    content: str = "test content",
    truth_gate: TruthGate = TruthGate.UNVERIFIED,
    citations: tuple = (),
    cluster: Cluster = Cluster.GENERAL,
    actor: Actor = Actor.USER,
) -> SSOTEntry:
    now = datetime.now(timezone.utc)
    return SSOTEntry(
        nkid=nkid,
        content=content,
        truth_gate=truth_gate,
        citations=citations,
        content_hash=sha256_of(content),
        created_at=now,
        cluster=cluster,
        actor=actor,
    )


def make_work(
    mkid: str,
    content: str = "draft content",
    truth_gate: TruthGate = TruthGate.UNVERIFIED,
    citations: list = None,  # type: ignore[assignment]
    cluster: Cluster = Cluster.GENERAL,
    actor: Actor = Actor.USER,
) -> WorkEntry:
    now = datetime.now(timezone.utc)
    return WorkEntry(
        mkid=mkid,
        content=content,
        truth_gate=truth_gate,
        citations=citations or [],
        content_hash=sha256_of(content),
        created_at=now,
        modified_at=now,
        cluster=cluster,
        actor=actor,
    )
