from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

_LOG_RECORD_RESERVED = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
) | frozenset({"message", "asctime"})


class JsonFormatter(logging.Formatter):
    """One JSON object per line for machine-readable logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _LOG_RECORD_RESERVED and not key.startswith("_"):
                payload[key] = value

        if record.exc_info and not payload.get("stack_trace"):
            payload["stack_trace"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def _configure_named_logger(name: str, handler: logging.Handler, level: int) -> None:
    log = logging.getLogger(name)
    log.setLevel(level)
    log.handlers.clear()
    log.addHandler(handler)
    log.propagate = False


def configure_logging(level: int = logging.INFO) -> None:
    """Configure JSON stdout loggers for HTTP access and errors."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(JsonFormatter())

    _configure_named_logger("app.request", handler, level)
    _configure_named_logger("app.error", handler, level)


def get_request_logger() -> logging.Logger:
    return logging.getLogger("app.request")


def get_error_logger() -> logging.Logger:
    return logging.getLogger("app.error")
