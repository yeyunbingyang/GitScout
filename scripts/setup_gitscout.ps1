$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$VenvPython = Join-Path $Backend ".venv\Scripts\python.exe"

function Write-Step([string]$Message) { Write-Host ""; Write-Host "[GitScout] $Message" -ForegroundColor Cyan }
function Stop-WithMessage([string]$Message) {
    Write-Host ""
    Write-Host "[ERROR] $Message" -ForegroundColor Red
    exit 1
}

Write-Step "Checking Windows prerequisites..."
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    Stop-WithMessage "Python Launcher (py) not found. Install Python 3.11 from https://www.python.org/downloads/windows/ and enable the Python Launcher."
}
$pythonCheck = & py -3.11 --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Stop-WithMessage "Python 3.11 is required. Detected: $pythonCheck"
}
Write-Host "  $pythonCheck" -ForegroundColor Green

if (-not (Get-Command node -ErrorAction SilentlyContinue) -or -not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Stop-WithMessage "Node.js 20+ and npm are required. Install from https://nodejs.org/"
}
$nodeVersion = (& node -p "process.versions.node").Trim()
$nodeMajor = [int]($nodeVersion.Split(".")[0])
if ($nodeMajor -lt 20) {
    Stop-WithMessage "Node.js 20+ is required. Detected: $nodeVersion"
}
Write-Host "  Node.js $nodeVersion" -ForegroundColor Green

Write-Step "Preparing backend virtual environment..."
if (-not (Test-Path $VenvPython)) {
    & py -3.11 -m venv (Join-Path $Backend ".venv")
    if ($LASTEXITCODE -ne 0) { Stop-WithMessage "Unable to create the Python virtual environment." }
}
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { Stop-WithMessage "Unable to upgrade pip." }
& $VenvPython -m pip install -r (Join-Path $Backend "requirements.txt")
if ($LASTEXITCODE -ne 0) { Stop-WithMessage "Backend dependency installation failed." }

Write-Step "Installing frontend dependencies and building React..."
Push-Location $Frontend
try {
    & npm install --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { Stop-WithMessage "Frontend dependency installation failed." }
    & npm run build
    if ($LASTEXITCODE -ne 0) { Stop-WithMessage "Frontend production build failed." }
}
finally {
    Pop-Location
}

Write-Step "Preparing local data and runtime directories..."
@(
    (Join-Path $Root "data"),
    (Join-Path $Root "data\backups"),
    (Join-Path $Root ".runtime"),
    (Join-Path $Root ".runtime\logs")
) | ForEach-Object {
    New-Item -ItemType Directory -Path $_ -Force | Out-Null
}

$envFile = Join-Path $Root ".env"
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $Root ".env.example") $envFile
    Write-Host "  Created .env from .env.example. Add GITHUB_TOKEN only if needed." -ForegroundColor Yellow
}

Write-Step "Setup completed."
Write-Host "Run start_gitscout.bat to launch GitScout at http://127.0.0.1:8765" -ForegroundColor Green
