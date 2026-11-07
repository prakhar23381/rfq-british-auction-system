"""Auction lifecycle: start/close jobs, the sweeper, and how they interact with bids (A21-A23)."""

import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock, utc_now
from app.db import SessionLocal
from app.domain.enums import ActivityType, AuctionStatus, UserRole
from app.models import ActivityLog, Rfq, User
from app.services import lifecycle_service
from app.services.lifecycle_service import Outcome
from app.workers import scheduling as celery_scheduling
from app.workers import tasks
from tests.factories import T0, make_bid, make_rfq, make_user
from tests.fakes import RecordingScheduler

START = T0
CLOSE = T0 + timedelta(hours=1)
FORCED = T0 + timedelta(hours=2)
MIN = timedelta(minutes=1)


@pytest.fixture
def buyer(db: Session) -> User:
    user = make_user(db, UserRole.BUYER, company="Acme Exports")
    db.commit()
    return user


def scheduled(db: Session, buyer: User, **kwargs: Any) -> Rfq:
    rfq = make_rfq(db, buyer, start=START, close=CLOSE, forced=FORCED, **kwargs)
    db.commit()
    return rfq


def active(db: Session, buyer: User, **kwargs: Any) -> Rfq:
    return scheduled(db, buyer, status=AuctionStatus.ACTIVE, **kwargs)


def log(db: Session, rfq: Rfq) -> list[ActivityLog]:
    db.expire_all()
    return list(
        db.scalars(select(ActivityLog).where(ActivityLog.rfq_id == rfq.id).order_by(ActivityLog.id))
    )


def stored(db: Session, rfq: Rfq) -> Rfq:
    db.expire_all()
    return db.get_one(Rfq, rfq.id)


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------


def test_start_opens_a_scheduled_auction_once(db: Session, buyer: User) -> None:
    rfq = scheduled(db, buyer)
    clock = FrozenClock(START + timedelta(seconds=2))

    result = lifecycle_service.start_auction(db, rfq.id, clock)
    assert result.outcome == Outcome.UPDATED
    assert result.transitions == (ActivityType.AUCTION_STARTED,)
    assert stored(db, rfq).status == AuctionStatus.ACTIVE
    [entry] = log(db, rfq)
    assert (entry.type, entry.message) == (ActivityType.AUCTION_STARTED, "Bidding opened")
    assert entry.created_at == START  # dated at the scheduled start, not when the job ran

    again = lifecycle_service.start_auction(db, rfq.id, clock)
    assert again.outcome == Outcome.UNCHANGED
    assert len(log(db, rfq)) == 1


def test_start_job_that_fires_early_asks_to_retry(db: Session, buyer: User) -> None:
    rfq = scheduled(db, buyer)
    result = lifecycle_service.start_auction(db, rfq.id, FrozenClock(START - MIN))
    assert result.outcome == Outcome.NOT_DUE
    assert result.due_at == START
    assert stored(db, rfq).status == AuctionStatus.SCHEDULED


def test_unknown_rfq_is_reported_not_raised(db: Session) -> None:
    missing = uuid.uuid4()
    clock = FrozenClock(T0)
    assert lifecycle_service.start_auction(db, missing, clock).outcome == Outcome.NOT_FOUND
    assert lifecycle_service.close_auction(db, missing, clock).outcome == Outcome.NOT_FOUND


# ---------------------------------------------------------------------------
# Close
# ---------------------------------------------------------------------------


def test_close_records_l1_and_is_idempotent(db: Session, buyer: User) -> None:
    rfq = active(db, buyer)
    swift = make_user(db, company="Swift Cargo")
    bluewave = make_user(db, company="BlueWave")
    make_bid(db, rfq, bluewave, freight="2000.00", is_latest=False)
    make_bid(db, rfq, bluewave, freight="1500.00")
    make_bid(db, rfq, swift, freight="1200.00")
    db.commit()
    clock = FrozenClock(CLOSE + timedelta(seconds=1))

    result = lifecycle_service.close_auction(db, rfq.id, clock, expected_close_at=CLOSE)
    assert (result.outcome, result.status) == (Outcome.UPDATED, AuctionStatus.CLOSED)

    rfq = stored(db, rfq)
    assert rfq.status == AuctionStatus.CLOSED
    assert rfq.closed_at == CLOSE
    [entry] = log(db, rfq)
    assert entry.type == ActivityType.AUCTION_CLOSED
    assert entry.created_at == CLOSE
    assert entry.message == (
        "Auction closed. L1: Swift Cargo at INR 1,350.00 (3 bids from 2 suppliers)"
    )
    assert entry.meta["l1"]["supplier_id"] == str(swift.id)
    assert entry.meta["l1"]["total_amount"] == "1350.00"
    assert (entry.meta["bid_count"], entry.meta["supplier_count"]) == (3, 2)

    again = lifecycle_service.close_auction(db, rfq.id, clock, expected_close_at=CLOSE)
    assert again.outcome == Outcome.UNCHANGED
    assert lifecycle_service.sweep(db, clock) == []
    assert len(log(db, rfq)) == 1


