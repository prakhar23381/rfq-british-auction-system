"""Bid submission: the British auction write path.

Everything happens in one transaction that starts by locking the RFQ row
(SELECT ... FOR UPDATE). Bids for the same auction, and the task that closes it, therefore
run one at a time: two simultaneous bids cannot both read the same "before" ranking or both
extend from the same close time, and no bid can slip in after the close.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.clock import Clock
from app.core.errors import AppError, ErrorCode
from app.domain.auction_engine import (
    ExtensionDecision,
    RankableBid,
    TriggerResult,
    accepts_bids_at,
    compute_ranking,
    decide_extension,
    is_valid_revision,
    rank_label,
    with_new_bid,
)
from app.domain.enums import ActivityType, TriggerType
from app.models import ActivityLog, AuctionConfig, AuctionExtension, Bid, Rfq, User
from app.realtime.events import EventPublisher
from app.schemas.bid import BidCreate, ExtensionOut
from app.services import event_service
from app.services.activity_service import duration, log_activity, money
from app.services.lifecycle_service import mark_started
from app.services.locks import lock_rfq
from app.services.scheduling import LifecycleScheduler


@dataclass(frozen=True)
class BidOutcome:
    """What happened when a bid was accepted (the API turns this into its response)."""

    rfq: Rfq
    bid: Bid
    rank: int
    decision: ExtensionDecision
    reason: str | None  # why the auction was (or would have been) extended
    activity_ids: tuple[int, ...]

    def extension_out(self) -> ExtensionOut | None:
        """Set whenever the trigger fired: applied, shortened by the cap, or skipped at it."""
        extension = self.decision.extension
        if extension is None:
            return None
        return ExtensionOut(
            applied=extension.applied,
            previous_close_at=extension.previous_close_at,
            new_close_at=extension.new_close_at,
            capped=extension.capped,
            reason=self.reason or "",
        )


def _lock_rfq(db: Session, rfq_id: uuid.UUID) -> Rfq:
    rfq = lock_rfq(db, rfq_id)
    if rfq is None:
        raise AppError(ErrorCode.NOT_FOUND, "RFQ not found")
    return rfq


def _extension_reason(
    trigger: TriggerResult, names: dict[uuid.UUID, str], bidder: str, x_minutes: int
) -> str:
    window = f"within the last {x_minutes} min before close"
    match trigger.trigger_type:
        case TriggerType.BID_RECEIVED:
            return f"Bid received from {bidder} {window}"
        case TriggerType.ANY_RANK_CHANGE:
            moves = ", ".join(
                f"{names[c.supplier_id]} {rank_label(c.from_rank)}→{rank_label(c.to_rank)}"
                for c in sorted(trigger.rank_changes, key=lambda c: c.to_rank)
            )
            return f"Supplier ranking changed {window}: {moves}"
        case TriggerType.L1_CHANGE:
            if trigger.previous_l1 is None:
                return f"First bid, by {bidder}, set a new L1 {window}"
            new_l1 = names[trigger.new_l1] if trigger.new_l1 else bidder
            return f"New L1 {window}: {new_l1} replaced {names[trigger.previous_l1]}"


def submit_bid(
    db: Session,
    rfq_id: uuid.UUID,
    supplier: User,
    data: BidCreate,
    clock: Clock,
    *,
    scheduler: LifecycleScheduler,
    publisher: EventPublisher,
) -> BidOutcome:
    rfq = _lock_rfq(db, rfq_id)
    now = clock.now()  # read after the lock, so it reflects when the bid is processed

    if now < rfq.bid_start_at:
        raise AppError(ErrorCode.AUCTION_NOT_STARTED, "Bidding has not started yet")
    if not accepts_bids_at(
        bid_start_at=rfq.bid_start_at, current_close_at=rfq.current_close_at, at=now
    ):
        raise AppError(ErrorCode.AUCTION_CLOSED, "Bidding for this auction has closed")
    # The start job may not have run yet; open the auction first so the log reads in order.
    entries: list[ActivityLog] = []
    if (started := mark_started(db, rfq)) is not None:
        entries.append(started)
    if data.quote_validity_date < rfq.pickup_date:
        message = "Quote must be valid until at least the pickup / service date"
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            message,
            details=[{"field": "quote_validity_date", "message": message}],
        )

    config = db.get_one(AuctionConfig, rfq.id)
    rows = db.execute(
        select(Bid, User.company_name)
        .join(User, User.id == Bid.supplier_id)
        .where(Bid.rfq_id == rfq.id, Bid.is_latest.is_(True))
    ).all()
    latest = {bid.supplier_id: bid for bid, _ in rows}
    names = {bid.supplier_id: name for bid, name in rows}
    names[supplier.id] = supplier.company_name

    previous = latest.get(supplier.id)
    new_total = data.total_amount
    if not is_valid_revision(previous.total_amount if previous else None, new_total):
        assert previous is not None
        currency = previous.currency
        raise AppError(
            ErrorCode.BID_NOT_LOWER,
            f"Your new bid must be lower than your current bid of "
            f"{money(previous.total_amount, currency)}",
            details=[{"field": "total_amount", "message": "Must be lower than your current bid"}],
        )

    if previous is not None:
        previous.is_latest = False
        db.flush()  # free the "one latest bid per supplier" slot before inserting

    bid = Bid(
        rfq_id=rfq.id,
        supplier_id=supplier.id,
        carrier_name=data.carrier_name,
        freight_charges=data.freight_charges,
        origin_charges=data.origin_charges,
        destination_charges=data.destination_charges,
        currency=get_settings().currency,
        transit_time_days=data.transit_time_days,
        quote_validity_date=data.quote_validity_date,
        notes=data.notes,
        submitted_at=now,
    )
    db.add(bid)
    db.flush()

    rankable = [
        RankableBid(b.id, b.supplier_id, b.total_amount, b.submitted_at) for b in latest.values()
    ]
    new_rankable = RankableBid(bid.id, supplier.id, new_total, now)
    before = compute_ranking(rankable)
    after = compute_ranking(with_new_bid(rankable, new_rankable))
    rank = next(r.rank for r in after if r.supplier_id == supplier.id)
    bid.rank_at_submission = rank

    decision = decide_extension(
        bid_at=now,
        current_close_at=rfq.current_close_at,
        forced_close_at=rfq.forced_close_at,
        trigger_window_minutes=config.trigger_window_minutes,
        extension_duration_minutes=config.extension_duration_minutes,
        trigger_type=config.trigger_type,
        before=before,
        after=after,
    )

    bid_meta: dict[str, Any] = {
        "total_amount": str(new_total),
        "rank": rank,
        "in_trigger_window": decision.in_window,
    }
    if previous is not None:
        bid_meta["previous_total"] = str(previous.total_amount)
    bid_entry = log_activity(
        db,
        rfq_id=rfq.id,
        type=ActivityType.BID_SUBMITTED,
        actor_id=supplier.id,
        bid_id=bid.id,
        message=(
            f"{supplier.company_name} bid {money(new_total, bid.currency)}: now {rank_label(rank)}"
        ),
        at=now,
        meta=bid_meta,
    )
    entries.append(bid_entry)

    reason = None
    if decision.trigger is not None and decision.extension is not None:
        trigger, extension = decision.trigger, decision.extension
        reason = _extension_reason(
            trigger, names, supplier.company_name, config.trigger_window_minutes
        )
        trigger_meta: dict[str, Any] = {
            "trigger_type": trigger.trigger_type.value,
            "previous_l1": str(trigger.previous_l1) if trigger.previous_l1 else None,
            "new_l1": str(trigger.new_l1) if trigger.new_l1 else None,
            "rank_changes": [
                {"supplier_id": str(c.supplier_id), "from": c.from_rank, "to": c.to_rank}
                for c in sorted(trigger.rank_changes, key=lambda c: c.to_rank)
            ],
        }
        if extension.applied:
            added = extension.new_close_at - extension.previous_close_at
            record = AuctionExtension(
                rfq_id=rfq.id,
                bid_id=bid.id,
                trigger_type=trigger.trigger_type,
                previous_close_at=extension.previous_close_at,
                new_close_at=extension.new_close_at,
                capped=extension.capped,
                reason=reason[:300],
                created_at=now,
            )
            db.add(record)
            db.flush()
            rfq.current_close_at = extension.new_close_at
            rfq.extension_count += 1
            capped_note = " (capped at the forced close time)" if extension.capped else ""
            extended_entry = log_activity(
                db,
                rfq_id=rfq.id,
                type=ActivityType.AUCTION_EXTENDED,
                bid_id=bid.id,
                extension_id=record.id,
                message=f"Auction extended by {duration(added)}{capped_note}. {reason}",
                at=now,
                meta={
                    **trigger_meta,
                    "previous_close_at": extension.previous_close_at.isoformat(),
                    "new_close_at": extension.new_close_at.isoformat(),
                    "capped": extension.capped,
                    "extension_seconds": round(added.total_seconds()),
                },
            )
            entries.append(extended_entry)
        else:
            skipped_entry = log_activity(
                db,
                rfq_id=rfq.id,
                type=ActivityType.EXTENSION_SKIPPED,
                bid_id=bid.id,
                message=(
                    "Not extended: the auction is already at its forced close time. "
                    f"Trigger met: {reason}"
                ),
                at=now,
                meta={**trigger_meta, "forced_close_at": rfq.forced_close_at.isoformat()},
            )
            entries.append(skipped_entry)

    db.flush()  # assigns the activity ids
    outcome = BidOutcome(
        rfq=rfq,
        bid=bid,
        rank=rank,
        decision=decision,
        reason=reason,
        activity_ids=tuple(e.id for e in entries),
    )
    db.commit()

    if decision.extended:
        # The job queued for the old close time will find the close moved and do nothing.
        scheduler.schedule_close(rfq.id, rfq.current_close_at)
    event_service.publish_bid(
        publisher,
        rfq_id=rfq.id,
        bid_id=bid.id,
        rank=rank,
        extension=outcome.extension_out(),
        activity_ids=outcome.activity_ids,
        now=clock.now(),
    )
    return outcome
