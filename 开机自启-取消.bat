@echo off
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs
echo Removing startup task...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\uninstall_startup.ps1" > logs\startup-uninstall.log 2>&1
set "RC=%ERRORLEVEL%"
type logs\startup-uninstall.log
if not "%RC%"=="0" (
  echo.
  echo Startup uninstall failed. Read logs\startup-uninstall.log
  pause
  exit /b %RC%
)
echo.
echo Startup uninstall finished.
pause
