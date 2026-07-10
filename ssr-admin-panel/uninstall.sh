#!/usr/bin/env bash
set -Eeuo pipefail

DEFAULT_PANEL_DIR="/opt/ssr-admin-panel"
DEFAULT_SSR_DIR="/usr/local/shadowsocksr"
DEFAULT_DEVICE_STATS_DIR="/var/lib/ssr-admin-panel"
DEFAULT_PANEL_LOG_DIR="/var/log/ssr-admin-panel"
DEFAULT_LEGACY_INIT_SCRIPT="/etc/init.d/ssrmu"
DEFAULT_FIREWALL_HELPER_DIR="/usr/local/libexec/ssr-panel"
DEFAULT_FIREWALL_CONFIG="/etc/default/ssr-panel-firewall"
DEFAULT_FIREWALL_STATE_DIR="/var/lib/ssr-panel-firewall"
MANAGED_MARKER=".ssr-panel-managed"
SYSTEMD_DIR="${SSR_ADMIN_SYSTEMD_DIR-/etc/systemd/system}"
DEFAULT_ADMIN_SERVICE="ssr-admin"
DEFAULT_DEVICE_STATS_SERVICE="ssr-device-stats"
DEFAULT_PANEL_USER="ssr-panel"
DEFAULT_PANEL_GROUP="ssr-panel"
DEFAULT_PANEL_SUDOERS="/etc/sudoers.d/ssr-panel"

PANEL_DIR="${SSR_ADMIN_PANEL_DIR-$DEFAULT_PANEL_DIR}"
SSR_DIR="${SSR_ADMIN_SSR_DIR-$DEFAULT_SSR_DIR}"
DEVICE_STATS_DIR="${SSR_DEVICE_STATS_DIR-$DEFAULT_DEVICE_STATS_DIR}"
PANEL_LOG_DIR="${SSR_ADMIN_LOG_DIR-$DEFAULT_PANEL_LOG_DIR}"
ADMIN_SERVICE="${SSR_ADMIN_SERVICE_NAME-$DEFAULT_ADMIN_SERVICE}"
DEVICE_STATS_SERVICE="${SSR_DEVICE_STATS_SERVICE_NAME-$DEFAULT_DEVICE_STATS_SERVICE}"
LEGACY_INIT_SCRIPT="$DEFAULT_LEGACY_INIT_SCRIPT"
FIREWALL_HELPER_DIR="$DEFAULT_FIREWALL_HELPER_DIR"
FIREWALL_CONFIG="$DEFAULT_FIREWALL_CONFIG"
FIREWALL_STATE_DIR="$DEFAULT_FIREWALL_STATE_DIR"
FIREWALL_STATE_FILE="${FIREWALL_STATE_DIR}/managed-ports.json"
PANEL_USER="$DEFAULT_PANEL_USER"
PANEL_GROUP="$DEFAULT_PANEL_GROUP"
PANEL_SUDOERS="${SSR_ADMIN_SUDOERS_PATH-$DEFAULT_PANEL_SUDOERS}"
ADMIN_HELPER="${FIREWALL_HELPER_DIR}/admin-helper"

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

collect_ssr_ports() {
  local database="${SSR_DIR}/mudb.json"
  local -a sources=()

  [[ ! -f "$database" || -L "$database" ]] || sources+=("$database")
  [[ ! -f "$FIREWALL_STATE_FILE" || -L "$FIREWALL_STATE_FILE" ]] || sources+=("$FIREWALL_STATE_FILE")
  [[ "${#sources[@]}" -gt 0 ]] || return 0
  command -v python3 >/dev/null 2>&1 || {
    log "python3 is unavailable; skipping firewall cleanup" >&2
    return 0
  }

  python3 - "${sources[@]}" <<'PY'
import json
import sys

ports = set()
for source in sys.argv[1:]:
    try:
        with open(source, encoding="utf-8") as handle:
            entries = json.load(handle)
    except (OSError, ValueError) as exc:
        print("warning: cannot read firewall ports from {}: {}".format(source, exc), file=sys.stderr)
        continue
    for entry in entries if isinstance(entries, list) else []:
        value = entry.get("port") if isinstance(entry, dict) else entry
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            port = value
        elif isinstance(value, str) and value.isdigit():
            port = int(value)
        else:
            continue
        if 1 <= port <= 65535:
            ports.add(port)

for port in sorted(ports):
    print(port)
PY
}

