"""British auction rules as pure functions.

Nothing here touches the database or reads the clock: callers pass in the current time and
the bids. That keeps every rule deterministic and unit-testable, and lets the bid service
apply them inside a locked transaction.

Rules (see docs/HLD.md, section 3):
- Ranking: each supplier's latest bid, lowest total first; ties go to the earlier bid.
- Trigger window: [current_close - X, current_close), relative to the *current* close.
- Triggers: BID_RECEIVED (any bid), ANY_RANK_CHANGE (an already-ranked supplier's rank
  changed), L1_CHANGE (the lowest bidder changed, including the first bid).
- Extension: new_close = min(current_close + Y, forced_close); never past forced close.
- Status: SCHEDULED before start, ACTIVE until current close, then CLOSED, or FORCE_CLOSED
  when the close had been pushed to the forced close.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import assert_never

from app.domain.enums import AuctionStatus, TriggerType

# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RankableBid:
    """The fields of a supplier's latest bid that ranking needs."""

    bid_id: uuid.UUID
    supplier_id: uuid.UUID
    total_amount: Decimal
    submitted_at: datetime


@dataclass(frozen=True, slots=True)
class RankedBid:
    rank: int
    bid: RankableBid

    @property
    def supplier_id(self) -> uuid.UUID:
        return self.bid.supplier_id

    @property
    def label(self) -> str:
        return rank_label(self.rank)


def rank_label(rank: int) -> str:
    return f"L{rank}"


def compute_ranking(latest_bids: Sequence[RankableBid]) -> list[RankedBid]:
    """Rank suppliers by their latest bid: lowest total first, earlier bid wins a tie.
    The bid id is a final tie-breaker so the order is always deterministic."""
    suppliers = [b.supplier_id for b in latest_bids]
    if len(suppliers) != len(set(suppliers)):
        raise ValueError("compute_ranking expects at most one (latest) bid per supplier")
    ordered = sorted(latest_bids, key=lambda b: (b.total_amount, b.submitted_at, b.bid_id))
    return [RankedBid(rank=i, bid=b) for i, b in enumerate(ordered, start=1)]


def with_new_bid(latest_bids: Sequence[RankableBid], new_bid: RankableBid) -> list[RankableBid]:
    """The supplier's new bid replaces their previous latest bid (if any)."""
    return [b for b in latest_bids if b.supplier_id != new_bid.supplier_id] + [new_bid]


def is_valid_revision(previous_total: Decimal | None, new_total: Decimal) -> bool:
    """A supplier may only lower their own price: each new bid must be strictly lower."""
    return previous_total is None or new_total < previous_total


# ---------------------------------------------------------------------------
# Trigger detection
# ---------------------------------------------------------------------------


def is_in_trigger_window(at: datetime, current_close_at: datetime, x_minutes: int) -> bool:
    """True if `at` falls in [current_close - X, current_close)."""
    return current_close_at - timedelta(minutes=x_minutes) <= at < current_close_at


@dataclass(frozen=True, slots=True)
class RankChange:
    supplier_id: uuid.UUID
    from_rank: int
    to_rank: int


@dataclass(frozen=True, slots=True)
class TriggerResult:
    triggered: bool
    trigger_type: TriggerType
    previous_l1: uuid.UUID | None
    new_l1: uuid.UUID | None
    # Suppliers ranked before the bid whose rank changed (the bidder included, if they moved).
    rank_changes: list[RankChange] = field(default_factory=list)

    @property
    def l1_changed(self) -> bool:
        return self.previous_l1 != self.new_l1


def rank_changes(before: Sequence[RankedBid], after: Sequence[RankedBid]) -> list[RankChange]:
    """Rank changes for suppliers that were already ranked. A newcomer is not a change in
    itself; it only counts if it pushes an existing supplier down."""
    after_ranks = {r.supplier_id: r.rank for r in after}
    changes = []
    for r in before:
        new_rank = after_ranks.get(r.supplier_id)
        if new_rank is not None and new_rank != r.rank:
            changes.append(RankChange(r.supplier_id, r.rank, new_rank))
    return changes


