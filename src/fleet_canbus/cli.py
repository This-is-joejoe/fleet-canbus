"""Run a single-device synthetic CAN simulator publishing to MQTT."""
from __future__ import annotations

import argparse
import logging
import os
import signal
import time

from .publisher import MqttPublisher
from .simulator import BatterySimulator

log = logging.getLogger("fleet_canbus.cli")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Synthetic battery CAN simulator → MQTT")
    parser.add_argument("--device-id", default=os.getenv("DEVICE_ID", "device-001"))
    parser.add_argument("--mqtt-host", default=os.getenv("MQTT_HOST", "localhost"))
    parser.add_argument(
        "--mqtt-port",
        type=int,
        default=int(os.getenv("MQTT_PORT", "1883")),
    )
    parser.add_argument(
        "--rate-hz",
        type=float,
        default=float(os.getenv("RATE_HZ", "10.0")),
        help="frames-per-second per device (default 10)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=float(os.getenv("DURATION", "0")),
        help="seconds to run; 0 = forever (default)",
    )
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--inject-fault", action="append", default=[],
                        help="fault to inject at startup (repeatable)")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    sim = BatterySimulator(device_id=args.device_id, seed=args.seed)
    for fault in args.inject_fault:
        sim.inject_fault(fault)

    pub = MqttPublisher(
        host=args.mqtt_host,
        port=args.mqtt_port,
        client_id=f"sim-{args.device_id}",
    )
    pub.connect()
    log.info("publisher connected to %s:%s as %s",
             args.mqtt_host, args.mqtt_port, args.device_id)

    interval = 1.0 / args.rate_hz
    start = time.monotonic()
    msg_count = 0
    stop = False

    def _handle_sigterm(_signum, _frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)

    try:
        while not stop:
            sim.step(dt=interval)
            frames = sim.encode_frames()
            pub.publish_frames(args.device_id, frames)
            msg_count += len(frames)
            if args.duration and time.monotonic() - start >= args.duration:
                break
            time.sleep(interval)
    finally:
        elapsed = time.monotonic() - start
        log.info("published %d frames in %.1fs (%.1f msg/s)",
                 msg_count, elapsed, msg_count / max(elapsed, 1e-6))
        pub.disconnect()


if __name__ == "__main__":
    main()
