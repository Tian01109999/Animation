"""Adapter for the supplied standalone CapCut Node module."""
from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

from .. import paths
from . import audio_io, voices
from .tts import TTSEngine, TTSError


class CapCutTTSEngine(TTSEngine):
    output_suffix = '.wav'

    def __init__(self, language: str = 'vi'):
        voices.catalog('capcut', language)
        self.language = language
        self.name = f'capcut:{language}:v1'

    async def synth(self, text: str, voice: str, out_file: Path, *, rate: str, pitch: str) -> None:
        if not voices.valid(voice, 'capcut', self.language):
            raise TTSError('Giọng CapCut không thuộc ngôn ngữ đã chọn.')
        await asyncio.to_thread(self._synth, text, voice, out_file, rate, pitch)

    def _synth(self, text: str, voice: str, out_file: Path, rate: str, pitch: str) -> None:
        node = paths.RUNTIME / 'node' / 'node.exe'
        if not node.is_file():
            raise TTSError('Thiếu runtime/node/node.exe trong thư mục ứng dụng.')
        # Match the existing per-character rate/pitch tuning using the bundled FFmpeg.
        tempo = 1 + int(rate.rstrip('%')) / 100
        pitch_factor = max(0.5, min(2.0, 1 + int(pitch.rstrip('Hz')) / 200))
        if not 0.25 <= tempo <= 3:
            raise TTSError('Tốc độ đọc ngoài phạm vi hỗ trợ.')
        source = out_file.with_suffix('.source.mp3')
        try:
            payload = {'text': text, 'voice': voice, 'lang': self.language, 'outPath': str(source.resolve())}
            result = subprocess.run(
                [str(node), str(voices.VENDOR / 'bridge.js')], input=json.dumps(payload, ensure_ascii=False),
                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=300,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
            if result.returncode or not source.is_file() or source.stat().st_size < 200:
                raise TTSError('CapCut không tạo được âm thanh: ' + (result.stderr.strip()[-600:] or 'Tệp âm thanh rỗng.'))
            filters = ['aresample=48000', f'asetrate={48000 * pitch_factor:.0f}', 'aresample=48000']
            speed = tempo / pitch_factor
            while speed < 0.5:
                filters.append('atempo=0.5'); speed /= 0.5
            while speed > 2:
                filters.append('atempo=2'); speed /= 2
            filters.append(f'atempo={speed:.6f}')
            audio_io.run_ffmpeg(['-i', str(source), '-af', ','.join(filters), '-ac', '1', '-ar', '48000',
                                 '-c:a', 'pcm_s16le', str(out_file)])
        except subprocess.TimeoutExpired as exc:
            raise TTSError('CapCut quá thời gian chờ (5 phút). Hãy thử lại sau.') from exc
        finally:
            source.unlink(missing_ok=True)
