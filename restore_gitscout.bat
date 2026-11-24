@echo off
setlocal
chcp 65001 >nul
title Restore GitScout Data
if "%~1"=="" (
  echo Usage: restore_gitscout.bat gitscout-manual-YYYYMMDDTHHMMSSZ.db
  echo You can also queue a restore from System Settings in GitScout.
  pause
  exit /b 2
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\restore_gitscout.ps1" "%~1"
if errorlevel 1 pause
exit /b %ERRORLEVEL%
