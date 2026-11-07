"""Very large amounts: the per-charge limit and the total's column limit."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.domain.enums import AuctionStatus, UserRole
from tests.factories import T0, make_rfq, make_user

MAX_CHARGE = "999999999999.99"  # Numeric(14, 2)


def bid(freight: str, origin: str = "0", destination: str = "0") -> dict[str, object]:
    return {
        "carrier_name": "Big Line",
        "freight_charges": freight,
        "origin_charges": origin,
        "destination_charges": destination,
        "transit_time_days": 10,
        "quote_validity_date": "2026-12-31",
    }


def test_charges_whose_total_overflows_are_rejected_cleanly(
    client: TestClient, clock: FrozenClock, db: Session
) -> None:
    buyer = make_user(db, UserRole.BUYER)
    supplier = make_user(db)
    rfq = make_rfq(db, buyer, status=AuctionStatus.ACTIVE)
    db.commit()
    clock.set(T0.replace(minute=30))
    url, headers = f"/api/rfqs/{rfq.id}/bids", {"X-User-Id": str(supplier.id)}

    res = client.post(url, json=bid(MAX_CHARGE, "100", "100"), headers=headers)
    assert res.status_code == 422, res.text
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"

    res = client.post(url, json=bid(MAX_CHARGE), headers=headers)  # the largest total that fits
    assert res.status_code == 201, res.text
    assert res.json()["bid"]["total_amount"] == MAX_CHARGE
    listing = client.get("/api/rfqs").json()["items"][0]
    assert listing["lowest_bid"]["amount"] == MAX_CHARGE


def test_control_characters_are_rejected_not_crashed_on(
    client: TestClient, clock: FrozenClock, db: Session
) -> None:
    """PostgreSQL can't store NUL: it must be a 422, never a 500."""
    buyer = make_user(db, UserRole.BUYER)
    supplier = make_user(db)
    rfq = make_rfq(db, buyer, status=AuctionStatus.ACTIVE)
    db.commit()
    clock.set(T0.replace(minute=30))
    headers = {"X-User-Id": str(supplier.id)}
    for field, value in [("carrier_name", "Line\x00"), ("notes", "a\x00b"), ("notes", "bell\x07")]:
        body = {**bid("1000"), field: value}
        res = client.post(f"/api/rfqs/{rfq.id}/bids", json=body, headers=headers)
        assert res.status_code == 422, (field, res.text)
        assert res.json()["error"]["details"][0]["field"] == field

    ok = {**bid("1000"), "notes": "Line one\nLine two\tand a tab"}
    assert client.post(f"/api/rfqs/{rfq.id}/bids", json=ok, headers=headers).status_code == 201

    created = client.post(
        "/api/rfqs",
        json={
            "name": "Lane\x00",
            "pickup_date": "2026-12-01",
            "bid_start_at": "2026-11-10T12:35:00Z",
            "bid_close_at": "2026-11-10T13:00:00Z",
            "forced_close_at": "2026-11-10T13:30:00Z",
            "auction_config": {"trigger_window_minutes": 10, "extension_duration_minutes": 5,
                               "trigger_type": "L1_CHANGE"},
        },
        headers={"X-User-Id": str(buyer.id)},
    )  # fmt: skip
    assert created.status_code == 422
    assert created.json()["error"]["details"][0]["field"] == "name"

    res = client.get("/api/rfqs", params={"search": "a\x00b"})
    assert res.status_code == 422
    assert res.json()["error"]["details"][0]["field"] == "search"
