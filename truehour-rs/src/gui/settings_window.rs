use super::icons;
use super::modals::AlertKind;
use super::theme::{font_bold, font_regular, font_semibold, ThemePalette};
use super::widgets::{self, PillVariant};
use super::{AsyncTaskResult, GuiCmd, TextureCache};
use crate::backup::ImportBackupResult;
use crate::config::ProfilesConfig;
use crate::file_dialog;
use crate::settings::{FullSettingsDto, QrCodeItemDto};
use crate::AppCore;
use egui::{
    pos2, vec2, Align, Color32, ComboBox, CornerRadius, CursorIcon, Frame, Id, Layout, Margin,
    Modal, Panel, Pos2, ScrollArea, Sense, Stroke, StrokeKind, Vec2, ViewportBuilder,
    ViewportCommand, ViewportId,
};
use std::collections::{BTreeSet, HashMap, HashSet};
use std::path::PathBuf;
use std::sync::atomic::Ordering;
use std::sync::mpsc::Sender;
use std::sync::Arc;

const CURRENCIES: &[&str] = &[
    "$ (USD)",
    "€ (EUR)",
    "£ (GBP)",
    "¥ (JPY/CNY)",
    "₱ (PHP)",
    "₹ (INR)",
    "₽ (RUB)",
    "₩ (KRW)",
    "₫ (VND)",
    "฿ (THB)",
    "₪ (ILS)",
    "₺ (TRY)",
    "Rp (IDR)",
    "RM (MYR)",
    "R$ (BRL)",
    "C$ (CAD)",
    "A$ (AUD)",
    "S$ (SGD)",
    "NZ$ (NZD)",
    "CHF (CHF)",
    "kr (SEK/NOK)",
    "zł (PLN)",
    "Kč (CZK)",
    "Ft (HUF)",
    "lei (RON)",
    "лв (BGN)",
    "₴ (UAH)",
    "R (ZAR)",
];

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum SettingsTab {
    General,
    Billing,
}

enum SettingsModal {
    Alert {
        title: String,
        message: String,
        kind: AlertKind,
    },
    PromptProfile {
        title: String,
        label: String,
        value: String,
        placeholder: String,
        confirm_label: String,
        is_rename_from: Option<String>,
    },
    ConfirmDeleteProfile(String),
    DistractionManager {
        search: String,
        custom_input: String,
        all_apps: BTreeSet<String>,
        working: HashSet<String>,
    },
    QrLinkEditor {
        filename: String,
        url: String,
    },
    LocalBackup {
        scope_profile: bool,
        encrypted: bool,
        pw1: String,
        pw2: String,
        busy: bool,
    },
    EncryptedRestore {
        archive_path: String,
        message: String,
        password: String,
        busy: bool,
    },
}

pub struct SettingsWindowState {
    pub open: bool,
    pub tab: SettingsTab,
    pub scroll_to_bottom_frames: u8,
    loaded: bool,
    last_settings_rev: u64,
    profiles: ProfilesConfig,
    original_theme: String,
    dto: Option<FullSettingsDto>,

    // String buffers for numeric & chip inputs
    min_track_buf: String,
    auto_save_buf: String,
    idle_min_buf: String,
    idle_sec_buf: String,
    hourly_rate_buf: String,
    biz_email_draft: String,
    client_email_draft: String,

    pending_qr_deletes: HashSet<String>,
    newly_added_qr_files: HashSet<String>,
    qr_links: HashMap<String, String>,
    qr_items: Vec<QrCodeItemDto>,
    distraction_apps: Vec<String>,
    data_root: String,

    modal: Option<SettingsModal>,
    spawn_pos: Option<Pos2>,
    spawn_size: Option<Vec2>,
}

impl Default for SettingsWindowState {
    fn default() -> Self {
        Self {
            open: false,
            tab: SettingsTab::General,
            scroll_to_bottom_frames: 0,
            loaded: false,
            last_settings_rev: 0,
            profiles: ProfilesConfig::default(),
            original_theme: "modern-dark".into(),
            dto: None,
            min_track_buf: "2".into(),
            auto_save_buf: "10".into(),
            idle_min_buf: "2".into(),
            idle_sec_buf: "0".into(),
            hourly_rate_buf: "0.00".into(),
            biz_email_draft: String::new(),
            client_email_draft: String::new(),
            pending_qr_deletes: HashSet::new(),
            newly_added_qr_files: HashSet::new(),
            qr_links: HashMap::new(),
            qr_items: Vec::new(),
            distraction_apps: Vec::new(),
            data_root: String::new(),
            modal: None,
            spawn_pos: None,
            spawn_size: None,
        }
    }
}

impl SettingsWindowState {
    pub fn mark_needs_reload(&mut self) {
        self.loaded = false;
    }

    pub fn load_from_core(&mut self, core: &Arc<AppCore>) {
        let p = core.get_full_settings();
        let s = p.settings;
        self.profiles = p.profiles;
        self.data_root = p.data_root;
        self.original_theme = s.theme_style.clone();
        self.min_track_buf = s.min_track_seconds.to_string();
        self.auto_save_buf = s.auto_save_seconds.to_string();
        let total_idle = s.idle_threshold_seconds_total;
        self.idle_min_buf = (total_idle / 60).to_string();
        self.idle_sec_buf = (total_idle % 60).to_string();
        self.hourly_rate_buf = format!("{:.2}", s.hourly_rate);
        self.biz_email_draft.clear();
        self.client_email_draft.clear();
        self.distraction_apps = s.distraction_apps.clone();
        self.qr_items = s.qr_code_items.clone();
        self.qr_links = s.qr_code_links.clone();
        self.pending_qr_deletes.clear();
        self.newly_added_qr_files.clear();
        self.dto = Some(s);
        self.loaded = true;
        self.last_settings_rev = core.settings_rev.load(Ordering::SeqCst);
    }

    pub fn handle_async_result(&mut self, res: AsyncTaskResult) {
        match res {
            AsyncTaskResult::LogoPicked(Some(path)) => {
                if let Some(ref mut d) = self.dto {
                    d.business_logo_path = path.to_string_lossy().to_string();
                }
            }
            AsyncTaskResult::LogoPicked(None) => {}
            AsyncTaskResult::QrPicked(Ok(Some(item))) => {
                self.newly_added_qr_files.insert(item.filename.clone());
                self.pending_qr_deletes.remove(&item.filename);
                if !item.link.is_empty() {
                    self.qr_links
                        .insert(item.filename.clone(), item.link.clone());
                }
                self.qr_items.push(item);
            }
            AsyncTaskResult::QrPicked(Ok(None)) => {}
            AsyncTaskResult::QrPicked(Err(err)) => {
                self.modal = Some(SettingsModal::Alert {
                    title: "QR Code Error".into(),
                    message: err,
                    kind: AlertKind::Error,
                });
            }
            AsyncTaskResult::LocalBackupDone { scope, result } => {
                self.modal = match result {
                    Ok(Some(path)) => Some(SettingsModal::Alert {
                        title: "Backup Saved".into(),
                        message: format!("{scope} archive saved to:\n{path}"),
                        kind: AlertKind::Info,
                    }),
                    Ok(None) => None,
                    Err(err) => Some(SettingsModal::Alert {
                        title: "Backup Failed".into(),
                        message: err,
                        kind: AlertKind::Error,
                    }),
                };
            }
            AsyncTaskResult::LocalImportDone {
                archive_path,
                result,
            } => {
                self.apply_import_result(&archive_path, result);
            }
            _ => {}
        }
    }

    fn apply_import_result(&mut self, archive_path: &str, res: ImportBackupResult) {
        if res.status == "success" || res.status == "banking_stripped" {
            self.loaded = false;
            self.modal = Some(SettingsModal::Alert {
                title: "Restore Complete".into(),
                message: res.message,
                kind: AlertKind::Info,
            });
        } else if res.status == "password_required" || res.status == "wrong_password" {
            self.modal = Some(SettingsModal::EncryptedRestore {
                archive_path: archive_path.to_string(),
                message: res.message,
                password: String::new(),
                busy: false,
            });
        } else {
            self.modal = Some(SettingsModal::Alert {
                title: "Restore Notice".into(),
                message: res.message,
                kind: AlertKind::Warn,
            });
        }
    }
}

