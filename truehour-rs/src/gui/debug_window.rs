use super::theme::{font_bold, font_mono, font_regular, ThemePalette};
use super::widgets::{self, PillVariant};
use crate::AppCore;
use egui::{
    vec2, Align, Color32, CornerRadius, Frame, Layout, Margin, Panel, Pos2, ScrollArea, Stroke,
    Vec2, ViewportBuilder, ViewportCommand, ViewportId,
};
use std::sync::Arc;

pub struct DebugWindowState {
    pub open: bool,
    pub auto_scroll: bool,
    spawn_pos: Option<Pos2>,
    spawn_size: Option<Vec2>,
}

impl Default for DebugWindowState {
    fn default() -> Self {
        Self {
            open: false,
            auto_scroll: true,
            spawn_pos: None,
            spawn_size: None,
        }
    }
}

pub fn show_debug_viewport(
    ctx: &egui::Context,
    core: &Arc<AppCore>,
    palette: &ThemePalette,
    icon_data: &Option<Arc<egui::IconData>>,
    state: &mut DebugWindowState,
) {
    if !state.open {
        state.spawn_pos = None;
        state.spawn_size = None;
        return;
    }

    if state.spawn_size.is_none() {
        let (pos, sz) = widgets::centered_viewport_pos_and_size(ctx, vec2(640.0, 420.0));
        state.spawn_pos = pos;
        state.spawn_size = Some(sz);
    }
    let size = state.spawn_size.unwrap_or(vec2(640.0, 420.0));

    let vp_id = ViewportId::from_hash_of("debug_window");
    let mut builder = ViewportBuilder::default()
        .with_title("TrueHour Debug Console")
        .with_inner_size(size)
        .with_min_inner_size([480.0, 320.0])
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
        if render_debug_contents(ui, core, palette, state) {
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

pub(crate) fn render_debug_in_root(
    ui: &mut egui::Ui,
    core: &Arc<AppCore>,
    palette: &ThemePalette,
    state: &mut DebugWindowState,
) {
    let _ = render_debug_contents(ui, core, palette, state);
}

fn render_debug_contents(
    ui: &mut egui::Ui,
    core: &Arc<AppCore>,
    palette: &ThemePalette,
    state: &mut DebugWindowState,
) -> bool {
    let logs = core.get_debug_logs();
    let mut close_req = false;

    Panel::top("dbg_header")
            .frame(
                Frame::NONE
                    .fill(palette.bg_window)
                    .inner_margin(Margin::symmetric(14, 10)),
            )
            .show(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new("TrueHour Debug Console")
                            .font(font_bold(15.0))
                            .color(palette.text_primary),
                    );
                    ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                        ui.spacing_mut().item_spacing.x = 6.0;
                        if widgets::pill_button(
                            ui,
                            palette,
                            PillVariant::Secondary,
                            "Close",
                            26.0,
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
                            PillVariant::Secondary,
                            "Clear",
                            26.0,
                            58.0,
                            true,
                        )
                        .clicked()
                        {
                            core.clear_debug_logs();
                        }
                        if widgets::pill_button(
                            ui,
                            palette,
                            PillVariant::Secondary,
                            "Copy All",
                            26.0,
                            72.0,
                            !logs.is_empty(),
                        )
                        .clicked()
                        {
                            let all = logs
                                .iter()
                                .map(|e| format!("[{}] [{}] {}", e.timestamp, e.level, e.message))
                                .collect::<Vec<_>>()
                                .join("\n");
                            ui.ctx().copy_text(all);
                        }
                        if widgets::pill_button(
                            ui,
                            palette,
                            PillVariant::Secondary,
                            "Test Logs",
                            26.0,
                            76.0,
                            true,
                        )
                        .clicked()
                        {
                            let _ = core.emit_test_logs();
                        }
                        widgets::th_checkbox_label(
                            ui,
                            palette,
                            &mut state.auto_scroll,
                            "Auto-scroll",
                        );
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
                Frame::NONE
                    .fill(palette.bg_card)
                    .stroke(Stroke::new(1.0, palette.border))
                    .corner_radius(CornerRadius::same(8))
                    .inner_margin(Margin::same(10))
                    .show(ui, |ui| {
                        ui.set_min_size(ui.available_size());
                        ScrollArea::vertical()
                            .id_salt("dbg_logs_scroll")
                            .stick_to_bottom(state.auto_scroll)
                            .auto_shrink([false, false])
                            .show(ui, |ui| {
                                if logs.is_empty() {
                                    ui.label(
                                        egui::RichText::new("No runtime log entries yet.")
                                            .font(font_regular(12.0))
                                            .color(palette.text_muted),
                                    );
                                } else {
                                    for e in &logs {
                                        let upper = e.level.to_ascii_uppercase();
                                        let col = if upper.contains("ERR") {
                                            palette.danger
                                        } else if upper.contains("WARN") {
                                            Color32::from_rgb(0xF5, 0x9E, 0x0B)
                                        } else {
                                            palette.text_primary
                                        };
                                        ui.label(
                                            egui::RichText::new(format!(
                                                "[{}] [{}] {}",
                                                e.timestamp, upper, e.message
                                            ))
                                            .font(font_mono(11.5))
                                            .color(col),
                                        );
                                    }
                                }
                            });
                    });
            });

    close_req
}
