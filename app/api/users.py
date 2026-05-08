from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.user import UserResponse, UserSuccessResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserSuccessResponse)
async def read_current_user(current_user: User = Depends(get_current_user)) -> UserSuccessResponse:
    return UserSuccessResponse(user=UserResponse.model_validate(current_user))
