@echo off
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs

echo Starting project monitor watchdog...
echo BaseDir=%CD%
echo Logs:
echo   logs\watchdog.log
echo   logs\watchdog-console.log
echo   logs\watchdog-error.log
echo.

set "PYTHON_CMD="
python --version >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=python"
if not defined PYTHON_CMD py -3 --version >nul 2>nul
if not defined PYTHON_CMD if not errorlevel 1 set "PYTHON_CMD=py -3"

if not defined PYTHON_CMD (
  echo Python not found. Install Python 3 first.
  echo [%date% %time%] Python not found. > logs\start-monitor-console.log
  pause
  exit /b 1
)

echo Using %PYTHON_CMD%
echo [%date% %time%] start monitor requested > logs\start-monitor-console.log
echo BaseDir=%CD% >> logs\start-monitor-console.log
echo Using %PYTHON_CMD% >> logs\start-monitor-console.log

start "ProjectMonitorWatchdog" /min "%ComSpec%" /c call "%CD%\scripts\watchdog.bat"
echo Started. Open status panel after about 1 minute to check the first scan.
echo If it fails, read logs\watchdog-error.log.
pause
exit /b 0
