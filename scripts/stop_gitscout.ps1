$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Runtime = Join-Path $Root ".runtime"
$PidFile = Join-Path $Runtime "gitscout.pid"

if (-not (Test-Path $PidFile)) {
    Write-Host "GitScout PID file not found. The service may already be stopped." -ForegroundColor Yellow
    exit 0
}

$rawPid = (Get-Content $PidFile -Raw).Trim()
$processId = 0
if (-not [int]::TryParse($rawPid, [ref]$processId)) {
    Remove-Item $PidFile -Force
    Write-Host "Removed an invalid stale PID file." -ForegroundColor Yellow
    exit 0
}

$process = Get-Process -Id $processId -ErrorAction SilentlyContinue
if (-not $process) {
    Remove-Item $PidFile -Force
    Write-Host "GitScout is already stopped. Removed stale PID file." -ForegroundColor Yellow
    exit 0
}

$details = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
if (-not $details -or $details.CommandLine -notmatch "app\.main:app" -or $details.CommandLine -notmatch "127\.0\.0\.1") {
    Write-Host "PID $processId does not look like the GitScout API process. Refusing to stop an unrelated process." -ForegroundColor Red
    exit 1
}

Stop-Process -Id $processId -Force
Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
Write-Host "GitScout has been stopped." -ForegroundColor Green
