#!/usr/bin/env python3
import base64
import gzip
import hmac
import json
import os
import secrets
import shutil
import string
import subprocess
import sys
import tempfile
import time
from collections import deque
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Flask, Response, jsonify, redirect, render_template, request, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
except ImportError:
    def get_remote_address():
        return request.remote_addr or "127.0.0.1"

    class Limiter:
        def __init__(self, *args, **kwargs):
            pass

        def limit(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator

try:
    import fcntl
except ImportError:
    class _FcntlCompat:
        LOCK_SH = 1
        LOCK_EX = 2
        LOCK_UN = 8

        @staticmethod
        def flock(_file, _operation):
            return None

    fcntl = _FcntlCompat()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import config as app_config
except ImportError:
    app_config = None


# ========== 审计日志 ==========
AUDIT_LOG_PATH = Path("/var/log/ssr-admin-panel/audit.log")


def audit_log(action: str, details: str = "", level: str = "INFO"):
    """记录审计日志"""
    try:
        AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().isoformat()
        ip = request.remote_addr if request else "system"
        user = session.get("username", "anonymous") if session else "system"
        log_entry = f"[{timestamp}] [{level}] [{ip}] [{user}] {action}"
        if details:
            log_entry += f" | {details}"
        with AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(log_entry + "\n")
    except OSError:
        pass  # 日志写入失败不应影响主流程

def _default_secret_key():
    """生成强随机 SECRET_KEY（仅在未配置时使用）"""
    return secrets.token_hex(32)


ADMIN_USER = getattr(app_config, "ADMIN_USER", "admin")
ADMIN_PASS = getattr(app_config, "ADMIN_PASS", secrets.token_urlsafe(16))
SECRET_KEY = getattr(app_config, "SECRET_KEY", _default_secret_key())
MUDB_FILE = getattr(app_config, "MUDB_FILE", "/usr/local/shadowsocksr/mudb.json")
SSR_SHARE_HOST = getattr(app_config, "SSR_SHARE_HOST", "")
SSR_SHARE_PORT = getattr(app_config, "SSR_SHARE_PORT", 18899)
SSR_SHARE_PASSWORD = getattr(app_config, "SSR_SHARE_PASSWORD", "")
SSR_SHARE_REMARKS = getattr(app_config, "SSR_SHARE_REMARKS", "")
SSR_SHARE_PROTOCOL = getattr(app_config, "SSR_SHARE_PROTOCOL", "auth_aes128_md5")
SSR_SHARE_METHOD = getattr(app_config, "SSR_SHARE_METHOD", "aes-256-cfb")
SSR_SHARE_OBFS = getattr(app_config, "SSR_SHARE_OBFS", "tls1.2_ticket_auth")
SSR_SHARE_OBFS_PARAM = getattr(app_config, "SSR_SHARE_OBFS_PARAM", "www.baidu.com")
DEVICE_STATS_FILE = getattr(
    app_config, "DEVICE_STATS_FILE", "/var/lib/ssr-admin-panel/device-stats.json"
)
DEVICE_STATS_STALE_SECONDS = getattr(app_config, "DEVICE_STATS_STALE_SECONDS", 120)

app = Flask(__name__)
# 信任 nginx 反代传入的 X-Forwarded-Proto / X-Forwarded-For
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
app.secret_key = SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

# 速率限制：全局默认 200/分钟，登录端点单独限制 5/分钟
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per minute"],
    storage_uri="memory://",
)


# ========== 安全响应头与轻量压缩 ==========
COMPRESSIBLE_MIMETYPES = {
    "text/html",
    "text/css",
    "text/plain",
    "text/javascript",
    "application/javascript",
    "application/json",
    "application/xml",
    "image/svg+xml",
}


@app.after_request
def add_security_headers(response):
    """添加安全相关的 HTTP 响应头，并对较大的文本响应启用 gzip。"""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; font-src 'self'; "
        "base-uri 'self'; form-action 'self'; frame-ancestors 'none'; object-src 'none';"
    )
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"

    accept_encoding = request.headers.get("Accept-Encoding", "").lower()
    if (
        "gzip" in accept_encoding
        and response.status_code == 200
        and not response.direct_passthrough
        and "Content-Encoding" not in response.headers
        and response.mimetype in COMPRESSIBLE_MIMETYPES
    ):
        raw = response.get_data()
        if len(raw) >= 1024:
            compressed = gzip.compress(raw, compresslevel=6)
            if len(compressed) < len(raw):
                response.set_data(compressed)
                response.headers["Content-Encoding"] = "gzip"
                response.headers["Content-Length"] = str(len(compressed))
                response.headers["Vary"] = "Accept-Encoding"
    return response


