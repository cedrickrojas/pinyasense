#!/usr/bin/env python3
"""Improve generated daily soil samples using a synthetic hourly water balance.

Rain and irrigation are demo assumptions, not measured weather or water content.
No labels/source fields are added. Existing ownership and metadata are retained.
"""
from __future__ import annotations
import argparse
import json
import math
import random
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANILA = timezone(timedelta(hours=8))
MODEL_START = date(2020, 1, 1)
PREFIXES = ('soil_history', 'daily_soil_moisture')


def soil_status(value):
    return 'dry' if value <= 30 else 'moist' if value <= 70 else 'wet'


def generate_samples(start, end, seed=42, adc_dry=1023, adc_wet=0):
    """Stable across date ranges; ADC defaults are illustrative calibration.

    Shared daily acquisition times preserve cross-zone averaging in the app.
    Naive timestamps follow the app's existing Manila ISO convention.
    """
    if not MODEL_START <= start <= end:
        raise ValueError(f'Dates must be ordered and on/after {MODEL_START}.')
    if not 0 <= adc_wet < adc_dry <= 1023:
        raise ValueError('Calibration must satisfy 0 <= adc-wet < adc-dry <= 1023.')
    levels = [54.0, 58.0, 62.0, 66.0]
    losses = [1.08, 1.02, 0.98, 0.92]
    absorption = [0.96, 1.00, 1.03, 1.06]
    for offset in range((end - MODEL_START).days + 1):
        day = MODEL_START + timedelta(days=offset)
        rng = random.Random(f'pinyasense-water-balance-v2:{seed}:{day.isoformat()}')
        rain_mm = rng.uniform(6, 38) if rng.random() < 0.21 else 0.0
        rain_hour, duration = rng.randint(4, 16), rng.randint(2, 4)
        evaporation = rng.uniform(3.5, 6.0) * (0.7 if rain_mm else 1.0)
        timestamp = datetime.combine(day, time(12)) + timedelta(seconds=rng.randint(-900, 900))
        for hour in range(24):
            irrigation = rng.uniform(23, 30) if hour == 6 and min(levels) < 25 else 0.0
            rain = rain_mm / duration if rain_hour <= hour < rain_hour + duration else 0.0
            daytime_loss = 0.25 + 0.75 * max(0, math.sin(math.pi * (hour - 6) / 12))
            for index in range(4):
                levels[index] += (rain * 0.85 + irrigation) * absorption[index]
                levels[index] -= max(0.0, levels[index] - 58) * 0.035
                levels[index] -= evaporation * daytime_loss / 11.7 * losses[index]
                levels[index] = max(8.0, min(95.0, levels[index]))
            if hour != timestamp.hour or day < start:
                continue
            for index in range(4):
                measured = max(0.0, min(100.0, levels[index] + rng.gauss(0, 0.35)))
                raw = max(adc_wet, min(adc_dry, round(adc_dry - measured / 100 * (adc_dry - adc_wet))))
                value = round((adc_dry - raw) * 100 / (adc_dry - adc_wet), 1)
                status = soil_status(value)
                yield day, index + 1, {
                    'value': value, 'unit': '%', 'status': status,
                    'state': status.upper(), 'raw_value': raw,
                    'sensor_mode': 'arduino_analog', 'zone': index + 1,
                    'timestamp': timestamp.isoformat(),
                }


