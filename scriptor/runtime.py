"""
Gemeinsame Laufzeit für CLI und Desktop-App: Einstellungen, Docks, LLM, Governance.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scriptor.audit import AuditLog
from scriptor.docks import DockRegistry, discover
from scriptor.llm import LLM, AnthropicLLM, OllamaLLM
from scriptor.settings import Settings, get_api_key

LLMFactory = Callable[["Runtime"], LLM]


def anthropic_factory(rt: Runtime) -> LLM:
    return AnthropicLLM(
        AuditLog(rt.workspace / "audit.jsonl"), model=rt.settings.model, api_key=get_api_key()
    )


def ollama_factory(rt: Runtime) -> LLM:
    s = rt.settings
    return OllamaLLM(
        AuditLog(rt.workspace / "audit.jsonl"),
        model=s.ollama_model,
        base_url=s.ollama_url,
        num_ctx=int(s.ollama_num_ctx),
    )


def default_factory(rt: Runtime) -> LLM:
    """Wählt das Backend nach ``Settings.provider`` — bei jedem Aufruf neu (Umschalten ohne Neustart)."""
    if rt.settings.provider == "ollama":
        return ollama_factory(rt)
    return anthropic_factory(rt)


def _make_governance(settings: Settings) -> Any | None:
    """G.O.D.A.I.-Instanz oder None (abgeschaltet bzw. godai nicht installiert)."""
    if not settings.governance:
        return None
    try:
        from scriptor.ghostwriter import load_config
        from scriptor.governance import GodaiGovernance
    except ImportError:
        return None
    cfg = load_config().get("governance", {})
    return GodaiGovernance(
        trust=str(cfg.get("trust", "L2")),
        rate_limit=int(cfg.get("rate_limit", 100_000)),
    )


@dataclass
class Runtime:
    settings: Settings
    docks: DockRegistry
    llm_factory: LLMFactory = default_factory
    governance: Any | None = None

    @property
    def workspace(self) -> Path:
        ws = self.settings.workspace_path()
        ws.mkdir(parents=True, exist_ok=True)
        return ws

    def llm(self) -> LLM:
        llm = self.llm_factory(self)
        if self.governance is not None:
            from scriptor.governance import GovernedLLM

            return GovernedLLM(llm, self.governance)
        return llm

    @classmethod
    def create(
        cls,
        settings: Settings | None = None,
        llm_factory: LLMFactory = default_factory,
        include_entry_points: bool = True,
    ) -> Runtime:
        s = settings or Settings.load()
        docks = discover(
            plugin_dir=s.plugin_dir(),
            enabled_plugins=s.enabled_plugins,
            disabled=s.disabled_docks,
            include_entry_points=include_entry_points,
        )
        return cls(s, docks, llm_factory, _make_governance(s))
