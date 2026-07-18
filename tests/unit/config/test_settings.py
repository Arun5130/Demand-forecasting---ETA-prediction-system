"""Tests for environment-backed runtime settings."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from delivery_ml.config.settings import Settings


def test_settings_build_encoded_connection_urls() -> None:
    """Connection URLs encode credentials and honor the configured transport."""
    settings = Settings(
        postgres_user="user@example.com",
        postgres_password="pa:ss word",
        postgres_database="delivery db",
        redis_password="redis secret",
        redis_ssl=True,
    )

    assert "user%40example.com:pa%3Ass+word" in settings.postgres_dsn
    assert settings.postgres_dsn.endswith("delivery+db?connect_timeout=10")
    assert settings.redis_url == "rediss://:redis+secret@redis:6379/0"


def test_blank_redis_password_is_normalized_to_none() -> None:
    """An empty environment-provided Redis password does not produce malformed auth."""
    settings = Settings(redis_password="   ")

    assert settings.redis_password is None
    assert settings.redis_url == "redis://redis:6379/0"


@pytest.mark.parametrize("api_prefix", ["api/v1", "/api/v1/"])
def test_settings_reject_invalid_api_prefix(api_prefix: str) -> None:
    """API paths must be normalized before routers are configured."""
    with pytest.raises(ValidationError, match="API_PREFIX"):
        Settings(api_prefix=api_prefix)


def test_settings_reject_invalid_log_level() -> None:
    """An invalid log level fails during startup rather than during logging."""
    with pytest.raises(ValidationError, match="LOG_LEVEL"):
        Settings(log_level="verbose")


def test_settings_normalize_scheduler_and_resolve_artifact_directory(tmp_path: Path) -> None:
    """Scheduler values and artifact paths are normalized at configuration boundaries."""
    settings = Settings(
        retrain_schedule_day_of_week="MONDAY",
        model_artifacts_directory=tmp_path / "models",
    )

    assert settings.retrain_schedule_day_of_week == "monday"
    assert settings.resolved_model_artifacts_directory == (tmp_path / "models").resolve()


@pytest.mark.parametrize("day", ["weekday", "Sun day"])
def test_settings_reject_invalid_retraining_day(day: str) -> None:
    """A malformed weekly schedule cannot be accepted at startup."""
    with pytest.raises(ValidationError, match="RETRAIN_SCHEDULE_DAY_OF_WEEK"):
        Settings(retrain_schedule_day_of_week=day)
