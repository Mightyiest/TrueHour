import os
import json
import zipfile
import pytest
from unittest.mock import patch

from core.backup_manager import (
    backup_workspace,
    import_workspace,
    backup_settings,
    count_workspace_sessions,
    get_workspace_summary,
)


def test_workspace_summary_and_session_count(tmp_path):
    root_dir = tmp_path / "app_root"
    root_dir.mkdir()
    prof_default = root_dir / "profiles" / "Default" / "sessions"
    prof_default.mkdir(parents=True)
    prof_mighty = root_dir / "profiles" / "Mightyiest" / "sessions"
    prof_mighty.mkdir(parents=True)

    # Write dummy sessions
    (prof_default / "session_1.json").write_text("{}")
    (prof_default / "session_2.json").write_text("{}")
    (prof_mighty / "session_3.json").write_text("{}")

    (root_dir / "profiles.json").write_text(
        json.dumps({"active_profile": "Mightyiest", "profiles": ["Default", "Mightyiest"]})
    )

    with patch("core.backup_manager.get_app_data_root", return_value=str(root_dir)):
        assert count_workspace_sessions() == 3
        summary = get_workspace_summary()
        assert summary["active_profile"] == "Mightyiest"
        assert sorted(summary["profiles"]) == ["Default", "Mightyiest"]
        assert summary["total_sessions"] == 3
        assert summary["sessions_by_profile"]["Default"] == 2
        assert summary["sessions_by_profile"]["Mightyiest"] == 1


def test_backup_and_import_workspace_roundtrip(tmp_path):
    root_dir = tmp_path / "app_root"
    root_dir.mkdir()

    # Create 2 profiles with data
    for prof, s_count, bank_holder in [("Default", 2, "Alice"), ("Work", 3, "Bob")]:
        p_dir = root_dir / "profiles" / prof
        (p_dir / "sessions").mkdir(parents=True)
        for i in range(s_count):
            (p_dir / "sessions" / f"session_{i}.json").write_text(f'{{"index": {i}}}')

        settings = {
            "business_name": f"{prof} Biz",
            "bank_holder": bank_holder,
            "bank_account": "123456",
        }
        (p_dir / "app_settings.json").write_text(json.dumps(settings))

    (root_dir / "profiles.json").write_text(
        json.dumps({"active_profile": "Work", "profiles": ["Default", "Work"]})
    )

    zip_file = str(tmp_path / "workspace.truehour")

    with patch("core.backup_manager.get_app_data_root", return_value=str(root_dir)):
        success = backup_workspace(zip_file)
        assert success is True
        assert os.path.exists(zip_file)

        # Verify ZIP contains both profiles and metadata
        with zipfile.ZipFile(zip_file, "r") as z:
            names = z.namelist()
            assert "__backup_meta__.json" in names
            assert "profiles.json" in names
            assert "profiles/Default/app_settings.json" in names
            assert "profiles/Work/app_settings.json" in names
            assert "profiles/Default/sessions/session_0.json" in names
            assert "profiles/Work/sessions/session_2.json" in names

            meta = json.loads(z.read("__backup_meta__.json"))
            assert meta["type"] == "full_workspace"
            assert meta["total_sessions"] == 5
            assert "Default" in meta["profiles"]
            assert "Work" in meta["profiles"]

    # Now restore into a fresh mock root directory
    restore_root = tmp_path / "restore_root"
    restore_root.mkdir()

    with patch("core.backup_manager.get_app_data_root", return_value=str(restore_root)):
        res = import_workspace(zip_file)
        assert res["status"] == "success"
        assert res["type"] == "full_workspace"
        assert sorted(res["restored_profiles"]) == ["Default", "Work"]
        assert res["total_sessions"] == 5

        # Check restored profiles on disk
        assert (restore_root / "profiles" / "Default" / "sessions" / "session_0.json").exists()
        assert (restore_root / "profiles" / "Work" / "sessions" / "session_2.json").exists()

        work_settings = json.loads((restore_root / "profiles" / "Work" / "app_settings.json").read_text())
        assert work_settings["business_name"] == "Work Biz"
        assert work_settings["bank_holder"] == "Bob"

        restored_pjson = json.loads((restore_root / "profiles.json").read_text())
        assert sorted(restored_pjson["profiles"]) == ["Default", "Work"]


