"""Reusable FastAPI dependencies (Annotated aliases keep route signatures short)."""

import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header
from redis import Redis
from sqlalchemy.orm import Session

from app.core.clock import Clock, get_clock
from app.core.errors import AppError, ErrorCode
from app.core.redis_client import get_redis
from app.db import get_db
from app.domain.enums import UserRole
from app.models import User
from app.services.scheduling import LifecycleScheduler
from app.workers.scheduling import get_scheduler

DbSession = Annotated[Session, Depends(get_db)]
RedisClient = Annotated[Redis, Depends(get_redis)]
AppClock = Annotated[Clock, Depends(get_clock)]
AppScheduler = Annotated[LifecycleScheduler, Depends(get_scheduler)]


def get_current_user(
    db: DbSession,
    x_user_id: Annotated[str | None, Header(description="Acting user's id (seeded user)")] = None,
) -> User:
    """Resolve the acting user from the X-User-Id header (simplified auth, see HLD)."""
    if not x_user_id:
        raise AppError(ErrorCode.UNAUTHENTICATED, "X-User-Id header is required")
    try:
        user_id = uuid.UUID(x_user_id)
    except ValueError:
        raise AppError(ErrorCode.UNAUTHENTICATED, "X-User-Id is not a valid user id") from None
    user = db.get(User, user_id)
    if user is None:
        raise AppError(ErrorCode.UNAUTHENTICATED, "Unknown user")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(role: UserRole) -> Callable[[User], User]:
    def dependency(user: CurrentUser) -> User:
        if user.role != role:
            raise AppError(ErrorCode.FORBIDDEN, f"Only a {role.value.lower()} can do this")
        return user

    return dependency


BuyerUser = Annotated[User, Depends(require_role(UserRole.BUYER))]
SupplierUser = Annotated[User, Depends(require_role(UserRole.SUPPLIER))]
