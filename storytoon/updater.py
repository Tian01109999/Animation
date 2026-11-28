"""In-app updates: check, download, verify and install full app + assets update packages.

A release is tagged `vX.Y.Z` and carries `StoryToon-Update-X.Y.Z.zip` plus `.sha256`.
The zip holds root-relative files (EXE, storytoon/, assets/) and an `update.json`
manifest: {"version": ..., "notes": ..., "delete": [paths removed since the last release]}.
The download source is built here and never shown to the user.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import threading
import zipfile
from typing import Callable
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import __version__, paths

REPOSITORY = 'Tian01109999/Animation'
ASSETS_VERSION_FILE = '.storytoon-assets-version.json'
EXE_NAME = 'StoryToon-Desktop-Portable.exe'
ALLOWED_ROOT_FILES = {EXE_NAME, EXE_NAME + '.config', 'README.md', 'update.json'}
ALLOWED_TREES = ('storytoon/', 'assets/')
_UA = {'User-Agent': 'StoryToon-Portable'}


def assets_version() -> str:
    try:
        value = json.loads((paths.ASSETS / ASSETS_VERSION_FILE).read_text(encoding='utf-8'))['version']
        version_tuple(value)
        return value
    except (OSError, ValueError, KeyError, TypeError):
        return '0.0.0'


def version_tuple(value: str) -> tuple[int, ...]:
    if not isinstance(value, str) or not re.fullmatch(r'v?\d+\.\d+\.\d+(?:\.\d+)?', value):
        raise ValueError('Phiên bản phát hành không hợp lệ.')
    parts = tuple(int(part) for part in value.removeprefix('v').split('.'))
    return parts + (0,) * (4 - len(parts))


def _package_name(version: str) -> str:
    return f'StoryToon-Update-{version}.zip'


def _download_url(version: str, name: str) -> str:
    return f'https://github.com/{REPOSITORY}/releases/download/v{version}/{name}'


def check_release() -> dict:
    """Newest stable update newer than this app. Never returns a link or source."""
    result = {'current': __version__, 'app_version': __version__, 'kind': 'app',
              'available': False, 'version': '', 'notes': '', 'error': ''}
    try:
        request = Request(f'https://api.github.com/repos/{REPOSITORY}/releases?per_page=100', headers={
            **_UA, 'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'})
        with urlopen(request, timeout=15) as response:
            releases = json.load(response)
        if not isinstance(releases, list):
            raise ValueError('Invalid release list')
        candidates = []
        for release in releases:
            if not isinstance(release, dict) or release.get('draft') or release.get('prerelease'):
                continue
            tag = release.get('tag_name', '')
            if not isinstance(tag, str) or not re.fullmatch(r'v\d+\.\d+\.\d+', tag):
                continue
            version = tag[1:]
            names = {a.get('name') for a in release.get('assets', [])
                     if isinstance(a, dict) and a.get('state') == 'uploaded'}
            package = _package_name(version)
            if package in names and package + '.sha256' in names:
                notes = release.get('body') if isinstance(release.get('body'), str) else ''
                candidates.append((version_tuple(version), version, notes))
        if not candidates:
            return result
        _, version, notes = max(candidates)
        result.update(version=version, notes=notes.strip()[:6000],
                      available=version_tuple(version) > version_tuple(__version__))
    except HTTPError as exc:
        result['error'] = ('Máy chủ cập nhật đang giới hạn lượt kiểm tra. Vui lòng thử lại sau.'
                           if exc.code == 403 else 'Không kiểm tra được bản cập nhật.')
    except (OSError, URLError, ValueError, TypeError, AttributeError):
        result['error'] = 'Không kiểm tra được cập nhật. Kiểm tra kết nối Internet và thử lại sau.'
    return result


def _safe_name(name: str) -> str | None:
    """Return the normalized member path if it may be installed, else None."""
    if name.endswith('/'):
        return None
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or ':' in name or '\\' in name:
        raise ValueError(f'Đường dẫn không hợp lệ trong gói: {name}')
    text = p.as_posix()
    if text in ALLOWED_ROOT_FILES or text.startswith(ALLOWED_TREES):
        return text
    raise ValueError(f'File không được phép trong gói: {name}')


Progress = Callable[[str, int, int], None]   # (stage, done, total)


def _fetch(url: str, dest: Path, progress: Progress | None = None) -> None:
    with urlopen(Request(url, headers=_UA), timeout=60) as response, dest.open('wb') as out:
        total = int(response.headers.get('Content-Length') or 0)
        done = 0
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            out.write(block)
            done += len(block)
            if progress:
                progress('download', done, total)


def install_package(package: Path, root: Path | None = None, progress: Progress | None = None) -> dict:
    """Validate and install an already-verified update zip into the app folder."""
    root = (root or paths.ROOT).resolve()
    with zipfile.ZipFile(package) as archive:
        if archive.testzip():
            raise ValueError('Gói cập nhật bị hỏng.')
        members = [(info, _safe_name(info.filename)) for info in archive.infolist()]
        manifest = json.loads(archive.read('update.json').decode('utf-8'))
        version = manifest['version']
        version_tuple(version)
        written = 0
        total = sum(1 for _, name in members if name and name != 'update.json')
        for info, name in members:
            if not name or name == 'update.json':
                continue
            if progress and written % 25 == 0:
                progress('install', written, total)
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + '.updating')
            with archive.open(info) as src, tmp.open('wb') as out:
                shutil.copyfileobj(src, out, 1024 * 1024)
            if name == EXE_NAME and target.exists():
                old = target.with_name(target.name + '.old')
                old.unlink(missing_ok=True)
                target.replace(old)          # a running EXE can be renamed, not overwritten
            tmp.replace(target)
            written += 1
    removed = 0
    for rel in manifest.get('delete', []):
        if not isinstance(rel, str) or not rel.startswith(ALLOWED_TREES) or '..' in rel:
            continue
        target = root / rel
        if target.is_file():
            target.unlink()
            removed += 1
            parent = target.parent
            while parent != root and parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent
    return {'version': version, 'written': written, 'removed': removed}


def download_and_install(version: str, progress: Progress | None = None) -> dict:
    """Download the package for `version`, verify SHA-256 and install it."""
    version_tuple(version)
    name = _package_name(version)
    with tempfile.TemporaryDirectory(prefix='storytoon-update-') as tmp:
        zip_path = Path(tmp) / name
        sha_path = Path(tmp) / (name + '.sha256')
        _fetch(_download_url(version, name + '.sha256'), sha_path)
        expected = sha_path.read_text(encoding='ascii').split()[0].lower()
        if not re.fullmatch(r'[0-9a-f]{64}', expected):
            raise ValueError('Mã kiểm tra của gói không hợp lệ.')
        _fetch(_download_url(version, name), zip_path, progress)
        if progress:
            progress('verify', 0, 0)
        with zip_path.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != expected:
            raise ValueError('Gói tải về không khớp mã kiểm tra. Hãy thử lại.')
        return install_package(zip_path, progress=progress)


# ---------------------------------------------------------------- background job (one at a time)
_job_lock = threading.Lock()
_job: dict = {'state': 'idle', 'version': '', 'stage': '', 'done': 0, 'total': 0, 'message': ''}


def job_status() -> dict:
    with _job_lock:
        return dict(_job)


def start_install(version: str, runner: Callable[..., dict] | None = None) -> bool:
    """Start downloading + installing `version` in the background. False if a job is already running."""
    version_tuple(version)
    with _job_lock:
        if _job['state'] in ('running', 'done'):
            return False
        _job.update(state='running', version=version, stage='download', done=0, total=0, message='')

    def report(stage: str, done: int, total: int) -> None:
        with _job_lock:
            _job.update(stage=stage, done=done, total=total)

    def work() -> None:
        try:
            result = (runner or download_and_install)(version, progress=report)
            with _job_lock:
                _job.update(state='done', stage='done', version=result.get('version', version))
        except Exception as exc:  # noqa: BLE001 - surfaced to the update page
            message = str(exc) if isinstance(exc, ValueError) else 'Không tải được gói cập nhật. Kiểm tra kết nối Internet và thử lại.'
            with _job_lock:
                _job.update(state='error', message=message)

    threading.Thread(target=work, name='storytoon-update', daemon=True).start()
    return True


def cleanup_previous() -> None:
    """Remove the EXE left over from the last update (called at startup)."""
    try:
        (paths.ROOT / (EXE_NAME + '.old')).unlink(missing_ok=True)
    except OSError:
        pass
    for leftover in paths.ROOT.glob('storytoon/**/*.updating'):
        try:
            leftover.unlink()
        except OSError:
            pass
