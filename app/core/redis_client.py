from __future__ import annotations

from collections.abc import AsyncGenerator

import redis.asyncio as redis
import redis.exceptions as redis_exc
from redis.asyncio import Redis

from app.core.config import settings

# Async client retry/connect often raises builtins (e.g. ConnectionRefusedError), not only RedisError.
REDIS_UNAVAILABLE: tuple[type[BaseException], ...] = (
    redis_exc.RedisError,
    ConnectionError,
    TimeoutError,
    OSError,
)

_pool: redis.ConnectionPool | None = None


def _connection_pool() -> redis.ConnectionPool:
    global _pool
    if _pool is None:
        _pool = redis.ConnectionPool(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True,
            socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
        )
    return _pool


async def get_redis() -> AsyncGenerator[Redis, None]:
    """FastAPI dependency: async Redis client per request; pool is shared."""
    client = redis.Redis(connection_pool=_connection_pool())
    try:
        yield client
    finally:
        await client.aclose()


async def ping_redis() -> None:
    """Raise REDIS_UNAVAILABLE if the shared pool cannot reach Redis."""
    client = redis.Redis(connection_pool=_connection_pool())
    try:
        if await client.ping() is not True:
            raise redis_exc.RedisError("unexpected PING response")
    finally:
        await client.aclose()


async def close_redis_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.disconnect()
        _pool = None
