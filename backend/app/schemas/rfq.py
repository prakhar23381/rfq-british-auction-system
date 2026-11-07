"""RFQ request and response schemas.

Request: cross-field rules are field validators (not one model validator) so each error
points at the field the user must fix. Fields are declared in dependency order because a
validator can only see fields declared before it. "Start must not be in the past" needs the
clock, so the RFQ service checks it.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from app.domain.enums import AuctionStatus, TriggerType
from app.schemas.common import ApiModel, ServerTimed, Text
from app.schemas.party import PartyOut

REFERENCE_ID_PATTERN = r"^[A-Z0-9-]{3,30}$"


class AuctionConfigIn(BaseModel):
    trigger_window_minutes: int = Field(
        ge=1, le=120, description="X: minutes before the close in which activity is watched"
    )
    extension_duration_minutes: int = Field(
        ge=1, le=120, description="Y: minutes added to the close when triggered"
    )
    trigger_type: TriggerType


class RfqCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: Text = Field(min_length=3, max_length=120)
    reference_id: str | None = Field(
        default=None,
        description="Optional; generated (RFQ-YYYY-NNNN) when omitted",
        pattern=REFERENCE_ID_PATTERN,
    )
    bid_start_at: AwareDatetime
    bid_close_at: AwareDatetime
    forced_close_at: AwareDatetime
    pickup_date: date
    auction_config: AuctionConfigIn

    @field_validator("reference_id", mode="before")
    @classmethod
    def normalise_reference(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip().upper()
            return value or None
        return value

    @field_validator("bid_start_at", "bid_close_at", "forced_close_at")
    @classmethod
    def to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @field_validator("bid_close_at")
    @classmethod
    def close_after_start(cls, value: datetime, info: ValidationInfo) -> datetime:
        start = info.data.get("bid_start_at")
        if start is not None and value <= start:
            raise PydanticCustomError(
                "close_not_after_start", "Bid close time must be later than the bid start time"
            )
        return value

    @field_validator("forced_close_at")
    @classmethod
    def forced_after_close(cls, value: datetime, info: ValidationInfo) -> datetime:
        close = info.data.get("bid_close_at")
        if close is not None and value <= close:
            raise PydanticCustomError(
                "forced_close_not_after_close",
                "Forced bid close time must be later than the bid close time",
            )
        return value

    @field_validator("pickup_date")
    @classmethod
    def pickup_not_before_close(cls, value: date, info: ValidationInfo) -> date:
        close = info.data.get("bid_close_at")
        if close is not None and value < close.date():
            raise PydanticCustomError(
                "pickup_before_close", "Pickup / service date cannot be before the bid close date"
            )
        return value


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class AuctionConfigOut(ApiModel):
    trigger_window_minutes: int
    extension_duration_minutes: int
    trigger_type: TriggerType


class RfqOut(ApiModel):
    id: uuid.UUID
    reference_id: str
    name: str
    status: AuctionStatus = Field(description="Derived from the times at response time")
    pickup_date: date
    bid_start_at: datetime
    bid_close_at: datetime = Field(description="Original close; never changes")
    current_close_at: datetime = Field(description="Close after extensions")
    forced_close_at: datetime
    extension_count: int
    closed_at: datetime | None
    created_at: datetime
    buyer: PartyOut
    version: int = Field(
        description="Newest activity id; orders this snapshot against live events (see /ws)"
    )


class RankedBidOut(ApiModel):
    rank: int
    rank_label: str
    bid_id: uuid.UUID
    supplier: PartyOut
    carrier_name: str
    freight_charges: Decimal
    origin_charges: Decimal
    destination_charges: Decimal
    total_amount: Decimal
    currency: str
    transit_time_days: int
    quote_validity_date: date
    notes: str | None
    submitted_at: datetime
    revision_count: int = Field(description="How many bids this supplier has submitted")


class RfqStats(ApiModel):
    bid_count: int
    supplier_count: int
    extension_count: int
    total_extended_minutes: int = Field(description="Whole minutes added by extensions")
    total_extended_seconds: int = Field(description="Exact time added by extensions")
    first_l1_amount: Decimal | None = Field(description="Total of the first bid placed")
    current_l1_amount: Decimal | None
    savings_pct: Decimal | None = Field(description="Drop from first to current L1, in %")


class RfqDetail(ServerTimed):
    rfq: RfqOut
    auction_config: AuctionConfigOut
    ranking: list[RankedBidOut]
    stats: RfqStats


class LowestBidOut(ApiModel):
    amount: Decimal
    currency: str
    supplier_name: str


class RfqListItem(ApiModel):
    id: uuid.UUID
    reference_id: str
    name: str
    status: AuctionStatus
    lowest_bid: LowestBidOut | None
    bid_start_at: datetime
    bid_close_at: datetime
    current_close_at: datetime
    forced_close_at: datetime
    extension_count: int
    bid_count: int
    supplier_count: int
    trigger_window_minutes: int | None = Field(
        description="Trigger window X, so clients can highlight the last X minutes before close"
    )
    version: int = Field(
        description="Newest activity id; orders this row against live events (see /ws)"
    )


class StatusCounts(ApiModel):
    """Auctions per status for the current search, ignoring the status filter (filter tabs)."""

    SCHEDULED: int = 0
    ACTIVE: int = 0
    CLOSED: int = 0
    FORCE_CLOSED: int = 0


class RfqListResponse(ServerTimed):
    items: list[RfqListItem]
    page: int
    page_size: int
    total: int
    status_counts: StatusCounts
