import subprocess
import unittest
from pathlib import Path
from unittest import mock
from types import SimpleNamespace

import app as panel
from scripts import admin_helper
import test_app


class ErrorPrivacyTests(unittest.TestCase):
    setUp = test_app.AppSecurityTests.setUp
    tearDown = test_app.AppSecurityTests.tearDown
    detail = '/private/internal/token=secret-fixture'

    def test_process_failures_do_not_expose_paths_or_commands(self):
        for function in (panel.run_process, panel.run_capture_process):
            for failure in (OSError(self.detail), subprocess.TimeoutExpired(self.detail, 1)):
                with self.subTest(function=function.__name__, failure=type(failure).__name__):
                    with mock.patch.object(panel.subprocess, 'run', side_effect=failure):
                        result = function(['fixture'])
                    self.assertFalse(result['success'])
                    self.assertNotIn(self.detail, str(result))
                    self.assertTrue(result['error'])

    def test_log_failure_does_not_expose_filesystem_detail(self):
        with mock.patch.object(Path, 'open', side_effect=OSError(self.detail)):
            result = panel.read_log_tail(10)
        self.assertFalse(result['success'])
        self.assertNotIn(self.detail, str(result))

    def test_backup_endpoints_do_not_expose_storage_errors(self):
        cases = [('/api/backup', 'post', 'mkdir'), ('/api/backups/list', 'get', 'exists')]
        for route, method, operation in cases:
            with self.subTest(route=route):
                with mock.patch.object(Path, operation, side_effect=OSError(self.detail)):
                    response = getattr(self.client, method)(route, headers={'X-CSRF-Token': 'test-token'})
                self.assertEqual(response.status_code, 500)
                self.assertNotIn(self.detail, response.get_data(as_text=True))
                self.assertFalse(response.get_json()['success'])

    def test_share_failure_does_not_echo_arbitrary_parser_error(self):
        with mock.patch.object(panel, 'load_users', return_value=[{'user': 'fixture'}]), \
                mock.patch.object(panel, 'build_ssr_share_url', side_effect=ValueError(self.detail)):
            response = self.client.post('/api/share/fixture', headers={'X-CSRF-Token': 'test-token'})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn(self.detail, response.get_data(as_text=True))

    def test_update_status_write_failure_is_safe(self):
        info = {'success': True, 'update_available': True,
                'current_version': 'old', 'latest_version': 'new'}
        with mock.patch.object(panel, 'collect_panel_update_info', return_value=info), \
                mock.patch.object(panel, 'read_panel_update_status', return_value={'in_progress': False}), \
                mock.patch.object(Path, 'mkdir', side_effect=OSError(self.detail)):
            result = panel.start_panel_update()
        self.assertFalse(result['success'])
        self.assertNotIn(self.detail, str(result))


class PanelGroupTests(unittest.TestCase):
    def check_group(self, members=(), other_gid=101, uid=100, gid=100):
        account = SimpleNamespace(pw_name='ssr-panel', pw_uid=uid, pw_gid=gid)
        other = SimpleNamespace(pw_name='unrelated', pw_gid=other_gid)
        group = SimpleNamespace(gr_name='ssr-panel', gr_mem=list(members))
        with mock.patch.object(admin_helper.pwd, 'getpwnam', return_value=account), \
                mock.patch.object(admin_helper.pwd, 'getpwall', return_value=[account, other]), \
                mock.patch.object(admin_helper.grp, 'getgrgid', return_value=group):
            return admin_helper._panel_reader_gid()

    def test_dedicated_reader_is_allowed(self):
        self.assertEqual(self.check_group(), 100)
        self.assertEqual(self.check_group(members=['ssr-panel']), 100)

    def test_shared_or_root_group_is_rejected(self):
        for settings in ({'members': ['other']}, {'other_gid': 100}, {'uid': 0}, {'gid': 0}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                self.check_group(**settings)
