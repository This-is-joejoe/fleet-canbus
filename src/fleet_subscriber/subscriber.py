"""MQTT subscriber: receives signal JSON, enqueues parsed Telemetry."""
from __future__ import annotations

import json
import logging
import queue

from paho.mqtt import client as mqtt_client

from . import metrics
from .db_writer import Telemetry

log = logging.getLogger("fleet_subscriber.subscriber")

TOPIC_PATTERN = "fleet/+/can"


class Subscriber:
    def __init__(
        self,
        host: str,
        port: int = 1883,
        out_queue: queue.Queue | None = None,
        client_id: str = "fleet-subscriber",
        keepalive: int = 30,
    ) -> None:
        self.host = host
        self.port = port
        self.keepalive = keepalive
        self.q = out_queue if out_queue is not None else queue.Queue(maxsize=10000)
        self.client = mqtt_client.Client(
            mqtt_client.CallbackAPIVersion.VERSION2,
            client_id=client_id,
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def start(self) -> None:
        self.client.connect(self.host, self.port, keepalive=self.keepalive)
        self.client.loop_start()

    def stop(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()

    def _on_connect(self, client, _userdata, _flags, _reason_code, _properties=None):
        client.subscribe(TOPIC_PATTERN, qos=1)
        log.info("subscribed to %s", TOPIC_PATTERN)

    def _on_message(self, _client, _userdata, msg) -> None:
        try:
            payload = json.loads(msg.payload)
            signals = payload["signals"]
            item = Telemetry(
                ts_ms=int(payload["ts_ms"]),
                device_id=str(payload["device_id"]),
                soc=float(signals["SOC"]),
                voltage=float(signals["Voltage_Pack"]),
                current=float(signals["Current"]),
                temp_max=float(signals["Temp_Max"]),
                temp_min=float(signals["Temp_Min"]),
                temp_avg=float(signals["Temp_Avg"]),
                pack_health=float(signals["Pack_Health"]),
                fault_flags=int(signals["Fault_Flags"]),
                cell_voltages=[float(v) for v in signals["cell_voltages"]],
            )
        except (ValueError, KeyError, TypeError):
            metrics.dropped_total.labels(reason="malformed").inc()
            log.warning("dropping malformed payload on %s", msg.topic)
            return

        try:
            self.q.put_nowait(item)
            metrics.messages_total.inc()
        except queue.Full:
            metrics.dropped_total.labels(reason="queue_full").inc()
            log.warning("queue full; dropping message from %s", item.device_id)
