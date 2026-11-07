"""RFQ endpoints: create, listing, details, bids and activity. Case ids (A1, A17, ...) match
the test matrix in the project plan. The clock is frozen at T0 = 2026-11-10 12:00 UTC."""

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.errors import AppError, ErrorCode
from app.domain.enums import ActivityType, UserRole
from app.models import Rfq, User
from app.services import query_service
from app.services.activity_service import log_activity
from tests.factories import T0, make_bid, make_rfq, make_user


def iso(minutes: float) -> str:
    """T0 + minutes as an ISO string."""
    return (T0 + timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")


def create_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "Mumbai to Rotterdam, 2 x 40HC",
        "pickup_date": "2026-11-20",
        "bid_start_at": iso(60),
        "bid_close_at": iso(120),
        "forced_close_at": iso(180),
        "auction_config": {
            "trigger_window_minutes": 10,
            "extension_duration_minutes": 5,
            "trigger_type": "L1_CHANGE",
        },
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def buyer(db: Session) -> User:
    user = make_user(db, UserRole.BUYER, company="Acme Exports")
    db.commit()
    return user


def headers(user: User) -> dict[str, str]:
    return {"X-User-Id": str(user.id)}


def post_rfq(client: TestClient, user: User, **overrides: Any) -> Any:
    return client.post("/api/rfqs", json=create_payload(**overrides), headers=headers(user))


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("clock")
def test_a1_create_scheduled_rfq(client: TestClient, buyer: User) -> None:
    res = post_rfq(client, buyer)
    assert res.status_code == 201, res.text
    body = res.json()
    rfq = body["rfq"]
    assert rfq["reference_id"] == "RFQ-2026-0001"  # generated
    assert rfq["status"] == "SCHEDULED"
    assert rfq["current_close_at"] == rfq["bid_close_at"] == "2026-11-10T14:00:00Z"
    assert rfq["forced_close_at"] == "2026-11-10T15:00:00Z"
    assert rfq["extension_count"] == 0
    assert rfq["buyer"]["company_name"] == "Acme Exports"
    assert body["auction_config"] == {
        "trigger_window_minutes": 10,
        "extension_duration_minutes": 5,
        "trigger_type": "L1_CHANGE",
    }
    assert body["ranking"] == []
    assert body["stats"]["bid_count"] == 0
    assert body["stats"]["current_l1_amount"] is None

    activity = client.get(f"/api/rfqs/{rfq['id']}/activity").json()["items"]
    assert [a["type"] for a in activity] == ["RFQ_CREATED"]
    assert activity[0]["actor"]["company_name"] == "Acme Exports"
    assert activity[0]["message"] == "Acme Exports created RFQ RFQ-2026-0001"


@pytest.mark.usefixtures("clock")
def test_create_rfq_starting_now_is_active(client: TestClient, buyer: User) -> None:
    res = post_rfq(client, buyer, bid_start_at=iso(0), reference_id="lane-7")
    assert res.status_code == 201, res.text
    rfq = res.json()["rfq"]
    assert rfq["status"] == "ACTIVE"
    assert rfq["reference_id"] == "LANE-7"  # normalised to upper case

    activity = client.get(f"/api/rfqs/{rfq['id']}/activity").json()["items"]
    assert [a["type"] for a in activity] == ["AUCTION_STARTED", "RFQ_CREATED"]
    assert activity[0]["actor"] is None


@pytest.mark.usefixtures("clock")
def test_start_time_tolerance(client: TestClient, buyer: User) -> None:
    assert post_rfq(client, buyer, bid_start_at=iso(-0.5)).status_code == 201

    res = post_rfq(client, buyer, bid_start_at=iso(-2))
    assert res.status_code == 422
    error = res.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"][0]["field"] == "bid_start_at"


@pytest.mark.usefixtures("clock")
@pytest.mark.parametrize("forced_minutes", [120, 90], ids=["equal", "earlier"])
def test_a2_forced_close_must_be_after_close(
    client: TestClient, buyer: User, forced_minutes: int
) -> None:
    res = post_rfq(client, buyer, forced_close_at=iso(forced_minutes))
    assert res.status_code == 422
    error = res.json()["error"]
    assert error["code"] == "FORCED_CLOSE_NOT_AFTER_CLOSE"
    assert error["details"] == [
        {
            "field": "forced_close_at",
            "message": "Forced bid close time must be later than the bid close time",
        }
    ]


@pytest.mark.usefixtures("clock")
@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"bid_close_at": iso(60)}, "bid_close_at"),  # A3
        ({"pickup_date": "2026-11-09"}, "pickup_date"),
        (
            {
                "auction_config": {
                    "trigger_window_minutes": 0,
                    "extension_duration_minutes": 5,
                    "trigger_type": "L1_CHANGE",
                }
            },
            "auction_config.trigger_window_minutes",
        ),  # A4
        ({"name": ""}, "name"),
    ],
)
def test_validation_errors_point_at_the_field(
    client: TestClient, buyer: User, overrides: dict[str, Any], field: str
) -> None:
    res = post_rfq(client, buyer, **overrides)
    assert res.status_code == 422
    body = res.json()["error"]
    assert body["code"] == "VALIDATION_ERROR"
    assert [d["field"] for d in body["details"]] == [field]


