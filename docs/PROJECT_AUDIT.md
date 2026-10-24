# Project audit and fixes

Reviewed October 23, 2026. Scope: Flask routes and helpers, authentication,
detection and media handling, local/cloud records, sensors and irrigation,
forecasting, reports and notifications, templates, browser scripts, service
worker, deployment/startup configuration, and the manual scripts' imports and
syntax. Existing uncommitted work, records, datasets, model weights, and legacy
hardware programs were preserved.

## Important findings and root causes

| Issue | Root cause | Implemented fix |
| --- | --- | --- |
| Reusable password reset codes | `reset_password()` returned before deleting the code. | Consume successful codes, revoke old sessions, reject short passwords, and expire codes after five wrong guesses. |
| Weak password storage | Passwords used unsalted SHA-256. | Salted PBKDF2 for new passwords; successful legacy logins upgrade the hash without requiring a password reset. |
| Sessions survived deactivation | Session validation checked expiry without checking current account access. | Validate account approval/status and invalidate sessions on deactivation, rejection, and password reset. Reactivation does not restore old sessions. |
| JSON files could be truncated or lose concurrent updates | Stores wrote directly to live files; authentication read/modify/write operations were not serialized. | Shared atomic JSON writer, an authentication lock, and serialized sensor appends. Multi-process limitations remain below. |
| Missing authorization on sensitive endpoints | Pump routes, single-image detection, statistics, sensor/history endpoints, and the manual report trigger lacked consistent guards. | Reuse approval-aware API checks; require administrator access for manual report delivery. Preserve the same-site serial bridge with a separate ingest policy. |
| Other users' records could appear in local fallback | Local history ignored record ownership, while cloud history filtered it. | Consistent user scope across statistics, history, media, trends, and exports. Administrators retain access to legacy unowned files; staff see owned records. |
| Detection history disappeared during cloud failure | Some reads were unbounded, empty cloud results prevented fallback, and views used different sources. | Bounded cloud reads and a shared local fallback; include new locally saved records whose cloud writes failed, without duplicating successfully uploaded records. |
| Total detections stopped increasing at 1,000 | Statistics counted a limited recent-history query. | Statistics read the full accessible result set; only the displayed recent list is capped. |
| Non-detection JSON files inflated totals | The old local counter included every JSON file, including a sensor-data migration manifest. | Load validated detection-result files only; preserve unrelated JSON metadata without counting it as a disease detection. |
| Image metadata was missing from saved records | The result file was written before adding media, farm, and timestamp fields. | Assemble the complete result before saving; use unique record IDs and consistent ISO timestamps. |
| Batch/video results were lost offline | Those endpoints saved only to Firestore, and cloud exceptions turned successful analysis into failed requests. | Persist every successful analysis locally before attempting cloud storage. Reject analysis errors and non-pineapple results without counting them. |
| Uploads could overwrite one another | Single-image uploads and result documents used timestamps with second precision. | Unique record IDs and upload names; report and notification IDs also use UUIDs. |
| Uploaded media returned 404 | The UI referenced `/uploads/...`, but no corresponding route existed. | Add an authenticated, owner-aware media route with private, no-store response headers. |
| Predictions were labeled as different diseases | Model mappings changed `RootRot` into Pink Disease, `MealybugWilt` into Yellow Spot, and disorders into unrelated disease categories. | Preserve the loaded model's named condition; use the generic expert-review recommendation when no matching knowledge-base entry exists. Historical records are not relabeled. |
| Some YOLO checkpoints would not load | The loader identified YOLO by whether the filename contained `yolov8`. | Try the checkpoint loader for `.pt` files, including `best.pt`, then retain the plain PyTorch fallback. Keras inference no longer requires compiling training metrics. |
| Video requests interfered with one another | Temporary frame filenames were shared, sampling could exceed the limit, FPS could be zero, and failed/rejected frames were included. | Isolated temporary directories, bounded sampling, safe zero-FPS handling, guaranteed resource cleanup, and aggregation of valid frames only. Confidence describes the selected condition's frames. |
| A single result failed after batch/video output | Those displays replaced the original DOM elements that `displayResults()` later expected. | Preserve and restore the original single-result layout before rendering the next image result. |
| Sensor CSV exports contained the wrong data | The exporter queried detection records for both report scopes and omitted nested sensor `value` fields. | Query the sensor source for sensor exports and preserve legitimate zero values. |
| Legacy timestamps broke trends/date filters | Analytics assumed every record used a naive ISO timestamp, while saved records also used compact filenames and timezone-aware dates. | Shared timestamp parsing; normalize timezone-aware values, skip invalid dated records, and exclude the following day's midnight from end-date filters. |
| Healthy plants increased disease spread risk | The heuristic counted every recent detection as diseased. | Exclude Healthy, Unknown, and rejected-image categories from disease frequency. This remains a heuristic, not a validated epidemiological forecast. |
| Weather requests returned 500 | The route called the nonexistent `read_sensor_data()` method and did not handle nested values. | Read recent recorded live temperature/humidity data; return an explicit unavailable state and hide the alert when no valid data exists. |
| Forecast moisture differed from Arduino readings | The forecast converted raw ADC again instead of using the calibrated Arduino percentage. | Use the provided percentage; reject invalid, nonfinite, boolean, or nonbinary digital values. |
| Stored names/messages could become HTML | Staff details, schedule names, and some administrative messages were interpolated directly into `innerHTML`. | Shared escaping utility and escaped dynamic values; constrain status classes to known states. |
| Private responses could survive sign-out in the offline cache | The service worker cached arbitrary same-origin GET responses. | Cache public static assets only, do not cache failed responses, and bump the cache version to clear old cached responses. |
| String `false` enabled watering | Python's `bool('false')` is true. | Require actual JSON booleans. Validate durations against `WATER_PUMP_MAX_DURATION_SECONDS`, default 300 seconds. |
| Timed pump operations overlapped or reported a failed stop as success | Concurrent requests had no run lock, and the timer lacked an interruption-safe stop. | Serialize timed operations, attempt stopping in `finally`, and propagate stop errors. Manual off remains available to approved users. |
| Daily schedules could behave like weekly schedules | The cron registration applied `days_of_week` even to daily schedules. | Apply weekday filters only to weekly schedules. |
| Sensor GET requests created fabricated cloud records | `/save_sensor` GET inserted fixed example measurements. | GET is read-only. POST validates timestamps, derives state from moisture, ignores duplicate zones, and requires a shared token for remote ingestion. |
| Preview values looked like live operational advice | Display fallbacks were simulated but the soil summary still recommended watering; an admin view checked the wrong source name. | Clearly label simulated/stale readings and avoid generating live low-moisture alerts from preview values. Hardware automation continues to use actual sensor reads. |
| Daily sensor history silently discarded older readings | Every append kept only the last 1,000 samples, which can be less than a full day. | Preserve earlier daily samples during atomic appends. Previously discarded samples cannot be reconstructed. |
| Notification delivery silently missed accounts or claimed success | Alerts read the old root-level account path; missing providers returned success; reports invented a fallback recipient and ignored delivery results. | Read canonical accounts, retain a legacy notification-history read fallback, exclude unapproved accounts and simulated samples, report delivery failure honestly, bound SMTP calls, and require explicit report recipients. Reset codes are no longer printed. |
| Welcome-email links used the wrong site | The dashboard URL was hardcoded to an older domain. | Use configurable `APP_BASE_URL`, defaulting to the site's current deployment URL. |
| Users could modify another user's notification | The mark-read helper wrote a supplied document ID without checking ownership or existence. | Check the existing document's owner and return 404 for inaccessible notifications. |
| Report/notification lists could need missing cloud indexes | Per-user queries combined filtering and ordering. | Filter by owner, then sort and limit the returned records, with bounded reads. |
| Invalid requests became internal errors | Broad exception handlers caught malformed JSON, field type errors, invalid limits, and upload-size failures. | Validate JSON object shape, textual fields, numeric bounds, and declared upload sizes before route execution. |
| `/training-results` failed | The route referenced a missing template; its API also replaced ISO timestamps with filenames. | Add a functional saved-detection history page and preserve actual record timestamps. This page does not claim to show training metrics. |
| Startup could select the wrong files | Uploads, results, model defaults, and pump settings depended on the working directory. | Anchor active application paths to the project directory. Keep the documented working directory for manual tools. |
| Deployment could destroy Pi accounts or continue after a failed copy | Accounts/credentials were copied automatically and native command exit codes were ignored. | Preserve accounts and credentials by default; add explicit opt-in flags, timestamped account backups, directory preparation, and checked SSH/SCP failures. Include all new runtime modules. |

