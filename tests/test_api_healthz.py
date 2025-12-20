from fastapi.testclient import TestClient
from frapp.api import app


def test_healthz_status_ok():
    c = TestClient(app)
    r = c.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "ok"
    assert "version" in body
