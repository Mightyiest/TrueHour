"""
TrueHour — Session Report Dialog
Displays detailed live preview or historical session report breakdown.
"""

import logging
from datetime import datetime
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
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
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
)

from report import save_to_history
from theme import (
    apply_dialog_theme,
    get_theme_colors,
    get_tag_color,
)
from widgets.custom_widgets import SegmentedAllocationBar
from widgets.ui_utils import center_window

logger = logging.getLogger(__name__)


class ReportDialog(QDialog):
    """Session report dialog showing summary cards, allocation breakdown, app list, and timeline."""

    export_requested = pyqtSignal(object, str)
    refresh_requested = pyqtSignal()

    def __init__(
        self,
        report: dict,
        is_new: bool = True,
        is_live: bool = False,
        theme_style: str = "light",
        parent=None,
    ):
        super().__init__(parent)
        self.report = report
        self.is_new = is_new
        self.is_live = is_live
        self.theme_style = theme_style

        self.setWindowTitle(
            "TrueHour — Live Report" if is_live else "TrueHour — Session Report"
        )
        center_window(self, 720, 680)
        self.setMinimumSize(600, 500)

        apply_dialog_theme(self, self.theme_style)
        colors = get_theme_colors(self.theme_style)
        is_dark = self.theme_style in ["modern-dark", "classic-dark"]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar
        hdr = QFrame(self)
        hdr.setFixedHeight(44)
        hdr.setStyleSheet(
            f"QFrame {{ background-color: {colors['bg_widget']}; border-bottom: 1px solid {colors['border_color']}; }}"
        )
        hdr_layout = QHBoxLayout(hdr)
        hdr_layout.setContentsMargins(14, 0, 14, 0)

        title_lbl = QLabel(
            "📊 Live Report (Preview)" if is_live else "📊 Session Report", hdr
        )
        title_lbl.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 15px; font-weight: bold; color: {colors['text_primary']}; border: none;"
        )
        hdr_layout.addWidget(title_lbl)
        hdr_layout.addStretch()

        if is_live:
            ref_btn = QPushButton("🔄 Refresh", hdr)
            ref_btn.setObjectName("NormalButton")
            ref_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            ref_btn.clicked.connect(self._on_refresh_clicked)
            hdr_layout.addWidget(ref_btn)
        elif is_new:
            save_btn = QPushButton("💾 Save to History", hdr)
            save_btn.setObjectName("AccentButton")
            save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            hdr_layout.addWidget(save_btn)

        layout.addWidget(hdr)

        # Name Entry bar
        name_bar = QFrame(self)
        name_bar.setFixedHeight(40)
        name_bar.setStyleSheet(
            f"QFrame {{ background-color: {colors['bg_widget']}; border-bottom: 1px solid {colors['border_f3']}; }}"
        )
        nb_layout = QHBoxLayout(name_bar)
        nb_layout.setContentsMargins(14, 0, 14, 0)

        nb_layout.addWidget(QLabel("Session Name: "))
        self.report_name_entry = QLineEdit(name_bar)
        self.report_name_entry.setFixedWidth(260)
        self.report_name_entry.setText(
            self.report.get("session_name", "").strip() or "Unnamed"
        )
        nb_layout.addWidget(self.report_name_entry)

        nb_layout.addStretch()
        if is_live:
            live_lbl = QLabel(
                f"🕒 Snapshot: {datetime.now().strftime('%H:%M:%S')} • Tracking active",
                name_bar,
            )
            live_lbl.setStyleSheet(
                "color: #CA5010; font-family: 'Segoe UI'; font-size: 11px;"
            )
            nb_layout.addWidget(live_lbl)
        layout.addWidget(name_bar)

        # Scrollable Content Area
        scroll = QScrollArea(self)
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

        date_lbl = QLabel(
            f"{self.report['date_display']}  ·  {self.report['start_display']} -> {self.report['end_display']}",
            card1,
        )
        date_lbl.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 12px; color: {colors['text_secondary']};"
        )
        c1_layout.addWidget(date_lbl)

        total_lbl = QLabel(
            f"Total session:  {self.report['total_formatted']}", card1
        )
        total_lbl.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 13px; color: {colors['text_primary']};"
        )
        c1_layout.addWidget(total_lbl)

        counted_lbl = QLabel(
            f"Counted work:  {self.report['counted_formatted']}", card1
        )
        counted_lbl.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 14px; font-weight: bold; color: {colors['accent_lbl_color']};"
        )
        c1_layout.addWidget(counted_lbl)

        if self.report.get("total_earned", 0) > 0:
            earned_f = QFrame(card1)
            earned_f.setStyleSheet(
                f"QFrame {{ background-color: {colors['card_bg']}; border-radius: 4px; }}"
            )
            ef_layout = QHBoxLayout(earned_f)
            ef_layout.setContentsMargins(10, 6, 10, 6)

            lbl_title = QLabel("💰 Total Earned: ", earned_f)
            lbl_title.setStyleSheet(
                f"font-family: 'Segoe UI'; font-size: 12px; color: {colors['text_secondary']};"
            )
            ef_layout.addWidget(lbl_title)

            lbl_val = QLabel(self.report["total_earned_display"], earned_f)
            lbl_val.setStyleSheet(
                f"font-family: 'Segoe UI'; font-size: 18px; font-weight: bold; color: {colors['earned_fg']};"
            )
            ef_layout.addWidget(lbl_val)

            lbl_rate = QLabel(
                f"@ {self.report['currency_symbol']}{self.report['hourly_rate']:.2f}/hr",
                earned_f,
            )
            lbl_rate.setStyleSheet(
                f"font-family: 'Segoe UI'; font-size: 11px; color: {colors['text_secondary']};"
            )
            ef_layout.addWidget(lbl_rate)

            ef_layout.addStretch()
            c1_layout.addWidget(earned_f)

        scroll_layout.addWidget(card1)

        # Card 2: Allocation horizontal custom paint bar
        project_breakdown = self.report.get("project_breakdown", [])
        if project_breakdown:
            title_p = QLabel("Project & Category Allocation", scroll_widget)
            title_p.setStyleSheet(
                f"font-family: 'Segoe UI'; font-size: 13px; font-weight: bold; color: {colors['text_secondary']};"
            )
            scroll_layout.addWidget(title_p)

            alloc_card = QFrame(scroll_widget)
            alloc_card.setObjectName("MainCard")
            ac_layout = QVBoxLayout(alloc_card)
            ac_layout.setContentsMargins(14, 14, 14, 14)

            paint_bar = SegmentedAllocationBar(alloc_card)
            paint_bar.set_breakdown(project_breakdown)
            ac_layout.addWidget(paint_bar)

            for pb in project_breakdown:
                row_f = QFrame(alloc_card)
                row_f.setFixedHeight(24)
                row_layout = QHBoxLayout(row_f)
                row_layout.setContentsMargins(0, 0, 0, 0)

                swatch = QLabel("■", row_f)
                swatch.setStyleSheet(f"color: {pb['color']}; font-size: 14px;")
                row_layout.addWidget(swatch)

                lbl = QLabel(pb["project"], row_f)
                lbl.setStyleSheet(
                    f"font-family: 'Segoe UI'; font-size: 12px; font-weight: bold; color: {colors['text_primary']};"
                )
                row_layout.addWidget(lbl)

                pct_lbl = QLabel(f"{pb['percent']:.1f}%", row_f)
                pct_lbl.setStyleSheet(
                    f"font-family: 'Segoe UI'; font-size: 12px; color: {colors['text_secondary']};"
                )
                row_layout.addWidget(pct_lbl)

                row_layout.addStretch()

                if pb.get("earned_display"):
                    earned_lbl = QLabel(f"({pb['earned_display']})", row_f)
                    earned_lbl.setStyleSheet(
                        f"font-family: 'Segoe UI'; font-size: 12px; font-weight: bold; color: {colors['earned_fg']};"
                    )
                    row_layout.addWidget(earned_lbl)

                time_lbl = QLabel(pb["formatted"], row_f)
                time_lbl.setStyleSheet(
                    f"font-family: 'Segoe UI'; font-size: 12px; color: {colors['text_primary']};"
                )
                row_layout.addWidget(time_lbl)

                ac_layout.addWidget(row_f)

            scroll_layout.addWidget(alloc_card)

        # Card 3: App Breakdown list table
        apps_data = self.report.get("apps", [])
        if apps_data:
            title_b = QLabel("App Breakdown", scroll_widget)
            title_b.setStyleSheet(
                f"font-family: 'Segoe UI'; font-size: 13px; font-weight: bold; color: {colors['text_secondary']};"
            )
            scroll_layout.addWidget(title_b)

            tbl_card = QFrame(scroll_widget)
            tbl_card.setObjectName("MainCard")
            tc_layout = QVBoxLayout(tbl_card)
            tc_layout.setContentsMargins(0, 0, 0, 0)

            table = QTableWidget(tbl_card)
            table.setColumnCount(5)
            table.setHorizontalHeaderLabels(
                ["App", "Category", "Time", "%", "Status"]
            )
            table.horizontalHeader().setSectionResizeMode(
                0, QHeaderView.ResizeMode.Stretch
            )
            table.horizontalHeader().setSectionResizeMode(
                1, QHeaderView.ResizeMode.ResizeToContents
            )
            table.horizontalHeader().setSectionResizeMode(
                2, QHeaderView.ResizeMode.ResizeToContents
            )
            table.horizontalHeader().setSectionResizeMode(
                3, QHeaderView.ResizeMode.ResizeToContents
            )
            table.horizontalHeader().setSectionResizeMode(
                4, QHeaderView.ResizeMode.ResizeToContents
            )
            table.setRowCount(len(apps_data))
            table.verticalHeader().setVisible(False)
            table.setFocusPolicy(Qt.FocusPolicy.NoFocus)

            for i, app in enumerate(apps_data):
                table.setItem(i, 0, QTableWidgetItem(app["name"]))

                tag_item = QTableWidgetItem(app["tag"])
                tag_item.setForeground(QColor("#FFFFFF"))
                tag_item.setBackground(QColor(get_tag_color(app["tag"])))
                tag_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(i, 1, tag_item)

                table.setItem(i, 2, QTableWidgetItem(app["formatted"]))
                table.setItem(i, 3, QTableWidgetItem(f"{app['percent']:.0f}%"))

                st_text = "✓ Counted" if not app["excluded"] else "✗ Excluded"
                st_color = (
                    colors["earned_fg"]
                    if not app["excluded"]
                    else ("#888888" if is_dark else "#C42B1C")
                )
                st_item = QTableWidgetItem(st_text)
                st_item.setForeground(QColor(st_color))
                table.setItem(i, 4, st_item)

            table.setFixedHeight(
                table.horizontalHeader().height()
                + sum(table.rowHeight(row) for row in range(len(apps_data)))
                + 4
            )
            tc_layout.addWidget(table)
            scroll_layout.addWidget(tbl_card)

        # Card 4: Timeline
        timeline_data = self.report.get("timeline", [])
        if timeline_data:
            title_t = QLabel("Timeline", scroll_widget)
            title_t.setStyleSheet(
                f"font-family: 'Segoe UI'; font-size: 13px; font-weight: bold; color: {colors['text_secondary']};"
            )
            scroll_layout.addWidget(title_t)

            tl_card = QFrame(scroll_widget)
            tl_card.setObjectName("MainCard")
            tl_layout = QVBoxLayout(tl_card)
            tl_layout.setContentsMargins(0, 0, 0, 0)
            tl_layout.setSpacing(0)

            tl_table = QTableWidget(tl_card)
            tl_table.setColumnCount(2)
            tl_table.setHorizontalHeaderLabels(["Duration Block", "Application"])
            tl_table.horizontalHeader().setSectionResizeMode(
                0, QHeaderView.ResizeMode.ResizeToContents
            )
            tl_table.horizontalHeader().setSectionResizeMode(
                1, QHeaderView.ResizeMode.Stretch
            )
            tl_table.verticalHeader().setVisible(False)
            tl_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)

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
                    t_start = (
                        tl["start"].strftime("%H:%M:%S")
                        if hasattr(tl["start"], "strftime")
                        else tl["start"]
                    )
                    t_end = (
                        tl["end"].strftime("%H:%M:%S")
                        if hasattr(tl["end"], "strftime")
                        else tl["end"]
                    )

                    tl_table.setItem(
                        i, 0, QTableWidgetItem(f"{t_start} -> {t_end}")
                    )
                    tl_table.setItem(i, 1, QTableWidgetItem(tl["app"]))

                header_h = (
                    tl_table.horizontalHeader().height()
                    if tl_table.horizontalHeader().height() > 0
                    else 28
                )
                row_sum = 0
                for row in range(current_limit):
                    rh = tl_table.rowHeight(row)
                    row_sum += rh if rh > 0 else 28
                tl_table.setFixedHeight(header_h + row_sum + 4)

                if current_limit < len(timeline_data):
                    more_btn.setVisible(True)
                    btn_container.setVisible(True)
                    more_btn.setText(
                        f"Show More (+{min(15, len(timeline_data) - current_limit)})"
                    )
                else:
                    more_btn.setVisible(False)
                    btn_container.setVisible(False)

            def show_more():
                state["limit"] += 15
                load_timeline_rows(state["limit"])

            more_btn.clicked.connect(show_more)
            load_timeline_rows(state["limit"])

            tl_layout.addWidget(tl_table)
            tl_layout.addWidget(btn_container)
            scroll_layout.addWidget(tl_card)

        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

        # Export Actions Footer
        footer_f = QFrame(self)
        footer_f.setFixedHeight(50)
        footer_f.setStyleSheet(
            f"QFrame {{ background-color: {colors['bg_widget']}; border-top: 1px solid {colors['border_color']}; }}"
        )
        footer_layout = QHBoxLayout(footer_f)
        footer_layout.setContentsMargins(14, 0, 14, 0)

        txt_btn = QPushButton("Export .txt", footer_f)
        txt_btn.setObjectName("AccentButton")
        txt_btn.clicked.connect(lambda: self._export_with_name("txt"))
        footer_layout.addWidget(txt_btn)

        html_btn = QPushButton("View in Browser", footer_f)
        html_btn.setObjectName("AccentButton")
        html_btn.clicked.connect(lambda: self._export_with_name("html"))
        footer_layout.addWidget(html_btn)

        footer_layout.addStretch()

        close_btn = QPushButton("Close", footer_f)
        close_btn.setObjectName("NormalButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.reject)
        footer_layout.addWidget(close_btn)

        if not is_live and is_new:
            save_btn.clicked.connect(self._save_and_close)

        layout.addWidget(footer_f)

    def _on_refresh_clicked(self):
        self.accept()
        self.refresh_requested.emit()

    def _export_with_name(self, fmt: str):
        try:
            new_name = self.report_name_entry.text().strip()
            if new_name:
                self.report["session_name"] = new_name
        except Exception:
            pass
        self.export_requested.emit(self.report, fmt)

    def _save_and_close(self):
        try:
            new_name = self.report_name_entry.text().strip()
            logger.info(
                f"[Action] Saving session to history with name: '{new_name}'"
            )
            self.report["session_name"] = new_name if new_name else "Unnamed"
            save_to_history(self.report)
            QMessageBox.information(self, "Saved", "Session saved to History.")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")
