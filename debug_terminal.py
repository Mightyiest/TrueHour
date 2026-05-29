"""
FocusLog — Debug Terminal Module
Manages thread-safe stdout/stderr and logging redirection to a premium, toggleable UI panel.
"""
import sys
import html
from collections import deque
import threading
from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QLineEdit,
    QPushButton, QCheckBox, QLabel, QFileDialog, QMessageBox
)

class LogSignalEmitter(QObject):
    log_written = pyqtSignal(str)

class LogBufferCollector:
    """Thread-safe collector that intercepts sys.stdout and sys.stderr and retains a memory buffer."""
    def __init__(self, max_lines=1000):
        self.buffer = deque(maxlen=max_lines)
        self.emitter = LogSignalEmitter()
        self.lock = threading.Lock()
        
        self._stdout = sys.stdout
        self._stderr = sys.stderr
        self._is_redirected = False

    def write_log(self, text):
        if not text:
            return
        with self.lock:
            self.buffer.append(text)
            self.emitter.log_written.emit(text)

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
    """Helper stream object to replace sys.stdout and sys.stderr."""
    def __init__(self, collector, is_stderr=False):
        self.collector = collector
        self.is_stderr = is_stderr

    def write(self, text):
        if text:
            self.collector.write_log(text)
            # Write to original console streams to keep terminal logging visible
            if self.is_stderr:
                self.collector._stderr.write(text)
            else:
                self.collector._stdout.write(text)

    def flush(self):
        if self.is_stderr:
            self.collector._stderr.flush()
        else:
            self.collector._stdout.flush()

class DebugTerminalWindow(QDialog):
    """Modern Windows-11 style dialog to display active logs with filtering, colorizing and auto-scroll."""
    def __init__(self, collector, parent=None):
        super().__init__(parent)
        self.collector = collector
        self.setWindowTitle("FocusLog Debug Console")
        self.resize(620, 420)
        self.setMinimumSize(450, 300)
        
        # Stylesheet matching FocusLog's elegant design language
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
        
        # Inject standard checkmark image path if exists
        from config import get_app_data_dir
        import os
        chk_path = os.path.join(get_app_data_dir(), "checkmark.png").replace("\\", "/")
        if os.path.exists(chk_path):
            self.setStyleSheet(self.styleSheet().replace("CHECKMARK_PATH", chk_path))
        else:
            self.setStyleSheet(self.styleSheet().replace("CHECKMARK_PATH", ""))
        
        self.init_ui()
        
        # Connect thread-safe signal for live streaming
        self.collector.emitter.log_written.connect(self.append_log)
        
        # Load logs already in buffer
        self.reload_logs()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        
        # Filter Bar Layout
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)
        
        self.filter_input = QLineEdit(self)
        self.filter_input.setPlaceholderText("Filter logs by keyword...")
        self.filter_input.textChanged.connect(self.apply_filter)
        top_bar.addWidget(self.filter_input, 1)
        
        layout.addLayout(top_bar)
        
        # Console Output
        self.log_display = QPlainTextEdit(self)
        self.log_display.setReadOnly(True)
        layout.addWidget(self.log_display, 1)
        
        # Bottom Controls
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

    def reload_logs(self):
        self.log_display.clear()
        with self.collector.lock:
            # Re-read queue under lock
            logs_snapshot = list(self.collector.buffer)
        
        # Append lines that match current filter
        filter_text = self.filter_input.text().strip().lower()
        
        # Batch HTML construction to avoid frequent rendering updates
        batch_htmls = []
        for text in logs_snapshot:
            if not filter_text or filter_text in text.lower():
                batch_htmls.append(self.colorize_text(text))
                
        if batch_htmls:
            # Combine batch to prevent cursor movements blinking
            self.log_display.appendHtml("".join(batch_htmls))
            
        # Ensure scrollbar goes to bottom if autoscroll active
        if self.auto_scroll_cb.isChecked():
            scrollbar = self.log_display.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

    def append_log(self, text):
        """Callback triggered via pyqtSignal on the main thread."""
        filter_text = self.filter_input.text().strip().lower()
        if filter_text and filter_text not in text.lower():
            return
            
        scrollbar = self.log_display.verticalScrollBar()
        # Keep track if we were already at the bottom
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 10
        
        colored_html = self.colorize_text(text)
        self.log_display.appendHtml(colored_html)
        
        if self.auto_scroll_cb.isChecked() and at_bottom:
            scrollbar.setValue(scrollbar.maximum())

    def colorize_text(self, text):
        """Converts raw log lines to modern syntax-colored HTML elements."""
        escaped = html.escape(text).replace('\n', '<br>')
        lower_text = text.lower()
        
        # Level mapping and coloring
        if "error" in lower_text or "critical" in lower_text or "exception" in lower_text or "traceback" in lower_text:
            return f'<span style="color:#EF4444; font-weight: 500;">{escaped}</span>'
        elif "warning" in lower_text or "warn" in lower_text:
            return f'<span style="color:#F59E0B; font-weight: 500;">{escaped}</span>'
        elif "info" in lower_text:
            return f'<span style="color:#38BDF8;">{escaped}</span>'
        elif "debug" in lower_text:
            return f'<span style="color:#94A3B8;">{escaped}</span>'
            
        return f'<span style="color:#F8FAFC;">{escaped}</span>'

    def apply_filter(self):
        self.reload_logs()

    def clear_logs(self):
        with self.collector.lock:
            self.collector.buffer.clear()
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
                with open(path, "w", encoding="utf-8") as f:
                    with self.collector.lock:
                        f.writelines(self.collector.buffer)
                QMessageBox.information(self, "Success", "Logs exported successfully.")
            except Exception as e:
                QMessageBox.critical(self, "Export Failed", f"Could not export logs:\n{e}")

    def closeEvent(self, event):
        # Override standard close to just hide the dialog, preserving its state
        self.hide()
        event.ignore()
