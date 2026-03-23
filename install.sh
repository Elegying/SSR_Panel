#!/bin/bash

# SSR Admin Panel 一键安装脚本
# Author: Elegying
# GitHub: https://github.com/Elegying/ssr-admin-panel

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

# 检查mudb.json
if [ ! -f "$MUDB_FILE" ]; then
    echo -e "${YELLOW}警告: 未找到 mudb.json，请确保已安装SSR${NC}"
    echo -e "${YELLOW}如果SSR安装在其他位置，安装后请修改app.py中的MUDB_FILE路径${NC}"
fi

# 安装依赖
echo -e "${GREEN}[1/5] 安装系统依赖...${NC}"
apt-get update -qq
apt-get install -y python3-pip git -qq 2>/dev/null || yum install -y python3-pip git -q 2>/dev/null

# 安装Python依赖
echo -e "${GREEN}[2/5] 安装Python依赖...${NC}"
pip3 install flask gunicorn -q

# 创建目录
echo -e "${GREEN}[3/5] 创建项目目录...${NC}"
mkdir -p $INSTALL_DIR/templates

# 下载项目文件
echo -e "${GREEN}[4/5] 下载项目文件...${NC}"
if [ -d "$INSTALL_DIR/.git" ]; then
    cd $INSTALL_DIR
    git pull -q
else
    git clone https://github.com/Elegying/ssr-admin-panel.git $INSTALL_DIR -q
fi

# 创建systemd服务
echo -e "${GREEN}[5/5] 配置系统服务...${NC}"
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

echo
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}         安装完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo
echo -e "访问地址: ${YELLOW}http://your-server-ip:5000${NC}"
echo -e "默认账号: ${YELLOW}admin${NC}"
echo -e "默认密码: ${YELLOW}admin123${NC}"
echo
echo -e "${YELLOW}请及时修改账号密码！编辑: /opt/ssr-admin-panel/app.py${NC}"
echo
