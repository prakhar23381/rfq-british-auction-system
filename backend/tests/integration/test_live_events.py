"""Which live events each change publishes, and what they carry (recorded, no Redis)."""

import uuid
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.domain.enums import UserRole
from app.models import ActivityLog, Rfq, User
from app.realtime.events import NullPublisher
from app.services import event_service, lifecycle_service, query_service
from app.services.lifecycle_service import Outcome
from tests.factories import T0, make_rfq, make_user
from tests.fakes import Event, RecordingPublisher

START = T0
CLOSE = T0 + timedelta(hours=1)
FORCED = T0 + timedelta(hours=2)
MIN = timedelta(minutes=1)


@pytest.fixture
def people(db: Session) -> dict[str, User]:
    users = {
        "buyer": make_user(db, UserRole.BUYER, company="Acme Exports"),
        "A": make_user(db, company="BlueWave"),
        "B": make_user(db, company="Swift Cargo"),
    }
    db.commit()
    return users


@pytest.fixture
def rfq(db: Session, people: dict[str, User]) -> Rfq:
    created = make_rfq(db, people["buyer"], start=START, close=CLOSE, forced=FORCED, x=10, y=5)
    db.commit()
    return created


def bid(
    client: TestClient, clock: FrozenClock, rfq: Rfq, supplier: User, amount: int, at: Any
) -> Any:
    clock.set(at)
    return client.post(
        f"/api/rfqs/{rfq.id}/bids",
        json={
            "carrier_name": "Line",
            "freight_charges": str(amount),
            "origin_charges": "0",
            "destination_charges": "0",
            "transit_time_days": 10,
            "quote_validity_date": "2026-12-31",
        },
        headers={"X-User-Id": str(supplier.id)},
    )


def newest_activity_id(db: Session, rfq: Rfq) -> int:
    return db.scalar(select(func.max(ActivityLog.id)).where(ActivityLog.rfq_id == rfq.id)) or 0


def activity_types(event: Event) -> list[str]:
    return [a["type"] for a in event.data["activity"]]


def test_create_publishes_the_new_listing_row(
    client: TestClient, clock: FrozenClock, db: Session, people: dict[str, User],
    publisher: RecordingPublisher,
) -> None:  # fmt: skip
    clock.set(START - 30 * MIN)
    res = client.post(
        "/api/rfqs",
        json={
            "name": "Mumbai to Rotterdam",
            "pickup_date": "2026-12-01",
            "bid_start_at": START.isoformat(),
            "bid_close_at": CLOSE.isoformat(),
            "forced_close_at": FORCED.isoformat(),
            "auction_config": {
                "trigger_window_minutes": 10,
                "extension_duration_minutes": 5,
                "trigger_type": "L1_CHANGE",
            },
        },
        headers={"X-User-Id": str(people["buyer"].id)},
    )
    detail = res.json()
    [event] = publisher.events
    assert (event.type, event.channel) == ("rfq.created", "listing")
    assert event.data["item"]["id"] == detail["rfq"]["id"]
    assert event.data["item"]["status"] == "SCHEDULED"
    assert event.data["version"] == event.data["item"]["version"] == detail["rfq"]["version"] > 0


def test_bid_outside_the_window(
    client: TestClient, clock: FrozenClock, db: Session, people: dict[str, User], rfq: Rfq,
    publisher: RecordingPublisher,
) -> None:  # fmt: skip
    bid(client, clock, rfq, people["A"], 1000, START + MIN)
    publisher.events.clear()

    res = bid(client, clock, rfq, people["B"], 900, START + 2 * MIN)
    assert res.status_code == 201
    assert publisher.types() == ["bid.submitted", "listing.updated"]
    submitted, listing = publisher.events
    assert submitted.channel == f"rfq:{rfq.id}"
    data = submitted.data
    assert (data["rank"], data["rank_label"], data["extension"]) == (1, "L1", None)
    assert data["bid"]["id"] == res.json()["bid"]["id"]
    assert [(r["rank_label"], r["supplier"]["company_name"]) for r in data["ranking"]] == [
        ("L1", "Swift Cargo"),
        ("L2", "BlueWave"),
    ]
    assert data["stats"]["bid_count"] == 2
    assert activity_types(submitted) == ["BID_SUBMITTED"]
    assert data["activity"][0]["actor"]["company_name"] == "Swift Cargo"
    assert data["version"] == data["rfq"]["version"] == newest_activity_id(db, rfq)

    assert listing.channel == "listing"
    assert listing.data["item"]["lowest_bid"]["supplier_name"] == "Swift Cargo"
    assert listing.data["version"] == data["version"]


