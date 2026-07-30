"""
TrueHour — Google Drive Cloud Sync Module.
Handles OAuth 2.0 PKCE desktop authentication and synchronization of settings,
session history, and logs with a private 'TrueHour_UserData' folder on Google Drive.
"""

import io
import json
import logging
import os
import pickle
import tempfile
from datetime import datetime

from config import get_app_data_dir, get_app_data_root
from core.backup_manager import backup_settings, import_settings

logger = logging.getLogger("TrueHour.DriveSync")

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid",
]
APP_FOLDER_NAME = "TrueHour_UserData"


def get_client_secrets_path() -> str:
    """Return path to client_secret.json (in app root or appdata)."""
    root_dir = os.path.dirname(os.path.abspath(__file__))
    primary = os.path.join(root_dir, "client_secret.json")
    if os.path.exists(primary):
        return primary
    secondary = os.path.join(get_app_data_dir(), "client_secret.json")
    return secondary


def get_token_path() -> str:
    """Return path to token.pickle stored in appdata directory."""
    return os.path.join(get_app_data_dir(), "token.pickle")


def is_authenticated() -> bool:
    """Check if token.pickle exists and contains valid/refreshable credentials."""
    token_path = get_token_path()
    if not os.path.exists(token_path):
        return False
    try:
        with open(token_path, "rb") as f:
            creds = pickle.load(f)
        if creds and (creds.valid or creds.refresh_token):
            return True
    except Exception as e:
        logger.warning("Failed reading token.pickle: %s", e)
    return False


def get_google_credentials(interactive: bool = True):
    """
    Load stored credentials or run OAuth 2.0 local loopback flow if interactive is True.
    Returns (creds, user_info_dict).
    """
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow

    token_path = get_token_path()
    creds = None

    if os.path.exists(token_path):
        try:
            with open(token_path, "rb") as f:
                creds = pickle.load(f)
        except Exception as e:
            logger.warning("Error reading existing token file: %s", e)
            creds = None

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(token_path, "wb") as f:
                pickle.dump(creds, f)
        except Exception as e:
            logger.warning("Token refresh failed: %s", e)
            creds = None

    if not creds and interactive:
        secrets_path = get_client_secrets_path()
        if not os.path.exists(secrets_path):
            raise FileNotFoundError(f"client_secret.json not found at {secrets_path}")

        flow = InstalledAppFlow.from_client_secrets_file(secrets_path, SCOPES)
        creds = flow.run_local_server(port=0, prompt="select_account")
        with open(token_path, "wb") as f:
            pickle.dump(creds, f)

    user_info = {}
    if creds and creds.valid:
        user_info = fetch_user_profile(creds)

    return creds, user_info


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
    query = (
        f"name = '{APP_FOLDER_NAME}' and "
        f"mimeType = 'application/vnd.google-apps.folder' and "
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


def upload_file_to_drive(service, local_filepath: str, folder_id: str, remote_filename: str = None) -> str:
    """Upload or update a local file in the Google Drive app folder."""
    from googleapiclient.http import MediaFileUpload

    if not os.path.exists(local_filepath):
        return None

    filename = remote_filename or os.path.basename(local_filepath)
    query = f"name = '{filename}' and '{folder_id}' in parents and trashed = false"
    results = service.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
    files = results.get("files", [])

    media = MediaFileUpload(local_filepath, resumable=True)

    if files:
        file_id = files[0]["id"]
        updated = service.files().update(fileId=file_id, media_body=media).execute()
        return updated.get("id")
    else:
        file_metadata = {
            "name": filename,
            "parents": [folder_id],
        }
        created = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
        return created.get("id")


def download_file_from_drive(service, file_id: str, local_filepath: str, progress_callback=None):
    """Download a file from Google Drive to local_filepath."""
    from googleapiclient.http import MediaIoBaseDownload

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
    query = f"'{folder_id}' in parents and name contains '.truehour' and trashed = false"
    results = service.files().list(
        q=query,
        spaces="drive",
        fields="files(id, name, size, modifiedTime)"
    ).execute()
    return results.get("files", [])


def sync_to_cloud(profile_name: str = "Default", progress_callback=None) -> dict:
    """
    Packs all profile data (settings, active sessions, history, QR codes, logos, logs, database)
    into a single compressed .truehour archive using backup_manager and uploads it to Google Drive.
    """
    creds, user_info = get_google_credentials(interactive=False)
    if not creds or not creds.valid:
        raise ValueError("User not logged in to Google Drive.")

    service = get_drive_service(creds)
    folder_id = get_or_create_app_folder(service)

    if progress_callback:
        progress_callback(f"Compressing profile data for '{profile_name}'...")

    with tempfile.TemporaryDirectory() as tmp_dir:
        archive_name = f"backup_{profile_name}.truehour"
        tmp_zip_path = os.path.join(tmp_dir, archive_name)

        success = backup_settings(tmp_zip_path, profile_name)
        if not success:
            raise RuntimeError(f"Failed to build local backup archive for profile '{profile_name}'.")

        if progress_callback:
            progress_callback(f"Uploading single archive ({archive_name}) to Google Drive...")

        file_id = upload_file_to_drive(service, tmp_zip_path, folder_id, remote_filename=archive_name)

    sync_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info("Drive cloud sync completed. Archive uploaded: %s (id: %s)", archive_name, file_id)

    return {
        "status": "success",
        "archive_name": archive_name,
        "file_id": file_id,
        "files_synced": 1,
        "last_sync": sync_time,
        "user": user_info.get("email", ""),
    }


def restore_from_cloud(profile_name: str = "Default", file_id: str = None, password: str = None, progress_callback=None) -> dict:
    """
    Downloads the single .truehour backup archive from Google Drive and restores it into TrueHour.
    """
    creds, user_info = get_google_credentials(interactive=False)
    if not creds or not creds.valid:
        raise ValueError("User not logged in to Google Drive.")

    service = get_drive_service(creds)

    if not file_id:
        backups = list_cloud_backups(service)
        target_name = f"backup_{profile_name}.truehour"
        matched = [b for b in backups if b.get("name") == target_name]
        if matched:
            file_id = matched[0]["id"]
        elif backups:
            file_id = backups[0]["id"]
        else:
            raise FileNotFoundError("No cloud backup (.truehour) found in TrueHour_UserData on Google Drive.")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_zip_path = os.path.join(tmp_dir, "cloud_restore.truehour")

        if progress_callback:
            progress_callback("Downloading backup archive from Google Drive...")
        download_file_from_drive(service, file_id, tmp_zip_path, progress_callback)

        if progress_callback:
            progress_callback("Restoring settings, sessions, and assets...")
        status = import_settings(tmp_zip_path, profile_name, password=password)

    if status in ["success", "banking_stripped"]:
        return {
            "status": "success",
            "import_status": status,
            "profile": profile_name,
            "user": user_info.get("email", ""),
        }
    elif status in ["password_required", "wrong_password"]:
        return {"status": status, "profile": profile_name}
    else:
        raise RuntimeError("Failed to restore profile from cloud backup.")


def sign_out() -> bool:
    """Remove local token.pickle file to log user out."""
    token_path = get_token_path()
    if os.path.exists(token_path):
        try:
            os.remove(token_path)
            logger.info("Removed Google OAuth token file.")
            return True
        except Exception as e:
            logger.error("Failed deleting token file: %s", e)
            return False
    return True
