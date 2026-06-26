#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_status(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_command(args: list[str], cwd: Path, log_handle, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=str(cwd),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        check=False,
        env=env,
    )


def get_git_version(panel_dir: Path, ref: str = "HEAD") -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", ref],
        cwd=str(panel_dir),
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode == 0:
        return result.stdout.strip() or "unknown"

    version_file = panel_dir / "VERSION"
    if version_file.exists():
        return version_file.read_text(encoding="utf-8").strip() or "unknown"
    return "unknown"


def update_from_script(
    panel_dir: Path,
    branch: str,
    repo_url: str,
    status_file: Path,
    log_handle,
) -> tuple[bool, str]:
    update_script = panel_dir / "update.sh"
    if not update_script.exists():
        return False, f"未找到更新脚本: {update_script}"

    env = os.environ.copy()
    if repo_url:
        env["SSR_ADMIN_REPO_URL"] = repo_url
    env["SSR_ADMIN_UPDATE_REF"] = branch
    env["SSR_ADMIN_UPDATE_STATUS_FILE"] = str(status_file)
    result = run_command(["bash", str(update_script), branch], panel_dir, log_handle, env=env)
    if result.returncode != 0:
        return False, "update.sh 执行失败"
    return True, "脚本更新完成"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run SSR Admin Panel update")
    parser.add_argument("--panel-dir", required=True)
    parser.add_argument("--status-file", required=True)
    parser.add_argument("--log-file", required=True)
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--repo-url", default="")
    parser.add_argument("--service", default="ssr-admin")
    args = parser.parse_args()

    panel_dir = Path(args.panel_dir).resolve()
    status_file = Path(args.status_file).resolve()
    log_file = Path(args.log_file).resolve()

    status = {
        "in_progress": True,
        "started_at": utc_now(),
        "finished_at": None,
        "message": "更新任务已启动",
        "current_version": get_git_version(panel_dir),
        "latest_version": None,
        "last_exit_code": None,
        "branch": args.branch,
        "remote": args.remote,
        "repo_url": args.repo_url,
        "phase": "queued",
        "backup_dir": "",
        "rollback_attempted": False,
        "rollback_success": False,
    }
    write_status(status_file, status)

    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as log_handle:
        log_handle.write(f"\n[{utc_now()}] Starting panel update\n")
        log_handle.flush()

        ok, message = update_from_script(
            panel_dir,
            args.branch,
            args.repo_url,
            status_file,
            log_handle,
        )

        exit_code = 0 if ok else 1
        try:
            latest_status = json.loads(status_file.read_text(encoding="utf-8"))
            if isinstance(latest_status, dict):
                status.update(latest_status)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass

        status.update(
            {
                "in_progress": False,
                "finished_at": utc_now(),
                "message": status.get("message") if ok else message,
                "current_version": get_git_version(panel_dir),
                "latest_version": get_git_version(panel_dir, f"{args.remote}/{args.branch}")
                if (panel_dir / ".git").is_dir()
                else None,
                "last_exit_code": exit_code,
                "phase": "done" if ok else status.get("phase", "failed"),
                "backup_dir": status.get("backup_dir", ""),
                "rollback_attempted": bool(status.get("rollback_attempted", False)),
                "rollback_success": bool(status.get("rollback_success", False)),
            }
        )
        write_status(status_file, status)
        log_handle.write(f"[{utc_now()}] Update finished with exit code {exit_code}\n")
        log_handle.flush()

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
