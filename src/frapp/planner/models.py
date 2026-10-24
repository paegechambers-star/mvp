"""Aufgaben für den Tagesplaner (Termine kommen aus ``frapp.models.Event``)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class Constraint(str, Enum):
    HARD = "HARD"    # fester Zeitpunkt, nicht verschiebbar
    SOFT = "SOFT"    # soll heute erledigt werden, Zeit flexibel
    FLOAT = "FLOAT"  # kann, wenn Zeit bleibt


class Certainty(str, Enum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    ASSUMPTION = "ASSUMPTION"


class Task(SQLModel, table=True):  # type: ignore[call-arg]
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    duration_min: int = 30
    constraint: Constraint = Constraint.SOFT
    domain: str = "Allgemein"
    # Feste Uhrzeit (nur sinnvoll bei HARD); zeitzonenbewusst
    fixed_start: Optional[datetime] = None
    # Tag, für den die Aufgabe geplant ist (None = ab heute offen)
    day: Optional[date] = Field(default=None, index=True)
    due: Optional[date] = None
    priority: int = 2  # 1 = hoch, 3 = niedrig
    source: str = "Nutzereingabe"
    certainty: Certainty = Certainty.VERIFIED
    done: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
