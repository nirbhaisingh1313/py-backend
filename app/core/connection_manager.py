from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


def user_events_channel(user_id: int) -> str:
    return f"websocket:user:{user_id}:events"


class ConnectionManager:
    def __init__(self) -> None:
        self._active_connections: dict[int, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._active_connections[user_id].add(websocket)

    async def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            connections = self._active_connections.get(user_id)
            if connections is None:
                return

            connections.discard(websocket)
            if not connections:
                self._active_connections.pop(user_id, None)

    async def send_to_user(self, user_id: int, payload: Mapping[str, Any]) -> None:
        async with self._lock:
            connections = list(self._active_connections.get(user_id, set()))

        stale_connections: list[WebSocket] = []
        for websocket in connections:
            try:
                await websocket.send_json(dict(payload))
            except (RuntimeError, WebSocketDisconnect):
                stale_connections.append(websocket)
            except Exception:
                logger.exception("Failed to send websocket message to user_id=%s", user_id)
                stale_connections.append(websocket)

        for websocket in stale_connections:
            await self.disconnect(user_id, websocket)

    async def broadcast(self, payload: Mapping[str, Any]) -> None:
        async with self._lock:
            user_ids = list(self._active_connections)

        for user_id in user_ids:
            await self.send_to_user(user_id, payload)

    async def active_connections_count(self) -> int:
        async with self._lock:
            return sum(len(connections) for connections in self._active_connections.values())

    async def user_connections_count(self, user_id: int) -> int:
        async with self._lock:
            return len(self._active_connections.get(user_id, set()))


connection_manager = ConnectionManager()
