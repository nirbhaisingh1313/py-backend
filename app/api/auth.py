from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import AuthSuccessResponse
from app.schemas.user import UserCreate, UserLogin, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)) -> UserResponse:
    existing = await db.scalar(select(User).where(User.email == str(payload.email)))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(email=str(payload.email), hashed_password=hash_password(payload.password))
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    await db.refresh(user)
    return user


@router.post("/login", response_model=AuthSuccessResponse)
async def login(payload: UserLogin, db: AsyncSession = Depends(get_db)) -> AuthSuccessResponse:
    user = await db.scalar(select(User).where(User.email == str(payload.email)))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    access_token = create_access_token(user_id=user.id, email=str(user.email))
    return AuthSuccessResponse(
        success=True,
        user=UserResponse.model_validate(user),
        access_token=access_token,
        token_type="bearer",
    )

