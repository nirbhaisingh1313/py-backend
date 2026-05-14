from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"

class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class TaskBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    status: TaskStatus
    priority: TaskPriority

class TaskCreate(TaskBase):
    pass

class TaskUpdate(BaseModel):
    title: str | None = Field(min_length=1, max_length=200)
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None

class TaskResponse(TaskBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskSuccessResponse(BaseModel):
    success: bool = True
    task: TaskResponse

    model_config = ConfigDict(from_attributes=True)

class TasksListSuccessResponse(BaseModel):
    success: bool = True
    tasks: list[TaskResponse]

    model_config = ConfigDict(from_attributes=True)

class TaskDeleteSuccessResponse(BaseModel):
    success: bool = True
    message: str = "Task deleted successfully"

    model_config = ConfigDict(from_attributes=True)