"""Validated, environment-driven application settings."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated
from urllib.parse import quote_plus

from pydantic import Field, PositiveInt, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LogFormat(StrEnum):
    """Supported serialization formats for application logs."""

    JSON = "json"
    TEXT = "text"


class Settings(BaseSettings):
    """Runtime settings read from environment variables and an optional `.env` file.

    The model deliberately keeps connection elements separate so deployment systems can
    rotate credentials independently and the application can create encoded DSNs safely.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    app_name: str = Field(default="delivery-ml-platform", min_length=1, max_length=128)
    app_environment: str = Field(default="development", min_length=1, max_length=64)
    app_version: str = Field(default="0.1.0", min_length=1, max_length=64)
    debug: bool = False
    api_host: str = Field(default="0.0.0.0", min_length=1)
    api_port: Annotated[int, Field(ge=1, le=65535)] = 8000
    api_prefix: str = Field(default="/api/v1", min_length=1)
    log_level: str = Field(default="INFO", min_length=1, max_length=16)
    log_format: LogFormat = LogFormat.JSON

    postgres_host: str = Field(default="postgres", min_length=1)
    postgres_port: Annotated[int, Field(ge=1, le=65535)] = 5432
    postgres_database: str = Field(default="delivery_ml", min_length=1)
    postgres_user: str = Field(default="delivery_ml", min_length=1)
    postgres_password: str = Field(default="change-me-before-deployment", min_length=1)
    postgres_pool_size: PositiveInt = 10
    postgres_max_overflow: Annotated[int, Field(ge=0)] = 20
    postgres_pool_timeout_seconds: PositiveInt = 30
    postgres_pool_recycle_seconds: PositiveInt = 1800
    postgres_connect_timeout_seconds: PositiveInt = 10

    redis_host: str = Field(default="redis", min_length=1)
    redis_port: Annotated[int, Field(ge=1, le=65535)] = 6379
    redis_database: Annotated[int, Field(ge=0, le=15)] = 0
    redis_password: str | None = None
    redis_ssl: bool = False
    redis_socket_timeout_seconds: PositiveInt = 3
    redis_feature_ttl_seconds: PositiveInt = 3600
    redis_weather_ttl_seconds: PositiveInt = 1800

    model_artifacts_directory: Path = Path("artifacts")
    model_registry_stage: str = Field(default="production", min_length=1, max_length=64)
    random_seed: Annotated[int, Field(ge=0, le=2_147_483_647)] = 42
    inference_max_batch_size: PositiveInt = 1000

    retrain_schedule_day_of_week: str = Field(default="sunday", min_length=1)
    retrain_schedule_hour_utc: Annotated[int, Field(ge=0, le=23)] = 2
    retrain_schedule_minute_utc: Annotated[int, Field(ge=0, le=59)] = 0

    @field_validator("api_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        """Require a normalized absolute API path without a trailing slash."""
        if not value.startswith("/"):
            raise ValueError("API_PREFIX must start with '/'.")
        if value != "/" and value.endswith("/"):
            raise ValueError("API_PREFIX must not end with '/'.")
        return value

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        """Normalize and validate standard-library logging levels."""
        normalized = value.upper()
        allowed_levels = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        if normalized not in allowed_levels:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed_levels)}.")
        return normalized

    @field_validator("retrain_schedule_day_of_week")
    @classmethod
    def validate_retrain_day(cls, value: str) -> str:
        """Validate scheduler-compatible weekly day names."""
        normalized = value.lower()
        days = {
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        }
        if normalized not in days:
            raise ValueError(f"RETRAIN_SCHEDULE_DAY_OF_WEEK must be one of {sorted(days)}.")
        return normalized

    @field_validator("redis_password", mode="before")
    @classmethod
    def normalize_optional_redis_password(cls, value: str | None) -> str | None:
        """Convert blank optional Redis credentials to ``None`` before validation."""
        if value is not None and not value.strip():
            return None
        return value

    @property
    def postgres_dsn(self) -> str:
        """Return an encoded SQLAlchemy-compatible PostgreSQL connection URL."""
        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password)
        database = quote_plus(self.postgres_database)
        return (
            f"postgresql+psycopg://{user}:{password}@{self.postgres_host}:"
            f"{self.postgres_port}/{database}?connect_timeout={self.postgres_connect_timeout_seconds}"
        )

    @property
    def redis_url(self) -> str:
        """Return an encoded Redis connection URL."""
        scheme = "rediss" if self.redis_ssl else "redis"
        credentials = ""
        if self.redis_password:
            credentials = f":{quote_plus(self.redis_password)}@"
        return f"{scheme}://{credentials}{self.redis_host}:{self.redis_port}/{self.redis_database}"

    @property
    def resolved_model_artifacts_directory(self) -> Path:
        """Return the absolute artifact directory without creating it as a side effect."""
        return self.model_artifacts_directory.expanduser().resolve()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Create and cache the validated process-wide settings instance."""
    return Settings()
