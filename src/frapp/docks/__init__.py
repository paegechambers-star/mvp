"""
FraPP-Docks (Plugins).

Ein Dock hat ``name`` und ``load()`` (Original-Interface, unverändert). Optional:

  mount(app)   hängt eigene Routen/Unter-Apps in die FraPP-API ein
  cli()        liefert eine Typer-App, die als ``frapp <name> …`` erscheint

Eingebaut: ``scriptor`` (KI-Ghostwriter, unter /scriptor/). Abschalten einzelner
Docks: Umgebungsvariable ``FRAPP_DISABLED_DOCKS=scriptor`` (kommagetrennt).
Ein Dock, dessen ``load()`` False liefert oder eine Exception wirft, wird
übersprungen — FraPP selbst startet immer.
"""

from __future__ import annotations

import logging
import os
from typing import Any, List, Optional

_log = logging.getLogger("frapp.docks")


class Dock:
    """Minimal Dock-Interface (Plugins)."""

    name: str = "dummy"

    def load(self):
        return True

    def mount(self, app: Any) -> None:
        """Optional: Routen in die FraPP-API einhängen."""

    def cli(self) -> Optional[Any]:
        """Optional: Typer-App für ``frapp <name>``."""
        return None


def builtin_docks() -> List[Dock]:
    from .scriptor import ScriptorDock

    return [ScriptorDock()]


def load_docks(candidates: Optional[List[Dock]] = None) -> List[Dock]:
    """Lädt alle Docks; fehlerhafte werden geloggt und übersprungen."""
    disabled = {d.strip() for d in os.environ.get("FRAPP_DISABLED_DOCKS", "").split(",") if d.strip()}
    loaded: List[Dock] = []
    for dock in candidates if candidates is not None else builtin_docks():
        if dock.name in disabled:
            continue
        try:
            if dock.load():
                loaded.append(dock)
        except Exception as exc:  # noqa: BLE001 - Dock-Isolation
            _log.warning("Dock %s nicht geladen: %s", dock.name, exc)
    return loaded
