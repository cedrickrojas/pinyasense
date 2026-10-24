# Deploys code changes from this Windows folder to the Raspberry Pi, then restarts the service.
# Usage: run this from PowerShell inside the pinyasense folder:
#   .\deploy_to_pi.ps1

param(
    [switch]$IncludeAccounts,
    [switch]$IncludeFirebaseKey
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$PiHost = "voicebrain@voicebrain.local"
$PiPath = "~/agripinya"
$PublicUrl = "https://xn--piasense-e3a.tech/"

$ScpCommand = (Get-Command scp -CommandType Application -ErrorAction Stop).Source
$SshCommand = (Get-Command ssh -CommandType Application -ErrorAction Stop).Source

function scp {
    & $ScpCommand @args
    if ($LASTEXITCODE -ne 0) { throw "SCP failed (exit $LASTEXITCODE). Deployment stopped before restart." }
}

function ssh {
    & $SshCommand @args
    if ($LASTEXITCODE -ne 0) { throw "SSH failed (exit $LASTEXITCODE). Deployment stopped." }
}

ssh $PiHost "mkdir -p ${PiPath}/core ${PiPath}/templates ${PiPath}/static/js ${PiPath}/static/css ${PiPath}/static/icons ${PiPath}/scripts ${PiPath}/data"

Write-Host "Copying app.py..." -ForegroundColor Cyan
scp app.py "${PiHost}:${PiPath}/app.py"

Write-Host "Copying general scene validation model..." -ForegroundColor Cyan
scp yolov8n.pt "${PiHost}:${PiPath}/yolov8n.pt"

Write-Host "Copying core/sensor_monitor.py..." -ForegroundColor Cyan
scp core\sensor_monitor.py "${PiHost}:${PiPath}/core/sensor_monitor.py"

Write-Host "Copying core/auth.py..." -ForegroundColor Cyan
scp core\auth.py "${PiHost}:${PiPath}/core/auth.py"

Write-Host "Copying core/disease_detector.py..." -ForegroundColor Cyan
scp core\disease_detector.py "${PiHost}:${PiPath}/core/disease_detector.py"

Write-Host "Copying forecast modules (time_series_forecaster.py, plant_monitoring.py)..." -ForegroundColor Cyan
scp core\time_series_forecaster.py core\plant_monitoring.py "${PiHost}:${PiPath}/core/"

Write-Host "Copying shared runtime dependencies..." -ForegroundColor Cyan
scp core\__init__.py core\soil_preview.py core\email_service.py core\notification_service.py core\detection_records.py core\json_storage.py core\pump_remote.py "${PiHost}:${PiPath}/core/"

Write-Host "Copying templates..." -ForegroundColor Cyan
scp templates\*.html "${PiHost}:${PiPath}/templates/"

if ($IncludeAccounts) {
    if (-not (Test-Path -LiteralPath 'data/users.json')) { throw 'Local data/users.json was not found.' }
    $AccountBackup = "users.json.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss-fff')"
    Write-Host "Backing up and copying user accounts..." -ForegroundColor Yellow
    ssh $PiHost "if [ -f ${PiPath}/data/users.json ]; then cp ${PiPath}/data/users.json ${PiPath}/data/${AccountBackup}; fi"
    scp data\users.json "${PiHost}:${PiPath}/data/users.json"
}

Write-Host "Copying static/js..." -ForegroundColor Cyan
scp static\js\*.js "${PiHost}:${PiPath}/static/js/"

Write-Host "Copying static/css..." -ForegroundColor Cyan
scp static\css\*.css "${PiHost}:${PiPath}/static/css/"

Write-Host "Copying PWA assets..." -ForegroundColor Cyan
scp static\manifest.webmanifest static\sw.js "${PiHost}:${PiPath}/static/"
ssh $PiHost "mkdir -p ${PiPath}/static/icons"
scp static\icons\*.svg "${PiHost}:${PiPath}/static/icons/"

Write-Host "Copying serial bridge and requirements..." -ForegroundColor Cyan
scp requirements.txt "${PiHost}:${PiPath}/requirements.txt"
ssh $PiHost "mkdir -p ${PiPath}/scripts"
scp scripts\arduino_serial_bridge.py "${PiHost}:${PiPath}/scripts/arduino_serial_bridge.py"

if ($IncludeFirebaseKey) {
    if (-not (Test-Path -LiteralPath 'serviceAccountKey.json')) { throw 'Local serviceAccountKey.json was not found.' }
	Write-Host "Copying Firebase service account key..." -ForegroundColor Yellow
	scp serviceAccountKey.json "${PiHost}:${PiPath}/serviceAccountKey.json"
}

Write-Host "Restarting the service on the Pi..." -ForegroundColor Cyan
ssh $PiHost "sudo systemctl restart agripinya && sleep 3 && systemctl is-active agripinya"

Write-Host "Done. App should be live at $PublicUrl" -ForegroundColor Green
try {
	$healthResponse = Invoke-WebRequest -Uri $PublicUrl -Method Head -UseBasicParsing -TimeoutSec 15
	Write-Host "Public site check: HTTP $($healthResponse.StatusCode)" -ForegroundColor Green
} catch {
	Write-Warning "The Pi restarted, but the public HTTPS check failed: $($_.Exception.Message)"
}
