"""
Test suite for idle deduction logic in AppTracker
"""

import unittest
import time
from datetime import datetime
from tracker import AppTracker

class TestIdleDeduction(unittest.TestCase):
    """Tests for the idle deduction logic in AppTracker"""

    def test_idle_deduction(self):
        """Test that idle threshold duration is correctly deducted upon auto-pause"""
        tracker = AppTracker(poll_interval=1.0, min_track_seconds=2)
        tracker.running = True
        tracker.session_start = datetime.now()
        tracker.idle_threshold_seconds = 120
        
        # Simulate active app tracking for 5 minutes (300 seconds)
        tracker._current_app = "Google Chrome"
        tracker._current_start = time.time()
        tracker._current_block_start = time.time() - 300
        tracker._current_block_active = 300.0
        tracker.app_times["Google Chrome"] = 300.0
        
        # Ensure initial state matches simulation
        self.assertEqual(tracker.app_times["Google Chrome"], 300.0)
        self.assertEqual(tracker._total_paused_time, 0.0)
        
        # Trigger idle pause
        tracker.toggle_pause(is_idle=True)
        
        # Verify 120 seconds was deducted from the app times and block duration
        self.assertAlmostEqual(tracker.app_times["Google Chrome"], 180.0, places=3)
        self.assertEqual(len(tracker.timeline), 1)
        timeline_entry = tracker.timeline[0]
        self.assertEqual(timeline_entry["app"], "Google Chrome")
        duration = (timeline_entry["end"] - timeline_entry["start"]).total_seconds()
        self.assertAlmostEqual(duration, 180.0, places=3)
        
        # Verify 120 seconds was added to total paused time
        self.assertEqual(tracker._total_paused_time, 120.0)
        
        # Verify tracker state is now paused
        self.assertTrue(tracker.paused)

    def test_idle_deduction_lower_bound_guard(self):
        """Test that deduction doesn't drop app times or block duration below 0"""
        tracker = AppTracker(poll_interval=1.0, min_track_seconds=2)
        tracker.running = True
        tracker.session_start = datetime.now()
        tracker.idle_threshold_seconds = 120
        
        # Simulate active app tracking for only 30 seconds
        tracker._current_app = "Google Chrome"
        tracker._current_start = time.time()
        tracker._current_block_start = time.time() - 30
        tracker._current_block_active = 30.0
        tracker.app_times["Google Chrome"] = 30.0
        
        # Trigger idle pause
        tracker.toggle_pause(is_idle=True)
        
        # Verify it is capped at 0.0 instead of going negative
        self.assertAlmostEqual(tracker.app_times["Google Chrome"], 0.0, places=3)
        self.assertEqual(len(tracker.timeline), 0)
        self.assertEqual(tracker._total_paused_time, 120.0)
        self.assertTrue(tracker.paused)

if __name__ == '__main__':
    unittest.main(verbosity=2)
