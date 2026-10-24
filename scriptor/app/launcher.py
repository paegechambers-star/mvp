"""
Startet die Desktop-App: lokaler Server auf 127.0.0.1 + eigenes Fenster.

Fenster: pywebview (unter Windows Edge WebView2, ab Windows 10/11 vorinstalliert).
Fehlt pywebview, öffnet sich der Standardbrowser. Der Zugriffstoken wird im
URL-Fragment übergeben (``#token=…``) — Fragmente werden nie an den Server
gesendet und landen nicht in Logs.
"""

from __future__ import annotations

import secrets
import socket
import threading
import time
import webbrowser
from typing import Any

from scriptor.runtime import Runtime


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def start_server(rt: Runtime, port: int = 0) -> tuple[Any, str]:
    """Startet uvicorn im Hintergrund-Thread. Gibt (server, url) zurück."""
    import uvicorn

    from scriptor.app.server import create_app

    token = secrets.token_urlsafe(24)
    port = port or _free_port()
    app = create_app(rt, token)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="scriptor-server", daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            raise RuntimeError("Server konnte nicht starten")
        time.sleep(0.05)
    return server, f"http://127.0.0.1:{port}/#token={token}"


def launch(rt: Runtime, port: int = 0, prefer_window: bool = True) -> None:
    server, url = start_server(rt, port)
    try:
        if prefer_window:
            try:
                import webview

                webview.create_window("SCRIPTOR", url, width=1400, height=900, min_size=(900, 600))
                webview.start()
                return
            except ImportError:
                pass
        opened = webbrowser.open(url)
        print(
            ("SCRIPTOR läuft im Browser." if opened else "Browser bitte manuell öffnen:")
            + f"\n  {url}\nZum Beenden Strg+C drücken.",
            flush=True,
        )
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.should_exit = True
