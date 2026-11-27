"""Thời lượng shot và thời điểm từng line (khi bước audio chưa điền thì ước lượng theo số chữ)."""
from __future__ import annotations

from dataclasses import dataclass

from ..schema import Line, Shot

LEAD_IN = 0.25     # giây im lặng đầu shot nếu line không có start
GAP = 0.15         # khoảng nghỉ giữa các line ước lượng
TAIL = 0.4


def estimate_line_duration(text: str) -> float:
    words = max(1, len((text or "").split()))
    return round(0.32 * words + 0.35, 2)


@dataclass
class TimedLine:
    line: Line
    start: float
    duration: float

    @property
    def end(self) -> float:
        return self.start + self.duration


def timed_lines(shot: Shot) -> list[TimedLine]:
    out: list[TimedLine] = []
    cur = LEAD_IN
    for ln in shot.lines:
        dur = ln.duration if ln.duration and ln.duration > 0 else estimate_line_duration(ln.text)
        st = ln.start if ln.start is not None else cur
        out.append(TimedLine(ln, float(st), float(dur)))
        cur = st + dur + GAP
    return out


def shot_duration(shot: Shot) -> float:
    if shot.duration and shot.duration > 0:
        return float(shot.duration)
    tl = timed_lines(shot)
    end = max((t.end for t in tl), default=0.0)
    return max(float(shot.min_duration), end + TAIL)
