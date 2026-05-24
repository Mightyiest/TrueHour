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