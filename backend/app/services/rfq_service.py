"""Creating RFQs. Reads live in query_service."""

from datetime import datetime, timedelta

from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.domain.auction_engine import derive_status
from app.domain.enums import ActivityType, AuctionStatus
from app.models import AuctionConfig, Rfq, User
from app.models.rfq import RFQ_REFERENCE_SEQ
from app.schemas.rfq import RfqCreate
from app.services.activity_service import log_activity
from app.services.lifecycle_service import STARTED_MESSAGE
from app.services.scheduling import LifecycleScheduler, schedule_lifecycle

# Allowance for the time between filling in the form and submitting it.
START_TIME_TOLERANCE = timedelta(minutes=1)
MAX_REFERENCE_ATTEMPTS = 1000


def next_reference_id(db: Session, now: datetime) -> str:
    """RFQ-YYYY-NNNN from a sequence, skipping numbers someone already typed in by hand."""
    for _ in range(MAX_REFERENCE_ATTEMPTS):
        number = db.scalar(select(RFQ_REFERENCE_SEQ.next_value()))
        candidate = f"RFQ-{now.year}-{number:04d}"
        if not db.scalar(select(exists().where(Rfq.reference_id == candidate))):
            return candidate
    raise RuntimeError("Could not generate a free RFQ reference id")  # pragma: no cover


def create_rfq(
    db: Session,
    data: RfqCreate,
    buyer: User,
    now: datetime,
    *,
    scheduler: LifecycleScheduler,
) -> Rfq:
    if data.bid_start_at < now - START_TIME_TOLERANCE:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "Bid start time cannot be in the past",
            details=[{"field": "bid_start_at", "message": "Bid start time cannot be in the past"}],
        )

    reference_id = data.reference_id or next_reference_id(db, now)
    status = derive_status(
        bid_start_at=data.bid_start_at,
        current_close_at=data.bid_close_at,
        forced_close_at=data.forced_close_at,
        now=now,
    )
    rfq = Rfq(
        reference_id=reference_id,
        name=data.name,
        buyer_id=buyer.id,
        pickup_date=data.pickup_date,
        bid_start_at=data.bid_start_at,
        bid_close_at=data.bid_close_at,
        current_close_at=data.bid_close_at,
        forced_close_at=data.forced_close_at,
        status=status,
        created_at=now,
        auction_config=AuctionConfig(
            trigger_window_minutes=data.auction_config.trigger_window_minutes,
            extension_duration_minutes=data.auction_config.extension_duration_minutes,
            trigger_type=data.auction_config.trigger_type,
        ),
    )
    db.add(rfq)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        if "uq_rfqs_reference_id" in str(exc.orig):
            raise AppError(
                ErrorCode.DUPLICATE_REFERENCE,
                f"Reference ID {reference_id} is already in use",
                details=[{"field": "reference_id", "message": "Already in use"}],
            ) from None
        raise

    log_activity(
        db,
        rfq_id=rfq.id,
        type=ActivityType.RFQ_CREATED,
        actor_id=buyer.id,
        message=f"{buyer.company_name} created RFQ {reference_id}",
        at=now,
        meta={
            "bid_close_at": data.bid_close_at.isoformat(),
            "forced_close_at": data.forced_close_at.isoformat(),
        },
    )
    if status == AuctionStatus.ACTIVE:
        log_activity(
            db, rfq_id=rfq.id, type=ActivityType.AUCTION_STARTED, message=STARTED_MESSAGE, at=now
        )
    db.commit()
    schedule_lifecycle(scheduler, rfq)  # after commit, so a job never sees an uncommitted row
    return rfq
