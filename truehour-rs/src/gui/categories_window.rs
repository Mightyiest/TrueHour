use super::icons;
use super::theme::{font_bold, font_regular, font_semibold, parse_hex_color, ThemePalette};
use super::widgets::{self, PillVariant};
use super::{GuiCmd, TextureCache};
use crate::{AppCore, CategoriesOverviewDto};
use egui::{
    vec2, Align, Color32, ComboBox, CornerRadius, CursorIcon, Frame, Id, Layout, Margin, Modal,
    Panel, Pos2, ScrollArea, Sense, Stroke, StrokeKind, Vec2, ViewportBuilder, ViewportCommand,
    ViewportId,
};
use std::sync::atomic::Ordering;
use std::sync::Arc;

pub struct CategoriesWindowState {
    pub open: bool,
    overview: Option<CategoriesOverviewDto>,
    last_cat_rev: u64,
    selected_category: String,
    cat_search: String,
    app_search: String,
    new_cat_name: String,
    new_app_name: String,
    new_app_cat: String,
    confirm_delete_cat: Option<String>,
    spawn_pos: Option<Pos2>,
    spawn_size: Option<Vec2>,
}

impl Default for CategoriesWindowState {
    fn default() -> Self {
        Self {
            open: false,
            overview: None,
            last_cat_rev: 0,
            selected_category: "__ALL__".into(),
            cat_search: String::new(),
            app_search: String::new(),
            new_cat_name: String::new(),
            new_app_name: String::new(),
            new_app_cat: "Unassigned".into(),
            confirm_delete_cat: None,
            spawn_pos: None,
            spawn_size: None,
        }
    }
}

impl CategoriesWindowState {
    pub fn mark_dirty(&mut self) {
        self.overview = None;
    }
}

