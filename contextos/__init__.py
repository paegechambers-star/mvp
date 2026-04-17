"""
ContextOS™ — Deterministic knowledge-governance layer for FraPP.

Public API surface::

    from contextos import (
        Register, ContextOSLog, ContextOSIndex,
        Resolver, MKIDRunner,
        generate_id, validate_id, parse_id,
        SSOTEntry, WorkEntry, CommitBlock,
        Kind, Actor, Cluster, EntryType, TruthGate, CommitOp, Citation,
    )

All other symbols are internal implementation details.
"""

from contextos.commit import (
    deprecate_commit,
    make_commit,
    patch_commit,
    promote_commit,
    supersede_commit,
)
from contextos.id_generator import (
    compute_checksum,
    decode_b36,
    encode_b36,
    encode_time_bucket,
    generate_id,
    next_sequence,
    parse_id,
    validate_id,
)
from contextos.index import ContextOSIndex
from contextos.log import ContextOSLog, LogEntry, TamperDetectedError
from contextos.mkid_runner import MKIDRunner
from contextos.register import Register
from contextos.resolver import QueryResult, Resolver
from contextos.store import blob_exists, read_blob, sha256_of, write_blob
from contextos.types import (
    BASE36,
    Actor,
    Citation,
    Cluster,
    CommitBlock,
    CommitOp,
    ContextID,
    EntryType,
    Kind,
    SSOTEntry,
    TruthGate,
    WorkEntry,
)

__all__ = [
    # Types
    "BASE36",
    "Kind", "Actor", "Cluster", "EntryType", "TruthGate", "CommitOp",
    "ContextID", "Citation", "SSOTEntry", "WorkEntry", "CommitBlock",
    # ID generator
    "generate_id", "validate_id", "parse_id", "compute_checksum",
    "encode_b36", "decode_b36", "encode_time_bucket", "next_sequence",
    # Store
    "write_blob", "read_blob", "sha256_of", "blob_exists",
    # Log
    "ContextOSLog", "LogEntry", "TamperDetectedError",
    # Commit
    "make_commit", "patch_commit", "supersede_commit", "promote_commit", "deprecate_commit",
    # Register
    "Register",
    # Index
    "ContextOSIndex",
    # Resolver
    "Resolver", "QueryResult",
    # Runner
    "MKIDRunner",
]
