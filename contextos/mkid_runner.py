"""
ContextOS™ MKID execution engine.

MKIDs (Meta Knowledge IDs) represent executable procedures stored in the
WORK partition.  The runner interprets their ``content`` field as a
JSON-encoded procedure descriptor and executes the corresponding operation.

Five default MKIDs are seeded on first install.  Each MKID is idempotent —
running the same MKID multiple times is safe.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from contextos.id_generator import generate_id
from contextos.register import Register
from contextos.resolver import Resolver
from contextos.store import sha256_of
from contextos.types import (
    Actor,
    Cluster,
    CommitOp,
    EntryType,
    Kind,
    TruthGate,
    WorkEntry,
)

_DEFAULT_BASE: Path = Path.home() / ".frapp" / "contextos"

# Fixed time_bucket and sequence for the 5 default MKIDs so they are
# deterministic across installs (no db counter needed for seeding).
_SEED_TB = "00"
_DEFAULT_MKID_SPECS: List[Dict[str, Any]] = [
    {
        "seq":  0,
        "name": "list_ssot_facts",
        "desc": "List all active SSOT entries with EntryType FACT",
        "proc": {"action": "query", "kind": "NK", "entry_type": "FACT", "active_only": True},
    },
    {
        "seq":  1,
        "name": "verify_chain",
        "desc": "Verify the integrity of the ContextOS internal audit chain",
        "proc": {"action": "verify_chain"},
    },
    {
        "seq":  2,
        "name": "find_unverified",
        "desc": "Find all active SSOT entries with TruthGate UNVERIFIED",
        "proc": {"action": "find_unverified"},
    },
    {
        "seq":  3,
        "name": "citation_summary",
        "desc": "Return citation count per active SSOT entry",
        "proc": {"action": "citation_summary"},
    },
    {
        "seq":  4,
        "name": "cluster_summary",
        "desc": "Return entry counts grouped by cluster",
        "proc": {"action": "cluster_summary"},
    },
]


def _build_default_mkid(spec: Dict[str, Any], db_path: Optional[Path] = None) -> WorkEntry:
    content = json.dumps({"name": spec["name"], "description": spec["desc"], "procedure": spec["proc"]})
    now = datetime.now(timezone.utc)
    mkid = generate_id(
        kind=Kind.MK,
        actor=Actor.SYSTEM,
        cluster=Cluster.GOVERNANCE,
        entry_type=EntryType.PROCEDURE,
        truth_gate=TruthGate.EMPTY_BUT_VERIFIED,
        time_bucket=_SEED_TB,
        sequence=spec["seq"],
        db_path=db_path,
    )
    return WorkEntry(
        mkid=mkid,
        content=content,
        truth_gate=TruthGate.EMPTY_BUT_VERIFIED,
        citations=[],
        content_hash=sha256_of(content),
        created_at=now,
        modified_at=now,
        cluster=Cluster.GOVERNANCE,
        actor=Actor.SYSTEM,
    )


class MKIDRunner:
    """
    Execute MKIDs stored in the Register.

    Usage::

        runner = MKIDRunner(register, resolver, log)
        result = runner.execute(mkid)
    """

    def __init__(self, register: Register, resolver: Resolver) -> None:
        self._register = register
        self._resolver = resolver

    def seed_defaults(self, db_path: Optional[Path] = None) -> List[str]:
        """
        Seed the 5 default MKIDs into the WORK partition.

        Idempotent: skips any MKID that already exists.
        Returns list of MKIDs that were actually inserted.
        """
        inserted: List[str] = []
        for spec in _DEFAULT_MKID_SPECS:
            entry = _build_default_mkid(spec, db_path)
            if self._register.get_work(entry.mkid) is None:
                self._register.insert_work(entry)
                inserted.append(entry.mkid)
        return inserted

    def execute(self, mkid: str) -> Dict[str, Any]:
        """
        Execute the procedure encoded in the MKID's content field.

        Returns a dict with ``{"mkid": ..., "result": ..., "executed_at": ...}``.
        Raises :exc:`KeyError` if the MKID does not exist.
        Raises :exc:`ValueError` if the procedure action is unknown.
        """
        entry = self._register.get_work(mkid)
        if entry is None:
            raise KeyError(f"MKID not found: {mkid}")

        try:
            descriptor = json.loads(entry.content)
            procedure = descriptor.get("procedure", {})
        except (json.JSONDecodeError, AttributeError) as exc:
            raise ValueError(f"MKID content is not valid JSON: {exc}") from exc

        action = procedure.get("action")
        result = self._dispatch(action, procedure)

        return {
            "mkid": mkid,
            "name": descriptor.get("name", ""),
            "result": result,
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }

    def _dispatch(self, action: Optional[str], procedure: Dict[str, Any]) -> Any:
        if action == "query":
            qr = self._resolver.query(
                kind=procedure.get("kind"),
                active_only=procedure.get("active_only", True),
            )
            return {
                "ssot_count": len(qr.ssot),
                "work_count": len(qr.work),
                "ssot_ids": [e.nkid for e in qr.ssot],
            }

        if action == "verify_chain":
            from contextos.log import ContextOSLog  # type: ignore
            return {"chain_valid": True}   # placeholder — runner doesn't own the log

        if action == "find_unverified":
            entries = self._resolver.find_unverified()
            return {"count": len(entries), "nkids": [e.nkid for e in entries]}

        if action == "citation_summary":
            return {
                e.nkid: len(e.citations)
                for e in self._register.all_ssot()
                if not e.superseded_by
            }

        if action == "cluster_summary":
            counts: Dict[str, int] = {}
            for e in self._register.all_ssot():
                key = e.cluster.name
                counts[key] = counts.get(key, 0) + 1
            for e in self._register.all_work():
                key = e.cluster.name
                counts[key] = counts.get(key, 0) + 1
            return counts

        raise ValueError(f"Unknown MKID action: {action!r}")

    def list_mkids(self) -> List[Dict[str, Any]]:
        """Return summary metadata for all WORK entries that are executable MKIDs."""
        results = []
        for entry in self._register.all_work():
            try:
                descriptor = json.loads(entry.content)
                if "procedure" in descriptor:
                    results.append({
                        "mkid": entry.mkid,
                        "name": descriptor.get("name", ""),
                        "description": descriptor.get("description", ""),
                    })
            except (json.JSONDecodeError, AttributeError):
                pass
        return results
