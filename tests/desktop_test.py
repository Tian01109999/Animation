"""Desktop backend contract: activity protection, native readiness and private files."""
from __future__ import annotations
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storytoon import activity, paths


class ActivityTests(unittest.TestCase):
    def test_nested_work_and_exception_release(self):
        self.assertFalse(activity.busy())
        with self.assertRaisesRegex(ValueError, 'test'):
            with activity.work():
                self.assertTrue(activity.busy())
                with activity.work():
                    self.assertTrue(activity.busy())
                self.assertTrue(activity.busy())
                raise ValueError('test')
        self.assertFalse(activity.busy())


class DesktopBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from storytoon.desktop_server import build_app
        cls.client = TestClient(build_app('desktop-test-token-01234567890123456789'))

    def test_readiness_requires_native_session_token(self):
        self.assertEqual(self.client.get('/__desktop__/status').status_code, 403)
        headers = {'X-StoryToon-Desktop': 'desktop-test-token-01234567890123456789'}
        self.assertEqual(self.client.get('/__desktop__/status', headers=headers).json()['busy'], False)
        with activity.work():
            self.assertEqual(self.client.get('/__desktop__/status', headers=headers).json()['busy'], True)

    def test_full_backend_requires_login(self):
        self.assertEqual(self.client.get('/config').status_code, 401)
        self.assertEqual(self.client.get('/updates').status_code, 401)

    @patch('storytoon.login_portal.LoginPortal.validate', return_value=SimpleNamespace(email='test@example.com'))
    def test_native_ui_keeps_existing_tabs_and_blocks_configuration_download(self, _validate):
        response = self.client.get('/config')
        self.assertEqual(response.status_code, 200)
        for title in ['Kịch bản', 'Kho assets', 'Xuất phim']:
            self.assertIn(title, response.text)
        labels=[c.get('props',{}).get('label','') for c in response.json().get('components',[])]
        tabs=[c.get('props',{}).get('label') for c in response.json()['components'] if c['type']=='tabitem']
        self.assertNotIn('Storyboard',tabs)
        self.assertNotIn('Gemini',response.text)
        self.assertNotIn('Người que',response.text)
        self.assertIn('Đăng xuất GPT',response.text)
        self.assertIn('project-trash',response.json().get('js',''))
        self.assertIn('#project-picker',response.json().get('css',''))
        self.assertFalse(any('Flow' in str(label) for label in labels))
        self.assertTrue(any('AI phân tích và gán assets' in str(c.get('props',{}).get('value',''))
                            for c in response.json().get('components',[])))
        private = self.client.get('/gradio_api/file=' + paths.CONFIG_FILE.as_posix())
        self.assertIn(private.status_code, [403, 404])


if __name__ == '__main__':
    unittest.main()
