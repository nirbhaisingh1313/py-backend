from __future__ import annotations

import json
import logging
from typing import Any, Literal

from fastapi import HTTPException
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.connection_manager import user_events_channel
from app.core.redis_client import REDIS_UNAVAILABLE
from app.repositories import task_repository
from app.schemas.task import TaskCreate, TaskResponse, TaskUpdate
from app.schemas.websocket import WebSocketEvent

logger = logging.getLogger(__name__)


def _task_list_cache_key(
    user_id: int,
    status: str | None,
    priority: str | None,
    sort_by: str,
    sort_order: str,
    limit: int,
    offset: int,
) -> str:
    return (
        f"tasks:user:{user_id}:status:{status!s}:priority:{priority!s}:"
        f"sort:{sort_by}:{sort_order}:limit:{limit}:offset:{offset}"
    )


def _task_list_cache_ttl_seconds() -> int:
    return 300


def _serialize_task_list(tasks: list[TaskResponse]) -> str:
    return json.dumps([t.model_dump(mode="json") for t in tasks])


def _deserialize_task_list(raw: str) -> list[TaskResponse]:
    data = json.loads(raw)
    return [TaskResponse.model_validate(item) for item in data]


async def set_tasks_list_cache(
    redis: Redis,
    tasks: list[TaskResponse],
    user_id: int,
    status: str | None,
    priority: str | None,
    sort_by: str,
    sort_order: str,
    limit: int,
    offset: int,
) -> None:
    key = _task_list_cache_key(user_id, status, priority, sort_by, sort_order, limit, offset)
    try:
        await redis.set(key, _serialize_task_list(tasks), ex=_task_list_cache_ttl_seconds())
    except REDIS_UNAVAILABLE as exc:
        logger.warning("Redis set_tasks_list_cache failed: %s", exc)


async def get_tasks_list_cache(
    redis: Redis,
    user_id: int,
    status: str | None,
    priority: str | None,
    sort_by: str,
    sort_order: str,
    limit: int,
    offset: int,
) -> list[TaskResponse] | None:
    key = _task_list_cache_key(user_id, status, priority, sort_by, sort_order, limit, offset)
    try:
        raw = await redis.get(key)
        if raw is None:
            return None
        return _deserialize_task_list(raw)
    except REDIS_UNAVAILABLE as exc:
        logger.warning("Redis get_tasks_list_cache failed: %s", exc)
        return None


async def invalidate_user_tasks_list_cache(redis: Redis, user_id: int) -> None:
    pattern = f"tasks:user:{user_id}:*"
    try:
        keys = await redis.keys(pattern)
        if keys:
            await redis.delete(*keys)
    except REDIS_UNAVAILABLE as exc:
        logger.warning("Redis invalidate_user_tasks_list_cache failed: %s", exc)


async def publish_task_update(
    redis: Redis,
    user_id: int,
    action: Literal["created", "updated", "deleted"],
    *,
    task: TaskResponse | None = None,
    task_id: int | None = None,
) -> None:
    data: dict[str, Any] = {"action": action}
    if task is not None:
        data["task"] = task.model_dump(mode="json")
    if task_id is not None:
        data["task_id"] = task_id

    event = WebSocketEvent(event="tasks", data=data)
    try:
        await redis.publish(
            user_events_channel(user_id),
            event.model_dump_json(exclude_none=True),
        )
    except REDIS_UNAVAILABLE as exc:
        logger.warning("Redis publish_task_update failed: %s", exc)


async def create_task_service(
    db: AsyncSession, redis: Redis, task: TaskCreate, owner_id: int
) -> TaskResponse:
    if (
        await task_repository.get_task_by_title_and_owner(db, owner_id, task.title)
        is not None
    ):
        raise HTTPException(
            status_code=400, detail="A task with this title already exists"
        )

    row = await task_repository.create_task(db, task, owner_id)
    await invalidate_user_tasks_list_cache(redis, owner_id)
    response = TaskResponse.model_validate(row)
    await publish_task_update(redis, owner_id, "created", task=response)
    return response


async def get_task_by_id_service(
    db: AsyncSession, task_id: int, owner_id: int
) -> TaskResponse:
    row = await task_repository.get_task_by_id_and_owner(db, task_id, owner_id)
    if row is None:
        raise HTTPException(
            status_code=404, detail="A task with this id does not exist"
        )
    return TaskResponse.model_validate(row)


async def get_all_tasks_service(
    db: AsyncSession,
    redis: Redis,
    owner_id: int,
    status: str | None = None,
    priority: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    limit: int = 10,
    offset: int = 0,
) -> list[TaskResponse]:
    cached = await get_tasks_list_cache(
        redis, owner_id, status, priority, sort_by, sort_order, limit, offset
    )
    if cached is not None:
        return cached

    rows = await task_repository.get_all_tasks(
        db, owner_id, status, priority, sort_by, sort_order, limit, offset
    )
    tasks = [TaskResponse.model_validate(r) for r in rows]
    await set_tasks_list_cache(
        redis, tasks, owner_id, status, priority, sort_by, sort_order, limit, offset
    )
    return tasks


async def update_task_service(
    db: AsyncSession, redis: Redis, task_id: int, task: TaskUpdate, owner_id: int
) -> TaskResponse:
    has_ownership = await task_repository.get_task_by_id_and_owner(
        db, task_id, owner_id
    )
    if has_ownership is None:
        raise HTTPException(
            status_code=403, detail="You are not allowed to update this task"
        )

    row = await task_repository.update_task(db, task_id, task)
    await invalidate_user_tasks_list_cache(redis, owner_id)
    response = TaskResponse.model_validate(row)
    await publish_task_update(redis, owner_id, "updated", task=response)
    return response


async def delete_task_service(db: AsyncSession, redis: Redis, task_id: int, owner_id: int) -> None:
    has_ownership = await task_repository.get_task_by_id_and_owner(db, task_id, owner_id)
    if has_ownership is None:
        raise HTTPException(
            status_code=403, detail="You are not allowed to delete this task"
        )
    await task_repository.delete_task(db, task_id)
    await invalidate_user_tasks_list_cache(redis, owner_id)
    await publish_task_update(redis, owner_id, "deleted", task_id=task_id)
