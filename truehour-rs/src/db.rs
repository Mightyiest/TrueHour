use crate::config::ProfilePaths;
use chrono::Local;
use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::Path;
use std::time::Duration;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DailySummaryRow {
    pub date: String,
    pub total_seconds: i64,
    pub session_count: i64,
    pub active_projects: i64,
    pub longest_session: i64,
    pub updated_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InvoiceListItem {
    pub invoice_no: String,
    pub client_name: String,
    pub amount: f64,
    pub currency: String,
    pub status: String,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InvoiceRecord {
    pub invoice_no: String,
    pub client_name: String,
    pub amount: f64,
    pub currency: String,
    pub status: String,
    pub session_files: String,
    pub billing_data: String,
    pub settings_data: String,
    pub created_at: String,
    pub updated_at: String,
}

pub fn open_connection(db_path: &Path) -> rusqlite::Result<Connection> {
    if let Some(parent) = db_path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    let conn = Connection::open(db_path)?;
    conn.busy_timeout(Duration::from_millis(5000))?;
    conn.pragma_update(None, "journal_mode", "WAL")?;
    conn.pragma_update(None, "synchronous", "NORMAL")?;
    Ok(conn)
}

pub fn init_schema(conn: &Connection) -> rusqlite::Result<()> {
    conn.execute_batch(
        r#"
        CREATE TABLE IF NOT EXISTS daily_summary (
            date TEXT PRIMARY KEY,
            total_seconds INTEGER NOT NULL DEFAULT 0,
            session_count INTEGER NOT NULL DEFAULT 0,
            active_projects INTEGER NOT NULL DEFAULT 0,
            longest_session INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT
        );

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

        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        INSERT OR IGNORE INTO schema_meta (key, value) VALUES ('version', '1');

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
        "#,
    )?;
    Ok(())
}

pub fn init_database(paths: &ProfilePaths) -> rusqlite::Result<()> {
    let conn = open_connection(&paths.db_file)?;
    init_schema(&conn)
}

fn read_json_file(path: &Path) -> Option<Value> {
    let raw = fs::read_to_string(path).ok()?;
    serde_json::from_str(raw.trim_start_matches('\u{feff}')).ok()
}

/// Mirrors `core/reporting/aggregator.py:get_sessions_for_date(date_str)`.
pub fn get_sessions_for_date(paths: &ProfilePaths, date_str: &str) -> Vec<Value> {
    let mut unique_sessions: HashMap<(String, String), Value> = HashMap::new();
    let mut finalized_keys: HashSet<(String, String)> = HashSet::new();

    if paths.sessions_dir.exists() {
        if let Ok(entries) = fs::read_dir(&paths.sessions_dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.extension().and_then(|e| e.to_str()) != Some("json") {
                    continue;
                }
                if let Some(data) = read_json_file(&path) {
                    let s_date = data.get("date").and_then(|v| v.as_str()).unwrap_or("");
                    if s_date != date_str {
                        continue;
                    }
                    let start_str = data.get("start").and_then(|v| v.as_str()).unwrap_or("");
                    if !start_str.is_empty() {
                        let key = (s_date.to_string(), start_str.to_string());
                        finalized_keys.insert(key.clone());
                        unique_sessions.insert(key, data);
                    }
                }
            }
        }
    }

    if paths.autosave_dir.exists() {
        if let Ok(entries) = fs::read_dir(&paths.autosave_dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.extension().and_then(|e| e.to_str()) != Some("json") {
                    continue;
                }
                if let Some(data) = read_json_file(&path) {
                    let s_date = data.get("date").and_then(|v| v.as_str()).unwrap_or("");
                    if s_date != date_str {
                        continue;
                    }
                    let start_str = data.get("start").and_then(|v| v.as_str()).unwrap_or("");
                    if start_str.is_empty() {
                        continue;
                    }
                    let key = (s_date.to_string(), start_str.to_string());
                    if finalized_keys.contains(&key) {
                        let total_secs =
                            data.get("total_seconds").and_then(|v| v.as_i64()).unwrap_or(0);
                        let existing_total = unique_sessions
                            .get(&key)
                            .and_then(|v| v.get("total_seconds"))
                            .and_then(|v| v.as_i64())
                            .unwrap_or(0);
                        if total_secs > existing_total {
                            unique_sessions.insert(key, data);
                        }
                    }
                }
            }
        }
    }

    unique_sessions.into_values().collect()
}

