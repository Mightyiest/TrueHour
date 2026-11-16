use super::icons;
use super::modals::AlertKind;
use super::theme::{font_bold, font_regular, font_semibold, ThemePalette};
use super::widgets::{self, PillVariant};
use super::GuiCmd;
use crate::invoice::{InvoicePrivacyOverrides, ManualLineItem};
use crate::report::SessionListEntry;
use crate::{compute_suggested_invoice_no, AppCore, SessionManagerTabData};
use egui::{
    vec2, Align, Color32, CornerRadius, Frame, Id, Layout, Margin, Modal, Panel, Pos2,
    ScrollArea, Sense, Stroke, Vec2, ViewportBuilder, ViewportCommand, ViewportId,
};
use std::collections::HashSet;
use std::sync::atomic::Ordering;
use std::sync::Arc;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SessionTab {
    Sessions,
    Recoveries,
    Trash,
    Invoices,
}

impl SessionTab {
    fn api_key(&self) -> &'static str {
        match self {
            Self::Sessions => "sessions",
            Self::Recoveries => "recoveries",
            Self::Trash => "trash",
            Self::Invoices => "invoices",
        }
    }
}

enum SessionModal {
    Alert {
        title: String,
        message: String,
        kind: AlertKind,
    },
    Confirm {
        title: String,
        message: String,
        confirm_label: String,
        danger: bool,
        action: ConfirmSmAction,
    },
    Prompt {
        title: String,
        label: String,
        value: String,
        confirm_label: String,
        action: PromptSmAction,
    },
    GenerateInvoice {
        selected_paths: Vec<String>,
        selected_names: Vec<String>,
        invoice_no: String,
        mask_biz_email: bool,
        mask_biz_phone: bool,
        mask_client_email: bool,
        extra_items: Vec<(String, String)>,
    },
}

#[derive(Clone)]
enum ConfirmSmAction {
    ResumeWhileRunning(String),
    TrashSession(String),
    DeleteRecovery(String),
    DeleteTrash(String),
    DeleteInvoice(String),
}

#[derive(Clone)]
enum PromptSmAction {
    RenameSession(String),
    RenameInvoice(String),
    MergeSessions(Vec<String>),
}

pub struct SessionsWindowState {
    pub open: bool,
    pub tab: SessionTab,
    pub edit_mode: bool,
    pub selected_paths: HashSet<String>,
    pub cached_data: Option<SessionManagerTabData>,
    last_loaded_tab: Option<SessionTab>,
    last_sessions_rev: u64,
    last_invoices_rev: u64,
    modal: Option<SessionModal>,
    spawn_pos: Option<Pos2>,
    spawn_size: Option<Vec2>,
}

impl Default for SessionsWindowState {
    fn default() -> Self {
        Self {
            open: false,
            tab: SessionTab::Sessions,
            edit_mode: false,
            selected_paths: HashSet::new(),
            cached_data: None,
            last_loaded_tab: None,
            last_sessions_rev: 0,
            last_invoices_rev: 0,
            modal: None,
            spawn_pos: None,
            spawn_size: None,
        }
    }
}

impl SessionsWindowState {
    pub fn mark_dirty(&mut self) {
        self.last_loaded_tab = None;
    }

    pub(crate) fn open_generate_invoice_preview(&mut self, core: &Arc<AppCore>) {
        ensure_sessions_loaded(core, self);
        if let Some(ref data) = self.cached_data {
            for s in &data.sessions {
                self.selected_paths.insert(s.filepath.clone());
            }
        }
        handle_invoice_click(core, self);
        if let Some(SessionModal::GenerateInvoice { ref mut extra_items, .. }) = self.modal {
            extra_items.push(("Rush delivery adjustment".into(), "15.00".into()));
        }
    }
}

pub fn show_sessions_viewport(
    ctx: &egui::Context,
    core: &Arc<AppCore>,
    palette: &ThemePalette,
    icon_data: &Option<Arc<egui::IconData>>,
    state: &mut SessionsWindowState,
    cmds: &mut Vec<GuiCmd>,
) {
    if !state.open {
        state.spawn_pos = None;
        state.spawn_size = None;
        return;
    }

    ensure_sessions_loaded(core, state);

    if state.spawn_size.is_none() {
        let (pos, sz) = widgets::centered_viewport_pos_and_size(ctx, vec2(520.0, 540.0));
        state.spawn_pos = pos;
        state.spawn_size = Some(sz);
    }
    let size = state.spawn_size.unwrap_or(vec2(520.0, 540.0));

    let vp_id = ViewportId::from_hash_of("sessions_window");
    let mut builder = ViewportBuilder::default()
        .with_title("Session Manager")
        .with_inner_size(size)
        .with_min_inner_size([460.0, 420.0])
        .with_resizable(true);
    if let Some(pos) = state.spawn_pos {
        builder = builder.with_position(pos);
    }
    if let Some(ref ic) = icon_data {
        builder = builder.with_icon(Arc::clone(ic));
    }

    let mut close_req = false;

    ctx.show_viewport_immediate(vp_id, builder, |ui, _class| {
        if ui.ctx().input(|i| i.viewport().close_requested()) {
            close_req = true;
        }
        if render_sessions_contents(ui, core, palette, state, cmds) {
            close_req = true;
        }
        if close_req {
            ui.ctx().send_viewport_cmd(ViewportCommand::Close);
        }
    });

    if close_req {
        state.open = false;
        state.spawn_pos = None;
        state.spawn_size = None;
    }
}

