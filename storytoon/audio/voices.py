"""Local voice catalogs shared by settings and the audio pipeline."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

LANGUAGES = [('Tiếng Việt', 'vi'), ('Tiếng Thái', 'th'), ('Tiếng Hàn', 'ko')]
ENGINES = [('CapCut TTS', 'capcut'), ('Microsoft Edge TTS', 'edge')]
SAMPLES = {
    'vi': 'Xin chào, đây là giọng đọc thử cho câu chuyện của bạn.',
    'th': 'สวัสดี นี่คือเสียงตัวอย่างสำหรับเรื่องราวของคุณ',
    'ko': '안녕하세요. 여러분의 이야기를 위한 음성 미리 듣기입니다.',
}
VENDOR = Path(__file__).resolve().parents[1] / 'vendor' / 'capcut_tts'
_EDGE = {
    'vi': [('Nam Minh', 'vi-VN-NamMinhNeural', 'nam'), ('Hoài My', 'vi-VN-HoaiMyNeural', 'nu')],
    'th': [('Niwat', 'th-TH-NiwatNeural', 'nam'), ('Premwadee', 'th-TH-PremwadeeNeural', 'nu')],
    'ko': [('InJoon', 'ko-KR-InJoonNeural', 'nam'), ('SunHi', 'ko-KR-SunHiNeural', 'nu')],
}


@lru_cache(maxsize=8)
def catalog(engine: str, language: str) -> list[dict]:
    if language not in SAMPLES:
        raise ValueError('Ngôn ngữ giọng đọc không được hỗ trợ.')
    if engine == 'capcut':
        return json.loads((VENDOR / 'voices' / f'{language}.json').read_text(encoding='utf-8'))
    if engine == 'edge':
        return [{'ten': name, 'id': voice, 'gioi': gender} for name, voice, gender in _EDGE[language]]
    raise ValueError('Bộ tạo giọng không được hỗ trợ.')


def choices(engine: str, language: str) -> list[tuple[str, str]]:
    return [(' · '.join(filter(None, [v.get('tenCapcut') or v['ten'],
             {'nam': 'Nam', 'nu': 'Nữ'}.get(v.get('gioi')), v.get('vungMien')])), v['id'])
            for v in catalog(engine, language)]


def valid(voice: str | None, engine: str, language: str) -> bool:
    return any(v['id'] == voice for v in catalog(engine, language))


def default_voice(engine: str, language: str, gender: str = 'nam') -> str:
    entries = catalog(engine, language)
    return next((v['id'] for v in entries if v.get('gioi') == gender), entries[0]['id'])


def selected(engine: str, language: str, voice: str | None, gender: str = 'nam') -> str:
    return voice if valid(voice, engine, language) else default_voice(engine, language, gender)


def validate_settings(engine: str, language: str, narrator: str, male: str, female: str, rate: str) -> str:
    for voice in (narrator, male, female):
        if not valid(voice, engine, language):
            raise ValueError('Hãy chọn lại giọng phù hợp với bộ đọc và ngôn ngữ.')
    if not re.fullmatch(r'[+-]?\d+%', rate.strip()) or not -50 <= int(rate.strip()[:-1]) <= 100:
        raise ValueError('Tốc độ đọc phải từ -50% đến +100%, ví dụ +20%.')
    return f'{int(rate.strip()[:-1]):+d}%'