def test_close_with_no_bids(db: Session, buyer: User) -> None:
    rfq = active(db, buyer)
    lifecycle_service.close_auction(db, rfq.id, FrozenClock(CLOSE))
    [entry] = log(db, rfq)
    assert entry.message == "Auction closed with no bids"
    assert entry.meta["l1"] is None


def test_close_at_the_forced_cap_is_a_force_close(db: Session, buyer: User) -> None:
    rfq = active(db, buyer, current_close=FORCED, extension_count=12)
    make_bid(db, rfq, make_user(db, company="Swift Cargo"))
    db.commit()

    result = lifecycle_service.close_auction(db, rfq.id, FrozenClock(FORCED))
    assert result.status == AuctionStatus.FORCE_CLOSED
    [entry] = log(db, rfq)
    assert entry.type == ActivityType.AUCTION_FORCE_CLOSED
    assert entry.message.startswith("Auction force closed at its forced close time. L1: Swift")
    assert entry.meta["extension_count"] == 12
    assert stored(db, rfq).closed_at == FORCED


def test_a22_close_job_for_an_old_close_time_does_nothing(db: Session, buyer: User) -> None:
    rfq = active(db, buyer, current_close=CLOSE + 5 * MIN, extension_count=1)
    result = lifecycle_service.close_auction(
        db, rfq.id, FrozenClock(CLOSE), expected_close_at=CLOSE
    )
    assert result.outcome == Outcome.STALE
    assert stored(db, rfq).status == AuctionStatus.ACTIVE
    assert log(db, rfq) == []


def test_close_job_that_fires_early_asks_to_retry(db: Session, buyer: User) -> None:
    rfq = active(db, buyer)
    result = lifecycle_service.close_auction(
        db, rfq.id, FrozenClock(CLOSE - timedelta(seconds=1)), expected_close_at=CLOSE
    )
    assert (result.outcome, result.due_at) == (Outcome.NOT_DUE, CLOSE)
    assert stored(db, rfq).status == AuctionStatus.ACTIVE


def test_very_late_job_starts_then_closes_in_order(db: Session, buyer: User) -> None:
    rfq = scheduled(db, buyer)  # the start job never ran
    result = lifecycle_service.close_auction(db, rfq.id, FrozenClock(CLOSE + timedelta(hours=3)))
    assert result.transitions == (ActivityType.AUCTION_STARTED, ActivityType.AUCTION_CLOSED)
    assert [(e.type, e.created_at) for e in log(db, rfq)] == [
        (ActivityType.AUCTION_STARTED, START),
        (ActivityType.AUCTION_CLOSED, CLOSE),
    ]


# ---------------------------------------------------------------------------
# Sweeper (A23)
# ---------------------------------------------------------------------------


def test_a23_sweeper_catches_up_overdue_auctions_only(db: Session, buyer: User) -> None:
    now = CLOSE + MIN
    due_start = make_rfq(db, buyer, start=now - MIN, close=now + 60 * MIN,
                         forced=now + 120 * MIN)  # fmt: skip
    due_close = active(db, buyer, reference_id="DUE-CLOSE")
    future = make_rfq(db, buyer, start=now + MIN, close=now + 2 * MIN, forced=now + 3 * MIN)
    finished = active(db, buyer, reference_id="DONE")
    db.commit()
    lifecycle_service.close_auction(db, finished.id, FrozenClock(now))

    results = {r.rfq_id: r for r in lifecycle_service.sweep(db, FrozenClock(now))}
    assert set(results) == {due_start.id, due_close.id}
    assert results[due_start.id].status == AuctionStatus.ACTIVE
    assert results[due_close.id].status == AuctionStatus.CLOSED
    assert stored(db, future).status == AuctionStatus.SCHEDULED

    assert lifecycle_service.sweep(db, FrozenClock(now)) == []  # nothing left to do


def test_sweeper_skips_an_auction_locked_by_a_bid(db: Session, buyer: User) -> None:
    rfq = active(db, buyer)
    clock = FrozenClock(CLOSE)
    with SessionLocal() as bidder:
        bidder.scalars(select(Rfq).where(Rfq.id == rfq.id).with_for_update()).one()
        started = time.monotonic()
        [result] = lifecycle_service.sweep(db, clock)
        assert result.outcome == Outcome.BUSY
        assert time.monotonic() - started < 2  # skipped, not waited on
        bidder.rollback()

    [result] = lifecycle_service.sweep(db, clock)
    assert result.status == AuctionStatus.CLOSED