def test_a5_only_buyers_create_rfqs(client: TestClient, db: Session) -> None:
    supplier = make_user(db, UserRole.SUPPLIER)
    db.commit()
    assert post_rfq(client, supplier).status_code == 403
    assert client.post("/api/rfqs", json=create_payload()).status_code == 401


@pytest.mark.usefixtures("clock")
def test_a6_duplicate_reference_id(client: TestClient, buyer: User) -> None:
    assert post_rfq(client, buyer, reference_id="RFQ-X-1").status_code == 201
    res = post_rfq(client, buyer, reference_id="rfq-x-1")
    assert res.status_code == 409
    error = res.json()["error"]
    assert error["code"] == "DUPLICATE_REFERENCE"
    assert error["details"][0]["field"] == "reference_id"


@pytest.mark.usefixtures("clock")
def test_generated_reference_skips_ids_typed_by_hand(client: TestClient, buyer: User) -> None:
    assert post_rfq(client, buyer, reference_id="RFQ-2026-0001").status_code == 201
    assert post_rfq(client, buyer).json()["rfq"]["reference_id"] == "RFQ-2026-0002"
    assert post_rfq(client, buyer).json()["rfq"]["reference_id"] == "RFQ-2026-0003"


# ---------------------------------------------------------------------------
# Listing (A17)
# ---------------------------------------------------------------------------


@pytest.fixture
def auctions(db: Session, buyer: User) -> dict[str, Rfq]:
    """One auction per status. Stored status is SCHEDULED for all of them, so the API has to
    derive each status from the times."""
    s1, s2, s3 = (make_user(db, company=c) for c in ("BlueWave", "Swift Cargo", "Oceanic"))
    h = timedelta(hours=1)
    m = timedelta(minutes=1)
    upcoming = make_rfq(db, buyer, name="Upcoming lane", start=T0 + h, close=T0 + 2 * h,
                        forced=T0 + 3 * h)  # fmt: skip
    active = make_rfq(db, buyer, name="Active lane", reference_id="ACT-1", start=T0 - h,
                      close=T0 + 30 * m, forced=T0 + h)  # fmt: skip
    closed = make_rfq(db, buyer, name="Closed lane", start=T0 - 3 * h, close=T0 - 90 * m,
                      forced=T0 - h)  # fmt: skip
    forced = make_rfq(db, buyer, name="Forced lane", start=T0 - 3 * h, close=T0 - 2 * h,
                      forced=T0 - h, current_close=T0 - h, extension_count=4)  # fmt: skip

    make_bid(db, active, s1, freight="1200.00", is_latest=False, submitted_at=T0 - 50 * m)
    make_bid(db, active, s1, freight="1000.00", submitted_at=T0 - 40 * m)  # 1150 total
    make_bid(db, active, s2, freight="1100.00", submitted_at=T0 - 45 * m)  # 1250 total
    make_bid(db, forced, s3, freight="900.00", submitted_at=T0 - 70 * m)
    db.commit()
    return {"upcoming": upcoming, "active": active, "closed": closed, "forced": forced}


@pytest.mark.usefixtures("clock")
def test_a17_listing_fields_and_derived_statuses(
    client: TestClient, auctions: dict[str, Rfq]
) -> None:
    body = client.get("/api/rfqs").json()
    assert body["total"] == 4
    items = body["items"]
    # Active first, then upcoming, then ended (most recently ended first).
    assert [i["name"] for i in items] == ["Active lane", "Upcoming lane", "Forced lane",
                                          "Closed lane"]  # fmt: skip
    assert [i["status"] for i in items] == ["ACTIVE", "SCHEDULED", "FORCE_CLOSED", "CLOSED"]

    active = items[0]
    assert active["lowest_bid"] == {
        "amount": "1150.00",
        "currency": "INR",
        "supplier_name": "BlueWave",
    }
    assert active["bid_count"] == 3  # includes the superseded revision
    assert active["supplier_count"] == 2
    assert (
        active["trigger_window_minutes"] == auctions["active"].auction_config.trigger_window_minutes
    )
    assert active["current_close_at"] == "2026-11-10T12:30:00Z"
    assert active["forced_close_at"] == "2026-11-10T13:00:00Z"

    assert items[1]["lowest_bid"] is None
    assert items[2]["extension_count"] == 4
    assert items[2]["current_close_at"] == items[2]["forced_close_at"]


