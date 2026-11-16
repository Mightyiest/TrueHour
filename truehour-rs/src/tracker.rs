use crate::appinfo::{AppResolver, ForegroundApp};
use crate::config::{atomic_write_str, ProfilePaths};
use crate::report::{self, format_duration, format_duration_hms, SessionReportData};
use crate::secure_time::{SessionSecurityReport, TimeTamperDetector};
use crate::settings::{
    is_auto_excluded_exe, load_auto_excluded_exes, AppSettings, ExcludedSettings,
};
use crate::tags::TagManager;
use chrono::{Duration as ChronoDuration, Local, NaiveDateTime, TimeZone};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::Path;
use std::sync::{Arc, Condvar, Mutex};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

pub trait SystemProbe: Send + Sync {
    fn get_foreground_app(&self) -> ForegroundApp;
    fn get_idle_seconds(&self) -> f64;
}

pub struct Win32Probe {
    resolver: Arc<AppResolver>,
}

impl Win32Probe {
    pub fn new(resolver: Arc<AppResolver>) -> Self {
        Self { resolver }
    }
}

impl SystemProbe for Win32Probe {
    fn get_foreground_app(&self) -> ForegroundApp {
        self.resolver.get_foreground_app_info()
    }

    fn get_idle_seconds(&self) -> f64 {
        #[cfg(windows)]
        {
            use windows::Win32::System::SystemInformation::GetTickCount;
            use windows::Win32::UI::Input::KeyboardAndMouse::{GetLastInputInfo, LASTINPUTINFO};
            unsafe {
                let mut lii = LASTINPUTINFO {
                    cbSize: std::mem::size_of::<LASTINPUTINFO>() as u32,
                    dwTime: 0,
                };
                if GetLastInputInfo(&mut lii).as_bool() {
                    let now_ticks = GetTickCount();
                    let elapsed_ms = now_ticks.wrapping_sub(lii.dwTime);
                    return (elapsed_ms as f64) / 1000.0;
                }
            }
            0.0
        }
        #[cfg(not(windows))]
        {
            0.0
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TimelineBlock {
    pub app: String,
    pub start: f64,
    pub end: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ActiveSessionFile {
    pub session_start: Option<f64>,
    #[serde(default)]
    pub session_name: String,
    #[serde(default)]
    pub app_times: HashMap<String, f64>,
    #[serde(default)]
    pub app_included: HashMap<String, bool>,
    #[serde(default)]
    pub app_exe_paths: HashMap<String, String>,
    #[serde(default)]
    pub timeline: Vec<TimelineBlock>,
    #[serde(default)]
    pub paused: bool,
    #[serde(default)]
    pub _pause_start: Option<f64>,
    #[serde(default)]
    pub _total_paused_time: f64,
    #[serde(default)]
    pub _current_app: Option<String>,
    #[serde(default)]
    pub _current_start: Option<f64>,
    #[serde(default)]
    pub _current_block_start: Option<f64>,
    #[serde(default)]
    pub _current_block_active: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TrackedAppRowSnapshot {
    pub name: String,
    pub seconds: i64,
    pub formatted: String,
    pub percent: f64,
    pub excluded: bool,
    pub tag: String,
    pub tag_color: String,
    pub exe_path: String,
    pub is_distracting: bool,
    pub icon_data_url: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProjectAllocationItem {
    pub project: String,
    pub seconds: i64,
    pub formatted: String,
    pub percent: f64,
    pub color: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TrackerUiSnapshot {
    pub running: bool,
    pub paused: bool,
    pub idle_paused: bool,
    pub distraction_paused: bool,
    pub is_recovered: bool,
    pub session_name: String,
    pub current_app: String,
    pub status_text: String,
    pub elapsed_seconds: i64,
    pub elapsed_hms: String,
    pub elapsed_formatted: String,
    pub counted_seconds: i64,
    pub counted_hms: String,
    pub counted_formatted: String,
    pub hourly_rate: f64,
    pub currency_symbol: String,
    pub earned: f64,
    pub earned_display: String,
    pub idle_threshold_seconds: u64,
    pub trust_score: i32,
    pub trust_level: String,
    pub chain_valid: bool,
    pub integrity_status: String,
    pub theme_style: String,
    pub dark_mode: bool,
    pub developer_mode: bool,
    pub profile_name: String,
    pub apps: Vec<TrackedAppRowSnapshot>,
    pub allocations: Vec<ProjectAllocationItem>,
    pub available_projects: Vec<String>,
    pub has_pending_recovery: bool,
    pub pending_recovery_summary: Option<PendingRecoverySummary>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PendingRecoverySummary {
    pub session_name: String,
    pub tracked_formatted: String,
    pub app_count: usize,
    pub saved_at: String,
}

pub fn unix_now_f64() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

fn sanitize_session_name(raw: &str) -> String {
    raw.chars()
        .filter(|c| !c.is_control())
        .collect::<String>()
        .trim()
        .to_string()
}

struct TrackerInner {
    paths: ProfilePaths,
    poll_interval: f64,
    min_track_seconds: i64,
    save_interval_secs: u64,

    running: bool,
    paused: bool,
    idle_paused: bool,
    distraction_paused: bool,
    session_start: Option<f64>,
    session_end: Option<f64>,
    pause_start: Option<f64>,
    total_paused_time: f64,
    last_save_time: f64,
    is_recovered: bool,
    session_name: String,
    resumed_filepath: Option<String>,
    resume_snapshot: Option<HashMap<String, f64>>,

    app_times: HashMap<String, f64>,
    app_included: HashMap<String, bool>,
    app_exe_paths: HashMap<String, String>,
    timeline: Vec<TimelineBlock>,

    current_app: Option<String>,
    current_start: Option<f64>,
    current_block_start: Option<f64>,
    current_block_active: f64,

    excluded_settings: ExcludedSettings,
    auto_excluded_exes: HashSet<String>,
    app_settings: AppSettings,

    idle_threshold_seconds: u64,
    enable_distraction_auto_pause: bool,
    distraction_apps: Vec<String>,

    security_detector: Option<TimeTamperDetector>,
    last_integrity_status: String,
    integrity_warnings: Vec<Value>,
    has_pending_recovery: bool,
    on_update: Option<Arc<dyn Fn() + Send + Sync>>,
}

pub struct AppTracker {
    inner: Arc<Mutex<TrackerInner>>,
    wake: Arc<Condvar>,
    probe: Arc<dyn SystemProbe>,
    resolver: Arc<AppResolver>,
    tag_manager: Arc<TagManager>,
}

impl AppTracker {
    pub fn new(
        paths: ProfilePaths,
        resolver: Arc<AppResolver>,
        tag_manager: Arc<TagManager>,
        probe: Arc<dyn SystemProbe>,
    ) -> Arc<Self> {
        let app_settings = AppSettings::load(&paths.app_settings_file);
        let excluded_settings = ExcludedSettings::load(&paths.settings_file);
        let auto_excluded_exes = load_auto_excluded_exes(&paths.auto_excluded_file);
        let min_track_seconds = app_settings.min_track_seconds();
        let save_interval_secs = app_settings.auto_save_seconds().max(1);
        let idle_threshold_seconds = app_settings.idle_threshold_seconds_total();
        let enable_distraction_auto_pause = app_settings.enable_distraction_auto_pause();
        let distraction_apps = app_settings.distraction_apps();
        let has_pending_recovery = paths.active_session_file.exists();

        Arc::new(Self {
            inner: Arc::new(Mutex::new(TrackerInner {
                paths,
                poll_interval: 1.0,
                min_track_seconds,
                save_interval_secs,
                running: false,
                paused: false,
                idle_paused: false,
                distraction_paused: false,
                session_start: None,
                session_end: None,
                pause_start: None,
                total_paused_time: 0.0,
                last_save_time: 0.0,
                is_recovered: false,
                session_name: String::new(),
                resumed_filepath: None,
                resume_snapshot: None,
                app_times: HashMap::new(),
                app_included: HashMap::new(),
                app_exe_paths: HashMap::new(),
                timeline: Vec::new(),
                current_app: None,
                current_start: None,
                current_block_start: None,
                current_block_active: 0.0,
                excluded_settings,
                auto_excluded_exes,
                app_settings,
                idle_threshold_seconds,
                enable_distraction_auto_pause,
                distraction_apps,
                security_detector: None,
                last_integrity_status: "VALID".to_string(),
                integrity_warnings: Vec::new(),
                has_pending_recovery,
                on_update: None,
            })),
            wake: Arc::new(Condvar::new()),
            probe,
            resolver,
            tag_manager,
        })
    }

    pub fn set_on_update(&self, cb: Arc<dyn Fn() + Send + Sync>) {
        self.inner.lock().unwrap().on_update = Some(cb);
    }

    fn emit_update(&self) {
        let cb = self.inner.lock().unwrap().on_update.clone();
        if let Some(f) = cb {
            f();
        }
    }

    pub fn start(self: &Arc<Self>, session_name: &str) -> bool {
        let now = unix_now_f64();
        {
            let mut st = self.inner.lock().unwrap();
            if st.running {
                return false;
            }
            st.auto_excluded_exes = load_auto_excluded_exes(&st.paths.auto_excluded_file);
            st.excluded_settings = ExcludedSettings::load(&st.paths.settings_file);
            st.app_settings = AppSettings::load(&st.paths.app_settings_file);
            st.min_track_seconds = st.app_settings.min_track_seconds();
            st.save_interval_secs = st.app_settings.auto_save_seconds().max(1);
            st.idle_threshold_seconds = st.app_settings.idle_threshold_seconds_total();
            st.enable_distraction_auto_pause = st.app_settings.enable_distraction_auto_pause();
            st.distraction_apps = st.app_settings.distraction_apps();

            let detector = TimeTamperDetector::new(
                st.paths.time_chain_file.clone(),
                st.paths.security_log_file.clone(),
            );
            detector.start_session();
            st.security_detector = Some(detector);
            st.last_integrity_status = "VALID".to_string();
            st.integrity_warnings.clear();

            st.running = true;
            st.paused = false;
            st.idle_paused = false;
            st.distraction_paused = false;
            st.has_pending_recovery = false;
            st.session_start = Some(now);
            st.session_end = None;
            st.pause_start = None;
            st.total_paused_time = 0.0;
            st.last_save_time = now;
            st.is_recovered = false;
            let cleaned_arg = sanitize_session_name(session_name);
            let pending_name = sanitize_session_name(&st.session_name);
            st.session_name = if !cleaned_arg.is_empty() {
                cleaned_arg
            } else if !pending_name.is_empty() {
                pending_name
            } else {
                chrono::Local::now().format("Session - %I:%M %p").to_string()
            };
            st.resumed_filepath = None;
            st.resume_snapshot = None;

            st.app_times.clear();
            st.app_included.clear();
            st.app_exe_paths.clear();
            st.timeline.clear();
            st.current_app = None;
            st.current_start = None;
            st.current_block_start = None;
            st.current_block_active = 0.0;
        }

        let this = Arc::clone(self);
        std::thread::spawn(move || this.poll_loop());
        self.emit_update();
        true
    }

    pub fn stop_and_build_report(&self) -> Option<(SessionReportData, Option<SessionSecurityReport>)> {
        let now = unix_now_f64();
        let (report_data, sec_report) = {
            let mut st = self.inner.lock().unwrap();
            if !st.running {
                return None;
            }
            st.running = false;
            self.wake.notify_all();
            st.session_end = Some(now);

            Self::flush_current_locked(&mut st, now);
            if st.paused {
                if let Some(ps) = st.pause_start.take() {
                    st.total_paused_time += (now - ps).max(0.0);
                }
            }
            st.paused = false;
            st.idle_paused = false;
            st.distraction_paused = false;

            let sec_rep = st.security_detector.take().map(|d| d.end_session());
            self.tag_manager.save_if_dirty();
            let _ = fs::remove_file(&st.paths.active_session_file);
            st.has_pending_recovery = false;

            let rep = self.build_report_locked(&st, now);
            st.session_name.clear();
            st.resumed_filepath = None;
            st.resume_snapshot = None;
            (rep, sec_rep)
        };

        self.emit_update();
        Some((report_data, sec_report))
    }

    pub fn discard_pending_recovery(&self) {
        let mut st = self.inner.lock().unwrap();
        let _ = fs::remove_file(&st.paths.active_session_file);
        st.has_pending_recovery = false;
        drop(st);
        self.emit_update();
    }

    pub fn get_pending_recovery_summary(&self) -> Option<PendingRecoverySummary> {
        let st = self.inner.lock().unwrap();
        if !st.has_pending_recovery || !st.paths.active_session_file.exists() {
            return None;
        }
        let raw = fs::read_to_string(&st.paths.active_session_file).ok()?;
        let parsed: ActiveSessionFile =
            serde_json::from_str(raw.trim_start_matches('\u{feff}')).ok()?;
        let total_secs: f64 = parsed
            .app_times
            .iter()
            .filter(|(k, _)| *parsed.app_included.get(*k).unwrap_or(&true))
            .map(|(_, v)| *v)
            .sum();
        let saved_at = parsed
            .session_start
            .map(|ts| {
                chrono::DateTime::from_timestamp(ts as i64, 0)
                    .map(|dt| {
                        dt.with_timezone(&chrono::Local)
                            .format("%b %d, %I:%M %p")
                            .to_string()
                    })
                    .unwrap_or_else(|| "Previous Session".to_string())
            })
            .unwrap_or_else(|| "Previous Session".to_string());

        Some(PendingRecoverySummary {
            session_name: if parsed.session_name.trim().is_empty() {
                "Interrupted Session".to_string()
            } else {
                parsed.session_name
            },
            tracked_formatted: format_duration(total_secs as i64),
            app_count: parsed.app_times.len(),
            saved_at,
        })
    }

    pub fn recover_session(self: &Arc<Self>) -> bool {
        let now = unix_now_f64();
        {
            let mut st = self.inner.lock().unwrap();
            if st.running || !st.paths.active_session_file.exists() {
                return false;
            }
            let raw = match fs::read_to_string(&st.paths.active_session_file) {
                Ok(s) => s,
                Err(_) => return false,
            };
            let mut parsed: ActiveSessionFile =
                match serde_json::from_str(raw.trim_start_matches('\u{feff}')) {
                    Ok(p) => p,
                    Err(_) => return false,
                };
            let Some(session_start) = parsed.session_start else {
                return false;
            };

            let mtime = fs::metadata(&st.paths.active_session_file)
                .and_then(|m| m.modified())
                .ok()
                .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
                .map(|d| d.as_secs_f64())
                .unwrap_or(now);

            if let (Some(c_app), Some(c_block_start)) =
                (parsed._current_app.take(), parsed._current_block_start.take())
            {
                let mut c_block_active = parsed._current_block_active;
                if let Some(c_start) = parsed._current_start {
                    let mut elapsed = mtime - c_start;
                    if elapsed > 0.0 {
                        if elapsed > st.poll_interval + 2.0 {
                            elapsed = st.poll_interval;
                        }
                        if *parsed.app_included.get(&c_app).unwrap_or(&true) {
                            *parsed.app_times.entry(c_app.clone()).or_insert(0.0) += elapsed;
                            c_block_active += elapsed;
                        }
                    }
                }
                if c_block_active >= st.min_track_seconds as f64 {
                    parsed.timeline.push(TimelineBlock {
                        app: c_app,
                        start: c_block_start,
                        end: c_block_start + c_block_active,
                    });
                }
            }

            st.auto_excluded_exes = load_auto_excluded_exes(&st.paths.auto_excluded_file);
            st.excluded_settings = ExcludedSettings::load(&st.paths.settings_file);
            st.app_settings = AppSettings::load(&st.paths.app_settings_file);
            st.min_track_seconds = st.app_settings.min_track_seconds();
            st.save_interval_secs = st.app_settings.auto_save_seconds().max(1);
            st.idle_threshold_seconds = st.app_settings.idle_threshold_seconds_total();
            st.enable_distraction_auto_pause = st.app_settings.enable_distraction_auto_pause();
            st.distraction_apps = st.app_settings.distraction_apps();

            let detector = TimeTamperDetector::new(
                st.paths.time_chain_file.clone(),
                st.paths.security_log_file.clone(),
            );
            detector.start_session();
            st.security_detector = Some(detector);
            st.integrity_warnings.clear();

            st.session_name = sanitize_session_name(&parsed.session_name);
            st.session_start = Some(session_start);
            st.app_times = parsed.app_times;
            st.app_included = parsed.app_included;
            st.app_exe_paths = parsed.app_exe_paths;
            st.timeline = parsed.timeline;
            st.paused = parsed.paused;

            let tracked_duration: f64 = st.app_times.values().sum();
            st.total_paused_time = ((now - session_start) - tracked_duration).max(0.0);
            st.pause_start = if st.paused { Some(now) } else { None };
            st.current_app = None;
            st.current_start = None;
            st.current_block_start = None;
            st.current_block_active = 0.0;
            st.session_end = None;
            st.is_recovered = true;
            st.resumed_filepath = None;
            st.resume_snapshot = None;
            st.has_pending_recovery = false;
            st.running = true;
            st.last_save_time = now;
        }

        let this = Arc::clone(self);
        std::thread::spawn(move || this.poll_loop());
        self.emit_update();
        true
    }

    pub fn load_from_report(self: &Arc<Self>, filepath: &Path) -> Result<String, String> {
        let rep = report::load_session_report(filepath)?;
        let now = unix_now_f64();

        let naive_start = NaiveDateTime::parse_from_str(
            &format!("{} {}", rep.date, rep.start),
            "%Y-%m-%d %H:%M:%S",
        )
        .map_err(|e| format!("Invalid session start timestamp: {e}"))?;
        let start_local = Local
            .from_local_datetime(&naive_start)
            .single()
            .or_else(|| Local.from_local_datetime(&naive_start).earliest())
            .unwrap_or_else(Local::now);
        let session_start_ts =
            start_local.timestamp() as f64 + (start_local.timestamp_subsec_nanos() as f64 / 1e9);

        let resumed_display_name;
        let mut resumed_app_tags: Vec<(String, String, String)> = Vec::new();
        {
            let mut st = self.inner.lock().unwrap();
            if st.running {
                return Err("Stop the active tracking session before resuming another.".to_string());
            }

            st.auto_excluded_exes = load_auto_excluded_exes(&st.paths.auto_excluded_file);
            st.excluded_settings = ExcludedSettings::load(&st.paths.settings_file);
            st.app_settings = AppSettings::load(&st.paths.app_settings_file);
            st.min_track_seconds = st.app_settings.min_track_seconds();
            st.save_interval_secs = st.app_settings.auto_save_seconds().max(1);
            st.idle_threshold_seconds = st.app_settings.idle_threshold_seconds_total();
            st.enable_distraction_auto_pause = st.app_settings.enable_distraction_auto_pause();
            st.distraction_apps = st.app_settings.distraction_apps();

            st.app_exe_paths = rep.app_exe_paths.clone();
            st.app_times.clear();
            st.app_included.clear();

            for a in &rep.apps {
                let exe_path = st.app_exe_paths.get(&a.name).cloned().unwrap_or_default();
                if a.name != "[Idle]" && !is_auto_excluded_exe(&exe_path, &st.auto_excluded_exes) {
                    st.app_times.insert(a.name.clone(), a.seconds as f64);
                    st.app_included.insert(a.name.clone(), !a.excluded);
                    resumed_app_tags.push((a.name.clone(), a.tag.clone(), exe_path));
                }
            }

            st.timeline.clear();
            let mut day_offset = ChronoDuration::days(0);
            let mut prev_end: Option<NaiveDateTime> = None;
            for t in &rep.timeline {
                let Ok(mut t_start) = NaiveDateTime::parse_from_str(
                    &format!("{} {}", rep.date, t.start),
                    "%Y-%m-%d %H:%M:%S",
                ) else {
                    continue;
                };
                let Ok(mut t_end) = NaiveDateTime::parse_from_str(
                    &format!("{} {}", rep.date, t.end),
                    "%Y-%m-%d %H:%M:%S",
                ) else {
                    continue;
                };
                t_start += day_offset;
                t_end += day_offset;
                if let Some(pe) = prev_end {
                    if t_start < pe {
                        day_offset += ChronoDuration::days(1);
                        t_start += ChronoDuration::days(1);
                        t_end += ChronoDuration::days(1);
                    }
                }
                if t_end <= t_start {
                    day_offset += ChronoDuration::days(1);
                    t_end += ChronoDuration::days(1);
                }
                prev_end = Some(t_end);
                let to_ts = |ndt: NaiveDateTime| -> f64 {
                    Local
                        .from_local_datetime(&ndt)
                        .single()
                        .or_else(|| Local.from_local_datetime(&ndt).earliest())
                        .map(|dt| dt.timestamp() as f64)
                        .unwrap_or(now)
                };
                st.timeline.push(TimelineBlock {
                    app: t.app.clone(),
                    start: to_ts(t_start),
                    end: to_ts(t_end),
                });
            }

            st.session_name = if rep.session_name.trim().is_empty() {
                filepath
                    .file_stem()
                    .and_then(|s| s.to_str())
                    .unwrap_or("Resumed Session")
                    .to_string()
            } else {
                rep.session_name.trim().to_string()
            };
            resumed_display_name = st.session_name.clone();

            st.session_start = Some(session_start_ts);
            st.session_end = None;
            st.total_paused_time = ((now - session_start_ts) - rep.total_seconds as f64).max(0.0);
            st.paused = false;
            st.idle_paused = false;
            st.distraction_paused = false;
            st.pause_start = None;
            st.current_app = None;
            st.current_start = None;
            st.current_block_start = None;
            st.current_block_active = 0.0;

            let detector = TimeTamperDetector::new(
                st.paths.time_chain_file.clone(),
                st.paths.security_log_file.clone(),
            );
            detector.start_session();
            st.security_detector = Some(detector);
            st.last_integrity_status = "VALID".to_string();
            st.integrity_warnings.clear();

            st.is_recovered = false;
            st.has_pending_recovery = false;
            st.resume_snapshot = Some(st.app_times.clone());
            st.resumed_filepath = Some(filepath.to_string_lossy().to_string());
            st.running = true;
            st.last_save_time = now;
        }

        for (app_name, saved_tag, exe_path) in resumed_app_tags {
            if self.tag_manager.get_mapped_tag(&app_name) == "Unassigned" {
                let trimmed_tag = saved_tag.trim();
                if !trimmed_tag.is_empty() && trimmed_tag != "Unassigned" {
                    let _ = self.tag_manager.add_project(trimmed_tag);
                    let _ = self.tag_manager.set_tag(&app_name, trimmed_tag);
                } else {
                    let _ = self.tag_manager.get_tag(&app_name, &exe_path);
                }
            }
        }

        let this = Arc::clone(self);
        std::thread::spawn(move || this.poll_loop());
        self.emit_update();
        Ok(resumed_display_name)
    }

    pub fn toggle_pause(&self, is_idle: bool, is_distraction: bool) -> bool {
        self.toggle_pause_at(is_idle, is_distraction, unix_now_f64())
    }

    pub fn toggle_pause_at(&self, is_idle: bool, is_distraction: bool, now: f64) -> bool {
        let paused = {
            let mut st = self.inner.lock().unwrap();
            if !st.running {
                return false;
            }
            st.paused = !st.paused;
            if !is_idle {
                st.idle_paused = false;
            }
            if !is_distraction {
                st.distraction_paused = false;
            }
            if st.paused {
                if is_idle {
                    let deduct = st.idle_threshold_seconds as f64;
                    if let Some(cur) = st.current_app.clone() {
                        let entry = st.app_times.entry(cur).or_insert(0.0);
                        *entry = (*entry - deduct).max(0.0);
                        st.current_block_active = (st.current_block_active - deduct).max(0.0);
                    }
                    st.total_paused_time += deduct;
                    st.current_start = None;
                }
                Self::flush_current_locked(&mut st, now);
                st.current_app = None;
                st.current_start = None;
                st.pause_start = Some(now);
            } else if let Some(ps) = st.pause_start.take() {
                st.total_paused_time += (now - ps).max(0.0);
            }
            st.paused
        };
        self.emit_update();
        paused
    }

    pub fn set_session_name(&self, session_name: &str) {
        let cleaned = sanitize_session_name(session_name);
        {
            let mut st = self.inner.lock().unwrap();
            st.session_name = cleaned;
            if st.running {
                Self::save_active_state_locked(&st);
            }
        }
        self.emit_update();
    }

    pub fn set_app_included(&self, app_name: &str, included: bool) {
        {
            let mut st = self.inner.lock().unwrap();
            st.app_included.insert(app_name.to_string(), included);
            st.excluded_settings.set_excluded(app_name, !included);
            let path = st.paths.settings_file.clone();
            let _ = st.excluded_settings.save(&path);
        }
        self.emit_update();
    }

    pub fn set_app_tag(&self, app_name: &str, tag: &str) -> bool {
        let ok = self.tag_manager.set_tag(app_name, tag);
        if ok {
            self.emit_update();
        }
        ok
    }

    pub fn add_project_category(&self, project: &str) -> bool {
        let ok = self.tag_manager.add_project(project);
        if ok {
            self.emit_update();
        }
        ok
    }

    pub fn toggle_distraction_app(&self, app_name: &str, exe_path: &str) -> bool {
        let is_now_distracting;
        {
            let mut st = self.inner.lock().unwrap();
            let exe_name = Path::new(exe_path)
                .file_name()
                .and_then(|n| n.to_str())
                .unwrap_or("")
                .to_lowercase();
            let app_lower = app_name.trim().to_lowercase();

            let mut list = st.distraction_apps.clone();
            let existing_idx = list.iter().position(|d| {
                let dl = d.trim().to_lowercase();
                !dl.is_empty() && (dl == app_lower || (!exe_name.is_empty() && dl == exe_name))
            });

            if let Some(idx) = existing_idx {
                list.remove(idx);
                is_now_distracting = false;
            } else {
                let to_add = if !exe_name.is_empty() {
                    exe_name
                } else {
                    app_name.trim().to_string()
                };
                if !to_add.is_empty() {
                    list.push(to_add);
                }
                is_now_distracting = true;
            }
            st.distraction_apps = list.clone();
            st.app_settings.set_distraction_apps(list);
            let path = st.paths.app_settings_file.clone();
            let _ = st.app_settings.save(&path);
        }
        self.emit_update();
        is_now_distracting
    }

    pub fn update_inline_settings(&self, hourly_rate: f64, idle_threshold_seconds: u64) {
        {
            let mut st = self.inner.lock().unwrap();
            st.app_settings.set_hourly_rate(hourly_rate);
            st.app_settings
                .set_idle_threshold_seconds_total(idle_threshold_seconds);
            st.idle_threshold_seconds = idle_threshold_seconds;
            let path = st.paths.app_settings_file.clone();
            let _ = st.app_settings.save(&path);
        }
        self.emit_update();
    }

    pub fn cycle_theme(&self) -> String {
        let next = {
            let mut st = self.inner.lock().unwrap();
            let cur = st.app_settings.theme_style();
            let next_style = match cur.as_str() {
                "light" => "modern-dark",
                "modern-dark" => "classic-dark",
                _ => "light",
            };
            st.app_settings.set_theme_style(next_style);
            let path = st.paths.app_settings_file.clone();
            let _ = st.app_settings.save(&path);
            next_style.to_string()
        };
        self.emit_update();
        next
    }

    pub fn set_theme_style(&self, style: &str) -> String {
        let applied = {
            let mut st = self.inner.lock().unwrap();
            st.app_settings.set_theme_style(style);
            let path = st.paths.app_settings_file.clone();
            let _ = st.app_settings.save(&path);
            st.app_settings.theme_style()
        };
        self.emit_update();
        applied
    }

    pub fn theme_style(&self) -> String {
        self.inner.lock().unwrap().app_settings.theme_style()
    }

    pub fn set_developer_mode(&self, enabled: bool) -> bool {
        {
            let mut st = self.inner.lock().unwrap();
            st.app_settings.set_developer_mode(enabled);
            let path = st.paths.app_settings_file.clone();
            let _ = st.app_settings.save(&path);
        }
        self.emit_update();
        enabled
    }

    pub fn update_weekly_goal_hours(&self, hours: f64) -> f64 {
        let clamped = {
            let mut st = self.inner.lock().unwrap();
            st.app_settings.set_weekly_goal_hours(hours);
            let path = st.paths.app_settings_file.clone();
            let _ = st.app_settings.save(&path);
            st.app_settings.weekly_goal_hours()
        };
        self.emit_update();
        clamped
    }

    pub fn reload_app_settings_and_exclusions(&self) {
        {
            let mut st = self.inner.lock().unwrap();
            self.resolver.reload_name_overrides();
            st.auto_excluded_exes = load_auto_excluded_exes(&st.paths.auto_excluded_file);
            st.excluded_settings = ExcludedSettings::load(&st.paths.settings_file);
            st.app_settings = AppSettings::load(&st.paths.app_settings_file);
            st.min_track_seconds = st.app_settings.min_track_seconds();
            st.save_interval_secs = st.app_settings.auto_save_seconds().max(1);
            st.idle_threshold_seconds = st.app_settings.idle_threshold_seconds_total();
            st.enable_distraction_auto_pause = st.app_settings.enable_distraction_auto_pause();
            st.distraction_apps = st.app_settings.distraction_apps();
        }
        self.emit_update();
    }

    pub fn reload_for_profile_switch(&self, new_paths: ProfilePaths) -> Result<(), String> {
        {
            let mut st = self.inner.lock().unwrap();
            if st.running {
                return Err("Stop the active tracking session before switching profiles.".to_string());
            }
            let _ = new_paths.ensure_dirs();
            let _ = crate::settings::ensure_profile_bootstrap_files(&new_paths);
            let _ = crate::db::init_database(&new_paths);
            let _ = crate::db::rebuild_all_summaries(&new_paths, false);

            self.resolver
                .set_overrides_file_and_reload(new_paths.name_overrides_file.clone());
            self.tag_manager
                .reload_from_file(new_paths.tags_file.clone());

            st.auto_excluded_exes = load_auto_excluded_exes(&new_paths.auto_excluded_file);
            st.excluded_settings = ExcludedSettings::load(&new_paths.settings_file);
            st.app_settings = AppSettings::load(&new_paths.app_settings_file);
            st.min_track_seconds = st.app_settings.min_track_seconds();
            st.save_interval_secs = st.app_settings.auto_save_seconds().max(1);
            st.idle_threshold_seconds = st.app_settings.idle_threshold_seconds_total();
            st.enable_distraction_auto_pause = st.app_settings.enable_distraction_auto_pause();
            st.distraction_apps = st.app_settings.distraction_apps();

            st.session_start = None;
            st.session_end = None;
            st.pause_start = None;
            st.total_paused_time = 0.0;
            st.is_recovered = false;
            st.session_name.clear();
            st.resumed_filepath = None;
            st.resume_snapshot = None;
            st.app_times.clear();
            st.app_included.clear();
            st.app_exe_paths.clear();
            st.timeline.clear();
            st.current_app = None;
            st.current_start = None;
            st.current_block_start = None;
            st.current_block_active = 0.0;
            st.integrity_warnings.clear();
            st.has_pending_recovery = new_paths.active_session_file.exists();
            st.paths = new_paths;
        }
        self.emit_update();
        Ok(())
    }

    pub fn is_running(&self) -> bool {
        self.inner.lock().unwrap().running
    }

    pub fn tag_manager(&self) -> Arc<TagManager> {
        Arc::clone(&self.tag_manager)
    }

    pub fn known_app_exes(&self) -> HashMap<String, String> {
        self.inner.lock().unwrap().app_exe_paths.clone()
    }

    pub fn should_confirm_on_exit(&self) -> bool {
        let st = self.inner.lock().unwrap();
        st.running && st.app_settings.confirm_on_close()
    }

    /// Used during Tray -> Exit when user clicks Exit while session is running:
    /// autosaves completed report into `autosave/` + updates `daily_summary` cleanly.
    pub fn autosave_on_exit(&self) {
        let paths = { self.inner.lock().unwrap().paths.clone() };
        if let Some((report_data, _)) = self.stop_and_build_report() {
            if report_data.total_seconds > 0 {
                let _ = report::save_to_autosave(&paths, &report_data);
            }
        }
    }

    pub fn save_active_state_snapshot(&self) {
        let st = self.inner.lock().unwrap();
        Self::save_active_state_locked(&st);
    }

    fn save_active_state_locked(st: &TrackerInner) {
        let payload = json!({
            "session_start": st.session_start,
            "session_name": st.session_name,
            "app_times": st.app_times,
            "app_included": st.app_included,
            "app_exe_paths": st.app_exe_paths,
            "timeline": st.timeline,
            "paused": st.paused,
            "_pause_start": st.pause_start,
            "_total_paused_time": st.total_paused_time,
            "_current_app": st.current_app,
            "_current_start": st.current_start,
            "_current_block_start": st.current_block_start,
            "_current_block_active": st.current_block_active,
        });
        if let Ok(json_str) = serde_json::to_string(&payload) {
            let _ = atomic_write_str(&st.paths.active_session_file, &json_str);
        }
    }

    fn flush_current_locked(st: &mut TrackerInner, now: f64) {
        if let Some(app) = st.current_app.take() {
            if let Some(start) = st.current_start.take() {
                let mut elapsed = now - start;
                if elapsed > 0.0 {
                    if elapsed > st.poll_interval + 2.0 {
                        st.total_paused_time += elapsed - st.poll_interval;
                        elapsed = st.poll_interval;
                    }
                    *st.app_times.entry(app.clone()).or_insert(0.0) += elapsed;
                    st.current_block_active += elapsed;
                }
            }
            if let Some(block_start) = st.current_block_start.take() {
                if st.current_block_active >= st.min_track_seconds as f64 {
                    let included = *st.app_included.get(&app).unwrap_or(&true);
                    if included && app != "[Idle]" {
                        st.timeline.push(TimelineBlock {
                            app,
                            start: block_start,
                            end: block_start + st.current_block_active,
                        });
                    }
                }
            }
        }
        st.current_start = None;
        st.current_block_start = None;
        st.current_block_active = 0.0;
    }

    fn is_app_distracting_locked(st: &TrackerInner, app_name: &str, exe_path: &str) -> bool {
        if !st.enable_distraction_auto_pause || st.distraction_apps.is_empty() {
            return false;
        }
        let exe_name = if exe_path.is_empty() {
            String::new()
        } else {
            Path::new(exe_path)
                .file_name()
                .and_then(|n| n.to_str())
                .unwrap_or("")
                .to_lowercase()
        };
        let app_lower = app_name.to_lowercase();
        for dist in &st.distraction_apps {
            let dist_lower = dist.trim().to_lowercase();
            if dist_lower.is_empty() {
                continue;
            }
            if (!exe_name.is_empty() && dist_lower == exe_name) || app_lower.contains(&dist_lower)
            {
                return true;
            }
        }
        false
    }

    /// Executes one poll iteration using explicit foreground/idle inputs (used by real poll loop AND tests).
    pub fn process_poll_tick(
        &self,
        fg: ForegroundApp,
        idle_secs: f64,
        now: f64,
    ) -> bool {
        let mut emit_now = false;

        // 1. Check idle auto-pause & auto-resume
        let idle_thresh = { self.inner.lock().unwrap().idle_threshold_seconds };
        if idle_thresh > 0 {
            let (is_paused, was_idle_paused) = {
                let st = self.inner.lock().unwrap();
                (st.paused, st.idle_paused)
            };
            if !is_paused && idle_secs >= idle_thresh as f64 {
                self.inner.lock().unwrap().idle_paused = true;
                self.toggle_pause_at(true, false, now);
                emit_now = true;
            } else if was_idle_paused && idle_secs < idle_thresh as f64 {
                self.inner.lock().unwrap().idle_paused = false;
                if self.inner.lock().unwrap().paused {
                    self.toggle_pause_at(false, false, now);
                }
                emit_now = true;
            }
        }

        // Manual pause must NOT auto-resume even on app switch
        {
            let st = self.inner.lock().unwrap();
            if !st.running || (st.paused && !st.distraction_paused) {
                return emit_now;
            }
        }

        // 2. Check distraction auto-pause / auto-resume
        let (is_distracting, currently_paused, was_dist_paused) = {
            let st = self.inner.lock().unwrap();
            (
                Self::is_app_distracting_locked(&st, &fg.friendly_name, &fg.exe_path),
                st.paused,
                st.distraction_paused,
            )
        };
        if is_distracting {
            if !currently_paused {
                self.inner.lock().unwrap().distraction_paused = true;
                self.toggle_pause_at(false, true, now);
                emit_now = true;
            }
        } else if was_dist_paused {
            self.inner.lock().unwrap().distraction_paused = false;
            if self.inner.lock().unwrap().paused {
                self.toggle_pause_at(false, true, now);
            }
            emit_now = true;
        }

        // 3. Accumulate active foreground app time (skip auto-excluded apps seamlessly)
        let mut should_autosave = false;
        let mut switched = false;
        let detector_tick: Option<(TimeTamperDetector, String, f64)> = {
            let mut st = self.inner.lock().unwrap();
            if !st.running || st.paused {
                return emit_now;
            }

            let mut target_app: Option<String> = if fg.friendly_name.is_empty() {
                None
            } else {
                Some(fg.friendly_name.clone())
            };

            if is_auto_excluded_exe(&fg.exe_path, &st.auto_excluded_exes) {
                // Pretend the last real app is still focused; do not record excluded exe
                target_app = st.current_app.clone();
            }

            let mut tick_val: Option<(TimeTamperDetector, String, f64)> = None;

            if target_app != st.current_app {
                Self::flush_current_locked(&mut st, now);
                st.current_app = target_app.clone();
                st.current_start = target_app.as_ref().map(|_| now);
                st.current_block_start = target_app.as_ref().map(|_| now);
                st.current_block_active = 0.0;

                if let Some(ref app_name) = target_app {
                    if !fg.exe_path.is_empty() {
                        st.app_exe_paths
                            .insert(app_name.clone(), fg.exe_path.clone());
                    }
                    if !st.app_included.contains_key(app_name) {
                        let inc = if st.excluded_settings.is_excluded(app_name) {
                            false
                        } else {
                            app_name != "[Idle]"
                        };
                        st.app_included.insert(app_name.clone(), inc);
                    }
                    if app_name != "[Idle]" {
                        let exe_for_tag = st
                            .app_exe_paths
                            .get(app_name)
                            .cloned()
                            .unwrap_or_default();
                        let _ = self.tag_manager.get_tag(app_name, &exe_for_tag);
                    }
                }
                switched = true;
            } else if let (Some(app_name), Some(prev_start)) =
                (st.current_app.clone(), st.current_start)
            {
                let mut elapsed = now - prev_start;
                if elapsed > 0.0 {
                    // OS sleep leap guard
                    if elapsed > st.poll_interval + 2.0 {
                        st.total_paused_time += elapsed - st.poll_interval;
                        elapsed = st.poll_interval;
                    }
                    *st.app_times.entry(app_name.clone()).or_insert(0.0) += elapsed;
                    st.current_block_active += elapsed;
                    st.current_start = Some(now);

                    let included = *st.app_included.get(&app_name).unwrap_or(&true);
                    if included {
                        if let Some(ref det) = st.security_detector {
                            tick_val = Some((det.clone(), app_name, elapsed));
                        }
                    }
                }
            }

            if (now - st.last_save_time) >= st.save_interval_secs as f64 {
                Self::save_active_state_locked(&st);
                self.tag_manager.save_if_dirty();
                st.last_save_time = now;
                should_autosave = true;
            }

            tick_val
        };

        if let Some((det, app_name, elapsed)) = detector_tick {
            let res = det.validate_and_record(&app_name, elapsed);
            let mut st = self.inner.lock().unwrap();
            st.last_integrity_status = res.integrity_status.clone();
            if res.integrity_status == "TAMPER_DETECTED" || res.integrity_status == "SUSPICIOUS" {
                st.integrity_warnings.push(json!({
                    "type": res.integrity_status,
                    "app": app_name,
                    "discrepancy": res.discrepancy,
                    "timestamp": chrono::Local::now().to_rfc3339(),
                }));
                if st.integrity_warnings.len() > 100 {
                    let drain = st.integrity_warnings.len() - 100;
                    st.integrity_warnings.drain(0..drain);
                }
            }
        }

        emit_now || switched || should_autosave
    }

    fn poll_loop(self: Arc<Self>) {
        loop {
            let poll_secs = {
                let st = self.inner.lock().unwrap();
                if !st.running {
                    break;
                }
                st.poll_interval.max(0.2)
            };

            let fg = self.probe.get_foreground_app();
            let idle = self.probe.get_idle_seconds();
            let now = unix_now_f64();
            let _ = self.process_poll_tick(fg, idle, now);
            self.emit_update();

            let guard = self.inner.lock().unwrap();
            if !guard.running {
                break;
            }
            let _ = self
                .wake
                .wait_timeout(guard, Duration::from_secs_f64(poll_secs));
        }
    }

    fn elapsed_locked(st: &TrackerInner, now: f64) -> f64 {
        let Some(start) = st.session_start else {
            return 0.0;
        };
        let end = st.session_end.unwrap_or(now);
        let raw_elapsed = (end - start).max(0.0);
        let mut paused = st.total_paused_time;
        if st.paused {
            if let Some(ps) = st.pause_start {
                paused += (now - ps).max(0.0);
            }
        }
        (raw_elapsed - paused).max(0.0)
    }

    fn counted_seconds_locked(st: &TrackerInner) -> f64 {
        st.app_times
            .iter()
            .filter(|(name, _)| {
                let included = *st.app_included.get(*name).unwrap_or(&true);
                let exe = st.app_exe_paths.get(*name).map(String::as_str).unwrap_or("");
                included && name.as_str() != "[Idle]" && !is_auto_excluded_exe(exe, &st.auto_excluded_exes)
            })
            .map(|(_, secs)| *secs)
            .sum()
    }

    fn build_report_locked(&self, st: &TrackerInner, now: f64) -> SessionReportData {
        let mut sorted: Vec<(String, f64, bool, String)> = st
            .app_times
            .iter()
            .filter(|(name, _)| {
                let exe = st.app_exe_paths.get(*name).map(String::as_str).unwrap_or("");
                name.as_str() != "[Idle]" && !is_auto_excluded_exe(exe, &st.auto_excluded_exes)
            })
            .map(|(name, secs)| {
                let inc = *st.app_included.get(name).unwrap_or(&true);
                let tag = self.tag_manager.get_mapped_tag(name);
                (name.clone(), *secs, inc, tag)
            })
            .collect();

        sorted.sort_by(|a, b| {
            b.2.cmp(&a.2)
                .then_with(|| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal))
        });

        let total_secs = Self::elapsed_locked(st, now) as i64;
        let counted_secs = Self::counted_seconds_locked(st) as i64;
        let rate = st.app_settings.hourly_rate();
        let currency = st.app_settings.currency_symbol();
        let timeline_tuples: Vec<(String, f64, f64)> = st
            .timeline
            .iter()
            .map(|b| (b.app.clone(), b.start, b.end))
            .collect();

        let is_resumed = st.resume_snapshot.is_some();
        let mut rep = report::build_report_data(report::ReportInput {
            session_start_ts: st.session_start.unwrap_or(now),
            session_end_ts: st.session_end.unwrap_or(now),
            total_seconds: total_secs,
            counted_seconds: counted_secs,
            apps: &sorted,
            timeline: &timeline_tuples,
            app_included: &st.app_included,
            app_exe_paths: &st.app_exe_paths,
            is_recovered: st.is_recovered,
            is_resumed,
            resumed_filepath: st.resumed_filepath.clone(),
            session_name: &st.session_name,
            hourly_rate: rate,
            currency_symbol: &currency,
        });

        if let Some(ref prev_map) = st.resume_snapshot {
            let mut new_act = Vec::new();
            let mut any_new = false;
            for (name, secs_f, inc, tag) in &sorted {
                let prev_secs = *prev_map.get(name).unwrap_or(&0.0);
                let new_secs = (*secs_f - prev_secs).max(0.0);
                if new_secs > 0.0 || prev_secs > 0.0 {
                    if new_secs > 0.0 {
                        any_new = true;
                    }
                    new_act.push(json!({
                        "name": name,
                        "previous_seconds": prev_secs as i64,
                        "previous_formatted": format_duration(prev_secs as i64),
                        "new_seconds": new_secs as i64,
                        "new_formatted": if new_secs as i64 > 0 { format_duration(new_secs as i64) } else { "—".to_string() },
                        "total_seconds": *secs_f as i64,
                        "total_formatted": format_duration(*secs_f as i64),
                        "excluded": !*inc,
                        "tag": tag,
                    }));
                }
            }
            if any_new {
                rep.new_activity = new_act;
            }
        }
        rep
    }

    pub fn ui_snapshot(&self, include_icons: bool) -> TrackerUiSnapshot {
        let now = unix_now_f64();
        let pending_recovery_summary = self.get_pending_recovery_summary();
        let st = self.inner.lock().unwrap();

        let elapsed = Self::elapsed_locked(&st, now) as i64;
        let counted = Self::counted_seconds_locked(&st) as i64;
        let rate = st.app_settings.hourly_rate();
        let currency = st.app_settings.currency_symbol();
        let earned = if rate > 0.0 {
            ((counted as f64 / 3600.0) * rate * 100.0).round() / 100.0
        } else {
            0.0
        };

        let (trust_score, trust_level, chain_valid) = if let Some(ref det) = st.security_detector {
            let rep = det.get_session_report();
            (rep.trust_score, rep.trust_level, rep.chain_valid)
        } else {
            (100, "HIGH".to_string(), true)
        };

        let mut rows_raw: Vec<(String, f64, bool)> = st
            .app_times
            .iter()
            .filter(|(name, _)| {
                let exe = st.app_exe_paths.get(*name).map(String::as_str).unwrap_or("");
                name.as_str() != "[Idle]" && !is_auto_excluded_exe(exe, &st.auto_excluded_exes)
            })
            .map(|(name, secs)| (name.clone(), *secs, *st.app_included.get(name).unwrap_or(&true)))
            .collect();

        rows_raw.sort_by(|a, b| {
            b.2.cmp(&a.2)
                .then_with(|| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal))
        });

        let mut proj_secs: HashMap<String, i64> = HashMap::new();
        let mut apps_out = Vec::with_capacity(rows_raw.len());
        for (name, secs_f, included) in rows_raw {
            let secs = secs_f as i64;
            let pct = if elapsed > 0 {
                ((secs as f64 / elapsed as f64) * 1000.0).round() / 10.0
            } else {
                0.0
            };
            let exe_path = st.app_exe_paths.get(&name).cloned().unwrap_or_default();
            let tag = self.tag_manager.get_mapped_tag(&name);
            let tag_color = report::project_color(&tag).to_string();
            let is_distracting = Self::is_app_distracting_locked(&st, &name, &exe_path);
            let icon_data_url = if include_icons {
                self.resolver.get_icon_data_url(&exe_path, 32)
            } else {
                None
            };
            if included {
                *proj_secs.entry(tag.clone()).or_insert(0) += secs;
            }
            apps_out.push(TrackedAppRowSnapshot {
                name,
                seconds: secs,
                formatted: format_duration(secs),
                percent: pct,
                excluded: !included,
                tag,
                tag_color,
                exe_path,
                is_distracting,
                icon_data_url,
            });
        }

        let total_alloc_secs: i64 = proj_secs.values().sum();
        let mut allocations: Vec<ProjectAllocationItem> = proj_secs
            .into_iter()
            .filter(|(_, s)| *s > 0)
            .map(|(project, secs)| ProjectAllocationItem {
                color: report::project_color(&project).to_string(),
                percent: if total_alloc_secs > 0 {
                    ((secs as f64 / total_alloc_secs as f64) * 1000.0).round() / 10.0
                } else {
                    0.0
                },
                formatted: format_duration(secs),
                project,
                seconds: secs,
            })
            .collect();
        allocations.sort_by(|a, b| b.seconds.cmp(&a.seconds));

        let current_app = if st.paused {
            "Paused".to_string()
        } else {
            st.current_app.clone().unwrap_or_default()
        };

        let status_text = if !st.running {
            if st.session_end.is_some() {
                "Session ended".to_string()
            } else {
                "Ready to track".to_string()
            }
        } else if st.idle_paused {
            "Auto-paused (Idle)".to_string()
        } else if st.distraction_paused {
            "Auto-paused (Distracting app)".to_string()
        } else if st.paused {
            "Paused".to_string()
        } else if current_app.is_empty() {
            String::new()
        } else {
            format!("Active: {current_app}")
        };

        let theme_style = st.app_settings.theme_style();
        let developer_mode = st.app_settings.developer_mode();
        TrackerUiSnapshot {
            running: st.running,
            paused: st.paused,
            idle_paused: st.idle_paused,
            distraction_paused: st.distraction_paused,
            is_recovered: st.is_recovered,
            session_name: st.session_name.clone(),
            current_app,
            status_text,
            elapsed_seconds: elapsed,
            elapsed_hms: format_duration_hms(elapsed),
            elapsed_formatted: format_duration(elapsed),
            counted_seconds: counted,
            counted_hms: format_duration_hms(counted),
            counted_formatted: format_duration(counted),
            hourly_rate: rate,
            currency_symbol: currency.clone(),
            earned,
            earned_display: report::format_currency(&currency, earned),
            idle_threshold_seconds: st.idle_threshold_seconds,
            trust_score,
            trust_level,
            chain_valid,
            integrity_status: st.last_integrity_status.clone(),
            dark_mode: theme_style != "light",
            theme_style,
            developer_mode,
            profile_name: st.paths.profile_name.clone(),
            apps: apps_out,
            allocations,
            available_projects: self.tag_manager.projects(),
            has_pending_recovery: st.has_pending_recovery && !st.running,
            pending_recovery_summary,
        }
    }

    pub fn resolver(&self) -> Arc<AppResolver> {
        Arc::clone(&self.resolver)
    }

    pub fn tray_status(&self) -> (bool, bool) {
        let st = self.inner.lock().unwrap();
        (st.running, st.paused)
    }

    pub fn paths(&self) -> ProfilePaths {
        self.inner.lock().unwrap().paths.clone()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    struct MockProbe {
        fg: Mutex<ForegroundApp>,
        idle: Mutex<f64>,
    }

    impl MockProbe {
        fn new(app: &str, exe: &str) -> Arc<Self> {
            Arc::new(Self {
                fg: Mutex::new(ForegroundApp {
                    friendly_name: app.to_string(),
                    exe_path: exe.to_string(),
                }),
                idle: Mutex::new(0.0),
            })
        }
    }

    impl SystemProbe for MockProbe {
        fn get_foreground_app(&self) -> ForegroundApp {
            self.fg.lock().unwrap().clone()
        }
        fn get_idle_seconds(&self) -> f64 {
            *self.idle.lock().unwrap()
        }
    }

    fn setup_tracker(tmp: &TempDir) -> (ProfilePaths, Arc<AppTracker>, Arc<MockProbe>) {
        let paths = ProfilePaths::from_root_and_profile(tmp.path().to_path_buf(), "Test".into());
        paths.ensure_dirs().unwrap();
        let mut settings = AppSettings::default();
        settings.set_idle_threshold_seconds_total(300);
        settings.set_hourly_rate(60.0);
        settings.set_distraction_apps(vec!["reddit".to_string(), "youtube.exe".to_string()]);
        settings.save(&paths.app_settings_file).unwrap();

        let resolver = AppResolver::new(paths.name_overrides_file.clone());
        let tag_mgr = TagManager::new(paths.tags_file.clone(), Arc::clone(&resolver));
        tag_mgr.disable_online_lookup_for_test();
        let probe = MockProbe::new("Visual Studio Code", r"C:\Apps\Code.exe");
        let tracker = AppTracker::new(paths.clone(), resolver, tag_mgr, probe.clone());
        (paths, tracker, probe)
    }

    #[test]
    fn test_retroactive_idle_deduction_and_zero_clamp() {
        let tmp = TempDir::new().unwrap();
        let (_paths, tracker, _) = setup_tracker(&tmp);

        {
            let mut st = tracker.inner.lock().unwrap();
            st.running = true;
            st.paused = false;
            st.session_start = Some(1000.0);
            st.idle_threshold_seconds = 300;
            st.current_app = Some("Visual Studio Code".to_string());
            st.current_start = Some(1499.0);
            st.current_block_start = Some(1000.0);
            st.current_block_active = 500.0;
            st.app_times.insert("Visual Studio Code".to_string(), 500.0);
            st.app_included.insert("Visual Studio Code".to_string(), true);
        }

        tracker.toggle_pause_at(true, false, 1500.0);
        {
            let st = tracker.inner.lock().unwrap();
            assert!(st.paused);
            // 500 - 300 + 1 (since 1499->1500 flush happened after deduct? Wait: check order!)
            // Wait: in toggle_pause_at: deduct happens BEFORE flush, AND current_start was set to None!
            // So exact deducted time is 500 - 300 = 200.0!
            assert_eq!(st.app_times["Visual Studio Code"], 200.0);
            assert_eq!(st.total_paused_time, 300.0);
        }

        // Clamp guard when app_time < idle_threshold_seconds
        {
            let mut st = tracker.inner.lock().unwrap();
            st.paused = false;
            st.app_times.insert("Notepad".to_string(), 50.0);
            st.current_app = Some("Notepad".to_string());
            st.current_start = None;
        }
        tracker.toggle_pause_at(true, false, 1600.0);
        assert_eq!(tracker.inner.lock().unwrap().app_times["Notepad"], 0.0);
    }

    #[test]
    fn test_distraction_auto_pause_and_manual_pause_override() {
        let tmp = TempDir::new().unwrap();
        let (_paths, tracker, _probe) = setup_tracker(&tmp);
        {
            let mut st = tracker.inner.lock().unwrap();
            st.running = true;
            st.enable_distraction_auto_pause = true;
            st.session_start = Some(1000.0);
            st.last_save_time = 1000.0;
        }

        // 1. Focus work app -> active
        tracker.process_poll_tick(
            ForegroundApp {
                friendly_name: "Visual Studio Code".into(),
                exe_path: r"C:\Apps\Code.exe".into(),
            },
            0.0,
            1001.0,
        );
        assert!(!tracker.inner.lock().unwrap().paused);

        // 2. Focus distracting app -> auto-paused
        tracker.process_poll_tick(
            ForegroundApp {
                friendly_name: "Reddit — Browser".into(),
                exe_path: r"C:\Apps\chrome.exe".into(),
            },
            0.0,
            1002.0,
        );
        {
            let st = tracker.inner.lock().unwrap();
            assert!(st.paused);
            assert!(st.distraction_paused);
        }

        // 3. User switches back to work app -> auto-resumed
        tracker.process_poll_tick(
            ForegroundApp {
                friendly_name: "Visual Studio Code".into(),
                exe_path: r"C:\Apps\Code.exe".into(),
            },
            0.0,
            1003.0,
        );
        {
            let st = tracker.inner.lock().unwrap();
            assert!(!st.paused);
            assert!(!st.distraction_paused);
        }

        // 4. User manually clicks Pause while on work app -> stays paused even on work polls!
        tracker.toggle_pause_at(false, false, 1004.0);
        tracker.process_poll_tick(
            ForegroundApp {
                friendly_name: "Visual Studio Code".into(),
                exe_path: r"C:\Apps\Code.exe".into(),
            },
            0.0,
            1005.0,
        );
        assert!(tracker.inner.lock().unwrap().paused);
    }

    #[test]
    fn test_auto_excluded_passthrough_and_sleep_guard_and_crash_recovery() {
        let tmp = TempDir::new().unwrap();
        let (paths, tracker, _probe) = setup_tracker(&tmp);
        {
            let mut st = tracker.inner.lock().unwrap();
            st.running = true;
            st.session_start = Some(1000.0);
            st.last_save_time = 1000.0;
        }

        // Track VS Code
        tracker.process_poll_tick(
            ForegroundApp {
                friendly_name: "Visual Studio Code".into(),
                exe_path: r"C:\Apps\Code.exe".into(),
            },
            0.0,
            1000.0,
        );
        tracker.process_poll_tick(
            ForegroundApp {
                friendly_name: "Visual Studio Code".into(),
                exe_path: r"C:\Apps\Code.exe".into(),
            },
            0.0,
            1001.0,
        );

        // User opens Windows Explorer (auto-excluded) -> time keeps accruing to VS Code, Explorer hidden!
        tracker.process_poll_tick(
            ForegroundApp {
                friendly_name: "Windows Explorer".into(),
                exe_path: r"C:\Windows\explorer.exe".into(),
            },
            0.0,
            1002.0,
        );
        {
            let st = tracker.inner.lock().unwrap();
            assert!(!st.app_times.contains_key("Windows Explorer"));
            assert_eq!(st.app_times["Visual Studio Code"], 2.0);
        }

        // OS Sleep leap guard: +50s gap must clamp elapsed to poll_interval (1.0s) and add 49.0s to paused_time
        tracker.process_poll_tick(
            ForegroundApp {
                friendly_name: "Visual Studio Code".into(),
                exe_path: r"C:\Apps\Code.exe".into(),
            },
            0.0,
            1052.0,
        );
        {
            let st = tracker.inner.lock().unwrap();
            assert_eq!(st.app_times["Visual Studio Code"], 3.0);
            assert_eq!(st.total_paused_time, 49.0);
        }

        // Save active_session.json and verify recover_session on fresh tracker instance
        tracker.save_active_state_snapshot();
        assert!(paths.active_session_file.exists());

        // Stop old background-less state flag before loading fresh tracker
        let resolver2 = AppResolver::new(paths.name_overrides_file.clone());
        let tag_mgr2 = TagManager::new(paths.tags_file.clone(), Arc::clone(&resolver2));
        tag_mgr2.disable_online_lookup_for_test();
        let probe2 = MockProbe::new("Visual Studio Code", r"C:\Apps\Code.exe");
        let tracker2 = AppTracker::new(paths.clone(), resolver2, tag_mgr2, probe2);

        assert!(tracker2.get_pending_recovery_summary().is_some());
        assert!(tracker2.recover_session());
        assert!(tracker2.inner.lock().unwrap().is_recovered);
        assert!(tracker2.inner.lock().unwrap().app_times["Visual Studio Code"] >= 3.0);

        // Clean stop removes active_session.json
        let (rep, _) = tracker2.stop_and_build_report().unwrap();
        assert!(!paths.active_session_file.exists());
        assert!(rep.is_recovered);
    }

    #[test]
    fn test_exclusion_checkbox_persists_to_settings_json() {
        let tmp = TempDir::new().unwrap();
        let (paths, tracker, _) = setup_tracker(&tmp);
        tracker.set_app_included("YouTube", false);

        let reloaded = ExcludedSettings::load(&paths.settings_file);
        assert!(reloaded.is_excluded("YouTube"));
    }

    #[test]
    fn test_ui_snapshot_counted_hms_and_short_autosave_interval() {
        let tmp = TempDir::new().unwrap();
        let (paths, tracker, _) = setup_tracker(&tmp);
        let mut settings = AppSettings::load(&paths.app_settings_file);
        settings.raw.insert("auto_save_seconds".into(), json!(2));
        settings.save(&paths.app_settings_file).unwrap();

        // Reload settings deterministically via start() then immediately stop poll thread
        // or reload via AppTracker::new() so no background poll thread races with synthetic timestamps.
        drop(tracker);
        let resolver = AppResolver::new(paths.name_overrides_file.clone());
        let tag_mgr = TagManager::new(paths.tags_file.clone(), Arc::clone(&resolver));
        tag_mgr.disable_online_lookup_for_test();
        let probe = MockProbe::new("Visual Studio Code", r"C:\Apps\Code.exe");
        let tracker = AppTracker::new(paths.clone(), resolver, tag_mgr, probe);

        {
            let mut st = tracker.inner.lock().unwrap();
            assert_eq!(st.save_interval_secs, 2);
            st.running = true;
            st.session_start = Some(1000.0);
            st.last_save_time = 1000.0;
            st.app_times.insert("Visual Studio Code".into(), 1800.0);
            st.app_included.insert("Visual Studio Code".into(), true);
            st.app_times.insert("Google Chrome".into(), 600.0);
            st.app_included.insert("Google Chrome".into(), false);
        }

        let snap = tracker.ui_snapshot(false);
        assert_eq!(snap.counted_seconds, 1800);
        assert_eq!(snap.counted_hms, "00:30:00");
        assert_eq!(snap.counted_formatted, "0h 30m 00s");

        // 2s autosave interval fires without waiting 5s
        tracker.process_poll_tick(
            ForegroundApp {
                friendly_name: "Visual Studio Code".into(),
                exe_path: r"C:\Apps\Code.exe".into(),
            },
            0.0,
            1002.5,
        );
        assert!(paths.active_session_file.exists());
        let _ = tracker.stop_and_build_report();
    }

    #[test]
    fn test_set_session_name_pre_start_and_clear_on_stop() {
        let tmp = TempDir::new().unwrap();
        let (paths, tracker, _) = setup_tracker(&tmp);

        // Pre-start naming trims control chars/whitespace and does not fabricate active_session.json
        tracker.set_session_name("  \x00Pre-Start\x07 Focus\r\n\t ");
        assert_eq!(tracker.ui_snapshot(false).session_name, "Pre-Start Focus");
        assert!(!paths.active_session_file.exists());

        // Starting with empty session_name preserves the pre-typed pending name
        assert!(tracker.start(""));
        assert_eq!(tracker.ui_snapshot(false).session_name, "Pre-Start Focus");

        let (rep, _) = tracker.stop_and_build_report().unwrap();
        assert_eq!(rep.session_name, "Pre-Start Focus");
        assert_eq!(tracker.ui_snapshot(false).session_name, "");

        // Starting a fresh session with empty name does not reuse the finished session's name
        assert!(tracker.start(""));
        let next_name = tracker.ui_snapshot(false).session_name;
        assert!(next_name.starts_with("Session - "));
        assert_ne!(next_name, "Pre-Start Focus");
        let _ = tracker.stop_and_build_report();
    }

    #[test]
    fn test_set_session_name_mid_session_persists_to_active_report_and_autosave() {
        let tmp = TempDir::new().unwrap();
        let (paths, tracker, _) = setup_tracker(&tmp);

        assert!(tracker.start("Initial Focus"));
        {
            let mut st = tracker.inner.lock().unwrap();
            st.session_start = Some(unix_now_f64() - 12.0);
            st.app_times.insert("Visual Studio Code".into(), 10.0);
            st.app_included.insert("Visual Studio Code".into(), true);
        }

        tracker.set_session_name("  Mid-Session\x00 Sprint\n\r ");
        assert_eq!(
            tracker.ui_snapshot(false).session_name,
            "Mid-Session Sprint"
        );
        assert!(paths.active_session_file.exists());

        let active_raw = fs::read_to_string(&paths.active_session_file).unwrap();
        let active_parsed: ActiveSessionFile = serde_json::from_str(&active_raw).unwrap();
        assert_eq!(active_parsed.session_name, "Mid-Session Sprint");

        // autosave_on_exit stops the running session and writes the updated name into autosave/
        tracker.autosave_on_exit();
        assert!(!paths.active_session_file.exists());

        let autosave_files: Vec<_> = fs::read_dir(&paths.autosave_dir)
            .unwrap()
            .filter_map(|e| e.ok())
            .map(|e| e.path())
            .collect();
        assert_eq!(autosave_files.len(), 1);
        let saved_json: Value =
            serde_json::from_str(&fs::read_to_string(&autosave_files[0]).unwrap()).unwrap();
        assert_eq!(
            saved_json.get("session_name").and_then(|v| v.as_str()),
            Some("Mid-Session Sprint")
        );
    }

    #[test]
    fn test_resume_from_report_preserves_date_tracks_new_activity_and_profile_switch() {
        let tmp = TempDir::new().unwrap();
        let (paths, tracker, _) = setup_tracker(&tmp);

        let saved_file = paths.sessions_dir.join("session_2026-10-05_09-00-00.json");
        fs::write(
            &saved_file,
            serde_json::to_string_pretty(&serde_json::json!({
                "date": "2026-10-05",
                "start": "09:00:00",
                "end": "09:30:00",
                "total_seconds": 1800,
                "counted_seconds": 1800,
                "session_name": "Historical Sprint",
                "apps": [
                    {"name": "Visual Studio Code", "seconds": 1800, "excluded": false, "tag": "Development"}
                ],
                "app_exe_paths": {
                    "Visual Studio Code": "C:\\Apps\\Code.exe"
                },
                "timeline": [
                    {"app": "Visual Studio Code", "start": "09:00:00", "end": "09:30:00"}
                ]
            }))
            .unwrap(),
        )
        .unwrap();

        let resumed_name = tracker.load_from_report(&saved_file).unwrap();
        assert_eq!(resumed_name, "Historical Sprint");
        assert!(tracker.is_running());

        // Concurrent resume & profile switch while running must be rejected
        assert!(tracker.load_from_report(&saved_file).is_err());
        let other_paths = ProfilePaths::from_root_and_profile(paths.app_data_root.clone(), "Other".into());
        assert!(tracker.reload_for_profile_switch(other_paths.clone()).is_err());

        // Add additional time in resumed session
        {
            let mut st = tracker.inner.lock().unwrap();
            st.app_times.insert("Visual Studio Code".into(), 1920.0);
        }
        let (rep, _) = tracker.stop_and_build_report().unwrap();
        assert!(rep.is_resumed);
        assert_eq!(rep.apps[0].tag, "Development");
        assert_eq!(rep.date, "2026-10-05");
        assert_eq!(rep.start, "09:00:00");
        assert!(!rep.new_activity.is_empty());
        assert_eq!(
            rep.new_activity[0].get("new_seconds").and_then(|v| v.as_i64()),
            Some(120)
        );

        // Profile switch succeeds once stopped
        tracker.reload_for_profile_switch(other_paths.clone()).unwrap();
        assert_eq!(tracker.paths().profile_name, "Other");
    }
}
