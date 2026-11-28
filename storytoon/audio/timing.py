"""Bước audio của pipeline: TTS mọi câu thoại -> điền Line.audio/start/duration/visemes, Shot.duration,
và ghi projects/<p>/subtitles.srt.

    fill_timing(storyboard, project_dir, cfg=None, *, progress=None, lipsync=True) -> Storyboard
    shot_offsets(storyboard) -> list[float]      # thời điểm bắt đầu tuyệt đối của từng shot
    film_duration(storyboard) -> float
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import textwrap
import zlib
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..schema import CharacterDef, Line, Shot, Storyboard
from . import lipsync as _lip
from . import tts
from . import voices

log = logging.getLogger(__name__)

FIRST_LINE_START = 0.25   # giây, câu đầu tiên trong shot (bố cục cũ, dùng khi không có kịch bản)
LINE_GAP = 0.15           # nghỉ giữa các câu trong shot
TAIL = 0.45               # đuôi sau câu cuối

# Nghỉ theo nội dung câu chuyện (không theo ranh giới shot)
PAUSE_SENTENCE = 0.35     # câu nối tiếp trong cùng đoạn văn
PAUSE_PARAGRAPH = 0.8     # sang đoạn văn mới
PAUSE_SCENE = 1.2         # đổi bối cảnh hoặc có thẻ chương
SHOT_LEAD = 0.15          # phần khoảng nghỉ nằm ở đầu shot mới (hình đổi trước tiếng một chút)
FILM_LEAD = 0.25          # lặng trước câu đầu tiên của phim
FILM_TAIL = 0.8           # lặng sau câu cuối cùng của phim
TAIL_BEFORE_SILENT = 0.3  # đuôi khi shot kế tiếp không có lời (shot đó tự tạo khoảng nghỉ)
MIN_SHOT = 0.5            # thời lượng tối thiểu của 1 shot (giây)
TTS_CONCURRENCY = 4
LIPSYNC_WORKERS = 4

Progress = Callable[[str, float], None]

# điều chỉnh giọng theo độ tuổi (edge-tts chỉ có 2 giọng tiếng Việt -> phân biệt bằng pitch/rate)
_AGE_TUNING: dict[str, tuple[int, int]] = {   # (Δrate %, Δpitch Hz)
    "child": (8, 30), "young": (4, 8), "adult": (0, 0), "old": (-10, -10),
}
_SAME_VOICE_PITCH_STEPS = (0, -6, 6, -12, 12, -18, 18)


@dataclass(frozen=True)
class VoiceSpec:
    voice: str
    rate: str = "+0%"
    pitch: str = "+0Hz"


def _parse_pct(rate: str) -> int:
    m = re.fullmatch(r"\s*([+-]?\d+)\s*%\s*", rate or "")
    return int(m.group(1)) if m else 0


def _fmt(v: int, unit: str) -> str:
    return f"{v:+d}{unit}"


def _tts_cfg(cfg: dict[str, Any] | None) -> dict[str, Any]:
    if cfg is None:
        from ..config import cfg as load_cfg
        cfg = load_cfg()
    return dict(cfg.get("tts") or {})


def build_voice_map(sb: Storyboard, tcfg: dict[str, Any]) -> dict[str, VoiceSpec]:
    """speaker id -> VoiceSpec. Nhân vật trùng giọng gốc + cùng tuổi được lệch pitch để dễ phân biệt."""
    base_rate = _parse_pct(str(tcfg.get("rate", "+0%")))
    engine, language = tcfg.get('engine', 'edge'), tcfg.get('language', 'vi')
    narrator = voices.selected(engine, language, tcfg.get('narrator_voice'))
    defaults = {"male": voices.selected(engine, language, tcfg.get('default_male'), 'nam'),
                "female": voices.selected(engine, language, tcfg.get('default_female'), 'nu')}
    out = {"narrator": VoiceSpec(narrator, _fmt(base_rate, "%"), "+0Hz")}
    used: dict[tuple[str, int, int], int] = {}
    for c in sb.characters:
        # Generated storyboards may still carry old Edge IDs. Settings are authoritative;
        # explicit character overrides are opt-in and must match engine AND language.
        explicit = bool(tcfg.get('use_character_voices')) and voices.valid(c.voice, engine, language)
        voice = c.voice if explicit else defaults.get(c.gender, narrator)
        d_rate, d_pitch = _AGE_TUNING.get(c.age, (0, 0))
        if not explicit:
            k = (voice, d_rate, d_pitch)
            idx = used.get(k, 0)
            used[k] = idx + 1
            # người dẫn chuyện chiếm vị trí 0 của giọng narrator ở tuổi adult
            if voice == narrator and d_pitch == 0:
                idx += 1
            d_pitch += _SAME_VOICE_PITCH_STEPS[idx % len(_SAME_VOICE_PITCH_STEPS)]
        out[c.id] = VoiceSpec(voice, _fmt(base_rate + d_rate, "%"), _fmt(d_pitch, "Hz"))
    return out


def _voice_for(speaker: str, vmap: dict[str, VoiceSpec]) -> VoiceSpec:
    if speaker not in vmap:
        log.warning("Không có nhân vật '%s' trong storyboard — dùng giọng người dẫn chuyện.", speaker)
    return vmap.get(speaker, vmap["narrator"])


def _audio_name(shot: Shot, idx: int, line: Line, spec: VoiceSpec, engine_name: str = 'edge') -> str:
    key = tts.cache_key(line.text, spec.voice, spec.rate, spec.pitch, engine_name)
    return f"{shot.id}_{idx:02d}_{key[:10]}.wav"


# ---------------------------------------------------------------- TTS song song
async def _synth_all(jobs: list[tuple[Line, VoiceSpec, Path]], progress: Progress | None,
                     engine: tts.TTSEngine | None = None) -> list[float]:
    sem = asyncio.Semaphore(TTS_CONCURRENCY)
    engine = engine or tts.get_engine()
    done = 0

    async def one(line: Line, spec: VoiceSpec, path: Path) -> float:
        nonlocal done
        async with sem:
            d = await tts.synth_line_async(line.text, spec.voice, path, rate=spec.rate, pitch=spec.pitch,
                                           engine=engine)
        done += 1
        if progress:
            progress(f"Lồng tiếng {done}/{len(jobs)}", done / max(1, len(jobs)))
        return d

    return list(await asyncio.gather(*(one(*j) for j in jobs)))


# ---------------------------------------------------------------- lip sync (có cache)
def _visemes_cached(wav: Path, text: str, cache_dir: Path, use_rhubarb: bool) -> list[tuple[float, str]]:
    cache = cache_dir / (wav.stem + ".json")
    if use_rhubarb and cache.exists():
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            # khẩu hình tính trên wav chưa cắt lặng sẽ lệch thời điểm → tính lại
            if data.get("source") == "rhubarb" and data.get("trim") == tts.TRIM_VERSION:
                return [(float(t), str(s)) for t, s in data["visemes"]]
        except (OSError, ValueError, KeyError):
            pass
    vis: list[tuple[float, str]] | None = None
    if use_rhubarb:
        try:
            vis = _lip.run_rhubarb(tts.wav16_path(wav) if tts.wav16_path(wav).exists() else wav)
        except Exception as e:
            log.warning("Rhubarb lỗi cho %s (%s) — dùng biên độ.", wav.name, e)
    if vis:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"source": "rhubarb", "visemes": vis, "trim": tts.TRIM_VERSION}),
                         encoding="utf-8")
        return vis
    return _lip.amplitude_visemes(wav)


# ---------------------------------------------------------------- tổng hợp
def shot_offsets(sb: Storyboard) -> list[float]:
    offs, t = [], 0.0
    for s in sb.shots:
        offs.append(round(t, 3))
        t += s.duration if s.duration is not None else s.min_duration
    return offs


def film_duration(sb: Storyboard) -> float:
    return round(sum(s.duration if s.duration is not None else s.min_duration for s in sb.shots), 3)


def layout_shot(shot: Shot) -> None:
    """Xếp các câu nối tiếp trong shot và tính Shot.duration (cần Line.duration đã có)."""
    t = FIRST_LINE_START
    end = 0.0
    for ln in shot.lines:
        ln.start = round(t, 3)
        end = t + (ln.duration or 0.0)
        t = end + LINE_GAP
    # sàn MIN_SHOT: min_duration 0/âm (sửa tay) làm shot 0 s -> renderer vẫn phải ra >= 1 frame -> lệch tiếng/hình
    shot.duration = round(max(shot.min_duration, end + TAIL if shot.lines else 0.0, MIN_SHOT), 3)


def _is_scene_break(prev: Shot, shot: Shot, between: list[Shot]) -> bool:
    if shot.location != prev.location:
        return True
    return any(o.kind == "chapter_card" for s in [*between, shot] for o in s.overlays)


def story_pauses(sb: Storyboard, script_text: str | None) -> tuple[list[float], int]:
    """Khoảng nghỉ trước từng câu (thứ tự phim) và số câu đối chiếu được với kịch bản."""
    from .paragraphs import line_paragraphs

    order = [(si, ln) for si, s in enumerate(sb.shots) for ln in s.lines]
    paras = line_paragraphs(script_text or "", [ln.text for _, ln in order])
    pauses: list[float] = []
    for k, (si, _ln) in enumerate(order):
        if k == 0:
            pauses.append(FILM_LEAD)
            continue
        pi = order[k - 1][0]
        if si != pi and _is_scene_break(sb.shots[pi], sb.shots[si], sb.shots[pi + 1:si]):
            pauses.append(PAUSE_SCENE)
            continue
        a, b = paras[k - 1], paras[k]
        pauses.append(PAUSE_PARAGRAPH if a and b and b[0] != a[1] else PAUSE_SENTENCE)
    return pauses, sum(1 for p in paras if p)


def layout_story(sb: Storyboard, pauses: list[float]) -> None:
    """Xếp câu theo khoảng nghỉ câu chuyện; mỗi khoảng nghỉ giữa 2 shot chia thành đuôi shot trước
    + SHOT_LEAD đầu shot sau. Shot không lời giữ min_duration như cũ."""
    k = 0
    starts: dict[int, int] = {}          # shot index -> chỉ số câu đầu tiên (thứ tự phim)
    for si, s in enumerate(sb.shots):
        if s.lines:
            starts[si] = k
            k += len(s.lines)

    def lead(si: int) -> float:
        first = starts[si]
        if first == 0:
            return pauses[0]
        if si > 0 and not sb.shots[si - 1].lines:   # sau shot không lời: khoảng nghỉ đã có sẵn
            return SHOT_LEAD
        return min(SHOT_LEAD, pauses[first])

    for si, shot in enumerate(sb.shots):
        if not shot.lines:
            shot.duration = round(max(shot.min_duration, MIN_SHOT), 3)
            continue
        k = starts[si]
        t = lead(si)
        end = t
        for j, ln in enumerate(shot.lines):
            if j:
                t = end + pauses[k + j]
            ln.start = round(t, 3)
            end = t + (ln.duration or 0.0)
        if si + 1 >= len(sb.shots):
            tail = FILM_TAIL
        elif sb.shots[si + 1].lines:
            tail = max(0.0, pauses[starts[si + 1]] - lead(si + 1))
        else:
            tail = TAIL_BEFORE_SILENT
        shot.duration = round(max(shot.min_duration, end + tail, MIN_SHOT), 3)


def _srt_time(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(sb: Storyboard, out: Path, *, width: int = 45) -> Path:
    blocks: list[str] = []
    for off, shot in zip(shot_offsets(sb), sb.shots):
        for ln in shot.lines:
            if ln.start is None or ln.duration is None:
                continue
            a = off + ln.start
            text = "\n".join(textwrap.wrap(tts.normalize_text(ln.text), width)) or " "
            blocks.append(f"{len(blocks) + 1}\n{_srt_time(a)} --> {_srt_time(a + ln.duration)}\n{text}\n")
    out.write_text("\n".join(blocks), encoding="utf-8")
    return out


def fill_timing(storyboard: Storyboard, project_dir: Path, cfg: dict[str, Any] | None = None, *,
                progress: Progress | None = None, lipsync: bool = True,
                script_text: str | None = None) -> Storyboard:
    """Điền thời gian/âm thanh/viseme cho storyboard (sửa tại chỗ và trả về chính nó).

    Có `script_text` → khoảng nghỉ theo câu chuyện (câu / đoạn văn / đổi cảnh); không có → bố cục cũ.
    """
    project_dir = Path(project_dir)
    audio_dir = project_dir / "audio"
    lip_dir = project_dir / "lipsync"
    audio_dir.mkdir(parents=True, exist_ok=True)
    tcfg = _tts_cfg(cfg)
    vmap = build_voice_map(storyboard, tcfg)
    engine = tts.get_engine(tcfg.get('engine', 'edge'), language=tcfg.get('language', 'vi'))

    jobs: list[tuple[Line, VoiceSpec, Path]] = []
    for shot in storyboard.shots:
        shot.lines = [ln for ln in shot.lines if tts.normalize_text(ln.text)]
        for i, ln in enumerate(shot.lines):
            spec = _voice_for(ln.speaker, vmap)
            jobs.append((ln, spec, audio_dir / _audio_name(shot, i, ln, spec, engine.name)))

    durations = tts.run_coro(_synth_all(jobs, progress, engine))
    for (ln, _spec, path), d in zip(jobs, durations):
        ln.audio = path.relative_to(project_dir).as_posix()
        ln.duration = round(d, 3)

    if progress:
        progress("Khớp khẩu hình", 0.0)
    use_rhubarb = lipsync and _lip.ensure_rhubarb() is not None
    with ThreadPoolExecutor(max_workers=LIPSYNC_WORKERS) as ex:
        results = list(ex.map(lambda j: _visemes_cached(j[2], j[0].text, lip_dir, use_rhubarb), jobs))
    for (ln, _s, _p), vis in zip(jobs, results):
        ln.visemes = vis

    if script_text and script_text.strip():
        pauses, matched = story_pauses(storyboard, script_text)
        layout_story(storyboard, pauses)
        total = len(pauses)
        log.info("Khoảng nghỉ theo câu chuyện: %d/%d câu đối chiếu được với kịch bản.", matched, total)
        if progress:
            progress(f"Xếp khoảng nghỉ theo đoạn văn ({matched}/{total} câu khớp kịch bản)", 0.99)
    else:
        for shot in storyboard.shots:
            layout_shot(shot)
    write_srt(storyboard, project_dir / "subtitles.srt")
    if progress:
        progress("Xong phần âm thanh", 1.0)
    return storyboard

