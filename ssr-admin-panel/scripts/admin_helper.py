#!/usr/bin/python3
import argparse
import ast
import fcntl
import json
import os
import pwd
import re
import stat
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse


PANEL_DIR = Path("/opt/ssr-admin-panel")
RUNTIME_DIR = Path("/var/lib/ssr-admin-panel")
CONFIG_FILE = PANEL_DIR / "config.py"
PENDING_MUDB_FILE = RUNTIME_DIR / "mudb.pending.json"
MUDB_FILE = Path("/usr/local/shadowsocksr/mudb.json")
MUDB_LOCK_FILE = Path("/run/lock/ssr-panel-mudb.lock")
FIREWALL_HELPER = Path("/usr/local/libexec/ssr-panel/sync-firewall.py")
SYSTEMCTL = "/usr/bin/systemctl"
SYSTEMD_RUN = "/usr/bin/systemd-run"
PYTHON = "/usr/bin/python3"
SERVICE_PATTERN = re.compile(r"^[A-Za-z0-9_.@-]+$")
REF_PATTERN = re.compile(r"^[A-Za-z0-9._/-]+$")
ALLOWED_ACTIONS = {
    "ssr-start",
    "ssr-stop",
    "ssr-restart",
    "firewall-sync",
    "mudb-commit",
    "panel-update",
}


def load_literal_config(path=CONFIG_FILE):
    tree = ast.parse(Path(path).read_text(encoding="utf-8"), filename=str(path))
    values = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (TypeError, ValueError):
            continue
        values[target.id] = value
    return values


def _validate_update_config(config):
    repo_url = config.get("PANEL_GIT_URL", "https://github.com/Elegying/SSR_Panel.git")
    branch = config.get("PANEL_GIT_BRANCH", "main")
    subdir = config.get("PANEL_GIT_SUBDIR", "ssr-admin-panel")
    service = config.get("PANEL_SERVICE_NAME", "ssr-admin")
    parsed = urlparse(repo_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("PANEL_GIT_URL must be an HTTPS URL without credentials")
    if not isinstance(branch, str) or not REF_PATTERN.fullmatch(branch) or branch.startswith("-"):
        raise ValueError("invalid PANEL_GIT_BRANCH")
    subdir_path = Path(subdir)
    if not isinstance(subdir, str) or subdir_path.is_absolute() or ".." in subdir_path.parts:
        raise ValueError("invalid PANEL_GIT_SUBDIR")
    if not isinstance(service, str) or not SERVICE_PATTERN.fullmatch(service):
        raise ValueError("invalid PANEL_SERVICE_NAME")
    return repo_url, branch, subdir, service


def build_panel_update_command(panel_dir=PANEL_DIR, config=None):
    panel_dir = Path(panel_dir).resolve()
    repo_url, branch, subdir, service = _validate_update_config(config or {})
    runner = panel_dir / "scripts" / "run_panel_update.py"
    return [
        SYSTEMD_RUN,
        "--unit",
        "ssr-admin-panel-update",
        "--property=Type=oneshot",
        PYTHON,
        str(runner),
        "--panel-dir",
        str(panel_dir),
        "--status-file",
        str(RUNTIME_DIR / "panel-update-status.json"),
        "--log-file",
        str(RUNTIME_DIR / "panel-update.log"),
        "--remote",
        "origin",
        "--branch",
        branch,
        "--repo-url",
        repo_url,
        "--repo-subdir",
        subdir,
        "--service",
        service,
    ]


def build_command(action, config=None):
    commands = {
        "ssr-start": [SYSTEMCTL, "start", "ssr.service"],
        "ssr-stop": [SYSTEMCTL, "stop", "ssr.service"],
        "ssr-restart": [SYSTEMCTL, "restart", "ssr.service"],
        "firewall-sync": [PYTHON, str(FIREWALL_HELPER)],
    }
    if action in commands:
        return commands[action]
    if action == "panel-update":
        return build_panel_update_command(PANEL_DIR, config or load_literal_config())
    if action == "mudb-commit":
        raise ValueError("mudb-commit is handled internally")
    raise ValueError(f"unsupported action: {action}")


def validate_mudb_payload(payload):
    if not isinstance(payload, list):
        raise ValueError("mudb root must be a list")
    if len(payload) > 10_000:
        raise ValueError("mudb has too many users")
    for user in payload:
        if not isinstance(user, dict):
            raise ValueError("mudb entries must be objects")
        port = user.get("port")
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError("mudb entry has an invalid port")
        for value in user.values():
            if isinstance(value, str) and len(value) > 4096:
                raise ValueError("mudb string value is too long")
    return payload


def _read_pending_payload(path=PENDING_MUDB_FILE):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(path), flags)
    try:
        file_stat = os.fstat(fd)
        panel_uid = pwd.getpwnam("ssr-panel").pw_uid
        if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_nlink != 1:
            raise ValueError("pending mudb must be a regular file")
        if file_stat.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise ValueError("pending mudb must not be group/world writable")
        if file_stat.st_uid != panel_uid or file_stat.st_size > 16 * 1024 * 1024:
            raise ValueError("pending mudb has unsafe ownership or size")
        with os.fdopen(fd, "r", encoding="utf-8-sig") as handle:
            fd = -1
            payload = json.load(handle)
    finally:
        if fd >= 0:
            os.close(fd)
    return validate_mudb_payload(payload)


