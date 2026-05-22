from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError

from app.core.log_context import bind_http_context, get_bound_context
from app.core.logging_setup import get_error_logger

logger = get_error_logger()


def _context_from_request(request: Request) -> dict[str, Any]:
    request_id = getattr(request.state, "request_id", None)
    user_id = getattr(request.state, "user_id", None)
    endpoint = f"{request.method} {request.url.path}"

    if request_id is not None:
        bind_http_context(
            request_id=str(request_id),
            endpoint=endpoint,
            user_id=user_id if isinstance(user_id, int) else None,
        )
    return get_bound_context()


def log_error(
    message: str,
    *,
    event: str,
    exc: BaseException | None = None,
    level: int = logging.ERROR,
    **fields: Any,
) -> None:
    extra = {**get_bound_context(), **fields, "event": event}
    if exc is not None:
        extra["error_type"] = type(exc).__name__
        extra["error_message"] = str(exc)
    logger.log(level, message, exc_info=exc, extra=extra)


def log_redis_failure(
    operation: str,
    exc: BaseException,
    *,
    level: int = logging.WARNING,
    **fields: Any,
) -> None:
    log_error(
        f"Redis operation failed: {operation}",
        event="redis_failure",
        exc=exc,
        level=level,
        operation=operation,
        **fields,
    )


def log_validation_error(
    exc: RequestValidationError,
    request: Request,
) -> None:
    _context_from_request(request)
    errors = exc.errors()
    log_error(
        "Request validation failed",
        event="validation_failure",
        level=logging.WARNING,
        validation_errors=errors,
        error_count=len(errors),
    )


def log_http_exception(request: Request, status_code: int, detail: Any) -> None:
    _context_from_request(request)
    level = logging.ERROR if status_code >= 500 else logging.WARNING
    log_error(
        "HTTP exception",
        event="http_exception",
        level=level,
        status_code=status_code,
        detail=detail,
    )


def log_websocket_disconnect(
    *,
    user_id: int | None,
    code: int | None = None,
    reason: str | None = None,
    disconnect_type: str = "client_disconnect",
    level: int = logging.INFO,
    exc: BaseException | None = None,
    **fields: Any,
) -> None:
    log_error(
        "WebSocket disconnected",
        event="websocket_disconnect",
        exc=exc,
        level=level,
        user_id=user_id,
        disconnect_type=disconnect_type,
        close_code=code,
        close_reason=reason,
        **fields,
    )

