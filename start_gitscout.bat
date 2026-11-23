@echo off
setlocal
chcp 65001 >nul
title GitScout Local Workspace

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "VENV=%BACKEND%\.venv"

echo.
echo  GitScout - Open Source Discovery & Research
echo  -------------------------------------------
echo.

if not exist "%ROOT%frontend\dist\index.html" (
    echo Frontend build not found.
    echo Run these commands once before first launch:
    echo   cd frontend
    echo   npm install
    echo   npm run build
    pause
    exit /b 1
)

if not exist "%VENV%\Scripts\python.exe" (
    echo [1/3] Creating Python virtual environment...
    py -3.11 -m venv "%VENV%"
    if errorlevel 1 (
        echo Python 3.11+ was not found. Install Python and retry.
        pause
        exit /b 1
    )
)

echo [2/3] Checking backend dependencies...
"%VENV%\Scripts\python.exe" -c "import fastapi, uvicorn, httpx, bs4, tzdata" >nul 2>nul
if errorlevel 1 (
    "%VENV%\Scripts\python.exe" -m pip install -r "%BACKEND%\requirements.txt"
    if errorlevel 1 (
        echo Dependency installation failed.
        pause
        exit /b 1
    )
)

if not exist "%ROOT%data" mkdir "%ROOT%data"
if not exist "%ROOT%.runtime\logs" mkdir "%ROOT%.runtime\logs"

echo [3/3] Starting local service at http://127.0.0.1:8765
echo Press Ctrl+C to stop GitScout.
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8765'"
cd /d "%BACKEND%"
"%VENV%\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8765 --workers 1
