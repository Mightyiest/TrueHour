"""
Test suite for secure_time.py - Anti-tamper time tracking system
"""

import unittest
import time
import hashlib
from unittest.mock import patch, MagicMock
from secure_time import TimeTamperDetector, get_detector, reset_detector


class TestTimeTamperDetector(unittest.TestCase):
    """Tests for the TimeTamperDetector class"""

    def setUp(self):
        self.detector = TimeTamperDetector()

    def tearDown(self):
        # Clean up any running sessions
        if self.detector.monotonic_start is not None:
            self.detector.end_session()

    def test_initialization(self):
        """Test that detector initializes correctly"""
        self.assertEqual(self.detector.trust_score, 100)
        self.assertIsNone(self.detector.monotonic_start)
        self.assertIsNone(self.detector.system_start)
        self.assertEqual(len(self.detector.tamper_events), 0)

    def test_start_session_initializes_correctly(self):
        """Test that start_session sets up initial state"""
        self.detector.start_session()
        
        self.assertIsNotNone(self.detector.monotonic_start)
        self.assertIsNotNone(self.detector.system_start)
        self.assertGreater(len(self.detector.chain_data), 0)
        
        # First entry should be SESSION_START
        self.assertEqual(self.detector.chain_data[0]['event_type'], 'SESSION_START')

    def test_validate_and_record_valid_entry(self):
        """Test recording a valid tracking entry"""
        self.detector.start_session()
        time.sleep(0.1)
        
        result = self.detector.validate_and_record("TestApp", 60.0)
        
        self.assertIn('duration_seconds', result)
        self.assertEqual(result['duration_seconds'], 60.0)
        self.assertIn('integrity_status', result)
        self.assertEqual(result['integrity_status'], 'VALID')
        self.assertIn('trust_score', result)

    def test_end_session_finalizes(self):
        """Test that end_session finalizes properly"""
        self.detector.start_session()
        time.sleep(0.1)
        self.detector.validate_and_record("TestApp", 30.0)
        
        result = self.detector.end_session()
        
        self.assertIn('trust_score', result)
        self.assertIn('tamper_events_count', result)
        self.assertIn('chain_length', result)
        self.assertGreater(result['chain_length'], 1)

    def test_trust_level_calculation(self):
        """Test trust level calculation based on score"""
        self.detector.trust_score = 95
        self.assertEqual(self.detector.get_trust_level(), 'HIGH')
        
        self.detector.trust_score = 75
        self.assertEqual(self.detector.get_trust_level(), 'MEDIUM')
        
        self.detector.trust_score = 55
        self.assertEqual(self.detector.get_trust_level(), 'LOW')
        
        self.detector.trust_score = 40
        self.assertEqual(self.detector.get_trust_level(), 'COMPROMISED')

    def test_hash_chain_creation(self):
        """Test that hash chain is created correctly"""
        initial_length = len(self.detector.chain_data)
        
        self.detector._add_to_chain("TEST_EVENT", {"data": "test"})
        
        self.assertEqual(len(self.detector.chain_data), initial_length + 1)
        last_entry = self.detector.chain_data[-1]
        
        self.assertIn('hash', last_entry)
        self.assertEqual(len(last_entry['hash']), 64)  # SHA256 hex length
        self.assertEqual(last_entry['event_type'], 'TEST_EVENT')

    def test_hash_chain_verification_valid(self):
        """Test verification of valid hash chain"""
        self.detector._add_to_chain("EVENT1", {"value": 1})
        self.detector._add_to_chain("EVENT2", {"value": 2})
        self.detector._add_to_chain("EVENT3", {"value": 3})
        
        is_valid = self.detector.verify_chain_integrity()
        self.assertTrue(is_valid)

    def test_hash_chain_verification_detects_tampering(self):
        """Test detection of tampered hash chain"""
        self.detector._add_to_chain("EVENT1", {"value": 1})
        self.detector._add_to_chain("EVENT2", {"value": 2})
        
        # Tamper with an entry
        if len(self.detector.chain_data) > 1:
            self.detector.chain_data[1]['data']['value'] = 999
            
            is_valid = self.detector.verify_chain_integrity()
            self.assertFalse(is_valid)

    def test_empty_chain_verification(self):
        """Test verification of empty chain"""
        fresh_detector = TimeTamperDetector()
        # Clear chain data
        fresh_detector.chain_data = []
        
        is_valid = fresh_detector.verify_chain_integrity()
        self.assertTrue(is_valid)

    @patch('secure_time.TimeTamperDetector.get_network_time')
    def test_clock_drift_detection(self, mock_ntp):
        """Test detection of clock drift via network time"""
        mock_ntp.return_value = 15.0  # 15 seconds offset
        
        self.detector.start_session()
        
        # Wait for async thread to complete
        time.sleep(0.5)
        
        # Trust score should be reduced due to drift
        self.assertLess(self.detector.trust_score, 100)
        self.assertGreater(len(self.detector.tamper_events), 0)

    @patch('urllib.request.urlopen')
    def test_get_network_time_date_header(self, mock_urlopen):
        """Test getting network time successfully via HTTP Date header"""
        from datetime import datetime, timezone
        
        # Configure mock response
        mock_response = MagicMock()
        mock_response.__enter__.return_value = mock_response
        mock_response.headers.get.return_value = "Wed, 20 May 2026 02:50:00 GMT"
        mock_urlopen.return_value = mock_response
        
        # Freeze system time to compare accurately
        # System time is 5 seconds ahead
        system_now = datetime(2026, 5, 20, 2, 50, 5, tzinfo=timezone.utc)
        
        with patch('secure_time.datetime') as mock_datetime:
            mock_datetime.now.return_value = system_now
            mock_datetime.fromisoformat = datetime.fromisoformat
            
            offset = self.detector.get_network_time()
            
            # Expected offset = 5.0 seconds
            self.assertEqual(offset, 5.0)
            mock_response.headers.get.assert_called_with("Date")

    @patch('urllib.request.urlopen')
    def test_get_network_time_json_fallback(self, mock_urlopen):
        """Test getting network time via JSON API body if Date header is missing"""
        from datetime import datetime, timezone
        
        def mock_urlopen_side_effect(req, *args, **kwargs):
            url = req.full_url if hasattr(req, 'full_url') else req
            mock_resp = MagicMock()
            mock_resp.__enter__.return_value = mock_resp
            if "timeapi.io" in url:
                mock_resp.headers.get.return_value = None
                mock_resp.read.return_value = b'{"dateTime": "2026-05-20T02:50:00+00:00"}'
                return mock_resp
            else:
                mock_resp.headers.get.return_value = None
                mock_resp.read.return_value = b''
                return mock_resp

        mock_urlopen.side_effect = mock_urlopen_side_effect
        
        system_now = datetime(2026, 5, 20, 2, 50, 5, tzinfo=timezone.utc)
        
        with patch('secure_time.datetime') as mock_datetime:
            mock_datetime.now.return_value = system_now
            mock_datetime.fromisoformat = datetime.fromisoformat
            
            offset = self.detector.get_network_time()
            
            # Expected offset = 5.0 seconds
            self.assertEqual(offset, 5.0)

    @patch('urllib.request.urlopen')
    def test_get_network_time_all_sources_fail(self, mock_urlopen):
        """Test that get_network_time returns None when all requests fail"""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("Connection failed")
        
        offset = self.detector.get_network_time()
        self.assertIsNone(offset)

    def test_trust_score_recovery(self):
        """Test that trust score recovers over time during valid tracking"""
        self.detector.start_session()
        self.detector.trust_score = 90
        # Set last recovery to 350 seconds ago to trigger recovery
        self.detector.last_trust_recovery = time.time() - 350
        
        # Validate entry
        result = self.detector.validate_and_record("TestApp", 60.0)
        
        # Expected: trust score increments by 1 to 91
        self.assertEqual(self.detector.trust_score, 91)
        self.assertEqual(result['trust_score'], 91)

    def test_session_report_generation(self):
        """Test session report generation"""
        self.detector.start_session()
        time.sleep(0.1)
        self.detector.validate_and_record("TestApp", 45.0)
        
        report = self.detector.get_session_report()
        
        self.assertIn('trust_score', report)
        self.assertIn('trust_level', report)
        self.assertIn('chain_length', report)
        self.assertIn('chain_valid', report)
        self.assertIn('events', report)


