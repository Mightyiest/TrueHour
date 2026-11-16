#![allow(dead_code)]

use egui::epaint::{PathShape, PathStroke};
use egui::{pos2, vec2, Color32, Painter, Pos2, Rect, Shape, Stroke};
use std::f32::consts::TAU;

pub fn paint_crescent_moon(p: &Painter, rect: Rect, color: Color32, cut_bg: Color32) {
    let c = rect.center();
    let r = rect.width().min(rect.height()) * 0.36;
    p.circle_filled(c, r, color);
    p.circle_filled(c + vec2(r * 0.42, -r * 0.25), r * 0.85, cut_bg);
}

pub fn paint_sun(p: &Painter, rect: Rect, color: Color32) {
    let c = rect.center();
    let r = rect.width().min(rect.height()) * 0.22;
    let inner = r * 1.55;
    let outer = r * 2.15;
    p.circle_stroke(c, r, Stroke::new(1.5, color));
    for i in 0..8 {
        let a = (i as f32) * (TAU / 8.0);
        let d = vec2(a.cos(), a.sin());
        p.line_segment([c + d * inner, c + d * outer], Stroke::new(1.4, color));
    }
}

pub fn paint_bars(p: &Painter, rect: Rect, color: Color32) {
    let s = rect.width().min(rect.height());
    let base_y = rect.bottom() - s * 0.14;
    let left = rect.left() + s * 0.14;
    let w = s * 0.17;
    let gap = s * 0.10;
    let heights = [s * 0.36, s * 0.56, s * 0.74];
    for (idx, h) in heights.iter().enumerate() {
        let x = left + (idx as f32) * (w + gap);
        let r = Rect::from_min_max(pos2(x, base_y - *h), pos2(x + w, base_y));
        p.rect_stroke(r, 1.0, Stroke::new(1.25, color), egui::StrokeKind::Middle);
    }
}

pub fn paint_folder(p: &Painter, rect: Rect, color: Color32) {
    let l = rect.left() + rect.width() * 0.12;
    let r = rect.right() - rect.width() * 0.12;
    let b = rect.bottom() - rect.height() * 0.15;
    let top_body = rect.top() + rect.height() * 0.33;
    let top_tab = rect.top() + rect.height() * 0.17;
    let mid_tab_x = l + (r - l) * 0.38;
    let split_x = l + (r - l) * 0.48;

    let body = Rect::from_min_max(pos2(l, top_body), pos2(r, b));
    p.rect_stroke(body, 1.8, Stroke::new(1.3, color), egui::StrokeKind::Middle);
    p.add(PathShape::line(
        vec![
            pos2(l + 1.0, top_body),
            pos2(l + 1.0, top_tab),
            pos2(mid_tab_x, top_tab),
            pos2(split_x, top_body),
        ],
        PathStroke::new(1.3, color),
    ));
}

pub fn paint_gear(p: &Painter, rect: Rect, color: Color32) {
    let c = rect.center();
    let r_outer = rect.width().min(rect.height()) * 0.36;
    let r_inner = r_outer * 0.44;
    let r_tooth = r_outer * 1.32;
    p.circle_stroke(c, r_outer, Stroke::new(1.35, color));
    p.circle_stroke(c, r_inner, Stroke::new(1.35, color));
    for i in 0..8 {
        let a = (i as f32) * (TAU / 8.0);
        let d = vec2(a.cos(), a.sin());
        p.line_segment(
            [c + d * (r_outer * 0.92), c + d * r_tooth],
            Stroke::new(1.5, color),
        );
    }
}

