@echo off
setlocal
chcp 65001 >nul
title Backup GitScout Data
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\backup_gitscout.ps1"
if errorlevel 1 pause
exit /b %ERRORLEVEL%
