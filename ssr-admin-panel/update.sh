#!/bin/bash

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

PANEL_DIR="${SSR_ADMIN_PANEL_DIR:-/opt/ssr-admin-panel}"
SSR_DIR="${SSR_ADMIN_SSR_DIR:-/usr/local/shadowsocksr}"
REPO_URL="${SSR_ADMIN_REPO_URL:-https://github.com/Elegying/SSR_Panel.git}"
TARGET_REF="${1:-${SSR_ADMIN_UPDATE_REF:-main}}"
REPO_SUBDIR="${SSR_ADMIN_REPO_SUBDIR:-ssr-admin-panel}"
SERVICE_NAME="${SSR_ADMIN_SERVICE_NAME:-ssr-admin}"
DEVICE_STATS_SERVICE_NAME="${SSR_DEVICE_STATS_SERVICE_NAME:-ssr-device-stats}"
DEVICE_STATS_FILE="${SSR_DEVICE_STATS_FILE:-/var/lib/ssr-admin-panel/device-stats.json}"
DEVICE_STATS_INTERVAL="${SSR_DEVICE_STATS_INTERVAL:-15}"
DEVICE_STATS_WINDOW="${SSR_DEVICE_STATS_WINDOW:-900}"
APPLY_SERVER_OPTIMIZATION="${SSR_ADMIN_APPLY_SERVER_OPTIMIZATION:-1}"
PYTHON3_BIN="${PYTHON3_BIN:-$(command -v python3 2>/dev/null || echo /usr/bin/python3)}"
TMP_CLONE_DIR=""
STATUS_FILE="${SSR_ADMIN_UPDATE_STATUS_FILE:-}"
BACKUP_DIR=""
ROLLBACK_ATTEMPTED=0
ROLLBACK_SUCCESS=0

cleanup() {
    if [ -n "${TMP_CLONE_DIR}" ] && [ -d "${TMP_CLONE_DIR}" ]; then
        rm -rf "${TMP_CLONE_DIR}"
    fi
}

trap cleanup EXIT

repo_source_dir() {
    local repo_root="$1"
    if [ -n "${REPO_SUBDIR}" ]; then
        printf '%s/%s\n' "${repo_root}" "${REPO_SUBDIR}"
    else
        printf '%s\n' "${repo_root}"
    fi
}

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

python_version_lt() {
    "${PYTHON3_BIN}" - "$1" "$2" <<'PY' &>/dev/null
import sys

major = int(sys.argv[1])
minor = int(sys.argv[2])
raise SystemExit(0 if sys.version_info < (major, minor) else 1)
PY
}

python_version_ge() {
    "${PYTHON3_BIN}" - "$1" "$2" <<'PY' &>/dev/null
import sys

major = int(sys.argv[1])
minor = int(sys.argv[2])
raise SystemExit(0 if sys.version_info >= (major, minor) else 1)
PY
}

write_status() {
    local phase="$1"
    local message="$2"
    local exit_code="${3:-}"

    if [ -z "${STATUS_FILE}" ]; then
        return 0
    fi

    STATUS_FILE="${STATUS_FILE}" PHASE="${phase}" MESSAGE="${message}" EXIT_CODE="${exit_code}" \
    CURRENT_VERSION="$(read_version "${PANEL_DIR}")" BACKUP_DIR="${BACKUP_DIR}" \
    ROLLBACK_ATTEMPTED="${ROLLBACK_ATTEMPTED}" ROLLBACK_SUCCESS="${ROLLBACK_SUCCESS}" \
    "${PYTHON3_BIN}" <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

path = Path(os.environ["STATUS_FILE"])
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        payload = {}
except (FileNotFoundError, json.JSONDecodeError, OSError):
    payload = {}

exit_code = os.environ.get("EXIT_CODE", "")
payload.update(
    {
        "in_progress": exit_code == "",
        "phase": os.environ.get("PHASE", ""),
        "message": os.environ.get("MESSAGE", ""),
        "current_version": os.environ.get("CURRENT_VERSION", "unknown"),
        "backup_dir": os.environ.get("BACKUP_DIR", ""),
        "rollback_attempted": os.environ.get("ROLLBACK_ATTEMPTED") == "1",
        "rollback_success": os.environ.get("ROLLBACK_SUCCESS") == "1",
    }
)
if exit_code != "":
    payload["finished_at"] = datetime.now(timezone.utc).isoformat()
    payload["last_exit_code"] = int(exit_code)

path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
PY
}

