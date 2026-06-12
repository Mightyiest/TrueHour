"""
Test suite for core/reporting module - Report generation, statistics, and caching
"""

import unittest
import os
import sys
import tempfile
import shutil
from unittest.mock import patch, MagicMock

# Adjust path so we can import from local files
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.reporting.models import ReportStatus, ReportJob
from core.reporting.cache import get_cache_dir, compute_cache_key, get_cached_report, save_to_cache
from core.reporting.statistics import (
    calculate_total_hours, 
    calculate_average_hours, 
    calculate_most_active_day, 
    calculate_longest_session
)


class TestReportStatus(unittest.TestCase):
    """Tests for ReportStatus constants"""

    def test_status_constants(self):
        """Test that status constants are defined correctly"""
        self.assertEqual(ReportStatus.PENDING, "pending")
        self.assertEqual(ReportStatus.RUNNING, "running")
        self.assertEqual(ReportStatus.COMPLETE, "complete")
        self.assertEqual(ReportStatus.FAILED, "failed")


class TestReportJob(unittest.TestCase):
    """Tests for ReportJob dataclass"""

    def test_create_report_job(self):
        """Test creating a ReportJob instance"""
        job = ReportJob(
            id="test-id-123",
            status=ReportStatus.PENDING,
            progress=0,
            report_type="weekly",
            start_date="2026-05-01",
            end_date="2026-05-07",
            output_path=None,
            error_message=None
        )
        
        self.assertEqual(job.id, "test-id-123")
        self.assertEqual(job.status, "pending")
        self.assertEqual(job.progress, 0)
        self.assertEqual(job.report_type, "weekly")
        self.assertEqual(job.start_date, "2026-05-01")
        self.assertEqual(job.end_date, "2026-05-07")
        self.assertIsNone(job.output_path)
        self.assertIsNone(job.error_message)

    def test_create_report_job_with_output_path(self):
        """Test creating a ReportJob with output path"""
        job = ReportJob(
            id="test-id-456",
            status=ReportStatus.COMPLETE,
            progress=100,
            report_type="monthly",
            start_date="2026-05-01",
            end_date="2026-05-31",
            output_path="/path/to/report.html",
            error_message=None
        )
        
        self.assertEqual(job.output_path, "/path/to/report.html")


class TestCacheFunctions(unittest.TestCase):
    """Tests for cache utility functions"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_cache_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.test_cache_dir, ignore_errors=True)

    @patch('core.reporting.cache.get_app_data_dir')
    def test_get_cache_dir_creates_directory(self, mock_get_dir):
        """Test that get_cache_dir creates the directory if it doesn't exist"""
        mock_get_dir.return_value = self.test_cache_dir
        
        cache_dir = get_cache_dir()
        
        self.assertTrue(os.path.exists(cache_dir))
        self.assertTrue(os.path.isdir(cache_dir))

    def test_compute_cache_key_generates_consistent_hash(self):
        """Test that compute_cache_key generates consistent hashes"""
        key1 = compute_cache_key("weekly", "2026-05-01", "2026-05-07", "html")
        key2 = compute_cache_key("weekly", "2026-05-01", "2026-05-07", "html")
        
        self.assertEqual(key1, key2)
        self.assertEqual(len(key1), 64)  # SHA256 hex length

    def test_compute_cache_key_different_inputs_different_keys(self):
        """Test that different inputs produce different keys"""
        key1 = compute_cache_key("weekly", "2026-05-01", "2026-05-07", "html")
        key2 = compute_cache_key("monthly", "2026-05-01", "2026-05-07", "html")
        key3 = compute_cache_key("weekly", "2026-06-01", "2026-06-30", "html")
        key4 = compute_cache_key("weekly", "2026-05-01", "2026-05-07", "csv")
        
        self.assertNotEqual(key1, key2)
        self.assertNotEqual(key1, key3)
        self.assertNotEqual(key1, key4)

    @patch('core.reporting.cache.get_app_data_dir')
    def test_get_cached_report_returns_none_when_not_exists(self, mock_get_dir):
        """Test that get_cached_report returns None when cache file doesn't exist"""
        mock_get_dir.return_value = self.test_cache_dir
        
        result = get_cached_report("weekly", "2026-05-01", "2026-05-07", "html")
        
        self.assertIsNone(result)

    @patch('core.reporting.cache.get_app_data_dir')
    @patch('core.reporting.cache.shutil.copy2')
    def test_save_to_cache_copies_file(self, mock_copy, mock_get_dir):
        """Test that save_to_cache copies the file to cache directory"""
        mock_get_dir.return_value = self.test_cache_dir
        
        # Create a temp source file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.html') as f:
            f.write("<html>test</html>")
            source_path = f.name
        
        try:
            save_to_cache("weekly", "2026-05-01", "2026-05-07", "html", source_path)
            
            mock_copy.assert_called_once()
            args = mock_copy.call_args[0]
            self.assertEqual(args[0], source_path)
            self.assertTrue(args[1].endswith('.html'))
        finally:
            os.unlink(source_path)

    @patch('core.reporting.cache.get_cache_dir')
    def test_get_cached_report_returns_path_when_exists(self, mock_get_cache_dir):
        """Test that get_cached_report returns path when cache file exists"""
        mock_get_cache_dir.return_value = self.test_cache_dir
        
        # Create cache file manually
        key = compute_cache_key("weekly", "2026-05-01", "2026-05-07", "html")
        cache_file = os.path.join(self.test_cache_dir, f"{key}.html")
        with open(cache_file, 'w') as f:
            f.write("<html>cached</html>")
        
        result = get_cached_report("weekly", "2026-05-01", "2026-05-07", "html")
        
        self.assertEqual(result, cache_file)


