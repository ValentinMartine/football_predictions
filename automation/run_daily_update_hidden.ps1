$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"

$automationDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoDir = Split-Path -Parent $automationDir
$logDir = Join-Path $automationDir "logs"
$logPath = Join-Path $logDir "task_wrapper.log"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Set-Location $repoDir

& python "automation\daily_update.py" >> $logPath 2>&1
exit $LASTEXITCODE
