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
            "PANEL_GIT_URL": panel_app.PANEL_GIT_URL,
            "SSR_SHARE_HOST": panel_app.SSR_SHARE_HOST,
            "SSR_SHARE_PORT": panel_app.SSR_SHARE_PORT,
            "SSR_SHARE_PASSWORD": panel_app.SSR_SHARE_PASSWORD,
            "SSR_SHARE_REMARKS": panel_app.SSR_SHARE_REMARKS,
            "SSR_SHARE_PROTOCOL": panel_app.SSR_SHARE_PROTOCOL,
            "SSR_SHARE_METHOD": panel_app.SSR_SHARE_METHOD,
            "SSR_SHARE_OBFS": panel_app.SSR_SHARE_OBFS,
            "SSR_SHARE_OBFS_PARAM": panel_app.SSR_SHARE_OBFS_PARAM,
        }

        panel_app.MUDB_FILE = str(self.mudb_path)
        panel_app.SSR_DIR = self.ssr_dir
        panel_app.SSR_WORKDIR = self.ssr_dir / "shadowsocks"
        panel_app.SSR_SERVER = panel_app.SSR_WORKDIR / "server.py"
        panel_app.SSR_LOG_FILE = self.log_file
        panel_app.SSR_INIT_SCRIPT = self.base_path / "etc" / "init.d" / "ssrmu"
        panel_app.SSR_PYTHON_BIN = ""
        panel_app.BACKUP_DIR = self.backup_dir
        panel_app.PANEL_GIT_URL = "https://github.com/Elegying/ssr-admin-panel.git"
        panel_app.SSR_SHARE_HOST = "ssr.ssrvpn.vip"
        panel_app.SSR_SHARE_PORT = 18899
        panel_app.SSR_SHARE_PASSWORD = "nikuaimobi"
        panel_app.SSR_SHARE_REMARKS = "私家车-2025"
        panel_app.SSR_SHARE_PROTOCOL = "auth_aes128_md5"
        panel_app.SSR_SHARE_METHOD = "aes-256-cfb"
        panel_app.SSR_SHARE_OBFS = "tls1.2_ticket_auth"
        panel_app.SSR_SHARE_OBFS_PARAM = "www.baidu.com"
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
        panel_app.PANEL_GIT_URL = self.original_state["PANEL_GIT_URL"]
        panel_app.SSR_SHARE_HOST = self.original_state["SSR_SHARE_HOST"]
        panel_app.SSR_SHARE_PORT = self.original_state["SSR_SHARE_PORT"]
        panel_app.SSR_SHARE_PASSWORD = self.original_state["SSR_SHARE_PASSWORD"]
        panel_app.SSR_SHARE_REMARKS = self.original_state["SSR_SHARE_REMARKS"]
        panel_app.SSR_SHARE_PROTOCOL = self.original_state["SSR_SHARE_PROTOCOL"]
        panel_app.SSR_SHARE_METHOD = self.original_state["SSR_SHARE_METHOD"]
        panel_app.SSR_SHARE_OBFS = self.original_state["SSR_SHARE_OBFS"]
        panel_app.SSR_SHARE_OBFS_PARAM = self.original_state["SSR_SHARE_OBFS_PARAM"]
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

    def test_panel_update_check_endpoint_returns_update_info(self):
        with mock.patch.object(
            panel_app,
            "collect_panel_update_info",
            return_value={
                "success": True,
                "current_version": "old123",
                "latest_version": "new456",
                "update_available": True,
                "message": "发现新版本 new456",
            },
        ):
            response = self.client.get("/api/panel/update/check")

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["update_available"])
        self.assertEqual(payload["latest_version"], "new456")

    def test_collect_panel_update_info_falls_back_to_repo_check_without_git_workspace(self):
        with mock.patch.object(panel_app, "is_panel_git_workspace", return_value=False), mock.patch.object(
            panel_app, "get_panel_version", return_value="1.1.0"
        ), mock.patch.object(
            panel_app,
            "fetch_remote_panel_version_from_repo",
            return_value={"success": True, "version": "1.2.0", "message": ""},
        ) as fetch_remote:
            info = panel_app.collect_panel_update_info(fetch_remote=True)

        self.assertTrue(info["success"])
        self.assertTrue(info["update_available"])
        self.assertEqual(info["latest_version"], "1.2.0")
        fetch_remote.assert_called_once_with()

    def test_collect_panel_update_info_detects_revision_change_when_version_file_is_unchanged(self):
        with mock.patch.object(panel_app, "is_panel_git_workspace", return_value=False), mock.patch.object(
            panel_app, "get_panel_version", return_value="1.1.0"
        ), mock.patch.object(
            panel_app,
            "fetch_remote_panel_version_from_repo",
            return_value={
                "success": True,
                "version": "1.1.0",
                "revision": "4767677",
                "display_version": "1.1.0 (4767677)",
                "message": "",
            },
        ):
            info = panel_app.collect_panel_update_info(fetch_remote=True)

        self.assertTrue(info["success"])
        self.assertTrue(info["update_available"])
        self.assertEqual(info["latest_version"], "1.1.0 (4767677)")
        self.assertEqual(info["message"], "发现新版本 1.1.0 (4767677)")

    def test_get_panel_version_prefers_build_metadata_without_git_workspace(self):
        build_info_path = self.base_path / ".panel-build.json"
        build_info_path.write_text(
            json.dumps(
                {
                    "version": "1.1.0",
                    "revision": "4767677",
                    "display_version": "1.1.0 (4767677)",
                }
            ),
            encoding="utf-8",
        )

        with mock.patch.object(panel_app, "PANEL_DIR", self.base_path), mock.patch.object(
            panel_app, "PANEL_BUILD_INFO_FILE", build_info_path
        ), mock.patch.object(panel_app, "PANEL_VERSION_FILE", self.base_path / "VERSION"):
            self.assertEqual(panel_app.get_panel_version(), "1.1.0 (4767677)")

    def test_panel_update_start_requires_csrf(self):
        response = self.client.post("/api/panel/update")
        self.assertEqual(response.status_code, 403)

    def test_panel_update_start_endpoint_returns_started_result(self):
        with mock.patch.object(
            panel_app,
            "start_panel_update",
            return_value={
                "success": True,
                "message": "更新任务已启动",
                "current_version": "old123",
                "latest_version": "new456",
            },
        ):
            response = self.post_json("/api/panel/update")

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["latest_version"], "new456")

    def test_start_panel_update_passes_repo_url_to_runner(self):
        runner_path = self.base_path / "run_panel_update.py"
        runner_path.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

        with mock.patch.object(panel_app, "PANEL_UPDATE_RUNNER", runner_path), mock.patch.object(
            panel_app, "read_panel_update_status", return_value={"in_progress": False}
        ), mock.patch.object(
            panel_app,
            "collect_panel_update_info",
            return_value={
                "success": True,
                "current_version": "1.1.0",
                "latest_version": "1.2.0",
                "update_available": True,
                "message": "发现新版本 1.2.0",
            },
        ), mock.patch.object(
            panel_app, "get_panel_repo_url", return_value="https://github.com/Elegying/ssr-admin-panel.git"
        ), mock.patch.object(
            panel_app.shutil, "which", return_value="/bin/systemd-run"
        ), mock.patch.object(
            panel_app, "run_process", return_value={"success": True, "output": "detached", "error": ""}
        ) as run_process_mock:
            result = panel_app.start_panel_update()

        self.assertTrue(result["success"])
        command = run_process_mock.call_args.args[0]
        self.assertIn("--repo-url", command)
        self.assertIn("https://github.com/Elegying/ssr-admin-panel.git", command)

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

    def test_build_ssr_share_url_matches_expected_format(self):
        share_url = panel_app.build_ssr_share_url(
            {
                "user": "1000",
                "passwd": "yingjie1r",
            },
            "",
        )

        self.assertEqual(
            share_url,
            "ssr://c3NyLnNzcnZwbi52aXA6MTg4OTk6YXV0aF9hZXMxMjhfbWQ1OmFlcy0yNTYtY2ZiOnRsczEuMl90aWNrZXRfYXV0aDpibWxyZFdGcGJXOWlhUS8_cmVtYXJrcz01NmVCNWE2MjZMMm1MVEl3TWpVJnByb3RvcGFyYW09TVRBd01EcDVhVzVuYW1sbE1YSSZvYmZzcGFyYW09ZDNkM0xtSmhhV1IxTG1OdmJR",
        )

    def test_build_ssr_share_url_requires_private_template(self):
        panel_app.SSR_SHARE_HOST = ""
        panel_app.SSR_SHARE_PASSWORD = ""
        panel_app.SSR_SHARE_REMARKS = ""

        with self.assertRaisesRegex(ValueError, "SSR_SHARE_"):
            panel_app.build_ssr_share_url({"user": "1000", "passwd": "yingjie1r"}, "")

    def test_share_user_returns_ssr_link(self):
        self.write_users(
            [
                {
                    "user": "1000",
                    "passwd": "yingjie1r",
                    "u": 0,
                    "d": 0,
                    "transfer_enable": 1024,
                    "port": 8080,
                    "enable": 1,
                    "method": "aes-256-cfb",
                    "protocol": "auth_aes128_md5",
                    "obfs": "tls1.2_ticket_auth",
                    "obfs_param": "www.baidu.com",
                    "protocol_param": "16:alice",
                }
            ]
        )

        response = self.client.post("/api/share/1000", headers={"X-CSRF-Token": "test-token"})
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertEqual(
            payload["share_url"],
            "ssr://c3NyLnNzcnZwbi52aXA6MTg4OTk6YXV0aF9hZXMxMjhfbWQ1OmFlcy0yNTYtY2ZiOnRsczEuMl90aWNrZXRfYXV0aDpibWxyZFdGcGJXOWlhUS8_cmVtYXJrcz01NmVCNWE2MjZMMm1MVEl3TWpVJnByb3RvcGFyYW09TVRBd01EcDVhVzVuYW1sbE1YSSZvYmZzcGFyYW09ZDNkM0xtSmhhV1IxTG1OdmJR",
        )

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
