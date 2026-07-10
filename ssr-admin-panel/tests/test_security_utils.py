import stat
import tempfile
import unittest
from pathlib import Path

from security_utils import hash_password, migrate_config, verify_password


class PasswordSecurityTests(unittest.TestCase):
    def test_hash_is_salted_and_verifies_only_the_original_password(self):
        first = hash_password("correct horse battery staple")
        second = hash_password("correct horse battery staple")

        self.assertNotEqual(first, second)
        self.assertNotIn("correct horse battery staple", first)
        self.assertTrue(verify_password("correct horse battery staple", first))
        self.assertFalse(verify_password("wrong", first))

    def test_malformed_hash_fails_closed(self):
        for value in ("", "plain-text", "pbkdf2_sha256$1$bad$bad", None):
            self.assertFalse(verify_password("password", value))

    def test_migrate_config_replaces_plaintext_password_atomically(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.py"
            config_path.write_text(
                "ADMIN_USER = 'admin'\n"
                "ADMIN_PASS = 'existing password'\n"
                "SECRET_KEY = 'unchanged'\n",
                encoding="utf-8",
            )
            config_path.chmod(0o640)

            self.assertTrue(migrate_config(config_path))

            content = config_path.read_text(encoding="utf-8")
            self.assertNotIn("ADMIN_PASS =", content)
            self.assertNotIn("existing password", content)
            self.assertIn("ADMIN_PASSWORD_HASH =", content)
            self.assertIn("SECRET_KEY = 'unchanged'", content)
            password_hash = next(
                line.split("=", 1)[1].strip().strip("'")
                for line in content.splitlines()
                if line.startswith("ADMIN_PASSWORD_HASH =")
            )
            self.assertTrue(verify_password("existing password", password_hash))
            self.assertEqual(stat.S_IMODE(config_path.stat().st_mode), 0o640)

    def test_migrate_config_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.py"
            password_hash = hash_password("existing password")
            original = f"ADMIN_PASSWORD_HASH = {password_hash!r}\n"
            config_path.write_text(original, encoding="utf-8")

            self.assertFalse(migrate_config(config_path))
            self.assertEqual(config_path.read_text(encoding="utf-8"), original)

    def test_migrate_config_rejects_dynamic_password_expressions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.py"
            config_path.write_text("ADMIN_PASS = get_password()\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                migrate_config(config_path)


if __name__ == "__main__":
    unittest.main()
