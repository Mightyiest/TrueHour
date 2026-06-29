"""
TrueHour — Main Application UI (PyQt6).
Lightweight Windows desktop time tracker with a clean Windows 11-style light theme.
"""
import base64
import hashlib
import io
import json
import logging
import os
import shutil
import sys
import time
import traceback
from datetime import datetime

from PyQt6.QtCore import QFileInfo, QObject, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPixmap, QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QLineEdit, QDialog, QMenu, QMessageBox,
    QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView, QSystemTrayIcon, QFileIconProvider
)

from tracker import AppTracker
from config import get_app_data_dir, open_file, get_app_data_root, DynamicPath
from report import (
    format_duration, format_duration_hms, build_report_data,
    export_txt, save_to_autosave, save_to_history, generate_session_report_html,
)
from version import VERSION_FULL, INFO
from assets import GITHUB_SVG, SUN_SVG, MOON_SVG, SOLID_MOON_SVG, PLAY_SVG, PAUSE_SVG, BUG_SVG, SHIELD_SVG
from debug_terminal import LogBufferCollector, DebugTerminalWindow
from widgets.custom_widgets import SegmentedAllocationBar, AppUsageRow
from widgets.loading_dialog import LoadingDialog
from widgets.update_label import FadingVersionLabel
from workers.report_worker import ReportWorker
from theme import (
    FONT_FAMILY, get_tag_color, get_light_palette,
    ensure_checkmark_icon, get_svg_icon, create_minimalist_icon, get_qss_style, get_dark_palette
)
import ctypes

# Global Constants & Paths
ICON_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(ICON_DIR, "icon.ico")
APP_SETTINGS_FILE = DynamicPath(lambda: os.path.join(get_app_data_dir(), "app_settings.json"))

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
        logger.debug("pil_to_pixmap failed: %s", e)
        return None

from crypto import _get_secure_key, _encrypt_string, _decrypt_string

# ── Crypto Key Bindings (Moved to crypto.py) ──────────────────

_ICON_PROVIDER = None

