"""Fuzzing the HTTP API with Hypothesis: whatever a client sends, the server answers with a
deliberate status and the error envelope, never a 500."""

import json
import uuid
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.domain.enums import AuctionStatus, UserRole
from app.models import User
from tests.factories import T0, make_rfq, make_user

FUZZ = settings(
    max_examples=150,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)

# Anything JSON can carry (and a few things it can't, like NaN).
junk = st.recursive(
    st.none()
    | st.booleans()
    | st.integers(min_value=-(10**20), max_value=10**20)
    | st.floats(allow_nan=True, allow_infinity=True)
    | st.text(max_size=40),
    lambda inner: (
        st.lists(inner, max_size=3) | st.dictionaries(st.text(max_size=8), inner, max_size=3)
    ),
    max_leaves=6,
)

timestamps = st.one_of(
    st.datetimes(timezones=st.just(T0.tzinfo)).map(lambda d: d.isoformat()),
    st.sampled_from(["2026-11-10T12:00:00", "2026-11-10", "tomorrow", "", "2026-13-45T99:99:99Z"]),
    junk,
)
money = st.one_of(
    st.decimals(allow_nan=False, allow_infinity=False, places=3).map(str),
    # Up to the column limit (NUMERIC(14, 2)), where totals of several charges overflow.
    st.decimals(min_value=0, max_value=Decimal("999999999999.99"), places=2).map(str),
    st.just("999999999999.99"),
    st.sampled_from(["-1", "0", "1e3", "1,000", "99999999999999.99", "100000000000000"]),
    junk,
)


def maybe(strategy: st.SearchStrategy[Any]) -> st.SearchStrategy[Any]:
    """The field is sent with this value, or left out."""
    return st.one_of(st.just(...), strategy)


def payload(fields: dict[str, st.SearchStrategy[Any]]) -> st.SearchStrategy[dict[str, Any]]:
    return st.fixed_dictionaries({k: maybe(v) for k, v in fields.items()}).map(
        lambda d: {k: v for k, v in d.items() if v is not ...}
    )


rfq_payloads = payload(
    {
        "name": st.one_of(st.text(max_size=130), junk),
        "reference_id": st.one_of(st.from_regex(r"[A-Za-z0-9 -]{0,32}", fullmatch=True), junk),
        "pickup_date": st.one_of(st.dates().map(str), junk),
        "bid_start_at": timestamps,
        "bid_close_at": timestamps,
        "forced_close_at": timestamps,
        "auction_config": st.one_of(
            payload(
                {
                    "trigger_window_minutes": st.one_of(st.integers(-5, 130), junk),
                    "extension_duration_minutes": st.one_of(st.integers(-5, 130), junk),
                    "trigger_type": st.one_of(
                        st.sampled_from(
                            ["BID_RECEIVED", "ANY_RANK_CHANGE", "L1_CHANGE", "l1_change", "X"]
                        ),
                        junk,
                    ),
                }
            ),
            junk,
        ),
    }
)

bid_payloads = payload(
    {
        "carrier_name": st.one_of(st.text(max_size=110), junk),
        "freight_charges": money,
        "origin_charges": money,
        "destination_charges": money,
        "transit_time_days": st.one_of(st.integers(-5, 400), junk),
        "quote_validity_date": st.one_of(st.dates().map(str), junk),
        "notes": st.one_of(st.none(), st.text(max_size=520), junk),
    }
)

ALLOWED = {200, 201, 401, 403, 404, 405, 409, 422}


def assert_handled(response: Any) -> None:
    assert response.status_code in ALLOWED, (response.status_code, response.text[:500])
    body = response.json()
    assert "server_time" in body
    if response.status_code >= 400:
        assert set(body["error"]) >= {"code", "message"}
        assert isinstance(body["error"]["message"], str) and body["error"]["message"]


def post_json(client: TestClient, url: str, data: Any, headers: dict[str, str]) -> Any:
    # json.dumps writes NaN/Infinity, which is not valid JSON: the server must still cope.
    return client.post(
        url, content=json.dumps(data), headers={**headers, "Content-Type": "application/json"}
    )


@pytest.fixture
def people(db: Session) -> tuple[User, User]:
    buyer = make_user(db, UserRole.BUYER)
    supplier = make_user(db)
    db.commit()
    return buyer, supplier


