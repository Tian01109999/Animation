"""Trộn toàn bộ âm thanh của phim thành 1 file wav 48 kHz stereo.

    build_soundtrack(storyboard, project_dir, out_wav) -> Path

- Giọng: mỗi Line đặt tại (offset shot + Line.start). Cần chạy timing.fill_timing trước.
- Nhạc nền: theo Shot.music_mood (None = giữ nhạc trước; "none"/"silence" = tắt nhạc), lặp lại cho đủ,
  crossfade khi đổi mood, ducking −12 dB khi có lời.
- SFX: phát ở đầu shot.
- File nhạc/sfx tìm trong assets/music/<mood>.* và assets/sfx/<tên>.*; thiếu thì tự tạo bản thủ tục.

Tham số tuỳ chọn trong config.yaml (không bắt buộc):
    audio: {music_rms_db: -30, duck_db: -12, sfx_peak_db: -6, crossfade_s: 1.5}
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from ..config import get
from ..paths import MUSIC, SFX
from ..schema import Storyboard
from . import audio_io, procedural
from .timing import film_duration, shot_offsets

log = logging.getLogger(__name__)
SR = audio_io.SR

MOOD_ALIASES = {
    "scary": "horror", "fear": "horror", "dark": "horror", "creepy": "horror",
    "suspense": "tense", "danger": "tense", "action": "tense",
    "peaceful": "calm", "happy": "calm", "neutral": "calm", "warm": "calm",
    "melancholy": "sad", "grief": "sad",
    "mysterious": "mystery", "eerie": "mystery",
}
SILENT_MOODS = {"none", "silence", "off", "stop"}
SFX_ALIASES = {
    "crowd_night": "crowd", "crowd_day": "crowd", "market": "crowd", "murmur": "crowd",
    "knock": "door", "creak": "door", "door_creak": "door", "door_open": "door",
    "steps": "footsteps", "footstep": "footsteps", "heart": "heartbeat", "heart_beat": "heartbeat",
    "glass": "glass_break", "bell": "gong", "cleaver": "chop", "knife_chop": "chop",
    "frying": "sizzle", "cooking": "sizzle", "clank": "metal_clank", "metal": "metal_clank",
    "whispers": "whisper",
}


def _db(x: float) -> float:
    return float(10 ** (x / 20))


# ---------------------------------------------------------------- tìm / tạo tài sản
def resolve_music(mood: str) -> Path | None:
    mood = mood.strip().lower()
    p = procedural.find_audio(MUSIC, mood)
    if p:
        return p
    canon = MOOD_ALIASES.get(mood, mood)
    if canon not in procedural.MUSIC_MOODS:
        log.warning("Không có nhạc cho mood '%s' — dùng 'mystery'.", mood)
        canon = "mystery"
    return procedural.find_audio(MUSIC, canon) or procedural.make_music(canon, MUSIC)


def resolve_sfx(name: str) -> Path | None:
    key = name.strip().lower().replace(" ", "_")
    p = procedural.find_audio(SFX, key)
    if p:
        return p
    canon = SFX_ALIASES.get(key, key)
    p = procedural.find_audio(SFX, canon) or procedural.make_sfx(canon, SFX)
    if p is None:
        log.warning("Không tìm thấy hiệu ứng '%s' trong assets/sfx — bỏ qua.", name)
    return p


# ---------------------------------------------------------------- xử lý tín hiệu
def loop_to(x: np.ndarray, n: int, xfade: int = SR // 2) -> np.ndarray:
    """Lặp x (shape [m, ch]) cho đủ n mẫu, nối các vòng bằng crossfade xfade mẫu."""
    if len(x) >= n:
        return x[:n]
    xfade = min(xfade, len(x) // 4)
    out = np.zeros((n, x.shape[1]), dtype=np.float32)
    fade_in = np.linspace(0, 1, xfade, dtype=np.float32)[:, None] if xfade else None
    pos = 0
    first = True
    while pos < n:
        seg = x.copy()
        if not first and xfade:
            seg[:xfade] *= fade_in
            out[pos: pos + xfade] *= (1 - fade_in[: max(0, min(xfade, n - pos))])
        end = min(n, pos + len(seg))
        out[pos:end] += seg[: end - pos]
        pos = end - xfade if end < n else end
        first = False
    return out


def _rms_normalize(x: np.ndarray, target_db: float) -> np.ndarray:
    rms = float(np.sqrt(np.mean(x.astype(np.float64) ** 2)) + 1e-9)
    return (x * (_db(target_db) / rms)).astype(np.float32)


def _peak_normalize(x: np.ndarray, target_db: float) -> np.ndarray:
    return (x * (_db(target_db) / (float(np.abs(x).max()) + 1e-9))).astype(np.float32)


def duck_gain(voice: np.ndarray, duck_db: float, *, attack: float = 0.08, release: float = 0.45,
              threshold: float = 0.015) -> np.ndarray:
    """Hệ số khuếch đại cho nhạc (mỗi mẫu): 1 khi im lặng, duck_db khi có giọng."""
    hop = SR // 100  # khung 10 ms
    n = len(voice)
    frames = int(np.ceil(n / hop))
    padded = np.zeros(frames * hop, dtype=np.float32)
    padded[:n] = np.abs(voice)
    active = (padded.reshape(frames, hop).max(axis=1) > threshold).astype(np.float32)
    env = np.empty(frames, dtype=np.float32)
    a_up, a_dn = 1 - np.exp(-0.01 / attack), 1 - np.exp(-0.01 / release)
    acc = 0.0
    # nhìn trước 1 khoảng attack để nhạc nhỏ xuống đúng lúc giọng bắt đầu
    look = int(attack / 0.01)
    active = np.concatenate([active[look:], np.zeros(look, dtype=np.float32)]) if look else active
    for i, v in enumerate(active):
        acc += (a_up if v > acc else a_dn) * (v - acc)
        env[i] = acc
    gain_frames = _db(duck_db) ** env  # nội suy theo dB
    xp = np.arange(frames) * hop + hop / 2
    out = np.empty(n, dtype=np.float32)
    # nội suy theo từng khúc: tránh mảng int64/float64 cỡ n (phim 20 phút ~ 0.5 GB mỗi mảng)
    for a in range(0, n, _CHUNK):
        b = min(n, a + _CHUNK)
        out[a:b] = np.interp(np.arange(a, b), xp, gain_frames)
    return out


_CHUNK = 1 << 20


def soft_limit(x: np.ndarray, ceiling: float = 0.97, *, inplace: bool = False) -> np.ndarray:
    """Giữ nguyên phần nhỏ hơn ngưỡng 0.8*ceiling, nén mềm phần vượt (tanh). Xử lý theo khúc để tiết kiệm RAM."""
    knee = 0.8 * ceiling
    y = x if inplace else x.copy()
    flat = y.reshape(-1)
    for a in range(0, len(flat), _CHUNK):
        seg = flat[a: a + _CHUNK]
        over = np.abs(seg) > knee
        if over.any():
            v = seg[over]
            seg[over] = np.sign(v) * (knee + (ceiling - knee) * np.tanh((np.abs(v) - knee) / (ceiling - knee)))
    return y


# ---------------------------------------------------------------- dàn dựng
def music_segments(sb: Storyboard) -> list[tuple[str, float, float]]:
    """[(mood, t_bắt_đầu, t_kết_thúc)] liên tục theo mood hiện hành."""
    segs: list[tuple[str, float, float]] = []
    cur: str | None = None
    start = 0.0
    offs = shot_offsets(sb)
    for off, shot in zip(offs, sb.shots):
        mood = (shot.music_mood or "").strip().lower() or None
        if mood is None or mood == cur:
            continue
        if cur is not None and cur not in SILENT_MOODS:
            segs.append((cur, start, off))
        cur, start = mood, off
    if cur is not None and cur not in SILENT_MOODS:
        segs.append((cur, start, film_duration(sb)))
    return [s for s in segs if s[2] - s[1] > 0.05]


def build_soundtrack(storyboard: Storyboard, project_dir: Path, out_wav: Path, *,
                     music: bool = True, sfx: bool = True) -> Path:
    project_dir = Path(project_dir)
    out_wav = Path(out_wav)
    total = film_duration(storyboard)
    n = int(np.ceil(total * SR)) + 1
    music_rms = float(get("audio.music_rms_db", -30))
    duck_db = float(get("audio.duck_db", -12))
    sfx_peak = float(get("audio.sfx_peak_db", -6))
    xf_s = float(get("audio.crossfade_s", 1.5))

    offs = shot_offsets(storyboard)

    # giọng (mono)
    voice = np.zeros(n, dtype=np.float32)
    for off, shot in zip(offs, storyboard.shots):
        for ln in shot.lines:
            if not ln.audio or ln.start is None:
                continue
            p = project_dir / ln.audio
            if not p.exists():
                log.warning("Thiếu file giọng %s — bỏ qua.", p)
                continue
            data, sr = audio_io.read_wav(p)
            mono = data.mean(axis=1) if sr == SR else audio_io.decode(p, channels=1)[:, 0]
            a = int(round((off + ln.start) * SR))
            b = min(n, a + len(mono))
            if b > a:
                voice[a:b] += mono[: b - a]

    mix = np.repeat(voice[:, None], 2, axis=1)

    # nhạc nền
    if music:
        bed = np.zeros((n, 2), dtype=np.float32)
        xf = int(xf_s * SR)
        cache: dict[Path, np.ndarray] = {}
        for i, (mood, t0, t1) in enumerate(music_segments(storyboard)):
            path = resolve_music(mood)
            if path is None:
                continue
            if path not in cache:
                cache[path] = _rms_normalize(audio_io.decode(path, channels=2), music_rms)
            a = int(t0 * SR)
            is_last = t1 >= total - 1e-3
            b = n if is_last else min(n, int(t1 * SR) + xf)
            seg = loop_to(cache[path], b - a)
            fin = min(len(seg), xf if i > 0 else int(2.0 * SR))
            seg[:fin] *= np.linspace(0, 1, fin, dtype=np.float32)[:, None]
            fout = min(len(seg), int(2.5 * SR) if is_last else xf)
            seg[len(seg) - fout:] *= np.linspace(1, 0, fout, dtype=np.float32)[:, None]
            bed[a:b] += seg
        cache.clear()
        bed *= duck_gain(voice, duck_db)[:, None]
        mix += bed
        del bed

    # hiệu ứng
    if sfx:
        fx_cache: dict[str, np.ndarray | None] = {}
        for off, shot in zip(offs, storyboard.shots):
            for name in shot.sfx:
                if name not in fx_cache:   # mỗi hiệu ứng chỉ tìm/giải mã 1 lần (phim dài lặp lại nhiều)
                    path = resolve_sfx(name)
                    fx_cache[name] = (None if path is None else
                                      _peak_normalize(audio_io.decode(path, channels=2), sfx_peak))
                fx = fx_cache[name]
                if fx is None:
                    continue
                a = int(off * SR)
                b = min(n, a + len(fx))
                mix[a:b] += fx[: b - a]

    return audio_io.write_wav(out_wav, soft_limit(mix, inplace=True), SR)
