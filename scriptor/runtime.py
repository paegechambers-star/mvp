"""
Gemeinsame Laufzeit für CLI und Desktop-App: Einstellungen, Docks, LLM.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from scriptor.audit import AuditLog
from scriptor.docks import DockRegistry, discover
from scriptor.llm import LLM, AnthropicLLM
from scriptor.settings import Settings, get_api_key

LLMFactory = Callable[["Runtime"], LLM]


def anthropic_factory(rt: "Runtime") -> LLM:
    return AnthropicLLM(
        AuditLog(rt.workspace / "audit.jsonl"), model=rt.settings.model, api_key=get_api_key()
    )


@dataclass
class Runtime:
    settings: Settings
    docks: DockRegistry
    llm_factory: LLMFactory = anthropic_factory

    @property
    def workspace(self) -> Path:
        ws = self.settings.workspace_path()
        ws.mkdir(parents=True, exist_ok=True)
        return ws

    def llm(self) -> LLM:
        return self.llm_factory(self)

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
        return cls(s, docks, llm_factory)
