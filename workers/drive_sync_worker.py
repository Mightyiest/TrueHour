"""
TrueHour — Google Drive Async Workers (PyQt6 QThread).
Executes OAuth authentication, workspace cloud upload, restore, pre-flight checks,
and revision inspection in background threads to keep the main application UI fluid and responsive.
"""

import logging
from PyQt6.QtCore import QThread, pyqtSignal

import drive_sync

logger = logging.getLogger("TrueHour.DriveSyncWorker")


class BaseDriveWorker(QThread):
    """Base background worker providing common progress signaling for Drive tasks."""
    progress = pyqtSignal(str)

    def _emit_progress(self, msg: str):
        self.progress.emit(msg)


class DriveAuthWorker(QThread):
    """Background worker for interactive Google OAuth 2.0 PKCE browser login."""
    # Signal arguments: (success: bool, user_info: dict, error_message: str)
    finished = pyqtSignal(bool, dict, str)

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        try:
            creds, user_info = drive_sync.get_google_credentials(interactive=True)
            if creds and creds.valid:
                self.finished.emit(True, user_info, "")
            else:
                self.finished.emit(False, {}, "Authentication failed or cancelled.")
        except Exception as e:
            logger.error("DriveAuthWorker error: %s", e, exc_info=True)
            self.finished.emit(False, {}, str(e))


class DrivePreflightWorker(BaseDriveWorker):
    """Background worker to check cloud backup status and detect conflicts before syncing."""
    # Signal arguments: (success: bool, preflight_data: dict, error_message: str)
    finished = pyqtSignal(bool, dict, str)

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        try:
            self._emit_progress("Checking cloud backup status...")
            result = drive_sync.preflight_cloud_check()
            self.finished.emit(True, result, "")
        except Exception as e:
            logger.error("DrivePreflightWorker error: %s", e, exc_info=True)
            self.finished.emit(False, {}, str(e))


class DriveSyncWorker(BaseDriveWorker):
    """Background worker for Google Drive workspace cloud sync with anti-overwrite protection."""
    # Signal arguments: (success: bool, result_dict: dict, error_message: str)
    finished = pyqtSignal(bool, dict, str)
    safety_blocked = pyqtSignal(dict)

    def __init__(self, profile_name: str = "Default", force: bool = False, parent=None):
        super().__init__(parent)
        self.profile_name = profile_name
        self.force = force

    def run(self):
        try:
            result = drive_sync.sync_to_cloud(
                profile_name=self.profile_name,
                force=self.force,
                progress_callback=self._emit_progress,
            )
            status = result.get("status") if isinstance(result, dict) else None
            if status == "error":
                self.finished.emit(False, result, "Cloud sync failed.")
            else:
                self.finished.emit(True, result, "")
        except drive_sync.CloudSafetyException as cse:
            logger.warning("DriveSyncWorker halted by safety gate: %s", cse)
            self.safety_blocked.emit(cse.preflight_data)
        except Exception as e:
            logger.error("DriveSyncWorker error: %s", e, exc_info=True)
            self.finished.emit(False, {}, str(e))


class DriveRestoreWorker(BaseDriveWorker):
    """Background worker for restoring workspace from Google Drive .truehour archive."""
    # Signal arguments: (success: bool, result_dict: dict, error_message: str)
    finished = pyqtSignal(bool, dict, str)

    def __init__(
        self,
        profile_name: str = "Default",
        file_id: str = None,
        revision_id: str = None,
        password: str = None,
        parent=None,
    ):
        super().__init__(parent)
        self.profile_name = profile_name
        self.file_id = file_id
        self.revision_id = revision_id
        self.password = password

    def run(self):
        try:
            result = drive_sync.restore_from_cloud(
                profile_name=self.profile_name,
                file_id=self.file_id,
                revision_id=self.revision_id,
                password=self.password,
                progress_callback=self._emit_progress,
            )
            status = result.get("status") if isinstance(result, dict) else None
            if status in ["password_required", "wrong_password", "error"]:
                err_msg = (
                    "Password required to restore encrypted backup."
                    if status == "password_required"
                    else ("Incorrect password provided." if status == "wrong_password" else "Restore failed.")
                )
                self.finished.emit(False, result, err_msg)
            else:
                self.finished.emit(True, result, "")
        except Exception as e:
            logger.error("DriveRestoreWorker error: %s", e, exc_info=True)
            self.finished.emit(False, {}, str(e))


class DriveRevisionsWorker(BaseDriveWorker):
    """Background worker to fetch list of historical revisions for cloud backup rollback."""
    # Signal arguments: (success: bool, revisions_list: list, error_message: str)
    finished = pyqtSignal(bool, list, str)

    def __init__(self, file_id: str = None, parent=None):
        super().__init__(parent)
        self.file_id = file_id

    def run(self):
        try:
            self._emit_progress("Fetching cloud backup revision history...")
            revisions = drive_sync.list_cloud_backup_revisions(file_id=self.file_id)
            self.finished.emit(True, revisions, "")
        except Exception as e:
            logger.error("DriveRevisionsWorker error: %s", e, exc_info=True)
            self.finished.emit(False, [], str(e))
