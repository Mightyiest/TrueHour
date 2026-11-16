pub mod about_window;
pub mod categories_window;
pub mod dashboard_window;
pub mod debug_window;
pub mod icons;
pub mod main_window;
pub mod modals;
pub mod report_window;
pub mod sessions_window;
pub mod settings_window;
pub mod theme;
pub mod widgets;

use crate::backup::ImportBackupResult;
use crate::settings::QrCodeItemDto;
use crate::tracker::TrackerUiSnapshot;
use crate::tray::{SystemTray, TrayAction};
use crate::AppCore;
use egui::{
    ColorImage, Frame, Margin, TextureHandle, TextureOptions, ViewportCommand,
};
use modals::{AlertKind, RootModalState};
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::mpsc::{self, Receiver, Sender};
use std::sync::Arc;
use std::time::Instant;

pub enum AsyncTaskResult {
    ExportReportSaved(Result<bool, String>),
    LogoPicked(Option<PathBuf>),
    QrPicked(Result<Option<QrCodeItemDto>, String>),
    LocalBackupDone {
        scope: String,
        result: Result<Option<String>, String>,
    },
    LocalImportDone {
        archive_path: String,
        result: ImportBackupResult,
    },
}

pub enum GuiCmd {
    OpenSessions,
    OpenSettings(Option<settings_window::SettingsTab>),
    OpenCategories,
    OpenDashboard(Option<dashboard_window::DashTab>),
    OpenReport(String),
    OpenAbout,
    OpenDebug,
    ShowResumedDialog(String),
    ShowAlert {
        title: String,
        message: String,
        kind: AlertKind,
    },
    ShowToast(String),
    FocusMain,
    SetTheme(String),
    RequestExit,
}

#[derive(Default)]
pub struct TextureCache {
    app_icons: HashMap<String, Option<TextureHandle>>,
    image_files: HashMap<String, Option<TextureHandle>>,
}

impl TextureCache {
    pub fn get_app_icon(
        &mut self,
        ctx: &egui::Context,
        core: &Arc<AppCore>,
        exe_path: &str,
    ) -> Option<&TextureHandle> {
        if exe_path.is_empty() || exe_path.eq_ignore_ascii_case("truehour.exe") {
            return None;
        }
        if !self.app_icons.contains_key(exe_path) {
            let loaded = core
                .tracker
                .resolver()
                .get_icon_rgba(exe_path, 32)
                .and_then(|rgba| {
                    if rgba.len() == 32 * 32 * 4 {
                        let img = ColorImage::from_rgba_unmultiplied([32, 32], &rgba);
                        Some(ctx.load_texture(
                            format!("app_icon_{exe_path}"),
                            img,
                            TextureOptions::LINEAR,
                        ))
                    } else {
                        None
                    }
                });
            if self.app_icons.len() >= 256 {
                self.app_icons.clear();
            }
            self.app_icons.insert(exe_path.to_string(), loaded);
        }
        self.app_icons.get(exe_path).and_then(|o| o.as_ref())
    }

    pub fn get_image_file(
        &mut self,
        ctx: &egui::Context,
        path: &Path,
    ) -> Option<&TextureHandle> {
        let key = path.to_string_lossy().to_string();
        if key.is_empty() {
            return None;
        }
        if !self.image_files.contains_key(&key) {
            let loaded = std::fs::read(path).ok().and_then(|bytes| {
                let dyn_img = image::load_from_memory(&bytes).ok()?;
                let rgba = dyn_img.to_rgba8();
                let (w, h) = rgba.dimensions();
                let color_img =
                    ColorImage::from_rgba_unmultiplied([w as usize, h as usize], &rgba);
                Some(ctx.load_texture(
                    format!("img_file_{key}"),
                    color_img,
                    TextureOptions::LINEAR,
                ))
            });
            if self.image_files.len() >= 128 {
                self.image_files.clear();
            }
            self.image_files.insert(key.clone(), loaded);
        }
        self.image_files.get(&key).and_then(|o| o.as_ref())
    }
}

struct ToastBanner {
    text: String,
    expires_at: Instant,
}

