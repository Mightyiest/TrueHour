use super::icons;
use super::theme::{font_bold, font_mono, font_regular, font_semibold, parse_hex_color, ThemePalette};
use super::widgets::{self, PillVariant};
use super::GuiCmd;
use crate::report::{format_duration, project_color, HeatmapDayDto, ProjectBreakdownEntry, TrendBarItem};
use crate::{AppCore, DashboardInsightsPayload};
use chrono::{Datelike, Duration as ChronoDuration, Local, NaiveDate};
use egui::epaint::{PathShape, PathStroke};
use egui::{
    pos2, vec2, Align, Color32, CornerRadius, Frame, Grid, Layout, Margin, Panel, Pos2, Rect,
    ScrollArea, Sense, Stroke, Vec2, ViewportBuilder, ViewportCommand, ViewportId,
};
use std::collections::HashMap;
use std::f32::consts::TAU;
use std::sync::atomic::Ordering;
use std::sync::Arc;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum DashTab {
    Live,
    History,
    Goals,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PeriodKey {
    Today,
    Week,
    Month,
}

impl PeriodKey {
    fn as_str(&self) -> &'static str {
        match self {
            Self::Today => "today",
            Self::Week => "week",
            Self::Month => "month",
        }
    }
}

pub struct DashboardWindowState {
    pub open: bool,
    pub tab: DashTab,
    pub period: PeriodKey,
    payload: Option<DashboardInsightsPayload>,
    goal_buf: String,
    last_loaded_period: Option<PeriodKey>,
    last_tracker_rev: u64,
    last_sessions_rev: u64,
    last_settings_rev: u64,
    spawn_pos: Option<Pos2>,
    spawn_size: Option<Vec2>,
}

impl Default for DashboardWindowState {
    fn default() -> Self {
        Self {
            open: false,
            tab: DashTab::Live,
            period: PeriodKey::Week,
            payload: None,
            goal_buf: "40.0".into(),
            last_loaded_period: None,
            last_tracker_rev: 0,
            last_sessions_rev: 0,
            last_settings_rev: 0,
            spawn_pos: None,
            spawn_size: None,
        }
    }
}

impl DashboardWindowState {
    pub fn mark_dirty(&mut self) {
        self.payload = None;
    }
}

