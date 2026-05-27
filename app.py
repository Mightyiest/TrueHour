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
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy,
    QLayout, QInputDialog
)
from PyQt6.QtCore import Qt, QTimer, QSize, QObject, pyqtSignal, QRectF, QPointF, QRect, QPoint
from PyQt6.QtGui import QColor, QPainter, QBrush, QPen, QImage, QPixmap, QIcon, QPainterPath, QPalette

from tracker import AppTracker, AUTO_EXCLUDE_FILE, create_auto_excluded_if_missing
from appinfo import get_icon_image, OVERRIDES_FILE
from config import get_app_data_dir
from secure_time import get_detector
from report import (
    format_duration, format_duration_hms, build_report_data,
    export_txt, export_json, export_csv, export_csv_history,
    save_to_autosave, save_to_history, load_session_json,
    aggregate_history_data, generate_session_report_html,
)
from version import VERSION_SHORT, VERSION_FULL
from dashboard_widgets import DonutChartWidget, BarChartWidget
from assets import RENAME_SVG, TRASH_SVG, RESTORE_SVG

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
def get_light_palette():
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

# ── Modern Minimalist Light Palette ──────────────────────────────────
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

# ── Email Chip Widget (Gmail-style Token Input) ──────────────────────
class EmailChipWidget(QWidget):
    """A multi-email input widget with Gmail-style chips/tokens."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._emails = []
        self._chip_widgets = []

        self._outer_layout = QVBoxLayout(self)
        self._outer_layout.setContentsMargins(0, 0, 0, 0)
        self._outer_layout.setSpacing(4)

        # Chip container with flow-wrap behavior
        self._chip_container = QWidget(self)
        self._chip_container.setStyleSheet("background: transparent;")
        self._flow_layout = FlowLayout(self._chip_container, margin=2, spacing=4)
        self._outer_layout.addWidget(self._chip_container)

        # Text input line
        self._input = QLineEdit(self)
        self._input.setPlaceholderText("Type email and press Enter or comma...")
        self._input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #E2E8F0;
                border-radius: 6px;
                padding: 5px 8px;
                font-family: 'Segoe UI';
                font-size: 12px;
                background-color: #FFFFFF;
            }
            QLineEdit:focus {
                border-color: #0078D4;
            }
        """)
        self._input.returnPressed.connect(self._on_commit)
        self._input.textChanged.connect(self._on_text_changed)
        self._outer_layout.addWidget(self._input)

    def _on_text_changed(self, text):
        """Detect comma or semicolon separator to commit chip."""
        if text.endswith(",") or text.endswith(";"):
            self._input.setText(text[:-1])
            self._on_commit()

    def _on_commit(self):
        """Validate and add current text as a chip."""
        text = self._input.text().strip().lower()
        if not text:
            return
        if "@" not in text or "." not in text.split("@")[-1]:
            return  # Basic validation
        if text in self._emails:
            self._input.clear()
            return  # No duplicates
        self._emails.append(text)
        self._add_chip_widget(text)
        self._input.clear()

    def _add_chip_widget(self, email):
        """Create a visual chip pill for an email."""
        chip = QFrame(self._chip_container)
        chip.setStyleSheet("""
            QFrame {
                background-color: #EEF2FF;
                border: 1px solid #C7D2FE;
                border-radius: 12px;
                padding: 2px 4px;
            }
        """)
        chip_layout = QHBoxLayout(chip)
        chip_layout.setContentsMargins(8, 2, 4, 2)
        chip_layout.setSpacing(4)

        label = QLabel(email, chip)
        label.setStyleSheet("color: #3730A3; font-size: 11px; font-family: 'Segoe UI'; font-weight: 500; border: none; background: transparent;")
        chip_layout.addWidget(label)

        remove_btn = QPushButton("✕", chip)
        remove_btn.setFixedSize(16, 16)
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #6366F1;
                font-size: 11px;
                font-weight: bold;
                padding: 0;
            }
            QPushButton:hover {
                color: #DC2626;
            }
        """)
        remove_btn.clicked.connect(lambda checked, e=email, c=chip: self._remove_chip(e, c))
        chip_layout.addWidget(remove_btn)

        self._flow_layout.addWidget(chip)
        self._chip_widgets.append(chip)

    def _remove_chip(self, email, chip_widget):
        """Remove a chip by email and destroy its widget."""
        if email in self._emails:
            self._emails.remove(email)
        if chip_widget in self._chip_widgets:
            self._chip_widgets.remove(chip_widget)
        self._flow_layout.removeWidget(chip_widget)
        chip_widget.deleteLater()

    def get_emails(self):
        """Return the list of entered emails."""
        return list(self._emails)

    def set_emails(self, email_list):
        """Set emails from a list, creating chips for each."""
        self.clear()
        for email in email_list:
            email = email.strip().lower()
            if email and email not in self._emails:
                self._emails.append(email)
                self._add_chip_widget(email)

    def clear(self):
        """Remove all chips and clear input."""
        self._emails.clear()
        for chip in self._chip_widgets:
            self._flow_layout.removeWidget(chip)
            chip.deleteLater()
        self._chip_widgets.clear()
        self._input.clear()


class FlowLayout(QLayout):
    """Dynamic flow layout that wraps widgets dynamically based on available width."""

    def __init__(self, parent=None, margin=0, spacing=4):
        super().__init__(parent)
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self._items = []

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect, test_only):
        margins = self.contentsMargins()
        x = rect.x() + margins.left()
        y = rect.y() + margins.top()
        row_height = 0
        space_x = self.spacing()
        space_y = self.spacing()
        
        for item in self._items:
            widget = item.widget()
            if not widget:
                continue
            item_width = item.sizeHint().width()
            item_height = item.sizeHint().height()
            
            next_x = x + item_width + space_x
            if next_x - space_x > rect.right() - margins.right() and row_height > 0:
                x = rect.x() + margins.left()
                y = y + row_height + space_y
                next_x = x + item_width + space_x
                row_height = 0
                
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
                
            x = next_x
            row_height = max(row_height, item_height)
            
        return y + row_height - rect.y() + margins.bottom()


# ── Invoice Privacy Options Dialog (Custom Checkable Popup Prompt) ────
class InvoicePrivacyOptionsDialog(QDialog):
    """Custom checkbox selection prompt for sensitive data masking prior to invoice generation."""

    def __init__(self, parent=None, default_biz_email=False, default_biz_phone=False, default_client_email=False):
        super().__init__(parent)
        self.setWindowTitle("Invoice Privacy Options")
        self.setFixedSize(380, 240)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        title = QLabel("Privacy & Masking Options", self)
        title.setStyleSheet("font-family: 'Segoe UI'; font-size: 14px; font-weight: bold; color: #1A1A1A; border: none; background: transparent;")
        layout.addWidget(title)
        
        desc = QLabel("Select which sensitive details you would like to mask on this invoice:", self)
        desc.setWordWrap(True)
        desc.setStyleSheet("font-family: 'Segoe UI'; font-size: 11px; color: #64748B; border: none; background: transparent;")
        layout.addWidget(desc)
        
        # Options Group
        options_box = QFrame(self)
        options_box.setStyleSheet("QFrame { background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; }")
        options_layout = QVBoxLayout(options_box)
        options_layout.setContentsMargins(12, 8, 12, 8)
        options_layout.setSpacing(6)
        
        self.cb_biz_email = QCheckBox("Mask business contact emails (e.g. bu**@****.com)", options_box)
        self.cb_biz_email.setChecked(default_biz_email)
        self.cb_biz_email.setStyleSheet("border: none; background: transparent; font-family: 'Segoe UI'; font-size: 12px;")
        options_layout.addWidget(self.cb_biz_email)
        
        self.cb_biz_phone = QCheckBox("Mask business contact phone (e.g. +1***)", options_box)
        self.cb_biz_phone.setChecked(default_biz_phone)
        self.cb_biz_phone.setStyleSheet("border: none; background: transparent; font-family: 'Segoe UI'; font-size: 12px;")
        options_layout.addWidget(self.cb_biz_phone)
        
        self.cb_client_email = QCheckBox("Mask client contact emails (e.g. cl**@****.com)", options_box)
        self.cb_client_email.setChecked(default_client_email)
        self.cb_client_email.setStyleSheet("border: none; background: transparent; font-family: 'Segoe UI'; font-size: 12px;")
        options_layout.addWidget(self.cb_client_email)
        
        layout.addWidget(options_box)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel", self)
        cancel_btn.setObjectName("NormalButton")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        
        gen_btn = QPushButton("Generate", self)
        gen_btn.setObjectName("AccentButton")
        gen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        gen_btn.clicked.connect(self.accept)
        
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(gen_btn)
        layout.addLayout(btn_layout)


# ── Thread-Safe Signals ──────────────────────────────────────────────
class TrackerSignals(QObject):
    update_signal = pyqtSignal()
    icon_loaded_signal = pyqtSignal(str, str, object)  # exe_path, app_name, PIL Image (or None)

def create_minimalist_icon(icon_type, color_hex, size=16):
    import math
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

class HeaderBar(QFrame):
    def __init__(self, parent, cmd_report, cmd_sessions, cmd_settings):
        super().__init__(parent)
        self.setObjectName("HeaderBar")
        self.setFixedHeight(44)
        self.setStyleSheet("""
            #HeaderBar {
                background-color: #FFFFFF;
                border-bottom: 1px solid #E2E8F0;
            }
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(8)
        layout.addStretch()
        self.live_report_btn = QPushButton("Dashboard", self)
        self.live_report_btn.setIcon(create_minimalist_icon("chart", "#0078D4"))
        self.live_report_btn.setIconSize(QSize(16, 16))
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
        self.sessions_btn = QPushButton("", self)
        self.sessions_btn.setIcon(create_minimalist_icon("folder", "#475569"))
        self.sessions_btn.setIconSize(QSize(16, 16))
        self.sessions_btn.setToolTip("Session Manager")
        self.sessions_btn.setFixedSize(28, 28)
        self.sessions_btn.setStyleSheet("""
            QPushButton {
                background: none;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #F1F5F9;
            }
        """)
        self.sessions_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sessions_btn.clicked.connect(cmd_sessions)
        layout.addWidget(self.sessions_btn)
        self.settings_btn = QPushButton("", self)
        self.settings_btn.setIcon(create_minimalist_icon("settings", "#475569"))
        self.settings_btn.setIconSize(QSize(16, 16))
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.setFixedSize(28, 28)
        self.settings_btn.setStyleSheet("""
            QPushButton {
                background: none;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #F1F5F9;
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
            cmd_report=self._show_dashboard,
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
        self.clock_label.setStyleSheet("font-family: 'Segoe UI'; font-size: 36px; font-weight: bold; color: #0F172A;")
        ctrl_layout.addWidget(self.clock_label)

        self.earnings_label = QLabel("", self)
        self.earnings_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.earnings_label.setStyleSheet("font-family: 'Segoe UI'; font-size: 13px; font-weight: bold; color: #16A34A;")
        ctrl_layout.addWidget(self.earnings_label)

        self.active_label = QLabel("Ready to track", self)
        self.active_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.active_label.setStyleSheet("font-family: 'Segoe UI'; font-size: 10px; color: #475569;")
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

    def _show_session_manager(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Session Manager")
        self._center_window(dialog, 520, 540)
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        
        selected_sessions = set()
        
        tab_widget = QTabWidget(dialog)
        tab_widget.setObjectName("SessionTabs")

        edit_btn = QPushButton("Edit", dialog)
        edit_btn.setCheckable(True)
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
                padding: 4px 12px;
                font-family: 'Segoe UI';
                font-size: 12px;
                font-weight: bold;
                color: #475569;
            }
            QPushButton:checked {
                background-color: #0078D4;
                color: white;
                border-color: #0078D4;
            }
            QPushButton:hover {
                background-color: #F1F5F9;
            }
            QPushButton:checked:hover {
                background-color: #106EBE;
            }
        """)
        tab_widget.setCornerWidget(edit_btn, Qt.Corner.TopRightCorner)

        def get_svg_icon(svg_content, size=QSize(16, 16), color="#33363F"):
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
                painter.setPen(QPen(QColor(color), 2))
                painter.drawRect(2, 2, 12, 12)
            painter.end()
            return QIcon(pixmap)

        rename_svg = RENAME_SVG
        trash_svg = TRASH_SVG
        restore_svg = RESTORE_SVG

        def send_to_recycle_bin(path):
            try:
                import ctypes
                from ctypes import wintypes
                
                class SHFILEOPSTRUCTW(ctypes.Structure):
                    _fields_ = [
                        ("hwnd", wintypes.HWND),
                        ("wFunc", wintypes.UINT),
                        ("pFrom", wintypes.LPCWSTR),
                        ("pTo", wintypes.LPCWSTR),
                        ("fFlags", wintypes.USHORT),
                        ("fAnyOperationsAborted", wintypes.BOOL),
                        ("hNameMappings", wintypes.LPVOID),
                        ("lpszProgressTitle", wintypes.LPCWSTR),
                    ]
                
                FO_DELETE = 3
                FOF_ALLOWUNDO = 0x0040
                FOF_NOCONFIRMATION = 0x0010
                FOF_NOERRORUI = 0x0400
                
                abs_path = os.path.abspath(path)
                path_dn = abs_path + "\0\0"
                
                fileop = SHFILEOPSTRUCTW()
                fileop.hwnd = None
                fileop.wFunc = FO_DELETE
                fileop.pFrom = path_dn
                fileop.pTo = None
                fileop.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_NOERRORUI
                
                shell32 = ctypes.windll.shell32
                result = shell32.SHFileOperationW(ctypes.byref(fileop))
                return result == 0
            except Exception as e:
                print(f"[FocusLog] Recycle bin failed: {e}")
                return False
         
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

        trash_scroll = QScrollArea()
        trash_scroll.setWidgetResizable(True)
        trash_widget = QWidget()
        trash_widget.setObjectName("trash_widget")
        trash_layout = QVBoxLayout(trash_widget)
        trash_layout.setContentsMargins(4, 4, 4, 4)
        trash_layout.setSpacing(4)
        
        history_folder = os.path.join(get_app_data_dir(), "sessions")
        autosave_folder = os.path.join(get_app_data_dir(), "autosave")
        trash_folder = os.path.join(get_app_data_dir(), "trash")
        os.makedirs(history_folder, exist_ok=True)
        os.makedirs(autosave_folder, exist_ok=True)
        os.makedirs(trash_folder, exist_ok=True)
        
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
            # Clear old layout (including widgets and stretches)
            while layout_container.count() > 0:
                item = layout_container.takeAt(0)
                if item and item.widget():
                    item.widget().setParent(None)
                    
            files = glob.glob(os.path.join(folder, "*.json"))
            files.sort(key=os.path.getmtime, reverse=True)
            if not files:
                if folder == trash_folder:
                    label_txt = "No trashed sessions found."
                elif is_recoveries:
                    label_txt = "No auto-saves/recoveries found."
                else:
                    label_txt = "No manual sessions found."
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
                
                is_trash = (folder == trash_folder)
                if not is_recoveries and not is_trash:
                    cb_select = QCheckBox(row_frame)
                    cb_select.setFixedWidth(20)
                    
                    def make_cb_connector(path):
                        return lambda state: (
                            selected_sessions.add(path) if state == 2 else selected_sessions.discard(path)
                        )
                    cb_select.stateChanged.connect(make_cb_connector(filepath))
                    row_layout.addWidget(cb_select)
                
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

                def _rename_session_file(path, current_name):
                    new_name, ok = QInputDialog.getText(dialog, "Rename Session", "Enter new session name:", QLineEdit.EchoMode.Normal, current_name)
                    if ok and new_name.strip():
                        confirm = QMessageBox.question(
                            dialog,
                            "Confirm Rename",
                            f"Are you sure you want to rename this session to '{new_name.strip()}'?",
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                            QMessageBox.StandardButton.No
                        )
                        if confirm == QMessageBox.StandardButton.Yes:
                            try:
                                with open(path, "r", encoding="utf-8") as f:
                                    data = json.load(f)
                                data["session_name"] = new_name.strip()
                                with open(path, "w", encoding="utf-8") as f:
                                    json.dump(data, f, indent=4)
                                _refresh_all_lists()
                            except Exception as e:
                                QMessageBox.critical(dialog, "Error", f"Could not rename session:\n{e}")

                def _delete_session_file(path):
                    is_trash = (folder == trash_folder)
                    if is_trash:
                        reply = QMessageBox.question(
                            dialog,
                            "Delete Permanently",
                            "Are you sure you want to permanently move this session to the Windows Recycle Bin?",
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                            QMessageBox.StandardButton.No
                        )
                        if reply == QMessageBox.StandardButton.Yes:
                            try:
                                selected_sessions.discard(path)
                                if not send_to_recycle_bin(path):
                                    if os.path.exists(path):
                                        os.remove(path)
                                _refresh_all_lists()
                            except Exception as e:
                                QMessageBox.critical(dialog, "Error", f"Could not delete session:\n{e}")
                    else:
                        reply = QMessageBox.question(
                            dialog,
                            "Move to Trash",
                            "Are you sure you want to move this session to the Trash?",
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                            QMessageBox.StandardButton.No
                        )
                        if reply == QMessageBox.StandardButton.Yes:
                            try:
                                filename = os.path.basename(path)
                                dest_path = os.path.join(trash_folder, filename)
                                if os.path.exists(dest_path):
                                    base, ext = os.path.splitext(filename)
                                    dest_path = os.path.join(trash_folder, f"{base}_{int(time.time())}{ext}")
                                import shutil
                                shutil.move(path, dest_path)
                                selected_sessions.discard(path)
                                _refresh_all_lists()
                            except Exception as e:
                                QMessageBox.critical(dialog, "Error", f"Could not move session to Trash:\n{e}")

                def _restore_session_file(path):
                    try:
                        filename = os.path.basename(path)
                        if "auto_" in filename or "recovery_" in filename:
                            dest_folder = autosave_folder
                        else:
                            dest_folder = history_folder
                        dest_path = os.path.join(dest_folder, filename)
                        if os.path.exists(dest_path):
                            base, ext = os.path.splitext(filename)
                            dest_path = os.path.join(dest_folder, f"{base}_restored_{int(time.time())}{ext}")
                        import shutil
                        shutil.move(path, dest_path)
                        _refresh_all_lists()
                    except Exception as e:
                        QMessageBox.critical(dialog, "Error", f"Could not restore session:\n{e}")

                is_trash = (folder == trash_folder)
                is_edit_active = edit_btn.isChecked()

                if is_trash:
                    rest_icon = get_svg_icon(restore_svg, QSize(16, 16), "#0F7B0F")
                    del_icon = get_svg_icon(trash_svg, QSize(18, 18), "#FF0000")

                    restore_btn = QPushButton(row_frame)
                    restore_btn.setIcon(rest_icon)
                    restore_btn.setIconSize(QSize(16, 16))
                    restore_btn.setToolTip("Restore Session")
                    restore_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                    restore_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #F0FDF4;
                            border: 1px solid #DCFCE7;
                            border-radius: 4px;
                            padding: 4px;
                            min-width: 28px;
                            min-height: 28px;
                        }
                        QPushButton:hover {
                            background-color: #DCFCE7;
                            border-color: #86EFAC;
                        }
                    """)
                    restore_btn.clicked.connect(lambda checked, p=filepath: _restore_session_file(p))
                    btn_layout.addWidget(restore_btn)

                    delete_btn = QPushButton(row_frame)
                    delete_btn.setIcon(del_icon)
                    delete_btn.setIconSize(QSize(18, 18))
                    delete_btn.setToolTip("Move to Windows Recycle Bin")
                    delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                    delete_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #FFF5F5;
                            border: 1px solid #FEE2E2;
                            border-radius: 4px;
                            padding: 4px;
                            min-width: 28px;
                            min-height: 28px;
                        }
                        QPushButton:hover {
                            background-color: #FEE2E2;
                            border-color: #FCA5A5;
                        }
                    """)
                    delete_btn.clicked.connect(lambda checked, p=filepath: _delete_session_file(p))
                    btn_layout.addWidget(delete_btn)

                    restore_btn.setVisible(is_edit_active)
                    delete_btn.setVisible(is_edit_active)
                else:
                    ren_icon = get_svg_icon(rename_svg, QSize(16, 16), "#0078D4")
                    del_icon = get_svg_icon(trash_svg, QSize(18, 18), "#FF0000")

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

                    rename_btn = QPushButton(row_frame)
                    rename_btn.setIcon(ren_icon)
                    rename_btn.setIconSize(QSize(16, 16))
                    rename_btn.setToolTip("Rename Session")
                    rename_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                    rename_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #FFFFFF;
                            border: 1px solid #CBD5E1;
                            border-radius: 4px;
                            padding: 4px;
                            min-width: 28px;
                            min-height: 28px;
                        }
                        QPushButton:hover {
                            background-color: #F1F5F9;
                            border-color: #94A3B8;
                        }
                    """)
                    rename_btn.clicked.connect(lambda checked, p=filepath, n=session_name: _rename_session_file(p, n))
                    btn_layout.addWidget(rename_btn)

                    delete_btn = QPushButton(row_frame)
                    delete_btn.setIcon(del_icon)
                    delete_btn.setIconSize(QSize(18, 18))
                    delete_btn.setToolTip("Move to Trash")
                    delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                    delete_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #FFF5F5;
                            border: 1px solid #FEE2E2;
                            border-radius: 4px;
                            padding: 4px;
                            min-width: 28px;
                            min-height: 28px;
                        }
                        QPushButton:hover {
                            background-color: #FEE2E2;
                            border-color: #FCA5A5;
                        }
                    """)
                    delete_btn.clicked.connect(lambda checked, p=filepath: _delete_session_file(p))
                    btn_layout.addWidget(delete_btn)

                    res_btn.setVisible(not is_edit_active)
                    view_btn.setVisible(not is_edit_active)
                    rename_btn.setVisible(is_edit_active)
                    delete_btn.setVisible(is_edit_active)
                
                row_layout.addLayout(btn_layout)
                layout_container.addWidget(row_frame)
                
            layout_container.addStretch()
 
        def _refresh_all_lists():
            _render_list(sessions_layout, history_folder, False)
            _render_list(recoveries_layout, autosave_folder, True)
            _render_list(trash_layout, trash_folder, False)

        _refresh_all_lists()

        edit_btn.clicked.connect(_refresh_all_lists)
        
        sessions_scroll.setWidget(sessions_widget)
        recoveries_scroll.setWidget(recoveries_widget)
        trash_scroll.setWidget(trash_widget)
        
        tab_widget.addTab(sessions_scroll, "Sessions")
        tab_widget.addTab(recoveries_scroll, "Recoveries")
        tab_widget.addTab(trash_scroll, "Trash")
        
        layout.addWidget(tab_widget)
        
        footer = QHBoxLayout()
        export_btn = QPushButton("📊 CSV", dialog)
        export_btn.setToolTip("Export All manually saved sessions to CSV")
        export_btn.setObjectName("NormalButton")
        export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        export_btn.clicked.connect(self._export_csv_history)
        footer.addWidget(export_btn)
        
        # New Generate Selected HTML Invoice button
        def _generate_selected_html_invoice():
            if not selected_sessions:
                QMessageBox.warning(dialog, "No Sessions Selected", "Please select at least one session using the checkbox on the left of the item.")
                return
            
            # Show save path dialog
            default_html_name = f"FocusLog_Invoice_{datetime.now().strftime('%Y-%m-%d')}.html"
            html_filepath, _ = QFileDialog.getSaveFileName(dialog, "Save Invoice HTML", default_html_name, "HTML Files (*.html)")
            if not html_filepath:
                return
                
            try:
                # Mask sensitive data custom options dialog
                privacy_dialog = InvoicePrivacyOptionsDialog(
                    dialog,
                    default_biz_email=self.mask_business_emails,
                    default_biz_phone=self.mask_business_phone,
                    default_client_email=self.mask_client_emails
                )
                if privacy_dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                
                mask_biz_email = privacy_dialog.cb_biz_email.isChecked()
                mask_biz_phone = privacy_dialog.cb_biz_phone.isChecked()
                mask_client_email = privacy_dialog.cb_client_email.isChecked()

                from report import merge_sessions_for_invoice, generate_invoice_html
                
                billing_data = merge_sessions_for_invoice(list(selected_sessions), self.tracker, self.hourly_rate, self.currency_symbol)
                settings_data = {
                    "business_name": self.business_name,
                    "business_emails": self.business_emails,
                    "business_email": self.business_email,
                    "business_phone": self.business_phone,
                    "business_address": self.business_address,
                    "business_payment": self.business_payment,
                    "client_name": self.client_name,
                    "client_emails": self.client_emails,
                    "client_address": self.client_address,
                    "business_logo_path": self.business_logo_path,
                    "hourly_rate": self.hourly_rate,
                    "currency_symbol": self.currency_symbol,
                    "qr_code_paths": self.qr_code_paths,
                    
                    "mask_business_emails": mask_biz_email,
                    "mask_business_phone": mask_biz_phone,
                    "mask_client_emails": mask_client_email,
                }
                
                html_content = generate_invoice_html(billing_data, settings_data)
                with open(html_filepath, "w", encoding="utf-8") as f:
                    f.write(html_content)
                
                reply = QMessageBox.question(
                    dialog, 
                    "Invoice Created", 
                    f"Invoice HTML generated successfully at:\n{html_filepath}\n\nWould you like to open it in your browser now to print/save as PDF?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    os.startfile(html_filepath)
            except Exception as e:
                QMessageBox.critical(dialog, "Error", f"Failed to generate invoice HTML:\n{str(e)}")
                
        html_invoice_btn = QPushButton("📄 Generate HTML Invoice", dialog)
        html_invoice_btn.setObjectName("AccentButton")
        html_invoice_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        html_invoice_btn.clicked.connect(_generate_selected_html_invoice)
        footer.addWidget(html_invoice_btn)
        
        footer.addStretch()
        
        open_folder_btn = QPushButton("Folder", dialog)
        open_folder_btn.setToolTip("Open manual saved sessions folder")
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

    def _handle_interrupted_session(self):
        """Prompt the user to recover a crashed or interrupted tracking session."""
        from tracker import ACTIVE_SESSION_FILE
        if not os.path.exists(ACTIVE_SESSION_FILE):
            return
            
        reply = QMessageBox.question(
            self,
            "Recover Session?",
            "FocusLog detected an interrupted tracking session. Would you like to recover it?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if self.tracker.recover_session():
                    self.start_btn.setEnabled(False)
                    self.pause_btn.setEnabled(True)
                    self.pause_btn.setText("⏸ Pause" if not self.tracker.paused else "▶ Resume")
                    self.stop_btn.setEnabled(True)
                    
                    self.start_btn.setObjectName("AccentButton")
                    self.pause_btn.setObjectName("NormalButton")
                    self.stop_btn.setObjectName("RedButton")
                    
                    if self.hourly_rate > 0:
                        self.earnings_label.setText(f"💰 {self.currency_symbol}0.00 earned")
                    self.active_label.setText(f"▶ Recovered: {self.tracker.session_name}")
                    self.active_label.setStyleSheet("color: #0F7B0F; font-size: 10px;")
                    
                    self.clock_timer.start(250)
                    self._refresh_app_list()
                    QMessageBox.information(self, "Recovered", "Previous session recovered successfully.")
                else:
                    QMessageBox.critical(self, "Recovery Error", "Failed to recover the previous session.")
                    if os.path.exists(ACTIVE_SESSION_FILE):
                        os.remove(ACTIVE_SESSION_FILE)
            except Exception as e:
                QMessageBox.critical(self, "Recovery Error", f"An error occurred during recovery:\n{e}")
                if os.path.exists(ACTIVE_SESSION_FILE):
                    try:
                        os.remove(ACTIVE_SESSION_FILE)
                    except Exception:
                        pass
        else:
            try:
                os.remove(ACTIVE_SESSION_FILE)
            except Exception:
                pass

    def _load_app_settings(self):
        self.confirm_on_close = True
        self.min_track_seconds = 2
        self.auto_save_seconds = 10
        self.currency_symbol = "$"
        self.hourly_rate = 0.0
        self.idle_threshold_seconds_total = 120  # default: 2 min (0 = disabled)
        self.business_name = ""
        self.business_emails = []   # NEW: list of business contact emails
        self.business_email = ""    # LEGACY: kept for backward compat
        self.business_phone = ""
        self.business_address = ""
        self.business_payment = ""
        self.client_name = ""
        self.client_emails = []     # NEW: list of client contact emails
        self.client_address = ""
        self.business_logo_path = ""
        self.qr_code_paths = []     # NEW: list of payment QR code filenames
        self.mask_business_emails = False
        self.mask_business_phone = False
        self.mask_client_emails = False
        self.mask_sensitive_data = False  # LEGACY: default mask toggle for invoices
        
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
                    
                    self.business_name = data.get("business_name", "")
                    self.business_phone = data.get("business_phone", "")
                    self.business_address = data.get("business_address", "")
                    self.business_payment = data.get("business_payment", "")
                    self.client_name = data.get("client_name", "")
                    self.client_address = data.get("client_address", "")
                    self.business_logo_path = data.get("business_logo_path", "")
                    
                    # Multi-email lists with backward compat migration
                    self.business_emails = data.get("business_emails", [])
                    if not self.business_emails:
                        old_email = data.get("business_email", "")
                        if old_email:
                            self.business_emails = [old_email]
                    self.business_email = ", ".join(self.business_emails)  # legacy compat
                    
                    self.client_emails = data.get("client_emails", [])
                    
                    # QR codes and masking with granular preferences
                    self.qr_code_paths = data.get("qr_code_paths", [])
                    legacy_mask = data.get("mask_sensitive_data", False)
                    self.mask_business_emails = data.get("mask_business_emails", legacy_mask)
                    self.mask_business_phone = data.get("mask_business_phone", legacy_mask)
                    self.mask_client_emails = data.get("mask_client_emails", legacy_mask)
                    self.mask_sensitive_data = legacy_mask
            except Exception as e:
                print(f"[FocusLog] Failed to load app settings: {e}")

    def _save_app_settings(self):
        try:
            dirpath = os.path.dirname(APP_SETTINGS_FILE)
            if dirpath:
                os.makedirs(dirpath, exist_ok=True)
            data = {
                "confirm_on_close": self.confirm_on_close,
                "min_track_seconds": self.min_track_seconds,
                "auto_save_seconds": self.auto_save_seconds,
                "currency_symbol": self.currency_symbol,
                "hourly_rate": self.hourly_rate,
                "idle_threshold_seconds_total": self.idle_threshold_seconds_total,
                "business_name": self.business_name,
                "business_emails": self.business_emails,
                "business_email": ", ".join(self.business_emails),  # legacy compat
                "business_phone": self.business_phone,
                "business_address": self.business_address,
                "business_payment": self.business_payment,
                "client_name": self.client_name,
                "client_emails": self.client_emails,
                "client_address": self.client_address,
                "business_logo_path": self.business_logo_path,
                "qr_code_paths": self.qr_code_paths,
                "mask_business_emails": self.mask_business_emails,
                "mask_business_phone": self.mask_business_phone,
                "mask_client_emails": self.mask_client_emails,
                "mask_sensitive_data": self.mask_business_emails or self.mask_business_phone or self.mask_client_emails,
            }
            with open(APP_SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"[FocusLog] Failed to save app settings: {e}")

    def _show_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Settings")
        self._center_window(dialog, 520, 650)
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        
        title = QLabel("Settings", dialog)
        title.setStyleSheet("font-family: 'Segoe UI'; font-size: 15px; font-weight: bold; color: #1A1A1A;")
        layout.addWidget(title)
        
        # QTabWidget for settings categories
        settings_tabs = QTabWidget(dialog)
        settings_tabs.setStyleSheet("""
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
                font-size: 12px;
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
        """)
        
        # ── Tab 1: General Settings ──────────────────────────────────
        tab_general = QWidget()
        tg_main_layout = QVBoxLayout(tab_general)
        tg_main_layout.setContentsMargins(0, 0, 0, 0)
        tg_main_layout.setSpacing(0)
        
        scroll_general = QScrollArea(tab_general)
        scroll_general.setWidgetResizable(True)
        scroll_general.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_general.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        scroll_general_content = QWidget()
        tg_layout = QVBoxLayout(scroll_general_content)
        tg_layout.setContentsMargins(12, 12, 12, 12)
        tg_layout.setSpacing(6)
        
        cb_confirm = QCheckBox("Always ask for confirmation before closing", scroll_general_content)
        cb_confirm.setChecked(self.confirm_on_close)
        cb_confirm.setStyleSheet("font-family: 'Segoe UI'; font-size: 13px;")
        tg_layout.addWidget(cb_confirm)
        
        form_general = QFormLayout()
        form_general.setSpacing(6)
        
        min_sec_entry = QLineEdit(scroll_general_content)
        min_sec_entry.setText(str(self.min_track_seconds))
        form_general.addRow("Min activity threshold (secs):", min_sec_entry)
        
        auto_save_entry = QLineEdit(scroll_general_content)
        auto_save_entry.setText(str(self.auto_save_seconds))
        form_general.addRow("Auto-save interval (secs):", auto_save_entry)
        
        # Idle row
        idle_row = QHBoxLayout()
        idle_row.setSpacing(4)
        _idle_total = getattr(self, "idle_threshold_seconds_total", 120)
        _idle_m_def = _idle_total // 60
        _idle_s_def = _idle_total % 60
        
        idle_min_entry = QLineEdit(scroll_general_content)
        idle_min_entry.setFixedWidth(40)
        idle_min_entry.setText(str(_idle_m_def))
        idle_row.addWidget(idle_min_entry)
        idle_row.addWidget(QLabel("min"))
        
        idle_sec_entry = QLineEdit(scroll_general_content)
        idle_sec_entry.setFixedWidth(40)
        idle_sec_entry.setText(str(_idle_s_def))
        idle_row.addWidget(idle_sec_entry)
        idle_row.addWidget(QLabel("sec"))
        idle_row.addStretch()
        
        form_general.addRow("Idle auto-pause:", idle_row)
        
        # Billing Group details inside general tab
        currency_options = [
            "$ (USD)", "€ (EUR)", "£ (GBP)", "¥ (JPY/CNY)", "₱ (PHP)", "₹ (INR)", 
            "₽ (RUB)", "₩ (KRW)", "₫ (VND)", "฿ (THB)", "₪ (ILS)", "₺ (TRY)", 
            "Rp (IDR)", "RM (MYR)", "R$ (BRL)", "C$ (CAD)", "A$ (AUD)", "S$ (SGD)", 
            "NZ$ (NZD)", "CHF (CHF)", "kr (SEK/NOK)", "zł (PLN)", "Kč (CZK)", 
            "Ft (HUF)", "lei (RON)", "лв (BGN)", "₴ (UAH)", "R (ZAR)"
        ]
        curr_combo = QComboBox(scroll_general_content)
        curr_combo.addItems(currency_options)
        matched = [c for c in currency_options if c.startswith(self.currency_symbol)]
        if matched:
            curr_combo.setCurrentText(matched[0])
        else:
            curr_combo.setCurrentText(self.currency_symbol)
        form_general.addRow("Currency symbol:", curr_combo)
        
        rate_entry = QLineEdit(scroll_general_content)
        rate_entry.setText(f"{self.hourly_rate:.2f}")
        form_general.addRow("Hourly rate:", rate_entry)
        
        tg_layout.addLayout(form_general)
        
        # Config Files Group
        config_box = QGroupBox("Configuration & Categories", scroll_general_content)
        config_layout = QVBoxLayout(config_box)
        config_layout.setContentsMargins(8, 8, 8, 8)
        config_layout.setSpacing(4)
        
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

        btn_overrides = QPushButton("Edit Name Overrides", scroll_general_content)
        btn_overrides.setObjectName("NormalButton")
        btn_overrides.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_overrides.clicked.connect(lambda: _open_file(OVERRIDES_FILE))
        config_layout.addWidget(btn_overrides)
        
        excl_row = QHBoxLayout()
        btn_excl = QPushButton("Edit Auto-Exclusions", scroll_general_content)
        btn_excl.setObjectName("NormalButton")
        btn_excl.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_excl.clicked.connect(lambda: _open_file(AUTO_EXCLUDE_FILE))
        excl_row.addWidget(btn_excl, 1)
        
        btn_reload = QPushButton("🔄 Reload", scroll_general_content)
        btn_reload.setObjectName("NormalButton")
        btn_reload.setCursor(Qt.CursorShape.PointingHandCursor)
        
        reload_status_lbl = QLabel(" ", scroll_general_content)
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
        
        btn_categories = QPushButton("Manage Project Categories...", scroll_general_content)
        btn_categories.setObjectName("NormalButton")
        btn_categories.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_categories.clicked.connect(self._show_categories_dialog)
        config_layout.addWidget(btn_categories)
        
        tg_layout.addWidget(config_box)
        tg_layout.addStretch()
        
        scroll_general.setWidget(scroll_general_content)
        tg_main_layout.addWidget(scroll_general)
        
        # ── Tab 2: Billing & Invoicing Details ────────────────────────
        tab_invoice = QWidget()
        ti_layout = QVBoxLayout(tab_invoice)
        ti_layout.setContentsMargins(0, 0, 0, 0)
        ti_layout.setSpacing(0)
        
        scroll_invoice = QScrollArea(tab_invoice)
        scroll_invoice.setWidgetResizable(True)
        scroll_invoice.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_invoice.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        scroll_invoice_content = QWidget()
        scroll_invoice_layout = QVBoxLayout(scroll_invoice_content)
        scroll_invoice_layout.setContentsMargins(12, 12, 12, 12)
        scroll_invoice_layout.setSpacing(10)
        
        # Freelancer Business Profile
        biz_box = QGroupBox("Business Profile Details", scroll_invoice_content)
        biz_layout = QFormLayout(biz_box)
        biz_layout.setSpacing(6)
        
        business_name_entry = QLineEdit(biz_box)
        business_name_entry.setText(self.business_name)
        biz_layout.addRow("Business Name:", business_name_entry)
        
        # Email Chip Widget for business contact emails
        business_email_chips = EmailChipWidget(biz_box)
        business_email_chips.set_emails(self.business_emails)
        biz_layout.addRow("Contact Emails:", business_email_chips)
        
        business_phone_entry = QLineEdit(biz_box)
        business_phone_entry.setText(self.business_phone)
        biz_layout.addRow("Contact Phone:", business_phone_entry)
        
        business_address_entry = QLineEdit(biz_box)
        business_address_entry.setText(self.business_address)
        biz_layout.addRow("Billing Address:", business_address_entry)
        
        business_payment_entry = QLineEdit(biz_box)
        business_payment_entry.setPlaceholderText("e.g. IBAN: US12 3456... or PayPal: ...")
        business_payment_entry.setText(self.business_payment)
        biz_layout.addRow("Payment Details:", business_payment_entry)
        
        scroll_invoice_layout.addWidget(biz_box)
        
        # Default Client Profile
        client_box = QGroupBox("Default Client Profile", scroll_invoice_content)
        client_layout = QFormLayout(client_box)
        client_layout.setSpacing(6)
        
        client_name_entry = QLineEdit(client_box)
        client_name_entry.setText(self.client_name)
        client_layout.addRow("Client Name:", client_name_entry)
        
        # Email Chip Widget for client contact emails
        client_email_chips = EmailChipWidget(client_box)
        client_email_chips.set_emails(self.client_emails)
        client_layout.addRow("Client Emails:", client_email_chips)
        
        client_address_entry = QLineEdit(client_box)
        client_address_entry.setText(self.client_address)
        client_layout.addRow("Client Address:", client_address_entry)
        
        scroll_invoice_layout.addWidget(client_box)
        
        # Logo Profile Configuration
        logo_box = QGroupBox("Invoice Business Logo", scroll_invoice_content)
        logo_layout = QVBoxLayout(logo_box)
        logo_layout.setSpacing(4)
        
        logo_row = QHBoxLayout()
        logo_path_entry = QLineEdit(logo_box)
        logo_path_entry.setText(self.business_logo_path)
        logo_row.addWidget(logo_path_entry, 1)
        
        def _browse_logo():
            path, _ = QFileDialog.getOpenFileName(dialog, "Select Business Logo Image", "", "Image files (*.png *.jpg *.jpeg)")
            if path:
                logo_path_entry.setText(path)
                
        browse_logo_btn = QPushButton("Browse...", logo_box)
        browse_logo_btn.setObjectName("NormalButton")
        browse_logo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_logo_btn.clicked.connect(_browse_logo)
        logo_row.addWidget(browse_logo_btn)
        logo_layout.addLayout(logo_row)
        
        logo_spec_lbl = QLabel("Image Spec: PNG, JPG, or JPEG. Max size: 250px (w) x 80px (h). Proportionally resized automatically.", logo_box)
        logo_spec_lbl.setWordWrap(True)
        logo_spec_lbl.setStyleSheet("color: #64748B; font-size: 10px; font-family: 'Segoe UI';")
        logo_layout.addWidget(logo_spec_lbl)
        
        scroll_invoice_layout.addWidget(logo_box)
        
        # ── Payment QR Codes Section ─────────────────────────────────
        qr_box = QGroupBox("Payment QR Codes", scroll_invoice_content)
        qr_box_layout = QVBoxLayout(qr_box)
        qr_box_layout.setSpacing(6)
        
        qr_thumbs_widget = QWidget(qr_box)
        qr_thumbs_layout = QHBoxLayout(qr_thumbs_widget)
        qr_thumbs_layout.setContentsMargins(0, 0, 0, 0)
        qr_thumbs_layout.setSpacing(8)
        
        # Track QR paths for this dialog session
        _qr_paths_local = list(self.qr_code_paths)
        _qr_thumb_refs = []  # keep references to thumbnail frames
        
        def _refresh_qr_thumbnails():
            """Rebuild QR thumbnail strip from _qr_paths_local."""
            # Clear existing thumbnails
            for ref in _qr_thumb_refs:
                qr_thumbs_layout.removeWidget(ref)
                ref.deleteLater()
            _qr_thumb_refs.clear()
            
            qr_dir = os.path.join(get_app_data_dir(), "qr_codes")
            for qr_filename in _qr_paths_local:
                qr_full_path = os.path.join(qr_dir, qr_filename)
                if not os.path.exists(qr_full_path):
                    continue
                    
                thumb_frame = QFrame(qr_thumbs_widget)
                thumb_frame.setFixedSize(72, 72)
                thumb_frame.setStyleSheet("""
                    QFrame {
                        background-color: #F8FAFC;
                        border: 1px solid #E2E8F0;
                        border-radius: 8px;
                    }
                """)
                thumb_inner = QVBoxLayout(thumb_frame)
                thumb_inner.setContentsMargins(4, 4, 4, 4)
                thumb_inner.setSpacing(0)
                
                # QR image thumbnail
                pix = QPixmap(qr_full_path)
                if not pix.isNull():
                    pix = pix.scaled(56, 56, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                thumb_lbl = QLabel(thumb_frame)
                thumb_lbl.setPixmap(pix)
                thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                thumb_lbl.setStyleSheet("border: none; background: transparent;")
                thumb_inner.addWidget(thumb_lbl)
                
                # Overlay remove button
                remove_qr_btn = QPushButton("✕", thumb_frame)
                remove_qr_btn.setFixedSize(18, 18)
                remove_qr_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                remove_qr_btn.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(239, 68, 68, 0.85);
                        color: white;
                        border: none;
                        border-radius: 9px;
                        font-size: 10px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background-color: #DC2626;
                    }
                """)
                remove_qr_btn.move(54, 0)
                
                def _remove_qr(fname=qr_filename):
                    if fname in _qr_paths_local:
                        _qr_paths_local.remove(fname)
                    _refresh_qr_thumbnails()
                
                remove_qr_btn.clicked.connect(_remove_qr)
                
                qr_thumbs_layout.addWidget(thumb_frame)
                _qr_thumb_refs.append(thumb_frame)
            
            qr_thumbs_layout.addStretch()
        
        _refresh_qr_thumbnails()
        qr_box_layout.addWidget(qr_thumbs_widget)
        
        def _add_qr_code():
            if len(_qr_paths_local) >= 4:
                QMessageBox.information(dialog, "QR Limit", "Maximum of 4 QR code images allowed.")
                return
            path, _ = QFileDialog.getOpenFileName(dialog, "Select Payment QR Code Image", "", "Image files (*.png *.jpg *.jpeg)")
            if not path:
                return
            import shutil
            qr_dir = os.path.join(get_app_data_dir(), "qr_codes")
            os.makedirs(qr_dir, exist_ok=True)
            fname = f"qr_{len(_qr_paths_local)+1}_{os.path.basename(path)}"
            dest = os.path.join(qr_dir, fname)
            try:
                shutil.copy2(path, dest)
                _qr_paths_local.append(fname)
                _refresh_qr_thumbnails()
            except Exception as ex:
                QMessageBox.critical(dialog, "Error", f"Failed to copy QR image:\n{ex}")
        
        add_qr_btn = QPushButton("+ Add QR Code", qr_box)
        add_qr_btn.setObjectName("NormalButton")
        add_qr_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_qr_btn.clicked.connect(_add_qr_code)
        qr_box_layout.addWidget(add_qr_btn)
        
        qr_spec_lbl = QLabel("Upload up to 4 payment QR code images (PNG/JPG). They will appear in generated invoices at 140×140px.", qr_box)
        qr_spec_lbl.setWordWrap(True)
        qr_spec_lbl.setStyleSheet("color: #64748B; font-size: 10px; font-family: 'Segoe UI';")
        qr_box_layout.addWidget(qr_spec_lbl)
        
        scroll_invoice_layout.addWidget(qr_box)
        
        # ── Sensitive Data Masking Toggles ────────────────────────────
        mask_box = QGroupBox("Privacy Settings", scroll_invoice_content)
        mask_layout = QVBoxLayout(mask_box)
        mask_layout.setSpacing(6)
        
        mask_biz_email_cb = QCheckBox("Mask business contact emails by default", mask_box)
        mask_biz_email_cb.setChecked(self.mask_business_emails)
        mask_biz_email_cb.setStyleSheet("font-family: 'Segoe UI'; font-size: 12px;")
        mask_layout.addWidget(mask_biz_email_cb)
        
        mask_biz_phone_cb = QCheckBox("Mask business contact phone number by default", mask_box)
        mask_biz_phone_cb.setChecked(self.mask_business_phone)
        mask_biz_phone_cb.setStyleSheet("font-family: 'Segoe UI'; font-size: 12px;")
        mask_layout.addWidget(mask_biz_phone_cb)
        
        mask_client_email_cb = QCheckBox("Mask client contact emails by default", mask_box)
        mask_client_email_cb.setChecked(self.mask_client_emails)
        mask_client_email_cb.setStyleSheet("font-family: 'Segoe UI'; font-size: 12px;")
        mask_layout.addWidget(mask_client_email_cb)
        
        mask_hint = QLabel("When enabled, sensitive contact details (emails, phone) are masked on the generated invoice. You can override these per-invoice.", mask_box)
        mask_hint.setWordWrap(True)
        mask_hint.setStyleSheet("color: #64748B; font-size: 10px; font-family: 'Segoe UI';")
        mask_layout.addWidget(mask_hint)
        
        scroll_invoice_layout.addWidget(mask_box)
        
        scroll_invoice.setWidget(scroll_invoice_content)
        ti_layout.addWidget(scroll_invoice)
        
        # Add Tabs to Widget
        settings_tabs.addTab(tab_general, "General && Controls")
        settings_tabs.addTab(tab_invoice, "Billing && Invoices")
        layout.addWidget(settings_tabs)
        
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
                
                # Invoice settings
                self.business_name = business_name_entry.text().strip()
                self.business_emails = business_email_chips.get_emails()
                self.business_email = ", ".join(self.business_emails)
                self.business_phone = business_phone_entry.text().strip()
                self.business_address = business_address_entry.text().strip()
                self.business_payment = business_payment_entry.text().strip()
                self.client_name = client_name_entry.text().strip()
                self.client_emails = client_email_chips.get_emails()
                self.client_address = client_address_entry.text().strip()
                self.business_logo_path = logo_path_entry.text().strip()
                self.qr_code_paths = list(_qr_paths_local)
                
                self.mask_business_emails = mask_biz_email_cb.isChecked()
                self.mask_business_phone = mask_biz_phone_cb.isChecked()
                self.mask_client_emails = mask_client_email_cb.isChecked()
                self.mask_sensitive_data = self.mask_business_emails or self.mask_business_phone or self.mask_client_emails
                
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
        
        html_btn = QPushButton("Export .html", footer_f)
        html_btn.setObjectName("AccentButton")
        html_btn.clicked.connect(lambda: export_with_name("html"))
        footer_layout.addWidget(html_btn)
        
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
        else: 
            path, _ = QFileDialog.getSaveFileName(self, "Export HTML", f"focuslog_{report['date']}.html", "HTML Files (*.html)")
            
        if not path: 
            return
        try:
            if fmt == "txt": 
                export_txt(report, path)
            else: 
                html_content = generate_session_report_html(report, hourly_rate=self.hourly_rate, currency_symbol=self.currency_symbol)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                reply = QMessageBox.question(
                    self, "Open Report",
                    f"Session HTML report generated successfully at:\n{path}\n\nWould you like to open it in your browser now?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                if reply == QMessageBox.StandardButton.Yes:
                    import os
                    os.startfile(path)
                return
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

    def _show_dashboard(self):
        dialog = FocusLogDashboard(self)
        dialog.exec()

    def run(self):
        self.show()

class FocusLogDashboard(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_app = parent  # Reference to FocusLogApp
        self.setWindowTitle("FocusLog — Analytics Dashboard")
        self.resize(800, 680)
        self.setMinimumSize(740, 600)
        
        # Center dashboard window
        self.main_app._center_window(self, 800, 680)
        
        # Set styling similar to main window
        self.setStyleSheet(self.main_app.styleSheet())
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 1. Header Bar
        hdr = QFrame(self)
        hdr.setFixedHeight(46)
        hdr.setStyleSheet("QFrame { background-color: #FFFFFF; border-bottom: 1px solid #E2E8F0; }")
        hdr_layout = QHBoxLayout(hdr)
        hdr_layout.setContentsMargins(16, 0, 16, 0)
        
        title_lbl = QLabel("📊 Focus Analytics Dashboard", hdr)
        title_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 15px; font-weight: bold; color: #0F172A; border: none;")
        hdr_layout.addWidget(title_lbl)
        hdr_layout.addStretch()
        
        close_icon_btn = QPushButton("Close", hdr)
        close_icon_btn.setObjectName("NormalButton")
        close_icon_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_icon_btn.clicked.connect(self.accept)
        hdr_layout.addWidget(close_icon_btn)
        
        layout.addWidget(hdr)
        
        # 2. Tab Widget
        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("DashboardTabs")
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                background-color: #F8FAFC;
            }
            QTabBar::tab {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-bottom: none;
                padding: 8px 24px;
                font-family: 'Segoe UI';
                font-size: 13px;
                font-weight: 500;
                color: #475569;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 4px;
                margin-top: 6px;
            }
            QTabBar::tab:selected {
                background-color: #F8FAFC;
                border-color: #E2E8F0;
                color: #0078D4;
                font-weight: bold;
            }
        """)
        
        # Create Tab 1: Live Analytics
        self.live_tab = QWidget()
        self.build_live_tab()
        
        # Create Tab 2: Historical Insights
        self.history_tab = QWidget()
        self.build_history_tab()
        
        self.tabs.addTab(self.live_tab, "Live Tracker Insights")
        self.tabs.addTab(self.history_tab, "Historical Insights")
        self.tabs.currentChanged.connect(self.on_tab_changed)
        
        layout.addWidget(self.tabs)
        
        # Timer for real-time live data updates
        self.live_timer = QTimer(self)
        self.live_timer.timeout.connect(self.update_live_data)
        
        # Set initial state
        self.on_tab_changed(0)

    def create_kpi_card(self, title, value_text, icon_text=None, value_color="#0F172A"):
        card = QFrame(self)
        card.setObjectName("MainCard")
        card.setStyleSheet("""
            QFrame#MainCard {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
            }
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)
        
        if icon_text:
            title_row = QHBoxLayout()
            title_lbl = QLabel(title)
            title_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 11px; color: #64748B; font-weight: 500;")
            icon_lbl = QLabel(icon_text)
            icon_lbl.setStyleSheet("font-size: 14px;")
            title_row.addWidget(title_lbl)
            title_row.addStretch()
            title_row.addWidget(icon_lbl)
            layout.addLayout(title_row)
        else:
            title_lbl = QLabel(title)
            title_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 11px; color: #64748B; font-weight: 500;")
            layout.addWidget(title_lbl)
            
        val_lbl = QLabel(value_text)
        val_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 18px; font-weight: bold; color: {value_color};")
        layout.addWidget(val_lbl)
        
        return card, val_lbl

    def build_live_tab(self):
        self.live_layout = QVBoxLayout(self.live_tab)
        self.live_layout.setContentsMargins(16, 16, 16, 16)
        self.live_layout.setSpacing(12)
        
        # Placeholder for when tracking is inactive
        self.live_placeholder = QFrame(self.live_tab)
        self.live_placeholder.setObjectName("MainCard")
        ph_layout = QVBoxLayout(self.live_placeholder)
        ph_layout.setContentsMargins(40, 40, 40, 40)
        ph_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        ph_icon = QLabel("💤", self.live_placeholder)
        ph_icon.setStyleSheet("font-size: 48px;")
        ph_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph_layout.addWidget(ph_icon)
        
        ph_lbl = QLabel("No active session is currently running.", self.live_placeholder)
        ph_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 14px; font-weight: bold; color: #475569; margin-top: 10px;")
        ph_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph_layout.addWidget(ph_lbl)
        
        ph_sub = QLabel("Start focus tracking from the main screen to view real-time live insights.", self.live_placeholder)
        ph_sub.setStyleSheet("font-family: 'Segoe UI'; font-size: 12px; color: #94A3B8; margin-top: 4px;")
        ph_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph_layout.addWidget(ph_sub)
        
        self.live_layout.addWidget(self.live_placeholder)
        
        # Actual content container
        self.live_content = QWidget(self.live_tab)
        self.live_content_layout = QHBoxLayout(self.live_content)
        self.live_content_layout.setContentsMargins(0, 0, 0, 0)
        self.live_content_layout.setSpacing(16)
        
        # Left column: KPI Cards
        left_col = QVBoxLayout()
        left_col.setSpacing(10)
        
        self.card_live_total, self.lbl_live_total = self.create_kpi_card("Total Session Time", "00:00:00", "🕒")
        self.card_live_focus, self.lbl_live_focus = self.create_kpi_card("Counted Focus Time", "00:00:00", "🛡️", "#0078D4")
        self.card_live_earnings, self.lbl_live_earnings = self.create_kpi_card("Session Earnings", "0.00", "💰", "#16A34A")
        self.card_live_active, self.lbl_live_active = self.create_kpi_card("Current Active App", "None", "💻")
        
        left_col.addWidget(self.card_live_total)
        left_col.addWidget(self.card_live_focus)
        left_col.addWidget(self.card_live_earnings)
        left_col.addWidget(self.card_live_active)
        left_col.addStretch()
        
        self.live_content_layout.addLayout(left_col, 2)
        
        # Right column: Donut Chart & Category breakdown
        right_col = QVBoxLayout()
        right_col.setSpacing(10)
        
        chart_card = QFrame(self.live_content)
        chart_card.setObjectName("MainCard")
        chart_card_layout = QVBoxLayout(chart_card)
        chart_card_layout.setContentsMargins(12, 12, 12, 12)
        
        chart_lbl = QLabel("App Time Allocation", chart_card)
        chart_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 12px; font-weight: bold; color: #475569;")
        chart_card_layout.addWidget(chart_lbl)
        
        self.live_donut = DonutChartWidget(chart_card)
        chart_card_layout.addWidget(self.live_donut, 1)
        
        right_col.addWidget(chart_card, 3)
        
        # Bottom Legend / Category List for Live Tab
        self.live_legend_card = QFrame(self.live_content)
        self.live_legend_card.setObjectName("MainCard")
        ll_layout = QVBoxLayout(self.live_legend_card)
        ll_layout.setContentsMargins(12, 10, 12, 10)
        
        ll_title = QLabel("Focus Categories breakdown", self.live_legend_card)
        ll_title.setStyleSheet("font-family: 'Segoe UI'; font-size: 11px; font-weight: bold; color: #475569;")
        ll_layout.addWidget(ll_title)
        
        # Scroll area for legend list
        self.live_legend_scroll = QScrollArea(self.live_legend_card)
        self.live_legend_scroll.setWidgetResizable(True)
        self.live_legend_scroll.setFixedHeight(120)
        self.live_legend_widget = QWidget()
        self.live_legend_list_layout = QVBoxLayout(self.live_legend_widget)
        self.live_legend_list_layout.setContentsMargins(0, 4, 0, 4)
        self.live_legend_list_layout.setSpacing(4)
        self.live_legend_scroll.setWidget(self.live_legend_widget)
        ll_layout.addWidget(self.live_legend_scroll)
        
        right_col.addWidget(self.live_legend_card, 2)
        
        self.live_content_layout.addLayout(right_col, 3)
        self.live_layout.addWidget(self.live_content)

    def build_history_tab(self):
        self.history_layout = QVBoxLayout(self.history_tab)
        self.history_layout.setContentsMargins(16, 16, 16, 16)
        self.history_layout.setSpacing(12)
        
        # Top Period Selector bar
        period_bar = QHBoxLayout()
        period_bar.setSpacing(8)
        
        period_lbl = QLabel("Select Analysis Range:", self.history_tab)
        period_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 12px; font-weight: bold; color: #475569;")
        period_bar.addWidget(period_lbl)
        
        self.period_combo = QComboBox(self.history_tab)
        self.period_combo.addItems(["Today", "Last 7 Days", "This Month"])
        self.period_combo.currentTextChanged.connect(self.update_history_range)
        self.period_combo.setFixedWidth(140)
        period_bar.addWidget(self.period_combo)
        period_bar.addStretch()
        
        self.history_layout.addLayout(period_bar)
        
        # Main content area (Split layout)
        self.history_content = QWidget(self.history_tab)
        self.hc_layout = QHBoxLayout(self.history_content)
        self.hc_layout.setContentsMargins(0, 0, 0, 0)
        self.hc_layout.setSpacing(16)
        
        # Left side: Historical KPIs
        left_col = QVBoxLayout()
        left_col.setSpacing(10)
        
        self.card_hist_sessions, self.lbl_hist_sessions = self.create_kpi_card("Tracked Sessions", "0", "📊")
        self.card_hist_total, self.lbl_hist_total = self.create_kpi_card("Total Tracked Time", "00:00:00", "🕒")
        self.card_hist_focus, self.lbl_hist_focus = self.create_kpi_card("Total Focus Time", "00:00:00", "🛡️", "#0078D4")
        self.card_hist_earnings, self.lbl_hist_earnings = self.create_kpi_card("Aggregated Earnings", "0.00", "💰", "#16A34A")
        
        left_col.addWidget(self.card_hist_sessions)
        left_col.addWidget(self.card_hist_total)
        left_col.addWidget(self.card_hist_focus)
        left_col.addWidget(self.card_hist_earnings)
        left_col.addStretch()
        
        self.hc_layout.addLayout(left_col, 2)
        
        # Right side: Visual Charts & Legend
        right_col = QVBoxLayout()
        right_col.setSpacing(12)
        
        # Top row: Donut & Bar Charts side-by-side
        charts_row = QHBoxLayout()
        charts_row.setSpacing(10)
        
        # App allocation chart card
        app_card = QFrame(self.history_content)
        app_card.setObjectName("MainCard")
        app_card.setFixedHeight(240)
        ac_layout = QVBoxLayout(app_card)
        ac_layout.setContentsMargins(10, 10, 10, 10)
        
        ac_lbl = QLabel("App Allocation", app_card)
        ac_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 11px; font-weight: bold; color: #475569;")
        ac_layout.addWidget(ac_lbl)
        
        self.hist_donut = DonutChartWidget(app_card)
        ac_layout.addWidget(self.hist_donut, 1)
        charts_row.addWidget(app_card, 1)
        
        # Productivity trend bar chart card
        trend_card = QFrame(self.history_content)
        trend_card.setObjectName("MainCard")
        trend_card.setFixedHeight(240)
        tc_layout = QVBoxLayout(trend_card)
        tc_layout.setContentsMargins(10, 10, 10, 10)
        
        tc_lbl = QLabel("Productivity Hours Trend", trend_card)
        tc_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 11px; font-weight: bold; color: #475569;")
        tc_layout.addWidget(tc_lbl)
        
        self.hist_bar = BarChartWidget(trend_card)
        tc_layout.addWidget(self.hist_bar, 1)
        charts_row.addWidget(trend_card, 1)
        
        right_col.addLayout(charts_row)
        
        # Bottom: Categories/Projects Allocation Summary Legend list
        self.hist_legend_card = QFrame(self.history_content)
        self.hist_legend_card.setObjectName("MainCard")
        hl_layout = QVBoxLayout(self.hist_legend_card)
        hl_layout.setContentsMargins(12, 10, 12, 10)
        
        hl_title = QLabel("Focus Categories Aggregation", self.hist_legend_card)
        hl_title.setStyleSheet("font-family: 'Segoe UI'; font-size: 11px; font-weight: bold; color: #475569;")
        hl_layout.addWidget(hl_title)
        
        self.hist_legend_scroll = QScrollArea(self.hist_legend_card)
        self.hist_legend_scroll.setWidgetResizable(True)
        self.hist_legend_scroll.setFixedHeight(120)
        self.hist_legend_widget = QWidget()
        self.hist_legend_list_layout = QVBoxLayout(self.hist_legend_widget)
        self.hist_legend_list_layout.setContentsMargins(0, 4, 0, 4)
        self.hist_legend_list_layout.setSpacing(4)
        self.hist_legend_scroll.setWidget(self.hist_legend_widget)
        hl_layout.addWidget(self.hist_legend_scroll)
        
        right_col.addWidget(self.hist_legend_card)
        
        self.hc_layout.addLayout(right_col, 5)
        self.history_layout.addWidget(self.history_content)

    def on_tab_changed(self, index):
        if index == 0:
            self.live_timer.start(1000)
            self.update_live_data()
        else:
            self.live_timer.stop()
            self.update_historical_data()

    def update_history_range(self, text):
        self.update_historical_data()

    def update_live_data(self):
        tracker = self.main_app.tracker
        if not tracker.running:
            self.live_placeholder.setVisible(True)
            self.live_content.setVisible(False)
            return
        
        self.live_placeholder.setVisible(False)
        self.live_content.setVisible(True)
        
        # Live stats
        elapsed = tracker.get_elapsed()
        self.lbl_live_total.setText(format_duration_hms(elapsed))
        
        counted = tracker.get_counted_seconds()
        self.lbl_live_focus.setText(format_duration_hms(counted))
        
        hourly = self.main_app.hourly_rate
        earned = (counted / 3600.0) * hourly if hourly > 0 else 0.0
        display_symbol = self.main_app.currency_symbol
        self.lbl_live_earnings.setText(f"{display_symbol}{earned:,.2f}")
        
        current_app = tracker.get_current_app() or "None"
        self.lbl_live_active.setText(current_app)
        
        # Apps donut
        report = build_report_data(tracker, hourly_rate=hourly, currency_symbol=display_symbol)
        apps_breakdown = []
        for app in report.get("apps", []):
            if not app["excluded"]:
                apps_breakdown.append({
                    "name": app["name"],
                    "seconds": app["seconds"],
                    "color": get_tag_color(app["tag"])
                })
        self.live_donut.set_data(apps_breakdown)
        
        # Refresh live legend list
        for i in reversed(range(self.live_legend_list_layout.count())):
            item = self.live_legend_list_layout.itemAt(i)
            if item and item.widget():
                item.widget().setParent(None)
                
        project_breakdown = report.get("project_breakdown", [])
        for pb in project_breakdown:
            row_f = QFrame()
            row_f.setFixedHeight(22)
            row_layout = QHBoxLayout(row_f)
            row_layout.setContentsMargins(4, 0, 4, 0)
            row_layout.setSpacing(6)
            
            swatch = QLabel("■", row_f)
            swatch.setStyleSheet(f"color: {pb['color']}; font-size: 13px;")
            row_layout.addWidget(swatch)
            
            lbl = QLabel(pb["project"], row_f)
            lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 11px; font-weight: bold; color: #1A1A1A;")
            row_layout.addWidget(lbl)
            
            pct_lbl = QLabel(f"{pb['percent']:.1f}%", row_f)
            pct_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 11px; color: #64748B;")
            row_layout.addWidget(pct_lbl)
            
            row_layout.addStretch()
            
            time_lbl = QLabel(pb["formatted"], row_f)
            time_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 11px; font-weight: 500; color: #1A1A1A;")
            row_layout.addWidget(time_lbl)
            
            self.live_legend_list_layout.addWidget(row_f)
        self.live_legend_list_layout.addStretch()

    def update_historical_data(self):
        range_text = self.period_combo.currentText()
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        if range_text == "Today":
            start_d = today
            end_d = datetime.now()
        elif range_text == "Last 7 Days":
            start_d = today - timedelta(days=6)
            end_d = datetime.now()
        else:  # "This Month"
            start_d = today.replace(day=1)
            end_d = datetime.now()
            
        hourly = self.main_app.hourly_rate
        curr_sym = self.main_app.currency_symbol
        
        data = aggregate_history_data(start_d, end_d, hourly_rate=hourly, currency_symbol=curr_sym)
        
        # Fill historical KPI Cards
        self.lbl_hist_sessions.setText(str(data["session_count"]))
        self.lbl_hist_total.setText(data["total_formatted"])
        self.lbl_hist_focus.setText(data["counted_formatted"])
        self.lbl_hist_earnings.setText(data["total_earned_display"])
        
        # App breakdown donut
        apps_breakdown = []
        for app in data.get("apps", []):
            if not app["excluded"]:
                apps_breakdown.append({
                    "name": app["name"],
                    "seconds": app["seconds"],
                    "color": get_tag_color(app["tag"])
                })
        self.hist_donut.set_data(apps_breakdown)
        
        # Productivity bar trend
        self.hist_bar.set_data(data.get("daily_trend", []))
        
        # Refresh historical legend list
        for i in reversed(range(self.hist_legend_list_layout.count())):
            item = self.hist_legend_list_layout.itemAt(i)
            if item and item.widget():
                item.widget().setParent(None)
                
        project_breakdown = data.get("project_breakdown", [])
        for pb in project_breakdown:
            row_f = QFrame()
            row_f.setFixedHeight(22)
            row_layout = QHBoxLayout(row_f)
            row_layout.setContentsMargins(4, 0, 4, 0)
            row_layout.setSpacing(6)
            
            swatch = QLabel("■", row_f)
            swatch.setStyleSheet(f"color: {pb['color']}; font-size: 13px;")
            row_layout.addWidget(swatch)
            
            lbl = QLabel(pb["project"], row_f)
            lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 11px; font-weight: bold; color: #1A1A1A;")
            row_layout.addWidget(lbl)
            
            pct_lbl = QLabel(f"{pb['percent']:.1f}%", row_f)
            pct_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 11px; color: #64748B;")
            row_layout.addWidget(pct_lbl)
            
            row_layout.addStretch()
            
            time_lbl = QLabel(pb["formatted"], row_f)
            time_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 11px; font-weight: 500; color: #1A1A1A;")
            row_layout.addWidget(time_lbl)
            
            self.hist_legend_list_layout.addWidget(row_f)
        self.hist_legend_list_layout.addStretch()

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
    
    # Single instance lock using QLockFile to prevent multiple running instances
    from PyQt6.QtCore import QLockFile
    lock_file_path = os.path.join(get_app_data_dir(), "focuslog.lock")
    lock_file = QLockFile(lock_file_path)
    
    if not lock_file.tryLock(100):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("FocusLog Already Running")
        msg.setText("Another instance of FocusLog is already running.\nOnly one instance of FocusLog can be active at a time.")
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        
        # Load style on message box to match app theme
        msg.setStyle(app.style())
        msg.setStyleSheet(QSS_STYLE.replace("CHECKMARK_PATH", checkmark_path))
        msg_font = msg.font()
        msg_font.setFamily(FONT_FAMILY)
        msg_font.setPointSize(10)
        msg.setFont(msg_font)
        
        msg.exec()
        sys.exit(1)
        
    focus_app = FocusLogApp()
    focus_app.run()
    
    # Keep reference to lock_file during execution and unlock upon exiting
    exit_code = app.exec()
    lock_file.unlock()
    sys.exit(exit_code)
