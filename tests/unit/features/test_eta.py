"""Tests for ETA feature validation and shared transformation behavior."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from delivery_ml.features import EtaFeatureBuilder


def test_eta_feature_builder_uses_same_online_and_training_transformation() -> None:
    """Categorical normalization and calendar extraction are identical across paths."""
    row = {"distance_km": 3.4, "traffic_level": "High", "weather_condition": "Rain", "vehicle_type": "Bike", "restaurant_id": "R-1", "predicted_demand": 12, "ordered_at": datetime(2026, 7, 18, 10, tzinfo=UTC)}
    builder = EtaFeatureBuilder()
    online = builder.build_online_features(pd.DataFrame([row])).frame.iloc[0]
    training = builder.build_training_features(pd.DataFrame([{**row, "eta_seconds": 840}])).frame.iloc[0]

    assert online["traffic_level"] == training["traffic_level"] == "high"
    assert online["restaurant_id"] == "r-1"
    assert online["hour"] == 10


def test_eta_feature_builder_rejects_invalid_distance_and_calendar() -> None:
    """Invalid online feature values are refused before model inference."""
    builder = EtaFeatureBuilder()
    invalid = pd.DataFrame([{ "distance_km": -1, "traffic_level": "low", "weather_condition": "clear", "vehicle_type": "bike", "restaurant_id": "r", "predicted_demand": 1, "hour": 25, "weekday": 1 }])
    with pytest.raises(ValueError, match="non-negative"):
        builder.build_online_features(invalid)
