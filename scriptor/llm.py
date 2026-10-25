"""
LLM-Schicht für SCRIPTOR.

Drei Implementierungen desselben Protokolls:

  AnthropicLLM — echte Claude-API (Streaming, adaptive Thinking, Effort-Steuerung,
                 serverseitiger Refusal-Fallback, Prompt-Caching).
  OllamaLLM    — lokales Modell über Ollama (http://localhost:11434). Kein Key, keine
                 Cloud; Texte verlassen den Rechner nicht.
  FakeLLM      — deterministischer Stub für Tests und Offline-Läufe. Keine Netzaufrufe.

Jeder Aufruf wird über :class:`~scriptor.audit.AuditLog` protokolliert
(Invariante „All Decisions Logged“ aus G.O.D.A.I.).
"""

from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from scriptor.audit import AuditLog

DEFAULT_MODEL = os.environ.get("SCRIPTOR_MODEL", "claude-opus-5-5")

# Fallback-Modus "default": die API routet bei einer Refusal selbst auf ein Ersatzmodell.
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(RuntimeError):
    """Generierung fehlgeschlagen (Refusal, Abbruch, ungültiges JSON)."""


@dataclass
class AgentTurn:
    """Ergebnis eines Agent-Schritts: Rohinhalt (für die Historie) + Tool-Calls + Text."""

    content: list[Any]
    stop_reason: str
    text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


class LLM(Protocol):
    """Minimales Protokoll, das Ghostwriter und Agent benötigen."""

    def complete(
        self,
        role: str,
        system: str,
        prompt: str,
        *,
        effort: str = "high",
        max_tokens: int = 64000,
    ) -> str: ...

    def complete_json(
        self,
        role: str,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        *,
        effort: str = "high",
    ) -> dict[str, Any]: ...

    def agent_turn(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        effort: str = "high",
    ) -> AgentTurn: ...

    def chat_stream(
        self, system: str, messages: list[dict[str, str]], *, max_tokens: int = 8000
    ) -> Iterator[str]:
        """Freier Chat: liefert die Antwort stückweise (``messages``: role/content-Strings)."""
        ...


# ---------------------------------------------------------------------------
# AnthropicLLM
# ---------------------------------------------------------------------------


class AnthropicLLM:
    """
    Claude-API-Backend.

    Zugangsdaten werden vom SDK aufgelöst (``ANTHROPIC_API_KEY``,
    ``ANTHROPIC_AUTH_TOKEN`` oder ein ``ant auth login``-Profil).
    """

    def __init__(
        self,
        audit: AuditLog,
        model: str = DEFAULT_MODEL,
        client: Any = None,
        api_key: str | None = None,
    ) -> None:
        if client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - Installationsfehler
                raise ImportError("Paket 'anthropic' fehlt: pip install anthropic") from exc
            client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self._client = client
        self._model = model
        self._audit = audit

    @property
    def model(self) -> str:
        return self._model

    def _stream(self, **params: Any) -> Any:
        with self._client.beta.messages.stream(
            model=self._model,
            thinking={"type": "adaptive"},
            cache_control={"type": "ephemeral"},
            betas=[_FALLBACK_BETA],
            fallbacks="default",
            **params,
        ) as stream:
            return stream.get_final_message()

    @staticmethod
    def _text_of(message: Any) -> str:
        return "".join(b.text for b in message.content if b.type == "text")

    def _check(self, role: str, message: Any) -> None:
        if message.stop_reason == "refusal":
            details = getattr(message, "stop_details", None)
            category = getattr(details, "category", None) if details else None
            raise LLMError(f"[{role}] Anfrage abgelehnt (Kategorie: {category})")
        if message.stop_reason == "max_tokens":
            raise LLMError(f"[{role}] Ausgabe bei max_tokens abgeschnitten")

    def complete(
        self,
        role: str,
        system: str,
        prompt: str,
        *,
        effort: str = "high",
        max_tokens: int = 64000,
    ) -> str:
        message = self._stream(
            max_tokens=max_tokens,
            system=system,
            output_config={"effort": effort},
            messages=[{"role": "user", "content": prompt}],
        )
        self._audit.llm_call(role, message.model, prompt, message.stop_reason, message.usage)
        self._check(role, message)
        return self._text_of(message)

    def complete_json(
        self,
        role: str,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        *,
        effort: str = "high",
    ) -> dict[str, Any]:
        message = self._stream(
            max_tokens=32000,
            system=system,
            output_config={
                "effort": effort,
                "format": {"type": "json_schema", "schema": schema},
            },
            messages=[{"role": "user", "content": prompt}],
        )
        self._audit.llm_call(role, message.model, prompt, message.stop_reason, message.usage)
        self._check(role, message)
        try:
            return dict(json.loads(self._text_of(message)))
        except json.JSONDecodeError as exc:
            raise LLMError(f"[{role}] Ungültiges JSON: {exc}") from exc

    def agent_turn(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        effort: str = "high",
    ) -> AgentTurn:
        message = self._client.beta.messages.create(
            model=self._model,
            max_tokens=16000,
            system=system,
            thinking={"type": "adaptive"},
            output_config={"effort": effort},
            cache_control={"type": "ephemeral"},
            betas=[_FALLBACK_BETA],
            fallbacks="default",
            tools=tools,
            messages=messages,
        )
        last = messages[-1]["content"] if messages else ""
        self._audit.llm_call("agent", message.model, str(last), message.stop_reason, message.usage)
        if message.stop_reason == "refusal":
            self._check("agent", message)
        return AgentTurn(
            content=list(message.content),
            stop_reason=message.stop_reason,
            text=self._text_of(message),
            tool_calls=[
                {"id": b.id, "name": b.name, "input": b.input}
                for b in message.content
                if b.type == "tool_use"
            ],
        )

    def chat_stream(
        self, system: str, messages: list[dict[str, str]], *, max_tokens: int = 8000
    ) -> Iterator[str]:
        with self._client.beta.messages.stream(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            cache_control={"type": "ephemeral"},
            betas=[_FALLBACK_BETA],
            fallbacks="default",
            messages=messages,
        ) as stream:
            yield from stream.text_stream
            message = stream.get_final_message()
        last = messages[-1]["content"] if messages else ""
        self._audit.llm_call("chat", message.model, last, message.stop_reason, message.usage)
        if message.stop_reason == "refusal":
            self._check("chat", message)


