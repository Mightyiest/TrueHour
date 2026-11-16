use egui::epaint::Shadow;
use egui::{
    Color32, CornerRadius, FontData, FontDefinitions, FontFamily, FontId, Stroke, SystemTheme,
    Visuals,
};
use std::path::PathBuf;
use std::sync::Arc;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ThemeKind {
    ModernDark,
    ClassicDark,
    Light,
}

impl ThemeKind {
    pub fn from_str_style(style: &str) -> Self {
        match style.trim().to_ascii_lowercase().as_str() {
            "light" => Self::Light,
            "classic-dark" => Self::ClassicDark,
            _ => Self::ModernDark,
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            Self::ModernDark => "modern-dark",
            Self::ClassicDark => "classic-dark",
            Self::Light => "light",
        }
    }

    pub fn is_dark(&self) -> bool {
        !matches!(self, Self::Light)
    }

    pub fn system_theme(&self) -> SystemTheme {
        if self.is_dark() {
            SystemTheme::Dark
        } else {
            SystemTheme::Light
        }
    }
}

#[derive(Debug, Clone, Copy)]
pub struct ThemePalette {
    pub kind: ThemeKind,
    pub is_dark: bool,
    pub bg_window: Color32,
    pub bg_card: Color32,
    pub bg_card_alt: Color32,
    pub bg_hover: Color32,
    pub bg_input: Color32,
    pub border: Color32,
    pub border_strong: Color32,
    pub text_primary: Color32,
    pub text_secondary: Color32,
    pub text_muted: Color32,
    pub clock_color: Color32,
    pub earned_color: Color32,
    pub total_val_color: Color32,
    pub accent: Color32,
    pub accent_hover: Color32,
    pub accent_soft: Color32,
    pub accent_btn_bg: Color32,
    pub accent_btn_hover: Color32,
    pub accent_btn_text: Color32,
    pub normal_btn_bg: Color32,
    pub normal_btn_hover: Color32,
    pub normal_btn_border: Color32,
    pub disabled_btn_bg: Color32,
    pub disabled_btn_text: Color32,
    pub cb_bg: Color32,
    pub cb_border: Color32,
    pub tab_inactive_bg: Color32,
    pub tab_inactive_text: Color32,
    pub tab_active_bg: Color32,
    pub tab_active_text: Color32,
    pub badge_latest_bg: Color32,
    pub badge_latest_text: Color32,
    pub badge_rel_bg: Color32,
    pub badge_rel_text: Color32,
    pub amber: Color32,
    pub green: Color32,
    pub danger: Color32,
    pub info_blue: Color32,
    pub chip_bg: Color32,
    pub chip_border: Color32,
    pub heat: [Color32; 5],
}

