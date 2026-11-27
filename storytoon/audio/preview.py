"""Fixed voice samples persisted beside the portable app, shared across projects."""
from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import wave
from pathlib import Path

from .. import paths
from . import audio_io, tts, voices

_lock = threading.Lock()


def _ready(path: Path) -> bool:
    try:
        with wave.open(str(path), 'rb') as wav:
            frames = wav.getnframes()
            size = frames * wav.getnchannels() * wav.getsampwidth()
            return frames > 0 and path.stat().st_size >= size + 44
    except (OSError, EOFError, wave.Error):
        return False


def get_preview(engine: str, language: str, voice: str, rate: str = '+0%') -> Path:
    """Generate a voice once; speed variants are made locally from the saved sample."""
    rate = voices.validate_settings(engine, language, voice, voice, voice, rate)
    text = voices.SAMPLES[language]  # Always server-owned, never accept custom preview text.
    provider = tts.get_engine(engine, language=language)
    identity = json.dumps([provider.name, language, voice, text, 'preview-v1'], ensure_ascii=False)
    key = hashlib.sha256(identity.encode('utf-8')).hexdigest()[:32]
    folder = paths.VOICE_PREVIEWS / key
    source = folder / 'sample.wav'
    speed = int(rate[:-1])
    output = source if speed == 0 else folder / f'rate_{speed:+d}.wav'
    with _lock:
        if _ready(output):
            return output
        folder.mkdir(parents=True, exist_ok=True)
        # Publish only complete WAVs; failed/interrupted synthesis never becomes a cache hit.
        with tempfile.TemporaryDirectory(prefix='creating-', dir=folder) as staging:
            if not _ready(source):
                staged = Path(staging) / 'sample.wav'
                tts.run_coro(tts.synth_line_async(text, voice, staged, rate='+0%', pitch='+0Hz', engine=provider))
                if not _ready(staged):
                    raise tts.TTSError('Mẫu nghe thử chưa có âm thanh hợp lệ.')
                staged.replace(source)
                (folder / 'voice.json').write_text(json.dumps({
                    'engine': engine, 'language': language, 'voice': voice, 'text': text,
                }, ensure_ascii=False, indent=2), encoding='utf-8')
            if speed != 0:
                staged = Path(staging) / 'speed.wav'
                audio_io.run_ffmpeg(['-i', str(source), '-af', f'atempo={1 + speed / 100:.6f}',
                                     '-c:a', 'pcm_s16le', str(staged)])
                if not _ready(staged):
                    raise tts.TTSError('Không điều chỉnh được tốc độ mẫu nghe thử.')
                staged.replace(output)
    return output
