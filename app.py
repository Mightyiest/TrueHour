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
from assets import RENAME_SVG, TRASH_SVG, RESTORE_SVG, GITHUB_SVG, EDIT_SVG

# Global Constants & Paths
ICON_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(ICON_DIR, "icon.ico")
APP_SETTINGS_FILE = os.path.join(get_app_data_dir(), "app_settings.json")

def pil_to_pixmap(pil_img):
    """Convert a PIL Image safely to a QPixmap for PyQt6 icon rendering."""
    if not pil_img:
        return None
    try:
        im = pil_img.convert("RGBA")
        data = im.tobytes("raw", "RGBA")
        qim = QImage(data, im.size[0], im.size[1], QImage.Format.Format_RGBA8888)
        return QPixmap.fromImage(qim)
    except Exception as e:
        logger.debug(f"pil_to_pixmap failed: {e}")
        return None

from debug_terminal import LogBufferCollector, DebugTerminalWindow
from PyQt6.QtGui import QKeySequence, QShortcut
from widgets.custom_widgets import (
    QRThumbnailWidget, EmailChipWidget, FlowLayout,
    InvoicePrivacyOptionsDialog, SegmentedAllocationBar, AppUsageRow
)
from theme import (
    BG_WHITE, BG_SURFACE, BG_HOVER, BG_CARD, ACCENT, ACCENT_HOVER, ACCENT_LIGHT,
    GREEN_STATUS, RED_STATUS, ORANGE, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_DISABLED,
    BORDER, FONT_FAMILY, PROJECT_COLORS, get_tag_color, get_light_palette,
    ensure_checkmark_icon, get_svg_icon, create_minimalist_icon, QSS_STYLE
)

# Start stdout/stderr log redirection immediately to catch early events
log_collector = LogBufferCollector()
log_collector.start_redirection()

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


# ── Thread-Safe Signals ──────────────────────────────────────────────
class TrackerSignals(QObject):
    update_signal = pyqtSignal()
    icon_loaded_signal = pyqtSignal(str, str, object)  # exe_path, app_name, PIL Image (or None)

# create_minimalist_icon moved to theme.py

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

# Custom paint bar and app list usage row widgets moved to widgets/custom_widgets.py

