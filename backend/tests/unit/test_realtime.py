"""Connection manager, channel names and the Redis relay, in isolation."""

import asyncio
import json
import uuid
from typing import Any, cast

import pytest
from fastapi import WebSocket
from redis import Redis

from app.config import get_settings
from app.realtime import events as events_module
from app.realtime import manager as manager_module
from app.realtime.events import encode, normalize_channel, rfq_channel
from app.realtime.manager import MAX_SUBSCRIPTIONS, ConnectionManager
from app.realtime.relay import EventRelay


class FakeSocket:
    def __init__(self, *, fail: bool = False, stall: bool = False) -> None:
        self.sent: list[str] = []
        self.fail = fail
        self.stall = stall
        self.closed = False
        self.in_send = 0
        self.max_in_send = 0

    async def send_text(self, text: str) -> None:
        if self.fail:
            raise RuntimeError("connection reset")
        self.in_send += 1
        self.max_in_send = max(self.max_in_send, self.in_send)
        await asyncio.sleep(3600 if self.stall else 0.001)
        self.in_send -= 1
        self.sent.append(text)

    async def close(self) -> None:
        self.closed = True


def ws(fake: FakeSocket) -> WebSocket:
    return cast(WebSocket, fake)


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------


def test_channel_names_are_validated_and_normalised() -> None:
    rfq_id = uuid.uuid4()
    assert normalize_channel("listing") == "listing"
    assert normalize_channel(f"rfq:{rfq_id}") == rfq_channel(rfq_id)
    assert normalize_channel(f"rfq:{str(rfq_id).upper()}") == rfq_channel(rfq_id)
    assert normalize_channel(f"rfq:{rfq_id.hex}") == rfq_channel(rfq_id)
    for bad in [None, 42, "", "LISTING", "rfq:", "rfq:123", f"rfq:{rfq_id}x", f"x:{rfq_id}",
                f"rfq:{{{rfq_id}}}", f"rfq: {rfq_id}", "rfq:" + "-" * 36]:  # fmt: skip
        assert normalize_channel(bad) is None, bad


def test_envelope_shape() -> None:
    message = json.loads(encode("pong", None, {}))
    assert set(message) == {"type", "channel", "data", "server_time"}
    assert message["server_time"].endswith("Z")


# ---------------------------------------------------------------------------
# Connection manager
# ---------------------------------------------------------------------------


def test_broadcast_reaches_only_the_channel_subscribers() -> None:
    async def scenario() -> None:
        manager = ConnectionManager()
        a, b, c = FakeSocket(), FakeSocket(), FakeSocket()
        for fake in (a, b, c):
            manager.connect(ws(fake))
        manager.subscribe(ws(a), "listing")
        manager.subscribe(ws(b), "listing")
        manager.subscribe(ws(c), "rfq:x")
        assert await manager.broadcast("listing", "hello") == 2
        assert await manager.broadcast("nobody", "hello") == 0
        assert (a.sent, b.sent, c.sent) == (["hello"], ["hello"], [])

        manager.unsubscribe(ws(a), "listing")
        manager.unsubscribe(ws(a), "listing")  # idempotent
        assert await manager.broadcast("listing", "again") == 1
        assert await manager.broadcast_all("everyone") == 3

    asyncio.run(scenario())


def test_dead_socket_is_dropped_and_closed() -> None:
    async def scenario() -> None:
        manager = ConnectionManager()
        alive, dead = FakeSocket(), FakeSocket(fail=True)
        for fake in (alive, dead):
            manager.connect(ws(fake))
            manager.subscribe(ws(fake), "listing")
        assert await manager.broadcast("listing", "x") == 1
        assert dead.closed
        assert manager.connection_count == 1
        assert manager.subscribers("listing") == 1

    asyncio.run(scenario())


