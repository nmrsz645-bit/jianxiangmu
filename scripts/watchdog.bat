@echo off
setlocal
cd /d "%~dp0\.."
if not exist logs mkdir logs

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0watchdog_mutex.ps1"
exit /b %ERRORLEVEL%
