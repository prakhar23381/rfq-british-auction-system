"""Small builders for test data (direct ORM inserts, bypassing services)."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.domain.enums import AuctionStatus, TriggerType, UserRole
from app.models import AuctionConfig, Bid, Rfq, User

T0 = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


def make_user(db: Session, role: UserRole = UserRole.SUPPLIER, company: str | None = None) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        name=f"User {suffix}",
        email=f"{suffix}@example.test",
        company_name=company or f"Company {suffix}",
        role=role,
    )
    db.add(user)
    db.flush()
    return user


def make_rfq(
    db: Session,
    buyer: User,
    *,
    start: datetime = T0,
    close: datetime = T0 + timedelta(hours=1),
    forced: datetime = T0 + timedelta(hours=2),
    current_close: datetime | None = None,
    extension_count: int = 0,
    name: str = "Test lane",
    reference_id: str | None = None,
    x: int = 10,
    y: int = 5,
    trigger: TriggerType = TriggerType.L1_CHANGE,
) -> Rfq:
    rfq = Rfq(
        reference_id=reference_id or f"RFQ-T-{uuid.uuid4().hex[:6].upper()}",
        name=name,
        buyer_id=buyer.id,
        pickup_date=date(2026, 12, 1),
        bid_start_at=start,
        bid_close_at=close,
        current_close_at=current_close or close,
        forced_close_at=forced,
        status=AuctionStatus.SCHEDULED,  # stored status; APIs derive it from the times
        extension_count=extension_count,
        auction_config=AuctionConfig(
            trigger_window_minutes=x, extension_duration_minutes=y, trigger_type=trigger
        ),
    )
    db.add(rfq)
    db.flush()
    return rfq


def make_bid(
    db: Session,
    rfq: Rfq,
    supplier: User,
    *,
    freight: str = "1000.00",
    origin: str = "100.00",
    destination: str = "50.00",
    is_latest: bool = True,
    submitted_at: datetime | None = None,
) -> Bid:
    bid = Bid(
        rfq_id=rfq.id,
        supplier_id=supplier.id,
        carrier_name="Test Carrier",
        freight_charges=Decimal(freight),
        origin_charges=Decimal(origin),
        destination_charges=Decimal(destination),
        transit_time_days=20,
        quote_validity_date=date(2026, 12, 31),
        is_latest=is_latest,
        submitted_at=submitted_at or T0,
    )
    db.add(bid)
    db.flush()
    return bid
