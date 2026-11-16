use super::icons;
use super::modals::AlertKind;
use super::theme::{font_bold, font_mono, font_regular, font_semibold, parse_hex_color, ThemePalette};
use super::widgets::{self, PillVariant};
use super::{AsyncTaskResult, GuiCmd, TextureCache};
use crate::file_dialog;
use crate::report::{project_color, SessionReportData};
use crate::AppCore;
use egui::{
    vec2, Align, Color32, CornerRadius, Frame, Grid, Id, Layout, Margin, Modal, Panel, Pos2,
    ScrollArea, Sense, Stroke, Vec2, ViewportBuilder, ViewportCommand, ViewportId,
};
use std::sync::mpsc::Sender;
use std::sync::Arc;

const PAGE_SIZE: usize = 50;

enum ReportModal {
    Alert {
        title: String,
        message: String,
        kind: AlertKind,
    },
    Rename(String),
    ConfirmTrash,
    ConfirmResumeWhileRunning,
}

pub struct ReportWindowState {
    pub open: bool,
    pub filepath: String,
    report: Option<SessionReportData>,
    error: Option<String>,
    loaded_path: String,
    timeline_page: usize,
    modal: Option<ReportModal>,
    spawn_pos: Option<Pos2>,
    spawn_size: Option<Vec2>,
}

impl Default for ReportWindowState {
    fn default() -> Self {
        Self {
            open: false,
            filepath: String::new(),
            report: None,
            error: None,
            loaded_path: String::new(),
            timeline_page: 1,
            modal: None,
            spawn_pos: None,
            spawn_size: None,
        }
    }
}

impl ReportWindowState {
    pub fn open_for(&mut self, filepath: String) {
        self.open = true;
        self.filepath = filepath;
        self.loaded_path.clear();
        self.report = None;
        self.error = None;
        self.timeline_page = 1;
        self.modal = None;
    }

    pub fn handle_async_result(&mut self, res: AsyncTaskResult, cmds: &mut Vec<GuiCmd>) {
        if let AsyncTaskResult::ExportReportSaved(r) = res {
            match r {
                Ok(true) => cmds.push(GuiCmd::ShowToast("Report exported to text file".into())),
                Ok(false) => {}
                Err(err) => {
                    self.modal = Some(ReportModal::Alert {
                        title: "Export Error".into(),
                        message: err,
                        kind: AlertKind::Error,
                    });
                }
            }
        }
    }
}

