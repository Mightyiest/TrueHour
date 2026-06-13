import logging
from PyQt6.QtCore import QThread, pyqtSignal
from report import build_report_data, save_to_autosave

logger = logging.getLogger(__name__)

class ReportWorker(QThread):
    """
    Background worker thread to compile session reports and handle
    autosaves without blocking the primary GUI event loop.
    """
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    status_changed = pyqtSignal(int, str)

    def __init__(self, tracker, hourly_rate=0.0, currency_symbol="$", stop_tracker=False, parent=None):
        super().__init__(parent)
        self.tracker = tracker
        self.hourly_rate = hourly_rate
        self.currency_symbol = currency_symbol
        self.stop_tracker = stop_tracker

    def run(self):
        try:
            logger.info("[ReportWorker] Starting background report compilation...")

            if self.stop_tracker:
                self.status_changed.emit(5, "Stopping active tracking session...")
                self.tracker.stop()

            self.status_changed.emit(10, "Initializing background report builder...")

            # Map progress steps from build_report_data directly to the status_changed signal
            report = build_report_data(
                self.tracker,
                self.hourly_rate,
                self.currency_symbol,
                progress_cb=self.status_changed.emit
            )

            logger.info("[ReportWorker] Safe autosave in progress...")
            self.status_changed.emit(85, "Creating secure crash-recovery backup...")
            save_to_autosave(report)

            logger.info("[ReportWorker] Report compilation complete.")
            self.status_changed.emit(100, "Finalizing report rendering...")
            self.finished.emit(report)
        except Exception as e:
            logger.error(f"[ReportWorker] Exception during generation: {e}")
            self.error.emit(str(e))

class AsyncExportWorker(QThread):
    """
    Background worker to queue and poll the TrueHour 3.0 asynchronous SQLite pre-aggregation
    and export queue manager. Emits dynamic progress status to the LoadingDialog overlay.
    """
    finished = pyqtSignal(str)  # Emits the exported output path
    error = pyqtSignal(str)
    status_changed = pyqtSignal(int, str)

    def __init__(self, report_type, start_date, end_date, output_path, parent=None):
        super().__init__(parent)
        self.report_type = report_type
        self.start_date = start_date
        self.end_date = end_date
        self.output_path = output_path

    def run(self):
        try:
            from core.reporting.queue import add_report_job, get_report_job
            from core.reporting.models import ReportStatus
            import time

            logger.info(f"[AsyncExportWorker] Starting queue submission for report type: '{self.report_type}'")
            self.status_changed.emit(5, "Submitting export job to queue...")

            job_id = add_report_job(
                report_type=self.report_type,
                start_date=self.start_date,
                end_date=self.end_date,
                output_path=self.output_path
            )

            self.status_changed.emit(10, "Job queued. Waiting for background worker...")

            while True:
                time.sleep(0.5)
                job = get_report_job(job_id)
                if not job:
                    raise Exception("Export job not found in database queue.")

                if job.status == ReportStatus.PENDING:
                    self.status_changed.emit(10, "Job pending in queue...")
                elif job.status == ReportStatus.RUNNING:
                    desc = "Processing export..."
                    if job.progress < 25:
                        desc = "Preparing data and queries..."
                    elif job.progress < 60:
                        desc = "Calculating statistics and pre-aggregation layer..."
                    elif job.progress < 85:
                        desc = "Generating and rendering charts..."
                    else:
                        desc = f"Exporting {self.report_type.upper()} file..."
                    self.status_changed.emit(job.progress, desc)
                elif job.status == ReportStatus.COMPLETE:
                    self.status_changed.emit(100, f"Exported to {self.report_type.upper()} successfully!")
                    self.finished.emit(job.output_path)
                    break
                elif job.status == ReportStatus.FAILED:
                    raise Exception(job.error_message or "Job compilation failed inside background queue.")
        except Exception as e:
            logger.error(f"[AsyncExportWorker] Job failed: {e}")
            self.error.emit(str(e))

