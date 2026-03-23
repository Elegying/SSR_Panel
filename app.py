#!/usr/bin/env python3
import hmac
import json
import os
import random
import secrets
import shutil
import string
import subprocess
import sys
import time
from collections import deque
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from config import ADMIN_PASS, ADMIN_USER, MUDB_FILE, SECRET_KEY
except ImportError:
    ADMIN_USER = "admin"
    ADMIN_PASS = "admin123"
    SECRET_KEY = "default-secret-key-change-me"
    MUDB_FILE = "/usr/local/shadowsocksr/mudb.json"

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

SSR_DIR = Path("/usr/local/shadowsocksr")
SSR_WORKDIR = SSR_DIR / "shadowsocks"
SSR_SERVER = SSR_WORKDIR / "server.py"
SSR_LOG_FILE = SSR_DIR / "ssserver.log"
BACKUP_DIR = Path("/opt/ssr-admin-panel/backups")
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


def load_users():
    try:
        with mudb_path().open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def save_users(users):
    path = mudb_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(users, f, indent=4, ensure_ascii=False)


def generate_password(length=12):
    chars = string.ascii_letters + string.digits
    return "".join(random.choice(chars) for _ in range(length))


def to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
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


def serialize_user(user):
    upload = max(0, to_int(user.get("u", 0), 0))
    download = max(0, to_int(user.get("d", 0), 0))
    total = upload + download
    transfer_limit = to_int(user.get("transfer_enable", 0), 0)
    usage_percent = 0 if transfer_limit <= 0 else min(100, round(total / transfer_limit * 100, 2))

    serialized = dict(user)
    serialized["port"] = to_int(user.get("port", 0), 0)
    serialized["enable"] = 1 if to_int(user.get("enable", 0), 0) == 1 else 0
    serialized["u"] = upload
    serialized["d"] = download
    serialized["upload_human"] = format_bytes(upload)
    serialized["download_human"] = format_bytes(download)
    serialized["total_human"] = format_bytes(total)
    serialized["transfer_limit_human"] = format_transfer_limit(transfer_limit)
    serialized["usage_percent"] = usage_percent
    serialized.pop("passwd", None)
    return serialized


def json_error(message, status=400):
    return jsonify({"success": False, "error": message}), status


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
        }


def get_ssr_python():
    for candidate in ("python3", "python"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return sys.executable


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


def execute_ssr_command(action):
    if action not in {"start", "stop", "restart"}:
        return {"success": False, "output": "", "error": "不支持的操作"}
    if not SSR_SERVER.exists():
        return {"success": False, "output": "", "error": f"未找到 SSR 服务脚本: {SSR_SERVER}"}

    if action == "restart":
        stop_result = run_process([get_ssr_python(), "server.py", "-d", "stop"], cwd=SSR_WORKDIR)
        start_result = run_process([get_ssr_python(), "server.py", "-d", "start"], cwd=SSR_WORKDIR)
        if not stop_result["success"] and not stop_result["error"]:
            stop_result["error"] = "停止 SSR 失败"
        if not start_result["success"] and not start_result["error"]:
            start_result["error"] = "启动 SSR 失败"
        return {
            "success": start_result["success"],
            "output": "\n".join(filter(None, [stop_result["output"], start_result["output"]])),
            "error": "\n".join(filter(None, [stop_result["error"], start_result["error"]])),
        }

    return run_process([get_ssr_python(), "server.py", "-d", action], cwd=SSR_WORKDIR)


def get_ssr_status():
    try:
        result = subprocess.run(
            ["pgrep", "-f", "server.py"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return "running" if result.returncode == 0 else "stopped"
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

    port = to_int(data.get("port"), None)
    if port is None or not 1 <= port <= 65535:
        return None, "端口必须是 1-65535 之间的数字"

    username = str(data.get("user") or port).strip()
    if not username:
        return None, "用户名不能为空"

    password = str(data.get("password") or "").strip() or generate_password()
    transfer_enable = to_int(data.get("transfer"), DEFAULT_TRANSFER)
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
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if check_auth(username, password):
            session.clear()
            session["logged_in"] = True
            session["username"] = username
            ensure_csrf_token()
            return redirect(url_for("index"))
        error = "用户名或密码错误"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@requires_auth
def index():
    users = load_users()
    total_users = len(users)
    total_upload = sum(max(0, to_int(user.get("u", 0), 0)) for user in users)
    total_download = sum(max(0, to_int(user.get("d", 0), 0)) for user in users)
    inactive_users = sum(
        1 for user in users if (to_int(user.get("u", 0), 0) + to_int(user.get("d", 0), 0)) == 0
    )

    return render_template(
        "index.html",
        total_users=total_users,
        total_upload=total_upload,
        total_download=total_download,
        inactive_users=inactive_users,
        format_bytes=format_bytes,
        ssr_status=get_ssr_status(),
        system_info=get_system_info(),
        csrf_token=ensure_csrf_token(),
    )


@app.route("/api/ssr/start", methods=["POST"])
@requires_auth
@requires_csrf
def ssr_start():
    return jsonify(execute_ssr_command("start"))


@app.route("/api/ssr/stop", methods=["POST"])
@requires_auth
@requires_csrf
def ssr_stop():
    return jsonify(execute_ssr_command("stop"))


@app.route("/api/ssr/restart", methods=["POST"])
@requires_auth
@requires_csrf
def ssr_restart():
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


@app.route("/api/backup", methods=["POST"])
@requires_auth
@requires_csrf
def backup_data():
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = BACKUP_DIR / f"mudb_{timestamp}.json"
        shutil.copy2(mudb_path(), backup_file)

        backups = sorted(BACKUP_DIR.glob("mudb_*.json"))
        for old_backup in backups[:-10]:
            old_backup.unlink(missing_ok=True)

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
    users = [serialize_user(user) for user in load_users()]
    return jsonify({"success": True, "data": users})


@app.route("/api/add", methods=["POST"])
@requires_auth
@requires_csrf
def add_user():
    users = load_users()
    new_user, error = validate_new_user(request.get_json(silent=True) or {}, users)
    if error:
        return json_error(error)

    users.append(new_user)
    save_users(users)
    created_user = serialize_user(new_user)
    created_user["generated_password"] = new_user["passwd"]
    return jsonify({"success": True, "message": "用户添加成功", "user": created_user})


@app.route("/api/delete/<path:user>", methods=["POST"])
@requires_auth
@requires_csrf
def delete_user(user):
    users = load_users()
    target = find_user(users, user)
    if not target:
        return json_error("用户不存在", 404)

    users.remove(target)
    save_users(users)
    return jsonify({"success": True, "message": "用户删除成功"})


@app.route("/api/reset/<path:user>", methods=["POST"])
@requires_auth
@requires_csrf
def reset_user(user):
    users = load_users()
    target = find_user(users, user)
    if not target:
        return json_error("用户不存在", 404)

    target["u"] = 0
    target["d"] = 0
    save_users(users)
    return jsonify({"success": True, "message": f"用户 {user} 流量已重置"})


@app.route("/api/toggle/<path:user>", methods=["POST"])
@requires_auth
@requires_csrf
def toggle_user(user):
    users = load_users()
    target = find_user(users, user)
    if not target:
        return json_error("用户不存在", 404)

    target["enable"] = 0 if to_int(target.get("enable", 0), 0) == 1 else 1
    save_users(users)
    return jsonify({"success": True, "message": f"用户 {user} 状态已切换"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
