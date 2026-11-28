"""Trộn toàn bộ âm thanh của phim thành 1 file wav 48 kHz stereo.

    build_soundtrack(storyboard, project_dir, out_wav) -> Path

- Giọng: mỗi Line đặt tại (offset shot + Line.start). Cần chạy timing.fill_timing trước.
- Nhạc nền: theo Shot.music_mood (None = giữ nhạc trước; "none"/"silence" = tắt nhạc), lặp lại cho đủ,
  crossfade khi đổi mood, ducking −12 dB khi có lời.
- Nhạc: mỗi mood có nhiều bài (assets/music/catalog.json); các đoạn cùng mood luân phiên bài khác nhau.
- SFX một lần (oneshot): phát ở đầu shot.
- SFX âm nền (ambience: mưa, phố, côn trùng đêm…): lặp liền mạch suốt chuỗi shot liên tiếp có cùng âm,
  vào/ra mềm, hạ nhỏ khi có lời.
- File nhạc/sfx tìm qua catalog, rồi assets/music/<mood>.* và assets/sfx/<tên>.*; thiếu thì tạo bản thủ tục.

Mức âm tính theo độ to giọng đọc của phim (RMS phần có tiếng). Tham số tuỳ chọn trong config.yaml:
    audio: {music_below_voice_db: 18, duck_db: -8, music_cue_max_s: 60, music_rest_s: 20,
            ambience_below_voice_db: 20, ambience_duck_db: -6, sfx_below_voice_db: 10, sfx_peak_db: -8,
            crossfade_s: 2.0}
    (music_rms_db / ambience_rms_db đặt cố định nếu muốn bỏ qua cách tính theo giọng)
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from ..config import get
from ..paths import MUSIC, SFX
from ..schema import Storyboard
from . import audio_io, library, procedural
from .timing import film_duration, shot_offsets

log = logging.getLogger(__name__)
SR = audio_io.SR

MOOD_ALIASES = {
    "scary": "horror", "fear": "horror", "dark": "horror", "creepy": "horror", "ghost": "horror",
    "suspense": "tense", "danger": "tense", "tension": "tense",
    "chase": "action", "fight": "action", "escape": "action",
    "peaceful": "calm", "neutral": "calm", "daily": "calm",
    "happy": "warm", "tender": "warm", "nostalgic": "warm", "family": "warm",
    "melancholy": "sad", "grief": "sad", "sorrow": "sad",
    "mysterious": "mystery", "eerie": "mystery", "curious": "mystery",
    "police": "investigation", "detective": "investigation", "interrogation": "investigation",
    "reveal": "shock", "twist": "shock", "shocked": "shock",
    "hope": "hopeful", "ending": "hopeful", "resolution": "hopeful", "relief": "hopeful",
    "hacker": "tech", "technology": "tech", "cyber": "tech",
}
# mood chưa có bài trong thư viện → mượn bài thật của mood gần nhất
_LIBRARY_FALLBACK = {"shock": "horror", "hopeful": "warm", "tech": "mystery", "action": "tense",
                     "investigation": "mystery", "warm": "calm"}
# mood mới → mood thủ tục gần nhất khi bản cũ chưa có thư viện nhạc
_PROCEDURAL_FALLBACK = {"warm": "calm", "hopeful": "calm", "investigation": "mystery", "tech": "mystery",
                        "action": "tense", "shock": "horror"}
SILENT_MOODS = {"none", "silence", "off", "stop"}
SFX_TAIL_S = 0.4      # âm một lần được kéo quá cuối shot tối đa bấy nhiêu giây rồi tắt dần
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
def resolve_music(mood: str, nth: int = 0, seed: str = "") -> Path | None:
    """Bài nhạc cho mood; nth = lần thứ mấy mood này xuất hiện trong phim (để luân phiên bài)."""
    mood = mood.strip().lower()
    canon = MOOD_ALIASES.get(mood, mood)
    p = library.music_track(canon, nth, seed) or library.music_track(_LIBRARY_FALLBACK.get(canon, ""), nth, seed)
    if p:
        return p
    p = procedural.find_audio(MUSIC, mood)
    if p:
        return p
    canon = _PROCEDURAL_FALLBACK.get(canon, canon)
    if canon not in procedural.MUSIC_MOODS:
        log.warning("Không có nhạc cho mood '%s' — dùng 'mystery'.", mood)
        canon = "mystery"
    return procedural.find_audio(MUSIC, canon) or procedural.make_music(canon, MUSIC)


def resolve_sound(name: str) -> library.SoundInfo | None:
    """Hiệu ứng theo tên (catalog → file cùng tên → tên đồng nghĩa cũ → âm thủ tục)."""
    info = library.sfx(name)
    if info:
        return info
    key = name.strip().lower().replace(" ", "_")
    canon = SFX_ALIASES.get(key, key)
    p = (procedural.find_audio(SFX, key) or procedural.find_audio(SFX, canon)
         or procedural.make_sfx(canon, SFX))
    if p is None:
        log.warning("Không tìm thấy hiệu ứng '%s' trong assets/sfx — bỏ qua.", name)
        return None
    return library.SoundInfo(canon, p)


def resolve_sfx(name: str) -> Path | None:
    info = resolve_sound(name)
    return info.path if info else None


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


def active_rms_db(x: np.ndarray, floor_db: float = -45.0) -> float | None:
    """RMS (dBFS) chỉ tính các khung 10 ms có tiếng (bỏ khoảng lặng) — độ to cảm nhận của giọng/âm."""
    mono = x if x.ndim == 1 else x.mean(axis=1)
    hop = SR // 100
    n = len(mono) // hop
    if n == 0:
        return None
    fr = np.sqrt((mono[: n * hop].astype(np.float64).reshape(n, hop) ** 2).mean(axis=1))
    act = fr[fr > _db(floor_db)]
    if len(act) == 0:
        return None
    return float(20 * np.log10(np.sqrt((act ** 2).mean()) + 1e-12))


def _loudness_normalize(x: np.ndarray, target_db: float, peak_cap_db: float) -> np.ndarray:
    """Đưa âm về độ to `target_db` (RMS phần có tiếng) nhưng đỉnh không vượt `peak_cap_db`."""
    cur = active_rms_db(x, floor_db=-60.0)
    if cur is None:
        return x.astype(np.float32)
    gain = _db(target_db - cur)
    peak = float(np.abs(x).max()) * gain
    if peak > _db(peak_cap_db):
        gain *= _db(peak_cap_db) / peak
    return (x * gain).astype(np.float32)


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
def music_segments(sb: Storyboard, *, cue_max: float | None = None,
                   rest: float | None = None) -> list[tuple[str, float, float]]:
    """[(mood, t_bắt_đầu, t_kết_thúc)] — nhạc là các *đoạn* ở nhịp cảm xúc, không phủ kín cả phim.

    Mỗi lần đặt mood mở một đoạn; đoạn kết thúc khi đổi mood, gặp "none", hoặc dài quá `cue_max` giây
    (cắt ở ranh giới shot đầu tiên sau mốc đó) → im lặng tới lần đặt mood kế tiếp. Đặt lại đúng mood vừa
    hết trong vòng `rest` giây thì bỏ qua, để có quãng lặng.
    """
    cue_max = float(get("audio.music_cue_max_s", 60)) if cue_max is None else cue_max
    rest = float(get("audio.music_rest_s", 20)) if rest is None else rest
    segs: list[tuple[str, float, float]] = []
    cur: str | None = None
    start = 0.0
    last_mood: str | None = None
    last_end = -1e9
    offs = shot_offsets(sb)
    for off, shot in zip(offs, sb.shots):
        mood = (shot.music_mood or "").strip().lower() or None
        if cur is not None and off - start >= cue_max:       # đoạn nhạc đủ dài → tắt ở điểm cắt cảnh này
            segs.append((cur, start, off))
            last_mood, last_end, cur = cur, off, None
        if mood is None or mood == cur:
            continue
        if mood in SILENT_MOODS:
            if cur is not None:
                segs.append((cur, start, off))
                last_mood, last_end, cur = cur, off, None
            continue
        if cur is None and mood == last_mood and off - last_end < rest:
            continue                                          # vừa hết đoạn cùng tâm trạng → để lặng một lúc
        if cur is not None:
            segs.append((cur, start, off))
        cur, start = mood, off
    if cur is not None:
        segs.append((cur, start, film_duration(sb)))
    return [s for s in segs if s[2] - s[1] > 0.05]


def ambience_runs(sb: Storyboard, offs: list[float] | None = None) -> list[tuple[str, float, float]]:
    """[(tên, t_bắt_đầu, t_kết_thúc)] cho âm nền: các shot liên tiếp cùng âm gộp thành 1 đoạn liền."""
    offs = offs if offs is not None else shot_offsets(sb)
    ends = [o + (s.duration if s.duration is not None else s.min_duration) for o, s in zip(offs, sb.shots)]
    runs: list[tuple[str, float, float]] = []
    open_runs: dict[str, float] = {}
    for i, shot in enumerate(sb.shots):
        names = set()
        for name in shot.sfx:
            info = library.sfx(name)
            if info and info.kind == "ambience":
                names.add(info.key)
        for key in list(open_runs):
            if key not in names:
                runs.append((key, open_runs.pop(key), ends[i - 1]))
        for key in names:
            open_runs.setdefault(key, offs[i])
    for key, start in open_runs.items():
        runs.append((key, start, ends[-1] if ends else 0.0))
    return sorted(runs, key=lambda r: (r[1], r[0]))


def build_soundtrack(storyboard: Storyboard, project_dir: Path, out_wav: Path, *,
                     music: bool = True, sfx: bool = True) -> Path:
    project_dir = Path(project_dir)
    out_wav = Path(out_wav)
    total = film_duration(storyboard)
    n = int(np.ceil(total * SR)) + 1
    xf_s = float(get("audio.crossfade_s", 2.0))

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

    # mọi mức âm tính tương đối theo độ to giọng đọc của chính phim này
    voice_db = active_rms_db(voice)
    voice_db = -16.0 if voice_db is None else min(max(voice_db, -26.0), -10.0)
    music_rms = (float(get("audio.music_rms_db")) if get("audio.music_rms_db") is not None
                 else voice_db - float(get("audio.music_below_voice_db", 18)))
    duck_db = float(get("audio.duck_db", -8))
    sfx_level = voice_db - float(get("audio.sfx_below_voice_db", 10))
    sfx_peak = float(get("audio.sfx_peak_db", -8))
    amb_rms = (float(get("audio.ambience_rms_db")) if get("audio.ambience_rms_db") is not None
               else voice_db - float(get("audio.ambience_below_voice_db", 20)))
    amb_duck = float(get("audio.ambience_duck_db", -6))
    log.info("Mức âm: giọng %.1f dB · nhạc %.1f dB (−%.0f khi đọc) · nền %.1f dB · hiệu ứng %.1f dB",
             voice_db, music_rms, -duck_db, amb_rms, sfx_level)

    # nhạc nền
    if music:
        bed = np.zeros((n, 2), dtype=np.float32)
        xf = int(xf_s * SR)
        cache: dict[Path, np.ndarray] = {}
        seen: dict[str, int] = {}
        for i, (mood, t0, t1) in enumerate(music_segments(storyboard)):
            nth = seen.get(mood, 0)
            seen[mood] = nth + 1
            path = resolve_music(mood, nth, storyboard.title)
            if path is None:
                continue
            if path not in cache:
                cache[path] = _rms_normalize(audio_io.decode(path, channels=2), music_rms)
            a = int(t0 * SR)
            b = min(n, int(t1 * SR))            # kết thúc đúng điểm cắt cảnh, tắt dần trước đó
            if b - a < SR:
                continue
            seg = loop_to(cache[path], b - a)
            fin = min(len(seg) // 3, int(1.5 * SR))
            seg[:fin] *= np.linspace(0, 1, fin, dtype=np.float32)[:, None]
            fout = min(len(seg) // 3, xf)
            seg[len(seg) - fout:] *= np.linspace(1, 0, fout, dtype=np.float32)[:, None]
            bed[a:b] += seg
        cache.clear()
        # nhả chậm (1.2 s): nhạc không "bơm" to lên trong quãng nghỉ ngắn giữa các câu
        bed *= duck_gain(voice, duck_db, release=1.2)[:, None]
        mix += bed
        del bed

    # hiệu ứng
    if sfx:
        # âm nền: lặp liền mạch trên cả chuỗi shot, vào/ra mềm, hạ nhỏ khi có lời
        runs = ambience_runs(storyboard, offs)
        if runs:
            bed = np.zeros((n, 2), dtype=np.float32)
            amb_cache: dict[str, np.ndarray] = {}
            for key, t0, t1 in runs:
                info = library.sfx(key)
                if info is None:
                    continue
                if key not in amb_cache:
                    amb_cache[key] = _rms_normalize(audio_io.decode(info.path, channels=2), amb_rms)
                a, b = int(t0 * SR), min(n, int(t1 * SR))
                if b - a < SR // 10:
                    continue
                seg = loop_to(amb_cache[key], b - a, xfade=SR)
                fin, fout = min(len(seg), int(0.6 * SR)), min(len(seg), int(1.0 * SR))
                seg[:fin] *= np.linspace(0, 1, fin, dtype=np.float32)[:, None]
                seg[len(seg) - fout:] *= np.linspace(1, 0, fout, dtype=np.float32)[:, None]
                bed[a:b] += seg
            bed *= duck_gain(voice, amb_duck)[:, None]
            mix += bed
            del bed, amb_cache
        fx_cache: dict[str, np.ndarray | None] = {}
        for off, shot in zip(offs, storyboard.shots):
            for name in shot.sfx:
                if name not in fx_cache:   # mỗi hiệu ứng chỉ tìm/giải mã 1 lần (phim dài lặp lại nhiều)
                    info = resolve_sound(name)
                    fx_cache[name] = (None if info is None or info.kind == "ambience" else
                                      _loudness_normalize(audio_io.decode(info.path, channels=2),
                                                          sfx_level, sfx_peak))
                fx = fx_cache[name]
                if fx is None:
                    continue
                # âm một lần chỉ kéo dài trong shot của nó (+0.4 s đuôi), tắt dần — khớp với hình
                dur = shot.duration if shot.duration is not None else shot.min_duration
                a = int(off * SR)
                length = min(len(fx), int((dur + SFX_TAIL_S) * SR), n - a)
                if length <= 0:
                    continue
                seg = fx[:length].copy()
                if length < len(fx):
                    fo = min(length // 2, int(0.35 * SR))
                    seg[length - fo:] *= np.linspace(1, 0, fo, dtype=np.float32)[:, None]
                mix[a:a + length] += seg

    return audio_io.write_wav(out_wav, soft_limit(mix, inplace=True), SR)
