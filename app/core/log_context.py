from __future__ import annotations

import contextvars
from typing import Any

REQUEST_ID_HEADER = "X-Request-ID"

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)
_endpoint: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "endpoint", default=None
)
_user_id: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "user_id", default=None
)
_connection: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "connection", default=None
)


def bind_http_context(
    *,
    request_id: str,
    endpoint: str,
    user_id: int | None = None,
) -> None:
    _request_id.set(request_id)
    _endpoint.set(endpoint)
    _user_id.set(user_id)
    _connection.set("http")


def bind_websocket_context(
    *,
    user_id: int | None,
    endpoint: str = "WS /ws",
    request_id: str | None = None,
) -> None:
    if request_id is not None:
        _request_id.set(request_id)
    _endpoint.set(endpoint)
    _user_id.set(user_id)
    _connection.set("websocket")


def get_bound_context() -> dict[str, Any]:
    context: dict[str, Any] = {}
    request_id = _request_id.get()
    endpoint = _endpoint.get()
    user_id = _user_id.get()
    connection = _connection.get()

    if request_id is not None:
        context["request_id"] = request_id
    if endpoint is not None:
        context["endpoint"] = endpoint
    if user_id is not None:
        context["user_id"] = user_id
    if connection is not None:
        context["connection"] = connection
    return context


def clear_context() -> None:
    for var in (_request_id, _endpoint, _user_id, _connection):
        var.set(None)
