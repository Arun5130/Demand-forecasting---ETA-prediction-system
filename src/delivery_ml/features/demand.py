"""Leakage-safe zone demand features for offline training and online prediction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final

import numpy as np
import pandas as pd

REQUIRED_HISTORY_COLUMNS: Final[frozenset[str]] = frozenset({"zone_id", "bucket_at", "demand_count"})
REQUIRED_ORDER_COLUMNS: Final[frozenset[str]] = frozenset({"zone_id", "ordered_at"})
FEATURE_COLUMNS: Final[tuple[str, ...]] = (
    "demand_lag_1h",
    "demand_lag_3h",
    "demand_lag_6h",
    "demand_rolling_mean_3h",
    "demand_rolling_std_6h",
    "demand_ewma_6h",
    "hour",
    "weekday",
    "is_weekend",
    "is_holiday",
    "weather_temperature_celsius",
    "weather_precipitation_mm",
    "weather_wind_speed_kph",
    "weather_condition_code",
    "active_event_count",
    "event_expected_attendance",
)


@dataclass(frozen=True, slots=True)
class DemandFeatureSet:
    """Feature data plus its ordered model input columns."""

    frame: pd.DataFrame
    feature_columns: tuple[str, ...] = FEATURE_COLUMNS


class DemandFeatureBuilder:
    """Build demand features using a timestamp cut-off as the sole information boundary.

    All demand statistics are shifted one hour before aggregation. Weather observations
    are matched with a backward-asof join, and events are active only at the feature
    timestamp. Consequently, calling :meth:`build_online_features` yields the same
    values as the corresponding row created by :meth:`build_training_features`.
    """

    def build_training_features(
        self,
        orders: pd.DataFrame,
        weather: pd.DataFrame | None = None,
        holidays: pd.DataFrame | None = None,
        events: pd.DataFrame | None = None,
        horizons: tuple[int, ...] = (1, 3, 6),
    ) -> DemandFeatureSet:
        """Create hourly training rows with future horizon targets from historical orders."""
        history = self.aggregate_orders(orders)
        if history.empty:
            return DemandFeatureSet(self._empty_training_frame(horizons))

        pieces: list[pd.DataFrame] = []
        for zone_id, zone_history in history.groupby("zone_id", sort=False):
            rows = self._assemble_zone_features(str(zone_id), zone_history, weather, holidays, events)
            for horizon in horizons:
                if horizon not in {1, 3, 6}:
                    raise ValueError("Demand forecast horizons must be one of 1, 3, or 6 hours.")
                rows[f"target_demand_{horizon}h"] = zone_history["demand_count"].shift(-horizon).to_numpy()
            pieces.append(rows)
        return DemandFeatureSet(pd.concat(pieces, ignore_index=True))

    def build_online_features(
        self,
        zone_id: str,
        prediction_at: datetime,
        demand_history: pd.DataFrame,
        weather: pd.DataFrame | None = None,
        holidays: pd.DataFrame | None = None,
        events: pd.DataFrame | None = None,
    ) -> DemandFeatureSet:
        """Build one online feature row using only observations before ``prediction_at``."""
        normalized_at = self._normalize_timestamp(prediction_at)
        history = self._validate_history(demand_history)
        zone_history = history.loc[
            (history["zone_id"] == zone_id) & (history["bucket_at"] < normalized_at)
        ].copy()
        current = pd.DataFrame(
            {"zone_id": [zone_id], "bucket_at": [normalized_at], "demand_count": [np.nan]}
        )
        rows = pd.concat((zone_history, current), ignore_index=True).sort_values("bucket_at")
        feature_row = self._assemble_zone_features(zone_id, rows, weather, holidays, events).tail(1)
        return DemandFeatureSet(feature_row.reset_index(drop=True))

    def aggregate_orders(self, orders: pd.DataFrame) -> pd.DataFrame:
        """Aggregate order facts into complete per-zone hourly demand buckets."""
        if not REQUIRED_ORDER_COLUMNS.issubset(orders.columns):
            missing = sorted(REQUIRED_ORDER_COLUMNS.difference(orders.columns))
            raise ValueError(f"Orders are missing required columns: {missing}")
        source = orders.loc[:, ["zone_id", "ordered_at"]].copy()
        if source.empty:
            return pd.DataFrame(columns=["zone_id", "bucket_at", "demand_count"])
        source["ordered_at"] = self._timestamps(source["ordered_at"], "ordered_at")
        source["bucket_at"] = source["ordered_at"].dt.floor("h")
        counts = source.groupby(["zone_id", "bucket_at"]).size().reset_index(name="demand_count")
        parts: list[pd.DataFrame] = []
        for zone_id, group in counts.groupby("zone_id", sort=False):
            index = pd.date_range(group["bucket_at"].min(), group["bucket_at"].max(), freq="h", tz="UTC")
            complete = pd.DataFrame({"bucket_at": index})
            complete["zone_id"] = zone_id
            complete = complete.merge(group, on=["zone_id", "bucket_at"], how="left")
            complete["demand_count"] = complete["demand_count"].fillna(0).astype("int64")
            parts.append(complete)
        return pd.concat(parts, ignore_index=True)

    def _assemble_zone_features(
        self,
        zone_id: str,
        history: pd.DataFrame,
        weather: pd.DataFrame | None,
        holidays: pd.DataFrame | None,
        events: pd.DataFrame | None,
    ) -> pd.DataFrame:
        frame = history.loc[:, ["zone_id", "bucket_at", "demand_count"]].copy().sort_values("bucket_at")
        previous = frame["demand_count"].shift(1)
        frame["demand_lag_1h"] = previous
        frame["demand_lag_3h"] = frame["demand_count"].shift(3)
        frame["demand_lag_6h"] = frame["demand_count"].shift(6)
        frame["demand_rolling_mean_3h"] = previous.rolling(3, min_periods=3).mean()
        frame["demand_rolling_std_6h"] = previous.rolling(6, min_periods=6).std(ddof=0)
        frame["demand_ewma_6h"] = previous.ewm(span=6, adjust=False, min_periods=1).mean()
        frame["hour"] = frame["bucket_at"].dt.hour.astype("int8")
        frame["weekday"] = frame["bucket_at"].dt.weekday.astype("int8")
        frame["is_weekend"] = (frame["weekday"] >= 5).astype("int8")
        frame["is_holiday"] = self._holiday_flags(frame["bucket_at"], holidays)
        frame = self._add_weather(frame, zone_id, weather)
        frame = self._add_events(frame, zone_id, events)
        return frame

    def _add_weather(self, frame: pd.DataFrame, zone_id: str, weather: pd.DataFrame | None) -> pd.DataFrame:
        defaults = {
            "weather_temperature_celsius": np.nan,
            "weather_precipitation_mm": 0.0,
            "weather_wind_speed_kph": np.nan,
            "weather_condition_code": -1,
        }
        if weather is None or weather.empty:
            return frame.assign(**defaults)
        required = {"zone_id", "observed_at", "condition"}
        if not required.issubset(weather.columns):
            missing = sorted(required.difference(weather.columns))
            raise ValueError(f"Weather is missing required columns: {missing}")
        observations = weather.loc[weather["zone_id"] == zone_id].copy()
        if observations.empty:
            return frame.assign(**defaults)
        observations["observed_at"] = self._timestamps(observations["observed_at"], "observed_at")
        observations = observations.sort_values("observed_at")
        categories = {value: index for index, value in enumerate(sorted(observations["condition"].dropna().unique()))}
        observations["weather_condition_code"] = observations["condition"].map(categories).fillna(-1).astype("int16")
        for source, target, default in (
            ("temperature_celsius", "weather_temperature_celsius", np.nan),
            ("precipitation_mm", "weather_precipitation_mm", 0.0),
            ("wind_speed_kph", "weather_wind_speed_kph", np.nan),
        ):
            observations[target] = observations.get(source, default)
        return pd.merge_asof(
            frame.sort_values("bucket_at"),
            observations.loc[:, ["observed_at", *defaults]].sort_values("observed_at"),
            left_on="bucket_at",
            right_on="observed_at",
            direction="backward",
        ).drop(columns="observed_at")

    def _add_events(self, frame: pd.DataFrame, zone_id: str, events: pd.DataFrame | None) -> pd.DataFrame:
        frame["active_event_count"] = 0
        frame["event_expected_attendance"] = 0.0
        if events is None or events.empty:
            return frame
        required = {"name", "starts_at", "ends_at"}
        if not required.issubset(events.columns):
            missing = sorted(required.difference(events.columns))
            raise ValueError(f"Events are missing required columns: {missing}")
        source = events.copy()
        if "zone_id" in source:
            source = source.loc[source["zone_id"].isna() | (source["zone_id"] == zone_id)]
        source["starts_at"] = self._timestamps(source["starts_at"], "starts_at")
        source["ends_at"] = self._timestamps(source["ends_at"], "ends_at")
        attendance_source = (
            source["expected_attendance"]
            if "expected_attendance" in source
            else pd.Series(0, index=source.index)
        )
        attendance = pd.to_numeric(attendance_source, errors="coerce").fillna(0)
        for index, timestamp in frame["bucket_at"].items():
            active = source.loc[(source["starts_at"] <= timestamp) & (source["ends_at"] > timestamp)]
            frame.loc[index, "active_event_count"] = len(active)
            frame.loc[index, "event_expected_attendance"] = float(attendance.loc[active.index].sum())
        return frame

    def _holiday_flags(self, timestamps: pd.Series, holidays: pd.DataFrame | None) -> pd.Series:
        if holidays is None or holidays.empty:
            return pd.Series(0, index=timestamps.index, dtype="int8")
        if "holiday_date" not in holidays.columns:
            raise ValueError("Holidays are missing required column: ['holiday_date']")
        dates = pd.to_datetime(holidays["holiday_date"], errors="raise").dt.date
        known_dates = set(dates)
        return pd.Series(timestamps.dt.date.isin(known_dates), index=timestamps.index, dtype="int8")

    def _validate_history(self, history: pd.DataFrame) -> pd.DataFrame:
        if not REQUIRED_HISTORY_COLUMNS.issubset(history.columns):
            missing = sorted(REQUIRED_HISTORY_COLUMNS.difference(history.columns))
            raise ValueError(f"Demand history is missing required columns: {missing}")
        normalized = history.loc[:, ["zone_id", "bucket_at", "demand_count"]].copy()
        normalized["bucket_at"] = self._timestamps(normalized["bucket_at"], "bucket_at")
        normalized["demand_count"] = pd.to_numeric(normalized["demand_count"], errors="raise")
        if (normalized["demand_count"] < 0).any():
            raise ValueError("Demand history cannot contain negative demand counts.")
        return normalized.sort_values(["zone_id", "bucket_at"])

    def _empty_training_frame(self, horizons: tuple[int, ...]) -> pd.DataFrame:
        columns = ["zone_id", "bucket_at", "demand_count", *FEATURE_COLUMNS]
        columns.extend(f"target_demand_{horizon}h" for horizon in horizons)
        return pd.DataFrame(columns=columns)

    def _normalize_timestamp(self, value: datetime) -> pd.Timestamp:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            raise ValueError("Prediction timestamps must be timezone-aware.")
        return timestamp.tz_convert("UTC").floor("h")

    def _timestamps(self, values: pd.Series, field_name: str) -> pd.Series:
        timestamps = pd.to_datetime(values, utc=True, errors="raise")
        if timestamps.isna().any():
            raise ValueError(f"{field_name} contains null timestamps.")
        return timestamps
