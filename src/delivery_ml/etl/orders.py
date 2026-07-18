"""CSV-to-PostgreSQL idempotent ingestion for normalized delivery order facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from delivery_ml.config import Settings
from delivery_ml.database.models import Customer, DeliveryZone, Driver, Order, Restaurant
from delivery_ml.database.session import DatabaseRuntime
from delivery_ml.observability import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class NormalizedOrder:
    """Validated order fact plus normalized dimension identity fields."""

    external_id: str
    zone_code: str
    zone_name: str
    city: str
    restaurant_external_id: str
    restaurant_name: str
    customer_external_id: str
    driver_external_id: str | None
    vehicle_type: str
    ordered_at: datetime
    status: str
    distance_km: float | None
    traffic_level: str | None


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """Counts emitted by a successful idempotent ingestion run."""

    source_rows: int
    accepted_rows: int


class OrderCsvTransformer:
    """Normalize a source CSV into canonical order records using an explicit column map."""

    required_fields = frozenset(
        {
            "external_id", "zone_code", "zone_name", "city", "restaurant_external_id",
            "restaurant_name", "customer_external_id", "vehicle_type", "ordered_at", "status",
        }
    )

    def read(self, path: Path, column_map: dict[str, str]) -> list[NormalizedOrder]:
        """Read a CSV and transform it after validating source-to-canonical mappings."""
        return self.transform(pd.read_csv(path), column_map)

    def transform(self, source: pd.DataFrame, column_map: dict[str, str]) -> list[NormalizedOrder]:
        """Validate, normalize, and convert source records without mutating the input frame."""
        missing = sorted(self.required_fields.difference(column_map))
        if missing:
            raise ValueError(f"Column map is missing canonical fields: {missing}")
        unavailable = sorted(set(column_map.values()).difference(source.columns))
        if unavailable:
            raise ValueError(f"Source data is missing mapped columns: {unavailable}")
        frame = source.rename(columns={raw: canonical for canonical, raw in column_map.items()})
        frame["ordered_at"] = pd.to_datetime(frame["ordered_at"], utc=True, errors="raise")
        distance_source = (
            frame["distance_km"] if "distance_km" in frame else pd.Series(None, index=frame.index)
        )
        frame["distance_km"] = pd.to_numeric(distance_source, errors="coerce")
        for field in ("external_id", "zone_code", "zone_name", "city", "restaurant_external_id", "restaurant_name", "customer_external_id", "vehicle_type", "status"):
            frame[field] = frame[field].astype(str).str.strip()
            if frame[field].eq("").any() or frame[field].eq("nan").any():
                raise ValueError(f"Order source contains blank values for {field}.")
        if frame["external_id"].duplicated().any():
            raise ValueError("Order source contains duplicate external_id values.")
        frame["driver_external_id"] = frame.get("driver_external_id", pd.Series(None, index=frame.index))
        frame["traffic_level"] = frame.get("traffic_level", pd.Series(None, index=frame.index))
        records: list[NormalizedOrder] = []
        for _, row in frame.iterrows():
            records.append(
                NormalizedOrder(
                    external_id=str(row["external_id"]), zone_code=str(row["zone_code"]),
                    zone_name=str(row["zone_name"]), city=str(row["city"]),
                    restaurant_external_id=str(row["restaurant_external_id"]),
                    restaurant_name=str(row["restaurant_name"]),
                    customer_external_id=str(row["customer_external_id"]),
                    driver_external_id=None if pd.isna(row["driver_external_id"]) else str(row["driver_external_id"]),
                    vehicle_type=str(row["vehicle_type"]).lower(),
                    ordered_at=pd.Timestamp(row["ordered_at"]).to_pydatetime(),
                    status=str(row["status"]).lower(),
                    distance_km=None if pd.isna(row["distance_km"]) else float(row["distance_km"]),
                    traffic_level=None if pd.isna(row["traffic_level"]) else str(row["traffic_level"]).lower(),
                )
            )
        return records


class OrderIngestionService:
    """Upsert order dimensions and facts in one transaction for rerunnable ETL batches."""

    def __init__(self, settings: Settings) -> None:
        self._batch_size = settings.etl_batch_size

    def ingest(self, runtime: DatabaseRuntime, records: list[NormalizedOrder]) -> IngestionResult:
        """Persist records idempotently; PostgreSQL unique constraints make retries safe."""
        with runtime.session_scope() as session:
            for offset in range(0, len(records), self._batch_size):
                self._ingest_batch(session, records[offset : offset + self._batch_size])
        result = IngestionResult(source_rows=len(records), accepted_rows=len(records))
        logger.info("orders_ingested", extra={"source_rows": result.source_rows})
        return result

    @staticmethod
    def _ingest_batch(session: Any, records: list[NormalizedOrder]) -> None:
        zones = {record.zone_code: record for record in records}
        session.execute(
            insert(DeliveryZone)
            .values([{"code": item.zone_code, "name": item.zone_name, "city": item.city} for item in zones.values()])
            .on_conflict_do_update(index_elements=["code"], set_={"name": insert(DeliveryZone).excluded.name, "city": insert(DeliveryZone).excluded.city})
        )
        zone_ids = dict(session.execute(select(DeliveryZone.code, DeliveryZone.id).where(DeliveryZone.code.in_(zones))).all())
        restaurants = {record.restaurant_external_id: record for record in records}
        session.execute(insert(Restaurant).values([{"external_id": item.restaurant_external_id, "name": item.restaurant_name, "zone_id": zone_ids[item.zone_code]} for item in restaurants.values()]).on_conflict_do_update(index_elements=["external_id"], set_={"name": insert(Restaurant).excluded.name, "zone_id": insert(Restaurant).excluded.zone_id}))
        customers = {record.customer_external_id for record in records}
        session.execute(insert(Customer).values([{"external_id": value} for value in customers]).on_conflict_do_nothing(index_elements=["external_id"]))
        drivers = {record.driver_external_id: record for record in records if record.driver_external_id}
        if drivers:
            session.execute(insert(Driver).values([{"external_id": value, "vehicle_type": item.vehicle_type} for value, item in drivers.items()]).on_conflict_do_update(index_elements=["external_id"], set_={"vehicle_type": insert(Driver).excluded.vehicle_type}))
        restaurant_ids = dict(session.execute(select(Restaurant.external_id, Restaurant.id).where(Restaurant.external_id.in_(restaurants))).all())
        customer_ids = dict(session.execute(select(Customer.external_id, Customer.id).where(Customer.external_id.in_(customers))).all())
        driver_ids = dict(session.execute(select(Driver.external_id, Driver.id).where(Driver.external_id.in_(drivers))).all()) if drivers else {}
        values = [{"external_id": item.external_id, "zone_id": zone_ids[item.zone_code], "restaurant_id": restaurant_ids[item.restaurant_external_id], "customer_id": customer_ids[item.customer_external_id], "driver_id": driver_ids.get(item.driver_external_id), "ordered_at": item.ordered_at, "status": item.status, "distance_km": item.distance_km, "traffic_level": item.traffic_level} for item in records]
        session.execute(insert(Order).values(values).on_conflict_do_update(index_elements=["external_id"], set_={key: insert(Order).excluded[key] for key in values[0] if key != "external_id"}))
