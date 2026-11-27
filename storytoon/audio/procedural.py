"""Nhạc nền & hiệu ứng âm thanh tạo bằng numpy — chỉ để bản demo có tiếng khi chưa có file thật.

Nhạc: vòng lặp liền mạch (mọi tần số là bội của 1/L, nhiễu lọc trong miền tần số -> vòng tròn),
nên mixer lặp lại không bị "tách". File thật trong assets/music/ luôn được ưu tiên.
"""
from __future__ import annotations

import logging
import tempfile
import zlib
from collections.abc import Callable
from pathlib import Path

import numpy as np

from ..paths import MUSIC, SFX
from . import audio_io

log = logging.getLogger(__name__)
SR = audio_io.SR
LOOP_S = 32.0
AUDIO_EXTS = (".wav", ".ogg", ".mp3", ".flac", ".m4a", ".opus")


# ---------------------------------------------------------------- khối dựng
def _q(f: float, length_s: float) -> float:
    """Làm tròn tần số về bội của 1/length để vòng lặp khớp pha."""
    return max(1.0, round(f * length_s)) / length_s


def _t(seconds: float) -> np.ndarray:
    return np.arange(int(seconds * SR), dtype=np.float64) / SR


def _filtered_noise(n: int, lo: float, hi: float, rng: np.random.Generator, tilt: float = 0.0) -> np.ndarray:
    """Nhiễu dải [lo, hi] Hz, lọc FFT (vòng tròn -> lặp liền mạch). tilt<0 làm tối âm sắc."""
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / SR)
    band = ((f >= lo) & (f <= hi)).astype(np.float64)
    shape = band * np.where(f > 0, (np.maximum(f, 1) / max(lo, 1)) ** tilt, 0)
    out = np.fft.irfft(spec * shape, n)
    return out / (np.abs(out).max() + 1e-9)


def _pad(t: np.ndarray, freqs: list[float], L: float, rng: np.random.Generator, detune: float = 0.12) -> np.ndarray:
    """Pad ấm: mỗi nốt 2 dao động lệch nhẹ + LFO biên độ chậm (tất cả lượng tử theo L)."""
    out = np.zeros((len(t), 2))
    for i, f0 in enumerate(freqs):
        for ch, d in enumerate((-detune, detune)):
            f = _q(f0 + d, L)
            lfo = 0.6 + 0.4 * np.sin(2 * np.pi * _q(rng.uniform(0.03, 0.09), L) * t + rng.uniform(0, 6.28))
            ph = rng.uniform(0, 6.28)
            tone = np.sin(2 * np.pi * f * t + ph) + 0.25 * np.sin(2 * np.pi * 2 * f * t + ph)
            out[:, ch] += tone * lfo / (1 + i * 0.4)
    return out


def _norm(x: np.ndarray, peak_db: float = -6.0) -> np.ndarray:
    return x / (np.abs(x).max() + 1e-9) * 10 ** (peak_db / 20)


def _env(n: int, attack: float, decay: float) -> np.ndarray:
    t = np.arange(n) / SR
    return np.minimum(1.0, t / max(attack, 1e-4)) * np.exp(-t / max(decay, 1e-4))


