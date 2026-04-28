#!/bin/bash

# SSR Admin Panel 一键安装脚本
# Author: Elegying
# GitHub: https://github.com/Elegying/ssr-admin-panel

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
MUDB_FILE="/usr/local/shadowsocksr/mudb.json"
SSR_DIR="/usr/local/shadowsocksr"
DEVICE_STATS_FILE="${SSR_DEVICE_STATS_FILE:-/var/lib/ssr-admin-panel/device-stats.json}"
DEVICE_STATS_INTERVAL="${SSR_DEVICE_STATS_INTERVAL:-15}"
DEVICE_STATS_WINDOW="${SSR_DEVICE_STATS_WINDOW:-900}"
REPO_URL="${SSR_ADMIN_REPO_URL:-https://github.com/Elegying/ssr-admin-panel.git}"
REPO_REF="${SSR_ADMIN_UPDATE_REF:-main}"
PYTHON3_BIN="/usr/bin/python3"
APT_UPDATED=0
export DEBIAN_FRONTEND="${DEBIAN_FRONTEND:-noninteractive}"

if [ -f /etc/debian_version ]; then
    SYS="debian"
elif [ -f /etc/redhat-release ]; then
    SYS="centos"
else
    SYS="debian"
fi

install_packages() {
    if [ "$SYS" = "centos" ]; then
        yum install -y "$@" -q 2>/dev/null
        return
    fi

    apt-get install -y "$@" -qq 2>/dev/null || {
        if [ "$APT_UPDATED" -eq 0 ]; then
            echo -e "${YELLOW}软件源索引不可用，正在刷新 apt 索引...${NC}"
            apt-get update -qq
            APT_UPDATED=1
        fi
        apt-get install -y "$@" -qq
    }
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

ensure_basic_runtime() {
    PYTHON3_BIN=$(command -v python3 2>/dev/null || echo "/usr/bin/python3")

    ensure_command "systemctl" "systemd"
    ensure_command "curl" "curl"
    ensure_command "ss" "iproute2"
    ensure_command "git" "git"

    if ! command -v python3 &> /dev/null; then
        echo -e "${YELLOW}python3 未安装，正在安装...${NC}"
        install_packages python3
        PYTHON3_BIN=$(command -v python3 2>/dev/null || echo "/usr/bin/python3")
    fi

    if ! "$PYTHON3_BIN" -m pip --version &>/dev/null; then
        echo -e "${YELLOW}未检测到可用的 pip 模块，尝试启用 ensurepip...${NC}"
        "$PYTHON3_BIN" -m ensurepip --upgrade >/dev/null 2>&1 || true
    fi

    if ! "$PYTHON3_BIN" -m pip --version &>/dev/null; then
        echo -e "${YELLOW}尝试安装 python3-pip...${NC}"
        install_packages python3-pip || true
    fi

    if ! "$PYTHON3_BIN" -m pip --version &>/dev/null; then
        echo -e "${YELLOW}当前环境缺少 pip，将优先依赖系统包安装 Flask${NC}"
    fi
}

install_flask_runtime() {
    if "$PYTHON3_BIN" -c "import flask; import flask_limiter" &>/dev/null; then
        echo -e "${GREEN}✓ Flask 运行时已就绪${NC}"
        return
    fi

    echo -e "${GREEN}安装 Flask 运行时...${NC}"
    install_packages python3-flask || \
    "$PYTHON3_BIN" -m pip install --no-input --disable-pip-version-check Flask -q

    if ! "$PYTHON3_BIN" - <<'PY' &>/dev/null
import flask
PY
    then
        echo -e "${RED}Flask 安装失败，请手动安装后重试${NC}"
        exit 1
    fi

    # 安装 flask-limiter
    echo -e "${GREEN}安装 Flask-Limiter 速率限制模块...${NC}"
    if ! "$PYTHON3_BIN" -c "import flask_limiter" &>/dev/null; then
        "$PYTHON3_BIN" -m pip install --no-input --disable-pip-version-check flask-limiter -q || true
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
    systemctl restart ssr-device-stats
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
    local input
    local _check_val=""
    eval "_check_val=\"\${${var_name}:-}\""
    if [ -n "$_check_val" ]; then return 0; fi
    if [ -t 0 ]; then
        if [ "$is_password" = "yes" ]; then read -s -p "$prompt" input; echo; else read -r -p "$prompt" input; fi
    elif [ -e /dev/tty ]; then
        if [ "$is_password" = "yes" ]; then read -s -p "$prompt" input < /dev/tty; echo; else read -r -p "$prompt" input < /dev/tty; fi
    else
        if ! read -r input; then return 1; fi
    fi
    eval "$var_name='$input'"
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

# 安装依赖
echo -e "${GREEN}[1/6] 安装系统依赖...${NC}"
ensure_basic_runtime

# 安装Python依赖
echo -e "${GREEN}[2/6] 安装Python依赖...${NC}"
install_flask_runtime

# 创建目录
echo -e "${GREEN}[3/6] 创建项目目录...${NC}"
mkdir -p $INSTALL_DIR/templates

# 下载项目文件
echo -e "${GREEN}[4/6] 下载项目文件...${NC}"
if [ -d "$INSTALL_DIR/.git" ]; then
    cd $INSTALL_DIR
    git pull --ff-only -q origin "$REPO_REF" 2>/dev/null || true
elif [ -d "$INSTALL_DIR" ]; then
    TMP_CLONE_DIR=$(mktemp -d /tmp/ssr-admin-panel.XXXXXX)
    git clone --depth 1 --branch "$REPO_REF" "$REPO_URL" "$TMP_CLONE_DIR" -q
    cp -R "$TMP_CLONE_DIR"/. "$INSTALL_DIR"/
    rm -rf "$TMP_CLONE_DIR"
else
    git clone --depth 1 --branch "$REPO_REF" "$REPO_URL" "$INSTALL_DIR" -q
fi

chmod +x "$INSTALL_DIR/update.sh" "$INSTALL_DIR/install.sh" "$INSTALL_DIR/install-all.sh" "$INSTALL_DIR/scripts/collect_device_stats.py" 2>/dev/null || true
APP_VERSION=$(cat "$INSTALL_DIR/VERSION" 2>/dev/null | tr -d '\r\n')
APP_REVISION=$(git -C "$INSTALL_DIR" rev-parse --short HEAD 2>/dev/null || echo "")
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

# 创建配置文件
echo -e "${GREEN}[5/6] 生成配置文件...${NC}"
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
echo -e "${GREEN}[6/6] 配置系统服务...${NC}"
install_device_stats_service

cat > /etc/systemd/system/ssr-admin.service <<SERVICE
[Unit]
Description=SSR Admin Panel
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/ssr-admin-panel
ExecStart=${PYTHON3_BIN} /opt/ssr-admin-panel/app.py
Restart=always
RestartSec=5

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
else
    SERVICE_STATUS="${RED}启动失败${NC}"
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
echo
