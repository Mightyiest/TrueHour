@echo off
for /f "delims=" %%A in ('python -c "import version; print(version.__version__)"') do set "VERSION=%%A"
echo Building TrueHours_%VERSION% (Telemetry OFF)...

:: Inject build-time configuration to disable telemetry
echo TELEMETRY_ENABLED = False > telemetry_config.py

:: Try running pyinstaller directly first, fallback to python -m PyInstaller
pyinstaller --onefile --windowed --name "TrueHours_%VERSION%" --icon=icon.ico --add-data "icon.ico;." app.py
if %ERRORLEVEL% neq 0 (
    echo Direct pyinstaller command failed. Trying python -m PyInstaller fallback...
    python -m PyInstaller --onefile --windowed --name "TrueHours_%VERSION%" --icon=icon.ico --add-data "icon.ico;." app.py
)

if %ERRORLEVEL% equ 0 (
    echo Moving executable to root...
    move /y "dist\TrueHours_%VERSION%.exe" ".\TrueHours_%VERSION%.exe"
    echo Cleaning up...
    rmdir /s /q build
    rmdir /s /q dist
    del /f /q "TrueHours_%VERSION%.spec"
    del /f /q telemetry_config.py
    echo Build complete!
) else (
    echo Cleaning up...
    del /f /q telemetry_config.py
    echo Build failed.
)
pause