"""
SCRIPTOR als FraPP-Dock: KI-Ghostwriter unter ``/scriptor/``, CLI unter ``frapp scriptor``.

Jeder Claude-Aufruf von SCRIPTOR läuft durch G.O.D.A.I. (siehe ``scriptor/governance.py``).
Zugriff auf ``/scriptor/api/*`` nur mit dem Start-Token (Header ``X-Scriptor-Token``);
Token aus ``FRAPP_SCRIPTOR_TOKEN`` oder pro Start zufällig erzeugt.
"""

from __future__ import annotations

import os
import secrets
from typing import Any

from . import Dock

MOUNT_PATH = "/scriptor"


class ScriptorDock(Dock):
    name = "scriptor"

    def __init__(self) -> None:
        self.token = os.environ.get("FRAPP_SCRIPTOR_TOKEN") or secrets.token_urlsafe(24)
        self.runtime: Any = None

    def load(self) -> bool:
        from scriptor.runtime import Runtime

        self.runtime = Runtime.create()
        return True

    def mount(self, app: Any) -> None:
        from scriptor.app.server import create_app

        sub = create_app(self.runtime, self.token)
        sub.state.host_app = "FraPP"
        app.mount(MOUNT_PATH, sub)
        app.state.scriptor_token = self.token

    def url(self, base: str) -> str:
        return f"{base.rstrip('/')}{MOUNT_PATH}/#token={self.token}"

    def cli(self) -> Any | None:
        from scriptor.cli import build_app

        return build_app()
