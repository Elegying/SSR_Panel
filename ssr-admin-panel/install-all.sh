#!/bin/bash
#=================================================
# SSR + 管理面板 一键部署脚本 v2.0
# Author: Elegying
# GitHub: https://github.com/Elegying/SSR_Panel
#
# v2.0 改进:
#   1. SSR 直接安装（不再 pipe 50 空行）
#   3. 断点续装状态追踪
#   4. venv 虚拟环境优先
#   5. 部署后健康检查
#   6. 端口冲突检测
#   7. iptables 统一兼容处理
#   8. JSON 配置文件预置
#=================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log_ok()   { echo -e "${GREEN}✓ $1${NC}"; }
log_warn() { echo -e "${YELLOW}⚠ $1${NC}"; }
log_err()  { echo -e "${RED}✗ $1${NC}"; }
log_info() { echo -e "  $1"; }

clear 2>/dev/null || true
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}    SSR + 管理面板 一键部署脚本 v2.0${NC}"
echo -e "${GREEN}============================================${NC}"
echo -e "${CYAN}  GitHub: https://github.com/Elegying/SSR_Panel${NC}"; echo

[ "$EUID" -ne 0 ] && { log_err "请使用root权限运行此脚本"; exit 1; }

# ── 全局配置 ──────────────────────────
PANEL_DIR="/opt/ssr-admin-panel"
SSR_DIR="/usr/local/shadowsocksr"
MUDB_FILE="${SSR_DIR}/mudb.json"
VENV_DIR="${PANEL_DIR}/venv"
STATE_FILE="/var/lib/ssr-admin-panel/.install-state"
PRESET_FILE="${SSR_DEPLOY_CONF:-}"
DEVICE_STATS_FILE="${SSR_DEVICE_STATS_FILE:-/var/lib/ssr-admin-panel/device-stats.json}"
DEVICE_STATS_INTERVAL="${SSR_DEVICE_STATS_INTERVAL:-15}"
DEVICE_STATS_WINDOW="${SSR_DEVICE_STATS_WINDOW:-900}"
REPO_URL="${SSR_ADMIN_REPO_URL:-https://github.com/Elegying/SSR_Panel.git}"
REPO_REF="${SSR_ADMIN_UPDATE_REF:-main}"
REPO_SUBDIR="${SSR_ADMIN_REPO_SUBDIR:-ssr-admin-panel}"
PYTHON3_BIN="/usr/bin/python3"
PANEL_PORT="${SSR_PANEL_PORT:-5000}"
APT_UPDATED=0; SYNC_REVISION=""
export DEBIAN_FRONTEND=noninteractive

# ── 加载预置文件 ──────────────────────
load_preset() {
    [ -z "$PRESET_FILE" ] && return 0
    [ -f "$PRESET_FILE" ] || { log_warn "预置文件不存在: $PRESET_FILE"; return 0; }
    log_info "加载预置文件: $PRESET_FILE"

    local _tmp_eval="/tmp/ssr-preset-eval-$$.sh"
    if command -v python3 &>/dev/null; then
        python3 -c "
import json, sys
try:
    with open('$PRESET_FILE') as f: cfg = json.load(f)
    for k, v in cfg.items():
        k = 'SSR_' + k.upper()
        print(f'export {k}={json.dumps(v) if isinstance(v,str) else v}')
except Exception as e:
    print(f'echo PRESET_PARSE_ERROR: {e}', file=sys.stderr)
    sys.exit(1)
" > "$_tmp_eval" 2>/dev/null || { rm -f "$_tmp_eval"; log_err "预置文件解析失败"; exit 1; }
        . "$_tmp_eval"
        rm -f "$_tmp_eval"
        [ -n "${SSR_PORT:-}" ] && PANEL_PORT="$SSR_PORT"
    elif command -v jq &>/dev/null; then
        jq -r 'to_entries[] | "export SSR_"+.key|ascii_upcase+"="+(.value|tostring)' "$PRESET_FILE" > "$_tmp_eval" 2>/dev/null
        . "$_tmp_eval"
        rm -f "$_tmp_eval"
    fi
    log_ok "预置文件已加载"
}

