import json
import os
import shutil
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
        self.run_git("init", "-b", "main", cwd=source_repo)
        self.run_git("config", "user.name", "SSR Panel Test", cwd=source_repo)
        self.run_git("config", "user.email", "test@example.invalid", cwd=source_repo)
        self.run_git("add", ".", cwd=source_repo)
        self.run_git("commit", "-m", "fixture", cwd=source_repo)

        bin_dir = base / "bin"
        bin_dir.mkdir()
        self.write_executable(bin_dir / "flock", "#!/bin/sh\nexit 0\n")
        restart_failure = "[ \"${1:-}\" = restart ] && exit 1\n" if fail_restart else ""
        self.write_executable(
            bin_dir / "systemctl",
            "#!/bin/sh\n"
            "echo \"$@\" >> \"$SYSTEMCTL_LOG\"\n"
            f"{restart_failure}"
            "exit 0\n",
        )

        status_file = base / "status.json"
        env = {
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "SSR_ADMIN_SKIP_ROOT_CHECK": "1",
            "SSR_ADMIN_PANEL_DIR": str(panel),
            "SSR_ADMIN_VENV_DIR": str(venv),
            "SSR_ADMIN_SYSTEMD_DIR": str(base / "systemd"),
            "SSR_ADMIN_REPO_URL": str(source_repo),
            "SSR_ADMIN_REPO_SUBDIR": "ssr-admin-panel",
            "SSR_ADMIN_UPDATE_STATUS_FILE": str(status_file),
            "SSR_ADMIN_UPDATE_LOCK_FILE": str(base / "update.lock"),
            "SSR_ADMIN_SSR_DIR": str(base / "missing-ssr"),
            "SYSTEMCTL_LOG": str(base / "systemctl.log"),
            "VENV_MARKER": str(marker),
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
            status = json.loads(status_file.read_text(encoding="utf-8"))
            self.assertEqual(status["phase"], "done")
            self.assertFalse(status["rollback_attempted"])


if __name__ == "__main__":
    unittest.main()
