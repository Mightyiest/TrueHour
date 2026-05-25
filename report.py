<<<<<<< Updated upstream
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
    tag: str

class ProjectBreakdownEntry(TypedDict):
    project: str
    seconds: int
    formatted: str
    percent: float
    earned: float
    earned_display: str
    color: str

PROJECT_COLORS = {
    "Development": "#4F46E5",  # Indigo
    "Design": "#EC4899",       # Pink
    "Research": "#10B981",     # Emerald
    "Documentation": "#F59E0B",# Amber
    "Communication": "#06B6D4",# Cyan
    "Management": "#8B5CF6",   # Purple
    "Unassigned": "#64748B",   # Slate
}

def get_project_color(project_name: str) -> str:
    return PROJECT_COLORS.get(project_name, "#64748B")

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
    project_breakdown: List[ProjectBreakdownEntry]

def build_report_data(tracker, hourly_rate=0.0, currency_symbol="$") -> ReportData:
    """Build a structured dict from the tracker's session data."""
    session_start = tracker.session_start
    session_end = tracker.session_end or datetime.now()
    total_session = tracker.get_elapsed()
    counted = tracker.get_counted_seconds()
    apps = tracker.get_app_times_sorted()
    
    app_list = []
    project_times = {}
    for name, secs, included in apps:
        tag = tracker.get_app_tag(name)
        pct = (secs / total_session * 100) if total_session > 0 else 0
        app_list.append({
            "name": name,
            "seconds": int(secs),
            "formatted": format_duration(secs),
            "percent": round(pct, 1),
            "excluded": not included,
            "tag": tag,
        })
        if included:
            project_times[tag] = project_times.get(tag, 0) + secs

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

    total_counted = sum(project_times.values())
    breakdown = []
    for proj, secs in project_times.items():
        proj_pct = (secs / total_counted * 100) if total_counted > 0 else 0
        proj_earned = (secs / 3600) * hourly_rate
        breakdown.append({
            "project": proj,
            "seconds": int(secs),
            "formatted": format_duration(secs),
            "percent": round(proj_pct, 1),
            "earned": round(proj_earned, 2),
            "earned_display": f"{currency_symbol}{proj_earned:,.2f}",
            "color": get_project_color(proj)
        })
    breakdown.sort(key=lambda x: x["seconds"], reverse=True)

    # ── New Activity: diff against resume snapshot ─────────────────────────
    # Only populated when the session was loaded from a saved file via Session Manager.
    resume_snapshot = getattr(tracker, 'resume_snapshot', None)
    is_resumed = resume_snapshot is not None
    new_activity = []
    if is_resumed:
        # Collect all app names across both snapshot and current app_times
        all_app_names = set(resume_snapshot.keys()) | set(tracker.app_times.keys())
        # Sort by new seconds descending, then name
        for name, secs, included in apps:
            prev_secs = resume_snapshot.get(name, 0)
            new_secs = max(0.0, secs - prev_secs)
            if new_secs > 0 or prev_secs > 0:
                tag = tracker.get_app_tag(name)
                new_activity.append({
                    "name": name,
                    "previous_seconds": int(prev_secs),
                    "previous_formatted": format_duration(prev_secs),
                    "new_seconds": int(new_secs),
                    "new_formatted": format_duration(new_secs) if new_secs > 0 else "—",
                    "total_seconds": int(secs),
                    "total_formatted": format_duration(secs),
                    "excluded": not included,
                    "tag": tag,
                })
        # Only keep the list if at least one app has new time
        if not any(a["new_seconds"] > 0 for a in new_activity):
            new_activity = []

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
        "is_resumed": is_resumed,
        "new_activity": new_activity,
        "session_name": getattr(tracker, 'session_name', ""),
        "app_exe_paths": getattr(tracker, 'app_exe_paths', {}),
        "hourly_rate": hourly_rate,
        "currency_symbol": currency_symbol,
        "total_earned": round(earned, 2),
        "total_earned_display": f"{currency_symbol}{earned:,.2f}",
        "project_breakdown": breakdown,
    }

def export_txt(report, filepath):
    """Export the report as a .txt file."""
    lines = []
    lines.append("FOCUSLOG SESSION REPORT")
    if report.get("is_resumed"):
        lines.append("[RESUMED SESSION]")
    lines.append(f"Date: {report['date']}")
    lines.append(f"Start: {report['start']} | End: {report['end']} | Duration: {report['total_formatted']}")
    lines.append(f"Counted Work Time: {report['counted_formatted']}")
    hourly_rate = report.get("hourly_rate", 0.0)
    currency_symbol = report.get("currency_symbol", "$")
    lines.append(f"Hourly Rate: {currency_symbol}{hourly_rate:.2f}/hr")
    lines.append(f"Total Earned: {report.get('total_earned_display') or (currency_symbol + '0.00')}")
    lines.append("")
    # New activity section (only for resumed sessions with new time)
    new_activity = [a for a in report.get("new_activity", []) if not a["excluded"]]
    if new_activity:
        lines.append("NEW ACTIVITY (THIS RESUME)")
        lines.append("--------------------------")
        lines.append(f"{'App':<30s} {'Previous':>12s} {'New Added':>12s} {'Total':>12s}")
        for a in new_activity:
            new_str = a["new_formatted"] if a["new_seconds"] > 0 else "—"
            lines.append(f"{a['name']:<30s} {a['previous_formatted']:>12s} {new_str:>12s} {a['total_formatted']:>12s}")
        lines.append("")
    lines.append("APP USAGE BREAKDOWN")
    lines.append("-------------------")
    for app in report["apps"]:
        if app["excluded"]:
            continue
        lines.append(f"{app['name']:<30s} {app['formatted']:>12s}   {app['percent']:>5.1f}%")
    lines.append("")
    lines.append("TIMELINE LOG")
    lines.append("------------")
    for entry in report["timeline"]:
        t_start = entry['start'].strftime("%H:%M:%S") if hasattr(entry['start'], 'strftime') else entry['start']
        t_end = entry['end'].strftime("%H:%M:%S") if hasattr(entry['end'], 'strftime') else entry['end']
        lines.append(f"{t_start} -> {t_end}   {entry['app']}")
    lines.append("")
    lines.append("PROJECT BREAKDOWN SUMMARY")
    lines.append("-------------------------")
    for pb in report.get("project_breakdown", []):
        earned_str = f"   Earned: {pb['earned_display']}" if pb.get('earned_display') else ""
        lines.append(f"{pb['project']:<20s} {pb['formatted']:>12s}   {pb['percent']:>5.1f}%{earned_str}")
    lines.append("")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

