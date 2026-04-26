# Architecture

> Replace this with a draw.io / excalidraw / mermaid diagram before Week 4 (per the portfolio plan completion checklist).

## Week 1 — current scope

```
[BatterySimulator] --encode--> [CAN frames] --JSON--> [MqttPublisher] --MQTT QoS 1--> [Mosquitto broker]
```

One simulator process per device. Scaled out via `docker compose --scale` in Week 3.

## Target — Week 4

```
┌──────────────┐     ┌────────────┐     ┌──────────────────┐     ┌──────────┐
│  CAN sources │────▶│  Mosquitto │────▶│ Subscriber +     │────▶│ Timescale│
│  (synthetic  │ MQTT│   (broker) │ MQTT│ Decoder          │ SQL │   DB     │
│   battery    │     │            │     │ (cantools +      │     │          │
│   fleet x50) │     └────────────┘     │  python-can)     │     └──────────┘
└──────────────┘                        └──────────────────┘           │
                                                                       ▼
                                                                 ┌──────────┐
                                                                 │ Grafana  │
                                                                 │ + Alerts │
                                                                 └──────────┘
                       ┌──────────────────┐
                       │  FastAPI Admin   │ ← register devices, query health
                       │  (API key auth)  │
                       └──────────────────┘
```

## Topic layout

`fleet/{device_id}/can` — JSON envelope per publish:

```json
{
  "device_id": "device-001",
  "ts_ms": 1714224000000,
  "frames": [
    {"arbitration_id": 256, "name": "BMS_Pack_Status", "data": "5a..."},
    ...
  ]
}
```

Sending decoded JSON (rather than raw CAN bytes) trades a small wire-size cost for a much simpler subscriber and easier debugging via `mosquitto_sub`. Can switch to protobuf in Week 3 if throughput requires it.

## Open questions / decisions for later

- **Wire format**: JSON (current) vs protobuf vs raw `can.Message` bytes — revisit when tuning Week 3 throughput.
- **Subscriber language**: Python (consistent with simulator) vs Go (better for high throughput) — default Python, fall back to Go only if 10k msg/s isn't reachable.
- **Schema evolution**: when DBC changes, how do older subscribers handle new signals? Add a DBC version field in the MQTT envelope when this becomes a real concern.
