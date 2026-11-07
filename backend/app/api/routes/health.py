from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import text

from app.api.deps import DbSession, RedisClient

router = APIRouter(tags=["meta"])

CheckStatus = Literal["ok", "error"]


class HealthResponse(BaseModel):
    status: CheckStatus
    db: CheckStatus
    redis: CheckStatus
    realtime: CheckStatus
    server_time: datetime


@router.get("/health", response_model=HealthResponse)
def health(request: Request, db: DbSession, redis: RedisClient) -> HealthResponse:
    """Liveness + dependency check. Returns 200 even when a dependency is down, so the
    caller can see which one failed. `realtime` is the live-event relay (Redis pub/sub)."""
    db_status: CheckStatus = "ok"
    redis_status: CheckStatus = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"
    try:
        redis.ping()
    except Exception:
        redis_status = "error"

    relay = getattr(request.app.state, "event_relay", None)
    realtime_status: CheckStatus = "ok" if relay is not None and relay.is_listening else "error"

    overall: CheckStatus = "ok" if db_status == redis_status == realtime_status == "ok" else "error"
    return HealthResponse(
        status=overall,
        db=db_status,
        redis=redis_status,
        realtime=realtime_status,
        server_time=datetime.now(UTC),
    )
