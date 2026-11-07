"""Scale guards: the listing and details cost a fixed number of SQL queries however many
auctions, suppliers or bids there are (no N+1), and stay fast at demo-plus scale."""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.db import engine
from app.domain.enums import AuctionStatus, UserRole
from app.models import Rfq, User
from tests.factories import T0, make_bid, make_rfq, make_user


@contextmanager
def count_queries() -> Iterator[list[str]]:
    statements: list[str] = []

    def record(_conn: Any, _cursor: Any, statement: str, *_: Any) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


def build(
    db: Session, auctions: int, suppliers: int, revisions: int
) -> tuple[list[Rfq], list[User]]:
    buyer = make_user(db, UserRole.BUYER)
    people = [make_user(db) for _ in range(suppliers)]
    rfqs = [
        make_rfq(
            db, buyer, name=f"Lane {i}", start=T0 - timedelta(hours=1), status=AuctionStatus.ACTIVE
        )
        for i in range(auctions)
    ]
    for rfq in rfqs:
        for n, supplier in enumerate(people):
            for r in range(revisions):
                make_bid(db, rfq, supplier, freight=f"{10_000 - n * 10 - r}.00",
                         is_latest=r == revisions - 1,
                         submitted_at=T0 - timedelta(minutes=50 - r, seconds=n))  # fmt: skip
    db.commit()
    return rfqs, people


def queries_for(client: TestClient, url: str) -> int:
    with count_queries() as statements:
        assert client.get(url).status_code == 200
    return len(statements)


def test_listing_query_count_does_not_grow_with_the_data(
    client: TestClient, clock: FrozenClock, db: Session
) -> None:
    clock.set(T0)
    build(db, auctions=2, suppliers=2, revisions=1)
    small = queries_for(client, "/api/rfqs")
    build(db, auctions=30, suppliers=5, revisions=2)
    large = queries_for(client, "/api/rfqs?page_size=100")
    assert large == small, f"{small} queries for 2 auctions, {large} for 32"


def test_detail_query_count_does_not_grow_with_suppliers(
    client: TestClient, clock: FrozenClock, db: Session
) -> None:
    clock.set(T0)
    (few,), _ = build(db, auctions=1, suppliers=2, revisions=1)
    (many,), _ = build(db, auctions=1, suppliers=50, revisions=3)
    for path in ("", "/bids", "/bids?history=true", "/activity"):
        small = queries_for(client, f"/api/rfqs/{few.id}{path}")
        large = queries_for(client, f"/api/rfqs/{many.id}{path}")
        assert large == small, f"{path or 'detail'}: {small} vs {large} queries"


def test_fifty_suppliers_and_hundreds_of_auctions_stay_fast(
    client: TestClient, clock: FrozenClock, db: Session
) -> None:
    clock.set(T0)
    build(db, auctions=200, suppliers=3, revisions=1)
    (big,), people = build(db, auctions=1, suppliers=50, revisions=5)

    started = time.perf_counter()
    listing = client.get("/api/rfqs", params={"page_size": 100}).json()
    detail = client.get(f"/api/rfqs/{big.id}").json()
    elapsed = time.perf_counter() - started

    assert listing["total"] == 201
    assert len(detail["ranking"]) == 50
    assert detail["stats"]["bid_count"] == 250
    assert [r["rank"] for r in detail["ranking"]] == list(range(1, 51))
    # Generous budget: catches accidental N+1 or missing indexes, not machine speed.
    assert elapsed < 2.0, f"listing + detail took {elapsed:.2f}s"

    # A bid at that scale is still a single quick transaction.
    clock.set(T0 + timedelta(minutes=1))
    started = time.perf_counter()
    res = client.post(
        f"/api/rfqs/{big.id}/bids",
        json={"carrier_name": "Scale Line", "freight_charges": "100.00", "origin_charges": "0",
              "destination_charges": "0", "transit_time_days": 5,
              "quote_validity_date": "2026-12-31"},
        headers={"X-User-Id": str(people[-1].id)},
    )  # fmt: skip
    assert res.status_code == 201, res.text
    assert res.json()["rank"] == 1
    assert time.perf_counter() - started < 1.0
