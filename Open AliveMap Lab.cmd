@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo AliveMap's Python environment is missing. Follow docs\run-poc.md first.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m laptop.lab
