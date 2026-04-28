#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path


LEGACY_COLLECTIONS_ALIASES = {
    "collections.MutableMapping": "collections.abc.MutableMapping",
    "collections.Mapping": "collections.abc.Mapping",
    "collections.MutableSet": "collections.abc.MutableSet",
    "collections.Set": "collections.abc.Set",
    "collections.MutableSequence": "collections.abc.MutableSequence",
    "collections.Sequence": "collections.abc.Sequence",
    "collections.Iterable": "collections.abc.Iterable",
    "collections.Iterator": "collections.abc.Iterator",
    "collections.Callable": "collections.abc.Callable",
}

LEGACY_LITERAL_COMPARISONS = {
    'addr is ""': 'addr == ""',
    "len(block) is 1": "len(block) == 1",
    "ip is not 0": "ip != 0",
}


def patch_python_file(file_path: Path) -> bool:
    try:
        original = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        original = file_path.read_text(encoding="utf-8", errors="ignore")

    updated = original
    for old, new in LEGACY_COLLECTIONS_ALIASES.items():
        updated = updated.replace(old, new)

    for old, new in LEGACY_LITERAL_COMPARISONS.items():
        updated = updated.replace(old, new)

    if updated == original:
        return False

    file_path.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    target_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "/usr/local/shadowsocksr")
    if not target_dir.exists():
        print(f"[compat] SSR directory not found: {target_dir}", file=sys.stderr)
        return 1

    patched_files = []
    for file_path in sorted(target_dir.rglob("*.py")):
        if patch_python_file(file_path):
            patched_files.append(file_path)

    if patched_files:
        print(f"[compat] Patched {len(patched_files)} file(s) in {target_dir}")
        for file_path in patched_files:
            print(f"[compat] updated: {file_path}")
    else:
        print(f"[compat] No legacy collections aliases found in {target_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
