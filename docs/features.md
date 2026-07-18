# Feature engineering module

`DemandFeatureBuilder` produces zone-level hourly demand features for both training and
online inference. The exact same `_assemble_zone_features` path is used in both cases.

Demand lag, rolling, and EWMA values are shifted by one hour before calculation. At a
prediction timestamp, the builder excludes the current and future demand bucket. Weather
uses a backward-asof match, holidays use the feature date, and events contribute only when
their scheduled interval contains the feature timestamp.

Training data includes `target_demand_1h`, `target_demand_3h`, and `target_demand_6h`.
Drop rows with unavailable lag/target values before fitting a model; this preserves the
point-in-time boundary rather than imputing a future-derived value.
