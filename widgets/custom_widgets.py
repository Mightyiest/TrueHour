"""
TrueHour — Custom Reusable UI Widgets & Dialog Component Leaf Nodes
"""

from PyQt6.QtWidgets import (
    QWidget,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QCheckBox,
    QDialog,
    QLayout,
    QInputDialog,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, QSize, QPoint, QRect
from PyQt6.QtGui import QPixmap, QPainter, QBrush, QColor, QPainterPath

from theme import get_svg_icon, get_tag_color
from assets import EDIT_SVG
from report import format_duration


# ── QR Code Thumbnail Widget with Hover Edit ──────────────────────────
class QRThumbnailWidget(QFrame):
    """Custom QFrame for QR code thumbnail displaying with hover and edit/delete overlay."""

    def __init__(
        self,
        qr_filename,
        qr_full_path,
        initial_url,
        on_remove,
        on_link_changed,
        parent=None,
    ):
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
            pix = pix.scaled(
                56,
                56,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
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
        self.link_indicator.setStyleSheet(
            "background-color: #0F7B0F; border-radius: 5px; border: 1px solid white;"
        )
        self.link_indicator.move(4, 4)
        self.link_indicator.setVisible(bool(self.link_url))
        self.link_indicator.setToolTip(
            f"Link: {self.link_url}" if self.link_url else ""
        )

    def _edit_link(self):
        url, ok = QInputDialog.getText(
            self,
            "Edit QR Code Link",
            "Enter hyperlink for this QR code (when clicked on invoice):",
            QLineEdit.EchoMode.Normal,
            self.link_url,
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
        if not hasattr(self, "_input"):
            return
        win = self.window()
        theme_style = "light"
        if win:
            theme_style = getattr(
                win,
                "theme_style",
                "modern-dark"
                if (win.palette().color(win.backgroundRole()).value() < 128)
                else "light",
            )

        if theme_style == "classic-dark":
            bg_widget = "#1e1e1e"
            border_color = "#333333"
            text_color = "#e0e0e0"
            accent = "#d1d5db"
        elif theme_style == "modern-dark":
            bg_widget = "#16161A"
            border_color = "#232329"
            text_color = "#EDEDED"
            accent = "#2563EB"
        else:  # light
            bg_widget = "#FFFFFF"
            border_color = "#E2E8F0"
            text_color = "#0F172A"
            accent = "#0078D4"

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
        if (
            event.type() == event.Type.PaletteChange
            or event.type() == event.Type.StyleChange
        ):
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
        win = self.window()
        theme_style = "light"
        if win:
            theme_style = getattr(
                win,
                "theme_style",
                "modern-dark"
                if (win.palette().color(win.backgroundRole()).value() < 128)
                else "light",
            )

        if theme_style == "classic-dark":
            chip_bg = "#262626"
            chip_border = "#333333"
            chip_text = "#d1d5db"
            chip_close = "#888"
        elif theme_style == "modern-dark":
            chip_bg = "#232329"
            chip_border = "#2a2a35"
            chip_text = "#EDEDED"
            chip_close = "#a3a3a3"
        else:  # light
            chip_bg = "#EEF2FF"
            chip_border = "#C7D2FE"
            chip_text = "#3730A3"
            chip_close = "#6366F1"

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
        label.setStyleSheet(
            f"color: {chip_text}; font-size: 11px; font-family: 'Segoe UI'; font-weight: 500; border: none; background: transparent;"
        )
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
        remove_btn.clicked.connect(
            lambda checked, e=email, c=chip: self._remove_chip(e, c)
        )
        chip_layout.addWidget(remove_btn)

        self._flow_layout.addWidget(chip)
        self._chip_widgets.append(chip)

    def _remove_chip(self, email, chip_widget):
        """Remove a chip by email and destroy its widget."""
        if email in self._emails:
            self._emails.remove(email)
        if chip_widget in self._chip_widgets:
            self._chip_widgets.remove(chip_widget)
        chip_widget.hide()
        self._flow_layout.removeWidget(chip_widget)
        chip_widget.setParent(None)
        chip_widget.deleteLater()
        self._flow_layout.invalidate()

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
            chip.hide()
            self._flow_layout.removeWidget(chip)
            chip.setParent(None)
            chip.deleteLater()
        self._chip_widgets.clear()
        self._input.clear()
        self._flow_layout.invalidate()


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
        size += QSize(
            margins.left() + margins.right(), margins.top() + margins.bottom()
        )
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

    def __init__(
        self,
        parent=None,
        default_biz_email=False,
        default_biz_phone=False,
        default_client_email=False,
        is_dark=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Invoice Options & Custom Charges")
        self.setFixedSize(380, 370)

        # Robust theme detection
        self.theme_style = "light"
        if parent:
            if hasattr(parent, "theme_style"):
                self.theme_style = parent.theme_style
            elif hasattr(parent, "settings") and isinstance(parent.settings, dict):
                self.theme_style = parent.settings.get(
                    "theme_style",
                    "modern-dark"
                    if parent.settings.get("dark_mode", False)
                    else "light",
                )
            elif hasattr(parent, "dark_mode"):
                self.theme_style = "modern-dark" if parent.dark_mode else "light"

        if is_dark is not None:
            if isinstance(is_dark, str):
                self.theme_style = is_dark
            else:
                self.theme_style = "modern-dark" if is_dark else "light"

        self.is_dark = self.theme_style in ["modern-dark", "classic-dark"]

        # Apply dialog-level Fluent Design styling
        from theme import (
            get_qss_style,
            get_dark_palette,
            get_light_palette,
            ensure_checkmark_icon,
        )

        qss = get_qss_style(self.theme_style).replace(
            "CHECKMARK_PATH", ensure_checkmark_icon(self.theme_style)
        )
        self.setStyleSheet(qss)
        self.setPalette(
            get_dark_palette(self.theme_style) if self.is_dark else get_light_palette()
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.title = QLabel("Invoice Options & Custom Charges", self)
        self.title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(self.title)

        self.desc = QLabel(
            "Configure privacy masking and optional manual line items:",
            self,
        )
        self.desc.setWordWrap(True)
        layout.addWidget(self.desc)

        # Options Group
        self.options_box = QFrame(self)
        options_layout = QVBoxLayout(self.options_box)
        options_layout.setContentsMargins(12, 8, 12, 8)
        options_layout.setSpacing(6)

        self.cb_biz_email = QCheckBox(
            "Mask business contact emails (e.g. bu**@****.com)", self.options_box
        )
        self.cb_biz_email.setChecked(default_biz_email)
        options_layout.addWidget(self.cb_biz_email)

        self.cb_biz_phone = QCheckBox(
            "Mask business contact phone (e.g. +1***)", self.options_box
        )
        self.cb_biz_phone.setChecked(default_biz_phone)
        options_layout.addWidget(self.cb_biz_phone)

        self.cb_client_email = QCheckBox(
            "Mask client contact emails (e.g. cl**@****.com)", self.options_box
        )
        self.cb_client_email.setChecked(default_client_email)
        options_layout.addWidget(self.cb_client_email)

        layout.addWidget(self.options_box)

        # Additional Payment Group
        self.add_payment_box = QFrame(self)
        add_layout = QVBoxLayout(self.add_payment_box)
        add_layout.setContentsMargins(12, 8, 12, 8)
        add_layout.setSpacing(6)

        add_title = QLabel("Additional Payment / Custom Fee (Optional):", self.add_payment_box)
        add_title.setStyleSheet("font-weight: bold; font-size: 11px;")
        add_layout.addWidget(add_title)

        fields_row = QHBoxLayout()
        fields_row.setSpacing(6)

        self.additional_amount_input = QLineEdit(self.add_payment_box)
        self.additional_amount_input.setPlaceholderText("Amount ($)")
        self.additional_amount_input.setFixedWidth(90)
        fields_row.addWidget(self.additional_amount_input)

        self.additional_desc_input = QLineEdit(self.add_payment_box)
        self.additional_desc_input.setPlaceholderText("Description (e.g. Bonus, Setup Fee)")
        fields_row.addWidget(self.additional_desc_input)

        add_layout.addLayout(fields_row)
        layout.addWidget(self.add_payment_box)

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

    def get_additional_payment(self):
        txt_amount = (
            self.additional_amount_input.text()
            .strip()
            .replace("$", "")
            .replace(",", "")
        )
        txt_desc = self.additional_desc_input.text().strip()
        if not txt_amount:
            return None
        try:
            val = float(txt_amount)
            if val > 0:
                desc = txt_desc if txt_desc else "Additional Payment"
                return (desc, val)
        except ValueError:
            pass
        return None

    def changeEvent(self, event):
        if event.type() in (event.Type.PaletteChange, event.Type.StyleChange):
            # Recalculate is_dark if theme dynamically changes
            win = self.window()
            if win:
                self.is_dark = win.palette().color(win.backgroundRole()).value() < 128
            self._apply_theme()
        super().changeEvent(event)

    def _apply_theme(self):
        if not hasattr(self, "title"):
            return

        if self.theme_style == "classic-dark":
            title_color = "#e0e0e0"
            desc_color = "#aaa"
            box_bg = "#262626"
            box_border = "#333333"
            cb_color = "#e0e0e0"
        elif self.theme_style == "modern-dark":
            title_color = "#EDEDED"
            desc_color = "#A3A3A3"
            box_bg = "#16161A"
            box_border = "#232329"
            cb_color = "#EDEDED"
        else:  # light
            title_color = "#1A1A1A"
            desc_color = "#64748B"
            box_bg = "#F8FAFC"
            box_border = "#E2E8F0"
            cb_color = "#1A1A1A"

        self.title.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 14px; font-weight: bold; color: {title_color}; border: none; background: transparent;"
        )
        self.desc.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 11px; color: {desc_color}; border: none; background: transparent;"
        )
        self.options_box.setStyleSheet(
            f"QFrame {{ background-color: {box_bg}; border: 1px solid {box_border}; border-radius: 8px; }}"
        )

        cb_style = f"border: none; background: transparent; font-family: 'Segoe UI'; font-size: 12px; color: {cb_color};"
        self.cb_biz_email.setStyleSheet(cb_style)
        self.cb_biz_phone.setStyleSheet(cb_style)
        self.cb_client_email.setStyleSheet(cb_style)


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


# ── Elided Label Component ───────────────────────────────────────────
class ElidedLabel(QLabel):
    """A QLabel that automatically elides text that is too long to fit."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.full_text = text
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(50)

    def setText(self, text):
        self.full_text = text
        self._update_elided()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_elided()

    def _update_elided(self):
        fm = self.fontMetrics()
        elided = fm.elidedText(
            self.full_text, Qt.TextElideMode.ElideRight, self.width()
        )
        super().setText(elided)

    def sizeHint(self):
        fm = self.fontMetrics()
        width = fm.horizontalAdvance(self.full_text) + 8
        height = super().sizeHint().height()
        return QSize(width, height)


# ── Custom List App Usage Row Widget ─────────────────────────────────
class AppUsageRow(QFrame):
    def __init__(
        self,
        app_name,
        secs,
        included,
        tag,
        exe_path,
        on_toggle,
        on_tag_click,
        on_context_menu=None,
        parent=None,
    ):
        super().__init__(parent)
        self.app_name = app_name
        self.secs = secs
        self.included = included
        self.tag = tag
        self.exe_path = exe_path
        self.on_toggle = on_toggle
        self.on_tag_click = on_tag_click
        self.on_context_menu = on_context_menu
        self._icon_loaded = False

        self.setObjectName("AppUsageRow")
        self.init_ui()

    def contextMenuEvent(self, event):
        if self.on_context_menu:
            self.on_context_menu(self.app_name, self.exe_path, event.globalPos())
            event.accept()
        else:
            super().contextMenuEvent(event)

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

        self.name_lbl = ElidedLabel(self.app_name, self)
        self.name_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 13px;")
        layout.addWidget(self.name_lbl)

        layout.addStretch()

        self.tag_lbl = QPushButton(self.tag, self)
        self.tag_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tag_lbl.setFixedWidth(90)
        self._update_tag_style()
        self.tag_lbl.clicked.connect(
            lambda: self.on_tag_click(self.app_name, self.tag_lbl)
        )
        layout.addWidget(self.tag_lbl)

        self.time_lbl = QLabel(format_duration(self.secs), self)
        self.time_lbl.setStyleSheet(
            "font-family: 'Segoe UI'; font-size: 13px; font-weight: 500;"
        )
        self.time_lbl.setFixedWidth(80)
        self.time_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
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
            self.icon_lbl.setPixmap(
                pixmap.scaled(
                    16,
                    16,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            self.icon_lbl.clear()

    def _cb_changed(self, state):
        is_checked = state == 2  # Qt.CheckState.Checked = 2
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
        if not hasattr(self, "name_lbl"):
            return
        win = self.window()
        theme_style = "light"
        if win:
            theme_style = getattr(
                win,
                "theme_style",
                "modern-dark"
                if (win.palette().color(win.backgroundRole()).value() < 128)
                else "light",
            )

        if theme_style == "classic-dark":
            text_color = "#e0e0e0" if self.included else "#64748B"
        elif theme_style == "modern-dark":
            text_color = "#EDEDED" if self.included else "#555555"
        else:  # light
            text_color = "#1A1A1A" if self.included else "#ABABAB"

        self.name_lbl.setStyleSheet(
            f"color: {text_color}; font-family: 'Segoe UI'; font-size: 13px;"
        )
        self.time_lbl.setStyleSheet(
            f"color: {text_color}; font-family: 'Segoe UI'; font-size: 13px; font-weight: 500;"
        )
