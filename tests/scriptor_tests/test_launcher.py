import httpx

from scriptor.app.launcher import start_server
from scriptor.runtime import Runtime
from scriptor.settings import Settings


def test_server_starts_on_localhost_with_token(tmp_path):
    rt = Runtime.create(Settings(workspace=str(tmp_path / "ws")), include_entry_points=False)
    server, url = start_server(rt)
    try:
        base, token = url.split("/#token=")
        assert base.startswith("http://127.0.0.1:")
        assert httpx.get(base + "/api/info").status_code == 401
        r = httpx.get(base + "/api/info", headers={"X-Scriptor-Token": token})
        assert r.status_code == 200 and r.json()["version"]
    finally:
        server.should_exit = True


def test_server_starts_without_console(tmp_path, monkeypatch):
    """Regression: pythonw.exe (Desktop-Verknüpfung) hat sys.stdout/stderr = None."""
    import sys

    from scriptor.app import launcher

    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    logfile = launcher.ensure_streams()
    assert logfile is not None and sys.stdout is not None and sys.stderr is not None
    rt = Runtime.create(Settings(workspace=str(tmp_path / "ws")), include_entry_points=False)
    server, url = start_server(rt)
    try:
        base, token = url.split("/#token=")
        assert httpx.get(base + "/api/info", headers={"X-Scriptor-Token": token}).status_code == 200
    finally:
        server.should_exit = True
        sys.stdout.close()


def test_window_failure_falls_back(monkeypatch):
    import sys
    import types

    from scriptor.app import launcher

    def boom(*a, **k):
        raise RuntimeError("WebView2 fehlt")

    monkeypatch.setitem(
        sys.modules, "webview", types.SimpleNamespace(create_window=boom, start=boom)
    )
    assert launcher._open_window("http://127.0.0.1:1/") is False