pub fn show_dashboard_viewport(
    ctx: &egui::Context,
    core: &Arc<AppCore>,
    palette: &ThemePalette,
    icon_data: &Option<Arc<egui::IconData>>,
    state: &mut DashboardWindowState,
    cmds: &mut Vec<GuiCmd>,
) {
    if !state.open {
        state.spawn_pos = None;
        state.spawn_size = None;
        return;
    }

    ensure_dashboard_loaded(core, state);

    if state.spawn_size.is_none() {
        let (pos, sz) = widgets::centered_viewport_pos_and_size(ctx, vec2(840.0, 700.0));
        state.spawn_pos = pos;
        state.spawn_size = Some(sz);
    }
    let size = state.spawn_size.unwrap_or(vec2(840.0, 700.0));

    let vp_id = ViewportId::from_hash_of("dashboard_window");
    let mut builder = ViewportBuilder::default()
        .with_title("TrueHour Analytics Dashboard")
        .with_inner_size(size)
        .with_min_inner_size([720.0, 560.0])
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
        if render_dashboard_contents(ui, core, palette, state, cmds) {
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

pub(crate) fn render_dashboard_in_root(
    ui: &mut egui::Ui,
    core: &Arc<AppCore>,
    palette: &ThemePalette,
    state: &mut DashboardWindowState,
    cmds: &mut Vec<GuiCmd>,
) {
    ensure_dashboard_loaded(core, state);
    let _ = render_dashboard_contents(ui, core, palette, state, cmds);
}

fn ensure_dashboard_loaded(core: &Arc<AppCore>, state: &mut DashboardWindowState) {
    let t_rev = core.tracker_rev.load(Ordering::SeqCst);
    let s_rev = core.sessions_rev.load(Ordering::SeqCst);
    let st_rev = core.settings_rev.load(Ordering::SeqCst);

    if state.payload.is_none()
        || state.last_loaded_period != Some(state.period)
        || state.last_sessions_rev != s_rev
        || state.last_settings_rev != st_rev
        || (state.tab == DashTab::Live && state.last_tracker_rev != t_rev)
    {
        let p = core.get_dashboard_insights(state.period.as_str());
        if state.last_settings_rev != st_rev || state.payload.is_none() {
            state.goal_buf = format!("{:.1}", p.weekly_goal_hours.max(0.5));
        }
        state.payload = Some(p);
        state.last_loaded_period = Some(state.period);
        state.last_tracker_rev = t_rev;
        state.last_sessions_rev = s_rev;
        state.last_settings_rev = st_rev;
    }
}

fn render_dashboard_contents(
    ui: &mut egui::Ui,
    core: &Arc<AppCore>,
    palette: &ThemePalette,
    state: &mut DashboardWindowState,
    cmds: &mut Vec<GuiCmd>,
) -> bool {
    let mut close_req = false;

    Panel::top("dash_header")
            .frame(
                Frame::NONE
                    .fill(palette.bg_window)
                    .inner_margin(Margin::symmetric(16, 10)),
            )
            .show(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new("TrueHour Analytics Dashboard")
                            .font(font_bold(16.0))
                            .color(palette.text_primary),
                    );
                    ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                        ui.spacing_mut().item_spacing.x = 6.0;
                        if widgets::pill_button(
                            ui,
                            palette,
                            PillVariant::Secondary,
                            "Close",
                            28.0,
                            62.0,
                            true,
                        )
                        .clicked()
                        {
                            close_req = true;
                        }
                        if widgets::pill_button_with_icon(
                            ui,
                            palette,
                            PillVariant::Secondary,
                            "Refresh",
                            28.0,
                            82.0,
                            true,
                            Some(icons::paint_refresh),
                        )
                        .clicked()
                        {
                            state.mark_dirty();
                        }
                    });
                });
            });

        egui::CentralPanel::default()
            .frame(
                Frame::NONE
                    .fill(palette.bg_window)
                    .inner_margin(Margin {
                        left: 16,
                        right: 16,
                        top: 0,
                        bottom: 14,
                    }),
            )
            .show(ui, |ui| {
                ui.spacing_mut().item_spacing.y = 0.0;
                let tabs = [
                    (DashTab::Live, "Live Insights"),
                    (DashTab::History, "Historical Insights"),
                    (DashTab::Goals, "Weekly Focus Goals"),
                ];
                let active_tab_rect =
                    widgets::folder_tab_bar(ui, palette, &tabs, &mut state.tab, 126.0);

                let pane_h = ui.available_height().max(200.0);
                let pane_resp = Frame::NONE
                    .fill(palette.bg_card)
                    .stroke(Stroke::new(1.0, palette.border))
                    .corner_radius(CornerRadius {
                        nw: 0,
                        ne: 8,
                        sw: 8,
                        se: 8,
                    })
                    .inner_margin(Margin::same(14))
                    .show(ui, |ui| {
                        ui.set_width(ui.available_width());
                        ui.set_height(pane_h - 4.0);

                        ScrollArea::vertical()
                            .id_salt(("dash_scroll", state.tab))
                            .auto_shrink([false, false])
                            .show(ui, |ui| {
                                ui.spacing_mut().item_spacing.y = 10.0;
                                match state.tab {
                                    DashTab::Live => render_live_tab(ui, palette, state),
                                    DashTab::History => render_history_tab(ui, palette, state),
                                    DashTab::Goals => render_goals_tab(ui, core, palette, state, cmds),
                                }
                            });
                    });
                widgets::seamless_tab_join(ui, palette, active_tab_rect, pane_resp.response.rect);
            });

    close_req
}

