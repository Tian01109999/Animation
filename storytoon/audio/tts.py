"""Text-to-speech: văn bản tiếng Việt -> wav 48 kHz mono (+ bản 16 kHz cho Rhubarb).

API công khai:
    synth_line(text, voice, out_path, *, rate=None, pitch=None) -> float      (đồng bộ)
    synth_line_async(...)                                                       (async, dùng cho song song)
    cache_key(text, voice, rate, pitch) -> str
    get_engine(name) -> TTSEngine

Engine:
    EdgeTTSEngine  — edge-tts (Microsoft, cần mạng, miễn phí). Mặc định.
    F5TTSEngine    — STUB. F5-TTS (voice clone offline, chạy GPU) sẽ thêm sau: cần model
                     tiếng Việt (vd "F5-TTS-Vietnamese"), một file giọng mẫu + transcript cho mỗi
                     giọng; "voice" khi đó là id giọng trong assets/voices/<id>/(ref.wav, ref.txt).

Cache: wav đích có file kèm "<tên>.json" chứa khoá hash(text+voice+rate+pitch+engine). Nếu khớp
và wav còn tồn tại thì không gọi mạng lại.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
import unicodedata
from abc import ABC, abstractmethod
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, TypeVar

from . import audio_io

log = logging.getLogger(__name__)
T = TypeVar("T")

RETRIES = 3
TRIM_VERSION = 1      # tăng khi đổi cách cắt lặng → file cũ được cắt lại (không gọi TTS lại)
TRIM_KEEP = 0.05      # giây lặng giữ lại ở đầu/cuối mỗi câu
TRIM_WINDOW = 0.01    # cửa sổ 10 ms để dò tiếng


def trim_silence(path: Path, keep: float = TRIM_KEEP) -> float:
    """Cắt khoảng lặng thừa ở đầu/cuối wav (giữ `keep` giây mỗi đầu), ghi đè file. Trả về thời lượng mới."""
    import numpy as np

    data, sr = audio_io.read_wav(path)
    mono = np.abs(data).max(axis=1) if data.ndim > 1 else np.abs(data)
    win = max(1, int(sr * TRIM_WINDOW))
    frames = len(mono) // win
    if frames == 0:
        return audio_io.wav_duration(path)
    level = mono[: frames * win].reshape(frames, win).max(axis=1)
    peak = float(level.max())
    if peak <= 0:
        return audio_io.wav_duration(path)
    loud = np.flatnonzero(level > max(peak * 0.03, 0.004))   # ~-30 dB so với đỉnh
    pad = int(sr * keep)
    start = max(0, int(loud[0]) * win - pad)
    end = min(len(data), (int(loud[-1]) + 1) * win + pad)
    if start > 0 or end < len(data):
        audio_io.write_wav(path, data[start:end], sr)
    return audio_io.wav_duration(path)


class TTSError(RuntimeError):
    pass


def normalize_text(text: str) -> str:
    """NFC + gộp khoảng trắng. edge-tts đọc tốt dấu tiếng Việt dạng dựng sẵn (NFC)."""
    return " ".join(unicodedata.normalize("NFC", text).split())


def cache_key(text: str, voice: str, rate: str = "+0%", pitch: str = "+0Hz", engine: str = "edge") -> str:
    blob = "\x1f".join([engine, voice, rate, pitch, normalize_text(text)])
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


class TTSEngine(ABC):
    """Giao diện engine TTS. synth ghi ra file âm thanh bất kỳ định dạng (ffmpeg sẽ chuyển sang wav)."""

    name: str = "base"
    output_suffix: str = ".mp3"

    @abstractmethod
    async def synth(self, text: str, voice: str, out_file: Path, *, rate: str, pitch: str) -> None: ...


def _shift(value: str, unit: str, delta: int) -> str:
    """'+5%' + 1 -> '+6%' (giữ đơn vị)."""
    num = value.strip().rstrip(unit) or "0"
    try:
        return f"{int(num) + delta:+d}{unit}"
    except ValueError:
        return value


class EdgeTTSEngine(TTSEngine):
    """edge-tts. Dịch vụ thỉnh thoảng trả về 'No audio was received' cho một số câu tiếng Việt, và
    lỗi này "dính" theo đúng yêu cầu (cùng text + tham số -> lỗi lặp lại). Đã kiểm chứng (11/2026):
    chỉ cần đổi rất nhẹ yêu cầu (volume/pitch/rate ±1, thêm dấu phẩy cuối) là thường qua — nên thử
    lần lượt các biến thể gần như không nghe ra khác biệt."""

    name = "edge"
    output_suffix = ".mp3"
    max_variants = 8

    @staticmethod
    def _variants(text: str, rate: str, pitch: str) -> list[tuple[str, str, str, str]]:
        """(text, rate, pitch, volume) — biến thể đầu tiên là yêu cầu gốc."""
        return [
            (text, rate, pitch, "+0%"),
            (text, rate, pitch, "+1%"),
            (text, rate, _shift(pitch, "Hz", 1), "+0%"),
            (text + " ,", rate, pitch, "+0%"),
            (text, _shift(rate, "%", -1), pitch, "+0%"),
            (text, rate, _shift(pitch, "Hz", -1), "-1%"),
            (text, _shift(rate, "%", 1), pitch, "+2%"),
            (text + " ,", rate, _shift(pitch, "Hz", 1), "-2%"),
        ]

    async def synth(self, text: str, voice: str, out_file: Path, *, rate: str, pitch: str) -> None:
        import edge_tts
        from edge_tts.exceptions import NoAudioReceived

        last: Exception | None = None
        for i, (t, r, p, v) in enumerate(self._variants(text, rate, pitch)[: self.max_variants]):
            try:
                await edge_tts.Communicate(t, voice, rate=r, pitch=p, volume=v).save(str(out_file))
            except NoAudioReceived as e:
                last = e
                log.debug("edge-tts không trả âm thanh (biến thể %d) — thử biến thể khác", i)
                await asyncio.sleep(0.3)
                continue
            if out_file.exists() and out_file.stat().st_size >= 200:
                if i:
                    log.info("edge-tts thành công ở biến thể %d cho: %s", i, text[:40])
                return
        raise TTSError(f"edge-tts không trả về âm thanh sau {self.max_variants} biến thể: {last}")


class F5TTSEngine(TTSEngine):
    """Chỗ để gắn F5-TTS sau này (offline, GPU). Chưa cài đặt."""

    name = "f5"
    output_suffix = ".wav"

    async def synth(self, text: str, voice: str, out_file: Path, *, rate: str, pitch: str) -> None:
        raise NotImplementedError(
            "F5-TTS chưa được tích hợp. Cần: pip install f5-tts, model tiếng Việt, "
            "assets/voices/<voice>/ref.wav + ref.txt. Tạm thời dùng tts.engine: edge trong config.yaml."
        )


_ENGINES: dict[str, type[TTSEngine]] = {"edge": EdgeTTSEngine, "f5": F5TTSEngine}


def get_engine(name: str | None = None, *, language: str | None = None) -> TTSEngine:
    from ..config import get

    key = (name or get("tts.engine", "edge") or "edge").lower()
    if key == 'capcut':
        from .capcut import CapCutTTSEngine
        return CapCutTTSEngine(language or get('tts.language', 'vi'))
    if key not in _ENGINES:
        raise ValueError(f"Engine TTS không hỗ trợ: {key!r} (có: {', '.join(_ENGINES)})")
    return _ENGINES[key]()


def _meta_path(wav: Path) -> Path:
    return wav.with_suffix(".json")


def wav16_path(wav: Path) -> Path:
    """Đường dẫn bản 16 kHz (Rhubarb xử lý nội bộ ở 16 kHz, file nhỏ hơn -> nhanh hơn)."""
    return wav.with_name(wav.stem + ".16k.wav")


def _cached_duration(out_path: Path, key: str) -> float | None:
    meta = _meta_path(out_path)
    if not (out_path.exists() and meta.exists()):
        return None
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if data.get("key") != key:
        return None
    if data.get("trim") != TRIM_VERSION:
        # file tạo trước khi có bước cắt lặng: cắt tại chỗ, tạo lại bản 16k, không gọi TTS lại
        try:
            duration = trim_silence(out_path)
            audio_io.to_wav(out_path, wav16_path(out_path), sr=16000, channels=1)
        except Exception as e:  # noqa: BLE001 - file hỏng → tổng hợp lại
            log.warning("Không cắt được khoảng lặng %s (%s) — tạo lại giọng.", out_path.name, e)
            return None
        data.update(trim=TRIM_VERSION, duration=duration)
        meta.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        return duration
    return float(data.get("duration") or audio_io.wav_duration(out_path))


async def synth_line_async(text: str, voice: str, out_path: Path, *, rate: str | None = None,
                           pitch: str | None = None, engine: TTSEngine | None = None) -> float:
    """Tổng hợp 1 câu -> out_path (wav 48k mono) + bản .16k.wav. Trả về thời lượng (giây)."""
    from ..config import get

    out_path = Path(out_path)
    text = normalize_text(text)
    if not text:
        raise TTSError("Câu thoại rỗng")
    rate = rate or get("tts.rate", "+0%") or "+0%"
    pitch = pitch or "+0Hz"
    engine = engine or get_engine()
    key = cache_key(text, voice, rate, pitch, engine.name)

    cached = await asyncio.to_thread(_cached_duration, out_path, key)
    if cached is not None:
        return cached

    out_path.parent.mkdir(parents=True, exist_ok=True)
    raw = out_path.with_name(out_path.stem + ".raw" + engine.output_suffix)
    last_err: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        try:
            await engine.synth(text, voice, raw, rate=rate, pitch=pitch)
            break
        except NotImplementedError:
            raise
        except Exception as e:  # lỗi mạng / websocket / NoAudioReceived
            last_err = e
            log.warning("TTS lỗi (lần %d/%d) voice=%s: %s", attempt, RETRIES, voice, e)
            if attempt < RETRIES:
                await asyncio.sleep(1.5 * attempt)
    else:
        raise TTSError(f"Không tổng hợp được giọng sau {RETRIES} lần ({voice}): {last_err}") from last_err

    await asyncio.to_thread(audio_io.to_wav, raw, out_path, sr=audio_io.SR, channels=1)
    await asyncio.to_thread(trim_silence, out_path)          # cùng một mức lặng cho mọi engine
    await asyncio.to_thread(audio_io.to_wav, out_path, wav16_path(out_path), sr=16000, channels=1)
    raw.unlink(missing_ok=True)
    duration = audio_io.wav_duration(out_path)
    if duration <= 0:
        raise TTSError(f"Âm thanh rỗng cho câu: {text[:40]}")
    _meta_path(out_path).write_text(
        json.dumps({"key": key, "engine": engine.name, "voice": voice, "rate": rate, "pitch": pitch,
                    "text": text, "duration": duration, "trim": TRIM_VERSION}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    return duration


def run_coro(coro: Coroutine[Any, Any, T]) -> T:
    """Chạy coroutine từ code đồng bộ, kể cả khi đang ở trong event loop (vd Gradio)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    box: dict[str, Any] = {}

    def worker() -> None:
        try:
            box["v"] = asyncio.run(coro)
        except BaseException as e:  # noqa: BLE001 — chuyển lỗi sang thread gọi
            box["e"] = e

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join()
    if "e" in box:
        raise box["e"]
    return box["v"]


def synth_line(text: str, voice: str, out_path: Path, *, rate: str | None = None,
               pitch: str | None = None) -> float:
    """Bản đồng bộ của synth_line_async (đúng chữ ký trong SPEC)."""
    return run_coro(synth_line_async(text, voice, Path(out_path), rate=rate, pitch=pitch))
