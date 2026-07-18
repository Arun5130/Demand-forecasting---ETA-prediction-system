"""Tests proving demand feature point-in-time correctness and offline/online parity."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from delivery_ml.features import DemandFeatureBuilder


def _history() -> pd.DataFrame:
    start = datetime(2026, 7, 18, tzinfo=UTC)
    return pd.DataFrame(
        {"zone_id": ["zone-a"] * 8, "bucket_at": [start + timedelta(hours=i) for i in range(8)], "demand_count": list(range(1, 9))}
    )


def test_online_features_match_offline_training_row() -> None:
    """The feature assembler has identical offline and online behavior at a cut-off."""
    builder = DemandFeatureBuilder()
    history = _history()
    orders = history.loc[history.index.repeat(history["demand_count"])].rename(columns={"bucket_at": "ordered_at"})
    weather = pd.DataFrame({"zone_id": ["zone-a"], "observed_at": [history.iloc[0]["bucket_at"]], "condition": ["clear"], "temperature_celsius": [26]})
    training = builder.build_training_features(orders, weather=weather).frame
    prediction_at = history.iloc[6]["bucket_at"]
    online = builder.build_online_features("zone-a", prediction_at, history, weather=weather).frame.iloc[0]
    offline = training.loc[training["bucket_at"] == prediction_at].iloc[0]

    for column in builder.build_online_features("zone-a", prediction_at, history).feature_columns:
        assert online[column] == pytest.approx(offline[column], nan_ok=True)


def test_future_demand_and_weather_do_not_leak_into_online_features() -> None:
    """Changing future records cannot alter a feature vector at its earlier cut-off."""
    builder = DemandFeatureBuilder()
    history = _history()
    prediction_at = history.iloc[5]["bucket_at"]
    weather = pd.DataFrame({"zone_id": ["zone-a", "zone-a"], "observed_at": [history.iloc[2]["bucket_at"], history.iloc[6]["bucket_at"]], "condition": ["clear", "rain"], "temperature_celsius": [22, 10]})
    baseline = builder.build_online_features("zone-a", prediction_at, history, weather=weather).frame.iloc[0]
    changed = history.copy()
    changed.loc[changed.index >= 5, "demand_count"] = 999
    candidate = builder.build_online_features("zone-a", prediction_at, changed, weather=weather).frame.iloc[0]

    assert candidate["demand_lag_1h"] == baseline["demand_lag_1h"]
    assert candidate["demand_rolling_mean_3h"] == baseline["demand_rolling_mean_3h"]
    assert candidate["weather_temperature_celsius"] == 22


def test_orders_are_hourly_aggregated_with_empty_buckets_and_validation() -> None:
    """Sparse order facts become complete hourly history and invalid inputs fail fast."""
    builder = DemandFeatureBuilder()
    orders = pd.DataFrame({"zone_id": ["zone-a", "zone-a"], "ordered_at": [datetime(2026, 7, 18, 0, 5, tzinfo=UTC), datetime(2026, 7, 18, 2, 5, tzinfo=UTC)]})
    aggregated = builder.aggregate_orders(orders)

    assert aggregated["demand_count"].tolist() == [1, 0, 1]
    with pytest.raises(ValueError, match="required columns"):
        builder.aggregate_orders(pd.DataFrame({"zone_id": ["zone-a"]}))