@pytest.mark.timeout(300)
@FUZZ
@given(body=rfq_payloads)
def test_create_rfq_never_crashes(
    client: TestClient, clock: FrozenClock, people: tuple[User, User], body: dict[str, Any]
) -> None:
    clock.set(T0)
    response = post_json(client, "/api/rfqs", body, {"X-User-Id": str(people[0].id)})
    assert_handled(response)
    if response.status_code == 201:
        rfq = response.json()["rfq"]
        assert rfq["bid_start_at"] < rfq["bid_close_at"] < rfq["forced_close_at"]
        assert rfq["current_close_at"] == rfq["bid_close_at"]


@pytest.mark.timeout(300)
@FUZZ
@given(body=bid_payloads)
def test_submit_bid_never_crashes(
    client: TestClient,
    clock: FrozenClock,
    db: Session,
    people: tuple[User, User],
    body: dict[str, Any],
) -> None:
    buyer, supplier = people
    rfq = make_rfq(db, buyer, status=AuctionStatus.ACTIVE)
    db.commit()
    clock.set(T0.replace(minute=30))
    response = post_json(client, f"/api/rfqs/{rfq.id}/bids", body, {"X-User-Id": str(supplier.id)})
    assert_handled(response)
    if response.status_code == 201:
        bid = response.json()["bid"]
        assert float(bid["total_amount"]) > 0


@pytest.mark.timeout(300)
@FUZZ
@given(
    status=st.one_of(
        st.none(), st.sampled_from(["ACTIVE", "CLOSED", "active", "?"]), st.text(max_size=10)
    ),
    search=st.one_of(st.none(), st.text(max_size=120)),
    page=st.one_of(st.none(), st.integers(-3, 10**12).map(str), st.text(max_size=5)),
    page_size=st.one_of(st.none(), st.integers(-3, 500).map(str), st.text(max_size=5)),
)
def test_listing_query_never_crashes(
    client: TestClient, status: Any, search: Any, page: Any, page_size: Any
) -> None:
    params = {
        k: v
        for k, v in {
            "status": status,
            "search": search,
            "page": page,
            "page_size": page_size,
        }.items()
        if v is not None
    }
    assert_handled(client.get("/api/rfqs", params=params))


@pytest.mark.timeout(300)
@FUZZ
@given(
    rfq_id=st.one_of(
        st.uuids().map(str),
        st.text(
            alphabet=st.characters(
                blacklist_categories=["Cs", "Cc"], blacklist_characters="/?#%\\"
            ),
            max_size=40,
        ),
    ),
    user_header=st.one_of(
        st.uuids().map(str),
        st.text(alphabet=st.characters(min_codepoint=33, max_codepoint=126), max_size=40),
    ),
)
def test_paths_and_user_header_never_crash(
    client: TestClient, people: tuple[User, User], rfq_id: str, user_header: str
) -> None:
    for url in (f"/api/rfqs/{rfq_id}", f"/api/rfqs/{rfq_id}/bids", f"/api/rfqs/{rfq_id}/activity"):
        if rfq_id:
            assert_handled(client.get(url))
    assert_handled(client.get("/api/users/me", headers={"X-User-Id": user_header}))
    assert_handled(
        post_json(client, f"/api/rfqs/{uuid.uuid4()}/bids", {}, {"X-User-Id": user_header})
    )


