from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, Request, status
from passlib.context import CryptContext

from jose import jwt, JWTError
from redis.asyncio import Redis

from app.core.config import settings
from app.core.error_logging import log_redis_failure
from app.core.redis_client import REDIS_UNAVAILABLE

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_client_ip(request: Request) -> str:
    """Best-effort client IP; prefers X-Forwarded-For when behind a trusted proxy."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client:
        return request.client.host
    return "unknown"


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    *, user_id: int, email: str, expires_in_minutes: int | None = None
) -> str:
    if not settings.SECRET_KEY:
        raise RuntimeError("SECRET_KEY is not set")

    expire_minutes = (
        expires_in_minutes
        if expires_in_minutes is not None
        else settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    expire_at = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)

    payload: dict[str, Any] = {
        "user_id": user_id,
        "email": email,
        "exp": expire_at,
    }

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    if not settings.SECRET_KEY:
        raise RuntimeError("SECRET_KEY is not set")

    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError as exc:
        raise ValueError("Invalid token") from exc

    return payload


async def check_rate_limit(
    redis_client: Redis, key: str, limit: int = 5, seconds: int = 60
) -> bool:
    try:
        requests = await redis_client.incr(key)
        if requests == 1:
            await redis_client.expire(key, seconds)

        if requests > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
            )
    except REDIS_UNAVAILABLE as exc:
        # Fail open so the API stays usable when Redis is down (no long hangs).
        log_redis_failure("rate_limit", exc, rate_limit_key=key)

    return True
