# Scripts Index

Run grouped Python helpers as modules from the `pinyasense/` application root:

```powershell
python -m scripts.training.yolov8_quickstart --help
python -m scripts.maintenance.realistic_sensor_data --help
```

Use your configured Python environment. The former flat helper paths have moved;
update external shortcuts and scheduled commands. Relative dataset and output
arguments retain their existing meaning relative to the current directory.
The Arduino bridge retains its existing file path and command.

## Training and Dataset Tools

- [quick_train.sh](training/quick_train.sh)
- [train_complete.py](training/train_complete.py)
- [train_yolov8.py](training/train_yolov8.py)
- [yolov8_quickstart.py](training/yolov8_quickstart.py)
- [prepare_yolov8_dataset.py](training/prepare_yolov8_dataset.py)
- [balance_dataset_5class.py](training/balance_dataset_5class.py)
- [convert_dataset.py](training/convert_dataset.py)
- [train_model.py](training/train_model.py)
- [TRAINING_GUIDE.py](training/TRAINING_GUIDE.py)
- [YOLOV8_ACTION_PLAN.py](training/YOLOV8_ACTION_PLAN.py)

## Diagnostics

Some tools access hardware, load models, or install dependencies. This directory
is not an offline unit-test suite. Do not run broad test discovery here.

- [setup_diagnostics.py](diagnostics/setup_diagnostics.py)
- [test_bh1750_detect.py](diagnostics/test_bh1750_detect.py)
- [test_model.py](diagnostics/test_model.py)
- [test_sensor.py](diagnostics/test_sensor.py)
- [test_simple.py](diagnostics/test_simple.py)
- [test_yolov8_inference.py](diagnostics/test_yolov8_inference.py)
- [bh1750_test.py](diagnostics/bh1750_test.py)

## Maintenance

- [firebase_setup.py](maintenance/firebase_setup.py)
- [normalize_sensor_ids.py](maintenance/normalize_sensor_ids.py)
- [realistic_sensor_data.py](maintenance/realistic_sensor_data.py)
- [reset_sensor_data.py](maintenance/reset_sensor_data.py)

Review each command before use: some operations update Firebase or local backups.
In particular, `reset_sensor_data` is not an offline test command; its write mode
must be chosen deliberately. Module relocation does not change those operations.

## Reporting

- [export_detection_reports.py](reporting/export_detection_reports.py)
- [send_detection_reports.py](reporting/send_detection_reports.py)
- [build_sample_detection_reports.py](reporting/build_sample_detection_reports.py)

Export reads Firebase and writes report artifacts. Preparation can write local
files; sending uses SMTP. Use `--send` only for an intentional email operation.

## Arduino Soil Moisture Bridge

Run the Flask app with Firestore configured, then open another terminal and
forward the Arduino JSON serial output to it. On Windows, replace `COM5` with
the port shown for the Arduino in Device Manager:

```powershell
python scripts/arduino_serial_bridge.py --port COM5 --url http://127.0.0.1:5001/save_sensor
```

The bridge forwards the latest four-zone sample immediately and then once per
minute. The Flask endpoint stores readings locally for the soil-moisture page
and in the Firestore `sensor_data` collection. The Arduino Serial Monitor must
be closed while the bridge is using the same COM port. Check the Flask startup
output for successful Firestore initialization; the bridge reports an HTTP
error if a Firestore write fails.

## Notes

- Reusable runtime modules live in `core/`.
- Move training outputs to `archive/training/` after copying deployable weights into `models/`.
## Realistic daily soil samples

`realistic_sensor_data.py` generates daily demo readings from an hourly water
balance, with shared rain events, drying, drainage, irrigation when the driest
zone drops below 25%, and small measurement noise. The four zones share an
acquisition time but have different absorption and drying rates. No display
labels or new source fields are added; existing source metadata is preserved.
These are synthetic relative moisture values, not measured weather or calibrated
volumetric water content. The default inverse ADC scale is dry=1023, wet=0;
use `--adc-dry` and `--adc-wet` if the Arduino has different measured endpoints.

From the `pinyasense` directory, preview without connecting to Firebase:

