"""Normalized SQLAlchemy ORM mappings for the delivery ML platform."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from delivery_ml.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now

JSON_PAYLOAD = JSON().with_variant(JSONB, "postgresql")


class DeliveryZone(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A delivery-service area used for demand aggregation and routing."""

    __tablename__ = "delivery_zones"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    city: Mapped[str] = mapped_column(String(128), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    restaurants: Mapped[list[Restaurant]] = relationship(back_populates="zone")
    orders: Mapped[list[Order]] = relationship(back_populates="zone")

    __table_args__ = (
        CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90 AND 90",
            name="valid_latitude",
        ),
        CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180",
            name="valid_longitude",
        ),
        Index("ix_delivery_zones_city_active", "city", "is_active"),
    )


class Restaurant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Restaurant master data with a stable source-system identifier."""

    __tablename__ = "restaurants"

    external_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    zone_id: Mapped[UUID] = mapped_column(
        ForeignKey("delivery_zones.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    cuisine: Mapped[str | None] = mapped_column(String(128), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    zone: Mapped[DeliveryZone] = relationship(back_populates="restaurants")
    orders: Mapped[list[Order]] = relationship(back_populates="restaurant")

    __table_args__ = (Index("ix_restaurants_zone_active", "zone_id", "is_active"),)


class Driver(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Driver master data used to connect historical deliveries to supply context."""

    __tablename__ = "drivers"

    external_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    vehicle_type: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    orders: Mapped[list[Order]] = relationship(back_populates="driver")

    __table_args__ = (
        CheckConstraint(
            "vehicle_type IN ('bicycle', 'bike', 'car', 'scooter', 'walk')",
            name="valid_vehicle_type",
        ),
    )


