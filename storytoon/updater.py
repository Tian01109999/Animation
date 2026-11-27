"""Check public assets releases without GitHub credentials."""
from __future__ import annotations

import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import __version__, paths

REPOSITORY = 'Tian01109999/Animation'
ASSETS_VERSION_FILE = '.storytoon-assets-version.json'


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


def check_release() -> dict:
    result = {'current': assets_version(), 'app_version': __version__, 'kind': 'assets',
              'available': False, 'version': '', 'url': '', 'error': ''}
    try:
        request = Request(f'https://api.github.com/repos/{REPOSITORY}/releases?per_page=100', headers={
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'StoryToon-Portable', 'X-GitHub-Api-Version': '2022-11-28',
        })
        with urlopen(request, timeout=15) as response:
            releases = json.load(response)
        candidates = []
        if not isinstance(releases, list):
            raise ValueError('Invalid release list')
        for release in releases:
            if not isinstance(release, dict) or release.get('draft') or release.get('prerelease'):
                continue
            tag = release.get('tag_name', '')
            if not isinstance(tag, str) or not tag.startswith('assets-v'):
                continue
            version = tag.removeprefix('assets-v')
            try:
                numeric = version_tuple(version)
            except ValueError:
                continue
            filename = f'StoryToon-Assets-{version}.zip'
            names = {asset.get('name') for asset in release.get('assets', [])
                     if isinstance(asset, dict) and asset.get('state') == 'uploaded'}
            if filename in names and filename + '.sha256' in names:
                candidates.append((numeric, version, tag))
        if not candidates:
            result['error'] = 'Chưa có gói assets ổn định được phát hành.'
            return result
        numeric, version, tag = max(candidates)
        result.update(version=version, available=numeric > version_tuple(result['current']))
        # Construct the trusted URL locally; never open a URL supplied by metadata.
        if result['available']:
            result['url'] = f'https://github.com/{REPOSITORY}/releases/tag/{tag}'
    except HTTPError as exc:
        result['error'] = ({403: 'GitHub đang giới hạn lượt kiểm tra. Vui lòng thử lại sau.',
                            404: 'Chưa tìm thấy repository công khai hoặc bản phát hành.'}
                           .get(exc.code, 'Không thể kiểm tra bản phát hành GitHub.'))
    except (OSError, URLError, ValueError, TypeError, AttributeError):
        result['error'] = 'Không kiểm tra được cập nhật. Kiểm tra kết nối Internet và thử lại sau.'
    return result
