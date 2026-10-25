"""
Freier Chat (FraPP-Tab „Chat“): Gespräche mit dem eingestellten Modell (Ollama oder Claude).

Jedes Gespräch ist eine JSON-Datei unter ``<workspace>/chats/<id>.json``. Der Aufruf
läuft wie alle SCRIPTOR-Aufrufe durch G.O.D.A.I.

Zwei Betriebsarten:

  ohne Werkzeuge   Antwort wird Wort für Wort gestreamt.
  mit Werkzeugen   Die Host-App (FraPP) stellt ``ChatToolkit``s bereit, z. B. den Kalender.
                   Lesende Werkzeuge laufen sofort. Schreibende Werkzeuge erzeugen nur einen
                   **Vorschlag**; ausgeführt wird er erst, wenn die Nutzerin im Chat
                   „Übernehmen“ klickt (:func:`decide`). Das Modell kann also nichts
                   selbst eintragen — und darf nicht behaupten, es habe es getan.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
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
# Höchstzahl Modell-Schritte pro Nachricht im Werkzeug-Modus
MAX_TOOL_STEPS = 6
TOOL_RULES = (
    "WERKZEUGE: Nutze die Werkzeuge, statt Daten zu raten. Schreibende Werkzeuge "
    "(anlegen/ändern/löschen) erzeugen nur einen VORSCHLAG, den die Nutzerin im Chat "
    "bestätigen muss. Sag danach klar: „Bitte bestätigen“ — behaupte NIE, etwas sei "
    "eingetragen oder gespeichert. Wenn Datum, Uhrzeit oder Dauer unklar sind, frag nach, "
    "statt zu raten. Zeiten immer als ISO 8601 (z. B. 2026-10-27T14:00) in Europe/Berlin."
)
DATA_CLASSES = ("PUBLIC", "INTERNAL", "SENSITIVE", "RESTRICTED")
_ID = re.compile(r"^[0-9a-f]{12}$")


@dataclass
class Proposal:
    """Von einem schreibenden Werkzeug vorbereitete, noch nicht ausgeführte Änderung."""

    summary: str  # deterministischer Kartentext (nicht vom Modell formuliert)
    payload: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


@dataclass
class ChatTool:
    """
    Werkzeug für den Chat.

    Lesend:     ``run(args) -> str`` (läuft sofort).
    Schreibend: ``prepare(args) -> Proposal`` (prüft, schreibt nichts) und
                ``apply(payload) -> str`` (schreibt, erst nach Bestätigung).
    Ungültige Eingaben: ``ValueError`` mit verständlicher Meldung.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    run: Callable[[dict[str, Any]], str] | None = None
    prepare: Callable[[dict[str, Any]], Proposal] | None = None
    apply: Callable[[dict[str, Any]], str] | None = None

    @property
    def writes(self) -> bool:
        return self.prepare is not None

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