class Customer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Customer master data containing only features permitted for ETA modeling."""

    __tablename__ = "customers"

    external_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    home_zone_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("delivery_zones.id", ondelete="SET NULL"), nullable=True, index=True
    )
    first_order_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    orders: Mapped[list[Order]] = relationship(back_populates="customer")


class WeatherObservation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Point-in-time weather observations associated with delivery zones."""

    __tablename__ = "weather"

    zone_id: Mapped[UUID] = mapped_column(
        ForeignKey("delivery_zones.id", ondelete="RESTRICT"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    condition: Mapped[str] = mapped_column(String(64), nullable=False)
    temperature_celsius: Mapped[float | None] = mapped_column(Float, nullable=True)
    precipitation_mm: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    wind_speed_kph: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint("zone_id", "observed_at", "source", name="weather_observation"),
        CheckConstraint("precipitation_mm >= 0", name="non_negative_precipitation"),
        Index("ix_weather_zone_observed_at", "zone_id", "observed_at"),
    )


class Holiday(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Regional holiday calendar used for offline and online feature generation."""

    __tablename__ = "holidays"

    holiday_date: Mapped[date] = mapped_column(Date, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    region_code: Mapped[str] = mapped_column(String(16), default="IN", nullable=False)
    is_public_holiday: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint("holiday_date", "name", "region_code", name="holiday_identity"),
        Index("ix_holidays_date_region", "holiday_date", "region_code"),
    )


class Event(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Local events that may affect zone-level demand without modifying order facts."""

    __tablename__ = "events"

    zone_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("delivery_zones.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expected_attendance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="end_after_start"),
        CheckConstraint(
            "expected_attendance IS NULL OR expected_attendance >= 0",
            name="non_negative_attendance",
        ),
        Index("ix_events_zone_schedule", "zone_id", "starts_at", "ends_at"),
    )


class Order(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Immutable delivery order fact supporting demand and ETA training datasets."""

    __tablename__ = "orders"

    external_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    zone_id: Mapped[UUID] = mapped_column(
        ForeignKey("delivery_zones.id", ondelete="RESTRICT"), nullable=False
    )
    restaurant_id: Mapped[UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="RESTRICT"), nullable=False
    )
    driver_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("drivers.id", ondelete="RESTRICT"), nullable=True
    )
    customer_id: Mapped[UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    ordered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    picked_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    distance_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    traffic_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    delivery_fee: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    zone: Mapped[DeliveryZone] = relationship(back_populates="orders")
    restaurant: Mapped[Restaurant] = relationship(back_populates="orders")
    driver: Mapped[Driver | None] = relationship(back_populates="orders")
    customer: Mapped[Customer] = relationship(back_populates="orders")

    __table_args__ = (
        CheckConstraint(
            "status IN ('created', 'accepted', 'picked_up', 'delivered', 'cancelled')",
            name="valid_status",
        ),
        CheckConstraint("distance_km IS NULL OR distance_km >= 0", name="non_negative_distance"),
        CheckConstraint(
            "traffic_level IS NULL OR traffic_level IN ('low', 'medium', 'high', 'severe')",
            name="valid_traffic_level",
        ),
        CheckConstraint(
            "delivered_at IS NULL OR delivered_at >= ordered_at",
            name="delivery_after_order",
        ),
        Index("ix_orders_zone_ordered_at", "zone_id", "ordered_at"),
        Index("ix_orders_restaurant_ordered_at", "restaurant_id", "ordered_at"),
        Index("ix_orders_driver_ordered_at", "driver_id", "ordered_at"),
        Index("ix_orders_status_ordered_at", "status", "ordered_at"),
    )


class ZoneDemand(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Observed or labeled demand aggregates for a zone and forecast horizon."""

    __tablename__ = "zone_demand"

    zone_id: Mapped[UUID] = mapped_column(
        ForeignKey("delivery_zones.id", ondelete="RESTRICT"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    horizon_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    demand_count: Mapped[int] = mapped_column(Integer, nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(128), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "zone_id", "observed_at", "horizon_hours", "dataset_version", name="zone_demand_identity"
        ),
        CheckConstraint("horizon_hours IN (1, 3, 6)", name="supported_horizon"),
        CheckConstraint("demand_count >= 0", name="non_negative_demand"),
        Index("ix_zone_demand_lookup", "zone_id", "observed_at", "horizon_hours"),
    )


class FeatureStoreRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Versioned point-in-time feature vector for online/offline feature parity."""

    __tablename__ = "feature_store"

    zone_id: Mapped[UUID] = mapped_column(
        ForeignKey("delivery_zones.id", ondelete="RESTRICT"), nullable=False
    )
    feature_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    feature_set_version: Mapped[str] = mapped_column(String(64), nullable=False)
    values: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, nullable=False)

    __table_args__ = (
        CheckConstraint("available_at <= feature_timestamp", name="available_before_feature_time"),
        UniqueConstraint(
            "zone_id", "feature_timestamp", "feature_set_version", name="feature_store_identity"
        ),
        Index("ix_feature_store_zone_time", "zone_id", "feature_timestamp"),
    )


class ModelRegistryEntry(UUIDPrimaryKeyMixin, Base):
    """Registered model artifact and reproducibility metadata."""

    __tablename__ = "model_registry"

    model_type: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(128), nullable=False)
    hyperparameters: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, nullable=False)
    metrics: Mapped[dict[str, float]] = mapped_column(JSON_PAYLOAD, nullable=False)
    artifact_path: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("model_type", "version", name="model_registry_version"),
        CheckConstraint("model_type IN ('demand', 'eta')", name="valid_model_type"),
        CheckConstraint(
            "stage IN ('development', 'staging', 'production', 'archived')", name="valid_stage"
        ),
        Index(
            "uq_model_registry_one_active",
            "model_type",
            unique=True,
            postgresql_where="is_active",
        ),
        Index("ix_model_registry_type_stage", "model_type", "stage"),
    )


class PredictionLog(UUIDPrimaryKeyMixin, Base):
    """Auditable inference record without copying raw personally identifying inputs."""

    __tablename__ = "prediction_logs"

    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    prediction_type: Mapped[str] = mapped_column(String(32), nullable=False)
    zone_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("delivery_zones.id", ondelete="SET NULL"), nullable=True
    )
    model_registry_id: Mapped[UUID] = mapped_column(
        ForeignKey("model_registry.id", ondelete="RESTRICT"), nullable=False
    )
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, nullable=False)
    response_payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, nullable=False)
    response_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    __table_args__ = (
        CheckConstraint("prediction_type IN ('demand', 'eta')", name="valid_prediction_type"),
        CheckConstraint("response_time_ms >= 0", name="non_negative_response_time"),
        Index("ix_prediction_logs_requested_at", "requested_at"),
        Index("ix_prediction_logs_zone_requested_at", "zone_id", "requested_at"),
        Index("ix_prediction_logs_request_id", "request_id"),
    )
