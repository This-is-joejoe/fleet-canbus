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
