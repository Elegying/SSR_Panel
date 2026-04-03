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

    def test_install_scripts_write_private_share_template_config(self):
        for script in ("install.sh", "install-all.sh"):
            content = (REPO_ROOT / script).read_text(encoding="utf-8")
            self.assertIn("SSR_SHARE_HOST", content)
            self.assertIn("SSR_SHARE_PASSWORD", content)
            self.assertIn("分享功能默认关闭", content)
            self.assertNotIn("请输入协议 [${SHARE_PROTOCOL}]", content)
            self.assertNotIn("请输入加密方式 [${SHARE_METHOD}]", content)
            self.assertNotIn("请输入混淆方式 [${SHARE_OBFS}]", content)
            self.assertNotIn("请输入 obfs_param [${SHARE_OBFS_PARAM}]", content)

    def test_installers_apply_ssr_python_compatibility_patch(self):
        expected = "patch_ssr_python_compat.py"
        for script in ("install.sh", "install-all.sh", "update.sh"):
            content = (REPO_ROOT / script).read_text(encoding="utf-8")
            self.assertIn(expected, content)

    def test_ssrmu_applies_python_compatibility_patch_before_startup(self):
        content = (REPO_ROOT / "ssrmu.sh").read_text(encoding="utf-8")
        self.assertIn("Fix_python_collections_compatibility()", content)
        self.assertIn("Fix_python_collections_compatibility\n\techo -e", content.replace("\r\n", "\n"))

    def test_ssrmu_generates_or_bypasses_missing_init_script(self):
        content = (REPO_ROOT / "ssrmu.sh").read_text(encoding="utf-8")
        self.assertIn("Create_local_ssr_init_script()", content)
        self.assertIn('cat > /etc/init.d/ssrmu <<EOF', content)
        self.assertIn('if [[ -e "/etc/init.d/ssrmu" ]]; then', content)
        self.assertIn('cd "${ssr_folder}/shadowsocks" && "${python_bin}" server.py -d start', content)

    def test_index_template_no_longer_contains_trend_view(self):
        content = (REPO_ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("用户趋势视图", content)
        self.assertNotIn("TREND_STORAGE_KEY", content)
        self.assertNotIn("renderTrendChart", content)

    def test_config_example_uses_safe_share_placeholders(self):
        content = (REPO_ROOT / "config.py.example").read_text(encoding="utf-8")
        self.assertIn("SSR_SHARE_HOST = ''", content)
        self.assertIn("SSR_SHARE_PASSWORD = ''", content)
        self.assertIn("SSR_SHARE_REMARKS = ''", content)
        self.assertNotIn("nikuaimobi", content)
        self.assertNotIn("ssr.ssrvpn.vip", content)

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
