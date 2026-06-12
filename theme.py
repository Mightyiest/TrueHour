"""
TrueHour — Unified Theme & Design System
Houses colors, global stylesheets, palette configurations, and SVG paint utilities.
"""
import os
import math
from PyQt6.QtCore import Qt, QSize, QPointF, QRectF
from PyQt6.QtGui import QColor, QPalette, QIcon, QPixmap, QPainter, QPen, QPainterPath

# ── Design Tokens & Color Palettes ───────────────────────────────────
BG_WHITE      = "#FFFFFF"
BG_SURFACE    = "#F8FAFC"
BG_HOVER      = "#F1F5F9"
BG_CARD       = "#FFFFFF"
ACCENT        = "#0078D4"
ACCENT_HOVER  = "#106EBE"
ACCENT_LIGHT  = "#F0FDF4"
GREEN_STATUS  = "#16A34A"
RED_STATUS    = "#EF4444"
ORANGE        = "#F59E0B"
TEXT_PRIMARY  = "#0F172A"
TEXT_SECONDARY= "#475569"
TEXT_DISABLED = "#94A3B8"
BORDER        = "#E2E8F0"
FONT_FAMILY   = "Segoe UI"

PROJECT_COLORS = {
    "Development": "#4F46E5",  # Indigo
    "Design": "#EC4899",       # Pink
    "Research": "#10B981",     # Emerald
    "Documentation": "#F59E0B",# Amber
    "Communication": "#06B6D4",# Cyan
    "Management": "#8B5CF6",   # Purple
    "Unassigned": "#64748B",   # Slate
}

def get_tag_color(tag_name: str) -> str:
    if tag_name in PROJECT_COLORS:
        return PROJECT_COLORS[tag_name]
    palette = list(PROJECT_COLORS.values())[:-1]
    idx = sum(ord(c) for c in tag_name) % len(palette)
    return palette[idx]

