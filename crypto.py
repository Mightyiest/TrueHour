import os
import hashlib
import base64

def _get_secure_key(seed: str) -> str:
    """Derives a machine-bound encryption key using the local COMPUTERNAME or HOSTNAME."""
    if not seed:
        return "default_key_seed"
    machine_id = os.environ.get("COMPUTERNAME", "") or os.environ.get("HOSTNAME", "default_host")
    combined = f"{seed}:{machine_id}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()

def _get_password_key(password: str) -> str:
    """Derives a portable encryption key derived purely from a user-provided password."""
    if not password:
        return "default_password_seed"
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def _encrypt_string(plain_text: str, key: str) -> str:
    """Encrypts a string using a XOR cipher with the derived key and base64 encodes the result."""
    if not plain_text:
        return ""
    plain_bytes = plain_text.encode("utf-8")
    key_bytes = key.encode("utf-8")
    key_len = len(key_bytes)
    xor_bytes = bytearray(b ^ key_bytes[i % key_len] for i, b in enumerate(plain_bytes))
    return base64.b64encode(xor_bytes).decode("utf-8")

def _decrypt_string(cipher_text: str, key: str) -> str:
    """Decrypts a base64 encoded XOR cipher-text using the derived key."""
    if not cipher_text:
        return ""
    try:
        raw_bytes = base64.b64decode(cipher_text)
        key_bytes = key.encode("utf-8")
        key_len = len(key_bytes)
        plain_bytes = bytearray(b ^ key_bytes[i % key_len] for i, b in enumerate(raw_bytes))
        return plain_bytes.decode("utf-8")
    except Exception:
        return ""
