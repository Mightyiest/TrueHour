import os
import zipfile
import json
import shutil
import tempfile
import logging
from config import get_app_data_root

logger = logging.getLogger(__name__)

def backup_settings(dest_zip_path: str, profile_name: str) -> bool:
    """
    Backs up everything inside the specified profile directory
    (settings, SQLite pre-aggregation db, QR codes, logos, historical sessions, and autosaves)
    into a compressed .truehour ZIP archive.
    """
    try:
        root_dir = get_app_data_root()
        profile_dir = os.path.join(root_dir, "profiles", profile_name)
        if not os.path.exists(profile_dir):
            logger.error(f"Profile directory {profile_dir} does not exist.")
            return False

        with zipfile.ZipFile(dest_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(profile_dir):
                for file in files:
                    full_path = os.path.join(root, file)
                    # Pack everything inside the profile folder relative to it
                    rel_path = os.path.relpath(full_path, profile_dir)
                    zipf.write(full_path, arcname=rel_path)
        return True
    except Exception as e:
        logger.error(f"Backup failed for profile '{profile_name}': {e}")
        return False

def import_settings(src_zip_path: str, target_profile_name: str) -> bool:
    """
    Validates and restores an entire profile structure (settings, sessions, DB, assets)
    from a compressed .truehour archive into TrueHour/profiles/<target_profile_name>.
    Automatically registers the profile in profiles.json if it is not already present.
    """
    if not zipfile.is_zipfile(src_zip_path):
        logger.error("Provided backup file is not a valid zip archive.")
        return False

    root_dir = get_app_data_root()
    target_profile_dir = os.path.join(root_dir, "profiles", target_profile_name)

    with tempfile.TemporaryDirectory() as tmpdir:
        # Extract to validation temp workspace
        try:
            with zipfile.ZipFile(src_zip_path, 'r') as zipf:
                zipf.extractall(tmpdir)
        except Exception as e:
            logger.error(f"Failed to extract zip file: {e}")
            return False

        # Validate that app_settings.json exists in the extracted backup folder
        temp_settings_path = os.path.join(tmpdir, "app_settings.json")
        if not os.path.exists(temp_settings_path):
            logger.error("Backup file is missing app_settings.json.")
            return False

        # Ensure target profile directory exists and is empty/ready to overwrite
        if os.path.exists(target_profile_dir):
            try:
                shutil.rmtree(target_profile_dir)
            except Exception as e:
                logger.warning(f"Could not clear target profile directory before writing: {e}")

        os.makedirs(target_profile_dir, exist_ok=True)

        # Copy everything from tmpdir to target_profile_dir
        try:
            # Re-base any absolute paths in app_settings.json if a business logo was extracted
            # This is critical for portability across machines
            logo_dir = os.path.join(tmpdir, "logo")
            extracted_logo_path = None
            if os.path.exists(logo_dir) and os.path.isdir(logo_dir):
                logo_files = os.listdir(logo_dir)
                if logo_files:
                    logo_file = logo_files[0]
                    extracted_logo_path = os.path.join(target_profile_dir, "logo", logo_file)

            # Copy all files recursively
            for root, _, files in os.walk(tmpdir):
                # Create corresponding target subdirectories
                rel_dir = os.path.relpath(root, tmpdir)
                target_dir = target_profile_dir if rel_dir == "." else os.path.join(target_profile_dir, rel_dir)
                os.makedirs(target_dir, exist_ok=True)

                for file in files:
                    src_file = os.path.join(root, file)
                    dst_file = os.path.join(target_dir, file)
                    shutil.copy2(src_file, dst_file)

            # If we restored a logo, update its path in target app_settings.json to be absolute on the target machine
            if extracted_logo_path:
                target_settings_path = os.path.join(target_profile_dir, "app_settings.json")
                try:
                    with open(target_settings_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    data["business_logo_path"] = extracted_logo_path
                    with open(target_settings_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=4)
                except Exception as e:
                    logger.warning(f"Failed to adjust logo path in imported settings: {e}")

            # ── Register Profile in profiles.json ──
            profiles_file = os.path.join(root_dir, "profiles.json")
            if os.path.exists(profiles_file):
                try:
                    with open(profiles_file, 'r', encoding='utf-8') as f:
                        profiles_data = json.load(f)

                    if "profiles" not in profiles_data:
                        profiles_data["profiles"] = ["Default"]
                    if target_profile_name not in profiles_data["profiles"]:
                        profiles_data["profiles"].append(target_profile_name)

                    with open(profiles_file, 'w', encoding='utf-8') as f:
                        json.dump(profiles_data, f, indent=4)
                except Exception as e:
                    logger.warning(f"Failed to register imported profile in profiles.json: {e}")

            return True
        except Exception as e:
            logger.error(f"Import failed during file write phase: {e}")
            return False