fn render_live_tab(ui: &mut egui::Ui, palette: &ThemePalette, state: &DashboardWindowState) {
    let Some(ref p) = state.payload else {
        return;
    };
    let live = &p.live;
    let avail_w = ui.available_width();
    let kpi_w = ((avail_w - 16.0) / 3.0).max(120.0);

    ui.horizontal(|ui| {
        ui.spacing_mut().item_spacing.x = 8.0;
        widgets::kpi_card(
            ui,
            palette,
            "Total Elapsed",
            &live.elapsed_formatted,
            false,
            kpi_w,
        );
        widgets::kpi_card(
            ui,
            palette,
            "Counted Focus",
            &live.counted_formatted,
            false,
            kpi_w,
        );
        widgets::kpi_card(
            ui,
            palette,
            "Session Earned",
            &live.earned_display,
            true,
            kpi_w,
        );
    });

    widgets::group_box(ui, palette, "Session Status", |ui| {
        let sess = if live.session_name.trim().is_empty() {
            "No active session"
        } else {
            live.session_name.trim()
        };
        ui.label(
            egui::RichText::new(format!(
                "{sess}  ·  {}  ·  {}",
                live.status_text, live.integrity_status
            ))
            .font(font_regular(12.5))
            .color(palette.text_primary),
        );
    });

    widgets::group_box(ui, palette, "Live Project Allocation", |ui| {
        widgets::segmented_bar_allocations(ui, palette, &live.allocations);
    });

    widgets::group_box(ui, palette, "Live Application Breakdown", |ui| {
        if live.apps.is_empty() {
            ui.label(
                egui::RichText::new(
                    "Start tracking in the main window to see live application metrics.",
                )
                .font(font_regular(12.0))
                .color(palette.text_muted),
            );
        } else {
            Grid::new("dash_live_apps_grid")
                .num_columns(4)
                .spacing([20.0, 6.0])
                .striped(true)
                .show(ui, |ui| {
                    for h in ["Application", "Category", "Duration", "Share"] {
                        ui.label(
                            egui::RichText::new(h)
                                .font(font_semibold(11.5))
                                .color(palette.text_secondary),
                        );
                    }
                    ui.end_row();
                    for a in &live.apps {
                        let name_lbl = if a.excluded {
                            format!("{} (Excluded)", a.name)
                        } else {
                            a.name.clone()
                        };
                        ui.label(egui::RichText::new(name_lbl).font(font_regular(12.0)).color(
                            if a.excluded {
                                palette.text_muted
                            } else {
                                palette.text_primary
                            },
                        ));
                        let tag = if a.tag.is_empty() {
                            "Unassigned"
                        } else {
                            a.tag.as_str()
                        };
                        ui.horizontal(|ui| {
                            let col = parse_hex_color(&a.tag_color, Color32::GRAY);
                            let (dr, _) =
                                ui.allocate_exact_size(vec2(8.0, 12.0), Sense::hover());
                            ui.painter().circle_filled(dr.center(), 3.5, col);
                            ui.label(egui::RichText::new(tag).font(font_regular(12.0)));
                        });
                        ui.label(egui::RichText::new(&a.formatted).font(font_mono(11.5)));
                        ui.label(
                            egui::RichText::new(format!("{:.1}%", a.percent))
                                .font(font_mono(11.5)),
                        );
                        ui.end_row();
                    }
                });
        }
    });
}

