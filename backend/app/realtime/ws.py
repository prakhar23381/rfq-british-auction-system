"""The `/ws` endpoint: clients subscribe to `listing` and/or `rfq:<id>` channels.

Client messages (JSON text frames):
    {"action": "subscribe", "channel": "rfq:<uuid>"}   -> {"type": "subscribed", ...}
    {"action": "unsubscribe", "channel": "rfq:<uuid>"} -> {"type": "unsubscribed", ...}
    {"action": "ping"}                                 -> {"type": "pong", ...}
Invalid messages get {"type": "error", "data": {"code", "message"}}; the connection stays open.

Subscribe first, then load the page over REST, and keep the highest `version` seen: nothing is
missed in between and stale events are ignored.
"""

import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.realtime.events import encode, normalize_channel
from app.realtime.manager import MAX_SUBSCRIPTIONS, ConnectionManager

router = APIRouter()


def _error(code: str, message: str) -> str:
    return encode("error", None, {"code": code, "message": message})


async def _handle(ws: WebSocket, manager: ConnectionManager, text: str) -> None:
    try:
        message: Any = json.loads(text)
    except ValueError:
        await manager.send(ws, _error("INVALID_MESSAGE", "Messages must be JSON objects"))
        return
    if not isinstance(message, dict):
        await manager.send(ws, _error("INVALID_MESSAGE", "Messages must be JSON objects"))
        return

    action = message.get("action")
    if action == "ping":
        await manager.send(ws, encode("pong", None, {}))
        return
    if action not in ("subscribe", "unsubscribe"):
        await manager.send(
            ws, _error("UNKNOWN_ACTION", "action must be subscribe, unsubscribe or ping")
        )
        return

    channel = normalize_channel(message.get("channel"))
    if channel is None:
        await manager.send(
            ws, _error("INVALID_CHANNEL", 'channel must be "listing" or "rfq:<rfq id>"')
        )
        return
    if action == "unsubscribe":
        manager.unsubscribe(ws, channel)
        await manager.send(ws, encode("unsubscribed", channel, {}))
    elif manager.subscribe(ws, channel):
        await manager.send(ws, encode("subscribed", channel, {}))
    else:
        await manager.send(
            ws,
            _error("TOO_MANY_SUBSCRIPTIONS", f"At most {MAX_SUBSCRIPTIONS} channels per socket"),
        )


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    manager: ConnectionManager = ws.app.state.ws_manager
    await ws.accept()
    manager.connect(ws)
    try:
        while True:
            frame = await ws.receive()
            if frame["type"] == "websocket.disconnect":
                break
            text = frame.get("text")
            if text is None:
                await manager.send(ws, _error("INVALID_MESSAGE", "Send JSON as text frames"))
                continue
            await _handle(ws, manager, text)
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws)