# ── 状态文件 ──────────────────────────
state_done() { local s="$1"; mkdir -p "$(dirname "$STATE_FILE")"; echo "$s=1 $(date +%s)" >> "$STATE_FILE"; }
state_check() { local s="$1"; [ -f "$STATE_FILE" ] && grep -q "^${s}=1" "$STATE_FILE" 2>/dev/null; }

# ── 系统检测 ──────────────────────────
if [ -f /etc/debian_version ] || [ -f /etc/lsb-release ]; then
    SYS="debian"; PKG_MANAGER="apt-get"
elif [ -f /etc/redhat-release ] || [ -f /etc/centos-release ]; then
    SYS="centos"; PKG_MANAGER="yum"
else
    log_err "不支持的系统类型，仅支持 Debian/Ubuntu 和 CentOS/RHEL"
    exit 1
fi
echo -e "${CYAN}系统检测: ${YELLOW}${SYS}${NC}"; echo

install_packages() {
    if [ "$SYS" = "centos" ]; then
        if command -v dnf &>/dev/null; then timeout 180 dnf install -y -q "$@" 2>/dev/null
        else timeout 180 yum install -y -q "$@" 2>/dev/null; fi
        return
    fi
    apt-get install -y -qq "$@" 2>/dev/null && return
    if [ "$APT_UPDATED" -eq 0 ]; then
        log_info "刷新 apt 软件源索引..."
        apt-get update -qq; APT_UPDATED=1
        apt-get install -y -qq "$@"
    fi
}

ensure_minimal_command() {
    local binary="$1"; shift
    command -v "$binary" &>/dev/null && { log_ok "${binary} 已就绪"; return; }
    log_info "${binary} 未找到，安装中..."
    install_packages "$@" || { log_err "${binary} 安装失败"; exit 1; }
}

# ── 第零步：运行环境准备 ──────────────
echo -e "${CYAN}[ 0/7 ] 运行环境准备${NC}"; echo -e "${YELLOW}----------------------------------------${NC}"

prepare_minimal_runtime() {
    if state_check "step0"; then log_ok "step0 已完成，跳过"; return 0; fi

    log_info "检查并安装最小运行环境..."
    local MISSING="" _ss_pkg="iproute2"
    [ "$SYS" = "centos" ] && _ss_pkg="iproute"
    for cmd_pkg in "systemctl:systemd" "curl:curl" "ss:${_ss_pkg}" "git:git" "python3:python3"; do
        local cmd="${cmd_pkg%%:*}" pkg="${cmd_pkg##*:}"
        command -v "$cmd" &>/dev/null || MISSING="$MISSING $pkg"
    done
    [ -n "$MISSING" ] && { log_info "安装系统依赖:${MISSING}"; install_packages $MISSING || { log_err "系统依赖安装失败"; exit 1; }; }
    log_ok "系统依赖已就绪"

    # python → python3
    if ! command -v python &>/dev/null; then
        log_info "创建 python → python3 兼容入口..."
        install_packages python-is-python3 2>/dev/null || ln -sf "$(command -v python3)" /usr/local/bin/python
    fi
    PYTHON3_BIN=$(command -v python3 2>/dev/null || echo "/usr/bin/python3")

    # pip
    if ! "$PYTHON3_BIN" -m pip --version &>/dev/null; then
        log_info "启用 pip..."
        "$PYTHON3_BIN" -m ensurepip --upgrade >/dev/null 2>&1 || true
        "$PYTHON3_BIN" -m pip --version &>/dev/null || install_packages python3-pip 2>/dev/null || true
    fi

    # iptables 兼容 (7)
    if ! command -v iptables &>/dev/null; then
        log_info "iptables 未安装，安装中（ssrmu.sh 依赖）..."
        if [ "$SYS" = "centos" ]; then
            command -v dnf &>/dev/null && timeout 120 dnf install -y -q iptables 2>/dev/null || \
                timeout 120 yum install -y -q iptables 2>/dev/null || true
        else
            install_packages iptables 2>/dev/null || true
        fi
    fi
    command -v iptables &>/dev/null && log_ok "iptables 已就绪" || log_warn "iptables 不可用（SSR 可运行，端口管理需手动）"

    # cronie (CentOS)
    if [ "$SYS" = "centos" ] && ! command -v crond &>/dev/null; then
        log_info "安装 cronie..."
        install_packages cronie
        systemctl enable crond 2>/dev/null || true; systemctl start crond 2>/dev/null || true
    fi

    state_done "step0"
}

