from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


class Event(SQLModel, table=True):  # type: ignore[call-arg]
    id: int | None = Field(default=None, primary_key=True)
    title: str
    starts_at: datetime
    ends_at: datetime
    location: str | None = None
    all_day: bool = False
    owner: str | None = Field(default=None, index=True)
    tenant_id: str | None = Field(default=None, index=True)


class UsageRecord(SQLModel, table=True):  # type: ignore[call-arg]
    """Per-tenant request metering — used for billing and capacity planning."""

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: str = Field(index=True)
    endpoint: str
    method: str
    status_code: int
    # zeitzonenbewusst: sqlmodel >= 0.0.48 lehnt naive Zeitpunkte ab
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