pub struct TrueHourGuiApp {
    core: Arc<AppCore>,
    icon_data: Option<Arc<egui::IconData>>,
    palette: theme::ThemePalette,
    current_theme_style: String,
    last_title: String,
    last_tracker_rev: u64,
    last_settings_rev: u64,
    snapshot: TrackerUiSnapshot,

    tray: SystemTray,
    tray_rx: Receiver<TrayAction>,
    task_tx: Sender<AsyncTaskResult>,
    task_rx: Receiver<AsyncTaskResult>,
    main_visible: bool,
    allow_exit: bool,
    cleaned_up: bool,

    tex_cache: TextureCache,
    main_state: main_window::MainWindowState,
    sessions_state: sessions_window::SessionsWindowState,
    settings_state: settings_window::SettingsWindowState,
    report_state: report_window::ReportWindowState,
    categories_state: categories_window::CategoriesWindowState,
    dashboard_state: dashboard_window::DashboardWindowState,
    about_state: about_window::AboutWindowState,
    debug_state: debug_window::DebugWindowState,

    root_modal: Option<RootModalState>,
    session_resumed_dialog: Option<String>,
    session_resumed_pos: Option<egui::Pos2>,
    toast: Option<ToastBanner>,

    // Inert unless TRUEHOUR_SCREENSHOT_PREFIX is set in env
    screenshot_prefix: Option<String>,
    screenshot_target: Option<ScreenshotTarget>,
    screenshot_frames: u32,
    screenshot_pending: Option<Arc<AtomicUsize>>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ScreenshotTarget {
    Main,
    ResumedDialog,
    Sessions,
    Settings,
    Report,
    Categories,
    Dashboard,
    About,
    Debug,
}

impl TrueHourGuiApp {
    pub fn new(
        cc: &eframe::CreationContext<'_>,
        core: Arc<AppCore>,
        icon_data: Option<Arc<egui::IconData>>,
        initial_theme: String,
    ) -> Self {
        core.attach_egui_context(cc.egui_ctx.clone());
        theme::install_fonts(&cc.egui_ctx);
        let palette = theme::apply_theme(&cc.egui_ctx, &initial_theme);
        cc.egui_ctx
            .send_viewport_cmd(ViewportCommand::SetTheme(palette.kind.system_theme()));

        let snapshot = core.ui_snapshot();
        let (tray_tx, tray_rx) = mpsc::channel();
        let tray = SystemTray::start(
            cc.egui_ctx.clone(),
            tray_tx,
            snapshot.running,
            snapshot.paused,
        );
        let (task_tx, task_rx) = mpsc::channel();

        let screenshot_prefix = std::env::var("TRUEHOUR_SCREENSHOT_PREFIX")
            .ok()
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty());

        let mut app = Self {
            core: Arc::clone(&core),
            icon_data,
            palette,
            current_theme_style: initial_theme,
            last_title: "TrueHour".to_string(),
            last_tracker_rev: core.tracker_rev.load(Ordering::SeqCst),
            last_settings_rev: core.settings_rev.load(Ordering::SeqCst),
            snapshot,
            tray,
            tray_rx,
            task_tx,
            task_rx,
            main_visible: true,
            allow_exit: false,
            cleaned_up: false,
            tex_cache: TextureCache::default(),
            main_state: main_window::MainWindowState::default(),
            sessions_state: sessions_window::SessionsWindowState::default(),
            settings_state: settings_window::SettingsWindowState::default(),
            report_state: report_window::ReportWindowState::default(),
            categories_state: categories_window::CategoriesWindowState::default(),
            dashboard_state: dashboard_window::DashboardWindowState::default(),
            about_state: about_window::AboutWindowState::default(),
            debug_state: debug_window::DebugWindowState::default(),
            root_modal: None,
            session_resumed_dialog: None,
            session_resumed_pos: None,
            toast: None,
            screenshot_prefix,
            screenshot_target: None,
            screenshot_frames: 0,
            screenshot_pending: None,
        };

        let in_screenshot_mode = app.screenshot_prefix.is_some();

