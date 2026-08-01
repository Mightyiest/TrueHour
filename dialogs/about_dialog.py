"""
TrueHour — About Modal Dialog
Displays application version, build metadata, GitHub links, and terms.
"""

import os
import webbrowser
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QPushButton,
)

from version import INFO
from assets import GITHUB_SVG
from theme import get_svg_icon, apply_dialog_theme, get_theme_colors
from widgets.ui_utils import center_window


class AboutDialog(QDialog):
    """About dialog modal showing version metadata and repository links."""

    def __init__(self, theme_style: str = "light", parent=None):
        super().__init__(parent)
        self.theme_style = theme_style

        self.setWindowTitle("About TrueHour")
        center_window(self, 360, 310)
        self.setModal(True)

        apply_dialog_theme(self, self.theme_style)
        colors = get_theme_colors(self.theme_style)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("TrueHour", self)
        title.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 22px; font-weight: bold; color: {colors['text_primary']};"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        desc = QLabel("Automated Time Tracker & Productivity Assistant", self)
        desc.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 11px; color: {colors['text_secondary']}; font-weight: 500;"
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc)

        divider = QFrame(self)
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        divider.setStyleSheet(
            f"background-color: {colors['border_color']}; min-height: 1px; max-height: 1px; border: none;"
        )
        layout.addWidget(divider)

        details_layout = QVBoxLayout()
        details_layout.setSpacing(4)

        ver_lbl = QLabel(f"Version: {INFO.version}", self)
        ver_lbl.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 12px; color: {colors['text_primary']};"
        )
        ver_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        details_layout.addWidget(ver_lbl)

        build_lbl = QLabel(
            f"Build: {INFO.build_number} ({INFO.build_date})", self
        )
        build_lbl.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 12px; color: {colors['text_secondary']};"
        )
        build_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        details_layout.addWidget(build_lbl)

        layout.addLayout(details_layout)

        links_row = QHBoxLayout()
        links_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        links_row.setSpacing(12)

        github_btn = QPushButton(self)
        github_btn.setIcon(
            get_svg_icon(GITHUB_SVG, QSize(20, 20), color_hex=colors['text_primary'])
        )
        github_btn.setIconSize(QSize(20, 20))
        github_btn.setToolTip("Visit TrueHour on GitHub")
        github_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        github_btn.setFixedSize(32, 32)
        github_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {colors['btn_bg']};
                border: 1px solid {colors['btn_border']};
                border-radius: 16px;
                padding: 5px;
            }}
            QPushButton:hover {{
                background-color: {colors['btn_hover']};
                border-color: {colors['btn_border_hover']};
            }}
        """)
        github_btn.clicked.connect(
            lambda: webbrowser.open("https://mightyiest.github.io/TrueHour/")
        )
        links_row.addWidget(github_btn)

        legal_btn = QPushButton("Terms && Notices", self)
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
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            legal_path = os.path.join(base_dir, "templates", "about_legal.html")
            webbrowser.open(f"file:///{legal_path.replace('\\', '/')}")

        legal_btn.clicked.connect(open_legal)
        links_row.addWidget(legal_btn)

        layout.addLayout(links_row)
        layout.addSpacing(6)

        close_btn = QPushButton("Close", self)
        close_btn.setObjectName("AccentButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFixedHeight(32)
        close_btn.setStyleSheet("""
            QPushButton {
                border-radius: 16px;
                font-size: 12px;
            }
        """)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
