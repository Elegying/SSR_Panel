#!/usr/bin/env python3
"""Overlay managed project files without traversing target symlinks."""

import shutil
import sys
from pathlib import Path


def remove_path(path):
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def validate_source_directory(source):
    for source_item in source.iterdir():
        if source_item.is_symlink():
            raise SystemExit(f"refusing source symlink: {source_item}")
        if source_item.is_dir():
            validate_source_directory(source_item)


def copy_directory(source, target):
    target.mkdir(parents=True, exist_ok=True)
    for source_item in source.iterdir():
        target_item = target / source_item.name
        if target_item.is_symlink():
            remove_path(target_item)

        if source_item.is_dir() and not source_item.is_symlink():
            if target_item.exists() and not target_item.is_dir():
                remove_path(target_item)
            copy_directory(source_item, target_item)
            continue

        if target_item.exists() and target_item.is_dir():
            remove_path(target_item)
        target_item.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_item, target_item, follow_symlinks=False)


def main(argv):
    if len(argv) != 3:
        raise SystemExit("usage: sync_project_files.py SOURCE TARGET")

    source = Path(argv[1])
    target = Path(argv[2])
    if not source.is_dir() or source.is_symlink():
        raise SystemExit(f"invalid source directory: {source}")
    if target.is_symlink():
        raise SystemExit(f"refusing symlink target directory: {target}")

    validate_source_directory(source)
    copy_directory(source, target)


if __name__ == "__main__":
    main(sys.argv)
