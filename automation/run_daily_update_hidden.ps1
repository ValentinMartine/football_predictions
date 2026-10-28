$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"

$automationDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoDir = Split-Path -Parent $automationDir
$logDir = Join-Path $automationDir "logs"
$logPath = Join-Path $logDir "task_wrapper.log"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Set-Location $repoDir

# Sous PowerShell 5.1, une ligne de stderr d'un exécutable redirigée par 2>&1 devient une erreur :
# avec Stop, elle arrêtait la tâche au premier message de git (du 06 au 27/10/2026).
$ErrorActionPreference = "Continue"
& python "automation\daily_update.py" >> $logPath 2>&1
exit $LASTEXITCODE