#[allow(clippy::too_many_arguments)]
pub fn show_report_viewport(
    ctx: &egui::Context,
    core: &Arc<AppCore>,
    palette: &ThemePalette,
    icon_data: &Option<Arc<egui::IconData>>,
    tex_cache: &mut TextureCache,
    task_tx: &Sender<AsyncTaskResult>,
    state: &mut ReportWindowState,
    cmds: &mut Vec<GuiCmd>,
) {
    if !state.open {
        state.spawn_pos = None;
        state.spawn_size = None;
        return;
    }

    ensure_report_loaded(core, state);

    if state.spawn_size.is_none() {
        let (pos, sz) = widgets::centered_viewport_pos_and_size(ctx, vec2(720.0, 680.0));
        state.spawn_pos = pos;
        state.spawn_size = Some(sz);
    }
    let size = state.spawn_size.unwrap_or(vec2(720.0, 680.0));

    let vp_id = ViewportId::from_hash_of("report_window");
    let mut builder = ViewportBuilder::default()
        .with_title("TrueHour — Session Report")
        .with_inner_size(size)
        .with_min_inner_size([600.0, 500.0])
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
        if render_report_contents(ui, core, palette, tex_cache, task_tx, state, cmds) {
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

#[allow(clippy::too_many_arguments)]
pub(crate) fn render_report_in_root(
    ui: &mut egui::Ui,
    core: &Arc<AppCore>,
    palette: &ThemePalette,
    tex_cache: &mut TextureCache,
    task_tx: &Sender<AsyncTaskResult>,
    state: &mut ReportWindowState,
    cmds: &mut Vec<GuiCmd>,
) {
    ensure_report_loaded(core, state);
    let _ = render_report_contents(ui, core, palette, tex_cache, task_tx, state, cmds);
}

fn ensure_report_loaded(core: &Arc<AppCore>, state: &mut ReportWindowState) {
    if !state.filepath.is_empty() && state.loaded_path != state.filepath {
        state.loaded_path = state.filepath.clone();
        match core.load_session_report_details(&state.filepath) {
            Ok(rep) => {
                state.report = Some(rep);
                state.error = None;
            }
            Err(err) => {
                state.report = None;
                state.error = Some(err);
            }
        }
    }
}

fn render_report_contents(
    ui: &mut egui::Ui,
    core: &Arc<AppCore>,
    palette: &ThemePalette,
    tex_cache: &mut TextureCache,
    task_tx: &Sender<AsyncTaskResult>,
    state: &mut ReportWindowState,
    cmds: &mut Vec<GuiCmd>,
) -> bool {
    let mut close_req = false;

    Panel::top("report_header")
            .frame(
                Frame::NONE
                    .fill(palette.bg_window)
                    .inner_margin(Margin::symmetric(14, 10)),
            )
            .show(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new("Session Report")
                            .font(font_bold(16.0))
                            .color(palette.text_primary),
                    );
                    let has_rep = state.report.is_some();
                    ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                        ui.spacing_mut().item_spacing.x = 6.0;
                        if widgets::pill_button(
                            ui,
                            palette,
                            PillVariant::Secondary,
                            "Close",
                            28.0,
                            58.0,
                            true,
                        )
                        .clicked()
                        {
                            close_req = true;
                        }
                        if widgets::pill_button(
                            ui,
                            palette,
                            PillVariant::DangerOutline,
                            "Move to Trash",
                            28.0,
                            96.0,
                            has_rep,
                        )
                        .clicked()
                        {
                            state.modal = Some(ReportModal::ConfirmTrash);
                        }
                        if widgets::pill_button(
                            ui,
                            palette,
                            PillVariant::PrimaryBlue,
                            "Open in Browser",
                            28.0,
                            116.0,
                            has_rep,
                        )
                        .clicked()
                        {
                            if let Err(err) =
                                core.open_session_report_in_browser(&state.filepath)
                            {
                                state.modal = Some(ReportModal::Alert {
                                    title: "Browser Preview Error".into(),
                                    message: err,
                                    kind: AlertKind::Error,
                                });
                            }
                        }
                        if widgets::pill_button(
                            ui,
                            palette,
                            PillVariant::Secondary,
                            "Export (.txt)",
                            28.0,
                            92.0,
                            has_rep,
                        )
                        .clicked()
                        {
                            if let Some(ref rep) = state.report {
                                let core_bg = Arc::clone(core);
                                let fp = state.filepath.clone();
                                let def_name =
                                    format!("report_{}.txt", rep.date.replace('-', ""));
                                let tx_bg = task_tx.clone();
                                let ctx_bg = ui.ctx().clone();
                                std::thread::spawn(move || {
                                    let picked = file_dialog::pick_save_file(
                                        "Export Session Report",
                                        &def_name,
                                        &[
                                            ("Text Files (*.txt)", "*.txt"),
                                            ("All Files (*.*)", "*.*"),
                                        ],
                                        "txt",
                                    );
                                    let out = match picked {
                                        Some(dest) => core_bg
                                            .export_session_report_txt_to(&fp, &dest)
                                            .map(|()| true),
                                        None => Ok(false),
                                    };
                                    let _ = tx_bg.send(AsyncTaskResult::ExportReportSaved(out));
                                    ctx_bg.request_repaint();
                                });
                            }
                        }
                        if widgets::pill_button_with_icon(
                            ui,
                            palette,
                            PillVariant::Accent,
                            "Resume",
                            28.0,
                            82.0,
                            has_rep,
                            Some(|p: &egui::Painter, r: egui::Rect, c: Color32| {
                                icons::paint_play_triangle(p, r.center(), 9.0, c);
                            }),
                        )
                        .clicked()
                        {
                            if core.tracker.is_running() {
                                state.modal = Some(ReportModal::ConfirmResumeWhileRunning);
                            } else {
                                match core.resume_saved_session(&state.filepath, false) {
                                    Ok(res) => {
                                        cmds.push(GuiCmd::FocusMain);
                                        cmds.push(GuiCmd::ShowResumedDialog(res.session_name));
                                        close_req = true;
                                    }
                                    Err(err) => {
                                        state.modal = Some(ReportModal::Alert {
                                            title: "Cannot Resume Session".into(),
                                            message: err,
                                            kind: AlertKind::Warn,
                                        });
                                    }
                                }
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
                        left: 14,
                        right: 14,
                        top: 0,
                        bottom: 14,
                    }),
            )
            .show(ui, |ui| {
                if let Some(ref err) = state.error {
                    ui.label(
                        egui::RichText::new(format!("Failed to load report: {err}"))
                            .font(font_regular(13.0))
                            .color(palette.danger),
                    );
                    return;
                }
                let Some(rep) = state.report.clone() else {
                    ui.label(
                        egui::RichText::new("No session selected.")
                            .font(font_regular(13.0))
                            .color(palette.text_secondary),
                    );
                    return;
                };

                ScrollArea::vertical()
                    .id_salt("report_body_scroll")
                    .auto_shrink([false, false])
                    .show(ui, |ui| {
                        ui.spacing_mut().item_spacing.y = 10.0;
                        let avail_w = ui.available_width();

                        // Meta Card
                        Frame::NONE
                            .fill(palette.bg_card)
                            .stroke(Stroke::new(1.0, palette.border))
                            .corner_radius(CornerRadius::same(10))
                            .inner_margin(Margin::same(12))
                            .show(ui, |ui| {
                                ui.set_width((avail_w - 24.0).max(200.0));
                                ui.horizontal(|ui| {
                                    ui.label(
                                        egui::RichText::new(&rep.session_name)
                                            .font(font_bold(15.5))
                                            .color(palette.text_primary),
                                    );
                                    if rep.is_resumed {
                                        widgets::dark_badge_pill(
                                            ui,
                                            "Resumed",
                                            palette.badge_latest_bg,
                                            palette.badge_latest_text,
                                        );
                                    }
                                    if rep.is_recovered {
                                        widgets::dark_badge_pill(
                                            ui,
                                            "Recovered",
                                            palette.badge_rel_bg,
                                            palette.badge_rel_text,
                                        );
                                    }
                                    ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                                        if widgets::pill_button(
                                            ui,
                                            palette,
                                            PillVariant::Secondary,
                                            "Rename",
                                            24.0,
                                            62.0,
                                            true,
                                        )
                                        .clicked()
                                        {
                                            state.modal = Some(ReportModal::Rename(
                                                rep.session_name.clone(),
                                            ));
                                        }
                                    });
                                });
                                ui.add_space(3.0);
                                let d = if rep.date_display.is_empty() {
                                    &rep.date
                                } else {
                                    &rep.date_display
                                };
                                let s = if rep.start_display.is_empty() {
                                    &rep.start
                                } else {
                                    &rep.start_display
                                };
                                let e = if rep.end_display.is_empty() {
                                    &rep.end
                                } else {
                                    &rep.end_display
                                };
                                ui.label(
                                    egui::RichText::new(format!("{d}  ·  {s} – {e}"))
                                        .font(font_regular(12.0))
                                        .color(palette.text_secondary),
                                );
                            });

                        // 3 KPI Cards
                        let kpi_w = ((avail_w - 16.0) / 3.0).max(120.0);
                        ui.horizontal(|ui| {
                            ui.spacing_mut().item_spacing.x = 8.0;
                            widgets::kpi_card(
                                ui,
                                palette,
                                "Total Time Tracked",
                                &rep.total_formatted,
                                false,
                                kpi_w,
                            );
                            widgets::kpi_card(
                                ui,
                                palette,
                                "Counted Work Time",
                                &rep.counted_formatted,
                                false,
                                kpi_w,
                            );
                            widgets::kpi_card(
                                ui,
                                palette,
                                "Total Earned",
                                &rep.total_earned_display,
                                true,
                                kpi_w,
                            );
                        });

                        // Project Allocation
                        widgets::group_box(ui, palette, "Project Allocation", |ui| {
                            widgets::segmented_bar_breakdown(ui, palette, &rep.project_breakdown);
                            if !rep.project_breakdown.is_empty() && rep.hourly_rate > 0.0 {
                                ui.add_space(6.0);
                                let line = rep
                                    .project_breakdown
                                    .iter()
                                    .map(|p| format!("{}: {}", p.project, p.earned_display))
                                    .collect::<Vec<_>>()
                                    .join("  ·  ");
                                ui.label(
                                    egui::RichText::new(line)
                                        .font(font_regular(11.5))
                                        .color(palette.text_muted),
                                );
                            }
                        });

                        // New Activity (Resumed Session)
                        if !rep.new_activity.is_empty() {
                            widgets::group_box(
                                ui,
                                palette,
                                "New Activity (Resumed Session)",
                                |ui| {
                                    Grid::new("report_new_activity_grid")
                                        .num_columns(5)
                                        .spacing([14.0, 6.0])
                                        .striped(true)
                                        .show(ui, |ui| {
                                            for h in [
                                                "Application",
                                                "Category",
                                                "Previous",
                                                "New Added",
                                                "Total",
                                            ] {
                                                ui.label(
                                                    egui::RichText::new(h)
                                                        .font(font_semibold(11.5))
                                                        .color(palette.text_secondary),
                                                );
                                            }
                                            ui.end_row();
                                            for na in &rep.new_activity {
                                                let name = na
                                                    .get("name")
                                                    .and_then(|v| v.as_str())
                                                    .unwrap_or("");
                                                let tag = na
                                                    .get("tag")
                                                    .and_then(|v| v.as_str())
                                                    .unwrap_or("Unassigned");
                                                let prev_f = na
                                                    .get("previous_formatted")
                                                    .and_then(|v| v.as_str())
                                                    .unwrap_or("—");
                                                let new_f = na
                                                    .get("new_formatted")
                                                    .and_then(|v| v.as_str())
                                                    .unwrap_or("—");
                                                let tot_f = na
                                                    .get("total_formatted")
                                                    .and_then(|v| v.as_str())
                                                    .unwrap_or("—");
                                                ui.label(
                                                    egui::RichText::new(name)
                                                        .font(font_regular(12.0)),
                                                );
                                                ui.horizontal(|ui| {
                                                    let col = parse_hex_color(
                                                        project_color(tag),
                                                        Color32::GRAY,
                                                    );
                                                    let (dr, _) = ui.allocate_exact_size(
                                                        vec2(8.0, 12.0),
                                                        Sense::hover(),
                                                    );
                                                    ui.painter().circle_filled(dr.center(), 3.5, col);
                                                    ui.label(
                                                        egui::RichText::new(tag)
                                                            .font(font_regular(12.0)),
                                                    );
                                                });
                                                ui.label(
                                                    egui::RichText::new(prev_f)
                                                        .font(font_mono(11.5)),
                                                );
                                                ui.label(
                                                    egui::RichText::new(new_f)
                                                        .font(font_mono(11.5))
                                                        .color(palette.green),
                                                );
                                                ui.label(
                                                    egui::RichText::new(tot_f)
                                                        .font(font_mono(11.5)),
                                                );
                                                ui.end_row();
                                            }
                                        });
                                },
                            );
                        }

                        // Application Usage Table
                        widgets::group_box(ui, palette, "Application Usage", |ui| {
                            if rep.apps.is_empty() {
                                ui.label(
                                    egui::RichText::new("No applications recorded.")
                                        .font(font_regular(12.0))
                                        .color(palette.text_muted),
                                );
                            } else {
                                let mut sorted = rep.apps.clone();
                                sorted.sort_by(|a, b| b.seconds.cmp(&a.seconds));
                                Grid::new("report_apps_grid")
                                    .num_columns(4)
                                    .spacing([18.0, 6.0])
                                    .striped(true)
                                    .show(ui, |ui| {
                                        for h in ["Application", "Category", "Time", "Share"] {
                                            ui.label(
                                                egui::RichText::new(h)
                                                    .font(font_semibold(11.5))
                                                    .color(palette.text_secondary),
                                            );
                                        }
                                        ui.end_row();
                                        for a in &sorted {
                                            let exe = rep
                                                .app_exe_paths
                                                .get(&a.name)
                                                .map(String::as_str)
                                                .unwrap_or("");
                                            ui.horizontal(|ui| {
                                                ui.spacing_mut().item_spacing.x = 6.0;
                                                if let Some(tex) =
                                                    tex_cache.get_app_icon(ui.ctx(), core, exe)
                                                {
                                                    ui.add(egui::Image::new((
                                                        tex.id(),
                                                        vec2(16.0, 16.0),
                                                    )));
                                                }
                                                let lbl = if a.excluded {
                                                    format!("{} (Excluded)", a.name)
                                                } else {
                                                    a.name.clone()
                                                };
                                                ui.label(egui::RichText::new(lbl).font(
                                                    font_regular(12.0),
                                                ).color(if a.excluded {
                                                    palette.text_muted
                                                } else {
                                                    palette.text_primary
                                                }));
                                            });
                                            let tag = if a.tag.is_empty() {
                                                "Unassigned"
                                            } else {
                                                a.tag.as_str()
                                            };
                                            ui.horizontal(|ui| {
                                                let col = parse_hex_color(
                                                    project_color(tag),
                                                    Color32::GRAY,
                                                );
                                                let (dr, _) = ui.allocate_exact_size(
                                                    vec2(8.0, 12.0),
                                                    Sense::hover(),
                                                );
                                                ui.painter().circle_filled(dr.center(), 3.5, col);
                                                ui.label(
                                                    egui::RichText::new(tag)
                                                        .font(font_regular(12.0)),
                                                );
                                            });
                                            ui.label(
                                                egui::RichText::new(&a.formatted)
                                                    .font(font_mono(11.5)),
                                            );
                                            ui.label(
                                                egui::RichText::new(format!(
                                                    "{:.1}%",
                                                    a.percent
                                                ))
                                                .font(font_mono(11.5)),
                                            );
                                            ui.end_row();
                                        }
                                    });
                            }
                        });

                        // Paginated Timeline Log
                        widgets::group_box(
                            ui,
                            palette,
                            &format!("Timeline Log ({})", rep.timeline.len()),
                            |ui| {
                                if rep.timeline.is_empty() {
                                    ui.label(
                                        egui::RichText::new("No timeline entries recorded.")
                                            .font(font_regular(12.0))
                                            .color(palette.text_muted),
                                    );
                                } else {
                                    let total_pages =
                                        rep.timeline.len().div_ceil(PAGE_SIZE).max(1);
                                    state.timeline_page =
                                        state.timeline_page.clamp(1, total_pages);
                                    let start = (state.timeline_page - 1) * PAGE_SIZE;
                                    let end = (start + PAGE_SIZE).min(rep.timeline.len());

                                    Grid::new("report_tl_grid")
                                        .num_columns(2)
                                        .spacing([20.0, 5.0])
                                        .striped(true)
                                        .show(ui, |ui| {
                                            ui.label(
                                                egui::RichText::new("Time Window")
                                                    .font(font_semibold(11.5))
                                                    .color(palette.text_secondary),
                                            );
                                            ui.label(
                                                egui::RichText::new("Application")
                                                    .font(font_semibold(11.5))
                                                    .color(palette.text_secondary),
                                            );
                                            ui.end_row();
                                            for entry in &rep.timeline[start..end] {
                                                ui.label(
                                                    egui::RichText::new(format!(
                                                        "{} – {}",
                                                        entry.start, entry.end
                                                    ))
                                                    .font(font_mono(11.5)),
                                                );
                                                ui.label(
                                                    egui::RichText::new(&entry.app)
                                                        .font(font_regular(12.0)),
                                                );
                                                ui.end_row();
                                            }
                                        });

                                    ui.add_space(8.0);
                                    ui.horizontal(|ui| {
                                        ui.label(
                                            egui::RichText::new(format!(
                                                "Page {} of {} ({} entries)",
                                                state.timeline_page,
                                                total_pages,
                                                rep.timeline.len()
                                            ))
                                            .font(font_regular(11.5))
                                            .color(palette.text_secondary),
                                        );
                                        ui.with_layout(
                                            Layout::right_to_left(Align::Center),
                                            |ui| {
                                                ui.spacing_mut().item_spacing.x = 6.0;
                                                if widgets::pill_button(
                                                    ui,
                                                    palette,
                                                    PillVariant::Secondary,
                                                    "Next",
                                                    24.0,
                                                    54.0,
                                                    state.timeline_page < total_pages,
                                                )
                                                .clicked()
                                                {
                                                    state.timeline_page += 1;
                                                }
                                                if widgets::pill_button(
                                                    ui,
                                                    palette,
                                                    PillVariant::Secondary,
                                                    "Prev",
                                                    24.0,
                                                    54.0,
                                                    state.timeline_page > 1,
                                                )
                                                .clicked()
                                                {
                                                    state.timeline_page -= 1;
                                                }
                                            },
                                        );
                                    });
                                }
                            },
                        );
                    });
            });

        render_report_modal(
            ui.ctx(),
            core,
            palette,
            state,
            cmds,
            &mut close_req,
        );

    close_req
}

