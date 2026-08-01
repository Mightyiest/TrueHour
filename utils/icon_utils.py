"""
TrueHour — Icon Utility Functions
Native Windows executable icon extraction and PIL image conversion.
"""

import io
import logging
import os
from PyQt6.QtCore import QFileInfo, QSize
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QFileIconProvider

logger = logging.getLogger(__name__)

_ICON_PROVIDER = None


def pil_to_pixmap(pil_img):
    """Convert a PIL Image safely to a QPixmap for PyQt6 icon rendering using QImage.fromData."""
    if not pil_img:
        return None
    try:
        byte_arr = io.BytesIO()
        pil_img.save(byte_arr, format="PNG")
        png_bytes = byte_arr.getvalue()
        qim = QImage.fromData(png_bytes)
        return QPixmap.fromImage(qim)
    except Exception as e:
        logger.debug("pil_to_pixmap failed: %s", e)
        return None


def get_native_icon_pixmap(exe_path: str, size: int = 16):
    """Retrieve the native system icon for a file path using a shared QFileIconProvider."""
    global _ICON_PROVIDER
    if not exe_path or not os.path.exists(exe_path):
        return None
    try:
        if _ICON_PROVIDER is None:
            _ICON_PROVIDER = QFileIconProvider()
        file_info = QFileInfo(exe_path)
        icon = _ICON_PROVIDER.icon(file_info)
        if icon and not icon.isNull():
            return icon.pixmap(QSize(size, size))
    except Exception as e:
        logger.debug("Failed to get native icon for %s: %s", exe_path, e)
    return None
