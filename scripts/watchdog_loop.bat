@echo off
setlocal
cd /d "%~dp0\.."
if not exist logs mkdir logs

echo Project monitor watchdog is running.
echo BaseDir=%CD%
echo Logs:
echo   logs\watchdog.log
echo   logs\watchdog-console.log
echo   logs\watchdog-error.log
echo.

set "PYTHON_CMD="
python --version >> logs\watchdog.log 2>&1
if not errorlevel 1 set "PYTHON_CMD=python"
if not defined PYTHON_CMD py -3 --version >> logs\watchdog.log 2>&1
if not defined PYTHON_CMD if not errorlevel 1 set "PYTHON_CMD=py -3"

if not defined PYTHON_CMD (
  echo [%date% %time%] Python not found. Install Python 3 first. >> logs\watchdog-error.log
  type logs\watchdog-error.log
  pause
  exit /b 1
)

echo Using %PYTHON_CMD%
echo First scan may take about 1 minute. Keep this window open, or use start-monitor.bat.
echo.

:loop
echo [%date% %time%] worker starting with %PYTHON_CMD% >> logs\watchdog.log
%PYTHON_CMD% app\project_monitor.py >> logs\watchdog-console.log 2>> logs\watchdog-error.log
echo [%date% %time%] worker exited, restart after 30 seconds >> logs\watchdog.log
echo Worker exited. Restarting after 30 seconds...
timeout /t 30 /nobreak >nul
goto loop
