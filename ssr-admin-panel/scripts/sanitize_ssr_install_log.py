#!/usr/bin/env python3
"""Remove generated credentials from the root-only SSR installation log."""

import os
import re
import sys
import tempfile
from pathlib import Path


SSR_LINK_PATTERN = re.compile(r"ssr://[A-Za-z0-9_=-]+")


def sanitize_install_log(log_path: Path, password_path: Path) -> None:
    if log_path.is_symlink() or password_path.is_symlink():
        raise ValueError("refusing to read or replace a symlink")
    if not log_path.is_file() or not password_path.is_file():
        raise ValueError("installation log or initial password file is missing")

    password = password_path.read_text(encoding="utf-8").strip()
    text = log_path.read_text(encoding="utf-8", errors="replace")
    if password:
        text = text.replace(password, "[redacted]")
    text = SSR_LINK_PATTERN.sub("ssr://[redacted]", text)

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=log_path.name + ".sanitize-",
        suffix=".tmp",
        dir=str(log_path.parent),
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(str(temporary), 0o600)
        os.replace(str(temporary), str(log_path))
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    if len(sys.argv) != 3:
        print(
            "usage: sanitize_ssr_install_log.py LOG_PATH INITIAL_PASSWORD_FILE",
            file=sys.stderr,
        )
        return 2
    try:
        sanitize_install_log(Path(sys.argv[1]), Path(sys.argv[2]))
    except (OSError, UnicodeError, ValueError) as exc:
        print("failed to sanitize SSR install log: {}".format(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
