from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from inspect import isawaitable

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.connection_manager import connection_manager, user_events_channel
from app.core.redis_client import REDIS_UNAVAILABLE, get_redis
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User
from app.schemas.websocket import WebSocketAcceptedResponse
from app.services import user_service

router = APIRouter(tags=["websocket"])
logger = logging.getLogger(__name__)


def _extract_websocket_token(websocket: WebSocket) -> str | None:
    auth_header = websocket.headers.get("Authorization")
    if auth_header:
        scheme, _, token = auth_header.partition(" ")
        if scheme.lower() == "bearer" and token:
            return token

    return websocket.query_params.get("token") or websocket.query_params.get("access_token")


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


async def _forward_events(websocket: WebSocket, pubsub) -> None:
    while True:
        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
        if message is None or message.get("type") != "message":
            continue

        try:
            payload = json.loads(message["data"])
        except json.JSONDecodeError:
            logger.warning("Invalid websocket payload: %s", message["data"])
            continue

        await websocket.send_json(payload)


async def _wait_for_disconnect(websocket: WebSocket) -> None:
    while True:
        await websocket.receive_text()


async def _close_pubsub(pubsub) -> None:
    close = getattr(pubsub, "aclose", None) or getattr(pubsub, "close", None)
    if close is None:
        return

    result = close()
    if isawaitable(result):
        await result


@router.websocket("/ws/")
@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> None:
    current_user = await _authenticate_websocket_user(websocket, db, redis)
    if current_user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
        return

    pubsub = redis.pubsub()
    channel = user_events_channel(current_user.id)
    await connection_manager.connect(current_user.id, websocket)
    try:
        await websocket.send_json(WebSocketAcceptedResponse().model_dump(mode="json"))
        await pubsub.subscribe(channel)
        forward_task = asyncio.create_task(_forward_events(websocket, pubsub))
        disconnect_task = asyncio.create_task(_wait_for_disconnect(websocket))
        done, pending = await asyncio.wait(
            {forward_task, disconnect_task}, return_when=asyncio.FIRST_COMPLETED
        )

        for task in pending:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        for task in done:
            with suppress(WebSocketDisconnect):
                await task
    except WebSocketDisconnect:
        return
    except REDIS_UNAVAILABLE as exc:
        logger.warning("Websocket Redis stream failed: %s", exc)
        with suppress(RuntimeError):
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
    except Exception:
        logger.exception("Websocket failed")
        with suppress(RuntimeError):
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
    finally:
        await connection_manager.disconnect(current_user.id, websocket)
        with suppress(*REDIS_UNAVAILABLE):
            await pubsub.unsubscribe(channel)
        with suppress(*REDIS_UNAVAILABLE):
            await _close_pubsub(pubsub)
