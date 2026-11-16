use super::icons;
use super::theme::{font_bold, font_regular, font_semibold, ThemePalette};
use super::widgets::{self, PillVariant};
use super::GuiCmd;
use crate::AppCore;
use egui::{
    vec2, Align, CornerRadius, CursorIcon, Frame, Layout, Margin, Pos2, Sense, Stroke, StrokeKind,
    Vec2, ViewportBuilder, ViewportCommand, ViewportId,
};
use std::sync::Arc;

pub struct AboutWindowState {
    pub open: bool,
    spawn_pos: Option<Pos2>,
    spawn_size: Option<Vec2>,
}

impl Default for AboutWindowState {
    fn default() -> Self {
        Self {
            open: false,
            spawn_pos: None,
            spawn_size: None,
        }
    }
}

pub fn show_about_viewport(
    ctx: &egui::Context,
    core: &Arc<AppCore>,
    palette: &ThemePalette,
    icon_data: &Option<Arc<egui::IconData>>,
    state: &mut AboutWindowState,
    cmds: &mut Vec<GuiCmd>,
) {
    if !state.open {
        state.spawn_pos = None;
        state.spawn_size = None;
        return;
    }

    if state.spawn_size.is_none() {
        let (pos, sz) = widgets::centered_viewport_pos_and_size(ctx, vec2(360.0, 310.0));
        state.spawn_pos = pos;
        state.spawn_size = Some(sz);
    }
    let size = state.spawn_size.unwrap_or(vec2(360.0, 310.0));

    let vp_id = ViewportId::from_hash_of("about_window");
    let mut builder = ViewportBuilder::default()
        .with_title("About TrueHour")
        .with_inner_size(size)
        .with_min_inner_size([360.0, 310.0])
        .with_resizable(false)
        .with_maximize_button(false);
    if let Some(pos) = state.spawn_pos {
        builder = builder.with_position(pos);
    }
    if let Some(ref ic) = icon_data {
        builder = builder.with_icon(Arc::clone(ic));
    }

    let mut close_req = false;
    let mut alert_msg: Option<String> = None;

    ctx.show_viewport_immediate(vp_id, builder, |ui, _class| {
        if ui.ctx().input(|i| i.viewport().close_requested())
            || ui.ctx().input(|i| i.key_pressed(egui::Key::Escape))
        {
            close_req = true;
        }
        let (cr, msg) = render_about_contents(ui, core, palette);
        if cr {
            close_req = true;
        }
        if msg.is_some() {
            alert_msg = msg;
        }
        if close_req {
            ui.ctx().send_viewport_cmd(ViewportCommand::Close);
        }
    });

    if let Some(err) = alert_msg {
        cmds.push(GuiCmd::ShowAlert {
            title: "Open Link Error".into(),
            message: err,
            kind: super::modals::AlertKind::Error,
        });
    }
    if close_req {
        state.open = false;
        state.spawn_pos = None;
        state.spawn_size = None;
    }
}

pub(crate) fn render_about_in_root(
    ui: &mut egui::Ui,
    core: &Arc<AppCore>,
    palette: &ThemePalette,
    _state: &mut AboutWindowState,
    cmds: &mut Vec<GuiCmd>,
) {
    let (_close, alert_msg) = render_about_contents(ui, core, palette);
    if let Some(err) = alert_msg {
        cmds.push(GuiCmd::ShowAlert {
            title: "Open Link Error".into(),
            message: err,
            kind: super::modals::AlertKind::Error,
        });
    }
}

fn render_about_contents(
    ui: &mut egui::Ui,
    core: &Arc<AppCore>,
    palette: &ThemePalette,
) -> (bool, Option<String>) {
    let mut close_req = false;
    let mut alert_msg: Option<String> = None;

    egui::CentralPanel::default()
            .frame(
                Frame::NONE
                    .fill(palette.bg_window)
                    .inner_margin(Margin::same(22)),
            )
            .show(ui, |ui| {
                ui.vertical_centered(|ui| {
                    ui.label(
                        egui::RichText::new("TrueHour")
                            .font(font_bold(22.0))
                            .color(palette.text_primary),
                    );
                    ui.add_space(4.0);
                    ui.label(
                        egui::RichText::new("Automated Time Tracker & Productivity Assistant")
                            .font(font_semibold(11.5))
                            .color(palette.text_secondary),
                    );
                    ui.add_space(12.0);
                    widgets::horizontal_divider(ui, palette);
                    ui.add_space(12.0);
                    ui.label(
                        egui::RichText::new("Version: 5.0.0")
                            .font(font_regular(12.5))
                            .color(palette.text_primary),
                    );
                    ui.add_space(3.0);
                    ui.label(
                        egui::RichText::new("Build: 5000 (2026.11.16)")
                            .font(font_regular(12.0))
                            .color(palette.text_secondary),
                    );
                    ui.add_space(18.0);

                    // Links row centered
                    ui.horizontal(|ui| {
                        let row_w = 34.0 + 12.0 + 132.0;
                        let pad = ((ui.available_width() - row_w) * 0.5).max(0.0);
                        ui.add_space(pad);
                        ui.spacing_mut().item_spacing.x = 12.0;

                        let (gh_r, mut gh_resp) =
                            ui.allocate_exact_size(vec2(34.0, 34.0), Sense::click());
                        gh_resp = gh_resp
                            .on_hover_cursor(CursorIcon::PointingHand)
                            .on_hover_text("Visit TrueHour on GitHub");
                        let bg = if gh_resp.hovered() {
                            palette.normal_btn_hover
                        } else {
                            palette.normal_btn_bg
                        };
                        ui.painter().rect(
                            gh_r,
                            CornerRadius::same(17),
                            bg,
                            Stroke::new(1.0, palette.normal_btn_border),
                            StrokeKind::Inside,
                        );
                        icons::paint_github_mark(
                            ui.painter(),
                            gh_r.center(),
                            10.0,
                            palette.text_primary,
                        );
                        if gh_resp.clicked() {
                            if let Err(e) =
                                core.open_external_url("https://mightyiest.github.io/TrueHour/")
                            {
                                alert_msg = Some(e);
                            }
                        }

                        if widgets::pill_button(
                            ui,
                            palette,
                            PillVariant::Secondary,
                            "Terms & Notices",
                            34.0,
                            132.0,
                            true,
                        )
                        .clicked()
                        {
                            if let Err(e) = core.open_legal_notices() {
                                alert_msg = Some(e);
                            }
                        }
                    });

                    ui.add_space(18.0);
                    ui.with_layout(Layout::bottom_up(Align::Center), |ui| {
                        let w = ui.available_width();
                        if widgets::pill_button(
                            ui,
                            palette,
                            PillVariant::Accent,
                            "Close",
                            34.0,
                            w,
                            true,
                        )
                        .clicked()
                        {
                            close_req = true;
                        }
                    });
                });
            });

    (close_req, alert_msg)
}
