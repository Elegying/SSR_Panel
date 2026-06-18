#!/bin/bash
# =============================================================
# SSR Server 性能与安全优化脚本
# 由 install.sh / install-all.sh 自动调用，也可独立运行
# 兼容 Debian/Ubuntu/CentOS
# =============================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SSR_DIR="/usr/local/shadowsocksr"
SSR_CONFIG="${SSR_DIR}/user-config.json"
SYSCTL_CONF="/etc/sysctl.d/99-ssr-optimize.conf"
LIMITS_CONF="/etc/security/limits.conf"
LOGROTATE_CONF="/etc/logrotate.d/ssr"
FAIL2BAN_JAIL="/etc/fail2ban/jail.local"

log_ok()   { echo -e "${GREEN}✓ $1${NC}"; }
log_warn() { echo -e "${YELLOW}⚠ $1${NC}"; }
log_info() { echo -e "  $1"; }

# ── 1. SSR systemd 服务 ──────────────────────────────────────
setup_ssr_service() {
    echo -e "${GREEN}[优化 1/6] 配置 SSR systemd 服务...${NC}"

    if [ ! -f "${SSR_DIR}/server.py" ]; then
        log_warn "SSR 未安装，跳过 SSR 服务配置"
        return
    fi

    local PYTHON_BIN
    PYTHON_BIN=$(command -v python 2>/dev/null || command -v python3 2>/dev/null || echo "/usr/bin/python3")

    cat > /etc/systemd/system/ssr.service <<SERVICE
[Unit]
Description=ShadowsocksR Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${SSR_DIR}
ExecStart=${PYTHON_BIN} ${SSR_DIR}/server.py a
Restart=always
RestartSec=3
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
SERVICE

    systemctl daemon-reload
    systemctl enable ssr.service 2>/dev/null

    # 如果 SSR 正在裸进程运行，迁移到 systemd 管理
    local OLD_PID
    OLD_PID=$(pgrep -f "${SSR_DIR}/server.py" | head -1 || true)
    if [ -n "$OLD_PID" ]; then
        log_info "迁移 SSR 进程 PID=$OLD_PID 到 systemd 管理..."
        kill "$OLD_PID" 2>/dev/null || true
        sleep 2
    fi

    systemctl start ssr.service 2>/dev/null || true
    sleep 2

    if systemctl is-active --quiet ssr.service; then
        log_ok "SSR 服务已启动 (systemd 托管，开机自启，崩溃自动重启)"
    else
        log_warn "SSR 服务启动失败，请检查: journalctl -u ssr.service -n 20"
    fi
}

# ── 2. 文件描述符限制 ─────────────────────────────────────────
setup_ulimit() {
    echo -e "${GREEN}[优化 2/6] 提升文件描述符限制...${NC}"

    if grep -q "nofile 65535" "$LIMITS_CONF" 2>/dev/null; then
        log_ok "ulimit 已是 65535，跳过"
        return
    fi

    cat >> "$LIMITS_CONF" <<'EOF'

# SSR Server optimization - raised file descriptor limit
* soft nofile 65535
* hard nofile 65535
root soft nofile 65535
root hard nofile 65535
EOF

    log_ok "ulimit 已提升到 65535（新会话生效，SSR 服务已通过 systemd LimitNOFILE 设置）"
}

# ── 3. 内核参数优化 ───────────────────────────────────────────
setup_sysctl() {
    echo -e "${GREEN}[优化 3/6] 优化内核网络参数...${NC}"

    cat > "$SYSCTL_CONF" <<'EOF'
# ── TCP 缓冲区（配合 BBR 发挥最大吞吐）──
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.ipv4.tcp_rmem = 4096 87380 16777216
net.ipv4.tcp_wmem = 4096 65536 16777216

# ── TCP Fast Open（减少一个 RTT 握手延迟）──
net.ipv4.tcp_fastopen = 3

# ── 连接回收加速（减少半开连接堆积）──
net.ipv4.tcp_fin_timeout = 15
net.ipv4.tcp_keepalive_time = 600
net.ipv4.tcp_keepalive_intvl = 30
net.ipv4.tcp_keepalive_probes = 3
net.ipv4.tcp_tw_reuse = 1

# ── MTU 探测 + 并发 backlog ──
net.ipv4.tcp_mtu_probing = 1
net.core.netdev_max_backlog = 5000
net.ipv4.tcp_slow_start_after_idle = 0
EOF

    sysctl --system > /dev/null 2>&1
    log_ok "内核参数已生效（TCP 缓冲区 16MB / TFO / 快速回收 / MTU 探测）"
}

