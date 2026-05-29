"""
FocusLog — Unified Theme & Design System
Houses colors, global stylesheets, palette configurations, and SVG paint utilities.
"""
import os
import sys
import math
from PyQt6.QtCore import Qt, QSize, QPointF, QRectF
from PyQt6.QtGui import QColor, QPalette, QIcon, QPixmap, QPainter, QPen, QBrush, QPainterPath

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

# ── Dynamic Checkmark Icon Generator ─────────────────────────────────
def ensure_checkmark_icon() -> str:
    from config import get_app_data_dir
    checkmark_path = os.path.join(get_app_data_dir(), "checkmark.png").replace("\\", "/")
    if not os.path.exists(checkmark_path):
        try:
            from PIL import Image, ImageDraw
            img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.line([(4, 8), (7, 11), (12, 4)], fill=(255, 255, 255, 255), width=2, joint="round")
            img.save(checkmark_path, "PNG")
        except Exception:
            try:
                import base64
                png_base64 = b"iVBORw0KGgoAAAANSUhEUgAAAAwAAAAMCAYAAABWdVznAAAAGXRFWHRTb2Z0d2FyZQBBZG9iZSBJbWFnZVJlYWR5ccllPAAAAGRJREFUeNpi7OzsfM/AwMAAxIxADEjEwIhFEEUDkI+iCcQnEUTRAOKjCIIo6kBsEEUA1kC4gBEMwAog3gDEm4B4GxCPwWMEWAPEX4F4NhCPBWIjIAby2UA8k4GBgRcggAEA4d86bO+E6JkAAAAASUVORK5CYII="
                with open(checkmark_path, "wb") as f:
                    f.write(base64.b64decode(png_base64))
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
QSS_STYLE = """
QWidget {
    color: #0F172A;
    background-color: transparent;
}
QMainWindow {
    background-color: #F8FAFC;
}
QDialog {
    background-color: #F8FAFC;
}
QWidget#scroll_widget, 
QWidget#sessions_widget, 
QWidget#recoveries_widget, 
QWidget#scroll_content,
QWidget#report_scroll_widget {
    background-color: #FFFFFF;
}
QLabel {
    color: #0F172A;
}
QFrame#MainCard {
    background-color: #FFFFFF;
    border-radius: 12px;
    border: 1px solid #E2E8F0;
}
QFrame#AppListCard {
    background-color: #FFFFFF;
    border-radius: 12px;
    border: 1px solid #E2E8F0;
}
QScrollArea {
    border: none;
    background-color: transparent;
}
QScrollBar:vertical {
    background: #FFFFFF;
    width: 6px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #E2E8F0;
    min-height: 20px;
    border-radius: 3px;
}
QScrollBar::handle:vertical:hover {
    background: #CBD5E1;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    background: #FFFFFF;
    height: 6px;
    margin: 0px;
}
QScrollBar::handle:horizontal {
    background: #E2E8F0;
    min-width: 20px;
    border-radius: 3px;
}
QScrollBar::handle:horizontal:hover {
    background: #CBD5E1;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}
QPushButton {
    font-family: 'Segoe UI';
    font-size: 13px;
}
QPushButton#AccentButton {
    background-color: #0F172A;
    color: #FFFFFF;
    border: none;
    border-radius: 14px;
    padding: 6px 16px;
    font-weight: bold;
}
QPushButton#AccentButton:hover {
    background-color: #1E293B;
}
QPushButton#AccentButton:disabled {
    background-color: #F1F5F9;
    color: #94A3B8;
}
QPushButton#NormalButton {
    background-color: #FFFFFF;
    color: #0F172A;
    border: 1px solid #E2E8F0;
    border-radius: 14px;
    padding: 6px 16px;
    font-weight: 500;
}
QPushButton#NormalButton:hover {
    background-color: #F1F5F9;
    border-color: #CBD5E1;
}
QPushButton#NormalButton:disabled {
    background-color: #F8FAFC;
    color: #94A3B8;
    border: 1px solid #E2E8F0;
}
QPushButton#RedButton {
    background-color: #EF4444;
    color: #FFFFFF;
    border: none;
    border-radius: 14px;
    padding: 6px 16px;
    font-weight: bold;
}
QPushButton#RedButton:hover {
    background-color: #DC2626;
}
QPushButton#RedButton:disabled {
    background-color: #F8FAFC;
    color: #94A3B8;
}
QLineEdit {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 6px;
    padding: 4px 8px;
    color: #0F172A;
    font-family: 'Segoe UI';
    font-size: 13px;
}
QLineEdit:focus {
    border: 1px solid #0078D4;
}
QComboBox {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 6px;
    padding: 4px 8px;
    color: #0F172A;
    font-family: 'Segoe UI';
    font-size: 13px;
}
QComboBox:focus {
    border: 1px solid #0078D4;
}
QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    color: #0F172A;
    border: 1px solid #E2E8F0;
    selection-background-color: #F1F5F9;
    selection-color: #0078D4;
}
QTabWidget::pane {
    border: 1px solid #E2E8F0;
    background-color: #FFFFFF;
    border-radius: 8px;
}
QTabBar::tab {
    background-color: #F8FAFC;
    color: #475569;
    padding: 6px 16px;
    font-family: 'Segoe UI';
    font-size: 13px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    border: 1px solid #E2E8F0;
    border-bottom: none;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #FFFFFF;
    color: #0078D4;
    font-weight: bold;
    border: 1px solid #CBD5E1;
    border-bottom: none;
}
QTableWidget {
    background-color: #FFFFFF;
    color: #0F172A;
    border: 1px solid #E2E8F0;
    gridline-color: #F8FAFC;
    font-family: 'Segoe UI';
    font-size: 13px;
}
QTableWidget::item {
    color: #0F172A;
    background-color: #FFFFFF;
}
QTableWidget::item:selected {
    background-color: #F1F5F9;
    color: #0078D4;
}
QHeaderView::section {
    background-color: #F8FAFC;
    color: #475569;
    padding: 6px;
    border: 1px solid #E2E8F0;
    font-family: 'Segoe UI';
    font-size: 12px;
    font-weight: bold;
}
QTableCornerButton::section {
    background-color: #F8FAFC;
    border: 1px solid #E2E8F0;
}
QCheckBox {
    color: #0F172A;
    font-family: 'Segoe UI';
    font-size: 13px;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1.5px solid #94A3B8;
    border-radius: 3px;
    background-color: #FFFFFF;
}
QCheckBox::indicator:hover {
    border-color: #0078D4;
    background-color: #F1F5F9;
}
QCheckBox::indicator:checked {
    border-color: #0078D4;
    background-color: #0078D4;
    image: url(CHECKMARK_PATH);
}
QCheckBox::indicator:checked:hover {
    border-color: #106EBE;
    background-color: #106EBE;
}
QCheckBox::indicator:disabled {
    border-color: #E2E8F0;
    background-color: #F8FAFC;
}
QGroupBox {
    font-family: 'Segoe UI';
    font-weight: bold;
    font-size: 12px;
    color: #475569;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 12px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding-left: 3px;
    padding-right: 3px;
}
QMenu {
    background-color: #FFFFFF;
    color: #0F172A;
    border: 1px solid #E2E8F0;
}
QMenu::item {
    padding: 6px 20px;
    background-color: transparent;
}
QMenu::item:selected {
    background-color: #F1F5F9;
    color: #0078D4;
}
QMenu::separator {
    height: 1px;
    background-color: #E2E8F0;
    margin: 4px 0px;
}
QMessageBox {
    background-color: #F8FAFC;
}
QMessageBox QLabel {
    color: #0F172A;
}
QMessageBox QPushButton {
    background-color: #FFFFFF;
    color: #0F172A;
    border: 1px solid #E2E8F0;
    border-radius: 14px;
    padding: 4px 12px;
}
"""