prepare_minimal_runtime
echo -e "${GREEN}运行环境就绪${NC}"; echo

# ── 第一步：下载项目文件 ──────────────
echo -e "${CYAN}[ 1/7 ] 下载项目文件${NC}"

sync_project_files() {
    if state_check "step1"; then log_ok "step1 已完成，跳过"; return 0; fi
    local tmp=$(mktemp -d /tmp/ssr-admin-panel.XXXXXX)
    git clone --depth 1 --branch "$REPO_REF" "$REPO_URL" "$tmp" -q
    local src="$tmp"; [ -n "$REPO_SUBDIR" ] && src="$tmp/$REPO_SUBDIR"
    [ ! -f "$src/app.py" ] && { log_err "项目文件未找到: ${src}"; rm -rf "$tmp"; exit 1; }
    mkdir -p "$PANEL_DIR"
    find "$PANEL_DIR" -mindepth 1 -maxdepth 1 ! -name config.py ! -name backups ! -name venv -exec rm -rf {} +
    cp -R "$src"/. "$PANEL_DIR"/
    SYNC_REVISION=$(git -C "$tmp" rev-parse --short HEAD 2>/dev/null || echo "")
    rm -rf "$tmp"
    state_done "step1"
}

sync_project_files "$PANEL_DIR"
cd "$PANEL_DIR"
chmod +x "$PANEL_DIR"/{update.sh,install.sh,install-all.sh,uninstall.sh,ssrmu.sh} 2>/dev/null || true
chmod +x "$PANEL_DIR/scripts"/{collect_device_stats.py,optimize_server.sh,patch_ssr_python_compat.py} 2>/dev/null || true

APP_VERSION=$(cat "$PANEL_DIR/VERSION" 2>/dev/null | tr -d '\r\n')
APP_REVISION="${SYNC_REVISION:-$([ -d "$PANEL_DIR/.git" ] && git -C "$PANEL_DIR" rev-parse --short HEAD 2>/dev/null || echo "")}"
log_ok "项目文件下载完成 (${APP_VERSION} ${APP_REVISION})"; echo

# ── 第二步：配置信息 ──────────────────
echo -e "${CYAN}[ 2/7 ] 配置信息${NC}"; echo -e "${YELLOW}----------------------------------------${NC}"

ADMIN_USER="${SSR_ADMIN_USER:-}"; ADMIN_PASS="${SSR_ADMIN_PASS:-}"

safe_read() {
    local vn="$1" p="$2" pw="$3"
    [ -n "${!vn:-}" ] && return 0
    local i=""
    if [ -t 0 ]; then [ "$pw" = "yes" ] && read -rs -p "$p" i || read -r -p "$p" i; echo
    elif [ -e /dev/tty ]; then [ "$pw" = "yes" ] && read -rs -p "$p" i < /dev/tty || read -r -p "$p" i < /dev/tty; echo
    else return 1; fi
    printf -v "$vn" '%s' "$i"; return 0
}

if [ -z "$ADMIN_USER" ]; then
    safe_read ADMIN_USER "管理面板用户名: " "no" || { log_err "非交互模式请设置 SSR_ADMIN_USER 环境变量"; exit 1; }
    [ -z "$ADMIN_USER" ] && { log_err "用户名不能为空"; exit 1; }
fi
if [ -z "$ADMIN_PASS" ]; then
    safe_read ADMIN_PASS "管理面板密码: " "yes" || { log_err "非交互模式请设置 SSR_ADMIN_PASS 环境变量"; exit 1; }
    [ -z "$ADMIN_PASS" ] && { log_err "密码不能为空"; exit 1; }
    safe_read CPC "再次输入密码确认: " "yes" && [ "$ADMIN_PASS" != "$CPC" ] && { log_err "两次密码不一致"; exit 1; }
fi

