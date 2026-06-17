@echo off
for /f "delims=" %%A in ('python -c "import version; print(version.__version__)"') do set "VERSION=%%A"
for /f "delims=" %%B in ('python -c "import version; print(version.INFO.build_number)"') do set "BUILD_NUM=%%B"
set "BUILD_NAME=TrueHours_%VERSION%-beta.1_build%BUILD_NUM%"
echo Building %BUILD_NAME% (Telemetry OFF)...

:: Inject build-time configuration to disable telemetry
echo TELEMETRY_ENABLED = False > telemetry_config.py

:: Try running pyinstaller directly first, fallback to python -m PyInstaller
pyinstaller --onefile --windowed --name "%BUILD_NAME%" --icon=icon.ico --add-data "icon.ico;." --add-data "templates;templates" app.py
if %ERRORLEVEL% neq 0 (
    echo Direct pyinstaller command failed. Trying python -m PyInstaller fallback...
    python -m PyInstaller --onefile --windowed --name "%BUILD_NAME%" --icon=icon.ico --add-data "icon.ico;." --add-data "templates;templates" app.py
)

if %ERRORLEVEL% equ 0 (
    echo Moving executable to root...
    move /y "dist\%BUILD_NAME%.exe" ".\%BUILD_NAME%.exe"
    echo Cleaning up...
    rmdir /s /q build
    rmdir /s /q dist
    del /f /q "%BUILD_NAME%.spec"
    del /f /q telemetry_config.py
    echo Build complete!
) else (
    echo Cleaning up...
    del /f /q telemetry_config.py
    echo Build failed.
)
pause