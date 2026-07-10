#!/bin/bash

#=================================================
# SSR + 管理面板 一键部署脚本
# Author: Elegying
# GitHub: https://github.com/Elegying/SSR_Panel
#=================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

clear 2>/dev/null || true
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}    SSR + 管理面板 一键部署脚本${NC}"
echo -e "${GREEN}============================================${NC}"
echo -e "${CYAN}  GitHub: https://github.com/Elegying/SSR_Panel${NC}"
echo

# 检查root权限
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}请使用root权限运行此脚本${NC}"
    exit 1
fi

# 安装目录
PANEL_DIR="/opt/ssr-admin-panel"
VENV_DIR="${PANEL_DIR}/venv"
SSR_DIR="/usr/local/shadowsocksr"
MUDB_FILE="${SSR_DIR}/mudb.json"
DEVICE_STATS_FILE="${SSR_DEVICE_STATS_FILE:-/var/lib/ssr-admin-panel/device-stats.json}"
DEVICE_STATS_INTERVAL="${SSR_DEVICE_STATS_INTERVAL:-15}"
DEVICE_STATS_WINDOW="${SSR_DEVICE_STATS_WINDOW:-900}"
SSR_DEFAULT_PASSWORD="${SSR_DEFAULT_PASSWORD:-}"
SSR_SERVER_PUB_ADDR="${SSR_SERVER_PUB_ADDR:-}"
SSR_INITIAL_PASSWORD_FILE="${SSR_INITIAL_PASSWORD_FILE:-${PANEL_DIR}/.initial_ssr_password}"
SSR_INSTALL_LOG="${SSR_INSTALL_LOG:-${PANEL_DIR}/ssr-install.log}"
SSR_INSTALLED_BY_SCRIPT=0
REPO_URL="${SSR_ADMIN_REPO_URL:-https://github.com/Elegying/SSR_Panel.git}"
REPO_REF="${SSR_ADMIN_UPDATE_REF:-main}"
REPO_SUBDIR="${SSR_ADMIN_REPO_SUBDIR:-ssr-admin-panel}"
PYTHON3_BIN="/usr/bin/python3"
SYSTEM_PYTHON3_BIN="/usr/bin/python3"
SYS=""
PACKAGE_FAMILY=""
PACKAGE_MANAGER=""
PACKAGE_INSTALL_RETRIES="${SSR_ADMIN_PACKAGE_INSTALL_RETRIES:-3}"
APT_LOCK_TIMEOUT="${SSR_ADMIN_APT_LOCK_TIMEOUT:-300}"
APT_UPDATED=0
RPM_UPDATED=0
SYNC_REVISION=""
export DEBIAN_FRONTEND="${DEBIAN_FRONTEND:-noninteractive}"

# ========== 第零步：快速准备 ==========
echo -e "${CYAN}[ 0/6 ] 基础环境准备...${NC}"
echo -e "${YELLOW}----------------------------------------${NC}"
# bootstrap-common:start
detect_platform() {
    local os_id="" os_like=""

    if [ ! -r /etc/os-release ]; then
        echo -e "${RED}不支持的操作系统或软件包管理器: 缺少 /etc/os-release${NC}"
        exit 1
    fi

    # shellcheck disable=SC1091
    . /etc/os-release
    os_id="${ID:-}"
    os_like="${ID_LIKE:-}"

    case " ${os_id,,} ${os_like,,} " in
        *debian*|*ubuntu*)
            if ! command -v apt-get >/dev/null 2>&1; then
                echo -e "${RED}不支持的操作系统或软件包管理器: 未找到 apt-get${NC}"
                exit 1
            fi
            SYS="debian"
            PACKAGE_FAMILY="apt"
            PACKAGE_MANAGER="apt-get"
            ;;
        *rhel*|*fedora*|*centos*|*rocky*|*almalinux*)
            SYS="centos"
            PACKAGE_FAMILY="rpm"
            if command -v dnf >/dev/null 2>&1; then
                PACKAGE_MANAGER="dnf"
            elif command -v yum >/dev/null 2>&1; then
                PACKAGE_MANAGER="yum"
            else
                echo -e "${RED}不支持的操作系统或软件包管理器: 未找到 dnf/yum${NC}"
                exit 1
            fi
            ;;
        *)
            echo -e "${RED}不支持的操作系统或软件包管理器: ${os_id:-unknown}${NC}"
            exit 1
            ;;
    esac
}

retry_command() {
    local attempt=1

    while [ "$attempt" -le "$PACKAGE_INSTALL_RETRIES" ]; do
        if "$@"; then
            return 0
        fi
        if [ "$attempt" -eq "$PACKAGE_INSTALL_RETRIES" ]; then
            break
        fi
        echo -e "${YELLOW}命令失败，正在重试 (${attempt}/${PACKAGE_INSTALL_RETRIES})...${NC}" >&2
        sleep "$attempt"
        attempt=$((attempt + 1))
    done

    return 1
}

