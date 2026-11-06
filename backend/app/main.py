from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.routes import health, meta, rfqs, users
from app.config import get_settings
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
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
    return app


app = create_app()
