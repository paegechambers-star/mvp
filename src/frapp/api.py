from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from sqlmodel import select, Session
from .settings import settings
from .db import init_db, get_session
from .models import Event
from godai.modules.mnemosyne import Mnemosyne
from godai.modules.hermes import Hermes
from godai.modules.dispatch_bridge import DispatchBridge
from .mobile_dispatch import build_router
from .mcp_dispatch import build_mcp_router
from .chat import router as chat_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    mnemosyne = Mnemosyne()
    hermes = Hermes(mnemosyne=mnemosyne)
    bridge = DispatchBridge(mnemosyne=mnemosyne)
    app.include_router(build_router(bridge, hermes))
    app.include_router(build_mcp_router(bridge, hermes))
    app.include_router(chat_router)
    yield


app = FastAPI(title="FraPP API", version=settings.version, lifespan=lifespan)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "app": settings.app_name, "version": settings.version}


@app.get("/v1/events")
def list_events(session: Session = Depends(get_session)):
    return session.exec(select(Event)).all()