pub(crate) fn render_sessions_in_root(
    ui: &mut egui::Ui,
    core: &Arc<AppCore>,
    palette: &ThemePalette,
    state: &mut SessionsWindowState,
    cmds: &mut Vec<GuiCmd>,
) {
    ensure_sessions_loaded(core, state);
    let _ = render_sessions_contents(ui, core, palette, state, cmds);
}

fn ensure_sessions_loaded(core: &Arc<AppCore>, state: &mut SessionsWindowState) {
    let s_rev = core.sessions_rev.load(Ordering::SeqCst);
    let i_rev = core.invoices_rev.load(Ordering::SeqCst);
    if state.last_loaded_tab != Some(state.tab)
        || state.last_sessions_rev != s_rev
        || state.last_invoices_rev != i_rev
        || state.cached_data.is_none()
    {
        match core.list_session_manager_items(state.tab.api_key()) {
            Ok(data) => {
                let valid: HashSet<&str> =
                    data.sessions.iter().map(|s| s.filepath.as_str()).collect();
                state.selected_paths.retain(|p| valid.contains(p.as_str()));
                state.cached_data = Some(data);
            }
            Err(err) => {
                state.modal = Some(SessionModal::Alert {
                    title: "Session Manager Error".into(),
                    message: err,
                    kind: AlertKind::Error,
                });
            }
        }
        state.last_loaded_tab = Some(state.tab);
        state.last_sessions_rev = s_rev;
        state.last_invoices_rev = i_rev;
    }
}

fn render_sessions_contents(
    ui: &mut egui::Ui,
    core: &Arc<AppCore>,
    palette: &ThemePalette,
    state: &mut SessionsWindowState,
    cmds: &mut Vec<GuiCmd>,
) -> bool {
    let mut close_req = false;

    Panel::bottom("sm_footer")
            .frame(
                Frame::NONE
                    .fill(palette.bg_window)
                    .inner_margin(Margin {
                        left: 12,
                        right: 12,
                        top: 6,
                        bottom: 10,
                    }),
            )
            .show(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.spacing_mut().item_spacing.x = 6.0;

                    if widgets::pill_button_with_icon(
                        ui,
                        palette,
                        PillVariant::Secondary,
                        "Merge Sessions",
                        30.0,
                        126.0,
                        true,
                        Some(|p: &egui::Painter, r: egui::Rect, _c: Color32| {
                            icons::paint_merge_badge(p, r, Color32::from_rgb(0x25, 0x63, 0xEB), Color32::WHITE);
                        }),
                    )
                    .clicked()
                    {
                        handle_merge_click(state);
                    }

                    if widgets::pill_button_with_icon(
                        ui,
                        palette,
                        PillVariant::Accent,
                        "View Invoice in Browser",
                        30.0,
                        164.0,
                        true,
                        Some(|p: &egui::Painter, r: egui::Rect, _c: Color32| {
                            icons::paint_doc_icon(p, r, Color32::WHITE);
                        }),
                    )
                    .clicked()
                    {
                        handle_invoice_click(core, state);
                    }

                    ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                        ui.spacing_mut().item_spacing.x = 6.0;

                        if widgets::pill_button(
                            ui,
                            palette,
                            PillVariant::Secondary,
                            "Close",
                            30.0,
                            56.0,
                            true,
                        )
                        .clicked()
                        {
                            close_req = true;
                        }

                        if widgets::pill_button(
                            ui,
                            palette,
                            PillVariant::Secondary,
                            "Folder",
                            30.0,
                            58.0,
                            true,
                        )
                        .clicked()
                        {
                            let kind = match state.tab {
                                SessionTab::Recoveries => "autosave",
                                SessionTab::Trash => "trash",
                                _ => "sessions",
                            };
                            if let Err(err) = core.open_profile_folder(Some(kind)) {
                                state.modal = Some(SessionModal::Alert {
                                    title: "Folder Error".into(),
                                    message: err,
                                    kind: AlertKind::Error,
                                });
                            }
                        }
                    });
                });
            });

        egui::CentralPanel::default()
            .frame(
                Frame::NONE
                    .fill(palette.bg_window)
                    .inner_margin(Margin {
                        left: 12,
                        right: 12,
                        top: 10,
                        bottom: 0,
                    }),
            )
            .show(ui, |ui| {
                ui.spacing_mut().item_spacing.y = 0.0;

                // Folder tabs on left + Refresh / Edit on right
                let prev_tab = state.tab;
                let mut active_tab_rect = None;
                ui.horizontal(|ui| {
                    let tabs = [
                        (SessionTab::Sessions, "Sessions"),
                        (SessionTab::Recoveries, "Recoveries"),
                        (SessionTab::Trash, "Trash"),
                        (SessionTab::Invoices, "Invoices"),
                    ];
                    active_tab_rect =
                        widgets::folder_tab_bar(ui, palette, &tabs, &mut state.tab, 68.0);

                    ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                        ui.spacing_mut().item_spacing.x = 6.0;
                        if widgets::pill_button(
                            ui,
                            palette,
                            if state.edit_mode {
                                PillVariant::ToggledActive
                            } else {
                                PillVariant::Secondary
                            },
                            "Edit",
                            26.0,
                            46.0,
                            true,
                        )
                        .clicked()
                        {
                            state.edit_mode = !state.edit_mode;
                        }
                        if widgets::pill_button_with_icon(
                            ui,
                            palette,
                            PillVariant::Secondary,
                            "Refresh",
                            26.0,
                            74.0,
                            true,
                            Some(icons::paint_refresh),
                        )
                        .clicked()
                        {
                            state.mark_dirty();
                        }
                    });
                });

                if state.tab != prev_tab {
                    state.selected_paths.clear();
                    state.mark_dirty();
                }

                // Connected bordered container pane
                let pane_h = ui.available_height().max(120.0);
                let pane_resp = Frame::NONE
                    .fill(palette.bg_card)
                    .stroke(Stroke::new(1.0, palette.border))
                    .corner_radius(CornerRadius {
                        nw: 0,
                        ne: 8,
                        sw: 8,
                        se: 8,
                    })
                    .inner_margin(Margin::symmetric(0, 2))
                    .show(ui, |ui| {
                        ui.set_width(ui.available_width());
                        ui.set_height(pane_h - 6.0);

                        ScrollArea::vertical()
                            .id_salt("sm_list_scroll")
                            .auto_shrink([false, false])
                            .show(ui, |ui| {
                                render_tab_contents(
                                    ui,
                                    core,
                                    palette,
                                    state,
                                    cmds,
                                    &mut close_req,
                                );
                            });
                    });
                widgets::seamless_tab_join(ui, palette, active_tab_rect, pane_resp.response.rect);
            });

        render_session_modals(ui.ctx(), core, palette, state, cmds);

    close_req
}

