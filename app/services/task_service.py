from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories import task_repository
from app.schemas.task import TaskCreate, TaskUpdate, TaskResponse


async def create_task_service(
    db: AsyncSession, task: TaskCreate, owner_id: int
) -> TaskResponse:

    if (
        await task_repository.get_task_by_title_and_owner(db, owner_id, task.title)
        is not None
    ):
        raise HTTPException(
            status_code=400, detail="A task with this title already exists"
        )

    task = await task_repository.create_task(db, task, owner_id)

    return TaskResponse.model_validate(task)


async def get_task_by_id_service(
    db: AsyncSession, task_id: int, owner_id: int
) -> TaskResponse:
    task = await task_repository.get_task_by_id_and_owner(db, task_id, owner_id)
    if task is None:
        raise HTTPException(
            status_code=404, detail="A task with this id does not exist"
        )
    return TaskResponse.model_validate(task)


async def get_all_tasks_service(
    db: AsyncSession,
    owner_id: int,
    status: str | None = None,
    priority: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    limit: int = 10,
    offset: int = 0,
) -> list[TaskResponse]:
    tasks = await task_repository.get_all_tasks(
        db, owner_id, status, priority, sort_by, sort_order, limit, offset
    )
    return [TaskResponse.model_validate(task) for task in tasks]


async def update_task_service(
    db: AsyncSession, task_id: int, task: TaskUpdate, owner_id: int
) -> TaskResponse:

    has_ownership = await task_repository.get_task_by_id_and_owner(
        db, task_id, owner_id
    )
    if has_ownership is None:
        raise HTTPException(
            status_code=403, detail="You are not allowed to update this task"
        )

    task = await task_repository.update_task(db, task_id, task)
    return TaskResponse.model_validate(task)


async def delete_task_service(db: AsyncSession, task_id: int, owner_id: int) -> None:
    has_ownership = await task_repository.get_task_by_id_and_owner(db, task_id, owner_id)
    if has_ownership is None:
        raise HTTPException(
            status_code=403, detail="You are not allowed to delete this task"
        )
    await task_repository.delete_task(db, task_id)
    return None