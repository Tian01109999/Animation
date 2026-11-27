"""Hậu kỳ: chỉnh màu theo thời điểm (ngày/đêm/hoàng hôn/trong nhà), vignette, film grain.

Để đạt tốc độ, chỉnh màu KHÔNG làm thành một lượt xử lý toàn khung: ma trận màu được "nướng" sẵn vào ảnh nền
của shot (1 lần) và gắn vào Paint khi vẽ nhân vật. Vignette và grain là ảnh dựng sẵn, mỗi frame chỉ vẽ chồng 1 lần.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import skia

# Ma trận màu 4x5 (hàng R,G,B,A; cột R,G,B,A,bias 0..1)
_GRADES: dict[str, tuple[float, float, float, float, float, float]] = {
    # name: (gain_r, gain_g, gain_b, saturation, contrast, lift)
    "day": (1.04, 1.00, 0.94, 0.95, 1.06, 0.0),
    "dusk": (1.08, 0.96, 0.86, 0.95, 1.06, 0.0),
    "indoor": (1.05, 0.99, 0.90, 0.92, 1.05, 0.0),
    "night": (0.86, 0.92, 1.06, 0.86, 1.08, -0.01),
    "neutral": (1.0, 1.0, 1.0, 1.0, 1.0, 0.0),
}

# Nhân vật ban đêm: tối hơn nền một chút để không "nổi" như dán (nền đêm đã tự vẽ tối)
_CHAR_EXTRA = {"night": 0.86, "dusk": 0.95, "indoor": 0.97, "day": 1.0, "neutral": 1.0}


def grade_matrix(time_of_day: str, extra_gain: float = 1.0) -> list[float]:
    gr, gg, gb, sat, con, lift = _GRADES.get(time_of_day, _GRADES["neutral"])
    # bão hoà (luma Rec.709)
    lr, lg, lb = 0.2126, 0.7152, 0.0722
    s = sat
    S = np.array([[lr * (1 - s) + s, lg * (1 - s), lb * (1 - s)],
                  [lr * (1 - s), lg * (1 - s) + s, lb * (1 - s)],
                  [lr * (1 - s), lg * (1 - s), lb * (1 - s) + s]])
    G = np.diag([gr, gg, gb]) * extra_gain
    M = con * (G @ S)
    bias = (1 - con) * 0.5 + lift
    rows = []
    for i in range(3):
        rows += [float(M[i, 0]), float(M[i, 1]), float(M[i, 2]), 0.0, float(bias)]
    rows += [0.0, 0.0, 0.0, 1.0, 0.0]
    return rows


@lru_cache(maxsize=16)
def grade_filter(time_of_day: str, for_character: bool = False) -> skia.ColorFilter:
    extra = _CHAR_EXTRA.get(time_of_day, 1.0) if for_character else 1.0
    return skia.ColorFilters.Matrix(grade_matrix(time_of_day, extra))


def graded_paint(time_of_day: str, for_character: bool = False, alpha: float = 1.0) -> skia.Paint:
    p = skia.Paint(AntiAlias=True, ColorFilter=grade_filter(time_of_day, for_character))
    if alpha < 1.0:
        p.setAlphaf(alpha)
    return p


@lru_cache(maxsize=8)
def vignette_image(W: int, H: int, strength: float = 0.78, night: bool = False) -> skia.Image:
    """Vignette mạnh kiểu phim: tâm trong suốt, góc tối gần đen."""
    s = skia.Surface(W, H)
    c = s.getCanvas()
    c.clear(skia.ColorTRANSPARENT)
    r = (W * W + H * H) ** 0.5 / 2
    a = min(1.0, strength + (0.08 if night else 0.0))
    cols = [skia.ColorSetARGB(0, 0, 0, 0), skia.ColorSetARGB(int(a * 0.25 * 255), 0, 0, 0),
            skia.ColorSetARGB(int(a * 0.70 * 255), 0, 0, 0), skia.ColorSetARGB(int(a * 255), 0, 0, 0)]
    sh = skia.GradientShader.MakeRadial(skia.Point(W / 2, H * 0.47), r, cols, [0.0, 0.45, 0.78, 1.0],
                                        skia.TileMode.kClamp, 0,
                                        skia.Matrix.Scale(1.0, 1.0))
    # ellipse: nén theo chiều dọc để vignette ôm khung 16:9
    m = skia.Matrix()
    m.setScale(1.0, H / W * 1.25, W / 2, H * 0.47)
    sh = sh.makeWithLocalMatrix(m)
    c.drawPaint(skia.Paint(Shader=sh))
    return s.makeImageSnapshot()


@lru_cache(maxsize=4)
def grain_frames(W: int, H: int, n: int = 6, seed: int = 7) -> tuple[skia.Image, ...]:
    """Các khung nhiễu xám (độ phân giải 1/2) để vẽ chồng chế độ overlay, xoay vòng theo frame."""
    rng = np.random.default_rng(seed)
    w, h = max(2, W // 2), max(2, H // 2)
    out = []
    for _ in range(n):
        g = np.clip(rng.normal(128, 38, (h, w)), 0, 255).astype(np.uint8)
        arr = np.empty((h, w, 4), np.uint8)
        arr[..., 0] = g
        arr[..., 1] = g
        arr[..., 2] = g
        arr[..., 3] = 255
        out.append(skia.Image.fromarray(arr, colorType=skia.kRGBA_8888_ColorType))
    return tuple(out)


def cctv_matrix(desaturate: float = 0.9, tint: str = "#9aa8a4", tint_amount: float = 0.25,
                contrast: float = 1.08, lift: float = 0.03) -> list[float]:
    """Ma trận màu 4x5 kiểu camera an ninh: khử bão hoà + ám teal + nâng đen nhẹ (STYLE_GUIDE §6 'cctv')."""
    lr, lg, lb = 0.2126, 0.7152, 0.0722
    s = 1.0 - desaturate
    S = np.array([[lr * (1 - s) + s, lg * (1 - s), lb * (1 - s)],
                  [lr * (1 - s), lg * (1 - s) + s, lb * (1 - s)],
                  [lr * (1 - s), lg * (1 - s), lb * (1 - s) + s]])
    h = tint.lstrip("#")
    tc = np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])
    tc = tc / max(1e-6, float(tc @ np.array([lr, lg, lb])))        # giữ độ sáng
    T = np.diag(1 - tint_amount + tint_amount * tc)
    M = contrast * (T @ S)
    bias = (1 - contrast) * 0.5 + lift
    rows: list[float] = []
    for i in range(3):
        rows += [float(M[i, 0]), float(M[i, 1]), float(M[i, 2]), 0.0, float(bias)]
    rows += [0.0, 0.0, 0.0, 1.0, 0.0]
    return rows


def concat_matrix(a: list[float], b: list[float]) -> list[float]:
    """Ma trận màu tương đương áp a rồi b."""
    A = np.array(a, dtype=float).reshape(4, 5)
    B = np.array(b, dtype=float).reshape(4, 5)
    A4 = np.vstack([A, [0, 0, 0, 0, 1]])
    B4 = np.vstack([B, [0, 0, 0, 0, 1]])
    return [float(v) for v in (B4 @ A4)[:4].reshape(-1)]


@lru_cache(maxsize=4)
def scanlines_image(W: int, H: int, line_px: float = 2.0, alpha: float = 0.08) -> skia.Image:
    """Ô lặp scanline ngang (dùng với shader kRepeat): 1 dòng tối mỗi 2*line_px px (theo khung 1080p)."""
    period = max(2, int(round(line_px * 2 * H / 1080)))
    dark = max(1, period // 2)
    arr = np.zeros((period, 4, 4), np.uint8)
    arr[:dark, :, 3] = int(alpha * 255)
    return skia.Image.fromarray(arr, colorType=skia.kRGBA_8888_ColorType, alphaType=skia.kUnpremul_AlphaType)


class PostFX:
    """Vẽ vignette + grain lên khung đã có nền + nhân vật (+ overlay)."""

    def __init__(self, W: int, H: int, time_of_day: str = "day", grain: float = 0.10,
                 vignette: float = 0.78) -> None:
        self.W, self.H = W, H
        self.vig = vignette_image(W, H, vignette, time_of_day == "night") if vignette > 0 else None
        self.grain = grain_frames(W, H) if grain > 0 else ()
        self.grain_paint = skia.Paint(BlendMode=skia.BlendMode.kOverlay, Alphaf=grain)
        self.rect = skia.Rect.MakeWH(W, H)
        self.samp = skia.SamplingOptions(skia.FilterMode.kLinear)

    def vignette(self, c: skia.Canvas) -> None:
        if self.vig is not None:
            c.drawImage(self.vig, 0, 0)

    def film_grain(self, c: skia.Canvas, frame: int) -> None:
        if self.grain:
            img = self.grain[(frame // 2) % len(self.grain)]  # nhiễu đổi mỗi 2 frame (giống phim 12-15 fps)
            c.drawImageRect(img, self.rect, self.samp, self.grain_paint)