def export_json(report, filepath, is_internal=False):
    """Export the report as a .json file."""
    # Normalize timeline entries — may contain datetime objects from load_session_json
    normalized_timeline = []
    for t in report["timeline"]:
        normalized_timeline.append({
            "app": t["app"],
            "start": t["start"].strftime("%H:%M:%S") if hasattr(t["start"], "strftime") else t["start"],
            "end": t["end"].strftime("%H:%M:%S") if hasattr(t["end"], "strftime") else t["end"],
        })

    if is_internal:
        apps_list = [{"name": a["name"], "seconds": a["seconds"], "excluded": a["excluded"], "tag": a.get("tag", "Unassigned")} for a in report["apps"]]
        new_activity_list = report.get("new_activity", [])
    else:
        apps_list = [{"name": a["name"], "seconds": a["seconds"], "tag": a.get("tag", "Unassigned")} for a in report["apps"] if not a["excluded"]]
        new_activity_list = [a for a in report.get("new_activity", []) if not a["excluded"]]

    export = {
        "session_name": report.get("session_name", ""),
        "app_exe_paths": report.get("app_exe_paths", {}),
        "date": report["date"],
        "start": report["start"],
        "end": report["end"],
        "total_seconds": report["total_seconds"],
        "counted_seconds": report["counted_seconds"],
        "is_resumed": report.get("is_resumed", False),
        "new_activity": new_activity_list,
        "apps": apps_list,
        "project_breakdown": report.get("project_breakdown", []),
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
    export_json(report, filepath, is_internal=True)
    return filepath

def save_to_history(report):
    """Save session to sessions/ folder (User Manual Save)."""
    folder = os.path.join(get_app_data_dir(), "sessions")
    os.makedirs(folder, exist_ok=True)
    start_dt = datetime.strptime(report['date'] + " " + report['start'], "%Y-%m-%d %H:%M:%S")
    filename = f"session_{start_dt.strftime('%Y-%m-%d_%H-%M-%S')}.json"
    filepath = os.path.join(folder, filename)
    export_json(report, filepath, is_internal=True)
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
    project_times = {}
    for a in data['apps']:
        tag = a.get('tag', 'Unassigned')
        pct = (a['seconds'] / data['total_seconds'] * 100) if data['total_seconds'] > 0 else 0
        apps.append({
            "name": a['name'],
            "seconds": a['seconds'],
            "formatted": format_duration(a['seconds']),
            "percent": round(pct, 1),
            "excluded": a.get('excluded', False),
            "tag": tag
        })
        if not a['excluded']:
            project_times[tag] = project_times.get(tag, 0) + a['seconds']

    total_counted = sum(project_times.values())
    breakdown = []
    for proj, secs in project_times.items():
        proj_pct = (secs / total_counted * 100) if total_counted > 0 else 0
        proj_earned = (secs / 3600) * data.get('hourly_rate', 0.0)
        breakdown.append({
            "project": proj,
            "seconds": int(secs),
            "formatted": format_duration(secs),
            "percent": round(proj_pct, 1),
            "earned": round(proj_earned, 2),
            "earned_display": f"{data.get('currency_symbol', '$')}{proj_earned:,.2f}",
            "color": get_project_color(proj)
        })
    breakdown.sort(key=lambda x: x["seconds"], reverse=True)

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
        "total_earned_display": f"{data.get('currency_symbol','$')}{data.get('total_earned',0.0):,.2f}",
        "project_breakdown": breakdown,
    }

def export_csv(report, filepath):
    """Export a single session report as CSV."""
    try:
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            date_str = report['date']
            session_name = report.get('session_name', 'Unnamed')

            # New activity section (resumed sessions only)
            new_activity = [a for a in report.get('new_activity', []) if not a['excluded']]
            if new_activity:
                writer.writerow(['[RESUMED SESSION] NEW ACTIVITY', '', '', '', '', '', '', ''])
                writer.writerow(['App Name', 'Category', 'Previous Time (seconds)', 'Previous Time',
                                 'New Added (seconds)', 'New Added', 'Total (seconds)', 'Total'])
                for a in new_activity:
                    writer.writerow([
                        a['name'], a.get('tag', 'Unassigned'),
                        a['previous_seconds'], a['previous_formatted'],
                        a['new_seconds'], a['new_formatted'] if a['new_seconds'] > 0 else '—',
                        a['total_seconds'], a['total_formatted']
                    ])
                writer.writerow([])

            writer.writerow(['Date', 'Session Name', 'App Name', 'Project', 'Duration (seconds)',
                            'Duration (formatted)', 'Percent of Session'])
            for app in report['apps']:
                if app['excluded']:
                    continue
                writer.writerow([date_str, session_name, app['name'], app.get('tag', 'Unassigned'), app['seconds'],
                                app['formatted'], f"{app['percent']:.1f}%"])

            writer.writerow([])
            writer.writerow(['PROJECT BREAKDOWN', '', '', '', '', '', ''])
            writer.writerow(['Project', 'Duration (seconds)', 'Duration (formatted)', 'Percent of Total Counted', 'Estimated Earnings'])
            for pb in report.get('project_breakdown', []):
                writer.writerow([pb['project'], pb['seconds'], pb['formatted'], f"{pb['percent']:.1f}%", pb['earned_display'] or "N/A"])
            writer.writerow([])
            writer.writerow(['TOTAL COUNTED HOURS', '', '', report['counted_seconds'], report['counted_formatted'], '', ''])
            hourly_rate = report.get('hourly_rate', 0.0)
            currency_symbol = report.get('currency_symbol', '$')
            total_earned_display = report.get('total_earned_display') or f"{currency_symbol}0.00"
            writer.writerow(['TOTAL EARNED', '', '', '', total_earned_display, f"@ {currency_symbol}{hourly_rate:.2f}/hr", ''])
        return True
    except Exception as e:
        print(f"CSV export error: {e}")
        return False