#[allow(clippy::too_many_arguments)]
pub fn show_settings_viewport(
    ctx: &egui::Context,
    core: &Arc<AppCore>,
    palette: &ThemePalette,
    icon_data: &Option<Arc<egui::IconData>>,
    tex_cache: &mut TextureCache,
    task_tx: &Sender<AsyncTaskResult>,
    state: &mut SettingsWindowState,
    cmds: &mut Vec<GuiCmd>,
) {
    if !state.open {
        state.spawn_pos = None;
        state.spawn_size = None;
        return;
    }

    ensure_settings_loaded(core, state);

    if state.spawn_size.is_none() {
        let (pos, sz) = widgets::centered_viewport_pos_and_size(ctx, vec2(620.0, 700.0));
        state.spawn_pos = pos;
        state.spawn_size = Some(sz);
    }
    let size = state.spawn_size.unwrap_or(vec2(620.0, 700.0));

    let vp_id = ViewportId::from_hash_of("settings_window");
    let mut builder = ViewportBuilder::default()
        .with_title("Settings")
        .with_inner_size(size)
        .with_min_inner_size([580.0, 580.0])
        .with_resizable(true);
    if let Some(pos) = state.spawn_pos {
        builder = builder.with_position(pos);
    }
    if let Some(ref ic) = icon_data {
        builder = builder.with_icon(Arc::clone(ic));
    }

    let mut close_req = false;
    let mut cancel_cleanup = false;

    ctx.show_viewport_immediate(vp_id, builder, |ui, _class| {
        if ui.ctx().input(|i| i.viewport().close_requested()) {
            close_req = true;
            cancel_cleanup = true;
        }
        let (cr, cc) = render_settings_contents(ui, core, palette, tex_cache, task_tx, state, cmds);
        if cr {
            close_req = true;
            cancel_cleanup = cc;
        }
        if close_req {
            ui.ctx().send_viewport_cmd(ViewportCommand::Close);
        }
    });

    if close_req {
        if cancel_cleanup {
            if let Some(ref d) = state.dto {
                if d.theme_style != state.original_theme {
                    let orig = state.original_theme.clone();
                    let _ = core.set_theme_style(&orig);
                    cmds.push(GuiCmd::SetTheme(orig));
                }
            }
            for fn_name in state.newly_added_qr_files.drain() {
                core.delete_qr_code_file(&fn_name);
            }
        }
        state.loaded = false;
        state.modal = None;
        state.open = false;
        state.spawn_pos = None;
        state.spawn_size = None;
    }
}

pub(crate) fn render_settings_in_root(
    ui: &mut egui::Ui,
    core: &Arc<AppCore>,
    palette: &ThemePalette,
    tex_cache: &mut TextureCache,
    task_tx: &Sender<AsyncTaskResult>,
    state: &mut SettingsWindowState,
    cmds: &mut Vec<GuiCmd>,
) {
    ensure_settings_loaded(core, state);
    let _ = render_settings_contents(ui, core, palette, tex_cache, task_tx, state, cmds);
}

fn ensure_settings_loaded(core: &Arc<AppCore>, state: &mut SettingsWindowState) {
    let s_rev = core.settings_rev.load(Ordering::SeqCst);
    if !state.loaded || state.dto.is_none() {
        state.load_from_core(core);
    } else if state.last_settings_rev != s_rev && state.modal.is_none() {
        state.last_settings_rev = s_rev;
    }
}

fn render_settings_contents(
    ui: &mut egui::Ui,
    core: &Arc<AppCore>,
    palette: &ThemePalette,
    tex_cache: &mut TextureCache,
    task_tx: &Sender<AsyncTaskResult>,
    state: &mut SettingsWindowState,
    cmds: &mut Vec<GuiCmd>,
) -> (bool, bool) {
    let mut close_req = false;
    let mut cancel_cleanup = false;

    // Fixed Bottom Footer
        Panel::bottom("settings_footer")
            .frame(
                Frame::NONE
                    .fill(palette.bg_window)
                    .inner_margin(Margin {
                        left: 16,
                        right: 16,
                        top: 8,
                        bottom: 12,
                    }),
            )
            .show(ui, |ui| {
                ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                    ui.spacing_mut().item_spacing.x = 8.0;
                    if widgets::pill_button(
                        ui,
                        palette,
                        PillVariant::Secondary,
                        "Cancel",
                        32.0,
                        82.0,
                        true,
                    )
                    .clicked()
                    {
                        close_req = true;
                        cancel_cleanup = true;
                    }
                    if widgets::pill_button(
                        ui,
                        palette,
                        PillVariant::Accent,
                        "Save Settings",
                        32.0,
                        120.0,
                        true,
                    )
                    .clicked()
                    {
                        if try_save_settings(core, state, cmds) {
                            close_req = true;
                            cancel_cleanup = false;
                        }
                    }
                });
            });

        egui::CentralPanel::default()
            .frame(
                Frame::NONE
                    .fill(palette.bg_window)
                    .inner_margin(Margin {
                        left: 16,
                        right: 16,
                        top: 12,
                        bottom: 0,
                    }),
            )
            .show(ui, |ui| {
                ui.spacing_mut().item_spacing.y = 0.0;

                ui.label(
                    egui::RichText::new("Settings")
                        .font(font_bold(17.0))
                        .color(palette.text_primary),
                );
                ui.add_space(10.0);

                let tabs = [
                    (SettingsTab::General, "General & Controls"),
                    (SettingsTab::Billing, "Billing & Invoices"),
                ];
                let active_tab_rect =
                    widgets::folder_tab_bar(ui, palette, &tabs, &mut state.tab, 128.0);

                let pane_h = ui.available_height().max(160.0);
                let pane_resp = Frame::NONE
                    .fill(palette.bg_card)
                    .stroke(Stroke::new(1.0, palette.border))
                    .corner_radius(CornerRadius {
                        nw: 0,
                        ne: 8,
                        sw: 8,
                        se: 8,
                    })
                    .inner_margin(Margin::symmetric(14, 12))
                    .show(ui, |ui| {
                        ui.set_width(ui.available_width());
                        ui.set_height(pane_h - 4.0);

                        let mut sa = ScrollArea::vertical()
                            .id_salt(("settings_scroll", state.tab))
                            .auto_shrink([false, false]);
                        if state.scroll_to_bottom_frames > 0 {
                            state.scroll_to_bottom_frames -= 1;
                            sa = sa.stick_to_bottom(true);
                        }
                        sa.show(ui, |ui| {
                            ui.spacing_mut().item_spacing.y = 6.0;
                            match state.tab {
                                SettingsTab::General => {
                                    render_general_tab(ui, core, palette, state, task_tx, cmds);
                                }
                                SettingsTab::Billing => {
                                    render_billing_tab(
                                        ui,
                                        core,
                                        palette,
                                        tex_cache,
                                        state,
                                        task_tx,
                                    );
                                }
                            }
                            ui.add_space(6.0);
                        });
                    });
                widgets::seamless_tab_join(ui, palette, active_tab_rect, pane_resp.response.rect);
            });

    render_settings_modals(ui.ctx(), core, palette, state, task_tx, cmds);

    (close_req, cancel_cleanup)
}