# 分享模板
SHARE_HOST=""; SHARE_PORT="18899"; SHARE_PASSWORD=""; SHARE_REMARKS=""
SHARE_PROTOCOL="auth_aes128_md5"; SHARE_METHOD="aes-256-cfb"; SHARE_OBFS="tls1.2_ticket_auth"; SHARE_OBFS_PARAM="www.baidu.com"

echo; echo -e "${CYAN}[ 可选：配置账号分享模板 ]${NC}"
if [ -n "${SSR_ADMIN_USER:-}" ]; then
    if [ -n "${SSR_SHARE_HOST:-}" ]; then
        ENABLE_SHARE="y"; SHARE_HOST="$SSR_SHARE_HOST"
        SHARE_PASSWORD="nikuaimobi"; SHARE_REMARKS="私家车-2025"
        log_ok "已自动启用分享: ${SHARE_HOST}"
    else
        ENABLE_SHARE="n"; log_warn "非交互模式，已跳过分享配置"
    fi
else
    if [ -t 0 ]; then read -p "是否启用账号分享模板？[y/N]: " ENABLE_SHARE
    elif [ -e /dev/tty ]; then read -p "是否启用账号分享模板？[y/N]: " ENABLE_SHARE < /dev/tty
    else ENABLE_SHARE="n"; fi
fi
ENABLE_SHARE=$(printf '%s' "${ENABLE_SHARE:-n}" | tr '[:upper:]' '[:lower:]')

if [ "$ENABLE_SHARE" = "y" ] || [ "$ENABLE_SHARE" = "yes" ]; then
    if [ -z "${SHARE_HOST:-}" ]; then
        if [ -t 0 ]; then read -p "分享域名/IP: " SHARE_HOST
        elif [ -e /dev/tty ]; then read -p "分享域名/IP: " SHARE_HOST < /dev/tty
        else SHARE_HOST=""; fi
    fi
    if [ -z "$SHARE_HOST" ]; then log_err "分享域名不能为空，已关闭分享功能"; ENABLE_SHARE="n"
    else SHARE_PASSWORD="nikuaimobi"; SHARE_REMARKS="私家车-2025"; fi
fi
log_ok "配置完成"; echo

# ── 第三步：安装 SSR ───────────────────
echo -e "${CYAN}[ 3/7 ] 安装 ShadowsocksR${NC}"; echo -e "${YELLOW}----------------------------------------${NC}"

