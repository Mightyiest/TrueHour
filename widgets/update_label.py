"""
TrueHour — Fading Version / Update-Available Label Widget.
Alternates between the current version string and an "Update available"
message with a smooth fade-in / fade-out animation until the user
acknowledges or dismisses the update.
"""

import webbrowser

from PyQt6.QtWidgets import QLabel, QGraphicsOpacityEffect, QMessageBox
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QMouseEvent

# GitHub releases page for TrueHour
GITHUB_RELEASES_URL = "https://github.com/Mightyiest/TrueHour/releases"


class FadingVersionLabel(QLabel):
    """
    A QLabel that, when an update is available, crossfades between the
    normal version text and an accent-coloured "Update available" hint.

    When no update is flagged it behaves exactly like a plain QLabel
    (including forwarding clicks for the developer-mode easter egg).
    """

    # Duration of one fade-out or fade-in leg (ms)
    FADE_DURATION = 600
    # How long each text stays fully visible before switching (ms)
    DISPLAY_HOLD = 3000

    def __init__(self, version_text: str, parent=None):
        super().__init__(version_text, parent)
        self._version_text = version_text
        self._update_text = "✨ Update available"
        self._release_url = GITHUB_RELEASES_URL
        self._new_version = ""
        self._showing_update = False
        self._update_available = False
        self._is_dark = False
        self._dismissed = False  # True after user clicks "No" — animation keeps going

        # External callback for the developer-mode easter egg
        self._version_click_handler = None

        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._apply_base_style()

        # Opacity effect for smooth fading
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity)

        # Animation on the opacity property
        self._anim = QPropertyAnimation(self._opacity, b"opacity", self)
        self._anim.setDuration(self.FADE_DURATION)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._anim.finished.connect(self._on_animation_finished)

        # Timer that triggers fade transitions
        self._cycle_timer = QTimer(self)
        self._cycle_timer.setSingleShot(True)
        self._cycle_timer.timeout.connect(self._start_fade_out)

    # ── Public API ───────────────────────────────────────────────────

    def set_update_available(self, available: bool, new_version: str = "", release_url: str = ""):
        """Call this to start or stop the fade cycle."""
        self._update_available = available
        self._dismissed = False
        if new_version:
            self._new_version = new_version
            self._update_text = f"✨ {new_version} available"
        if release_url:
            self._release_url = release_url
        if available:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setToolTip(f"Click to view {new_version or 'the latest release'}")
            self._showing_update = False
            self.setText(self._version_text)
            self._opacity.setOpacity(1.0)
            # Kick off the first cycle after a brief pause
            self._cycle_timer.start(self.DISPLAY_HOLD)
        else:
            self._stop_animation()
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.setToolTip("")
            self.setText(self._version_text)
            self._opacity.setOpacity(1.0)
            self._apply_base_style()

    def set_version_click_handler(self, handler):
        """Forward raw mouse-press events for the dev-mode easter egg."""
        self._version_click_handler = handler

    def update_theme(self, is_dark: bool):
        self._is_dark = is_dark
        self._apply_base_style()

    # ── Animation cycle ──────────────────────────────────────────────

    def _start_fade_out(self):
        """Fade the current text to invisible."""
        if not self._update_available:
            return
        self._anim.stop()
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.start()

    def _on_animation_finished(self):
        """Handle transition after fade-out or fade-in completes."""
        if not self._update_available:
            return

        end_val = self._anim.endValue()
        if end_val == 0.0:
            # We faded out. Swap text, apply style, and fade back in.
            self._showing_update = not self._showing_update
            if self._showing_update:
                self.setText(self._update_text)
                self._apply_update_style()
            else:
                self.setText(self._version_text)
                self._apply_base_style()

            self._anim.stop()
            self._anim.setStartValue(0.0)
            self._anim.setEndValue(1.0)
            self._anim.start()
        elif end_val == 1.0:
            # We faded in. Wait DISPLAY_HOLD ms before cycling again.
            self._cycle_timer.start(self.DISPLAY_HOLD)

    def _stop_animation(self):
        self._anim.stop()
        self._cycle_timer.stop()
        self._opacity.setOpacity(1.0)

    # ── Styling ──────────────────────────────────────────────────────

    def _apply_base_style(self):
        color = "#888" if self._is_dark else "#ABABAB"
        self.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 9px; color: {color}; "
            f"background: transparent; border: none;"
        )

    def _apply_update_style(self):
        color = "#6b8bb5" if self._is_dark else "#0078D4"
        self.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 9px; font-weight: bold; "
            f"color: {color}; background: transparent; border: none;"
        )

    # ── Click handling ───────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)

        if self._update_available:
            # Pause animation while the dialog is shown
            self._stop_animation()
            self._show_update_dialog()
        else:
            # Forward to the developer-mode easter egg handler
            if self._version_click_handler:
                self._version_click_handler(event)

    def _show_update_dialog(self):
        version_hint = f" ({self._new_version})" if self._new_version else ""
        msg = QMessageBox(self.window())
        msg.setWindowTitle("Update Available")
        msg.setText(f"A new version of TrueHour{version_hint} is available!")
        msg.setInformativeText(
            "Would you like to open the GitHub releases page to download it?"
        )
        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        msg.setDefaultButton(QMessageBox.StandardButton.Yes)
        msg.setIcon(QMessageBox.Icon.Information)

        result = msg.exec()

        if result == QMessageBox.StandardButton.Yes:
            webbrowser.open(self._release_url)
            # After opening, keep the label static on version text
            self._update_available = False
            self._showing_update = False
            self.setText(self._version_text)
            self._apply_base_style()
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.setToolTip("")
        else:
            # User dismissed — resume the fade animation
            self._dismissed = True
            self._showing_update = False
            self.setText(self._version_text)
            self._apply_base_style()
            self._opacity.setOpacity(1.0)
            self._cycle_timer.start(self.DISPLAY_HOLD)