validate_package_settings() {
    case "$PACKAGE_INSTALL_RETRIES" in
        ''|*[!0-9]*|0)
            echo -e "${RED}SSR_ADMIN_PACKAGE_INSTALL_RETRIES 必须是正整数${NC}" >&2
            return 1
            ;;
    esac
    case "$APT_LOCK_TIMEOUT" in
        ''|*[!0-9]*)
            echo -e "${RED}SSR_ADMIN_APT_LOCK_TIMEOUT 必须是非负整数${NC}" >&2
            return 1
            ;;
    esac
}

apt_get() {
    apt-get -o Acquire::Retries=3 -o "DPkg::Lock::Timeout=${APT_LOCK_TIMEOUT}" "$@"
}

install_packages() {
    if [ "$PACKAGE_FAMILY" = "apt" ]; then
        if [ "$APT_UPDATED" -eq 0 ]; then
            echo -e "${YELLOW}如 apt/dpkg 正被系统更新占用，将等待最多 ${APT_LOCK_TIMEOUT} 秒...${NC}"
            echo -e "${YELLOW}刷新 apt 软件源索引...${NC}"
            retry_command apt_get update -qq || {
                echo -e "${RED}apt 软件源刷新失败${NC}" >&2
                return 1
            }
            APT_UPDATED=1
        fi
        retry_command apt_get install -y -qq "$@"
        return
    fi

    if [ "$PACKAGE_FAMILY" = "rpm" ]; then
        if [ "$RPM_UPDATED" -eq 0 ]; then
            echo -e "${YELLOW}刷新 yum/dnf 软件源索引...${NC}"
            retry_command "$PACKAGE_MANAGER" makecache -q || {
                echo -e "${RED}${PACKAGE_MANAGER} 软件源刷新失败${NC}" >&2
                return 1
            }
            RPM_UPDATED=1
        fi
        retry_command "$PACKAGE_MANAGER" install -y -q "$@"
        return
    fi

    echo -e "${RED}尚未识别可用的软件包管理器${NC}" >&2
    return 1
}
# bootstrap-common:end

ensure_minimal_command() {
    local binary=$1
    shift

    if command -v "$binary" &> /dev/null; then
        echo -e "${GREEN}✓ ${binary} 已就绪${NC}"
        return
    fi

    echo -e "${YELLOW}${binary} 未找到，正在安装最小依赖...${NC}"
    install_packages "$@" || {
        echo -e "${RED}${binary} 安装失败，请手动安装后重试${NC}"
        exit 1
    }
}

python_version_lt() {
    "$PYTHON3_BIN" - "$1" "$2" <<'PY' &>/dev/null
import sys

major = int(sys.argv[1])
minor = int(sys.argv[2])
raise SystemExit(0 if sys.version_info < (major, minor) else 1)
PY
}

python_version_ge() {
    "$PYTHON3_BIN" - "$1" "$2" <<'PY' &>/dev/null
import sys

major = int(sys.argv[1])
minor = int(sys.argv[2])
raise SystemExit(0 if sys.version_info >= (major, minor) else 1)
PY
}

install_python_runtime_with_pip() {
    local req_file="$1"
    local pip_install_opts=(--no-input --disable-pip-version-check)

    # Debian 12+ / Ubuntu 24+ PEP 668: allow system-wide install outside venv.
    if python_version_ge 3 11; then
        pip_install_opts+=(--break-system-packages)
    fi

    if python_version_lt 3 7; then
        echo -e "${YELLOW}检测到 Python 3.6，安装兼容版 Flask 运行时...${NC}"
        "$PYTHON3_BIN" -m pip install "${pip_install_opts[@]}" --prefer-binary -q \
            'Flask>=2.0,<2.1' \
            'Werkzeug>=2.0,<2.1' \
            'Jinja2>=3.0,<3.1' \
            'MarkupSafe>=2.0,<2.1' \
            'itsdangerous>=2.0,<2.1' \
            'click>=8.0,<8.1' \
            'Flask-Limiter>=1.5,<2.0' \
            'waitress>=2.0,<2.1'
        return
    fi

    if python_version_lt 3 8; then
        echo -e "${YELLOW}检测到 Python 3.7，安装兼容版 Flask 运行时...${NC}"
        "$PYTHON3_BIN" -m pip install "${pip_install_opts[@]}" --prefer-binary -q \
            'Flask>=2.2,<2.3' \
            'Flask-Limiter>=3.0,<3.5.1' \
            'waitress>=2.1,<2.2'
        return
    fi

    "$PYTHON3_BIN" -m pip install "${pip_install_opts[@]}" --prefer-binary -q -r "${req_file}"
}

