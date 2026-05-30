import os
import sys
from datetime import datetime, timedelta

# Adjust path so we can import from local files
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from report import generate_session_report_html

# Setup common Windows paths for testing local icon extraction
windir = os.environ.get("WINDIR", "C:\\Windows")
explorer_path = os.path.join(windir, "explorer.exe")
cmd_path = os.path.join(windir, "System32", "cmd.exe")
notepad_path = os.path.join(windir, "System32", "notepad.exe")
taskmgr_path = os.path.join(windir, "System32", "taskmgr.exe")

# Verify which paths exist, fallback to sys.executable (Python itself) if they don't
def get_existing_path(path):
    return path if os.path.exists(path) else sys.executable

# Mock report data matching report.py structure
mock_report = {
    "session_name": "Sprint 4 Deep Work & UI Design",
    "date": "May 27, 2026",
    "date_display": "May 27, 2026",
    "start": "09:15 AM",
    "start_display": "09:15 AM",
    "end": "05:45 PM",
    "end_display": "05:45 PM",
    "total_seconds": 30600,  # 8h 30m
    "counted_seconds": 24312, # 6h 45m 12s
    "total_formatted": "8h 30m 00s",
    "counted_formatted": "6h 45m 12s",
    
    # Project & Category Breakdown
    "project_breakdown": [
        {"project": "Development", "formatted": "4h 15m 00s", "percent": 62.9, "color": "#4F46E5"},
        {"project": "Design", "formatted": "1h 45m 12s", "percent": 25.9, "color": "#EC4899"},
        {"project": "Documentation", "formatted": "0h 45m 00s", "percent": 11.2, "color": "#F59E0B"}
    ],
    
    # App usage list
    "apps": [
        {"name": "VS Code", "tag": "Development", "formatted": "4h 15m 00s", "percent": 50.0},
        {"name": "Command Prompt", "tag": "Development", "formatted": "1h 30m 00s", "percent": 20.0},
        {"name": "Notepad", "tag": "Documentation", "formatted": "0h 45m 00s", "percent": 8.8},
        {"name": "File Explorer", "tag": "Unassigned", "formatted": "1h 44m 48s", "percent": 21.2}
    ],
    
    # Map app names to local executable paths for icon extraction
    "app_exe_paths": {
        "VS Code": get_existing_path(taskmgr_path),  # Using Task Manager as a stand-in for VS Code icon
        "Command Prompt": get_existing_path(cmd_path),
        "Notepad": get_existing_path(notepad_path),
        "File Explorer": get_existing_path(explorer_path)
    },
    
    # Timeline logs
    "timeline": [
        {
            "start": datetime.now() - timedelta(hours=8),
            "end": datetime.now() - timedelta(hours=4),
            "app": "VS Code"
        },
        {
            "start": datetime.now() - timedelta(hours=4),
            "end": datetime.now() - timedelta(hours=2),
            "app": "Command Prompt"
        },
        {
            "start": datetime.now() - timedelta(hours=2),
            "end": datetime.now() - timedelta(hours=1),
            "app": "Notepad"
        },
        {
            "start": datetime.now() - timedelta(hours=1),
            "end": datetime.now(),
            "app": "File Explorer"
        }
    ]
}

print("Compiling report HTML using generate_session_report_html function...")
try:
    html_output = generate_session_report_html(mock_report, hourly_rate=45.0, currency_symbol="$")
    
    output_path = "sample_report.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_output)
        
    print(f"Success! Sample report generated successfully as '{output_path}'.")
    print("Open this file in your browser to verify the app icons render next to names!")
except Exception as e:
    import traceback
    print("Error compiling report template:")
    traceback.print_exc()
    sys.exit(1)
