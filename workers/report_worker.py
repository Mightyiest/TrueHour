"""
Worker thread for generating session reports in the background.
This prevents UI freezing during heavy report generation.
"""
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any
from PyQt6.QtCore import QThread, pyqtSignal

# Add project root to path for imports
sys.path.insert(0, '/workspace')

from tracker import AppTracker


class ReportGeneratorWorker(QThread):
    """
    Background worker to generate session reports without blocking UI.
    """
    # Signals
    finished = pyqtSignal(str)  # Emits HTML report
    error = pyqtSignal(str)     # Emits error message
    progress = pyqtSignal(int, str)  # Emits progress percentage and status

    def __init__(self, tracker: AppTracker, start_time: datetime, end_time: datetime):
        super().__init__()
        self.tracker = tracker
        self.start_time = start_time
        self.end_time = end_time
        self._stop_flag = False

    def stop(self):
        """Request worker to stop gracefully."""
        self._stop_flag = True

    def run(self):
        """Execute report generation in background thread."""
        try:
            self.progress.emit(10, "Analyzing activity data...")
            
            if self._stop_flag:
                return

            # Build optimized report data (single pass, no icons)
            report_data = self._build_optimized_report_data()
            
            if self._stop_flag:
                return

            self.progress.emit(60, "Generating report...")
            
            # Generate HTML (optimized, no external resources)
            html_report = self._generate_optimized_html(report_data)
            
            if self._stop_flag:
                return

            self.progress.emit(90, "Finalizing...")
            self.progress.emit(100, "Complete!")
            
            self.finished.emit(html_report)
            
        except Exception as e:
            self.error.emit(str(e))

    def _build_optimized_report_data(self) -> Dict[str, Any]:
        """
        Build report data with optimized single-pass aggregation.
        No icon extraction, no timeline details, no network calls.
        """
        total_seconds = int((self.end_time - self.start_time).total_seconds())
        
        # Get apps from tracker (thread-safe read using public methods)
        with self.tracker._lock:
            app_times = dict(self.tracker.app_times)
            app_exe_paths = dict(self.tracker.app_exe_paths)
            app_included = dict(self.tracker.app_included)
        
        # Single pass aggregation
        app_list = []
        category_stats = {}
        
        for app_name, seconds in app_times.items():
            if seconds <= 0:
                continue
            
            # Get category from tag manager
            exe_path = app_exe_paths.get(app_name, "")
            included = app_included.get(app_name, True)
            
            # Skip auto-excluded apps
            if not included:
                continue
                
            category = self.tracker.tag_manager.get_tag(app_name, exe_path)
            
            # Category stats
            if category not in category_stats:
                category_stats[category] = {'time': 0, 'count': 0}
            category_stats[category]['time'] += seconds
            category_stats[category]['count'] += 1
            
            # App list
            app_list.append({
                'name': app_name,
                'path': exe_path,
                'seconds': seconds,
                'category': category,
                'initial': app_name[0].upper() if app_name else '?',
                'color': self._get_category_color(category)
            })
        
        # Sort by time descending
        app_list.sort(key=lambda x: x['seconds'], reverse=True)
        
        # Top apps summary
        top_apps = app_list[:5]
        other_time = sum(app['seconds'] for app in app_list[5:])
        
        # Category breakdown
        category_list = [
            {
                'name': cat,
                'seconds': stats['time'],
                'count': stats['count'],
                'color': self._get_category_color(cat)
            }
            for cat, stats in category_stats.items()
        ]
        category_list.sort(key=lambda x: x['seconds'], reverse=True)
        
        return {
            'start_time': self.start_time,
            'end_time': self.end_time,
            'total_seconds': total_seconds,
            'apps': app_list,
            'top_apps': top_apps,
            'other_time': other_time,
            'categories': category_list,
            'app_count': len(app_list),
            'category_count': len(category_list)
        }

    def _get_category_color(self, category: str) -> str:
        """Get color for category."""
        colors = {
            'Development': '#3b82f6',
            'Communication': '#10b981',
            'Entertainment': '#8b5cf6',
            'Social Media': '#ec4899',
            'Productivity': '#f59e0b',
            'Browser': '#06b6d4',
            'System': '#6b7280',
            'Other': '#9ca3af'
        }
        return colors.get(category, '#9ca3af')

    def _generate_optimized_html(self, data: Dict[str, Any]) -> str:
        """
        Generate simplified HTML report without icons or timeline.
        Uses inline SVG placeholders instead of extracted icons.
        """
        def format_time(seconds):
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            if hours > 0:
                return f"{hours}h {minutes}m {secs}s"
            elif minutes > 0:
                return f"{minutes}m {secs}s"
            else:
                return f"{secs}s"
        
        def format_datetime(dt):
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        
        def svg_icon(initial, color):
            return f'''<svg width="40" height="40" viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg">
                <rect width="40" height="40" rx="8" fill="{color}"/>
                <text x="20" y="27" font-family="Arial, sans-serif" font-size="20" font-weight="bold" fill="white" text-anchor="middle">{initial}</text>
            </svg>'''
        
        # Build app rows
        app_rows = ""
        for i, app in enumerate(data['apps'][:10]):  # Top 10 only
            percent = (app['seconds'] / data['total_seconds'] * 100) if data['total_seconds'] > 0 else 0
            app_rows += f'''
            <tr>
                <td style="padding: 12px; border-bottom: 1px solid #e5e7eb;">
                    <div style="display: flex; align-items: center; gap: 12px;">
                        {svg_icon(app['initial'], app['color'])}
                        <div>
                            <div style="font-weight: 600; color: #1f2937;">{app['name']}</div>
                            <div style="font-size: 12px; color: #6b7280;">{app['category']}</div>
                        </div>
                    </div>
                </td>
                <td style="padding: 12px; border-bottom: 1px solid #e5e7eb; text-align: right;">
                    <div style="font-weight: 600; color: #1f2937;">{format_time(app['seconds'])}</div>
                    <div style="font-size: 12px; color: #6b7280;">{percent:.1f}%</div>
                </td>
            </tr>'''
        
        if len(data['apps']) > 10:
            app_rows += f'''
            <tr>
                <td colspan="2" style="padding: 12px; text-align: center; color: #6b7280; font-style: italic;">
                    ... and {len(data['apps']) - 10} more apps
                </td>
            </tr>'''
        
        # Build category rows
        category_rows = ""
        for cat in data['categories']:
            percent = (cat['seconds'] / data['total_seconds'] * 100) if data['total_seconds'] > 0 else 0
            category_rows += f'''
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">
                    <span style="display: inline-block; width: 12px; height: 12px; background: {cat['color']}; border-radius: 2px; margin-right: 8px;"></span>
                    {cat['name']} ({cat['count']} apps)
                </td>
                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb; text-align: right;">
                    {format_time(cat['seconds'])} ({percent:.1f}%)
                </td>
            </tr>'''
        
        html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>TrueHour Session Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #f9fafb; }}
        .container {{ max-width: 800px; margin: 0 auto; background: white; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); overflow: hidden; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; }}
        .header h1 {{ margin: 0 0 10px 0; font-size: 28px; }}
        .header p {{ margin: 0; opacity: 0.9; }}
        .summary {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; padding: 30px; background: #f3f4f6; }}
        .summary-item {{ text-align: center; }}
        .summary-value {{ font-size: 32px; font-weight: bold; color: #667eea; }}
        .summary-label {{ font-size: 14px; color: #6b7280; margin-top: 5px; }}
        .section {{ padding: 30px; }}
        .section h2 {{ margin: 0 0 20px 0; color: #1f2937; font-size: 20px; border-bottom: 2px solid #667eea; padding-bottom: 10px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ text-align: left; padding: 12px; background: #f9fafb; color: #6b7280; font-weight: 600; font-size: 14px; }}
        .footer {{ padding: 20px; text-align: center; color: #9ca3af; font-size: 12px; border-top: 1px solid #e5e7eb; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎯 Session Report</h1>
            <p>{format_datetime(data['start_time'])} - {format_datetime(data['end_time'])}</p>
        </div>
        
        <div class="summary">
            <div class="summary-item">
                <div class="summary-value">{format_time(data['total_seconds'])}</div>
                <div class="summary-label">Total Time</div>
            </div>
            <div class="summary-item">
                <div class="summary-value">{data['app_count']}</div>
                <div class="summary-label">Apps Used</div>
            </div>
            <div class="summary-item">
                <div class="summary-value">{data['category_count']}</div>
                <div class="summary-label">Categories</div>
            </div>
        </div>
        
        <div class="section">
            <h2>📊 Top Applications</h2>
            <table>
                <thead>
                    <tr>
                        <th>Application</th>
                        <th style="text-align: right;">Time Spent</th>
                    </tr>
                </thead>
                <tbody>
                    {app_rows}
                </tbody>
            </table>
        </div>
        
        <div class="section">
            <h2>🏷️ Categories Breakdown</h2>
            <table>
                <thead>
                    <tr>
                        <th>Category</th>
                        <th style="text-align: right;">Time</th>
                    </tr>
                </thead>
                <tbody>
                    {category_rows}
                </tbody>
            </table>
        </div>
        
        <div class="footer">
            Generated by TrueHour • {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        </div>
    </div>
</body>
</html>'''
        
        return html
