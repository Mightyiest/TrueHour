use crate::config::atomic_write_str;
use crate::net::http_request;
use chrono::{DateTime, Local, Utc};
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::{Instant, SystemTime, UNIX_EPOCH};

pub const DRIFT_THRESHOLD: f64 = 5.0;

pub const NTP_SOURCES: &[&str] = &[
    "https://www.google.com",
    "https://www.microsoft.com",
    "https://www.cloudflare.com",
    "https://timeapi.io/api/time/current/zone?timeZone=UTC",
];

/// Fast O(line_len) reverse binary seek returning the last non-empty UTF-8 line of a potentially
/// hundreds-of-megabytes JSONL file without loading the file into RAM.
pub fn get_last_line(path: &Path) -> Option<String> {
    let mut file = File::open(path).ok()?;
    let mut end_pos = file.seek(SeekFrom::End(0)).ok()?;
    if end_pos == 0 {
        return None;
    }

    const CHUNK_SIZE: u64 = 4096;
    let mut buf = [0u8; CHUNK_SIZE as usize];

    // Step 1: Trim trailing whitespace/newlines from the end of the file.
    while end_pos > 0 {
        let start = end_pos.saturating_sub(CHUNK_SIZE);
        let len = (end_pos - start) as usize;
        file.seek(SeekFrom::Start(start)).ok()?;
        file.read_exact(&mut buf[..len]).ok()?;

        if let Some(rel_non_ws) = buf[..len]
            .iter()
            .rposition(|&b| b != b'\n' && b != b'\r' && b != b' ' && b != b'\t')
        {
            end_pos = start + rel_non_ws as u64 + 1;
            break;
        }
        end_pos = start;
    }

    if end_pos == 0 {
        return None;
    }

    // Step 2: Walk backward from `end_pos` to find the preceding '\n' or start of file.
    let mut scan_pos = end_pos;
    let mut line_start = 0u64;
    while scan_pos > 0 {
        let start = scan_pos.saturating_sub(CHUNK_SIZE);
        let len = (scan_pos - start) as usize;
        file.seek(SeekFrom::Start(start)).ok()?;
        file.read_exact(&mut buf[..len]).ok()?;

        if let Some(rel_nl) = buf[..len].iter().rposition(|&b| b == b'\n') {
            line_start = start + rel_nl as u64 + 1;
            break;
        }
        scan_pos = start;
    }

    let line_len = (end_pos - line_start) as usize;
    let mut line_bytes = vec![0u8; line_len];
    file.seek(SeekFrom::Start(line_start)).ok()?;
    file.read_exact(&mut line_bytes).ok()?;
    let s = String::from_utf8(line_bytes).ok()?;
    let trimmed = s.trim();
    if trimmed.is_empty() {
        None
    } else {
        Some(trimmed.to_string())
    }
}

/// Migrates legacy single-object `{"chain": [...]}` `time_chain.json` files to JSONL format.
pub fn check_and_migrate_chain_file(chain_file: &Path) {
    if !chain_file.exists() {
        return;
    }
    let Ok(meta) = fs::metadata(chain_file) else {
        return;
    };
    if meta.len() == 0 {
        return;
    }

    let Ok(mut f) = File::open(chain_file) else {
        return;
    };
    let mut prefix = [0u8; 128];
    let n = f.read(&mut prefix).unwrap_or(0);
    let header = String::from_utf8_lossy(&prefix[..n]).trim().to_string();
    drop(f);

    if header.starts_with('{') && header.contains("\"chain\"") {
        if let Ok(raw) = fs::read_to_string(chain_file) {
            if let Ok(val) = serde_json::from_str::<Value>(raw.trim_start_matches('\u{feff}')) {
                if let Some(chain) = val.get("chain").and_then(|c| c.as_array()) {
                    let mut out = String::new();
                    for entry in chain {
                        if let Ok(line) = serde_json::to_string(entry) {
                            out.push_str(&line);
                            out.push('\n');
                        }
                    }
                    let _ = atomic_write_str(chain_file, &out);
                }
            }
        }
    }
}

/// Serializes any JSON `Value` using Python `json.dumps(..., sort_keys=True)` canonical form
/// (`", "` and `": "` separators, recursively sorted keys, `ensure_ascii=True` string escaping)
/// so SHA-256 hashes match Python `secure_time.py` byte-for-byte.
pub fn to_python_canonical_json(value: &Value) -> String {
    let mut out = String::new();
    write_canonical_json(value, &mut out);
    out
}

fn write_canonical_json(value: &Value, out: &mut String) {
    match value {
        Value::Null => out.push_str("null"),
        Value::Bool(b) => out.push_str(if *b { "true" } else { "false" }),
        Value::Number(n) => out.push_str(&n.to_string()),
        Value::String(s) => write_python_escaped_string(s, out),
        Value::Array(arr) => {
            out.push('[');
            for (i, item) in arr.iter().enumerate() {
                if i > 0 {
                    out.push_str(", ");
                }
                write_canonical_json(item, out);
            }
            out.push(']');
        }
        Value::Object(map) => {
            let sorted: BTreeMap<&String, &Value> = map.iter().collect();
            out.push('{');
            for (i, (k, v)) in sorted.into_iter().enumerate() {
                if i > 0 {
                    out.push_str(", ");
                }
                write_python_escaped_string(k, out);
                out.push_str(": ");
                write_canonical_json(v, out);
            }
            out.push('}');
        }
    }
}

