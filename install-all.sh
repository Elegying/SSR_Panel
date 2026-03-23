#!/bin/bash

#=================================================
# SSR + 管理面板 一键部署脚本
# Author: Elegying
# GitHub: https://github.com/Elegying/ssr-admin-panel
#=================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

clear
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
REPO_URL="https://github.com/Elegying/ssr-admin-panel.git"
PYTHON3_BIN="/usr/bin/python3"

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
ensure_minimal_command() {
    local binary=$1
    shift
    local packages="$*"

    if command -v "$binary" &> /dev/null; then
        echo -e "${GREEN}✓ ${binary} 已就绪${NC}"
        return
    fi

    echo -e "${YELLOW}${binary} 未找到，正在安装最小依赖...${NC}"
    if [ "$SYS" = "centos" ]; then
        yum install -y ${packages} -q 2>/dev/null || {
            echo -e "${RED}${binary} 安装失败，请手动安装后重试${NC}"
            exit 1
        }
    else
        apt-get install -y ${packages} -qq 2>/dev/null || {
            echo -e "${RED}${binary} 安装失败，请手动安装后重试${NC}"
            exit 1
        }
    fi
}

prepare_minimal_runtime() {
    echo -e "${GREEN}快速检查最小运行环境...${NC}"
    ensure_minimal_command "git" "git"
    ensure_minimal_command "python3" "python3"

    if ! command -v python &> /dev/null; then
        echo -e "${YELLOW}未找到 python 命令，正在创建兼容入口...${NC}"
        if [ "$SYS" = "debian" ] || [ "$SYS" = "ubuntu" ]; then
            apt-get install -y python-is-python3 -qq 2>/dev/null || true
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
            yum install -y python3-pip -q 2>/dev/null || true
        else
            apt-get install -y python3-pip -qq 2>/dev/null || true
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
    if "$PYTHON3_BIN" - <<'PY' &>/dev/null
import flask
PY
    then
        echo -e "${GREEN}✓ Flask 运行时已就绪${NC}"
        return
    fi

    echo -e "${GREEN}安装 Flask 运行时...${NC}"
    if [ "$SYS" = "debian" ] || [ "$SYS" = "ubuntu" ]; then
        apt-get install -y python3-flask -qq 2>/dev/null || \
        "$PYTHON3_BIN" -m pip install --no-input --disable-pip-version-check Flask -q || true
    else
        "$PYTHON3_BIN" -m pip install --no-input --disable-pip-version-check Flask -q || \
        yum install -y python3-flask -q 2>/dev/null || true
    fi

    if ! "$PYTHON3_BIN" - <<'PY' &>/dev/null
import flask
PY
    then
        echo -e "${RED}Flask 安装失败，请手动安装后重试${NC}"
        exit 1
    fi
}

prepare_minimal_runtime

echo
echo -e "${GREEN}快速模式已启用${NC}"
echo -e "${CYAN}已跳过:${NC} 软件源更新 / 额外工具检测 / cymysql 安装 / 自动 Swap 配置"
echo -e "${CYAN}保留最小依赖:${NC} git / python3 / pip3 / python 兼容入口"
echo

# ========== 第一步：下载项目文件 ==========
echo -e "${CYAN}[ 1/5 ] 下载项目文件...${NC}"

if [ -d "$PANEL_DIR" ]; then
    if [ -d "$PANEL_DIR/.git" ]; then
        cd $PANEL_DIR
        git pull --ff-only -q 2>/dev/null || true
    else
        TMP_CLONE_DIR=$(mktemp -d /tmp/ssr-admin-panel.XXXXXX)
        git clone --depth 1 "$REPO_URL" "$TMP_CLONE_DIR" -q
        cp -R "$TMP_CLONE_DIR"/. "$PANEL_DIR"/
        rm -rf "$TMP_CLONE_DIR"
    fi
else
    git clone --depth 1 "$REPO_URL" "$PANEL_DIR" -q
fi

cd $PANEL_DIR

echo -e "${GREEN}✓ 项目文件下载完成${NC}"
echo

# ========== 第二步：配置信息 ==========
echo -e "${CYAN}[ 2/5 ] 配置信息${NC}"
echo -e "${YELLOW}----------------------------------------${NC}"

if [ -t 0 ]; then
    READ_MODE="normal"
else
    READ_MODE="tty"
fi

read_input() {
    if [ "$READ_MODE" = "tty" ]; then
        read "$@" < /dev/tty
    else
        read "$@"
    fi
}

while true; do
    echo -ne "请输入管理面板用户名: "
    if read_input ADMIN_USER; then
        if [ -n "$ADMIN_USER" ]; then
            break
        fi
    fi
    echo -e "${RED}用户名不能为空！${NC}"
done

while true; do
    echo -ne "请输入管理面板密码: "
    if read_input -s ADMIN_PASS; then
        echo
        if [ -n "$ADMIN_PASS" ]; then
            echo -ne "请再次输入密码确认: "
            if read_input -s ADMIN_PASS_CONFIRM; then
                echo
                if [ "$ADMIN_PASS" = "$ADMIN_PASS_CONFIRM" ]; then
                    break
                else
                    echo -e "${RED}两次密码不一致！${NC}"
                fi
            fi
        fi
    fi
    echo -e "${RED}密码不能为空！${NC}"
done

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

echo

# ========== 第四步：安装管理面板 ==========
echo -e "${CYAN}[ 4/5 ] 安装管理面板${NC}"
echo -e "${YELLOW}----------------------------------------${NC}"

install_flask_runtime

echo -e "${GREEN}生成配置文件...${NC}"
SECRET_KEY=$(head -c 32 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 32)
PANEL_DIR="$PANEL_DIR" ADMIN_USER="$ADMIN_USER" ADMIN_PASS="$ADMIN_PASS" SECRET_KEY="$SECRET_KEY" MUDB_FILE="$MUDB_FILE" python3 << 'PY'
import os
from pathlib import Path

config_path = Path(os.environ["PANEL_DIR"]) / "config.py"
values = {
    "ADMIN_USER": os.environ["ADMIN_USER"],
    "ADMIN_PASS": os.environ["ADMIN_PASS"],
    "SECRET_KEY": os.environ["SECRET_KEY"],
    "MUDB_FILE": os.environ["MUDB_FILE"],
}

with config_path.open("w", encoding="utf-8") as f:
    f.write("# SSR Admin Panel 配置文件\n")
    for key, value in values.items():
        f.write(f"{key} = {value!r}\n")
PY

echo -e "${GREEN}配置系统服务...${NC}"
cat > /etc/systemd/system/ssr-admin.service << 'SERVICE'
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
echo
echo -e "${CYAN}SSR默认用户:${NC}"
echo -e "  用户名:   ${YELLOW}doubi${NC}"
echo -e "  端口:     ${YELLOW}2333${NC}"
echo -e "  密码:     ${YELLOW}doub.io${NC}"
echo
echo -e "${CYAN}常用命令:${NC}"
echo -e "  重启面板:     ${YELLOW}systemctl restart ssr-admin${NC}"
echo -e "  管理SSR:      ${YELLOW}bash /opt/ssr-admin-panel/ssrmu.sh${NC}"
echo
echo -e "${GREEN}感谢使用！${NC}"
echo
