@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Follow docs\map-system.md to create the laptop environment first.
    pause
    exit /b 1
)
if not exist ".local\mec-endpoint.json" (
    echo The private MEC endpoint configuration is missing. See docs\permanent-deployment.md.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m laptop.map_launcher --playground --remote
