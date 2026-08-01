import os
import json
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime
from report import merge_session_files, save_to_history, build_report_data, merge_sessions_for_invoice
from tracker import AppTracker

class TestMergeSessions(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = self.temp_dir.name

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_merge_session_files(self):
        sess1 = {
            "session_name": "Session 1",
            "date": "2026-07-28",
            "start": "09:00:00",
            "end": "10:00:00",
            "total_seconds": 3600,
            "counted_seconds": 3600,
            "apps": [
                {"name": "VSCode", "seconds": 2000, "tag": "Development", "excluded": False},
                {"name": "Chrome", "seconds": 1600, "tag": "Research", "excluded": False},
            ],
            "app_exe_paths": {"VSCode": "C:\\VSCode.exe"},
            "timeline": [{"app": "VSCode", "start": "09:00:00", "end": "09:33:20"}],
            "new_activity": ["Started working"],
            "hourly_rate": 50.0,
            "currency_symbol": "$",
        }

        sess2 = {
            "session_name": "Session 2",
            "date": "2026-07-28",
            "start": "11:00:00",
            "end": "12:00:00",
            "total_seconds": 3600,
            "counted_seconds": 3600,
            "apps": [
                {"name": "VSCode", "seconds": 1600, "tag": "Development", "excluded": False},
                {"name": "Slack", "seconds": 2000, "tag": "Communication", "excluded": False},
            ],
            "app_exe_paths": {"Slack": "C:\\Slack.exe"},
            "timeline": [{"app": "Slack", "start": "11:00:00", "end": "11:33:20"}],
            "new_activity": ["Finished task"],
            "hourly_rate": 50.0,
            "currency_symbol": "$",
        }

        p1 = os.path.join(self.dir_path, "session_1.json")
        p2 = os.path.join(self.dir_path, "session_2.json")
        with open(p1, "w", encoding="utf-8") as f:
            json.dump(sess1, f)
        with open(p2, "w", encoding="utf-8") as f:
            json.dump(sess2, f)

        out_dir = os.path.join(self.dir_path, "out")
        merged_path = merge_session_files([p1, p2], "Combined Session", out_dir)

        self.assertTrue(os.path.exists(merged_path))
        with open(merged_path, "r", encoding="utf-8") as f:
            res = json.load(f)

        self.assertEqual(res["session_name"], "Combined Session")
        self.assertEqual(res["total_seconds"], 7200)
        self.assertEqual(res["counted_seconds"], 7200)
        self.assertEqual(res["start"], "09:00:00")
        self.assertEqual(res["end"], "12:00:00")
        self.assertEqual(len(res["apps"]), 3)

        vscode_app = next(a for a in res["apps"] if a["name"] == "VSCode")
        self.assertEqual(vscode_app["seconds"], 3600)
        self.assertEqual(res["total_earned"], 100.0)

    def test_single_session_merge_and_invoice(self):
        sess = {
            "session_name": "Single Session",
            "total_seconds": 1800,
            "counted_seconds": 1800,
            "apps": [{"name": "VSCode", "seconds": 1800, "tag": "Development", "excluded": False}],
        }
        p1 = os.path.join(self.dir_path, "single.json")
        with open(p1, "w", encoding="utf-8") as f:
            json.dump(sess, f)

        out_dir = os.path.join(self.dir_path, "out")
        with self.assertRaises(ValueError):
            merge_session_files([p1], "Single Merged Session", out_dir)

        mock_tracker = MagicMock()
        mock_tracker.get_app_tag.return_value = "Development"
        billing_data = merge_sessions_for_invoice([p1], mock_tracker, hourly_rate=50.0)
        self.assertEqual(billing_data["counted_seconds"], 1800)
        self.assertEqual(len(billing_data["project_breakdown"]), 1)

    @patch("report.get_app_data_dir")
    def test_resumed_session_in_place_save(self, mock_get_app_data_dir):
        mock_get_app_data_dir.return_value = self.dir_path
        sessions_folder = os.path.join(self.dir_path, "sessions")
        os.makedirs(sessions_folder, exist_ok=True)

        sess_data = {
            "session_name": "Merged Session",
            "date": "2026-07-28",
            "start": "09:00:00",
            "end": "10:00:00",
            "total_seconds": 3600,
            "counted_seconds": 3600,
            "apps": [{"name": "VSCode", "seconds": 3600, "tag": "Development", "excluded": False}],
            "app_exe_paths": {},
            "timeline": [],
            "new_activity": [],
            "hourly_rate": 0.0,
            "currency_symbol": "$",
        }
        initial_file = os.path.join(sessions_folder, "session_20260728_180000.json")
        with open(initial_file, "w", encoding="utf-8") as f:
            json.dump(sess_data, f)

        tracker = AppTracker()
        tracker.load_from_report(initial_file)

        self.assertEqual(tracker.resumed_filepath, initial_file)

        rep = build_report_data(tracker)
        rep["session_name"] = "Merged Session Updated"

        saved_file = save_to_history(rep)

        self.assertEqual(saved_file, initial_file)
        self.assertEqual(len(os.listdir(sessions_folder)), 1)

        with open(saved_file, "r", encoding="utf-8") as f:
            updated_data = json.load(f)
        self.assertEqual(updated_data["session_name"], "Merged Session Updated")

if __name__ == "__main__":
    unittest.main()
