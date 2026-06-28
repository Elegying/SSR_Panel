#!/bin/bash

# SSR Admin Panel 一键安装脚本
# Author: Elegying
# GitHub: https://github.com/Elegying/SSR_Panel

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}    SSR Admin Panel 一键安装脚本${NC}"
echo -e "${GREEN}========================================${NC}"

# 检查root权限
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}请使用root权限运行此脚本${NC}"
    exit 1
fi

# 安装目录
INSTALL_DIR="/opt/ssr-admin-panel"
VENV_DIR="${INSTALL_DIR}/venv"
MUDB_FILE="/usr/local/shadowsocksr/mudb.json"
SSR_DIR="/usr/local/shadowsocksr"
DEVICE_STATS_FILE="${SSR_DEVICE_STATS_FILE:-/var/lib/ssr-admin-panel/device-stats.json}"
DEVICE_STATS_INTERVAL="${SSR_DEVICE_STATS_INTERVAL:-15}"
DEVICE_STATS_WINDOW="${SSR_DEVICE_STATS_WINDOW:-900}"
REPO_URL="${SSR_ADMIN_REPO_URL:-https://github.com/Elegying/SSR_Panel.git}"
REPO_REF="${SSR_ADMIN_UPDATE_REF:-main}"
REPO_SUBDIR="${SSR_ADMIN_REPO_SUBDIR:-ssr-admin-panel}"
PYTHON3_BIN="/usr/bin/python3"
SYSTEM_PYTHON3_BIN="/usr/bin/python3"
APT_UPDATED=0
SYNC_REVISION=""
export DEBIAN_FRONTEND="${DEBIAN_FRONTEND:-noninteractive}"

if [ -f /etc/debian_version ] || [ -f /etc/lsb-release ]; then
    SYS="debian"
elif [ -f /etc/redhat-release ] || [ -f /etc/centos-release ]; then
    SYS="centos"
else
    SYS="debian"
fi

install_packages() {
    if [ "$SYS" = "centos" ]; then
        if command -v dnf &>/dev/null; then
            dnf install -y -q "$@" 2>/dev/null
        else
            yum install -y -q "$@" 2>/dev/null
        fi
        return
    fi

    apt-get install -y -qq "$@" 2>/dev/null && return

    # 首次失败 → 更新索引后重试（仅一次）
    if [ "$APT_UPDATED" -eq 0 ]; then
        echo -e "${YELLOW}刷新 apt 软件源索引...${NC}"
        apt-get update -qq
        APT_UPDATED=1
        apt-get install -y -qq "$@"
    fi
}

