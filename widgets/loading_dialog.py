from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton, QHBoxLayout
from PyQt6.QtCore import Qt
from theme import get_qss_style, get_dark_palette, get_light_palette

class LoadingDialog(QDialog):
    """
    Elegant, frameless loading overlay following the modern Fluent Design system.
    """
    def __init__(self, message="Generating Report...", parent=None, is_dark=False, can_cancel=True, worker=None):
        super().__init__(parent)
        self.setWindowTitle("Processing")
        self.setFixedSize(300, 140)
        
        # Frameless native UI look
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        
        # Styling Setup
        self.setStyleSheet(get_qss_style(is_dark))
        self.setPalette(get_dark_palette() if is_dark else get_light_palette())
        
        self.worker = worker
        self.compiled_report = None
        self.error_message = None
        if self.worker:
            self.worker.status_changed.connect(self.update_status)
            self.worker.finished.connect(self._on_worker_finished)
            self.worker.error.connect(self._on_worker_error)
            
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        # Message Label
        self.label = QLabel(message, self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("font-family: 'Segoe UI'; font-size: 13px; font-weight: 600; border: none;")
        layout.addWidget(self.label)
        
        # Infinite Animated Progress Bar
        self.progress = QProgressBar(self)
        self.progress.setRange(0, 0) # Infinite state
        self.progress.setFixedHeight(6)
        
        # Apply specific accent colors
        accent = "#d1d5db" if is_dark else "#0078D4"
        bg_bar = "#333333" if is_dark else "#E2E8F0"
        self.progress.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                border-radius: 3px;
                background-color: {bg_bar};
            }}
            QProgressBar::chunk {{
                background-color: {accent};
                border-radius: 3px;
            }}
        """)
        layout.addWidget(self.progress)
        
        # Cancel option
        self.was_cancelled = False
        if can_cancel:
            btn_layout = QHBoxLayout()
            btn_layout.addStretch()
            self.cancel_btn = QPushButton("Cancel", self)
            self.cancel_btn.setObjectName("NormalButton")
            self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.cancel_btn.clicked.connect(self._on_cancel)
            btn_layout.addWidget(self.cancel_btn)
            btn_layout.addStretch()
            layout.addLayout(btn_layout)

    def _on_cancel(self):
        self.was_cancelled = True
        self.reject()

    def update_status(self, percent, text=None):
        """Thread-safe update of the status message label and progress percentage."""
        if isinstance(percent, str):
            text = percent
            percent = -1
            
        if text:
            self.label.setText(text)
            
        if percent >= 0:
            self.progress.setRange(0, 100)
            self.progress.setValue(percent)
        else:
            self.progress.setRange(0, 0) # Indeterminate state

    def showEvent(self, event):
        super().showEvent(event)
        if self.worker:
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(300, self.worker.start)

    def _on_worker_finished(self, report):
        self.compiled_report = report
        self.accept()

    def _on_worker_error(self, err_msg):
        self.error_message = err_msg
        self.reject()



