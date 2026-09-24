import os
import zipfile
import json
import shutil
import tempfile
import logging
from datetime import datetime
from config import get_app_data_root
from crypto import (
    _get_secure_key,
    _get_password_key,
    _get_password_key_legacy,
    _encrypt_string,
    _decrypt_string,
)

logger = logging.getLogger(__name__)

BANK_FIELDS = [
    "bank_holder",
    "bank_account",
    "bank_routing",
    "bank_swift",
    "bank_name",
    "bank_address",
]

BANK_ENC_FIELDS = [
    "bank_holder_enc",
    "bank_account_enc",
    "bank_routing_enc",
    "bank_swift_enc",
    "bank_name_enc",
    "bank_address_enc",
]

EXCLUDED_BACKUP_FILENAMES = {
    "token.json",
    "token.pickle",
    "client_secret.json",
}

EXCLUDED_BACKUP_EXTENSIONS = (
    "-wal",
    "-shm",
    ".tmp",
)


def _should_skip_backup_file(filename: str) -> bool:
    """Returns True if the file is an OAuth token, secrets file, or database lock file."""
    base = os.path.basename(filename)
    if base in EXCLUDED_BACKUP_FILENAMES:
        return True
    if any(filename.endswith(ext) for ext in EXCLUDED_BACKUP_EXTENSIONS):
        return True
    return False



def _derive_password_key(
    password: str, key_derivation: str = "pbkdf2", salt: bytes = None
) -> str:
    return (
        _get_password_key(password, salt=salt)
        if key_derivation == "pbkdf2"
        else _get_password_key_legacy(password)
    )


def _sanitize_settings_for_backup(
    settings_data: dict,
    password: str = None,
    salt_bytes: bytes = None,
    anonymous_user_id: str = "",
) -> dict:
    """Helper to strip plaintext bank details or re-encrypt with portable password key."""
    data = dict(settings_data)
    anon_id = anonymous_user_id or data.get("anonymous_user_id", "")
    local_key = _get_secure_key(anon_id)

    if password:
        pwd_key = _get_password_key(password, salt=salt_bytes)
        for fld in BANK_ENC_FIELDS:
            plain_fld = fld.replace("_enc", "")
            decrypted = _decrypt_string(data.get(fld, ""), local_key)
            if not decrypted:
                decrypted = data.get(plain_fld, "")
            data[fld] = _encrypt_string(decrypted, pwd_key, salt=salt_bytes)
            data.pop(plain_fld, None)
    else:
        for fld_name in BANK_FIELDS:
            enc_fld = fld_name + "_enc"
            plain_val = data.get(fld_name, "")
            if plain_val:
                data[enc_fld] = _encrypt_string(plain_val, local_key)
                del data[fld_name]
            elif enc_fld in data and fld_name in data:
                del data[fld_name]

    return data


def _restore_settings_from_backup(
    settings_data: dict,
    is_encrypted: bool,
    password: str = None,
    key_derivation: str = "pbkdf2",
    salt_bytes: bytes = None,
) -> dict:
    """Helper to decrypt and re-encrypt banking fields for the target machine."""
    data = dict(settings_data)
    anon_id = data.get("anonymous_user_id", "")
    target_local_key = _get_secure_key(anon_id)

    if is_encrypted and password:
        pwd_key = _derive_password_key(password, key_derivation, salt=salt_bytes)
        for fld in BANK_ENC_FIELDS:
            decrypted_val = _decrypt_string(data.get(fld, ""), pwd_key, salt=salt_bytes)
            data[fld] = _encrypt_string(decrypted_val, target_local_key)
            plain_fld = fld.replace("_enc", "")
            if decrypted_val:
                data[plain_fld] = decrypted_val
    elif not is_encrypted:
        for fld in BANK_ENC_FIELDS:
            plain_fld = fld.replace("_enc", "")
            plain_val = data.get(plain_fld, "")
            if plain_val:
                data[fld] = _encrypt_string(plain_val, target_local_key)
            elif data.get(fld):
                decrypted_val = _decrypt_string(data.get(fld, ""), target_local_key)
                if decrypted_val:
                    data[plain_fld] = decrypted_val
                    data[fld] = _encrypt_string(decrypted_val, target_local_key)

    return data


