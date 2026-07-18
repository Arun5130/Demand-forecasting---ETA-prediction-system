# API module

## Purpose

The API module is a FastAPI application factory that serves the static dashboard and
operational read endpoints. It creates no database connections at import time, making it
suitable for CLI tools, workers, and test clients.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Independently reports API, PostgreSQL, and Redis status. |
| `GET` | `/system-status` | Returns service state, warehouse counts, model count, and uptime. |
| `GET` | `/models` | Lists registered model metadata newest first. |
| `GET` | `/prediction-history` | Lists recent inference audit entries. |
| `GET` | `/orders` | Provides bounded explorer data for orders, restaurants, weather, events, or holidays. |

The inference endpoints are implemented with the inference module because they must load
registered, validated XGBoost artifacts and their shared point-in-time feature pipeline.

## Run

Install the project dependencies, ensure `.env` has valid PostgreSQL and Redis settings,
then start the application from the repository root:

```bash
uvicorn delivery_ml.api.app:create_app --factory --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`. FastAPI serves the dashboard files from the configurable
`FRONTEND_DIRECTORY`. When PostgreSQL or Redis is unavailable, `/health` remains available
and reports the dependency as `unavailable`; it does not claim a false healthy state.

## Configuration

- `CORS_ALLOWED_ORIGINS` is a comma-separated allow-list for browser clients.
- `FRONTEND_DIRECTORY` selects the static dashboard directory.
- `POSTGRES_*` and `REDIS_*` control dependency connectivity.

Every request receives an `X-Request-ID` response header. The API logs the request path,
method, duration, and correlation ID using the platform's structured logging contract.
