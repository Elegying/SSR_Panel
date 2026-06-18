#!/usr/bin/env bash
set -Eeuo pipefail

PANEL_DIR="${SSR_ADMIN_PANEL_DIR:-/opt/ssr-admin-panel}"
SSR_DIR="${SSR_ADMIN_SSR_DIR:-/usr/local/shadowsocksr}"
DEVICE_STATS_DIR="${SSR_DEVICE_STATS_DIR:-/var/lib/ssr-admin-panel}"
ADMIN_SERVICE="${SSR_ADMIN_SERVICE_NAME:-ssr-admin}"
DEVICE_STATS_SERVICE="${SSR_DEVICE_STATS_SERVICE_NAME:-ssr-device-stats}"

CONFIRM=0
KEEP_DATA=0
REMOVE_SSR=0

usage() {
  cat <<'EOF'
Usage: bash uninstall.sh --yes [--keep-data] [--remove-ssr]

Options:
  --yes         Required. Confirm removal.
  --keep-data   Keep panel files and device stats data; only disable services.
  --remove-ssr  Also remove /usr/local/shadowsocksr and ssr.service.
  -h, --help    Show this help.

Environment overrides:
  SSR_ADMIN_PANEL_DIR, SSR_ADMIN_SSR_DIR, SSR_DEVICE_STATS_DIR
  SSR_ADMIN_SERVICE_NAME, SSR_DEVICE_STATS_SERVICE_NAME
EOF
}

log() {
  printf '[ssr-admin-uninstall] %s\n' "$*"
}

fail() {
  printf '[ssr-admin-uninstall] ERROR: %s\n' "$*" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes)
      CONFIRM=1
      ;;
    --keep-data)
      KEEP_DATA=1
      ;;
    --remove-ssr)
      REMOVE_SSR=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "unknown option: $1"
      ;;
  esac
  shift
done

[[ "${EUID:-$(id -u)}" -eq 0 ]] || fail "run as root"

if [[ "$CONFIRM" -ne 1 && "${SSR_ADMIN_UNINSTALL_CONFIRM:-}" != "yes" ]]; then
  usage
  fail "refusing to uninstall without --yes"
fi

stop_service() {
  local service="$1"
  systemctl disable --now "$service" >/dev/null 2>&1 || true
  rm -f "/etc/systemd/system/${service}.service"
}

log "disabling panel services"
stop_service "$ADMIN_SERVICE"
stop_service "$DEVICE_STATS_SERVICE"

if [[ "$REMOVE_SSR" -eq 1 ]]; then
  log "removing SSR service and directory"
  systemctl disable --now ssr >/dev/null 2>&1 || true
  rm -f /etc/systemd/system/ssr.service
  [[ "$KEEP_DATA" -eq 1 ]] || rm -rf "$SSR_DIR"
else
  log "leaving SSR server files intact; pass --remove-ssr to remove them"
fi

systemctl daemon-reload >/dev/null 2>&1 || true

if [[ "$KEEP_DATA" -eq 1 ]]; then
  log "kept data directories because --keep-data was set"
else
  log "removing panel files and device stats data"
  rm -rf "$PANEL_DIR" "$DEVICE_STATS_DIR"
fi

log "completed"
