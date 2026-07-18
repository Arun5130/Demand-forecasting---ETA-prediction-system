# Demand model training

`DemandModelTrainer` fits independent XGBoost regressors for the next 1, 3, and 6 hours.
It orders rows by `bucket_at`, trains on the oldest configured fraction, and evaluates on
the newest holdout. It reports MAE, RMSE, and MAPE for every horizon.

`DemandModelArtifactStore` writes an atomic Joblib bundle containing the feature contract,
all three estimators, metrics, hyperparameters, version, and timestamp. `ModelRegistryService`
archives the preceding active demand model and activates the new PostgreSQL registry entry
within one transaction.

All XGBoost hyperparameters, validation split, random seed, and artifact directory are
environment-configurable. Use the leakage-safe `DemandFeatureBuilder` output and remove
rows without sufficient historical lags or future labels before fitting.

## ETA model

`EtaFeatureBuilder` consistently validates distance, predicted demand, time fields, and
normalizes categorical delivery context. `EtaModelTrainer` applies one-hot encoding with
unknown-category tolerance before fitting XGBoost. It evaluates chronologically held-out
rows using MAE, RMSE, and R², then `EtaModelArtifactStore` and `EtaModelRegistryService`
persist and activate the resulting model.
