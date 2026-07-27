import json
import os
import shutil
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
        (ssr_dir / "shadowsocks").mkdir()
        (ssr_dir / "shadowsocks" / "server.py").write_text("# server\n", encoding="utf-8")
        (ssr_dir / "shadowsocks" / "udprelay.py").write_text(
            "import socket\n"
            "\n"
            "def make_listener(af, socktype, proto, listen_addr, listen_port):\n"
            "    server_socket = socket.socket(af, socktype, proto)\n"
            "    server_socket.bind((listen_addr, listen_port))\n"
            "    server_socket.setblocking(False)\n"
            "    return server_socket\n",
            encoding="utf-8",
        )
        (ssr_dir / "db_transfer.py").write_text(
            "logging.info('db start server at port [%s] pass [%s] protocol [%s] "
            "method [%s] obfs [%s]' % (port, passwd, protocol, method, obfs))\n",
            encoding="utf-8",
        )
        (ssr_dir / "server.py").write_text("# multi-user server\n", encoding="utf-8")

        panel_dir = base / "panel"
        (panel_dir / "scripts").mkdir(parents=True)
        (panel_dir / "scripts" / "collect_device_stats.py").write_text(
            "#!/usr/bin/env python3\n",
            encoding="utf-8",
        )
        firewall_source = panel_dir / "scripts" / "sync_ssr_firewall.py"
        firewall_source.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

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
        self.write_executable(
            bin_dir / "getent",
            "#!/bin/sh\n"
            "[ \"$1\" = passwd ] && [ \"$2\" = ssr-panel ] && exit 0\n"
            "[ \"$1\" = group ] && [ \"$2\" = ssr-panel ] && exit 0\n"
            "exit 2\n",
        )
        legacy_init = base / "ssrmu"
        self.write_executable(
            legacy_init,
            "#!/bin/sh\n"
            "echo \"legacy $@\" >> \"$SYSTEMCTL_LOG\"\n"
            "exit 0\n",
        )

        return {
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "SSR_OPT_SKIP_ROOT_CHECK": "1",
            "SSR_DIR": str(ssr_dir),
            "SYSTEMD_DIR": str(base / "systemd"),
            "SYSCTL_DIR": str(base / "sysctl.d"),
            "SYSCTL_CONF": str(base / "sysctl.conf"),
            "PANEL_DIR": str(panel_dir),
            "DEVICE_STATS_FILE": str(base / "var" / "device-stats.json"),
            "SYSTEMCTL_LOG": str(base / "systemctl.log"),
            "SSR_LEGACY_INIT": str(legacy_init),
            "SSR_FIREWALL_HELPER": str(base / "libexec" / "sync-firewall.py"),
            "SSR_FIREWALL_CONFIG": str(base / "etc" / "ssr-panel-firewall"),
        }, ssr_dir

    def write_executable(self, path: Path, content: str):
        path.write_text(content, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def test_check_mode_does_not_write_system_files(self):
        if not shutil.which("bash"):
            self.skipTest("bash is not available")
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
        if not shutil.which("bash"):
            self.skipTest("bash is not available")
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
            udp_relay = (ssr_dir / "shadowsocks" / "udprelay.py").read_text(encoding="utf-8")
            self.assertNotIn("SO_RCVBUF", udp_relay)
            db_transfer = (ssr_dir / "db_transfer.py").read_text(encoding="utf-8")
            self.assertIn(" pass [%s]", db_transfer)
            self.assertFalse((base / "systemd" / "ssr.service").exists())
            self.assertFalse((base / "sysctl.d" / "99-z-ssr-performance.conf").exists())
            self.assertIn("restoring changed files", result.stdout)

    def test_apply_tunes_udp_defaults_and_patches_listener_idempotently(self):
        if not shutil.which("bash"):
            self.skipTest("bash is not available")
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            env, ssr_dir = self.make_env(base)

            for _ in range(2):
                result = subprocess.run(
                    ["bash", str(SCRIPT)],
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, msg=result.stderr)

            sysctl_config = (base / "sysctl.d" / "99-z-ssr-performance.conf").read_text(
                encoding="utf-8"
            )
            self.assertIn("net.core.rmem_default = 2097152", sysctl_config)
            self.assertIn("net.core.wmem_default = 1048576", sysctl_config)

            udp_relay = (ssr_dir / "shadowsocks" / "udprelay.py").read_text(encoding="utf-8")
            marker = "SSR_Panel: enlarge the shared UDP listener queue for QUIC bursts"
            self.assertEqual(udp_relay.count(marker), 1)
            self.assertEqual(udp_relay.count("socket.SO_RCVBUF, 2097152"), 1)
            self.assertLess(udp_relay.index("socket.SO_RCVBUF"), udp_relay.index(".bind("))
            db_transfer = (ssr_dir / "db_transfer.py").read_text(encoding="utf-8")
            self.assertNotIn(" pass [%s]", db_transfer)
            self.assertIn("db start server at port [%s] protocol [%s]", db_transfer)

    def test_apply_adopts_an_existing_manual_udp_buffer_setting(self):
        if not shutil.which("bash"):
            self.skipTest("bash is not available")
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            env, ssr_dir = self.make_env(base)
            udp_relay_path = ssr_dir / "shadowsocks" / "udprelay.py"
            source = udp_relay_path.read_text(encoding="utf-8")
            source = source.replace(
                "    server_socket.bind((listen_addr, listen_port))",
                "    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1048576)\n"
                "    server_socket.bind((listen_addr, listen_port))",
            )
            udp_relay_path.write_text(source, encoding="utf-8")

            result = subprocess.run(
                ["bash", str(SCRIPT)],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            udp_relay = udp_relay_path.read_text(encoding="utf-8")
            self.assertEqual(udp_relay.count("socket.SO_RCVBUF"), 1)
            self.assertIn("socket.SO_RCVBUF, 2097152", udp_relay)
            self.assertIn(
                "SSR_Panel: enlarge the shared UDP listener queue for QUIC bursts",
                udp_relay,
            )

    def test_generated_unit_uses_real_ssr_entrypoint_and_disables_sysv_autostart(self):
        if not shutil.which("bash"):
            self.skipTest("bash is not available")
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            env, ssr_dir = self.make_env(base)

            result = subprocess.run(
                ["bash", str(SCRIPT)],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            unit = (base / "systemd" / "ssr.service").read_text(encoding="utf-8")
            self.assertIn(f"WorkingDirectory={ssr_dir}", unit)
            self.assertIn(f"{ssr_dir / 'server.py'} m", unit)
            self.assertIn(
                f"EnvironmentFile=-{base / 'etc' / 'ssr-panel-firewall'}",
                unit,
            )
            self.assertIn(
                f"ExecStartPre={base / 'libexec' / 'sync-firewall.py'}",
                unit,
            )
            firewall_helper = base / "libexec" / "sync-firewall.py"
            firewall_config = base / "etc" / "ssr-panel-firewall"
            self.assertTrue(firewall_helper.is_file())
            self.assertTrue(firewall_helper.stat().st_mode & stat.S_IXUSR)
            self.assertEqual(
                firewall_config.read_text(encoding="utf-8"),
                "# Managed by SSR_Panel\nSSR_EXTRA_PORTS=18899\n",
            )
            self.assertEqual(stat.S_IMODE(firewall_config.stat().st_mode), 0o600)
            actions = (base / "systemctl.log").read_text(encoding="utf-8")
            self.assertIn("legacy stop", actions)
            self.assertIn("disable ssrmu.service", actions)
            device_stats_unit = (
                base / "systemd" / "ssr-device-stats.service"
            ).read_text(encoding="utf-8")
            self.assertIn("User=ssr-panel", device_stats_unit)
            self.assertIn("Group=ssr-panel", device_stats_unit)
            self.assertNotIn("User=root", device_stats_unit)


if __name__ == "__main__":
    unittest.main()