pub fn paint_refresh(p: &Painter, rect: Rect, color: Color32) {
    let c = rect.center();
    let r = rect.width().min(rect.height()) * 0.34;
    let pts: Vec<Pos2> = (0..18)
        .map(|i| {
            let a = -0.35 + (i as f32 / 17.0) * (TAU * 0.78);
            c + vec2(a.cos(), a.sin()) * r
        })
        .collect();
    let tip = *pts.last().unwrap_or(&c);
    p.add(PathShape::line(pts, PathStroke::new(1.4, color)));
    // Arrowhead at top-right arc start/end
    p.add(PathShape::line(
        vec![
            tip + vec2(-3.2, -0.8),
            tip,
            tip + vec2(0.8, 3.2),
        ],
        PathStroke::new(1.4, color),
    ));
}

pub fn paint_rename_pencil(p: &Painter, rect: Rect, color: Color32) {
    let s = rect.width().min(rect.height());
    let l = rect.center().x - s * 0.34;
    let r = rect.center().x + s * 0.34;
    let t = rect.center().y - s * 0.34;
    let b = rect.center().y + s * 0.34;
    // Classic 45-degree pencil barrel + nib at bottom-left
    let tip = pos2(l, b);
    let nib_a = pos2(l + s * 0.24, b - s * 0.08);
    let nib_b = pos2(l + s * 0.08, b - s * 0.24);
    let top_a = pos2(r - s * 0.04, t + s * 0.20);
    let top_b = pos2(r - s * 0.20, t + s * 0.04);
    p.add(PathShape::closed_line(
        vec![tip, nib_a, top_a, top_b, nib_b],
        PathStroke::new(1.3, color),
    ));
    p.line_segment([nib_a, nib_b], Stroke::new(1.1, color));
}

pub fn paint_trash(p: &Painter, rect: Rect, color: Color32) {
    let w = rect.width();
    let h = rect.height();
    let cx = rect.center().x;
    let l = cx - w * 0.24;
    let r = cx + w * 0.24;
    let top_lid = rect.top() + h * 0.28;
    let bot = rect.bottom() - h * 0.16;

    // Lid crossbar + small centered knob line (clean, no boxy eye-like shape)
    p.line_segment(
        [pos2(l - 2.0, top_lid), pos2(r + 2.0, top_lid)],
        Stroke::new(1.4, color),
    );
    p.line_segment(
        [pos2(cx - w * 0.10, top_lid - 2.2), pos2(cx + w * 0.10, top_lid - 2.2)],
        Stroke::new(1.4, color),
    );

    // Slightly tapered bin outline
    p.add(PathShape::line(
        vec![
            pos2(l, top_lid + 1.5),
            pos2(l + 1.0, bot),
            pos2(r - 1.0, bot),
            pos2(r, top_lid + 1.5),
        ],
        PathStroke::new(1.3, color),
    ));
    // Two inner slats
    p.line_segment(
        [pos2(cx - 2.0, top_lid + 4.0), pos2(cx - 1.8, bot - 2.2)],
        Stroke::new(1.0, color),
    );
    p.line_segment(
        [pos2(cx + 2.0, top_lid + 4.0), pos2(cx + 1.8, bot - 2.2)],
        Stroke::new(1.0, color),
    );
}

pub fn paint_restore(p: &Painter, rect: Rect, color: Color32) {
    let c = rect.center();
    let r = rect.width().min(rect.height()) * 0.34;
    let pts: Vec<Pos2> = (0..16)
        .map(|i| {
            let a = std::f32::consts::PI * 0.9 - (i as f32 / 15.0) * (TAU * 0.70);
            c + vec2(a.cos(), a.sin()) * r
        })
        .collect();
    let start_tip = pts[0];
    p.add(PathShape::line(pts, PathStroke::new(1.45, color)));
    p.add(PathShape::line(
        vec![
            start_tip + vec2(-3.0, -2.5),
            start_tip,
            start_tip + vec2(3.5, -1.5),
        ],
        PathStroke::new(1.45, color),
    ));
}

pub fn paint_play_triangle(p: &Painter, center: Pos2, size: f32, color: Color32) {
    let half_h = size * 0.44;
    let left_x = center.x - size * 0.30;
    let right_x = center.x + size * 0.42;
    p.add(Shape::convex_polygon(
        vec![
            pos2(left_x, center.y - half_h),
            pos2(right_x, center.y),
            pos2(left_x, center.y + half_h),
        ],
        color,
        Stroke::NONE,
    ));
}