def test_one_failing_auction_does_not_stop_the_sweep(
    db: Session, buyer: User, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    broken = active(db, buyer, reference_id="BROKEN")
    fine = active(db, buyer, reference_id="FINE")
    real_advance = lifecycle_service._advance

    def flaky(session: Session, rfq: Rfq, now: datetime) -> tuple[ActivityType, ...]:
        if rfq.id == broken.id:
            raise RuntimeError("boom")
        return real_advance(session, rfq, now)

    monkeypatch.setattr(lifecycle_service, "_advance", flaky)
    results = lifecycle_service.sweep(db, FrozenClock(CLOSE))
    assert [r.rfq_id for r in results] == [fine.id]
    assert stored(db, fine).status == AuctionStatus.CLOSED
    assert stored(db, broken).status == AuctionStatus.ACTIVE  # retried by the next sweep
    assert "Sweeper failed to update RFQ" in caplog.text


def test_mark_closed_refuses_an_auction_still_open(db: Session, buyer: User) -> None:
    rfq = active(db, buyer)
    with pytest.raises(ValueError, match="not due to close"):
        lifecycle_service.mark_closed(db, rfq, CLOSE - MIN)


# ---------------------------------------------------------------------------
# Bids and lifecycle together (A21)
# ---------------------------------------------------------------------------


def test_a21_close_job_waits_for_a_bid_in_progress_and_sees_its_extension(
    db: Session, buyer: User
) -> None:
    rfq = active(db, buyer)
    results: list[lifecycle_service.LifecycleResult] = []

    with SessionLocal() as bidder:
        # A bid at 12:59:59 holds the lock and is about to extend the close by 5 min.
        locked = bidder.scalars(select(Rfq).where(Rfq.id == rfq.id).with_for_update()).one()

        def run_close_job() -> None:
            with SessionLocal() as worker:
                results.append(
                    lifecycle_service.close_auction(
                        worker, rfq.id, FrozenClock(CLOSE), expected_close_at=CLOSE
                    )
                )

        job = threading.Thread(target=run_close_job)
        job.start()
        time.sleep(0.3)
        assert job.is_alive(), "close job should be blocked on the row lock"

        locked.current_close_at = CLOSE + 5 * MIN
        locked.extension_count += 1
        bidder.commit()
        job.join(timeout=5)

    assert [r.outcome for r in results] == [Outcome.STALE]
    assert stored(db, rfq).status == AuctionStatus.ACTIVE


def test_a21_bid_after_the_close_job_ran_is_rejected(
    client: TestClient, clock: FrozenClock, db: Session, buyer: User
) -> None:
    rfq = active(db, buyer)
    supplier = make_user(db)
    db.commit()
    lifecycle_service.close_auction(db, rfq.id, FrozenClock(CLOSE))

    clock.set(CLOSE)
    res = client.post(
        f"/api/rfqs/{rfq.id}/bids",
        json={
            "carrier_name": "Line",
            "freight_charges": "100",
            "origin_charges": "0",
            "destination_charges": "0",
            "transit_time_days": 10,
            "quote_validity_date": "2026-12-31",
        },
        headers={"X-User-Id": str(supplier.id)},
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "AUCTION_CLOSED"


def test_first_bid_opens_a_scheduled_auction_before_the_start_job(
    client: TestClient, clock: FrozenClock, db: Session, buyer: User
) -> None:
    rfq = scheduled(db, buyer)
    supplier = make_user(db, company="Swift Cargo")
    db.commit()

    clock.set(START + MIN)
    res = client.post(
        f"/api/rfqs/{rfq.id}/bids",
        json={
            "carrier_name": "Line",
            "freight_charges": "100",
            "origin_charges": "0",
            "destination_charges": "0",
            "transit_time_days": 10,
            "quote_validity_date": "2026-12-31",
        },
        headers={"X-User-Id": str(supplier.id)},
    )
    assert res.status_code == 201
    assert [e.type for e in log(db, rfq)] == [
        ActivityType.AUCTION_STARTED,
        ActivityType.BID_SUBMITTED,
    ]
    assert lifecycle_service.start_auction(db, rfq.id, clock).outcome == Outcome.UNCHANGED


# ---------------------------------------------------------------------------
# Scheduling jobs
# ---------------------------------------------------------------------------


def create_body(start: datetime) -> dict[str, Any]:
    return {
        "name": "Mumbai to Rotterdam",
        "pickup_date": "2026-12-01",
        "bid_start_at": start.isoformat(),
        "bid_close_at": CLOSE.isoformat(),
        "forced_close_at": FORCED.isoformat(),
        "auction_config": {
            "trigger_window_minutes": 10,
            "extension_duration_minutes": 5,
            "trigger_type": "BID_RECEIVED",
        },
    }


def test_a1_create_queues_start_and_close_jobs(
    client: TestClient, clock: FrozenClock, buyer: User, scheduler: RecordingScheduler
) -> None:
    clock.set(START - timedelta(minutes=30))
    res = client.post("/api/rfqs", json=create_body(START), headers={"X-User-Id": str(buyer.id)})
    rfq_id = uuid.UUID(res.json()["rfq"]["id"])
    assert scheduler.starts == [(rfq_id, START)]
    assert scheduler.closes == [(rfq_id, CLOSE)]


def test_create_already_open_queues_only_the_close(
    client: TestClient, clock: FrozenClock, buyer: User, scheduler: RecordingScheduler
) -> None:
    clock.set(START)
    client.post("/api/rfqs", json=create_body(START), headers={"X-User-Id": str(buyer.id)})
    assert scheduler.starts == []
    assert [close for _, close in scheduler.closes] == [CLOSE]


def test_failed_create_queues_nothing(
    client: TestClient, clock: FrozenClock, buyer: User, scheduler: RecordingScheduler
) -> None:
    clock.set(START)
    body = create_body(START) | {"forced_close_at": CLOSE.isoformat()}
    assert client.post("/api/rfqs", json=body, headers={"X-User-Id": str(buyer.id)}).is_error
    assert (scheduler.starts, scheduler.closes) == ([], [])


# ---------------------------------------------------------------------------
# Celery wrappers (run in-process; real time, since the tasks use the system clock)
# ---------------------------------------------------------------------------


class Sent:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


def test_tasks_close_and_sweep(db: Session, buyer: User) -> None:
    now = utc_now()
    overdue = make_rfq(db, buyer, start=now - 10 * MIN, close=now - MIN, forced=now + MIN,
                       status=AuctionStatus.ACTIVE)  # fmt: skip
    also_overdue = make_rfq(db, buyer, start=now - 10 * MIN, close=now - MIN, forced=now + MIN,
                            status=AuctionStatus.ACTIVE)  # fmt: skip
    db.commit()

    assert tasks.close_auction(str(overdue.id), overdue.current_close_at.isoformat()) == "UPDATED"
    assert tasks.close_auction(str(overdue.id), overdue.current_close_at.isoformat()) == (
        "UNCHANGED"
    )
    assert tasks.sweep_auctions() == {"UPDATED": 1}
    assert stored(db, also_overdue).status == AuctionStatus.CLOSED


def test_tasks_requeue_themselves_when_early(
    db: Session, buyer: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = utc_now()
    rfq = make_rfq(db, buyer, start=now + 10 * MIN, close=now + 20 * MIN, forced=now + 30 * MIN)
    db.commit()
    start_sent, close_sent = Sent(), Sent()
    monkeypatch.setattr(tasks.start_auction, "apply_async", start_sent)
    monkeypatch.setattr(tasks.close_auction, "apply_async", close_sent)

    assert tasks.start_auction(str(rfq.id)) == "NOT_DUE"
    assert start_sent.calls == [{"args": [str(rfq.id)], "eta": rfq.bid_start_at}]

    expected = rfq.current_close_at.isoformat()
    assert tasks.close_auction(str(rfq.id), expected) == "NOT_DUE"
    assert close_sent.calls == [{"args": [str(rfq.id), expected], "eta": rfq.current_close_at}]


def test_celery_scheduler_sends_eta_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    start_sent, close_sent = Sent(), Sent()
    monkeypatch.setattr(tasks.start_auction, "apply_async", start_sent)
    monkeypatch.setattr(tasks.close_auction, "apply_async", close_sent)
    rfq_id = uuid.uuid4()

    scheduler = celery_scheduling.CeleryScheduler()
    scheduler.schedule_start(rfq_id, START)
    scheduler.schedule_close(rfq_id, CLOSE)

    assert start_sent.calls == [{"args": [str(rfq_id)], "eta": START, "retry": False}]
    assert close_sent.calls == [
        {"args": [str(rfq_id), CLOSE.isoformat()], "eta": CLOSE, "retry": False}
    ]


def test_celery_scheduler_survives_a_broker_outage(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def broker_down(**_: Any) -> None:
        raise ConnectionError("redis unreachable")

    monkeypatch.setattr(tasks.close_auction, "apply_async", broker_down)
    celery_scheduling.CeleryScheduler().schedule_close(uuid.uuid4(), CLOSE)  # no exception
    assert "the sweeper will handle it" in caplog.text


def test_beat_runs_the_sweeper() -> None:
    entry = tasks.celery_app.conf.beat_schedule["sweep-auctions"]
    assert entry["task"] == tasks.sweep_auctions.name == "auction.sweep"
    assert entry["schedule"] == 5.0