def get_native_icon_pixmap(exe_path: str, size: int = 16):
    """Retrieve the native system icon for a file path using a shared QFileIconProvider."""
    global _ICON_PROVIDER
    if not exe_path or not os.path.exists(exe_path):
        return None
    try:
        if _ICON_PROVIDER is None:
            _ICON_PROVIDER = QFileIconProvider()
        file_info = QFileInfo(exe_path)
        icon = _ICON_PROVIDER.icon(file_info)
        if icon and not icon.isNull():
            return icon.pixmap(QSize(size, size))
    except Exception as e:
        logger.debug("Failed to get native icon for %s: %s", exe_path, e)
    return None

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

    # File logging handler (saved to App Data Root Directory)
    try:
        log_file_path = os.path.join(get_app_data_root(), "truehour.log")
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
        self.update_theme("light")

    def update_theme(self, theme_style=None, is_dark=None):
        if is_dark is not None:
            theme_style = is_dark
        if theme_style is None:
            theme_style = "light"
        if isinstance(theme_style, bool):
            theme_style = "modern-dark" if theme_style else "light"
        
        is_dark = (theme_style in ["modern-dark", "classic-dark"])
        
        if theme_style == "classic-dark":
            accent_color = "#d1d5db"
            neutral_color = "#aaa"
            self.theme_btn.setIcon(get_svg_icon(SUN_SVG, QSize(16, 16), color_hex="#d1d5db"))
            self.theme_btn.setToolTip("Switch to Light Mode")
        elif theme_style == "modern-dark":
            accent_color = "#2563EB"
            neutral_color = "#A3A3A3"
            self.theme_btn.setIcon(get_svg_icon(SOLID_MOON_SVG, QSize(16, 16), color_hex="#475569"))
            self.theme_btn.setToolTip("Switch to Classic Dark Mode")
        else: # light
            accent_color = "#0078D4"
            neutral_color = "#475569"
            self.theme_btn.setIcon(get_svg_icon(SOLID_MOON_SVG, QSize(16, 16), color_hex="#2563EB"))
            self.theme_btn.setToolTip("Switch to Modern Dark Mode")

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
        self.notified_goals = None
        self.notified_earnings_goal = None
        self._load_app_settings()
        self._init_posthog()
        self._track_event("app_started", {"version": VERSION_FULL, "platform": sys.platform})

        self._check_vars = {}
        self._photo_refs = []
        self._row_widgets = {}
        self._showing_placeholder = True

        # Icon cache and parameters
        self._last_app_state_hash = None
        self._icon_cache = {}
        self._icons_to_load = []
        self._icon_load_timer = QTimer(self)
        self._icon_load_timer.setInterval(30)
        self._icon_load_timer.timeout.connect(self._process_icon_load_queue)

        self.signals = TrackerSignals()
        self.signals.update_signal.connect(self._schedule_refresh)

        self.setWindowTitle("TrueHour")
        self._center_window(self, 440, 520)
        self.setMinimumSize(440, 500)

        if os.path.exists(ICON_PATH):
            try:
                self.setWindowIcon(QIcon(ICON_PATH))
            except Exception:
                pass

        # Initialize System Tray Icon
        self.tray_icon = QSystemTrayIcon(self)
        if os.path.exists(ICON_PATH):
            self.tray_icon.setIcon(QIcon(ICON_PATH))
        else:
            self.tray_icon.setIcon(self.windowIcon())

        self.tray_menu = QMenu()
        show_action = self.tray_menu.addAction("Show/Restore")
        show_action.triggered.connect(self.showNormal)

        self.tray_pause_action = self.tray_menu.addAction("Pause Tracking")
        self.tray_pause_action.triggered.connect(self._on_pause)
        self.tray_pause_action.setEnabled(False)

        self.tray_menu.addSeparator()
        quit_action = self.tray_menu.addAction("Exit")
        quit_action.triggered.connect(self.close)

        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self._on_tray_icon_activated)
        self.tray_icon.show()

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
            import threading
            from core.reporting.aggregator import rebuild_all_summaries
            def run_rebuild():
                try:
                    rebuild_all_summaries()
                except Exception as ex:
                    print(f"[TrueHour] Background summary rebuild failed: {ex}")
            QTimer.singleShot(2500, lambda: threading.Thread(target=run_rebuild, daemon=True).start())
            QTimer.singleShot(3500, self._recalculate_weekly_base_focus_seconds)
        except Exception as e:
            print(f"[TrueHour] Failed to schedule summary rebuild: {e}")

        # Start local web server for Focus Goals dashboard
        try:
            from core.reporting.web_server import WebServerManager
            self.web_server_mgr = WebServerManager(self._get_web_goals_state, self)
            self.web_server_mgr.signals.goals_updated.connect(self._on_web_goals_updated)
            self.web_server_mgr.signals.alerts_toggled.connect(self._on_web_alerts_toggled)
            self.web_server_mgr.signals.theme_toggled.connect(self._on_web_theme_toggled)
            self.web_server_mgr.signals.test_notification_requested.connect(self._trigger_test_notification)
            self.web_server_mgr.signals.reset_requested.connect(self._on_web_goals_reset)
            self.web_server_mgr.start()
        except Exception as e:
            print(f"[TrueHour] Failed to initialize web server: {e}")

        # Schedule database optimization 3 seconds after startup to clean up database file
        try:
            import threading
            from database.schema import optimize_db
            def run_optimize():
                try:
                    optimize_db()
                except Exception as ex:
                    print(f"[TrueHour] Background database optimization failed: {ex}")
            QTimer.singleShot(3000, lambda: threading.Thread(target=run_optimize, daemon=True).start())
        except Exception as e:
            print(f"[TrueHour] Failed to schedule database optimization: {e}")


        # ── Background update check ──────────────────────────────────
        # Runs 5 seconds after startup to avoid blocking the UI.
        from core.update_checker import UpdateCheckSignals, check_for_updates_async
        from version import __version__
        self._update_signals = UpdateCheckSignals()
        self._update_signals.update_found.connect(self._on_update_found)
        QTimer.singleShot(5000, lambda: check_for_updates_async(__version__, self._update_signals))

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

    def _on_update_found(self, new_version: str, release_url: str):
        """Callback from the background update checker when a newer release exists."""
        logger.info(f"[UpdateChecker] Notifying user: {new_version}")
        if hasattr(self, 'ver_lbl'):
            self.ver_lbl.set_update_available(True, new_version=new_version, release_url=release_url)

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
            self.active_label.setStyleSheet("color: #ffffff; font-size: 10px;" if self.dark_mode else "color: #CA5010; font-size: 10px;")
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
            self.active_label.setStyleSheet("color: #ffffff; font-size: 10px;" if self.dark_mode else "color: #0F7B0F; font-size: 10px;")

    def _trigger_diagnostic_logs(self):
        logger.debug("[DEBUG] This is a diagnostic debug message to test console colorizing.")
        logger.info("[INFO] This is a diagnostic info message to test console colorizing.")
        logger.warning("[WARNING] This is a diagnostic warning message to test console colorizing.")
        logger.error("[ERROR] This is a diagnostic error message to test console colorizing.")

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
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
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

        total_lbl = QLabel("Total session time", self)
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

        self.ver_lbl = FadingVersionLabel(VERSION_FULL, self)
        self.ver_lbl.set_version_click_handler(self._on_version_clicked)
        bottom_bar_layout.addWidget(self.ver_lbl, alignment=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.bug_btn = QPushButton(self)
        self.bug_btn.setFixedSize(16, 16)
        self.bug_btn.setIconSize(QSize(12, 12))
        self.bug_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bug_btn.setToolTip("Report a Bug / Feedback")
        self.bug_btn.setStyleSheet("QPushButton { background: none; border: none; padding: 0px; }")
        self.bug_btn.setIcon(get_svg_icon(BUG_SVG, QSize(12, 12)))
        self.bug_btn.clicked.connect(self._show_bug_report_menu)
        bottom_bar_layout.addWidget(self.bug_btn, alignment=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

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

        # Clean up icon loading resources
        self._icon_cache.clear()

        # Safely shut down streams to avoid C++ object deleted crashes
        try:
            log_collector.stop_redirection()
        except Exception:
            pass

        if hasattr(self, "web_server_mgr"):
            self.web_server_mgr.stop()

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
        self.pause_btn.setText(" Pause")
        self._update_pause_btn_ui()
        self.stop_btn.setEnabled(True)

        self.tray_pause_action.setEnabled(True)
        self.tray_pause_action.setText("Pause Tracking")

        # Trigger dynamic QSS style changes
        self.start_btn.setObjectName("AccentButton")
        self.pause_btn.setObjectName("NormalButton")
        self.stop_btn.setObjectName("RedButton")
        self.start_btn.setStyleSheet("")
        self.pause_btn.setStyleSheet("")
        self.stop_btn.setStyleSheet("")

        if self.hourly_rate > 0:
            self.earnings_label.setText(f"💰 {self.currency_symbol}0.00 earned")
            self.earnings_label.setStyleSheet("color: #ffffff; font-size: 13px; font-weight: bold;" if self.dark_mode else "color: #0F7B0F; font-size: 13px; font-weight: bold;")
        self.clock_timer.start(250)

    def _on_stop(self):
        logger.info("[Action] Clicked Stop Tracking")
        self.clock_timer.stop()

        # Update UI immediately — instant visual feedback before any blocking work
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setText(" Pause")
        self.pause_btn.setStyleSheet("")
        is_dark = getattr(self, "dark_mode", False)
        icon_color = "#d1d5db" if is_dark else "#475569"
        self.pause_btn.setIcon(get_svg_icon(PAUSE_SVG, QSize(12, 12), icon_color))
        self.stop_btn.setEnabled(False)
        self.active_label.setText("Session ended")
        self.clock_label.setText("00:00:00")
        self.total_label.setText("0h 00m 00s")
        self.earnings_label.setText("")
        self.setWindowTitle("TrueHour")

        # Clear application usage list immediately
        self._clear_list_layout()
        self._check_vars.clear()
        self._photo_refs.clear()
        self._row_widgets.clear()
        self._last_app_state_hash = None
        self.placeholder_lbl = QLabel("Waiting for app activity...", self)
        self.placeholder_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 13px; color: #ABABAB; margin: 20px;")
        self.scroll_layout.insertWidget(0, self.placeholder_lbl)
        self._showing_placeholder = True

        self.tray_pause_action.setEnabled(False)
        self.tray_pause_action.setText("Pause Tracking")
        self._recalculate_weekly_base_focus_seconds()

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
            self._show_compact_save_dialog(self._load_dlg.compiled_report)
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

    def _update_pause_btn_ui(self):
        if not hasattr(self, 'pause_btn'):
            return
        is_paused = self.tracker.paused
        is_dark = getattr(self, "dark_mode", False)
        icon_color = "#d1d5db" if is_dark else "#475569"
        
        if is_paused:
            icon_color = "#ffffff"
            self.pause_btn.setIcon(get_svg_icon(PLAY_SVG, QSize(12, 12), icon_color))
            self.pause_btn.setText(" Resume")
        else:
            self.pause_btn.setIcon(get_svg_icon(PAUSE_SVG, QSize(12, 12), icon_color))
            self.pause_btn.setText(" Pause")

    def _on_pause(self):
        is_paused = self.tracker.toggle_pause()
        logger.info(f"[Action] Clicked {'Pause' if is_paused else 'Resume'}")
        self.tray_pause_action.setText("Resume Tracking" if is_paused else "Pause Tracking")
        if is_paused:
            if self.dark_mode:
                self.pause_btn.setStyleSheet("color: #ffffff; background-color: #262626; font-weight: bold;")
                self.active_label.setStyleSheet("color: #ffffff; font-size: 10px;")
            else:
                self.pause_btn.setStyleSheet("color: #ffffff; background-color: #1e293b; font-weight: bold;")
                self.active_label.setStyleSheet("color: #CA5010; font-size: 10px;")
            self.active_label.setText("⏸ Session paused")
        else:
            self.pause_btn.setStyleSheet("")
            current = self.tracker.get_current_app()
            self.active_label.setText(f"Active: {current}" if current else " ")
            self.active_label.setStyleSheet("color: #616161; font-size: 10px;")
        self._update_pause_btn_ui()

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
        counted = self.tracker.get_counted_seconds()
        self.clock_label.setText(format_duration_hms(counted))
        self.total_label.setText(format_duration(elapsed))
        if self.hourly_rate > 0:
            counted = self.tracker.get_counted_seconds()
            earned = (counted / 3600) * self.hourly_rate
            display_symbol = self.currency_symbol.split()[0].split('(')[0].strip() if self.currency_symbol else "$"
            if self.tracker.paused:
                self.earnings_label.setText(f"💰 {display_symbol}{earned:,.2f} earned (paused)")
                self.earnings_label.setStyleSheet("color: #616161; font-size: 13px; font-weight: bold;")
            else:
                self.earnings_label.setText(f"💰 {display_symbol}{earned:,.2f} earned")
                self.earnings_label.setStyleSheet("color: #ffffff; font-size: 13px; font-weight: bold;" if self.dark_mode else "color: #0F7B0F; font-size: 13px; font-weight: bold;")
        else:
            self.earnings_label.setText("")

        if not self.tracker.paused:
            current = self.tracker.get_current_app()
            self.active_label.setText(f"Active: {current}" if current else " ")
            self.active_label.setStyleSheet("color: #616161; font-size: 10px;")
        elif getattr(self.tracker, '_idle_paused', False):
            self.active_label.setText("💤 Idle — auto paused")
            self.active_label.setStyleSheet("color: #ffffff; font-size: 10px;" if self.dark_mode else "color: #CA5010; font-size: 10px;")

        name = getattr(self.tracker, "session_name", "")
        self.setWindowTitle(f"TrueHour | {name}" if name else "TrueHour")
        self._check_weekly_goal_milestones()

    def _on_tray_icon_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.DoubleClick, QSystemTrayIcon.ActivationReason.Trigger):
            if self.isVisible():
                self.hide()
            else:
                self.showNormal()
                self.activateWindow()

    def _show_tray_notification(self, title, message):
        if hasattr(self, "tray_icon") and self.tray_icon.isVisible():
            self.tray_icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 5000)

    def _trigger_test_notification(self):
        self._show_tray_notification(
            "TrueHour Goals",
            "This is a test notification from TrueHour! Tray alerts are functioning properly."
        )

    def _recalculate_weekly_base_focus_seconds(self):
        from datetime import datetime, timedelta
        now = datetime.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        period = getattr(self, "earnings_goal_period", "weekly")
        if period == "daily":
            start_date = today
            self.last_week_start_date = today
        else:
            start_of_week = today - timedelta(days=today.weekday())
            start_date = start_of_week
            self.last_week_start_date = start_of_week

        reset_ts_str = getattr(self, "earnings_goal_reset_timestamp", "")
        if reset_ts_str:
            try:
                reset_ts = datetime.fromisoformat(reset_ts_str)
                if reset_ts > start_date:
                    start_date = reset_ts
            except Exception:
                pass

        exclude_key = None
        if self.tracker.running and self.tracker.session_start:
            s_date = self.tracker.session_start.strftime("%Y-%m-%d")
            s_start = self.tracker.session_start.strftime("%H:%M:%S")
            exclude_key = (s_date, s_start)

        try:
            from report import aggregate_history_data
            data = aggregate_history_data(start_date, now, exclude_key=exclude_key)
            self.weekly_base_focus_seconds = {}
            for item in data.get("project_breakdown", []):
                self.weekly_base_focus_seconds[item["project"]] = item["seconds"]
        except Exception as e:
            print(f"[TrueHour] Failed to recalculate base focus seconds: {e}")
            self.weekly_base_focus_seconds = {}
        finally:
            self._goals_initialized = True

    def _check_weekly_goal_milestones(self, force=False):
        if not getattr(self, "enable_goal_tray_alerts", True):
            return

        weekly_goals = getattr(self, "weekly_goals", {})
        weekly_earnings_goal = getattr(self, "weekly_earnings_goal", 0.0)
        if not weekly_goals and weekly_earnings_goal <= 0:
            return

        if not force and not getattr(self, "_goals_initialized", False):
            return

        if not force:
            import time
            now_ts = time.time()
            if now_ts - getattr(self, "_last_goal_check", 0.0) < 30.0:
                return
            self._last_goal_check = now_ts

        from datetime import datetime, timedelta
        now = datetime.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        period = getattr(self, "earnings_goal_period", "weekly")
        if period == "daily":
            expected_start = today
        else:
            expected_start = today - timedelta(days=today.weekday())

        if getattr(self, "last_week_start_date", None) != expected_start:
            self.last_week_start_date = expected_start
            self._recalculate_weekly_base_focus_seconds()
            if self.notified_goals is not None:
                self.notified_goals.clear()
            if self.notified_earnings_goal is not None:
                self.notified_earnings_goal.clear()

        project_seconds = dict(getattr(self, "weekly_base_focus_seconds", {}))

        if self.tracker.running:
            from tracker import _is_auto_excluded
            with self.tracker._lock:
                for app_name, secs in self.tracker.app_times.items():
                    if self.tracker.app_included.get(app_name, True) and not _is_auto_excluded(self.tracker.app_exe_paths.get(app_name, "")):
                        tag = self.tracker.tag_manager.get_tag(app_name, self.tracker.app_exe_paths.get(app_name, ""))
                        project_seconds[tag] = project_seconds.get(tag, 0.0) + secs

        total_seconds = sum(project_seconds.values())
        total_hours = total_seconds / 3600.0
        total_earnings = total_hours * getattr(self, "hourly_rate", 0.0)

        # Check weekly earnings goal milestones
        if weekly_earnings_goal > 0 and getattr(self, "hourly_rate", 0.0) > 0:
            if self.notified_earnings_goal is None:
                self.notified_earnings_goal = set()
                if total_earnings >= weekly_earnings_goal:
                    self.notified_earnings_goal.add(100)
                    self.notified_earnings_goal.add(50)
                elif total_earnings >= 0.5 * weekly_earnings_goal:
                    self.notified_earnings_goal.add(50)
            else:
                curr_sym = getattr(self, "currency_symbol", "$")
                if 50 not in self.notified_earnings_goal and total_earnings >= 0.5 * weekly_earnings_goal:
                    self.notified_earnings_goal.add(50)
                    self._show_tray_notification(
                        "Earnings Goal Milestone",
                        f"Reached 50% of your weekly earnings goal ({curr_sym}{total_earnings:.2f} / {curr_sym}{weekly_earnings_goal:.2f})!"
                    )
                if 100 not in self.notified_earnings_goal and total_earnings >= weekly_earnings_goal:
                    self.notified_earnings_goal.add(100)
                    self._show_tray_notification(
                        "Earnings Goal Completed!",
                        f"Congratulations! Reached 100% of your weekly earnings goal ({curr_sym}{total_earnings:.2f} / {curr_sym}{weekly_earnings_goal:.2f})!"
                    )

        # Check project goals
        if weekly_goals:
            if self.notified_goals is None:
                self.notified_goals = {}
                for proj, goal_hours in weekly_goals.items():
                    if goal_hours <= 0:
                        continue
                    goal_secs = goal_hours * 3600.0
                    curr_secs = project_seconds.get(proj, 0.0)
                    self.notified_goals[proj] = set()
                    if curr_secs >= goal_secs:
                        self.notified_goals[proj].add(100)
                        self.notified_goals[proj].add(50)
                    elif curr_secs >= 0.5 * goal_secs:
                        self.notified_goals[proj].add(50)
            else:
                for proj, goal_hours in weekly_goals.items():
                    if goal_hours <= 0:
                        continue
                    goal_secs = goal_hours * 3600.0
                    curr_secs = project_seconds.get(proj, 0.0)

                    if proj not in self.notified_goals:
                        self.notified_goals[proj] = set()

                    if 50 not in self.notified_goals[proj] and curr_secs >= 0.5 * goal_secs:
                        self.notified_goals[proj].add(50)
                        self._show_tray_notification(
                            "Focus Goal Milestone",
                            f"Reached 50% of your weekly goal for '{proj}' ({curr_secs/3600.0:.1f}h / {goal_hours:.1f}h)!"
                        )

                    if 100 not in self.notified_goals[proj] and curr_secs >= goal_secs:
                        self.notified_goals[proj].add(100)
                        self._show_tray_notification(
                            "Focus Goal Completed!",
                            f"Congratulations! Reached 100% of your weekly goal for '{proj}' ({curr_secs/3600.0:.1f}h / {goal_hours:.1f}h)!"
                        )

    def _get_web_goals_state(self):
        active_seconds = {}
        if self.tracker.running:
            from tracker import _is_auto_excluded
            with self.tracker._lock:
                for app_name, secs in self.tracker.app_times.items():
                    if self.tracker.app_included.get(app_name, True) and not _is_auto_excluded(self.tracker.app_exe_paths.get(app_name, "")):
                        tag = self.tracker.tag_manager.get_tag(app_name, self.tracker.app_exe_paths.get(app_name, ""))
                        active_seconds[tag] = active_seconds.get(tag, 0.0) + secs

        from theme import PROJECT_COLORS
        from config import get_app_data_dir
        import os
        return {
            "weekly_goals": dict(getattr(self, "weekly_goals", {})),
            "enable_goal_tray_alerts": getattr(self, "enable_goal_tray_alerts", True),
            "weekly_base_focus_seconds": dict(getattr(self, "weekly_base_focus_seconds", {})),
            "active_seconds": active_seconds,
            "project_colors": dict(PROJECT_COLORS),
            "dark_mode": getattr(self, "dark_mode", False),
            "weekly_earnings_goal": getattr(self, "weekly_earnings_goal", 0.0),
            "hourly_rate": getattr(self, "hourly_rate", 0.0),
            "currency_symbol": getattr(self, "currency_symbol", "$"),
            "earnings_goal_period": getattr(self, "earnings_goal_period", "weekly"),
            "active_profile": os.path.basename(get_app_data_dir()),
            "earnings_goal_reset_timestamp": getattr(self, "earnings_goal_reset_timestamp", "")
        }

    def _on_web_goals_reset(self):
        logger.info("[Web Server] Goals reset requested")
        tracker_was_running = self.tracker.running
        session_name = getattr(self.tracker, "session_name", "")
        if tracker_was_running:
            self.tracker.stop()
        self.earnings_goal_reset_timestamp = datetime.now().isoformat()
        if self.notified_goals is not None:
            self.notified_goals.clear()
        if self.notified_earnings_goal is not None:
            self.notified_earnings_goal.clear()
        self._recalculate_weekly_base_focus_seconds()
        self._save_app_settings()
        if tracker_was_running:
            self.tracker.start(session_name=session_name)
        for widget in QApplication.topLevelWidgets():
            if widget.inherits("QDialog") and widget.metaObject().className() == "TrueHourDashboard":
                if hasattr(widget, "update_historical_data"):
                    widget.update_historical_data()

    def _on_web_goals_updated(self, goals_data):
        logger.info(f"[Web Server] Weekly goals updated: {goals_data}")
        if "weekly_goals" in goals_data:
            self.weekly_goals = goals_data["weekly_goals"]
            if self.notified_goals is not None:
                self.notified_goals.clear()
        if "weekly_earnings_goal" in goals_data:
            self.weekly_earnings_goal = goals_data["weekly_earnings_goal"]
            if self.notified_earnings_goal is not None:
                self.notified_earnings_goal.clear()
        if "earnings_goal_period" in goals_data:
            self.earnings_goal_period = str(goals_data["earnings_goal_period"])
            if self.notified_earnings_goal is not None:
                self.notified_earnings_goal.clear()
        self._recalculate_weekly_base_focus_seconds()
        self._save_app_settings()

        # Sync with open dashboard dialogs
        for widget in QApplication.topLevelWidgets():
            if widget.inherits("QDialog") and widget.metaObject().className() == "TrueHourDashboard":
                if hasattr(widget, "update_historical_data"):
                    widget.update_historical_data()

    def _on_web_alerts_toggled(self, enabled):
        logger.info(f"[Web Server] Milestone notifications toggled: {enabled}")
        self.enable_goal_tray_alerts = enabled
        self._save_app_settings()

    def _on_web_theme_toggled(self, is_dark):
        logger.info(f"[Web Server] Dark mode toggled: {is_dark}")
        self.apply_theme(is_dark)
        self._save_app_settings()

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
                elapsed = self.tracker.get_elapsed()
                self.clock_label.setText(format_duration_hms(counted))
                self.total_label.setText(format_duration(elapsed))
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

            # Temporarily remove all widgets and spacers from layout to reorder them without destroying
            for i in reversed(range(self.scroll_layout.count())):
                item = self.scroll_layout.itemAt(i)
                if item:
                    if item.widget():
                        self.scroll_layout.removeWidget(item.widget())
                    elif item.spacerItem():
                        self.scroll_layout.removeItem(item)

            active_apps = set()
            new_widgets = {}

            # Single unified pass to update existing or create new widgets and add them in correct sorted order
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
                else:
                    row = AppUsageRow(
                        app_name, secs, included, tag, exe_path,
                        on_toggle=self._toggle_include,
                        on_tag_click=self._show_tag_menu,
                        on_context_menu=self._show_app_context_menu,
                        parent=self.scroll_widget
                    )

                self.scroll_layout.addWidget(row)
                new_widgets[app_name] = row

                # Deferred non-blocking native system icon loading
                if exe_path:
                    if exe_path in self._icon_cache:
                        if not getattr(row, '_icon_loaded', False):
                            row.set_icon(self._icon_cache[exe_path])
                            row._icon_loaded = True
                    else:
                        row.set_icon(None)
                        row._icon_loaded = False
                        if exe_path not in self._icons_to_load:
                            self._icons_to_load.append(exe_path)

            # Clean up removed apps
            to_remove = [name for name in self._row_widgets if name not in active_apps]
            for name in to_remove:
                widget = self._row_widgets[name]
                widget.setParent(None)
                widget.deleteLater()
                del self._row_widgets[name]

            # Update the widget dictionary to reflect new order
            self._row_widgets = new_widgets

            # Add stretch at the end to push content to top
            self.scroll_layout.addStretch()

            if self._icons_to_load and not self._icon_load_timer.isActive():
                self._icon_load_timer.start()

            counted = self.tracker.get_counted_seconds()
            elapsed = self.tracker.get_elapsed()
            self.clock_label.setText(format_duration_hms(counted))
            self.total_label.setText(format_duration(elapsed))
        except Exception as e:
            logger.debug(f"Exception during app list refresh: {e}")

    def _process_icon_load_queue(self):
        if not self._icons_to_load:
            self._icon_load_timer.stop()
            return
        
        exe_path = self._icons_to_load.pop(0)
        try:
            pixmap = get_native_icon_pixmap(exe_path, size=16)
        except Exception:
            pixmap = None
            
        self._icon_cache[exe_path] = pixmap

        # Update the UI rows having this exe_path
        for widget in self._row_widgets.values():
            if getattr(widget, 'exe_path', None) == exe_path:
                widget.set_icon(pixmap)
                widget._icon_loaded = True

    def _clear_list_layout(self):
        """Clear all widgets from the scroll layout while preserving the bottom stretch."""
        # First, find and remove the stretch if it exists
        for i in reversed(range(self.scroll_layout.count())):
            item = self.scroll_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                widget.setParent(None)
                widget.deleteLater()
            elif item and item.spacerItem():
                # Remove stretch items
                self.scroll_layout.removeItem(item)

    def _toggle_include(self, app_name, is_checked):
        self.tracker.set_included(app_name, is_checked)
        self._schedule_refresh()

    def _show_app_context_menu(self, app_name, exe_path, global_pos):
        menu = QMenu(self)
        exe_name = os.path.basename(exe_path).lower() if exe_path else ""
        target = exe_name if exe_name else app_name
        if not target:
            return

        is_distracting = any(d.lower() == target.lower() for d in self.distraction_apps)

        if is_distracting:
            action = menu.addAction("Remove from Distracting Apps")
            action.triggered.connect(lambda: self._remove_distraction_app(target))
        else:
            action = menu.addAction("Mark as Distracting App")
            action.triggered.connect(lambda: self._add_distraction_app(target))

        menu.exec(global_pos)

    def _add_distraction_app(self, target):
        if target and target not in self.distraction_apps:
            logger.info(f"[Action] Added '{target}' to distracting apps")
            self.distraction_apps.append(target)
            self.tracker.distraction_apps = self.distraction_apps
            self._save_app_settings()

    def _remove_distraction_app(self, target):
        self.distraction_apps = [d for d in self.distraction_apps if d.lower() != target.lower()]
        self.tracker.distraction_apps = self.distraction_apps
        self._save_app_settings()
        logger.info(f"[Action] Removed '{target}' from distracting apps")


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
            "enable_business_logo": self.enable_business_logo,
            "qr_code_paths": self.qr_code_paths,
            "qr_code_links": self.qr_code_links,
            "mask_business_emails": self.mask_business_emails,
            "mask_business_phone": self.mask_business_phone,
            "mask_client_emails": self.mask_client_emails,
            "enable_bank_details": self.enable_bank_details,
            "developer_mode": self.developer_mode,
            "dark_mode": self.dark_mode,
            "theme_style": self.theme_style,
        }

        dialog = SessionManagerDialog(current_settings, self.tracker, self)
        dialog.setModal(True)

        # Connect signals
        dialog.resume_requested.connect(self._resume_session)
        
        def _on_view_report_sm(rep):
            self._show_report(rep, is_new=False)
            dialog._refresh_all_lists()
        dialog.view_report_requested.connect(_on_view_report_sm)

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
            self.pause_btn.setText(" Pause")
            self._update_pause_btn_ui()
            self.stop_btn.setEnabled(True)

            # Styles
            self.start_btn.setObjectName("AccentButton")
            self.pause_btn.setObjectName("NormalButton")
            self.stop_btn.setObjectName("RedButton")

            if self.hourly_rate > 0:
                self.earnings_label.setText(f"💰 {self.currency_symbol}0.00 earned")
            self.active_label.setText(f"▶ Resumed: {self.tracker.session_name}")
            self.active_label.setStyleSheet("color: #ffffff; font-size: 10px;" if self.dark_mode else "color: #0F7B0F; font-size: 10px;")

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
                    self._update_pause_btn_ui()
                    self.stop_btn.setEnabled(True)

                    self.start_btn.setObjectName("AccentButton")
                    self.pause_btn.setObjectName("NormalButton")
                    self.stop_btn.setObjectName("RedButton")

                    if self.hourly_rate > 0:
                        self.earnings_label.setText(f"💰 {self.currency_symbol}0.00 earned")
                    self.active_label.setText(f"▶ Recovered: {self.tracker.session_name}")
                    self.active_label.setStyleSheet("color: #ffffff; font-size: 10px;" if self.dark_mode else "color: #0F7B0F; font-size: 10px;")

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
        self.weekly_goals = {}
        self.weekly_earnings_goal = 0.0
        self.earnings_goal_period = "weekly"
        self.enable_goal_tray_alerts = True
        self.enable_distraction_auto_pause = False
        self.distraction_apps = []
        self.weekly_base_focus_seconds = {}
        self.earnings_goal_reset_timestamp = ""
        self._goals_initialized = False
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
        self.enable_business_logo = True
        self.qr_code_paths = []     # NEW: list of payment QR code filenames
        self.qr_code_links = {}     # NEW: mapping of QR code filenames to hyperlink URLs
        self.mask_business_emails = False
        self.mask_business_phone = False
        self.mask_client_emails = False
        self.mask_sensitive_data = False  # LEGACY: default mask toggle for invoices
        self.developer_mode = False
        self.dark_mode = False
        self.theme_style = "light"
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
                    self.enable_distraction_auto_pause = data.get("enable_distraction_auto_pause", False)
                    self.distraction_apps = data.get("distraction_apps", [])
                    self.tracker.enable_distraction_auto_pause = self.enable_distraction_auto_pause
                    self.tracker.distraction_apps = self.distraction_apps

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
                    self.enable_business_logo = data.get("enable_business_logo", True)

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
                    self.theme_style = data.get("theme_style", "modern-dark" if self.dark_mode else "light")
                    self.weekly_goals = data.get("weekly_goals", {})
                    self.weekly_earnings_goal = float(data.get("weekly_earnings_goal", 0.0))
                    self.earnings_goal_period = data.get("earnings_goal_period", "weekly")
                    self.enable_goal_tray_alerts = data.get("enable_goal_tray_alerts", True)
                    self.earnings_goal_reset_timestamp = data.get("earnings_goal_reset_timestamp", "")
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
                "enable_business_logo": self.enable_business_logo,
                "qr_code_paths": self.qr_code_paths,
                "qr_code_links": self.qr_code_links,
                "mask_business_emails": self.mask_business_emails,
                "mask_business_phone": self.mask_business_phone,
                "mask_client_emails": self.mask_client_emails,
                "mask_sensitive_data": self.mask_business_emails or self.mask_business_phone or self.mask_client_emails,
                "developer_mode": self.developer_mode,
                "dark_mode": self.dark_mode,
                "theme_style": self.theme_style,
                "weekly_goals": self.weekly_goals,
                "weekly_earnings_goal": self.weekly_earnings_goal,
                "earnings_goal_period": self.earnings_goal_period,
                "enable_goal_tray_alerts": self.enable_goal_tray_alerts,
                "earnings_goal_reset_timestamp": getattr(self, "earnings_goal_reset_timestamp", ""),
                "anonymous_user_id": self.anonymous_user_id,
                "enable_distraction_auto_pause": self.enable_distraction_auto_pause,
                "distraction_apps": self.distraction_apps,
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

        telemetry_allowed = True
        try:
            # pyrefly: ignore [missing-import]
            import telemetry_config
            telemetry_allowed = getattr(telemetry_config, "TELEMETRY_ENABLED", True)
        except ImportError:
            pass

        if not api_key and is_frozen and telemetry_allowed:
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

    def apply_theme(self, theme_style):
        if isinstance(theme_style, bool):
            theme_style = "modern-dark" if theme_style else "light"
        
        self.theme_style = theme_style
        self.dark_mode = (theme_style in ["modern-dark", "classic-dark"])
        is_dark = self.dark_mode

        # Set stylesheet and system palette of the main application!
        app = QApplication.instance()
        if app:
            checkmark_path = ensure_checkmark_icon(self.theme_style)
            qss = get_qss_style(self.theme_style).replace("CHECKMARK_PATH", checkmark_path)
            app.setStyleSheet(qss)
            app.setPalette(get_dark_palette(self.theme_style) if self.dark_mode else get_light_palette())

        # Update header bar button styles and icons!
        if hasattr(self, 'header'):
            self.header.update_theme(self.theme_style)

        if hasattr(self, '_update_pause_btn_ui'):
            self._update_pause_btn_ui()

        # Update clock label colors to fit the theme
        if hasattr(self, 'clock_label'):
            if is_dark:
                self.clock_label.setStyleSheet("font-family: 'Segoe UI'; font-size: 36px; font-weight: bold; color: #F3F4F6;")
            else:
                self.clock_label.setStyleSheet("font-family: 'Segoe UI'; font-size: 36px; font-weight: bold; color: #0F172A;")

        # Update total label style to fit the theme
        if hasattr(self, 'total_label'):
            if is_dark:
                self.total_label.setStyleSheet("font-family: 'Segoe UI'; font-size: 14px; font-weight: bold; color: #d1d5db;")
            else:
                self.total_label.setStyleSheet("font-family: 'Segoe UI'; font-size: 14px; font-weight: bold; color: #0078D4;")

        # Update debug and test button hover colors to fit the theme
        if hasattr(self, 'debug_btn'):
            debug_hover = "#ffffff" if is_dark else "#0078D4"
            self.debug_btn.setStyleSheet(f"""
                QPushButton {{
                    color: #ABABAB;
                    font-size: 9px;
                    font-family: 'Segoe UI';
                    background: none;
                    border: none;
                    padding: 0px;
                }}
                QPushButton:hover {{
                    color: {debug_hover};
                    text-decoration: underline;
                }}
            """)
        if hasattr(self, 'test_btn'):
            test_hover = "#ffffff" if is_dark else "#F59E0B"
            self.test_btn.setStyleSheet(f"""
                QPushButton {{
                    color: #ABABAB;
                    font-size: 9px;
                    font-family: 'Segoe UI';
                    background: none;
                    border: none;
                    padding: 0px;
                }}
                QPushButton:hover {{
                    color: {test_hover};
                    text-decoration: underline;
                }}
            """)

        # Update version/update label theme
        if hasattr(self, 'ver_lbl'):
            self.ver_lbl.update_theme(is_dark)

        # Trigger dynamic QSS style changes on custom list row widgets
        self._refresh_app_list()

    def _toggle_theme(self):
        if self.theme_style == "light":
            new_style = "modern-dark"
        elif self.theme_style == "modern-dark":
            new_style = "classic-dark"
        else:
            new_style = "light"
        logger.info(f"[Action] Cycling theme to: {new_style}")
        self.apply_theme(new_style)
        self._save_app_settings()

    def _show_bug_report_menu(self):
        import webbrowser
        logger.info("[Action] Opened Bug Report / Feedback Menu")

        msg = QMessageBox(self)
        msg.setWindowTitle("Report a Bug / Feedback")
        msg.setText("Would you like to report a bug or share feedback?")
        msg.setInformativeText("If you have a GitHub account, you can open an issue on our GitHub repository. Otherwise, you can submit our feedback form.")

        github_btn = msg.addButton("Open GitHub Issues", QMessageBox.ButtonRole.AcceptRole)
        form_btn = msg.addButton("Open Feedback Form", QMessageBox.ButtonRole.AcceptRole)
        msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)

        # Apply current stylesheet to the QMessageBox
        msg.setStyleSheet(self.styleSheet())

        msg.exec()

        if msg.clickedButton() == github_btn:
            webbrowser.open("https://github.com/Mightyiest/TrueHour/issues")
        elif msg.clickedButton() == form_btn:
            webbrowser.open("https://forms.gle/798MkSd5Yyps3Uv18")

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
            "enable_business_logo": self.enable_business_logo,
            "qr_code_paths": self.qr_code_paths,
            "qr_code_links": self.qr_code_links,
            "mask_business_emails": self.mask_business_emails,
            "mask_business_phone": self.mask_business_phone,
            "mask_client_emails": self.mask_client_emails,
            "enable_bank_details": self.enable_bank_details,
            "developer_mode": self.developer_mode,
            "dark_mode": self.dark_mode,
            "theme_style": self.theme_style,
            "weekly_goals": self.weekly_goals,
            "weekly_earnings_goal": getattr(self, "weekly_earnings_goal", 0.0),
            "earnings_goal_period": getattr(self, "earnings_goal_period", "weekly"),
            "enable_goal_tray_alerts": self.enable_goal_tray_alerts,
            "enable_distraction_auto_pause": self.enable_distraction_auto_pause,
            "distraction_apps": self.distraction_apps,
        }

        dialog = SettingsDialog(current_settings, self)

        # Connect signals
        dialog.manage_categories_requested.connect(self._show_categories_dialog)
        dialog.about_requested.connect(self._show_about_dialog)
        dialog.theme_toggled.connect(self.apply_theme)
        dialog.profile_changed.connect(self._handle_profile_switched)
        dialog.profile_renamed.connect(self._handle_profile_renamed)
        dialog.profile_deleted.connect(self._handle_profile_deleted)
        dialog.settings_imported.connect(self._handle_settings_imported)
        dialog.test_notification_requested.connect(self._trigger_test_notification)

        def handle_reload():
            from tracker import reload_auto_excluded
            success = reload_auto_excluded()
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
            self.enable_business_logo = new_settings.get("enable_business_logo", True)
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
            self.theme_style = new_settings.get("theme_style", "modern-dark" if self.dark_mode else "light")

            self.weekly_goals = new_settings.get("weekly_goals", {})
            self.weekly_earnings_goal = new_settings.get("weekly_earnings_goal", 0.0)
            self.earnings_goal_period = new_settings.get("earnings_goal_period", "weekly")
            self.enable_goal_tray_alerts = new_settings.get("enable_goal_tray_alerts", True)
            self.enable_distraction_auto_pause = new_settings.get("enable_distraction_auto_pause", False)
            self.distraction_apps = new_settings.get("distraction_apps", [])
            self.tracker.enable_distraction_auto_pause = self.enable_distraction_auto_pause
            self.tracker.distraction_apps = self.distraction_apps
            if self.notified_goals is not None:
                self.notified_goals.clear()
            if self.notified_earnings_goal is not None:
                self.notified_earnings_goal.clear()
            self._recalculate_weekly_base_focus_seconds()

            self.apply_theme(self.theme_style)
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
            self.apply_theme(self.theme_style)

        dialog.rejected.connect(handle_rejected)
        dialog.settings_saved.connect(handle_settings_saved)
        dialog.exec()


    def _show_about_dialog(self):
        import webbrowser
        dialog = QDialog(self)
        dialog.setWindowTitle("About TrueHour")
        self._center_window(dialog, 360, 310)
        dialog.setModal(True)

        # Apply stylesheet and palette on start
        from theme import get_qss_style, get_dark_palette, get_light_palette, ensure_checkmark_icon
        qss = get_qss_style(self.theme_style).replace("CHECKMARK_PATH", ensure_checkmark_icon(self.theme_style))
        dialog.setStyleSheet(qss)
        dialog.setPalette(get_dark_palette(self.theme_style) if self.dark_mode else get_light_palette())

        # Dynamic theme colors based on theme_style
        if self.theme_style == "classic-dark":
            text_primary = "#e0e0e0"
            text_secondary = "#888888"
            border_color = "#333333"
            btn_bg = "#262626"
            btn_border = "#333333"
            btn_hover = "#333333"
            btn_border_hover = "#444444"
        elif self.theme_style == "modern-dark":
            text_primary = "#EDEDED"
            text_secondary = "#A3A3A3"
            border_color = "#232329"
            btn_bg = "#232329"
            btn_border = "#232329"
            btn_hover = "#2a2a32"
            btn_border_hover = "#353542"
        else: # light
            text_primary = "#0F172A"
            text_secondary = "#64748B"
            border_color = "#E2E8F0"
            btn_bg = "#F8FAFC"
            btn_border = "#E2E8F0"
            btn_hover = "#F1F5F9"
            btn_border_hover = "#CBD5E1"

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Title & Icon/Label
        title = QLabel("TrueHour", dialog)
        title.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 22px; font-weight: bold; color: {text_primary};")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Subtitle or description
        desc = QLabel("Automated Time Tracker & Productivity Assistant", dialog)
        desc.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 11px; color: {text_secondary}; font-weight: 500;")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc)

        # Divider line
        divider = QFrame(dialog)
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        divider.setStyleSheet(f"background-color: {border_color}; min-height: 1px; max-height: 1px; border: none;")
        layout.addWidget(divider)

        # Version & Build details
        details_layout = QVBoxLayout()
        details_layout.setSpacing(4)

        ver_lbl = QLabel(f"Version: {INFO.version}", dialog)
        ver_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 12px; color: {text_primary};")
        ver_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        details_layout.addWidget(ver_lbl)

        build_lbl = QLabel(f"Build: {INFO.build_number} ({INFO.build_date})", dialog)
        build_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 12px; color: {text_secondary};")
        build_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        details_layout.addWidget(build_lbl)

        layout.addLayout(details_layout)

        # GitHub SVG button & Legal Row
        links_row = QHBoxLayout()
        links_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        links_row.setSpacing(12)

        github_btn = QPushButton(dialog)
        github_btn.setIcon(get_svg_icon(GITHUB_SVG, QSize(20, 20), color_hex=text_primary))
        github_btn.setIconSize(QSize(20, 20))
        github_btn.setToolTip("Visit TrueHour on GitHub")
        github_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        github_btn.setFixedSize(32, 32)
        github_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {btn_bg};
                border: 1px solid {btn_border};
                border-radius: 16px;
                padding: 5px;
            }}
            QPushButton:hover {{
                background-color: {btn_hover};
                border-color: {btn_border_hover};
            }}
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

        from theme import get_qss_style, get_dark_palette, get_light_palette, ensure_checkmark_icon
        qss = get_qss_style(self.theme_style).replace("CHECKMARK_PATH", ensure_checkmark_icon(self.theme_style))
        dialog.setStyleSheet(qss)
        dialog.setPalette(get_dark_palette(self.theme_style) if self.dark_mode else get_light_palette())

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 12, 14, 12)

        title_color = "#EDEDED" if self.theme_style == "modern-dark" else "#e0e0e0" if self.dark_mode else "#1A1A1A"
        title = QLabel("Manage Categories", dialog)
        title.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 15px; font-weight: bold; color: {title_color};")
        layout.addWidget(title)

        scroll = QScrollArea(dialog)
        scroll.setWidgetResizable(True)
        scroll.setObjectName("AppListCard")
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(4, 4, 4, 4)
        scroll_layout.setSpacing(2)

        def refresh_categories_list():
            while scroll_layout.count():
                item = scroll_layout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.setParent(None)
                    widget.deleteLater()


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
                lbl_color = "#EDEDED" if self.theme_style == "modern-dark" else "#e0e0e0" if self.dark_mode else "#1A1A1A"
                lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 13px; color: {lbl_color};")
                row_layout.addWidget(lbl, 1, alignment=Qt.AlignmentFlag.AlignVCenter)

                if proj != "Unassigned":
                    del_btn = QPushButton("❌", row)
                    del_btn.setFixedSize(20, 20)
                    del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                    del_btn_hover = "#333333" if self.dark_mode else "#E9E9E9"
                    del_btn.setStyleSheet(f"QPushButton {{ background: none; border: none; font-size: 10px; }} QPushButton:hover {{ background-color: {del_btn_hover}; border-radius: 3px; }}")
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
        qss = get_qss_style(self.theme_style).replace("CHECKMARK_PATH", ensure_checkmark_icon(self.theme_style))
        dialog.setStyleSheet(qss)
        dialog.setPalette(get_dark_palette(self.theme_style) if self.dark_mode else get_light_palette())

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Dynamic color tokens based on theme_style
        if self.theme_style == "classic-dark":
            bg_widget = "#1e1e1e"
            border_color = "#333333"
            border_f3 = "#333333"
            text_primary = "#e0e0e0"
            text_sec = "#aaa"
            accent_lbl_color = "#d1d5db"
            card_bg = "#262626"
            earned_fg = "#ffffff"
        elif self.theme_style == "modern-dark":
            bg_widget = "#16161A"
            border_color = "#232329"
            border_f3 = "#232329"
            text_primary = "#EDEDED"
            text_sec = "#A3A3A3"
            accent_lbl_color = "#2563EB"
            card_bg = "#232329"
            earned_fg = "#10B981"
        else: # light
            bg_widget = "#FFFFFF"
            border_color = "#E0E0E0"
            border_f3 = "#F3F3F3"
            text_primary = "#1A1A1A"
            text_sec = "#616161"
            accent_lbl_color = "#0078D4"
            card_bg = "#E8F1FB"
            earned_fg = "#0F7B0F"

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
            earned_f.setStyleSheet(f"QFrame {{ background-color: {card_bg}; border-radius: 4px; }}")
            ef_layout = QHBoxLayout(earned_f)
            ef_layout.setContentsMargins(10, 6, 10, 6)

            lbl_title = QLabel("💰 Total Earned: ", earned_f)
            lbl_title.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 12px; color: {text_sec};")
            ef_layout.addWidget(lbl_title)

            lbl_val = QLabel(report["total_earned_display"], earned_f)
            lbl_val.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 18px; font-weight: bold; color: {earned_fg};")
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
                    earned_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 12px; font-weight: bold; color: {earned_fg};")
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
                st_color = (earned_fg if not app["excluded"] else ("#888888" if self.dark_mode else "#C42B1C"))
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

    def _show_compact_save_dialog(self, report):
        logger.info("[Action] Displaying compact session save dialog")
        dialog = QDialog(self)
        dialog.setWindowTitle("Session Summary Report")
        dialog.setFixedSize(380, 380)

        from theme import get_qss_style, get_dark_palette, get_light_palette, ensure_checkmark_icon
        qss = get_qss_style(self.theme_style).replace("CHECKMARK_PATH", ensure_checkmark_icon(self.theme_style))
        dialog.setStyleSheet(qss)
        dialog.setPalette(get_dark_palette(self.theme_style) if self.dark_mode else get_light_palette())

        # Theme-specific variables
        if self.theme_style == "classic-dark":
            bg_widget = "#1e1e1e"
            border_color = "#333333"
            text_primary = "#e0e0e0"
            text_sec = "#aaa"
            accent_lbl_color = "#d1d5db"
            earned_bg = "#262626"
            earned_fg = "#ffffff"
            accent_btn_bg = "#262626"
            accent_btn_hover = "#383838"
        elif self.theme_style == "modern-dark":
            bg_widget = "#16161A"
            border_color = "#232329"
            text_primary = "#EDEDED"
            text_sec = "#A3A3A3"
            accent_lbl_color = "#2563EB"
            earned_bg = "#232329"
            earned_fg = "#10B981"
            accent_btn_bg = "#2563EB"
            accent_btn_hover = "#3B82F6"
        else: # light
            bg_widget = "#FFFFFF"
            border_color = "#E0E0E0"
            text_primary = "#1A1A1A"
            text_sec = "#616161"
            accent_lbl_color = "#0078D4"
            earned_bg = "#E8F1FB"
            earned_fg = "#0F7B0F"
            accent_btn_bg = "#1e293b"
            accent_btn_hover = "#334155"

        # Layout
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Title
        report_title = QLabel("Session Summary Report", dialog)
        report_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        report_title.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 18px; font-weight: 700; color: {text_primary};")
        layout.addWidget(report_title)

        # Date
        meta_lbl = QLabel(report.get("date_display", datetime.now().strftime("%B %d, %Y")), dialog)
        meta_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        meta_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 11px; color: {text_sec}; margin-top: -6px;")
        layout.addWidget(meta_lbl)

        # Session Name Entry Field
        name_input_layout = QVBoxLayout()
        name_input_layout.setSpacing(4)
        name_lbl = QLabel("Session Name", dialog)
        name_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 11px; font-weight: bold; color: {text_sec};")
        name_input_layout.addWidget(name_lbl)

        report_name_entry = QLineEdit(dialog)
        report_name_entry.setText(report.get("session_name", "").strip() or "Unnamed")
        report_name_entry.setStyleSheet(f"""
            QLineEdit {{
                border: 1px solid {border_color};
                border-radius: 6px;
                padding: 8px 12px;
                background-color: {bg_widget};
                color: {text_primary};
                font-family: 'Segoe UI';
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border-color: {accent_lbl_color};
            }}
        """)
        name_input_layout.addWidget(report_name_entry)
        layout.addLayout(name_input_layout)

        # Stats Cards side-by-side
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(10)

        # Tracked Focus Time Card
        card_time = QFrame(dialog)
        card_time.setStyleSheet(f"QFrame {{ background-color: {earned_bg}; border: 1px solid {border_color}; border-radius: 8px; }}")
        ct_layout = QVBoxLayout(card_time)
        ct_layout.setContentsMargins(12, 12, 12, 12)
        ct_layout.setSpacing(4)

        time_val = QLabel(report.get("counted_formatted", "0s"), card_time)
        time_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        time_val.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 16px; font-weight: 700; color: {text_primary};")
        ct_layout.addWidget(time_val)

        time_lbl = QLabel("Tracked Focus Time", card_time)
        time_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        time_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 10px; color: {text_sec}; font-weight: 500;")
        ct_layout.addWidget(time_lbl)

        stats_layout.addWidget(card_time)

        # Total Earned Card
        card_earned = QFrame(dialog)
        card_earned.setStyleSheet(f"QFrame {{ background-color: {earned_bg}; border: 1px solid {border_color}; border-radius: 8px; }}")
        ce_layout = QVBoxLayout(card_earned)
        ce_layout.setContentsMargins(12, 12, 12, 12)
        ce_layout.setSpacing(4)

        earned_val = QLabel(report.get("total_earned_display", "$0.00"), card_earned)
        earned_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        earned_val.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 16px; font-weight: 700; color: {earned_fg};")
        ce_layout.addWidget(earned_val)

        earned_lbl = QLabel("Total Earned", card_earned)
        earned_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        earned_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 10px; color: {text_sec}; font-weight: 500;")
        ce_layout.addWidget(earned_lbl)

        stats_layout.addWidget(card_earned)
        layout.addLayout(stats_layout)

        # Ledger Badge Style
        if self.theme_style == "modern-dark":
            badge_bg = "rgba(22, 163, 74, 0.1)"
            badge_border = "rgba(22, 163, 74, 0.3)"
            icon_color = "#4ade80"
        elif self.theme_style == "classic-dark":
            badge_bg = "rgba(22, 163, 74, 0.1)"
            badge_border = "rgba(22, 163, 74, 0.3)"
            icon_color = "#4ade80"
        else: # light
            badge_bg = "#f0fdf4"
            badge_border = "#bbf7d0"
            icon_color = "#16a34a"

        badge_frame = QFrame(dialog)
        badge_frame.setObjectName("LedgerBadge")
        badge_frame.setStyleSheet(f"""
            QFrame#LedgerBadge {{
                background-color: {badge_bg};
                border: 1px solid {badge_border};
                border-radius: 6px;
            }}
        """)
        badge_layout = QHBoxLayout(badge_frame)
        badge_layout.setContentsMargins(10, 8, 10, 8)
        badge_layout.setSpacing(6)
        badge_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_lbl = QLabel(badge_frame)
        icon_lbl.setFixedSize(14, 14)
        shield_icon = get_svg_icon(SHIELD_SVG, QSize(14, 14), color_hex=icon_color)
        icon_lbl.setPixmap(shield_icon.pixmap(14, 14))
        icon_lbl.setStyleSheet("border: none; background: transparent;")
        badge_layout.addWidget(icon_lbl)

        text_lbl = QLabel("100% Verified SHA-256 Ledger", badge_frame)
        text_lbl.setStyleSheet(f"""
            QLabel {{
                color: {icon_color};
                font-family: 'Segoe UI';
                font-size: 11.5px;
                font-weight: 600;
                border: none;
                background: transparent;
            }}
        """)
        badge_layout.addWidget(text_lbl)
        
        layout.addWidget(badge_frame)

        # Save Session Button
        primary_btn = QPushButton("Save Session", dialog)
        primary_btn.setFixedHeight(40)
        primary_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        primary_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {accent_btn_bg};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-family: 'Segoe UI';
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {accent_btn_hover};
            }}
        """)
        
        def _save_and_close():
            try:
                new_name = report_name_entry.text().strip()
                logger.info(f"[Action] Saving session to history with name: '{new_name}'")
                report["session_name"] = new_name if new_name else "Unnamed"
                save_to_history(report)
                QMessageBox.information(dialog, "Saved", "Session saved successfully.")
                dialog.accept()
            except Exception as e:
                QMessageBox.critical(dialog, "Error", f"Failed to save: {e}")
        
        primary_btn.clicked.connect(_save_and_close)
        layout.addWidget(primary_btn)

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

    def _show_dashboard(self):
        from dialogs.dashboard_dialog import TrueHourDashboard
        dialog = TrueHourDashboard(self)
        dialog.exec()

    def _handle_profile_switched(self, profile_name):
        if self.tracker.running:
            QMessageBox.warning(
                self, "Active Tracking Session",
                "Please stop the current active tracking session before switching or modifying profiles."
            )
            return False

        root_dir = get_app_data_root()
        profiles_file = os.path.join(root_dir, "profiles.json")
        try:
            # Load profiles.json
            with open(profiles_file, "r", encoding="utf-8") as f:
                pdata = json.load(f)

            pdata["active_profile"] = profile_name
            if profile_name not in pdata.get("profiles", []):
                pdata["profiles"].append(profile_name)

            with open(profiles_file, "w", encoding="utf-8") as f:
                json.dump(pdata, f, indent=4)

            # Dynamic dynamic reloading of target profile configuration
            self._load_app_settings()

            # Re-initialize target database schema inside target profile directory
            try:
                from database.schema import init_db
                init_db()
            except Exception as e:
                print(f"[TrueHour] Failed database bootstrap on profile switch: {e}")

            # Reload tracker configurations
            self.tracker._load_settings()
            self.tracker.tag_manager._load_tags()
            from tracker import reload_auto_excluded
            reload_auto_excluded()

            # Reset security time integrity detector for the new profile
            try:
                from secure_time import reset_detector
                reset_detector()
            except Exception as e:
                print(f"[TrueHour] Failed to reset security time detector: {e}")

            # Reload name overrides for the new profile
            try:
                from appinfo import _load_name_overrides
                _load_name_overrides()
            except Exception as e:
                print(f"[TrueHour] Failed to reload name overrides: {e}")

            # Apply dynamic parameters
            self.tracker.min_track_seconds = self.min_track_seconds
            self.tracker.save_interval = self.auto_save_seconds
            self.tracker.idle_threshold_seconds = self.idle_threshold_seconds_total

            # Trigger dynamic refresh of active layout
            self._last_app_state_hash = None
            self._refresh_app_list()
            self._update_developer_ui()
            self.apply_theme(self.dark_mode)

            # Reset earnings text if tracker not active
            if self.hourly_rate > 0:
                self.earnings_label.setText(f"💰 {self.currency_symbol}0.00 earned")
            else:
                self.earnings_label.setText(" ")

            QMessageBox.information(
                self, "Profile Switched",
                f"Successfully switched to profile '{profile_name}'."
            )
            return True
        except Exception as e:
            QMessageBox.critical(self, "Switch Failed", f"Failed to switch to profile:\n{e}")
            return False

    def _handle_profile_renamed(self, old_name, new_name):
        if self.tracker.running:
            QMessageBox.warning(
                self, "Active Tracking Session",
                "Please stop the current active tracking session before switching or modifying profiles."
            )
            return False

        root_dir = get_app_data_root()
        profiles_dir = os.path.join(root_dir, "profiles")
        src = os.path.join(profiles_dir, old_name)
        dst = os.path.join(profiles_dir, new_name)

        try:
            # Force GC to release SQLite database connection handles
            import gc
            import time
            gc.collect()

            # Retry rename loop in case of temporary OS indexer/anti-virus locks on Windows
            rename_success = False
            for _ in range(10):
                try:
                    if os.path.exists(src):
                        os.rename(src, dst)
                    rename_success = True
                    break
                except PermissionError:
                    time.sleep(0.1)
                    gc.collect()

            if not rename_success:
                raise PermissionError(f"Could not rename profile folder '{old_name}' because it is currently locked by another process.")

            profiles_file = os.path.join(root_dir, "profiles.json")
            with open(profiles_file, "r", encoding="utf-8") as f:
                pdata = json.load(f)

            # Update values
            pdata["active_profile"] = new_name
            pdata["profiles"] = [new_name if p == old_name else p for p in pdata.get("profiles", ["Default"])]

            with open(profiles_file, "w", encoding="utf-8") as f:
                json.dump(pdata, f, indent=4)

            self._handle_profile_switched(new_name)
            QMessageBox.information(
                self, "Profile Renamed",
                f"Successfully renamed profile from '{old_name}' to '{new_name}'."
            )
        except Exception as e:
            QMessageBox.critical(self, "Rename Failed", f"Failed to rename profile directory:\n{e}")

    def _handle_profile_deleted(self, profile_name):
        if self.tracker.running:
            QMessageBox.warning(
                self, "Active Tracking Session",
                "Please stop the current active tracking session before switching or modifying profiles."
            )
            return False

        root_dir = get_app_data_root()
        profiles_dir = os.path.join(root_dir, "profiles")
        target_dir = os.path.join(profiles_dir, profile_name)

        try:
            if os.path.exists(target_dir):
                import gc
                import stat
                import time
                gc.collect()

                # Helper to clear read-only flag on Windows
                def remove_readonly(func, path, _exc_info):
                    try:
                        os.chmod(path, stat.S_IWRITE)
                        func(path)
                    except Exception:
                        pass

                # Delete folder aggressively and with retries
                delete_success = False
                for _ in range(5):
                    try:
                        shutil.rmtree(target_dir, onerror=remove_readonly)
                        delete_success = True
                        break
                    except Exception:
                        time.sleep(0.1)
                        gc.collect()

                if not delete_success:
                    # Final aggressive sweep fallback
                    for root, dirs, files in os.walk(target_dir, topdown=False):
                        for file in files:
                            fp = os.path.join(root, file)
                            try:
                                os.chmod(fp, stat.S_IWRITE)
                                os.remove(fp)
                            except Exception:
                                pass
                        for d in dirs:
                            dp = os.path.join(root, d)
                            try:
                                os.chmod(dp, stat.S_IWRITE)
                                shutil.rmtree(dp, onerror=remove_readonly)
                            except Exception:
                                pass
                    shutil.rmtree(target_dir, onerror=remove_readonly)

            profiles_file = os.path.join(root_dir, "profiles.json")
            with open(profiles_file, "r", encoding="utf-8") as f:
                pdata = json.load(f)

            # Filter from list
            pdata["profiles"] = [p for p in pdata.get("profiles", ["Default"]) if p != profile_name]

            # Switch active to first available profile
            new_active = pdata["profiles"][0] if pdata["profiles"] else "Default"
            pdata["active_profile"] = new_active

            with open(profiles_file, "w", encoding="utf-8") as f:
                json.dump(pdata, f, indent=4)

            self._handle_profile_switched(new_active)
            QMessageBox.information(
                self, "Profile Deleted",
                f"Permanently deleted profile '{profile_name}'."
            )
        except Exception as e:
            QMessageBox.critical(self, "Delete Failed", f"Failed to delete profile:\n{e}")

    def _handle_settings_imported(self, profile_name):
        # Trigger dynamic switch to imported profile
        self._handle_profile_switched(profile_name)

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
    lock_file_path = os.path.join(get_app_data_root(), "truehour.lock")
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
