import os
import time
import json
import glob
import logging
from datetime import datetime
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTabWidget,
    QScrollArea, QWidget, QFrame, QCheckBox, QLabel, QSizePolicy,
    QMessageBox, QInputDialog, QLineEdit, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize

from config import get_app_data_dir, open_file, send_to_trash

logger = logging.getLogger(__name__)
from report import (
    load_session_json, merge_sessions_for_invoice, generate_invoice_html
)
from theme import get_svg_icon
from assets import RENAME_SVG, TRASH_SVG, RESTORE_SVG
from widgets.custom_widgets import InvoicePrivacyOptionsDialog
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

class InvoiceHTTPHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(self.server.html_content.encode('utf-8'))
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        if self.path == '/save':
            try:
                from database.schema import get_invoice_by_no
                invoice_record = get_invoice_by_no(self.server.invoice_no)
                exists_and_active = (invoice_record is not None) and (invoice_record.get("status") in ["unpaid", "paid"])
                if exists_and_active:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "already_saved"}).encode('utf-8'))
                else:
                    self.server.save_callback()
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "success"}).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
        else:
            self.send_error(404, "Not Found")

class InvoiceHTTPServer(HTTPServer):
    def __init__(self, server_address, RequestHandlerClass, html_content, save_callback, invoice_no):
        super().__init__(server_address, RequestHandlerClass)
        self.html_content = html_content
        self.save_callback = save_callback
        self.invoice_no = invoice_no

class InvoiceServerThread(threading.Thread):
    def __init__(self, html_content, save_callback, invoice_no):
        super().__init__()
        self.html_content = html_content
        self.save_callback = save_callback
        self.invoice_no = invoice_no
        self.daemon = True
        self.server = InvoiceHTTPServer(('127.0.0.1', 0), InvoiceHTTPHandler, html_content, save_callback, invoice_no)
        self.port = self.server.server_address[1]

    def run(self):
        self.server.serve_forever()

    def stop(self):
        try:
            self.server.shutdown()
            self.server.server_close()
        except Exception:
            pass