        // Optional automation/verification view pre-open
        if let Ok(init_view) = std::env::var("TRUEHOUR_INITIAL_VIEW") {
            let trimmed = init_view.trim();
            match trimmed {
                "sessions" => {
                    app.sessions_state.open = true;
                    if in_screenshot_mode {
                        app.screenshot_target = Some(ScreenshotTarget::Sessions);
                    }
                }
                "sessions:invoices" => {
                    app.sessions_state.open = true;
                    app.sessions_state.tab = sessions_window::SessionTab::Invoices;
                    if in_screenshot_mode {
                        app.screenshot_target = Some(ScreenshotTarget::Sessions);
                    }
                }
                "sessions:gen_invoice" => {
                    app.sessions_state.open = true;
                    app.sessions_state.open_generate_invoice_preview(&app.core);
                    if in_screenshot_mode {
                        app.screenshot_target = Some(ScreenshotTarget::Sessions);
                    }
                }
                "settings" => {
                    app.settings_state.open = true;
                    if in_screenshot_mode {
                        app.screenshot_target = Some(ScreenshotTarget::Settings);
                    }
                }
                "settings:general_bottom" => {
                    app.settings_state.open = true;
                    app.settings_state.tab = settings_window::SettingsTab::General;
                    app.settings_state.scroll_to_bottom_frames = 4;
                    if in_screenshot_mode {
                        app.screenshot_target = Some(ScreenshotTarget::Settings);
                    }
                }
                "settings:billing" => {
                    app.settings_state.open = true;
                    app.settings_state.tab = settings_window::SettingsTab::Billing;
                    if in_screenshot_mode {
                        app.screenshot_target = Some(ScreenshotTarget::Settings);
                    }
                }
                "settings:billing_bottom" => {
                    app.settings_state.open = true;
                    app.settings_state.tab = settings_window::SettingsTab::Billing;
                    app.settings_state.scroll_to_bottom_frames = 4;
                    if in_screenshot_mode {
                        app.screenshot_target = Some(ScreenshotTarget::Settings);
                    }
                }
                "categories" => {
                    app.categories_state.open = true;
                    if in_screenshot_mode {
                        app.screenshot_target = Some(ScreenshotTarget::Categories);
                    }
                }
                "dashboard" => {
                    app.dashboard_state.open = true;
                    if in_screenshot_mode {
                        app.screenshot_target = Some(ScreenshotTarget::Dashboard);
                    }
                }
                "dashboard:history" => {
                    app.dashboard_state.open = true;
                    app.dashboard_state.tab = dashboard_window::DashTab::History;
                    if in_screenshot_mode {
                        app.screenshot_target = Some(ScreenshotTarget::Dashboard);
                    }
                }
                "dashboard:goals" => {
                    app.dashboard_state.open = true;
                    app.dashboard_state.tab = dashboard_window::DashTab::Goals;
                    if in_screenshot_mode {
                        app.screenshot_target = Some(ScreenshotTarget::Dashboard);
                    }
                }
                "about" => {
                    app.about_state.open = true;
                    if in_screenshot_mode {
                        app.screenshot_target = Some(ScreenshotTarget::About);
                    }
                }
                "debug" => {
                    app.debug_state.open = true;
                    if in_screenshot_mode {
                        let _ = app.core.emit_test_logs();
                        app.screenshot_target = Some(ScreenshotTarget::Debug);
                    }
                }
                "alert_stop_error" => {
                    app.root_modal = Some(RootModalState::Alert {
                        title: "Stop Session Error".into(),
                        message: "No active session to stop".into(),
                        kind: AlertKind::Error,
                    });
                    if in_screenshot_mode {
                        app.screenshot_target = Some(ScreenshotTarget::Main);
                    }
                }
                "diagnostics_modal" => {
                    app.root_modal = Some(RootModalState::Diagnostics);
                    if in_screenshot_mode {
                        app.screenshot_target = Some(ScreenshotTarget::Main);
                    }
                }
                other => {
                    if let Some(path) = other.strip_prefix("report:") {
                        app.report_state.open_for(path.to_string());
                        if in_screenshot_mode {
                            app.screenshot_target = Some(ScreenshotTarget::Report);
                        }
                    } else if let Some(path) = other.strip_prefix("resume:") {
                        match app.core.resume_saved_session(path, false) {
                            Ok(res) => {
                                app.snapshot = res.state;
                                if in_screenshot_mode {
                                    app.screenshot_target = Some(ScreenshotTarget::Main);
                                } else {
                                    app.session_resumed_dialog = Some(res.session_name);
                                }
                            }
                            Err(err) => {
                                eprintln!("TRUEHOUR_INITIAL_VIEW resume error for {path}: {err}");
                            }
                        }
                    } else if let Some(name) = other.strip_prefix("resumed_dialog:") {
                        app.session_resumed_dialog = Some(name.to_string());
                        if in_screenshot_mode {
                            app.screenshot_target = Some(ScreenshotTarget::ResumedDialog);
                        }
                    } else if let Some(path) = other.strip_prefix("stop_modal:") {
                        match app.core.load_session_report_details(path) {
                            Ok(rep) => {
                                let session_name_edit = rep.session_name.clone();
                                app.root_modal = Some(RootModalState::StopSaveSummary {
                                    resp: crate::StopAndSaveResponse {
                                        report: rep,
                                        saved_path: path.to_string(),
                                        security: None,
                                        state: app.snapshot.clone(),
                                    },
                                    session_name_edit,
                                });
                            }
                            Err(err) => {
                                eprintln!(
                                    "TRUEHOUR_INITIAL_VIEW stop_modal error for {path}: {err}"
                                );
                            }
                        }
                        if in_screenshot_mode {
                            app.screenshot_target = Some(ScreenshotTarget::Main);
                        }
                    } else if let Some(msg) = other.strip_prefix("toast:") {
                        app.toast = Some(ToastBanner {
                            text: msg.to_string(),
                            expires_at: Instant::now() + std::time::Duration::from_secs(30),
                        });
                        if in_screenshot_mode {
                            app.screenshot_target = Some(ScreenshotTarget::Main);
                        }
                    } else if in_screenshot_mode {
                        app.screenshot_target = Some(ScreenshotTarget::Main);
                    }
                }
            }
        } else if in_screenshot_mode {
            app.screenshot_target = Some(ScreenshotTarget::Main);
        }

