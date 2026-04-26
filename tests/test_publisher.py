"""Publisher unit tests with a mocked paho client."""
import json
from unittest.mock import MagicMock

from fleet_canbus.publisher import MqttPublisher


def test_publish_uses_correct_topic_and_payload():
    pub = MqttPublisher("localhost")
    pub.client = MagicMock()
    frames = [{"arbitration_id": 256, "name": "BMS_Pack_Status", "data": "00ff"}]

    pub.publish_frames("device-007", frames)

    pub.client.publish.assert_called_once()
    call_args, call_kwargs = pub.client.publish.call_args
    topic = call_args[0]
    payload = call_args[1]
    assert topic == "fleet/device-007/can"
    assert call_kwargs.get("qos") == 1

    parsed = json.loads(payload)
    assert parsed["device_id"] == "device-007"
    assert parsed["frames"] == frames
    assert isinstance(parsed["ts_ms"], int)


def test_publish_respects_custom_qos():
    pub = MqttPublisher("localhost")
    pub.client = MagicMock()
    pub.publish_frames("dev", [], qos=0)
    _, call_kwargs = pub.client.publish.call_args
    assert call_kwargs.get("qos") == 0
