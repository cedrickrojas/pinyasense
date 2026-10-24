#!/usr/bin/env python3
"""Normalize existing soil sensor document IDs without changing payloads.

Firestore IDs cannot be renamed directly. Create the destination and delete the
source in one atomic batch, after a typed backup and collision checks.
"""
from __future__ import annotations
import argparse
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANILA = timezone(timedelta(hours=8))


def target_id(document_id, payload):
    if document_id.startswith('soil_history_'):
        return document_id
    match = re.fullmatch(r'daily_soil_moisture_(\d{8})_zone([1-4])', document_id)
    if match:
        date.fromisoformat(match[1])
        return f'soil_history_{match[1]}_zone{match[2]}'
    if not str(payload.get('sensor_type', '')).startswith('soil_moisture'):
        raise ValueError(f'Unexpected non-soil document: {document_id}')
    timestamp = datetime.fromisoformat(str(payload['timestamp']).replace('Z', '+00:00'))
    if timestamp.tzinfo:
        timestamp = timestamp.astimezone(MANILA)
    # Retain the original unique suffix for multiple readings on the same day.
    return f'soil_history_{timestamp:%Y%m%d_%H%M%S_%f}_{document_id}'


def plan_renames(snapshots):
    existing_ids = {snapshot.id for snapshot in snapshots}
    used_targets = set()
    plan = []
    for snapshot in snapshots:
        destination = target_id(snapshot.id, snapshot.to_dict())
        if destination == snapshot.id:
            continue
        if destination in existing_ids or destination in used_targets:
            raise ValueError(f'Destination already exists: {destination}')
        used_targets.add(destination)
        plan.append((snapshot, destination))
    if len(plan) > 200:
        raise ValueError('More than 200 renames; aborting before any write.')
    return plan


def migrate(db, plan):
    from google.cloud.firestore_v1 import LastUpdateOption
    from google.cloud.firestore_v1._helpers import encode_dict
    from google.cloud.firestore_v1.types import Document
    from google.protobuf.json_format import MessageToDict
    backups = []
    for source, destination in plan:
        # Do not silently leave subcollections under a deleted parent ID.
        if list(source.reference.collections()):
            raise ValueError(f'Document has subcollections: {source.id}')
        backups.append({
            'source_id': source.id, 'destination_id': destination,
            'fields': MessageToDict(Document(fields=encode_dict(source.to_dict()))._pb)['fields'],
        })
    folder = ROOT / 'data' / 'sensor_backups'
    folder.mkdir(parents=True, exist_ok=True)
    filename = folder / f'sensor_id_rename_{datetime.now(MANILA):%Y%m%d_%H%M%S_%f}.json'
    with filename.open('x', encoding='utf-8') as handle:
        json.dump({'project': db.project, 'collection': 'sensor_data', 'documents': backups}, handle, indent=2)
    print(f'Backup: {filename}', flush=True)
    batch = db.batch()
    collection = db.collection('sensor_data')
    for source, destination in plan:
        batch.create(collection.document(destination), source.to_dict())
        batch.delete(source.reference, option=LastUpdateOption(source.update_time))
    batch.commit(timeout=30, retry=None)
    current = {snapshot.id: snapshot.to_dict() for snapshot in collection.stream(timeout=30, retry=None)}
    for source, destination in plan:
        if source.id in current or current.get(destination) != source.to_dict():
            raise RuntimeError(f'Verification failed: {source.id} -> {destination}')
    print(f'Renamed and verified: {len(plan)}. Total records: {len(current)}.', flush=True)
    print('Remaining daily_soil_moisture IDs:', sum(key.startswith('daily_soil_moisture_') for key in current))
    print('soil_history IDs:', sum(key.startswith('soil_history_') for key in current))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Write after backup; default is read-only preview.')
    args = parser.parse_args()
    from scripts.maintenance.reset_sensor_data import connect_firestore
    db = connect_firestore()
    if db.project != 'pinyasense':
        raise ValueError('Refusing to migrate a different project.')
    snapshots = list(db.collection('sensor_data').stream(timeout=30, retry=None))
    plan = plan_renames(snapshots)
    print(f'Project: {db.project}; records: {len(snapshots)}; renames: {len(plan)}', flush=True)
    for source, destination in plan:
        print(f'{source.id} -> {destination}', flush=True)
    if args.apply and plan:
        migrate(db, plan)
    elif not plan:
        print('All IDs are already normalized.')


if __name__ == '__main__':
    main()
