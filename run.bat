@echo off
cd /d "%~dp0"
echo [TrueHour] Starting time tracker with console output...
python app.py
if %errorlevel% neq 0 (
    echo.
    echo [TrueHour] Application crashed with error code %errorlevel%.
    pause
)
