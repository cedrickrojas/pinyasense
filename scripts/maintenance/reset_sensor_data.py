#!/usr/bin/env python3
"""Upsert deterministic daily sample values into Firestore sensor_data.

This script updates only its generated soil_history documents, preserving other
documents in the sensor_data collection.

Examples:
    python -m scripts.maintenance.reset_sensor_data --dry-run
    python -m scripts.maintenance.reset_sensor_data --from-date 2026-09-17
    python -m scripts.maintenance.reset_sensor_data --from-date 2026-09-17 --to-date 2026-09-26
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, List, Tuple

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
except ImportError:  # pragma: no cover
    firebase_admin = None
    credentials = None
    firestore = None

ROOT_DIR = Path(__file__).resolve().parents[2]
if load_dotenv is not None:
    load_dotenv(ROOT_DIR / ".env")


def parse_args() -> argparse.Namespace:
    today = date.today().isoformat()
    parser = argparse.ArgumentParser(description="Update generated daily moisture readings in Firestore.")
    parser.add_argument("--from-date", default="2026-09-17", help="Start date in YYYY-MM-DD format.")
    parser.add_argument("--to-date", default=today, help="End date in YYYY-MM-DD format.")
    parser.add_argument("--dry-run", action="store_true", help="Preview the generated records without writing to Firestore.")
    return parser.parse_args()


def normalize_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def iter_day_range(start_date: date, end_date: date) -> Iterable[date]:
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def calculate_moisture_value(day: date, zone: int) -> int:
    """Create a realistic irrigation-driven soil-moisture pattern per zone.

    Each zone has a distinct baseline, dry days are intentionally more frequent
    than wet days, and a weekly irrigation pattern creates realistic recovery
    after dry periods.
    """
    zone_offsets = {1: 8, 2: 12, 3: 15, 4: 18}
    zone_base = 32 + zone_offsets[zone]
    irrigation_cycle = (day.day % 7)

    if irrigation_cycle in (0, 1):
        irrigation_boost = 18
    elif irrigation_cycle in (2, 3):
        irrigation_boost = 10
    elif irrigation_cycle == 4:
        irrigation_boost = 4
    else:
        irrigation_boost = -10

    dry_bias = (day.day + zone * 3) % 5
    if dry_bias in (0, 1, 2):
        moisture = zone_base + irrigation_boost - 18
    elif dry_bias == 3:
        moisture = zone_base + irrigation_boost - 6
    else:
        moisture = zone_base + irrigation_boost + 12

    seasonal_wave = int(16 * __import__('math').sin((day.timetuple().tm_yday + zone * 5) / 4.0))
    moisture += seasonal_wave

    if zone == 1:
        moisture -= 6
    elif zone == 2:
        moisture += 2
    elif zone == 3:
        moisture += 5
    elif zone == 4:
        moisture += 8

    if moisture > 80:
        moisture = 80
    if moisture < 18:
        moisture = 18
    return moisture


def soil_status(value: int) -> str:
    if value <= 30:
        return "dry"
    if value <= 70:
        return "moist"
    return "wet"


def get_service_account_path() -> str | None:
    env_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_KEY")
    if env_path:
        return env_path

    candidates = [
        ROOT_DIR / "serviceAccountKey.json",
        ROOT_DIR / "pinyasense" / "serviceAccountKey.json",
        ROOT_DIR / ".." / "serviceAccountKey.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def connect_firestore():
    if firebase_admin is None or credentials is None or firestore is None:
        raise RuntimeError("firebase_admin is not installed. Please install project requirements first.")

    key_path = get_service_account_path()
    if not key_path:
        raise FileNotFoundError(
            "No Firebase service account JSON was found. Place serviceAccountKey.json in the project root or set FIREBASE_SERVICE_ACCOUNT_KEY."
        )

    cred = credentials.Certificate(key_path)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    return firestore.client()


def sample_sensor_record(day: date, zone: int) -> Tuple[str, dict]:
    value = calculate_moisture_value(day, zone)
    raw_value = 620 + (value * 3)
    status = soil_status(value)
    state = "DRY" if status == "dry" else "MOIST" if status == "moist" else "WET"
    timestamp = datetime.combine(day, datetime.min.time().replace(hour=12, minute=0, second=0)).isoformat()
    document_id = f"soil_history_{day.strftime('%Y%m%d')}_zone{zone}"
    payload = {
        "sensor_type": f"soil_moisture_zone{zone}",
        "user_id": None,
        "timestamp": timestamp,
        "data": {
            "value": value,
            "unit": "%",
            "status": status,
            "state": state,
            "raw_value": raw_value,
            "sensor_mode": "arduino_analog",
            "zone": zone,
            "timestamp": timestamp,
        },
    }
    return document_id, payload


def write_sample_data(db, start_date: date, end_date: date) -> List[dict]:
    records: List[dict] = []
    for day in iter_day_range(start_date, end_date):
        for zone in (1, 2, 3, 4):
            document_id, payload = sample_sensor_record(day, zone)
            db.collection("sensor_data").document(document_id).set(payload)
            records.append({"document_id": document_id, "payload": payload})
    return records


def print_preview(start_date: date, end_date: date) -> None:
    print(f"Previewing daily sensor samples from {start_date.isoformat()} to {end_date.isoformat()}.")
    total = 0
    for day in iter_day_range(start_date, end_date):
        for zone in (1, 2, 3, 4):
            document_id, payload = sample_sensor_record(day, zone)
            total += 1
            print(f"{document_id}: {payload['sensor_type']} = {payload['data']['value']}% @ {payload['timestamp']}")
    print(f"Total generated sample records: {total}")


def main() -> int:
    args = parse_args()
    try:
        start_date = normalize_date(args.from_date)
        end_date = normalize_date(args.to_date)
    except ValueError as exc:
        print(f"Invalid date format: {exc}", file=sys.stderr)
        return 2

    if start_date > end_date:
        print("Start date cannot be later than end date.", file=sys.stderr)
        return 2

    if args.dry_run:
        print_preview(start_date, end_date)
        return 0

    try:
        db = connect_firestore()
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"Firebase setup error: {exc}", file=sys.stderr)
        return 1

    try:
        inserted = write_sample_data(db, start_date, end_date)
        print(f"Updated {len(inserted)} generated daily records across {start_date.isoformat()} to {end_date.isoformat()}.")
        return 0
    except Exception as exc:  # pragma: no cover
        print(f"Failed to write sample data: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