fn render_history_tab(ui: &mut egui::Ui, palette: &ThemePalette, state: &mut DashboardWindowState) {
    let Some(ref p) = state.payload.clone() else {
        return;
    };
    let h = &p.history;

    ui.horizontal(|ui| {
        ui.spacing_mut().item_spacing.x = 6.0;
        for (pk, label) in [
            (PeriodKey::Today, "Today"),
            (PeriodKey::Week, "Last 7 Days"),
            (PeriodKey::Month, "This Month"),
        ] {
            if widgets::pill_button(
                ui,
                palette,
                if state.period == pk {
                    PillVariant::PrimaryBlue
                } else {
                    PillVariant::Secondary
                },
                label,
                28.0,
                96.0,
                true,
            )
            .clicked()
            {
                state.period = pk;
                state.mark_dirty();
            }
        }
        ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
            let s_txt = format!(
                "{} session{}",
                h.session_count,
                if h.session_count == 1 { "" } else { "s" }
            );
            ui.label(
                egui::RichText::new(s_txt)
                    .font(font_regular(12.0))
                    .color(palette.text_secondary),
            );
        });
    });

    let avail_w = ui.available_width();
    let kpi_w = ((avail_w - 16.0) / 3.0).max(120.0);
    ui.horizontal(|ui| {
        ui.spacing_mut().item_spacing.x = 8.0;
        widgets::kpi_card(ui, palette, "Total Time", &h.total_formatted, false, kpi_w);
        widgets::kpi_card(
            ui,
            palette,
            "Counted Focus",
            &h.counted_formatted,
            false,
            kpi_w,
        );
        widgets::kpi_card(
            ui,
            palette,
            "Estimated Earnings",
            &h.total_earned_display,
            true,
            kpi_w,
        );
    });

    // Donut + Daily Trend row
    let half_w = ((avail_w - 10.0) * 0.5).max(200.0);
    ui.horizontal(|ui| {
        ui.spacing_mut().item_spacing.x = 10.0;
        ui.allocate_ui(vec2(half_w, 190.0), |ui| {
            widgets::group_box(ui, palette, "Project Breakdown", |ui| {
                render_donut_chart(ui, palette, &h.project_breakdown);
            });
        });
        ui.allocate_ui(vec2(half_w, 190.0), |ui| {
            widgets::group_box(ui, palette, "Daily Activity Trend", |ui| {
                render_trend_chart(ui, palette, &h.daily_trend);
            });
        });
    });

    widgets::group_box(ui, palette, "365-Day Activity Heatmap", |ui| {
        render_heatmap(ui, palette, &p.heatmap);
    });

    widgets::group_box(ui, palette, "Historical Application Breakdown", |ui| {
        if h.apps.is_empty() {
            ui.label(
                egui::RichText::new("No saved application usage in this period.")
                    .font(font_regular(12.0))
                    .color(palette.text_muted),
            );
        } else {
            Grid::new("dash_hist_apps_grid")
                .num_columns(4)
                .spacing([20.0, 6.0])
                .striped(true)
                .show(ui, |ui| {
                    for col in ["Application", "Category", "Time", "Share"] {
                        ui.label(
                            egui::RichText::new(col)
                                .font(font_semibold(11.5))
                                .color(palette.text_secondary),
                        );
                    }
                    ui.end_row();
                    for a in h.apps.iter().take(50) {
                        let name_lbl = if a.excluded {
                            format!("{} (Excluded)", a.name)
                        } else {
                            a.name.clone()
                        };
                        ui.label(egui::RichText::new(name_lbl).font(font_regular(12.0)).color(
                            if a.excluded {
                                palette.text_muted
                            } else {
                                palette.text_primary
                            },
                        ));
                        let tag = if a.tag.is_empty() {
                            "Unassigned"
                        } else {
                            a.tag.as_str()
                        };
                        ui.horizontal(|ui| {
                            let col = parse_hex_color(project_color(tag), Color32::GRAY);
                            let (dr, _) =
                                ui.allocate_exact_size(vec2(8.0, 12.0), Sense::hover());
                            ui.painter().circle_filled(dr.center(), 3.5, col);
                            ui.label(egui::RichText::new(tag).font(font_regular(12.0)));
                        });
                        ui.label(egui::RichText::new(&a.formatted).font(font_mono(11.5)));
                        ui.label(
                            egui::RichText::new(format!("{:.1}%", a.percent))
                                .font(font_mono(11.5)),
                        );
                        ui.end_row();
                    }
                });
        }
    });
}

