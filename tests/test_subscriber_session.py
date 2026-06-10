"""Subscriber connects with a non-clean MQTT v5 session so the broker queues
messages while it is offline."""
from unittest.mock import MagicMock

from fleet_subscriber import subscriber as sub_mod


def test_connects_with_persistent_v5_session(monkeypatch):
    fake_client = MagicMock()
    monkeypatch.setattr(sub_mod.mqtt_client, "Client", lambda *a, **k: fake_client)

    sub = sub_mod.Subscriber("broker", 1883, client_id="fleet-subscriber-main",
                             session_expiry_s=3600)
    sub.start()

    # client constructed for MQTT v5
    # (protocol passed through kwargs captured below)
    args, kwargs = fake_client.connect.call_args
    assert kwargs["clean_start"] is False
    assert kwargs["properties"].SessionExpiryInterval == 3600
