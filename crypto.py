import os
import hashlib
import base64
import logging

logger = logging.getLogger(__name__)


def _get_secure_key(seed: str) -> str:
    """Derives a machine-bound encryption key using the local COMPUTERNAME or HOSTNAME."""
    if not seed:
        logger.warning("_get_secure_key called with empty seed; falling back to default key seed.")
        return "default_key_seed"
    machine_id = os.environ.get("COMPUTERNAME", "") or os.environ.get(
        "HOSTNAME", "default_host"
    )
    combined = f"{seed}:{machine_id}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def _get_password_key(
    password: str, salt: bytes = None, iterations: int = 600000
) -> str:
    """Derives a portable encryption key derived purely from a user-provided password using PBKDF2HMAC (CodeQL compliant)."""
    if not password:
        return "default_password_seed"
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes

    effective_salt = salt if salt is not None else b"TrueHour_Password_Salt_Fixed"
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=effective_salt,
        iterations=iterations,
    )
    derived = kdf.derive(password.encode("utf-8"))
    return derived.hex()


def _get_password_key_legacy(data: str) -> str:
    """Legacy SHA-256 key derivation to support old backups."""
    if not data:
        return "default_password_seed"
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _derive_fernet_key(
    key_seed: str, salt: bytes = None, iterations: int = 600000
) -> bytes:
    """Derives a 32-byte key suitable for Fernet from the hex key_seed."""
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes

    effective_salt = salt if salt is not None else b"TrueHour_Fixed_Salt_1337"
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=effective_salt,
        iterations=iterations,
    )
    return base64.urlsafe_b64encode(kdf.derive(key_seed.encode("utf-8")))


def _encrypt_string(plain_text: str, key: str, salt: bytes = None) -> str:
    """Encrypts a string using Fernet and base64 encodes the result, prefixing with 'v2:'."""
    if not plain_text:
        return ""
    try:
        from cryptography.fernet import Fernet

        fernet_key = _derive_fernet_key(key, salt=salt, iterations=600000)
        f = Fernet(fernet_key)
        enc_bytes = f.encrypt(plain_text.encode("utf-8"))
        return "v2:" + enc_bytes.decode("utf-8")
    except Exception as e:
        logger.error("Encryption failed in _encrypt_string: %s", e)
        return ""


def _decrypt_string(
    cipher_text: str, key: str, salt: bytes = None, allow_legacy_xor: bool = False
) -> str:
    """Decrypts a Fernet (v2) or legacy XOR encrypted string."""
    if not cipher_text:
        return ""
    if cipher_text.startswith("v2:"):
        from cryptography.fernet import Fernet

        raw_payload = cipher_text[3:].encode("utf-8")

        # Attempt 1: Current standard 600,000 PBKDF2 iterations
        try:
            fernet_key = _derive_fernet_key(key, salt=salt, iterations=600000)
            f = Fernet(fernet_key)
            dec_bytes = f.decrypt(raw_payload)
            return dec_bytes.decode("utf-8")
        except Exception:
            pass

        # Attempt 2: Legacy 100,000 PBKDF2 iterations (for backward compatibility with existing local settings)
        try:
            fernet_key_legacy = _derive_fernet_key(key, salt=salt, iterations=100000)
            f_legacy = Fernet(fernet_key_legacy)
            dec_bytes = f_legacy.decrypt(raw_payload)
            return dec_bytes.decode("utf-8")
        except Exception:
            pass

        logger.error("Fernet decryption failed in _decrypt_string: Invalid key or corrupt ciphertext")
        return ""
    elif allow_legacy_xor:
        # Legacy XOR cipher fallback (explicit opt-in only)
        try:
            raw_bytes = base64.b64decode(cipher_text)
            key_bytes = key.encode("utf-8")
            key_len = len(key_bytes)
            plain_bytes = bytearray(
                b ^ key_bytes[i % key_len] for i, b in enumerate(raw_bytes)
            )
            return plain_bytes.decode("utf-8")
        except Exception as e:
            logger.error("Legacy XOR decryption failed: %s", e)
            return ""
    else:
        logger.warning("Unrecognized ciphertext format and legacy XOR disabled.")
        return ""

