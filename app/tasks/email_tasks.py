from __future__ import annotations

import logging
import time

from app.core.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="email.send_welcome")
def send_welcome_email(user_id: int, email: str) -> None:
    """Simulated async welcome email (no SMTP)."""
    time.sleep(0.5)
    logger.info(
        "Welcome email sent (simulated) user_id=%s email=%s",
        user_id,
        email,
    )
