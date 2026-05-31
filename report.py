"""
TrueHour — Report generation and export utilities.
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

def build_report_data(tracker, hourly_rate=0.0, currency_symbol="$", progress_cb=None) -> ReportData:
    """Build a structured dict from the tracker's session data."""
    if progress_cb:
        progress_cb(20, "Analyzing tracked session metrics...")
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

    if progress_cb:
        progress_cb(40, "Compiling category allocations...")

    # Snapshot timeline under the lock to prevent concurrent modification
    with tracker._lock:
        timeline_snapshot = list(tracker.timeline)

    timeline = []
    for entry in timeline_snapshot:
        if entry["app"] == "[Idle]" or not tracker.app_included.get(entry["app"], True):
            continue
        timeline.append({
            "app": entry["app"],
            "start": entry["start"].strftime("%H:%M:%S"),
            "end": entry["end"].strftime("%H:%M:%S"),
        })

    if progress_cb:
        progress_cb(60, "Constructing timeline log visualizers...")

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

    earned = 0.0
    if hourly_rate > 0:
        earned = sum(pb["earned"] for pb in breakdown)

    # ── New Activity: diff against resume snapshot ─────────────────────────
    # Only populated when the session was loaded from a saved file via Session Manager.
    resume_snapshot = getattr(tracker, 'resume_snapshot', None)
    is_resumed = resume_snapshot is not None
    new_activity = []
    if is_resumed:
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

    if progress_cb:
        progress_cb(75, "Aggregating new activities & diff snapshots...")

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
    try:
        from core.reporting.aggregator import update_daily_summary
        update_daily_summary(report)
    except Exception as e:
        print(f"[TrueHour] Failed to update daily summary: {e}")
    return filepath

def save_to_history(report):
    """Save session to sessions/ folder (User Manual Save)."""
    folder = os.path.join(get_app_data_dir(), "sessions")
    os.makedirs(folder, exist_ok=True)
    start_dt = datetime.strptime(report['date'] + " " + report['start'], "%Y-%m-%d %H:%M:%S")
    filename = f"session_{start_dt.strftime('%Y-%m-%d_%H-%M-%S')}.json"
    filepath = os.path.join(folder, filename)
    export_json(report, filepath, is_internal=True)
    try:
        from core.reporting.aggregator import update_daily_summary
        update_daily_summary(report)
    except Exception as e:
        print(f"[TrueHour] Failed to update daily summary: {e}")
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
        if not a.get('excluded', False):
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

    excluded_apps = {a['name'] for a in data.get('apps', []) if a.get('excluded', False)}
    timeline = []
    day_offset = timedelta(days=0)  # Track accumulated midnight crossovers
    prev_end_time = None
    for t in data['timeline']:
        if t['app'] in excluded_apps:
            continue
        t_start = datetime.strptime(data['date'] + " " + t['start'], "%Y-%m-%d %H:%M:%S") + day_offset
        t_end = datetime.strptime(data['date'] + " " + t['end'], "%Y-%m-%d %H:%M:%S") + day_offset
        
        # Detect if this entry's start is before the previous entry's end (crossed midnight)
        if prev_end_time and t_start < prev_end_time:
            day_offset += timedelta(days=1)
            t_start += timedelta(days=1)
            t_end += timedelta(days=1)
        
        # Midnight crossover guard within entry
        if t_end <= t_start:
            t_end += timedelta(days=1)
            day_offset += timedelta(days=1)
        
        prev_end_time = t_end
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
    
    # First, collect all finalized session keys to ignore orphaned/discarded autosaves
    finalized_keys = set()
    if os.path.exists(sessions_folder):
        for filepath in glob.glob(os.path.join(sessions_folder, "*.json")):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                date_str = data.get("date")
                start_str = data.get("start")
                if date_str and start_str:
                    finalized_keys.add((date_str, start_str))
                    # Add to unique_sessions initially
                    key = (date_str, start_str)
                    unique_sessions[key] = data
            except Exception:
                continue

    # Scan autosave folder, only including autosaves of finalized sessions to keep most complete data
    if os.path.exists(autosave_folder):
        for filepath in glob.glob(os.path.join(autosave_folder, "*.json")):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                date_str = data.get("date")
                start_str = data.get("start")
                if not date_str or not start_str:
                    continue
                
                key = (date_str, start_str)
                if key in finalized_keys:
                    total_secs = data.get("total_seconds", 0)
                    existing_total = unique_sessions[key].get("total_seconds", 0)
                    if total_secs > existing_total:
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
            # Only mark as excluded if ALL sessions excluded it
            if name not in app_exclusions:
                app_exclusions[name] = excluded
            elif not excluded:
                app_exclusions[name] = False
            
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
        total_earned = sum(item["earned"] for item in project_list)

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
            
            # Use the saved session's own exclusion status to compile exactly the productive/counted work time
            tag = tracker.get_app_tag(name)
            included = not app.get("excluded", False)
            
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
        total_earned = sum(item["earned"] for item in breakdown)
        
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

def mask_email(email: str) -> str:
    """
    Masks sensitive email data.
    e.g., neil@gmail.com -> ne**@*****.com
    """
    if not email or "@" not in email:
        return email
    try:
        parts = email.split("@")
        local = parts[0]
        domain = "@".join(parts[1:])
        
        # Local part: preserve first 2 characters, rest replaced with '**'
        if len(local) <= 2:
            masked_local = local + "**"
        else:
            masked_local = local[:2] + "**"
            
        # Domain: mask domain name with '*****', preserve TLD
        if "." in domain:
            domain_parts = domain.split(".")
            tld = domain_parts[-1]
            masked_domain = "*****." + tld
        else:
            masked_domain = "*****"
            
        return f"{masked_local}@{masked_domain}"
    except Exception:
        return email

def mask_phone(phone: str) -> str:
    """
    Masks sensitive phone numbers.
    e.g., +1 (555) 123-4567 -> +1 (555) ***-****
    """
    if not phone:
        return phone
    try:
        masked = []
        mask_count = 0
        for c in reversed(phone):
            if c.isdigit() and mask_count < 7:
                masked.append('*')
                mask_count += 1
            else:
                masked.append(c)
        return "".join(reversed(masked))
    except Exception:
        return phone

_TEMPLATE_CACHE = {}

def get_cached_template(template_path: str, default_content: str) -> str:
    """Return cached HTML template content to prevent redundant disk read operations."""
    if template_path in _TEMPLATE_CACHE:
        return _TEMPLATE_CACHE[template_path]
    
    if not os.path.exists(template_path):
        os.makedirs(os.path.dirname(template_path), exist_ok=True)
        try:
            with open(template_path, "w", encoding="utf-8") as f:
                f.write(default_content.strip())
        except Exception:
            pass

    try:
        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        content = default_content
        
    _TEMPLATE_CACHE[template_path] = content
    return content