fn render_tab_contents(
    ui: &mut egui::Ui,
    core: &Arc<AppCore>,
    palette: &ThemePalette,
    state: &mut SessionsWindowState,
    cmds: &mut Vec<GuiCmd>,
    close_req: &mut bool,
) {
    let Some(data) = state.cached_data.clone() else {
        return;
    };

    if state.tab == SessionTab::Invoices {
        if data.invoices.is_empty() {
            ui.add_space(60.0);
            ui.vertical_centered(|ui| {
                ui.label(
                    egui::RichText::new("No generated invoices yet.")
                        .font(font_regular(13.5))
                        .color(palette.text_secondary),
                );
            });
            return;
        }
        let len = data.invoices.len();
        for (idx, inv) in data.invoices.iter().enumerate() {
            let amount_txt = crate::report::format_currency(
                if inv.currency.is_empty() {
                    &data.currency_symbol
                } else {
                    &inv.currency
                },
                inv.amount,
            );
            let client = if inv.client_name.trim().is_empty() {
                "Default Client"
            } else {
                inv.client_name.trim()
            };

            let created_fmt = format_invoice_created(&inv.created_at);
            let title_str = format!("{} — {}", inv.invoice_no, client);
            let meta_str = format!("Created: {created_fmt}  |  Amount: {amount_txt}");

            Frame::NONE
                .inner_margin(Margin::symmetric(14, 10))
                .show(ui, |ui| {
                    let row_w = ui.available_width();
                    ui.set_width(row_w);
                    let text_w = (row_w - 186.0).max(140.0);
                    let title_galley = ui.painter().layout(
                        title_str.clone(),
                        font_bold(12.5),
                        palette.text_primary,
                        text_w,
                    );
                    let meta_galley = ui.painter().layout(
                        meta_str.clone(),
                        font_regular(11.0),
                        palette.text_secondary,
                        text_w,
                    );
                    let text_h = title_galley.size().y + 3.0 + meta_galley.size().y;
                    let row_h = (text_h + 2.0).max(28.0);

                    ui.allocate_ui_with_layout(
                        vec2(row_w, row_h),
                        Layout::left_to_right(Align::Center),
                        |ui| {
                            ui.spacing_mut().item_spacing.x = 12.0;
                            ui.allocate_ui_with_layout(
                                vec2(text_w, row_h),
                                Layout::top_down(Align::LEFT),
                                |ui| {
                                    ui.add_space(((row_h - text_h) * 0.5).max(0.0));
                                    ui.spacing_mut().item_spacing.y = 3.0;
                                    ui.add(
                                        egui::Label::new(
                                            egui::RichText::new(title_str)
                                                .font(font_bold(12.5))
                                                .color(palette.text_primary),
                                        )
                                        .wrap(),
                                    );
                                    ui.add(
                                        egui::Label::new(
                                            egui::RichText::new(meta_str)
                                                .font(font_regular(11.0))
                                                .color(palette.text_secondary),
                                        )
                                        .wrap(),
                                    );
                                },
                            );
                            ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                                ui.spacing_mut().item_spacing.x = 6.0;
                                if widgets::icon_square_button(
                                    ui,
                                    palette,
                                    vec2(26.0, 26.0),
                                    6,
                                    true,
                                    "Delete invoice",
                                    icons::paint_trash,
                                )
                                .clicked()
                                {
                                    state.modal = Some(SessionModal::Confirm {
                                        title: "Delete Invoice".into(),
                                        message: format!("Delete invoice \"{}\"?", inv.invoice_no),
                                        confirm_label: "Delete".into(),
                                        danger: true,
                                        action: ConfirmSmAction::DeleteInvoice(
                                            inv.invoice_no.clone(),
                                        ),
                                    });
                                }
                                if widgets::icon_square_button(
                                    ui,
                                    palette,
                                    vec2(26.0, 26.0),
                                    6,
                                    false,
                                    "Rename invoice",
                                    icons::paint_rename_pencil,
                                )
                                .clicked()
                                {
                                    state.modal = Some(SessionModal::Prompt {
                                        title: "Rename Invoice".into(),
                                        label: "New invoice number:".into(),
                                        value: inv.invoice_no.clone(),
                                        confirm_label: "Rename".into(),
                                        action: PromptSmAction::RenameInvoice(
                                            inv.invoice_no.clone(),
                                        ),
                                    });
                                }
                                if widgets::pill_button(
                                    ui,
                                    palette,
                                    PillVariant::Secondary,
                                    "View",
                                    26.0,
                                    50.0,
                                    true,
                                )
                                .clicked()
                                {
                                    if let Err(err) =
                                        core.open_saved_invoice_in_browser(&inv.invoice_no)
                                    {
                                        state.modal = Some(SessionModal::Alert {
                                            title: "Invoice Preview Error".into(),
                                            message: err,
                                            kind: AlertKind::Error,
                                        });
                                    }
                                }
                                if widgets::status_pill_button(
                                    ui,
                                    palette,
                                    &inv.status,
                                    "Click to cycle invoice status (DRAFT → UNPAID → PAID)",
                                )
                                .clicked()
                                {
                                    let _ = core.cycle_invoice_status(&inv.invoice_no);
                                    state.mark_dirty();
                                }
                            });
                        },
                    );
                });
            if idx + 1 < len {
                widgets::horizontal_divider(ui, palette);
            }
        }
        return;
    }

    if data.sessions.is_empty() {
        let msg = match state.tab {
            SessionTab::Recoveries => "No interrupted recovery sessions found.",
            SessionTab::Trash => "Trash is empty.",
            _ => "No saved sessions yet.",
        };
        ui.add_space(60.0);
        ui.vertical_centered(|ui| {
            ui.label(
                egui::RichText::new(msg)
                    .font(font_regular(13.5))
                    .color(palette.text_secondary),
            );
        });
        return;
    }

    let len = data.sessions.len();
    for (idx, s) in data.sessions.iter().enumerate() {
        render_session_row(ui, core, palette, state, s, cmds, close_req);
        if idx + 1 < len {
            widgets::horizontal_divider(ui, palette);
        }
    }
}

