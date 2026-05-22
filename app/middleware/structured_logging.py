from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.log_context import REQUEST_ID_HEADER, bind_http_context, clear_context
from app.core.logging_setup import get_request_logger
from app.core.security import decode_access_token

logger = get_request_logger()

def _resolve_request_id(request: Request) -> str:
    incoming = request.headers.get(REQUEST_ID_HEADER)
    if incoming and incoming.strip():
        return incoming.strip()
    return str(uuid.uuid4())


def _user_id_from_request(request: Request) -> int | None:
    state_user_id = getattr(request.state, "user_id", None)
    if isinstance(state_user_id, int):
        return state_user_id

    auth = request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        return None

    token = auth.split(" ", 1)[1].strip()
    if not token:
        return None

    try:
        payload = decode_access_token(token)
    except ValueError:
        return None

    user_id = payload.get("user_id")
    return user_id if isinstance(user_id, int) else None


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = _resolve_request_id(request)
        request.state.request_id = request_id
        endpoint = f"{request.method} {request.url.path}"

        try:
            bind_http_context(
                request_id=request_id,
                endpoint=endpoint,
                user_id=_user_id_from_request(request),
            )

            started = time.perf_counter()
            response = await call_next(request)
            duration_s = time.perf_counter() - started

            user_id = _user_id_from_request(request)
            bind_http_context(
                request_id=request_id,
                endpoint=endpoint,
                user_id=user_id,
            )

            logger.info(
                "request completed",
                extra={
                    "request_id": request_id,
                    "endpoint": endpoint,
                    "user_id": user_id,
                    "status_code": response.status_code,
                    "duration": round(duration_s, 6),
                },
            )

            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            clear_context()
