"""Engine render 2D cutout-puppet (skia) -> mp4 (ffmpeg). Xem docs/render.md."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..schema import Shot, Storyboard


def render_shot(shot: "Shot", sb: "Storyboard", project_dir: Path, out_mp4: Path, *, width: int = 1920,
                height: int = 1080, fps: int = 30, **kw: Any) -> Path:
    from .compositor import render_shot as _rs
    return _rs(shot, sb, project_dir, out_mp4, width=width, height=height, fps=fps, **kw)


def render_film(sb: "Storyboard", project_dir: Path, out_mp4: Path, **kw: Any) -> Path:
    from .film import render_film as _rf
    return _rf(sb, project_dir, out_mp4, **kw)


__all__ = ["render_shot", "render_film"]