fn render_donut_chart(
    ui: &mut egui::Ui,
    palette: &ThemePalette,
    breakdown: &[ProjectBreakdownEntry],
) {
    ui.horizontal(|ui| {
        ui.spacing_mut().item_spacing.x = 14.0;
        let (rect, _) = ui.allocate_exact_size(vec2(104.0, 104.0), Sense::hover());
        let center = rect.center();
        let radius = 38.0;
        ui.painter()
            .circle_stroke(center, radius, Stroke::new(12.0, palette.bg_hover));

        let non_zero: Vec<&ProjectBreakdownEntry> =
            breakdown.iter().filter(|b| b.percent > 0.0).collect();
        if !non_zero.is_empty() {
            let mut angle = -std::f32::consts::FRAC_PI_2;
            for item in &non_zero {
                let sweep = ((item.percent as f32 / 100.0) * TAU).max(0.05);
                let steps = ((sweep * 20.0).ceil() as usize).max(4);
                let pts: Vec<Pos2> = (0..=steps)
                    .map(|i| {
                        let a = angle + sweep * (i as f32 / steps as f32);
                        center + vec2(a.cos(), a.sin()) * radius
                    })
                    .collect();
                let col = parse_hex_color(&item.color, Color32::GRAY);
                ui.painter().add(PathShape::line(pts, PathStroke::new(12.0, col)));
                angle += sweep;
            }
        }

        ui.vertical(|ui| {
            ui.spacing_mut().item_spacing.y = 4.0;
            if non_zero.is_empty() {
                ui.label(
                    egui::RichText::new("No project time in this period.")
                        .font(font_regular(12.0))
                        .color(palette.text_muted),
                );
            } else {
                for item in non_zero.iter().take(6) {
                    let col = parse_hex_color(&item.color, Color32::GRAY);
                    ui.horizontal(|ui| {
                        ui.spacing_mut().item_spacing.x = 6.0;
                        let (dr, _) = ui.allocate_exact_size(vec2(9.0, 14.0), Sense::hover());
                        ui.painter().circle_filled(dr.center(), 4.0, col);
                        ui.label(
                            egui::RichText::new(format!(
                                "{}  {:.0}%",
                                item.project, item.percent
                            ))
                            .font(font_regular(12.0))
                            .color(palette.text_primary),
                        );
                    });
                }
            }
        });
    });
}

