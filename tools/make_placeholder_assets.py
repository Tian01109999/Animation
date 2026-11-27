"""Tạo tài sản mẫu (placeholder) cho StoryToon: nhân vật puppet, địa điểm, ảnh chèn, font, động tác.

Chạy:  runtime\\venv\\Scripts\\python.exe tools\\make_placeholder_assets.py [--chars] [--locs] [--fonts] [--actions] [--inserts]
(không có cờ = làm tất cả)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storytoon.paths import ACTIONS, FONTS, INSERTS  # noqa: E402

FONT_BASE = "https://raw.githubusercontent.com/google/fonts/main/ofl/bevietnampro/"
FONT_FILES = ["BeVietnamPro-Regular.ttf", "BeVietnamPro-SemiBold.ttf", "BeVietnamPro-Bold.ttf",
              "BeVietnamPro-ExtraBold.ttf"]


def get_fonts() -> None:
    FONTS.mkdir(parents=True, exist_ok=True)
    for name in FONT_FILES:
        dst = FONTS / name
        if dst.exists() and dst.stat().st_size > 10_000:
            print(f"  font có sẵn: {name}")
            continue
        try:
            req = urllib.request.Request(FONT_BASE + name, headers={"User-Agent": "storytoon-asset-tool"})
            data = urllib.request.urlopen(req, timeout=30).read()
            if data[:4] not in (b"\x00\x01\x00\x00", b"true", b"OTTO"):
                raise ValueError("không phải file TTF")
            dst.write_bytes(data)
            print(f"  đã tải font: {name} ({len(data) // 1024} KB)")
        except Exception as e:  # noqa: BLE001 — mạng có thể lỗi bất kỳ kiểu gì
            print(f"  KHÔNG tải được {name}: {e} — engine sẽ dùng Segoe UI / Arial của Windows")


# ------------------------------------------------------------------ động tác (khớp SPEC; góc độ, dịch px)
def _k(*pairs: float) -> list[list[float]]:
    return [[pairs[i], pairs[i + 1]] for i in range(0, len(pairs), 2)]


ARMS_REST = {"arm_l_up": _k(0, 4), "arm_r_up": _k(0, -4), "arm_l_low": _k(0, -6), "arm_r_low": _k(0, 6)}

ACTION_DEFS: dict[str, dict] = {
    "idle": {"loop": True, "duration": 4.0, "tracks": {
        "arm_l_up": _k(0, 4, 2, 6, 4, 4), "arm_r_up": _k(0, -4, 2, -6, 4, -4),
        "arm_l_low": _k(0, -6, 2, -8, 4, -6), "arm_r_low": _k(0, 6, 2, 8, 4, 6),
        "head": _k(0, 0, 1.5, 1.5, 3, -1, 4, 0), "torso": _k(0, 0, 2, 0.6, 4, 0)}},
    "talk": {"loop": True, "duration": 2.4, "tracks": {
        "head": _k(0, 0, 0.6, 2.5, 1.2, -1.5, 1.8, 2, 2.4, 0), "head.y": _k(0, 0, 0.6, 2, 1.2, 0, 1.8, 2, 2.4, 0),
        "torso": _k(0, 0, 1.2, 1.5, 2.4, 0),
        "arm_r_up": _k(0, -6, 0.8, -24, 1.6, -16, 2.4, -6), "arm_r_low": _k(0, 6, 0.8, -48, 1.6, -30, 2.4, 6),
        "hand_r": _k(0, 0, 0.8, -15, 1.6, -5, 2.4, 0),
        "arm_l_up": _k(0, 4, 1.2, 7, 2.4, 4), "arm_l_low": _k(0, -6, 1.2, -14, 2.4, -6)}},
    "walk": {"loop": True, "duration": 1.0, "move": {"x_per_s": 170}, "tracks": {
        "leg_l_up": _k(0, 14, 0.5, -14, 1, 14), "leg_r_up": _k(0, -14, 0.5, 14, 1, -14),
        "leg_l_low": _k(0, 4, 0.25, 26, 0.5, 2, 1, 4), "leg_r_low": _k(0, 2, 0.5, 4, 0.75, 26, 1, 2),
        "root.y": _k(0, 0, 0.25, -9, 0.5, 0, 0.75, -9, 1, 0),
        "arm_l_up": _k(0, -12, 0.5, 12, 1, -12), "arm_r_up": _k(0, 12, 0.5, -12, 1, 12),
        "arm_l_low": _k(0, -14, 0.5, -4, 1, -14), "arm_r_low": _k(0, 4, 0.5, 14, 1, 4),
        "torso": _k(0, 2), "head": _k(0, 0, 0.25, 1, 0.5, 0, 0.75, 1, 1, 0)}},
    "sit": {"loop": True, "duration": 4.0, "sit": True, "tracks": {
        # đùi xoay ngang về phía mặt, ống chân thẳng đứng; hông tự hạ (Animator.sit_drop) để chân chạm sàn
        "leg_l_up": _k(0, -82), "leg_r_up": _k(0, -82), "leg_l_low": _k(0, 82), "leg_r_low": _k(0, 82),
        "leg_r_up.x": _k(0, -14), "leg_l_up.x": _k(0, 8),
        "arm_l_up": _k(0, -16, 2, -14, 4, -16), "arm_l_low": _k(0, -48, 2, -45, 4, -48),
        "arm_r_up": _k(0, -12, 2, -10, 4, -12), "arm_r_low": _k(0, -44, 2, -42, 4, -44),
        "torso": _k(0, 3, 2, 4, 4, 3), "head": _k(0, -2, 2, -0.5, 4, -2)}},
    "point": {"loop": False, "duration": 1.0, "slots": {"hand_r": "point"}, "tracks": {
        "arm_r_up": _k(0, -6, 0.45, -88, 1.0, -84), "arm_r_low": _k(0, 6, 0.45, -6, 1.0, -4),
        "hand_r": _k(0, 0, 0.45, -4, 1.0, 0), "torso": _k(0, 0, 0.45, 3, 1.0, 2.5),
        "head": _k(0, 0, 0.45, -3, 1.0, -2), "arm_l_up": _k(0, 4, 1, 5), "arm_l_low": _k(0, -6, 1, -10)}},
    "nod": {"loop": True, "duration": 1.3, "tracks": {
        "head": _k(0, 0, 0.3, 7, 0.6, 0, 0.95, 5, 1.3, 0), "head.y": _k(0, 0, 0.3, 4, 0.6, 0, 0.95, 3, 1.3, 0),
        **ARMS_REST}},
    "shake_head": {"loop": True, "duration": 1.0, "tracks": {
        "head": _k(0, 0, 0.25, -5, 0.5, 0, 0.75, 5, 1, 0), "head.x": _k(0, 0, 0.25, -7, 0.5, 0, 0.75, 7, 1, 0),
        **ARMS_REST}},
    "scared": {"loop": True, "duration": 0.4, "default_expression": "scared", "slots": {"hand_l": "open"}, "tracks": {
        "arm_l_up": _k(0, -28), "arm_l_low": _k(0, -105), "arm_r_up": _k(0, -38), "arm_r_low": _k(0, -92),
        "hand_l": _k(0, -10), "hand_r": _k(0, -12), "torso": _k(0, -5), "head": _k(0, -4, 0.2, -3, 0.4, -4),
        "root.y": _k(0, 6), "root.x": _k(0, 0, 0.1, 2.5, 0.2, 0, 0.3, -2.5, 0.4, 0),
        "leg_l_up": _k(0, 4), "leg_r_up": _k(0, -4)}},
}


def write_actions() -> None:
    ACTIONS.mkdir(parents=True, exist_ok=True)
    for name, d in ACTION_DEFS.items():
        data = {"name": name, **d}
        (ACTIONS / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  {len(ACTION_DEFS)} động tác -> {ACTIONS}")


def make_chars(ids: list[str] | None = None) -> None:
    from storytoon.render.puppetgen import PRESETS, make_character
    for cid in ids or list(PRESETS):
        t = time.perf_counter()
        make_character(cid, PRESETS[cid])
        print(f"  nhân vật {cid}: {time.perf_counter() - t:.1f}s")


def make_locs(ids: list[str] | None = None) -> None:
    from storytoon.render.locgen import LOCATION_BUILDERS, make_location
    for lid in ids or list(LOCATION_BUILDERS):
        t = time.perf_counter()
        make_location(lid)
        print(f"  địa điểm {lid}: {time.perf_counter() - t:.1f}s")


def make_inserts() -> None:
    # Chữ trong ảnh phải là tiếng Anh -> dùng insertgen (kind 'newspaper'), không dùng placeholder chữ Việt.
    from storytoon.render.insertgen import make_insert
    p = make_insert("bao_cu", "newspaper", None, INSERTS)
    print(f"  ảnh chèn: {p}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Tạo tài sản mẫu cho StoryToon")
    for flag in ("chars", "locs", "fonts", "actions", "inserts"):
        ap.add_argument(f"--{flag}", action="store_true")
    ap.add_argument("--only", nargs="*", help="chỉ tạo các id này (nhân vật/địa điểm)")
    a = ap.parse_args()
    everything = not any((a.chars, a.locs, a.fonts, a.actions, a.inserts))
    if everything or a.fonts:
        print("Font:")
        get_fonts()
    if everything or a.actions:
        print("Động tác:")
        write_actions()
    if everything or a.chars:
        print("Nhân vật:")
        make_chars(a.only)
    if everything or a.locs:
        print("Địa điểm:")
        make_locs(a.only)
    if everything or a.inserts:
        print("Ảnh chèn:")
        make_inserts()


if __name__ == "__main__":
    main()
