"""HTTP response schemas for operational API endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    """Dependency-aware health response returned without requiring a model artifact."""

    status: str
    database: str
    redis: str
    version: str
    environment: str


class SystemStatusResponse(BaseModel):
    """Runtime status used by the dashboard and deployment monitoring."""

    database: dict[str, str]
    redis: dict[str, str]
    docker_containers: dict[str, str]
    latest_retraining_date: datetime | None
    system_uptime: str
    total_historical_orders: int
    total_delivery_zones: int
    number_of_trained_models: int
    app_version: str
    environment: str


class ModelRecord(BaseModel):
    """Safe model registry projection for model-management clients."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    model_type: str
    model_name: str
    version: str
    stage: str
    trained_at: datetime
    dataset_version: str
    metrics: dict[str, float]
    is_active: bool


class PredictionHistoryRecord(BaseModel):
    """Prediction audit projection with compact response fields."""

    id: UUID
    created_at: datetime
    prediction_type: str
    zone_id: UUID | None
    model_version: str
    eta_seconds: float | None = None
    demand: float | None = None
    response_time_ms: int


class RecordsResponse(BaseModel):
    """Stable list envelope for dashboard tables."""

    records: list[dict[str, Any]] = Field(default_factory=list)


class ForecastRequest(BaseModel):
    """Zone-level demand request at an explicit UTC prediction time."""

    zone_id: UUID
    prediction_at: datetime


class ForecastResponse(BaseModel):
    """Three horizon demand forecast response."""

    next_1_hour: float
    next_3_hours: float
    next_6_hours: float
    model_version: str


class EtaRequest(BaseModel):
    """Validated ETA delivery context with demand supplied by orchestration."""

    restaurant_id: str
    customer_id: str
    distance_km: float = Field(ge=0)
    weather: str
    traffic_level: str
    vehicle_type: str
    hour: int = Field(ge=0, le=23)
    predicted_demand: float = Field(default=0, ge=0)


class EtaResponse(BaseModel):
    """ETA prediction response for dashboard rendering."""

    eta_seconds: float
    model_version: str
    distance_km: float
    weather: str
    traffic_level: str
    predicted_demand: float