def export_csv_history(reports_list, filepath, hourly_rate=0.0, currency_symbol="$"):
    """Export multiple session reports as a single CSV file."""
    try:
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Date', 'Start Time', 'End Time', 'Session Name', 'App Name', 'Project',
                            'Duration (seconds)', 'Duration (formatted)', 'Percent of Session'])
            total_counted_seconds = 0
            historical_projects = {}
            for report in sorted(reports_list, key=lambda r: r['date']):
                date_str = report['date']
                start_time = report['start']
                end_time = report['end']
                session_name = report.get('session_name', 'Unnamed')
                for app in report['apps']:
                    if app['excluded']:
                        continue
                    writer.writerow([date_str, start_time, end_time, session_name, app['name'], app.get('tag', 'Unassigned'),
                                    app['seconds'], app['formatted'], f"{app['percent']:.1f}%"])
                total_counted_seconds += report.get('counted_seconds', 0)
                
                # Accumulate historical project times
                for pb in report.get('project_breakdown', []):
                    historical_projects[pb['project']] = historical_projects.get(pb['project'], 0) + pb['seconds']

            writer.writerow([])
            h = total_counted_seconds // 3600
            m = (total_counted_seconds % 3600) // 60
            s = total_counted_seconds % 60
            total_formatted = f"{h}h {m:02d}m {s:02d}s"
            writer.writerow(['TOTAL COUNTED HOURS', '', '', '', '', '', total_counted_seconds, total_formatted, ''])
            total_earned = (total_counted_seconds / 3600) * hourly_rate
            total_earned_display = f"{currency_symbol}{total_earned:,.2f}"
            writer.writerow(['TOTAL EARNED', '', '', '', '', '', '', total_earned_display, f"@ {currency_symbol}{hourly_rate:.2f}/hr"])

            writer.writerow([])
            writer.writerow(['PROJECT BREAKDOWN SUMMARY', '', '', '', '', '', '', '', ''])
            writer.writerow(['Project', 'Duration (seconds)', 'Duration (formatted)', 'Percent of Total Counted', 'Estimated Earnings'])
            total_hist_counted = sum(historical_projects.values())
            for proj, secs in sorted(historical_projects.items(), key=lambda x: x[1], reverse=True):
                pct = (secs / total_hist_counted * 100) if total_hist_counted > 0 else 0
                earned = (secs / 3600) * hourly_rate
                earned_display = f"{currency_symbol}{earned:,.2f}"
                writer.writerow([proj, secs, format_duration(secs), f"{pct:.1f}%", earned_display])
        return True
    except Exception as e:
        print(f"CSV export error: {e}")
        return False
=======
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
    tag: str

class ProjectBreakdownEntry(TypedDict):
    project: str
    seconds: int
    formatted: str
    percent: float
    earned: float
    earned_display: str
    color: str

PROJECT_COLORS = {
    "Development": "#4F46E5",  # Indigo
    "Design": "#EC4899",       # Pink
    "Research": "#10B981",     # Emerald
    "Documentation": "#F59E0B",# Amber
    "Communication": "#06B6D4",# Cyan
    "Management": "#8B5CF6",   # Purple
    "Unassigned": "#64748B",   # Slate
}

def get_project_color(project_name: str) -> str:
    return PROJECT_COLORS.get(project_name, "#64748B")

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
    project_breakdown: List[ProjectBreakdownEntry]

def build_report_data(tracker, hourly_rate=0.0, currency_symbol="$") -> ReportData:
    """Build a structured dict from the tracker's session data."""
    session_start = tracker.session_start
    session_end = tracker.session_end or datetime.now()
    total_session = tracker.get_elapsed()
    counted = tracker.get_counted_seconds()
    apps = tracker.get_app_times_sorted()
    
    app_list = []
    project_times = {}
    for name, secs, included in apps:
        tag = tracker.get_app_tag(name)
        pct = (secs / total_session * 100) if total_session > 0 else 0
        app_list.append({
            "name": name,
            "seconds": int(secs),
            "formatted": format_duration(secs),
            "percent": round(pct, 1),
            "excluded": not included,
            "tag": tag,
        })
        if included:
            project_times[tag] = project_times.get(tag, 0) + secs

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

    total_counted = sum(project_times.values())
    breakdown = []
    for proj, secs in project_times.items():
        proj_pct = (secs / total_counted * 100) if total_counted > 0 else 0
        proj_earned = (secs / 3600) * hourly_rate
        breakdown.append({
            "project": proj,
            "seconds": int(secs),
            "formatted": format_duration(secs),
            "percent": round(proj_pct, 1),
            "earned": round(proj_earned, 2),
            "earned_display": f"{currency_symbol}{proj_earned:,.2f}",
            "color": get_project_color(proj)
        })
    breakdown.sort(key=lambda x: x["seconds"], reverse=True)

    # ── New Activity: diff against resume snapshot ─────────────────────────
    # Only populated when the session was loaded from a saved file via Session Manager.
    resume_snapshot = getattr(tracker, 'resume_snapshot', None)
    is_resumed = resume_snapshot is not None
    new_activity = []
    if is_resumed:
        # Collect all app names across both snapshot and current app_times
        all_app_names = set(resume_snapshot.keys()) | set(tracker.app_times.keys())
        # Sort by new seconds descending, then name
        for name, secs, included in apps:
            prev_secs = resume_snapshot.get(name, 0)
            new_secs = max(0.0, secs - prev_secs)
            if new_secs > 0 or prev_secs > 0:
                tag = tracker.get_app_tag(name)
                new_activity.append({
                    "name": name,
                    "previous_seconds": int(prev_secs),
                    "previous_formatted": format_duration(prev_secs),
                    "new_seconds": int(new_secs),
                    "new_formatted": format_duration(new_secs) if new_secs > 0 else "—",
                    "total_seconds": int(secs),
                    "total_formatted": format_duration(secs),
                    "excluded": not included,
                    "tag": tag,
                })
        # Only keep the list if at least one app has new time
        if not any(a["new_seconds"] > 0 for a in new_activity):
            new_activity = []

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
        "is_resumed": is_resumed,
        "new_activity": new_activity,
        "session_name": getattr(tracker, 'session_name', ""),
        "app_exe_paths": getattr(tracker, 'app_exe_paths', {}),
        "hourly_rate": hourly_rate,
        "currency_symbol": currency_symbol,
        "total_earned": round(earned, 2),
        "total_earned_display": f"{currency_symbol}{earned:,.2f}",
        "project_breakdown": breakdown,
    }

