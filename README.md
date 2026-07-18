# Delivery ML Platform

Production-grade food delivery demand forecasting and ETA prediction platform.

The platform is implemented incrementally. The current modules provide typed runtime
configuration, environment validation, structured logging, a normalized PostgreSQL
database layer, quality tooling, and a framework-free operations dashboard.

## Frontend

The [frontend](frontend/README.md) is plain HTML5, CSS3, and ES6 modules. It has no npm,
bundler, or frontend framework. It uses Fetch API for FastAPI communication and Chart.js
directly from its CDN for forecast and model-metric charts.

## Local setup

1. Install Python 3.12.
2. Create and activate a virtual environment.
3. Install the application and development dependencies:

   ```bash
   pip install -e ".[dev]"
   ```

4. Copy `.env.example` to `.env` and replace deployment credentials.
5. Run the checks:

   ```bash
   ruff check .
   mypy src
   pytest --cov
   ```

See [docs/foundation.md](docs/foundation.md) for configuration details and
[docs/database.md](docs/database.md) for the schema, migration, and runtime usage. See
[docs/api.md](docs/api.md) for the current FastAPI endpoints and dashboard serving, and
[docs/cache.md](docs/cache.md) for Redis feature-cache behavior. The feature contract and
leakage controls are documented in [docs/features.md](docs/features.md). Model training
and registry activation are described in [docs/models.md](docs/models.md).