fn render_session_row(
    ui: &mut egui::Ui,
    core: &Arc<AppCore>,
    palette: &ThemePalette,
    state: &mut SessionsWindowState,
    s: &SessionListEntry,
    cmds: &mut Vec<GuiCmd>,
    close_req: &mut bool,
) {
    Frame::NONE
        .inner_margin(Margin::symmetric(14, 11))
        .show(ui, |ui| {
            let row_w = ui.available_width();
            ui.set_width(row_w);
            let has_checkbox = matches!(state.tab, SessionTab::Sessions | SessionTab::Recoveries);
            let cb_w = if has_checkbox { 30.0 } else { 0.0 };
            let right_w = if !state.edit_mode { 148.0 } else { 66.0 };
            let stack_w = (row_w - cb_w - right_w - 24.0).max(120.0);
            ui.allocate_ui_with_layout(
                vec2(row_w, 54.0),
                Layout::left_to_right(Align::Center),
                |ui| {
                    ui.spacing_mut().item_spacing.x = 12.0;

                    if has_checkbox {
                        let mut checked = state.selected_paths.contains(&s.filepath);
                        if widgets::th_checkbox(ui, palette, &mut checked).changed() {
                            if checked {
                                state.selected_paths.insert(s.filepath.clone());
                            } else {
                                state.selected_paths.remove(&s.filepath);
                            }
                        }
                    }

                    // 3-line stack: Title, ISO Date, Relative Pill Badge
                    ui.allocate_ui_with_layout(
                        vec2(stack_w, 54.0),
                        Layout::top_down(Align::LEFT),
                        |ui| {
                            ui.spacing_mut().item_spacing.y = 2.0;
                            ui.add_space(1.0);
                            let title_lbl = ui.add(
                                egui::Label::new(
                                    egui::RichText::new(&s.session_name)
                                        .font(font_bold(13.0))
                                        .color(palette.text_primary),
                                )
                                .truncate(),
                            );
                            title_lbl.on_hover_text(&s.filename);

                            ui.label(
                                egui::RichText::new(&s.date)
                                    .font(font_regular(11.5))
                                    .color(palette.text_secondary),
                            );

                            let badge = if s.is_latest {
                                "Latest"
                            } else if !s.relative_label.is_empty() {
                                s.relative_label.as_str()
                            } else {
                                s.date_display.as_str()
                            };
                            if !badge.is_empty() {
                                ui.add_space(1.0);
                                widgets::dark_badge_pill(
                                    ui,
                                    badge,
                                    if s.is_latest {
                                        palette.badge_latest_bg
                                    } else {
                                        palette.badge_rel_bg
                                    },
                                    if s.is_latest {
                                        palette.badge_latest_text
                                    } else {
                                        palette.badge_rel_text
                                    },
                                );
                            }
                        },
                    );

                // Right-aligned actions
                ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                    ui.spacing_mut().item_spacing.x = 6.0;

                    if !state.edit_mode {
                        if widgets::pill_button(
                            ui,
                            palette,
                            PillVariant::Secondary,
                            "View",
                            28.0,
                            54.0,
                            true,
                        )
                        .clicked()
                        {
                            cmds.push(GuiCmd::OpenReport(s.filepath.clone()));
                        }

                        if matches!(state.tab, SessionTab::Sessions | SessionTab::Recoveries) {
                            if widgets::pill_button_with_icon(
                                ui,
                                palette,
                                PillVariant::Accent,
                                "Resume",
                                28.0,
                                84.0,
                                true,
                                Some(|p: &egui::Painter, r: egui::Rect, c: Color32| {
                                    icons::paint_play_triangle(p, r.center(), 9.0, c);
                                }),
                            )
                            .clicked()
                            {
                                if core.tracker.is_running() {
                                    state.modal = Some(SessionModal::Confirm {
                                        title: "Session Currently Running".into(),
                                        message: "A session is currently running. Stop and autosave it, then resume this session?".into(),
                                        confirm_label: "Stop & Resume".into(),
                                        danger: false,
                                        action: ConfirmSmAction::ResumeWhileRunning(
                                            s.filepath.clone(),
                                        ),
                                    });
                                } else {
                                    match core.resume_saved_session(&s.filepath, false) {
                                        Ok(res) => {
                                            cmds.push(GuiCmd::FocusMain);
                                            cmds.push(GuiCmd::ShowResumedDialog(res.session_name));
                                            *close_req = true;
                                        }
                                        Err(err) => {
                                            state.modal = Some(SessionModal::Alert {
                                                title: "Cannot Resume Session".into(),
                                                message: err,
                                                kind: AlertKind::Warn,
                                            });
                                        }
                                    }
                                }
                            }
                        } else if state.tab == SessionTab::Trash
                            && widgets::pill_button(
                                ui,
                                palette,
                                PillVariant::Accent,
                                "Restore",
                                28.0,
                                74.0,
                                true,
                            )
                            .clicked()
                        {
                            match core.restore_trashed_session(&s.filepath) {
                                Ok(()) => {
                                    cmds.push(GuiCmd::ShowToast("Session restored".into()));
                                    state.mark_dirty();
                                }
                                Err(err) => {
                                    state.modal = Some(SessionModal::Alert {
                                        title: "Restore Error".into(),
                                        message: err,
                                        kind: AlertKind::Error,
                                    });
                                }
                            }
                        }
                    } else if matches!(state.tab, SessionTab::Sessions | SessionTab::Recoveries) {
                        let is_sess = state.tab == SessionTab::Sessions;
                        if widgets::icon_square_button(
                            ui,
                            palette,
                            vec2(28.0, 28.0),
                            6,
                            true,
                            if is_sess {
                                "Move to Trash"
                            } else {
                                "Delete Recovery"
                            },
                            icons::paint_trash,
                        )
                        .clicked()
                        {
                            state.modal = Some(SessionModal::Confirm {
                                title: if is_sess {
                                    "Move to Trash".into()
                                } else {
                                    "Delete Recovery".into()
                                },
                                message: if is_sess {
                                    format!("Move \"{}\" to Trash?", s.session_name)
                                } else {
                                    format!(
                                        "Permanently delete recovery \"{}\"?",
                                        s.session_name
                                    )
                                },
                                confirm_label: if is_sess {
                                    "Move to Trash".into()
                                } else {
                                    "Delete".into()
                                },
                                danger: true,
                                action: if is_sess {
                                    ConfirmSmAction::TrashSession(s.filepath.clone())
                                } else {
                                    ConfirmSmAction::DeleteRecovery(s.filepath.clone())
                                },
                            });
                        }

                        if widgets::icon_square_button(
                            ui,
                            palette,
                            vec2(28.0, 28.0),
                            6,
                            false,
                            "Rename session",
                            icons::paint_rename_pencil,
                        )
                        .clicked()
                        {
                            state.modal = Some(SessionModal::Prompt {
                                title: "Rename Session".into(),
                                label: "Session name:".into(),
                                value: s.session_name.clone(),
                                confirm_label: "Rename".into(),
                                action: PromptSmAction::RenameSession(s.filepath.clone()),
                            });
                        }
                    } else if state.tab == SessionTab::Trash {
                        if widgets::icon_square_button(
                            ui,
                            palette,
                            vec2(28.0, 28.0),
                            6,
                            true,
                            "Delete permanently",
                            icons::paint_trash,
                        )
                        .clicked()
                        {
                            state.modal = Some(SessionModal::Confirm {
                                title: "Delete Permanently".into(),
                                message: format!(
                                    "Permanently delete \"{}\"? This cannot be undone.",
                                    s.session_name
                                ),
                                confirm_label: "Delete Forever".into(),
                                danger: true,
                                action: ConfirmSmAction::DeleteTrash(s.filepath.clone()),
                            });
                        }

                        if widgets::icon_square_button(
                            ui,
                            palette,
                            vec2(28.0, 28.0),
                            6,
                            false,
                            "Restore session",
                            icons::paint_restore,
                        )
                        .clicked()
                        {
                            match core.restore_trashed_session(&s.filepath) {
                                Ok(()) => state.mark_dirty(),
                                Err(err) => {
                                    state.modal = Some(SessionModal::Alert {
                                        title: "Restore Error".into(),
                                        message: err,
                                        kind: AlertKind::Error,
                                    });
                                }
                            }
                        }
                    }
                });
            });
        });
}

