"""
Startet die Desktop-App: lokaler Server auf 127.0.0.1 + eigenes Fenster.

Fenster: pywebview (unter Windows Edge WebView2, ab Windows 10/11 vorinstalliert).
Fehlt pywebview oder scheitert das Fenster, öffnet sich der Standardbrowser. Der
Zugriffstoken wird im URL-Fragment übergeben (``#token=…``) — Fragmente werden nie
an den Server gesendet und landen nicht in Logs.

Ohne Konsole (``pythonw.exe``, Desktop-Verknüpfung) sind ``sys.stdout``/``sys.stderr``
``None``. Dann wird nach ``<config>/scriptor.log`` umgeleitet, und ein fataler Fehler
erscheint unter Windows als Meldungsfenster statt still zu verschwinden.
"""

from __future__ import annotations

import logging
import secrets
import socket
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path
from typing import Any, List, Optional

from scriptor.runtime import Runtime
from scriptor.settings import config_dir

_log = logging.getLogger("scriptor.launcher")


def log_path() -> Path:
    return config_dir() / "scriptor.log"


def ensure_streams() -> Optional[Path]:
    """Leitet fehlende Standardströme (pythonw) in die Logdatei um. Gibt den Pfad zurück."""
    if sys.stdout is not None and sys.stderr is not None:
        return None
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = open(path, "a", encoding="utf-8", buffering=1)  # noqa: SIM115 - lebt bis Prozessende
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream
    return path


def _show_error(message: str) -> None:
    """Fehlermeldung sichtbar machen — auch ohne Konsole."""
    print(message, file=sys.stderr, flush=True)
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, "SCRIPTOR – Fehler", 0x10)
        except Exception:  # noqa: BLE001
            pass


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def start_server(
    rt: Runtime,
    port: int = 0,
    asgi: Any = None,
    token: Optional[str] = None,
    path: str = "/",
) -> tuple[Any, str]:
    """
    Startet uvicorn im Hintergrund-Thread. Gibt (server, url) zurück.

    Standard: SCRIPTOR allein. Mit ``asgi``/``token``/``path`` wird eine fremde App
    gestartet, in die SCRIPTOR eingebettet ist (FraPP: ``path="/scriptor/"``).
    """
    import uvicorn

    port = port or _free_port()
    if asgi is None:
        from scriptor.app.server import create_app

        token = secrets.token_urlsafe(24)
        app = create_app(rt, token)
    else:
        if not token:
            raise ValueError("token ist bei eigener ASGI-App Pflicht")
        app = asgi
    # use_colors=False: uvicorn ruft sonst sys.stdout.isatty() auf (Absturz unter pythonw)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", use_colors=False)
    server = uvicorn.Server(config)
    errors: List[BaseException] = []

    def run() -> None:
        try:
            server.run()
        except BaseException as exc:  # noqa: BLE001 - an den Aufrufer melden
            errors.append(exc)

    thread = threading.Thread(target=run, name="scriptor-server", daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if errors or not thread.is_alive() or time.monotonic() > deadline:
            detail = f": {type(errors[0]).__name__}: {errors[0]}" if errors else ""
            raise RuntimeError(f"Server konnte nicht starten{detail}")
        time.sleep(0.05)
    return server, f"http://127.0.0.1:{port}{path}#token={token}"


def _open_window(url: str, title: str = "SCRIPTOR") -> bool:
    """Eigenes Fenster (pywebview). False, wenn nicht möglich → Browser-Fallback."""
    try:
        import webview
    except ImportError:
        return False
    try:
        webview.create_window(title, url, width=1400, height=900, min_size=(900, 600))
        webview.start()
        return True
    except Exception:  # noqa: BLE001 - z. B. WebView2/pythonnet fehlt
        print("Fenster nicht möglich, öffne Browser:\n" + traceback.format_exc(), file=sys.stderr)
        return False


def launch(
    rt: Runtime,
    port: int = 0,
    prefer_window: bool = True,
    asgi: Any = None,
    token: Optional[str] = None,
    path: str = "/",
    title: str = "SCRIPTOR",
) -> None:
    logfile = ensure_streams()
    try:
        server, url = start_server(rt, port, asgi=asgi, token=token, path=path)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        hint = f"\n\nDetails: {logfile}" if logfile else ""
        _show_error(f"{title} konnte nicht starten.\n\n{exc}{hint}")
        raise SystemExit(1) from exc
    try:
        if prefer_window and _open_window(url, title):
            return
        opened = webbrowser.open(url)
        print(
            (f"{title} läuft im Browser." if opened else "Browser bitte manuell öffnen:")
            + f"\n  {url}\nZum Beenden Strg+C drücken.",
            flush=True,
        )
        if logfile is not None and not opened:
            _show_error(f"Bitte im Browser öffnen:\n{url}")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.should_exit = True