@app.route("/favicon.ico")
def favicon():
    """内置轻量 favicon，避免浏览器产生 404 请求。"""
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="16" fill="#0d1526"/>
<path d="M32 8l20 8v14c0 12.5-8 22-20 26C20 52 12 42.5 12 30V16l20-8z" fill="#2f6df6"/>
<path d="M22 32l7 7 14-17" fill="none" stroke="#fff" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""
    return Response(svg, mimetype="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})

SSR_DIR = Path("/usr/local/shadowsocksr")
SSR_WORKDIR = SSR_DIR / "shadowsocks"
SSR_SERVER = SSR_WORKDIR / "server.py"
SSR_LOG_FILE = SSR_DIR / "ssserver.log"
SSR_INIT_SCRIPT = Path(getattr(app_config, "SSR_INIT_SCRIPT", "/etc/init.d/ssrmu"))
SSR_SYSTEMD_UNIT = Path(
    getattr(app_config, "SSR_SYSTEMD_UNIT", "/etc/systemd/system/ssr.service")
)
SSR_SYSTEMD_SERVICE = getattr(app_config, "SSR_SYSTEMD_SERVICE", "ssr.service")
SSR_PYTHON_BIN = getattr(app_config, "SSR_PYTHON_BIN", "")
BACKUP_DIR = Path("/opt/ssr-admin-panel/backups")
PANEL_DIR = Path(__file__).resolve().parent
PANEL_VERSION_FILE = PANEL_DIR / "VERSION"
PANEL_BUILD_INFO_FILE = PANEL_DIR / ".panel-build.json"
PANEL_UPDATE_SCRIPT = PANEL_DIR / "update.sh"
PANEL_UPDATE_RUNNER = PANEL_DIR / "scripts" / "run_panel_update.py"
PANEL_UPDATE_LOG = PANEL_DIR / ".panel-update.log"
PANEL_UPDATE_STATUS_FILE = PANEL_DIR / ".panel-update-status.json"
PANEL_GIT_REMOTE = getattr(app_config, "PANEL_GIT_REMOTE", "origin")
PANEL_GIT_BRANCH = getattr(app_config, "PANEL_GIT_BRANCH", "main")
PANEL_GIT_URL = getattr(
    app_config,
    "PANEL_GIT_URL",
    os.environ.get("SSR_ADMIN_REPO_URL", "https://github.com/Elegying/SSR_Panel.git"),
)
PANEL_GIT_SUBDIR = getattr(
    app_config,
    "PANEL_GIT_SUBDIR",
    os.environ.get("SSR_ADMIN_REPO_SUBDIR", "ssr-admin-panel"),
)
PANEL_SERVICE_NAME = getattr(app_config, "PANEL_SERVICE_NAME", "ssr-admin")
PANEL_UPDATE_UNIT = getattr(app_config, "PANEL_UPDATE_UNIT", "ssr-admin-panel-update")
DEFAULT_TRANSFER = 268435456000


def check_auth(username, password):
    return hmac.compare_digest(username or "", ADMIN_USER) and hmac.compare_digest(
        password or "", ADMIN_PASS
    )


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated


def requires_csrf(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        session_token = session.get("csrf_token", "")
        request_token = request.headers.get("X-CSRF-Token", "")

        if not request_token and request.is_json:
            payload = request.get_json(silent=True) or {}
            request_token = payload.get("csrf_token", "")

        if not request_token:
            request_token = request.form.get("csrf_token", "")

        if not session_token or not hmac.compare_digest(request_token, session_token):
            return jsonify({"success": False, "error": "CSRF 校验失败，请刷新页面后重试"}), 403
        return f(*args, **kwargs)

    return decorated


def ensure_csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_hex(16)
        session["csrf_token"] = token
    return token


def mudb_path():
    return Path(MUDB_FILE)


class UserDatabaseError(RuntimeError):
    """Raised when the SSR user database cannot be read safely."""


class UserOperationError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _read_users_unlocked(path):
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, OSError) as exc:
        raise UserDatabaseError(f"无法读取用户数据库: {path}") from exc

    if not isinstance(data, list):
        raise UserDatabaseError(f"用户数据库格式无效: {path}")
    return data


def _write_users_unlocked(path, users):
    tmp_name = None
    mode = None
    try:
        mode = path.stat().st_mode & 0o777
    except OSError:
        pass

    try:
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=str(path.parent),
            text=True,
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=4, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        if mode is not None:
            os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
        tmp_name = None
        try:
            dir_flags = getattr(os, "O_DIRECTORY", 0)
            dir_fd = os.open(path.parent, dir_flags)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    finally:
        if tmp_name:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def load_users():
    path = mudb_path()
    if not path.exists():
        return []
    try:
        with path.with_suffix(path.suffix + ".lock").open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock, fcntl.LOCK_SH)
            try:
                return _read_users_unlocked(path)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
    except UserDatabaseError:
        raise
    except OSError as exc:
        raise UserDatabaseError(f"无法锁定用户数据库: {path}") from exc


def save_users(users):
    path = mudb_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            if path.exists():
                _read_users_unlocked(path)
            _write_users_unlocked(path, users)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def mutate_users(mutator):
    path = mudb_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    try:
        with lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                users = _read_users_unlocked(path)
                result = mutator(users)
                _write_users_unlocked(path, users)
                return result
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
    except (UserDatabaseError, UserOperationError):
        raise
    except OSError as exc:
        raise UserDatabaseError(f"无法更新用户数据库: {path}") from exc


def generate_password(length=12):
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


def to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def to_strict_int(value, default=None):
    if isinstance(value, bool):
        return default
    if isinstance(value, float) and not value.is_integer():
        return default
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def format_bytes(bytes_val):
    bytes_val = float(max(0, to_int(bytes_val, 0)))
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_val < 1024:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.2f} PB"


def format_transfer_limit(limit):
    limit = to_int(limit, 0)
    if limit <= 0:
        return "不限"
    return format_bytes(limit)


def parse_device_limit(user):
    raw_value = str(user.get("protocol_param") or "").strip()
    if not raw_value:
        return 0

    first_part = raw_value.split(":", 1)[0].strip()
    limit = to_int(first_part, 0)
    return max(0, limit)


def load_device_stats():
    payload = read_json_file(DEVICE_STATS_FILE, {})
    if not isinstance(payload, dict):
        return {}

    generated_at_ts = payload.get("generated_at_ts")
    if generated_at_ts is not None:
        try:
            age = time.time() - float(generated_at_ts)
        except (TypeError, ValueError):
            age = 0
        if age > max(1, to_int(DEVICE_STATS_STALE_SECONDS, 120)):
            payload["stale"] = True

    ports = payload.get("ports")
    if not isinstance(ports, dict):
        payload["ports"] = {}
    return payload


def get_device_stats_for_port(device_stats, port):
    ports = device_stats.get("ports", {}) if isinstance(device_stats, dict) else {}
    if not isinstance(ports, dict):
        return {}
    return ports.get(str(port), {}) if isinstance(ports.get(str(port), {}), dict) else {}


