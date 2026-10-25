"""
Einstellungen für SCRIPTOR (CLI und Desktop-App).

Reihenfolge der Auflösung: Umgebungsvariable > settings.json > Plattform-Default.

  Windows  settings: %APPDATA%\\Scriptor\\settings.json
           workspace: %USERPROFILE%\\Documents\\Scriptor
           plugins:   %APPDATA%\\Scriptor\\plugins
  sonst    settings: ~/.config/scriptor/settings.json
           workspace: ~/Scriptor
           plugins:   ~/.config/scriptor/plugins

Der API-Key wird — falls ``keyring`` installiert ist — im Betriebssystem-Tresor
gespeichert (Windows: Anmeldeinformationsverwaltung), sonst nur aus der
Umgebung gelesen. Er landet nie in settings.json.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

_KEYRING_SERVICE = "scriptor"
_KEYRING_USER = "anthropic_api_key"


def config_dir() -> Path:
    override = os.environ.get("SCRIPTOR_CONFIG_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Scriptor"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "scriptor"


def default_workspace_dir() -> Path:
    if sys.platform == "win32":
        return Path.home() / "Documents" / "Scriptor"
    return Path.home() / "Scriptor"


@dataclass
class Settings:
    workspace: str = ""
    # KI-Anbieter: "anthropic" (Claude, Cloud, API-Key) | "ollama" (lokal, kein Key)
    provider: str = "anthropic"
    model: str = "claude-opus-5-5"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    # Kontextfenster für Ollama (Tokens); Ollamas Standard ist für Kapitel zu klein
    ollama_num_ctx: int = 16384
    web_search: bool = False
    # Jeder Claude-Aufruf läuft durch G.O.D.A.I. (HERMES/THEMIS/MNEMOSYNE)
    governance: bool = True
    # Ordner-Plugins laufen nur, wenn ihr Name hier steht (beliebiger Code!)
    enabled_plugins: list[str] = field(default_factory=list)
    # Docks (eingebaut / Entry-Point), die abgeschaltet sind
    disabled_docks: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------

    @classmethod
    def path(cls) -> Path:
        return config_dir() / "settings.json"

    @classmethod
    def load(cls) -> Settings:
        data: dict[str, Any] = {}
        if cls.path().exists():
            data = json.loads(cls.path().read_text(encoding="utf-8"))
        known = cls.__dataclass_fields__
        s = cls(**{k: v for k, v in data.items() if k in known})
        if os.environ.get("SCRIPTOR_MODEL"):
            s.model = os.environ["SCRIPTOR_MODEL"]
        if os.environ.get("SCRIPTOR_PROVIDER"):
            s.provider = os.environ["SCRIPTOR_PROVIDER"]
        if os.environ.get("SCRIPTOR_OLLAMA_URL"):
            s.ollama_url = os.environ["SCRIPTOR_OLLAMA_URL"]
        if os.environ.get("SCRIPTOR_OLLAMA_MODEL"):
            s.ollama_model = os.environ["SCRIPTOR_OLLAMA_MODEL"]
        return s

    def save(self) -> None:
        self.path().parent.mkdir(parents=True, exist_ok=True)
        self.path().write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def active_model(self) -> str:
        return f"ollama:{self.ollama_model}" if self.provider == "ollama" else self.model

    def workspace_path(self) -> Path:
        env = os.environ.get("SCRIPTOR_HOME")
        raw = env or self.workspace
        return Path(raw).expanduser().resolve() if raw else default_workspace_dir()

    def plugin_dir(self) -> Path:
        return config_dir() / "plugins"


# ---------------------------------------------------------------------------
# API-Key
# ---------------------------------------------------------------------------


def _keyring() -> Any:
    try:
        import keyring

        return keyring
    except ImportError:
        return None


def get_api_key() -> str | None:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    kr = _keyring()
    if kr is None:
        return None
    try:
        value = kr.get_password(_KEYRING_SERVICE, _KEYRING_USER)
        return str(value) if value else None
    except Exception:
        return None


def set_api_key(key: str) -> bool:
    """Speichert den Key im OS-Tresor. False, wenn kein Tresor verfügbar ist."""
    kr = _keyring()
    if kr is None:
        return False
    try:
        if key:
            kr.set_password(_KEYRING_SERVICE, _KEYRING_USER, key)
        else:
            kr.delete_password(_KEYRING_SERVICE, _KEYRING_USER)
        return True
    except Exception:
        return False


def api_key_status() -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "env"
    return "keyring" if get_api_key() else "missing"
