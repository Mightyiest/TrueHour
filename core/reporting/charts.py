import math
import sys
from PyQt6.QtGui import QImage, QPainter, QColor, QPen, QBrush, QFont, QLinearGradient, QPainterPath
from PyQt6.QtCore import Qt, QRectF, QPointF, QCoreApplication
from PyQt6.QtWidgets import QApplication

_qt_app = None

def ensure_qt_app():
    global _qt_app
    if not QCoreApplication.instance():
        args = sys.argv if hasattr(sys, "argv") else []
        _qt_app = QApplication(args)

def build_donut_chart(segments, output_path: str, width=400, height=400):
    """
    Renders a donut chart offscreen to the specified output_path using PyQt6 QPainter.
    """
    ensure_qt_app()
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor("#FFFFFF"))
    
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    cx = width / 2.0
    cy = height / 2.0
    r_outer = min(cx, cy) * 0.8
    r_inner = r_outer * 0.6
    thickness = r_outer - r_inner
    
    rect = QRectF(cx - r_outer + thickness/2.0, cy - r_outer + thickness/2.0, 
                  2.0 * r_outer - thickness, 2.0 * r_outer - thickness)
                  
    total_seconds = sum(s.get("seconds", 0) for s in segments)
    
    if not segments or total_seconds == 0:
        # Draw placeholder
        pen = QPen(QColor("#E2E8F0"))
        pen.setWidthF(thickness)
        painter.setPen(pen)
        painter.drawEllipse(rect)
        
        painter.setPen(QColor("#94A3B8"))
        painter.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        painter.drawText(QRectF(cx - 100, cy - 20, 200, 40), 
                         Qt.AlignmentFlag.AlignCenter, "No Data")
    else:
        current_angle = 90.0
        for s in segments:
            secs = s.get("seconds", 0)
            if secs <= 0:
                continue
            span = (secs / total_seconds) * 360.0
            
            pen = QPen(QColor(s.get("color", "#64748B")))
            pen.setWidthF(thickness)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            painter.setPen(pen)
            
            painter.drawArc(rect, int(current_angle * 16), int(-span * 16))
            current_angle -= span
            
        # Draw Center Total Text
        painter.setPen(QColor("#0F172A"))
        painter.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        
        total_m = total_seconds // 60
        total_h = total_m // 60
        rem_m = total_m % 60
        if total_h > 0:
            time_str = f"{total_h}h {rem_m}m"
        else:
            time_str = f"{rem_m}m" if rem_m > 0 else f"{total_seconds}s"
            
        painter.drawText(QRectF(cx - r_inner, cy - 20, 2.0 * r_inner, 25), 
                         Qt.AlignmentFlag.AlignCenter, time_str)
                         
        painter.setPen(QColor("#64748B"))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
        painter.drawText(QRectF(cx - r_inner, cy + 8, 2.0 * r_inner, 20), 
                         Qt.AlignmentFlag.AlignCenter, "Tracked")
                         
    painter.end()
    image.save(output_path)

def build_bar_chart(data, output_path: str, width=500, height=300):
    """
    Renders a bar chart offscreen to the specified output_path using PyQt6 QPainter.
    """
    ensure_qt_app()
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor("#FFFFFF"))
    
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    padding_left = 50.0
    padding_right = 20.0
    padding_bottom = 40.0
    padding_top = 30.0
    
    chart_w = width - padding_left - padding_right
    chart_h = height - padding_top - padding_bottom
    
    if not data or chart_w <= 0 or chart_h <= 0:
        painter.setPen(QColor("#94A3B8"))
        painter.setFont(QFont("Segoe UI", 12))
        painter.drawText(QRectF(0, 0, width, height), Qt.AlignmentFlag.AlignCenter, "No tracked hours history.")
    else:
        max_val = max(d["value"] for d in data)
        if max_val <= 0:
            max_val = 1.0
        y_max = math.ceil(max_val) if max_val > 1 else max_val
        
        # Draw gridlines
        grid_lines = 4
        painter.setFont(QFont("Segoe UI", 9))
        for i in range(grid_lines + 1):
            val = (y_max / grid_lines) * i
            gy = height - padding_bottom - (val / y_max * chart_h)
            
            if i > 0:
                pen = QPen(QColor("#E2E8F0"))
                pen.setStyle(Qt.PenStyle.DashLine)
                pen.setWidth(1)
                painter.setPen(pen)
                painter.drawLine(QPointF(padding_left, gy), QPointF(width - padding_right, gy))
                
            painter.setPen(QColor("#64748B"))
            label = f"{int(val)}h" if y_max >= 1 else f"{val:.1f}h"
            painter.drawText(QRectF(5, gy - 8, padding_left - 10, 16), 
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, label)
                             
        # Draw bars
        num_bars = len(data)
        bar_outer_width = chart_w / num_bars
        bar_width = max(10.0, bar_outer_width * 0.6)
        bar_radius = min(4.0, bar_width / 2.0)
        
        for idx, d in enumerate(data):
            val = d["value"]
            bar_h = (val / y_max) * chart_h
            bx = padding_left + (idx * bar_outer_width) + (bar_outer_width - bar_width) / 2.0
            by = height - padding_bottom - bar_h
            
            bar_rect = QRectF(bx, by, bar_width, bar_h)
            
            if val > 0:
                gradient = QLinearGradient(QPointF(bx, by), QPointF(bx, by + bar_h))
                gradient.setColorAt(0.0, QColor("#0078D4"))
                gradient.setColorAt(1.0, QColor("#60A5FA"))
                
                painter.setBrush(QBrush(gradient))
                painter.setPen(Qt.PenStyle.NoPen)
                
                path = QPainterPath()
                path.addRoundedRect(bar_rect, bar_radius, bar_radius)
                painter.drawPath(path)
                
            # X label
            painter.setPen(QColor("#64748B"))
            painter.setFont(QFont("Segoe UI", 9))
            x_lbl_rect = QRectF(padding_left + (idx * bar_outer_width), height - padding_bottom + 5, 
                                bar_outer_width, 25)
            painter.drawText(x_lbl_rect, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignTop, d["label"])
            
        # Draw bottom axis line
        pen_axis = QPen(QColor("#CBD5E1"))
        pen_axis.setWidth(1)
        painter.setPen(pen_axis)
        painter.drawLine(QPointF(padding_left, height - padding_bottom), QPointF(width - padding_right, height - padding_bottom))
        
    painter.end()
    image.save(output_path)
