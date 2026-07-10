#!/usr/bin/env bash
set -Eeuo pipefail

PANEL_DIR="${SSR_ADMIN_PANEL_DIR:-/opt/ssr-admin-panel}"
MUDB_FILE="${SSR_ADMIN_MUDB_FILE:-/usr/local/shadowsocksr/mudb.json}"
SSR_LOG_FILE="${SSR_ADMIN_SSR_LOG_FILE:-/usr/local/shadowsocksr/ssserver.log}"
RUNTIME_DIR="${SSR_ADMIN_RUNTIME_DIR:-/var/lib/ssr-admin-panel}"
LOG_DIR="${SSR_ADMIN_LOG_DIR:-/var/log/ssr-admin-panel}"
PANEL_USER="ssr-panel"
PANEL_GROUP="ssr-panel"
HELPER_DIR="/usr/local/libexec/ssr-panel"
HELPER_PATH="/usr/local/libexec/ssr-panel/admin-helper"
SUDOERS_PATH="/etc/sudoers.d/ssr-panel"

if [ "${EUID}" -ne 0 ]; then
    echo "provision_panel_runtime.sh must run as root" >&2
    exit 1
fi

fail() {
    echo "provision_panel_runtime.sh: $*" >&2
    exit 1
}

[ -d "${PANEL_DIR}" ] && [ ! -L "${PANEL_DIR}" ] || fail "unsafe panel directory: ${PANEL_DIR}"
[ ! -L "${HELPER_DIR}" ] || fail "helper directory must not be a symlink"
[ ! -L "${SUDOERS_PATH}" ] || fail "sudoers path must not be a symlink"
[ -f "${PANEL_DIR}/scripts/admin_helper.py" ] && [ ! -L "${PANEL_DIR}/scripts/admin_helper.py" ] || \
    fail "unsafe admin helper source"
for runtime_path in "${RUNTIME_DIR}" "${LOG_DIR}"; do
    [ ! -L "${runtime_path}" ] || fail "runtime path must not be a symlink: ${runtime_path}"
done

if ! getent group "${PANEL_GROUP}" >/dev/null 2>&1; then
    groupadd --system "${PANEL_GROUP}"
fi

NOLOGIN_SHELL="$(command -v nologin 2>/dev/null || true)"
NOLOGIN_SHELL="${NOLOGIN_SHELL:-/sbin/nologin}"
if ! id -u "${PANEL_USER}" >/dev/null 2>&1; then
    useradd --system --gid "${PANEL_GROUP}" --home-dir /nonexistent --no-create-home \
        --shell "${NOLOGIN_SHELL}" "${PANEL_USER}"
else
    usermod --gid "${PANEL_GROUP}" --shell "${NOLOGIN_SHELL}" "${PANEL_USER}"
fi
usermod --groups "" "${PANEL_USER}"
[ "$(id -u "${PANEL_USER}")" -ne 0 ] || fail "panel user must not be root"
[ "$(getent group "${PANEL_GROUP}" | cut -d: -f3)" -ne 0 ] || fail "panel group must not be root"

install -d -o root -g root -m 0755 "${HELPER_DIR}"
install -o root -g root -m 0755 "${PANEL_DIR}/scripts/admin_helper.py" "${HELPER_PATH}"
printf 'Managed by SSR_Panel\n' > "${HELPER_DIR}/.ssr-panel-managed"

sudoers_tmp="$(mktemp /tmp/ssr-panel-sudoers.XXXXXX)"
trap 'rm -f "${sudoers_tmp}"' EXIT
cat > "${sudoers_tmp}" <<EOF
# Managed by SSR_Panel
${PANEL_USER} ALL=(root) NOPASSWD: ${HELPER_PATH} ssr-start, ${HELPER_PATH} ssr-stop, ${HELPER_PATH} ssr-restart, ${HELPER_PATH} firewall-sync, ${HELPER_PATH} mudb-commit, ${HELPER_PATH} panel-update
EOF
chmod 0440 "${sudoers_tmp}"
if command -v visudo >/dev/null 2>&1; then
    visudo -cf "${sudoers_tmp}" >/dev/null
fi
install -o root -g root -m 0440 "${sudoers_tmp}" "${SUDOERS_PATH}"

install -d -o root -g "${PANEL_GROUP}" -m 0770 \
    "${RUNTIME_DIR}" "${RUNTIME_DIR}/backups" "${LOG_DIR}"
touch "${LOG_DIR}/audit.log"
chown root:"${PANEL_GROUP}" "${LOG_DIR}/audit.log"
chmod 0660 "${LOG_DIR}/audit.log"
rm -f "${RUNTIME_DIR}/mudb.pending.json"

chown -R root:root "${PANEL_DIR}"
chmod -R go-w "${PANEL_DIR}"
if [ -f "${PANEL_DIR}/config.py" ]; then
    chown root:"${PANEL_GROUP}" "${PANEL_DIR}/config.py"
    chmod 0640 "${PANEL_DIR}/config.py"
fi
if [ -f "${MUDB_FILE}" ] && [ ! -L "${MUDB_FILE}" ]; then
    chgrp "${PANEL_GROUP}" "$(dirname "${MUDB_FILE}")"
    chmod g+rx,g-w,g+s "$(dirname "${MUDB_FILE}")"
    chown root:"${PANEL_GROUP}" "${MUDB_FILE}"
    chmod 0640 "${MUDB_FILE}"
fi
if [ -f "${SSR_LOG_FILE}" ] && [ ! -L "${SSR_LOG_FILE}" ]; then
    chown root:"${PANEL_GROUP}" "${SSR_LOG_FILE}"
    chmod 0640 "${SSR_LOG_FILE}"
fi
if [ -f "${RUNTIME_DIR}/device-stats.json" ]; then
    chown "${PANEL_USER}:${PANEL_GROUP}" "${RUNTIME_DIR}/device-stats.json"
    chmod 0660 "${RUNTIME_DIR}/device-stats.json"
fi
