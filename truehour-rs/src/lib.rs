pub mod appinfo;
pub mod backup;
pub mod config;
pub mod crypto;
pub mod db;
pub mod file_dialog;
pub mod gui;
pub mod http_preview;
pub mod invoice;
pub mod net;
pub mod report;
pub mod secure_time;
pub mod settings;
pub mod tags;
pub mod tracker;
pub mod tray;

use config::{ProfilesConfig, SingleInstanceLock};
use invoice::{BillingData, InvoicePrivacyOverrides};
use report::SessionReportData;
use secure_time::SessionSecurityReport;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, VecDeque};
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use tracker::{AppTracker, TrackerUiSnapshot, Win32Probe};

const ABOUT_LEGAL_HTML: &str = include_str!("../../templates/about_legal.html");
const APP_ICON_PNG: &[u8] = include_bytes!("../icons/icon.png");

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DebugLogEntry {
    pub timestamp: String,
    pub level: String,
    pub message: String,
}

#[derive(Debug, Clone)]
pub struct StopAndSaveResponse {
    pub report: SessionReportData,
    pub saved_path: String,
    pub security: Option<SessionSecurityReport>,
    pub state: TrackerUiSnapshot,
}

#[derive(Debug, Clone)]
pub struct SessionManagerTabData {
    pub tab: String,
    pub sessions: Vec<report::SessionListEntry>,
    pub invoices: Vec<db::InvoiceListItem>,
    pub currency_symbol: String,
}

#[derive(Debug, Clone)]
pub struct ResumeSessionResponse {
    pub session_name: String,
    pub state: TrackerUiSnapshot,
}

#[derive(Debug, Clone)]
pub struct FullSettingsPayload {
    pub settings: settings::FullSettingsDto,
    pub profiles: ProfilesConfig,
    pub data_root: String,
}

#[derive(Debug, Clone)]
pub struct CategoryMetaItem {
    pub name: String,
    pub color: String,
    pub count: usize,
    pub is_builtin: bool,
}

#[derive(Debug, Clone)]
pub struct CategoryAppMappingItem {
    pub app_name: String,
    pub exe_path: String,
    pub tag: String,
    pub tag_color: String,
}

#[derive(Debug, Clone)]
pub struct CategoriesOverviewDto {
    pub categories: Vec<CategoryMetaItem>,
    pub apps: Vec<CategoryAppMappingItem>,
    pub available_projects: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct DashboardInsightsPayload {
    pub live: TrackerUiSnapshot,
    pub history: report::HistoryInsightsDto,
    pub heatmap: Vec<report::HeatmapDayDto>,
    pub weekly_goal_hours: f64,
    pub current_week_hours: f64,
}

pub struct AppCore {
    pub tracker: Arc<AppTracker>,
    instance_lock: SingleInstanceLock,
    debug_logs: Arc<Mutex<VecDeque<DebugLogEntry>>>,
    repaint_ctx: Mutex<Option<egui::Context>>,
    pub tracker_rev: Arc<AtomicU64>,
    pub sessions_rev: Arc<AtomicU64>,
    pub invoices_rev: Arc<AtomicU64>,
    pub settings_rev: Arc<AtomicU64>,
    pub categories_rev: Arc<AtomicU64>,
}

impl AppCore {
    pub fn new(tracker: Arc<AppTracker>, instance_lock: SingleInstanceLock) -> Arc<Self> {
        let core = Arc::new(Self {
            tracker,
            instance_lock,
            debug_logs: Arc::new(Mutex::new(VecDeque::with_capacity(500))),
            repaint_ctx: Mutex::new(None),
            tracker_rev: Arc::new(AtomicU64::new(1)),
            sessions_rev: Arc::new(AtomicU64::new(1)),
            invoices_rev: Arc::new(AtomicU64::new(1)),
            settings_rev: Arc::new(AtomicU64::new(1)),
            categories_rev: Arc::new(AtomicU64::new(1)),
        });
        core.push_debug_log("INFO", "TrueHour v5.0 native GUI initialized (Local-Only)");
        core
    }

    pub fn attach_egui_context(&self, ctx: egui::Context) {
        if let Ok(mut guard) = self.repaint_ctx.lock() {
            *guard = Some(ctx);
        }
    }

    pub fn request_repaint(&self) {
        if let Ok(guard) = self.repaint_ctx.lock() {
            if let Some(ref ctx) = *guard {
                ctx.request_repaint();
            }
        }
    }

    pub fn release_lock(&self) {
        self.instance_lock.release();
    }

    pub fn push_debug_log(&self, level: &str, message: &str) {
        let entry = DebugLogEntry {
            timestamp: chrono::Local::now().format("%H:%M:%S").to_string(),
            level: level.to_string(),
            message: message.to_string(),
        };
        if let Ok(mut logs) = self.debug_logs.lock() {
            if logs.len() >= 500 {
                logs.pop_front();
            }
            logs.push_back(entry);
        }
        self.request_repaint();
    }

    pub fn get_debug_logs(&self) -> Vec<DebugLogEntry> {
        self.debug_logs
            .lock()
            .map(|d| d.iter().cloned().collect())
            .unwrap_or_default()
    }

    pub fn clear_debug_logs(&self) {
        if let Ok(mut logs) = self.debug_logs.lock() {
            logs.clear();
        }
    }

