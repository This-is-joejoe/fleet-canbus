"""DBC sanity tests — guards against accidental signal-definition breakage."""
import cantools

from fleet_canbus.simulator import DEFAULT_DBC_PATH

DBC_PATH = DEFAULT_DBC_PATH


def test_dbc_loads_without_error():
    db = cantools.database.load_file(str(DBC_PATH))
    assert db is not None
    assert len(db.messages) == 6


def test_pack_status_has_expected_signals():
    db = cantools.database.load_file(str(DBC_PATH))
    msg = db.get_message_by_name("BMS_Pack_Status")
    names = {s.name for s in msg.signals}
    assert {"SOC", "Voltage_Pack", "Current", "Temp_Max", "Temp_Min"} <= names


def test_all_16_cells_defined_across_4_frames():
    db = cantools.database.load_file(str(DBC_PATH))
    cells_seen = set()
    for i in range(1, 5):
        msg = db.get_message_by_name(f"BMS_Cell_Voltages_{i}")
        assert len(msg.signals) == 4
        for sig in msg.signals:
            assert sig.name.startswith("Cell_V_")
            cells_seen.add(sig.name)
    assert cells_seen == {f"Cell_V_{i}" for i in range(1, 17)}


def test_pack_health_signals():
    db = cantools.database.load_file(str(DBC_PATH))
    msg = db.get_message_by_name("BMS_Pack_Health")
    names = {s.name for s in msg.signals}
    assert {"Pack_Health", "Cycle_Count", "Fault_Flags", "Temp_Avg"} <= names
