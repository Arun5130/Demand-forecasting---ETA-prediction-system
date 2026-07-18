"""Context-aware structured logging for services, jobs, and libraries."""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any

from delivery_ml.config.settings import LogFormat, Settings

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_configured = False


class JsonFormatter(logging.Formatter):
    """Serialize standard logging records into stable JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record while preserving exception information."""
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": _request_id.get(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, separators=(",", ":"))


def bind_request_id(request_id: str) -> Token[str | None]:
    """Bind a request or job correlation identifier to the current context."""
    return _request_id.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    """Restore the preceding request identifier after a scoped operation."""
    _request_id.reset(token)


def configure_logging(settings: Settings) -> None:
    """Configure the root logger once using the requested runtime log format."""
    global _configured
    if _configured:
        return

    handler = logging.StreamHandler(sys.stdout)
    if settings.log_format is LogFormat.JSON:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%SZ",
            )
        )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(settings.log_level)
    _configured = True


class _RequestIdFilter(logging.Filter):
    """Attach request context to plain-text logging records."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Attach a safe default value for the formatter's request ID field."""
        record.request_id = _request_id.get() or "-"
        return True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger with request context attached when needed."""
    logger = logging.getLogger(name)
    if not any(isinstance(item, _RequestIdFilter) for item in logger.filters):
        logger.addFilter(_RequestIdFilter())
    return logger
