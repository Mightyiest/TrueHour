"""
Diagnostic isolation test for HTML invoice export crash.
Validates that HTMLExporter constructs file streams successfully
and doesn't cause low-level memory runtime crashes.
"""
import os
import sys
import tempfile
import traceback

# Add workspace to path
sys.path.insert(0, '/workspace')

from report import generate_session_report_html

def test_html_export_isolated_flow():
    """
    Validates that generate_session_report_html constructs HTML successfully
    without causing crashes.
    """
    print("=" * 60)
    print("Testing HTML Report Generation (Isolated Flow)")
    print("=" * 60)
    
    # Mock comprehensive payload matching format expected by app.py data builders
    mock_report_data = {
        "session_name": "Test Session",
        "date": "2026-01-15",
        "date_display": "January 15, 2026",
        "start": "2026-01-15T09:00:00",
        "start_display": "09:00 AM",
        "end": "2026-01-15T17:00:00",
        "end_display": "05:00 PM",
        "total_seconds": 28800,  # 8 hours
        "total_formatted": "8h 0m",
        "counted_seconds": 25200,  # 7 hours productive
        "counted_formatted": "7h 0m",
        "productivity_ratio": 87.5,
        "apps": [
            {
                "name": "VS Code",
                "seconds": 14400,
                "formatted": "4h 0m",
                "percent": 57.1,
                "tag": "Development",
                "excluded": False
            },
            {
                "name": "Chrome",
                "seconds": 7200,
                "formatted": "2h 0m",
                "percent": 28.6,
                "tag": "Research",
                "excluded": False
            },
            {
                "name": "Slack",
                "seconds": 3600,
                "formatted": "1h 0m",
                "percent": 14.3,
                "tag": "Communication",
                "excluded": False
            }
        ],
        "project_breakdown": [
            {"project": "Development", "seconds": 14400, "formatted": "4h 0m", "percent": 57.1, "color": "#4F46E5"},
            {"project": "Research", "seconds": 7200, "formatted": "2h 0m", "percent": 28.6, "color": "#10B981"},
            {"project": "Communication", "seconds": 3600, "formatted": "1h 0m", "percent": 14.3, "color": "#06B6D4"}
        ],
        "timeline": [
            {
                "app": "VS Code",
                "start": datetime_from_str("2026-01-15T09:00:00"),
                "end": datetime_from_str("2026-01-15T13:00:00")
            },
            {
                "app": "Chrome",
                "start": datetime_from_str("2026-01-15T13:00:00"),
                "end": datetime_from_str("2026-01-15T15:00:00")
            },
            {
                "app": "Slack",
                "start": datetime_from_str("2026-01-15T15:00:00"),
                "end": datetime_from_str("2026-01-15T16:00:00")
            }
        ],
        "app_exe_paths": {},
        "new_activity": []
    }
    
    try:
        print("\n[1] Generating HTML content...")
        html_content = generate_session_report_html(
            mock_report_data, 
            hourly_rate=50.0, 
            currency_symbol="$"
        )
        
        assert html_content is not None, "HTML content is None"
        assert len(html_content) > 0, "HTML content is empty"
        assert "<!DOCTYPE html>" in html_content or "<html" in html_content, "Invalid HTML structure"
        print(f"✓ HTML generated successfully ({len(html_content)} characters)")
        
        print("\n[2] Writing HTML to temporary file...")
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_report.html")
            
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            
            assert os.path.exists(output_path), "Output file was not created"
            
            file_size = os.path.getsize(output_path)
            print(f"✓ File written successfully ({file_size} bytes)")
            
            # Verify content integrity
            with open(output_path, "r", encoding="utf-8") as f:
                content = f.read()
                assert "TrueHour" in content, "Missing TrueHour branding"
                assert "Test Session" in content, "Missing session name"
                assert "VS Code" in content, "Missing app data"
                print("✓ Content verification passed")
        
        print("\n" + "=" * 60)
        print("TEST PASSED: HTML export works correctly!")
        print("=" * 60)
        return True
        
    except Exception as e:
        print("\n" + "=" * 60)
        print("TEST FAILED: Exception occurred!")
        print("=" * 60)
        print(f"\nError Type: {type(e).__name__}")
        print(f"Error Message: {str(e)}")
        print("\nFull Traceback:")
        traceback.print_exc()
        return False


def datetime_from_str(iso_str):
    """Helper to parse ISO datetime strings."""
    from datetime import datetime
    return datetime.fromisoformat(iso_str)


if __name__ == "__main__":
    success = test_html_export_isolated_flow()
    sys.exit(0 if success else 1)