pub fn show_categories_viewport(
    ctx: &egui::Context,
    core: &Arc<AppCore>,
    palette: &ThemePalette,
    icon_data: &Option<Arc<egui::IconData>>,
    tex_cache: &mut TextureCache,
    state: &mut CategoriesWindowState,
    cmds: &mut Vec<GuiCmd>,
) {
    if !state.open {
        state.spawn_pos = None;
        state.spawn_size = None;
        return;
    }

    ensure_categories_loaded(core, state);

    if state.spawn_size.is_none() {
        let (pos, sz) = widgets::centered_viewport_pos_and_size(ctx, vec2(940.0, 620.0));
        state.spawn_pos = pos;
        state.spawn_size = Some(sz);
    }
    let size = state.spawn_size.unwrap_or(vec2(940.0, 620.0));

    let vp_id = ViewportId::from_hash_of("categories_window");
    let mut builder = ViewportBuilder::default()
        .with_title("Categories & Assigned Applications")
        .with_inner_size(size)
        .with_min_inner_size([720.0, 480.0])
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
        if render_categories_contents(ui, core, palette, tex_cache, state, cmds) {
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

pub(crate) fn render_categories_in_root(
    ui: &mut egui::Ui,
    core: &Arc<AppCore>,
    palette: &ThemePalette,
    tex_cache: &mut TextureCache,
    state: &mut CategoriesWindowState,
    cmds: &mut Vec<GuiCmd>,
) {
    ensure_categories_loaded(core, state);
    let _ = render_categories_contents(ui, core, palette, tex_cache, state, cmds);
}

fn ensure_categories_loaded(core: &Arc<AppCore>, state: &mut CategoriesWindowState) {
    let rev = core.categories_rev.load(Ordering::SeqCst);
    if state.overview.is_none() || state.last_cat_rev != rev {
        let ov = core.get_categories_overview();
        if state.selected_category != "__ALL__"
            && !ov
                .categories
                .iter()
                .any(|c| c.name == state.selected_category)
        {
            state.selected_category = "__ALL__".into();
        }
        if !ov.available_projects.contains(&state.new_app_cat) {
            state.new_app_cat = ov
                .available_projects
                .first()
                .cloned()
                .unwrap_or_else(|| "Unassigned".into());
        }
        state.overview = Some(ov);
        state.last_cat_rev = rev;
    }
}

fn render_categories_contents(
    ui: &mut egui::Ui,
    core: &Arc<AppCore>,
    palette: &ThemePalette,
    tex_cache: &mut TextureCache,
    state: &mut CategoriesWindowState,
    cmds: &mut Vec<GuiCmd>,
) -> bool {
    let mut close_req = false;

    Panel::top("cat_header")
            .frame(
                Frame::NONE
                    .fill(palette.bg_window)
                    .inner_margin(Margin::symmetric(14, 10)),
            )
            .show(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new("Categories & Assigned Applications")
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

        let Some(ov) = state.overview.clone() else {
            return close_req;
        };

        // Left sidebar
        Panel::left("cat_sidebar")
            .exact_size(270.0)
            .frame(
                Frame::NONE
                    .fill(palette.bg_window)
                    .inner_margin(Margin {
                        left: 14,
                        right: 8,
                        top: 2,
                        bottom: 14,
                    }),
            )
            .show(ui, |ui| {
                Frame::NONE
                    .fill(palette.bg_card)
                    .stroke(Stroke::new(1.0, palette.border))
                    .corner_radius(CornerRadius::same(10))
                    .inner_margin(Margin::same(10))
                    .show(ui, |ui| {
                        ui.set_min_size(ui.available_size());
                        ui.spacing_mut().item_spacing.y = 8.0;

                        widgets::text_input_line(
                            ui,
                            palette,
                            &mut state.cat_search,
                            "Filter categories...",
                            ui.available_width(),
                            true,
                        );

                        let list_h = (ui.available_height() - 42.0).max(120.0);
                        ScrollArea::vertical()
                            .id_salt("cat_nav_scroll")
                            .max_height(list_h)
                            .auto_shrink([false, false])
                            .show(ui, |ui| {
                                ui.spacing_mut().item_spacing.y = 4.0;
                                let q = state.cat_search.trim().to_lowercase();

                                if q.is_empty() || "all assigned apps".contains(&q) {
                                    let active = state.selected_category == "__ALL__";
                                    if cat_nav_row(
                                        ui,
                                        palette,
                                        None,
                                        "All Assigned Apps",
                                        ov.apps.len(),
                                        active,
                                        false,
                                    )
                                    .0
                                    {
                                        state.selected_category = "__ALL__".into();
                                    }
                                }

                                for c in &ov.categories {
                                    if !q.is_empty() && !c.name.to_lowercase().contains(&q) {
                                        continue;
                                    }
                                    let active = state.selected_category == c.name;
                                    let col = parse_hex_color(&c.color, Color32::GRAY);
                                    let (clicked, del_clicked) = cat_nav_row(
                                        ui,
                                        palette,
                                        Some(col),
                                        &c.name,
                                        c.count,
                                        active,
                                        !c.is_builtin,
                                    );
                                    if del_clicked {
                                        state.confirm_delete_cat = Some(c.name.clone());
                                    } else if clicked {
                                        state.selected_category = c.name.clone();
                                        state.new_app_cat = c.name.clone();
                                    }
                                }
                            });

                        ui.horizontal(|ui| {
                            ui.spacing_mut().item_spacing.x = 6.0;
                            let add_w = 62.0;
                            let inp_w = (ui.available_width() - add_w - 6.0).max(80.0);
                            let r = widgets::text_input_line(
                                ui,
                                palette,
                                &mut state.new_cat_name,
                                "New category name...",
                                inp_w,
                                true,
                            );
                            let enter =
                                r.lost_focus() && ui.input(|i| i.key_pressed(egui::Key::Enter));
                            if widgets::pill_button(
                                ui,
                                palette,
                                PillVariant::PrimaryBlue,
                                "+ Add",
                                28.0,
                                add_w,
                                true,
                            )
                            .clicked()
                                || enter
                            {
                                let name = state.new_cat_name.trim().to_string();
                                if !name.is_empty() {
                                    match core.add_project_category(&name) {
                                        Ok(_) => {
                                            state.new_cat_name.clear();
                                            state.selected_category = name.clone();
                                            state.mark_dirty();
                                            cmds.push(GuiCmd::ShowToast(format!(
                                                "Added category \"{name}\""
                                            )));
                                        }
                                        Err(err) => cmds.push(GuiCmd::ShowToast(err)),
                                    }
                                }
                            }
                        });
                    });
            });

        // Right main panel
        egui::CentralPanel::default()
            .frame(
                Frame::NONE
                    .fill(palette.bg_window)
                    .inner_margin(Margin {
                        left: 4,
                        right: 14,
                        top: 2,
                        bottom: 14,
                    }),
            )
            .show(ui, |ui| {
                Frame::NONE
                    .fill(palette.bg_card)
                    .stroke(Stroke::new(1.0, palette.border))
                    .corner_radius(CornerRadius::same(10))
                    .inner_margin(Margin::same(12))
                    .show(ui, |ui| {
                        ui.set_min_size(ui.available_size());
                        ui.spacing_mut().item_spacing.y = 8.0;

                        let app_q = state.app_search.trim().to_lowercase();
                        let filtered: Vec<_> = ov
                            .apps
                            .iter()
                            .filter(|a| {
                                (state.selected_category == "__ALL__"
                                    || a.tag == state.selected_category)
                                    && (app_q.is_empty()
                                        || a.app_name.to_lowercase().contains(&app_q))
                            })
                            .collect();

                        ui.horizontal(|ui| {
                            let panel_title = if state.selected_category == "__ALL__" {
                                format!("All Assigned Apps ({})", filtered.len())
                            } else {
                                format!("{} ({})", state.selected_category, filtered.len())
                            };
                            ui.label(
                                egui::RichText::new(panel_title)
                                    .font(font_bold(14.5))
                                    .color(palette.text_primary),
                            );
                            ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                                widgets::text_input_line(
                                    ui,
                                    palette,
                                    &mut state.app_search,
                                    "Search applications...",
                                    230.0,
                                    true,
                                );
                            });
                        });

                        // Quick assign bar
                        ui.horizontal(|ui| {
                            ui.spacing_mut().item_spacing.x = 6.0;
                            let combo_w = 148.0;
                            let btn_w = 104.0;
                            let inp_w =
                                (ui.available_width() - combo_w - btn_w - 14.0).max(120.0);
                            widgets::text_input_line(
                                ui,
                                palette,
                                &mut state.new_app_name,
                                "Add application name (e.g. code.exe / Figma)...",
                                inp_w,
                                true,
                            );
                            ComboBox::from_id_salt("cat_quick_assign_combo")
                                .width(combo_w)
                                .selected_text(&state.new_app_cat)
                                .show_ui(ui, |ui| {
                                    for p in &ov.available_projects {
                                        ui.selectable_value(
                                            &mut state.new_app_cat,
                                            p.clone(),
                                            p,
                                        );
                                    }
                                });
                            if widgets::pill_button(
                                ui,
                                palette,
                                PillVariant::PrimaryBlue,
                                "+ Assign App",
                                28.0,
                                btn_w,
                                true,
                            )
                            .clicked()
                            {
                                let app_name = state.new_app_name.trim().to_string();
                                if !app_name.is_empty() {
                                    let tag = state.new_app_cat.clone();
                                    let _ = core.set_app_tag(&app_name, &tag);
                                    state.new_app_name.clear();
                                    state.mark_dirty();
                                    cmds.push(GuiCmd::ShowToast(format!(
                                        "Assigned \"{app_name}\" to {tag}"
                                    )));
                                }
                            }
                        });

                        widgets::horizontal_divider(ui, palette);

                        ScrollArea::vertical()
                            .id_salt("cat_apps_scroll")
                            .auto_shrink([false, false])
                            .show(ui, |ui| {
                                ui.spacing_mut().item_spacing.y = 4.0;
                                if filtered.is_empty() {
                                    ui.add_space(40.0);
                                    ui.vertical_centered(|ui| {
                                        ui.label(
                                            egui::RichText::new(
                                                "No applications assigned to this view yet.",
                                            )
                                            .font(font_regular(13.0))
                                            .color(palette.text_secondary),
                                        );
                                    });
                                } else {
                                    for app in filtered {
                                        let row_w = ui.available_width();
                                        let name_avail = (row_w - 18.0 - 150.0 - 76.0 - 30.0).max(80.0);
                                        ui.allocate_ui_with_layout(
                                            vec2(row_w, 28.0),
                                            Layout::left_to_right(Align::Center),
                                            |ui| {
                                                ui.spacing_mut().item_spacing.x = 8.0;
                                                if let Some(tex) = tex_cache.get_app_icon(
                                                    ui.ctx(),
                                                    core,
                                                    &app.exe_path,
                                                ) {
                                                    ui.add(egui::Image::new((
                                                        tex.id(),
                                                        vec2(18.0, 18.0),
                                                    )));
                                                } else {
                                                    ui.allocate_exact_size(
                                                        vec2(18.0, 18.0),
                                                        Sense::hover(),
                                                    );
                                                }
                                                ui.allocate_ui_with_layout(
                                                    vec2(name_avail, 24.0),
                                                    Layout::left_to_right(Align::Center),
                                                    |ui| {
                                                        ui.add(
                                                            egui::Label::new(
                                                                egui::RichText::new(&app.app_name)
                                                                    .font(font_regular(12.5))
                                                                    .color(palette.text_primary),
                                                            )
                                                            .truncate(),
                                                        );
                                                    },
                                                );
                                                ui.with_layout(
                                                    Layout::right_to_left(Align::Center),
                                                    |ui| {
                                                        ui.spacing_mut().item_spacing.x = 6.0;
                                                        if widgets::pill_button(
                                                            ui,
                                                            palette,
                                                            PillVariant::Secondary,
                                                            "Unassign",
                                                            24.0,
                                                            74.0,
                                                            app.tag != "Unassigned",
                                                        )
                                                        .clicked()
                                                        {
                                                            let _ = core.set_app_tag(
                                                                &app.app_name,
                                                                "Unassigned",
                                                            );
                                                            state.mark_dirty();
                                                        }
                                                        let mut chosen = app.tag.clone();
                                                        ComboBox::from_id_salt((
                                                            "cat_app_sel",
                                                            &app.app_name,
                                                        ))
                                                        .width(150.0)
                                                        .selected_text(&chosen)
                                                        .show_ui(ui, |ui| {
                                                            for p in &ov.available_projects {
                                                                ui.selectable_value(
                                                                    &mut chosen,
                                                                    p.clone(),
                                                                    p,
                                                                );
                                                            }
                                                        });
                                                        if chosen != app.tag {
                                                            let _ = core
                                                                .set_app_tag(&app.app_name, &chosen);
                                                            state.mark_dirty();
                                                        }
                                                    },
                                                );
                                            },
                                        );
                                        widgets::horizontal_divider(ui, palette);
                                    }
                                }
                            });
                    });
            });

        // Confirm delete category modal
        if let Some(cat_name) = state.confirm_delete_cat.clone() {
            let mut keep = true;
            let card_frame = Frame::NONE
                .fill(palette.bg_card)
                .stroke(Stroke::new(1.0, palette.border_strong))
                .corner_radius(CornerRadius::same(12))
                .inner_margin(Margin::same(16));
            let mresp = Modal::new(Id::unique("cat_del_modal"))
                .backdrop_color(Color32::from_black_alpha(150))
                .frame(card_frame)
                .show(ui.ctx(), |ui| {
                    let inner_w = widgets::modal_inner_width(ui.ctx(), 340.0, 16);
                    ui.set_width(inner_w);
                    ui.set_max_width(inner_w);
                    ui.label(
                        egui::RichText::new("Delete Category")
                            .font(font_bold(15.0))
                            .color(palette.text_primary),
                    );
                    ui.add_space(8.0);
                    ui.add(
                        egui::Label::new(
                            egui::RichText::new(format!(
                                "Delete custom category \"{cat_name}\"? Assigned apps will move back to Unassigned."
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
                            "Delete",
                            28.0,
                            72.0,
                            true,
                        )
                        .clicked()
                        {
                            match core.delete_project_category(&cat_name) {
                                Ok(_) => {
                                    if state.selected_category == cat_name {
                                        state.selected_category = "__ALL__".into();
                                    }
                                    state.mark_dirty();
                                    cmds.push(GuiCmd::ShowToast(format!(
                                        "Deleted \"{cat_name}\""
                                    )));
                                    keep = false;
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
                });
            if mresp.should_close() || !keep {
                state.confirm_delete_cat = None;
            }
        }

    close_req
}

fn cat_nav_row(
    ui: &mut egui::Ui,
    palette: &ThemePalette,
    dot_color: Option<Color32>,
    label: &str,
    count: usize,
    active: bool,
    deletable: bool,
) -> (bool, bool) {
    let w = ui.available_width();
    let (rect, mut resp) = ui.allocate_exact_size(vec2(w, 30.0), Sense::click());
    resp = resp.on_hover_cursor(CursorIcon::PointingHand);
    let bg = if active {
        palette.accent_soft
    } else if resp.hovered() {
        palette.bg_hover
    } else {
        Color32::TRANSPARENT
    };
    let border = if active {
        Stroke::new(1.0, palette.accent)
    } else {
        Stroke::NONE
    };
    ui.painter()
        .rect(rect, CornerRadius::same(6), bg, border, StrokeKind::Inside);

    let mut x = rect.left() + 8.0;
    if let Some(col) = dot_color {
        ui.painter()
            .circle_filled(egui::pos2(x + 4.5, rect.center().y), 4.5, col);
        x += 16.0;
    }

    let g = ui.painter().layout_no_wrap(
        label.to_string(),
        if active {
            font_semibold(12.5)
        } else {
            font_regular(12.5)
        },
        if active {
            palette.accent
        } else {
            palette.text_primary
        },
    );
    ui.painter().with_clip_rect(rect.shrink2(vec2(6.0, 2.0))).galley(
        egui::pos2(x, rect.center().y - g.size().y * 0.5),
        g,
        palette.text_primary,
    );

    let mut del_clicked = false;
    let mut right_edge = rect.right() - 8.0;
    if deletable {
        let xr = egui::Rect::from_center_size(
            egui::pos2(right_edge - 6.0, rect.center().y),
            vec2(16.0, 16.0),
        );
        let xresp = ui
            .interact(xr, Id::unique(("cat_del_row", label)), Sense::click())
            .on_hover_cursor(CursorIcon::PointingHand);
        ui.painter().text(
            xr.center(),
            egui::Align2::CENTER_CENTER,
            "×",
            font_bold(12.0),
            if xresp.hovered() {
                palette.danger
            } else {
                palette.text_secondary
            },
        );
        del_clicked = xresp.clicked();
        right_edge -= 20.0;
    }

    let cnt_g = ui.painter().layout_no_wrap(
        count.to_string(),
        font_semibold(11.0),
        palette.text_secondary,
    );
    let badge_w = cnt_g.size().x + 12.0;
    let badge_r = egui::Rect::from_center_size(
        egui::pos2(right_edge - badge_w * 0.5, rect.center().y),
        vec2(badge_w, 18.0),
    );
    ui.painter()
        .rect_filled(badge_r, CornerRadius::same(9), palette.bg_card_alt);
    ui.painter().galley(
        egui::pos2(
            badge_r.center().x - cnt_g.size().x * 0.5,
            badge_r.center().y - cnt_g.size().y * 0.5,
        ),
        cnt_g,
        palette.text_secondary,
    );

    (resp.clicked(), del_clicked)
}
