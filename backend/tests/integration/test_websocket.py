"""/ws end to end: protocol, and events travelling API/Celery -> Redis pub/sub -> socket (A24)."""

import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from starlette.testclient import WebSocketTestSession

from app.core.clock import FrozenClock, utc_now
from app.domain.enums import AuctionStatus, UserRole
from app.main import app
from app.models import Rfq, User
from app.realtime.events import RedisPublisher, get_publisher
from app.realtime.manager import MAX_SUBSCRIPTIONS
from app.workers import tasks
from tests.factories import T0, make_rfq, make_user
from tests.waiting import wait_until

MIN = timedelta(minutes=1)


def manager_connections() -> int:
    return int(app.state.ws_manager.connection_count)


@pytest.fixture
def live(client: TestClient) -> Iterator[TestClient]:
    """The app publishing through real Redis, with its relay subscribed."""
    app.dependency_overrides[get_publisher] = lambda: RedisPublisher()
    wait_until(lambda: app.state.event_relay.is_listening)
    yield client


def subscribe(ws: WebSocketTestSession, channel: str) -> dict[str, Any]:
    ws.send_json({"action": "subscribe", "channel": channel})
    reply: dict[str, Any] = ws.receive_json()
    return reply


def assert_nothing_pending(ws: WebSocketTestSession) -> None:
    """A ping is answered in order, so if the next message is the pong nothing else was sent."""
    ws.send_json({"action": "ping"})
    assert ws.receive_json()["type"] == "pong"


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


def test_ping_subscribe_unsubscribe(client: TestClient) -> None:
    rfq_id = uuid.uuid4()
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"action": "ping"})
        pong = ws.receive_json()
        assert pong["type"] == "pong"
        assert pong["server_time"].endswith("Z")

        reply = subscribe(ws, "listing")
        assert (reply["type"], reply["channel"], reply["data"]) == ("subscribed", "listing", {})
        # Channel names are normalised (upper-case or unhyphenated ids are accepted).
        reply = subscribe(ws, f"rfq:{rfq_id.hex.upper()}")
        assert (reply["type"], reply["channel"]) == ("subscribed", f"rfq:{rfq_id}")
        assert app.state.ws_manager.subscribers(f"rfq:{rfq_id}") == 1

        ws.send_json({"action": "unsubscribe", "channel": f"rfq:{rfq_id}"})
        assert ws.receive_json()["type"] == "unsubscribed"
        assert app.state.ws_manager.subscribers(f"rfq:{rfq_id}") == 0
    wait_until(lambda: manager_connections() == 0)


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ("not json", "INVALID_MESSAGE"),
        ("[1, 2]", "INVALID_MESSAGE"),
        ('{"action": "dance"}', "UNKNOWN_ACTION"),
        ('{"action": "subscribe"}', "INVALID_CHANNEL"),
        ('{"action": "subscribe", "channel": "rfq:not-a-uuid"}', "INVALID_CHANNEL"),
        ('{"action": "subscribe", "channel": "admin"}', "INVALID_CHANNEL"),
        ('{"action": "subscribe", "channel": 42}', "INVALID_CHANNEL"),
    ],
)
def test_bad_messages_get_an_error_and_keep_the_connection(
    client: TestClient, message: str, code: str
) -> None:
    with client.websocket_connect("/ws") as ws:
        ws.send_text(message)
        reply = ws.receive_json()
        assert reply["type"] == "error"
        assert reply["data"]["code"] == code
        assert_nothing_pending(ws)  # still connected and responsive


