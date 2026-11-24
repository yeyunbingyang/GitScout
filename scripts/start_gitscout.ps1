$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$VenvPython = Join-Path $Backend ".venv\Scripts\python.exe"
$Runtime = Join-Path $Root ".runtime"
$Logs = Join-Path $Runtime "logs"
$PidFile = Join-Path $Runtime "gitscout.pid"
$Port = 8765
$HealthUrl = "http://127.0.0.1:$Port/api/v1/health"
$HomeUrl = "http://127.0.0.1:$Port"

function Test-GitScoutHealth {
    try {
        $response = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 2
        return $response.status -eq "ok" -and $response.service -eq "gitscout-api"
    }
    catch { return $false }
}

function Test-PortOpen {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $client.Connect("127.0.0.1", $Port)
        return $true
    }
    catch { return $false }
    finally { $client.Dispose() }
}

function Show-LogTail([string]$Path) {
    if (Test-Path $Path) {
        Write-Host ""
        Write-Host "Last log lines from $Path" -ForegroundColor Yellow
        Get-Content $Path -Tail 35
    }
}

Write-Host ""
Write-Host "GitScout local workspace" -ForegroundColor Cyan
Write-Host "-------------------------" -ForegroundColor DarkGray

if (Test-PortOpen) {
    if (Test-GitScoutHealth) {
        Write-Host "GitScout is already running. Opening the local workspace..." -ForegroundColor Green
        Start-Process $HomeUrl
        exit 0
    }
    Write-Host "Port $Port is already in use by another process. GitScout will not terminate it." -ForegroundColor Red
    exit 1
}

$frontendBuild = Join-Path $Root "frontend\dist\index.html"
$envFile = Join-Path $Root ".env"
$dependenciesReady = $false
if (Test-Path $VenvPython) {
    & $VenvPython -c "import fastapi, uvicorn, httpx, bs4, tzdata" 2>$null
    $dependenciesReady = $LASTEXITCODE -eq 0
}

if (-not $dependenciesReady -or -not (Test-Path $frontendBuild) -or -not (Test-Path $envFile)) {
    Write-Host "First-run setup or build is required..." -ForegroundColor Yellow
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "setup_gitscout.ps1")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

New-Item -ItemType Directory -Path $Logs -Force | Out-Null
$stdout = Join-Path $Logs "gitscout.log"
$stderr = Join-Path $Logs "gitscout-error.log"
$limit = 20MB
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
foreach ($logPath in @($stdout, $stderr)) {
    if ((Test-Path $logPath) -and (Get-Item $logPath).Length -gt $limit) {
        Move-Item $logPath ($logPath + "." + $stamp) -Force
    }
}
Get-ChildItem $Logs -Filter "gitscout*.log.*" -File | Sort-Object LastWriteTime -Descending | Select-Object -Skip 10 | Remove-Item -Force -ErrorAction SilentlyContinue

$env:PYTHONUTF8 = "1"
Write-Host "Starting FastAPI on 127.0.0.1:$Port..." -ForegroundColor Cyan
$process = Start-Process -FilePath $VenvPython -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port", "--workers", "1") -WorkingDirectory $Backend -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
Set-Content -Path $PidFile -Value $process.Id -Encoding ascii

$ready = $false
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    Start-Sleep -Seconds 1
    if (Test-GitScoutHealth) {
        $ready = $true
        break
    }
    if (-not (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) { break }
}

if (-not $ready) {
    if (Get-Process -Id $process.Id -ErrorAction SilentlyContinue) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    Write-Host "GitScout did not become healthy. Check the logs below." -ForegroundColor Red
    Show-LogTail $stderr
    Show-LogTail $stdout
    exit 1
}

Write-Host "GitScout is ready." -ForegroundColor Green
Write-Host "Workspace: $HomeUrl" -ForegroundColor Green
Write-Host "Logs: $Logs" -ForegroundColor DarkGray
Start-Process $HomeUrl
