from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "backend",
    broker=settings.celery_broker_url(),
    include=["app.tasks.email_tasks"],
)

celery_app.conf.update(
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
)