fn format_invoice_created(raw: &str) -> String {
    let s = raw.trim();
    if let Ok(dt) = chrono::DateTime::parse_from_rfc3339(s) {
        return dt
            .with_timezone(&chrono::Local)
            .format("%b %d, %Y  %I:%M %p")
            .to_string();
    }
    for fmt in [
        "%Y-%m-%dT%H:%M:%S%.f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S%.f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
    ] {
        if let Ok(ndt) = chrono::NaiveDateTime::parse_from_str(s, fmt) {
            return ndt.format("%b %d, %Y  %I:%M %p").to_string();
        }
    }
    s.to_string()
}

fn get_selected_ordered(state: &SessionsWindowState) -> Vec<SessionListEntry> {
    let Some(ref data) = state.cached_data else {
        return Vec::new();
    };
    data.sessions
        .iter()
        .filter(|s| state.selected_paths.contains(&s.filepath))
        .cloned()
        .collect()
}

fn handle_merge_click(state: &mut SessionsWindowState) {
    if !matches!(state.tab, SessionTab::Sessions | SessionTab::Recoveries) {
        state.modal = Some(SessionModal::Alert {
            title: "Merge Sessions".into(),
            message: "Switch to the Sessions or Recoveries tab and select at least 2 sessions to merge.".into(),
            kind: AlertKind::Info,
        });
        return;
    }
    let selected = get_selected_ordered(state);
    if selected.len() < 2 {
        state.modal = Some(SessionModal::Alert {
            title: "Merge Sessions".into(),
            message: "Please select at least 2 sessions to merge.".into(),
            kind: AlertKind::Info,
        });
        return;
    }
    let default_name = format!("{} (Merged)", selected[0].session_name);
    let paths: Vec<String> = selected.into_iter().map(|s| s.filepath).collect();
    state.modal = Some(SessionModal::Prompt {
        title: "Merge Sessions".into(),
        label: format!("Name for merged session ({} files):", paths.len()),
        value: default_name,
        confirm_label: "Merge".into(),
        action: PromptSmAction::MergeSessions(paths),
    });
}