impl ThemePalette {
    pub fn for_style(style: &str) -> Self {
        match ThemeKind::from_str_style(style) {
            ThemeKind::ModernDark => Self {
                kind: ThemeKind::ModernDark,
                is_dark: true,
                bg_window: Color32::from_rgb(0x0F, 0x0F, 0x11),
                bg_card: Color32::from_rgb(0x16, 0x16, 0x1A),
                bg_card_alt: Color32::from_rgb(0x13, 0x13, 0x17),
                bg_hover: Color32::from_rgb(0x23, 0x23, 0x29),
                bg_input: Color32::from_rgb(0x16, 0x16, 0x1A),
                border: Color32::from_rgb(0x23, 0x23, 0x29),
                border_strong: Color32::from_rgb(0x36, 0x36, 0x40),
                text_primary: Color32::from_rgb(0xED, 0xED, 0xED),
                text_secondary: Color32::from_rgb(0xA3, 0xA3, 0xA3),
                text_muted: Color32::from_rgb(0x6D, 0x6D, 0x75),
                clock_color: Color32::from_rgb(0xF3, 0xF4, 0xF6),
                earned_color: Color32::WHITE,
                total_val_color: Color32::WHITE,
                accent: Color32::from_rgb(0x25, 0x63, 0xEB),
                accent_hover: Color32::from_rgb(0x3B, 0x82, 0xF6),
                accent_soft: Color32::from_rgba_unmultiplied(0x25, 0x63, 0xEB, 42),
                accent_btn_bg: Color32::from_rgb(0x26, 0x26, 0x26),
                accent_btn_hover: Color32::from_rgb(0x3F, 0x3F, 0x46),
                accent_btn_text: Color32::WHITE,
                normal_btn_bg: Color32::from_rgb(0x16, 0x16, 0x1A),
                normal_btn_hover: Color32::from_rgb(0x23, 0x23, 0x29),
                normal_btn_border: Color32::from_rgb(0x2A, 0x2A, 0x32),
                disabled_btn_bg: Color32::from_rgb(0x13, 0x13, 0x17),
                disabled_btn_text: Color32::from_rgb(0x61, 0x61, 0x69),
                cb_bg: Color32::from_rgb(0x16, 0x16, 0x1A),
                cb_border: Color32::from_rgb(0x8E, 0x8E, 0x96),
                tab_inactive_bg: Color32::from_rgb(0x0F, 0x0F, 0x11),
                tab_inactive_text: Color32::from_rgb(0xA3, 0xA3, 0xA3),
                tab_active_bg: Color32::from_rgb(0x16, 0x16, 0x1A),
                tab_active_text: Color32::from_rgb(0x25, 0x63, 0xEB),
                badge_latest_bg: Color32::from_rgb(0x26, 0x26, 0x26),
                badge_latest_text: Color32::WHITE,
                badge_rel_bg: Color32::from_rgb(0x26, 0x26, 0x26),
                badge_rel_text: Color32::from_rgb(0xAA, 0xAA, 0xAA),
                amber: Color32::from_rgb(0xD9, 0x77, 0x06),
                green: Color32::from_rgb(0x22, 0xC5, 0x5E),
                danger: Color32::from_rgb(0xEF, 0x44, 0x44),
                info_blue: Color32::from_rgb(0x00, 0x78, 0xD4),
                chip_bg: Color32::from_rgb(0x26, 0x26, 0x2C),
                chip_border: Color32::from_rgb(0x36, 0x36, 0x40),
                heat: [
                    Color32::from_rgb(0x1C, 0x1C, 0x22),
                    Color32::from_rgb(0x1E, 0x3A, 0x5F),
                    Color32::from_rgb(0x1D, 0x4E, 0xD8),
                    Color32::from_rgb(0x25, 0x63, 0xEB),
                    Color32::from_rgb(0x60, 0xA5, 0xFA),
                ],
            },
            ThemeKind::ClassicDark => Self {
                kind: ThemeKind::ClassicDark,
                is_dark: true,
                bg_window: Color32::from_rgb(0x14, 0x14, 0x14),
                bg_card: Color32::from_rgb(0x1E, 0x1E, 0x1E),
                bg_card_alt: Color32::from_rgb(0x18, 0x18, 0x18),
                bg_hover: Color32::from_rgb(0x2A, 0x2A, 0x2A),
                bg_input: Color32::from_rgb(0x1E, 0x1E, 0x1E),
                border: Color32::from_rgb(0x33, 0x33, 0x33),
                border_strong: Color32::from_rgb(0x45, 0x45, 0x45),
                text_primary: Color32::from_rgb(0xE0, 0xE0, 0xE0),
                text_secondary: Color32::from_rgb(0xAA, 0xAA, 0xAA),
                text_muted: Color32::from_rgb(0x75, 0x75, 0x75),
                clock_color: Color32::from_rgb(0xF3, 0xF4, 0xF6),
                earned_color: Color32::WHITE,
                total_val_color: Color32::WHITE,
                accent: Color32::from_rgb(0x25, 0x63, 0xEB),
                accent_hover: Color32::from_rgb(0x3B, 0x82, 0xF6),
                accent_soft: Color32::from_rgba_unmultiplied(0x25, 0x63, 0xEB, 46),
                accent_btn_bg: Color32::from_rgb(0x26, 0x26, 0x26),
                accent_btn_hover: Color32::from_rgb(0x38, 0x38, 0x38),
                accent_btn_text: Color32::WHITE,
                normal_btn_bg: Color32::from_rgb(0x1E, 0x1E, 0x1E),
                normal_btn_hover: Color32::from_rgb(0x2C, 0x2C, 0x2C),
                normal_btn_border: Color32::from_rgb(0x33, 0x33, 0x33),
                disabled_btn_bg: Color32::from_rgb(0x18, 0x18, 0x18),
                disabled_btn_text: Color32::from_rgb(0x68, 0x68, 0x68),
                cb_bg: Color32::from_rgb(0x1E, 0x1E, 0x1E),
                cb_border: Color32::from_rgb(0x90, 0x90, 0x98),
                tab_inactive_bg: Color32::from_rgb(0x14, 0x14, 0x14),
                tab_inactive_text: Color32::from_rgb(0xAA, 0xAA, 0xAA),
                tab_active_bg: Color32::from_rgb(0x1E, 0x1E, 0x1E),
                tab_active_text: Color32::from_rgb(0x25, 0x63, 0xEB),
                badge_latest_bg: Color32::from_rgb(0x26, 0x26, 0x26),
                badge_latest_text: Color32::WHITE,
                badge_rel_bg: Color32::from_rgb(0x26, 0x26, 0x26),
                badge_rel_text: Color32::from_rgb(0xAA, 0xAA, 0xAA),
                amber: Color32::from_rgb(0xD9, 0x77, 0x06),
                green: Color32::from_rgb(0x22, 0xC5, 0x5E),
                danger: Color32::from_rgb(0xEF, 0x44, 0x44),
                info_blue: Color32::from_rgb(0x00, 0x78, 0xD4),
                chip_bg: Color32::from_rgb(0x2C, 0x2C, 0x2C),
                chip_border: Color32::from_rgb(0x45, 0x45, 0x45),
                heat: [
                    Color32::from_rgb(0x26, 0x26, 0x26),
                    Color32::from_rgb(0x1E, 0x3A, 0x5F),
                    Color32::from_rgb(0x1D, 0x4E, 0xD8),
                    Color32::from_rgb(0x25, 0x63, 0xEB),
                    Color32::from_rgb(0x60, 0xA5, 0xFA),
                ],
            },
            ThemeKind::Light => Self {
                kind: ThemeKind::Light,
                is_dark: false,
                bg_window: Color32::from_rgb(0xF8, 0xFA, 0xFC),
                bg_card: Color32::WHITE,
                bg_card_alt: Color32::from_rgb(0xF1, 0xF5, 0xF9),
                bg_hover: Color32::from_rgb(0xF1, 0xF5, 0xF9),
                bg_input: Color32::WHITE,
                border: Color32::from_rgb(0xE2, 0xE8, 0xF0),
                border_strong: Color32::from_rgb(0xCB, 0xD5, 0xE1),
                text_primary: Color32::from_rgb(0x0F, 0x17, 0x2A),
                text_secondary: Color32::from_rgb(0x47, 0x55, 0x69),
                text_muted: Color32::from_rgb(0x94, 0xA3, 0xB8),
                clock_color: Color32::from_rgb(0x0F, 0x17, 0x2A),
                earned_color: Color32::from_rgb(0x0F, 0x7B, 0x0F),
                total_val_color: Color32::from_rgb(0x00, 0x78, 0xD4),
                accent: Color32::from_rgb(0x00, 0x78, 0xD4),
                accent_hover: Color32::from_rgb(0x10, 0x6E, 0xBE),
                accent_soft: Color32::from_rgba_unmultiplied(0x00, 0x78, 0xD4, 30),
                accent_btn_bg: Color32::from_rgb(0x1E, 0x29, 0x3B),
                accent_btn_hover: Color32::from_rgb(0x33, 0x41, 0x55),
                accent_btn_text: Color32::WHITE,
                normal_btn_bg: Color32::WHITE,
                normal_btn_hover: Color32::from_rgb(0xF1, 0xF5, 0xF9),
                normal_btn_border: Color32::from_rgb(0xCB, 0xD5, 0xE1),
                disabled_btn_bg: Color32::from_rgb(0xF8, 0xFA, 0xFC),
                disabled_btn_text: Color32::from_rgb(0x94, 0xA3, 0xB8),
                cb_bg: Color32::WHITE,
                cb_border: Color32::from_rgb(0x94, 0xA3, 0xB8),
                tab_inactive_bg: Color32::from_rgb(0xF1, 0xF5, 0xF9),
                tab_inactive_text: Color32::from_rgb(0x47, 0x55, 0x69),
                tab_active_bg: Color32::WHITE,
                tab_active_text: Color32::from_rgb(0x00, 0x78, 0xD4),
                badge_latest_bg: Color32::from_rgb(0xE1, 0xF5, 0xFE),
                badge_latest_text: Color32::from_rgb(0x00, 0x78, 0xD4),
                badge_rel_bg: Color32::from_rgb(0xF1, 0xF5, 0xF9),
                badge_rel_text: Color32::from_rgb(0x47, 0x55, 0x69),
                amber: Color32::from_rgb(0xD9, 0x77, 0x06),
                green: Color32::from_rgb(0x16, 0xA3, 0x4A),
                danger: Color32::from_rgb(0xDC, 0x26, 0x26),
                info_blue: Color32::from_rgb(0x00, 0x78, 0xD4),
                chip_bg: Color32::from_rgb(0xF1, 0xF5, 0xF9),
                chip_border: Color32::from_rgb(0xCB, 0xD5, 0xE1),
                heat: [
                    Color32::from_rgb(0xE2, 0xE8, 0xF0),
                    Color32::from_rgb(0xBF, 0xDB, 0xFE),
                    Color32::from_rgb(0x60, 0xA5, 0xFA),
                    Color32::from_rgb(0x25, 0x63, 0xEB),
                    Color32::from_rgb(0x1D, 0x4E, 0xD8),
                ],
            },
        }
    }
}

