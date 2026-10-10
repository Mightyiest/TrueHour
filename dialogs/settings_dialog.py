import os
import shutil
import logging
import json
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTabWidget,
    QWidget,
    QScrollArea,
    QCheckBox,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QGroupBox,
    QPushButton,
    QMessageBox,
    QFileDialog,
    QApplication,
    QInputDialog,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QRadioButton,
    QGridLayout,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize

from widgets.custom_widgets import EmailChipWidget, QRThumbnailWidget
from theme import get_svg_icon
from config import get_app_data_dir, open_file, get_app_data_root
from tracker import AUTO_EXCLUDE_FILE, create_auto_excluded_if_missing
from appinfo import OVERRIDES_FILE
from assets import INFO_SVG, LOCK_SVG, GOOGLE_G_SVG

import drive_sync
from workers.drive_sync_worker import (
    DriveAuthWorker,
    DriveSyncWorker,
    DriveRestoreWorker,
    DriveRevisionsWorker,
)
from core.backup_manager import (
    backup_settings,
    backup_workspace,
    import_workspace,
    get_workspace_summary,
)

logger = logging.getLogger(__name__)


class NoWheelComboBox(QComboBox):
    """QComboBox subclass that ignores wheel events to prevent accidental option changes while scrolling container layouts."""

    def wheelEvent(self, event):
        event.ignore()


class DistractionAppsDialog(QDialog):
    def __init__(self, current_distractions, parent=None):
        super().__init__(parent)
        self.distraction_apps = list(current_distractions)
        self.setWindowTitle("Manage Distraction Apps")
        self.resize(360, 480)
        self.setMinimumSize(300, 400)

        self.theme_style = "light"
        if parent:
            self.theme_style = parent.settings.get(
                "theme_style",
                "modern-dark" if parent.settings.get("dark_mode", False) else "light",
            )
        if isinstance(self.theme_style, bool):
            self.theme_style = "modern-dark" if self.theme_style else "light"
        self.is_dark = self.theme_style in ["modern-dark", "classic-dark"]

        from theme import (
            get_qss_style,
            get_dark_palette,
            get_light_palette,
            ensure_checkmark_icon,
        )

        qss = get_qss_style(self.theme_style).replace(
            "CHECKMARK_PATH", ensure_checkmark_icon(self.theme_style)
        )
        self.setStyleSheet(qss)
        self.setPalette(
            get_dark_palette(self.theme_style) if self.is_dark else get_light_palette()
        )

        self.init_ui()

    def _get_all_tracked_apps(self):
        apps = set()
        # 1. Add current session tracker apps if parent's parent (TrueHourApp) is available
        if (
            self.parent()
            and hasattr(self.parent(), "parent")
            and self.parent().parent()
        ):
            main_app = self.parent().parent()
            if hasattr(main_app, "tracker") and main_app.tracker:
                apps.update(main_app.tracker.app_times.keys())
                apps.update(main_app.tracker.app_included.keys())

        # 2. Scan sessions/autosave folders
        from config import get_app_data_dir
        import glob

        for folder in ["sessions", "autosave"]:
            dirpath = os.path.join(get_app_data_dir(), folder)
            if os.path.exists(dirpath):
                for path in glob.glob(os.path.join(dirpath, "*.json")):
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            for app in data.get("apps", []):
                                if isinstance(app, dict) and "name" in app:
                                    apps.add(app["name"])
                                elif isinstance(app, list) and len(app) > 0:
                                    apps.add(app[0])
                    except Exception:
                        pass
        return sorted(list(apps), key=lambda x: x.lower())

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("Manage Distracting Apps", self)
        title.setStyleSheet(
            "font-family: 'Segoe UI'; font-size: 14px; font-weight: bold;"
        )
        layout.addWidget(title)

        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Search tracked apps...")
        self.search_input.textChanged.connect(self._filter_apps)
        layout.addWidget(self.search_input)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll_border = "#333333" if self.is_dark else "#E2E8F0"
        scroll.setStyleSheet(
            f"QScrollArea {{ border: 1px solid {scroll_border}; border-radius: 6px; }}"
        )

        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(8, 8, 8, 8)
        self.scroll_layout.setSpacing(6)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.checkboxes = {}
        all_apps = self._get_all_tracked_apps()

        for app in self.distraction_apps:
            if app not in all_apps:
                all_apps.append(app)
        all_apps = sorted(all_apps, key=lambda x: x.lower())

        for app in all_apps:
            self._create_app_row(app)

        scroll.setWidget(self.scroll_content)
        layout.addWidget(scroll)

        actions = QHBoxLayout()
        add_custom_btn = QPushButton("+ Add Custom App...", self)
        add_custom_btn.setObjectName("NormalButton")
        add_custom_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_custom_btn.clicked.connect(self._add_custom_app)
        actions.addWidget(add_custom_btn)
        actions.addStretch()
        layout.addLayout(actions)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        save_btn = QPushButton("Save", self)
        save_btn.setObjectName("AccentButton")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self._save_changes)
        btn_layout.addWidget(save_btn)

        cancel_btn = QPushButton("Cancel", self)
        cancel_btn.setObjectName("NormalButton")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    def _create_app_row(self, app):
        cb = QCheckBox(app, self.scroll_content)
        cb.setStyleSheet("font-family: 'Segoe UI'; font-size: 12px;")
        is_checked = any(d.lower() == app.lower() for d in self.distraction_apps)
        cb.setChecked(is_checked)
        self.scroll_layout.addWidget(cb)
        self.checkboxes[app] = cb

    def _filter_apps(self, text):
        text = text.lower().strip()
        for app, cb in self.checkboxes.items():
            cb.setVisible(not text or text in app.lower())

    def _add_custom_app(self):
        text, ok = QInputDialog.getText(
            self,
            "Add Custom App",
            "Enter application name or executable (e.g. steam.exe, game.exe):",
        )
        if ok and text.strip():
            app = text.strip()
            match_key = None
            for existing in self.checkboxes:
                if existing.lower() == app.lower():
                    match_key = existing
                    break

            if match_key:
                self.checkboxes[match_key].setChecked(True)
                self.checkboxes[match_key].setVisible(True)
            else:
                self._create_app_row(app)
                self.checkboxes[app].setChecked(True)

    def _save_changes(self):
        self.distraction_apps = [
            app for app, cb in self.checkboxes.items() if cb.isChecked()
        ]
        self.accept()


