"""
TrueHour — Compact Session Save Dialog
Presents post-tracking summary modal to enter session name and save to history.
"""

import logging
from datetime import datetime
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QFrame,
    QPushButton,
    QMessageBox,
)

from assets import SHIELD_SVG
from report import save_to_history
from theme import get_svg_icon, apply_dialog_theme, get_theme_colors

logger = logging.getLogger(__name__)


class SaveSessionDialog(QDialog):
    """Compact session summary modal for naming and saving completed session."""

    def __init__(self, report: dict, theme_style: str = "light", parent=None):
        super().__init__(parent)
        self.report = report
        self.theme_style = theme_style

        self.setWindowTitle("Session Summary Report")
        self.setFixedSize(380, 380)

        apply_dialog_theme(self, self.theme_style)
        colors = get_theme_colors(self.theme_style)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        report_title = QLabel("Session Summary Report", self)
        report_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        report_title.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 18px; font-weight: 700; color: {colors['text_primary']};"
        )
        layout.addWidget(report_title)

        meta_lbl = QLabel(
            self.report.get("date_display", datetime.now().strftime("%B %d, %Y")), self
        )
        meta_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        meta_lbl.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 11px; color: {colors['text_secondary']}; margin-top: -6px;"
        )
        layout.addWidget(meta_lbl)

        name_input_layout = QVBoxLayout()
        name_input_layout.setSpacing(4)
        name_lbl = QLabel("Session Name", self)
        name_lbl.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 11px; font-weight: bold; color: {colors['text_secondary']};"
        )
        name_input_layout.addWidget(name_lbl)

        self.report_name_entry = QLineEdit(self)
        self.report_name_entry.setText(
            self.report.get("session_name", "").strip() or "Unnamed"
        )
        self.report_name_entry.setStyleSheet(f"""
            QLineEdit {{
                border: 1px solid {colors['border_color']};
                border-radius: 6px;
                padding: 8px 12px;
                background-color: {colors['bg_widget']};
                color: {colors['text_primary']};
                font-family: 'Segoe UI';
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border-color: {colors['accent_lbl_color']};
            }}
        """)
        name_input_layout.addWidget(self.report_name_entry)
        layout.addLayout(name_input_layout)

        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(10)

        card_time = QFrame(self)
        card_time.setStyleSheet(
            f"QFrame {{ background-color: {colors['earned_bg']}; border: 1px solid {colors['border_color']}; border-radius: 8px; }}"
        )
        ct_layout = QVBoxLayout(card_time)
        ct_layout.setContentsMargins(12, 12, 12, 12)
        ct_layout.setSpacing(4)

        time_val = QLabel(self.report.get("counted_formatted", "0s"), card_time)
        time_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        time_val.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 16px; font-weight: 700; color: {colors['text_primary']};"
        )
        ct_layout.addWidget(time_val)

        time_lbl = QLabel("Tracked Focus Time", card_time)
        time_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        time_lbl.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 10px; color: {colors['text_secondary']}; font-weight: 500;"
        )
        ct_layout.addWidget(time_lbl)
        stats_layout.addWidget(card_time)

        card_earned = QFrame(self)
        card_earned.setStyleSheet(
            f"QFrame {{ background-color: {colors['earned_bg']}; border: 1px solid {colors['border_color']}; border-radius: 8px; }}"
        )
        ce_layout = QVBoxLayout(card_earned)
        ce_layout.setContentsMargins(12, 12, 12, 12)
        ce_layout.setSpacing(4)

        earned_val = QLabel(
            self.report.get("total_earned_display", "$0.00"), card_earned
        )
        earned_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        earned_val.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 16px; font-weight: 700; color: {colors['earned_fg']};"
        )
        ce_layout.addWidget(earned_val)

        earned_lbl = QLabel("Total Earned", card_earned)
        earned_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        earned_lbl.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 10px; color: {colors['text_secondary']}; font-weight: 500;"
        )
        ce_layout.addWidget(earned_lbl)
        stats_layout.addWidget(card_earned)

        layout.addLayout(stats_layout)

        if self.theme_style in ["modern-dark", "classic-dark"]:
            badge_bg = "rgba(22, 163, 74, 0.1)"
            badge_border = "rgba(22, 163, 74, 0.3)"
            icon_color = "#4ade80"
        else:
            badge_bg = "#f0fdf4"
            badge_border = "#bbf7d0"
            icon_color = "#16a34a"

        badge_frame = QFrame(self)
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

        primary_btn = QPushButton("Save Session", self)
        primary_btn.setFixedHeight(40)
        primary_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        primary_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {colors['accent_btn_bg']};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-family: 'Segoe UI';
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {colors['accent_btn_hover']};
            }}
        """)

        primary_btn.clicked.connect(self._save_and_close)
        layout.addWidget(primary_btn)

    def _save_and_close(self):
        try:
            new_name = self.report_name_entry.text().strip()
            logger.info(f"[Action] Saving session to history with name: '{new_name}'")
            self.report["session_name"] = new_name if new_name else "Unnamed"
            save_to_history(self.report)
            QMessageBox.information(self, "Saved", "Session saved successfully.")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")