fn handle_invoice_click(core: &Arc<AppCore>, state: &mut SessionsWindowState) {
    if !matches!(state.tab, SessionTab::Sessions | SessionTab::Recoveries) {
        state.modal = Some(SessionModal::Alert {
            title: "No Sessions Selected".into(),
            message: "Switch to the Sessions or Recoveries tab and select at least one session using the checkbox on the left of the item.".into(),
            kind: AlertKind::Info,
        });
        return;
    }
    let selected = get_selected_ordered(state);
    if selected.is_empty() {
        state.modal = Some(SessionModal::Alert {
            title: "No Sessions Selected".into(),
            message: "Please select at least one session using the checkbox on the left of the item.".into(),
            kind: AlertKind::Info,
        });
        return;
    }
    let full = core.get_full_settings();
    let names_refs: Vec<&str> = selected.iter().map(|s| s.session_name.as_str()).collect();
    let suggested = compute_suggested_invoice_no(&names_refs);
    state.modal = Some(SessionModal::GenerateInvoice {
        selected_paths: selected.iter().map(|s| s.filepath.clone()).collect(),
        selected_names: selected.iter().map(|s| s.session_name.clone()).collect(),
        invoice_no: suggested,
        mask_biz_email: full.settings.mask_business_emails,
        mask_biz_phone: full.settings.mask_business_phone,
        mask_client_email: full.settings.mask_client_emails,
        extra_items: Vec::new(),
    });
}

