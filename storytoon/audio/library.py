"""Thư viện nhạc nền + hiệu ứng: đọc assets/music/catalog.json và assets/sfx/catalog.json.

    music_moods() -> {mood: mô tả dùng khi nào}
    music_track(mood, nth, seed) -> Path | None     # luân phiên các bài của mood
    sfx(name) -> SoundInfo | None                    # tên chuẩn hoặc tên đồng nghĩa
    sfx_guide() -> {tên: mô tả}                      # cho prompt AI
Không có catalog (bản cũ) → trả rỗng, mixer dùng cách cũ (file theo tên / âm thủ tục).
"""
from __future__ import annotations

import json
import logging
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from ..paths import MUSIC, SFX

log = logging.getLogger(__name__)
_cache: dict[Path, tuple[float, dict]] = {}


def _load(path: Path) -> dict:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}
    hit = _cache.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as e:
        log.warning('Không đọc được %s: %s', path, e)
        data = {}
    _cache[path] = (mtime, data)
    return data


def _key(name: str) -> str:
    return (name or '').strip().lower().replace(' ', '_').replace('-', '_')


# ---------------------------------------------------------------- nhạc
def music_moods() -> dict[str, str]:
    return {m: v.get('use', '') for m, v in (_load(MUSIC / 'catalog.json').get('moods') or {}).items()}


def music_tracks(mood: str) -> list[Path]:
    entry = (_load(MUSIC / 'catalog.json').get('moods') or {}).get(_key(mood)) or {}
    return [MUSIC / t['file'] for t in entry.get('tracks', []) if (MUSIC / t['file']).exists()]


def music_track(mood: str, nth: int = 0, seed: str = '') -> Path | None:
    """Bài thứ `nth` của mood (lần xuất hiện thứ nth trong phim), bắt đầu từ vị trí theo `seed`."""
    tracks = music_tracks(mood)
    if not tracks:
        return None
    start = zlib.crc32(f'{seed}|{_key(mood)}'.encode('utf-8')) % len(tracks)
    return tracks[(start + nth) % len(tracks)]


# ---------------------------------------------------------------- hiệu ứng
@dataclass(frozen=True)
class SoundInfo:
    key: str
    path: Path
    kind: str = 'oneshot'            # oneshot | ambience
    use: str = ''
    aliases: tuple[str, ...] = field(default_factory=tuple)


def _sounds() -> dict[str, dict]:
    return _load(SFX / 'catalog.json').get('sounds') or {}


def sfx(name: str) -> SoundInfo | None:
    key = _key(name)
    sounds = _sounds()
    entry = sounds.get(key)
    if entry is None:
        for k, v in sounds.items():
            if key in (v.get('aliases') or []):
                key, entry = k, v
                break
    if entry is None:
        return None
    path = SFX / entry.get('file', f'{key}.ogg')
    if not path.exists():
        return None
    return SoundInfo(key, path, entry.get('kind', 'oneshot'), entry.get('use', ''),
                     tuple(entry.get('aliases') or ()))


def sfx_guide() -> dict[str, str]:
    """{tên: mô tả (+ 'âm nền' nếu lặp suốt cảnh)} — dùng trong prompt cho AI."""
    out = {}
    for k, v in sorted(_sounds().items()):
        use = v.get('use', '')
        out[k] = use + (' [âm nền, lặp suốt các shot liên tiếp]' if v.get('kind') == 'ambience' else '')
    return out


def known_sfx(name: str) -> str | None:
    """Tên chuẩn nếu có trong thư viện (kể cả tên đồng nghĩa), ngược lại None."""
    info = sfx(name)
    return info.key if info else None
