import re
from datetime import datetime
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field
from pydantic_core import PydanticCustomError

from app.core.clock import utc_now

# Control characters other than tab, newline and carriage return. PostgreSQL cannot store NUL
# at all, and the rest have no business in names or notes.
CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _no_control_characters(value: str) -> str:
    if CONTROL_CHARACTERS.search(value):
        raise PydanticCustomError("control_characters", "Text must not contain control characters")
    return value


# Free text from clients (names, notes): stored as-is, minus control characters.
Text = Annotated[str, AfterValidator(_no_control_characters)]


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
