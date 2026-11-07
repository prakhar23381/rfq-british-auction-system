"""LifecycleScheduler backed by Celery ETA tasks."""

import logging
import uuid
from datetime import datetime

from celery import Task

from app.services.scheduling import LifecycleScheduler
from app.workers.tasks import close_auction, start_auction

logger = logging.getLogger(__name__)


class CeleryScheduler:
    def schedule_start(self, rfq_id: uuid.UUID, at: datetime) -> None:
        self._send(start_auction, [str(rfq_id)], at)

    def schedule_close(self, rfq_id: uuid.UUID, close_at: datetime) -> None:
        self._send(close_auction, [str(rfq_id), close_at.isoformat()], close_at)

    @staticmethod
    def _send(task: Task, args: list[str], eta: datetime) -> None:
        # Called after the caller's commit, so a broker outage must not fail the request:
        # the sweeper performs the transition anyway.
        try:
            task.apply_async(args=args, eta=eta, retry=False)
        except Exception:
            logger.warning(
                "Could not queue %s for RFQ %s; the sweeper will handle it",
                task.name,
                args[0],
                exc_info=True,
            )


_scheduler = CeleryScheduler()


def get_scheduler() -> LifecycleScheduler:
    """FastAPI dependency; tests override it with a recording fake."""
    return _scheduler
