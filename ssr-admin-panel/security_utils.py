#!/usr/bin/env python3
import argparse
import ast
import base64
import hashlib
import hmac
import os
import secrets
import stat
import sys
import tempfile
from pathlib import Path


ALGORITHM = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 600_000
MIN_ITERATIONS = 100_000
MAX_ITERATIONS = 2_000_000
SALT_BYTES = 16


def _encode(value):
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value):
    padding = "=" * (-len(value) % 4)
    return base64.b64decode((value + padding).encode("ascii"), altchars=b"-_", validate=True)


def _parse_password_hash(encoded):
    if not isinstance(encoded, str):
        raise ValueError("password hash must be a string")
    algorithm, iteration_text, salt_text, digest_text = encoded.split("$")
    if algorithm != ALGORITHM or not iteration_text.isdigit():
        raise ValueError("unsupported password hash")
    iterations = int(iteration_text)
    if not MIN_ITERATIONS <= iterations <= MAX_ITERATIONS:
        raise ValueError("unsafe PBKDF2 iteration count")
    salt = _decode(salt_text)
    digest = _decode(digest_text)
    if len(salt) < SALT_BYTES or len(digest) != hashlib.sha256().digest_size:
        raise ValueError("invalid password hash length")
    return iterations, salt, digest


def hash_password(password, iterations=DEFAULT_ITERATIONS):
    if not isinstance(password, str):
        raise TypeError("password must be a string")
    if not MIN_ITERATIONS <= iterations <= MAX_ITERATIONS:
        raise ValueError("unsafe PBKDF2 iteration count")
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{ALGORITHM}${iterations}${_encode(salt)}${_encode(digest)}"


def verify_password(password, encoded):
    if not isinstance(password, str):
        return False
    try:
        iterations, salt, expected = _parse_password_hash(encoded)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    except (TypeError, ValueError, UnicodeError):
        return False
    return hmac.compare_digest(actual, expected)


def _literal_assignment(node, name):
    if not isinstance(node, ast.Assign) or len(node.targets) != 1:
        return None
    target = node.targets[0]
    if not isinstance(target, ast.Name) or target.id != name:
        return None
    if getattr(node, "end_lineno", node.lineno) != node.lineno:
        raise ValueError(f"{name} must use a single-line string literal")
    try:
        value = ast.literal_eval(node.value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must use a string literal") from exc
    if not isinstance(value, str):
        raise ValueError(f"{name} must use a string literal")
    return node.lineno - 1, value


def _write_atomic(path, content, file_stat):
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        os.fchmod(fd, stat.S_IMODE(file_stat.st_mode))
        if hasattr(os, "fchown"):
            try:
                os.fchown(fd, file_stat.st_uid, file_stat.st_gid)
            except PermissionError:
                pass
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, str(path))
        temp_name = None
    finally:
        if fd >= 0:
            os.close(fd)
        if temp_name:
            try:
                os.unlink(temp_name)
            except OSError:
                pass


def migrate_config(config_path):
    path = Path(config_path)
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    password_entries = []
    hash_entries = []
    for node in tree.body:
        password = _literal_assignment(node, "ADMIN_PASS")
        if password is not None:
            password_entries.append(password)
        password_hash = _literal_assignment(node, "ADMIN_PASSWORD_HASH")
        if password_hash is not None:
            hash_entries.append(password_hash)

    if len(password_entries) > 1 or len(hash_entries) > 1:
        raise ValueError("duplicate administrator password assignments")
    if not password_entries and not hash_entries:
        raise ValueError("config has no administrator password")
    if hash_entries:
        _parse_password_hash(hash_entries[0][1])
        if not password_entries:
            return False

    lines = source.splitlines(keepends=True)
    if hash_entries:
        del lines[password_entries[0][0]]
    else:
        line_index, password = password_entries[0]
        newline = "\n" if lines[line_index].endswith("\n") else ""
        lines[line_index] = f"ADMIN_PASSWORD_HASH = {hash_password(password)!r}{newline}"
    _write_atomic(path, "".join(lines), path.stat())
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description="SSR Panel password utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("hash", help="read a password from stdin and print its hash")
    migrate_parser = subparsers.add_parser("migrate-config", help="replace legacy ADMIN_PASS")
    migrate_parser.add_argument("config_path")
    args = parser.parse_args(argv)

    if args.command == "hash":
        password = sys.stdin.read()
        if not password:
            parser.error("password input is empty")
        print(hash_password(password))
        return 0

    changed = migrate_config(args.config_path)
    print("migrated" if changed else "already hashed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