def test_first_bid_also_announces_that_bidding_opened(
    client: TestClient, clock: FrozenClock, people: dict[str, User], rfq: Rfq,
    publisher: RecordingPublisher,
) -> None:  # fmt: skip
    bid(client, clock, rfq, people["A"], 1000, START + MIN)  # stored status is still SCHEDULED
    assert publisher.types() == ["auction.status", "bid.submitted", "listing.updated"]
    status, submitted, _ = publisher.events
    assert status.data["status"] == "ACTIVE"
    assert activity_types(status) == ["AUCTION_STARTED"]
    assert activity_types(submitted) == ["BID_SUBMITTED"]


def test_extending_bid_sends_each_activity_entry_once(
    client: TestClient, clock: FrozenClock, db: Session, people: dict[str, User], rfq: Rfq,
    publisher: RecordingPublisher,
) -> None:  # fmt: skip
    bid(client, clock, rfq, people["A"], 1000, START + MIN)
    publisher.events.clear()

    bid(client, clock, rfq, people["B"], 900, CLOSE - 2 * MIN)  # new L1 in the window
    assert publisher.types() == ["bid.submitted", "auction.extended", "listing.updated"]
    submitted, extended, listing = publisher.events
    assert submitted.data["rfq"]["current_close_at"] == "2026-11-10T13:05:00Z"
    assert submitted.data["extension"]["applied"] is True
    assert activity_types(submitted) == ["BID_SUBMITTED"]
    assert activity_types(extended) == ["AUCTION_EXTENDED"]
    assert extended.data["previous_close_at"] == "2026-11-10T13:00:00Z"
    assert extended.data["new_close_at"] == "2026-11-10T13:05:00Z"
    assert extended.data["extension_count"] == 1
    assert "Swift Cargo replaced BlueWave" in extended.data["reason"]
    assert listing.data["item"]["current_close_at"] == "2026-11-10T13:05:00Z"

    versions = {e.data["version"] for e in publisher.events}
    assert versions == {newest_activity_id(db, rfq)}
    detail = client.get(f"/api/rfqs/{rfq.id}").json()
    assert detail["rfq"]["version"] == versions.pop()


def test_trigger_at_the_cap_reports_the_skip_without_an_extension_event(
    client: TestClient, clock: FrozenClock, db: Session, people: dict[str, User],
    publisher: RecordingPublisher,
) -> None:  # fmt: skip
    capped = make_rfq(db, people["buyer"], start=START, close=CLOSE, forced=CLOSE + MIN,
                      current_close=CLOSE + MIN, extension_count=1, x=10, y=5)  # fmt: skip
    db.commit()
    bid(client, clock, capped, people["A"], 1000, CLOSE)
    assert publisher.types() == ["auction.status", "bid.submitted", "listing.updated"]
    submitted = publisher.events[1]
    assert submitted.data["extension"] == {
        "applied": False,
        "previous_close_at": "2026-11-10T13:01:00Z",
        "new_close_at": "2026-11-10T13:01:00Z",
        "capped": True,
        "reason": submitted.data["extension"]["reason"],
    }
    assert activity_types(submitted) == ["BID_SUBMITTED", "EXTENSION_SKIPPED"]


def test_rejected_bid_publishes_nothing(
    client: TestClient, clock: FrozenClock, people: dict[str, User], rfq: Rfq,
    publisher: RecordingPublisher,
) -> None:  # fmt: skip
    bid(client, clock, rfq, people["A"], 1000, START + MIN)
    publisher.events.clear()
    assert bid(client, clock, rfq, people["A"], 1000, START + 2 * MIN).status_code == 422
    assert bid(client, clock, rfq, people["B"], 500, CLOSE).status_code == 409
    assert publisher.events == []


