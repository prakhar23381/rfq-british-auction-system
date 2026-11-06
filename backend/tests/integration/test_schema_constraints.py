"""The database itself enforces the assignment's invariants (defence in depth)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.enums import ActivityType, UserRole
from app.models import ActivityLog, AuctionConfig, Bid, Rfq
from tests.factories import T0, make_bid, make_rfq, make_user


def _expect_violation(db: Session, constraint: str) -> None:
    with pytest.raises(IntegrityError) as exc_info:
        db.flush()
    assert constraint in str(exc_info.value.orig)
    db.rollback()


def test_forced_close_must_be_after_bid_close(db: Session) -> None:
    buyer = make_user(db, UserRole.BUYER)
    with pytest.raises(IntegrityError) as exc_info:
        make_rfq(db, buyer, close=T0 + timedelta(hours=1), forced=T0 + timedelta(hours=1))
    assert "chk_forced_after_close" in str(exc_info.value.orig)


def test_bid_close_must_be_after_start(db: Session) -> None:
    buyer = make_user(db, UserRole.BUYER)
    with pytest.raises(IntegrityError) as exc_info:
        make_rfq(db, buyer, start=T0, close=T0)
    assert "chk_close_after_start" in str(exc_info.value.orig)


def test_current_close_can_never_pass_forced_close(db: Session) -> None:
    buyer = make_user(db, UserRole.BUYER)
    rfq = make_rfq(db, buyer, forced=T0 + timedelta(hours=2))
    rfq.current_close_at = rfq.forced_close_at  # reaching the cap exactly is allowed
    db.flush()
    rfq.current_close_at = rfq.forced_close_at + timedelta(seconds=1)
    _expect_violation(db, "chk_current_in_bounds")


def test_trigger_window_and_extension_must_be_in_range(db: Session) -> None:
    buyer = make_user(db, UserRole.BUYER)
    rfq = make_rfq(db, buyer)
    config = db.get(AuctionConfig, rfq.id)
    assert config is not None
    config.trigger_window_minutes = 0
    _expect_violation(db, "chk_trigger_window_range")


def test_total_amount_is_generated_from_charges(db: Session) -> None:
    buyer = make_user(db, UserRole.BUYER)
    supplier = make_user(db)
    rfq = make_rfq(db, buyer)
    bid = make_bid(db, rfq, supplier, freight="100.10", origin="20.00", destination="5.25")
    db.refresh(bid)
    assert bid.total_amount == Decimal("125.35")


def test_negative_charges_rejected(db: Session) -> None:
    buyer = make_user(db, UserRole.BUYER)
    supplier = make_user(db)
    rfq = make_rfq(db, buyer)
    with pytest.raises(IntegrityError) as exc_info:
        make_bid(db, rfq, supplier, freight="-1.00")
    assert "chk_freight_non_negative" in str(exc_info.value.orig)


def test_only_one_latest_bid_per_supplier(db: Session) -> None:
    buyer = make_user(db, UserRole.BUYER)
    supplier = make_user(db)
    rfq = make_rfq(db, buyer)
    make_bid(db, rfq, supplier, is_latest=False)  # history rows are unlimited
    make_bid(db, rfq, supplier, is_latest=False)
    make_bid(db, rfq, supplier, is_latest=True)
    with pytest.raises(IntegrityError) as exc_info:
        make_bid(db, rfq, supplier, is_latest=True)
    assert "uq_bids_latest_per_supplier" in str(exc_info.value.orig)


def test_deleting_rfq_cascades_to_children(db: Session) -> None:
    buyer = make_user(db, UserRole.BUYER)
    supplier = make_user(db)
    rfq = make_rfq(db, buyer)
    make_bid(db, rfq, supplier)
    db.add(ActivityLog(rfq_id=rfq.id, type=ActivityType.RFQ_CREATED, message="created"))
    db.flush()

    db.delete(rfq)
    db.flush()
    for model in (AuctionConfig, Bid, ActivityLog):
        assert db.scalar(select(func.count()).select_from(model)) == 0
    assert db.scalar(select(func.count()).select_from(Rfq)) == 0