install_single_python_package() {
    local package="$1"
    local pip_install_opts=(--no-input --disable-pip-version-check)
    if python_version_ge 3 11; then
        pip_install_opts+=(--break-system-packages)
    fi
    if python_version_lt 3 7; then
        case "${package}" in
            Flask|flask) package='Flask>=2.0,<2.1' ;;
            flask-limiter|Flask-Limiter) package='Flask-Limiter>=1.5,<2.0' ;;
            waitress|Waitress) package='waitress>=2.0,<2.1' ;;
        esac
    elif python_version_lt 3 8; then
        case "${package}" in
            Flask|flask) package='Flask>=2.2,<2.3' ;;
            flask-limiter|Flask-Limiter) package='Flask-Limiter>=3.0,<3.5.1' ;;
            waitress|Waitress) package='waitress>=2.1,<2.2' ;;
        esac
    fi
    "$PYTHON3_BIN" -m pip install "${pip_install_opts[@]}" -q "${package}"
}

generate_password() {
    "$PYTHON3_BIN" - <<'PY'
import secrets
import string

alphabet = string.ascii_letters + string.digits
print(''.join(secrets.choice(alphabet) for _ in range(18)))
PY
}

detect_server_pub_addr() {
    local detected
    detected="$(curl -fsS --max-time 5 ip.sb 2>/dev/null || curl -fsS --max-time 5 ifconfig.me 2>/dev/null || true)"
    printf '%s' "$detected"
}

harden_sensitive_files() {
    chmod 600 "$PANEL_DIR/config.py" "$MUDB_FILE" "$SSR_INITIAL_PASSWORD_FILE" 2>/dev/null || true
}

persist_initial_ssr_password() {
    mkdir -p "$(dirname "$SSR_INITIAL_PASSWORD_FILE")"
    install -m 600 /dev/null "$SSR_INITIAL_PASSWORD_FILE"
    printf '%s\n' "$SSR_DEFAULT_PASSWORD" > "$SSR_INITIAL_PASSWORD_FILE"
    chmod 600 "$SSR_INITIAL_PASSWORD_FILE" 2>/dev/null || true
}

print_sanitized_ssr_install_log() {
    SSR_DEFAULT_PASSWORD="$SSR_DEFAULT_PASSWORD" "$PYTHON3_BIN" - "$SSR_INSTALL_LOG" <<'PY' | tail -n 80 || true
import os
import re
import sys
from pathlib import Path

log_path = Path(sys.argv[1])
password = os.environ.get("SSR_DEFAULT_PASSWORD", "")
text = log_path.read_text(encoding="utf-8", errors="replace")
if password:
    text = text.replace(password, "[redacted]")
text = re.sub(r"ssr://[A-Za-z0-9_=-]+", "ssr://[redacted]", text)
print(text, end="" if text.endswith("\n") else "\n")
PY
}

ensure_panel_venv() {
    SYSTEM_PYTHON3_BIN=$(command -v python3 2>/dev/null || echo "/usr/bin/python3")

    if [ ! -x "${VENV_DIR}/bin/python" ]; then
        echo -e "${YELLOW}创建面板 Python 虚拟环境...${NC}"
        "${SYSTEM_PYTHON3_BIN}" -m venv "${VENV_DIR}" || {
            echo -e "${RED}面板 Python 虚拟环境创建失败${NC}" >&2
            exit 1
        }
    fi

    PYTHON3_BIN="${VENV_DIR}/bin/python"
    "${PYTHON3_BIN}" -m ensurepip --upgrade >/dev/null 2>&1 || true
    if ! "${PYTHON3_BIN}" -m pip --version >/dev/null 2>&1; then
        echo -e "${RED}面板 Python pip 不可用${NC}" >&2
        exit 1
    fi
    "${PYTHON3_BIN}" -m pip install --upgrade pip setuptools wheel --no-input --disable-pip-version-check -q 2>/dev/null || true
}

# runtime-common:start
base_dependency_packages() {
    if [ "$SYS" = "centos" ]; then
        echo "ca-certificates sudo curl wget socat git tar gzip unzip cronie iproute jq iptables-services python3 python3-pip systemd"
    else
        echo "ca-certificates sudo curl wget socat git tar gzip unzip cron iproute2 jq iptables python3 python3-venv python3-pip systemd"
    fi
}

require_systemd() {
    local init_name=""

    if [ -r /proc/1/comm ]; then
        IFS= read -r init_name < /proc/1/comm
    fi
    if [ "$init_name" != "systemd" ] || ! systemctl show-environment >/dev/null 2>&1; then
        echo -e "${RED}当前环境未运行可用的 systemd（容器、WSL 或 chroot 请改用完整虚拟机）${NC}" >&2
        return 1
    fi
}

