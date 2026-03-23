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
REPO_URL="https://github.com/Elegying/ssr-admin-panel.git"
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
    git pull --ff-only -q 2>/dev/null || true
elif [ -d "$INSTALL_DIR" ]; then
    TMP_CLONE_DIR=$(mktemp -d /tmp/ssr-admin-panel.XXXXXX)
    git clone --depth 1 "$REPO_URL" "$TMP_CLONE_DIR" -q
    cp -R "$TMP_CLONE_DIR"/. "$INSTALL_DIR"/
    rm -rf "$TMP_CLONE_DIR"
else
    git clone --depth 1 "$REPO_URL" "$INSTALL_DIR" -q
fi

# 创建配置文件
echo -e "${GREEN}[5/6] 生成配置文件...${NC}"
SECRET_KEY=$(head -c 32 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 32)
INSTALL_DIR="$INSTALL_DIR" ADMIN_USER="$ADMIN_USER" ADMIN_PASS="$ADMIN_PASS" SECRET_KEY="$SECRET_KEY" MUDB_FILE="$MUDB_FILE" python3 << 'PY'
import os
from pathlib import Path

config_path = Path(os.environ["INSTALL_DIR"]) / "config.py"
values = {
    "ADMIN_USER": os.environ["ADMIN_USER"],
    "ADMIN_PASS": os.environ["ADMIN_PASS"],
    "SECRET_KEY": os.environ["SECRET_KEY"],
    "MUDB_FILE": os.environ["MUDB_FILE"],
}

with config_path.open("w", encoding="utf-8") as f:
    f.write("# SSR Admin Panel 配置文件\n")
    f.write("# 由安装脚本自动生成\n\n")
    for key, value in values.items():
        f.write(f"{key} = {value!r}\n")
PY

echo -e "${GREEN}✓ 配置文件已生成: $INSTALL_DIR/config.py${NC}"

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

echo
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}         安装完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo
echo -e "项目目录: ${CYAN}$INSTALL_DIR${NC}"
echo -e "配置文件: ${CYAN}$INSTALL_DIR/config.py${NC}"
echo -e "服务状态: $SERVICE_STATUS"
echo
echo -e "访问地址: ${YELLOW}http://your-server-ip:5000${NC}"
echo -e "管理员账号: ${YELLOW}${ADMIN_USER}${NC}"
echo
echo -e "${CYAN}提示: 如需修改账号密码，编辑 config.py 后执行:${NC}"
echo -e "${CYAN}  systemctl restart ssr-admin${NC}"
echo
