import os
import sqlite3
from config import get_app_data_dir

def get_db_path() -> str:
    return os.path.join(get_app_data_dir(), "truehour.db")

def get_connection():
    db_path = get_db_path()
    conn = sqlite3.connect(db_path, timeout=30.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except Exception:
        pass
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Create Daily Summary Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_summary (
        date TEXT PRIMARY KEY,
        total_seconds INTEGER NOT NULL DEFAULT 0,
        session_count INTEGER NOT NULL DEFAULT 0,
        active_projects INTEGER NOT NULL DEFAULT 0,
        longest_session INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT
    );
    """)
    
    # Create Report Job Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS report_jobs (
        id TEXT PRIMARY KEY,
        status TEXT,
        progress INTEGER,
        report_type TEXT,
        start_date TEXT,
        end_date TEXT,
        output_path TEXT,
        error_message TEXT,
        created_at TEXT,
        completed_at TEXT
    );
    """)
    
    # Create Schema Version Metadata Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS schema_meta (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    """)
    
    # Insert initial schema version
    cursor.execute("INSERT OR IGNORE INTO schema_meta (key, value) VALUES ('version', '1');")
    
    conn.commit()
    conn.close()

def optimize_db():
    """Runs vacuum and analyze/optimization pragma to clean up fragmentation and optimize query planner."""
    conn = get_connection()
    try:
        conn.execute("PRAGMA optimize;")
        conn.execute("VACUUM;")
        conn.commit()
    except Exception as e:
        print(f"[TrueHour] Database optimization failed: {e}")
    finally:
        conn.close()

# Initialize when imported
init_db()