fn compute_summary_metrics(sessions: &[Value]) -> (i64, i64, i64, i64) {
    let mut total_seconds: i64 = 0;
    let session_count: i64 = sessions.len() as i64;
    let mut active_projects: HashSet<String> = HashSet::new();
    let mut longest_session: i64 = 0;

    for s in sessions {
        let secs = s.get("total_seconds").and_then(|v| v.as_i64()).unwrap_or(0);
        total_seconds += secs;
        if secs > longest_session {
            longest_session = secs;
        }
        if let Some(apps) = s.get("apps").and_then(|v| v.as_array()) {
            for app in apps {
                let excluded = app.get("excluded").and_then(|v| v.as_bool()).unwrap_or(false);
                if !excluded {
                    let tag = app
                        .get("tag")
                        .and_then(|v| v.as_str())
                        .unwrap_or("Unassigned");
                    active_projects.insert(tag.to_string());
                }
            }
        }
    }

    (
        total_seconds,
        session_count,
        active_projects.len() as i64,
        longest_session,
    )
}

pub fn update_daily_summary(paths: &ProfilePaths, date_str: &str) -> rusqlite::Result<()> {
    if date_str.trim().is_empty() {
        return Ok(());
    }
    let sessions = get_sessions_for_date(paths, date_str);
    let (total_seconds, session_count, active_projects, longest_session) =
        compute_summary_metrics(&sessions);
    let updated_at = Local::now().format("%Y-%m-%dT%H:%M:%S%.6f").to_string();

    let conn = open_connection(&paths.db_file)?;
    init_schema(&conn)?;
    conn.execute(
        r#"
        INSERT INTO daily_summary (date, total_seconds, session_count, active_projects, longest_session, updated_at)
        VALUES (?1, ?2, ?3, ?4, ?5, ?6)
        ON CONFLICT(date) DO UPDATE SET
            total_seconds = excluded.total_seconds,
            session_count = excluded.session_count,
            active_projects = excluded.active_projects,
            longest_session = excluded.longest_session,
            updated_at = excluded.updated_at
        "#,
        params![
            date_str,
            total_seconds,
            session_count,
            active_projects,
            longest_session,
            updated_at,
        ],
    )?;
    Ok(())
}

pub fn rebuild_all_summaries(paths: &ProfilePaths, force: bool) -> rusqlite::Result<()> {
    let mut conn = open_connection(&paths.db_file)?;
    init_schema(&conn)?;

    let existing_count: i64 =
        conn.query_row("SELECT COUNT(*) FROM daily_summary", [], |row| row.get(0))?;
    if existing_count > 0 && !force {
        return Ok(());
    }

    let mut sessions_by_date: HashMap<String, HashMap<(String, String), Value>> = HashMap::new();
    let mut finalized_keys: HashSet<(String, String)> = HashSet::new();

    if paths.sessions_dir.exists() {
        if let Ok(entries) = fs::read_dir(&paths.sessions_dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.extension().and_then(|e| e.to_str()) != Some("json") {
                    continue;
                }
                if let Some(data) = read_json_file(&path) {
                    let s_date = data.get("date").and_then(|v| v.as_str()).unwrap_or("");
                    let start_str = data.get("start").and_then(|v| v.as_str()).unwrap_or("");
                    if !s_date.is_empty() && !start_str.is_empty() {
                        let key = (s_date.to_string(), start_str.to_string());
                        finalized_keys.insert(key.clone());
                        sessions_by_date
                            .entry(s_date.to_string())
                            .or_default()
                            .insert(key, data);
                    }
                }
            }
        }
    }

    if paths.autosave_dir.exists() {
        if let Ok(entries) = fs::read_dir(&paths.autosave_dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.extension().and_then(|e| e.to_str()) != Some("json") {
                    continue;
                }
                if let Some(data) = read_json_file(&path) {
                    let s_date = data.get("date").and_then(|v| v.as_str()).unwrap_or("");
                    let start_str = data.get("start").and_then(|v| v.as_str()).unwrap_or("");
                    if !s_date.is_empty() && !start_str.is_empty() {
                        let key = (s_date.to_string(), start_str.to_string());
                        if finalized_keys.contains(&key) {
                            let map = sessions_by_date.entry(s_date.to_string()).or_default();
                            let total_secs =
                                data.get("total_seconds").and_then(|v| v.as_i64()).unwrap_or(0);
                            let existing_total = map
                                .get(&key)
                                .and_then(|v| v.get("total_seconds"))
                                .and_then(|v| v.as_i64())
                                .unwrap_or(0);
                            if total_secs > existing_total {
                                map.insert(key, data);
                            }
                        }
                    }
                }
            }
        }
    }

    let updated_at = Local::now().format("%Y-%m-%dT%H:%M:%S%.6f").to_string();
    let tx = conn.transaction()?;
    if force {
        tx.execute("DELETE FROM daily_summary", [])?;
    }
    {
        let mut stmt = tx.prepare(
            r#"
            INSERT INTO daily_summary (date, total_seconds, session_count, active_projects, longest_session, updated_at)
            VALUES (?1, ?2, ?3, ?4, ?5, ?6)
            ON CONFLICT(date) DO UPDATE SET
                total_seconds = excluded.total_seconds,
                session_count = excluded.session_count,
                active_projects = excluded.active_projects,
                longest_session = excluded.longest_session,
                updated_at = excluded.updated_at
            "#,
        )?;
        for (date_str, map) in sessions_by_date {
            let list: Vec<Value> = map.into_values().collect();
            let (total_seconds, session_count, active_projects, longest_session) =
                compute_summary_metrics(&list);
            stmt.execute(params![
                date_str,
                total_seconds,
                session_count,
                active_projects,
                longest_session,
                updated_at,
            ])?;
        }
    }
    tx.commit()?;
    Ok(())
}

