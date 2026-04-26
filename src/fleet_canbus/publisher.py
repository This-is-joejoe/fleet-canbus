"""Thin MQTT publisher around paho-mqtt v2."""
from __future__ import annotations

import json
import time

from paho.mqtt import client as mqtt_client


class MqttPublisher:
    """Publish JSON-serialized CAN frame batches to `fleet/{device_id}/can`."""

    def __init__(
        self,
        host: str,
        port: int = 1883,
        client_id: str = "",
        keepalive: int = 30,
    ) -> None:
        self.host = host
        self.port = port
        self.keepalive = keepalive
        self.client = mqtt_client.Client(
            mqtt_client.CallbackAPIVersion.VERSION2,
            client_id=client_id,
        )

    def connect(self) -> None:
        self.client.connect(self.host, self.port, keepalive=self.keepalive)
        self.client.loop_start()

    def disconnect(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()

    def publish_frames(
        self,
        device_id: str,
        frames: list[dict],
        qos: int = 1,
    ) -> None:
        topic = f"fleet/{device_id}/can"
        payload = json.dumps({
            "device_id": device_id,
            "ts_ms": int(time.time() * 1000),
            "frames": frames,
        })
        self.client.publish(topic, payload, qos=qos)
