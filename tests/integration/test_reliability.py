# tests/integration/test_reliability.py
"""Zero message loss across a subscriber restart, against a real MQTT broker.

Establish a persistent session + subscription, go offline, publish while offline,
reconnect with the same client_id, and assert every QoS-1 message is delivered.
"""
import os
import queue
import socket
import time
import uuid

import pytest

from fleet_canbus.publisher import MqttPublisher
from fleet_subscriber.subscriber import Subscriber

pytestmark = pytest.mark.integration

BROKER_HOST = os.getenv("MQTT_HOST", "localhost")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))

SIGNALS = {
    "SOC": 95.0, "Voltage_Pack": 400.0, "Current": 0.0,
    "Temp_Max": 25.0, "Temp_Min": 25.0, "Temp_Avg": 25.0,
    "Pack_Health": 99.0, "Fault_Flags": 0,
    "cell_voltages": [3.7] * 16,
}


def _broker_reachable() -> bool:
    try:
        with socket.create_connection((BROKER_HOST, BROKER_PORT), timeout=2):
            return True
    except OSError:
        return False


@pytest.fixture(autouse=True)
def _require_broker():
    if not _broker_reachable():
        pytest.skip(f"no MQTT broker at {BROKER_HOST}:{BROKER_PORT}")


def _drain(q: queue.Queue, expected: int, timeout: float) -> list:
    items: list = []
    deadline = time.monotonic() + timeout
    while len(items) < expected and time.monotonic() < deadline:
        try:
            items.append(q.get(timeout=0.5))
        except queue.Empty:
            pass
    return items


def test_no_loss_across_subscriber_restart():
    client_id = f"itest-sub-{uuid.uuid4().hex[:8]}"
    device_id = f"itest-dev-{uuid.uuid4().hex[:8]}"
    q: queue.Queue = queue.Queue(maxsize=10000)
    n = 20

    # 1. Establish persistent session + QoS-1 subscription, then go offline.
    sub = Subscriber(BROKER_HOST, BROKER_PORT, out_queue=q, client_id=client_id)
    sub.start()
    time.sleep(1.0)            # allow SUBACK to register the subscription
    sub.stop()
    time.sleep(0.5)

    # 2. Publish while the subscriber is OFFLINE (broker must queue these).
    pub = MqttPublisher(BROKER_HOST, BROKER_PORT,
                        client_id=f"itest-pub-{uuid.uuid4().hex[:8]}")
    pub.connect()
    for _ in range(n):
        pub.publish_signals(device_id, SIGNALS, qos=1)
    time.sleep(1.0)            # let the broker persist queued messages
    pub.disconnect()

    # 3. Reconnect with the SAME client_id → broker replays the queued messages.
    sub2 = Subscriber(BROKER_HOST, BROKER_PORT, out_queue=q, client_id=client_id)
    sub2.start()
    received = _drain(q, n, timeout=15.0)
    sub2.stop()

    assert len(received) == n, f"expected {n} messages, got {len(received)}"
