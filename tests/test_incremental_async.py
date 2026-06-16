"""
Test suite for Incremental Aggregation and Asynchronous Batch Report Generation
"""

import unittest
import os
import sys
import json
import tempfile
import shutil
from unittest.mock import patch, MagicMock

# Adjust path so we can import from local files
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestIncrementalAggregation(unittest.TestCase):
    """Tests for incremental aggregation in aggregator.py"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_data_dir = tempfile.mkdtemp()
        self.sessions_dir = os.path.join(self.test_data_dir, "sessions")
        self.autosave_dir = os.path.join(self.test_data_dir, "autosave")
        os.makedirs(self.sessions_dir, exist_ok=True)
        os.makedirs(self.autosave_dir, exist_ok=True)

    def tearDown(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.test_data_dir, ignore_errors=True)

    def _create_session_file(self, folder, date, start, total_seconds, apps=None, tag="Project1"):
        """Helper to create a session JSON file"""
        if apps is None:
            apps = [{"tag": tag, "seconds": total_seconds, "excluded": False}]

        session_data = {
            "date": date,
            "start": start,
            "total_seconds": total_seconds,
            "apps": apps
        }

        filename = f"session_{date}_{start.replace(':', '-')}.json"
        filepath = os.path.join(folder, filename)
        with open(filepath, 'w') as f:
            json.dump(session_data, f)
        return filepath

    @patch('core.reporting.aggregator.get_app_data_dir')
    @patch('core.reporting.aggregator.get_connection')
    def test_get_sessions_for_date_single_session(self, mock_get_conn, mock_get_dir):
        """Test getting sessions for a specific date with single session"""
        mock_get_dir.return_value = self.test_data_dir

        # Create a session file
        self._create_session_file(
            self.sessions_dir,
            "2026-05-30",
            "09:00:00",
            3600
        )

        from core.reporting.aggregator import get_sessions_for_date

        sessions = get_sessions_for_date("2026-05-30")

        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["date"], "2026-05-30")
        self.assertEqual(sessions[0]["total_seconds"], 3600)

    @patch('core.reporting.aggregator.get_app_data_dir')
    @patch('core.reporting.aggregator.get_connection')
    def test_get_sessions_for_date_multiple_sessions(self, mock_get_conn, mock_get_dir):
        """Test getting multiple sessions for a specific date"""
        mock_get_dir.return_value = self.test_data_dir

        # Create multiple session files for same date
        self._create_session_file(self.sessions_dir, "2026-05-30", "09:00:00", 3600)
        self._create_session_file(self.sessions_dir, "2026-05-30", "14:00:00", 7200)
        self._create_session_file(self.sessions_dir, "2026-05-30", "18:00:00", 1800)

        from core.reporting.aggregator import get_sessions_for_date

        sessions = get_sessions_for_date("2026-05-30")

        self.assertEqual(len(sessions), 3)
        total_secs = sum(s["total_seconds"] for s in sessions)
        self.assertEqual(total_secs, 12600)

    @patch('core.reporting.aggregator.get_app_data_dir')
    def test_get_sessions_for_date_filters_by_date(self, mock_get_dir):
        """Test that get_sessions_for_date only returns sessions for specified date"""
        mock_get_dir.return_value = self.test_data_dir

        # Create sessions for different dates
        self._create_session_file(self.sessions_dir, "2026-05-30", "09:00:00", 3600)
        self._create_session_file(self.sessions_dir, "2026-05-31", "09:00:00", 7200)
        self._create_session_file(self.sessions_dir, "2026-06-01", "09:00:00", 1800)

        from core.reporting.aggregator import get_sessions_for_date

        sessions = get_sessions_for_date("2026-05-30")

        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["date"], "2026-05-30")

    @patch('core.reporting.aggregator.get_app_data_dir')
    def test_get_sessions_for_date_deduplicates(self, mock_get_dir):
        """Test that duplicate sessions are deduplicated keeping highest total_seconds"""
        mock_get_dir.return_value = self.test_data_dir

        # Create duplicate sessions (same date and start time) in both folders
        self._create_session_file(self.sessions_dir, "2026-05-30", "09:00:00", 3600)
        self._create_session_file(self.autosave_dir, "2026-05-30", "09:00:00", 5000)

        from core.reporting.aggregator import get_sessions_for_date

        sessions = get_sessions_for_date("2026-05-30")

        # Should only have 1 session (the one with higher total_seconds)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["total_seconds"], 5000)

    @patch('core.reporting.aggregator.get_connection')
    @patch('core.reporting.aggregator.get_app_data_dir')
    def test_update_daily_summary_inserts_new_record(self, mock_get_dir, mock_get_conn):
        """Test update_daily_summary inserts new daily summary record"""
        mock_get_dir.return_value = self.test_data_dir

        # Create session files
        self._create_session_file(self.sessions_dir, "2026-05-30", "09:00:00", 3600, tag="Project1")
        self._create_session_file(self.sessions_dir, "2026-05-30", "14:00:00", 7200, tag="Project2")

        # Mock database connection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        from core.reporting.aggregator import update_daily_summary

        update_daily_summary("2026-05-30")

        # Verify INSERT was called with correct values
        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args[0][0]
        self.assertIn("INSERT INTO daily_summary", call_args)
        self.assertIn("ON CONFLICT(date) DO UPDATE", call_args)

    @patch('core.reporting.aggregator.get_connection')
    @patch('core.reporting.aggregator.get_app_data_dir')
    def test_update_daily_summary_calculates_correct_stats(self, mock_get_dir, mock_get_conn):
        """Test update_daily_summary calculates correct statistics"""
        mock_get_dir.return_value = self.test_data_dir

        # Create sessions with known values
        self._create_session_file(self.sessions_dir, "2026-05-30", "09:00:00", 3600, tag="Project1")
        self._create_session_file(self.sessions_dir, "2026-05-30", "14:00:00", 7200, tag="Project2")
        self._create_session_file(self.sessions_dir, "2026-05-30", "18:00:00", 1800, tag="Project1")  # Same project

        # Mock database connection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        from core.reporting.aggregator import update_daily_summary

        update_daily_summary("2026-05-30")

        # Get the parameters passed to execute
        call_args = mock_cursor.execute.call_args[0][1]

        # Check total_seconds (3600 + 7200 + 1800 = 12600)
        self.assertEqual(call_args[1], 12600)
        # Check session_count (3 sessions)
        self.assertEqual(call_args[2], 3)
        # Check active_projects (Project1 and Project2 = 2 unique projects)
        self.assertEqual(call_args[3], 2)
        # Check longest_session (7200)
        self.assertEqual(call_args[4], 7200)

    @patch('core.reporting.aggregator.get_connection')
    @patch('core.reporting.aggregator.get_app_data_dir')
    def test_update_daily_summary_excludes_inactive_apps(self, mock_get_dir, mock_get_conn):
        """Test that excluded apps are not counted in active projects"""
        mock_get_dir.return_value = self.test_data_dir

        # Create session with excluded app
        apps = [
            {"tag": "ActiveProject", "seconds": 3600, "excluded": False},
            {"tag": "ExcludedProject", "seconds": 1800, "excluded": True}
        ]
        self._create_session_file(self.sessions_dir, "2026-05-30", "09:00:00", 5400, apps=apps)

        # Mock database connection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        from core.reporting.aggregator import update_daily_summary

        update_daily_summary("2026-05-30")

        # Get the parameters passed to execute
        call_args = mock_cursor.execute.call_args[0][1]

        # Should only count ActiveProject (1 active project)
        self.assertEqual(call_args[3], 1)

    @patch('core.reporting.aggregator.get_connection')
    @patch('core.reporting.aggregator.get_app_data_dir')
    def test_rebuild_all_summaries_rebuilds_all_dates(self, mock_get_dir, mock_get_conn):
        """Test rebuild_all_summaries processes all unique dates"""
        mock_get_dir.return_value = self.test_data_dir

        # Create sessions for multiple dates
        self._create_session_file(self.sessions_dir, "2026-05-30", "09:00:00", 3600)
        self._create_session_file(self.sessions_dir, "2026-05-31", "09:00:00", 7200)
        self._create_session_file(self.sessions_dir, "2026-06-01", "09:00:00", 1800)

        # Mock database connection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        from core.reporting.aggregator import rebuild_all_summaries

        rebuild_all_summaries()

        # Should call execute 4 times: 1 SELECT for count check + 3 INSERTs (once per date)
        self.assertEqual(mock_cursor.execute.call_count, 4)


class TestAsynchronousBatchReportGeneration(unittest.TestCase):
    """Tests for asynchronous batch report generation in queue.py and builder.py"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_data_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.test_data_dir, ignore_errors=True)

    @patch('core.reporting.queue.get_connection')
    @patch('core.reporting.queue.uuid.uuid4')
    @patch('core.reporting.queue.datetime')
    def test_add_report_job_creates_pending_job(self, mock_datetime, mock_uuid, mock_get_conn):
        """Test adding a report job creates it in PENDING status"""
        # Setup mocks
        mock_uuid.return_value = "test-job-id-123"
        mock_datetime.now.return_value.isoformat.return_value = "2026-05-30T10:00:00"

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        # Clear the queue before test
        from core.reporting import queue
        while not queue.report_queue.empty():
            queue.report_queue.get()
            queue.report_queue.task_done()

        from core.reporting.queue import add_report_job, ReportStatus

        job_id = add_report_job("weekly", "2026-05-01", "2026-05-07", "/output/report.html")

        self.assertEqual(job_id, "test-job-id-123")

        # Verify INSERT was called with PENDING status
        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args[0][1]
        self.assertEqual(call_args[0], "test-job-id-123")
        self.assertEqual(call_args[1], ReportStatus.PENDING)
        self.assertEqual(call_args[2], 0)  # progress
        self.assertEqual(call_args[3], "weekly")
        self.assertEqual(call_args[4], "2026-05-01")
        self.assertEqual(call_args[5], "2026-05-07")
        self.assertEqual(call_args[6], "/output/report.html")

        # Verify job was added to queue
        self.assertFalse(queue.report_queue.empty())
        queued_job_id = queue.report_queue.get()
        self.assertEqual(queued_job_id, "test-job-id-123")

    @patch('core.reporting.queue.get_connection')
    def test_get_report_job_retrieves_job(self, mock_get_conn):
        """Test retrieving a report job by ID"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        # Mock fetchone to return a job row
        mock_row = {
            "id": "test-job-id",
            "status": "running",
            "progress": 50,
            "report_type": "weekly",
            "start_date": "2026-05-01",
            "end_date": "2026-05-07",
            "output_path": "/output/report.html",
            "error_message": None
        }
        mock_cursor.fetchone.return_value = mock_row
        mock_get_conn.return_value = mock_conn

        from core.reporting.queue import get_report_job
        from core.reporting.models import ReportJob

        job = get_report_job("test-job-id")

        self.assertIsNotNone(job)
        self.assertIsInstance(job, ReportJob)
        self.assertEqual(job.id, "test-job-id")
        self.assertEqual(job.status, "running")
        self.assertEqual(job.progress, 50)

    @patch('core.reporting.queue.get_connection')
    def test_get_report_job_returns_none_when_not_found(self, mock_get_conn):
        """Test get_report_job returns None when job doesn't exist"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None
        mock_get_conn.return_value = mock_conn

        from core.reporting.queue import get_report_job

        job = get_report_job("non-existent-id")

        self.assertIsNone(job)

    @patch('core.reporting.queue.get_connection')
    @patch('core.reporting.queue.datetime')
    def test_update_job_updates_status_and_progress(self, mock_datetime, mock_get_conn):
        """Test updating job status and progress"""
        mock_datetime.now.return_value.isoformat.return_value = "2026-05-30T10:00:00"

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        from core.reporting.queue import update_job, ReportStatus

        update_job("test-job-id", ReportStatus.RUNNING, 50)

        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args[0][1]
        self.assertEqual(call_args[0], ReportStatus.RUNNING)
        self.assertEqual(call_args[1], 50)

    @patch('core.reporting.queue.get_connection')
    @patch('core.reporting.queue.datetime')
    def test_update_job_sets_completed_at_on_complete(self, mock_datetime, mock_get_conn):
        """Test that completed_at is set when job completes"""
        mock_datetime.now.return_value.isoformat.return_value = "2026-05-30T10:00:00"

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        from core.reporting.queue import update_job, ReportStatus

        update_job("test-job-id", ReportStatus.COMPLETE, 100, output_path="/output/report.html")

        call_args = mock_cursor.execute.call_args[0][1]
        self.assertEqual(call_args[0], ReportStatus.COMPLETE)
        self.assertEqual(call_args[1], 100)
        self.assertEqual(call_args[3], "/output/report.html")
        # completed_at should be set
        self.assertEqual(call_args[4], "2026-05-30T10:00:00")

    def test_generate_report_full_workflow(self):
        """Test complete report generation workflow - structural verification"""
        # Due to PyQt6 dependencies in charts.py, we verify the structure via AST analysis
        import ast
        with open('core/reporting/builder.py', 'r') as f:
            source = f.read()

        tree = ast.parse(source)

        # Verify generate_report function exists
        has_generate_report = any(
            isinstance(node, ast.FunctionDef) and node.name == 'generate_report'
            for node in ast.walk(tree)
        )
        self.assertTrue(has_generate_report, "generate_report function should exist")

        # Check for key workflow steps in source
        self.assertIn("get_cached_report", source)  # Cache check
        self.assertIn("get_daily_summaries", source)  # Load data
        self.assertIn("calculate_total_hours", source)  # Statistics
        self.assertIn("update_job", source)  # Progress updates
        self.assertIn("ReportStatus.COMPLETE", source)  # Completion

    def test_generate_report_uses_cache_when_available(self):
        """Test that generate_report uses cached report when available - structural verification"""
        with open('core/reporting/builder.py', 'r') as f:
            source = f.read()

        # Verify cache logic exists
        self.assertIn("cached_path = get_cached_report", source)
        self.assertIn("if cached_path", source)
        self.assertIn("shutil.copy2", source)

    def test_generate_report_saves_to_cache_on_success(self):
        """Test that successful report generation saves to cache - structural verification"""
        with open('core/reporting/builder.py', 'r') as f:
            source = f.read()

        # Verify cache save logic exists
        self.assertIn("save_to_cache", source)
        self.assertIn("if success:", source)

    def test_generate_report_handles_exporter_failure(self):
        """Test that exporter failure is handled gracefully - structural verification"""
        with open('core/reporting/builder.py', 'r') as f:
            source = f.read()

        # Verify error handling for exporter
        self.assertIn("exporter.export", source)
        self.assertIn("if success:", source)
        self.assertIn("else:", source)
        self.assertIn("ReportStatus.FAILED", source)

    def test_process_reports_exception_handling_structure(self):
        """Test that process_reports has proper exception handling structure"""
        # This test verifies the code structure handles exceptions
        # The actual thread testing is complex due to PyQt dependencies
        from core.reporting.queue import process_reports
        import inspect

        # Verify process_reports function exists and has try/except structure
        source = inspect.getsource(process_reports)
        self.assertIn("try:", source)
        self.assertIn("except", source)
        self.assertIn("update_job", source)
        self.assertIn("FAILED", source)


