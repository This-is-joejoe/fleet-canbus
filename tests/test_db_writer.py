"""Unit tests for the batch DB writer (no real database)."""
import queue
import time
from unittest.mock import MagicMock

from prometheus_client import REGISTRY

from fleet_subscriber.db_writer import Telemetry


def _sample_row(device="d1", soc=80.0):
    return Telemetry(
        ts_ms=1715000000000,
        device_id=device,
        soc=soc,
        voltage=400.0,
        current=-10.0,
        temp_max=30.0,
        temp_min=28.0,
        temp_avg=29.0,
        pack_health=99.0,
        fault_flags=0,
        cell_voltages=[3.7] * 16,
    )


def test_flush_triggered_by_count(monkeypatch):
    import fleet_subscriber.db_writer as dbw
    calls = []
    monkeypatch.setattr(dbw, "execute_values",
                        lambda cur, sql, rows, *a, **k: calls.append((sql, list(rows))))

    q = queue.Queue()
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor

    writer = dbw.DbWriter(q, conn_factory=lambda: conn, batch_size=3, flush_interval_s=10.0)

    for _ in range(3):
        q.put(_sample_row())

    writer.start()
    time.sleep(0.3)  # let writer drain queue
    writer.stop()

    assert len(calls) == 1
    sql, rows = calls[0]
    assert "INSERT INTO battery_telemetry" in sql
    assert len(rows) == 3


def test_flush_triggered_by_time(monkeypatch):
    import fleet_subscriber.db_writer as dbw
    calls = []
    monkeypatch.setattr(dbw, "execute_values",
                        lambda cur, sql, rows, *a, **k: calls.append((sql, list(rows))))

    q = queue.Queue()
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor

    writer = dbw.DbWriter(q, conn_factory=lambda: conn, batch_size=500, flush_interval_s=0.1)

    q.put(_sample_row())
    writer.start()
    time.sleep(0.4)  # > flush_interval_s
    writer.stop()

    assert len(calls) >= 1
    _sql, rows = calls[-1]
    assert len(rows) == 1


def test_metrics_count_written_rows_on_flush(monkeypatch):
    import fleet_subscriber.db_writer as dbw
    monkeypatch.setattr(dbw, "execute_values", lambda *a, **k: None)

    q = queue.Queue()
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = MagicMock()

    writer = dbw.DbWriter(
        q, conn_factory=lambda: conn, batch_size=3, flush_interval_s=10.0
    )
    before = REGISTRY.get_sample_value("telemetry_rows_inserted_total") or 0.0
    for _ in range(3):
        q.put(_sample_row())

    writer.start()
    time.sleep(0.3)
    writer.stop()

    after = REGISTRY.get_sample_value("telemetry_rows_inserted_total")
    assert after == before + 3


def test_flush_uses_execute_values_single_statement(monkeypatch):
    """One flush issues a single multi-row INSERT via execute_values, not N
    executemany round-trips."""
    import fleet_subscriber.db_writer as dbw

    calls = []

    def fake_execute_values(cur, sql, rows, *a, **k):
        calls.append((sql, list(rows)))

    monkeypatch.setattr(dbw, "execute_values", fake_execute_values)

    q = queue.Queue()
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor

    writer = dbw.DbWriter(q, conn_factory=lambda: conn, batch_size=3, flush_interval_s=10.0)
    for _ in range(3):
        q.put(_sample_row())

    writer.start()
    time.sleep(0.3)
    writer.stop()

    cursor.executemany.assert_not_called()
    assert len(calls) == 1
    sql, rows = calls[0]
    assert "INSERT INTO battery_telemetry" in sql
    assert "VALUES %s" in sql
    assert len(rows) == 3


def test_empty_buffer_does_not_flush(monkeypatch):
    import fleet_subscriber.db_writer as dbw
    ev = MagicMock()
    monkeypatch.setattr(dbw, "execute_values", ev)

    q = queue.Queue()
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor

    writer = dbw.DbWriter(q, conn_factory=lambda: conn, batch_size=500, flush_interval_s=0.1)
    writer.start()
    time.sleep(0.3)
    writer.stop()

    ev.assert_not_called()
