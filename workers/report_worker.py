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

