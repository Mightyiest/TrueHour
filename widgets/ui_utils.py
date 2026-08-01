"""
TrueHour — UI Utility Functions
Contains window layout and centering helpers.
"""

from PyQt6.QtWidgets import QApplication


def center_window(win, width: int, height: int):
    """Center a QWidget/QDialog on the primary screen."""
    win.resize(width, height)
    screen = QApplication.primaryScreen().geometry()
    x = (screen.width() - width) // 2
    y = (screen.height() - height) // 2
    win.move(x, y)
