"""HTTP-API: Aufgaben (CRUD) und Tagesplan. Auth wird beim Einbinden gesetzt."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session, select

from ..db import get_session
from ..models import Event
from ..settings import settings
from .engine import build_day_plan
from .models import Certainty, Constraint, Task
from .timesource import BERLIN, now_cached

router = APIRouter(prefix="/v1", tags=["Tagesplaner"])


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    from zoneinfo import ZoneInfo

    return value.replace(tzinfo=ZoneInfo(settings.timezone))


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    duration_min: int = Field(default=30, ge=5, le=720)
    constraint: Constraint = Constraint.SOFT
    domain: str = Field(default="Allgemein", max_length=60)
    fixed_start: datetime | None = None
    day: date | None = None
    due: date | None = None
    priority: int = Field(default=2, ge=1, le=3)
    source: str = Field(default="Nutzereingabe", max_length=120)
    certainty: Certainty = Certainty.VERIFIED

    _tz = field_validator("fixed_start")(_aware)


class TaskPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    duration_min: int | None = Field(default=None, ge=5, le=720)
    constraint: Constraint | None = None
    domain: str | None = None
    fixed_start: datetime | None = None
    day: date | None = None
    due: date | None = None
    priority: int | None = Field(default=None, ge=1, le=3)
    source: str | None = None
    certainty: Certainty | None = None
    done: bool | None = None

    _tz = field_validator("fixed_start")(_aware)


def _get(session: Session, task_id: int) -> Task:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Aufgabe nicht gefunden")
    return task


@router.get("/tasks", summary="Aufgaben auflisten")
def list_tasks(
    day: date | None = None, include_done: bool = False, session: Session = Depends(get_session)
) -> list[Task]:
    q = select(Task)
    if day is not None:
        q = q.where(Task.day == day)
    if not include_done:
        q = q.where(Task.done == False)
    return list(session.exec(q.order_by(Task.priority, Task.id)).all())


@router.post("/tasks", status_code=status.HTTP_201_CREATED, summary="Aufgabe anlegen")
def create_task(payload: TaskIn, session: Session = Depends(get_session)) -> Task:
    if payload.constraint == Constraint.HARD and payload.fixed_start is None:
        raise HTTPException(
            status_code=422, detail="HARD-Aufgaben brauchen eine feste Uhrzeit (fixed_start)"
        )
    task = Task(**payload.model_dump())
    if task.fixed_start is not None and task.day is None:
        task.day = task.fixed_start.astimezone(BERLIN).date()
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@router.patch("/tasks/{task_id}", summary="Aufgabe ändern / erledigen")
def update_task(task_id: int, payload: TaskPatch, session: Session = Depends(get_session)) -> Task:
    task = _get(session, task_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, key, value)
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@router.delete(
    "/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Aufgabe löschen"
)
def delete_task(task_id: int, session: Session = Depends(get_session)) -> None:
    session.delete(_get(session, task_id))
    session.commit()


@router.get("/planner/day", summary="Tagesplan: Truth-Gate + 4D-Matrix")
def day_plan(
    day: date | None = None,
    start: str = "07:00",
    end: str = "22:00",
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    stamp = now_cached()
    target = day or stamp.berlin.date()
    try:
        # nur Uhrzeit (HH:MM) — Zeitzone kommt aus dem Tag (Europe/Berlin)
        t_start = datetime.strptime(start, "%H:%M").time()  # noqa: DTZ007
        t_end = datetime.strptime(end, "%H:%M").time()  # noqa: DTZ007
    except ValueError:
        raise HTTPException(status_code=422, detail="start/end im Format HH:MM")
    if t_end <= t_start:
        raise HTTPException(status_code=422, detail="end muss nach start liegen")
    events = session.exec(select(Event)).all()
    today = stamp.berlin.date()
    tasks = [
        t
        for t in session.exec(select(Task).where(Task.done == False)).all()
        if t.day == target or (t.day is None and target == today)
    ]
    plan = build_day_plan(
        target,
        events,
        tasks,
        stamp,
        t_start,
        t_end,
        external={"Google Calendar": "nicht verbunden"},
    )
    return plan.to_dict()
