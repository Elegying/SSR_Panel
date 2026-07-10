import unittest
from pathlib import Path


PANEL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PANEL_ROOT.parent


class RepositoryPolicyTests(unittest.TestCase):
    def test_root_ci_covers_python_shell_and_supported_distros(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )

        for version in ("3.9", "3.11", "3.12"):
            self.assertIn(version, workflow)
        for image in ("ubuntu:22.04", "debian:12-slim", "rockylinux:9"):
            self.assertIn(image, workflow)
        self.assertIn("shellcheck", workflow)
        self.assertIn("compileall", workflow)
        self.assertIn("pip-audit", workflow)
        self.assertIn("cd ssr-admin-panel", workflow)
        self.assertIn("cd ssr-server-optimizer", workflow)

    def test_only_root_workflows_are_used(self):
        self.assertFalse((PANEL_ROOT / ".github" / "workflows" / "ci.yml").exists())
        self.assertFalse(
            (REPO_ROOT / "ssr-server-optimizer" / ".github" / "workflows" / "ci.yml").exists()
        )

    def test_release_metadata_and_operations_docs_match_new_defaults(self):
        self.assertEqual((PANEL_ROOT / "VERSION").read_text(encoding="utf-8").strip(), "1.3.0")
        changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        operations = (PANEL_ROOT / "docs" / "OPERATIONS.md").read_text(encoding="utf-8")

        self.assertIn("v1.3.0", changelog)
        self.assertIn("SSR_ADMIN_APPLY_SERVER_OPTIMIZATION=1", operations)
        self.assertIn("SSR_ADMIN_PATCH_SSR_COMPAT=1", operations)
        self.assertIn("HTTP 健康检查", operations)
        self.assertNotIn("更新脚本也会重新应用 SSR 服务端优化", operations)


if __name__ == "__main__":
    unittest.main()
