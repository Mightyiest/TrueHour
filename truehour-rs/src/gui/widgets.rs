#![allow(dead_code)]

use super::icons;
use super::theme::{
    font_bold, font_regular, font_semibold, parse_hex_color, ThemeKind, ThemePalette,
};
use crate::report::ProjectBreakdownEntry;
use crate::tracker::ProjectAllocationItem;
use egui::epaint::PathStroke;
use egui::{
    pos2, vec2, Align, Align2, Color32, CornerRadius, CursorIcon, Frame, Galley, Margin, Pos2,
    Rect, Response, Sense, Stroke, StrokeKind, TextEdit, Ui, Vec2,
};
use std::sync::Arc;

/// Computes centered outer spawn position and work-area-clamped inner size for secondary windows.
pub fn centered_viewport_pos_and_size(
    root_ctx: &egui::Context,
    desired_inner_size: Vec2,
) -> (Option<Pos2>, Vec2) {
    let ppp = root_ctx.pixels_per_point().max(1.0);
    let root_outer = root_ctx.input(|i| i.viewport().outer_rect);

    #[cfg(windows)]
    {
        use windows::Win32::Foundation::POINT;
        use windows::Win32::Graphics::Gdi::{
            GetMonitorInfoW, MonitorFromPoint, MONITORINFO, MONITOR_DEFAULTTOPRIMARY,
        };
        use windows::Win32::UI::WindowsAndMessaging::GetCursorPos;

        let ref_pt = if let Some(r) = root_outer {
            let c = r.center();
            POINT {
                x: (c.x * ppp).round() as i32,
                y: (c.y * ppp).round() as i32,
            }
        } else {
            let mut cursor = POINT::default();
            if unsafe { GetCursorPos(&mut cursor).is_ok() } {
                cursor
            } else {
                POINT { x: 0, y: 0 }
            }
        };

        let hmon = unsafe { MonitorFromPoint(ref_pt, MONITOR_DEFAULTTOPRIMARY) };
        let mut mi = MONITORINFO {
            cbSize: std::mem::size_of::<MONITORINFO>() as u32,
            ..Default::default()
        };
        if unsafe { GetMonitorInfoW(hmon, &mut mi).as_bool() } {
            let rc = mi.rcWork;
            let work_left = rc.left as f32 / ppp;
            let work_top = rc.top as f32 / ppp;
            let work_w = ((rc.right - rc.left) as f32 / ppp).max(320.0);
            let work_h = ((rc.bottom - rc.top) as f32 / ppp).max(240.0);
            let clamped = vec2(
                desired_inner_size.x.min((work_w - 32.0).max(320.0)),
                desired_inner_size.y.min((work_h - 56.0).max(145.0)),
            );
            let title_pad_h = 34.0;
            let x = (work_left + ((work_w - clamped.x) * 0.5).max(8.0)).round();
            let y = (work_top + ((work_h - (clamped.y + title_pad_h)) * 0.5).max(8.0)).round();
            return (Some(pos2(x, y)), clamped);
        }
    }

    if let Some(mon) = root_ctx.input(|i| i.viewport().monitor_size) {
        if mon.x > 100.0 && mon.y > 100.0 {
            let clamped = vec2(
                desired_inner_size.x.min((mon.x - 32.0).max(320.0)),
                desired_inner_size.y.min((mon.y - 56.0).max(145.0)),
            );
            let x = ((mon.x - clamped.x) * 0.5).max(8.0).round();
            let y = ((mon.y - (clamped.y + 34.0)) * 0.5).max(8.0).round();
            return (Some(pos2(x, y)), clamped);
        }
    }
    (None, desired_inner_size)
}

/// Computes responsive inner modal content width so outer rounded card always keeps >= 22px backdrop margin on both sides.
pub fn modal_inner_width(ctx: &egui::Context, preferred_inner_w: f32, frame_margin_x: i8) -> f32 {
    let win_w = ctx.content_rect().width();
    let max_inner = (win_w - (frame_margin_x as f32 * 2.0) - 44.0).max(220.0);
    preferred_inner_w.min(max_inner)
}

