#!/bin/bash

#=================================================
# SSR + 管理面板 一键部署脚本
# Author: Elegying
# GitHub: https://github.com/Elegying/ssr-admin-panel
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
echo -e "${CYAN}  GitHub: https://github.com/Elegying/ssr-admin-panel${NC}"
echo

# 检查root权限
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}请使用root权限运行此脚本${NC}"
    exit 1
fi

# 安装目录
PANEL_DIR="/opt/ssr-admin-panel"
SSR_DIR="/usr/local/shadowsocksr"
MUDB_FILE="${SSR_DIR}/mudb.json"
DEVICE_STATS_FILE="${SSR_DEVICE_STATS_FILE:-/var/lib/ssr-admin-panel/device-stats.json}"
DEVICE_STATS_INTERVAL="${SSR_DEVICE_STATS_INTERVAL:-15}"
DEVICE_STATS_WINDOW="${SSR_DEVICE_STATS_WINDOW:-900}"
REPO_URL="${SSR_ADMIN_REPO_URL:-https://github.com/Elegying/ssr-admin-panel.git}"
REPO_REF="${SSR_ADMIN_UPDATE_REF:-main}"
PYTHON3_BIN="/usr/bin/python3"
APT_UPDATED=0
export DEBIAN_FRONTEND="${DEBIAN_FRONTEND:-noninteractive}"

# 检测系统类型
if [ -f /etc/debian_version ]; then
    SYS="debian"
    PKG_MANAGER="apt-get"
elif [ -f /etc/redhat-release ]; then
    SYS="centos"
    PKG_MANAGER="yum"
else
    SYS="other"
    PKG_MANAGER="apt-get"
fi

echo -e "${CYAN}系统检测: ${YELLOW}${SYS}${NC}"
echo

# ========== 第零步：快速准备 ==========
echo -e "${CYAN}[ 0/5 ] 快速准备（跳过依赖检测）...${NC}"
echo -e "${YELLOW}----------------------------------------${NC}"
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

prepare_minimal_runtime() {
    echo -e "${GREEN}快速检查最小运行环境...${NC}"
    ensure_minimal_command "systemctl" "systemd"
    ensure_minimal_command "curl" "curl"
    ensure_minimal_command "ss" "iproute2"
    ensure_minimal_command "git" "git"
    ensure_minimal_command "python3" "python3"

    if ! command -v python &> /dev/null; then
        echo -e "${YELLOW}未找到 python 命令，正在创建兼容入口...${NC}"
        if [ "$SYS" = "debian" ] || [ "$SYS" = "ubuntu" ]; then
            install_packages python-is-python3 || true
        fi
        if ! command -v python &> /dev/null; then
            ln -sf "$(command -v python3)" /usr/local/bin/python
        fi
    fi

    if ! command -v pip &> /dev/null && command -v pip3 &> /dev/null; then
        ln -sf "$(command -v pip3)" /usr/local/bin/pip
    fi

    PYTHON3_BIN=$(command -v python3 2>/dev/null || echo "/usr/bin/python3")

    if ! "$PYTHON3_BIN" -m pip --version &>/dev/null; then
        echo -e "${YELLOW}未检测到可用的 pip 模块，尝试启用 ensurepip...${NC}"
        "$PYTHON3_BIN" -m ensurepip --upgrade >/dev/null 2>&1 || true
    fi

    if ! "$PYTHON3_BIN" -m pip --version &>/dev/null; then
        echo -e "${YELLOW}尝试安装 python3-pip...${NC}"
        if [ "$SYS" = "centos" ]; then
            install_packages python3-pip || true
        else
            install_packages python3-pip || true
        fi
    fi

    if ! "$PYTHON3_BIN" -m pip --version &>/dev/null; then
        echo -e "${YELLOW}当前环境缺少 pip，将优先依赖系统包安装 Flask${NC}"
    else
        if ! command -v pip3 &> /dev/null; then
            ln -sf "$("$PYTHON3_BIN" -m site --user-base 2>/dev/null)/bin/pip3" /usr/local/bin/pip3 2>/dev/null || true
        fi
        if ! command -v pip &> /dev/null; then
            ln -sf "$(command -v pip3 2>/dev/null || true)" /usr/local/bin/pip 2>/dev/null || true
        fi
    fi
}

