"""Publisher unit tests with a mocked paho client."""
import json
from unittest.mock import MagicMock

from fleet_canbus.publisher import MqttPublisher


def test_publish_signals_uses_correct_topic_and_payload():
    pub = MqttPublisher("localhost")
    pub.client = MagicMock()
    signals = {
        "SOC": 95.2,
        "Voltage_Pack": 398.5,
        "Current": -12.3,
        "Temp_Max": 31.1,
        "Temp_Min": 28.4,
        "Temp_Avg": 29.8,
        "Pack_Health": 99.0,
        "Fault_Flags": 0,
        "cell_voltages": [3.7] * 16,
    }

    pub.publish_signals("device-007", signals)

    pub.client.publish.assert_called_once()
    call_args, call_kwargs = pub.client.publish.call_args
    topic = call_args[0]
    payload = call_args[1]
    assert topic == "fleet/device-007/can"
    assert call_kwargs.get("qos") == 1

    parsed = json.loads(payload)
    assert parsed["device_id"] == "device-007"
    assert parsed["signals"] == signals
    assert isinstance(parsed["ts_ms"], int)


def test_publish_signals_respects_custom_qos():
    pub = MqttPublisher("localhost")
    pub.client = MagicMock()
    pub.publish_signals("dev", {"SOC": 50.0}, qos=0)
    _, call_kwargs = pub.client.publish.call_args
    assert call_kwargs.get("qos") == 0
