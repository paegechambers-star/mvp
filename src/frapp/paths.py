"""Datenablage von FraPP (Desktop): Datenbank, ContextOS-Register."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    override = os.environ.get("FRAPP_DATA_DIR")
    if override:
        path = Path(override)
    elif sys.platform == "win32":
        path = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "FraPP"
    else:
        path = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "frapp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def sqlite_url() -> str:
    return "sqlite:///" + (data_dir() / "frapp.db").as_posix()
