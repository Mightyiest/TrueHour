"""
FocusLog — Report generation and export utilities.
"""
import json
import os
import csv
from datetime import datetime, timedelta
from typing import TypedDict, List
from config import get_app_data_dir

def format_duration(total_seconds):
    """Format seconds into 'Xh XXm XXs' string."""
    total_seconds = int(total_seconds)
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{h}h {m:02d}m {s:02d}s"

def format_duration_hms(total_seconds):
    """Format seconds into 'HH:MM:SS' string."""
    total_seconds = int(total_seconds)
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

class AppUsage(TypedDict):
    name: str
    seconds: int
    formatted: str
    percent: float
    excluded: bool

class TimelineEntry(TypedDict):
    app: str
    start: str
    end: str

class ReportData(TypedDict):
    date: str
    date_display: str
    start: str
    start_display: str
    end: str
    end_display: str
    total_seconds: int
    total_formatted: str
    counted_seconds: int
    counted_formatted: str
    apps: List[AppUsage]
    timeline: List[TimelineEntry]
    is_recovered: bool
    session_name: str
    app_exe_paths: dict
    hourly_rate: float
    currency_symbol: str
    total_earned: float
    total_earned_display: str

def build_report_data(tracker, hourly_rate=0.0, currency_symbol="$") -> ReportData:
    """Build a structured dict from the tracker's session data."""
    session_start = tracker.session_start
    session_end = tracker.session_end or datetime.now()
    total_session = tracker.get_elapsed()
    counted = tracker.get_counted_seconds()
    apps = tracker.get_app_times_sorted()
    
    app_list = []
    for name, secs, included in apps:
        pct = (secs / total_session * 100) if total_session > 0 else 0
        app_list.append({
            "name": name,
            "seconds": int(secs),
            "formatted": format_duration(secs),
            "percent": round(pct, 1),
            "excluded": not included,
        })

    # Snapshot timeline under the lock to prevent concurrent modification
    with tracker._lock:
        timeline_snapshot = list(tracker.timeline)

    timeline = []
    for entry in timeline_snapshot:
        if entry["app"] == "[Idle]":
            continue
        timeline.append({
            "app": entry["app"],
            "start": entry["start"].strftime("%H:%M:%S"),
            "end": entry["end"].strftime("%H:%M:%S"),
        })

    earned = 0.0
    if hourly_rate > 0:
        earned = (counted / 3600) * hourly_rate

    return {
        "date": session_start.strftime("%Y-%m-%d"),
        "date_display": session_start.strftime("%B %d, %Y"),
        "start": session_start.strftime("%H:%M:%S"),
        "start_display": session_start.strftime("%I:%M %p"),
        "end": session_end.strftime("%H:%M:%S"),
        "end_display": session_end.strftime("%I:%M %p"),
        "total_seconds": int(total_session),
        "total_formatted": format_duration(total_session),
        "counted_seconds": int(counted),
        "counted_formatted": format_duration(counted),
        "apps": app_list,
        "timeline": timeline,
        "is_recovered": getattr(tracker, 'is_recovered', False),
        "session_name": getattr(tracker, 'session_name', ""),
        "app_exe_paths": getattr(tracker, 'app_exe_paths', {}),
        "hourly_rate": hourly_rate,
        "currency_symbol": currency_symbol,
        "total_earned": round(earned, 2),
        "total_earned_display": f"{currency_symbol}{earned:,.2f}" if hourly_rate > 0 else "",
    }