pub fn get_daily_summary(
    paths: &ProfilePaths,
    date_str: &str,
) -> rusqlite::Result<Option<DailySummaryRow>> {
    let conn = open_connection(&paths.db_file)?;
    init_schema(&conn)?;
    let mut stmt = conn.prepare(
        "SELECT date, total_seconds, session_count, active_projects, longest_session, COALESCE(updated_at, '') FROM daily_summary WHERE date = ?1",
    )?;
    let mut rows = stmt.query_map(params![date_str], |row| {
        Ok(DailySummaryRow {
            date: row.get(0)?,
            total_seconds: row.get(1)?,
            session_count: row.get(2)?,
            active_projects: row.get(3)?,
            longest_session: row.get(4)?,
            updated_at: row.get(5)?,
        })
    })?;
    if let Some(res) = rows.next() {
        Ok(Some(res?))
    } else {
        Ok(None)
    }
}

pub fn get_all_daily_summaries(paths: &ProfilePaths) -> rusqlite::Result<Vec<DailySummaryRow>> {
    let conn = open_connection(&paths.db_file)?;
    init_schema(&conn)?;
    let mut stmt = conn.prepare(
        "SELECT date, total_seconds, session_count, active_projects, longest_session, COALESCE(updated_at, '') FROM daily_summary ORDER BY date ASC",
    )?;
    let rows = stmt.query_map([], |row| {
        Ok(DailySummaryRow {
            date: row.get(0)?,
            total_seconds: row.get(1)?,
            session_count: row.get(2)?,
            active_projects: row.get(3)?,
            longest_session: row.get(4)?,
            updated_at: row.get(5)?,
        })
    })?;
    let mut out = Vec::new();
    for r in rows {
        out.push(r?);
    }
    Ok(out)
}

#[allow(clippy::too_many_arguments)]
pub fn save_invoice(
    paths: &ProfilePaths,
    invoice_no: &str,
    client_name: &str,
    amount: f64,
    currency: &str,
    status: &str,
    session_files: &Value,
    billing_data: &Value,
    settings_data: &Value,
    created_at: Option<&str>,
) -> rusqlite::Result<()> {
    let now = Local::now().format("%Y-%m-%dT%H:%M:%S%.6f").to_string();
    let created_at_val = created_at.unwrap_or(&now);
    let session_files_str = serde_json::to_string(session_files).unwrap_or_else(|_| "[]".into());
    let billing_data_str = serde_json::to_string(billing_data).unwrap_or_else(|_| "{}".into());
    let settings_data_str = serde_json::to_string(settings_data).unwrap_or_else(|_| "{}".into());

    let conn = open_connection(&paths.db_file)?;
    init_schema(&conn)?;
    conn.execute(
        r#"
        INSERT INTO invoices (
            invoice_no, client_name, amount, currency, status,
            session_files, billing_data, settings_data, created_at, updated_at
        ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10)
        ON CONFLICT(invoice_no) DO UPDATE SET
            client_name = excluded.client_name,
            amount = excluded.amount,
            currency = excluded.currency,
            status = excluded.status,
            session_files = excluded.session_files,
            billing_data = excluded.billing_data,
            settings_data = excluded.settings_data,
            updated_at = excluded.updated_at;
        "#,
        params![
            invoice_no,
            client_name,
            amount,
            currency,
            status,
            session_files_str,
            billing_data_str,
            settings_data_str,
            created_at_val,
            now,
        ],
    )?;
    Ok(())
}

