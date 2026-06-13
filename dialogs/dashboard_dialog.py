from datetime import datetime, timedelta
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QTabWidget, QWidget, QScrollArea, QComboBox
)
from PyQt6.QtCore import Qt, QTimer

from report import (
    format_duration_hms, build_report_data, aggregate_history_data
)
from theme import (
    get_tag_color
)
from dashboard_widgets import DonutChartWidget, BarChartWidget, ContributionMapWidget

class TrueHourDashboard(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_app = parent  # Reference to TrueHourApp
        self.setWindowTitle("TrueHour — Analytics Dashboard")
        
        # Set styling similar to main window
        is_dark = getattr(self.main_app, "dark_mode", False)
        from theme import get_dark_palette, get_light_palette
        self.setStyleSheet(self.main_app.styleSheet())
        self.setPalette(get_dark_palette() if is_dark else get_light_palette())
        
        self.init_ui()
        
    def get_project_color(self, project_name):
        return get_tag_color(project_name)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 1. Header Bar
        is_dark = getattr(self.main_app, "dark_mode", False)
        bg_widget = "#1e1e1e" if is_dark else "#FFFFFF"
        border_color = "#333333" if is_dark else "#E2E8F0"
        bg_window = "#141414" if is_dark else "#F8FAFC"
        text_primary = "#e0e0e0" if is_dark else "#0F172A"
        text_secondary = "#aaa" if is_dark else "#475569"
        accent = "#d1d5db" if is_dark else "#0078D4"
        
        hdr = QFrame(self)
        hdr.setFixedHeight(46)
        hdr.setStyleSheet(f"QFrame {{ background-color: {bg_widget}; border-bottom: 1px solid {border_color}; }}")
        hdr_layout = QHBoxLayout(hdr)
        hdr_layout.setContentsMargins(16, 0, 16, 0)
        
        title_lbl = QLabel("📊 Focus Analytics Dashboard", hdr)
        title_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 15px; font-weight: bold; color: {text_primary}; border: none;")
        hdr_layout.addWidget(title_lbl)
        hdr_layout.addStretch()
        
        close_icon_btn = QPushButton("Close", hdr)
        close_icon_btn.setObjectName("NormalButton")
        close_icon_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_icon_btn.clicked.connect(self.accept)
        hdr_layout.addWidget(close_icon_btn)
        
        layout.addWidget(hdr)
        
        # 2. Tab Widget
        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("DashboardTabs")
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background-color: {bg_window};
            }}
            QTabBar::tab {{
                background-color: {bg_widget};
                border: 1px solid {border_color};
                border-bottom: none;
                padding: 8px 24px;
                font-family: 'Segoe UI';
                font-size: 13px;
                font-weight: 500;
                color: {text_secondary};
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 4px;
                margin-top: 6px;
            }}
            QTabBar::tab:selected {{
                background-color: {bg_window};
                border-color: {border_color};
                color: {accent};
                font-weight: bold;
            }}
        """)
        
        # Create Tab 1: Live Analytics
        self.live_tab = QWidget()
        self.build_live_tab()
        
        # Create Tab 2: Historical Insights
        self.history_tab = QWidget()
        self.build_history_tab()
        
        # Create Tab 3: Weekly Focus Goals
        self.goals_tab = QWidget()
        self.build_goals_tab()
        
        self.tabs.addTab(self.live_tab, "Live Tracker Insights")
        self.tabs.addTab(self.history_tab, "Historical Insights")
        self.tabs.addTab(self.goals_tab, "Weekly Focus Goals")
        self.tabs.currentChanged.connect(self.on_tab_changed)
        
        layout.addWidget(self.tabs)
        
        # Timer for real-time live data updates
        self.live_timer = QTimer(self)
        self.live_timer.timeout.connect(self.update_live_data)
        
        # Set initial state
        self.on_tab_changed(0)
 
    def create_kpi_card(self, title, value_text, icon_text=None, value_color="#0F172A"):
        is_dark = getattr(self.main_app, "dark_mode", False)
        bg_widget = "#1e1e1e" if is_dark else "#FFFFFF"
        border_color = "#333333" if is_dark else "#E2E8F0"
        
        # Map light text colors to premium dark mode colors
        if value_color == "#0F172A" or value_color is None:
            val_color = "#e0e0e0" if is_dark else "#0F172A"
        elif value_color == "#0078D4":
            val_color = "#d1d5db" if is_dark else "#0078D4"
        elif value_color == "#16A34A":
            val_color = "#a8c5b8" if is_dark else "#16A34A"
        else:
            val_color = value_color

        card = QFrame(self)
        card.setObjectName("MainCard")
        card.setStyleSheet(f"""
            QFrame#MainCard {{
                background-color: {bg_widget};
                border: 1px solid {border_color};
                border-radius: 8px;
            }}
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)
        
        if icon_text:
            title_row = QHBoxLayout()
            title_lbl = QLabel(title)
            title_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 11px; color: #64748B; font-weight: 500;")
            icon_lbl = QLabel(icon_text)
            icon_lbl.setStyleSheet("font-size: 14px;")
            title_row.addWidget(title_lbl)
            title_row.addStretch()
            title_row.addWidget(icon_lbl)
            layout.addLayout(title_row)
        else:
            title_lbl = QLabel(title)
            title_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 11px; color: #64748B; font-weight: 500;")
            layout.addWidget(title_lbl)
            
        val_lbl = QLabel(value_text)
        val_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 18px; font-weight: bold; color: {val_color};")
        layout.addWidget(val_lbl)
        
        return card, val_lbl
 
    def build_live_tab(self):
        is_dark = getattr(self.main_app, "dark_mode", False)
        text_sec = "#aaa" if is_dark else "#475569"

        self.live_layout = QVBoxLayout(self.live_tab)
        self.live_layout.setContentsMargins(16, 16, 16, 16)
        self.live_layout.setSpacing(12)
        
        # Placeholder for when tracking is inactive
        self.live_placeholder = QFrame(self.live_tab)
        self.live_placeholder.setObjectName("MainCard")
        ph_layout = QVBoxLayout(self.live_placeholder)
        ph_layout.setContentsMargins(40, 40, 40, 40)
        ph_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        ph_icon = QLabel("💤", self.live_placeholder)
        ph_icon.setStyleSheet("font-size: 48px;")
        ph_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph_layout.addWidget(ph_icon)
        
        ph_lbl = QLabel("No active session is currently running.", self.live_placeholder)
        ph_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 14px; font-weight: bold; color: {text_sec}; margin-top: 10px;")
        ph_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph_layout.addWidget(ph_lbl)
        
        ph_sub = QLabel("Start focus tracking from the main screen to view real-time live insights.", self.live_placeholder)
        ph_sub.setStyleSheet("font-family: 'Segoe UI'; font-size: 12px; color: #94A3B8; margin-top: 4px;")
        ph_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph_layout.addWidget(ph_sub)
        
        self.live_layout.addWidget(self.live_placeholder)
        
        # Actual content container
        self.live_content = QWidget(self.live_tab)
        self.live_content_layout = QHBoxLayout(self.live_content)
        self.live_content_layout.setContentsMargins(0, 0, 0, 0)
        self.live_content_layout.setSpacing(16)
        
        # Left column: KPI Cards
        left_col = QVBoxLayout()
        left_col.setSpacing(10)
        
        self.card_live_total, self.lbl_live_total = self.create_kpi_card("Total Session Time", "00:00:00", "🕒")
        self.card_live_focus, self.lbl_live_focus = self.create_kpi_card("Counted Focus Time", "00:00:00", "🛡️", "#0078D4")
        self.card_live_earnings, self.lbl_live_earnings = self.create_kpi_card("Session Earnings", "0.00", "💰", "#16A34A")
        self.card_live_active, self.lbl_live_active = self.create_kpi_card("Current Active App", "None", "💻")
        
        left_col.addWidget(self.card_live_total)
        left_col.addWidget(self.card_live_focus)
        left_col.addWidget(self.card_live_earnings)
        left_col.addWidget(self.card_live_active)
        left_col.addStretch()
        
        self.live_content_layout.addLayout(left_col, 2)
        
        # Right column: Donut Chart & Category breakdown
        right_col = QVBoxLayout()
        right_col.setSpacing(10)
        
        chart_card = QFrame(self.live_content)
        chart_card.setObjectName("MainCard")
        chart_card.setFixedHeight(240)
        chart_card_layout = QVBoxLayout(chart_card)
        chart_card_layout.setContentsMargins(12, 12, 12, 12)
        
        chart_lbl = QLabel("App Time Allocation", chart_card)
        chart_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 12px; font-weight: bold; color: {text_sec};")
        chart_card_layout.addWidget(chart_lbl)
        
        self.live_donut = DonutChartWidget(chart_card)
        chart_card_layout.addWidget(self.live_donut, 1)
        
        right_col.addWidget(chart_card)
        
        # Bottom Legend / Category List for Live Tab
        self.live_legend_card = QFrame(self.live_content)
        self.live_legend_card.setObjectName("MainCard")
        self.live_legend_card.setFixedHeight(105)
        ll_layout = QVBoxLayout(self.live_legend_card)
        ll_layout.setContentsMargins(12, 8, 12, 8)
        ll_layout.setSpacing(2)
        
        ll_title = QLabel("Focus Categories breakdown", self.live_legend_card)
        ll_title.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 11px; font-weight: bold; color: {text_sec}; background: transparent; border: none;")
        ll_layout.addWidget(ll_title)
        
        # Scroll area for legend list
        self.live_legend_scroll = QScrollArea(self.live_legend_card)
        self.live_legend_scroll.setWidgetResizable(True)
        self.live_legend_scroll.setFixedHeight(75)
        self.live_legend_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.live_legend_widget = QWidget()
        self.live_legend_list_layout = QVBoxLayout(self.live_legend_widget)
        self.live_legend_list_layout.setContentsMargins(0, 0, 0, 0)
        self.live_legend_list_layout.setSpacing(4)
        self.live_legend_scroll.setWidget(self.live_legend_widget)
        ll_layout.addWidget(self.live_legend_scroll)
        
        right_col.addWidget(self.live_legend_card)
        right_col.addStretch()
        
        self.live_content_layout.addLayout(right_col, 3)
        self.live_layout.addWidget(self.live_content)
 
    def build_history_tab(self):
        is_dark = getattr(self.main_app, "dark_mode", False)
        text_sec = "#aaa" if is_dark else "#475569"

        self.history_layout = QVBoxLayout(self.history_tab)
        self.history_layout.setContentsMargins(16, 16, 16, 16)
        self.history_layout.setSpacing(12)
        
        # Top Period Selector bar
        period_bar = QHBoxLayout()
        period_bar.setSpacing(8)
        
        period_lbl = QLabel("Select Analysis Range:", self.history_tab)
        period_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 12px; font-weight: bold; color: {text_sec};")
        period_bar.addWidget(period_lbl)
        
        self.period_combo = QComboBox(self.history_tab)
        self.period_combo.addItems(["Today", "Last 7 Days", "This Month"])
        self.period_combo.currentTextChanged.connect(self.update_history_range)
        self.period_combo.setFixedWidth(140)
        period_bar.addWidget(self.period_combo)
        period_bar.addStretch()
        
        self.history_layout.addLayout(period_bar)
        
        # Main content area (Split layout)
        self.history_content = QWidget(self.history_tab)
        self.hc_layout = QHBoxLayout(self.history_content)
        self.hc_layout.setContentsMargins(0, 0, 0, 0)
        self.hc_layout.setSpacing(16)
        
        # Left side: Historical KPIs
        left_col = QVBoxLayout()
        left_col.setSpacing(10)
        
        self.card_hist_sessions, self.lbl_hist_sessions = self.create_kpi_card("Tracked Sessions", "0", "📊")
        self.card_hist_total, self.lbl_hist_total = self.create_kpi_card("Total Tracked Time", "00:00:00", "🕒")
        self.card_hist_focus, self.lbl_hist_focus = self.create_kpi_card("Total Focus Time", "00:00:00", "🛡️", "#0078D4")
        self.card_hist_earnings, self.lbl_hist_earnings = self.create_kpi_card("Aggregated Earnings", "0.00", "💰", "#16A34A")
        
        left_col.addWidget(self.card_hist_sessions)
        left_col.addWidget(self.card_hist_total)
        left_col.addWidget(self.card_hist_focus)
        left_col.addWidget(self.card_hist_earnings)
        left_col.addStretch()
        
        self.hc_layout.addLayout(left_col, 2)
        
        # Right side: Visual Charts & Legend
        right_col = QVBoxLayout()
        right_col.setSpacing(12)
        
        # Top row: Donut & Bar Charts side-by-side
        charts_row = QHBoxLayout()
        charts_row.setSpacing(10)
        
        # App allocation chart card
        app_card = QFrame(self.history_content)
        app_card.setObjectName("MainCard")
        app_card.setFixedHeight(240)
        ac_layout = QVBoxLayout(app_card)
        ac_layout.setContentsMargins(10, 10, 10, 10)
        
        ac_lbl = QLabel("App Allocation", app_card)
        ac_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 11px; font-weight: bold; color: {text_sec};")
        ac_layout.addWidget(ac_lbl)
        
        self.hist_donut = DonutChartWidget(app_card)
        ac_layout.addWidget(self.hist_donut, 1)
        charts_row.addWidget(app_card, 1)
        
        # Productivity trend bar chart card
        trend_card = QFrame(self.history_content)
        trend_card.setObjectName("MainCard")
        trend_card.setFixedHeight(240)
        tc_layout = QVBoxLayout(trend_card)
        tc_layout.setContentsMargins(10, 10, 10, 10)
        
        tc_lbl = QLabel("Productivity Hours Trend", trend_card)
        tc_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 11px; font-weight: bold; color: {text_sec};")
        tc_layout.addWidget(tc_lbl)
        
        self.hist_bar = BarChartWidget(trend_card)
        tc_layout.addWidget(self.hist_bar, 1)
        charts_row.addWidget(trend_card, 1)
        
        right_col.addLayout(charts_row)
        
        # Bottom: Categories/Projects Allocation Summary Legend list
        self.hist_legend_card = QFrame(self.history_content)
        self.hist_legend_card.setObjectName("MainCard")
        self.hist_legend_card.setFixedHeight(105)
        hl_layout = QVBoxLayout(self.hist_legend_card)
        hl_layout.setContentsMargins(12, 8, 12, 8)
        hl_layout.setSpacing(2)
        
        hl_title = QLabel("Focus Categories Aggregation", self.hist_legend_card)
        hl_title.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 11px; font-weight: bold; color: {text_sec}; background: transparent; border: none;")
        hl_layout.addWidget(hl_title)
        
        self.hist_legend_scroll = QScrollArea(self.hist_legend_card)
        self.hist_legend_scroll.setWidgetResizable(True)
        self.hist_legend_scroll.setFixedHeight(75)
        self.hist_legend_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.hist_legend_widget = QWidget()
        self.hist_legend_list_layout = QVBoxLayout(self.hist_legend_widget)
        self.hist_legend_list_layout.setContentsMargins(0, 0, 0, 0)
        self.hist_legend_list_layout.setSpacing(4)
        self.hist_legend_scroll.setWidget(self.hist_legend_widget)
        hl_layout.addWidget(self.hist_legend_scroll)
        
        right_col.addWidget(self.hist_legend_card)
        right_col.addStretch()
        
        self.hc_layout.addLayout(right_col, 5)
        self.history_layout.addWidget(self.history_content)

        # Bottom: GitHub-Style Activity Heatmap card
        self.heatmap_card = QFrame(self.history_tab)
        self.heatmap_card.setObjectName("MainCard")
        self.heatmap_card.setFixedHeight(165)
        hm_layout = QVBoxLayout(self.heatmap_card)
        hm_layout.setContentsMargins(12, 10, 12, 10)
        hm_layout.setSpacing(2)
        
        hm_title = QLabel("Activity History (Past 365 Days)", self.heatmap_card)
        hm_title.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 11px; font-weight: bold; color: {text_sec}; background: transparent; border: none;")
        hm_layout.addWidget(hm_title)
        self.hist_heatmap = ContributionMapWidget(self.heatmap_card)
        hm_layout.addWidget(self.hist_heatmap, 1)
        
        self.history_layout.addWidget(self.heatmap_card)
 
    def build_goals_tab(self):
        is_dark = getattr(self.main_app, "dark_mode", False)
        bg_widget = "#1e1e1e" if is_dark else "#FFFFFF"
        border_color = "#333333" if is_dark else "#E2E8F0"
        text_primary = "#e0e0e0" if is_dark else "#0F172A"
        text_sec = "#aaa" if is_dark else "#475569"
        
        self.goals_layout = QVBoxLayout(self.goals_tab)
        self.goals_layout.setContentsMargins(30, 40, 30, 40)
        self.goals_layout.setSpacing(20)
        self.goals_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Illustration / Large Icon
        icon_lbl = QLabel("🎯", self.goals_tab)
        icon_lbl.setStyleSheet("font-size: 64px; border: none; background: transparent;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.goals_layout.addWidget(icon_lbl)
        
        # Title
        title_lbl = QLabel("Focus Goals Studio", self.goals_tab)
        title_lbl.setStyleSheet(f"font-family: 'Outfit', 'Segoe UI'; font-size: 20px; font-weight: bold; color: {text_primary}; border: none; background: transparent;")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.goals_layout.addWidget(title_lbl)
        
        # Subtitle
        sub_lbl = QLabel("We've created a fun, interactive web dashboard to set and track your goals.\nAdjust category hours with sliders, check milestones, and toggle notifications instantly.", self.goals_tab)
        sub_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 12px; color: {text_sec}; border: none; background: transparent; line-height: 18px;")
        sub_lbl.setWordWrap(True)
        sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.goals_layout.addWidget(sub_lbl)
        
        # Divider or spacing
        self.goals_layout.addSpacing(10)
        
        # Launch Button
        launch_btn = QPushButton("🚀 Open Web Goals Studio", self.goals_tab)
        launch_btn.setObjectName("AccentButton")
        launch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        launch_btn.setFixedHeight(40)
        launch_btn.setMinimumWidth(240)
        launch_btn.setStyleSheet("""
            QPushButton {
                font-family: 'Segoe UI';
                font-size: 13px;
                font-weight: bold;
                border-radius: 8px;
                padding: 0px 24px;
            }
        """)
        
        def launch_web_console():
            import webbrowser
            if hasattr(self.main_app, "web_server_mgr") and self.main_app.web_server_mgr:
                port = self.main_app.web_server_mgr.port
                webbrowser.open(f"http://localhost:{port}/")
            else:
                webbrowser.open("http://localhost:5080/") # fallback
                
        launch_btn.clicked.connect(launch_web_console)
        self.goals_layout.addWidget(launch_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # Footer server status
        status_lbl = QLabel("Local Web Console is secure, lightweight, and offline.", self.goals_tab)
        status_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 10px; color: #64748B; border: none; background: transparent;")
        status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.goals_layout.addWidget(status_lbl)
        
        self.goals_layout.addStretch()
 
    def adjust_dialog_size(self, is_live, is_goals=False):
        # Enforce a stable 800x680 size for all tabs to prevent jarring jumps and setGeometry warnings
        self.setMinimumSize(800, 680)
        self.resize(800, 680)
        if self.main_app:
            self.main_app._center_window(self, 800, 680)

    def on_tab_changed(self, index):
        if index == 0:
            self.live_timer.start(1000)
            self.update_live_data()
            self.adjust_dialog_size(is_live=True)
        elif index == 1:
            self.live_timer.stop()
            self.update_historical_data()
            self.adjust_dialog_size(is_live=False)
        else:
            self.live_timer.stop()
            self.adjust_dialog_size(is_live=False, is_goals=True)
 
    def update_history_range(self, text):
        self.update_historical_data()
 
    def update_live_data(self):
        tracker = self.main_app.tracker
        if not tracker.running:
            self.live_placeholder.setVisible(True)
            self.live_content.setVisible(False)
            return
        
        self.live_placeholder.setVisible(False)
        self.live_content.setVisible(True)
        
        # Live stats
        elapsed = tracker.get_elapsed()
        self.lbl_live_total.setText(format_duration_hms(elapsed))
        
        counted = tracker.get_counted_seconds()
        self.lbl_live_focus.setText(format_duration_hms(counted))
        
        hourly = self.main_app.hourly_rate
        earned = (counted / 3600.0) * hourly if hourly > 0 else 0.0
        display_symbol = self.main_app.currency_symbol
        self.lbl_live_earnings.setText(f"{display_symbol}{earned:,.2f}")
        
        current_app = tracker.get_current_app() or "None"
        self.lbl_live_active.setText(current_app)
        
        # Apps donut
        report = build_report_data(tracker, hourly_rate=hourly, currency_symbol=display_symbol)
        apps_breakdown = []
        for app in report.get("apps", []):
            if not app["excluded"]:
                apps_breakdown.append({
                    "name": app["name"],
                    "seconds": app["seconds"],
                    "color": self.get_project_color(app["tag"])
                })
        self.live_donut.set_data(apps_breakdown)
        
        # Refresh live legend list
        while self.live_legend_list_layout.count() > 0:
            item = self.live_legend_list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
                
        project_breakdown = report.get("project_breakdown", [])
        for pb in project_breakdown:
            row_f = QFrame()
            row_f.setFixedHeight(22)
            row_layout = QHBoxLayout(row_f)
            row_layout.setContentsMargins(4, 0, 4, 0)
            row_layout.setSpacing(6)
            row_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            
            # Dynamic styled color dot for baseline alignment
            swatch = QLabel(row_f)
            swatch.setFixedSize(8, 8)
            swatch.setStyleSheet(f"background-color: {self.get_project_color(pb['project'])}; border-radius: 4px; border: none; margin-top: 1px;")
            row_layout.addWidget(swatch, alignment=Qt.AlignmentFlag.AlignVCenter)
            
            is_dark = getattr(self.main_app, "dark_mode", False)
            text_primary = "#e0e0e0" if is_dark else "#1A1A1A"
            
            lbl = QLabel(pb["project"], row_f)
            lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 11px; font-weight: bold; color: {text_primary}; border: none; background: transparent; margin-bottom: 1px; padding: 0px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            row_layout.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignVCenter)
            
            pct_lbl = QLabel(f"{pb['percent']:.1f}%", row_f)
            pct_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 11px; color: #64748B; border: none; background: transparent; margin-bottom: 1px; padding: 0px;")
            pct_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            row_layout.addWidget(pct_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)
            
            row_layout.addStretch()
            
            time_lbl = QLabel(pb["formatted"], row_f)
            time_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 11px; font-weight: 500; color: {text_primary}; border: none; background: transparent; margin-bottom: 1px; padding: 0px;")
            time_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
            row_layout.addWidget(time_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)
            
            self.live_legend_list_layout.addWidget(row_f)
        self.live_legend_list_layout.addStretch()
 
    def update_historical_data(self):
        range_text = self.period_combo.currentText()
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        if range_text == "Today":
            start_d = today
            end_d = datetime.now()
        elif range_text == "Last 7 Days":
            start_d = today - timedelta(days=6)
            end_d = datetime.now()
        else:  # "This Month"
            start_d = today.replace(day=1)
            end_d = datetime.now()
            
        hourly = self.main_app.hourly_rate
        curr_sym = self.main_app.currency_symbol
        
        data = aggregate_history_data(start_d, end_d, hourly_rate=hourly, currency_symbol=curr_sym)
        
        # Fill historical KPI Cards
        self.lbl_hist_sessions.setText(str(data["session_count"]))
        self.lbl_hist_total.setText(data["total_formatted"])
        self.lbl_hist_focus.setText(data["counted_formatted"])
        self.lbl_hist_earnings.setText(data["total_earned_display"])
        
        # App breakdown donut
        apps_breakdown = []
        for app in data.get("apps", []):
            if not app["excluded"]:
                apps_breakdown.append({
                    "name": app["name"],
                    "seconds": app["seconds"],
                    "color": self.get_project_color(app["tag"])
                })
        self.hist_donut.set_data(apps_breakdown)
        
        # Productivity bar trend
        self.hist_bar.set_data(data.get("daily_trend", []))
        
        # Refresh historical legend list
        while self.hist_legend_list_layout.count() > 0:
            item = self.hist_legend_list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
                
        # Calculate weekly focus seconds for categories
        weekly_project_seconds = {}
        try:
            from datetime import datetime as dt_class, timedelta as td_class
            now_dt = dt_class.now()
            today_start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            start_of_week = today_start - td_class(days=today_start.weekday())
            
            exclude_key = None
            if self.main_app and self.main_app.tracker.running and self.main_app.tracker.session_start:
                s_date = self.main_app.tracker.session_start.strftime("%Y-%m-%d")
                s_start = self.main_app.tracker.session_start.strftime("%H:%M:%S")
                exclude_key = (s_date, s_start)
                
            data_w = aggregate_history_data(start_of_week, now_dt, exclude_key=exclude_key)
            for item in data_w.get("project_breakdown", []):
                weekly_project_seconds[item["project"]] = item["seconds"]
                
            if self.main_app and self.main_app.tracker.running:
                report_l = build_report_data(self.main_app.tracker, hourly_rate=self.main_app.hourly_rate)
                for item in report_l.get("project_breakdown", []):
                    proj = item["project"]
                    weekly_project_seconds[proj] = weekly_project_seconds.get(proj, 0.0) + item["seconds"]
        except Exception as e:
            print(f"[TrueHour] Failed to compute weekly progress data: {e}")

        project_breakdown = data.get("project_breakdown", [])
        weekly_goals = getattr(self.main_app, "weekly_goals", {})
        
        for pb in project_breakdown:
            row_f = QFrame()
            
            # Dynamic styled color dot for baseline alignment
            swatch = QLabel(row_f)
            swatch.setFixedSize(8, 8)
            swatch.setStyleSheet(f"background-color: {self.get_project_color(pb['project'])}; border-radius: 4px; border: none; margin-top: 1px;")
            
            is_dark = getattr(self.main_app, "dark_mode", False)
            text_primary = "#e0e0e0" if is_dark else "#1A1A1A"
            
            goal_hours = weekly_goals.get(pb["project"], 0.0)
            if goal_hours > 0:
                row_f.setFixedHeight(34)
                row_layout = QVBoxLayout(row_f)
                row_layout.setContentsMargins(4, 2, 4, 2)
                row_layout.setSpacing(4)
                
                # Top text row
                top_layout = QHBoxLayout()
                top_layout.setContentsMargins(0, 0, 0, 0)
                top_layout.setSpacing(6)
                
                top_layout.addWidget(swatch, alignment=Qt.AlignmentFlag.AlignVCenter)
                
                lbl = QLabel(pb["project"], row_f)
                lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 11px; font-weight: bold; color: {text_primary}; border: none; background: transparent; padding: 0px;")
                top_layout.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignVCenter)
                
                goal_seconds = goal_hours * 3600.0
                tracked_seconds = weekly_project_seconds.get(pb["project"], 0.0)
                progress_pct = (tracked_seconds / goal_seconds) * 100.0
                
                pct_lbl = QLabel(f"({progress_pct:.1f}% of {goal_hours:.1f}h weekly goal)", row_f)
                pct_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 10px; color: #64748B; border: none; background: transparent; padding: 0px;")
                top_layout.addWidget(pct_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)
                
                top_layout.addStretch()
                
                time_lbl = QLabel(pb["formatted"], row_f)
                time_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 11px; font-weight: 500; color: {text_primary}; border: none; background: transparent; padding: 0px;")
                top_layout.addWidget(time_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)
                
                row_layout.addLayout(top_layout)
                
                # Bottom progress bar row
                pbar = QFrame(row_f)
                pbar.setFixedHeight(4)
                pbar.setStyleSheet(f"background-color: {'#333333' if is_dark else '#E2E8F0'}; border-radius: 2px; border: none;")
                pbar_layout = QHBoxLayout(pbar)
                pbar_layout.setContentsMargins(0, 0, 0, 0)
                pbar_layout.setSpacing(0)
                
                pfill = QFrame(pbar)
                pfill.setFixedHeight(4)
                fill_pct = max(0, min(100, round(progress_pct)))
                pfill.setStyleSheet(f"background-color: {self.get_project_color(pb['project'])}; border-radius: 2px; border: none;")
                pbar_layout.addWidget(pfill, fill_pct)
                pbar_layout.addStretch(100 - fill_pct)
                
                row_layout.addWidget(pbar)
            else:
                row_f.setFixedHeight(22)
                row_layout = QHBoxLayout(row_f)
                row_layout.setContentsMargins(4, 0, 4, 0)
                row_layout.setSpacing(6)
                row_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
                
                row_layout.addWidget(swatch, alignment=Qt.AlignmentFlag.AlignVCenter)
                
                lbl = QLabel(pb["project"], row_f)
                lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 11px; font-weight: bold; color: {text_primary}; border: none; background: transparent; margin-bottom: 1px; padding: 0px;")
                lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                row_layout.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignVCenter)
                
                pct_lbl = QLabel(f"{pb['percent']:.1f}%", row_f)
                pct_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 11px; color: #64748B; border: none; background: transparent; margin-bottom: 1px; padding: 0px;")
                pct_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                row_layout.addWidget(pct_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)
                
                row_layout.addStretch()
                
                time_lbl = QLabel(pb["formatted"], row_f)
                time_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 11px; font-weight: 500; color: {text_primary}; border: none; background: transparent; margin-bottom: 1px; padding: 0px;")
                time_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
                row_layout.addWidget(time_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)
                
            self.hist_legend_list_layout.addWidget(row_f)
        self.hist_legend_list_layout.addStretch()

        # Update heatmap (always query past 365 days)
        try:
            from core.reporting.statistics import get_daily_summaries
            hm_start = today - timedelta(days=364)
            hm_start_str = hm_start.strftime("%Y-%m-%d")
            hm_end_str = datetime.now().strftime("%Y-%m-%d")
            summaries = get_daily_summaries(hm_start_str, hm_end_str)
            heatmap_data = {s["date"]: s["total_seconds"] for s in summaries}
            self.hist_heatmap.set_data(heatmap_data)
        except Exception as e:
            print(f"[TrueHour] Failed to load heatmap data: {e}")
            self.hist_heatmap.set_data({})
