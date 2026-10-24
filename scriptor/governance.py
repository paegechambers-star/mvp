"""
G.O.D.A.I.-Governance für SCRIPTOR.

Jeder Claude-Aufruf von SCRIPTOR läuft vorher durch G.O.D.A.I.:

  HERMES     Authentifizierung, Trust-Level, Datenklasse
  THEMIS     YAML-Policy (bindend — eine Ablehnung stoppt den Aufruf)
  MNEMOSYNE  SHA256-verkettetes Audit aller Entscheidungen + Ergebnis

APOLLON (Modellwahl) und ATHENA (Gegenprüfung durch ein zweites Modell) werden
bewusst nicht genutzt: Das Modell wählt die Nutzerin in den Einstellungen, und
SCRIPTOR hat ein eigenes, unabhängiges Lektorat mit Code-Gate (Generator ≠ Arbiter).

Die G.O.D.A.I.-Module sind async; SCRIPTOR ruft synchron aus mehreren Threads.
Deshalb läuft G.O.D.A.I. in einem eigenen Event-Loop-Thread — so teilen sich alle
Aufrufe eine MNEMOSYNE-Kette ohne Loop-Konflikte.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

from scriptor.llm import LLM, AgentTurn, LLMError

T = TypeVar("T")


class PolicyDenied(LLMError):
    """THEMIS hat den Aufruf abgelehnt (bindend)."""


class GodaiGovernance:
    """Gemeinsame G.O.D.A.I.-Instanz (eine MNEMOSYNE-Kette) für eine SCRIPTOR-Laufzeit."""

    def __init__(
        self,
        policy_path: Path | None = None,
        trust: str = "L2",
        user_id: str = "scriptor",
        rate_limit: int = 100_000,
    ) -> None:
        import secrets

        from godai.modules.hermes import Hermes
        from godai.modules.mnemosyne import Mnemosyne
        from godai.modules.themis import Themis
        from godai.pipeline import _DEFAULT_POLICY_PATH

        self._trust = trust
        self._user_id = user_id
        # Eigener Signaturschlüssel; HERMES im strengen Modus akzeptiert nur gültige JWTs
        self._secret = secrets.token_urlsafe(32)
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever, name="godai-loop", daemon=True
        )
        self._thread.start()
        self.mnemosyne = Mnemosyne()
        self.hermes = Hermes(
            self.mnemosyne, rate_limit=rate_limit, secret_key=self._secret, dev_mode=False
        )
        self.themis = Themis(self.mnemosyne, policy_path=policy_path or _DEFAULT_POLICY_PATH)
        self.decisions = {"allowed": 0, "denied": 0}

    def _run(self, coro: Coroutine[Any, Any, T]) -> T:
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=30)

    def check(self, role: str, prompt: str, data_class: str, book: str = "") -> None:
        """HERMES + THEMIS. Wirft :class:`PolicyDenied` bei Ablehnung."""
        from godai.models.request import TrustLevel
        from godai.modules.hermes import (
            AuthenticationError,
            RateLimitError,
            create_token,
        )

        context = {"data_class": data_class, "action": f"scriptor.{role}", "book": book}
        token = create_token(self._user_id, TrustLevel[self._trust], self._secret, expires_hours=1)
        try:
            request = self._run(
                self.hermes.normalize(
                    token=token,
                    user_id=self._user_id,
                    protocol="http",
                    query=prompt,
                    context=context,
                )
            )
        except (AuthenticationError, RateLimitError) as exc:
            self.decisions["denied"] += 1
            raise PolicyDenied(f"G.O.D.A.I./HERMES: {exc}") from exc
        decision = self._run(self.themis.evaluate(request))
        if not decision.allowed:
            self.decisions["denied"] += 1
            raise PolicyDenied(f"G.O.D.A.I./THEMIS: {decision.reason}")
        self.decisions["allowed"] += 1

    def record(self, role: str, model: str, ok: bool, detail: str = "") -> None:
        """Ergebnis des Aufrufs in MNEMOSYNE festhalten."""
        from godai.models.audit import AuditEvent

        self._run(
            self.mnemosyne.append(
                AuditEvent(
                    event_type="pipeline_success" if ok else "pipeline_error",
                    event_data={
                        "source": "scriptor",
                        "role": role,
                        "model": model,
                        "detail": detail[:300],
                    },
                    source_module="PIPELINE",
                    timestamp=datetime.now(timezone.utc),
                )
            )
        )

    def status(self) -> dict[str, Any]:
        try:
            chain_ok = bool(self.mnemosyne.verify_chain())
        except Exception:
            chain_ok = False
        recent: list[dict[str, Any]] = []
        for e in self.mnemosyne.entries[-15:]:
            recent.append(
                {
                    "ts": e.timestamp.isoformat() if hasattr(e, "timestamp") else "",
                    "module": getattr(e, "source_module", ""),
                    "type": getattr(e, "event_type", ""),
                    "data": {
                        k: v
                        for k, v in (getattr(e, "event_data", {}) or {}).items()
                        if k in ("allowed", "reason", "role", "model", "data_class", "detail")
                    },
                }
            )
        return {
            "active": True,
            "entries": len(self.mnemosyne),
            "chain_ok": chain_ok,
            "decisions": dict(self.decisions),
            "recent": recent,
        }


class GovernedLLM:
    """Wrapper: jeder LLM-Aufruf wird von G.O.D.A.I. freigegeben und protokolliert."""

    def __init__(self, inner: LLM, governance: GodaiGovernance) -> None:
        self.inner = inner
        self.gov = governance
        self.data_class = "INTERNAL"
        self.book = ""

    @property
    def model(self) -> str:
        return str(getattr(self.inner, "model", "?"))

    def set_context(self, data_class: str = "INTERNAL", book: str = "") -> None:
        """Vom Ghostwriter je Buch gesetzt (Datenklasse aus der Buchart)."""
        self.data_class = data_class
        self.book = book

    def _guarded(self, role: str, prompt: str, call: Any) -> Any:
        self.gov.check(role, prompt, self.data_class, self.book)
        try:
            result = call()
        except Exception as exc:
            self.gov.record(role, self.model, False, f"{type(exc).__name__}: {exc}")
            raise
        self.gov.record(role, self.model, True)
        return result

    def complete(self, role, system, prompt, *, effort="high", max_tokens=64000) -> str:
        return str(
            self._guarded(
                role,
                prompt,
                lambda: self.inner.complete(
                    role, system, prompt, effort=effort, max_tokens=max_tokens
                ),
            )
        )

    def complete_json(self, role, system, prompt, schema, *, effort="high") -> dict[str, Any]:
        return dict(
            self._guarded(
                role,
                prompt,
                lambda: self.inner.complete_json(role, system, prompt, schema, effort=effort),
            )
        )

    def agent_turn(self, system, messages, tools, *, effort="high") -> AgentTurn:
        last = str(messages[-1]["content"]) if messages else ""
        turn: AgentTurn = self._guarded(
            "agent", last, lambda: self.inner.agent_turn(system, messages, tools, effort=effort)
        )
        return turn
