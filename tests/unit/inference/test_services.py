"""Tests for model-bundle prediction services."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from delivery_ml.config import Settings
from delivery_ml.features import DemandFeatureSet
from delivery_ml.inference import DemandInferenceService
from delivery_ml.training import DemandModelTrainer


def test_demand_inference_returns_all_non_negative_horizons() -> None:
    """A trained bundle produces dashboard-ready horizon predictions."""
    start = datetime(2026, 1, 1, tzinfo=UTC)
    frame = pd.DataFrame([{"bucket_at": start + timedelta(hours=i), "lag": float(i), "target_demand_1h": i + 1, "target_demand_3h": i + 3, "target_demand_6h": i + 6} for i in range(20)])
    model = DemandModelTrainer(Settings(xgboost_n_estimators=4, xgboost_max_depth=2)).train(DemandFeatureSet(frame, feature_columns=("lag",)), version="demand-inference")
    prediction = DemandInferenceService().predict(model, pd.DataFrame({"lag": [12.0]}))

    assert prediction.model_version == "demand-inference"
    assert prediction.next_1_hour >= 0
