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
        for script in (
            "install.sh",
            "install-all.sh",
            "update.sh",
            "rollback.sh",
            "uninstall.sh",
        ):
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
            self.assertIn("User=ssr-panel", content)
            self.assertIn("Group=ssr-panel", content)
            self.assertIn("NoNewPrivileges=false", content)
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

    def test_uninstaller_removes_panel_privilege_boundary(self):
        content = (REPO_ROOT / "uninstall.sh").read_text(encoding="utf-8")
        self.assertIn("/etc/sudoers.d/ssr-panel", content)
        self.assertIn("admin-helper", content)
        self.assertIn("userdel", content)
        self.assertIn("groupdel", content)

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
            self.assertIn("User=ssr-panel", content)
            self.assertIn("Group=ssr-panel", content)

    def test_panel_runs_as_dedicated_user_with_allowlisted_sudo_helper(self):
        provisioner = (REPO_ROOT / "scripts" / "provision_panel_runtime.sh").read_text(
            encoding="utf-8"
        )
        for script in ("install.sh", "install-all.sh", "update.sh"):
            content = (REPO_ROOT / script).read_text(encoding="utf-8")
            self.assertIn("provision_panel_runtime.sh", content)
            self.assertIn("User=ssr-panel", content)
            self.assertIn("Group=ssr-panel", content)
            self.assertIn("NoNewPrivileges=false", content)
            self.assertIn("--host=0.0.0.0 --port=5000", content)

        self.assertIn("/etc/sudoers.d/ssr-panel", provisioner)
        self.assertIn("/usr/local/libexec/ssr-panel/admin-helper", provisioner)
        for action in (
            "ssr-start",
            "ssr-stop",
            "ssr-restart",
            "firewall-sync",
            "mudb-commit",
            "panel-update",
        ):
            self.assertIn(action, provisioner)
        self.assertIn('PANEL_GROUP="ssr-panel"', provisioner)
        self.assertIn("0640", provisioner)
        self.assertIn('chmod g+rx,g-w,g+s "$(dirname "${MUDB_FILE}")"', provisioner)
        self.assertIn('usermod --groups ""', provisioner)
        self.assertIn("must not be a symlink", provisioner)

    def test_optimizer_blocks_ipv6_targets_and_allows_udp443_by_default(self):
        content = (REPO_ROOT / "scripts" / "optimize_server.sh").read_text(encoding="utf-8")
        self.assertIn('SSR_BLOCK_IPV6_TARGETS="${SSR_BLOCK_IPV6_TARGETS:-1}"', content)
        self.assertIn('SSR_BLOCK_UDP_443="${SSR_BLOCK_UDP_443:-0}"', content)
        self.assertIn('"::/0"', content)
        self.assertIn('"forbidden_ip"', content)
        self.assertIn("disable_udp_443_guard", content)
        self.assertIn("已放行服务器出站 UDP/443", content)
        self.assertIn("udp dport 443 reject", content)
        self.assertNotIn("tcp dport 443 reject", content)

    def test_optimizer_tunes_shared_entry_port_capacity(self):
        content = (REPO_ROOT / "scripts" / "optimize_server.sh").read_text(encoding="utf-8")

        self.assertIn("LimitNOFILE=512000", content)
        self.assertIn("LimitNPROC=512000", content)
        self.assertIn("net.core.default_qdisc = fq", content)
        self.assertIn("net.ipv4.tcp_congestion_control = bbr", content)
        self.assertIn("net.core.somaxconn = 4096", content)
        self.assertIn("net.ipv4.tcp_max_syn_backlog = 8192", content)
        self.assertIn("net.ipv4.ip_local_port_range = 10000 65535", content)

    def test_optimizers_use_the_real_ssr_server_entrypoint(self):
        expected = "${SSR_DIR}/server.py"
        embedded = (REPO_ROOT / "scripts" / "optimize_server.sh").read_text(encoding="utf-8")
        standalone = (REPO_ROOT.parent / "ssr-server-optimizer" / "optimize-ssr.sh").read_text(
            encoding="utf-8"
        )

        for content in (embedded, standalone):
            self.assertIn(expected, content)
            self.assertIn('SSR_WORKDIR="${SSR_DIR}"', content)
            self.assertNotIn("${SSR_DIR}/shadowsocks/server.py a", content)

        self.assertIn("ExecStart=${PYTHON_BIN} ${SSR_DIR}/server.py m", embedded)
        self.assertIn("ExecStart=$pybin ${SSR_DIR}/server.py m", standalone)
        self.assertIn('"${SSR_LEGACY_INIT}" stop', embedded)
        self.assertIn('"$SSR_LEGACY_INIT" stop', standalone)

        self.assertIn("systemctl disable ssrmu.service", embedded)
        self.assertIn("systemctl disable ssrmu.service", standalone)

    def test_optimizers_install_firewall_sync_with_default_shared_port(self):
        embedded = (REPO_ROOT / "scripts" / "optimize_server.sh").read_text(encoding="utf-8")
        standalone = (REPO_ROOT.parent / "ssr-server-optimizer" / "optimize-ssr.sh").read_text(
            encoding="utf-8"
        )

        for content in (embedded, standalone):
            self.assertIn("sync_ssr_firewall.py", content)
            self.assertIn("/usr/local/libexec/ssr-panel/sync-firewall.py", content)
            self.assertIn("/etc/default/ssr-panel-firewall", content)
            self.assertIn("SSR_EXTRA_PORTS=18899", content)
            self.assertIn("EnvironmentFile=-", content)
            self.assertIn("ExecStartPre=", content)

        helper = (REPO_ROOT / "scripts" / "sync_ssr_firewall.py").read_text(encoding="utf-8")
        self.assertIn('return "18899"', helper)
        self.assertIn('"/etc/default/ssr-panel-firewall"', helper)

        for script in ("install.sh", "install-all.sh", "update.sh"):
            content = (REPO_ROOT / script).read_text(encoding="utf-8")
            self.assertIn("sync_ssr_firewall.py", content)

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

    def test_update_script_installs_missing_runtime_prerequisites(self):
        content = (REPO_ROOT / "update.sh").read_text(encoding="utf-8")

        self.assertIn("APT_UPDATED=0", content)
        self.assertIn("RPM_UPDATED=0", content)
        self.assertIn('APT_LOCK_TIMEOUT="${SSR_ADMIN_APT_LOCK_TIMEOUT:-300}"', content)
        self.assertIn('PACKAGE_INSTALL_RETRIES="${SSR_ADMIN_PACKAGE_INSTALL_RETRIES:-3}"', content)
        self.assertIn("install_packages()", content)
        self.assertIn("retry_command()", content)
        self.assertIn('DPkg::Lock::Timeout=${APT_LOCK_TIMEOUT}', content)
        self.assertIn("Acquire::Retries=3", content)
        self.assertIn('"${rpm_cmd}" makecache -q', content)
        self.assertIn("ensure_update_runtime", content)
        self.assertIn('ensure_command "git" "git"', content)
        self.assertIn('ensure_command "systemctl" "systemd"', content)
        self.assertIn('ensure_command "python3" "python3"', content)
        self.assertIn("install_packages python3-pip", content)
        self.assertIn('ensure_command "ss" "$_ss_pkg"', content)

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

    def test_update_script_guards_the_entire_post_backup_transaction(self):
        content = (REPO_ROOT / "update.sh").read_text(encoding="utf-8")

        self.assertIn("set -Eeuo pipefail", content)
        self.assertIn("flock -n", content)
        self.assertIn("TRANSACTION_ACTIVE", content)
        self.assertIn("trap 'handle_update_error $? $LINENO' ERR", content)
        self.assertIn('cp -a "${VENV_DIR}" "${BACKUP_DIR}/venv"', content)
        self.assertIn('restore_virtualenv', content)
        self.assertIn('verify_panel_health', content)

    def test_update_does_not_mutate_ssr_by_default(self):
        content = (REPO_ROOT / "update.sh").read_text(encoding="utf-8")

        self.assertIn('SSR_ADMIN_APPLY_SERVER_OPTIMIZATION:-0', content)
        self.assertIn('SSR_ADMIN_PATCH_SSR_COMPAT:-0', content)

    def test_update_script_excludes_virtualenv_from_backup_and_sync(self):
        content = (REPO_ROOT / "update.sh").read_text(encoding="utf-8")

        self.assertIn('"venv"', content)
        self.assertIn("follow_symlinks=False", content)

    def test_update_script_preserves_local_secret_artifacts_and_uses_venv(self):
        content = (REPO_ROOT / "update.sh").read_text(encoding="utf-8")

        self.assertIn('VENV_DIR="${SSR_ADMIN_VENV_DIR:-${PANEL_DIR}/venv}"', content)
        self.assertIn('"${VENV_DIR}/bin/python"', content)
        self.assertIn('".initial_ssr_password"', content)
        self.assertIn('"ssr-install.log"', content)
        self.assertIn('"${PANEL_DIR}/.initial_ssr_password"', content)
        self.assertIn('"${PANEL_DIR}/ssr-install.log"', content)

    def test_installers_harden_sensitive_files(self):
        for script in ("install.sh", "install-all.sh", "update.sh"):
            content = (REPO_ROOT / script).read_text(encoding="utf-8")
            self.assertIn("harden_sensitive_files", content)
            self.assertIn("chmod 0600", content)
            self.assertIn("chmod 0640", content)
            self.assertIn("config.py", content)
            self.assertIn("mudb.json", content)

    def test_full_install_generates_private_ssr_password(self):
        content = (REPO_ROOT / "install-all.sh").read_text(encoding="utf-8")

        self.assertIn("generate_password", content)
        self.assertIn("SSR_DEFAULT_PASSWORD", content)
        self.assertIn("SSR_SERVER_PUB_ADDR", content)
        self.assertIn("detect_server_pub_addr", content)
        self.assertIn(".initial_ssr_password", content)
        self.assertIn("SSR_INSTALL_LOG", content)
        self.assertIn("print_sanitized_ssr_install_log", content)
        self.assertIn("[redacted]", content)
        self.assertIn("SSR_ADMIN_SHOW_SECRETS", content)
        self.assertIn("默认隐藏", content)
        self.assertNotIn('echo -e "  密码:     ${YELLOW}doub.io${NC}"', content)

    def test_full_install_feeds_ssrmu_prompts_in_order(self):
        content = (REPO_ROOT / "install-all.sh").read_text(encoding="utf-8")

        self.assertIn(
            "printf '1\\n'\n"
            "        printf '%s\\n' \"$SSR_SERVER_PUB_ADDR\"\n"
            "        printf '\\n'\n"
            "        printf '\\n'\n"
            "        printf '%s\\n' \"$SSR_DEFAULT_PASSWORD\"",
            content,
        )

    def test_embedded_optimizer_supports_check_mode(self):
        content = (REPO_ROOT / "scripts" / "optimize_server.sh").read_text(encoding="utf-8")

        self.assertIn("check_mode()", content)
        self.assertIn("--check)", content)
        self.assertIn("preflight ok", content)

    def test_optimizer_summary_counts_listening_ssr_ports(self):
        content = (REPO_ROOT / "scripts" / "optimize_server.sh").read_text(encoding="utf-8")

        self.assertIn("count_ssr_ports", content)
        self.assertIn("mudb.json", content)
        self.assertNotIn('grep -c "server.py"', content)

    def test_optimizer_does_not_print_ipv6_patch_count(self):
        content = (REPO_ROOT / "scripts" / "optimize_server.sh").read_text(encoding="utf-8")

        self.assertNotIn("print(changed)", content)

    def test_panel_update_runner_uses_update_script_without_hard_reset(self):
        content = (REPO_ROOT / "scripts" / "run_panel_update.py").read_text(encoding="utf-8")
        self.assertIn("SSR_ADMIN_UPDATE_STATUS_FILE", content)
        self.assertIn("update_from_script", content)
        self.assertNotIn("reset\", \"--hard", content)

    def test_installers_prepare_minimal_debian_runtime(self):
        for script in ("install.sh", "install-all.sh"):
            content = (REPO_ROOT / script).read_text(encoding="utf-8")
            self.assertIn('APT_LOCK_TIMEOUT="${SSR_ADMIN_APT_LOCK_TIMEOUT:-300}"', content)
            self.assertIn('DPkg::Lock::Timeout=${APT_LOCK_TIMEOUT}', content)
            self.assertIn(
                "ca-certificates sudo curl wget socat git tar gzip unzip cron "
                "iproute2 jq iptables python3 python3-venv python3-pip systemd",
                content,
            )
            self.assertIn('"$SYSTEM_PYTHON3_BIN" -m pip --version', content)
            self.assertIn('"$SYSTEM_PYTHON3_BIN" -m venv --help', content)

    def test_installers_bootstrap_before_project_or_python_setup(self):
        runtime_functions = {
            "install.sh": "ensure_basic_runtime",
            "install-all.sh": "prepare_minimal_runtime",
        }

        for script, runtime_function in runtime_functions.items():
            content = (REPO_ROOT / script).read_text(encoding="utf-8")
            platform_call = content.index("\ndetect_platform\n")
            runtime_call = content.index(f"\n{runtime_function}\n")
            sync_call = content.index('\nsync_project_files "$')

            self.assertLess(platform_call, runtime_call, msg=script)
            self.assertLess(runtime_call, sync_call, msg=script)

    def test_installers_reject_unknown_platforms_before_mutating(self):
        for script in ("install.sh", "install-all.sh"):
            content = (REPO_ROOT / script).read_text(encoding="utf-8")

            self.assertIn("/etc/os-release", content)
            self.assertIn("command -v apt-get", content)
            self.assertIn("command -v dnf", content)
            self.assertIn("command -v yum", content)
            self.assertIn("不支持的操作系统或软件包管理器", content)
            self.assertNotIn('else\n    SYS="debian"\nfi', content)
            self.assertNotIn('SYS="other"\n    PKG_MANAGER="apt-get"', content)

    def test_installer_package_refresh_retries_without_false_success(self):
        for script in ("install.sh", "install-all.sh"):
            content = (REPO_ROOT / script).read_text(encoding="utf-8")
            bootstrap = content[
                content.index("# bootstrap-common:start") : content.index("# bootstrap-common:end")
            ]

            self.assertIn('PACKAGE_INSTALL_RETRIES="${SSR_ADMIN_PACKAGE_INSTALL_RETRIES:-3}"', content)
            self.assertIn('DPkg::Lock::Timeout=${APT_LOCK_TIMEOUT}', bootstrap)
            self.assertIn("retry_command", bootstrap)
            self.assertNotIn("makecache -q 2>/dev/null || true", bootstrap)
            self.assertLess(bootstrap.index("update -qq"), bootstrap.index("APT_UPDATED=1"))
            self.assertLess(bootstrap.index("makecache"), bootstrap.index("RPM_UPDATED=1"))

    def test_package_installers_wait_for_locks_without_deleting_lock_files(self):
        forbidden_lock_removals = (
            "rm -f /var/lib/dpkg/lock",
            "rm -f /var/lib/dpkg/lock-frontend",
            "rm -f /var/lib/apt/lists/lock",
            "rm -f /var/cache/apt/archives/lock",
        )

        for script in ("install.sh", "install-all.sh", "update.sh"):
            content = (REPO_ROOT / script).read_text(encoding="utf-8")
            self.assertIn('APT_LOCK_TIMEOUT="${SSR_ADMIN_APT_LOCK_TIMEOUT:-300}"', content)
            self.assertIn('PACKAGE_INSTALL_RETRIES="${SSR_ADMIN_PACKAGE_INSTALL_RETRIES:-3}"', content)
            self.assertGreaterEqual(content.count('DPkg::Lock::Timeout=${APT_LOCK_TIMEOUT}'), 1)
            self.assertIn("apt/dpkg", content)
            for forbidden in forbidden_lock_removals:
                self.assertNotIn(forbidden, content)

    def test_installers_install_and_verify_base_dependencies(self):
        debian_packages = (
            "ca-certificates sudo curl wget socat git tar gzip unzip cron "
            "iproute2 jq iptables python3 python3-venv python3-pip systemd"
        )
        rpm_packages = (
            "ca-certificates sudo curl wget socat git tar gzip unzip cronie "
            "iproute jq iptables-services python3 python3-pip systemd"
        )
        verified_commands = (
            "sudo curl wget socat git tar gzip unzip crontab ss jq iptables python3 systemctl"
        )

        for script in ("install.sh", "install-all.sh"):
            content = (REPO_ROOT / script).read_text(encoding="utf-8")
            self.assertIn(debian_packages, content)
            self.assertIn(rpm_packages, content)
            self.assertIn(verified_commands, content)
            self.assertIn("verify_base_runtime", content)
            self.assertIn('"$SYSTEM_PYTHON3_BIN" -m pip --version', content)
            self.assertIn('"$SYSTEM_PYTHON3_BIN" -m venv', content)

    def test_installers_verify_pip_inside_the_panel_virtualenv(self):
        for script in ("install.sh", "install-all.sh"):
            content = (REPO_ROOT / script).read_text(encoding="utf-8")
            self.assertIn('if ! "${PYTHON3_BIN}" -m pip --version', content)
            self.assertIn("面板 Python pip 不可用", content)

    def test_installers_require_a_running_systemd_manager(self):
        for script in ("install.sh", "install-all.sh"):
            content = (REPO_ROOT / script).read_text(encoding="utf-8")
            self.assertIn("require_systemd()", content)
            self.assertIn("/proc/1/comm", content)
            self.assertIn("systemctl show-environment", content)

    def test_standalone_installers_share_the_same_bootstrap_core(self):
        for marker in ("bootstrap-common", "runtime-common"):
            common_blocks = []
            for script in ("install.sh", "install-all.sh"):
                content = (REPO_ROOT / script).read_text(encoding="utf-8")
                start_marker = f"# {marker}:start"
                end_marker = f"# {marker}:end"
                start = content.index(start_marker)
                end = content.index(end_marker) + len(end_marker)
                common_blocks.append(content[start:end])

            self.assertEqual(common_blocks[0], common_blocks[1], msg=marker)

    def test_installers_reject_repo_subdir_traversal(self):
        for script in ("install.sh", "install-all.sh"):
            content = (REPO_ROOT / script).read_text(encoding="utf-8")
            self.assertIn("非法项目子目录", content)
            self.assertIn("*/../*", content)

    def test_installers_use_centos_package_names_for_runtime_dependencies(self):
        for script in ("install.sh", "install-all.sh"):
            content = (REPO_ROOT / script).read_text(encoding="utf-8")
            self.assertIn("RPM_UPDATED=0", content)
            self.assertIn('retry_command "$PACKAGE_MANAGER" makecache -q', content)
            self.assertIn(
                "ca-certificates sudo curl wget socat git tar gzip unzip cronie "
                "iproute jq iptables-services python3 python3-pip systemd",
                content,
            )
            self.assertIn('"$SYSTEM_PYTHON3_BIN" -m venv --help', content)

        install_content = (REPO_ROOT / "install.sh").read_text(encoding="utf-8")
        full_install_content = (REPO_ROOT / "install-all.sh").read_text(encoding="utf-8")
        self.assertIn('ensure_command "ss" "$_ss_pkg"', install_content)
        self.assertIn('ensure_minimal_command "ss" "$_ss_pkg"', full_install_content)

    def test_installers_support_legacy_python_runtime_dependencies(self):
        for script in ("install.sh", "install-all.sh", "update.sh"):
            content = (REPO_ROOT / script).read_text(encoding="utf-8")
            self.assertIn("python_version_lt", content)
            self.assertIn("Flask-Limiter>=1.5,<2.0", content)
            self.assertIn("waitress>=2.0,<2.1", content)
            self.assertIn("Flask-Limiter>=3.0,<3.5.1", content)

    def test_installers_use_panel_virtualenv_for_runtime_dependencies(self):
        for script in ("install.sh", "install-all.sh"):
            content = (REPO_ROOT / script).read_text(encoding="utf-8")
            self.assertIn("VENV_DIR=", content)
            self.assertIn("ensure_panel_venv", content)
            self.assertIn('PYTHON3_BIN="${VENV_DIR}/bin/python"', content)

    def test_project_sync_preserves_panel_virtualenv(self):
        for script in ("install.sh", "install-all.sh"):
            content = (REPO_ROOT / script).read_text(encoding="utf-8")
            self.assertNotIn('find "$target_dir" -mindepth 1', content)
            self.assertIn('scripts/sync_project_files.py', content)
            self.assertIn('sync_project_files "$', content)
            self.assertLess(content.index("    ensure_panel_venv\n"), content.index('\nsync_project_files "$'))

    def test_installers_require_flask_limiter_to_start_panel(self):
        for script in ("install.sh", "install-all.sh"):
            content = (REPO_ROOT / script).read_text(encoding="utf-8")
            self.assertNotIn("install_packages python3-waitress", content)
            self.assertNotIn("install_packages python3-flask", content)
            self.assertNotIn("install_packages python3-flask-limiter", content)
            self.assertIn("install_single_python_package Flask", content)
            self.assertIn("install_single_python_package waitress", content)
            self.assertIn("import flask\nimport flask_limiter\nimport waitress", content)

        update = (REPO_ROOT / "update.sh").read_text(encoding="utf-8")
        self.assertIn('import flask; import flask_limiter; import waitress', update)
        self.assertNotIn("内置限流兼容模式", update)

    def test_installers_write_password_hash_and_migrate_legacy_config(self):
        for script in ("install.sh", "install-all.sh"):
            content = (REPO_ROOT / script).read_text(encoding="utf-8")
            self.assertIn("ADMIN_PASSWORD_HASH", content)
            self.assertNotIn('"ADMIN_PASS": os.environ["ADMIN_PASS"]', content)

        update = (REPO_ROOT / "update.sh").read_text(encoding="utf-8")
        self.assertIn("security_utils.py", update)
        self.assertIn("migrate-config", update)

    def test_update_script_uses_python_version_checks_without_bc_or_eval(self):
        content = (REPO_ROOT / "update.sh").read_text(encoding="utf-8")
        self.assertNotIn("bc -l", content)
        self.assertNotIn("eval ${pip_bin}", content)
        self.assertIn("run_pip_install", content)

    def test_ssrmu_centos_package_manager_expands_yum_variable(self):
        content = (REPO_ROOT / "ssrmu.sh").read_text(encoding="utf-8")
        self.assertIn('Run_with_retries "${_yum}" makecache', content)
        self.assertNotIn("\\${_yum}", content)

    def test_ssrmu_validates_numeric_input_without_arithmetic_expansion(self):
        content = (REPO_ROOT / "ssrmu.sh").read_text(encoding="utf-8")
        numeric_inputs = (
            "ssr_port",
            "ssr_protocol_param",
            "ssr_speed_limit_per_con",
            "ssr_speed_limit_per_user",
            "ssr_transfer",
        )

        for variable in numeric_inputs:
            self.assertIn(f'[[ "${variable}" =~ ^[0-9]+$ ]]', content)
            self.assertNotIn(f'$((${{{variable}}}+0))', content)

    def test_ssrmu_bootstraps_python_and_does_not_hide_package_failures(self):
        content = (REPO_ROOT / "ssrmu.sh").read_text(encoding="utf-8")
        python_init = content[
            content.index("_init_python_bin(){") : content.index("\n}\n_init_python_bin")
        ]
        centos_packages = content[
            content.index("Centos_yum(){") : content.index("\n}\nDebian_apt")
        ]
        debian_packages = content[
            content.index("Debian_apt(){") : content.index("\n}\n# 下载 ShadowsocksR")
        ]

        self.assertNotIn("exit 1", python_init)
        self.assertIn("Run_with_retries", centos_packages)
        self.assertIn("Run_with_retries", debian_packages)
        self.assertNotIn("|| true", centos_packages)
        self.assertNotIn("|| true", debian_packages)
        self.assertIn("Centos_yum || exit 1", content)
        self.assertIn("Debian_apt || exit 1", content)

    def test_ssrmu_does_not_require_unzip_when_git_or_tar_is_available(self):
        content = (REPO_ROOT / "ssrmu.sh").read_text(encoding="utf-8")

        self.assertIn('fetch --depth 1 origin "${SSR_UPSTREAM_REF}"', content)
        self.assertIn("manyuser.tar.gz", content)
        self.assertIn("command -v git", content)
        self.assertIn("command -v tar", content)
        self.assertIn("command -v unzip", content)
        self.assertNotIn("依赖 unzip(解压压缩包) 安装失败", content)

    def test_ssrmu_installs_socat_for_network_helpers(self):
        content = (REPO_ROOT / "ssrmu.sh").read_text(encoding="utf-8")

        self.assertIn("wget socat", content)
        self.assertGreaterEqual(content.count("socat"), 2)

    def test_ssrmu_pins_and_verifies_the_upstream_ssr_source(self):
        content = (REPO_ROOT / "ssrmu.sh").read_text(encoding="utf-8")

        self.assertIn(
            'SSR_UPSTREAM_REF="${SSR_UPSTREAM_REF:-c4507b7af1fe20a5a6adbb5e3b5a86da9d3a35e8}"',
            content,
        )
        self.assertIn('fetch --depth 1 origin "${SSR_UPSTREAM_REF}"', content)
        self.assertIn('rev-parse HEAD', content)
        self.assertIn('^[0-9a-fA-F]{40}$', content)
        self.assertIn('${SSR_UPSTREAM_ARCHIVE_BASE}/${SSR_UPSTREAM_REF}.tar.gz', content)
        self.assertIn('Validate_SSR_layout', content)
        self.assertIn('.ssr-upstream-revision', content)
        self.assertNotIn('archive/refs/heads/manyuser.tar.gz', content)
        self.assertNotIn('archive/manyuser.zip', content)

    def test_ssrmu_uses_vendored_service_template_and_system_jq(self):
        content = (REPO_ROOT / "ssrmu.sh").read_text(encoding="utf-8")

        self.assertNotIn('/service/ssrmu_centos', content)
        self.assertNotIn('/service/ssrmu_debian', content)
        self.assertIn('Service_SSR(){\n\tCreate_local_ssr_init_script', content)
        self.assertIn('ln -sf "$(command -v jq)" "${jq_file}"', content)
        self.assertNotIn('mv "jq-linux32" "jq"', content)
        self.assertNotIn('/usr/share/zoneinfo/Asia/Shanghai', content)

    def test_installers_mark_managed_paths_and_validate_full_ssr_layout(self):
        panel_only = (REPO_ROOT / "install.sh").read_text(encoding="utf-8")
        full = (REPO_ROOT / "install-all.sh").read_text(encoding="utf-8")

        update = (REPO_ROOT / "update.sh").read_text(encoding="utf-8")

        for content in (panel_only, full, update):
            self.assertIn('.ssr-panel-managed', content)
        self.assertIn('validate_ssr_installation', full)
        self.assertIn('"${SSR_DIR}/server.py"', full)
        self.assertIn('"${SSR_DIR}/shadowsocks/server.py"', full)
        self.assertIn('"${MUDB_FILE}"', full)

    def test_ssrmu_firewall_supports_modern_backends_and_idempotent_rules(self):
        content = (REPO_ROOT / "ssrmu.sh").read_text(encoding="utf-8")

        self.assertIn('Firewall_uses_firewalld', content)
        self.assertIn('firewall-cmd --permanent --add-port', content)
        self.assertIn('firewall-cmd --permanent --remove-port', content)
        self.assertIn('iptables -C INPUT', content)
        self.assertIn('command -v ip6tables', content)
        self.assertIn('netfilter-persistent save', content)
        self.assertIn('/etc/sysconfig/iptables', content)
        self.assertNotIn('service iptables save || true', content)
        self.assertIn('Set_iptables || exit 1', content)
        self.assertIn('Add_iptables || exit 1', content)
        self.assertIn('Save_iptables || exit 1', content)

    def test_update_requires_a_running_systemd_manager_before_sync(self):
        content = (REPO_ROOT / "update.sh").read_text(encoding="utf-8")

        runtime = content[content.index('ensure_update_runtime()') : content.index('\n}\n\nacquire_update_lock')]
        self.assertIn('systemctl show-environment', runtime)

    def test_ssrmu_verifies_the_system_jq_link(self):
        content = (REPO_ROOT / "ssrmu.sh").read_text(encoding="utf-8")
        jq_install = content[content.index('JQ_install(){') : content.index('\n}\n# 安装 依赖')]

        self.assertIn('ln -sf "$(command -v jq)" "${jq_file}" || exit 1', jq_install)
        self.assertIn('[[ -x "${jq_file}" ]]', jq_install)

    def test_ssrmu_blocks_unverified_remote_root_scripts_by_default(self):
        content = (REPO_ROOT / "ssrmu.sh").read_text(encoding="utf-8")

        self.assertIn('SSR_ALLOW_UNVERIFIED_DOWNLOADS:-0', content)
        self.assertIn('Require_unverified_download_opt_in', content)
        self.assertGreaterEqual(content.count('Require_unverified_download_opt_in '), 7)
        update_shell = content[content.index('Update_Shell(){') : content.index('\n}\n# 显示 菜单状态')]
        self.assertNotIn('wget', update_shell)
        self.assertIn('/opt/ssr-admin-panel/update.sh', update_shell)

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
