#!/bin/bash

# SSR Admin Panel 一键安装脚本
# Author: Elegying
# GitHub: https://github.com/Elegying/ssr-admin-panel

set -e

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
REPO_URL="${SSR_ADMIN_REPO_URL:-https://github.com/Elegying/ssr-admin-panel.git}"
REPO_REF="${SSR_ADMIN_UPDATE_REF:-main}"
PYTHON3_BIN="/usr/bin/python3"

ensure_basic_runtime() {
    PYTHON3_BIN=$(command -v python3 2>/dev/null || echo "/usr/bin/python3")

    if ! command -v git &> /dev/null; then
        echo -e "${YELLOW}git 未安装，正在安装...${NC}"
        apt-get install -y git -qq 2>/dev/null || yum install -y git -q 2>/dev/null
    fi

    if ! command -v python3 &> /dev/null; then
        echo -e "${YELLOW}python3 未安装，正在安装...${NC}"
        apt-get install -y python3 -qq 2>/dev/null || yum install -y python3 -q 2>/dev/null
        PYTHON3_BIN=$(command -v python3 2>/dev/null || echo "/usr/bin/python3")
    fi

    if ! "$PYTHON3_BIN" -m pip --version &>/dev/null; then
        echo -e "${YELLOW}未检测到可用的 pip 模块，尝试启用 ensurepip...${NC}"
        "$PYTHON3_BIN" -m ensurepip --upgrade >/dev/null 2>&1 || true
    fi

    if ! "$PYTHON3_BIN" -m pip --version &>/dev/null; then
        echo -e "${YELLOW}尝试安装 python3-pip...${NC}"
        apt-get install -y python3-pip -qq 2>/dev/null || yum install -y python3-pip -q 2>/dev/null || true
    fi

    if ! "$PYTHON3_BIN" -m pip --version &>/dev/null; then
        echo -e "${YELLOW}当前环境缺少 pip，将优先依赖系统包安装 Flask${NC}"
    fi
}

install_flask_runtime() {
    if "$PYTHON3_BIN" - <<'PY' &>/dev/null
import flask
PY
    then
        echo -e "${GREEN}✓ Flask 运行时已就绪${NC}"
        return
    fi

    echo -e "${GREEN}安装 Flask 运行时...${NC}"
    apt-get install -y python3-flask -qq 2>/dev/null || \
    yum install -y python3-flask -q 2>/dev/null || \
    "$PYTHON3_BIN" -m pip install --no-input --disable-pip-version-check Flask -q

    if ! "$PYTHON3_BIN" - <<'PY' &>/dev/null
import flask
PY
    then
        echo -e "${RED}Flask 安装失败，请手动安装后重试${NC}"
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

# ========== 交互式配置 ==========
echo
echo -e "${CYAN}[ 配置管理员账号 ]${NC}"
echo -e "${YELLOW}----------------------------------------${NC}"

# 读取用户名
while true; do
    read -p "请输入管理员用户名: " ADMIN_USER
    if [ -z "$ADMIN_USER" ]; then
        echo -e "${RED}用户名不能为空！${NC}"
    else
        break
    fi
done

# 读取密码
while true; do
    read -s -p "请输入管理员密码: " ADMIN_PASS
    echo
    if [ -z "$ADMIN_PASS" ]; then
        echo -e "${RED}密码不能为空！${NC}"
        continue
    fi
    read -s -p "请再次输入密码确认: " ADMIN_PASS_CONFIRM
    echo
    if [ "$ADMIN_PASS" != "$ADMIN_PASS_CONFIRM" ]; then
        echo -e "${RED}两次密码不一致，请重新输入！${NC}"
    else
        break
    fi
done

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
read -p "是否启用账号分享模板？[y/N]: " ENABLE_SHARE_TEMPLATE
ENABLE_SHARE_TEMPLATE=$(printf '%s' "$ENABLE_SHARE_TEMPLATE" | tr '[:upper:]' '[:lower:]')

if [ "$ENABLE_SHARE_TEMPLATE" = "y" ] || [ "$ENABLE_SHARE_TEMPLATE" = "yes" ]; then
    while true; do
        read -p "请输入分享域名/IP: " SHARE_HOST
        if [ -n "$SHARE_HOST" ]; then
            break
        fi
        echo -e "${RED}分享域名/IP 不能为空！${NC}"
    done

    while true; do
        read -p "请输入分享端口 [18899]: " SHARE_PORT_INPUT
        SHARE_PORT=${SHARE_PORT_INPUT:-18899}
        if [ "$SHARE_PORT" -ge 1 ] 2>/dev/null && [ "$SHARE_PORT" -le 65535 ] 2>/dev/null; then
            break
        fi
        echo -e "${RED}分享端口必须是 1-65535 之间的数字！${NC}"
    done

    while true; do
        read -s -p "请输入固定分享密码: " SHARE_PASSWORD
        echo
        if [ -n "$SHARE_PASSWORD" ]; then
            break
        fi
        echo -e "${RED}固定分享密码不能为空！${NC}"
    done

    while true; do
        read -p "请输入固定备注: " SHARE_REMARKS
        if [ -n "$SHARE_REMARKS" ]; then
            break
        fi
        echo -e "${RED}固定备注不能为空！${NC}"
    done
else
    echo -e "${YELLOW}已跳过分享模板配置，分享功能默认关闭${NC}"
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

chmod +x "$INSTALL_DIR/update.sh" "$INSTALL_DIR/install.sh" "$INSTALL_DIR/install-all.sh" 2>/dev/null || true
apply_ssr_python_compatibility_fix

# 创建配置文件
echo -e "${GREEN}[5/6] 生成配置文件...${NC}"
if [ -f "$INSTALL_DIR/config.py" ]; then
    echo -e "${YELLOW}检测到现有配置文件，已保留: $INSTALL_DIR/config.py${NC}"
else
SECRET_KEY=$(head -c 32 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 32)
INSTALL_DIR="$INSTALL_DIR" ADMIN_USER="$ADMIN_USER" ADMIN_PASS="$ADMIN_PASS" SECRET_KEY="$SECRET_KEY" MUDB_FILE="$MUDB_FILE" SHARE_HOST="$SHARE_HOST" SHARE_PORT="$SHARE_PORT" SHARE_PASSWORD="$SHARE_PASSWORD" SHARE_REMARKS="$SHARE_REMARKS" SHARE_PROTOCOL="$SHARE_PROTOCOL" SHARE_METHOD="$SHARE_METHOD" SHARE_OBFS="$SHARE_OBFS" SHARE_OBFS_PARAM="$SHARE_OBFS_PARAM" python3 << 'PY'
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
