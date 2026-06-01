import os
import glob
import json
from datetime import datetime
from database.schema import get_connection
from config import get_app_data_dir

def get_daily_summaries(start_date_str: str, end_date_str: str):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT date, total_seconds, session_count, active_projects, longest_session, updated_at
            FROM daily_summary
            WHERE date BETWEEN ? AND ?
            ORDER BY date ASC
        """, (start_date_str, end_date_str))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def calculate_total_hours(days):
    return sum(day["total_seconds"] for day in days) / 3600.0

def calculate_average_hours(days):
    if not days:
        return 0.0
    return calculate_total_hours(days) / len(days)

def calculate_most_active_day(days):
    if not days:
        return None
    max_day = max(days, key=lambda x: x["total_seconds"])
    if max_day["total_seconds"] == 0:
        return None
    return max_day["date"]

def calculate_longest_session(days):
    if not days:
        return 0
    return max(day["longest_session"] for day in days)

def calculate_project_breakdown(start_date_str: str, end_date_str: str):
    """
    Load sessions only for dates that have registered activity according to summaries.
    This avoids scanning the filesystem blindly.
    """
    days = get_daily_summaries(start_date_str, end_date_str)
    active_dates = [day["date"] for day in days if day["session_count"] > 0]
    
    project_times = {}
    total_seconds = 0
    
    sessions_folder = os.path.join(get_app_data_dir(), "sessions")
    autosave_folder = os.path.join(get_app_data_dir(), "autosave")
    
    for date_str in active_dates:
        # Load unique sessions for this date
        unique_sessions = {}
        
        # First, collect all finalized session keys to ignore orphaned/discarded autosaves
        finalized_keys = set()
        if os.path.exists(sessions_folder):
            for filepath in glob.glob(os.path.join(sessions_folder, f"*{date_str}*.json")) + glob.glob(os.path.join(sessions_folder, "*.json")):
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if data.get("date") != date_str:
                        continue
                    start_str = data.get("start")
                    if start_str:
                        finalized_keys.add((date_str, start_str))
                        key = (date_str, start_str)
                        unique_sessions[key] = data
                except Exception:
                    continue

        # Scan autosave folder, including autosaves of finalized sessions (to keep most complete data) and unfinalized recovery sessions
        if os.path.exists(autosave_folder):
            for filepath in glob.glob(os.path.join(autosave_folder, f"*{date_str}*.json")) + glob.glob(os.path.join(autosave_folder, "*.json")):
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if data.get("date") != date_str:
                        continue
                    start_str = data.get("start")
                    if not start_str:
                        continue
                    key = (date_str, start_str)
                    total_secs = data.get("total_seconds", 0)
                    if key in unique_sessions:
                        existing_total = unique_sessions[key].get("total_seconds", 0)
                        if total_secs > existing_total:
                            unique_sessions[key] = data
                    else:
                        unique_sessions[key] = data
                except Exception:
                    continue
                    
        for s in unique_sessions.values():
            total_seconds += s.get("total_seconds", 0)
            for app in s.get("apps", []):
                if not app.get("excluded", False):
                    tag = app.get("tag", "Unassigned")
                    secs = app.get("seconds", 0)
                    project_times[tag] = project_times.get(tag, 0) + secs
                    
    breakdown = []
    for proj, secs in project_times.items():
        pct = (secs / total_seconds * 100.0) if total_seconds > 0 else 0
        breakdown.append({
            "project": proj,
            "seconds": secs,
            "percent": round(pct, 1)
        })
    breakdown.sort(key=lambda x: x["seconds"], reverse=True)
    return breakdown
