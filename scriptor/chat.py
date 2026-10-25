"""
Freier Chat (FraPP-Tab „Chat“): Gespräche mit dem eingestellten Modell (Ollama oder Claude).

Jedes Gespräch ist eine JSON-Datei unter ``<workspace>/chats/<id>.json``. Antworten
werden gestreamt; der Aufruf läuft wie alle SCRIPTOR-Aufrufe durch G.O.D.A.I.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scriptor.llm import LLM

DEFAULT_SYSTEM = (
    "Du bist ein hilfreicher Assistent in FraPP. Antworte auf Deutsch, direkt, klar und "
    "strukturiert, ohne Floskeln. Wenn du etwas nicht sicher weißt, sag das offen "
    "(UNVERIFIED) statt zu raten."
)
# So viele letzte Nachrichten gehen ans Modell (kleine lokale Kontextfenster)
HISTORY_LIMIT = 40
DATA_CLASSES = ("PUBLIC", "INTERNAL", "SENSITIVE", "RESTRICTED")
_ID = re.compile(r"^[0-9a-f]{12}$")


class ChatError(ValueError):
    """Ungültige Eingabe."""


class ChatNotFound(ChatError):
    """Unbekanntes Gespräch."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChatStore:
    def __init__(self, workspace: Path) -> None:
        self.dir = workspace / "chats"

    def _path(self, chat_id: str) -> Path:
        if not _ID.match(chat_id):
            raise ChatError(f"Ungültige Chat-ID: {chat_id}")
        return self.dir / f"{chat_id}.json"

    def create(self, system: str = "", data_class: str = "INTERNAL") -> dict[str, Any]:
        if data_class not in DATA_CLASSES:
            raise ChatError(f"Datenklasse muss eine von {DATA_CLASSES} sein")
        chat = {
            "id": uuid.uuid4().hex[:12],
            "title": "Neuer Chat",
            "system": system.strip(),
            "data_class": data_class,
            "created": _now(),
            "updated": _now(),
            "messages": [],
        }
        self.save(chat)
        return chat

    def get(self, chat_id: str) -> dict[str, Any]:
        path = self._path(chat_id)
        if not path.exists():
            raise ChatNotFound(f"Chat {chat_id} nicht gefunden")
        return dict(json.loads(path.read_text(encoding="utf-8")))

    def save(self, chat: dict[str, Any]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        chat["updated"] = _now()
        self._path(chat["id"]).write_text(
            json.dumps(chat, ensure_ascii=False, indent=1), encoding="utf-8"
        )

    def delete(self, chat_id: str) -> None:
        self._path(chat_id).unlink(missing_ok=True)

    def list(self) -> list[dict[str, Any]]:
        if not self.dir.exists():
            return []
        out = []
        for p in self.dir.glob("*.json"):
            try:
                c = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            out.append(
                {
                    "id": c["id"],
                    "title": c["title"],
                    "updated": c["updated"],
                    "n": len(c["messages"]),
                }
            )
        return sorted(out, key=lambda c: c["updated"], reverse=True)


def stream_reply(
    store: ChatStore, chat_id: str, text: str, llm: LLM, model: str
) -> Iterator[dict[str, Any]]:
    """
    Hängt die Nutzer-Nachricht an, streamt die Antwort als Events
    (``{"delta"}``, am Ende ``{"done"}`` oder ``{"error"}``) und speichert beides.
    """
    text = text.strip()
    if not text:
        raise ChatError("Leere Nachricht")
    chat = store.get(chat_id)
    chat["messages"].append({"role": "user", "content": text, "ts": _now()})
    if chat["title"] == "Neuer Chat":
        chat["title"] = text[:60] + ("…" if len(text) > 60 else "")
    store.save(chat)

    if hasattr(llm, "set_context"):
        llm.set_context(data_class=chat["data_class"], book="chat")
    history = [
        {"role": m["role"], "content": m["content"]} for m in chat["messages"][-HISTORY_LIMIT:]
    ]
    if history[0]["role"] != "user":  # Claude verlangt: erste Nachricht vom Nutzer
        history = history[1:]
    system = chat["system"] or DEFAULT_SYSTEM

    parts: list[str] = []
    error = ""
    aborted = False
    gen = llm.chat_stream(system, history)
    try:
        for piece in gen:
            if not parts:
                piece = piece.lstrip()
                if not piece:
                    continue
            parts.append(piece)
            yield {"delta": piece}
    except GeneratorExit:  # Client hat abgebrochen (Stopp-Knopf)
        aborted = True
        raise
    except Exception as exc:
        error = str(exc) or type(exc).__name__
    finally:
        close = getattr(gen, "close", None)
        if close is not None:
            close()  # beendet auch den Modell-Stream (Ollama/Claude) sofort
        reply = "".join(parts).rstrip()
        if reply:
            msg: dict[str, Any] = {
                "role": "assistant",
                "content": reply,
                "ts": _now(),
                "model": model,
            }
            if error or aborted:
                msg["incomplete"] = True
            chat["messages"].append(msg)
            store.save(chat)
    if error:
        yield {"error": error}
    else:
        yield {"done": True, "model": model}
