"""Load active registered artifacts and execute typed demand and ETA predictions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from sqlalchemy import select

from delivery_ml.database.models import ModelRegistryEntry
from delivery_ml.database.session import DatabaseRuntime
from delivery_ml.training import (
    DemandModelArtifactStore,
    EtaModelArtifactStore,
    TrainedDemandModel,
    TrainedEtaModel,
)


class ModelUnavailableError(RuntimeError):
    """Raised when inference cannot resolve an active, valid model artifact."""


@dataclass(frozen=True, slots=True)
class DemandPrediction:
    """Demand predictions for each supported horizon and serving model version."""

    next_1_hour: float
    next_3_hours: float
    next_6_hours: float
    model_version: str


@dataclass(frozen=True, slots=True)
class EtaPrediction:
    """ETA seconds and serving model version."""

    eta_seconds: float
    model_version: str


class ActiveModelLoader:
    """Resolve active database registry entries and type-check their persisted artifacts."""

    def __init__(self, runtime: DatabaseRuntime, demand_store: DemandModelArtifactStore, eta_store: EtaModelArtifactStore) -> None:
        self._runtime = runtime
        self._demand_store = demand_store
        self._eta_store = eta_store

    def demand(self) -> TrainedDemandModel:
        """Load the active demand artifact, rejecting mismatched or missing registry state."""
        entry = self._active_entry("demand")
        return self._demand_store.load(Path(entry.artifact_path))

    def eta(self) -> TrainedEtaModel:
        """Load the active ETA artifact, rejecting mismatched or missing registry state."""
        entry = self._active_entry("eta")
        return self._eta_store.load(Path(entry.artifact_path))

    def _active_entry(self, model_type: str) -> ModelRegistryEntry:
        with self._runtime.session_scope() as session:
            entry = session.scalar(select(ModelRegistryEntry).where(ModelRegistryEntry.model_type == model_type, ModelRegistryEntry.is_active.is_(True)))
        if entry is None:
            raise ModelUnavailableError(f"No active {model_type} model is registered.")
        return entry


class DemandInferenceService:
    """Execute all three active demand horizons using one validated feature row."""

    def predict(self, model: TrainedDemandModel, features: pd.DataFrame) -> DemandPrediction:
        """Return non-negative demand values from a trained demand model bundle."""
        values = model.predict(features)
        return DemandPrediction(
            next_1_hour=max(0.0, float(values[1][0])),
            next_3_hours=max(0.0, float(values[3][0])),
            next_6_hours=max(0.0, float(values[6][0])),
            model_version=model.version,
        )


class EtaInferenceService:
    """Execute ETA inference and protect clients from implausible negative durations."""

    def predict(self, model: TrainedEtaModel, features: pd.DataFrame) -> EtaPrediction:
        """Return ETA seconds from one validated ETA feature row."""
        return EtaPrediction(eta_seconds=max(0.0, float(model.predict(features)[0])), model_version=model.version)
