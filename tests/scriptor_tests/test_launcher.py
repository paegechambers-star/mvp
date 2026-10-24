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
