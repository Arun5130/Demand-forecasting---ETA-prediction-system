"""Reusable repository abstractions for SQLAlchemy-backed application services."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from delivery_ml.database.base import Base


class SqlAlchemyRepository[ModelT: Base]:
    """Minimal unit-of-work friendly repository for a single ORM model type.

    The caller owns transaction boundaries through :class:`Session`; repository methods
    never commit independently. This makes multi-record writes atomic in service layers.
    """

    def __init__(self, session: Session, model_type: type[ModelT]) -> None:
        """Initialize the repository with an active session and mapped type."""
        self._session = session
        self._model_type = model_type

    def add(self, entity: ModelT) -> ModelT:
        """Attach an entity to the current unit of work and return it."""
        self._session.add(entity)
        return entity

    def get(self, entity_id: UUID) -> ModelT | None:
        """Return an entity by primary key, or ``None`` when it does not exist."""
        return self._session.get(self._model_type, entity_id)

    def list(self, statement: Select[tuple[ModelT]] | None = None) -> Sequence[ModelT]:
        """Run an optional typed statement or return all rows of this model type."""
        query = statement if statement is not None else select(self._model_type)
        return self._session.scalars(query).all()

    def delete(self, entity: ModelT) -> None:
        """Mark an entity for deletion in the surrounding transaction."""
        self._session.delete(entity)
