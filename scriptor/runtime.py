"""
Gemeinsame Laufzeit für CLI und Desktop-App: Einstellungen, Docks, LLM, Governance.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from scriptor.audit import AuditLog
from scriptor.docks import DockRegistry, discover
from scriptor.llm import LLM, AnthropicLLM
from scriptor.settings import Settings, get_api_key

LLMFactory = Callable[["Runtime"], LLM]


def anthropic_factory(rt: "Runtime") -> LLM:
    return AnthropicLLM(
        AuditLog(rt.workspace / "audit.jsonl"), model=rt.settings.model, api_key=get_api_key()
    )


def _make_governance(settings: Settings) -> Optional[Any]:
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
        token=str(cfg.get("token", "elevated-scriptor-local")),
        rate_limit=int(cfg.get("rate_limit", 100_000)),
    )


@dataclass
class Runtime:
    settings: Settings
    docks: DockRegistry
    llm_factory: LLMFactory = anthropic_factory
    governance: Optional[Any] = None

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
        settings: Optional[Settings] = None,
        llm_factory: LLMFactory = anthropic_factory,
        include_entry_points: bool = True,
    ) -> "Runtime":
        s = settings or Settings.load()
        docks = discover(
            plugin_dir=s.plugin_dir(),
            enabled_plugins=s.enabled_plugins,
            disabled=s.disabled_docks,
            include_entry_points=include_entry_points,
        )
        return cls(s, docks, llm_factory, _make_governance(s))
