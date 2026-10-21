@echo off
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Run setup.cmd first.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" "%~dp0launcher.py" start
if errorlevel 1 pause
