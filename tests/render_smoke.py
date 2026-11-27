"""Smoke test engine render: dựng Storyboard trong code (không cần audio), render vài shot + ảnh tĩnh + ghép phim.

Chạy:  runtime\\venv\\Scripts\\python.exe tests\\render_smoke.py [--quick] [--no-film]
Kết quả: logs/render_test/*.mp4, logs/render_test/frames/*.png, logs/render_test/film.mp4
"""
from __future__ import annotations

import argparse
import logging
import math
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storytoon.paths import LOGS  # noqa: E402
from storytoon.schema import (CharacterDef, CharacterInShot, Line, LocationDef, Overlay, Shot,  # noqa: E402
                              Storyboard)

OUT = LOGS / "render_test"
SHAPES = "BCDCEBFCADGCHB"


def fake_visemes(dur: float, step: float = 0.11) -> list[tuple[float, str]]:
    out, t, i = [], 0.0, 0
    while t < dur - 0.1:
        out.append((round(t, 3), SHAPES[i % len(SHAPES)] if (i % 7) != 6 else "X"))
        t += step
        i += 1
    out.append((round(dur - 0.08, 3), "X"))
    return out


def line(speaker: str, text: str, start: float, dur: float) -> Line:
    return Line(speaker=speaker, text=text, start=start, duration=dur,
                visemes=fake_visemes(dur) if speaker != "narrator" else None)


def build_storyboard() -> Storyboard:
    chars = [
        CharacterDef(id="chu_tu", name="Chú Tư", role="Chủ tiệm bánh bao", gender="male", age="old"),
        CharacterDef(id="toi", name="Tôi", role="Nhân viên ca đêm", gender="male", age="young"),
        CharacterDef(id="co_lan", name="Cô Lan", role="Khách quen", gender="female", age="young"),
    ]
    locs = [
        LocationDef(id="cho_dem", name="Chợ đêm", time_of_day="night", signs=["BÁNH BAO CHÚ TƯ"]),
        LocationDef(id="hem_toi", name="Hẻm tối", time_of_day="night"),
    ]
    shots = [
        Shot(id="t01", location="cho_dem", framing="wide", camera="zoom_in", duration=4.0,
             characters=[CharacterInShot(id="chu_tu", slot="counter", action="idle", facing="left"),
                         CharacterInShot(id="toi", slot="left", action="sit", facing="right")],
             lines=[line("narrator", "Năm đó tôi xin vào làm ca đêm ở tiệm bánh bao của chú Tư, ngay giữa chợ Lớn.",
                         0.3, 3.4)],
             overlays=[Overlay(kind="location_card", title="Chợ Lớn · Sài Gòn", subtitle="Quận 5"),
                       Overlay(kind="time_card", title="23:45", subtitle="Đêm thứ nhất")]),
        Shot(id="t02", location="cho_dem", framing="medium", camera="pan_right", duration=4.0,
             characters=[CharacterInShot(id="toi", slot="center", action="point", facing="right",
                                         expression="surprised"),
                         CharacterInShot(id="chu_tu", slot="counter", action="talk", facing="left",
                                         expression="angry")],
             lines=[line("chu_tu", "Đừng bao giờ mở cái tủ đó sau nửa đêm, nghe chưa?", 0.3, 3.2)],
             overlays=[Overlay(kind="nametag", title="Chú Tư", subtitle="Chủ tiệm bánh bao", character_id="chu_tu")]),
        Shot(id="t03", location="cho_dem", framing="close", camera="push_in_slow", focus="chu_tu", duration=4.0,
             characters=[CharacterInShot(id="chu_tu", slot="center", action="talk", facing="right",
                                         expression="evil")],
             lines=[line("chu_tu", "Luật thứ nhất: không bán cho khách không có bóng.", 0.3, 3.0)],
             overlays=[Overlay(kind="rule_card", title="Không bán cho khách *không có bóng*.",
                               subtitle="Luật số 1")]),
        Shot(id="t04", location="hem_toi", framing="medium", camera="shake", duration=3.5,
             characters=[CharacterInShot(id="co_lan", slot="center", action="scared", facing="left"),
                         CharacterInShot(id="toi", slot="left", action="walk", facing="right")],
             lines=[line("co_lan", "Ai… ai đang đứng sau lưng anh vậy?", 0.4, 2.6)],
             overlays=[Overlay(kind="nametag", title="Cô Lan", character_id="co_lan")]),
        Shot(id="t05", location="hem_toi", framing="extreme_close", camera="static", focus="co_lan", duration=2.5,
             characters=[CharacterInShot(id="co_lan", slot="center", action="nod", facing="left",
                                         expression="sad")],
             lines=[line("co_lan", "Em biết.", 0.4, 1.2)]),
        Shot(id="t06", location="insert:bao_cu", camera="static", duration=3.0,
             lines=[line("narrator", "Sáng hôm sau, báo đăng tin tiệm bánh bao cháy rụi.", 0.3, 2.5)],
             overlays=[Overlay(kind="chapter_card", title="Chương 2", subtitle="Vị khách không có bóng")]),
        Shot(id="t07", location="khong_ton_tai", framing="medium", duration=2.5,
             characters=[CharacterInShot(id="nhan_vat_ma", slot="center")],
             lines=[line("narrator", "Địa điểm và nhân vật thiếu tài sản không được làm sập engine.", 0.2, 2.0)]),
    ]
    return Storyboard(title="Tiệm bánh bao nửa đêm", characters=chars, locations=locs, shots=shots)


