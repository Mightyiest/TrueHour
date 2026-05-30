@echo off
echo Building TrueHours...

:: Try running pyinstaller directly first, fallback to python -m PyInstaller
pyinstaller --onefile --windowed --name TrueHours --icon=icon.ico --add-data "icon.ico;." app.py
if %ERRORLEVEL% neq 0 (
    echo Direct pyinstaller command failed. Trying python -m PyInstaller fallback...
    python -m PyInstaller --onefile --windowed --name TrueHours --icon=icon.ico --add-data "icon.ico;." app.py
)

if %ERRORLEVEL% equ 0 (
    echo Moving executable to root...
    move /y dist\TrueHours.exe .\TrueHours.exe
    echo Cleaning up...
    rmdir /s /q build
    rmdir /s /q dist
    del /f /q TrueHours.spec
    echo Build complete!
) else (
    echo Build failed.
)
pause