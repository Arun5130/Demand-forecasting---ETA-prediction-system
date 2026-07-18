"""Tests for transactional session handling and database health probes."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from delivery_ml.config.settings import Settings
from delivery_ml.database.session import (
    DatabaseRuntime,
    check_database_connection,
    create_database_runtime,
)


def test_session_scope_commits_and_rolls_back_failures() -> None:
    """Transaction boundaries commit success and roll back exceptions exactly once."""
    engine = create_engine("sqlite://")
    runtime = DatabaseRuntime(engine=engine, session_factory=sessionmaker(bind=engine))

    with runtime.session_scope() as session:
        assert session.in_transaction() is False

    with pytest.raises(RuntimeError, match="expected failure"), runtime.session_scope():
        raise RuntimeError("expected failure")


def test_database_health_probe_reports_connection_availability() -> None:
    """A successful lightweight query maps to a healthy database result."""
    engine = create_engine("sqlite://")
    runtime = DatabaseRuntime(engine=engine, session_factory=sessionmaker(bind=engine))

    assert check_database_connection(runtime) is True

    broken_engine = Mock()
    broken_engine.connect.side_effect = OSError("connection refused")
    broken_runtime = DatabaseRuntime(engine=broken_engine, session_factory=Mock())
    assert check_database_connection(broken_runtime) is False


def test_database_runtime_uses_validated_pool_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Engine construction is driven entirely by typed runtime settings."""
    engine = create_engine("sqlite://")
    create_engine_mock = Mock(return_value=engine)
    monkeypatch.setattr("delivery_ml.database.session.create_engine", create_engine_mock)
    settings = Settings(postgres_pool_size=7, postgres_max_overflow=9)

    runtime = create_database_runtime(settings)

    assert runtime.engine is engine
    assert create_engine_mock.call_args.kwargs["pool_size"] == 7
    assert create_engine_mock.call_args.kwargs["max_overflow"] == 9
