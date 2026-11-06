from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import AppClock

router = APIRouter(prefix="/meta", tags=["meta"])


class TimeResponse(BaseModel):
    server_time: datetime


@router.get("/time", response_model=TimeResponse)
def server_time(clock: AppClock) -> TimeResponse:
    """Authoritative server time, used by clients to sync auction countdowns."""
    return TimeResponse(server_time=clock.now())