fn render_general_tab(
    ui: &mut egui::Ui,
    core: &Arc<AppCore>,
    palette: &ThemePalette,
    state: &mut SettingsWindowState,
    task_tx: &Sender<AsyncTaskResult>,
    cmds: &mut Vec<GuiCmd>,
) {
    // 1. Profile Selection GroupBox
    widgets::group_box(ui, palette, "Profile Selection", |ui| {
        let avail_w = ui.available_width();
        ui.allocate_ui_with_layout(
            vec2(avail_w, 28.0),
            Layout::left_to_right(Align::Center),
            |ui| {
                ui.spacing_mut().item_spacing.x = 8.0;
                let mut selected_prof = state.profiles.active_profile.clone();
                let btns_w = 88.0 + 74.0 + 70.0 + 24.0;
            let combo_w = (avail_w - btns_w).max(120.0);

            ComboBox::from_id_salt("settings_profile_combo")
                .width(combo_w)
                .selected_text(&selected_prof)
                .show_ui(ui, |ui| {
                    for prof in &state.profiles.profiles {
                        ui.selectable_value(&mut selected_prof, prof.clone(), prof);
                    }
                });
            if selected_prof != state.profiles.active_profile {
                match core.switch_profile(&selected_prof) {
                    Ok(_) => {
                        state.load_from_core(core);
                        if let Some(ref d) = state.dto {
                            cmds.push(GuiCmd::SetTheme(d.theme_style.clone()));
                        }
                    }
                    Err(err) => {
                        state.modal = Some(SettingsModal::Alert {
                            title: "Switch Profile Error".into(),
                            message: err,
                            kind: AlertKind::Error,
                        });
                    }
                }
            }

            if widgets::pill_button(
                ui,
                palette,
                PillVariant::Secondary,
                "New Profile",
                28.0,
                86.0,
                true,
            )
            .clicked()
            {
                state.modal = Some(SettingsModal::PromptProfile {
                    title: "New Profile".into(),
                    label: "Enter a name for the new profile:".into(),
                    value: String::new(),
                    placeholder: "e.g. Client Work".into(),
                    confirm_label: "Create".into(),
                    is_rename_from: None,
                });
            }

            let cur = state.profiles.active_profile.clone();
            if widgets::pill_button(
                ui,
                palette,
                PillVariant::Secondary,
                "Rename",
                28.0,
                72.0,
                true,
            )
            .clicked()
            {
                state.modal = Some(SettingsModal::PromptProfile {
                    title: "Rename Profile".into(),
                    label: format!("Rename profile \"{cur}\" to:"),
                    value: cur.clone(),
                    placeholder: "Profile name".into(),
                    confirm_label: "Rename".into(),
                    is_rename_from: Some(cur.clone()),
                });
            }

            let can_del = state.profiles.profiles.len() > 1 && cur != "Default";
            if widgets::pill_button(
                ui,
                palette,
                PillVariant::Secondary,
                "Delete",
                28.0,
                68.0,
                can_del,
            )
            .clicked()
            {
                state.modal = Some(SettingsModal::ConfirmDeleteProfile(cur));
            }
        });
    });

    ui.add_space(4.0);

    // 2. Direct flat checkboxes & numeric fields
    if let Some(ref mut dto) = state.dto {
        ui.vertical(|ui| {
            ui.spacing_mut().item_spacing.y = 8.0;

            widgets::th_checkbox_label(
                ui,
                palette,
                &mut dto.confirm_on_close,
                "Always ask for confirmation before closing",
            );
            widgets::th_checkbox_label(
                ui,
                palette,
                &mut dto.developer_mode,
                "Enable Developer Options (Debug Console)",
            );

            ui.horizontal(|ui| {
                widgets::form_label_col(ui, palette, 188.0, 26.0, "Theme Style:", false);
                let mut cur_theme = dto.theme_style.clone();
                let theme_label = match cur_theme.as_str() {
                    "classic-dark" => "Classic Dark",
                    "light" => "Light",
                    _ => "Modern Dark",
                };
                ComboBox::from_id_salt("settings_theme_combo")
                    .width(120.0)
                    .selected_text(theme_label)
                    .show_ui(ui, |ui| {
                        ui.selectable_value(&mut cur_theme, "modern-dark".into(), "Modern Dark");
                        ui.selectable_value(&mut cur_theme, "classic-dark".into(), "Classic Dark");
                        ui.selectable_value(&mut cur_theme, "light".into(), "Light");
                    });
                if cur_theme != dto.theme_style {
                    dto.theme_style = cur_theme.clone();
                    dto.dark_mode = cur_theme != "light";
                    let _ = core.set_theme_style(&cur_theme);
                    cmds.push(GuiCmd::SetTheme(cur_theme));
                }
            });

            general_num_row(
                ui,
                palette,
                "Min activity threshold (secs):",
                &mut state.min_track_buf,
            );
            general_num_row(
                ui,
                palette,
                "Auto-save interval (secs):",
                &mut state.auto_save_buf,
            );

            ui.horizontal(|ui| {
                widgets::form_label_col(ui, palette, 188.0, 26.0, "Idle auto-pause:", false);
                ui.spacing_mut().item_spacing.x = 6.0;
                widgets::text_input_line(ui, palette, &mut state.idle_min_buf, "0", 48.0, true);
                ui.label(
                    egui::RichText::new("min")
                        .font(font_regular(12.0))
                        .color(palette.text_secondary),
                );
                widgets::text_input_line(ui, palette, &mut state.idle_sec_buf, "0", 48.0, true);
                ui.label(
                    egui::RichText::new("sec")
                        .font(font_regular(12.0))
                        .color(palette.text_secondary),
                );
            });

            ui.horizontal(|ui| {
                widgets::form_label_col(ui, palette, 188.0, 26.0, "Currency symbol:", false);
                let mut cur_c = if dto.currency_symbol_raw.trim().is_empty() {
                    "$ (USD)".to_string()
                } else {
                    dto.currency_symbol_raw.clone()
                };
                ComboBox::from_id_salt("settings_curr_combo")
                    .width(175.0)
                    .selected_text(&cur_c)
                    .show_ui(ui, |ui| {
                        for c in CURRENCIES {
                            ui.selectable_value(&mut cur_c, (*c).to_string(), *c);
                        }
                    });
                dto.currency_symbol_raw = cur_c;
            });

            general_num_row(ui, palette, "Hourly rate:", &mut state.hourly_rate_buf);
        });
    }

    ui.add_space(4.0);

    // 3. Distraction Auto-Pause GroupBox
    let mut enable_dist = state
        .dto
        .as_ref()
        .map(|d| d.enable_distraction_auto_pause)
        .unwrap_or(false);
    widgets::group_box(ui, palette, "Distraction Auto-Pause", |ui| {
        ui.spacing_mut().item_spacing.y = 8.0;
        widgets::th_checkbox_label(
            ui,
            palette,
            &mut enable_dist,
            "Automatically pause tracking on distracting apps",
        );
        let full_w = ui.available_width();
        if widgets::pill_button(
            ui,
            palette,
            PillVariant::Secondary,
            "Manage Distraction Apps...",
            30.0,
            full_w,
            enable_dist,
        )
        .clicked()
        {
            let snap = core.ui_snapshot();
            let mut all_apps = BTreeSet::new();
            for a in snap.apps {
                all_apps.insert(a.name);
            }
            for d in &state.distraction_apps {
                all_apps.insert(d.clone());
            }
            let working: HashSet<String> = state.distraction_apps.iter().cloned().collect();
            state.modal = Some(SettingsModal::DistractionManager {
                search: String::new(),
                custom_input: String::new(),
                all_apps,
                working,
            });
        }
    });
    if let Some(ref mut d) = state.dto {
        d.enable_distraction_auto_pause = enable_dist;
    }

    // 4. Configuration & Categories GroupBox
    widgets::group_box(ui, palette, "Configuration & Categories", |ui| {
        ui.spacing_mut().item_spacing.y = 7.0;
        let full_w = ui.available_width();
        if widgets::pill_button(
            ui,
            palette,
            PillVariant::Secondary,
            "Edit Name Overrides",
            30.0,
            full_w,
            true,
        )
        .clicked()
        {
            if let Err(err) = core.edit_config_txt_file("name_overrides") {
                cmds.push(GuiCmd::ShowToast(err));
            }
        }

        ui.horizontal(|ui| {
            ui.spacing_mut().item_spacing.x = 8.0;
            let reload_w = 96.0;
            let edit_w = (ui.available_width() - reload_w - 8.0).max(140.0);
            if widgets::pill_button(
                ui,
                palette,
                PillVariant::Secondary,
                "Edit Auto-Exclusions",
                30.0,
                edit_w,
                true,
            )
            .clicked()
            {
                if let Err(err) = core.edit_config_txt_file("auto_excluded") {
                    cmds.push(GuiCmd::ShowToast(err));
                }
            }
            if widgets::pill_button_with_icon(
                ui,
                palette,
                PillVariant::Secondary,
                "Reload",
                30.0,
                reload_w,
                true,
                Some(|p: &egui::Painter, r: egui::Rect, _fg: Color32| {
                    icons::paint_refresh(p, r, Color32::from_rgb(0x25, 0x63, 0xEB));
                }),
            )
            .clicked()
            {
                let _ = core.reload_exclusions_and_overrides();
                cmds.push(GuiCmd::ShowToast(
                    "Exclusions & name overrides reloaded".into(),
                ));
            }
        });

        if widgets::pill_button(
            ui,
            palette,
            PillVariant::Secondary,
            "Manage Project Categories...",
            30.0,
            full_w,
            true,
        )
        .clicked()
        {
            cmds.push(GuiCmd::OpenCategories);
        }

        if widgets::pill_button_with_icon(
            ui,
            palette,
            PillVariant::AmberOutline,
            "About TrueHour",
            31.0,
            full_w,
            true,
            Some(|p: &egui::Painter, r: egui::Rect, fg: Color32| {
                icons::paint_info_circle(p, r.center(), r.width() * 0.44, fg);
            }),
        )
        .clicked()
        {
            cmds.push(GuiCmd::OpenAbout);
        }
    });

    // 5. Backup & Restore GroupBox (Strictly Local-Only — ZERO Google Sign-In / Drive)
    widgets::group_box(ui, palette, "Backup & Restore", |ui| {
        let col_w = ((ui.available_width() - 16.0) / 3.0).max(90.0);
        ui.horizontal(|ui| {
            ui.spacing_mut().item_spacing.x = 8.0;
            if widgets::pill_button(
                ui,
                palette,
                PillVariant::Accent,
                "Backup Workspace...",
                30.0,
                col_w,
                true,
            )
            .clicked()
            {
                state.modal = Some(SettingsModal::LocalBackup {
                    scope_profile: false,
                    encrypted: false,
                    pw1: String::new(),
                    pw2: String::new(),
                    busy: false,
                });
            }
            if widgets::pill_button(
                ui,
                palette,
                PillVariant::Secondary,
                "Import / Restore...",
                30.0,
                col_w,
                true,
            )
            .clicked()
            {
                if core.tracker.is_running() {
                    state.modal = Some(SettingsModal::Alert {
                        title: "Stop Tracking First".into(),
                        message: "Stop active tracking before restoring a workspace backup."
                            .into(),
                        kind: AlertKind::Warn,
                    });
                } else {
                    let core_bg = Arc::clone(core);
                    let tx_bg = task_tx.clone();
                    let ctx_bg = ui.ctx().clone();
                    std::thread::spawn(move || {
                        let picked = file_dialog::pick_open_file(
                            "Select TrueHour Backup Archive",
                            &[
                                ("TrueHour Backups (*.truehour)", "*.truehour"),
                                ("ZIP Archives (*.zip)", "*.zip"),
                            ],
                            "truehour",
                        );
                        if let Some(src) = picked {
                            let paths = core_bg.tracker.paths();
                            let archive_path = src.to_string_lossy().to_string();
                            let result = crate::backup::import_backup(
                                &paths.app_data_root,
                                &src,
                                None,
                                false,
                                &paths.profile_name,
                            );
                            if result.status == "success" || result.status == "banking_stripped" {
                                reload_core_after_import(&core_bg, &result);
                            }
                            let _ = tx_bg.send(AsyncTaskResult::LocalImportDone {
                                archive_path,
                                result,
                            });
                            ctx_bg.request_repaint();
                        }
                    });
                }
            }
            if widgets::pill_button(
                ui,
                palette,
                PillVariant::Secondary,
                "Open Data Folder",
                30.0,
                col_w,
                true,
            )
            .clicked()
            {
                if let Err(err) = core.open_data_root_folder() {
                    cmds.push(GuiCmd::ShowToast(err));
                }
            }
        });
    });
}

