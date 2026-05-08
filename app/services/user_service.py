from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories import user_repository


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    return await user_repository.get_by_id(db, user_id)