def write_tone(path: Path, seconds: float, sr: int = 48000) -> Path:
    t = np.arange(int(seconds * sr)) / sr
    y = (0.15 * np.sin(2 * math.pi * 220 * t) * (0.5 + 0.5 * np.sin(2 * math.pi * 0.5 * t))).astype(np.float32)
    data = (np.stack([y, y], 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())
    return path


def probe_duration(p: Path) -> float:
    exe = shutil.which("ffprobe")
    if not exe:
        return -1.0
    r = subprocess.run([exe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(p)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return -1.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="chỉ xuất ảnh tĩnh, không render video")
    ap.add_argument("--no-film", action="store_true")
    ap.add_argument("--shots", nargs="*")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    from storytoon.render.compositor import ShotRenderer, render_shot
    from storytoon.render.film import render_film
    from storytoon.render.skutil import save_png

    sb = build_storyboard()
    frames_dir = OUT / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    proj = OUT / "project"
    ok = True
    for sh in sb.shots:
        if a.shots and sh.id not in a.shots:
            continue
        if a.quick:
            r = ShotRenderer(sh, sb, proj)
            for frac in (0.15, 0.6):
                i = int(r.n * frac)
                r.frame(i)
                save_png(r.target.rgb(), frames_dir / f"{sh.id}_{i:03d}.png")
            t = time.perf_counter()
            for i in range(30):
                r.frame(i)
            print(f"{sh.id}: {30 / (time.perf_counter() - t):.1f} fps (chỉ vẽ, không mã hoá)")
            continue
        n = round(sh.duration * 30)
        stills = {int(n * f): frames_dir / f"{sh.id}_{int(n * f):03d}.png" for f in (0.15, 0.6)}
        t = time.perf_counter()
        out = render_shot(sh, sb, proj, OUT / f"{sh.id}.mp4", stills=stills)
        dt = time.perf_counter() - t
        d = probe_duration(out)
        print(f"{sh.id}: {n} frame / {dt:.2f}s = {n / dt:.1f} fps (gồm chuẩn bị + mã hoá), video {d:.2f}s")
        ok &= out.exists() and abs(d - n / 30) < 0.1 if d > 0 else out.exists()
    if not a.quick and not a.no_film and not a.shots:
        total = sum(s.duration or 0 for s in sb.shots)
        wav = write_tone(OUT / "tone.wav", total)
        t = time.perf_counter()
        film = render_film(sb, proj, OUT / "film.mp4", soundtrack=wav, workers=3, force=True)
        dt = time.perf_counter() - t
        d = probe_duration(film)
        print(f"film: {dt:.1f}s cho {total:.1f}s video ({total * 30 / dt:.1f} fps tổng), thời lượng {d:.2f}s")
        t = time.perf_counter()
        render_film(sb, proj, OUT / "film.mp4", soundtrack=wav)
        print(f"film (chạy lại, cache shot): {time.perf_counter() - t:.1f}s")
        ok &= abs(d - total) < 0.15
    print("OK" if ok else "LỖI")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