        app
    }

    fn apply_theme_if_needed(&mut self, ctx: &egui::Context, next_style: &str) {
        if self.current_theme_style != next_style {
            self.current_theme_style = next_style.to_string();
            self.palette = theme::apply_theme(ctx, next_style);
            ctx.send_viewport_cmd(ViewportCommand::SetTheme(self.palette.kind.system_theme()));
        }
    }

    fn sync_window_title(&mut self, ctx: &egui::Context) {
        let name = self.snapshot.session_name.trim();
        let desired = if self.snapshot.running && !name.is_empty() {
            format!("TrueHour | {name}")
        } else {
            "TrueHour".to_string()
        };
        if desired != self.last_title {
            self.last_title = desired.clone();
            ctx.send_viewport_cmd(ViewportCommand::Title(desired));
        }
    }

    fn show_and_focus_main(&mut self, ctx: &egui::Context) {
        self.main_visible = true;
        ctx.send_viewport_cmd(ViewportCommand::Visible(true));
        ctx.send_viewport_cmd(ViewportCommand::Minimized(false));
        ctx.send_viewport_cmd(ViewportCommand::Focus);
        ctx.request_repaint();
    }

    fn perform_exit_cleanup(&mut self, ctx: &egui::Context) {
        if !self.cleaned_up {
            self.cleaned_up = true;
            self.core.tracker.autosave_on_exit();
            self.tray.shutdown();
            self.core.release_lock();
        }
        self.allow_exit = true;
        ctx.send_viewport_cmd(ViewportCommand::Close);
    }