    pub fn emit_test_logs(&self) -> Vec<DebugLogEntry> {
        self.push_debug_log("INFO", "Diagnostics test log [INFO] verified");
        self.push_debug_log("WARN", "Diagnostics test log [WARN] threshold sample check");
        self.push_debug_log("ERROR", "Diagnostics test log [ERROR] simulated test error alert");
        self.get_debug_logs()
    }

    pub fn ui_snapshot(&self) -> TrackerUiSnapshot {
        self.tracker.ui_snapshot(false)
    }

    pub fn start_tracking(&self, session_name: &str) -> TrackerUiSnapshot {
        self.tracker.start(session_name);
        let snap = self.ui_snapshot();
        self.push_debug_log("INFO", &format!("Tracking started: {}", snap.session_name));
        self.tracker_rev.fetch_add(1, Ordering::SeqCst);
        self.request_repaint();
        snap
    }

    pub fn toggle_pause(&self) -> TrackerUiSnapshot {
        let paused = self.tracker.toggle_pause(false, false);
        let snap = self.ui_snapshot();
        self.push_debug_log(
            "INFO",
            if paused {
                "Tracking paused"
            } else {
                "Tracking resumed"
            },
        );
        self.tracker_rev.fetch_add(1, Ordering::SeqCst);
        self.request_repaint();
        snap
    }

    pub fn stop_and_save_session(&self) -> Result<StopAndSaveResponse, String> {
        let Some((mut report_data, security)) = self.tracker.stop_and_build_report() else {
            return Err("No active session to stop".to_string());
        };
        let paths = self.tracker.paths();
        let saved_path = report::save_to_history(&paths, &mut report_data)
            .map_err(|e| format!("Failed to save session: {e}"))?;
        let snap = self.ui_snapshot();
        self.push_debug_log(
            "INFO",
            &format!("Session stopped & saved: {}", saved_path.display()),
        );
        self.tracker_rev.fetch_add(1, Ordering::SeqCst);
        self.sessions_rev.fetch_add(1, Ordering::SeqCst);
        self.request_repaint();
        Ok(StopAndSaveResponse {
            report: report_data,
            saved_path: saved_path.to_string_lossy().to_string(),
            security,
            state: snap,
        })
    }

    pub fn set_session_name(&self, name: &str) -> TrackerUiSnapshot {
        self.tracker.set_session_name(name);
        self.tracker_rev.fetch_add(1, Ordering::SeqCst);
        self.request_repaint();
        self.ui_snapshot()
    }

    pub fn set_app_included(&self, app_name: &str, included: bool) -> TrackerUiSnapshot {
        self.tracker.set_app_included(app_name, included);
        self.tracker_rev.fetch_add(1, Ordering::SeqCst);
        self.request_repaint();
        self.ui_snapshot()
    }

    pub fn set_app_tag(&self, app_name: &str, tag: &str) -> TrackerUiSnapshot {
        self.tracker.set_app_tag(app_name, tag);
        self.tracker_rev.fetch_add(1, Ordering::SeqCst);
        self.categories_rev.fetch_add(1, Ordering::SeqCst);
        self.request_repaint();
        self.ui_snapshot()
    }

    pub fn add_project_category(&self, project: &str) -> Result<TrackerUiSnapshot, String> {
        if self.tracker.add_project_category(project) {
            self.tracker_rev.fetch_add(1, Ordering::SeqCst);
            self.categories_rev.fetch_add(1, Ordering::SeqCst);
            self.request_repaint();
            Ok(self.ui_snapshot())
        } else {
            Err("Category name is empty or already exists".to_string())
        }
    }

    pub fn toggle_distraction_app(&self, app_name: &str, exe_path: &str) -> TrackerUiSnapshot {
        self.tracker.toggle_distraction_app(app_name, exe_path);
        self.tracker_rev.fetch_add(1, Ordering::SeqCst);
        self.settings_rev.fetch_add(1, Ordering::SeqCst);
        self.request_repaint();
        self.ui_snapshot()
    }

    pub fn cycle_theme(&self) -> TrackerUiSnapshot {
        let _next = self.tracker.cycle_theme();
        self.tracker_rev.fetch_add(1, Ordering::SeqCst);
        self.settings_rev.fetch_add(1, Ordering::SeqCst);
        self.request_repaint();
        self.ui_snapshot()
    }

    pub fn set_theme_style(&self, style: &str) -> TrackerUiSnapshot {
        let _applied = self.tracker.set_theme_style(style);
        self.tracker_rev.fetch_add(1, Ordering::SeqCst);
        self.settings_rev.fetch_add(1, Ordering::SeqCst);
        self.request_repaint();
        self.ui_snapshot()
    }

    pub fn set_developer_mode(&self, enabled: bool) -> TrackerUiSnapshot {
        self.tracker.set_developer_mode(enabled);
        self.push_debug_log(
            "INFO",
            if enabled {
                "Developer Options enabled"
            } else {
                "Developer Options disabled"
            },
        );
        self.tracker_rev.fetch_add(1, Ordering::SeqCst);
        self.settings_rev.fetch_add(1, Ordering::SeqCst);
        self.request_repaint();
        self.ui_snapshot()
    }

