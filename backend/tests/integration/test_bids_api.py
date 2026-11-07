"""Bid submission through the API, with a frozen clock. Case ids (A7, A15, ...) match the
test matrix in the project plan. Auction times follow the HLD example: start 17:00,
close 18:00, forced close 18:20, X = 10 min, Y = 5 min."""

import itertools
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock, SystemClock
from app.core.errors import AppError, ErrorCode
from app.db import SessionLocal
from app.domain.enums import ActivityType, TriggerType, UserRole
from app.models import ActivityLog, AuctionExtension, Bid, Rfq, User
from app.schemas.bid import BidCreate
from app.services import bid_service
from tests.factories import make_rfq, make_user


def at(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 11, 10, hour, minute, second, tzinfo=UTC)


Suppliers = dict[str, User]


@pytest.fixture
def people(db: Session) -> Suppliers:
    users = {
        "buyer": make_user(db, UserRole.BUYER, company="Acme Exports"),
        "A": make_user(db, company="BlueWave"),
        "B": make_user(db, company="Swift Cargo"),
        "C": make_user(db, company="Oceanic"),
    }
    db.commit()
    return users


def auction(db: Session, buyer: User, trigger: TriggerType = TriggerType.L1_CHANGE) -> Rfq:
    rfq = make_rfq(
        db,
        buyer,
        start=at(17, 0),
        close=at(18, 0),
        forced=at(18, 20),
        x=10,
        y=5,
        trigger=trigger,
    )
    db.commit()
    return rfq


def bid_body(amount: int | str, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "carrier_name": "Test Line",
        "freight_charges": str(amount),
        "origin_charges": "0",
        "destination_charges": "0",
        "transit_time_days": 20,
        "quote_validity_date": "2026-12-31",
    }
    body.update(overrides)
    return body


def place(
    client: TestClient,
    clock: FrozenClock,
    rfq: Rfq,
    supplier: User,
    amount: int | str,
    when: datetime,
    **overrides: Any,
) -> Any:
    clock.set(when)
    return client.post(
        f"/api/rfqs/{rfq.id}/bids",
        json=bid_body(amount, **overrides),
        headers={"X-User-Id": str(supplier.id)},
    )


def activity_types(client: TestClient, rfq: Rfq) -> list[str]:
    items = client.get(f"/api/rfqs/{rfq.id}/activity", params={"limit": 200}).json()["items"]
    return [a["type"] for a in reversed(items)]  # oldest first


# ---------------------------------------------------------------------------
# Acceptance rules
# ---------------------------------------------------------------------------


def test_a7_bid_before_start(
    client: TestClient, clock: FrozenClock, db: Session, people: Suppliers
) -> None:
    rfq = auction(db, people["buyer"])
    res = place(client, clock, rfq, people["A"], 100, at(16, 59))
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "AUCTION_NOT_STARTED"


@pytest.mark.parametrize("when", [at(18, 0), at(18, 5)], ids=["at close", "after close"])
def test_a8_bid_at_or_after_close(
    client: TestClient, clock: FrozenClock, db: Session, people: Suppliers, when: datetime
) -> None:
    # Stored status is still SCHEDULED: acceptance depends only on the time, checked under lock.
    rfq = auction(db, people["buyer"])
    res = place(client, clock, rfq, people["A"], 100, when)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "AUCTION_CLOSED"


def test_a9_bid_after_forced_close(
    client: TestClient, clock: FrozenClock, db: Session, people: Suppliers
) -> None:
    rfq = make_rfq(db, people["buyer"], start=at(17, 0), close=at(18, 0), forced=at(18, 20),
                   current_close=at(18, 20))  # fmt: skip
    db.commit()
    assert place(client, clock, rfq, people["A"], 100, at(18, 19)).status_code == 201
    res = place(client, clock, rfq, people["B"], 90, at(18, 20))
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "AUCTION_CLOSED"


def test_a10_only_suppliers_bid(
    client: TestClient, clock: FrozenClock, db: Session, people: Suppliers
) -> None:
    rfq = auction(db, people["buyer"])
    assert place(client, clock, rfq, people["buyer"], 100, at(17, 30)).status_code == 403
    clock.set(at(17, 30))
    missing = client.post(
        f"/api/rfqs/{uuid.uuid4()}/bids",
        json=bid_body(100),
        headers={"X-User-Id": str(people["A"].id)},
    )
    assert missing.status_code == 404


