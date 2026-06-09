"""Metric objects exist with the expected names and labels."""
from prometheus_client import REGISTRY

from fleet_subscriber import metrics


def test_messages_counter_increments():
    before = REGISTRY.get_sample_value("telemetry_messages_total") or 0.0
    metrics.messages_total.inc()
    after = REGISTRY.get_sample_value("telemetry_messages_total")
    assert after == before + 1


def test_dropped_counter_has_reason_label():
    before = REGISTRY.get_sample_value(
        "telemetry_dropped_total", {"reason": "malformed"}
    ) or 0.0
    metrics.dropped_total.labels(reason="malformed").inc()
    after = REGISTRY.get_sample_value(
        "telemetry_dropped_total", {"reason": "malformed"}
    )
    assert after == before + 1


def test_rows_inserted_increments_by_amount():
    before = REGISTRY.get_sample_value("telemetry_rows_inserted_total") or 0.0
    metrics.rows_inserted_total.inc(5)
    after = REGISTRY.get_sample_value("telemetry_rows_inserted_total")
    assert after == before + 5