pub fn paint_pause_bars(p: &Painter, center: Pos2, size: f32, color: Color32) {
    let w = size * 0.20;
    let h = size * 0.72;
    let gap = size * 0.16;
    let left = Rect::from_center_size(pos2(center.x - gap * 0.5 - w * 0.5, center.y), vec2(w, h));
    let right = Rect::from_center_size(pos2(center.x + gap * 0.5 + w * 0.5, center.y), vec2(w, h));
    p.rect_filled(left, 1.0, color);
    p.rect_filled(right, 1.0, color);
}

pub fn paint_stop_square(p: &Painter, center: Pos2, size: f32, color: Color32) {
    let s = (size * 0.76).round().max(7.0);
    p.rect_filled(Rect::from_center_size(center, vec2(s, s)), 0.8, color);
}

pub fn paint_info_circle(p: &Painter, center: Pos2, radius: f32, stroke_color: Color32) {
    p.circle_stroke(center, radius, Stroke::new(1.4, stroke_color));
    p.circle_filled(pos2(center.x, center.y - radius * 0.38), radius * 0.14, stroke_color);
    p.line_segment(
        [
            pos2(center.x, center.y - radius * 0.08),
            pos2(center.x, center.y + radius * 0.44),
        ],
        Stroke::new((radius * 0.22).max(1.4), stroke_color),
    );
}

pub fn paint_blue_info_badge(p: &Painter, center: Pos2, radius: f32) {
    let blue = Color32::from_rgb(0x00, 0x78, 0xD4);
    p.circle_filled(center, radius, blue);
    p.circle_filled(
        pos2(center.x, center.y - radius * 0.36),
        radius * 0.11,
        Color32::WHITE,
    );
    p.line_segment(
        [
            pos2(center.x, center.y - radius * 0.08),
            pos2(center.x, center.y + radius * 0.44),
        ],
        Stroke::new((radius * 0.16).max(2.5), Color32::WHITE),
    );
}

pub fn paint_bug(p: &Painter, rect: Rect, color: Color32) {
    let c = rect.center();
    let rx = rect.width() * 0.24;
    let ry = rect.height() * 0.28;
    p.rect_stroke(
        Rect::from_center_size(c + vec2(0.0, 1.0), vec2(rx * 2.0, ry * 2.0)),
        rx,
        Stroke::new(1.25, color),
        egui::StrokeKind::Middle,
    );
    p.circle_stroke(c + vec2(0.0, -ry - 1.2), rx * 0.65, Stroke::new(1.2, color));
    for dy in [-2.0, 1.0, 4.0] {
        p.line_segment(
            [pos2(c.x - rx, c.y + dy), pos2(c.x - rx - 3.0, c.y + dy - 1.2)],
            Stroke::new(1.1, color),
        );
        p.line_segment(
            [pos2(c.x + rx, c.y + dy), pos2(c.x + rx + 3.0, c.y + dy - 1.2)],
            Stroke::new(1.1, color),
        );
    }
}

pub fn paint_merge_badge(p: &Painter, rect: Rect, bg: Color32, fg: Color32) {
    p.rect_filled(rect, 3.0, bg);
    let l = rect.left() + 3.5;
    let r = rect.right() - 3.5;
    let t = rect.top() + 4.0;
    let b = rect.bottom() - 4.0;
    let mid = rect.center().x;
    p.line_segment([pos2(l, t), pos2(mid, t)], Stroke::new(1.3, fg));
    p.line_segment([pos2(l, b), pos2(mid, b)], Stroke::new(1.3, fg));
    p.line_segment([pos2(mid, t), pos2(r, b)], Stroke::new(1.3, fg));
    p.line_segment([pos2(mid, b), pos2(r, t)], Stroke::new(1.3, fg));
}

