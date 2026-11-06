from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app.api.deps import DbSession, RedisClient

router = APIRouter(tags=["meta"])

CheckStatus = Literal["ok", "error"]


class HealthResponse(BaseModel):
    status: CheckStatus
    db: CheckStatus
    redis: CheckStatus
    server_time: datetime


@router.get("/health", response_model=HealthResponse)
def health(db: DbSession, redis: RedisClient) -> HealthResponse:
    """Liveness + dependency check. Returns 200 even when a dependency is down, so the
    caller can see which one failed."""
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

    overall: CheckStatus = "ok" if db_status == redis_status == "ok" else "error"
    return HealthResponse(
        status=overall, db=db_status, redis=redis_status, server_time=datetime.now(UTC)
    )
