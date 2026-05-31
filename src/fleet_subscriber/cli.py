"""Run the MQTT → TimescaleDB subscriber as a long-lived service."""
from __future__ import annotations

import argparse
import logging
import os
import queue
import signal
import time

import psycopg2

from .db_writer import DbWriter
from .subscriber import Subscriber

log = logging.getLogger("fleet_subscriber.cli")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="MQTT → TimescaleDB subscriber")
    p.add_argument("--mqtt-host", default=os.getenv("MQTT_HOST", "localhost"))
    p.add_argument("--mqtt-port", type=int, default=int(os.getenv("MQTT_PORT", "1883")))
    p.add_argument("--pg-host", default=os.getenv("PG_HOST", "localhost"))
    p.add_argument("--pg-port", type=int, default=int(os.getenv("PG_PORT", "5432")))
    p.add_argument("--pg-db",   default=os.getenv("PG_DB", "fleet"))
    p.add_argument("--pg-user", default=os.getenv("PG_USER", "fleet"))
    p.add_argument("--pg-password", default=os.getenv("PG_PASSWORD", "fleet"))
    p.add_argument("--batch-size", type=int,   default=int(os.getenv("BATCH_SIZE", "500")))
    p.add_argument("--flush-interval", type=float,
                   default=float(os.getenv("FLUSH_INTERVAL_S", "1.0")))
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def _make_conn_factory(args):
    def factory():
        return psycopg2.connect(
            host=args.pg_host,
            port=args.pg_port,
            dbname=args.pg_db,
            user=args.pg_user,
            password=args.pg_password,
        )
    return factory


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    q: queue.Queue = queue.Queue(maxsize=10000)
    writer = DbWriter(
        q,
        conn_factory=_make_conn_factory(args),
        batch_size=args.batch_size,
        flush_interval_s=args.flush_interval,
    )
    sub = Subscriber(args.mqtt_host, args.mqtt_port, out_queue=q)

    stop = False

    def _handle_sigterm(_signum, _frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)

    writer.start()
    sub.start()
    log.info("subscriber running; broker=%s:%s db=%s:%s/%s",
             args.mqtt_host, args.mqtt_port, args.pg_host, args.pg_port, args.pg_db)

    try:
        while not stop:
            time.sleep(0.5)
    finally:
        sub.stop()
        writer.stop()
        log.info("subscriber stopped")


if __name__ == "__main__":
    main()
