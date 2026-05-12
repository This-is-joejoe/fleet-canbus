"""Synthetic battery state evolution + CAN frame encoding."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path

import cantools
from cantools.database import Database

DEFAULT_DBC_PATH = Path(__file__).resolve().parent.parent.parent / "dbc" / "battery_fleet.dbc"

NUM_CELLS = 16
PACK_CAPACITY_AH = 100.0
NOMINAL_PACK_VOLTAGE = 400.0


@dataclass
class BatteryState:
    soc: float = 95.0
    voltage_pack: float = NOMINAL_PACK_VOLTAGE
    current: float = 0.0
    temp_max: float = 25.0
    temp_min: float = 25.0
    temp_avg: float = 25.0
    pack_health: float = 99.0
    cycle_count: int = 120
    fault_flags: int = 0
    cell_voltages: list[float] = field(
        default_factory=lambda: [3.7] * NUM_CELLS
    )


class BatterySimulator:
    """Time-stepped battery state simulator with controllable fault injection.

    Designed to be deterministic when seeded — important for tests and
    reproducible throughput experiments.
    """

    KNOWN_FAULTS = {"overheat", "cell_imbalance", "over_voltage", "under_voltage"}

    def __init__(
        self,
        device_id: str,
        dbc_path: Path | str = DEFAULT_DBC_PATH,
        seed: int | None = None,
    ) -> None:
        self.device_id = device_id
        self.db: Database = cantools.database.load_file(str(dbc_path))
        self.state = BatteryState()
        self.rng = random.Random(seed)
        self._faults: set[str] = set()

    # ----- fault control -----

    def inject_fault(self, fault: str) -> None:
        if fault not in self.KNOWN_FAULTS:
            raise ValueError(f"Unknown fault {fault!r}; known: {sorted(self.KNOWN_FAULTS)}")
        self._faults.add(fault)
        self._update_fault_flags()

    def clear_fault(self, fault: str) -> None:
        self._faults.discard(fault)
        self._update_fault_flags()

    def _update_fault_flags(self) -> None:
        flag_bits = {
            "overheat": 1 << 0,
            "over_voltage": 1 << 1,
            "under_voltage": 1 << 2,
            "cell_imbalance": 1 << 3,
        }
        self.state.fault_flags = sum(flag_bits[f] for f in self._faults)

    # ----- state evolution -----

    def step(self, dt: float = 1.0) -> None:
        """Advance the simulation by `dt` seconds."""
        s = self.state

        # current: random walk, clamped
        s.current = _clamp(s.current + self.rng.gauss(0, 5.0), -200.0, 200.0)

        # SOC drift from current draw (positive current = discharge)
        soc_delta = (s.current * dt) / (3600.0 * PACK_CAPACITY_AH)
        s.soc = _clamp(s.soc - soc_delta * 100.0, 0.0, 100.0)

        # pack voltage tracks SOC with small noise
        s.voltage_pack = _clamp(
            350.0 + (s.soc / 100.0) * 70.0 + self.rng.gauss(0, 0.5),
            300.0, 450.0,
        )

        # baseline thermal evolution on temp_avg
        s.temp_avg = _clamp(s.temp_avg + self.rng.gauss(0, 0.1), -20.0, 90.0)

        # overheat fault drives an accumulating thermal-runaway-style rise.
        # Apply BEFORE deriving max/min so it propagates this step.
        if "overheat" in self._faults:
            s.temp_avg = _clamp(s.temp_avg + 0.5, -20.0, 90.0)

        s.temp_max = _clamp(s.temp_avg + 1.5 + abs(self.rng.gauss(0, 0.5)), -20.0, 150.0)
        s.temp_min = _clamp(s.temp_avg - 1.5 - abs(self.rng.gauss(0, 0.5)), -30.0, 90.0)

        # cell voltages: small per-cell noise around an SOC-derived baseline
        cell_base = 3.0 + (s.soc / 100.0) * 1.2
        s.cell_voltages = [
            _clamp(cell_base + self.rng.gauss(0, 0.005), 2.0, 4.5)
            for _ in range(NUM_CELLS)
        ]

        # static cell-level faults: persistent offsets on specific cells
        if "cell_imbalance" in self._faults:
            s.cell_voltages[0] = _clamp(s.cell_voltages[0] - 0.1, 2.0, 4.5)
        if "over_voltage" in self._faults:
            s.cell_voltages[1] = _clamp(s.cell_voltages[1] + 0.3, 2.0, 4.5)
        if "under_voltage" in self._faults:
            s.cell_voltages[2] = _clamp(s.cell_voltages[2] - 0.5, 2.0, 4.5)

    # ----- CAN encoding -----

    def encode_frames(self) -> list[dict]:
        """Encode current state as a list of CAN frames matching the DBC."""
        s = self.state
        frames: list[dict] = []

        frames.append(self._encode("BMS_Pack_Status", {
            "SOC": s.soc,
            "Voltage_Pack": s.voltage_pack,
            "Current": s.current,
            "Temp_Max": s.temp_max,
            "Temp_Min": s.temp_min,
        }))

        for i in range(4):
            cells = s.cell_voltages[i * 4:(i + 1) * 4]
            payload = {f"Cell_V_{i * 4 + j + 1}": cells[j] for j in range(4)}
            frames.append(self._encode(f"BMS_Cell_Voltages_{i + 1}", payload))

        frames.append(self._encode("BMS_Pack_Health", {
            "Pack_Health": s.pack_health,
            "Cycle_Count": s.cycle_count,
            "Fault_Flags": s.fault_flags,
            "Temp_Avg": s.temp_avg,
        }))

        return frames

    def _encode(self, message_name: str, signals: dict) -> dict:
        msg = self.db.get_message_by_name(message_name)
        data = msg.encode(signals)
        return {
            "arbitration_id": msg.frame_id,
            "name": message_name,
            "data": data.hex(),
        }

    def signals_snapshot(self) -> dict:
        """Return current battery state as a flat dict of decoded signal values.

        Cloud-side MQTT payload uses engineering units, not raw CAN bytes —
        this method is the device-side equivalent of cantools decode.
        """
        s = self.state
        return {
            "SOC": s.soc,
            "Voltage_Pack": s.voltage_pack,
            "Current": s.current,
            "Temp_Max": s.temp_max,
            "Temp_Min": s.temp_min,
            "Temp_Avg": s.temp_avg,
            "Pack_Health": s.pack_health,
            "Fault_Flags": s.fault_flags,
            "cell_voltages": list(s.cell_voltages),
        }


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
