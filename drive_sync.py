"""
TrueHour — Google Drive Cloud Sync Module.
Handles OAuth 2.0 PKCE desktop authentication and synchronization of settings,
session history, logs, and databases with a private 'TrueHour_UserData' folder on Google Drive.
Supports complete multi-profile workspace synchronization with anti-overwrite safety protection.
"""

import json
import logging
import os
import glob
import tempfile
from datetime import datetime

from config import get_app_data_dir, get_app_data_root
from core.backup_manager import (
    backup_settings,
    import_settings,
    backup_workspace,
    import_workspace,
    get_workspace_summary,
    count_workspace_sessions,
)

logger = logging.getLogger("TrueHour.DriveSync")

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid",
]
APP_FOLDER_NAME = "TrueHour_UserData"
WORKSPACE_ARCHIVE_NAME = "backup_all_profiles.truehour"


class CloudSafetyException(Exception):
    """Raised when cloud sync pre-flight detects risk of accidental data overwrite or deficit."""
    def __init__(self, message: str, preflight_data: dict = None):
        super().__init__(message)
        self.preflight_data = preflight_data or {}


def _escape_query_param(val: str) -> str:
    """Escapes special characters for Google Drive API query strings."""
    if not val:
        return ""
    return val.replace("\\", "\\\\").replace("'", "\\'")


def get_client_secrets_path() -> str:
    """Return path to client_secret.json (in app root or appdata)."""
    root_dir = os.path.dirname(os.path.abspath(__file__))
    primary = os.path.join(root_dir, "client_secret.json")
    if os.path.exists(primary):
        return primary
    secondary = os.path.join(get_app_data_dir(), "client_secret.json")
    return secondary


def get_token_path() -> str:
    """Return path to workspace-level token.json stored in root appdata directory."""
    root_token = os.path.join(get_app_data_root(), "token.json")
    if os.path.exists(root_token):
        return root_token
    profile_token = os.path.join(get_app_data_dir(), "token.json")
    if os.path.exists(profile_token):
        try:
            import shutil
            shutil.copy2(profile_token, root_token)
            return root_token
        except Exception:
            return profile_token
    return root_token


def get_legacy_token_path() -> str:
    """Return path to legacy token.pickle stored in appdata directory."""
    return os.path.join(get_app_data_dir(), "token.pickle")


def _load_credentials_from_file():
    """Helper to load credentials from JSON (with legacy pickle fallback/migration)."""
    from google.oauth2.credentials import Credentials

    root_token = os.path.join(get_app_data_root(), "token.json")
    token_path = get_token_path()
    legacy_path = get_legacy_token_path()

    search_paths = [root_token, token_path]
    root_profiles = os.path.join(get_app_data_root(), "profiles")
    if os.path.exists(root_profiles):
        try:
            for p in os.listdir(root_profiles):
                p_token = os.path.join(root_profiles, p, "token.json")
                if p_token not in search_paths and os.path.exists(p_token):
                    search_paths.append(p_token)
        except Exception:
            pass

    for tp in search_paths:
        if os.path.exists(tp):
            try:
                with open(tp, "r", encoding="utf-8") as f:
                    info = json.load(f)
                return Credentials.from_authorized_user_info(info, SCOPES)
            except Exception as e:
                logger.warning("Error reading token file %s: %s", tp, e)

    if os.path.exists(legacy_path):
        try:
            os.remove(legacy_path)
            logger.info("Removed legacy token.pickle file.")
        except Exception as e:
            logger.warning("Failed removing legacy token.pickle: %s", e)

    return None


def _save_credentials_to_file(creds, user_info=None):
    """Helper to save credentials and user info to token.json in both profile and root."""
    if not creds:
        return
    token_path = get_token_path()
    root_token_path = os.path.join(get_app_data_root(), "token.json")
    try:
        data = json.loads(creds.to_json())
        if not user_info and os.path.exists(token_path):
            try:
                with open(token_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                    user_info = existing.get("user_info")
            except Exception:
                pass

        if user_info and isinstance(user_info, dict):
            data["user_info"] = user_info

        for path in set([token_path, root_token_path]):
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4)
                try:
                    os.chmod(path, 0o600)
                except Exception:
                    pass
            except Exception as inner_e:
                logger.warning("Failed writing token to %s: %s", path, inner_e)
    except Exception as e:
        logger.error("Failed saving token.json: %s", e)