fn write_python_escaped_string(s: &str, out: &mut String) {
    out.push('"');
    for ch in s.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\u{0008}' => out.push_str("\\b"),
            '\u{000C}' => out.push_str("\\f"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 || ((c as u32) >= 0x7f && (c as u32) <= 0x9f) => {
                out.push_str(&format!("\\u{:04x}", c as u32));
            }
            c if (c as u32) < 0x80 => out.push(c),
            c => {
                let mut utf16 = [0u16; 2];
                for code_unit in c.encode_utf16(&mut utf16) {
                    out.push_str(&format!("\\u{:04x}", code_unit));
                }
            }
        }
    }
    out.push('"');
}

pub fn hash_chain_entry_fields(entry_without_hash: &Value) -> String {
    let canonical = to_python_canonical_json(entry_without_hash);
    let mut hasher = Sha256::new();
    hasher.update(canonical.as_bytes());
    hex::encode(hasher.finalize())
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SecurityEvent {
    pub timestamp: String,
    pub event_type: String,
    pub details: Value,
    pub trust_score: i32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ValidationResult {
    pub duration_seconds: f64,
    pub integrity_status: String,
    pub trust_score: i32,
    pub monotonic_elapsed: f64,
    pub discrepancy: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionSecurityReport {
    pub trust_score: i32,
    pub trust_level: String,
    pub tamper_events_count: usize,
    pub chain_length: usize,
    pub chain_valid: bool,
    pub network_syncs: usize,
    pub events: Vec<SecurityEvent>,
}

struct DetectorInner {
    time_chain_file: PathBuf,
    security_log_file: PathBuf,
    origin_instant: Instant,
    monotonic_start: Option<f64>,
    system_start: Option<f64>,
    last_monotonic: Option<f64>,
    last_system: Option<f64>,
    last_network_sync: Option<f64>,
    network_time_offset: f64,
    trust_score: i32,
    tamper_events: Vec<SecurityEvent>,
    chain_data: Vec<Value>,
    last_historic_hash: String,
    appended_count: usize,
    verified_len: usize,
    cached_chain_valid: bool,
    last_trust_recovery: f64,
    network_sync_fn: Arc<dyn Fn(u64) -> Option<f64> + Send + Sync>,
    session_gen: u64,
    session_ended: bool,
}

fn unix_now_f64() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

fn default_network_sync(timeout_secs: u64) -> Option<f64> {
    let timeout_ms = (timeout_secs.max(1) * 1000) as i32;
    for url in NTP_SOURCES {
        let is_json_api = url.contains("api") || url.contains("timezone");
        let method = if is_json_api { "GET" } else { "HEAD" };
        if let Ok(resp) = http_request(method, url, timeout_ms) {
            if let Some(date_hdr) = resp.date_header {
                if let Ok(dt) = DateTime::parse_from_rfc2822(&date_hdr) {
                    let net_utc = dt.with_timezone(&Utc);
                    let sys_utc = Utc::now();
                    let diff = (sys_utc - net_utc).num_milliseconds() as f64 / 1000.0;
                    return Some(diff);
                }
            }
            if is_json_api && !resp.body.is_empty() {
                if let Ok(v) = serde_json::from_str::<Value>(&resp.body) {
                    if let Some(dt_str) = v
                        .get("dateTime")
                        .or_else(|| v.get("datetime"))
                        .and_then(|d| d.as_str())
                    {
                        let normalized = if dt_str.ends_with('Z') || dt_str.contains('+') {
                            dt_str.to_string()
                        } else {
                            format!("{dt_str}Z")
                        };
                        if let Ok(dt) = DateTime::parse_from_rfc3339(&normalized) {
                            let net_utc = dt.with_timezone(&Utc);
                            let sys_utc = Utc::now();
                            let diff = (sys_utc - net_utc).num_milliseconds() as f64 / 1000.0;
                            return Some(diff);
                        }
                    }
                }
            }
        }
    }
    None
}

#[derive(Clone)]
pub struct TimeTamperDetector {
    inner: Arc<Mutex<DetectorInner>>,
    validation_gate: Arc<Mutex<()>>,
}

impl TimeTamperDetector {
    pub fn new(time_chain_file: PathBuf, security_log_file: PathBuf) -> Self {
        let mut inner = DetectorInner {
            time_chain_file,
            security_log_file,
            origin_instant: Instant::now(),
            monotonic_start: None,
            system_start: None,
            last_monotonic: None,
            last_system: None,
            last_network_sync: None,
            network_time_offset: 0.0,
            trust_score: 100,
            tamper_events: Vec::new(),
            chain_data: Vec::new(),
            last_historic_hash: "GENESIS".to_string(),
            appended_count: 0,
            verified_len: 0,
            cached_chain_valid: true,
            last_trust_recovery: unix_now_f64(),
            network_sync_fn: Arc::new(default_network_sync),
            session_gen: 0,
            session_ended: false,
        };
        Self::load_chain_locked(&mut inner);
        Self {
            inner: Arc::new(Mutex::new(inner)),
            validation_gate: Arc::new(Mutex::new(())),
        }
    }

    #[cfg(test)]
    pub fn with_mock_network(
        time_chain_file: PathBuf,
        security_log_file: PathBuf,
        sync_fn: impl Fn(u64) -> Option<f64> + Send + Sync + 'static,
    ) -> Self {
        let det = Self::new(time_chain_file, security_log_file);
        {
            let mut guard = det.inner.lock().unwrap();
            guard.network_sync_fn = Arc::new(sync_fn);
        }
        det
    }

    fn load_chain_locked(inner: &mut DetectorInner) {
        inner.chain_data.clear();
        inner.appended_count = 0;
        inner.verified_len = 0;
        inner.cached_chain_valid = true;
        inner.last_historic_hash = "GENESIS".to_string();

        check_and_migrate_chain_file(&inner.time_chain_file);

        if inner.time_chain_file.exists() {
            if let Some(last_line) = get_last_line(&inner.time_chain_file) {
                if let Ok(val) =
                    serde_json::from_str::<Value>(last_line.trim_start_matches('\u{feff}'))
                {
                    if let Some(h) = val.get("hash").and_then(|v| v.as_str()) {
                        if !h.is_empty() {
                            inner.last_historic_hash = h.to_string();
                        }
                    }
                }
            }
        }
    }

    fn save_chain_locked(inner: &mut DetectorInner) {
        if inner.appended_count >= inner.chain_data.len() {
            return;
        }
        let unsaved = &inner.chain_data[inner.appended_count..];
        if let Some(parent) = inner.time_chain_file.parent() {
            let _ = fs::create_dir_all(parent);
        }
        if let Ok(mut f) = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&inner.time_chain_file)
        {
            let mut ok = true;
            for entry in unsaved {
                if let Ok(line) = serde_json::to_string(entry) {
                    if writeln!(f, "{line}").is_err() {
                        ok = false;
                        break;
                    }
                }
            }
            if ok {
                let _ = f.flush();
                inner.appended_count = inner.chain_data.len();
            }
        }
    }

    fn log_security_event_locked(inner: &mut DetectorInner, event_type: &str, details: Value) {
        let event = SecurityEvent {
            timestamp: Local::now().format("%Y-%m-%dT%H:%M:%S%.6f").to_string(),
            event_type: event_type.to_string(),
            details,
            trust_score: inner.trust_score,
        };
        inner.tamper_events.push(event.clone());
        if inner.tamper_events.len() > 1000 {
            let drain = inner.tamper_events.len() - 1000;
            inner.tamper_events.drain(0..drain);
        }

        let mut all_events: Vec<SecurityEvent> = if inner.security_log_file.exists() {
            fs::read_to_string(&inner.security_log_file)
                .ok()
                .and_then(|raw| serde_json::from_str(raw.trim_start_matches('\u{feff}')).ok())
                .unwrap_or_default()
        } else {
            Vec::new()
        };

        all_events.push(event);
        if all_events.len() > 5000 {
            let drain = all_events.len() - 5000;
            all_events.drain(0..drain);
        }

        if let Ok(json_str) = serde_json::to_string_pretty(&all_events) {
            let _ = atomic_write_str(&inner.security_log_file, &json_str);
        }
    }

    fn add_to_chain_locked(inner: &mut DetectorInner, event_type: &str, data: Value) -> String {
        let previous_hash = inner
            .chain_data
            .last()
            .and_then(|e| e.get("hash").and_then(|h| h.as_str()))
            .map(|s| s.to_string())
            .unwrap_or_else(|| inner.last_historic_hash.clone());

        let timestamp = Local::now().format("%Y-%m-%dT%H:%M:%S%.6f").to_string();
        let entry_without_hash = json!({
            "event_type": event_type,
            "data": data,
            "previous_hash": previous_hash,
            "timestamp": timestamp,
        });

        let entry_hash = hash_chain_entry_fields(&entry_without_hash);

        let mut full_map = match entry_without_hash {
            Value::Object(m) => m,
            _ => Map::new(),
        };
        full_map.insert("hash".to_string(), Value::String(entry_hash.clone()));
        inner.chain_data.push(Value::Object(full_map));

        if inner.chain_data.len() % 10 == 0 {
            Self::save_chain_locked(inner);
        }

        entry_hash
    }

    pub fn start_session(&self) {
        let mut inner = self.inner.lock().unwrap();
        inner.session_gen = inner.session_gen.wrapping_add(1);
        inner.session_ended = false;
        let gen = inner.session_gen;
        let mono_now = inner.origin_instant.elapsed().as_secs_f64();
        let sys_now = unix_now_f64();
        inner.monotonic_start = Some(mono_now);
        inner.system_start = Some(sys_now);
        inner.last_monotonic = Some(mono_now);
        inner.last_system = Some(sys_now);
        inner.trust_score = 100;
        inner.tamper_events.clear();
        inner.chain_data.clear();
        inner.appended_count = 0;
        inner.last_network_sync = None;
        inner.network_time_offset = 0.0;
        inner.last_trust_recovery = sys_now;
        Self::load_chain_locked(&mut inner);

        Self::add_to_chain_locked(
            &mut inner,
            "SESSION_START",
            json!({
                "monotonic": mono_now,
                "system": sys_now,
                "timestamp": Local::now().format("%Y-%m-%dT%H:%M:%S%.6f").to_string(),
            }),
        );

        let sync_fn = Arc::clone(&inner.network_sync_fn);
        let cloned = Arc::clone(&self.inner);
        drop(inner);

        std::thread::spawn(move || {
            let offset = (sync_fn)(3);
            if let Some(off) = offset {
                let mut g = cloned.lock().unwrap();
                if g.session_gen != gen || g.session_ended {
                    return;
                }
                g.network_time_offset = off;
                g.last_network_sync = Some(unix_now_f64());
                if off.abs() > DRIFT_THRESHOLD {
                    g.trust_score = (g.trust_score - 30).max(0);
                    Self::log_security_event_locked(
                        &mut g,
                        "CLOCK_DRIFT_DETECTED",
                        json!({"offset_seconds": off, "phase": "session_start"}),
                    );
                } else {
                    g.trust_score = (g.trust_score + 10).min(100);
                }
            }
        });
    }

    pub fn validate_and_record(&self, app_name: &str, duration_seconds: f64) -> ValidationResult {
        let gen_at_entry = {
            let g = self.inner.lock().unwrap();
            if g.session_ended {
                return Self::ended_noop_result(
                    &g,
                    duration_seconds,
                    g.origin_instant.elapsed().as_secs_f64(),
                );
            }
            g.session_gen
        };
        let _gate = self.validation_gate.lock().unwrap();
        let (mono_now, sys_now) = {
            let g = self.inner.lock().unwrap();
            (g.origin_instant.elapsed().as_secs_f64(), unix_now_f64())
        };
        self.validate_and_record_at_locked(
            app_name,
            duration_seconds,
            mono_now,
            sys_now,
            gen_at_entry,
        )
    }

    /// Deterministic testable entrypoint accepting explicit monotonic and system clocks.
    pub fn validate_and_record_at(
        &self,
        app_name: &str,
        duration_seconds: f64,
        current_monotonic: f64,
        current_system: f64,
    ) -> ValidationResult {
        let gen_at_entry = {
            let g = self.inner.lock().unwrap();
            if g.session_ended {
                return Self::ended_noop_result(&g, duration_seconds, current_monotonic);
            }
            g.session_gen
        };
        let _gate = self.validation_gate.lock().unwrap();
        self.validate_and_record_at_locked(
            app_name,
            duration_seconds,
            current_monotonic,
            current_system,
            gen_at_entry,
        )
    }

    fn ended_noop_result(
        inner: &DetectorInner,
        duration_seconds: f64,
        current_monotonic: f64,
    ) -> ValidationResult {
        let mono_start = inner.monotonic_start.unwrap_or(current_monotonic);
        let expected_monotonic_elapsed = (current_monotonic - mono_start).max(0.0);
        ValidationResult {
            duration_seconds,
            integrity_status: "VALID".to_string(),
            trust_score: inner.trust_score,
            monotonic_elapsed: expected_monotonic_elapsed,
            discrepancy: 0.0,
        }
    }

    fn validate_and_record_at_locked(
        &self,
        app_name: &str,
        duration_seconds: f64,
        current_monotonic: f64,
        current_system: f64,
        gen_at_entry: u64,
    ) -> ValidationResult {
        let mut inner = self.inner.lock().unwrap();
        if inner.session_gen != gen_at_entry || inner.session_ended {
            return Self::ended_noop_result(&inner, duration_seconds, current_monotonic);
        }
        if inner.monotonic_start.is_none() {
            inner.monotonic_start = Some(current_monotonic);
        }
        if inner.system_start.is_none() {
            inner.system_start = Some(current_system);
        }
        let last_mono = inner.last_monotonic.unwrap_or(current_monotonic);
        let last_sys = inner.last_system.unwrap_or(current_system);

        let monotonic_tick_elapsed = current_monotonic - last_mono;
        let system_tick_elapsed = current_system - last_sys;
        let sleep_time = system_tick_elapsed - monotonic_tick_elapsed;

        inner.last_monotonic = Some(current_monotonic);
        inner.last_system = Some(current_system);

        // Release mutex across blocking WinHTTP network time verification so concurrent
        // get_session_report() / end_session() callers never block on network I/O.
        if sleep_time > 5.0 {
            let sync_fn = Arc::clone(&inner.network_sync_fn);
            let gen_before = inner.session_gen;
            drop(inner);

            let net_offset = (sync_fn)(1);

            inner = self.inner.lock().unwrap();
            if inner.session_gen != gen_before || inner.session_ended {
                return Self::ended_noop_result(&inner, duration_seconds, current_monotonic);
            }

            if let Some(off) = net_offset {
                if (off - inner.network_time_offset).abs() <= DRIFT_THRESHOLD {
                    if let Some(ref mut sys_start) = inner.system_start {
                        *sys_start += sleep_time;
                    }
                    inner.network_time_offset = off;
                    inner.last_network_sync = Some(current_system);
                }
            }
        }

        let mono_start = inner.monotonic_start.unwrap_or(current_monotonic);
        let sys_start = inner.system_start.unwrap_or(current_system);
        let expected_monotonic_elapsed = current_monotonic - mono_start;
        let expected_system_elapsed = current_system - sys_start;
        let discrepancy = (expected_monotonic_elapsed - expected_system_elapsed).abs();

        let mut integrity_status = "VALID".to_string();
        if discrepancy > DRIFT_THRESHOLD {
            integrity_status = "TAMPER_DETECTED".to_string();
            inner.trust_score = (inner.trust_score - 20).max(0);
            Self::log_security_event_locked(
                &mut inner,
                "TIME_DISCREPANCY",
                json!({
                    "discrepancy_seconds": discrepancy,
                    "app": app_name,
                    "reported_duration": duration_seconds,
                    "monotonic_elapsed": expected_monotonic_elapsed,
                    "system_elapsed": expected_system_elapsed,
                }),
            );
        } else if discrepancy > 1.0 {
            integrity_status = "SUSPICIOUS".to_string();
            inner.trust_score = (inner.trust_score - 5).max(0);
        }

        let need_periodic_sync = match inner.last_network_sync {
            None => true,
            Some(prev) => (current_system - prev) > 900.0,
        };
        if need_periodic_sync {
            inner.last_network_sync = Some(current_system);
            let gen_periodic = inner.session_gen;
            let sync_fn = Arc::clone(&inner.network_sync_fn);
            let cloned = Arc::clone(&self.inner);
            std::thread::spawn(move || {
                let offset = (sync_fn)(2);
                if let Some(off) = offset {
                    let mut g = cloned.lock().unwrap();
                    if g.session_gen != gen_periodic || g.session_ended {
                        return;
                    }
                    let old_off = g.network_time_offset;
                    g.network_time_offset = off;
                    g.last_network_sync = Some(unix_now_f64());
                    if (off - old_off).abs() > DRIFT_THRESHOLD {
                        g.trust_score = (g.trust_score - 25).max(0);
                        Self::log_security_event_locked(
                            &mut g,
                            "NETWORK_TIME_MISMATCH",
                            json!({
                                "old_offset": old_off,
                                "new_offset": off,
                                "change_detected": (off - old_off).abs(),
                            }),
                        );
                    }
                }
            });
        }

        Self::add_to_chain_locked(
            &mut inner,
            "TRACKING_ENTRY",
            json!({
                "app": app_name,
                "duration": duration_seconds,
                "monotonic_time": current_monotonic,
                "system_time": current_system,
                "integrity_status": integrity_status,
            }),
        );

        if integrity_status == "VALID"
            && inner.trust_score < 100
            && (current_system - inner.last_trust_recovery) > 300.0
        {
            inner.trust_score = (inner.trust_score + 1).min(100);
            inner.last_trust_recovery = current_system;
        }

        ValidationResult {
            duration_seconds,
            integrity_status,
            trust_score: inner.trust_score,
            monotonic_elapsed: expected_monotonic_elapsed,
            discrepancy,
        }
    }

    pub fn end_session(&self) -> SessionSecurityReport {
        let mut inner = self.inner.lock().unwrap();
        inner.session_ended = true;
        let mono_end = inner.origin_instant.elapsed().as_secs_f64();
        let sys_end = unix_now_f64();
        let final_trust = inner.trust_score;
        let events_len = inner.tamper_events.len();

        Self::add_to_chain_locked(
            &mut inner,
            "SESSION_END",
            json!({
                "monotonic_end": mono_end,
                "system_end": sys_end,
                "final_trust_score": final_trust,
                "total_tamper_events": events_len,
            }),
        );
        Self::save_chain_locked(&mut inner);
        Self::build_report_locked(&mut inner, true)
    }

    pub fn verify_chain_integrity(&self) -> bool {
        let mut inner = self.inner.lock().unwrap();
        Self::verify_chain_range_locked(&mut inner, 0)
    }

    fn verify_chain_incremental_locked(inner: &mut DetectorInner) -> bool {
        if !inner.cached_chain_valid {
            return false;
        }
        let start = inner.verified_len.min(inner.chain_data.len());
        Self::verify_chain_range_locked(inner, start)
    }

    fn verify_chain_range_locked(inner: &mut DetectorInner, start_idx: usize) -> bool {
        if inner.chain_data.is_empty() {
            inner.verified_len = 0;
            inner.cached_chain_valid = true;
            return true;
        }
        let historic = inner.last_historic_hash.clone();
        for i in start_idx..inner.chain_data.len() {
            let expected_prev = if i == 0 {
                historic.clone()
            } else {
                inner.chain_data[i - 1]
                    .get("hash")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_string()
            };

            let entry = &inner.chain_data[i];
            let actual_prev = entry
                .get("previous_hash")
                .and_then(|v| v.as_str())
                .unwrap_or("");
            if actual_prev != expected_prev {
                inner.cached_chain_valid = false;
                return false;
            }

            let Some(obj) = entry.as_object() else {
                inner.cached_chain_valid = false;
                return false;
            };
            let mut stripped = Map::new();
            for (k, v) in obj {
                if k != "hash" {
                    stripped.insert(k.clone(), v.clone());
                }
            }
            let computed = hash_chain_entry_fields(&Value::Object(stripped));
            let stored = entry.get("hash").and_then(|v| v.as_str()).unwrap_or("");
            if computed != stored {
                Self::log_security_event_locked(
                    inner,
                    "CHAIN_TAMPER_DETECTED",
                    json!({"entry_index": i, "computed_hash": computed}),
                );
                inner.cached_chain_valid = false;
                return false;
            }
        }
        inner.verified_len = inner.chain_data.len();
        inner.cached_chain_valid = true;
        true
    }

    pub fn trust_level_for(score: i32) -> &'static str {
        if score >= 90 {
            "HIGH"
        } else if score >= 70 {
            "MEDIUM"
        } else if score >= 50 {
            "LOW"
        } else {
            "COMPROMISED"
        }
    }

    fn build_report_locked(inner: &mut DetectorInner, full_verify: bool) -> SessionSecurityReport {
        let valid = if full_verify {
            Self::verify_chain_range_locked(inner, 0)
        } else {
            Self::verify_chain_incremental_locked(inner)
        };
        let tail_start = inner.tamper_events.len().saturating_sub(20);
        SessionSecurityReport {
            trust_score: inner.trust_score,
            trust_level: Self::trust_level_for(inner.trust_score).to_string(),
            tamper_events_count: inner.tamper_events.len(),
            chain_length: inner.chain_data.len(),
            chain_valid: valid,
            network_syncs: usize::from(inner.last_network_sync.is_some()),
            events: inner.tamper_events[tail_start..].to_vec(),
        }
    }

    pub fn get_session_report(&self) -> SessionSecurityReport {
        let mut inner = self.inner.lock().unwrap();
        Self::build_report_locked(&mut inner, false)
    }

    #[cfg(test)]
    pub fn force_set_starts_for_test(&self, mono: f64, sys: f64) {
        let mut inner = self.inner.lock().unwrap();
        inner.monotonic_start = Some(mono);
        inner.system_start = Some(sys);
        inner.last_monotonic = Some(mono);
        inner.last_system = Some(sys);
    }

    #[cfg(test)]
    pub fn tamper_entry_for_test(&self, idx: usize, new_app: &str) {
        let mut inner = self.inner.lock().unwrap();
        if let Some(Value::Object(map)) = inner.chain_data.get_mut(idx) {
            if let Some(Value::Object(data)) = map.get_mut("data") {
                data.insert("app".to_string(), Value::String(new_app.to_string()));
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn test_canonical_json_matches_python_hash() {
        // Cross-check exact SHA-256 produced by Python:
        // json.dumps({"event_type":"SESSION_START","data":{"a":1,"b":"hi \u2014 test"},"previous_hash":"GENESIS","timestamp":"2026-11-15T12:00:00"}, sort_keys=True)
        let v = json!({
            "event_type": "SESSION_START",
            "data": {"b": "hi \u{2014} test", "a": 1},
            "previous_hash": "GENESIS",
            "timestamp": "2026-11-15T12:00:00"
        });
        let canon = to_python_canonical_json(&v);
        assert_eq!(
            canon,
            r#"{"data": {"a": 1, "b": "hi \u2014 test"}, "event_type": "SESSION_START", "previous_hash": "GENESIS", "timestamp": "2026-11-15T12:00:00"}"#
        );
    }

    #[test]
    fn test_reverse_seek_large_file_tail() {
        let tmp = TempDir::new().unwrap();
        let chain_path = tmp.path().join("time_chain.json");
        {
            let mut f = File::create(&chain_path).unwrap();
            for i in 0..5000 {
                writeln!(f, r#"{{"seq": {i}, "hash": "h_{i}"}}"#).unwrap();
            }
            // Also trailing blank lines
            writeln!(f).unwrap();
            writeln!(f, "   ").unwrap();
        }
        let last = get_last_line(&chain_path).unwrap();
        assert!(last.contains(r#""seq": 4999"#));
    }

    #[test]
    fn test_tamper_detection_and_os_suspend_recovery() {
        let tmp = TempDir::new().unwrap();
        let chain_path = tmp.path().join("time_chain.json");
        let log_path = tmp.path().join("security_log.json");

        let det = TimeTamperDetector::with_mock_network(chain_path.clone(), log_path, |_| Some(0.1));
        det.start_session();
        det.force_set_starts_for_test(0.0, 1000.0);

        // Normal tick (+2s monotonic, +2s system)
        let ok_res = det.validate_and_record_at("VS Code", 2.0, 2.0, 1002.0);
        assert_eq!(ok_res.integrity_status, "VALID");

        // Legitimate OS suspend: monotonic advanced +2s, system clock jumped +300s, network confirms clock is aligned
        let wake_res = det.validate_and_record_at("VS Code", 2.0, 4.0, 1302.0);
        assert_eq!(wake_res.integrity_status, "VALID");

        // Clock manipulation without OS suspend: system jumped backwards by -100s -> tamper!
        let tamper_res = det.validate_and_record_at("VS Code", 2.0, 6.0, 1202.0);
        assert_eq!(tamper_res.integrity_status, "TAMPER_DETECTED");
        assert!(tamper_res.trust_score < 100);

        assert!(det.verify_chain_integrity());
        det.tamper_entry_for_test(1, "MaliciousApp");
        assert!(!det.verify_chain_integrity());

        let rep = det.end_session();
        assert!(!rep.chain_valid);
        assert!(chain_path.exists());
    }

    #[test]
    fn test_nonblocking_network_sync_and_incremental_verify() {
        let tmp = TempDir::new().unwrap();
        let chain_path = tmp.path().join("time_chain.json");
        let log_path = tmp.path().join("security_log.json");

        // Slow network sync (400ms) must NOT block end_session() or get_session_report()
        let det = TimeTamperDetector::with_mock_network(chain_path, log_path, |_| {
            std::thread::sleep(std::time::Duration::from_millis(400));
            Some(0.05)
        });
        det.start_session();
        det.force_set_starts_for_test(0.0, 1000.0);

        let t0 = std::time::Instant::now();
        for i in 1..=200 {
            let res = det.validate_and_record_at("VS Code", 1.0, i as f64, 1000.0 + i as f64);
            assert_eq!(res.integrity_status, "VALID");
            let r = det.get_session_report();
            assert!(r.chain_valid);
        }
        let end_rep = det.end_session();
        assert!(end_rep.chain_valid);
        assert!(
            t0.elapsed() < std::time::Duration::from_millis(350),
            "Slow network sync blocked foreground thread: elapsed={:?}",
            t0.elapsed()
        );
    }

    #[test]
    fn test_suspend_network_sync_does_not_hold_mutex_for_concurrent_callers() {
        use std::sync::{Condvar, Mutex as StdMutex};
        use std::time::Duration;

        let tmp = TempDir::new().unwrap();
        let chain_path = tmp.path().join("time_chain.json");
        let log_path = tmp.path().join("security_log.json");

        // (entered_suspend_sync, release_suspend_sync, timed_out)
        let gate = Arc::new((StdMutex::new((false, false, false)), Condvar::new()));
        let gate_cb = Arc::clone(&gate);

        let det = TimeTamperDetector::with_mock_network(chain_path, log_path, move |timeout| {
            if timeout == 1 {
                let (lock, cv) = &*gate_cb;
                let mut state = lock.lock().unwrap();
                state.0 = true;
                cv.notify_all();
                let res = cv
                    .wait_timeout_while(state, Duration::from_secs(2), |s| !s.1)
                    .unwrap();
                state = res.0;
                if res.1.timed_out() {
                    state.2 = true;
                }
            }
            Some(0.05)
        });

        det.start_session();
        det.force_set_starts_for_test(0.0, 1000.0);
        let ok_res = det.validate_and_record_at("VS Code", 2.0, 2.0, 1002.0);
        assert_eq!(ok_res.integrity_status, "VALID");

        let det_bg = det.clone();
        let handle = std::thread::spawn(move || {
            // Triggers sleep_time > 5.0 -> calls (sync_fn)(1)
            det_bg.validate_and_record_at("VS Code", 2.0, 4.0, 1302.0)
        });

        // Wait until background thread is actively inside (sync_fn)(1)
        {
            let (lock, cv) = &*gate;
            let state = lock.lock().unwrap();
            let (state, wait_res) = cv
                .wait_timeout_while(state, Duration::from_secs(2), |s| !s.0)
                .unwrap();
            assert!(!wait_res.timed_out(), "timed out waiting to enter sync_fn(1)");
            drop(state);
        }

        // Concurrent caller MUST acquire inner mutex immediately without waiting on sync_fn(1).
        // If inner mutex were still held across sync_fn(1), this would deadlock until timeout!
        let rep = det.get_session_report();
        assert!(rep.chain_valid);

        // Release sync_fn(1) now that get_session_report() succeeded concurrently
        {
            let (lock, cv) = &*gate;
            let mut state = lock.lock().unwrap();
            state.1 = true;
            cv.notify_all();
        }

        let wake_res = handle.join().unwrap();
        assert_eq!(wake_res.integrity_status, "VALID");
        assert!(!gate.0.lock().unwrap().2, "sync_fn(1) timed out due to lock contention");

        let end_rep = det.end_session();
        assert!(end_rep.chain_valid);
    }

    #[test]
    fn test_end_session_during_inflight_suspend_sync_stays_consistent() {
        use std::sync::{Condvar, Mutex as StdMutex};
        use std::time::Duration;

        let tmp = TempDir::new().unwrap();
        let chain_path = tmp.path().join("time_chain.json");
        let log_path = tmp.path().join("security_log.json");

        let gate = Arc::new((StdMutex::new((false, false)), Condvar::new()));
        let gate_cb = Arc::clone(&gate);

        let det = TimeTamperDetector::with_mock_network(chain_path, log_path, move |timeout| {
            if timeout == 1 {
                let (lock, cv) = &*gate_cb;
                let mut state = lock.lock().unwrap();
                state.0 = true;
                cv.notify_all();
                let _ = cv
                    .wait_timeout_while(state, Duration::from_secs(2), |s| !s.1)
                    .unwrap();
            }
            Some(0.0)
        });

        det.start_session();
        det.force_set_starts_for_test(0.0, 1000.0);
        assert_eq!(
            det.validate_and_record_at("VS Code", 1.0, 1.0, 1001.0)
                .integrity_status,
            "VALID"
        );

        let det_bg = det.clone();
        let handle = std::thread::spawn(move || {
            det_bg.validate_and_record_at("VS Code", 1.0, 2.0, 1200.0)
        });

        {
            let (lock, cv) = &*gate;
            let state = lock.lock().unwrap();
            let (_s, wait_res) = cv
                .wait_timeout_while(state, Duration::from_secs(2), |s| !s.0)
                .unwrap();
            assert!(!wait_res.timed_out());
        }

        // End session while sync_fn(1) is blocked
        let end_rep = det.end_session();
        assert!(end_rep.chain_valid);
        let len_at_end = end_rep.chain_length;

        {
            let (lock, cv) = &*gate;
            let mut state = lock.lock().unwrap();
            state.1 = true;
            cv.notify_all();
        }

        let _ = handle.join().unwrap();
        let after_rep = det.get_session_report();
        assert!(after_rep.chain_valid);
        assert_eq!(after_rep.chain_length, len_at_end);
    }

    #[test]
    fn test_post_end_session_and_queued_session_restart_noops() {
        use std::sync::atomic::{AtomicUsize, Ordering};
        use std::sync::{Condvar, Mutex as StdMutex};
        use std::time::Duration;

        let tmp = TempDir::new().unwrap();
        let chain_path = tmp.path().join("time_chain.json");
        let log_path = tmp.path().join("security_log.json");

        let suspend_calls = Arc::new(AtomicUsize::new(0));
        let suspend_calls_cb = Arc::clone(&suspend_calls);
        let gate = Arc::new((StdMutex::new((false, false)), Condvar::new()));
        let gate_cb = Arc::clone(&gate);

        let det = TimeTamperDetector::with_mock_network(chain_path, log_path, move |timeout| {
            if timeout == 1 {
                suspend_calls_cb.fetch_add(1, Ordering::SeqCst);
                let (lock, cv) = &*gate_cb;
                let mut state = lock.lock().unwrap();
                state.0 = true;
                cv.notify_all();
                let _ = cv
                    .wait_timeout_while(state, Duration::from_secs(2), |s| !s.1)
                    .unwrap();
            }
            Some(0.0)
        });

        // Part 1: Calling validate_and_record_at AFTER end_session() must NOT run sync_fn(1) or append entries
        det.start_session();
        det.force_set_starts_for_test(0.0, 1000.0);
        assert_eq!(
            det.validate_and_record_at("VS Code", 1.0, 1.0, 1001.0)
                .integrity_status,
            "VALID"
        );
        let end_rep = det.end_session();
        let len_ended = end_rep.chain_length;

        let post_normal = det.validate_and_record_at("VS Code", 1.0, 2.0, 1002.0);
        assert_eq!(post_normal.integrity_status, "VALID");
        let post_jump = det.validate_and_record_at("VS Code", 1.0, 3.0, 1500.0);
        assert_eq!(post_jump.integrity_status, "VALID");
        assert_eq!(suspend_calls.load(Ordering::SeqCst), 0);
        assert_eq!(det.get_session_report().chain_length, len_ended);
        assert!(det.get_session_report().chain_valid);

        // Part 2: Queued validate_and_record_at behind validation_gate must NOT inject old timestamps into a restarted session
        det.start_session();
        det.force_set_starts_for_test(0.0, 2000.0);
        assert_eq!(
            det.validate_and_record_at("VS Code", 1.0, 1.0, 2001.0)
                .integrity_status,
            "VALID"
        );

        let det_bg1 = det.clone();
        let h1 = std::thread::spawn(move || {
            det_bg1.validate_and_record_at("VS Code", 1.0, 2.0, 2300.0)
        });

        {
            let (lock, cv) = &*gate;
            let state = lock.lock().unwrap();
            let (_s, wait_res) = cv
                .wait_timeout_while(state, Duration::from_secs(2), |s| !s.0)
                .unwrap();
            assert!(!wait_res.timed_out());
        }

        // Second thread blocks on validation_gate with old-session timestamps
        let det_bg2 = det.clone();
        let h2 = std::thread::spawn(move || {
            det_bg2.validate_and_record_at("OldApp", 1.0, 3.0, 2301.0)
        });
        std::thread::sleep(Duration::from_millis(30));

        // End old session and immediately start a brand new session before h1/h2 unblock
        let _ = det.end_session();
        det.start_session();
        det.force_set_starts_for_test(10.0, 5000.0);
        let new_session_len_before = det.get_session_report().chain_length;

        {
            let (lock, cv) = &*gate;
            let mut state = lock.lock().unwrap();
            state.1 = true;
            cv.notify_all();
        }

        let r1 = h1.join().unwrap();
        let r2 = h2.join().unwrap();
        assert_eq!(r1.integrity_status, "VALID");
        assert_eq!(r2.integrity_status, "VALID");

        let rep_new = det.get_session_report();
        assert_eq!(rep_new.trust_score, 100);
        assert_eq!(rep_new.chain_length, new_session_len_before);
        assert!(rep_new.chain_valid);
    }
}
