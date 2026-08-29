@echo off
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\startup_status.ps1" > logs\startup-status.log 2>&1
type logs\startup-status.log
pause