## Cleanup

- Removed the unused language-selector JavaScript and CSS after the dropdowns
  were removed. Translation API compatibility endpoints remain available.
- Consolidated duplicate authorization checks, JSON writers, record readers,
  and model-loading branches. Removed unreachable reset code and duplicate imports.
- Removed the duplicate `opencv-contrib-python` requirement. The project uses
  standard `cv2` functionality, supplied by `opencv-python`, which is also the
  distribution required by Ultralytics. Installed environments were not changed.
- Reworked sensor-route tests to load actual functions without starting models,
  GPIO, cloud clients, or scheduled jobs. Added an optional development test
  dependency file rather than changing runtime environments.

## Validation

- Final automated run: **81 Python tests and 14 JavaScript tests passed**.
- Python regression suites cover authentication/approval, reset-code lifecycle,
  legacy hash migration, storage preservation, detection/cloud fallback, record
  ownership, media access, sensor exports, date filters, weather availability,
  video sampling, schedules, pump shutdown/overlap, and mocked message delivery.
- JavaScript tests cover single/batch/video transitions, HTML escaping,
  statistics errors, existing forecast and soil refresh behavior, and private
  response cache exclusion.
- Every active HTML template was rendered and its inline/local JavaScript was
  syntax checked together. Application, core, hardware-program, and manual-script
  Python sources were parsed; static API references were checked against routes.
