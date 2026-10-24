from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from sqlmodel import select, Session
from .settings import settings
from .db import init_db, get_session
from .models import Event
from .docks import load_docks


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="FraPP API", version=settings.version, lifespan=lifespan)

# Docks (Plugins) einhängen — z. B. SCRIPTOR unter /scriptor/
DOCKS = load_docks()
for _dock in DOCKS:
    _dock.mount(app)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "app": settings.app_name, "version": settings.version}


@app.get("/v1/docks")
def list_docks():
    return [{"name": d.name} for d in DOCKS]


@app.get("/v1/events")
def list_events(session: Session = Depends(get_session)):
    return session.exec(select(Event)).all()
