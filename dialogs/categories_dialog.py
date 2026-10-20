"""
TrueHour — Manage Categories & Assigned Applications Dialog
Modern Master-Detail modal dialog for viewing, adding, modifying, and reassigning
applications across tracking categories without needing to start a live session first.
"""

import os
import logging
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QWidget,
    QFrame,
    QPushButton,
    QLineEdit,
    QComboBox,
    QMessageBox,
    QCompleter,
    QSplitter,
    QSizePolicy,
)
import json
import shutil
from PyQt6.QtGui import QFont, QPixmap, QPainter, QColor, QBrush

from theme import apply_dialog_theme, get_theme_colors, get_tag_color
from widgets.ui_utils import center_window
from utils.icon_utils import get_native_icon_pixmap
from config import get_app_data_dir

logger = logging.getLogger(__name__)

ALL_APPS_ID = "__ALL_APPS__"
 
class NoWheelComboBox(QComboBox):
    def wheelEvent(self, e):
        e.ignore()


class CategoriesDialog(QDialog):
    """
    Master-detail dialog allowing users to:
    1. View all categories with assigned app count badges.
    2. Select any category to view all assigned applications.
    3. Add new applications directly to categories (with autocompletion).
    4. Reassign applications between categories via an inline dropdown.
    5. Remove applications from categories.
    6. Add and remove custom categories.
    """

    categories_changed = pyqtSignal()

    def __init__(self, tracker, theme_style: str = "light", parent=None):
        super().__init__(parent)
        self.tracker = tracker
        self.theme_style = theme_style
        self._selected_category = ALL_APPS_ID
        self._category_search_filter = ""
        self._app_search_filter = ""

        self.setWindowTitle("Manage Categories & Assigned Applications")
        center_window(self, 940, 620)
        self.setMinimumSize(840, 520)
        self.setModal(True)

        self._known_exe_paths = self._build_known_exe_cache()
        self._icon_cache = {}

        apply_dialog_theme(self, self.theme_style)
        self._colors = get_theme_colors(self.theme_style)
        self._is_dark = self.theme_style in ["modern-dark", "classic-dark"]

        self._init_ui()
        self._refresh_all()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        # ── Header ──────────────────────────────────────────────────────────
        header_row = QHBoxLayout()
        header_text_layout = QVBoxLayout()
        header_text_layout.setSpacing(3)

        title = QLabel("🏷️ Manage Categories & Assigned Applications", self)
        title.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 16px; font-weight: bold; color: {self._colors['text_primary']};"
        )
        subtitle = QLabel(
            "Configure categories and assign your applications directly before starting tracking.",
            self,
        )
        subtitle.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 12px; color: {self._colors['text_secondary']};"
        )

        header_text_layout.addWidget(title)
        header_text_layout.addWidget(subtitle)
        header_row.addLayout(header_text_layout, 1)

        main_layout.addLayout(header_row)

        # ── Splitter Body ───────────────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet(
            f"QSplitter::handle {{ background-color: {self._colors['border_color']}; }}"
        )

        # ── Left Pane: Categories List & Add Category ───────────────────────
        left_widget = QWidget(self)
        left_widget.setMinimumWidth(260)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(8)

        left_header = QLabel("CATEGORIES", left_widget)
        left_header.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 11px; font-weight: bold; letter-spacing: 0.5px; color: {self._colors['text_secondary']};"
        )
        left_layout.addWidget(left_header)

        # Filter categories
        self.cat_filter_entry = QLineEdit(left_widget)
        self.cat_filter_entry.setPlaceholderText("🔍 Filter categories...")
        self.cat_filter_entry.textChanged.connect(self._on_category_filter_changed)
        self.cat_filter_entry.setFixedHeight(28)
        left_layout.addWidget(self.cat_filter_entry)

        # Scrollable categories list
        cat_scroll = QScrollArea(left_widget)
        cat_scroll.setWidgetResizable(True)
        cat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        cat_scroll.setObjectName("AppListCard")
        cat_scroll.setStyleSheet("QScrollArea { border: 1px solid transparent; }")
        self.cat_scroll_content = QWidget()
        self.cat_scroll_layout = QVBoxLayout(self.cat_scroll_content)
        self.cat_scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.cat_scroll_layout.setSpacing(4)
        cat_scroll.setWidget(self.cat_scroll_content)
        left_layout.addWidget(cat_scroll, 1)

        # Add new category bar
        add_cat_box = QFrame(left_widget)
        add_cat_box.setStyleSheet(
            f"background-color: {self._colors['card_bg']}; border-radius: 6px; padding: 4px;"
        )
        add_cat_layout = QHBoxLayout(add_cat_box)
        add_cat_layout.setContentsMargins(4, 4, 4, 4)
        add_cat_layout.setSpacing(6)

        self.add_cat_entry = QLineEdit(add_cat_box)
        self.add_cat_entry.setPlaceholderText("New category...")
        self.add_cat_entry.returnPressed.connect(self._add_category)
        self.add_cat_entry.setFixedHeight(26)
        self.add_entry = self.add_cat_entry
        add_cat_layout.addWidget(self.add_cat_entry, 1)

        btn_add_cat = QPushButton("+ Add", add_cat_box)
        btn_add_cat.setObjectName("AccentButton")
        btn_add_cat.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add_cat.setFixedHeight(26)
        btn_add_cat.clicked.connect(self._add_category)
        add_cat_layout.addWidget(btn_add_cat)

        left_layout.addWidget(add_cat_box)

        splitter.addWidget(left_widget)

        # ── Right Pane: Assigned Apps Detail Canvas ─────────────────────────
        right_widget = QWidget(self)
        right_widget.setMinimumWidth(520)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(10, 0, 0, 0)
        right_layout.setSpacing(10)

        # Right Header: Selected Category Title & Stats
        self.detail_header = QLabel("All Applications", right_widget)
        self.detail_header.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 15px; font-weight: bold; color: {self._colors['text_primary']};"
        )
        self.detail_subtitle = QLabel("Overview of all application assignments", right_widget)
        self.detail_subtitle.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 12px; color: {self._colors['text_secondary']};"
        )

        header_box = QVBoxLayout()
        header_box.setSpacing(2)
        header_box.addWidget(self.detail_header)
        header_box.addWidget(self.detail_subtitle)
        right_layout.addLayout(header_box)

        # Add / Assign App Action Card
        assign_card = QFrame(right_widget)
        assign_card.setStyleSheet(
            f"background-color: {self._colors['card_bg']}; border: 1px solid {self._colors['border_color']}; border-radius: 8px;"
        )
        assign_layout = QVBoxLayout(assign_card)
        assign_layout.setContentsMargins(10, 10, 10, 10)
        assign_layout.setSpacing(6)

        assign_title = QLabel("ASSIGN AN APPLICATION", assign_card)
        assign_title.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 10px; font-weight: bold; letter-spacing: 0.5px; color: {self._colors['text_secondary']};"
        )
        assign_layout.addWidget(assign_title)

        assign_row = QHBoxLayout()
        assign_row.setSpacing(8)

        self.app_name_entry = QLineEdit(assign_card)
        self.app_name_entry.setPlaceholderText("Enter or select application name (e.g. code, figma, chrome)...")
        self.app_name_entry.setFixedHeight(30)
        self.app_name_entry.returnPressed.connect(self._assign_entered_app)
        assign_row.addWidget(self.app_name_entry, 1)

        # Target category combo for assignment
        self.target_cat_combo = NoWheelComboBox(assign_card)
        self.target_cat_combo.setFixedHeight(30)
        self.target_cat_combo.setMinimumWidth(130)
        assign_row.addWidget(self.target_cat_combo)

        btn_assign = QPushButton("Assign to Category", assign_card)
        btn_assign.setObjectName("AccentButton")
        btn_assign.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_assign.setFixedHeight(30)
        btn_assign.clicked.connect(self._assign_entered_app)
        assign_row.addWidget(btn_assign)

        assign_layout.addLayout(assign_row)
        right_layout.addWidget(assign_card)

        # Apps search and filter row
        apps_search_row = QHBoxLayout()
        self.app_filter_entry = QLineEdit(right_widget)
        self.app_filter_entry.setPlaceholderText("🔍 Search applications...")
        self.app_filter_entry.textChanged.connect(self._on_app_filter_changed)
        self.app_filter_entry.setFixedHeight(28)
        apps_search_row.addWidget(self.app_filter_entry, 1)

        self.app_count_lbl = QLabel("0 apps", right_widget)
        self.app_count_lbl.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 12px; font-weight: 600; color: {self._colors['text_secondary']};"
        )
        apps_search_row.addWidget(self.app_count_lbl)
        right_layout.addLayout(apps_search_row)

        # Scrollable Assigned Apps List
        apps_scroll = QScrollArea(right_widget)
        apps_scroll.setWidgetResizable(True)
        apps_scroll.setObjectName("AppListCard")
        self.apps_scroll_content = QWidget()
        self.apps_scroll_layout = QVBoxLayout(self.apps_scroll_content)
        self.apps_scroll_layout.setContentsMargins(2, 2, 2, 2)
        self.apps_scroll_layout.setSpacing(4)
        apps_scroll.setWidget(self.apps_scroll_content)
        right_layout.addWidget(apps_scroll, 1)

        splitter.addWidget(right_widget)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([270, 650])

        main_layout.addWidget(splitter, 1)

        # ── Dialog Footer ───────────────────────────────────────────────────
        footer_row = QHBoxLayout()
        footer_row.addStretch()

        btn_close = QPushButton("Done", self)
        btn_close.setObjectName("NormalButton")
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setFixedWidth(90)
        btn_close.setFixedHeight(30)
        btn_close.clicked.connect(self.accept)
        footer_row.addWidget(btn_close)

        main_layout.addLayout(footer_row)

    # ── Refresh & Populate ──────────────────────────────────────────────────

    def _refresh_all(self):
        """Re-render both categories sidebar and the apps detail pane."""
        self._refresh_categories_sidebar()
        self._update_target_combo()
        self._refresh_apps_pane()
        self._setup_app_completer()

    def _refresh_categories_sidebar(self):
        """Render the left category navigation list."""
        while self.cat_scroll_layout.count():
            item = self.cat_scroll_layout.takeAt(0)
            if item:
                widget = item.widget()
                if widget:
                    widget.deleteLater()
                del item

        all_mappings = self.tracker.tag_manager.get_all_mapped_apps()
        total_mapped = len(all_mappings)

        # 1. Top "All Applications" navigation row
        all_row = self._create_category_nav_row(
            name="All Applications",
            color="#0078D4",
            count=total_mapped,
            is_all_item=True,
            is_selected=(self._selected_category == ALL_APPS_ID),
        )
        self.cat_scroll_layout.addWidget(all_row)

        # 2. Individual Categories
        projects = self.tracker.tag_manager.projects
        search_filter = self._category_search_filter.lower()

        for proj in projects:
            if search_filter and search_filter not in proj.lower():
                continue

            app_count = sum(1 for tag in all_mappings.values() if tag == proj)
            color = get_tag_color(proj)
            row = self._create_category_nav_row(
                name=proj,
                color=color,
                count=app_count,
                is_all_item=False,
                is_selected=(self._selected_category == proj),
            )
            self.cat_scroll_layout.addWidget(row)

        self.cat_scroll_layout.addStretch()

    def _create_category_nav_row(
        self, name: str, color: str, count: int, is_all_item: bool, is_selected: bool
    ) -> QFrame:
        row = QFrame(self.cat_scroll_content)
        row.setObjectName("CatNavRow")
        row.setFixedHeight(36)
        row.setCursor(Qt.CursorShape.PointingHandCursor)

        border_col = color if is_selected else "transparent"
        bg_col = (
            "#1E293B" if (self._is_dark and is_selected)
            else "#E0F2FE" if is_selected
            else "transparent"
        )
        hover_bg = "#262626" if self._is_dark else "#F1F5F9"

        row.setStyleSheet(f"""
            QFrame#CatNavRow {{
                background-color: {bg_col};
                border: 1px solid {border_col};
                border-radius: 6px;
            }}
            QFrame#CatNavRow:hover {{
                background-color: {hover_bg};
            }}
        """)

        layout = QHBoxLayout(row)
        layout.setContentsMargins(10, 0, 8, 0)
        layout.setSpacing(8)

        # Dot or icon
        dot_txt = "★" if is_all_item else "●"
        dot = QLabel(dot_txt, row)
        dot.setFixedWidth(14)
        dot.setStyleSheet(
            f"color: {color}; font-size: {13 if is_all_item else 13}px; font-weight: bold; background: none; border: none;"
        )
        dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(dot)

        # Category Name
        lbl_font_weight = "bold" if is_selected else "600"
        lbl = QLabel(name, row)
        lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        lbl.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 13px; font-weight: {lbl_font_weight}; color: {self._colors['text_primary']}; background: none; border: none;"
        )
        layout.addWidget(lbl, 1)

        # Count badge - fixed width & height so it's always prominently visible
        count_badge = QLabel(f"{count}", row)
        count_badge.setMinimumWidth(26)
        count_badge.setFixedHeight(20)
        count_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        count_badge.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        count_badge.setStyleSheet(f"""
            QLabel {{
                background-color: {'#334155' if self._is_dark else '#E2E8F0'};
                color: {self._colors['text_secondary']};
                border-radius: 9px;
                padding: 1px 6px;
                font-size: 11px;
                font-weight: 600;
                font-family: 'Segoe UI';
                border: none;
            }}
        """)
        layout.addWidget(count_badge)

        # Delete Category Button (only for custom categories, protecting default core pillars)
        default_cats = getattr(self.tracker.tag_manager, "DEFAULT_PROJECTS", ["Unassigned"])
        if not is_all_item and name not in default_cats:
            del_btn = QPushButton("✕", row)
            del_btn.setFixedSize(18, 18)
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_btn.setToolTip(f"Delete category '{name}'")
            del_hover = "#EF4444" if self._is_dark else "#DC2626"
            del_btn.setStyleSheet(f"""
                QPushButton {{
                    background: none;
                    border: none;
                    color: {self._colors['text_secondary']};
                    font-size: 11px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    color: #FFFFFF;
                    background-color: {del_hover};
                    border-radius: 9px;
                }}
            """)
            del_btn.clicked.connect(lambda checked=False, p=name: self._delete_category(p))
            layout.addWidget(del_btn)

        # Make entire row clickable
        def on_click(event):
            target_id = ALL_APPS_ID if is_all_item else name
            self._select_category(target_id)

        row.mousePressEvent = on_click
        return row

    def _select_category(self, category_name: str):
        self._selected_category = category_name
        self._refresh_categories_sidebar()
        self._update_target_combo()
        self._refresh_apps_pane()

    def _update_target_combo(self):
        """Keep the target category combo updated with available projects."""
        self.target_cat_combo.clear()
        projects = self.tracker.tag_manager.projects
        self.target_cat_combo.addItems(projects)

        if self._selected_category != ALL_APPS_ID and self._selected_category in projects:
            self.target_cat_combo.setCurrentText(self._selected_category)
        elif "Development" in projects:
            self.target_cat_combo.setCurrentText("Development")

    def _refresh_apps_pane(self):
        """Render the right pane displaying assigned applications."""
        while self.apps_scroll_layout.count():
            item = self.apps_scroll_layout.takeAt(0)
            if item:
                widget = item.widget()
                if widget:
                    widget.deleteLater()
                del item

        all_mappings = self.tracker.tag_manager.get_all_mapped_apps()
        filter_text = self._app_filter_entry_text().lower()

        # Update headers
        if self._selected_category == ALL_APPS_ID:
            self.detail_header.setText("★ All Configured Applications")
            self.detail_header.setStyleSheet(
                f"font-family: 'Segoe UI'; font-size: 15px; font-weight: bold; color: {self._colors['text_primary']};"
            )
            self.detail_subtitle.setText(f"Showing all {len(all_mappings)} mapped applications across all categories.")
            apps_to_display = [(app, tag) for app, tag in all_mappings.items()]
        else:
            cat_name = self._selected_category
            color = get_tag_color(cat_name)
            self.detail_header.setText(f"● {cat_name}")
            self.detail_header.setStyleSheet(
                f"font-family: 'Segoe UI'; font-size: 16px; font-weight: bold; color: {color};"
            )
            apps_to_display = [(app, tag) for app, tag in all_mappings.items() if tag == cat_name]
            self.detail_subtitle.setText(
                f"Showing {len(apps_to_display)} application(s) categorized under '{cat_name}'."
            )

        # Apply search filter
        if filter_text:
            apps_to_display = [
                (app, tag) for app, tag in apps_to_display if filter_text in app.lower() or filter_text in tag.lower()
            ]

        apps_to_display.sort(key=lambda t: t[0].lower())
        self.app_count_lbl.setText(f"{len(apps_to_display)} app{'s' if len(apps_to_display) != 1 else ''}")

        # Empty State
        if not apps_to_display:
            empty_frame = QFrame(self.apps_scroll_content)
            empty_frame.setStyleSheet(
                f"background: transparent; border: 1px dashed {self._colors['border_color']}; border-radius: 8px; padding: 24px;"
            )
            empty_layout = QVBoxLayout(empty_frame)
            empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            empty_icon = QLabel("📦", empty_frame)
            empty_icon.setStyleSheet("font-size: 30px;")
            empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_layout.addWidget(empty_icon)

            msg = (
                "No applications found matching search filter."
                if filter_text
                else f"No applications currently assigned to '{self._selected_category}'."
            )
            empty_lbl = QLabel(msg, empty_frame)
            empty_lbl.setStyleSheet(
                f"font-family: 'Segoe UI'; font-size: 13px; font-weight: 600; color: {self._colors['text_primary']}; margin-top: 6px;"
            )
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_layout.addWidget(empty_lbl)

            hint = QLabel("Type an application name above and click 'Assign to Category' to add one.", empty_frame)
            hint.setStyleSheet(
                f"font-family: 'Segoe UI'; font-size: 11px; color: {self._colors['text_secondary']};"
            )
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_layout.addWidget(hint)

            self.apps_scroll_layout.addWidget(empty_frame)
            self.apps_scroll_layout.addStretch()
            return

        # Render rows
        for app_name, current_tag in apps_to_display:
            row = self._create_app_row(app_name, current_tag)
            self.apps_scroll_layout.addWidget(row)

        self.apps_scroll_layout.addStretch()

    def _create_app_row(self, app_name: str, current_tag: str) -> QFrame:
        row = QFrame(self.apps_scroll_content)
        row.setObjectName("AppRow")
        row.setFixedHeight(40)
        row.setStyleSheet(f"""
            QFrame#AppRow {{
                background-color: {self._colors['card_bg']};
                border: 1px solid {self._colors['border_color']};
                border-radius: 6px;
            }}
            QFrame#AppRow:hover {{
                border-color: {get_tag_color(current_tag)};
            }}
        """)

        layout = QHBoxLayout(row)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(10)

        # App Icon (resolves smooth native icon or crisp vector category badge)
        icon_lbl = QLabel(row)
        icon_lbl.setObjectName("AppIcon")
        icon_lbl.setFixedSize(22, 22)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("background: transparent; border: none; padding: 0px; margin: 0px;")
        pix = self._get_app_icon(app_name, current_tag)
        if pix and not pix.isNull():
            icon_lbl.setPixmap(pix)
        else:
            icon_lbl.setPixmap(self._create_fallback_icon(get_tag_color(current_tag)))

        layout.addWidget(icon_lbl)

        # App Name
        name_lbl = QLabel(app_name, row)
        name_lbl.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 13px; font-weight: 600; color: {self._colors['text_primary']}; background: transparent; border: none; padding: 0px;"
        )
        layout.addWidget(name_lbl, 1)

        # Reassign Category ComboBox
        cat_combo = NoWheelComboBox(row)
        cat_combo.setFixedHeight(26)
        cat_combo.setMinimumWidth(130)
        projects = self.tracker.tag_manager.projects
        cat_combo.addItems(projects)
        if current_tag in projects:
            cat_combo.setCurrentText(current_tag)

        # Connect reassign handler with safety wrapper
        cat_combo.currentTextChanged.connect(
            lambda new_cat, app=app_name, old_cat=current_tag: self._reassign_app(app, old_cat, new_cat)
        )
        layout.addWidget(cat_combo)

        # Remove / Unassign Button
        del_btn = QPushButton("🗑", row)
        del_btn.setFixedSize(24, 24)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setToolTip(f"Remove '{app_name}' from categories")
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background: none;
                border: none;
                font-size: 12px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {'#3F1D1D' if self._is_dark else '#FEE2E2'};
            }}
        """)
        del_btn.clicked.connect(lambda checked=False, app=app_name: self._remove_app(app))
        layout.addWidget(del_btn)

        return row

    # ── Icon Resolution & Badging ───────────────────────────────────────────

    def _build_known_exe_cache(self) -> dict[str, str]:
        """Pre-populate executable paths from tracker and session history."""
        cache = {}
        if hasattr(self.tracker, "app_exe_paths"):
            for k, v in self.tracker.app_exe_paths.items():
                if v and os.path.exists(v):
                    cache[k.lower().strip()] = v

        try:
            sess_dir = os.path.join(get_app_data_dir(), "sessions")
            if os.path.exists(sess_dir):
                for f in os.listdir(sess_dir):
                    if f.endswith(".json"):
                        try:
                            with open(os.path.join(sess_dir, f), "r", encoding="utf-8") as fp:
                                data = json.load(fp)
                                for app, path in data.get("app_exe_paths", {}).items():
                                    k = app.lower().strip()
                                    if k not in cache and path and os.path.exists(path):
                                        cache[k] = path
                        except Exception:
                            pass
        except Exception as e:
            logger.debug("Failed reading session exe cache: %s", e)

        # Mirror back into tracker.app_exe_paths so other components benefit
        if hasattr(self.tracker, "app_exe_paths"):
            for k, v in cache.items():
                if k not in self.tracker.app_exe_paths:
                    self.tracker.app_exe_paths[k] = v

        return cache

    def _find_alive_path(self, p: str) -> str:
        if not p:
            return ""
        if os.path.exists(p):
            return p
        try:
            import glob

            parent = os.path.dirname(os.path.dirname(p))
            fname = os.path.basename(p)
            if os.path.exists(parent):
                cand = glob.glob(os.path.join(parent, "app-*", fname))
                if cand and os.path.exists(cand[-1]):
                    return cand[-1]
                direct = os.path.join(parent, fname)
                if os.path.exists(direct):
                    return direct
        except Exception:
            pass
        return ""

    def _resolve_app_exe_path(self, app_name: str) -> str:
        """Find executable path for an application name with fallbacks."""
        clean = app_name.lower().strip()
        if clean in self._known_exe_paths:
            alive = self._find_alive_path(self._known_exe_paths[clean])
            if alive:
                return alive

        if hasattr(self.tracker, "get_exe_path"):
            p = self.tracker.get_exe_path(app_name)
            if p:
                alive = self._find_alive_path(p)
                if alive:
                    self._known_exe_paths[clean] = alive
                    return alive

        # Check system PATH
        cand = shutil.which(clean)
        if cand and os.path.exists(cand):
            self._known_exe_paths[clean] = cand
            return cand

        if not clean.endswith(".exe"):
            cand = shutil.which(clean + ".exe")
            if cand and os.path.exists(cand):
                self._known_exe_paths[clean] = cand
                return cand

        return ""

    def _get_app_icon(self, app_name: str, current_tag: str) -> QPixmap:
        """Return crisp native icon or clean vector fallback badge."""
        cache_key = f"{app_name.lower().strip()}:{current_tag}"
        if cache_key in self._icon_cache:
            return self._icon_cache[cache_key]

        exe_path = self._resolve_app_exe_path(app_name)
        pix = get_native_icon_pixmap(exe_path, size=20) if exe_path else None
        if not pix or pix.isNull():
            pix = self._create_fallback_icon(get_tag_color(current_tag))

        self._icon_cache[cache_key] = pix
        return pix

    def _create_fallback_icon(self, color_hex: str) -> QPixmap:
        """Paint a crisp 20x20 vector circle badge with category accent color."""
        pix = QPixmap(20, 20)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        col = QColor(color_hex)
        painter.setBrush(QBrush(col))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(3, 3, 14, 14)
        painter.end()
        return pix

    def _setup_app_completer(self):
        """Populate autocompletion for quick app entry from discovered and keyword apps."""
        discovered = []
        if hasattr(self.tracker, "get_discovered_apps"):
            discovered = self.tracker.get_discovered_apps()
        if not discovered:
            discovered = list(self.tracker.tag_manager.mappings.keys())

        completer = QCompleter(discovered, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.app_name_entry.setCompleter(completer)

    # ── Action Handlers ─────────────────────────────────────────────────────

    def _assign_entered_app(self):
        """Assign the app name in the input box to the selected target category."""
        app_name = self.app_name_entry.text().strip()
        if not app_name:
            return

        target_cat = self.target_cat_combo.currentText().strip()
        if not target_cat:
            target_cat = "Development"

        logger.info(f"[CategoriesManager] Manually assigned '{app_name}' -> '{target_cat}'")
        self.tracker.tag_manager.set_tag(app_name, target_cat)
        self.app_name_entry.clear()
        self.categories_changed.emit()

        QTimer.singleShot(0, self._refresh_all)

    def _reassign_app(self, app_name: str, old_cat: str, new_cat: str):
        """Reassign an app to a different category via the dropdown."""
        if not new_cat or new_cat == old_cat:
            return

        logger.info(f"[CategoriesManager] Reassigned '{app_name}' from '{old_cat}' -> '{new_cat}'")
        self.tracker.tag_manager.set_tag(app_name, new_cat)
        self.categories_changed.emit()

        QTimer.singleShot(0, self._refresh_all)

    def _remove_app(self, app_name: str):
        """Remove explicit mapping for an application."""
        logger.info(f"[CategoriesManager] Removed mapping for '{app_name}'")
        self.tracker.tag_manager.remove_app_tag(app_name)
        self.categories_changed.emit()

        QTimer.singleShot(0, self._refresh_all)

    def _add_category(self):
        """Create a new custom category."""
        name = self.add_cat_entry.text().strip()
        if not name:
            return

        if name in self.tracker.tag_manager.projects:
            QMessageBox.critical(self, "Category Exists", f"Category '{name}' already exists.")
            return

        if self.tracker.tag_manager.add_project(name):
            self.add_cat_entry.clear()
            self._selected_category = name
            self.categories_changed.emit()
            QTimer.singleShot(0, self._refresh_all)

    def _delete_category(self, project: str, confirm: bool = True):
        """Delete custom category with user confirmation (optional)."""
        if confirm:
            reply = QMessageBox.question(
                self,
                "Delete Category",
                f"Are you sure you want to delete category '{project}'?\n\nAny applications assigned to this category will be moved to 'Unassigned'.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        if self.tracker.tag_manager.remove_project(project):
            if self._selected_category == project:
                self._selected_category = ALL_APPS_ID
            self.categories_changed.emit()
            QTimer.singleShot(0, self._refresh_all)

    # ── Backward Compatibility Aliases ──────────────────────────────────────

    def _add_project(self):
        """Compatibility alias for _add_category."""
        self._add_category()

    def _delete_project(self, project: str):
        """Compatibility alias for programmatic deletion without confirmation prompt."""
        self._delete_category(project, confirm=False)

    def _refresh_categories_list(self):
        """Compatibility alias for _refresh_all."""
        self._refresh_all()

    # ── Search Filters ──────────────────────────────────────────────────────

    def _on_category_filter_changed(self, text: str):
        self._category_search_filter = text.strip()
        self._refresh_categories_sidebar()

    def _on_app_filter_changed(self, text: str):
        self._refresh_apps_pane()

    def _app_filter_entry_text(self) -> str:
        return self.app_filter_entry.text().strip()
