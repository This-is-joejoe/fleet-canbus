"""Simulator behavior tests."""
import pytest

from fleet_canbus.simulator import NUM_CELLS, BatterySimulator


def test_initial_state_is_in_valid_range():
    sim = BatterySimulator("dev-1", seed=42)
    assert 0 <= sim.state.soc <= 100
    assert len(sim.state.cell_voltages) == NUM_CELLS
    for v in sim.state.cell_voltages:
        assert 2.0 <= v <= 4.5


def test_deterministic_when_seeded():
    a = BatterySimulator("dev-1", seed=42)
    b = BatterySimulator("dev-1", seed=42)
    for _ in range(20):
        a.step()
        b.step()
    assert a.state.soc == b.state.soc
    assert a.state.current == b.state.current
    assert a.state.cell_voltages == b.state.cell_voltages


def test_overheat_fault_increases_temp_max_over_time():
    sim = BatterySimulator("dev-1", seed=0)
    baseline = sim.state.temp_max
    sim.inject_fault("overheat")
    for _ in range(20):
        sim.step()
    assert sim.state.temp_max > baseline + 5.0


def test_unknown_fault_raises():
    sim = BatterySimulator("dev-1", seed=0)
    with pytest.raises(ValueError):
        sim.inject_fault("nope-not-a-fault")


def test_fault_flags_bitmask_reflects_active_faults():
    sim = BatterySimulator("dev-1", seed=0)
    assert sim.state.fault_flags == 0
    sim.inject_fault("overheat")
    sim.inject_fault("cell_imbalance")
    assert sim.state.fault_flags == (1 << 0) | (1 << 3)
    sim.clear_fault("overheat")
    assert sim.state.fault_flags == (1 << 3)


def test_encode_frames_returns_six_valid_frames():
    sim = BatterySimulator("dev-1", seed=0)
    sim.step()
    frames = sim.encode_frames()
    assert len(frames) == 6
    arb_ids = {f["arbitration_id"] for f in frames}
    assert arb_ids == {0x100, 0x101, 0x102, 0x103, 0x104, 0x105}
    for f in frames:
        assert isinstance(f["data"], str)
        assert len(f["data"]) == 16  # 8 bytes hex-encoded


def test_encoded_frames_decode_back_to_close_values():
    """Round-trip via cantools to ensure encoding is well-formed."""
    sim = BatterySimulator("dev-1", seed=7)
    sim.step()
    frames = sim.encode_frames()
    pack = next(f for f in frames if f["arbitration_id"] == 0x100)
    decoded = sim.db.decode_message(0x100, bytes.fromhex(pack["data"]))
    # SOC has factor 1 → expect ≤1% rounding
    assert abs(decoded["SOC"] - sim.state.soc) <= 1.0


def test_signals_snapshot_returns_decoded_engineering_values():
    sim = BatterySimulator(device_id="dev-1", seed=42)
    sim.step(dt=1.0)

    snap = sim.signals_snapshot()

    assert set(snap.keys()) == {
        "SOC", "Voltage_Pack", "Current",
        "Temp_Max", "Temp_Min", "Temp_Avg",
        "Pack_Health", "Fault_Flags", "cell_voltages",
    }
    assert isinstance(snap["SOC"], float)
    assert isinstance(snap["Fault_Flags"], int)
    assert isinstance(snap["cell_voltages"], list)
    assert len(snap["cell_voltages"]) == 16
    assert all(isinstance(v, float) for v in snap["cell_voltages"])
