"""
ContextOS™ ID generator.

Produces deterministic 16-char IDs in the format:
  [kind 2][actor 2][cluster 2][entry_type 2][truth_gate 2][time_bucket 2][sequence 2][checksum 2]

All characters are drawn from BASE36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ".
The checksum is a polynomial hash over the first 14 characters, yielding
a 2-char base36 suffix that detects any single-character corruption.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from contextos.types import (
    BASE36,
    Actor,
    Cluster,
    ContextID,
    EntryType,
    Kind,
    TruthGate,
)

# Epoch for time_bucket calculation (2024-01-01 00:00:00 UTC)
_EPOCH_TS: float = datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp()

# Time-bucket granularity: 1 hour = 3600 s
_BUCKET_SECONDS: int = 3600

# Modulus for 2-char base36 values: 36² = 1296
_MOD: int = 1296


# ─────────────────────────────── Codec ───────────────────────────────────────


def encode_b36(n: int, width: int = 2) -> str:
    """Encode a non-negative integer as a base36 string of exactly *width* chars."""
    if n < 0:
        raise ValueError(f"encode_b36: negative value {n}")
    result: list[str] = []
    for _ in range(width):
        result.append(BASE36[n % 36])
        n //= 36
    if n:
        raise ValueError(f"encode_b36: value too large for width={width}")
    return "".join(reversed(result))


def decode_b36(s: str) -> int:
    """Decode a base36 string to an integer."""
    s = s.upper()
    result = 0
    for c in s:
        if c not in BASE36:
            raise ValueError(f"decode_b36: invalid character {c!r}")
        result = result * 36 + BASE36.index(c)
    return result


# ─────────────────────────────── Checksum ────────────────────────────────────


def compute_checksum(prefix14: str) -> str:
    """
    Polynomial hash of the first 14 characters, returned as 2 base36 chars.

    Algorithm: v = 0; for each char c: v = (v*36 + index(c)) mod 1296
    Then encode v as a 2-char base36 string.
    """
    if len(prefix14) != 14:
        raise ValueError(f"compute_checksum expects 14 chars, got {len(prefix14)}")
    v = 0
    for c in prefix14.upper():
        if c not in BASE36:
            raise ValueError(f"compute_checksum: invalid char {c!r}")
        v = (v * 36 + BASE36.index(c)) % _MOD
    return encode_b36(v, 2)


# ─────────────────────────────── Validation ──────────────────────────────────


def validate_id(id_str: str) -> bool:
    """Return True if *id_str* is a well-formed 16-char ContextOS ID."""
    if not isinstance(id_str, str) or len(id_str) != 16:
        return False
    id_str = id_str.upper()
    for c in id_str:
        if c not in BASE36:
            return False
    try:
        expected = compute_checksum(id_str[:14])
    except ValueError:
        return False
    return id_str[14:] == expected


def parse_id(id_str: str) -> ContextID:
    """
    Parse a 16-char ContextOS ID into a :class:`ContextID`.

    Raises :exc:`ValueError` if the ID is invalid.
    """
    if not validate_id(id_str):
        raise ValueError(f"Invalid ContextOS ID: {id_str!r}")
    s = id_str.upper()
    return ContextID(
        raw=s,
        kind=Kind(s[0:2]),
        actor=Actor(s[2:4]),
        cluster=Cluster(s[4:6]),
        entry_type=EntryType(s[6:8]),
        truth_gate=TruthGate(s[8:10]),
        time_bucket=decode_b36(s[10:12]),
        sequence=decode_b36(s[12:14]),
        checksum=s[14:16],
    )


# ─────────────────────────────── Time bucket ─────────────────────────────────


def encode_time_bucket(ts: Optional[datetime] = None) -> str:
    """Encode a datetime into a 2-char base36 time-bucket string."""
    if ts is None:
        ts = datetime.now(timezone.utc)
    elapsed = max(0, int(ts.timestamp() - _EPOCH_TS))
    bucket = (elapsed // _BUCKET_SECONDS) % _MOD
    return encode_b36(bucket, 2)


# ─────────────────────────────── Sequence counter ────────────────────────────


def next_sequence(db_path: Path) -> int:
    """
    Return the next sequence value (0–1295) from a SQLite counter.

    Creates the database and table if they don't exist.  Thread-safe via
    SQLite's exclusive transaction.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), isolation_level="EXCLUSIVE")
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS _seq (val INTEGER NOT NULL DEFAULT 0)"
        )
        row = conn.execute("SELECT val FROM _seq").fetchone()
        if row is None:
            conn.execute("INSERT INTO _seq VALUES (0)")
            val = 0
        else:
            val = (row[0] + 1) % _MOD
            conn.execute("UPDATE _seq SET val = ?", (val,))
        conn.commit()
        return val
    finally:
        conn.close()


# ─────────────────────────────── ID generation ───────────────────────────────


def generate_id(
    kind: Kind,
    actor: Actor,
    cluster: Cluster,
    entry_type: EntryType,
    truth_gate: TruthGate,
    *,
    time_bucket: Optional[str] = None,
    sequence: Optional[int] = None,
    db_path: Optional[Path] = None,
) -> str:
    """
    Generate a valid 16-char ContextOS ID.

    Pass *time_bucket* and *sequence* explicitly in tests for determinism.
    In production, *time_bucket* defaults to the current UTC hour bucket and
    *sequence* is read from the SQLite counter at *db_path*.
    """
    tb = time_bucket if time_bucket is not None else encode_time_bucket()

    if sequence is None:
        if db_path is None:
            db_path = Path.home() / ".frapp" / "contextos" / "seq.db"
        sequence = next_sequence(db_path)

    seq_str = encode_b36(sequence % _MOD, 2)
    prefix = f"{kind.value}{actor.value}{cluster.value}{entry_type.value}{truth_gate.value}{tb}{seq_str}"
    assert len(prefix) == 14, f"BUG: prefix len={len(prefix)}"
    return prefix + compute_checksum(prefix)
