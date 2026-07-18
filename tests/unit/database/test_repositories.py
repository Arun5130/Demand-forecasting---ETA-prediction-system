"""Tests for repository transaction ownership and CRUD primitives."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from delivery_ml.database.base import Base
from delivery_ml.database.models import DeliveryZone
from delivery_ml.database.repositories import SqlAlchemyRepository


def test_repository_add_get_list_and_delete_without_committing() -> None:
    """Repositories compose inside a caller-owned unit of work."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    with Session(bind=engine) as session:
        repository = SqlAlchemyRepository(session, DeliveryZone)
        zone = repository.add(DeliveryZone(code="blr-01", name="Indiranagar", city="Bengaluru"))
        assert zone in session.new
        session.flush()
        zone_id = zone.id
        session.commit()

    with factory() as session:
        repository = SqlAlchemyRepository(session, DeliveryZone)
        fetched = repository.get(zone_id)
        assert fetched is not None
        assert repository.list() == [fetched]
        repository.delete(fetched)
        session.commit()

    with factory() as session:
        assert SqlAlchemyRepository(session, DeliveryZone).list() == []