# Nearly valid requests: everything correct except one field, so the deeper rules run too.
VALID_RFQ: dict[str, Any] = {
    "name": "Fuzz lane",
    "pickup_date": "2026-12-01",
    "bid_start_at": "2026-11-10T12:05:00Z",
    "bid_close_at": "2026-11-10T13:00:00Z",
    "forced_close_at": "2026-11-10T13:30:00Z",
    "auction_config": {
        "trigger_window_minutes": 10,
        "extension_duration_minutes": 5,
        "trigger_type": "L1_CHANGE",
    },
}
VALID_BID: dict[str, Any] = {
    "carrier_name": "Fuzz Line",
    "freight_charges": "1000.00",
    "origin_charges": "100.00",
    "destination_charges": "50.00",
    "transit_time_days": 10,
    "quote_validity_date": "2026-12-31",
}
RFQ_FIELDS: dict[str, st.SearchStrategy[Any]] = {
    "name": st.one_of(st.text(max_size=130), junk),
    "reference_id": st.one_of(st.from_regex(r"[A-Za-z0-9 -]{0,32}", fullmatch=True), junk),
    "pickup_date": st.one_of(st.dates().map(str), junk),
    "bid_start_at": timestamps,
    "bid_close_at": timestamps,
    "forced_close_at": timestamps,
    "auction_config.trigger_window_minutes": st.one_of(st.integers(-5, 130), junk),
    "auction_config.extension_duration_minutes": st.one_of(st.integers(-5, 130), junk),
    "auction_config.trigger_type": st.one_of(st.text(max_size=20), junk),
}
BID_FIELDS: dict[str, st.SearchStrategy[Any]] = {
    "carrier_name": st.one_of(st.text(max_size=110), junk),
    "freight_charges": money,
    "origin_charges": money,
    "destination_charges": money,
    "transit_time_days": st.one_of(st.integers(-5, 400), junk),
    "quote_validity_date": st.one_of(st.dates().map(str), junk),
    "notes": st.one_of(st.text(max_size=520), junk),
}


def with_field(base: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    body = json.loads(json.dumps(base))
    *parents, leaf = path.split(".")
    target = body
    for key in parents:
        target = target[key]
    target[leaf] = value
    return body


def test_the_valid_bases_are_accepted(
    client: TestClient, clock: FrozenClock, db: Session, people: tuple[User, User]
) -> None:
    clock.set(T0)
    buyer, supplier = people
    created = post_json(client, "/api/rfqs", VALID_RFQ, {"X-User-Id": str(buyer.id)})
    assert created.status_code == 201
    clock.set(T0.replace(minute=30))
    bid = post_json(
        client,
        f"/api/rfqs/{created.json()['rfq']['id']}/bids",
        VALID_BID,
        {"X-User-Id": str(supplier.id)},
    )
    assert bid.status_code == 201


@pytest.mark.timeout(300)
@FUZZ
@given(data=st.data())
def test_one_bad_rfq_field_is_reported_on_that_field(
    client: TestClient, clock: FrozenClock, people: tuple[User, User], data: st.DataObject
) -> None:
    clock.set(T0)
    path = data.draw(st.sampled_from(sorted(RFQ_FIELDS)))
    value = data.draw(RFQ_FIELDS[path])
    response = post_json(
        client, "/api/rfqs", with_field(VALID_RFQ, path, value), {"X-User-Id": str(people[0].id)}
    )
    assert_handled(response)
    if response.status_code == 422:
        fields = {d.get("field") for d in response.json()["error"].get("details", [])}
        # The error names the field we broke (or, for times, a field whose rule it broke).
        related = (
            {"bid_start_at", "bid_close_at", "forced_close_at", "pickup_date"}
            if path.endswith("_at") or path == "pickup_date"
            else {path}
        )
        assert fields & (related | {path, path.split(".")[0], None}), (path, value, fields)
    if response.status_code == 201:
        rfq = response.json()["rfq"]
        assert rfq["bid_start_at"] < rfq["bid_close_at"] < rfq["forced_close_at"]


@pytest.mark.timeout(300)
@FUZZ
@given(data=st.data())
def test_one_bad_bid_field_is_reported_on_that_field(
    client: TestClient,
    clock: FrozenClock,
    db: Session,
    people: tuple[User, User],
    data: st.DataObject,
) -> None:
    buyer, supplier = people
    rfq = make_rfq(db, buyer, status=AuctionStatus.ACTIVE)
    db.commit()
    clock.set(T0.replace(minute=30))
    path = data.draw(st.sampled_from(sorted(BID_FIELDS)))
    value = data.draw(BID_FIELDS[path])
    response = post_json(
        client,
        f"/api/rfqs/{rfq.id}/bids",
        with_field(VALID_BID, path, value),
        {"X-User-Id": str(supplier.id)},
    )
    assert_handled(response)
    if response.status_code == 422:
        fields = {d.get("field") for d in response.json()["error"].get("details", [])}
        assert fields & {path, None}, (
            path,
            value,
            fields,
        )  # None: the total rule (no single field)
    if response.status_code == 201:
        body = response.json()
        assert float(body["bid"]["total_amount"]) > 0
        assert body["rank_label"] == "L1"
