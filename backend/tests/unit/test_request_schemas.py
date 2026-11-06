"""Validation of the RFQ and bid request bodies."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.enums import TriggerType
from app.schemas.bid import BidCreate
from app.schemas.rfq import RfqCreate


def rfq_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "Mumbai to Rotterdam",
        "reference_id": "RFQ-2026-0001",
        "pickup_date": "2026-11-20",
        "bid_start_at": "2026-11-10T12:00:00Z",
        "bid_close_at": "2026-11-10T13:00:00Z",
        "forced_close_at": "2026-11-10T13:30:00Z",
        "auction_config": {
            "trigger_window_minutes": 10,
            "extension_duration_minutes": 5,
            "trigger_type": "L1_CHANGE",
        },
    }
    payload.update(overrides)
    return payload


def errors_for(model: type[RfqCreate] | type[BidCreate], payload: dict[str, Any]) -> dict[str, str]:
    """{field: error type} for a payload expected to fail."""
    with pytest.raises(ValidationError) as exc_info:
        model.model_validate(payload)
    return {".".join(str(p) for p in e["loc"]): e["type"] for e in exc_info.value.errors()}


# ---------------------------------------------------------------------------
# RFQ
# ---------------------------------------------------------------------------


def test_valid_rfq_is_normalised_to_utc() -> None:
    rfq = RfqCreate.model_validate(
        rfq_payload(
            bid_start_at="2026-11-10T17:30:00+05:30",
            reference_id="  rfq-2026-0001 ",
            name="  Mumbai to Rotterdam  ",
        )
    )
    assert rfq.bid_start_at == datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
    assert rfq.bid_start_at.tzinfo == UTC
    assert rfq.reference_id == "RFQ-2026-0001"
    assert rfq.name == "Mumbai to Rotterdam"
    assert rfq.auction_config.trigger_type == TriggerType.L1_CHANGE


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_reference_id_is_optional(blank: str | None) -> None:
    assert RfqCreate.model_validate(rfq_payload(reference_id=blank)).reference_id is None


def test_reference_id_format() -> None:
    assert errors_for(RfqCreate, rfq_payload(reference_id="RFQ 1!")) == {
        "reference_id": "string_pattern_mismatch"
    }


@pytest.mark.parametrize(
    "forced", ["2026-11-10T13:00:00Z", "2026-11-10T12:59:00Z"], ids=["equal", "earlier"]
)
def test_forced_close_must_be_after_close(forced: str) -> None:
    assert errors_for(RfqCreate, rfq_payload(forced_close_at=forced)) == {
        "forced_close_at": "forced_close_not_after_close"
    }


def test_forced_close_compared_across_timezones() -> None:
    # 18:30 IST == 13:00 UTC == bid close, so it is not later.
    payload = rfq_payload(forced_close_at="2026-11-10T18:30:00+05:30")
    assert errors_for(RfqCreate, payload) == {"forced_close_at": "forced_close_not_after_close"}


def test_close_must_be_after_start() -> None:
    assert errors_for(RfqCreate, rfq_payload(bid_close_at="2026-11-10T12:00:00Z")) == {
        "bid_close_at": "close_not_after_start"
    }


def test_naive_datetimes_are_rejected() -> None:
    assert errors_for(RfqCreate, rfq_payload(bid_start_at="2026-11-10T12:00:00")) == {
        "bid_start_at": "timezone_aware"
    }


def test_pickup_cannot_be_before_close_date() -> None:
    assert errors_for(RfqCreate, rfq_payload(pickup_date="2026-11-09")) == {
        "pickup_date": "pickup_before_close"
    }
    # Same day as the close is fine.
    assert RfqCreate.model_validate(rfq_payload(pickup_date="2026-11-10"))


@pytest.mark.parametrize(
    ("config", "field"),
    [
        ({"trigger_window_minutes": 0}, "auction_config.trigger_window_minutes"),
        ({"trigger_window_minutes": 121}, "auction_config.trigger_window_minutes"),
        ({"extension_duration_minutes": 0}, "auction_config.extension_duration_minutes"),
        ({"extension_duration_minutes": -5}, "auction_config.extension_duration_minutes"),
        ({"trigger_type": "ANY_BID"}, "auction_config.trigger_type"),
    ],
)
def test_auction_config_ranges(config: dict[str, Any], field: str) -> None:
    base = rfq_payload()["auction_config"]
    errors = errors_for(RfqCreate, rfq_payload(auction_config={**base, **config}))
    assert list(errors) == [field]


def test_name_length() -> None:
    assert errors_for(RfqCreate, rfq_payload(name="  ab ")) == {"name": "string_too_short"}


# ---------------------------------------------------------------------------
# Bid
# ---------------------------------------------------------------------------


def bid_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "carrier_name": "Swift Ocean Line",
        "freight_charges": "110000.00",
        "origin_charges": "8000",
        "destination_charges": 7000.5,
        "transit_time_days": 24,
        "quote_validity_date": "2026-11-30",
    }
    payload.update(overrides)
    return payload


def test_valid_bid_total() -> None:
    bid = BidCreate.model_validate(bid_payload())
    assert bid.total_amount == Decimal("125000.50")
    assert bid.notes is None


def test_charges_cannot_be_negative() -> None:
    assert errors_for(BidCreate, bid_payload(origin_charges="-1")) == {
        "origin_charges": "greater_than_equal"
    }


def test_charges_have_at_most_two_decimals() -> None:
    assert errors_for(BidCreate, bid_payload(freight_charges="100.123")) == {
        "freight_charges": "decimal_max_places"
    }


def test_total_must_be_positive() -> None:
    zero = {"freight_charges": "0", "origin_charges": "0", "destination_charges": "0"}
    assert errors_for(BidCreate, bid_payload(**zero)) == {"": "zero_total"}


@pytest.mark.parametrize("days", [0, 366])
def test_transit_time_range(days: int) -> None:
    assert list(errors_for(BidCreate, bid_payload(transit_time_days=days))) == ["transit_time_days"]


def test_carrier_name_required() -> None:
    assert errors_for(BidCreate, bid_payload(carrier_name="  ")) == {
        "carrier_name": "string_too_short"
    }
