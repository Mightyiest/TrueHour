"""
TrueHour — Custom Reusable UI Widgets & Dialog Component Leaf Nodes
"""
import os
from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QCheckBox, QDialog, QLayout, QInputDialog
)
from PyQt6.QtCore import Qt, QSize, QPoint, QRect, QRectF
from PyQt6.QtGui import QPixmap, QPainter, QBrush, QColor, QPen, QPainterPath

from theme import get_svg_icon, get_tag_color
from assets import EDIT_SVG
from report import format_duration

# ── QR Code Thumbnail Widget with Hover Edit ──────────────────────────
class QRThumbnailWidget(QFrame):
    """Custom QFrame for QR code thumbnail displaying with hover and edit/delete overlay."""
    def __init__(self, qr_filename, qr_full_path, initial_url, on_remove, on_link_changed, parent=None):
        super().__init__(parent)
        self.qr_filename = qr_filename
        self.qr_full_path = qr_full_path
        self.link_url = initial_url
        self.on_remove = on_remove
        self.on_link_changed = on_link_changed
        
        self.setFixedSize(72, 72)
        self.setStyleSheet("""
            QRThumbnailWidget {
                background-color: #F8FAFC;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
            }
            QRThumbnailWidget:hover {
                border-color: #0078D4;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)
        
        # QR image thumbnail
        pix = QPixmap(qr_full_path)
        self.thumb_lbl = QLabel(self)
        if not pix.isNull():
            pix = pix.scaled(56, 56, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.thumb_lbl.setPixmap(pix)
        else:
            self.thumb_lbl.setText("⚠")
        self.thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_lbl.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(self.thumb_lbl)
        
        # Overlay remove button
        self.remove_btn = QPushButton("✕", self)
        self.remove_btn.setFixedSize(18, 18)
        self.remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remove_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(239, 68, 68, 0.85);
                color: white;
                border: none;
                border-radius: 9px;
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #DC2626;
            }
        """)
        self.remove_btn.move(54, 0)
        self.remove_btn.clicked.connect(self.on_remove)
        
        # Overlay edit button (pencil icon in the middle)
        self.edit_btn = QPushButton(self)
        self.edit_btn.setFixedSize(24, 24)
        self.edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # SVG icon
        self.edit_btn.setIcon(get_svg_icon(EDIT_SVG, QSize(16, 16)))
        self.edit_btn.setIconSize(QSize(16, 16))
        self.edit_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.95);
                border: 1px solid #CBD5E1;
                border-radius: 12px;
                padding: 3px;
            }
            QPushButton:hover {
                background-color: #FFFFFF;
                border-color: #0078D4;
            }
        """)
        # Center in the 72x72 frame: (72 - 24) / 2 = 24
        self.edit_btn.move(24, 24)
        self.edit_btn.setVisible(False)
        self.edit_btn.setToolTip("Add/Edit QR Code Link")
        self.edit_btn.clicked.connect(self._edit_link)
        
        # Overlay for URL status indicator
        self.link_indicator = QLabel(self)
        self.link_indicator.setFixedSize(10, 10)
        self.link_indicator.setStyleSheet("background-color: #0F7B0F; border-radius: 5px; border: 1px solid white;")
        self.link_indicator.move(4, 4)
        self.link_indicator.setVisible(bool(self.link_url))
        self.link_indicator.setToolTip(f"Link: {self.link_url}" if self.link_url else "")

    def _edit_link(self):
        url, ok = QInputDialog.getText(
            self, 
            "Edit QR Code Link", 
            "Enter hyperlink for this QR code (when clicked on invoice):",
            QLineEdit.EchoMode.Normal,
            self.link_url
        )
        if ok:
            url = url.strip()
            self.link_url = url
            self.link_indicator.setVisible(bool(url))
            self.link_indicator.setToolTip(f"Link: {url}" if url else "")
            self.on_link_changed(self.qr_filename, url)

    def enterEvent(self, event):
        self.edit_btn.setVisible(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.edit_btn.setVisible(False)
        super().leaveEvent(event)

# ── Email Chip Widget (Gmail-style Token Input) ──────────────────────
class EmailChipWidget(QWidget):
    """A multi-email input widget with Gmail-style chips/tokens."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._emails = []
        self._chip_widgets = []

        self._outer_layout = QVBoxLayout(self)
        self._outer_layout.setContentsMargins(0, 0, 0, 0)
        self._outer_layout.setSpacing(4)

        # Chip container with flow-wrap behavior
        self._chip_container = QWidget(self)
        self._chip_container.setStyleSheet("background: transparent;")
        self._flow_layout = FlowLayout(self._chip_container, margin=2, spacing=4)
        self._outer_layout.addWidget(self._chip_container)

        # Text input line
        self._input = QLineEdit(self)
        self._input.setPlaceholderText("Type email and press Enter or comma...")
        self._outer_layout.addWidget(self._input)

        self._input.returnPressed.connect(self._on_commit)
        self._input.textChanged.connect(self._on_text_changed)
        
        self.update_theme()

    def update_theme(self):
        is_dark = False
        win = self.window()
        if win:
            is_dark = win.palette().color(win.backgroundRole()).value() < 128
        bg_widget = "#161D30" if is_dark else "#FFFFFF"
        border_color = "#24304F" if is_dark else "#E2E8F0"
        text_color = "#F3F4F6" if is_dark else "#0F172A"
        accent = "#38BDF8" if is_dark else "#0078D4"
        
        self._input.setStyleSheet(f"""
            QLineEdit {{
                border: 1px solid {border_color};
                border-radius: 6px;
                padding: 5px 8px;
                font-family: 'Segoe UI';
                font-size: 12px;
                background-color: {bg_widget};
                color: {text_color};
            }}
            QLineEdit:focus {{
                border-color: {accent};
            }}
        """)

    def changeEvent(self, event):
        if event.type() == event.Type.PaletteChange or event.type() == event.Type.StyleChange:
            self.update_theme()
            # Also refresh existing chips to match the new theme state
            self.set_emails(list(self._emails))
        super().changeEvent(event)

    def _on_text_changed(self, text):
        """Detect comma or semicolon separator to commit chip."""
        if text.endswith(",") or text.endswith(";"):
            self._input.setText(text[:-1])
            self._on_commit()

    def _on_commit(self):
        """Validate and add current text as a chip."""
        text = self._input.text().strip().lower()
        if not text:
            return
        if "@" not in text or "." not in text.split("@")[-1]:
            return  # Basic validation
        if text in self._emails:
            self._input.clear()
            return  # No duplicates
        self._emails.append(text)
        self._add_chip_widget(text)
        self._input.clear()

    def _add_chip_widget(self, email):
        """Create a visual chip pill for an email."""
        is_dark = False
        win = self.window()
        if win:
            is_dark = win.palette().color(win.backgroundRole()).value() < 128
        chip_bg = "#1E293B" if is_dark else "#EEF2FF"
        chip_border = "#334155" if is_dark else "#C7D2FE"
        chip_text = "#38BDF8" if is_dark else "#3730A3"
        chip_close = "#94A3B8" if is_dark else "#6366F1"

        chip = QFrame(self._chip_container)
        chip.setStyleSheet(f"""
            QFrame {{
                background-color: {chip_bg};
                border: 1px solid {chip_border};
                border-radius: 12px;
                padding: 2px 4px;
            }}
        """)
        chip_layout = QHBoxLayout(chip)
        chip_layout.setContentsMargins(8, 2, 4, 2)
        chip_layout.setSpacing(4)

        label = QLabel(email, chip)
        label.setStyleSheet(f"color: {chip_text}; font-size: 11px; font-family: 'Segoe UI'; font-weight: 500; border: none; background: transparent;")
        chip_layout.addWidget(label)

        remove_btn = QPushButton("✕", chip)
        remove_btn.setFixedSize(16, 16)
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {chip_close};
                font-size: 11px;
                font-weight: bold;
                padding: 0;
            }}
            QPushButton:hover {{
                color: #DC2626;
            }}
        """)
        remove_btn.clicked.connect(lambda checked, e=email, c=chip: self._remove_chip(e, c))
        chip_layout.addWidget(remove_btn)

        self._flow_layout.addWidget(chip)
        self._chip_widgets.append(chip)

    def _remove_chip(self, email, chip_widget):
        """Remove a chip by email and destroy its widget."""
        if email in self._emails:
            self._emails.remove(email)
        if chip_widget in self._chip_widgets:
            self._chip_widgets.remove(chip_widget)
        self._flow_layout.removeWidget(chip_widget)
        chip_widget.deleteLater()

    def get_emails(self):
        """Return the list of entered emails."""
        return list(self._emails)

    def set_emails(self, email_list):
        """Set emails from a list, creating chips for each."""
        self.clear()
        for email in email_list:
            email = email.strip().lower()
            if email and email not in self._emails:
                self._emails.append(email)
                self._add_chip_widget(email)

    def clear(self):
        """Remove all chips and clear input."""
        self._emails.clear()
        for chip in self._chip_widgets:
            self._flow_layout.removeWidget(chip)
            chip.deleteLater()
        self._chip_widgets.clear()
        self._input.clear()

# ── Dynamic Flow Layout Component ───────────────────────────────────
class FlowLayout(QLayout):
    """Dynamic flow layout that wraps widgets dynamically based on available width."""
    def __init__(self, parent=None, margin=0, spacing=4):
        super().__init__(parent)
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self._items = []

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect, test_only):
        margins = self.contentsMargins()
        x = rect.x() + margins.left()
        y = rect.y() + margins.top()
        row_height = 0
        space_x = self.spacing()
        space_y = self.spacing()
        
        for item in self._items:
            widget = item.widget()
            if not widget:
                continue
            item_width = item.sizeHint().width()
            item_height = item.sizeHint().height()
            
            next_x = x + item_width + space_x
            if next_x - space_x > rect.right() - margins.right() and row_height > 0:
                x = rect.x() + margins.left()
                y = y + row_height + space_y
                next_x = x + item_width + space_x
                row_height = 0
                
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
                
            x = next_x
            row_height = max(row_height, item_height)
            
        return y + row_height - rect.y() + margins.bottom()

# ── Invoice Privacy Options Dialog ──────────────────────────────────
class InvoicePrivacyOptionsDialog(QDialog):
    """Custom checkbox selection prompt for sensitive data masking prior to invoice generation."""
    def __init__(self, parent=None, default_biz_email=False, default_biz_phone=False, default_client_email=False):
        super().__init__(parent)
        self.setWindowTitle("Invoice Privacy Options")
        self.setFixedSize(380, 240)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        title = QLabel("Privacy & Masking Options", self)
        title.setStyleSheet("font-family: 'Segoe UI'; font-size: 14px; font-weight: bold; color: #1A1A1A; border: none; background: transparent;")
        layout.addWidget(title)
        
        desc = QLabel("Select which sensitive details you would like to mask on this invoice:", self)
        desc.setWordWrap(True)
        desc.setStyleSheet("font-family: 'Segoe UI'; font-size: 11px; color: #64748B; border: none; background: transparent;")
        layout.addWidget(desc)
        
        # Options Group
        options_box = QFrame(self)
        options_box.setStyleSheet("QFrame { background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; }")
        options_layout = QVBoxLayout(options_box)
        options_layout.setContentsMargins(12, 8, 12, 8)
        options_layout.setSpacing(6)
        
        self.cb_biz_email = QCheckBox("Mask business contact emails (e.g. bu**@****.com)", options_box)
        self.cb_biz_email.setChecked(default_biz_email)
        self.cb_biz_email.setStyleSheet("border: none; background: transparent; font-family: 'Segoe UI'; font-size: 12px;")
        options_layout.addWidget(self.cb_biz_email)
        
        self.cb_biz_phone = QCheckBox("Mask business contact phone (e.g. +1***)", options_box)
        self.cb_biz_phone.setChecked(default_biz_phone)
        self.cb_biz_phone.setStyleSheet("border: none; background: transparent; font-family: 'Segoe UI'; font-size: 12px;")
        options_layout.addWidget(self.cb_biz_phone)
        
        self.cb_client_email = QCheckBox("Mask client contact emails (e.g. cl**@****.com)", options_box)
        self.cb_client_email.setChecked(default_client_email)
        self.cb_client_email.setStyleSheet("border: none; background: transparent; font-family: 'Segoe UI'; font-size: 12px;")
        options_layout.addWidget(self.cb_client_email)
        
        layout.addWidget(options_box)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel", self)
        cancel_btn.setObjectName("NormalButton")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        
        gen_btn = QPushButton("Generate", self)
        gen_btn.setObjectName("AccentButton")
        gen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        gen_btn.clicked.connect(self.accept)
        
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(gen_btn)
        layout.addLayout(btn_layout)

# ── Segmented Allocation Paint Bar ─────────────────────────────────
class SegmentedAllocationBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.project_breakdown = []
        self.setFixedHeight(20)

    def set_breakdown(self, breakdown):
        self.project_breakdown = breakdown
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w = self.width()
        h = self.height()
        
        total_secs = sum(pb["seconds"] for pb in self.project_breakdown)
        if total_secs <= 0:
            # Draw placeholder gray bar
            painter.setBrush(QBrush(QColor("#E2E8F0")))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(0, 0, w, h, 6, 6)
            return

        # Setup rounded corners clipping path
        path = QPainterPath()
        path.addRoundedRect(0.0, 0.0, float(w), float(h), 6.0, 6.0)
        painter.setClipPath(path)

        current_x = 0.0
        for pb in self.project_breakdown:
            pct = pb["seconds"] / total_secs
            segment_w = pct * w
            color_hex = pb.get("color", "#64748B")
            painter.setBrush(QBrush(QColor(color_hex)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(int(current_x), 0, int(segment_w + 1), h)
            current_x += segment_w

# ── Custom List App Usage Row Widget ─────────────────────────────────
class AppUsageRow(QFrame):
    def __init__(self, app_name, secs, included, tag, exe_path, on_toggle, on_tag_click, parent=None):
        super().__init__(parent)
        self.app_name = app_name
        self.secs = secs
        self.included = included
        self.tag = tag
        self.exe_path = exe_path
        self.on_toggle = on_toggle
        self.on_tag_click = on_tag_click
        
        self.setObjectName("AppUsageRow")
        self.init_ui()
        
    def init_ui(self):
        self.setFixedHeight(32)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(8)
        
        self.cb = QCheckBox(self)
        self.cb.setChecked(self.included)
        self.cb.stateChanged.connect(self._cb_changed)
        layout.addWidget(self.cb)
        
        self.icon_lbl = QLabel(self)
        self.icon_lbl.setFixedSize(16, 16)
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_lbl)
        
        self.name_lbl = QLabel(self.app_name, self)
        self.name_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 13px;")
        layout.addWidget(self.name_lbl)
        
        layout.addStretch()
        
        self.tag_lbl = QPushButton(self.tag, self)
        self.tag_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tag_lbl.setFixedWidth(90)
        self._update_tag_style()
        self.tag_lbl.clicked.connect(lambda: self.on_tag_click(self.app_name, self.tag_lbl))
        layout.addWidget(self.tag_lbl)
        
        self.time_lbl = QLabel(format_duration(self.secs), self)
        self.time_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 13px; font-weight: 500;")
        self.time_lbl.setFixedWidth(80)
        self.time_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.time_lbl)
        
        self._apply_row_style()

    def update_time(self, secs):
        self.secs = secs
        self.time_lbl.setText(format_duration(secs))

    def update_tag(self, tag):
        self.tag = tag
        self.tag_lbl.setText(tag)
        self._update_tag_style()

    def set_icon(self, pixmap):
        if pixmap:
            self.icon_lbl.setPixmap(pixmap.scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            self.icon_lbl.clear()

    def _cb_changed(self, state):
        is_checked = (state == 2)  # Qt.CheckState.Checked = 2
        self.included = is_checked
        self.on_toggle(self.app_name, is_checked)
        self._apply_row_style()

    def _update_tag_style(self):
        color = get_tag_color(self.tag)
        self.tag_lbl.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                padding: 2px 6px;
                font-family: 'Segoe UI';
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {color}E6;
            }}
        """)

    def changeEvent(self, event):
        if event.type() in (event.Type.PaletteChange, event.Type.StyleChange):
            self._apply_row_style()
        super().changeEvent(event)

    def _apply_row_style(self):
        is_dark = False
        win = self.window()
        if win:
            is_dark = win.palette().color(win.backgroundRole()).value() < 128
        if is_dark:
            text_color = "#F3F4F6" if self.included else "#64748B"
        else:
            text_color = "#1A1A1A" if self.included else "#ABABAB"
            
        self.name_lbl.setStyleSheet(f"color: {text_color}; font-family: 'Segoe UI'; font-size: 13px;")
        self.time_lbl.setStyleSheet(f"color: {text_color}; font-family: 'Segoe UI'; font-size: 13px; font-weight: 500;")
