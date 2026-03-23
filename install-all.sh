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

# ========== 第零步：环境准备 ==========
echo -e "${CYAN}[ 0/5 ] 环境准备...${NC}"
echo -e "${YELLOW}----------------------------------------${NC}"

echo -e "${GREEN}更新系统包...${NC}"
apt update -y 2>/dev/null || yum update -y 2>/dev/null

echo -e "${GREEN}安装必要工具...${NC}"
apt install -y curl socat sudo git python3-pip expect -qq 2>/dev/null || yum install -y curl socat sudo git python3-pip expect -q 2>/dev/null

echo -e "${GREEN}配置虚拟内存 (2GB)...${NC}"
# 检查当前swap
SWAP_SIZE=$(free -m | grep Swap | awk '{print $2}')
if [ "$SWAP_SIZE" -lt 2048 ]; then
    # 创建swap文件
    if [ -f /swapfile ]; then
        swapoff /swapfile 2>/dev/null
        rm -f /swapfile
    fi
    
    dd if=/dev/zero of=/swapfile bs=1M count=2048 status=progress
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    
    # 添加到fstab
    if ! grep -q '/swapfile' /etc/fstab; then
        echo '/swapfile none swap sw 0 0' >> /etc/fstab
    fi
    
    echo -e "${GREEN}✓ 虚拟内存已设置为 2GB${NC}"
else
    echo -e "${GREEN}✓ 虚拟内存已足够 (${SWAP_SIZE}MB)${NC}"
fi

echo -e "${GREEN}✓ 环境准备完成${NC}"
echo

# ========== 第一步：下载项目文件 ==========
echo -e "${CYAN}[ 1/5 ] 下载项目文件...${NC}"

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
echo -e "${CYAN}[ 2/5 ] 配置信息${NC}"
echo -e "${YELLOW}----------------------------------------${NC}"

# 检测是否通过管道运行
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

# 读取管理员用户名
while true; do
    echo -ne "请输入管理面板用户名: "
    if read_input ADMIN_USER; then
        if [ -n "$ADMIN_USER" ]; then
            break
        fi
    fi
    echo -e "${RED}用户名不能为空！${NC}"
done

# 读取管理员密码
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
    
    # 创建自动应答脚本
    cat > /tmp/ssr_auto_install.exp << 'EXPECT'
#!/usr/bin/expect -f
set timeout 120

log_user 1

spawn bash /opt/ssr-admin-panel/ssrmu.sh

expect {
    "请输入数字" { send "1\r" }
    timeout { puts "超时等待菜单"; exit 1 }
}

expect -re "默认.*doubi.*:" { send "\r" }
expect -re "默认.*2333.*:" { send "\r" }
expect -re "默认.*doub.io.*:" { send "\r" }
expect -re "默认.*5.*aes" { send "\r" }
expect -re "默认.*3.*auth" { send "\r" }
expect "Y/n" { send "\r" }
expect -re "默认.*1.*plain" { send "\r" }
expect "Y/n" { send "\r" }
expect -re "默认.*无限.*:" { send "\r" }
expect -re "默认.*无限.*:" { send "\r" }
expect -re "默认.*无限.*:" { send "\r" }
expect -re "默认.*无限.*:" { send "\r" }
expect -re "默认为空.*:" { send "\r" }
expect -re "默认.*Y.*:" { send "\r" }
expect {
    -re "服务器IP或域名" { send "\r"; exp_continue }
    -re "自动检测外网IP" { send "\r"; exp_continue }
    -re "手动输入服务器IP" { send "\r"; exp_continue }
    "安装完毕" { }
    "所有步骤" { }
    timeout { puts "等待安装完成超时" }
}

puts "\nSSR安装完成！"
expect eof
EXPECT

    chmod +x /tmp/ssr_auto_install.exp
    /tmp/ssr_auto_install.exp
    
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

cat > $PANEL_DIR/config.py << CONFIG
# SSR Admin Panel 配置文件
ADMIN_USER = '${ADMIN_USER}'
ADMIN_PASS = '${ADMIN_PASS}'
SECRET_KEY = '${SECRET_KEY}'
MUDB_FILE = '${MUDB_FILE}'
CONFIG

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
echo -e "${CYAN}服务器配置:${NC}"
echo -e "  虚拟内存: ${YELLOW}2GB${NC}"
echo -e "  SSR目录:  ${YELLOW}${SSR_DIR}${NC}"
echo
echo -e "${CYAN}常用命令:${NC}"
echo -e "  重启面板:     ${YELLOW}systemctl restart ssr-admin${NC}"
echo -e "  管理SSR:      ${YELLOW}bash /usr/local/shadowsocksr/ssrmu.sh${NC}"
echo
echo -e "${GREEN}感谢使用！${NC}"
echo
