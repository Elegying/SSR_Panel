#!/usr/bin/env bash
set -Eeuo pipefail

SSR_DIR="${SSR_DIR:-/usr/local/shadowsocksr}"
SSR_CONFIG="${SSR_CONFIG:-$SSR_DIR/user-config.json}"
MUDB_FILE="${MUDB_FILE:-$SSR_DIR/mudb.json}"
PANEL_DIR="${PANEL_DIR:-/opt/ssr-admin-panel}"
DEVICE_STATS_SCRIPT="${DEVICE_STATS_SCRIPT:-$PANEL_DIR/scripts/collect_device_stats.py}"
DEVICE_STATS_FILE="${DEVICE_STATS_FILE:-/var/lib/ssr-admin-panel/device-stats.json}"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"
SYSCTL_DIR="${SYSCTL_DIR:-/etc/sysctl.d}"
DEVICE_STATS_SERVICE="${DEVICE_STATS_SERVICE:-$SYSTEMD_DIR/ssr-device-stats.service}"
SYSCTL_FILE="${SYSCTL_FILE:-$SYSCTL_DIR/99-z-ssr-performance.conf}"
SERVICE_FILE="${SERVICE_FILE:-$SYSTEMD_DIR/ssr.service}"
TIMESTAMP="$(date +%F-%H%M%S)"
BACKUP_FILES=""
ROLLBACK_ON_ERROR=0

log() {
  printf '[ssr-opt] %s\n' "$*"
}

fail() {
  printf '[ssr-opt] ERROR: %s\n' "$*" >&2
  exit 1
}

require_root() {
  [[ "${SSR_OPT_SKIP_ROOT_CHECK:-0}" = "1" ]] && return
  [[ "${EUID:-$(id -u)}" -eq 0 ]] || fail "run as root"
}

require_tools() {
  command -v systemctl >/dev/null 2>&1 || fail "systemctl not found"
  command -v python3 >/dev/null 2>&1 || fail "python3 not found"
  command -v sysctl >/dev/null 2>&1 || fail "sysctl not found"
}

ensure_ss_tool() {
  if command -v ss >/dev/null 2>&1; then
    return
  fi

  log "ss command not found; trying to install iproute2"
  if command -v apt-get >/dev/null 2>&1; then
    DEBIAN_FRONTEND=noninteractive apt-get update -qq >/dev/null 2>&1 || true
    DEBIAN_FRONTEND=noninteractive apt-get install -y iproute2 -qq >/dev/null 2>&1 || true
  elif command -v yum >/dev/null 2>&1; then
    yum install -y iproute -q >/dev/null 2>&1 || true
  fi
}

backup_file() {
  local file="$1"
  if [[ -f "$file" ]]; then
    local backup="${file}.bak.${TIMESTAMP}"
    cp -a "$file" "$backup"
    BACKUP_FILES="${BACKUP_FILES}${file}|${backup}
"
  else
    BACKUP_FILES="${BACKUP_FILES}${file}|
"
  fi
}

restore_backups() {
  local line file backup
  while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    file="${line%%|*}"
    backup="${line#*|}"
    if [[ -f "$backup" ]]; then
      cp -a "$backup" "$file"
      log "restored $file from $backup"
    elif [[ -e "$file" ]]; then
      rm -rf "$file"
      log "removed newly created $file"
    fi
  done <<EOF
$BACKUP_FILES
EOF
}

on_error() {
  local line="${1:-unknown}"
  if [[ "$ROLLBACK_ON_ERROR" -eq 1 ]]; then
    log "error at line $line; restoring changed files"
    restore_backups
    systemctl daemon-reload >/dev/null 2>&1 || true
  fi
}

detect_python() {
  if command -v python >/dev/null 2>&1; then
    command -v python
  else
    command -v python3
  fi
}

validate_layout() {
  [[ -d "$SSR_DIR" ]] || fail "$SSR_DIR not found"
  [[ -f "$SSR_CONFIG" ]] || fail "$SSR_CONFIG not found"
}

patch_ssr_config() {
  log "updating SSR config"
  backup_file "$SSR_CONFIG"
  python3 - "$SSR_CONFIG" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
raw = path.read_text(encoding="utf-8-sig")
data = json.loads(raw)
data["timeout"] = 300
data["udp_timeout"] = 120
data["fast_open"] = True
path.write_text(json.dumps(data, indent=4) + "\n", encoding="utf-8")
PY
}

write_sysctl() {
  log "writing sysctl tuning"
  log "will update $SYSCTL_FILE"
  backup_file "$SYSCTL_FILE"
  mkdir -p "$(dirname "$SYSCTL_FILE")"
  cat > "$SYSCTL_FILE" <<'EOF'
fs.file-max = 1048576
net.core.somaxconn = 8192
net.core.netdev_max_backlog = 16384
net.core.rmem_default = 262144
net.core.wmem_default = 262144
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.ipv4.ip_local_port_range = 10240 65535
net.ipv4.tcp_congestion_control = bbr
net.core.default_qdisc = fq
net.ipv4.tcp_max_syn_backlog = 8192
net.ipv4.tcp_fastopen = 3
net.ipv4.tcp_mtu_probing = 1
net.ipv4.tcp_slow_start_after_idle = 0
net.ipv4.tcp_fin_timeout = 15
net.ipv4.tcp_rmem = 4096 262144 16777216
net.ipv4.tcp_wmem = 4096 262144 16777216
net.netfilter.nf_conntrack_max = 262144
EOF
}

