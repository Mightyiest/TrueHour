#!/bin/bash
# FocusLog macOS Launcher
cd "$(dirname "$0")"

echo "Launching FocusLog..."
if command -v python3 &>/dev/null; then
    python3 app.py
elif command -v python &>/dev/null; then
    python app.py
else
    echo "Error: Python is not installed or not in PATH."
    exit 1
fi