class BackupTypeDialog(QDialog):
    def __init__(self, theme_style, active_profile="Default", parent=None):
        super().__init__(parent)
        self.theme_style = theme_style
        self.active_profile = active_profile
        self.selected_type = None  # "standard", "encrypted", or None
        self.selected_scope = "workspace"  # "workspace" or "profile"
        self.setWindowTitle("Select Backup Options")
        self._center_window(400, 310)

        # Style matching parent
        from theme import (
            get_qss_style,
            get_dark_palette,
            get_light_palette,
            ensure_checkmark_icon,
        )

        is_dark = theme_style in ["modern-dark", "classic-dark"]
        qss = get_qss_style(theme_style).replace(
            "CHECKMARK_PATH", ensure_checkmark_icon(theme_style)
        )
        self.setStyleSheet(qss)
        self.setPalette(
            get_dark_palette(theme_style) if is_dark else get_light_palette()
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title = QLabel("Backup TrueHour Data", self)
        title.setStyleSheet(
            "font-family: 'Segoe UI'; font-size: 14px; font-weight: bold;"
        )
        layout.addWidget(title)

        scope_box = QGroupBox("Backup Scope", self)
        scope_layout = QVBoxLayout(scope_box)
        scope_layout.setSpacing(6)

        self.rb_workspace = QRadioButton("Entire Workspace (All Profiles & Sessions)", scope_box)
        self.rb_workspace.setChecked(True)
        self.rb_workspace.setStyleSheet("font-family: 'Segoe UI'; font-size: 12px; font-weight: bold;")
        scope_layout.addWidget(self.rb_workspace)

        self.rb_profile = QRadioButton(f"Current Profile Only ('{self.active_profile}')", scope_box)
        self.rb_profile.setStyleSheet("font-family: 'Segoe UI'; font-size: 12px;")
        scope_layout.addWidget(self.rb_profile)

        layout.addWidget(scope_box)

        desc = QLabel(
            "Standard backup excludes sensitive banking credentials. "
            "Encrypted backup protects banking info with a portable password for transfer to other PCs.",
            self,
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-family: 'Segoe UI'; font-size: 11px; color: #64748B;")
        layout.addWidget(desc)

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(8)

        self.btn_standard = QPushButton("Standard Backup", self)
        self.btn_standard.setObjectName("NormalButton")
        self.btn_standard.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_standard.setMinimumHeight(34)
        self.btn_standard.setStyleSheet(
            "font-family: 'Segoe UI'; font-size: 12px; font-weight: bold;"
        )
        self.btn_standard.clicked.connect(self._on_standard)
        buttons_layout.addWidget(self.btn_standard, 1)

        self.btn_encrypted = QPushButton("  Encrypted Backup", self)
        self.btn_encrypted.setObjectName("AccentButton")
        self.btn_encrypted.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_encrypted.setMinimumHeight(34)
        self.btn_encrypted.setStyleSheet(
            "font-family: 'Segoe UI'; font-size: 12px; font-weight: bold;"
        )
        self.btn_encrypted.setIcon(
            get_svg_icon(LOCK_SVG, QSize(14, 14), color_hex="#FFFFFF")
        )
        self.btn_encrypted.setIconSize(QSize(14, 14))
        self.btn_encrypted.clicked.connect(self._on_encrypted)
        buttons_layout.addWidget(self.btn_encrypted, 1)

        layout.addLayout(buttons_layout)

        cancel_layout = QHBoxLayout()
        cancel_layout.addStretch()
        self.btn_cancel = QPushButton("Cancel", self)
        self.btn_cancel.setObjectName("NormalButton")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.setStyleSheet(
            "font-family: 'Segoe UI'; font-size: 11px; padding: 4px 12px;"
        )
        self.btn_cancel.clicked.connect(self.reject)
        cancel_layout.addWidget(self.btn_cancel)
        layout.addLayout(cancel_layout)

    def _center_window(self, width, height):
        self.resize(width, height)
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - width) // 2
        y = (screen.height() - height) // 2
        self.move(x, y)

    def _on_standard(self):
        self.selected_scope = "workspace" if self.rb_workspace.isChecked() else "profile"
        self.selected_type = "standard"
        self.accept()

    def _on_encrypted(self):
        self.selected_scope = "workspace" if self.rb_workspace.isChecked() else "profile"
        self.selected_type = "encrypted"
        self.accept()


class CloudRevisionsDialog(QDialog):
    """Dialog displaying historical revisions of the cloud backup archive on Google Drive."""
    restore_requested = pyqtSignal(str)  # emits revision_id

    def __init__(self, theme_style, parent=None):
        super().__init__(parent)
        self.theme_style = theme_style
        self.setWindowTitle("Google Drive Backup History")
        self.resize(620, 420)
        self.setMinimumSize(520, 320)

        from theme import (
            get_qss_style,
            get_dark_palette,
            get_light_palette,
            ensure_checkmark_icon,
        )

        is_dark = theme_style in ["modern-dark", "classic-dark"]
        qss = get_qss_style(theme_style).replace(
            "CHECKMARK_PATH", ensure_checkmark_icon(theme_style)
        )
        self.setStyleSheet(qss)
        self.setPalette(
            get_dark_palette(theme_style) if is_dark else get_light_palette()
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        header = QLabel("Google Drive Revision History", self)
        header.setStyleSheet("font-family: 'Segoe UI'; font-size: 15px; font-weight: bold;")
        layout.addWidget(header)

        desc = QLabel(
            "All cloud backup revisions are protected with permanent retention. "
            "Select any past revision to preview and restore it into your workspace.",
            self,
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-family: 'Segoe UI'; font-size: 11px; color: #64748B;")
        layout.addWidget(desc)

        self.table = QTableWidget(self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Date & Time", "Archive Size", "Retention Status", "Action"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        self.status_lbl = QLabel("Loading revision history...", self)
        self.status_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 11px; color: #64748B;")
        layout.addWidget(self.status_lbl)

        btn_row = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh", self)
        self.btn_refresh.setObjectName("NormalButton")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.clicked.connect(self._load_revisions)
        btn_row.addWidget(self.btn_refresh)

        btn_row.addStretch()

        self.btn_close = QPushButton("Close", self)
        self.btn_close.setObjectName("NormalButton")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.accept)
        btn_row.addWidget(self.btn_close)
        layout.addLayout(btn_row)

        self._load_revisions()

    def _load_revisions(self):
        self.status_lbl.setText("Fetching revision history from Google Drive...")
        self.btn_refresh.setEnabled(False)
        self._worker = DriveRevisionsWorker(parent=self)
        self._worker.finished.connect(self._on_revisions_loaded)
        self._worker.start()

    def _on_revisions_loaded(self, success, revisions, err):
        self.btn_refresh.setEnabled(True)
        if not success or not revisions:
            self.status_lbl.setText("No historical revisions found or error fetching.")
            return

        self.table.setRowCount(0)
        self.status_lbl.setText(f"Found {len(revisions)} cloud backup revision(s).")

        from datetime import datetime
        sorted_revs = sorted(revisions, key=lambda r: r.get("modifiedTime", ""), reverse=True)

        for row, rev in enumerate(sorted_revs):
            self.table.insertRow(row)
            rev_id = rev.get("id", "")
            mod_time = rev.get("modifiedTime", "")
            try:
                dt = datetime.fromisoformat(mod_time.replace("Z", "+00:00"))
                display_time = dt.strftime("%Y-%m-%d %I:%M %p")
            except Exception:
                display_time = mod_time

            sz_bytes = int(rev.get("size") or 0)
            if sz_bytes >= 1024 * 1024:
                display_size = f"{sz_bytes / (1024*1024):.1f} MB"
            elif sz_bytes >= 1024:
                display_size = f"{sz_bytes / 1024:.1f} KB"
            else:
                display_size = f"{sz_bytes} B"

            keep_forever = rev.get("keepForever", False)
            status_text = "Pinned / Protected" if keep_forever else "Standard"

            self.table.setItem(row, 0, QTableWidgetItem(display_time))
            self.table.setItem(row, 1, QTableWidgetItem(display_size))
            self.table.setItem(row, 2, QTableWidgetItem(status_text))

            btn_restore = QPushButton("Restore", self.table)
            btn_restore.setObjectName("AccentButton" if row == 0 else "NormalButton")
            btn_restore.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_restore.setStyleSheet("font-size: 11px; padding: 2px 8px;")
            btn_restore.clicked.connect(
                lambda checked=False, rid=rev_id, d=display_time, s=display_size: self._confirm_restore(rid, d, s)
            )
            self.table.setCellWidget(row, 3, btn_restore)

    def _confirm_restore(self, rev_id, display_time, display_size):
        confirm = QMessageBox.question(
            self,
            "Restore Historical Revision?",
            (
                f"Are you sure you want to restore the cloud backup from {display_time} ({display_size})?\n\n"
                "This will restore all profiles and sessions from that snapshot. "
                "A local safety snapshot will automatically be created before restoring."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.restore_requested.emit(rev_id)
            self.accept()


class SettingsDialog(QDialog):
    manage_categories_requested = pyqtSignal()
    about_requested = pyqtSignal()
    reload_exclusions_requested = pyqtSignal()
    settings_saved = pyqtSignal(dict)
    theme_toggled = pyqtSignal(str)
    profile_changed = pyqtSignal(str)
    profile_renamed = pyqtSignal(str, str)
    profile_deleted = pyqtSignal(str)
    settings_imported = pyqtSignal(str)
    test_notification_requested = pyqtSignal()

    def __init__(self, current_settings, parent=None):
        super().__init__(parent)
        self.settings = dict(current_settings)  # copy to avoid mutating directly
        self.setWindowTitle("Settings")
        self._center_window(620, 700)
        self.setMinimumSize(580, 580)

        # Load profiles config
        root_dir = get_app_data_root()
        profiles_file = os.path.join(root_dir, "profiles.json")
        self.profiles_list = ["Default"]
        self.active_profile = "Default"
        if os.path.exists(profiles_file):
            try:
                with open(profiles_file, "r", encoding="utf-8") as f:
                    pdata = json.load(f)
                    self.profiles_list = pdata.get("profiles", ["Default"])
                    self.active_profile = pdata.get("active_profile", "Default")
            except Exception:
                pass

        self._qr_paths_local = list(self.settings.get("qr_code_paths", []))
        self._qr_links_local = dict(self.settings.get("qr_code_links", {}))
        self._qr_thumb_refs = []

        # Apply stylesheet and palette on start
        self.theme_style = self.settings.get(
            "theme_style",
            "modern-dark" if self.settings.get("dark_mode", False) else "light",
        )
        if isinstance(self.theme_style, bool):
            self.theme_style = "modern-dark" if self.theme_style else "light"
        is_dark = self.theme_style in ["modern-dark", "classic-dark"]
        from theme import (
            get_qss_style,
            get_dark_palette,
            get_light_palette,
            ensure_checkmark_icon,
        )

        qss = get_qss_style(self.theme_style).replace(
            "CHECKMARK_PATH", ensure_checkmark_icon(self.theme_style)
        )
        self.setStyleSheet(qss)
        self.setPalette(
            get_dark_palette(self.theme_style) if is_dark else get_light_palette()
        )

        self._build_ui()

    def _center_window(self, width, height):
        self.resize(width, height)
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - width) // 2
        y = (screen.height() - height) // 2
        self.move(x, y)

    def set_reload_status(self, success):
        if success:
            self.reload_status_lbl.setText("✓ Reloaded")
            self.reload_status_lbl.setStyleSheet("color: #0F7B0F;")
        else:
            self.reload_status_lbl.setText("✗ Failed")
            self.reload_status_lbl.setStyleSheet("color: #C42B1C;")
        QTimer.singleShot(2000, lambda: self.reload_status_lbl.setText(" "))

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        title = QLabel("Settings", self)
        title.setStyleSheet(
            "font-family: 'Segoe UI'; font-size: 15px; font-weight: bold;"
        )
        layout.addWidget(title)

        # QTabWidget for settings categories
        settings_tabs = QTabWidget(self)

        # ── Tab 1: General Settings ──────────────────────────────────
        tab_general = QWidget()
        tg_main_layout = QVBoxLayout(tab_general)
        tg_main_layout.setContentsMargins(0, 0, 0, 0)
        tg_main_layout.setSpacing(0)

        scroll_general = QScrollArea(tab_general)
        scroll_general.setWidgetResizable(True)
        scroll_general.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll_general.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )

        scroll_general_content = QWidget()
        tg_layout = QVBoxLayout(scroll_general_content)
        tg_layout.setContentsMargins(12, 12, 12, 12)
        tg_layout.setSpacing(6)

        # Profile Selection Group Box
        profile_box = QGroupBox("Profile Selection", scroll_general_content)
        profile_layout = QHBoxLayout(profile_box)
        profile_layout.setContentsMargins(8, 8, 8, 8)
        profile_layout.setSpacing(6)

        self.profile_combo = NoWheelComboBox(scroll_general_content)
        self.profile_combo.addItems(self.profiles_list)
        self.profile_combo.setCurrentText(self.active_profile)
        self.profile_combo.currentTextChanged.connect(self._on_profile_combo_changed)
        profile_layout.addWidget(self.profile_combo, 2)

        btn_new_prof = QPushButton("New Profile", scroll_general_content)
        btn_new_prof.setObjectName("NormalButton")
        btn_new_prof.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_new_prof.clicked.connect(self._on_new_profile_clicked)
        profile_layout.addWidget(btn_new_prof, 1)

        btn_rename_prof = QPushButton("Rename", scroll_general_content)
        btn_rename_prof.setObjectName("NormalButton")
        btn_rename_prof.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_rename_prof.clicked.connect(self._on_rename_profile_clicked)
        profile_layout.addWidget(btn_rename_prof, 1)

        btn_delete_prof = QPushButton("Delete", scroll_general_content)
        btn_delete_prof.setObjectName("NormalButton")
        btn_delete_prof.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_delete_prof.clicked.connect(self._on_delete_profile_clicked)
        profile_layout.addWidget(btn_delete_prof, 1)

        tg_layout.addWidget(profile_box)

        self.cb_confirm = QCheckBox(
            "Always ask for confirmation before closing", scroll_general_content
        )
        self.cb_confirm.setChecked(self.settings.get("confirm_on_close", True))
        self.cb_confirm.setStyleSheet("font-family: 'Segoe UI'; font-size: 13px;")
        tg_layout.addWidget(self.cb_confirm)

        # Checkbox for Developer Options
        self.cb_dev = QCheckBox(
            "Enable Developer Options (Debug Console)", scroll_general_content
        )
        self.cb_dev.setChecked(self.settings.get("developer_mode", False))
        self.cb_dev.setStyleSheet("font-family: 'Segoe UI'; font-size: 13px;")
        tg_layout.addWidget(self.cb_dev)

        # Dropdown selection for Theme Style
        theme_row = QHBoxLayout()
        theme_lbl = QLabel("Theme Style:", scroll_general_content)
        theme_lbl.setStyleSheet(
            "font-family: 'Segoe UI'; font-size: 13px; font-weight: 500;"
        )
        theme_row.addWidget(theme_lbl)

        self.theme_combo = NoWheelComboBox(scroll_general_content)
        self.theme_combo.addItems(["Light", "Modern Dark", "Classic Dark"])

        current_style = self.settings.get(
            "theme_style",
            "modern-dark" if self.settings.get("dark_mode", False) else "light",
        )
        if current_style == "light":
            self.theme_combo.setCurrentText("Light")
        elif current_style == "classic-dark":
            self.theme_combo.setCurrentText("Classic Dark")
        else:
            self.theme_combo.setCurrentText("Modern Dark")

        theme_row.addWidget(self.theme_combo)
        theme_row.addStretch()
        tg_layout.addLayout(theme_row)

        def _on_theme_combo_changed(text):
            if text == "Light":
                style_name = "light"
            elif text == "Classic Dark":
                style_name = "classic-dark"
            else:
                style_name = "modern-dark"

            self.settings["theme_style"] = style_name
            self.theme_style = style_name
            self.settings["dark_mode"] = style_name in ["modern-dark", "classic-dark"]
            is_dark = self.settings["dark_mode"]

            # Instantly apply stylesheet to SettingsDialog itself!
            from theme import (
                get_qss_style,
                get_dark_palette,
                get_light_palette,
                ensure_checkmark_icon,
            )

            qss = get_qss_style(style_name).replace(
                "CHECKMARK_PATH", ensure_checkmark_icon(style_name)
            )
            self.setStyleSheet(qss)
            self.setPalette(
                get_dark_palette(style_name) if is_dark else get_light_palette()
            )
            self.theme_toggled.emit(style_name)

        self.theme_combo.currentTextChanged.connect(_on_theme_combo_changed)

        form_general = QFormLayout()
        form_general.setSpacing(6)

        self.min_sec_entry = QLineEdit(scroll_general_content)
        self.min_sec_entry.setFixedWidth(80)
        self.min_sec_entry.setText(str(self.settings.get("min_track_seconds", 2)))
        form_general.addRow("Min activity threshold (secs):", self.min_sec_entry)

        self.auto_save_entry = QLineEdit(scroll_general_content)
        self.auto_save_entry.setFixedWidth(80)
        self.auto_save_entry.setText(str(self.settings.get("auto_save_seconds", 10)))
        form_general.addRow("Auto-save interval (secs):", self.auto_save_entry)

        # Idle row
        idle_row = QHBoxLayout()
        idle_row.setSpacing(4)
        _idle_total = self.settings.get("idle_threshold_seconds_total", 120)
        _idle_m_def = _idle_total // 60
        _idle_s_def = _idle_total % 60

        self.idle_min_entry = QLineEdit(scroll_general_content)
        self.idle_min_entry.setFixedWidth(40)
        self.idle_min_entry.setText(str(_idle_m_def))
        idle_row.addWidget(self.idle_min_entry)
        idle_row.addWidget(QLabel("min"))

        self.idle_sec_entry = QLineEdit(scroll_general_content)
        self.idle_sec_entry.setFixedWidth(40)
        self.idle_sec_entry.setText(str(_idle_s_def))
        idle_row.addWidget(self.idle_sec_entry)
        idle_row.addWidget(QLabel("sec"))
        idle_row.addStretch()

        form_general.addRow("Idle auto-pause:", idle_row)

        # Billing Group details inside general tab
        currency_options = [
            "$ (USD)",
            "€ (EUR)",
            "£ (GBP)",
            "¥ (JPY/CNY)",
            "₱ (PHP)",
            "₹ (INR)",
            "₽ (RUB)",
            "₩ (KRW)",
            "₫ (VND)",
            "฿ (THB)",
            "₪ (ILS)",
            "₺ (TRY)",
            "Rp (IDR)",
            "RM (MYR)",
            "R$ (BRL)",
            "C$ (CAD)",
            "A$ (AUD)",
            "S$ (SGD)",
            "NZ$ (NZD)",
            "CHF (CHF)",
            "kr (SEK/NOK)",
            "zł (PLN)",
            "Kč (CZK)",
            "Ft (HUF)",
            "lei (RON)",
            "лв (BGN)",
            "₴ (UAH)",
            "R (ZAR)",
        ]
        self.curr_combo = NoWheelComboBox(scroll_general_content)
        self.curr_combo.setFixedWidth(160)
        self.curr_combo.addItems(currency_options)
        curr_symbol = self.settings.get("currency_symbol", "$")
        matched = [c for c in currency_options if c.startswith(curr_symbol)]
        if matched:
            self.curr_combo.setCurrentText(matched[0])
        else:
            self.curr_combo.setCurrentText(curr_symbol)
        form_general.addRow("Currency symbol:", self.curr_combo)

        self.rate_entry = QLineEdit(scroll_general_content)
        self.rate_entry.setFixedWidth(100)
        self.rate_entry.setText(f"{self.settings.get('hourly_rate', 0.0):.2f}")
        form_general.addRow("Hourly rate:", self.rate_entry)

        tg_layout.addLayout(form_general)

        # Distraction Auto-Pause Group
        distract_box = QGroupBox("Distraction Auto-Pause", scroll_general_content)
        distract_layout = QVBoxLayout(distract_box)
        distract_layout.setContentsMargins(8, 8, 8, 8)
        distract_layout.setSpacing(6)

        self.cb_distract = QCheckBox(
            "Automatically pause tracking on distracting apps", distract_box
        )
        self.cb_distract.setChecked(
            self.settings.get("enable_distraction_auto_pause", False)
        )
        self.cb_distract.setStyleSheet("font-family: 'Segoe UI'; font-size: 13px;")
        distract_layout.addWidget(self.cb_distract)

        self._distraction_apps_local = list(self.settings.get("distraction_apps", []))

        def _manage_distraction_apps():
            dialog = DistractionAppsDialog(self._distraction_apps_local, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self._distraction_apps_local = dialog.distraction_apps

        self.manage_distract_btn = QPushButton(
            "Manage Distraction Apps...", distract_box
        )
        self.manage_distract_btn.setObjectName("NormalButton")
        self.manage_distract_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.manage_distract_btn.clicked.connect(_manage_distraction_apps)
        distract_layout.addWidget(self.manage_distract_btn)

        self.cb_distract.toggled.connect(self.manage_distract_btn.setEnabled)
        self.manage_distract_btn.setEnabled(self.cb_distract.isChecked())

        tg_layout.addWidget(distract_box)

        # Config Files Group
        config_box = QGroupBox("Configuration && Categories", scroll_general_content)
        config_layout = QVBoxLayout(config_box)
        config_layout.setContentsMargins(8, 8, 8, 8)
        config_layout.setSpacing(4)

        def _open_file(filepath):
            logger.info(f"[Action] Opened config file: {os.path.basename(filepath)}")
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
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write("# Configuration file created.\n")
                except Exception:
                    pass
            try:
                open_file(filepath)
            except Exception:
                QMessageBox.critical(self, "Error", f"Could not open: {filepath}")

        btn_overrides = QPushButton("Edit Name Overrides", scroll_general_content)
        btn_overrides.setObjectName("NormalButton")
        btn_overrides.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_overrides.clicked.connect(lambda: _open_file(OVERRIDES_FILE))
        config_layout.addWidget(btn_overrides)

        excl_row = QHBoxLayout()
        excl_row.setSpacing(6)
        btn_excl = QPushButton("Edit Auto-Exclusions", scroll_general_content)
        btn_excl.setObjectName("NormalButton")
        btn_excl.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_excl.setFixedHeight(30)
        btn_excl.clicked.connect(lambda: _open_file(AUTO_EXCLUDE_FILE))
        excl_row.addWidget(btn_excl, 1)

        btn_reload = QPushButton("🔄 Reload", scroll_general_content)
        btn_reload.setObjectName("NormalButton")
        btn_reload.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_reload.setFixedHeight(30)
        btn_reload.setMinimumWidth(100)

        self.reload_status_lbl = QLabel(" ", scroll_general_content)
        self.reload_status_lbl.setStyleSheet("font-size: 11px; font-weight: bold;")

        btn_reload.clicked.connect(lambda: self.reload_exclusions_requested.emit())
        excl_row.addWidget(btn_reload)
        excl_row.addWidget(self.reload_status_lbl)
        config_layout.addLayout(excl_row)

        btn_categories = QPushButton(
            "Manage Project Categories...", scroll_general_content
        )
        btn_categories.setObjectName("NormalButton")
        btn_categories.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_categories.setFixedHeight(30)
        btn_categories.clicked.connect(lambda: self.manage_categories_requested.emit())
        config_layout.addWidget(btn_categories)

        btn_about = QPushButton("  About TrueHour", scroll_general_content)
        btn_about.setObjectName("AboutButton")
        btn_about.setCursor(Qt.CursorShape.PointingHandCursor)
        is_dark_theme = self.theme_style in ["modern-dark", "classic-dark"]
        btn_about.setIcon(get_svg_icon(INFO_SVG, QSize(14, 14), color_hex="#F59E0B" if is_dark_theme else "#D97706"))
        btn_about.setIconSize(QSize(14, 14))
        btn_about.setFixedHeight(30)
        btn_about.setStyleSheet("""
            QPushButton#AboutButton {
                background-color: transparent;
                color: #D97706;
                border: 1px solid #D97706;
                border-radius: 6px;
                padding: 4px 14px;
                font-weight: 600;
                font-family: 'Segoe UI';
                font-size: 12px;
            }
            QPushButton#AboutButton:hover {
                background-color: rgba(217, 119, 6, 0.12);
                border-color: #B45309;
                color: #B45309;
            }
            QPushButton#AboutButton:pressed {
                background-color: rgba(217, 119, 6, 0.22);
            }
        """)
        btn_about.clicked.connect(lambda: self.about_requested.emit())
        config_layout.addWidget(btn_about)

        tg_layout.addWidget(config_box)

        # Backup & Restore Group
        backup_box = QGroupBox("Backup && Restore", scroll_general_content)
        backup_layout = QHBoxLayout(backup_box)
        backup_layout.setContentsMargins(10, 10, 10, 10)
        backup_layout.setSpacing(8)

        btn_backup = QPushButton("Backup Workspace...", scroll_general_content)
        btn_backup.setObjectName("AccentButton")
        btn_backup.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_backup.setFixedHeight(32)
        btn_backup.clicked.connect(self._on_backup_clicked)
        backup_layout.addWidget(btn_backup, 1)

        btn_import = QPushButton("Import / Restore...", scroll_general_content)
        btn_import.setObjectName("NormalButton")
        btn_import.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_import.setFixedHeight(32)
        btn_import.clicked.connect(self._on_import_clicked)
        backup_layout.addWidget(btn_import, 1)

        btn_browse = QPushButton("Open Data Folder", scroll_general_content)
        btn_browse.setObjectName("NormalButton")
        btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_browse.setFixedHeight(32)
        btn_browse.clicked.connect(self._on_browse_files_clicked)
        backup_layout.addWidget(btn_browse, 1)

        tg_layout.addWidget(backup_box)

        # Google Drive Cloud Sync Group
        drive_box = QGroupBox("Google Drive Cloud Sync", scroll_general_content)
        drive_layout = QVBoxLayout(drive_box)
        drive_layout.setContentsMargins(10, 10, 10, 10)
        drive_layout.setSpacing(8)

        self.drive_status_lbl = QLabel("Checking status...", drive_box)
        self.drive_status_lbl.setWordWrap(True)
        self.drive_status_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 12px;")
        drive_layout.addWidget(self.drive_status_lbl)

        # Disconnected state: Google Sign-in button
        self.btn_drive_auth = QPushButton(" Sign in with Google", drive_box)
        self.btn_drive_auth.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_drive_auth.setIcon(get_svg_icon(GOOGLE_G_SVG, QSize(18, 18)))
        self.btn_drive_auth.setIconSize(QSize(18, 18))
        self.btn_drive_auth.setFixedHeight(36)

        is_dark_theme = self.settings.get("dark_mode", False)
        if is_dark_theme:
            self.btn_drive_auth.setStyleSheet("""
                QPushButton {
                    background-color: #131314;
                    color: #E3E3E3;
                    border: 1px solid #8E918F;
                    border-radius: 18px;
                    font-family: 'Roboto', 'Segoe UI', sans-serif;
                    font-size: 13px;
                    font-weight: 500;
                    padding: 0px 16px;
                }
                QPushButton:hover {
                    background-color: #202124;
                    border-color: #A8AAA7;
                }
                QPushButton:pressed {
                    background-color: #303134;
                }
                QPushButton:disabled {
                    background-color: #1F1F1F;
                    color: #5E5E5E;
                    border-color: #444444;
                }
            """)
        else:
            self.btn_drive_auth.setStyleSheet("""
                QPushButton {
                    background-color: #FFFFFF;
                    color: #1F1F1F;
                    border: 1px solid #747775;
                    border-radius: 18px;
                    font-family: 'Roboto', 'Segoe UI', sans-serif;
                    font-size: 13px;
                    font-weight: 500;
                    padding: 0px 16px;
                }
                QPushButton:hover {
                    background-color: #F8F9FA;
                    border-color: #5E5E5E;
                }
                QPushButton:pressed {
                    background-color: #F1F3F4;
                }
                QPushButton:disabled {
                    background-color: #F5F5F5;
                    color: #A8AAA7;
                    border-color: #E3E3E3;
                }
            """)
        self.btn_drive_auth.clicked.connect(self._on_drive_auth_clicked)
        drive_layout.addWidget(self.btn_drive_auth)

        # Connected state: Clean 2x2 grid for sync actions
        self.drive_actions_widget = QWidget(drive_box)
        drive_grid = QGridLayout(self.drive_actions_widget)
        drive_grid.setContentsMargins(0, 0, 0, 0)
        drive_grid.setSpacing(8)

        self.btn_drive_sync = QPushButton("Sync All Profiles Now", self.drive_actions_widget)
        self.btn_drive_sync.setObjectName("AccentButton")
        self.btn_drive_sync.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_drive_sync.setFixedHeight(32)
        self.btn_drive_sync.clicked.connect(self._on_drive_sync_clicked)
        drive_grid.addWidget(self.btn_drive_sync, 0, 0)

        self.btn_drive_restore = QPushButton("Restore from Cloud", self.drive_actions_widget)
        self.btn_drive_restore.setObjectName("NormalButton")
        self.btn_drive_restore.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_drive_restore.setFixedHeight(32)
        self.btn_drive_restore.clicked.connect(self._on_drive_restore_clicked)
        drive_grid.addWidget(self.btn_drive_restore, 0, 1)

        self.btn_drive_history = QPushButton("Revision History...", self.drive_actions_widget)
        self.btn_drive_history.setObjectName("NormalButton")
        self.btn_drive_history.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_drive_history.setFixedHeight(32)
        self.btn_drive_history.clicked.connect(self._on_drive_history_clicked)
        drive_grid.addWidget(self.btn_drive_history, 1, 0)

        self.btn_drive_signout = QPushButton("Sign Out", self.drive_actions_widget)
        self.btn_drive_signout.setObjectName("NormalButton")
        self.btn_drive_signout.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_drive_signout.setFixedHeight(32)
        self.btn_drive_signout.clicked.connect(self._on_drive_signout_clicked)
        drive_grid.addWidget(self.btn_drive_signout, 1, 1)

        drive_layout.addWidget(self.drive_actions_widget)

        self.cb_drive_auto = QCheckBox("Automatically sync to Google Drive (startup, session save, and periodic)", drive_box)
        self.cb_drive_auto.setChecked(self.settings.get("google_drive_auto_sync", True))
        self.cb_drive_auto.setStyleSheet("font-family: 'Segoe UI'; font-size: 12px;")
        self.cb_drive_auto.toggled.connect(lambda val: self.settings.__setitem__("google_drive_auto_sync", val))
        drive_layout.addWidget(self.cb_drive_auto)

        tg_layout.addWidget(drive_box)
        self._update_drive_ui()

        tg_layout.addStretch()

        scroll_general.setWidget(scroll_general_content)
        tg_main_layout.addWidget(scroll_general)

        # (Focus goals configuration moved directly to the Web Dashboard)

        # ── Tab 2: Billing & Invoicing Details ────────────────────────
        tab_invoice = QWidget()
        ti_layout = QVBoxLayout(tab_invoice)
        ti_layout.setContentsMargins(0, 0, 0, 0)
        ti_layout.setSpacing(0)

        scroll_invoice = QScrollArea(tab_invoice)
        scroll_invoice.setWidgetResizable(True)
        scroll_invoice.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll_invoice.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )

        scroll_invoice_content = QWidget()
        scroll_invoice_layout = QVBoxLayout(scroll_invoice_content)
        scroll_invoice_layout.setContentsMargins(12, 12, 12, 12)
        scroll_invoice_layout.setSpacing(10)

        # Freelancer Business Profile
        biz_box = QGroupBox("Business Profile Details", scroll_invoice_content)
        biz_layout = QFormLayout(biz_box)
        biz_layout.setSpacing(6)

        self.business_name_entry = QLineEdit(biz_box)
        self.business_name_entry.setText(self.settings.get("business_name", ""))
        biz_layout.addRow("Business Name:", self.business_name_entry)

        # Email Chip Widget for business contact emails
        self.business_email_chips = EmailChipWidget(biz_box)
        self.business_email_chips.set_emails(self.settings.get("business_emails", []))
        biz_layout.addRow("Contact Emails:", self.business_email_chips)

        self.business_phone_entry = QLineEdit(biz_box)
        self.business_phone_entry.setText(self.settings.get("business_phone", ""))
        biz_layout.addRow("Contact Phone:", self.business_phone_entry)

        self.business_address_entry = QLineEdit(biz_box)
        self.business_address_entry.setText(self.settings.get("business_address", ""))
        biz_layout.addRow("Billing Address:", self.business_address_entry)

        self.business_payment_entry = QLineEdit(biz_box)
        self.business_payment_entry.setPlaceholderText(
            "e.g. IBAN: US12 3456... or PayPal: ..."
        )
        self.business_payment_entry.setText(self.settings.get("business_payment", ""))
        biz_layout.addRow("Payment Details:", self.business_payment_entry)

        scroll_invoice_layout.addWidget(biz_box)

        # Bank Transfer Details
        bank_box = QGroupBox("Bank Transfer Details", scroll_invoice_content)
        bank_layout = QFormLayout(bank_box)
        bank_layout.setSpacing(6)

        self.enable_bank_cb = QCheckBox(
            "Enable Bank Transfer Details on Invoices", bank_box
        )
        self.enable_bank_cb.setChecked(self.settings.get("enable_bank_details", True))
        bank_layout.addRow(self.enable_bank_cb)

        self.bank_holder_entry = QLineEdit(bank_box)
        self.bank_holder_entry.setText(self.settings.get("bank_holder", ""))
        bank_layout.addRow("Account Holder:", self.bank_holder_entry)

        self.bank_account_entry = QLineEdit(bank_box)
        self.bank_account_entry.setText(self.settings.get("bank_account", ""))
        bank_layout.addRow("Account Number:", self.bank_account_entry)

        self.bank_routing_entry = QLineEdit(bank_box)
        self.bank_routing_entry.setText(self.settings.get("bank_routing", ""))
        bank_layout.addRow("Routing Number:", self.bank_routing_entry)

        self.bank_swift_entry = QLineEdit(bank_box)
        self.bank_swift_entry.setText(self.settings.get("bank_swift", ""))
        bank_layout.addRow("SWIFT / BIC:", self.bank_swift_entry)

        self.bank_name_entry = QLineEdit(bank_box)
        self.bank_name_entry.setText(self.settings.get("bank_name", ""))
        bank_layout.addRow("Bank Name:", self.bank_name_entry)

        self.bank_address_entry = QLineEdit(bank_box)
        self.bank_address_entry.setText(self.settings.get("bank_address", ""))
        bank_layout.addRow("Bank Address:", self.bank_address_entry)

        self.enable_bank_cb.toggled.connect(self._toggle_bank_inputs)
        self._toggle_bank_inputs(self.enable_bank_cb.isChecked())

        scroll_invoice_layout.addWidget(bank_box)

        # Default Client Profile
        client_box = QGroupBox("Default Client Profile", scroll_invoice_content)
        client_layout = QFormLayout(client_box)
        client_layout.setSpacing(6)

        self.client_name_entry = QLineEdit(client_box)
        self.client_name_entry.setText(self.settings.get("client_name", ""))
        client_layout.addRow("Client Name:", self.client_name_entry)

        # Email Chip Widget for client contact emails
        self.client_email_chips = EmailChipWidget(client_box)
        self.client_email_chips.set_emails(self.settings.get("client_emails", []))
        client_layout.addRow("Client Emails:", self.client_email_chips)

        self.client_address_entry = QLineEdit(client_box)
        self.client_address_entry.setText(self.settings.get("client_address", ""))
        client_layout.addRow("Client Address:", self.client_address_entry)

        scroll_invoice_layout.addWidget(client_box)

        # Logo Profile Configuration
        logo_box = QGroupBox("Invoice Business Logo", scroll_invoice_content)
        logo_layout = QVBoxLayout(logo_box)
        logo_layout.setSpacing(4)

        self.enable_logo_cb = QCheckBox("Enable Business Logo on Invoices", logo_box)
        self.enable_logo_cb.setChecked(self.settings.get("enable_business_logo", True))
        logo_layout.addWidget(self.enable_logo_cb)

        logo_row = QHBoxLayout()
        self.logo_path_entry = QLineEdit(logo_box)
        self.logo_path_entry.setText(self.settings.get("business_logo_path", ""))
        logo_row.addWidget(self.logo_path_entry, 1)

        def _browse_logo():
            logger.info("[Action] Browsing for business logo image")
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Select Business Logo Image",
                "",
                "Image files (*.png *.jpg *.jpeg)",
            )
            if path:
                self.logo_path_entry.setText(path)

        self.browse_logo_btn = QPushButton("Browse...", logo_box)
        self.browse_logo_btn.setObjectName("NormalButton")
        self.browse_logo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.browse_logo_btn.clicked.connect(_browse_logo)
        logo_row.addWidget(self.browse_logo_btn)
        logo_layout.addLayout(logo_row)

        self.logo_spec_lbl = QLabel(
            "Image Spec: PNG, JPG, or JPEG. Max size: 250px (w) x 80px (h). Proportionally resized automatically.",
            logo_box,
        )
        self.logo_spec_lbl.setWordWrap(True)
        self.logo_spec_lbl.setStyleSheet(
            "color: #64748B; font-size: 10px; font-family: 'Segoe UI';"
        )
        logo_layout.addWidget(self.logo_spec_lbl)

        self.enable_logo_cb.toggled.connect(self._toggle_logo_inputs)
        self._toggle_logo_inputs(self.enable_logo_cb.isChecked())

        scroll_invoice_layout.addWidget(logo_box)

        # ── Payment QR Codes Section ─────────────────────────────────
        qr_box = QGroupBox("Payment QR Codes", scroll_invoice_content)
        self.qr_box_layout = QVBoxLayout(qr_box)
        self.qr_box_layout.setSpacing(6)

        self.qr_thumbs_widget = QWidget(qr_box)
        self.qr_thumbs_layout = QHBoxLayout(self.qr_thumbs_widget)
        self.qr_thumbs_layout.setContentsMargins(0, 0, 0, 0)
        self.qr_thumbs_layout.setSpacing(8)

        self._refresh_qr_thumbnails()
        self.qr_box_layout.addWidget(self.qr_thumbs_widget)

        def _add_qr_code():
            if len(self._qr_paths_local) >= 4:
                QMessageBox.information(
                    self, "QR Limit", "Maximum of 4 QR code images allowed."
                )
                return
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Select Payment QR Code Image",
                "",
                "Image files (*.png *.jpg *.jpeg)",
            )
            if not path:
                return
            qr_dir = os.path.join(get_app_data_dir(), "qr_codes")
            os.makedirs(qr_dir, exist_ok=True)
            fname = f"qr_{len(self._qr_paths_local) + 1}_{os.path.basename(path)}"
            dest = os.path.join(qr_dir, fname)
            try:
                shutil.copy2(path, dest)
                logger.info(f"[Action] Added payment QR code: {fname}")
                self._qr_paths_local.append(fname)
                self._refresh_qr_thumbnails()
            except Exception as ex:
                QMessageBox.critical(self, "Error", f"Failed to copy QR image:\n{ex}")

        add_qr_btn = QPushButton("+ Add QR Code", qr_box)
        add_qr_btn.setObjectName("NormalButton")
        add_qr_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_qr_btn.clicked.connect(_add_qr_code)
        self.qr_box_layout.addWidget(add_qr_btn)

        qr_spec_lbl = QLabel(
            "Upload up to 4 payment QR code images (PNG/JPG). They will appear in generated invoices at 140×140px.",
            qr_box,
        )
        qr_spec_lbl.setWordWrap(True)
        qr_spec_lbl.setStyleSheet(
            "color: #64748B; font-size: 10px; font-family: 'Segoe UI';"
        )
        self.qr_box_layout.addWidget(qr_spec_lbl)

        scroll_invoice_layout.addWidget(qr_box)

        # ── Sensitive Data Masking Toggles ────────────────────────────
        mask_box = QGroupBox("Privacy Settings", scroll_invoice_content)
        mask_layout = QVBoxLayout(mask_box)
        mask_layout.setSpacing(6)

        self.mask_biz_email_cb = QCheckBox(
            "Mask business contact emails by default", mask_box
        )
        self.mask_biz_email_cb.setChecked(
            self.settings.get("mask_business_emails", False)
        )
        self.mask_biz_email_cb.setStyleSheet(
            "font-family: 'Segoe UI'; font-size: 12px;"
        )
        mask_layout.addWidget(self.mask_biz_email_cb)

        self.mask_biz_phone_cb = QCheckBox(
            "Mask business contact phone number by default", mask_box
        )
        self.mask_biz_phone_cb.setChecked(
            self.settings.get("mask_business_phone", False)
        )
        self.mask_biz_phone_cb.setStyleSheet(
            "font-family: 'Segoe UI'; font-size: 12px;"
        )
        mask_layout.addWidget(self.mask_biz_phone_cb)

        self.mask_client_email_cb = QCheckBox(
            "Mask client contact emails by default", mask_box
        )
        self.mask_client_email_cb.setChecked(
            self.settings.get("mask_client_emails", False)
        )
        self.mask_client_email_cb.setStyleSheet(
            "font-family: 'Segoe UI'; font-size: 12px;"
        )
        mask_layout.addWidget(self.mask_client_email_cb)

        mask_hint = QLabel(
            "When enabled, sensitive contact details (emails, phone) are masked on the generated invoice. You can override these per-invoice.",
            mask_box,
        )
        mask_hint.setWordWrap(True)
        mask_hint.setStyleSheet(
            "color: #64748B; font-size: 10px; font-family: 'Segoe UI';"
        )
        mask_layout.addWidget(mask_hint)

        scroll_invoice_layout.addWidget(mask_box)

        scroll_invoice.setWidget(scroll_invoice_content)
        ti_layout.addWidget(scroll_invoice)

        settings_tabs.addTab(tab_general, "General && Controls")
        settings_tabs.addTab(tab_invoice, "Billing && Invoices")
        layout.addWidget(settings_tabs)

        # Bottom Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        save_btn = QPushButton("Save Settings", self)
        save_btn.setObjectName("AccentButton")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self._save_and_close)
        btn_layout.addWidget(save_btn)

        cancel_btn = QPushButton("Cancel", self)
        cancel_btn.setObjectName("NormalButton")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    def _toggle_bank_inputs(self, checked):
        self.bank_holder_entry.setEnabled(checked)
        self.bank_account_entry.setEnabled(checked)
        self.bank_routing_entry.setEnabled(checked)
        self.bank_swift_entry.setEnabled(checked)
        self.bank_name_entry.setEnabled(checked)
        self.bank_address_entry.setEnabled(checked)

    def _toggle_logo_inputs(self, checked):
        self.logo_path_entry.setEnabled(checked)
        self.browse_logo_btn.setEnabled(checked)
        self.logo_spec_lbl.setEnabled(checked)

    def _refresh_qr_thumbnails(self):
        """Rebuild QR thumbnail strip from _qr_paths_local."""
        while self.qr_thumbs_layout.count() > 0:
            item = self.qr_thumbs_layout.takeAt(0)
            if item:
                widget = item.widget()
                if widget:
                    widget.deleteLater()
                del item
        self._qr_thumb_refs.clear()

        qr_dir = os.path.join(get_app_data_dir(), "qr_codes")
        for qr_filename in self._qr_paths_local:
            qr_full_path = os.path.join(qr_dir, qr_filename)
            if not os.path.exists(qr_full_path):
                continue

            initial_url = self._qr_links_local.get(qr_filename, "")

            def _remove_qr(fname=qr_filename):
                logger.info(f"[Action] Removed payment QR code: {fname}")
                if fname in self._qr_paths_local:
                    self._qr_paths_local.remove(fname)
                self._qr_links_local.pop(fname, None)
                QTimer.singleShot(0, self._refresh_qr_thumbnails)

            def _link_changed(fname, new_url):
                if new_url:
                    self._qr_links_local[fname] = new_url
                else:
                    self._qr_links_local.pop(fname, None)

            thumb_widget = QRThumbnailWidget(
                qr_filename=qr_filename,
                qr_full_path=qr_full_path,
                initial_url=initial_url,
                on_remove=lambda checked=False, fname=qr_filename: _remove_qr(fname),
                on_link_changed=_link_changed,
                parent=self.qr_thumbs_widget,
            )

            self.qr_thumbs_layout.addWidget(thumb_widget)
            self._qr_thumb_refs.append(thumb_widget)

        self.qr_thumbs_layout.addStretch()

    def _save_and_close(self):
        try:
            logger.info("[Action] Adjusted Settings:")
            logger.info(f"  - Confirm close: {self.cb_confirm.isChecked()}")
            logger.info(f"  - Min track seconds: {self.min_sec_entry.text()}")
            logger.info(f"  - Auto-save seconds: {self.auto_save_entry.text()}")
            logger.info(f"  - Hourly rate: {self.rate_entry.text()}")
            logger.info(f"  - Developer mode: {self.cb_dev.isChecked()}")

            self.settings["confirm_on_close"] = self.cb_confirm.isChecked()
            self.settings["min_track_seconds"] = int(self.min_sec_entry.text())
            self.settings["auto_save_seconds"] = int(self.auto_save_entry.text())

            # (Focus goals settings are managed directly in the Web Dashboard)

            raw_symbol = self.curr_combo.currentText().strip()
            self.settings["currency_symbol"] = (
                raw_symbol.split()[0].split("(")[0].strip() if raw_symbol else "$"
            )
            self.settings["hourly_rate"] = float(self.rate_entry.text().strip() or 0)

            _im = max(0, int(self.idle_min_entry.text().strip() or 0))
            _is = max(0, min(59, int(self.idle_sec_entry.text().strip() or 0)))
            self.settings["idle_threshold_seconds_total"] = _im * 60 + _is

            self.settings["business_name"] = self.business_name_entry.text().strip()
            self.settings["business_emails"] = self.business_email_chips.get_emails()
            self.settings["business_phone"] = self.business_phone_entry.text().strip()
            self.settings["business_address"] = (
                self.business_address_entry.text().strip()
            )
            self.settings["business_payment"] = (
                self.business_payment_entry.text().strip()
            )

            self.settings["enable_bank_details"] = self.enable_bank_cb.isChecked()
            self.settings["bank_holder"] = self.bank_holder_entry.text().strip()
            self.settings["bank_account"] = self.bank_account_entry.text().strip()
            self.settings["bank_routing"] = self.bank_routing_entry.text().strip()
            self.settings["bank_swift"] = self.bank_swift_entry.text().strip()
            self.settings["bank_name"] = self.bank_name_entry.text().strip()
            self.settings["bank_address"] = self.bank_address_entry.text().strip()

            self.settings["client_name"] = self.client_name_entry.text().strip()
            self.settings["client_emails"] = self.client_email_chips.get_emails()
            self.settings["client_address"] = self.client_address_entry.text().strip()

            self.settings["enable_business_logo"] = self.enable_logo_cb.isChecked()
            self.settings["business_logo_path"] = self.logo_path_entry.text().strip()
            self.settings["qr_code_paths"] = list(self._qr_paths_local)
            self.settings["qr_code_links"] = dict(self._qr_links_local)

            self.settings["mask_business_emails"] = self.mask_biz_email_cb.isChecked()
            self.settings["mask_business_phone"] = self.mask_biz_phone_cb.isChecked()
            self.settings["mask_client_emails"] = self.mask_client_email_cb.isChecked()
            self.settings["mask_sensitive_data"] = (
                self.settings["mask_business_emails"]
                or self.settings["mask_business_phone"]
                or self.settings["mask_client_emails"]
            )
            self.settings["developer_mode"] = self.cb_dev.isChecked()
            theme_text = self.theme_combo.currentText()
            if theme_text == "Light":
                self.settings["theme_style"] = "light"
            elif theme_text == "Classic Dark":
                self.settings["theme_style"] = "classic-dark"
            else:
                self.settings["theme_style"] = "modern-dark"
            self.settings["dark_mode"] = self.settings["theme_style"] in [
                "modern-dark",
                "classic-dark",
            ]
            self.settings["enable_distraction_auto_pause"] = (
                self.cb_distract.isChecked()
            )
            self.settings["distraction_apps"] = list(self._distraction_apps_local)
            if hasattr(self, "cb_drive_auto"):
                self.settings["google_drive_auto_sync"] = self.cb_drive_auto.isChecked()

            self.settings_saved.emit(self.settings)
            self.accept()
        except ValueError:
            QMessageBox.critical(self, "Error", "Please enter valid numeric values.")

    def _on_profile_combo_changed(self, text):
        if text != self.active_profile:
            self.profile_changed.emit(text)
            self.accept()

    def _on_new_profile_clicked(self):
        name, ok = QInputDialog.getText(
            self, "New Profile", "Enter profile name:", QLineEdit.EchoMode.Normal, ""
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        # Clean profile name validation
        if not all(c.isalnum() or c in " _-" for c in name):
            QMessageBox.critical(
                self,
                "Invalid Name",
                "Profile name can only contain alphanumeric characters, spaces, hyphens, or underscores.",
            )
            return

        if name in self.profiles_list:
            QMessageBox.critical(
                self, "Already Exists", f"A profile named '{name}' already exists."
            )
            return

        # Update config directly
        root_dir = get_app_data_root()
        profiles_file = os.path.join(root_dir, "profiles.json")
        try:
            self.profiles_list.append(name)
            with open(profiles_file, "w", encoding="utf-8") as f:
                json.dump(
                    {"active_profile": name, "profiles": self.profiles_list},
                    f,
                    indent=4,
                )
            self.profile_changed.emit(name)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create profile:\n{e}")

    def _on_rename_profile_clicked(self):
        name, ok = QInputDialog.getText(
            self,
            "Rename Profile",
            f"Enter new name for profile '{self.active_profile}':",
            QLineEdit.EchoMode.Normal,
            self.active_profile,
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        if name == self.active_profile:
            return
        if not all(c.isalnum() or c in " _-" for c in name):
            QMessageBox.critical(
                self,
                "Invalid Name",
                "Profile name can only contain alphanumeric characters, spaces, hyphens, or underscores.",
            )
            return

        if name in self.profiles_list:
            QMessageBox.critical(
                self, "Already Exists", f"A profile named '{name}' already exists."
            )
            return

        self.profile_renamed.emit(self.active_profile, name)
        self.accept()

    def _on_delete_profile_clicked(self):
        if len(self.profiles_list) <= 1:
            QMessageBox.critical(
                self, "Action Prohibited", "You must keep at least one active profile."
            )
            return

        confirm = QMessageBox.question(
            self,
            "Delete Profile",
            f"Are you sure you want to permanently delete profile '{self.active_profile}' and ALL of its session logs?\n\nThis action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.profile_deleted.emit(self.active_profile)
            self.accept()

    def _on_backup_clicked(self):
        from datetime import datetime
        from core.backup_manager import backup_settings, backup_workspace

        theme_style = self.settings.get("theme_style", "modern-dark")
        type_dialog = BackupTypeDialog(theme_style, active_profile=self.active_profile, parent=self)
        if (
            type_dialog.exec() != QDialog.DialogCode.Accepted
            or not type_dialog.selected_type
        ):
            return

        password = None
        if type_dialog.selected_type == "encrypted":
            pwd1, ok1 = QInputDialog.getText(
                self,
                "Backup Password",
                "Enter a password to encrypt your banking details (min 4 characters):",
                QLineEdit.EchoMode.Password,
                "",
            )
            if not ok1:
                return
            if not pwd1 or len(pwd1) < 4:
                QMessageBox.critical(
                    self,
                    "Invalid Password",
                    "Password must be at least 4 characters long.",
                )
                return

            pwd2, ok2 = QInputDialog.getText(
                self,
                "Confirm Password",
                "Re-enter password to confirm:",
                QLineEdit.EchoMode.Password,
                "",
            )
            if not ok2 or pwd1 != pwd2:
                QMessageBox.critical(
                    self,
                    "Passwords Mismatch",
                    "Passwords do not match. Backup aborted.",
                )
                return
            password = pwd1

        scope = getattr(type_dialog, "selected_scope", "workspace")
        if scope == "workspace":
            default_name = f"backup_all_profiles_{datetime.now().strftime('%Y%m%d_%H%M%S')}.truehour"
            title_text = "Backup Entire Workspace (All Profiles)"
        else:
            default_name = f"backup_{self.active_profile}_{datetime.now().strftime('%Y%m%d')}.truehour"
            title_text = f"Backup Profile '{self.active_profile}'"

        dest_path, _ = QFileDialog.getSaveFileName(
            self,
            title_text,
            default_name,
            "TrueHour Backup Files (*.truehour)",
        )
        if not dest_path:
            return

        if not dest_path.endswith(".truehour"):
            dest_path += ".truehour"

        if scope == "workspace":
            success = backup_workspace(dest_path, password=password)
        else:
            anon_user_id = self.settings.get("anonymous_user_id", "")
            success = backup_settings(
                dest_path, self.active_profile, password, anon_user_id
            )

        if success:
            enc_msg = (
                "Encrypted backup created successfully! Banking credentials are password-protected."
                if password
                else "Backup created successfully! Sensitive banking details were safely excluded."
            )
            QMessageBox.information(
                self,
                "Backup Successful",
                f"{enc_msg}\n\nFile location:\n{dest_path}",
            )
        else:
            QMessageBox.critical(
                self,
                "Backup Failed",
                "An error occurred while compiling and writing the backup archive.",
            )

    def _on_import_clicked(self):
        from core.backup_manager import import_workspace

        src_path, _ = QFileDialog.getOpenFileName(
            self, "Import Backup Archive", "", "TrueHour Backup Files (*.truehour)"
        )
        if not src_path or not os.path.exists(src_path):
            return

        res = import_workspace(src_path, password=None, strip_if_encrypted=False)
        status = res.get("status")

        if status == "password_required":
            password, ok = QInputDialog.getText(
                self,
                "Encrypted Backup Detected",
                "This backup is encrypted. Please enter the password to restore:",
                QLineEdit.EchoMode.Password,
                "",
            )
            if not ok:
                return
            res = import_workspace(src_path, password=password)
            status = res.get("status")

            while status == "wrong_password":
                retry = QMessageBox.question(
                    self,
                    "Incorrect Password",
                    "Incorrect password entered. Would you like to try again?\n\n(Click 'No' to import without sensitive banking details, or 'Cancel' to abort)",
                    QMessageBox.StandardButton.Yes
                    | QMessageBox.StandardButton.No
                    | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Yes,
                )
                if retry == QMessageBox.StandardButton.Yes:
                    password, ok = QInputDialog.getText(
                        self,
                        "Enter Backup Password",
                        "Enter the password to decrypt banking details:",
                        QLineEdit.EchoMode.Password,
                        "",
                    )
                    if not ok:
                        return
                    res = import_workspace(src_path, password=password)
                    status = res.get("status")
                elif retry == QMessageBox.StandardButton.No:
                    res = import_workspace(src_path, password=None, strip_if_encrypted=True)
                    status = res.get("status")
                else:
                    return

        if status in ["success", "banking_stripped"]:
            restored_profiles = res.get("restored_profiles", [self.active_profile])
            total_s = res.get("total_sessions", 0)
            active_p = res.get("active_profile", self.active_profile)
            msg_extra = " Note that sensitive banking details were stripped or omitted." if status == "banking_stripped" else ""
            QMessageBox.information(
                self,
                "Import Successful",
                f"Backup restored successfully!{msg_extra}\n\n"
                f"Restored {total_s} session(s) across profile(s): {', '.join(restored_profiles)}.",
            )
            self.settings_imported.emit(active_p)
            self.accept()
        else:
            QMessageBox.critical(
                self,
                "Import Failed",
                "Failed to restore backup archive. Please ensure the file is a valid TrueHour backup.",
            )

    def _on_browse_files_clicked(self):
        try:
            open_file(get_app_data_dir())
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open data directory:\n{e}")

    # ── Google Drive Sync Handlers ─────────────────────────────────────
    def _update_drive_ui(self, user_info=None):
        authenticated = drive_sync.is_authenticated()
        if authenticated:
            if user_info and isinstance(user_info, dict) and user_info.get("email"):
                self._cached_drive_user_info = user_info
            else:
                stored = drive_sync.get_stored_user_info()
                if stored and stored.get("email"):
                    self._cached_drive_user_info = stored
                elif not hasattr(self, "_cached_drive_user_info"):
                    self._cached_drive_user_info = {}

            email = self._cached_drive_user_info.get("email")
            if not email or email in ["Google Account", "Connected Account"]:
                stored = drive_sync.get_stored_user_info()
                email = stored.get("email") or "Google Account"

            self.drive_status_lbl.setText(f"Connected: {email} (Workspace Sync Active)")
            self.drive_status_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 12px; font-weight: bold; color: #16A34A;")
            self.btn_drive_auth.setVisible(False)
            if hasattr(self, "drive_actions_widget"):
                self.drive_actions_widget.setVisible(True)
            self.btn_drive_sync.setVisible(True)
            self.btn_drive_restore.setVisible(True)
            if hasattr(self, "btn_drive_history"):
                self.btn_drive_history.setVisible(True)
            self.btn_drive_signout.setVisible(True)
            self.cb_drive_auto.setEnabled(True)
        else:
            self._cached_drive_user_info = {}
            self.drive_status_lbl.setText("Status: Not connected to Google Drive")
            self.drive_status_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 12px; color: #64748B;")
            self.btn_drive_auth.setVisible(True)
            if hasattr(self, "drive_actions_widget"):
                self.drive_actions_widget.setVisible(False)
            self.btn_drive_sync.setVisible(False)
            self.btn_drive_restore.setVisible(False)
            if hasattr(self, "btn_drive_history"):
                self.btn_drive_history.setVisible(False)
            self.btn_drive_signout.setVisible(False)
            self.cb_drive_auto.setEnabled(False)

    def _on_drive_auth_clicked(self):
        self.drive_status_lbl.setText("Opening browser to authorize with Google...")
        self.btn_drive_auth.setEnabled(False)
        self._auth_worker = DriveAuthWorker(self)
        self._auth_worker.finished.connect(self._on_drive_auth_finished)
        self._auth_worker.start()

    def _on_drive_auth_finished(self, success, user_info, err_msg):
        self.btn_drive_auth.setEnabled(True)
        if success:
            self._update_drive_ui(user_info)
            QMessageBox.information(
                self,
                "Google Drive Connected",
                f"Successfully signed in as {user_info.get('email', 'Google Account')}!\n\nAll profiles will now sync seamlessly with Google Drive.",
            )
        else:
            self._update_drive_ui()
            QMessageBox.warning(
                self,
                "Google Login Failed",
                f"Could not sign in with Google:\n{err_msg}",
            )

    def _on_drive_sync_clicked(self):
        self.drive_status_lbl.setText("Compressing & uploading workspace (all profiles)...")
        self.btn_drive_sync.setEnabled(False)
        self._sync_worker = DriveSyncWorker(self.active_profile, force=False, parent=self)
        self._sync_worker.progress.connect(
            lambda msg: self.drive_status_lbl.setText(msg)
        )
        self._sync_worker.finished.connect(self._on_drive_sync_finished)
        self._sync_worker.safety_blocked.connect(self._on_drive_sync_blocked)
        self._sync_worker.start()

    def _on_drive_sync_blocked(self, preflight_data):
        self.btn_drive_sync.setEnabled(True)
        status = preflight_data.get("status")
        remote_sessions = preflight_data.get("remote_sessions", 0)
        remote_size = preflight_data.get("remote_size", 0)
        local_sessions = preflight_data.get("local_sessions", 0)

        if status == "prompt_restore":
            choice = QMessageBox.question(
                self,
                "Cloud Backup Detected",
                (
                    f"Google Drive has an existing backup with {remote_sessions} sessions ({remote_size:,} bytes), "
                    "but your local machine has 0 sessions.\n\n"
                    "Would you like to RESTORE from Google Drive now to recover your data?\n\n"
                    "(Click 'No' if you explicitly want to overwrite the cloud with an empty workspace)"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if choice == QMessageBox.StandardButton.Yes:
                self._on_drive_restore_clicked()
                return

            force_confirm = QMessageBox.question(
                self,
                "Confirm Cloud Overwrite",
                "Are you absolutely certain you want to OVERWRITE the existing cloud backup with your empty local workspace?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if force_confirm == QMessageBox.StandardButton.Yes:
                self._force_drive_sync()
        elif status == "conflict_deficit":
            choice = QMessageBox.question(
                self,
                "Cloud Backup Conflict",
                (
                    f"Your cloud backup has {remote_sessions} sessions, while this local machine only has {local_sessions} sessions.\n\n"
                    "Uploading now could cause data loss on the cloud. Do you want to FORCE upload anyway?"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if choice == QMessageBox.StandardButton.Yes:
                self._force_drive_sync()

    def _force_drive_sync(self):
        self.drive_status_lbl.setText("Force uploading workspace archive...")
        self.btn_drive_sync.setEnabled(False)
        self._sync_worker = DriveSyncWorker(self.active_profile, force=True, parent=self)
        self._sync_worker.progress.connect(lambda msg: self.drive_status_lbl.setText(msg))
        self._sync_worker.finished.connect(self._on_drive_sync_finished)
        self._sync_worker.start()

    def _on_drive_sync_finished(self, success, result, err_msg):
        self.btn_drive_sync.setEnabled(True)
        self._update_drive_ui(result)
        if success:
            archive_name = result.get("archive_name", "backup archive")
            tot_s = result.get("total_sessions", 0)
            self.drive_status_lbl.setText(
                f"✓ Uploaded {archive_name} ({tot_s} sessions) at {result.get('last_sync', '')}"
            )
            QMessageBox.information(
                self,
                "Cloud Sync Complete",
                f"Successfully backed up entire workspace ({tot_s} sessions across all profiles) to Google Drive!\n\nArchive: {archive_name}",
            )
        else:
            QMessageBox.warning(self, "Cloud Sync Blocked/Failed", f"Sync message:\n{err_msg}")

    def _on_drive_restore_clicked(self, file_id=None, revision_id=None):
        if hasattr(self.parent(), "tracker") and getattr(self.parent().tracker, "running", False):
            QMessageBox.warning(
                self,
                "Active Tracking Session",
                "Please stop the current active tracking session before restoring from cloud backup.",
            )
            return

        confirm = QMessageBox.question(
            self,
            "Restore Workspace from Cloud?",
            "Restoring from Google Drive will download your multi-profile cloud backup and restore all profiles, sessions, and databases.\n\nA local safety snapshot will automatically be created before restoring.\n\nDo you want to proceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.drive_status_lbl.setText("Downloading cloud backup archive...")
        self.btn_drive_restore.setEnabled(False)
        self._restore_worker = DriveRestoreWorker(
            profile_name=self.active_profile,
            file_id=file_id,
            revision_id=revision_id,
            parent=self,
        )
        self._restore_worker.progress.connect(
            lambda msg: self.drive_status_lbl.setText(msg)
        )
        self._restore_worker.finished.connect(self._on_drive_restore_finished)
        self._restore_worker.start()

    def _on_drive_restore_finished(self, success, result, err_msg):
        self.btn_drive_restore.setEnabled(True)
        self._update_drive_ui()
        if success:
            restored = result.get("restored_profiles", [])
            tot = result.get("total_sessions", 0)
            active_p = result.get("active_profile", self.active_profile)
            QMessageBox.information(
                self,
                "Cloud Restore Successful",
                f"Successfully restored workspace from Google Drive cloud backup!\n\n"
                f"Restored {tot} sessions across {len(restored)} profile(s): {', '.join(restored)}.\n\n"
                "All preferences, sessions, and databases are up to date.",
            )
            self.settings_imported.emit(active_p)
            self.accept()
        else:
            QMessageBox.critical(
                self,
                "Cloud Restore Failed",
                f"Failed to restore workspace from Google Drive:\n{err_msg}",
            )

    def _on_drive_history_clicked(self):
        theme_style = self.settings.get("theme_style", "modern-dark")
        history_dlg = CloudRevisionsDialog(theme_style, parent=self)
        history_dlg.restore_requested.connect(
            lambda rev_id: self._on_drive_restore_clicked(revision_id=rev_id)
        )
        history_dlg.exec()

    def _on_drive_signout_clicked(self):
        drive_sync.sign_out()
        self._update_drive_ui()
        QMessageBox.information(
            self, "Signed Out", "Successfully signed out of Google Drive."
        )