pub fn get_invoices_list(paths: &ProfilePaths) -> rusqlite::Result<Vec<InvoiceListItem>> {
    let conn = open_connection(&paths.db_file)?;
    init_schema(&conn)?;
    let mut stmt = conn.prepare(
        "SELECT invoice_no, COALESCE(client_name, ''), COALESCE(amount, 0.0), COALESCE(currency, '$'), COALESCE(status, 'unpaid'), COALESCE(created_at, '') FROM invoices ORDER BY created_at DESC",
    )?;
    let rows = stmt.query_map([], |row| {
        Ok(InvoiceListItem {
            invoice_no: row.get(0)?,
            client_name: row.get(1)?,
            amount: row.get(2)?,
            currency: row.get(3)?,
            status: row.get(4)?,
            created_at: row.get(5)?,
        })
    })?;
    let mut out = Vec::new();
    for r in rows {
        out.push(r?);
    }
    Ok(out)
}

pub fn get_invoice_by_no(
    paths: &ProfilePaths,
    invoice_no: &str,
) -> rusqlite::Result<Option<InvoiceRecord>> {
    let conn = open_connection(&paths.db_file)?;
    init_schema(&conn)?;
    let mut stmt = conn.prepare(
        "SELECT invoice_no, COALESCE(client_name, ''), COALESCE(amount, 0.0), COALESCE(currency, '$'), COALESCE(status, 'unpaid'), COALESCE(session_files, '[]'), COALESCE(billing_data, '{}'), COALESCE(settings_data, '{}'), COALESCE(created_at, ''), COALESCE(updated_at, '') FROM invoices WHERE invoice_no = ?1",
    )?;
    let mut rows = stmt.query_map(params![invoice_no], |row| {
        Ok(InvoiceRecord {
            invoice_no: row.get(0)?,
            client_name: row.get(1)?,
            amount: row.get(2)?,
            currency: row.get(3)?,
            status: row.get(4)?,
            session_files: row.get(5)?,
            billing_data: row.get(6)?,
            settings_data: row.get(7)?,
            created_at: row.get(8)?,
            updated_at: row.get(9)?,
        })
    })?;
    if let Some(res) = rows.next() {
        Ok(Some(res?))
    } else {
        Ok(None)
    }
}

pub fn update_invoice_status(
    paths: &ProfilePaths,
    invoice_no: &str,
    status: &str,
) -> rusqlite::Result<usize> {
    let now = Local::now().format("%Y-%m-%dT%H:%M:%S%.6f").to_string();
    let conn = open_connection(&paths.db_file)?;
    init_schema(&conn)?;
    conn.execute(
        "UPDATE invoices SET status = ?1, updated_at = ?2 WHERE invoice_no = ?3",
        params![status, now, invoice_no],
    )
}

pub fn rename_invoice(
    paths: &ProfilePaths,
    old_no: &str,
    new_no: &str,
) -> rusqlite::Result<usize> {
    let clean_new = new_no.trim();
    if clean_new.is_empty() {
        return Err(rusqlite::Error::InvalidParameterName(
            "Invoice number cannot be empty".to_string(),
        ));
    }
    let now = Local::now().format("%Y-%m-%dT%H:%M:%S%.6f").to_string();
    let conn = open_connection(&paths.db_file)?;
    init_schema(&conn)?;
    conn.execute(
        "UPDATE invoices SET invoice_no = ?1, updated_at = ?2 WHERE invoice_no = ?3",
        params![clean_new, now, old_no],
    )
}

