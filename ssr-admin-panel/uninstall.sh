#!/usr/bin/env bash
set -Eeuo pipefail

DEFAULT_PANEL_DIR="/opt/ssr-admin-panel"
DEFAULT_SSR_DIR="/usr/local/shadowsocksr"
DEFAULT_DEVICE_STATS_DIR="/var/lib/ssr-admin-panel"
MANAGED_MARKER=".ssr-panel-managed"
SYSTEMD_DIR="${SSR_ADMIN_SYSTEMD_DIR-/etc/systemd/system}"
DEFAULT_ADMIN_SERVICE="ssr-admin"
DEFAULT_DEVICE_STATS_SERVICE="ssr-device-stats"

PANEL_DIR="${SSR_ADMIN_PANEL_DIR-$DEFAULT_PANEL_DIR}"
SSR_DIR="${SSR_ADMIN_SSR_DIR-$DEFAULT_SSR_DIR}"
DEVICE_STATS_DIR="${SSR_DEVICE_STATS_DIR-$DEFAULT_DEVICE_STATS_DIR}"
ADMIN_SERVICE="${SSR_ADMIN_SERVICE_NAME-$DEFAULT_ADMIN_SERVICE}"
DEVICE_STATS_SERVICE="${SSR_DEVICE_STATS_SERVICE_NAME-$DEFAULT_DEVICE_STATS_SERVICE}"

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
  SSR_ADMIN_SERVICE_NAME, SSR_DEVICE_STATS_SERVICE_NAME, SSR_ADMIN_SYSTEMD_DIR
EOF
}

log() {
  printf '[ssr-admin-uninstall] %s\n' "$*"
}

fail() {
  printf '[ssr-admin-uninstall] ERROR: %s\n' "$*" >&2
  exit 1
}

validate_service_name() {
  local service="$1"
  [[ "$service" =~ ^[A-Za-z0-9_.@-]+$ ]] || fail "invalid service name: $service"
}

validate_custom_service_unit() {
  local service="$1" default_service="$2"
  local unit="${SYSTEMD_DIR}/${service}.service"

  [[ "$service" == "$default_service" ]] && return 0
  [[ -f "$unit" && ! -L "$unit" ]] || fail "custom service unit is missing or unsafe: $unit"
  grep -Fqx "# Managed by SSR_Panel" "$unit" || fail "custom service unit is not managed by SSR_Panel: $unit"
}

normalize_absolute_path() {
  local path="$1"
  local part normalized=""
  local -a parts

  IFS='/' read -r -a parts <<< "$path"
  for part in "${parts[@]}"; do
    case "$part" in
      ""|.)
        ;;
      ..)
        normalized="${normalized%/*}"
        ;;
      *)
        normalized="${normalized}/${part}"
        ;;
    esac
  done
  printf '%s\n' "${normalized:-/}"
}

is_critical_system_dir() {
  case "$1" in
    /|/Applications|/Library|/System|/Volumes|/bin|/boot|/dev|/etc|/home|/lib|/lib64|/media|/mnt|/opt|/private|/proc|/root|/run|/sbin|/srv|/sys|/tmp|/usr|/usr/local|/var|/var/lib|/var/tmp)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

validate_no_symlink_components() {
  local label="$1" path="$2"
  local part current=""
  local -a parts
  local IFS='/'

  read -r -a parts <<< "$path"
  for part in "${parts[@]}"; do
    [[ -n "$part" ]] || continue
    current="${current}/${part}"
    [[ ! -L "$current" ]] || fail "$label must not traverse symlinks: $current"
  done
}

validate_delete_dir() {
  local label="$1" path="$2" default_path="$3"
  local normalized physical marker

  [[ -n "$path" ]] || fail "$label must not be empty"
  [[ "$path" == /* ]] || fail "$label must be an absolute path"

  normalized="$(normalize_absolute_path "$path")"
  is_critical_system_dir "$normalized" && fail "refusing to remove critical system directory: $normalized"
  validate_no_symlink_components "$label" "$normalized"
  [[ ! -e "$path" || -d "$path" ]] || fail "$label must be a directory: $normalized"

  if [[ -d "$path" ]]; then
    physical="$(cd -P -- "$path" 2>/dev/null && pwd -P)" || fail "cannot resolve $label: $normalized"
    [[ "$physical" == "$normalized" ]] || fail "$label must not traverse symlinks"
  elif [[ "$normalized" != "$default_path" ]]; then
    fail "custom $label does not exist: $normalized"
  fi

  if [[ "$normalized" != "$default_path" ]]; then
    marker="${normalized}/${MANAGED_MARKER}"
    [[ -f "$marker" && ! -L "$marker" ]] || fail "custom $label is missing marker: $marker"
  fi

  printf '%s\n' "$normalized"
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

validate_service_name "$ADMIN_SERVICE"
validate_service_name "$DEVICE_STATS_SERVICE"
validate_service_name "ssr"
[[ "$SYSTEMD_DIR" == /* ]] || fail "systemd directory must be an absolute path"
[[ "$ADMIN_SERVICE" != "ssr" ]] || fail "panel service name is reserved: ssr"
[[ "$DEVICE_STATS_SERVICE" != "ssr" ]] || fail "device stats service name is reserved: ssr"
[[ "$ADMIN_SERVICE" != "$DEVICE_STATS_SERVICE" ]] || fail "panel and device stats services must be different"
validate_custom_service_unit "$ADMIN_SERVICE" "$DEFAULT_ADMIN_SERVICE"
validate_custom_service_unit "$DEVICE_STATS_SERVICE" "$DEFAULT_DEVICE_STATS_SERVICE"

PANEL_DIR="$(validate_delete_dir "panel directory" "$PANEL_DIR" "$DEFAULT_PANEL_DIR")"
DEVICE_STATS_DIR="$(validate_delete_dir "device stats directory" "$DEVICE_STATS_DIR" "$DEFAULT_DEVICE_STATS_DIR")"
if [[ "$REMOVE_SSR" -eq 1 ]]; then
  SSR_DIR="$(validate_delete_dir "SSR directory" "$SSR_DIR" "$DEFAULT_SSR_DIR")"
fi

stop_service() {
  local service="$1"
  systemctl disable --now -- "$service" >/dev/null 2>&1 || true
  rm -f "${SYSTEMD_DIR}/${service}.service"
}

log "disabling panel services"
stop_service "$ADMIN_SERVICE"
stop_service "$DEVICE_STATS_SERVICE"

if [[ "$REMOVE_SSR" -eq 1 ]]; then
  log "removing SSR service and directory"
  stop_service "ssr"
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
