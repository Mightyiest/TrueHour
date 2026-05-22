"""
FocusLog — Main Application UI (PyQt6).
Lightweight Windows desktop time tracker with a clean Windows 11-style light theme.
"""
import sys
import os
import time
import ctypes
import threading
from datetime import datetime, timedelta
import json
import io
import logging

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QCheckBox, QComboBox, QLineEdit,
    QDialog, QFormLayout, QGroupBox, QMenu, QMessageBox, QFileDialog,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, QSize, QObject, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QBrush, QPen, QImage, QPixmap, QIcon, QPainterPath, QPalette

from tracker import AppTracker, AUTO_EXCLUDE_FILE, create_auto_excluded_if_missing
from appinfo import get_icon_image, OVERRIDES_FILE
from config import get_app_data_dir
from secure_time import get_detector
from report import (
    format_duration, format_duration_hms, build_report_data,
    export_txt, export_json, export_csv, export_csv_history,
    save_to_autosave, save_to_history, load_session_json,
)
from version import VERSION_SHORT, VERSION_FULL

# Configure logging for the app module
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)

# ── Force Windows to use Light Mode ──────────────────────────────────
def _force_light_mode():
    try:
        # 0=Default, 1=AllowDark, 2=ForceDark, 3=ForceLight
        ctypes.windll.uxtheme.SetPreferredAppMode(3)
        ctypes.windll.uxtheme.FlushMenuThemes()
    except Exception:
        pass

_force_light_mode()

