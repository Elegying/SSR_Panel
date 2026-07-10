import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parent.parent
RUNNER_PATH = REPO_ROOT / "scripts" / "run_panel_update.py"
SPEC = importlib.util.spec_from_file_location("run_panel_update", RUNNER_PATH)
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class UpdateRunnerTests(unittest.TestCase):
    def test_update_script_receives_selected_panel_service_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            panel_dir = Path(tmp)
            (panel_dir / "update.sh").write_text("#!/bin/sh\n", encoding="utf-8")
            status_file = panel_dir / "status.json"
            log_file = panel_dir / "update.log"

            with log_file.open("w", encoding="utf-8") as log_handle, mock.patch.object(
                RUNNER,
                "run_command",
                return_value=mock.Mock(returncode=0),
            ) as run_command:
                ok, _message = RUNNER.update_from_script(
                    panel_dir,
                    "main",
                    "https://example.invalid/repo.git",
                    "ssr-admin-panel",
                    "custom-panel",
                    status_file,
                    log_handle,
                )

        self.assertTrue(ok)
        self.assertEqual(run_command.call_args.kwargs["env"]["SSR_ADMIN_SERVICE_NAME"], "custom-panel")


if __name__ == "__main__":
    unittest.main()
