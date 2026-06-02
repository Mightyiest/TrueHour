@echo off
echo Building TrueHours-beta (Telemetry OFF)...

:: Inject build-time configuration to disable telemetry
echo TELEMETRY_ENABLED = False > telemetry_config.py

:: Try running pyinstaller directly first, fallback to python -m PyInstaller
pyinstaller --onefile --windowed --name TrueHours-beta --icon=icon.ico --add-data "icon.ico;." app.py
if %ERRORLEVEL% neq 0 (
    echo Direct pyinstaller command failed. Trying python -m PyInstaller fallback...
    python -m PyInstaller --onefile --windowed --name TrueHours-beta --icon=icon.ico --add-data "icon.ico;." app.py
)

if %ERRORLEVEL% equ 0 (
    echo Moving executable to root...
    move /y dist\TrueHours-beta.exe .\TrueHours-beta.exe
    echo Cleaning up...
    rmdir /s /q build
    rmdir /s /q dist
    del /f /q TrueHours-beta.spec
    del /f /q telemetry_config.py
    echo Build complete!
) else (
    echo Cleaning up...
    del /f /q telemetry_config.py
    echo Build failed.
)
pause