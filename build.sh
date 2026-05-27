#!/bin/bash
# FocusLog macOS Standalone Packaging Script
cd "$(dirname "$0")"

echo "Building FocusLog Standalone App Bundle for macOS..."

# Detect standard python interpreter
PYTHON_CMD="python3"
if ! command -v python3 &>/dev/null; then
    if command -v python &>/dev/null; then
        PYTHON_CMD="python"
    else
        echo "Error: Python is not installed."
        exit 1
    fi
fi

# Ensure PyInstaller is installed
$PYTHON_CMD -m pip install pyinstaller PyQt6 pyobjc-framework-AppKit psutil Pillow

# Build command using PyInstaller
echo "Running PyInstaller..."
pyinstaller --noconsole --onefile --windowed --name="FocusLog" app.py

if [ $? -eq 0 ]; then
    echo "Moving executable bundle to root..."
    # On macOS, --windowed creates both a standalone binary in dist/FocusLog and FocusLog.app folder in dist/
    if [ -d "dist/FocusLog.app" ]; then
        rm -rf ./FocusLog.app
        mv "dist/FocusLog.app" ./FocusLog.app
        echo "Clean-up temporary folders..."
        rm -rf build dist FocusLog.spec
        echo "----------------------------------------"
        echo "Build Complete!"
        echo "Your macOS App Bundle is ready: ./FocusLog.app"
        echo "----------------------------------------"
    else
        echo "Error: App bundle FocusLog.app was not created."
        exit 1
    fi
else
    echo "Build failed."
    exit 1
fi
