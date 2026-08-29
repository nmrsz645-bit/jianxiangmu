@echo off
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs

set "LOG=logs\import-auth-console.log"
echo [%date% %time%] import auth started > "%LOG%"
echo BaseDir=%CD% >> "%LOG%"

powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\import_qianchuan_auth.ps1" -BaseDir "%CD%" >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"

type "%LOG%"
echo.
if not "%RC%"=="0" (
  echo Import auth failed. Log: %LOG%
) else (
  echo Import auth finished. Run status panel or start monitor.
)
pause
exit /b %RC%
