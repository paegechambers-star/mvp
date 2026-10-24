"""SCRIPTOR als FraPP-Dock: eine App, ein Server, G.O.D.A.I. aktiv."""

import subprocess
import sys

import httpx
from fastapi.testclient import TestClient

from frapp.api import DOCKS
from frapp.api import app as frapp_app
from frapp.docks import Dock, load_docks


def _client():
    client = TestClient(frapp_app)
    client.__enter__()  # Lifespan ausführen (init_db) wie im echten Start
    return client, frapp_app.state.scriptor_token


def test_frapp_and_scriptor_share_one_server():
    client, token = _client()
    assert client.get("/healthz").json()["status"] == "ok"  # FraPP unverändert
    assert {"name": "scriptor"} in client.get("/v1/docks").json()
    page = client.get("/scriptor/")
    assert page.status_code == 200 and "SCRIPTOR" in page.text
    info = client.get("/scriptor/api/info", headers={"X-Scriptor-Token": token}).json()
    assert info["host"] == "FraPP" and info["governance"] is True


def test_token_enforced_when_mounted():
    """Regression: unter /scriptor enthält scope['path'] das Präfix."""
    client, token = _client()
    assert client.get("/scriptor/api/info").status_code == 401
    assert client.get("/scriptor/api/books", headers={"X-Scriptor-Token": "falsch"}).status_code == 401
    assert client.get("/scriptor/api/governance", headers={"X-Scriptor-Token": token}).json()["active"]


def test_failing_dock_does_not_break_frapp(monkeypatch):
    class Broken(Dock):
        name = "kaputt"

        def load(self):
            raise RuntimeError("boom")

    class Off(Dock):
        name = "aus"

    monkeypatch.setenv("FRAPP_DISABLED_DOCKS", "aus")
    assert [d.name for d in load_docks([Broken(), Off(), Dock()])] == ["dummy"]
    assert any(d.name == "scriptor" for d in DOCKS)


def test_frapp_cli_includes_scriptor():
    out = subprocess.run([sys.executable, "-m", "frapp.cli", "scriptor", "genres"],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert "young_adult" in out.stdout


def test_desktop_server_serves_frapp_with_scriptor(tmp_path):
    from scriptor.app.launcher import start_server

    scriptor = next(d for d in DOCKS if d.name == "scriptor")
    server, url = start_server(scriptor.runtime, asgi=frapp_app, token=scriptor.token, path="/scriptor/")
    try:
        assert "/scriptor/#token=" in url
        base = url.split("/scriptor/")[0]
        assert httpx.get(base + "/healthz").json()["status"] == "ok"
        assert httpx.get(base + "/scriptor/api/info",
                         headers={"X-Scriptor-Token": scriptor.token}).status_code == 200
    finally:
        server.should_exit = True