class TestStatisticsFunctions(unittest.TestCase):
    """Tests for statistics calculation functions"""

    def test_calculate_total_hours_empty(self):
        """Test calculate_total_hours with empty list"""
        result = calculate_total_hours([])
        self.assertEqual(result, 0.0)

    def test_calculate_total_hours_single_day(self):
        """Test calculate_total_hours with single day"""
        days = [{"total_seconds": 3600}]  # 1 hour
        result = calculate_total_hours(days)
        self.assertEqual(result, 1.0)

    def test_calculate_total_hours_multiple_days(self):
        """Test calculate_total_hours with multiple days"""
        days = [
            {"total_seconds": 3600},   # 1 hour
            {"total_seconds": 7200},   # 2 hours
            {"total_seconds": 1800}    # 0.5 hours
        ]
        result = calculate_total_hours(days)
        self.assertEqual(result, 3.5)

    def test_calculate_average_hours_empty(self):
        """Test calculate_average_hours with empty list"""
        result = calculate_average_hours([])
        self.assertEqual(result, 0.0)

    def test_calculate_average_hours_single_day(self):
        """Test calculate_average_hours with single day"""
        days = [{"total_seconds": 7200}]  # 2 hours
        result = calculate_average_hours(days)
        self.assertEqual(result, 2.0)

    def test_calculate_average_hours_multiple_days(self):
        """Test calculate_average_hours with multiple days"""
        days = [
            {"total_seconds": 3600},   # 1 hour
            {"total_seconds": 3600},   # 1 hour
            {"total_seconds": 3600}    # 1 hour
        ]
        result = calculate_average_hours(days)
        self.assertEqual(result, 1.0)

    def test_calculate_most_active_day_empty(self):
        """Test calculate_most_active_day with empty list"""
        result = calculate_most_active_day([])
        self.assertIsNone(result)

    def test_calculate_most_active_day_all_zero(self):
        """Test calculate_most_active_day when all days have zero seconds"""
        days = [
            {"date": "2026-05-01", "total_seconds": 0},
            {"date": "2026-05-02", "total_seconds": 0}
        ]
        result = calculate_most_active_day(days)
        self.assertIsNone(result)

    def test_calculate_most_active_day_finds_max(self):
        """Test calculate_most_active_day finds the day with most seconds"""
        days = [
            {"date": "2026-05-01", "total_seconds": 3600},
            {"date": "2026-05-02", "total_seconds": 7200},
            {"date": "2026-05-03", "total_seconds": 1800}
        ]
        result = calculate_most_active_day(days)
        self.assertEqual(result, "2026-05-02")

    def test_calculate_longest_session_empty(self):
        """Test calculate_longest_session with empty list"""
        result = calculate_longest_session([])
        self.assertEqual(result, 0)

    def test_calculate_longest_session_single_day(self):
        """Test calculate_longest_session with single day"""
        days = [{"longest_session": 3600}]
        result = calculate_longest_session(days)
        self.assertEqual(result, 3600)

    def test_calculate_longest_session_multiple_days(self):
        """Test calculate_longest_session with multiple days"""
        days = [
            {"longest_session": 1800},
            {"longest_session": 7200},
            {"longest_session": 3600}
        ]
        result = calculate_longest_session(days)
        self.assertEqual(result, 7200)


class TestIntegration(unittest.TestCase):
    """Integration tests for reporting module"""

    def test_report_job_lifecycle(self):
        """Test complete report job lifecycle"""
        # Create pending job
        job = ReportJob(
            id="integration-test-id",
            status=ReportStatus.PENDING,
            progress=0,
            report_type="daily",
            start_date="2026-05-30",
            end_date="2026-05-30",
            output_path=None,
            error_message=None
        )
        
        self.assertEqual(job.status, ReportStatus.PENDING)
        self.assertEqual(job.progress, 0)
        
        # Simulate running state
        job.status = ReportStatus.RUNNING
        job.progress = 50
        
        self.assertEqual(job.status, ReportStatus.RUNNING)
        self.assertEqual(job.progress, 50)
        
        # Simulate completion
        job.status = ReportStatus.COMPLETE
        job.progress = 100
        job.output_path = "/output/report.html"
        
        self.assertEqual(job.status, ReportStatus.COMPLETE)
        self.assertEqual(job.progress, 100)
        self.assertEqual(job.output_path, "/output/report.html")

    def test_statistics_chain_calculation(self):
        """Test chaining multiple statistics calculations"""
        days = [
            {"date": "2026-05-01", "total_seconds": 7200, "longest_session": 3600},
            {"date": "2026-05-02", "total_seconds": 10800, "longest_session": 5400},
            {"date": "2026-05-03", "total_seconds": 3600, "longest_session": 1800}
        ]
        
        total = calculate_total_hours(days)
        avg = calculate_average_hours(days)
        most_active = calculate_most_active_day(days)
        longest = calculate_longest_session(days)
        
        self.assertEqual(total, 6.0)  # 21600 / 3600
        self.assertEqual(avg, 2.0)    # 6.0 / 3
        self.assertEqual(most_active, "2026-05-02")
        self.assertEqual(longest, 5400)


if __name__ == '__main__':
    unittest.main(verbosity=2)
