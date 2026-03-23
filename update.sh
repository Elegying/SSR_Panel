#!/bin/bash

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

PANEL_DIR="${SSR_ADMIN_PANEL_DIR:-/opt/ssr-admin-panel}"
REPO_URL="${SSR_ADMIN_REPO_URL:-https://github.com/Elegying/ssr-admin-panel.git}"
TARGET_REF="${1:-${SSR_ADMIN_UPDATE_REF:-main}}"
SERVICE_NAME="${SSR_ADMIN_SERVICE_NAME:-ssr-admin}"
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

CURRENT_VERSION="$(read_version "${PANEL_DIR}")"
echo -e "${CYAN}当前版本:${NC} ${YELLOW}${CURRENT_VERSION}${NC}"
echo -e "${CYAN}更新来源:${NC} ${YELLOW}${REPO_URL} (${TARGET_REF})${NC}"

TMP_CLONE_DIR="$(mktemp -d /tmp/ssr-admin-panel-update.XXXXXX)"
git clone --depth 1 --branch "${TARGET_REF}" "${REPO_URL}" "${TMP_CLONE_DIR}" -q

NEW_VERSION="$(read_version "${TMP_CLONE_DIR}")"
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

chmod +x "${PANEL_DIR}/update.sh" "${PANEL_DIR}/install.sh" "${PANEL_DIR}/install-all.sh" 2>/dev/null || true

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