    fn dispatch_cmds(&mut self, ctx: &egui::Context, cmds: Vec<GuiCmd>) {
        for cmd in cmds {
            match cmd {
                GuiCmd::OpenSessions => {
                    self.sessions_state.open = true;
                    self.sessions_state.mark_dirty();
                }
                GuiCmd::OpenSettings(tab_opt) => {
                    self.settings_state.open = true;
                    self.settings_state.mark_needs_reload();
                    if let Some(tab) = tab_opt {
                        self.settings_state.tab = tab;
                    }
                }
                GuiCmd::OpenCategories => {
                    self.categories_state.open = true;
                    self.categories_state.mark_dirty();
                }
                GuiCmd::OpenDashboard(tab_opt) => {
                    self.dashboard_state.open = true;
                    self.dashboard_state.mark_dirty();
                    if let Some(tab) = tab_opt {
                        self.dashboard_state.tab = tab;
                    }
                }
                GuiCmd::OpenReport(path) => {
                    self.report_state.open_for(path);
                }
                GuiCmd::OpenAbout => {
                    self.about_state.open = true;
                }
                GuiCmd::OpenDebug => {
                    self.debug_state.open = true;
                }
                GuiCmd::ShowResumedDialog(name) => {
                    self.session_resumed_pos = None;
                    self.session_resumed_dialog = Some(name);
                }
                GuiCmd::ShowAlert {
                    title,
                    message,
                    kind,
                } => {
                    self.root_modal = Some(RootModalState::Alert {
                        title,
                        message,
                        kind,
                    });
                }
                GuiCmd::ShowToast(text) => {
                    self.toast = Some(ToastBanner {
                        text,
                        expires_at: Instant::now() + std::time::Duration::from_millis(2800),
                    });
                }
                GuiCmd::FocusMain => {
                    self.show_and_focus_main(ctx);
                }
                GuiCmd::SetTheme(style) => {
                    self.apply_theme_if_needed(ctx, &style);
                }
                GuiCmd::RequestExit => {
                    self.perform_exit_cleanup(ctx);
                }
            }
        }
    }
}

impl eframe::App for TrueHourGuiApp {
    fn logic(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        // 1. Handle tray menu / double-click / single-instance restore events even while hidden
        let tray_events: Vec<TrayAction> = self.tray_rx.try_iter().collect();
        for ev in tray_events {
            match ev {
                TrayAction::OpenMain => self.show_and_focus_main(ctx),
                TrayAction::TogglePause => {
                    let next = self.core.toggle_pause();
                    self.snapshot = next;
                }
                TrayAction::Exit => {
                    if self.core.tracker.should_confirm_on_exit() {
                        self.show_and_focus_main(ctx);
                        self.root_modal = Some(RootModalState::Confirm {
                            title: "Exit TrueHour?".into(),
                            message: "Tracking is currently active.\n\nAutosave the current session and exit TrueHour?".into(),
                            confirm_label: "Exit & Autosave".into(),
                            danger: false,
                            purpose: modals::ConfirmPurpose::ExitWhileTracking,
                        });
                    } else {
                        self.perform_exit_cleanup(ctx);
                        return;
                    }
                }
            }
        }

        // 2. Drain background file dialogs & backup/import tasks
        let async_results: Vec<AsyncTaskResult> = self.task_rx.try_iter().collect();
        let mut bg_cmds = Vec::new();
        for res in async_results {
            match &res {
                AsyncTaskResult::ExportReportSaved(_) => {
                    self.report_state.handle_async_result(res, &mut bg_cmds);
                }
                _ => {
                    self.settings_state.handle_async_result(res);
                }
            }
        }
        if !bg_cmds.is_empty() {
            self.dispatch_cmds(ctx, bg_cmds);
        }

        // 3. Sync snapshot & tray pause/resume state
        let t_rev = self.core.tracker_rev.load(Ordering::SeqCst);
        let s_rev = self.core.settings_rev.load(Ordering::SeqCst);
        if t_rev != self.last_tracker_rev || s_rev != self.last_settings_rev {
            self.last_tracker_rev = t_rev;
            self.last_settings_rev = s_rev;
            self.snapshot = self.core.ui_snapshot();
            let next_theme = self.snapshot.theme_style.clone();
            self.apply_theme_if_needed(ctx, &next_theme);
        }
        self.tray
            .set_tracking_state(self.snapshot.running, self.snapshot.paused);
        self.sync_window_title(ctx);

        // 4. Intercept main window close button -> hide to system tray (unless Tray -> Exit)
        if !self.allow_exit && ctx.input(|i| i.viewport().close_requested()) {
            if self.tray.is_alive() {
                ctx.send_viewport_cmd(ViewportCommand::CancelClose);
                ctx.send_viewport_cmd(ViewportCommand::Visible(false));
                self.main_visible = false;
            } else {
                self.perform_exit_cleanup(ctx);
            }
        }
    }

    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        let ctx = ui.ctx().clone();
        let mut cmds = Vec::new();

