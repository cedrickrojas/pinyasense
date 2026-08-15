#!/usr/bin/env python3
"""DHT22 live test on GPIO 27 (Physical Pin 13)."""

import time

import adafruit_dht
from adafruit_blinka.microcontroller.bcm283x import pin as blinka_pin


def main() -> None:
    print("🌡️  DHT22 Temperature/Humidity Live Test")
    print("   GPIO Pin: 27 (Physical Pin 13)")
    print("-" * 60)

    sensor = adafruit_dht.DHT22(blinka_pin.D27, use_pulseio=False)
    success = 0
    try:
        for index in range(5):
            try:
                temperature = sensor.temperature
                humidity = sensor.humidity
                if temperature is None or humidity is None:
                    raise RuntimeError("No data returned")

                temp_fahrenheit = (temperature * 9 / 5) + 32
                success += 1
                print(f"[{index + 1}] ✅ {time.strftime('%Y-%m-%dT%H:%M:%S')}")
                print(f"    Temperature: {temperature:.1f}°C ({temp_fahrenheit:.1f}°F)")
                print(f"    Humidity: {humidity:.1f}%")
            except Exception as error:
                print(f"[{index + 1}] ⚠️  Read failed: {error}")
            print()
            time.sleep(2)
    finally:
        sensor.exit()

    print("-" * 60)
    if success > 0:
        print(f"✅ Live sensor reads OK: {success}/5")
    else:
        print("❌ No successful live reads. Recheck wiring and pull-up resistor.")


if __name__ == "__main__":
    main()