# ── Unified Styled Window Palette (QSS) ──────────────────────────────
# QSS_STYLE moved to theme.py

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

        # Standalone debug console is launched as an independent process on demand.

        self._build_ui()

        # Keyboard shortcut for toggling debug console (Ctrl+`)
        self.shortcut_debug = QShortcut(QKeySequence("Ctrl+`"), self)
        self.shortcut_debug.activated.connect(self._toggle_debug_console)
        
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._tick_clock)

        # Link tracker callback
        self.tracker.on_update = lambda: self.signals.update_signal.emit()
        
        from tracker import ACTIVE_SESSION_FILE
        if os.path.exists(ACTIVE_SESSION_FILE):
            QTimer.singleShot(100, self._handle_interrupted_session)

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
        logger.info(f"[Action] Categorized app '{app_name}' as '{tag}'")
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
            "client_name": self.client_name,
            "client_emails": self.client_emails,
            "client_address": self.client_address,
            "business_logo_path": self.business_logo_path,
            "qr_code_paths": self.qr_code_paths,
            "qr_code_links": self.qr_code_links,
            "mask_business_emails": self.mask_business_emails,
            "mask_business_phone": self.mask_business_phone,
            "mask_client_emails": self.mask_client_emails,
            "developer_mode": self.developer_mode,
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
        self.qr_code_links = {}     # NEW: mapping of QR code filenames to hyperlink URLs
        self.mask_business_emails = False
        self.mask_business_phone = False
        self.mask_client_emails = False
        self.mask_sensitive_data = False  # LEGACY: default mask toggle for invoices
        self.developer_mode = False
        
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
                    self.qr_code_links = data.get("qr_code_links", {})
                    legacy_mask = data.get("mask_sensitive_data", False)
                    self.mask_business_emails = data.get("mask_business_emails", legacy_mask)
                    self.mask_business_phone = data.get("mask_business_phone", legacy_mask)
                    self.mask_client_emails = data.get("mask_client_emails", legacy_mask)
                    self.mask_sensitive_data = legacy_mask
                    self.developer_mode = data.get("developer_mode", False)
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
                "qr_code_links": self.qr_code_links,
                "mask_business_emails": self.mask_business_emails,
                "mask_business_phone": self.mask_business_phone,
                "mask_client_emails": self.mask_client_emails,
                "mask_sensitive_data": self.mask_business_emails or self.mask_business_phone or self.mask_client_emails,
                "developer_mode": self.developer_mode,
            }
            with open(APP_SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"[FocusLog] Failed to save app settings: {e}")

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
            "client_name": self.client_name,
            "client_emails": self.client_emails,
            "client_address": self.client_address,
            "business_logo_path": self.business_logo_path,
            "qr_code_paths": self.qr_code_paths,
            "qr_code_links": self.qr_code_links,
            "mask_business_emails": self.mask_business_emails,
            "mask_business_phone": self.mask_business_phone,
            "mask_client_emails": self.mask_client_emails,
            "developer_mode": self.developer_mode,
        }
        
        dialog = SettingsDialog(current_settings, self)
        
        # Connect signals
        dialog.manage_categories_requested.connect(self._show_categories_dialog)
        dialog.about_requested.connect(self._show_about_dialog)
        
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
            self._update_developer_ui()
            self._save_app_settings()
            
            # Update live indicators
            if self.tracker.running and self.hourly_rate > 0:
                counted = self.tracker.get_counted_seconds()
                earned = (counted / 3600) * self.hourly_rate
                state_text = " (paused)" if self.tracker.paused else ""
                self.earnings_label.setText(f"💰 {self.currency_symbol}{earned:,.2f} earned{state_text}")
                
        dialog.settings_saved.connect(handle_settings_saved)
        dialog.exec()


    def _show_about_dialog(self):
        import webbrowser
        dialog = QDialog(self)
        dialog.setWindowTitle("About FocusLog")
        self._center_window(dialog, 360, 310)
        dialog.setModal(True)
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        # Title & Icon/Label
        title = QLabel("FocusLog", dialog)
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
        github_btn.setToolTip("Visit FocusLog on GitHub")
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
        github_btn.clicked.connect(lambda: webbrowser.open("https://mightyiest.github.io/FocusLog/"))
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
        logger.info(f"[Action] Displaying session report (is_new={is_new}, is_live={is_live})")
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
                    open_file(path)
                return
            QMessageBox.information(self, "Exported", f"Report saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

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
            
        default_name = f"FocusLog_Export_{datetime.now().strftime('%Y-%m-%d')}.csv"
        filepath, _ = QFileDialog.getSaveFileName(self, "Export History CSV", default_name, "CSV files (*.csv);;All files (*.*)")
        if not filepath: 
            return
        if export_csv_history(reports, filepath, hourly_rate=self.hourly_rate, currency_symbol=self.currency_symbol):
            QMessageBox.information(self, "Success", f"Exported {len(reports)} sessions to:\n{filepath}")
        else: 
            QMessageBox.critical(self, "Error", "Failed to export CSV.")

    def _show_dashboard(self):
        from dialogs.dashboard_dialog import FocusLogDashboard
        dialog = FocusLogDashboard(self)
        dialog.exec()

    def run(self):
        self.show()

# FocusLogDashboard removed - now imported from dialogs.dashboard_dialog



if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Force style and palette to avoid theme bleeding on systems set to Dark Mode
    app.setStyle("Fusion")
    app.setPalette(get_light_palette())
    
    checkmark_path = ensure_checkmark_icon()
    
    # Check for standalone Debug Console argument first to bypass single instance lock
    if "--debug-console" in sys.argv:
        app.setStyleSheet(QSS_STYLE.replace("CHECKMARK_PATH", checkmark_path))
        from debug_terminal import DebugTerminalWindow
        window = DebugTerminalWindow()
        window.show()
        sys.exit(app.exec())
        
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
