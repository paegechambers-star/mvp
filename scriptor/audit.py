"""
Append-only Audit-Log für SCRIPTOR (JSONL, SHA256-verkettet).

Jede Zeile enthält den Hash der Vorgängerzeile. ``verify()`` erkennt jede
nachträgliche Manipulation. Prompts werden nur als Hash + Länge gespeichert,
nicht im Klartext (Manuskripte sind vertraulich).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_GENESIS = "0" * 64


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class AuditLog:
    """Tamper-evident JSONL-Log. ``path=None`` → nur im Speicher."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._entries: list[dict[str, Any]] = []
        if path is not None and path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self._entries.append(json.loads(line))

    @property
    def entries(self) -> list[dict[str, Any]]:
        return list(self._entries)

    def append(self, event: str, data: dict[str, Any]) -> dict[str, Any]:
        prev = self._entries[-1]["hash"] if self._entries else _GENESIS
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "data": data,
            "prev": prev,
        }
        entry["hash"] = _sha(json.dumps(entry, sort_keys=True, ensure_ascii=False))
        self._entries.append(entry)
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def llm_call(self, role: str, model: str, prompt: str, stop_reason: str, usage: Any) -> None:
        data: dict[str, Any] = {
            "role": role,
            "model": model,
            "prompt_sha256": _sha(prompt),
            "prompt_len": len(prompt),
            "stop_reason": stop_reason,
        }
        if usage is not None:
            data["input_tokens"] = getattr(usage, "input_tokens", None)
            data["output_tokens"] = getattr(usage, "output_tokens", None)
            data["cache_read_tokens"] = getattr(usage, "cache_read_input_tokens", None)
        self.append("llm_call", data)

    def verify(self) -> bool:
        prev = _GENESIS
        for entry in self._entries:
            body = {k: v for k, v in entry.items() if k != "hash"}
            if entry["prev"] != prev:
                return False
            if _sha(json.dumps(body, sort_keys=True, ensure_ascii=False)) != entry["hash"]:
                return False
            prev = entry["hash"]
        return True
