"""Builds live events after a change has been committed, and publishes them.

Payloads are read in their own short REPEATABLE READ transaction, on a fresh session: the
`version` (newest activity id) and the state in the payload come from the same database
snapshot, and the caller's session and objects are left untouched.

Each activity entry is sent in exactly one event. All events of one change share its version.
Failures are logged, never raised: the change is already committed and clients resync over
REST when they reconnect.
"""

import logging
import uuid
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime
from functools import wraps

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.domain.auction_engine import rank_label
from app.domain.enums import ActivityType
from app.models import ActivityLog, Bid, User
from app.realtime.events import LISTING_CHANNEL, EventPublisher, rfq_channel
from app.schemas.activity import ActivityOut
from app.schemas.bid import ExtensionOut
from app.schemas.events import (
    AuctionExtendedData,
    AuctionStatusData,
    BidSubmittedData,
    ListingItemData,
)
from app.services import query_service

logger = logging.getLogger(__name__)

# Tests switch this on so that a bug in an event payload fails the test instead of being logged.
STRICT = False


def _best_effort[**P](fn: Callable[P, None]) -> Callable[P, None]:
    @wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> None:
        try:
            fn(*args, **kwargs)
        except Exception:
            if STRICT:
                raise
            logger.exception("Could not publish live events (%s)", fn.__name__)

    return wrapper


@contextmanager
def _snapshot() -> Iterator[Session]:
    with SessionLocal() as db:
        db.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        yield db


def _activity(db: Session, ids: Sequence[int]) -> list[ActivityOut]:
    rows = db.execute(
        select(ActivityLog, User)
        .outerjoin(User, User.id == ActivityLog.actor_id)
        .where(ActivityLog.id.in_(ids))
        .order_by(ActivityLog.id)
    ).tuples()
    return [query_service.activity_out(entry, actor) for entry, actor in rows]


def _publish_listing(
    db: Session, publisher: EventPublisher, type: str, rfq_id: uuid.UUID, now: datetime
) -> None:
    item = query_service.get_list_item(db, rfq_id, now)
    data = ListingItemData(version=item.version, item=item)
    publisher.publish(type, LISTING_CHANNEL, data.model_dump(mode="json"))


@_best_effort
def publish_rfq_created(publisher: EventPublisher, rfq_id: uuid.UUID, now: datetime) -> None:
    with _snapshot() as db:
        _publish_listing(db, publisher, "rfq.created", rfq_id, now)


def _publish_status(
    db: Session,
    publisher: EventPublisher,
    rfq_id: uuid.UUID,
    entries: list[ActivityOut],
    version: int,
    now: datetime,
) -> None:
    rfq = query_service.get_rfq_or_404(db, rfq_id)
    rfq_state = query_service.rfq_out(rfq, now, version)
    data = AuctionStatusData(
        version=version, status=rfq_state.status, rfq=rfq_state, activity=entries
    )
    publisher.publish("auction.status", rfq_channel(rfq_id), data.model_dump(mode="json"))


@_best_effort
def publish_lifecycle(
    publisher: EventPublisher, rfq_id: uuid.UUID, activity_ids: Sequence[int], now: datetime
) -> None:
    """The auction opened and/or closed (Celery job, sweeper)."""
    if not activity_ids:
        return
    with _snapshot() as db:
        version = query_service.rfq_version(db, rfq_id)
        entries = _activity(db, activity_ids)
        _publish_status(db, publisher, rfq_id, entries, version, now)
        _publish_listing(db, publisher, "listing.updated", rfq_id, now)


@_best_effort
def publish_bid(
    publisher: EventPublisher,
    *,
    rfq_id: uuid.UUID,
    bid_id: uuid.UUID,
    rank: int,
    extension: ExtensionOut | None,
    activity_ids: Sequence[int],
    now: datetime,
) -> None:
    """A bid was accepted: maybe `auction.status` (it opened the auction), `bid.submitted`,
    maybe `auction.extended`, then `listing.updated`."""
    with _snapshot() as db:
        version = query_service.rfq_version(db, rfq_id)
        entries = _activity(db, activity_ids)
        started = [e for e in entries if e.type == ActivityType.AUCTION_STARTED]
        extended = [e for e in entries if e.type == ActivityType.AUCTION_EXTENDED]
        rest = [e for e in entries if e not in started and e not in extended]

        if started:
            _publish_status(db, publisher, rfq_id, started, version, now)

        detail = query_service.get_rfq_detail(db, rfq_id, now)
        bid, supplier = db.execute(
            select(Bid, User).join(User, User.id == Bid.supplier_id).where(Bid.id == bid_id)
        ).one()
        submitted = BidSubmittedData(
            version=version,
            bid=query_service.bid_out(bid, supplier),
            rank=rank,
            rank_label=rank_label(rank),
            extension=extension,
            rfq=detail.rfq,
            ranking=detail.ranking,
            stats=detail.stats,
            activity=rest,
        )
        channel = rfq_channel(rfq_id)
        publisher.publish("bid.submitted", channel, submitted.model_dump(mode="json"))

        if extended and extension is not None:
            data = AuctionExtendedData(
                version=version,
                previous_close_at=extension.previous_close_at,
                new_close_at=extension.new_close_at,
                capped=extension.capped,
                reason=extension.reason,
                extension_count=detail.rfq.extension_count,
                activity=extended,
            )
            publisher.publish("auction.extended", channel, data.model_dump(mode="json"))

        _publish_listing(db, publisher, "listing.updated", rfq_id, now)