def export_txt(report, filepath):
    """Export the report as a .txt file."""
    lines = []
    lines.append("FOCUSLOG SESSION REPORT")
    if report.get("is_resumed"):
        lines.append("[RESUMED SESSION]")
    lines.append(f"Date: {report['date']}")
    lines.append(f"Start: {report['start']} | End: {report['end']} | Duration: {report['total_formatted']}")
    lines.append(f"Counted Work Time: {report['counted_formatted']}")
    hourly_rate = report.get("hourly_rate", 0.0)
    currency_symbol = report.get("currency_symbol", "$")
    lines.append(f"Hourly Rate: {currency_symbol}{hourly_rate:.2f}/hr")
    lines.append(f"Total Earned: {report.get('total_earned_display') or (currency_symbol + '0.00')}")
    lines.append("")
    # New activity section (only for resumed sessions with new time)
    new_activity = [a for a in report.get("new_activity", []) if not a["excluded"]]
    if new_activity:
        lines.append("NEW ACTIVITY (THIS RESUME)")
        lines.append("--------------------------")
        lines.append(f"{'App':<30s} {'Previous':>12s} {'New Added':>12s} {'Total':>12s}")
        for a in new_activity:
            new_str = a["new_formatted"] if a["new_seconds"] > 0 else "—"
            lines.append(f"{a['name']:<30s} {a['previous_formatted']:>12s} {new_str:>12s} {a['total_formatted']:>12s}")
        lines.append("")
    lines.append("APP USAGE BREAKDOWN")
    lines.append("-------------------")
    for app in report["apps"]:
        if app["excluded"]:
            continue
        lines.append(f"{app['name']:<30s} {app['formatted']:>12s}   {app['percent']:>5.1f}%")
    lines.append("")
    lines.append("TIMELINE LOG")
    lines.append("------------")
    for entry in report["timeline"]:
        t_start = entry['start'].strftime("%H:%M:%S") if hasattr(entry['start'], 'strftime') else entry['start']
        t_end = entry['end'].strftime("%H:%M:%S") if hasattr(entry['end'], 'strftime') else entry['end']
        lines.append(f"{t_start} -> {t_end}   {entry['app']}")
    lines.append("")
    lines.append("PROJECT BREAKDOWN SUMMARY")
    lines.append("-------------------------")
    for pb in report.get("project_breakdown", []):
        earned_str = f"   Earned: {pb['earned_display']}" if pb.get('earned_display') else ""
        lines.append(f"{pb['project']:<20s} {pb['formatted']:>12s}   {pb['percent']:>5.1f}%{earned_str}")
    lines.append("")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

def export_json(report, filepath, is_internal=False):
    """Export the report as a .json file."""
    # Normalize timeline entries — may contain datetime objects from load_session_json
    normalized_timeline = []
    for t in report["timeline"]:
        normalized_timeline.append({
            "app": t["app"],
            "start": t["start"].strftime("%H:%M:%S") if hasattr(t["start"], "strftime") else t["start"],
            "end": t["end"].strftime("%H:%M:%S") if hasattr(t["end"], "strftime") else t["end"],
        })

    if is_internal:
        apps_list = [{"name": a["name"], "seconds": a["seconds"], "excluded": a["excluded"], "tag": a.get("tag", "Unassigned")} for a in report["apps"]]
        new_activity_list = report.get("new_activity", [])
    else:
        apps_list = [{"name": a["name"], "seconds": a["seconds"], "tag": a.get("tag", "Unassigned")} for a in report["apps"] if not a["excluded"]]
        new_activity_list = [a for a in report.get("new_activity", []) if not a["excluded"]]

    export = {
        "session_name": report.get("session_name", ""),
        "app_exe_paths": report.get("app_exe_paths", {}),
        "date": report["date"],
        "start": report["start"],
        "end": report["end"],
        "total_seconds": report["total_seconds"],
        "counted_seconds": report["counted_seconds"],
        "is_resumed": report.get("is_resumed", False),
        "new_activity": new_activity_list,
        "apps": apps_list,
        "project_breakdown": report.get("project_breakdown", []),
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
    export_json(report, filepath, is_internal=True)
    return filepath

def save_to_history(report):
    """Save session to sessions/ folder (User Manual Save)."""
    folder = os.path.join(get_app_data_dir(), "sessions")
    os.makedirs(folder, exist_ok=True)
    start_dt = datetime.strptime(report['date'] + " " + report['start'], "%Y-%m-%d %H:%M:%S")
    filename = f"session_{start_dt.strftime('%Y-%m-%d_%H-%M-%S')}.json"
    filepath = os.path.join(folder, filename)
    export_json(report, filepath, is_internal=True)
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
    project_times = {}
    for a in data['apps']:
        tag = a.get('tag', 'Unassigned')
        pct = (a['seconds'] / data['total_seconds'] * 100) if data['total_seconds'] > 0 else 0
        apps.append({
            "name": a['name'],
            "seconds": a['seconds'],
            "formatted": format_duration(a['seconds']),
            "percent": round(pct, 1),
            "excluded": a.get('excluded', False),
            "tag": tag
        })
        if not a['excluded']:
            project_times[tag] = project_times.get(tag, 0) + a['seconds']

    total_counted = sum(project_times.values())
    breakdown = []
    for proj, secs in project_times.items():
        proj_pct = (secs / total_counted * 100) if total_counted > 0 else 0
        proj_earned = (secs / 3600) * data.get('hourly_rate', 0.0)
        breakdown.append({
            "project": proj,
            "seconds": int(secs),
            "formatted": format_duration(secs),
            "percent": round(proj_pct, 1),
            "earned": round(proj_earned, 2),
            "earned_display": f"{data.get('currency_symbol', '$')}{proj_earned:,.2f}",
            "color": get_project_color(proj)
        })
    breakdown.sort(key=lambda x: x["seconds"], reverse=True)

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
        "total_earned_display": f"{data.get('currency_symbol','$')}{data.get('total_earned',0.0):,.2f}",
        "project_breakdown": breakdown,
    }

