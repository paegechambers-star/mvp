import time

import pytest
from fastapi.testclient import TestClient

from scriptor.app.jobs import JobConflict, JobManager
from scriptor.app.server import create_app
from scriptor.llm import AgentTurn
from scriptor.runtime import Runtime
from scriptor.settings import Settings

from .conftest import chapter_text, make_llm

TOKEN = "t0k3n"
H = {"X-Scriptor-Token": TOKEN}


@pytest.fixture
def ctx(tmp_path):
    llm = make_llm(n_chapters=2)
    rt = Runtime.create(
        Settings(workspace=str(tmp_path / "ws")),
        llm_factory=lambda rt: llm,
        include_entry_points=False,
    )
    jobs = JobManager()
    client = TestClient(create_app(rt, TOKEN, jobs))
    return client, jobs, llm, rt


def _job(ctx, resp):
    assert resp.status_code == 200, resp.text
    job = ctx[1].wait(resp.json()["id"])
    assert job.status == "done", job.error + "\n".join(job.log)
    return job


def test_auth_and_host_guard(ctx):
    client = ctx[0]
    assert client.get("/api/info").status_code == 401
    assert client.get("/api/info", headers={"X-Scriptor-Token": "falsch"}).status_code == 401
    assert client.get("/api/info", headers={**H, "host": "evil.example"}).status_code == 403
    assert client.get("/").status_code == 200 and "SCRIPTOR" in client.get("/").text
    info = client.get("/api/info", headers=H).json()
    assert info["api_key"] == "missing" and "expose" in info["materials"]


def test_book_lifecycle(ctx):
    client = ctx[0]
    r = client.post(
        "/api/books", headers=H, json={"title": "App Buch", "genre": "young_adult", "idea": "x"}
    )
    slug = r.json()["slug"]
    assert (
        client.post(
            "/api/books", headers=H, json={"title": "Y", "genre": "nope", "idea": "x"}
        ).status_code
        == 400
    )
    assert [b["slug"] for b in client.get("/api/books", headers=H).json()] == [slug]

    _job(
        ctx,
        client.post(f"/api/books/{slug}/actions/bible", headers=H, json={"params": {"notes": "n"}}),
    )
    _job(
        ctx,
        client.post(
            f"/api/books/{slug}/actions/outline", headers=H, json={"params": {"chapters": 2}}
        ),
    )
    job = _job(
        ctx, client.post(f"/api/books/{slug}/actions/write_book", headers=H, json={"params": {}})
    )
    assert len(job.result) == 2 and any("Kap. 1" in line for line in job.log)

    b = client.get(f"/api/books/{slug}", headers=H).json()
    assert b["status"]["has_outline"] and b["status"]["words_total"] > 0 and b["register"]

    ch = client.get(f"/api/books/{slug}/chapters/1", headers=H).json()
    assert ch["versions"] == [1] and ch["review"]["verdict"] == "PASS"
    r = client.put(f"/api/books/{slug}/chapters/1", headers=H, json={"text": "Meine Fassung."})
    assert r.json()["version"] == 2
    assert (
        client.get(f"/api/books/{slug}/chapters/1?version=2", headers=H)
        .json()["text"]
        .startswith("Meine")
    )
    assert client.get(f"/api/books/{slug}/chapters/1?version=9", headers=H).status_code == 404

    _job(ctx, client.post(f"/api/books/{slug}/actions/export", headers=H, json={"params": {}}))
    dl = client.get(f"/api/books/{slug}/export/{slug}.md?token={TOKEN}")
    assert dl.status_code == 200 and "Meine Fassung." in dl.text
    assert (
        client.get(f"/api/books/{slug}/export/..%2F..%2Fregister.jsonl?token={TOKEN}").status_code
        == 404
    )

    job = _job(
        ctx, client.post(f"/api/books/{slug}/actions/export_docx", headers=H, json={"params": {}})
    )
    assert job.result.endswith(".docx")
    assert (
        client.post(f"/api/books/{slug}/actions/rm", headers=H, json={"params": {}}).status_code
        == 404
    )


