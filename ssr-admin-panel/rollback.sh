#!/bin/bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
VERSION_FILE="${SCRIPT_DIR}/VERSION"
UPDATE_SCRIPT="${SCRIPT_DIR}/update.sh"
ASSUME_YES=0

usage() {
    echo "Usage: bash rollback.sh [--yes]"
}

for argument in "$@"; do
    case "${argument}" in
        -y|--yes) ASSUME_YES=1 ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            usage >&2
            exit 2
            ;;
    esac
done

if [ "${EUID}" -ne 0 ] && [ "${SSR_ADMIN_SKIP_ROOT_CHECK:-0}" != "1" ]; then
    echo "请使用 root 权限执行回滚" >&2
    exit 1
fi

if [ ! -f "${VERSION_FILE}" ] || [ ! -f "${UPDATE_SCRIPT}" ]; then
    echo "回滚包不完整：缺少 VERSION 或 update.sh" >&2
    exit 1
fi

VERSION="$(tr -d '\r\n' < "${VERSION_FILE}")"
case "${VERSION}" in
    ''|*[!0-9.]*)
        echo "回滚包版本无效: ${VERSION}" >&2
        exit 1
        ;;
esac
TAG="v${VERSION}"

if [ "${ASSUME_YES}" -ne 1 ]; then
    if [ ! -t 0 ]; then
        echo "非交互模式请添加 --yes" >&2
        exit 1
    fi
    read -r -p "将面板回滚到 ${TAG}，继续？[y/N]: " answer
    case "${answer}" in
        y|Y|yes|YES) ;;
        *) echo "已取消"; exit 0 ;;
    esac
fi

echo "开始从本地发布包回滚到 ${TAG}；失败时将自动恢复现有版本。"
export SSR_ADMIN_UPDATE_SOURCE_DIR="${SCRIPT_DIR}"
export SSR_ADMIN_UPDATE_REVISION="${TAG}"
exec bash "${UPDATE_SCRIPT}" "${TAG}"
