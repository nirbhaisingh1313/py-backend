from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


def _request_timing_logger() -> logging.Logger:
    """Own handler: under Uvicorn the root logger is often WARNING, so INFO never prints."""
    log = logging.getLogger("app.request")
    log.setLevel(logging.INFO)
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(message)s"))
        log.addHandler(handler)
        log.propagate = False
    return log


logger = _request_timing_logger()


class RequestTimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started) * 1000
        logger.info("%s %s -> %.0fms", request.method, request.url.path, duration_ms)
        return response
