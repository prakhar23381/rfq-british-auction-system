"""Forwards events from Redis pub/sub to this process's WebSocket clients.

Runs as a background task for the lifetime of the API process. If Redis goes away it
reconnects with backoff; events published in the meantime are lost, so after reconnecting it
tells every client to `resync` (refetch over REST).
"""

import asyncio
import json
import logging

from redis.asyncio import Redis

from app.realtime.events import encode
from app.realtime.manager import ConnectionManager

logger = logging.getLogger(__name__)

MAX_BACKOFF_SECONDS = 10.0


class EventRelay:
    def __init__(self, manager: ConnectionManager, redis_url: str, channel: str) -> None:
        self._manager = manager
        self._redis_url = redis_url
        self._channel = channel
        self.is_listening = False

    async def run(self) -> None:
        backoff = 0.5
        missed_events = False
        while True:
            client = Redis.from_url(
                self._redis_url, decode_responses=True, health_check_interval=30
            )
            try:
                async with client.pubsub() as pubsub:
                    await pubsub.subscribe(self._channel)
                    self.is_listening = True
                    backoff = 0.5
                    logger.info("Relaying live events from Redis channel %s", self._channel)
                    if missed_events:
                        await self._manager.broadcast_all(encode("resync", None, {}))
                        missed_events = False
                    async for message in pubsub.listen():
                        if message["type"] == "message":
                            await self.dispatch(message["data"])
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning(
                    "Live event relay lost Redis; retrying in %.1fs", backoff, exc_info=True
                )
                missed_events = True
            finally:
                self.is_listening = False
                await client.aclose()
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)

    async def dispatch(self, raw: str) -> int:
        """Send one published event to the clients subscribed to its channel."""
        try:
            channel = json.loads(raw)["channel"]
        except (ValueError, KeyError, TypeError):
            logger.warning("Ignoring malformed live event: %.200s", raw)
            return 0
        if not isinstance(channel, str):
            return 0
        return await self._manager.broadcast(channel, raw)
