from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.clock import utc_now


class ApiModel(BaseModel):
    """Base for API schemas; can be built directly from ORM objects."""

    model_config = ConfigDict(from_attributes=True)


class ServerTimed(ApiModel):
    """Every top-level response carries the server time so clients can correct their clock."""

    server_time: datetime = Field(default_factory=utc_now)


class ErrorDetail(BaseModel):
    field: str | None = None
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)


class ErrorResponse(ServerTimed):
    error: ErrorBody


def error_payload(
    code: str, message: str, details: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return ErrorResponse(
        error=ErrorBody(
            code=code,
            message=message,
            details=[ErrorDetail(**d) for d in details or []],
        )
    ).model_dump(mode="json")
