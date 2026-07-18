"""Chronological XGBoost training and registry activation for demand forecasting."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    mean_absolute_error,
    mean_absolute_percentage_error,
    root_mean_squared_error,
)
from sqlalchemy import select
from xgboost import XGBRegressor

from delivery_ml.config import Settings
from delivery_ml.database.models import ModelRegistryEntry
from delivery_ml.database.session import DatabaseRuntime
from delivery_ml.features import DemandFeatureSet
from delivery_ml.observability import get_logger

logger = get_logger(__name__)
HORIZONS = (1, 3, 6)


@dataclass(frozen=True, slots=True)
class RegressionMetrics:
    """Standard regression metrics for one demand forecast horizon."""

    mae: float
    rmse: float
    mape: float


@dataclass(slots=True)
class TrainedDemandModel:
    """Three horizon-specific regressors with reproducible feature and metric metadata."""

    version: str
    trained_at: datetime
    feature_columns: tuple[str, ...]
    models: dict[int, XGBRegressor]
    metrics: dict[int, RegressionMetrics]
    hyperparameters: dict[str, Any]

    def predict(self, features: pd.DataFrame) -> dict[int, np.ndarray]:
        """Predict all supported horizons after enforcing the trained feature contract."""
        missing = sorted(set(self.feature_columns).difference(features.columns))
        if missing:
            raise ValueError(f"Prediction features are missing columns: {missing}")
        matrix = features.loc[:, self.feature_columns]
        if matrix.isna().any().any():
            raise ValueError("Prediction features contain null values.")
        return {horizon: model.predict(matrix) for horizon, model in self.models.items()}


class DemandModelTrainer:
    """Train independent XGBoost regressors with chronological holdout evaluation."""

    def __init__(self, settings: Settings) -> None:
        """Initialize model hyperparameters from validated runtime configuration."""
        self._settings = settings

    def train(self, feature_set: DemandFeatureSet, version: str | None = None) -> TrainedDemandModel:
        """Fit all horizons using future-held-out data and return a persistable model bundle."""
        frame = feature_set.frame.copy().sort_values("bucket_at")
        self._validate_feature_set(frame, feature_set.feature_columns)
        parameters = self._hyperparameters()
        models: dict[int, XGBRegressor] = {}
        metrics: dict[int, RegressionMetrics] = {}
        for horizon in HORIZONS:
            target = f"target_demand_{horizon}h"
            dataset = frame.dropna(subset=[*feature_set.feature_columns, target])
            split_index = int(len(dataset) * (1 - self._settings.model_validation_fraction))
            if split_index < 1 or split_index >= len(dataset):
                raise ValueError(f"Insufficient chronologically ordered data for {horizon}h training.")
            train_frame, validation_frame = dataset.iloc[:split_index], dataset.iloc[split_index:]
            model = XGBRegressor(**parameters)
            model.fit(train_frame.loc[:, feature_set.feature_columns], train_frame[target])
            prediction = model.predict(validation_frame.loc[:, feature_set.feature_columns])
            actual = validation_frame[target].to_numpy(dtype=float)
            models[horizon] = model
            metrics[horizon] = RegressionMetrics(
                mae=float(mean_absolute_error(actual, prediction)),
                rmse=float(root_mean_squared_error(actual, prediction)),
                mape=float(mean_absolute_percentage_error(actual, prediction)),
            )
        trained_at = datetime.now(UTC)
        model_version = version or trained_at.strftime("demand-%Y%m%dT%H%M%SZ")
        result = TrainedDemandModel(
            version=model_version,
            trained_at=trained_at,
            feature_columns=feature_set.feature_columns,
            models=models,
            metrics=metrics,
            hyperparameters=parameters,
        )
        logger.info("demand_model_trained", extra={"version": result.version, "metrics": self.metrics_payload(result)})
        return result

    def metrics_payload(self, model: TrainedDemandModel) -> dict[str, float]:
        """Flatten per-horizon metrics for the PostgreSQL model registry."""
        payload: dict[str, float] = {}
        for horizon, metrics in model.metrics.items():
            for name, value in asdict(metrics).items():
                payload[f"{horizon}h_{name}"] = value
        return payload

    def _hyperparameters(self) -> dict[str, Any]:
        return {
            "objective": "reg:squarederror",
            "n_estimators": self._settings.xgboost_n_estimators,
            "max_depth": self._settings.xgboost_max_depth,
            "learning_rate": self._settings.xgboost_learning_rate,
            "subsample": self._settings.xgboost_subsample,
            "colsample_bytree": self._settings.xgboost_colsample_bytree,
            "min_child_weight": self._settings.xgboost_min_child_weight,
            "random_state": self._settings.random_seed,
            "n_jobs": self._settings.xgboost_n_jobs,
        }

    @staticmethod
    def _validate_feature_set(frame: pd.DataFrame, columns: tuple[str, ...]) -> None:
        required = {"bucket_at", *(f"target_demand_{horizon}h" for horizon in HORIZONS), *columns}
        missing = sorted(required.difference(frame.columns))
        if missing:
            raise ValueError(f"Training data is missing columns: {missing}")
        if not pd.api.types.is_datetime64_any_dtype(frame["bucket_at"]):
            raise ValueError("Training bucket_at values must be datetime-like.")


class DemandModelArtifactStore:
    """Persist and load complete trained-demand model bundles using atomic replacement."""

    def __init__(self, settings: Settings) -> None:
        """Resolve the configured artifact root without relying on process working state later."""
        self._directory = settings.resolved_model_artifacts_directory

    def save(self, model: TrainedDemandModel) -> Path:
        """Write a complete model bundle atomically and return its immutable artifact path."""
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._directory / f"{model.version}.joblib"
        temporary = path.with_suffix(".joblib.tmp")
        joblib.dump(model, temporary)
        temporary.replace(path)
        logger.info("demand_model_artifact_saved", extra={"path": str(path), "version": model.version})
        return path

    def load(self, artifact_path: Path) -> TrainedDemandModel:
        """Load and type-check a persisted model bundle before inference uses it."""
        loaded = joblib.load(artifact_path)
        if not isinstance(loaded, TrainedDemandModel):
            raise TypeError("Artifact does not contain a TrainedDemandModel.")
        return loaded


class ModelRegistryService:
    """Transactionally register and activate trained demand model artifacts."""

    def register_demand_model(
        self,
        runtime: DatabaseRuntime,
        model: TrainedDemandModel,
        artifact_path: Path,
        dataset_version: str,
        stage: str,
    ) -> ModelRegistryEntry:
        """Archive prior active demand model and atomically activate the supplied registry entry."""
        if stage not in {"development", "staging", "production"}:
            raise ValueError("Model registry stage must be development, staging, or production.")
        with runtime.session_scope() as session:
            active_models = session.scalars(
                select(ModelRegistryEntry)
                .where(ModelRegistryEntry.model_type == "demand", ModelRegistryEntry.is_active.is_(True))
                .with_for_update()
            ).all()
            for active in active_models:
                active.is_active = False
                active.archived_at = datetime.now(UTC)
            entry = ModelRegistryEntry(
                model_type="demand",
                version=model.version,
                stage=stage,
                trained_at=model.trained_at,
                dataset_version=dataset_version,
                hyperparameters=model.hyperparameters,
                metrics=DemandModelTrainer(self._settings).metrics_payload(model),
                artifact_path=str(artifact_path),
                is_active=True,
            )
            session.add(entry)
        logger.info("demand_model_registered", extra={"version": model.version, "stage": stage})
        return entry

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
