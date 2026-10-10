"""
Tests for UI Dialog Stability, Widget Teardown, and Animation State Transitions.
Prevents regression of STATUS_ACCESS_VIOLATION (0xC0000005) issues.
"""

import sys
import unittest
from PyQt6.QtWidgets import QApplication, QPushButton, QLineEdit
from PyQt6.QtCore import QCoreApplication

from tracker import AppTracker
from dialogs.categories_dialog import CategoriesDialog
from widgets.update_label import FadingVersionLabel
from widgets.custom_widgets import EmailChipWidget
from debug_terminal import LogBufferCollector


class TestUIDialogStability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication(sys.argv)

    def test_log_buffer_collector_lazy_emitter(self):
        """Test that LogBufferCollector does not crash or emit improperly."""
        collector = LogBufferCollector()
        try:
            collector.write_log("Test early message\n")
            self.assertIn("Test early message\n", list(collector.buffer))
            self.assertIsNotNone(collector.emitter)
        finally:
            collector.udp_socket.close()

    def test_categories_dialog_add_and_delete(self):
        """Test adding and deleting categories via UI without access violations."""
        tracker = AppTracker()
        tracker.tag_manager.projects = ["Unassigned", "Work", "Personal"]

        dialog = CategoriesDialog(tracker, theme_style="light")
        dialog.show()
        self.app.processEvents()

        signal_emitted = []
        dialog.categories_changed.connect(lambda: signal_emitted.append(True))

        # Test Add Category
        dialog.add_entry.setText("Research")
        dialog._add_project()
        self.app.processEvents()

        self.assertIn("Research", tracker.tag_manager.projects)
        self.assertTrue(len(signal_emitted) > 0)

        # Test Delete Category (simulating clicking delete on 'Research')
        signal_emitted.clear()
        dialog._delete_project("Research")
        self.app.processEvents()

        self.assertNotIn("Research", tracker.tag_manager.projects)
        self.assertTrue(len(signal_emitted) > 0)

        # Multiple processEvents cycles to ensure singleShot deferrals execute cleanly
        for _ in range(5):
            self.app.processEvents()

        dialog.close()
        dialog.deleteLater()
        self.app.processEvents()

    def test_fading_version_label_sync_and_restore(self):
        """Test FadingVersionLabel state machine transitions during sync and restore."""
        label = FadingVersionLabel("v4.1.0-beta.1")
        label.show()
        self.app.processEvents()

        # Enter cloud sync progress
        label.show_sync_progress("Uploading backup...", percent=45)
        self.app.processEvents()
        self.assertTrue(label._is_syncing)
        self.assertFalse(label._is_restoring)

        # Enter cloud sync finished
        label.show_sync_finished(success=True, message="Backup complete")
        self.app.processEvents()
        self.assertFalse(label._is_syncing)

        # Trigger restore display
        label._restore_normal_display()
        self.app.processEvents()
        self.assertTrue(label._is_restoring)

        # Advance animation to completion
        label._anim.setCurrentTime(label._anim.duration())
        label._on_animation_finished()
        self.app.processEvents()

        label.close()
        label.deleteLater()
        self.app.processEvents()

    def test_email_chip_widget_removal(self):
        """Test EmailChipWidget chip deletion does not invoke setParent(None)."""
        widget = EmailChipWidget()
        widget.show()
        self.app.processEvents()

        widget.set_emails(["test1@example.com", "test2@example.com"])
        self.app.processEvents()
        self.assertEqual(len(widget.get_emails()), 2)

        # Remove single chip
        widget._remove_chip("test1@example.com", widget._chip_widgets[0])
        self.app.processEvents()
        self.assertEqual(widget.get_emails(), ["test2@example.com"])

        # Clear remaining
        widget.clear()
        self.app.processEvents()
        self.assertEqual(len(widget.get_emails()), 0)

        widget.close()
        widget.deleteLater()
        self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
