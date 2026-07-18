"""Tests for ETA model fitting and persisted artifact inference."""

from __future__ import annotations

import pandas as pd

from delivery_ml.config import Settings
from delivery_ml.features import EtaFeatureBuilder
from delivery_ml.training import EtaModelArtifactStore, EtaModelTrainer


def test_eta_trainer_fits_and_loads_artifact(tmp_path) -> None:
    """The categorical pipeline trains, predicts seconds, and survives serialization."""
    rows = []
    for index in range(24):
        rows.append({"distance_km": 1 + index % 6, "traffic_level": ["low", "medium", "high"][index % 3], "weather_condition": ["clear", "rain"][index % 2], "vehicle_type": "bike", "restaurant_id": f"r-{index % 3}", "predicted_demand": 5 + index, "hour": index % 24, "weekday": index % 7, "eta_seconds": 400 + index * 12})
    settings = Settings(model_artifacts_directory=tmp_path, xgboost_n_estimators=8, xgboost_max_depth=2)
    feature_set = EtaFeatureBuilder().build_training_features(pd.DataFrame(rows))
    model = EtaModelTrainer(settings).train(feature_set, version="eta-test-v1")

    assert model.metrics.mae >= 0
    assert model.predict(feature_set.frame.head(1)).shape == (1,)
    store = EtaModelArtifactStore(settings)
    assert store.load(store.save(model)).version == "eta-test-v1"