pub fn delete_invoice(paths: &ProfilePaths, invoice_no: &str) -> rusqlite::Result<usize> {
    let conn = open_connection(&paths.db_file)?;
    init_schema(&conn)?;
    conn.execute("DELETE FROM invoices WHERE invoice_no = ?1", params![invoice_no])
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use tempfile::TempDir;

    #[test]
    fn test_daily_summary_dedup_and_recalc() {
        let tmp = TempDir::new().unwrap();
        let paths = ProfilePaths::from_root_and_profile(tmp.path().to_path_buf(), "Test".into());
        paths.ensure_dirs().unwrap();
        init_database(&paths).unwrap();

        let finalized = json!({
            "date": "2026-11-15",
            "start": "09:00:00",
            "end": "10:00:00",
            "total_seconds": 3600,
            "counted_seconds": 3600,
            "apps": [
                {"name": "VS Code", "seconds": 3000, "excluded": false, "tag": "Development"},
                {"name": "YouTube", "seconds": 600, "excluded": true, "tag": "Unassigned"}
            ]
        });
        fs::write(
            paths.sessions_dir.join("session_2026-11-15_09-00-00.json"),
            serde_json::to_string_pretty(&finalized).unwrap(),
        )
        .unwrap();

        // Orphaned autosave with unfinalized start must be ignored just like Python aggregator.py
        let orphan = json!({
            "date": "2026-11-15",
            "start": "11:00:00",
            "total_seconds": 999,
            "apps": [{"name": "Figma", "seconds": 999, "excluded": false, "tag": "Design"}]
        });
        fs::write(
            paths.autosave_dir.join("auto_session_2026-11-15_11-00-00.json"),
            serde_json::to_string_pretty(&orphan).unwrap(),
        )
        .unwrap();

        update_daily_summary(&paths, "2026-11-15").unwrap();
        let row = get_daily_summary(&paths, "2026-11-15").unwrap().unwrap();
        assert_eq!(row.total_seconds, 3600);
        assert_eq!(row.session_count, 1);
        assert_eq!(row.active_projects, 1);
        assert_eq!(row.longest_session, 3600);

        // Newer autosave for the finalized key wins if total_seconds is larger
        let newer_auto = json!({
            "date": "2026-11-15",
            "start": "09:00:00",
            "total_seconds": 4000,
            "apps": [
                {"name": "VS Code", "seconds": 3000, "excluded": false, "tag": "Development"},
                {"name": "Figma", "seconds": 1000, "excluded": false, "tag": "Design"}
            ]
        });
        fs::write(
            paths.autosave_dir.join("auto_session_2026-11-15_09-00-00.json"),
            serde_json::to_string_pretty(&newer_auto).unwrap(),
        )
        .unwrap();

        update_daily_summary(&paths, "2026-11-15").unwrap();
        let row2 = get_daily_summary(&paths, "2026-11-15").unwrap().unwrap();
        assert_eq!(row2.total_seconds, 4000);
        assert_eq!(row2.active_projects, 2);

        let all_rows = get_all_daily_summaries(&paths).unwrap();
        assert_eq!(all_rows.len(), 1);
        assert_eq!(all_rows[0].date, "2026-11-15");
    }

    #[test]
    fn test_invoice_crud_and_status_lifecycle() {
        let tmp = TempDir::new().unwrap();
        let paths = ProfilePaths::from_root_and_profile(tmp.path().to_path_buf(), "Test".into());
        paths.ensure_dirs().unwrap();
        init_database(&paths).unwrap();

        save_invoice(
            &paths,
            "INV-2026-01",
            "Acme Corp",
            250.50,
            "$",
            "draft",
            &json!(["s1.json"]),
            &json!({"counted_seconds": 3600}),
            &json!({"business_name": "Studio"}),
            None,
        )
        .unwrap();

        let list = get_invoices_list(&paths).unwrap();
        assert_eq!(list.len(), 1);
        assert_eq!(list[0].invoice_no, "INV-2026-01");
        assert_eq!(list[0].status, "draft");

        let rec = get_invoice_by_no(&paths, "INV-2026-01").unwrap().unwrap();
        assert_eq!(rec.client_name, "Acme Corp");
        assert_eq!(rec.amount, 250.50);

        update_invoice_status(&paths, "INV-2026-01", "paid").unwrap();
        assert_eq!(
            get_invoice_by_no(&paths, "INV-2026-01").unwrap().unwrap().status,
            "paid"
        );

        assert!(rename_invoice(&paths, "INV-2026-01", "   ").is_err());
        rename_invoice(&paths, "INV-2026-01", "INV-2026-FINAL").unwrap();
        assert!(get_invoice_by_no(&paths, "INV-2026-01").unwrap().is_none());
        assert!(get_invoice_by_no(&paths, "INV-2026-FINAL").unwrap().is_some());

        delete_invoice(&paths, "INV-2026-FINAL").unwrap();
        assert!(get_invoices_list(&paths).unwrap().is_empty());
    }
}
