#!/usr/bin/env python3
"""Export the requested 2026 detection reports and prepare one email with CSVs.

Reads disease_results only; never changes Firestore or sends email. Dates are
inclusive in Asia/Manila. Compact legacy timestamps and ISO timestamps are
supported, without importing app.py or starting its scheduled jobs.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from email.policy import SMTP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANILA = timezone(timedelta(hours=8))
PERIODS = [('2026-09-18', '2026-09-24'), ('2026-09-25', '2026-10-01'), ('2026-10-02', '2026-10-07')]
HEADERS = ['Date', 'Time', 'Disease', 'Confidence', 'Severity', 'Method', 'Media Type', 'Farm']


def parse_timestamp(value):
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or '').strip()
        try:
            parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
        except ValueError:
            parsed = datetime.strptime(text, '%Y%m%d_%H%M%S')
    return parsed.replace(tzinfo=MANILA) if parsed.tzinfo is None else parsed.astimezone(MANILA)


def csv_cell(value, default='Unknown'):
    text = str(value) if value is not None and value != '' else default
    # Protect spreadsheet users if a field starts with a formula character.
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) else text


def create_csv(records, start, end):
    selected = [(stamp, document_id, row) for stamp, document_id, row in records if start <= stamp.date() <= end]
    selected.sort(key=lambda item: (item[0], item[1]))
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(HEADERS)
    for stamp, document_id, row in selected:
        confidence = row.get('confidence')
        confidence_text = f'{float(confidence):.2%}' if confidence is not None else 'Unknown'
        writer.writerow([
            stamp.date().isoformat(), stamp.strftime('%H:%M:%S'),
            csv_cell(row.get('disease')), confidence_text,
            csv_cell(row.get('severity')), csv_cell(row.get('method'), 'unknown'),
            csv_cell(row.get('media_type'), 'image'), csv_cell(row.get('farm')),
        ])
    return output.getvalue().encode('utf-8-sig'), [document_id for _, document_id, _ in selected]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'results' / 'detection_reports_20260918_20261007')
    args = parser.parse_args()
    from scripts.maintenance.reset_sensor_data import connect_firestore
    db = connect_firestore()
    if db.project != 'pinyasense':
        raise ValueError('Unexpected Firebase project.')
    snapshots = list(db.collection('disease_results').stream(timeout=30, retry=None))
    records, invalid = [], []
    for snapshot in snapshots:
        row = snapshot.to_dict()
        try:
            stamp = parse_timestamp(row.get('timestamp'))
        except (ValueError, TypeError):
            invalid.append(snapshot.id)
            continue
        records.append((stamp, snapshot.id, row))
    if invalid:
        raise ValueError(f'Invalid timestamps in {len(invalid)} records; aborting to avoid omissions.')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {'project': db.project, 'collection': 'disease_results', 'timezone': 'Asia/Manila',
                'generated_at': datetime.now(MANILA).isoformat(), 'source_record_count': len(snapshots), 'reports': []}
    attachments = []
    for start_text, end_text in PERIODS:
        start, end = date.fromisoformat(start_text), date.fromisoformat(end_text)
        content, document_ids = create_csv(records, start, end)
        name = f'detections_report_{start_text}_to_{end_text}.csv'
        target = args.output_dir / name
        target.write_bytes(content)
        # Re-open the actual artifact and verify the row count and field count.
        with target.open(encoding='utf-8-sig', newline='') as handle:
            rows = list(csv.reader(handle))
        if rows[0] != HEADERS or len(rows) - 1 != len(document_ids) or any(len(row) != 8 for row in rows):
            raise RuntimeError(f'CSV verification failed: {name}')
        manifest['reports'].append({'filename': name, 'start_date': start_text, 'end_date': end_text,
                                    'record_count': len(document_ids), 'document_ids': document_ids,
                                    'sha256': hashlib.sha256(content).hexdigest()})
        attachments.append((name, content))
        print(f'{name}: {len(document_ids)} detection records', flush=True)
    message = EmailMessage(policy=SMTP)
    message['To'] = 'agripinyaa@gmail.com'
    message['Subject'] = 'AgriPinya - Detection Reports (September 18 - October 7, 2026)'
    body = ['Attached are the detection reports (CSV) for the following inclusive date ranges in 2026:', '']
    for report in manifest['reports']:
        body.append(f"{report['start_date']} to {report['end_date']}: {report['record_count']} detection records.")
    body += ['', 'Reports contain the existing detection results from AgriPinya.',
             'A CSV with only column headers means no detection records were found for that period.']
    message.set_content('\n'.join(body))
    for name, content in attachments:
        message.add_attachment(content, maintype='text', subtype='csv', filename=name)
    (args.output_dir / 'detection_reports_email.eml').write_bytes(message.as_bytes())
    (args.output_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Files and unsent email prepared:', args.output_dir)


if __name__ == '__main__':
    main()
