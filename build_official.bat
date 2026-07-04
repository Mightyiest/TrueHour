@echo off
for /f "delims=" %%A in ('python -c "import version; print(version.__version__)"') do set "VERSION=%%A"
echo Building TrueHours_%VERSION% (Official Release with Telemetry ON)...

:: Inject build-time configuration to enable telemetry
echo TELEMETRY_ENABLED = True > telemetry_config.py

:: Check if pyinstaller is available in PATH to avoid shell error printout
where pyinstaller >nul 2>nul
if %ERRORLEVEL% equ 0 (
    pyinstaller --onefile --windowed --name "TrueHours_%VERSION%" --icon=icon.ico --add-data "icon.ico;." --add-data "templates;templates" --exclude-module pytest --exclude-module unittest --exclude-module tkinter --exclude-module pydoc --exclude-module doctest --exclude-module test --exclude-module setuptools --exclude-module pip --exclude-module distutils app.py
) else (
    echo pyinstaller command not found in PATH. Using python -O -m PyInstaller fallback...
    python -O -m PyInstaller --onefile --windowed --name "TrueHours_%VERSION%" --icon=icon.ico --add-data "icon.ico;." --add-data "templates;templates" --exclude-module pytest --exclude-module unittest --exclude-module tkinter --exclude-module pydoc --exclude-module doctest --exclude-module test --exclude-module setuptools --exclude-module pip --exclude-module distutils app.py
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