class SessionManagerDialog(QDialog):
    resume_requested = pyqtSignal(str)             # filepath to resume
    view_report_requested = pyqtSignal(dict)       # report dict
    invoice_saved_signal = pyqtSignal()            # invoice saved from browser

    def __init__(self, settings_data, tracker, parent=None):
        super().__init__(parent)
        self.settings = settings_data
        self.tracker = tracker
        self.setWindowTitle("Session Manager")
        self._center_window(520, 540)

        # Apply stylesheet and palette on start
        is_dark = self.settings.get("dark_mode", False)
        from theme import get_qss_style, get_dark_palette, get_light_palette, ensure_checkmark_icon
        qss = get_qss_style(is_dark).replace("CHECKMARK_PATH", ensure_checkmark_icon(is_dark))
        self.setStyleSheet(qss)
        self.setPalette(get_dark_palette() if is_dark else get_light_palette())

        self.selected_sessions = set()
        self._build_ui()
        self.preview_server = None
        self.invoice_saved_signal.connect(self._on_invoice_saved_from_browser)

    def _center_window(self, width, height):
        self.resize(width, height)
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - width) // 2
        y = (screen.height() - height) // 2
        self.move(x, y)

    def _on_invoice_saved_from_browser(self):
        self.selected_sessions.clear()
        self._refresh_all_lists()
        self.raise_()
        self.activateWindow()

    def _stop_preview_server(self):
        if hasattr(self, 'preview_server') and self.preview_server:
            try:
                self.preview_server.stop()
            except Exception:
                pass
            self.preview_server = None

    def closeEvent(self, event):
        self._stop_preview_server()
        super().closeEvent(event)

    def reject(self):
        self._stop_preview_server()
        super().reject()

    def accept(self):
        self._stop_preview_server()
        super().accept()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        self.tab_widget = QTabWidget(self)
        self.tab_widget.setObjectName("SessionTabs")

        is_dark = self.settings.get("dark_mode", False)
        bg_widget = "#1e1e1e" if is_dark else "#FFFFFF"
        border_color = "#333333" if is_dark else "#CBD5E1"
        text_sec = "#aaa" if is_dark else "#475569"
        bg_hover = "#262626" if is_dark else "#F1F5F9"
        accent = "#ef4444" if is_dark else "#0078D4"
        accent_hover = "#dc2626" if is_dark else "#106EBE"

        self.edit_btn = QPushButton("Edit", self)
        self.edit_btn.setCheckable(True)
        self.edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.edit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg_widget};
                border: 1px solid {border_color};
                border-radius: 4px;
                padding: 4px 12px;
                font-family: 'Segoe UI';
                font-size: 12px;
                font-weight: bold;
                color: {text_sec};
            }}
            QPushButton:checked {{
                background-color: {accent};
                color: white;
                border-color: {accent};
            }}
            QPushButton:hover {{
                background-color: {bg_hover};
            }}
            QPushButton:checked:hover {{
                background-color: {accent_hover};
            }}
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

        self.invoices_scroll = QScrollArea()
        self.invoices_scroll.setWidgetResizable(True)
        self.invoices_widget = QWidget()
        self.invoices_widget.setObjectName("invoices_widget")
        self.invoices_layout = QVBoxLayout(self.invoices_widget)
        self.invoices_layout.setContentsMargins(4, 4, 4, 4)
        self.invoices_layout.setSpacing(4)

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
        self.invoices_scroll.setWidget(self.invoices_widget)

        self.tab_widget.addTab(self.sessions_scroll, "Sessions")
        self.tab_widget.addTab(self.recoveries_scroll, "Recoveries")
        self.tab_widget.addTab(self.trash_scroll, "Trash")
        self.tab_widget.addTab(self.invoices_scroll, "Invoices")

        layout.addWidget(self.tab_widget)

        footer = QHBoxLayout()
        html_invoice_btn = QPushButton("📄 View Invoice in Browser", self)
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
            if item:
                w = item.widget()
                if w:
                    w.deleteLater()

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

            is_dark = self.settings.get("dark_mode", False)
            bg_widget = "#1e1e1e" if is_dark else "#FFFFFF"
            border_color = "#333333" if is_dark else "#F3F3F3"
            bg_hover = "#262626" if is_dark else "#E9E9E9"
            text_primary = "#e0e0e0" if is_dark else "#1A1A1A"
            text_sec = "#aaa" if is_dark else "#616161"

            row_frame = QFrame()
            row_frame.setStyleSheet(f"QFrame {{ background-color: {bg_widget}; border-bottom: 1px solid {border_color}; }} QFrame:hover {{ background-color: {bg_hover}; }}")
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
            name_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 13px; font-weight: bold; color: {text_primary};")
            text_layout.addWidget(name_lbl)

            date_lbl = QLabel(date_str, row_frame)
            date_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 11px; color: {text_sec};")
            text_layout.addWidget(date_lbl)

            is_dark = self.settings.get("dark_mode", False)
            if is_dark:
                tag_bg = "#262626" if i == 0 else "#262626"
                tag_fg = "#ffffff" if i == 0 else "#aaa"
            else:
                tag_bg = "#E1F5FE" if i == 0 else "#F1F5F9"
                tag_fg = "#0078D4" if i == 0 else "#475569"

            tag_txt = "Latest" if i == 0 else rel_time
            tag_lbl = QLabel(tag_txt, row_frame)
            tag_lbl.setStyleSheet(f"background-color: {tag_bg}; color: {tag_fg}; font-size: 9px; font-weight: bold; border-radius: 3px; padding: 2px 6px; font-family: 'Segoe UI'; border: none;")
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

            is_dark = self.settings.get("dark_mode", False)
            if is_dark:
                green_bg = "#262626"
                green_border = "#444444"
                green_hover = "#333333"

                red_bg = "#262626"
                red_border = "#444444"
                red_hover = "#333333"

                normal_bg = "#1e1e1e"
                normal_border = "#333333"
                normal_hover = "#262626"
                normal_border_hover = "#e0e0e0"
            else:
                green_bg = "#F0FDF4"
                green_border = "#DCFCE7"
                green_hover = "#DCFCE7"

                red_bg = "#FFF5F5"
                red_border = "#FEE2E2"
                red_hover = "#FEE2E2"

                normal_bg = "#FFFFFF"
                normal_border = "#CBD5E1"
                normal_hover = "#F1F5F9"
                normal_border_hover = "#94A3B8"

            if is_trash:
                rest_icon = get_svg_icon(RESTORE_SVG, QSize(16, 16), "#0F7B0F" if not is_dark else "#d1d5db")
                del_icon = get_svg_icon(TRASH_SVG, QSize(18, 18), "#FF0000" if not is_dark else "#d1d5db")

                restore_btn = QPushButton(row_frame)
                restore_btn.setIcon(rest_icon)
                restore_btn.setIconSize(QSize(16, 16))
                restore_btn.setToolTip("Restore Session")
                restore_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                restore_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {green_bg};
                        border: 1px solid {green_border};
                        border-radius: 4px;
                        padding: 4px;
                        min-width: 28px;
                        min-height: 28px;
                    }}
                    QPushButton:hover {{
                        background-color: {green_hover};
                        border-color: #86EFAC;
                    }}
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
                delete_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {red_bg};
                        border: 1px solid {red_border};
                        border-radius: 4px;
                        padding: 4px;
                        min-width: 28px;
                        min-height: 28px;
                    }}
                    QPushButton:hover {{
                        background-color: {red_hover};
                        border-color: #FCA5A5;
                    }}
                """)
                delete_btn.clicked.connect(lambda checked, p=filepath: _delete_session_file(p))
                btn_layout.addWidget(delete_btn)

                restore_btn.setVisible(is_edit_active)
                delete_btn.setVisible(is_edit_active)
            else:
                ren_icon = get_svg_icon(RENAME_SVG, QSize(16, 16), "#0078D4" if not is_dark else "#d1d5db")
                del_icon = get_svg_icon(TRASH_SVG, QSize(18, 18), "#FF0000" if not is_dark else "#d1d5db")

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
                rename_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {normal_bg};
                        border: 1px solid {normal_border};
                        border-radius: 4px;
                        padding: 4px;
                        min-width: 28px;
                        min-height: 28px;
                    }}
                    QPushButton:hover {{
                        background-color: {normal_hover};
                        border-color: {normal_border_hover};
                    }}
                """)
                rename_btn.clicked.connect(lambda checked, p=filepath, n=session_name: _rename_session_file(p, n))
                btn_layout.addWidget(rename_btn)

                delete_btn = QPushButton(row_frame)
                delete_btn.setIcon(del_icon)
                delete_btn.setIconSize(QSize(18, 18))
                delete_btn.setToolTip("Move to Trash")
                delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                delete_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {red_bg};
                        border: 1px solid {red_border};
                        border-radius: 4px;
                        padding: 4px;
                        min-width: 28px;
                        min-height: 28px;
                    }}
                    QPushButton:hover {{
                        background-color: {red_hover};
                        border-color: #FCA5A5;
                    }}
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
        from core.reporting.aggregator import rebuild_all_summaries
        try:
            rebuild_all_summaries(force=True)
        except Exception as e:
            print(f"[TrueHour] Failed to rebuild summaries on list refresh: {e}")
        self._render_list(self.sessions_layout, self.history_folder, False)
        self._render_list(self.recoveries_layout, self.autosave_folder, True)
        self._render_list(self.trash_layout, self.trash_folder, False)
        self._refresh_invoices_list()

    def _refresh_invoices_list(self):
        while self.invoices_layout.count() > 0:
            item = self.invoices_layout.takeAt(0)
            if item:
                w = item.widget()
                if w:
                    w.deleteLater()

        from database.schema import get_invoices_list
        try:
            invoices = get_invoices_list()

        except Exception as e:
            logger.error(f"Failed to fetch invoices: {e}")
            invoices = []

        if not invoices:
            lbl = QLabel("No recorded invoices found.")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("font-family: 'Segoe UI'; font-size: 13px; color: #ABABAB; margin: 40px;")
            self.invoices_layout.insertWidget(0, lbl)
            self.invoices_layout.addStretch()
            return

        is_dark = self.settings.get("dark_mode", False)
        bg_widget = "#1e1e1e" if is_dark else "#FFFFFF"
        border_color = "#333333" if is_dark else "#F3F3F3"
        bg_hover = "#262626" if is_dark else "#E9E9E9"
        text_primary = "#e0e0e0" if is_dark else "#1A1A1A"
        text_sec = "#aaa" if is_dark else "#616161"

        from theme import get_svg_icon
        from assets import TRASH_SVG

        for inv in invoices:
            row_frame = QFrame()
            row_frame.setStyleSheet(f"QFrame {{ background-color: {bg_widget}; border-bottom: 1px solid {border_color}; }} QFrame:hover {{ background-color: {bg_hover}; }}")
            row_layout = QHBoxLayout(row_frame)
            row_layout.setContentsMargins(8, 8, 8, 8)

            text_layout = QVBoxLayout()
            text_layout.setSpacing(2)

            inv_no = inv.get("invoice_no", "")
            client = inv.get("client_name", "Valued Client")
            amount = inv.get("amount", 0.0)
            curr = inv.get("currency", "$")
            status = inv.get("status", "unpaid")
            created_at_raw = inv.get("created_at", "")

            try:
                date_obj = datetime.fromisoformat(created_at_raw)
                date_str = date_obj.strftime("%b %d, %Y  %I:%M %p")
            except Exception:
                date_str = created_at_raw

            title_lbl = QLabel(f"{inv_no} — {client}", row_frame)
            title_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 13px; font-weight: bold; color: {text_primary};")
            title_lbl.setWordWrap(True)
            text_layout.addWidget(title_lbl)

            detail_lbl = QLabel(f"Created: {date_str} | Amount: {curr}{amount:,.2f}", row_frame)
            detail_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 11px; color: {text_sec};")
            detail_lbl.setWordWrap(True)
            text_layout.addWidget(detail_lbl)

            row_layout.addLayout(text_layout, 1)

            status_btn = QPushButton(status.upper(), row_frame)
            status_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if status == "draft":
                status_btn.setToolTip("Draft: Click to confirm and save as an Unpaid invoice")
            else:
                status_btn.setToolTip("Click to toggle Paid/Unpaid status")

            if is_dark:
                if status == "paid":
                    status_color_bg = "#333333"
                    status_color_fg = "#ffffff"
                elif status == "draft":
                    status_color_bg = "#2e1065"
                    status_color_fg = "#c084fc"
                else:
                    status_color_bg = "#222222"
                    status_color_fg = "#888888"
            else:
                if status == "paid":
                    status_color_bg = "#DCFCE7"
                    status_color_fg = "#16A34A"
                elif status == "draft":
                    status_color_bg = "#F3E8FF"
                    status_color_fg = "#7E22CE"
                else:
                    status_color_bg = "#FEF3C7"
                    status_color_fg = "#D97706"

            status_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {status_color_bg};
                    color: {status_color_fg};
                    font-size: 10px;
                    font-weight: bold;
                    border-radius: 4px;
                    padding: 3px 8px;
                    border: 1px solid {status_color_fg}33;
                }}
                QPushButton:hover {{
                    border-color: {status_color_fg};
                }}
            """)

            def make_toggle_status_connector(inv_num, current_status):
                return lambda: self._toggle_invoice_status(inv_num, current_status)
            status_btn.clicked.connect(make_toggle_status_connector(inv_no, status))
            row_layout.addWidget(status_btn)

            view_btn = QPushButton("View", row_frame)
            view_btn.setObjectName("NormalButton")
            view_btn.setCursor(Qt.CursorShape.PointingHandCursor)

            def make_view_connector(inv_data):
                return lambda: self._view_recorded_invoice(inv_data)
            view_btn.clicked.connect(make_view_connector(inv))
            row_layout.addWidget(view_btn)

            from assets import RENAME_SVG
            ren_icon = get_svg_icon(RENAME_SVG, QSize(16, 16), "#0078D4" if not is_dark else "#d1d5db")
            rename_invoice_btn = QPushButton(row_frame)
            rename_invoice_btn.setIcon(ren_icon)
            rename_invoice_btn.setIconSize(QSize(16, 16))
            rename_invoice_btn.setToolTip("Rename Invoice")
            rename_invoice_btn.setCursor(Qt.CursorShape.PointingHandCursor)

            normal_bg = "#1e1e1e" if is_dark else "#FFFFFF"
            normal_border = "#333333" if is_dark else "#CBD5E1"
            normal_hover = "#262626" if is_dark else "#F1F5F9"
            normal_border_hover = "#e0e0e0" if is_dark else "#94A3B8"
            rename_invoice_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {normal_bg};
                    border: 1px solid {normal_border};
                    border-radius: 4px;
                    padding: 4px;
                    min-width: 28px;
                    min-height: 28px;
                }}
                QPushButton:hover {{
                    background-color: {normal_hover};
                    border-color: {normal_border_hover};
                }}
            """)
            def make_rename_invoice_connector(inv_num):
                return lambda: self._rename_recorded_invoice(inv_num)
            rename_invoice_btn.clicked.connect(make_rename_invoice_connector(inv_no))
            row_layout.addWidget(rename_invoice_btn)

            del_icon = get_svg_icon(TRASH_SVG, QSize(18, 18), "#FF0000" if not is_dark else "#c27a6e")
            delete_btn = QPushButton(row_frame)
            delete_btn.setIcon(del_icon)
            delete_btn.setIconSize(QSize(18, 18))
            delete_btn.setToolTip("Delete Invoice Record")
            delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)

            red_bg = "#8a4a3d" if is_dark else "#FFF5F5"
            red_border = "#a1594b" if is_dark else "#FEE2E2"
            red_hover = "#a1594b" if is_dark else "#FEE2E2"
            delete_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {red_bg};
                    border: 1px solid {red_border};
                    border-radius: 4px;
                    padding: 4px;
                    min-width: 28px;
                    min-height: 28px;
                }}
                QPushButton:hover {{
                    background-color: {red_hover};
                    border-color: #FCA5A5;
                }}
            """)
            def make_delete_connector(inv_num):
                return lambda: self._delete_recorded_invoice(inv_num)
            delete_btn.clicked.connect(make_delete_connector(inv_no))
            row_layout.addWidget(delete_btn)

            self.invoices_layout.addWidget(row_frame)

        self.invoices_layout.addStretch()

    def _toggle_invoice_status(self, invoice_no, current_status):
        if current_status == "draft":
            new_status = "unpaid"
        else:
            new_status = "unpaid" if current_status == "paid" else "paid"
        logger.info(f"[Action] Toggling invoice {invoice_no} status from {current_status} to {new_status}")
        try:
            from database.schema import update_invoice_status
            update_invoice_status(invoice_no, new_status)
            self._refresh_invoices_list()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to update status:\n{e}")

    def _rename_recorded_invoice(self, invoice_no):
        new_name, ok = QInputDialog.getText(
            self,
            "Rename Invoice",
            "Enter new invoice name/number:",
            QLineEdit.EchoMode.Normal,
            invoice_no
        )
        if ok and new_name.strip():
            new_name = new_name.strip()
            if new_name == invoice_no:
                return

            from database.schema import get_all_invoices, rename_invoice
            try:
                existing_nos = {inv["invoice_no"] for inv in get_all_invoices()}
            except Exception:
                existing_nos = set()

            if new_name in existing_nos:
                QMessageBox.warning(self, "Conflict", f"An invoice/receipt named '{new_name}' already exists.")
                return

            logger.info(f"[Action] Renaming invoice from {invoice_no} to {new_name}")
            try:
                rename_invoice(invoice_no, new_name)
                self._refresh_invoices_list()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to rename invoice:\n{e}")

    def _delete_recorded_invoice(self, invoice_no):
        reply = QMessageBox.question(
            self,
            "Delete Invoice Record",
            f"Are you sure you want to delete the record for {invoice_no}?\nThis will not delete the session files.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            logger.info(f"[Action] Deleting invoice {invoice_no} record")
            try:
                from database.schema import delete_invoice
                delete_invoice(invoice_no)
                self._refresh_invoices_list()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete invoice record:\n{e}")

    def _view_recorded_invoice(self, inv_data):
        try:
            import json
            import tempfile
            from report import generate_invoice_html
            from database.schema import get_invoice_by_no

            invoice_no = inv_data.get("invoice_no")
            full_inv = get_invoice_by_no(invoice_no)
            if not full_inv:
                raise ValueError(f"Invoice {invoice_no} not found in database.")

            billing_data = json.loads(full_inv.get("billing_data", "{}"))
            settings_data = json.loads(full_inv.get("settings_data", "{}"))
            status = full_inv.get("status", "unpaid")

            if status == "draft":
                self._stop_preview_server()
                
                session_files = json.loads(full_inv.get("session_files", "[]"))
                
                def save_callback():
                    from database.schema import save_invoice
                    save_invoice(
                        invoice_no=invoice_no,
                        client_name=settings_data.get("client_name", "Valued Client"),
                        amount=billing_data.get("total_earned", 0.0),
                        currency=settings_data.get("currency_symbol", "$"),
                        status="unpaid",
                        session_files=session_files,
                        billing_data=billing_data,
                        settings_data=settings_data
                    )
                    self.invoice_saved_signal.emit()

                html_content = generate_invoice_html(billing_data, settings_data, status="unpaid", invoice_no=invoice_no)
                
                self.preview_server = InvoiceServerThread(html_content, save_callback, invoice_no)
                self.preview_server.start()
                port = self.preview_server.port
                
                try:
                    open_file(f"http://127.0.0.1:{port}/")
                except Exception as open_err:
                    logger.warning(f"Failed to auto-open invoice draft in browser: {open_err}")
                    QMessageBox.warning(
                        self,
                        "Failed to Open",
                        f"Invoice server started, but browser could not be opened automatically:\nhttp://127.0.0.1:{port}/",
                        QMessageBox.StandardButton.Ok
                    )
            else:
                html_content = generate_invoice_html(billing_data, settings_data, status=status, invoice_no=invoice_no)

                with tempfile.NamedTemporaryFile('w', delete=False, suffix='.html', encoding='utf-8') as f:
                    f.write(html_content)
                    temp_path = f.name

                try:
                    open_file(temp_path)
                except Exception as open_err:
                    logger.warning(f"Failed to auto-open invoice in browser: {open_err}")
                    QMessageBox.warning(
                        self,
                        "Failed to Open",
                        f"Invoice generated successfully, but could not be opened automatically:\n{temp_path}",
                        QMessageBox.StandardButton.Ok
                    )
        except Exception as e:
            logger.error(f"Failed to view recorded invoice: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to view invoice:\n{str(e)}")

    def _send_to_recycle_bin(self, path):
        return send_to_trash(path)

    def _generate_selected_html_invoice(self):
        if not self.selected_sessions:
            QMessageBox.warning(self, "No Sessions Selected", "Please select at least one session using the checkbox on the left of the item.")
            return

        logger.info(f"[Action] Generating HTML invoice for {len(self.selected_sessions)} selected sessions")

        try:
            # Mask sensitive data custom options dialog
            privacy_dialog = InvoicePrivacyOptionsDialog(
                self,
                default_biz_email=self.settings.get("mask_business_emails", False),
                default_biz_phone=self.settings.get("mask_business_phone", False),
                default_client_email=self.settings.get("mask_client_emails", False),
                is_dark=self.settings.get("dark_mode", False)
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
                "enable_bank_details": self.settings.get("enable_bank_details", True),
                "bank_holder": self.settings.get("bank_holder", ""),
                "bank_account": self.settings.get("bank_account", ""),
                "bank_routing": self.settings.get("bank_routing", ""),
                "bank_swift": self.settings.get("bank_swift", ""),
                "bank_name": self.settings.get("bank_name", ""),
                "bank_address": self.settings.get("bank_address", ""),
                "client_name": self.settings.get("client_name", ""),
                "client_emails": self.settings.get("client_emails", []),
                "client_address": self.settings.get("client_address", ""),
                "business_logo_path": self.settings.get("business_logo_path", ""),
                "enable_business_logo": self.settings.get("enable_business_logo", True),
                "hourly_rate": self.settings.get("hourly_rate", 0.0),
                "currency_symbol": self.settings.get("currency_symbol", "$"),
                "qr_code_paths": self.settings.get("qr_code_paths", []),
                "qr_code_links": self.settings.get("qr_code_links", {}),

                "mask_business_emails": mask_biz_email,
                "mask_business_phone": mask_biz_phone,
                "mask_client_emails": mask_client_email,
                "dark_mode": self.settings.get("dark_mode", False),
            }

            # Resolve name from session files (chronologically sorted)
            sessions_info = []
            for path in self.selected_sessions:
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    s_name = data.get("session_name", "").strip() or "Unnamed"
                    s_date = data.get("date", "")
                    s_start = data.get("start", "")
                    sessions_info.append((s_date, s_start, s_name))
                except Exception:
                    pass

            # Sort chronologically by date and start time
            sessions_info.sort(key=lambda x: (x[0], x[1]))

            if sessions_info:
                if len(sessions_info) == 1:
                    inv_no = sessions_info[0][2].replace(" ", "")
                else:
                    first_name = sessions_info[0][2].replace(" ", "")
                    last_name = sessions_info[-1][2].replace(" ", "")
                    inv_no = f"{first_name}_to_{last_name}"
            else:
                inv_no = f"INV-{datetime.now().strftime('%Y%m%d%H%M')}"

            # Resolve duplicate name conflicts in database
            from database.schema import get_all_invoices, save_invoice
            try:
                existing_nos = {inv["invoice_no"] for inv in get_all_invoices()}
            except Exception:
                existing_nos = set()

            base_inv_no = inv_no
            counter = 1
            while inv_no in existing_nos:
                inv_no = f"{base_inv_no} ({counter})"
                counter += 1

            self._stop_preview_server()

            html_content = generate_invoice_html(billing_data, settings_data, status="unpaid", invoice_no=inv_no)
            session_filenames = [os.path.basename(path) for path in self.selected_sessions]

            # Save immediately as a draft
            save_invoice(
                invoice_no=inv_no,
                client_name=settings_data.get("client_name", "Valued Client"),
                amount=billing_data.get("total_earned", 0.0),
                currency=settings_data.get("currency_symbol", "$"),
                status="draft",
                session_files=session_filenames,
                billing_data=billing_data,
                settings_data=settings_data
            )

            # Clear checkboxes and refresh lists immediately to show the draft
            self.selected_sessions.clear()
            self._refresh_all_lists()

            def save_callback():
                save_invoice(
                    invoice_no=inv_no,
                    client_name=settings_data.get("client_name", "Valued Client"),
                    amount=billing_data.get("total_earned", 0.0),
                    currency=settings_data.get("currency_symbol", "$"),
                    status="unpaid",
                    session_files=session_filenames,
                    billing_data=billing_data,
                    settings_data=settings_data
                )
                self.invoice_saved_signal.emit()

            self.preview_server = InvoiceServerThread(html_content, save_callback, inv_no)
            self.preview_server.start()
            port = self.preview_server.port

            try:
                open_file(f"http://127.0.0.1:{port}/")
            except Exception as open_err:
                logger.warning(f"Failed to auto-open invoice in browser: {open_err}")
                QMessageBox.warning(
                    self,
                    "Failed to Open",
                    f"Invoice server started, but browser could not be opened automatically:\nhttp://127.0.0.1:{port}/",
                    QMessageBox.StandardButton.Ok
                )
        except Exception as e:
            logger.error(f"Failed to generate invoice HTML: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to generate invoice HTML:\n{str(e)}")
