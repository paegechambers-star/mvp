"""FraPP-Desktop: Oberfläche, Datenablage, ein Schlüssel für alles, ContextOS-Ansicht."""

from fastapi.testclient import TestClient


def test_shell_served_and_root_redirects():
    import frapp.api as api

    with TestClient(api.app) as c:
        r = c.get("/", follow_redirects=False)
        assert r.status_code in (302, 307) and r.headers["location"] == "/app/"
        page = c.get("/app/")
        assert page.status_code == 200
        for tab in ("Tagesplan", "Kalender", "Scriptor", "G.O.D.A.I.", "ContextOS"):
            assert tab in page.text
        assert "dev-key" not in page.text  # kein Schlüssel in der Seite


def test_prepare_desktop_sets_data_dir_and_single_key(tmp_path, monkeypatch):
    from frapp import cli
    from frapp.settings import settings

    monkeypatch.setenv("FRAPP_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("FRAPP_SCRIPTOR_TOKEN", raising=False)
    old = (settings.database_url, settings.api_key)
    try:
        token = cli.prepare_desktop()
        assert settings.api_key == token and len(token) > 20
        assert settings.database_url.endswith(f"{tmp_path.as_posix()}/frapp.db")
        import os

        assert os.environ["FRAPP_SCRIPTOR_TOKEN"] == token
    finally:
        settings.database_url, settings.api_key = old
        monkeypatch.delenv("FRAPP_SCRIPTOR_TOKEN", raising=False)


def test_contextos_view(tmp_path, monkeypatch):
    from contextos import Actor, Cluster, EntryType, Kind, TruthGate, generate_id

    import frapp.api as api
    from frapp import contextos_view

    monkeypatch.setenv("FRAPP_DATA_DIR", str(tmp_path))
    contextos_view._state.clear()
    H = {"X-API-Key": "dev-key"}
    with TestClient(api.app) as c:
        assert c.get("/v1/contextos/status").status_code == 401
        st = c.get("/v1/contextos/status", headers=H).json()
        assert st["chain_ok"] and st["ssot"] == 0 and str(tmp_path) in st["path"]
        nkid = generate_id(Kind.NK, Actor(list(Actor)[0]), Cluster(list(Cluster)[0]),
                           EntryType(list(EntryType)[0]), TruthGate(list(TruthGate)[0]))
        ok = c.get(f"/v1/contextos/validate/{nkid}", headers=H).json()
        assert ok["valid"] is True
        assert c.get("/v1/contextos/validate/kaputt", headers=H).json()["valid"] is False
        assert c.get("/v1/contextos/entries?partition=x", headers=H).status_code == 422
    contextos_view._state.clear()
