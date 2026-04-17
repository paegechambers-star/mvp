"""
ContextOS™ fast-lookup index.

Maintains an in-memory dictionary for O(1) ID lookups, backed by a JSON
snapshot file for persistence across restarts.  The index is rebuilt from
the Register on demand if the snapshot is missing or stale.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from contextos.types import Cluster, SSOTEntry, WorkEntry

_DEFAULT_BASE: Path = Path.home() / ".frapp" / "contextos"


class ContextOSIndex:
    """
    In-memory + JSON-persisted lookup index over ContextOS entries.

    The index maps IDs → lightweight metadata dicts (not full entries).
    Full entries are fetched from the Register on demand.
    """

    def __init__(self, index_path: Optional[Path] = None) -> None:
        self._index_path = index_path or (_DEFAULT_BASE / "index.json")
        # id → {"kind": "NK"|"MK", "cluster": str, "truth_gate": str}
        self._data: Dict[str, dict] = {}  # type: ignore[type-arg]
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if self._index_path.exists():
            try:
                self._data = json.loads(self._index_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def save(self) -> None:
        """Persist the current index to disk."""
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        self._index_path.write_text(
            json.dumps(self._data, indent=2), encoding="utf-8"
        )

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add_ssot(self, entry: SSOTEntry) -> None:
        """Register an SSOT entry in the index."""
        self._data[entry.nkid] = {
            "kind": "NK",
            "cluster": entry.cluster.value,
            "truth_gate": entry.truth_gate.value,
            "superseded_by": entry.superseded_by,
        }

    def add_work(self, entry: WorkEntry) -> None:
        """Register a WORK entry in the index."""
        self._data[entry.mkid] = {
            "kind": "MK",
            "cluster": entry.cluster.value,
            "truth_gate": entry.truth_gate.value,
            "promoted": entry.promoted,
        }

    def update_work(self, mkid: str, **kwargs: object) -> None:
        """Update metadata for a WORK entry (e.g. after a patch)."""
        if mkid in self._data:
            self._data[mkid].update(kwargs)

    def build_from_register(self, ssot_entries: List[SSOTEntry], work_entries: List[WorkEntry]) -> None:
        """Rebuild the entire index from Register data."""
        self._data = {}
        for e in ssot_entries:
            self.add_ssot(e)
        for e in work_entries:
            self.add_work(e)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, id_str: str) -> Optional[dict]:  # type: ignore[type-arg]
        """Return index metadata for *id_str*, or None if not found."""
        return self._data.get(id_str)

    def exists(self, id_str: str) -> bool:
        return id_str in self._data

    def by_cluster(self, cluster: Cluster) -> List[str]:
        """Return all IDs belonging to *cluster*."""
        return [
            id_str for id_str, meta in self._data.items()
            if meta.get("cluster") == cluster.value
        ]

    def by_kind(self, kind: str) -> List[str]:
        """Return all IDs of the given kind ('NK' or 'MK')."""
        return [
            id_str for id_str, meta in self._data.items()
            if meta.get("kind") == kind
        ]

    def active_ssot(self) -> List[str]:
        """Return NKIDs that have not been superseded."""
        return [
            id_str for id_str, meta in self._data.items()
            if meta.get("kind") == "NK" and not meta.get("superseded_by")
        ]

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, id_str: object) -> bool:
        return id_str in self._data