@pytest.mark.parametrize("amount", [100, 101], ids=["equal", "higher"])
def test_a11_revision_must_be_lower(
    client: TestClient, clock: FrozenClock, db: Session, people: Suppliers, amount: int
) -> None:
    rfq = auction(db, people["buyer"])
    assert place(client, clock, rfq, people["A"], 100, at(17, 30)).status_code == 201
    res = place(client, clock, rfq, people["A"], amount, at(17, 31))
    assert res.status_code == 422
    error = res.json()["error"]
    assert error["code"] == "BID_NOT_LOWER"
    assert "INR 100.00" in error["message"]


def test_a12_lower_revision_replaces_previous_bid(
    client: TestClient, clock: FrozenClock, db: Session, people: Suppliers
) -> None:
    rfq = auction(db, people["buyer"])
    place(client, clock, rfq, people["A"], 100, at(17, 30))
    res = place(client, clock, rfq, people["A"], "99.50", at(17, 31))
    assert res.status_code == 201
    assert res.json()["bid"]["total_amount"] == "99.50"

    history = client.get(f"/api/rfqs/{rfq.id}/bids", params={"history": True}).json()["items"]
    assert [(b["total_amount"], b["is_latest"]) for b in history] == [
        ("99.50", True),
        ("100.00", False),
    ]
    latest = db.scalar(select(func.count()).where(Bid.rfq_id == rfq.id, Bid.is_latest.is_(True)))
    assert latest == 1


def test_a16_quote_must_cover_pickup_date(
    client: TestClient, clock: FrozenClock, db: Session, people: Suppliers
) -> None:
    rfq = auction(db, people["buyer"])  # pickup 2026-12-01
    res = place(client, clock, rfq, people["A"], 100, at(17, 30), quote_validity_date="2026-11-30")
    assert res.status_code == 422
    assert res.json()["error"]["details"][0]["field"] == "quote_validity_date"
    ok = place(client, clock, rfq, people["A"], 100, at(17, 30), quote_validity_date="2026-12-01")
    assert ok.status_code == 201


def test_bid_validation_errors(
    client: TestClient, clock: FrozenClock, db: Session, people: Suppliers
) -> None:
    rfq = auction(db, people["buyer"])
    res = place(client, clock, rfq, people["A"], "-5", at(17, 30))
    assert res.status_code == 422
    assert res.json()["error"]["details"][0]["field"] == "freight_charges"


# ---------------------------------------------------------------------------
# Response and activity log
# ---------------------------------------------------------------------------


def test_response_and_log_for_a_bid_outside_the_window(
    client: TestClient, clock: FrozenClock, db: Session, people: Suppliers
) -> None:
    rfq = auction(db, people["buyer"])
    res = place(client, clock, rfq, people["A"], 1000, at(17, 40))  # A13
    assert res.status_code == 201
    body = res.json()
    assert (body["rank"], body["rank_label"]) == (1, "L1")
    assert body["extension"] is None
    assert body["rfq"] == {
        "status": "ACTIVE",
        "current_close_at": "2026-11-10T18:00:00Z",
        "extension_count": 0,
    }
    assert body["bid"]["supplier"]["company_name"] == "BlueWave"
    assert body["bid"]["rank_at_submission"] == 1

    entry = client.get(f"/api/rfqs/{rfq.id}/activity").json()["items"][0]
    assert entry["type"] == "BID_SUBMITTED"
    assert entry["message"] == "BlueWave bid INR 1,000.00: now L1"
    assert entry["actor"]["company_name"] == "BlueWave"
    assert entry["metadata"] == {"total_amount": "1000.00", "rank": 1, "in_trigger_window": False}
    assert entry["created_at"] == "2026-11-10T17:40:00Z"