def export_csv(report, filepath):
    """Export a single session report as CSV."""
    try:
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            date_str = report['date']
            session_name = report.get('session_name', 'Unnamed')

            # New activity section (resumed sessions only)
            new_activity = [a for a in report.get('new_activity', []) if not a['excluded']]
            if new_activity:
                writer.writerow(['[RESUMED SESSION] NEW ACTIVITY', '', '', '', '', '', '', ''])
                writer.writerow(['App Name', 'Category', 'Previous Time (seconds)', 'Previous Time',
                                 'New Added (seconds)', 'New Added', 'Total (seconds)', 'Total'])
                for a in new_activity:
                    writer.writerow([
                        a['name'], a.get('tag', 'Unassigned'),
                        a['previous_seconds'], a['previous_formatted'],
                        a['new_seconds'], a['new_formatted'] if a['new_seconds'] > 0 else '—',
                        a['total_seconds'], a['total_formatted']
                    ])
                writer.writerow([])

            writer.writerow(['Date', 'Session Name', 'App Name', 'Project', 'Duration (seconds)',
                            'Duration (formatted)', 'Percent of Session'])
            for app in report['apps']:
                if app['excluded']:
                    continue
                writer.writerow([date_str, session_name, app['name'], app.get('tag', 'Unassigned'), app['seconds'],
                                app['formatted'], f"{app['percent']:.1f}%"])

            writer.writerow([])
            writer.writerow(['PROJECT BREAKDOWN', '', '', '', '', '', ''])
            writer.writerow(['Project', 'Duration (seconds)', 'Duration (formatted)', 'Percent of Total Counted', 'Estimated Earnings'])
            for pb in report.get('project_breakdown', []):
                writer.writerow([pb['project'], pb['seconds'], pb['formatted'], f"{pb['percent']:.1f}%", pb['earned_display'] or "N/A"])
            writer.writerow([])
            writer.writerow(['TOTAL COUNTED HOURS', '', '', report['counted_seconds'], report['counted_formatted'], '', ''])
            hourly_rate = report.get('hourly_rate', 0.0)
            currency_symbol = report.get('currency_symbol', '$')
            total_earned_display = report.get('total_earned_display') or f"{currency_symbol}0.00"
            writer.writerow(['TOTAL EARNED', '', '', '', total_earned_display, f"@ {currency_symbol}{hourly_rate:.2f}/hr", ''])
        return True
    except Exception as e:
        print(f"CSV export error: {e}")
        return False

def export_csv_history(reports_list, filepath, hourly_rate=0.0, currency_symbol="$"):
    """Export multiple session reports as a single CSV file."""
    try:
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Date', 'Start Time', 'End Time', 'Session Name', 'App Name', 'Project',
                            'Duration (seconds)', 'Duration (formatted)', 'Percent of Session'])
            total_counted_seconds = 0
            historical_projects = {}
            for report in sorted(reports_list, key=lambda r: r['date']):
                date_str = report['date']
                start_time = report['start']
                end_time = report['end']
                session_name = report.get('session_name', 'Unnamed')
                for app in report['apps']:
                    if app['excluded']:
                        continue
                    writer.writerow([date_str, start_time, end_time, session_name, app['name'], app.get('tag', 'Unassigned'),
                                    app['seconds'], app['formatted'], f"{app['percent']:.1f}%"])
                total_counted_seconds += report.get('counted_seconds', 0)
                
                # Accumulate historical project times
                for pb in report.get('project_breakdown', []):
                    historical_projects[pb['project']] = historical_projects.get(pb['project'], 0) + pb['seconds']

            writer.writerow([])
            h = total_counted_seconds // 3600
            m = (total_counted_seconds % 3600) // 60
            s = total_counted_seconds % 60
            total_formatted = f"{h}h {m:02d}m {s:02d}s"
            writer.writerow(['TOTAL COUNTED HOURS', '', '', '', '', '', total_counted_seconds, total_formatted, ''])
            total_earned = (total_counted_seconds / 3600) * hourly_rate
            total_earned_display = f"{currency_symbol}{total_earned:,.2f}"
            writer.writerow(['TOTAL EARNED', '', '', '', '', '', '', total_earned_display, f"@ {currency_symbol}{hourly_rate:.2f}/hr"])

            writer.writerow([])
            writer.writerow(['PROJECT BREAKDOWN SUMMARY', '', '', '', '', '', '', '', ''])
            writer.writerow(['Project', 'Duration (seconds)', 'Duration (formatted)', 'Percent of Total Counted', 'Estimated Earnings'])
            total_hist_counted = sum(historical_projects.values())
            for proj, secs in sorted(historical_projects.items(), key=lambda x: x[1], reverse=True):
                pct = (secs / total_hist_counted * 100) if total_hist_counted > 0 else 0
                earned = (secs / 3600) * hourly_rate
                earned_display = f"{currency_symbol}{earned:,.2f}"
                writer.writerow([proj, secs, format_duration(secs), f"{pct:.1f}%", earned_display])
        return True
    except Exception as e:
        print(f"CSV export error: {e}")
        return False

