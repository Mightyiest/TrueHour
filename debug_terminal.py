"""
TrueHour — Debug Terminal Module
Manages thread-safe stdout/stderr, active file logging, and UDP loopback streaming to a standalone debug console.
"""
import sys
import os
import html
import socket
from collections import deque
import threading
from datetime import datetime
from PyQt6.QtCore import QObject, pyqtSignal, Qt, QRectF
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QLineEdit,
    QPushButton, QCheckBox, QLabel, QFileDialog, QMessageBox, QApplication
)

class LogSignalEmitter(QObject):
    log_written = pyqtSignal(str)

class LogBufferCollector:
    """Thread-safe collector that intercepts sys.stdout/stderr, writes to active log, and broadcasts over UDP."""
    def __init__(self, max_lines=1000):
        self.buffer = deque(maxlen=max_lines)
        self.emitter = LogSignalEmitter()
        self.lock = threading.Lock()
        
        self._stdout = sys.stdout
        self._stderr = sys.stderr
        self._is_redirected = False
        
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_target = ("127.0.0.1", 50099)
        
        # Initialize and clear the active log file
        try:
            from config import get_app_data_root
            import os
            log_file = os.path.join(get_app_data_root(), "TrueHour_active.log")
            if os.path.exists(log_file):
                os.remove(log_file)
            with open(log_file, "w", encoding="utf-8") as f:
                f.write(f"--- TrueHour Debug Session Started at {datetime.now()} ---\n")
        except Exception:
            pass

    def write_log(self, text):
        if not text:
            return
        with self.lock:
            self.buffer.append(text)
            self.emitter.log_written.emit(text)
            
            # Write to persistent active log file
            try:
                from config import get_app_data_root
                import os
                log_file = os.path.join(get_app_data_root(), "TrueHour_active.log")
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(text)
            except Exception:
                pass
                
            # Broadcast over local UDP loopback
            try:
                self.udp_socket.sendto(text.encode("utf-8"), self.udp_target)
            except Exception:
                pass

    def start_redirection(self):
        if not self._is_redirected:
            sys.stdout = StreamRedirector(self, is_stderr=False)
            sys.stderr = StreamRedirector(self, is_stderr=True)
            self._is_redirected = True

    def stop_redirection(self):
        if self._is_redirected:
            sys.stdout = self._stdout
            sys.stderr = self._stderr
            self._is_redirected = False

class StreamRedirector:
    """Helper stream object to replace sys.stdout and sys.stderr with safety checks for PyInstaller frozen mode."""
    def __init__(self, collector, is_stderr=False):
        self.collector = collector
        self.is_stderr = is_stderr

    def write(self, text):
        if text:
            self.collector.write_log(text)
            try:
                if self.is_stderr:
                    if self.collector._stderr is not None:
                        self.collector._stderr.write(text)
                else:
                    if self.collector._stdout is not None:
                        self.collector._stdout.write(text)
            except Exception:
                pass

    def flush(self):
        try:
            if self.is_stderr:
                if self.collector._stderr is not None:
                    self.collector._stderr.flush()
            else:
                if self.collector._stdout is not None:
                    self.collector._stdout.flush()
        except Exception:
            pass

