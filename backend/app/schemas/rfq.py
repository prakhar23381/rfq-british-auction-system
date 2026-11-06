"""Request schemas for creating an RFQ. Response schemas are added with the RFQ endpoints.

Cross-field rules are field validators (not one model validator) so each error points at
the field the user must fix. Fields are declared in dependency order because a validator
can only see fields declared before it. "Start must not be in the past" needs the clock,
so the RFQ service checks it.
"""

from datetime import UTC, date, datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from app.domain.enums import TriggerType

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

    name: str = Field(min_length=3, max_length=120)
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
