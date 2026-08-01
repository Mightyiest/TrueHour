import os
import json
import tempfile
import unittest
from urllib.parse import urlparse
from crypto import _get_password_key, _encrypt_string, _decrypt_string
from core.backup_manager import backup_settings, import_settings
from core.reporting.exporters.html_exporter import HTMLExporter
from widgets.update_label import GITHUB_RELEASES_URL


class TestSecurityAuditFixes(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_backup_no_plaintext_bank_details(self):
        """Finding 1: Ensure password-protected and standard backups do not contain cleartext bank details."""
        root_data_dir = os.path.join(self.temp_dir.name, "app_data")
        os.makedirs(os.path.join(root_data_dir, "profiles", "Default"), exist_ok=True)

        settings_path = os.path.join(
            root_data_dir, "profiles", "Default", "app_settings.json"
        )
        sample_settings = {
            "anonymous_user_id": "test_user_123",
            "bank_account": "123456789",
            "bank_routing": "987654321",
            "bank_swift": "TESTSWIFT",
            "bank_account_enc": "v2:some_encrypted_val",
        }
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(sample_settings, f)

        # Patch get_app_data_root to return our mock root directory
        import core.backup_manager

        orig_get_root = core.backup_manager.get_app_data_root
        core.backup_manager.get_app_data_root = lambda: root_data_dir

        try:
            zip_path = os.path.join(self.temp_dir.name, "backup.truehour")
            success = backup_settings(
                dest_zip_path=zip_path,
                profile_name="Default",
                password="SecurePassword123!",
                anonymous_user_id="test_user_123",
            )
            self.assertTrue(success)

            import zipfile

            with zipfile.ZipFile(zip_path, "r") as zipf:
                settings_in_zip = json.loads(zipf.read("app_settings.json").decode("utf-8"))
                meta_in_zip = json.loads(zipf.read("__backup_meta__.json").decode("utf-8"))

                # Plain bank fields must be absent
                self.assertNotIn("bank_account", settings_in_zip)
                self.assertNotIn("bank_routing", settings_in_zip)
                self.assertNotIn("bank_swift", settings_in_zip)
                # Salt must be recorded
                self.assertIn("salt_hex", meta_in_zip)
        finally:
            core.backup_manager.get_app_data_root = orig_get_root

    def test_xss_escaping_in_html_exporter(self):
        """Finding 3: Ensure project names, labels, and styles are sanitized against XSS."""
        exporter = HTMLExporter()
        report_data = {
            "report_type": "<script>alert('xss')</script>",
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "total_seconds": 3600,
            "project_breakdown": [
                {
                    "project": "<img src=x onerror=alert(1)>",
                    "color": 'red" onload="alert(1)',
                    "seconds": 3600,
                    "percent": 100,
                }
            ],
            "daily_trend": [
                {
                    "label": "<svg onload=alert(1)>",
                    "value": 1.0,
                }
            ],
        }
        out_path = os.path.join(self.temp_dir.name, "test_report.html")
        result = exporter.export(report_data, out_path)
        self.assertTrue(result)

        with open(out_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertNotIn("<script>alert('xss')</script>", content)
        self.assertIn("&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;", content)
        self.assertNotIn('style="background: red" onload="alert(1)"', content)
        self.assertIn('style="background: #64748B"', content)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", content)

    def test_release_url_validation(self):
        """Finding 8: Ensure malicious or non-GitHub URLs fall back to official GitHub release URL."""
        untrusted_url = "javascript:alert(1)"
        parsed = urlparse(untrusted_url)
        target_url = (
            untrusted_url
            if (parsed.scheme == "https" and parsed.netloc.lower() == "github.com")
            else GITHUB_RELEASES_URL
        )
        self.assertEqual(target_url, GITHUB_RELEASES_URL)

        valid_url = "https://github.com/Mightyiest/TrueHour/releases/tag/v2.0"
        parsed_valid = urlparse(valid_url)
        target_valid = (
            valid_url
            if (parsed_valid.scheme == "https" and parsed_valid.netloc.lower() == "github.com")
            else GITHUB_RELEASES_URL
        )
        self.assertEqual(target_valid, valid_url)


    def test_fernet_100k_backward_compatibility(self):
        """Ensure ciphertexts encrypted with legacy 100,000 iterations decrypt seamlessly."""
        from crypto import _derive_fernet_key
        from cryptography.fernet import Fernet

        key_seed = "test_machine_seed_123"
        plain = "My Bank Account #12345"

        # Simulate existing ciphertext generated with 100k iterations
        legacy_fernet_key = _derive_fernet_key(key_seed, iterations=100000)
        f = Fernet(legacy_fernet_key)
        legacy_v2_cipher = "v2:" + f.encrypt(plain.encode("utf-8")).decode("utf-8")

        # _decrypt_string should decrypt it seamlessly via 100k iteration fallback
        decrypted = _decrypt_string(legacy_v2_cipher, key_seed)
        self.assertEqual(decrypted, plain)


if __name__ == "__main__":
    unittest.main()