    pub fn resolve_interrupted_session(&self, recover: bool) -> TrackerUiSnapshot {
        if recover {
            let _ = self.tracker.recover_session();
            self.push_debug_log("INFO", "Recovered interrupted session");
        } else {
            self.tracker.discard_pending_recovery();
            self.push_debug_log("INFO", "Discarded pending recovery session");
        }
        self.tracker_rev.fetch_add(1, Ordering::SeqCst);
        self.sessions_rev.fetch_add(1, Ordering::SeqCst);
        self.request_repaint();
        self.ui_snapshot()
    }

    pub fn list_session_manager_items(&self, tab: &str) -> Result<SessionManagerTabData, String> {
        let paths = self.tracker.paths();
        let app_settings = settings::AppSettings::load(&paths.app_settings_file);
        let currency_symbol = app_settings.currency_symbol();
        match tab {
            "sessions" => Ok(SessionManagerTabData {
                tab: tab.to_string(),
                sessions: report::list_session_files(&paths.sessions_dir),
                invoices: vec![],
                currency_symbol,
            }),
            "autosave" | "recoveries" => Ok(SessionManagerTabData {
                tab: "autosave".to_string(),
                sessions: report::list_session_files(&paths.autosave_dir),
                invoices: vec![],
                currency_symbol,
            }),
            "trash" => Ok(SessionManagerTabData {
                tab: tab.to_string(),
                sessions: report::list_session_files(&paths.trash_dir),
                invoices: vec![],
                currency_symbol,
            }),
            "invoices" => {
                let invoices = db::get_invoices_list(&paths).unwrap_or_default();
                Ok(SessionManagerTabData {
                    tab: tab.to_string(),
                    sessions: vec![],
                    invoices,
                    currency_symbol,
                })
            }
            other => Err(format!("Unsupported Session Manager tab: {other}")),
        }
    }

    pub fn resume_saved_session(
        &self,
        filepath: &str,
        force_stop_active: bool,
    ) -> Result<ResumeSessionResponse, String> {
        if force_stop_active && self.tracker.is_running() {
            self.tracker.autosave_on_exit();
            self.sessions_rev.fetch_add(1, Ordering::SeqCst);
        }
        let session_name = self.tracker.load_from_report(&PathBuf::from(filepath))?;
        let snap = self.ui_snapshot();
        self.push_debug_log("INFO", &format!("Resumed session: {session_name}"));
        self.tracker_rev.fetch_add(1, Ordering::SeqCst);
        self.request_repaint();
        Ok(ResumeSessionResponse {
            session_name,
            state: snap,
        })
    }

    pub fn rename_saved_session(&self, filepath: &str, new_name: &str) -> Result<String, String> {
        let res = report::rename_saved_session(&PathBuf::from(filepath), new_name)
            .map_err(|e| e.to_string())?;
        self.sessions_rev.fetch_add(1, Ordering::SeqCst);
        self.request_repaint();
        Ok(res)
    }

    pub fn trash_saved_session(&self, filepath: &str) -> Result<(), String> {
        let paths = self.tracker.paths();
        report::move_session_to_trash(&paths, &PathBuf::from(filepath))
            .map_err(|e| e.to_string())?;
        self.sessions_rev.fetch_add(1, Ordering::SeqCst);
        self.request_repaint();
        Ok(())
    }

    pub fn restore_trashed_session(&self, filepath: &str) -> Result<(), String> {
        let paths = self.tracker.paths();
        report::restore_session_from_trash(&paths, &PathBuf::from(filepath))?;
        self.sessions_rev.fetch_add(1, Ordering::SeqCst);
        self.request_repaint();
        Ok(())
    }

    pub fn delete_session_permanently(&self, filepath: &str, kind: &str) -> Result<(), String> {
        let paths = self.tracker.paths();
        report::delete_saved_file(&paths, &PathBuf::from(filepath), kind)?;
        self.sessions_rev.fetch_add(1, Ordering::SeqCst);
        self.request_repaint();
        Ok(())
    }

    pub fn merge_selected_sessions(
        &self,
        filepaths: &[String],
        merged_name: &str,
    ) -> Result<String, String> {
        let paths = self.tracker.paths();
        let bufs: Vec<PathBuf> = filepaths.iter().map(PathBuf::from).collect();
        let dest = report::merge_session_files(&paths, &bufs, merged_name)?;
        self.push_debug_log(
            "INFO",
            &format!("Merged {} sessions into {}", bufs.len(), dest.display()),
        );
        self.sessions_rev.fetch_add(1, Ordering::SeqCst);
        self.request_repaint();
        Ok(dest.to_string_lossy().to_string())
    }

    pub fn load_session_report_details(&self, filepath: &str) -> Result<SessionReportData, String> {
        report::load_session_report(&PathBuf::from(filepath))
    }

    pub fn export_session_report_txt_to(
        &self,
        filepath: &str,
        dest: &std::path::Path,
    ) -> Result<(), String> {
        let rep = report::load_session_report(&PathBuf::from(filepath))?;
        report::export_txt(&rep, dest).map_err(|e| format!("Failed exporting report: {e}"))
    }

    pub fn open_session_report_in_browser(&self, filepath: &str) -> Result<(), String> {
        let paths = self.tracker.paths();
        let rep = report::load_session_report(&PathBuf::from(filepath))?;
        let html = report::generate_session_report_html(&paths, &rep);
        http_preview::write_temp_html_and_open("truehour_report", &html).map(|_| ())
    }

