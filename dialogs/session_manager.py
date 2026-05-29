import os
import time
import json
import glob
import logging
from datetime import datetime
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTabWidget,
    QScrollArea, QWidget, QFrame, QCheckBox, QLabel, QSizePolicy,
    QFileDialog, QMessageBox, QInputDialog, QLineEdit, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QRectF
from PyQt6.QtGui import QIcon, QPixmap, QColor, QPainter, QPen

from config import get_app_data_dir, open_file, send_to_trash

logger = logging.getLogger(__name__)
from report import (
    load_session_json, merge_sessions_for_invoice, generate_invoice_html
)
from theme import (
    TEXT_SECONDARY, get_svg_icon
)
from assets import RENAME_SVG, TRASH_SVG, RESTORE_SVG
from widgets.custom_widgets import InvoicePrivacyOptionsDialog

class SessionManagerDialog(QDialog):
    resume_requested = pyqtSignal(str)             # filepath to resume
    view_report_requested = pyqtSignal(dict)       # report dict
    export_csv_history_requested = pyqtSignal()

    def __init__(self, settings_data, tracker, parent=None):
        super().__init__(parent)
        self.settings = settings_data
        self.tracker = tracker
        self.setWindowTitle("Session Manager")
        self._center_window(520, 540)
        
        self.selected_sessions = set()
        self._build_ui()

    def _center_window(self, width, height):
        self.resize(width, height)
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - width) // 2
        y = (screen.height() - height) // 2
        self.move(x, y)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        
        self.tab_widget = QTabWidget(self)
        self.tab_widget.setObjectName("SessionTabs")

        self.edit_btn = QPushButton("Edit", self)
        self.edit_btn.setCheckable(True)
        self.edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.edit_btn.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
                padding: 4px 12px;
                font-family: 'Segoe UI';
                font-size: 12px;
                font-weight: bold;
                color: #475569;
            }
            QPushButton:checked {
                background-color: #0078D4;
                color: white;
                border-color: #0078D4;
            }
            QPushButton:hover {
                background-color: #F1F5F9;
            }
            QPushButton:checked:hover {
                background-color: #106EBE;
            }
        """)
        self.tab_widget.setCornerWidget(self.edit_btn, Qt.Corner.TopRightCorner)
        
        self.sessions_scroll = QScrollArea()
        self.sessions_scroll.setWidgetResizable(True)
        self.sessions_widget = QWidget()
        self.sessions_widget.setObjectName("sessions_widget")
        self.sessions_layout = QVBoxLayout(self.sessions_widget)
        self.sessions_layout.setContentsMargins(4, 4, 4, 4)
        self.sessions_layout.setSpacing(4)
        
        self.recoveries_scroll = QScrollArea()
        self.recoveries_scroll.setWidgetResizable(True)
        self.recoveries_widget = QWidget()
        self.recoveries_widget.setObjectName("recoveries_widget")
        self.recoveries_layout = QVBoxLayout(self.recoveries_widget)
        self.recoveries_layout.setContentsMargins(4, 4, 4, 4)
        self.recoveries_layout.setSpacing(4)

        self.trash_scroll = QScrollArea()
        self.trash_scroll.setWidgetResizable(True)
        self.trash_widget = QWidget()
        self.trash_widget.setObjectName("trash_widget")
        self.trash_layout = QVBoxLayout(self.trash_widget)
        self.trash_layout.setContentsMargins(4, 4, 4, 4)
        self.trash_layout.setSpacing(4)
        
        self.history_folder = os.path.join(get_app_data_dir(), "sessions")
        self.autosave_folder = os.path.join(get_app_data_dir(), "autosave")
        self.trash_folder = os.path.join(get_app_data_dir(), "trash")
        os.makedirs(self.history_folder, exist_ok=True)
        os.makedirs(self.autosave_folder, exist_ok=True)
        os.makedirs(self.trash_folder, exist_ok=True)
        
        self._refresh_all_lists()

        self.edit_btn.clicked.connect(self._refresh_all_lists)
        
        self.sessions_scroll.setWidget(self.sessions_widget)
        self.recoveries_scroll.setWidget(self.recoveries_widget)
        self.trash_scroll.setWidget(self.trash_widget)
        
        self.tab_widget.addTab(self.sessions_scroll, "Sessions")
        self.tab_widget.addTab(self.recoveries_scroll, "Recoveries")
        self.tab_widget.addTab(self.trash_scroll, "Trash")
        
        layout.addWidget(self.tab_widget)
        
        footer = QHBoxLayout()
        export_btn = QPushButton("📊 CSV", self)
        export_btn.setToolTip("Export All manually saved sessions to CSV")
        export_btn.setObjectName("NormalButton")
        export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        export_btn.clicked.connect(lambda: self.export_csv_history_requested.emit())
        footer.addWidget(export_btn)
        
        html_invoice_btn = QPushButton("📄 Generate HTML Invoice", self)
        html_invoice_btn.setObjectName("AccentButton")
        html_invoice_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        html_invoice_btn.clicked.connect(self._generate_selected_html_invoice)
        footer.addWidget(html_invoice_btn)
        
        footer.addStretch()
        
        open_folder_btn = QPushButton("Folder", self)
        open_folder_btn.setToolTip("Open manual saved sessions folder")
        open_folder_btn.setObjectName("NormalButton")
        open_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_folder_btn.clicked.connect(lambda: open_file(self.autosave_folder if self.tab_widget.currentIndex() == 1 else self.history_folder))
        footer.addWidget(open_folder_btn)
        
        close_btn = QPushButton("Close", self)
        close_btn.setObjectName("NormalButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.reject)
        footer.addWidget(close_btn)
        
        layout.addLayout(footer)

    def _get_relative_time(self, timestamp):
        diff = time.time() - timestamp
        if diff < 60: 
            return "Just now"
        if diff < 3600: 
            return f"{int(diff/60)}m ago"
        if diff < 86400: 
            return f"{int(diff/3600)}h ago"
        return datetime.fromtimestamp(timestamp).strftime("%b %d, %Y")

    def _render_list(self, layout_container, folder, is_recoveries):
        while layout_container.count() > 0:
            item = layout_container.takeAt(0)
            if item and item.widget():
                item.widget().setParent(None)
                
        files = glob.glob(os.path.join(folder, "*.json"))
        files.sort(key=os.path.getmtime, reverse=True)
        if not files:
            if folder == self.trash_folder:
                label_txt = "No trashed sessions found."
            elif is_recoveries:
                label_txt = "No auto-saves/recoveries found."
            else:
                label_txt = "No manual sessions found."
            lbl = QLabel(label_txt)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 13px; color: #ABABAB; margin: 40px;")
            layout_container.insertWidget(0, lbl)
            layout_container.addStretch()
            return

        for i, filepath in enumerate(files):
            filename = os.path.basename(filepath)
            mtime = os.path.getmtime(filepath)
            rel_time = self._get_relative_time(mtime)
            
            row_frame = QFrame()
            row_frame.setStyleSheet("QFrame { background-color: #FFFFFF; border-bottom: 1px solid #F3F3F3; } QFrame:hover { background-color: #E9E9E9; }")
            row_layout = QHBoxLayout(row_frame)
            row_layout.setContentsMargins(8, 8, 8, 8)
            
            is_trash = (folder == self.trash_folder)
            if not is_recoveries and not is_trash:
                cb_select = QCheckBox(row_frame)
                cb_select.setFixedWidth(20)
                
                def make_cb_connector(path):
                    return lambda state: (
                        self.selected_sessions.add(path) if state == 2 else self.selected_sessions.discard(path)
                    )
                cb_select.stateChanged.connect(make_cb_connector(filepath))
                row_layout.addWidget(cb_select)
            
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                session_name = data.get("session_name", "").strip()
                date_str = data.get("date", "")
            except Exception:
                session_name = ""
                date_str = filename.replace("session_", "").replace("auto_", "").replace("recovery_", "").replace(".json", "").replace("_", "  ")
            
            text_layout = QVBoxLayout()
            text_layout.setSpacing(2)
            
            name_lbl = QLabel(session_name or "Unnamed", row_frame)
            name_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 13px; font-weight: bold; color: #1A1A1A;")
            text_layout.addWidget(name_lbl)
            
            date_lbl = QLabel(date_str, row_frame)
            date_lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 11px; color: #616161;")
            text_layout.addWidget(date_lbl)
            
            tag_bg = "#E1F5FE" if i == 0 else "#F5F5F5"
            tag_fg = "#0288D1" if i == 0 else TEXT_SECONDARY
            tag_txt = "Latest" if i == 0 else rel_time
            tag_lbl = QLabel(tag_txt, row_frame)
            tag_lbl.setStyleSheet(f"background-color: {tag_bg}; color: {tag_fg}; font-size: 9px; font-weight: bold; border-radius: 3px; padding: 2px 6px; font-family: 'Segoe UI';")
            tag_lbl.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed))
            text_layout.addWidget(tag_lbl)
            
            row_layout.addLayout(text_layout)
            row_layout.addStretch()
            
            btn_layout = QHBoxLayout()
            btn_layout.setSpacing(4)
            
            def _open_report_local(path):
                try:
                    logger.info(f"[Action] Viewing local report for session: {os.path.basename(path)}")
                    rep = load_session_json(path)
                    self.view_report_requested.emit(rep)
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Could not load session:\n{e}")
                    
            def _resume_from_file(path):
                logger.info(f"[Action] Resuming session from: {os.path.basename(path)}")
                if self.tracker.running:
                    reply = QMessageBox.question(self, "Active Session", "A session is currently running.\nStop it and resume this one?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                    if reply != QMessageBox.StandardButton.Yes:
                        return
                self.resume_requested.emit(path)
                self.accept()

            def _rename_session_file(path, current_name):
                new_name, ok = QInputDialog.getText(self, "Rename Session", "Enter new session name:", QLineEdit.EchoMode.Normal, current_name)
                if ok and new_name.strip():
                    confirm = QMessageBox.question(
                        self,
                        "Confirm Rename",
                        f"Are you sure you want to rename this session to '{new_name.strip()}'?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No
                    )
                    if confirm == QMessageBox.StandardButton.Yes:
                        logger.info(f"[Action] Renaming session file {os.path.basename(path)} from '{current_name}' to '{new_name.strip()}'")
                        try:
                            with open(path, "r", encoding="utf-8") as f:
                                data = json.load(f)
                            data["session_name"] = new_name.strip()
                            with open(path, "w", encoding="utf-8") as f:
                                json.dump(data, f, indent=4)
                            self._refresh_all_lists()
                        except Exception as e:
                            QMessageBox.critical(self, "Error", f"Could not rename session:\n{e}")

            def _delete_session_file(path):
                is_trash = (folder == self.trash_folder)
                if is_trash:
                    import sys
                    bin_name = "Trash" if sys.platform == "darwin" else "Recycle Bin" if sys.platform == "win32" else "system Trash"
                    reply = QMessageBox.question(
                        self,
                        "Delete Permanently",
                        f"Are you sure you want to permanently move this session to the {bin_name}?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        logger.info(f"[Action] Permanently deleting session: {os.path.basename(path)}")
                        try:
                            self.selected_sessions.discard(path)
                            if not self._send_to_recycle_bin(path):
                                if os.path.exists(path):
                                    os.remove(path)
                            self._refresh_all_lists()
                        except Exception as e:
                            QMessageBox.critical(self, "Error", f"Could not delete session:\n{e}")
                else:
                    reply = QMessageBox.question(
                        self,
                        "Move to Trash",
                        "Are you sure you want to move this session to the Trash?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        logger.info(f"[Action] Trashing session: {os.path.basename(path)}")
                        try:
                            filename = os.path.basename(path)
                            dest_path = os.path.join(self.trash_folder, filename)
                            if os.path.exists(dest_path):
                                base, ext = os.path.splitext(filename)
                                dest_path = os.path.join(self.trash_folder, f"{base}_{int(time.time())}{ext}")
                            import shutil
                            shutil.move(path, dest_path)
                            self.selected_sessions.discard(path)
                            self._refresh_all_lists()
                        except Exception as e:
                            QMessageBox.critical(self, "Error", f"Could not move session to Trash:\n{e}")

            def _restore_session_file(path):
                logger.info(f"[Action] Restoring session from trash: {os.path.basename(path)}")
                try:
                    filename = os.path.basename(path)
                    if "auto_" in filename or "recovery_" in filename:
                        dest_folder = self.autosave_folder
                    else:
                        dest_folder = self.history_folder
                    dest_path = os.path.join(dest_folder, filename)
                    if os.path.exists(dest_path):
                        base, ext = os.path.splitext(filename)
                        dest_path = os.path.join(dest_folder, f"{base}_restored_{int(time.time())}{ext}")
                    import shutil
                    shutil.move(path, dest_path)
                    self._refresh_all_lists()
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Could not restore session:\n{e}")

            is_edit_active = self.edit_btn.isChecked()

            if is_trash:
                rest_icon = get_svg_icon(RESTORE_SVG, QSize(16, 16), "#0F7B0F")
                del_icon = get_svg_icon(TRASH_SVG, QSize(18, 18), "#FF0000")

                restore_btn = QPushButton(row_frame)
                restore_btn.setIcon(rest_icon)
                restore_btn.setIconSize(QSize(16, 16))
                restore_btn.setToolTip("Restore Session")
                restore_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                restore_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #F0FDF4;
                        border: 1px solid #DCFCE7;
                        border-radius: 4px;
                        padding: 4px;
                        min-width: 28px;
                        min-height: 28px;
                    }
                    QPushButton:hover {
                        background-color: #DCFCE7;
                        border-color: #86EFAC;
                    }
                """)
                restore_btn.clicked.connect(lambda checked, p=filepath: _restore_session_file(p))
                btn_layout.addWidget(restore_btn)

                delete_btn = QPushButton(row_frame)
                delete_btn.setIcon(del_icon)
                delete_btn.setIconSize(QSize(18, 18))
                import sys
                bin_name = "Trash" if sys.platform == "darwin" else "Recycle Bin" if sys.platform == "win32" else "system Trash"
                delete_btn.setToolTip(f"Move to {bin_name}")
                delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                delete_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #FFF5F5;
                        border: 1px solid #FEE2E2;
                        border-radius: 4px;
                        padding: 4px;
                        min-width: 28px;
                        min-height: 28px;
                    }
                    QPushButton:hover {
                        background-color: #FEE2E2;
                        border-color: #FCA5A5;
                    }
                """)
                delete_btn.clicked.connect(lambda checked, p=filepath: _delete_session_file(p))
                btn_layout.addWidget(delete_btn)

                restore_btn.setVisible(is_edit_active)
                delete_btn.setVisible(is_edit_active)
            else:
                ren_icon = get_svg_icon(RENAME_SVG, QSize(16, 16), "#0078D4")
                del_icon = get_svg_icon(TRASH_SVG, QSize(18, 18), "#FF0000")

                res_btn = QPushButton("▶ Resume", row_frame)
                res_btn.setObjectName("AccentButton")
                res_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                res_btn.clicked.connect(lambda checked, p=filepath: _resume_from_file(p))
                btn_layout.addWidget(res_btn)
                
                view_btn = QPushButton("View", row_frame)
                view_btn.setObjectName("NormalButton")
                view_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                view_btn.clicked.connect(lambda checked, p=filepath: _open_report_local(p))
                btn_layout.addWidget(view_btn)

                rename_btn = QPushButton(row_frame)
                rename_btn.setIcon(ren_icon)
                rename_btn.setIconSize(QSize(16, 16))
                rename_btn.setToolTip("Rename Session")
                rename_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                rename_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #FFFFFF;
                        border: 1px solid #CBD5E1;
                        border-radius: 4px;
                        padding: 4px;
                        min-width: 28px;
                        min-height: 28px;
                    }
                    QPushButton:hover {
                        background-color: #F1F5F9;
                        border-color: #94A3B8;
                    }
                """)
                rename_btn.clicked.connect(lambda checked, p=filepath, n=session_name: _rename_session_file(p, n))
                btn_layout.addWidget(rename_btn)

                delete_btn = QPushButton(row_frame)
                delete_btn.setIcon(del_icon)
                delete_btn.setIconSize(QSize(18, 18))
                delete_btn.setToolTip("Move to Trash")
                delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                delete_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #FFF5F5;
                        border: 1px solid #FEE2E2;
                        border-radius: 4px;
                        padding: 4px;
                        min-width: 28px;
                        min-height: 28px;
                    }
                    QPushButton:hover {
                        background-color: #FEE2E2;
                        border-color: #FCA5A5;
                    }
                """)
                delete_btn.clicked.connect(lambda checked, p=filepath: _delete_session_file(p))
                btn_layout.addWidget(delete_btn)

                res_btn.setVisible(not is_edit_active)
                view_btn.setVisible(not is_edit_active)
                rename_btn.setVisible(is_edit_active)
                delete_btn.setVisible(is_edit_active)
            
            row_layout.addLayout(btn_layout)
            layout_container.addWidget(row_frame)
            
        layout_container.addStretch()

    def _refresh_all_lists(self):
        self._render_list(self.sessions_layout, self.history_folder, False)
        self._render_list(self.recoveries_layout, self.autosave_folder, True)
        self._render_list(self.trash_layout, self.trash_folder, False)

    def _send_to_recycle_bin(self, path):
        return send_to_trash(path)

    def _generate_selected_html_invoice(self):
        if not self.selected_sessions:
            QMessageBox.warning(self, "No Sessions Selected", "Please select at least one session using the checkbox on the left of the item.")
            return
        
        logger.info(f"[Action] Generating HTML invoice for {len(self.selected_sessions)} selected sessions")
        
        # Show save path dialog
        default_html_name = f"FocusLog_Invoice_{datetime.now().strftime('%Y-%m-%d')}.html"
        html_filepath, _ = QFileDialog.getSaveFileName(self, "Save Invoice HTML", default_html_name, "HTML Files (*.html)")
        if not html_filepath:
            return
            
        try:
            # Mask sensitive data custom options dialog
            privacy_dialog = InvoicePrivacyOptionsDialog(
                self,
                default_biz_email=self.settings.get("mask_business_emails", False),
                default_biz_phone=self.settings.get("mask_business_phone", False),
                default_client_email=self.settings.get("mask_client_emails", False)
            )
            if privacy_dialog.exec() != QDialog.DialogCode.Accepted:
                return
            
            mask_biz_email = privacy_dialog.cb_biz_email.isChecked()
            mask_biz_phone = privacy_dialog.cb_biz_phone.isChecked()
            mask_client_email = privacy_dialog.cb_client_email.isChecked()

            billing_data = merge_sessions_for_invoice(
                list(self.selected_sessions), self.tracker,
                self.settings.get("hourly_rate", 0.0), self.settings.get("currency_symbol", "$")
            )
            
            settings_data = {
                "business_name": self.settings.get("business_name", ""),
                "business_emails": self.settings.get("business_emails", []),
                "business_email": ", ".join(self.settings.get("business_emails", [])),
                "business_phone": self.settings.get("business_phone", ""),
                "business_address": self.settings.get("business_address", ""),
                "business_payment": self.settings.get("business_payment", ""),
                "client_name": self.settings.get("client_name", ""),
                "client_emails": self.settings.get("client_emails", []),
                "client_address": self.settings.get("client_address", ""),
                "business_logo_path": self.settings.get("business_logo_path", ""),
                "hourly_rate": self.settings.get("hourly_rate", 0.0),
                "currency_symbol": self.settings.get("currency_symbol", "$"),
                "qr_code_paths": self.settings.get("qr_code_paths", []),
                "qr_code_links": self.settings.get("qr_code_links", {}),
                
                "mask_business_emails": mask_biz_email,
                "mask_business_phone": mask_biz_phone,
                "mask_client_emails": mask_client_email,
            }
            
            html_content = generate_invoice_html(billing_data, settings_data)
            with open(html_filepath, "w", encoding="utf-8") as f:
                f.write(html_content)
            
            reply = QMessageBox.question(
                self, 
                "Invoice Created", 
                f"Invoice HTML generated successfully at:\n{html_filepath}\n\nWould you like to open it in your browser now to print/save as PDF?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                open_file(html_filepath)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to generate invoice HTML:\n{str(e)}")
