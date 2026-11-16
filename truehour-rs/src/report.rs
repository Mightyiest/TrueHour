use crate::config::{atomic_write_str, ProfilePaths};
use crate::db;
use crate::settings::AppSettings;
use chrono::{Datelike, DateTime, Duration as ChronoDuration, Local, NaiveDate, NaiveDateTime, TimeZone};
use serde::{de::DeserializeOwned, Deserialize, Serialize};
use serde_json::{json, Map, Value};
use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::time::UNIX_EPOCH;

fn parse_json_str<T: DeserializeOwned>(raw: &str) -> serde_json::Result<T> {
    serde_json::from_str(raw.trim_start_matches('\u{feff}'))
}

pub fn format_duration(total_seconds: i64) -> String {
    let clamped = total_seconds.max(0);
    let h = clamped / 3600;
    let m = (clamped % 3600) / 60;
    let s = clamped % 60;
    format!("{h}h {m:02}m {s:02}s")
}

pub fn format_duration_hms(total_seconds: i64) -> String {
    let clamped = total_seconds.max(0);
    let h = clamped / 3600;
    let m = (clamped % 3600) / 60;
    let s = clamped % 60;
    format!("{h:02}:{m:02}:{s:02}")
}

pub fn format_currency(currency_symbol: &str, amount: f64) -> String {
    let negative = amount < 0.0;
    let abs_val = amount.abs();
    let cents_str = format!("{:.2}", abs_val);
    let (int_part, frac_part) = cents_str.split_once('.').unwrap_or((&cents_str, "00"));
    let mut grouped = String::new();
    for (idx, ch) in int_part.chars().rev().enumerate() {
        if idx > 0 && idx % 3 == 0 {
            grouped.push(',');
        }
        grouped.push(ch);
    }
    let formatted_int: String = grouped.chars().rev().collect();
    if negative {
        format!("-{currency_symbol}{formatted_int}.{frac_part}")
    } else {
        format!("{currency_symbol}{formatted_int}.{frac_part}")
    }
}

