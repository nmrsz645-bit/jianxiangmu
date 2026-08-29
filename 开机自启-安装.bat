@echo off
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs
echo Installing startup task...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_startup.ps1" > logs\startup-install.log 2>&1
set "RC=%ERRORLEVEL%"
type logs\startup-install.log
if not "%RC%"=="0" (
  echo.
  echo Startup install failed. Read logs\startup-install.log
  pause
  exit /b %RC%
)
echo.
echo Startup install finished.
pause
