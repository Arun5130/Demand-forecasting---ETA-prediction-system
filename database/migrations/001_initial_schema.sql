-- Initial normalized PostgreSQL schema for Delivery ML Platform.
-- Application code creates UUID values, so this migration has no extension dependency.

CREATE TABLE IF NOT EXISTS delivery_zones (
    id UUID PRIMARY KEY,
    code VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(128) NOT NULL,
    city VARCHAR(128) NOT NULL,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_delivery_zones_valid_latitude CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90),
    CONSTRAINT ck_delivery_zones_valid_longitude CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180)
);

CREATE TABLE IF NOT EXISTS restaurants (
    id UUID PRIMARY KEY,
    external_id VARCHAR(128) UNIQUE,
    zone_id UUID NOT NULL REFERENCES delivery_zones(id) ON DELETE RESTRICT,
    name VARCHAR(256) NOT NULL,
    cuisine VARCHAR(128),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS drivers (
    id UUID PRIMARY KEY,
    external_id VARCHAR(128) UNIQUE,
    vehicle_type VARCHAR(32) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_drivers_valid_vehicle_type CHECK (vehicle_type IN ('bicycle', 'bike', 'car', 'scooter', 'walk'))
);

CREATE TABLE IF NOT EXISTS customers (
    id UUID PRIMARY KEY,
    external_id VARCHAR(128) UNIQUE,
    home_zone_id UUID REFERENCES delivery_zones(id) ON DELETE SET NULL,
    first_order_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS weather (
    id UUID PRIMARY KEY,
    zone_id UUID NOT NULL REFERENCES delivery_zones(id) ON DELETE RESTRICT,
    observed_at TIMESTAMPTZ NOT NULL,
    condition VARCHAR(64) NOT NULL,
    temperature_celsius DOUBLE PRECISION,
    precipitation_mm DOUBLE PRECISION NOT NULL DEFAULT 0,
    wind_speed_kph DOUBLE PRECISION,
    source VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_weather_observation UNIQUE (zone_id, observed_at, source),
    CONSTRAINT ck_weather_non_negative_precipitation CHECK (precipitation_mm >= 0)
);

CREATE TABLE IF NOT EXISTS holidays (
    id UUID PRIMARY KEY,
    holiday_date DATE NOT NULL,
    name VARCHAR(256) NOT NULL,
    region_code VARCHAR(16) NOT NULL DEFAULT 'IN',
    is_public_holiday BOOLEAN NOT NULL DEFAULT TRUE,
    source VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_holiday_identity UNIQUE (holiday_date, name, region_code)
);

CREATE TABLE IF NOT EXISTS events (
    id UUID PRIMARY KEY,
    zone_id UUID REFERENCES delivery_zones(id) ON DELETE SET NULL,
    name VARCHAR(256) NOT NULL,
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    expected_attendance INTEGER,
    source VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_events_end_after_start CHECK (ends_at > starts_at),
    CONSTRAINT ck_events_non_negative_attendance CHECK (expected_attendance IS NULL OR expected_attendance >= 0)
);

CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY,
    external_id VARCHAR(128) NOT NULL UNIQUE,
    zone_id UUID NOT NULL REFERENCES delivery_zones(id) ON DELETE RESTRICT,
    restaurant_id UUID NOT NULL REFERENCES restaurants(id) ON DELETE RESTRICT,
    driver_id UUID REFERENCES drivers(id) ON DELETE RESTRICT,
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    ordered_at TIMESTAMPTZ NOT NULL,
    accepted_at TIMESTAMPTZ,
    picked_up_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    status VARCHAR(32) NOT NULL,
    distance_km DOUBLE PRECISION,
    traffic_level VARCHAR(16),
    delivery_fee NUMERIC(10,2),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_orders_valid_status CHECK (status IN ('created', 'accepted', 'picked_up', 'delivered', 'cancelled')),
    CONSTRAINT ck_orders_non_negative_distance CHECK (distance_km IS NULL OR distance_km >= 0),
    CONSTRAINT ck_orders_valid_traffic_level CHECK (traffic_level IS NULL OR traffic_level IN ('low', 'medium', 'high', 'severe')),
    CONSTRAINT ck_orders_delivery_after_order CHECK (delivered_at IS NULL OR delivered_at >= ordered_at)
);

CREATE TABLE IF NOT EXISTS zone_demand (
    id UUID PRIMARY KEY,
    zone_id UUID NOT NULL REFERENCES delivery_zones(id) ON DELETE RESTRICT,
    observed_at TIMESTAMPTZ NOT NULL,
    horizon_hours INTEGER NOT NULL,
    demand_count INTEGER NOT NULL,
    dataset_version VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_zone_demand_identity UNIQUE (zone_id, observed_at, horizon_hours, dataset_version),
    CONSTRAINT ck_zone_demand_supported_horizon CHECK (horizon_hours IN (1, 3, 6)),
    CONSTRAINT ck_zone_demand_non_negative_demand CHECK (demand_count >= 0)
);

CREATE TABLE IF NOT EXISTS feature_store (
    id UUID PRIMARY KEY,
    zone_id UUID NOT NULL REFERENCES delivery_zones(id) ON DELETE RESTRICT,
    feature_timestamp TIMESTAMPTZ NOT NULL,
    available_at TIMESTAMPTZ NOT NULL,
    feature_set_version VARCHAR(64) NOT NULL,
    values JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_feature_store_identity UNIQUE (zone_id, feature_timestamp, feature_set_version),
    CONSTRAINT ck_feature_store_available_before_feature_time CHECK (available_at <= feature_timestamp)
);

CREATE TABLE IF NOT EXISTS model_registry (
    id UUID PRIMARY KEY,
    model_type VARCHAR(32) NOT NULL,
    version VARCHAR(128) NOT NULL,
    stage VARCHAR(32) NOT NULL,
    trained_at TIMESTAMPTZ NOT NULL,
    dataset_version VARCHAR(128) NOT NULL,
    hyperparameters JSONB NOT NULL,
    metrics JSONB NOT NULL,
    artifact_path TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    archived_at TIMESTAMPTZ,
    CONSTRAINT uq_model_registry_version UNIQUE (model_type, version),
    CONSTRAINT ck_model_registry_valid_model_type CHECK (model_type IN ('demand', 'eta')),
    CONSTRAINT ck_model_registry_valid_stage CHECK (stage IN ('development', 'staging', 'production', 'archived'))
);

CREATE TABLE IF NOT EXISTS prediction_logs (
    id UUID PRIMARY KEY,
    requested_at TIMESTAMPTZ NOT NULL,
    prediction_type VARCHAR(32) NOT NULL,
    zone_id UUID REFERENCES delivery_zones(id) ON DELETE SET NULL,
    model_registry_id UUID NOT NULL REFERENCES model_registry(id) ON DELETE RESTRICT,
    request_payload JSONB NOT NULL,
    response_payload JSONB NOT NULL,
    response_time_ms INTEGER NOT NULL,
    request_id VARCHAR(128),
    CONSTRAINT ck_prediction_logs_valid_prediction_type CHECK (prediction_type IN ('demand', 'eta')),
    CONSTRAINT ck_prediction_logs_non_negative_response_time CHECK (response_time_ms >= 0)
);

CREATE INDEX IF NOT EXISTS ix_delivery_zones_city_active ON delivery_zones (city, is_active);
CREATE INDEX IF NOT EXISTS ix_restaurants_zone_active ON restaurants (zone_id, is_active);
CREATE INDEX IF NOT EXISTS ix_customers_home_zone_id ON customers (home_zone_id);
CREATE INDEX IF NOT EXISTS ix_weather_zone_observed_at ON weather (zone_id, observed_at);
CREATE INDEX IF NOT EXISTS ix_holidays_date_region ON holidays (holiday_date, region_code);
CREATE INDEX IF NOT EXISTS ix_events_zone_schedule ON events (zone_id, starts_at, ends_at);
CREATE INDEX IF NOT EXISTS ix_orders_zone_ordered_at ON orders (zone_id, ordered_at);
CREATE INDEX IF NOT EXISTS ix_orders_restaurant_ordered_at ON orders (restaurant_id, ordered_at);
CREATE INDEX IF NOT EXISTS ix_orders_driver_ordered_at ON orders (driver_id, ordered_at);
CREATE INDEX IF NOT EXISTS ix_orders_status_ordered_at ON orders (status, ordered_at);
CREATE INDEX IF NOT EXISTS ix_zone_demand_lookup ON zone_demand (zone_id, observed_at, horizon_hours);
CREATE INDEX IF NOT EXISTS ix_feature_store_zone_time ON feature_store (zone_id, feature_timestamp);
CREATE UNIQUE INDEX IF NOT EXISTS uq_model_registry_one_active ON model_registry (model_type) WHERE is_active;
CREATE INDEX IF NOT EXISTS ix_model_registry_type_stage ON model_registry (model_type, stage);
CREATE INDEX IF NOT EXISTS ix_prediction_logs_requested_at ON prediction_logs (requested_at);
CREATE INDEX IF NOT EXISTS ix_prediction_logs_zone_requested_at ON prediction_logs (zone_id, requested_at);
CREATE INDEX IF NOT EXISTS ix_prediction_logs_request_id ON prediction_logs (request_id);

CREATE OR REPLACE VIEW latest_zone_features AS
SELECT DISTINCT ON (zone_id, feature_set_version)
    id, zone_id, feature_timestamp, available_at, feature_set_version, values, created_at, updated_at
FROM feature_store
ORDER BY zone_id, feature_set_version, feature_timestamp DESC;

CREATE OR REPLACE VIEW active_models AS
SELECT id, model_type, version, stage, trained_at, dataset_version, metrics, artifact_path
FROM model_registry
WHERE is_active = TRUE;