fn render_session_modals(
    ctx: &egui::Context,
    core: &Arc<AppCore>,
    palette: &ThemePalette,
    state: &mut SessionsWindowState,
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

    let resp = Modal::new(Id::unique("sessions_modal"))
        .backdrop_color(Color32::from_black_alpha(150))
        .frame(card_frame)
        .show(ctx, |ui| match &mut modal {
            SessionModal::Alert {
                title,
                message,
                kind,
            } => {
                let inner_w = widgets::modal_inner_width(ctx, 340.0, 16);
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
            SessionModal::Confirm {
                title,
                message,
                confirm_label,
                danger,
                action,
            } => {
                let inner_w = widgets::modal_inner_width(ctx, 340.0, 16);
                ui.set_width(inner_w);
                ui.label(
                    egui::RichText::new(title.as_str())
                        .font(font_bold(15.0))
                        .color(palette.text_primary),
                );
                ui.add_space(8.0);
                ui.add(
                    egui::Label::new(
                        egui::RichText::new(message.as_str())
                            .font(font_regular(12.5))
                            .color(palette.text_secondary),
                    )
                    .wrap(),
                );
                ui.add_space(14.0);
                widgets::modal_action_row(ui, inner_w, 28.0, |ui| {
                    let var = if *danger {
                        PillVariant::DangerOutline
                    } else {
                        PillVariant::PrimaryBlue
                    };
                    if widgets::pill_button(
                        ui,
                        palette,
                        var,
                        confirm_label.as_str(),
                        28.0,
                        88.0,
                        true,
                    )
                    .clicked()
                    {
                        keep_open = false;
                        match action.clone() {
                            ConfirmSmAction::ResumeWhileRunning(path) => {
                                match core.resume_saved_session(&path, true) {
                                    Ok(res) => {
                                        cmds.push(GuiCmd::FocusMain);
                                        cmds.push(GuiCmd::ShowResumedDialog(res.session_name));
                                        state.open = false;
                                    }
                                    Err(err) => cmds.push(GuiCmd::ShowToast(err)),
                                }
                            }
                            ConfirmSmAction::TrashSession(path) => {
                                if let Err(err) = core.trash_saved_session(&path) {
                                    cmds.push(GuiCmd::ShowToast(err));
                                } else {
                                    state.mark_dirty();
                                }
                            }
                            ConfirmSmAction::DeleteRecovery(path) => {
                                if let Err(err) = core.delete_session_permanently(&path, "autosave")
                                {
                                    cmds.push(GuiCmd::ShowToast(err));
                                } else {
                                    state.mark_dirty();
                                }
                            }
                            ConfirmSmAction::DeleteTrash(path) => {
                                if let Err(err) = core.delete_session_permanently(&path, "trash") {
                                    cmds.push(GuiCmd::ShowToast(err));
                                } else {
                                    state.mark_dirty();
                                }
                            }
                            ConfirmSmAction::DeleteInvoice(inv_no) => {
                                if let Err(err) = core.delete_invoice_record(&inv_no) {
                                    cmds.push(GuiCmd::ShowToast(err));
                                } else {
                                    state.mark_dirty();
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
            SessionModal::Prompt {
                title,
                label,
                value,
                confirm_label,
                action,
            } => {
                let inner_w = widgets::modal_inner_width(ctx, 350.0, 16);
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
                widgets::text_input_line(ui, palette, value, "", inner_w, true);
                let enter = ui.input(|i| i.key_pressed(egui::Key::Enter));
                ui.add_space(14.0);
                widgets::modal_action_row(ui, inner_w, 28.0, |ui| {
                    if widgets::pill_button(
                        ui,
                        palette,
                        PillVariant::PrimaryBlue,
                        confirm_label.as_str(),
                        28.0,
                        80.0,
                        true,
                    )
                    .clicked()
                        || enter
                    {
                        let trimmed = value.trim().to_string();
                        if !trimmed.is_empty() {
                            keep_open = false;
                            match action.clone() {
                                PromptSmAction::RenameSession(path) => {
                                    if let Err(err) = core.rename_saved_session(&path, &trimmed) {
                                        cmds.push(GuiCmd::ShowToast(err));
                                    } else {
                                        state.mark_dirty();
                                    }
                                }
                                PromptSmAction::RenameInvoice(old_no) => {
                                    if let Err(err) = core.rename_invoice_no(&old_no, &trimmed) {
                                        cmds.push(GuiCmd::ShowToast(err));
                                    } else {
                                        state.mark_dirty();
                                    }
                                }
                                PromptSmAction::MergeSessions(paths) => {
                                    match core.merge_selected_sessions(&paths, &trimmed) {
                                        Ok(_) => {
                                            state.selected_paths.clear();
                                            state.mark_dirty();
                                            cmds.push(GuiCmd::ShowToast("Sessions merged".into()));
                                        }
                                        Err(err) => cmds.push(GuiCmd::ShowToast(err)),
                                    }
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
            SessionModal::GenerateInvoice {
                selected_paths,
                selected_names,
                invoice_no,
                mask_biz_email,
                mask_biz_phone,
                mask_client_email,
                extra_items,
            } => {
                let inner_w = widgets::modal_inner_width(ctx, 410.0, 16);
                ui.set_width(inner_w);
                ui.label(
                    egui::RichText::new("Generate & Preview Invoice")
                        .font(font_bold(15.0))
                        .color(palette.text_primary),
                );
                ui.add_space(4.0);
                let names_summary = if selected_names.len() > 3 {
                    format!(
                        "{}, +{} more",
                        selected_names[..3].join(", "),
                        selected_names.len() - 3
                    )
                } else {
                    selected_names.join(", ")
                };
                ui.add(
                    egui::Label::new(
                        egui::RichText::new(format!(
                            "Selected sessions: {} ({names_summary})",
                            selected_names.len()
                        ))
                        .font(font_regular(12.0))
                        .color(palette.text_secondary),
                    )
                    .wrap(),
                );
                ui.add_space(10.0);
                ui.label(
                    egui::RichText::new("Invoice No.")
                        .font(font_semibold(12.0))
                        .color(palette.text_secondary),
                );
                ui.add_space(3.0);
                widgets::text_input_line(
                    ui,
                    palette,
                    invoice_no,
                    "Auto-generated if left blank",
                    inner_w,
                    true,
                );
                ui.add_space(8.0);
                widgets::group_box(ui, palette, "Privacy Options", |ui| {
                    ui.spacing_mut().item_spacing.y = 5.0;
                    widgets::th_checkbox_label(
                        ui,
                        palette,
                        mask_biz_email,
                        "Mask Business Emails",
                    );
                    widgets::th_checkbox_label(
                        ui,
                        palette,
                        mask_biz_phone,
                        "Mask Business Phone Number",
                    );
                    widgets::th_checkbox_label(
                        ui,
                        palette,
                        mask_client_email,
                        "Mask Client Emails",
                    );
                });
                widgets::group_box(ui, palette, "Additional Payment Items (Optional)", |ui| {
                    ui.horizontal(|ui| {
                        ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                            if widgets::pill_button(
                                ui,
                                palette,
                                PillVariant::Secondary,
                                "+ Add Item",
                                24.0,
                                84.0,
                                true,
                            )
                            .clicked()
                            {
                                extra_items.push((String::new(), String::new()));
                            }
                        });
                    });
                    if !extra_items.is_empty() {
                        ui.add_space(4.0);
                        ScrollArea::vertical()
                            .id_salt("inv_extra_items_scroll")
                            .max_height(120.0)
                            .show(ui, |ui| {
                                let mut remove_idx = None;
                                let avail = ui.available_width();
                                let amt_w = 72.0;
                                let btn_w = 28.0;
                                let desc_w = (avail - amt_w - btn_w - 14.0).max(120.0);
                                for (idx, (desc, amt)) in extra_items.iter_mut().enumerate() {
                                    ui.horizontal(|ui| {
                                        ui.spacing_mut().item_spacing.x = 6.0;
                                        widgets::text_input_line(
                                            ui,
                                            palette,
                                            desc,
                                            "Description (e.g. Rush fee)",
                                            desc_w,
                                            true,
                                        );
                                        widgets::text_input_line(
                                            ui, palette, amt, "0.00", amt_w, true,
                                        );
                                        if widgets::pill_button(
                                            ui,
                                            palette,
                                            PillVariant::DangerOutline,
                                            "×",
                                            26.0,
                                            btn_w,
                                            true,
                                        )
                                        .clicked()
                                        {
                                            remove_idx = Some(idx);
                                        }
                                    });
                                    ui.add_space(4.0);
                                }
                                if let Some(i) = remove_idx {
                                    extra_items.remove(i);
                                }
                            });
                    }
                });
                ui.add_space(12.0);
                widgets::modal_action_row(ui, inner_w, 30.0, |ui| {
                    if widgets::pill_button(
                        ui,
                        palette,
                        PillVariant::Accent,
                        "Generate",
                        30.0,
                        92.0,
                        true,
                    )
                    .clicked()
                    {
                        let additional_items: Vec<ManualLineItem> = extra_items
                            .iter()
                            .filter_map(|(d, a)| {
                                let dt = d.trim();
                                let val = a.trim().parse::<f64>().ok()?;
                                if !dt.is_empty() && val.is_finite() {
                                    Some(ManualLineItem {
                                        description: dt.to_string(),
                                        amount: val,
                                    })
                                } else {
                                    None
                                }
                            })
                            .collect();
                        let privacy = InvoicePrivacyOverrides {
                            mask_business_emails: *mask_biz_email,
                            mask_business_phone: *mask_biz_phone,
                            mask_client_emails: *mask_client_email,
                            invoice_no: if invoice_no.trim().is_empty() {
                                None
                            } else {
                                Some(invoice_no.trim().to_string())
                            },
                            additional_items,
                        };
                        match core.generate_and_preview_invoice(selected_paths, privacy) {
                            Ok(inv_no) => {
                                keep_open = false;
                                state.mark_dirty();
                                cmds.push(GuiCmd::ShowToast(format!(
                                    "Invoice \"{inv_no}\" opened in browser"
                                )));
                            }
                            Err(err) => {
                                cmds.push(GuiCmd::ShowToast(err));
                            }
                        }
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
        });

    if resp.should_close() {
        keep_open = false;
    }
    if keep_open && state.modal.is_none() {
        state.modal = Some(modal);
    }
}