# ── Robust Application-Wide Light Palette ─────────────────────────────
def get_light_palette():
    palette = QPalette()
    
    # Active Colors (Clean Windows 11 Light Style)
    palette.setColor(QPalette.ColorRole.Window, QColor("#F3F3F3"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#1A1A1A"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#FBFBFB"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#1A1A1A"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#1A1A1A"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#1A1A1A"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.Link, QColor("#0078D4"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#E8F1FB"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#0078D4"))
    
    # Inactive Colors (match Active to prevent visual blinking/flickering)
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Window, QColor("#F3F3F3"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.WindowText, QColor("#1A1A1A"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Base, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.AlternateBase, QColor("#FBFBFB"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.ToolTipBase, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.ToolTipText, QColor("#1A1A1A"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Text, QColor("#1A1A1A"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Button, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.ButtonText, QColor("#1A1A1A"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.BrightText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Link, QColor("#0078D4"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Highlight, QColor("#E8F1FB"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.HighlightedText, QColor("#0078D4"))
    
    # Disabled Colors (elegant grayish states)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Window, QColor("#F3F3F3"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor("#ABABAB"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor("#F3F3F3"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.AlternateBase, QColor("#FBFBFB"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ToolTipBase, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ToolTipText, QColor("#ABABAB"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#ABABAB"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, QColor("#F3F3F3"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#ABABAB"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.BrightText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Link, QColor("#0078D4"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor("#E9E9E9"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, QColor("#ABABAB"))
    
    return palette

# ── Windows 11 Fluent Light Palette ──────────────────────────────────
BG_WHITE      = "#FFFFFF"
BG_SURFACE    = "#F3F3F3"
BG_HOVER      = "#E9E9E9"
BG_CARD       = "#FBFBFB"
ACCENT        = "#0078D4"
ACCENT_HOVER  = "#106EBE"
ACCENT_LIGHT  = "#E8F1FB"
GREEN_STATUS  = "#0F7B0F"
RED_STATUS    = "#C42B1C"
ORANGE        = "#CA5010"
TEXT_PRIMARY  = "#1A1A1A"
TEXT_SECONDARY= "#616161"
TEXT_DISABLED = "#ABABAB"
BORDER        = "#E0E0E0"
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

# ── Icon Path ──────────────────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    ICON_DIR = sys._MEIPASS
else:
    ICON_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(ICON_DIR, "icon.ico")
APP_SETTINGS_FILE = os.path.join(get_app_data_dir(), "app_settings.json")

# Helper function to convert PIL Image to QPixmap
def pil_to_pixmap(pil_img):
    if not pil_img:
        return None
    try:
        buffer = io.BytesIO()
        pil_img.save(buffer, format="PNG")
        qimg = QImage()
        qimg.loadFromData(buffer.getvalue(), "PNG")
        return QPixmap.fromImage(qimg)
    except Exception as e:
        logger.debug(f"Failed to convert PIL Image to QPixmap: {e}")
        return None

def ensure_checkmark_icon():
    checkmark_path = os.path.join(get_app_data_dir(), "checkmark.png").replace("\\", "/")
    if not os.path.exists(checkmark_path):
        try:
            from PIL import Image, ImageDraw
            img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.line([(4, 8), (7, 11), (12, 4)], fill=(255, 255, 255, 255), width=2, joint="round")
            img.save(checkmark_path, "PNG")
        except Exception as e:
            logger.debug(f"Failed to dynamically draw checkmark.png: {e}")
            try:
                import base64
                png_base64 = b"iVBORw0KGgoAAAANSUhEUgAAAAwAAAAMCAYAAABWdVznAAAAGXRFWHRTb2Z0d2FyZQBBZG9iZSBJbWFnZVJlYWR5ccllPAAAAGRJREFUeNpi7OzsfM/AwMAAxIxADEjEwIhFEEUDkI+iCcQnEUTRAOKjCIIo6kBsEEUA1kC4gBEMwAog3gDEm4B4GxCPwWMEWAPEX4F4NhCPBWIjIAby2UA8k4GBgRcggAEA4d86bO+E6JkAAAAASUVORK5CYII="
                with open(checkmark_path, "wb") as f:
                    f.write(base64.b64decode(png_base64))
            except Exception as e2:
                logger.debug(f"Fallback checkmark writing failed: {e2}")
    return checkmark_path

# ── Thread-Safe Signals ──────────────────────────────────────────────
class TrackerSignals(QObject):
    update_signal = pyqtSignal()
    icon_loaded_signal = pyqtSignal(str, str, object)  # exe_path, app_name, PIL Image (or None)

# ── Modular Header Bar ───────────────────────────────────────────────
class HeaderBar(QFrame):
    def __init__(self, parent, cmd_report, cmd_sessions, cmd_settings):
        super().__init__(parent)
        self.setObjectName("HeaderBar")
        self.setFixedHeight(44)
        
        self.setStyleSheet("""
            #HeaderBar {
                background-color: #FFFFFF;
                border-bottom: 1px solid #E0E0E0;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(8)
        
        logo = QLabel("📊 FocusLog", self)
        logo.setStyleSheet("color: #0078D4; font-size: 15px; font-weight: bold; font-family: 'Segoe UI';")
        layout.addWidget(logo)
        
        layout.addStretch()
        
        self.live_report_btn = QPushButton("📊 View Report", self)
        self.live_report_btn.setStyleSheet("""
            QPushButton {
                color: #0078D4;
                font-size: 12px;
                font-weight: bold;
                font-family: 'Segoe UI';
                background: none;
                border: none;
            }
            QPushButton:hover {
                text-decoration: underline;
            }
        """)
        self.live_report_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.live_report_btn.clicked.connect(cmd_report)
        layout.addWidget(self.live_report_btn)
        
        self.sessions_btn = QPushButton("📂", self)
        self.sessions_btn.setToolTip("Session Manager")
        self.sessions_btn.setFixedSize(28, 28)
        self.sessions_btn.setStyleSheet("""
            QPushButton {
                color: #616161;
                font-size: 16px;
                background: none;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #E9E9E9;
                color: #0078D4;
            }
        """)
        self.sessions_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sessions_btn.clicked.connect(cmd_sessions)
        layout.addWidget(self.sessions_btn)
        
        self.settings_btn = QPushButton("⚙", self)
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.setFixedSize(28, 28)
        self.settings_btn.setStyleSheet("""
            QPushButton {
                color: #616161;
                font-size: 16px;
                background: none;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #E9E9E9;
                color: #0078D4;
            }
        """)
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.clicked.connect(cmd_settings)
        layout.addWidget(self.settings_btn)

# ── Custom Segmented Paint-Based Bar ───────────────────────────────
class SegmentedAllocationBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.project_breakdown = []
        self.setFixedHeight(20)

    def set_breakdown(self, breakdown):
        self.project_breakdown = breakdown
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w = self.width()
        h = self.height()
        
        total_secs = sum(pb["seconds"] for pb in self.project_breakdown)
        if total_secs <= 0:
            # Draw placeholder gray bar
            painter.setBrush(QBrush(QColor("#E2E8F0")))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(0, 0, w, h, 6, 6)
            return

        # Setup rounded corners clipping path
        path = QPainterPath()
        path.addRoundedRect(0.0, 0.0, float(w), float(h), 6.0, 6.0)
        painter.setClipPath(path)

        current_x = 0.0
        for pb in self.project_breakdown:
            pct = pb["seconds"] / total_secs
            segment_w = pct * w
            color_hex = pb.get("color", "#64748B")
            painter.setBrush(QBrush(QColor(color_hex)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(int(current_x), 0, int(segment_w + 1), h)
            current_x += segment_w

# ── Custom List App Usage Row Widget ─────────────────────────────────
class AppUsageRow(QFrame):
    def __init__(self, app_name, secs, included, tag, exe_path, on_toggle, on_tag_click, parent=None):
        super().__init__(parent)
        self.app_name = app_name
        self.secs = secs
        self.included = included
        self.tag = tag
        self.exe_path = exe_path
        self.on_toggle = on_toggle
        self.on_tag_click = on_tag_click
        
        self.setObjectName("AppUsageRow")
        self.init_ui()
        
    def init_ui(self):
        self.setFixedHeight(32)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(8)
        
        self.cb = QCheckBox(self)
        self.cb.setChecked(self.included)
        self.cb.stateChanged.connect(self._cb_changed)
        layout.addWidget(self.cb)
        
        self.icon_lbl = QLabel(self)
        self.icon_lbl.setFixedSize(16, 16)
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_lbl)
        
        self.name_lbl = QLabel(self.app_name, self)
        self.name_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 13px;")
        layout.addWidget(self.name_lbl)
        
        layout.addStretch()
        
        self.tag_lbl = QPushButton(self.tag, self)
        self.tag_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tag_lbl.setFixedWidth(90)
        self._update_tag_style()
        self.tag_lbl.clicked.connect(lambda: self.on_tag_click(self.app_name, self.tag_lbl))
        layout.addWidget(self.tag_lbl)
        
        self.time_lbl = QLabel(format_duration(self.secs), self)
        self.time_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 13px; font-weight: 500;")
        self.time_lbl.setFixedWidth(80)
        self.time_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.time_lbl)
        
        self._apply_row_style()

    def update_time(self, secs):
        self.secs = secs
        self.time_lbl.setText(format_duration(secs))

    def update_tag(self, tag):
        self.tag = tag
        self.tag_lbl.setText(tag)
        self._update_tag_style()

    def set_icon(self, pixmap):
        if pixmap:
            self.icon_lbl.setPixmap(pixmap.scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            self.icon_lbl.clear()

    def _cb_changed(self, state):
        is_checked = (state == 2)  # Qt.CheckState.Checked = 2
        self.included = is_checked
        self.on_toggle(self.app_name, is_checked)
        self._apply_row_style()

    def _update_tag_style(self):
        color = get_tag_color(self.tag)
        self.tag_lbl.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                padding: 2px 6px;
                font-family: 'Segoe UI';
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {color}E6;
            }}
        """)

    def _apply_row_style(self):
        text_color = "#1A1A1A" if self.included else "#ABABAB"
        self.name_lbl.setStyleSheet(f"color: {text_color}; font-family: 'Segoe UI'; font-size: 13px;")
        self.time_lbl.setStyleSheet(f"color: {text_color if self.included else '#ABABAB'}; font-family: 'Segoe UI'; font-size: 13px; font-weight: 500;")

# ── Unified Styled Window Palette (QSS) ──────────────────────────────
QSS_STYLE = """
QWidget {
    color: #1A1A1A;
    background-color: transparent;
}
QMainWindow {
    background-color: #F3F3F3;
}
QDialog {
    background-color: #F3F3F3;
}
QWidget#scroll_widget, 
QWidget#sessions_widget, 
QWidget#recoveries_widget, 
QWidget#scroll_content,
QWidget#report_scroll_widget {
    background-color: #FFFFFF;
}
QLabel {
    color: #1A1A1A;
}
QFrame#MainCard {
    background-color: #FFFFFF;
    border-radius: 8px;
    border: 1px solid #E0E0E0;
}
QFrame#AppListCard {
    background-color: #FFFFFF;
    border-radius: 8px;
    border: 1px solid #E0E0E0;
}
QScrollArea {
    border: none;
    background-color: transparent;
}
QScrollBar:vertical {
    background: #FFFFFF;
    width: 8px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #D0D0D0;
    min-height: 20px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #C0C0C0;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    background: #FFFFFF;
    height: 8px;
    margin: 0px;
}
QScrollBar::handle:horizontal {
    background: #D0D0D0;
    min-width: 20px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal:hover {
    background: #C0C0C0;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}
QPushButton {
    font-family: 'Segoe UI';
    font-size: 13px;
}
QPushButton#AccentButton {
    background-color: #0078D4;
    color: #FFFFFF;
    border: none;
    border-radius: 4px;
    padding: 6px 16px;
    font-weight: bold;
}
QPushButton#AccentButton:hover {
    background-color: #106EBE;
}
QPushButton#AccentButton:disabled {
    background-color: #E9E9E9;
    color: #ABABAB;
}
QPushButton#NormalButton {
    background-color: #FFFFFF;
    color: #1A1A1A;
    border: 1px solid #E0E0E0;
    border-radius: 4px;
    padding: 6px 16px;
}
QPushButton#NormalButton:hover {
    background-color: #E9E9E9;
}
QPushButton#NormalButton:disabled {
    background-color: #F3F3F3;
    color: #ABABAB;
    border: 1px solid #E9E9E9;
}
QPushButton#RedButton {
    background-color: #C42B1C;
    color: #FFFFFF;
    border: none;
    border-radius: 4px;
    padding: 6px 16px;
    font-weight: bold;
}
QPushButton#RedButton:hover {
    background-color: #A82015;
}
QPushButton#RedButton:disabled {
    background-color: #F3F3F3;
    color: #ABABAB;
}
QLineEdit {
    background-color: #FFFFFF;
    border: 1px solid #E0E0E0;
    border-radius: 4px;
    padding: 4px 8px;
    color: #1A1A1A;
    font-family: 'Segoe UI';
    font-size: 13px;
}
QLineEdit:focus {
    border: 1px solid #0078D4;
}
QComboBox {
    background-color: #FFFFFF;
    border: 1px solid #E0E0E0;
    border-radius: 4px;
    padding: 4px 8px;
    color: #1A1A1A;
    font-family: 'Segoe UI';
    font-size: 13px;
}
QComboBox:focus {
    border: 1px solid #0078D4;
}
QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    color: #1A1A1A;
    border: 1px solid #E0E0E0;
    selection-background-color: #E8F1FB;
    selection-color: #0078D4;
}
QTabWidget::pane {
    border: 1px solid #E0E0E0;
    background-color: #FFFFFF;
    border-radius: 6px;
}
QTabBar::tab {
    background-color: #F3F3F3;
    color: #616161;
    padding: 6px 16px;
    font-family: 'Segoe UI';
    font-size: 13px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QTabBar::tab:selected {
    background-color: #FFFFFF;
    color: #0078D4;
    font-weight: bold;
    border: 1px solid #E0E0E0;
    border-bottom: none;
}
QTableWidget {
    background-color: #FFFFFF;
    color: #1A1A1A;
    border: 1px solid #E0E0E0;
    gridline-color: #F3F3F3;
    font-family: 'Segoe UI';
    font-size: 13px;
}
QTableWidget::item {
    color: #1A1A1A;
    background-color: #FFFFFF;
}
QTableWidget::item:selected {
    background-color: #E8F1FB;
    color: #0078D4;
}
QHeaderView::section {
    background-color: #F3F3F3;
    color: #616161;
    padding: 6px;
    border: 1px solid #E0E0E0;
    font-family: 'Segoe UI';
    font-size: 12px;
    font-weight: bold;
}
QTableCornerButton::section {
    background-color: #F3F3F3;
    border: 1px solid #E0E0E0;
}
QCheckBox {
    color: #1A1A1A;
    font-family: 'Segoe UI';
    font-size: 13px;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1.5px solid #8A8A8A;
    border-radius: 3px;
    background-color: #FFFFFF;
}
QCheckBox::indicator:hover {
    border-color: #0078D4;
    background-color: #F3F9FE;
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
    border-color: #CCCCCC;
    background-color: #F3F3F3;
}
QGroupBox {
    font-family: 'Segoe UI';
    font-weight: bold;
    font-size: 12px;
    color: #616161;
    border: 1px solid #E0E0E0;
    border-radius: 6px;
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
    color: #1A1A1A;
    border: 1px solid #E0E0E0;
}
QMenu::item {
    padding: 6px 20px;
    background-color: transparent;
}
QMenu::item:selected {
    background-color: #E8F1FB;
    color: #0078D4;
}
QMenu::separator {
    height: 1px;
    background-color: #E0E0E0;
    margin: 4px 0px;
}
QMessageBox {
    background-color: #F3F3F3;
}
QMessageBox QLabel {
    color: #1A1A1A;
}
QMessageBox QPushButton {
    background-color: #FFFFFF;
    color: #1A1A1A;
    border: 1px solid #E0E0E0;
    border-radius: 4px;
    padding: 4px 12px;
}
"""

# ── Main Application Window ──────────────────────────────────────────
class FocusLogApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.tracker = AppTracker(poll_interval=1.0, min_track_seconds=2)
        self._load_app_settings()

        self._check_vars = {}
        self._photo_refs = []
        self._row_widgets = {}
        self._showing_placeholder = True
        
        # Async icon cache and parameters
        self._last_app_state_hash = None
        self._icon_cache = {}
        self._icon_load_queue = set()

        self.signals = TrackerSignals()
        self.signals.update_signal.connect(self._schedule_refresh)
        self.signals.icon_loaded_signal.connect(self._update_icon_for_app)

        self.setWindowTitle("FocusLog")
        self._center_window(self, 440, 520)
        self.setMinimumSize(440, 500)
        
        if os.path.exists(ICON_PATH):
            try:
                self.setWindowIcon(QIcon(ICON_PATH))
            except Exception:
                pass

        self._build_ui()
        
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._tick_clock)

        # Link tracker callback
        self.tracker.on_update = lambda: self.signals.update_signal.emit()
        
        from tracker import ACTIVE_SESSION_FILE
        if os.path.exists(ACTIVE_SESSION_FILE):
            QTimer.singleShot(100, self._handle_interrupted_session)

    def _center_window(self, win, width, height):
        win.resize(width, height)
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - width) // 2
        y = (screen.height() - height) // 2
        win.move(x, y)

    def _build_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Header Bar ──────────────────────────────────────────────
        self.header = HeaderBar(
            self, 
            cmd_report=self._show_live_report,
            cmd_sessions=self._show_session_manager,
            cmd_settings=self._show_settings
        )
        main_layout.addWidget(self.header)

        # Body Layout (with spacing)
        body_widget = QWidget(self)
        body_layout = QVBoxLayout(body_widget)
        body_layout.setContentsMargins(12, 10, 12, 10)
        body_layout.setSpacing(10)

        # ── Clock + Controls Card ─────────────────────────────────────
        ctrl_card = QFrame(self)
        ctrl_card.setObjectName("MainCard")
        ctrl_layout = QVBoxLayout(ctrl_card)
        ctrl_layout.setContentsMargins(12, 12, 12, 12)
        ctrl_layout.setSpacing(4)
        
        self.clock_label = QLabel("00:00:00", self)
        self.clock_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clock_label.setStyleSheet("font-family: 'Segoe UI'; font-size: 36px; font-weight: bold; color: #1A1A1A;")
        ctrl_layout.addWidget(self.clock_label)

        self.earnings_label = QLabel("", self)
        self.earnings_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.earnings_label.setStyleSheet("font-family: 'Segoe UI'; font-size: 13px; font-weight: bold; color: #0F7B0F;")
        ctrl_layout.addWidget(self.earnings_label)

        self.active_label = QLabel("Ready to track", self)
        self.active_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.active_label.setStyleSheet("font-family: 'Segoe UI'; font-size: 10px; color: #616161;")
        ctrl_layout.addWidget(self.active_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.start_btn = QPushButton("▶ Start", self)
        self.start_btn.setObjectName("AccentButton")
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.clicked.connect(self._on_start)
        btn_row.addWidget(self.start_btn)

        self.pause_btn = QPushButton("⏸ Pause", self)
        self.pause_btn.setObjectName("NormalButton")
        self.pause_btn.setEnabled(False)
        self.pause_btn.clicked.connect(self._on_pause)
        btn_row.addWidget(self.pause_btn)

        self.stop_btn = QPushButton("■ Stop && Report", self)
        self.stop_btn.setObjectName("NormalButton")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)
        btn_row.addWidget(self.stop_btn)
        
        ctrl_layout.addLayout(btn_row)
        body_layout.addWidget(ctrl_card)

        # ── App List Section ──────────────────────────────────────────
        app_sec_hdr = QHBoxLayout()
        app_sec_lbl = QLabel("Application usage", self)
        app_sec_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 10px; color: #616161;")
        app_sec_hdr.addWidget(app_sec_lbl)
        
        exclude_btn = QPushButton("+ Exclude App", self)
        exclude_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        exclude_btn.setStyleSheet("""
            QPushButton {
                color: #0078D4;
                font-size: 10px;
                font-family: 'Segoe UI';
                background: none;
                border: none;
                text-decoration: underline;
            }
            QPushButton:hover {
                color: #106EBE;
            }
        """)
        exclude_btn.clicked.connect(self._on_exclude_app)
        app_sec_hdr.addWidget(exclude_btn, alignment=Qt.AlignmentFlag.AlignRight)
        body_layout.addLayout(app_sec_hdr)

        self.list_card = QFrame(self)
        self.list_card.setObjectName("AppListCard")
        list_card_layout = QVBoxLayout(self.list_card)
        list_card_layout.setContentsMargins(0, 0, 0, 0)
        
        self.scroll_area = QScrollArea(self.list_card)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_widget = QWidget()
        self.scroll_widget.setObjectName("scroll_widget")
        self.scroll_layout = QVBoxLayout(self.scroll_widget)
        self.scroll_layout.setContentsMargins(0, 4, 0, 4)
        self.scroll_layout.setSpacing(0)
        self.scroll_layout.addStretch()
        
        self.scroll_area.setWidget(self.scroll_widget)
        list_card_layout.addWidget(self.scroll_area)
        body_layout.addWidget(self.list_card, 1) # Expandable

        # Placeholder label
        self.placeholder_lbl = QLabel("Click Start to begin tracking", self)
        self.placeholder_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 13px; color: #ABABAB; margin: 40px;")
        self.scroll_layout.insertWidget(0, self.placeholder_lbl)

        # ── Footer ───────────────────────────────────────────────────
        self.footer_card = QFrame(self)
        self.footer_card.setObjectName("MainCard")
        self.footer_card.setFixedHeight(40)
        footer_layout = QHBoxLayout(self.footer_card)
        footer_layout.setContentsMargins(12, 0, 12, 0)
        
        total_lbl = QLabel("Total work time", self)
        total_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 10px; color: #616161;")
        footer_layout.addWidget(total_lbl)
        
        self.total_label = QLabel("0h 00m 00s", self)
        self.total_label.setStyleSheet("font-family: 'Segoe UI'; font-size: 14px; font-weight: bold; color: #0078D4;")
        footer_layout.addWidget(self.total_label, alignment=Qt.AlignmentFlag.AlignRight)
        body_layout.addWidget(self.footer_card)

        # ── Version Bar ──────────────────────────────────────────────
        ver_lbl = QLabel(VERSION_FULL, self)
        ver_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 9px; color: #ABABAB;")
        body_layout.addWidget(ver_lbl)

        main_layout.addWidget(body_widget)

    def closeEvent(self, event):
        if self.confirm_on_close:
            msg = "A tracking session is active.\nAre you sure you want to stop tracking and exit?" if self.tracker.running else "Are you sure you want to close FocusLog?"
            reply = QMessageBox.question(self, "Confirm Exit", msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        if self.tracker.running:
            self.tracker.stop()
            try:
                report = build_report_data(self.tracker, hourly_rate=self.hourly_rate, currency_symbol=self.currency_symbol)
                save_to_autosave(report)
            except Exception as e:
                print(f"[FocusLog] Closing autosave failed: {e}")
        
        # Clean up async icon loading resources
        self._icon_cache.clear()
        self._icon_load_queue.clear()
        event.accept()

    def _on_start(self):
        auto_name = datetime.now().strftime("Session - %I:%M %p")
        self.tracker.start(session_name=auto_name) 
        
        # Clear layout
        self._clear_list_layout()
        self._check_vars.clear()
        self._photo_refs.clear()
        self._row_widgets.clear()
        self._showing_placeholder = True

        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.pause_btn.setText("⏸ Pause")
        self.stop_btn.setEnabled(True)
        
        # Trigger dynamic QSS style changes
        self.start_btn.setObjectName("AccentButton")
        self.pause_btn.setObjectName("NormalButton")
        self.stop_btn.setObjectName("RedButton")
        self.start_btn.setStyleSheet("")
        self.pause_btn.setStyleSheet("")
        self.stop_btn.setStyleSheet("")
        
        if self.hourly_rate > 0:
            self.earnings_label.setText(f"💰 {self.currency_symbol}0.00 earned")
            self.earnings_label.setStyleSheet("color: #0F7B0F; font-size: 13px; font-weight: bold;")
        self.clock_timer.start(250)

    def _on_stop(self):
        self.tracker.stop()
        self.clock_timer.stop()
        
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.active_label.setText("Session ended")
        self.clock_label.setText("00:00:00")
        self.earnings_label.setText("")
        self.setWindowTitle("FocusLog")

        report = build_report_data(self.tracker, hourly_rate=self.hourly_rate, currency_symbol=self.currency_symbol)
        try:
            save_to_autosave(report)
        except Exception as e:
            print(f"[FocusLog] Stop autosave failed: {e}")
        self._show_report(report, is_new=True)

    def _on_pause(self):
        is_paused = self.tracker.toggle_pause()
        if is_paused:
            self.pause_btn.setText("▶ Resume")
            self.pause_btn.setStyleSheet("color: #0078D4; background-color: #E8F1FB; font-weight: bold;")
            self.active_label.setText("⏸ Session paused")
            self.active_label.setStyleSheet("color: #CA5010; font-size: 10px;")
        else:
            self.pause_btn.setText("⏸ Pause")
            self.pause_btn.setStyleSheet("")
            current = self.tracker.get_current_app()
            self.active_label.setText(f"Active: {current}" if current else " ")
            self.active_label.setStyleSheet("color: #616161; font-size: 10px;")

    def _show_live_report(self):
        if not self.tracker.running:
            QMessageBox.information(self, "No Active Session", "Start tracking first to view a live report.")
            return
        report = build_report_data(self.tracker, hourly_rate=self.hourly_rate, currency_symbol=self.currency_symbol)
        self._show_report(report, is_new=False, is_live=True)

    def _tick_clock(self):
        if not self.tracker.running:
            return
        elapsed = self.tracker.get_elapsed()
        self.clock_label.setText(format_duration_hms(elapsed))
        if self.hourly_rate > 0:
            counted = self.tracker.get_counted_seconds()
            earned = (counted / 3600) * self.hourly_rate
            display_symbol = self.currency_symbol.split()[0].split('(')[0].strip() if self.currency_symbol else "$"
            if self.tracker.paused:
                self.earnings_label.setText(f"💰 {display_symbol}{earned:,.2f} earned (paused)")
                self.earnings_label.setStyleSheet("color: #616161; font-size: 13px; font-weight: bold;")
            else:
                self.earnings_label.setText(f"💰 {display_symbol}{earned:,.2f} earned")
                self.earnings_label.setStyleSheet("color: #0F7B0F; font-size: 13px; font-weight: bold;")
        else:
            self.earnings_label.setText("")
            
        if not self.tracker.paused:
            current = self.tracker.get_current_app()
            self.active_label.setText(f"Active: {current}" if current else " ")
            self.active_label.setStyleSheet("color: #616161; font-size: 10px;")
        elif getattr(self.tracker, '_idle_paused', False):
            self.active_label.setText("💤 Idle — auto paused")
            self.active_label.setStyleSheet("color: #CA5010; font-size: 10px;")
            
        name = getattr(self.tracker, "session_name", "")
        self.setWindowTitle(f"FocusLog | {name}" if name else "FocusLog")

    def _schedule_refresh(self):
        # The background thread emits `update_signal`, which wakes this up in the main GUI thread!
        self._refresh_app_list()

    def _refresh_app_list(self):
        try:
            apps = self.tracker.get_app_times_sorted()
            app_state_key = tuple((name, included, int(secs) // 5) for name, secs, included in apps)

            # Skip full rebuild if nothing meaningful changed
            if app_state_key == self._last_app_state_hash and not self._showing_placeholder:
                # Fast path: update times
                for app_name, secs, included in apps:
                    if app_name in self._row_widgets:
                        self._row_widgets[app_name].update_time(secs)
                counted = self.tracker.get_counted_seconds()
                self.total_label.setText(format_duration(counted))
                return

            self._last_app_state_hash = app_state_key
            
            if not apps:
                self._clear_list_layout()
                self._row_widgets.clear()
                self.placeholder_lbl = QLabel("Waiting for app activity...", self)
                self.placeholder_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.placeholder_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 13px; color: #ABABAB; margin: 20px;")
                self.scroll_layout.insertWidget(0, self.placeholder_lbl)
                self._showing_placeholder = True
                return

            if self._showing_placeholder:
                self._clear_list_layout()
                self._showing_placeholder = False

            active_apps = set()
            for i, (app_name, secs, included) in enumerate(apps):
                active_apps.add(app_name)
                
                if app_name not in self._row_widgets:
                    exe_path = self.tracker.get_exe_path(app_name)
                    tag = self.tracker.get_app_tag(app_name)
                    
                    row = AppUsageRow(
                        app_name, secs, included, tag, exe_path,
                        on_toggle=self._toggle_include,
                        on_tag_click=self._show_tag_menu,
                        parent=self.scroll_widget
                    )
                    
                    # Insert in vertical list
                    self.scroll_layout.insertWidget(self.scroll_layout.count() - 1, row)
                    self._row_widgets[app_name] = row
                    
                    # Async icon load
                    if exe_path and exe_path in self._icon_cache:
                        row.set_icon(self._icon_cache[exe_path])
                    elif exe_path and exe_path not in self._icon_load_queue:
                        self._icon_load_queue.add(exe_path)
                        threading.Thread(target=self._load_icon_async, args=(exe_path, app_name), daemon=True).start()
                else:
                    row = self._row_widgets[app_name]
                    row.update_time(secs)
                    row.update_tag(self.tracker.get_app_tag(app_name))

            # Clean up removed apps
            to_remove = [name for name in self._row_widgets if name not in active_apps]
            for name in to_remove:
                self._row_widgets[name].setParent(None)
                del self._row_widgets[name]
                
            counted = self.tracker.get_counted_seconds()
            self.total_label.setText(format_duration(counted))

        except Exception as e:
            logger.debug(f"Exception during app list refresh: {e}")

    def _clear_list_layout(self):
        for i in reversed(range(self.scroll_layout.count())):
            item = self.scroll_layout.itemAt(i)
            if item and item.widget():
                # Retain the bottom spacer stretch
                item.widget().setParent(None)

    def _toggle_include(self, app_name, is_checked):
        self.tracker.set_included(app_name, is_checked)
        self._schedule_refresh()

    def _load_icon_async(self, exe_path: str, app_name: str):
        try:
            icon_img = get_icon_image(exe_path, size=16)
            # Emit PIL image so the conversion to QPixmap happens in the main GUI thread!
            self.signals.icon_loaded_signal.emit(exe_path, app_name, icon_img)
        except Exception as e:
            logger.debug(f"Failed to load icon for {exe_path}: {e}")
            self.signals.icon_loaded_signal.emit(exe_path, app_name, None)

    def _update_icon_for_app(self, exe_path: str, app_name: str, pil_img):
        if pil_img:
            pixmap = pil_to_pixmap(pil_img)
            self._icon_cache[exe_path] = pixmap
        else:
            self._icon_cache[exe_path] = None
        self._icon_load_queue.discard(exe_path)
        
        if app_name in self._row_widgets:
            self._row_widgets[app_name].set_icon(self._icon_cache.get(exe_path))

    def _show_tag_menu(self, app_name, button):
        menu = QMenu(self)
        projects = self.tracker.tag_manager.projects
        current_tag = self.tracker.get_app_tag(app_name)
        
        for proj in projects:
            label = f"✓ {proj}" if proj == current_tag else proj
            action = menu.addAction(label)
            action.triggered.connect(lambda checked, p=proj: self._set_app_tag_and_refresh(app_name, p))
            
        menu.addSeparator()
        action_manage = menu.addAction("Manage Categories...")
        action_manage.triggered.connect(self._show_categories_dialog)
        
        menu.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def _set_app_tag_and_refresh(self, app_name, tag):
        self.tracker.set_app_tag(app_name, tag)
        self._last_app_state_hash = None
        self._refresh_app_list()

    def _on_exclude_app(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Exclude Application")
        self._center_window(dialog, 380, 440)
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 12, 14, 12)
        
        lbl = QLabel("Select a running application to exclude:", dialog)
        lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 11px; color: #616161;")
        layout.addWidget(lbl)
        
        scroll = QScrollArea(dialog)
        scroll.setWidgetResizable(True)
        scroll.setObjectName("AppListCard")
        scroll_content = QWidget()
        scroll_content.setObjectName("scroll_content")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(4, 4, 4, 4)
        scroll_layout.setSpacing(2)
        
        from appinfo import get_running_applications
        running_apps = get_running_applications()
        
        def _exclude_and_close(friendly, exe_path):
            self.tracker.set_included(friendly, False)
            if exe_path: 
                self.tracker.app_exe_paths[friendly] = exe_path
            if friendly not in self.tracker.app_times: 
                self.tracker.app_times[friendly] = 0
            self._refresh_app_list()
            dialog.accept()

        for i, (friendly, exe_path) in enumerate(running_apps):
            row_frame = QFrame(scroll_content)
            row_frame.setFixedHeight(30)
            row_frame.setStyleSheet("QFrame:hover { background-color: #E9E9E9; border-radius: 4px; }")
            row_layout = QHBoxLayout(row_frame)
            row_layout.setContentsMargins(6, 0, 6, 0)
            row_layout.setSpacing(6)
            
            icon_lbl = QLabel(row_frame)
            icon_lbl.setFixedSize(16, 16)
            
            # Load icon directly if possible
            if exe_path:
                pil_icon = get_icon_image(exe_path, size=16)
                px = pil_to_pixmap(pil_icon)
                if px:
                    icon_lbl.setPixmap(px.scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            row_layout.addWidget(icon_lbl)
            
            btn = QPushButton(friendly, row_frame)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background: none;
                    border: none;
                    text-align: left;
                    font-family: 'Segoe UI';
                    font-size: 13px;
                    color: #1A1A1A;
                }
            """)
            btn.clicked.connect(lambda checked, f=friendly, p=exe_path: _exclude_and_close(f, p))
            row_layout.addWidget(btn, 1)
            
            scroll_layout.addWidget(row_frame)
            
        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        def _browse_file():
            path, _ = QFileDialog.getOpenFileName(dialog, "Browse for .exe", "", "Executable files (*.exe);;All files (*.*)")
            if path:
                base = os.path.basename(path)
                if base.lower().endswith(".exe"): 
                    base = base[:-4]
                from appinfo import resolve_name
                friendly = resolve_name(path, base)
                _exclude_and_close(friendly, path)

        browse_btn = QPushButton("Browse for .exe...", dialog)
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.setStyleSheet("""
            QPushButton {
                color: #0078D4;
                font-size: 12px;
                font-family: 'Segoe UI';
                background: none;
                border: none;
                text-decoration: underline;
            }
            QPushButton:hover {
                color: #106EBE;
            }
        """)
        browse_btn.clicked.connect(_browse_file)
        layout.addWidget(browse_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        dialog.exec()

    def _handle_interrupted_session(self):
        from tracker import ACTIVE_SESSION_FILE, AppTracker
        temp_tracker = AppTracker()
        if temp_tracker.load_crash_data():
            report = build_report_data(temp_tracker, hourly_rate=self.hourly_rate, currency_symbol=self.currency_symbol)
            try:
                save_to_autosave(report)
                if os.path.exists(ACTIVE_SESSION_FILE):
                    os.remove(ACTIVE_SESSION_FILE)
                QMessageBox.information(
                    self, "Session Recovered", 
                    "An interrupted session was found and saved as a recovery backup.\n\nYou can view or resume it from the Recoveries tab."
                )
                self._show_session_manager()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save interrupted session: {e}")
        else:
            if os.path.exists(ACTIVE_SESSION_FILE):
                try: 
                    os.remove(ACTIVE_SESSION_FILE)
                except Exception: 
                    pass

    def _show_session_manager(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Session Manager")
        self._center_window(dialog, 480, 540)
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        
        tab_widget = QTabWidget(dialog)
        tab_widget.setObjectName("SessionTabs")
        
        sessions_scroll = QScrollArea()
        sessions_scroll.setWidgetResizable(True)
        sessions_widget = QWidget()
        sessions_widget.setObjectName("sessions_widget")
        sessions_layout = QVBoxLayout(sessions_widget)
        sessions_layout.setContentsMargins(4, 4, 4, 4)
        sessions_layout.setSpacing(4)
        
        recoveries_scroll = QScrollArea()
        recoveries_scroll.setWidgetResizable(True)
        recoveries_widget = QWidget()
        recoveries_widget.setObjectName("recoveries_widget")
        recoveries_layout = QVBoxLayout(recoveries_widget)
        recoveries_layout.setContentsMargins(4, 4, 4, 4)
        recoveries_layout.setSpacing(4)
        
        history_folder = os.path.join(get_app_data_dir(), "sessions")
        autosave_folder = os.path.join(get_app_data_dir(), "autosave")
        os.makedirs(history_folder, exist_ok=True)
        os.makedirs(autosave_folder, exist_ok=True)
        
        def _get_relative_time(timestamp):
            diff = time.time() - timestamp
            if diff < 60: 
                return "Just now"
            if diff < 3600: 
                return f"{int(diff/60)}m ago"
            if diff < 86400: 
                return f"{int(diff/3600)}h ago"
            return datetime.fromtimestamp(timestamp).strftime("%b %d, %Y")

        import glob
        def _render_list(layout_container, folder, is_recoveries):
            # Clear old layout
            for i in reversed(range(layout_container.count())):
                item = layout_container.itemAt(i)
                if item and item.widget():
                    item.widget().setParent(None)
                    
            files = glob.glob(os.path.join(folder, "*.json"))
            files.sort(key=os.path.getmtime, reverse=True)
            if not files:
                label_txt = "No auto-saves/recoveries found." if is_recoveries else "No manual sessions found."
                lbl = QLabel(label_txt)
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 13px; color: #ABABAB; margin: 40px;")
                layout_container.insertWidget(0, lbl)
                layout_container.addStretch()
                return

            for i, filepath in enumerate(files):
                filename = os.path.basename(filepath)
                mtime = os.path.getmtime(filepath)
                rel_time = _get_relative_time(mtime)
                
                row_frame = QFrame()
                row_frame.setStyleSheet("QFrame { background-color: #FFFFFF; border-bottom: 1px solid #F3F3F3; } QFrame:hover { background-color: #E9E9E9; }")
                row_layout = QHBoxLayout(row_frame)
                row_layout.setContentsMargins(8, 8, 8, 8)
                
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    session_name = data.get("session_name", "").strip()
                    date_str = data.get("date", "")
                except Exception:
                    session_name = ""
                    date_str = filename.replace("session_", "").replace("auto_", "").replace("recovery_", "").replace(".json", "").replace("_", "  ")
                
                text_layout = QVBoxLayout()
                text_layout.setSpacing(2)
                
                name_lbl = QLabel(session_name or "Unnamed", row_frame)
                name_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 13px; font-weight: bold; color: #1A1A1A;")
                text_layout.addWidget(name_lbl)
                
                date_lbl = QLabel(date_str, row_frame)
                date_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 11px; color: #616161;")
                text_layout.addWidget(date_lbl)
                
                tag_bg = "#E1F5FE" if i == 0 else "#F5F5F5"
                tag_fg = "#0288D1" if i == 0 else TEXT_SECONDARY
                tag_txt = "Latest" if i == 0 else rel_time
                tag_lbl = QLabel(tag_txt, row_frame)
                tag_lbl.setStyleSheet(f"background-color: {tag_bg}; color: {tag_fg}; font-size: 9px; font-weight: bold; border-radius: 3px; padding: 2px 6px; font-family: 'Segoe UI';")
                tag_lbl.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed))
                text_layout.addWidget(tag_lbl)
                
                row_layout.addLayout(text_layout)
                row_layout.addStretch()
                
                btn_layout = QHBoxLayout()
                btn_layout.setSpacing(4)
                
                def _open_report_local(path):
                    try:
                        rep = load_session_json(path)
                        self._show_report(rep, is_new=False)
                    except Exception as e:
                        QMessageBox.critical(dialog, "Error", f"Could not load session:\n{e}")
                        
                def _resume_from_file(path):
                    if self.tracker.running:
                        reply = QMessageBox.question(dialog, "Active Session", "A session is currently running.\nStop it and resume this one?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                        if reply != QMessageBox.StandardButton.Yes:
                            return
                        self._on_stop()
                    self._resume_session(path)
                    dialog.accept()

                res_btn = QPushButton("▶ Resume", row_frame)
                res_btn.setObjectName("AccentButton")
                res_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                res_btn.clicked.connect(lambda checked, p=filepath: _resume_from_file(p))
                btn_layout.addWidget(res_btn)
                
                view_btn = QPushButton("View", row_frame)
                view_btn.setObjectName("NormalButton")
                view_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                view_btn.clicked.connect(lambda checked, p=filepath: _open_report_local(p))
                btn_layout.addWidget(view_btn)
                
                row_layout.addLayout(btn_layout)
                layout_container.addWidget(row_frame)
                
            layout_container.addStretch()

        _render_list(sessions_layout, history_folder, False)
        _render_list(recoveries_layout, autosave_folder, True)
        
        sessions_scroll.setWidget(sessions_widget)
        recoveries_scroll.setWidget(recoveries_widget)
        
        tab_widget.addTab(sessions_scroll, "Sessions")
        tab_widget.addTab(recoveries_scroll, "Recoveries")
        
        layout.addWidget(tab_widget)
        
        footer = QHBoxLayout()
        export_btn = QPushButton("📊 Export All to CSV", dialog)
        export_btn.setObjectName("AccentButton")
        export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        export_btn.clicked.connect(self._export_csv_history)
        footer.addWidget(export_btn)
        
        footer.addStretch()
        
        open_folder_btn = QPushButton("Open Folder", dialog)
        open_folder_btn.setObjectName("NormalButton")
        open_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_folder_btn.clicked.connect(lambda: os.startfile(autosave_folder if tab_widget.currentIndex() == 1 else history_folder))
        footer.addWidget(open_folder_btn)
        
        close_btn = QPushButton("Close", dialog)
        close_btn.setObjectName("NormalButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(dialog.reject)
        footer.addWidget(close_btn)
        
        layout.addLayout(footer)
        dialog.exec()

    def _resume_session(self, filepath):
        try:
            if self.tracker.running:
                self.tracker.stop()
                
            self.clock_timer.stop()
            self._clear_list_layout()
            self._check_vars.clear()
            self._photo_refs.clear()
            self._row_widgets.clear()
            self._showing_placeholder = True
            self._last_app_state_hash = None

            if not self.tracker.load_from_report(filepath):
                QMessageBox.critical(self, "Error", "Failed to resume session. The file may be corrupted.")
                return

            self.start_btn.setEnabled(False)
            self.pause_btn.setEnabled(True)
            self.pause_btn.setText("⏸ Pause")
            self.stop_btn.setEnabled(True)
            
            # Styles
            self.start_btn.setObjectName("AccentButton")
            self.pause_btn.setObjectName("NormalButton")
            self.stop_btn.setObjectName("RedButton")
            
            if self.hourly_rate > 0:
                self.earnings_label.setText(f"💰 {self.currency_symbol}0.00 earned")
            self.active_label.setText(f"▶ Resumed: {self.tracker.session_name}")
            self.active_label.setStyleSheet("color: #0F7B0F; font-size: 10px;")
            
            self.clock_timer.start(250)
            self._refresh_app_list()
            QMessageBox.information(self, "Session Resumed", f"Resumed session: {self.tracker.session_name}\nTracking is now active.")
        except Exception as e:
            QMessageBox.critical(self, "Resume Error", f"Could not resume session:\n{e}")

    def _load_app_settings(self):
        self.confirm_on_close = True
        self.min_track_seconds = 2
        self.auto_save_seconds = 10
        self.currency_symbol = "$"
        self.hourly_rate = 0.0
        self.idle_threshold_seconds_total = 120  # default: 2 min (0 = disabled)
        if os.path.exists(APP_SETTINGS_FILE):
            try:
                with open(APP_SETTINGS_FILE, "r") as f:
                    data = json.load(f)
                    self.confirm_on_close = data.get("confirm_on_close", True)
                    self.min_track_seconds = data.get("min_track_seconds", 2)
                    self.auto_save_seconds = data.get("auto_save_seconds", 10)
                    raw_curr = data.get("currency_symbol", "$")
                    self.currency_symbol = str(raw_curr).split()[0].split('(')[0].strip() if raw_curr else "$"
                    self.hourly_rate = float(data.get("hourly_rate", 0.0))
                    self.tracker.min_track_seconds = self.min_track_seconds
                    self.tracker.save_interval = self.auto_save_seconds
                    _old_min = data.get("idle_threshold_minutes", 2) * 60
                    self.idle_threshold_seconds_total = data.get("idle_threshold_seconds_total", _old_min)
                    self.tracker.idle_threshold_seconds = self.idle_threshold_seconds_total
            except Exception as e:
                print(f"[FocusLog] Failed to load app settings: {e}")

    def _save_app_settings(self):
        try:
            dirpath = os.path.dirname(APP_SETTINGS_FILE)
            if dirpath: 
                os.makedirs(dirpath, exist_ok=True)
            with open(APP_SETTINGS_FILE, "w") as f:
                json.dump({
                    "confirm_on_close": self.confirm_on_close, 
                    "min_track_seconds": self.min_track_seconds, 
                    "auto_save_seconds": self.auto_save_seconds, 
                    "currency_symbol": self.currency_symbol, 
                    "hourly_rate": self.hourly_rate, 
                    "idle_threshold_seconds_total": self.idle_threshold_seconds_total
                }, f)
        except Exception as e:
            print(f"[FocusLog] Failed to save app settings: {e}")

    def _show_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Settings")
        self._center_window(dialog, 380, 520)
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        
        title = QLabel("Settings", dialog)
        title.setStyleSheet("font-family: 'Segoe UI'; font-size: 15px; font-weight: bold; color: #1A1A1A;")
        layout.addWidget(title)
        
        form = QFormLayout()
        form.setSpacing(8)
        
        cb_confirm = QCheckBox("Always ask for confirmation before closing", dialog)
        cb_confirm.setChecked(self.confirm_on_close)
        cb_confirm.setStyleSheet("font-family: 'Segoe UI'; font-size: 13px;")
        layout.addWidget(cb_confirm)
        
        min_sec_entry = QLineEdit(dialog)
        min_sec_entry.setText(str(self.min_track_seconds))
        form.addRow("Min activity threshold (seconds):", min_sec_entry)
        
        auto_save_entry = QLineEdit(dialog)
        auto_save_entry.setText(str(self.auto_save_seconds))
        form.addRow("Auto-save interval (seconds):", auto_save_entry)
        
        # Idle row
        idle_row = QHBoxLayout()
        idle_row.setSpacing(4)
        _idle_total = getattr(self, "idle_threshold_seconds_total", 120)
        _idle_m_def = _idle_total // 60
        _idle_s_def = _idle_total % 60
        
        idle_min_entry = QLineEdit(dialog)
        idle_min_entry.setFixedWidth(40)
        idle_min_entry.setText(str(_idle_m_def))
        idle_row.addWidget(idle_min_entry)
        idle_row.addWidget(QLabel("min"))
        
        idle_sec_entry = QLineEdit(dialog)
        idle_sec_entry.setFixedWidth(40)
        idle_sec_entry.setText(str(_idle_s_def))
        idle_row.addWidget(idle_sec_entry)
        idle_row.addWidget(QLabel("sec"))
        idle_row.addStretch()
        
        form.addRow("Idle auto-pause (0 min 0 sec = disabled):", idle_row)
        layout.addLayout(form)
        
        # Billing Group
        billing_box = QGroupBox("Billing", dialog)
        billing_box.setStyleSheet("QGroupBox { font-family: 'Segoe UI'; font-weight: bold; font-size: 12px; color: #616161; }")
        billing_layout = QFormLayout(billing_box)
        
        currency_options = [
            "$ (USD)", "€ (EUR)", "£ (GBP)", "¥ (JPY/CNY)", "₱ (PHP)", "₹ (INR)", 
            "₽ (RUB)", "₩ (KRW)", "₫ (VND)", "฿ (THB)", "₪ (ILS)", "₺ (TRY)", 
            "Rp (IDR)", "RM (MYR)", "R$ (BRL)", "C$ (CAD)", "A$ (AUD)", "S$ (SGD)", 
            "NZ$ (NZD)", "CHF (CHF)", "kr (SEK/NOK)", "zł (PLN)", "Kč (CZK)", 
            "Ft (HUF)", "lei (RON)", "лв (BGN)", "₴ (UAH)", "R (ZAR)"
        ]
        curr_combo = QComboBox(dialog)
        curr_combo.addItems(currency_options)
        matched = [c for c in currency_options if c.startswith(self.currency_symbol)]
        if matched:
            curr_combo.setCurrentText(matched[0])
        else:
            curr_combo.setCurrentText(self.currency_symbol)
        billing_layout.addRow("Currency symbol:", curr_combo)
        
        rate_entry = QLineEdit(dialog)
        rate_entry.setText(f"{self.hourly_rate:.2f}")
        billing_layout.addRow("Hourly rate:", rate_entry)
        
        layout.addWidget(billing_box)

        # Config files Buttons
        config_box = QGroupBox("Configuration Files", dialog)
        config_box.setStyleSheet("QGroupBox { font-family: 'Segoe UI'; font-weight: bold; font-size: 12px; color: #616161; }")
        config_layout = QVBoxLayout(config_box)
        config_layout.setSpacing(6)
        
        def _open_file(filepath):
            if filepath == AUTO_EXCLUDE_FILE:
                try:
                    create_auto_excluded_if_missing()
                except Exception:
                    pass
            elif filepath == OVERRIDES_FILE:
                try:
                    from appinfo import _load_name_overrides
                    _load_name_overrides()
                except Exception:
                    pass

            if not os.path.exists(filepath):
                try:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write("# Configuration file created.\n")
                except Exception: 
                    pass
            try: 
                os.startfile(filepath)
            except Exception: 
                QMessageBox.critical(dialog, "Error", f"Could not open: {filepath}")

        btn_overrides = QPushButton("Edit Name Overrides", dialog)
        btn_overrides.setObjectName("NormalButton")
        btn_overrides.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_overrides.clicked.connect(lambda: _open_file(OVERRIDES_FILE))
        config_layout.addWidget(btn_overrides)
        
        excl_row = QHBoxLayout()
        btn_excl = QPushButton("Edit Auto-Exclusions", dialog)
        btn_excl.setObjectName("NormalButton")
        btn_excl.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_excl.clicked.connect(lambda: _open_file(AUTO_EXCLUDE_FILE))
        excl_row.addWidget(btn_excl, 1)
        
        btn_reload = QPushButton("🔄 Reload", dialog)
        btn_reload.setObjectName("NormalButton")
        btn_reload.setCursor(Qt.CursorShape.PointingHandCursor)
        
        reload_status_lbl = QLabel(" ", dialog)
        reload_status_lbl.setStyleSheet("font-size: 11px; font-weight: bold;")
        
        def _reload_exclusions():
            from tracker import reload_auto_excluded
            lock = self.tracker._lock if self.tracker.running else None
            if reload_auto_excluded(lock=lock):
                reload_status_lbl.setText("✓ Reloaded")
                reload_status_lbl.setStyleSheet("color: #0F7B0F;")
            else:
                reload_status_lbl.setText("✗ Failed")
                reload_status_lbl.setStyleSheet("color: #C42B1C;")
            QTimer.singleShot(2000, lambda: reload_status_lbl.setText(" "))

        btn_reload.clicked.connect(_reload_exclusions)
        excl_row.addWidget(btn_reload)
        excl_row.addWidget(reload_status_lbl)
        config_layout.addLayout(excl_row)
        
        btn_categories = QPushButton("Manage Project Categories", dialog)
        btn_categories.setObjectName("NormalButton")
        btn_categories.setStyleSheet("font-weight: bold;")
        btn_categories.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_categories.clicked.connect(self._show_categories_dialog)
        config_layout.addWidget(btn_categories)
        
        layout.addWidget(config_box)

        # Bottom Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        save_btn = QPushButton("Save Settings", dialog)
        save_btn.setObjectName("AccentButton")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        
        def _save_and_close():
            try:
                self.confirm_on_close = cb_confirm.isChecked()
                self.min_track_seconds = int(min_sec_entry.text())
                self.auto_save_seconds = int(auto_save_entry.text())
                raw_symbol = curr_combo.currentText().strip()
                self.currency_symbol = raw_symbol.split()[0].split('(')[0].strip() if raw_symbol else "$"
                self.hourly_rate = float(rate_entry.text().strip() or 0)
                
                _im = max(0, int(idle_min_entry.text().strip() or 0))
                _is = max(0, min(59, int(idle_sec_entry.text().strip() or 0)))
                self.idle_threshold_seconds_total = _im * 60 + _is
                
                self.tracker.min_track_seconds = self.min_track_seconds
                self.tracker.save_interval = self.auto_save_seconds
                self.tracker.idle_threshold_seconds = self.idle_threshold_seconds_total
                
                self._save_app_settings()
                
                # Update live indicators
                if self.tracker.running and self.hourly_rate > 0:
                    counted = self.tracker.get_counted_seconds()
                    earned = (counted / 3600) * self.hourly_rate
                    state_text = " (paused)" if self.tracker.paused else ""
                    self.earnings_label.setText(f"💰 {self.currency_symbol}{earned:,.2f} earned{state_text}")
                dialog.accept()
            except ValueError:
                QMessageBox.critical(dialog, "Error", "Please enter valid numeric values.")

        save_btn.clicked.connect(_save_and_close)
        btn_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("Cancel", dialog)
        cancel_btn.setObjectName("NormalButton")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
        dialog.exec()

    def _show_categories_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Manage Categories")
        self._center_window(dialog, 360, 440)
        dialog.setModal(True)
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 12, 14, 12)
        
        title = QLabel("Manage Categories", dialog)
        title.setStyleSheet("font-family: 'Segoe UI'; font-size: 15px; font-weight: bold; color: #1A1A1A;")
        layout.addWidget(title)
        
        scroll = QScrollArea(dialog)
        scroll.setWidgetResizable(True)
        scroll.setObjectName("AppListCard")
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(4, 4, 4, 4)
        scroll_layout.setSpacing(2)
        
        def refresh_categories_list():
            for i in reversed(range(scroll_layout.count())):
                item = scroll_layout.itemAt(i)
                if item and item.widget():
                    item.widget().setParent(None)
                    
            projects = self.tracker.tag_manager.projects
            for proj in projects:
                row = QFrame(scroll_content)
                row.setFixedHeight(30)
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(6, 0, 6, 0)
                row_layout.setSpacing(6)
                
                color = get_tag_color(proj)
                dot = QLabel("●", row)
                dot.setStyleSheet(f"color: {color}; font-size: 14px; font-family: 'Segoe UI';")
                row_layout.addWidget(dot)
                
                lbl = QLabel(proj, row)
                lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 13px; color: #1A1A1A;")
                row_layout.addWidget(lbl, 1)
                
                if proj != "Unassigned":
                    del_btn = QPushButton("❌", row)
                    del_btn.setFixedSize(20, 20)
                    del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                    del_btn.setStyleSheet("QPushButton { background: none; border: none; font-size: 10px; } QPushButton:hover { background-color: #E9E9E9; border-radius: 3px; }")
                    del_btn.clicked.connect(lambda checked, p=proj: delete_project(p))
                    row_layout.addWidget(del_btn)
                    
                scroll_layout.addWidget(row)
            scroll_layout.addStretch()

        def delete_project(project):
            if self.tracker.tag_manager.remove_project(project):
                self._last_app_state_hash = None
                self._refresh_app_list()
                refresh_categories_list()

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)
        
        add_row = QHBoxLayout()
        add_entry = QLineEdit(dialog)
        add_entry.setPlaceholderText("New category name...")
        add_row.addWidget(add_entry, 1)
        
        add_btn = QPushButton("Add Category", dialog)
        add_btn.setObjectName("AccentButton")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        
        def add_project():
            name = add_entry.text().strip()
            if not name:
                return
            if name in self.tracker.tag_manager.projects:
                QMessageBox.critical(dialog, "Error", f"Category '{name}' already exists.")
                return
            if self.tracker.tag_manager.add_project(name):
                add_entry.clear()
                refresh_categories_list()
                self._last_app_state_hash = None
                self._refresh_app_list()

        add_btn.clicked.connect(add_project)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)
        
        refresh_categories_list()
        dialog.exec()

    def _show_report(self, report, is_new=True, is_live=False):
        dialog = QDialog(self)
        dialog.setWindowTitle("FocusLog — Live Report" if is_live else "FocusLog — Session Report")
        self._center_window(dialog, 720, 680)
        dialog.setMinimumSize(600, 500)
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header bar
        hdr = QFrame(dialog)
        hdr.setFixedHeight(44)
        hdr.setStyleSheet("QFrame { background-color: #FFFFFF; border-bottom: 1px solid #E0E0E0; }")
        hdr_layout = QHBoxLayout(hdr)
        hdr_layout.setContentsMargins(14, 0, 14, 0)
        
        title_lbl = QLabel("📊 Live Report (Preview)" if is_live else "📊 Session Report", hdr)
        title_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 15px; font-weight: bold; color: #1A1A1A; border: none;")
        hdr_layout.addWidget(title_lbl)
        hdr_layout.addStretch()
        
        if is_live:
            ref_btn = QPushButton("🔄 Refresh", hdr)
            ref_btn.setObjectName("NormalButton")
            ref_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            ref_btn.clicked.connect(lambda: (dialog.accept(), self._show_live_report()))
            hdr_layout.addWidget(ref_btn)
        elif is_new:
            save_btn = QPushButton("💾 Save to History", hdr)
            save_btn.setObjectName("AccentButton")
            save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            hdr_layout.addWidget(save_btn)
            
        layout.addWidget(hdr)
        
        # Name Entry bar
        name_bar = QFrame(dialog)
        name_bar.setFixedHeight(40)
        name_bar.setStyleSheet("QFrame { background-color: #FFFFFF; border-bottom: 1px solid #F3F3F3; }")
        nb_layout = QHBoxLayout(name_bar)
        nb_layout.setContentsMargins(14, 0, 14, 0)
        
        nb_layout.addWidget(QLabel("Session Name: "))
        report_name_entry = QLineEdit(name_bar)
        report_name_entry.setFixedWidth(260)
        report_name_entry.setText(report.get("session_name", "").strip() or "Unnamed")
        nb_layout.addWidget(report_name_entry)
        
        nb_layout.addStretch()
        if is_live:
            live_lbl = QLabel(f"🕒 Snapshot: {datetime.now().strftime('%H:%M:%S')} • Tracking active", name_bar)
            live_lbl.setStyleSheet("color: #CA5010; font-family: 'Segoe UI'; font-size: 11px;")
            nb_layout.addWidget(live_lbl)
        layout.addWidget(name_bar)
        
        # Scrollable Content Area
        scroll = QScrollArea(dialog)
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_widget.setObjectName("report_scroll_widget")
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(20, 12, 20, 12)
        scroll_layout.setSpacing(12)
        
        # Card 1: Time summary
        card1 = QFrame(scroll_widget)
        card1.setObjectName("MainCard")
        c1_layout = QVBoxLayout(card1)
        c1_layout.setContentsMargins(14, 12, 14, 12)
        c1_layout.setSpacing(4)
        
        date_lbl = QLabel(f"{report['date_display']}  ·  {report['start_display']} -> {report['end_display']}", card1)
        date_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 12px; color: #616161;")
        c1_layout.addWidget(date_lbl)
        
        total_lbl = QLabel(f"Total session:  {report['total_formatted']}", card1)
        total_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 13px; color: #1A1A1A;")
        c1_layout.addWidget(total_lbl)
        
        counted_lbl = QLabel(f"Counted work:  {report['counted_formatted']}", card1)
        counted_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 14px; font-weight: bold; color: #0078D4;")
        c1_layout.addWidget(counted_lbl)
        
        if report.get("total_earned", 0) > 0:
            earned_f = QFrame(card1)
            earned_f.setStyleSheet("QFrame { background-color: #E8F1FB; border-radius: 4px; }")
            ef_layout = QHBoxLayout(earned_f)
            ef_layout.setContentsMargins(10, 6, 10, 6)
            
            lbl_title = QLabel("💰 Total Earned: ", earned_f)
            lbl_title.setStyleSheet("font-family: 'Segoe UI'; font-size: 12px; color: #616161;")
            ef_layout.addWidget(lbl_title)
            
            lbl_val = QLabel(report["total_earned_display"], earned_f)
            lbl_val.setStyleSheet("font-family: 'Segoe UI'; font-size: 18px; font-weight: bold; color: #0F7B0F;")
            ef_layout.addWidget(lbl_val)
            
            lbl_rate = QLabel(f"@ {report['currency_symbol']}{report['hourly_rate']:.2f}/hr", earned_f)
            lbl_rate.setStyleSheet("font-family: 'Segoe UI'; font-size: 11px; color: #616161;")
            ef_layout.addWidget(lbl_rate)
            
            ef_layout.addStretch()
            c1_layout.addWidget(earned_f)
            
        scroll_layout.addWidget(card1)

        # Card 2: Allocation horizontal custom paint bar
        project_breakdown = report.get("project_breakdown", [])
        if project_breakdown:
            title_p = QLabel("Project & Category Allocation", scroll_widget)
            title_p.setStyleSheet("font-family: 'Segoe UI'; font-size: 13px; font-weight: bold; color: #616161;")
            scroll_layout.addWidget(title_p)
            
            alloc_card = QFrame(scroll_widget)
            alloc_card.setObjectName("MainCard")
            ac_layout = QVBoxLayout(alloc_card)
            ac_layout.setContentsMargins(14, 14, 14, 14)
            
            paint_bar = SegmentedAllocationBar(alloc_card)
            paint_bar.set_breakdown(project_breakdown)
            ac_layout.addWidget(paint_bar)
            
            # Legend table
            for pb in project_breakdown:
                row_f = QFrame(alloc_card)
                row_f.setFixedHeight(24)
                row_layout = QHBoxLayout(row_f)
                row_layout.setContentsMargins(0, 0, 0, 0)
                
                swatch = QLabel("■", row_f)
                swatch.setStyleSheet(f"color: {pb['color']}; font-size: 14px;")
                row_layout.addWidget(swatch)
                
                lbl = QLabel(pb["project"], row_f)
                lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 12px; font-weight: bold; color: #1A1A1A;")
                row_layout.addWidget(lbl)
                
                pct_lbl = QLabel(f"{pb['percent']:.1f}%", row_f)
                pct_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 12px; color: #616161;")
                row_layout.addWidget(pct_lbl)
                
                row_layout.addStretch()
                
                if pb.get("earned_display"):
                    earned_lbl = QLabel(f"({pb['earned_display']})", row_f)
                    earned_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 12px; font-weight: bold; color: #0F7B0F;")
                    row_layout.addWidget(earned_lbl)
                    
                time_lbl = QLabel(pb["formatted"], row_f)
                time_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 12px; color: #1A1A1A;")
                row_layout.addWidget(time_lbl)
                
                ac_layout.addWidget(row_f)
                
            scroll_layout.addWidget(alloc_card)

        # Card 3: App Breakdown list table
        apps_data = report.get("apps", [])
        if apps_data:
            title_b = QLabel("App Breakdown", scroll_widget)
            title_b.setStyleSheet("font-family: 'Segoe UI'; font-size: 13px; font-weight: bold; color: #616161;")
            scroll_layout.addWidget(title_b)
            
            tbl_card = QFrame(scroll_widget)
            tbl_card.setObjectName("MainCard")
            tc_layout = QVBoxLayout(tbl_card)
            tc_layout.setContentsMargins(0, 0, 0, 0)
            
            table = QTableWidget(tbl_card)
            table.setColumnCount(5)
            table.setHorizontalHeaderLabels(["App", "Category", "Time", "%", "Status"])
            table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
            table.setRowCount(len(apps_data))
            table.verticalHeader().setVisible(False)
            table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            
            for i, app in enumerate(apps_data):
                table.setItem(i, 0, QTableWidgetItem(app["name"]))
                
                # Custom Tag style inside cell
                tag_item = QTableWidgetItem(app["tag"])
                tag_item.setForeground(QColor("#FFFFFF"))
                tag_item.setBackground(QColor(get_tag_color(app["tag"])))
                tag_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(i, 1, tag_item)
                
                table.setItem(i, 2, QTableWidgetItem(app["formatted"]))
                table.setItem(i, 3, QTableWidgetItem(f"{app['percent']:.0f}%"))
                
                st_text = "✓ Counted" if not app["excluded"] else "✗ Excluded"
                st_color = "#0F7B0F" if not app["excluded"] else "#C42B1C"
                st_item = QTableWidgetItem(st_text)
                st_item.setForeground(QColor(st_color))
                table.setItem(i, 4, st_item)
                
            # Set exact height to table content to prevent scrollbar duplication
            table.setFixedHeight(table.horizontalHeader().height() + sum(table.rowHeight(row) for row in range(len(apps_data))) + 4)
            tc_layout.addWidget(table)
            scroll_layout.addWidget(tbl_card)

        # Card 4: Timeline
        timeline_data = report.get("timeline", [])
        if timeline_data:
            title_t = QLabel("Timeline", scroll_widget)
            title_t.setStyleSheet("font-family: 'Segoe UI'; font-size: 13px; font-weight: bold; color: #616161;")
            scroll_layout.addWidget(title_t)
            
            tl_card = QFrame(scroll_widget)
            tl_card.setObjectName("MainCard")
            tl_layout = QVBoxLayout(tl_card)
            tl_layout.setContentsMargins(0, 0, 0, 0)
            tl_layout.setSpacing(0)
            
            tl_table = QTableWidget(tl_card)
            tl_table.setColumnCount(2)
            tl_table.setHorizontalHeaderLabels(["Duration Block", "Application"])
            tl_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            tl_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            tl_table.verticalHeader().setVisible(False)
            tl_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            
            # Show More button container and button
            btn_container = QWidget(tl_card)
            btn_layout = QHBoxLayout(btn_container)
            btn_layout.setContentsMargins(14, 8, 14, 12)
            
            more_btn = QPushButton(tl_card)
            more_btn.setObjectName("NormalButton")
            more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_layout.addWidget(more_btn)
            
            state = {"limit": 15}
            
            def load_timeline_rows(limit):
                current_limit = min(limit, len(timeline_data))
                tl_table.setRowCount(current_limit)
                
                for i in range(current_limit):
                    tl = timeline_data[i]
                    t_start = tl['start'].strftime("%H:%M:%S") if hasattr(tl['start'], 'strftime') else tl['start']
                    t_end = tl['end'].strftime("%H:%M:%S") if hasattr(tl['end'], 'strftime') else tl['end']
                    
                    tl_table.setItem(i, 0, QTableWidgetItem(f"{t_start} -> {t_end}"))
                    tl_table.setItem(i, 1, QTableWidgetItem(tl["app"]))
                
                # Dynamically adjust height of table to exactly fit rows
                header_h = tl_table.horizontalHeader().height() if tl_table.horizontalHeader().height() > 0 else 28
                row_sum = 0
                for row in range(current_limit):
                    rh = tl_table.rowHeight(row)
                    row_sum += rh if rh > 0 else 28
                tl_table.setFixedHeight(header_h + row_sum + 4)
                
                if current_limit < len(timeline_data):
                    more_btn.setVisible(True)
                    btn_container.setVisible(True)
                    more_btn.setText(f"Show More (+{min(15, len(timeline_data) - current_limit)})")
                else:
                    more_btn.setVisible(False)
                    btn_container.setVisible(False)
            
            def show_more():
                state["limit"] += 15
                load_timeline_rows(state["limit"])
                
            more_btn.clicked.connect(show_more)
            
            # Load initial rows
            load_timeline_rows(state["limit"])
            
            tl_layout.addWidget(tl_table)
            tl_layout.addWidget(btn_container)
            scroll_layout.addWidget(tl_card)

        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)
        
        # Export Actions Footer
        footer_f = QFrame(dialog)
        footer_f.setFixedHeight(50)
        footer_f.setStyleSheet("QFrame { background-color: #FFFFFF; border-top: 1px solid #E0E0E0; }")
        footer_layout = QHBoxLayout(footer_f)
        footer_layout.setContentsMargins(14, 0, 14, 0)
        
        def export_with_name(fmt):
            try:
                new_name = report_name_entry.text().strip()
                if new_name: 
                    report['session_name'] = new_name
            except Exception: 
                pass
            self._export(report, fmt)

        txt_btn = QPushButton("Export .txt", footer_f)
        txt_btn.setObjectName("AccentButton")
        txt_btn.clicked.connect(lambda: export_with_name("txt"))
        footer_layout.addWidget(txt_btn)
        
        json_btn = QPushButton("Export .json", footer_f)
        json_btn.setObjectName("AccentButton")
        json_btn.clicked.connect(lambda: export_with_name("json"))
        footer_layout.addWidget(json_btn)
        
        csv_btn = QPushButton("Export .csv", footer_f)
        csv_btn.setObjectName("AccentButton")
        csv_btn.clicked.connect(lambda: export_with_name("csv"))
        footer_layout.addWidget(csv_btn)
        
        footer_layout.addStretch()
        
        close_btn = QPushButton("Close", footer_f)
        close_btn.setObjectName("NormalButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(dialog.reject)
        footer_layout.addWidget(close_btn)
        
        if not is_live and is_new:
            def _save_and_close():
                try:
                    new_name = report_name_entry.text().strip()
                    report["session_name"] = new_name if new_name else "Unnamed"
                    save_to_history(report)
                    QMessageBox.information(dialog, "Saved", "Session saved to History.")
                    dialog.accept()
                except Exception as e:
                    QMessageBox.critical(dialog, "Error", f"Failed to save: {e}")
            save_btn.clicked.connect(_save_and_close)
            
        layout.addWidget(footer_f)
        dialog.exec()

    def _export(self, report, fmt):
        if fmt == "txt": 
            path, _ = QFileDialog.getSaveFileName(self, "Export TXT", f"focuslog_{report['date']}.txt", "Text files (*.txt)")
        elif fmt == "json": 
            path, _ = QFileDialog.getSaveFileName(self, "Export JSON", f"focuslog_{report['date']}.json", "JSON files (*.json)")
        else: 
            path, _ = QFileDialog.getSaveFileName(self, "Export CSV", f"focuslog_{report['date']}.csv", "CSV files (*.csv)")
            
        if not path: 
            return
        try:
            if fmt == "txt": 
                export_txt(report, path)
            elif fmt == "json": 
                export_json(report, path)
            else: 
                export_csv(report, path)
            QMessageBox.information(self, "Exported", f"Report saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    def _export_csv_history(self):
        sessions_dir = os.path.join(get_app_data_dir(), "sessions")
        if not os.path.exists(sessions_dir):
            QMessageBox.warning(self, "No Sessions", "No saved sessions found.")
            return
        json_files = [f for f in os.listdir(sessions_dir) if f.endswith('.json')]
        if not json_files:
            QMessageBox.warning(self, "No Sessions", "No saved sessions found.")
            return
        reports = []
        for filename in json_files:
            try: 
                reports.append(load_session_json(os.path.join(sessions_dir, filename)))
            except Exception as e: 
                print(f"Error loading {filename}: {e}")
        if not reports: 
            QMessageBox.critical(self, "Error", "Could not load any sessions.")
            return
            
        default_name = f"FocusLog_Export_{datetime.now().strftime('%Y-%m-%d')}.csv"
        filepath, _ = QFileDialog.getSaveFileName(self, "Export History CSV", default_name, "CSV files (*.csv);;All files (*.*)")
        if not filepath: 
            return
        if export_csv_history(reports, filepath, hourly_rate=self.hourly_rate, currency_symbol=self.currency_symbol):
            QMessageBox.information(self, "Success", f"Exported {len(reports)} sessions to:\n{filepath}")
        else: 
            QMessageBox.critical(self, "Error", "Failed to export CSV.")

    def run(self):
        self.show()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Force style and palette to avoid theme bleeding on systems set to Dark Mode
    app.setStyle("Fusion")
    app.setPalette(get_light_palette())
    
    checkmark_path = ensure_checkmark_icon()
    app.setStyleSheet(QSS_STYLE.replace("CHECKMARK_PATH", checkmark_path))
    
    # Set default fonts globally
    font = app.font()
    font.setFamily(FONT_FAMILY)
    font.setPointSize(10)
    app.setFont(font)
    
    focus_app = FocusLogApp()
    focus_app.run()
    sys.exit(app.exec())