class TestGlobalDetector(unittest.TestCase):
    """Tests for global detector functions"""

    def tearDown(self):
        reset_detector()

    def test_get_detector_creates_instance(self):
        """Test that get_detector creates an instance"""
        detector = get_detector()
        self.assertIsNotNone(detector)
        self.assertIsInstance(detector, TimeTamperDetector)

    def test_get_detector_returns_same_instance(self):
        """Test that get_detector returns same instance"""
        detector1 = get_detector()
        detector2 = get_detector()
        
        self.assertIs(detector1, detector2)

    def test_reset_detector_creates_new_instance(self):
        """Test that reset_detector creates new instance"""
        detector1 = get_detector()
        reset_detector()
        detector2 = get_detector()
        
        self.assertIsNot(detector1, detector2)


class TestIntegration(unittest.TestCase):
    """Integration tests for the complete system"""

    def test_full_session_workflow(self):
        """Test complete session workflow with integrity checking"""
        detector = TimeTamperDetector()
        
        # Start session
        detector.start_session()
        time.sleep(0.1)
        
        # Record multiple entries
        detector.validate_and_record("App1", 60.0)
        time.sleep(0.05)
        detector.validate_and_record("App2", 120.0)
        time.sleep(0.05)
        detector.validate_and_record("App3", 90.0)
        
        # End session
        result = detector.end_session()
        
        # Verify chain integrity
        is_valid = detector.verify_chain_integrity()
        self.assertTrue(is_valid)
        
        # Check trust score
        self.assertGreaterEqual(result['trust_score'], 0)
        self.assertLessEqual(result['trust_score'], 100)

    def test_multiple_sessions_isolation(self):
        """Test that multiple sessions are properly isolated"""
        detector1 = TimeTamperDetector()
        detector2 = TimeTamperDetector()
        
        detector1.start_session()
        detector2.start_session()
        
        detector1.validate_and_record("App1", 30.0)
        detector2.validate_and_record("App2", 45.0)
        
        detector1.end_session()
        detector2.end_session()
        
        # Each detector should have its own chain
        self.assertNotEqual(id(detector1.chain_data), id(detector2.chain_data))


if __name__ == '__main__':
    unittest.main(verbosity=2)
