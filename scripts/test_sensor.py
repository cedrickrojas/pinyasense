#!/usr/bin/env python3
"""Quick sensor test utility for AgriPinya soil moisture (Digital DO).

Usage:
  python test_sensor.py
  python test_sensor.py --samples 10 --interval 1
  sudo /home/voicebrain/agripinya/venv/bin/python test_sensor.py --samples 10
"""

import argparse
import time
from datetime import datetime

from core.sensor_monitor import sensor_monitor


def print_reading(reading: dict, index: int | None = None) -> bool:
    prefix = f"[{index}] " if index is not None else ""

    if "error" in reading:
        print(f"{prefix}❌ ERROR: {reading['error']}")
        return False

    timestamp = reading.get("timestamp", datetime.now().isoformat())
    state = reading.get("state", "UNKNOWN")
    raw_value = reading.get("raw_value", "?")
    gpio_pin = reading.get("gpio_pin", "?")
    status = reading.get("status", "unknown").upper()
    recommendation = reading.get("recommendation", "")

    print(
        f"{prefix}✅ {timestamp} | GPIO {gpio_pin} | DO={raw_value} | "
        f"STATE={state} | STATUS={status}"
    )
    if recommendation:
        print(f"{prefix}   💡 {recommendation}")

    return True


def run_test(samples: int, interval: float) -> int:
    print("🌱 AgriPinya Soil Moisture Sensor Test (Digital DO)")
    print(f"   Samples: {samples}")
    print(f"   Interval: {interval}s")
    print("-" * 60)

    dry_count = 0
    wet_count = 0
    success_count = 0

    for i in range(1, samples + 1):
        reading = sensor_monitor.read_soil_moisture()
        ok = print_reading(reading, i)

        if ok:
            success_count += 1
            state = reading.get("state")
            if state == "DRY":
                dry_count += 1
            elif state == "WET":
                wet_count += 1

        if i < samples:
            time.sleep(interval)

    print("-" * 60)
    print(f"Successful reads: {success_count}/{samples}")
    print(f"DRY count: {dry_count}")
    print(f"WET count: {wet_count}")

    if success_count == 0:
        print("\n❌ No valid readings received.")
        print("   Try running with sudo on Raspberry Pi:")
        print("   sudo /home/voicebrain/agripinya/venv/bin/python test_sensor.py --samples 10")
        return 1

    print("\n✅ Sensor test completed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Test soil moisture sensor readings")
    parser.add_argument("--samples", type=int, default=5, help="Number of readings to capture")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between readings")

    args = parser.parse_args()

    samples = max(1, args.samples)
    interval = max(0.1, args.interval)

    return run_test(samples=samples, interval=interval)


if __name__ == "__main__":
    raise SystemExit(main())