def serialize_user(user, device_stats=None):
    upload = max(0, to_int(user.get("u", 0), 0))
    download = max(0, to_int(user.get("d", 0), 0))
    total = upload + download
    transfer_limit = to_int(user.get("transfer_enable", 0), 0)
    usage_percent = 0 if transfer_limit <= 0 else min(100, round(total / transfer_limit * 100, 2))
    port = to_int(user.get("port", 0), 0)
    port_device_stats = get_device_stats_for_port(device_stats or {}, port)

    serialized = dict(user)
    serialized["port"] = port
    serialized["enable"] = 1 if to_int(user.get("enable", 0), 0) == 1 else 0
    serialized["u"] = upload
    serialized["d"] = download
    serialized["upload_human"] = format_bytes(upload)
    serialized["download_human"] = format_bytes(download)
    serialized["total_human"] = format_bytes(total)
    serialized["transfer_limit_human"] = format_transfer_limit(transfer_limit)
    serialized["usage_percent"] = usage_percent
    serialized["device_limit"] = parse_device_limit(user)
    serialized["online_device_count"] = max(0, to_int(port_device_stats.get("online_count", 0), 0))
    serialized["recent_device_count"] = max(0, to_int(port_device_stats.get("recent_count", 0), 0))
    serialized["device_last_seen"] = str(port_device_stats.get("last_seen") or "")
    serialized.pop("passwd", None)
    return serialized


def urlsafe_b64encode(value):
    raw = str(value or "").encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def normalize_share_host(host):
    candidate = str(host or "").split(",", 1)[0].strip()
    if not candidate:
        return ""

    if candidate.startswith("[") and "]" in candidate and candidate.count(":") > 1:
        return candidate.rsplit(":", 1)[0] if not candidate.endswith("]") else candidate

    if ":" in candidate and candidate.count(":") == 1:
        return candidate.rsplit(":", 1)[0]

    return candidate


def get_share_host(request_host=""):
    configured_host = normalize_share_host(SSR_SHARE_HOST)
    return configured_host


def build_ssr_share_url(user, host):
    share_host = get_share_host(host)
    if not share_host:
        raise ValueError("未配置账号分享模板，请先在 config.py 中设置 SSR_SHARE_* 参数")

    share_port = to_int(SSR_SHARE_PORT, None)
    if share_port is None or not 1 <= share_port <= 65535:
        raise ValueError("分享端口配置无效，无法生成分享链接")

    account = str(user.get("user") or "").strip()
    if not account:
        raise ValueError("用户缺少账号，无法生成分享链接")

    account_password = str(user.get("passwd") or "").strip()
    if not account_password:
        raise ValueError("用户缺少密码，无法生成分享链接")

    share_password = str(SSR_SHARE_PASSWORD or "").strip()
    if not share_password:
        raise ValueError("未配置账号分享模板，请先在 config.py 中设置 SSR_SHARE_* 参数")

    protocol = str(SSR_SHARE_PROTOCOL or "auth_aes128_md5").replace("_compatible", "")
    method = str(SSR_SHARE_METHOD or "aes-256-cfb")
    obfs = str(SSR_SHARE_OBFS or "tls1.2_ticket_auth").replace("_compatible", "")
    remarks = str(SSR_SHARE_REMARKS or "").strip()
    if not remarks:
        raise ValueError("未配置账号分享模板，请先在 config.py 中设置 SSR_SHARE_* 参数")
    protocol_param = f"{account}:{account_password}"
    obfs_param = str(SSR_SHARE_OBFS_PARAM or "").strip()
    password_b64 = urlsafe_b64encode(share_password)

    query_parts = [
        f"remarks={urlsafe_b64encode(remarks)}",
        f"protoparam={urlsafe_b64encode(protocol_param)}",
        f"obfsparam={urlsafe_b64encode(obfs_param)}",
    ]
    raw = f"{share_host}:{share_port}:{protocol}:{method}:{obfs}:{password_b64}/?{'&'.join(query_parts)}"
    return f"ssr://{urlsafe_b64encode(raw)}"


def json_error(message, status=400):
    return jsonify({"success": False, "error": message}), status


@app.errorhandler(UserDatabaseError)
def handle_user_database_error(error):
    audit_log("USER_DATABASE_ERROR", str(error), "ERROR")
    return json_error("用户数据库不可用，已拒绝操作以保护现有数据", 500)


@app.errorhandler(UserOperationError)
def handle_user_operation_error(error):
    return json_error(str(error), error.status)


def read_json_file(path, default):
    try:
        with Path(path).open("r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def format_panel_version(version, revision=""):
    base_version = str(version or "").strip() or "unknown"
    clean_revision = str(revision or "").strip()
    if not clean_revision:
        return base_version
    if clean_revision == base_version or clean_revision in base_version:
        return base_version
    if base_version == "unknown":
        return clean_revision
    return f"{base_version} ({clean_revision})"


def read_panel_build_info():
    payload = read_json_file(PANEL_BUILD_INFO_FILE, {})
    if not isinstance(payload, dict):
        return {}
    return payload


def get_panel_version(ref="HEAD"):
    if (PANEL_DIR / ".git").exists():
        result = run_process(["git", "rev-parse", "--short", ref], cwd=PANEL_DIR)
        if result["success"] and result["output"]:
            return result["output"]

    build_info = read_panel_build_info()
    if build_info:
        display_version = str(build_info.get("display_version") or "").strip()
        if display_version:
            return display_version
        formatted = format_panel_version(build_info.get("version", ""), build_info.get("revision", ""))
        if formatted and formatted != "unknown":
            return formatted

    try:
        return PANEL_VERSION_FILE.read_text(encoding="utf-8").strip() or "unknown"
    except OSError:
        return "unknown"


def get_panel_update_unit_state():
    result = run_process(
        ["systemctl", "show", PANEL_UPDATE_UNIT, "--property=ActiveState", "--value"]
    )
    if result["success"] and result["output"]:
        return result["output"].strip()
    return "inactive"


def is_panel_git_workspace():
    return (PANEL_DIR / ".git").is_dir()


def read_version_file(path):
    try:
        return Path(path).read_text(encoding="utf-8").strip() or "unknown"
    except OSError:
        return "unknown"


def panel_repo_source_dir(repo_root):
    repo_root = Path(repo_root)
    if PANEL_GIT_SUBDIR:
        return repo_root / PANEL_GIT_SUBDIR
    return repo_root


def run_capture_process(args, cwd=None, timeout=60):
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout.strip(),
            "error": result.stderr.strip(),
        }
    except (OSError, subprocess.SubprocessError) as e:
        return {"success": False, "output": "", "error": str(e)}


