#!/bin/bash

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

PANEL_DIR="${SSR_ADMIN_PANEL_DIR:-/opt/ssr-admin-panel}"
SSR_DIR="${SSR_ADMIN_SSR_DIR:-/usr/local/shadowsocksr}"
REPO_URL="${SSR_ADMIN_REPO_URL:-https://github.com/Elegying/ssr-admin-panel.git}"
TARGET_REF="${1:-${SSR_ADMIN_UPDATE_REF:-main}}"
SERVICE_NAME="${SSR_ADMIN_SERVICE_NAME:-ssr-admin}"
DEVICE_STATS_SERVICE_NAME="${SSR_DEVICE_STATS_SERVICE_NAME:-ssr-device-stats}"
DEVICE_STATS_FILE="${SSR_DEVICE_STATS_FILE:-/var/lib/ssr-admin-panel/device-stats.json}"
DEVICE_STATS_INTERVAL="${SSR_DEVICE_STATS_INTERVAL:-15}"
DEVICE_STATS_WINDOW="${SSR_DEVICE_STATS_WINDOW:-900}"
PYTHON3_BIN="${PYTHON3_BIN:-$(command -v python3 2>/dev/null || echo /usr/bin/python3)}"
TMP_CLONE_DIR=""

cleanup() {
    if [ -n "${TMP_CLONE_DIR}" ] && [ -d "${TMP_CLONE_DIR}" ]; then
        rm -rf "${TMP_CLONE_DIR}"
    fi
}

trap cleanup EXIT

read_version() {
    local target_dir="$1"
    if [ -f "${target_dir}/VERSION" ]; then
        tr -d '\r\n' < "${target_dir}/VERSION"
        return
    fi

    if [ -d "${target_dir}/.git" ]; then
        git -C "${target_dir}" rev-parse --short HEAD 2>/dev/null || echo "unknown"
        return
    fi

    echo "unknown"
}

install_or_restart_device_stats_service() {
    local stats_script="${PANEL_DIR}/scripts/collect_device_stats.py"
    if [ ! -f "${stats_script}" ]; then
        return 0
    fi

    chmod +x "${stats_script}" 2>/dev/null || true
    mkdir -p "$(dirname "${DEVICE_STATS_FILE}")"
    cat > /etc/systemd/system/${DEVICE_STATS_SERVICE_NAME}.service <<SERVICE
[Unit]
Description=SSR Device Stats Collector
After=network.target

[Service]
Type=simple
User=root
ExecStart=${PYTHON3_BIN} ${stats_script} --mudb ${SSR_DIR}/mudb.json --output ${DEVICE_STATS_FILE} --interval ${DEVICE_STATS_INTERVAL} --window ${DEVICE_STATS_WINDOW} --watch
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

    systemctl enable "${DEVICE_STATS_SERVICE_NAME}" >/dev/null 2>&1 || true
    systemctl restart "${DEVICE_STATS_SERVICE_NAME}" || true
}

if [ "${1:-}" = "--version" ]; then
    read_version "${PANEL_DIR}"
    exit 0
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}      SSR Admin Panel 更新脚本${NC}"
echo -e "${GREEN}========================================${NC}"

if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}请使用 root 权限运行此脚本${NC}"
    exit 1
fi

if [ ! -d "${PANEL_DIR}" ]; then
    echo -e "${RED}未找到面板目录: ${PANEL_DIR}${NC}"
    exit 1
fi

if ! command -v git >/dev/null 2>&1; then
    echo -e "${RED}未检测到 git，请先安装 git 后再更新${NC}"
    exit 1
fi

if [ ! -x "${PYTHON3_BIN}" ]; then
    echo -e "${RED}未检测到可用的 python3，可执行路径: ${PYTHON3_BIN}${NC}"
    exit 1
fi

if [ -d "${SSR_DIR}" ]; then
    echo -e "${CYAN}检测到 SSR 目录，应用 Python 兼容修复...${NC}"
fi

CURRENT_VERSION="$(read_version "${PANEL_DIR}")"
echo -e "${CYAN}当前版本:${NC} ${YELLOW}${CURRENT_VERSION}${NC}"
echo -e "${CYAN}更新来源:${NC} ${YELLOW}${REPO_URL} (${TARGET_REF})${NC}"

