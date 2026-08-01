#!/bin/bash
# TrueHours macOS Standalone Packaging Script
cd "$(dirname "$0")"

echo "Building TrueHours Standalone App Bundle for macOS..."

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
$PYTHON_CMD -O -m PyInstaller --noconsole --onefile --windowed --name="TrueHours" --add-data "templates:templates" --exclude-module pytest --exclude-module unittest --exclude-module tkinter --exclude-module pydoc --exclude-module doctest --exclude-module test --exclude-module setuptools --exclude-module pip --exclude-module distutils app.py

if [ $? -eq 0 ]; then
    echo "Moving executable bundle to root..."
    # On macOS, --windowed creates both a standalone binary in dist/TrueHours and TrueHours.app folder in dist/
    if [ -d "dist/TrueHours.app" ]; then
        rm -rf ./TrueHours.app
        mv "dist/TrueHours.app" ./TrueHours.app
        echo "Clean-up temporary folders..."
        rm -rf build dist TrueHours.spec
        echo "----------------------------------------"
        echo "Build Complete!"
        echo "Your macOS App Bundle is ready: ./TrueHours.app"
        echo "----------------------------------------"
    else
        echo "Error: App bundle TrueHours.app was not created."
        exit 1
    fi
else
    echo "Build failed."
    exit 1
fi
