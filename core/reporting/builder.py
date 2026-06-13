import os
from core.reporting.models import ReportStatus
from core.reporting.queue import update_job, get_report_job
from core.reporting.statistics import get_daily_summaries, calculate_total_hours, calculate_average_hours, calculate_longest_session, calculate_project_breakdown
from core.reporting.charts import build_donut_chart, build_bar_chart
from core.reporting.cache import get_cached_report, save_to_cache
from report import get_project_color, format_duration
from config import get_app_data_dir

def generate_report(job_id: str):
    job = get_report_job(job_id)
    if not job:
        return

    start_date = job.start_date
    end_date = job.end_date
    report_type = job.report_type

    # 1. Check Cache
    cached_path = get_cached_report(report_type, start_date, end_date, report_type)
    if cached_path and job.output_path:
        import shutil
        try:
            shutil.copy2(cached_path, job.output_path)
            update_job(job_id, ReportStatus.COMPLETE, 100, output_path=job.output_path)
            return
        except Exception:
            pass

    # 2. Load Data
    update_job(job_id, ReportStatus.RUNNING, 15)
    days = get_daily_summaries(start_date, end_date)

    # 3. Calculate Statistics
    update_job(job_id, ReportStatus.RUNNING, 40)
    total_hours = calculate_total_hours(days)
    avg_hours = calculate_average_hours(days)
    longest_session_secs = calculate_longest_session(days)
    project_breakdown = calculate_project_breakdown(start_date, end_date)

    # Enrich breakdown with colors & formatted strings for UI / Exporters
    enriched_breakdown = []
    for item in project_breakdown:
        proj_name = item["project"]
        secs = item["seconds"]
        enriched_breakdown.append({
            "project": proj_name,
            "seconds": secs,
            "percent": item["percent"],
            "formatted": format_duration(secs),
            "color": get_project_color(proj_name)
        })

    # Build daily trend representation for bar chart
    trend_data = []
    for day in days:
        # e.g., '2026-05-30' -> '05/30'
        label = day["date"][5:].replace("-", "/")
        trend_data.append({
            "label": label,
            "value": round(day["total_seconds"] / 3600.0, 2)
        })

    # 4. Generate Charts
    update_job(job_id, ReportStatus.RUNNING, 70)
    temp_dir = os.path.join(get_app_data_dir(), "temp_charts")
    os.makedirs(temp_dir, exist_ok=True)

    donut_chart_path = os.path.join(temp_dir, f"{job_id}_donut.png")
    bar_chart_path = os.path.join(temp_dir, f"{job_id}_bar.png")

    build_donut_chart(enriched_breakdown, donut_chart_path)
    build_bar_chart(trend_data, bar_chart_path)

    # Combine all stats into a single dictionary
    report_data = {
        "report_type": report_type,
        "start_date": start_date,
        "end_date": end_date,
        "total_seconds": int(total_hours * 3600),
        "average_hours": avg_hours,
        "longest_session_secs": longest_session_secs,
        "project_breakdown": enriched_breakdown,
        "daily_trend": trend_data,
        "donut_chart_path": donut_chart_path,
        "bar_chart_path": bar_chart_path
    }

    # 5. Export Report
    update_job(job_id, ReportStatus.RUNNING, 90)

    export_format = report_type.lower()
    output_path = job.output_path
    if output_path:
        _, ext = os.path.splitext(output_path)
        if ext:
            export_format = ext[1:].lower()
    else:
        # Default fallback output path
        output_path = os.path.join(get_app_data_dir(), f"Report_{start_date}_{end_date}.{export_format}")

    success = False
    if export_format == "html":
        from core.reporting.exporters.html_exporter import HTMLExporter
        exporter = HTMLExporter()
        success = exporter.export(report_data, output_path)
    elif export_format == "txt":
        try:
            total_hours = round(report_data.get("total_seconds", 0) / 3600.0, 2)
            longest_hours = round(report_data.get("longest_session_secs", 0) / 3600.0, 2)

            lines = [
                "==================================================",
                "              TRUEHOUR PERFORMANCE REPORT         ",
                "==================================================",
                f"Report Type:          {report_data.get('report_type', '')}",
                f"Date Range:           {report_data.get('start_date', '')} to {report_data.get('end_date', '')}",
                f"Total Tracked Time:   {total_hours} hours",
                f"Average Daily Time:   {round(report_data.get('average_hours', 0.0), 2)} hours",
                f"Longest Session:      {longest_hours} hours",
                "==================================================",
                "",
                "PROJECT BREAKDOWN",
                "--------------------------------------------------",
            ]
            for item in report_data.get("project_breakdown", []):
                lines.append(f"- {item.get('project', ''):<20} {item.get('formatted', ''):<15} ({item.get('percent', 0.0)}%)")

            lines.extend([
                "",
                "DAILY TREND",
                "--------------------------------------------------",
            ])
            for item in report_data.get("daily_trend", []):
                lines.append(f"- {item.get('label', ''):<10} {item.get('value', 0.0):>5} hours")

            lines.append("==================================================")

            with open(output_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            success = True
        except Exception as e:
            print(f"[TXT Export] Failed: {e}")
            success = False

    # Clean up temp charts
    try:
        if os.path.exists(donut_chart_path):
            os.remove(donut_chart_path)
        if os.path.exists(bar_chart_path):
            os.remove(bar_chart_path)
    except Exception:
        pass

    if success:
        save_to_cache(report_type, start_date, end_date, export_format, output_path)
        update_job(job_id, ReportStatus.COMPLETE, 100, output_path=output_path)
    else:
        update_job(job_id, ReportStatus.FAILED, 100, error_message="Exporter failed to output report.")