TMP_CLONE_DIR="$(mktemp -d /tmp/ssr-admin-panel-update.XXXXXX)"
git clone --depth 1 --branch "${TARGET_REF}" "${REPO_URL}" "${TMP_CLONE_DIR}" -q

NEW_VERSION="$(read_version "${TMP_CLONE_DIR}")"
NEW_REVISION="$(git -C "${TMP_CLONE_DIR}" rev-parse --short HEAD 2>/dev/null || echo "")"
BACKUP_DIR="${PANEL_DIR}/backups/update_$(date +%Y%m%d_%H%M%S)"
mkdir -p "${BACKUP_DIR}"

if [ -f "${PANEL_DIR}/config.py" ]; then
    cp "${PANEL_DIR}/config.py" "${BACKUP_DIR}/config.py"
fi

SYNC_SOURCE="${TMP_CLONE_DIR}" SYNC_TARGET="${PANEL_DIR}" "${PYTHON3_BIN}" <<'PY'
import os
import shutil
from pathlib import Path

source = Path(os.environ["SYNC_SOURCE"])
target = Path(os.environ["SYNC_TARGET"])
exclude = {".git", "backups", "config.py", "__pycache__"}


def remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def sync_dir(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    source_items = {item.name: item for item in src.iterdir() if item.name not in exclude}

    for existing in list(dst.iterdir()):
        if existing.name in exclude:
            continue
        if existing.name not in source_items:
            remove_path(existing)

    for name, src_item in source_items.items():
        dst_item = dst / name
        if src_item.is_dir():
            if dst_item.exists() and not dst_item.is_dir():
                remove_path(dst_item)
            sync_dir(src_item, dst_item)
        else:
            if dst_item.exists() and dst_item.is_dir():
                remove_path(dst_item)
            dst_item.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_item, dst_item)


sync_dir(source, target)
PY

PANEL_BUILD_INFO_FILE="${PANEL_DIR}/.panel-build.json"
PANEL_BUILD_VERSION="${NEW_VERSION}" PANEL_BUILD_REVISION="${NEW_REVISION}" PANEL_BUILD_INFO_FILE="${PANEL_BUILD_INFO_FILE}" "${PYTHON3_BIN}" <<'PY'
import json
import os
from pathlib import Path

version = os.environ.get("PANEL_BUILD_VERSION", "").strip() or "unknown"
revision = os.environ.get("PANEL_BUILD_REVISION", "").strip()
display_version = version if not revision or revision == version or revision in version else f"{version} ({revision})"
Path(os.environ["PANEL_BUILD_INFO_FILE"]).write_text(
    json.dumps(
        {
            "version": version,
            "revision": revision,
            "display_version": display_version,
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)
PY

chmod +x "${PANEL_DIR}/update.sh" "${PANEL_DIR}/install.sh" "${PANEL_DIR}/install-all.sh" "${PANEL_DIR}/scripts/collect_device_stats.py" 2>/dev/null || true

if [ -d "${SSR_DIR}" ]; then
    "${PYTHON3_BIN}" "${PANEL_DIR}/scripts/patch_ssr_python_compat.py" "${SSR_DIR}"
fi

systemctl daemon-reload
install_or_restart_device_stats_service
systemctl daemon-reload
systemctl restart "${SERVICE_NAME}"

if systemctl is-active --quiet "${SERVICE_NAME}"; then
    echo -e "${GREEN}更新完成${NC}"
    echo -e "${CYAN}新版本:${NC} ${YELLOW}${NEW_VERSION}${NC}"
    echo -e "${CYAN}配置备份:${NC} ${YELLOW}${BACKUP_DIR}${NC}"
else
    echo -e "${RED}更新后服务启动失败，请检查日志${NC}"
    echo -e "${CYAN}配置备份:${NC} ${YELLOW}${BACKUP_DIR}${NC}"
    journalctl -u "${SERVICE_NAME}" -n 50 --no-pager || true
    exit 1
fi
