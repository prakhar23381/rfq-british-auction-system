"""Publishing live events.

Every event is one JSON message on a single Redis pub/sub channel
(`settings.events_channel`). Each API process relays it to the WebSocket clients subscribed to
the event's own `channel` (`listing` or `rfq:<id>`), so events from any API process or Celery
worker reach every browser.

Publishing is best effort and happens after the database commit: a Redis outage never fails a
request, and clients refetch over REST when they reconnect.
"""

import json
import logging
import re
import uuid
from typing import Any, Protocol

from redis.exceptions import RedisError

from app.config import get_settings
from app.core.clock import utc_now
from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)

LISTING_CHANNEL = "listing"
_RFQ_CHANNEL = re.compile(r"^rfq:(?P<id>[0-9a-fA-F-]{32,36})$")


def rfq_channel(rfq_id: uuid.UUID) -> str:
    return f"rfq:{rfq_id}"


def normalize_channel(channel: object) -> str | None:
    """The canonical channel name, or None if it is not one clients may subscribe to."""
    if channel == LISTING_CHANNEL:
        return LISTING_CHANNEL
    if not isinstance(channel, str):
        return None
    match = _RFQ_CHANNEL.match(channel)
    if match is None:
        return None
    try:
        return rfq_channel(uuid.UUID(match["id"]))
    except ValueError:
        return None


def encode(type: str, channel: str | None, data: dict[str, Any]) -> str:
    """The envelope every server message uses."""
    return json.dumps(
        {
            "type": type,
            "channel": channel,
            "data": data,
            "server_time": utc_now().isoformat().replace("+00:00", "Z"),
        },
        separators=(",", ":"),
    )


class EventPublisher(Protocol):
    def publish(self, type: str, channel: str, data: dict[str, Any]) -> None: ...


class NullPublisher:
    def publish(self, type: str, channel: str, data: dict[str, Any]) -> None:
        pass


class RedisPublisher:
    def publish(self, type: str, channel: str, data: dict[str, Any]) -> None:
        try:
            get_redis().publish(get_settings().events_channel, encode(type, channel, data))
        except RedisError:
            logger.warning("Could not publish %s on %s", type, channel, exc_info=True)


_publisher = RedisPublisher()


def get_publisher() -> EventPublisher:
    """FastAPI dependency (and the Celery tasks' publisher); tests override it."""
    return _publisher
