use super::icons;
use super::modals::ConfirmPurpose;
use super::modals::RootModalState;
use super::theme::{font_bold, font_regular, font_semibold, parse_hex_color, ThemeKind, ThemePalette};
use super::widgets::{self, PillVariant};
use super::{GuiCmd, TextureCache};
use crate::tracker::{TrackedAppRowSnapshot, TrackerUiSnapshot};
use crate::AppCore;
use egui::text::LayoutJob;
use egui::{
    pos2, vec2, Align, Color32, CornerRadius, CursorIcon, Frame, Id, Layout, Margin, Popup,
    PopupCloseBehavior, Rect, ScrollArea, Sense, Stroke, StrokeKind, TextFormat, Ui,
};
use std::sync::Arc;
use std::time::Instant;

pub struct MainWindowState {
    pub new_cat_draft: String,
    pub version_clicks: Vec<Instant>,
}

impl Default for MainWindowState {
    fn default() -> Self {
        Self {
            new_cat_draft: String::new(),
            version_clicks: Vec::new(),
        }
    }
}

pub fn render_main_window(
    ui: &mut Ui,
    core: &Arc<AppCore>,
    palette: &ThemePalette,
    snap: &TrackerUiSnapshot,
    tex_cache: &mut TextureCache,
    state: &mut MainWindowState,
    modal_slot: &mut Option<RootModalState>,
    cmds: &mut Vec<GuiCmd>,
) {
    let ctx = ui.ctx().clone();

    // 1. Top Toolbar
    ui.horizontal(|ui| {
        ui.spacing_mut().item_spacing.x = 6.0;

        // Left: Theme toggle square button
        let theme_tip = match palette.kind {
            ThemeKind::ModernDark => "Switch to Classic Dark Mode",
            ThemeKind::ClassicDark => "Switch to Light Mode",
            ThemeKind::Light => "Switch to Modern Dark Mode",
        };
        let btn_bg = palette.normal_btn_bg;
        let theme_resp = widgets::icon_square_button(
            ui,
            palette,
            vec2(28.0, 28.0),
            6,
            false,
            theme_tip,
            |p, r, _fg| match palette.kind {
                ThemeKind::ClassicDark => {
                    icons::paint_sun(p, r, Color32::from_rgb(0xD1, 0xD5, 0xDB));
                }
                ThemeKind::Light => {
                    icons::paint_crescent_moon(p, r, Color32::from_rgb(0x25, 0x63, 0xEB), btn_bg);
                }
                ThemeKind::ModernDark => {
                    icons::paint_crescent_moon(p, r, Color32::from_rgb(0x64, 0x74, 0x8B), btn_bg);
                }
            },
        );
        if theme_resp.clicked() {
            let next = core.cycle_theme();
            cmds.push(GuiCmd::SetTheme(next.theme_style));
        }

        ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
            ui.spacing_mut().item_spacing.x = 6.0;

            if widgets::icon_square_button(
                ui,
                palette,
                vec2(28.0, 28.0),
                6,
                false,
                "Settings",
                icons::paint_gear,
            )
            .clicked()
            {
                cmds.push(GuiCmd::OpenSettings(None));
            }

            if widgets::icon_square_button(
                ui,
                palette,
                vec2(28.0, 28.0),
                6,
                false,
                "Session Manager",
                icons::paint_folder,
            )
            .clicked()
            {
                cmds.push(GuiCmd::OpenSessions);
            }

            // Dashboard pill/flat button with icon
            let dash_w = 92.0;
            let (dr, mut dresp) = ui.allocate_exact_size(vec2(dash_w, 28.0), Sense::click());
            dresp = dresp
                .on_hover_cursor(CursorIcon::PointingHand)
                .on_hover_text("Open Analytics Dashboard");
            if dresp.hovered() {
                ui.painter().rect(
                    dr,
                    CornerRadius::same(6),
                    palette.normal_btn_hover,
                    Stroke::new(1.0, palette.border),
                    StrokeKind::Inside,
                );
            }
            let icon_r = Rect::from_min_size(pos2(dr.left() + 6.0, dr.top() + 6.0), vec2(15.0, 15.0));
            icons::paint_bars(ui.painter(), icon_r, palette.text_primary);
            let dg = ui.painter().layout_no_wrap(
                "Dashboard".to_string(),
                font_regular(12.5),
                palette.text_primary,
            );
            ui.painter().galley(
                pos2(icon_r.right() + 5.0, dr.center().y - dg.size().y * 0.5),
                dg,
                palette.text_primary,
            );
            if dresp.clicked() {
                cmds.push(GuiCmd::OpenDashboard(None));
            }
        });
    });

    ui.add_space(6.0);

    // 2. Crash recovery banner (shown when interrupted active_session.json is present)
    if snap.has_pending_recovery && !snap.running {
        if let Some(ref sum) = snap.pending_recovery_summary {
            Frame::NONE
                .fill(palette.accent_soft)
                .stroke(Stroke::new(1.0, palette.accent))
                .corner_radius(CornerRadius::same(8))
                .inner_margin(Margin::symmetric(10, 7))
                .show(ui, |ui| {
                    ui.set_width(ui.available_width());
                    ui.horizontal(|ui| {
                        ui.vertical(|ui| {
                            ui.label(
                                egui::RichText::new("Interrupted session found")
                                    .font(font_semibold(12.0))
                                    .color(palette.text_primary),
                            );
                            ui.label(
                                egui::RichText::new(format!(
                                    "{} · {} ({} apps)",
                                    sum.session_name, sum.tracked_formatted, sum.app_count
                                ))
                                .font(font_regular(11.0))
                                .color(palette.text_secondary),
                            );
                        });
                        ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                            ui.spacing_mut().item_spacing.x = 5.0;
                            if widgets::pill_button(
                                ui,
                                palette,
                                PillVariant::Secondary,
                                "Dismiss",
                                24.0,
                                58.0,
                                true,
                            )
                            .clicked()
                            {
                                *modal_slot = Some(RootModalState::Confirm {
                                    title: "Discard Recovery".into(),
                                    message: "Discard the interrupted autosave session? This cannot be undone.".into(),
                                    confirm_label: "Discard".into(),
                                    danger: true,
                                    purpose: ConfirmPurpose::DiscardRecovery,
                                });
                            }
                            if widgets::pill_button(
                                ui,
                                palette,
                                PillVariant::PrimaryBlue,
                                "Recover",
                                24.0,
                                62.0,
                                true,
                            )
                            .clicked()
                            {
                                let _ = core.resolve_interrupted_session(true);
                                cmds.push(GuiCmd::ShowToast("Session recovered".into()));
                            }
                        });
                    });
                });
            ui.add_space(6.0);
        }
    }

    // 3. Timer Card
    let is_any_pause = snap.paused || snap.idle_paused || snap.distraction_paused;
    Frame::NONE
        .fill(palette.bg_card)
        .stroke(Stroke::new(1.0, palette.border))
        .corner_radius(CornerRadius::same(12))
        .inner_margin(Margin::symmetric(14, 16))
        .show(ui, |ui| {
            ui.set_width(ui.available_width());
            ui.vertical_centered(|ui| {
                ui.label(
                    egui::RichText::new(&snap.counted_hms)
                        .font(font_bold(42.0))
                        .color(palette.clock_color),
                );

                let show_earnings =
                    snap.hourly_rate > 0.0 && (snap.running || snap.counted_seconds > 0);
                if show_earnings {
                    ui.add_space(3.0);
                    let mut job = LayoutJob::default();
                    job.append(
                        "💰 ",
                        0.0,
                        TextFormat {
                            font_id: font_regular(13.0),
                            color: Color32::from_rgb(0xF5, 0x9E, 0x0B),
                            ..Default::default()
                        },
                    );
                    job.append(
                        &format!("{} earned", snap.earned_display),
                        0.0,
                        TextFormat {
                            font_id: font_bold(13.0),
                            color: if snap.running && is_any_pause {
                                palette.text_secondary
                            } else {
                                palette.earned_color
                            },
                            ..Default::default()
                        },
                    );
                    if snap.running && is_any_pause {
                        job.append(
                            "  (paused)",
                            0.0,
                            TextFormat {
                                font_id: font_regular(12.0),
                                color: palette.text_secondary,
                                ..Default::default()
                            },
                        );
                    }
                    ui.label(job);
                }

                let sub_line = if snap.running && is_any_pause {
                    Some((
                        snap.status_text.clone(),
                        if palette.is_dark {
                            Color32::WHITE
                        } else {
                            Color32::from_rgb(0xCA, 0x50, 0x10)
                        },
                    ))
                } else if snap.running {
                    let trimmed = snap.status_text.trim();
                    if trimmed.is_empty() || trimmed == "Active: [Idle]" {
                        None
                    } else {
                        Some((trimmed.to_string(), palette.text_secondary))
                    }
                } else {
                    let txt = if snap.status_text.trim().is_empty() {
                        "Ready to track".to_string()
                    } else {
                        snap.status_text.clone()
                    };
                    Some((txt, palette.text_secondary))
                };

                if let Some((txt, col)) = sub_line {
                    ui.add_space(2.0);
                    ui.label(
                        egui::RichText::new(txt)
                            .font(font_regular(12.0))
                            .color(col),
                    );
                } else {
                    ui.add_space(10.0);
                }

                ui.add_space(10.0);

                // Action pill buttons centered horizontally
                let buttons_w = 78.0 + 8.0 + 82.0 + 8.0 + 118.0;
                let left_pad = ((ui.available_width() - buttons_w) * 0.5).max(0.0);
                ui.horizontal(|ui| {
                    ui.add_space(left_pad);
                    ui.spacing_mut().item_spacing.x = 8.0;

                    let start_resp = widgets::pill_button_with_icon(
                        ui,
                        palette,
                        PillVariant::Accent,
                        "Start",
                        30.0,
                        78.0,
                        !snap.running,
                        Some(|p: &egui::Painter, r: Rect, c: Color32| {
                            icons::paint_play_triangle(p, r.center(), 10.0, c);
                        }),
                    );
                    if start_resp.clicked() {
                        let _ = core.start_tracking("");
                    }

                    let pause_variant = if snap.running && snap.paused {
                        PillVariant::Accent
                    } else {
                        PillVariant::Secondary
                    };
                    let pause_label = if snap.paused { "Resume" } else { "Pause" };
                    let pause_resp = widgets::pill_button_with_icon(
                        ui,
                        palette,
                        pause_variant,
                        pause_label,
                        30.0,
                        82.0,
                        snap.running,
                        Some(|p: &egui::Painter, r: Rect, c: Color32| {
                            if snap.paused {
                                icons::paint_play_triangle(p, r.center(), 10.0, c);
                            } else {
                                icons::paint_pause_bars(p, r.center(), 10.0, c);
                            }
                        }),
                    );
                    if pause_resp.clicked() {
                        let _ = core.toggle_pause();
                    }

                    let stop_enabled = snap.running;
                    let stop_resp = widgets::pill_button_with_icon(
                        ui,
                        palette,
                        PillVariant::Secondary,
                        "Stop & Report",
                        30.0,
                        118.0,
                        stop_enabled,
                        Some(|p: &egui::Painter, r: Rect, c: Color32| {
                            icons::paint_stop_square(p, r.center(), 10.0, c);
                        }),
                    );
                    if stop_resp.clicked() {
                        match core.stop_and_save_session() {
                            Ok(resp) => {
                                let name = resp.report.session_name.clone();
                                *modal_slot = Some(RootModalState::StopSaveSummary {
                                    resp,
                                    session_name_edit: name,
                                });
                            }
                            Err(err) => {
                                *modal_slot = Some(RootModalState::Alert {
                                    title: "Stop Session Error".into(),
                                    message: err,
                                    kind: super::modals::AlertKind::Error,
                                });
                            }
                        }
                    }
                });
            });
        });

    ui.add_space(8.0);

    // 4. Application usage section label
    ui.label(
        egui::RichText::new("Application usage")
            .font(font_regular(12.0))
            .color(palette.text_secondary),
    );
    ui.add_space(4.0);

    // Reserve height cleanly for footer card (42) + bottom bar (24) + gaps + bottom padding
    let reserve_bottom = 88.0;
    let list_h = (ui.available_height() - reserve_bottom).max(110.0);

    Frame::NONE
        .fill(palette.bg_card)
        .stroke(Stroke::new(1.0, palette.border))
        .corner_radius(CornerRadius::same(12))
        .inner_margin(Margin::symmetric(8, 8))
        .show(ui, |ui| {
            ui.set_width(ui.available_width());
            ui.set_height(list_h);

            if snap.apps.is_empty() {
                let empty_msg = if snap.running {
                    "Waiting for app activity..."
                } else {
                    "Click Start to begin tracking"
                };
                let avail = ui.available_size();
                ui.allocate_ui_with_layout(
                    avail,
                    Layout::centered_and_justified(egui::Direction::TopDown),
                    |ui| {
                        ui.label(
                            egui::RichText::new(empty_msg)
                                .font(font_regular(14.5))
                                .color(palette.text_secondary),
                        );
                    },
                );
            } else {
                ScrollArea::vertical()
                    .id_salt("main_apps_scroll")
                    .auto_shrink([false, false])
                    .show(ui, |ui| {
                        ui.spacing_mut().item_spacing.y = 2.0;
                        for app in &snap.apps {
                            render_app_row(
                                ui,
                                &ctx,
                                core,
                                palette,
                                snap,
                                tex_cache,
                                state,
                                app,
                                cmds,
                            );
                        }
                    });
            }
        });

    ui.add_space(8.0);

    // 5. Total session time card
    Frame::NONE
        .fill(palette.bg_card)
        .stroke(Stroke::new(1.0, palette.border))
        .corner_radius(CornerRadius::same(12))
        .inner_margin(Margin::symmetric(14, 10))
        .show(ui, |ui| {
            ui.set_width(ui.available_width());
            ui.horizontal(|ui| {
                ui.label(
                    egui::RichText::new("Total session time")
                        .font(font_regular(12.0))
                        .color(palette.text_muted),
                );
                ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                    ui.label(
                        egui::RichText::new(&snap.elapsed_formatted)
                            .font(font_bold(14.5))
                            .color(palette.total_val_color),
                    );
                });
            });
        });

    ui.add_space(6.0);

    // 6. Bottom developer / version bar
    ui.horizontal(|ui| {
        if snap.developer_mode {
            ui.spacing_mut().item_spacing.x = 12.0;

            let dbg_resp = ui
                .horizontal(|ui| {
                    ui.spacing_mut().item_spacing.x = 4.0;
                    let (ir, _) = ui.allocate_exact_size(vec2(13.0, 13.0), Sense::hover());
                    icons::paint_bug(
                        ui.painter(),
                        ir,
                        Color32::from_rgb(0xF4, 0x3F, 0x5E),
                    );
                    ui.label(
                        egui::RichText::new("Debug Console")
                            .font(font_regular(11.0))
                            .color(palette.text_secondary),
                    );
                })
                .response
                .interact(Sense::click())
                .on_hover_cursor(CursorIcon::PointingHand);
            if dbg_resp.clicked() {
                cmds.push(GuiCmd::OpenDebug);
            }

            let tst_resp = ui
                .horizontal(|ui| {
                    ui.spacing_mut().item_spacing.x = 3.0;
                    let (ir, _) = ui.allocate_exact_size(vec2(12.0, 12.0), Sense::hover());
                    icons::paint_lightning(
                        ui.painter(),
                        ir,
                        Color32::from_rgb(0xF5, 0x9E, 0x0B),
                    );
                    ui.label(
                        egui::RichText::new("Test Logs")
                            .font(font_regular(11.0))
                            .color(palette.text_secondary),
                    );
                })
                .response
                .interact(Sense::click())
                .on_hover_cursor(CursorIcon::PointingHand);
            if tst_resp.clicked() {
                let _ = core.emit_test_logs();
                cmds.push(GuiCmd::ShowToast("Emitted test debug logs".into()));
            }
        }

        ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
            ui.spacing_mut().item_spacing.x = 6.0;

            let (bug_r, mut bug_resp) = ui.allocate_exact_size(vec2(18.0, 18.0), Sense::click());
            bug_resp = bug_resp
                .on_hover_cursor(CursorIcon::PointingHand)
                .on_hover_text("Diagnostics & Bug Report");
            icons::paint_bug(
                ui.painter(),
                bug_r.shrink(2.0),
                if bug_resp.hovered() {
                    palette.text_primary
                } else {
                    palette.text_secondary
                },
            );
            if bug_resp.clicked() {
                *modal_slot = Some(RootModalState::Diagnostics);
            }

            let ver_resp = ui
                .add(
                    egui::Label::new(
                        egui::RichText::new("v5.0.0 · Build 2026.11.16")
                            .font(font_regular(11.0))
                            .color(palette.text_muted),
                    )
                    .sense(Sense::click()),
                )
                .on_hover_cursor(CursorIcon::PointingHand)
                .on_hover_text("TrueHour v5.0.0 (Local-Only)");
            if ver_resp.clicked() {
                let now = Instant::now();
                state
                    .version_clicks
                    .retain(|t| now.duration_since(*t).as_secs_f32() < 2.0);
                state.version_clicks.push(now);
                if state.version_clicks.len() >= 7 {
                    state.version_clicks.clear();
                    let next = core.set_developer_mode(!snap.developer_mode);
                    cmds.push(GuiCmd::ShowToast(if next.developer_mode {
                        "Developer Console unlocked".into()
                    } else {
                        "Developer Console hidden".into()
                    }));
                }
            }
        });
    });
}

