"""Celery tasks. Thin wrappers: the logic (and its tests) lives in lifecycle_service."""

import logging
import uuid
from collections import Counter
from datetime import datetime

from sqlalchemy.exc import OperationalError

from app.core.clock import get_clock
from app.db import SessionLocal
from app.realtime.events import get_publisher
from app.services import lifecycle_service
from app.services.lifecycle_service import Outcome
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Retry when the database is briefly unreachable; the sweeper is the final safety net.
DB_RETRY: dict[str, object] = {
    "autoretry_for": (OperationalError,),
    "retry_backoff": True,
    "max_retries": 5,
    "ignore_result": True,
}


@celery_app.task(name="system.ping")
def ping() -> str:
    """Smoke-test task to verify the worker is consuming from the broker."""
    return "pong"


@celery_app.task(name="auction.start", **DB_RETRY)
def start_auction(rfq_id: str) -> str:
    with SessionLocal() as db:
        result = lifecycle_service.start_auction(
            db, uuid.UUID(rfq_id), get_clock(), publisher=get_publisher()
        )
    if result.outcome == Outcome.NOT_DUE and result.due_at is not None:
        start_auction.apply_async(args=[rfq_id], eta=result.due_at)
    return result.outcome.value


@celery_app.task(name="auction.close", **DB_RETRY)
def close_auction(rfq_id: str, expected_close_at: str | None = None) -> str:
    expected = datetime.fromisoformat(expected_close_at) if expected_close_at else None
    with SessionLocal() as db:
        result = lifecycle_service.close_auction(
            db,
            uuid.UUID(rfq_id),
            get_clock(),
            publisher=get_publisher(),
            expected_close_at=expected,
        )
    if result.outcome == Outcome.NOT_DUE and result.due_at is not None:
        close_auction.apply_async(args=[rfq_id, expected_close_at], eta=result.due_at)
    return result.outcome.value


@celery_app.task(name="auction.sweep", **DB_RETRY)
def sweep_auctions() -> dict[str, int]:
    with SessionLocal() as db:
        results = lifecycle_service.sweep(db, get_clock(), publisher=get_publisher())
    counts = Counter(r.outcome.value for r in results)
    if counts:
        logger.info("Sweep: %s", dict(counts))
    return dict(counts)
