"""Tiện ích skia dùng chung: màu, paint, đọc/ghi ảnh, font (an toàn với đường dẫn Unicode)."""
from __future__ import annotations

import logging
import unicodedata
from functools import lru_cache
from pathlib import Path

import numpy as np
import skia

from ..paths import FONTS

log = logging.getLogger("storytoon.render")

SAMPLING = skia.SamplingOptions(skia.FilterMode.kLinear, skia.MipmapMode.kLinear)
SAMPLING_FAST = skia.SamplingOptions(skia.FilterMode.kLinear, skia.MipmapMode.kNone)


# ---------------------------------------------------------------- màu
def hex2rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def color(h: str | tuple, a: float = 1.0) -> int:
    if isinstance(h, str):
        r, g, b = hex2rgb(h)
    else:
        r, g, b = h[:3]
    return skia.ColorSetARGB(int(max(0, min(1, a)) * 255), int(r), int(g), int(b))


def mix(c1: str, c2: str, t: float) -> str:
    a, b = hex2rgb(c1), hex2rgb(c2)
    return "#%02x%02x%02x" % tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def shade(c: str, k: float) -> str:
    """k<0: tối đi, k>0: sáng lên (0..1)."""
    return mix(c, "#000000", -k) if k < 0 else mix(c, "#ffffff", k)


def fill(c: str | tuple, a: float = 1.0, **kw) -> skia.Paint:
    return skia.Paint(AntiAlias=True, Color=color(c, a), **kw)


def stroke(c: str | tuple, w: float, a: float = 1.0, **kw) -> skia.Paint:
    return skia.Paint(AntiAlias=True, Color=color(c, a), Style=skia.Paint.kStroke_Style, StrokeWidth=w,
                      StrokeCap=skia.Paint.kRound_Cap, StrokeJoin=skia.Paint.kRound_Join, **kw)


# ---------------------------------------------------------------- path helpers
def union(*paths: skia.Path) -> skia.Path:
    out = skia.Path(paths[0])
    for p in paths[1:]:
        out = skia.Op(out, p, skia.PathOp.kUnion_PathOp)
    return out


def diff(a: skia.Path, b: skia.Path) -> skia.Path:
    return skia.Op(a, b, skia.PathOp.kDifference_PathOp)


def inter(a: skia.Path, b: skia.Path) -> skia.Path:
    return skia.Op(a, b, skia.PathOp.kIntersect_PathOp)


def offset(p: skia.Path, dx: float, dy: float) -> skia.Path:
    q = skia.Path(p)
    q.offset(dx, dy)
    return q


def scaled(p: skia.Path, s: float, cx: float, cy: float, sy: float | None = None) -> skia.Path:
    q = skia.Path(p)
    m = skia.Matrix.Concat(skia.Matrix.Translate(cx, cy),
                           skia.Matrix.Concat(skia.Matrix.Scale(s, s if sy is None else sy), skia.Matrix.Translate(-cx, -cy)))
    q.transform(m)
    return q


def poly(pts, close: bool = True) -> skia.Path:
    p = skia.Path()
    p.moveTo(*pts[0])
    for pt in pts[1:]:
        p.lineTo(*pt)
    if close:
        p.close()
    return p


def smooth(pts, close: bool = True, tension: float = 0.5) -> skia.Path:
    """Đường cong Catmull-Rom qua các điểm -> cubic Bezier."""
    n = len(pts)
    p = skia.Path()
    p.moveTo(*pts[0])
    rng = range(n) if close else range(n - 1)
    for i in rng:
        p0 = pts[(i - 1) % n] if (close or i > 0) else pts[i]
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        p3 = pts[(i + 2) % n] if (close or i + 2 < n) else p2
        t = tension / 3 * 2
        c1 = (p1[0] + (p2[0] - p0[0]) * t / 2, p1[1] + (p2[1] - p0[1]) * t / 2)
        c2 = (p2[0] - (p3[0] - p1[0]) * t / 2, p2[1] - (p3[1] - p1[1]) * t / 2)
        p.cubicTo(*c1, *c2, *p2)
    if close:
        p.close()
    return p


def circle(x: float, y: float, r: float) -> skia.Path:
    p = skia.Path()
    p.addCircle(x, y, r)
    return p


def oval(x: float, y: float, rx: float, ry: float) -> skia.Path:
    p = skia.Path()
    p.addOval(skia.Rect.MakeLTRB(x - rx, y - ry, x + rx, y + ry))
    return p


def rrect(l: float, t: float, r: float, b: float, rad: float) -> skia.Path:
    p = skia.Path()
    p.addRRect(skia.RRect.MakeRectXY(skia.Rect.MakeLTRB(l, t, r, b), rad, rad))
    return p


