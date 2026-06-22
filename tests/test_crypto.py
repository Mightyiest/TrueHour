import unittest
from crypto import _get_secure_key, _get_password_key, _get_password_key_legacy, _encrypt_string, _decrypt_string

class TestCrypto(unittest.TestCase):
    def test_secure_and_password_keys(self):
        k1 = _get_secure_key("test_seed")
        k2 = _get_password_key("test_pwd")
        self.assertEqual(len(k1), 64)
        self.assertEqual(len(k2), 64)
        
        # Defaults
        self.assertEqual(_get_secure_key(""), "default_key_seed")
        self.assertEqual(_get_password_key(""), "default_password_seed")

    def test_encryption_decryption(self):
        key = _get_secure_key("user_id_123")
        plain = "Sensitive banking details"
        
        cipher = _encrypt_string(plain, key)
        self.assertTrue(cipher.startswith("v2:"))
        
        decrypted = _decrypt_string(cipher, key)
        self.assertEqual(decrypted, plain)

    def test_legacy_xor_fallback(self):
        # Legacy XOR implementation for generating test cipher
        import base64
        def legacy_encrypt(plain, key):
            plain_bytes = plain.encode("utf-8")
            key_bytes = key.encode("utf-8")
            key_len = len(key_bytes)
            xor_bytes = bytearray(b ^ key_bytes[i % key_len] for i, b in enumerate(plain_bytes))
            return base64.b64encode(xor_bytes).decode("utf-8")

        key = _get_secure_key("user_id_legacy")
        plain = "My legacy bank information"
        legacy_cipher = legacy_encrypt(plain, key)
        
        # Decrypting legacy cipher should fallback and work correctly
        decrypted = _decrypt_string(legacy_cipher, key)
        self.assertEqual(decrypted, plain)
        
        # Re-encrypting should upgrade it to v2
        new_cipher = _encrypt_string(decrypted, key)
        self.assertTrue(new_cipher.startswith("v2:"))
        self.assertEqual(_decrypt_string(new_cipher, key), plain)

    def test_encryption_empty_and_corrupt(self):
        key = _get_secure_key("some_key")
        self.assertEqual(_encrypt_string("", key), "")
        self.assertEqual(_decrypt_string("", key), "")
        self.assertEqual(_decrypt_string("invalid_base64_or_fernet", key), "")
        self.assertEqual(_decrypt_string("v2:invalid_fernet", key), "")

    def test_password_key_upgrade_and_legacy_compat(self):
        password = "secret_password_123"
        
        legacy_key = _get_password_key_legacy(password)
        new_key = _get_password_key(password)
        
        self.assertNotEqual(legacy_key, new_key)
        self.assertEqual(len(legacy_key), 64)
        self.assertEqual(len(new_key), 64)
        
        # Test that encryption/decryption works with both independently
        plain = "Sensitive Data"
        
        # Legacy path
        legacy_cipher = _encrypt_string(plain, legacy_key)
        self.assertEqual(_decrypt_string(legacy_cipher, legacy_key), plain)
        
        # New PBKDF2 path
        new_cipher = _encrypt_string(plain, new_key)
        self.assertEqual(_decrypt_string(new_cipher, new_key), plain)