pub fn font_regular(size: f32) -> FontId {
    FontId::proportional(size)
}

pub fn font_semibold(size: f32) -> FontId {
    FontId::new(size, FontFamily::Name("semibold".into()))
}

pub fn font_bold(size: f32) -> FontId {
    FontId::new(size, FontFamily::Name("bold".into()))
}

pub fn font_mono(size: f32) -> FontId {
    FontId::monospace(size)
}

pub fn install_fonts(ctx: &egui::Context) {
    let mut fonts = FontDefinitions::default();
    let windir = std::env::var("WINDIR").unwrap_or_else(|_| "C:\\Windows".to_string());
    let fonts_dir = PathBuf::from(windir).join("Fonts");

    let try_load = |filename: &str| -> Option<Arc<FontData>> {
        let path = fonts_dir.join(filename);
        let bytes = std::fs::read(path).ok()?;
        Some(Arc::new(FontData::from_owned(bytes)))
    };

    let default_prop = fonts
        .families
        .get(&FontFamily::Proportional)
        .cloned()
        .unwrap_or_default();
    let default_mono = fonts
        .families
        .get(&FontFamily::Monospace)
        .cloned()
        .unwrap_or_default();

    let mut sym_fallbacks = Vec::new();
    if let Some(sym) = try_load("seguisym.ttf") {
        fonts.font_data.insert("segoe_sym".to_string(), sym);
        sym_fallbacks.push("segoe_sym".to_string());
    }

    if let Some(regular) = try_load("segoeui.ttf") {
        fonts.font_data.insert("segoe_regular".to_string(), regular);
        let mut chain = vec!["segoe_regular".to_string()];
        chain.extend(sym_fallbacks.clone());
        chain.extend(default_prop.clone());
        fonts.families.insert(FontFamily::Proportional, chain);
    }

    if let Some(sb) = try_load("seguisb.ttf") {
        fonts.font_data.insert("segoe_semibold".to_string(), sb);
        let mut chain = vec!["segoe_semibold".to_string()];
        chain.extend(sym_fallbacks.clone());
        chain.extend(default_prop.clone());
        fonts
            .families
            .insert(FontFamily::Name("semibold".into()), chain);
    } else {
        fonts
            .families
            .insert(FontFamily::Name("semibold".into()), default_prop.clone());
    }

    if let Some(bold) = try_load("segoeuib.ttf") {
        fonts.font_data.insert("segoe_bold".to_string(), bold);
        let mut chain = vec!["segoe_bold".to_string()];
        chain.extend(sym_fallbacks.clone());
        chain.extend(default_prop.clone());
        fonts.families.insert(FontFamily::Name("bold".into()), chain);
    } else {
        fonts
            .families
            .insert(FontFamily::Name("bold".into()), default_prop);
    }

    if let Some(mono) = try_load("consola.ttf") {
        fonts.font_data.insert("consolas".to_string(), mono);
        let mut chain = vec!["consolas".to_string()];
        chain.extend(sym_fallbacks);
        chain.extend(default_mono);
        fonts.families.insert(FontFamily::Monospace, chain);
    }

    ctx.set_fonts(fonts);
}