    pub fn generate_and_preview_invoice(
        &self,
        filepaths: &[String],
        privacy: InvoicePrivacyOverrides,
    ) -> Result<String, String> {
        let paths = self.tracker.paths();
        let mut full_settings = settings::load_full_settings(&paths);
        full_settings.mask_business_emails = privacy.mask_business_emails;
        full_settings.mask_business_phone = privacy.mask_business_phone;
        full_settings.mask_client_emails = privacy.mask_client_emails;

        let tag_mgr = self.tracker.tag_manager();
        let bufs: Vec<PathBuf> = filepaths.iter().map(PathBuf::from).collect();
        let mut billing = invoice::merge_sessions_for_invoice(
            &tag_mgr,
            &bufs,
            full_settings.hourly_rate,
            &full_settings.currency_symbol,
        )?;
        billing.additional_items = privacy.additional_items.clone();

        let add_total: f64 = privacy.additional_items.iter().map(|i| i.amount).sum();
        let grand_total = ((billing.total_earned + add_total) * 100.0).round() / 100.0;

        let final_invoice_no = privacy
            .invoice_no
            .as_deref()
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .map(str::to_string)
            .unwrap_or_else(|| format!("INV-{}", chrono::Local::now().format("%Y%m%d%H%M%S")));

        let html = invoice::generate_invoice_html(
            &paths,
            &billing,
            &full_settings,
            "draft",
            Some(&final_invoice_no),
            &privacy.additional_items,
        );

        let billing_json = serde_json::to_value(&billing).map_err(|e| e.to_string())?;
        let settings_json = serde_json::to_value(&full_settings).map_err(|e| e.to_string())?;
        let files_json = serde_json::to_value(filepaths).map_err(|e| e.to_string())?;
        let client_name = if full_settings.client_name.trim().is_empty() {
            "Valued Client".to_string()
        } else {
            full_settings.client_name.clone()
        };

        db::save_invoice(
            &paths,
            &final_invoice_no,
            &client_name,
            grand_total,
            &full_settings.currency_symbol,
            "draft",
            &files_json,
            &billing_json,
            &settings_json,
            None,
        )
        .map_err(|e| format!("Failed saving draft invoice: {e}"))?;
        self.invoices_rev.fetch_add(1, Ordering::SeqCst);

        let saved_flag = Arc::new(std::sync::atomic::AtomicBool::new(false));
        let paths_cb = paths.clone();
        let inv_no_cb = final_invoice_no.clone();
        let rev_cb = Arc::clone(&self.invoices_rev);
        let ctx_cb = self.repaint_ctx.lock().ok().and_then(|g| g.clone());

        let url = http_preview::start_invoice_preview_server(html, move || {
            if saved_flag.swap(true, Ordering::SeqCst) {
                return Ok("already_saved");
            }
            if let Ok(Some(rec)) = db::get_invoice_by_no(&paths_cb, &inv_no_cb) {
                if rec.status != "draft" {
                    return Ok("already_saved");
                }
            }
            db::update_invoice_status(&paths_cb, &inv_no_cb, "unpaid")
                .map_err(|e| format!("SQLite update failed: {e}"))?;
            rev_cb.fetch_add(1, Ordering::SeqCst);
            if let Some(ref c) = ctx_cb {
                c.request_repaint();
            }
            Ok("success")
        })?;

        http_preview::open_target_externally(&url)?;
        self.push_debug_log(
            "INFO",
            &format!("Invoice preview opened: {final_invoice_no} at {url}"),
        );
        Ok(final_invoice_no)
    }

    pub fn open_saved_invoice_in_browser(&self, invoice_no: &str) -> Result<(), String> {
        let paths = self.tracker.paths();
        let rec = db::get_invoice_by_no(&paths, invoice_no)
            .map_err(|e| e.to_string())?
            .ok_or_else(|| format!("Invoice '{invoice_no}' was not found."))?;
        let billing: BillingData = serde_json::from_str(&rec.billing_data)
            .map_err(|e| format!("Corrupt invoice billing payload: {e}"))?;
        let settings_dto: settings::FullSettingsDto = serde_json::from_str(&rec.settings_data)
            .unwrap_or_else(|_| settings::load_full_settings(&paths));
        let add_items = billing.additional_items.clone();
        let html = invoice::generate_invoice_html(
            &paths,
            &billing,
            &settings_dto,
            &rec.status,
            Some(&rec.invoice_no),
            &add_items,
        );

        if rec.status.eq_ignore_ascii_case("draft") {
            let saved_flag = Arc::new(std::sync::atomic::AtomicBool::new(false));
            let paths_cb = paths.clone();
            let inv_cb = rec.invoice_no.clone();
            let rev_cb = Arc::clone(&self.invoices_rev);
            let ctx_cb = self.repaint_ctx.lock().ok().and_then(|g| g.clone());
            let url = http_preview::start_invoice_preview_server(html, move || {
                if saved_flag.swap(true, Ordering::SeqCst) {
                    return Ok("already_saved");
                }
                db::update_invoice_status(&paths_cb, &inv_cb, "unpaid")
                    .map_err(|e| format!("SQLite update failed: {e}"))?;
                rev_cb.fetch_add(1, Ordering::SeqCst);
                if let Some(ref c) = ctx_cb {
                    c.request_repaint();
                }
                Ok("success")
            })?;
            http_preview::open_target_externally(&url)?;
        } else {
            http_preview::write_temp_html_and_open("truehour_invoice", &html)?;
        }
        Ok(())
    }