#[allow(clippy::too_many_arguments)]
fn render_app_row(
    ui: &mut Ui,
    ctx: &egui::Context,
    core: &Arc<AppCore>,
    palette: &ThemePalette,
    snap: &TrackerUiSnapshot,
    tex_cache: &mut TextureCache,
    state: &mut MainWindowState,
    app: &TrackedAppRowSnapshot,
    cmds: &mut Vec<GuiCmd>,
) {
    let row_w = ui.available_width();
    let row_frame = Frame::NONE
        .corner_radius(CornerRadius::same(6))
        .inner_margin(Margin::symmetric(6, 4));

    let row_resp = row_frame.show(ui, |ui| {
        ui.allocate_ui_with_layout(
            vec2((row_w - 12.0).max(120.0), 26.0),
            Layout::left_to_right(Align::Center),
            |ui| {
                ui.spacing_mut().item_spacing.x = 7.0;

            let mut included = !app.excluded;
            if widgets::th_checkbox(ui, palette, &mut included).changed() {
                let _ = core.set_app_included(&app.name, included);
            }

            // App icon (18x18)
            if let Some(tex) = tex_cache.get_app_icon(ctx, core, &app.exe_path) {
                ui.add(egui::Image::new((tex.id(), vec2(18.0, 18.0))));
            } else {
                ui.allocate_exact_size(vec2(18.0, 18.0), Sense::hover());
            }

            // Right-side fixed allocation width: category pill (96) + spacing (10) + duration (72)
            let right_w = 96.0 + 10.0 + 72.0;
            let name_avail = (ui.available_width() - right_w - 6.0).max(50.0);

            ui.allocate_ui_with_layout(
                vec2(name_avail, 22.0),
                Layout::left_to_right(Align::Center),
                |ui| {
                    let name_color = if app.excluded {
                        palette.text_muted
                    } else {
                        palette.text_primary
                    };
                    let mut name_rt = egui::RichText::new(&app.name)
                        .font(font_regular(12.5))
                        .color(name_color);
                    if app.excluded {
                        name_rt = name_rt.strikethrough();
                    }
                    let lbl = ui.add(egui::Label::new(name_rt).truncate());
                    if !app.exe_path.is_empty() {
                        lbl.on_hover_text(&app.exe_path);
                    }
                    if app.is_distracting {
                        widgets::dark_badge_pill(
                            ui,
                            "Distraction",
                            Color32::from_rgba_unmultiplied(0xEF, 0x44, 0x44, 40),
                            palette.danger,
                        );
                    }
                },
            );

            ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                ui.spacing_mut().item_spacing.x = 10.0;

                // Duration on far right
                let dur_w = 72.0;
                ui.allocate_ui_with_layout(
                    vec2(dur_w, 22.0),
                    Layout::right_to_left(Align::Center),
                    |ui| {
                        let dur_col = if app.excluded {
                            palette.text_muted
                        } else {
                            palette.text_primary
                        };
                        ui.label(
                            egui::RichText::new(&app.formatted)
                                .font(font_semibold(12.0))
                                .color(dur_col),
                        );
                    },
                );

                // Category pill button
                let tag_label = if app.tag.is_empty() {
                    "Unassigned"
                } else {
                    app.tag.as_str()
                };
                let pill_resp = widgets::category_pill(ui, tag_label, &app.tag_color, 96.0);
                let pop_id = Id::unique(("cat_popup", &app.name));
                Popup::menu(&pill_resp)
                    .id(pop_id)
                    .close_behavior(PopupCloseBehavior::CloseOnClickOutside)
                    .show(|ui| {
                        ui.set_min_width(175.0);
                        ui.spacing_mut().item_spacing.y = 3.0;
                        let projects = if snap.available_projects.is_empty() {
                            vec!["Unassigned".to_string()]
                        } else {
                            snap.available_projects.clone()
                        };
                        for proj in &projects {
                            let selected = app.tag == *proj;
                            let hex = crate::report::project_color(proj);
                            let dot_col = parse_hex_color(hex, Color32::GRAY);
                            let item_resp = ui
                                .horizontal(|ui| {
                                    ui.spacing_mut().item_spacing.x = 7.0;
                                    let (dr, _) =
                                        ui.allocate_exact_size(vec2(10.0, 14.0), Sense::hover());
                                    ui.painter().circle_filled(dr.center(), 4.5, dot_col);
                                    ui.label(
                                        egui::RichText::new(proj)
                                            .font(if selected {
                                                font_bold(12.0)
                                            } else {
                                                font_regular(12.0)
                                            })
                                            .color(if selected {
                                                palette.accent
                                            } else {
                                                palette.text_primary
                                            }),
                                    );
                                })
                                .response
                                .interact(Sense::click())
                                .on_hover_cursor(CursorIcon::PointingHand);
                            if item_resp.clicked() {
                                let _ = core.set_app_tag(&app.name, proj);
                                Popup::close_all(ui.ctx());
                            }
                        }

                        widgets::horizontal_divider(ui, palette);

                        ui.horizontal(|ui| {
                            ui.spacing_mut().item_spacing.x = 5.0;
                            let inp = widgets::text_input_line(
                                ui,
                                palette,
                                &mut state.new_cat_draft,
                                "+ New category...",
                                115.0,
                                true,
                            );
                            let enter = inp.lost_focus()
                                && ui.input(|i| i.key_pressed(egui::Key::Enter));
                            if widgets::pill_button(
                                ui,
                                palette,
                                PillVariant::PrimaryBlue,
                                "Add",
                                24.0,
                                42.0,
                                true,
                            )
                            .clicked()
                                || enter
                            {
                                let val = state.new_cat_draft.trim().to_string();
                                if !val.is_empty() {
                                    let _ = core.add_project_category(&val);
                                    let _ = core.set_app_tag(&app.name, &val);
                                    state.new_cat_draft.clear();
                                    Popup::close_all(ui.ctx());
                                }
                            }
                        });

                        if widgets::pill_button(
                            ui,
                            palette,
                            PillVariant::Secondary,
                            "Manage Categories...",
                            25.0,
                            165.0,
                            true,
                        )
                        .clicked()
                        {
                            Popup::close_all(ui.ctx());
                            cmds.push(GuiCmd::OpenCategories);
                        }
                    });
            });
        });
    });

    // Subtle hover background + native egui context menu on right-click (NO browser menu!)
    let rect = row_resp.response.rect;
    let interact = ui.interact(
        rect,
        Id::unique(("app_row_ctx", &app.name)),
        Sense::click(),
    );
    Popup::context_menu(&interact)
        .close_behavior(PopupCloseBehavior::CloseOnClickOutside)
        .show(|ui| {
            ui.set_min_width(190.0);
            let inc_label = if app.excluded {
                "Include in Total"
            } else {
                "Exclude from Total"
            };
            if ui.button(inc_label).clicked() {
                let _ = core.set_app_included(&app.name, app.excluded);
                Popup::close_all(ui.ctx());
            }

            ui.menu_button("Change Category", |ui| {
                for proj in &snap.available_projects {
                    if ui.button(proj).clicked() {
                        let _ = core.set_app_tag(&app.name, proj);
                        Popup::close_all(ui.ctx());
                    }
                }
            });

            ui.separator();

            let dist_label = if app.is_distracting {
                "Remove Distraction Auto-Pause"
            } else {
                "Mark as Distraction (Auto-Pause)"
            };
            if ui.button(dist_label).clicked() {
                let _ = core.toggle_distraction_app(&app.name, &app.exe_path);
                Popup::close_all(ui.ctx());
            }

            if ui
                .add_enabled(
                    !app.exe_path.is_empty(),
                    egui::Button::new("Open File Location"),
                )
                .clicked()
            {
                if let Err(err) = core.reveal_app_executable(&app.exe_path) {
                    cmds.push(GuiCmd::ShowToast(err));
                }
                Popup::close_all(ui.ctx());
            }
        });
}
