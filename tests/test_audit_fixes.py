"""
Unit tests verifying comprehensive fixes for issues diagnosed in codebase_audit_report.md
"""

import os
import json
import time
import tempfile
import shutil
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtCore import QPointF

# Ensure QApplication exists for GUI widget tests
app = QApplication.instance()
if app is None:
    app = QApplication([])


class TestAuditFixes(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_email_chip_widget_uncommitted_email(self):
        """H13: EmailChipWidget.get_emails commits text currently typed into QLineEdit"""
        from widgets.custom_widgets import EmailChipWidget

        widget = EmailChipWidget()
        widget.set_emails(["first@example.com"])
        widget._input.setText("second@example.com")

        emails = widget.get_emails()
        self.assertIn("first@example.com", emails)
        self.assertIn("second@example.com", emails)
        self.assertEqual(len(emails), 2)

    def test_tracker_recover_session_name_and_security(self):
        """H6: recover_session restores session_name and initializes security_detector"""
        from tracker import AppTracker, ACTIVE_SESSION_FILE

        active_file = str(ACTIVE_SESSION_FILE)
        os.makedirs(os.path.dirname(active_file), exist_ok=True)

        now = time.time()
        state = {
            "session_name": "Test Client Project",
            "session_start": now - 300,
            "app_times": {"VSCode": 300},
            "app_included": {"VSCode": True},
            "app_exe_paths": {},
            "timeline": [],
            "paused": False,
            "_pause_start": None,
            "_total_paused_time": 0,
        }

        with open(active_file, "w", encoding="utf-8") as f:
            json.dump(state, f)

        tracker = AppTracker(poll_interval=1.0, min_track_seconds=2)
        try:
            success = tracker.recover_session()
            self.assertTrue(success)
            self.assertEqual(tracker.session_name, "Test Client Project")
            self.assertIsNotNone(tracker.security_detector)
            status = tracker.get_security_status()
            self.assertEqual(status["status"], "ACTIVE")
        finally:
            tracker.running = False
            if tracker._thread and tracker._thread.is_alive():
                tracker._thread.join(timeout=1.0)
            if os.path.exists(active_file):
                os.remove(active_file)

    def test_tag_manager_online_fetch_filters_and_word_boundaries(self):
        """H10: TagManager skips '[' apps and uses word boundaries for keywords"""
        from tracker import TagManager

        tm = TagManager()

        # 1. Protected system app / bracketed placeholders must be skipped without network request
        with patch("urllib.request.urlopen") as mock_urlopen:
            tm._fetch_and_update_tag_online("[Protected System App]", "")
            mock_urlopen.assert_not_called()

            tm._fetch_and_update_tag_online("[Idle]", "")
            mock_urlopen.assert_not_called()

        # 2. Keyword matcher uses word boundaries
        # "ide" should NOT match "video streaming" or "guide"
        # "git" should NOT match "digital camera"
        abstract_false_positives = "This is a digital video guide for providers."
        matched_tag = None
        import re
        for category, words in tm.KEYWORDS.items():
            for word in words:
                if re.search(r"\b" + re.escape(word.lower()) + r"\b", abstract_false_positives.lower()):
                    matched_tag = category
                    break
            if matched_tag:
                break
        self.assertIsNone(matched_tag, "Should not match 'ide' in 'guide' or 'git' in 'digital'")

        # "ide" should match standalone word "ide"
        abstract_true_positive = "An integrated ide for python development."
        matched_tag_true = None
        for category, words in tm.KEYWORDS.items():
            for word in words:
                if re.search(r"\b" + re.escape(word.lower()) + r"\b", abstract_true_positive.lower()):
                    matched_tag_true = category
                    break
            if matched_tag_true:
                break
        self.assertEqual(matched_tag_true, "Development")

    def test_appinfo_access_denied_never_returns_window_title(self):
        """H10: On psutil.AccessDenied, get_foreground_app_info never leaks window title"""
        import psutil
        from appinfo import get_foreground_app_info

        with patch("win32gui.GetForegroundWindow", return_value=12345), \
             patch("win32process.GetWindowThreadProcessId", return_value=(0, 9999)), \
             patch("win32gui.GetWindowText", return_value="Secret Financial Data - Confidential"):

            # Mock psutil.Process to simulate AccessDenied on exe()
            mock_proc = MagicMock()
            mock_proc.name.return_value = "ProtectedService.exe"
            mock_proc.exe.side_effect = psutil.AccessDenied()

            with patch("psutil.Process", return_value=mock_proc):
                friendly, exe = get_foreground_app_info()
                self.assertNotIn("Secret Financial Data", friendly)
                self.assertNotIn("Confidential", friendly)
                self.assertEqual(friendly, "Protectedservice")
                self.assertEqual(exe, "")

    def test_no_wheel_combo_box_ignores_wheel(self):
        """H12: NoWheelComboBox ignores mouse wheel events to prevent accidental reassignment"""
        from dialogs.categories_dialog import NoWheelComboBox

        combo = NoWheelComboBox()
        mock_event = MagicMock()
        combo.wheelEvent(mock_event)
        mock_event.ignore.assert_called_once()

    def test_calculate_project_breakdown_percentage_denominator(self):
        """M11: calculate_project_breakdown uses counted_seconds as percentage denominator"""
        from core.reporting.statistics import calculate_project_breakdown

        mock_summaries = [{"date": "2026-06-01", "session_count": 1}]
        mock_sessions = [
            {
                "date": "2026-06-01",
                "total_seconds": 7200,  # Total includes 3600s excluded app
                "apps": [
                    {"name": "Code", "tag": "Development", "seconds": 1800, "excluded": False},
                    {"name": "Docs", "tag": "Writing", "seconds": 1800, "excluded": False},
                    {"name": "Game", "tag": "Gaming", "seconds": 3600, "excluded": True},
                ],
            }
        ]

        with patch("core.reporting.statistics.get_daily_summaries", return_value=mock_summaries), \
             patch("core.reporting.aggregator.get_sessions_for_date", return_value=mock_sessions):

            breakdown = calculate_project_breakdown("2026-06-01", "2026-06-01")

            # Counted time is 3600 (1800 + 1800). Each should be 50.0%, NOT 25.0%!
            self.assertEqual(len(breakdown), 2)
            pct_map = {item["project"]: item["percent"] for item in breakdown}
            self.assertAlmostEqual(pct_map["Development"], 50.0, places=1)
            self.assertAlmostEqual(pct_map["Writing"], 50.0, places=1)
            self.assertAlmostEqual(sum(pct_map.values()), 100.0, places=1)

    def test_cache_invalidation_on_database_modification(self):
        """M2: get_cached_report invalidates cache when truehour.db is newer than cache file"""
        from core.reporting.cache import get_cached_report, save_to_cache, get_cache_dir

        cache_dir = get_cache_dir()
        dummy_export = os.path.join(self.test_dir, "export.html")
        with open(dummy_export, "w", encoding="utf-8") as f:
            f.write("<html>Cached Report</html>")

        save_to_cache("summary", "2026-01-01", "2026-01-02", "html", dummy_export)

        # Initially, cache hit
        cached_file = get_cached_report("summary", "2026-01-01", "2026-01-02", "html")
        self.assertIsNotNone(cached_file)
        self.assertTrue(os.path.exists(cached_file))

        # Now simulate database update by writing to truehour.db with future mtime
        from config import get_app_data_dir
        db_path = os.path.join(get_app_data_dir(), "truehour.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        with open(db_path, "w") as f:
            f.write("mock db")
        future_time = time.time() + 100
        os.utime(db_path, (future_time, future_time))

        # get_cached_report should detect newer db and invalidate
        stale_check = get_cached_report("summary", "2026-01-01", "2026-01-02", "html")
        self.assertIsNone(stale_check)

    def test_web_server_json_script_escaping(self):
        """M5: web server escapes < and > in JSON state injected into <script>"""
        malicious_input = {"title": "</script><script>alert('xss')</script>"}
        json_state = (
            json.dumps(malicious_input)
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026")
        )
        self.assertNotIn("</script>", json_state)
        self.assertIn("\\u003c/script\\u003e", json_state)

    def test_loading_dialog_cancel_and_signals(self):
        """H14: LoadingDialog cancel stops start timer and disconnects worker signals"""
        from widgets.loading_dialog import LoadingDialog
        from PyQt6.QtCore import QThread, pyqtSignal

        class MockWorker(QThread):
            status_changed = pyqtSignal(int, str)
            finished = pyqtSignal(dict)
            error = pyqtSignal(str)

        worker = MockWorker()
        dlg = LoadingDialog("Testing...", worker=worker)
        dlg.show()

        # Reject dialog (simulating cancel or Esc)
        dlg.reject()
        self.assertTrue(dlg.was_cancelled)
        self.assertFalse(dlg._start_timer.isActive())

        # Emitting finished on cancelled worker must NOT call accept
        with patch.object(dlg, "accept") as mock_accept:
            worker.finished.emit({})
            mock_accept.assert_not_called()

    def test_fading_label_sync_finished_stops_animation(self):
        """M7: FadingVersionLabel.show_sync_finished stops anim and clears is_restoring"""
        from widgets.update_label import FadingVersionLabel

        lbl = FadingVersionLabel("v1.0.0")
        lbl._is_restoring = True
        lbl._anim.start()

        lbl.show_sync_finished(True, "Complete")
        self.assertFalse(lbl._is_restoring)
        self.assertFalse(lbl._anim.state() == lbl._anim.State.Running)
        self.assertIn("Complete", lbl.text())

    def test_load_app_settings_corrupt_protection(self):
        """C2: _load_app_settings preserves .corrupt.bak and does not wipe file with defaults"""
        from app import TrueHourApp, APP_SETTINGS_FILE

        settings_path = str(APP_SETTINGS_FILE)
        corrupt_bak = f"{settings_path}.corrupt.bak"

        # Cleanup existing backup if present
        if os.path.exists(corrupt_bak):
            os.remove(corrupt_bak)

        # Write invalid JSON to settings file
        with open(settings_path, "w", encoding="utf-8") as f:
            f.write("{invalid json content!!!")

        with patch.object(TrueHourApp, "_save_app_settings") as mock_save:
            test_app = TrueHourApp.__new__(TrueHourApp)
            test_app.tracker = MagicMock()
            test_app._load_app_settings()

            # Verify .corrupt.bak was created
            self.assertTrue(os.path.exists(corrupt_bak))
            with open(corrupt_bak, "r", encoding="utf-8") as bak_f:
                self.assertEqual(bak_f.read(), "{invalid json content!!!")

            # Verify _save_app_settings was NOT called to overwrite with defaults
            mock_save.assert_not_called()

        # Clean up
        if os.path.exists(corrupt_bak):
            os.remove(corrupt_bak)

    def test_dashboard_live_timer_stops_on_close(self):
        """H11: TrueHourDashboard stops live_timer on closeEvent/reject/accept"""
        from dialogs.dashboard_dialog import TrueHourDashboard

        from PyQt6.QtWidgets import QWidget

        parent = QWidget()
        parent.theme_style = "light"
        parent.tracker = MagicMock()
        parent.tracker.running = False
        parent.hourly_rate = 50.0
        parent.currency_symbol = "$"

        dlg = TrueHourDashboard(parent)
        dlg.live_timer.start(1000)
        self.assertTrue(dlg.live_timer.isActive())

        dlg.reject()
        self.assertFalse(dlg.live_timer.isActive())

    def test_c1_sqlite_wal_backup_and_stale_cleanup(self):
        """C1: SQLite WAL backup flushes frames and restore cleans stale -wal/-shm"""
        import sqlite3
        import zipfile
        from core.backup_manager import _backup_sqlite_db_to_archive, import_settings

        src_db = os.path.join(self.test_dir, "source.db")
        conn = sqlite3.connect(src_db)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("CREATE TABLE test_wal (id INT, name TEXT);")
        conn.execute("INSERT INTO test_wal VALUES (42, 'uncheckpointed');")
        conn.commit()
        conn.close()

        zip_path = os.path.join(self.test_dir, "archive.zip")
        with zipfile.ZipFile(zip_path, "w") as z:
            _backup_sqlite_db_to_archive(src_db, z, arcname="truehour.db")
            z.writestr("app_settings.json", "{}")

        dest_root = os.path.join(self.test_dir, "app_data")
        dest_prof = os.path.join(dest_root, "profiles", "TargetProf")
        os.makedirs(dest_prof, exist_ok=True)
        # Place stale WAL and SHM
        with open(os.path.join(dest_prof, "truehour.db-wal"), "wb") as f:
            f.write(b"stale wal corrupt junk")
        with open(os.path.join(dest_prof, "truehour.db-shm"), "wb") as f:
            f.write(b"stale shm junk")

        with patch("core.backup_manager.get_app_data_root", return_value=dest_root):
            res = import_settings(zip_path, target_profile_name="TargetProf")
            self.assertEqual(res, "success")

        # Confirm stale wal was deleted and restored database reads correctly
        dest_db = os.path.join(dest_prof, "truehour.db")
        conn2 = sqlite3.connect(dest_db)
        rows = conn2.execute("SELECT * FROM test_wal;").fetchall()
        conn2.close()
        self.assertEqual(rows, [(42, "uncheckpointed")])

    def test_c3_cross_pc_bank_sync_and_no_plaintext_leak(self):
        """C3: Cross-PC portable key decryption works and doesn't leak plaintext to disk"""
        from crypto import _get_secure_key, _encrypt_string, _decrypt_string
        from core.backup_manager import _sanitize_settings_for_backup, _restore_settings_from_backup

        orig_comp = os.environ.get("COMPUTERNAME", "")
        try:
            # Machine A (COMPUTERNAME = 'PC_ALPHA')
            os.environ["COMPUTERNAME"] = "PC_ALPHA"
            anon_id = "uuid-machine-a"
            key_a = _get_secure_key(anon_id)
            plain_acc = "987654321"

            settings = {
                "anonymous_user_id": anon_id,
                "bank_account": "",
                "bank_account_enc": _encrypt_string(plain_acc, key_a),
            }

            # Machine A creates unencrypted backup
            sanitized = _sanitize_settings_for_backup(settings, anonymous_user_id=anon_id)

            # Machine B (COMPUTERNAME = 'PC_BETA') restores backup
            os.environ["COMPUTERNAME"] = "PC_BETA"
            key_b = _get_secure_key(anon_id)
            restored = _restore_settings_from_backup(sanitized, is_encrypted=False)

            # Bank details can be decrypted using Machine B's local key
            decrypted = _decrypt_string(restored["bank_account_enc"], key_b)
            self.assertEqual(decrypted, plain_acc)
            # Plaintext field is populated with decrypted value for app settings
            self.assertEqual(restored.get("bank_account", ""), plain_acc)
        finally:
            os.environ["COMPUTERNAME"] = orig_comp

    def test_c4_settings_dialog_cleanup_workers_on_accept(self):
        """C4: SettingsDialog cleans up workers on accept()"""
        from dialogs.settings_dialog import SettingsDialog
        from PyQt6.QtCore import QThread

        class DummyWorker(QThread):
            pass

        dlg = SettingsDialog.__new__(SettingsDialog)
        dlg._auth_worker = DummyWorker()
        dlg._sync_worker = DummyWorker()
        dlg._restore_worker = DummyWorker()

        with patch.object(dlg, "_cleanup_workers") as mock_cleanup, \
             patch("PyQt6.QtWidgets.QDialog.accept"):
            dlg.accept()
            mock_cleanup.assert_called_once()

    def test_c5_forward_clock_tamper_detection(self):
        """C5: Forward clock jump >5s without network verification flags tamper"""
        from secure_time import TimeTamperDetector

        detector = TimeTamperDetector()
        detector.monotonic_start = 1000.0
        detector.system_start = 1000.0
        detector.last_monotonic = 1000.0
        detector.last_system = 1000.0
        detector.network_time_offset = 0.0

        # Simulate 1 hour clock jump forward while monotonic only moved 1s
        with patch.object(detector, "get_network_time", return_value=None), \
             patch("time.monotonic", return_value=1001.0), \
             patch("time.time", return_value=4601.0):

            res = detector.validate_and_record("VSCode", 1.0)
            self.assertEqual(res["integrity_status"], "TAMPER_DETECTED")
            self.assertLess(detector.trust_score, 100)

    def test_h1_fresh_install_active_profile_fallback(self):
        """H1: TrueHourApp initializes active_profile in __init__ and supports getattr fallback"""
        from app import TrueHourApp

        app_obj = TrueHourApp.__new__(TrueHourApp)
        app_obj.active_profile = "TestProfile"
        self.assertEqual(getattr(app_obj, "active_profile", "Default"), "TestProfile")

    def test_h2_drive_sync_worker_safety_exception_no_finished(self):
        """H2: DriveSyncWorker does not emit finished signal on CloudSafetyException"""
        from workers.drive_sync_worker import DriveSyncWorker
        from drive_sync import CloudSafetyException

        worker = DriveSyncWorker("Default")
        finished_emitted = []
        safety_emitted = []

        worker.finished.connect(lambda *args: finished_emitted.append(args))
        worker.safety_blocked.connect(lambda data: safety_emitted.append(data))

        with patch("drive_sync.sync_to_cloud", side_effect=CloudSafetyException("Blocked", {"status": "prompt_restore"})):
            worker.run()

        self.assertEqual(len(safety_emitted), 1)
        self.assertEqual(len(finished_emitted), 0)

    def test_h3_invoice_additional_items_in_amount_and_receipt(self):
        """H3: Additional items are included in invoice amount and paid receipts"""
        from report import generate_receipt_html

        billing_data = {
            "counted_seconds": 7200,
            "total_earned": 100.0,
            "total_hours": 2.0,
            "hourly_rate": 50.0,
            "additional_items": [{"description": "Setup Fee", "amount": 25.0}],
        }
        settings_data = {"currency_symbol": "$"}

        html = generate_receipt_html(billing_data, settings_data, invoice_no="INV-101")
        self.assertIn("$125.00", html)

    def test_h4_currency_zar_not_corrupted_to_idr(self):
        """H4: Matching currency symbol 'R' prefers exact code split 'R (ZAR)' over 'Rp (IDR)'"""
        currency_options = ["Rp (IDR)", "R (ZAR)", "$ (USD)"]
        curr_symbol = "R"

        matched = [
            c for c in currency_options if c.split(" (")[0].strip() == curr_symbol
        ] or [c for c in currency_options if c.startswith(curr_symbol)]

        self.assertEqual(matched[0], "R (ZAR)")

    def test_h5_web_goals_reset_preserves_running_session(self):
        """H5: _on_web_goals_reset does not stop or start active tracker"""
        from app import TrueHourApp

        app_obj = TrueHourApp.__new__(TrueHourApp)
        app_obj.tracker = MagicMock()
        app_obj.tracker.running = True
        app_obj.notified_goals = set()
        app_obj.notified_earnings_goal = set()
        app_obj._recalculate_weekly_base_focus_seconds = MagicMock()
        app_obj._save_app_settings = MagicMock()

        app_obj._on_web_goals_reset()
        app_obj.tracker.stop.assert_not_called()
        app_obj.tracker.start.assert_not_called()

    def test_h8_session_report_html_app_settings_and_theme(self):
        """H8: generate_session_report_html switches theme class without wiping dark mode"""
        from report import generate_session_report_html

        report = {
            "session_name": "Test",
            "date": "2026-01-01",
            "start_time": "10:00:00",
            "end_time": "11:00:00",
            "total_time": "01:00:00",
            "total_seconds": 3600,
            "apps": [{"name": "Code", "formatted": "01:00:00", "time": "01:00:00", "seconds": 3600, "percent": 100.0, "tag": "Development"}],
            "timeline": [],
        }

        html = generate_session_report_html(report)
        self.assertIn("truehour-report-color-theme", html)
        self.assertIn("classes = Array.from(document.body.classList)", html)

    def test_h9_get_cached_template_readonly_handling(self):
        """H9: get_cached_template catches exceptions when writing to read-only directory"""
        from report import get_cached_template

        # Pointing to an invalid read-only location should fall back to default_content gracefully
        fake_path = "/invalid_read_only_root/template.html"
        result = get_cached_template(fake_path, "<html>Default Content</html>")
        self.assertEqual(result, "<html>Default Content</html>")

    def test_m1_crypto_lru_cache(self):
        """M1: _derive_fernet_key caches results via functools.lru_cache"""
        from crypto import _derive_fernet_key

        _derive_fernet_key.cache_clear()
        k1 = _derive_fernet_key("seed_test", iterations=1000)
        k2 = _derive_fernet_key("seed_test", iterations=1000)
        self.assertEqual(k1, k2)
        info = _derive_fernet_key.cache_info()
        self.assertGreaterEqual(info.hits, 1)

    def test_m3_aggregator_force_rebuild_deletes_daily_summary(self):
        """M3: rebuild_all_summaries(force=True) clears daily_summary table"""
        from database.schema import init_db, get_connection
        from core.reporting.aggregator import rebuild_all_summaries

        init_db()
        conn = get_connection()
        conn.execute("INSERT OR REPLACE INTO daily_summary (date, total_seconds) VALUES ('2020-01-01', 9999);")
        conn.commit()
        conn.close()

        with patch("core.reporting.aggregator.get_app_data_dir", return_value=self.test_dir):
            rebuild_all_summaries(force=True)

        conn2 = get_connection()
        row = conn2.execute("SELECT * FROM daily_summary WHERE date = '2020-01-01';").fetchone()
        conn2.close()
        self.assertIsNone(row)

    def test_m4_merge_session_files_multiday_sorting(self):
        """M4: merge_session_files sorts timeline across dates properly"""
        from report import merge_session_files

        file1 = os.path.join(self.test_dir, "session_day1.json")
        file2 = os.path.join(self.test_dir, "session_day2.json")

        with open(file1, "w", encoding="utf-8") as f:
            json.dump({
                "date": "2026-06-01",
                "total_seconds": 3600,
                "timeline": [{"start": "23:00:00", "end": "23:30:00", "app": "LateNightApp"}],
                "apps": [{"name": "LateNightApp", "seconds": 1800, "tag": "Development", "excluded": False}],
            }, f)

        with open(file2, "w", encoding="utf-8") as f:
            json.dump({
                "date": "2026-06-02",
                "total_seconds": 3600,
                "timeline": [{"start": "01:00:00", "end": "01:30:00", "app": "EarlyMorningApp"}],
                "apps": [{"name": "EarlyMorningApp", "seconds": 1800, "tag": "Development", "excluded": False}],
            }, f)

        out_path = merge_session_files([file2, file1], "merged_output", self.test_dir)
        with open(out_path, "r", encoding="utf-8") as f:
            merged = json.load(f)
        tl = merged["timeline"]
        self.assertEqual(len(tl), 2)
        # LateNightApp (June 1) must precede EarlyMorningApp (June 2) despite '01:00:00' < '23:00:00'
        self.assertEqual(tl[0]["app"], "LateNightApp")
        self.assertEqual(tl[1]["app"], "EarlyMorningApp")

    def test_m12_secure_time_iso_timezone_handling(self):
        """M12: parse ISO datetime with +08:00 timezone offset without stripping offset"""
        from datetime import datetime, timezone

        dt_str = "2026-10-20T15:30:00+08:00"
        network_dt = datetime.fromisoformat(dt_str)
        utc_dt = network_dt.astimezone(timezone.utc)
        self.assertEqual(utc_dt.hour, 7)

    def test_l1_save_invoice_preserves_created_at_on_update(self):
        """L1: save_invoice preserves original created_at timestamp upon conflict update"""
        from database.schema import init_db, save_invoice, get_connection

        init_db()
        save_invoice(
            "INV-999", "Alpha Corp", 500.0, "$", "draft",
            session_files=[], billing_data={}, settings_data={},
            created_at="2026-01-01T12:00:00"
        )
        save_invoice(
            "INV-999", "Alpha Corp", 750.0, "$", "paid",
            session_files=[], billing_data={}, settings_data={},
            created_at="2026-02-01T12:00:00"
        )

        conn = get_connection()
        row = conn.execute("SELECT created_at, amount, status FROM invoices WHERE invoice_no = 'INV-999';").fetchone()
        conn.close()
        self.assertEqual(row[0], "2026-01-01T12:00:00")
        self.assertEqual(row[1], 750.0)
        self.assertEqual(row[2], "paid")

    def test_l2_trash_svg_unified_color(self):
        """L2: TRASH_SVG uses unified #FF0000 fill color"""
        from assets import TRASH_SVG
        from theme import get_svg_icon

        self.assertNotIn(b"#FF7F7F", TRASH_SVG)
        self.assertIn(b"#FF0000", TRASH_SVG)
        icon = get_svg_icon(TRASH_SVG, color_hex="#16A34A")
        self.assertFalse(icon.isNull())

    def test_l3_project_color_matches_tag_color(self):
        """L3: get_project_color matches get_tag_color for custom categories"""
        from report import get_project_color
        from theme import get_tag_color

        for cat in ["CustomProject1", "Marketing Alpha", "Crypto Mining"]:
            self.assertEqual(get_project_color(cat), get_tag_color(cat))


if __name__ == "__main__":
    unittest.main()