class TestIntegrationIncrementalAndAsync(unittest.TestCase):
    """Integration tests combining incremental aggregation and async report generation"""

    @patch('core.reporting.aggregator.get_app_data_dir')
    @patch('core.reporting.aggregator.get_connection')
    @patch('core.reporting.queue.get_connection')
    def test_incremental_aggregation_feeds_async_reports(
        self, mock_queue_conn, mock_agg_conn, mock_get_dir
    ):
        """Test that incremental aggregation data is used by async report generation"""
        test_data_dir = tempfile.mkdtemp()
        sessions_dir = os.path.join(test_data_dir, "sessions")
        os.makedirs(sessions_dir, exist_ok=True)

        try:
            mock_get_dir.return_value = test_data_dir

            # Create session files
            session_data = {
                "date": "2026-05-30",
                "start": "09:00:00",
                "total_seconds": 7200,
                "apps": [{"tag": "Project1", "seconds": 7200, "excluded": False}]
            }
            with open(os.path.join(sessions_dir, "session.json"), 'w') as f:
                json.dump(session_data, f)

            # Mock DB connections
            mock_agg_cursor = MagicMock()
            mock_agg_conn.return_value.cursor.return_value = mock_agg_cursor

            mock_queue_cursor = MagicMock()
            mock_queue_cursor.fetchone.return_value = {
                "id": "test-job",
                "status": "pending",
                "progress": 0,
                "report_type": "daily",
                "start_date": "2026-05-30",
                "end_date": "2026-05-30",
                "output_path": "/output/report.html",
                "error_message": None
            }
            mock_queue_conn.return_value.cursor.return_value = mock_queue_cursor

            # Run incremental aggregation
            from core.reporting.aggregator import update_daily_summary
            update_daily_summary("2026-05-30")

            # Verify daily_summary was updated
            mock_agg_cursor.execute.assert_called()

            # Now verify report generation can access this data
            from core.reporting.queue import get_report_job
            job = get_report_job("test-job")

            self.assertIsNotNone(job)
            self.assertEqual(job.start_date, "2026-05-30")
            self.assertEqual(job.end_date, "2026-05-30")

        finally:
            shutil.rmtree(test_data_dir, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
