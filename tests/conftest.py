"""Shared pytest fixtures for platform tests."""

from __future__ import annotations

from collections.abc import Generator

import pytest

from delivery_ml.config.settings import Settings, get_settings


@pytest.fixture(autouse=True)
def isolate_settings_environment(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Prevent host environment configuration from leaking into deterministic tests."""
    for field_name in Settings.model_fields:
        monkeypatch.delenv(field_name.upper(), raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