@pytest.mark.usefixtures("clock")
@pytest.mark.parametrize(
    ("status", "name"),
    [
        ("SCHEDULED", "Upcoming lane"),
        ("ACTIVE", "Active lane"),
        ("CLOSED", "Closed lane"),
        ("FORCE_CLOSED", "Forced lane"),
    ],
)
def test_listing_status_filter(
    client: TestClient, auctions: dict[str, Rfq], status: str, name: str
) -> None:
    body = client.get("/api/rfqs", params={"status": status}).json()
    assert [i["name"] for i in body["items"]] == [name]
    assert body["total"] == 1
    # The tab counts ignore the status filter.
    assert body["status_counts"] == {"SCHEDULED": 1, "ACTIVE": 1, "CLOSED": 1, "FORCE_CLOSED": 1}


@pytest.mark.usefixtures("clock")
def test_listing_status_counts_follow_search_and_clock(
    client: TestClient, auctions: dict[str, Rfq], clock: FrozenClock
) -> None:
    counts = client.get("/api/rfqs", params={"search": "ACT-"}).json()["status_counts"]
    assert counts == {"SCHEDULED": 0, "ACTIVE": 1, "CLOSED": 0, "FORCE_CLOSED": 0}

    clock.advance(minutes=30)  # the active auction closes
    body = client.get("/api/rfqs").json()
    assert body["status_counts"] == {"SCHEDULED": 1, "ACTIVE": 0, "CLOSED": 2, "FORCE_CLOSED": 1}
    assert body["total"] == 4

    empty = client.get("/api/rfqs", params={"search": "nothing matches"}).json()
    assert empty["status_counts"] == {"SCHEDULED": 0, "ACTIVE": 0, "CLOSED": 0, "FORCE_CLOSED": 0}
    assert empty["total"] == 0


@pytest.mark.usefixtures("clock")
def test_listing_status_follows_the_clock(
    client: TestClient, auctions: dict[str, Rfq], clock: FrozenClock
) -> None:
    clock.advance(minutes=30)  # the active auction's close time
    statuses = {i["name"]: i["status"] for i in client.get("/api/rfqs").json()["items"]}
    assert statuses["Active lane"] == "CLOSED"


@pytest.mark.usefixtures("clock")
@pytest.mark.parametrize(
    ("search", "expected"),
    [("ACTIVE", ["Active lane"]), ("act-", ["Active lane"]), ("lane", 4), ("%", [])],
)
def test_listing_search(
    client: TestClient, auctions: dict[str, Rfq], search: str, expected: list[str] | int
) -> None:
    items = client.get("/api/rfqs", params={"search": search}).json()["items"]
    if isinstance(expected, int):
        assert len(items) == expected
    else:
        assert [i["name"] for i in items] == expected


@pytest.mark.usefixtures("clock")
def test_listing_pagination(client: TestClient, auctions: dict[str, Rfq]) -> None:
    first = client.get("/api/rfqs", params={"page_size": 3}).json()
    second = client.get("/api/rfqs", params={"page_size": 3, "page": 2}).json()
    assert (len(first["items"]), len(second["items"])) == (3, 1)
    assert first["total"] == second["total"] == 4
    assert second["items"][0]["name"] == "Closed lane"
    assert client.get("/api/rfqs", params={"page_size": 101}).status_code == 422


# ---------------------------------------------------------------------------
# Details (A18), bids and activity
# ---------------------------------------------------------------------------


@pytest.fixture
def ranked_auction(db: Session, buyer: User) -> Rfq:
    s1, s2, s3 = (make_user(db, company=c) for c in ("BlueWave", "Swift Cargo", "Oceanic"))
    m = timedelta(minutes=1)
    rfq = make_rfq(db, buyer, start=T0 - 60 * m, close=T0 + 30 * m, forced=T0 + 60 * m,
                   current_close=T0 + 45 * m, extension_count=3)  # fmt: skip
    make_bid(db, rfq, s1, freight="1150.00", is_latest=False, submitted_at=T0 - 50 * m)  # 1300
    make_bid(db, rfq, s2, freight="1050.00", submitted_at=T0 - 40 * m)  # 1200
    make_bid(db, rfq, s1, freight="1000.00", submitted_at=T0 - 30 * m)  # 1150
    make_bid(db, rfq, s3, freight="1000.00", submitted_at=T0 - 20 * m)  # 1150, later: L2
    db.commit()
    return rfq


