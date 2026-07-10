#!/usr/bin/env python3
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
UNINSTALL_SCRIPT = REPO_ROOT / "uninstall.sh"
ROOT_CHECK = '[[ "${EUID:-$(id -u)}" -eq 0 ]] || fail "run as root"'
OVERRIDE_NAMES = (
    "SSR_ADMIN_PANEL_DIR",
    "SSR_ADMIN_SSR_DIR",
    "SSR_DEVICE_STATS_DIR",
    "SSR_ADMIN_SERVICE_NAME",
    "SSR_DEVICE_STATS_SERVICE_NAME",
)


class UninstallSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name).resolve()
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        self.action_log = self.root / "actions.log"
        self.default_panel_dir = self.root / "default-panel"
        self.default_ssr_dir = self.root / "default-ssr"
        self.default_stats_dir = self.root / "default-stats"
        for path in (self.default_panel_dir, self.default_ssr_dir, self.default_stats_dir):
            path.mkdir()

        source = UNINSTALL_SCRIPT.read_text(encoding="utf-8")
        self.assertEqual(source.count(ROOT_CHECK), 1)
        self.assertNotIn("/bin/rm", source)
        self.assertNotIn("/bin/systemctl", source)
        harness_source = source.replace(
            ROOT_CHECK,
            ": # root check bypassed; systemctl and rm are sandboxed below",
        )
        for original, replacement in (
            ('DEFAULT_PANEL_DIR="/opt/ssr-admin-panel"', f'DEFAULT_PANEL_DIR="{self.default_panel_dir}"'),
            ('DEFAULT_SSR_DIR="/usr/local/shadowsocksr"', f'DEFAULT_SSR_DIR="{self.default_ssr_dir}"'),
            ('DEFAULT_DEVICE_STATS_DIR="/var/lib/ssr-admin-panel"', f'DEFAULT_DEVICE_STATS_DIR="{self.default_stats_dir}"'),
        ):
            self.assertEqual(harness_source.count(original), 1)
            harness_source = harness_source.replace(original, replacement)
        self.harness = self.root / "uninstall.sh"
        self.harness.write_text(harness_source, encoding="utf-8")

        for command in ("systemctl", "rm"):
            stub = self.bin_dir / command
            stub.write_text(
                "#!/bin/sh\n"
                "printf '%s' \"${0##*/}\" >> \"$ACTION_LOG\"\n"
                "for arg in \"$@\"; do printf '\\t%s' \"$arg\" >> \"$ACTION_LOG\"; done\n"
                "printf '\\n' >> \"$ACTION_LOG\"\n",
                encoding="utf-8",
            )
            stub.chmod(0o755)

    def tearDown(self):
        self.temp_dir.cleanup()

    def managed_dir(self, name):
        path = self.root / name
        path.mkdir()
        (path / ".ssr-panel-managed").write_text("managed\n", encoding="utf-8")
        return path

    def harness_with_panel_default(self, path, name):
        source = self.harness.read_text(encoding="utf-8")
        original = f'DEFAULT_PANEL_DIR="{self.default_panel_dir}"'
        self.assertEqual(source.count(original), 1)
        harness = self.root / name
        harness.write_text(source.replace(original, f'DEFAULT_PANEL_DIR="{path}"'), encoding="utf-8")
        return harness

    def run_uninstall(self, *args, overrides=None, harness=None):
        env = os.environ.copy()
        for name in OVERRIDE_NAMES:
            env.pop(name, None)
        env.pop("BASH_ENV", None)
        env.update(
            {
                "ACTION_LOG": str(self.action_log),
                "PATH": f"{self.bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            }
        )
        env.update(overrides or {})
        result = subprocess.run(
            [shutil.which("bash") or "bash", str(harness or self.harness), *args],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        actions = self.action_log.read_text(encoding="utf-8").splitlines() if self.action_log.exists() else []
        return result, actions

    def assert_rejected_without_actions(self, result, actions):
        self.assertNotEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertEqual(actions, [], msg="uninstall performed side effects before rejecting input")

    def assert_rm_actions(self, actions, expected):
        self.assertEqual([action for action in actions if action.startswith("rm\t")], expected)

    def test_rejects_critical_panel_path_before_side_effects(self):
        for path in ("/", "/etc", "/opt/../etc"):
            with self.subTest(path=path):
                if self.action_log.exists():
                    self.action_log.unlink()
                result, actions = self.run_uninstall(
                    "--yes",
                    overrides={"SSR_ADMIN_PANEL_DIR": path},
                )

                self.assert_rejected_without_actions(result, actions)

    def test_rejects_service_name_traversal_before_side_effects(self):
        for variable in ("SSR_ADMIN_SERVICE_NAME", "SSR_DEVICE_STATS_SERVICE_NAME"):
            with self.subTest(variable=variable):
                if self.action_log.exists():
                    self.action_log.unlink()
                result, actions = self.run_uninstall(
                    "--yes",
                    overrides={variable: "../../tmp/pwn"},
                )

                self.assert_rejected_without_actions(result, actions)

    def test_rejects_empty_relative_and_unmarked_custom_paths(self):
        unmarked = self.root / "unmarked"
        unmarked.mkdir()
        for path in ("", "relative/path", str(unmarked)):
            with self.subTest(path=path):
                if self.action_log.exists():
                    self.action_log.unlink()
                result, actions = self.run_uninstall(
                    "--yes",
                    overrides={"SSR_ADMIN_PANEL_DIR": path},
                )

                self.assert_rejected_without_actions(result, actions)

    def test_rejects_custom_symlink_before_side_effects(self):
        target = self.managed_dir("target")
        symlink = self.root / "panel-link"
        symlink.symlink_to(target, target_is_directory=True)

        result, actions = self.run_uninstall(
            "--yes",
            overrides={"SSR_ADMIN_PANEL_DIR": str(symlink)},
        )

        self.assert_rejected_without_actions(result, actions)

    def test_rejects_custom_path_through_parent_symlink(self):
        target_parent = self.root / "target-parent"
        target_parent.mkdir()
        target = target_parent / "panel"
        target.mkdir()
        (target / ".ssr-panel-managed").write_text("managed\n", encoding="utf-8")
        symlink_parent = self.root / "linked-parent"
        symlink_parent.symlink_to(target_parent, target_is_directory=True)

        result, actions = self.run_uninstall(
            "--yes",
            overrides={"SSR_ADMIN_PANEL_DIR": str(symlink_parent / "panel")},
        )

        self.assert_rejected_without_actions(result, actions)

    def test_rejects_existing_default_path_through_parent_symlink(self):
        target_parent = self.root / "default-target"
        target_parent.mkdir()
        target = target_parent / "panel"
        target.mkdir()
        symlink_parent = self.root / "default-link"
        symlink_parent.symlink_to(target_parent, target_is_directory=True)
        linked_default = symlink_parent / "panel"

        alternate_harness = self.harness_with_panel_default(
            linked_default,
            "uninstall-symlinked-default.sh",
        )

        result, actions = self.run_uninstall(
            "--yes",
            harness=alternate_harness,
        )

        self.assert_rejected_without_actions(result, actions)

    def test_rejects_missing_default_path_through_parent_symlink(self):
        target_parent = self.root / "missing-default-target"
        target_parent.mkdir()
        symlink_parent = self.root / "missing-default-link"
        symlink_parent.symlink_to(target_parent, target_is_directory=True)
        alternate_harness = self.harness_with_panel_default(
            symlink_parent / "missing-panel",
            "uninstall-missing-symlinked-default.sh",
        )

        result, actions = self.run_uninstall(
            "--yes",
            harness=alternate_harness,
        )

        self.assert_rejected_without_actions(result, actions)

    def test_keep_data_still_rejects_invalid_paths_before_side_effects(self):
        result, actions = self.run_uninstall(
            "--yes",
            "--keep-data",
            overrides={"SSR_ADMIN_PANEL_DIR": ""},
        )

        self.assert_rejected_without_actions(result, actions)

    def test_remove_ssr_rejects_critical_path_before_side_effects(self):
        result, actions = self.run_uninstall(
            "--yes",
            "--remove-ssr",
            overrides={"SSR_ADMIN_SSR_DIR": "/etc"},
        )

        self.assert_rejected_without_actions(result, actions)

    def test_allows_backward_compatible_default_paths_without_markers(self):
        result, actions = self.run_uninstall("--yes", "--remove-ssr")

        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assert_rm_actions(
            actions,
            [
                "rm\t-f\t/etc/systemd/system/ssr-admin.service",
                "rm\t-f\t/etc/systemd/system/ssr-device-stats.service",
                "rm\t-f\t/etc/systemd/system/ssr.service",
                f"rm\t-rf\t{self.default_ssr_dir}",
                f"rm\t-rf\t{self.default_panel_dir}\t{self.default_stats_dir}",
            ],
        )

    def test_allows_marked_custom_paths_including_remove_ssr(self):
        panel_dir = self.managed_dir("panel")
        stats_dir = self.managed_dir("stats")
        ssr_dir = self.managed_dir("ssr")

        result, actions = self.run_uninstall(
            "--yes",
            "--remove-ssr",
            overrides={
                "SSR_ADMIN_PANEL_DIR": str(panel_dir),
                "SSR_DEVICE_STATS_DIR": str(stats_dir),
                "SSR_ADMIN_SSR_DIR": str(ssr_dir),
            },
        )

        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assert_rm_actions(
            actions,
            [
                "rm\t-f\t/etc/systemd/system/ssr-admin.service",
                "rm\t-f\t/etc/systemd/system/ssr-device-stats.service",
                "rm\t-f\t/etc/systemd/system/ssr.service",
                f"rm\t-rf\t{ssr_dir}",
                f"rm\t-rf\t{panel_dir}\t{stats_dir}",
            ],
        )


if __name__ == "__main__":
    unittest.main()
