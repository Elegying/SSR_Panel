#!/bin/bash

#=================================================
# SSR + 管理面板 一键部署脚本
# Author: Elegying
# GitHub: https://github.com/Elegying/ssr-admin-panel
# 包含逗比的SSR脚本 (https://github.com/ToyoDAdoubiBackup/doubi)
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

# ========== 第一步：下载项目文件 ==========
echo -e "${CYAN}[ 1/4 ] 下载项目文件...${NC}"

# 安装git
apt-get update -qq 2>/dev/null || yum update -q 2>/dev/null
apt-get install -y git python3-pip -qq 2>/dev/null || yum install -y git python3-pip -q 2>/dev/null

# 克隆项目
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
echo -e "${CYAN}[ 2/4 ] 配置信息${NC}"
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

echo
echo -e "${GREEN}✓ 配置完成${NC}"
echo

# ========== 第三步：安装SSR ==========
echo -e "${CYAN}[ 3/4 ] 安装 ShadowsocksR${NC}"
echo -e "${YELLOW}----------------------------------------${NC}"

if [ -d "$SSR_DIR" ]; then
    echo -e "${GREEN}检测到已安装SSR，跳过安装...${NC}"
else
    echo -e "${GREEN}开始安装 SSR...${NC}"
    echo -e "${YELLOW}提示: 请按照提示操作，选择 1 安装 SSR${NC}"
    echo -e "${YELLOW}安装完成后输入其他命令可退出脚本${NC}"
    echo
    
    # 运行本地的SSR脚本
    chmod +x $PANEL_DIR/ssrmu.sh
    bash $PANEL_DIR/ssrmu.sh
fi

echo

# ========== 第四步：安装管理面板 ==========
echo -e "${CYAN}[ 4/4 ] 安装管理面板${NC}"
echo -e "${YELLOW}----------------------------------------${NC}"

# 安装Python依赖
echo -e "${GREEN}安装 Python 依赖...${NC}"
pip3 install flask gunicorn -q 2>/dev/null

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
echo
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}           安装完成！${NC}"
echo -e "${GREEN}============================================${NC}"
echo
echo -e "${CYAN}管理面板信息:${NC}"
echo -e "  访问地址: ${YELLOW}http://$(curl -s ip.sb):5000${NC}"
echo -e "  用户名:   ${YELLOW}${ADMIN_USER}${NC}"
echo -e "  密码:     ${YELLOW}${ADMIN_PASS}${NC}"
echo
echo -e "${CYAN}常用命令:${NC}"
echo -e "  重启面板:     ${YELLOW}systemctl restart ssr-admin${NC}"
echo -e "  查看面板状态: ${YELLOW}systemctl status ssr-admin${NC}"
echo -e "  管理SSR用户:  ${YELLOW}bash /usr/local/shadowsocksr/shadowsocks/mujson_mgr.sh${NC}"
echo
echo -e "${GREEN}感谢使用！${NC}"
echo