fn render_report_modal(
    ctx: &egui::Context,
    core: &Arc<AppCore>,
    palette: &ThemePalette,
    state: &mut ReportWindowState,
    cmds: &mut Vec<GuiCmd>,
    close_req: &mut bool,
) {
    let Some(mut modal) = state.modal.take() else {
        return;
    };
    let mut keep = true;
    let card_frame = Frame::NONE
        .fill(palette.bg_card)
        .stroke(Stroke::new(1.0, palette.border_strong))
        .corner_radius(CornerRadius::same(12))
        .inner_margin(Margin::same(16));

    let resp = Modal::new(Id::unique("report_modal"))
        .backdrop_color(Color32::from_black_alpha(150))
        .frame(card_frame)
        .show(ctx, |ui| {
            let inner_w = widgets::modal_inner_width(ctx, 340.0, 16);
            ui.set_width(inner_w);
            ui.set_max_width(inner_w);
            match &mut modal {
            ReportModal::Alert {
                title,
                message,
                kind,
            } => {
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
                ui.add_space(12.0);
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
                        keep = false;
                    }
                });
            }
            ReportModal::Rename(name_buf) => {
                ui.label(
                    egui::RichText::new("Rename Session")
                        .font(font_bold(15.0))
                        .color(palette.text_primary),
                );
                ui.add_space(6.0);
                widgets::text_input_line(ui, palette, name_buf, "Session name", inner_w, true);
                ui.add_space(12.0);
                widgets::modal_action_row(ui, inner_w, 28.0, |ui| {
                    if widgets::pill_button(
                        ui,
                        palette,
                        PillVariant::PrimaryBlue,
                        "Save",
                        28.0,
                        72.0,
                        true,
                    )
                    .clicked()
                    {
                        let trimmed = name_buf.trim().to_string();
                        if !trimmed.is_empty() {
                            match core.rename_saved_session(&state.filepath, &trimmed) {
                                Ok(_) => {
                                    state.loaded_path.clear();
                                    keep = false;
                                }
                                Err(err) => cmds.push(GuiCmd::ShowToast(err)),
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
                        keep = false;
                    }
                });
            }
            ReportModal::ConfirmTrash => {
                ui.label(
                    egui::RichText::new("Move to Trash")
                        .font(font_bold(15.0))
                        .color(palette.text_primary),
                );
                ui.add_space(8.0);
                ui.add(
                    egui::Label::new(
                        egui::RichText::new("Move this saved session report to Trash?")
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
                        "Move to Trash",
                        28.0,
                        104.0,
                        true,
                    )
                    .clicked()
                    {
                        if core.trash_saved_session(&state.filepath).is_ok() {
                            cmds.push(GuiCmd::ShowToast("Session moved to Trash".into()));
                            keep = false;
                            *close_req = true;
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
                        keep = false;
                    }
                });
            }
            ReportModal::ConfirmResumeWhileRunning => {
                ui.label(
                    egui::RichText::new("Session Currently Running")
                        .font(font_bold(15.0))
                        .color(palette.text_primary),
                );
                ui.add_space(8.0);
                ui.add(
                    egui::Label::new(
                        egui::RichText::new(
                            "A session is currently running. Stop and autosave it, then resume this session?",
                        )
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
                        PillVariant::PrimaryBlue,
                        "Stop & Resume",
                        28.0,
                        114.0,
                        true,
                    )
                    .clicked()
                    {
                        match core.resume_saved_session(&state.filepath, true) {
                            Ok(res) => {
                                cmds.push(GuiCmd::FocusMain);
                                cmds.push(GuiCmd::ShowResumedDialog(res.session_name));
                                keep = false;
                                *close_req = true;
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
                        keep = false;
                    }
                });
            }
            }
        });
    if resp.should_close() {
        keep = false;
    }
    if keep && state.modal.is_none() {
        state.modal = Some(modal);
    }
}