fn render_trend_chart(ui: &mut egui::Ui, palette: &ThemePalette, bars: &[TrendBarItem]) {
    if bars.is_empty() {
        ui.label(
            egui::RichText::new("No activity trend data for this period.")
                .font(font_regular(12.0))
                .color(palette.text_muted),
        );
        return;
    }

    let w = ui.available_width().max(180.0);
    let h = 114.0;
    let (rect, _) = ui.allocate_exact_size(vec2(w, h), Sense::hover());

    let pad_l = 32.0;
    let pad_r = 8.0;
    let pad_t = 8.0;
    let pad_b = 18.0;
    let plot_w = (rect.width() - pad_l - pad_r).max(40.0);
    let plot_h = (rect.height() - pad_t - pad_b).max(30.0);
    let max_val = bars.iter().map(|b| b.value).fold(1.0_f64, f64::max);

    for frac in [0.0_f32, 0.5, 1.0] {
        let y = rect.top() + pad_t + plot_h * (1.0 - frac);
        ui.painter().line_segment(
            [pos2(rect.left() + pad_l, y), pos2(rect.right() - pad_r, y)],
            Stroke::new(1.0, palette.border),
        );
        ui.painter().text(
            pos2(rect.left() + pad_l - 4.0, y),
            egui::Align2::RIGHT_CENTER,
            format!("{:.1}h", max_val * frac as f64),
            font_regular(9.5),
            palette.text_muted,
        );
    }

    let slot_w = plot_w / (bars.len() as f32);
    let bar_w = (slot_w * 0.62).clamp(4.0, 26.0);
    let label_every = if bars.len() > 14 {
        bars.len().div_ceil(7)
    } else {
        1
    };

    for (i, b) in bars.iter().enumerate() {
        let bh = ((b.value / max_val) as f32 * plot_h).max(if b.value > 0.0 { 2.0 } else { 0.0 });
        let x = rect.left() + pad_l + (i as f32) * slot_w + (slot_w - bar_w) * 0.5;
        let y = rect.top() + pad_t + plot_h - bh;
        let bar_r = Rect::from_min_size(pos2(x, y), vec2(bar_w, bh));
        ui.painter()
            .rect_filled(bar_r, CornerRadius::same(2), palette.accent);

        if ui.rect_contains_pointer(bar_r.expand2(vec2(2.0, 6.0))) {
            let hint_id = egui::Id::unique(("trend_tip", i));
            egui::Tooltip::always_open(
                ui.ctx().clone(),
                ui.layer_id(),
                hint_id,
                bar_r.center_top(),
            )
            .show(|ui| {
                ui.label(format!("{}: {:.2} hrs", b.label, b.value));
            });
        }

        if i % label_every == 0 || i + 1 == bars.len() {
            ui.painter().text(
                pos2(x + bar_w * 0.5, rect.bottom() - 4.0),
                egui::Align2::CENTER_BOTTOM,
                &b.label,
                font_regular(9.5),
                palette.text_muted,
            );
        }
    }
}

fn render_heatmap(ui: &mut egui::Ui, palette: &ThemePalette, days: &[HeatmapDayDto]) {
    let mut by_date: HashMap<&str, (i64, i64)> = HashMap::new();
    for d in days {
        by_date.insert(d.date.as_str(), (d.total_seconds, d.session_count));
    }

    let today = Local::now().date_naive();
    let start_approx = today - ChronoDuration::days(364);
    let sunday_offset = start_approx.weekday().num_days_from_sunday() as i64;
    let start = start_approx - ChronoDuration::days(sunday_offset);
    let total_days = (today - start).num_days() + 1;
    let weeks = ((total_days + 6) / 7).max(52) as usize;

    let cell = 11.0;
    let gap = 3.0;
    let step = cell + gap;
    let w = weeks as f32 * step;
    let h = 7.0 * step - gap;

    ScrollArea::horizontal()
        .id_salt("dash_heatmap_scroll")
        .show(ui, |ui| {
            let (rect, _) = ui.allocate_exact_size(vec2(w, h), Sense::hover());
            let pointer = ui.input(|i| i.pointer.hover_pos());
            let mut hovered_info: Option<(Rect, String)> = None;

            let mut cursor: NaiveDate = start;
            let mut idx = 0usize;
            while cursor <= today {
                let col = idx / 7;
                let row = idx % 7;
                let iso = cursor.format("%Y-%m-%d").to_string();
                let (secs, cnt) = by_date.get(iso.as_str()).copied().unwrap_or((0, 0));
                let level = if secs == 0 {
                    0
                } else {
                    let hrs = secs as f64 / 3600.0;
                    if hrs >= 6.0 {
                        4
                    } else if hrs >= 3.0 {
                        3
                    } else if hrs >= 1.0 {
                        2
                    } else {
                        1
                    }
                };
                let cr = Rect::from_min_size(
                    pos2(
                        rect.left() + col as f32 * step,
                        rect.top() + row as f32 * step,
                    ),
                    vec2(cell, cell),
                );
                ui.painter()
                    .rect_filled(cr, CornerRadius::same(2), palette.heat[level]);
                if let Some(pt) = pointer {
                    if cr.contains(pt) {
                        let txt = if secs > 0 {
                            format!(
                                "{iso}: {} ({} session{})",
                                format_duration(secs),
                                cnt,
                                if cnt == 1 { "" } else { "s" }
                            )
                        } else {
                            format!("{iso}: No recorded sessions")
                        };
                        hovered_info = Some((cr, txt));
                    }
                }
                cursor += ChronoDuration::days(1);
                idx += 1;
            }

            if let Some((hr, txt)) = hovered_info {
                egui::Tooltip::always_open(
                    ui.ctx().clone(),
                    ui.layer_id(),
                    egui::Id::unique("heatmap_hover_tip"),
                    hr.center_top(),
                )
                .show(|ui| {
                    ui.label(txt);
                });
            }
        });
}

