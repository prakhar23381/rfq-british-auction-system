"""Request schema for submitting a bid (quote). Rules that need the RFQ or the supplier's
previous bid (quote validity vs pickup date, "must be lower") are checked by the bid service."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from app.schemas.common import ApiModel, ServerTimed
from app.schemas.party import PartyOut

Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]


class BidCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    carrier_name: str = Field(min_length=2, max_length=100)
    freight_charges: Money
    origin_charges: Money
    destination_charges: Money
    transit_time_days: int = Field(ge=1, le=365, description="Transit time in days")
    quote_validity_date: date = Field(description="Quote is valid until this date")
    notes: str | None = Field(default=None, max_length=500)

    @property
    def total_amount(self) -> Decimal:
        return self.freight_charges + self.origin_charges + self.destination_charges

    @model_validator(mode="after")
    def total_must_be_positive(self) -> "BidCreate":
        if self.total_amount <= 0:
            raise PydanticCustomError("zero_total", "Total charges must be greater than zero")
        return self


class BidOut(ApiModel):
    id: uuid.UUID
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
    is_latest: bool = Field(description="False once the supplier submitted a lower bid")
    rank_at_submission: int | None
    submitted_at: datetime


class BidListResponse(ServerTimed):
    items: list[BidOut]
