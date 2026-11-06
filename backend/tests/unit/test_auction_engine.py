"""Unit tests for the pure auction rules. Case ids (E1, X2, S3, ...) match the test matrix
in the project plan."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.auction_engine import (
    ExtensionDecision,
    RankableBid,
    RankChange,
    RankedBid,
    accepts_bids_at,
    compute_extension,
    compute_ranking,
    decide_extension,
    derive_status,
    detect_trigger,
    is_in_trigger_window,
    is_valid_revision,
    rank_label,
    with_new_bid,
)
from app.domain.enums import AuctionStatus, TriggerType

A, B, C, D = (uuid.UUID(int=i) for i in range(1, 5))
NAMES = {A: "A", B: "B", C: "C", D: "D"}


def at(hour: int, minute: int, second: int = 0, micro: int = 0) -> datetime:
    return datetime(2026, 11, 10, hour, minute, second, micro, tzinfo=UTC)


START = at(17, 0)
CLOSE = at(18, 0)
FORCED = at(18, 30)


def bid(supplier: uuid.UUID, amount: str | int, when: datetime = START) -> RankableBid:
    return RankableBid(uuid.uuid4(), supplier, Decimal(amount), when)


def order(ranking: list[RankedBid]) -> list[str]:
    return [NAMES[r.supplier_id] for r in ranking]


def place(latest: list[RankableBid], new: RankableBid) -> tuple[list[RankedBid], list[RankedBid]]:
    """(ranking before, ranking after) for a new bid on top of `latest`."""
    return compute_ranking(latest), compute_ranking(with_new_bid(latest, new))


# A = 100 (L1), B = 110 (L2), C = 120 (L3)
BASE = [bid(A, 100, at(17, 0)), bid(B, 110, at(17, 1)), bid(C, 120, at(17, 2))]


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------


def test_e1_ranking_is_lowest_total_first() -> None:
    ranking = compute_ranking([bid(C, 120), bid(A, 100), bid(B, 110)])
    assert order(ranking) == ["A", "B", "C"]
    assert [r.label for r in ranking] == ["L1", "L2", "L3"]


def test_e2_tie_goes_to_earlier_bid() -> None:
    ranking = compute_ranking([bid(A, 100, at(17, 5)), bid(B, 100, at(17, 4))])
    assert order(ranking) == ["B", "A"]


def test_identical_amount_and_time_is_still_deterministic() -> None:
    first, second = bid(A, 100, at(17, 0)), bid(B, 100, at(17, 0))
    expected = sorted([first, second], key=lambda b: b.bid_id)
    assert [r.bid for r in compute_ranking([second, first])] == expected
    assert [r.bid for r in compute_ranking([first, second])] == expected


def test_ranking_requires_one_bid_per_supplier() -> None:
    with pytest.raises(ValueError):
        compute_ranking([bid(A, 100), bid(A, 90)])


def test_empty_ranking() -> None:
    assert compute_ranking([]) == []


def test_new_bid_replaces_suppliers_previous_bid() -> None:
    updated = with_new_bid(BASE, bid(B, 95))
    assert len(updated) == 3
    assert order(compute_ranking(updated)) == ["B", "A", "C"]


def test_rank_label() -> None:
    assert rank_label(1) == "L1"
    assert rank_label(12) == "L12"


@pytest.mark.parametrize(
    ("previous", "new", "valid"),
    [(None, "100", True), ("100", "99.99", True), ("100", "100", False), ("100", "101", False)],
)
def test_revision_must_be_strictly_lower(previous: str | None, new: str, valid: bool) -> None:
    prev = Decimal(previous) if previous is not None else None
    assert is_valid_revision(prev, Decimal(new)) is valid


# ---------------------------------------------------------------------------
# Trigger window
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("case", "when", "expected"),
    [
        ("E3 window start is inclusive", at(17, 50), True),
        ("E4 just before the window", at(17, 49, 59, 999999), False),
        ("inside the window", at(17, 55), True),
        ("last instant before close", at(17, 59, 59, 999999), True),
        ("E5 close itself is excluded", at(18, 0), False),
        ("after close", at(18, 1), False),
    ],
)
def test_trigger_window_boundaries(case: str, when: datetime, expected: bool) -> None:
    assert is_in_trigger_window(when, CLOSE, x_minutes=10) is expected, case


def test_window_follows_the_current_close() -> None:
    extended_close = at(18, 5)
    assert not is_in_trigger_window(at(17, 54), extended_close, 10)
    assert is_in_trigger_window(at(17, 55), extended_close, 10)


# ---------------------------------------------------------------------------
# Trigger types
# ---------------------------------------------------------------------------


@dataclass
class TriggerCase:
    case: str
    trigger: TriggerType
    new_bid: RankableBid
    expected: bool
    latest: list[RankableBid] = field(default_factory=lambda: BASE)


TRIGGER_CASES = [
    TriggerCase("E6 any bid triggers", TriggerType.BID_RECEIVED, bid(C, 115), True),
    TriggerCase("first bid triggers", TriggerType.BID_RECEIVED, bid(A, 100), True, latest=[]),
    TriggerCase("E7 B undercuts A", TriggerType.ANY_RANK_CHANGE, bid(B, 95), True),
    TriggerCase("E8 L2 lowers, stays L2", TriggerType.ANY_RANK_CHANGE, bid(B, 105), False),
    TriggerCase("E9 newcomer enters last", TriggerType.ANY_RANK_CHANGE, bid(D, 130), False),
    TriggerCase("E10 newcomer enters as L1", TriggerType.ANY_RANK_CHANGE, bid(D, 90), True),
    TriggerCase("E11 L3 overtakes L2", TriggerType.ANY_RANK_CHANGE, bid(C, 105), True),
    TriggerCase(
        "E16 first bid is not a rank change",
        TriggerType.ANY_RANK_CHANGE,
        bid(A, 100),
        False,
        latest=[],
    ),
    TriggerCase("E12 L3 to L2 is not an L1 change", TriggerType.L1_CHANGE, bid(C, 105), False),
    TriggerCase("E13 C becomes new L1", TriggerType.L1_CHANGE, bid(C, 90), True),
    TriggerCase("E14 L1 lowers own price", TriggerType.L1_CHANGE, bid(A, 95), False),
    TriggerCase("E15 first bid is an L1 change", TriggerType.L1_CHANGE, bid(A, 100), True, []),
    TriggerCase("tie does not take L1", TriggerType.L1_CHANGE, bid(B, 100, at(17, 30)), False),
]


@pytest.mark.parametrize("tc", TRIGGER_CASES, ids=[tc.case for tc in TRIGGER_CASES])
def test_trigger_types(tc: TriggerCase) -> None:
    before, after = place(tc.latest, tc.new_bid)
    result = detect_trigger(tc.trigger, before, after)
    assert result.triggered is tc.expected
    assert result.trigger_type == tc.trigger


def test_trigger_result_reports_l1_and_rank_changes() -> None:
    before, after = place(BASE, bid(C, 90))
    result = detect_trigger(TriggerType.L1_CHANGE, before, after)
    assert (result.previous_l1, result.new_l1) == (A, C)
    assert result.l1_changed
    assert result.rank_changes == [
        RankChange(A, 1, 2),
        RankChange(B, 2, 3),
        RankChange(C, 3, 1),
    ]


def test_rank_changes_ignore_newcomer_at_the_bottom() -> None:
    before, after = place(BASE, bid(D, 130))
    assert detect_trigger(TriggerType.BID_RECEIVED, before, after).rank_changes == []


def test_first_bid_has_no_previous_l1() -> None:
    before, after = place([], bid(A, 100))
    result = detect_trigger(TriggerType.L1_CHANGE, before, after)
    assert (result.previous_l1, result.new_l1) == (None, A)


# ---------------------------------------------------------------------------
# Extension
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("case", "current", "forced", "y", "applied", "new_close", "capped"),
    [
        ("X1 normal extension", at(18, 0), at(18, 30), 5, True, at(18, 5), False),
        ("X2 clipped by forced close", at(18, 28), at(18, 30), 5, True, at(18, 30), True),
        ("X3 lands exactly on forced close", at(18, 15), at(18, 20), 5, True, at(18, 20), False),
        ("X4 already at forced close", at(18, 30), at(18, 30), 5, False, at(18, 30), True),
    ],
)
def test_compute_extension(
    case: str,
    current: datetime,
    forced: datetime,
    y: int,
    applied: bool,
    new_close: datetime,
    capped: bool,
) -> None:
    result = compute_extension(current, forced, y)
    assert (result.applied, result.new_close_at, result.capped) == (applied, new_close, capped), (
        case
    )
    assert result.previous_close_at == current


@given(
    current_offset=st.integers(min_value=0, max_value=24 * 60),
    gap=st.integers(min_value=0, max_value=24 * 60),
    y=st.integers(min_value=1, max_value=120),
)
def test_x5_extension_never_passes_forced_close(current_offset: int, gap: int, y: int) -> None:
    current = at(0, 0) + timedelta(minutes=current_offset)
    forced = current + timedelta(minutes=gap)
    result = compute_extension(current, forced, y)
    assert result.new_close_at <= forced
    assert result.new_close_at >= current
    assert result.applied == (result.new_close_at > current)


# ---------------------------------------------------------------------------
# Combined decision
# ---------------------------------------------------------------------------


def _decide(
    when: datetime, new_bid: RankableBid, current: datetime = CLOSE, forced: datetime = FORCED
) -> ExtensionDecision:
    before, after = place(BASE, new_bid)
    return decide_extension(
        bid_at=when,
        current_close_at=current,
        forced_close_at=forced,
        trigger_window_minutes=10,
        extension_duration_minutes=5,
        trigger_type=TriggerType.L1_CHANGE,
        before=before,
        after=after,
    )


def test_decision_outside_window_never_extends() -> None:
    decision = _decide(at(17, 40), bid(C, 90))  # would be an L1 change
    assert (decision.in_window, decision.trigger, decision.extension) == (False, None, None)
    assert not decision.extended


def test_decision_in_window_without_trigger() -> None:
    decision = _decide(at(17, 55), bid(A, 95))  # L1 lowers own price
    assert decision.in_window
    assert decision.trigger is not None and not decision.trigger.triggered
    assert decision.extension is None and not decision.extended


def test_decision_in_window_with_trigger_extends() -> None:
    decision = _decide(at(17, 55), bid(C, 90))
    assert decision.extended and not decision.skipped_at_cap
    assert decision.extension is not None
    assert decision.extension.new_close_at == at(18, 5)


def test_decision_at_forced_close_is_skipped() -> None:
    decision = _decide(at(18, 25), bid(C, 90), current=at(18, 30), forced=at(18, 30))
    assert decision.skipped_at_cap and not decision.extended


# ---------------------------------------------------------------------------
# Status and acceptance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("case", "now", "current", "expected"),
    [
        ("S1 before start", at(16, 59), at(18, 0), AuctionStatus.SCHEDULED),
        ("start instant is active", at(17, 0), at(18, 0), AuctionStatus.ACTIVE),
        ("S2 running", at(17, 30), at(18, 0), AuctionStatus.ACTIVE),
        ("S3 ended before forced close", at(18, 0), at(18, 0), AuctionStatus.CLOSED),
        ("still closed later on", at(19, 0), at(18, 10), AuctionStatus.CLOSED),
        ("S4 ended at forced close", at(18, 30), at(18, 30), AuctionStatus.FORCE_CLOSED),
    ],
)
def test_derive_status(
    case: str, now: datetime, current: datetime, expected: AuctionStatus
) -> None:
    status = derive_status(
        bid_start_at=at(17, 0), current_close_at=current, forced_close_at=at(18, 30), now=now
    )
    assert status == expected, case


@pytest.mark.parametrize(
    ("when", "accepted"),
    [(at(16, 59), False), (at(17, 0), True), (at(17, 59, 59), True), (at(18, 0), False)],
)
def test_bid_acceptance_window(when: datetime, accepted: bool) -> None:
    assert accepts_bids_at(bid_start_at=at(17, 0), current_close_at=CLOSE, at=when) is accepted


# ---------------------------------------------------------------------------
# Worked example from the HLD (section 3.6), end to end
# ---------------------------------------------------------------------------


@dataclass
class AuctionSim:
    """Minimal driver that applies the engine the way the bid service will."""

    current_close: datetime
    forced_close: datetime
    trigger: TriggerType
    x: int = 10
    y: int = 5
    start: datetime = START
    latest: list[RankableBid] = field(default_factory=list)

    def place(self, supplier: uuid.UUID, amount: int, when: datetime) -> ExtensionDecision | None:
        if not accepts_bids_at(
            bid_start_at=self.start, current_close_at=self.current_close, at=when
        ):
            return None
        new = bid(supplier, amount, when)
        before, after = place(self.latest, new)
        decision = decide_extension(
            bid_at=when,
            current_close_at=self.current_close,
            forced_close_at=self.forced_close,
            trigger_window_minutes=self.x,
            extension_duration_minutes=self.y,
            trigger_type=self.trigger,
            before=before,
            after=after,
        )
        self.latest = with_new_bid(self.latest, new)
        if decision.extended:
            assert decision.extension is not None
            self.current_close = decision.extension.new_close_at
        return decision

    def status(self, now: datetime) -> AuctionStatus:
        return derive_status(
            bid_start_at=self.start,
            current_close_at=self.current_close,
            forced_close_at=self.forced_close,
            now=now,
        )


def test_worked_example_l1_change_until_force_close() -> None:
    sim = AuctionSim(
        current_close=at(18, 0), forced_close=at(18, 20), trigger=TriggerType.L1_CHANGE
    )

    # (time, supplier, amount, extended?, skipped at cap?, close afterwards)
    steps = [
        (at(17, 40), A, 100, False, False, at(18, 0)),  # outside window
        (at(17, 52), B, 95, True, False, at(18, 5)),  # L1 A -> B
        (at(17, 58), B, 90, False, False, at(18, 5)),  # L1 unchanged
        (at(18, 1), A, 85, True, False, at(18, 10)),  # L1 B -> A
        (at(18, 8), B, 80, True, False, at(18, 15)),  # L1 A -> B
        (at(18, 12), A, 75, True, False, at(18, 20)),  # reaches forced close exactly
        (at(18, 16), B, 70, False, True, at(18, 20)),  # trigger met, already at cap
    ]
    for when, supplier, amount, extended, skipped, close_after in steps:
        decision = sim.place(supplier, amount, when)
        assert decision is not None, when
        assert decision.extended is extended, when
        assert decision.skipped_at_cap is skipped, when
        assert sim.current_close == close_after, when

    assert sim.status(at(18, 19, 59)) == AuctionStatus.ACTIVE
    assert sim.status(at(18, 20)) == AuctionStatus.FORCE_CLOSED
    assert order(compute_ranking(sim.latest)) == ["B", "A"]  # winner B at 70
    assert sim.place(C, 60, at(18, 20, 1)) is None  # bidding has stopped


def test_quiet_finish_closes_normally() -> None:
    sim = AuctionSim(
        current_close=at(18, 0), forced_close=at(18, 20), trigger=TriggerType.BID_RECEIVED
    )
    decision = sim.place(A, 100, at(17, 55))
    assert decision is not None and decision.extended
    assert sim.current_close == at(18, 5)
    assert sim.status(at(18, 5)) == AuctionStatus.CLOSED