def get_panel_repo_url():
    if PANEL_GIT_URL:
        return PANEL_GIT_URL

    if is_panel_git_workspace():
        result = run_capture_process(["git", "remote", "get-url", PANEL_GIT_REMOTE], cwd=PANEL_DIR)
        if result["success"] and result["output"]:
            return result["output"]

    return ""


def fetch_remote_panel_version_from_repo():
    repo_url = get_panel_repo_url()
    if not repo_url:
        return {"success": False, "version": "unknown", "message": "未配置面板更新仓库地址"}

    with tempfile.TemporaryDirectory(prefix="ssr-admin-panel-update-check-") as tmp_dir:
        clone_result = run_capture_process(
            ["git", "clone", "--depth", "1", "--branch", PANEL_GIT_BRANCH, repo_url, tmp_dir],
            timeout=120,
        )
        if not clone_result["success"]:
            return {
                "success": False,
                "version": "unknown",
                "message": clone_result["error"] or clone_result["output"] or "远程更新检查失败",
            }

        source_dir = panel_repo_source_dir(tmp_dir)
        if not (source_dir / "app.py").is_file():
            return {
                "success": False,
                "version": "unknown",
                "message": f"Project files not found: {source_dir}",
            }

        latest_version = read_version_file(source_dir / "VERSION")
        rev_result = run_capture_process(["git", "rev-parse", "--short", "HEAD"], cwd=tmp_dir)
        revision = rev_result["output"] if rev_result["success"] and rev_result["output"] else ""
        if latest_version == "unknown" and revision:
            latest_version = revision

    return {
        "success": True,
        "version": latest_version,
        "revision": revision,
        "display_version": format_panel_version(latest_version, revision),
        "message": "",
    }


def resolve_latest_panel_version(fetch_remote=False):
    if is_panel_git_workspace() and not PANEL_GIT_SUBDIR:
        if fetch_remote:
            fetch_result = run_process(["git", "fetch", PANEL_GIT_REMOTE, PANEL_GIT_BRANCH], cwd=PANEL_DIR)
            if not fetch_result["success"]:
                return {
                    "success": False,
                    "version": "unknown",
                    "message": fetch_result["error"] or fetch_result["output"] or "远程更新检查失败",
                }

        return {
            "success": True,
            "version": get_panel_version(f"{PANEL_GIT_REMOTE}/{PANEL_GIT_BRANCH}"),
            "message": "",
        }

    return fetch_remote_panel_version_from_repo()


def collect_panel_update_info(fetch_remote=False):
    current_version = get_panel_version()
    info = {
        "success": True,
        "current_version": current_version,
        "latest_version": current_version,
        "update_available": False,
        "remote": PANEL_GIT_REMOTE,
        "branch": PANEL_GIT_BRANCH,
        "message": "当前已是最新版本",
    }

    latest_result = resolve_latest_panel_version(fetch_remote=fetch_remote)
    if not latest_result["success"]:
        info["success"] = False
        info["message"] = latest_result["message"]
        return info

    latest_version = latest_result.get("display_version") or latest_result["version"]
    info["latest_version"] = latest_version
    info["update_available"] = latest_version != "unknown" and latest_version != current_version
    if info["update_available"]:
        info["message"] = f"发现新版本 {latest_version}"
    return info


def read_panel_update_status():
    payload = read_json_file(PANEL_UPDATE_STATUS_FILE, {})
    unit_state = get_panel_update_unit_state()
    payload.setdefault("in_progress", unit_state == "active")
    payload["in_progress"] = payload.get("in_progress", False) or unit_state == "active"
    payload.setdefault("message", "暂无更新任务")
    payload.setdefault("current_version", get_panel_version())
    payload.setdefault("latest_version", None)
    payload.setdefault("last_exit_code", None)
    payload.setdefault("phase", "idle" if not payload.get("in_progress") else "running")
    payload.setdefault("backup_dir", "")
    payload.setdefault("rollback_attempted", False)
    payload.setdefault("rollback_success", False)
    payload["unit_state"] = unit_state
    payload["log_path"] = str(PANEL_UPDATE_LOG)
    return payload


