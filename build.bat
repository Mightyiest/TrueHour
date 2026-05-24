@echo off
echo Building FocusLog...

pyinstaller --onefile --windowed --name FocusLog --icon=icon.ico --add-data "icon.ico;." app.py

if %ERRORLEVEL% equ 0 (
    echo Moving executable to root...
    move /y dist\FocusLog.exe .\FocusLog.exe
    echo Cleaning up...
    rmdir /s /q build
    rmdir /s /q dist
    del /f /q FocusLog.spec
    echo Build complete!
) else (
    echo Build failed.
)
pause