# ---------------------------------------------------------------------------
# Trigger types through the API (A14). A = 100 (L1) and B = 110 (L2) bid before the window.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("trigger", "bidder", "amount", "extended", "reason"),
    [
        (TriggerType.BID_RECEIVED, "B", 105, True, "Bid received from Swift Cargo"),
        (TriggerType.ANY_RANK_CHANGE, "B", 105, False, None),
        (TriggerType.ANY_RANK_CHANGE, "B", 95, True, "Swift Cargo L2→L1, BlueWave L1→L2"),
        (TriggerType.ANY_RANK_CHANGE, "C", 120, False, None),  # newcomer enters last
        (TriggerType.L1_CHANGE, "A", 90, False, None),  # L1 lowers own price
        (TriggerType.L1_CHANGE, "C", 99, True, "Oceanic replaced BlueWave"),
    ],
)
def test_a14_trigger_types(
    client: TestClient,
    clock: FrozenClock,
    db: Session,
    people: Suppliers,
    trigger: TriggerType,
    bidder: str,
    amount: int,
    extended: bool,
    reason: str | None,
) -> None:
    rfq = auction(db, people["buyer"], trigger)
    place(client, clock, rfq, people["A"], 100, at(17, 30))
    place(client, clock, rfq, people["B"], 110, at(17, 31))

    res = place(client, clock, rfq, people[bidder], amount, at(17, 55))
    assert res.status_code == 201
    body = res.json()
    if extended:
        assert reason is not None
        assert body["extension"]["applied"] is True
        assert body["extension"]["new_close_at"] == "2026-11-10T18:05:00Z"
        assert reason in body["extension"]["reason"]
        assert activity_types(client, rfq)[-1] == "AUCTION_EXTENDED"
    else:
        assert body["extension"] is None
        assert body["rfq"]["current_close_at"] == "2026-11-10T18:00:00Z"
        assert activity_types(client, rfq)[-1] == "BID_SUBMITTED"


# ---------------------------------------------------------------------------
# The HLD worked example, end to end through the API (A15)
# ---------------------------------------------------------------------------


def test_a15_worked_example_until_force_close(
    client: TestClient, clock: FrozenClock, db: Session, people: Suppliers
) -> None:
    rfq = auction(db, people["buyer"], TriggerType.L1_CHANGE)
    a, b, c = people["A"], people["B"], people["C"]

    steps = [
        (at(17, 40), a, 100, "2026-11-10T18:00:00Z"),
        (at(17, 52), b, 95, "2026-11-10T18:05:00Z"),
        (at(17, 58), b, 90, "2026-11-10T18:05:00Z"),
        (at(18, 1), a, 85, "2026-11-10T18:10:00Z"),
        (at(18, 8), b, 80, "2026-11-10T18:15:00Z"),
        (at(18, 12), a, 75, "2026-11-10T18:20:00Z"),
        (at(18, 16), b, 70, "2026-11-10T18:20:00Z"),
    ]
    for when, supplier, amount, close_after in steps:
        res = place(client, clock, rfq, supplier, amount, when)
        assert res.status_code == 201, (when, res.text)
        assert res.json()["rfq"]["current_close_at"] == close_after, when

    last = res.json()
    assert last["extension"]["applied"] is False  # trigger met at the cap
    assert last["extension"]["capped"] is True

    late = place(client, clock, rfq, c, 60, at(18, 20, 1))
    assert late.status_code == 409

    assert activity_types(client, rfq) == [
        "BID_SUBMITTED",
        "BID_SUBMITTED", "AUCTION_EXTENDED",
        "BID_SUBMITTED",
        "BID_SUBMITTED", "AUCTION_EXTENDED",
        "BID_SUBMITTED", "AUCTION_EXTENDED",
        "BID_SUBMITTED", "AUCTION_EXTENDED",
        "BID_SUBMITTED", "EXTENSION_SKIPPED",
    ]  # fmt: skip

    clock.set(at(18, 20))
    detail = client.get(f"/api/rfqs/{rfq.id}").json()
    assert detail["rfq"]["status"] == "FORCE_CLOSED"
    assert detail["rfq"]["extension_count"] == 4
    assert detail["stats"]["total_extended_minutes"] == 20
    assert [(r["rank_label"], r["supplier"]["company_name"], r["total_amount"])
            for r in detail["ranking"]] == [("L1", "Swift Cargo", "70.00"),
                                           ("L2", "BlueWave", "75.00")]  # fmt: skip

    # Extensions form an unbroken chain from the original close to the forced close.
    chain = db.scalars(
        select(AuctionExtension)
        .where(AuctionExtension.rfq_id == rfq.id)
        .order_by(AuctionExtension.created_at)
    ).all()
    assert [(e.previous_close_at, e.new_close_at) for e in chain] == [
        (at(18, 0), at(18, 5)),
        (at(18, 5), at(18, 10)),
        (at(18, 10), at(18, 15)),
        (at(18, 15), at(18, 20)),
    ]
    assert not any(e.capped for e in chain)

    extended = client.get(f"/api/rfqs/{rfq.id}/activity").json()["items"]
    reasons = [e for e in extended if e["type"] == "AUCTION_EXTENDED"]
    assert reasons[-1]["message"] == (
        "Auction extended by 5 min. New L1 within the last 10 min before close: "
        "Swift Cargo replaced BlueWave"
    )
    assert reasons[-1]["metadata"]["previous_close_at"] == "2026-11-10T18:00:00+00:00"


