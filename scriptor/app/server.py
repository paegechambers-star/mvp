"""
Lokaler API-Server der Desktop-App (FastAPI).

Sicherheit:
  - bindet nur an 127.0.0.1 (Launcher)
  - jede /api-Anfrage braucht den pro Start zufällig erzeugten Token
    (Header ``X-Scriptor-Token`` oder ``?token=`` für Downloads)
  - Host-Header muss 127.0.0.1/localhost sein (Schutz vor DNS-Rebinding)
"""

from __future__ import annotations

import hmac
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    StreamingResponse,
)
from pydantic import BaseModel, Field

from scriptor import __version__
from scriptor.agent import Agent
from scriptor.app.jobs import JobConflict, JobManager
from scriptor.chat import ChatError, ChatNotFound, ChatStore, decide, stream_reply
from scriptor.genres import GenreError, all_genres
from scriptor.ghostwriter import Ghostwriter, load_config
from scriptor.project import BookProject, ProjectError, _dump
from scriptor.runtime import Runtime
from scriptor.settings import api_key_status, set_api_key

STATIC = Path(__file__).parent / "static"
_ALLOWED_HOSTS = {"127.0.0.1", "localhost", "testserver"}


# ---------------------------------------------------------------------------
# Request-Modelle
# ---------------------------------------------------------------------------


class NewBook(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    genre: str
    idea: str = Field(min_length=1)
    author: str = ""


class TextFile(BaseModel):
    filename: str = Field(min_length=1, max_length=120)
    content: str


class VoiceIn(BaseModel):
    samples: list[TextFile]
    describe: bool = True


class BiblePatch(BaseModel):
    yaml: str
    reason: str = Field(min_length=1)
    kind: str = "PATCH"


class ChapterEdit(BaseModel):
    text: str = Field(min_length=1)
    reason: str = "Manuelle Bearbeitung in der App"


class ActionIn(BaseModel):
    params: dict[str, Any] = {}


class SettingsIn(BaseModel):
    workspace: str | None = None
    provider: str | None = Field(None, pattern="^(anthropic|ollama)$")
    model: str | None = None
    ollama_url: str | None = None
    ollama_model: str | None = None
    ollama_num_ctx: int | None = Field(None, ge=2048, le=262144)
    web_search: bool | None = None
    enabled_plugins: list[str] | None = None
    disabled_docks: list[str] | None = None


class ApiKeyIn(BaseModel):
    key: str


class ChatNew(BaseModel):
    system: str = ""
    data_class: str = "INTERNAL"
    tools: bool = True


class ChatDecision(BaseModel):
    accept: bool


class ChatMessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=50_000)


class OllamaPullIn(BaseModel):
    model: str = Field(min_length=1, pattern=r"^[A-Za-z0-9._:/-]+$")


class AgentMessage(BaseModel):
    text: str = Field(min_length=1)
    allow_expensive: bool = False


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


def _safe_name(name: str) -> str:
    base = Path(name).name
    if not base or base.startswith(".") or Path(base).suffix.lower() not in (".txt", ".md"):
        raise HTTPException(400, "Nur .txt- oder .md-Dateien erlaubt")
    return base


