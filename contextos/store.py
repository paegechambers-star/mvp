"""
ContextOS™ content-addressable blob store.

Blobs are stored under:
  <base_dir>/store/<sha256[:2]>/<sha256[2:]>

This is identical to Git's object store layout.  Reading a blob by its hash
is an O(1) filesystem lookup.  Writing the same content twice is idempotent.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


_DEFAULT_BASE: Path = Path.home() / ".frapp" / "contextos"


def _store_root(base_dir: Path) -> Path:
    return base_dir / "store"


def sha256_of(content: str) -> str:
    """Return the SHA256 hex digest of *content* (UTF-8 encoded)."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def write_blob(content: str, base_dir: Path = _DEFAULT_BASE) -> str:
    """
    Write *content* to the store.

    Returns the SHA256 hex digest (content address).
    Idempotent: writing the same content twice leaves one file on disk.
    """
    digest = sha256_of(content)
    prefix, rest = digest[:2], digest[2:]
    dest = _store_root(base_dir) / prefix / rest
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
    return digest


def read_blob(digest: str, base_dir: Path = _DEFAULT_BASE) -> str:
    """
    Read a blob by its SHA256 hex digest.

    Raises :exc:`KeyError` if the blob is not in the store.
    """
    prefix, rest = digest[:2], digest[2:]
    dest = _store_root(base_dir) / prefix / rest
    if not dest.exists():
        raise KeyError(f"Blob not found in store: {digest}")
    return dest.read_text(encoding="utf-8")


def blob_exists(digest: str, base_dir: Path = _DEFAULT_BASE) -> bool:
    """Return True if a blob with the given digest exists in the store."""
    prefix, rest = digest[:2], digest[2:]
    return (_store_root(base_dir) / prefix / rest).exists()