# ---------------------------------------------------------------- nhạc theo mood
def _music(mood: str, L: float = LOOP_S) -> np.ndarray:
    rng = np.random.default_rng(_SEEDS.get(mood, zlib.crc32(mood.encode("utf-8"))))
    t = _t(L)
    n = len(t)
    noise = _filtered_noise(n, 40, 900, rng, tilt=-1.2)
    air = np.stack([noise, np.roll(noise, n // 3)], axis=1) * 0.18
    if mood == "calm":
        mix = _pad(t, [110.0, 164.8, 220.0, 277.2], L, rng) + air * 0.6
    elif mood == "sad":
        mix = _pad(t, [98.0, 146.8, 196.0, 233.1], L, rng) + air * 0.7
    elif mood == "horror":
        mix = _pad(t, [55.0, 58.3, 82.4, 116.5], L, rng, detune=0.35) * 1.2
        swell = 0.5 + 0.5 * np.sin(2 * np.pi * _q(1 / 16, L) * t)
        hiss = _filtered_noise(n, 2500, 7000, rng)
        mix = mix + air * 1.4 + np.stack([hiss, np.roll(hiss, 999)], 1)[:, :] * 0.05 * swell[:, None]
    elif mood == "tense":
        mix = _pad(t, [65.4, 98.0, 138.6], L, rng, detune=0.2)
        pulse_f = _q(1.25, L)  # ~75 bpm, nhịp đập trầm
        ph = (t * pulse_f) % 1.0
        thump = np.sin(2 * np.pi * 50 * t) * np.exp(-ph * 9) * 0.9
        mix = mix + thump[:, None] + air
    else:  # mystery / mặc định
        mix = _pad(t, [73.4, 110.0, 155.6, 207.7], L, rng, detune=0.18) + air
    return _norm(mix, -6.0)


_SEEDS = {"calm": 11, "sad": 22, "horror": 33, "tense": 44, "mystery": 55}
MUSIC_MOODS = tuple(_SEEDS)


# ---------------------------------------------------------------- sfx
def _gong(rng: np.random.Generator) -> np.ndarray:
    t = _t(5.0)
    partials = [(98, 1.0, 4.0), (98 * 2.76, 0.5, 2.5), (98 * 5.4, 0.3, 1.5), (98 * 8.9, 0.15, 0.8), (151, 0.4, 3.5)]
    x = sum(a * np.sin(2 * np.pi * f * t * (1 + 0.003 * np.exp(-t))) * np.exp(-t / d) for f, a, d in partials)
    return x * np.minimum(1, t / 0.005)


def _heartbeat(rng: np.random.Generator) -> np.ndarray:
    t = _t(3.0)
    x = np.zeros_like(t)
    for beat in (0.0, 1.0, 2.0):
        for off, amp in ((0.0, 1.0), (0.28, 0.7)):
            tt = t - beat - off
            m = tt >= 0
            x[m] += amp * np.sin(2 * np.pi * 48 * tt[m] * (1 - 0.3 * tt[m])) * np.exp(-tt[m] / 0.07)
    return x


def _door(rng: np.random.Generator) -> np.ndarray:
    t = _t(2.2)
    f = 180 + 120 * np.sin(2 * np.pi * 0.6 * t) + 40 * rng.standard_normal(len(t)).cumsum() / SR * 20
    creak = np.sign(np.sin(2 * np.pi * np.cumsum(f) / SR)) * (0.5 + 0.5 * np.sin(2 * np.pi * 23 * t))
    creak *= np.minimum(1, t / 0.2) * np.clip((1.7 - t) / 0.3, 0, 1) * 0.25
    thud_t = t - 1.75
    m = thud_t >= 0
    thud = np.zeros_like(t)
    thud[m] = np.sin(2 * np.pi * 70 * thud_t[m]) * np.exp(-thud_t[m] / 0.12)
    return creak * _filtered_noise(len(t), 200, 3000, rng) * 2 + thud


def _wind(rng: np.random.Generator) -> np.ndarray:
    n = int(6.0 * SR)
    t = np.arange(n) / SR
    lo = _filtered_noise(n, 150, 700, rng)
    hi = _filtered_noise(n, 700, 2200, rng)
    gust = 0.5 + 0.5 * np.sin(2 * np.pi * 0.17 * t + 1) * np.sin(2 * np.pi * 0.05 * t)
    return (lo * (0.6 + 0.4 * gust) + hi * gust * 0.5) * np.minimum(1, t / 1.0) * np.minimum(1, (6 - t) / 1.0)


def _chop(rng: np.random.Generator) -> np.ndarray:
    n = int(0.8 * SR)
    t = np.arange(n) / SR
    crack = _filtered_noise(n, 1500, 9000, rng) * np.exp(-t / 0.02)
    thud = np.sin(2 * np.pi * 90 * t * (1 - 0.4 * t)) * np.exp(-t / 0.09)
    return crack * 0.7 + thud


def _glass_break(rng: np.random.Generator) -> np.ndarray:
    n = int(2.0 * SR)
    t = np.arange(n) / SR
    x = _filtered_noise(n, 3000, 14000, rng) * np.exp(-t / 0.08)
    for _ in range(14):
        start = rng.uniform(0.02, 0.9)
        f = rng.uniform(2500, 7500)
        tt = t - start
        m = tt >= 0
        x[m] += rng.uniform(0.2, 0.5) * np.sin(2 * np.pi * f * tt[m]) * np.exp(-tt[m] / rng.uniform(0.05, 0.3))
    return x


def _footsteps(rng: np.random.Generator) -> np.ndarray:
    n = int(2.6 * SR)
    t = np.arange(n) / SR
    x = np.zeros(n)
    for k in range(5):
        start = 0.05 + k * 0.5 + rng.uniform(-0.03, 0.03)
        tt = t - start
        m = tt >= 0
        step = _filtered_noise(int(m.sum()), 80, 1200, rng) * np.exp(-tt[m] / 0.05)
        x[m] += step * (0.8 + 0.2 * rng.random())
    return x


def _sizzle(rng: np.random.Generator) -> np.ndarray:
    n = int(3.0 * SR)
    t = np.arange(n) / SR
    bed = _filtered_noise(n, 3000, 12000, rng) * 0.25
    pops = (rng.random(n) < 0.0015) * rng.uniform(0.3, 1.0, n)
    crackle = np.convolve(pops, np.exp(-np.arange(200) / 30.0), mode="same") * rng.choice([-1, 1], n)
    return (bed + crackle) * np.minimum(1, t / 0.3) * np.minimum(1, (3 - t) / 0.5)


def _metal_clank(rng: np.random.Generator) -> np.ndarray:
    t = _t(1.6)
    parts = [(523, 1.0, 0.5), (523 * 2.32, 0.6, 0.35), (523 * 3.9, 0.4, 0.2), (1789, 0.3, 0.15)]
    x = sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t / d) for f, a, d in parts)
    return x + _filtered_noise(len(t), 2000, 9000, rng) * np.exp(-t / 0.01)


def _whisper(rng: np.random.Generator) -> np.ndarray:
    n = int(3.0 * SR)
    t = np.arange(n) / SR
    syll = np.clip(np.sin(2 * np.pi * 3.1 * t) * np.sin(2 * np.pi * 0.7 * t + 0.5), 0, 1) ** 0.7
    return _filtered_noise(n, 1500, 6000, rng) * syll * np.minimum(1, (3 - t) / 0.4)


def _crowd(rng: np.random.Generator) -> np.ndarray:
    n = int(8.0 * SR)
    t = np.arange(n) / SR
    x = np.zeros(n)
    for _ in range(10):  # mỗi "người" là dải nhiễu giọng được điều biên ngẫu nhiên
        f0 = rng.uniform(300, 900)
        voice = _filtered_noise(n, f0, f0 * 2.2, rng)
        mod = np.clip(np.sin(2 * np.pi * rng.uniform(1.5, 4) * t + rng.uniform(0, 6)) *
                      np.sin(2 * np.pi * rng.uniform(0.1, 0.4) * t + rng.uniform(0, 6)), 0, 1)
        x += voice * mod
    return x * np.minimum(1, t / 1.0) * np.minimum(1, (8 - t) / 1.5)


SFX_GENERATORS: dict[str, Callable[[np.random.Generator], np.ndarray]] = {
    "gong": _gong, "heartbeat": _heartbeat, "door": _door, "wind": _wind,
    "chop": _chop, "glass_break": _glass_break, "footsteps": _footsteps,
    "sizzle": _sizzle, "metal_clank": _metal_clank, "whisper": _whisper, "crowd": _crowd,
}


# ---------------------------------------------------------------- lưu file
def _save(data: np.ndarray, dst: Path) -> Path:
    """Ghi ra .ogg (nhỏ) qua ffmpeg; nếu ffmpeg không có vorbis thì để .wav."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="stoon_gen_") as td:
        tmp = audio_io.write_wav(Path(td) / "x.wav", data)
        try:
            return audio_io.encode(tmp, dst.with_suffix(".ogg"))
        except RuntimeError:
            wav = dst.with_suffix(".wav")
            wav.write_bytes(tmp.read_bytes())
            return wav


def find_audio(folder: Path, name: str) -> Path | None:
    """assets/<folder>/<name>.<ext> hoặc file đầu tiên trong assets/<folder>/<name>/."""
    for ext in AUDIO_EXTS:
        p = folder / f"{name}{ext}"
        if p.exists():
            return p
    sub = folder / name
    if sub.is_dir():
        files = sorted(p for p in sub.iterdir() if p.suffix.lower() in AUDIO_EXTS)
        if files:
            return files[0]
    return None


def make_music(mood: str, folder: Path = MUSIC) -> Path:
    log.info("Tạo nhạc nền thủ tục cho mood '%s'", mood)
    return _save(_music(mood), folder / mood)


def make_sfx(name: str, folder: Path = SFX) -> Path | None:
    gen = SFX_GENERATORS.get(name)
    if gen is None:
        return None
    x = gen(np.random.default_rng(len(name) * 7919))
    x = _norm(np.asarray(x, dtype=np.float64), -3.0)
    log.info("Tạo hiệu ứng thủ tục '%s'", name)
    return _save(np.stack([x, x], axis=1), folder / name)


def ensure_default_assets(music_dir: Path = MUSIC, sfx_dir: Path = SFX) -> list[Path]:
    """Tạo các file nhạc/sfx mặc định còn thiếu. Không ghi đè file người dùng đã đặt."""
    made: list[Path] = []
    for mood in MUSIC_MOODS:
        if find_audio(music_dir, mood) is None:
            made.append(make_music(mood, music_dir))
    for name in SFX_GENERATORS:
        if find_audio(sfx_dir, name) is None:
            p = make_sfx(name, sfx_dir)
            if p:
                made.append(p)
    return made
