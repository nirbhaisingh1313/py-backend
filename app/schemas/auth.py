from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.schemas.user import UserResponse


class AuthSuccessResponse(BaseModel):
    success: bool = True
    user: UserResponse

    model_config = ConfigDict(from_attributes=True)

