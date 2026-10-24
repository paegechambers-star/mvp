"""
Docks — Plugin-System für SCRIPTOR (Konzept aus FraPP: ``Dock`` mit ``name`` + ``load``).

Ein Dock erweitert SCRIPTOR um:

  - Agent-Werkzeuge         ``registry.add_tool(name, description, schema, handler)``
  - Bucharten               ``registry.add_genre_dir(path)`` (Ordner mit YAML-Profilen)
  - Materialarten           ``registry.add_material(kind, auftrag)``
  - API-Routen (App)        ``registry.add_router(fastapi.APIRouter)``
  - CLI-Befehle             ``registry.add_cli(name, typer.Typer)``

Quellen (in dieser Reihenfolge):

  1. eingebaut              ``scriptor.docks.builtin.BUILTIN_DOCKS``
  2. pip-Pakete             Entry-Point-Gruppe ``scriptor.docks``
  3. Plugin-Ordner          ``<config>/plugins/*.py`` — **nur** wenn der Dateiname in
                            ``Settings.enabled_plugins`` steht (Ordner-Plugins sind
                            beliebiger Code; nichts läuft ohne Freigabe).

Fehler in einem Dock werden gesammelt, nicht geworfen: ein kaputtes Plugin legt
die App nicht lahm.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

if TYPE_CHECKING:
    from scriptor.agent import Agent

ENTRY_POINT_GROUP = "scriptor.docks"

ToolHandler = Callable[..., Any]


class Dock:
    """Basisklasse für Plugins (kompatibel zu ``frapp.docks.Dock``)."""

    name: str = "dummy"
    version: str = "0.0.0"
    description: str = ""

    def load(self, registry: "DockRegistry") -> bool:
        """Registriert die Beiträge des Docks. False = Dock deaktiviert sich selbst."""
        return True


@dataclass
class DockTool:
    schema: Dict[str, Any]
    handler: ToolHandler
    confirm: bool
    dock: str


@dataclass
class DockInfo:
    name: str
    version: str
    description: str
    source: str  # builtin | entrypoint | folder
    loaded: bool
    error: str = ""
    contributes: List[str] = field(default_factory=list)


class DockRegistry:
    """Sammelt alle Beiträge der geladenen Docks."""

    def __init__(self) -> None:
        self.tools: Dict[str, DockTool] = {}
        self.genre_dirs: List[Path] = []
        self.materials: Dict[str, str] = {}
        self.routers: List[Any] = []
        self.cli: Dict[str, Any] = {}
        self.infos: List[DockInfo] = []
        self._current: Optional[DockInfo] = None

    # -- API für Docks -------------------------------------------------

    def _note(self, what: str) -> None:
        if self._current is not None:
            self._current.contributes.append(what)

    def add_tool(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        handler: ToolHandler,
        confirm: bool = False,
    ) -> None:
        """
        Agent-Werkzeug registrieren. ``handler(agent, **input) -> str``.
        ``confirm=True``: läuft erst nach Nutzerfreigabe (Kosten/Wirkung).
        """
        if not name.isidentifier():
            raise ValueError(f"Werkzeugname '{name}' ist kein gültiger Bezeichner")
        if name in self.tools:
            raise ValueError(f"Werkzeug '{name}' ist bereits registriert")
        dock = self._current.name if self._current else "?"
        schema = {"name": name, "description": description, "input_schema": input_schema}
        self.tools[name] = DockTool(schema, handler, confirm, dock)
        self._note(f"tool:{name}")

    def add_genre_dir(self, path: Path) -> None:
        self.genre_dirs.append(Path(path))
        self._note(f"genres:{Path(path).name}")

    def add_material(self, kind: str, instruction: str) -> None:
        self.materials[kind] = instruction
        self._note(f"material:{kind}")

    def add_router(self, router: Any) -> None:
        self.routers.append(router)
        self._note("api-router")

    def add_cli(self, name: str, typer_app: Any) -> None:
        self.cli[name] = typer_app
        self._note(f"cli:{name}")

    # -- Laden ---------------------------------------------------------

    def load_dock(self, dock: Dock, source: str) -> DockInfo:
        info = DockInfo(dock.name, dock.version, dock.description, source, loaded=False)
        self._current = info
        snapshot = (dict(self.tools), list(self.genre_dirs), dict(self.materials),
                    list(self.routers), dict(self.cli))
        try:
            info.loaded = bool(dock.load(self))
        except Exception as exc:  # noqa: BLE001 - Plugin-Isolation
            info.error = f"{type(exc).__name__}: {exc}"
        if not info.loaded:
            # Teilregistrierungen eines fehlgeschlagenen Docks zurückrollen
            self.tools, self.genre_dirs, self.materials, self.routers, self.cli = snapshot
            info.contributes = []
        self._current = None
        self.infos.append(info)
        return info

    def apply_genres(self) -> None:
        from scriptor import genres

        genres.set_extra_dirs(self.genre_dirs)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _instantiate(obj: Any) -> Dock:
    dock = obj() if isinstance(obj, type) else obj
    if not hasattr(dock, "load") or not hasattr(dock, "name"):
        raise TypeError(f"{obj!r} ist kein Dock (braucht name + load)")
    return dock  # type: ignore[no-any-return]


def _folder_docks(plugin_dir: Path, enabled: List[str]) -> List[tuple[str, Any, str]]:
    found: List[tuple[str, Any, str]] = []
    if not plugin_dir.exists():
        return found
    for path in sorted(plugin_dir.glob("*.py")):
        if path.stem not in enabled:
            found.append((path.stem, None, "nicht freigegeben (Einstellungen → Plugins)"))
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"scriptor_plugin_{path.stem}", path)
            if spec is None or spec.loader is None:
                raise ImportError("kein Modul")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            found.append((path.stem, getattr(module, "DOCK"), ""))
        except Exception as exc:  # noqa: BLE001
            found.append((path.stem, None, f"{type(exc).__name__}: {exc}"))
    return found


def discover(
    plugin_dir: Optional[Path] = None,
    enabled_plugins: Optional[List[str]] = None,
    disabled: Optional[List[str]] = None,
    include_entry_points: bool = True,
) -> DockRegistry:
    """Lädt alle Docks und gibt die befüllte Registry zurück."""
    from scriptor.docks.builtin import BUILTIN_DOCKS

    registry = DockRegistry()
    disabled = disabled or []

    def _load(obj: Any, source: str, fallback_name: str) -> None:
        try:
            dock = _instantiate(obj)
        except Exception as exc:  # noqa: BLE001
            registry.infos.append(DockInfo(fallback_name, "?", "", source, False, str(exc)))
            return
        if dock.name in disabled:
            registry.infos.append(DockInfo(dock.name, dock.version, dock.description, source,
                                           False, "deaktiviert"))
            return
        registry.load_dock(dock, source)

    for obj in BUILTIN_DOCKS:
        _load(obj, "builtin", getattr(obj, "name", "?"))

    if include_entry_points:
        for ep in metadata.entry_points(group=ENTRY_POINT_GROUP):
            try:
                obj = ep.load()
            except Exception as exc:  # noqa: BLE001
                registry.infos.append(DockInfo(ep.name, "?", "", "entrypoint", False, str(exc)))
                continue
            _load(obj, "entrypoint", ep.name)

    if plugin_dir is not None:
        for stem, obj, error in _folder_docks(plugin_dir, enabled_plugins or []):
            if obj is None:
                registry.infos.append(DockInfo(stem, "?", "", "folder", False, error))
            else:
                _load(obj, "folder", stem)

    registry.apply_genres()
    return registry
