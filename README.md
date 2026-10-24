# PinyaSense

Existing Flask application for pineapple image/video disease detection, four-zone
soil monitoring, plot status history, growth and harvest estimates, reports, and
Raspberry Pi pump control. Authentication data is local; application records also
use Firebase Firestore. Some displays use generated fallbacks when readings are
unavailable; these are not calibrated measurements.

## Project structure

This `pinyasense/` directory is the Git and application root. Its parent,
`CAPSTONE ERA/`, also contains environments and runtime folders that are preserved.

```text
CAPSTONE ERA/
├── .venv/                       # Existing Python 3.13 environment; preserve
├── .venv311/                    # Documented Windows Python 3.11 environment
├── data/, sensor_data/, results/, static/, uploads/  # Preserve pending review
└── pinyasense/
    ├── app.py                   # Flask entry point
    ├── pinyasense.py             # Separate hardware monitoring program
    ├── agripinya                # Separate extensionless hardware program
    ├── test_sms.py              # Notification-capable manual tool
    ├── .venv/                   # Existing application Python 3.11 environment
    ├── core/
    ├── templates/
    ├── static/
    │   ├── css/
    │   ├── js/
    │   ├── icons/
    │   ├── manifest.webmanifest
    │   └── sw.js
    ├── scripts/
    │   ├── arduino_serial_bridge.py  # Existing hardware command path retained
    │   ├── training/
    │   ├── diagnostics/
    │   ├── maintenance/
    │   ├── reporting/
    │   └── README.md
    ├── tests/
    ├── models/
    ├── yolov8n.pt                # General scene-validation model
    ├── imported_dataset/
    ├── data/, sensor_data/, uploads/, results/
    ├── docs/user_materials/
    ├── archive/
    ├── requirements.txt
    ├── .env.example
    ├── .env.twilio.example
    ├── .gitignore
    ├── README.md
    ├── start.sh
    ├── deploy_to_pi.ps1
    └── agripinya.service
```

See [scripts/README.md](scripts/README.md) for grouped commands. Run helpers as
modules from the application root, for example:
`python -m scripts.maintenance.realistic_sensor_data --help`.
The former flat helper paths have moved; update external shortcuts or scheduled
commands that reference them. The serial bridge path remains unchanged.

## Environment and dependencies

The existing Windows setup uses Python 3.11. `requirements.txt` includes Flask,
OpenCV, NumPy, PyTorch, TensorFlow, Ultralytics, Firebase Admin, Twilio, ReportLab,
APScheduler, pyserial, and python-dotenv. GPIO and other Pi dependencies are
platform-specific and are not all installed by this file.

For a **new** installation, from `CAPSTONE ERA/`:

```powershell
py -3.11 -m venv .venv311
.\.venv311\Scripts\python.exe -m pip install -r .\pinyasense\requirements.txt
```

Reuse an existing working environment rather than recreating it. The workspace
`.venv`, workspace `.venv311`, and application `.venv` were all preserved. No
package versions or dependency managers were changed during organization.

## Windows startup

From `CAPSTONE ERA/`:

```powershell
Set-Location .\pinyasense
$env:PYTHONUTF8 = "1"
..\.venv311\Scripts\python.exe app.py
```

Open `http://localhost:5001`, or the configured `PORT`. Activation is optional
with an explicit interpreter; the existing activation command is
`..\.venv311\Scripts\Activate.ps1`.

Run from the application directory for consistent behavior with manual scripts.
The Flask app now anchors uploads, results, model defaults, pump settings,
schedules, accounts, and sensor history to the project directory.

Direct startup attempts to mirror existing accounts to Firestore. Flask CLI
startup skips that main-block sync, while still initializing the application:

```powershell
..\.venv311\Scripts\python.exe -m flask --app app run --host 0.0.0.0 --port 5001 --no-reload
```

Both methods can initialize models, GPIO, Firebase, and scheduled jobs. Importing
`app` is not a side-effect-free test.

## Raspberry Pi / Linux

The existing service uses a Linux installation such as
`/home/<device-user>/agripinya`, its `venv/`, and an explicit working directory.
Inspect `agripinya.service` and the actual target configuration before applying
service changes. Windows environments cannot be used as Linux environments.

For an intentional manual start on an already configured device:

```bash
cd /path/to/agripinya
bash start.sh
```

`start.sh` creates/activates `venv/` and can install packages. Its Flask check does
not verify every dependency. Model packages and GPIO libraries must match the
Pi's Python, OS, and architecture. Fresh-device setup and physical hardware were
not verified by this organization task.

