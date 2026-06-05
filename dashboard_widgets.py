"""
TrueHour — Custom Interactive QPainter Chart Widgets.
Provides a premium, dependency-free visual experience with animations and hover states.
"""
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRectF, QPointF, QSize
from PyQt6.QtGui import QColor, QPainter, QBrush, QPen, QPainterPath, QLinearGradient, QFont, QFontMetrics
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
                        gradient.setColorAt(0.0, QColor("#5677a2"))  # Darker accent
                        gradient.setColorAt(1.0, QColor("#6b8bb5"))  # Accent
                    else:
                        gradient.setColorAt(0.0, QColor("#1E3A8A"))  # Darker Blue
                        gradient.setColorAt(1.0, QColor("#3B82F6"))  # Brighter Blue
                else:
                    if is_dark:
                        gradient.setColorAt(0.0, QColor("#6b8bb5"))  # Accent
                        gradient.setColorAt(1.0, QColor("#7ca1cf"))  # Accent hover
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
