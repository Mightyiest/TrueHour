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

    # Create Invoices Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS invoices (
        invoice_no TEXT PRIMARY KEY,
        client_name TEXT,
        amount REAL,
        currency TEXT,
        status TEXT DEFAULT 'unpaid',
        session_files TEXT,
        billing_data TEXT,
        settings_data TEXT,
        created_at TEXT,
        updated_at TEXT
    );
    """)

    conn.commit()
    conn.close()

def save_invoice(invoice_no, client_name, amount, currency, status, session_files, billing_data, settings_data):
    import json
    from datetime import datetime
    now = datetime.now().isoformat()
    conn = get_connection()
    try:
        conn.execute("""
        INSERT OR REPLACE INTO invoices (
            invoice_no, client_name, amount, currency, status,
            session_files, billing_data, settings_data, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            invoice_no, client_name, amount, currency, status,
            json.dumps(session_files), json.dumps(billing_data), json.dumps(settings_data),
            now, now
        ))
        conn.commit()
    finally:
        conn.close()

def get_all_invoices():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM invoices ORDER BY created_at DESC;")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def get_invoices_list():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT invoice_no, client_name, amount, currency, status, created_at FROM invoices ORDER BY created_at DESC;")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def get_invoice_by_no(invoice_no):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM invoices WHERE invoice_no = ?;", (invoice_no,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def update_invoice_status(invoice_no, status):
    from datetime import datetime
    now = datetime.now().isoformat()
    conn = get_connection()
    try:
        conn.execute("""
        UPDATE invoices SET status = ?, updated_at = ? WHERE invoice_no = ?;
        """, (status, now, invoice_no))
        conn.commit()
    finally:
        conn.close()

def delete_invoice(invoice_no):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM invoices WHERE invoice_no = ?;", (invoice_no,))
        conn.commit()
    finally:
        conn.close()

def rename_invoice(old_no, new_no):
    from datetime import datetime
    now = datetime.now().isoformat()
    conn = get_connection()
    try:
        conn.execute("""
        UPDATE invoices SET invoice_no = ?, updated_at = ? WHERE invoice_no = ?;
        """, (new_no, now, old_no))
        conn.commit()
    finally:
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

