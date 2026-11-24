@echo off
setlocal
chcp 65001 >nul
title Stop GitScout
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop_gitscout.ps1"
if errorlevel 1 pause
exit /b %ERRORLEVEL%