fix_conflicting_backlog() {
  for file in "${SYSCTL_CONF:-/etc/sysctl.conf}" "${SYSCTL_DIR}/99-sysctl.conf"; do
    if [[ -f "$file" ]] && grep -Eq '^[[:space:]]*net\.ipv4\.tcp_max_syn_backlog[[:space:]]*=[[:space:]]*1024([[:space:]]*)$' "$file"; then
      log "fixing old backlog override in $file"
      backup_file "$file"
      sed -i 's/^[[:space:]]*net\.ipv4\.tcp_max_syn_backlog[[:space:]]*=.*/net.ipv4.tcp_max_syn_backlog = 8192/' "$file"
    fi
  done
}

write_systemd_unit() {
  local pybin
  pybin="$(detect_python)"
  log "writing systemd service"
  log "will update $SERVICE_FILE"
  backup_file "$SERVICE_FILE"
  mkdir -p "$(dirname "$SERVICE_FILE")"
  cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=ShadowsocksR Python Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$SSR_DIR
ExecStart=$pybin $SSR_DIR/server.py a
Restart=always
RestartSec=3
LimitNOFILE=1048576
TasksMax=infinity

[Install]
WantedBy=multi-user.target
EOF
}

write_device_stats_unit() {
  if [[ ! -f "$DEVICE_STATS_SCRIPT" ]]; then
    log "device stats collector not found; skipping device stats service"
    return
  fi

  ensure_ss_tool
  mkdir -p "$(dirname "$DEVICE_STATS_FILE")"
  chmod +x "$DEVICE_STATS_SCRIPT" 2>/dev/null || true
  log "writing device stats service"
  log "will update $DEVICE_STATS_SERVICE"
  backup_file "$DEVICE_STATS_SERVICE"
  mkdir -p "$(dirname "$DEVICE_STATS_SERVICE")"
  cat > "$DEVICE_STATS_SERVICE" <<EOF
[Unit]
Description=SSR Device Stats Collector
After=network.target

[Service]
Type=simple
User=root
ExecStart=$(command -v python3) $DEVICE_STATS_SCRIPT --mudb $MUDB_FILE --output $DEVICE_STATS_FILE --interval 15 --window 900 --watch
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable ssr-device-stats >/dev/null 2>&1 || true
  systemctl restart ssr-device-stats || true
}

apply_sysctl() {
  log "reloading sysctl"
  local log_file="/tmp/ssr-optimizer-sysctl.log"
  if sysctl --system >"$log_file" 2>&1; then
    return
  fi

  log "sysctl reload reported warnings/errors; see $log_file"
  sed 's/^/[ssr-opt] sysctl: /' "$log_file" >&2 || true
}

restart_ssr() {
  log "reloading systemd"
  systemctl daemon-reload
  systemctl stop ssr >/dev/null 2>&1 || true
  if pgrep -f "$SSR_DIR/server.py a" >/dev/null 2>&1; then
    log "stopping existing SSR process"
    pkill -f "$SSR_DIR/server.py a" || true
    sleep 2
  fi
  log "enabling and starting ssr.service"
  systemctl enable ssr >/dev/null 2>&1 || true
  systemctl start ssr
  sleep 3
}

verify() {
  log "verifying SSR state"
  systemctl is-active --quiet ssr || fail "ssr.service is not active"

  python3 - "$SSR_CONFIG" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8-sig"))
assert data.get("timeout") == 300, data
assert data.get("udp_timeout") == 120, data
assert bool(data.get("fast_open")) is True, data
PY

  local current_backlog
  current_backlog="$(sysctl -n net.ipv4.tcp_max_syn_backlog 2>/dev/null || true)"
  log "ssr.service is active"
  log "tcp_max_syn_backlog=${current_backlog}"
  log "completed successfully"
}

check_mode() {
  require_root
  require_tools
  validate_layout
  command -v ss >/dev/null 2>&1 || fail "ss not found; install iproute2 before applying optimization"

  log "preflight ok"
  log "SSR_DIR=$SSR_DIR"
  log "SSR_CONFIG=$SSR_CONFIG"
  log "SYSCTL_FILE=$SYSCTL_FILE"
  log "SERVICE_FILE=$SERVICE_FILE"
  if [[ -f "$DEVICE_STATS_SCRIPT" ]]; then
    log "device stats collector found"
  else
    log "device stats collector not found; device stats service will be skipped"
  fi
}

run_apply() {
  require_root
  require_tools
  validate_layout
  log "planned changes:"
  log "- update SSR config: timeout=300, udp_timeout=120, fast_open=true"
  log "- write sysctl tuning: $SYSCTL_FILE"
  log "- write systemd unit: $SERVICE_FILE"
  log "- refresh device stats unit when panel collector exists"
  ROLLBACK_ON_ERROR=1
  patch_ssr_config
  write_sysctl
  fix_conflicting_backlog
  write_systemd_unit
  write_device_stats_unit
  apply_sysctl
  restart_ssr
  verify
  ROLLBACK_ON_ERROR=0
}

main() {
  case "${1:-}" in
    --check)
      check_mode
      ;;
    "")
      trap 'on_error $LINENO' ERR
      run_apply
      ;;
    *)
      fail "unknown option: $1"
      ;;
  esac
}

main "$@"
