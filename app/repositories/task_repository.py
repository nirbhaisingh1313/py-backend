from __future__ import annotations

from sqlalchemy import select, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.task import Task
from app.schemas.task import TaskCreate, TaskUpdate


async def create_task(db: AsyncSession, payload: TaskCreate, owner_id: int) -> Task:
    row = Task(
        title=payload.title,
        description=payload.description,
        status=payload.status.value,
        priority=payload.priority.value,
        owner_id=owner_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def get_task_by_id(db: AsyncSession, task_id: int) -> Task | None:
    return await db.get(Task, task_id)


async def get_task_by_title_and_owner(
    db: AsyncSession, owner_id: int, title: str
) -> Task | None:

    result = await db.execute(
        select(Task).where(Task.owner_id == owner_id, Task.title == title)
    )

    return result.scalar_one_or_none()


async def get_task_by_id_and_owner(
    db: AsyncSession, task_id: int, owner_id: int
) -> Task | None:

    result = await db.execute(
        select(Task).where(Task.id == task_id, Task.owner_id == owner_id)
    )

    return result.scalar_one_or_none()


async def get_all_tasks(
    db: AsyncSession,
    owner_id: int,
    status: str | None = None,
    priority: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    limit: int = 10,
    offset: int = 0,
) -> list[Task]:

    query = select(Task).where(Task.owner_id == owner_id)

    # FILTERS
    if status:
        query = query.where(Task.status == status)

    if priority:
        query = query.where(Task.priority == priority)

    # SORTING
    allowed_sort_fields = {
        "created_at": Task.created_at,
        "priority": Task.priority,
        "status": Task.status,
    }
    sort_column = allowed_sort_fields.get(sort_by, Task.created_at)

    if sort_order == "desc":
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(asc(sort_column))

    # PAGINATION
    query = query.limit(limit).offset(offset)

    result = await db.execute(query)

    return result.scalars().all()


async def update_task(db: AsyncSession, task_id: int, task: TaskUpdate) -> Task:
    db_task = await db.get(Task, task_id)
    if db_task is None:
        raise ValueError("Task not found")

    if task.title is not None:
        db_task.title = task.title
    if task.description is not None:
        db_task.description = task.description
    if task.status is not None:
        db_task.status = task.status.value
    if task.priority is not None:
        db_task.priority = task.priority.value

    db.add(db_task)
    await db.commit()
    await db.refresh(db_task)
    return db_task


async def delete_task(db: AsyncSession, task_id: int) -> None:
    task = await db.get(Task, task_id)
    if task is None:
        raise ValueError("Task not found")
    await db.delete(task)
    await db.commit()
