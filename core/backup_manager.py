import os
import zipfile
import json
import shutil
import tempfile
import logging
from datetime import datetime
from config import get_app_data_root
from crypto import _get_secure_key, _get_password_key, _encrypt_string, _decrypt_string

logger = logging.getLogger(__name__)

def backup_settings(dest_zip_path: str, profile_name: str, password: str = None, anonymous_user_id: str = "") -> bool:
    """
    Backs up everything inside the specified profile directory
    (settings, SQLite pre-aggregation db, QR codes, logos, historical sessions, and autosaves)
    into a compressed .truehour ZIP archive.
    
    If password is provided, re-encrypts the banking details with a password-derived key.
    If no password is provided, strips banking details from the settings file inside the backup.
    """
    try:
        root_dir = get_app_data_root()
        profile_dir = os.path.join(root_dir, "profiles", profile_name)
        if not os.path.exists(profile_dir):
            logger.error(f"Profile directory {profile_dir} does not exist.")
            return False

        # Prepare metadata
        meta = {
            "version": 1,
            "encrypted": password is not None,
            "created_at": datetime.now().isoformat(),
            "source_machine": os.environ.get("COMPUTERNAME", "") or os.environ.get("HOSTNAME", "unknown")
        }
        
        if password:
            pwd_key = _get_password_key(password)
            meta["verification_enc"] = _encrypt_string("truehour_backup_verify", pwd_key)

        with zipfile.ZipFile(dest_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Write metadata file first
            zipf.writestr("__backup_meta__.json", json.dumps(meta, indent=4))
            
            for root, _, files in os.walk(profile_dir):
                for file in files:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, profile_dir)
                    
                    if rel_path == "app_settings.json":
                        # Intercept app_settings.json to strip or re-encrypt banking details
                        try:
                            with open(full_path, 'r', encoding='utf-8') as f:
                                settings_data = json.load(f)
                            
                            # Clean plaintext fields (they should already be empty, but enforce it)
                            bank_fields = ["bank_holder", "bank_account", "bank_routing", "bank_swift", "bank_name", "bank_address"]
                            for fld in bank_fields:
                                settings_data[fld] = ""

                            enc_fields = ["bank_holder_enc", "bank_account_enc", "bank_routing_enc", "bank_swift_enc", "bank_name_enc", "bank_address_enc"]

                            if password:
                                # Decrypt using local machine key, then encrypt using portable password key
                                local_key = _get_secure_key(anonymous_user_id)
                                pwd_key = _get_password_key(password)
                                
                                for fld in enc_fields:
                                    decrypted = _decrypt_string(settings_data.get(fld, ""), local_key)
                                    settings_data[fld] = _encrypt_string(decrypted, pwd_key)
                            else:
                                # Standard backup: strip encrypted fields
                                for fld in enc_fields:
                                    settings_data.pop(fld, None)
                            
                            # Write sanitized settings to ZIP
                            zipf.writestr("app_settings.json", json.dumps(settings_data, indent=4))
                        except Exception as e:
                            logger.error(f"Failed to process app_settings.json for backup: {e}")
                            # Fallback: write as-is if processed fails
                            zipf.write(full_path, arcname=rel_path)
                    else:
                        zipf.write(full_path, arcname=rel_path)
        return True
    except Exception as e:
        logger.error(f"Backup failed for profile '{profile_name}': {e}")
        return False

def import_settings(src_zip_path: str, target_profile_name: str, password: str = None, strip_if_encrypted: bool = False) -> str:
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
            with zipfile.ZipFile(src_zip_path, 'r') as zipf:
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
        
        if os.path.exists(temp_meta_path):
            try:
                with open(temp_meta_path, 'r', encoding='utf-8') as f:
                    meta_data = json.load(f)
                is_encrypted = meta_data.get("encrypted", False)
                verification_token = meta_data.get("verification_enc", "")
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
                pwd_key = _get_password_key(password)
                decrypted_verify = _decrypt_string(verification_token, pwd_key)
                if decrypted_verify != "truehour_backup_verify":
                    return "wrong_password"


        try:
            with open(temp_settings_path, 'r', encoding='utf-8') as f:
                settings_data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to parse app_settings.json: {e}")
            return "error"

        # Clean/Re-encrypt fields based on standard vs encrypted
        enc_fields = ["bank_holder_enc", "bank_account_enc", "bank_routing_enc", "bank_swift_enc", "bank_name_enc", "bank_address_enc"]
        anon_id = settings_data.get("anonymous_user_id", "")
        target_local_key = _get_secure_key(anon_id)

        if is_encrypted:
            # We verified the password above. Now decrypt and re-encrypt for target machine.
            pwd_key = _get_password_key(password)
            for fld in enc_fields:
                decrypted_val = _decrypt_string(settings_data.get(fld, ""), pwd_key)
                settings_data[fld] = _encrypt_string(decrypted_val, target_local_key)
        else:
            # Legacy or standard backup: strip local-only machine-bound encrypted details
            for fld in enc_fields:
                settings_data.pop(fld, None)
            status = "banking_stripped"

        # Write corrected app_settings.json back to temp
        try:
            with open(temp_settings_path, 'w', encoding='utf-8') as f:
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
            logo_dir = os.path.join(tmpdir, "logo")
            extracted_logo_path = None
            if os.path.exists(logo_dir) and os.path.isdir(logo_dir):
                logo_files = os.listdir(logo_dir)
                if logo_files:
                    logo_file = logo_files[0]
                    extracted_logo_path = os.path.join(target_profile_dir, "logo", logo_file)

            # Copy all files recursively
            for root, _, files in os.walk(tmpdir):
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

            # Register Profile in profiles.json
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

            return status
        except Exception as e:
            logger.error(f"Import failed during file write phase: {e}")
            return "error"