fn general_num_row(
    ui: &mut egui::Ui,
    palette: &ThemePalette,
    label: &str,
    buf: &mut String,
) {
    ui.horizontal(|ui| {
        widgets::form_label_col(ui, palette, 188.0, 26.0, label, false);
        widgets::text_input_line(ui, palette, buf, "0", 88.0, true);
    });
}

fn billing_input_row(
    ui: &mut egui::Ui,
    palette: &ThemePalette,
    label: &str,
    buf: &mut String,
    placeholder: &str,
    enabled: bool,
) {
    ui.horizontal(|ui| {
        widgets::form_label_col(ui, palette, 122.0, 26.0, label, false);
        let w = ui.available_width().max(160.0);
        widgets::text_input_line(ui, palette, buf, placeholder, w, enabled);
    });
}

fn render_billing_tab(
    ui: &mut egui::Ui,
    core: &Arc<AppCore>,
    palette: &ThemePalette,
    tex_cache: &mut TextureCache,
    state: &mut SettingsWindowState,
    task_tx: &Sender<AsyncTaskResult>,
) {
    let Some(mut d) = state.dto.take() else {
        return;
    };

    // 1. Business Profile Details
    widgets::group_box(ui, palette, "Business Profile Details", |ui| {
        ui.spacing_mut().item_spacing.y = 7.0;
        billing_input_row(
            ui,
            palette,
            "Business Name:",
            &mut d.business_name,
            "Your Business or Freelancer Name",
            true,
        );
        ui.horizontal(|ui| {
            widgets::form_label_col(ui, palette, 122.0, 26.0, "Contact Emails:", true);
            let w = ui.available_width().max(160.0);
            widgets::email_chip_editor(
                ui,
                palette,
                &mut d.business_emails,
                &mut state.biz_email_draft,
                w,
            );
        });
        billing_input_row(
            ui,
            palette,
            "Contact Phone:",
            &mut d.business_phone,
            "+1 555-0199",
            true,
        );
        billing_input_row(
            ui,
            palette,
            "Billing Address:",
            &mut d.business_address,
            "Street, City, State, ZIP",
            true,
        );
        billing_input_row(
            ui,
            palette,
            "Payment Details:",
            &mut d.business_payment,
            "Optional (e.g., PayPal / Wise / Venmo)",
            true,
        );
    });

    // 2. Bank Transfer Details
    widgets::group_box(ui, palette, "Bank Transfer Details", |ui| {
        ui.spacing_mut().item_spacing.y = 7.0;
        widgets::th_checkbox_label(
            ui,
            palette,
            &mut d.enable_bank_details,
            "Enable Bank Transfer Details on Invoices",
        );
        let en = d.enable_bank_details;
        billing_input_row(ui, palette, "Account Holder:", &mut d.bank_holder, "", en);
        billing_input_row(ui, palette, "Account Number:", &mut d.bank_account, "", en);
        billing_input_row(ui, palette, "Routing Number:", &mut d.bank_routing, "", en);
        billing_input_row(ui, palette, "SWIFT / BIC:", &mut d.bank_swift, "", en);
        billing_input_row(ui, palette, "Bank Name:", &mut d.bank_name, "", en);
        billing_input_row(ui, palette, "Bank Address:", &mut d.bank_address, "", en);
    });

    // 3. Default Client Profile
    widgets::group_box(ui, palette, "Default Client Profile", |ui| {
        ui.spacing_mut().item_spacing.y = 7.0;
        billing_input_row(
            ui,
            palette,
            "Client Name:",
            &mut d.client_name,
            "Client / Company Name",
            true,
        );
        ui.horizontal(|ui| {
            widgets::form_label_col(ui, palette, 122.0, 26.0, "Client Emails:", true);
            let w = ui.available_width().max(160.0);
            widgets::email_chip_editor(
                ui,
                palette,
                &mut d.client_emails,
                &mut state.client_email_draft,
                w,
            );
        });
        billing_input_row(
            ui,
            palette,
            "Client Address:",
            &mut d.client_address,
            "",
            true,
        );
    });

    // 4. Invoice Business Logo
    widgets::group_box(ui, palette, "Invoice Business Logo", |ui| {
        ui.spacing_mut().item_spacing.y = 6.0;
        widgets::th_checkbox_label(
            ui,
            palette,
            &mut d.enable_business_logo,
            "Enable Business Logo on Invoices",
        );
        let en = d.enable_business_logo;
        ui.horizontal(|ui| {
            ui.spacing_mut().item_spacing.x = 8.0;
            let browse_w = 82.0;
            let inp_w = (ui.available_width() - browse_w - 8.0).max(120.0);
            widgets::text_input_line(
                ui,
                palette,
                &mut d.business_logo_path,
                "Select image (max 250x80px recommended)...",
                inp_w,
                en,
            );
            if widgets::pill_button(
                ui,
                palette,
                PillVariant::Secondary,
                "Browse...",
                28.0,
                browse_w,
                en,
            )
            .clicked()
            {
                let tx_bg = task_tx.clone();
                let ctx_bg = ui.ctx().clone();
                std::thread::spawn(move || {
                    let picked = file_dialog::pick_open_file(
                        "Select Business Logo",
                        &[("Image Files (*.png;*.jpg;*.jpeg)", "*.png;*.jpg;*.jpeg")],
                        "png",
                    );
                    let _ = tx_bg.send(AsyncTaskResult::LogoPicked(picked));
                    ctx_bg.request_repaint();
                });
            }
        });
        ui.label(
            egui::RichText::new(
                "Image Spec: PNG, JPG, or JPEG. Max size: 250px (w) x 80px (h). Proportionally resized automatically.",
            )
            .font(font_regular(11.0))
            .color(palette.text_muted),
        );
    });

    // 5. Payment QR Codes
    widgets::group_box(ui, palette, "Payment QR Codes", |ui| {
        ui.spacing_mut().item_spacing.y = 8.0;
        let qr_dir = core.tracker.paths().qr_codes_dir;
        let mut remove_name: Option<String> = None;

        if !state.qr_items.is_empty() {
            ui.horizontal(|ui| {
                ui.spacing_mut().item_spacing.x = 10.0;
                for item in &state.qr_items {
                    let has_link = state
                        .qr_links
                        .get(&item.filename)
                        .map(|l| !l.trim().is_empty())
                        .unwrap_or(false);
                    let card_size = vec2(72.0, 72.0);
                    let (rect, mut card_resp) =
                        ui.allocate_exact_size(card_size, Sense::click());
                    card_resp = card_resp.on_hover_cursor(CursorIcon::PointingHand);
                    let tip = if has_link {
                        format!(
                            "{}\nLink: {}\n(Click to edit URL)",
                            item.filename,
                            state.qr_links.get(&item.filename).map(String::as_str).unwrap_or("")
                        )
                    } else {
                        format!("{}\nClick to set optional payment URL", item.filename)
                    };
                    card_resp = card_resp.on_hover_text(tip);

                    ui.painter().rect(
                        rect,
                        CornerRadius::same(10),
                        Color32::WHITE,
                        Stroke::new(1.0, palette.border_strong),
                        StrokeKind::Inside,
                    );

                    let full_qr_path = qr_dir.join(&item.filename);
                    if let Some(tex) = tex_cache.get_image_file(ui.ctx(), &full_qr_path) {
                        let img_rect = rect.shrink(6.0);
                        ui.painter().image(
                            tex.id(),
                            img_rect,
                            egui::Rect::from_min_max(pos2(0.0, 0.0), pos2(1.0, 1.0)),
                            Color32::WHITE,
                        );
                    } else {
                        ui.painter().text(
                            rect.center(),
                            egui::Align2::CENTER_CENTER,
                            "QR",
                            font_bold(12.0),
                            Color32::BLACK,
                        );
                    }

                    // Top-left green link status dot
                    if has_link {
                        ui.painter().circle_filled(
                            pos2(rect.left() + 8.0, rect.top() + 8.0),
                            4.0,
                            palette.green,
                        );
                    }

                    // Top-right red '✕' remove badge
                    let x_center = pos2(rect.right() - 7.0, rect.top() + 7.0);
                    let x_rect = egui::Rect::from_center_size(x_center, vec2(18.0, 18.0));
                    let x_resp = ui
                        .interact(
                            x_rect,
                            Id::unique(("qr_remove_x", &item.filename)),
                            Sense::click(),
                        )
                        .on_hover_cursor(CursorIcon::PointingHand)
                        .on_hover_text("Remove QR code");
                    ui.painter().circle_filled(
                        x_center,
                        8.0,
                        if x_resp.hovered() {
                            Color32::from_rgb(0xDC, 0x26, 0x26)
                        } else {
                            Color32::from_rgb(0xEF, 0x44, 0x44)
                        },
                    );
                    ui.painter().text(
                        x_center,
                        egui::Align2::CENTER_CENTER,
                        "✕",
                        font_bold(9.5),
                        Color32::WHITE,
                    );

                    if x_resp.clicked() {
                        remove_name = Some(item.filename.clone());
                    } else if card_resp.clicked() {
                        state.modal = Some(SettingsModal::QrLinkEditor {
                            filename: item.filename.clone(),
                            url: state
                                .qr_links
                                .get(&item.filename)
                                .cloned()
                                .unwrap_or_default(),
                        });
                    }
                }
            });
        }

        if let Some(rm) = remove_name {
            state.pending_qr_deletes.insert(rm.clone());
            state.qr_items.retain(|q| q.filename != rm);
            state.qr_links.remove(&rm);
        }

        let full_w = ui.available_width();
        if widgets::pill_button(
            ui,
            palette,
            PillVariant::Secondary,
            "+ Add QR Code",
            30.0,
            full_w,
            state.qr_items.len() < 4,
        )
        .clicked()
        {
            let core_bg = Arc::clone(core);
            let tx_bg = task_tx.clone();
            let ctx_bg = ui.ctx().clone();
            std::thread::spawn(move || {
                let picked = file_dialog::pick_open_file(
                    "Select Payment QR Code",
                    &[("Image Files (*.png;*.jpg;*.jpeg)", "*.png;*.jpg;*.jpeg")],
                    "png",
                );
                let out = match picked {
                    Some(src) => core_bg.import_qr_code(&src).map(Some),
                    None => Ok(None),
                };
                let _ = tx_bg.send(AsyncTaskResult::QrPicked(out));
                ctx_bg.request_repaint();
            });
        }

        ui.label(
            egui::RichText::new(
                "Upload up to 4 payment QR code images (PNG/JPG). They will appear in generated invoices at 140×140px.",
            )
            .font(font_regular(11.0))
            .color(palette.text_muted),
        );
    });

    // 6. Privacy Settings
    widgets::group_box(ui, palette, "Privacy Settings", |ui| {
        ui.spacing_mut().item_spacing.y = 6.0;
        widgets::th_checkbox_label(
            ui,
            palette,
            &mut d.mask_business_emails,
            "Mask business contact emails by default",
        );
        widgets::th_checkbox_label(
            ui,
            palette,
            &mut d.mask_business_phone,
            "Mask business contact phone number by default",
        );
        widgets::th_checkbox_label(
            ui,
            palette,
            &mut d.mask_client_emails,
            "Mask client contact emails by default",
        );
        ui.label(
            egui::RichText::new(
                "When enabled, sensitive contact details (emails, phone) are masked on the generated invoice. You can override these per-invoice.",
            )
            .font(font_regular(11.0))
            .color(palette.text_muted),
        );
    });

    state.dto = Some(d);
}

