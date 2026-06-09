"""Unit tests for the MQTT subscriber callback (no real broker)."""
import json
import queue
from unittest.mock import MagicMock

from prometheus_client import REGISTRY

from fleet_subscriber.subscriber import Subscriber


def _make_message(topic: str, payload: dict) -> MagicMock:
    msg = MagicMock()
    msg.topic = topic
    msg.payload = json.dumps(payload).encode("utf-8")
    return msg


def _valid_payload(device: str = "d") -> dict:
    return {
        "device_id": device,
        "ts_ms": 1,
        "signals": {
            "SOC": 1.0, "Voltage_Pack": 1.0, "Current": 1.0,
            "Temp_Max": 1.0, "Temp_Min": 1.0, "Temp_Avg": 1.0,
            "Pack_Health": 1.0, "Fault_Flags": 0,
            "cell_voltages": [3.7] * 16,
        },
    }


def test_on_message_parses_payload_and_enqueues():
    out_q = queue.Queue()
    sub = Subscriber("localhost", out_queue=out_q)

    payload = {
        "device_id": "dev-9",
        "ts_ms": 1715000000000,
        "signals": {
            "SOC": 88.1,
            "Voltage_Pack": 400.0,
            "Current": -8.0,
            "Temp_Max": 31.0,
            "Temp_Min": 28.0,
            "Temp_Avg": 29.5,
            "Pack_Health": 99.0,
            "Fault_Flags": 0,
            "cell_voltages": [3.7] * 16,
        },
    }
    sub._on_message(None, None, _make_message("fleet/dev-9/can", payload))

    assert out_q.qsize() == 1
    item = out_q.get()
    assert item.device_id == "dev-9"
    assert item.soc == 88.1
    assert item.fault_flags == 0
    assert len(item.cell_voltages) == 16


def test_on_message_drops_malformed_payload():
    out_q = queue.Queue()
    sub = Subscriber("localhost", out_queue=out_q)

    bad = MagicMock()
    bad.topic = "fleet/x/can"
    bad.payload = b"not-json"

    sub._on_message(None, None, bad)
    assert out_q.empty()


def test_on_message_drops_when_queue_full():
    out_q = queue.Queue(maxsize=1)
    out_q.put("placeholder")
    sub = Subscriber("localhost", out_queue=out_q)

    payload = {
        "device_id": "d",
        "ts_ms": 1,
        "signals": {
            "SOC": 1.0, "Voltage_Pack": 1.0, "Current": 1.0,
            "Temp_Max": 1.0, "Temp_Min": 1.0, "Temp_Avg": 1.0,
            "Pack_Health": 1.0, "Fault_Flags": 0,
            "cell_voltages": [3.7] * 16,
        },
    }
    sub._on_message(None, None, _make_message("fleet/d/can", payload))

    # queue still holds only the placeholder; payload was dropped
    assert out_q.qsize() == 1
    assert out_q.get() == "placeholder"


def test_on_message_increments_messages_total():
    sub = Subscriber("localhost", out_queue=queue.Queue())
    before = REGISTRY.get_sample_value("telemetry_messages_total") or 0.0
    sub._on_message(None, None, _make_message("fleet/dev/can", _valid_payload("dev")))
    after = REGISTRY.get_sample_value("telemetry_messages_total")
    assert after == before + 1


def test_on_message_malformed_increments_dropped():
    class _Bad:
        topic = "fleet/dev/can"
        payload = b"not json"

    sub = Subscriber("localhost", out_queue=queue.Queue())
    before = REGISTRY.get_sample_value(
        "telemetry_dropped_total", {"reason": "malformed"}
    ) or 0.0
    sub._on_message(None, None, _Bad())
    after = REGISTRY.get_sample_value(
        "telemetry_dropped_total", {"reason": "malformed"}
    )
    assert after == before + 1


def test_on_message_queue_full_increments_dropped():
    out_q = queue.Queue(maxsize=1)
    out_q.put("placeholder")
    sub = Subscriber("localhost", out_queue=out_q)
    before = REGISTRY.get_sample_value(
        "telemetry_dropped_total", {"reason": "queue_full"}
    ) or 0.0
    sub._on_message(None, None, _make_message("fleet/d/can", _valid_payload()))
    after = REGISTRY.get_sample_value(
        "telemetry_dropped_total", {"reason": "queue_full"}
    )
    assert after == before + 1
