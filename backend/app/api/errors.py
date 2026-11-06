"""Exception handlers that turn every error into the standard JSON envelope."""

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import AppError, ErrorCode
from app.schemas.common import error_payload

logger = logging.getLogger(__name__)

_HTTP_STATUS_CODES = {
    status.HTTP_404_NOT_FOUND: ErrorCode.NOT_FOUND,
    status.HTTP_405_METHOD_NOT_ALLOWED: ErrorCode.METHOD_NOT_ALLOWED,
    status.HTTP_401_UNAUTHORIZED: ErrorCode.UNAUTHENTICATED,
    status.HTTP_403_FORBIDDEN: ErrorCode.FORBIDDEN,
}

# Location prefixes that are noise for clients ("body.bid_close_at" -> "bid_close_at").
_LOC_PREFIXES = {"body", "query", "path", "header"}


def _field_name(loc: tuple[Any, ...]) -> str | None:
    parts = [str(p) for p in loc if p not in _LOC_PREFIXES]
    return ".".join(parts) or None


def _validation_code(errors: list[dict[str, Any]]) -> ErrorCode:
    """A validator can raise PydanticCustomError("<error_code_in_lowercase>", ...) to surface a
    specific error code (e.g. FORCED_CLOSE_NOT_AFTER_CLOSE) instead of VALIDATION_ERROR."""
    for err in errors:
        candidate = str(err.get("type", "")).upper()
        if candidate in ErrorCode.__members__:
            return ErrorCode(candidate)
    return ErrorCode.VALIDATION_ERROR


async def _app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(exc.code, exc.message, exc.details),
    )


async def _validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = list(exc.errors())
    code = _validation_code(errors)
    details = [{"field": _field_name(tuple(e.get("loc", ()))), "message": e["msg"]} for e in errors]
    message = details[0]["message"] if code != ErrorCode.VALIDATION_ERROR else "Invalid request"
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=error_payload(code, message, details),
    )


async def _http_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = _HTTP_STATUS_CODES.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(code, str(exc.detail)),
        headers=getattr(exc, "headers", None),
    )


async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_payload(ErrorCode.INTERNAL_ERROR, "Something went wrong"),
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)