def test_import_workspace_handles_legacy_single_profile(tmp_path):
    root_dir = tmp_path / "legacy_root"
    root_dir.mkdir()
    p_dir = root_dir / "profiles" / "Default"
    (p_dir / "sessions").mkdir(parents=True)
    (p_dir / "sessions" / "session_legacy.json").write_text('{"legacy": true}')
    (p_dir / "app_settings.json").write_text(json.dumps({"business_name": "Legacy Co"}))

    zip_file = str(tmp_path / "legacy.truehour")

    with patch("core.backup_manager.get_app_data_root", return_value=str(root_dir)):
        success = backup_settings(zip_file, "Default")
        assert success is True

    # Restore via import_workspace into a fresh target
    restore_root = tmp_path / "legacy_restore_root"
    restore_root.mkdir()

    with patch("core.backup_manager.get_app_data_root", return_value=str(restore_root)):
        res = import_workspace(zip_file, selected_profiles=["ImportedProfile"])
        assert res["status"] in ["success", "banking_stripped"]
        assert res["type"] == "single_profile"
        assert res["total_sessions"] == 1
        assert (restore_root / "profiles" / "ImportedProfile" / "sessions" / "session_legacy.json").exists()


def test_backup_and_restore_excludes_tokens_and_lock_files(tmp_path):
    root_dir = tmp_path / "app_root"
    p_dir = root_dir / "profiles" / "Default"
    (p_dir / "sessions").mkdir(parents=True)
    (p_dir / "sessions" / "session_1.json").write_text('{"name": "test"}')
    (p_dir / "app_settings.json").write_text('{"business_name": "Test"}')

    # Add sensitive/lock files that must be excluded
    (p_dir / "token.json").write_text('{"refresh_token": "secret123"}')
    (p_dir / "token.pickle").write_bytes(b"secret_bytes")
    (p_dir / "client_secret.json").write_text('{"installed": {}}')
    (p_dir / "truehour.db-wal").write_bytes(b"wal_data")
    (p_dir / "temp_cache.tmp").write_text("temp")

    (root_dir / "profiles.json").write_text(
        json.dumps({"active_profile": "Default", "profiles": ["Default"]})
    )

    zip_file = str(tmp_path / "workspace_secure.truehour")

    with patch("core.backup_manager.get_app_data_root", return_value=str(root_dir)):
        success = backup_workspace(zip_file)
        assert success is True

        with zipfile.ZipFile(zip_file, "r") as z:
            names = z.namelist()
            assert not any("token.json" in n for n in names)
            assert not any("token.pickle" in n for n in names)
            assert not any("client_secret.json" in n for n in names)
            assert not any(n.endswith(("-wal", "-shm", ".tmp")) for n in names)
            assert "profiles/Default/sessions/session_1.json" in names

    # Now create an archive that artificially has token.json to test import exclusion
    poison_zip = str(tmp_path / "poison.truehour")
    with zipfile.ZipFile(poison_zip, "w") as z:
        z.writestr("__backup_meta__.json", json.dumps({"version": 3, "type": "full_workspace"}))
        z.writestr("profiles.json", json.dumps({"active_profile": "Default", "profiles": ["Default"]}))
        z.writestr("profiles/Default/app_settings.json", '{"business_name": "New"}')
        z.writestr("profiles/Default/token.json", '{"refresh_token": "bad_token"}')
        z.writestr("profiles/Default/sessions/session_2.json", '{}')

    restore_root = tmp_path / "restore_secure_root"
    restore_root.mkdir()
    # Put an existing local token in place
    existing_token = restore_root / "token.json"
    existing_token.write_text('{"refresh_token": "my_valid_local_token"}')

    with patch("core.backup_manager.get_app_data_root", return_value=str(restore_root)):
        res = import_workspace(poison_zip)
        assert res["status"] == "success"
        # token.json inside profile must not have been extracted
        assert not (restore_root / "profiles" / "Default" / "token.json").exists()
        # local root token.json must be untouched
        assert json.loads(existing_token.read_text())["refresh_token"] == "my_valid_local_token"

