"""Read side: auction listing, details, bid history and activity log.

Status is always derived from the times (the same rule as auction_engine.derive_status), so
pages are correct even before a lifecycle task updates the stored status. The listing's
status filter uses the equivalent SQL conditions for the same reason.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ColumnElement, and_, case, distinct, func, or_, select, true
from sqlalchemy.orm import Session, selectinload

from app.core.errors import AppError, ErrorCode
from app.domain.auction_engine import RankableBid, RankedBid, compute_ranking, derive_status
from app.domain.enums import AuctionStatus
from app.models import ActivityLog, Bid, Rfq, User
from app.schemas.activity import ActivityListResponse, ActivityOut
from app.schemas.bid import BidListResponse, BidOut
from app.schemas.party import PartyOut
from app.schemas.rfq import (
    AuctionConfigOut,
    LowestBidOut,
    RankedBidOut,
    RfqDetail,
    RfqListItem,
    RfqListResponse,
    RfqOut,
    RfqStats,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def status_of(rfq: Rfq, now: datetime) -> AuctionStatus:
    return derive_status(
        bid_start_at=rfq.bid_start_at,
        current_close_at=rfq.current_close_at,
        forced_close_at=rfq.forced_close_at,
        now=now,
    )


def status_condition(status: AuctionStatus, now: datetime) -> ColumnElement[bool]:
    """SQL equivalent of derive_status(...) == status."""
    ended = Rfq.current_close_at <= now
    match status:
        case AuctionStatus.SCHEDULED:
            return Rfq.bid_start_at > now
        case AuctionStatus.ACTIVE:
            return and_(Rfq.bid_start_at <= now, Rfq.current_close_at > now)
        case AuctionStatus.CLOSED:
            return and_(ended, Rfq.current_close_at < Rfq.forced_close_at)
        case AuctionStatus.FORCE_CLOSED:
            return and_(ended, Rfq.current_close_at >= Rfq.forced_close_at)


def get_rfq_or_404(db: Session, rfq_id: uuid.UUID) -> Rfq:
    rfq = db.get(Rfq, rfq_id, options=[selectinload(Rfq.buyer), selectinload(Rfq.auction_config)])
    if rfq is None:
        raise AppError(ErrorCode.NOT_FOUND, "RFQ not found")
    return rfq


def _party(user: User) -> PartyOut:
    return PartyOut(id=user.id, name=user.name, company_name=user.company_name)


def rfq_out(rfq: Rfq, now: datetime) -> RfqOut:
    return RfqOut(
        id=rfq.id,
        reference_id=rfq.reference_id,
        name=rfq.name,
        status=status_of(rfq, now),
        pickup_date=rfq.pickup_date,
        bid_start_at=rfq.bid_start_at,
        bid_close_at=rfq.bid_close_at,
        current_close_at=rfq.current_close_at,
        forced_close_at=rfq.forced_close_at,
        extension_count=rfq.extension_count,
        closed_at=rfq.closed_at,
        created_at=rfq.created_at,
        buyer=_party(rfq.buyer),
    )


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def _listing_rows(
    db: Session,
    filters: list[ColumnElement[bool]],
    now: datetime,
    *,
    offset: int = 0,
    limit: int | None = None,
) -> list[RfqListItem]:
    lowest = (
        select(
            Bid.total_amount.label("amount"),
            Bid.currency.label("currency"),
            User.company_name.label("supplier_name"),
        )
        .join(User, User.id == Bid.supplier_id)
        .where(Bid.rfq_id == Rfq.id, Bid.is_latest.is_(True))
        .order_by(Bid.total_amount, Bid.submitted_at, Bid.id)
        .limit(1)
        .lateral("lowest")
    )
    counts = (
        select(
            func.count(Bid.id).label("bid_count"),
            func.count(distinct(Bid.supplier_id)).label("supplier_count"),
        )
        .where(Bid.rfq_id == Rfq.id)
        .lateral("counts")
    )

    active = status_condition(AuctionStatus.ACTIVE, now)
    scheduled = status_condition(AuctionStatus.SCHEDULED, now)
    # Active auctions first (closing soonest on top), then upcoming (starting soonest), then
    # ended auctions (most recently ended first).
    ordering = (
        case((active, 0), (scheduled, 1), else_=2),
        case((active, Rfq.current_close_at)).asc().nulls_last(),
        case((scheduled, Rfq.bid_start_at)).asc().nulls_last(),
        Rfq.current_close_at.desc(),
        Rfq.created_at.desc(),
    )

    stmt = (
        select(
            Rfq,
            lowest.c.amount,
            lowest.c.currency,
            lowest.c.supplier_name,
            counts.c.bid_count,
            counts.c.supplier_count,
        )
        .select_from(Rfq)
        .outerjoin(lowest, true())
        .join(counts, true())
        .where(*filters)
        .order_by(*ordering)
        .offset(offset)
        .limit(limit)
    )

    items = []
    for rfq, amount, currency, supplier_name, bid_count, supplier_count in db.execute(stmt):
        items.append(
            RfqListItem(
                id=rfq.id,
                reference_id=rfq.reference_id,
                name=rfq.name,
                status=status_of(rfq, now),
                lowest_bid=(
                    LowestBidOut(amount=amount, currency=currency, supplier_name=supplier_name)
                    if amount is not None
                    else None
                ),
                bid_start_at=rfq.bid_start_at,
                bid_close_at=rfq.bid_close_at,
                current_close_at=rfq.current_close_at,
                forced_close_at=rfq.forced_close_at,
                extension_count=rfq.extension_count,
                bid_count=bid_count,
                supplier_count=supplier_count,
            )
        )
    return items


def list_rfqs(
    db: Session,
    *,
    now: datetime,
    status: AuctionStatus | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> RfqListResponse:
    filters: list[ColumnElement[bool]] = [Rfq.is_british_auction.is_(True)]
    if status is not None:
        filters.append(status_condition(status, now))
    if search:
        filters.append(
            or_(
                Rfq.name.icontains(search, autoescape=True),
                Rfq.reference_id.icontains(search, autoescape=True),
            )
        )
    total = db.scalar(select(func.count()).select_from(Rfq).where(*filters)) or 0
    items = _listing_rows(db, filters, now, offset=(page - 1) * page_size, limit=page_size)
    return RfqListResponse(items=items, page=page, page_size=page_size, total=total)


def get_list_item(db: Session, rfq_id: uuid.UUID, now: datetime) -> RfqListItem:
    """One listing row, e.g. to push a live update after a bid."""
    items = _listing_rows(db, [Rfq.id == rfq_id], now)
    if not items:
        raise AppError(ErrorCode.NOT_FOUND, "RFQ not found")
    return items[0]


# ---------------------------------------------------------------------------
# Details
# ---------------------------------------------------------------------------


def _ranked_latest(db: Session, rfq_id: uuid.UUID) -> list[tuple[RankedBid, Bid, User]]:
    """Latest bid per supplier in rank order, ranked by the auction engine (the same rules
    the bid service applies)."""
    rows = db.execute(
        select(Bid, User)
        .join(User, User.id == Bid.supplier_id)
        .where(Bid.rfq_id == rfq_id, Bid.is_latest.is_(True))
    )
    by_id = {bid.id: (bid, user) for bid, user in rows}
    ranking = compute_ranking(
        [
            RankableBid(b.id, b.supplier_id, b.total_amount, b.submitted_at)
            for b, _ in by_id.values()
        ]
    )
    return [(entry, *by_id[entry.bid.bid_id]) for entry in ranking]


def ranked_bids(db: Session, rfq_id: uuid.UUID) -> list[RankedBidOut]:
    # A comprehension, not dict(result): Result has .keys(), so dict() would treat it as a mapping.
    revisions = {
        supplier_id: count
        for supplier_id, count in db.execute(
            select(Bid.supplier_id, func.count())
            .where(Bid.rfq_id == rfq_id)
            .group_by(Bid.supplier_id)
        )
    }
    result = []
    for entry, bid, user in _ranked_latest(db, rfq_id):
        result.append(
            RankedBidOut(
                rank=entry.rank,
                rank_label=entry.label,
                bid_id=bid.id,
                supplier=_party(user),
                carrier_name=bid.carrier_name,
                freight_charges=bid.freight_charges,
                origin_charges=bid.origin_charges,
                destination_charges=bid.destination_charges,
                total_amount=bid.total_amount,
                currency=bid.currency,
                transit_time_days=bid.transit_time_days,
                quote_validity_date=bid.quote_validity_date,
                notes=bid.notes,
                submitted_at=bid.submitted_at,
                revision_count=revisions.get(bid.supplier_id, 1),
            )
        )
    return result


def _stats(db: Session, rfq: Rfq, ranking: list[RankedBidOut]) -> RfqStats:
    bid_count, supplier_count = db.execute(
        select(func.count(Bid.id), func.count(distinct(Bid.supplier_id))).where(
            Bid.rfq_id == rfq.id
        )
    ).one()
    first_l1 = db.scalar(
        select(Bid.total_amount)
        .where(Bid.rfq_id == rfq.id)
        .order_by(Bid.submitted_at, Bid.id)
        .limit(1)
    )
    current_l1 = ranking[0].total_amount if ranking else None
    savings = None
    if first_l1 and current_l1 is not None:
        savings = ((first_l1 - current_l1) / first_l1 * 100).quantize(Decimal("0.01"))
    extended = rfq.current_close_at - rfq.bid_close_at
    return RfqStats(
        bid_count=bid_count,
        supplier_count=supplier_count,
        extension_count=rfq.extension_count,
        total_extended_minutes=int(extended.total_seconds() // 60),
        first_l1_amount=first_l1,
        current_l1_amount=current_l1,
        savings_pct=savings,
    )


def get_rfq_detail(db: Session, rfq_id: uuid.UUID, now: datetime) -> RfqDetail:
    rfq = get_rfq_or_404(db, rfq_id)
    ranking = ranked_bids(db, rfq.id)
    return RfqDetail(
        rfq=rfq_out(rfq, now),
        auction_config=AuctionConfigOut.model_validate(rfq.auction_config),
        ranking=ranking,
        stats=_stats(db, rfq, ranking),
    )


# ---------------------------------------------------------------------------
# Bids and activity
# ---------------------------------------------------------------------------


def bid_out(bid: Bid, user: User) -> BidOut:
    return BidOut(
        id=bid.id,
        supplier=_party(user),
        carrier_name=bid.carrier_name,
        freight_charges=bid.freight_charges,
        origin_charges=bid.origin_charges,
        destination_charges=bid.destination_charges,
        total_amount=bid.total_amount,
        currency=bid.currency,
        transit_time_days=bid.transit_time_days,
        quote_validity_date=bid.quote_validity_date,
        notes=bid.notes,
        is_latest=bid.is_latest,
        rank_at_submission=bid.rank_at_submission,
        submitted_at=bid.submitted_at,
    )


def list_bids(db: Session, rfq_id: uuid.UUID, *, history: bool) -> BidListResponse:
    """Latest bids in rank order, or (history=True) every bid, newest first."""
    get_rfq_or_404(db, rfq_id)
    if not history:
        return BidListResponse(
            items=[bid_out(bid, user) for _, bid, user in _ranked_latest(db, rfq_id)]
        )

    rows = db.execute(
        select(Bid, User)
        .join(User, User.id == Bid.supplier_id)
        .where(Bid.rfq_id == rfq_id)
        .order_by(Bid.submitted_at.desc(), Bid.id.desc())
    )
    return BidListResponse(items=[bid_out(bid, user) for bid, user in rows])


def activity_out(entry: ActivityLog, actor: User | None) -> ActivityOut:
    return ActivityOut(
        id=entry.id,
        type=entry.type,
        message=entry.message,
        actor=_party(actor) if actor else None,
        metadata=entry.meta,
        created_at=entry.created_at,
    )


def list_activity(
    db: Session, rfq_id: uuid.UUID, *, before_id: int | None = None, limit: int = 50
) -> ActivityListResponse:
    """Newest first, paginated by id (stable even when timestamps tie)."""
    get_rfq_or_404(db, rfq_id)
    stmt = (
        select(ActivityLog, User)
        .outerjoin(User, User.id == ActivityLog.actor_id)
        .where(ActivityLog.rfq_id == rfq_id)
        .order_by(ActivityLog.id.desc())
        .limit(limit + 1)
    )
    if before_id is not None:
        stmt = stmt.where(ActivityLog.id < before_id)
    rows = list(db.execute(stmt).tuples())
    page = rows[:limit]
    next_before_id = page[-1][0].id if len(rows) > limit else None
    return ActivityListResponse(
        items=[activity_out(entry, actor) for entry, actor in page],
        next_before_id=next_before_id,
    )
