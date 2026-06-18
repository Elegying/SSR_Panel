import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "optimize-ssr.sh"


class OptimizerScriptTests(unittest.TestCase):
    def test_shell_scripts_use_lf_line_endings(self):
        for script in REPO_ROOT.glob("*.sh"):
            data = script.read_bytes()
            self.assertNotIn(b"\r\n", data, msg=f"{script.name} uses CRLF line endings")

    def make_env(self, base: Path, fail_start: bool = False):
        ssr_dir = base / "shadowsocksr"
        ssr_dir.mkdir()
        (ssr_dir / "user-config.json").write_text(
            json.dumps({"timeout": 120, "udp_timeout": 60, "fast_open": False}) + "\n",
            encoding="utf-8",
        )
        (ssr_dir / "server.py").write_text("# server\n", encoding="utf-8")

        bin_dir = base / "bin"
        bin_dir.mkdir()
        self.write_executable(
            bin_dir / "systemctl",
            "#!/bin/sh\n"
            "echo \"$@\" >> \"$SYSTEMCTL_LOG\"\n"
            + ("[ \"$1\" = start ] && exit 1\n" if fail_start else "")
            + "[ \"$1\" = is-active ] && exit 0\n"
            "exit 0\n",
        )
        self.write_executable(bin_dir / "sysctl", "#!/bin/sh\nexit 0\n")
        self.write_executable(bin_dir / "ss", "#!/bin/sh\nexit 0\n")

        return {
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "SSR_OPT_SKIP_ROOT_CHECK": "1",
            "SSR_DIR": str(ssr_dir),
            "SYSTEMD_DIR": str(base / "systemd"),
            "SYSCTL_DIR": str(base / "sysctl.d"),
            "SYSCTL_CONF": str(base / "sysctl.conf"),
            "PANEL_DIR": str(base / "panel"),
            "SYSTEMCTL_LOG": str(base / "systemctl.log"),
        }, ssr_dir

    def write_executable(self, path: Path, content: str):
        path.write_text(content, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def test_check_mode_does_not_write_system_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            env, _ = self.make_env(base)

            result = subprocess.run(
                ["bash", str(SCRIPT), "--check"],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("preflight ok", result.stdout)
            self.assertFalse((base / "systemd").exists())
            self.assertFalse((base / "sysctl.d").exists())

    def test_failed_apply_restores_changed_files_and_removes_new_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            env, ssr_dir = self.make_env(base, fail_start=True)

            result = subprocess.run(
                ["bash", str(SCRIPT)],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            config = json.loads((ssr_dir / "user-config.json").read_text(encoding="utf-8"))
            self.assertEqual(config["timeout"], 120)
            self.assertEqual(config["udp_timeout"], 60)
            self.assertFalse(config["fast_open"])
            self.assertFalse((base / "systemd" / "ssr.service").exists())
            self.assertFalse((base / "sysctl.d" / "99-z-ssr-performance.conf").exists())
            self.assertIn("restoring changed files", result.stdout)


if __name__ == "__main__":
    unittest.main()
