# Deploys code changes from this Windows folder to the Raspberry Pi, then restarts the service.
# Usage: run this from PowerShell inside the pinyasense folder:
#   .\deploy_to_pi.ps1

$PiHost = "voicebrain@voicebrain.local"
$PiPath = "~/agripinya"

Write-Host "Copying app.py..." -ForegroundColor Cyan
scp app.py "${PiHost}:${PiPath}/app.py"

Write-Host "Copying core/sensor_monitor.py..." -ForegroundColor Cyan
scp core\sensor_monitor.py "${PiHost}:${PiPath}/core/sensor_monitor.py"

Write-Host "Copying templates..." -ForegroundColor Cyan
scp templates\*.html "${PiHost}:${PiPath}/templates/"

Write-Host "Copying static/js..." -ForegroundColor Cyan
scp static\js\*.js "${PiHost}:${PiPath}/static/js/"

Write-Host "Copying static/css..." -ForegroundColor Cyan
scp static\css\*.css "${PiHost}:${PiPath}/static/css/"

Write-Host "Restarting the service on the Pi..." -ForegroundColor Cyan
ssh $PiHost "sudo systemctl restart agripinya && sleep 3 && systemctl is-active agripinya"

Write-Host "Done. App should be live at http://voicebrain.local:5001" -ForegroundColor Green
