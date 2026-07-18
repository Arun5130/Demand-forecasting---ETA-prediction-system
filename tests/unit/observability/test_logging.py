"""Tests for context-aware structured logging."""

from __future__ import annotations

import json
import logging
import sys

from delivery_ml.config.settings import Settings
from delivery_ml.observability import logging as logging_module


def test_json_formatter_includes_request_context() -> None:
    """JSON logs preserve correlation IDs and standard record metadata."""
    formatter = logging_module.JsonFormatter()
    token = logging_module.bind_request_id("request-123")
    try:
        record = logging.LogRecord(
            name="delivery_ml.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="forecast completed",
            args=(),
            exc_info=None,
        )
        payload = json.loads(formatter.format(record))
    finally:
        logging_module.reset_request_id(token)

    assert payload["message"] == "forecast completed"
    assert payload["request_id"] == "request-123"
    assert payload["level"] == "INFO"


def test_json_formatter_serializes_exceptions() -> None:
    """Structured logs retain traceback details for production diagnostics."""
    formatter = logging_module.JsonFormatter()
    try:
        raise RuntimeError("model artifact unavailable")
    except RuntimeError:
        record = logging.LogRecord(
            name="delivery_ml.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="inference failed",
            args=(),
            exc_info=sys.exc_info(),
        )

    payload = json.loads(formatter.format(record))

    assert "RuntimeError: model artifact unavailable" in payload["exception"]


def test_configure_logging_is_idempotent() -> None:
    """Repeated startup hooks do not add duplicate root handlers."""
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    was_configured = logging_module._configured
    try:
        root.handlers.clear()
        logging_module._configured = False
        settings = Settings()
        logging_module.configure_logging(settings)
        logging_module.configure_logging(settings)

        assert len(root.handlers) == 1
    finally:
        root.handlers.clear()
        root.handlers.extend(original_handlers)
        root.setLevel(original_level)
        logging_module._configured = was_configured


def test_request_id_filter_sets_default_and_bound_values() -> None:
    """Plain-text formatting always receives a safe correlation-ID value."""
    request_filter = logging_module._RequestIdFilter()
    record = logging.LogRecord("delivery_ml.test", logging.INFO, __file__, 1, "message", (), None)

    assert request_filter.filter(record) is True
    assert record.__dict__["request_id"] == "-"

    token = logging_module.bind_request_id("job-456")
    try:
        assert request_filter.filter(record) is True
        assert record.__dict__["request_id"] == "job-456"
    finally:
        logging_module.reset_request_id(token)
