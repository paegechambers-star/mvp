from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Event(SQLModel, table=True):  # type: ignore[call-arg]
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    starts_at: datetime
    ends_at: datetime
    location: Optional[str] = None
    all_day: bool = False
    owner: Optional[str] = Field(default=None, index=True)
    tenant_id: Optional[str] = Field(default=None, index=True)


class UsageRecord(SQLModel, table=True):  # type: ignore[call-arg]
    """Per-tenant request metering — used for billing and capacity planning."""
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(index=True)
    endpoint: str
    method: str
    status_code: int
    recorded_at: datetime = Field(default_factory=datetime.utcnow)