    pub fn cycle_invoice_status(&self, invoice_no: &str) -> Result<String, String> {
        let paths = self.tracker.paths();
        let rec = db::get_invoice_by_no(&paths, invoice_no)
            .map_err(|e| e.to_string())?
            .ok_or_else(|| "Invoice not found".to_string())?;
        let next = match rec.status.to_ascii_lowercase().as_str() {
            "draft" => "unpaid",
            "unpaid" => "paid",
            "paid" => "unpaid",
            _ => "unpaid",
        };
        db::update_invoice_status(&paths, invoice_no, next).map_err(|e| e.to_string())?;
        self.invoices_rev.fetch_add(1, Ordering::SeqCst);
        self.request_repaint();
        Ok(next.to_string())
    }

    pub fn rename_invoice_no(&self, old_no: &str, new_no: &str) -> Result<(), String> {
        let paths = self.tracker.paths();
        db::rename_invoice(&paths, old_no, new_no).map_err(|e| e.to_string())?;
        self.invoices_rev.fetch_add(1, Ordering::SeqCst);
        self.request_repaint();
        Ok(())
    }

    pub fn delete_invoice_record(&self, invoice_no: &str) -> Result<(), String> {
        let paths = self.tracker.paths();
        db::delete_invoice(&paths, invoice_no).map_err(|e| e.to_string())?;
        self.invoices_rev.fetch_add(1, Ordering::SeqCst);
        self.request_repaint();
        Ok(())
    }

    pub fn get_full_settings(&self) -> FullSettingsPayload {
        let paths = self.tracker.paths();
        let dto = settings::load_full_settings(&paths);
        let profiles = config::load_or_init_profiles(&paths.app_data_root).unwrap_or_default();
        FullSettingsPayload {
            settings: dto,
            profiles,
            data_root: paths.app_data_root.to_string_lossy().to_string(),
        }
    }

    pub fn save_full_settings(&self, dto: &settings::FullSettingsDto) -> Result<TrackerUiSnapshot, String> {
        let paths = self.tracker.paths();
        settings::save_full_settings(&paths, dto)?;
        self.tracker.reload_app_settings_and_exclusions();
        self.push_debug_log("INFO", "Settings saved");
        self.tracker_rev.fetch_add(1, Ordering::SeqCst);
        self.settings_rev.fetch_add(1, Ordering::SeqCst);
        self.request_repaint();
        Ok(self.ui_snapshot())
    }

    pub fn switch_profile(&self, name: &str) -> Result<FullSettingsPayload, String> {
        if self.tracker.is_running() {
            return Err("Stop the active tracking session before switching profiles.".to_string());
        }
        let root = self.tracker.paths().app_data_root;
        let cfg = config::switch_profile(&root, name)?;
        let new_paths = config::ProfilePaths::from_root_and_profile(root, cfg.active_profile);
        self.tracker.reload_for_profile_switch(new_paths.clone())?;
        self.push_debug_log(
            "INFO",
            &format!("Switched active profile to '{}'", new_paths.profile_name),
        );
        self.tracker_rev.fetch_add(1, Ordering::SeqCst);
        self.settings_rev.fetch_add(1, Ordering::SeqCst);
        self.sessions_rev.fetch_add(1, Ordering::SeqCst);
        self.invoices_rev.fetch_add(1, Ordering::SeqCst);
        self.categories_rev.fetch_add(1, Ordering::SeqCst);
        self.request_repaint();
        Ok(self.get_full_settings())
    }

    pub fn create_profile(&self, name: &str) -> Result<ProfilesConfig, String> {
        let root = self.tracker.paths().app_data_root;
        config::create_profile(&root, name)
    }

    pub fn rename_profile(&self, old_name: &str, new_name: &str) -> Result<ProfilesConfig, String> {
        let cur_paths = self.tracker.paths();
        let renaming_active = cur_paths.profile_name == old_name;
        if renaming_active && self.tracker.is_running() {
            return Err("Stop the active tracking session before renaming the active profile.".to_string());
        }
        let cfg = config::rename_profile(&cur_paths.app_data_root, old_name, new_name)?;
        if renaming_active {
            let new_paths = config::ProfilePaths::from_root_and_profile(
                cur_paths.app_data_root,
                cfg.active_profile.clone(),
            );
            self.tracker.reload_for_profile_switch(new_paths)?;
            self.tracker_rev.fetch_add(1, Ordering::SeqCst);
            self.settings_rev.fetch_add(1, Ordering::SeqCst);
            self.request_repaint();
        }
        Ok(cfg)
    }

    pub fn delete_profile(&self, name: &str) -> Result<FullSettingsPayload, String> {
        let cur_paths = self.tracker.paths();
        if cur_paths.profile_name == name && self.tracker.is_running() {
            return Err("Stop the active tracking session before deleting the active profile.".to_string());
        }
        let cfg = config::delete_profile(&cur_paths.app_data_root, name)?;
        let next_paths = config::ProfilePaths::from_root_and_profile(
            cur_paths.app_data_root,
            cfg.active_profile,
        );
        if cur_paths.profile_name == name {
            self.tracker.reload_for_profile_switch(next_paths)?;
            self.tracker_rev.fetch_add(1, Ordering::SeqCst);
            self.settings_rev.fetch_add(1, Ordering::SeqCst);
            self.sessions_rev.fetch_add(1, Ordering::SeqCst);
            self.invoices_rev.fetch_add(1, Ordering::SeqCst);
            self.categories_rev.fetch_add(1, Ordering::SeqCst);
            self.request_repaint();
        }
        Ok(self.get_full_settings())
    }