# ---------------------------------------------------------------------------
# OllamaLLM
# ---------------------------------------------------------------------------

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen3:8b"

_THINK = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


@dataclass
class _Usage:
    input_tokens: int | None
    output_tokens: int | None
    cache_read_input_tokens: None = None


def _block(b: Any, key: str) -> Any:
    return b.get(key) if isinstance(b, dict) else getattr(b, key, None)


class _ThinkFilter:
    """Entfernt ``<think>…</think>`` aus einem Token-Strom (Tags können über Chunks verteilt sein)."""

    def __init__(self) -> None:
        self._buf = ""
        self._inside = False

    def feed(self, chunk: str) -> str:
        self._buf += chunk
        out = []
        while self._buf:
            tag = "</think>" if self._inside else "<think>"
            i = self._buf.find(tag)
            if i >= 0:
                if not self._inside:
                    out.append(self._buf[:i])
                self._buf = self._buf[i + len(tag) :]
                self._inside = not self._inside
                continue
            # möglichen Tag-Anfang am Ende zurückhalten
            keep = next((k for k in range(len(tag) - 1, 0, -1) if self._buf.endswith(tag[:k])), 0)
            if not self._inside:
                out.append(self._buf[: len(self._buf) - keep])
            self._buf = self._buf[len(self._buf) - keep :] if keep else ""
            break
        return "".join(out)

    def flush(self) -> str:
        rest, self._buf = ("" if self._inside else self._buf), ""
        return rest