def start_panel_update():
    if not PANEL_UPDATE_RUNNER.exists():
        return {"success": False, "message": f"未找到更新执行器: {PANEL_UPDATE_RUNNER}"}

    if read_panel_update_status().get("in_progress"):
        return {"success": False, "message": "已有更新任务正在执行，请稍后再试"}

    info = collect_panel_update_info(fetch_remote=True)
    if not info["success"]:
        return {"success": False, "message": info["message"]}
    if not info["update_available"]:
        return {
            "success": False,
            "message": f"当前已是最新版本 ({info['current_version']})",
            "current_version": info["current_version"],
            "latest_version": info["latest_version"],
        }

    command = [
        "systemd-run",
        "--unit",
        PANEL_UPDATE_UNIT,
        "--property=Type=oneshot",
        sys.executable,
        str(PANEL_UPDATE_RUNNER),
        "--panel-dir",
        str(PANEL_DIR),
        "--status-file",
        str(PANEL_UPDATE_STATUS_FILE),
        "--log-file",
        str(PANEL_UPDATE_LOG),
        "--remote",
        PANEL_GIT_REMOTE,
        "--branch",
        PANEL_GIT_BRANCH,
        "--repo-url",
        get_panel_repo_url(),
        "--repo-subdir",
        PANEL_GIT_SUBDIR,
        "--service",
        PANEL_SERVICE_NAME,
    ]

    status = {
        "in_progress": True,
        "started_at": datetime.now().isoformat(),
        "finished_at": None,
        "message": f"正在从 {PANEL_GIT_REMOTE}/{PANEL_GIT_BRANCH} 更新到 {info['latest_version']}",
        "current_version": info["current_version"],
        "latest_version": info["latest_version"],
        "last_exit_code": None,
        "phase": "queued",
        "backup_dir": "",
        "rollback_attempted": False,
        "rollback_success": False,
    }
    try:
        PANEL_UPDATE_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        PANEL_UPDATE_STATUS_FILE.write_text(
            json.dumps(status, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        return {"success": False, "message": f"无法创建更新状态文件: {e}"}

    if shutil.which("systemd-run"):
        launch_result = run_process(command)
    else:
        try:
            subprocess.Popen(
                command[4:],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                close_fds=True,
            )
            launch_result = {"success": True, "output": "detached", "error": ""}
        except OSError as e:
            launch_result = {"success": False, "output": "", "error": str(e)}

    if not launch_result["success"]:
        status.update(
            {
                "in_progress": False,
                "finished_at": datetime.now().isoformat(),
                "message": launch_result["error"] or launch_result["output"] or "更新任务启动失败",
                "last_exit_code": 1,
                "phase": "failed",
            }
        )
        try:
            PANEL_UPDATE_STATUS_FILE.write_text(
                json.dumps(status, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass
        return {
            "success": False,
            "message": launch_result["error"] or launch_result["output"] or "更新任务启动失败",
        }
    return {
        "success": True,
        "message": f"更新任务已启动，目标版本 {info['latest_version']}。面板会在完成后自动重启。",
        "current_version": info["current_version"],
        "latest_version": info["latest_version"],
    }


def read_proc_stat():
    stat_path = Path("/proc/stat")
    if not stat_path.exists():
        return None

    with stat_path.open("r", encoding="utf-8") as f:
        first_line = f.readline().strip().split()

    if len(first_line) < 8 or first_line[0] != "cpu":
        return None

    return [int(value) for value in first_line[1:8]]


def get_cpu_usage():
    first = read_proc_stat()
    if first:
        time.sleep(0.1)
        second = read_proc_stat()
        if second:
            idle_delta = (second[3] + second[4]) - (first[3] + first[4])
            total_delta = sum(second) - sum(first)
            if total_delta > 0:
                usage = (1 - (idle_delta / total_delta)) * 100
                return f"{usage:.1f}"

    try:
        load_avg = os.getloadavg()[0]
        cpu_count = max(1, os.cpu_count() or 1)
        usage = min(100.0, load_avg / cpu_count * 100)
        return f"{usage:.1f}"
    except OSError:
        return "0"


def get_memory_info():
    meminfo_path = Path("/proc/meminfo")
    if meminfo_path.exists():
        values = {}
        with meminfo_path.open("r", encoding="utf-8") as f:
            for line in f:
                key, _, raw_value = line.partition(":")
                parts = raw_value.strip().split()
                if parts:
                    values[key] = int(parts[0])

        mem_total = values.get("MemTotal", 0) // 1024
        mem_available = values.get("MemAvailable", values.get("MemFree", 0)) // 1024
        mem_used = max(0, mem_total - mem_available)
        mem_percent = round(mem_used / mem_total * 100, 1) if mem_total > 0 else 0
        return mem_total, mem_used, mem_percent

    return 0, 0, 0


def humanize_duration(seconds):
    seconds = max(0, int(seconds))
    if seconds == 0:
        return "刚刚"

    parts = []
    intervals = (
        ("天", 86400),
        ("小时", 3600),
        ("分钟", 60),
    )

    for label, unit_seconds in intervals:
        value, seconds = divmod(seconds, unit_seconds)
        if value:
            parts.append(f"{value}{label}")

    if not parts:
        parts.append(f"{seconds}秒")

    return " ".join(parts[:2])


def get_uptime():
    uptime_path = Path("/proc/uptime")
    if uptime_path.exists():
        try:
            seconds = float(uptime_path.read_text(encoding="utf-8").split()[0])
            return humanize_duration(seconds)
        except (OSError, ValueError, IndexError):
            pass

    try:
        result = subprocess.run(
            ["uptime"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        output = result.stdout.strip()
        if " up " in output:
            return output.split(" up ", 1)[1].split(",", 1)[0].strip()
    except (OSError, subprocess.SubprocessError):
        pass

    return "unknown"


def _json_has_ipv6_forbid(path):
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False

    entries = payload if isinstance(payload, list) else [payload] if isinstance(payload, dict) else []
    for entry in entries:
        if "::/0" in str(entry.get("forbidden_ip") or ""):
            return True
    return False


def get_server_optimization_status():
    ipv6_guard = any(_json_has_ipv6_forbid(path) for path in (MUDB_FILE,))
    quic_guard = False
    try:
        result = subprocess.run(
            ["nft", "list", "table", "inet", "ssr_filter"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        quic_guard = result.returncode == 0 and "udp dport 443 reject" in result.stdout
    except (OSError, subprocess.SubprocessError):
        pass

    # BBR 检测
    bbr_mode = "未知"
    bbr_available = False
    try:
        result = subprocess.run(
            ["sysctl", "-n", "net.ipv4.tcp_congestion_control"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        cc = result.stdout.strip()
        if cc == "bbr":
            bbr_available = True
            bbr_mode = "BBR"
        elif cc:
            bbr_mode = cc
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        result = subprocess.run(
            ["sysctl", "-n", "net.core.default_qdisc"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        qdisc = result.stdout.strip()
        if bbr_available and qdisc:
            bbr_mode = f"BBR ({qdisc})"
    except (OSError, subprocess.SubprocessError):
        pass

    if ipv6_guard:
        label = "已启用"
    elif quic_guard:
        label = "仅 UDP/443 拦截"
    else:
        label = "未启用"

    return {
        "ipv6_guard": ipv6_guard,
        "quic_guard": quic_guard,
        "bbr_mode": bbr_mode,
        "bbr_available": bbr_available,
        "enabled": ipv6_guard,
        "label": label,
    }


def get_system_info():
    try:
        mem_total, mem_used, mem_percent = get_memory_info()
        disk = shutil.disk_usage("/")
        disk_total = format_bytes(disk.total)
        disk_used = format_bytes(disk.used)
        disk_percent = str(round(disk.used / disk.total * 100)) if disk.total else "0"

        return {
            "cpu": get_cpu_usage(),
            "mem_total": mem_total,
            "mem_used": mem_used,
            "mem_percent": mem_percent,
            "disk_total": disk_total,
            "disk_used": disk_used,
            "disk_percent": disk_percent,
            "uptime": get_uptime(),
            "optimization_status": get_server_optimization_status(),
        }
    except OSError:
        return {
            "cpu": "0",
            "mem_total": 0,
            "mem_used": 0,
            "mem_percent": 0,
            "disk_total": "0",
            "disk_used": "0",
            "disk_percent": "0",
            "uptime": "unknown",
            "optimization_status": get_server_optimization_status(),
        }


def get_ssr_python():
    return get_ssr_python_candidates()[0]


def resolve_binary(candidate):
    if not candidate:
        return None

    candidate_path = Path(candidate)
    if candidate_path.is_absolute():
        return str(candidate_path) if candidate_path.exists() else None

    return shutil.which(candidate)


def get_ssr_python_candidates():
    candidates = []
    for candidate in (SSR_PYTHON_BIN, "python2", "python", "python3", sys.executable):
        resolved = resolve_binary(candidate)
        if resolved and resolved not in candidates:
            candidates.append(resolved)
    return candidates or [sys.executable]


def run_process(args, cwd=None):
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout.strip(),
            "error": result.stderr.strip(),
        }
    except (OSError, subprocess.SubprocessError) as e:
        return {"success": False, "output": "", "error": str(e)}


def get_expected_ssr_status(action):
    return "stopped" if action == "stop" else "running"


def is_ssr_process_command(command):
    parts = command.split()
    if not parts:
        return False

    python_name = Path(parts[0]).name.lower()
    if python_name.startswith("python") and len(parts) > 1 and parts[1] == "server.py":
        return True

    for part in parts:
        if part.endswith("server.py") and "shadowsocks" in part:
            return True

    return False


def wait_for_ssr_status(expected_status, retries=10, delay=0.5):
    for attempt in range(max(1, retries)):
        if get_ssr_status() == expected_status:
            return True
        if attempt < retries - 1:
            time.sleep(delay)
    return False


def merge_process_results(results):
    return {
        "success": any(result.get("success") for result in results),
        "output": "\n".join(filter(None, (result.get("output", "").strip() for result in results))),
        "error": "\n".join(filter(None, (result.get("error", "").strip() for result in results))),
    }


def run_ssr_init_script(action):
    if not SSR_INIT_SCRIPT.exists():
        return None
    return run_process([str(SSR_INIT_SCRIPT), action])


def systemd_controls_ssr():
    return (
        SSR_SYSTEMD_UNIT.is_file()
        and Path("/run/systemd/system").is_dir()
        and shutil.which("systemctl") is not None
    )


def run_ssr_systemd_command(action):
    return run_process(["systemctl", action, SSR_SYSTEMD_SERVICE])


def run_ssr_server_command_once(action):
    if not SSR_SERVER.exists():
        return {"success": False, "output": "", "error": f"未找到 SSR 服务脚本: {SSR_SERVER}"}

    failures = []
    for python_bin in get_ssr_python_candidates():
        result = run_process([python_bin, "server.py", "-d", action], cwd=SSR_WORKDIR)
        if result["success"]:
            return result
        failures.append((python_bin, result))

    messages = []
    for python_bin, result in failures:
        details = result["error"] or result["output"] or "命令执行失败"
        messages.append(f"{python_bin}: {details}")
    return {"success": False, "output": "", "error": "\n".join(messages)}


def run_ssr_server_command(action):
    if action == "restart":
        return merge_process_results(
            [run_ssr_server_command_once("stop"), run_ssr_server_command_once("start")]
        )
    return run_ssr_server_command_once(action)


def execute_ssr_command(action):
    if action not in {"start", "stop", "restart"}:
        return {"success": False, "output": "", "error": "不支持的操作"}

    if systemd_controls_ssr():
        runners = [run_ssr_systemd_command]
    else:
        runners = []
        if SSR_INIT_SCRIPT.exists():
            runners.append(run_ssr_init_script)
        if SSR_SERVER.exists():
            runners.append(run_ssr_server_command)

    if not runners:
        return {
            "success": False,
            "output": "",
            "error": f"未找到 SSR 控制脚本: {SSR_INIT_SCRIPT}，也未找到 SSR 服务脚本: {SSR_SERVER}",
        }

    expected_status = get_expected_ssr_status(action)
    attempted_results = []

    for runner in runners:
        result = runner(action)
        if result is None:
            continue
        attempted_results.append(result)
        if wait_for_ssr_status(expected_status):
            merged = merge_process_results(attempted_results)
            if not merged["output"]:
                merged["output"] = f"SSR 当前状态: {expected_status}"
            merged["success"] = True
            return merged

    merged = merge_process_results(attempted_results)
    merged["success"] = False
    merged["error"] = "\n".join(
        filter(None, [merged["error"], f"执行后 SSR 状态仍未达到预期，当前状态: {get_ssr_status()}"])
    )
    return merged


def get_ssr_status():
    try:
        if systemd_controls_ssr():
            result = run_process(["systemctl", "is-active", SSR_SYSTEMD_SERVICE])
            status = (result["output"] or result["error"]).strip().lower().splitlines()
            state = status[0] if status else ""
            if result["success"] or state in {"active", "activating", "reloading"}:
                return "running"
            if state in {"inactive", "failed", "deactivating", "dead"}:
                return "stopped"
            return "unknown"

        if SSR_INIT_SCRIPT.exists():
            result = run_process([str(SSR_INIT_SCRIPT), "status"])
            output = "\n".join(filter(None, [result["output"], result["error"]])).lower()
            if any(keyword in output for keyword in ("not running", "stopped", "inactive", "未运行", "已停止")):
                return "stopped"
            if any(keyword in output for keyword in ("running", "active", "正在运行", "已运行")):
                return "running"

        result = subprocess.run(
            ["ps", "-eo", "args="],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode != 0:
            return "unknown"

        for command in result.stdout.splitlines():
            normalized = command.strip()
            if not normalized or "grep" in normalized:
                continue
            if is_ssr_process_command(normalized):
                return "running"
        return "stopped"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def read_log_tail(lines):
    lines = max(1, min(lines, 500))
    if not SSR_LOG_FILE.exists():
        return {"success": True, "output": "日志文件不存在", "error": ""}

    try:
        with SSR_LOG_FILE.open("r", encoding="utf-8", errors="replace") as f:
            last_lines = "".join(deque(f, maxlen=lines))
        return {"success": True, "output": last_lines.strip(), "error": ""}
    except OSError as e:
        return {"success": False, "output": "", "error": str(e)}


def find_user(users, username):
    for user in users:
        if str(user.get("user", "")) == username:
            return user
    return None


def validate_new_user(data, existing_users):
    if not isinstance(data, dict):
        return None, "请求数据格式错误"

    port = to_strict_int(data.get("port"), None)
    if port is None or not 1 <= port <= 65535:
        return None, "端口必须是 1-65535 之间的数字"

    username = str(data.get("user") or port).strip()
    if not username:
        return None, "用户名不能为空"

    password = str(data.get("password") or "").strip() or generate_password()
    raw_transfer = data.get("transfer")
    if raw_transfer in (None, ""):
        transfer_enable = DEFAULT_TRANSFER
    else:
        transfer_enable = to_strict_int(raw_transfer, None)
        if transfer_enable is None:
            return None, "流量限额必须是非负整数"
    if transfer_enable < 0:
        return None, "流量限额不能小于 0"

    if any(to_int(user.get("port"), 0) == port for user in existing_users):
        return None, f"端口 {port} 已存在"

    if any(str(user.get("user", "")) == username for user in existing_users):
        return None, f"用户名 {username} 已存在"

    return {
        "user": username,
        "passwd": password,
        "port": port,
        "method": str(data.get("method") or "aes-256-cfb"),
        "protocol": str(data.get("protocol") or "auth_aes128_md5"),
        "obfs": str(data.get("obfs") or "tls1.2_ticket_auth"),
        "obfs_param": str(data.get("obfs_param") or "www.baidu.com"),
        "transfer_enable": transfer_enable,
        "enable": 1,
        "d": 0,
        "u": 0,
    }, None


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute", exempt_when=lambda: request.method != "POST")
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        request_token = request.form.get("csrf_token", "")
        session_token = session.get("csrf_token", "")
        if not session_token or not hmac.compare_digest(request_token, session_token):
            error = "页面已过期，请刷新后重试"
            audit_log("LOGIN_CSRF_FAILED", f"登录 CSRF 校验失败，用户名: {username}", "WARNING")
        elif check_auth(username, password):
            session.clear()
            session["logged_in"] = True
            session["username"] = username
            ensure_csrf_token()
            audit_log("LOGIN_SUCCESS", f"用户 {username} 登录成功")
            return redirect(url_for("index"))
        else:
            error = "用户名或密码错误"
            audit_log("LOGIN_FAILED", f"登录失败，用户名: {username}", "WARNING")
    return render_template("login.html", error=error, csrf_token=ensure_csrf_token())


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@requires_auth
def index():
    users = load_users()
    device_stats = load_device_stats()
    total_users = len(users)
    total_upload = sum(max(0, to_int(user.get("u", 0), 0)) for user in users)
    total_download = sum(max(0, to_int(user.get("d", 0), 0)) for user in users)
    inactive_users = sum(
        1 for user in users if (to_int(user.get("u", 0), 0) + to_int(user.get("d", 0), 0)) == 0
    )
    total_online_devices = sum(
        serialize_user(user, device_stats).get("online_device_count", 0) for user in users
    )

    return render_template(
        "index.html",
        total_users=total_users,
        total_upload=total_upload,
        total_download=total_download,
        inactive_users=inactive_users,
        total_online_devices=total_online_devices,
        format_bytes=format_bytes,
        ssr_status=get_ssr_status(),
        system_info=get_system_info(),
        optimization_status=get_server_optimization_status(),
        panel_version=get_panel_version(),
        csrf_token=ensure_csrf_token(),
    )


@app.route("/api/ssr/start", methods=["POST"])
@requires_auth
@requires_csrf
@limiter.limit("10 per minute")
def ssr_start():
    audit_log("SSR_START", "启动 SSR 服务")
    return jsonify(execute_ssr_command("start"))


@app.route("/api/ssr/stop", methods=["POST"])
@requires_auth
@requires_csrf
@limiter.limit("10 per minute")
def ssr_stop():
    audit_log("SSR_STOP", "停止 SSR 服务")
    return jsonify(execute_ssr_command("stop"))


@app.route("/api/ssr/restart", methods=["POST"])
@requires_auth
@requires_csrf
@limiter.limit("10 per minute")
def ssr_restart():
    audit_log("SSR_RESTART", "重启 SSR 服务")
    return jsonify(execute_ssr_command("restart"))


@app.route("/api/ssr/status")
@requires_auth
def ssr_status():
    return jsonify({"status": get_ssr_status()})


@app.route("/api/ssr/log")
@requires_auth
def ssr_log():
    lines = to_int(request.args.get("lines", 100), 100)
    return jsonify(read_log_tail(lines))


@app.route("/api/system")
@requires_auth
def api_system():
    return jsonify(get_system_info())


@app.route("/api/panel/update/check")
@requires_auth
def panel_update_check():
    info = collect_panel_update_info(fetch_remote=True)
    return jsonify(info), (200 if info["success"] else 500)


@app.route("/api/panel/update/status")
@requires_auth
def panel_update_status():
    return jsonify(read_panel_update_status())


@app.route("/api/panel/update", methods=["POST"])
@requires_auth
@requires_csrf
@limiter.limit("5 per minute")
def panel_update():
    audit_log("PANEL_UPDATE", "触发面板更新")
    result = start_panel_update()
    return jsonify(result), (200 if result["success"] else 409)


@app.route("/api/backup", methods=["POST"])
@requires_auth
@requires_csrf
@limiter.limit("10 per minute")
def backup_data():
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = BACKUP_DIR / f"mudb_{timestamp}.json"
        shutil.copy2(mudb_path(), backup_file)

        backups = sorted(BACKUP_DIR.glob("mudb_*.json"))
        for old_backup in backups[:-10]:
            old_backup.unlink(missing_ok=True)

        audit_log("BACKUP", f"备份成功: {backup_file.name}")
        return jsonify({"success": True, "message": f"备份成功: {backup_file}"})
    except OSError as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/backups/list")
@requires_auth
def list_backups():
    try:
        if not BACKUP_DIR.exists():
            return jsonify({"success": True, "backups": []})

        backups = []
        for backup_file in sorted(BACKUP_DIR.glob("mudb_*.json"), reverse=True):
            backups.append(
                {
                    "name": backup_file.name,
                    "size": backup_file.stat().st_size,
                    "time": datetime.fromtimestamp(backup_file.stat().st_mtime).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                }
            )

        return jsonify({"success": True, "backups": backups})
    except OSError as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/users")
@requires_auth
def api_users():
    device_stats = load_device_stats()
    users = [serialize_user(user, device_stats) for user in reversed(load_users())]
    return jsonify(
        {
            "success": True,
            "data": users,
            "device_stats": {
                "generated_at": device_stats.get("generated_at", ""),
                "stale": bool(device_stats.get("stale", False)),
                "window_seconds": to_int(device_stats.get("window_seconds", 0), 0),
            },
        }
    )


@app.route("/api/add", methods=["POST"])
@requires_auth
@requires_csrf
@limiter.limit("30 per minute")
def add_user():
    payload = request.get_json(silent=True) or {}

    def add(users):
        new_user, error = validate_new_user(payload, users)
        if error:
            raise UserOperationError(error)
        users.append(new_user)
        return new_user

    new_user = mutate_users(add)
    audit_log("USER_ADD", f"添加用户: {new_user['user']}, 端口: {new_user['port']}")
    created_user = serialize_user(new_user)
    created_user["generated_password"] = new_user["passwd"]
    return jsonify({"success": True, "message": "用户添加成功", "user": created_user})


@app.route("/api/share/<path:user>", methods=["POST"])
@requires_auth
@requires_csrf
def share_user(user):
    users = load_users()
    target = find_user(users, user)
    if not target:
        return json_error("用户不存在", 404)

    try:
        share_url = build_ssr_share_url(target, request.host)
    except ValueError as exc:
        return json_error(str(exc))

    return jsonify(
        {
            "success": True,
            "message": f"用户 {user} 的分享链接已生成",
            "share_url": share_url,
        }
    )


@app.route("/api/delete/<path:user>", methods=["POST"])
@requires_auth
@requires_csrf
@limiter.limit("30 per minute")
def delete_user(user):
    def delete(users):
        target = find_user(users, user)
        if not target:
            raise UserOperationError("用户不存在", 404)
        port = target.get("port", "?")
        users.remove(target)
        return port

    port = mutate_users(delete)
    audit_log("USER_DELETE", f"删除用户: {user}, 端口: {port}")
    return jsonify({"success": True, "message": "用户删除成功"})


@app.route("/api/reset/<path:user>", methods=["POST"])
@requires_auth
@requires_csrf
@limiter.limit("30 per minute")
def reset_user(user):
    def reset(users):
        target = find_user(users, user)
        if not target:
            raise UserOperationError("用户不存在", 404)
        target["u"] = 0
        target["d"] = 0

    mutate_users(reset)
    audit_log("USER_RESET", f"重置流量: {user}")
    return jsonify({"success": True, "message": f"用户 {user} 流量已重置"})


@app.route("/api/toggle/<path:user>", methods=["POST"])
@requires_auth
@requires_csrf
@limiter.limit("30 per minute")
def toggle_user(user):
    def toggle(users):
        target = find_user(users, user)
        if not target:
            raise UserOperationError("用户不存在", 404)
        new_state = 0 if to_int(target.get("enable", 0), 0) == 1 else 1
        target["enable"] = new_state
        return new_state

    new_state = mutate_users(toggle)
    audit_log("USER_TOGGLE", f"{'启用' if new_state else '禁用'}用户: {user}")
    return jsonify({"success": True, "message": f"用户 {user} 状态已切换"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