def capsule(x1: float, y1: float, x2: float, y2: float, w1: float, w2: float) -> skia.Path:
    """Đoạn chi thuôn với 2 đầu tròn (dùng cho tay/chân để khớp không hở khi xoay)."""
    import math
    dx, dy = x2 - x1, y2 - y1
    ln = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / ln, dx / ln
    body = poly([(x1 + nx * w1 / 2, y1 + ny * w1 / 2), (x2 + nx * w2 / 2, y2 + ny * w2 / 2),
                 (x2 - nx * w2 / 2, y2 - ny * w2 / 2), (x1 - nx * w1 / 2, y1 - ny * w1 / 2)])
    return union(body, circle(x1, y1, w1 / 2), circle(x2, y2, w2 / 2))


# ---------------------------------------------------------------- ảnh
def load_image(path: Path) -> skia.Image | None:
    try:
        data = Path(path).read_bytes()
        img = skia.Image.MakeFromEncoded(skia.Data.MakeWithCopy(data))
        if img is None:
            log.warning("Không đọc được ảnh: %s", path)
            return None
        return img.makeRasterImage()
    except OSError as e:
        log.warning("Không mở được ảnh %s: %s", path, e)
        return None


def save_png(img: skia.Image | np.ndarray, path: Path) -> None:
    """Ghi PNG (RGBA unpremul) — qua PIL để an toàn với đường dẫn Unicode."""
    from PIL import Image as PILImage
    arr = img if isinstance(img, np.ndarray) else to_rgba(img)
    path.parent.mkdir(parents=True, exist_ok=True)
    PILImage.fromarray(arr, "RGBA" if arr.shape[2] == 4 else "RGB").save(path, optimize=False, compress_level=4)


def to_rgba(img: skia.Image) -> np.ndarray:
    return img.toarray(colorType=skia.kRGBA_8888_ColorType, alphaType=skia.kUnpremul_AlphaType)


def from_rgba(arr: np.ndarray) -> skia.Image:
    return skia.Image.fromarray(np.ascontiguousarray(arr), colorType=skia.kRGBA_8888_ColorType,
                                alphaType=skia.kUnpremul_AlphaType)


# ---------------------------------------------------------------- font
_FONT_FILES = {
    "regular": ["BeVietnamPro-Regular.ttf"],
    "semibold": ["BeVietnamPro-SemiBold.ttf", "BeVietnamPro-Bold.ttf"],
    "bold": ["BeVietnamPro-Bold.ttf"],
    "extrabold": ["BeVietnamPro-ExtraBold.ttf", "BeVietnamPro-Bold.ttf"],
}
_WIN_FALLBACK = {
    "regular": ["segoeui.ttf", "arial.ttf"],
    "semibold": ["seguisb.ttf", "segoeuib.ttf", "arialbd.ttf"],
    "bold": ["segoeuib.ttf", "arialbd.ttf"],
    "extrabold": ["seguibl.ttf", "segoeuib.ttf", "arialbd.ttf"],
}


@lru_cache(maxsize=16)
def typeface(weight: str = "bold") -> skia.Typeface:
    cands = [FONTS / f for f in _FONT_FILES.get(weight, _FONT_FILES["bold"])]
    cands += [Path("C:/Windows/Fonts") / f for f in _WIN_FALLBACK.get(weight, _WIN_FALLBACK["bold"])]
    for c in cands:
        if c.exists():
            tf = skia.Typeface.MakeFromData(skia.Data.MakeWithCopy(c.read_bytes()))
            if tf is not None:
                return tf
    log.warning("Không tìm thấy font %s — dùng font mặc định", weight)
    return skia.Typeface.MakeDefault()


def font(size: float, weight: str = "bold") -> skia.Font:
    f = skia.Font(typeface(weight), size)
    f.setEdging(skia.Font.Edging.kAntiAlias)
    f.setSubpixel(True)
    return f


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s or "")


def wrap_text(text: str, f: skia.Font, max_w: float, max_lines: int | None = None) -> list[str]:
    words = nfc(text).split()
    lines: list[str] = []
    cur = ""
    for w in words:
        t = (cur + " " + w).strip()
        if f.measureText(t) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if max_lines and len(lines) > max_lines:
        # gộp phần dư vào dòng cuối (người gọi nên tách đoạn trước)
        lines = lines[:max_lines - 1] + [" ".join(lines[max_lines - 1:])]
    return lines


def balanced_wrap(text: str, f: skia.Font, max_w: float) -> list[str]:
    """Ngắt tối đa 2 dòng, cân độ dài 2 dòng (đẹp hơn cho phụ đề)."""
    words = nfc(text).split()
    if not words:
        return []
    if f.measureText(" ".join(words)) <= max_w:
        return [" ".join(words)]
    best, best_score = None, 1e18
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        wa, wb = f.measureText(a), f.measureText(b)
        over = max(0.0, wa - max_w) + max(0.0, wb - max_w)
        score = over * 1000 + abs(wa - wb)
        if score < best_score:
            best, best_score = [a, b], score
    return best or [" ".join(words)]