class OllamaLLM:
    """
    Lokales Backend über die Ollama-HTTP-API (``/api/chat``).

    - ``effort`` wird ignoriert (lokale Modelle kennen das nicht).
    - ``complete_json`` nutzt Ollamas strukturierte Ausgabe (``format`` = JSON-Schema).
    - ``agent_turn`` übersetzt Werkzeuge und Verlauf zwischen Anthropic- und
      Ollama-Format; das Modell muss Tool-Calling können (z. B. qwen3, llama3.1).
    - Serverseitige Werkzeuge (Websuche) gibt es lokal nicht — sie werden ausgelassen.
    """

    def __init__(
        self,
        audit: AuditLog,
        model: str = DEFAULT_OLLAMA_MODEL,
        base_url: str = DEFAULT_OLLAMA_URL,
        num_ctx: int = 16384,
        timeout: float = 1800.0,
        client: Any = None,
    ) -> None:
        if client is None:
            import httpx

            client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)
        self._client = client
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._num_ctx = num_ctx
        self._audit = audit

    @property
    def model(self) -> str:
        return f"ollama:{self._model}"

    def _chat(self, role: str, payload: dict[str, Any]) -> dict[str, Any]:
        payload = {"model": self._model, "stream": False, **payload}
        try:
            r = self._client.post("/api/chat", json=payload)
        except Exception as exc:
            raise LLMError(
                f"[{role}] Ollama nicht erreichbar unter {self._base_url} — "
                f"läuft Ollama? (Startmenü → Ollama, oder 'ollama serve'). {exc}"
            ) from exc
        if r.status_code == 404:
            raise LLMError(
                f"[{role}] Modell '{self._model}' ist nicht installiert: ollama pull {self._model}"
            )
        if r.status_code >= 400:
            raise LLMError(f"[{role}] Ollama-Fehler {r.status_code}: {r.text[:300]}")
        return dict(r.json())

    def _options(self, max_tokens: int) -> dict[str, Any]:
        return {"num_ctx": self._num_ctx, "num_predict": min(max_tokens, self._num_ctx)}

    def _finish(self, role: str, prompt: str, data: dict[str, Any]) -> str:
        stop = "max_tokens" if data.get("done_reason") == "length" else "end_turn"
        usage = _Usage(data.get("prompt_eval_count"), data.get("eval_count"))
        self._audit.llm_call(role, self.model, prompt, stop, usage)
        if stop == "max_tokens":
            raise LLMError(
                f"[{role}] Ausgabe abgeschnitten (Kontext {self._num_ctx} Tokens zu klein?)"
            )
        return _THINK.sub("", str(data.get("message", {}).get("content", ""))).strip()

    def complete(
        self,
        role: str,
        system: str,
        prompt: str,
        *,
        effort: str = "high",
        max_tokens: int = 64000,
    ) -> str:
        data = self._chat(
            role,
            {
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "options": self._options(max_tokens),
            },
        )
        return self._finish(role, prompt, data)

    def complete_json(
        self,
        role: str,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        *,
        effort: str = "high",
    ) -> dict[str, Any]:
        data = self._chat(
            role,
            {
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "format": schema,
                "options": self._options(32000),
            },
        )
        text = self._finish(role, prompt, data)
        try:
            return dict(json.loads(text))
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                try:
                    return dict(json.loads(m.group(0)))
                except json.JSONDecodeError:
                    pass
            raise LLMError(f"[{role}] Ungültiges JSON vom lokalen Modell") from None

    @staticmethod
    def _tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
                },
            }
            for t in tools
            if "input_schema" in t  # serverseitige Werkzeuge (type=web_search_…) auslassen
        ]

    @staticmethod
    def _messages(system: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = [{"role": "system", "content": system}]
        names: dict[str, str] = {}
        for m in messages:
            content = m["content"]
            if isinstance(content, str):
                out.append({"role": m["role"], "content": content})
                continue
            if m["role"] == "assistant":
                text, calls = [], []
                for b in content:
                    kind = _block(b, "type")
                    if kind == "text":
                        text.append(str(_block(b, "text")))
                    elif kind == "tool_use":
                        names[str(_block(b, "id"))] = str(_block(b, "name"))
                        calls.append(
                            {
                                "function": {
                                    "name": _block(b, "name"),
                                    "arguments": _block(b, "input") or {},
                                }
                            }
                        )
                msg: dict[str, Any] = {"role": "assistant", "content": "".join(text)}
                if calls:
                    msg["tool_calls"] = calls
                out.append(msg)
                continue
            for b in content:
                if _block(b, "type") == "tool_result":
                    out.append(
                        {
                            "role": "tool",
                            "content": str(_block(b, "content")),
                            "tool_name": names.get(str(_block(b, "tool_use_id")), ""),
                        }
                    )
                elif _block(b, "type") == "text":
                    out.append({"role": "user", "content": str(_block(b, "text"))})
        return out

    def agent_turn(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        effort: str = "high",
    ) -> AgentTurn:
        data = self._chat(
            "agent",
            {
                "messages": self._messages(system, messages),
                "tools": self._tools(tools),
                "options": self._options(16000),
            },
        )
        msg = data.get("message", {})
        text = _THINK.sub("", str(msg.get("content", ""))).strip()
        calls = [
            {
                "id": str(c.get("id") or f"call_{uuid.uuid4().hex[:12]}"),
                "name": c["function"]["name"],
                "input": c["function"].get("arguments") or {},
            }
            for c in msg.get("tool_calls") or []
        ]
        for c in calls:
            if isinstance(c["input"], str):  # manche Modelle liefern Argumente als JSON-Text
                try:
                    c["input"] = json.loads(c["input"])
                except json.JSONDecodeError:
                    c["input"] = {}
        stop = "tool_use" if calls else "end_turn"
        last = messages[-1]["content"] if messages else ""
        usage = _Usage(data.get("prompt_eval_count"), data.get("eval_count"))
        self._audit.llm_call("agent", self.model, str(last), stop, usage)
        content: list[Any] = [{"type": "text", "text": text}] if text else []
        content += [{"type": "tool_use", **c} for c in calls]
        return AgentTurn(content=content, stop_reason=stop, text=text, tool_calls=calls)

    def chat_stream(
        self, system: str, messages: list[dict[str, str]], *, max_tokens: int = 8000
    ) -> Iterator[str]:
        import httpx

        payload = {
            "model": self._model,
            "stream": True,
            "messages": [{"role": "system", "content": system}, *messages],
            "options": self._options(max_tokens),
        }
        final: dict[str, Any] = {}
        try:
            with self._client.stream("POST", "/api/chat", json=payload) as r:
                if r.status_code == 404:
                    raise LLMError(
                        f"[chat] Modell '{self._model}' ist nicht installiert: "
                        f"ollama pull {self._model}"
                    )
                if r.status_code >= 400:
                    r.read()
                    raise LLMError(f"[chat] Ollama-Fehler {r.status_code}: {r.text[:300]}")
                flt = _ThinkFilter()
                for line in r.iter_lines():
                    if not line:
                        continue
                    ev = json.loads(line)
                    if "error" in ev:
                        raise LLMError(f"[chat] Ollama: {ev['error']}")
                    piece = flt.feed(str(ev.get("message", {}).get("content", "")))
                    if piece:
                        yield piece
                    if ev.get("done"):
                        final = ev
                tail = flt.flush()
                if tail:
                    yield tail
        except httpx.HTTPError as exc:
            raise LLMError(
                f"[chat] Verbindung zu Ollama ({self._base_url}) fehlgeschlagen — "
                f"läuft Ollama? (Startmenü → Ollama, oder 'ollama serve'). {exc}"
            ) from exc
        stop = "max_tokens" if final.get("done_reason") == "length" else "end_turn"
        usage = _Usage(final.get("prompt_eval_count"), final.get("eval_count"))
        last = messages[-1]["content"] if messages else ""
        self._audit.llm_call("chat", self.model, last, stop, usage)


def ollama_status(base_url: str = DEFAULT_OLLAMA_URL, client: Any = None) -> dict[str, Any]:
    """Erreichbarkeit, Version und installierte Modelle des lokalen Ollama-Servers."""
    import httpx

    c = client or httpx.Client(base_url=base_url.rstrip("/"), timeout=3.0)
    try:
        version = c.get("/api/version").json().get("version", "?")
        models = sorted(m["name"] for m in c.get("/api/tags").json().get("models", []))
        return {"reachable": True, "url": base_url, "version": version, "models": models}
    except Exception as exc:
        return {"reachable": False, "url": base_url, "error": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------------------
# FakeLLM
# ---------------------------------------------------------------------------


class FakeLLM:
    """
    Deterministischer Test-Stub.

    ``responders`` bildet eine Rolle (z. B. ``"draft"``) auf eine Funktion
    ``(system, prompt) -> str | dict`` ab. Unbekannte Rollen liefern einen
    Platzhaltertext bzw. ein leeres Dict. ``agent_script`` ist eine Liste
    vorbereiteter :class:`AgentTurn`-Objekte, die nacheinander ausgegeben werden.
    """

    def __init__(
        self,
        responders: dict[str, Callable[[str, str], Any]] | None = None,
        agent_script: list[AgentTurn] | None = None,
        audit: AuditLog | None = None,
    ) -> None:
        self._responders = responders or {}
        self._script = list(agent_script or [])
        self._audit = audit
        self.calls: list[dict[str, Any]] = []

    @property
    def model(self) -> str:
        return "fake"

    def _respond(self, role: str, system: str, prompt: str) -> Any:
        self.calls.append({"role": role, "system": system, "prompt": prompt})
        if self._audit is not None:
            self._audit.llm_call(role, "fake", prompt, "end_turn", None)
        fn = self._responders.get(role)
        return fn(system, prompt) if fn else None

    def complete(self, role, system, prompt, *, effort="high", max_tokens=64000) -> str:
        out = self._respond(role, system, prompt)
        return str(out) if out is not None else f"[{role}] Platzhaltertext."

    def complete_json(self, role, system, prompt, schema, *, effort="high") -> dict[str, Any]:
        out = self._respond(role, system, prompt)
        return dict(out) if out is not None else {}

    def chat_stream(self, system, messages, *, max_tokens=8000) -> Iterator[str]:
        last = messages[-1]["content"] if messages else ""
        out = self._respond("chat", system, last)
        text = str(out) if out is not None else f"Echo: {last}"
        for word in text.split(" "):
            yield word + " "

    def agent_turn(self, system, messages, tools, *, effort="high") -> AgentTurn:
        self.calls.append({"role": "agent", "system": system, "messages": list(messages)})
        if not self._script:
            return AgentTurn(content=[], stop_reason="end_turn", text="Fertig.")
        return self._script.pop(0)
