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

# ========== 第零步：环境检查与依赖安装 ==========
echo -e "${CYAN}[ 0/5 ] 环境检查与依赖安装...${NC}"
echo -e "${YELLOW}----------------------------------------${NC}"

# 定义需要的工具列表
REQUIRED_TOOLS="wget curl git python python3 pip pip3 unzip vim cron"

check_and_install() {
    local tool=$1
    local pkg=$2
    
    if ! command -v $tool &> /dev/null; then
        echo -e "${YELLOW}$tool 未安装，正在安装...${NC}"
        if [ "$SYS" = "centos" ]; then
            yum install -y $pkg -q 2>/dev/null || echo "安装 $pkg 失败"
        else
            apt-get install -y $pkg -qq 2>/dev/null || echo "安装 $pkg 失败"
        fi
    else
        echo -e "${GREEN}✓ $tool 已安装${NC}"
    fi
}

install_compatible_python() {
    echo -e "${GREEN}检查Python环境...${NC}"

    if ! command -v python3 &> /dev/null; then
        echo -e "${YELLOW}Python3 未安装，正在安装...${NC}"
        if [ "$SYS" = "centos" ]; then
            yum install -y python3 python3-pip -q 2>/dev/null || {
                echo -e "${RED}Python3 安装失败，请手动安装后重试${NC}"
                exit 1
            }
        else
            apt-get install -y python3 python3-pip -qq 2>/dev/null || {
                echo -e "${RED}Python3 安装失败，请手动安装后重试${NC}"
                exit 1
            }
        fi
    fi

    if ! command -v pip3 &> /dev/null; then
        echo -e "${YELLOW}pip3 未安装，正在安装...${NC}"
        if [ "$SYS" = "centos" ]; then
            yum install -y python3-pip -q 2>/dev/null || true
        else
            apt-get install -y python3-pip -qq 2>/dev/null || true
        fi
    fi

    if ! command -v python &> /dev/null; then
        echo -e "${YELLOW}未找到 python 命令，正在创建兼容入口...${NC}"
        if [ "$SYS" = "debian" ] || [ "$SYS" = "ubuntu" ]; then
            apt-get install -y python-is-python3 -qq 2>/dev/null || true
        fi

        if ! command -v python &> /dev/null; then
            local python3_path
            python3_path=$(command -v python3 2>/dev/null || true)
            if [ -n "$python3_path" ]; then
                ln -sf "$python3_path" /usr/local/bin/python
            fi
        fi
    fi

    if ! command -v pip &> /dev/null; then
        local pip3_path
        pip3_path=$(command -v pip3 2>/dev/null || true)
        if [ -n "$pip3_path" ]; then
            ln -sf "$pip3_path" /usr/local/bin/pip
        fi
    fi

    if ! command -v python &> /dev/null; then
        echo -e "${RED}兼容 python 命令准备失败，请手动检查 Python 环境${NC}"
        exit 1
    fi
}

# 更新包列表
echo -e "${GREEN}更新软件源...${NC}"
if [ "$SYS" = "centos" ]; then
    yum update -y -q 2>/dev/null
else
    apt-get update -qq 2>/dev/null
fi

# 检查并安装必要工具
echo -e "${GREEN}检查并安装必要工具...${NC}"
check_and_install "wget" "wget"
check_and_install "curl" "curl"
check_and_install "git" "git"
check_and_install "unzip" "unzip"
check_and_install "vim" "vim"
check_and_install "cron" "cron"

install_compatible_python

# 安装Python依赖
echo -e "${GREEN}安装Python依赖...${NC}"
python3 -m pip install cymysql -q 2>/dev/null || pip install cymysql -q 2>/dev/null || echo "cymysql安装跳过"

# 配置虚拟内存
echo -e "${GREEN}配置虚拟内存 (2GB)...${NC}"
SWAP_SIZE=$(free -m | grep Swap | awk '{print $2}')
if [ "$SWAP_SIZE" -lt 2048 ]; then
    if [ -f /swapfile ]; then
        swapoff /swapfile 2>/dev/null
        rm -f /swapfile
    fi
    
    dd if=/dev/zero of=/swapfile bs=1M count=2048 status=progress 2>/dev/null
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    
    if ! grep -q '/swapfile' /etc/fstab; then
        echo '/swapfile none swap sw 0 0' >> /etc/fstab
    fi
    
    echo -e "${GREEN}✓ 虚拟内存已设置为 2GB${NC}"
else
    echo -e "${GREEN}✓ 虚拟内存已足够 (${SWAP_SIZE}MB)${NC}"
fi

# 显示环境状态
echo
echo -e "${CYAN}环境状态:${NC}"
echo -e "  Python:  $(python --version 2>&1 || echo '未安装')"
echo -e "  Python3: $(python3 --version 2>&1 || echo '未安装')"
echo -e "  pip:     $(pip --version 2>&1 | cut -d' ' -f1-2 || echo '未安装')"
echo -e "  pip3:    $(pip3 --version 2>&1 | cut -d' ' -f1-2 || echo '未安装')"
echo -e "  git:     $(git --version 2>&1 | cut -d' ' -f3)"
echo -e "  wget:    $(wget --version 2>&1 | head -1 | cut -d' ' -f3)"
echo

echo -e "${GREEN}✓ 环境准备完成${NC}"
echo

# ========== 第一步：下载项目文件 ==========
echo -e "${CYAN}[ 1/5 ] 下载项目文件...${NC}"

if [ -d "$PANEL_DIR" ]; then
    cd $PANEL_DIR
    git pull -q 2>/dev/null || true
else
    git clone https://github.com/Elegying/ssr-admin-panel.git $PANEL_DIR -q
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

echo -e "${GREEN}安装 Python 依赖...${NC}"
pip3 install flask gunicorn -q 2>/dev/null

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
ExecStart=/usr/bin/python3 /opt/ssr-admin-panel/app.py
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