def test_capped_extension_is_reported(
    client: TestClient, clock: FrozenClock, db: Session, people: Suppliers
) -> None:
    rfq = make_rfq(db, people["buyer"], start=at(17, 0), close=at(18, 0), forced=at(18, 3),
                   trigger=TriggerType.BID_RECEIVED)  # fmt: skip
    db.commit()
    body = place(client, clock, rfq, people["A"], 100, at(17, 58)).json()
    assert body["extension"]["capped"] is True
    assert body["extension"]["new_close_at"] == "2026-11-10T18:03:00Z"
    log = client.get(f"/api/rfqs/{rfq.id}/activity").json()["items"][0]
    assert log["message"].startswith("Auction extended by 3 min (capped at the forced close time)")


# ---------------------------------------------------------------------------
# Concurrency (A20)
# ---------------------------------------------------------------------------


def test_a20_concurrent_bids_keep_every_invariant(db: Session) -> None:
    """20 bids from 4 suppliers at once, all inside the trigger window, each extending the
    auction by 1 minute. Without the row lock, extensions would be lost (two bids extending
    from the same close time) and the chain check below would fail."""
    now = datetime.now(UTC)
    buyer = make_user(db, UserRole.BUYER)
    suppliers = [make_user(db) for _ in range(4)]
    rfq = make_rfq(
        db,
        buyer,
        start=now - timedelta(hours=1),
        close=now + timedelta(minutes=5),
        forced=now + timedelta(hours=1),
        x=60,  # the whole remaining auction is inside the window
        y=1,
        trigger=TriggerType.BID_RECEIVED,
    )
    db.commit()
    supplier_ids = [s.id for s in suppliers]
    rfq_id = rfq.id

    def submit(n: int) -> bool:
        session = SessionLocal()
        try:
            supplier = session.get_one(User, supplier_ids[n % 4])
            body = BidCreate(
                carrier_name="Line",
                freight_charges=Decimal(10_000 - n * 10),
                origin_charges=Decimal(0),
                destination_charges=Decimal(0),
                transit_time_days=10,
                quote_validity_date=date(2027, 1, 1),
            )
            bid_service.submit_bid(session, rfq_id, supplier, body, SystemClock())
            return True
        except AppError as exc:
            # Same supplier racing itself: whichever lower bid lands first wins.
            assert exc.code == ErrorCode.BID_NOT_LOWER
            return False
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=10) as pool:
        accepted = sum(pool.map(submit, range(20)))

    db.expire_all()
    rfq = db.get_one(Rfq, rfq_id)
    latest = db.scalars(select(Bid).where(Bid.rfq_id == rfq_id, Bid.is_latest.is_(True))).all()
    assert sorted(b.supplier_id for b in latest) == sorted(supplier_ids)
    assert db.scalar(select(func.count()).where(Bid.rfq_id == rfq_id)) == accepted

    def count(kind: ActivityType) -> int:
        return (
            db.scalar(
                select(func.count()).where(ActivityLog.rfq_id == rfq_id, ActivityLog.type == kind)
            )
            or 0
        )

    assert count(ActivityType.BID_SUBMITTED) == accepted
    assert count(ActivityType.AUCTION_EXTENDED) == accepted == rfq.extension_count
    assert rfq.current_close_at == rfq.bid_close_at + timedelta(minutes=accepted)
    assert rfq.current_close_at <= rfq.forced_close_at

    chain = db.scalars(
        select(AuctionExtension)
        .where(AuctionExtension.rfq_id == rfq_id)
        .order_by(AuctionExtension.new_close_at)
    ).all()
    for earlier, later in itertools.pairwise(chain):
        assert later.previous_close_at == earlier.new_close_at