/// Paints a fixed-width left form label column so aligned inputs start at one straight X coordinate.
pub fn form_label_col(
    ui: &mut Ui,
    palette: &ThemePalette,
    col_width: f32,
    row_height: f32,
    text: &str,
    top_align: bool,
) {
    let (rect, _) = ui.allocate_exact_size(vec2(col_width, row_height), Sense::hover());
    if ui.is_rect_visible(rect) {
        let galley = ui.painter().layout_no_wrap(
            text.to_string(),
            font_regular(12.5),
            palette.text_primary,
        );
        let y = if top_align {
            (rect.top() + 5.0).round()
        } else {
            (rect.center().y - galley.size().y * 0.5).round()
        };
        ui.painter()
            .galley(pos2(rect.left().round(), y), galley, palette.text_primary);
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PillVariant {
    Accent,
    Secondary,
    PrimaryBlue,
    DangerOutline,
    AmberOutline,
    ToggledActive,
}

pub fn pill_button(
    ui: &mut Ui,
    palette: &ThemePalette,
    variant: PillVariant,
    label: &str,
    height: f32,
    min_width: f32,
    enabled: bool,
) -> Response {
    pill_button_with_icon(
        ui,
        palette,
        variant,
        label,
        height,
        min_width,
        enabled,
        None::<fn(&egui::Painter, Rect, Color32)>,
    )
}

pub fn pill_button_with_icon<F>(
    ui: &mut Ui,
    palette: &ThemePalette,
    variant: PillVariant,
    label: &str,
    height: f32,
    min_width: f32,
    enabled: bool,
    paint_icon: Option<F>,
) -> Response
where
    F: FnOnce(&egui::Painter, Rect, Color32),
{
    let is_bold = matches!(
        variant,
        PillVariant::Accent | PillVariant::PrimaryBlue | PillVariant::ToggledActive
    );
    let compact = height <= 27.0;
    let font_sz = if compact { 12.0 } else { 12.5 };
    let font = if is_bold {
        font_semibold(font_sz)
    } else {
        font_regular(font_sz)
    };
    let galley: Arc<Galley> =
        ui.painter()
            .layout_no_wrap(label.to_string(), font, Color32::WHITE);

    let icon_space = if paint_icon.is_some() {
        if compact { 16.0 } else { 18.0 }
    } else {
        0.0
    };
    let pad_x = if compact { 11.0 } else { 14.0 };
    let desired_w = (galley.size().x + icon_space + pad_x * 2.0).max(min_width);
    let (rect, mut resp) = ui.allocate_exact_size(
        vec2(desired_w, height),
        if enabled {
            Sense::click()
        } else {
            Sense::hover()
        },
    );
    if enabled && resp.hovered() {
        resp = resp.on_hover_cursor(CursorIcon::PointingHand);
    }

    if ui.is_rect_visible(rect) {
        let hovered = enabled && resp.hovered();
        let (bg, border, fg) = if !enabled {
            match variant {
                PillVariant::Accent | PillVariant::PrimaryBlue => (
                    palette.disabled_btn_bg,
                    Stroke::NONE,
                    palette.disabled_btn_text,
                ),
                _ => (
                    palette.disabled_btn_bg,
                    Stroke::new(1.0, palette.border),
                    palette.disabled_btn_text,
                ),
            }
        } else {
            match variant {
                PillVariant::Accent => (
                    if hovered {
                        palette.accent_btn_hover
                    } else {
                        palette.accent_btn_bg
                    },
                    Stroke::NONE,
                    palette.accent_btn_text,
                ),
                PillVariant::PrimaryBlue => (
                    if hovered {
                        palette.accent_hover
                    } else {
                        palette.accent
                    },
                    Stroke::NONE,
                    Color32::WHITE,
                ),
                PillVariant::Secondary => (
                    if hovered {
                        palette.normal_btn_hover
                    } else {
                        palette.normal_btn_bg
                    },
                    Stroke::new(1.0, palette.normal_btn_border),
                    palette.text_primary,
                ),
                PillVariant::DangerOutline => (
                    if hovered {
                        Color32::from_rgba_unmultiplied(0xEF, 0x44, 0x44, 32)
                    } else {
                        palette.normal_btn_bg
                    },
                    Stroke::new(1.0, Color32::from_rgba_unmultiplied(0xEF, 0x44, 0x44, 140)),
                    palette.danger,
                ),
                PillVariant::AmberOutline => (
                    if hovered {
                        Color32::from_rgba_unmultiplied(0xD9, 0x77, 0x06, 36)
                    } else {
                        Color32::from_rgba_unmultiplied(0xD9, 0x77, 0x06, 20)
                    },
                    Stroke::new(1.0, palette.amber),
                    if palette.is_dark {
                        Color32::from_rgb(0xFB, 0xBF, 0x24)
                    } else {
                        palette.amber
                    },
                ),
                PillVariant::ToggledActive => (
                    if hovered {
                        palette.accent_hover
                    } else {
                        palette.accent
                    },
                    Stroke::new(1.0, palette.accent),
                    Color32::WHITE,
                ),
            }
        };

        let radius = CornerRadius::same(((height * 0.5).floor() as u8).clamp(8, 20));
        let painter = ui.painter();
        painter.rect(rect, radius, bg, border, StrokeKind::Inside);

        let content_w = galley.size().x + icon_space;
        let start_x = rect.center().x - content_w * 0.5;
        if let Some(icon_fn) = paint_icon {
            let icon_rect = Rect::from_center_size(
                pos2(start_x + 6.5, rect.center().y),
                vec2(14.0, 14.0),
            );
            icon_fn(painter, icon_rect, fg);
        }

        let text_galley = ui.painter().layout_no_wrap(
            label.to_string(),
            if is_bold {
                font_semibold(font_sz)
            } else {
                font_regular(font_sz)
            },
            fg,
        );
        let text_pos = pos2(
            (start_x + icon_space).round(),
            (rect.center().y - text_galley.size().y * 0.5).round(),
        );
        painter.galley(text_pos, text_galley, fg);
    }

    resp
}

pub fn icon_square_button<F>(
    ui: &mut Ui,
    palette: &ThemePalette,
    size: Vec2,
    corner_radius: u8,
    danger: bool,
    tooltip: &str,
    paint_icon: F,
) -> Response
where
    F: FnOnce(&egui::Painter, Rect, Color32),
{
    let (rect, mut resp) = ui.allocate_exact_size(size, Sense::click());
    resp = resp.on_hover_cursor(CursorIcon::PointingHand);
    if !tooltip.is_empty() {
        resp = resp.on_hover_text(tooltip);
    }
    if ui.is_rect_visible(rect) {
        let hovered = resp.hovered();
        let (bg, border, fg) = if danger {
            match palette.kind {
                ThemeKind::ClassicDark => (
                    if hovered {
                        Color32::from_rgb(0x33, 0x33, 0x33)
                    } else {
                        Color32::from_rgb(0x26, 0x26, 0x26)
                    },
                    Stroke::new(
                        1.0,
                        if hovered {
                            Color32::from_rgb(0xF8, 0x71, 0x71)
                        } else {
                            Color32::from_rgb(0x44, 0x44, 0x44)
                        },
                    ),
                    Color32::from_rgb(0xF8, 0x71, 0x71),
                ),
                ThemeKind::ModernDark => (
                    if hovered {
                        Color32::from_rgb(0x3F, 0x23, 0x23)
                    } else {
                        Color32::from_rgb(0x2D, 0x1C, 0x1C)
                    },
                    Stroke::new(
                        1.0,
                        if hovered {
                            Color32::from_rgb(0xEF, 0x44, 0x44)
                        } else {
                            Color32::from_rgb(0x4A, 0x2E, 0x2E)
                        },
                    ),
                    Color32::from_rgb(0xEF, 0x44, 0x44),
                ),
                ThemeKind::Light => (
                    if hovered {
                        Color32::from_rgb(0xFE, 0xE2, 0xE2)
                    } else {
                        Color32::from_rgb(0xFF, 0xF5, 0xF5)
                    },
                    Stroke::new(
                        1.0,
                        if hovered {
                            Color32::from_rgb(0xFC, 0xA5, 0xA5)
                        } else {
                            Color32::from_rgb(0xFE, 0xE2, 0xE2)
                        },
                    ),
                    Color32::from_rgb(0xDC, 0x26, 0x26),
                ),
            }
        } else {
            (
                if hovered {
                    palette.normal_btn_hover
                } else {
                    palette.normal_btn_bg
                },
                Stroke::new(1.0, palette.normal_btn_border),
                palette.text_primary,
            )
        };
        let p = ui.painter();
        p.rect(
            rect,
            CornerRadius::same(corner_radius),
            bg,
            border,
            StrokeKind::Inside,
        );
        let icon_dim = (size.x.min(size.y) * 0.54).clamp(12.0, 16.0);
        let icon_rect = Rect::from_center_size(rect.center(), vec2(icon_dim, icon_dim));
        paint_icon(p, icon_rect, fg);
    }
    resp
}

pub fn th_checkbox(ui: &mut Ui, palette: &ThemePalette, checked: &mut bool) -> Response {
    let (rect, mut resp) = ui.allocate_exact_size(vec2(16.0, 16.0), Sense::click());
    resp = resp.on_hover_cursor(CursorIcon::PointingHand);
    if resp.clicked() {
        *checked = !*checked;
        resp.mark_changed();
    }
    if ui.is_rect_visible(rect) {
        let p = ui.painter();
        if *checked {
            let fill = if resp.hovered() {
                palette.accent_hover
            } else {
                palette.accent
            };
            p.rect_filled(rect, CornerRadius::same(4), fill);
            icons::paint_checkmark(p, rect, Color32::WHITE);
        } else {
            p.rect(
                rect,
                CornerRadius::same(4),
                palette.cb_bg,
                Stroke::new(
                    1.5,
                    if resp.hovered() {
                        palette.text_secondary
                    } else {
                        palette.cb_border
                    },
                ),
                StrokeKind::Inside,
            );
        }
    }
    resp
}

pub fn th_checkbox_label(
    ui: &mut Ui,
    palette: &ThemePalette,
    checked: &mut bool,
    label: &str,
) -> Response {
    ui.horizontal(|ui| {
        ui.spacing_mut().item_spacing.x = 8.0;
        let cb = th_checkbox(ui, palette, checked);
        let lbl_resp = ui
            .add(
                egui::Label::new(
                    egui::RichText::new(label)
                        .font(font_regular(12.5))
                        .color(palette.text_primary),
                )
                .sense(Sense::click()),
            )
            .on_hover_cursor(CursorIcon::PointingHand);
        if lbl_resp.clicked() {
            *checked = !*checked;
        }
        cb
    })
    .inner
}

/// Renders a PyQt6-style QGroupBox with rounded 1px border and title breaking the top border.
pub fn group_box(
    ui: &mut Ui,
    palette: &ThemePalette,
    title: &str,
    add_contents: impl FnOnce(&mut Ui),
) {
    let outer_margin = Margin {
        left: 0,
        right: 0,
        top: 9,
        bottom: 6,
    };
    let inner_margin = Margin {
        left: 12,
        right: 12,
        top: 14,
        bottom: 10,
    };

    let title_galley = ui.painter().layout_no_wrap(
        title.to_string(),
        font_semibold(12.0),
        palette.text_primary,
    );

    let group_stroke_color = if palette.is_dark {
        Color32::from_rgb(0x2C, 0x2C, 0x34)
    } else {
        palette.border_strong
    };

    let outer = Frame::NONE.outer_margin(outer_margin).show(ui, |ui| {
        let mut inner_resp = Frame::NONE
            .fill(palette.bg_card)
            .stroke(Stroke::new(1.0, group_stroke_color))
            .corner_radius(CornerRadius::same(8))
            .inner_margin(inner_margin)
            .show(ui, |ui| {
                ui.set_width(ui.available_width());
                add_contents(ui);
            });
        // Mask top border behind title and draw title text
        let frame_rect = inner_resp.response.rect;
        let title_x = frame_rect.left() + 10.0;
        let title_y = frame_rect.top() - title_galley.size().y * 0.52;
        let mask_rect = Rect::from_min_size(
            pos2(title_x - 4.0, frame_rect.top() - 3.0),
            vec2(title_galley.size().x + 8.0, 6.0),
        );
        ui.painter().rect_filled(mask_rect, 0, palette.bg_card);
        ui.painter().galley(
            pos2(title_x, title_y),
            title_galley,
            palette.text_primary,
        );
        inner_resp.response.mark_changed();
    });
    let _ = outer;
}

/// Renders connected folder-style tabs (top-rounded tabs flush with the content container border below).
pub fn folder_tab_bar<T: Copy + PartialEq>(
    ui: &mut Ui,
    palette: &ThemePalette,
    tabs: &[(T, &str)],
    active: &mut T,
    min_tab_width: f32,
) -> Option<Rect> {
    let mut active_rect = None;
    ui.horizontal(|ui| {
        ui.spacing_mut().item_spacing.x = 3.0;
        for &(key, label) in tabs {
            let selected = *active == key;
            let font = if selected {
                font_semibold(12.5)
            } else {
                font_regular(12.5)
            };
            let galley = ui.painter().layout_no_wrap(label.to_string(), font, Color32::WHITE);
            let w = (galley.size().x + 22.0).max(min_tab_width);
            let (rect, mut resp) = ui.allocate_exact_size(vec2(w, 29.0), Sense::click());
            resp = resp.on_hover_cursor(CursorIcon::PointingHand);
            if resp.clicked() {
                *active = key;
            }
            if selected {
                active_rect = Some(rect);
            }
            if ui.is_rect_visible(rect) {
                let p = ui.painter();
                let radius = CornerRadius {
                    nw: 6,
                    ne: 6,
                    sw: 0,
                    se: 0,
                };
                let (bg, fg) = if selected {
                    (palette.tab_active_bg, palette.tab_active_text)
                } else if resp.hovered() {
                    (palette.bg_hover, palette.text_primary)
                } else {
                    (palette.tab_inactive_bg, palette.tab_inactive_text)
                };
                p.rect_filled(rect, radius, bg);
                // Draw left, top, right borders without bottom border so active tab connects seamlessly
                let border = PathStroke::new(1.0, palette.border);
                let b_y = rect.bottom();
                let t_y = rect.top() + 0.5;
                let l_x = rect.left() + 0.5;
                let r_x = rect.right() - 0.5;
                p.add(egui::epaint::PathShape::line(
                    vec![
                        pos2(l_x, b_y),
                        pos2(l_x, t_y + 4.0),
                        pos2(l_x + 4.0, t_y),
                        pos2(r_x - 4.0, t_y),
                        pos2(r_x, t_y + 4.0),
                        pos2(r_x, b_y),
                    ],
                    border,
                ));
                let text_galley = ui.painter().layout_no_wrap(
                    label.to_string(),
                    if selected {
                        font_semibold(12.5)
                    } else {
                        font_regular(12.5)
                    },
                    fg,
                );
                let text_pos = pos2(
                    (rect.center().x - text_galley.size().x * 0.5).round(),
                    (rect.center().y - text_galley.size().y * 0.5).round(),
                );
                p.galley(text_pos, text_galley, fg);
            }
        }
    });
    active_rect
}

/// Erases the 1px top border of a pane immediately underneath the active folder tab.
pub fn seamless_tab_join(ui: &Ui, palette: &ThemePalette, active_tab_rect: Option<Rect>, pane_rect: Rect) {
    if let Some(tab_r) = active_tab_rect {
        let seam = Rect::from_min_max(
            pos2(tab_r.left() + 1.5, pane_rect.top() - 1.5),
            pos2(tab_r.right() - 1.5, pane_rect.top() + 2.0),
        );
        ui.painter().rect_filled(seam, 0, palette.tab_active_bg);
    }
}

pub fn category_pill(
    ui: &mut Ui,
    label: &str,
    hex_color: &str,
    width: f32,
) -> Response {
    let base = parse_hex_color(hex_color, Color32::from_rgb(0x64, 0x74, 0x8B));
    let (rect, mut resp) = ui.allocate_exact_size(vec2(width, 21.0), Sense::click());
    resp = resp.on_hover_cursor(CursorIcon::PointingHand);
    if ui.is_rect_visible(rect) {
        let bg = if resp.hovered() {
            base.linear_multiply(1.12)
        } else {
            base
        };
        let p = ui.painter();
        p.rect_filled(rect, CornerRadius::same(6), bg);
        let text_galley = p.layout_no_wrap(
            label.to_string(),
            font_bold(11.0),
            Color32::WHITE,
        );
        let max_text_w = rect.width() - 10.0;
        let text_pos = if text_galley.size().x <= max_text_w {
            pos2(
                (rect.center().x - text_galley.size().x * 0.5).round(),
                (rect.center().y - text_galley.size().y * 0.5).round(),
            )
        } else {
            pos2(
                (rect.left() + 5.0).round(),
                (rect.center().y - text_galley.size().y * 0.5).round(),
            )
        };
        p.with_clip_rect(rect.shrink(3.0))
            .galley(text_pos, text_galley, Color32::WHITE);
    }
    resp
}

pub fn status_pill_button(
    ui: &mut Ui,
    palette: &ThemePalette,
    status: &str,
    tooltip: &str,
) -> Response {
    let upper = status.trim().to_ascii_uppercase();
    let (bg, fg) = match (palette.kind, upper.as_str()) {
        (ThemeKind::ClassicDark, "PAID") => (
            Color32::from_rgb(0x33, 0x33, 0x33),
            Color32::from_rgb(0xFF, 0xFF, 0xFF),
        ),
        (ThemeKind::ClassicDark, "DRAFT") => (
            Color32::from_rgb(0x2E, 0x10, 0x65),
            Color32::from_rgb(0xC0, 0x84, 0xFC),
        ),
        (ThemeKind::ClassicDark, _) => (
            Color32::from_rgb(0x22, 0x22, 0x22),
            Color32::from_rgb(0xA3, 0xA3, 0xA3),
        ),
        (ThemeKind::ModernDark, "PAID") => (
            Color32::from_rgb(0x1A, 0x2E, 0x26),
            Color32::from_rgb(0x10, 0xB9, 0x81),
        ),
        (ThemeKind::ModernDark, "DRAFT") => (
            Color32::from_rgb(0x2E, 0x10, 0x65),
            Color32::from_rgb(0xC0, 0x84, 0xFC),
        ),
        (ThemeKind::ModernDark, _) => (
            Color32::from_rgb(0x2B, 0x21, 0x18),
            Color32::from_rgb(0xF5, 0x9E, 0x0B),
        ),
        (ThemeKind::Light, "PAID") => (
            Color32::from_rgb(0xDC, 0xFC, 0xE7),
            Color32::from_rgb(0x16, 0xA3, 0x4A),
        ),
        (ThemeKind::Light, "DRAFT") => (
            Color32::from_rgb(0xF3, 0xE8, 0xFF),
            Color32::from_rgb(0x7E, 0x22, 0xCE),
        ),
        (ThemeKind::Light, _) => (
            Color32::from_rgb(0xFE, 0xF3, 0xC7),
            Color32::from_rgb(0xD9, 0x77, 0x06),
        ),
    };
    let galley = ui
        .painter()
        .layout_no_wrap(upper, font_bold(10.0), fg);
    let desired_w = (galley.size().x + 16.0).max(54.0);
    let (rect, mut resp) = ui.allocate_exact_size(vec2(desired_w, 26.0), Sense::click());
    resp = resp.on_hover_cursor(CursorIcon::PointingHand);
    if !tooltip.is_empty() {
        resp = resp.on_hover_text(tooltip);
    }
    if ui.is_rect_visible(rect) {
        let border_col = if resp.hovered() {
            fg
        } else {
            Color32::from_rgba_unmultiplied(fg.r(), fg.g(), fg.b(), 65)
        };
        let p = ui.painter();
        p.rect(
            rect,
            CornerRadius::same(5),
            bg,
            Stroke::new(1.0, border_col),
            StrokeKind::Inside,
        );
        p.galley(
            pos2(
                (rect.center().x - galley.size().x * 0.5).round(),
                (rect.center().y - galley.size().y * 0.5).round(),
            ),
            galley,
            fg,
        );
    }
    resp
}

pub fn dark_badge_pill(ui: &mut Ui, text: &str, bg: Color32, fg: Color32) {
    let galley = ui.painter().layout_no_wrap(text.to_string(), font_semibold(10.5), fg);
    let (rect, _) = ui.allocate_exact_size(vec2(galley.size().x + 14.0, 18.0), Sense::hover());
    if ui.is_rect_visible(rect) {
        let p = ui.painter();
        p.rect_filled(rect, CornerRadius::same(4), bg);
        p.galley(
            pos2(
                (rect.center().x - galley.size().x * 0.5).round(),
                (rect.center().y - galley.size().y * 0.5).round(),
            ),
            galley,
            fg,
        );
    }
}

pub fn styled_input_frame(palette: &ThemePalette) -> Frame {
    Frame::NONE
        .fill(palette.bg_input)
        .stroke(Stroke::new(1.0, palette.border_strong))
        .corner_radius(CornerRadius::same(6))
        .inner_margin(Margin::symmetric(8, 5))
}

pub fn text_input_line(
    ui: &mut Ui,
    palette: &ThemePalette,
    buf: &mut String,
    placeholder: &str,
    width: f32,
    enabled: bool,
) -> Response {
    let inner_w = (width - 2.0).max(20.0);
    ui.add_enabled_ui(enabled, |ui| {
        let edit = TextEdit::singleline(buf)
            .hint_text(
                egui::RichText::new(placeholder)
                    .font(font_regular(12.5))
                    .color(palette.text_muted),
            )
            .font(font_regular(12.5))
            .align(Align2::LEFT_CENTER)
            .text_color(if enabled {
                palette.text_primary
            } else {
                palette.disabled_btn_text
            })
            .frame(styled_input_frame(palette))
            .desired_width(inner_w);
        ui.add(edit)
    })
    .inner
}

pub fn password_input_line(
    ui: &mut Ui,
    palette: &ThemePalette,
    buf: &mut String,
    placeholder: &str,
    width: f32,
) -> Response {
    let inner_w = (width - 2.0).max(20.0);
    let edit = TextEdit::singleline(buf)
        .password(true)
        .hint_text(
            egui::RichText::new(placeholder)
                .font(font_regular(12.5))
                .color(palette.text_muted),
        )
        .font(font_regular(12.5))
        .align(Align2::LEFT_CENTER)
        .text_color(palette.text_primary)
        .frame(styled_input_frame(palette))
        .desired_width(inner_w);
    ui.add(edit)
}

pub fn email_chip_editor(
    ui: &mut Ui,
    palette: &ThemePalette,
    emails: &mut Vec<String>,
    draft: &mut String,
    width: f32,
) {
    ui.vertical(|ui| {
        ui.set_width(width);
        ui.spacing_mut().item_spacing.y = 5.0;

        if !emails.is_empty() {
            let mut remove_idx: Option<usize> = None;
            ui.horizontal_wrapped(|ui| {
                ui.spacing_mut().item_spacing = vec2(6.0, 5.0);
                for (idx, addr) in emails.iter().enumerate() {
                    Frame::NONE
                        .fill(palette.chip_bg)
                        .stroke(Stroke::new(1.0, palette.chip_border))
                        .corner_radius(CornerRadius::same(13))
                        .inner_margin(Margin::symmetric(10, 4))
                        .show(ui, |ui| {
                            ui.horizontal(|ui| {
                                ui.spacing_mut().item_spacing.x = 6.0;
                                ui.label(
                                    egui::RichText::new(addr)
                                        .font(font_regular(12.0))
                                        .color(palette.text_primary),
                                );
                                let x_resp = ui
                                    .add(
                                        egui::Label::new(
                                            egui::RichText::new("✕")
                                                .font(font_bold(11.0))
                                                .color(palette.text_secondary),
                                        )
                                        .sense(Sense::click()),
                                    )
                                    .on_hover_cursor(CursorIcon::PointingHand);
                                if x_resp.clicked() {
                                    remove_idx = Some(idx);
                                }
                            });
                        });
                }
            });
            if let Some(idx) = remove_idx {
                emails.remove(idx);
            }
        }

        let resp = text_input_line(
            ui,
            palette,
            draft,
            "Type email and press Enter or comma...",
            width,
            true,
        );
        let enter = resp.lost_focus() && ui.input(|i| i.key_pressed(egui::Key::Enter));
        let has_delim = draft.contains(',') || draft.contains(';');
        if enter || has_delim || (resp.lost_focus() && !draft.trim().is_empty()) {
            commit_email_draft(emails, draft);
        }
    });
}

pub fn commit_email_draft(emails: &mut Vec<String>, draft: &mut String) {
    let parts: Vec<String> = draft
        .split([',', ';', ' ', '\t', '\n'])
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .collect();
    for p in parts {
        if !emails.contains(&p) {
            emails.push(p);
        }
    }
    draft.clear();
}

pub fn segmented_bar_allocations(
    ui: &mut Ui,
    palette: &ThemePalette,
    items: &[ProjectAllocationItem],
) {
    if items.is_empty() {
        ui.label(
            egui::RichText::new("No counted project activity yet.")
                .font(font_regular(12.0))
                .color(palette.text_muted),
        );
        return;
    }

    let w = ui.available_width().max(120.0);
    let (bar_rect, _) = ui.allocate_exact_size(vec2(w, 12.0), Sense::hover());
    ui.painter()
        .rect_filled(bar_rect, CornerRadius::same(6), palette.bg_hover);

    let total_pct: f64 = items.iter().map(|i| i.percent.max(0.0)).sum();
    if total_pct > 0.0 {
        let mut x = bar_rect.left();
        for (idx, item) in items.iter().enumerate() {
            let seg_w = if idx + 1 == items.len() {
                (bar_rect.right() - x).max(0.0)
            } else {
                ((item.percent / total_pct) as f32 * bar_rect.width()).max(2.0)
            };
            let seg = Rect::from_min_max(
                pos2(x, bar_rect.top()),
                pos2((x + seg_w).min(bar_rect.right()), bar_rect.bottom()),
            );
            let col = parse_hex_color(&item.color, Color32::GRAY);
            let cr = if items.len() == 1 {
                CornerRadius::same(6)
            } else if idx == 0 {
                CornerRadius { nw: 6, sw: 6, ne: 0, se: 0 }
            } else if idx + 1 == items.len() {
                CornerRadius { nw: 0, sw: 0, ne: 6, se: 6 }
            } else {
                CornerRadius::ZERO
            };
            ui.painter().rect_filled(seg, cr, col);
            x += seg_w;
        }
    }

    ui.add_space(6.0);
    let max_row_w = ui.available_width().max(160.0);
    let mut rows: Vec<Vec<(&ProjectAllocationItem, String, f32)>> = Vec::new();
    let mut cur_row: Vec<(&ProjectAllocationItem, String, f32)> = Vec::new();
    let mut cur_w = 0.0f32;
    let gap = 12.0f32;

    for item in items {
        let label = format!("{} ({:.1}% · {})", item.project, item.percent, item.formatted);
        let text_w = ui
            .painter()
            .layout_no_wrap(label.clone(), font_regular(11.5), palette.text_secondary)
            .size()
            .x;
        let item_w = 9.0 + 5.0 + text_w;
        if !cur_row.is_empty() && cur_w + gap + item_w > max_row_w {
            rows.push(std::mem::take(&mut cur_row));
            cur_w = 0.0;
        }
        if !cur_row.is_empty() {
            cur_w += gap;
        }
        cur_w += item_w;
        cur_row.push((item, label, item_w));
    }
    if !cur_row.is_empty() {
        rows.push(cur_row);
    }

    for row in rows {
        ui.horizontal(|ui| {
            ui.spacing_mut().item_spacing.x = gap;
            for (item, label, _w) in row {
                ui.horizontal(|ui| {
                    ui.spacing_mut().item_spacing.x = 5.0;
                    let (dot_r, _) = ui.allocate_exact_size(vec2(9.0, 14.0), Sense::hover());
                    ui.painter().circle_filled(
                        dot_r.center(),
                        4.0,
                        parse_hex_color(&item.color, Color32::GRAY),
                    );
                    ui.label(
                        egui::RichText::new(label)
                            .font(font_regular(11.5))
                            .color(palette.text_secondary),
                    );
                });
            }
        });
    }
}

pub fn segmented_bar_breakdown(
    ui: &mut Ui,
    palette: &ThemePalette,
    items: &[ProjectBreakdownEntry],
) {
    let mapped: Vec<ProjectAllocationItem> = items
        .iter()
        .map(|b| ProjectAllocationItem {
            project: b.project.clone(),
            seconds: b.seconds,
            formatted: b.formatted.clone(),
            percent: b.percent,
            color: b.color.clone(),
        })
        .collect();
    segmented_bar_allocations(ui, palette, &mapped);
}

pub fn kpi_card(
    ui: &mut Ui,
    palette: &ThemePalette,
    label: &str,
    value: &str,
    green: bool,
    width: f32,
) {
    Frame::NONE
        .fill(palette.bg_card_alt)
        .stroke(Stroke::new(1.0, palette.border))
        .corner_radius(CornerRadius::same(8))
        .inner_margin(Margin::symmetric(12, 10))
        .show(ui, |ui| {
            ui.set_width((width - 24.0).max(60.0));
            ui.label(
                egui::RichText::new(label)
                    .font(font_semibold(11.0))
                    .color(palette.text_secondary),
            );
            ui.add_space(3.0);
            ui.label(
                egui::RichText::new(value)
                    .font(font_bold(18.0))
                    .color(if green {
                        palette.green
                    } else {
                        palette.text_primary
                    }),
            );
        });
}

pub fn kpi_card_centered(
    ui: &mut Ui,
    palette: &ThemePalette,
    label: &str,
    value: &str,
    green: bool,
    width: f32,
) {
    Frame::NONE
        .fill(palette.bg_card_alt)
        .stroke(Stroke::new(1.0, palette.border))
        .corner_radius(CornerRadius::same(8))
        .inner_margin(Margin::symmetric(10, 10))
        .show(ui, |ui| {
            ui.set_width((width - 22.0).max(60.0));
            ui.vertical_centered(|ui| {
                ui.spacing_mut().item_spacing.y = 3.0;
                ui.label(
                    egui::RichText::new(value)
                        .font(font_bold(16.0))
                        .color(if green {
                            palette.earned_color
                        } else {
                            palette.text_primary
                        }),
                );
                ui.label(
                    egui::RichText::new(label)
                        .font(font_regular(10.5))
                        .color(palette.text_secondary),
                );
            });
        });
}

pub fn horizontal_divider(ui: &mut Ui, palette: &ThemePalette) {
    let w = ui.available_width();
    let (rect, _) = ui.allocate_exact_size(vec2(w, 1.0), Sense::hover());
    ui.painter().line_segment(
        [
            pos2(rect.left(), rect.center().y),
            pos2(rect.right(), rect.center().y),
        ],
        Stroke::new(1.0, palette.border),
    );
}

pub fn paint_badge_dot(painter: &egui::Painter, center: Pos2, radius: f32, color: Color32) {
    painter.circle_filled(center, radius, color);
}

/// Fixed-height right-aligned action button row inside modals so `right_to_left(Align::Center)`
/// does not absorb the remaining viewport height and stretch short modals vertically.
pub fn modal_action_row(
    ui: &mut Ui,
    inner_w: f32,
    height: f32,
    add_contents: impl FnOnce(&mut Ui),
) {
    ui.allocate_ui_with_layout(
        vec2(inner_w, height),
        egui::Layout::right_to_left(Align::Center),
        |ui| {
            ui.spacing_mut().item_spacing.x = 8.0;
            add_contents(ui);
        },
    );
}

/// Renders a crisp, cleanly sized floating toast pill centered near the bottom of `ctx`.
pub fn render_toast_overlay(ctx: &egui::Context, palette: &ThemePalette, text: &str) {
    let trimmed = text.trim();
    if trimmed.is_empty() {
        return;
    }

    let screen = ctx.content_rect();
    let max_text_w = (screen.width() - 68.0).clamp(140.0, 340.0);
    let fg = Color32::WHITE;
    let measure_painter = ctx.layer_painter(egui::LayerId::new(
        egui::Order::Tooltip,
        egui::Id::unique("truehour_toast_layer"),
    ));
    let galley = measure_painter.layout(trimmed.to_string(), font_semibold(12.0), fg, max_text_w);
    let single_line = galley.rows.len() <= 1;
    let text_w = galley.size().x.ceil();
    let text_h = galley.size().y.ceil();

    let pad_x = 14.0;
    let pad_y = if single_line { 8.0 } else { 9.0 };
    let dot_slot = 14.0;
    let pill_w = (text_w + dot_slot + pad_x * 2.0)
        .min((screen.width() - 24.0).max(160.0))
        .ceil();
    let pill_h = (text_h + pad_y * 2.0).max(32.0).ceil();
    let radius_u8 = if single_line {
        (pill_h * 0.5).floor().clamp(10.0, 18.0) as u8
    } else {
        10
    };

    let x = (screen.left() + (screen.width() - pill_w) * 0.5).round();
    let y = (screen.bottom() - pill_h - 32.0)
        .round()
        .max(screen.top() + 8.0);

    let lower = trimmed.to_lowercase();
    let dot_color = if lower.contains("error") || lower.contains("failed") || lower.contains("cannot")
    {
        palette.danger
    } else if lower.contains("saved")
        || lower.contains("recovered")
        || lower.contains("restored")
        || lower.contains("merged")
        || lower.contains("opened")
        || lower.contains("moved")
    {
        palette.green
    } else {
        Color32::from_rgb(0x60, 0xA5, 0xFA)
    };

    let bg = if palette.is_dark {
        Color32::from_rgb(0x1E, 0x24, 0x33)
    } else {
        Color32::from_rgb(0x1E, 0x29, 0x3B)
    };
    let border = if palette.is_dark {
        Stroke::new(1.0, palette.border_strong)
    } else {
        Stroke::new(1.0, Color32::from_rgb(0x33, 0x41, 0x55))
    };

    egui::Area::new(egui::Id::unique("truehour_toast"))
        .fixed_pos(pos2(x, y))
        .default_size(vec2(pill_w, pill_h))
        .order(egui::Order::Tooltip)
        .interactable(false)
        .show(ctx, |ui| {
            let (rect, _) = ui.allocate_exact_size(vec2(pill_w, pill_h), Sense::hover());
            let radius = CornerRadius::same(radius_u8);
            let shadow = egui::epaint::Shadow {
                offset: [0, 3],
                blur: 10,
                spread: 0,
                color: Color32::from_black_alpha(if palette.is_dark { 110 } else { 40 }),
            };
            let p = ui.painter();
            p.add(shadow.as_shape(rect, radius));
            p.rect(rect, radius, bg, border, StrokeKind::Inside);

            let dot_y = if single_line {
                rect.center().y.round()
            } else {
                (rect.top() + pad_y + 7.0).round()
            };
            p.circle_filled(pos2((rect.left() + pad_x + 3.0).round(), dot_y), 3.0, dot_color);
            p.galley(
                pos2(
                    (rect.left() + pad_x + dot_slot).round(),
                    (rect.center().y - galley.size().y * 0.5).round(),
                ),
                galley,
                fg,
            );
        });
}

#[allow(dead_code)]
fn _align_check(_a: Align, _b: Align2) {}