def generate_invoice_html(billing_data, settings_data) -> str:
    """
    Generates a stunning, premium, modern A4 HTML invoice.
    Optimized for high-fidelity web viewing and perfect browser-based PDF printing.
    Loads templates/invoice.html from disk, auto-creating it if missing.
    """
    import base64
    import sys
    from html import escape as _esc
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
    else:
        # High-fidelity dynamic SVG placeholder logo that dynamically shifts with CSS theme variables!
        logo_html = """<svg class="invoice-logo" width="40" height="40" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" style="margin-bottom: 12px; display: block;">
  <rect width="40" height="40" rx="10" fill="url(#logo-grad)"/>
  <path d="M20 11V29" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M13 18L20 11L27 18" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M10 29H30" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
  <defs>
    <linearGradient id="logo-grad" x1="0" y1="0" x2="40" y2="40" gradientUnits="userSpaceOnUse">
      <stop stop-color="var(--accent-gradient-start, #6366F1)"/>
      <stop offset="1" stop-color="var(--accent-gradient-end, #4F46E5)"/>
    </linearGradient>
  </defs>
</svg>"""

    # Calculation Metrics
    hours_counted = billing_data["counted_seconds"] / 3600.0
    hourly_rate = settings_data.get("hourly_rate", 0.0)
    curr_sym = settings_data.get("currency_symbol", "$")

    # Email & Phone Masking & Multi-Email Processing
    mask_biz_emails = settings_data.get("mask_business_emails", settings_data.get("mask_sensitive_data", False))
    mask_biz_phone = settings_data.get("mask_business_phone", settings_data.get("mask_sensitive_data", False))
    mask_client_emails = settings_data.get("mask_client_emails", settings_data.get("mask_sensitive_data", False))
    
    # Process business emails
    biz_emails = settings_data.get("business_emails", [])
    if not biz_emails:
        legacy_email = settings_data.get("business_email", "")
        if legacy_email:
            biz_emails = [e.strip() for e in legacy_email.split(",") if e.strip()]
            
    if mask_biz_emails:
        biz_emails_processed = [_esc(mask_email(e)) for e in biz_emails]
    else:
        biz_emails_processed = [_esc(e) for e in biz_emails]
        
    biz_email_str = ", ".join(biz_emails_processed)
    
    # Process business phone
    biz_phone = settings_data.get("business_phone", "")
    if biz_phone:
        if mask_biz_phone:
            biz_phone = _esc(mask_phone(biz_phone))
        else:
            biz_phone = _esc(biz_phone)
        
    biz_contact_parts = []
    if biz_email_str:
        biz_contact_parts.append(biz_email_str)
    if biz_phone:
        biz_contact_parts.append(biz_phone)
    biz_contact_html = " &nbsp;&bull;&nbsp; ".join(biz_contact_parts)

    # Process client emails
    client_emails = settings_data.get("client_emails", [])
    if mask_client_emails:
        client_emails_processed = [_esc(mask_email(e)) for e in client_emails]
    else:
        client_emails_processed = [_esc(e) for e in client_emails]

    client_emails_html = ""
    if client_emails_processed:
        emails_joined = ", ".join(client_emails_processed)
        client_emails_html = f'<div class="client-email">{emails_joined}</div>'

    # Load and encode payment QR codes
    qr_html = ""
    qr_code_paths = settings_data.get("qr_code_paths", [])
    qr_code_links = settings_data.get("qr_code_links", {})
    if qr_code_paths:
        from config import get_app_data_dir
        qr_dir = os.path.join(get_app_data_dir(), "qr_codes")
        qr_items = []
        for qr_fname in qr_code_paths:
            qr_full_path = os.path.join(qr_dir, qr_fname)
            if os.path.exists(qr_full_path):
                try:
                    ext = os.path.splitext(qr_fname)[1].lower().replace(".", "")
                    if ext in ["png", "jpg", "jpeg"]:
                        with open(qr_full_path, "rb") as f:
                            encoded_qr = base64.b64encode(f.read()).decode("utf-8")
                        qr_data_uri = f"data:image/{ext};base64,{encoded_qr}"
                        
                        link_url = qr_code_links.get(qr_fname, "")
                        if link_url:
                            img_html = f"""
                                <a href="{_esc(link_url)}" target="_blank" style="cursor: pointer; display: block; text-decoration: none; text-align: center;">
                                    <img src="{qr_data_uri}" class="qr-code-image" alt="Payment QR Code" />
                                    <div style="font-size: 10px; color: var(--accent); margin-top: 6px; font-weight: 700; font-family: 'Inter', sans-serif;">🔗 Click to Pay</div>
                                </a>
                            """
                        else:
                            img_html = f'<img src="{qr_data_uri}" class="qr-code-image" alt="Payment QR Code" />'
                            
                        qr_items.append(f"""
                            <div class="qr-code-item">
                                {img_html}
                            </div>
                        """)
                except Exception as ex:
                    print(f"[TrueHour] Error base64 encoding QR code {qr_fname}: {ex}")
        if qr_items:
            has_any_link = any(qr_code_links.get(fn, "") for fn in qr_code_paths)
            hint_html = ""
            if has_any_link:
                hint_html = '\n            <div style="font-size: 11px; color: var(--text-muted); margin-top: 8px; font-weight: 500; font-family: \'Inter\', sans-serif;">💡 Click on a QR code to open its payment link.</div>'
            qr_html = f"""
            <div style="margin-top: 14px; padding-top: 12px; border-top: 1px dashed var(--border); display: flex; flex-direction: column; align-items: flex-start; justify-content: flex-start; width: 100%;">
                <div class="qr-codes-container">
                    {"".join(qr_items)}
                </div>{hint_html}
                <div class="trust-banner" style="margin-top: 8px; max-width: 320px;">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                        <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                        <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
                    </svg>
                    <span>Secure Settlement</span>
                </div>
            </div>
            """

    # Self-healing logic: find templates/invoice.html or auto-create it
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        except Exception:
            base_dir = os.getcwd()

    templates_dir = os.path.join(base_dir, "templates")
    template_path = os.path.join(templates_dir, "invoice.html")

    # Define default template fallback
    default_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Invoice - {{BUSINESS_NAME}}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Outfit:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-body: #F8FAFC;
            --bg-card: #FFFFFF;
            --border: #E2E8F0;
            --text-main: #0F172A;
            --text-muted: #64748B;
            --text-light: #94A3B8;
            --card-shadow: 0 8px 24px -10px rgba(15, 23, 42, 0.04);
            --hover-shadow: 0 16px 32px -12px rgba(15, 23, 42, 0.06);
            
            --accent: #4F46E5;
            --accent-hover: #4338CA;
            --accent-gradient-start: #6366F1;
            --accent-gradient-end: #4F46E5;
            --success: #10B981;
        }

        body.theme-indigo {
            --accent: #4F46E5;
            --accent-hover: #4338CA;
            --accent-gradient-start: #6366F1;
            --accent-gradient-end: #4F46E5;
            --success: #10B981;
        }
        body.theme-teal {
            --accent: #0D9488;
            --accent-hover: #0F766E;
            --accent-gradient-start: #14B8A6;
            --accent-gradient-end: #0D9488;
            --success: #10B981;
        }
        body.theme-slate {
            --accent: #334155;
            --accent-hover: #1E293B;
            --accent-gradient-start: #475569;
            --accent-gradient-end: #334155;
            --success: #059669;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { 
            font-family: 'Inter', system-ui, -apple-system, sans-serif; 
            background-color: var(--bg-body); 
            color: var(--text-main); 
            line-height: 1.5; 
            padding: 20px 16px; 
            display: flex; 
            flex-direction: column; 
            align-items: center;
            transition: background 0.3s ease;
        }

        .print-actions-bar { 
            width: 100%; 
            max-width: 850px; 
            background: rgba(255, 255, 255, 0.75); 
            backdrop-filter: blur(16px); 
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid rgba(226, 232, 240, 0.8); 
            border-radius: 10px; 
            padding: 8px 16px; 
            margin-bottom: 12px; 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
            box-shadow: var(--card-shadow);
        }
        .action-left-info {
            display: flex;
            align-items: center;
            gap: 16px;
        }
        .status-pill {
            font-size: 13px;
            font-weight: 600;
            color: var(--text-main);
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .theme-selector {
            display: flex;
            align-items: center;
            gap: 6px;
            background: #F1F5F9;
            padding: 4px;
            border-radius: 9999px;
            border: 1px solid var(--border);
        }
        .theme-pill-btn {
            border: none;
            width: 20px;
            height: 20px;
            border-radius: 50%;
            cursor: pointer;
            position: relative;
            transition: all 0.2s ease;
            box-shadow: inset 0 1px 3px rgba(0,0,0,0.1);
        }
        .theme-pill-btn:hover {
            transform: scale(1.15);
        }
        .theme-pill-btn.active::after {
            content: '';
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: white;
            box-shadow: 0 1px 2px rgba(0,0,0,0.3);
        }
        .theme-pill-btn[data-theme="indigo"] { background: linear-gradient(135deg, #6366F1, #4F46E5); }
        .theme-pill-btn[data-theme="teal"] { background: linear-gradient(135deg, #14B8A6, #0D9488); }
        .theme-pill-btn[data-theme="slate"] { background: linear-gradient(135deg, #475569, #334155); }

        .print-btn { 
            background: var(--accent-gradient-start);
            background: linear-gradient(135deg, var(--accent-gradient-start) 0%, var(--accent-gradient-end) 100%);
            color: white; 
            border: none; 
            padding: 8px 16px; 
            border-radius: 8px; 
            font-family: 'Outfit', sans-serif;
            font-size: 13.5px;
            font-weight: 600; 
            cursor: pointer; 
            display: inline-flex; 
            align-items: center; 
            gap: 8px; 
            transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1); 
            box-shadow: 0 3px 10px rgba(79, 70, 229, 0.12);
        }
        .print-btn:hover { 
            transform: translateY(-1px);
            box-shadow: 0 5px 15px rgba(79, 70, 229, 0.2);
        }

        .invoice-container { 
            width: 100%; 
            max-width: 850px; 
            background-color: var(--bg-card); 
            border: 1px solid var(--border); 
            border-radius: 16px; 
            padding: 32px 40px; 
            box-shadow: var(--card-shadow); 
            transition: all 0.3s ease;
        }
        
        .invoice-header-row { 
            display: flex; 
            justify-content: space-between; 
            align-items: flex-start; 
            border-bottom: 2px solid var(--bg-body); 
            padding-bottom: 20px; 
            margin-bottom: 24px; 
        }
        .invoice-logo { 
            max-width: 180px; 
            max-height: 52px; 
            object-fit: contain; 
            margin-bottom: 8px; 
            display: block; 
        }
        .profile-title { 
            font-family: 'Outfit', sans-serif;
            font-size: 18px; 
            font-weight: 700; 
            color: var(--text-main); 
            letter-spacing: -0.02em; 
        }
        .profile-details { 
            font-size: 12px; 
            color: var(--text-muted); 
            margin-top: 4px; 
            line-height: 1.4; 
        }
        
        .meta-column { text-align: right; }
        .invoice-badge { 
            font-family: 'Outfit', sans-serif;
            font-size: 24px; 
            font-weight: 800; 
            background: linear-gradient(135deg, var(--accent-gradient-start), var(--accent-gradient-end));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: -0.03em; 
            margin-bottom: 8px; 
        }
        .meta-item { 
            font-size: 12px; 
            color: var(--text-muted); 
            margin-bottom: 4px; 
        }
        .meta-item strong {
            color: var(--text-main);
            font-weight: 600;
        }

        .billed-to-container { margin-bottom: 20px; }
        .section-label { 
            font-family: 'Outfit', sans-serif;
            font-size: 10px; 
            font-weight: 700; 
            text-transform: uppercase; 
            color: var(--accent); 
            letter-spacing: 0.1em; 
            margin-bottom: 8px; 
        }
        .client-name { 
            font-family: 'Outfit', sans-serif;
            font-size: 15px; 
            font-weight: 700; 
            color: var(--text-main); 
        }
        .client-address { 
            font-size: 12.5px; 
            color: var(--text-muted); 
            margin-top: 4px; 
            line-height: 1.45; 
        }
        .client-email { 
            font-size: 12.5px; 
            color: var(--text-muted); 
            margin-top: 3px; 
            line-height: 1.45; 
        }

        .dashboard-grid { 
            display: grid; 
            grid-template-columns: 1fr 1fr; 
            gap: 12px; 
            margin-bottom: 24px; 
        }
        .kpi-card { 
            background-color: var(--bg-body); 
            border: 1px solid transparent; 
            border-left: 4px solid var(--accent);
            border-radius: 10px; 
            padding: 12px 16px; 
            transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1); 
        }
        .kpi-card:hover { 
            background-color: var(--bg-card); 
            border-color: var(--border); 
            border-left-color: var(--accent);
            transform: translateY(-1px);
            box-shadow: var(--hover-shadow);
        }
        .kpi-label { 
            font-size: 10.5px; 
            font-weight: 700; 
            text-transform: uppercase; 
            letter-spacing: 0.08em; 
            color: var(--text-muted); 
            margin-bottom: 4px; 
        }
        .kpi-val { 
            font-family: 'Outfit', sans-serif;
            font-size: 22px; 
            font-weight: 800; 
            color: var(--text-main); 
        }
        .amount-val { 
            color: var(--success); 
        }

        table { 
            width: 100%; 
            border-collapse: collapse; 
            margin-bottom: 28px; 
        }
        th { 
            font-family: 'Outfit', sans-serif;
            font-size: 10.5px; 
            font-weight: 700; 
            text-transform: uppercase; 
            letter-spacing: 0.1em; 
            color: var(--text-muted); 
            text-align: left; 
            padding: 8px 14px; 
            border-bottom: 2px solid var(--border); 
        }
        td { 
            font-size: 12.5px; 
            color: var(--text-main); 
            padding: 10px 14px; 
            border-bottom: 1px solid var(--border); 
            transition: background-color 0.2s ease;
        }
        tr:hover td {
            background-color: var(--bg-body);
        }
        .tag-pill { 
            display: inline-block; 
            padding: 3px 8px; 
            font-size: 10.5px; 
            font-weight: 600; 
            border-radius: 6px; 
            background-color: var(--bg-body); 
            color: var(--text-muted); 
        }
        .subtotal-row td { 
            border-bottom: none; 
            padding-top: 14px; 
        }
        .subtotal-row:hover td {
            background-color: transparent;
        }
        .subtotal-label { 
            font-family: 'Outfit', sans-serif;
            font-size: 14px; 
            font-weight: 700; 
            text-align: right; 
            color: var(--text-muted); 
        }
        .subtotal-value { 
            font-family: 'Outfit', sans-serif;
            font-size: 17px; 
            font-weight: 800; 
            color: var(--success); 
            text-align: right; 
            padding-right: 14px; 
        }

        .payment-box { 
            background-color: var(--bg-body); 
            border: 1px solid var(--border); 
            border-radius: 12px; 
            padding: 16px 20px; 
            page-break-inside: avoid; 
            break-inside: avoid; 
        }
        .payment-box-title { 
            font-family: 'Outfit', sans-serif;
            font-size: 12px; 
            font-weight: 700; 
            text-transform: uppercase; 
            color: var(--text-main); 
            margin-bottom: 8px; 
            letter-spacing: 0.05em;
        }
        .payment-content { 
            font-size: 12.5px; 
            color: var(--text-muted); 
            line-height: 1.5; 
            white-space: pre-wrap; 
        }
        .payment-flex-row {
            display: flex;
            flex-direction: row;
            flex-wrap: wrap;
            gap: 16px;
            width: 100%;
        }
        .payment-flex-row > * {
            flex: 1 1 280px;
            box-sizing: border-box;
        }

        .qr-codes-container { 
            display: flex; 
            flex-direction: row;
            flex-wrap: wrap;
            gap: 12px; 
            align-items: flex-start;
            justify-content: flex-start;
            page-break-inside: avoid; 
            break-inside: avoid; 
        }
        .qr-code-item { 
            display: flex; 
            flex-direction: column; 
            align-items: center; 
            background: #FFFFFF; 
            border: 1px solid var(--border); 
            border-radius: 8px; 
            padding: 6px; 
            box-shadow: 0 2px 8px rgba(0,0,0,0.03); 
            page-break-inside: avoid; 
            break-inside: avoid; 
        }
        .qr-code-image { 
            width: 140px; 
            height: 140px; 
            object-fit: contain; 
            border-radius: 4px; 
        }
        .qr-label {
            font-size: 9px;
            font-weight: 700;
            text-transform: uppercase;
            color: var(--text-muted);
            margin-top: 4px;
            letter-spacing: 0.05em;
        }

        .trust-banner {
            display: flex;
            align-items: center;
            gap: 8px;
            background: rgba(16, 185, 129, 0.08);
            border: 1px solid rgba(16, 185, 129, 0.2);
            color: var(--success);
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 600;
            width: 100%;
            box-sizing: border-box;
            justify-content: center;
            margin-top: 8px;
        }

        .invoice-footer { 
            margin-top: 24px; 
            text-align: center; 
            padding: 14px; 
        }
        .footer-link { 
            display: inline-flex; 
            align-items: center; 
            gap: 8px; 
            color: var(--text-muted); 
            text-decoration: none; 
            font-family: 'Outfit', sans-serif;
            font-size: 12.5px; 
            font-weight: 600; 
            transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1); 
            padding: 8px 16px; 
            border-radius: 8px; 
            background-color: var(--bg-body); 
            border: 1px solid var(--border);
        }
        .footer-link:hover { 
            background: linear-gradient(135deg, var(--accent-gradient-start) 0%, var(--accent-gradient-end) 100%);
            color: white; 
            border-color: transparent;
            transform: translateY(-1px); 
            box-shadow: 0 4px 12px rgba(79, 70, 229, 0.15); 
        }

        @page {
            size: auto;
            margin: 0; 
        }

        @media print { 
            * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
            body { background-color: white; padding: 8mm 12mm; margin: 0; font-size: 11px; } 
            .print-actions-bar { display: none; } 
            .invoice-container { border: none; box-shadow: none; padding: 0; width: 100%; max-width: 100%; } 
            .invoice-header-row { padding-bottom: 14px; margin-bottom: 14px; }
            .invoice-badge { font-size: 20px; margin-bottom: 4px; }
            .invoice-logo { max-height: 40px; margin-bottom: 4px; }
            .billed-to-container { margin-bottom: 12px; }
            .dashboard-grid { gap: 10px; margin-bottom: 14px; }
            .kpi-card { padding: 8px 12px; }
            .kpi-val { font-size: 16px; }
            table { margin-bottom: 14px; }
            th { padding: 6px 10px; }
            td { padding: 8px 10px; }
            .payment-box { padding: 10px 14px; }
            .qr-code-image { width: 140px; height: 140px; }
            .invoice-footer { margin-top: 14px; padding: 6px 0; }
            .footer-link { background: none; padding: 0; border: none; box-shadow: none; display: inline-flex; color: var(--accent); }
            .invoice-header-row, .billed-to-container, .dashboard-grid, table, .payment-box { page-break-inside: avoid; break-inside: avoid; }
        }
    </style>
</head>
<body class="theme-indigo">
    <div class="print-actions-bar">
        <div class="action-left-info">
            <div class="status-pill">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--success)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                    <polyline points="22 4 12 14.01 9 11.01"></polyline>
                </svg>
                <span>Invoice Generated</span>
            </div>
            <div class="theme-selector">
                <button class="theme-pill-btn active" data-theme="indigo" onclick="switchTheme('indigo')" title="Indigo Violet Theme"></button>
                <button class="theme-pill-btn" data-theme="teal" onclick="switchTheme('teal')" title="Emerald Teal Theme"></button>
                <button class="theme-pill-btn" data-theme="slate" onclick="switchTheme('slate')" title="Slate Charcoal Theme"></button>
            </div>
        </div>
        
        <button class="print-btn" onclick="window.print()">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="6 9 6 2 18 2 18 9"></polyline>
                <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"></path>
                <rect x="6" y="14" width="12" height="8"></rect>
            </svg>
            Print / Save PDF
        </button>
    </div>
    
    <div class="invoice-container">
        <div class="invoice-header-row">
            <div>
                {{LOGO_HTML}}
                <div class="profile-title">{{BUSINESS_NAME}}</div>
                <div class="profile-details">
                    {{BUSINESS_ADDRESS}}<br>
                    {{BUSINESS_CONTACT}}
                </div>
            </div>
            <div class="meta-column">
                <div class="invoice-badge">INVOICE</div>
                <div class="meta-item"><strong>Invoice No:</strong> {{INVOICE_NO}}</div>
                <div class="meta-item"><strong>Date:</strong> {{DATE}}</div>
                <div class="meta-item"><strong>Sessions:</strong> {{SESSIONS_COMPILED}}</div>
            </div>
        </div>
        
        <div class="billed-to-container">
            <div class="section-label">Billed To</div>
            <div class="client-name">{{CLIENT_NAME}}</div>
            <div class="client-address">{{CLIENT_ADDRESS}}</div>
            {{CLIENT_EMAILS_HTML}}
        </div>
        
        <div class="dashboard-grid">
            <div class="kpi-card">
                <div class="kpi-label">Total Work Hours</div>
                <div class="kpi-val">{{HOURS_COUNTED}} hrs</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">Total Amount Due</div>
                <div class="kpi-val amount-val">{{TOTAL_AMOUNT_DUE}}</div>
            </div>
        </div>
        
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
                <!-- {{ITEMS}} -->
                <tr class="subtotal-row">
                    <td colspan="4" class="subtotal-label">Grand Total:</td>
                    <td class="subtotal-value">{{GRAND_TOTAL}}</td>
                </tr>
            </tbody>
        </table>
        
        <div class="payment-box">
            <div class="payment-box-title">Payment Terms & Instructions</div>
            <div class="payment-content">{{PAYMENT_INSTRUCTIONS}}</div>
            <div class="payment-flex-row">
                {{BANK_DETAILS_HTML}}
                {{QR_HTML}}
            </div>
        </div>
        
        <div class="invoice-footer">
            <a href="https://mightyiest.github.io/TrueHour/" target="_blank" class="footer-link">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"></path>
                </svg>
                Powered by TrueHour - View on GitHub
            </a>
        </div>
    </div>

    <script>
        function switchTheme(themeName) {
            document.body.className = 'theme-' + themeName;
            document.querySelectorAll('.theme-pill-btn').forEach(btn => {
                btn.classList.toggle('active', btn.getAttribute('data-theme') === themeName);
            });
            try {
                localStorage.setItem('truehour-theme', themeName);
            } catch(e) {}
        }
        
        window.addEventListener('DOMContentLoaded', () => {
            try {
                const savedTheme = localStorage.getItem('truehour-theme') || 'indigo';
                switchTheme(savedTheme);
            } catch(e) {}
        });
    </script>
</body>
</html>"""

    template_html = get_cached_template(template_path, default_template)

    # Replace all placeholders in HTML template
    html = template_html
    html = html.replace("{{LOGO_HTML}}", logo_html)
    html = html.replace("{{BUSINESS_NAME}}", _esc(settings_data.get("business_name", "TrueHour Invoice")))
    html = html.replace("{{BUSINESS_ADDRESS}}", _esc(settings_data.get("business_address", "")))
    html = html.replace("{{BUSINESS_CONTACT}}", biz_contact_html)
    html = html.replace("{{INVOICE_NO}}", f"INV-{datetime.now().strftime('%Y%m%d%H%M')}")
    html = html.replace("{{DATE}}", datetime.now().strftime("%B %d, %Y"))
    html = html.replace("{{SESSIONS_COMPILED}}", str(billing_data.get("session_count", 1)))
    html = html.replace("{{CLIENT_NAME}}", _esc(settings_data.get("client_name", "Valued Client")))
    html = html.replace("{{CLIENT_ADDRESS}}", _esc(settings_data.get("client_address", "")))
    html = html.replace("{{CLIENT_EMAILS_HTML}}", client_emails_html)
    html = html.replace("{{HOURS_COUNTED}}", f"{hours_counted:.2f}")
    
    # Safely get total_earned_display with fallback calculation
    total_earned_display = billing_data.get("total_earned_display")
    if not total_earned_display:
        total_earned = billing_data.get("total_earned", 0.0)
        curr_sym = settings_data.get("currency_symbol", "$")
        total_earned_display = f"{curr_sym}{total_earned:,.2f}"
    
    html = html.replace("{{TOTAL_AMOUNT_DUE}}", _esc(total_earned_display))
    html = html.replace("{{GRAND_TOTAL}}", _esc(total_earned_display))
    html = html.replace("{{PAYMENT_INSTRUCTIONS}}", _esc(settings_data.get("business_payment", "Payment is due within 14 days of invoice date.")))
    html = html.replace("{{QR_HTML}}", qr_html)

    # Generate bank details block if any provided
    bank_holder = settings_data.get("bank_holder", "")
    bank_account = settings_data.get("bank_account", "")
    bank_routing = settings_data.get("bank_routing", "")
    bank_swift = settings_data.get("bank_swift", "")
    bank_name = settings_data.get("bank_name", "")
    bank_address = settings_data.get("bank_address", "")
    
    bank_details_html = ""
    if settings_data.get("enable_bank_details", True) and any([bank_holder, bank_account, bank_routing, bank_swift, bank_name, bank_address]):
        items = []
        if bank_holder:
            items.append(f"""
            <div class="bank-detail-item">
                <div style="font-size: 10px; font-weight: 700; text-transform: uppercase; color: var(--text-muted); letter-spacing: 0.05em;">Account Holder</div>
                <div style="font-size: 13px; font-weight: 600; color: var(--text-main); margin-top: 3px;">{_esc(bank_holder)}</div>
            </div>""")
        if bank_account:
            items.append(f"""
            <div class="bank-detail-item">
                <div style="font-size: 10px; font-weight: 700; text-transform: uppercase; color: var(--text-muted); letter-spacing: 0.05em;">Account Number</div>
                <div style="font-size: 13px; font-weight: 600; color: var(--text-main); margin-top: 3px;">{_esc(bank_account)}</div>
            </div>""")
        if bank_routing:
            items.append(f"""
            <div class="bank-detail-item">
                <div style="font-size: 10px; font-weight: 700; text-transform: uppercase; color: var(--text-muted); letter-spacing: 0.05em;">Routing Number</div>
                <div style="font-size: 13px; font-weight: 600; color: var(--text-main); margin-top: 3px;">{_esc(bank_routing)}</div>
            </div>""")
        if bank_swift:
            items.append(f"""
            <div class="bank-detail-item">
                <div style="font-size: 10px; font-weight: 700; text-transform: uppercase; color: var(--text-muted); letter-spacing: 0.05em;">SWIFT / BIC</div>
                <div style="font-size: 13px; font-weight: 600; color: var(--text-main); margin-top: 3px;">{_esc(bank_swift)}</div>
            </div>""")
        if bank_name or bank_address:
            bank_info_parts = []
            if bank_name:
                bank_info_parts.append(bank_name)
            if bank_address:
                bank_info_parts.append(bank_address)
            bank_info_str = ", ".join(bank_info_parts)
            items.append(f"""
            <div class="bank-detail-item" style="grid-column: span 2;">
                <div style="font-size: 10px; font-weight: 700; text-transform: uppercase; color: var(--text-muted); letter-spacing: 0.05em;">Bank Name & Address</div>
                <div style="font-size: 13px; font-weight: 600; color: var(--text-main); margin-top: 3px; line-height: 1.4;">{_esc(bank_info_str)}</div>
            </div>""")
            
        bank_details_html = f"""
        <div class="bank-details-box" style="margin-top: 14px; padding-top: 12px; border-top: 1px dashed var(--border);">
            <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: var(--accent); letter-spacing: 0.05em; margin-bottom: 8px;">Bank Transfer Details</div>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px 16px;">
                {"".join(items)}
            </div>
        </div>"""
        
    html = html.replace("{{BANK_DETAILS_HTML}}", bank_details_html)

    # Generate Itemized Rows
    items_html = ""
    for pb in billing_data.get("project_breakdown", []):
        cat_hours = pb["seconds"] / 3600.0
        tag_color = pb.get("color", "#64748B")
        pill_style = f"background-color: {tag_color}1a; color: {tag_color};" if tag_color != "#64748B" else ""
        items_html += f"""
                <tr>
                    <td style="font-weight: 600;"><span class="tag-pill" style="{pill_style}">{pb["project"]}</span></td>
                    <td>{pb["formatted"]}</td>
                    <td>{cat_hours:.2f}</td>
                    <td>{curr_sym}{hourly_rate:.2f}/hr</td>
                    <td>{pb["earned_display"]}</td>
                </tr>
        """

    # Replace items placeholder
    html = html.replace("<!-- {{ITEMS}} -->", items_html)
    html = html.replace("{{ITEMS}}", items_html)

    return html

def generate_session_report_html(report, hourly_rate=0.0, currency_symbol="$") -> str:
    """
    Generates a stunning, premium, modern A4 HTML session report.
    Optimized for high-fidelity web viewing and perfect browser-based PDF printing.
    Loads templates/report_template.html from disk, auto-creating it if missing.
    """
    import sys
    from html import escape as _esc
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        except Exception:
            base_dir = os.getcwd()

    templates_dir = os.path.join(base_dir, "templates")
    template_path = os.path.join(templates_dir, "report_template.html")

    # Define default template fallback
    default_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>TrueHour Session Report - {{SESSION_NAME}}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Outfit:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-body: #F8FAFC;
            --bg-card: #FFFFFF;
            --border: #E2E8F0;
            --text-main: #0F172A;
            --text-muted: #64748B;
            --text-light: #94A3B8;
            --card-shadow: 0 10px 40px -15px rgba(15, 23, 42, 0.04);
            --hover-shadow: 0 20px 40px -15px rgba(15, 23, 42, 0.08);

            --accent: #4F46E5;
            --accent-hover: #4338CA;
            --accent-gradient-start: #6366F1;
            --accent-gradient-end: #4F46E5;
            --success: #10B981;
            --warning: #F59E0B;
        }

        body.theme-indigo {
            --accent: #4F46E5;
            --accent-hover: #4338CA;
            --accent-gradient-start: #6366F1;
            --accent-gradient-end: #4F46E5;
            --success: #10B981;
        }
        body.theme-teal {
            --accent: #0D9488;
            --accent-hover: #0F766E;
            --accent-gradient-start: #14B8A6;
            --accent-gradient-end: #0D9488;
            --success: #10B981;
        }
        body.theme-slate {
            --accent: #334155;
            --accent-hover: #1E293B;
            --accent-gradient-start: #475569;
            --accent-gradient-end: #334155;
            --success: #059669;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { 
            font-family: 'Inter', system-ui, -apple-system, sans-serif; 
            background-color: var(--bg-body); 
            color: var(--text-main); 
            line-height: 1.6; 
            padding: 40px 20px; 
            display: flex; 
            flex-direction: column; 
            align-items: center;
            transition: background 0.3s ease;
        }
        
        .print-actions-bar { 
            width: 100%; 
            max-width: 900px; 
            background: rgba(255, 255, 255, 0.75); 
            backdrop-filter: blur(16px); 
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid rgba(226, 232, 240, 0.8); 
            border-radius: 16px; 
            padding: 14px 24px; 
            margin-bottom: 24px; 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
            box-shadow: var(--card-shadow);
        }
        .action-left-info {
            display: flex;
            align-items: center;
            gap: 16px;
        }
        .status-pill {
            font-size: 13px;
            font-weight: 600;
            color: var(--text-main);
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .theme-selector {
            display: flex;
            align-items: center;
            gap: 6px;
            background: #F1F5F9;
            padding: 4px;
            border-radius: 9999px;
            border: 1px solid var(--border);
        }
        .theme-pill-btn {
            border: none;
            width: 20px;
            height: 20px;
            border-radius: 50%;
            cursor: pointer;
            position: relative;
            transition: all 0.2s ease;
            box-shadow: inset 0 1px 3px rgba(0,0,0,0.1);
        }
        .theme-pill-btn:hover {
            transform: scale(1.15);
        }
        .theme-pill-btn.active::after {
            content: '';
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: white;
            box-shadow: 0 1px 2px rgba(0,0,0,0.3);
        }
        .theme-pill-btn[data-theme="indigo"] { background: linear-gradient(135deg, #6366F1, #4F46E5); }
        .theme-pill-btn[data-theme="teal"] { background: linear-gradient(135deg, #14B8A6, #0D9488); }
        .theme-pill-btn[data-theme="slate"] { background: linear-gradient(135deg, #475569, #334155); }

        .print-btn { 
            background: var(--accent-gradient-start);
            background: linear-gradient(135deg, var(--accent-gradient-start) 0%, var(--accent-gradient-end) 100%);
            color: white; 
            border: none; 
            padding: 10px 20px; 
            border-radius: 10px; 
            font-family: 'Outfit', sans-serif;
            font-size: 14px;
            font-weight: 600; 
            cursor: pointer; 
            display: inline-flex; 
            align-items: center; 
            gap: 8px; 
            transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1); 
            box-shadow: 0 4px 14px rgba(79, 70, 229, 0.15);
        }
        .print-btn:hover { 
            transform: translateY(-1.5px);
            box-shadow: 0 6px 20px rgba(79, 70, 229, 0.25);
        }

        .report-container { 
            width: 100%; 
            max-width: 900px; 
            background-color: var(--bg-card); 
            border: 1px solid var(--border); 
            border-radius: 24px; 
            padding: 60px; 
            box-shadow: var(--card-shadow); 
            transition: all 0.3s ease;
        }
        
        .report-header { 
            display: flex; 
            justify-content: space-between; 
            align-items: flex-start; 
            border-bottom: 2px solid var(--bg-body); 
            padding-bottom: 35px; 
            margin-bottom: 40px; 
        }
        .report-title-section { max-width: 60%; }
        .report-title-label { 
            font-family: 'Outfit', sans-serif;
            font-size: 11px; 
            font-weight: 700; 
            text-transform: uppercase; 
            color: var(--accent); 
            letter-spacing: 0.1em; 
            margin-bottom: 8px; 
        }
        .report-title { 
            font-family: 'Outfit', sans-serif;
            font-size: 32px; 
            font-weight: 800; 
            color: var(--text-main); 
            letter-spacing: -0.04em; 
            line-height: 1.25; 
        }
        .report-date { 
            font-size: 14px; 
            color: var(--text-muted); 
            margin-top: 8px; 
            font-weight: 500; 
        }
        
        .meta-column { text-align: right; }
        .app-badge { 
            font-family: 'Outfit', sans-serif;
            font-size: 26px; 
            font-weight: 800; 
            background: linear-gradient(135deg, var(--accent-gradient-start), var(--accent-gradient-end));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: -0.03em; 
            margin-bottom: 12px; 
        }
        .meta-item { 
            font-size: 13px; 
            color: var(--text-muted); 
            margin-bottom: 5px; 
            font-weight: 500; 
        }
        .meta-item strong { color: var(--text-main); }

        .dashboard-grid { 
            display: grid; 
            grid-template-columns: repeat(3, 1fr); 
            gap: 20px; 
            margin-bottom: 45px; 
        }
        .kpi-card { 
            background-color: var(--bg-body); 
            border: 1px solid transparent; 
            border-top: 4px solid var(--accent);
            border-radius: 16px; 
            padding: 22px 20px; 
            transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1); 
            position: relative; 
            overflow: hidden; 
        }
        .kpi-card:hover { 
            background-color: var(--bg-card); 
            border-color: var(--border); 
            border-top-color: var(--accent);
            transform: translateY(-2.5px); 
            box-shadow: var(--hover-shadow); 
        }
        .kpi-label { 
            font-size: 11px; 
            font-weight: 700; 
            text-transform: uppercase; 
            letter-spacing: 0.08em; 
            color: var(--text-muted); 
            margin-bottom: 6px; 
        }
        .kpi-val { 
            font-family: 'Outfit', sans-serif;
            font-size: 24px; 
            font-weight: 800; 
            color: var(--text-main); 
        }
        .kpi-card.productive { border-top-color: var(--accent); }
        .kpi-card.productive .kpi-val { color: var(--accent); }
        .kpi-card.ratio { border-top-color: var(--success); }
        .kpi-card.ratio .kpi-val { color: var(--success); }

        .section-header { 
            display: flex; 
            align-items: center; 
            justify-content: space-between; 
            margin-bottom: 24px; 
            padding-bottom: 10px; 
            border-bottom: 2px solid var(--bg-body); 
        }
        .section-title { 
            font-family: 'Outfit', sans-serif;
            font-size: 14px; 
            font-weight: 700; 
            text-transform: uppercase; 
            color: var(--text-main); 
            letter-spacing: 0.08em; 
        }

        .projects-container { 
            display: flex; 
            flex-direction: column; 
            gap: 20px; 
            margin-bottom: 45px; 
        }
        .project-row { display: flex; flex-direction: column; gap: 8px; }
        .project-info { display: flex; justify-content: space-between; font-size: 13px; font-weight: 600; }
        .project-name { 
            font-family: 'Outfit', sans-serif;
            color: var(--text-main); 
        }
        .project-stats { color: var(--text-muted); }
        .project-bar-bg { 
            width: 100%; 
            height: 10px; 
            background-color: var(--bg-body); 
            border-radius: 9999px; 
            overflow: hidden; 
            border: 1px solid var(--border);
        }
        .project-bar-fill { 
            height: 100%; 
            border-radius: 9999px; 
            transition: width 1s cubic-bezier(0.4, 0, 0.2, 1); 
        }

        table { 
            width: 100%; 
            border-collapse: collapse; 
            margin-bottom: 45px; 
        }
        th { 
            font-family: 'Outfit', sans-serif;
            font-size: 11px; 
            font-weight: 700; 
            text-transform: uppercase; 
            letter-spacing: 0.1em; 
            color: var(--text-muted); 
            text-align: left; 
            padding: 14px 20px; 
            border-bottom: 2px solid var(--border); 
        }
        td { 
            font-size: 13.5px; 
            color: var(--text-main); 
            padding: 15px 20px; 
            border-bottom: 1px solid var(--border); 
            transition: background-color 0.2s ease;
        }
        tr:hover td { background-color: var(--bg-body); }
        .tag-pill { 
            display: inline-block; 
            padding: 4px 10px; 
            font-size: 11px; 
            font-weight: 600; 
            border-radius: 8px; 
            background-color: var(--bg-body); 
            color: var(--text-muted); 
        }
        .app-icon { 
            width: 22px; 
            height: 22px; 
            border-radius: 6px; 
            vertical-align: middle; 
            margin-right: 10px; 
        }

        .timeline-list { 
            position: relative;
            display: flex; 
            flex-direction: column; 
            gap: 16px; 
            margin-bottom: 25px; 
            padding-left: 24px;
        }
        .timeline-list::before {
            content: '';
            position: absolute;
            left: 5px;
            top: 10px;
            bottom: 10px;
            width: 2px;
            background: var(--border);
        }
        .timeline-item { 
            position: relative;
            display: flex; 
            align-items: center; 
            background: var(--bg-body); 
            border-radius: 12px; 
            padding: 12px 20px; 
            border: 1px solid var(--border);
            border-left: 4px solid var(--accent); 
            transition: all 0.25s ease;
        }
        .timeline-item:hover {
            transform: translateX(4px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.03);
            background: var(--bg-card);
        }
        .timeline-item::before {
            content: '';
            position: absolute;
            left: -24px;
            top: 50%;
            transform: translate(-50%, -50%);
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background-color: var(--tag-color, var(--accent));
            border: 2px solid var(--bg-card);
            box-shadow: 0 0 0 2px var(--border);
            z-index: 2;
        }
        .timeline-time { 
            font-family: 'Outfit', sans-serif;
            font-size: 11.5px; 
            font-weight: 700; 
            color: var(--text-muted); 
            min-width: 200px; 
            white-space: nowrap; 
        }
        .timeline-app { 
            font-size: 13px; 
            font-weight: 600; 
            color: var(--text-main); 
            flex-grow: 1; 
        }
        .timeline-duration { 
            font-family: 'Outfit', sans-serif;
            font-size: 12px; 
            font-weight: 700; 
            color: var(--text-muted); 
            text-align: right; 
            white-space: nowrap; 
        }

        .report-footer { 
            text-align: center; 
            font-family: 'Outfit', sans-serif;
            font-size: 12.5px; 
            color: var(--text-muted); 
            border-top: 1px solid var(--border); 
            padding-top: 30px; 
            margin-top: 45px; 
            font-weight: 500; 
        }

        @media print { 
            body { background-color: white; padding: 0; } 
            .print-actions-bar { display: none; } 
            .report-container { border: none; box-shadow: none; padding: 0; max-width: 100%; } 
            .kpi-card { background-color: #F8FAFC !important; border: 1px solid #E2E8F0 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
            .project-bar-bg { background-color: #F8FAFC !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
            .project-bar-fill { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
            .timeline-item { background-color: #F8FAFC !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
        }
    </style>
</head>
<body class="theme-indigo">
    <div class="print-actions-bar">
        <div class="action-left-info">
            <div class="status-pill">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--success)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                    <polyline points="22 4 12 14.01 9 11.01"></polyline>
                </svg>
                <span>Report Compiled</span>
            </div>
            <div class="theme-selector">
                <button class="theme-pill-btn active" data-theme="indigo" onclick="switchTheme('indigo')" title="Indigo Violet Theme"></button>
                <button class="theme-pill-btn" data-theme="teal" onclick="switchTheme('teal')" title="Emerald Teal Theme"></button>
                <button class="theme-pill-btn" data-theme="slate" onclick="switchTheme('slate')" title="Slate Charcoal Theme"></button>
            </div>
        </div>
        
        <button class="print-btn" onclick="window.print()">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="6 9 6 2 18 2 18 9"></polyline>
                <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"></path>
                <rect x="6" y="14" width="12" height="8"></rect>
            </svg>
            Print / Save PDF
        </button>
    </div>
    
    <div class="report-container">
        <div class="report-header">
            <div class="report-title-section">
                <div class="report-title-label">Session Report</div>
                <div class="report-title">{{SESSION_NAME}}</div>
                <div class="report-date">{{DATE}}</div>
            </div>
            <div class="meta-column">
                <div class="app-badge">TrueHour</div>
                <div class="meta-item"><strong>Start:</strong> {{START_TIME}}</div>
                <div class="meta-item"><strong>End:</strong> {{END_TIME}}</div>
            </div>
        </div>

        <div class="dashboard-grid">
            <div class="kpi-card productive">
                <div class="kpi-label">Total Session Time</div>
                <div class="kpi-val">{{TOTAL_DURATION}}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">Productive (Counted) Time</div>
                <div class="kpi-val">{{PRODUCTIVE_DURATION}}</div>
            </div>
            <div class="kpi-card ratio">
                <div class="kpi-label">Productivity Ratio</div>
                <div class="kpi-val">{{PRODUCTIVITY_RATIO}}%</div>
            </div>
        </div>

        {{EARNINGS_HTML}}

        {{NEW_ACTIVITY_HTML}}

        <div class="section-header">
            <div class="section-title">Project & Category Breakdown</div>
        </div>
        <div class="projects-container">
            {{PROJECTS_VISUAL}}
        </div>

        <div class="section-header">
            <div class="section-title">Itemized Application Usage</div>
        </div>
        <table>
            <thead>
                <tr>
                    <th>Application</th>
                    <th>Project Category</th>
                    <th>Time Spent</th>
                    <th style="text-align: right;">Percentage</th>
                </tr>
            </thead>
            <tbody>
                {{APPS_TABLE_ROWS}}
            </tbody>
        </table>

        <div class="section-header">
            <div class="section-title">Detailed Timeline Activity</div>
        </div>
        <div class="timeline-list">
            {{TIMELINE_ITEMS}}
        </div>

        <div class="report-footer">
            Generated with TrueHour — Automated Time Tracking and Productivity Dashboard.
        </div>
    </div>

    <script>
        function switchTheme(themeName) {
            document.body.className = 'theme-' + themeName;
            document.querySelectorAll('.theme-pill-btn').forEach(btn => {
                btn.classList.toggle('active', btn.getAttribute('data-theme') === themeName);
            });
            try {
                localStorage.setItem('truehour-theme', themeName);
            } catch(e) {}
        }
        
        window.addEventListener('DOMContentLoaded', () => {
            try {
                const savedTheme = localStorage.getItem('truehour-theme') || 'indigo';
                switchTheme(savedTheme);
            } catch(e) {}
        });
    </script>
</body>
</html>"""

    template_html = get_cached_template(template_path, default_template)

    total_secs = report.get("total_seconds", 0)
    counted_secs = report.get("counted_seconds", 0)
    ratio = (counted_secs / total_secs * 100.0) if total_secs > 0 else 0.0

    # Earnings logic
    earnings_html = ""
    if hourly_rate > 0:
        total_earned = (counted_secs / 3600.0) * hourly_rate
        total_earned_display = f"{currency_symbol}{total_earned:,.2f}"
        earnings_html = f"""
        <div class="section-header">
            <div class="section-title">Billing & Estimated Earnings</div>
        </div>
        <div class="dashboard-grid" style="grid-template-columns: 1fr 1fr; margin-bottom: 40px;">
            <div class="kpi-card">
                <div class="kpi-label">Hourly Rate</div>
                <div class="kpi-val">{currency_symbol}{hourly_rate:.2f}/hr</div>
            </div>
            <div class="kpi-card productive">
                <div class="kpi-label">Total Earned</div>
                <div class="kpi-val" style="color: var(--success);">{total_earned_display}</div>
            </div>
        </div>
        """

    # New Activity logic for resumed sessions
    new_activity_html = ""
    new_activity = [a for a in report.get("new_activity", []) if not a.get("excluded", False)]
    if new_activity:
        rows_html = ""
        for a in new_activity:
            raw_tag = a.get("tag", "Unassigned")
            tag_color = get_project_color(raw_tag)
            pill_style = f"background-color: {tag_color}1a; color: {tag_color};" if tag_color != "#64748B" else ""
            escaped_name = _esc(a['name'])
            escaped_tag = _esc(raw_tag)
            initial = _esc(a['name'][0].upper()) if a['name'] else "?"
            icon_html = f"""<svg class="app-icon" style="vertical-align: middle; margin-right: 8px;" width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect width="24" height="24" rx="6" fill="{tag_color}1a"/>
                <text x="12" y="16" fill="{tag_color}" font-size="12" font-weight="800" font-family="Inter, system-ui, sans-serif" text-anchor="middle">{initial}</text>
            </svg>"""
            
            rows_html += f"""
            <tr>
                <td style="font-weight: 600;">{icon_html}{escaped_name}</td>
                <td><span class="tag-pill" style="{pill_style}">{escaped_tag}</span></td>
                <td>{a['previous_formatted']}</td>
                <td style="color: var(--success); font-weight: 600;">+{a['new_formatted']}</td>
                <td style="text-align: right; font-weight: 600;">{a['total_formatted']}</td>
            </tr>
            """
        new_activity_html = f"""
        <div class="section-header">
            <div class="section-title">New Activity (Resumed Session)</div>
        </div>
        <table>
            <thead>
                <tr>
                    <th>Application</th>
                    <th>Project Category</th>
                    <th>Previous Time</th>
                    <th>New Time Added</th>
                    <th style="text-align: right;">Total Time</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
        """

    # Projects visual
    projects_visual = ""
    for pb in report.get("project_breakdown", []):
        pct = pb.get("percent", 0.0)
        color = pb.get("color", "#4F46E5")
        projects_visual += f"""
        <div class="project-row">
            <div class="project-info">
                <span class="project-name">{pb['project']}</span>
                <span class="project-stats">{pb['formatted']} ({pct:.1f}%)</span>
            </div>
            <div class="project-bar-bg">
                <div class="project-bar-fill" style="width: {pct:.1f}%; background: linear-gradient(90deg, {color} 0%, {color}cc 100%);"></div>
            </div>
        </div>
        """

    # Applications rows
    apps_rows = ""
    app_exe_paths = report.get("app_exe_paths", {})
    for app in report.get("apps", []):
        if app.get("excluded", False):
            continue
        pct = app.get("percent", 0.0)
        raw_tag = app.get("tag", "Unassigned")
        tag_color = get_project_color(raw_tag)
        pill_style = f"background-color: {tag_color}1a; color: {tag_color};" if tag_color != "#64748B" else ""
        escaped_app_name = _esc(app['name'])
        escaped_tag = _esc(raw_tag)
        
        # Clean background-friendly bypass for local icon extraction
        local_b64 = ""
        
        # Mappings for premium online SVG icons via Simple Icons CDN
        app_name_lower = app['name'].lower().strip()
        simple_icons = {
            "vs code": "visualstudiocode",
            "vscode": "visualstudiocode",
            "visual studio": "visualstudio",
            "figma": "figma",
            "notion": "notion",
            "chrome": "googlechrome",
            "google chrome": "googlechrome",
            "edge": "microsoftedge",
            "microsoft edge": "microsoftedge",
            "firefox": "mozillafirefox",
            "safari": "safari",
            "slack": "slack",
            "discord": "discord",
            "spotify": "spotify",
            "photoshop": "adobephotoshop",
            "illustrator": "adobeillustrator",
            "premiere": "adobepremierepro",
            "blender": "blender",
            "word": "microsoftword",
            "excel": "microsoftexcel",
            "powerpoint": "microsoftpowerpoint",
            "teams": "microsoftteams",
            "zoom": "zoom",
            "github": "github",
            "python": "python",
            "node": "nodedotjs",
            "trello": "trello",
            "jira": "jira",
            "asana": "asana",
            "clickup": "clickup",
            "whatsapp": "whatsapp",
            "telegram": "telegram",
            "outlook": "microsoftoutlook",
            "sublime": "sublimetext",
            "docker": "docker",
            "postman": "postman",
            "canva": "canva",
        }
        
        slug = None
        for key, value in simple_icons.items():
            if key in app_name_lower:
                slug = value
                break
                
        icon_html = ""
        if slug:
            # Multi-layered fallback sources if a service is blocked or down:
            # 1. cdn.simpleicons.org (customizable colors)
            # 2. jsDelivr NPM CDN (Enterprise Cloudflare/Fastly backed)
            # 3. Unpkg CDN
            # 4. Local extracted base64 or Category-colored letter SVG
            
            if local_b64:
                fallback_src = f"data:image/png;base64,{local_b64}"
            else:
                initial = _esc(app['name'][0].upper()) if app['name'] else "?"
                fallback_src = f"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' width='20' height='20'><rect width='24' height='24' rx='6' fill='{tag_color.replace('#', '%23')}1a'/><text x='12' y='16' fill='{tag_color.replace('#', '%23')}' font-size='12' font-weight='800' font-family='sans-serif' text-anchor='middle'>{initial}</text></svg>"
            
            # Escape quotes safely for HTML attributes
            escaped_fallback = fallback_src.replace("'", "\\'")
            
            icon_html = f"""<img src="https://cdn.simpleicons.org/{slug}" class="app-icon" onerror="this.onerror=function(){{ this.onerror=function(){{ this.onerror=null; this.src='{escaped_fallback}'; }}; this.src='https://unpkg.com/simple-icons@11.13.0/icons/{slug}.svg'; }}; this.src='https://cdn.jsdelivr.net/npm/simple-icons@11.13.0/icons/{slug}.svg';" />"""
        elif local_b64:
            # Use local base64 extracted exe icon
            icon_html = f'<img src="data:image/png;base64,{local_b64}" class="app-icon" />'
        else:
            # High-fidelity category-colored letter-initial SVG vector (completely offline & local)
            initial = _esc(app['name'][0].upper()) if app['name'] else "?"
            icon_html = f"""<svg class="app-icon" style="vertical-align: middle; margin-right: 8px;" width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect width="24" height="24" rx="6" fill="{tag_color}1a"/>
                <text x="12" y="16" fill="{tag_color}" font-size="12" font-weight="800" font-family="Inter, system-ui, sans-serif" text-anchor="middle">{initial}</text>
            </svg>"""
        
        apps_rows += f"""
        <tr>
            <td style="font-weight: 600;">{icon_html}{escaped_app_name}</td>
            <td><span class="tag-pill" style="{pill_style}">{escaped_tag}</span></td>
            <td>{app['formatted']}</td>
            <td style="text-align: right; font-weight: 600;">{pct:.1f}%</td>
        </tr>
        """

    # Timeline list
    timeline_items = ""
    timeline_entries = report.get("timeline", [])
    capped_timeline = timeline_entries[:15]
    
    # Pre-compile app category mappings in O(N) to allow O(1) lookups inside loop
    app_tags = {app["name"]: app.get("tag", "Unassigned") for app in report.get("apps", [])}
    
    for t in capped_timeline:
        t_start = t["start"]
        t_end = t["end"]
        
        start_str = t_start.strftime("%I:%M:%S %p") if hasattr(t_start, "strftime") else str(t_start)
        end_str = t_end.strftime("%I:%M:%S %p") if hasattr(t_end, "strftime") else str(t_end)
        
        app_name = t.get("app", "Active Session")
        app_tag = app_tags.get(app_name, "Unassigned")
        tag_color = get_project_color(app_tag)
        
        duration_secs = 0
        if hasattr(t_start, "timestamp") and hasattr(t_end, "timestamp"):
            duration_secs = int(t_end.timestamp() - t_start.timestamp())
        duration_str = format_duration(duration_secs) if duration_secs > 0 else ""
        
        escaped_app_name = _esc(app_name)
        escaped_app_tag = _esc(app_tag)
        timeline_items += f"""
        <div class="timeline-item" style="border-left-color: {tag_color}; --tag-color: {tag_color};">
            <span class="timeline-time">{start_str} - {end_str}</span>
            <span class="timeline-app">{escaped_app_name} <span style="font-weight: normal; color: var(--text-muted); font-size: 11px;">({escaped_app_tag})</span></span>
            <span class="timeline-duration">{duration_str}</span>
        </div>
        """

    if len(timeline_entries) > 15:
        timeline_items += f"""
        <div style="text-align: center; font-size: 12px; color: var(--text-muted); font-weight: 600; padding: 12px; border: 1px dashed var(--border); border-radius: 8px; margin-top: 10px; background-color: var(--bg-body);">
            ... and {len(timeline_entries) - 15} more activity segments in this session.
        </div>
        """

    # Replacements
    html = template_html
    html = html.replace("{{SESSION_NAME}}", _esc(report.get("session_name", "Unnamed Session")))
    html = html.replace("{{DATE}}", _esc(report.get("date_display", report.get("date", ""))))
    html = html.replace("{{START_TIME}}", _esc(report.get("start_display", report.get("start", ""))))
    html = html.replace("{{END_TIME}}", _esc(report.get("end_display", report.get("end", ""))))
    html = html.replace("{{TOTAL_DURATION}}", report.get("total_formatted", format_duration(total_secs)))
    html = html.replace("{{PRODUCTIVE_DURATION}}", report.get("counted_formatted", format_duration(counted_secs)))
    html = html.replace("{{PRODUCTIVITY_RATIO}}", f"{ratio:.1f}")
    html = html.replace("{{EARNINGS_HTML}}", earnings_html)
    html = html.replace("{{NEW_ACTIVITY_HTML}}", new_activity_html)
    html = html.replace("{{PROJECTS_VISUAL}}", projects_visual)
    html = html.replace("{{APPS_TABLE_ROWS}}", apps_rows)
    html = html.replace("{{TIMELINE_ITEMS}}", timeline_items)

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
