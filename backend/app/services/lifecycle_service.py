"""Auction lifecycle: opening auctions at their start time and closing them at their close.

Each transition runs under the same row lock as bid submission (SELECT ... FOR UPDATE on the
RFQ), so a close and a last-second bid never interleave: either the bid commits first (and may
move the close time, making this close a no-op) or the close commits first (and the bid is then
rejected by its own time check).

Who calls this:
- Celery ETA jobs `auction.start` / `auction.close`, queued when an RFQ is created and after
  every extension (precise timing).
- The Celery Beat sweeper `auction.sweep`, every few seconds (catches lost or late jobs).
- The bid service, which opens a still-SCHEDULED auction itself before accepting a bid.

All of these are idempotent. The status returned by the APIs is derived from the times on every
read, so a late job only delays the stored status and the activity entry, never correctness.
"""

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import and_, distinct, func, or_, select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.domain.auction_engine import derive_status
from app.domain.enums import ActivityType, AuctionStatus
from app.models import ActivityLog, Bid, Rfq
from app.realtime.events import EventPublisher
from app.services import event_service
from app.services.activity_service import log_activity, money
from app.services.locks import lock_rfq
from app.services.query_service import ranked_latest

logger = logging.getLogger(__name__)

OPEN_STATUSES = (AuctionStatus.SCHEDULED, AuctionStatus.ACTIVE)
ENDED_STATUSES = (AuctionStatus.CLOSED, AuctionStatus.FORCE_CLOSED)
STARTED_MESSAGE = "Bidding opened"
SWEEP_BATCH_SIZE = 100


class Outcome(StrEnum):
    UPDATED = "UPDATED"  # one or more transitions applied
    UNCHANGED = "UNCHANGED"  # nothing left to do (already started / closed)
    NOT_DUE = "NOT_DUE"  # job ran early; retry at `due_at`
    STALE = "STALE"  # close job for a close time that an extension has since moved
    BUSY = "BUSY"  # row locked by a bid in progress (sweeper only; retried next sweep)
    NOT_FOUND = "NOT_FOUND"


@dataclass(frozen=True)
class LifecycleResult:
    rfq_id: uuid.UUID
    outcome: Outcome
    status: AuctionStatus | None = None
    transitions: tuple[ActivityType, ...] = ()
    due_at: datetime | None = None
    activity_ids: tuple[int, ...] = ()


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def mark_started(db: Session, rfq: Rfq) -> ActivityLog | None:
    """SCHEDULED -> ACTIVE on a locked row whose start time has passed.

    The entry is dated at the scheduled start, so the timeline reads correctly even when this
    runs late (e.g. the worker was down, or a bid arrived before the start job)."""
    if rfq.status != AuctionStatus.SCHEDULED:
        return None
    rfq.status = AuctionStatus.ACTIVE
    return log_activity(
        db,
        rfq_id=rfq.id,
        type=ActivityType.AUCTION_STARTED,
        message=STARTED_MESSAGE,
        at=rfq.bid_start_at,
    )


def mark_closed(db: Session, rfq: Rfq, now: datetime) -> ActivityLog:
    """ACTIVE -> CLOSED / FORCE_CLOSED on a locked row whose close time has passed.

    FORCE_CLOSED when the close had been pushed all the way to the forced close time."""
    status = derive_status(
        bid_start_at=rfq.bid_start_at,
        current_close_at=rfq.current_close_at,
        forced_close_at=rfq.forced_close_at,
        now=now,
    )
    if status not in ENDED_STATUSES:
        raise ValueError(f"RFQ {rfq.reference_id} is not due to close at {now.isoformat()}")

    forced = status == AuctionStatus.FORCE_CLOSED
    bid_count, supplier_count = db.execute(
        select(func.count(), func.count(distinct(Bid.supplier_id))).where(Bid.rfq_id == rfq.id)
    ).one()
    ranking = ranked_latest(db, rfq.id)

    verb = "Auction force closed at its forced close time" if forced else "Auction closed"
    meta: dict[str, Any] = {
        "status": status.value,
        "closed_at": rfq.current_close_at.isoformat(),
        "extension_count": rfq.extension_count,
        "bid_count": bid_count,
        "supplier_count": supplier_count,
        "l1": None,
    }
    if ranking:
        _, l1_bid, l1_user = ranking[0]
        message = (
            f"{verb}. L1: {l1_user.company_name} at {money(l1_bid.total_amount, l1_bid.currency)}"
            f" ({_plural(bid_count, 'bid')} from {_plural(supplier_count, 'supplier')})"
        )
        meta["l1"] = {
            "supplier_id": str(l1_user.id),
            "bid_id": str(l1_bid.id),
            "total_amount": str(l1_bid.total_amount),
        }
    else:
        message = f"{verb} with no bids"

    rfq.status = status
    rfq.closed_at = rfq.current_close_at
    activity_type = ActivityType.AUCTION_FORCE_CLOSED if forced else ActivityType.AUCTION_CLOSED
    return log_activity(
        db, rfq_id=rfq.id, type=activity_type, message=message, at=rfq.current_close_at, meta=meta
    )