fn render_goals_tab(
    ui: &mut egui::Ui,
    core: &Arc<AppCore>,
    palette: &ThemePalette,
    state: &mut DashboardWindowState,
    cmds: &mut Vec<GuiCmd>,
) {
    let Some(ref p) = state.payload else {
        return;
    };
    let goal = p.weekly_goal_hours.max(0.5);
    let cur = p.current_week_hours.max(0.0);
    let pct = ((cur / goal) * 100.0).min(100.0);
    let remaining = (goal - cur).max(0.0);

    widgets::group_box(ui, palette, "This Week's Focus Progress", |ui| {
        ui.spacing_mut().item_spacing.y = 8.0;
        ui.label(
            egui::RichText::new(format!("{cur:.1}h / {goal:.1}h ({pct:.0}%)"))
                .font(font_bold(20.0))
                .color(palette.text_primary),
        );

        let w = ui.available_width().max(120.0);
        let (track, _) = ui.allocate_exact_size(vec2(w, 12.0), Sense::hover());
        ui.painter()
            .rect_filled(track, CornerRadius::same(6), palette.bg_hover);
        let fill_w = (w * (pct as f32 / 100.0)).max(if cur > 0.0 { 4.0 } else { 0.0 });
        if fill_w > 0.0 {
            let fill_r = Rect::from_min_size(track.min, vec2(fill_w, 12.0));
            ui.painter().rect_filled(
                fill_r,
                CornerRadius::same(6),
                if cur >= goal {
                    palette.green
                } else {
                    palette.accent
                },
            );
        }

        let status = if cur >= goal {
            format!(
                "Goal reached! You are {:.1}h ahead this week.",
                cur - goal
            )
        } else {
            format!(
                "{remaining:.1}h remaining to reach your {goal:.1}h weekly target."
            )
        };
        ui.label(
            egui::RichText::new(status)
                .font(font_regular(12.5))
                .color(palette.text_secondary),
        );
    });

    widgets::group_box(ui, palette, "Weekly Focus Target", |ui| {
        ui.horizontal(|ui| {
            ui.spacing_mut().item_spacing.x = 8.0;
            ui.label(
                egui::RichText::new("Target hours per week:")
                    .font(font_regular(12.5))
                    .color(palette.text_primary),
            );
            widgets::text_input_line(ui, palette, &mut state.goal_buf, "40.0", 80.0, true);
            ui.label(
                egui::RichText::new("hours")
                    .font(font_regular(12.0))
                    .color(palette.text_secondary),
            );
            if widgets::pill_button(
                ui,
                palette,
                PillVariant::PrimaryBlue,
                "Save Goal",
                28.0,
                92.0,
                true,
            )
            .clicked()
            {
                match state.goal_buf.trim().parse::<f64>() {
                    Ok(v) if v.is_finite() && (0.5..=168.0).contains(&v) => {
                        let saved = core.save_weekly_goal_hours(v);
                        state.mark_dirty();
                        cmds.push(GuiCmd::ShowToast(format!(
                            "Weekly goal saved ({saved:.1}h)"
                        )));
                    }
                    _ => {
                        cmds.push(GuiCmd::ShowToast(
                            "Enter a weekly target between 0.5 and 168 hours.".into(),
                        ));
                    }
                }
            }
        });
    });
}