    pub fn import_qr_code(&self, src: &std::path::Path) -> Result<settings::QrCodeItemDto, String> {
        let paths = self.tracker.paths();
        settings::import_qr_code_image(&paths, src)
    }

    pub fn delete_qr_code_file(&self, filename: &str) {
        let paths = self.tracker.paths();
        settings::delete_qr_code_image(&paths, filename);
    }

    pub fn edit_config_txt_file(&self, kind: &str) -> Result<(), String> {
        let paths = self.tracker.paths();
        let target = match kind {
            "auto_excluded" => {
                settings::create_auto_excluded_if_missing(&paths.auto_excluded_file);
                paths.auto_excluded_file
            }
            "name_overrides" => {
                self.tracker.resolver().reload_name_overrides();
                paths.name_overrides_file
            }
            other => return Err(format!("Unsupported config file kind: {other}")),
        };
        http_preview::open_folder_or_file(&target)
    }

    pub fn reload_exclusions_and_overrides(&self) -> TrackerUiSnapshot {
        self.tracker.reload_app_settings_and_exclusions();
        self.push_debug_log("INFO", "Reloaded name_overrides.txt and auto_excluded_apps.txt");
        self.tracker_rev.fetch_add(1, Ordering::SeqCst);
        self.request_repaint();
        self.ui_snapshot()
    }

    pub fn open_profile_folder(&self, kind: Option<&str>) -> Result<(), String> {
        let paths = self.tracker.paths();
        let dir = resolve_profile_folder_dir(&paths, kind)?;
        std::fs::create_dir_all(&dir)
            .map_err(|e| format!("Failed to create folder {}: {e}", dir.display()))?;
        #[cfg(windows)]
        {
            std::process::Command::new("explorer.exe")
                .arg(&dir)
                .spawn()
                .map_err(|e| format!("Failed to open Explorer for {}: {e}", dir.display()))?;
            Ok(())
        }
        #[cfg(not(windows))]
        {
            let _ = &dir;
            Err("Opening profile folders is only supported on Windows".to_string())
        }
    }

    pub fn open_data_root_folder(&self) -> Result<(), String> {
        let root = self.tracker.paths().app_data_root;
        std::fs::create_dir_all(&root).map_err(|e| e.to_string())?;
        http_preview::open_folder_or_file(&root)
    }

    pub fn reveal_app_executable(&self, exe_path: &str) -> Result<(), String> {
        let valid_path = validate_reveal_executable_path(exe_path)?;
        #[cfg(windows)]
        {
            std::process::Command::new("explorer.exe")
                .arg(format!("/select,{}", valid_path))
                .spawn()
                .map_err(|e| format!("Failed to reveal executable in Explorer: {e}"))?;
            Ok(())
        }
        #[cfg(not(windows))]
        {
            let _ = valid_path;
            Err("Revealing executables is only supported on Windows".to_string())
        }
    }

    pub fn open_external_url(&self, url: &str) -> Result<(), String> {
        let trimmed = url.trim();
        if !(trimmed.starts_with("https://") || trimmed.starts_with("http://")) {
            return Err("Only http:// or https:// URLs can be opened externally.".to_string());
        }
        http_preview::open_target_externally(trimmed)
    }

    pub fn open_legal_notices(&self) -> Result<(), String> {
        http_preview::write_temp_html_and_open("truehour_legal", ABOUT_LEGAL_HTML).map(|_| ())
    }

    pub fn get_categories_overview(&self) -> CategoriesOverviewDto {
        let paths = self.tracker.paths();
        let tag_mgr = self.tracker.tag_manager();
        let (projects, mapped_entries) = tag_mgr.get_all_mappings_snapshot();

        let mut exes = report::scan_historical_app_exes(&paths);
        for (k, v) in self.tracker.known_app_exes() {
            if !v.is_empty() {
                exes.entry(k).or_insert(v);
            }
        }

        let mut app_map: HashMap<String, String> = HashMap::new();
        for (app_name, tag) in mapped_entries {
            app_map.insert(app_name, tag);
        }
        for app_name in self.tracker.known_app_exes().keys() {
            if !app_map.contains_key(app_name) {
                app_map.insert(app_name.clone(), tag_mgr.get_mapped_tag(app_name));
            }
        }

        let mut counts: HashMap<String, usize> = HashMap::new();
        for tag in app_map.values() {
            *counts.entry(tag.clone()).or_insert(0) += 1;
        }

        let categories: Vec<CategoryMetaItem> = projects
            .iter()
            .map(|p| CategoryMetaItem {
                name: p.clone(),
                color: report::project_color(p).to_string(),
                count: *counts.get(p).unwrap_or(&0),
                is_builtin: tags::DEFAULT_PROJECTS
                    .iter()
                    .any(|&d| d.eq_ignore_ascii_case(p)),
            })
            .collect();

        let mut apps: Vec<CategoryAppMappingItem> = app_map
            .into_iter()
            .map(|(app_name, tag)| {
                let exe_path = exes.get(&app_name).cloned().unwrap_or_default();
                CategoryAppMappingItem {
                    app_name,
                    exe_path,
                    tag_color: report::project_color(&tag).to_string(),
                    tag,
                }
            })
            .collect();
        apps.sort_by(|a, b| a.app_name.to_lowercase().cmp(&b.app_name.to_lowercase()));

        CategoriesOverviewDto {
            categories,
            apps,
            available_projects: projects,
        }
    }

