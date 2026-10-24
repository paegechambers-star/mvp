"""Tests for contextos/commit.py — 7 tests."""

from __future__ import annotations

import pytest

from contextos.commit import (
    deprecate_commit,
    make_commit,
    patch_commit,
    promote_commit,
    supersede_commit,
)
from contextos.types import Actor, CommitBlock, CommitOp


def test_make_commit_returns_frozen_commitblock():
    cb = make_commit(
        operation=CommitOp.PATCH,
        target_id="NK00000000000000",
        actor=Actor.USER,
        new_content_hash="a" * 64,
    )
    assert isinstance(cb, CommitBlock)
    # CommitBlock is frozen — cannot assign
    with pytest.raises(Exception):
        cb.operation = CommitOp.SUPERSEDE  # type: ignore[misc]


def test_commit_block_delta_dict():
    cb = make_commit(
        operation=CommitOp.PATCH,
        target_id="NK00000000000000",
        actor=Actor.USER,
        new_content_hash="a" * 64,
        delta={"key": "value"},
    )
    assert cb.delta_dict == {"key": "value"}


def test_patch_commit_operation():
    cb = patch_commit("NK00000000000000", Actor.USER, "a" * 64, "b" * 64)
    assert cb.operation == CommitOp.PATCH
    assert cb.prev_content_hash == "a" * 64
    assert cb.new_content_hash == "b" * 64


def test_supersede_commit_operation():
    cb = supersede_commit("NK00000000000001", "NK00000000000002", Actor.ADMIN, "a" * 64, "b" * 64)
    assert cb.operation == CommitOp.SUPERSEDE
    assert cb.delta_dict["supersedes"] == "NK00000000000001"


def test_promote_commit_operation():
    cb = promote_commit("MK00000000000000", "NK00000000000000", Actor.USER, "c" * 64)
    assert cb.operation == CommitOp.PROMOTE
    assert cb.delta_dict["promoted_from"] == "MK00000000000000"


def test_deprecate_commit_operation():
    cb = deprecate_commit("NK00000000000000", Actor.ADMIN, "d" * 64, reason="outdated")
    assert cb.operation == CommitOp.DEPRECATE
    assert cb.delta_dict["reason"] == "outdated"


def test_commit_id_is_unique():
    a = make_commit(CommitOp.PATCH, "NK00000000000000", Actor.USER, "a" * 64)
    b = make_commit(CommitOp.PATCH, "NK00000000000000", Actor.USER, "a" * 64)
    assert a.commit_id != b.commit_id
