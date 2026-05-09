from __future__ import annotations
from typing import Literal
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.task import (
    TaskCreate,
    TaskDeleteSuccessResponse,
    TaskUpdate,
    TaskSuccessResponse,
    TasksListSuccessResponse,
)
from app.services import task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post(
    "/", response_model=TaskSuccessResponse, status_code=status.HTTP_201_CREATED
)
async def create_task(
    payload: TaskCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskSuccessResponse:
    task = await task_service.create_task_service(db, payload, current_user.id)
    return TaskSuccessResponse(success=True, task=task)


@router.get("/{task_id}", response_model=TaskSuccessResponse)
async def get_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskSuccessResponse:
    task = await task_service.get_task_by_id_service(db, task_id, current_user.id)
    return TaskSuccessResponse(success=True, task=task)


@router.get("/", response_model=TasksListSuccessResponse)
async def get_all_tasks(
    status: str | None = None,
    priority: str | None = None,
    sort_by: str = "created_at",
    sort_order: Literal["asc", "desc"] = "desc",
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TasksListSuccessResponse:
    tasks = await task_service.get_all_tasks_service(
        db, current_user.id, status, priority, sort_by, sort_order, limit, offset
    )
    return TasksListSuccessResponse(success=True, tasks=tasks)


@router.put("/{task_id}", response_model=TaskSuccessResponse)
async def update_task(
    task_id: int,
    payload: TaskUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskSuccessResponse:
    task = await task_service.update_task_service(db, task_id, payload, current_user.id)
    return TaskSuccessResponse(success=True, task=task)


@router.delete("/{task_id}", response_model=TaskDeleteSuccessResponse)
async def delete_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskDeleteSuccessResponse:
    await task_service.delete_task_service(db, task_id, current_user.id)
    return TaskDeleteSuccessResponse(success=True, message="Task deleted successfully")