install_ssr_direct() {
    # 直接安装 SSR，不再 pipe 50 个空行 (1)
    if state_check "step3"; then
        log_ok "step3 已完成，跳过"
        return 0
    fi
    if [ -d "$SSR_DIR" ] && [ -f "$SSR_DIR/server.py" ]; then
        log_ok "检测到已安装 SSR，跳过安装"
        state_done "step3"; return 0
    fi

    log_info "直接安装 ShadowsocksR..."

    # 下载 SSR
    local SSR_TMP=$(mktemp -d)
    curl -fsSL -m 60 "https://github.com/ToyoDAdoubiBackup/shadowsocksr/archive/manyuser.zip" -o "$SSR_TMP/manyuser.zip" || {
        log_err "SSR 下载失败"; rm -rf "$SSR_TMP"; exit 1;
    }
    # 安装 unzip
    command -v unzip &>/dev/null || install_packages unzip 2>/dev/null || true
    unzip -qo "$SSR_TMP/manyuser.zip" -d "$SSR_TMP/"
    mkdir -p "$SSR_DIR"
    cp -R "$SSR_TMP/shadowsocksr-manyuser"/* "$SSR_DIR"/
    rm -rf "$SSR_TMP"

    # Python 兼容修复
    if "$PYTHON3_BIN" "$PANEL_DIR/scripts/patch_ssr_python_compat.py" "$SSR_DIR" 2>/dev/null; then
        log_ok "SSR Python 兼容性已修复"
    fi

    # 初始化 mudb.json
    cat > "$MUDB_FILE" <<'JSON'
[]
JSON

    # 配置 userapiconfig.py 为 mudbjson 模式
    cat > "$SSR_DIR/userapiconfig.py" <<'PYEOF'
import os
API_INTERFACE = 'mudbjson'
SERVER_PUB_ADDR = '127.0.0.1'
MUDB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mudb.json')
PYEOF

    # 下载 init.d 脚本
    local init_url="https://raw.githubusercontent.com/ToyoDAdoubiBackup/doubi/master/service/ssrmu_debian"
    [ "$SYS" = "centos" ] && init_url="https://raw.githubusercontent.com/ToyoDAdoubiBackup/doubi/master/service/ssrmu_centos"
    curl -fsSL -m 10 "$init_url" -o /etc/init.d/ssrmu 2>/dev/null || true
    if [ ! -s /etc/init.d/ssrmu ]; then
        # 生成本地 init.d 脚本
        cat > /etc/init.d/ssrmu <<'INITSH'
#!/bin/bash
### BEGIN INIT INFO
# Provides:          ssrmu
# Required-Start:    $network $local_fs $remote_fs
# Required-Stop:     $network $local_fs $remote_fs
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: ShadowsocksR multi-user
### END INIT INFO

SSR_DIR=/usr/local/shadowsocksr
PYTHON_BIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || echo "/usr/bin/python3")

case "$1" in
    start)   cd "$SSR_DIR" && nohup "$PYTHON_BIN" server.py a > /dev/null 2>&1 & echo "SSR started" ;;
    stop)    pkill -f "$SSR_DIR/server.py" 2>/dev/null || true; echo "SSR stopped" ;;
    restart) "$0" stop; sleep 1; "$0" start ;;
    status)  pgrep -f "$SSR_DIR/server.py" > /dev/null 2>&1 && echo "SSR is running" || echo "SSR is not running" ;;
    *)       echo "Usage: $0 {start|stop|restart|status}" ;;
esac
INITSH
    fi
    chmod +x /etc/init.d/ssrmu

    # 添加默认用户 doubi:2333
    local _iptext=""
    IP=$(curl -s -m 10 ip.sb 2>/dev/null || curl -s -m 10 ifconfig.me 2>/dev/null || echo '127.0.0.1')
    cd "$SSR_DIR"
    _iptext=$("$PYTHON3_BIN" mujson_mgr.py -a -u "doubi" -p "2333" -k "doub.io" -m "aes-128-ctr" -O "auth_aes128_md5" -o "plain" 2>&1) || true
    log_info "$_iptext"

    # 添加 iptables 规则
    if command -v iptables &>/dev/null; then
        iptables -I INPUT -p tcp --dport 2333 -j ACCEPT 2>/dev/null || true
        iptables -I INPUT -p udp --dport 2333 -j ACCEPT 2>/dev/null || true
    fi

    # 启动 SSR
    local SSR_PY="$PYTHON3_BIN"; command -v python &>/dev/null && SSR_PY="$(command -v python)"
    cd "$SSR_DIR" && nohup "$SSR_PY" server.py a > /var/log/ssr.log 2>&1 &
    sleep 2
    if pgrep -f "$SSR_DIR/server.py" >/dev/null 2>&1; then
        log_ok "SSR 已启动"
    else
        log_warn "SSR 启动可能失败，请检查: cat /var/log/ssr.log"
    fi

    state_done "step3"
}

install_ssr_direct
echo

# ── 第四步：Flask 运行时 ──────────────
echo -e "${CYAN}[ 4/7 ] 安装 Python 运行时${NC}"; echo -e "${YELLOW}----------------------------------------${NC}"

install_flask_venv() {
    # 优先使用 venv (4)，失败回退到系统包
    if state_check "step4"; then log_ok "step4 已完成，跳过"; return 0; fi

    if [ -d "$VENV_DIR" ] && [ -f "$VENV_DIR/bin/python3" ]; then
        log_ok "venv 已存在，跳过创建"
    else
        log_info "创建 Python 虚拟环境..."
        # 确保 python3-venv 已安装（Ubuntu 24.04+ 默认未装）
        if ! "$PYTHON3_BIN" -c "import ensurepip" 2>/dev/null; then
            log_info "安装 python3-venv..."
            [ "$SYS" = "debian" ] && install_packages python3-venv 2>/dev/null || true
        fi
        "$PYTHON3_BIN" -m venv "$VENV_DIR" 2>/dev/null || {
            log_warn "venv 创建失败，回退到系统 pip"
            VENV_DIR=""; install_flask_system; return 0
        }
        log_ok "venv 已创建: $VENV_DIR"
    fi

    local PIP="$VENV_DIR/bin/pip"
    local PYT="$VENV_DIR/bin/python3"
    "$PIP" install --upgrade pip -q 2>/dev/null || true

    local req="$PANEL_DIR/requirements.txt"
    if [ -f "$req" ]; then
        "$PIP" install --no-input --disable-pip-version-check -r "$req" -q 2>/dev/null || {
            log_warn "venv pip 安装失败，尝试逐个安装..."
            "$PIP" install --no-input Flask>=3.0 flask-limiter waitress -q 2>/dev/null || true
        }
    else
        "$PIP" install --no-input Flask>=3.0 flask-limiter waitress -q 2>/dev/null || true
    fi

    if "$PYT" -c "import flask,flask_limiter,waitress" 2>/dev/null; then
        log_ok "Flask 运行时 (venv) 就绪"
        PYTHON3_BIN="$PYT"  # 后续使用 venv 中的 python
    else
        log_warn "venv 安装不完整，回退到系统包"
        VENV_DIR=""; install_flask_system
    fi
    state_done "step4"
}

install_flask_system() {
    if "$PYTHON3_BIN" -c "import flask,flask_limiter,waitress" 2>/dev/null; then
        log_ok "Flask 运行时 (系统) 已就绪"; return
    fi

    local popts="--no-input --disable-pip-version-check"
    local _nb=0
    "$PYTHON3_BIN" -c "import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)" 2>/dev/null && _nb=1
    local _em=$("$PYTHON3_BIN" -c "import sysconfig; print(sysconfig.get_path('stdlib'))" 2>/dev/null)/EXTERNALLY-MANAGED
    [ -f "$_em" ] && _nb=1
    [ "$_nb" -eq 1 ] && popts="$popts --break-system-packages"

    "$PYTHON3_BIN" -m pip install $popts --prefer-binary -q Flask>=3.0 flask-limiter waitress 2>/dev/null || \
    "$PYTHON3_BIN" -m pip install $popts Flask flask-limiter waitress -q 2>/dev/null || true

    "$PYTHON3_BIN" -c "import flask" 2>/dev/null || {
        [ "$SYS" = "debian" ] && install_packages python3-flask python3-flask-limiter 2>/dev/null || true
    }
}

# 选择安装策略
if [ "${SSR_USE_VENV:-1}" = "0" ]; then
    install_flask_system
else
    install_flask_venv
fi

# 确保运行时可用
if ! "$PYTHON3_BIN" -c "import flask" 2>/dev/null; then
    log_err "Flask 运行时安装失败"; exit 1
fi
echo

# ── 第五步：部署面板服务 ──────────────
echo -e "${CYAN}[ 5/7 ] 部署管理面板${NC}"; echo -e "${YELLOW}----------------------------------------${NC}"

# 端口冲突检测 (6)
if state_check "step5"; then log_ok "step5 已完成，跳过"; else

# 先检查端口
if ss -tlnp 2>/dev/null | grep -q ":${PANEL_PORT} "; then
    _existing_pid=$(ss -tlnp | grep ":${PANEL_PORT} " | head -1)
    if systemctl is-active --quiet ssr-admin 2>/dev/null; then
        log_warn "端口 ${PANEL_PORT} 已被 ssr-admin 旧实例占用，将覆盖"
        systemctl stop ssr-admin 2>/dev/null || true
    elif pgrep -f "waitress.*${PANEL_PORT}" >/dev/null 2>&1; then
        log_warn "端口 ${PANEL_PORT} 已被占用，尝试释放..."
        pkill -f "waitress.*${PANEL_PORT}" 2>/dev/null || true
        sleep 1
    elif [ -n "$_existing_pid" ]; then
        log_err "端口 ${PANEL_PORT} 已被占用: $_existing_pid"
        echo -e "${CYAN}提示: 设置 SSR_PANEL_PORT 环境变量使用其他端口${NC}"
        exit 1
    fi
fi

# 生成 config.py
echo -e "${GREEN}生成配置文件...${NC}"
if [ -f "$PANEL_DIR/config.py" ]; then
    log_warn "检测到现有配置文件，已保留: $PANEL_DIR/config.py"
else
    SECRET_KEY=$("$PYTHON3_BIN" -c "import secrets; print(secrets.token_hex(32))")
    PANEL_DIR="$PANEL_DIR" PYTHON3_BIN="$PYTHON3_BIN" ADMIN_USER="$ADMIN_USER" ADMIN_PASS="$ADMIN_PASS" SECRET_KEY="$SECRET_KEY" MUDB_FILE="$MUDB_FILE" DEVICE_STATS_FILE="$DEVICE_STATS_FILE" SHARE_HOST="$SHARE_HOST" SHARE_PORT="$SHARE_PORT" SHARE_PASSWORD="$SHARE_PASSWORD" SHARE_REMARKS="$SHARE_REMARKS" SHARE_PROTOCOL="$SHARE_PROTOCOL" SHARE_METHOD="$SHARE_METHOD" SHARE_OBFS="$SHARE_OBFS" SHARE_OBFS_PARAM="$SHARE_OBFS_PARAM" "$PYTHON3_BIN" << 'PY'
import os; from pathlib import Path
def i(v,d): return int(v) if v else d

c = os.environ
cfg = Path(c["PANEL_DIR"]) / "config.py"
vals = {
    "ADMIN_USER": c["ADMIN_USER"], "ADMIN_PASS": c["ADMIN_PASS"],
    "SECRET_KEY": c["SECRET_KEY"], "MUDB_FILE": c["MUDB_FILE"],
    "SSR_SHARE_HOST": c.get("SHARE_HOST",""), "SSR_SHARE_PORT": i(c.get("SHARE_PORT"),18899),
    "SSR_SHARE_PASSWORD": c.get("SHARE_PASSWORD",""), "SSR_SHARE_REMARKS": c.get("SHARE_REMARKS",""),
    "SSR_SHARE_PROTOCOL": c.get("SHARE_PROTOCOL","auth_aes128_md5"),
    "SSR_SHARE_METHOD": c.get("SHARE_METHOD","aes-256-cfb"),
    "SSR_SHARE_OBFS": c.get("SHARE_OBFS","tls1.2_ticket_auth"),
    "SSR_SHARE_OBFS_PARAM": c.get("SHARE_OBFS_PARAM","www.baidu.com"),
    "DEVICE_STATS_FILE": c.get("DEVICE_STATS_FILE","/var/lib/ssr-admin-panel/device-stats.json"),
    "DEVICE_STATS_STALE_SECONDS": 120,
}
with cfg.open("w",encoding="utf-8") as f:
    f.write("# SSR Admin Panel 配置文件\n")
    for k,v in vals.items(): f.write(f"{k} = {v!r}\n")
PY
fi

# 设备统计服务
log_info "配置设备统计服务..."
ensure_minimal_command "ss" "iproute2"
mkdir -p "$(dirname "$DEVICE_STATS_FILE")"

cat > /etc/systemd/system/ssr-device-stats.service <<SERVICE
[Unit]
Description=SSR Device Stats Collector
After=network.target
[Service]
Type=simple; User=root
ExecStart=${PYTHON3_BIN} ${PANEL_DIR}/scripts/collect_device_stats.py --mudb ${MUDB_FILE} --output ${DEVICE_STATS_FILE} --interval ${DEVICE_STATS_INTERVAL} --window ${DEVICE_STATS_WINDOW} --watch
Restart=always; RestartSec=5
[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable ssr-device-stats 2>/dev/null
systemctl restart ssr-device-stats 2>/dev/null || true

# ssr-admin 服务 — 始终用 python -m waitress（兼容 venv 和系统安装）
cat > /etc/systemd/system/ssr-admin.service <<SERVICE
[Unit]
Description=SSR Admin Panel
After=network.target
[Service]
Type=simple; User=root
WorkingDirectory=${PANEL_DIR}
ExecStart=${PYTHON3_BIN} -m waitress --host=0.0.0.0 --port=${PANEL_PORT} app:app
Restart=always; RestartSec=5
NoNewPrivileges=true; PrivateTmp=true; RestrictSUIDSGID=true; LockPersonality=true; UMask=0077
[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable ssr-admin 2>/dev/null
systemctl restart ssr-admin

sleep 2
if systemctl is-active --quiet ssr-admin; then
    log_ok "ssr-admin 服务运行中"
else
    log_err "ssr-admin 服务启动失败"
    echo -e "${CYAN}诊断:${NC} journalctl -u ssr-admin -n 50 --no-pager"
    journalctl -u ssr-admin -n 50 --no-pager || true
    exit 1
fi

state_done "step5"; fi
echo

# ── 第六步：服务器优化 ────────────────
echo -e "${CYAN}[ 6/7 ] SSR 服务器性能优化${NC}"
echo
if [ -f "$PANEL_DIR/scripts/optimize_server.sh" ] && [ -x "$PANEL_DIR/scripts/optimize_server.sh" ]; then
    bash "$PANEL_DIR/scripts/optimize_server.sh"
else
    log_warn "优化脚本不存在或不可执行，跳过服务器优化"
fi
echo

# ── 第七步：完成 + 健康检查 ──────────
echo -e "${CYAN}[ 7/7 ] 完成 & 验证${NC}"
sleep 2

IP=$(curl -s -m 10 ip.sb 2>/dev/null || curl -s -m 10 ifconfig.me 2>/dev/null || echo 'your-server-ip')
echo
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}           安装完成！${NC}"
echo -e "${GREEN}============================================${NC}"
echo
echo -e "${CYAN}管理面板信息:${NC}"
echo -e "  访问地址: ${YELLOW}http://${IP}:${PANEL_PORT}${NC}"
echo -e "  用户名:   ${YELLOW}${ADMIN_USER}${NC}"
echo -e "  密码:     ${YELLOW}${ADMIN_PASS}${NC}"
echo -e "  版本:     ${YELLOW}${APP_VERSION:-unknown}${NC}"
echo
echo -e "${CYAN}SSR默认用户:${NC}"
echo -e "  用户名:   ${YELLOW}doubi${NC}"
echo -e "  端口:     ${YELLOW}2333${NC}"
echo -e "  密码:     ${YELLOW}doub.io${NC}"
echo
echo -e "${CYAN}常用命令:${NC}"
echo -e "  重启面板:     ${YELLOW}systemctl restart ssr-admin${NC}"
echo -e "  更新面板:     ${YELLOW}bash ${PANEL_DIR}/update.sh${NC}"
echo -e "  卸载面板:     ${YELLOW}bash ${PANEL_DIR}/uninstall.sh --yes${NC}"
echo -e "  管理SSR:      ${YELLOW}bash ${PANEL_DIR}/ssrmu.sh${NC}"
echo
if [ -n "${VENV_DIR:-}" ]; then
    echo -e "${CYAN}Python 环境:${NC} ${YELLOW}${VENV_DIR}${NC}"
fi
echo

# 健康检查 (5)
echo -e "${CYAN}健康检查...${NC}"
sleep 1

# 检查面板 HTTP 响应
if curl -sf -m 5 "http://127.0.0.1:${PANEL_PORT}/" >/dev/null 2>&1; then
    log_ok "管理面板 HTTP 响应正常"
else
    log_warn "管理面板未响应 HTTP，请检查: journalctl -u ssr-admin -n 20"
fi

# 检查 SSR 进程
if pgrep -f "$SSR_DIR/server.py" >/dev/null 2>&1; then
    _ssr_count=$(pgrep -f "$SSR_DIR/server.py" | wc -l | tr -d ' ')
    log_ok "SSR 服务运行中 (${_ssr_count} 进程)"
else
    log_warn "SSR 进程未运行"
fi

# 检查服务状态
for svc in ssr-admin ssr-device-stats ssr.service fail2ban; do
    if systemctl is-active --quiet "$svc" 2>/dev/null; then
        echo -e "  ${GREEN}●${NC} $svc active"
    else
        echo -e "  ${YELLOW}○${NC} $svc inactive"
    fi
done

echo
echo -e "${GREEN}感谢使用！${NC}"
echo
