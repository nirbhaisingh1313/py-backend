from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy import text

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.redis_client import REDIS_UNAVAILABLE, ping_redis
from app.db.session import AsyncSessionLocal
from app.schemas.health import ComponentHealth

CELERY_INSPECT_TIMEOUT_SECONDS = 2.0


@dataclass(frozen=True)
class ReadinessReport:
    checks: dict[str, ComponentHealth]

    @property
    def is_ready(self) -> bool:
        return all(check.status == "ok" for check in self.checks.values())


async def check_database() -> ComponentHealth:
    if not settings.DATABASE_URL:
        return ComponentHealth(
            status="unavailable", detail="DATABASE_URL is not configured"
        )

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return ComponentHealth(status="ok")
    except Exception as exc:
        return ComponentHealth(status="unavailable", detail=str(exc))


async def check_redis() -> ComponentHealth:
    try:
        await ping_redis()
        return ComponentHealth(status="ok")
    except REDIS_UNAVAILABLE as exc:
        return ComponentHealth(status="unavailable", detail=str(exc))


def _check_celery_workers_sync() -> ComponentHealth:
    try:
        inspector = celery_app.control.inspect(
            timeout=CELERY_INSPECT_TIMEOUT_SECONDS
        )
        ping_response = inspector.ping()
        if not ping_response:
            return ComponentHealth(
                status="unavailable",
                detail="no Celery workers responded to ping",
            )
        worker_count = len(ping_response)
        return ComponentHealth(status="ok", detail=f"{worker_count} worker(s) online")
    except Exception as exc:
        return ComponentHealth(status="unavailable", detail=str(exc))


async def check_celery_workers() -> ComponentHealth:
    return await asyncio.to_thread(_check_celery_workers_sync)


async def run_readiness_checks() -> ReadinessReport:
    database, redis_health, celery = await asyncio.gather(
        check_database(),
        check_redis(),
        check_celery_workers(),
    )
    return ReadinessReport(
        checks={
            "database": database,
            "redis": redis_health,
            "celery_worker": celery,
        }
    )