persist_firewall_rules() {
  if command -v netfilter-persistent >/dev/null 2>&1; then
    netfilter-persistent save >/dev/null 2>&1 || log "warning: failed to persist firewall cleanup"
    return
  fi

  if [[ -f /etc/sysconfig/iptables ]] && command -v iptables-save >/dev/null 2>&1; then
    iptables-save > /etc/sysconfig/iptables || log "warning: failed to persist IPv4 firewall cleanup"
    if [[ -f /etc/sysconfig/ip6tables ]] && command -v ip6tables-save >/dev/null 2>&1; then
      ip6tables-save > /etc/sysconfig/ip6tables || log "warning: failed to persist IPv6 firewall cleanup"
    fi
    return
  fi

  if [[ -f /etc/iptables.up.rules || -f "${SYSTEMD_DIR}/ssr-iptables-restore.service" ]]; then
    if command -v iptables-save >/dev/null 2>&1; then
      iptables-save > /etc/iptables.up.rules || log "warning: failed to persist IPv4 firewall cleanup"
    fi
    if command -v ip6tables-save >/dev/null 2>&1; then
      ip6tables-save > /etc/ip6tables.up.rules || log "warning: failed to persist IPv6 firewall cleanup"
    fi
  fi
}

cleanup_firewall_ports() {
  local ports="$1" port protocol changed=0

  [[ -n "$ports" ]] || return 0
  if command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1; then
    for port in $ports; do
      for protocol in tcp udp; do
        firewall-cmd --permanent --remove-port="${port}/${protocol}" >/dev/null 2>&1 || true
      done
    done
    firewall-cmd --reload >/dev/null 2>&1 || log "warning: failed to reload firewalld"
    return
  fi

  for port in $ports; do
    for protocol in tcp udp; do
      if command -v iptables >/dev/null 2>&1; then
        while iptables -C INPUT -m conntrack --ctstate NEW -p "$protocol" --dport "$port" -j ACCEPT 2>/dev/null; do
          iptables -D INPUT -m conntrack --ctstate NEW -p "$protocol" --dport "$port" -j ACCEPT || break
          changed=1
        done
      fi
      if command -v ip6tables >/dev/null 2>&1; then
        while ip6tables -C INPUT -m conntrack --ctstate NEW -p "$protocol" --dport "$port" -j ACCEPT 2>/dev/null; do
          ip6tables -D INPUT -m conntrack --ctstate NEW -p "$protocol" --dport "$port" -j ACCEPT || break
          changed=1
        done
      fi
    done
  done

  [[ "$changed" -eq 0 ]] || persist_firewall_rules
}

is_managed_legacy_init() {
  [[ -f "$LEGACY_INIT_SCRIPT" && ! -L "$LEGACY_INIT_SCRIPT" ]] || return 1
  grep -Fqx "# Managed by SSR_Panel" "$LEGACY_INIT_SCRIPT" && return 0
  grep -Fq "# Provides:          ssrmu" "$LEGACY_INIT_SCRIPT" &&
    grep -Fq "# Short-Description: ShadowsocksR manyuser service" "$LEGACY_INIT_SCRIPT"
}

cleanup_legacy_init() {
  [[ -e "$LEGACY_INIT_SCRIPT" || -L "$LEGACY_INIT_SCRIPT" ]] || return 0
  if ! is_managed_legacy_init; then
    log "leaving unrecognized legacy init script intact: $LEGACY_INIT_SCRIPT"
    return 0
  fi

  [[ ! -x "$LEGACY_INIT_SCRIPT" ]] || "$LEGACY_INIT_SCRIPT" stop >/dev/null 2>&1 || true
  if command -v update-rc.d >/dev/null 2>&1; then
    update-rc.d -f ssrmu remove >/dev/null 2>&1 || true
  elif command -v chkconfig >/dev/null 2>&1; then
    chkconfig --del ssrmu >/dev/null 2>&1 || true
  fi
  rm -f "$LEGACY_INIT_SCRIPT"
}

