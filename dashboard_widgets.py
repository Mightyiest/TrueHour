"""
TrueHour — Custom Interactive QPainter Chart Widgets.
Provides a premium, dependency-free visual experience with animations and hover states.
"""
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QColor, QPainter, QBrush, QPen, QPainterPath, QLinearGradient, QFont
import math

class DonutChartWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.segments = []  # List of {"name": str, "seconds": int, "color": str}
        self.total_seconds = 0
        self.hovered_index = -1
        self.mouse_pos = QPointF()
        self.setMouseTracking(True)
        self.setMinimumSize(220, 220)

    def set_data(self, segments):
        self.segments = [s for s in segments if s.get("seconds", 0) > 0]
        self.total_seconds = sum(s["seconds"] for s in self.segments)
        self.hovered_index = -1
        self.update()

    def mouseMoveEvent(self, event):
        self.mouse_pos = event.position()
        
        # Calculate center and radius
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        r_outer = min(cx, cy) * 0.8
        r_inner = r_outer * 0.6
        
        dx = self.mouse_pos.x() - cx
        dy = self.mouse_pos.y() - cy
        dist = math.sqrt(dx*dx + dy*dy)
        
        if r_inner <= dist <= r_outer and self.total_seconds > 0:
            # Calculate angle in degrees from 0 to 360 starting from top (-90 degrees in standard math)
            angle = math.degrees(math.atan2(dy, dx))
            # Shift angle to start from top (12 o'clock) and increase clockwise
            angle = (angle + 90) % 360
                
            # Determine which segment contains this angle
            current_angle = 0.0
            new_hover = -1
            for idx, s in enumerate(self.segments):
                span = (s["seconds"] / self.total_seconds) * 360.0
                if current_angle <= angle < (current_angle + span):
                    new_hover = idx
                    break
                current_angle += span
            
            if new_hover != self.hovered_index:
                self.hovered_index = new_hover
                self.update()
        else:
            if self.hovered_index != -1:
                self.hovered_index = -1
                self.update()
                
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.hovered_index = -1
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0
        r_outer = min(cx, cy) * 0.8
        r_inner = r_outer * 0.6
        thickness = r_outer - r_inner
        
        rect = QRectF(cx - r_outer + thickness/2.0, cy - r_outer + thickness/2.0, 
                      2.0 * r_outer - thickness, 2.0 * r_outer - thickness)

        if not self.segments or self.total_seconds == 0:
            # Draw placeholder gray donut
            pen = QPen(QColor("#E2E8F0"))
            pen.setWidthF(thickness)
            painter.setPen(pen)
            painter.drawEllipse(rect)
            
            # Center label
            painter.setPen(QColor("#94A3B8"))
            painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            painter.drawText(QRectF(cx - 70, cy - 20, 140, 40), 
                             Qt.AlignmentFlag.AlignCenter, "No Data")
            return

        current_angle = 90.0  # Start at 12 o'clock (PyQt draws positive angles counter-clockwise)
        
        # 1. Draw segments
        for idx, s in enumerate(self.segments):
            pct = s["seconds"] / self.total_seconds
            span = pct * 360.0
            
            pen = QPen(QColor(s.get("color", "#64748B")))
            
            # Highlight hovered segment
            if idx == self.hovered_index:
                pen.setWidthF(thickness + 4.0)
            else:
                pen.setWidthF(thickness)
                
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            painter.setPen(pen)
            
            # Draw arc (PyQt angles are in 1/16th of a degree, and negative span means clockwise)
            painter.drawArc(rect, int(current_angle * 16), int(-span * 16))
            current_angle -= span

        # 2. Draw Center Text Label
        is_dark = False
        win = self.window()
        if win:
            is_dark = win.palette().color(win.backgroundRole()).value() < 128
        painter.setPen(QColor("#F3F4F6") if is_dark else QColor("#0F172A"))
        painter.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        
        # Format total time
        total_m = self.total_seconds // 60
        total_h = total_m // 60
        rem_m = total_m % 60
        if total_h > 0:
            time_str = f"{total_h}h {rem_m}m"
        else:
            time_str = f"{rem_m}m" if rem_m > 0 else f"{self.total_seconds}s"
            
        painter.drawText(QRectF(cx - r_inner, cy - 18, 2.0 * r_inner, 20), 
                         Qt.AlignmentFlag.AlignCenter, time_str)
        
        painter.setPen(QColor("#9CA3AF") if is_dark else QColor("#64748B"))
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
        painter.drawText(QRectF(cx - r_inner, cy + 4, 2.0 * r_inner, 15), 
                         Qt.AlignmentFlag.AlignCenter, "Tracked")

        # 3. Draw premium floating tooltip when hovered
        if self.hovered_index != -1 and 0 <= self.hovered_index < len(self.segments):
            s = self.segments[self.hovered_index]
            pct = (s["seconds"] / self.total_seconds) * 100.0
            
            h = s["seconds"] // 3600
            m = (s["seconds"] % 3600) // 60
            s_rem = s["seconds"] % 60
            
            if h > 0:
                duration_str = f"{h}h {m}m"
            else:
                duration_str = f"{m}m {s_rem}s" if m > 0 else f"{s_rem}s"
                
            tooltip_txt = f"{s['name']}\n{duration_str} ({pct:.1f}%)"
            
            # Custom drawn tooltip box
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            fm = painter.fontMetrics()
            lines = tooltip_txt.split('\n')
            tw = max(fm.horizontalAdvance(line) for line in lines) + 20
            th = len(lines) * fm.height() + 12
            
            # Position tooltip nicely next to the mouse pointer
            tx = self.mouse_pos.x() + 15
            ty = self.mouse_pos.y() - th - 5
            
            # Boundary collision checks
            if tx + tw > w:
                tx = self.mouse_pos.x() - tw - 15
            if ty < 0:
                ty = self.mouse_pos.y() + 15
                
            tooltip_rect = QRectF(tx, ty, tw, th)
            
            # Draw shadow
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(15, 23, 42, 35)))
            painter.drawRoundedRect(tooltip_rect.translated(1, 1), 6, 6)
            
            # Draw tooltip background box
            painter.setBrush(QBrush(QColor("#0F172A")))
            painter.drawRoundedRect(tooltip_rect, 6, 6)
            
            # Draw text
            painter.setPen(QColor("#FFFFFF"))
            for i, line in enumerate(lines):
                text_rect = QRectF(tx + 10, ty + 6 + (i * fm.height()), tw - 20, fm.height())
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, line)


class BarChartWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = []  # List of {"label": str, "value": float} where value is hours
        self.hovered_index = -1
        self.mouse_pos = QPointF()
        self.setMouseTracking(True)
        self.setMinimumSize(280, 200)

    def set_data(self, data):
        self.data = data
        self.hovered_index = -1
        self.update()

    def mouseMoveEvent(self, event):
        self.mouse_pos = event.position()
        
        # Calculate hover boundaries
        w = self.width()
        h = self.height()
        padding_left = 40.0
        padding_right = 15.0
        padding_bottom = 30.0
        padding_top = 20.0
        
        chart_w = w - padding_left - padding_right
        chart_h = h - padding_top - padding_bottom
        
        if not self.data or chart_w <= 0 or chart_h <= 0:
            super().mouseMoveEvent(event)
            return

        num_bars = len(self.data)
        bar_outer_width = chart_w / num_bars
        bar_width = max(6.0, bar_outer_width * 0.6)
        
        max_val = max(d["value"] for d in self.data)
        if max_val <= 0:
            max_val = 1.0

        new_hover = -1
        for idx, d in enumerate(self.data):
            val = d["value"]
            bar_h = (val / max_val) * chart_h
            bx = padding_left + (idx * bar_outer_width) + (bar_outer_width - bar_width) / 2.0
            by = h - padding_bottom - bar_h
            
            # Build bounding box for mouse collision detection
            bar_rect = QRectF(bx - 3, by - 5, bar_width + 6, bar_h + 10)
            if bar_rect.contains(self.mouse_pos):
                new_hover = idx
                break
                
        if new_hover != self.hovered_index:
            self.hovered_index = new_hover
            self.update()
            
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.hovered_index = -1
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w = self.width()
        h = self.height()
        
        padding_left = 40.0
        padding_right = 15.0
        padding_bottom = 30.0
        padding_top = 20.0
        
        chart_w = w - padding_left - padding_right
        chart_h = h - padding_top - padding_bottom

        if not self.data or chart_w <= 0 or chart_h <= 0:
            # Draw placeholder message
            painter.setPen(QColor("#94A3B8"))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No tracked hours history.")
            return

        # Y axis max limit
        max_val = max(d["value"] for d in self.data)
        if max_val <= 0:
            max_val = 1.0
            
        # Round max to nice interval
        y_max = math.ceil(max_val) if max_val > 1 else max_val
        if y_max <= 0:
            y_max = 1.0

        # 1. Draw horizontal gridlines
        is_dark = False
        win = self.window()
        if win:
            is_dark = win.palette().color(win.backgroundRole()).value() < 128
        grid_lines = 4
        painter.setFont(QFont("Segoe UI", 8))
        for i in range(grid_lines + 1):
            val = (y_max / grid_lines) * i
            gy = h - padding_bottom - (val / y_max * chart_h)
            
            # Gridline
            if i > 0:
                pen = QPen(QColor("#333333") if is_dark else QColor("#E2E8F0"))
                pen.setStyle(Qt.PenStyle.DashLine)
                pen.setWidth(1)
                painter.setPen(pen)
                painter.drawLine(QPointF(padding_left, gy), QPointF(w - padding_right, gy))
            
            # Y Axis Labels
            painter.setPen(QColor("#9CA3AF") if is_dark else QColor("#64748B"))
            if y_max >= 1:
                label = f"{int(val)}h"
            else:
                label = f"{val:.1f}h"
            painter.drawText(QRectF(5, gy - 7, padding_left - 10, 14), 
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, label)

        # 2. Draw bars
        num_bars = len(self.data)
        bar_outer_width = chart_w / num_bars
        bar_width = max(8.0, bar_outer_width * 0.5)
        
        # Adjust bar radius depending on width
        bar_radius = min(4.0, bar_width / 2.0)

        for idx, d in enumerate(self.data):
            val = d["value"]
            bar_h = (val / y_max) * chart_h
            bx = padding_left + (idx * bar_outer_width) + (bar_outer_width - bar_width) / 2.0
            by = h - padding_bottom - bar_h
            
            bar_rect = QRectF(bx, by, bar_width, bar_h)

            if val > 0:
                # Set gradient fill color
                gradient = QLinearGradient(QPointF(bx, by), QPointF(bx, by + bar_h))
                if idx == self.hovered_index:
                    if is_dark:
                        gradient.setColorAt(0.0, QColor("#ffffff"))  # Hover top (white)
                        gradient.setColorAt(1.0, QColor("#e0e0e0"))  # Hover bottom (light gray)
                    else:
                        gradient.setColorAt(0.0, QColor("#1E3A8A"))  # Darker Blue
                        gradient.setColorAt(1.0, QColor("#3B82F6"))  # Brighter Blue
                else:
                    if is_dark:
                        gradient.setColorAt(0.0, QColor("#d1d5db"))  # Normal top (light gray)
                        gradient.setColorAt(1.0, QColor("#888888"))  # Normal bottom (medium gray)
                    else:
                        gradient.setColorAt(0.0, QColor("#0078D4"))  # Fluent Primary Accent
                        gradient.setColorAt(1.0, QColor("#60A5FA"))  # Fluent Secondary Accent
                    
                painter.setBrush(QBrush(gradient))
                painter.setPen(Qt.PenStyle.NoPen)
                
                # Draw rounded bar (top rounded, bottom flat)
                path = QPainterPath()
                path.addRoundedRect(bar_rect, bar_radius, bar_radius)
                
                # Flatten the bottom by intersecting/painting over it, or just draw rounded rect
                painter.drawPath(path)
            
            # Draw X Axis labels
            painter.setPen(QColor("#9CA3AF") if is_dark else QColor("#64748B"))
            painter.setFont(QFont("Segoe UI", 8))
            x_lbl_rect = QRectF(padding_left + (idx * bar_outer_width), h - padding_bottom + 4, 
                                bar_outer_width, 20)
            painter.drawText(x_lbl_rect, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignTop, d["label"])

        # 3. Draw Bottom Axis Line
        pen_axis = QPen(QColor("#333333") if is_dark else QColor("#CBD5E1"))
        pen_axis.setWidth(1)
        painter.setPen(pen_axis)
        painter.drawLine(QPointF(padding_left, h - padding_bottom), QPointF(w - padding_right, h - padding_bottom))

        # 4. Floating tooltip when hovered
        if self.hovered_index != -1 and 0 <= self.hovered_index < len(self.data):
            d = self.data[self.hovered_index]
            
            # Format display string nicely
            val_secs = int(d["value"] * 3600)
            val_h = val_secs // 3600
            val_m = (val_secs % 3600) // 60
            val_s = val_secs % 60
            
            if val_h > 0:
                duration_str = f"{val_h}h {val_m}m"
            else:
                duration_str = f"{val_m}m {val_s}s" if val_m > 0 else f"{val_s}s"
                
            tooltip_txt = f"{d['label']}\n{duration_str}"
            
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            fm = painter.fontMetrics()
            lines = tooltip_txt.split('\n')
            tw = max(fm.horizontalAdvance(line) for line in lines) + 20
            th = len(lines) * fm.height() + 12
            
            tx = self.mouse_pos.x() + 15
            ty = self.mouse_pos.y() - th - 5
            
            if tx + tw > w:
                tx = self.mouse_pos.x() - tw - 15
            if ty < 0:
                ty = self.mouse_pos.y() + 15
                
            tooltip_rect = QRectF(tx, ty, tw, th)
            
            # Shadow
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(15, 23, 42, 35)))
            painter.drawRoundedRect(tooltip_rect.translated(1, 1), 6, 6)
            
            # Box background
            painter.setBrush(QBrush(QColor("#0F172A")))
            painter.drawRoundedRect(tooltip_rect, 6, 6)
            
            # Text
            painter.setPen(QColor("#FFFFFF"))
            for i, line in enumerate(lines):
                text_rect = QRectF(tx + 10, ty + 6 + (i * fm.height()), tw - 20, fm.height())
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, line)


class ContributionMapWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = {}  # dict of date_str (YYYY-MM-DD) -> seconds (int)
        self.hovered_date = None
        self.hovered_cell = None  # tuple of (col, row)
        self.mouse_pos = QPointF()
        self.setMouseTracking(True)
        self.setMinimumSize(680, 130)

    def set_data(self, data):
        self.data = data if data else {}
        self.hovered_date = None
        self.hovered_cell = None
        self.update()

    def mouseMoveEvent(self, event):
        import datetime
        self.mouse_pos = event.position()
        mx = self.mouse_pos.x()
        my = self.mouse_pos.y()
        
        left_padding = 35.0
        top_padding = 25.0
        cell_size = 10.0
        cell_spacing = 2.0
        
        col = int((mx - left_padding) // (cell_size + cell_spacing))
        row = int((my - top_padding) // (cell_size + cell_spacing))
        
        new_hover_date = None
        new_hover_cell = None
        
        if 0 <= col < 53 and 0 <= row < 7:
            cx = left_padding + col * (cell_size + cell_spacing)
            cy = top_padding + row * (cell_size + cell_spacing)
            cell_rect = QRectF(cx, cy, cell_size, cell_size)
            if cell_rect.contains(self.mouse_pos):
                today = datetime.date.today()
                start_date = today - datetime.timedelta(days=364)
                start_wday = (start_date.weekday() + 1) % 7
                offset = col * 7 + row - start_wday
                if 0 <= offset < 365:
                    d = start_date + datetime.timedelta(days=offset)
                    if d <= today:
                        new_hover_date = d.strftime("%Y-%m-%d")
                        new_hover_cell = (col, row)
                    
        if new_hover_date != self.hovered_date:
            self.hovered_date = new_hover_date
            self.hovered_cell = new_hover_cell
            self.update()
            
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.hovered_date = None
        self.hovered_cell = None
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        import datetime
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w = self.width()
        h = self.height()
        
        is_dark = False
        win = self.window()
        if win:
            is_dark = win.palette().color(win.backgroundRole()).value() < 128
            
        # Set up color tokens
        accent_color = QColor("#d1d5db") if is_dark else QColor("#0078D4")
        bg_level0 = QColor("#21262D") if is_dark else QColor("#EBEDF0")
        
        # Pre-blend accent against card background for crisp cell rendering
        card_bg = QColor("#1e1e1e") if is_dark else QColor("#FFFFFF")
        def blend(accent, alpha, bg):
            t = alpha / 255.0
            r = int(accent.red() * t + bg.red() * (1 - t))
            g = int(accent.green() * t + bg.green() * (1 - t))
            b = int(accent.blue() * t + bg.blue() * (1 - t))
            return QColor(r, g, b)
        
        level1_color = blend(accent_color, 50, card_bg)
        level2_color = blend(accent_color, 110, card_bg)
        level3_color = blend(accent_color, 170, card_bg)
        level4_color = blend(accent_color, 255, card_bg)
        
        left_padding = 35.0
        top_padding = 25.0
        cell_size = 10.0
        cell_spacing = 2.0
        
        today = datetime.date.today()
        start_date = today - datetime.timedelta(days=364)
        start_wday = (start_date.weekday() + 1) % 7
        
        max_secs = max(self.data.values()) if self.data else 0
        max_limit = max(float(max_secs), 14400.0)  # 4 hours baseline ceiling
        
        # Draw cells
        for i in range(365):
            d = start_date + datetime.timedelta(days=i)
            if d > today:
                break  # Don't draw future dates
            d_str = d.strftime("%Y-%m-%d")
            col = (start_wday + i) // 7
            row = (start_wday + i) % 7
            
            cx = left_padding + col * (cell_size + cell_spacing)
            cy = top_padding + row * (cell_size + cell_spacing)
            cell_rect = QRectF(cx, cy, cell_size, cell_size)
            
            secs = self.data.get(d_str, 0)
            
            if secs <= 0:
                color = bg_level0
            elif secs <= 0.25 * max_limit:
                color = level1_color
            elif secs <= 0.50 * max_limit:
                color = level2_color
            elif secs <= 0.75 * max_limit:
                color = level3_color
            else:
                color = level4_color
                
            if d_str == self.hovered_date:
                painter.setPen(QPen(QColor("#FFFFFF") if is_dark else QColor("#0F172A"), 1.2))
            else:
                painter.setPen(Qt.PenStyle.NoPen)
                
            painter.setBrush(QBrush(color))
            painter.drawRoundedRect(cell_rect, 2.0, 2.0)
            
        # Draw month labels on top
        months_labels = []
        prev_month = -1
        temp_labels = []
        for i in range(365):
            d = start_date + datetime.timedelta(days=i)
            col = (start_wday + i) // 7
            if d.month != prev_month:
                temp_labels.append((col, d.strftime("%b")))
                prev_month = d.month
                
        last_col = -10
        for idx, (col, name) in enumerate(temp_labels):
            if idx == 0 and len(temp_labels) > 1:
                next_col = temp_labels[1][0]
                if next_col - col < 3:
                    continue
            if col - last_col >= 3:
                months_labels.append((col, name))
                last_col = col
                
        painter.setFont(QFont("Segoe UI", 8))
        painter.setPen(QColor("#9CA3AF") if is_dark else QColor("#64748B"))
        for col, month_name in months_labels:
            mx = left_padding + col * (cell_size + cell_spacing)
            painter.drawText(QRectF(mx, top_padding - 16, 40, 12), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, month_name)
            
        # Draw weekday labels on the left: "Mon", "Wed", "Fri"
        y_mon = top_padding + 1 * (cell_size + cell_spacing) + (cell_size / 2.0) - 6.0
        painter.drawText(QRectF(5, y_mon, 25, 12), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "Mon")
        
        y_wed = top_padding + 3 * (cell_size + cell_spacing) + (cell_size / 2.0) - 6.0
        painter.drawText(QRectF(5, y_wed, 25, 12), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "Wed")
        
        y_fri = top_padding + 5 * (cell_size + cell_spacing) + (cell_size / 2.0) - 6.0
        painter.drawText(QRectF(5, y_fri, 25, 12), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "Fri")
        
        # Draw legend in the bottom right
        legend_y = top_padding + 7 * (cell_size + cell_spacing) + 6
        legend_start_x = left_padding + 53 * (cell_size + cell_spacing) - 130
        
        painter.drawText(QRectF(legend_start_x - 30, legend_y - 2, 25, 12), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "Less")
        
        for level in range(5):
            lx = legend_start_x + level * (8 + 2)
            ly = legend_y
            l_rect = QRectF(lx, ly, 8, 8)
            
            if level == 0:
                l_color = bg_level0
            elif level == 1:
                l_color = level1_color
            elif level == 2:
                l_color = level2_color
            elif level == 3:
                l_color = level3_color
            else:
                l_color = level4_color
                
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(l_color))
            painter.drawRoundedRect(l_rect, 1.5, 1.5)
            
        painter.drawText(QRectF(legend_start_x + 50, legend_y - 2, 30, 12), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "More")
        
        # Draw floating tooltip when hovered
        if self.hovered_date and self.hovered_cell:
            secs = self.data.get(self.hovered_date, 0)
            h_val = secs // 3600
            m_val = (secs % 3600) // 60
            
            try:
                date_obj = datetime.datetime.strptime(self.hovered_date, "%Y-%m-%d").date()
                date_str = date_obj.strftime("%b %d, %Y")
            except Exception:
                date_str = self.hovered_date
                
            if secs > 0:
                if h_val > 0:
                    time_str = f"{h_val}h {m_val}m"
                else:
                    time_str = f"{m_val}m" if m_val > 0 else f"{secs}s"
                tooltip_txt = f"{time_str} on {date_str}"
            else:
                tooltip_txt = f"No tracked time on {date_str}"
                
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(tooltip_txt) + 20
            th = fm.height() + 12
            
            tx = self.mouse_pos.x() + 15
            ty = self.mouse_pos.y() - th - 5
            
            if tx + tw > w:
                tx = self.mouse_pos.x() - tw - 15
            if ty < 0:
                ty = self.mouse_pos.y() + 15
                
            tooltip_rect = QRectF(tx, ty, tw, th)
            
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(15, 23, 42, 35)))
            painter.drawRoundedRect(tooltip_rect.translated(1, 1), 6, 6)
            
            painter.setBrush(QBrush(QColor("#0F172A")))
            painter.drawRoundedRect(tooltip_rect, 6, 6)
            
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(tooltip_rect, Qt.AlignmentFlag.AlignCenter, tooltip_txt)