def _advance(db: Session, rfq: Rfq, now: datetime) -> list[ActivityLog]:
    """Apply every transition that is due at `now` (a late job may need both)."""
    entries: list[ActivityLog] = []
    if rfq.status == AuctionStatus.SCHEDULED and now >= rfq.bid_start_at:
        started = mark_started(db, rfq)
        assert started is not None
        entries.append(started)
    if rfq.status == AuctionStatus.ACTIVE and now >= rfq.current_close_at:
        entries.append(mark_closed(db, rfq, now))
    return entries


def _finish(
    db: Session,
    rfq: Rfq,
    entries: list[ActivityLog],
    publisher: EventPublisher,
    clock: Clock,
) -> LifecycleResult:
    db.flush()  # assigns the activity ids
    transitions = tuple(e.type for e in entries)
    activity_ids = tuple(e.id for e in entries)
    db.commit()
    if not entries:
        return LifecycleResult(rfq.id, Outcome.UNCHANGED, rfq.status)
    logger.info("RFQ %s: %s", rfq.reference_id, ", ".join(transitions))
    event_service.publish_lifecycle(publisher, rfq.id, activity_ids, clock.now())
    return LifecycleResult(
        rfq.id, Outcome.UPDATED, rfq.status, transitions, activity_ids=activity_ids
    )


def start_auction(
    db: Session, rfq_id: uuid.UUID, clock: Clock, *, publisher: EventPublisher
) -> LifecycleResult:
    """Job at bid_start_at: open the auction (and close it too if the job is very late)."""
    rfq = lock_rfq(db, rfq_id)
    if rfq is None:
        db.rollback()
        return LifecycleResult(rfq_id, Outcome.NOT_FOUND)
    now = clock.now()  # after the lock, like the bid service
    if rfq.status == AuctionStatus.SCHEDULED and now < rfq.bid_start_at:
        db.rollback()
        return LifecycleResult(rfq_id, Outcome.NOT_DUE, rfq.status, due_at=rfq.bid_start_at)
    return _finish(db, rfq, _advance(db, rfq, now), publisher, clock)


def close_auction(
    db: Session,
    rfq_id: uuid.UUID,
    clock: Clock,
    *,
    publisher: EventPublisher,
    expected_close_at: datetime | None = None,
) -> LifecycleResult:
    """Job at a close time. A new job is queued after every extension, so the job carries the
    close time it was queued for and does nothing if the close has moved since."""
    rfq = lock_rfq(db, rfq_id)
    if rfq is None:
        db.rollback()
        return LifecycleResult(rfq_id, Outcome.NOT_FOUND)
    if rfq.status in ENDED_STATUSES:
        db.rollback()
        return LifecycleResult(rfq_id, Outcome.UNCHANGED, rfq.status)
    if expected_close_at is not None and rfq.current_close_at != expected_close_at:
        db.rollback()
        return LifecycleResult(rfq_id, Outcome.STALE, rfq.status)
    now = clock.now()
    if now < rfq.current_close_at:
        db.rollback()
        return LifecycleResult(rfq_id, Outcome.NOT_DUE, rfq.status, due_at=rfq.current_close_at)
    return _finish(db, rfq, _advance(db, rfq, now), publisher, clock)


def due_rfq_ids(db: Session, now: datetime, limit: int = SWEEP_BATCH_SIZE) -> Sequence[uuid.UUID]:
    """Auctions whose stored status is behind the clock (uses idx_rfqs_status_start/_close)."""
    return db.scalars(
        select(Rfq.id)
        .where(
            or_(
                and_(Rfq.status == AuctionStatus.SCHEDULED, Rfq.bid_start_at <= now),
                and_(Rfq.status.in_(OPEN_STATUSES), Rfq.current_close_at <= now),
            )
        )
        .order_by(Rfq.current_close_at)
        .limit(limit)
    ).all()


def sweep(
    db: Session, clock: Clock, *, publisher: EventPublisher, limit: int = SWEEP_BATCH_SIZE
) -> list[LifecycleResult]:
    """Bring every overdue auction up to date, one short transaction per auction.

    Rows locked by a bid in progress are skipped (SKIP LOCKED) rather than waited on; the next
    sweep picks them up, and the bid itself may already have moved the close time."""
    ids = due_rfq_ids(db, clock.now(), limit)
    db.rollback()
    results: list[LifecycleResult] = []
    for rfq_id in ids:
        try:
            rfq = lock_rfq(db, rfq_id, skip_locked=True)
            if rfq is None:
                db.rollback()
                results.append(LifecycleResult(rfq_id, Outcome.BUSY))
                continue
            results.append(_finish(db, rfq, _advance(db, rfq, clock.now()), publisher, clock))
        except Exception:
            db.rollback()
            logger.exception("Sweeper failed to update RFQ %s", rfq_id)
    return results
