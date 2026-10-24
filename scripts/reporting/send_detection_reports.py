#!/usr/bin/env python3
"""Verify and send the prepared PinyaSense CSV reports using local SMTP config.

Default: prepare the email without sending. --send requires configured SMTP and
saves a receipt after server acceptance. Never logs the SMTP password.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formataddr, format_datetime, make_msgid
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / 'results' / 'detection_reports_20260918_20261007'
RECIPIENT = 'agripinyaa@gmail.com'
MANILA = timezone(timedelta(hours=8))


def prepare_message(folder, sender):
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    reports = manifest['reports']
    if len(reports) != 3:
        raise ValueError('Expected exactly three CSV reports.')
    message = EmailMessage(policy=SMTP)
    message['From'] = formataddr(('PinyaSense', sender))
    message['To'] = RECIPIENT
    message['Subject'] = 'PinyaSense - Detection Reports (September 18 - October 7, 2026)'
    message['Date'] = format_datetime(datetime.now(MANILA))
    message['Message-ID'] = make_msgid(domain=sender.split('@')[-1])
    body = ['Attached are the PinyaSense detection reports (CSV) for the following inclusive date ranges in 2026:', '']
    for report in reports:
        body.append(f"{report['start_date']} to {report['end_date']}: {report['record_count']} detection records.")
    source_note = ('Reports include generated sample records for demo/testing; the Method column identifies them as sample_generated.'
                   if manifest.get('sample_record_count', 0) else 'Reports contain the existing detection results from PinyaSense.')
    body += ['', source_note,
             'A CSV with only column headers means no detection records were found for that period.', '', 'PinyaSense']
    message.set_content('\n'.join(body))
    for report in reports:
        name = report['filename']
        if Path(name).name != name or not name.endswith('.csv'):
            raise ValueError('Invalid attachment filename.')
        path = folder / name
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != report['sha256']:
            raise ValueError(f'Attachment checksum mismatch: {name}')
        with path.open(encoding='utf-8-sig', newline='') as handle:
            rows = list(csv.reader(handle))
        if len(rows) - 1 != report['record_count'] or any(len(row) != 8 for row in rows):
            raise ValueError(f'Invalid CSV structure: {name}')
        if any(not report['start_date'] <= row[0] <= report['end_date'] for row in rows[1:]):
            raise ValueError(f'Date outside requested range: {name}')
        message.add_attachment(content, maintype='text', subtype='csv', filename=name)
    return message, manifest


def submit_message(message, reports, receipt, attempt, sender):
    if receipt.exists():
        print(f'Already sent; skipping: {message["Subject"]}', flush=True)
        return
    if attempt.exists():
        raise RuntimeError('Previous submission has no receipt; check delivery before retrying.')
    server_host = os.getenv('MAIL_SERVER', '').strip()
    server_port = int(os.getenv('MAIL_PORT', '587'))
    password = os.getenv('MAIL_PASSWORD', '').replace(' ', '')
    if not server_host or not password:
        raise ValueError('SMTP credentials are missing; nothing sent.')
    # Authenticate before recording an uncertain delivery attempt. Authentication
    # errors can be corrected safely because no message has been submitted yet.
    server = smtplib.SMTP_SSL(server_host, server_port, timeout=30, context=ssl.create_default_context()) if server_port == 465 else smtplib.SMTP(server_host, server_port, timeout=30)
    try:
        server.ehlo()
        if server_port != 465:
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
        server.login(sender, password)
        print('SMTP authentication succeeded.', flush=True)
        info = {'status': 'submission_started', 'recipient': RECIPIENT, 'sender': sender,
                'subject': str(message['Subject']), 'message_id': str(message['Message-ID']),
                'attempted_at': datetime.now(MANILA).isoformat(),
                'attachments': [{'filename': r['filename'], 'sha256': r['sha256'], 'record_count': r['record_count']} for r in reports]}
        with attempt.open('x', encoding='utf-8') as handle:
            json.dump(info, handle, indent=2)
        refused = server.send_message(message, from_addr=sender, to_addrs=[RECIPIENT])
        if refused:
            raise RuntimeError('SMTP did not accept the recipient.')
        info.update(status='accepted_by_smtp', accepted_at=datetime.now(MANILA).isoformat())
        with receipt.open('x', encoding='utf-8') as handle:
            json.dump(info, handle, indent=2)
        print(f'Email accepted by SMTP: {message["Subject"]} ({len(reports)} CSV attachments).', flush=True)
        print(f'Receipt saved: {receipt}', flush=True)
    finally:
        server.close()


def prepare_individual_messages(folder, sender):
    combined, manifest = prepare_message(folder, sender)
    attachments = {part.get_filename(): part.get_payload(decode=True) for part in combined.iter_attachments()}
    prepared = []
    for report in manifest['reports']:
        start = datetime.fromisoformat(report['start_date'])
        end = datetime.fromisoformat(report['end_date'])
        period = f"{start:%B} {start.day} - {end:%B} {end.day}, {end.year}"
        message = EmailMessage(policy=SMTP)
        message['From'] = formataddr(('PinyaSense', sender))
        message['To'] = RECIPIENT
        message['Subject'] = f'PinyaSense - Detection Report ({period})'
        # The header records actual submission time; report dates are in subject/body.
        message['Date'] = format_datetime(datetime.now(MANILA))
        message['Message-ID'] = make_msgid(domain=sender.split('@')[-1])
        body = ['Attached is the PinyaSense detection report (CSV).', '',
                f'Reporting period: {period}', f"Detection records: {report['record_count']}"]
        if report.get('sample_record_count', 0):
            body += ['', 'Data source: generated sample records for demo/testing; no actual detections were performed for these dates.']
        if report['record_count'] == 0:
            body += ['', 'No detection records were found for this period; the CSV contains column headers only.']
        body += ['', 'PinyaSense']
        message.set_content('\n'.join(body))
        message.add_attachment(attachments[report['filename']], maintype='text', subtype='csv', filename=report['filename'])
        prepared.append((message, report))
    return prepared


def send_individual_reports(sender, send=False):
    messages = prepare_individual_messages(FOLDER, sender)
    # Save all reviewable messages before any submission.
    for message, report in messages:
        key = f"{report['start_date']}_to_{report['end_date']}"
        (FOLDER / f'detection_report_email_{key}.eml').write_bytes(message.as_bytes())
        print(f'Prepared: {message["Subject"]}; one CSV, {report["record_count"]} records.', flush=True)
    if not send:
        print('Three individual messages verified locally; not sent.')
        return
    # Preflight all states before sending the first message.
    for message, report in messages:
        key = f"{report['start_date']}_to_{report['end_date']}"
        receipt = FOLDER / f'email_send_receipt_{key}.json'
        attempt = FOLDER / f'email_send_attempt_{key}.json'
        if attempt.exists() and not receipt.exists():
            raise RuntimeError(f'Previous submission has no receipt for {key}; check delivery before retrying.')
    for message, report in messages:
        key = f"{report['start_date']}_to_{report['end_date']}"
        submit_message(message, [report], FOLDER / f'email_send_receipt_{key}.json',
                       FOLDER / f'email_send_attempt_{key}.json', sender)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--send', action='store_true')
    parser.add_argument('--separate', action='store_true', help='One email per report date range.')
    args = parser.parse_args()
    load_dotenv(ROOT / '.env')
    sender = os.getenv('MAIL_USERNAME', '').strip()
    if not sender or '@' not in sender:
        raise ValueError('MAIL_USERNAME is missing.')
    if args.separate:
        send_individual_reports(sender, send=args.send)
        return
    receipt = FOLDER / 'email_send_receipt.json'
    attempt = FOLDER / 'email_send_attempt.json'
    if args.send and receipt.exists():
        print('This report email has already been accepted by SMTP; skipped duplicate send.')
        return
    if args.send and attempt.exists():
        raise RuntimeError('A previous send attempt has no receipt; check delivery before retrying.')
    message, manifest = prepare_message(FOLDER, sender)
    (FOLDER / 'detection_reports_email.eml').write_bytes(message.as_bytes())
    print(f'Prepared: {message["Subject"]}', flush=True)
    print(f'From: PinyaSense <{sender}>; To: {RECIPIENT}; CSV attachments: 3', flush=True)
    if not args.send:
        print('Verified locally; not sent.')
        return
    submit_message(message, manifest['reports'], receipt, attempt, sender)


if __name__ == '__main__':
    main()
