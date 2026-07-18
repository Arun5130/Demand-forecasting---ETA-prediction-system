"""Chronological ETA XGBoost model training, artifacts, and registry activation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sqlalchemy import select
from xgboost import XGBRegressor

from delivery_ml.config import Settings
from delivery_ml.database.models import ModelRegistryEntry
from delivery_ml.database.session import DatabaseRuntime
from delivery_ml.features import EtaFeatureSet
from delivery_ml.observability import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class EtaMetrics:
    """ETA regression evaluation metrics."""

    mae: float
    rmse: float
    r2: float


@dataclass(slots=True)
class TrainedEtaModel:
    """Persistable ETA pipeline, input contract, and evaluation metadata."""

    version: str
    trained_at: datetime
    feature_columns: tuple[str, ...]
    pipeline: Pipeline
    metrics: EtaMetrics
    hyperparameters: dict[str, Any]

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        """Validate the feature contract and return ETA predictions in seconds."""
        missing = sorted(set(self.feature_columns).difference(features.columns))
        if missing:
            raise ValueError(f"Prediction features are missing columns: {missing}")
        matrix = features.loc[:, self.feature_columns]
        if matrix.isna().any().any():
            raise ValueError("Prediction features contain null values.")
        return np.asarray(self.pipeline.predict(matrix))


class EtaModelTrainer:
    """Train a categorical-aware XGBoost ETA pipeline using a chronological holdout."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def train(self, feature_set: EtaFeatureSet, version: str | None = None) -> TrainedEtaModel:
        """Fit the ETA pipeline and report MAE, RMSE, and R² on future holdout rows."""
        frame = feature_set.frame.copy()
        if "eta_seconds" not in frame.columns:
            raise ValueError("ETA training features must include eta_seconds.")
        dataset = frame.dropna(subset=[*feature_set.feature_columns, "eta_seconds"])
        if len(dataset) < 2:
            raise ValueError("ETA training requires at least two complete rows.")
        split_index = int(len(dataset) * (1 - self._settings.model_validation_fraction))
        if split_index < 1 or split_index >= len(dataset):
            raise ValueError("Insufficient chronologically ordered data for ETA training.")
        train_frame, validation_frame = dataset.iloc[:split_index], dataset.iloc[split_index:]
        hyperparameters = self._hyperparameters()
        transformer = ColumnTransformer(
            [("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=False), feature_set.categorical_features)],
            remainder="passthrough",
            verbose_feature_names_out=False,
        )
        pipeline = Pipeline(
            [("features", transformer), ("regressor", XGBRegressor(**hyperparameters))]
        )
        pipeline.fit(train_frame.loc[:, feature_set.feature_columns], train_frame["eta_seconds"])
        prediction = pipeline.predict(validation_frame.loc[:, feature_set.feature_columns])
        actual = validation_frame["eta_seconds"].to_numpy(dtype=float)
        trained_at = datetime.now(UTC)
        result = TrainedEtaModel(
            version=version or trained_at.strftime("eta-%Y%m%dT%H%M%SZ"),
            trained_at=trained_at,
            feature_columns=feature_set.feature_columns,
            pipeline=pipeline,
            metrics=EtaMetrics(
                mae=float(mean_absolute_error(actual, prediction)),
                rmse=float(root_mean_squared_error(actual, prediction)),
                r2=float(r2_score(actual, prediction)),
            ),
            hyperparameters=hyperparameters,
        )
        logger.info("eta_model_trained", extra={"version": result.version, "metrics": asdict(result.metrics)})
        return result

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


class EtaModelArtifactStore:
    """Atomically persist and load complete ETA pipeline bundles."""

    def __init__(self, settings: Settings) -> None:
        self._directory = settings.resolved_model_artifacts_directory

    def save(self, model: TrainedEtaModel) -> Path:
        """Persist one versioned ETA artifact without leaving a partial final file."""
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._directory / f"{model.version}.joblib"
        temporary = path.with_suffix(".joblib.tmp")
        joblib.dump(model, temporary)
        temporary.replace(path)
        return path

    def load(self, artifact_path: Path) -> TrainedEtaModel:
        """Load an ETA artifact only when it contains the expected bundle type."""
        loaded = joblib.load(artifact_path)
        if not isinstance(loaded, TrainedEtaModel):
            raise TypeError("Artifact does not contain a TrainedEtaModel.")
        return loaded


class EtaModelRegistryService:
    """Register and activate an ETA model with an atomic active-model transition."""

    def register(
        self,
        runtime: DatabaseRuntime,
        model: TrainedEtaModel,
        artifact_path: Path,
        dataset_version: str,
        stage: str,
    ) -> ModelRegistryEntry:
        """Archive prior ETA production candidate and persist the active replacement."""
        if stage not in {"development", "staging", "production"}:
            raise ValueError("Model registry stage must be development, staging, or production.")
        with runtime.session_scope() as session:
            active_models = session.scalars(
                select(ModelRegistryEntry)
                .where(ModelRegistryEntry.model_type == "eta", ModelRegistryEntry.is_active.is_(True))
                .with_for_update()
            ).all()
            for active in active_models:
                active.is_active = False
                active.archived_at = datetime.now(UTC)
            entry = ModelRegistryEntry(
                model_type="eta",
                version=model.version,
                stage=stage,
                trained_at=model.trained_at,
                dataset_version=dataset_version,
                hyperparameters=model.hyperparameters,
                metrics=asdict(model.metrics),
                artifact_path=str(artifact_path),
                is_active=True,
            )
            session.add(entry)
        logger.info("eta_model_registered", extra={"version": model.version, "stage": stage})
        return entry