def create_app(rt: Runtime, token: str, jobs: JobManager | None = None) -> FastAPI:
    app = FastAPI(title="SCRIPTOR", version=__version__, docs_url=None, redoc_url=None)
    jobs = jobs or JobManager()
    sessions: dict[str, dict[str, Any]] = {}
    app.state.jobs = jobs
    app.state.runtime = rt

    def project(slug: str) -> BookProject:
        try:
            return BookProject.load(rt.workspace, slug)
        except ProjectError as exc:
            raise HTTPException(404, str(exc))

    app.state.project = project

    @app.middleware("http")
    async def _guard(request: Request, call_next: Callable[..., Any]) -> Any:
        host = (request.headers.get("host") or "").split(":")[0]
        if host not in _ALLOWED_HOSTS:
            return JSONResponse({"detail": "Host nicht erlaubt"}, status_code=403)
        # Relativer Pfad: bei Einbettung in FraPP (Mount unter /scriptor) enthält
        # scope["path"] das Präfix — die Token-Prüfung muss trotzdem greifen.
        path = request.scope.get("path", "")
        root = request.scope.get("root_path", "")
        if root and path.startswith(root):
            path = path[len(root) :]
        if path.startswith("/api/") or path == "/api":
            given = request.headers.get("x-scriptor-token") or request.query_params.get("token", "")
            if not hmac.compare_digest(given, token):
                return JSONResponse({"detail": "Token fehlt oder falsch"}, status_code=401)
        return await call_next(request)

    @app.exception_handler(ProjectError)
    async def _project_error(request: Request, exc: ProjectError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(JobConflict)
    async def _conflict(request: Request, exc: JobConflict) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=409)

    # -- Oberfläche ----------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (STATIC / "index.html").read_text(encoding="utf-8")

    # -- Info & Einstellungen ------------------------------------------

    @app.get("/api/info")
    def info() -> dict[str, Any]:
        return {
            "version": __version__,
            "model": rt.settings.active_model(),
            "provider": rt.settings.provider,
            "api_key": api_key_status(),
            "workspace": str(rt.workspace),
            "plugin_dir": str(rt.settings.plugin_dir()),
            "docks": [i.__dict__ for i in rt.docks.infos],
            "materials": sorted({**load_config()["materials"], **rt.docks.materials}),
            "governance": rt.governance is not None,
            "host": getattr(app.state, "host_app", "SCRIPTOR"),
        }

    @app.get("/api/governance")
    def governance() -> dict[str, Any]:
        if rt.governance is None:
            return {"active": False}
        return dict(rt.governance.status())

    @app.get("/api/settings")
    def get_settings() -> dict[str, Any]:
        return {**rt.settings.__dict__, "workspace_resolved": str(rt.workspace)}

    @app.put("/api/settings")
    def put_settings(body: SettingsIn) -> dict[str, Any]:
        for k, v in body.model_dump(exclude_none=True).items():
            setattr(rt.settings, k, v)
        rt.settings.save()
        return {"saved": True, "restart_needed_for_plugins": True}

    @app.put("/api/settings/api-key")
    def put_api_key(body: ApiKeyIn) -> dict[str, Any]:
        if not set_api_key(body.key.strip()):
            raise HTTPException(
                501, "Kein OS-Tresor verfügbar — ANTHROPIC_API_KEY als Umgebungsvariable setzen"
            )
        return {"api_key": api_key_status()}

    @app.get("/api/ollama")
    def ollama() -> dict[str, Any]:
        from scriptor.llm import ollama_status

        return {**ollama_status(rt.settings.ollama_url), "model": rt.settings.ollama_model}

    @app.post("/api/ollama/pull")
    def ollama_pull(body: OllamaPullIn) -> dict[str, Any]:
        url = rt.settings.ollama_url.rstrip("/")

        def run(log: Callable[[str], None]) -> str:
            import json

            import httpx

            last = ""
            with httpx.stream(
                "POST", f"{url}/api/pull", json={"model": body.model}, timeout=None
            ) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line:
                        continue
                    ev = json.loads(line)
                    if "error" in ev:
                        raise RuntimeError(ev["error"])
                    status = str(ev.get("status", ""))
                    if ev.get("total"):
                        status += f" {int(100 * ev.get('completed', 0) / ev['total'])} %"
                    if status != last:
                        log(status)
                        last = status
            return f"{body.model} installiert"

        return jobs.submit("ollama pull", f"ollama:{body.model}", run).to_dict()

    # -- Chat ----------------------------------------------------------

    def chats() -> ChatStore:
        return ChatStore(rt.workspace)

    def toolkits() -> list[Any]:
        # von der Host-App gesetzt (FraPP: Kalender/Aufgaben); SCRIPTOR allein: keine
        return list(getattr(app.state, "chat_toolkits", []))

    @app.exception_handler(ChatError)
    async def _chat_error(request: Request, exc: ChatError) -> JSONResponse:
        code = 404 if isinstance(exc, ChatNotFound) else 400
        return JSONResponse({"detail": str(exc)}, status_code=code)

    @app.get("/api/chats")
    def chat_list() -> list[dict[str, Any]]:
        return chats().list()

    @app.post("/api/chats")
    def chat_new(body: ChatNew) -> dict[str, Any]:
        return chats().create(body.system, body.data_class, body.tools)

    @app.get("/api/chats/{chat_id}")
    def chat_get(chat_id: str) -> dict[str, Any]:
        return chats().get(chat_id)

    @app.delete("/api/chats/{chat_id}")
    def chat_delete(chat_id: str) -> dict[str, Any]:
        chats().delete(chat_id)
        return {"deleted": chat_id}

    @app.post("/api/chats/{chat_id}/messages")
    def chat_send(chat_id: str, body: ChatMessageIn) -> StreamingResponse:
        store = chats()
        store.get(chat_id)  # 404 vor Streambeginn
        events = stream_reply(
            store, chat_id, body.text, rt.llm(), rt.settings.active_model(), toolkits()
        )

        def ndjson() -> Any:
            import json

            for ev in events:
                yield json.dumps(ev, ensure_ascii=False) + "\n"

        return StreamingResponse(ndjson(), media_type="application/x-ndjson")

    @app.post("/api/chats/{chat_id}/proposals/{pid}")
    def chat_decide(chat_id: str, pid: str, body: ChatDecision) -> dict[str, Any]:
        try:
            return decide(chats(), chat_id, pid, body.accept, toolkits())
        except ChatError:
            raise
        except ValueError as exc:  # apply() hat abgelehnt, z. B. Termin inzwischen gelöscht
            raise HTTPException(409, str(exc))

    @app.get("/api/chat-tools")
    def chat_tools() -> list[dict[str, Any]]:
        return [
            {"toolkit": k.name, "name": t.name, "writes": t.writes, "description": t.description}
            for k in toolkits()
            for t in k.tools
        ]

    @app.get("/api/genres")
    def genres() -> list[dict[str, Any]]:
        return [
            {
                "id": g.id,
                "name": g.name,
                "audience": g.audience,
                "fiction": g.fiction,
                "target_words": g.target_words,
                "chapters": g.chapters["default"],
                "unit": g.unit_label,
            }
            for g in all_genres()
        ]

    # -- Bücher --------------------------------------------------------

    @app.get("/api/books")
    def books() -> list[dict[str, Any]]:
        out = []
        for slug in BookProject.list_slugs(rt.workspace):
            p = BookProject.load(rt.workspace, slug)
            out.append({"slug": slug, "title": p.title, "genre": p.bible["meta"]["genre"]})
        return out

    @app.post("/api/books")
    def create_book(body: NewBook) -> dict[str, Any]:
        try:
            p = BookProject.create(rt.workspace, body.title, body.genre, body.idea, body.author)
        except GenreError as exc:
            raise HTTPException(400, str(exc))
        return {"slug": p.slug}

    @app.get("/api/books/{slug}")
    def book(slug: str) -> dict[str, Any]:
        p = project(slug)
        exports = sorted(f.name for f in (p.root / "export").glob("*") if f.is_file())
        return {
            "slug": slug,
            "status": p.status(),
            "bible": p.bible,
            "bible_yaml": _dump(p.bible),
            "outline": p.outline,
            "voice": p.read_ssot("voice"),
            "sources": sorted(f.name for f in (p.root / "ssot" / "sources").glob("*")),
            "exports": exports,
            "register": p.register()[-30:],
        }

    @app.get("/api/books/{slug}/chapters/{nr}")
    def chapter(slug: str, nr: int, version: int | None = None) -> dict[str, Any]:
        p = project(slug)
        versions = [v for v, _ in p._chapter_versions(nr)]
        if not versions:
            return {
                "nr": nr,
                "versions": [],
                "text": "",
                "review": None,
                "plan": p.chapter_plan(nr),
            }
        v = version or versions[-1]
        if v not in versions:
            raise HTTPException(404, f"Version {v} existiert nicht")
        text = (p.root / "work" / "chapters" / f"kap-{nr:02d}.v{v}.md").read_text(encoding="utf-8")
        return {
            "nr": nr,
            "version": v,
            "versions": versions,
            "text": text,
            "review": p.read_review(nr, v),
            "plan": p.chapter_plan(nr),
        }

    @app.put("/api/books/{slug}/chapters/{nr}")
    def edit_chapter(slug: str, nr: int, body: ChapterEdit) -> dict[str, Any]:
        p = project(slug)
        p.chapter_plan(nr)
        version, rid = p.write_chapter(nr, body.text.rstrip() + "\n", body.reason)
        return {"version": version, "register_id": rid}

    @app.patch("/api/books/{slug}/bible")
    def patch_bible(slug: str, body: BiblePatch) -> dict[str, Any]:
        p = project(slug)
        try:
            data = yaml.safe_load(body.yaml)
        except yaml.YAMLError as exc:
            raise HTTPException(400, f"YAML ungültig: {exc}")
        if not isinstance(data, dict):
            raise HTTPException(400, "YAML muss ein Mapping sein")
        if body.kind not in ("PATCH", "SUPERSEDE"):
            raise HTTPException(400, "kind muss PATCH oder SUPERSEDE sein")
        if data.get("meta", p.bible["meta"]) != p.bible["meta"]:
            raise HTTPException(400, "meta ist schreibgeschützt")
        data["meta"] = p.bible["meta"]
        return {"register_id": p.commit_ssot("bible", data, body.reason, body.kind)}

    @app.post("/api/books/{slug}/sources")
    def add_source(slug: str, body: TextFile) -> dict[str, Any]:
        name = _safe_name(body.filename)
        return {"register_id": project(slug).add_source_text(name, body.content), "file": name}

    @app.get("/api/books/{slug}/export/{filename}")
    def download(slug: str, filename: str) -> FileResponse:
        p = project(slug)
        target = p.root / "export" / Path(filename).name
        if not target.is_file():
            raise HTTPException(404, "Datei nicht gefunden")
        return FileResponse(target, filename=target.name)

    # -- Aktionen (Jobs) -----------------------------------------------

    def _gw() -> Ghostwriter:
        return Ghostwriter(rt.llm())

    def _action(
        p: BookProject, action: str, params: dict[str, Any]
    ) -> Callable[[Callable[[str], None]], Any]:
        nr = int(params.get("nr", 0))

        def run(log: Callable[[str], None]) -> Any:
            gw = _gw()
            if action == "bible":
                return gw.develop_bible(p, str(params.get("notes", "")))
            if action == "outline":
                return gw.develop_outline(p, params.get("chapters") or None)
            if action == "draft":
                return {"version": gw.draft_chapter(p, nr)}
            if action == "review":
                r = gw.review_chapter(p, nr)
                return r.__dict__
            if action == "revise":
                return {"version": gw.revise_chapter(p, nr, str(params.get("instructions", "")))}
            if action == "write_book":
                res = gw.write_book(
                    p,
                    int(params.get("start") or 1),
                    params.get("end") or None,
                    progress=lambda r: log(
                        f"Kap. {r.nr} v{r.version}: {r.verdict} ({r.score}) " + "; ".join(r.reasons)
                    ),
                )
                return [r.__dict__ for r in res]
            if action == "material":
                agent = Agent(gw.llm, rt.workspace, docks=rt.docks)
                return agent._t_book_material(p.slug, str(params.get("kind", "")))
            if action == "export":
                return str(p.export_markdown().name)
            if action == "export_docx":
                if not any(i.name == "docx_export" and i.loaded for i in rt.docks.infos):
                    raise ValueError("DOCX-Export nicht aktiv (pip install python-docx)")
                from scriptor.docks.builtin import export_docx

                return export_docx(p).name
            if action == "voice":
                return gw.learn_voice(
                    p, [Path(x) for x in params["paths"]], bool(params.get("describe", True))
                )
            raise ValueError(f"Unbekannte Aktion {action}")

        return run

    _ACTIONS = {
        "bible",
        "outline",
        "draft",
        "review",
        "revise",
        "write_book",
        "material",
        "export",
        "export_docx",
    }

    @app.post("/api/books/{slug}/actions/{action}")
    def action(slug: str, action: str, body: ActionIn) -> dict[str, Any]:
        if action not in _ACTIONS:
            raise HTTPException(404, f"Unbekannte Aktion '{action}'")
        p = project(slug)
        job = jobs.submit(action, f"book:{slug}", _action(p, action, body.params))
        return job.to_dict()

    @app.post("/api/books/{slug}/voice")
    def voice(slug: str, body: VoiceIn) -> dict[str, Any]:
        p = project(slug)
        sample_dir = p.root / "ssot" / "voice_samples"
        sample_dir.mkdir(exist_ok=True)
        paths = []
        for f in body.samples:
            target = sample_dir / _safe_name(f.filename)
            target.write_text(f.content, encoding="utf-8")
            paths.append(str(target))
        job = jobs.submit(
            "voice",
            f"book:{slug}",
            _action(p, "voice", {"paths": paths, "describe": body.describe}),
        )
        return job.to_dict()

    @app.get("/api/jobs")
    def list_jobs() -> list[dict[str, Any]]:
        return [j.to_dict() for j in jobs.list()]

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Job nicht gefunden")
        return job.to_dict()

    # -- Agent ---------------------------------------------------------

    @app.post("/api/agent/sessions")
    def new_session() -> dict[str, Any]:
        import uuid

        sid = uuid.uuid4().hex[:12]
        state: dict[str, Any] = {"transcript": [], "allow": False}

        def approve(name: str, args: dict[str, Any]) -> bool:
            state["transcript"].append(
                {
                    "kind": "approval",
                    "text": f"{name}: " + ("freigegeben" if state["allow"] else "abgelehnt"),
                }
            )
            return bool(state["allow"])

        def on_event(kind: str, text: str) -> None:
            state["transcript"].append({"kind": kind, "text": text})

        state["agent"] = Agent(
            rt.llm(),
            rt.workspace,
            approve=approve,
            web_search=rt.settings.web_search,
            on_event=on_event,
            docks=rt.docks,
        )
        sessions[sid] = state
        return {"id": sid}

    @app.post("/api/agent/sessions/{sid}/messages")
    def agent_message(sid: str, body: AgentMessage) -> dict[str, Any]:
        state = sessions.get(sid)
        if state is None:
            raise HTTPException(404, "Sitzung nicht gefunden")

        def run(log: Callable[[str], None]) -> str:
            state["allow"] = body.allow_expensive
            state["transcript"].append({"kind": "user", "text": body.text})
            answer = state["agent"].run(body.text)
            state["transcript"].append({"kind": "answer", "text": answer})
            return str(answer)

        return jobs.submit("agent", f"agent:{sid}", run).to_dict()

    @app.get("/api/agent/sessions/{sid}")
    def agent_session(sid: str) -> dict[str, Any]:
        state = sessions.get(sid)
        if state is None:
            raise HTTPException(404, "Sitzung nicht gefunden")
        return {"id": sid, "transcript": state["transcript"]}

    # -- Dock-Routen ---------------------------------------------------

    for router in rt.docks.routers:
        app.include_router(router)

    return app
