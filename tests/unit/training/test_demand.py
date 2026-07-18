"""Tests for chronological demand training, prediction, and artifact round trips."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from delivery_ml.config import Settings
from delivery_ml.features import DemandFeatureSet
from delivery_ml.training import DemandModelArtifactStore, DemandModelTrainer


def _feature_set() -> DemandFeatureSet:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows = []
    for index in range(32):
        value = float(index + 1)
        rows.append(
            {
                "bucket_at": start + timedelta(hours=index),
                "demand_lag_1h": value,
                "hour": index % 24,
                "target_demand_1h": value + 1,
                "target_demand_3h": value + 3,
                "target_demand_6h": value + 6,
            }
        )
    return DemandFeatureSet(pd.DataFrame(rows), feature_columns=("demand_lag_1h", "hour"))


def test_trainer_fits_all_horizons_and_artifact_round_trips(tmp_path) -> None:
    """Three horizon models produce metrics, valid predictions, and a loadable artifact."""
    settings = Settings(
        model_artifacts_directory=tmp_path,
        xgboost_n_estimators=8,
        xgboost_max_depth=2,
        model_validation_fraction=0.25,
    )
    trainer = DemandModelTrainer(settings)
    model = trainer.train(_feature_set(), version="demand-test-v1")

    assert set(model.models) == {1, 3, 6}
    assert all(metric.mae >= 0 for metric in model.metrics.values())
    prediction = model.predict(pd.DataFrame({"demand_lag_1h": [50.0], "hour": [4]}))
    assert set(prediction) == {1, 3, 6}
    store = DemandModelArtifactStore(settings)
    path = store.save(model)
    assert store.load(path).version == "demand-test-v1"


def test_trainer_rejects_missing_feature_contract() -> None:
    """Training fails before fitting when a feature contract column is missing."""
    frame = _feature_set().frame.drop(columns="hour")
    with pytest.raises(ValueError, match="missing columns"):
        DemandModelTrainer(Settings(xgboost_n_estimators=2)).train(
            DemandFeatureSet(frame, feature_columns=("demand_lag_1h", "hour"))
        )