def prepare_updates(db, samples, create_missing=False):
    """Only recognized generated IDs; refuse hardware mode collisions."""
    from google.cloud.firestore_v1._helpers import encode_dict
    from google.protobuf.json_format import MessageToDict
    from google.cloud.firestore_v1.types import Document
    updates, backups = [], []
    for day, zone, data in samples:
        matched = False
        for prefix in PREFIXES:
            document_id = f'{prefix}_{day:%Y%m%d}_zone{zone}'
            reference = db.collection('sensor_data').document(document_id)
            snapshot = reference.get(timeout=20, retry=None)
            if not snapshot.exists:
                continue
            previous = snapshot.to_dict()
            old_data = previous.get('data', {})
            mode = str(old_data.get('sensor_mode', '')).strip().lower()
            raw = old_data.get('raw_value')
            # Some legacy generated percent samples were mislabeled digital_do.
            # A genuine digital reading is binary, so only accept analog raw ADC.
            legacy_analog = (prefix == 'daily_soil_moisture' and mode == 'digital_do'
                             and old_data.get('unit') == '%'
                             and isinstance(raw, (int, float)) and 1 < raw <= 1023)
            if (previous.get('sensor_type') != f'soil_moisture_zone{zone}' or
                    (mode not in ('arduino_analog', 'daily_random') and not legacy_analog) or
                    old_data.get('zone', zone) != zone):
                raise ValueError(f'Refusing to replace unexpected record: {document_id}')
            matched = True
            fields = {f'data.{key}': value for key, value in data.items()}
            fields['timestamp'] = data['timestamp']
            backups.append({
                'document_id': document_id, 'exists': True,
                'fields': MessageToDict(Document(fields=encode_dict(previous))._pb)['fields'],
            })
            updates.append((reference, fields, snapshot.update_time, data))
        if create_missing and not matched:
            document_id = f'soil_history_{day:%Y%m%d}_zone{zone}'
            reference = db.collection('sensor_data').document(document_id)
            backups.append({'document_id': document_id, 'exists': False})
            payload = {'sensor_type': f'soil_moisture_zone{zone}', 'user_id': None,
                       'timestamp': data['timestamp'], 'data': data}
            updates.append((reference, payload, None, data))
    return updates, backups


def apply_updates(db, updates, backups, backup_dir):
    if len(updates) > 400:
        raise ValueError('Limit one run to 400 documents; use a shorter date range.')
    backup_dir.mkdir(parents=True, exist_ok=True)
    filename = backup_dir / f'sensor_data_{datetime.now(MANILA):%Y%m%d_%H%M%S_%f}.json'
    with filename.open('x', encoding='utf-8') as handle:
        json.dump({'project': db.project, 'collection': 'sensor_data', 'documents': backups}, handle, indent=2)
    print(f'Backup saved: {filename}', flush=True)
    from google.cloud.firestore_v1 import LastUpdateOption
    batch = db.batch()
    for reference, fields, update_time, data in updates:
        if update_time is None:
            batch.create(reference, fields)
        else:
            batch.update(reference, fields, option=LastUpdateOption(update_time))
    # Atomic commit aborts if any document changed after it was backed up.
    batch.commit(timeout=30, retry=None)
    for reference, fields, update_time, expected in updates:
        actual = reference.get(timeout=20, retry=None).to_dict()
        if actual.get('timestamp') != expected['timestamp'] or any(
                actual.get('data', {}).get(key) != value for key, value in expected.items()):
            raise RuntimeError(f'Read-back verification failed: {reference.id}')
    return filename


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-date', default='2026-09-17')
    parser.add_argument('--to-date', default=datetime.now(MANILA).date().isoformat())
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='Preview locally (default).')
    mode.add_argument('--apply', action='store_true', help='Back up and update generated Firestore records.')
    parser.add_argument('--create-missing', action='store_true', help='Also create missing daily samples.')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--adc-dry', type=int, default=1023)
    parser.add_argument('--adc-wet', type=int, default=0)
    parser.add_argument('--project', default='pinyasense')
    parser.add_argument('--backup-dir', type=Path, default=ROOT / 'data' / 'sensor_backups')
    args = parser.parse_args()
    try:
        start, end = date.fromisoformat(args.from_date), date.fromisoformat(args.to_date)
        now = datetime.now(MANILA).replace(tzinfo=None)
        if end > now.date():
            raise ValueError('Future dates are not allowed.')
        samples = list(generate_samples(start, end, args.seed, args.adc_dry, args.adc_wet))
        samples = [row for row in samples if datetime.fromisoformat(row[2]['timestamp']) <= now]
        for day, zone, data in samples:
            print(f"{day} zone{zone}: {data['value']:5.1f}% ADC={data['raw_value']:4} {data['state']:5} @ {data['timestamp']}")
        print(f'Daily samples: {len(samples)}', flush=True)
        if not args.apply:
            return 0
        from scripts.maintenance.reset_sensor_data import connect_firestore
        db = connect_firestore()
        if db.project != args.project:
            raise ValueError(f'Connected project {db.project!r} does not match {args.project!r}.')
        updates, backups = prepare_updates(db, samples, args.create_missing)
        if not updates:
            print('No matching generated documents; nothing changed.')
            return 0
        print(f'Updating {len(updates)} generated documents in {db.project}.', flush=True)
        apply_updates(db, updates, backups, args.backup_dir)
        print(f'Updated and verified {len(updates)} documents.')
        return 0
    except Exception as error:
        print(f'Sensor data update failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
