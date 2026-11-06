"""Reusable FastAPI dependencies (Annotated aliases keep route signatures short)."""

from typing import Annotated

from fastapi import Depends
from redis import Redis
from sqlalchemy.orm import Session

from app.core.redis_client import get_redis
from app.db import get_db

DbSession = Annotated[Session, Depends(get_db)]
RedisClient = Annotated[Redis, Depends(get_redis)]
