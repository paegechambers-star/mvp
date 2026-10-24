"""Tests for contextos/store.py — 6 tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from contextos.store import blob_exists, read_blob, sha256_of, write_blob


def test_write_and_read(tmp_path: Path):
    content = "hello ContextOS"
    digest = write_blob(content, base_dir=tmp_path)
    assert read_blob(digest, base_dir=tmp_path) == content


def test_content_addressable(tmp_path: Path):
    c1 = "alpha"
    c2 = "beta"
    d1 = write_blob(c1, base_dir=tmp_path)
    d2 = write_blob(c2, base_dir=tmp_path)
    assert d1 != d2


def test_write_idempotent(tmp_path: Path):
    content = "idempotent content"
    d1 = write_blob(content, base_dir=tmp_path)
    d2 = write_blob(content, base_dir=tmp_path)
    assert d1 == d2  # same hash
    # Only one file on disk
    prefix, rest = d1[:2], d1[2:]
    assert (tmp_path / "store" / prefix / rest).is_file()


def test_read_missing_raises(tmp_path: Path):
    with pytest.raises(KeyError):
        read_blob("a" * 64, base_dir=tmp_path)


def test_blob_exists(tmp_path: Path):
    content = "exists check"
    digest = write_blob(content, base_dir=tmp_path)
    assert blob_exists(digest, base_dir=tmp_path) is True
    assert blob_exists("b" * 64, base_dir=tmp_path) is False


def test_sha256_of_deterministic():
    assert sha256_of("same") == sha256_of("same")
    assert sha256_of("a") != sha256_of("b")
    assert len(sha256_of("anything")) == 64
