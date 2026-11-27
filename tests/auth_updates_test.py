"""Authentication boundary and private-release notification contracts."""
import sys
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

    def test_private_request_and_new_release(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"tag_name":"v0.3.0"}'
        with patch('storytoon.secure_store.read', return_value={'token': 'test-token'}), patch.object(updater, 'urlopen', return_value=response) as call:
            result = updater.check_release()
            self.assertTrue(result['available'])
            self.assertEqual(result['url'], 'https://github.com/Tian01109999/Animation/releases/tag/v0.3.0')
            self.assertEqual(call.call_args.args[0].get_header('Authorization'), 'Bearer test-token')
            self.assertNotIn('test-token', str(result))

    def test_no_token_or_network_failure_does_not_offer_update(self):
        with patch('storytoon.secure_store.read', return_value={}):
            self.assertFalse(updater.check_release()['available'])
        with patch('storytoon.secure_store.read', return_value={'token': 'test'}), patch.object(updater, 'urlopen', side_effect=OSError):
            self.assertTrue(updater.check_release()['error'])


if __name__ == '__main__':
    unittest.main()
