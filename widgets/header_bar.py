"""
TrueHour — HeaderBar Custom Widget
Top navigation bar widget housing theme toggle, dashboard, session manager, and settings controls.
"""

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QPushButton

from assets import SUN_SVG, SOLID_MOON_SVG
from theme import get_svg_icon, create_minimalist_icon


class HeaderBar(QFrame):
    """Top navigation frame with icon buttons for primary window controls."""

    def __init__(
        self, parent, cmd_report, cmd_sessions, cmd_settings, cmd_toggle_theme
    ):
        super().__init__(parent)
        self.setObjectName("HeaderBar")
        self.setFixedHeight(44)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(8)

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

        self.update_theme("light")

    def update_theme(self, theme_style=None, is_dark=None):
        if is_dark is not None:
            theme_style = is_dark
        if theme_style is None:
            theme_style = "light"
        if isinstance(theme_style, bool):
            theme_style = "modern-dark" if theme_style else "light"

        if theme_style == "classic-dark":
            neutral_color = "#aaa"
            self.theme_btn.setIcon(
                get_svg_icon(SUN_SVG, QSize(16, 16), color_hex="#d1d5db")
            )
            self.theme_btn.setToolTip("Switch to Light Mode")
        elif theme_style == "modern-dark":
            neutral_color = "#A3A3A3"
            self.theme_btn.setIcon(
                get_svg_icon(SOLID_MOON_SVG, QSize(16, 16), color_hex="#475569")
            )
            self.theme_btn.setToolTip("Switch to Classic Dark Mode")
        else:  # light
            neutral_color = "#475569"
            self.theme_btn.setIcon(
                get_svg_icon(SOLID_MOON_SVG, QSize(16, 16), color_hex="#2563EB")
            )
            self.theme_btn.setToolTip("Switch to Modern Dark Mode")

        self.live_report_btn.setIcon(create_minimalist_icon("chart", neutral_color))
        self.sessions_btn.setIcon(create_minimalist_icon("folder", neutral_color))
        self.settings_btn.setIcon(create_minimalist_icon("settings", neutral_color))

        self.live_report_btn.setStyleSheet(f"""
            QPushButton {{
                color: {neutral_color};
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
