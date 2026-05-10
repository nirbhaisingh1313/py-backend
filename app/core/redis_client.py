from __future__ import annotations
from collections.abc import AsyncGenerator
import redis.asyncio as redis 
from redis.asyncio import Redis
from app.core.config import settings

_pool: redis.ConnectionPool | None = None

def _connection_pool() -> redis.ConnectionPool:
    global _pool
    if _pool is None:
        _pool = redis.ConnectionPool(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True,
        )
    return _pool

async def get_redis() -> AsyncGenerator[Redis, None]:
    """FastAPI dependency: async Redis client per request; pool is shared."""
    client = redis.Redis(connection_pool=_connection_pool())
    try:
        yield client
    finally:
        await client.aclose()

async def close_redis() -> None:
    """FastAPI dependency: async Redis client per request; pool is shared."""
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None