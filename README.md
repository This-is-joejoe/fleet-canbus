# Fleet CAN-bus Telemetry Pipeline

<!-- TODO: replace <YOUR_USERNAME>/fleet-canbus once GitHub repo is created -->
[![CI](https://github.com/<YOUR_USERNAME>/fleet-canbus/actions/workflows/ci.yml/badge.svg)](https://github.com/<YOUR_USERNAME>/fleet-canbus/actions/workflows/ci.yml)

Real-time CAN-bus telemetry pipeline simulating a fleet of battery-powered devices. Synthetic CAN frames → MQTT broker → time-series database → Grafana dashboards + alerting.

> Part of the `battery-platform` portfolio. See `../soh-model/` for the ML analytics layer.

---

## Architecture (target, Week 4)

```
┌──────────────┐     ┌────────────┐     ┌──────────────────┐     ┌──────────┐
│  CAN sources │────▶│  Mosquitto │────▶│ Subscriber +     │────▶│ Timescale│
│  (synthetic  │ MQTT│   (broker) │ MQTT│ Decoder (cantools│ SQL │   DB     │
│   battery    │     │            │     │ + python-can)    │     │          │
│   fleet)     │     └────────────┘     └──────────────────┘     └──────────┘
└──────────────┘                                                       │
                                                                       ▼
                                                                 ┌──────────┐
                                                                 │ Grafana  │
                                                                 │ + Alerts │
                                                                 └──────────┘
                       ┌──────────────────┐
                       │  FastAPI Admin   │ ← register devices, query health
                       └──────────────────┘
```

> Replace this ASCII with a draw.io / excalidraw / mermaid diagram before Week 4.

## Stack

| Layer | Tool |
|---|---|
| CAN encoding | `cantools` + `python-can` |
| Message bus | Mosquitto (MQTT) |
| Time-series DB | TimescaleDB (Week 2) |
| Dashboards | Grafana (Week 2) |
| Admin API | FastAPI (Week 4) |
| Auth | API key (production note: use JWT/OAuth) |
| Orchestration | Docker Compose |

## Quickstart

### Local dev

```bash
pip install -e ".[dev]"
pytest
```

### Run simulator + broker via Docker

```bash
docker compose up --build
# in another shell, watch frames arrive:
docker compose exec mosquitto mosquitto_sub -t 'fleet/+/can' -v
```

### Standalone simulator (broker already running)

```bash
python -m fleet_canbus.cli --device-id device-001 --rate-hz 10 --duration 30
```

## Roadmap

- [x] Week 1 (Apr 27 – May 3): CAN simulator + MQTT publisher + CI
- [ ] Week 2 (May 4 – May 10): TimescaleDB schema + Grafana + continuous aggregates
- [ ] Week 3 (May 11 – May 17): Scale to 50 simulators + alerts + retention + reconnect tests
- [ ] Week 4 (May 18 – May 24): FastAPI admin + deployment + docs

## Performance notes

> To be filled in Week 3 with throughput numbers and the hardware they were measured on. The 10k msg/s target is a **synthetic stress test**, not real fleet traffic — the README will document hardware (CPU, RAM) and the simulation methodology so the number is defensible in interviews.

## Project layout

```
.
├── dbc/battery_fleet.dbc        # CAN signal definitions
├── src/fleet_canbus/
│   ├── simulator.py             # Synthetic battery state + CAN frame encoder
│   ├── publisher.py             # MQTT publisher
│   └── cli.py                   # Entry point
├── tests/                       # pytest
├── config/mosquitto.conf        # Broker config
├── docker-compose.yml           # Mosquitto + simulator
├── Dockerfile.simulator
└── .github/workflows/ci.yml     # Lint + test on push/PR
```
