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
        self.assertIn("actionlint", workflow)
        self.assertIn("cd ssr-admin-panel", workflow)
        self.assertIn("cd ssr-server-optimizer", workflow)

    def test_only_root_workflows_are_used(self):
        self.assertFalse((PANEL_ROOT / ".github" / "workflows" / "ci.yml").exists())
        self.assertFalse(
            (REPO_ROOT / "ssr-server-optimizer" / ".github" / "workflows" / "ci.yml").exists()
        )

    def test_release_metadata_and_operations_docs_match_new_defaults(self):
        self.assertEqual((PANEL_ROOT / "VERSION").read_text(encoding="utf-8").strip(), "1.3.1")
        changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        operations = (PANEL_ROOT / "docs" / "OPERATIONS.md").read_text(encoding="utf-8")

        self.assertIn("v1.3.1", changelog)
        self.assertIn("SSR_ADMIN_APPLY_SERVER_OPTIMIZATION=1", operations)
        self.assertIn("SSR_ADMIN_PATCH_SSR_COMPAT=1", operations)
        self.assertIn("HTTP 健康检查", operations)
        self.assertNotIn("更新脚本也会重新应用 SSR 服务端优化", operations)

    def test_download_examples_save_the_optimizer_before_running_it(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        guide = (REPO_ROOT / "USER_GUIDE.md").read_text(encoding="utf-8")

        optimizer_url = (
            "https://raw.githubusercontent.com/Elegying/SSR_Panel/main/"
            "ssr-server-optimizer/optimize-ssr.sh"
        )
        self.assertIn(f"wget -O optimize-ssr.sh {optimizer_url}", readme)
        self.assertIn(f"curl -fsSL {optimizer_url} -o optimize-ssr.sh", guide)
        self.assertNotIn(f"curl -fsSL {optimizer_url} | bash", guide)

    def test_docs_describe_distro_jobs_as_x86_64_container_smoke(self):
        documents = (
            REPO_ROOT / "README.md",
            PANEL_ROOT / "README.md",
            PANEL_ROOT / "docs" / "OPERATIONS.md",
        )
        for document in documents:
            with self.subTest(document=document.name):
                content = document.read_text(encoding="utf-8")
                self.assertIn("x86_64 容器冒烟", content)
                self.assertIn("ARM64 未在 CI 实机验证", content)


if __name__ == "__main__":
    unittest.main()