```powershell
python -m scripts.maintenance.realistic_sensor_data --from-date 2026-09-17 --to-date 2026-10-11 --dry-run
```

Apply to existing `soil_history_YYYYMMDD_zoneN` and
`daily_soil_moisture_YYYYMMDD_zoneN` documents:

```powershell
python -m scripts.maintenance.realistic_sensor_data --from-date 2026-09-17 --to-date 2026-10-11 --apply
```

A typed Firestore backup is saved under `data/sensor_backups/` before an atomic
write. Update-time preconditions prevent overwriting concurrent changes, and
read-back checks verify the resulting fields. Ownership and unrelated fields
remain intact. Hardware records with random document IDs are not touched.
Missing daily documents are skipped unless `--create-missing` is supplied.
Future dates are rejected, and overlapping date ranges produce identical samples
for the same seed and calibration. Runs are limited to 400 document updates.
The older `reset_sensor_data.py` still uses its original generator; use the new
script for the water-balance pattern.

Run the focused checks without installing pytest:

```powershell
python -m unittest discover -s tests -p test_realistic_sensor_data.py -v
```

## Normalize soil history document IDs

`normalize_sensor_ids.py` changes existing `daily_soil_moisture_*` IDs to
`soil_history_*` and gives other soil readings a `soil_history_` ID with their
timestamp and original unique suffix. It preserves every field, refuses naming
collisions and documents with subcollections, saves a typed backup under
`data/sensor_backups/`, and uses one atomic create/delete batch with source
update-time preconditions. Re-running it after migration makes no changes.

```powershell
python -m scripts.maintenance.normalize_sensor_ids          # Read-only preview
python -m scripts.maintenance.normalize_sensor_ids --apply  # Back up, rename and verify
```

## Detection CSV reports for September 18 to October 7, 2026

`export_detection_reports.py` reads all existing Firestore `disease_results` and
exports three CSVs for September 18–24, September 25–October 1, and October 2–7,
2026. It handles compact and ISO timestamps, uses inclusive Manila calendar
dates, and retains the app's eight detection report columns. Empty periods
produce header-only files. It also prepares an unsent `.eml` with the three
attachments addressed to `<recipient@example.com>`, plus a manifest with source IDs,
counts and SHA-256 checksums. It never sends email or modifies Firestore.

```powershell
python -m scripts.reporting.export_detection_reports
```

Output: `results/detection_reports_20260918_20261007/`.

## Send the prepared PinyaSense CSV reports

`send_detection_reports.py` verifies the three exported CSVs against the manifest
and prepares an email with the PinyaSense sender name, subject and body. It reads
SMTP credentials from the ignored local `.env`; passwords are never logged.

```powershell
python -m scripts.reporting.send_detection_reports         # Verify and prepare only
python -m scripts.reporting.send_detection_reports --send  # Send to <recipient@example.com>
```

A successful SMTP submission is recorded in `email_send_receipt.json` beside the
reports, and subsequent runs skip duplicate sends. If a submission starts but
its result is uncertain, the script stops retries until delivery is checked.
The receipt confirms SMTP acceptance; inbox placement is controlled by Gmail.

For one email per CSV date range:

```powershell
python -m scripts.reporting.send_detection_reports --separate
python -m scripts.reporting.send_detection_reports --separate --send
```

Each individual email uses its report date range in the PinyaSense subject and
body, with one CSV attachment. Its Date header retains the actual sending time.
Separate per-period receipts prevent duplicate individual submissions.


### Sample detection reports for the requested 2026 periods

`python -m scripts.reporting.build_sample_detection_reports` prepares the two formerly empty CSVs with deterministic sample records and three separate emails. The September 18-24 actual records remain unchanged. Sample rows use `Method=sample_generated`; details are in `sample_detection_records.json` and the report manifest. Original CSVs and manifest are backed up in `before_sample_records_v1`. This script does not write to Firebase or run a model.

After inspecting the files, `python -m scripts.reporting.build_sample_detection_reports --send` submits the three prepared emails through the configured SMTP account. The example Date headers are September 25, October 2, and October 8 at 09:00 Asia/Manila; actual receipt time is the current transmission time. Receipts in `sample_records_v1` prevent duplicate submissions on reruns.
