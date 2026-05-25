@echo off
echo Building FocusLog...

<<<<<<< Updated upstream
pyinstaller --onefile --windowed --name FocusLog --icon=icon.ico --add-data "icon.ico;." app.py
=======
<<<<<<< Updated upstream
"%APPDATA%\Python\Python314\Scripts\pyinstaller.exe" --onefile --windowed --name FocusLog --icon=icon.ico --add-data "icon.ico;." app.py
=======
python -m PyInstaller --onefile --windowed --name FocusLog --icon=icon.ico --add-data "icon.ico;." app.py
>>>>>>> Stashed changes
>>>>>>> Stashed changes

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