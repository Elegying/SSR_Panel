import tempfile
import unittest
from pathlib import Path

from scripts import admin_helper


class AdminHelperTests(unittest.TestCase):
    def test_rejects_unknown_actions(self):
        with self.assertRaises(ValueError):
            admin_helper.build_command("shell")

    def test_ssr_actions_expand_to_fixed_systemd_commands(self):
        self.assertEqual(
            admin_helper.build_command("ssr-restart"),
            ["/usr/bin/systemctl", "restart", "ssr.service"],
        )

    def test_panel_update_uses_only_root_owned_fixed_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            panel_dir = Path(temp_dir) / "panel"
            (panel_dir / "scripts").mkdir(parents=True)
            (panel_dir / "scripts" / "run_panel_update.py").write_text("# runner\n")
            (panel_dir / "venv" / "bin").mkdir(parents=True)
            (panel_dir / "venv" / "bin" / "python").write_text("# python\n")

            command = admin_helper.build_panel_update_command(
                panel_dir,
                {
                    "PANEL_GIT_URL": "https://github.com/Elegying/SSR_Panel.git",
                    "PANEL_GIT_BRANCH": "main",
                    "PANEL_GIT_SUBDIR": "ssr-admin-panel",
                    "PANEL_SERVICE_NAME": "ssr-admin",
                },
            )

        self.assertEqual(command[0], "/usr/bin/systemd-run")
        self.assertIn("--repo-url", command)
        self.assertIn("https://github.com/Elegying/SSR_Panel.git", command)
        self.assertNotIn("sh", command)
        self.assertNotIn("bash", command)

    def test_mudb_validation_rejects_unsafe_payloads(self):
        for payload in ({}, [{"port": 0}], [{"port": 65536}], [{"port": "18899"}]):
            with self.assertRaises(ValueError):
                admin_helper.validate_mudb_payload(payload)

    def test_mudb_validation_accepts_imported_multi_user_data(self):
        payload = [
            {
                "user": "alice",
                "passwd": "secret",
                "port": 18899,
                "enable": 1,
                "u": 0,
                "d": 0,
                "transfer_enable": 1024,
                "protocol_param": "16:alice",
            }
        ]

        self.assertIs(admin_helper.validate_mudb_payload(payload), payload)

    def test_mudb_target_rejects_world_writable_parent(self):
        with self.assertRaises(ValueError):
            admin_helper.validate_mudb_target("/tmp/mudb.json")


if __name__ == "__main__":
    unittest.main()