def test_bible_patch_rules(ctx):
    client = ctx[0]
    slug = client.post(
        "/api/books", headers=H, json={"title": "B", "genre": "roman", "idea": "x"}
    ).json()["slug"]
    ok = client.patch(
        f"/api/books/{slug}/bible", headers=H, json={"yaml": "tone: düster", "reason": "Wunsch"}
    )
    assert ok.status_code == 200
    assert client.get(f"/api/books/{slug}", headers=H).json()["bible"]["tone"] == "düster"
    bad_meta = client.patch(
        f"/api/books/{slug}/bible", headers=H, json={"yaml": "meta: {title: X}", "reason": "r"}
    )
    assert bad_meta.status_code == 400
    assert (
        client.patch(
            f"/api/books/{slug}/bible", headers=H, json={"yaml": "- liste", "reason": "r"}
        ).status_code
        == 400
    )
    assert (
        client.patch(
            f"/api/books/{slug}/bible", headers=H, json={"yaml": "a: 1", "reason": ""}
        ).status_code
        == 422
    )


def test_sources_and_voice(ctx):
    client = ctx[0]
    slug = client.post(
        "/api/books", headers=H, json={"title": "M", "genre": "memoir", "idea": "x"}
    ).json()["slug"]
    r = client.post(
        f"/api/books/{slug}/sources",
        headers=H,
        json={"filename": "../../int.md", "content": "Kiel 1961"},
    )
    assert r.json()["file"] == "int.md"
    assert (
        client.post(
            f"/api/books/{slug}/sources", headers=H, json={"filename": "x.exe", "content": "x"}
        ).status_code
        == 400
    )
    assert client.get(f"/api/books/{slug}", headers=H).json()["sources"] == ["int.md"]
    sample = {"filename": "probe.txt", "content": chapter_text(600)}
    _job(ctx, client.post(f"/api/books/{slug}/voice", headers=H, json={"samples": [sample]}))
    assert client.get(f"/api/books/{slug}", headers=H).json()["voice"]["metrics"]


def test_job_conflict_per_book():
    jobs = JobManager()
    jobs.submit("slow", "book:a", lambda log: time.sleep(0.3))
    with pytest.raises(JobConflict):
        jobs.submit("other", "book:a", lambda log: None)
    j = jobs.submit("ok", "book:b", lambda log: 1)
    assert jobs.wait(j.id).result == 1
    bad = jobs.submit("bad", "book:c", lambda log: 1 / 0)
    assert jobs.wait(bad.id).status == "error" and "ZeroDivision" in bad.error


def test_agent_session_and_approval(ctx):
    client, _jobs, llm, _rt = ctx
    llm._script = [
        AgentTurn(
            [],
            "tool_use",
            "",
            [
                {
                    "id": "a",
                    "name": "create_book",
                    "input": {"title": "Ag", "genre": "roman", "idea": "x"},
                }
            ],
        ),
        AgentTurn(
            [], "tool_use", "", [{"id": "b", "name": "develop_bible", "input": {"slug": "ag"}}]
        ),
        AgentTurn([{"type": "text", "text": "fertig"}], "end_turn", "fertig"),
    ]
    sid = client.post("/api/agent/sessions", headers=H).json()["id"]
    job = _job(
        ctx,
        client.post(
            f"/api/agent/sessions/{sid}/messages",
            headers=H,
            json={"text": "mach", "allow_expensive": False},
        ),
    )
    assert job.result == "fertig"
    t = client.get(f"/api/agent/sessions/{sid}", headers=H).json()["transcript"]
    kinds = [m["kind"] for m in t]
    assert kinds[0] == "user" and kinds.count("answer") == 1
    assert sum(m["text"] == "fertig" for m in t) == 1  # Schlussantwort nicht doppelt
    assert any(m["kind"] == "approval" and "abgelehnt" in m["text"] for m in t)
    assert client.get("/api/agent/sessions/nope", headers=H).status_code == 404


def test_dock_route_and_settings(ctx):
    client, _, _, rt = ctx
    slug = client.post(
        "/api/books", headers=H, json={"title": "L", "genre": "erstleser", "idea": "x"}
    ).json()["slug"]
    assert client.get(f"/api/docks/lesbarkeit/{slug}", headers=H).json() == []
    assert client.get(f"/api/docks/lesbarkeit/{slug}").status_code == 401
    r = client.put(
        "/api/settings", headers=H, json={"model": "claude-sonnet-5-5", "web_search": True}
    )
    assert r.status_code == 200 and rt.settings.model == "claude-sonnet-5-5"
    assert Settings.load().web_search is True