def test_close_publishes_status_and_listing(
    client: TestClient, clock: FrozenClock, db: Session, people: dict[str, User], rfq: Rfq,
    publisher: RecordingPublisher,
) -> None:  # fmt: skip
    bid(client, clock, rfq, people["A"], 1000, START + MIN)
    publisher.events.clear()

    result = lifecycle_service.close_auction(db, rfq.id, FrozenClock(CLOSE), publisher=publisher)
    assert result.outcome == Outcome.UPDATED
    assert publisher.types() == ["auction.status", "listing.updated"]
    status, listing = publisher.events
    assert status.channel == f"rfq:{rfq.id}"
    assert status.data["status"] == "CLOSED"
    assert status.data["rfq"]["closed_at"] == "2026-11-10T13:00:00Z"
    assert activity_types(status) == ["AUCTION_CLOSED"]
    assert status.data["activity"][0]["actor"] is None
    assert listing.data["item"]["status"] == "CLOSED"
    assert status.data["version"] == listing.data["version"] == newest_activity_id(db, rfq)


def test_noop_lifecycle_jobs_publish_nothing(
    db: Session, rfq: Rfq, publisher: RecordingPublisher
) -> None:
    clock = FrozenClock(CLOSE)
    lifecycle_service.close_auction(db, rfq.id, clock, publisher=NullPublisher())
    lifecycle_service.close_auction(db, rfq.id, clock, publisher=publisher)  # already closed
    lifecycle_service.close_auction(db, rfq.id, clock, publisher=publisher,
                                    expected_close_at=CLOSE - MIN)  # fmt: skip
    assert lifecycle_service.sweep(db, clock, publisher=publisher) == []
    assert publisher.events == []


def test_versions_increase_with_every_change(
    client: TestClient, clock: FrozenClock, people: dict[str, User], rfq: Rfq,
    publisher: RecordingPublisher,
) -> None:  # fmt: skip
    for n, (supplier, amount) in enumerate([("A", 1000), ("B", 900), ("A", 800), ("B", 700)]):
        bid(client, clock, rfq, people[supplier], amount, CLOSE - (10 - n) * MIN)
    versions = [e.data["version"] for e in publisher.of_type("bid.submitted")]
    assert versions == sorted(versions)
    assert len(set(versions)) == len(versions)


def test_late_publisher_sends_a_snapshot_consistent_with_its_version(
    client: TestClient, clock: FrozenClock, db: Session, people: dict[str, User], rfq: Rfq,
    publisher: RecordingPublisher,
) -> None:  # fmt: skip
    """Bid 1's events are built after bid 2 committed (two requests racing). The snapshot then
    shows both bids and carries bid 2's version, so a client never mixes old state with a new
    version, and ignores whichever copy arrives second."""
    first = bid(client, clock, rfq, people["A"], 1000, START + MIN).json()
    bid(client, clock, rfq, people["B"], 900, START + 2 * MIN)
    publisher.events.clear()

    event_service.publish_bid(
        publisher,
        rfq_id=rfq.id,
        bid_id=uuid.UUID(first["bid"]["id"]),
        rank=1,
        extension=None,
        activity_ids=[],
        now=START + 2 * MIN,
    )
    submitted = publisher.of_type("bid.submitted")[0]
    assert submitted.data["version"] == newest_activity_id(db, rfq)
    assert len(submitted.data["ranking"]) == 2


def test_a_broken_event_never_fails_the_request(
    client: TestClient, clock: FrozenClock, people: dict[str, User], rfq: Rfq,
    publisher: RecordingPublisher, monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:  # fmt: skip
    monkeypatch.setattr(event_service, "STRICT", False)

    def broken(*_: Any, **__: Any) -> None:
        raise RuntimeError("payload bug")

    monkeypatch.setattr(query_service, "get_rfq_detail", broken)
    res = bid(client, clock, rfq, people["A"], 1000, START + MIN)
    assert res.status_code == 201
    assert "Could not publish live events (publish_bid)" in caplog.text


def test_listing_and_detail_expose_the_same_version(
    client: TestClient, clock: FrozenClock, db: Session, people: dict[str, User], rfq: Rfq
) -> None:
    bid(client, clock, rfq, people["A"], 1000, START + MIN)
    listing = client.get("/api/rfqs").json()["items"][0]
    detail = client.get(f"/api/rfqs/{rfq.id}").json()
    assert listing["version"] == detail["rfq"]["version"] == newest_activity_id(db, rfq)
