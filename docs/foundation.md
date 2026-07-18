# Foundation module

## Purpose

This module centralizes environment-driven configuration and structured logging. Application
modules must obtain configuration through `get_settings()` and log through
`get_logger(__name__)`; they must not read environment variables directly.

## Configuration

Configuration is loaded from `.env` when present, then overridden by real environment
variables. Every setting has an environment variable documented in `.env.example`.
Sensitive values are intentionally excluded from version control.

The `Settings` model validates network ports, connection pool limits, feature-cache TTLs,
API prefixes, and scheduling values before the process starts. Its `postgres_dsn` and
`redis_url` properties generate safely encoded connection URLs from the individual values.

## Logging contract

`configure_logging()` installs one idempotent root handler. JSON log entries include UTC
timestamp, level, logger name, message, request ID, and exception details when available.
`bind_request_id()` is context-local and intended for API middleware and background jobs.

Human-readable logs are available by setting `LOG_FORMAT=text`, primarily for local work.