copy_tree() {
    local source_dir="$1"
    local target_dir="$2"
    local mode="${3:-sync}"

    COPY_SOURCE="${source_dir}" COPY_TARGET="${target_dir}" COPY_MODE="${mode}" "${PYTHON3_BIN}" <<'PY'
import os
import shutil
from pathlib import Path

source = Path(os.environ["COPY_SOURCE"])
target = Path(os.environ["COPY_TARGET"])
mode = os.environ.get("COPY_MODE", "sync")
exclude = {"backups", "__pycache__", "venv"}
if mode == "sync" and not (source / "config.py").exists():
    exclude.add("config.py")


def remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def copy_dir(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    source_items = {item.name: item for item in src.iterdir() if item.name not in exclude}

    if mode == "sync":
        for existing in list(dst.iterdir()):
            if existing.name in exclude:
                continue
            if existing.name not in source_items:
                remove_path(existing)

    for name, src_item in source_items.items():
        dst_item = dst / name
        if src_item.is_dir() and not src_item.is_symlink():
            if dst_item.exists() and not dst_item.is_dir():
                remove_path(dst_item)
            copy_dir(src_item, dst_item)
        else:
            if dst_item.exists() and dst_item.is_dir():
                remove_path(dst_item)
            dst_item.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_item, dst_item, follow_symlinks=False)


copy_dir(source, target)
PY
}

create_full_backup() {
    BACKUP_DIR="${PANEL_DIR}/backups/update_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "${BACKUP_DIR}/app"
    copy_tree "${PANEL_DIR}" "${BACKUP_DIR}/app" "copy"
}

harden_sensitive_files() {
    chmod 600 "${PANEL_DIR}/config.py" "${SSR_DIR}/mudb.json" 2>/dev/null || true
}

restore_backup() {
    if [ -z "${BACKUP_DIR}" ] || [ ! -d "${BACKUP_DIR}/app" ]; then
        return 1
    fi

    ROLLBACK_ATTEMPTED=1
    echo -e "${YELLOW}正在恢复上一版应用文件...${NC}"
    write_status "rollback" "新版本启动失败，正在恢复上一版"
    copy_tree "${BACKUP_DIR}/app" "${PANEL_DIR}" "sync"
    harden_sensitive_files
    chmod +x "${PANEL_DIR}/update.sh" "${PANEL_DIR}/install.sh" "${PANEL_DIR}/install-all.sh" "${PANEL_DIR}/uninstall.sh" "${PANEL_DIR}/scripts/collect_device_stats.py" 2>/dev/null || true
    systemctl daemon-reload || true
    if systemctl restart "${SERVICE_NAME}" && systemctl is-active --quiet "${SERVICE_NAME}"; then
        ROLLBACK_SUCCESS=1
        echo -e "${GREEN}已恢复上一版并重启服务${NC}"
        return 0
    fi

    echo -e "${RED}回滚后服务仍未启动，请检查日志${NC}"
    return 1
}