class DebugTerminalWindow(QDialog):
    """Modern Windows-11 style dialog to display active logs with filtering, colorizing and auto-scroll."""
    def __init__(self, collector=None, parent=None):
        super().__init__(parent)
        self.collector = collector
        self.listener_active = False
        self.udp_sock = None
        
        self.setWindowTitle("TrueHour Debug Console")
        self.resize(620, 420)
        self.setMinimumSize(450, 300)
        
        self.setStyleSheet("""
            QDialog {
                background-color: #F8FAFC;
            }
            QLabel {
                font-family: 'Segoe UI';
                font-size: 12px;
                color: #475569;
            }
            QLineEdit {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 6px;
                padding: 6px 10px;
                font-family: 'Segoe UI';
                font-size: 12px;
                color: #0F172A;
            }
            QLineEdit:focus {
                border: 1px solid #0078D4;
            }
            QPlainTextEdit {
                background-color: #0F172A;
                color: #F8FAFC;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
                border: 1px solid #1E293B;
                border-radius: 8px;
                padding: 6px;
            }
            QCheckBox {
                font-family: 'Segoe UI';
                font-size: 12px;
                color: #475569;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border: 1.5px solid #94A3B8;
                border-radius: 3px;
                background-color: #FFFFFF;
            }
            QCheckBox::indicator:checked {
                border-color: #0078D4;
                background-color: #0078D4;
                image: url(CHECKMARK_PATH);
            }
            QPushButton {
                background-color: #FFFFFF;
                color: #0F172A;
                border: 1px solid #E2E8F0;
                border-radius: 6px;
                padding: 5px 14px;
                font-family: 'Segoe UI';
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #F1F5F9;
                border-color: #CBD5E1;
            }
            QPushButton:pressed {
                background-color: #E2E8F0;
            }
        """)
        
        from config import get_app_data_dir
        import os
        chk_path = os.path.join(get_app_data_dir(), "checkmark.png").replace("\\", "/")
        if os.path.exists(chk_path):
            self.setStyleSheet(self.styleSheet().replace("CHECKMARK_PATH", chk_path))
        else:
            self.setStyleSheet(self.styleSheet().replace("CHECKMARK_PATH", ""))
            
        self.init_ui()
        
        if self.collector:
            self.collector.emitter.log_written.connect(self.append_log)
            self.reload_logs()
        else:
            self.load_history_from_file()
            self.start_udp_listener()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)
        
        self.filter_input = QLineEdit(self)
        self.filter_input.setPlaceholderText("Filter logs by keyword...")
        self.filter_input.textChanged.connect(self.apply_filter)
        top_bar.addWidget(self.filter_input, 1)
        
        layout.addLayout(top_bar)
        
        self.log_display = QPlainTextEdit(self)
        self.log_display.setReadOnly(True)
        layout.addWidget(self.log_display, 1)
        
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(12)
        
        self.auto_scroll_cb = QCheckBox("Auto-scroll", self)
        self.auto_scroll_cb.setChecked(True)
        bottom_bar.addWidget(self.auto_scroll_cb)
        
        bottom_bar.addStretch()
        
        self.clear_btn = QPushButton("Clear", self)
        self.clear_btn.clicked.connect(self.clear_logs)
        bottom_bar.addWidget(self.clear_btn)
        
        self.export_btn = QPushButton("Export Log", self)
        self.export_btn.clicked.connect(self.export_logs)
        bottom_bar.addWidget(self.export_btn)
        
        layout.addLayout(bottom_bar)

    def load_history_from_file(self):
        try:
            from config import get_app_data_root
            import os
            log_file = os.path.join(get_app_data_root(), "TrueHour_active.log")
            if os.path.exists(log_file):
                with open(log_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                filter_text = self.filter_input.text().strip().lower()
                batch_htmls = []
                for line in lines:
                    if not filter_text or filter_text in line.lower():
                        batch_htmls.append(self.colorize_text(line))
                if batch_htmls:
                    self.log_display.appendHtml("".join(batch_htmls))
                
                scrollbar = self.log_display.verticalScrollBar()
                scrollbar.setValue(scrollbar.maximum())
        except Exception as e:
            self.log_display.appendHtml(f'<span style="color:#EF4444;">Failed to load log history: {e}</span>')

    def start_udp_listener(self):
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.udp_sock.bind(("127.0.0.1", 50099))
        except Exception:
            # Address already in use: another console is running, so exit gracefully
            QMessageBox.warning(self, "Console Already Open", "TrueHour Debug Console is already running.")
            sys.exit(0)
            
        self.listener_active = True
        
        class UDPLogSignalEmitter(QObject):
            log_received = pyqtSignal(str)
            
        self.udp_emitter = UDPLogSignalEmitter()
        self.udp_emitter.log_received.connect(self.append_log)
        
        def udp_worker():
            while self.listener_active:
                try:
                    data, _ = self.udp_sock.recvfrom(65535)
                    if data:
                        text = data.decode("utf-8", errors="replace")
                        self.udp_emitter.log_received.emit(text)
                except Exception:
                    break
                    
        self.udp_thread = threading.Thread(target=udp_worker, daemon=True)
        self.udp_thread.start()

    def reload_logs(self):
        self.log_display.clear()
        if self.collector:
            with self.collector.lock:
                logs_snapshot = list(self.collector.buffer)
            filter_text = self.filter_input.text().strip().lower()
            batch_htmls = []
            for text in logs_snapshot:
                if not filter_text or filter_text in text.lower():
                    batch_htmls.append(self.colorize_text(text))
            if batch_htmls:
                self.log_display.appendHtml("".join(batch_htmls))
            if self.auto_scroll_cb.isChecked():
                scrollbar = self.log_display.verticalScrollBar()
                scrollbar.setValue(scrollbar.maximum())
        else:
            self.load_history_from_file()

    def append_log(self, text):
        filter_text = self.filter_input.text().strip().lower()
        if filter_text and filter_text not in text.lower():
            return
            
        scrollbar = self.log_display.verticalScrollBar()
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 10
        
        colored_html = self.colorize_text(text)
        self.log_display.appendHtml(colored_html)
        
        if self.auto_scroll_cb.isChecked() and at_bottom:
            scrollbar.setValue(scrollbar.maximum())

    def colorize_text(self, text):
        escaped = html.escape(text).replace('\n', '<br>')
        lower_text = text.lower()
        
        # Telemetry Action coloring (premium bright cyan)
        if "[action]" in lower_text:
            return f'<span style="color:#06B6D4; font-weight: bold;">{escaped}</span>'
            
        if "error" in lower_text or "critical" in lower_text or "exception" in lower_text or "traceback" in lower_text:
            return f'<span style="color:#EF4444; font-weight: 500;">{escaped}</span>'
        elif "warning" in lower_text or "warn" in lower_text:
            return f'<span style="color:#F59E0B; font-weight: 500;">{escaped}</span>'
        elif "info" in lower_text:
            return f'<span style="color:#e0e0e0;">{escaped}</span>'
        elif "debug" in lower_text:
            return f'<span style="color:#94A3B8;">{escaped}</span>'
            
        return f'<span style="color:#F8FAFC;">{escaped}</span>'

    def apply_filter(self):
        self.reload_logs()

    def clear_logs(self):
        if self.collector:
            with self.collector.lock:
                self.collector.buffer.clear()
        try:
            from config import get_app_data_root
            import os
            log_file = os.path.join(get_app_data_root(), "TrueHour_active.log")
            if os.path.exists(log_file):
                with open(log_file, "w", encoding="utf-8") as f:
                    f.write(f"--- Log Cleared at {datetime.now()} ---\n")
        except Exception:
            pass
        self.log_display.clear()

    def export_logs(self):
        path, _ = QFileDialog.getSaveFileName(
            self, 
            "Export Debug Logs", 
            os.path.join(os.path.expanduser("~"), "focuslog_debug.log"),
            "Log Files (*.log);;Text Files (*.txt)"
        )
        if path:
            try:
                if self.collector:
                    with open(path, "w", encoding="utf-8") as f:
                        with self.collector.lock:
                            f.writelines(self.collector.buffer)
                else:
                    from config import get_app_data_root
                    import shutil
                    log_file = os.path.join(get_app_data_root(), "TrueHour_active.log")
                    if os.path.exists(log_file):
                        shutil.copy(log_file, path)
                    else:
                        with open(path, "w", encoding="utf-8") as f:
                            f.write(self.log_display.toPlainText())
                QMessageBox.information(self, "Success", "Logs exported successfully.")
            except Exception as e:
                QMessageBox.critical(self, "Export Failed", f"Could not export logs:\n{e}")

    def closeEvent(self, event):
        if self.collector:
            self.hide()
            event.ignore()
        else:
            self.listener_active = False
            if self.udp_sock:
                try:
                    self.udp_sock.close()
                except Exception:
                    pass
            event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Start in standalone client mode
    window = DebugTerminalWindow()
    window.show()
    sys.exit(app.exec())