pub fn paint_doc_icon(p: &Painter, rect: Rect, color: Color32) {
    let r = Rect::from_min_max(
        pos2(rect.left() + 3.0, rect.top() + 2.0),
        pos2(rect.right() - 3.0, rect.bottom() - 2.0),
    );
    p.rect_filled(r, 1.5, color);
    let line_c = Color32::from_rgb(0x94, 0xA3, 0xB8);
    let y1 = r.top() + r.height() * 0.36;
    let y2 = r.top() + r.height() * 0.56;
    let y3 = r.top() + r.height() * 0.76;
    for y in [y1, y2, y3] {
        p.line_segment([pos2(r.left() + 2.2, y), pos2(r.right() - 2.2, y)], Stroke::new(1.0, line_c));
    }
}

pub fn paint_lightning(p: &Painter, rect: Rect, color: Color32) {
    let c = rect.center();
    p.add(Shape::convex_polygon(
        vec![
            pos2(c.x + 1.5, rect.top() + 1.5),
            pos2(c.x - 3.5, c.y + 0.5),
            pos2(c.x, c.y + 0.5),
            pos2(c.x - 1.5, rect.bottom() - 1.5),
            pos2(c.x + 3.5, c.y - 0.5),
            pos2(c.x, c.y - 0.5),
        ],
        color,
        Stroke::NONE,
    ));
}

pub fn paint_github_mark(p: &Painter, center: Pos2, radius: f32, color: Color32) {
    p.circle_filled(center, radius, color);
    // Subtle dark cat ears + face silhouette inside circle
    let cut = Color32::from_rgb(0x16, 0x16, 0x1A);
    p.circle_filled(center + vec2(0.0, 1.5), radius * 0.45, cut);
    p.add(Shape::convex_polygon(
        vec![
            center + vec2(-radius * 0.42, 0.0),
            center + vec2(-radius * 0.36, -radius * 0.42),
            center + vec2(-radius * 0.14, -radius * 0.15),
        ],
        cut,
        Stroke::NONE,
    ));
    p.add(Shape::convex_polygon(
        vec![
            center + vec2(radius * 0.42, 0.0),
            center + vec2(radius * 0.36, -radius * 0.42),
            center + vec2(radius * 0.14, -radius * 0.15),
        ],
        cut,
        Stroke::NONE,
    ));
}

pub fn paint_shield_check(p: &Painter, center: Pos2, size: f32, fill: Color32, check_color: Color32) {
    let half_w = size * 0.40;
    let top_y = center.y - size * 0.44;
    let mid_y = center.y + size * 0.06;
    let bot_y = center.y + size * 0.48;
    p.add(Shape::convex_polygon(
        vec![
            pos2(center.x, top_y),
            pos2(center.x + half_w, top_y + size * 0.16),
            pos2(center.x + half_w * 0.85, mid_y),
            pos2(center.x, bot_y),
            pos2(center.x - half_w * 0.85, mid_y),
            pos2(center.x - half_w, top_y + size * 0.16),
        ],
        fill,
        Stroke::NONE,
    ));
    p.add(PathShape::line(
        vec![
            pos2(center.x - size * 0.18, center.y + size * 0.02),
            pos2(center.x - size * 0.03, center.y + size * 0.18),
            pos2(center.x + size * 0.22, center.y - size * 0.14),
        ],
        PathStroke::new(1.5, check_color),
    ));
}

pub fn paint_checkmark(p: &Painter, rect: Rect, color: Color32) {
    p.add(PathShape::line(
        vec![
            pos2(rect.left() + rect.width() * 0.22, rect.top() + rect.height() * 0.54),
            pos2(rect.left() + rect.width() * 0.43, rect.top() + rect.height() * 0.74),
            pos2(rect.left() + rect.width() * 0.78, rect.top() + rect.height() * 0.30),
        ],
        PathStroke::new(1.9, color),
    ));
}
