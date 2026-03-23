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
echo

# 检查root权限
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}请使用root权限运行此脚本${NC}"
    exit 1
fi

# 安装目录
SSR_DIR="/usr/local/shadowsocksr"
PANEL_DIR="/opt/ssr-admin-panel"
MUDB_FILE="${SSR_DIR}/mudb.json"

# ========== 第一步：配置信息 ==========
echo -e "${CYAN}[ 第一步：配置信息 ]${NC}"
echo -e "${YELLOW}----------------------------------------${NC}"

# 读取管理员用户名
while true; do
    read -p "请输入管理面板用户名: " ADMIN_USER
    if [ -z "$ADMIN_USER" ]; then
        echo -e "${RED}用户名不能为空！${NC}"
    else
        break
    fi
done

# 读取管理员密码
while true; do
    read -s -p "请输入管理面板密码: " ADMIN_PASS
    echo
    if [ -z "$ADMIN_PASS" ]; then
        echo -e "${RED}密码不能为空！${NC}"
        continue
    fi
    read -s -p "请再次输入密码确认: " ADMIN_PASS_CONFIRM
    echo
    if [ "$ADMIN_PASS" != "$ADMIN_PASS_CONFIRM" ]; then
        echo -e "${RED}两次密码不一致！${NC}"
    else
        break
    fi
done

# 读取SSR端口
read -p "请输入SSR服务端口 (默认 443): " SSR_PORT
SSR_PORT=${SSR_PORT:-443}

# 读取SSR密码
read -p "请输入SSR连接密码 (默认随机生成): " SSR_PASS
if [ -z "$SSR_PASS" ]; then
    SSR_PASS=$(head -c 16 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 12)
fi

echo
echo -e "${GREEN}✓ 配置完成${NC}"
echo

# ========== 第二步：安装SSR ==========
echo -e "${CYAN}[ 第二步：安装 ShadowsocksR ]${NC}"
echo -e "${YELLOW}----------------------------------------${NC}"

if [ -d "$SSR_DIR" ]; then
    echo -e "${GREEN}检测到已安装SSR，跳过安装...${NC}"
else
    echo -e "${GREEN}正在下载 SSR 安装脚本...${NC}"
    
    # 下载并运行SSR安装脚本（自动应答）
    wget -N --no-check-certificate https://raw.githubusercontent.com/ToyoDAdoubiBackup/doubi/master/ssrmu.sh -O /tmp/ssrmu.sh
    chmod +x /tmp/ssrmu.sh
    
    echo -e "${GREEN}开始安装 SSR (请按提示操作)...${NC}"
    echo -e "${YELLOW}提示: 选择 1 安装 SSR${NC}"
    echo
    
    # 手动运行SSR脚本
    bash /tmp/ssrmu.sh
fi

# ========== 第三步：安装管理面板 ==========
echo
echo -e "${CYAN}[ 第三步：安装管理面板 ]${NC}"
echo -e "${YELLOW}----------------------------------------${NC}"

# 安装系统依赖
echo -e "${GREEN}安装系统依赖...${NC}"
apt-get update -qq 2>/dev/null || yum update -q 2>/dev/null
apt-get install -y python3-pip git -qq 2>/dev/null || yum install -y python3-pip git -q 2>/dev/null

# 安装Python依赖
echo -e "${GREEN}安装 Python 依赖...${NC}"
pip3 install flask gunicorn -q

# 创建目录
mkdir -p $PANEL_DIR/templates

# 下载项目
echo -e "${GREEN}下载管理面板...${NC}"
if [ -d "$PANEL_DIR/.git" ]; then
    cd $PANEL_DIR
    git pull -q
else
    git clone https://github.com/Elegying/ssr-admin-panel.git $PANEL_DIR -q
fi

# 生成配置文件
echo -e "${GREEN}生成配置文件...${NC}"
SECRET_KEY=$(head -c 32 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 32)

cat > $PANEL_DIR/config.py << CONFIG
# SSR Admin Panel 配置文件
ADMIN_USER = '${ADMIN_USER}'
ADMIN_PASS = '${ADMIN_PASS}'
SECRET_KEY = '${SECRET_KEY}'
MUDB_FILE = '${MUDB_FILE}'
CONFIG

# 创建systemd服务
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
sleep 2
clear
echo
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}           安装完成！${NC}"
echo -e "${GREEN}============================================${NC}"
echo
echo -e "${CYAN}管理面板信息:${NC}"
echo -e "  访问地址: ${YELLOW}http://your-server-ip:5000${NC}"
echo -e "  用户名:   ${YELLOW}${ADMIN_USER}${NC}"
echo -e "  密码:     ${YELLOW}${ADMIN_PASS}${NC}"
echo
echo -e "${CYAN}SSR服务信息:${NC}"
echo -e "  端口:     ${YELLOW}${SSR_PORT}${NC}"
echo -e "  密码:     ${YELLOW}${SSR_PASS}${NC}"
echo
echo -e "${CYAN}常用命令:${NC}"
echo -e "  查看SSR状态:  ${YELLOW}bash /usr/local/shadowsocksr/shadowsocks/logrun.sh${NC}"
echo -e "  添加用户:     ${YELLOW}bash /usr/local/shadowsocksr/shadowsocks/mujson_mgr.sh${NC}"
echo -e "  重启面板:     ${YELLOW}systemctl restart ssr-admin${NC}"
echo
echo -e "${GREEN}感谢使用！${NC}"
echo