cleanup_managed_firewall_artifacts() {
  local marker

  marker="${FIREWALL_HELPER_DIR}/${MANAGED_MARKER}"
  if [[ -d "$FIREWALL_HELPER_DIR" && ! -L "$FIREWALL_HELPER_DIR" && -f "$marker" && ! -L "$marker" ]]; then
    rm -rf "$FIREWALL_HELPER_DIR"
  elif [[ -e "$FIREWALL_HELPER_DIR" || -L "$FIREWALL_HELPER_DIR" ]]; then
    log "leaving unrecognized firewall helper directory intact: $FIREWALL_HELPER_DIR"
  fi

  if [[ -f "$FIREWALL_CONFIG" && ! -L "$FIREWALL_CONFIG" ]] &&
    grep -Fqx "# Managed by SSR_Panel" "$FIREWALL_CONFIG"; then
    rm -f "$FIREWALL_CONFIG"
  elif [[ -e "$FIREWALL_CONFIG" || -L "$FIREWALL_CONFIG" ]]; then
    log "leaving unrecognized firewall config intact: $FIREWALL_CONFIG"
  fi

  marker="${FIREWALL_STATE_DIR}/${MANAGED_MARKER}"
  if [[ -d "$FIREWALL_STATE_DIR" && ! -L "$FIREWALL_STATE_DIR" && -f "$marker" && ! -L "$marker" ]]; then
    rm -rf "$FIREWALL_STATE_DIR"
  elif [[ -e "$FIREWALL_STATE_DIR" || -L "$FIREWALL_STATE_DIR" ]]; then
    log "leaving unrecognized firewall state directory intact: $FIREWALL_STATE_DIR"
  fi
}

cleanup_panel_privileges() {
  local marker="${FIREWALL_HELPER_DIR}/${MANAGED_MARKER}"

  if [[ -f "$PANEL_SUDOERS" && ! -L "$PANEL_SUDOERS" ]] &&
    grep -Fqx "# Managed by SSR_Panel" "$PANEL_SUDOERS"; then
    rm -f "$PANEL_SUDOERS"
  elif [[ -e "$PANEL_SUDOERS" || -L "$PANEL_SUDOERS" ]]; then
    log "leaving unrecognized sudoers file intact: $PANEL_SUDOERS"
  fi

  if [[ -f "$marker" && ! -L "$marker" && ( -e "$ADMIN_HELPER" || -L "$ADMIN_HELPER" ) ]]; then
    rm -f "$ADMIN_HELPER"
  elif [[ -e "$ADMIN_HELPER" || -L "$ADMIN_HELPER" ]]; then
    log "leaving unrecognized admin helper intact: $ADMIN_HELPER"
  fi
}

cleanup_panel_identity() {
  if [[ -d "$SSR_DIR" && ! -L "$SSR_DIR" ]]; then
    chgrp root "$SSR_DIR" "${SSR_DIR}/mudb.json" "${SSR_DIR}/ssserver.log" 2>/dev/null || true
    chmod g-s "$SSR_DIR" 2>/dev/null || true
  fi
  if id -u "$PANEL_USER" >/dev/null 2>&1 && command -v userdel >/dev/null 2>&1; then
    userdel "$PANEL_USER" >/dev/null 2>&1 || true
  fi
  if getent group "$PANEL_GROUP" >/dev/null 2>&1 && command -v groupdel >/dev/null 2>&1; then
    groupdel "$PANEL_GROUP" >/dev/null 2>&1 || true
  fi
}

log "disabling panel services"
stop_service "$ADMIN_SERVICE"
stop_service "$DEVICE_STATS_SERVICE"
cleanup_panel_privileges

if [[ "$REMOVE_SSR" -eq 1 ]]; then
  log "removing SSR service and directory"
  SSR_PORTS="$(collect_ssr_ports)" || {
    log "warning: failed to read SSR user ports; skipping firewall cleanup"
    SSR_PORTS=""
  }
  stop_service "ssr"
  if [[ "$KEEP_DATA" -ne 1 ]]; then
    cleanup_legacy_init
    cleanup_firewall_ports "$SSR_PORTS"
    cleanup_managed_firewall_artifacts
    rm -rf "$SSR_DIR"
  fi
else
  log "leaving SSR server files intact; pass --remove-ssr to remove them"
fi

systemctl daemon-reload >/dev/null 2>&1 || true

if [[ "$KEEP_DATA" -eq 1 ]]; then
  log "kept data directories because --keep-data was set"
else
  log "removing panel files and device stats data"
  rm -rf "$PANEL_DIR" "$DEVICE_STATS_DIR" "$PANEL_LOG_DIR"
  cleanup_panel_identity
fi

log "completed"
