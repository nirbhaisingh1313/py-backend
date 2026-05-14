from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WebSocketAcceptedResponse(BaseModel):
    event: str = "connection"
    data: dict[str, str] = Field(
        default_factory=lambda: {
            "status": "accepted",
            "message": "Connected to live updates",
        }
    )


class WebSocketEvent(BaseModel):
    event: str
    data: dict[str, Any]