install_flask_runtime() {
    if "$PYTHON3_BIN" -c "import flask; import flask_limiter" &>/dev/null; then
        echo -e "${GREEN}✓ Flask 运行时已就绪${NC}"
        return
    fi

    echo -e "${GREEN}安装 Flask 运行时...${NC}"
    if [ "$SYS" = "debian" ] || [ "$SYS" = "ubuntu" ]; then
        install_packages python3-flask || \
        "$PYTHON3_BIN" -m pip install --no-input --disable-pip-version-check Flask -q || true
    else
        "$PYTHON3_BIN" -m pip install --no-input --disable-pip-version-check Flask -q || \
        install_packages python3-flask || true
    fi

    if ! "$PYTHON3_BIN" - <<'PY' &>/dev/null
import flask
PY
    then
        echo -e "${RED}Flask 安装失败，请手动安装后重试${NC}"
        exit 1
    fi

    # 安装 flask-limiter (用于速率限制)
    echo -e "${GREEN}安装 Flask-Limiter 速率限制模块...${NC}"
    if ! "$PYTHON3_BIN" -c "import flask_limiter" &>/dev/null; then
        "$PYTHON3_BIN" -m pip install --no-input --disable-pip-version-check flask-limiter -q || \
        install_packages python3-flask-limiter 2>/dev/null || true
    fi
}

apply_ssr_python_compatibility_fix() {
    if [ ! -d "$SSR_DIR" ]; then
        return 0
    fi

    echo -e "${GREEN}修复 ShadowsocksR 的 Python 3.10+ 兼容性...${NC}"
    "$PYTHON3_BIN" "$PANEL_DIR/scripts/patch_ssr_python_compat.py" "$SSR_DIR"
}

install_device_stats_service() {
    echo -e "${GREEN}配置设备统计服务...${NC}"
    ensure_minimal_command "ss" "iproute2"
    mkdir -p "$(dirname "$DEVICE_STATS_FILE")"
    chmod +x "$PANEL_DIR/scripts/collect_device_stats.py" 2>/dev/null || true

    cat > /etc/systemd/system/ssr-device-stats.service <<SERVICE
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
    systemctl restart ssr-device-stats
}

prepare_minimal_runtime

echo
echo -e "${GREEN}快速模式已启用${NC}"
echo -e "${CYAN}已跳过:${NC} cymysql 安装 / 自动 Swap 配置"
echo -e "${CYAN}保留最小依赖:${NC} systemd / curl / git / iproute2 / python3 / pip3 / python 兼容入口"
echo

# ========== 第一步：下载项目文件 ==========
echo -e "${CYAN}[ 1/5 ] 下载项目文件...${NC}"

if [ -d "$PANEL_DIR" ]; then
    if [ -d "$PANEL_DIR/.git" ]; then
        cd $PANEL_DIR
        git pull --ff-only -q origin "$REPO_REF" 2>/dev/null || true
    else
        TMP_CLONE_DIR=$(mktemp -d /tmp/ssr-admin-panel.XXXXXX)
        git clone --depth 1 --branch "$REPO_REF" "$REPO_URL" "$TMP_CLONE_DIR" -q
        cp -R "$TMP_CLONE_DIR"/. "$PANEL_DIR"/
        rm -rf "$TMP_CLONE_DIR"
    fi
else
    git clone --depth 1 --branch "$REPO_REF" "$REPO_URL" "$PANEL_DIR" -q
fi

cd $PANEL_DIR
chmod +x "$PANEL_DIR/update.sh" "$PANEL_DIR/install.sh" "$PANEL_DIR/install-all.sh" "$PANEL_DIR/scripts/collect_device_stats.py" 2>/dev/null || true
APP_VERSION=$(cat "$PANEL_DIR/VERSION" 2>/dev/null | tr -d '\r\n')
APP_REVISION=$(git -C "$PANEL_DIR" rev-parse --short HEAD 2>/dev/null || echo "")
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
echo -e "${CYAN}[ 2/5 ] 配置信息${NC}"
echo -e "${YELLOW}----------------------------------------${NC}"

# 支持环境变量非交互式配置
ADMIN_USER="${SSR_ADMIN_USER:-}"
ADMIN_PASS="${SSR_ADMIN_PASS:-}"