def export_txt(report, filepath):
    """Export the report as a .txt file."""
    lines = []
    lines.append("FOCUSLOG SESSION REPORT")
    lines.append(f"Date: {report['date']}")
    lines.append(f"Start: {report['start']} | End: {report['end']} | Duration: {report['total_formatted']}")
    lines.append(f"Counted Work Time: {report['counted_formatted']}")
    lines.append("")
    lines.append("APP USAGE BREAKDOWN")
    lines.append("-------------------")
    for app in report["apps"]:
        status = "[EXCLUDED]" if app["excluded"] else "[COUNTED]"
        lines.append(f"{app['name']:<30s} {app['formatted']:>12s}   {app['percent']:>5.1f}%   {status}")
    lines.append("")
    lines.append("TIMELINE LOG")
    lines.append("------------")
    for entry in report["timeline"]:
        t_start = entry['start'].strftime("%H:%M:%S") if hasattr(entry['start'], 'strftime') else entry['start']
        t_end = entry['end'].strftime("%H:%M:%S") if hasattr(entry['end'], 'strftime') else entry['end']
        lines.append(f"{t_start} -> {t_end}   {entry['app']}")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

def export_json(report, filepath):
    """Export the report as a .json file."""
    # Normalize timeline entries — may contain datetime objects from load_session_json
    normalized_timeline = []
    for t in report["timeline"]:
        normalized_timeline.append({
            "app": t["app"],
            "start": t["start"].strftime("%H:%M:%S") if hasattr(t["start"], "strftime") else t["start"],
            "end": t["end"].strftime("%H:%M:%S") if hasattr(t["end"], "strftime") else t["end"],
        })
    export = {
        "session_name": report.get("session_name", ""),
        "app_exe_paths": report.get("app_exe_paths", {}),
        "date": report["date"],
        "start": report["start"],
        "end": report["end"],
        "total_seconds": report["total_seconds"],
        "counted_seconds": report["counted_seconds"],
        "apps": [{"name": a["name"], "seconds": a["seconds"], "excluded": a["excluded"]} for a in report["apps"]],
        "timeline": normalized_timeline,
        "hourly_rate": report.get("hourly_rate", 0.0),
        "currency_symbol": report.get("currency_symbol", "$"),
        "total_earned": report.get("total_earned", 0.0),
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(export, f, indent=2, ensure_ascii=False)

def save_to_autosave(report):
    """Save session to autosave/ folder for crash recovery & system backup."""
    folder = os.path.join(get_app_data_dir(), "autosave")
    os.makedirs(folder, exist_ok=True)
    start_dt = datetime.strptime(report['date'] + " " + report['start'], "%Y-%m-%d %H:%M:%S")
    prefix = "recovery" if report.get("is_recovered") else "auto"
    filename = f"{prefix}_{start_dt.strftime('%Y-%m-%d_%H-%M-%S')}.json"
    filepath = os.path.join(folder, filename)
    export_json(report, filepath)
    return filepath

def save_to_history(report):
    """Save session to sessions/ folder (User Manual Save)."""
    folder = os.path.join(get_app_data_dir(), "sessions")
    os.makedirs(folder, exist_ok=True)
    start_dt = datetime.strptime(report['date'] + " " + report['start'], "%Y-%m-%d %H:%M:%S")
    filename = f"session_{start_dt.strftime('%Y-%m-%d_%H-%M-%S')}.json"
    filepath = os.path.join(folder, filename)
    export_json(report, filepath)
    return filepath

def load_session_json(filepath):
    """Load an exported JSON session back into the report format."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    start_dt = datetime.strptime(data['date'] + " " + data['start'], "%Y-%m-%d %H:%M:%S")
    end_dt = datetime.strptime(data['date'] + " " + data['end'], "%Y-%m-%d %H:%M:%S")
    
    # Midnight crossover guard for session bounds
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)
    
    apps = []
    for a in data['apps']:
        pct = (a['seconds'] / data['total_seconds'] * 100) if data['total_seconds'] > 0 else 0
        apps.append({
            "name": a['name'],
            "seconds": a['seconds'],
            "formatted": format_duration(a['seconds']),
            "percent": round(pct, 1),
            "excluded": a['excluded']
        })

    timeline = []
    for t in data['timeline']:
        t_start = datetime.strptime(data['date'] + " " + t['start'], "%Y-%m-%d %H:%M:%S")
        t_end = datetime.strptime(data['date'] + " " + t['end'], "%Y-%m-%d %H:%M:%S")
        
        # Midnight crossover guard
        if t_end <= t_start:
            t_end += timedelta(days=1)
            
        timeline.append({
            "app": t['app'],
            "start": t_start,
            "end": t_end
        })
    
    return {
        "session_name": data.get("session_name", ""),
        "app_exe_paths": data.get("app_exe_paths", {}),
        "date": data["date"],
        "date_display": start_dt.strftime("%B %d, %Y"),
        "start": data["start"],
        "start_display": start_dt.strftime("%I:%M %p"),
        "end": data["end"],
        "end_display": end_dt.strftime("%I:%M %p"),
        "total_seconds": data["total_seconds"],
        "total_formatted": format_duration(data["total_seconds"]),
        "counted_seconds": data["counted_seconds"],
        "counted_formatted": format_duration(data["counted_seconds"]),
        "apps": apps,
        "timeline": timeline,
        "hourly_rate": data.get("hourly_rate", 0.0),
        "currency_symbol": data.get("currency_symbol", "$"),
        "total_earned": data.get("total_earned", 0.0),
        "total_earned_display": f"{data.get('currency_symbol','$')}{data.get('total_earned',0.0):,.2f}" if data.get("hourly_rate", 0) > 0 else "",
    }

def export_csv(report, filepath):
    """Export a single session report as CSV."""
    try:
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Date', 'Session Name', 'App Name', 'Duration (seconds)', 
                            'Duration (formatted)', 'Percent of Session', 'Included in Count'])
            date_str = report['date']
            session_name = report.get('session_name', 'Unnamed')
            for app in report['apps']:
                writer.writerow([date_str, session_name, app['name'], app['seconds'],
                                app['formatted'], f"{app['percent']:.1f}%", "Yes" if not app['excluded'] else "No"])
            writer.writerow([])
            writer.writerow(['TOTAL COUNTED HOURS', '', '', report['counted_seconds'], report['counted_formatted'], '', ''])
            hourly_rate = report.get('hourly_rate', 0.0)
            if hourly_rate > 0:
                writer.writerow(['TOTAL EARNED', '', '', '', report['total_earned_display'], f"@ {report['currency_symbol']}{hourly_rate:.2f}/hr", ''])
        return True
    except Exception as e:
        print(f"CSV export error: {e}")
        return False

def export_csv_history(reports_list, filepath, hourly_rate=0.0, currency_symbol="$"):
    """Export multiple session reports as a single CSV file."""
    try:
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Date', 'Start Time', 'End Time', 'Session Name', 'App Name',
                            'Duration (seconds)', 'Duration (formatted)', 'Percent of Session', 'Included in Count'])
            total_counted_seconds = 0
            for report in sorted(reports_list, key=lambda r: r['date']):
                date_str = report['date']
                start_time = report['start']
                end_time = report['end']
                session_name = report.get('session_name', 'Unnamed')
                for app in report['apps']:
                    writer.writerow([date_str, start_time, end_time, session_name, app['name'],
                                    app['seconds'], app['formatted'], f"{app['percent']:.1f}%", "Yes" if not app['excluded'] else "No"])
                total_counted_seconds += report.get('counted_seconds', 0)

            writer.writerow([])
            h = total_counted_seconds // 3600
            m = (total_counted_seconds % 3600) // 60
            s = total_counted_seconds % 60
            total_formatted = f"{h}h {m:02d}m {s:02d}s"
            writer.writerow(['TOTAL COUNTED HOURS', '', '', '', '', total_counted_seconds, total_formatted, '', ''])
            if hourly_rate > 0:
                total_earned = (total_counted_seconds / 3600) * hourly_rate
                total_earned_display = f"{currency_symbol}{total_earned:,.2f}"
                writer.writerow(['TOTAL EARNED', '', '', '', '', '', total_earned_display, f"@ {currency_symbol}{hourly_rate:.2f}/hr", ''])
        return True
    except Exception as e:
        print(f"CSV export error: {e}")
        return False