@dataclass
class ChatToolkit:
    """Werkzeugsatz einer Host-App, z. B. ``kalender``; ``context()`` ergänzt den Systemprompt."""

    name: str
    tools: list[ChatTool]
    context: Callable[[], str] = lambda: ""


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

    def create(
        self, system: str = "", data_class: str = "INTERNAL", tools: bool = True
    ) -> dict[str, Any]:
        if data_class not in DATA_CLASSES:
            raise ChatError(f"Datenklasse muss eine von {DATA_CLASSES} sein")
        chat = {
            "id": uuid.uuid4().hex[:12],
            "title": "Neuer Chat",
            "system": system.strip(),
            "data_class": data_class,
            "tools": tools,
            "created": _now(),
            "updated": _now(),
            "messages": [],
            "proposals": {},
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


def _history(chat: dict[str, Any]) -> list[dict[str, str]]:
    """Letzte Nachrichten fürs Modell: Rollen zusammengeführt, beginnt mit dem Nutzer."""
    proposals = chat.get("proposals", {})
    out: list[dict[str, str]] = []
    for m in chat["messages"][-HISTORY_LIMIT:]:
        content = m["content"]
        for pid in m.get("proposals", []):
            p = proposals.get(pid, {})
            content += f"\n[Vorschlag {pid}: {p.get('summary', '?')} — Status: {p.get('status')}]"
        if out and out[-1]["role"] == m["role"]:
            out[-1]["content"] += "\n\n" + content
        else:
            out.append({"role": m["role"], "content": content})
    while out and out[0]["role"] != "user":  # Claude verlangt: erste Nachricht vom Nutzer
        out.pop(0)
    return out


def _system(chat: dict[str, Any], toolkits: list[ChatToolkit]) -> str:
    parts = [chat["system"] or DEFAULT_SYSTEM]
    if toolkits:
        parts.append(TOOL_RULES)
        parts += [ctx for k in toolkits if (ctx := k.context())]
    return "\n\n".join(parts)


def stream_reply(
    store: ChatStore,
    chat_id: str,
    text: str,
    llm: LLM,
    model: str,
    toolkits: list[ChatToolkit] | None = None,
) -> Iterator[dict[str, Any]]:
    """
    Hängt die Nutzer-Nachricht an und liefert Events:
    ``{"delta"}`` Text, ``{"tool"}`` Werkzeugaufruf, ``{"proposal"}`` Vorschlag,
    am Ende ``{"done"}`` oder ``{"error"}``. Speichert alles im Chat.
    """
    text = text.strip()
    if not text:
        raise ChatError("Leere Nachricht")
    chat = store.get(chat_id)
    chat.setdefault("proposals", {})
    chat["messages"].append({"role": "user", "content": text, "ts": _now()})
    if chat["title"] == "Neuer Chat":
        chat["title"] = text[:60] + ("…" if len(text) > 60 else "")
    store.save(chat)

    if hasattr(llm, "set_context"):
        llm.set_context(data_class=chat["data_class"], book="chat")
    active = toolkits if (toolkits and chat.get("tools", True)) else []
    if active:
        yield from _tool_reply(store, chat, llm, model, active)
    else:
        yield from _stream_plain(store, chat, llm, model)


def _stream_plain(
    store: ChatStore, chat: dict[str, Any], llm: LLM, model: str
) -> Iterator[dict[str, Any]]:
    parts: list[str] = []
    error = ""
    aborted = False
    gen = llm.chat_stream(_system(chat, []), _history(chat))
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


def _public(pid: str, p: dict[str, Any]) -> dict[str, Any]:
    return {"id": pid, **{k: v for k, v in p.items() if k != "payload"}}


def _tool_reply(
    store: ChatStore,
    chat: dict[str, Any],
    llm: LLM,
    model: str,
    toolkits: list[ChatToolkit],
) -> Iterator[dict[str, Any]]:
    tools = {t.name: t for k in toolkits for t in k.tools}
    schemas = [t.schema() for t in tools.values()]
    system = _system(chat, toolkits)
    msgs: list[dict[str, Any]] = list(_history(chat))
    new_ids: list[str] = []
    text, error = "", ""
    try:
        for _ in range(MAX_TOOL_STEPS):
            turn = llm.agent_turn(system, msgs, schemas, effort="medium")
            msgs.append({"role": "assistant", "content": turn.content})
            text = turn.text.strip()
            if turn.stop_reason != "tool_use":
                break
            results = []
            for call in turn.tool_calls:
                name, args = call["name"], dict(call["input"] or {})
                yield {"tool": name, "input": args}
                output, is_error = _run_tool(chat, tools.get(name), name, args, new_ids)
                if new_ids and output.startswith("Vorschlag " + new_ids[-1]):
                    yield {"proposal": _public(new_ids[-1], chat["proposals"][new_ids[-1]])}
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call["id"],
                        "content": output,
                        "is_error": is_error,
                    }
                )
            msgs.append({"role": "user", "content": results})
        else:
            text = (text + "\n" if text else "") + "[Abbruch: zu viele Werkzeugschritte]"
    except Exception as exc:
        error = str(exc) or type(exc).__name__
    if not text and new_ids:
        text = "Bitte prüfen und bestätigen:"
    if text or new_ids:
        msg: dict[str, Any] = {"role": "assistant", "content": text, "ts": _now(), "model": model}
        if new_ids:
            msg["proposals"] = new_ids
        if error:
            msg["incomplete"] = True
        chat["messages"].append(msg)
    store.save(chat)
    if text:
        yield {"delta": text}
    if error:
        yield {"error": error}
    else:
        yield {"done": True, "model": model}


def _run_tool(
    chat: dict[str, Any],
    tool: ChatTool | None,
    name: str,
    args: dict[str, Any],
    new_ids: list[str],
) -> tuple[str, bool]:
    if tool is None:
        return f"Unbekanntes Werkzeug: {name}", True
    try:
        if not tool.writes:
            assert tool.run is not None
            return tool.run(args), False
        assert tool.prepare is not None
        prop = tool.prepare(args)
    except (ValueError, KeyError, TypeError) as exc:
        return f"Fehler: {exc}", True
    pid = f"p{len(chat['proposals']) + 1}"
    chat["proposals"][pid] = {
        "tool": name,
        "summary": prop.summary,
        "warnings": prop.warnings,
        "payload": prop.payload,
        "status": "pending",
        "created": _now(),
    }
    new_ids.append(pid)
    warn = f" Hinweise: {'; '.join(prop.warnings)}." if prop.warnings else ""
    msg = (
        f"Vorschlag {pid} erstellt: {prop.summary}.{warn} NOCH NICHT gespeichert — "
        "die Nutzerin muss im Chat auf „Übernehmen“ klicken. Sag ihr das kurz."
    )
    return msg, False


def decide(
    store: ChatStore,
    chat_id: str,
    pid: str,
    accept: bool,
    toolkits: list[ChatToolkit],
) -> dict[str, Any]:
    """Vorschlag übernehmen (führt ``apply`` aus) oder verwerfen. Nur einmal möglich."""
    chat = store.get(chat_id)
    p = chat.get("proposals", {}).get(pid)
    if p is None:
        raise ChatNotFound(f"Vorschlag {pid} nicht gefunden")
    if p["status"] != "pending":
        raise ChatError(f"Vorschlag {pid} ist bereits {p['status']}")
    if accept:
        tool = next((t for k in toolkits for t in k.tools if t.name == p["tool"]), None)
        if tool is None or tool.apply is None:
            raise ChatError(f"Werkzeug {p['tool']} ist nicht verfügbar")
        p["result"] = tool.apply(p["payload"])  # ValueError → Vorschlag bleibt offen
        p["status"] = "accepted"
        note = f"[FraPP] Vorschlag {pid} übernommen: {p['result']}"
    else:
        p["status"] = "rejected"
        note = f"[FraPP] Vorschlag {pid} verworfen: {p['summary']}"
    p["decided"] = _now()
    chat["messages"].append({"role": "user", "kind": "note", "content": note, "ts": _now()})
    store.save(chat)
    return _public(pid, p)
