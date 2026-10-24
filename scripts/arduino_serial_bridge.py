#!/usr/bin/env python3
"""Forward JSON readings from the Arduino USB serial port to the Flask app."""

import argparse
import json
import os
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/ttyACM0")
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument("--url", default="http://127.0.0.1:5001/save_sensor")
    parser.add_argument('--token', default=os.getenv('SENSOR_INGEST_TOKEN', ''),
                        help='Shared sensor ingest token for a remote Flask server')
    parser.add_argument(
        "--interval",
        type=float,
        default=60,
        help="Minimum seconds between Flask/Firestore writes (default: 60)",
    )
    args = parser.parse_args()

    if args.interval <= 0:
        parser.error("--interval must be greater than zero")

    try:
        import serial
    except ImportError as error:
        raise SystemExit("pyserial is required; install it with: python -m pip install pyserial") from error

    print(
        f"Listening on {args.port} at {args.baud} baud; "
        f"forwarding at most once every {args.interval:g}s"
    )
    with serial.Serial(args.port, args.baud, timeout=2) as arduino:
        time.sleep(2)
        last_forward_at = None
        while True:
            line = arduino.readline().decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                if not isinstance(payload.get("zones"), list):
                    continue
            except (json.JSONDecodeError, AttributeError):
                continue

            now = time.monotonic()
            if last_forward_at is not None and now - last_forward_at < args.interval:
                continue
            last_forward_at = now

            body = json.dumps(payload).encode("utf-8")
            request = Request(
                args.url,
                data=body,
                headers={"Content-Type": "application/json", "X-Sensor-Token": args.token},
                method="POST",
            )
            try:
                with urlopen(request, timeout=5) as response:
                    print(f"Forwarded {len(payload['zones'])} zones: HTTP {response.status}")
            except HTTPError as error:
                detail = error.read().decode("utf-8", errors="replace").strip()
                print(f"Forward failed: HTTP {error.code} {detail}")
            except Exception as error:
                print(f"Forward failed: {error}")


if __name__ == "__main__":
    raise SystemExit(main())