fn reload_core_after_import(core: &Arc<AppCore>, res: &ImportBackupResult) {
    let cur_paths = core.tracker.paths();
    let next_paths = crate::config::ProfilePaths::from_root_and_profile(
        cur_paths.app_data_root,
        res.active_profile.clone(),
    );
    let _ = core.tracker.reload_for_profile_switch(next_paths);
    core.push_debug_log(
        "INFO",
        &format!("Restored local backup ({} sessions)", res.total_sessions),
    );
    core.tracker_rev.fetch_add(1, Ordering::SeqCst);
    core.settings_rev.fetch_add(1, Ordering::SeqCst);
    core.sessions_rev.fetch_add(1, Ordering::SeqCst);
    core.invoices_rev.fetch_add(1, Ordering::SeqCst);
    core.categories_rev.fetch_add(1, Ordering::SeqCst);
}

fn try_save_settings(
    core: &Arc<AppCore>,
    state: &mut SettingsWindowState,
    cmds: &mut Vec<GuiCmd>,
) -> bool {
    let Some(mut dto) = state.dto.take() else {
        return true;
    };

    if !state.biz_email_draft.trim().is_empty() {
        widgets::commit_email_draft(&mut dto.business_emails, &mut state.biz_email_draft);
    }
    if !state.client_email_draft.trim().is_empty() {
        widgets::commit_email_draft(&mut dto.client_emails, &mut state.client_email_draft);
    }

    dto.min_track_seconds = state
        .min_track_buf
        .trim()
        .parse::<f64>()
        .map(|v| if v.is_finite() { v.round().max(0.0) as i64 } else { 0 })
        .unwrap_or(0);
    dto.auto_save_seconds = state
        .auto_save_buf
        .trim()
        .parse::<f64>()
        .map(|v| if v.is_finite() { v.round().max(1.0) as u64 } else { 10 })
        .unwrap_or(10);
    let im = state
        .idle_min_buf
        .trim()
        .parse::<f64>()
        .map(|v| if v.is_finite() { v.floor().max(0.0) as u64 } else { 0 })
        .unwrap_or(0);
    let isec = state
        .idle_sec_buf
        .trim()
        .parse::<f64>()
        .map(|v| {
            if v.is_finite() {
                (v.floor().max(0.0) as u64).min(59)
            } else {
                0
            }
        })
        .unwrap_or(0);
    dto.idle_threshold_seconds_total = im.saturating_mul(60).saturating_add(isec);
    dto.hourly_rate = state
        .hourly_rate_buf
        .trim()
        .parse::<f64>()
        .map(|v| if v.is_finite() { v.max(0.0) } else { 0.0 })
        .unwrap_or(0.0);
    let sym = dto
        .currency_symbol_raw
        .split_whitespace()
        .next()
        .unwrap_or("$");
    dto.currency_symbol = sym.split('(').next().unwrap_or("$").trim().to_string();
    if dto.currency_symbol.is_empty() {
        dto.currency_symbol = "$".into();
    }

    dto.distraction_apps = state.distraction_apps.clone();
    dto.qr_code_paths = state.qr_items.iter().map(|q| q.filename.clone()).collect();
    dto.qr_code_links = state.qr_links.clone();
    dto.qr_code_items = state.qr_items.clone();

    match core.save_full_settings(&dto) {
        Ok(snap) => {
            let keep: HashSet<String> = state.qr_items.iter().map(|q| q.filename.clone()).collect();
            for del in state.pending_qr_deletes.drain() {
                if !keep.contains(&del) {
                    core.delete_qr_code_file(&del);
                }
            }
            state.newly_added_qr_files.clear();
            state.original_theme = snap.theme_style.clone();
            cmds.push(GuiCmd::SetTheme(snap.theme_style));
            cmds.push(GuiCmd::ShowToast("Settings saved".into()));
            state.dto = Some(dto);
            true
        }
        Err(err) => {
            state.dto = Some(dto);
            state.modal = Some(SettingsModal::Alert {
                title: "Save Settings Error".into(),
                message: err,
                kind: AlertKind::Error,
            });
            false
        }
    }
}

