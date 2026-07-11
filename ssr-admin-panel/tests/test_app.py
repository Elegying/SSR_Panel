import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock
from werkzeug.middleware.proxy_fix import ProxyFix

import app as panel_app
from security_utils import hash_password


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
            "AUDIT_LOG_PATH": panel_app.AUDIT_LOG_PATH,
            "MUDB_FILE": panel_app.MUDB_FILE,
            "SSR_DIR": panel_app.SSR_DIR,
            "SSR_LOG_FILE": panel_app.SSR_LOG_FILE,
            "SSR_INIT_SCRIPT": panel_app.SSR_INIT_SCRIPT,
            "SSR_SYSTEMD_UNIT": panel_app.SSR_SYSTEMD_UNIT,
            "PRIVILEGED_HELPER": panel_app.PRIVILEGED_HELPER,
            "USER_DB_LOCK_FILE": panel_app.USER_DB_LOCK_FILE,
            "USER_DB_PENDING_FILE": panel_app.USER_DB_PENDING_FILE,
            "SSR_PYTHON_BIN": panel_app.SSR_PYTHON_BIN,
            "BACKUP_DIR": panel_app.BACKUP_DIR,
            "PANEL_GIT_URL": panel_app.PANEL_GIT_URL,
            "PANEL_GIT_SUBDIR": panel_app.PANEL_GIT_SUBDIR,
            "SSR_SHARE_HOST": panel_app.SSR_SHARE_HOST,
            "SSR_SHARE_PORT": panel_app.SSR_SHARE_PORT,
            "SSR_SHARE_PASSWORD": panel_app.SSR_SHARE_PASSWORD,
            "SSR_SHARE_REMARKS": panel_app.SSR_SHARE_REMARKS,
            "SSR_SHARE_PROTOCOL": panel_app.SSR_SHARE_PROTOCOL,
            "SSR_SHARE_METHOD": panel_app.SSR_SHARE_METHOD,
            "SSR_SHARE_OBFS": panel_app.SSR_SHARE_OBFS,
            "SSR_SHARE_OBFS_PARAM": panel_app.SSR_SHARE_OBFS_PARAM,
            "DEVICE_STATS_FILE": panel_app.DEVICE_STATS_FILE,
            "DEVICE_STATS_STALE_SECONDS": panel_app.DEVICE_STATS_STALE_SECONDS,
            "PANEL_UPDATE_STATUS_FILE": panel_app.PANEL_UPDATE_STATUS_FILE,
        }

        panel_app.AUDIT_LOG_PATH = self.base_path / "audit.log"
        panel_app.MUDB_FILE = str(self.mudb_path)
        panel_app.SSR_DIR = self.ssr_dir
        panel_app.SSR_LOG_FILE = self.log_file
        panel_app.SSR_INIT_SCRIPT = self.base_path / "etc" / "init.d" / "ssrmu"
        panel_app.SSR_SYSTEMD_UNIT = self.base_path / "systemd" / "ssr.service"
        panel_app.PRIVILEGED_HELPER = self.base_path / "admin-helper"
        panel_app.USER_DB_LOCK_FILE = self.base_path / "runtime" / "mudb.lock"
        panel_app.USER_DB_PENDING_FILE = self.base_path / "runtime" / "mudb.pending.json"
        panel_app.SSR_PYTHON_BIN = ""
        panel_app.BACKUP_DIR = self.backup_dir
        panel_app.PANEL_GIT_URL = "https://github.com/Elegying/SSR_Panel.git"
        panel_app.PANEL_GIT_SUBDIR = "ssr-admin-panel"
        panel_app.SSR_SHARE_HOST = "ssr.ssrvpn.vip"
        panel_app.SSR_SHARE_PORT = 18899
        panel_app.SSR_SHARE_PASSWORD = "nikuaimobi"
        panel_app.SSR_SHARE_REMARKS = "私家车-2025"
        panel_app.SSR_SHARE_PROTOCOL = "auth_aes128_md5"
        panel_app.SSR_SHARE_METHOD = "aes-256-cfb"
        panel_app.SSR_SHARE_OBFS = "tls1.2_ticket_auth"
        panel_app.SSR_SHARE_OBFS_PARAM = "www.baidu.com"
        panel_app.DEVICE_STATS_FILE = str(self.base_path / "device-stats.json")
        panel_app.DEVICE_STATS_STALE_SECONDS = 120
        panel_app.PANEL_UPDATE_STATUS_FILE = self.base_path / "panel-update-status.json"
        panel_app.app.config["TESTING"] = True

        self.client = panel_app.app.test_client()
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["csrf_token"] = "test-token"

    def tearDown(self):
        panel_app.AUDIT_LOG_PATH = self.original_state["AUDIT_LOG_PATH"]
        panel_app.MUDB_FILE = self.original_state["MUDB_FILE"]
        panel_app.SSR_DIR = self.original_state["SSR_DIR"]
        panel_app.SSR_LOG_FILE = self.original_state["SSR_LOG_FILE"]
        panel_app.SSR_INIT_SCRIPT = self.original_state["SSR_INIT_SCRIPT"]
        panel_app.SSR_SYSTEMD_UNIT = self.original_state["SSR_SYSTEMD_UNIT"]
        panel_app.PRIVILEGED_HELPER = self.original_state["PRIVILEGED_HELPER"]
        panel_app.USER_DB_LOCK_FILE = self.original_state["USER_DB_LOCK_FILE"]
        panel_app.USER_DB_PENDING_FILE = self.original_state["USER_DB_PENDING_FILE"]
        panel_app.SSR_PYTHON_BIN = self.original_state["SSR_PYTHON_BIN"]
        panel_app.BACKUP_DIR = self.original_state["BACKUP_DIR"]
        panel_app.PANEL_GIT_URL = self.original_state["PANEL_GIT_URL"]
        panel_app.PANEL_GIT_SUBDIR = self.original_state["PANEL_GIT_SUBDIR"]
        panel_app.SSR_SHARE_HOST = self.original_state["SSR_SHARE_HOST"]
        panel_app.SSR_SHARE_PORT = self.original_state["SSR_SHARE_PORT"]
        panel_app.SSR_SHARE_PASSWORD = self.original_state["SSR_SHARE_PASSWORD"]
        panel_app.SSR_SHARE_REMARKS = self.original_state["SSR_SHARE_REMARKS"]
        panel_app.SSR_SHARE_PROTOCOL = self.original_state["SSR_SHARE_PROTOCOL"]
        panel_app.SSR_SHARE_METHOD = self.original_state["SSR_SHARE_METHOD"]
        panel_app.SSR_SHARE_OBFS = self.original_state["SSR_SHARE_OBFS"]
        panel_app.SSR_SHARE_OBFS_PARAM = self.original_state["SSR_SHARE_OBFS_PARAM"]
        panel_app.DEVICE_STATS_FILE = self.original_state["DEVICE_STATS_FILE"]
        panel_app.DEVICE_STATS_STALE_SECONDS = self.original_state["DEVICE_STATS_STALE_SECONDS"]
        panel_app.PANEL_UPDATE_STATUS_FILE = self.original_state["PANEL_UPDATE_STATUS_FILE"]
        self.temp_dir.cleanup()

    def write_users(self, users):
        self.mudb_path.write_text(json.dumps(users), encoding="utf-8")

    def read_users(self):
        return json.loads(self.mudb_path.read_text(encoding="utf-8"))

    def test_forwarded_headers_are_not_trusted_by_default(self):
        self.assertFalse(panel_app.TRUST_PROXY)
        self.assertNotIsInstance(panel_app.app.wsgi_app, ProxyFix)

    def test_health_check_exercises_user_database_without_authentication(self):
        self.write_users([])
        with self.client.session_transaction() as sess:
            sess.clear()

        healthy = self.client.get("/healthz")
        self.assertEqual(healthy.status_code, 200)
        self.assertEqual(healthy.get_json(), {"status": "ok"})

        self.mudb_path.write_text("not-json", encoding="utf-8")
        unhealthy = self.client.get("/healthz")
        self.assertEqual(unhealthy.status_code, 500)
        self.assertFalse(unhealthy.get_json()["success"])

    def test_audit_log_escapes_untrusted_line_breaks(self):
        with panel_app.app.test_request_context("/login", environ_base={"REMOTE_ADDR": "127.0.0.1"}):
            panel_app.audit_log("LOGIN_FAILED", "username: attacker\n[FORGED] success", "WARNING")

        entries = panel_app.AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(entries), 1)
        self.assertIn(r"attacker\n[FORGED]", entries[0])

    def test_backup_serializes_a_validated_database_snapshot(self):
        users = [{"user": "alice", "port": 18899}]
        self.write_users(users)

        response = self.client.post("/api/backup", headers={"X-CSRF-Token": "test-token"})

        self.assertEqual(response.status_code, 200)
        backups = list(self.backup_dir.glob("mudb_*.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(json.loads(backups[0].read_text(encoding="utf-8")), users)

    def test_backup_refuses_to_copy_a_corrupt_database(self):
        self.mudb_path.write_text("not-json", encoding="utf-8")

        response = self.client.post("/api/backup", headers={"X-CSRF-Token": "test-token"})

        self.assertEqual(response.status_code, 500)
        self.assertFalse(list(self.backup_dir.glob("mudb_*.json")))

    def test_server_optimization_status_treats_udp443_block_as_optional(self):
        self.write_users([{"user": "u1", "forbidden_ip": "127.0.0.0/8,::1/128,::/0"}])

        def fake_run(args, **kwargs):
            if args == ["nft", "list", "table", "inet", "ssr_filter"]:
                return mock.Mock(returncode=0, stdout="table inet ssr_filter { }")
            if args == ["sysctl", "-n", "net.ipv4.tcp_congestion_control"]:
                return mock.Mock(returncode=0, stdout="bbr\n")
            if args == ["sysctl", "-n", "net.core.default_qdisc"]:
                return mock.Mock(returncode=0, stdout="fq\n")
            raise AssertionError(f"unexpected command: {args}")

        with mock.patch.object(panel_app.subprocess, "run", side_effect=fake_run):
            status = panel_app.get_server_optimization_status()

        self.assertTrue(status["ipv6_guard"])
        self.assertFalse(status["quic_guard"])
        self.assertTrue(status["enabled"])
        self.assertEqual(status["label"], "已启用")

    def post_json(self, url, payload=None):
        return self.client.post(
            url,
            json=payload,
            headers={"X-CSRF-Token": "test-token"},
        )

    def test_api_users_returns_users_in_reverse_file_order(self):
        self.write_users(
            [
                {"user": "oldest", "passwd": "secret", "port": 1001, "enable": 1},
                {"user": "middle", "passwd": "secret", "port": 1002, "enable": 1},
                {"user": "newest", "passwd": "secret", "port": 1003, "enable": 1},
            ]
        )

        response = self.client.get("/api/users")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual([user["user"] for user in payload["data"]], ["newest", "middle", "oldest"])

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

    def test_api_users_includes_device_counts_from_stats_file(self):
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
                    "protocol_param": "3:u1",
                }
            ]
        )
        Path(panel_app.DEVICE_STATS_FILE).write_text(
            json.dumps(
                {
                    "generated_at_ts": time.time(),
                    "window_seconds": 900,
                    "ports": {
                        "1234": {
                            "online_count": 2,
                            "recent_count": 3,
                            "last_seen": "2026-04-28T12:00:00+00:00",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        response = self.client.get("/api/users")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        user = payload["data"][0]
        self.assertEqual(user["device_limit"], 3)
        self.assertEqual(user["online_device_count"], 2)
        self.assertEqual(user["recent_device_count"], 3)
        self.assertFalse(payload["device_stats"]["stale"])

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

    def test_update_remains_available_until_security_migration_finishes(self):
        with mock.patch.object(panel_app, "get_panel_version", return_value="1.4.0"), mock.patch.object(
            panel_app,
            "resolve_latest_panel_version",
            return_value={"success": True, "version": "1.4.0", "display_version": "1.4.0"},
        ), mock.patch.object(panel_app, "panel_security_migration_required", return_value=True, create=True):
            info = panel_app.collect_panel_update_info(fetch_remote=True)

        self.assertTrue(info["update_available"])
        self.assertIn("安全迁移", info["message"])

    def test_root_legacy_update_bootstraps_helper_before_panel_update(self):
        success = {"success": True, "output": "", "error": ""}
        with mock.patch.object(
            panel_app, "privileged_helper_available", side_effect=[False, True]
        ), mock.patch.object(
            panel_app, "panel_security_migration_required", return_value=True, create=True
        ), mock.patch.object(
            panel_app.os, "geteuid", return_value=0
        ), mock.patch.object(
            panel_app, "run_process", side_effect=[success, success]
        ) as run_process_mock:
            result = panel_app.run_privileged_action("panel-update")

        self.assertTrue(result["success"])
        self.assertEqual(run_process_mock.call_args_list[0].args[0][:2], ["bash", str(panel_app.PANEL_DIR / "scripts" / "provision_panel_runtime.sh")])
        self.assertEqual(run_process_mock.call_args_list[1].args[0][-1], "panel-update")

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

    def test_login_requires_csrf_token(self):
        with self.client.session_transaction() as sess:
            sess.clear()
            sess["csrf_token"] = "login-token"

        with mock.patch.object(panel_app, "ADMIN_USER", "admin"), mock.patch.object(
            panel_app, "ADMIN_PASSWORD_HASH", hash_password("secret")
        ):
            missing = self.client.post("/login", data={"username": "admin", "password": "secret"})
            self.assertEqual(missing.status_code, 200)
            self.assertIn("页面已过期", missing.get_data(as_text=True))

            ok = self.client.post(
                "/login",
                data={"username": "admin", "password": "secret", "csrf_token": "login-token"},
            )
            self.assertEqual(ok.status_code, 302)

    def test_login_form_contains_csrf_token(self):
        with self.client.session_transaction() as sess:
            sess.clear()

        response = self.client.get("/login")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('name="csrf_token"', body)

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

    def test_panel_update_status_includes_rollback_metadata_defaults(self):
        with mock.patch.object(panel_app, "get_panel_update_unit_state", return_value="inactive"):
            status = panel_app.read_panel_update_status()

        self.assertEqual(status["phase"], "idle")
        self.assertEqual(status["backup_dir"], "")
        self.assertFalse(status["rollback_attempted"])
        self.assertFalse(status["rollback_success"])

    def test_start_panel_update_uses_allowlisted_privileged_helper(self):
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
            panel_app,
            "run_privileged_action",
            return_value={"success": True, "output": "detached", "error": ""},
            create=True,
        ) as privileged_mock:
            result = panel_app.start_panel_update()

        self.assertTrue(result["success"])
        privileged_mock.assert_called_once_with("panel-update")

    def test_start_panel_update_writes_queued_status_before_launch(self):
        runner_path = self.base_path / "run_panel_update.py"
        runner_path.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

        def assert_status_exists_before_launch(_action):
            status = json.loads(panel_app.PANEL_UPDATE_STATUS_FILE.read_text(encoding="utf-8"))
            self.assertTrue(status["in_progress"])
            self.assertEqual(status["phase"], "queued")
            return {"success": True, "output": "detached", "error": ""}

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
            panel_app, "run_privileged_action", side_effect=assert_status_exists_before_launch, create=True
        ):
            result = panel_app.start_panel_update()

        self.assertTrue(result["success"])

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

    def test_user_add_and_delete_sync_the_firewall_without_hiding_success(self):
        self.write_users([])

        with mock.patch.object(
            panel_app,
            "run_privileged_action",
            return_value={"success": False, "output": "", "error": "firewall unavailable"},
            create=True,
        ) as privileged_mock, mock.patch.object(panel_app, "audit_log") as audit_mock:
            added = self.post_json(
                "/api/add",
                {"port": 9001, "user": "firewall-user", "password": "pw", "transfer": 2048},
            )
            deleted = self.client.post(
                "/api/delete/firewall-user",
                headers={"X-CSRF-Token": "test-token"},
            )

        self.assertEqual(added.status_code, 200)
        self.assertTrue(added.get_json()["success"])
        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(deleted.get_json()["success"])
        self.assertEqual(
            privileged_mock.call_args_list,
            [
                mock.call("firewall-sync"),
                mock.call("firewall-sync"),
            ],
        )
        warning_calls = [call for call in audit_mock.call_args_list if call.kwargs.get("level") == "WARNING"]
        self.assertEqual(len(warning_calls), 2)

    def test_save_users_is_atomic_when_json_dump_fails(self):
        original = [{"user": "existing", "passwd": "pw", "port": 8080}]
        self.write_users(original)

        with mock.patch.object(panel_app.json, "dump", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                panel_app.save_users([{"user": "new", "passwd": "pw", "port": 9090}])

        self.assertEqual(self.read_users(), original)
        self.assertFalse(list(self.mudb_path.parent.glob(".mudb.json.*.tmp")))

    def test_save_users_refuses_to_overwrite_corrupt_database(self):
        original = b"{broken-json\n"
        self.mudb_path.write_bytes(original)

        with self.assertRaises(panel_app.UserDatabaseError):
            panel_app.save_users([{"user": "new", "passwd": "pw", "port": 9090}])

        self.assertEqual(self.mudb_path.read_bytes(), original)

    def test_save_users_stages_data_before_privileged_commit(self):
        original = [{"user": "existing", "passwd": "pw", "port": 8080}]
        replacement = [{"user": "new", "passwd": "pw", "port": 18899}]
        self.write_users(original)
        panel_app.PRIVILEGED_HELPER.write_text("#!/usr/bin/python3\n", encoding="utf-8")

        def commit_staged(action):
            self.assertEqual(action, "mudb-commit")
            staged = json.loads(panel_app.USER_DB_PENDING_FILE.read_text(encoding="utf-8"))
            self.assertEqual(staged, replacement)
            panel_app._write_users_unlocked(self.mudb_path, staged)
            panel_app.USER_DB_PENDING_FILE.unlink()
            return {"success": True, "output": "", "error": ""}

        with mock.patch.object(panel_app, "run_privileged_action", side_effect=commit_staged):
            panel_app.save_users(replacement)

        self.assertEqual(self.read_users(), replacement)
        self.assertFalse(panel_app.USER_DB_PENDING_FILE.exists())

    def test_add_user_refuses_to_overwrite_corrupt_database(self):
        original = b"{broken-json\n"
        self.mudb_path.write_bytes(original)

        response = self.post_json(
            "/api/add",
            {
                "port": 9001,
                "user": "demo-user",
                "password": "",
                "transfer": 2048,
            },
        )

        self.assertEqual(response.status_code, 500)
        self.assertFalse(response.get_json()["success"])
        self.assertEqual(self.mudb_path.read_bytes(), original)

    def test_concurrent_adds_preserve_both_users(self):
        self.write_users([])
        mutation_barrier = threading.Barrier(2)
        original_mutate = panel_app.mutate_users
        responses = {}
        errors = []

        def synchronized_mutate(mutator):
            mutation_barrier.wait(timeout=2)
            return original_mutate(mutator)

        def add_user(name, port):
            try:
                client = panel_app.app.test_client()
                with client.session_transaction() as sess:
                    sess["logged_in"] = True
                    sess["csrf_token"] = "test-token"
                responses[name] = client.post(
                    "/api/add",
                    json={"port": port, "user": name, "password": "", "transfer": 2048},
                    headers={"X-CSRF-Token": "test-token"},
                )
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        with mock.patch.object(panel_app, "mutate_users", side_effect=synchronized_mutate):
            first = threading.Thread(target=add_user, args=("first", 9001))
            second = threading.Thread(target=add_user, args=("second", 9002))
            first.start()
            second.start()
            first.join(timeout=2)
            second.join(timeout=2)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertFalse(errors)
        self.assertEqual(responses["first"].status_code, 200)
        self.assertEqual(responses["second"].status_code, 200)
        self.assertEqual({user["user"] for user in self.read_users()}, {"first", "second"})

    def test_add_user_validates_input_and_returns_created_password(self):
        self.write_users([])

        bad_response = self.post_json("/api/add", {"port": "abc"})
        self.assertEqual(bad_response.status_code, 400)

        fractional_port = self.post_json("/api/add", {"port": 9001.5, "transfer": 2048})
        self.assertEqual(fractional_port.status_code, 400)

        fractional_transfer = self.post_json("/api/add", {"port": 9001, "transfer": 2048.5})
        self.assertEqual(fractional_transfer.status_code, 400)
        self.assertEqual(self.read_users(), [])

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

    def test_execute_ssr_command_uses_allowlisted_privileged_helper(self):
        with mock.patch.object(
            panel_app,
            "run_privileged_action",
            return_value={"success": True, "output": "started", "error": ""},
            create=True,
        ) as privileged_mock, mock.patch.object(
            panel_app, "wait_for_ssr_status", return_value=True
        ), mock.patch.object(panel_app, "get_ssr_status", return_value="running"):
            result = panel_app.execute_ssr_command("restart")

        self.assertTrue(result["success"])
        privileged_mock.assert_called_once_with("ssr-restart")

    def test_execute_ssr_command_rejects_unknown_action_before_privilege_boundary(self):
        with mock.patch.object(
            panel_app,
            "run_privileged_action",
            return_value={"success": True, "output": "", "error": ""},
            create=True,
        ) as privileged_mock:
            result = panel_app.execute_ssr_command("shell")

        self.assertFalse(result["success"])
        privileged_mock.assert_not_called()

    def test_execute_ssr_command_reports_unreached_final_state(self):
        with mock.patch.object(
            panel_app,
            "run_privileged_action",
            return_value={"success": True, "output": "started", "error": ""},
            create=True,
        ), mock.patch.object(
            panel_app, "wait_for_ssr_status", return_value=False
        ), mock.patch.object(panel_app, "get_ssr_status", return_value="stopped"):
            result = panel_app.execute_ssr_command("start")

        self.assertFalse(result["success"])
        self.assertIn("stopped", result["error"])

    def test_execute_ssr_command_accepts_expected_final_state(self):
        with mock.patch.object(
            panel_app,
            "run_privileged_action",
            return_value={"success": False, "output": "", "error": "ShadowsocksR 未运行 !"},
            create=True,
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

    def test_get_ssr_status_prefers_stopped_phrases(self):
        panel_app.SSR_INIT_SCRIPT.parent.mkdir(parents=True)
        panel_app.SSR_INIT_SCRIPT.touch()

        for output in ("ShadowsocksR is not running", "ssr.service is inactive"):
            with self.subTest(output=output), mock.patch.object(
                panel_app,
                "run_process",
                return_value={"success": False, "output": output, "error": ""},
            ):
                self.assertEqual(panel_app.get_ssr_status(), "stopped")


    def test_login_get_not_rate_limited(self):
        """Regression: GET /login should not be rate-limited (fix 429 on page refresh)."""
        with self.client.session_transaction() as sess:
            sess.clear()
            sess["csrf_token"] = "test-token"

        for i in range(8):
            response = self.client.get("/login")
            self.assertEqual(response.status_code, 200, f"GET /login #{i+1} returned {response.status_code}")


if __name__ == "__main__":
    unittest.main()
