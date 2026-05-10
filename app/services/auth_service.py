from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import EmailAlreadyRegisteredError, InvalidCredentialsError
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.repositories import user_repository
from app.schemas.auth import AuthSuccessResponse
from app.schemas.user import UserCreate, UserLogin, UserResponse


async def register_user(db: AsyncSession, payload: UserCreate) -> User:
    email = str(payload.email)
    if await user_repository.get_by_email(db, email) is not None:
        raise EmailAlreadyRegisteredError

    user = await user_repository.create(
        db,
        email=email,
        hashed_password=hash_password(payload.password),
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise EmailAlreadyRegisteredError

    await db.refresh(user)
    return user


async def login_user(db: AsyncSession, payload: UserLogin) -> tuple[AuthSuccessResponse, User]:
    user = await user_repository.get_by_email(db, str(payload.email))
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise InvalidCredentialsError

    access_token = create_access_token(user_id=user.id, email=str(user.email))
    return (
        AuthSuccessResponse(
            success=True,
            user=UserResponse.model_validate(user),
            access_token=access_token,
            token_type="bearer",
        ),
        user,
    )