verify_base_runtime() {
    local cmd
    local required_commands="sudo curl wget socat git tar gzip unzip crontab ss jq iptables python3 systemctl"

    for cmd in $required_commands; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            echo -e "${RED}系统依赖验证失败: 未找到 ${cmd}${NC}" >&2
            return 1
        fi
    done

    if [ ! -s /etc/ssl/certs/ca-certificates.crt ] && [ ! -s /etc/pki/tls/certs/ca-bundle.crt ]; then
        echo -e "${RED}系统依赖验证失败: CA 证书包不可用${NC}" >&2
        return 1
    fi
    if ! "$SYSTEM_PYTHON3_BIN" -m pip --version >/dev/null 2>&1; then
        echo -e "${RED}系统依赖验证失败: Python pip 不可用${NC}" >&2
        return 1
    fi
    if ! "$SYSTEM_PYTHON3_BIN" -m venv --help >/dev/null 2>&1; then
        echo -e "${RED}系统依赖验证失败: Python venv 不可用${NC}" >&2
        return 1
    fi
    require_systemd
}
# runtime-common:end

prepare_minimal_runtime() {
    echo -e "${GREEN}检查并安装最小运行环境...${NC}"

    install_packages $(base_dependency_packages) || {
        echo -e "${RED}系统依赖安装失败${NC}" >&2
        exit 1
    }
    SYSTEM_PYTHON3_BIN=$(command -v python3 2>/dev/null || true)
    PYTHON3_BIN="$SYSTEM_PYTHON3_BIN"
    verify_base_runtime || exit 1
    ensure_panel_venv
    echo -e "${GREEN}✓ 系统依赖已就绪${NC}"
}

install_flask_runtime() {
    if "$PYTHON3_BIN" -c "import flask; import waitress" &>/dev/null; then
        echo -e "${GREEN}✓ Flask 运行时已就绪${NC}"
        return
    fi

    local req_file="${PANEL_DIR}/requirements.txt"
    echo -e "${GREEN}安装 Python 依赖...${NC}"

    if "$PYTHON3_BIN" -m pip --version &>/dev/null && [ -f "${req_file}" ]; then
        install_python_runtime_with_pip "${req_file}" 2>/dev/null || true
    fi

    # 面板运行在独立 venv 中，依赖必须安装到该 venv，系统 Python 包不可见。
    if ! "$PYTHON3_BIN" -c "import flask" &>/dev/null; then
        echo -e "${YELLOW}批量安装 Flask 失败，尝试在 venv 中单独安装...${NC}"
        install_single_python_package Flask
    fi

    if ! "$PYTHON3_BIN" -c "import flask_limiter" &>/dev/null; then
        echo -e "${YELLOW}pip 安装 Flask-Limiter 失败，尝试系统包...${NC}"
        install_single_python_package flask-limiter 2>/dev/null || true
    fi

    if ! "$PYTHON3_BIN" -c "import waitress" &>/dev/null; then
        echo -e "${YELLOW}pip 安装 Waitress 失败，尝试单独安装...${NC}"
        install_single_python_package waitress
    fi

    if ! "$PYTHON3_BIN" - <<'PY' &>/dev/null
import flask
import waitress
PY
    then
        echo -e "${RED}Flask 运行时安装失败，请检查 Python 依赖${NC}"
        echo -e "${CYAN}诊断命令:${NC} ${PYTHON3_BIN} -m pip show Flask flask-limiter"
        exit 1
    fi
}

apply_ssr_python_compatibility_fix() {
    if [ ! -d "$SSR_DIR" ]; then
        return 0
    fi

    echo -e "${GREEN}修复 ShadowsocksR 的 Python 3.10+ 兼容性...${NC}"
    "$PYTHON3_BIN" "$PANEL_DIR/scripts/patch_ssr_python_compat.py" "$SSR_DIR"
}

validate_ssr_installation() {
    local required
    for required in \
        "${SSR_DIR}/server.py" \
        "${SSR_DIR}/shadowsocks/server.py" \
        "${SSR_DIR}/mujson_mgr.py" \
        "${SSR_DIR}/userapiconfig.py" \
        "${MUDB_FILE}"
    do
        if [ ! -f "${required}" ]; then
            echo -e "${RED}SSR 安装不完整，缺少: ${required}${NC}" >&2
            return 1
        fi
    done

    "${PYTHON3_BIN}" - "${MUDB_FILE}" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
if not isinstance(data, list):
    raise SystemExit("mudb.json root must be a list")
PY
}

