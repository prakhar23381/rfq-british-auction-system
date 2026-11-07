"""Model-based test: random bid sequences against the real bid service and database.

Hypothesis drives an auction with random suppliers, amounts and time steps. A small reference
model, written here independently of the auction engine, predicts every outcome straight from
the assignment's rules. After each step the database must agree with it: accepted or rejected
(and why), the current close, the extension count, the ranking, and the activity log.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import HealthCheck, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, rule
from sqlalchemy import func, select

from app.core.clock import FrozenClock
from app.core.errors import AppError, ErrorCode
from app.db import SessionLocal
from app.domain.enums import ActivityType, AuctionStatus, TriggerType, UserRole
from app.models import ActivityLog, Bid, Rfq
from app.realtime.events import NullPublisher
from app.schemas.bid import BidCreate
from app.services import bid_service, query_service
from tests.factories import T0, make_rfq, make_user
from tests.fakes import RecordingScheduler

SUPPLIERS = 4


@dataclass
class Model:
    """The rules, stated as plainly as possible."""

    start: datetime
    close: datetime
    forced: datetime
    x: timedelta
    y: timedelta
    trigger: TriggerType
    latest: dict[int, tuple[int, int]] = field(default_factory=dict)  # supplier → (total, seq)
    seq: int = 0
    extensions: int = 0
    skipped: int = 0
    accepted: int = 0

    def ranking(self, latest: dict[int, tuple[int, int]] | None = None) -> list[int]:
        bids = self.latest if latest is None else latest
        return sorted(bids, key=lambda s: bids[s])  # lowest total, then earliest bid

    def bid(self, supplier: int, total: int, now: datetime) -> ErrorCode | None:
        if now < self.start:
            return ErrorCode.AUCTION_NOT_STARTED
        if now >= self.close:
            return ErrorCode.AUCTION_CLOSED
        if supplier in self.latest and total >= self.latest[supplier][0]:
            return ErrorCode.BID_NOT_LOWER

        before = self.ranking()
        self.seq += 1
        self.latest[supplier] = (total, self.seq)
        after = self.ranking()
        self.accepted += 1

        in_window = self.close - self.x <= now < self.close
        if self.trigger == TriggerType.BID_RECEIVED:
            triggered = True
        elif self.trigger == TriggerType.L1_CHANGE:
            triggered = (before[:1] or [None])[0] != after[0]
        else:  # ANY_RANK_CHANGE: a supplier who was already ranked moved
            triggered = any(after.index(s) != i for i, s in enumerate(before))

        if in_window and triggered:
            if self.close < self.forced:
                self.close = min(self.close + self.y, self.forced)
                self.extensions += 1
            else:
                self.skipped += 1
        return None


class AuctionMachine(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.db = SessionLocal()
        self.scheduler = RecordingScheduler()
        self.publisher = NullPublisher()

    @initialize(
        x=st.integers(1, 15),
        y=st.integers(1, 10),
        trigger=st.sampled_from(list(TriggerType)),
        room=st.integers(1, 25),
    )
    def create_auction(self, x: int, y: int, trigger: TriggerType, room: int) -> None:
        buyer = make_user(self.db, UserRole.BUYER)
        self.suppliers = [make_user(self.db) for _ in range(SUPPLIERS)]
        close = T0 + timedelta(minutes=20)
        forced = close + timedelta(minutes=room)
        self.rfq = make_rfq(self.db, buyer, start=T0, close=close, forced=forced, x=x, y=y,
                            trigger=trigger, status=AuctionStatus.ACTIVE)  # fmt: skip
        self.db.commit()
        self.model = Model(start=T0, close=close, forced=forced, x=timedelta(minutes=x),
                           y=timedelta(minutes=y), trigger=trigger)  # fmt: skip
        # Start a little before the opening so some bids are too early.
        self.clock = FrozenClock(T0 - timedelta(seconds=90))

    @rule(
        supplier=st.integers(0, SUPPLIERS - 1),
        # A narrow price range makes ties and "not lower" rejections common.
        total=st.integers(50, 70),
        # At least a second between bids keeps submission order (the tie-break) unambiguous.
        wait=st.one_of(st.integers(1, 30), st.integers(30, 600)),
    )
    def place_bid(self, supplier: int, total: int, wait: int) -> None:
        self.clock.advance(seconds=wait)
        self._bid(supplier, total)

    @rule(
        supplier=st.integers(0, SUPPLIERS - 1),
        total=st.integers(50, 70),
        edge=st.sampled_from(["window_start", "before_window", "before_close", "at_close"]),
    )
    def bid_on_an_edge(self, supplier: int, total: int, edge: str) -> None:
        """Bid exactly on the boundaries, which random waits almost never hit."""
        target = {
            "window_start": self.model.close - self.model.x,  # first instant inside the window
            "before_window": self.model.close - self.model.x - timedelta(seconds=1),
            "before_close": self.model.close - timedelta(seconds=1),
            "at_close": self.model.close,  # too late
        }[edge]
        if target <= self.clock.now():
            return  # time only moves forward
        self.clock.set(target)
        self._bid(supplier, total)

    def _bid(self, supplier: int, total: int) -> None:
        expected = self.model.bid(supplier, total, self.clock.now())
        data = BidCreate(
            carrier_name="Model Line",
            freight_charges=Decimal(total),
            origin_charges=Decimal(0),
            destination_charges=Decimal(0),
            transit_time_days=10,
            quote_validity_date=self.rfq.pickup_date,
        )
        try:
            bid_service.submit_bid(self.db, self.rfq.id, self.suppliers[supplier], data, self.clock,
                                   scheduler=self.scheduler, publisher=self.publisher)  # fmt: skip
            outcome = None
        except AppError as error:
            self.db.rollback()
            outcome = error.code
        assert outcome == expected, f"at {self.clock.now()}: got {outcome}, model says {expected}"

    @invariant()
    def database_matches_the_model(self) -> None:
        if not hasattr(self, "model"):
            return
        self.db.expire_all()
        rfq = self.db.get_one(Rfq, self.rfq.id)
        assert rfq.current_close_at == self.model.close
        assert rfq.extension_count == self.model.extensions
        assert rfq.current_close_at <= rfq.forced_close_at

        # Ranking straight from SQL, independent of the engine: lowest total, then earliest.
        ids = {s.id: i for i, s in enumerate(self.suppliers)}
        order = self.db.scalars(
            select(Bid.supplier_id)
            .where(Bid.rfq_id == rfq.id, Bid.is_latest.is_(True))
            .order_by(Bid.total_amount, Bid.submitted_at)
        ).all()
        assert [ids[s] for s in order] == self.model.ranking()
        # ...and the engine-based ranking the API shows agrees.
        shown = [
            ids[ranked.supplier_id] for ranked, _, _ in query_service.ranked_latest(self.db, rfq.id)
        ]
        assert shown == self.model.ranking()

        total_bids = self.db.scalar(select(func.count()).where(Bid.rfq_id == rfq.id))
        assert total_bids == self.model.accepted

        def logged(kind: ActivityType) -> int:
            return (
                self.db.scalar(
                    select(func.count()).where(
                        ActivityLog.rfq_id == rfq.id, ActivityLog.type == kind
                    )
                )
                or 0
            )

        assert logged(ActivityType.BID_SUBMITTED) == self.model.accepted
        assert logged(ActivityType.AUCTION_EXTENDED) == self.model.extensions
        assert logged(ActivityType.EXTENSION_SKIPPED) == self.model.skipped

        expected_status = (
            AuctionStatus.SCHEDULED if self.clock.now() < self.model.start
            else AuctionStatus.ACTIVE if self.clock.now() < self.model.close
            else AuctionStatus.FORCE_CLOSED if self.model.close >= self.model.forced
            else AuctionStatus.CLOSED
        )  # fmt: skip
        assert query_service.status_of(rfq, self.clock.now()) == expected_status

    def teardown(self) -> None:
        self.db.rollback()
        self.db.close()


AuctionMachine.TestCase.settings = settings(
    max_examples=60,
    stateful_step_count=25,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)


@pytest.mark.timeout(300)
class TestAuctionModel(AuctionMachine.TestCase):  # type: ignore[misc,valid-type]
    """Random bid sequences: the database always agrees with the reference model."""


def test_model_matches_the_assignment_example() -> None:
    """The model itself, on the worked example (close 18:00, X=10, Y=5, forced 18:20)."""
    at = lambda h, m: datetime(2026, 11, 7, h, m, tzinfo=T0.tzinfo)  # noqa: E731
    model = Model(start=at(17, 0), close=at(18, 0), forced=at(18, 20), x=timedelta(minutes=10),
                  y=timedelta(minutes=5), trigger=TriggerType.L1_CHANGE)  # fmt: skip
    a, b, c = 0, 1, 2
    assert model.bid(a, 100, at(17, 30)) is None  # first bid: L1 changes, but outside window
    assert model.close == at(18, 0)
    assert model.bid(b, 90, at(17, 55)) is None  # B becomes L1 inside the window
    assert model.close == at(18, 5)
    assert model.bid(a, 95, at(18, 1)) is None  # A lowers but stays L2: no extension
    assert model.close == at(18, 5)
    assert model.bid(c, 80, at(18, 4)) is None
    assert model.bid(a, 70, at(18, 9)) is None
    assert model.bid(b, 60, at(18, 14)) is None
    assert model.close == at(18, 20)  # 18:20 reached: capped at the forced close
    assert model.bid(c, 50, at(18, 19)) is None
    assert (model.extensions, model.skipped) == (4, 1)
    assert model.bid(a, 40, at(18, 20)) == ErrorCode.AUCTION_CLOSED
    assert model.bid(a, 40, at(16, 0)) == ErrorCode.AUCTION_NOT_STARTED
    assert model.bid(c, 50, at(18, 19)) == ErrorCode.BID_NOT_LOWER
