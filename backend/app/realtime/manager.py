"""WebSocket connections of this API process and the channels they subscribe to."""

import asyncio
import contextlib
import logging
from collections import defaultdict
from dataclasses import dataclass, field

from fastapi import WebSocket

logger = logging.getLogger(__name__)

MAX_SUBSCRIPTIONS = 50
SEND_TIMEOUT_SECONDS = 5.0


@dataclass
class _Client:
    channels: set[str] = field(default_factory=set)
    # One send at a time per socket: relayed events and replies come from different tasks.
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class ConnectionManager:
    def __init__(self) -> None:
        self._clients: dict[WebSocket, _Client] = {}
        self._channels: dict[str, set[WebSocket]] = defaultdict(set)

    @property
    def connection_count(self) -> int:
        return len(self._clients)

    def subscribers(self, channel: str) -> int:
        return len(self._channels.get(channel, ()))

    def connect(self, ws: WebSocket) -> None:
        self._clients[ws] = _Client()

    def disconnect(self, ws: WebSocket) -> None:
        client = self._clients.pop(ws, None)
        if client is None:
            return
        for channel in client.channels:
            sockets = self._channels.get(channel)
            if sockets is not None:
                sockets.discard(ws)
                if not sockets:
                    del self._channels[channel]

    def subscribe(self, ws: WebSocket, channel: str) -> bool:
        """False if the socket is unknown or already has the maximum number of channels."""
        client = self._clients.get(ws)
        if client is None:
            return False
        if channel not in client.channels and len(client.channels) >= MAX_SUBSCRIPTIONS:
            return False
        client.channels.add(channel)
        self._channels[channel].add(ws)
        return True

    def unsubscribe(self, ws: WebSocket, channel: str) -> None:
        client = self._clients.get(ws)
        if client is None or channel not in client.channels:
            return
        client.channels.discard(channel)
        sockets = self._channels[channel]
        sockets.discard(ws)
        if not sockets:
            del self._channels[channel]

    async def send(self, ws: WebSocket, text: str) -> bool:
        """Send to one socket; a dead or stuck socket is dropped (it must reconnect)."""
        client = self._clients.get(ws)
        if client is None:
            return False
        try:
            async with client.lock:
                await asyncio.wait_for(ws.send_text(text), SEND_TIMEOUT_SECONDS)
            return True
        except Exception:
            logger.info("Dropping WebSocket client that could not be reached")
            self.disconnect(ws)
            with contextlib.suppress(Exception):
                await ws.close()
            return False

    async def broadcast(self, channel: str, text: str) -> int:
        targets = list(self._channels.get(channel, ()))
        sent = await asyncio.gather(*(self.send(ws, text) for ws in targets))
        return sum(sent)

    async def broadcast_all(self, text: str) -> int:
        sent = await asyncio.gather(*(self.send(ws, text) for ws in list(self._clients)))
        return sum(sent)