# 安全读取函数：优先 tty，其次 stdin，失败则报错退出
safe_read() {
    local var_name="$1"
    local prompt="$2"
    local is_password="$3"
    
    # 如果变量已有值（来自环境变量），跳过
    if [ -n "${!var_name}" ]; then
        return 0
    fi

    local input
    if [ -t 0 ]; then
        # 交互式终端
        if [ "$is_password" = "yes" ]; then
            read -s -p "$prompt" input
            echo
        else
            read -r -p "$prompt" input
        fi
    elif [ -e /dev/tty ]; then
        # 有 tty 设备但 stdin 非交互（如管道）
        if [ "$is_password" = "yes" ]; then
            read -s -p "$prompt" input < /dev/tty
            echo
        else
            read -r -p "$prompt" input < /dev/tty
        fi
    else
        # 完全非交互，尝试读取 stdin
        if ! read -r input; then
            return 1 # EOF
        fi
    fi
    
    eval "$var_name='$input'"
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
        # 读取分享端口
        local_port=""
        if [ -t 0 ]; then read -p "请输入分享端口 [18899]: " local_port
        elif [ -e /dev/tty ]; then read -p "请输入分享端口 [18899]: " local_port < /dev/tty
        fi
        SHARE_PORT=${local_port:-18899}
        
        # 读取分享密码
        if [ -t 0 ]; then read -s -p "请输入固定分享密码: " SHARE_PASSWORD; echo
        elif [ -e /dev/tty ]; then read -s -p "请输入固定分享密码: " SHARE_PASSWORD < /dev/tty; echo
        fi
        
        if [ -z "$SHARE_PASSWORD" ]; then
            echo -e "${RED}分享密码不能为空，已关闭分享功能${NC}"
            ENABLE_SHARE_TEMPLATE="n"
        else
            # 读取备注
            if [ -t 0 ]; then read -p "请输入固定备注: " SHARE_REMARKS
            elif [ -e /dev/tty ]; then read -p "请输入固定备注: " SHARE_REMARKS < /dev/tty
            fi
            if [ -z "$SHARE_REMARKS" ]; then
                echo -e "${RED}备注不能为空，已关闭分享功能${NC}"
                ENABLE_SHARE_TEMPLATE="n"
            fi
        fi
    fi
fi

echo
echo -e "${GREEN}✓ 配置完成${NC}"
echo

# ========== 第三步：安装SSR ==========
echo -e "${CYAN}[ 3/5 ] 安装 ShadowsocksR${NC}"
echo -e "${YELLOW}----------------------------------------${NC}"

if [ -d "$SSR_DIR" ]; then
    echo -e "${GREEN}检测到已安装SSR，跳过安装...${NC}"
else
    echo -e "${GREEN}开始自动安装 SSR...${NC}"
    
    chmod +x $PANEL_DIR/ssrmu.sh
    
    # 使用管道输入：先发送1选择安装，然后发送50个空行接受所有默认值
    (echo '1'; for i in $(seq 1 50); do echo ''; done) | bash $PANEL_DIR/ssrmu.sh
    
    if [ -d "$SSR_DIR" ]; then
        echo -e "${GREEN}✓ SSR安装完成${NC}"
    else
        echo -e "${RED}SSR安装可能失败，请检查${NC}"
    fi
fi

apply_ssr_python_compatibility_fix

echo

# ========== 第四步：安装管理面板 ==========
echo -e "${CYAN}[ 4/5 ] 安装管理面板${NC}"
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

echo -e "${GREEN}配置系统服务...${NC}"
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

APP_VERSION=$(cat "$PANEL_DIR/VERSION" 2>/dev/null || echo "unknown")

# ========== 完成 ==========
echo -e "${CYAN}[ 5/5 ] 完成${NC}"
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
echo -e "  密码:     ${YELLOW}${ADMIN_PASS}${NC}"
echo -e "  版本:     ${YELLOW}${APP_VERSION}${NC}"
echo
echo -e "${CYAN}SSR默认用户:${NC}"
echo -e "  用户名:   ${YELLOW}doubi${NC}"
echo -e "  端口:     ${YELLOW}2333${NC}"
echo -e "  密码:     ${YELLOW}doub.io${NC}"
echo
echo -e "${CYAN}常用命令:${NC}"
echo -e "  重启面板:     ${YELLOW}systemctl restart ssr-admin${NC}"
echo -e "  更新面板:     ${YELLOW}bash /opt/ssr-admin-panel/update.sh${NC}"
echo -e "  管理SSR:      ${YELLOW}bash /opt/ssr-admin-panel/ssrmu.sh${NC}"
echo
echo -e "${GREEN}感谢使用！${NC}"
echo
