@echo off
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Run setup.cmd first. The Python environment is created even if screen validation fails.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" "%~dp0diagnose_screen.py"
pause
