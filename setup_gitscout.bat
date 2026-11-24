@echo off
setlocal
chcp 65001 >nul
title GitScout First-run Setup
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup_gitscout.ps1"
if errorlevel 1 (
  echo.
  echo Setup failed. Review the error above.
  pause
)
exit /b %ERRORLEVEL%