install_device_stats_service() {
    echo -e "${GREEN}配置设备统计服务...${NC}"
    local _ss_pkg="iproute2"
    [ "$SYS" = "centos" ] && _ss_pkg="iproute"
    ensure_minimal_command "ss" "$_ss_pkg"
    mkdir -p "$(dirname "$DEVICE_STATS_FILE")"
    printf 'managed\n' > "$(dirname "$DEVICE_STATS_FILE")/.ssr-panel-managed"
    chmod +x "$PANEL_DIR/scripts/collect_device_stats.py" 2>/dev/null || true

    cat > /etc/systemd/system/ssr-device-stats.service <<SERVICE
# Managed by SSR_Panel
[Unit]
Description=SSR Device Stats Collector
After=network.target

[Service]
Type=simple
User=root
ExecStart=${PYTHON3_BIN} ${PANEL_DIR}/scripts/collect_device_stats.py --mudb ${MUDB_FILE} --output ${DEVICE_STATS_FILE} --interval ${DEVICE_STATS_INTERVAL} --window ${DEVICE_STATS_WINDOW} --watch
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

    systemctl daemon-reload
    systemctl enable ssr-device-stats
    systemctl restart ssr-device-stats || true

    if systemctl is-active --quiet ssr-device-stats; then
        echo -e "${GREEN}✓ ssr-device-stats 服务运行中${NC}"
    else
        echo -e "${YELLOW}ssr-device-stats 服务未运行，请检查: journalctl -u ssr-device-stats -n 50 --no-pager${NC}"
    fi
}

