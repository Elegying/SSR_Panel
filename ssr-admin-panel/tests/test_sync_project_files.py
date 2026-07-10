import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PANEL_ROOT = Path(__file__).resolve().parent.parent
SYNC_SCRIPT = PANEL_ROOT / "scripts" / "sync_project_files.py"


class SyncProjectFilesTests(unittest.TestCase):
    def test_overlay_preserves_local_files_without_following_target_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            source = base / "source"
            target = base / "target"
            outside = base / "outside"
            (source / "assets").mkdir(parents=True)
            target.mkdir()
            outside.mkdir()
            (source / "assets" / "new.txt").write_text("new\n", encoding="utf-8")
            (target / "local.txt").write_text("keep\n", encoding="utf-8")
            (outside / "sentinel.txt").write_text("safe\n", encoding="utf-8")
            (target / "assets").symlink_to(outside, target_is_directory=True)

            result = subprocess.run(
                [sys.executable, str(SYNC_SCRIPT), str(source), str(target)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertEqual((target / "local.txt").read_text(encoding="utf-8"), "keep\n")
            self.assertFalse((target / "assets").is_symlink())
            self.assertEqual((target / "assets" / "new.txt").read_text(encoding="utf-8"), "new\n")
            self.assertEqual((outside / "sentinel.txt").read_text(encoding="utf-8"), "safe\n")
            self.assertFalse((outside / "new.txt").exists())

    def test_rejects_a_symlink_as_the_target_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            source = base / "source"
            outside = base / "outside"
            source.mkdir()
            outside.mkdir()
            (source / "app.py").write_text("# app\n", encoding="utf-8")
            target = base / "target"
            target.symlink_to(outside, target_is_directory=True)

            result = subprocess.run(
                [sys.executable, str(SYNC_SCRIPT), str(source), str(target)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((outside / "app.py").exists())

    def test_rejects_target_path_through_parent_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            source = base / "source"
            real_parent = base / "real-parent"
            linked_parent = base / "linked-parent"
            source.mkdir()
            real_parent.mkdir()
            linked_parent.symlink_to(real_parent, target_is_directory=True)
            (source / "app.py").write_text("# app\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SYNC_SCRIPT),
                    str(source),
                    str(linked_parent / "target"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((real_parent / "target" / "app.py").exists())

    def test_rejects_source_symlinks_instead_of_copying_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            source = base / "source"
            target = base / "target"
            outside = base / "outside"
            source.mkdir()
            target.mkdir()
            outside.mkdir()
            (outside / "secret.txt").write_text("outside\n", encoding="utf-8")
            (source / "unsafe-link").symlink_to(outside, target_is_directory=True)

            result = subprocess.run(
                [sys.executable, str(SYNC_SCRIPT), str(source), str(target)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((target / "unsafe-link").exists())


if __name__ == "__main__":
    unittest.main()