def aggregate_history_data(start_date: datetime, end_date: datetime, hourly_rate: float = 0.0, currency_symbol: str = "$"):
    """
    Scans and aggregates manual saved sessions and autosaved backups for a specific date range.
    Deduplicates sessions found in both folders using (date, start) as a unique key.
    """
    import glob
    sessions_folder = os.path.join(get_app_data_dir(), "sessions")
    autosave_folder = os.path.join(get_app_data_dir(), "autosave")
    
    unique_sessions = {}
    
    # Scan both folders
    for folder in [autosave_folder, sessions_folder]:
        if not os.path.exists(folder):
            continue
        for filepath in glob.glob(os.path.join(folder, "*.json")):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # Unique key: (date, start_time)
                date_str = data.get("date")
                start_str = data.get("start")
                if not date_str or not start_str:
                    continue
                
                key = (date_str, start_str)
                total_secs = data.get("total_seconds", 0)
                
                # Deduplicate: keep the session with more recorded time (most complete)
                if key in unique_sessions:
                    existing_total = unique_sessions[key].get("total_seconds", 0)
                    if total_secs > existing_total:
                        unique_sessions[key] = data
                else:
                    unique_sessions[key] = data
            except Exception:
                continue
                
    # Filter sessions by date range
    filtered_sessions = []
    start_d = start_date.date()
    end_d = end_date.date()
    
    for session in unique_sessions.values():
        try:
            s_date = datetime.strptime(session["date"], "%Y-%m-%d").date()
            if start_d <= s_date <= end_d:
                filtered_sessions.append(session)
        except Exception:
            continue
            
    # Accumulate results
    total_seconds = 0
    counted_seconds = 0
    app_times = {}
    app_tags = {}
    app_exes = {}
    app_exclusions = {}
    project_times = {}
    
    # Track daily hours for trend chart
    # Key: date_str (YYYY-MM-DD) -> counted_seconds
    daily_counted_secs = {}
    curr_d = start_d
    while curr_d <= end_d:
        daily_counted_secs[curr_d.strftime("%Y-%m-%d")] = 0
        curr_d += timedelta(days=1)
        
    for session in filtered_sessions:
        total_seconds += session.get("total_seconds", 0)
        c_secs = session.get("counted_seconds", 0)
        counted_seconds += c_secs
        
        # Accumulate daily hours
        s_date_str = session["date"]
        if s_date_str in daily_counted_secs:
            daily_counted_secs[s_date_str] += c_secs
            
        # Accumulate apps
        for app in session.get("apps", []):
            name = app["name"]
            secs = app.get("seconds", 0)
            tag = app.get("tag", "Unassigned")
            excluded = app.get("excluded", False)
            
            app_times[name] = app_times.get(name, 0) + secs
            app_tags[name] = tag
            app_exclusions[name] = excluded
            
            # Map exe path if present in session
            exe_path = session.get("app_exe_paths", {}).get(name)
            if exe_path:
                app_exes[name] = exe_path
                
            if not excluded:
                project_times[tag] = project_times.get(tag, 0) + secs

    # Format app breakdown list
    app_list = []
    for name, secs in app_times.items():
        pct = (secs / total_seconds * 100.0) if total_seconds > 0 else 0
        app_list.append({
            "name": name,
            "seconds": int(secs),
            "formatted": format_duration(secs),
            "percent": round(pct, 1),
            "excluded": app_exclusions.get(name, False),
            "tag": app_tags.get(name, "Unassigned"),
            "exe_path": app_exes.get(name, "")
        })
    app_list.sort(key=lambda x: x["seconds"], reverse=True)
    
    # Format project breakdown
    project_list = []
    total_project_counted = sum(project_times.values())
    for proj, secs in project_times.items():
        pct = (secs / total_project_counted * 100.0) if total_project_counted > 0 else 0
        earned = (secs / 3600.0) * hourly_rate
        project_list.append({
            "project": proj,
            "seconds": int(secs),
            "formatted": format_duration(secs),
            "percent": round(pct, 1),
            "earned": round(earned, 2),
            "earned_display": f"{currency_symbol}{earned:,.2f}",
            "color": get_project_color(proj)
        })
    project_list.sort(key=lambda x: x["seconds"], reverse=True)

    # Format daily trend data for BarChartWidget
    daily_trend = []
    curr_d = start_d
    # Choose nice labels based on range size
    total_days = (end_d - start_d).days + 1
    while curr_d <= end_d:
        d_str = curr_d.strftime("%Y-%m-%d")
        secs = daily_counted_secs.get(d_str, 0)
        
        # Determine labels: e.g. "Mon" if <= 7 days, "MM/DD" otherwise
        if total_days <= 7:
            label = curr_d.strftime("%a")  # Mon, Tue, etc.
        else:
            label = curr_d.strftime("%m/%d")  # 05/26
            
        daily_trend.append({
            "label": label,
            "value": round(secs / 3600.0, 2)
        })
        curr_d += timedelta(days=1)
        
    # Calculate total earned
    total_earned = 0.0
    if hourly_rate > 0:
        total_earned = (counted_seconds / 3600.0) * hourly_rate

    return {
        "total_seconds": total_seconds,
        "total_formatted": format_duration(total_seconds),
        "counted_seconds": counted_seconds,
        "counted_formatted": format_duration(counted_seconds),
        "total_earned": round(total_earned, 2),
        "total_earned_display": f"{currency_symbol}{total_earned:,.2f}",
        "apps": app_list,
        "project_breakdown": project_list,
        "daily_trend": daily_trend,
        "session_count": len(filtered_sessions)
    }

def merge_sessions_for_invoice(filepaths: List[str], tracker, hourly_rate: float = 0.0, currency_symbol: str = "$"):
    """
    Merges multiple session logs for invoicing.
    Applies real-time category & exclusion overrides using the active tracker.
    """
    unique_sessions = {}
    for filepath in filepaths:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            date_str = data.get("date")
            start_str = data.get("start")
            if not date_str or not start_str:
                continue
                
            key = (date_str, start_str)
            total_secs = data.get("total_seconds", 0)
            
            # Deduplicate sessions: keep the one with higher tracked duration
            if key in unique_sessions:
                existing_total = unique_sessions[key].get("total_seconds", 0)
                if total_secs > existing_total:
                    unique_sessions[key] = data
            else:
                unique_sessions[key] = data
        except Exception:
            continue
            
    total_seconds = 0
    counted_seconds = 0
    project_times = {}
    
    # Process apps dynamically with overrides
    for session in unique_sessions.values():
        total_seconds += session.get("total_seconds", 0)
        
        for app in session.get("apps", []):
            name = app["name"]
            secs = app.get("seconds", 0)
            
            # Real-time overrides from active tracker
            tag = tracker.get_app_tag(name)
            included = tracker.get_included(name)
            
            if included:
                counted_seconds += secs
                project_times[tag] = project_times.get(tag, 0) + secs
                
    # Format project breakdown
    breakdown = []

    curr_sym = currency_symbol
    
    total_project_counted = sum(project_times.values())
    for proj, secs in project_times.items():
        pct = (secs / total_project_counted * 100.0) if total_project_counted > 0 else 0
        earned = (secs / 3600.0) * hourly_rate
        breakdown.append({
            "project": proj,
            "seconds": int(secs),
            "formatted": format_duration(secs),
            "percent": round(pct, 1),
            "earned": round(earned, 2),
            "earned_display": f"{curr_sym}{earned:,.2f}",
            "color": get_project_color(proj)
        })
    breakdown.sort(key=lambda x: x["seconds"], reverse=True)
    
    total_earned = 0.0
    if hourly_rate > 0:
        total_earned = (counted_seconds / 3600.0) * hourly_rate
        
    return {
        "total_seconds": total_seconds,
        "total_formatted": format_duration(total_seconds),
        "counted_seconds": counted_seconds,
        "counted_formatted": format_duration(counted_seconds),
        "total_earned": round(total_earned, 2),
        "total_earned_display": f"{curr_sym}{total_earned:,.2f}",
        "project_breakdown": breakdown,
        "session_count": len(unique_sessions)
    }