def get_light_palette() -> QPalette:
    palette = QPalette()
    
    # Active Colors (Modern Minimalist Light Style based on index.html)
    palette.setColor(QPalette.ColorRole.Window, QColor("#F8FAFC"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#0F172A"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#F8FAFC"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#0F172A"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#0F172A"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#0F172A"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.Link, QColor("#0078D4"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#F1F5F9"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#0078D4"))
    
    # Inactive Colors (match Active to prevent visual blinking/flickering)
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Window, QColor("#F8FAFC"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.WindowText, QColor("#0F172A"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Base, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.AlternateBase, QColor("#F8FAFC"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.ToolTipBase, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.ToolTipText, QColor("#0F172A"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Text, QColor("#0F172A"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Button, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.ButtonText, QColor("#0F172A"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.BrightText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Link, QColor("#0078D4"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Highlight, QColor("#F1F5F9"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.HighlightedText, QColor("#0078D4"))
    
    # Disabled Colors (elegant grayish states)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Window, QColor("#F8FAFC"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor("#94A3B8"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor("#F8FAFC"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.AlternateBase, QColor("#F8FAFC"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ToolTipBase, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ToolTipText, QColor("#94A3B8"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#94A3B8"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, QColor("#F8FAFC"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#94A3B8"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.BrightText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Link, QColor("#0078D4"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor("#F1F5F9"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, QColor("#94A3B8"))
    
    return palette

def get_dark_palette() -> QPalette:
    palette = QPalette()
    
    # Active Colors (Frankfurter Minimalistic Dark Theme)
    palette.setColor(QPalette.ColorRole.Window, QColor("#141414"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#e0e0e0"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#1e1e1e"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#262626"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#1e1e1e"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#e0e0e0"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#e0e0e0"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#1e1e1e"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#e0e0e0"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.Link, QColor("#d1d5db"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#262626"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    
    # Inactive Colors (match Active)
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Window, QColor("#141414"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.WindowText, QColor("#e0e0e0"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Base, QColor("#1e1e1e"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.AlternateBase, QColor("#262626"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.ToolTipBase, QColor("#1e1e1e"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.ToolTipText, QColor("#e0e0e0"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Text, QColor("#e0e0e0"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Button, QColor("#1e1e1e"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.ButtonText, QColor("#e0e0e0"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.BrightText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Link, QColor("#d1d5db"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Highlight, QColor("#262626"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    
    # Disabled Colors (grayed out dark theme)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Window, QColor("#141414"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor("#888888"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor("#141414"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.AlternateBase, QColor("#141414"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ToolTipBase, QColor("#1e1e1e"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ToolTipText, QColor("#888888"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#888888"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, QColor("#141414"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#888888"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.BrightText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Link, QColor("#d1d5db"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor("#262626"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, QColor("#888888"))
    
    return palette

_GENERATED_CHECKMARKS = set()

# ── Dynamic Checkmark Icon Generator ─────────────────────────────────
def ensure_checkmark_icon(is_dark: bool = False) -> str:
    from config import get_app_data_dir
    filename = "checkmark_dark.png" if is_dark else "checkmark_light.png"
    checkmark_path = os.path.join(get_app_data_dir(), filename).replace("\\", "/")
    
    if filename in _GENERATED_CHECKMARKS and os.path.exists(checkmark_path):
        return checkmark_path
        
    # Recreate the checkmark file to ensure any incorrect cached fallbacks are overwritten with the correct color
    try:
        from PyQt6.QtGui import QPixmap, QPainter, QColor, QPen
        from PyQt6.QtCore import Qt
        
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        fill_color = QColor(20, 20, 20) if is_dark else QColor(255, 255, 255)
        pen = QPen(fill_color, 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        
        painter.drawLine(4, 8, 7, 11)
        painter.drawLine(7, 11, 12, 4)
        painter.end()
        
        pixmap.save(checkmark_path, "PNG")
        _GENERATED_CHECKMARKS.add(filename)
    except Exception:
        try:
            import base64
            if is_dark:
                # Dark checkmark fallback
                png_base64 = b"iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABGdBTUEAALGPC/xhBQAAADpJREFUOBFjYBgFMMCEw/wnHGaE4D//kXWgm2DCwADCYEDQAWBsICwAGBsYiwfG4oHRcMAoGAWDEAMAANbQDBW/k19vAAAAAElFTkSuQmCC"
            else:
                # Light checkmark fallback
                png_base64 = b"iVBORw0KGgoAAAANSUhEUgAAAAwAAAAMCAYAAABWdVznAAAAGXRFWHRTb2Z0d2FyZQBBZG9iZSBJbWFnZVJlYWR5ccllPAAAAGRJREFUeNpi7OzsfM/AwMAAxIxADEjEwIhFEEUDkI+iCcQnEUTRAOKjCIIo6kBsEEUA1kC4gBEMwAog3gDEm4B4GxCPwWMEWAPEX4F4NhCPBWIjIAby2UA8k4GBgRcggAEA4d86bO+E6JkAAAAASUVORK5CYII="
            with open(checkmark_path, "wb") as f:
                f.write(base64.b64decode(png_base64))
            _GENERATED_CHECKMARKS.add(filename)
        except Exception:
            pass
    return checkmark_path

# ── Icon Painters ──────────────────────────────────────────────────
def get_svg_icon(svg_content, size=QSize(20, 20), color_hex=None) -> QIcon:
    if color_hex:
        if isinstance(svg_content, bytes):
            content_str = svg_content.decode("utf-8")
        else:
            content_str = svg_content
        for default_color in ["#0078D4", "#0F7B0F", "#FF0000"]:
            content_str = content_str.replace(default_color, color_hex)
            content_str = content_str.replace(default_color.lower(), color_hex.lower())
        svg_content = content_str.encode("utf-8")

    pixmap = QPixmap(size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    try:
        from PyQt6.QtSvg import QSvgRenderer
        from PyQt6.QtCore import QByteArray
        renderer = QSvgRenderer(QByteArray(svg_content))
        renderer.render(painter, QRectF(pixmap.rect()))
    except Exception:
        painter.setPen(QPen(QColor(color_hex or "#0078D4"), 2))
        painter.drawEllipse(2, 2, 16, 16)
    painter.end()
    return QIcon(pixmap)

def create_minimalist_icon(icon_type, color_hex, size=16) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color_hex))
    pen.setWidthF(1.5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if icon_type == "chart":
        painter.drawRoundedRect(QRectF(2.0, 9.0, 3.0, 5.0), 1.0, 1.0)
        painter.drawRoundedRect(QRectF(6.5, 5.0, 3.0, 9.0), 1.0, 1.0)
        painter.drawRoundedRect(QRectF(11.0, 2.0, 3.0, 12.0), 1.0, 1.0)
    elif icon_type == "folder":
        painter.drawRoundedRect(QRectF(1.5, 5.0, 13.0, 9.0), 1.5, 1.5)
        path = QPainterPath()
        path.moveTo(3.0, 5.0)
        path.lineTo(3.0, 2.5)
        path.lineTo(6.5, 2.5)
        path.lineTo(8.0, 5.0)
        painter.drawPath(path)
    elif icon_type == "settings":
        painter.drawEllipse(QPointF(8.0, 8.0), 2.2, 2.2)
        painter.drawEllipse(QPointF(8.0, 8.0), 5.0, 5.0)
        for i in range(8):
            angle = i * math.pi / 4
            c = math.cos(angle)
            s = math.sin(angle)
            painter.drawLine(
                QPointF(8.0 + 4.5 * c, 8.0 + 4.5 * s),
                QPointF(8.0 + 7.0 * c, 8.0 + 7.0 * s)
            )
    painter.end()
    return QIcon(pixmap)

# ── Unified Styled Window Palette (QSS) ──────────────────────────────
def get_qss_style(is_dark: bool) -> str:
    # Color tokens based on theme
    bg_window = "#141414" if is_dark else "#F8FAFC"
    bg_widget = "#1e1e1e" if is_dark else "#FFFFFF"
    text_primary = "#e0e0e0" if is_dark else "#0F172A"
    text_secondary = "#aaa" if is_dark else "#475569"
    border_color = "#333333" if is_dark else "#E2E8F0"
    accent = "#d1d5db" if is_dark else "#0078D4"
    accent_hover = "#ffffff" if is_dark else "#106EBE"
    bg_hover = "#262626" if is_dark else "#F1F5F9"
    accent_btn_text = "#141414" if is_dark else "#FFFFFF"
    
    return f"""
QWidget {{
    color: {text_primary};
    background-color: transparent;
}}
QMainWindow {{
    background-color: {bg_window};
}}
QDialog {{
    background-color: {bg_window};
}}
QWidget#scroll_widget, 
QWidget#sessions_widget, 
QWidget#recoveries_widget, 
QWidget#scroll_content,
QWidget#report_scroll_widget {{
    background-color: {bg_widget};
}}
QLabel {{
    color: {text_primary};
}}
QFrame#MainCard {{
    background-color: {bg_widget};
    border-radius: 12px;
    border: 1px solid {border_color};
}}
QFrame#AppListCard {{
    background-color: {bg_widget};
    border-radius: 12px;
    border: 1px solid {border_color};
}}
QScrollArea {{
    border: none;
    background-color: transparent;
}}
QScrollBar:vertical {{
    background: {bg_widget};
    width: 6px;
    margin: 0px;
}}
QScrollBar::handle:vertical {{
    background: {border_color};
    min-height: 20px;
    border-radius: 3px;
}}
QScrollBar::handle:vertical:hover {{
    background: {text_secondary};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    background: {bg_widget};
    height: 6px;
    margin: 0px;
}}
QScrollBar::handle:horizontal {{
    background: {border_color};
    min-width: 20px;
    border-radius: 3px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {text_secondary};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}
QPushButton {{
    font-family: '{FONT_FAMILY}';
    font-size: 13px;
}}
QPushButton#AccentButton {{
    background-color: {accent};
    color: {accent_btn_text};
    border: none;
    border-radius: 14px;
    padding: 6px 16px;
    font-weight: bold;
}}
QPushButton#AccentButton:hover {{
    background-color: {accent_hover};
    color: {accent_btn_text};
}}
QPushButton#AccentButton:pressed {{
    background-color: {accent_hover};
    color: {accent_btn_text};
}}
QPushButton#AccentButton:disabled {{
    background-color: {bg_hover};
    color: {text_secondary};
}}
QPushButton#NormalButton {{
    background-color: {bg_widget};
    color: {text_primary};
    border: 1px solid {border_color};
    border-radius: 14px;
    padding: 6px 16px;
    font-weight: 500;
}}
QPushButton#NormalButton:hover {{
    background-color: {bg_hover};
    border-color: {border_color};
    color: {text_primary};
}}
QPushButton#NormalButton:pressed {{
    background-color: {bg_hover};
    border-color: {border_color};
    color: {text_primary};
}}
QPushButton#NormalButton:disabled {{
    background-color: {bg_window};
    color: {text_secondary};
    border: 1px solid {border_color};
}}
QPushButton#RedButton {{
    background-color: #EF4444;
    color: #FFFFFF;
    border: none;
    border-radius: 14px;
    padding: 6px 16px;
    font-weight: bold;
}}
QPushButton#RedButton:hover {{
    background-color: #DC2626;
    color: #FFFFFF;
}}
QPushButton#RedButton:pressed {{
    background-color: #B91C1C;
    color: #FFFFFF;
}}
QPushButton#RedButton:disabled {{
    background-color: {bg_window};
    color: {text_secondary};
}}
QLineEdit {{
    background-color: {bg_widget};
    border: 1px solid {border_color};
    border-radius: 6px;
    padding: 4px 8px;
    color: {text_primary};
    font-family: '{FONT_FAMILY}';
    font-size: 13px;
}}
QLineEdit:focus {{
    border: 1px solid {accent};
}}
QComboBox {{
    background-color: {bg_widget};
    border: 1px solid {border_color};
    border-radius: 6px;
    padding: 4px 8px;
    color: {text_primary};
    font-family: '{FONT_FAMILY}';
    font-size: 13px;
}}
QComboBox:focus {{
    border: 1px solid {accent};
}}
QComboBox QAbstractItemView {{
    background-color: {bg_widget};
    color: {text_primary};
    border: 1px solid {border_color};
    selection-background-color: {bg_hover};
    selection-color: {accent};
}}
QTabWidget::pane {{
    border: 1px solid {border_color};
    background-color: {bg_widget};
    border-radius: 8px;
}}
QTabBar::tab {{
    background-color: {bg_window};
    color: {text_secondary};
    padding: 6px 16px;
    font-family: '{FONT_FAMILY}';
    font-size: 13px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    border: 1px solid {border_color};
    border-bottom: none;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background-color: {bg_widget};
    color: {accent};
    font-weight: bold;
    border: 1px solid {border_color};
    border-bottom: none;
}}
QTableWidget {{
    background-color: {bg_widget};
    color: {text_primary};
    border: 1px solid {border_color};
    gridline-color: {bg_window};
    font-family: '{FONT_FAMILY}';
    font-size: 13px;
}}
QTableWidget::item {{
    color: {text_primary};
    background-color: {bg_widget};
}}
QTableWidget::item:selected {{
    background-color: {bg_hover};
    color: {accent};
}}
QHeaderView::section {{
    background-color: {bg_window};
    color: {text_secondary};
    padding: 6px;
    border: 1px solid {border_color};
    font-family: '{FONT_FAMILY}';
    font-size: 12px;
    font-weight: bold;
}}
QTableCornerButton::section {{
    background-color: {bg_window};
    border: 1px solid {border_color};
}}
QCheckBox {{
    color: {text_primary};
    font-family: '{FONT_FAMILY}';
    font-size: 13px;
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1.5px solid {text_secondary};
    border-radius: 3px;
    background-color: {bg_widget};
}}
QCheckBox::indicator:hover {{
    border-color: {accent};
    background-color: {bg_hover};
}}
QCheckBox::indicator:checked {{
    border-color: {accent};
    background-color: {accent};
    image: url(CHECKMARK_PATH);
}}
QCheckBox::indicator:checked:hover {{
    border-color: {accent_hover};
    background-color: {accent_hover};
}}
QCheckBox::indicator:disabled {{
    border-color: {border_color};
    background-color: {bg_window};
}}
QGroupBox {{
    font-family: '{FONT_FAMILY}';
    font-weight: bold;
    font-size: 12px;
    color: {text_secondary};
    border: 1px solid {border_color};
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 12px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding-left: 3px;
    padding-right: 3px;
}}
QMenu {{
    background-color: {bg_widget};
    color: {text_primary};
    border: 1px solid {border_color};
}}
QMenu::item {{
    padding: 6px 20px;
    background-color: transparent;
}}
QMenu::item:selected {{
    background-color: {bg_hover};
    color: {accent};
}}
QMenu::separator {{
    height: 1px;
    background-color: {border_color};
    margin: 4px 0px;
}}
QMessageBox {{
    background-color: {bg_window};
}}
QMessageBox QLabel {{
    color: {text_primary};
}}
QMessageBox QPushButton {{
    background-color: {bg_widget};
    color: {text_primary};
    border: 1px solid {border_color};
    border-radius: 14px;
    padding: 4px 12px;
}}
"""