@pytest.mark.usefixtures("clock")
def test_a18_detail_ranking_breakdown_and_stats(client: TestClient, ranked_auction: Rfq) -> None:
    body = client.get(f"/api/rfqs/{ranked_auction.id}").json()
    assert body["rfq"]["status"] == "ACTIVE"

    ranking = body["ranking"]
    assert [(r["rank_label"], r["supplier"]["company_name"]) for r in ranking] == [
        ("L1", "BlueWave"),  # ties with Oceanic at 1150 but bid earlier
        ("L2", "Oceanic"),
        ("L3", "Swift Cargo"),
    ]
    top = ranking[0]
    assert (top["freight_charges"], top["origin_charges"], top["destination_charges"]) == (
        "1000.00",
        "100.00",
        "50.00",
    )
    assert top["total_amount"] == "1150.00"
    assert top["transit_time_days"] == 20
    assert top["quote_validity_date"] == "2026-12-31"
    assert top["revision_count"] == 2

    assert body["stats"] == {
        "bid_count": 4,
        "supplier_count": 3,
        "extension_count": 3,
        "total_extended_minutes": 15,
        "first_l1_amount": "1300.00",
        "current_l1_amount": "1150.00",
        "savings_pct": str((Decimal(150) / Decimal(1300) * 100).quantize(Decimal("0.01"))),
    }


def test_unknown_rfq_is_404(client: TestClient) -> None:
    for path in ("", "/bids", "/activity"):
        res = client.get(f"/api/rfqs/00000000-0000-0000-0000-000000000000{path}")
        assert res.status_code == 404, path
        assert res.json()["error"]["code"] == "NOT_FOUND"
    assert client.get("/api/rfqs/not-a-uuid").status_code == 422


def test_bids_latest_in_rank_order_and_full_history(
    client: TestClient, ranked_auction: Rfq
) -> None:
    latest = client.get(f"/api/rfqs/{ranked_auction.id}/bids").json()["items"]
    assert [b["supplier"]["company_name"] for b in latest] == ["BlueWave", "Oceanic", "Swift Cargo"]
    assert all(b["is_latest"] for b in latest)

    history = client.get(f"/api/rfqs/{ranked_auction.id}/bids", params={"history": True})
    items = history.json()["items"]
    assert [b["total_amount"] for b in items] == ["1150.00", "1150.00", "1200.00", "1300.00"]
    assert [b["is_latest"] for b in items] == [True, True, True, False]


def test_activity_newest_first_with_pagination(
    client: TestClient, db: Session, ranked_auction: Rfq
) -> None:
    for i in range(5):
        log_activity(
            db,
            rfq_id=ranked_auction.id,
            type=ActivityType.BID_SUBMITTED,
            message=f"entry {i}",
            at=T0,  # identical timestamps: order must still be stable
            meta={"n": i},
        )
    db.commit()
    url = f"/api/rfqs/{ranked_auction.id}/activity"

    first = client.get(url, params={"limit": 2}).json()
    assert [a["message"] for a in first["items"]] == ["entry 4", "entry 3"]
    assert first["items"][0]["metadata"] == {"n": 4}

    second = client.get(url, params={"limit": 2, "before_id": first["next_before_id"]}).json()
    assert [a["message"] for a in second["items"]] == ["entry 2", "entry 1"]

    last = client.get(url, params={"limit": 2, "before_id": second["next_before_id"]}).json()
    assert [a["message"] for a in last["items"]] == ["entry 0"]
    assert last["next_before_id"] is None


def test_single_listing_row_for_live_updates(db: Session, auctions: dict[str, Rfq]) -> None:
    item = query_service.get_list_item(db, auctions["active"].id, T0)
    assert (item.name, item.status, item.bid_count) == ("Active lane", "ACTIVE", 3)
    assert item.lowest_bid is not None and item.lowest_bid.amount == Decimal("1150.00")

    with pytest.raises(AppError) as exc_info:
        query_service.get_list_item(db, uuid.uuid4(), T0)
    assert exc_info.value.code == ErrorCode.NOT_FOUND