        if let Some(target) = self.screenshot_target {
            match target {
                ScreenshotTarget::Main => {
                    egui::CentralPanel::default()
                        .frame(
                            Frame::NONE
                                .fill(self.palette.bg_window)
                                .inner_margin(Margin::symmetric(12, 10)),
                        )
                        .show(ui, |ui| {
                            main_window::render_main_window(
                                ui,
                                &self.core,
                                &self.palette,
                                &self.snapshot,
                                &mut self.tex_cache,
                                &mut self.main_state,
                                &mut self.root_modal,
                                &mut cmds,
                            );
                        });
                    if let Some(ref toast) = self.toast {
                        if Instant::now() < toast.expires_at {
                            widgets::render_toast_overlay(&ctx, &self.palette, &toast.text);
                        }
                    }
                    modals::render_root_modal(
                        &ctx,
                        &self.core,
                        &self.palette,
                        &mut self.root_modal,
                        &mut cmds,
                    );
                }
                ScreenshotTarget::ResumedDialog => {
                    modals::render_session_resumed_in_root(
                        ui,
                        &self.palette,
                        &self.session_resumed_dialog,
                    );
                }
                ScreenshotTarget::Sessions => {
                    sessions_window::render_sessions_in_root(
                        ui,
                        &self.core,
                        &self.palette,
                        &mut self.sessions_state,
                        &mut cmds,
                    );
                }
                ScreenshotTarget::Settings => {
                    settings_window::render_settings_in_root(
                        ui,
                        &self.core,
                        &self.palette,
                        &mut self.tex_cache,
                        &self.task_tx,
                        &mut self.settings_state,
                        &mut cmds,
                    );
                }
                ScreenshotTarget::Report => {
                    report_window::render_report_in_root(
                        ui,
                        &self.core,
                        &self.palette,
                        &mut self.tex_cache,
                        &self.task_tx,
                        &mut self.report_state,
                        &mut cmds,
                    );
                }
                ScreenshotTarget::Categories => {
                    categories_window::render_categories_in_root(
                        ui,
                        &self.core,
                        &self.palette,
                        &mut self.tex_cache,
                        &mut self.categories_state,
                        &mut cmds,
                    );
                }
                ScreenshotTarget::Dashboard => {
                    dashboard_window::render_dashboard_in_root(
                        ui,
                        &self.core,
                        &self.palette,
                        &mut self.dashboard_state,
                        &mut cmds,
                    );
                }
                ScreenshotTarget::About => {
                    about_window::render_about_in_root(
                        ui,
                        &self.core,
                        &self.palette,
                        &mut self.about_state,
                        &mut cmds,
                    );
                }
                ScreenshotTarget::Debug => {
                    debug_window::render_debug_in_root(
                        ui,
                        &self.core,
                        &self.palette,
                        &mut self.debug_state,
                    );
                }
            }
        } else {
            egui::CentralPanel::default()
                .frame(
                    Frame::NONE
                        .fill(self.palette.bg_window)
                        .inner_margin(Margin::symmetric(12, 10)),
                )
                .show(ui, |ui| {
                    main_window::render_main_window(
                        ui,
                        &self.core,
                        &self.palette,
                        &self.snapshot,
                        &mut self.tex_cache,
                        &mut self.main_state,
                        &mut self.root_modal,
                        &mut cmds,
                    );
                });

            // Toast overlay if active
            if let Some(ref toast) = self.toast {
                if Instant::now() < toast.expires_at {
                    ctx.request_repaint_after(std::time::Duration::from_millis(200));
                    widgets::render_toast_overlay(&ctx, &self.palette, &toast.text);
                } else {
                    self.toast = None;
                }
            }

            // Root modal
            modals::render_root_modal(
                &ctx,
                &self.core,
                &self.palette,
                &mut self.root_modal,
                &mut cmds,
            );

            // Secondary viewports (all pure native OS windows, zero WebView2!)
            modals::show_session_resumed_viewport(
                &ctx,
                &self.palette,
                &self.icon_data,
                &mut self.session_resumed_dialog,
                &mut self.session_resumed_pos,
            );
            sessions_window::show_sessions_viewport(
                &ctx,
                &self.core,
                &self.palette,
                &self.icon_data,
                &mut self.sessions_state,
                &mut cmds,
            );
            settings_window::show_settings_viewport(
                &ctx,
                &self.core,
                &self.palette,
                &self.icon_data,
                &mut self.tex_cache,
                &self.task_tx,
                &mut self.settings_state,
                &mut cmds,
            );
            report_window::show_report_viewport(
                &ctx,
                &self.core,
                &self.palette,
                &self.icon_data,
                &mut self.tex_cache,
                &self.task_tx,
                &mut self.report_state,
                &mut cmds,
            );
            categories_window::show_categories_viewport(
                &ctx,
                &self.core,
                &self.palette,
                &self.icon_data,
                &mut self.tex_cache,
                &mut self.categories_state,
                &mut cmds,
            );
            dashboard_window::show_dashboard_viewport(
                &ctx,
                &self.core,
                &self.palette,
                &self.icon_data,
                &mut self.dashboard_state,
                &mut cmds,
            );
            about_window::show_about_viewport(
                &ctx,
                &self.core,
                &self.palette,
                &self.icon_data,
                &mut self.about_state,
                &mut cmds,
            );
            debug_window::show_debug_viewport(
                &ctx,
                &self.core,
                &self.palette,
                &self.icon_data,
                &mut self.debug_state,
            );
        }

