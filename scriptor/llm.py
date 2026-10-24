"""
LLM-Schicht für SCRIPTOR.

Zwei Implementierungen desselben Protokolls:

  AnthropicLLM — echte Claude-API (Streaming, adaptive Thinking, Effort-Steuerung,
                 serverseitiger Refusal-Fallback, Prompt-Caching).
  FakeLLM      — deterministischer Stub für Tests und Offline-Läufe. Keine Netzaufrufe.

Jeder Aufruf wird über :class:`~scriptor.audit.AuditLog` protokolliert
(Invariante „All Decisions Logged“ aus G.O.D.A.I.).
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
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

    def agent_turn(self, system, messages, tools, *, effort="high") -> AgentTurn:
        self.calls.append({"role": "agent", "system": system, "messages": list(messages)})
        if not self._script:
            return AgentTurn(content=[], stop_reason="end_turn", text="Fertig.")
        return self._script.pop(0)
