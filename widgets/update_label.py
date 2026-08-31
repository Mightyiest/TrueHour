"""
TrueHour — Fading Version / Update-Available / Cloud Sync Label Widget.
Alternates between the current version string, an "Update available" message,
and real-time circulating cloud synchronization loading & completion states.
"""

import webbrowser
from urllib.parse import urlparse

from PyQt6.QtWidgets import QLabel, QGraphicsOpacityEffect, QMessageBox
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QMouseEvent

# GitHub releases page for TrueHour
GITHUB_RELEASES_URL = "https://github.com/Mightyiest/TrueHour/releases"


class FadingVersionLabel(QLabel):
    """
    A QLabel that displays version & build metadata, with support for:
    1. Circulating animated spinner & percentage during Google Drive cloud sync.
    2. Confirmation checkmark status upon backup/sync completion with auto-revert.
    3. Update-available notification crossfades.
    4. Developer easter egg click handling.
    """

    # Duration of one fade-out or fade-in leg (ms)
    FADE_DURATION = 600
    # How long each text stays fully visible before switching (ms)
    DISPLAY_HOLD = 3000
    # Circulating Braille spinner animation frames
    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, version_text: str, parent=None):
        super().__init__(version_text, parent)
        self._version_text = version_text
        self._update_text = "✨ Update available"
        self._release_url = GITHUB_RELEASES_URL
        self._new_version = ""
        self._showing_update = False
        self._update_available = False
        self._is_dark = False
        self._dismissed = False

        # Cloud sync state
        self._is_syncing = False
        self._spinner_index = 0
        self._current_sync_msg = ""
        self._current_sync_percent = None

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

        # Timer that triggers fade transitions for updates
        self._cycle_timer = QTimer(self)
        self._cycle_timer.setSingleShot(True)
        self._cycle_timer.timeout.connect(self._start_fade_out)

        # Spinner animation timer for real-time circulating loading
        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(80)
        self._spinner_timer.timeout.connect(self._on_spinner_tick)

        # Restore timer to return to normal version text after confirmation
        self._restore_timer = QTimer(self)
        self._restore_timer.setSingleShot(True)
        self._restore_timer.timeout.connect(self._restore_normal_display)

    # ── Cloud Sync Status API ────────────────────────────────────────

    def show_sync_progress(self, msg: str = "Syncing in progress...", percent: int = None):
        """Display circulating loading spinner with sync progress/percentage."""
        self._restore_timer.stop()
        if self._cycle_timer.isActive():
            self._cycle_timer.stop()
        self._anim.stop()
        self._opacity.setOpacity(1.0)

        self._is_syncing = True
        self._current_sync_msg = msg
        self._current_sync_percent = percent
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setToolTip(f"Google Drive Cloud Backup: {msg}")

        if not self._spinner_timer.isActive():
            self._spinner_timer.start()

        self._update_sync_display()

    def show_sync_finished(self, success: bool = True, message: str = ""):
        """Display completion confirmation and start revert countdown."""
        self._spinner_timer.stop()
        self._is_syncing = False
        self._opacity.setOpacity(1.0)

        if success:
            confirm_text = f"✓ {message or 'Cloud backup complete'}"
            self.setText(confirm_text)
            self._apply_success_style()
            self.setToolTip("Google Drive Cloud Backup synchronized successfully.")
        else:
            err_text = f"⚠️ {message or 'Cloud sync failed'}"
            self.setText(err_text)
            self._apply_error_style()
            self.setToolTip(f"Google Drive Sync Issue: {message or 'Could not complete cloud backup'}")

        # Hold confirmation for 4.5 seconds before smoothly restoring version
        self._restore_timer.start(4500)

    def _on_spinner_tick(self):
        """Cycle circulating spinner frames."""
        self._spinner_index = (self._spinner_index + 1) % len(self.SPINNER_FRAMES)
        self._update_sync_display()

    def _update_sync_display(self):
        """Render current spinner frame and sync status message."""
        frame = self.SPINNER_FRAMES[self._spinner_index]
        if self._current_sync_percent is not None:
            text = f"{frame} Syncing in progress... {self._current_sync_percent}%"
        elif self._current_sync_msg:
            text = f"{frame} {self._current_sync_msg}"
        else:
            text = f"{frame} Syncing to Google Drive..."

        self.setText(text)
        self._apply_sync_style()

    def _restore_normal_display(self):
        """Smoothly cross-fade from confirmation back to default version text."""
        if self._is_syncing:
            return

        self._anim.stop()
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)

        def _on_faded_out():
            try:
                self._anim.finished.disconnect(_on_faded_out)
            except Exception:
                pass
            if self._is_syncing:
                return
            self.setText(self._version_text)
            self._apply_base_style()
            self.setToolTip("")
            self._anim.setStartValue(0.0)
            self._anim.setEndValue(1.0)
            self._anim.start()

            # Resume update cycles if an update was waiting
            if self._update_available and not self._dismissed:
                self._cycle_timer.start(self.DISPLAY_HOLD)

        self._anim.finished.connect(_on_faded_out)
        self._anim.start()

    # ── Update Notification API ──────────────────────────────────────

    def set_update_available(
        self, available: bool, new_version: str = "", release_url: str = ""
    ):
        """Call this to start or stop the fade cycle."""
        self._update_available = available
        self._dismissed = False
        if new_version:
            self._new_version = new_version
            self._update_text = f"✨ {new_version} available"
        if release_url:
            self._release_url = release_url

        if self._is_syncing:
            return

        if available:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setToolTip(f"Click to view {new_version or 'the latest release'}")
            self._showing_update = False
            self.setText(self._version_text)
            self._opacity.setOpacity(1.0)
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
        if self._is_syncing:
            self._apply_sync_style()
        else:
            self._apply_base_style()

    # ── Animation cycle ──────────────────────────────────────────────

    def _start_fade_out(self):
        """Fade the current text to invisible."""
        if not self._update_available or self._is_syncing:
            return
        self._anim.stop()
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.start()

    def _on_animation_finished(self):
        """Handle transition after fade-out or fade-in completes."""
        if not self._update_available or self._is_syncing:
            return

        end_val = self._anim.endValue()
        if end_val == 0.0:
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
        color = "#d1d5db" if self._is_dark else "#0078D4"
        self.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 9px; font-weight: bold; "
            f"color: {color}; background: transparent; border: none;"
        )

    def _apply_sync_style(self):
        color = "#60A5FA" if self._is_dark else "#0078D4"
        self.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 9px; font-weight: 600; "
            f"color: {color}; background: transparent; border: none;"
        )

    def _apply_success_style(self):
        color = "#10B981" if self._is_dark else "#059669"
        self.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 9px; font-weight: bold; "
            f"color: {color}; background: transparent; border: none;"
        )

    def _apply_error_style(self):
        color = "#EF4444" if self._is_dark else "#DC2626"
        self.setStyleSheet(
            f"font-family: 'Segoe UI'; font-size: 9px; font-weight: bold; "
            f"color: {color}; background: transparent; border: none;"
        )

    # ── Click handling ───────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)

        if self._is_syncing:
            return

        if self._update_available:
            self._stop_animation()
            self._show_update_dialog()
        else:
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
            parsed = urlparse(self._release_url)
            if parsed.scheme == "https" and parsed.netloc.lower() == "github.com":
                target_url = self._release_url
            else:
                target_url = GITHUB_RELEASES_URL
            webbrowser.open(target_url)
            self._update_available = False
            self._showing_update = False
            self.setText(self._version_text)
            self._apply_base_style()
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.setToolTip("")
        else:
            self._dismissed = True
            self._showing_update = False
            self.setText(self._version_text)
            self._apply_base_style()
            self._opacity.setOpacity(1.0)
            self._cycle_timer.start(self.DISPLAY_HOLD)

