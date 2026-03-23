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
apt-get update -qq 2>/dev/null || yum update -q 2>/dev/null
apt-get install -y python3-pip git -qq 2>/dev/null || yum install -y python3-pip git -q 2>/dev/null

# 安装Python依赖
echo -e "${GREEN}[2/6] 安装Python依赖...${NC}"
pip3 install flask gunicorn -q

# 创建目录
echo -e "${GREEN}[3/6] 创建项目目录...${NC}"
mkdir -p $INSTALL_DIR/templates

# 下载项目文件
echo -e "${GREEN}[4/6] 下载项目文件...${NC}"
if [ -d "$INSTALL_DIR/.git" ]; then
    cd $INSTALL_DIR
    git pull -q
else
    git clone https://github.com/Elegying/ssr-admin-panel.git $INSTALL_DIR -q
fi

# 创建配置文件
echo -e "${GREEN}[5/6] 生成配置文件...${NC}"
cat > $INSTALL_DIR/config.py << CONFIG
# SSR Admin Panel 配置文件
# 由安装脚本自动生成

ADMIN_USER = '${ADMIN_USER}'
ADMIN_PASS = '${ADMIN_PASS}'
SECRET_KEY = '$(head -c 32 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 32)'
MUDB_FILE = '${MUDB_FILE}'
CONFIG

echo -e "${GREEN}✓ 配置文件已生成: $INSTALL_DIR/config.py${NC}"

# 创建systemd服务
echo -e "${GREEN}[6/6] 配置系统服务...${NC}"
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
