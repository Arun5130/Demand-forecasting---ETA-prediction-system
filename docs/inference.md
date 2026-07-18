# Inference core

`ActiveModelLoader` reads the active model-registry entry and type-checks its Joblib
artifact. `DemandInferenceService` returns the 1h, 3h, and 6h forecasts; `EtaInferenceService`
returns ETA seconds. Both validate the persisted model feature contract before prediction.
