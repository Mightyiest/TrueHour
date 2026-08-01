"""
TrueHour — Manage Categories Dialog
Modal dialog for managing custom category/project tags.
"""

import logging
from PyQt6.QtCore import Qt, pyqtSignal
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
    QMessageBox,
)

from theme import apply_dialog_theme, get_theme_colors, get_tag_color
from widgets.ui_utils import center_window

logger = logging.getLogger(__name__)


class CategoriesDialog(QDialog):
    """Modal dialog to view, add, and remove tracking categories."""

    categories_changed = pyqtSignal()

    def __init__(self, tracker, theme_style: str = "light", parent=None):
        super().__init__(parent)
        self.tracker = tracker
        self.theme_style = theme_style

        self.setWindowTitle("Manage Categories")
        center_window(self, 360, 440)
        self.setModal(True)

        apply_dialog_theme(self, self.theme_style)
        colors = get_theme_colors(self.theme_style)
        is_dark = self.theme_style in ["modern-dark", "classic-dark"]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)

        title = QLabel("Manage Categories", self)
        title.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 15px; font-weight: bold; color: {colors['text_primary']};"
        )
        layout.addWidget(title)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setObjectName("AppListCard")
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(4, 4, 4, 4)
        self.scroll_layout.setSpacing(2)

        scroll.setWidget(self.scroll_content)
        layout.addWidget(scroll)

        add_row = QHBoxLayout()
        self.add_entry = QLineEdit(self)
        self.add_entry.setPlaceholderText("New category name...")
        add_row.addWidget(self.add_entry, 1)

        add_btn = QPushButton("Add Category", self)
        add_btn.setObjectName("AccentButton")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._add_project)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)

        self._is_dark = is_dark
        self._lbl_color = colors['text_primary']
        self._refresh_categories_list()

    def _refresh_categories_list(self):
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()

        projects = self.tracker.tag_manager.projects
        for proj in projects:
            row = QFrame(self.scroll_content)
            row.setFixedHeight(30)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(6, 0, 6, 0)
            row_layout.setSpacing(6)

            color = get_tag_color(proj)
            dot = QLabel("●", row)
            dot.setStyleSheet(
                f"color: {color}; font-size: 14px; font-family: 'Segoe UI';"
            )
            row_layout.addWidget(dot, alignment=Qt.AlignmentFlag.AlignVCenter)

            lbl = QLabel(proj, row)
            lbl.setStyleSheet(
                f"font-family: 'Segoe UI'; font-size: 13px; color: {self._lbl_color};"
            )
            row_layout.addWidget(lbl, 1, alignment=Qt.AlignmentFlag.AlignVCenter)

            if proj != "Unassigned":
                del_btn = QPushButton("❌", row)
                del_btn.setFixedSize(20, 20)
                del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                del_btn_hover = "#333333" if self._is_dark else "#E9E9E9"
                del_btn.setStyleSheet(
                    f"QPushButton {{ background: none; border: none; font-size: 10px; }} QPushButton:hover {{ background-color: {del_btn_hover}; border-radius: 3px; }}"
                )
                del_btn.clicked.connect(
                    lambda checked, p=proj: self._delete_project(p)
                )
                row_layout.addWidget(del_btn)

            self.scroll_layout.addWidget(row)
        self.scroll_layout.addStretch()

    def _delete_project(self, project: str):
        if self.tracker.tag_manager.remove_project(project):
            self.categories_changed.emit()
            self._refresh_categories_list()

    def _add_project(self):
        name = self.add_entry.text().strip()
        if not name:
            return
        if name in self.tracker.tag_manager.projects:
            QMessageBox.critical(self, "Error", f"Category '{name}' already exists.")
            return
        if self.tracker.tag_manager.add_project(name):
            self.add_entry.clear()
            self.categories_changed.emit()
            self._refresh_categories_list()
