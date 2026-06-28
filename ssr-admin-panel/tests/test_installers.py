import subprocess
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


class InstallerRegressionTests(unittest.TestCase):
    def test_shell_scripts_use_lf_line_endings(self):
        scripts = list(REPO_ROOT.glob("*.sh")) + list((REPO_ROOT / "scripts").glob("*.sh"))
        for script in scripts:
            data = script.read_bytes()
            self.assertNotIn(b"\r\n", data, msg=f"{script.relative_to(REPO_ROOT)} uses CRLF line endings")

    def test_install_scripts_have_valid_bash_syntax(self):
        if not shutil.which("bash"):
            self.skipTest("bash is not available")
        for script in ("install.sh", "install-all.sh", "update.sh", "uninstall.sh"):
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
            self.assertIn(
                "ExecStart=${PYTHON3_BIN} -m waitress --host=0.0.0.0 --port=5000 app:app",
                content,
            )
            self.assertIn("NoNewPrivileges=true", content)
            self.assertIn("PrivateTmp=true", content)

    def test_runtime_requirements_no_longer_include_unused_gunicorn(self):
        requirements = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertNotIn("gunicorn", requirements.lower())
        self.assertIn("waitress", requirements.lower())

    def test_installers_do_not_eval_admin_input(self):
        for script in ("install.sh", "install-all.sh"):
            content = (REPO_ROOT / script).read_text(encoding="utf-8")
            self.assertNotIn("eval \"$var_name=", content)
            self.assertIn('printf -v "$var_name"', content)

    def test_ssrmu_does_not_disable_tls_certificate_checks(self):
        content = (REPO_ROOT / "ssrmu.sh").read_text(encoding="utf-8")
        self.assertNotIn("--no-check-certificate", content)

    def test_install_scripts_reference_update_command(self):
        for script in ("install.sh", "install-all.sh"):
            content = (REPO_ROOT / script).read_text(encoding="utf-8")
            self.assertIn("update.sh", content)

    def test_installers_default_to_monorepo_subdir(self):
        for script in ("install.sh", "install-all.sh", "update.sh"):
            content = (REPO_ROOT / script).read_text(encoding="utf-8")
            self.assertIn("https://github.com/Elegying/SSR_Panel.git", content)
            self.assertIn("SSR_ADMIN_REPO_SUBDIR", content)
            self.assertIn("ssr-admin-panel", content)
            self.assertNotIn("https://github.com/Elegying/ssr-admin-panel.git", content)

    def test_install_and_update_scripts_expose_uninstall_command(self):
        for script in ("install.sh", "install-all.sh", "update.sh"):
            content = (REPO_ROOT / script).read_text(encoding="utf-8")
            self.assertIn("uninstall.sh", content)

    def test_install_and_update_scripts_write_panel_build_metadata(self):
        for script in ("install.sh", "install-all.sh", "update.sh"):
            content = (REPO_ROOT / script).read_text(encoding="utf-8")
            self.assertIn(".panel-build.json", content)
            self.assertIn("display_version", content)
            self.assertIn("revision", content)

    def test_install_scripts_write_private_share_template_config(self):
        for script in ("install.sh", "install-all.sh"):
            content = (REPO_ROOT / script).read_text(encoding="utf-8")
            self.assertIn("SSR_SHARE_HOST", content)
            self.assertIn("SSR_SHARE_PASSWORD", content)
            self.assertIn("默认关闭分享功能", content)
            self.assertNotIn("请输入协议 [${SHARE_PROTOCOL}]", content)
            self.assertNotIn("请输入加密方式 [${SHARE_METHOD}]", content)
            self.assertNotIn("请输入混淆方式 [${SHARE_OBFS}]", content)
            self.assertNotIn("请输入 obfs_param [${SHARE_OBFS_PARAM}]", content)

    def test_installers_apply_ssr_python_compatibility_patch(self):
        expected = "patch_ssr_python_compat.py"
        for script in ("install.sh", "install-all.sh", "update.sh"):
            content = (REPO_ROOT / script).read_text(encoding="utf-8")
            self.assertIn(expected, content)

    def test_installers_configure_device_stats_service(self):
        for script in ("install.sh", "install-all.sh", "update.sh"):
            content = (REPO_ROOT / script).read_text(encoding="utf-8")
            self.assertIn("collect_device_stats.py", content)
            self.assertIn("ssr-device-stats", content)
            self.assertIn("DEVICE_STATS_FILE", content)

    def test_optimizer_blocks_ipv6_targets_and_quic_by_default(self):
        content = (REPO_ROOT / "scripts" / "optimize_server.sh").read_text(encoding="utf-8")
        self.assertIn('SSR_BLOCK_IPV6_TARGETS="${SSR_BLOCK_IPV6_TARGETS:-1}"', content)
        self.assertIn('SSR_BLOCK_UDP_443="${SSR_BLOCK_UDP_443:-1}"', content)
        self.assertIn('"::/0"', content)
        self.assertIn('"forbidden_ip"', content)
        self.assertIn("udp dport 443 reject", content)
        self.assertNotIn("tcp dport 443 reject", content)

    def test_optimizer_persists_nft_rule_without_overwriting_existing_tables(self):
        content = (REPO_ROOT / "scripts" / "optimize_server.sh").read_text(encoding="utf-8")
        self.assertIn("/etc/nftables.d", content)
        self.assertIn("ssr-filter.nft", content)
        self.assertIn('include "/etc/nftables.d/ssr-filter.nft"', content)
        self.assertIn("nft delete table inet ssr_filter", content)
        self.assertNotIn("cat > \"$NFTABLES_CONF\" <<'EOF'\n#!/usr/sbin/nft -f\n\nflush ruleset\n\ntable inet ssr_filter", content)

    def test_update_script_reapplies_server_optimization_when_ssr_exists(self):
        content = (REPO_ROOT / "update.sh").read_text(encoding="utf-8")
        self.assertIn("SSR_ADMIN_APPLY_SERVER_OPTIMIZATION", content)
        self.assertIn("apply_server_optimization", content)
        self.assertIn("scripts/optimize_server.sh", content)
        self.assertIn("bash \"${optimizer}\"", content)

    def test_uninstall_script_requires_explicit_confirmation(self):
        content = (REPO_ROOT / "uninstall.sh").read_text(encoding="utf-8")
        self.assertIn("--yes", content)
        self.assertIn("refusing to uninstall without --yes", content)
        self.assertIn("--remove-ssr", content)

    def test_panel_only_install_skips_device_stats_without_ssr_data(self):
        content = (REPO_ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertIn('[ ! -d "$SSR_DIR" ] || [ ! -f "$MUDB_FILE" ]', content)
        self.assertIn("跳过设备统计服务", content)

    def test_installers_do_not_silence_panel_git_update_failures(self):
        for script in ("install.sh", "install-all.sh"):
            content = (REPO_ROOT / script).read_text(encoding="utf-8")
            self.assertNotIn('git pull --ff-only -q origin "$REPO_REF" 2>/dev/null || true', content)
            self.assertIn("git clone --depth 1 --branch", content)
            self.assertIn("Project files not found", content)

    def test_update_script_has_full_backup_status_and_rollback_fields(self):
        content = (REPO_ROOT / "update.sh").read_text(encoding="utf-8")
        self.assertIn("create_full_backup", content)
        self.assertIn("restore_backup", content)
        self.assertIn("rollback_attempted", content)
        self.assertIn("rollback_success", content)
        self.assertIn("backup_dir", content)

    def test_panel_update_runner_uses_update_script_without_hard_reset(self):
        content = (REPO_ROOT / "scripts" / "run_panel_update.py").read_text(encoding="utf-8")
        self.assertIn("SSR_ADMIN_UPDATE_STATUS_FILE", content)
        self.assertIn("update_from_script", content)
        self.assertNotIn("reset\", \"--hard", content)

    def test_installers_prepare_minimal_debian_runtime(self):
        content = (REPO_ROOT / "install-all.sh").read_text(encoding="utf-8")
        self.assertIn("apt-get update", content)
        self.assertIn('"ss:${_ss_pkg}"', content)
        self.assertIn('"systemctl:systemd"', content)

    def test_installers_support_legacy_python_runtime_dependencies(self):
        for script in ("install.sh", "install-all.sh", "update.sh"):
            content = (REPO_ROOT / script).read_text(encoding="utf-8")
            self.assertIn("python_version_lt", content)
            self.assertIn("Flask-Limiter>=1.5,<2.0", content)
            self.assertIn("waitress>=2.0,<2.1", content)
            self.assertIn("Flask-Limiter>=3.0,<3.5.1", content)

    def test_update_script_uses_python_version_checks_without_bc_or_eval(self):
        content = (REPO_ROOT / "update.sh").read_text(encoding="utf-8")
        self.assertNotIn("bc -l", content)
        self.assertNotIn("eval ${pip_bin}", content)
        self.assertIn("run_pip_install", content)

    def test_ssrmu_centos_package_manager_expands_yum_variable(self):
        content = (REPO_ROOT / "ssrmu.sh").read_text(encoding="utf-8")
        self.assertIn("${_yum} makecache", content)
        self.assertNotIn("\\${_yum}", content)

    def test_ssrmu_does_not_require_unzip_when_git_or_tar_is_available(self):
        content = (REPO_ROOT / "ssrmu.sh").read_text(encoding="utf-8")

        self.assertIn("git clone --depth 1 --branch manyuser", content)
        self.assertIn("manyuser.tar.gz", content)
        self.assertIn("command -v git", content)
        self.assertIn("command -v tar", content)
        self.assertIn("command -v unzip", content)
        self.assertNotIn("依赖 unzip(解压压缩包) 安装失败", content)

    def test_optimizer_sysctl_failure_does_not_abort_full_deploy(self):
        content = (REPO_ROOT / "scripts" / "optimize_server.sh").read_text(encoding="utf-8")
        self.assertIn("ssr-admin-sysctl.log", content)
        self.assertIn("不阻断部署", content)

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

    def test_created_user_modal_uses_share_action_instead_of_copy_password(self):
        content = (REPO_ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="shareUserBtn"', content)
        self.assertIn('>分享<', content)
        self.assertIn("shareCreatedUser", content)
        self.assertNotIn('id="copyPasswordBtn"', content)
        self.assertNotIn(">复制密码<", content)
        self.assertNotIn("copyCreatedPassword", content)

    def test_total_users_stat_card_removed_because_hero_shows_current_users(self):
        content = (REPO_ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertIn("heroTotalUsers", content)
        self.assertNotIn('id="stat-users"', content)
        self.assertNotIn("用户总数", content)

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
                [sys.executable, str(patcher), str(ssr_dir)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            updated = target.read_text(encoding="utf-8")
            self.assertIn("collections.abc.MutableMapping", updated)
            self.assertNotIn("collections.MutableMapping", updated)

    def test_patch_ssr_python_compat_rewrites_literal_identity_warnings(self):
        patcher = REPO_ROOT / "scripts" / "patch_ssr_python_compat.py"
        with tempfile.TemporaryDirectory() as tmp_dir:
            ssr_dir = Path(tmp_dir)
            target = ssr_dir / "shadowsocks" / "common.py"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                'if addr is "":\n    pass\nif len(block) is 1:\n    pass\nwhile ip is not 0:\n    pass\n',
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(patcher), str(ssr_dir)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            updated = target.read_text(encoding="utf-8")
            self.assertIn('addr == ""', updated)
            self.assertIn("len(block) == 1", updated)
            self.assertIn("ip != 0", updated)
            self.assertNotIn('addr is ""', updated)
            self.assertNotIn("len(block) is 1", updated)
            self.assertNotIn("ip is not 0", updated)


if __name__ == "__main__":
    unittest.main()
