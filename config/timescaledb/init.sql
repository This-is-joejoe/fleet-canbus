-- Enable TimescaleDB extension (idempotent).
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Raw telemetry: one row per simulator step per device.
CREATE TABLE IF NOT EXISTS battery_telemetry (
    time          TIMESTAMPTZ      NOT NULL,
    device_id     TEXT             NOT NULL,
    soc           DOUBLE PRECISION,
    voltage       DOUBLE PRECISION,
    current       DOUBLE PRECISION,
    temp_max      DOUBLE PRECISION,
    temp_min      DOUBLE PRECISION,
    temp_avg      DOUBLE PRECISION,
    pack_health   DOUBLE PRECISION,
    fault_flags   INTEGER,
    cell_voltages JSONB
);

SELECT create_hypertable('battery_telemetry', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_battery_device_time
    ON battery_telemetry (device_id, time DESC);

-- 1-minute rollup (per device).
CREATE MATERIALIZED VIEW IF NOT EXISTS telemetry_1min
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 minute', time) AS bucket,
    device_id,
    AVG(soc)         AS avg_soc,
    AVG(voltage)     AS avg_voltage,
    AVG(temp_max)    AS avg_temp_max,
    MAX(temp_max)    AS peak_temp,
    MAX(fault_flags) AS any_fault
FROM battery_telemetry
GROUP BY bucket, device_id
WITH NO DATA;

-- 1-hour rollup (per device), built on the 1-min view.
CREATE MATERIALIZED VIEW IF NOT EXISTS telemetry_1hour
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', bucket) AS bucket,
    device_id,
    AVG(avg_soc)   AS avg_soc,
    MAX(peak_temp) AS peak_temp,
    MAX(any_fault) AS any_fault
FROM telemetry_1min
GROUP BY time_bucket('1 hour', bucket), device_id
WITH NO DATA;

-- Refresh policies: rebuild recent buckets every 30s / 5min.
SELECT add_continuous_aggregate_policy('telemetry_1min',
    start_offset => INTERVAL '10 minutes',
    end_offset   => INTERVAL '10 seconds',
    schedule_interval => INTERVAL '30 seconds',
    if_not_exists => TRUE);

SELECT add_continuous_aggregate_policy('telemetry_1hour',
    start_offset => INTERVAL '3 hours',
    end_offset   => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE);
