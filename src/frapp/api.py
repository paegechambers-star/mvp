"""FraPP FastAPI application — SaaS-ready: auth, CORS, CRUD, G.O.D.A.I., metrics, metering."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Security, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from sqlmodel import Session, func, select

from .db import get_session, init_db
from .logging_config import configure_logging
from .metrics import setup_metrics
from .models import Event, UsageRecord
from .rate_limiter import limiter, rate_limit_exceeded_handler  # noqa: F401
from .settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(
        log_level=settings.log_level,
        json_logs=(settings.env == "production"),
    )
    init_db()
    yield


app = FastAPI(
    title="FraPP API",
    version=settings.version,
    lifespan=lifespan,
    description="FraPP — AI-governed event management API powered by G.O.D.A.I.",
)

# ── Prometheus metrics (Q3) ───────────────────────────────────────────────────
setup_metrics(app)

# ── Rate limiting (K2) — register limiter with app state ─────────────────────
if limiter is not None:
    try:
        from slowapi.errors import RateLimitExceeded  # type: ignore[import]
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    except ImportError:
        pass

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


# ── Header helpers ────────────────────────────────────────────────────────────
def get_caller_id(x_user_id: Optional[str] = Header(default=None)) -> Optional[str]:
    """Extract caller identity from X-User-ID header (used for GDPR scoping)."""
    return x_user_id


def get_tenant_id(x_tenant_id: Optional[str] = Header(default=None)) -> Optional[str]:
    """Extract tenant from X-Tenant-ID header for row-level data isolation (BR1)."""
    return x_tenant_id


# ── Usage metering middleware (BR4) ──────────────────────────────────────────
@app.middleware("http")
async def _meter_requests(request: Request, call_next):
    response = await call_next(request)
    tenant_id = request.headers.get("X-Tenant-ID")
    if tenant_id and request.url.path.startswith("/v1/"):
        try:
            from .db import engine as _engine
            with Session(_engine) as _s:
                _s.add(UsageRecord(
                    tenant_id=tenant_id,
                    endpoint=request.url.path,
                    method=request.method,
                    status_code=response.status_code,
                ))
                _s.commit()
        except Exception:
            pass  # never crash the request pipeline on metering failure
    return response


# ── Pydantic schemas (Q7) ─────────────────────────────────────────────────────
class EventCreate(BaseModel):
    title: str
    starts_at: datetime
    ends_at: datetime
    location: Optional[str] = None
    all_day: bool = False
    owner: Optional[str] = None


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
    owner: Optional[str] = None
    tenant_id: Optional[str] = None

    model_config = {"from_attributes": True}


class PaginatedEvents(BaseModel):
    data: List[EventResponse]
    total: int
    limit: int
    offset: int


# ── Health endpoints (K5) ─────────────────────────────────────────────────────
class LivenessResponse(BaseModel):
    status: str


@app.get("/healthz/live", response_model=LivenessResponse, tags=["Health"], summary="Liveness probe")
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
    tenant_id: Optional[str] = Depends(get_tenant_id),
):
    q = select(Event)
    cq = select(func.count()).select_from(Event)
    if tenant_id:
        q = q.where(Event.tenant_id == tenant_id)
        cq = cq.where(Event.tenant_id == tenant_id)
    total = session.exec(cq).one()
    events = session.exec(q.offset(offset).limit(limit)).all()
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
def create_event(
    payload: EventCreate,
    session: Session = Depends(get_session),
    caller_id: Optional[str] = Depends(get_caller_id),
    tenant_id: Optional[str] = Depends(get_tenant_id),
):
    data = payload.model_dump()
    if data.get("owner") is None and caller_id:
        data["owner"] = caller_id
    if tenant_id:
        data["tenant_id"] = tenant_id
    event = Event(**data)
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


# ── GDPR endpoints (Art. 15 / 17 / 20) ───────────────────────────────────────
class UserDataResponse(BaseModel):
    user_id: str
    events: List[EventResponse]
    event_count: int
    message: str = "Your data retrieved under GDPR Art. 15"


@app.get(
    "/v1/me/data",
    response_model=UserDataResponse,
    tags=["GDPR"],
    summary="Art. 15 — Right of access: retrieve all your stored data",
    dependencies=[Depends(require_api_key)],
)
def gdpr_get_data(
    caller_id: Optional[str] = Depends(get_caller_id),
    session: Session = Depends(get_session),
):
    if not caller_id:
        raise HTTPException(status_code=400, detail="X-User-ID header required for GDPR data access")
    events = session.exec(select(Event).where(Event.owner == caller_id)).all()
    return UserDataResponse(
        user_id=caller_id,
        events=[EventResponse.model_validate(e) for e in events],
        event_count=len(events),
    )


@app.delete(
    "/v1/me/data",
    status_code=status.HTTP_200_OK,
    tags=["GDPR"],
    summary="Art. 17 — Right to erasure: delete all your stored data",
    dependencies=[Depends(require_api_key)],
)
def gdpr_delete_data(
    caller_id: Optional[str] = Depends(get_caller_id),
    session: Session = Depends(get_session),
):
    if not caller_id:
        raise HTTPException(status_code=400, detail="X-User-ID header required for GDPR erasure")
    events = session.exec(select(Event).where(Event.owner == caller_id)).all()
    deleted = len(events)
    for event in events:
        session.delete(event)
    session.commit()
    return {
        "user_id": caller_id,
        "deleted_events": deleted,
        "message": "All your data has been erased under GDPR Art. 17",
    }


@app.get(
    "/v1/me/export",
    tags=["GDPR"],
    summary="Art. 20 — Data portability: export all your data as JSON",
    dependencies=[Depends(require_api_key)],
)
def gdpr_export_data(
    caller_id: Optional[str] = Depends(get_caller_id),
    session: Session = Depends(get_session),
):
    if not caller_id:
        raise HTTPException(status_code=400, detail="X-User-ID header required for GDPR export")
    events = session.exec(select(Event).where(Event.owner == caller_id)).all()
    return {
        "export_format": "application/json",
        "gdpr_article": "Art. 20 — Right to data portability",
        "user_id": caller_id,
        "events": [EventResponse.model_validate(e).model_dump(mode="json") for e in events],
    }


# ── Admin: Usage metering (BR4) ───────────────────────────────────────────────
@app.get(
    "/v1/admin/usage",
    tags=["Admin"],
    summary="Per-tenant request usage for billing and capacity planning",
    dependencies=[Depends(require_api_key)],
)
def admin_usage(
    tenant_id: Optional[str] = None,
    session: Session = Depends(get_session),
):
    q = select(UsageRecord)
    if tenant_id:
        q = q.where(UsageRecord.tenant_id == tenant_id)
    records = session.exec(q).all()

    by_tenant: dict = {}
    for r in records:
        if r.tenant_id not in by_tenant:
            by_tenant[r.tenant_id] = {"total_requests": 0, "endpoints": {}}
        by_tenant[r.tenant_id]["total_requests"] += 1
        ep = r.endpoint
        by_tenant[r.tenant_id]["endpoints"][ep] = (
            by_tenant[r.tenant_id]["endpoints"].get(ep, 0) + 1
        )

    return {
        "tenants": by_tenant,
        "total_tenants": len(by_tenant),
        "total_requests": sum(v["total_requests"] for v in by_tenant.values()),
    }


# ── Include G.O.D.A.I. router (B4) ───────────────────────────────────────────
from .godai_router import router as godai_router  # noqa: E402

app.include_router(godai_router, dependencies=[Depends(require_api_key)])
