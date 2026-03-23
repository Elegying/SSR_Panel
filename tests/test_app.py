import json
import tempfile
import unittest
from pathlib import Path

import app as panel_app


class AppSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.mudb_path = self.base_path / "mudb.json"
        self.ssr_dir = self.base_path / "ssr"
        self.ssr_dir.mkdir()
        self.log_file = self.ssr_dir / "ssserver.log"
        self.log_file.write_text("line1\nline2\n", encoding="utf-8")
        self.backup_dir = self.base_path / "backups"

        self.original_state = {
            "MUDB_FILE": panel_app.MUDB_FILE,
            "SSR_DIR": panel_app.SSR_DIR,
            "SSR_WORKDIR": panel_app.SSR_WORKDIR,
            "SSR_SERVER": panel_app.SSR_SERVER,
            "SSR_LOG_FILE": panel_app.SSR_LOG_FILE,
            "BACKUP_DIR": panel_app.BACKUP_DIR,
        }

        panel_app.MUDB_FILE = str(self.mudb_path)
        panel_app.SSR_DIR = self.ssr_dir
        panel_app.SSR_WORKDIR = self.ssr_dir / "shadowsocks"
        panel_app.SSR_SERVER = panel_app.SSR_WORKDIR / "server.py"
        panel_app.SSR_LOG_FILE = self.log_file
        panel_app.BACKUP_DIR = self.backup_dir
        panel_app.app.config["TESTING"] = True

        self.client = panel_app.app.test_client()
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["csrf_token"] = "test-token"

    def tearDown(self):
        panel_app.MUDB_FILE = self.original_state["MUDB_FILE"]
        panel_app.SSR_DIR = self.original_state["SSR_DIR"]
        panel_app.SSR_WORKDIR = self.original_state["SSR_WORKDIR"]
        panel_app.SSR_SERVER = self.original_state["SSR_SERVER"]
        panel_app.SSR_LOG_FILE = self.original_state["SSR_LOG_FILE"]
        panel_app.BACKUP_DIR = self.original_state["BACKUP_DIR"]
        self.temp_dir.cleanup()

    def write_users(self, users):
        self.mudb_path.write_text(json.dumps(users), encoding="utf-8")

    def read_users(self):
        return json.loads(self.mudb_path.read_text(encoding="utf-8"))

    def post_json(self, url, payload=None):
        return self.client.post(
            url,
            json=payload,
            headers={"X-CSRF-Token": "test-token"},
        )

    def test_api_users_handles_zero_transfer_limit(self):
        self.write_users(
            [
                {
                    "user": "u1",
                    "passwd": "secret",
                    "u": 1,
                    "d": 2,
                    "transfer_enable": 0,
                    "port": 1234,
                    "enable": 1,
                }
            ]
        )

        response = self.client.get("/api/users")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"][0]["usage_percent"], 0)
        self.assertEqual(payload["data"][0]["download_human"], "2.00 B")
        self.assertEqual(payload["data"][0]["transfer_limit_human"], "不限")
        self.assertNotIn("passwd", payload["data"][0])

    def test_ssr_log_rejects_injected_lines_argument(self):
        response = self.client.get("/api/ssr/log?lines=1;echo%20INJECTED")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertNotIn("INJECTED", payload["output"])
        self.assertIn("line1", payload["output"])

    def test_delete_requires_post_and_csrf(self):
        self.write_users(
            [
                {
                    "user": "alice",
                    "passwd": "pw",
                    "u": 0,
                    "d": 0,
                    "transfer_enable": 1024,
                    "port": 8080,
                    "enable": 1,
                }
            ]
        )

        get_response = self.client.get("/api/delete/alice")
        self.assertEqual(get_response.status_code, 405)

        missing_csrf = self.client.post("/api/delete/alice")
        self.assertEqual(missing_csrf.status_code, 403)

        ok_response = self.client.post(
            "/api/delete/alice",
            headers={"X-CSRF-Token": "test-token"},
        )
        self.assertEqual(ok_response.status_code, 200)
        self.assertEqual(self.read_users(), [])

    def test_add_user_validates_input_and_returns_created_password(self):
        self.write_users([])

        bad_response = self.post_json("/api/add", {"port": "abc"})
        self.assertEqual(bad_response.status_code, 400)

        ok_response = self.post_json(
            "/api/add",
            {
                "port": 9001,
                "user": "demo-user",
                "password": "",
                "transfer": 2048,
            },
        )
        payload = ok_response.get_json()

        self.assertEqual(ok_response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["user"]["user"], "demo-user")
        self.assertTrue(payload["user"]["generated_password"])
        self.assertNotIn("passwd", payload["user"])


if __name__ == "__main__":
    unittest.main()
