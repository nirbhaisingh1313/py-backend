from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ComponentHealth(BaseModel):
    status: Literal["ok", "unavailable"]
    detail: str | None = None


class LivenessResponse(BaseModel):
    status: Literal["alive"] = "alive"


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, ComponentHealth] = Field(default_factory=dict)
