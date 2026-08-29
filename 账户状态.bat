@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set "PYTHON_CMD="
python --version >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=python"
if not defined PYTHON_CMD py -3 --version >nul 2>nul
if not defined PYTHON_CMD if not errorlevel 1 set "PYTHON_CMD=py -3"

if not defined PYTHON_CMD (
  echo Python not found. Install Python 3 first.
  pause
  exit /b 1
)

%PYTHON_CMD% app\status_panel.py --accounts
pause
