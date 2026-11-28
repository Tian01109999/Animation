"""Authentication boundary and public assets notification contracts."""
import sys
import json
import tempfile
import zipfile
from pathlib import Path
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from storytoon import auth_24media as auth, updater
from storytoon.login_portal import attach, LoginPortal
from storytoon.update_portal import attach as attach_updates


class PortalTests(unittest.TestCase):
    def setUp(self):
        self.portal = LoginPortal()
        app = FastAPI()
        attach(app, self.portal)
        attach_updates(app, 'native-secret')
        @app.get('/config')
        def config():
            return {'protected': True}
        self.client = TestClient(app)

    def test_private_routes_require_login(self):
        for path in ('/config', '/updates', '/gradio_api/file=config.yaml'):
            self.assertEqual(self.client.get(path, headers={'Accept': 'application/json'}).status_code, 401)
        self.assertIn('Đăng nhập 24Media', self.client.get('/').text)

    def test_login_csrf_and_logout(self):
        self.assertEqual(self.client.post('/account/login', data={'email': 'x@y.com'}).status_code, 403)
        self.client.get('/account/login')
        with patch.object(auth, 'sign_in', return_value=auth.AuthSession('u', 'x@y.com', 'id', 'refresh')), patch('storytoon.secure_store.remove'):
            response = self.client.post('/account/login', data={'email': 'x@y.com', 'password': 'example', 'csrf': self.client.cookies['storytoon_csrf']}, follow_redirects=False)
            self.assertEqual(response.status_code, 303)
            self.assertEqual(self.client.get('/config').status_code, 200)
            self.client.get('/account')
            self.client.post('/account/logout', data={'csrf': self.client.cookies['storytoon_csrf']})
            self.assertEqual(self.client.get('/config').status_code, 401)

    def test_update_api_requires_native_token(self):
        self.assertEqual(self.client.get('/__desktop__/updates').status_code, 403)
        with patch.object(updater, 'check_release', return_value={'available': False}):
            self.assertEqual(self.client.get('/__desktop__/updates', headers={'X-StoryToon-Desktop': 'native-secret'}).json(), {'available': False})

    def test_revoked_session_is_removed(self):
        with patch('storytoon.secure_store.read', return_value={'project': self.portal.config.project_id, 'sid': 'test', 'expires': 9999999999, 'session': {'uid': 'u', 'email': 'x@y.com', 'id_token': 'i', 'refresh_token': 'r'}}), patch.object(auth, 'refresh_access', side_effect=auth.AccessDenied('revoked')), patch('storytoon.secure_store.remove') as remove:
            with self.assertRaises(auth.AccessDenied):
                self.portal.validate('test')
            remove.assert_called_once()


class UpdatesTests(unittest.TestCase):
    def test_numeric_versions(self):
        self.assertGreater(updater.version_tuple('v0.10.0'), updater.version_tuple('0.9.9'))
        self.assertEqual(updater.version_tuple('0.2.0'), updater.version_tuple('v0.2.0.0'))
        for value in ('latest', '1.0.0/../../evil', '1.0.0-rc1'):
            with self.assertRaises(ValueError):
                updater.version_tuple(value)

    def test_public_request_and_new_release_needs_no_credentials(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps([
            {'tag_name': 'v99.1.0', 'assets': [
                {'name': 'StoryToon-Update-99.1.0.zip', 'state': 'uploaded'},
                {'name': 'StoryToon-Update-99.1.0.zip.sha256', 'state': 'uploaded'}]}
        ]).encode()
        with patch('storytoon.secure_store.read', side_effect=AssertionError('Must not read credentials')), patch.object(updater, 'urlopen', return_value=response) as call:
            result = updater.check_release()
            self.assertTrue(result['available'])
            self.assertEqual(result['version'], '99.1.0')
            self.assertEqual(result['kind'], 'app')
            self.assertNotIn('url', result)
            self.assertIsNone(call.call_args.args[0].get_header('Authorization'))

    def test_app_versions_ignore_assets_tags_drafts_and_incomplete_packages(self):
        def release(version, **kwargs):
            return dict(tag_name='v' + version, assets=[
                {'name': f'StoryToon-Update-{version}.zip', 'state': 'uploaded'},
                {'name': f'StoryToon-Update-{version}.zip.sha256', 'state': 'uploaded'}], **kwargs)
        metadata = [release('92.0.0', draft=True), release('93.0.0', prerelease=True),
                    {'tag_name': 'assets-v99.0.0'}, {'tag_name': 'v95.0.0', 'assets': []},
                    release('1.2.0'), release('1.10.0')]
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(metadata).encode()
        with patch.object(updater, 'urlopen', return_value=response), patch.object(updater, '__version__', '1.10.0'):
            result = updater.check_release()
            self.assertEqual(result['version'], '1.10.0')
            self.assertFalse(result['available'])

    def test_assets_pack_contains_only_assets_and_installed_version_marker(self):
        from tools.prepare_assets_release import build
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'assets').mkdir()
            (root / 'assets' / 'picture.png').write_bytes(b'asset')
            (root / 'personal.txt').write_text('private')
            output = build('1.0.0', root)
            with zipfile.ZipFile(output) as archive:
                self.assertTrue(all(name.startswith('assets/') for name in archive.namelist()))
                self.assertNotIn('personal.txt', archive.namelist())
                self.assertEqual(json.loads(archive.read('assets/' + updater.ASSETS_VERSION_FILE))['version'], '1.0.0')
            with patch.object(updater.paths, 'ASSETS', root / 'assets'):
                self.assertEqual(updater.assets_version(), '1.0.0')
                (root / 'assets' / updater.ASSETS_VERSION_FILE).unlink()
                self.assertEqual(updater.assets_version(), '0.0.0')
            self.assertTrue(output.with_suffix('.zip.sha256').exists())

    def test_network_failure_does_not_offer_update(self):
        with patch.object(updater, 'urlopen', side_effect=OSError):
            self.assertTrue(updater.check_release()['error'])


if __name__ == '__main__':
    unittest.main()
