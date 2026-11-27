"""Camera: vùng cắt trên nền theo framing + chuyển động có easing trong suốt shot."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .actions import ease

FRAMING_W = {"wide": 1.0, "medium": 0.55, "close": 0.30, "extreme_close": 0.20}


@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    def scaled(self, s: float, ax: float | None = None, ay: float | None = None) -> "Rect":
        ax = self.cx if ax is None else ax
        ay = self.cy if ay is None else ay
        return Rect(ax + (self.x - ax) * s, ay + (self.y - ay) * s, self.w * s, self.h * s)

    def moved(self, dx: float, dy: float) -> "Rect":
        return Rect(self.x + dx, self.y + dy, self.w, self.h)

    def lerp(self, o: "Rect", u: float) -> "Rect":
        return Rect(self.x + (o.x - self.x) * u, self.y + (o.y - self.y) * u, self.w + (o.w - self.w) * u,
                    self.h + (o.h - self.h) * u)


@dataclass
class Subject:
    """Nhân vật trong toạ độ nền: điểm chân, tâm đầu, đỉnh đầu, chiều cao."""
    id: str
    foot_x: float
    foot_y: float
    head_x: float
    head_y: float
    top_y: float
    height: float
    facing: int  # +1 phải, -1 trái


def clamp_rect(r: Rect, bw: float, bh: float) -> Rect:
    w, h = min(r.w, bw), min(r.h, bh)
    x = min(max(r.x, 0.0), bw - w)
    y = min(max(r.y, 0.0), bh - h)
    return Rect(x, y, w, h)


def base_rect(framing: str, bw: float, bh: float, aspect: float, subjects: list[Subject],
              focus: Subject | None, focus_x_frac: float | None = None) -> Rect:
    """Vùng cắt ban đầu. `focus_x_frac` (0..1): đặt đầu nhân vật focus tại vị trí ngang này của khung
    (vd 0.64 cho cảnh qua vai: tiền cảnh sau lưng bên trái, người đối diện lệch phải)."""
    frac = FRAMING_W.get(framing, 0.55)
    w = bw * frac
    h = w / aspect
    if h > bh:
        h = bh
        w = h * aspect
    if framing == "wide" or not subjects:
        return clamp_rect(Rect((bw - w) / 2, (bh - h) / 2 if framing != "wide" else bh - h, w, h), bw, bh)
    if framing == "medium":
        group = [focus] if focus else subjects
        xs = [s.head_x for s in group]
        cx = (min(xs) + max(xs)) / 2
        if focus and len(subjects) > 1:
            cx = focus.head_x * 0.75 + (sum(s.head_x for s in subjects) / len(subjects)) * 0.25
        if focus and focus_x_frac is not None:
            cx = focus.head_x + (0.5 - focus_x_frac) * w
        top = min(s.top_y for s in group) - 0.12 * h
        return clamp_rect(Rect(cx - w / 2, top, w, h), bw, bh)
    s = focus or subjects[0]
    look = 0.07 * w * s.facing
    if focus_x_frac is not None:
        look = (0.5 - focus_x_frac) * w
    cy_frac = 0.42 if framing == "close" else 0.47
    return clamp_rect(Rect(s.head_x + look - w / 2, s.head_y - h * cy_frac, w, h), bw, bh)


def camera_at(move: str, base: Rect, t: float, duration: float, bw: float, bh: float, seed: int,
              anchor: tuple[float, float] | None = None) -> Rect:
    u = ease(t / duration) if duration > 0 else 0.0
    ax, ay = anchor if anchor else (base.cx, base.cy)
    if move in ("zoom_in", "push_in_slow"):
        k = 0.80 if move == "zoom_in" else 0.90
        if move == "push_in_slow":
            u = t / duration if duration > 0 else 0.0  # đẩy tuyến tính, rất chậm
        r = base.scaled(1.0 + (k - 1.0) * u, ax, ay)
    elif move == "zoom_out":
        r = base.scaled(0.80 + 0.20 * u, ax, ay)
    elif move in ("pan_left", "pan_right"):
        b = base.scaled(0.9) if base.w >= bw * 0.95 else base
        d = 0.06 * bw
        sgn = -1 if move == "pan_left" else 1
        r = b.moved(sgn * d * (u - 0.5) * 2, 0)
    elif move == "shake":
        b = base.scaled(0.96)
        rng = random.Random(seed)
        ph = [rng.uniform(0, math.tau) for _ in range(4)]
        amp = 0.008 * b.w
        dx = amp * (math.sin(t * 23 + ph[0]) * 0.6 + math.sin(t * 37 + ph[1]) * 0.4)
        dy = amp * (math.sin(t * 29 + ph[2]) * 0.6 + math.sin(t * 41 + ph[3]) * 0.4)
        r = b.moved(dx, dy)
    else:
        r = base
    return clamp_rect(r, bw, bh)