def generate_invoice_html(billing_data, settings_data) -> str:
    """
    Generates a stunning, premium, modern A4 HTML invoice.
    Optimized for high-fidelity web viewing and perfect browser-based PDF printing.
    """
    import base64
    logo_path = settings_data.get("business_logo_path", "")
    logo_data_uri = ""
    if logo_path and os.path.exists(logo_path):
        try:
            ext = os.path.splitext(logo_path)[1].lower().replace(".", "")
            if ext in ["png", "jpg", "jpeg"]:
                with open(logo_path, "rb") as f:
                    encoded = base64.b64encode(f.read()).decode("utf-8")
                logo_data_uri = f"data:image/{ext};base64,{encoded}"
        except Exception:
            pass

    # Header Logo Setup
    logo_html = ""
    if logo_data_uri:
        logo_html = f'<img src="{logo_data_uri}" class="invoice-logo" />'

    # Calculation Metrics
    hours_counted = billing_data["counted_seconds"] / 3600.0
    hourly_rate = settings_data.get("hourly_rate", 0.0)
    curr_sym = settings_data.get("currency_symbol", "$")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Invoice - {settings_data.get("business_name", "FocusLog")}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --primary: #0F172A;
            --primary-light: #1E293B;
            --accent: #4F46E5;
            --accent-hover: #4338CA;
            --success: #16A34A;
            --bg-body: #F8FAFC;
            --bg-card: #FFFFFF;
            --border: #E2E8F0;
            --text-main: #0F172A;
            --text-muted: #64748B;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: 'Inter', system-ui, -apple-system, sans-serif;
            background-color: var(--bg-body);
            color: var(--text-main);
            line-height: 1.5;
            padding: 40px 20px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }}

        /* Print utility bar */
        .print-actions-bar {{
            width: 100%;
            max-width: 800px;
            background: rgba(255, 255, 255, 0.85);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 16px 24px;
            margin-bottom: 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.05);
            animation: slideDown 0.4s ease-out;
        }}

        @keyframes slideDown {{
            from {{ transform: translateY(-20px); opacity: 0; }}
            to {{ transform: translateY(0); opacity: 1; }}
        }}

        .print-title {{
            font-weight: 600;
            font-size: 14px;
            color: var(--text-main);
        }}

        .print-btn {{
            background-color: var(--accent);
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            font-weight: 600;
            font-size: 13px;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            transition: all 0.2s ease;
            box-shadow: 0 4px 12px -2px rgba(79, 70, 229, 0.3);
        }}

        .print-btn:hover {{
            background-color: var(--accent-hover);
            transform: translateY(-1px);
            box-shadow: 0 6px 16px -2px rgba(79, 70, 229, 0.4);
        }}

        /* Invoice Container conforming to A4 */
        .invoice-container {{
            width: 100%;
            max-width: 800px;
            background-color: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 50px;
            box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.04);
            position: relative;
        }}

        /* Header Layout */
        .invoice-header-row {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            border-bottom: 2px solid var(--bg-body);
            padding-bottom: 30px;
            margin-bottom: 35px;
        }}

        .invoice-logo {{
            max-width: 200px;
            max-height: 70px;
            object-fit: contain;
            margin-bottom: 12px;
            display: block;
        }}

        .profile-title {{
            font-size: 18px;
            font-weight: 700;
            color: var(--primary);
            letter-spacing: -0.02em;
        }}

        .profile-details {{
            font-size: 13px;
            color: var(--text-muted);
            margin-top: 6px;
            line-height: 1.4;
        }}

        .meta-column {{
            text-align: right;
        }}

        .invoice-badge {{
            font-size: 28px;
            font-weight: 800;
            color: var(--primary);
            letter-spacing: -0.03em;
            margin-bottom: 12px;
        }}

        .meta-item {{
            font-size: 13px;
            color: var(--text-muted);
            margin-bottom: 4px;
            line-height: 1.4;
        }}

        .meta-item strong {{
            color: var(--text-main);
            font-weight: 600;
        }}

        /* Client Info Section */
        .billed-to-container {{
            margin-bottom: 35px;
        }}

        .section-label {{
            font-size: 10px;
            font-weight: 700;
            text-transform: uppercase;
            color: var(--accent);
            letter-spacing: 0.1em;
            margin-bottom: 8px;
        }}

        .client-name {{
            font-size: 15px;
            font-weight: 700;
            color: var(--text-main);
        }}

        .client-address {{
            font-size: 13px;
            color: var(--text-muted);
            margin-top: 4px;
            line-height: 1.4;
        }}

        /* Callout summary cards grid */
        .dashboard-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 40px;
        }}

        .kpi-card {{
            background: var(--bg-body);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
            transition: all 0.2s ease;
        }}

        .kpi-card:hover {{
            border-color: var(--text-muted);
        }}

        .kpi-label {{
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            color: var(--text-muted);
            letter-spacing: 0.05em;
        }}

        .kpi-val {{
            font-size: 26px;
            font-weight: 800;
            margin-top: 6px;
            letter-spacing: -0.03em;
        }}

        .hours-val {{ color: var(--accent); }}
        .amount-val {{ color: var(--success); }}

        /* Itemized table styling */
        .table-title {{
            font-size: 13px;
            font-weight: 700;
            color: var(--text-main);
            margin-bottom: 12px;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 35px;
        }}

        th {{
            background-color: var(--primary);
            color: white;
            font-size: 10px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            padding: 12px 16px;
            text-align: left;
        }}

        th:first-child {{ border-top-left-radius: 8px; border-bottom-left-radius: 8px; }}
        th:last-child {{ border-top-right-radius: 8px; border-bottom-right-radius: 8px; text-align: right; }}

        td {{
            padding: 14px 16px;
            font-size: 13px;
            border-bottom: 1px solid var(--border);
            color: var(--text-main);
        }}

        td:last-child {{
            text-align: right;
            font-weight: 600;
        }}

        tr:hover td {{
            background-color: var(--bg-body);
        }}

        /* Subtotal summary section */
        .subtotal-row td {{
            border-bottom: none;
            padding-top: 20px;
        }}

        .subtotal-label {{
            text-align: right;
            font-weight: 700;
            font-size: 13px;
            color: var(--text-muted);
        }}

        .subtotal-value {{
            text-align: right;
            font-weight: 800;
            font-size: 18px;
            color: var(--success);
            letter-spacing: -0.02em;
        }}

        /* Bottom Details Box */
        .payment-box {{
            background-color: var(--bg-body);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
            margin-top: 10px;
        }}

        .payment-box-title {{
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            color: var(--text-muted);
            letter-spacing: 0.05em;
            margin-bottom: 6px;
        }}

        .payment-content {{
            font-size: 12px;
            color: var(--text-main);
            line-height: 1.5;
        }}

        /* Browser Printing Styles */
        @media print {{
            body {{
                background-color: white;
                padding: 0;
            }}
            .print-actions-bar {{
                display: none;
            }}
            .invoice-container {{
                border: none;
                box-shadow: none;
                padding: 0;
                width: 100%;
                max-width: 100%;
            }}
            .kpi-card {{
                border-color: var(--border) !important;
                background-color: #F8FAFC !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
            }}
        }}
    </style>