def detect_trigger(
    trigger_type: TriggerType, before: Sequence[RankedBid], after: Sequence[RankedBid]
) -> TriggerResult:
    """Did the bid that turned `before` into `after` satisfy the auction's trigger?
    Assumes the bid was inside the trigger window (checked separately)."""
    previous_l1 = before[0].supplier_id if before else None
    new_l1 = after[0].supplier_id if after else None
    changes = rank_changes(before, after)

    match trigger_type:
        case TriggerType.BID_RECEIVED:
            triggered = True
        case TriggerType.ANY_RANK_CHANGE:
            triggered = bool(changes)
        case TriggerType.L1_CHANGE:
            triggered = previous_l1 != new_l1
        case _ as unreachable:  # pragma: no cover
            assert_never(unreachable)

    return TriggerResult(
        triggered=triggered,
        trigger_type=trigger_type,
        previous_l1=previous_l1,
        new_l1=new_l1,
        rank_changes=changes,
    )


# ---------------------------------------------------------------------------
# Extension and status
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExtensionResult:
    applied: bool
    previous_close_at: datetime
    new_close_at: datetime
    # True when the forced close cut the extension short, or prevented it entirely.
    capped: bool


def compute_extension(
    current_close_at: datetime, forced_close_at: datetime, y_minutes: int
) -> ExtensionResult:
    """Extend the current close by Y minutes, never beyond the forced close."""
    if current_close_at >= forced_close_at:
        return ExtensionResult(False, current_close_at, current_close_at, capped=True)
    candidate = current_close_at + timedelta(minutes=y_minutes)
    new_close = min(candidate, forced_close_at)
    return ExtensionResult(True, current_close_at, new_close, capped=candidate > forced_close_at)


@dataclass(frozen=True, slots=True)
class ExtensionDecision:
    """Everything the bid service needs to know about a bid's effect on the close time."""

    in_window: bool
    trigger: TriggerResult | None  # None when the bid was outside the window
    extension: ExtensionResult | None  # None when not triggered

    @property
    def extended(self) -> bool:
        return self.extension is not None and self.extension.applied

    @property
    def skipped_at_cap(self) -> bool:
        """Trigger met, but the close was already at the forced close."""
        return self.extension is not None and not self.extension.applied


def decide_extension(
    *,
    bid_at: datetime,
    current_close_at: datetime,
    forced_close_at: datetime,
    trigger_window_minutes: int,
    extension_duration_minutes: int,
    trigger_type: TriggerType,
    before: Sequence[RankedBid],
    after: Sequence[RankedBid],
) -> ExtensionDecision:
    """Apply window -> trigger -> extension for one accepted bid."""
    if not is_in_trigger_window(bid_at, current_close_at, trigger_window_minutes):
        return ExtensionDecision(in_window=False, trigger=None, extension=None)
    trigger = detect_trigger(trigger_type, before, after)
    if not trigger.triggered:
        return ExtensionDecision(in_window=True, trigger=trigger, extension=None)
    extension = compute_extension(current_close_at, forced_close_at, extension_duration_minutes)
    return ExtensionDecision(in_window=True, trigger=trigger, extension=extension)


def derive_status(
    *,
    bid_start_at: datetime,
    current_close_at: datetime,
    forced_close_at: datetime,
    now: datetime,
) -> AuctionStatus:
    """Status from the times alone (used on every read, so it is right even if a lifecycle
    task is late)."""
    if now < bid_start_at:
        return AuctionStatus.SCHEDULED
    if now < current_close_at:
        return AuctionStatus.ACTIVE
    if current_close_at >= forced_close_at:
        return AuctionStatus.FORCE_CLOSED
    return AuctionStatus.CLOSED


def accepts_bids_at(*, bid_start_at: datetime, current_close_at: datetime, at: datetime) -> bool:
    """Bids are accepted while bid_start_at <= at < current_close_at."""
    return bid_start_at <= at < current_close_at
