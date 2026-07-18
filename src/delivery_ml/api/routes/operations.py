"""Health, status, registry, audit-history, and explorer read endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from redis import Redis
from sqlalchemy import func, select
from sqlalchemy.inspection import inspect

from delivery_ml.api.schemas import (
    HealthResponse,
    ModelRecord,
    PredictionHistoryRecord,
    RecordsResponse,
    SystemStatusResponse,
)
from delivery_ml.config import Settings
from delivery_ml.database import (
    DeliveryZone,
    Event,
    Holiday,
    ModelRegistryEntry,
    Order,
    PredictionLog,
    Restaurant,
    WeatherObservation,
)
from delivery_ml.database.base import Base
from delivery_ml.database.session import DatabaseRuntime, check_database_connection

router = APIRouter(tags=["operations"])


def _runtime(request: Request) -> DatabaseRuntime:
    return cast(DatabaseRuntime, request.app.state.database_runtime)


def _settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def _redis_healthy(settings: Settings) -> bool:
    client = Redis.from_url(settings.redis_url, socket_timeout=settings.redis_socket_timeout_seconds)
    try:
        return bool(client.ping())
    except Exception:
        return False
    finally:
        client.close()


def _service_status(healthy: bool) -> str:
    return "healthy" if healthy else "unavailable"


def _serialize_row(value: Any) -> dict[str, Any]:
    return {column.key: getattr(value, column.key) for column in inspect(value).mapper.column_attrs}


def _dashboard_counts(runtime: DatabaseRuntime) -> tuple[int, int, int, datetime | None]:
    with runtime.session_scope() as session:
        orders = int(session.scalar(select(func.count()).select_from(Order)) or 0)
        zones = int(session.scalar(select(func.count()).select_from(DeliveryZone)) or 0)
        models = int(session.scalar(select(func.count()).select_from(ModelRegistryEntry)) or 0)
        latest = session.scalar(select(func.max(ModelRegistryEntry.trained_at)))
    return orders, zones, models, latest


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """Report independent API, PostgreSQL, and Redis health without masking outages."""
    settings = _settings(request)
    database = await run_in_threadpool(check_database_connection, _runtime(request))
    redis = await run_in_threadpool(_redis_healthy, settings)
    return HealthResponse(
        status="healthy",
        database=_service_status(database),
        redis=_service_status(redis),
        version=settings.app_version,
        environment=settings.app_environment,
    )


@router.get("/system-status", response_model=SystemStatusResponse)
async def system_status(request: Request) -> SystemStatusResponse:
    """Return current platform counts and non-invasive dependency diagnostics."""
    settings = _settings(request)
    runtime = _runtime(request)
    database = await run_in_threadpool(check_database_connection, runtime)
    redis = await run_in_threadpool(_redis_healthy, settings)
    counts: tuple[int, int, int, datetime | None] = (0, 0, 0, None)
    if database:
        counts = await run_in_threadpool(_dashboard_counts, runtime)
    uptime = datetime.now(UTC) - request.app.state.started_at
    return SystemStatusResponse(
        database={"status": _service_status(database)},
        redis={"status": _service_status(redis)},
        docker_containers={"status": "not_configured"},
        latest_retraining_date=counts[3],
        system_uptime=str(uptime).split(".", maxsplit=1)[0],
        total_historical_orders=counts[0],
        total_delivery_zones=counts[1],
        number_of_trained_models=counts[2],
        app_version=settings.app_version,
        environment=settings.app_environment,
    )


@router.get("/models", response_model=list[ModelRecord])
async def models(request: Request) -> list[ModelRecord]:
    """List registered models newest first for deployment and governance views."""
    def query() -> list[ModelRecord]:
        with _runtime(request).session_scope() as session:
            rows = session.scalars(select(ModelRegistryEntry).order_by(ModelRegistryEntry.trained_at.desc())).all()
        return [
            ModelRecord(
                id=row.id,
                model_type=row.model_type,
                model_name=f"{row.model_type}-xgboost",
                version=row.version,
                stage=row.stage,
                trained_at=row.trained_at,
                dataset_version=row.dataset_version,
                metrics=row.metrics,
                is_active=row.is_active,
            )
            for row in rows
        ]

    try:
        return await run_in_threadpool(query)
    except Exception as error:
        raise HTTPException(status_code=503, detail="Model registry is unavailable.") from error


@router.get("/prediction-history", response_model=list[PredictionHistoryRecord])
async def prediction_history(request: Request, limit: int = Query(default=100, ge=1, le=1000)) -> list[PredictionHistoryRecord]:
    """List bounded prediction audit history, newest first."""
    def query() -> list[PredictionHistoryRecord]:
        with _runtime(request).session_scope() as session:
            rows = session.execute(
                select(PredictionLog, ModelRegistryEntry.version)
                .join(ModelRegistryEntry, PredictionLog.model_registry_id == ModelRegistryEntry.id)
                .order_by(PredictionLog.requested_at.desc())
                .limit(limit)
            ).all()
        return [
            PredictionHistoryRecord(
                id=log.id,
                created_at=log.requested_at,
                prediction_type=log.prediction_type,
                zone_id=log.zone_id,
                model_version=version,
                eta_seconds=log.response_payload.get("eta_seconds"),
                demand=log.response_payload.get("demand"),
                response_time_ms=log.response_time_ms,
            )
            for log, version in rows
        ]

    try:
        return await run_in_threadpool(query)
    except Exception as error:
        raise HTTPException(status_code=503, detail="Prediction history is unavailable.") from error


EXPLORER_MODELS: dict[str, type[Base]] = {
    "orders": Order,
    "restaurants": Restaurant,
    "weather": WeatherObservation,
    "events": Event,
    "holidays": Holiday,
}


@router.get("/orders", response_model=RecordsResponse)
async def data_explorer(
    request: Request,
    dataset: str = Query(default="orders"),
    page_size: int = Query(default=100, ge=1, le=1000),
) -> RecordsResponse:
    """Return a bounded table projection for a whitelisted warehouse dataset."""
    model = EXPLORER_MODELS.get(dataset)
    if model is None:
        raise HTTPException(status_code=422, detail="Unsupported dataset.")

    def query() -> RecordsResponse:
        with _runtime(request).session_scope() as session:
            rows = session.scalars(select(model).limit(page_size)).all()
        return RecordsResponse(records=[_serialize_row(row) for row in rows])

    try:
        return await run_in_threadpool(query)
    except Exception as error:
        raise HTTPException(status_code=503, detail="Data explorer is unavailable.") from error