`pinyasense.py` and `agripinya` are separate hardware programs, not Flask launchers.
They initialize GPIO/Firebase and can control outputs; do not import them as tests.

### Water pump from a Windows browser

The Windows app can control the Pi pump directly from its own water pump page.
Set `PUMP_REMOTE_URL=http://voicebrain.local:5001` in the Windows `.env`, and set
the same random `PUMP_BRIDGE_TOKEN` (at least 32 characters) in both hosts' `.env`
files. Leave `PUMP_REMOTE_URL` empty on the Pi. Restart both apps after changing
these settings. The token stays on the servers; the browser uses its normal
staff login. Only pump operations are exposed by the authenticated bridge.

ON/OFF, timed runs, automatic watering, and schedules use the Pi controller.
Automatic watering settings and schedules are saved on the Pi so there is one
controller executing them. The Pi and Windows host must be able to communicate.
Timed runs stop on the Pi even if the browser disconnects. Connection failures
are shown as errors and never retried automatically.

If `.local` hostname resolution is slow on Windows, use the Pi's LAN IP in
`PUMP_REMOTE_URL` instead (for example, `http://192.168.1.22:5001`) and restart the
Windows app. Reserve that address for the Pi in the router, or update this setting
if its IP changes. ON/OFF updates the display from the confirmed command response,
without waiting for another status request or the background polling interval.

If the app on the Pi reports a missing backend, install into the same virtual
environment used by its service, then restart it:

```bash
cd ~/agripinya
venv/bin/python -m pip install gpiozero lgpio
sudo systemctl restart agripinya
```