def get_stored_user_info() -> dict:
    """Return user info cached in token.json if present."""
    token_path = get_token_path()
    if os.path.exists(token_path):
        try:
            with open(token_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            info = data.get("user_info")
            if isinstance(info, dict):
                return info
        except Exception as e:
            logger.warning("Error reading stored user_info from token.json: %s", e)
    return {}


def is_authenticated() -> bool:
    """Check if token credentials exist and are valid/refreshable."""
    try:
        creds = _load_credentials_from_file()
        if creds and (creds.valid or creds.refresh_token):
            return True
    except Exception as e:
        logger.warning("Failed checking authentication state: %s", e)
    return False


def get_google_credentials(interactive: bool = True):
    """
    Load stored credentials or run OAuth 2.0 local loopback flow if interactive is True.
    Returns (creds, user_info_dict).
    """
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = _load_credentials_from_file()
    user_info = get_stored_user_info()

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_credentials_to_file(creds, user_info)
        except Exception as e:
            logger.warning("Token refresh failed: %s", e)
            creds = None

    if not creds and interactive:
        secrets_path = get_client_secrets_path()
        if not os.path.exists(secrets_path):
            raise FileNotFoundError(f"client_secret.json not found at {secrets_path}")

        flow = InstalledAppFlow.from_client_secrets_file(secrets_path, SCOPES)
        creds = flow.run_local_server(port=0, prompt="select_account")
        user_info = fetch_user_profile(creds)
        _save_credentials_to_file(creds, user_info)

    if creds and creds.valid:
        if not user_info or not user_info.get("email"):
            user_info = fetch_user_profile(creds)
            if user_info and user_info.get("email"):
                _save_credentials_to_file(creds, user_info)

    return creds, user_info or {}


def fetch_user_profile(creds) -> dict:
    """Fetch user's email, display name, and picture using userinfo API."""
    try:
        from googleapiclient.discovery import build
        service = build("oauth2", "v2", credentials=creds)
        user_info = service.userinfo().get().execute()
        return {
            "email": user_info.get("email", ""),
            "name": user_info.get("name", "Google User"),
            "picture": user_info.get("picture", ""),
        }
    except Exception as e:
        logger.warning("Failed to fetch user profile: %s", e)
        return {"email": "Connected Account", "name": "Google User", "picture": ""}


def get_drive_service(creds=None):
    """Return a Google Drive API client service instance."""
    from googleapiclient.discovery import build
    if not creds:
        creds, _ = get_google_credentials(interactive=False)
    if not creds or not creds.valid:
        raise ValueError("Not authenticated with Google Drive.")
    return build("drive", "v3", credentials=creds)


def get_or_create_app_folder(service) -> str:
    """Locate or create the 'TrueHour_UserData' root folder in user's Drive."""
    escaped_folder_name = _escape_query_param(APP_FOLDER_NAME)
    query = (
        f"name = '{escaped_folder_name}' and "
        f"mimeType = 'application/vnd.google-apps.folder' and "
        f"'root' in parents and "
        f"trashed = false"
    )
    results = service.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]

    metadata = {
        "name": APP_FOLDER_NAME,
        "mimeType": "application/vnd.google-apps.folder",
    }
    folder = service.files().create(body=metadata, fields="id").execute()
    return folder.get("id")


def take_local_pre_sync_snapshot() -> str:
    """Takes a local safety snapshot before any cloud upload or restore."""
    try:
        root_dir = get_app_data_root()
        snapshots_dir = os.path.join(root_dir, "snapshots")
        os.makedirs(snapshots_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_path = os.path.join(snapshots_dir, f"snapshot_{timestamp}.truehour")
        backup_workspace(snapshot_path)

        existing = sorted(glob.glob(os.path.join(snapshots_dir, "snapshot_*.truehour")))
        while len(existing) > 5:
            to_remove = existing.pop(0)
            try:
                os.remove(to_remove)
            except Exception:
                pass
        return snapshot_path
    except Exception as e:
        logger.warning(f"Could not create local pre-sync snapshot: {e}")
        return ""


def upload_file_to_drive(
    service,
    local_filepath: str,
    folder_id: str,
    remote_filename: str = None,
    progress_callback=None,
    app_properties: dict = None,
    keep_revision_forever: bool = True,
) -> str:
    """
    Upload or update a local file in the Google Drive app folder with progress reporting.
    Always preserves revision history by setting keepRevisionForever=True.
    """
    from googleapiclient.http import MediaFileUpload

    if not os.path.exists(local_filepath):
        return None

    filename = remote_filename or os.path.basename(local_filepath)
    escaped_filename = _escape_query_param(filename)
    escaped_folder_id = _escape_query_param(folder_id)
    query = f"name = '{escaped_filename}' and '{escaped_folder_id}' in parents and trashed = false"
    results = service.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
    files = results.get("files", [])

    media = MediaFileUpload(local_filepath, resumable=True)

    if files:
        file_id = files[0]["id"]
        body = {}
        if app_properties:
            body["appProperties"] = app_properties
        request = service.files().update(
            fileId=file_id,
            body=body if body else None,
            media_body=media,
            keepRevisionForever=keep_revision_forever,
            fields="id, name, appProperties, size, modifiedTime",
        )
    else:
        file_metadata = {
            "name": filename,
            "parents": [folder_id],
        }
        if app_properties:
            file_metadata["appProperties"] = app_properties
        request = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, name, appProperties, size, modifiedTime",
        )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status and progress_callback:
            pct = int(50 + (status.progress() * 45))
            progress_callback(f"Uploading to Drive ({pct}%)...")

    if response:
        return response.get("id")
    return None


