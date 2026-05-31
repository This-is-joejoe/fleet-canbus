"""Unit tests for the MQTT subscriber callback (no real broker)."""
import json
import queue
from unittest.mock import MagicMock

from fleet_subscriber.subscriber import Subscriber


def _make_message(topic: str, payload: dict) -> MagicMock:
    msg = MagicMock()
    msg.topic = topic
    msg.payload = json.dumps(payload).encode("utf-8")
    return msg


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
