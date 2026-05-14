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
        self._send_locks: dict[WebSocket, asyncio.Lock] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._active_connections[user_id].add(websocket)
            self._send_locks[websocket] = asyncio.Lock()

    async def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            connections = self._active_connections.get(user_id)
            if connections is None:
                return

            connections.discard(websocket)
            if not connections:
                self._active_connections.pop(user_id, None)
            self._send_locks.pop(websocket, None)

    async def send_to_connection(
        self, user_id: int, websocket: WebSocket, payload: Mapping[str, Any]
    ) -> bool:
        async with self._lock:
            is_active = websocket in self._active_connections.get(user_id, set())
            send_lock = self._send_locks.get(websocket)

        if not is_active or send_lock is None:
            return False

        try:
            async with send_lock:
                async with self._lock:
                    is_active = websocket in self._active_connections.get(user_id, set())
                if not is_active:
                    return False

                await websocket.send_json(dict(payload))
            return True
        except (RuntimeError, WebSocketDisconnect):
            await self.disconnect(user_id, websocket)
            return False
        except Exception:
            logger.exception("Failed to send websocket message to user_id=%s", user_id)
            await self.disconnect(user_id, websocket)
            return False

    async def send_to_user(self, user_id: int, payload: Mapping[str, Any]) -> None:
        async with self._lock:
            connections = list(self._active_connections.get(user_id, set()))

        for websocket in connections:
            await self.send_to_connection(user_id, websocket, payload)

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