def count_workspace_sessions() -> int:
    """Returns the total number of saved session JSON files across all profiles."""
    root_dir = get_app_data_root()
    profiles_dir = os.path.join(root_dir, "profiles")
    if not os.path.exists(profiles_dir):
        return 0
    total = 0
    try:
        for p in os.listdir(profiles_dir):
            s_dir = os.path.join(profiles_dir, p, "sessions")
            if os.path.isdir(s_dir):
                total += len([f for f in os.listdir(s_dir) if f.endswith(".json")])
    except Exception as e:
        logger.warning(f"Error counting workspace sessions: {e}")
    return total


def get_workspace_summary() -> dict:
    """Returns a summary of the local workspace: active profile, profile list, and session counts."""
    root_dir = get_app_data_root()
    profiles_file = os.path.join(root_dir, "profiles.json")
    active_profile = "Default"
    profiles = ["Default"]
    if os.path.exists(profiles_file):
        try:
            with open(profiles_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                active_profile = data.get("active_profile", "Default")
                profiles = data.get("profiles", ["Default"])
        except Exception:
            pass

    profiles_dir = os.path.join(root_dir, "profiles")
    if os.path.exists(profiles_dir):
        try:
            for p in os.listdir(profiles_dir):
                if os.path.isdir(os.path.join(profiles_dir, p)) and p not in profiles:
                    profiles.append(p)
        except Exception:
            pass

    sessions_by_profile = {}
    total_sessions = 0
    for p in profiles:
        s_dir = os.path.join(profiles_dir, p, "sessions")
        cnt = 0
        if os.path.isdir(s_dir):
            try:
                cnt = len([f for f in os.listdir(s_dir) if f.endswith(".json")])
            except Exception:
                pass
        sessions_by_profile[p] = cnt
        total_sessions += cnt

    return {
        "active_profile": active_profile,
        "profiles": profiles,
        "total_sessions": total_sessions,
        "sessions_by_profile": sessions_by_profile,
    }


def backup_settings(
    dest_zip_path: str,
    profile_name: str,
    password: str = None,
    anonymous_user_id: str = "",
) -> bool:
    """
    Backs up everything inside the specified single profile directory
    into a compressed .truehour ZIP archive (v2 format).
    """
    try:
        root_dir = get_app_data_root()
        profile_dir = os.path.join(root_dir, "profiles", profile_name)
        if not os.path.exists(profile_dir):
            logger.error(f"Profile directory {profile_dir} does not exist.")
            return False

        # Prepare metadata
        salt_bytes = os.urandom(16) if password else None
        meta = {
            "version": 2,
            "type": "single_profile",
            "profile_name": profile_name,
            "key_derivation": "pbkdf2",
            "encrypted": password is not None,
            "created_at": datetime.now().isoformat(),
            "source_machine": os.environ.get("COMPUTERNAME", "")
            or os.environ.get("HOSTNAME", "unknown"),
        }
        if salt_bytes:
            meta["salt_hex"] = salt_bytes.hex()

        if password:
            pwd_key = _get_password_key(password, salt=salt_bytes)
            meta["verification_enc"] = _encrypt_string(
                "truehour_backup_verify", pwd_key, salt=salt_bytes
            )

        with zipfile.ZipFile(dest_zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            zipf.writestr("__backup_meta__.json", json.dumps(meta, indent=4))

            for root, _, files in os.walk(profile_dir):
                for file in files:
                    if _should_skip_backup_file(file):
                        continue

                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, profile_dir)

                    if rel_path == "app_settings.json":
                        try:
                            with open(full_path, "r", encoding="utf-8") as f:
                                settings_data = json.load(f)

                            sanitized = _sanitize_settings_for_backup(
                                settings_data,
                                password=password,
                                salt_bytes=salt_bytes,
                                anonymous_user_id=anonymous_user_id,
                            )
                            zipf.writestr("app_settings.json", json.dumps(sanitized, indent=4))
                        except Exception as e:
                            logger.error(f"Failed to process app_settings.json for backup: {e}")
                            try:
                                with open(full_path, "r", encoding="utf-8") as f:
                                    raw_data = json.load(f)
                                for fld_name in BANK_FIELDS:
                                    raw_data.pop(fld_name, None)
                                    raw_data.pop(fld_name + "_enc", None)
                                zipf.writestr("app_settings.json", json.dumps(raw_data, indent=4))
                            except Exception as inner:
                                logger.error(f"Could not write fallback settings: {inner}")
                    else:
                        zipf.write(full_path, arcname=rel_path)
        return True
    except Exception as e:
        logger.error(f"Backup failed for profile '{profile_name}': {e}")
        return False


def backup_workspace(
    dest_zip_path: str,
    password: str = None,
) -> bool:
    """
    Backs up ALL profiles in the TrueHour workspace (including profiles.json,
    preferences, historical sessions, SQLite database, logo, and QR codes for every profile)
    into a single compressed .truehour archive (v3 full_workspace container).
    """
    try:
        root_dir = get_app_data_root()
        summary = get_workspace_summary()
        discovered_profiles = summary.get("profiles", ["Default"])
        active_profile = summary.get("active_profile", "Default")
        sessions_by_profile = summary.get("sessions_by_profile", {})
        total_sessions = summary.get("total_sessions", 0)

        salt_bytes = os.urandom(16) if password else None
        meta = {
            "version": 3,
            "type": "full_workspace",
            "key_derivation": "pbkdf2",
            "encrypted": password is not None,
            "created_at": datetime.now().isoformat(),
            "source_machine": os.environ.get("COMPUTERNAME", "")
            or os.environ.get("HOSTNAME", "unknown"),
            "active_profile": active_profile,
            "profiles": discovered_profiles,
            "total_sessions": total_sessions,
            "sessions_by_profile": sessions_by_profile,
        }
        if salt_bytes:
            meta["salt_hex"] = salt_bytes.hex()

        if password:
            pwd_key = _get_password_key(password, salt=salt_bytes)
            meta["verification_enc"] = _encrypt_string(
                "truehour_backup_verify", pwd_key, salt=salt_bytes
            )

        os.makedirs(os.path.dirname(os.path.abspath(dest_zip_path)), exist_ok=True)

        with zipfile.ZipFile(dest_zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            # 1. Metadata
            zipf.writestr("__backup_meta__.json", json.dumps(meta, indent=4))

            # 2. Master profiles.json
            profiles_file = os.path.join(root_dir, "profiles.json")
            if os.path.exists(profiles_file):
                try:
                    with open(profiles_file, "r", encoding="utf-8") as f:
                        zipf.writestr("profiles.json", f.read())
                except Exception as e:
                    logger.warning(f"Could not read profiles.json: {e}")
                    zipf.writestr(
                        "profiles.json",
                        json.dumps({"active_profile": active_profile, "profiles": discovered_profiles}, indent=4),
                    )
            else:
                zipf.writestr(
                    "profiles.json",
                    json.dumps({"active_profile": active_profile, "profiles": discovered_profiles}, indent=4),
                )

            # 3. For each profile, package all its contents
            profiles_base = os.path.join(root_dir, "profiles")
            for prof in discovered_profiles:
                prof_dir = os.path.join(profiles_base, prof)
                if not os.path.exists(prof_dir):
                    continue

                for root, _, files in os.walk(prof_dir):
                    for file in files:
                        if _should_skip_backup_file(file):
                            continue

                        full_path = os.path.join(root, file)
                        rel_in_prof = os.path.relpath(full_path, prof_dir)
                        archive_entry = f"profiles/{prof}/{rel_in_prof}".replace("\\", "/")

                        if rel_in_prof == "app_settings.json":
                            try:
                                with open(full_path, "r", encoding="utf-8") as f:
                                    settings_data = json.load(f)

                                sanitized = _sanitize_settings_for_backup(
                                    settings_data,
                                    password=password,
                                    salt_bytes=salt_bytes,
                                )
                                zipf.writestr(archive_entry, json.dumps(sanitized, indent=4))
                            except Exception as e:
                                logger.error(f"Failed to sanitize {archive_entry}: {e}")
                                try:
                                    with open(full_path, "r", encoding="utf-8") as f:
                                        raw_data = json.load(f)
                                    for fld_name in BANK_FIELDS:
                                        raw_data.pop(fld_name, None)
                                        raw_data.pop(fld_name + "_enc", None)
                                    zipf.writestr(archive_entry, json.dumps(raw_data, indent=4))
                                except Exception:
                                    pass
                        else:
                            zipf.write(full_path, arcname=archive_entry)

        logger.info(
            f"Workspace backup created at {dest_zip_path} with {len(discovered_profiles)} profiles, {total_sessions} sessions."
        )
        return True
    except Exception as e:
        logger.error(f"Failed to create workspace backup: {e}", exc_info=True)
        return False


def import_settings(
    src_zip_path: str,
    target_profile_name: str,
    password: str = None,
    strip_if_encrypted: bool = False,
) -> str:
    """
    Validates and restores a single profile structure from a .truehour archive
    into TrueHour/profiles/<target_profile_name>. (Preserved for backward compatibility).
    """
    if not zipfile.is_zipfile(src_zip_path):
        logger.error("Provided backup file is not a valid zip archive.")
        return "error"

    root_dir = get_app_data_root()
    target_profile_dir = os.path.join(root_dir, "profiles", target_profile_name)

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            with zipfile.ZipFile(src_zip_path, "r") as zipf:
                target_dir = os.path.abspath(tmpdir)
                if not target_dir.endswith(os.path.sep):
                    target_dir += os.path.sep

                for member in zipf.namelist():
                    target_path = os.path.abspath(os.path.join(tmpdir, member))
                    if not (target_path == os.path.abspath(tmpdir) or target_path.startswith(target_dir)):
                        logger.error(f"Security Alert: Unsafe zip entry prevented: {member}")
                        return "error"
                zipf.extractall(tmpdir)
        except Exception as e:
            logger.error(f"Failed to extract zip file: {e}")
            return "error"

        # Check if this is a v3 workspace archive being imported via single-profile import
        temp_meta_path = os.path.join(tmpdir, "__backup_meta__.json")
        is_encrypted = False
        verification_token = ""
        key_derivation = "legacy"
        salt_bytes = None

        if os.path.exists(temp_meta_path):
            try:
                with open(temp_meta_path, "r", encoding="utf-8") as f:
                    meta_data = json.load(f)
                is_encrypted = meta_data.get("encrypted", False)
                verification_token = meta_data.get("verification_enc", "")
                key_derivation = meta_data.get("key_derivation", "legacy")
                salt_hex = meta_data.get("salt_hex")
                if salt_hex:
                    salt_bytes = bytes.fromhex(salt_hex)

                if meta_data.get("type") == "full_workspace" and os.path.exists(os.path.join(tmpdir, "profiles")):
                    res = import_workspace(
                        src_zip_path,
                        password=password,
                        strip_if_encrypted=strip_if_encrypted,
                        selected_profiles=[target_profile_name],
                    )
                    return res.get("status", "error")
            except Exception:
                pass

        temp_settings_path = os.path.join(tmpdir, "app_settings.json")
        if not os.path.exists(temp_settings_path):
            logger.error("Backup file is missing app_settings.json.")
            return "error"

        status = "success"
        if is_encrypted:
            if not password:
                if strip_if_encrypted:
                    is_encrypted = False
                    status = "banking_stripped"
                else:
                    return "password_required"

            if is_encrypted:
                pwd_key = _derive_password_key(password, key_derivation, salt=salt_bytes)
                decrypted_verify = _decrypt_string(verification_token, pwd_key, salt=salt_bytes)
                if decrypted_verify != "truehour_backup_verify":
                    return "wrong_password"

        try:
            with open(temp_settings_path, "r", encoding="utf-8") as f:
                settings_data = json.load(f)
            restored_settings = _restore_settings_from_backup(
                settings_data,
                is_encrypted=is_encrypted,
                password=password,
                key_derivation=key_derivation,
                salt_bytes=salt_bytes,
            )
            with open(temp_settings_path, "w", encoding="utf-8") as f:
                json.dump(restored_settings, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to process settings: {e}")
            return "error"

        if os.path.exists(temp_meta_path):
            try:
                os.remove(temp_meta_path)
            except Exception:
                pass

        os.makedirs(target_profile_dir, exist_ok=True)

        try:
            logo_dir = os.path.join(tmpdir, "logo")
            extracted_logo_path = None
            if os.path.exists(logo_dir) and os.path.isdir(logo_dir):
                logo_files = os.listdir(logo_dir)
                if logo_files:
                    extracted_logo_path = os.path.join(target_profile_dir, "logo", logo_files[0])

            for root, _, files in os.walk(tmpdir):
                rel_dir = os.path.relpath(root, tmpdir)
                target_dir = target_profile_dir if rel_dir == "." else os.path.join(target_profile_dir, rel_dir)
                os.makedirs(target_dir, exist_ok=True)

                for file in files:
                    if _should_skip_backup_file(file):
                        continue
                    src_file = os.path.join(root, file)
                    dst_file = os.path.join(target_dir, file)
                    try:
                        shutil.copy2(src_file, dst_file)
                    except Exception as copy_err:
                        logger.warning(f"Skipped locked file '{file}': {copy_err}")

            if extracted_logo_path:
                target_settings_path = os.path.join(target_profile_dir, "app_settings.json")
                try:
                    with open(target_settings_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    data["business_logo_path"] = extracted_logo_path
                    with open(target_settings_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=4)
                except Exception:
                    pass

            profiles_file = os.path.join(root_dir, "profiles.json")
            if os.path.exists(profiles_file):
                try:
                    with open(profiles_file, "r", encoding="utf-8") as f:
                        profiles_data = json.load(f)
                    if "profiles" not in profiles_data:
                        profiles_data["profiles"] = ["Default"]
                    if target_profile_name not in profiles_data["profiles"]:
                        profiles_data["profiles"].append(target_profile_name)
                    with open(profiles_file, "w", encoding="utf-8") as f:
                        json.dump(profiles_data, f, indent=4)
                except Exception:
                    pass

            return status
        except Exception as e:
            logger.error(f"Import failed during file write phase: {e}")
            return "error"


def import_workspace(
    src_zip_path: str,
    password: str = None,
    strip_if_encrypted: bool = False,
    selected_profiles: list = None,
) -> dict:
    """
    Validates and restores ALL profiles from a .truehour archive into the TrueHour workspace.
    Supports both v3 full_workspace archives and legacy v1/v2 single-profile archives.

    Returns a dict with:
      - "status": "success", "banking_stripped", "password_required", "wrong_password", or "error"
      - "type": "full_workspace" or "single_profile"
      - "restored_profiles": list of profile names restored
      - "active_profile": active profile name
      - "total_sessions": total session files restored
      - "sessions_by_profile": dict mapping profile name to session count
    """
    if not zipfile.is_zipfile(src_zip_path):
        logger.error("Provided backup file is not a valid zip archive.")
        return {"status": "error", "message": "Not a valid ZIP archive."}

    root_dir = get_app_data_root()

    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. Zip Slip Prevention & Extraction
        try:
            with zipfile.ZipFile(src_zip_path, "r") as zipf:
                target_dir = os.path.abspath(tmpdir)
                if not target_dir.endswith(os.path.sep):
                    target_dir += os.path.sep

                for member in zipf.namelist():
                    target_path = os.path.abspath(os.path.join(tmpdir, member))
                    if not (target_path == os.path.abspath(tmpdir) or target_path.startswith(target_dir)):
                        logger.error(f"Security Alert: Unsafe zip entry prevented (path traversal): {member}")
                        return {"status": "error", "message": "Unsafe path traversal detected."}
                zipf.extractall(tmpdir)
        except Exception as e:
            logger.error(f"Failed to extract zip file: {e}")
            return {"status": "error", "message": str(e)}

        # 2. Metadata & Encryption Verification
        temp_meta_path = os.path.join(tmpdir, "__backup_meta__.json")
        is_encrypted = False
        verification_token = ""
        key_derivation = "pbkdf2"
        salt_bytes = None
        archive_type = "single_profile"
        meta_data = {}

        if os.path.exists(temp_meta_path):
            try:
                with open(temp_meta_path, "r", encoding="utf-8") as f:
                    meta_data = json.load(f)
                is_encrypted = meta_data.get("encrypted", False)
                verification_token = meta_data.get("verification_enc", "")
                key_derivation = meta_data.get("key_derivation", "pbkdf2")
                archive_type = meta_data.get("type", "single_profile")
                salt_hex = meta_data.get("salt_hex")
                if salt_hex:
                    salt_bytes = bytes.fromhex(salt_hex)
            except Exception as e:
                logger.warning(f"Error parsing metadata: {e}")

        # If profiles/ directory exists inside tmpdir, treat as full workspace even if meta is missing
        extracted_profiles_dir = os.path.join(tmpdir, "profiles")
        if os.path.exists(extracted_profiles_dir) and os.path.isdir(extracted_profiles_dir):
            archive_type = "full_workspace"

        status = "success"
        if is_encrypted:
            if not password:
                if strip_if_encrypted:
                    is_encrypted = False
                    status = "banking_stripped"
                else:
                    return {"status": "password_required", "type": archive_type}

            if is_encrypted:
                pwd_key = _derive_password_key(password, key_derivation, salt=salt_bytes)
                decrypted_verify = _decrypt_string(verification_token, pwd_key, salt=salt_bytes)
                if decrypted_verify != "truehour_backup_verify":
                    return {"status": "wrong_password", "type": archive_type}

        # 3. Path A: Multi-Profile Workspace Restore
        if archive_type == "full_workspace":
            restored_profiles = []
            sessions_by_profile = {}
            total_sessions = 0

            available_profiles = [
                d for d in os.listdir(extracted_profiles_dir)
                if os.path.isdir(os.path.join(extracted_profiles_dir, d))
            ]

            target_profiles = (
                [p for p in available_profiles if p in selected_profiles]
                if selected_profiles
                else available_profiles
            )

            for prof in target_profiles:
                src_prof_dir = os.path.join(extracted_profiles_dir, prof)
                dest_prof_dir = os.path.join(root_dir, "profiles", prof)
                os.makedirs(dest_prof_dir, exist_ok=True)

                # Process app_settings.json
                src_settings_path = os.path.join(src_prof_dir, "app_settings.json")
                extracted_logo_path = None

                if os.path.exists(src_settings_path):
                    try:
                        with open(src_settings_path, "r", encoding="utf-8") as f:
                            s_data = json.load(f)
                        restored_settings = _restore_settings_from_backup(
                            s_data,
                            is_encrypted=is_encrypted,
                            password=password,
                            key_derivation=key_derivation,
                            salt_bytes=salt_bytes,
                        )

                        logo_dir = os.path.join(src_prof_dir, "logo")
                        if os.path.exists(logo_dir) and os.listdir(logo_dir):
                            extracted_logo_path = os.path.join(dest_prof_dir, "logo", os.listdir(logo_dir)[0])
                            restored_settings["business_logo_path"] = extracted_logo_path

                        with open(src_settings_path, "w", encoding="utf-8") as f:
                            json.dump(restored_settings, f, indent=4)
                    except Exception as e:
                        logger.warning(f"Error restoring settings for profile {prof}: {e}")

                # Copy all files for this profile
                prof_sessions = 0
                for root, _, files in os.walk(src_prof_dir):
                    rel_dir = os.path.relpath(root, src_prof_dir)
                    target_dir = dest_prof_dir if rel_dir == "." else os.path.join(dest_prof_dir, rel_dir)
                    os.makedirs(target_dir, exist_ok=True)

                    for file in files:
                        if _should_skip_backup_file(file):
                            continue
                        if file.endswith(".json") and rel_dir == "sessions":
                            prof_sessions += 1

                        src_file = os.path.join(root, file)
                        dst_file = os.path.join(target_dir, file)
                        try:
                            shutil.copy2(src_file, dst_file)
                        except Exception as copy_err:
                            logger.warning(f"Skipped copying '{file}': {copy_err}")

                restored_profiles.append(prof)
                sessions_by_profile[prof] = prof_sessions
                total_sessions += prof_sessions

            # Update / merge master profiles.json
            active_profile = meta_data.get("active_profile", "Default")
            profiles_file = os.path.join(root_dir, "profiles.json")
            existing_profiles = []
            if os.path.exists(profiles_file):
                try:
                    with open(profiles_file, "r", encoding="utf-8") as f:
                        cur_p = json.load(f)
                        existing_profiles = cur_p.get("profiles", [])
                        if not selected_profiles:
                            active_profile = cur_p.get("active_profile", active_profile)
                except Exception:
                    pass

            for p in restored_profiles:
                if p not in existing_profiles:
                    existing_profiles.append(p)

            if not existing_profiles:
                existing_profiles = ["Default"]
            if active_profile not in existing_profiles:
                active_profile = existing_profiles[0]

            try:
                with open(profiles_file, "w", encoding="utf-8") as f:
                    json.dump({"active_profile": active_profile, "profiles": existing_profiles}, f, indent=4)
            except Exception as e:
                logger.error(f"Failed to update master profiles.json: {e}")

            logger.info(
                f"Workspace restored successfully: {len(restored_profiles)} profiles, {total_sessions} sessions."
            )
            return {
                "status": status,
                "type": "full_workspace",
                "restored_profiles": restored_profiles,
                "active_profile": active_profile,
                "total_sessions": total_sessions,
                "sessions_by_profile": sessions_by_profile,
            }

        # 4. Path B: Single-Profile Archive Legacy Restore
        target_name = (
            selected_profiles[0]
            if selected_profiles
            else meta_data.get("profile_name") or "Default"
        )
        single_status = import_settings(
            src_zip_path,
            target_profile_name=target_name,
            password=password,
            strip_if_encrypted=strip_if_encrypted,
        )

        cnt = 0
        s_dir = os.path.join(root_dir, "profiles", target_name, "sessions")
        if os.path.exists(s_dir):
            try:
                cnt = len([f for f in os.listdir(s_dir) if f.endswith(".json")])
            except Exception:
                pass

        return {
            "status": single_status,
            "type": "single_profile",
            "restored_profiles": [target_name] if single_status in ["success", "banking_stripped"] else [],
            "active_profile": target_name,
            "total_sessions": cnt,
            "sessions_by_profile": {target_name: cnt},
        }
