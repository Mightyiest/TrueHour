import unittest
import time
from unittest.mock import patch
from datetime import datetime
from tracker import AppTracker

class TestDistractionPause(unittest.TestCase):
    def test_distraction_auto_pause(self):
        """Test that tracker auto-pauses when a distracting app is focused"""
        tracker = AppTracker(poll_interval=0.01, min_track_seconds=0)
        tracker.enable_distraction_auto_pause = True
        tracker.distraction_apps = ["chrome.exe", "discord"]
        
        with patch('tracker.get_foreground_app_info', return_value=("VS Code", "code.exe")):
            tracker.start(session_name="Test Session")
            time.sleep(0.05)
            self.assertFalse(tracker.paused)
            self.assertFalse(tracker._distraction_paused)
            
            # Switch to distracting app (exact exe match)
            with patch('tracker.get_foreground_app_info', return_value=("Google Chrome", "chrome.exe")):
                time.sleep(0.05)
                self.assertTrue(tracker.paused)
                self.assertTrue(tracker._distraction_paused)
                
            # Switch back to productive app
            with patch('tracker.get_foreground_app_info', return_value=("VS Code", "code.exe")):
                time.sleep(0.05)
                self.assertFalse(tracker.paused)
                self.assertFalse(tracker._distraction_paused)
                
            tracker.stop()

    def test_distraction_friendly_name_substring(self):
        """Test that tracker auto-pauses matching friendly name substrings"""
        tracker = AppTracker(poll_interval=0.01, min_track_seconds=0)
        tracker.enable_distraction_auto_pause = True
        tracker.distraction_apps = ["discord"]
        
        with patch('tracker.get_foreground_app_info', return_value=("VS Code", "code.exe")):
            tracker.start(session_name="Test Session")
            time.sleep(0.05)
            
            # Switch to distracting app (friendly name substring match)
            with patch('tracker.get_foreground_app_info', return_value=("Discord Desktop client", "discord.exe")):
                time.sleep(0.05)
                self.assertTrue(tracker.paused)
                self.assertTrue(tracker._distraction_paused)
                
            tracker.stop()

    def test_manual_pause_override(self):
        """Test that manual pause overrides distraction auto-resume"""
        tracker = AppTracker(poll_interval=0.01, min_track_seconds=0)
        tracker.enable_distraction_auto_pause = True
        tracker.distraction_apps = ["chrome.exe"]
        
        with patch('tracker.get_foreground_app_info', return_value=("VS Code", "code.exe")):
            tracker.start(session_name="Test Session")
            time.sleep(0.05)
            
            # Manually pause
            tracker.toggle_pause()
            self.assertTrue(tracker.paused)
            self.assertFalse(tracker._distraction_paused)
            
            # Switch to distracting app
            with patch('tracker.get_foreground_app_info', return_value=("Google Chrome", "chrome.exe")):
                time.sleep(0.05)
                self.assertTrue(tracker.paused)
                self.assertFalse(tracker._distraction_paused)
                
            # Switch back to productive app
            with patch('tracker.get_foreground_app_info', return_value=("VS Code", "code.exe")):
                time.sleep(0.05)
                self.assertTrue(tracker.paused)
                
            tracker.stop()

if __name__ == '__main__':
    unittest.main()