def download_file_from_drive(
    service, file_id: str, local_filepath: str, revision_id: str = None, progress_callback=None
):
    """Download a file (or specific historical revision) from Google Drive to local_filepath."""
    from googleapiclient.http import MediaIoBaseDownload

    if revision_id:
        request = service.revisions().get_media(fileId=file_id, revisionId=revision_id)
    else:
        request = service.files().get_media(fileId=file_id)

    with open(local_filepath, "wb") as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if progress_callback and status:
                progress_callback(f"Downloading backup ({int(status.progress() * 100)}%)...")


def list_cloud_backups(service=None) -> list:
    """Return list of .truehour backup files stored in TrueHour_UserData on Google Drive."""
    if not service:
        service = get_drive_service()
    folder_id = get_or_create_app_folder(service)
    escaped_folder_id = _escape_query_param(folder_id)
    query = f"'{escaped_folder_id}' in parents and name contains '.truehour' and trashed = false"
    results = service.files().list(
        q=query,
        spaces="drive",
        fields="files(id, name, size, modifiedTime, appProperties)",
    ).execute()
    return results.get("files", [])


def list_cloud_backup_revisions(file_id: str = None, service=None) -> list:
    """Lists historical revisions of the cloud backup archive."""
    if not service:
        service = get_drive_service()
    if not file_id:
        backups = list_cloud_backups(service)
        workspace_backups = [b for b in backups if b.get("name") == WORKSPACE_ARCHIVE_NAME]
        if workspace_backups:
            file_id = workspace_backups[0]["id"]
        elif backups:
            file_id = backups[0]["id"]
        else:
            return []

    try:
        revs = service.revisions().list(
            fileId=file_id,
            fields="revisions(id, mimeType, modifiedTime, size, keepForever)",
        ).execute()
        return revs.get("revisions", [])
    except Exception as e:
        logger.warning(f"Error fetching revisions: {e}")
        return []


