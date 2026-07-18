# Database module

## Purpose

The database module provides the normalized PostgreSQL data model, transactional
SQLAlchemy runtime, reusable repository primitive, and an executable initial schema
migration for the Delivery ML Platform.

`src/delivery_ml/database/models.py` is the application schema contract. The migration
at `database/migrations/001_initial_schema.sql` is the deployment artifact for a new
PostgreSQL database. Both define the same tables, constraints, indexes, and operational
views.

## Schema

| Area | Tables | Responsibility |
| --- | --- | --- |
| Service geography | `delivery_zones` | Zone dimension used by demand and routing data. |
| Delivery entities | `restaurants`, `drivers`, `customers` | Normalized operational dimensions. |
| Context | `weather`, `holidays`, `events` | Time-dependent external signals for feature generation. |
| Delivery facts | `orders`, `zone_demand` | Historical delivery facts and horizon-specific demand labels. |
| Feature parity | `feature_store` | Versioned point-in-time feature payloads with availability timestamps. |
| Model operations | `model_registry`, `prediction_logs` | Reproducible model metadata and auditable inference records. |

Foreign keys are restrictive for facts and nullable only where retaining historical data
requires it. The schema enforces allowed model, order, prediction, vehicle, traffic, and
forecast-horizon values. Composite uniqueness constraints make ingestion retry-safe.

## Views

- `latest_zone_features` returns the most recent feature record for each zone and feature
  set version.
- `active_models` exposes the model artifact metadata currently selected for inference.

The partial unique index `uq_model_registry_one_active` guarantees one active model per
model type even when concurrent writers are used.

## Applying the schema

Set the PostgreSQL values in `.env`, then run the migration once against the target
database:

```bash
psql "$DATABASE_URL" -f database/migrations/001_initial_schema.sql
```

`DATABASE_URL` must point to PostgreSQL and use credentials permitted to create tables,
indexes, and views. The application settings derive a SQLAlchemy URL from the individual
`POSTGRES_*` variables; deployment tooling may build `DATABASE_URL` from the same values.

## Runtime usage

Construct one `DatabaseRuntime` when the API or worker starts and dispose it at shutdown.
Transaction boundaries belong to the caller:

```python
from delivery_ml.config import get_settings
from delivery_ml.database import DeliveryZone, SqlAlchemyRepository, create_database_runtime

runtime = create_database_runtime(get_settings())
with runtime.session_scope() as session:
    zones = SqlAlchemyRepository(session, DeliveryZone)
    zones.add(DeliveryZone(code="blr-01", name="Indiranagar", city="Bengaluru"))
```

The context manager commits only after the block completes successfully; it rolls back
and re-raises failures. Repository methods deliberately do not commit, allowing a service
to atomically update multiple aggregates.

## Verification

```bash
pytest --cov
ruff check src tests
mypy src
```
