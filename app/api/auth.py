from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.errors import EmailAlreadyRegisteredError, InvalidCredentialsError
from app.core.redis_client import get_redis
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import AuthSuccessResponse
from app.schemas.user import UserCreate, UserLogin, UserResponse
from app.services import auth_service, user_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
async def register(
    request: Request,
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> User:
    client_ip = security.get_client_ip(request)
    await security.check_rate_limit(
        redis, f"auth_rate_limit:register:{client_ip}", limit=50, seconds=60
    )
    try:
        return await auth_service.register_user(db, payload)
    except EmailAlreadyRegisteredError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )


@router.post("/login", response_model=AuthSuccessResponse)
async def login(
    request: Request,
    payload: UserLogin,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> AuthSuccessResponse:
    client_ip = security.get_client_ip(request)
    await security.check_rate_limit(
        redis, f"auth_rate_limit:login:{client_ip}", limit=50, seconds=60
    )
    try:
        response, user = await auth_service.login_user(db, payload)
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    await user_service.set_user_cache(redis, user)
    return response
