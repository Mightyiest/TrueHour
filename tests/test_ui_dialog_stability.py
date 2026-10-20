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
import os
import tempfile
from debug_terminal import LogBufferCollector


class TestUIDialogStability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._temp_dir = tempfile.TemporaryDirectory()
        cls._orig_localappdata = os.environ.get("LOCALAPPDATA")
        cls._orig_appdata = os.environ.get("APPDATA")
        os.environ["LOCALAPPDATA"] = cls._temp_dir.name
        os.environ["APPDATA"] = cls._temp_dir.name

        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication(sys.argv)

    @classmethod
    def tearDownClass(cls):
        if cls._orig_localappdata is not None:
            os.environ["LOCALAPPDATA"] = cls._orig_localappdata
        else:
            os.environ.pop("LOCALAPPDATA", None)
        if cls._orig_appdata is not None:
            os.environ["APPDATA"] = cls._orig_appdata
        else:
            os.environ.pop("APPDATA", None)
        cls._temp_dir.cleanup()

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

        # Test Add Category (custom user category)
        dialog.add_entry.setText("Client Alpha")
        dialog._add_project()
        self.app.processEvents()

        self.assertIn("Client Alpha", tracker.tag_manager.projects)
        self.assertTrue(len(signal_emitted) > 0)

        # Test Delete Category (simulating clicking delete on 'Client Alpha')
        signal_emitted.clear()
        dialog._delete_project("Client Alpha")
        self.app.processEvents()

        self.assertNotIn("Client Alpha", tracker.tag_manager.projects)
        self.assertTrue(len(signal_emitted) > 0)

        # Multiple processEvents cycles to ensure singleShot deferrals execute cleanly
        for _ in range(5):
            self.app.processEvents()

        dialog.close()
        dialog.deleteLater()
        self.app.processEvents()

    def test_categories_dialog_app_assignment_and_reassignment(self):
        """Test listing, adding, reassigning, and removing applications from categories directly."""
        tracker = AppTracker()
        tracker.tag_manager.projects = ["Unassigned", "Development", "Design"]
        tracker.tag_manager.mappings = {}

        dialog = CategoriesDialog(tracker, theme_style="light")
        dialog.show()
        self.app.processEvents()

        # 1. Add application to "Design" category
        dialog._select_category("Design")
        self.app.processEvents()
        self.assertEqual(dialog._selected_category, "Design")

        dialog.app_name_entry.setText("Figma")
        dialog.target_cat_combo.setCurrentText("Design")
        dialog._assign_entered_app()
        self.app.processEvents()

        design_apps = tracker.tag_manager.get_apps_for_project("Design")
        self.assertIn("Figma", design_apps)
        self.assertEqual(tracker.get_app_tag("Figma"), "Design")

        # 2. Reassign "Figma" from "Design" to "Development"
        dialog._reassign_app("Figma", old_cat="Design", new_cat="Development")
        self.app.processEvents()

        dev_apps = tracker.tag_manager.get_apps_for_project("Development")
        self.assertIn("Figma", dev_apps)
        self.assertEqual(tracker.get_app_tag("Figma"), "Development")
        self.assertNotIn("Figma", tracker.tag_manager.get_apps_for_project("Design"))

        # 3. Add second application
        dialog.app_name_entry.setText("VS Code")
        dialog.target_cat_combo.setCurrentText("Development")
        dialog._assign_entered_app()
        self.app.processEvents()

        all_mapped = tracker.tag_manager.get_all_mapped_apps()
        self.assertIn("Figma", all_mapped)
        self.assertIn("VS Code", all_mapped)

        # 4. Remove application
        dialog._remove_app("Figma")
        self.app.processEvents()

        dev_apps_after = tracker.tag_manager.get_apps_for_project("Development")
        self.assertNotIn("Figma", dev_apps_after)
        self.assertEqual(tracker.tag_manager.get_tag("Figma"), "Unassigned")
        all_mapped_after = tracker.tag_manager.get_all_mapped_apps()
        self.assertIn("VS Code", all_mapped_after)

        for _ in range(3):
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
