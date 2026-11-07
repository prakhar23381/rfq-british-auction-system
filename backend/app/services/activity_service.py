import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.domain.enums import ActivityType
from app.models import ActivityLog


def log_activity(
    db: Session,
    *,
    rfq_id: uuid.UUID,
    type: ActivityType,
    message: str,
    at: datetime,
    actor_id: uuid.UUID | None = None,
    bid_id: uuid.UUID | None = None,
    extension_id: uuid.UUID | None = None,
    meta: dict[str, Any] | None = None,
) -> ActivityLog:
    """Add an entry to an auction's timeline (flushed with the caller's transaction).
    `at` comes from the injected clock so entries line up with bid and close times."""
    entry = ActivityLog(
        rfq_id=rfq_id,
        type=type,
        message=message,
        actor_id=actor_id,
        bid_id=bid_id,
        extension_id=extension_id,
        meta=meta or {},
        created_at=at,
    )
    db.add(entry)
    return entry


def duration(delta: timedelta) -> str:
    """A length of time as shown in activity messages: "5 min", "40 s", "2 min 30 s"."""
    seconds = round(delta.total_seconds())
    minutes, rest = divmod(seconds, 60)
    if minutes and rest:
        return f"{minutes} min {rest} s"
    return f"{minutes} min" if minutes else f"{rest} s"


def money(amount: Decimal, currency: str) -> str:
    """Money as shown in activity messages, e.g. "INR 125,000.00"."""
    return f"{currency} {amount:,.2f}"
