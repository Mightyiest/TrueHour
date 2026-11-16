use super::icons;
use super::theme::{font_bold, font_regular, font_semibold, ThemePalette};
use super::widgets::{self, PillVariant};
use super::GuiCmd;
use crate::{AppCore, StopAndSaveResponse};
use egui::{
    vec2, Align, Color32, CornerRadius, Frame, Id, Layout, Margin, Modal, Sense, Stroke,
    ViewportBuilder, ViewportCommand, ViewportId,
};
use std::sync::Arc;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AlertKind {
    Info,
    Warn,
    Error,
}

#[derive(Debug, Clone)]
pub enum ConfirmPurpose {
    DiscardRecovery,
    DeleteProfile(String),
    ExitWhileTracking,
}

#[derive(Debug, Clone)]
pub enum PromptPurpose {
    NewProfile,
    RenameProfile(String),
}

#[derive(Debug, Clone)]
pub enum RootModalState {
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
        purpose: ConfirmPurpose,
    },
    Prompt {
        title: String,
        message: String,
        value: String,
        placeholder: String,
        confirm_label: String,
        purpose: PromptPurpose,
    },
    StopSaveSummary {
        resp: StopAndSaveResponse,
        session_name_edit: String,
    },
    Diagnostics,
}

pub fn render_root_modal(
    ctx: &egui::Context,
    core: &Arc<AppCore>,
    palette: &ThemePalette,
    modal_slot: &mut Option<RootModalState>,
    cmds: &mut Vec<GuiCmd>,
) {
    let Some(mut state) = modal_slot.take() else {
        return;
    };

    let mut keep_open = true;
    let card_frame = Frame::NONE
        .fill(palette.bg_card)
        .stroke(Stroke::new(1.0, palette.border_strong))
        .corner_radius(CornerRadius::same(12))
        .inner_margin(Margin::same(16));

    let modal_id = Id::unique("truehour_root_modal");
    let modal_resp = Modal::new(modal_id)
        .backdrop_color(Color32::from_black_alpha(150))
        .frame(card_frame)
        .show(ctx, |ui| match &mut state {
            RootModalState::Alert {
                title,
                message,
                kind,
            } => {
                let inner_w = widgets::modal_inner_width(ctx, 330.0, 16);
                ui.set_width(inner_w);
                ui.horizontal(|ui| {
                    ui.spacing_mut().item_spacing.x = 12.0;
                    if *kind == AlertKind::Info {
                        let (ir, _) = ui.allocate_exact_size(vec2(34.0, 34.0), Sense::hover());
                        icons::paint_blue_info_badge(ui.painter(), ir.center(), 16.0);
                    }
                    let text_w = if *kind == AlertKind::Info {
                        (inner_w - 46.0).max(120.0)
                    } else {
                        inner_w
                    };
                    ui.vertical(|ui| {
                        ui.set_max_width(text_w);
                        let title_color = match kind {
                            AlertKind::Error => palette.danger,
                            AlertKind::Warn => palette.amber,
                            AlertKind::Info => palette.text_primary,
                        };
                        ui.label(
                            egui::RichText::new(title.as_str())
                                .font(font_bold(15.0))
                                .color(title_color),
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
                widgets::modal_action_row(ui, inner_w, 30.0, |ui| {
                    if widgets::pill_button(
                        ui,
                        palette,
                        PillVariant::PrimaryBlue,
                        "OK",
                        30.0,
                        78.0,
                        true,
                    )
                    .clicked()
                        || ui.input(|i| i.key_pressed(egui::Key::Enter))
                    {
                        keep_open = false;
                    }
                });
            }
            RootModalState::Confirm {
                title,
                message,
                confirm_label,
                danger,
                purpose,
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
                ui.add_space(16.0);
                widgets::modal_action_row(ui, inner_w, 30.0, |ui| {
                    let variant = if *danger {
                        PillVariant::DangerOutline
                    } else {
                        PillVariant::PrimaryBlue
                    };
                    if widgets::pill_button(
                        ui,
                        palette,
                        variant,
                        confirm_label.as_str(),
                        30.0,
                        88.0,
                        true,
                    )
                    .clicked()
                    {
                        match purpose.clone() {
                            ConfirmPurpose::DiscardRecovery => {
                                let _ = core.resolve_interrupted_session(false);
                                cmds.push(GuiCmd::ShowToast("Recovery discarded".into()));
                            }
                            ConfirmPurpose::DeleteProfile(name) => {
                                if let Err(err) = core.delete_profile(&name) {
                                    cmds.push(GuiCmd::ShowAlert {
                                        title: "Delete Profile Error".into(),
                                        message: err,
                                        kind: AlertKind::Error,
                                    });
                                }
                            }
                            ConfirmPurpose::ExitWhileTracking => {
                                cmds.push(GuiCmd::RequestExit);
                            }
                        }
                        keep_open = false;
                    }
                    if widgets::pill_button(
                        ui,
                        palette,
                        PillVariant::Secondary,
                        "Cancel",
                        30.0,
                        78.0,
                        true,
                    )
                    .clicked()
                    {
                        keep_open = false;
                    }
                });
            }
            RootModalState::Prompt {
                title,
                message,
                value,
                placeholder,
                confirm_label,
                purpose,
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
                        egui::RichText::new(message.as_str())
                            .font(font_regular(12.5))
                            .color(palette.text_secondary),
                    )
                    .wrap(),
                );
                ui.add_space(8.0);
                let resp = widgets::text_input_line(
                    ui,
                    palette,
                    value,
                    placeholder.as_str(),
                    inner_w,
                    true,
                );
                if resp.gained_focus() || ui.memory(|m| m.focused().is_none()) {
                    resp.request_focus();
                }
                let enter = ui.input(|i| i.key_pressed(egui::Key::Enter));
                ui.add_space(14.0);
                widgets::modal_action_row(ui, inner_w, 30.0, |ui| {
                    if widgets::pill_button(
                        ui,
                        palette,
                        PillVariant::PrimaryBlue,
                        confirm_label.as_str(),
                        30.0,
                        84.0,
                        true,
                    )
                    .clicked()
                        || enter
                    {
                        let trimmed = value.trim().to_string();
                        if !trimmed.is_empty() {
                            match purpose.clone() {
                                PromptPurpose::NewProfile => {
                                    if let Err(err) = core
                                        .create_profile(&trimmed)
                                        .and_then(|_| core.switch_profile(&trimmed))
                                    {
                                        cmds.push(GuiCmd::ShowAlert {
                                            title: "Create Profile Error".into(),
                                            message: err,
                                            kind: AlertKind::Error,
                                        });
                                    }
                                }
                                PromptPurpose::RenameProfile(old) => {
                                    if trimmed != old {
                                        if let Err(err) = core.rename_profile(&old, &trimmed) {
                                            cmds.push(GuiCmd::ShowAlert {
                                                title: "Rename Profile Error".into(),
                                                message: err,
                                                kind: AlertKind::Error,
                                            });
                                        }
                                    }
                                }
                            }
                            keep_open = false;
                        }
                    }
                    if widgets::pill_button(
                        ui,
                        palette,
                        PillVariant::Secondary,
                        "Cancel",
                        30.0,
                        78.0,
                        true,
                    )
                    .clicked()
                    {
                        keep_open = false;
                    }
                });
            }
            RootModalState::StopSaveSummary {
                resp,
                session_name_edit,
            } => {
                let inner_w = widgets::modal_inner_width(ctx, 344.0, 16);
                ui.set_width(inner_w);
                ui.vertical_centered(|ui| {
                    ui.label(
                        egui::RichText::new("Session Summary Report")
                            .font(font_bold(15.5))
                            .color(palette.text_primary),
                    );
                    ui.add_space(4.0);
                    let date_label = if resp.report.date_display.is_empty() {
                        &resp.report.date
                    } else {
                        &resp.report.date_display
                    };
                    ui.label(
                        egui::RichText::new(format!(
                            "Date: {date_label} ({} - {})",
                            resp.report.start_display, resp.report.end_display
                        ))
                        .font(font_regular(12.0))
                        .color(palette.text_secondary),
                    );
                });
                ui.add_space(10.0);
                ui.label(
                    egui::RichText::new("Session Name")
                        .font(font_semibold(11.5))
                        .color(palette.text_secondary),
                );
                ui.add_space(3.0);
                widgets::text_input_line(
                    ui,
                    palette,
                    session_name_edit,
                    "Session name",
                    inner_w,
                    true,
                );
                ui.add_space(10.0);
                let card_w = (inner_w - 8.0) * 0.5;
                ui.horizontal(|ui| {
                    ui.spacing_mut().item_spacing.x = 8.0;
                    widgets::kpi_card_centered(
                        ui,
                        palette,
                        "Tracked Focus Time",
                        &resp.report.counted_formatted,
                        false,
                        card_w,
                    );
                    widgets::kpi_card_centered(
                        ui,
                        palette,
                        "Total Earned",
                        &resp.report.total_earned_display,
                        true,
                        card_w,
                    );
                });
                ui.add_space(10.0);

                Frame::NONE
                    .fill(Color32::from_rgba_unmultiplied(0x22, 0xC5, 0x5E, 26))
                    .stroke(Stroke::new(
                        1.0,
                        Color32::from_rgba_unmultiplied(0x22, 0xC5, 0x5E, 90),
                    ))
                    .corner_radius(CornerRadius::same(8))
                    .inner_margin(Margin::symmetric(10, 7))
                    .show(ui, |ui| {
                        let badge_inner_w = (inner_w - 22.0).max(160.0);
                        ui.set_width(badge_inner_w);
                        let trust_txt = match &resp.security {
                            Some(sec) => format!(
                                "100% Verified SHA-256 Ledger (Trust {}%)",
                                sec.trust_score
                            ),
                            None => "100% Verified SHA-256 Ledger".to_string(),
                        };
                        let galley = ui.painter().layout_no_wrap(
                            trust_txt.clone(),
                            font_semibold(11.5),
                            palette.green,
                        );
                        let content_w = 15.0 + 7.0 + galley.size().x;
                        ui.horizontal(|ui| {
                            ui.spacing_mut().item_spacing.x = 7.0;
                            if content_w < badge_inner_w {
                                ui.add_space((badge_inner_w - content_w) * 0.5);
                            }
                            let (sr, _) =
                                ui.allocate_exact_size(vec2(15.0, 15.0), Sense::hover());
                            icons::paint_shield_check(
                                ui.painter(),
                                sr.center(),
                                14.5,
                                palette.green,
                                Color32::WHITE,
                            );
                            ui.add(
                                egui::Label::new(
                                    egui::RichText::new(trust_txt)
                                        .font(font_semibold(11.5))
                                        .color(palette.green),
                                )
                                .wrap(),
                            );
                        });
                    });

                ui.add_space(12.0);
                if widgets::pill_button(
                    ui,
                    palette,
                    PillVariant::PrimaryBlue,
                    "Save Session",
                    34.0,
                    inner_w,
                    true,
                )
                .clicked()
                {
                    let next = session_name_edit.trim().to_string();
                    if !next.is_empty() && next != resp.report.session_name {
                        if let Err(err) = core.rename_saved_session(&resp.saved_path, &next) {
                            cmds.push(GuiCmd::ShowAlert {
                                title: "Rename Error".into(),
                                message: err,
                                kind: AlertKind::Error,
                            });
                            return;
                        }
                    }
                    cmds.push(GuiCmd::ShowToast("Session saved".into()));
                    keep_open = false;
                }
                ui.add_space(8.0);
                let half_w = (inner_w - 8.0) * 0.5;
                ui.horizontal(|ui| {
                    ui.spacing_mut().item_spacing.x = 8.0;
                    if widgets::pill_button(
                        ui,
                        palette,
                        PillVariant::Secondary,
                        "View Full Report",
                        30.0,
                        half_w,
                        true,
                    )
                    .clicked()
                    {
                        let p = resp.saved_path.clone();
                        keep_open = false;
                        cmds.push(GuiCmd::OpenReport(p));
                    }
                    if widgets::pill_button(
                        ui,
                        palette,
                        PillVariant::DangerOutline,
                        "Trash",
                        30.0,
                        half_w,
                        true,
                    )
                    .clicked()
                    {
                        match core.trash_saved_session(&resp.saved_path) {
                            Ok(()) => {
                                cmds.push(GuiCmd::ShowToast("Session moved to Trash".into()));
                                keep_open = false;
                            }
                            Err(err) => cmds.push(GuiCmd::ShowToast(err)),
                        }
                    }
                });
            }
            RootModalState::Diagnostics => {
                let inner_w = widgets::modal_inner_width(ctx, 344.0, 16);
                ui.set_width(inner_w);

                ui.allocate_ui_with_layout(
                    vec2(inner_w, 34.0),
                    Layout::left_to_right(Align::Center),
                    |ui| {
                        ui.spacing_mut().item_spacing.x = 10.0;
                        let (badge_rect, _) =
                            ui.allocate_exact_size(vec2(32.0, 32.0), Sense::hover());
                        ui.painter().rect_filled(
                            badge_rect,
                            CornerRadius::same(8),
                            Color32::from_rgba_unmultiplied(0x3B, 0x82, 0xF6, 28),
                        );
                        icons::paint_bug(
                            ui.painter(),
                            badge_rect.shrink(7.0),
                            Color32::from_rgb(0x60, 0xA5, 0xFA),
                        );
                        ui.vertical(|ui| {
                            ui.spacing_mut().item_spacing.y = 1.0;
                            ui.label(
                                egui::RichText::new("Diagnostics & Bug Report")
                                    .font(font_bold(15.0))
                                    .color(palette.text_primary),
                            );
                            ui.label(
                                egui::RichText::new("Offline runtime · Local-Only Mode")
                                    .font(font_regular(11.5))
                                    .color(palette.text_muted),
                            );
                        });
                    },
                );

                ui.add_space(10.0);
                Frame::NONE
                    .fill(palette.bg_card_alt)
                    .stroke(Stroke::new(1.0, palette.border))
                    .corner_radius(CornerRadius::same(8))
                    .inner_margin(Margin::symmetric(12, 10))
                    .show(ui, |ui| {
                        ui.set_width((inner_w - 26.0).max(160.0));
                        ui.add(
                            egui::Label::new(
                                egui::RichText::new(
                                    "TrueHour is running offline in Local-Only Mode. Inspect local runtime logs or open the issue tracker in your browser.",
                                )
                                .font(font_regular(12.0))
                                .color(palette.text_secondary),
                            )
                            .wrap(),
                        );
                    });

                ui.add_space(10.0);
                let half_w = (inner_w - 8.0) * 0.5;
                ui.horizontal(|ui| {
                    ui.spacing_mut().item_spacing.x = 8.0;
                    if widgets::pill_button_with_icon(
                        ui,
                        palette,
                        PillVariant::Secondary,
                        "Debug Console",
                        30.0,
                        half_w,
                        true,
                        Some(|p: &egui::Painter, r: egui::Rect, c: Color32| {
                            icons::paint_bug(p, r.shrink(1.0), c);
                        }),
                    )
                    .clicked()
                    {
                        cmds.push(GuiCmd::OpenDebug);
                        keep_open = false;
                    }
                    if widgets::pill_button(
                        ui,
                        palette,
                        PillVariant::Secondary,
                        "GitHub Issues",
                        30.0,
                        half_w,
                        true,
                    )
                    .clicked()
                    {
                        let _ = core
                            .open_external_url("https://github.com/mightyiest/TrueHour/issues");
                    }
                });

                ui.add_space(10.0);
                widgets::horizontal_divider(ui, palette);
                ui.add_space(10.0);

                ui.allocate_ui_with_layout(
                    vec2(inner_w, 30.0),
                    Layout::left_to_right(Align::Center),
                    |ui| {
                        if widgets::pill_button(
                            ui,
                            palette,
                            PillVariant::Secondary,
                            "About TrueHour",
                            30.0,
                            114.0,
                            true,
                        )
                        .clicked()
                        {
                            cmds.push(GuiCmd::OpenAbout);
                            keep_open = false;
                        }
                        ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                            if widgets::pill_button(
                                ui,
                                palette,
                                PillVariant::PrimaryBlue,
                                "Close",
                                30.0,
                                82.0,
                                true,
                            )
                            .clicked()
                                || ui.input(|i| {
                                    i.key_pressed(egui::Key::Enter)
                                        || i.key_pressed(egui::Key::Escape)
                                })
                            {
                                keep_open = false;
                            }
                        });
                    },
                );
            }
        });

    if modal_resp.should_close() {
        keep_open = false;
    }
    if keep_open {
        *modal_slot = Some(state);
    }
}

/// Separate native dialog viewport matching Python v4.2's "Session Resumed" popup window (Screenshot 3).
pub fn show_session_resumed_viewport(
    ctx: &egui::Context,
    palette: &ThemePalette,
    icon_data: &Option<Arc<egui::IconData>>,
    session_name_opt: &mut Option<String>,
    pos_slot: &mut Option<egui::Pos2>,
) {
    let Some(session_name) = session_name_opt.clone() else {
        *pos_slot = None;
        return;
    };
    if pos_slot.is_none() {
        let (pos, _) = widgets::centered_viewport_pos_and_size(ctx, vec2(340.0, 155.0));
        *pos_slot = pos;
    }
    let vp_id = ViewportId::from_hash_of("session_resumed_dialog");
    let mut builder = ViewportBuilder::default()
        .with_title("Session Resumed")
        .with_inner_size([340.0, 155.0])
        .with_min_inner_size([320.0, 145.0])
        .with_resizable(false)
        .with_minimize_button(false)
        .with_maximize_button(false);
    if let Some(pos) = *pos_slot {
        builder = builder.with_position(pos);
    }
    if let Some(ref ic) = icon_data {
        builder = builder.with_icon(Arc::clone(ic));
    }

    let mut close_now = false;
    ctx.show_viewport_immediate(vp_id, builder, |ui, _class| {
        if ui.ctx().input(|i| i.viewport().close_requested()) {
            close_now = true;
        }
        if render_session_resumed_contents(ui, palette, &session_name) {
            close_now = true;
        }
        if close_now {
            ui.ctx().send_viewport_cmd(ViewportCommand::Close);
        }
    });

    if close_now {
        *session_name_opt = None;
        *pos_slot = None;
    }
}

pub(crate) fn render_session_resumed_in_root(
    ui: &mut egui::Ui,
    palette: &ThemePalette,
    session_name_opt: &Option<String>,
) {
    let name = session_name_opt
        .as_deref()
        .unwrap_or("Resumed Session");
    let _ = render_session_resumed_contents(ui, palette, name);
}

fn render_session_resumed_contents(
    ui: &mut egui::Ui,
    palette: &ThemePalette,
    session_name: &str,
) -> bool {
    let mut close_now = false;
    egui::CentralPanel::default()
            .frame(
                Frame::NONE
                    .fill(palette.bg_window)
                    .inner_margin(Margin::symmetric(18, 16)),
            )
            .show(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.spacing_mut().item_spacing.x = 16.0;
                    let (icon_rect, _) =
                        ui.allocate_exact_size(vec2(46.0, 46.0), Sense::hover());
                    icons::paint_blue_info_badge(ui.painter(), icon_rect.center(), 22.0);
                    ui.vertical(|ui| {
                        ui.add_space(4.0);
                        ui.label(
                            egui::RichText::new(format!(
                                "Resumed session: {session_name}\nTracking is now active."
                            ))
                            .font(font_regular(13.0))
                            .color(palette.text_primary),
                        );
                    });
                });
                ui.add_space(24.0);
                ui.allocate_ui_with_layout(
                    vec2(ui.available_width(), 28.0),
                    Layout::right_to_left(Align::Center),
                    |ui| {
                        if widgets::pill_button(
                            ui,
                            palette,
                            PillVariant::Secondary,
                            "OK",
                            28.0,
                            68.0,
                            true,
                        )
                        .clicked()
                            || ui.input(|i| {
                                i.key_pressed(egui::Key::Enter) || i.key_pressed(egui::Key::Escape)
                            })
                        {
                            close_now = true;
                        }
                    },
                );
            });
    close_now
}