pub fn apply_theme(ctx: &egui::Context, style_name: &str) -> ThemePalette {
    let p = ThemePalette::for_style(style_name);
    let mut v = if p.is_dark {
        Visuals::dark()
    } else {
        Visuals::light()
    };

    v.panel_fill = p.bg_window;
    v.window_fill = p.bg_card;
    v.faint_bg_color = p.bg_card_alt;
    v.extreme_bg_color = p.bg_input;
    v.code_bg_color = p.bg_card_alt;
    v.override_text_color = Some(p.text_primary);
    v.window_corner_radius = CornerRadius::same(10);
    v.window_stroke = Stroke::new(1.0, p.border_strong);
    v.window_shadow = Shadow {
        offset: [0, 6],
        blur: 18,
        spread: 0,
        color: Color32::from_black_alpha(if p.is_dark { 130 } else { 36 }),
    };
    v.popup_shadow = Shadow {
        offset: [0, 6],
        blur: 16,
        spread: 0,
        color: Color32::from_black_alpha(if p.is_dark { 140 } else { 42 }),
    };
    v.menu_corner_radius = CornerRadius::same(8);
    v.selection.bg_fill = p.accent_soft;
    v.selection.stroke = Stroke::new(1.0, p.accent);

    v.widgets.noninteractive.bg_fill = p.bg_card;
    v.widgets.noninteractive.weak_bg_fill = p.bg_card;
    v.widgets.noninteractive.bg_stroke = Stroke::new(1.0, p.border);
    v.widgets.noninteractive.fg_stroke = Stroke::new(1.0, p.text_primary);
    v.widgets.noninteractive.corner_radius = CornerRadius::same(6);

    v.widgets.inactive.bg_fill = p.normal_btn_bg;
    v.widgets.inactive.weak_bg_fill = p.normal_btn_bg;
    v.widgets.inactive.bg_stroke = Stroke::new(1.0, p.normal_btn_border);
    v.widgets.inactive.fg_stroke = Stroke::new(1.0, p.text_primary);
    v.widgets.inactive.corner_radius = CornerRadius::same(6);

    v.widgets.hovered.bg_fill = p.normal_btn_hover;
    v.widgets.hovered.weak_bg_fill = p.normal_btn_hover;
    v.widgets.hovered.bg_stroke = Stroke::new(1.0, p.border_strong);
    v.widgets.hovered.fg_stroke = Stroke::new(1.0, p.text_primary);
    v.widgets.hovered.corner_radius = CornerRadius::same(6);
    v.widgets.hovered.expansion = 0.0;

    v.widgets.active.bg_fill = p.bg_hover;
    v.widgets.active.weak_bg_fill = p.bg_hover;
    v.widgets.active.bg_stroke = Stroke::new(1.0, p.accent);
    v.widgets.active.fg_stroke = Stroke::new(1.0, p.text_primary);
    v.widgets.active.corner_radius = CornerRadius::same(6);
    v.widgets.active.expansion = 0.0;

    v.widgets.open.bg_fill = p.normal_btn_hover;
    v.widgets.open.weak_bg_fill = p.normal_btn_hover;
    v.widgets.open.bg_stroke = Stroke::new(1.0, p.accent);
    v.widgets.open.fg_stroke = Stroke::new(1.0, p.text_primary);
    v.widgets.open.corner_radius = CornerRadius::same(6);

    let target_theme = if p.is_dark {
        egui::Theme::Dark
    } else {
        egui::Theme::Light
    };
    ctx.set_theme(target_theme);
    ctx.set_visuals_of(target_theme, v);
    ctx.all_styles_mut(|s| {
        s.spacing.scroll = egui::style::ScrollStyle {
            bar_width: 6.0,
            floating_width: 6.0,
            floating_allocated_width: 8.0,
            bar_inner_margin: 3.0,
            bar_outer_margin: 2.0,
            floating: true,
            ..Default::default()
        };
        s.interaction.selectable_labels = false;
    });

    p
}

pub fn parse_hex_color(hex: &str, fallback: Color32) -> Color32 {
    let s = hex.trim().trim_start_matches('#');
    if s.len() == 6 {
        if let (Ok(r), Ok(g), Ok(b)) = (
            u8::from_str_radix(&s[0..2], 16),
            u8::from_str_radix(&s[2..4], 16),
            u8::from_str_radix(&s[4..6], 16),
        ) {
            return Color32::from_rgb(r, g, b);
        }
    }
    fallback
}
