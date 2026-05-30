import os
import base64
from core.reporting.exporters import BaseExporter
from report import format_duration

class HTMLExporter(BaseExporter):
    def export(self, report_data: dict, output_path: str) -> bool:
        try:
            # Load images as base64 for embedding if they exist
            donut_base64 = ""
            bar_base64 = ""
            
            donut_path = report_data.get("donut_chart_path")
            bar_path = report_data.get("bar_chart_path")
            
            if donut_path and os.path.exists(donut_path):
                with open(donut_path, "rb") as f:
                    donut_base64 = base64.b64encode(f.read()).decode("utf-8")
            if bar_path and os.path.exists(bar_path):
                with open(bar_path, "rb") as f:
                    bar_base64 = base64.b64encode(f.read()).decode("utf-8")
            
            donut_img_html = f'<img class="chart-img" src="data:image/png;base64,{donut_base64}" />' if donut_base64 else '<p>No Donut Chart</p>'
            bar_img_html = f'<img class="chart-img" src="data:image/png;base64,{bar_base64}" />' if bar_base64 else '<p>No Bar Chart</p>'
            
            project_rows = ""
            for item in report_data.get("project_breakdown", []):
                project_rows += f"""
                <tr>
                    <td><span class="project-dot" style="background: {item.get('color', '#64748B')}"></span>{item.get('project', '')}</td>
                    <td>{format_duration(item.get('seconds', 0))}</td>
                    <td>{item.get('percent', 0)}%</td>
                </tr>
                """
                
            trend_rows = ""
            for item in report_data.get("daily_trend", []):
                trend_rows += f"""
                <tr>
                    <td>{item.get('label', '')}</td>
                    <td>{item.get('value', 0.0)} hrs</td>
                </tr>
                """

            html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>TrueHour Performance Report</title>
    <style>
        :root {{
            --primary: #4F46E5;
            --primary-light: #818CF8;
            --bg-body: #F9FAFB;
            --bg-card: #FFFFFF;
            --text-main: #111827;
            --text-sec: #4B5563;
            --border: #E5E7EB;
        }}
        body {{
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: var(--bg-body);
            color: var(--text-main);
            margin: 0;
            padding: 40px 20px;
        }}
        .container {{
            max-width: 800px;
            margin: 0 auto;
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 40px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05);
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid var(--border);
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}
        .header h1 {{
            font-size: 24px;
            margin: 0;
            color: var(--primary);
            font-weight: 800;
        }}
        .meta {{
            font-size: 14px;
            color: var(--text-sec);
            text-align: right;
        }}
        .grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 30px;
        }}
        .card {{
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
            background: #FDFDFD;
        }}
        .card h3 {{
            margin-top: 0;
            color: var(--primary);
            font-size: 16px;
            border-bottom: 1px solid var(--border);
            padding-bottom: 8px;
        }}
        .chart-img {{
            max-width: 100%;
            height: auto;
            display: block;
            margin: 0 auto;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }}
        th, td {{
            padding: 10px 12px;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }}
        th {{
            color: var(--text-sec);
            font-weight: 600;
        }}
        .project-dot {{
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            margin-right: 8px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1>TrueHour Performance Report</h1>
                <div style="font-size: 14px; color: var(--text-sec); margin-top: 4px;">Type: {report_data.get('report_type', '')}</div>
            </div>
            <div class="meta">
                <div><strong>Range:</strong> {report_data.get('start_date', '')} to {report_data.get('end_date', '')}</div>
                <div><strong>Total Time:</strong> {format_duration(report_data.get('total_seconds', 0))}</div>
            </div>
        </div>
        
        <div class="grid">
            <div class="card">
                <h3>App Allocation Chart</h3>
                {donut_img_html}
            </div>
            <div class="card">
                <h3>Productivity Trend</h3>
                {bar_img_html}
            </div>
        </div>
        
        <div class="card" style="margin-bottom: 20px;">
            <h3>Project Breakdown</h3>
            <table>
                <thead>
                    <tr>
                        <th>Project</th>
                        <th>Duration</th>
                        <th>Percent</th>
                    </tr>
                </thead>
                <tbody>
                    {project_rows}
                </tbody>
            </table>
        </div>
        
        <div class="card">
            <h3>Daily Productivity History</h3>
            <table>
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Tracked Time</th>
                    </tr>
                </thead>
                <tbody>
                    {trend_rows}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            return True
        except Exception as e:
            print(f"[HTMLExporter] Export failed: {e}")
            return False