GPIO Zero documents the [virtual environment setup](https://gpiozero.readthedocs.io/en/latest/installing.html#virtual-environment).

## Configuration and storage

Use `.env.example` and `.env.twilio.example` as references. Keep real credentials
in the ignored local `.env`. Shared configuration must use placeholders:

```dotenv
PORT=5001
USE_HTTPS=0
PINEAPPLE_MODEL_PATH=models/pineapple_yolov8n_latest.pt
FIREBASE_SERVICE_ACCOUNT_KEY=/path/to/private-service-account.json
MAIL_SERVER=<smtp-host>
MAIL_USERNAME=<smtp-user>
MAIL_PASSWORD=<smtp-password>
TWILIO_ACCOUNT_SID=<account-sid>
TWILIO_AUTH_TOKEN=<auth-token>
TWILIO_FROM_NUMBER=<sender-number>
```

`.env.example` also contains legacy options. `core/config.py` is not currently
loaded as Flask's full configuration object; not every example key overrides
`app.py`. Optional camera HTTPS mode uses `USE_HTTPS=1` and existing `cert.pem`
and `key.pem` files in the application working directory.

- `data/`: accounts, sessions, reset codes, notifications, pump settings,
  schedules, and maintenance backups where configured.
- `sensor_data/`: local daily sensor history.
- `uploads/` and `results/`: detection inputs, outputs, and reports.
- Firestore: plot, status, problem, prediction, and other application records.

The parent workspace has another `data/auto_pump_settings.json`. Its complete
contents differ from the application copy. Neither was merged or selected as a
migration source. Preserve both until their readers and intended settings are
reviewed. Notifications now read canonical accounts from `data/users.json` and
write delivery history under `data/`, with a read fallback for existing legacy
notification history. Configured delivery providers are used during normal app
operation; the audit tests mock delivery and do not send messages.

## Models and datasets

The current default disease-model candidate is
`models/pineapple_yolov8n_latest.pt`. `PINEAPPLE_MODEL_PATH` takes precedence over
`MODEL_PATH`; supported fallback formats are listed in `core/disease_detector.py`.
Metadata stays under `models/`.

Root `yolov8n.pt` supports general scene validation. Another copy is under
`imported_dataset/yolov8_detection/`; both paths were preserved even though their
current hashes match. Preserve trained weights, `.bak` files, metadata, and
archives. The active trained weight is ignored by Git: a Git-only backup is
insufficient. The legacy model README does not describe every current model.

`imported_dataset/` contains the original and five-class datasets. Existing YAMLs
include relative, Windows-specific, and Pi-specific paths. Choose the appropriate
configuration for the training host. No dataset paths, class mappings, splits,
weights, or training artifacts were changed.

## Offline checks

From `pinyasense/`, using the existing Windows environment:

```powershell
..\.venv311\Scripts\python.exe -B -m unittest discover -s tests -p test_project_organization.py -v
..\.venv311\Scripts\python.exe -B -m unittest discover -s tests -p test_realistic_sensor_data.py -v
node tests/forecast_ui.test.cjs
node tests/detection_ui.test.cjs
node tests/soil_live_ui.test.cjs
node tests/service_worker.test.cjs
```

Organization checks use mocked subprocesses and isolated asset routes.
Maintenance checks use temporary backups and mocked storage. They do not require
physical hardware or live Firebase writes.

All unittest suites in `tests/` now run without initializing the real app,
models, GPIO, scheduled jobs, or cloud clients:

```powershell
..\.venv311\Scripts\python.exe -B -m unittest discover -s tests -v
```

Authentication approval and time-series fixture tests additionally use pytest:

```powershell
..\.venv311\Scripts\python.exe -m pip install -r requirements-dev.txt
..\.venv311\Scripts\python.exe -B -m pytest tests -q
```

Do not run broad discovery across `scripts/` or execute `test_sms.py`: manual
tools can load models, access hardware, change external data, or send messages.
See [the project audit](docs/PROJECT_AUDIT.md) for root causes, fixes, and
validation limits.

## Deployment and troubleshooting

### Deploy code to the Raspberry Pi

Run this in PowerShell from the parent `CAPSTONE ERA` folder:

```powershell
.\pinyasense\deploy_to_pi.ps1
```

If your terminal is already inside `pinyasense/`, use:

```powershell
.\deploy_to_pi.ps1
```

The Raspberry Pi must be powered on and reachable at `voicebrain.local`, with
SSH enabled and the existing app installed at `~/agripinya`. Windows must have
`ssh` and `scp` available. The script connects as `voicebrain` and may prompt
for its SSH password or the password required by `sudo`.

The script uploads the selected application files, templates, JavaScript, CSS,
PWA assets, runtime modules, `yolov8n.pt`, requirements file, and serial bridge.
This includes the password eye icons on login and sign up. It then restarts the
`agripinya` service, checks whether the service is active, and checks the public
site. It copies `requirements.txt` but does not install dependencies.

**Account data and credentials are preserved by default.** To intentionally
replace them with the local copies, run from `pinyasense/`:

```powershell
.\deploy_to_pi.ps1 -IncludeAccounts -IncludeFirebaseKey
```

`-IncludeAccounts` first creates a timestamped backup of the Pi's accounts.
`-IncludeFirebaseKey` uploads the local service account key. Use only the flags
you need. The script stops on failed SSH or SCP commands before continuing to
later steps. Edit `$PiHost` and `$PiPath` if your Pi uses a different username,
hostname, or application directory. This script updates an existing installation;
it does not install the trained disease weights, dependencies, or the service.

After changing Python routes or modules locally, restart the Flask process;
template auto-reload does not reload Python. Keep normal network access available
when launching it so Firebase can connect.

For a serial bridge running on the same Pi, `/save_sensor` accepts loopback POSTs.
Remote bridges must configure `SENSOR_INGEST_TOKEN` in the server environment and
send the matching token with `scripts/arduino_serial_bridge.py --token VALUE`.
Prefer setting the bridge environment variable instead of putting a token in
shell history. GET requests to this endpoint no longer create sample readings.

Timed watering is limited to 300 seconds by default. Set
`WATER_PUMP_MAX_DURATION_SECONDS` in the server environment and restart the app
if your installation requires a different maximum.

### Troubleshooting

- Failed PWA registration: verify `manifest.webmanifest` and `sw.js` are directly
  in `static/`, as expected by their Flask routes.
- Helper not found: use its new module command in `scripts/README.md` from the
  application root; update external callers of former flat paths.
- Missing models or unexpected JSON settings: check the current directory before
  changing data or configuration.
- `/training-results` now displays saved detection records. It requires an
  approved account, like the dashboard.

## Snapshot and rollback

The approved migration snapshot is outside the Git root:
`../_organization_backups/20261023_193517/`. It includes original affected files,
`manifest.json` with old/new paths, the pre-existing Git diff/status, and a
preservation hash baseline. Treat it as private: original documentation may
contain connection details. Keep it until this migration has been reviewed.

To roll back, preserve any newer edits, reverse the listed moves, and restore
original affected files from the snapshot's `files/` directory. Set aside new
files rather than deleting them. Use the snapshot, not `git reset --hard` or
`git clean`, because the working tree already had uncommitted and untracked work.

No environments, caches, runtime records, models, datasets, or archived outputs
were deleted. A future runtime-data migration needs a separate source-selection,
writer-pause, backup, and rollback plan before moving data.