def test_binary_frames_are_rejected_politely(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        ws.send_bytes(b'{"action": "ping"}')
        assert ws.receive_json()["data"]["code"] == "INVALID_MESSAGE"
        assert_nothing_pending(ws)


def test_subscription_limit(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        for _ in range(MAX_SUBSCRIPTIONS):
            assert subscribe(ws, f"rfq:{uuid.uuid4()}")["type"] == "subscribed"
        reply = subscribe(ws, f"rfq:{uuid.uuid4()}")
        assert reply["data"]["code"] == "TOO_MANY_SUBSCRIPTIONS"
        assert subscribe(ws, "listing")["type"] == "error"  # limit applies to every channel


def test_disconnect_releases_subscriptions(client: TestClient) -> None:
    rfq_id = uuid.uuid4()
    with client.websocket_connect("/ws") as ws:
        subscribe(ws, f"rfq:{rfq_id}")
        assert manager_connections() == 1
    wait_until(lambda: manager_connections() == 0)
    assert app.state.ws_manager.subscribers(f"rfq:{rfq_id}") == 0


# ---------------------------------------------------------------------------
# End to end through Redis
# ---------------------------------------------------------------------------


@pytest.fixture
def auction(db: Session) -> tuple[Rfq, User, User]:
    buyer = make_user(db, UserRole.BUYER, company="Acme Exports")
    a = make_user(db, company="BlueWave")
    b = make_user(db, company="Swift Cargo")
    rfq = make_rfq(db, buyer, start=T0, close=T0 + 60 * MIN, forced=T0 + 120 * MIN,
                   status=AuctionStatus.ACTIVE)  # fmt: skip
    db.commit()
    return rfq, a, b


def post_bid(client: TestClient, rfq_id: uuid.UUID, supplier: User, amount: int) -> Any:
    return client.post(
        f"/api/rfqs/{rfq_id}/bids",
        json={
            "carrier_name": "Line",
            "freight_charges": str(amount),
            "origin_charges": "0",
            "destination_charges": "0",
            "transit_time_days": 10,
            "quote_validity_date": "2026-12-31",
        },
        headers={"X-User-Id": str(supplier.id)},
    )


def test_a24_bids_and_extensions_reach_subscribed_sockets_only(
    live: TestClient, clock: FrozenClock, auction: tuple[Rfq, User, User]
) -> None:
    rfq, a, b = auction
    other = f"rfq:{uuid.uuid4()}"
    with (
        live.websocket_connect("/ws") as detail_ws,
        live.websocket_connect("/ws") as listing_ws,
        live.websocket_connect("/ws") as other_ws,
    ):
        subscribe(detail_ws, f"rfq:{rfq.id}")
        subscribe(listing_ws, "listing")
        subscribe(other_ws, other)

        clock.set(T0 + MIN)
        assert post_bid(live, rfq.id, a, 1000).status_code == 201
        clock.set(T0 + 55 * MIN)  # inside the 10 min window: new L1 extends the auction
        assert post_bid(live, rfq.id, b, 900).status_code == 201

        received = [detail_ws.receive_json() for _ in range(3)]
        assert [m["type"] for m in received] == [
            "bid.submitted",
            "bid.submitted",
            "auction.extended",
        ]
        assert all(m["channel"] == f"rfq:{rfq.id}" for m in received)
        assert received[1]["data"]["ranking"][0]["supplier"]["company_name"] == "Swift Cargo"
        assert received[2]["data"]["new_close_at"] == "2026-11-10T13:05:00Z"
        assert received[0]["data"]["version"] < received[1]["data"]["version"]

        listing = [listing_ws.receive_json() for _ in range(2)]
        assert [m["type"] for m in listing] == ["listing.updated", "listing.updated"]
        assert listing[1]["data"]["item"]["current_close_at"] == "2026-11-10T13:05:00Z"

        assert_nothing_pending(detail_ws)
        assert_nothing_pending(listing_ws)
        assert_nothing_pending(other_ws)


def test_celery_close_reaches_the_socket(live: TestClient, db: Session) -> None:
    """Stage 7 DoD: an auction.status published by a Celery task (another process in real
    deployments) arrives over the WebSocket."""
    buyer = make_user(db, UserRole.BUYER)
    now = utc_now()
    rfq = make_rfq(db, buyer, start=now - 10 * MIN, close=now - MIN, forced=now + MIN,
                   status=AuctionStatus.ACTIVE)  # fmt: skip
    db.commit()

    with live.websocket_connect("/ws") as ws:
        subscribe(ws, f"rfq:{rfq.id}")
        subscribe(ws, "listing")
        assert tasks.close_auction(str(rfq.id), rfq.current_close_at.isoformat()) == "UPDATED"

        status, listing = ws.receive_json(), ws.receive_json()
        assert (status["type"], status["data"]["status"]) == ("auction.status", "CLOSED")
        assert status["data"]["activity"][0]["message"] == "Auction closed with no bids"
        assert (listing["type"], listing["data"]["item"]["status"]) == ("listing.updated", "CLOSED")


def test_new_rfq_appears_on_the_listing_channel(
    live: TestClient, clock: FrozenClock, db: Session
) -> None:
    buyer = make_user(db, UserRole.BUYER)
    db.commit()
    clock.set(T0)
    with live.websocket_connect("/ws") as ws:
        subscribe(ws, "listing")
        res = live.post(
            "/api/rfqs",
            json={
                "name": "Chennai to Singapore",
                "pickup_date": "2026-12-01",
                "bid_start_at": (T0 + MIN).isoformat(),
                "bid_close_at": (T0 + 60 * MIN).isoformat(),
                "forced_close_at": (T0 + 90 * MIN).isoformat(),
                "auction_config": {
                    "trigger_window_minutes": 5,
                    "extension_duration_minutes": 5,
                    "trigger_type": "BID_RECEIVED",
                },
            },
            headers={"X-User-Id": str(buyer.id)},
        )
        event = ws.receive_json()
        assert event["type"] == "rfq.created"
        assert event["data"]["item"]["id"] == res.json()["rfq"]["id"]