sync_project_files() {
    local target_dir="$1"
    local tmp_clone_dir source_dir

    case "$REPO_SUBDIR" in
        /*|..|../*|*/..|*/../*)
            echo -e "${RED}非法项目子目录: ${REPO_SUBDIR}${NC}" >&2
            exit 1
            ;;
    esac

    tmp_clone_dir=$(mktemp -d /tmp/ssr-admin-panel.XXXXXX)
    git clone --depth 1 --branch "$REPO_REF" "$REPO_URL" "$tmp_clone_dir" -q
    source_dir="$tmp_clone_dir"
    if [ -n "$REPO_SUBDIR" ]; then
        source_dir="$tmp_clone_dir/$REPO_SUBDIR"
    fi

    if [ ! -f "$source_dir/app.py" ]; then
        echo -e "${RED}Project files not found: ${source_dir}${NC}"
        rm -rf "$tmp_clone_dir"
        exit 1
    fi

    mkdir -p "$target_dir"
    "$PYTHON3_BIN" "$source_dir/scripts/sync_project_files.py" "$source_dir" "$target_dir"
    SYNC_REVISION=$(git -C "$tmp_clone_dir" rev-parse --short HEAD 2>/dev/null || echo "")
    rm -rf "$tmp_clone_dir"
}

detect_platform
validate_package_settings || exit 1
echo -e "${CYAN}系统检测: ${YELLOW}${SYS} (${PACKAGE_MANAGER})${NC}"
prepare_minimal_runtime

echo
echo -e "${GREEN}快速模式已启用${NC}"
echo -e "${CYAN}已跳过:${NC} cymysql 安装 / 自动 Swap 配置"
echo -e "${CYAN}基础依赖:${NC} 已完成安装并逐项验证"
echo

# ========== 第一步：下载项目文件 ==========
echo -e "${CYAN}[ 1/6 ] 下载项目文件...${NC}"

sync_project_files "$PANEL_DIR"
printf 'managed\n' > "$PANEL_DIR/.ssr-panel-managed"

cd $PANEL_DIR
chmod +x "$PANEL_DIR/update.sh" "$PANEL_DIR/install.sh" "$PANEL_DIR/install-all.sh" "$PANEL_DIR/uninstall.sh" "$PANEL_DIR/scripts/collect_device_stats.py" "$PANEL_DIR/scripts/sync_ssr_firewall.py" "$PANEL_DIR/scripts/optimize_server.sh" 2>/dev/null || true
APP_VERSION=$(cat "$PANEL_DIR/VERSION" 2>/dev/null | tr -d '\r\n')
APP_REVISION="${SYNC_REVISION:-$(git -C "$PANEL_DIR" rev-parse --short HEAD 2>/dev/null || echo "")}"
PANEL_BUILD_INFO_FILE="$PANEL_DIR/.panel-build.json"
PANEL_BUILD_VERSION="$APP_VERSION" PANEL_BUILD_REVISION="$APP_REVISION" PANEL_BUILD_INFO_FILE="$PANEL_BUILD_INFO_FILE" "$PYTHON3_BIN" <<'PY'
import json
import os
from pathlib import Path

version = os.environ.get("PANEL_BUILD_VERSION", "").strip() or "unknown"
revision = os.environ.get("PANEL_BUILD_REVISION", "").strip()
display_version = version if not revision or revision == version or revision in version else f"{version} ({revision})"
Path(os.environ["PANEL_BUILD_INFO_FILE"]).write_text(
    json.dumps(
        {
            "version": version,
            "revision": revision,
            "display_version": display_version,
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)
PY

echo -e "${GREEN}✓ 项目文件下载完成${NC}"
echo

# ========== 第二步：配置信息 ==========
echo -e "${CYAN}[ 2/6 ] 配置信息${NC}"
echo -e "${YELLOW}----------------------------------------${NC}"

# 支持环境变量非交互式配置
ADMIN_USER="${SSR_ADMIN_USER:-}"
ADMIN_PASS="${SSR_ADMIN_PASS:-}"

# 安全读取函数：优先 tty，其次 stdin，失败则报错退出
safe_read() {
    local var_name="$1"
    local prompt="$2"
    local is_password="$3"

    if [ -n "${!var_name:-}" ]; then
        return 0
    fi

    local input=""
    if [ -t 0 ]; then
        if [ "$is_password" = "yes" ]; then read -r -s -p "$prompt" input; echo; else read -r -p "$prompt" input; fi
    elif [ -e /dev/tty ]; then
        if [ "$is_password" = "yes" ]; then read -s -p "$prompt" input < /dev/tty; echo; else read -r -p "$prompt" input < /dev/tty; fi
    else
        return 1
    fi

    printf -v "$var_name" '%s' "$input"
    return 0
}

# 获取用户名
if [ -z "$ADMIN_USER" ]; then
    if safe_read ADMIN_USER "请输入管理面板用户名: " "no"; then
        if [ -z "$ADMIN_USER" ]; then
            echo -e "${RED}用户名不能为空！${NC}"
            exit 1
        fi
    else
        echo -e "${RED}无法读取用户名（非交互模式请设置 SSR_ADMIN_USER 环境变量）${NC}"
        exit 1
    fi
fi

# 获取密码
if [ -z "$ADMIN_PASS" ]; then
    if safe_read ADMIN_PASS "请输入管理面板密码: " "yes"; then
        if [ -z "$ADMIN_PASS" ]; then
            echo -e "${RED}密码不能为空！${NC}"
            exit 1
        fi
        # 确认密码
        if safe_read ADMIN_PASS_CONFIRM "请再次输入密码确认: " "yes"; then
            if [ "$ADMIN_PASS" != "$ADMIN_PASS_CONFIRM" ]; then
                echo -e "${RED}两次密码不一致！${NC}"
                exit 1
            fi
        else
            echo -e "${RED}无法读取确认密码！${NC}"
            exit 1
        fi
    else
        echo -e "${RED}无法读取密码（非交互模式请设置 SSR_ADMIN_PASS 环境变量）${NC}"
        exit 1
    fi
fi

SHARE_HOST=""
SHARE_PORT="18899"
SHARE_PASSWORD=""
SHARE_REMARKS=""
SHARE_PROTOCOL="auth_aes128_md5"
SHARE_METHOD="aes-256-cfb"
SHARE_OBFS="tls1.2_ticket_auth"
SHARE_OBFS_PARAM="www.baidu.com"

echo
echo -e "${CYAN}[ 可选：配置账号分享模板 ]${NC}"
echo -e "${YELLOW}留空或选择 N 则默认关闭分享功能，真实值只写入本机 config.py${NC}"

# 非交互模式（已设置环境变量）自动跳过分享配置
if [ -n "${SSR_ADMIN_USER:-}" ]; then
    ENABLE_SHARE_TEMPLATE="n"
    echo -e "${YELLOW}检测到非交互模式，已跳过分享配置${NC}"
else
    if [ -t 0 ]; then
        read -p "是否启用账号分享模板？[y/N]: " ENABLE_SHARE_TEMPLATE
    elif [ -e /dev/tty ]; then
        read -p "是否启用账号分享模板？[y/N]: " ENABLE_SHARE_TEMPLATE < /dev/tty
    else
        ENABLE_SHARE_TEMPLATE="n"
    fi
fi

ENABLE_SHARE_TEMPLATE=$(printf '%s' "$ENABLE_SHARE_TEMPLATE" | tr '[:upper:]' '[:lower:]')

if [ "$ENABLE_SHARE_TEMPLATE" = "y" ] || [ "$ENABLE_SHARE_TEMPLATE" = "yes" ]; then
    # 读取分享域名
    if [ -t 0 ]; then read -p "请输入分享域名/IP: " SHARE_HOST
    elif [ -e /dev/tty ]; then read -p "请输入分享域名/IP: " SHARE_HOST < /dev/tty
    else SHARE_HOST=""; fi

    if [ -z "$SHARE_HOST" ]; then
        echo -e "${RED}分享域名不能为空，已关闭分享功能${NC}"
        ENABLE_SHARE_TEMPLATE="n"
    else
        # 分享端口/密码/备注均使用默认值，不提示输入
        SHARE_PORT="18899"
        SHARE_PASSWORD="nikuaimobi"
        SHARE_REMARKS="私家车-2025"
    fi
fi

echo
echo -e "${GREEN}✓ 配置完成${NC}"
echo

# ========== 第三步：安装SSR ==========
echo -e "${CYAN}[ 3/6 ] 安装 ShadowsocksR${NC}"
echo -e "${YELLOW}----------------------------------------${NC}"

if [ -d "$SSR_DIR" ] && validate_ssr_installation; then
    echo -e "${GREEN}检测到已安装SSR，跳过安装...${NC}"
elif [ -d "$SSR_DIR" ]; then
    echo -e "${RED}检测到不完整的 SSR 目录，请备份后清理再重试: ${SSR_DIR}${NC}" >&2
    exit 1
else
    echo -e "${GREEN}开始自动安装 SSR...${NC}"
    SSR_INSTALLED_BY_SCRIPT=1
    if [ -z "$SSR_DEFAULT_PASSWORD" ]; then
        SSR_DEFAULT_PASSWORD="$(generate_password)"
    fi
    if [ -z "$SSR_SERVER_PUB_ADDR" ]; then
        SSR_SERVER_PUB_ADDR="$(detect_server_pub_addr)"
    fi
    persist_initial_ssr_password

    chmod +x $PANEL_DIR/ssrmu.sh

    # 使用管道输入：安装 SSR，设置服务器地址，保留默认用户名/端口，但使用随机初始密码。
    mkdir -p "$(dirname "$SSR_INSTALL_LOG")"
    install -m 600 /dev/null "$SSR_INSTALL_LOG"
    if ! {
        printf '1\n'
        printf '%s\n' "$SSR_SERVER_PUB_ADDR"
        printf '\n'
        printf '\n'
        printf '%s\n' "$SSR_DEFAULT_PASSWORD"
        for i in $(seq 1 50); do printf '\n'; done
    } | bash "$PANEL_DIR/ssrmu.sh" >"$SSR_INSTALL_LOG" 2>&1; then
        echo -e "${RED}SSR 安装失败，日志: ${SSR_INSTALL_LOG}${NC}"
        print_sanitized_ssr_install_log
        exit 1
    fi
    chmod 600 "$SSR_INSTALL_LOG" 2>/dev/null || true
    echo -e "${GREEN}SSR 安装日志: ${SSR_INSTALL_LOG}${NC}"

    if validate_ssr_installation; then
        printf 'managed\n' > "$SSR_DIR/.ssr-panel-managed"
        echo -e "${GREEN}✓ SSR安装完成${NC}"
    else
        echo -e "${RED}SSR安装不完整，请检查日志: ${SSR_INSTALL_LOG}${NC}"
        exit 1
    fi
fi

harden_sensitive_files
apply_ssr_python_compatibility_fix

echo

# ========== 第四步：安装管理面板 ==========
echo -e "${CYAN}[ 4/6 ] 安装管理面板${NC}"
echo -e "${YELLOW}----------------------------------------${NC}"

install_flask_runtime

echo -e "${GREEN}生成配置文件...${NC}"
if [ -f "$PANEL_DIR/config.py" ]; then
    echo -e "${YELLOW}检测到现有配置文件，已保留: $PANEL_DIR/config.py${NC}"
else
SECRET_KEY=$("$PYTHON3_BIN" -c "import secrets; print(secrets.token_hex(32))")
PANEL_DIR="$PANEL_DIR" ADMIN_USER="$ADMIN_USER" ADMIN_PASS="$ADMIN_PASS" SECRET_KEY="$SECRET_KEY" MUDB_FILE="$MUDB_FILE" DEVICE_STATS_FILE="$DEVICE_STATS_FILE" SHARE_HOST="$SHARE_HOST" SHARE_PORT="$SHARE_PORT" SHARE_PASSWORD="$SHARE_PASSWORD" SHARE_REMARKS="$SHARE_REMARKS" SHARE_PROTOCOL="$SHARE_PROTOCOL" SHARE_METHOD="$SHARE_METHOD" SHARE_OBFS="$SHARE_OBFS" SHARE_OBFS_PARAM="$SHARE_OBFS_PARAM" "$PYTHON3_BIN" << 'PY'
import os
from pathlib import Path


def to_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


config_path = Path(os.environ["PANEL_DIR"]) / "config.py"
values = {
    "ADMIN_USER": os.environ["ADMIN_USER"],
    "ADMIN_PASS": os.environ["ADMIN_PASS"],
    "SECRET_KEY": os.environ["SECRET_KEY"],
    "MUDB_FILE": os.environ["MUDB_FILE"],
    "SSR_SHARE_HOST": os.environ.get("SHARE_HOST", ""),
    "SSR_SHARE_PORT": to_int(os.environ.get("SHARE_PORT"), 18899),
    "SSR_SHARE_PASSWORD": os.environ.get("SHARE_PASSWORD", ""),
    "SSR_SHARE_REMARKS": os.environ.get("SHARE_REMARKS", ""),
    "SSR_SHARE_PROTOCOL": os.environ.get("SHARE_PROTOCOL", "auth_aes128_md5"),
    "SSR_SHARE_METHOD": os.environ.get("SHARE_METHOD", "aes-256-cfb"),
    "SSR_SHARE_OBFS": os.environ.get("SHARE_OBFS", "tls1.2_ticket_auth"),
    "SSR_SHARE_OBFS_PARAM": os.environ.get("SHARE_OBFS_PARAM", "www.baidu.com"),
    "DEVICE_STATS_FILE": os.environ.get("DEVICE_STATS_FILE", "/var/lib/ssr-admin-panel/device-stats.json"),
    "DEVICE_STATS_STALE_SECONDS": 120,
}

with config_path.open("w", encoding="utf-8") as f:
    f.write("# SSR Admin Panel 配置文件\n")
    for key, value in values.items():
        f.write(f"{key} = {value!r}\n")
PY
fi
harden_sensitive_files

echo -e "${GREEN}配置系统服务...${NC}"
install_device_stats_service

cat > /etc/systemd/system/ssr-admin.service <<SERVICE
# Managed by SSR_Panel
[Unit]
Description=SSR Admin Panel
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/ssr-admin-panel
ExecStart=${PYTHON3_BIN} -m waitress --host=0.0.0.0 --port=5000 app:app
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
RestrictSUIDSGID=true
LockPersonality=true
UMask=0077

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable ssr-admin
systemctl restart ssr-admin

sleep 2
if systemctl is-active --quiet ssr-admin; then
    echo -e "${GREEN}✓ ssr-admin 服务运行中${NC}"
else
    echo -e "${RED}ssr-admin 服务启动失败${NC}"
    echo -e "${CYAN}诊断命令:${NC} journalctl -u ssr-admin -n 50 --no-pager"
    journalctl -u ssr-admin -n 50 --no-pager || true
    exit 1
fi

# ── SSR 服务器性能优化 ──
echo -e "${CYAN}[ 5/6 ] SSR 服务器性能优化...${NC}"
bash "$PANEL_DIR/scripts/optimize_server.sh"
if ! systemctl is-active --quiet ssr.service; then
    echo -e "${RED}SSR systemd 服务未启动，部署中止${NC}" >&2
    journalctl -u ssr.service -n 50 --no-pager || true
    exit 1
fi

APP_VERSION=$(cat "$PANEL_DIR/VERSION" 2>/dev/null || echo "unknown")

# ========== 完成 ==========
echo -e "${CYAN}[ 6/6 ] 完成${NC}"
sleep 2
echo
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}           安装完成！${NC}"
echo -e "${GREEN}============================================${NC}"
echo
IP=$(curl -s ip.sb 2>/dev/null || curl -s ifconfig.me 2>/dev/null || echo 'your-server-ip')
echo -e "${CYAN}管理面板信息:${NC}"
echo -e "  访问地址: ${YELLOW}http://${IP}:5000${NC}"
echo -e "  用户名:   ${YELLOW}${ADMIN_USER}${NC}"
if [ "${SSR_ADMIN_SHOW_SECRETS:-0}" = "1" ]; then
    echo -e "  密码:     ${YELLOW}${ADMIN_PASS}${NC}"
else
    echo -e "  密码:     ${YELLOW}已写入 ${PANEL_DIR}/config.py（默认隐藏）${NC}"
fi
echo -e "  版本:     ${YELLOW}${APP_VERSION}${NC}"
echo
echo -e "${CYAN}SSR默认用户:${NC}"
if [ "$SSR_INSTALLED_BY_SCRIPT" -eq 1 ]; then
    echo -e "  用户名:   ${YELLOW}doubi${NC}"
    echo -e "  端口:     ${YELLOW}2333${NC}"
    if [ "${SSR_ADMIN_SHOW_SECRETS:-0}" = "1" ]; then
        echo -e "  密码:     ${YELLOW}${SSR_DEFAULT_PASSWORD}${NC}"
    else
        echo -e "  密码文件: ${YELLOW}${SSR_INITIAL_PASSWORD_FILE}${NC}"
    fi
else
    echo -e "  ${YELLOW}检测到已有 SSR，未改动现有用户${NC}"
fi
echo
echo -e "${CYAN}常用命令:${NC}"
echo -e "  重启面板:     ${YELLOW}systemctl restart ssr-admin${NC}"
echo -e "  更新面板:     ${YELLOW}bash /opt/ssr-admin-panel/update.sh${NC}"
echo -e "  卸载面板:     ${YELLOW}bash /opt/ssr-admin-panel/uninstall.sh --yes${NC}"
echo -e "  管理SSR:      ${YELLOW}bash /opt/ssr-admin-panel/ssrmu.sh${NC}"
echo
echo -e "${GREEN}感谢使用！${NC}"
echo
