"""Tìm các công cụ ngoài (ffmpeg, ffprobe) — dùng chung cho mọi module.

Thứ tự: runtime/ffmpeg/<tên>.exe (bản portable) -> runtime/ffmpeg/bin/<tên>.exe -> PATH.
Chỉ dùng stdlib để import nhẹ (kể cả trong tiến trình con render).
"""
from __future__ import annotations

import os
import shutil
from functools import lru_cache
from pathlib import Path

from .paths import RUNTIME

FFMPEG_DIR = RUNTIME / "ffmpeg"


def _bundled_dirs() -> list[Path]:
    return [FFMPEG_DIR, FFMPEG_DIR / "bin"]


@lru_cache(maxsize=None)
def find_tool(name: str) -> str | None:
    """Đường dẫn tới <name>.exe: ưu tiên runtime/ffmpeg, không có thì tìm trong PATH. None nếu không thấy."""
    for d in _bundled_dirs():
        for cand in (d / f"{name}.exe", d / name):
            if cand.is_file():
                return str(cand)
    return shutil.which(name)


def _require(name: str) -> str:
    exe = find_tool(name)
    if not exe:
        raise RuntimeError(f"Không tìm thấy {name}: đặt {name}.exe vào runtime\\ffmpeg\\ hoặc thêm vào PATH")
    return exe


def ffmpeg_exe() -> str:
    return _require("ffmpeg")


def ffprobe_exe() -> str:
    return _require("ffprobe")


def add_bundled_to_path() -> None:
    """Thêm runtime/ffmpeg vào đầu PATH của tiến trình (cho thư viện bên thứ ba tự gọi `ffmpeg`)."""
    for d in _bundled_dirs():
        if (d / "ffmpeg.exe").is_file():
            cur = os.environ.get("PATH", "")
            parts = [p for p in cur.split(os.pathsep) if p]
            if str(d) not in parts:
                os.environ["PATH"] = os.pathsep.join([str(d), *parts])
            return
