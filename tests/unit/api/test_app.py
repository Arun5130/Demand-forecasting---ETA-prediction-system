"""Tests for API health and static dashboard serving without live dependencies."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from delivery_ml.api.app import create_app
from delivery_ml.config import Settings


def test_api_serves_health_with_dependency_states(monkeypatch) -> None:
    """Health remains available when downstream dependencies are not reachable."""
    app = create_app(Settings(frontend_directory=Path("frontend")))
    monkeypatch.setattr("delivery_ml.api.routes.operations.check_database_connection", lambda _: False)
    monkeypatch.setattr("delivery_ml.api.routes.operations._redis_healthy", lambda _: False)

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["database"] == "unavailable"
    assert response.json()["redis"] == "unavailable"


def test_api_serves_static_dashboard() -> None:
    """FastAPI serves the framework-free dashboard from its configured directory."""
    app = create_app(Settings(frontend_directory=Path("frontend")))

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "Operations overview" not in response.text
    assert 'src="js/dashboard.js"' in response.text
