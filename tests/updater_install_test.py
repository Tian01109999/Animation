"""In-app updater installs a full package safely and the update page hides the source."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from storytoon import updater


def make_zip(path: Path, files: dict, manifest: dict) -> None:
    with zipfile.ZipFile(path, 'w') as z:
        for name, data in files.items():
            z.writestr(name, data)
        z.writestr('update.json', json.dumps(manifest))


class InstallTests(unittest.TestCase):
    def test_install_writes_renames_exe_and_deletes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'assets/locations/old').mkdir(parents=True)
            (root / 'assets/locations/old/location.json').write_text('x')
            (root / updater.EXE_NAME).write_bytes(b'old-exe')
            (root / 'projects').mkdir()
            (root / 'projects/keep.txt').write_text('mine')
            pkg = root / 'u.zip'
            make_zip(pkg, {updater.EXE_NAME: b'new-exe', 'storytoon/a.py': 'A=1',
                           'assets/characters/x/character.json': '{}'},
                     {'version': '9.9.9', 'notes': 'n',
                      'delete': ['assets/locations/old/location.json', 'projects/keep.txt', '../evil']})
            done = updater.install_package(pkg, root)
            self.assertEqual(done['version'], '9.9.9')
            self.assertEqual((root / updater.EXE_NAME).read_bytes(), b'new-exe')
            self.assertEqual((root / (updater.EXE_NAME + '.old')).read_bytes(), b'old-exe')
            self.assertTrue((root / 'storytoon/a.py').exists())
            self.assertFalse((root / 'assets/locations/old').exists())
            self.assertTrue((root / 'projects/keep.txt').exists())

    def test_rejects_paths_outside_allowed_trees(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for bad in ('../x.txt', 'projects/p.json', 'config.yaml', 'runtime/python/python.exe'):
                pkg = root / 'bad.zip'
                make_zip(pkg, {bad: 'x'}, {'version': '9.9.9'})
                with self.assertRaises(ValueError):
                    updater.install_package(pkg, root)
            self.assertFalse((root.parent / 'x.txt').exists())

    def test_check_release_returns_notes_without_url(self):
        releases = [{'tag_name': 'v99.0.0', 'body': 'Thay đổi A', 'assets': [
            {'name': 'StoryToon-Update-99.0.0.zip', 'state': 'uploaded'},
            {'name': 'StoryToon-Update-99.0.0.zip.sha256', 'state': 'uploaded'}]},
            {'tag_name': 'assets-v5.0.0', 'assets': []}]

        class Resp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, *a): return json.dumps(releases).encode()
        with patch.object(updater, 'urlopen', return_value=Resp()):
            r = updater.check_release()
        self.assertTrue(r['available'])
        self.assertEqual(r['version'], '99.0.0')
        self.assertEqual(r['notes'], 'Thay đổi A')
        self.assertNotIn('url', r)
        self.assertNotIn('github', json.dumps(r).lower())


class BackgroundJobTests(unittest.TestCase):
    def setUp(self):
        updater._job.update(state='idle', version='', stage='', done=0, total=0, message='')

    def wait(self):
        import time
        for _ in range(100):
            if updater.job_status()['state'] != 'running':
                return updater.job_status()
            time.sleep(0.05)
        self.fail('job did not finish')

    def test_job_reports_progress_then_done_and_blocks_second_start(self):
        def runner(version, progress):
            progress('download', 50, 100)
            progress('install', 3, 10)
            return {'version': version}
        self.assertTrue(updater.start_install('9.9.9', runner=runner))
        state = self.wait()
        self.assertEqual((state['state'], state['version']), ('done', '9.9.9'))
        self.assertFalse(updater.start_install('9.9.9', runner=runner))   # chờ khởi động lại

    def test_job_error_allows_retry(self):
        def broken(version, progress):
            raise OSError('net down')
        updater.start_install('9.9.9', runner=broken)
        state = self.wait()
        self.assertEqual(state['state'], 'error')
        self.assertIn('Internet', state['message'])
        self.assertTrue(updater.start_install('9.9.9', runner=lambda v, progress: {'version': v}))
        self.wait()

    def test_portal_auto_start_progress_and_desktop_state(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from storytoon import update_portal
        app = FastAPI()
        token = 'T' * 40
        update_portal.attach(app, token)
        client = TestClient(app)
        available = {'current': '1.0.0', 'app_version': '1.0.0', 'kind': 'app', 'available': True,
                     'version': '9.9.9', 'notes': 'Thay đổi A', 'error': ''}
        started = []
        with patch.object(updater, 'check_release', return_value=available), \
             patch.object(updater, 'start_install', side_effect=lambda v: started.append(v) or True):
            page = client.get('/updates?start=1').text
            self.assertIn('Thay đổi A', page)
            self.assertIn('.submit()', page)                       # tự bấm Cập nhật ngay
            self.assertNotIn('github', page.lower())
            csrf = client.cookies.get('storytoon_update_csrf')
            page = client.post('/updates', data={'csrf': csrf, 'action': 'install', 'version': '9.9.9'}).text
            self.assertEqual(started, ['9.9.9'])
            self.assertIn('restart-after-update', page)
            self.assertIn('/updates/status', page)
        self.assertEqual(client.get('/__desktop__/update-state').status_code, 403)
        state = client.get('/__desktop__/update-state', headers={'X-StoryToon-Desktop': token}).json()
        self.assertIn('state', state)


if __name__ == '__main__':
    unittest.main()
