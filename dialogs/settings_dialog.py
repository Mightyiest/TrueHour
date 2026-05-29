import os
import shutil
import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QWidget,
    QScrollArea, QCheckBox, QFormLayout, QLineEdit, QComboBox, QGroupBox,
    QPushButton, QMessageBox, QFileDialog, QSizePolicy, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize

from widgets.custom_widgets import EmailChipWidget, QRThumbnailWidget
from theme import TEXT_SECONDARY, get_tag_color
from config import get_app_data_dir, open_file
from tracker import AUTO_EXCLUDE_FILE, create_auto_excluded_if_missing
from appinfo import OVERRIDES_FILE

logger = logging.getLogger(__name__)

class SettingsDialog(QDialog):
    manage_categories_requested = pyqtSignal()
    about_requested = pyqtSignal()
    reload_exclusions_requested = pyqtSignal()
    settings_saved = pyqtSignal(dict)

    def __init__(self, current_settings, parent=None):
        super().__init__(parent)
        self.settings = dict(current_settings)  # copy to avoid mutating directly
        self.setWindowTitle("Settings")
        self._center_window(520, 650)
        
        self._qr_paths_local = list(self.settings.get("qr_code_paths", []))
        self._qr_links_local = dict(self.settings.get("qr_code_links", {}))
        self._qr_thumb_refs = []
        
        self._build_ui()

    def _center_window(self, width, height):
        self.resize(width, height)
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - width) // 2
        y = (screen.height() - height) // 2
        self.move(x, y)

    def set_reload_status(self, success):
        if success:
            self.reload_status_lbl.setText("✓ Reloaded")
            self.reload_status_lbl.setStyleSheet("color: #0F7B0F;")
        else:
            self.reload_status_lbl.setText("✗ Failed")
            self.reload_status_lbl.setStyleSheet("color: #C42B1C;")
        QTimer.singleShot(2000, lambda: self.reload_status_lbl.setText(" "))

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        
        title = QLabel("Settings", self)
        title.setStyleSheet("font-family: 'Segoe UI'; font-size: 15px; font-weight: bold; color: #1A1A1A;")
        layout.addWidget(title)
        
        # QTabWidget for settings categories
        settings_tabs = QTabWidget(self)
        settings_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #E2E8F0;
                background-color: #FFFFFF;
                border-radius: 8px;
            }
            QTabBar::tab {
                background-color: #F8FAFC;
                color: #475569;
                padding: 6px 16px;
                font-family: 'Segoe UI';
                font-size: 12px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                border: 1px solid #E2E8F0;
                border-bottom: none;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #FFFFFF;
                color: #0078D4;
                font-weight: bold;
                border: 1px solid #CBD5E1;
                border-bottom: none;
            }
        """)
        
        # ── Tab 1: General Settings ──────────────────────────────────
        tab_general = QWidget()
        tg_main_layout = QVBoxLayout(tab_general)
        tg_main_layout.setContentsMargins(0, 0, 0, 0)
        tg_main_layout.setSpacing(0)
        
        scroll_general = QScrollArea(tab_general)
        scroll_general.setWidgetResizable(True)
        scroll_general.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_general.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        scroll_general_content = QWidget()
        tg_layout = QVBoxLayout(scroll_general_content)
        tg_layout.setContentsMargins(12, 12, 12, 12)
        tg_layout.setSpacing(6)
        
        self.cb_confirm = QCheckBox("Always ask for confirmation before closing", scroll_general_content)
        self.cb_confirm.setChecked(self.settings.get("confirm_on_close", True))
        self.cb_confirm.setStyleSheet("font-family: 'Segoe UI'; font-size: 13px;")
        tg_layout.addWidget(self.cb_confirm)
        
        # Checkbox for Developer Options
        self.cb_dev = QCheckBox("Enable Developer Options (Debug Console)", scroll_general_content)
        self.cb_dev.setChecked(self.settings.get("developer_mode", False))
        self.cb_dev.setStyleSheet("font-family: 'Segoe UI'; font-size: 13px;")
        tg_layout.addWidget(self.cb_dev)
        
        form_general = QFormLayout()
        form_general.setSpacing(6)
        
        self.min_sec_entry = QLineEdit(scroll_general_content)
        self.min_sec_entry.setText(str(self.settings.get("min_track_seconds", 2)))
        form_general.addRow("Min activity threshold (secs):", self.min_sec_entry)
        
        self.auto_save_entry = QLineEdit(scroll_general_content)
        self.auto_save_entry.setText(str(self.settings.get("auto_save_seconds", 10)))
        form_general.addRow("Auto-save interval (secs):", self.auto_save_entry)
        
        # Idle row
        idle_row = QHBoxLayout()
        idle_row.setSpacing(4)
        _idle_total = self.settings.get("idle_threshold_seconds_total", 120)
        _idle_m_def = _idle_total // 60
        _idle_s_def = _idle_total % 60
        
        self.idle_min_entry = QLineEdit(scroll_general_content)
        self.idle_min_entry.setFixedWidth(40)
        self.idle_min_entry.setText(str(_idle_m_def))
        idle_row.addWidget(self.idle_min_entry)
        idle_row.addWidget(QLabel("min"))
        
        self.idle_sec_entry = QLineEdit(scroll_general_content)
        self.idle_sec_entry.setFixedWidth(40)
        self.idle_sec_entry.setText(str(_idle_s_def))
        idle_row.addWidget(self.idle_sec_entry)
        idle_row.addWidget(QLabel("sec"))
        idle_row.addStretch()
        
        form_general.addRow("Idle auto-pause:", idle_row)
        
        # Billing Group details inside general tab
        currency_options = [
            "$ (USD)", "€ (EUR)", "£ (GBP)", "¥ (JPY/CNY)", "₱ (PHP)", "₹ (INR)", 
            "₽ (RUB)", "₩ (KRW)", "₫ (VND)", "฿ (THB)", "₪ (ILS)", "₺ (TRY)", 
            "Rp (IDR)", "RM (MYR)", "R$ (BRL)", "C$ (CAD)", "A$ (AUD)", "S$ (SGD)", 
            "NZ$ (NZD)", "CHF (CHF)", "kr (SEK/NOK)", "zł (PLN)", "Kč (CZK)", 
            "Ft (HUF)", "lei (RON)", "лв (BGN)", "₴ (UAH)", "R (ZAR)"
        ]
        self.curr_combo = QComboBox(scroll_general_content)
        self.curr_combo.addItems(currency_options)
        curr_symbol = self.settings.get("currency_symbol", "$")
        matched = [c for c in currency_options if c.startswith(curr_symbol)]
        if matched:
            self.curr_combo.setCurrentText(matched[0])
        else:
            self.curr_combo.setCurrentText(curr_symbol)
        form_general.addRow("Currency symbol:", self.curr_combo)
        
        self.rate_entry = QLineEdit(scroll_general_content)
        self.rate_entry.setText(f"{self.settings.get('hourly_rate', 0.0):.2f}")
        form_general.addRow("Hourly rate:", self.rate_entry)
        
        tg_layout.addLayout(form_general)
        
        # Config Files Group
        config_box = QGroupBox("Configuration & Categories", scroll_general_content)
        config_layout = QVBoxLayout(config_box)
        config_layout.setContentsMargins(8, 8, 8, 8)
        config_layout.setSpacing(4)
        
        def _open_file(filepath):
            logger.info(f"[Action] Opened config file: {os.path.basename(filepath)}")
            if filepath == AUTO_EXCLUDE_FILE:
                try:
                    create_auto_excluded_if_missing()
                except Exception:
                    pass
            elif filepath == OVERRIDES_FILE:
                try:
                    from appinfo import _load_name_overrides
                    _load_name_overrides()
                except Exception:
                    pass

            if not os.path.exists(filepath):
                try:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write("# Configuration file created.\n")
                except Exception: 
                    pass
            try: 
                open_file(filepath)
            except Exception: 
                QMessageBox.critical(self, "Error", f"Could not open: {filepath}")

        btn_overrides = QPushButton("Edit Name Overrides", scroll_general_content)
        btn_overrides.setObjectName("NormalButton")
        btn_overrides.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_overrides.clicked.connect(lambda: _open_file(OVERRIDES_FILE))
        config_layout.addWidget(btn_overrides)
        
        excl_row = QHBoxLayout()
        btn_excl = QPushButton("Edit Auto-Exclusions", scroll_general_content)
        btn_excl.setObjectName("NormalButton")
        btn_excl.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_excl.clicked.connect(lambda: _open_file(AUTO_EXCLUDE_FILE))
        excl_row.addWidget(btn_excl, 1)
        
        btn_reload = QPushButton("🔄 Reload", scroll_general_content)
        btn_reload.setObjectName("NormalButton")
        btn_reload.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.reload_status_lbl = QLabel(" ", scroll_general_content)
        self.reload_status_lbl.setStyleSheet("font-size: 11px; font-weight: bold;")
        
        btn_reload.clicked.connect(lambda: self.reload_exclusions_requested.emit())
        excl_row.addWidget(btn_reload)
        excl_row.addWidget(self.reload_status_lbl)
        config_layout.addLayout(excl_row)
        
        btn_categories = QPushButton("Manage Project Categories...", scroll_general_content)
        btn_categories.setObjectName("NormalButton")
        btn_categories.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_categories.clicked.connect(lambda: self.manage_categories_requested.emit())
        config_layout.addWidget(btn_categories)

        btn_about = QPushButton("About FocusLog", scroll_general_content)
        btn_about.setObjectName("NormalButton")
        btn_about.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_about.clicked.connect(lambda: self.about_requested.emit())
        config_layout.addWidget(btn_about)
        
        tg_layout.addWidget(config_box)
        tg_layout.addStretch()
        
        scroll_general.setWidget(scroll_general_content)
        tg_main_layout.addWidget(scroll_general)
        
        # ── Tab 2: Billing & Invoicing Details ────────────────────────
        tab_invoice = QWidget()
        ti_layout = QVBoxLayout(tab_invoice)
        ti_layout.setContentsMargins(0, 0, 0, 0)
        ti_layout.setSpacing(0)
        
        scroll_invoice = QScrollArea(tab_invoice)
        scroll_invoice.setWidgetResizable(True)
        scroll_invoice.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_invoice.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        scroll_invoice_content = QWidget()
        scroll_invoice_layout = QVBoxLayout(scroll_invoice_content)
        scroll_invoice_layout.setContentsMargins(12, 12, 12, 12)
        scroll_invoice_layout.setSpacing(10)
        
        # Freelancer Business Profile
        biz_box = QGroupBox("Business Profile Details", scroll_invoice_content)
        biz_layout = QFormLayout(biz_box)
        biz_layout.setSpacing(6)
        
        self.business_name_entry = QLineEdit(biz_box)
        self.business_name_entry.setText(self.settings.get("business_name", ""))
        biz_layout.addRow("Business Name:", self.business_name_entry)
        
        # Email Chip Widget for business contact emails
        self.business_email_chips = EmailChipWidget(biz_box)
        self.business_email_chips.set_emails(self.settings.get("business_emails", []))
        biz_layout.addRow("Contact Emails:", self.business_email_chips)
        
        self.business_phone_entry = QLineEdit(biz_box)
        self.business_phone_entry.setText(self.settings.get("business_phone", ""))
        biz_layout.addRow("Contact Phone:", self.business_phone_entry)
        
        self.business_address_entry = QLineEdit(biz_box)
        self.business_address_entry.setText(self.settings.get("business_address", ""))
        biz_layout.addRow("Billing Address:", self.business_address_entry)
        
        self.business_payment_entry = QLineEdit(biz_box)
        self.business_payment_entry.setPlaceholderText("e.g. IBAN: US12 3456... or PayPal: ...")
        self.business_payment_entry.setText(self.settings.get("business_payment", ""))
        biz_layout.addRow("Payment Details:", self.business_payment_entry)
        
        scroll_invoice_layout.addWidget(biz_box)
        
        # Default Client Profile
        client_box = QGroupBox("Default Client Profile", scroll_invoice_content)
        client_layout = QFormLayout(client_box)
        client_layout.setSpacing(6)
        
        self.client_name_entry = QLineEdit(client_box)
        self.client_name_entry.setText(self.settings.get("client_name", ""))
        client_layout.addRow("Client Name:", self.client_name_entry)
        
        # Email Chip Widget for client contact emails
        self.client_email_chips = EmailChipWidget(client_box)
        self.client_email_chips.set_emails(self.settings.get("client_emails", []))
        client_layout.addRow("Client Emails:", self.client_email_chips)
        
        self.client_address_entry = QLineEdit(client_box)
        self.client_address_entry.setText(self.settings.get("client_address", ""))
        client_layout.addRow("Client Address:", self.client_address_entry)
        
        scroll_invoice_layout.addWidget(client_box)
        
        # Logo Profile Configuration
        logo_box = QGroupBox("Invoice Business Logo", scroll_invoice_content)
        logo_layout = QVBoxLayout(logo_box)
        logo_layout.setSpacing(4)
        
        logo_row = QHBoxLayout()
        self.logo_path_entry = QLineEdit(logo_box)
        self.logo_path_entry.setText(self.settings.get("business_logo_path", ""))
        logo_row.addWidget(self.logo_path_entry, 1)
        
        def _browse_logo():
            logger.info("[Action] Browsing for business logo image")
            path, _ = QFileDialog.getOpenFileName(self, "Select Business Logo Image", "", "Image files (*.png *.jpg *.jpeg)")
            if path:
                self.logo_path_entry.setText(path)
                
        browse_logo_btn = QPushButton("Browse...", logo_box)
        browse_logo_btn.setObjectName("NormalButton")
        browse_logo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_logo_btn.clicked.connect(_browse_logo)
        logo_row.addWidget(browse_logo_btn)
        logo_layout.addLayout(logo_row)
        
        logo_spec_lbl = QLabel("Image Spec: PNG, JPG, or JPEG. Max size: 250px (w) x 80px (h). Proportionally resized automatically.", logo_box)
        logo_spec_lbl.setWordWrap(True)
        logo_spec_lbl.setStyleSheet("color: #64748B; font-size: 10px; font-family: 'Segoe UI';")
        logo_layout.addWidget(logo_spec_lbl)
        
        scroll_invoice_layout.addWidget(logo_box)
        
        # ── Payment QR Codes Section ─────────────────────────────────
        qr_box = QGroupBox("Payment QR Codes", scroll_invoice_content)
        self.qr_box_layout = QVBoxLayout(qr_box)
        self.qr_box_layout.setSpacing(6)
        
        self.qr_thumbs_widget = QWidget(qr_box)
        self.qr_thumbs_layout = QHBoxLayout(self.qr_thumbs_widget)
        self.qr_thumbs_layout.setContentsMargins(0, 0, 0, 0)
        self.qr_thumbs_layout.setSpacing(8)
        
        self._refresh_qr_thumbnails()
        self.qr_box_layout.addWidget(self.qr_thumbs_widget)
        
        def _add_qr_code():
            if len(self._qr_paths_local) >= 4:
                QMessageBox.information(self, "QR Limit", "Maximum of 4 QR code images allowed.")
                return
            path, _ = QFileDialog.getOpenFileName(self, "Select Payment QR Code Image", "", "Image files (*.png *.jpg *.jpeg)")
            if not path:
                return
            qr_dir = os.path.join(get_app_data_dir(), "qr_codes")
            os.makedirs(qr_dir, exist_ok=True)
            fname = f"qr_{len(self._qr_paths_local)+1}_{os.path.basename(path)}"
            dest = os.path.join(qr_dir, fname)
            try:
                shutil.copy2(path, dest)
                logger.info(f"[Action] Added payment QR code: {fname}")
                self._qr_paths_local.append(fname)
                self._refresh_qr_thumbnails()
            except Exception as ex:
                QMessageBox.critical(self, "Error", f"Failed to copy QR image:\n{ex}")
        
        add_qr_btn = QPushButton("+ Add QR Code", qr_box)
        add_qr_btn.setObjectName("NormalButton")
        add_qr_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_qr_btn.clicked.connect(_add_qr_code)
        self.qr_box_layout.addWidget(add_qr_btn)
        
        qr_spec_lbl = QLabel("Upload up to 4 payment QR code images (PNG/JPG). They will appear in generated invoices at 140×140px.", qr_box)
        qr_spec_lbl.setWordWrap(True)
        qr_spec_lbl.setStyleSheet("color: #64748B; font-size: 10px; font-family: 'Segoe UI';")
        self.qr_box_layout.addWidget(qr_spec_lbl)
        
        scroll_invoice_layout.addWidget(qr_box)
        
        # ── Sensitive Data Masking Toggles ────────────────────────────
        mask_box = QGroupBox("Privacy Settings", scroll_invoice_content)
        mask_layout = QVBoxLayout(mask_box)
        mask_layout.setSpacing(6)
        
        self.mask_biz_email_cb = QCheckBox("Mask business contact emails by default", mask_box)
        self.mask_biz_email_cb.setChecked(self.settings.get("mask_business_emails", False))
        self.mask_biz_email_cb.setStyleSheet("font-family: 'Segoe UI'; font-size: 12px;")
        mask_layout.addWidget(self.mask_biz_email_cb)
        
        self.mask_biz_phone_cb = QCheckBox("Mask business contact phone number by default", mask_box)
        self.mask_biz_phone_cb.setChecked(self.settings.get("mask_business_phone", False))
        self.mask_biz_phone_cb.setStyleSheet("font-family: 'Segoe UI'; font-size: 12px;")
        mask_layout.addWidget(self.mask_biz_phone_cb)
        
        self.mask_client_email_cb = QCheckBox("Mask client contact emails by default", mask_box)
        self.mask_client_email_cb.setChecked(self.settings.get("mask_client_emails", False))
        self.mask_client_email_cb.setStyleSheet("font-family: 'Segoe UI'; font-size: 12px;")
        mask_layout.addWidget(self.mask_client_email_cb)
        
        mask_hint = QLabel("When enabled, sensitive contact details (emails, phone) are masked on the generated invoice. You can override these per-invoice.", mask_box)
        mask_hint.setWordWrap(True)
        mask_hint.setStyleSheet("color: #64748B; font-size: 10px; font-family: 'Segoe UI';")
        mask_layout.addWidget(mask_hint)
        
        scroll_invoice_layout.addWidget(mask_box)
        
        scroll_invoice.setWidget(scroll_invoice_content)
        ti_layout.addWidget(scroll_invoice)
        
        # Add Tabs to Widget
        settings_tabs.addTab(tab_general, "General && Controls")
        settings_tabs.addTab(tab_invoice, "Billing && Invoices")
        layout.addWidget(settings_tabs)
        
        # Bottom Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        save_btn = QPushButton("Save Settings", self)
        save_btn.setObjectName("AccentButton")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self._save_and_close)
        btn_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("Cancel", self)
        cancel_btn.setObjectName("NormalButton")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)

    def _refresh_qr_thumbnails(self):
        """Rebuild QR thumbnail strip from _qr_paths_local."""
        while self.qr_thumbs_layout.count() > 0:
            item = self.qr_thumbs_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._qr_thumb_refs.clear()
        
        qr_dir = os.path.join(get_app_data_dir(), "qr_codes")
        for qr_filename in self._qr_paths_local:
            qr_full_path = os.path.join(qr_dir, qr_filename)
            if not os.path.exists(qr_full_path):
                continue
                
            initial_url = self._qr_links_local.get(qr_filename, "")
            
            def _remove_qr(fname=qr_filename):
                logger.info(f"[Action] Removed payment QR code: {fname}")
                if fname in self._qr_paths_local:
                    self._qr_paths_local.remove(fname)
                self._qr_links_local.pop(fname, None)
                self._refresh_qr_thumbnails()
                
            def _link_changed(fname, new_url):
                if new_url:
                    self._qr_links_local[fname] = new_url
                else:
                    self._qr_links_local.pop(fname, None)
                    
            thumb_widget = QRThumbnailWidget(
                qr_filename=qr_filename,
                qr_full_path=qr_full_path,
                initial_url=initial_url,
                on_remove=lambda checked=False, fname=qr_filename: _remove_qr(fname),
                on_link_changed=_link_changed,
                parent=self.qr_thumbs_widget
            )
            
            self.qr_thumbs_layout.addWidget(thumb_widget)
            self._qr_thumb_refs.append(thumb_widget)
        
        self.qr_thumbs_layout.addStretch()

    def _save_and_close(self):
        try:
            logger.info(f"[Action] Adjusted Settings:")
            logger.info(f"  - Confirm close: {self.cb_confirm.isChecked()}")
            logger.info(f"  - Min track seconds: {self.min_sec_entry.text()}")
            logger.info(f"  - Auto-save seconds: {self.auto_save_entry.text()}")
            logger.info(f"  - Hourly rate: {self.rate_entry.text()}")
            logger.info(f"  - Developer mode: {self.cb_dev.isChecked()}")

            self.settings["confirm_on_close"] = self.cb_confirm.isChecked()
            self.settings["min_track_seconds"] = int(self.min_sec_entry.text())
            self.settings["auto_save_seconds"] = int(self.auto_save_entry.text())
            
            raw_symbol = self.curr_combo.currentText().strip()
            self.settings["currency_symbol"] = raw_symbol.split()[0].split('(')[0].strip() if raw_symbol else "$"
            self.settings["hourly_rate"] = float(self.rate_entry.text().strip() or 0)
            
            _im = max(0, int(self.idle_min_entry.text().strip() or 0))
            _is = max(0, min(59, int(self.idle_sec_entry.text().strip() or 0)))
            self.settings["idle_threshold_seconds_total"] = _im * 60 + _is
            
            self.settings["business_name"] = self.business_name_entry.text().strip()
            self.settings["business_emails"] = self.business_email_chips.get_emails()
            self.settings["business_phone"] = self.business_phone_entry.text().strip()
            self.settings["business_address"] = self.business_address_entry.text().strip()
            self.settings["business_payment"] = self.business_payment_entry.text().strip()
            
            self.settings["client_name"] = self.client_name_entry.text().strip()
            self.settings["client_emails"] = self.client_email_chips.get_emails()
            self.settings["client_address"] = self.client_address_entry.text().strip()
            
            self.settings["business_logo_path"] = self.logo_path_entry.text().strip()
            self.settings["qr_code_paths"] = list(self._qr_paths_local)
            self.settings["qr_code_links"] = dict(self._qr_links_local)
            
            self.settings["mask_business_emails"] = self.mask_biz_email_cb.isChecked()
            self.settings["mask_business_phone"] = self.mask_biz_phone_cb.isChecked()
            self.settings["mask_client_emails"] = self.mask_client_email_cb.isChecked()
            self.settings["mask_sensitive_data"] = (
                self.settings["mask_business_emails"] or
                self.settings["mask_business_phone"] or
                self.settings["mask_client_emails"]
            )
            self.settings["developer_mode"] = self.cb_dev.isChecked()
            
            self.settings_saved.emit(self.settings)
            self.accept()
        except ValueError:
            QMessageBox.critical(self, "Error", "Please enter valid numeric values.")
