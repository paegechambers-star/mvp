from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from sqlmodel import select, Session
from .settings import settings
from .db import init_db, get_session
from .models import Event


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="FraPP API", version=settings.version, lifespan=lifespan)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "app": settings.app_name, "version": settings.version}


@app.get("/v1/events")
def list_events(session: Session = Depends(get_session)):
    return session.exec(select(Event)).all()
