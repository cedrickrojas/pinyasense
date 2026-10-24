"""Read-only soil display fallback; never persisted or used for pump control.

The uncalibrated percentage proxy models drying, drainage and assumed water
inputs. Source flags stay on every sample so it cannot become hardware history.
"""

import math
import random
from datetime import date, datetime, timedelta
from functools import lru_cache


MODEL_START = date(2020, 1, 1)
SAMPLE_INTERVAL_SECONDS = 5

# Illustrative area differences, not calibration for the actual sensor locations.
# Each zone has its own watering condition; one dry area does not water all four.
# Moderate the drier/wetter areas around the status boundaries, with earlier
# assumed watering for the drier area and faster drainage for the wetter area.
ZONE_PROFILES = (
    dict(initial=34.0, drying=0.8, absorption=0.65, capacity=43.0, drainage=0.12,
         irrigation_trigger=30.5, irrigation_target=35.5, interval_days=1, day_phase=0, hour=6),
    dict(initial=52.0, drying=1.0, absorption=0.9, capacity=62.0, drainage=0.045,
         irrigation_trigger=38.0, irrigation_target=61.0, interval_days=2, day_phase=0, hour=6),
    dict(initial=61.0, drying=0.8, absorption=1.0, capacity=70.0, drainage=0.025,
         irrigation_trigger=45.0, irrigation_target=66.0, interval_days=3, day_phase=1, hour=7),
    dict(initial=72.0, drying=0.8, absorption=0.75, capacity=72.0, drainage=0.12,
         irrigation_trigger=70.0, irrigation_target=75.0, interval_days=1, day_phase=0, hour=8),
)


@lru_cache(maxsize=2)
def _recent_profiles(last_day):
    """Independent area water balances under shared illustrative weather."""
    levels = [profile['initial'] for profile in ZONE_PROFILES]
    profiles = {}
    for offset in range((last_day - MODEL_START).days + 1):
        day = MODEL_START + timedelta(days=offset)
        rng = random.Random(f"pinyasense-soil-display-v1:{day.isoformat()}")
        rain = rng.uniform(8.0, 30.0) if rng.random() < 0.2 else 0.0
        rain_hour = rng.randint(8, 18)
        duration = rng.randint(2, 4)
        evaporation = rng.uniform(3.5, 5.5) * (0.7 if rain else 1.0)
        hourly = [tuple(levels)]
        for hour in range(24):
            rainfall = rain / duration if rain_hour <= hour < rain_hour + duration else 0.0
            daylight = 0.25 + 0.75 * max(0.0, math.sin(math.pi * (hour - 6) / 12))
            for zone, profile in enumerate(ZONE_PROFILES):
                scheduled = (hour == profile['hour']
                             and day.toordinal() % profile['interval_days'] == profile['day_phase'])
                irrigation = (max(0.0, profile['irrigation_target'] - levels[zone])
                              if scheduled and levels[zone] < profile['irrigation_trigger'] else 0.0)
                levels[zone] += rainfall * 0.85 * profile['absorption'] + irrigation
                levels[zone] -= max(0.0, levels[zone] - profile['capacity']) * profile['drainage']
                levels[zone] -= evaporation * daylight / 11.7 * profile['drying']
                levels[zone] = max(8.0, min(95.0, levels[zone]))
            hourly.append(tuple(levels))
        if (last_day - day).days <= 8:
            profiles[day] = hourly
    return profiles


def _status(value):
    return "dry" if value <= 30 else "moist" if value <= 70 else "wet"


def preview_zones(now=None):
    now = _sample_time(now)
    profiles = _recent_profiles(now.date())
    return _zones_at(now, profiles)


def _sample_time(now=None):
    now = now or datetime.now()
    return now.replace(second=(now.second // SAMPLE_INTERVAL_SECONDS) * SAMPLE_INTERVAL_SECONDS,
                       microsecond=0)


def _zones_at(timestamp, profiles):
    hourly = profiles[timestamp.date()]
    fraction = (timestamp.minute * 60 + timestamp.second) / 3600.0
    elapsed = (timestamp - datetime.combine(MODEL_START, datetime.min.time())).total_seconds()
    zones = []
    for index in range(4):
        low, high = hourly[timestamp.hour][index], hourly[timestamp.hour + 1][index]
        # Small, smooth display fluctuations around the slower water balance.
        # Absolute time makes repeated reads and history agree, without changing
        # real hardware values or generating a new random result per request.
        fluctuation = (
            0.24 * math.sin(2 * math.pi * elapsed / 67 + index * 1.73)
            + 0.12 * math.sin(2 * math.pi * elapsed / 29 + index * 2.41)
            + 0.06 * math.sin(2 * math.pi * elapsed / 173 + index * 0.97)
        )
        value = round(max(8.0, min(95.0, low + (high - low) * fraction + fluctuation)), 1)
        status = _status(value)
        zones.append({
            "zone": index + 1, "value": value, "unit": "%",
            "status": status, "state": status.upper(), "alert": status != "moist",
            "sensor_mode": "estimated_percent", "sensor_live": False,
            "data_source": "simulated", "timestamp": timestamp.isoformat(),
        })
    return zones


def preview_history(hours=24, now=None):
    """Return matching quarter-hour history plus the current five-second sample."""
    now = _sample_time(now)
    hours = max(1, min(168, int(hours)))
    start = now - timedelta(hours=hours)
    timestamp = start.replace(minute=(start.minute // 15) * 15, second=0, microsecond=0)
    if timestamp < start:
        timestamp += timedelta(minutes=15)
    profiles = _recent_profiles(now.date())
    readings = []
    while timestamp <= now:
        zones = _zones_at(timestamp, profiles)
        value = round(sum(zone["value"] for zone in zones) / len(zones), 1)
        status = _status(value)
        readings.append({
            "timestamp": timestamp.isoformat(), "value": value, "unit": "%",
            "status": status, "state": status.upper(), "alert": status != "moist",
            "zone_count": 4, "sensor_mode": "estimated_percent",
            "data_source": "simulated", "sensor_live": False,
        })
        if timestamp == now:
            break
        timestamp = min(timestamp + timedelta(minutes=15), now)
    return readings