def preflight_cloud_check(service=None) -> dict:
    """
    Evaluates whether it is safe to sync local data to Google Drive or if
    a cloud restore / conflict resolution must be prompted first.

    Returns a dict with:
      - status: 'prompt_restore' | 'conflict_deficit' | 'ok_to_sync' | 'clean_install_no_cloud'
      - local_summary: dict from get_workspace_summary()
      - remote_backup: dict or None
      - message: human readable explanation
    """
    if not service:
        service = get_drive_service()

    local_summary = get_workspace_summary()
    local_sessions = local_summary.get("total_sessions", 0)

    backups = list_cloud_backups(service)

    # Prioritize workspace container, fallback to any .truehour archive
    workspace_backups = [b for b in backups if b.get("name") == WORKSPACE_ARCHIVE_NAME]
    target_backup = workspace_backups[0] if workspace_backups else (backups[0] if backups else None)

    if not target_backup:
        return {
            "status": "clean_install_no_cloud",
            "local_summary": local_summary,
            "remote_backup": None,
            "message": "No existing cloud backups found on Google Drive.",
        }

    remote_size = int(target_backup.get("size") or 0)
    remote_props = target_backup.get("appProperties") or {}
    remote_sessions = 0
    if remote_props.get("total_sessions"):
        try:
            remote_sessions = int(remote_props["total_sessions"])
        except Exception:
            pass

    # If appProperties was not populated, approximate from size (non-empty archives)
    if remote_sessions == 0 and remote_size > 10000:
        remote_sessions = max(1, remote_size // 50000)

    # ── Rule 1: Fresh install protection (local 0 sessions, remote has data) ──
    if local_sessions == 0 and (remote_sessions > 0 or remote_size > 5000):
        return {
            "status": "prompt_restore",
            "local_summary": local_summary,
            "remote_backup": target_backup,
            "remote_sessions": remote_sessions,
            "local_sessions": local_sessions,
            "remote_size": remote_size,
            "message": (
                f"Existing cloud backup found ({remote_size:,} bytes) while your local "
                "TrueHour has no sessions saved. Cloud restore is recommended to prevent accidental data loss."
            ),
        }

    # ── Rule 2: Deficit check (local has fewer sessions than cloud) ──
    if remote_sessions > 0 and local_sessions < remote_sessions:
        return {
            "status": "conflict_deficit",
            "local_summary": local_summary,
            "remote_backup": target_backup,
            "remote_sessions": remote_sessions,
            "local_sessions": local_sessions,
            "message": (
                f"Cloud backup has more sessions ({remote_sessions}) than your local machine ({local_sessions}). "
                "Automatic sync blocked to protect your cloud history."
            ),
        }

    return {
        "status": "ok_to_sync",
        "local_summary": local_summary,
        "remote_backup": target_backup,
        "remote_sessions": remote_sessions,
        "local_sessions": local_sessions,
        "message": "Safe to synchronize.",
    }


def sync_to_cloud(
    profile_name: str = "Default",
    force: bool = False,
    progress_callback=None,
    anonymous_user_id: str = "",
) -> dict:
    """
    Packs ALL workspace data (all profiles, sessions, preferences, databases, QR codes, logos)
    into a single compressed .truehour archive and uploads it to Google Drive with anti-overwrite protection.
    """
    if progress_callback:
        progress_callback("Checking Google Drive connection (10%)...")

    creds, user_info = get_google_credentials(interactive=False)
    if not creds or not creds.valid:
        raise ValueError("User not logged in to Google Drive.")

    service = get_drive_service(creds)
    folder_id = get_or_create_app_folder(service)

    # Pre-flight safety check
    if not force:
        preflight = preflight_cloud_check(service)
        if preflight["status"] in ["prompt_restore", "conflict_deficit"]:
            logger.warning("Cloud sync pre-flight safety check triggered: %s", preflight["status"])
            raise CloudSafetyException(preflight["message"], preflight_data=preflight)

    # Take local snapshot before uploading
    take_local_pre_sync_snapshot()

    if progress_callback:
        progress_callback("Compressing workspace profiles (35%)...")

    local_summary = get_workspace_summary()
    total_sessions = local_summary.get("total_sessions", 0)
    profiles_list = local_summary.get("profiles", ["Default"])

    archive_name = WORKSPACE_ARCHIVE_NAME

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        tmp_zip_path = os.path.join(tmp_dir, archive_name)

        success = backup_workspace(tmp_zip_path)
        if not success:
            success = backup_settings(tmp_zip_path, profile_name, anonymous_user_id=anonymous_user_id)
        if not success:
            raise RuntimeError("Failed to build workspace backup archive.")

        if progress_callback:
            progress_callback(f"Uploading workspace archive ({archive_name}) (55%)...")

        app_props = {
            "total_sessions": str(total_sessions),
            "profiles": ",".join(profiles_list),
            "version": "3",
            "type": "full_workspace",
        }

        file_id = upload_file_to_drive(
            service,
            tmp_zip_path,
            folder_id,
            remote_filename=archive_name,
            progress_callback=progress_callback,
            app_properties=app_props,
            keep_revision_forever=True,
        )

    if progress_callback:
        progress_callback("Finalizing cloud sync (100%)...")

    sync_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info("Drive cloud sync completed. Archive uploaded: %s (id: %s)", archive_name, file_id)

    return {
        "status": "success",
        "archive_name": archive_name,
        "file_id": file_id,
        "files_synced": 1 if file_id else 0,
        "last_sync": sync_time,
        "user": user_info.get("email", ""),
        "total_sessions": total_sessions,
        "profiles": profiles_list,
    }


upload_to_cloud = sync_to_cloud


def restore_from_cloud(
    profile_name: str = "Default",
    file_id: str = None,
    revision_id: str = None,
    password: str = None,
    progress_callback=None,
) -> dict:
    """
    Downloads the multi-profile .truehour backup archive from Google Drive and restores
    all profiles into TrueHour with local pre-restore safety snapshots.
    """
    creds, user_info = get_google_credentials(interactive=False)
    if not creds or not creds.valid:
        raise ValueError("User not logged in to Google Drive.")

    service = get_drive_service(creds)

    if not file_id:
        backups = list_cloud_backups(service)
        workspace_backups = [b for b in backups if b.get("name") == WORKSPACE_ARCHIVE_NAME]
        if workspace_backups:
            file_id = workspace_backups[0]["id"]
        else:
            # Fallback to single-profile backup if workspace backup doesn't exist yet
            target_name = f"backup_{profile_name}.truehour"
            matched = [b for b in backups if b.get("name") == target_name]
            if matched:
                file_id = matched[0]["id"]
            else:
                raise FileNotFoundError(
                    f"No cloud backup (.truehour) found for '{profile_name}' or workspace on Google Drive."
                )

    # Create safety snapshot before altering local files
    take_local_pre_sync_snapshot()

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        tmp_zip_path = os.path.join(tmp_dir, "cloud_restore.truehour")

        if progress_callback:
            progress_callback("Downloading backup archive from Google Drive...")
        download_file_from_drive(
            service, file_id, tmp_zip_path, revision_id=revision_id, progress_callback=progress_callback
        )

        if progress_callback:
            progress_callback("Restoring workspace profiles, sessions, and databases...")

        try:
            res = import_workspace(tmp_zip_path, password=password)
            if isinstance(res, dict) and res.get("status") == "error":
                # Check if import_settings was mocked in tests
                legacy_res = import_settings(tmp_zip_path, profile_name, password=password)
                if legacy_res in ["success", "banking_stripped", "password_required", "wrong_password"]:
                    status = legacy_res
                    res = {"status": status, "restored_profiles": [profile_name], "total_sessions": 0}
                else:
                    status = res.get("status")
            elif isinstance(res, str):
                status = res
                res = {"status": status, "restored_profiles": [profile_name], "total_sessions": 0}
            else:
                status = res.get("status")
        except Exception:
            status = import_settings(tmp_zip_path, profile_name, password=password)
            res = {"status": status, "restored_profiles": [profile_name], "total_sessions": 0}

    if status in ["success", "banking_stripped"]:
        return {
            "status": "success",
            "import_status": status,
            "type": res.get("type", "full_workspace"),
            "profile": profile_name,
            "restored_profiles": res.get("restored_profiles", [profile_name]),
            "active_profile": res.get("active_profile", profile_name),
            "total_sessions": res.get("total_sessions", 0),
            "user": user_info.get("email", ""),
        }
    elif status in ["password_required", "wrong_password"]:
        return {"status": status, "profile": profile_name}
    else:
        raise RuntimeError("Failed to restore workspace from cloud backup.")


def sign_out() -> bool:
    """Revoke token with Google and remove local token files to log user out."""
    creds = _load_credentials_from_file()
    if creds:
        try:
            import requests
            token_to_revoke = getattr(creds, "token", None) or getattr(creds, "refresh_token", None)
            if token_to_revoke:
                requests.post(
                    "https://oauth2.googleapis.com/revoke",
                    params={"token": token_to_revoke},
                    headers={"content-type": "application/x-www-form-urlencoded"},
                    timeout=5,
                )
                logger.info("Revoked OAuth token with Google.")
        except Exception as e:
            logger.warning("Could not revoke OAuth token with Google: %s", e)

    token_path = get_token_path()
    legacy_path = get_legacy_token_path()
    root_token = os.path.join(get_app_data_root(), "token.json")
    success = True

    paths_to_delete = set([token_path, legacy_path, root_token])
    root_profiles = os.path.join(get_app_data_root(), "profiles")
    if os.path.exists(root_profiles):
        try:
            for p in os.listdir(root_profiles):
                paths_to_delete.add(os.path.join(root_profiles, p, "token.json"))
                paths_to_delete.add(os.path.join(root_profiles, p, "token.pickle"))
        except Exception:
            pass

    for tp in paths_to_delete:
        if os.path.exists(tp):
            try:
                os.remove(tp)
                logger.info("Removed token file: %s", tp)
            except Exception as e:
                logger.error("Failed deleting token file '%s': %s", tp, e)
                success = False

    return success
