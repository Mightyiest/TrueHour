"""
TrueHour — Main Application UI (PyQt6).
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
import traceback

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QCheckBox, QComboBox, QLineEdit,
    QDialog, QMenu, QMessageBox, QFileDialog, QSizePolicy, QInputDialog,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt, QTimer, QSize, QObject, pyqtSignal, QRectF, QPointF, QRect, QPoint
from PyQt6.QtGui import QColor, QPainter, QBrush, QPen, QImage, QPixmap, QIcon, QPainterPath, QPalette

from tracker import AppTracker, AUTO_EXCLUDE_FILE, create_auto_excluded_if_missing
from appinfo import get_icon_image, OVERRIDES_FILE
from config import get_app_data_dir, open_file
from secure_time import get_detector
from report import (
    format_duration, format_duration_hms, build_report_data,
    export_txt, export_json, export_csv, export_csv_history,
    save_to_autosave, save_to_history, load_session_json,
    aggregate_history_data, generate_session_report_html,
)
from version import VERSION_SHORT, VERSION_FULL, INFO
from assets import RENAME_SVG, TRASH_SVG, RESTORE_SVG, GITHUB_SVG, EDIT_SVG, SUN_SVG, MOON_SVG

# Global Constants & Paths
ICON_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(ICON_DIR, "icon.ico")
APP_SETTINGS_FILE = os.path.join(get_app_data_dir(), "app_settings.json")

def pil_to_pixmap(pil_img):
    """Convert a PIL Image safely to a QPixmap for PyQt6 icon rendering using QImage.fromData (independent memory)."""
    if not pil_img:
        return None
    try:
        byte_arr = io.BytesIO()
        pil_img.save(byte_arr, format='PNG')
        png_bytes = byte_arr.getvalue()
        qim = QImage.fromData(png_bytes)
        return QPixmap.fromImage(qim)
    except Exception as e:
        logger.debug(f"pil_to_pixmap failed: {e}")
        return None

import base64
import hashlib

def _get_secure_key(seed: str) -> str:
    if not seed:
        return "default_key_seed"
    machine_id = os.environ.get("COMPUTERNAME", "") or os.environ.get("HOSTNAME", "default_host")
    combined = f"{seed}:{machine_id}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()

def _encrypt_string(plain_text: str, key: str) -> str:
    if not plain_text:
        return ""
    key_len = len(key)
    xor_bytes = bytearray(ord(c) ^ ord(key[i % key_len]) for i, c in enumerate(plain_text))
    return base64.b64encode(xor_bytes).decode("utf-8")

def _decrypt_string(cipher_text: str, key: str) -> str:
    if not cipher_text:
        return ""
    try:
        raw_bytes = base64.b64decode(cipher_text)
        key_len = len(key)
        plain_bytes = bytearray(b ^ ord(key[i % key_len]) for i, b in enumerate(raw_bytes))
        return plain_bytes.decode("utf-8")
    except Exception:
        return ""

_ICON_PROVIDER = None

def get_native_icon_pixmap(exe_path: str, size: int = 16):
    """Retrieve the native system icon for a file path using a shared QFileIconProvider."""
    global _ICON_PROVIDER
    if not exe_path or not os.path.exists(exe_path):
        return None
    try:
        from PyQt6.QtWidgets import QFileIconProvider
        from PyQt6.QtCore import QFileInfo, QSize
        if _ICON_PROVIDER is None:
            _ICON_PROVIDER = QFileIconProvider()
        file_info = QFileInfo(exe_path)
        icon = _ICON_PROVIDER.icon(file_info)
        if icon and not icon.isNull():
            return icon.pixmap(QSize(size, size))
    except Exception as e:
        logger.debug(f"Failed to get native icon for {exe_path}: {e}")
    return None


from debug_terminal import LogBufferCollector, DebugTerminalWindow
from PyQt6.QtGui import QKeySequence, QShortcut
from widgets.custom_widgets import (
    QRThumbnailWidget, EmailChipWidget, FlowLayout,
    InvoicePrivacyOptionsDialog, SegmentedAllocationBar, AppUsageRow
)
from widgets.loading_dialog import LoadingDialog
from workers.report_worker import ReportWorker
from theme import (
    BG_WHITE, BG_SURFACE, BG_HOVER, BG_CARD, ACCENT, ACCENT_HOVER, ACCENT_LIGHT,
    GREEN_STATUS, RED_STATUS, ORANGE, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_DISABLED,
    BORDER, FONT_FAMILY, PROJECT_COLORS, get_tag_color, get_light_palette,
    ensure_checkmark_icon, get_svg_icon, create_minimalist_icon, get_qss_style, get_dark_palette
)

# Start stdout/stderr log redirection immediately to catch early events
log_collector = LogBufferCollector()
log_collector.start_redirection()

# Configure logging for the app module
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    # Stream (console) output handler
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(stream_handler)
    
    # File logging handler (saved to App Data Directory)
    try:
        log_file_path = os.path.join(get_app_data_dir(), "truehour.log")
        file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        logger.addHandler(file_handler)
        logger.info(f"[TrueHour] File logging initialized at: {log_file_path}")
    except Exception as log_err:
        logger.warning(f"Failed to initialize file logging: {log_err}")

# Uncaught exception hook to capture all application crashes to the log file
def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.critical("Uncaught application crash occurred:", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = handle_exception

# ── Force Windows to use Light Mode ──────────────────────────────────
def _force_light_mode():
    try:
        # 0=Default, 1=AllowDark, 2=ForceDark, 3=ForceLight
        ctypes.windll.uxtheme.SetPreferredAppMode(3)
        ctypes.windll.uxtheme.FlushMenuThemes()
    except Exception:
        pass

_force_light_mode()


# ── Thread-Safe Signals ──────────────────────────────────────────────
class TrackerSignals(QObject):
    update_signal = pyqtSignal()
    icon_loaded_signal = pyqtSignal(str, str, object)  # exe_path, app_name, PIL Image (or None)

# create_minimalist_icon moved to theme.py

class HeaderBar(QFrame):
    def __init__(self, parent, cmd_report, cmd_sessions, cmd_settings, cmd_toggle_theme):
        super().__init__(parent)
        self.setObjectName("HeaderBar")
        self.setFixedHeight(44)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(8)
        
        # Theme toggle switcher (top-left)
        self.theme_btn = QPushButton("", self)
        self.theme_btn.setObjectName("ThemeToggleBtn")
        self.theme_btn.setFixedSize(28, 28)
        self.theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_btn.clicked.connect(cmd_toggle_theme)
        layout.addWidget(self.theme_btn)
        
        layout.addStretch()
        
        self.live_report_btn = QPushButton("Dashboard", self)
        self.live_report_btn.setIconSize(QSize(16, 16))
        self.live_report_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.live_report_btn.clicked.connect(cmd_report)
        layout.addWidget(self.live_report_btn)
        
        self.sessions_btn = QPushButton("", self)
        self.sessions_btn.setIconSize(QSize(16, 16))
        self.sessions_btn.setToolTip("Session Manager")
        self.sessions_btn.setFixedSize(28, 28)
        self.sessions_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sessions_btn.clicked.connect(cmd_sessions)
        layout.addWidget(self.sessions_btn)
        
        self.settings_btn = QPushButton("", self)
        self.settings_btn.setIconSize(QSize(16, 16))
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.setFixedSize(28, 28)
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.clicked.connect(cmd_settings)
        layout.addWidget(self.settings_btn)
        
        # Initial light theme icons
        self.update_theme(is_dark=False)

    def update_theme(self, is_dark):
        accent_color = "#38BDF8" if is_dark else "#0078D4"
        neutral_color = "#9CA3AF" if is_dark else "#475569"
        
        if is_dark:
            self.theme_btn.setIcon(get_svg_icon(SUN_SVG, QSize(16, 16), color_hex="#38BDF8"))
            self.theme_btn.setToolTip("Switch to Light Mode")
        else:
            self.theme_btn.setIcon(get_svg_icon(MOON_SVG, QSize(16, 16), color_hex="#475569"))
            self.theme_btn.setToolTip("Switch to Dark Mode")
            
        self.live_report_btn.setIcon(create_minimalist_icon("chart", accent_color))
        self.sessions_btn.setIcon(create_minimalist_icon("folder", neutral_color))
        self.settings_btn.setIcon(create_minimalist_icon("settings", neutral_color))
        
        self.live_report_btn.setStyleSheet(f"""
            QPushButton {{
                color: {accent_color};
                font-size: 12px;
                font-weight: bold;
                font-family: 'Segoe UI';
                background: none;
                border: none;
            }}
            QPushButton:hover {{
                text-decoration: underline;
            }}
        """)

# Custom paint bar and app list usage row widgets moved to widgets/custom_widgets.py

# ── Unified Styled Window Palette (QSS) ──────────────────────────────
# QSS_STYLE moved to theme.py

# ── Main Application Window ──────────────────────────────────────────
class TrueHourApp(QMainWindow):
    def __init__(self):
        super().__init__()
        # Initialize SQLite database (lightweight schema creation)
        try:
            from database.schema import init_db
            init_db()
        except Exception as e:
            print(f"[TrueHour] Failed database bootstrap: {e}")
        
        self.tracker = AppTracker(poll_interval=1.0, min_track_seconds=2)
        self._load_app_settings()
        self._init_posthog()
        self._track_event("app_started", {"version": VERSION_FULL, "platform": sys.platform})

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

        self.setWindowTitle("TrueHour")
        self._center_window(self, 440, 520)
        self.setMinimumSize(440, 500)
        
        if os.path.exists(ICON_PATH):
            try:
                self.setWindowIcon(QIcon(ICON_PATH))
            except Exception:
                pass

        # Standalone debug console is launched as an independent process on demand.

        self._build_ui()

        # Keyboard shortcut for toggling debug console (Ctrl+`)
        self.shortcut_debug = QShortcut(QKeySequence("Ctrl+`"), self)
        self.shortcut_debug.activated.connect(self._toggle_debug_console)
        
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._tick_clock)

        # Link tracker callback
        self.tracker.on_update = lambda: self.signals.update_signal.emit()
        
        # Apply initially loaded theme (light or dark)
        self.apply_theme(self.dark_mode)
        
        from tracker import ACTIVE_SESSION_FILE
        if os.path.exists(ACTIVE_SESSION_FILE):
            QTimer.singleShot(100, self._handle_interrupted_session)
        
        # Postpone heavy database aggregation until after UI is fully responsive
        try:
            from core.reporting.aggregator import rebuild_all_summaries
            QTimer.singleShot(2500, rebuild_all_summaries)
        except Exception as e:
            print(f"[TrueHour] Failed to schedule summary rebuild: {e}")

    def _toggle_debug_console(self):
        import subprocess
        import sys
        logger.info("[Action] Toggled Debug Console")
        try:
            if getattr(sys, 'frozen', False):
                subprocess.Popen([sys.executable, "--debug-console"])
            else:
                subprocess.Popen([sys.executable, sys.argv[0], "--debug-console"])
        except Exception as e:
            logger.error(f"Failed to launch standalone debug console: {e}")

    def _update_developer_ui(self):
        self.debug_btn.setVisible(self.developer_mode)
        self.test_btn.setVisible(self.developer_mode)

    def _on_version_clicked(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
            
        if not hasattr(self, "_version_clicks"):
            self._version_clicks = 0
            
        self._version_clicks += 1
        
        if self.developer_mode:
            return
            
        remaining = 7 - self._version_clicks
        if remaining > 0 and remaining <= 4:
            self.active_label.setText(f"🛠️ You are now {remaining} steps away from being a developer.")
            self.active_label.setStyleSheet("color: #CA5010; font-size: 10px;")
            # Safely restore state label after 2.5 seconds
            QTimer.singleShot(2500, lambda: self.active_label.setText(
                f"Active: {self.tracker.get_current_app()}" if (self.tracker.running and not self.tracker.paused) else ("Ready to track" if not self.tracker.running else "⏸ Session paused")
            ))
        elif remaining == 0:
            self.developer_mode = True
            self._save_app_settings()
            self._update_developer_ui()
            
            QMessageBox.information(
                self, 
                "Developer Options", 
                "Congratulations! You have enabled Developer Options.\nThe Debug Console and Test Logs button are now visible."
            )
            self.active_label.setText("🛠️ Developer Options enabled!")
            self.active_label.setStyleSheet("color: #0F7B0F; font-size: 10px;")

    def _trigger_diagnostic_logs(self):
        logger.debug("[DEBUG] This is a diagnostic debug message to test console colorizing.")
        logger.info("[INFO] This is a diagnostic info message to test console colorizing.")
        logger.warning("[WARNING] This is a diagnostic warning message to test console colorizing.")
        logger.error("[ERROR] This is a diagnostic error message to test console colorizing.")
        print("[STDOUT] Direct standard print triggered for verification.")

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
            cmd_settings=self._show_settings,
            cmd_toggle_theme=self._toggle_theme
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
        
        footer_layout.addStretch()
        
        self.total_label = QLabel("0h 00m 00s", self)
        self.total_label.setStyleSheet("font-family: 'Segoe UI'; font-size: 14px; font-weight: bold; color: #0078D4;")
        footer_layout.addWidget(self.total_label, alignment=Qt.AlignmentFlag.AlignRight)
        body_layout.addWidget(self.footer_card)

        # ── Version & Debug Bar ──────────────────────────────────────
        bottom_bar_layout = QHBoxLayout()
        bottom_bar_layout.setContentsMargins(4, 0, 4, 0)
        bottom_bar_layout.setSpacing(10)
        
        self.debug_btn = QPushButton("🐞 Debug Console", self)
        self.debug_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.debug_btn.setStyleSheet("""
            QPushButton {
                color: #ABABAB;
                font-size: 9px;
                font-family: 'Segoe UI';
                background: none;
                border: none;
                padding: 0px;
            }
            QPushButton:hover {
                color: #0078D4;
                text-decoration: underline;
            }
        """)
        self.debug_btn.clicked.connect(self._toggle_debug_console)
        bottom_bar_layout.addWidget(self.debug_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        
        self.test_btn = QPushButton("⚡ Test Logs", self)
        self.test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.test_btn.setStyleSheet("""
            QPushButton {
                color: #ABABAB;
                font-size: 9px;
                font-family: 'Segoe UI';
                background: none;
                border: none;
                padding: 0px;
            }
            QPushButton:hover {
                color: #F59E0B;
                text-decoration: underline;
            }
        """)
        self.test_btn.clicked.connect(self._trigger_diagnostic_logs)
        bottom_bar_layout.addWidget(self.test_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        
        bottom_bar_layout.addStretch()
        
        ver_lbl = QLabel(VERSION_FULL, self)
        ver_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 9px; color: #ABABAB;")
        ver_lbl.mousePressEvent = self._on_version_clicked
        bottom_bar_layout.addWidget(ver_lbl, alignment=Qt.AlignmentFlag.AlignRight)
        
        body_layout.addLayout(bottom_bar_layout)

        main_layout.addWidget(body_widget)
        self._update_developer_ui()

    def closeEvent(self, event):
        if self.confirm_on_close:
            msg = "A tracking session is active.\nAre you sure you want to stop tracking and exit?" if self.tracker.running else "Are you sure you want to close TrueHour?"
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
                print(f"[TrueHour] Closing autosave failed: {e}")
        
        # Clean up async icon loading resources
        self._icon_cache.clear()
        self._icon_load_queue.clear()
        
        # Safely shut down streams to avoid C++ object deleted crashes
        try:
            log_collector.stop_redirection()
        except Exception:
            pass
            
        event.accept()

    def _on_start(self):
        logger.info("[Action] Clicked Start Tracking")
        auto_name = datetime.now().strftime("Session - %I:%M %p")
        self.tracker.start(session_name=auto_name) 
        self._track_event("tracking_started", {"session_name": auto_name})
        
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
        logger.info("[Action] Clicked Stop Tracking")
        self.clock_timer.stop()
        
        # Update UI immediately — instant visual feedback before any blocking work
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.active_label.setText("Session ended")
        self.clock_label.setText("00:00:00")
        self.earnings_label.setText("")
        self.setWindowTitle("TrueHour")

        # Initialize background worker (offloading tracker stop to background thread to prevent UI freeze)
        worker = ReportWorker(
            self.tracker, 
            hourly_rate=self.hourly_rate, 
            currency_symbol=self.currency_symbol, 
            stop_tracker=True,
            parent=self
        )
        
        # Show Loading Feedback Dialog instantly, which automatically executes and handles the worker!
        self._load_dlg = LoadingDialog("Compiling Report & Saving...", parent=self, is_dark=self.dark_mode, worker=worker)
        if self._load_dlg.exec() == QDialog.DialogCode.Accepted:
            self._show_report(self._load_dlg.compiled_report, is_new=True)
            try:
                rep = self._load_dlg.compiled_report
                self._track_event("tracking_stopped", {
                    "duration_seconds": rep.get("total_seconds", 0),
                    "app_count": len(rep.get("items", [])),
                    "amount_due": rep.get("total_amount_due", "")
                })
            except Exception:
                pass
        else:
            if hasattr(self._load_dlg, "error_message") and self._load_dlg.error_message:
                QMessageBox.critical(self, "Generation Error", f"Failed to generate report:\n{self._load_dlg.error_message}")

    def _on_pause(self):
        is_paused = self.tracker.toggle_pause()
        logger.info(f"[Action] Clicked {'Pause' if is_paused else 'Resume'}")
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
        logger.info("[Action] Opened Live Dashboard")
        if not self.tracker.running:
            QMessageBox.information(self, "No Active Session", "Start tracking first to view a live report.")
            return
            
        worker = ReportWorker(
            self.tracker, 
            hourly_rate=self.hourly_rate, 
            currency_symbol=self.currency_symbol, 
            parent=self
        )
        
        self._load_dlg = LoadingDialog("Compiling Live Data...", parent=self, is_dark=self.dark_mode, worker=worker)
        if self._load_dlg.exec() == QDialog.DialogCode.Accepted:
            self._show_report(self._load_dlg.compiled_report, is_new=False, is_live=True)
        else:
            if hasattr(self._load_dlg, "error_message") and self._load_dlg.error_message:
                QMessageBox.critical(self, "Generation Error", f"Failed to generate report:\n{self._load_dlg.error_message}")

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
        self.setWindowTitle(f"TrueHour | {name}" if name else "TrueHour")

    def _schedule_refresh(self):
        # The background thread emits `update_signal`, which wakes this up in the main GUI thread!
        # Rate limit UI updates to max 2 Hz for better performance
        now = time.time()
        if now - getattr(self, '_last_refresh_time', 0) < 0.5:
            return
        self._last_refresh_time = now
        self._refresh_app_list()

    def _refresh_app_list(self):
        try:
            apps = self.tracker.get_app_times_sorted()
            # Use a coarser hash (10-second buckets) to reduce UI rebuilds
            # Include tag in hash to detect category changes
            app_state_key = tuple(
                (name, included, int(secs) // 10, self.tracker.get_app_tag(name))
                for name, secs, included in apps
            )

            # Skip full rebuild if nothing meaningful changed
            if app_state_key == self._last_app_state_hash and not self._showing_placeholder:
                # Fast path: update times only for visible rows
                for app_name, secs, included in apps:
                    if app_name in self._row_widgets:
                        self._row_widgets[app_name].update_time(secs)
                counted = self.tracker.get_counted_seconds()
                self.total_label.setText(format_duration(counted))
                return

            self._last_app_state_hash = app_state_key
            
            if not apps:
                if self._showing_placeholder:
                    return
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
            # Build a map of expected widget order
            new_widgets = {}
            
            # First pass: update existing widgets and track which ones to keep
            for app_name, secs, included in apps:
                active_apps.add(app_name)
                
                exe_path = self.tracker.get_exe_path(app_name)
                tag = self.tracker.get_app_tag(app_name)
                
                if app_name in self._row_widgets:
                    row = self._row_widgets[app_name]
                    row.update_time(secs)
                    row.update_tag(tag)
                    if exe_path and not row.exe_path:
                        row.exe_path = exe_path
                    new_widgets[app_name] = row
                    
                    # Synchronous robust native system icon loading
                    if exe_path:
                        if exe_path in self._icon_cache:
                            if not getattr(row, '_icon_loaded', False):
                                row.set_icon(self._icon_cache[exe_path])
                                row._icon_loaded = True
                        else:
                            pixmap = get_native_icon_pixmap(exe_path, size=16)
                            self._icon_cache[exe_path] = pixmap
                            row.set_icon(pixmap)
                            row._icon_loaded = True
            
            # Second pass: create new widgets for apps that don't have widgets yet
            for app_name, secs, included in apps:
                if app_name not in new_widgets:
                    exe_path = self.tracker.get_exe_path(app_name)
                    tag = self.tracker.get_app_tag(app_name)
                    
                    row = AppUsageRow(
                        app_name, secs, included, tag, exe_path,
                        on_toggle=self._toggle_include,
                        on_tag_click=self._show_tag_menu,
                        parent=self.scroll_widget
                    )
                    
                    # Insert in vertical list
                    self.scroll_layout.addWidget(row)
                    new_widgets[app_name] = row
                    
                    # Synchronous robust native system icon loading
                    if exe_path:
                        if exe_path in self._icon_cache:
                            if not getattr(row, '_icon_loaded', False):
                                row.set_icon(self._icon_cache[exe_path])
                                row._icon_loaded = True
                        else:
                            pixmap = get_native_icon_pixmap(exe_path, size=16)
                            self._icon_cache[exe_path] = pixmap
                            row.set_icon(pixmap)
                            row._icon_loaded = True

            # Third pass: clean up removed apps
            to_remove = [name for name in self._row_widgets if name not in active_apps]
            for name in to_remove:
                self._row_widgets[name].setParent(None)
                del self._row_widgets[name]
            
            # Update the widget dictionary to reflect new order
            self._row_widgets = new_widgets
            
            # Add stretch at the end to push content to top
            self.scroll_layout.addStretch()
                
            counted = self.tracker.get_counted_seconds()
            self.total_label.setText(format_duration(counted))

        except Exception as e:
            logger.debug(f"Exception during app list refresh: {e}")

    def _clear_list_layout(self):
        """Clear all widgets from the scroll layout while preserving the bottom stretch."""
        # First, find and remove the stretch if it exists
        for i in reversed(range(self.scroll_layout.count())):
            item = self.scroll_layout.itemAt(i)
            if item and item.widget():
                item.widget().setParent(None)
            elif item and item.spacerItem():
                # Remove stretch items
                self.scroll_layout.removeItem(item)

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
            row = self._row_widgets[app_name]
            row.set_icon(self._icon_cache.get(exe_path))
            row._icon_loaded = True

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
        logger.info(f"[Action] Categorized app '{app_name}' as '{tag}'")
        self.tracker.set_app_tag(app_name, tag)
        self._last_app_state_hash = None
        self._refresh_app_list()

    def _show_session_manager(self):
        logger.info("[Action] Opened Session Manager")
        from dialogs.session_manager import SessionManagerDialog
        
        current_settings = {
            "confirm_on_close": self.confirm_on_close,
            "min_track_seconds": self.min_track_seconds,
            "auto_save_seconds": self.auto_save_seconds,
            "currency_symbol": self.currency_symbol,
            "hourly_rate": self.hourly_rate,
            "idle_threshold_seconds_total": self.idle_threshold_seconds_total,
            "business_name": self.business_name,
            "business_emails": self.business_emails,
            "business_phone": self.business_phone,
            "business_address": self.business_address,
            "business_payment": self.business_payment,
            "bank_holder": self.bank_holder,
            "bank_account": self.bank_account,
            "bank_routing": self.bank_routing,
            "bank_swift": self.bank_swift,
            "bank_name": self.bank_name,
            "bank_address": self.bank_address,
            "client_name": self.client_name,
            "client_emails": self.client_emails,
            "client_address": self.client_address,
            "business_logo_path": self.business_logo_path,
            "qr_code_paths": self.qr_code_paths,
            "qr_code_links": self.qr_code_links,
            "mask_business_emails": self.mask_business_emails,
            "mask_business_phone": self.mask_business_phone,
            "mask_client_emails": self.mask_client_emails,
            "enable_bank_details": self.enable_bank_details,
            "developer_mode": self.developer_mode,
            "dark_mode": self.dark_mode,
        }
        
        dialog = SessionManagerDialog(current_settings, self.tracker, self)
        dialog.setModal(True)
        
        # Connect signals
        dialog.resume_requested.connect(self._resume_session)
        dialog.view_report_requested.connect(lambda rep: self._show_report(rep, is_new=False))
        dialog.export_csv_history_requested.connect(self._export_csv_history)
        
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
                self._on_stop()
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
            
            # Defer the heavy app list rebuild to the next event loop tick
            # so the UI paints the resumed state instantly without freezing
            session_name = self.tracker.session_name
            QTimer.singleShot(0, self._refresh_app_list)
            QTimer.singleShot(50, lambda: QMessageBox.information(self, "Session Resumed", f"Resumed session: {session_name}\nTracking is now active."))
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
            "TrueHour detected an interrupted tracking session. Would you like to recover it?",
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
                    
                    # Defer heavy app list rebuild to next event loop tick
                    QTimer.singleShot(0, self._refresh_app_list)
                    QTimer.singleShot(50, lambda: QMessageBox.information(self, "Recovered", "Previous session recovered successfully."))
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
        self.bank_holder = ""
        self.bank_account = ""
        self.bank_routing = ""
        self.bank_swift = ""
        self.bank_name = ""
        self.bank_address = ""
        self.enable_bank_details = True
        self.client_name = ""
        self.client_emails = []     # NEW: list of client contact emails
        self.client_address = ""
        self.business_logo_path = ""
        self.qr_code_paths = []     # NEW: list of payment QR code filenames
        self.qr_code_links = {}     # NEW: mapping of QR code filenames to hyperlink URLs
        self.mask_business_emails = False
        self.mask_business_phone = False
        self.mask_client_emails = False
        self.mask_sensitive_data = False  # LEGACY: default mask toggle for invoices
        self.developer_mode = False
        self.dark_mode = False
        self.anonymous_user_id = ""
        
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
                    
                    self.anonymous_user_id = data.get("anonymous_user_id", "")
                    sec_key = _get_secure_key(self.anonymous_user_id)
                    self.enable_bank_details = data.get("enable_bank_details", True)
                    
                    if "bank_holder_enc" in data:
                        self.bank_holder = _decrypt_string(data.get("bank_holder_enc", ""), sec_key)
                        self.bank_account = _decrypt_string(data.get("bank_account_enc", ""), sec_key)
                        self.bank_routing = _decrypt_string(data.get("bank_routing_enc", ""), sec_key)
                        self.bank_swift = _decrypt_string(data.get("bank_swift_enc", ""), sec_key)
                        self.bank_name = _decrypt_string(data.get("bank_name_enc", ""), sec_key)
                        self.bank_address = _decrypt_string(data.get("bank_address_enc", ""), sec_key)
                    else:
                        self.bank_holder = data.get("bank_holder", "")
                        self.bank_account = data.get("bank_account", "")
                        self.bank_routing = data.get("bank_routing", "")
                        self.bank_swift = data.get("bank_swift", "")
                        self.bank_name = data.get("bank_name", "")
                        self.bank_address = data.get("bank_address", "")
                        
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
                    self.qr_code_links = data.get("qr_code_links", {})
                    legacy_mask = data.get("mask_sensitive_data", False)
                    self.mask_business_emails = data.get("mask_business_emails", legacy_mask)
                    self.mask_business_phone = data.get("mask_business_phone", legacy_mask)
                    self.mask_client_emails = data.get("mask_client_emails", legacy_mask)
                    self.mask_sensitive_data = legacy_mask
                    self.developer_mode = data.get("developer_mode", False)
                    self.dark_mode = data.get("dark_mode", False)
                    self.anonymous_user_id = data.get("anonymous_user_id", "")
            except Exception as e:
                print(f"[TrueHour] Failed to load app settings: {e}")
                
        if not self.anonymous_user_id:
            import uuid
            self.anonymous_user_id = str(uuid.uuid4())
            self._save_app_settings()

    def _save_app_settings(self):
        try:
            dirpath = os.path.dirname(APP_SETTINGS_FILE)
            if dirpath:
                os.makedirs(dirpath, exist_ok=True)
            sec_key = _get_secure_key(self.anonymous_user_id)
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
                
                "enable_bank_details": self.enable_bank_details,
                "bank_holder": "",
                "bank_account": "",
                "bank_routing": "",
                "bank_swift": "",
                "bank_name": "",
                "bank_address": "",
                
                "bank_holder_enc": _encrypt_string(self.bank_holder, sec_key),
                "bank_account_enc": _encrypt_string(self.bank_account, sec_key),
                "bank_routing_enc": _encrypt_string(self.bank_routing, sec_key),
                "bank_swift_enc": _encrypt_string(self.bank_swift, sec_key),
                "bank_name_enc": _encrypt_string(self.bank_name, sec_key),
                "bank_address_enc": _encrypt_string(self.bank_address, sec_key),
                
                "client_name": self.client_name,
                "client_emails": self.client_emails,
                "client_address": self.client_address,
                "business_logo_path": self.business_logo_path,
                "qr_code_paths": self.qr_code_paths,
                "qr_code_links": self.qr_code_links,
                "mask_business_emails": self.mask_business_emails,
                "mask_business_phone": self.mask_business_phone,
                "mask_client_emails": self.mask_client_emails,
                "mask_sensitive_data": self.mask_business_emails or self.mask_business_phone or self.mask_client_emails,
                "developer_mode": self.developer_mode,
                "dark_mode": self.dark_mode,
                "anonymous_user_id": self.anonymous_user_id,
            }
            with open(APP_SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"[TrueHour] Failed to save app settings: {e}")
            
    def _init_posthog(self):
        self.posthog_client = None
        self.posthog_enabled = False
        api_key = os.getenv("POSTHOG_API_KEY")
        host = os.getenv("POSTHOG_HOST", "https://us.i.posthog.com")
        
        if api_key:
            api_key = api_key.strip("'\"")
        if host:
            host = host.strip("'\"")
            
        # Fallback to embedded credentials if running as a prebuilt release (frozen bundle)
        # and no specific API key was configured locally in .env.
        is_frozen = getattr(sys, 'frozen', False)
        if not api_key and is_frozen:
            api_key = "phc_nNUNKAHMsXobKfZbD7pJ9X2dM88A5895nyhbJvyWDCHV"
            host = "https://us.i.posthog.com"
            
        if api_key and api_key != "your_posthog_project_api_key_here":
            try:
                from posthog import Posthog
                self.posthog_client = Posthog(api_key, host=host)
                self.posthog_enabled = True
                logger.info("[PostHog] Initialized successfully.")
            except Exception as e:
                logger.warning(f"[PostHog] Failed to import/initialize posthog: {e}")

    def _track_event(self, event_name, properties=None):
        if not self.posthog_enabled or not self.posthog_client or not self.anonymous_user_id:
            return
        try:
            self.posthog_client.capture(
                distinct_id=self.anonymous_user_id,
                event=event_name,
                properties=properties or {}
            )
            self.posthog_client.flush()
        except Exception as e:
            logger.debug(f"[PostHog] Failed to capture event '{event_name}': {e}")

    def apply_theme(self, is_dark):
        self.dark_mode = is_dark
        
        # Set stylesheet and system palette of the main application!
        app = QApplication.instance()
        if app:
            checkmark_path = ensure_checkmark_icon()
            qss = get_qss_style(is_dark).replace("CHECKMARK_PATH", checkmark_path)
            app.setStyleSheet(qss)
            app.setPalette(get_dark_palette() if is_dark else get_light_palette())
            
        # Update header bar button styles and icons!
        if hasattr(self, 'header'):
            self.header.update_theme(is_dark)
            
        # Update clock label colors to fit the theme
        if hasattr(self, 'clock_label'):
            if is_dark:
                self.clock_label.setStyleSheet("font-family: 'Segoe UI'; font-size: 36px; font-weight: bold; color: #F3F4F6;")
            else:
                self.clock_label.setStyleSheet("font-family: 'Segoe UI'; font-size: 36px; font-weight: bold; color: #0F172A;")
                
        # Trigger dynamic QSS style changes on custom list row widgets
        self._refresh_app_list()

    def _toggle_theme(self):
        new_mode = not self.dark_mode
        self.apply_theme(new_mode)
        self._save_app_settings()

    def _show_settings(self):
        logger.info("[Action] Opened Settings")
        from dialogs.settings_dialog import SettingsDialog
        
        # Prepare the current settings dictionary
        current_settings = {
            "confirm_on_close": self.confirm_on_close,
            "min_track_seconds": self.min_track_seconds,
            "auto_save_seconds": self.auto_save_seconds,
            "currency_symbol": self.currency_symbol,
            "hourly_rate": self.hourly_rate,
            "idle_threshold_seconds_total": self.idle_threshold_seconds_total,
            "business_name": self.business_name,
            "business_emails": self.business_emails,
            "business_phone": self.business_phone,
            "business_address": self.business_address,
            "business_payment": self.business_payment,
            "bank_holder": self.bank_holder,
            "bank_account": self.bank_account,
            "bank_routing": self.bank_routing,
            "bank_swift": self.bank_swift,
            "bank_name": self.bank_name,
            "bank_address": self.bank_address,
            "client_name": self.client_name,
            "client_emails": self.client_emails,
            "client_address": self.client_address,
            "business_logo_path": self.business_logo_path,
            "qr_code_paths": self.qr_code_paths,
            "qr_code_links": self.qr_code_links,
            "mask_business_emails": self.mask_business_emails,
            "mask_business_phone": self.mask_business_phone,
            "mask_client_emails": self.mask_client_emails,
            "enable_bank_details": self.enable_bank_details,
            "developer_mode": self.developer_mode,
            "dark_mode": self.dark_mode,
        }
        
        dialog = SettingsDialog(current_settings, self)
        
        # Connect signals
        dialog.manage_categories_requested.connect(self._show_categories_dialog)
        dialog.about_requested.connect(self._show_about_dialog)
        dialog.theme_toggled.connect(self.apply_theme)
        
        def handle_reload():
            from tracker import reload_auto_excluded
            lock = self.tracker._lock if self.tracker.running else None
            success = reload_auto_excluded(lock=lock)
            dialog.set_reload_status(success)
            
        dialog.reload_exclusions_requested.connect(handle_reload)
        
        def handle_settings_saved(new_settings):
            logger.info("[Action] Applied & Saved Settings")
            self.confirm_on_close = new_settings["confirm_on_close"]
            self.min_track_seconds = new_settings["min_track_seconds"]
            self.auto_save_seconds = new_settings["auto_save_seconds"]
            self.currency_symbol = new_settings["currency_symbol"]
            self.hourly_rate = new_settings["hourly_rate"]
            self.idle_threshold_seconds_total = new_settings["idle_threshold_seconds_total"]
            
            self.tracker.min_track_seconds = self.min_track_seconds
            self.tracker.save_interval = self.auto_save_seconds
            self.tracker.idle_threshold_seconds = self.idle_threshold_seconds_total
            
            self.business_name = new_settings["business_name"]
            self.business_emails = new_settings["business_emails"]
            self.business_email = ", ".join(self.business_emails)
            self.business_phone = new_settings["business_phone"]
            self.business_address = new_settings["business_address"]
            self.business_payment = new_settings["business_payment"]
            self.enable_bank_details = new_settings.get("enable_bank_details", True)
            self.bank_holder = new_settings["bank_holder"]
            self.bank_account = new_settings["bank_account"]
            self.bank_routing = new_settings["bank_routing"]
            self.bank_swift = new_settings["bank_swift"]
            self.bank_name = new_settings["bank_name"]
            self.bank_address = new_settings["bank_address"]
            self.client_name = new_settings["client_name"]
            self.client_emails = new_settings["client_emails"]
            self.client_address = new_settings["client_address"]
            self.business_logo_path = new_settings["business_logo_path"]
            self.qr_code_paths = new_settings["qr_code_paths"]
            self.qr_code_links = new_settings["qr_code_links"]
            
            self.mask_business_emails = new_settings["mask_business_emails"]
            self.mask_business_phone = new_settings["mask_business_phone"]
            self.mask_client_emails = new_settings["mask_client_emails"]
            self.mask_sensitive_data = (
                self.mask_business_emails or
                self.mask_business_phone or
                self.mask_client_emails
            )
            self.developer_mode = new_settings["developer_mode"]
            self.dark_mode = new_settings["dark_mode"]
            self.apply_theme(self.dark_mode)
            self._update_developer_ui()
            self._save_app_settings()
            
            # Update live indicators
            if self.tracker.running and self.hourly_rate > 0:
                counted = self.tracker.get_counted_seconds()
                earned = (counted / 3600) * self.hourly_rate
                state_text = " (paused)" if self.tracker.paused else ""
                self.earnings_label.setText(f"💰 {self.currency_symbol}{earned:,.2f} earned{state_text}")
                
        # Handle settings rejection/cancel to restore original theme
        def handle_rejected():
            self.apply_theme(self.dark_mode)
            
        dialog.rejected.connect(handle_rejected)
        dialog.settings_saved.connect(handle_settings_saved)
        dialog.exec()


    def _show_about_dialog(self):
        import webbrowser
        dialog = QDialog(self)
        dialog.setWindowTitle("About TrueHour")
        self._center_window(dialog, 360, 310)
        dialog.setModal(True)
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        # Title & Icon/Label
        title = QLabel("TrueHour", dialog)
        title.setStyleSheet("font-family: 'Segoe UI'; font-size: 22px; font-weight: bold; color: #0F172A;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # Subtitle or description
        desc = QLabel("Automated Time Tracker & Productivity Assistant", dialog)
        desc.setStyleSheet("font-family: 'Segoe UI'; font-size: 11px; color: #64748B; font-weight: 500;")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc)
        
        # Divider line
        divider = QFrame(dialog)
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        divider.setStyleSheet("background-color: #E2E8F0; min-height: 1px; max-height: 1px; border: none;")
        layout.addWidget(divider)
        
        # Version & Build details
        details_layout = QVBoxLayout()
        details_layout.setSpacing(4)
        
        ver_lbl = QLabel(f"Version: {INFO.version}", dialog)
        ver_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 12px; color: #0F172A;")
        ver_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        details_layout.addWidget(ver_lbl)
        
        build_lbl = QLabel(f"Build: {INFO.build_number} ({INFO.build_date})", dialog)
        build_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 12px; color: #64748B;")
        build_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        details_layout.addWidget(build_lbl)
        
        layout.addLayout(details_layout)
        
        # GitHub SVG button & Legal Row
        links_row = QHBoxLayout()
        links_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        links_row.setSpacing(12)
        
        def get_svg_icon(svg_content, size=QSize(20, 20)):
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
                painter.setPen(QPen(QColor("#0078D4"), 2))
                painter.drawEllipse(2, 2, 16, 16)
            painter.end()
            return QIcon(pixmap)
            
        github_btn = QPushButton(dialog)
        github_btn.setIcon(get_svg_icon(GITHUB_SVG, QSize(20, 20)))
        github_btn.setIconSize(QSize(20, 20))
        github_btn.setToolTip("Visit TrueHour on GitHub")
        github_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        github_btn.setFixedSize(32, 32)
        github_btn.setStyleSheet("""
            QPushButton {
                background-color: #F8FAFC;
                border: 1px solid #E2E8F0;
                border-radius: 16px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #F1F5F9;
                border-color: #CBD5E1;
            }
        """)
        github_btn.clicked.connect(lambda: webbrowser.open("https://mightyiest.github.io/TrueHour/"))
        links_row.addWidget(github_btn)
        
        legal_btn = QPushButton("Terms && Notices", dialog)
        legal_btn.setObjectName("NormalButton")
        legal_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        legal_btn.setFixedHeight(32)
        legal_btn.setStyleSheet("""
            QPushButton {
                padding: 0px 14px;
                font-size: 11px;
                font-weight: 600;
                border-radius: 16px;
            }
        """)
        
        def open_legal():
            legal_path = os.path.join(ICON_DIR, "templates", "about_legal.html")
            webbrowser.open(f"file:///{legal_path.replace('\\', '/')}")
            
        legal_btn.clicked.connect(open_legal)
        links_row.addWidget(legal_btn)
        
        layout.addLayout(links_row)
        
        # Spacer
        layout.addSpacing(6)
        
        # Close Button
        close_btn = QPushButton("Close", dialog)
        close_btn.setObjectName("AccentButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFixedHeight(32)
        close_btn.setStyleSheet("""
            QPushButton {
                border-radius: 16px;
                font-size: 12px;
            }
        """)
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        
        dialog.exec()

    def _show_categories_dialog(self):
        logger.info("[Action] Opened Categories Manager")
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
                row_layout.addWidget(dot, alignment=Qt.AlignmentFlag.AlignVCenter)
                
                lbl = QLabel(proj, row)
                lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 13px; color: #1A1A1A;")
                row_layout.addWidget(lbl, 1, alignment=Qt.AlignmentFlag.AlignVCenter)
                
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
        logger.info(f"[Action] Displaying session report (is_new={is_new}, is_live={is_live})")
        dialog = QDialog(self)
        dialog.setWindowTitle("TrueHour — Live Report" if is_live else "TrueHour — Session Report")
        self._center_window(dialog, 720, 680)
        dialog.setMinimumSize(600, 500)
        
        # Apply stylesheet and palette on start
        from theme import get_qss_style, get_dark_palette, get_light_palette, ensure_checkmark_icon
        qss = get_qss_style(self.dark_mode).replace("CHECKMARK_PATH", ensure_checkmark_icon())
        dialog.setStyleSheet(qss)
        dialog.setPalette(get_dark_palette() if self.dark_mode else get_light_palette())
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Dynamic color tokens
        bg_widget = "#161D30" if self.dark_mode else "#FFFFFF"
        border_color = "#24304F" if self.dark_mode else "#E0E0E0"
        border_f3 = "#24304F" if self.dark_mode else "#F3F3F3"
        text_primary = "#F3F4F6" if self.dark_mode else "#1A1A1A"
        text_sec = "#9CA3AF" if self.dark_mode else "#616161"
        accent_lbl_color = "#38BDF8" if self.dark_mode else "#0078D4"
        
        # Header bar
        hdr = QFrame(dialog)
        hdr.setFixedHeight(44)
        hdr.setStyleSheet(f"QFrame {{ background-color: {bg_widget}; border-bottom: 1px solid {border_color}; }}")
        hdr_layout = QHBoxLayout(hdr)
        hdr_layout.setContentsMargins(14, 0, 14, 0)
        
        title_lbl = QLabel("📊 Live Report (Preview)" if is_live else "📊 Session Report", hdr)
        title_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 15px; font-weight: bold; color: {text_primary}; border: none;")
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
        name_bar.setStyleSheet(f"QFrame {{ background-color: {bg_widget}; border-bottom: 1px solid {border_f3}; }}")
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
        date_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 12px; color: {text_sec};")
        c1_layout.addWidget(date_lbl)
        
        total_lbl = QLabel(f"Total session:  {report['total_formatted']}", card1)
        total_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 13px; color: {text_primary};")
        c1_layout.addWidget(total_lbl)
        
        counted_lbl = QLabel(f"Counted work:  {report['counted_formatted']}", card1)
        counted_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 14px; font-weight: bold; color: {accent_lbl_color};")
        c1_layout.addWidget(counted_lbl)
        
        if report.get("total_earned", 0) > 0:
            earned_f = QFrame(card1)
            earned_f.setStyleSheet(f"QFrame {{ background-color: {'#1F2937' if self.dark_mode else '#E8F1FB'}; border-radius: 4px; }}")
            ef_layout = QHBoxLayout(earned_f)
            ef_layout.setContentsMargins(10, 6, 10, 6)
            
            lbl_title = QLabel("💰 Total Earned: ", earned_f)
            lbl_title.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 12px; color: {text_sec};")
            ef_layout.addWidget(lbl_title)
            
            lbl_val = QLabel(report["total_earned_display"], earned_f)
            lbl_val.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 18px; font-weight: bold; color: {'#4ADE80' if self.dark_mode else '#0F7B0F'};")
            ef_layout.addWidget(lbl_val)
            
            lbl_rate = QLabel(f"@ {report['currency_symbol']}{report['hourly_rate']:.2f}/hr", earned_f)
            lbl_rate.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 11px; color: {text_sec};")
            ef_layout.addWidget(lbl_rate)
            
            ef_layout.addStretch()
            c1_layout.addWidget(earned_f)
            
        scroll_layout.addWidget(card1)

        # Card 2: Allocation horizontal custom paint bar
        project_breakdown = report.get("project_breakdown", [])
        if project_breakdown:
            title_p = QLabel("Project & Category Allocation", scroll_widget)
            title_p.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 13px; font-weight: bold; color: {text_sec};")
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
                lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 12px; font-weight: bold; color: {text_primary};")
                row_layout.addWidget(lbl)
                
                pct_lbl = QLabel(f"{pb['percent']:.1f}%", row_f)
                pct_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 12px; color: {text_sec};")
                row_layout.addWidget(pct_lbl)
                
                row_layout.addStretch()
                
                if pb.get("earned_display"):
                    earned_lbl = QLabel(f"({pb['earned_display']})", row_f)
                    earned_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 12px; font-weight: bold; color: {'#4ADE80' if self.dark_mode else '#0F7B0F'};")
                    row_layout.addWidget(earned_lbl)
                    
                time_lbl = QLabel(pb["formatted"], row_f)
                time_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 12px; color: {text_primary};")
                row_layout.addWidget(time_lbl)
                
                ac_layout.addWidget(row_f)
                
            scroll_layout.addWidget(alloc_card)

        # Card 3: App Breakdown list table
        apps_data = report.get("apps", [])
        if apps_data:
            title_b = QLabel("App Breakdown", scroll_widget)
            title_b.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 13px; font-weight: bold; color: {text_sec};")
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
                st_color = ("#4ADE80" if self.dark_mode else "#0F7B0F") if not app["excluded"] else ("#F87171" if self.dark_mode else "#C42B1C")
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
            title_t.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 13px; font-weight: bold; color: {text_sec};")
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
        footer_f.setStyleSheet(f"QFrame {{ background-color: {bg_widget}; border-top: 1px solid {border_color}; }}")
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
        
        html_btn = QPushButton("View in Browser", footer_f)
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
                    logger.info(f"[Action] Saving session to history with name: '{new_name}'")
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
        logger.info(f"[Action] Commencing report export to format: '{fmt}'")
        if fmt == "txt": 
            path, _ = QFileDialog.getSaveFileName(self, "Export TXT", f"truehour_{report['date']}.txt", "Text files (*.txt)")
            if not path: 
                return
            try:
                export_txt(report, path)
                QMessageBox.information(self, "Exported", f"Report saved to:\n{path}")
            except Exception as e:
                logger.error(f"Failed to export TXT report: {e}")
                QMessageBox.critical(self, "Error", f"Failed to export TXT report:\n{str(e)}")
        else: 
            try:
                html_content = generate_session_report_html(report, hourly_rate=self.hourly_rate, currency_symbol=self.currency_symbol)
                import tempfile
                with tempfile.NamedTemporaryFile('w', delete=False, suffix='.html', encoding='utf-8') as f:
                    f.write(html_content)
                    temp_path = f.name
                
                try:
                    open_file(temp_path)
                except Exception as e:
                    logger.error(f"Failed to open temp report in browser: {e}")
                    QMessageBox.warning(self, "Failed to Open", f"Could not automatically open the report in your browser:\n{str(e)}")
            except Exception as e:
                logger.error(f"Failed to generate HTML report: {e}")
                QMessageBox.critical(self, "Error", f"Failed to generate HTML report:\n{str(e)}")

    def _export_csv_history(self):
        logger.info("[Action] Commencing CSV history export")
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
            
        default_name = f"TrueHour_Export_{datetime.now().strftime('%Y-%m-%d')}.csv"
        filepath, _ = QFileDialog.getSaveFileName(self, "Export History CSV", default_name, "CSV files (*.csv);;All files (*.*)")
        if not filepath: 
            return
        if export_csv_history(reports, filepath, hourly_rate=self.hourly_rate, currency_symbol=self.currency_symbol):
            QMessageBox.information(self, "Success", f"Exported {len(reports)} sessions to:\n{filepath}")
        else: 
            QMessageBox.critical(self, "Error", "Failed to export CSV.")

    def _show_dashboard(self):
        from dialogs.dashboard_dialog import TrueHourDashboard
        dialog = TrueHourDashboard(self)
        dialog.exec()

    def run(self):
        self.show()

# TrueHourDashboard removed - now imported from dialogs.dashboard_dialog



if __name__ == "__main__":
    # Load environment variables from .env file
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception as e:
        print(f"[TrueHour] Failed to load .env: {e}")
    # Install global exception hook to catch unhandled Python exceptions
    def exception_hook(exctype, value, tb):
        """Global hook to intercept catastrophic failures and redirect them into logs."""
        error_msg = "".join(traceback.format_exception(exctype, value, tb))
        logger.critical(f"Catastrophic Application Crash Intercepted:\n{error_msg}")
        sys.__excepthook__(exctype, value, tb)
    
    sys.excepthook = exception_hook
    
    app = QApplication(sys.argv)
    
    # Force style and palette to avoid theme bleeding on systems set to Dark Mode
    app.setStyle("Fusion")
    app.setPalette(get_light_palette())
    
    checkmark_path = ensure_checkmark_icon()
    
    # Check for standalone Debug Console argument first to bypass single instance lock
    if "--debug-console" in sys.argv:
        app.setStyleSheet(get_qss_style(False).replace("CHECKMARK_PATH", checkmark_path))
        from debug_terminal import DebugTerminalWindow
        window = DebugTerminalWindow()
        window.show()
        sys.exit(app.exec())
        
    app.setStyleSheet(get_qss_style(False).replace("CHECKMARK_PATH", checkmark_path))
    
    # Set default fonts globally
    font = app.font()
    font.setFamily(FONT_FAMILY)
    font.setPointSize(10)
    app.setFont(font)
    
    # Single instance lock using QLockFile to prevent multiple running instances
    from PyQt6.QtCore import QLockFile
    lock_file_path = os.path.join(get_app_data_dir(), "truehour.lock")
    lock_file = QLockFile(lock_file_path)
    
    if not lock_file.tryLock(100):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("TrueHour Already Running")
        msg.setText("Another instance of TrueHour is already running.\nOnly one instance of TrueHour can be active at a time.")
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        
        # Load style on message box to match app theme
        msg.setStyle(app.style())
        msg.setStyleSheet(get_qss_style(False).replace("CHECKMARK_PATH", checkmark_path))
        msg_font = msg.font()
        msg_font.setFamily(FONT_FAMILY)
        msg_font.setPointSize(10)
        msg.setFont(msg_font)
        
        msg.exec()
        sys.exit(1)
        
    focus_app = TrueHourApp()
    focus_app.run()
    
    # Keep reference to lock_file during execution and unlock upon exiting
    exit_code = app.exec()
    lock_file.unlock()
    sys.exit(exit_code)
