"""Tests for normalized ORM metadata and migration artifacts."""

from __future__ import annotations

from pathlib import Path

from delivery_ml.database.base import Base


def test_orm_metadata_contains_required_normalized_tables() -> None:
    """The metadata exposes all facts, dimensions, feature, and audit tables."""
    assert {
        "delivery_zones",
        "orders",
        "restaurants",
        "drivers",
        "customers",
        "weather",
        "holidays",
        "events",
        "zone_demand",
        "feature_store",
        "prediction_logs",
        "model_registry",
    }.issubset(Base.metadata.tables)


def test_migration_declares_tables_indexes_and_operational_views() -> None:
    """The deployable migration includes schema, query indexes, and required views."""
    migration = (
        Path(__file__).resolve().parents[3] / "database" / "migrations" / "001_initial_schema.sql"
    ).read_text(encoding="utf-8")

    for fragment in (
        "CREATE TABLE IF NOT EXISTS orders",
        "CREATE TABLE IF NOT EXISTS model_registry",
        "CREATE INDEX IF NOT EXISTS ix_orders_zone_ordered_at",
        "CREATE OR REPLACE VIEW latest_zone_features",
        "CREATE OR REPLACE VIEW active_models",
    ):
        assert fragment in migration