def validate_mudb_target(target):
    target = Path(target)
    if not target.is_absolute() or target.name != "mudb.json" or target.is_symlink():
        raise ValueError("unsafe mudb target")
    parent = target.parent.resolve(strict=True)
    parent_stat = parent.stat()
    if parent_stat.st_uid != 0 or parent_stat.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise ValueError("mudb parent must be root-owned and not group/world writable")
    return parent / target.name


def _write_mudb_atomic(payload, target=MUDB_FILE):
    target = validate_mudb_target(target)
    group_gid = pwd.getpwnam("ssr-panel").pw_gid
    fd, temp_name = tempfile.mkstemp(prefix=".mudb.json.", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = -1
            json.dump(payload, handle, indent=4, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chown(temp_name, 0, group_gid)
        os.chmod(temp_name, 0o640)
        os.replace(temp_name, str(target))
        temp_name = None
    finally:
        if fd >= 0:
            os.close(fd)
        if temp_name:
            try:
                os.unlink(temp_name)
            except OSError:
                pass


def ensure_mudb_permissions(config=None):
    config = config or load_literal_config()
    target = Path(config.get("MUDB_FILE", str(MUDB_FILE)))
    if not target.exists():
        return
    target = validate_mudb_target(target)
    group_gid = pwd.getpwnam("ssr-panel").pw_gid
    os.chown(str(target), 0, group_gid)
    os.chmod(str(target), 0o640)


def commit_pending_mudb():
    MUDB_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with MUDB_LOCK_FILE.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        payload = _read_pending_payload()
        config = load_literal_config()
        _write_mudb_atomic(payload, config.get("MUDB_FILE", str(MUDB_FILE)))
        PENDING_MUDB_FILE.unlink()


def _assert_safe_root_file(path):
    file_stat = Path(path).lstat()
    if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_uid != 0:
        raise ValueError(f"unsafe privileged executable: {path}")
    if file_stat.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise ValueError(f"writable privileged executable: {path}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="SSR Panel privileged action helper")
    parser.add_argument("action", choices=sorted(ALLOWED_ACTIONS))
    args = parser.parse_args(argv)
    if os.geteuid() != 0:
        print("admin-helper must run as root", file=os.sys.stderr)
        return 1
    if args.action == "mudb-commit":
        commit_pending_mudb()
        return 0
    if args.action in {"ssr-start", "ssr-restart", "firewall-sync"}:
        ensure_mudb_permissions()
    if args.action == "firewall-sync":
        _assert_safe_root_file(FIREWALL_HELPER)
    if args.action == "panel-update":
        _assert_safe_root_file(PANEL_DIR / "scripts" / "run_panel_update.py")
        _assert_safe_root_file(PANEL_DIR / "update.sh")
    command = build_command(args.action)
    result = subprocess.run(
        command,
        check=False,
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C"},
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