# ── 4. SSR Fast Open ─────────────────────────────────────────
setup_ssr_fastopen() {
    echo -e "${GREEN}[优化 4/6] 启用 SSR TCP Fast Open...${NC}"

    if [ ! -f "$SSR_CONFIG" ]; then
        log_warn "未找到 ${SSR_CONFIG}，跳过"
        return
    fi

    if command -v python3 &>/dev/null; then
        local CURRENT
        CURRENT=$(python3 -c "import json; print(json.load(open('$SSR_CONFIG')).get('fast_open', False))" 2>/dev/null || echo "False")
        if [ "$CURRENT" = "True" ]; then
            log_ok "SSR fast_open 已启用，跳过"
            return
        fi

        cp "$SSR_CONFIG" "${SSR_CONFIG}.bak"
        python3 -c "
import json
with open('$SSR_CONFIG') as f: d = json.load(f)
d['fast_open'] = True
with open('$SSR_CONFIG', 'w') as f: json.dump(d, f, indent=4, ensure_ascii=False)
"
        log_ok "SSR fast_open 已启用（需重启 SSR 生效）"
    else
        log_warn "python3 不可用，跳过 fast_open 设置"
    fi
}

# ── 5. 日志轮转 ───────────────────────────────────────────────
setup_logrotate() {
    echo -e "${GREEN}[优化 5/6] 配置 SSR 日志轮转...${NC}"

    mkdir -p "$(dirname "$LOGROTATE_CONF")"
    cat > "$LOGROTATE_CONF" <<'EOF'
/usr/local/shadowsocksr/ssserver.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
    maxsize 50M
}
EOF

    log_ok "日志轮转已配置（每天/50MB 轮转，保留 7 天压缩）"
}

# ── 6. fail2ban 防暴力破解 ────────────────────────────────────
setup_fail2ban() {
    echo -e "${GREEN}[优化 6/6] 安装 fail2ban 防暴力破解...${NC}"

    if command -v fail2ban-client &>/dev/null; then
        log_ok "fail2ban 已安装"
    else
        export DEBIAN_FRONTEND="${DEBIAN_FRONTEND:-noninteractive}"
        if command -v dnf &>/dev/null; then
                dnf install -y -q epel-release 2>/dev/null || true
                dnf install -y -q fail2ban 2>/dev/null || {
                    log_warn "fail2ban 安装失败，跳过"
                    return
                }
        elif [ -f /etc/redhat-release ] || [ -f /etc/centos-release ]; then
            if command -v dnf &>/dev/null; then
                dnf install -y -q fail2ban 2>/dev/null || { log_warn "fail2ban 安装失败，跳过"; return; }
            else
                yum install -y -q epel-release 2>/dev/null || log_warn "EPEL 源安装失败，若后续 fail2ban 安装失败请手动安装 epel-release"
                yum install -y -q fail2ban 2>/dev/null || { log_warn "fail2ban 安装失败，跳过"; return; }
            fi
        fi
    fi

    if [ ! -f "$FAIL2BAN_JAIL" ]; then
        cat > "$FAIL2BAN_JAIL" <<'EOF'
[sshd]
enabled = true
port = ssh
filter = sshd
maxretry = 5
bantime = 3600
findtime = 600
EOF
    fi

    systemctl enable fail2ban 2>/dev/null
    systemctl restart fail2ban 2>/dev/null || true
    log_ok "fail2ban 已启用（SSH 5次失败封禁1小时）"
}

# ── 主流程 ────────────────────────────────────────────────────
main() {
    echo
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}    SSR 服务器性能与安全优化${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo

    setup_ssr_service
    setup_ulimit
    setup_sysctl
    setup_ssr_fastopen
    setup_logrotate
    setup_fail2ban

    # 重启 SSR 使 fast_open 生效
    if systemctl is-active --quiet ssr.service; then
        systemctl restart ssr.service 2>/dev/null || true
    fi

    echo
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}    优化完成！${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo -e "  SSR 服务:   $(systemctl is-active ssr.service 2>/dev/null || echo '未运行')"
    echo -e "  fail2ban:   $(systemctl is-active fail2ban 2>/dev/null || echo '未安装')"
    echo -e "  监听端口:   $(ss -tlnp 2>/dev/null | grep -c "server.py" || echo 0) 个"
    echo
}

main "$@"
