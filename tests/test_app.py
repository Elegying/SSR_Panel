import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
            "SSR_INIT_SCRIPT": panel_app.SSR_INIT_SCRIPT,
            "SSR_PYTHON_BIN": panel_app.SSR_PYTHON_BIN,
            "BACKUP_DIR": panel_app.BACKUP_DIR,
        }

        panel_app.MUDB_FILE = str(self.mudb_path)
        panel_app.SSR_DIR = self.ssr_dir
        panel_app.SSR_WORKDIR = self.ssr_dir / "shadowsocks"
        panel_app.SSR_SERVER = panel_app.SSR_WORKDIR / "server.py"
        panel_app.SSR_LOG_FILE = self.log_file
        panel_app.SSR_INIT_SCRIPT = self.base_path / "etc" / "init.d" / "ssrmu"
        panel_app.SSR_PYTHON_BIN = ""
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
        panel_app.SSR_INIT_SCRIPT = self.original_state["SSR_INIT_SCRIPT"]
        panel_app.SSR_PYTHON_BIN = self.original_state["SSR_PYTHON_BIN"]
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

    def test_execute_ssr_command_prefers_init_script(self):
        panel_app.SSR_INIT_SCRIPT.parent.mkdir(parents=True, exist_ok=True)
        panel_app.SSR_INIT_SCRIPT.write_text("#!/bin/sh\n", encoding="utf-8")

        with mock.patch.object(
            panel_app,
            "run_process",
            return_value={"success": True, "output": "started", "error": ""},
        ) as run_process_mock, mock.patch.object(
            panel_app, "wait_for_ssr_status", return_value=True
        ), mock.patch.object(panel_app, "get_ssr_status", return_value="running"):
            result = panel_app.execute_ssr_command("start")

        self.assertTrue(result["success"])
        run_process_mock.assert_called_once_with([str(panel_app.SSR_INIT_SCRIPT), "start"])

    def test_execute_ssr_command_falls_back_to_server_script(self):
        panel_app.SSR_WORKDIR.mkdir(parents=True, exist_ok=True)
        panel_app.SSR_SERVER.write_text("print('ok')\n", encoding="utf-8")

        with mock.patch.object(
            panel_app, "get_ssr_python_candidates", return_value=["/usr/bin/python2"]
        ), mock.patch.object(
            panel_app,
            "run_process",
            return_value={"success": True, "output": "started", "error": ""},
        ) as run_process_mock, mock.patch.object(
            panel_app, "wait_for_ssr_status", return_value=True
        ), mock.patch.object(panel_app, "get_ssr_status", return_value="running"):
            result = panel_app.execute_ssr_command("start")

        self.assertTrue(result["success"])
        run_process_mock.assert_called_once_with(
            ["/usr/bin/python2", "server.py", "-d", "start"],
            cwd=panel_app.SSR_WORKDIR,
        )

    def test_execute_ssr_command_accepts_expected_final_state(self):
        panel_app.SSR_INIT_SCRIPT.parent.mkdir(parents=True, exist_ok=True)
        panel_app.SSR_INIT_SCRIPT.write_text("#!/bin/sh\n", encoding="utf-8")

        with mock.patch.object(
            panel_app,
            "run_process",
            return_value={"success": False, "output": "", "error": "ShadowsocksR 未运行 !"},
        ), mock.patch.object(panel_app, "wait_for_ssr_status", return_value=True), mock.patch.object(
            panel_app, "get_ssr_status", return_value="stopped"
        ):
            result = panel_app.execute_ssr_command("stop")

        self.assertTrue(result["success"])
        self.assertIn("ShadowsocksR 未运行", result["error"])

    def test_get_ssr_status_detects_running_process_from_ps(self):
        completed = mock.Mock(returncode=0, stdout="python server.py -d start\n")
        with mock.patch.object(panel_app.subprocess, "run", return_value=completed):
            self.assertEqual(panel_app.get_ssr_status(), "running")

        completed = mock.Mock(returncode=0, stdout="python3 server.py -d start\n")
        with mock.patch.object(panel_app.subprocess, "run", return_value=completed):
            self.assertEqual(panel_app.get_ssr_status(), "running")

        completed = mock.Mock(returncode=0, stdout="python app.py\n")
        with mock.patch.object(panel_app.subprocess, "run", return_value=completed):
            self.assertEqual(panel_app.get_ssr_status(), "stopped")


if __name__ == "__main__":
    unittest.main()
