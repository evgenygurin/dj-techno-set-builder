"""Centralized logging configuration.

* **JSON** format when ``app_env`` ∈ {staging, prod}
* **Human-readable** format when ``debug=True`` or ``app_env == dev``
* Injects ``request_id`` into every log record via a filter.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import TYPE_CHECKING

from app.core.middleware.request_id import request_id_ctx

if TYPE_CHECKING:
    pass


class RequestIdFilter(logging.Filter):
    """Attach current ``request_id`` to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get("")
        return True


class JSONFormatter(logging.Formatter):
    """Emit log records as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", ""),
        }
        if record.exc_info and record.exc_info[1] is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(*, log_level: str = "INFO", json_output: bool = False) -> None:
    """Configure the root logger once at startup."""
    root = logging.getLogger()
    root.setLevel(log_level.upper())

    # Clear existing handlers (idempotent re-calls during tests)
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())

    if json_output:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s | %(levelname)-8s | %(name)s | rid=%(request_id)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            ),
        )

    root.addHandler(handler)

    # Quiet noisy third-party loggers
    for noisy in ("uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
