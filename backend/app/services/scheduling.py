"""Scheduling of auction start/close jobs, behind a small interface.

Services call a `LifecycleScheduler` after they commit. The real implementation enqueues
Celery tasks with an ETA (app/workers/scheduling.py); tests use a recording fake. Scheduling is
best effort: if a job is lost, the Beat sweeper still starts/closes the auction within seconds,
and every read derives the status from the times anyway.
"""

import uuid
from datetime import datetime
from typing import Protocol

from app.domain.enums import AuctionStatus
from app.models import Rfq


class LifecycleScheduler(Protocol):
    def schedule_start(self, rfq_id: uuid.UUID, at: datetime) -> None: ...

    def schedule_close(self, rfq_id: uuid.UUID, close_at: datetime) -> None: ...


class NullScheduler:
    """Schedules nothing; the sweeper alone drives transitions (scripts, tests)."""

    def schedule_start(self, rfq_id: uuid.UUID, at: datetime) -> None:
        pass

    def schedule_close(self, rfq_id: uuid.UUID, close_at: datetime) -> None:
        pass


def schedule_lifecycle(scheduler: LifecycleScheduler, rfq: Rfq) -> None:
    """Queue the jobs an auction still needs: its start (if upcoming) and its current close."""
    if rfq.status == AuctionStatus.SCHEDULED:
        scheduler.schedule_start(rfq.id, rfq.bid_start_at)
    if rfq.status in (AuctionStatus.SCHEDULED, AuctionStatus.ACTIVE):
        scheduler.schedule_close(rfq.id, rfq.current_close_at)
