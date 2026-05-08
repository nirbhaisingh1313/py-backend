from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from passlib.context import CryptContext

from jose import jwt, JWTError

from app.core.config import settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(plain_password, hashed_password)


def create_access_token(*, user_id: int, email: str, expires_in_minutes: int | None = None) -> str:
    if not settings.SECRET_KEY:
        raise RuntimeError("SECRET_KEY is not set")

    expire_minutes = expires_in_minutes if expires_in_minutes is not None else settings.ACCESS_TOKEN_EXPIRE_MINUTES
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
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise ValueError("Invalid token") from exc

    return payload

