@echo off
setlocal
chcp 65001 >nul
title GitScout Launcher
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_gitscout.ps1"
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" (
  echo.
  echo GitScout could not be started. Review the message and .runtime\logs.
  pause
)
exit /b %RESULT%
