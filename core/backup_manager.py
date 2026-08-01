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


def _derive_password_key(
    password: str, key_derivation: str = "pbkdf2", salt: bytes = None
) -> str:
    return (
        _get_password_key(password, salt=salt)
        if key_derivation == "pbkdf2"
        else _get_password_key_legacy(password)
    )


def backup_settings(
    dest_zip_path: str,
    profile_name: str,
    password: str = None,
    anonymous_user_id: str = "",
) -> bool:
    """
    Backs up everything inside the specified profile directory
    (settings, SQLite pre-aggregation db, QR codes, logos, historical sessions, and autosaves)
    into a compressed .truehour ZIP archive.

    If password is provided, re-encrypts banking details with a password-derived key.
    If no password is provided, encrypts banking details with the machine key and excludes
    plaintext banking details from app_settings.json inside the ZIP archive.
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
            # Write metadata file first
            zipf.writestr("__backup_meta__.json", json.dumps(meta, indent=4))

            for root, _, files in os.walk(profile_dir):
                for file in files:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, profile_dir)

                    if rel_path == "app_settings.json":
                        # Intercept app_settings.json to strip or re-encrypt banking details
                        try:
                            with open(full_path, "r", encoding="utf-8") as f:
                                settings_data = json.load(f)

                            anon_id = anonymous_user_id or settings_data.get("anonymous_user_id", "")
                            local_key = _get_secure_key(anon_id)

                            if password:
                                # Decrypt using local machine key, then encrypt using portable password key
                                pwd_key = _get_password_key(password, salt=salt_bytes)

                                for fld in BANK_ENC_FIELDS:
                                    plain_fld = fld.replace("_enc", "")
                                    decrypted = _decrypt_string(
                                        settings_data.get(fld, ""), local_key
                                    )
                                    if not decrypted:
                                        # Fall back to the plaintext field if this profile
                                        # never got encrypted (older settings files).
                                        decrypted = settings_data.get(plain_fld, "")
                                    settings_data[fld] = _encrypt_string(
                                        decrypted, pwd_key, salt=salt_bytes
                                    )
                                    # Never ship cleartext bank details in the archive;
                                    # import_settings reconstructs them locally after the
                                    # password check succeeds.
                                    settings_data.pop(plain_fld, None)
                            else:
                                # Standard / Cloud Backup: Re-encrypt to local_key if plain fields present, but strip plaintext bank fields from archive
                                for fld_name in BANK_FIELDS:
                                    enc_fld = fld_name + "_enc"
                                    plain_val = settings_data.get(fld_name, "")
                                    if plain_val:
                                        settings_data[enc_fld] = _encrypt_string(plain_val, local_key)
                                        del settings_data[fld_name]
                                    elif enc_fld in settings_data and fld_name in settings_data:
                                        del settings_data[fld_name]

                            # Write sanitized settings to ZIP
                            zipf.writestr(
                                "app_settings.json", json.dumps(settings_data, indent=4)
                            )
                        except Exception as e:
                            logger.error(
                                f"Failed to process app_settings.json for backup: {e}"
                            )
                            # Fallback: never write the file as-is, it may still hold
                            # cleartext bank details. Strip every bank field (plaintext
                            # and encrypted) and write that instead.
                            try:
                                with open(full_path, "r", encoding="utf-8") as f:
                                    raw_data = json.load(f)
                                for fld_name in BANK_FIELDS:
                                    raw_data.pop(fld_name, None)
                                    raw_data.pop(fld_name + "_enc", None)
                                zipf.writestr(
                                    "app_settings.json", json.dumps(raw_data, indent=4)
                                )
                            except Exception as inner:
                                logger.error(
                                    f"Could not write sanitized fallback settings, "
                                    f"omitting app_settings.json from backup: {inner}"
                                )
                    else:
                        zipf.write(full_path, arcname=rel_path)
        return True
    except Exception as e:
        logger.error(f"Backup failed for profile '{profile_name}': {e}")
        return False


def import_settings(
    src_zip_path: str,
    target_profile_name: str,
    password: str = None,
    strip_if_encrypted: bool = False,
) -> str:
    """
    Validates and restores an entire profile structure (settings, sessions, DB, assets)
    from a compressed .truehour archive into TrueHour/profiles/<target_profile_name>.
    Automatically registers the profile in profiles.json if it is not already present.

    Returns a status string:
      - "success": Complete import with decrypted/restored banking data.
      - "banking_stripped": Complete import, but banking details were removed/missing.
      - "password_required": The backup is encrypted, but no password was provided.
      - "wrong_password": The password provided failed to decrypt the verification token.
      - "error": General failure.
    """
    if not zipfile.is_zipfile(src_zip_path):
        logger.error("Provided backup file is not a valid zip archive.")
        return "error"

    root_dir = get_app_data_root()
    target_profile_dir = os.path.join(root_dir, "profiles", target_profile_name)

    with tempfile.TemporaryDirectory() as tmpdir:
        # Extract to validation temp workspace
        try:
            with zipfile.ZipFile(src_zip_path, "r") as zipf:
                # Zip Slip prevention: validate all member target paths
                target_dir = os.path.abspath(tmpdir)
                if not target_dir.endswith(os.path.sep):
                    target_dir += os.path.sep

                for member in zipf.namelist():
                    target_path = os.path.abspath(os.path.join(tmpdir, member))
                    if not (target_path == os.path.abspath(tmpdir) or target_path.startswith(target_dir)):
                        logger.error(
                            f"Security Alert: Unsafe zip entry prevented (path traversal): {member}"
                        )
                        return "error"
                zipf.extractall(tmpdir)
        except Exception as e:
            logger.error(f"Failed to extract zip file: {e}")
            return "error"

        # Validate that app_settings.json exists in the extracted backup folder
        temp_settings_path = os.path.join(tmpdir, "app_settings.json")
        if not os.path.exists(temp_settings_path):
            logger.error("Backup file is missing app_settings.json.")
            return "error"

        # Read meta file if it exists
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
            except Exception:
                pass

        # Handle Encryption logic
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
        except Exception as e:
            logger.error(f"Failed to parse app_settings.json: {e}")
            return "error"

        # Clean/Re-encrypt fields based on standard vs encrypted
        anon_id = settings_data.get("anonymous_user_id", "")
        target_local_key = _get_secure_key(anon_id)

        if is_encrypted:
            # We verified the password above. Now decrypt and re-encrypt for target machine.
            pwd_key = _derive_password_key(password, key_derivation, salt=salt_bytes)
            for fld in BANK_ENC_FIELDS:
                decrypted_val = _decrypt_string(settings_data.get(fld, ""), pwd_key, salt=salt_bytes)
                settings_data[fld] = _encrypt_string(decrypted_val, target_local_key)
                plain_fld = fld.replace("_enc", "")
                if decrypted_val:
                    settings_data[plain_fld] = decrypted_val
        else:
            # Standard / Cloud backup: Preserve bank details and generate local machine encrypted fields
            for fld in BANK_ENC_FIELDS:
                plain_fld = fld.replace("_enc", "")
                plain_val = settings_data.get(plain_fld, "")
                if plain_val:
                    settings_data[fld] = _encrypt_string(plain_val, target_local_key)
                elif settings_data.get(fld):
                    decrypted_val = _decrypt_string(settings_data.get(fld, ""), target_local_key)
                    if decrypted_val:
                        settings_data[plain_fld] = decrypted_val
                        settings_data[fld] = _encrypt_string(decrypted_val, target_local_key)

        # Write corrected app_settings.json back to temp
        try:
            with open(temp_settings_path, "w", encoding="utf-8") as f:
                json.dump(settings_data, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to write re-encrypted settings: {e}")
            return "error"

        # Remove the metadata file from extraction folder so it isn't copied to the user's profile
        if os.path.exists(temp_meta_path):
            try:
                os.remove(temp_meta_path)
            except Exception:
                pass

        # Ensure target profile directory exists
        os.makedirs(target_profile_dir, exist_ok=True)

        # Copy everything from tmpdir to target_profile_dir safely
        try:
            # Re-base any absolute paths in app_settings.json if a business logo was extracted
            logo_dir = os.path.join(tmpdir, "logo")
            extracted_logo_path = None
            if os.path.exists(logo_dir) and os.path.isdir(logo_dir):
                logo_files = os.listdir(logo_dir)
                if logo_files:
                    logo_file = logo_files[0]
                    extracted_logo_path = os.path.join(
                        target_profile_dir, "logo", logo_file
                    )

            # Copy all files recursively with safe exception handling for active/locked database files
            for root, _, files in os.walk(tmpdir):
                rel_dir = os.path.relpath(root, tmpdir)
                target_dir = (
                    target_profile_dir
                    if rel_dir == "."
                    else os.path.join(target_profile_dir, rel_dir)
                )
                os.makedirs(target_dir, exist_ok=True)

                for file in files:
                    # Skip temporary SQLite write-ahead log files to prevent Windows access violations
                    if file.endswith(("-wal", "-shm")):
                        continue

                    src_file = os.path.join(root, file)
                    dst_file = os.path.join(target_dir, file)
                    try:
                        shutil.copy2(src_file, dst_file)
                    except Exception as copy_err:
                        logger.warning(
                            f"Skipped copying locked file '{file}' during profile restore: {copy_err}"
                        )

            # If we restored a logo, update its path in target app_settings.json to be absolute on the target machine
            if extracted_logo_path:
                target_settings_path = os.path.join(
                    target_profile_dir, "app_settings.json"
                )
                try:
                    with open(target_settings_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    data["business_logo_path"] = extracted_logo_path
                    with open(target_settings_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=4)
                except Exception as e:
                    logger.warning(
                        f"Failed to adjust logo path in imported settings: {e}"
                    )

            # Register Profile in profiles.json
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
                except Exception as e:
                    logger.warning(
                        f"Failed to register imported profile in profiles.json: {e}"
                    )

            return status
        except Exception as e:
            logger.error(f"Import failed during file write phase: {e}")
            return "error"
