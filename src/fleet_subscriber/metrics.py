"""Prometheus metrics for the subscriber service."""
from __future__ import annotations

from prometheus_client import Counter, Gauge, start_http_server

messages_total = Counter(
    "telemetry_messages_total",
    "MQTT messages accepted (parsed + enqueued) by the subscriber",
)
dropped_total = Counter(
    "telemetry_dropped_total",
    "Messages dropped before insert",
    ["reason"],  # "malformed" | "queue_full"
)
rows_inserted_total = Counter(
    "telemetry_rows_inserted_total",
    "Telemetry rows successfully inserted into TimescaleDB",
)
queue_depth = Gauge(
    "telemetry_queue_depth",
    "Current depth of the subscriber -> DB-writer queue",
)


def start_metrics_server(port: int = 8000) -> None:
    """Expose /metrics on the given port (runs a daemon thread)."""
    start_http_server(port)