    pub fn delete_project_category(&self, project: &str) -> Result<CategoriesOverviewDto, String> {
        self.tracker.tag_manager().delete_project(project)?;
        self.categories_rev.fetch_add(1, Ordering::SeqCst);
        self.tracker_rev.fetch_add(1, Ordering::SeqCst);
        self.request_repaint();
        Ok(self.get_categories_overview())
    }

    pub fn get_dashboard_insights(&self, period: &str) -> DashboardInsightsPayload {
        let paths = self.tracker.paths();
        let app_settings = settings::AppSettings::load(&paths.app_settings_file);
        let hourly_rate = app_settings.hourly_rate();
        let curr_sym = app_settings.currency_symbol();
        let weekly_goal_hours = app_settings.weekly_goal_hours();

        let live = self.ui_snapshot();
        let history = report::aggregate_history_data(&paths, period, hourly_rate, &curr_sym);
        let week_data = report::aggregate_history_data(&paths, "week", hourly_rate, &curr_sym);
        let current_week_secs =
            week_data.counted_seconds + if live.running { live.counted_seconds } else { 0 };
        let current_week_hours = ((current_week_secs as f64 / 3600.0) * 100.0).round() / 100.0;
        let heatmap = report::get_activity_heatmap(&paths);

        DashboardInsightsPayload {
            live,
            history,
            heatmap,
            weekly_goal_hours,
            current_week_hours,
        }
    }

