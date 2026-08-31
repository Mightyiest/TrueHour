"""
Unit tests for TrueHour Google Drive Sync engine (drive_sync.py).
"""

import os
import pickle
import pytest
from unittest.mock import MagicMock, patch

import drive_sync


def test_get_client_secrets_path():
    path = drive_sync.get_client_secrets_path()
    assert os.path.exists(path)
    assert path.endswith("client_secret.json")


def test_is_authenticated_false_when_missing(tmp_path):
    with patch("drive_sync.get_token_path", return_value=str(tmp_path / "nonexistent.json")), \
         patch("drive_sync.get_legacy_token_path", return_value=str(tmp_path / "nonexistent.pickle")), \
         patch("drive_sync.get_app_data_root", return_value=str(tmp_path)):
        assert drive_sync.is_authenticated() is False


class DummyCreds:
    def __init__(self, valid=True, refresh_token="token"):
        self.valid = valid
        self.refresh_token = refresh_token

    def to_json(self):
        return '{"token": "mock", "refresh_token": "token"}'


def test_is_authenticated_true_when_valid(tmp_path):
    token_file = tmp_path / "token.json"
    token_file.write_text('{"token": "mock", "refresh_token": "token"}')

    with patch("drive_sync.get_token_path", return_value=str(token_file)), \
         patch("drive_sync.get_legacy_token_path", return_value=str(tmp_path / "nonexistent.pickle")), \
         patch("google.oauth2.credentials.Credentials.from_authorized_user_info", return_value=DummyCreds(valid=True)):
        assert drive_sync.is_authenticated() is True


def test_sign_out(tmp_path):
    token_file = tmp_path / "token.json"
    token_file.write_text("mock token data")

    with patch("drive_sync.get_token_path", return_value=str(token_file)), \
         patch("drive_sync.get_legacy_token_path", return_value=str(tmp_path / "nonexistent.pickle")), \
         patch("drive_sync.get_app_data_root", return_value=str(tmp_path)):
        assert os.path.exists(str(token_file))
        result = drive_sync.sign_out()
        assert result is True
        assert not os.path.exists(str(token_file))


def test_sync_to_cloud_not_authenticated():
    with patch("drive_sync.get_google_credentials", return_value=(None, {})):
        with pytest.raises(ValueError, match="User not logged in"):
            drive_sync.sync_to_cloud()


def test_sync_to_cloud_single_archive():
    mock_creds = DummyCreds(valid=True)
    mock_service = MagicMock()

    with patch("drive_sync.get_google_credentials", return_value=(mock_creds, {"email": "test@gmail.com"})), \
         patch("drive_sync.get_drive_service", return_value=mock_service), \
         patch("drive_sync.get_or_create_app_folder", return_value="folder_id_999"), \
         patch("drive_sync.backup_settings", return_value=True) as mock_backup, \
         patch("drive_sync.upload_file_to_drive", return_value="file_id_123") as mock_upload:

        res = drive_sync.sync_to_cloud(profile_name="Default")
        assert res["status"] == "success"
        assert res["archive_name"] == "backup_Default.truehour"
        assert res["file_id"] == "file_id_123"

        mock_backup.assert_called_once()
        mock_upload.assert_called_once()


def test_restore_from_cloud():
    mock_creds = DummyCreds(valid=True)
    mock_service = MagicMock()

    with patch("drive_sync.get_google_credentials", return_value=(mock_creds, {"email": "test@gmail.com"})), \
         patch("drive_sync.get_drive_service", return_value=mock_service), \
         patch("drive_sync.download_file_from_drive") as mock_download, \
         patch("drive_sync.import_settings", return_value="success") as mock_import:

        res = drive_sync.restore_from_cloud(profile_name="Default", file_id="cloud_file_999")
        assert res["status"] == "success"
        assert res["profile"] == "Default"

        mock_download.assert_called_once()
        mock_import.assert_called_once()


def test_list_cloud_backups():
    mock_service = MagicMock()
    mock_list = MagicMock()
    mock_list.execute.return_value = {
        "files": [{"id": "1", "name": "backup_Default.truehour", "size": "1024"}]
    }
    mock_service.files().list.return_value = mock_list

    with patch("drive_sync.get_or_create_app_folder", return_value="folder_id_999"):
        backups = drive_sync.list_cloud_backups(mock_service)
        assert len(backups) == 1
        assert backups[0]["name"] == "backup_Default.truehour"


def test_backup_and_import_preserves_bank_transfer_details(tmp_path):
    from core.backup_manager import backup_settings, import_settings
    import json

    root_dir = tmp_path / "app_root"
    root_dir.mkdir()
    prof_dir = root_dir / "profiles" / "Default"
    prof_dir.mkdir(parents=True)

    settings_data = {
        "business_name": "Acme Corp",
        "bank_holder": "John Doe",
        "bank_account": "123456789",
        "bank_routing": "987654321",
        "bank_name": "Test Bank",
        "enable_bank_details": True,
    }
    (prof_dir / "app_settings.json").write_text(json.dumps(settings_data))

    zip_file = str(tmp_path / "backup.truehour")

    with patch("core.backup_manager.get_app_data_root", return_value=str(root_dir)):
        success = backup_settings(zip_file, "Default")
        assert success is True

        target_prof = "RestoredProfile"
        status = import_settings(zip_file, target_prof)
        assert status in ["success", "banking_stripped"]

        restored_settings_file = root_dir / "profiles" / target_prof / "app_settings.json"
        assert restored_settings_file.exists()

        restored_data = json.loads(restored_settings_file.read_text())
        assert restored_data.get("bank_holder") == "John Doe"
        assert restored_data.get("bank_account") == "123456789"
        assert restored_data.get("bank_name") == "Test Bank"
        assert restored_data.get("business_name") == "Acme Corp"