</head>
<body>

    <!-- Dynamic Browser Action Bar -->
    <div class="print-actions-bar">
        <div class="print-title">📄 Invoice HTML Created successfully. Ready to print or export to PDF.</div>
        <button class="print-btn" onclick="window.print()">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="6 9 6 2 18 2 18 9"></polyline>
                <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"></path>
                <rect x="6" y="14" width="12" height="8"></rect>
            </svg>
            Print / Save as PDF
        </button>
    </div>

    <!-- Main Print Document Container -->
    <div class="invoice-container">
        
        <!-- Header Info -->
        <div class="invoice-header-row">
            <div>
                {logo_html}
                <div class="profile-title">{settings_data.get("business_name", "FocusLog Invoice")}</div>
                <div class="profile-details">
                    {settings_data.get("business_address", "")}<br>
                    {settings_data.get("business_email", "")} {settings_data.get("business_phone", "")}
                </div>
            </div>
            
            <div class="meta-column">
                <div class="invoice-badge">INVOICE</div>
                <div class="meta-item"><strong>Invoice No:</strong> INV-{datetime.now().strftime("%Y%m%d%H%M")}</div>
                <div class="meta-item"><strong>Date:</strong> {datetime.now().strftime("%B %d, %Y")}</div>
                <div class="meta-item"><strong>Sessions Compiled:</strong> {billing_data.get("session_count", 1)}</div>
            </div>
        </div>

        <!-- Billed to Client -->
        <div class="billed-to-container">
            <div class="section-label">Billed To</div>
            <div class="client-name">{settings_data.get("client_name", "Valued Client")}</div>
            <div class="client-address">
                {settings_data.get("client_address", "")}
            </div>
        </div>

        <!-- Visual Analytics Dashboard Cards -->
        <div class="dashboard-grid">
            <div class="kpi-card">
                <div class="kpi-label">Total Work Hours</div>
                <div class="kpi-val hours-val">{hours_counted:.2f} hrs</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">Total Amount Due</div>
                <div class="kpi-val amount-val">{billing_data["total_earned_display"]}</div>
            </div>
        </div>

        <!-- Itemized Breakdowns -->
        <div class="section-label">Itemized Work Breakdown</div>
        <table>
            <thead>
                <tr>
                    <th>Focus Category</th>
                    <th>Formatted Time</th>
                    <th>Hours</th>
                    <th>Rate</th>
                    <th style="text-align: right;">Total Amount</th>
                </tr>
            </thead>
            <tbody>
    """

    for pb in billing_data.get("project_breakdown", []):
        cat_hours = pb["seconds"] / 3600.0
        html += f"""
                <tr>
                    <td style="font-weight: 600;">{pb["project"]}</td>
                    <td>{pb["formatted"]}</td>
                    <td>{cat_hours:.2f}</td>
                    <td>{curr_sym}{hourly_rate:.2f}/hr</td>
                    <td>{pb["earned_display"]}</td>
                </tr>
        """

    html += f"""
                <tr class="subtotal-row">
                    <td colspan="4" class="subtotal-label">Grand Total:</td>
                    <td class="subtotal-value">{billing_data["total_earned_display"]}</td>
                </tr>
            </tbody>
        </table>

        <!-- Footer terms and info -->
        <div class="payment-box">
            <div class="payment-box-title">Payment Terms & Instructions</div>
            <div class="payment-content">
                {settings_data.get("business_payment", "Payment is due within 14 days of invoice date.")}
            </div>
        </div>

    </div>

</body>
</html>
"""
    return html

def print_html_to_pdf(html_content: str, output_path: str):
    """
    Natively converts HTML content into a vector PDF file using QPrinter and QTextDocument.
    """
    from PyQt6.QtGui import QTextDocument, QPageSize
    from PyQt6.QtPrintSupport import QPrinter
    
    doc = QTextDocument()
    doc.setHtml(html_content)
    
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(output_path)
    
    # Configure page settings
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    
    doc.print(printer)
    return True

>>>>>>> Stashed changes
