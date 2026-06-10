"""Background thread that batch-inserts telemetry rows into TimescaleDB."""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from psycopg2.extras import execute_values

from . import metrics

log = logging.getLogger("fleet_subscriber.db_writer")

# execute_values expands a single `%s` into all row tuples, producing one
# multi-row INSERT (one round-trip) instead of psycopg2's executemany, which
# issues a separate statement per row.
INSERT_SQL = """
INSERT INTO battery_telemetry (
    time, device_id, soc, voltage, current,
    temp_max, temp_min, temp_avg,
    pack_health, fault_flags, cell_voltages
) VALUES %s
"""


@dataclass
class Telemetry:
    ts_ms: int
    device_id: str
    soc: float
    voltage: float
    current: float
    temp_max: float
    temp_min: float
    temp_avg: float
    pack_health: float
    fault_flags: int
    cell_voltages: list[float]

    def to_row(self) -> tuple:
        ts = datetime.fromtimestamp(self.ts_ms / 1000.0, tz=UTC)
        return (
            ts,
            self.device_id,
            self.soc,
            self.voltage,
            self.current,
            self.temp_max,
            self.temp_min,
            self.temp_avg,
            self.pack_health,
            self.fault_flags,
            json.dumps(self.cell_voltages),
        )


class DbWriter(threading.Thread):
    """Drain a queue, batch-flush every `batch_size` rows or `flush_interval_s`."""

    def __init__(
        self,
        in_queue: queue.Queue,
        conn_factory: Callable[[], object],
        batch_size: int = 500,
        flush_interval_s: float = 1.0,
    ) -> None:
        super().__init__(name="db-writer", daemon=True)
        self.q = in_queue
        self.conn_factory = conn_factory
        self.batch_size = batch_size
        self.flush_interval_s = flush_interval_s
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()
        self.join(timeout=5.0)

    def run(self) -> None:
        conn = self.conn_factory()
        buffer: list[Telemetry] = []
        last_flush = time.monotonic()

        while not self._stop_event.is_set():
            timeout = max(0.0, self.flush_interval_s - (time.monotonic() - last_flush))
            try:
                item: Telemetry = self.q.get(timeout=timeout)
                buffer.append(item)
            except queue.Empty:
                pass

            should_flush_by_count = len(buffer) >= self.batch_size
            should_flush_by_time = (
                buffer and (time.monotonic() - last_flush) >= self.flush_interval_s
            )
            if should_flush_by_count or should_flush_by_time:
                self._flush(conn, buffer)
                buffer.clear()
                last_flush = time.monotonic()

        if buffer:
            self._flush(conn, buffer)

    def _flush(self, conn, buffer: list[Telemetry]) -> None:
        rows = [t.to_row() for t in buffer]
        try:
            with conn.cursor() as cur:
                execute_values(cur, INSERT_SQL, rows, page_size=len(rows))
            commit = getattr(conn, "commit", None)
            if callable(commit):
                commit()
            metrics.rows_inserted_total.inc(len(rows))
            log.debug("flushed %d rows", len(rows))
        except Exception:
            log.exception("flush failed; dropping %d rows", len(rows))
