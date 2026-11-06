"""Application error type and error codes. Every error response uses one JSON envelope:

{"error": {"code": "...", "message": "...", "details": [...]}, "server_time": "..."}
"""

from enum import StrEnum
from typing import Any

from fastapi import status


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    DUPLICATE_REFERENCE = "DUPLICATE_REFERENCE"
    AUCTION_NOT_STARTED = "AUCTION_NOT_STARTED"
    AUCTION_CLOSED = "AUCTION_CLOSED"
    FORCED_CLOSE_NOT_AFTER_CLOSE = "FORCED_CLOSE_NOT_AFTER_CLOSE"
    BID_NOT_LOWER = "BID_NOT_LOWER"
    INTERNAL_ERROR = "INTERNAL_ERROR"


DEFAULT_STATUS: dict[ErrorCode, int] = {
    ErrorCode.VALIDATION_ERROR: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ErrorCode.UNAUTHENTICATED: status.HTTP_401_UNAUTHORIZED,
    ErrorCode.FORBIDDEN: status.HTTP_403_FORBIDDEN,
    ErrorCode.NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ErrorCode.METHOD_NOT_ALLOWED: status.HTTP_405_METHOD_NOT_ALLOWED,
    ErrorCode.DUPLICATE_REFERENCE: status.HTTP_409_CONFLICT,
    ErrorCode.AUCTION_NOT_STARTED: status.HTTP_409_CONFLICT,
    ErrorCode.AUCTION_CLOSED: status.HTTP_409_CONFLICT,
    ErrorCode.FORCED_CLOSE_NOT_AFTER_CLOSE: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ErrorCode.BID_NOT_LOWER: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ErrorCode.INTERNAL_ERROR: status.HTTP_500_INTERNAL_SERVER_ERROR,
}


class AppError(Exception):
    """An expected, client-facing error. Raised by services and dependencies."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        status_code: int | None = None,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code or DEFAULT_STATUS[code]
        self.details = details or []