- The deployment script was parsed, and its SSH/SCP wrappers were exercised with
  deliberately failing local commands. No Raspberry Pi deployment was performed.
- The updated local server was restarted with normal network access. Login,
  sign-up, policy pages, and static assets returned HTTP 200; unsigned requests
  to statistics, history, and pump status returned HTTP 401. A read-only check
  through the updated record loader confirmed all **20 cloud detections** remain
  accessible. The first cloud check timed out; a direct connection check and
  the subsequent actual-loader check succeeded. Hashes confirmed all **15
  pre-existing result-folder JSON files** remained unchanged across the restart;
  one of those files is sensor migration metadata rather than a detection.
- Tests use temporary files and mocked device/delivery clients. No notification
  messages were sent, production records rewritten, or model weights retrained.

## Operational notes and limits

- Legacy SHA-256 passwords upgrade on successful login. New passwords and resets
  use salted PBKDF2. There is no mass account migration or forced password reset.
- Existing unowned local detections are available to administrators; assigning
  them to staff would require verified ownership. Existing cloud-first behavior
  is preserved to avoid double-counting historical local/cloud copies with
  inconsistent old timestamps. Pending new local records are merged by record ID.
- The JSON stores and locks target the existing single-process Flask deployment.
  Multiple web workers require a transactional datastore or cross-process locks;
  atomic replacement alone does not serialize separate worker processes.
- Sensor alert delivery uses configured providers during normal operation.
  `REPORT_RECIPIENTS` must be explicitly configured for scheduled report delivery.
  SMTP/Twilio delivery was mocked, not tested against real recipients.
- Remote serial bridges must provide `SENSOR_INGEST_TOKEN`. Same-device loopback
  bridge requests continue to work without a token when none is configured.
- Timed watering defaults to a maximum of 300 seconds. Set
  `WATER_PUMP_MAX_DURATION_SECONDS` for an installation requiring a different
  maximum, and restart the app. Existing GPIO pin configuration was preserved.
- GPIO/relay operation, physical breaker behavior, calibration, real irrigation
  timing, Linux service installation, and Raspberry Pi deployment require checks
  on the actual hardware. Unit tests cannot verify wiring or device operation.
- Model labels were checked against the loaded local checkpoint. Recognition
  accuracy, validation heuristics, agricultural recommendations, and growth/risk
  estimates still require representative field validation. This audit does not
  establish model accuracy or retrain models.
- Deployment still updates an existing installation in place. It stops on a
  failed transfer but does not provide a transactional release/rollback system,
  install dependencies, or replace trained disease weights automatically.
- This is a source and regression audit, not a guarantee that all bugs or
  deployment-specific failures have been eliminated.
