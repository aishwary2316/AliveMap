@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo AliveMap's environment is missing. Follow docs\map-system.md first.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m laptop.map_launcher --playground
