import threading
import uuid
from datetime import datetime
from queue import Queue
from contextlib import contextmanager
from database.schema import get_connection
from core.reporting.models import ReportJob, ReportStatus


@contextmanager
def db_session():
    conn = get_connection()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


report_queue = Queue()


def add_report_job(
    report_type: str, start_date: str, end_date: str, output_path: str = None
) -> str:
    job_id = str(uuid.uuid4())
    created_at = datetime.now().isoformat()

    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO report_jobs (id, status, progress, report_type, start_date, end_date, output_path, error_message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                job_id,
                ReportStatus.PENDING,
                0,
                report_type,
                start_date,
                end_date,
                output_path,
                None,
                created_at,
            ),
        )

    report_queue.put(job_id)
    return job_id


def get_report_job(job_id: str) -> ReportJob | None:
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, status, progress, report_type, start_date, end_date, output_path, error_message
            FROM report_jobs WHERE id = ?
        """,
            (job_id,),
        )
        row = cursor.fetchone()
        if row:
            return ReportJob(
                id=row["id"],
                status=row["status"],
                progress=row["progress"],
                report_type=row["report_type"],
                start_date=row["start_date"],
                end_date=row["end_date"],
                output_path=row["output_path"],
                error_message=row["error_message"],
            )
    return None


def update_job(
    job_id: str,
    status: str,
    progress: int,
    error_message: str = None,
    output_path: str = None,
):
    with db_session() as conn:
        cursor = conn.cursor()
        completed_at = (
            datetime.now().isoformat()
            if status in (ReportStatus.COMPLETE, ReportStatus.FAILED)
            else None
        )

        if output_path is not None:
            cursor.execute(
                """
                UPDATE report_jobs
                SET status = ?, progress = ?, error_message = ?, output_path = ?, completed_at = ?
                WHERE id = ?
            """,
                (status, progress, error_message, output_path, completed_at, job_id),
            )
        else:
            cursor.execute(
                """
                UPDATE report_jobs
                SET status = ?, progress = ?, error_message = ?, completed_at = ?
                WHERE id = ?
            """,
                (status, progress, error_message, completed_at, job_id),
            )


def process_reports():
    # Import builder dynamically to avoid circular references
    from core.reporting.builder import generate_report

    while True:
        job_id = report_queue.get()
        if job_id is None:
            break

        try:
            update_job(job_id, ReportStatus.RUNNING, 5)
            generate_report(job_id)
        except Exception as e:
            import traceback

            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            update_job(job_id, ReportStatus.FAILED, 100, error_message=error_msg)
        finally:
            report_queue.task_done()


# Start background worker thread unless running under unit test environment
import sys

if not any(mod in sys.modules for mod in ("pytest", "unittest", "_pytest")):
    worker_thread = threading.Thread(target=process_reports, daemon=True)
    worker_thread.start()
else:
    worker_thread = None
