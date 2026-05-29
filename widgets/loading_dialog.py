"""
Loading dialog widget to show during background operations.
"""
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont


class LoadingDialog(QDialog):
    """
    A non-blocking loading dialog with progress indicator.
    """
    
    def __init__(self, parent=None, title: str = "Generating Report", message: str = "Please wait..."):
        super().__init__(parent)
        
        self.setWindowTitle(title)
        self.setModal(False)
        self.setFixedSize(400, 150)
        
        # Remove close button to prevent accidental closure
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint)
        
        # Center on parent
        if parent:
            self.setParent(parent)
            self.move(
                parent.x() + (parent.width() - self.width()) // 2,
                parent.y() + (parent.height() - self.height()) // 2
            )
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # Title label
        self.title_label = QLabel(title)
        self.title_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)
        
        # Message label
        self.message_label = QLabel(message)
        self.message_label.setFont(QFont("Arial", 10))
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message_label.setStyleSheet("color: #6b7280;")
        layout.addWidget(self.message_label)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #e5e7eb;
                border-radius: 5px;
                background: #f9fafb;
            }
            QProgressBar::chunk {
                background: linear-gradient(90deg, #667eea, #764ba2);
                border-radius: 5px;
            }
        """)
        layout.addWidget(self.progress_bar)
        
        self.setLayout(layout)
    
    def update_progress(self, value: int, message: str = ""):
        """Update progress bar and optionally message."""
        self.progress_bar.setValue(value)
        if message:
            self.message_label.setText(message)
    
    def set_message(self, message: str):
        """Update only the message."""
        self.message_label.setText(message)
