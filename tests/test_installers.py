import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


class InstallerRegressionTests(unittest.TestCase):
    def test_install_scripts_have_valid_bash_syntax(self):
        for script in ("install.sh", "install-all.sh", "update.sh"):
            result = subprocess.run(
                ["bash", "-n", str(REPO_ROOT / script)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=f"{script} syntax error: {result.stderr}")

    def test_systemd_unit_heredoc_expands_python_path(self):
        for script in ("install.sh", "install-all.sh"):
            content = (REPO_ROOT / script).read_text(encoding="utf-8")
            self.assertIn("cat > /etc/systemd/system/ssr-admin.service <<SERVICE", content)
            self.assertNotIn("<< 'SERVICE'", content)
            self.assertIn("ExecStart=${PYTHON3_BIN} /opt/ssr-admin-panel/app.py", content)

    def test_runtime_requirements_no_longer_include_unused_gunicorn(self):
        requirements = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertNotIn("gunicorn", requirements.lower())

    def test_install_scripts_reference_update_command(self):
        for script in ("install.sh", "install-all.sh"):
            content = (REPO_ROOT / script).read_text(encoding="utf-8")
            self.assertIn("update.sh", content)

    def test_installers_apply_ssr_python_compatibility_patch(self):
        expected = "patch_ssr_python_compat.py"
        for script in ("install.sh", "install-all.sh", "update.sh"):
            content = (REPO_ROOT / script).read_text(encoding="utf-8")
            self.assertIn(expected, content)

    def test_patch_ssr_python_compat_rewrites_legacy_collections_aliases(self):
        patcher = REPO_ROOT / "scripts" / "patch_ssr_python_compat.py"
        with tempfile.TemporaryDirectory() as tmp_dir:
            ssr_dir = Path(tmp_dir)
            target = ssr_dir / "shadowsocks" / "lru_cache.py"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                "import collections\n\nclass LRUCache(collections.MutableMapping):\n    pass\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                ["python3", str(patcher), str(ssr_dir)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            updated = target.read_text(encoding="utf-8")
            self.assertIn("collections.abc.MutableMapping", updated)
            self.assertNotIn("collections.MutableMapping", updated)


if __name__ == "__main__":
    unittest.main()
