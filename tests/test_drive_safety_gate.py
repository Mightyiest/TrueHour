import pytest
from unittest.mock import MagicMock, patch

import drive_sync
from drive_sync import CloudSafetyException, preflight_cloud_check, WORKSPACE_ARCHIVE_NAME


class DummyCreds:
    def __init__(self, valid=True, refresh_token="token"):
        self.valid = valid
        self.refresh_token = refresh_token

    def to_json(self):
        return '{"token": "mock", "refresh_token": "token"}'


def test_safety_gate_blocks_upload_when_local_empty_and_cloud_has_sessions():
    mock_service = MagicMock()
    # Cloud backup has 65 sessions and 43MB size
    mock_service.files().list().execute.return_value = {
        "files": [{
            "id": "cloud_file_1",
            "name": WORKSPACE_ARCHIVE_NAME,
            "size": "45000000",
            "appProperties": {"total_sessions": "65", "profiles": "Default,Mightyiest"},
        }]
    }

    # Local workspace has 0 sessions
    local_summary = {
        "active_profile": "Default",
        "profiles": ["Default"],
        "total_sessions": 0,
        "sessions_by_profile": {"Default": 0},
    }

    with patch("drive_sync.get_workspace_summary", return_value=local_summary), \
         patch("drive_sync.get_or_create_app_folder", return_value="folder_1"):

        check = preflight_cloud_check(mock_service)
        assert check["status"] == "prompt_restore"
        assert check["remote_sessions"] == 65
        assert check["local_sessions"] == 0

        # Now verify sync_to_cloud raises CloudSafetyException when not forced
        mock_creds = DummyCreds(valid=True)
        with patch("drive_sync.get_google_credentials", return_value=(mock_creds, {"email": "test@gmail.com"})), \
             patch("drive_sync.get_drive_service", return_value=mock_service):

            with pytest.raises(CloudSafetyException) as exc_info:
                drive_sync.sync_to_cloud(force=False)

            assert "Cloud restore is recommended" in str(exc_info.value)
            assert exc_info.value.preflight_data["status"] == "prompt_restore"


def test_safety_gate_blocks_upload_on_session_deficit():
    mock_service = MagicMock()
    mock_service.files().list().execute.return_value = {
        "files": [{
            "id": "cloud_file_1",
            "name": WORKSPACE_ARCHIVE_NAME,
            "size": "45000000",
            "appProperties": {"total_sessions": "65", "profiles": "Default,Mightyiest"},
        }]
    }

    # Local workspace has 5 sessions (less than 65 in cloud)
    local_summary = {
        "active_profile": "Mightyiest",
        "profiles": ["Default", "Mightyiest"],
        "total_sessions": 5,
        "sessions_by_profile": {"Default": 2, "Mightyiest": 3},
    }

    with patch("drive_sync.get_workspace_summary", return_value=local_summary), \
         patch("drive_sync.get_or_create_app_folder", return_value="folder_1"):

        check = preflight_cloud_check(mock_service)
        assert check["status"] == "conflict_deficit"
        assert check["remote_sessions"] == 65
        assert check["local_sessions"] == 5

        mock_creds = DummyCreds(valid=True)
        with patch("drive_sync.get_google_credentials", return_value=(mock_creds, {"email": "test@gmail.com"})), \
             patch("drive_sync.get_drive_service", return_value=mock_service):

            with pytest.raises(CloudSafetyException) as exc_info:
                drive_sync.sync_to_cloud(force=False)

            assert "Cloud backup has more sessions" in str(exc_info.value)
            assert exc_info.value.preflight_data["status"] == "conflict_deficit"


def test_safety_gate_allows_upload_when_local_has_more_or_equal_sessions():
    mock_service = MagicMock()
    mock_service.files().list().execute.return_value = {
        "files": [{
            "id": "cloud_file_1",
            "name": WORKSPACE_ARCHIVE_NAME,
            "size": "45000000",
            "appProperties": {"total_sessions": "65", "profiles": "Default,Mightyiest"},
        }]
    }

    # Local workspace has 66 sessions (newer/more data)
    local_summary = {
        "active_profile": "Mightyiest",
        "profiles": ["Default", "Mightyiest"],
        "total_sessions": 66,
        "sessions_by_profile": {"Default": 2, "Mightyiest": 64},
    }

    with patch("drive_sync.get_workspace_summary", return_value=local_summary), \
         patch("drive_sync.get_or_create_app_folder", return_value="folder_1"):

        check = preflight_cloud_check(mock_service)
        assert check["status"] == "ok_to_sync"


def test_force_sync_bypasses_safety_gate():
    mock_service = MagicMock()
    mock_service.files().list().execute.return_value = {
        "files": [{
            "id": "cloud_file_1",
            "name": WORKSPACE_ARCHIVE_NAME,
            "size": "45000000",
            "appProperties": {"total_sessions": "65", "profiles": "Default,Mightyiest"},
        }]
    }

    # Local has 0 sessions
    local_summary = {
        "active_profile": "Default",
        "profiles": ["Default"],
        "total_sessions": 0,
        "sessions_by_profile": {"Default": 0},
    }

    mock_creds = DummyCreds(valid=True)
    with patch("drive_sync.get_workspace_summary", return_value=local_summary), \
         patch("drive_sync.get_or_create_app_folder", return_value="folder_1"), \
         patch("drive_sync.get_google_credentials", return_value=(mock_creds, {"email": "test@gmail.com"})), \
         patch("drive_sync.get_drive_service", return_value=mock_service), \
         patch("drive_sync.backup_workspace", return_value=True), \
         patch("drive_sync.upload_file_to_drive", return_value="file_id_force"):

        res = drive_sync.sync_to_cloud(force=True)
        assert res["status"] == "success"
        assert res["file_id"] == "file_id_force"
