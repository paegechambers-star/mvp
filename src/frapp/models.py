from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field


class Event(SQLModel, table=True):  # type: ignore[call-arg]
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    starts_at: datetime
    ends_at: datetime
    location: Optional[str] = None
    all_day: bool = False
    owner: Optional[str] = Field(default=None, index=True)  # GDPR Art. 17 — owner identifier
