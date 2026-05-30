import os
import glob
import json
import sqlite3
from datetime import datetime
from database.schema import get_connection
from config import get_app_data_dir

def get_sessions_for_date(date_str: str):
    """Scan sessions/ and autosave/ to get all unique sessions for a specific date."""
    sessions_folder = os.path.join(get_app_data_dir(), "sessions")
    autosave_folder = os.path.join(get_app_data_dir(), "autosave")
    
    unique_sessions = {}
    for folder in [autosave_folder, sessions_folder]:
        if not os.path.exists(folder):
            continue
        for filepath in glob.glob(os.path.join(folder, "*.json")):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # Check date
                s_date = data.get("date")
                if s_date != date_str:
                    continue
                    
                start_str = data.get("start")
                if not start_str:
                    continue
                    
                key = (s_date, start_str)
                total_secs = data.get("total_seconds", 0)
                
                if key in unique_sessions:
                    existing_total = unique_sessions[key].get("total_seconds", 0)
                    if total_secs > existing_total:
                        unique_sessions[key] = data
                else:
                    unique_sessions[key] = data
            except Exception:
                continue
    return list(unique_sessions.values())

def update_daily_summary(session_or_date):
    """
    Recalculates and updates the daily summary for a given date or a session dict's date.
    Called when a session is stopped, edited, or deleted.
    """
    if isinstance(session_or_date, dict):
        date_str = session_or_date.get("date")
    else:
        date_str = str(session_or_date)
        
    if not date_str:
        return
        
    sessions = get_sessions_for_date(date_str)
    
    total_seconds = 0
    session_count = len(sessions)
    active_projects_set = set()
    longest_session = 0
    
    for s in sessions:
        total_seconds += s.get("total_seconds", 0)
        longest_session = max(longest_session, s.get("total_seconds", 0))
        for app in s.get("apps", []):
            if not app.get("excluded", False):
                active_projects_set.add(app.get("tag", "Unassigned"))
                
    active_projects = len(active_projects_set)
    updated_at = datetime.now().isoformat()
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO daily_summary (date, total_seconds, session_count, active_projects, longest_session, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                total_seconds=excluded.total_seconds,
                session_count=excluded.session_count,
                active_projects=excluded.active_projects,
                longest_session=excluded.longest_session,
                updated_at=excluded.updated_at
        """, (date_str, total_seconds, session_count, active_projects, longest_session, updated_at))
        conn.commit()
    finally:
        conn.close()

def rebuild_all_summaries():
    """Scan all session files, rebuild daily summary database from scratch."""
    sessions_folder = os.path.join(get_app_data_dir(), "sessions")
    autosave_folder = os.path.join(get_app_data_dir(), "autosave")
    
    # Get all unique dates
    dates = set()
    for folder in [autosave_folder, sessions_folder]:
        if not os.path.exists(folder):
            continue
        for filepath in glob.glob(os.path.join(folder, "*.json")):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                d = data.get("date")
                if d:
                    dates.add(d)
            except Exception:
                continue
                
    for d in dates:
        update_daily_summary(d)