    pub fn save_weekly_goal_hours(&self, hours: f64) -> f64 {
        let saved = self.tracker.update_weekly_goal_hours(hours);
        self.settings_rev.fetch_add(1, Ordering::SeqCst);
        self.request_repaint();
        saved
    }
}

pub fn resolve_profile_folder_dir(
    paths: &config::ProfilePaths,
    kind: Option<&str>,
) -> Result<PathBuf, String> {
    let normalized = kind
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .unwrap_or("sessions")
        .to_ascii_lowercase();
    match normalized.as_str() {
        "sessions" => Ok(paths.sessions_dir.clone()),
        "autosave" => Ok(paths.autosave_dir.clone()),
        "trash" => Ok(paths.trash_dir.clone()),
        "profile" => Ok(paths.profile_dir.clone()),
        other => Err(format!("Unsupported profile folder kind: {other}")),
    }
}

pub fn validate_reveal_executable_path(exe_path: &str) -> Result<&str, String> {
    let trimmed = exe_path.trim();
    if trimmed.is_empty() {
        return Err("Executable path is empty".to_string());
    }
    if !std::path::Path::new(trimmed).exists() {
        return Err(format!("Executable path does not exist: {trimmed}"));
    }
    Ok(trimmed)
}

pub fn compute_suggested_invoice_no(session_names: &[&str]) -> String {
    if session_names.is_empty() {
        return String::new();
    }
    if session_names.len() == 1 {
        return session_names[0].to_string();
    }
    let first = session_names[0];
    let last = session_names[session_names.len() - 1];
    if first == last {
        first.to_string()
    } else {
        format!("{first}_to_{last}")
    }
}

pub fn load_embedded_icon() -> Option<egui::IconData> {
    let img = image::load_from_memory(APP_ICON_PNG).ok()?;
    let rgba = img.to_rgba8();
    let (width, height) = rgba.dimensions();
    Some(egui::IconData {
        rgba: rgba.into_raw(),
        width,
        height,
    })
}

pub fn run() {
    let paths = match config::resolve_active_profile() {
        Ok(p) => p,
        Err(e) => {
            config::show_native_error_dialog(
                "TrueHour Startup Error",
                &format!("Failed resolving profile directory:\n{e}"),
            );
            std::process::exit(1);
        }
    };

    let instance_lock = match SingleInstanceLock::acquire(&paths.lock_file) {
        Ok(lock) => lock,
        Err(_) => {
            if tray::try_signal_existing_instance() {
                std::process::exit(0);
            }
            config::show_native_error_dialog(
                "TrueHour Already Running",
                "Another TrueHour instance (Python v4.2 or Rust v5.0) is already running.\n\nOnly one instance can track active time at once.",
            );
            std::process::exit(0);
        }
    };

    if let Err(e) = config::ensure_first_launch_safety_backup(&paths) {
        config::show_native_error_dialog(
            "TrueHour Backup Warning",
            &format!("Could not complete automatic pre-v5 profile safety backup:\n{e}"),
        );
    }

    if let Err(e) = settings::ensure_profile_bootstrap_files(&paths) {
        config::show_native_error_dialog(
            "TrueHour Startup Error",
            &format!("Failed initializing profile files:\n{e}"),
        );
        instance_lock.release();
        std::process::exit(1);
    }

    if let Err(e) = db::init_database(&paths) {
        eprintln!("[TrueHour] SQLite init warning: {e}");
    } else {
        let _ = db::rebuild_all_summaries(&paths, false);
    }

    let resolver = appinfo::AppResolver::new(paths.name_overrides_file.clone());
    let tag_manager = tags::TagManager::new(paths.tags_file.clone(), Arc::clone(&resolver));
    let probe = Arc::new(Win32Probe::new(Arc::clone(&resolver)));
    let tracker = AppTracker::new(paths, resolver, tag_manager, probe);
    let initial_theme = tracker.theme_style();

    let core = AppCore::new(tracker, instance_lock);

    let core_for_cb = Arc::clone(&core);
    core.tracker.set_on_update(Arc::new(move || {
        core_for_cb.tracker_rev.fetch_add(1, Ordering::SeqCst);
        core_for_cb.request_repaint();
    }));

    let mut viewport_size = [440.0, 520.0];
    let mut viewport_min_size = [440.0, 500.0];
    if std::env::var("TRUEHOUR_SCREENSHOT_PREFIX")
        .ok()
        .is_some_and(|s| !s.trim().is_empty())
    {
        if let Ok(view) = std::env::var("TRUEHOUR_INITIAL_VIEW") {
            let v = view.trim();
            viewport_min_size = [200.0, 120.0];
            if v.starts_with("sessions") {
                viewport_size = [520.0, 540.0];
            } else if v.starts_with("settings") {
                viewport_size = [620.0, 700.0];
            } else if v == "categories" {
                viewport_size = [940.0, 620.0];
            } else if v.starts_with("dashboard") {
                viewport_size = [840.0, 700.0];
            } else if v.starts_with("report:") {
                viewport_size = [720.0, 680.0];
            } else if v == "about" {
                viewport_size = [360.0, 310.0];
            } else if v == "debug" {
                viewport_size = [640.0, 420.0];
            } else if v.starts_with("resumed_dialog:") {
                viewport_size = [340.0, 155.0];
            }
        }
    }

    let icon_data = load_embedded_icon().map(Arc::new);
    let mut viewport = egui::ViewportBuilder::default()
        .with_title("TrueHour")
        .with_inner_size(viewport_size)
        .with_min_inner_size(viewport_min_size)
        .with_resizable(true);
    if let Some(ref icon) = icon_data {
        viewport = viewport.with_icon(Arc::clone(icon));
    }

    let options = eframe::NativeOptions {
        viewport,
        renderer: eframe::Renderer::Glow,
        centered: true,
        persist_window: false,
        run_and_return: true,
        ..Default::default()
    };

    let core_for_gui = Arc::clone(&core);
    let icon_for_gui = icon_data.clone();
    let res = eframe::run_native(
        "TrueHour",
        options,
        Box::new(move |cc| {
            Ok(Box::new(gui::TrueHourGuiApp::new(
                cc,
                core_for_gui,
                icon_for_gui,
                initial_theme,
            )))
        }),
    );

    if let Err(err) = res {
        config::show_native_error_dialog(
            "TrueHour Graphics Error",
            &format!("Failed starting TrueHour native window:\n{err}"),
        );
    }

    core.tracker.autosave_on_exit();
    core.release_lock();
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn test_resolve_profile_folder_dir_kinds() {
        let tmp = TempDir::new().unwrap();
        let paths =
            config::ProfilePaths::from_root_and_profile(tmp.path().to_path_buf(), "Test".into());

        assert_eq!(resolve_profile_folder_dir(&paths, None).unwrap(), paths.sessions_dir);
        assert_eq!(resolve_profile_folder_dir(&paths, Some("")).unwrap(), paths.sessions_dir);
        assert_eq!(resolve_profile_folder_dir(&paths, Some("  ")).unwrap(), paths.sessions_dir);
        assert_eq!(
            resolve_profile_folder_dir(&paths, Some("sessions")).unwrap(),
            paths.sessions_dir
        );
        assert_eq!(
            resolve_profile_folder_dir(&paths, Some("AUTOSAVE")).unwrap(),
            paths.autosave_dir
        );
        assert_eq!(
            resolve_profile_folder_dir(&paths, Some("trash")).unwrap(),
            paths.trash_dir
        );
        assert_eq!(
            resolve_profile_folder_dir(&paths, Some("profile")).unwrap(),
            paths.profile_dir
        );
        assert!(resolve_profile_folder_dir(&paths, Some("unknown")).is_err());
    }

    #[test]
    fn test_validate_reveal_executable_path() {
        let tmp = TempDir::new().unwrap();
        let dummy_exe = tmp.path().join("dummy.exe");
        std::fs::write(&dummy_exe, b"MZ").unwrap();

        assert!(validate_reveal_executable_path("").is_err());
        assert!(validate_reveal_executable_path("   ").is_err());
        assert!(validate_reveal_executable_path(
            &tmp.path().join("missing.exe").to_string_lossy()
        )
        .is_err());

        let valid_str = dummy_exe.to_string_lossy().to_string();
        assert_eq!(validate_reveal_executable_path(&valid_str).unwrap(), valid_str);
    }

    #[test]
    fn test_suggested_invoice_no_logic() {
        assert_eq!(compute_suggested_invoice_no(&[]), "");
        assert_eq!(compute_suggested_invoice_no(&["Week 26 Day 2"]), "Week 26 Day 2");
        assert_eq!(compute_suggested_invoice_no(&["Day 1", "Day 1"]), "Day 1");
        assert_eq!(
            compute_suggested_invoice_no(&["Week 26 Day 1", "Week 26 Day 2"]),
            "Week 26 Day 1_to_Week 26 Day 2"
        );
    }
}
