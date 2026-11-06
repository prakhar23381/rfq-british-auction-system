from datetime import datetime
from typing import Any

from pydantic import Field

from app.domain.enums import ActivityType
from app.schemas.common import ApiModel, ServerTimed
from app.schemas.party import PartyOut


class ActivityOut(ApiModel):
    id: int
    type: ActivityType
    message: str
    actor: PartyOut | None = Field(description="Null for system events (start, close)")
    metadata: dict[str, Any]
    created_at: datetime


class ActivityListResponse(ServerTimed):
    items: list[ActivityOut]
    next_before_id: int | None = Field(
        description="Pass as before_id to load older entries; null when there are no more"
    )
