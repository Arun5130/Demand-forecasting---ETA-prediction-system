"""Application factory configuring FastAPI, observability, routes, and static UI."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import RequestResponseEndpoint

from delivery_ml.api.routes import router
from delivery_ml.config import Settings, get_settings
from delivery_ml.database import create_database_runtime
from delivery_ml.observability import (
    bind_request_id,
    configure_logging,
    get_logger,
    reset_request_id,
)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize process resources and dispose pooled connections at shutdown."""
    configure_logging(app.state.settings)
    app.state.started_at = datetime.now(UTC)
    logger.info("application_started")
    try:
        yield
    finally:
        app.state.database_runtime.dispose()
        logger.info("application_stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a configured API application without connecting during import."""
    runtime_settings = settings or get_settings()
    app = FastAPI(title=runtime_settings.app_name, version=runtime_settings.app_version, lifespan=lifespan)
    app.state.settings = runtime_settings
    app.state.database_runtime = create_database_runtime(runtime_settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in runtime_settings.cors_allowed_origins.split(",") if origin.strip()],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Request-ID"],
    )

    @app.middleware("http")
    async def log_request(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        token = bind_request_id(request_id)
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("http_request_failed", extra={"method": request.method, "path": request.url.path})
            return JSONResponse(status_code=500, content={"detail": "Internal server error."})
        finally:
            reset_request_id(token)
        response.headers["X-Request-ID"] = request_id
        logger.info("http_request_completed", extra={"method": request.method, "path": request.url.path, "duration_ms": round((perf_counter() - started) * 1000, 2)})
        return response

    app.include_router(router)
    frontend = runtime_settings.frontend_directory.expanduser().resolve()
    if frontend.is_dir():
        app.mount("/", StaticFiles(directory=Path(frontend), html=True), name="frontend")
    return app