pub fn project_color(project_name: &str) -> &'static str {
    match project_name {
        "Development" => "#4F46E5",
        "Design" => "#EC4899",
        "Research" => "#10B981",
        "Documentation" => "#F59E0B",
        "Communication" => "#06B6D4",
        "Management" => "#8B5CF6",
        "Unassigned" => "#64748B",
        _ => {
            const PALETTE: [&str; 6] = [
                "#4F46E5", "#EC4899", "#10B981", "#F59E0B", "#06B6D4", "#8B5CF6",
            ];
            let idx: usize = project_name.chars().map(|c| c as usize).sum::<usize>() % PALETTE.len();
            PALETTE[idx]
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppUsageEntry {
    pub name: String,
    pub seconds: i64,
    pub formatted: String,
    pub percent: f64,
    pub excluded: bool,
    pub tag: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProjectBreakdownEntry {
    pub project: String,
    pub seconds: i64,
    pub formatted: String,
    pub percent: f64,
    pub earned: f64,
    pub earned_display: String,
    pub color: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TimelineEntry {
    pub app: String,
    pub start: String,
    pub end: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionReportData {
    pub date: String,
    pub date_display: String,
    pub start: String,
    pub start_display: String,
    pub end: String,
    pub end_display: String,
    pub total_seconds: i64,
    pub total_formatted: String,
    pub counted_seconds: i64,
    pub counted_formatted: String,
    pub apps: Vec<AppUsageEntry>,
    pub timeline: Vec<TimelineEntry>,
    pub is_recovered: bool,
    pub is_resumed: bool,
    pub resumed_filepath: Option<String>,
    pub new_activity: Vec<Value>,
    pub session_name: String,
    pub app_exe_paths: HashMap<String, String>,
    pub hourly_rate: f64,
    pub currency_symbol: String,
    pub total_earned: f64,
    pub total_earned_display: String,
    pub project_breakdown: Vec<ProjectBreakdownEntry>,
}

pub struct ReportInput<'a> {
    pub session_start_ts: f64,
    pub session_end_ts: f64,
    pub total_seconds: i64,
    pub counted_seconds: i64,
    pub apps: &'a [(String, f64, bool, String)], // (name, secs, included, tag)
    pub timeline: &'a [(String, f64, f64)],       // (app, start_ts, end_ts)
    pub app_included: &'a HashMap<String, bool>,
    pub app_exe_paths: &'a HashMap<String, String>,
    pub is_recovered: bool,
    pub is_resumed: bool,
    pub resumed_filepath: Option<String>,
    pub session_name: &'a str,
    pub hourly_rate: f64,
    pub currency_symbol: &'a str,
}

fn ts_to_local(ts: f64) -> DateTime<Local> {
    let secs = ts.floor() as i64;
    let nanos = ((ts - ts.floor()).max(0.0) * 1_000_000_000.0) as u32;
    Local
        .timestamp_opt(secs, nanos.min(999_999_999))
        .single()
        .unwrap_or_else(Local::now)
}

fn round1(v: f64) -> f64 {
    (v * 10.0).round() / 10.0
}

fn round2(v: f64) -> f64 {
    (v * 100.0).round() / 100.0
}

pub fn generate_smart_session_name(
    current_name: &str,
    start_display: &str,
    breakdown: &[ProjectBreakdownEntry],
    apps: &[AppUsageEntry],
) -> String {
    let trimmed = current_name.trim();
    let is_default_placeholder = trimmed.is_empty() || trimmed.starts_with("Session - ");
    if !is_default_placeholder {
        return trimmed.to_string();
    }

    if let Some(top_proj) = breakdown
        .iter()
        .find(|p| p.seconds > 0 && p.project != "Unassigned")
    {
        return format!("{} — {}", top_proj.project, start_display);
    }

    if let Some(top_app) = apps.iter().find(|a| !a.excluded && a.seconds > 0) {
        return format!("{} — {}", top_app.name, start_display);
    }

    if !trimmed.is_empty() {
        trimmed.to_string()
    } else {
        format!("Session — {start_display}")
    }
}

pub fn build_report_data(input: ReportInput<'_>) -> SessionReportData {
    let start_dt = ts_to_local(input.session_start_ts);
    let end_dt = ts_to_local(input.session_end_ts);

    let mut app_list = Vec::with_capacity(input.apps.len());
    let mut project_times: HashMap<String, i64> = HashMap::new();

    for (name, secs_f, included, tag) in input.apps {
        let secs = *secs_f as i64;
        let pct = if input.total_seconds > 0 {
            round1((secs as f64 / input.total_seconds as f64) * 100.0)
        } else {
            0.0
        };
        app_list.push(AppUsageEntry {
            name: name.clone(),
            seconds: secs,
            formatted: format_duration(secs),
            percent: pct,
            excluded: !*included,
            tag: tag.clone(),
        });
        if *included {
            *project_times.entry(tag.clone()).or_insert(0) += secs;
        }
    }

    let mut timeline = Vec::new();
    for (app, start_ts, end_ts) in input.timeline {
        if app == "[Idle]" || !*input.app_included.get(app).unwrap_or(&true) {
            continue;
        }
        timeline.push(TimelineEntry {
            app: app.clone(),
            start: ts_to_local(*start_ts).format("%H:%M:%S").to_string(),
            end: ts_to_local(*end_ts).format("%H:%M:%S").to_string(),
        });
    }

    let total_counted_proj: i64 = project_times.values().sum();
    let mut breakdown: Vec<ProjectBreakdownEntry> = project_times
        .into_iter()
        .map(|(proj, secs)| {
            let pct = if total_counted_proj > 0 {
                round1((secs as f64 / total_counted_proj as f64) * 100.0)
            } else {
                0.0
            };
            let earned = round2((secs as f64 / 3600.0) * input.hourly_rate);
            ProjectBreakdownEntry {
                color: project_color(&proj).to_string(),
                project: proj,
                seconds: secs,
                formatted: format_duration(secs),
                percent: pct,
                earned,
                earned_display: format_currency(input.currency_symbol, earned),
            }
        })
        .collect();
    breakdown.sort_by(|a, b| b.seconds.cmp(&a.seconds));

    let total_earned = if input.hourly_rate > 0.0 {
        round2(breakdown.iter().map(|b| b.earned).sum())
    } else {
        0.0
    };

    let start_display = start_dt.format("%I:%M %p").to_string();
    let smart_name =
        generate_smart_session_name(input.session_name, &start_display, &breakdown, &app_list);

    SessionReportData {
        date: start_dt.format("%Y-%m-%d").to_string(),
        date_display: start_dt.format("%B %d, %Y").to_string(),
        start: start_dt.format("%H:%M:%S").to_string(),
        start_display,
        end: end_dt.format("%H:%M:%S").to_string(),
        end_display: end_dt.format("%I:%M %p").to_string(),
        total_seconds: input.total_seconds,
        total_formatted: format_duration(input.total_seconds),
        counted_seconds: input.counted_seconds,
        counted_formatted: format_duration(input.counted_seconds),
        apps: app_list,
        timeline,
        is_recovered: input.is_recovered,
        is_resumed: input.is_resumed,
        resumed_filepath: input.resumed_filepath,
        new_activity: Vec::new(),
        session_name: smart_name,
        app_exe_paths: input.app_exe_paths.clone(),
        hourly_rate: input.hourly_rate,
        currency_symbol: input.currency_symbol.to_string(),
        total_earned,
        total_earned_display: format_currency(input.currency_symbol, total_earned),
        project_breakdown: breakdown,
    }
}

/// Writes `report` using the exact Python v4.2 `export_json(..., is_internal=True)` schema.
pub fn export_internal_json(report: &SessionReportData, filepath: &Path) -> std::io::Result<()> {
    let apps_json: Vec<Value> = report
        .apps
        .iter()
        .map(|a| {
            json!({
                "name": a.name,
                "seconds": a.seconds,
                "excluded": a.excluded,
                "tag": a.tag,
            })
        })
        .collect();

    let payload = json!({
        "session_name": report.session_name,
        "app_exe_paths": report.app_exe_paths,
        "date": report.date,
        "start": report.start,
        "end": report.end,
        "total_seconds": report.total_seconds,
        "counted_seconds": report.counted_seconds,
        "is_resumed": report.is_resumed,
        "new_activity": report.new_activity,
        "apps": apps_json,
        "project_breakdown": report.project_breakdown,
        "timeline": report.timeline,
        "hourly_rate": report.hourly_rate,
        "currency_symbol": report.currency_symbol,
        "total_earned": report.total_earned,
    });

    let serialized = serde_json::to_string_pretty(&payload).map_err(std::io::Error::other)?;
    atomic_write_str(filepath, &serialized)
}

fn filename_stamp(date_str: &str, start_hms: &str) -> String {
    let hms_dash = start_hms.replace(':', "-");
    format!("{date_str}_{hms_dash}")
}

pub fn save_to_autosave(
    paths: &ProfilePaths,
    report: &SessionReportData,
) -> std::io::Result<PathBuf> {
    fs::create_dir_all(&paths.autosave_dir)?;
    let prefix = if report.is_recovered {
        "recovery"
    } else {
        "auto"
    };
    let stamp = filename_stamp(&report.date, &report.start);
    let filepath = paths.autosave_dir.join(format!("{prefix}_{stamp}.json"));
    export_internal_json(report, &filepath)?;
    let _ = db::update_daily_summary(paths, &report.date);
    Ok(filepath)
}

pub fn save_to_history(
    paths: &ProfilePaths,
    report: &mut SessionReportData,
) -> std::io::Result<PathBuf> {
    fs::create_dir_all(&paths.sessions_dir)?;

    let target = if let Some(ref resumed) = report.resumed_filepath {
        let p = PathBuf::from(resumed);
        if p.exists() && p.parent() == Some(paths.sessions_dir.as_path()) {
            p
        } else {
            unique_session_filepath(&paths.sessions_dir, &report.date, &report.start)
        }
    } else {
        unique_session_filepath(&paths.sessions_dir, &report.date, &report.start)
    };

    export_internal_json(report, &target)?;
    report.resumed_filepath = Some(target.to_string_lossy().to_string());
    let _ = db::update_daily_summary(paths, &report.date);
    Ok(target)
}

fn unique_session_filepath(sessions_dir: &Path, date_str: &str, start_hms: &str) -> PathBuf {
    let stamp = filename_stamp(date_str, start_hms);
    let candidate = sessions_dir.join(format!("session_{stamp}.json"));
    if !candidate.exists() {
        return candidate;
    }
    for idx in 1..=1000 {
        let numbered = sessions_dir.join(format!("session_{stamp}_{idx}.json"));
        if !numbered.exists() {
            return numbered;
        }
    }
    sessions_dir.join(format!(
        "session_{stamp}_{}.json",
        chrono::Local::now().timestamp_millis()
    ))
}

pub fn rename_saved_session(filepath: &Path, new_name: &str) -> std::io::Result<String> {
    let trimmed = new_name.trim();
    if trimmed.is_empty() {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidInput,
            "Session name cannot be empty",
        ));
    }
    let raw = fs::read_to_string(filepath)?;
    let mut obj: Map<String, Value> =
        parse_json_str(&raw).map_err(std::io::Error::other)?;
    obj.insert("session_name".to_string(), Value::String(trimmed.to_string()));
    let updated = serde_json::to_string_pretty(&obj).map_err(std::io::Error::other)?;
    atomic_write_str(filepath, &updated)?;
    Ok(trimmed.to_string())
}

pub fn move_session_to_trash(paths: &ProfilePaths, filepath: &Path) -> std::io::Result<PathBuf> {
    if !filepath.exists() {
        return Err(std::io::Error::new(
            std::io::ErrorKind::NotFound,
            "Session file not found",
        ));
    }

    // Ensure filepath is within profile sessions dir (safety against path traversal)
    let canon_sessions = fs::canonicalize(&paths.sessions_dir)?;
    let canon_file = fs::canonicalize(filepath)?;
    if !canon_file.starts_with(&canon_sessions) {
        return Err(std::io::Error::new(
            std::io::ErrorKind::PermissionDenied,
            "Cannot trash file outside sessions directory",
        ));
    }

    let date_str: Option<String> = fs::read_to_string(&canon_file)
        .ok()
        .and_then(|s| parse_json_str::<Value>(&s).ok())
        .and_then(|v| {
            v.get("date")
                .and_then(|d| d.as_str())
                .map(|s| s.to_string())
        });

    fs::create_dir_all(&paths.trash_dir)?;
    let fname = canon_file
        .file_name()
        .and_then(|n| n.to_str())
        .ok_or_else(|| std::io::Error::other("Invalid filename"))?;

    let mut dst = paths.trash_dir.join(fname);
    if dst.exists() {
        let stem = Path::new(fname)
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("session");
        let ts = Local::now().format("%Y%m%d%H%M%S");
        dst = paths.trash_dir.join(format!("{stem}_{ts}.json"));
    }

    if fs::rename(&canon_file, &dst).is_err() {
        fs::copy(&canon_file, &dst)?;
        fs::remove_file(&canon_file)?;
    }

    if let Some(d) = date_str {
        let _ = db::update_daily_summary(paths, &d);
    }
    Ok(dst)
}

pub fn html_escape(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for ch in s.chars() {
        match ch {
            '&' => out.push_str("&amp;"),
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            '"' => out.push_str("&quot;"),
            '\'' => out.push_str("&#x27;"),
            _ => out.push(ch),
        }
    }
    out
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionListEntry {
    pub filepath: String,
    pub filename: String,
    pub session_name: String,
    pub date: String,
    pub date_display: String,
    pub start: String,
    pub end: String,
    pub total_seconds: i64,
    pub total_formatted: String,
    pub counted_seconds: i64,
    pub counted_formatted: String,
    pub mtime_secs: i64,
    pub is_latest: bool,
    pub relative_label: String,
}

fn format_relative_age(mtime_secs: i64, date_str: &str, now_secs: i64, idx: usize) -> String {
    if idx == 0 {
        return "Latest".to_string();
    }
    let diff = (now_secs - mtime_secs).max(0);
    if diff < 60 {
        return "Just now".to_string();
    }
    if diff < 3600 {
        return format!("{}m ago", diff / 60);
    }
    if diff < 86400 {
        return format!("{}h ago", diff / 3600);
    }
    if diff < 86400 * 7 {
        return format!("{}d ago", diff / 86400);
    }
    if let Ok(d) = NaiveDate::parse_from_str(date_str, "%Y-%m-%d") {
        return d.format("%b %d, %Y").to_string();
    }
    date_str.to_string()
}

pub fn list_session_files(dir: &Path) -> Vec<SessionListEntry> {
    if !dir.exists() {
        return Vec::new();
    }
    let mut raw_items: Vec<(i64, SessionListEntry)> = Vec::new();
    let entries = match fs::read_dir(dir) {
        Ok(e) => e,
        Err(_) => return Vec::new(),
    };

    for entry in entries.flatten() {
        let path = entry.path();
        if path.extension().and_then(|e| e.to_str()) != Some("json") {
            continue;
        }
        let Ok(content) = fs::read_to_string(&path) else {
            continue;
        };
        let Ok(data) = parse_json_str::<Value>(&content) else {
            continue;
        };
        let fname = path
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("")
            .to_string();
        let date = data.get("date").and_then(|v| v.as_str()).unwrap_or("").to_string();
        let start = data.get("start").and_then(|v| v.as_str()).unwrap_or("").to_string();
        let end = data.get("end").and_then(|v| v.as_str()).unwrap_or("").to_string();
        let total_seconds = data.get("total_seconds").and_then(|v| v.as_i64()).unwrap_or(0);
        let counted_seconds = data.get("counted_seconds").and_then(|v| v.as_i64()).unwrap_or(0);
        let session_name = data
            .get("session_name")
            .and_then(|v| v.as_str())
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .map(str::to_string)
            .unwrap_or_else(|| {
                if !date.is_empty() && !start.is_empty() {
                    format!("Session {date} {start}")
                } else {
                    fname.clone()
                }
            });

        let date_display = NaiveDate::parse_from_str(&date, "%Y-%m-%d")
            .map(|d| d.format("%b %d, %Y").to_string())
            .unwrap_or_else(|_| date.clone());

        let mtime_secs = fs::metadata(&path)
            .and_then(|m| m.modified())
            .ok()
            .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
            .map(|d| d.as_secs() as i64)
            .unwrap_or(0);

        raw_items.push((
            mtime_secs,
            SessionListEntry {
                filepath: path.to_string_lossy().to_string(),
                filename: fname,
                session_name,
                date,
                date_display,
                start,
                end,
                total_seconds,
                total_formatted: format_duration(total_seconds),
                counted_seconds,
                counted_formatted: format_duration(counted_seconds),
                mtime_secs,
                is_latest: false,
                relative_label: String::new(),
            },
        ));
    }

    raw_items.sort_by(|a, b| {
        b.1.date
            .cmp(&a.1.date)
            .then_with(|| b.1.start.cmp(&a.1.start))
            .then_with(|| b.0.cmp(&a.0))
    });

    let now_secs = Local::now().timestamp();
    raw_items
        .into_iter()
        .enumerate()
        .map(|(idx, (mt, mut item))| {
            item.is_latest = idx == 0;
            item.relative_label = format_relative_age(mt, &item.date, now_secs, idx);
            item
        })
        .collect()
}

pub fn load_session_report(filepath: &Path) -> Result<SessionReportData, String> {
    let raw = fs::read_to_string(filepath).map_err(|e| format!("Failed to read session: {e}"))?;
    let data: Value =
        parse_json_str(&raw).map_err(|e| format!("Invalid session JSON: {e}"))?;

    let date_str = data
        .get("date")
        .and_then(|v| v.as_str())
        .unwrap_or("1970-01-01")
        .to_string();
    let start_str = data
        .get("start")
        .and_then(|v| v.as_str())
        .unwrap_or("00:00:00")
        .to_string();
    let end_str = data
        .get("end")
        .and_then(|v| v.as_str())
        .unwrap_or(&start_str)
        .to_string();

    let start_dt = NaiveDateTime::parse_from_str(
        &format!("{date_str} {start_str}"),
        "%Y-%m-%d %H:%M:%S",
    )
    .unwrap_or_else(|_| Local::now().naive_local());
    let mut end_dt = NaiveDateTime::parse_from_str(
        &format!("{date_str} {end_str}"),
        "%Y-%m-%d %H:%M:%S",
    )
    .unwrap_or(start_dt);
    if end_dt <= start_dt {
        end_dt += ChronoDuration::days(1);
    }

    let total_seconds = data
        .get("total_seconds")
        .and_then(|v| v.as_i64())
        .unwrap_or(0);
    let counted_seconds = data
        .get("counted_seconds")
        .and_then(|v| v.as_i64())
        .unwrap_or(0);
    let hourly_rate = data
        .get("hourly_rate")
        .and_then(|v| v.as_f64())
        .unwrap_or(0.0);
    let currency_symbol = data
        .get("currency_symbol")
        .and_then(|v| v.as_str())
        .unwrap_or("$")
        .to_string();

    let mut apps = Vec::new();
    let mut excluded_apps = HashSet::new();
    let mut project_times: HashMap<String, i64> = HashMap::new();

    if let Some(arr) = data.get("apps").and_then(|v| v.as_array()) {
        for a in arr {
            let name = a.get("name").and_then(|v| v.as_str()).unwrap_or("").to_string();
            let secs = a.get("seconds").and_then(|v| v.as_i64()).unwrap_or(0);
            let excluded = a.get("excluded").and_then(|v| v.as_bool()).unwrap_or(false);
            let tag = a
                .get("tag")
                .and_then(|v| v.as_str())
                .unwrap_or("Unassigned")
                .to_string();
            let pct = if total_seconds > 0 {
                round1((secs as f64 / total_seconds as f64) * 100.0)
            } else {
                0.0
            };
            if excluded {
                excluded_apps.insert(name.clone());
            } else {
                *project_times.entry(tag.clone()).or_insert(0) += secs;
            }
            apps.push(AppUsageEntry {
                name,
                seconds: secs,
                formatted: format_duration(secs),
                percent: pct,
                excluded,
                tag,
            });
        }
    }

    let total_proj_counted: i64 = project_times.values().sum();
    let mut breakdown: Vec<ProjectBreakdownEntry> = project_times
        .into_iter()
        .map(|(proj, secs)| {
            let pct = if total_proj_counted > 0 {
                round1((secs as f64 / total_proj_counted as f64) * 100.0)
            } else {
                0.0
            };
            let earned = round2((secs as f64 / 3600.0) * hourly_rate);
            ProjectBreakdownEntry {
                color: project_color(&proj).to_string(),
                project: proj,
                seconds: secs,
                formatted: format_duration(secs),
                percent: pct,
                earned,
                earned_display: format_currency(&currency_symbol, earned),
            }
        })
        .collect();
    breakdown.sort_by(|a, b| b.seconds.cmp(&a.seconds));

    let total_earned = if hourly_rate > 0.0 {
        round2(breakdown.iter().map(|b| b.earned).sum())
    } else {
        data.get("total_earned").and_then(|v| v.as_f64()).unwrap_or(0.0)
    };

    let mut timeline = Vec::new();
    if let Some(arr) = data.get("timeline").and_then(|v| v.as_array()) {
        for t in arr {
            let app = t.get("app").and_then(|v| v.as_str()).unwrap_or("").to_string();
            if excluded_apps.contains(&app) {
                continue;
            }
            let start = t.get("start").and_then(|v| v.as_str()).unwrap_or("").to_string();
            let end = t.get("end").and_then(|v| v.as_str()).unwrap_or("").to_string();
            timeline.push(TimelineEntry { app, start, end });
        }
    }

    let app_exe_paths: HashMap<String, String> = data
        .get("app_exe_paths")
        .and_then(|v| v.as_object())
        .map(|obj| {
            obj.iter()
                .filter_map(|(k, v)| v.as_str().map(|s| (k.clone(), s.to_string())))
                .collect()
        })
        .unwrap_or_default();

    let new_activity: Vec<Value> = data
        .get("new_activity")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();

    let session_name = data
        .get("session_name")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();

    Ok(SessionReportData {
        date: date_str,
        date_display: start_dt.format("%B %d, %Y").to_string(),
        start: start_str,
        start_display: start_dt.format("%I:%M %p").to_string(),
        end: end_str,
        end_display: end_dt.format("%I:%M %p").to_string(),
        total_seconds,
        total_formatted: format_duration(total_seconds),
        counted_seconds,
        counted_formatted: format_duration(counted_seconds),
        apps,
        timeline,
        is_recovered: false,
        is_resumed: data
            .get("is_resumed")
            .and_then(|v| v.as_bool())
            .unwrap_or(false),
        resumed_filepath: Some(filepath.to_string_lossy().to_string()),
        new_activity,
        session_name,
        app_exe_paths,
        hourly_rate,
        currency_symbol: currency_symbol.clone(),
        total_earned,
        total_earned_display: format_currency(&currency_symbol, total_earned),
        project_breakdown: breakdown,
    })
}

pub fn restore_session_from_trash(paths: &ProfilePaths, filepath: &Path) -> Result<PathBuf, String> {
    if !filepath.exists() {
        return Err("Session file not found in Trash.".to_string());
    }
    let canon_trash = fs::canonicalize(&paths.trash_dir).map_err(|e| e.to_string())?;
    let canon_file = fs::canonicalize(filepath).map_err(|e| e.to_string())?;
    if !canon_file.starts_with(&canon_trash) {
        return Err("Cannot restore file outside Trash directory.".to_string());
    }
    let date_str = fs::read_to_string(&canon_file)
        .ok()
        .and_then(|s| parse_json_str::<Value>(&s).ok())
        .and_then(|v| v.get("date").and_then(|d| d.as_str()).map(|s| s.to_string()));

    fs::create_dir_all(&paths.sessions_dir).map_err(|e| e.to_string())?;
    let fname = canon_file
        .file_name()
        .and_then(|n| n.to_str())
        .ok_or_else(|| "Invalid filename".to_string())?;
    let mut dst = paths.sessions_dir.join(fname);
    if dst.exists() {
        let stem = Path::new(fname)
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("session");
        let ts = Local::now().format("%Y%m%d%H%M%S");
        dst = paths.sessions_dir.join(format!("{stem}_restored_{ts}.json"));
    }

    if fs::rename(&canon_file, &dst).is_err() {
        fs::copy(&canon_file, &dst).map_err(|e| e.to_string())?;
        fs::remove_file(&canon_file).map_err(|e| e.to_string())?;
    }
    if let Some(d) = date_str {
        let _ = db::update_daily_summary(paths, &d);
    }
    Ok(dst)
}

pub fn delete_saved_file(paths: &ProfilePaths, filepath: &Path, kind: &str) -> Result<(), String> {
    if !filepath.exists() {
        return Err("File not found.".to_string());
    }
    let allowed_dir = match kind {
        "sessions" => &paths.sessions_dir,
        "autosave" => &paths.autosave_dir,
        "trash" => &paths.trash_dir,
        _ => return Err("Unsupported folder kind.".to_string()),
    };
    let canon_dir = fs::canonicalize(allowed_dir).map_err(|e| e.to_string())?;
    let canon_file = fs::canonicalize(filepath).map_err(|e| e.to_string())?;
    if !canon_file.starts_with(&canon_dir) {
        return Err("Cannot delete file outside managed directory.".to_string());
    }
    let date_str = if kind == "sessions" {
        fs::read_to_string(&canon_file)
            .ok()
            .and_then(|s| parse_json_str::<Value>(&s).ok())
            .and_then(|v| v.get("date").and_then(|d| d.as_str()).map(|s| s.to_string()))
    } else {
        None
    };

    fs::remove_file(&canon_file).map_err(|e| format!("Failed to delete file: {e}"))?;
    if let Some(d) = date_str {
        let _ = db::update_daily_summary(paths, &d);
    }
    Ok(())
}

pub fn merge_session_files(
    paths: &ProfilePaths,
    filepaths: &[PathBuf],
    merged_name: &str,
) -> Result<PathBuf, String> {
    let trimmed_name = merged_name.trim();
    if trimmed_name.is_empty() {
        return Err("Merged session name cannot be empty.".to_string());
    }
    if filepaths.len() < 2 {
        return Err("At least 2 session files are required to merge.".to_string());
    }

    let mut sessions: Vec<(PathBuf, Value)> = Vec::new();
    for path in filepaths {
        if let Ok(raw) = fs::read_to_string(path) {
            if let Ok(data) = parse_json_str::<Value>(&raw) {
                sessions.push((path.clone(), data));
            }
        }
    }
    if sessions.len() < 2 {
        return Err("At least 2 valid session files are required to merge.".to_string());
    }

    let parse_dt = |path: &Path, data: &Value, field: &str| -> NaiveDateTime {
        let d = data.get("date").and_then(|v| v.as_str()).unwrap_or("");
        let t = data.get(field).and_then(|v| v.as_str()).unwrap_or("");
        if let Ok(dt) = NaiveDateTime::parse_from_str(&format!("{d} {t}"), "%Y-%m-%d %H:%M:%S") {
            return dt;
        }
        fs::metadata(path)
            .and_then(|m| m.modified())
            .ok()
            .map(|sys| DateTime::<Local>::from(sys).naive_local())
            .unwrap_or_else(|| Local::now().naive_local())
    };

    sessions.sort_by_key(|(p, d)| parse_dt(p, d, "start"));

    let earliest_start = parse_dt(&sessions[0].0, &sessions[0].1, "start");
    let total_sum: i64 = sessions
        .iter()
        .map(|(_, d)| d.get("total_seconds").and_then(|v| v.as_i64()).unwrap_or(0))
        .sum();
    let mut latest_end = sessions
        .iter()
        .map(|(p, d)| parse_dt(p, d, "end"))
        .max()
        .unwrap_or(earliest_start);
    if latest_end <= earliest_start {
        latest_end = earliest_start + ChronoDuration::seconds(total_sum.max(0));
    }

    let mut merged_exes: HashMap<String, String> = HashMap::new();
    let mut merged_apps: HashMap<String, (i64, String, bool)> = HashMap::new();
    let mut merged_new_activity: Vec<Value> = Vec::new();
    let mut timeline_with_date: Vec<(String, Value)> = Vec::new();
    let mut total_seconds = 0i64;
    let mut counted_seconds = 0i64;
    let mut hourly_rate = 0.0f64;
    let mut currency_symbol = "$".to_string();

    for (_, data) in &sessions {
        total_seconds += data.get("total_seconds").and_then(|v| v.as_i64()).unwrap_or(0);
        counted_seconds += data.get("counted_seconds").and_then(|v| v.as_i64()).unwrap_or(0);
        if hourly_rate == 0.0 {
            if let Some(r) = data.get("hourly_rate").and_then(|v| v.as_f64()) {
                hourly_rate = r;
            }
        }
        if let Some(cs) = data.get("currency_symbol").and_then(|v| v.as_str()) {
            if !cs.is_empty() {
                currency_symbol = cs.to_string();
            }
        }
        if let Some(exes) = data.get("app_exe_paths").and_then(|v| v.as_object()) {
            for (k, v) in exes {
                if let Some(p) = v.as_str() {
                    if !p.is_empty() && !merged_exes.contains_key(k) {
                        merged_exes.insert(k.clone(), p.to_string());
                    }
                }
            }
        }
        if let Some(apps) = data.get("apps").and_then(|v| v.as_array()) {
            for app in apps {
                let name = app.get("name").and_then(|v| v.as_str()).unwrap_or("Unknown").to_string();
                let secs = app.get("seconds").and_then(|v| v.as_i64()).unwrap_or(0);
                let tag = app.get("tag").and_then(|v| v.as_str()).unwrap_or("Unassigned").to_string();
                let excluded = app.get("excluded").and_then(|v| v.as_bool()).unwrap_or(false);
                merged_apps
                    .entry(name)
                    .and_modify(|e| {
                        e.0 += secs;
                        if !excluded {
                            e.2 = false;
                        }
                        if e.1 == "Unassigned" && tag != "Unassigned" {
                            e.1 = tag.clone();
                        }
                    })
                    .or_insert((secs, tag, excluded));
            }
        }
        if let Some(acts) = data.get("new_activity").and_then(|v| v.as_array()) {
            for a in acts {
                if !merged_new_activity.contains(a) {
                    merged_new_activity.push(a.clone());
                }
            }
        }
        let s_date = data.get("date").and_then(|v| v.as_str()).unwrap_or("").to_string();
        if let Some(tl) = data.get("timeline").and_then(|v| v.as_array()) {
            for t in tl {
                let key = format!(
                    "{} {}",
                    s_date,
                    t.get("start").and_then(|v| v.as_str()).unwrap_or("")
                );
                timeline_with_date.push((key, t.clone()));
            }
        }
    }

    timeline_with_date.sort_by(|a, b| a.0.cmp(&b.0));
    let merged_timeline: Vec<TimelineEntry> = timeline_with_date
        .into_iter()
        .filter_map(|(_, v)| serde_json::from_value(v).ok())
        .collect();

    let mut apps_list = Vec::with_capacity(merged_apps.len());
    let mut project_times: HashMap<String, i64> = HashMap::new();
    for (name, (secs, tag, excluded)) in merged_apps {
        let pct = if total_seconds > 0 {
            round1((secs as f64 / total_seconds as f64) * 100.0)
        } else {
            0.0
        };
        if !excluded {
            *project_times.entry(tag.clone()).or_insert(0) += secs;
        }
        apps_list.push(AppUsageEntry {
            name,
            seconds: secs,
            formatted: format_duration(secs),
            percent: pct,
            excluded,
            tag,
        });
    }
    apps_list.sort_by(|a, b| b.seconds.cmp(&a.seconds));

    let recalculated_counted: i64 = project_times.values().sum();
    if recalculated_counted > 0 {
        counted_seconds = recalculated_counted;
    }

    let mut breakdown: Vec<ProjectBreakdownEntry> = project_times
        .into_iter()
        .map(|(proj, secs)| {
            let pct = if counted_seconds > 0 {
                round1((secs as f64 / counted_seconds as f64) * 100.0)
            } else {
                0.0
            };
            let earned = round2((secs as f64 / 3600.0) * hourly_rate);
            ProjectBreakdownEntry {
                color: project_color(&proj).to_string(),
                project: proj,
                seconds: secs,
                formatted: format_duration(secs),
                percent: pct,
                earned,
                earned_display: format_currency(&currency_symbol, earned),
            }
        })
        .collect();
    breakdown.sort_by(|a, b| b.seconds.cmp(&a.seconds));

    let total_earned = if hourly_rate > 0.0 {
        round2(breakdown.iter().map(|b| b.earned).sum())
    } else {
        0.0
    };

    let mut report = SessionReportData {
        date: earliest_start.format("%Y-%m-%d").to_string(),
        date_display: earliest_start.format("%B %d, %Y").to_string(),
        start: earliest_start.format("%H:%M:%S").to_string(),
        start_display: earliest_start.format("%I:%M %p").to_string(),
        end: latest_end.format("%H:%M:%S").to_string(),
        end_display: latest_end.format("%I:%M %p").to_string(),
        total_seconds,
        total_formatted: format_duration(total_seconds),
        counted_seconds,
        counted_formatted: format_duration(counted_seconds),
        apps: apps_list,
        timeline: merged_timeline,
        is_recovered: false,
        is_resumed: false,
        resumed_filepath: None,
        new_activity: merged_new_activity,
        session_name: trimmed_name.to_string(),
        app_exe_paths: merged_exes,
        hourly_rate,
        currency_symbol: currency_symbol.clone(),
        total_earned,
        total_earned_display: format_currency(&currency_symbol, total_earned),
        project_breakdown: breakdown,
    };

    fs::create_dir_all(&paths.sessions_dir).map_err(|e| e.to_string())?;
    let stamp = Local::now().format("%Y%m%d_%H%M%S").to_string();
    let mut dest = paths.sessions_dir.join(format!("session_{stamp}.json"));
    if dest.exists() {
        dest = paths
            .sessions_dir
            .join(format!("session_{stamp}_{}.json", Local::now().timestamp_millis()));
    }
    export_internal_json(&report, &dest).map_err(|e| e.to_string())?;
    report.resumed_filepath = Some(dest.to_string_lossy().to_string());
    let _ = db::update_daily_summary(paths, &report.date);
    Ok(dest)
}

pub fn export_txt(report: &SessionReportData, filepath: &Path) -> std::io::Result<()> {
    let mut lines = Vec::new();
    lines.push("FOCUSLOG SESSION REPORT".to_string());
    if report.is_resumed {
        lines.push("[RESUMED SESSION]".to_string());
    }
    lines.push(format!("Date: {}", report.date));
    lines.push(format!(
        "Start: {} | End: {} | Duration: {}",
        report.start, report.end, report.total_formatted
    ));
    lines.push(format!("Counted Work Time: {}", report.counted_formatted));
    lines.push(format!(
        "Hourly Rate: {}{:.2}/hr",
        report.currency_symbol, report.hourly_rate
    ));
    lines.push(format!("Total Earned: {}", report.total_earned_display));
    lines.push(String::new());

    let active_new: Vec<&Value> = report
        .new_activity
        .iter()
        .filter(|a| !a.get("excluded").and_then(|v| v.as_bool()).unwrap_or(false))
        .collect();
    if !active_new.is_empty() {
        lines.push("NEW ACTIVITY (THIS RESUME)".to_string());
        lines.push("--------------------------".to_string());
        lines.push(format!(
            "{:<30} {:>12} {:>12} {:>12}",
            "App", "Previous", "New Added", "Total"
        ));
        for a in active_new {
            let name = a.get("name").and_then(|v| v.as_str()).unwrap_or("");
            let prev = a.get("previous_formatted").and_then(|v| v.as_str()).unwrap_or("");
            let new_secs = a.get("new_seconds").and_then(|v| v.as_i64()).unwrap_or(0);
            let new_str = if new_secs > 0 {
                a.get("new_formatted").and_then(|v| v.as_str()).unwrap_or("—")
            } else {
                "—"
            };
            let tot = a.get("total_formatted").and_then(|v| v.as_str()).unwrap_or("");
            lines.push(format!("{name:<30} {prev:>12} {new_str:>12} {tot:>12}"));
        }
        lines.push(String::new());
    }

    lines.push("APP USAGE BREAKDOWN".to_string());
    lines.push("-------------------".to_string());
    for app in &report.apps {
        if app.excluded {
            continue;
        }
        lines.push(format!(
            "{:<30} {:>12}   {:>5.1}%",
            app.name, app.formatted, app.percent
        ));
    }
    lines.push(String::new());

    lines.push("TIMELINE LOG".to_string());
    lines.push("------------".to_string());
    for entry in &report.timeline {
        lines.push(format!("{} -> {}   {}", entry.start, entry.end, entry.app));
    }
    lines.push(String::new());

    lines.push("PROJECT BREAKDOWN SUMMARY".to_string());
    lines.push("-------------------------".to_string());
    for pb in &report.project_breakdown {
        let earned_str = if pb.earned_display.is_empty() {
            String::new()
        } else {
            format!("   Earned: {}", pb.earned_display)
        };
        lines.push(format!(
            "{:<20} {:>12}   {:>5.1}%{earned_str}",
            pb.project, pb.formatted, pb.percent
        ));
    }
    lines.push(String::new());

    atomic_write_str(filepath, &lines.join("\n"))
}

const REPORT_HTML_TEMPLATE: &str = include_str!("../../templates/report_template.html");

fn simple_icon_slug(app_name: &str) -> Option<&'static str> {
    let lower = app_name.trim().to_lowercase();
    const MAPPINGS: &[(&str, &str)] = &[
        ("vs code", "visualstudiocode"),
        ("vscode", "visualstudiocode"),
        ("visual studio", "visualstudio"),
        ("figma", "figma"),
        ("notion", "notion"),
        ("google chrome", "googlechrome"),
        ("chrome", "googlechrome"),
        ("microsoft edge", "microsoftedge"),
        ("edge", "microsoftedge"),
        ("firefox", "mozillafirefox"),
        ("safari", "safari"),
        ("slack", "slack"),
        ("discord", "discord"),
        ("spotify", "spotify"),
        ("photoshop", "adobephotoshop"),
        ("illustrator", "adobeillustrator"),
        ("premiere", "adobepremierepro"),
        ("blender", "blender"),
        ("word", "microsoftword"),
        ("excel", "microsoftexcel"),
        ("powerpoint", "microsoftpowerpoint"),
        ("teams", "microsoftteams"),
        ("zoom", "zoom"),
        ("github", "github"),
        ("python", "python"),
        ("node", "nodedotjs"),
        ("trello", "trello"),
        ("jira", "jira"),
        ("asana", "asana"),
        ("clickup", "clickup"),
        ("whatsapp", "whatsapp"),
        ("telegram", "telegram"),
        ("outlook", "microsoftoutlook"),
        ("sublime", "sublimetext"),
        ("docker", "docker"),
        ("postman", "postman"),
        ("canva", "canva"),
    ];
    for &(key, slug) in MAPPINGS {
        if lower.contains(key) {
            return Some(slug);
        }
    }
    None
}

pub fn generate_session_report_html(paths: &ProfilePaths, report: &SessionReportData) -> String {
    let settings = AppSettings::load(&paths.app_settings_file);
    let theme_style = settings.theme_style();
    let dark_mode = theme_style != "light";

    let total_secs = report.total_seconds;
    let counted_secs = report.counted_seconds;
    let ratio = if total_secs > 0 {
        (counted_secs as f64 / total_secs as f64) * 100.0
    } else {
        0.0
    };

    let hourly_rate = report.hourly_rate;
    let curr = &report.currency_symbol;
    let earnings_html = if hourly_rate > 0.0 {
        let total_earned = (counted_secs as f64 / 3600.0) * hourly_rate;
        let total_earned_display = format_currency(curr, total_earned);
        format!(
            r#"
        <div class="section-header">
            <div class="section-title">Billing &amp; Estimated Earnings</div>
        </div>
        <div class="dashboard-grid" style="grid-template-columns: 1fr 1fr; margin-bottom: 40px;">
            <div class="kpi-card">
                <div class="kpi-label">Hourly Rate</div>
                <div class="kpi-val">{curr}{hourly_rate:.2}/hr</div>
            </div>
            <div class="kpi-card productive">
                <div class="kpi-label">Total Earned</div>
                <div class="kpi-val" style="color: var(--success);">{total_earned_display}</div>
            </div>
        </div>
        "#,
            curr = html_escape(curr)
        )
    } else {
        String::new()
    };

    let active_new: Vec<&Value> = report
        .new_activity
        .iter()
        .filter(|a| !a.get("excluded").and_then(|v| v.as_bool()).unwrap_or(false))
        .collect();
    let new_activity_html = if active_new.is_empty() {
        String::new()
    } else {
        let mut rows_html = String::new();
        for a in active_new {
            let name = a.get("name").and_then(|v| v.as_str()).unwrap_or("");
            let raw_tag = a.get("tag").and_then(|v| v.as_str()).unwrap_or("Unassigned");
            let tag_color = project_color(raw_tag);
            let pill_style = if tag_color != "#64748B" || dark_mode {
                format!("background-color: {tag_color}1a; color: {tag_color};")
            } else {
                String::new()
            };
            let initial = name
                .chars()
                .next()
                .map(|c| c.to_uppercase().to_string())
                .unwrap_or_else(|| "?".to_string());
            let prev = a.get("previous_formatted").and_then(|v| v.as_str()).unwrap_or("0h 00m 00s");
            let added = a.get("new_formatted").and_then(|v| v.as_str()).unwrap_or("—");
            let tot = a.get("total_formatted").and_then(|v| v.as_str()).unwrap_or("0h 00m 00s");
            rows_html.push_str(&format!(
                r#"
            <tr>
                <td style="font-weight: 600;"><svg class="app-icon" style="vertical-align: middle; margin-right: 8px;" width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><rect width="24" height="24" rx="6" fill="{tag_color}1a"/><text x="12" y="16" fill="{tag_color}" font-size="12" font-weight="800" font-family="Inter, system-ui, sans-serif" text-anchor="middle">{}</text></svg>{}</td>
                <td><span class="tag-pill" style="{pill_style}">{}</span></td>
                <td>{}</td>
                <td style="color: var(--success); font-weight: 600;">+{}</td>
                <td style="text-align: right; font-weight: 600;">{}</td>
            </tr>
            "#,
                html_escape(&initial),
                html_escape(name),
                html_escape(raw_tag),
                html_escape(prev),
                html_escape(added),
                html_escape(tot)
            ));
        }
        format!(
            r#"
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
            <tbody>{rows_html}</tbody>
        </table>
        "#
        )
    };

    let mut projects_visual = String::new();
    for pb in &report.project_breakdown {
        let color = project_color(&pb.project);
        projects_visual.push_str(&format!(
            r#"
        <div class="project-row">
            <div class="project-info">
                <span class="project-name">{}</span>
                <span class="project-stats">{} ({:.1}%)</span>
            </div>
            <div class="project-bar-bg">
                <div class="project-bar-fill" style="width: {:.1}%; background: linear-gradient(90deg, {color} 0%, {color}cc 100%);"></div>
            </div>
        </div>
        "#,
            html_escape(&pb.project),
            pb.formatted,
            pb.percent,
            pb.percent
        ));
    }

    let mut apps_rows = String::new();
    let mut app_tags_map: HashMap<String, String> = HashMap::new();
    for app in &report.apps {
        app_tags_map.insert(app.name.clone(), app.tag.clone());
        if app.excluded {
            continue;
        }
        let tag_color = project_color(&app.tag);
        let pill_style = if tag_color != "#64748B" || dark_mode {
            format!("background-color: {tag_color}1a; color: {tag_color};")
        } else {
            String::new()
        };
        let initial = app
            .name
            .chars()
            .next()
            .map(|c| c.to_uppercase().to_string())
            .unwrap_or_else(|| "?".to_string());
        let icon_html = if let Some(slug) = simple_icon_slug(&app.name) {
            let si_suffix = if dark_mode { "/e0e0e0" } else { "" };
            let encoded_color = tag_color.replace('#', "%23");
            let fallback_svg = format!(
                "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' width='20' height='20'><rect width='24' height='24' rx='6' fill='{encoded_color}1a'/><text x='12' y='16' fill='{encoded_color}' font-size='12' font-weight='800' font-family='sans-serif' text-anchor='middle'>{}</text></svg>",
                html_escape(&initial)
            )
            .replace('\'', "\\'");
            format!(
                r#"<img src="https://cdn.simpleicons.org/{slug}{si_suffix}" class="app-icon" onerror="this.onerror=function(){{ this.onerror=function(){{ this.onerror=null; this.src='{fallback_svg}'; }}; this.src='https://unpkg.com/simple-icons@11.13.0/icons/{slug}.svg'; }}; this.src='https://cdn.jsdelivr.net/npm/simple-icons@11.13.0/icons/{slug}.svg';" />"#
            )
        } else {
            format!(
                r#"<svg class="app-icon" style="vertical-align: middle; margin-right: 8px;" width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><rect width="24" height="24" rx="6" fill="{tag_color}1a"/><text x="12" y="16" fill="{tag_color}" font-size="12" font-weight="800" font-family="Inter, system-ui, sans-serif" text-anchor="middle">{}</text></svg>"#,
                html_escape(&initial)
            )
        };
        apps_rows.push_str(&format!(
            r#"
        <tr>
            <td style="font-weight: 600;">{icon_html}{}</td>
            <td><span class="tag-pill" style="{pill_style}">{}</span></td>
            <td>{}</td>
            <td style="text-align: right; font-weight: 600;">{:.1}%</td>
        </tr>
        "#,
            html_escape(&app.name),
            html_escape(&app.tag),
            app.formatted,
            app.percent
        ));
    }

    let mut timeline_items = String::new();
    let total_tl = report.timeline.len();
    for entry in report.timeline.iter().take(15) {
        let app_tag = app_tags_map
            .get(&entry.app)
            .map(String::as_str)
            .unwrap_or("Unassigned");
        let tag_color = project_color(app_tag);
        let fmt_time = |raw: &str| -> (Option<chrono::NaiveTime>, String) {
            if let Ok(t) = chrono::NaiveTime::parse_from_str(raw, "%H:%M:%S") {
                (Some(t), t.format("%I:%M:%S %p").to_string())
            } else {
                (None, raw.to_string())
            }
        };
        let (ts, start_disp) = fmt_time(&entry.start);
        let (te, end_disp) = fmt_time(&entry.end);
        let dur_str = match (ts, te) {
            (Some(s), Some(e)) => {
                let mut diff = (e - s).num_seconds();
                if diff < 0 {
                    diff += 86400;
                }
                if diff > 0 {
                    format_duration(diff)
                } else {
                    String::new()
                }
            }
            _ => String::new(),
        };
        timeline_items.push_str(&format!(
            r#"
        <div class="timeline-item" style="border-left-color: {tag_color}; --tag-color: {tag_color};">
            <span class="timeline-time">{} - {}</span>
            <span class="timeline-app">{} <span style="font-weight: normal; color: var(--text-muted); font-size: 11px;">({})</span></span>
            <span class="timeline-duration">{}</span>
        </div>
        "#,
            html_escape(&start_disp),
            html_escape(&end_disp),
            html_escape(&entry.app),
            html_escape(app_tag),
            html_escape(&dur_str)
        ));
    }
    if total_tl > 15 {
        timeline_items.push_str(&format!(
            r#"
        <div style="text-align: center; font-size: 12px; color: var(--text-muted); font-weight: 600; padding: 12px; border: 1px dashed var(--border); border-radius: 8px; margin-top: 10px; background-color: var(--bg-body);">
            ... and {} more activity segments in this session.
        </div>
        "#,
            total_tl - 15
        ));
    }

    let mut html = REPORT_HTML_TEMPLATE.to_string();
    let sess_name = if report.session_name.trim().is_empty() {
        "Unnamed Session"
    } else {
        report.session_name.trim()
    };
    html = html
        .replace("{{SESSION_NAME}}", &html_escape(sess_name))
        .replace("{{DATE}}", &html_escape(&report.date_display))
        .replace("{{START_TIME}}", &html_escape(&report.start_display))
        .replace("{{END_TIME}}", &html_escape(&report.end_display))
        .replace("{{TOTAL_DURATION}}", &report.total_formatted)
        .replace("{{PRODUCTIVE_DURATION}}", &report.counted_formatted)
        .replace("{{PRODUCTIVITY_RATIO}}", &format!("{ratio:.1}"))
        .replace("{{EARNINGS_HTML}}", &earnings_html)
        .replace("{{NEW_ACTIVITY_HTML}}", &new_activity_html)
        .replace("{{PROJECTS_VISUAL}}", &projects_visual)
        .replace("{{APPS_TABLE_ROWS}}", &apps_rows)
        .replace("{{TIMELINE_ITEMS}}", &timeline_items);

    if dark_mode {
        html = html.replace(
            r#"<body class="theme-indigo">"#,
            &format!(r#"<body class="theme-indigo dark {theme_style}">"#),
        );
    }
    html
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TrendBarItem {
    pub label: String,
    pub value: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HistoryAppItem {
    pub name: String,
    pub seconds: i64,
    pub formatted: String,
    pub percent: f64,
    pub excluded: bool,
    pub tag: String,
    pub exe_path: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HistoryInsightsDto {
    pub period: String,
    pub total_seconds: i64,
    pub total_formatted: String,
    pub counted_seconds: i64,
    pub counted_formatted: String,
    pub total_earned: f64,
    pub total_earned_display: String,
    pub apps: Vec<HistoryAppItem>,
    pub project_breakdown: Vec<ProjectBreakdownEntry>,
    pub daily_trend: Vec<TrendBarItem>,
    pub session_count: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HeatmapDayDto {
    pub date: String,
    pub total_seconds: i64,
    pub session_count: i64,
}

pub fn aggregate_history_data(
    paths: &ProfilePaths,
    period: &str,
    hourly_rate: f64,
    currency_symbol: &str,
) -> HistoryInsightsDto {
    let today = Local::now().date_naive();
    let (start_d, end_d) = match period {
        "week" => (today - ChronoDuration::days(6), today),
        "month" => {
            let first = NaiveDate::from_ymd_opt(today.year(), today.month(), 1).unwrap_or(today);
            (first, today)
        }
        _ => (today, today),
    };

    let mut unique_sessions: HashMap<(String, String), Value> = HashMap::new();
    let mut finalized_keys: HashSet<(String, String)> = HashSet::new();

    if paths.sessions_dir.exists() {
        if let Ok(entries) = fs::read_dir(&paths.sessions_dir) {
            for entry in entries.flatten() {
                let p = entry.path();
                if p.extension().and_then(|e| e.to_str()) != Some("json") {
                    continue;
                }
                if let Ok(raw) = fs::read_to_string(&p) {
                    if let Ok(data) = parse_json_str::<Value>(&raw) {
                        let d = data.get("date").and_then(|v| v.as_str()).unwrap_or("").to_string();
                        let s = data.get("start").and_then(|v| v.as_str()).unwrap_or("").to_string();
                        if !d.is_empty() && !s.is_empty() {
                            let key = (d, s);
                            finalized_keys.insert(key.clone());
                            let total_secs =
                                data.get("total_seconds").and_then(|v| v.as_i64()).unwrap_or(0);
                            let existing_total = unique_sessions
                                .get(&key)
                                .and_then(|v| v.get("total_seconds"))
                                .and_then(|v| v.as_i64())
                                .unwrap_or(-1);
                            if total_secs >= existing_total {
                                unique_sessions.insert(key, data);
                            }
                        }
                    }
                }
            }
        }
    }

    if paths.autosave_dir.exists() {
        if let Ok(entries) = fs::read_dir(&paths.autosave_dir) {
            for entry in entries.flatten() {
                let p = entry.path();
                if p.extension().and_then(|e| e.to_str()) != Some("json") {
                    continue;
                }
                if let Ok(raw) = fs::read_to_string(&p) {
                    if let Ok(data) = parse_json_str::<Value>(&raw) {
                        let d = data.get("date").and_then(|v| v.as_str()).unwrap_or("").to_string();
                        let s = data.get("start").and_then(|v| v.as_str()).unwrap_or("").to_string();
                        if !d.is_empty() && !s.is_empty() {
                            let key = (d, s);
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
        }
    }

    let mut daily_counted: HashMap<String, i64> = HashMap::new();
    let mut cur = start_d;
    while cur <= end_d {
        daily_counted.insert(cur.format("%Y-%m-%d").to_string(), 0);
        cur += ChronoDuration::days(1);
    }

    let mut filtered_sessions: Vec<Value> = Vec::new();
    for (_, session) in unique_sessions {
        let d_str = session.get("date").and_then(|v| v.as_str()).unwrap_or("");
        if let Ok(sd) = NaiveDate::parse_from_str(d_str, "%Y-%m-%d") {
            if sd >= start_d && sd <= end_d {
                filtered_sessions.push(session);
            }
        }
    }

    let mut total_seconds = 0i64;
    let mut counted_seconds = 0i64;
    let mut app_times: HashMap<String, i64> = HashMap::new();
    let mut app_tags: HashMap<String, String> = HashMap::new();
    let mut app_exes: HashMap<String, String> = HashMap::new();
    let mut app_exclusions: HashMap<String, bool> = HashMap::new();
    let mut project_times: HashMap<String, i64> = HashMap::new();

    for session in &filtered_sessions {
        total_seconds += session.get("total_seconds").and_then(|v| v.as_i64()).unwrap_or(0);
        let c_secs = session.get("counted_seconds").and_then(|v| v.as_i64()).unwrap_or(0);
        counted_seconds += c_secs;
        let s_date = session.get("date").and_then(|v| v.as_str()).unwrap_or("");
        if let Some(entry) = daily_counted.get_mut(s_date) {
            *entry += c_secs;
        }
        if let Some(apps) = session.get("apps").and_then(|v| v.as_array()) {
            for app in apps {
                let name = app.get("name").and_then(|v| v.as_str()).unwrap_or("").to_string();
                if name.is_empty() {
                    continue;
                }
                let secs = app.get("seconds").and_then(|v| v.as_i64()).unwrap_or(0);
                let tag = app
                    .get("tag")
                    .and_then(|v| v.as_str())
                    .unwrap_or("Unassigned")
                    .to_string();
                let excluded = app.get("excluded").and_then(|v| v.as_bool()).unwrap_or(false);

                *app_times.entry(name.clone()).or_insert(0) += secs;
                app_tags.insert(name.clone(), tag.clone());
                let prev_ex = app_exclusions.entry(name.clone()).or_insert(excluded);
                if !excluded {
                    *prev_ex = false;
                }
                if let Some(exe) = session
                    .get("app_exe_paths")
                    .and_then(|v| v.get(&name))
                    .and_then(|v| v.as_str())
                {
                    if !exe.is_empty() {
                        app_exes.insert(name.clone(), exe.to_string());
                    }
                }
                if !excluded {
                    *project_times.entry(tag).or_insert(0) += secs;
                }
            }
        }
    }

    let mut app_list: Vec<HistoryAppItem> = app_times
        .into_iter()
        .map(|(name, secs)| {
            let pct = if total_seconds > 0 {
                round1((secs as f64 / total_seconds as f64) * 100.0)
            } else {
                0.0
            };
            HistoryAppItem {
                seconds: secs,
                formatted: format_duration(secs),
                percent: pct,
                excluded: *app_exclusions.get(&name).unwrap_or(&false),
                tag: app_tags
                    .get(&name)
                    .cloned()
                    .unwrap_or_else(|| "Unassigned".to_string()),
                exe_path: app_exes.get(&name).cloned().unwrap_or_default(),
                name,
            }
        })
        .collect();
    app_list.sort_by(|a, b| b.seconds.cmp(&a.seconds));

    let total_proj_counted: i64 = project_times.values().sum();
    let mut breakdown: Vec<ProjectBreakdownEntry> = project_times
        .into_iter()
        .map(|(proj, secs)| {
            let pct = if total_proj_counted > 0 {
                round1((secs as f64 / total_proj_counted as f64) * 100.0)
            } else {
                0.0
            };
            let earned = round2((secs as f64 / 3600.0) * hourly_rate);
            ProjectBreakdownEntry {
                color: project_color(&proj).to_string(),
                project: proj,
                seconds: secs,
                formatted: format_duration(secs),
                percent: pct,
                earned,
                earned_display: format_currency(currency_symbol, earned),
            }
        })
        .collect();
    breakdown.sort_by(|a, b| b.seconds.cmp(&a.seconds));

    let total_earned = if hourly_rate > 0.0 {
        round2(breakdown.iter().map(|b| b.earned).sum())
    } else {
        0.0
    };

    let total_days = (end_d - start_d).num_days() + 1;
    let mut daily_trend = Vec::new();
    let mut cur_d = start_d;
    while cur_d <= end_d {
        let d_str = cur_d.format("%Y-%m-%d").to_string();
        let secs = *daily_counted.get(&d_str).unwrap_or(&0);
        let label = if total_days <= 7 {
            cur_d.format("%a").to_string()
        } else {
            cur_d.format("%m/%d").to_string()
        };
        daily_trend.push(TrendBarItem {
            label,
            value: round2(secs as f64 / 3600.0),
        });
        cur_d += ChronoDuration::days(1);
    }

    HistoryInsightsDto {
        period: period.to_string(),
        total_seconds,
        total_formatted: format_duration(total_seconds),
        counted_seconds,
        counted_formatted: format_duration(counted_seconds),
        total_earned,
        total_earned_display: format_currency(currency_symbol, total_earned),
        apps: app_list,
        project_breakdown: breakdown,
        daily_trend,
        session_count: filtered_sessions.len(),
    }
}

pub fn get_activity_heatmap(paths: &ProfilePaths) -> Vec<HeatmapDayDto> {
    let rows = db::get_all_daily_summaries(paths).unwrap_or_default();
    rows.into_iter()
        .map(|r| HeatmapDayDto {
            date: r.date,
            total_seconds: r.total_seconds,
            session_count: r.session_count,
        })
        .collect()
}

pub fn scan_historical_app_exes(paths: &ProfilePaths) -> HashMap<String, String> {
    let mut map = HashMap::new();
    if let Ok(entries) = fs::read_dir(&paths.sessions_dir) {
        for entry in entries.flatten() {
            let p = entry.path();
            if p.extension().and_then(|e| e.to_str()) != Some("json") {
                continue;
            }
            if let Ok(raw) = fs::read_to_string(&p) {
                if let Ok(val) = parse_json_str::<Value>(&raw) {
                    if let Some(exes) = val.get("app_exe_paths").and_then(|v| v.as_object()) {
                        for (k, v) in exes {
                            if let Some(s) = v.as_str() {
                                if !s.is_empty() {
                                    map.entry(k.clone()).or_insert_with(|| s.to_string());
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    map
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn test_save_rename_and_trash_updates_daily_summary() {
        let tmp = TempDir::new().unwrap();
        let paths = ProfilePaths::from_root_and_profile(tmp.path().to_path_buf(), "Test".into());
        paths.ensure_dirs().unwrap();
        db::init_database(&paths).unwrap();

        let apps = vec![
            ("Visual Studio Code".to_string(), 1800.0, true, "Development".to_string()),
            ("YouTube".to_string(), 300.0, false, "Unassigned".to_string()),
        ];
        let timeline = vec![
            ("Visual Studio Code".to_string(), 1_700_000_000.0, 1_700_001_800.0),
        ];
        let mut inc = HashMap::new();
        inc.insert("Visual Studio Code".to_string(), true);
        inc.insert("YouTube".to_string(), false);
        let mut exes = HashMap::new();
        exes.insert("Visual Studio Code".to_string(), r"C:\Apps\Code.exe".to_string());

        let mut report = build_report_data(ReportInput {
            session_start_ts: 1_700_000_000.0,
            session_end_ts: 1_700_002_100.0,
            total_seconds: 2100,
            counted_seconds: 1800,
            apps: &apps,
            timeline: &timeline,
            app_included: &inc,
            app_exe_paths: &exes,
            is_recovered: false,
            is_resumed: false,
            resumed_filepath: None,
            session_name: "Session - 10:13 AM",
            hourly_rate: 60.0,
            currency_symbol: "$",
        });

        assert!(report.session_name.starts_with("Development — "));
        assert_eq!(report.total_earned, 30.0);

        let saved_path = save_to_history(&paths, &mut report).unwrap();
        assert!(saved_path.exists());

        let date_str = report.date.clone();
        let row = db::get_daily_summary(&paths, &date_str).unwrap().unwrap();
        assert_eq!(row.session_count, 1);
        assert_eq!(row.total_seconds, 2100);

        // Non-destructive review rename
        let renamed = rename_saved_session(&saved_path, "Sprint Review").unwrap();
        assert_eq!(renamed, "Sprint Review");
        let loaded: Value =
            serde_json::from_str(&fs::read_to_string(&saved_path).unwrap()).unwrap();
        assert_eq!(loaded.get("session_name").and_then(|v| v.as_str()), Some("Sprint Review"));

        // Explicit Move to Trash updates daily_summary back to 0 sessions
        let trashed = move_session_to_trash(&paths, &saved_path).unwrap();
        assert!(!saved_path.exists());
        assert!(trashed.exists());

        let row_after = db::get_daily_summary(&paths, &date_str).unwrap().unwrap();
        assert_eq!(row_after.session_count, 0);
        assert_eq!(row_after.total_seconds, 0);

        // Same-second collision creates unique suffixed files rather than overwriting
        let mut r1 = build_report_data(ReportInput {
            session_start_ts: 1_700_005_000.0,
            session_end_ts: 1_700_005_010.0,
            total_seconds: 10,
            counted_seconds: 10,
            apps: &apps,
            timeline: &timeline,
            app_included: &inc,
            app_exe_paths: &exes,
            is_recovered: false,
            is_resumed: false,
            resumed_filepath: None,
            session_name: "First",
            hourly_rate: 10.0,
            currency_symbol: "$",
        });
        let mut r2 = r1.clone();
        r2.session_name = "Second".to_string();
        let p1 = save_to_history(&paths, &mut r1).unwrap();
        let p2 = save_to_history(&paths, &mut r2).unwrap();
        assert_ne!(p1, p2);
        assert!(p1.exists() && p2.exists());
    }

    #[test]
    fn test_merge_restore_delete_export_and_history_aggregation() {
        let tmp = TempDir::new().unwrap();
        let paths = ProfilePaths::from_root_and_profile(tmp.path().to_path_buf(), "Test".into());
        paths.ensure_dirs().unwrap();
        db::init_database(&paths).unwrap();

        let today_str = Local::now().format("%Y-%m-%d").to_string();
        let f1 = paths.sessions_dir.join("session_merge_1.json");
        let f2 = paths.sessions_dir.join("session_merge_2.json");

        fs::write(
            &f1,
            serde_json::to_string_pretty(&serde_json::json!({
                "date": today_str,
                "start": "09:00:00",
                "end": "09:30:00",
                "total_seconds": 1800,
                "counted_seconds": 1800,
                "session_name": "Part 1",
                "hourly_rate": 40.0,
                "currency_symbol": "$",
                "apps": [{"name": "VS Code", "seconds": 1800, "excluded": false, "tag": "Development"}],
                "timeline": [{"app": "VS Code", "start": "09:00:00", "end": "09:30:00"}]
            }))
            .unwrap(),
        )
        .unwrap();
        fs::write(
            &f2,
            serde_json::to_string_pretty(&serde_json::json!({
                "date": today_str,
                "start": "10:00:00",
                "end": "10:30:00",
                "total_seconds": 1800,
                "counted_seconds": 1800,
                "session_name": "Part 2",
                "hourly_rate": 40.0,
                "currency_symbol": "$",
                "apps": [
                    {"name": "VS Code", "seconds": 900, "excluded": false, "tag": "Development"},
                    {"name": "Figma", "seconds": 900, "excluded": false, "tag": "Design"}
                ],
                "timeline": [{"app": "Figma", "start": "10:15:00", "end": "10:30:00"}]
            }))
            .unwrap(),
        )
        .unwrap();

        // Validation guards on merge_session_files
        assert!(merge_session_files(&paths, &[f1.clone(), f2.clone()], "   ").is_err());
        assert!(merge_session_files(&paths, &[f1.clone()], "Combined").is_err());

        let merged_path = merge_session_files(&paths, &[f1.clone(), f2.clone()], "Combined Sprint").unwrap();
        assert!(merged_path.exists());
        let merged = load_session_report(&merged_path).unwrap();
        assert_eq!(merged.session_name, "Combined Sprint");
        assert_eq!(merged.counted_seconds, 3600);
        assert_eq!(merged.apps[0].name, "VS Code");
        assert_eq!(merged.apps[0].seconds, 2700);
        assert_eq!(merged.project_breakdown.len(), 2);

        // History aggregation today: merged shares earliest start ("09:00:00") with f1,
        // so (date, start) deduplication deterministically picks the fuller merged session.
        let hist = aggregate_history_data(&paths, "today", 40.0, "$");
        assert_eq!(hist.session_count, 2);
        assert_eq!(hist.counted_seconds, 5400);

        // Export txt & HTML generation
        let txt_path = tmp.path().join("report.txt");
        export_txt(&merged, &txt_path).unwrap();
        let txt_body = fs::read_to_string(&txt_path).unwrap();
        assert!(txt_body.contains("FOCUSLOG SESSION REPORT"));
        assert!(txt_body.contains("VS Code"));

        let html = generate_session_report_html(&paths, &merged);
        assert!(html.contains("Combined Sprint"));
        assert!(html.contains("VS Code"));

        // Trash -> Restore roundtrip
        let trashed = move_session_to_trash(&paths, &merged_path).unwrap();
        assert!(!merged_path.exists() && trashed.exists());
        let restored = restore_session_from_trash(&paths, &trashed).unwrap();
        assert!(restored.exists() && !trashed.exists());

        // Path traversal / outside-folder delete guard
        let outside = tmp.path().join("outside.json");
        fs::write(&outside, "{}").unwrap();
        assert!(delete_saved_file(&paths, &outside, "sessions").is_err());
        assert!(outside.exists());

        delete_saved_file(&paths, &restored, "sessions").unwrap();
        assert!(!restored.exists());
    }

    #[test]
    fn test_list_session_files_sorts_chronologically_before_mtime() {
        let tmp = TempDir::new().unwrap();
        let dir = tmp.path().join("sessions");
        fs::create_dir_all(&dir).unwrap();

        let newer_session = dir.join("session_2026-11-15_09-00-00.json");
        fs::write(
            &newer_session,
            r#"{"session_name":"Newer Session","date":"2026-11-15","start":"09:00:00","total_seconds":60,"counted_seconds":60,"apps":[]}"#,
        )
        .unwrap();
        // Wait so the older-dated file gets a newer filesystem mtime
        std::thread::sleep(std::time::Duration::from_millis(25));
        let older_session_newer_mtime = dir.join("session_2026-11-10_08-00-00.json");
        fs::write(
            &older_session_newer_mtime,
            r#"{"session_name":"Older Date","date":"2026-11-10","start":"08:00:00","total_seconds":60,"counted_seconds":60,"apps":[]}"#,
        )
        .unwrap();

        let listed = list_session_files(&dir);
        assert_eq!(listed.len(), 2);
        assert_eq!(listed[0].session_name, "Newer Session");
        assert!(listed[0].is_latest);
        assert_eq!(listed[1].session_name, "Older Date");
        assert!(!listed[1].is_latest);
    }

    #[test]
    fn utf8_bom_session_json_loads_and_lists() {
        let tmp = TempDir::new().unwrap();
        let dir = tmp.path().join("sessions");
        fs::create_dir_all(&dir).unwrap();

        let bom_path = dir.join("session_2026-11-16_09-00-00.json");
        let payload = concat!(
            "\u{feff}",
            r#"{"session_name":"BOM Session","date":"2026-11-16","start":"09:00:00","end":"09:10:00","total_seconds":600,"counted_seconds":600,"hourly_rate":10.0,"currency_symbol":"$","apps":[{"name":"Notepad","seconds":600,"excluded":false,"tag":"Research"}]}"#
        );
        fs::write(&bom_path, payload).unwrap();

        let listed = list_session_files(&dir);
        assert_eq!(listed.len(), 1);
        assert_eq!(listed[0].session_name, "BOM Session");

        let loaded = load_session_report(&bom_path).unwrap();
        assert_eq!(loaded.session_name, "BOM Session");
        assert_eq!(loaded.counted_seconds, 600);
        assert_eq!(loaded.apps.len(), 1);
    }
}