def test_query_escaping():
    assert drive_sync._escape_query_param("O'Connor's Profile") == "O\\'Connor\\'s Profile"
    assert drive_sync._escape_query_param("test\\path") == "test\\\\path"


def test_restore_from_cloud_missing_backup_raises():
    mock_creds = DummyCreds(valid=True)
    mock_service = MagicMock()

    with patch("drive_sync.get_google_credentials", return_value=(mock_creds, {})), \
         patch("drive_sync.get_drive_service", return_value=mock_service), \
         patch("drive_sync.list_cloud_backups", return_value=[{"id": "1", "name": "backup_Other.truehour"}]):
        with pytest.raises(FileNotFoundError, match="No cloud backup"):
            drive_sync.restore_from_cloud(profile_name="NonExistentProfile")


def test_drive_restore_worker_failure_emission():
    from workers.drive_sync_worker import DriveRestoreWorker
    from PyQt6.QtCore import QCoreApplication

    app = QCoreApplication.instance() or QCoreApplication([])

    worker = DriveRestoreWorker(profile_name="Default")
    emitted = []

    def handle_finished(success, result, err):
        emitted.append((success, result, err))

    worker.finished.connect(handle_finished)

    with patch("drive_sync.restore_from_cloud", return_value={"status": "wrong_password", "profile": "Default"}):
        worker.run()

    assert len(emitted) == 1
    assert emitted[0][0] is False
    assert "password" in emitted[0][2].lower() or "incorrect" in emitted[0][2].lower()


def test_zip_slip_validation(tmp_path):
    import zipfile
    from core.backup_manager import import_settings

    bad_zip = str(tmp_path / "bad.truehour")
    with zipfile.ZipFile(bad_zip, "w") as zf:
        zf.writestr("../evil.txt", "evil content")

    root_dir = tmp_path / "app_root"
    root_dir.mkdir()

    with patch("core.backup_manager.get_app_data_root", return_value=str(root_dir)):
        status = import_settings(bad_zip, "Default")
        assert status == "error"


def test_drive_sync_worker_success_emission():
    from workers.drive_sync_worker import DriveSyncWorker
    from PyQt6.QtCore import QCoreApplication

    app = QCoreApplication.instance() or QCoreApplication([])

    worker = DriveSyncWorker(profile_name="Default")
    emitted = []

    def handle_finished(success, result, err):
        emitted.append((success, result, err))

    worker.finished.connect(handle_finished)

    mock_res = {"status": "success", "archive_name": "backup_Default.truehour"}
    with patch("drive_sync.sync_to_cloud", return_value=mock_res):
        worker.run()

    assert len(emitted) == 1
    assert emitted[0][0] is True
    assert emitted[0][1]["archive_name"] == "backup_Default.truehour"


def test_token_discovery_across_root_and_profiles(tmp_path):
    root_dir = tmp_path / "app_root"
    root_dir.mkdir()
    prof_dir = root_dir / "profiles" / "MightyProfile"
    prof_dir.mkdir(parents=True)
    token_file = prof_dir / "token.json"
    token_file.write_text('{"token": "mock_profile_token", "refresh_token": "refresh"}')

    active_dir = tmp_path / "empty_active_profile"
    active_dir.mkdir()

    with patch("drive_sync.get_app_data_dir", return_value=str(active_dir)), \
         patch("drive_sync.get_app_data_root", return_value=str(root_dir)), \
         patch("drive_sync.get_legacy_token_path", return_value=str(tmp_path / "nonexistent.pickle")), \
         patch("google.oauth2.credentials.Credentials.from_authorized_user_info", return_value=DummyCreds(valid=True)):
        assert drive_sync.is_authenticated() is True


def test_fading_version_label_sync_progress_and_finished(qtbot):
    from widgets.update_label import FadingVersionLabel

    lbl = FadingVersionLabel("v4.1.0-beta.1 · Build 2026.08.25")
    qtbot.addWidget(lbl)

    # Initial state
    assert lbl.text() == "v4.1.0-beta.1 · Build 2026.08.25"
    assert not lbl._is_syncing

    # Show progress
    lbl.show_sync_progress("Uploading to Drive... 75%", percent=75)
    assert lbl._is_syncing is True
    assert "75%" in lbl.text()
    assert lbl._spinner_timer.isActive() is True

    # Spinner animation tick
    initial_text = lbl.text()
    lbl._on_spinner_tick()
    # Spinner frame should rotate
    assert lbl._is_syncing is True
    assert "75%" in lbl.text()

    # Show finished success
    lbl.show_sync_finished(True, "Cloud backup complete")
    assert lbl._is_syncing is False
    assert lbl._spinner_timer.isActive() is False
    assert "✓ Cloud backup complete" in lbl.text()
    assert lbl._restore_timer.isActive() is True