def test_stuck_socket_does_not_hold_up_the_others(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(manager_module, "SEND_TIMEOUT_SECONDS", 0.05)

    async def scenario() -> None:
        manager = ConnectionManager()
        fast, stuck = FakeSocket(), FakeSocket(stall=True)
        for fake in (fast, stuck):
            manager.connect(ws(fake))
            manager.subscribe(ws(fake), "listing")
        assert await asyncio.wait_for(manager.broadcast("listing", "x"), timeout=1) == 1
        assert fast.sent == ["x"]
        assert manager.connection_count == 1

    asyncio.run(scenario())


def test_sends_to_one_socket_never_overlap() -> None:
    async def scenario() -> None:
        manager = ConnectionManager()
        fake = FakeSocket()
        manager.connect(ws(fake))
        await asyncio.gather(*(manager.send(ws(fake), str(n)) for n in range(20)))
        assert fake.max_in_send == 1
        assert sorted(fake.sent, key=int) == [str(n) for n in range(20)]

    asyncio.run(scenario())


def test_subscription_bookkeeping() -> None:
    manager = ConnectionManager()
    fake, stranger = FakeSocket(), FakeSocket()
    assert manager.subscribe(ws(stranger), "listing") is False  # never connected
    manager.connect(ws(fake))
    for n in range(MAX_SUBSCRIPTIONS):
        assert manager.subscribe(ws(fake), f"rfq:{n}")
    assert manager.subscribe(ws(fake), "rfq:0")  # already subscribed: still fine at the limit
    assert not manager.subscribe(ws(fake), "listing")
    manager.disconnect(ws(fake))
    manager.disconnect(ws(fake))  # idempotent
    assert manager.connection_count == 0
    assert manager.subscribers("rfq:0") == 0


def test_send_to_unknown_socket_is_a_noop() -> None:
    assert asyncio.run(ConnectionManager().send(ws(FakeSocket()), "x")) is False


# ---------------------------------------------------------------------------
# Relay
# ---------------------------------------------------------------------------


class FakeManager(ConnectionManager):
    def __init__(self) -> None:
        super().__init__()
        self.broadcasts: list[tuple[str, str]] = []
        self.to_all: list[str] = []

    async def broadcast(self, channel: str, text: str) -> int:
        self.broadcasts.append((channel, text))
        return 1

    async def broadcast_all(self, text: str) -> int:
        self.to_all.append(text)
        return 1


@pytest.mark.parametrize(
    "raw", ["not json", "[]", '{"type": "x"}', '{"channel": 5}', '{"channel": null}']
)
def test_relay_ignores_malformed_events(raw: str) -> None:
    fake = FakeManager()
    relay = EventRelay(fake, "redis://unused", "events")
    assert asyncio.run(relay.dispatch(raw)) == 0
    assert fake.broadcasts == []


async def _wait_for(condition: Any, timeout: float = 10.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not condition():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.02)


def test_relay_forwards_published_events_and_resyncs_after_an_outage() -> None:
    settings = get_settings()
    channel = f"relay-test-{uuid.uuid4()}"

    async def scenario() -> None:
        fake = FakeManager()
        relay = EventRelay(fake, "redis://localhost:1/0", channel)  # nothing listens there
        task = asyncio.create_task(relay.run())
        try:
            await asyncio.sleep(0.3)
            assert not relay.is_listening

            relay._redis_url = settings.redis_url  # Redis "comes back"
            await _wait_for(lambda: relay.is_listening)
            # Events published while it was away are lost, so clients are told to refetch.
            assert [json.loads(m)["type"] for m in fake.to_all] == ["resync"]

            raw = encode("bid.submitted", "rfq:abc", {"version": 1})
            Redis.from_url(settings.redis_url).publish(channel, raw)
            await _wait_for(lambda: fake.broadcasts)
            assert fake.broadcasts == [("rfq:abc", raw)]
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert not relay.is_listening

    asyncio.run(scenario())


def test_relay_does_not_resync_on_a_clean_first_connect() -> None:
    settings = get_settings()

    async def scenario() -> None:
        fake = FakeManager()
        relay = EventRelay(fake, settings.redis_url, f"relay-test-{uuid.uuid4()}")
        task = asyncio.create_task(relay.run())
        try:
            await _wait_for(lambda: relay.is_listening)
            assert fake.to_all == []
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(scenario())


def test_publisher_survives_a_redis_outage(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    unreachable = Redis.from_url("redis://localhost:1/0", socket_connect_timeout=0.5)
    monkeypatch.setattr(events_module, "get_redis", lambda: unreachable)
    events_module.RedisPublisher().publish("bid.submitted", "rfq:x", {})  # no exception
    assert "Could not publish bid.submitted on rfq:x" in caplog.text
