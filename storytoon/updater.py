"""Read private GitHub Releases using a per-Windows-user encrypted credential."""
from __future__ import annotations

import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import __version__, secure_store

REPOSITORY = 'Tian01109999/Animation'
STORE = 'github-updates.dat'


def version_tuple(value: str) -> tuple[int, ...]:
    if not isinstance(value, str) or not re.fullmatch(r'v?\d+\.\d+\.\d+(?:\.\d+)?', value):
        raise ValueError('Phiên bản phát hành không hợp lệ.')
    parts = tuple(int(part) for part in value.removeprefix('v').split('.'))
    return parts + (0,) * (4 - len(parts))


def save_token(token: str) -> None:
    token = token.strip()
    if not token or len(token) > 1024 or any(c.isspace() for c in token):
        raise ValueError('GitHub token không hợp lệ.')
    secure_store.write(STORE, {'token': token})


def check_release() -> dict:
    result = {'current': __version__, 'available': False, 'version': '',
              'url': '', 'error': ''}
    try:
        token = secure_store.read(STORE).get('token', '')
        if not isinstance(token, str) or not token:
            result['error'] = 'Chưa cấu hình quyền đọc GitHub. Mở Cập nhật để thêm token.'
            return result
        request = Request(f'https://api.github.com/repos/{REPOSITORY}/releases/latest', headers={
            'Accept': 'application/vnd.github+json', 'Authorization': f'Bearer {token}',
            'User-Agent': 'StoryToon-Portable', 'X-GitHub-Api-Version': '2022-11-28',
        })
        with urlopen(request, timeout=15) as response:
            release = json.load(response)
        tag = release.get('tag_name', '')
        if release.get('draft') or release.get('prerelease'):
            return result
        result.update(version=tag, available=version_tuple(tag) > version_tuple(__version__))
        # Construct the trusted URL locally; never open a URL supplied by metadata.
        if result['available']:
            result['url'] = f'https://github.com/{REPOSITORY}/releases/tag/{tag}'
    except HTTPError as exc:
        result['error'] = ({401: 'GitHub token hết hạn hoặc không hợp lệ.',
                            403: 'GitHub từ chối truy cập hoặc giới hạn lượt kiểm tra.',
                            404: 'Chưa có bản phát hành hoặc token chưa có quyền đọc repository.'}
                           .get(exc.code, 'Không thể kiểm tra bản phát hành GitHub.'))
    except (OSError, URLError, ValueError, TypeError, AttributeError):
        result['error'] = 'Không kiểm tra được cập nhật. Kiểm tra Internet và quyền đọc GitHub.'
    return result