fn render_settings_modals(
    ctx: &egui::Context,
    core: &Arc<AppCore>,
    palette: &ThemePalette,
    state: &mut SettingsWindowState,
    task_tx: &Sender<AsyncTaskResult>,
    cmds: &mut Vec<GuiCmd>,
) {
    let Some(mut modal) = state.modal.take() else {
        return;
    };

    let mut keep_open = true;
    let card_frame = Frame::NONE
        .fill(palette.bg_card)
        .stroke(Stroke::new(1.0, palette.border_strong))
        .corner_radius(CornerRadius::same(12))
        .inner_margin(Margin::same(16));

    let resp = Modal::new(Id::unique("settings_modal"))
        .backdrop_color(Color32::from_black_alpha(150))
        .frame(card_frame)
        .show(ctx, |ui| match &mut modal {
            SettingsModal::Alert {
                title,
                message,
                kind,
            } => {
                let inner_w = widgets::modal_inner_width(ctx, 350.0, 16);
                ui.set_width(inner_w);
                ui.horizontal(|ui| {
                    ui.spacing_mut().item_spacing.x = 12.0;
                    if *kind == AlertKind::Info {
                        let (ir, _) = ui.allocate_exact_size(vec2(32.0, 32.0), Sense::hover());
                        icons::paint_blue_info_badge(ui.painter(), ir.center(), 15.0);
                    }
                    let text_w = if *kind == AlertKind::Info {
                        (inner_w - 44.0).max(120.0)
                    } else {
                        inner_w
                    };
                    ui.vertical(|ui| {
                        ui.set_max_width(text_w);
                        let tc = match kind {
                            AlertKind::Error => palette.danger,
                            AlertKind::Warn => palette.amber,
                            AlertKind::Info => palette.text_primary,
                        };
                        ui.label(
                            egui::RichText::new(title.as_str())
                                .font(font_bold(15.0))
                                .color(tc),
                        );
                        ui.add_space(6.0);
                        ui.add(
                            egui::Label::new(
                                egui::RichText::new(message.as_str())
                                    .font(font_regular(12.5))
                                    .color(palette.text_secondary),
                            )
                            .wrap(),
                        );
                    });
                });
                ui.add_space(14.0);
                widgets::modal_action_row(ui, inner_w, 28.0, |ui| {
                    if widgets::pill_button(
                        ui,
                        palette,
                        PillVariant::PrimaryBlue,
                        "OK",
                        28.0,
                        72.0,
                        true,
                    )
                    .clicked()
                    {
                        keep_open = false;
                    }
                });
            }
            SettingsModal::PromptProfile {
                title,
                label,
                value,
                placeholder,
                confirm_label,
                is_rename_from,
            } => {
                let inner_w = widgets::modal_inner_width(ctx, 340.0, 16);
                ui.set_width(inner_w);
                ui.label(
                    egui::RichText::new(title.as_str())
                        .font(font_bold(15.0))
                        .color(palette.text_primary),
                );
                ui.add_space(6.0);
                ui.add(
                    egui::Label::new(
                        egui::RichText::new(label.as_str())
                            .font(font_regular(12.5))
                            .color(palette.text_secondary),
                    )
                    .wrap(),
                );
                ui.add_space(6.0);
                widgets::text_input_line(
                    ui,
                    palette,
                    value,
                    placeholder.as_str(),
                    inner_w,
                    true,
                );
                let enter = ui.input(|i| i.key_pressed(egui::Key::Enter));
                ui.add_space(14.0);
                widgets::modal_action_row(ui, inner_w, 28.0, |ui| {
                    if widgets::pill_button(
                        ui,
                        palette,
                        PillVariant::PrimaryBlue,
                        confirm_label.as_str(),
                        28.0,
                        82.0,
                        true,
                    )
                    .clicked()
                        || enter
                    {
                        let trimmed = value.trim().to_string();
                        if !trimmed.is_empty() {
                            let res = match is_rename_from {
                                Some(old) => core.rename_profile(old, &trimmed).map(|_| ()),
                                None => core
                                    .create_profile(&trimmed)
                                    .and_then(|_| core.switch_profile(&trimmed).map(|_| ())),
                            };
                            match res {
                                Ok(()) => {
                                    state.load_from_core(core);
                                    if let Some(ref d) = state.dto {
                                        cmds.push(GuiCmd::SetTheme(d.theme_style.clone()));
                                    }
                                    keep_open = false;
                                }
                                Err(err) => {
                                    cmds.push(GuiCmd::ShowToast(err));
                                }
                            }
                        }
                    }
                    if widgets::pill_button(
                        ui,
                        palette,
                        PillVariant::Secondary,
                        "Cancel",
                        28.0,
                        72.0,
                        true,
                    )
                    .clicked()
                    {
                        keep_open = false;
                    }
                });
            }
            SettingsModal::ConfirmDeleteProfile(name) => {
                let inner_w = widgets::modal_inner_width(ctx, 350.0, 16);
                ui.set_width(inner_w);
                ui.label(
                    egui::RichText::new("Delete Profile")
                        .font(font_bold(15.0))
                        .color(palette.text_primary),
                );
                ui.add_space(8.0);
                ui.add(
                    egui::Label::new(
                        egui::RichText::new(format!(
                            "Delete profile \"{name}\" and all of its local data? This cannot be undone."
                        ))
                        .font(font_regular(12.5))
                        .color(palette.text_secondary),
                    )
                    .wrap(),
                );
                ui.add_space(14.0);
                widgets::modal_action_row(ui, inner_w, 28.0, |ui| {
                    if widgets::pill_button(
                        ui,
                        palette,
                        PillVariant::DangerOutline,
                        "Delete Profile",
                        28.0,
                        108.0,
                        true,
                    )
                    .clicked()
                    {
                        match core.delete_profile(name) {
                            Ok(_) => {
                                state.load_from_core(core);
                                if let Some(ref d) = state.dto {
                                    cmds.push(GuiCmd::SetTheme(d.theme_style.clone()));
                                }
                                keep_open = false;
                            }
                            Err(err) => cmds.push(GuiCmd::ShowToast(err)),
                        }
                    }
                    if widgets::pill_button(
                        ui,
                        palette,
                        PillVariant::Secondary,
                        "Cancel",
                        28.0,
                        72.0,
                        true,
                    )
                    .clicked()
                    {
                        keep_open = false;
                    }
                });
            }
            SettingsModal::DistractionManager {
                search,
                custom_input,
                all_apps,
                working,
            } => {
                let inner_w = widgets::modal_inner_width(ctx, 390.0, 16);
                ui.set_width(inner_w);
                ui.label(
                    egui::RichText::new("Manage Distraction Apps")
                        .font(font_bold(15.0))
                        .color(palette.text_primary),
                );
                ui.add_space(8.0);
                widgets::text_input_line(
                    ui,
                    palette,
                    search,
                    "Filter applications...",
                    inner_w,
                    true,
                );
                ui.add_space(8.0);
                let q = search.trim().to_lowercase();
                Frame::NONE
                    .fill(palette.bg_card_alt)
                    .stroke(Stroke::new(1.0, palette.border))
                    .corner_radius(CornerRadius::same(8))
                    .inner_margin(Margin::same(8))
                    .show(ui, |ui| {
                        ui.set_width((inner_w - 18.0).max(160.0));
                        ui.set_height(210.0);
                        ScrollArea::vertical()
                            .id_salt("dist_mgr_scroll")
                            .auto_shrink([false, false])
                            .show(ui, |ui| {
                                ui.spacing_mut().item_spacing.y = 5.0;
                                let mut any = false;
                                for name in all_apps.iter() {
                                    if !q.is_empty() && !name.to_lowercase().contains(&q) {
                                        continue;
                                    }
                                    any = true;
                                    let mut checked = working.contains(name);
                                    widgets::th_checkbox_label(ui, palette, &mut checked, name);
                                    if checked {
                                        working.insert(name.clone());
                                    } else {
                                        working.remove(name);
                                    }
                                }
                                if !any {
                                    ui.label(
                                        egui::RichText::new("No matching applications.")
                                            .font(font_regular(12.0))
                                            .color(palette.text_muted),
                                    );
                                }
                            });
                    });
                ui.add_space(8.0);
                ui.horizontal(|ui| {
                    ui.spacing_mut().item_spacing.x = 6.0;
                    widgets::text_input_line(
                        ui,
                        palette,
                        custom_input,
                        "Add executable or app name (e.g. Steam.exe)...",
                        (inner_w - 108.0 - 6.0).max(120.0),
                        true,
                    );
                    if widgets::pill_button(
                        ui,
                        palette,
                        PillVariant::Secondary,
                        "+ Add Custom",
                        28.0,
                        108.0,
                        true,
                    )
                    .clicked()
                    {
                        let val = custom_input.trim().to_string();
                        if !val.is_empty() {
                            all_apps.insert(val.clone());
                            working.insert(val);
                            custom_input.clear();
                        }
                    }
                });
                ui.add_space(12.0);
                widgets::modal_action_row(ui, inner_w, 28.0, |ui| {
                    if widgets::pill_button(
                        ui,
                        palette,
                        PillVariant::PrimaryBlue,
                        "Apply List",
                        28.0,
                        88.0,
                        true,
                    )
                    .clicked()
                    {
                        let mut sorted: Vec<String> = working.iter().cloned().collect();
                        sorted.sort_by_key(|s| s.to_lowercase());
                        state.distraction_apps = sorted;
                        keep_open = false;
                    }
                    if widgets::pill_button(
                        ui,
                        palette,
                        PillVariant::Secondary,
                        "Cancel",
                        28.0,
                        72.0,
                        true,
                    )
                    .clicked()
                    {
                        keep_open = false;
                    }
                });
            }
            SettingsModal::QrLinkEditor { filename, url } => {
                let inner_w = widgets::modal_inner_width(ctx, 360.0, 16);
                ui.set_width(inner_w);
                ui.label(
                    egui::RichText::new("Payment QR Link")
                        .font(font_bold(15.0))
                        .color(palette.text_primary),
                );
                ui.add_space(6.0);
                ui.add(
                    egui::Label::new(
                        egui::RichText::new(format!(
                            "Optional payment URL for \"{filename}\" (leave blank to clear):"
                        ))
                        .font(font_regular(12.5))
                        .color(palette.text_secondary),
                    )
                    .wrap(),
                );
                ui.add_space(8.0);
                widgets::text_input_line(ui, palette, url, "https://...", inner_w, true);
                ui.add_space(14.0);
                widgets::modal_action_row(ui, inner_w, 28.0, |ui| {
                    if widgets::pill_button(
                        ui,
                        palette,
                        PillVariant::PrimaryBlue,
                        "Set Link",
                        28.0,
                        80.0,
                        true,
                    )
                    .clicked()
                    {
                        let trimmed = url.trim().to_string();
                        if trimmed.is_empty() {
                            state.qr_links.remove(filename);
                        } else {
                            state.qr_links.insert(filename.clone(), trimmed);
                        }
                        keep_open = false;
                    }
                    if widgets::pill_button(
                        ui,
                        palette,
                        PillVariant::Secondary,
                        "Cancel",
                        28.0,
                        72.0,
                        true,
                    )
                    .clicked()
                    {
                        keep_open = false;
                    }
                });
            }
            SettingsModal::LocalBackup {
                scope_profile,
                encrypted,
                pw1,
                pw2,
                busy,
            } => {
                let inner_w = widgets::modal_inner_width(ctx, 400.0, 16);
                ui.set_width(inner_w);
                ui.label(
                    egui::RichText::new("Local Backup Archive (.truehour)")
                        .font(font_bold(15.0))
                        .color(palette.text_primary),
                );
                ui.add_space(6.0);
                widgets::group_box(ui, palette, "Backup Scope", |ui| {
                    ui.radio_value(scope_profile, false, "Entire Workspace (All Profiles)");
                    ui.add(
                        egui::Label::new(
                            egui::RichText::new(
                                "Backs up all profiles, sessions, settings, tags, invoices, logos, and QR codes.",
                            )
                            .font(font_regular(11.0))
                            .color(palette.text_muted),
                        )
                        .wrap(),
                    );
                    ui.add_space(4.0);
                    ui.radio_value(
                        scope_profile,
                        true,
                        format!("Current Profile Only ({})", state.profiles.active_profile),
                    );
                    ui.add(
                        egui::Label::new(
                            egui::RichText::new(
                                "Exports only the currently active profile and its sessions/settings.",
                            )
                            .font(font_regular(11.0))
                            .color(palette.text_muted),
                        )
                        .wrap(),
                    );
                });
                widgets::group_box(ui, palette, "Protection", |ui| {
                    ui.radio_value(encrypted, false, "Standard Local Backup");
                    ui.add(
                        egui::Label::new(
                            egui::RichText::new(
                                "Excludes sensitive bank account fields so the archive stays portable.",
                            )
                            .font(font_regular(11.0))
                            .color(palette.text_muted),
                        )
                        .wrap(),
                    );
                    ui.add_space(4.0);
                    ui.radio_value(encrypted, true, "Password-Encrypted Backup");
                    ui.add(
                        egui::Label::new(
                            egui::RichText::new(
                                "Includes all settings with banking details protected under your password.",
                            )
                            .font(font_regular(11.0))
                            .color(palette.text_muted),
                        )
                        .wrap(),
                    );
                });
                if *encrypted {
                    ui.add_space(6.0);
                    ui.label(
                        egui::RichText::new("Encryption Password")
                            .font(font_semibold(12.0))
                            .color(palette.text_secondary),
                    );
                    widgets::password_input_line(ui, palette, pw1, "Backup password", inner_w);
                    ui.add_space(4.0);
                    widgets::password_input_line(ui, palette, pw2, "Confirm password", inner_w);
                }
                ui.add_space(12.0);
                widgets::modal_action_row(ui, inner_w, 30.0, |ui| {
                    if widgets::pill_button(
                        ui,
                        palette,
                        PillVariant::PrimaryBlue,
                        if *busy {
                            "Saving..."
                        } else {
                            "Save Backup Archive..."
                        },
                        30.0,
                        152.0,
                        !*busy,
                    )
                    .clicked()
                    {
                        if *encrypted {
                            if pw1.is_empty() {
                                cmds.push(GuiCmd::ShowToast(
                                    "Enter a password for encrypted backup.".into(),
                                ));
                                return;
                            }
                            if pw1 != pw2 {
                                cmds.push(GuiCmd::ShowToast("Passwords do not match.".into()));
                                return;
                            }
                        }
                        *busy = true;
                        let password = if *encrypted { Some(pw1.clone()) } else { None };
                        let is_prof = *scope_profile;
                        let paths = core.tracker.paths();
                        let root = paths.app_data_root;
                        let profile_name = paths.profile_name;
                        let tx_bg = task_tx.clone();
                        let ctx_bg = ui.ctx().clone();
                        std::thread::spawn(move || {
                            let date_tag = chrono::Local::now().format("%Y%m%d");
                            let default_name = if is_prof {
                                format!("TrueHour_{profile_name}_{date_tag}.truehour")
                            } else {
                                format!("TrueHour_Workspace_{date_tag}.truehour")
                            };
                            let title = if is_prof {
                                "Save TrueHour Profile Backup"
                            } else {
                                "Save TrueHour Workspace Backup"
                            };
                            let picked = file_dialog::pick_save_file(
                                title,
                                &default_name,
                                &[("TrueHour Backups (*.truehour)", "*.truehour")],
                                "truehour",
                            );
                            let result = match picked {
                                Some(dest) => {
                                    let res = if is_prof {
                                        crate::backup::backup_profile(
                                            &root,
                                            &profile_name,
                                            &dest,
                                            password.as_deref(),
                                        )
                                    } else {
                                        crate::backup::backup_workspace(
                                            &root,
                                            &dest,
                                            password.as_deref(),
                                        )
                                    };
                                    res.map(|_| Some(dest.to_string_lossy().to_string()))
                                }
                                None => Ok(None),
                            };
                            let _ = tx_bg.send(AsyncTaskResult::LocalBackupDone {
                                scope: if is_prof {
                                    "Profile".into()
                                } else {
                                    "Workspace".into()
                                },
                                result,
                            });
                            ctx_bg.request_repaint();
                        });
                    }
                    if widgets::pill_button(
                        ui,
                        palette,
                        PillVariant::Secondary,
                        "Cancel",
                        30.0,
                        72.0,
                        true,
                    )
                    .clicked()
                    {
                        keep_open = false;
                    }
                });
            }
            SettingsModal::EncryptedRestore {
                archive_path,
                message,
                password,
                busy,
            } => {
                let inner_w = widgets::modal_inner_width(ctx, 390.0, 16);
                ui.set_width(inner_w);
                ui.label(
                    egui::RichText::new("Encrypted Backup Password")
                        .font(font_bold(15.0))
                        .color(palette.text_primary),
                );
                ui.add_space(6.0);
                ui.add(
                    egui::Label::new(
                        egui::RichText::new(message.as_str())
                            .font(font_regular(12.5))
                            .color(palette.text_secondary),
                    )
                    .wrap(),
                );
                ui.add_space(8.0);
                widgets::password_input_line(
                    ui,
                    palette,
                    password,
                    "Enter backup password",
                    inner_w,
                );
                ui.add_space(12.0);
                ui.allocate_ui_with_layout(
                    vec2(inner_w, 28.0),
                    Layout::left_to_right(Align::Center),
                    |ui| {
                        ui.spacing_mut().item_spacing.x = 6.0;
                        if widgets::pill_button(
                            ui,
                            palette,
                            PillVariant::AmberOutline,
                            "Strip Banking & Continue",
                            28.0,
                            156.0,
                            !*busy,
                        )
                    .clicked()
                    {
                        *busy = true;
                        let core_bg = Arc::clone(core);
                        let src = PathBuf::from(archive_path.as_str());
                        let path_s = archive_path.clone();
                        let tx_bg = task_tx.clone();
                        let ctx_bg = ui.ctx().clone();
                        std::thread::spawn(move || {
                            let paths = core_bg.tracker.paths();
                            let result = crate::backup::import_backup(
                                &paths.app_data_root,
                                &src,
                                None,
                                true,
                                &paths.profile_name,
                            );
                            if result.status == "success" || result.status == "banking_stripped" {
                                reload_core_after_import(&core_bg, &result);
                            }
                            let _ = tx_bg.send(AsyncTaskResult::LocalImportDone {
                                archive_path: path_s,
                                result,
                            });
                            ctx_bg.request_repaint();
                        });
                    }
                    ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                        ui.spacing_mut().item_spacing.x = 6.0;
                        if widgets::pill_button(
                            ui,
                            palette,
                            PillVariant::PrimaryBlue,
                            "Unlock & Restore",
                            28.0,
                            116.0,
                            !*busy,
                        )
                        .clicked()
                        {
                            *busy = true;
                            let core_bg = Arc::clone(core);
                            let src = PathBuf::from(archive_path.as_str());
                            let path_s = archive_path.clone();
                            let pw = password.clone();
                            let tx_bg = task_tx.clone();
                            let ctx_bg = ui.ctx().clone();
                            std::thread::spawn(move || {
                                let paths = core_bg.tracker.paths();
                                let result = crate::backup::import_backup(
                                    &paths.app_data_root,
                                    &src,
                                    Some(&pw),
                                    false,
                                    &paths.profile_name,
                                );
                                if result.status == "success" || result.status == "banking_stripped"
                                {
                                    reload_core_after_import(&core_bg, &result);
                                }
                                let _ = tx_bg.send(AsyncTaskResult::LocalImportDone {
                                    archive_path: path_s,
                                    result,
                                });
                                ctx_bg.request_repaint();
                            });
                        }
                        if widgets::pill_button(
                            ui,
                            palette,
                            PillVariant::Secondary,
                            "Cancel",
                            28.0,
                            68.0,
                            true,
                        )
                        .clicked()
                        {
                            keep_open = false;
                        }
                    });
                });
            }
        });

    if resp.should_close() {
        keep_open = false;
    }
    if keep_open && state.modal.is_none() {
        state.modal = Some(modal);
    }
}
