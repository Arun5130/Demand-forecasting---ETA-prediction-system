"""Validated ETA feature assembly shared by offline training and online inference."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

ETA_NUMERIC_FEATURES = ("distance_km", "hour", "weekday", "predicted_demand")
ETA_CATEGORICAL_FEATURES = ("traffic_level", "weather_condition", "vehicle_type", "restaurant_id")
ETA_FEATURE_COLUMNS = (*ETA_NUMERIC_FEATURES, *ETA_CATEGORICAL_FEATURES)
REQUIRED_ETA_COLUMNS = frozenset({"distance_km", "traffic_level", "weather_condition", "vehicle_type", "restaurant_id", "predicted_demand"})


@dataclass(frozen=True, slots=True)
class EtaFeatureSet:
    """ETA feature matrix and its stable numeric/categorical feature contract."""

    frame: pd.DataFrame
    numeric_features: tuple[str, ...] = ETA_NUMERIC_FEATURES
    categorical_features: tuple[str, ...] = ETA_CATEGORICAL_FEATURES

    @property
    def feature_columns(self) -> tuple[str, ...]:
        """Return model input columns in deterministic order."""
        return (*self.numeric_features, *self.categorical_features)


class EtaFeatureBuilder:
    """Prepare ETA features without target leakage or divergent online transformations."""

    def build_training_features(self, deliveries: pd.DataFrame) -> EtaFeatureSet:
        """Validate historical delivery rows and retain the ETA target for model training."""
        if "eta_seconds" not in deliveries.columns:
            raise ValueError("ETA training data is missing required column: ['eta_seconds']")
        frame = self._normalize(deliveries)
        frame["eta_seconds"] = pd.to_numeric(frame["eta_seconds"], errors="raise")
        if (frame["eta_seconds"] <= 0).any():
            raise ValueError("ETA targets must be positive seconds.")
        return EtaFeatureSet(frame)

    def build_online_features(self, request_features: pd.DataFrame) -> EtaFeatureSet:
        """Validate online request features using the exact training transformation path."""
        return EtaFeatureSet(self._normalize(request_features))

    def _normalize(self, source: pd.DataFrame) -> pd.DataFrame:
        missing = sorted(REQUIRED_ETA_COLUMNS.difference(source.columns))
        if missing:
            raise ValueError(f"ETA features are missing required columns: {missing}")
        frame = source.copy()
        if "ordered_at" in frame.columns:
            timestamps = pd.to_datetime(frame["ordered_at"], utc=True, errors="raise")
            frame["hour"] = timestamps.dt.hour
            frame["weekday"] = timestamps.dt.weekday
        required_calendar = {"hour", "weekday"}
        missing_calendar = sorted(required_calendar.difference(frame.columns))
        if missing_calendar:
            raise ValueError(f"ETA features require ordered_at or columns: {missing_calendar}")
        for field in ETA_NUMERIC_FEATURES:
            frame[field] = pd.to_numeric(frame[field], errors="raise")
        if (frame["distance_km"] < 0).any() or (frame["predicted_demand"] < 0).any():
            raise ValueError("Distance and predicted demand must be non-negative.")
        if not frame["hour"].between(0, 23).all() or not frame["weekday"].between(0, 6).all():
            raise ValueError("Hour must be 0-23 and weekday must be 0-6.")
        for field in ETA_CATEGORICAL_FEATURES:
            values = frame[field].fillna("unknown").astype(str).str.strip().str.lower()
            if values.eq("").any():
                raise ValueError(f"ETA feature {field} cannot be blank.")
            frame[field] = values
        return frame.loc[:, [*ETA_FEATURE_COLUMNS, *(["eta_seconds"] if "eta_seconds" in frame else [])]]
