"""FraPP FastAPI application — Sprint 1: auth, CORS, full CRUD, G.O.D.A.I. HTTP."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from sqlmodel import Session, func, select

from .db import get_session, init_db
from .models import Event
from .settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="FraPP API",
    version=settings.version,
    lifespan=lifespan,
    description="FraPP — AI-governed event management API powered by G.O.D.A.I.",
)

# ── CORS (B5) ────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Auth (B1) ─────────────────────────────────────────────────────────────────
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(api_key: str = Security(_api_key_header)) -> str:
    if not api_key or api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return api_key


# ── RFC 7807 error handlers (K4) ──────────────────────────────────────────────
@app.exception_handler(HTTPException)
async def _http_exc(request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "type": f"https://httpstatuses.com/{exc.status_code}",
            "title": exc.detail,
            "status": exc.status_code,
        },
    )


@app.exception_handler(RequestValidationError)
async def _validation_exc(request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "type": "https://httpstatuses.com/422",
            "title": "Validation Error",
            "status": 422,
            "detail": exc.errors(),
        },
    )


# ── Pydantic schemas (Q7) ─────────────────────────────────────────────────────
class EventCreate(BaseModel):
    title: str
    starts_at: datetime
    ends_at: datetime
    location: Optional[str] = None
    all_day: bool = False


class EventUpdate(BaseModel):
    title: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    location: Optional[str] = None
    all_day: Optional[bool] = None


class EventResponse(BaseModel):
    id: int
    title: str
    starts_at: datetime
    ends_at: datetime
    location: Optional[str]
    all_day: bool

    model_config = {"from_attributes": True}


class PaginatedEvents(BaseModel):
    data: List[EventResponse]
    total: int
    limit: int
    offset: int


# ── Health endpoints (K5) ─────────────────────────────────────────────────────
@app.get("/healthz/live", tags=["Health"], summary="Liveness probe")
def liveness():
    return {"status": "alive"}


@app.get("/healthz", tags=["Health"], summary="Readiness probe — checks DB")
def healthz(session: Session = Depends(get_session)):
    try:
        session.exec(select(Event)).first()
        db_ok = True
    except Exception:
        db_ok = False

    if not db_ok:
        raise HTTPException(status_code=503, detail="Database unavailable")

    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.version,
        "db": "ok",
    }


# ── Events CRUD (B3) + Pagination (Q1) ───────────────────────────────────────
@app.get(
    "/v1/events",
    response_model=PaginatedEvents,
    tags=["Events"],
    summary="List events with pagination",
    dependencies=[Depends(require_api_key)],
)
def list_events(
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_session),
):
    total = session.exec(select(func.count()).select_from(Event)).one()
    events = session.exec(select(Event).offset(offset).limit(limit)).all()
    return PaginatedEvents(
        data=[EventResponse.model_validate(e) for e in events],
        total=total,
        limit=limit,
        offset=offset,
    )


@app.post(
    "/v1/events",
    response_model=EventResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Events"],
    summary="Create a new event",
    dependencies=[Depends(require_api_key)],
)
def create_event(payload: EventCreate, session: Session = Depends(get_session)):
    event = Event(**payload.model_dump())
    session.add(event)
    session.commit()
    session.refresh(event)
    return EventResponse.model_validate(event)


@app.get(
    "/v1/events/{event_id}",
    response_model=EventResponse,
    tags=["Events"],
    summary="Get a single event by ID",
    dependencies=[Depends(require_api_key)],
)
def get_event(event_id: int, session: Session = Depends(get_session)):
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return EventResponse.model_validate(event)


@app.put(
    "/v1/events/{event_id}",
    response_model=EventResponse,
    tags=["Events"],
    summary="Update an event",
    dependencies=[Depends(require_api_key)],
)
def update_event(
    event_id: int,
    payload: EventUpdate,
    session: Session = Depends(get_session),
):
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(event, field, value)
    session.add(event)
    session.commit()
    session.refresh(event)
    return EventResponse.model_validate(event)


@app.delete(
    "/v1/events/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Events"],
    summary="Delete an event",
    dependencies=[Depends(require_api_key)],
)
def delete_event(event_id: int, session: Session = Depends(get_session)):
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    session.delete(event)
    session.commit()


# ── Include G.O.D.A.I. router (B4) ───────────────────────────────────────────
from .godai_router import router as godai_router  # noqa: E402

app.include_router(godai_router, dependencies=[Depends(require_api_key)])