ensure_command() {
    local binary=$1
    shift
    if command -v "$binary" &> /dev/null; then
        return
    fi
    echo -e "${YELLOW}${binary} 未安装，正在安装...${NC}"
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

ensure_panel_venv() {
    SYSTEM_PYTHON3_BIN=$(command -v python3 2>/dev/null || echo "/usr/bin/python3")

    if [ ! -x "${VENV_DIR}/bin/python" ]; then
        echo -e "${YELLOW}创建面板 Python 虚拟环境...${NC}"
        "${SYSTEM_PYTHON3_BIN}" -m venv "${VENV_DIR}" 2>/dev/null || {
            install_packages python3-venv python3-pip 2>/dev/null || true
            "${SYSTEM_PYTHON3_BIN}" -m venv "${VENV_DIR}"
        }
    fi

    PYTHON3_BIN="${VENV_DIR}/bin/python"
    "${PYTHON3_BIN}" -m ensurepip --upgrade >/dev/null 2>&1 || true
    "${PYTHON3_BIN}" -m pip install --upgrade pip setuptools wheel --no-input --disable-pip-version-check -q 2>/dev/null || true
}

ensure_basic_runtime() {
    PYTHON3_BIN=$(command -v python3 2>/dev/null || echo "/usr/bin/python3")

    # 批量安装缺失的系统依赖
    local MISSING=""
    local _ss_pkg="iproute2"
    [ "$SYS" = "centos" ] && _ss_pkg="iproute"
    for cmd_pkg in "systemctl:systemd" "curl:curl" "ss:${_ss_pkg}" "git:git" "python3:python3"; do
        local cmd="${cmd_pkg%%:*}" pkg="${cmd_pkg##*:}"
        command -v "$cmd" &>/dev/null || MISSING="$MISSING $pkg"
    done
    if [ -n "$MISSING" ]; then
        echo -e "${YELLOW}安装系统依赖:${MISSING}${NC}"
        install_packages $MISSING || {
            echo -e "${RED}系统依赖安装失败${NC}"
            exit 1
        }
        PYTHON3_BIN=$(command -v python3 2>/dev/null || echo "/usr/bin/python3")
    fi

    # 创建 python → python3 兼容入口（ssrmu.sh 等脚本依赖 python 命令）
    if ! command -v python &> /dev/null; then
        echo -e "${YELLOW}未找到 python 命令，正在创建兼容入口...${NC}"
        install_packages python-is-python3 2>/dev/null || true
        if ! command -v python &> /dev/null && command -v python3 &> /dev/null; then
            ln -sf "$(command -v python3)" /usr/local/bin/python 2>/dev/null || true
        fi
    fi

    ensure_panel_venv
}

install_flask_runtime() {
    if "$PYTHON3_BIN" -c "import flask; import waitress" &>/dev/null; then
        echo -e "${GREEN}✓ Flask 运行时已就绪${NC}"
        return
    fi

    local req_file="$INSTALL_DIR/requirements.txt"
    echo -e "${GREEN}安装 Python 依赖...${NC}"

    if "$PYTHON3_BIN" -m pip --version &>/dev/null && [ -f "${req_file}" ]; then
        install_python_runtime_with_pip "${req_file}" 2>/dev/null || true
    fi

    # pip 失败或不可用时，回退到系统包
    if ! "$PYTHON3_BIN" -c "import flask" &>/dev/null; then
        echo -e "${YELLOW}pip 安装 Flask 失败，尝试系统包...${NC}"
        install_packages python3-flask || \
        install_single_python_package Flask
    fi

    if ! "$PYTHON3_BIN" -c "import flask_limiter" &>/dev/null; then
        echo -e "${YELLOW}pip 安装 Flask-Limiter 失败，尝试系统包...${NC}"
        install_single_python_package flask-limiter 2>/dev/null || \
        install_packages python3-flask-limiter 2>/dev/null || true
    fi

    if ! "$PYTHON3_BIN" -c "import waitress" &>/dev/null; then
        echo -e "${YELLOW}pip 安装 Waitress 失败，尝试单独安装...${NC}"
        install_single_python_package waitress 2>/dev/null || \
        install_packages python3-waitress 2>/dev/null || true
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

    echo -e "${GREEN}检测到 SSR 目录，正在修复 Python 3.10+ 兼容性...${NC}"
    "$PYTHON3_BIN" "$INSTALL_DIR/scripts/patch_ssr_python_compat.py" "$SSR_DIR"
}

install_device_stats_service() {
    if [ ! -d "$SSR_DIR" ] || [ ! -f "$MUDB_FILE" ]; then
        echo -e "${YELLOW}未检测到 SSR 数据文件，跳过设备统计服务${NC}"
        return 0
    fi

    echo -e "${GREEN}配置设备统计服务...${NC}"
    ensure_command "ss" "iproute2"
    mkdir -p "$(dirname "$DEVICE_STATS_FILE")"
    chmod +x "$INSTALL_DIR/scripts/collect_device_stats.py" 2>/dev/null || true

    cat > /etc/systemd/system/ssr-device-stats.service <<SERVICE
[Unit]
Description=SSR Device Stats Collector
After=network.target

[Service]
Type=simple
User=root
ExecStart=${PYTHON3_BIN} ${INSTALL_DIR}/scripts/collect_device_stats.py --mudb ${MUDB_FILE} --output ${DEVICE_STATS_FILE} --interval ${DEVICE_STATS_INTERVAL} --window ${DEVICE_STATS_WINDOW} --watch
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
    find "$target_dir" -mindepth 1 -maxdepth 1 ! -name config.py ! -name backups ! -name venv -exec rm -rf {} +
    cp -R "$source_dir"/. "$target_dir"/
    SYNC_REVISION=$(git -C "$tmp_clone_dir" rev-parse --short HEAD 2>/dev/null || echo "")
    rm -rf "$tmp_clone_dir"
}

# ========== 交互式配置 ==========
echo
echo -e "${CYAN}[ 配置管理员账号 ]${NC}"
echo -e "${YELLOW}----------------------------------------${NC}"

# 支持环境变量非交互式配置
ADMIN_USER="${SSR_ADMIN_USER:-}"
ADMIN_PASS="${SSR_ADMIN_PASS:-}"

# 安全读取函数
safe_read() {
    local var_name="$1"
    local prompt="$2"
    local is_password="$3"
    local input=""
    if [ -n "${!var_name:-}" ]; then return 0; fi
    if [ -t 0 ]; then
        if [ "$is_password" = "yes" ]; then read -r -s -p "$prompt" input; echo; else read -r -p "$prompt" input; fi
    elif [ -e /dev/tty ]; then
        if [ "$is_password" = "yes" ]; then read -s -p "$prompt" input < /dev/tty; echo; else read -r -p "$prompt" input < /dev/tty; fi
    else
        return 1
    fi
    printf -v "$var_name" '%s' "$input"
}

# 获取用户名
if [ -z "$ADMIN_USER" ]; then
    if ! safe_read ADMIN_USER "请输入管理员用户名: " "no" || [ -z "$ADMIN_USER" ]; then
        echo -e "${RED}用户名不能为空（非交互模式请设置 SSR_ADMIN_USER）${NC}"
        exit 1
    fi
fi

# 获取密码
if [ -z "$ADMIN_PASS" ]; then
    if ! safe_read ADMIN_PASS "请输入管理员密码: " "yes" || [ -z "$ADMIN_PASS" ]; then
        echo -e "${RED}密码不能为空（非交互模式请设置 SSR_ADMIN_PASS）${NC}"
        exit 1
    fi
    # 确认密码（非交互模式跳过确认）
    if [ -t 0 ] || [ -e /dev/tty ]; then
        local_confirm=""
        read -s -p "请再次输入密码确认: " local_confirm
        echo
        if [ "$ADMIN_PASS" != "$local_confirm" ]; then
            echo -e "${RED}两次密码不一致！${NC}"
            exit 1
        fi
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

if [ -n "${SSR_ADMIN_USER:-}" ]; then
    ENABLE_SHARE_TEMPLATE="n"
    echo -e "${YELLOW}检测到非交互模式，已跳过分享配置${NC}"
else
    if [ -t 0 ]; then read -p "是否启用账号分享模板？[y/N]: " ENABLE_SHARE_TEMPLATE
    elif [ -e /dev/tty ]; then read -p "是否启用账号分享模板？[y/N]: " ENABLE_SHARE_TEMPLATE < /dev/tty
    else ENABLE_SHARE_TEMPLATE="n"; fi
fi

ENABLE_SHARE_TEMPLATE=$(printf '%s' "$ENABLE_SHARE_TEMPLATE" | tr '[:upper:]' '[:lower:]')

if [ "$ENABLE_SHARE_TEMPLATE" = "y" ] || [ "$ENABLE_SHARE_TEMPLATE" = "yes" ]; then
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

echo -e "${GREEN}✓ 配置完成${NC}"
echo

# ========== 开始安装 ==========
# 检查mudb.json
if [ ! -f "$MUDB_FILE" ]; then
    echo -e "${YELLOW}警告: 未找到 mudb.json ($MUDB_FILE)${NC}"
    echo -e "${YELLOW}请确保已安装 ShadowsocksR，或安装后修改配置文件中的路径${NC}"
    echo
fi

# 下载项目文件
echo -e "${GREEN}[1/6] 下载项目文件...${NC}" 
sync_project_files "$INSTALL_DIR"

chmod +x "$INSTALL_DIR/update.sh" "$INSTALL_DIR/install.sh" "$INSTALL_DIR/install-all.sh" "$INSTALL_DIR/uninstall.sh" "$INSTALL_DIR/scripts/collect_device_stats.py" "$INSTALL_DIR/scripts/optimize_server.sh" 2>/dev/null || true
APP_VERSION=$(cat "$INSTALL_DIR/VERSION" 2>/dev/null | tr -d '\r\n')
APP_REVISION="${SYNC_REVISION:-$(git -C "$INSTALL_DIR" rev-parse --short HEAD 2>/dev/null || echo "")}"
PANEL_BUILD_INFO_FILE="$INSTALL_DIR/.panel-build.json"
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
apply_ssr_python_compatibility_fix

echo -e "${GREEN}✓ 项目文件下载完成${NC}"
echo

# 安装依赖
echo -e "${GREEN}[2/6] 安装系统依赖...${NC}"
ensure_basic_runtime

echo -e "${GREEN}[3/6] 安装Python依赖...${NC}"
install_flask_runtime

echo
# 创建配置文件
echo -e "${GREEN}[4/6] 生成配置文件...${NC}" 
if [ -f "$INSTALL_DIR/config.py" ]; then
    echo -e "${YELLOW}检测到现有配置文件，已保留: $INSTALL_DIR/config.py${NC}"
else
SECRET_KEY=$("$PYTHON3_BIN" -c "import secrets; print(secrets.token_hex(32))")
INSTALL_DIR="$INSTALL_DIR" ADMIN_USER="$ADMIN_USER" ADMIN_PASS="$ADMIN_PASS" SECRET_KEY="$SECRET_KEY" MUDB_FILE="$MUDB_FILE" DEVICE_STATS_FILE="$DEVICE_STATS_FILE" SHARE_HOST="$SHARE_HOST" SHARE_PORT="$SHARE_PORT" SHARE_PASSWORD="$SHARE_PASSWORD" SHARE_REMARKS="$SHARE_REMARKS" SHARE_PROTOCOL="$SHARE_PROTOCOL" SHARE_METHOD="$SHARE_METHOD" SHARE_OBFS="$SHARE_OBFS" SHARE_OBFS_PARAM="$SHARE_OBFS_PARAM" "$PYTHON3_BIN" << 'PY'
import os
from pathlib import Path


def to_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


config_path = Path(os.environ["INSTALL_DIR"]) / "config.py"
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
    f.write("# 由安装脚本自动生成\n\n")
    for key, value in values.items():
        f.write(f"{key} = {value!r}\n")
PY

echo -e "${GREEN}✓ 配置文件已生成: $INSTALL_DIR/config.py${NC}"
fi

# 创建systemd服务
echo -e "${GREEN}[5/6] 配置系统服务...${NC}" 
install_device_stats_service

cat > /etc/systemd/system/ssr-admin.service <<SERVICE
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

# 检查服务状态
sleep 2
if systemctl is-active --quiet ssr-admin; then
    SERVICE_STATUS="${GREEN}运行中${NC}"
    echo -e "${GREEN}✓ ssr-admin 服务运行中${NC}"
else
    SERVICE_STATUS="${RED}启动失败${NC}"
    echo -e "${RED}ssr-admin 服务启动失败${NC}"
    echo -e "${CYAN}诊断命令:${NC} journalctl -u ssr-admin -n 50 --no-pager"
    journalctl -u ssr-admin -n 50 --no-pager || true
    exit 1
fi

# ── SSR 服务器性能优化 ──
echo -e "${GREEN}[6/6] SSR 服务器性能优化...${NC}"
if [ -d "$SSR_DIR" ]; then
    bash "$INSTALL_DIR/scripts/optimize_server.sh"
else
    echo -e "${YELLOW}未检测到 SSR，跳过服务器优化（仅安装面板时无需优化）${NC}"
fi

APP_VERSION=$(cat "$INSTALL_DIR/VERSION" 2>/dev/null || echo "unknown")

echo
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}         安装完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo
echo -e "项目目录: ${CYAN}$INSTALL_DIR${NC}"
echo -e "配置文件: ${CYAN}$INSTALL_DIR/config.py${NC}"
echo -e "当前版本: ${CYAN}$APP_VERSION${NC}"
echo -e "服务状态: $SERVICE_STATUS"
echo
echo -e "访问地址: ${YELLOW}http://your-server-ip:5000${NC}"
echo -e "管理员账号: ${YELLOW}${ADMIN_USER}${NC}"
echo
echo -e "${CYAN}提示: 如需修改账号密码，编辑 config.py 后执行:${NC}"
echo -e "${CYAN}  systemctl restart ssr-admin${NC}"
echo -e "${CYAN}更新命令:${NC}"
echo -e "${CYAN}  bash /opt/ssr-admin-panel/update.sh${NC}"
echo -e "${CYAN}卸载命令:${NC}"
echo -e "${CYAN}  bash /opt/ssr-admin-panel/uninstall.sh --yes${NC}"
echo
