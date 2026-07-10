import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
UPDATE_SCRIPT = REPO_ROOT / "update.sh"


class HealthyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, _format, *_args):
        return


class UpdateTransactionTests(unittest.TestCase):
    def write_executable(self, path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def run_git(self, *args: str, cwd: Path) -> None:
        result = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def make_fixture(self, base: Path, *, fail_restart: bool):
        base = base.resolve()
        panel = base / "panel"
        panel.mkdir()
        (panel / "app.py").write_text("OLD_APP = True\n", encoding="utf-8")
        (panel / "VERSION").write_text("1.0.0\n", encoding="utf-8")
        (panel / "config.py").write_text("SECRET = 'keep'\n", encoding="utf-8")
        (panel / "local-note.txt").write_text("keep me\n", encoding="utf-8")

        venv = panel / "venv"
        (venv / "bin").mkdir(parents=True)
        marker = venv / "state.txt"
        marker.write_text("old\n", encoding="utf-8")
        self.write_executable(
            venv / "bin" / "python",
            "#!/bin/sh\n"
            "if [ \"${1:-}\" = -m ] && [ \"${2:-}\" = pip ]; then\n"
            "  if [ \"${3:-}\" = --version ]; then echo 'pip 1'; exit 0; fi\n"
            "  printf 'new\\n' > \"$VENV_MARKER\"\n"
            "  exit 0\n"
            "fi\n"
            "case \"${1:-}\" in\n"
            "  -c) case \"${2:-}\" in *'import flask'*) exit 0;; esac;;\n"
            "esac\n"
            f"exec {sys.executable} \"$@\"\n",
        )

        source_repo = base / "source"
        source_panel = source_repo / "ssr-admin-panel"
        source_panel.mkdir(parents=True)
        (source_panel / "app.py").write_text("NEW_APP = True\n", encoding="utf-8")
        (source_panel / "VERSION").write_text("2.0.0\n", encoding="utf-8")
        (source_panel / "requirements.txt").write_text("Flask\n", encoding="utf-8")
        (source_panel / "scripts").mkdir()
        (source_panel / "scripts" / "collect_device_stats.py").write_text(
            "#!/usr/bin/env python3\n",
            encoding="utf-8",
        )
        (source_panel / "assets").mkdir()
        (source_panel / "assets" / "new.txt").write_text("new asset\n", encoding="utf-8")
        self.run_git("init", "-b", "main", cwd=source_repo)
        self.run_git("config", "user.name", "SSR Panel Test", cwd=source_repo)
        self.run_git("config", "user.email", "test@example.invalid", cwd=source_repo)
        self.run_git("add", ".", cwd=source_repo)
        self.run_git("commit", "-m", "fixture", cwd=source_repo)

        bin_dir = base / "bin"
        bin_dir.mkdir()
        self.write_executable(bin_dir / "flock", "#!/bin/sh\nexit 0\n")
        self.write_executable(bin_dir / "ss", "#!/bin/sh\nexit 0\n")
        self.write_executable(
            bin_dir / "systemctl",
            "#!/bin/sh\n"
            "echo \"$@\" >> \"$SYSTEMCTL_LOG\"\n"
            "command=${1:-}\n"
            "shift || true\n"
            "service=\n"
            "for arg in \"$@\"; do service=$arg; done\n"
            "case \"$command\" in\n"
            "  show-environment) exit 0 ;;\n"
            "  is-enabled)\n"
            "    [ \"$service\" = \"$PANEL_SERVICE\" ] && exit 0\n"
            "    exit 1\n"
            "    ;;\n"
            "  is-active)\n"
            "    [ \"$service\" = \"$PANEL_SERVICE\" ] && exit 0\n"
            "    exit 1\n"
            "    ;;\n"
            "  daemon-reload)\n"
            "    if [ \"${BLOCK_DAEMON_RELOAD:-0}\" = 1 ] && [ ! -e \"$BLOCK_USED\" ]; then\n"
            "      : > \"$BLOCK_USED\"\n"
            "      : > \"$BLOCK_READY\"\n"
            "      trap 'exit 143' TERM INT HUP\n"
            "      while [ ! -e \"$BLOCK_RELEASE\" ]; do sleep 0.05; done\n"
            "    fi\n"
            "    ;;\n"
            "  restart)\n"
            "    if [ \"${FAIL_PANEL_RESTART:-0}\" = 1 ] && [ \"$service\" = \"$PANEL_SERVICE\" ]; then\n"
            "      exit 1\n"
            "    fi\n"
            "    ;;\n"
            "esac\n"
            "exit 0\n",
        )

        systemd_dir = base / "systemd"
        systemd_dir.mkdir()
        (systemd_dir / "ssr-admin.service").write_text("OLD_PANEL_UNIT\n", encoding="utf-8")

        status_file = base / "status.json"
        env = {
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "SSR_ADMIN_SKIP_ROOT_CHECK": "1",
            "SSR_ADMIN_PANEL_DIR": str(panel),
            "SSR_ADMIN_VENV_DIR": str(venv),
            "SSR_ADMIN_SYSTEMD_DIR": str(systemd_dir),
            "SSR_ADMIN_REPO_URL": str(source_repo),
            "SSR_ADMIN_REPO_SUBDIR": "ssr-admin-panel",
            "SSR_ADMIN_UPDATE_STATUS_FILE": str(status_file),
            "SSR_ADMIN_UPDATE_LOCK_FILE": str(base / "update.lock"),
            "SSR_ADMIN_SSR_DIR": str(base / "missing-ssr"),
            "SSR_DEVICE_STATS_FILE": str(base / "device-stats" / "stats.json"),
            "SYSTEMCTL_LOG": str(base / "systemctl.log"),
            "VENV_MARKER": str(marker),
            "PANEL_SERVICE": "ssr-admin",
            "FAIL_PANEL_RESTART": "1" if fail_restart else "0",
            "BLOCK_READY": str(base / "block.ready"),
            "BLOCK_USED": str(base / "block.used"),
            "BLOCK_RELEASE": str(base / "block.release"),
        }
        return panel, marker, status_file, env

    def test_post_sync_failure_restores_application_and_virtualenv(self):
        if not shutil.which("bash") or not shutil.which("git"):
            self.skipTest("bash and git are required")

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            panel, marker, status_file, env = self.make_fixture(base, fail_restart=True)
            result = subprocess.run(
                ["bash", str(UPDATE_SCRIPT), "main"],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((panel / "app.py").read_text(encoding="utf-8"), "OLD_APP = True\n")
            self.assertEqual(marker.read_text(encoding="utf-8"), "old\n")
            self.assertEqual(
                (base / "systemd" / "ssr-admin.service").read_text(encoding="utf-8"),
                "OLD_PANEL_UNIT\n",
            )
            self.assertFalse((base / "systemd" / "ssr-device-stats.service").exists())
            systemctl_log = (base / "systemctl.log").read_text(encoding="utf-8")
            self.assertIn("disable ssr-device-stats", systemctl_log)
            self.assertIn("stop ssr-device-stats", systemctl_log)
            self.assertEqual(
                (panel / "config.py").read_text(encoding="utf-8"), "SECRET = 'keep'\n"
            )
            status = json.loads(status_file.read_text(encoding="utf-8"))
            self.assertTrue(status["rollback_attempted"])
            self.assertEqual(status["phase"], "failed")

    def test_success_requires_http_health_and_preserves_local_artifacts(self):
        if not shutil.which("bash") or not shutil.which("git"):
            self.skipTest("bash and git are required")

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            panel, marker, status_file, env = self.make_fixture(base, fail_restart=False)
            outside = base / "outside"
            outside.mkdir()
            (outside / "sentinel.txt").write_text("untouched\n", encoding="utf-8")
            (panel / "assets").symlink_to(outside, target_is_directory=True)
            server = ThreadingHTTPServer(("127.0.0.1", 0), HealthyHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            env["SSR_ADMIN_HEALTH_URL"] = f"http://127.0.0.1:{server.server_port}/login"
            try:
                result = subprocess.run(
                    ["bash", str(UPDATE_SCRIPT), "main"],
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertEqual((panel / "app.py").read_text(encoding="utf-8"), "NEW_APP = True\n")
            self.assertEqual(marker.read_text(encoding="utf-8"), "new\n")
            self.assertEqual(
                (panel / "config.py").read_text(encoding="utf-8"), "SECRET = 'keep'\n"
            )
            self.assertEqual(
                (panel / "local-note.txt").read_text(encoding="utf-8"), "keep me\n"
            )
            self.assertFalse((panel / "assets").is_symlink())
            self.assertEqual(
                (panel / "assets" / "new.txt").read_text(encoding="utf-8"), "new asset\n"
            )
            self.assertEqual(
                (outside / "sentinel.txt").read_text(encoding="utf-8"), "untouched\n"
            )
            self.assertFalse((outside / "new.txt").exists())
            status = json.loads(status_file.read_text(encoding="utf-8"))
            self.assertEqual(status["phase"], "done")
            self.assertFalse(status["rollback_attempted"])

    def test_update_runs_from_stable_copy_when_replacing_itself(self):
        if not shutil.which("bash") or not shutil.which("git"):
            self.skipTest("bash and git are required")

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            panel, _marker, status_file, env = self.make_fixture(
                base, fail_restart=False
            )
            installed_updater = panel / "update.sh"
            installed_updater.write_text(
                UPDATE_SCRIPT.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            installed_updater.chmod(0o755)

            source_repo = Path(env["SSR_ADMIN_REPO_URL"])
            replacement = source_repo / "ssr-admin-panel" / "update.sh"
            replacement.write_text(
                "#!/bin/bash\nprintf 'replacement updater\\n'\n",
                encoding="utf-8",
            )
            replacement.chmod(0o755)
            self.run_git("add", ".", cwd=source_repo)
            self.run_git("commit", "-m", "replace updater", cwd=source_repo)

            server = ThreadingHTTPServer(("127.0.0.1", 0), HealthyHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            env["SSR_ADMIN_HEALTH_URL"] = (
                f"http://127.0.0.1:{server.server_port}/login"
            )
            try:
                result = subprocess.run(
                    ["bash", str(installed_updater), "main"],
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            status = json.loads(status_file.read_text(encoding="utf-8"))
            self.assertEqual(status["phase"], "done")
            self.assertEqual(
                installed_updater.read_text(encoding="utf-8"),
                "#!/bin/bash\nprintf 'replacement updater\\n'\n",
            )

    def test_sigterm_after_sync_restores_backup_and_records_failure(self):
        if not shutil.which("bash") or not shutil.which("git"):
            self.skipTest("bash and git are required")

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            panel, marker, status_file, env = self.make_fixture(base, fail_restart=False)
            env["BLOCK_DAEMON_RELOAD"] = "1"
            server = ThreadingHTTPServer(("127.0.0.1", 0), HealthyHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            env["SSR_ADMIN_HEALTH_URL"] = f"http://127.0.0.1:{server.server_port}/login"

            process = subprocess.Popen(
                ["bash", str(UPDATE_SCRIPT), "main"],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            try:
                ready = Path(env["BLOCK_READY"])
                for _ in range(100):
                    if ready.exists():
                        break
                    if process.poll() is not None:
                        break
                    threading.Event().wait(0.05)
                self.assertTrue(ready.exists(), "update did not reach the post-sync transaction step")
                os.killpg(process.pid, signal.SIGTERM)
                _stdout, _stderr = process.communicate(timeout=10)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=2)
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

            self.assertNotEqual(process.returncode, 0)
            self.assertEqual((panel / "app.py").read_text(encoding="utf-8"), "OLD_APP = True\n")
            self.assertEqual(marker.read_text(encoding="utf-8"), "old\n")
            status = json.loads(status_file.read_text(encoding="utf-8"))
            self.assertEqual(status["phase"], "failed")
            self.assertEqual(status["last_exit_code"], 143)
            self.assertTrue(status["rollback_attempted"])

    def test_rejects_reserved_or_colliding_service_names_before_sync(self):
        if not shutil.which("bash") or not shutil.which("git"):
            self.skipTest("bash and git are required")

        cases = (
            {"SSR_ADMIN_SERVICE_NAME": "ssr", "PANEL_SERVICE": "ssr"},
            {
                "SSR_ADMIN_SERVICE_NAME": "same-service",
                "SSR_DEVICE_STATS_SERVICE_NAME": "same-service",
                "PANEL_SERVICE": "same-service",
            },
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), HealthyHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for overrides in cases:
                with self.subTest(overrides=overrides), tempfile.TemporaryDirectory() as tmp:
                    base = Path(tmp)
                    panel, _marker, _status_file, env = self.make_fixture(
                        base, fail_restart=False
                    )
                    env.update(overrides)
                    env["SSR_ADMIN_HEALTH_URL"] = (
                        f"http://127.0.0.1:{server.server_port}/login"
                    )

                    result = subprocess.run(
                        ["bash", str(UPDATE_SCRIPT), "main"],
                        env=env,
                        capture_output=True,
                        text=True,
                        check=False,
                    )

                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(
                        (panel / "app.py").read_text(encoding="utf-8"),
                        "OLD_APP = True\n",
                    )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_rejects_symlink_panel_root_before_sync(self):
        if not shutil.which("bash") or not shutil.which("git"):
            self.skipTest("bash and git are required")

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            panel, _marker, _status_file, env = self.make_fixture(base, fail_restart=False)
            real_panel = base / "real-panel"
            panel.rename(real_panel)
            panel.symlink_to(real_panel, target_is_directory=True)

            server = ThreadingHTTPServer(("127.0.0.1", 0), HealthyHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            env["SSR_ADMIN_HEALTH_URL"] = f"http://127.0.0.1:{server.server_port}/login"
            try:
                result = subprocess.run(
                    ["bash", str(UPDATE_SCRIPT), "main"],
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(
                (real_panel / "app.py").read_text(encoding="utf-8"),
                "OLD_APP = True\n",
            )

    def test_rejects_panel_path_through_parent_symlink_before_sync(self):
        if not shutil.which("bash") or not shutil.which("git"):
            self.skipTest("bash and git are required")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real_base = root / "real-base"
            real_base.mkdir()
            panel, _marker, _status_file, env = self.make_fixture(
                real_base, fail_restart=False
            )
            linked_base = root / "linked-base"
            linked_base.symlink_to(real_base, target_is_directory=True)
            env["SSR_ADMIN_PANEL_DIR"] = str(linked_base / "panel")
            env["SSR_ADMIN_VENV_DIR"] = str(linked_base / "panel" / "venv")

            result = subprocess.run(
                ["bash", str(UPDATE_SCRIPT), "main"],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsafe panel symlink component", result.stderr)
            self.assertEqual(
                (panel / "app.py").read_text(encoding="utf-8"),
                "OLD_APP = True\n",
            )

    def test_rejects_repo_subdir_traversal_before_sync(self):
        if not shutil.which("bash") or not shutil.which("git"):
            self.skipTest("bash and git are required")

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            panel, _marker, _status_file, env = self.make_fixture(
                base, fail_restart=False
            )
            env["SSR_ADMIN_REPO_SUBDIR"] = "../outside-panel"

            result = subprocess.run(
                ["bash", str(UPDATE_SCRIPT), "main"],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsafe repo subdir", result.stderr)
            self.assertEqual(
                (panel / "app.py").read_text(encoding="utf-8"),
                "OLD_APP = True\n",
            )

    def test_rejects_source_symlink_and_rolls_back(self):
        if not shutil.which("bash") or not shutil.which("git"):
            self.skipTest("bash and git are required")

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            panel, _marker, _status_file, env = self.make_fixture(base, fail_restart=False)
            source_repo = Path(env["SSR_ADMIN_REPO_URL"])
            source_panel = source_repo / "ssr-admin-panel"
            outside = base / "source-outside"
            outside.mkdir()
            (outside / "secret.txt").write_text("outside\n", encoding="utf-8")
            (source_panel / "unsafe-link").symlink_to(outside, target_is_directory=True)
            self.run_git("add", ".", cwd=source_repo)
            self.run_git("commit", "-m", "add unsafe symlink", cwd=source_repo)

            server = ThreadingHTTPServer(("127.0.0.1", 0), HealthyHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            env["SSR_ADMIN_HEALTH_URL"] = f"http://127.0.0.1:{server.server_port}/login"
            try:
                result = subprocess.run(
                    ["bash", str(UPDATE_SCRIPT), "main"],
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((panel / "app.py").read_text(encoding="utf-8"), "OLD_APP = True\n")
            self.assertFalse((panel / "unsafe-link").exists())


if __name__ == "__main__":
    unittest.main()
