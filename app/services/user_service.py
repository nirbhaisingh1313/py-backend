from __future__ import annotations

import logging

import redis.exceptions
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User
from app.repositories import user_repository
from app.schemas.user import CachedUserSnapshot

logger = logging.getLogger(__name__)


def _user_cache_key(user_id: int) -> str:
    return f"user:auth:{user_id}"


def _cache_ttl_seconds() -> int:
    return max(60, settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)


def user_from_snapshot(snapshot: CachedUserSnapshot) -> User:
    """Detached User row for read-only use (e.g. `current_user.id`). Not loaded from DB session."""
    return User(
        id=snapshot.id,
        email=str(snapshot.email),
        name=snapshot.name,
        created_at=snapshot.created_at,
        hashed_password="",
    )


async def set_user_cache(redis: Redis, user: User) -> None:
    snapshot = CachedUserSnapshot.model_validate(user)
    try:
        await redis.set(
            _user_cache_key(user.id),
            snapshot.model_dump_json(),
            ex=_cache_ttl_seconds(),
        )
    except redis.exceptions.RedisError as exc:
        logger.warning("Redis set_user_cache failed: %s", exc)


async def invalidate_user_cache(redis: Redis, user_id: int) -> None:
    try:
        await redis.delete(_user_cache_key(user_id))
    except redis.exceptions.RedisError as exc:
        logger.warning("Redis invalidate_user_cache failed: %s", exc)


async def get_user_by_id(db: AsyncSession, redis: Redis, user_id: int) -> User | None:
    key = _user_cache_key(user_id)
    try:
        cached = await redis.get(key)
    except redis.exceptions.RedisError as exc:
        logger.warning("Redis get_user_cache failed, falling back to DB: %s", exc)
        cached = None

    if cached:
        snapshot = CachedUserSnapshot.model_validate_json(cached)
        return user_from_snapshot(snapshot)

    user = await user_repository.get_by_id(db, user_id)
    if user is not None:
        await set_user_cache(redis, user)
    return user
