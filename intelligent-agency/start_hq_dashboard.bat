@echo off
setlocal
cd /d "%~dp0"
if not exist ".horizon" mkdir ".horizon"
echo Starting Polymath HQ President Console...
echo.
start "" http://127.0.0.1:8765
python dashboard.py
if errorlevel 1 (
  echo.
  echo Dashboard could not start. Make sure Python is installed and available as 'python'.
  pause
)
