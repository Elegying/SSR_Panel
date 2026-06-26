#!/usr/bin/env bash
set -Eeuo pipefail

PANEL_DIR="${ANYTLS_PANEL_DIR:-/opt/anytls-panel}"
SERVICE_NAME="${ANYTLS_SERVICE_NAME:-anytls-panel}"
CONFIRM=0
KEEP_DATA=0

usage() {
  cat <<'EOF'
Usage: bash uninstall.sh --yes [--keep-data]

Options:
  --yes        Required. Confirm removal.
  --keep-data  Keep the panel directory and database; only disable the service.
  -h, --help   Show this help.

Environment overrides:
  ANYTLS_PANEL_DIR, ANYTLS_SERVICE_NAME
EOF
}

log() {
  printf '[anytls-panel-uninstall] %s\n' "$*"
}

fail() {
  printf '[anytls-panel-uninstall] ERROR: %s\n' "$*" >&2
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

if [[ "$CONFIRM" -ne 1 && "${ANYTLS_UNINSTALL_CONFIRM:-}" != "yes" ]]; then
  usage
  fail "refusing to uninstall without --yes"
fi

log "disabling service: $SERVICE_NAME"
systemctl disable --now "$SERVICE_NAME" >/dev/null 2>&1 || true
rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload >/dev/null 2>&1 || true

if [[ "$KEEP_DATA" -eq 1 ]]; then
  log "kept panel directory because --keep-data was set: $PANEL_DIR"
else
  log "removing panel directory: $PANEL_DIR"
  rm -rf "$PANEL_DIR"
fi

log "completed"