        if !cmds.is_empty() {
            self.dispatch_cmds(&ctx, cmds);
        }

        if let Some(prefix) = self.screenshot_prefix.clone() {
            self.screenshot_frames = self.screenshot_frames.saturating_add(1);
            ctx.request_repaint();
            ctx.request_repaint_after(std::time::Duration::from_millis(25));

            if self.screenshot_frames == 8 {
                let pending = Arc::new(AtomicUsize::new(1));
                self.screenshot_pending = Some(Arc::clone(&pending));
                let out_path = format!("{prefix}.png");
                let pending_cb = Arc::clone(&pending);
                let ctx_cb = ctx.clone();
                ctx.send_viewport_cmd(ViewportCommand::Screenshot(egui::ScreenshotCallback::new(
                    move |img| {
                        if let Err(err) = image::save_buffer(
                            &out_path,
                            img.as_raw(),
                            img.width() as u32,
                            img.height() as u32,
                            image::ColorType::Rgba8,
                        ) {
                            eprintln!("Failed saving screenshot {out_path}: {err}");
                        }
                        pending_cb.fetch_sub(1, Ordering::SeqCst);
                        ctx_cb.request_repaint();
                    },
                )));
            } else if self.screenshot_frames > 8 {
                let done = self
                    .screenshot_pending
                    .as_ref()
                    .is_some_and(|p| p.load(Ordering::SeqCst) == 0);
                if done || self.screenshot_frames > 45 {
                    self.perform_exit_cleanup(&ctx);
                }
            }
        }
    }

    fn on_exit(&mut self, _gl: Option<&eframe::glow::Context>) {
        if !self.cleaned_up {
            self.cleaned_up = true;
            self.core.tracker.autosave_on_exit();
            self.tray.shutdown();
            self.core.release_lock();
        }
    }
}