ensure_python_deps() {
    local req_file="${PANEL_DIR}/requirements.txt"
    if [ ! -f "${req_file}" ]; then
        return 0
    fi

    local pip_bin=""
    if "${PYTHON3_BIN}" -m pip --version &>/dev/null; then
        pip_bin="__PYTHON3_M_PIP__"
    elif command -v pip3 &>/dev/null; then
        pip_bin="pip3"
    elif command -v pip &>/dev/null; then
        pip_bin="pip"
    else
        echo -e "${YELLOW}未检测到 pip，尝试安装...${NC}"
        if [ -f /etc/debian_version ] || [ -f /etc/lsb-release ]; then
            apt-get install -y -qq python3-pip 2>/dev/null || \
            { apt-get update -qq && apt-get install -y -qq python3-pip; }
        elif [ -f /etc/redhat-release ]; then
            yum install -y -q python3-pip 2>/dev/null || true
        fi
        "${PYTHON3_BIN}" -m ensurepip --upgrade 2>/dev/null || true
        if "${PYTHON3_BIN}" -m pip --version &>/dev/null; then
            pip_bin="__PYTHON3_M_PIP__"
        else
            echo -e "${RED}pip 安装失败，跳过 Python 依赖安装${NC}"
            return 1
        fi
    fi

    run_pip_install() {
        if [ "${pip_bin}" = "__PYTHON3_M_PIP__" ]; then
            "${PYTHON3_BIN}" -m pip install "$@"
        else
            "${pip_bin}" install "$@"
        fi
    }

    # 根据 Python 版本选择兼容的依赖版本
    local py_ver
    py_ver=$("${PYTHON3_BIN}" -c "import sys; print('{}.{}'.format(sys.version_info.major, sys.version_info.minor))" 2>/dev/null || echo "3.8")
    local pip_install_opts=(--no-input --disable-pip-version-check)
    local pip_pkgs=(-r "${req_file}")

    if python_version_ge 3 11; then
        pip_install_opts+=(--break-system-packages)
    fi

    if python_version_lt 3 7; then
        echo -e "${YELLOW}Python ${py_ver} 检测到，使用 Python 3.6 兼容版本...${NC}"
        pip_pkgs=(
            'Flask>=2.0,<2.1'
            'Werkzeug>=2.0,<2.1'
            'Jinja2>=3.0,<3.1'
            'MarkupSafe>=2.0,<2.1'
            'itsdangerous>=2.0,<2.1'
            'click>=8.0,<8.1'
            'Flask-Limiter>=1.5,<2.0'
            'waitress>=2.0,<2.1'
        )
    elif python_version_lt 3 8; then
        echo -e "${YELLOW}Python ${py_ver} 检测到，使用 Python 3.7 兼容版本...${NC}"
        pip_pkgs=(
            'Flask>=2.2,<2.3'
            'Flask-Limiter>=3.0,<3.5.1'
            'waitress>=2.1,<2.2'
        )
    fi

    echo -e "${CYAN}正在安装 Python 依赖...${NC}"
    if ! run_pip_install "${pip_install_opts[@]}" --prefer-binary -q "${pip_pkgs[@]}" 2>/dev/null; then
        echo -e "${YELLOW}pip install 失败，尝试逐包安装...${NC}"
        if python_version_lt 3 8; then
            for pkg in "${pip_pkgs[@]}"; do
                run_pip_install "${pip_install_opts[@]}" --prefer-binary -q "${pkg}" 2>/dev/null || true
            done
        elif [ -f "${req_file}" ]; then
            while IFS= read -r pkg; do
                pkg="$(echo "${pkg}" | sed 's/#.*//;s/^[[:space:]]*//;s/[[:space:]]*$//')"
                [ -z "${pkg}" ] && continue
                run_pip_install "${pip_install_opts[@]}" --prefer-binary -q "${pkg}" 2>/dev/null || true
            done < "${req_file}"
        fi
    fi

    # 验证关键依赖
    if ! "${PYTHON3_BIN}" -c "import flask" &>/dev/null; then
        echo -e "${RED}Flask 导入失败，尝试系统包回退...${NC}"
        if [ -f /etc/debian_version ] || [ -f /etc/lsb-release ]; then
            apt-get install -y -qq python3-flask 2>/dev/null || true
        fi
    fi
    if ! "${PYTHON3_BIN}" -c "import flask_limiter" &>/dev/null; then
        echo -e "${RED}Flask-Limiter 导入失败，尝试系统包回退...${NC}"
        if [ -f /etc/debian_version ] || [ -f /etc/lsb-release ]; then
            apt-get install -y -qq python3-flask-limiter 2>/dev/null || true
        fi
    fi

    if ! "${PYTHON3_BIN}" -c "import waitress" &>/dev/null; then
        echo -e "${RED}Waitress 导入失败，尝试 pip 单独安装...${NC}"
        run_pip_install "${pip_install_opts[@]}" waitress -q 2>/dev/null || true
    fi

    if ! "${PYTHON3_BIN}" -c "import flask; import flask_limiter; import waitress" &>/dev/null; then
        echo -e "${RED}Python 依赖安装失败，服务可能无法启动${NC}"
        return 1
    fi

    echo -e "${GREEN}✓ Python 依赖已就绪${NC}"
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

install_or_update_panel_service() {
    cat > /etc/systemd/system/${SERVICE_NAME}.service <<SERVICE
[Unit]
Description=SSR Admin Panel
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${PANEL_DIR}
ExecStart=${PYTHON3_BIN} -m waitress --host=0.0.0.0 --port=5000 app:app
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
RestrictSUIDSGID=true
LockPersonality=true
UMask=0077

[Install]
WantedBy=multi-user.target
SERVICE

    systemctl enable "${SERVICE_NAME}" >/dev/null 2>&1 || true
}

apply_server_optimization() {
    local optimizer="${PANEL_DIR}/scripts/optimize_server.sh"
    if [ "${APPLY_SERVER_OPTIMIZATION}" != "1" ]; then
        echo -e "${YELLOW}SSR_ADMIN_APPLY_SERVER_OPTIMIZATION=0，跳过 SSR 服务器优化${NC}"
        return 0
    fi
    if [ ! -d "${SSR_DIR}" ] || [ ! -f "${optimizer}" ]; then
        return 0
    fi

    chmod +x "${optimizer}" 2>/dev/null || true
    echo -e "${CYAN}检测到 SSR，正在应用服务器优化...${NC}"
    if ! bash "${optimizer}"; then
        echo -e "${YELLOW}SSR 服务器优化未完全成功，请稍后手动执行: bash ${optimizer}${NC}"
    fi
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
write_status "clone" "正在下载新版本"
git clone --depth 1 --branch "${TARGET_REF}" "${REPO_URL}" "${TMP_CLONE_DIR}" -q
SOURCE_DIR="$(repo_source_dir "${TMP_CLONE_DIR}")"
if [ ! -f "${SOURCE_DIR}/app.py" ]; then
    echo -e "${RED}Project files not found: ${SOURCE_DIR}${NC}"
    write_status "failed" "Project files not found: ${SOURCE_DIR}" "1"
    exit 1
fi

NEW_VERSION="$(read_version "${SOURCE_DIR}")"
NEW_REVISION="$(git -C "${TMP_CLONE_DIR}" rev-parse --short HEAD 2>/dev/null || echo "")"
harden_sensitive_files
write_status "backup" "正在备份当前版本"
create_full_backup
echo -e "${CYAN}完整备份:${NC} ${YELLOW}${BACKUP_DIR}${NC}"

write_status "sync" "正在同步新版本"
copy_tree "${SOURCE_DIR}" "${PANEL_DIR}" "sync"
harden_sensitive_files

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

chmod +x "${PANEL_DIR}/update.sh" "${PANEL_DIR}/install.sh" "${PANEL_DIR}/install-all.sh" "${PANEL_DIR}/uninstall.sh" "${PANEL_DIR}/scripts/collect_device_stats.py" "${PANEL_DIR}/scripts/optimize_server.sh" 2>/dev/null || true

if [ -d "${SSR_DIR}" ]; then
    "${PYTHON3_BIN}" "${PANEL_DIR}/scripts/patch_ssr_python_compat.py" "${SSR_DIR}"
fi

write_status "deps" "正在安装 Python 依赖"
ensure_python_deps

write_status "restart" "正在重启服务"
systemctl daemon-reload
install_or_restart_device_stats_service
apply_server_optimization
install_or_update_panel_service
systemctl daemon-reload
if ! systemctl restart "${SERVICE_NAME}"; then
    echo -e "${RED}更新后服务重启命令失败${NC}"
    restore_backup || true
    write_status "failed" "更新后服务重启失败，已尝试回滚" "1"
    journalctl -u "${SERVICE_NAME}" -n 50 --no-pager || true
    exit 1
fi

if systemctl is-active --quiet "${SERVICE_NAME}"; then
    echo -e "${GREEN}更新完成${NC}"
    echo -e "${CYAN}新版本:${NC} ${YELLOW}${NEW_VERSION}${NC}"
    echo -e "${CYAN}完整备份:${NC} ${YELLOW}${BACKUP_DIR}${NC}"
    write_status "done" "更新完成，服务已重启" "0"
else
    echo -e "${RED}更新后服务启动失败，开始自动回滚${NC}"
    restore_backup || true
    write_status "failed" "更新后服务启动失败，已尝试回滚" "1"
    journalctl -u "${SERVICE_NAME}" -n 50 --no-pager || true
    exit 1
fi
