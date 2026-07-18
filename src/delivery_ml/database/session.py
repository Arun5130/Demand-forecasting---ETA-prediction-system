"""Database engine construction, health checks, and transaction lifecycle helpers."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from delivery_ml.config.settings import Settings


@dataclass(frozen=True, slots=True)
class DatabaseRuntime:
    """Own the database engine and factory used by API and background services."""

    engine: Engine
    session_factory: sessionmaker[Session]

    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        """Yield a transactional session, committing on success and rolling back on error."""
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        """Release all pooled database connections during orderly application shutdown."""
        self.engine.dispose()


def create_database_runtime(settings: Settings) -> DatabaseRuntime:
    """Create the production database runtime from validated application settings."""
    engine = create_engine(
        settings.postgres_dsn,
        pool_size=settings.postgres_pool_size,
        max_overflow=settings.postgres_max_overflow,
        pool_timeout=settings.postgres_pool_timeout_seconds,
        pool_recycle=settings.postgres_pool_recycle_seconds,
        pool_pre_ping=True,
    )
    return DatabaseRuntime(
        engine=engine,
        session_factory=sessionmaker(bind=engine, autoflush=False, expire_on_commit=False),
    )


def get_session(runtime: DatabaseRuntime) -> Generator[Session, None, None]:
    """FastAPI-compatible dependency that supplies one transaction-scoped session."""
    with runtime.session_scope() as session:
        yield session


def check_database_connection(runtime: DatabaseRuntime) -> bool:
    """Return whether a lightweight database probe succeeds without leaking a connection."""
    try:
        with runtime.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
