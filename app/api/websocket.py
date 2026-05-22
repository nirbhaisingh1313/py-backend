from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import suppress
from datetime import datetime, timezone
from inspect import isawaitable

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.connection_manager import connection_manager, user_events_channel
from app.core.error_logging import log_error, log_redis_failure, log_websocket_disconnect
from app.core.log_context import bind_websocket_context, clear_context
from app.core.redis_client import REDIS_UNAVAILABLE, get_redis
from app.core.security import decode_access_token
from app.db.session import get_db
from app.core.log_context import REQUEST_ID_HEADER
from app.models.user import User
from app.schemas.websocket import WebSocketAcceptedResponse, WebSocketEvent
from app.services import user_service

router = APIRouter(tags=["websocket"])
PING_INTERVAL_SECONDS = 30
PONG_TIMEOUT_SECONDS = 10


def _extract_websocket_token(websocket: WebSocket) -> str | None:
    auth_header = websocket.headers.get("Authorization")
    if auth_header:
        scheme, _, token = auth_header.partition(" ")
        if scheme.lower() == "bearer" and token:
            return token

    return websocket.query_params.get("token") or websocket.query_params.get("access_token")


def _websocket_request_id(websocket: WebSocket) -> str:
    incoming = websocket.headers.get(REQUEST_ID_HEADER)
    if incoming and incoming.strip():
        return incoming.strip()
    return str(uuid.uuid4())


async def _authenticate_websocket_user(
    websocket: WebSocket, db: AsyncSession, redis: Redis
) -> User | None:
    token = _extract_websocket_token(websocket)
    if token is None:
        return None

    try:
        payload = decode_access_token(token)
    except ValueError:
        return None

    user_id = payload.get("user_id")
    if not isinstance(user_id, int):
        return None

    return await user_service.get_user_by_id(db, redis, user_id)


async def _forward_events(websocket: WebSocket, user_id: int, pubsub) -> None:
    while True:
        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
        if message is None or message.get("type") != "message":
            continue

        try:
            payload = json.loads(message["data"])
        except json.JSONDecodeError:
            log_error(
                "Invalid websocket pub/sub payload",
                event="websocket_invalid_payload",
                level=logging.WARNING,
                user_id=user_id,
                raw_payload=message.get("data"),
            )
            continue

        if not await connection_manager.send_to_connection(user_id, websocket, payload):
            raise WebSocketDisconnect()


async def _handle_client_messages(
    websocket: WebSocket, user_id: int, pong_received: asyncio.Event
) -> None:
    while True:
        raw_message = await websocket.receive_text()
        try:
            payload = json.loads(raw_message)
        except json.JSONDecodeError:
            continue

        event = payload.get("event")
        if event == "pong":
            pong_received.set()
        elif event == "ping":
            pong_event = WebSocketEvent(
                event="pong",
                data={"timestamp": datetime.now(timezone.utc).isoformat()},
            )
            await connection_manager.send_to_connection(
                user_id, websocket, pong_event.model_dump(mode="json")
            )


async def _send_heartbeat(
    websocket: WebSocket, user_id: int, pong_received: asyncio.Event
) -> None:
    while True:
        await asyncio.sleep(PING_INTERVAL_SECONDS)
        pong_received.clear()
        sent_at = datetime.now(timezone.utc).isoformat()
        ping_event = WebSocketEvent(event="ping", data={"timestamp": sent_at})

        if not await connection_manager.send_to_connection(
            user_id, websocket, ping_event.model_dump(mode="json")
        ):
            return

        try:
            await asyncio.wait_for(pong_received.wait(), timeout=PONG_TIMEOUT_SECONDS)
        except TimeoutError:
            log_websocket_disconnect(
                user_id=user_id,
                disconnect_type="heartbeat_timeout",
                level=logging.WARNING,
            )
            await connection_manager.disconnect(user_id, websocket)
            with suppress(RuntimeError):
                await websocket.close(code=status.WS_1001_GOING_AWAY)
            return


async def _close_pubsub(pubsub) -> None:
    close = getattr(pubsub, "aclose", None) or getattr(pubsub, "close", None)
    if close is None:
        return

    result = close()
    if isawaitable(result):
        await result


def _disconnect_details(exc: WebSocketDisconnect) -> tuple[int | None, str | None]:
    code = getattr(exc, "code", None)
    reason = getattr(exc, "reason", None)
    return code, reason


@router.websocket("/ws/")
@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> None:
    request_id = _websocket_request_id(websocket)
    current_user = await _authenticate_websocket_user(websocket, db, redis)
    if current_user is None:
        log_error(
            "WebSocket authentication failed",
            event="websocket_auth_failure",
            level=logging.WARNING,
            request_id=request_id,
            endpoint="WS /ws",
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
        return

    bind_websocket_context(
        user_id=current_user.id,
        endpoint="WS /ws",
        request_id=request_id,
    )

    pubsub = redis.pubsub()
    channel = user_events_channel(current_user.id)
    await connection_manager.connect(current_user.id, websocket)
    try:
        await connection_manager.send_to_connection(
            current_user.id,
            websocket,
            WebSocketAcceptedResponse().model_dump(mode="json"),
        )
        await pubsub.subscribe(channel)
        pong_received = asyncio.Event()
        forward_task = asyncio.create_task(
            _forward_events(websocket, current_user.id, pubsub)
        )
        client_task = asyncio.create_task(
            _handle_client_messages(websocket, current_user.id, pong_received)
        )
        heartbeat_task = asyncio.create_task(
            _send_heartbeat(websocket, current_user.id, pong_received)
        )
        done, pending = await asyncio.wait(
            {forward_task, client_task, heartbeat_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        for task in done:
            with suppress(WebSocketDisconnect):
                await task

        for task in done:
            if task.cancelled():
                continue
            exc = task.exception()
            if isinstance(exc, WebSocketDisconnect):
                code, reason = _disconnect_details(exc)
                log_websocket_disconnect(
                    user_id=current_user.id,
                    code=code,
                    reason=reason,
                    disconnect_type="client_disconnect",
                )
    except WebSocketDisconnect as exc:
        code, reason = _disconnect_details(exc)
        log_websocket_disconnect(
            user_id=current_user.id,
            code=code,
            reason=reason,
            disconnect_type="client_disconnect",
        )
    except REDIS_UNAVAILABLE as exc:
        log_redis_failure(
            "websocket_pubsub",
            exc,
            level=logging.ERROR,
            user_id=current_user.id,
        )
        with suppress(RuntimeError):
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
    except Exception as exc:
        log_error(
            "WebSocket handler failed",
            event="websocket_failure",
            exc=exc,
            user_id=current_user.id,
        )
        with suppress(RuntimeError):
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
    finally:
        await connection_manager.disconnect(current_user.id, websocket)
        with suppress(*REDIS_UNAVAILABLE):
            await pubsub.unsubscribe(channel)
        with suppress(*REDIS_UNAVAILABLE):
            await _close_pubsub(pubsub)
        clear_context()
