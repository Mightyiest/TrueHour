from dataclasses import dataclass


class ReportStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class ReportJob:
    id: str
    status: str
    progress: int
    report_type: str
    start_date: str
    end_date: str
    output_path: str | None
    error_message: str | None
