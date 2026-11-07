import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.routes import health, meta, rfqs, users
from app.config import Settings, get_settings
from app.core.logging import configure_logging
from app.realtime import ws
from app.realtime.manager import ConnectionManager
from app.realtime.relay import EventRelay
from app.web import mount_frontend


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Relay live events from Redis to this process's WebSocket clients while it runs."""
    settings = get_settings()
    manager = ConnectionManager()
    relay = EventRelay(manager, settings.redis_url, settings.events_channel)
    app.state.ws_manager = manager
    app.state.event_relay = relay
    task = asyncio.create_task(relay.run(), name="event-relay")
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        lifespan=lifespan,
        title=settings.app_name,
        version="0.1.0",
        description="RFQ system with British Auction bidding. Mutating endpoints take the "
        "acting user's id in the `X-User-Id` header (see `GET /api/users`).",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)

    for router in (health.router, meta.router, users.router, rfqs.router):
        app.include_router(router, prefix="/api")
    app.include_router(ws.router)
    if settings.static_dir is not None:
        # Last, so its catch-all route never shadows the API.
        mount_frontend(app, settings.static_dir)
    return app


app = create_app()
