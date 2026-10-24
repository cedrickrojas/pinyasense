#!/usr/bin/env python3
"""Prepare explicitly sourced sample CSVs for two empty periods; optionally email each report.

Offline preparation is the default. Does not write to Firebase or run inference.
Existing actual rows and previous email receipts are preserved.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
import random
import shutil
from datetime import date, datetime, time, timedelta
from pathlib import Path

from scripts.reporting import send_detection_reports as mail
from scripts.reporting.export_detection_reports import HEADERS, create_csv

REVISION = 'sample_records_v1'
SAMPLE_METHOD = 'sample_generated'
SCHEDULES = [
    ('2026-09-25', '2026-10-01', [3, 2, 1, 4, 3, 2, 4]),
    ('2026-10-02', '2026-10-07', [3, 2, 1, 4, 3, 2]),
]
SEVERITY = {'Healthy': 'None', 'Yellow Spot': 'Medium', 'Fruit Rot': 'High', 'Heart Rot': 'High'}


def generate_samples():
    rng = random.Random(20260925)
    generated_at = datetime.now(mail.MANILA).isoformat()
    records = []
    for start_text, end_text, daily_counts in SCHEDULES:
        start = date.fromisoformat(start_text)
        for offset, count in enumerate(daily_counts):
            day = start + timedelta(days=offset)
            morning = datetime.combine(day, time(rng.randint(8, 10), rng.randint(2, 49), rng.randint(0, 59)), mail.MANILA)
            afternoon = datetime.combine(day, time(rng.randint(13, 15), rng.randint(2, 49), rng.randint(0, 59)), mail.MANILA)
            morning_count = (count + 1) // 2
            sessions = [(morning, morning_count), (afternoon, count - morning_count)]
            for first, session_count in sessions:
                stamp = first
                for _ in range(session_count):
                    disease = rng.choices(list(SEVERITY), weights=[55, 21, 16, 8])[0]
                    mean = .88 if disease == 'Healthy' else .81
                    confidence = round(max(.55, min(.98, rng.gauss(mean, .075))), 4)
                    identifier = 'sample_' + stamp.strftime('%Y%m%d_%H%M%S')
                    row = {'timestamp': stamp.isoformat(), 'disease': disease, 'confidence': confidence,
                           'severity': SEVERITY[disease], 'method': SAMPLE_METHOD, 'media_type': 'image',
                           'farm': 'Unknown', 'source': SAMPLE_METHOD, 'is_simulated': True,
                           'generated_at': generated_at,
                           'note': 'Generated example; no photo inference or historical observation.'}
                    records.append((stamp, identifier, row))
                    stamp += timedelta(seconds=rng.randint(48, 210))
    return records


def prepare():
    folder = mail.FOLDER
    manifest_path = folder / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    expected = {(start, end) for start, end, _ in SCHEDULES}
    if len(manifest['reports']) != 3:
        raise ValueError('Unexpected report manifest.')
    # Refuse to replace any actual observations in the two formerly empty periods.
    for report in manifest['reports']:
        if (report['start_date'], report['end_date']) not in expected:
            continue
        with (folder / report['filename']).open(encoding='utf-8-sig', newline='') as handle:
            rows = list(csv.DictReader(handle))
        if any(row['Method'] != SAMPLE_METHOD for row in rows):
            raise ValueError('Existing actual records must not be replaced with samples.')
    backup = folder / ('before_' + REVISION)
    if not backup.exists():
        backup.mkdir()
        shutil.copy2(manifest_path, backup / manifest_path.name)
        for report in manifest['reports']:
            shutil.copy2(folder / report['filename'], backup / report['filename'])
    records = generate_samples()
    for report in manifest['reports']:
        if (report['start_date'], report['end_date']) not in expected:
            report['source'] = 'existing_firestore_logs'
            report['actual_record_count'] = report['record_count']
            report['sample_record_count'] = 0
            continue
        start, end = date.fromisoformat(report['start_date']), date.fromisoformat(report['end_date'])
        content, identifiers = create_csv(records, start, end)
        target = folder / report['filename']
        target.write_bytes(content)
        with target.open(encoding='utf-8-sig', newline='') as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != HEADERS:
                raise ValueError('Unexpected CSV schema.')
            rows = list(reader)
        stamps = [datetime.fromisoformat(row['Date'] + 'T' + row['Time']) for row in rows]
        assert len(rows) == len(identifiers) > 0
        assert stamps == sorted(stamps) and len(set(stamps)) == len(stamps)
        assert all(start <= stamp.date() <= end and 8 <= stamp.hour <= 16 for stamp in stamps)
        assert all(row['Method'] == SAMPLE_METHOD and row['Severity'] == SEVERITY[row['Disease']] for row in rows)
        assert all(55 <= float(row['Confidence'].rstrip('%')) <= 98 for row in rows)
        report.update(record_count=len(rows), document_ids=[], record_ids=identifiers,
                      source=SAMPLE_METHOD, actual_record_count=0, sample_record_count=len(rows),
                      sha256=hashlib.sha256(content).hexdigest())
    manifest.update(revision=REVISION, updated_at=datetime.now(mail.MANILA).isoformat(),
                    sample_record_count=len(records),
                    note='September 18-24: existing Firestore results. Later periods: generated samples, not historical detections.')
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    (folder / 'sample_detection_records.json').write_text(json.dumps(
        {'source': SAMPLE_METHOD, 'seed': 20260925,
         'records': [{'record_id': identifier, **row} for _, identifier, row in records]}, indent=2) + '\n', encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--send', action='store_true')
    args = parser.parse_args()
    mail.load_dotenv(mail.ROOT / '.env')
    sender = os.getenv('MAIL_USERNAME', '').strip()
    if not sender or '@' not in sender:
        raise ValueError('MAIL_USERNAME is missing.')
    # A rerun after submission reuses the saved messages and checks existing receipts.
    outbox = mail.FOLDER / REVISION
    if (outbox / 'outbox_manifest.json').exists():
        messages_info = json.loads((outbox / 'outbox_manifest.json').read_text(encoding='utf-8'))
    else:
        manifest = prepare()
        outbox.mkdir(exist_ok=True)
        messages_info = []
        for message, report in mail.prepare_individual_messages(mail.FOLDER, sender):
            key = report['start_date'] + '_to_' + report['end_date']
            header_date = datetime.combine(date.fromisoformat(report['end_date']) + timedelta(days=1), time(9), mail.MANILA)
            message.replace_header('Date', mail.format_datetime(header_date))
            source = ('Existing PinyaSense detection logs.' if report.get('source') == 'existing_firestore_logs'
                      else 'Generated sample records for demo/testing; no actual detections were performed for these dates.')
            message.get_body(preferencelist=('plain',)).set_content(
                f"Attached is the PinyaSense detection report (CSV).\n\nReporting period: {report['start_date']} to {report['end_date']}\n"
                f"Records: {report['record_count']}\nData source: {source}\n\n"
                'The email Date header is set for this report example; actual Gmail receipt time is the current transmission time.\n\nPinyaSense\n')
            (outbox / (key + '.eml')).write_bytes(message.as_bytes())
            messages_info.append({'key': key, 'report': report, 'date_header': header_date.isoformat(),
                                  'prepared_at': datetime.now(mail.MANILA).isoformat(), 'message_id': str(message['Message-ID'])})
        (outbox / 'outbox_manifest.json').write_text(json.dumps(messages_info, indent=2) + '\n', encoding='utf-8')
    from email.parser import BytesParser
    from email.policy import SMTP
    prepared = []
    for info in messages_info:
        key, report = info['key'], info['report']
        message = BytesParser(policy=SMTP).parsebytes((outbox / (key + '.eml')).read_bytes())
        attachments = list(message.iter_attachments())
        if (len(attachments) != 1 or str(message['To']) != mail.RECIPIENT
                or hashlib.sha256(attachments[0].get_payload(decode=True)).hexdigest() != report['sha256']):
            raise ValueError('Prepared email verification failed.')
        receipt, attempt = outbox / (key + '_receipt.json'), outbox / (key + '_attempt.json')
        if attempt.exists() and not receipt.exists():
            raise RuntimeError('Uncertain earlier submission; check receipt before retrying.')
        prepared.append((message, report, receipt, attempt))
        print(json.dumps({'report': report['filename'], 'records': report['record_count'],
                          'source': report['source'], 'date_header': info['date_header']}), flush=True)
    if args.send:
        for message, report, receipt, attempt in prepared:
            mail.submit_message(message, [report], receipt, attempt, sender)
    else:
        print('Three separate emails prepared and verified; not sent.', flush=True)


if __name__ == '__main__':
    main()
