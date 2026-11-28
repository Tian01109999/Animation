"""Lớp đồ hoạ trên khung hình (phụ đề, nametag, thẻ địa điểm/giờ, chapter card, thẻ luật, tờ luật, HUD CCTV,
điện thoại chat/ngân hàng, tờ tìm người, bản đồ, timeline, thẻ giá, tin tuyển dụng, bảng tên trên áo, watermark).

Thiết kế: docs/STYLE_GUIDE.md §9; tham số: assets/catalog/overlays.json (đọc `Overlay.data`, thiếu khoá -> mặc định).

Mỗi lớp được dựng sẵn MỘT lần/shot thành ảnh RGBA ở độ phân giải đầu ra; mỗi frame chỉ vẽ ảnh (alpha fade, trượt,
xoay, phóng) trên GPU. Phần động (giây CCTV chạy, chấm REC nháy, tin nhắn pop, timeline hiện dần, chấm bản đồ nháy,
giấy bay) dùng `Layer.draw_fn` vẽ theo t từ các ảnh con dựng sẵn trong `Layer.images` (được đưa lên GPU cùng lúc).
Kích thước tính theo chiều cao khung hình H nên đúng với mọi độ phân giải.

Bản quyền: mọi chữ/tên/ngân hàng/cửa hàng là hư cấu chung chung; không logo/thương hiệu thật.
"""
from __future__ import annotations

import logging
import math
import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable

import skia

from ..schema import Overlay, Shot, Storyboard
from .skutil import balanced_wrap, circle, color, fill, font, mix, nfc, poly, rrect, shade, stroke, wrap_text
from .timing import TimedLine

log = logging.getLogger("storytoon.render")

# Bảng màu (STYLE_GUIDE §6, §9)
IVORY = "#f4eddf"
GREEN_DOT = "#3cb44b"
RED = "#d0302a"
RED_INK = "#c8352e"
CARD_BG = "#5b1f1a"
CARD_BORDER = "#d9b48a"
GOLD = "#d8ab3a"
YELLOW = "#f3c94e"
PAPER = "#f6efdf"
RULE_LINE = "#a9c4e0"
INK = "#1f2f5a"
HAND_INK = "#1f3f8a"
BRAND_GREEN = "#1f6f5c"
BRAND_CREAM = "#f2ead8"
BRAND_ORANGE = "#e8833a"
SKIN = "#e9b994"

LIN = skia.SamplingOptions(skia.FilterMode.kLinear)
NEAREST = skia.SamplingOptions()


def ease_out(u: float) -> float:
    u = max(0.0, min(1.0, u))
    return 1 - (1 - u) ** 3


def ease_out_back(u: float, k: float = 1.70158) -> float:
    u = max(0.0, min(1.0, u)) - 1
    return 1 + (k + 1) * u ** 3 + k * u ** 2


# ====================================================================== Layer
@dataclass
class Layer:
    image: skia.Image | None
    t0: float
    t1: float
    fade_in: float = 0.3
    fade_out: float = 0.3
    pos: tuple[float, float] = (0.0, 0.0)              # góc trên-trái (px màn hình)
    anchor: Callable[[float], tuple[float, float]] | None = None  # pos động theo thời gian
    kind: str = ""
    scale_in: float = 0.0                               # phóng nhẹ khi xuất hiện (chapter card)
    # --- mở rộng (gói C) ---
    draw_fn: Callable[["Layer", skia.Canvas, float, float], None] | None = None  # (layer, canvas, t, alpha)
    images: dict[str, skia.Image] = field(default_factory=dict)  # ảnh con cho draw_fn (được upload GPU)
    backdrop: str | None = None        # "blur" | "dim": làm mờ/tối khung phía sau khi lớp hiện
    backdrop_dim: float = 0.35
    backdrop_sigma: float = 10.0       # px khung đầu ra
    slide: tuple[float, float] = (0.0, 0.0)   # dịch khi vào (px), về 0 theo ease-out
    rotate: float = 0.0                # độ, quanh tâm ảnh
    blur: float = 0.0                  # σ px: vẽ ảnh mờ (tờ luật "blurred")
    data: dict[str, Any] = field(default_factory=dict)

    def alpha(self, t: float) -> float:
        if t < self.t0 or t > self.t1:
            return 0.0
        a = 1.0
        if self.fade_in > 0:
            a = min(a, (t - self.t0) / self.fade_in)
        if self.fade_out > 0:
            a = min(a, (self.t1 - t) / self.fade_out)
        return max(0.0, min(1.0, a))

    def entering(self, t: float) -> float:
        """0..1 tiến độ vào (chỉ phần fade-in), dùng cho trượt/pop."""
        if self.fade_in <= 0:
            return 1.0
        return max(0.0, min(1.0, (t - self.t0) / self.fade_in))

    def draw(self, c: skia.Canvas, t: float) -> None:
        a = self.alpha(t)
        if a <= 0.003:
            return
        if self.draw_fn is not None:
            self.draw_fn(self, c, t, a)
            return
        if self.image is None:
            return
        x, y = self.anchor(t) if self.anchor else self.pos
        p = skia.Paint(Alphaf=a)
        if self.blur > 0:
            p.setImageFilter(skia.ImageFilters.Blur(self.blur, self.blur, skia.TileMode.kDecal, None))
        u = self.entering(t)
        if self.slide != (0.0, 0.0) and u < 1:
            k = 1 - ease_out(u)
            x += self.slide[0] * k
            y += self.slide[1] * k
        s = 1.0
        if self.scale_in and a < 1 and u < 1:
            s = 1.0 - self.scale_in * (1 - a)
        if s != 1.0 or self.rotate:
            w, h = self.image.width(), self.image.height()
            c.save()
            c.translate(x + w / 2, y + h / 2)
            if self.rotate:
                c.rotate(self.rotate)
            c.scale(s, s)
            c.drawImage(self.image, -w / 2, -h / 2, LIN, p)
            c.restore()
        else:
            c.drawImage(self.image, round(x), round(y), NEAREST, p)


def _surface(w: float, h: float) -> tuple[skia.Surface, skia.Canvas]:
    s = skia.Surface(max(1, int(round(w))), max(1, int(round(h))))
    c = s.getCanvas()
    c.clear(skia.ColorTRANSPARENT)
    return s, c


def _shadow_paint(a: float, blur: float) -> skia.Paint:
    p = fill("#000000", a)
    p.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, max(0.1, blur)))
    return p


def outlined_text(c: skia.Canvas, text: str, x: float, y: float, f: skia.Font, col: str = "#ffffff",
                  outline: str = "#000000", ow: float = 6.0, shadow: float = 0.75) -> None:
    blob = skia.TextBlob.MakeFromString(text, f)
    if blob is None:
        return
    if shadow > 0:
        sp = _shadow_paint(shadow, ow * 1.2)
        sp.setStyle(skia.Paint.kStrokeAndFill_Style)
        sp.setStrokeWidth(ow * 1.6)
        c.drawTextBlob(blob, x + ow * 0.25, y + ow * 0.45, sp)
    if ow > 0:
        op = stroke(outline, ow)
        c.drawTextBlob(blob, x, y, op)
    c.drawTextBlob(blob, x, y, fill(col))


# ---------------------------------------------------------------- text helpers
def hand_font(size: float, weight: str = "semibold") -> skia.Font:
    """Chữ "viết tay": Be Vietnam Pro nghiêng (không có file Italic -> skew)."""
    f = font(size, weight)
    f.setSkewX(-0.16)
    return f


def text(c: skia.Canvas, s: str, x: float, y: float, f: skia.Font, col: str, a: float = 1.0,
         align: str = "l") -> float:
    """Vẽ chữ tại baseline y; align l/c/r. Trả về bề rộng."""
    s = nfc(s)
    w = f.measureText(s)
    if align == "c":
        x -= w / 2
    elif align == "r":
        x -= w
    c.drawString(s, x, y, f, fill(col, a))
    return w


def spaced_width(s: str, f: skia.Font, sp: float) -> float:
    s = nfc(s)
    return sum(f.measureText(ch) for ch in s) + sp * max(0, len(s) - 1)


def spaced_text(c: skia.Canvas, s: str, x: float, y: float, f: skia.Font, col: str, sp: float, a: float = 1.0,
                align: str = "l") -> float:
    """Chữ giãn cách (letter-spacing) — nhãn IN HOA."""
    s = nfc(s)
    w = spaced_width(s, f, sp)
    if align == "c":
        x -= w / 2
    elif align == "r":
        x -= w
    p = fill(col, a)
    for ch in s:
        c.drawString(ch, x, y, f, p)
        x += f.measureText(ch) + sp
    return w


def fit_font(s: str, weight: str, size: float, maxw: float, hand: bool = False) -> skia.Font:
    f = hand_font(size, weight) if hand else font(size, weight)
    w = f.measureText(nfc(s))
    if w > maxw > 0:
        size *= maxw / w
        f = hand_font(size, weight) if hand else font(size, weight)
    return f


def _upper(s: str) -> str:
    return nfc(s).upper()


# ---------------------------------------------------------------- icons
def warn_icon(c: skia.Canvas, cx: float, cy: float, s: float, col: str = YELLOW) -> None:
    """Tam giác cảnh báo vàng có dấu ! (s = cạnh)."""
    h = s * 0.87
    tri = poly([(cx, cy - h / 2), (cx + s / 2, cy + h / 2), (cx - s / 2, cy + h / 2)])
    c.drawPath(tri, fill(col))
    c.drawPath(tri, stroke(col, s * 0.12))
    ink = fill("#151517")
    c.drawRoundRect(skia.Rect.MakeLTRB(cx - s * 0.06, cy - h * 0.2, cx + s * 0.06, cy + h * 0.2), s * 0.05, s * 0.05, ink)
    c.drawCircle(cx, cy + h * 0.33, s * 0.07, ink)


def camera_icon(c: skia.Canvas, x: float, y: float, s: float, col: str = "#e6e8ea") -> None:
    """Camera an ninh chung chung (thân hộp + ống kính), góc trên-trái (x, y), cao s."""
    c.save()
    c.translate(x, y)
    c.rotate(-12)
    c.drawRoundRect(skia.Rect.MakeXYWH(0, s * 0.15, s * 1.2, s * 0.55), s * 0.1, s * 0.1, fill(col))
    c.drawRect(skia.Rect.MakeXYWH(s * 1.2, s * 0.28, s * 0.22, s * 0.3), fill(col))
    c.restore()
    c.drawRect(skia.Rect.MakeXYWH(x + s * 0.45, y + s * 0.62, s * 0.12, s * 0.38), fill(col))


def person_icon(c: skia.Canvas, cx: float, top: float, s: float, col: str) -> None:
    c.drawCircle(cx, top + s * 0.22, s * 0.2, fill(col))
    c.drawPath(rrect(cx - s * 0.32, top + s * 0.48, cx + s * 0.32, top + s * 1.0, s * 0.22), fill(col))


def leaf_emblem(c: skia.Canvas, cx: float, cy: float, r: float, fg: str = "#ffffff", bg: str = BRAND_GREEN,
                kind: str = "leaf") -> None:
    """Huy hiệu gốc của thư viện: lá trong vòng tròn hoặc sao 4 cánh."""
    c.drawCircle(cx, cy, r, fill(bg))
    c.drawCircle(cx, cy, r * 0.86, stroke(fg, r * 0.09))
    if kind == "star4":
        k = r * 0.58
        pts = []
        for i in range(8):
            a = -math.pi / 2 + i * math.pi / 4
            rr = k if i % 2 == 0 else k * 0.32
            pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
        c.drawPath(poly(pts), fill(fg))
        return
    p = skia.Path()
    p.moveTo(cx - r * 0.42, cy + r * 0.42)
    p.cubicTo(cx - r * 0.5, cy - r * 0.2, cx + r * 0.05, cy - r * 0.55, cx + r * 0.48, cy - r * 0.48)
    p.cubicTo(cx + r * 0.52, cy + r * 0.05, cx + r * 0.1, cy + r * 0.48, cx - r * 0.42, cy + r * 0.42)
    p.close()
    c.drawPath(p, fill(fg))
    vein = skia.Path()
    vein.moveTo(cx - r * 0.42, cy + r * 0.42)
    vein.quadTo(cx, cy, cx + r * 0.4, cy - r * 0.4)
    c.drawPath(vein, stroke(bg, r * 0.07))


def tape(c: skia.Canvas, cx: float, cy: float, w: float, h: float, ang: float, col: str = "#e2d3b0",
         a: float = 0.82) -> None:
    """Băng keo giấy: chữ nhật mờ, mép răng cưa nhẹ."""
    c.save()
    c.translate(cx, cy)
    c.rotate(ang)
    pts = []
    n = 7
    for i in range(n + 1):
        pts.append((-w / 2 + w * i / n, -h / 2 + (h * 0.05 if i % 2 else 0)))
    for i in range(n, -1, -1):
        pts.append((-w / 2 + w * i / n, h / 2 - (h * 0.05 if i % 2 else 0)))
    path = poly(pts)
    c.drawPath(path, fill(col, a))
    c.drawPath(path, stroke(shade(col, -0.15), max(1.0, h * 0.02), 0.4))
    c.restore()


def mitten_hand(c: skia.Canvas, x: float, y: float, s: float, ang: float, *, skin: str = SKIN,
                sleeve: str = BRAND_GREEN, mirror: bool = False) -> None:
    """Tay POV kiểu găng/ma-nơ-canh: 4 ngón capsule khớp tròn + ngón cái, móng sáng, cổ tay áo.
    (x, y) = đầu ngón giữa, hướng ngón chỉ lên (ang = độ xoay), s = chiều rộng bàn tay."""
    c.save()
    c.translate(x, y)
    c.rotate(ang)
    if mirror:
        c.scale(-1, 1)
    base = shade(skin, -0.12)
    # cổ tay áo + ống tay (kéo dài khỏi khung)
    c.drawPath(rrect(-s * 0.62, s * 1.25, s * 0.62, s * 4.0, s * 0.18), fill(sleeve))
    c.drawPath(rrect(-s * 0.66, s * 1.18, s * 0.66, s * 1.42, s * 0.1), fill(shade(sleeve, -0.18)))
    # lòng bàn tay
    c.drawPath(rrect(-s * 0.5, s * 0.35, s * 0.5, s * 1.3, s * 0.22), fill(skin))
    # 4 ngón
    fw = s * 0.235
    for i, (dx, ln) in enumerate(((-0.36, 0.62), (-0.12, 0.74), (0.12, 0.7), (0.36, 0.56))):
        cx = dx * s
        top = s * (0.48 - ln)
        c.drawPath(rrect(cx - fw / 2, top, cx + fw / 2, s * 0.62, fw / 2), fill(skin))
        c.drawPath(rrect(cx - fw / 2, top, cx + fw / 2, s * 0.62, fw / 2), stroke(base, s * 0.012, 0.6))
        # móng
        c.drawPath(rrect(cx - fw * 0.3, top + fw * 0.12, cx + fw * 0.3, top + fw * 0.62, fw * 0.2), fill("#f6e2d2"))
        # nếp đốt
        c.drawLine(cx - fw * 0.25, top + ln * s * 0.55, cx + fw * 0.25, top + ln * s * 0.55, stroke(base, s * 0.012))
    # ngón cái (chéo)
    c.save()
    c.translate(-s * 0.48, s * 0.8)
    c.rotate(-38)
    c.drawPath(rrect(-fw * 0.55, -s * 0.55, fw * 0.55, s * 0.05, fw * 0.55), fill(skin))
    c.drawPath(rrect(-fw * 0.3, -s * 0.5, fw * 0.3, -s * 0.3, fw * 0.2), fill("#f6e2d2"))
    c.restore()
    c.restore()


# ====================================================================== phụ đề
SUB_SIZE = 0.044
SUB_MAX_WORDS = 8


def render_subtitle(text_: str, W: int, H: int) -> tuple[skia.Image, tuple[float, float]]:
    size = SUB_SIZE * H
    f = font(size, "extrabold")
    lines = balanced_wrap(text_, f, W * 0.86)[:2]
    lh = size * 1.24
    ow = size * 0.14
    pad = ow * 3
    tw = max(f.measureText(ln) for ln in lines) if lines else 1
    w, h = tw + pad * 2, lh * len(lines) + pad * 2
    s, c = _surface(w, h)
    for i, ln in enumerate(lines):
        lw = f.measureText(ln)
        outlined_text(c, ln, (w - lw) / 2, pad + size * 0.98 + i * lh, f, ow=ow, shadow=0.7)
    img = s.makeImageSnapshot()
    # baseline dòng cuối ~89% chiều cao
    return img, ((W - w) / 2, H * 0.89 - (pad + size * 0.98 + (len(lines) - 1) * lh))


_PUNCT_END = (",", ".", "…", "!", "?", ":", ";", "—", "–")


def split_subtitle_chunks(text_: str, W: int, H: int) -> list[str]:
    """Chia câu thành các cụm 1 dòng (≈2–8 tiếng), ưu tiên ngắt ở dấu câu, cân độ dài (STYLE_GUIDE §9)."""
    f = font(SUB_SIZE * H, "extrabold")
    maxw = W * 0.84
    words = nfc(text_).split()
    if not words:
        return []
    if len(words) <= SUB_MAX_WORDS + 1 and f.measureText(" ".join(words)) <= maxw:
        return [" ".join(words)]
    n = len(words)
    target = 6.0
    INF = float("inf")
    best = [INF] * (n + 1)
    prev = [0] * (n + 1)
    best[0] = 0.0
    for j in range(1, n + 1):
        for i in range(max(0, j - SUB_MAX_WORDS), j):
            if best[i] == INF:
                continue
            chunk = " ".join(words[i:j])
            if j - i > 1 and f.measureText(chunk) > maxw:
                continue
            ln = j - i
            cost = (ln - target) ** 2
            if ln == 1 and n > 1:
                cost += 30
            if j < n and not words[j - 1].endswith(_PUNCT_END):
                cost += 6
            # ngắt ngay sau dấu câu giữa cụm (vd "…đó, tôi") -> phạt
            cost += sum(4 for w in words[i:j - 1] if w.endswith(_PUNCT_END))
            if best[i] + cost < best[j]:
                best[j], prev[j] = best[i] + cost, i
    out: list[str] = []
    j = n
    while j > 0:
        i = prev[j]
        out.append(" ".join(words[i:j]))
        j = i
    return out[::-1]


def subtitle_layers(shot: Shot, tls: list[TimedLine], duration: float, W: int, H: int) -> list[Layer]:
    out: list[Layer] = []
    segs: list[tuple[str, float, float]] = []
    if shot.subtitle:
        segs.append((shot.subtitle, 0.1, duration - 0.05))
    else:
        for tl in tls:
            if tl.line.text.strip():
                segs.append((tl.line.text, tl.start - 0.05, min(duration, tl.end + 0.25)))
    for text_, t0, t1 in segs:
        chunks = split_subtitle_chunks(text_, W, H)
        total = sum(len(ch) + 4 for ch in chunks) or 1
        cur = t0
        for ch in chunks:
            d = (t1 - t0) * (len(ch) + 4) / total
            img, pos = render_subtitle(ch, W, H)
            out.append(Layer(img, max(0.0, cur), cur + d, 0.08, 0.08, pos, kind="subtitle"))
            cur += d
    # tránh chồng chéo: phụ đề sau bắt đầu thì phụ đề trước kết thúc
    out.sort(key=lambda l: l.t0)
    for a, b in zip(out, out[1:]):
        if a.t1 > b.t0:
            a.t1 = b.t0
            a.fade_out = 0.0
            b.fade_in = 0.0 if b.t0 - a.t0 > 0.2 else b.fade_in
    return out


# ====================================================================== nametag
def render_nametag(name: str, role: str | None, H: int) -> skia.Image:
    fs = 0.030 * H
    rs = 0.020 * H
    fn, fr = font(fs, "bold"), font(rs, "semibold")
    name, role = nfc(name), nfc(role or "")
    padx, pady = 0.018 * H, 0.012 * H
    dot = 0.0085 * H
    tw = max(fn.measureText(name), fr.measureText(role) if role else 0)
    w = padx * 2 + dot * 2 + padx * 0.7 + tw
    h = pady * 2 + fs * 1.05 + (rs * 1.25 if role else 0)
    sh = 0.012 * H
    s, c = _surface(w + sh * 2, h + sh * 2)
    box = rrect(sh, sh, sh + w, sh + h, 0.014 * H)
    c.drawPath(box, _shadow_paint(0.45, sh * 0.6))
    c.drawPath(box, fill(IVORY))
    c.drawPath(box, stroke("#cbbfa8", max(1.0, H / 900)))
    cy = sh + pady + fs * 0.52
    c.drawCircle(sh + padx + dot, cy, dot, fill(GREEN_DOT))
    c.drawCircle(sh + padx + dot, cy, dot * 1.9, fill(GREEN_DOT, 0.22))
    tx = sh + padx + dot * 2 + padx * 0.7
    c.drawString(name, tx, sh + pady + fs * 0.9, fn, fill("#1f1a17"))
    if role:
        c.drawString(role, tx, sh + pady + fs * 1.05 + rs * 1.0, fr, fill("#7a736b"))
    return s.makeImageSnapshot()


# ====================================================================== location / time card
def render_place_card(title: str, subtitle: str | None, H: int, kind: str = "location_card") -> skia.Image:
    ts = 0.026 * H
    ss = 0.019 * H
    ft, fs = font(ts, "bold"), font(ss, "semibold")
    title, subtitle = nfc(title), nfc(subtitle or "")
    padx, pady = 0.016 * H, 0.011 * H
    dot = 0.007 * H
    tw = max(ft.measureText(title), fs.measureText(subtitle) if subtitle else 0)
    w = padx * 2 + dot * 2 + padx * 0.6 + tw
    h = pady * 2 + ts * 1.05 + (ss * 1.3 if subtitle else 0)
    sh = 0.01 * H
    s, c = _surface(w + sh * 2, h + sh * 2)
    box = rrect(sh, sh, sh + w, sh + h, 0.006 * H)
    c.drawPath(box, _shadow_paint(0.5, sh * 0.6))
    c.drawPath(box, fill(CARD_BG, 0.93))
    c.drawPath(box, stroke(CARD_BORDER, max(1.2, H / 700), 0.85))
    cy = sh + pady + ts * 0.5
    dcol = RED if kind == "location_card" else "#f0a33a"
    c.drawCircle(sh + padx + dot, cy, dot, fill(dcol))
    c.drawCircle(sh + padx + dot, cy, dot * 1.8, fill(dcol, 0.25))
    tx = sh + padx + dot * 2 + padx * 0.6
    c.drawString(title, tx, sh + pady + ts * 0.88, ft, fill("#ffffff"))
    if subtitle:
        c.drawString(subtitle, tx, sh + pady + ts * 1.05 + ss * 1.05, fs, fill("#ead9c6"))
    return s.makeImageSnapshot()


# ====================================================================== chapter card
def render_chapter_card(film_title: str, chapter: str, subtitle: str | None, W: int, H: int) -> skia.Image:
    film_title, chapter, subtitle = nfc(film_title), nfc(chapter), nfc(subtitle or "")
    f_title = font(0.075 * H, "extrabold")
    f_ch = font(0.038 * H, "bold")
    f_sub = font(0.034 * H, "semibold")
    title_lines = balanced_wrap(film_title.upper(), f_title, W * 0.62)
    pad = 0.04 * H
    gap = 0.022 * H
    chw = f_ch.measureText(chapter) + 0.05 * H
    chh = 0.062 * H
    tw = max([f_title.measureText(t) for t in title_lines] + [chw, f_sub.measureText(subtitle) if subtitle else 0])
    w = max(tw + pad * 2.4, W * 0.42)
    th = len(title_lines) * 0.075 * H * 1.12
    h = pad * 2 + th + gap + chh + (gap + 0.034 * H * 1.2 if subtitle else 0)
    sh = 0.02 * H
    s, c = _surface(w + sh * 2, h + sh * 2)
    box = rrect(sh, sh, sh + w, sh + h, 0.012 * H)
    c.drawPath(box, _shadow_paint(0.6, sh * 0.8))
    sh_grad = skia.GradientShader.MakeLinear([skia.Point(0, sh), skia.Point(0, sh + h)],
                                             [color("#221a16", 0.95), color("#0e0b0a", 0.95)])
    c.drawPath(box, skia.Paint(AntiAlias=True, Shader=sh_grad))
    c.drawPath(box, stroke(GOLD, 0.005 * H))
    inner = rrect(sh + 0.012 * H, sh + 0.012 * H, sh + w - 0.012 * H, sh + h - 0.012 * H, 0.008 * H)
    c.drawPath(inner, stroke(GOLD, 0.0015 * H, 0.7))
    y = sh + pad
    for t in title_lines:
        lw = f_title.measureText(t)
        y += 0.075 * H
        outlined_text(c, t, sh + (w - lw) / 2, y, f_title, "#ffffff", "#000000", 0.004 * H, 0.5)
        y += 0.075 * H * 0.12
    y += gap
    bx = sh + (w - chw) / 2
    c.drawPath(rrect(bx, y, bx + chw, y + chh, 0.006 * H), fill("#b3261e"))
    c.drawPath(rrect(bx, y, bx + chw, y + chh, 0.006 * H), stroke("#f0c060", 0.0015 * H, 0.8))
    c.drawString(chapter, bx + (chw - f_ch.measureText(chapter)) / 2, y + chh * 0.5 + 0.038 * H * 0.36, f_ch,
                 fill("#ffffff"))
    y += chh + gap
    if subtitle:
        c.drawString(subtitle, sh + (w - f_sub.measureText(subtitle)) / 2, y + 0.034 * H * 0.95, f_sub, fill(YELLOW))
    return s.makeImageSnapshot()


def render_black_title(title: str, subtitle: str | None, W: int, H: int) -> skia.Image:
    """Biến thể chapter_card 'text_on_black': khung đen, chữ trắng giữa (nhịp kinh dị)."""
    s, c = _surface(W, H)
    c.clear(color("#050506"))
    f = font(0.062 * H, "extrabold")
    lines = balanced_wrap(nfc(title), f, W * 0.78)
    lh = 0.062 * H * 1.25
    y = H * 0.5 - lh * (len(lines) - 1) / 2 + 0.062 * H * 0.35 - (0.03 * H if subtitle else 0)
    for ln in lines:
        text(c, ln, W / 2, y, f, "#f2efe8", align="c")
        y += lh
    if subtitle:
        fs = font(0.024 * H, "semibold")
        spaced_text(c, _upper(subtitle), W / 2, y + 0.01 * H, fs, "#c8352e", 0.004 * H, align="c")
    return s.makeImageSnapshot()


# ====================================================================== thẻ luật (sổ tay)
_KW = re.compile(r"(\*[^*]+\*|\[[^\]]+\]|«[^»]+»|\"[^\"]+\"|“[^”]+”)")


def _rule_tokens(text_: str) -> list[tuple[str, bool, bool]]:
    """Tách từ, đánh dấu từ khoá (trong *...*, [...], «...», "...") để tô đỏ."""
    out: list[tuple[str, bool, bool]] = []
    for part in _KW.split(nfc(text_)):
        if not part:
            continue
        hot = bool(_KW.fullmatch(part))
        if hot:
            part = part[1:-1]
        for i, w in enumerate(part.split()):
            # dấu câu dính liền từ khoá trước (vd "*không có bóng*." -> "bóng" + "." không có khoảng trắng)
            glue = i == 0 and not hot and bool(out) and not part[0].isspace()
            out.append((w, hot, glue))
    return out


Token = tuple[str, bool, bool]


def _layout_tokens(toks: list[Token], f: skia.Font, maxw: float) -> list[list[Token]]:
    space = f.measureText(" ")
    lines: list[list[Token]] = [[]]
    cur = 0.0
    for w, hot, glue in toks:
        ww = f.measureText(w)
        gap = 0.0 if (glue or not lines[-1]) else space
        if lines[-1] and not glue and cur + gap + ww > maxw:
            lines.append([])
            cur, gap = 0.0, 0.0
        cur += gap + ww
        lines[-1].append((w, hot, glue))
    return lines


def _tokens_width(ln: list[Token], f: skia.Font) -> float:
    space = f.measureText(" ")
    return sum(f.measureText(w) + (0.0 if (g or i == 0) else space) for i, (w, _, g) in enumerate(ln))


def _draw_tokens(c: skia.Canvas, ln: list[Token], x: float, y: float, f: skia.Font, col: str, hot_col: str,
                 a: float = 1.0) -> float:
    space = f.measureText(" ")
    x0 = x
    for i, (wd, hot, glue) in enumerate(ln):
        if i and not glue:
            x += space
        c.drawString(wd, x, y, f, fill(hot_col if hot else col, a))
        x += f.measureText(wd)
    return x - x0


def render_rule_card(rule_text: str, label: str | None, W: int, H: int, *, number: int | None = None,
                     caption: str | None = None) -> skia.Image:
    """Thẻ luật kiểu trang sổ tay: giấy kem kẻ dòng xanh, thanh lề đỏ dày + đường lề mảnh, pill đen (chấm đỏ +
    tam giác cảnh báo + "LUẬT N"), chữ xanh đậm, từ khoá đỏ, dòng phụ IN HOA xám, gạch dưới đỏ ngắn."""
    size = 0.035 * H
    fb = font(size, "bold")
    toks = _rule_tokens(rule_text)
    w = 0.30 * W
    bar = 0.0062 * W
    margin_x = bar + 0.026 * W          # đường lề mảnh
    tx = margin_x + 0.016 * W
    padr = 0.022 * W
    lines = _layout_tokens(toks, fb, w - tx - padr)
    if len(lines) > 3:                  # luật dài -> nới thẻ rồi thu chữ
        w = 0.38 * W
        lines = _layout_tokens(toks, fb, w - tx - padr)
        if len(lines) > 3:
            size *= 0.86
            fb = font(size, "bold")
            lines = _layout_tokens(toks, fb, w - tx - padr)
    if number is not None:
        lab = f"RULE {number}"
    else:
        lab = _upper(label or "RULE")
        m = re.search(r"(\d+)", lab)
        if m and ("LUẬT" in lab or "RULE" in lab):
            lab = f"RULE {m.group(1)}"
    fl = font(0.019 * H, "bold")
    pill_h = 0.036 * H
    lh = size * 1.42
    fc = font(0.0145 * H, "semibold")
    cap = _upper(caption) if caption else ""
    pad_t = 0.022 * H
    body_top = pad_t + pill_h + 0.012 * H
    h = body_top + lh * len(lines) + (0.012 * H + 0.0145 * H * 1.6 if cap else 0) + 0.034 * H
    h = max(h, 0.20 * H)
    sh = 0.016 * H
    s, c = _surface(w + sh * 2, h + sh * 2)
    c.translate(sh, sh)
    rad = 0.012 * H
    box = rrect(0, 0, w, h, rad)
    sp = _shadow_paint(0.5, sh * 0.6)
    c.save()
    c.translate(sh * 0.15, sh * 0.35)
    c.drawPath(box, sp)
    c.restore()
    grad = skia.GradientShader.MakeLinear([skia.Point(0, 0), skia.Point(0, h)],
                                          [color(PAPER), color(shade(PAPER, -0.04))])
    c.drawPath(box, skia.Paint(AntiAlias=True, Shader=grad))
    c.save()
    c.clipPath(box, skia.ClipOp.kIntersect, True)
    # dòng kẻ xanh (chữ đặt trên dòng)
    lp = stroke(RULE_LINE, max(1.0, 0.0012 * H), 0.85)
    y = body_top + lh * 0.98
    while y < h - 0.01 * H:
        c.drawLine(margin_x - 0.006 * W, y + size * 0.22, w, y + size * 0.22, lp)
        y += lh
    # thanh lề đỏ dày + đường lề mảnh
    c.drawRect(skia.Rect.MakeLTRB(0, 0, bar, h), fill(RED))
    c.drawLine(margin_x, 0, margin_x, h, stroke(RED, max(1.0, 0.0014 * H), 0.75))
    c.restore()
    c.drawPath(box, stroke(shade(PAPER, -0.18), max(1.0, H / 1000), 0.8))
    # pill đen: chấm đỏ + cảnh báo + nhãn
    sp_l = 0.0022 * H
    lw = spaced_width(lab, fl, sp_l)
    pw = pill_h * 0.5 + 0.016 * H + 0.012 * H + pill_h * 0.62 + 0.01 * H + lw + pill_h * 0.5
    px, py = tx, pad_t
    c.drawPath(rrect(px, py, px + pw, py + pill_h, pill_h / 2), fill("#151517"))
    cx = px + pill_h * 0.5 + 0.008 * H
    c.drawCircle(cx, py + pill_h / 2, 0.0075 * H, fill(RED))
    c.drawCircle(cx, py + pill_h / 2, 0.012 * H, fill(RED, 0.3))
    wx = cx + 0.012 * H + 0.008 * H + pill_h * 0.31
    warn_icon(c, wx, py + pill_h / 2, pill_h * 0.58)
    spaced_text(c, lab, wx + pill_h * 0.31 + 0.01 * H, py + pill_h * 0.5 + 0.019 * H * 0.36, fl, "#ffffff", sp_l)
    # thân
    y = body_top
    for ln in lines:
        y += lh
        _draw_tokens(c, ln, tx, y - lh * 0.24, fb, INK, RED)
    y += 0.004 * H
    if cap:
        y += 0.012 * H + 0.0145 * H
        spaced_text(c, cap, tx, y, fc, "#8a8478", 0.0026 * H)
    c.drawRoundRect(skia.Rect.MakeXYWH(tx, y + 0.012 * H, 0.05 * W, 0.0045 * H), 0.002 * H, 0.002 * H, fill(RED))
    return s.makeImageSnapshot()


# ====================================================================== tờ luật toàn khung
def render_rule_paper(title: str, note: str | None, rules: list[str], W: int, H: int, *, red_index: int | None = None,
                      redact_last: bool = False, coffee_stain: bool = False, bleed_through: bool = False,
                      seed: int = 0) -> skia.Image:
    """Giấy vở kẻ (kem, dòng xanh, lề đỏ), băng keo 2 góc trên, tiêu đề xanh đậm, luật đánh số chữ viết tay xanh,
    1 luật đỏ, tuỳ chọn thanh bôi đen dòng cuối / vết cà phê / chữ thấm ngược mặt sau. Ảnh chưa xoay."""
    rng = random.Random(seed)
    pw, ph = 0.56 * W, 0.92 * H
    m = 0.03 * H                       # lề ảnh cho băng keo + bóng
    s, c = _surface(pw + m * 2, ph + m * 2)
    c.translate(m, m)
    paper_col = "#f3ead6"
    path = skia.Path()
    path.addRect(skia.Rect.MakeWH(pw, ph))
    c.save()
    c.translate(0.004 * H, 0.012 * H)
    c.drawPath(path, _shadow_paint(0.55, 0.014 * H))
    c.restore()
    grad = skia.GradientShader.MakeRadial(skia.Point(pw * 0.45, ph * 0.4), max(pw, ph) * 0.8,
                                          [color(shade(paper_col, 0.04)), color(shade(paper_col, -0.07))])
    c.drawPath(path, skia.Paint(AntiAlias=True, Shader=grad))
    lh = 0.052 * H
    top = 0.17 * ph
    margin_x = 0.13 * pw
    lp = stroke(RULE_LINE, max(1.0, 0.0013 * H), 0.8)
    y = top
    while y < ph - 0.02 * H:
        c.drawLine(0, y, pw, y, lp)
        y += lh
    c.drawLine(margin_x, 0, margin_x, ph, stroke("#d0302a", max(1.0, 0.0016 * H), 0.7))
    c.drawLine(margin_x + 0.005 * H, 0, margin_x + 0.005 * H, ph, stroke("#d0302a", max(1.0, 0.0009 * H), 0.5))
    # lỗ đục lề trái
    for k in range(3):
        c.drawCircle(margin_x * 0.42, ph * (0.2 + 0.3 * k), 0.012 * H, fill("#2a2522", 0.18))
    ink_hand = hand_font(0.031 * H)
    tx = margin_x + 0.022 * H
    maxw = pw - tx - 0.04 * H
    if bleed_through:   # chữ thấm từ mặt sau (ngược, rất mờ)
        c.save()
        c.translate(pw, 0)
        c.scale(-1, 1)
        fb = hand_font(0.028 * H, "regular")
        yy = top + lh * 0.75
        for i in range(int((ph - top) / lh) - 1):
            ln = " ".join(rng.choice(["do", "not", "open", "the", "door", "after", "anyone", "calls", "your", "name",
                                      "never", "answer", "look", "mirror", "lights", "off"]) for _ in range(rng.randint(4, 8)))
            c.drawString(ln, tx, yy, fb, fill("#1f3f8a", 0.05))
            yy += lh
        c.restore()
    # tiêu đề + ghi chú
    ft = fit_font(title, "extrabold", 0.052 * H, pw - 0.1 * H)
    text(c, title, pw / 2, top - 0.055 * H, ft, "#1b2f63", align="c")
    if note:
        fn = hand_font(0.024 * H, "regular")
        text(c, f"({nfc(note).strip('()')})", pw / 2, top - 0.016 * H, fn, "#5a6a8a", align="c")
    # luật
    y = top
    lines_drawn: list[tuple[float, float, float]] = []   # (y, x0, x1) dòng cuối của mỗi luật
    for idx, rule in enumerate(rules):
        col = RED_INK if red_index is not None and idx == red_index else HAND_INK
        num = f"{idx + 1}."
        toks = _rule_tokens(rule)
        lines = _layout_tokens(toks, ink_hand, maxw - 0.035 * H)
        first = True
        for ln in lines:
            y += lh
            if y > ph - 0.02 * H:
                break
            if first:
                text(c, num, tx, y - lh * 0.2, ink_hand, col)
                first = False
            wln = _draw_tokens(c, ln, tx + 0.04 * H, y - lh * 0.2, ink_hand, col, RED_INK if col == HAND_INK else "#8a1010")
            lines_drawn.append((y, tx, tx + 0.04 * H + wln))
        if idx == len(rules) - 1 and redact_last and lines:
            # thanh bôi đen (bút dạ) phủ các dòng của luật cuối
            for (ly, x0, x1) in lines_drawn[-len(lines):]:
                pts = []
                n = 14
                for i in range(n + 1):
                    pts.append((x0 - 0.01 * H + (x1 - x0 + 0.03 * H) * i / n, ly - lh * 0.72 + rng.uniform(-2, 2) * H / 1080))
                for i in range(n, -1, -1):
                    pts.append((x0 - 0.01 * H + (x1 - x0 + 0.03 * H) * i / n, ly - lh * 0.02 + rng.uniform(-2, 2) * H / 1080))
                c.drawPath(poly(pts), fill("#111114"))
    if coffee_stain:
        cx, cy, r = pw * 0.78, ph * 0.84, 0.075 * H
        ring = stroke("#8a5a2b", 0.007 * H, 0.35)
        ring.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 0.002 * H))
        c.drawCircle(cx, cy, r, ring)
        c.drawCircle(cx + r * 0.08, cy - r * 0.05, r * 0.96, stroke("#8a5a2b", 0.003 * H, 0.25))
        c.drawCircle(cx, cy, r * 0.95, fill("#a87a4a", 0.08))
        c.drawCircle(cx - r * 1.25, cy + r * 0.4, r * 0.12, fill("#8a5a2b", 0.25))
    # băng keo 2 góc trên
    tape(c, 0.02 * H, 0.01 * H, 0.13 * H, 0.04 * H, -38)
    tape(c, pw - 0.02 * H, 0.01 * H, 0.13 * H, 0.04 * H, 38)
    return s.makeImageSnapshot()


# ====================================================================== bảng tên trên áo (badge)
def render_badge(text_: str, W_px: int = 330, H_px: int = 104, bg: str = "#ffffff", text_color: str = "#7a2a2a",
                 emblem: str = "leaf") -> skia.Image:
    """Bảng tên trắng chữ nhật (vẽ như một phần áo). Kích thước ảnh px; compositor co theo xương torso."""
    s, c = _surface(W_px, H_px)
    r = H_px * 0.12
    c.drawPath(rrect(1, 1, W_px - 1, H_px - 1, r), fill(bg))
    c.drawPath(rrect(1, 1, W_px - 1, H_px - 1, r), stroke("#9a948a", max(1.5, H_px * 0.03)))
    tx = H_px * 0.18
    if emblem in ("leaf", "star4"):
        er = H_px * 0.32
        leaf_emblem(c, H_px * 0.5, H_px * 0.5, er, kind=emblem)
        tx = H_px * 0.92
    f = fit_font(text_, "extrabold", H_px * 0.5, W_px - tx - H_px * 0.16)
    text(c, text_, tx + (W_px - tx - H_px * 0.12) / 2, H_px * 0.5 + f.getSize() * 0.36, f, text_color, align="c")
    return s.makeImageSnapshot()


# ====================================================================== CCTV HUD
DEFAULT_TS = "14-03-2024 02:47:13"


def _parse_ts(s: str | None) -> datetime | None:
    for fmt in ("%d-%m-%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M"):
        try:
            return datetime.strptime(nfc(s or "").strip(), fmt)
        except ValueError:
            continue
    return None


def _people_at(spec: Any, t: float) -> int | None:
    if spec is None:
        return None
    if isinstance(spec, (int, float)):
        return int(spec)
    if isinstance(spec, str) and spec.strip().isdigit():
        return int(spec)
    if isinstance(spec, list):
        cur = None
        for item in spec:
            try:
                tt, n = item
            except (TypeError, ValueError):
                continue
            if t >= float(tt):
                cur = int(n)
            elif cur is None:
                cur = int(n)
        return cur
    return None


def _people_change_t(spec: Any, t: float) -> float | None:
    """Thời điểm đổi số gần nhất trước t (để nháy viền)."""
    if not isinstance(spec, list):
        return None
    best = None
    for i, item in enumerate(spec):
        try:
            tt = float(item[0])
        except (TypeError, ValueError, IndexError):
            continue
        if i > 0 and tt <= t:
            best = tt
    return best


def render_counter_box(label: str, H: int, scale: float = 1.0) -> tuple[skia.Image, dict[str, float]]:
    """Hộp đếm người (không có số — số vẽ theo frame). Trả về ảnh + vị trí số trong ảnh."""
    k = H * scale
    w, h = 0.14 * 16 / 9 * k, 0.12 * k
    s, c = _surface(w, h)
    box = rrect(1, 1, w - 1, h - 1, 0.0075 * k)
    c.drawPath(box, fill("#0b0c0e", 0.85))
    c.drawPath(box, stroke("#d9dde2", max(1.0, k / 1080), 0.85))
    pad = 0.012 * k
    camera_icon(c, pad, pad * 0.9, 0.016 * k)
    c.drawCircle(pad + 0.03 * k, pad * 0.9 + 0.004 * k, 0.0035 * k, fill("#e0262b"))
    fl = fit_font(_upper(label), "semibold", 0.0118 * k, w - pad * 2 - 0.04 * k)
    lines = [_upper(label)]
    if fl.getSize() < 0.0095 * k:   # nhãn dài -> 2 dòng
        fl = font(0.0105 * k, "semibold")
        lines = wrap_text(_upper(label), fl, w - pad * 2 - 0.04 * k, 2)
    y = pad + 0.012 * k
    for ln in lines:
        c.drawString(ln, pad + 0.04 * k, y, fl, fill("#c9ced4"))
        y += fl.getSize() * 1.2
    return s.makeImageSnapshot(), {"x": pad, "y": h - pad * 1.1, "size": 0.074 * k, "unit_size": 0.02 * k, "w": w,
                                   "h": h}


def cctv_layer(ov: Overlay, W: int, H: int, end: float) -> Layer:
    d = dict(ov.data or {})
    cam = d.get("cam", 1)
    label = nfc(d.get("label") or ov.subtitle or "")
    title = nfc(ov.title or "").strip()
    cam_line = title if title else f"CAM {cam}" + (f" · {label}" if label else "")
    ts0 = _parse_ts(d.get("timestamp")) or _parse_ts(DEFAULT_TS)
    tick = d.get("tick", True) is not False
    people = d.get("people")
    unit = nfc(d.get("people_unit") or "people")
    emphasis = bool(d.get("people_emphasis"))
    grid = int(d.get("grid", 1) or 1)
    cells = d.get("cells") or []
    split = d.get("split") if isinstance(d.get("split"), dict) else None
    images: dict[str, skia.Image] = {}
    meta: dict[str, Any] = {}
    if people is not None:
        img, meta = render_counter_box(d.get("people_label") or "PEOPLE IN STORE", H)
        images["counter"] = img
        if emphasis:
            img2, meta2 = render_counter_box(d.get("people_label") or "PEOPLE IN STORE", H, 2.5)
            images["counter_big"] = img2
            meta["big"] = meta2
    f_rec = font(0.033 * H, "extrabold")
    f_cam = font(0.02 * H, "semibold")
    f_ts = font(0.03 * H, "semibold")
    f_cell = font(0.018 * H, "bold")
    f_cap = font(0.016 * H, "semibold")
    f_pill = font(0.02 * H, "bold")
    shadow = fill("#000000", 0.55)
    white = fill("#ffffff")
    m = 0.035 * H

    def label_text(c: skia.Canvas, s: str, x: float, y: float, f: skia.Font, p: skia.Paint) -> None:
        c.drawString(s, x + H * 0.0016, y + H * 0.0016, f, shadow)
        c.drawString(s, x, y, f, p)

    def draw(layer: Layer, c: skia.Canvas, t: float, a: float) -> None:
        img = layer.images
        rec_on = (t % 1.0) < 0.62
        # ---- lưới 4 / split: nhãn từng ô
        if grid == 4:
            for i in range(4):
                cx0 = (i % 2) * W / 2
                cy0 = (i // 2) * H / 2
                cell = cells[i] if i < len(cells) and isinstance(cells[i], dict) else {}
                n = cell.get("cam", i + 1)
                lx, ly = cx0 + 0.02 * H, cy0 + 0.045 * H
                if rec_on:
                    c.drawCircle(lx + 0.008 * H, ly - 0.0065 * H, 0.0075 * H, fill("#e0262b", a))
                label_text(c, f"CAM {n}", lx + 0.022 * H, ly, f_cell, fill("#ffffff", a))
                capt = nfc(cell.get("label") or "")
                if capt:
                    label_text(c, capt, cx0 + 0.02 * H, cy0 + H / 2 - 0.025 * H, f_cap, fill("#e6e8ea", a * 0.95))
        else:
            # ---- REC + CAM (trên-trái; split: trong nửa trái)
            x0, y0 = m, m + 0.03 * H
            if rec_on:
                c.drawCircle(x0 + 0.014 * H, y0 - 0.011 * H, 0.0125 * H, fill("#e0262b", a))
                c.drawCircle(x0 + 0.014 * H, y0 - 0.011 * H, 0.02 * H, fill("#e0262b", a * 0.25))
            label_text(c, "REC", x0 + 0.036 * H, y0, f_rec, fill("#ffffff", a))
            label_text(c, cam_line, x0 + 0.002 * H, y0 + 0.036 * H, f_cam, fill("#e6e8ea", a * 0.92))
        if split:
            mid = W / 2
            c.drawRect(skia.Rect.MakeLTRB(mid - H * 0.002, 0, mid + H * 0.002, H), fill("#f2f2f2", a * 0.9))
            for side, tag, col in ((0, split.get("left_tag") or "on camera", "#e0262b"),
                                   (1, split.get("right_tag") or "naked eye", "#3cb44b")):
                tg = _upper(tag)
                tw = spaced_width(tg, f_pill, 0.002 * H)
                ph_ = 0.046 * H
                pw_ = tw + ph_ * 1.6
                cx = mid / 2 + side * mid
                py = H - 0.2 * H if side == 0 else H - 0.2 * H
                c.drawPath(rrect(cx - pw_ / 2, py, cx + pw_ / 2, py + ph_, ph_ / 2), fill("#0b0c0e", a * 0.85))
                c.drawCircle(cx - pw_ / 2 + ph_ * 0.5, py + ph_ / 2, ph_ * 0.16, fill(col, a))
                spaced_text(c, tg, cx - pw_ / 2 + ph_ * 0.85, py + ph_ / 2 + 0.02 * H * 0.36, f_pill, "#ffffff",
                            0.002 * H, a)
        # ---- timestamp dưới-phải
        if ts0 is not None:
            ts = ts0 + timedelta(seconds=int(t) if tick else 0)
            s = ts.strftime("%d-%m-%Y %H:%M:%S")
            tw = f_ts.measureText(s)
            x = (W / 2 if split else W) - m - tw
            label_text(c, s, x, H - m - 0.004 * H, f_ts, fill("#e6e8ea", a))
        # ---- hộp đếm người
        if people is not None and "counter" in img:
            n = _people_at(people, t)
            ch = _people_change_t(people, t)
            flash = ch is not None and 0 <= t - ch < 0.6 and int((t - ch) * 8) % 2 == 0
            if emphasis and "counter_big" in img:
                u = ease_out_back(min(1.0, max(0.0, (t - layer.t0) / 0.45)))
                bm = meta["big"]
                ci = img["counter_big"]
                small_w, big_w = meta["w"], bm["w"]
                sc = (small_w + (big_w - small_w) * u) / big_w
                x1 = W - m - small_w
                y1 = m
                bx = x1 + ((W - big_w) / 2 - x1) * u
                by = y1 + ((H - bm["h"]) / 2 - 0.04 * H - y1) * u
                c.save()
                c.translate(bx, by)
                c.scale(sc, sc)
                c.drawImage(ci, 0, 0, LIN, skia.Paint(Alphaf=a))
                if n is not None:
                    fn = font(bm["size"], "extrabold")
                    c.drawString(str(n), bm["x"], bm["y"], fn, fill("#ffffff", a))
                    c.drawString(unit, bm["x"] + fn.measureText(str(n)) + bm["unit_size"] * 0.4, bm["y"],
                                 font(bm["unit_size"], "semibold"), fill("#c9ced4", a))
                if flash:
                    c.drawPath(rrect(1, 1, big_w - 1, bm["h"] - 1, 0.0075 * H * 2.5), stroke("#e0262b", 0.006 * H * 2.5, a))
                c.restore()
            else:
                ci = img["counter"]
                x = (W / 2 if split else W) - m - meta["w"]
                y = m
                c.drawImage(ci, x, y, LIN, skia.Paint(Alphaf=a))
                if n is not None:
                    fn = font(meta["size"], "extrabold")
                    sn = str(n)
                    c.drawString(sn, x + meta["x"], y + meta["y"], fn, fill("#ffffff", a))
                    c.drawString(unit, x + meta["x"] + fn.measureText(sn) + meta["unit_size"] * 0.4, y + meta["y"],
                                 font(meta["unit_size"], "semibold"), fill("#c9ced4", a))
                if flash:
                    c.drawPath(rrect(x + 1, y + 1, x + meta["w"] - 1, y + meta["h"] - 1, 0.0075 * H),
                               stroke("#e0262b", 0.004 * H, a))

    lay = Layer(None, 0.0, end + 1.0, 0.0, 0.0, kind="cctv", draw_fn=draw, images=images, data=d)
    if emphasis:
        lay.backdrop = "blur"
        lay.backdrop_dim = 0.3
    return lay


# ====================================================================== điện thoại
def _avatar_color(name: str) -> str:
    pal = ["#e8833a", "#3a78c2", "#4fa35a", "#c74a9a", "#b5332b", "#1f6f5c", "#8a6a9a"]
    return pal[sum(ord(ch) for ch in nfc(name)) % len(pal)]


def _status_bar(c: skia.Canvas, l: float, t: float, r: float, s: float, time_s: str, col: str) -> None:
    """Thanh trạng thái: giờ trái, sóng + pin phải. s = bề rộng màn hình."""
    f = font(s * 0.042, "semibold")
    c.drawString(nfc(time_s), l + s * 0.09, t + s * 0.075, f, fill(col))
    x = r - s * 0.2
    for i in range(4):
        bh = s * (0.012 + i * 0.006)
        c.drawRoundRect(skia.Rect.MakeXYWH(x + i * s * 0.014, t + s * 0.072 - bh, s * 0.009, bh), 1, 1, fill(col))
    bx = r - s * 0.13
    c.drawPath(rrect(bx, t + s * 0.045, bx + s * 0.06, t + s * 0.074, s * 0.007), stroke(col, s * 0.004))
    c.drawPath(rrect(bx + s * 0.007, t + s * 0.052, bx + s * 0.042, t + s * 0.067, s * 0.003), fill(col))
    c.drawRect(skia.Rect.MakeXYWH(bx + s * 0.062, t + s * 0.054, s * 0.005, s * 0.011), fill(col))


def phone_geometry(W: int, H: int, phone_h: float = 0.86) -> dict[str, float]:
    ph = phone_h * H
    pw = ph * 0.49
    x = (W - pw) / 2
    y = (H - ph) / 2
    inset = pw * 0.035
    return {"x": x, "y": y, "w": pw, "h": ph, "sl": x + inset, "st": y + inset, "sr": x + pw - inset,
            "sb": y + ph - inset, "sw": pw - inset * 2}


def draw_phone_frame(c: skia.Canvas, g: dict[str, float], screen_col: str | skia.Shader = "#101114") -> skia.Path:
    """Vỏ điện thoại hiện đại (viền đen, notch viên thuốc). Trả về path màn hình (để clip)."""
    x, y, pw, ph = g["x"], g["y"], g["w"], g["h"]
    body = rrect(x, y, x + pw, y + ph, pw * 0.13)
    c.save()
    c.translate(pw * 0.012, ph * 0.02)
    c.drawPath(body, _shadow_paint(0.6, pw * 0.04))
    c.restore()
    c.drawPath(body, fill("#0b0b0d"))
    c.drawPath(body, stroke("#3a3b40", pw * 0.008))
    # nút cạnh
    c.drawRoundRect(skia.Rect.MakeXYWH(x + pw - pw * 0.004, y + ph * 0.2, pw * 0.014, ph * 0.08), 3, 3, fill("#2a2b30"))
    c.drawRoundRect(skia.Rect.MakeXYWH(x - pw * 0.01, y + ph * 0.17, pw * 0.014, ph * 0.05), 3, 3, fill("#2a2b30"))
    scr = rrect(g["sl"], g["st"], g["sr"], g["sb"], pw * 0.1)
    if isinstance(screen_col, skia.Shader):
        c.drawPath(scr, skia.Paint(AntiAlias=True, Shader=screen_col))
    else:
        c.drawPath(scr, fill(screen_col))
    return scr


def draw_notch(c: skia.Canvas, g: dict[str, float]) -> None:
    nw, nh = g["w"] * 0.28, g["w"] * 0.07
    cx = g["x"] + g["w"] / 2
    c.drawPath(rrect(cx - nw / 2, g["st"] + g["w"] * 0.025, cx + nw / 2, g["st"] + g["w"] * 0.025 + nh, nh / 2),
               fill("#000000"))


def phone_hand_back(c: skia.Canvas, g: dict[str, float], H: int, sleeve: str, skin: str) -> None:
    """Tay POV cầm điện thoại (phần SAU máy): lòng bàn tay đỡ đáy máy + ống tay áo từ đáy khung."""
    pw, ph = g["w"], g["h"]
    x, y = g["x"], g["y"]
    cx = x + pw * 0.45
    # ống tay áo
    c.save()
    c.translate(cx + pw * 0.05, y + ph * 0.98)
    c.rotate(8)
    c.drawPath(rrect(-pw * 0.42, ph * 0.05, pw * 0.42, ph * 0.6, pw * 0.12), fill(sleeve))
    c.drawPath(rrect(-pw * 0.45, 0, pw * 0.45, ph * 0.1, pw * 0.06), fill(shade(sleeve, -0.18)))
    c.restore()
    # lòng bàn tay
    c.drawPath(rrect(x - pw * 0.04, y + ph * 0.66, x + pw * 0.98, y + ph * 1.04, pw * 0.2), fill(skin))
    c.drawPath(rrect(x - pw * 0.04, y + ph * 0.66, x + pw * 0.98, y + ph * 1.04, pw * 0.2),
               stroke(shade(skin, -0.15), max(1.0, pw * 0.006)))


def phone_hand_front(c: skia.Canvas, g: dict[str, float], H: int, skin: str) -> None:
    """Phần TRƯỚC máy: ngón cái ôm mép trái + 3 đầu ngón ôm mép phải (kiểu ngón capsule, móng sáng)."""
    pw, ph = g["w"], g["h"]
    x, y = g["x"], g["y"]
    base = shade(skin, -0.15)
    nail = "#f6e2d2"
    fw = pw * 0.105
    # ngón cái: từ dưới-trái chéo lên, đè viền trái
    c.save()
    c.translate(x + pw * 0.035, y + ph * 0.9)
    c.rotate(14)
    c.drawPath(rrect(-fw / 2, -ph * 0.2, fw / 2, ph * 0.02, fw / 2), fill(skin))
    c.drawPath(rrect(-fw / 2, -ph * 0.2, fw / 2, ph * 0.02, fw / 2), stroke(base, max(1.0, pw * 0.005)))
    c.drawPath(rrect(-fw * 0.3, -ph * 0.195, fw * 0.3, -ph * 0.155, fw * 0.22), fill(nail))
    c.drawLine(-fw * 0.3, -ph * 0.1, fw * 0.3, -ph * 0.1, stroke(base, max(1.0, pw * 0.005)))
    c.restore()
    # 3 ngón ôm mép phải (thò ra từ sau máy)
    for i in range(3):
        fy = y + ph * (0.6 + 0.085 * i)
        l = x + pw * 0.93
        c.drawPath(rrect(l, fy, l + pw * 0.11, fy + fw * 0.9, fw * 0.45), fill(skin))
        c.drawPath(rrect(l, fy, l + pw * 0.11, fy + fw * 0.9, fw * 0.45), stroke(base, max(1.0, pw * 0.005)))
        c.drawPath(rrect(l + pw * 0.005, fy + fw * 0.18, l + pw * 0.04, fy + fw * 0.72, fw * 0.2), fill(nail))


def _bubble_image(text_: str, me: bool, maxw: float, H: int, cols: dict[str, str]) -> skia.Image:
    f = font(0.021 * H, "regular")
    lines = wrap_text(text_, f, maxw - 0.03 * H)
    lh = 0.021 * H * 1.32
    tw = max(f.measureText(ln) for ln in lines) if lines else 0
    pad_x, pad_y = 0.015 * H, 0.011 * H
    w, h = tw + pad_x * 2, lh * len(lines) + pad_y * 2 - 0.021 * H * 0.3
    s, c = _surface(w, h)
    r = min(0.018 * H, h / 2)
    rr = skia.RRect()
    small = 0.005 * H
    radii = [skia.Point(r, r), skia.Point(r, r), skia.Point(small, small) if me else skia.Point(r, r),
             skia.Point(r, r) if me else skia.Point(small, small)]
    rr.setRectRadii(skia.Rect.MakeWH(w, h), radii)
    c.drawRRect(rr, fill(cols["bubble_out"] if me else cols["bubble_in"]))
    y = pad_y + 0.021 * H * 0.95
    for ln in lines:
        c.drawString(ln, pad_x, y, f, fill(cols["text"]))
        y += lh
    return s.makeImageSnapshot()


def phone_chat_layer(ov: Overlay, W: int, H: int, end: float) -> Layer:
    d = dict(ov.data or {})
    cols = {"bubble_in": "#3a3b40", "bubble_out": "#2e7cf6", "text": "#ffffff"}
    g = phone_geometry(W, H, float(d.get("phone_h", 0.86)))
    sw = g["sw"]
    name = nfc(ov.title or "Unknown")
    status = nfc(ov.subtitle or "Online")
    time_s = nfc(str(d.get("time") or "02:14"))
    hand = bool(d.get("hand"))
    sleeve = d.get("sleeve") or BRAND_GREEN
    skin = d.get("skin") or SKIN
    base, c = _surface(W, H)
    if d.get("lock_screen"):
        wall = skia.GradientShader.MakeLinear([skia.Point(0, g["st"]), skia.Point(0, g["sb"])],
                                              [color("#141a2e"), color("#2a2142"), color("#3b2a3a")])
        if hand:
            phone_hand_back(c, g, H, sleeve, skin)
        scr = draw_phone_frame(c, g, wall)
        c.save()
        c.clipPath(scr, skia.ClipOp.kIntersect, True)
        _status_bar(c, g["sl"], g["st"], g["sr"], sw, "", "#ffffff")
        fclock = font(sw * 0.24, "regular")
        cx = g["x"] + g["w"] / 2
        text(c, time_s, cx, g["st"] + sw * 0.52, fclock, "#f2f2f5", align="c")
        text(c, nfc(str(d.get("date") or "Saturday, March 14")), cx, g["st"] + sw * 0.25, font(sw * 0.045, "semibold"),
             "#d8d8e0", align="c")
        c.restore()
        draw_notch(c, g)
        # thẻ thông báo (vẽ riêng để pop)
        notif = d.get("notification") or {"sender": name, "text": "Are you still at the store?"}
        nw, nh = sw * 0.9, sw * 0.24
        ns, nc = _surface(nw, nh)
        nc.drawPath(rrect(0, 0, nw, nh, sw * 0.05), fill("#2a2c33", 0.92))
        ic = sw * 0.09
        nc.drawPath(rrect(sw * 0.035, sw * 0.04, sw * 0.035 + ic, sw * 0.04 + ic, ic * 0.25), fill("#4fa35a"))
        nc.drawPath(rrect(sw * 0.035 + ic * 0.2, sw * 0.04 + ic * 0.25, sw * 0.035 + ic * 0.8, sw * 0.04 + ic * 0.68,
                          ic * 0.2), fill("#ffffff"))
        nc.drawString("MESSAGES", sw * 0.035 + ic + sw * 0.03, sw * 0.08, font(sw * 0.032, "semibold"), fill("#b9bcc6"))
        text(nc, "now", nw - sw * 0.04, sw * 0.08, font(sw * 0.03, "regular"), "#9a9da8", align="r")
        nc.drawString(nfc(str(notif.get("sender") or name)), sw * 0.035, sw * 0.155, font(sw * 0.042, "bold"),
                      fill("#ffffff"))
        tl = wrap_text(str(notif.get("text") or ""), font(sw * 0.038, "regular"), nw - sw * 0.07, 2)
        for i, ln in enumerate(tl[:2]):
            nc.drawString(ln, sw * 0.035, sw * 0.205 + i * sw * 0.048, font(sw * 0.038, "regular"), fill("#e6e8ee"))
        images = {"base": base.makeImageSnapshot(), "notif": ns.makeImageSnapshot()}
        npos = (g["sl"] + (sw - nw) / 2, g["st"] + sw * 0.72)
        if hand:
            hs, hc = _surface(W, H)
            phone_hand_front(hc, g, H, skin)
            images["hand"] = hs.makeImageSnapshot()

        def draw_lock(layer: Layer, cv: skia.Canvas, t: float, a: float) -> None:
            dy = (1 - ease_out(layer.entering(t))) * 0.08 * H
            p = skia.Paint(Alphaf=a)
            cv.drawImage(layer.images["base"], 0, dy, LIN, p)
            u = ease_out_back(min(1.0, max(0.0, (t - layer.t0 - 0.5) / 0.35)))
            if u > 0:
                cv.save()
                cv.translate(npos[0] + nw / 2, npos[1] + dy - (1 - u) * sw * 0.15)
                cv.scale(0.9 + 0.1 * u, 0.9 + 0.1 * u)
                cv.drawImage(layer.images["notif"], -nw / 2, 0, LIN, skia.Paint(Alphaf=a * min(1.0, u)))
                cv.restore()
            if "hand" in layer.images:
                cv.drawImage(layer.images["hand"], 0, dy, LIN, p)
        return Layer(None, 0.15, end - 0.05, 0.3, 0.25, kind="phone_chat", draw_fn=draw_lock, images=images,
                     backdrop="blur", backdrop_dim=0.45, data=d)

    if hand:
        phone_hand_back(c, g, H, sleeve, skin)
    scr = draw_phone_frame(c, g, "#101114")
    c.save()
    c.clipPath(scr, skia.ClipOp.kIntersect, True)
    _status_bar(c, g["sl"], g["st"], g["sr"], sw, time_s, "#ffffff")
    # header
    hy0, hy1 = g["st"] + sw * 0.12, g["st"] + sw * 0.27
    c.drawRect(skia.Rect.MakeLTRB(g["sl"], hy0, g["sr"], hy1), fill("#16171b"))
    cy = (hy0 + hy1) / 2
    chev = skia.Path()
    chev.moveTo(g["sl"] + sw * 0.075, cy - sw * 0.025)
    chev.lineTo(g["sl"] + sw * 0.05, cy)
    chev.lineTo(g["sl"] + sw * 0.075, cy + sw * 0.025)
    c.drawPath(chev, stroke("#2e7cf6", sw * 0.011))
    ar = sw * 0.055
    ax = g["sl"] + sw * 0.15
    c.drawCircle(ax, cy, ar, fill(_avatar_color(name)))
    text(c, name[:1].upper(), ax, cy + ar * 0.38, font(ar * 1.05, "bold"), "#ffffff", align="c")
    c.drawCircle(ax + ar * 0.72, cy + ar * 0.72, ar * 0.22, fill("#3cb44b"))
    c.drawCircle(ax + ar * 0.72, cy + ar * 0.72, ar * 0.22, stroke("#16171b", ar * 0.08))
    fname = fit_font(name, "bold", sw * 0.048, sw * 0.5)
    c.drawString(name, ax + ar * 1.5, cy - sw * 0.004, fname, fill("#ffffff"))
    c.drawString(status, ax + ar * 1.5, cy + sw * 0.045, font(sw * 0.033, "regular"), fill("#8f939c"))
    # icon gọi (chung chung)
    gx = g["sr"] - sw * 0.1
    c.drawCircle(gx, cy, sw * 0.022, stroke("#2e7cf6", sw * 0.008))
    c.drawLine(g["sl"], hy1, g["sr"], hy1, stroke("#26282e", max(1.0, sw * 0.003)))
    # thanh nhập
    iy0 = g["sb"] - sw * 0.16
    c.drawRect(skia.Rect.MakeLTRB(g["sl"], iy0, g["sr"], g["sb"]), fill("#16171b"))
    pcx, pcy = g["sl"] + sw * 0.075, iy0 + sw * 0.065
    c.drawCircle(pcx, pcy, sw * 0.035, fill("#2a2c33"))
    c.drawLine(pcx - sw * 0.016, pcy, pcx + sw * 0.016, pcy, stroke("#9aa0aa", sw * 0.007))
    c.drawLine(pcx, pcy - sw * 0.016, pcx, pcy + sw * 0.016, stroke("#9aa0aa", sw * 0.007))
    c.drawPath(rrect(g["sl"] + sw * 0.13, pcy - sw * 0.04, g["sr"] - sw * 0.14, pcy + sw * 0.04, sw * 0.04),
               fill("#24262c"))
    c.drawString("Message…", g["sl"] + sw * 0.16, pcy + sw * 0.013, font(sw * 0.036, "regular"), fill("#737882"))
    sx = g["sr"] - sw * 0.075
    c.drawCircle(sx, pcy, sw * 0.038, fill("#2e7cf6"))
    c.drawPath(poly([(sx - sw * 0.016, pcy - sw * 0.018), (sx + sw * 0.02, pcy), (sx - sw * 0.016, pcy + sw * 0.018),
                     (sx - sw * 0.008, pcy)]), fill("#ffffff"))
    c.restore()
    draw_notch(c, g)
    images: dict[str, skia.Image] = {"base": base.makeImageSnapshot()}
    if hand:
        hs, hc = _surface(W, H)
        phone_hand_front(hc, g, H, skin)
        images["hand"] = hs.makeImageSnapshot()
    # tin nhắn
    msgs = [m for m in (d.get("messages") or []) if isinstance(m, dict) and str(m.get("text") or "").strip()]
    if not msgs:
        msgs = [{"from": "them", "text": "Who is on the night shift tonight?"}, {"from": "me", "text": "Just me, alone."}]
    area_top, area_bot = hy1 + sw * 0.04, iy0 - sw * 0.03
    maxw = sw * 0.72
    lay: list[tuple[str, float, float, bool, float]] = []   # key, x, y(content), me, t_pop
    y = 0.0
    prev = None
    pop = d.get("pop", True) is not False
    t_first = float(d.get("first_at", 0.45))
    gap_t = float(d.get("interval", 0.55))
    for i, mm in enumerate(msgs):
        me = str(mm.get("from", "them")).lower() in ("me", "toi", "tôi", "out", "self")
        img = _bubble_image(str(mm.get("text")), me, maxw, H, cols)
        key = f"b{i}"
        images[key] = img
        if prev is not None:
            y += 0.008 * H if prev == me else 0.02 * H
        x = g["sr"] - sw * 0.04 - img.width() if me else g["sl"] + sw * 0.04
        lay.append((key, x, y, me, (t_first + i * gap_t) if pop else -1.0))
        y += img.height()
        prev = me
    area_h = area_bot - area_top

    def scroll_at(t: float) -> float:
        bottom = 0.0
        for key, x, yy, me, tp in lay:
            if t >= tp:
                bottom = yy + images[key].height()
        target = max(0.0, bottom - area_h)
        # trượt mượt 0.25s sau khi tin mới xuất hiện
        prev_bottom = 0.0
        for key, x, yy, me, tp in lay:
            if t >= tp + 0.25:
                prev_bottom = yy + images[key].height()
        prev_target = max(0.0, prev_bottom - area_h)
        last_tp = max([tp for *_x, tp in lay if t >= tp] or [-1.0])
        u = ease_out(min(1.0, max(0.0, (t - last_tp) / 0.25)))
        return prev_target + (target - prev_target) * u

    def draw_chat(layer: Layer, cv: skia.Canvas, t: float, a: float) -> None:
        dy = (1 - ease_out(layer.entering(t))) * 0.08 * H
        p = skia.Paint(Alphaf=a)
        cv.drawImage(layer.images["base"], 0, dy, LIN, p)
        off = scroll_at(t)
        cv.save()
        cv.clipRect(skia.Rect.MakeLTRB(g["sl"], area_top + dy, g["sr"], area_bot + dy), skia.ClipOp.kIntersect, True)
        for key, x, yy, me, tp in lay:
            if t < tp:
                continue
            im = layer.images[key]
            u = min(1.0, (t - tp) / 0.3) if tp >= 0 else 1.0
            sc = 0.6 + 0.4 * ease_out_back(u)
            ax_ = x + (im.width() if me else 0)
            ay_ = area_top + yy - off + im.height() + dy
            cv.save()
            cv.translate(ax_, ay_)
            cv.scale(sc, sc)
            cv.drawImage(im, -im.width() if me else 0, -im.height(), LIN, skia.Paint(Alphaf=a * min(1.0, u * 2.5)))
            cv.restore()
        cv.restore()
        if "hand" in layer.images:
            cv.drawImage(layer.images["hand"], 0, dy, LIN, p)

    return Layer(None, 0.15, end - 0.05, 0.3, 0.25, kind="phone_chat", draw_fn=draw_chat, images=images,
                 backdrop="blur", backdrop_dim=0.45, data=d)


def phone_bank_layer(ov: Overlay, W: int, H: int, end: float) -> Layer:
    d = dict(ov.data or {})
    g = phone_geometry(W, H, float(d.get("phone_h", 0.86)))
    sw = g["sw"]
    bank = nfc(ov.title or "HARBOR BANK")
    holder = nfc(ov.subtitle or "ACCOUNT HOLDER")
    s, c = _surface(W, H)
    if d.get("hand"):
        phone_hand_back(c, g, H, d.get("sleeve") or BRAND_GREEN, d.get("skin") or SKIN)
    scr = draw_phone_frame(c, g, "#f3f5f8")
    c.save()
    c.clipPath(scr, skia.ClipOp.kIntersect, True)
    hy1 = g["st"] + sw * 0.78
    grad = skia.GradientShader.MakeLinear([skia.Point(g["sl"], g["st"]), skia.Point(g["sr"], hy1)],
                                          [color("#1e5fd0"), color("#3aa0f0")])
    c.drawRect(skia.Rect.MakeLTRB(g["sl"], g["st"], g["sr"], hy1), skia.Paint(AntiAlias=True, Shader=grad))
    # sóng trang trí
    for k in range(3):
        wv = skia.Path()
        wv.moveTo(g["sl"], hy1 - sw * (0.12 + 0.06 * k))
        wv.cubicTo(g["sl"] + sw * 0.35, hy1 - sw * (0.22 + 0.05 * k), g["sl"] + sw * 0.65, hy1 - sw * (0.02 + 0.05 * k),
                   g["sr"], hy1 - sw * (0.15 + 0.05 * k))
        c.drawPath(wv, stroke("#ffffff", sw * 0.006, 0.12))
    _status_bar(c, g["sl"], g["st"], g["sr"], sw, nfc(str(d.get("time") or "02:14")), "#ffffff")
    lx = g["sl"] + sw * 0.07
    # logo chung chung: vòng tròn + sóng (không phải logo thật)
    lr = sw * 0.045
    lcy = g["st"] + sw * 0.18
    c.drawCircle(lx + lr, lcy, lr, fill("#ffffff"))
    wv = skia.Path()
    wv.moveTo(lx + lr * 0.35, lcy + lr * 0.1)
    wv.quadTo(lx + lr * 0.7, lcy - lr * 0.45, lx + lr, lcy + lr * 0.05)
    wv.quadTo(lx + lr * 1.3, lcy + lr * 0.5, lx + lr * 1.65, lcy - lr * 0.1)
    c.drawPath(wv, stroke("#1e5fd0", lr * 0.22))
    c.drawString(bank, lx + lr * 2.5, lcy + sw * 0.016, fit_font(bank, "bold", sw * 0.046, sw * 0.65), fill("#ffffff"))
    c.drawString("Checking account", lx, g["st"] + sw * 0.34, font(sw * 0.036, "semibold"), fill("#dbe8ff"))
    acct = nfc(str(d.get("account_masked") or "•••• •••• 2468"))
    c.drawString(acct, lx, g["st"] + sw * 0.39, font(sw * 0.036, "regular"), fill("#dbe8ff"))
    c.drawString("Available balance", lx, g["st"] + sw * 0.49, font(sw * 0.034, "regular"), fill("#e6efff"))
    bal = nfc(str(d.get("balance") or "$1,250.00"))
    c.drawString(bal, lx, g["st"] + sw * 0.6, fit_font(bal, "extrabold", sw * 0.1, sw * 0.84), fill("#ffffff"))
    c.drawString(holder, lx, g["st"] + sw * 0.68, font(sw * 0.034, "semibold"), fill("#e6efff"))
    # danh sách giao dịch
    y = hy1 + sw * 0.03
    c.drawPath(rrect(g["sl"] + sw * 0.03, y, g["sr"] - sw * 0.03, g["sb"] - sw * 0.04, sw * 0.04), fill("#ffffff"))
    y += sw * 0.085
    c.drawString("Recent transactions", lx, y, font(sw * 0.042, "bold"), fill("#1d2433"))
    tx_list = d.get("transactions") or [
        {"label": "Transfer out", "amount": "-$50.00", "date": "03/14 02:13"},
        {"label": "Night shift pay", "amount": "+$450.00", "date": "03/10 08:00"},
        {"label": "Rent payment", "amount": "-$180.00", "date": "03/05 19:42"},
    ]
    y += sw * 0.04
    f_lab = font(sw * 0.038, "semibold")
    f_dt = font(sw * 0.03, "regular")
    f_amt = font(sw * 0.04, "bold")
    for txn in tx_list[:6]:
        if not isinstance(txn, dict):
            continue
        amt = nfc(str(txn.get("amount") or ""))
        neg = amt.strip().startswith(("-", "−"))
        rowh = sw * 0.14
        if y + rowh > g["sb"] - sw * 0.06:
            break
        ic = sw * 0.035
        c.drawCircle(lx + ic, y + rowh * 0.45, ic, fill("#fde6e4" if neg else "#e3f4e7"))
        arrow = poly([(lx + ic, y + rowh * 0.45 + (ic * 0.5 if neg else -ic * 0.5)),
                      (lx + ic - ic * 0.45, y + rowh * 0.45), (lx + ic + ic * 0.45, y + rowh * 0.45)])
        c.drawPath(arrow, fill("#d0302a" if neg else "#2f9a4a"))
        lab = nfc(str(txn.get("label") or ""))
        c.drawString(lab, lx + ic * 2.7, y + rowh * 0.42, fit_font(lab, "semibold", sw * 0.038, sw * 0.42), fill("#1d2433"))
        if txn.get("date"):
            c.drawString(nfc(str(txn["date"])), lx + ic * 2.7, y + rowh * 0.72, f_dt, fill("#8a92a3"))
        text(c, amt, g["sr"] - sw * 0.08, y + rowh * 0.5, f_amt, "#d0302a" if neg else "#2f9a4a", align="r")
        c.drawLine(lx, y + rowh * 0.95, g["sr"] - sw * 0.08, y + rowh * 0.95, stroke("#e6e9ef", max(1.0, sw * 0.003)))
        y += rowh
    c.restore()
    draw_notch(c, g)
    if d.get("hand"):
        phone_hand_front(c, g, H, d.get("skin") or SKIN)
    return Layer(s.makeImageSnapshot(), 0.15, end - 0.05, 0.3, 0.25, (0.0, 0.0), kind="phone_bank",
                 slide=(0.0, 0.08 * H), backdrop="blur", backdrop_dim=0.45, data=d)


# ====================================================================== chân dung (ảnh thẻ)
def character_portrait(spec: str | None, w: int, h: int) -> skia.Image | None:
    """Ảnh thẻ từ puppet: 'character:<id>' / 'archetype:<id>' / '<id>'. None nếu không có."""
    if not spec or spec == "blank":
        return None
    cid = spec.split(":", 1)[1] if ":" in spec else spec
    try:   # gói A (nếu đã có): ảnh thẻ đẹp với biểu cảm
        from . import puppetgen  # type: ignore
        fn = getattr(puppetgen, "render_portrait", None)
        if fn is not None:
            img = fn(cid, size=(w, h))
            if img is not None:
                return img.makeRasterImage() if img.isTextureBacked() else img
    except Exception as e:  # noqa: BLE001
        log.debug("render_portrait(%s) không dùng được: %s", cid, e)
    try:
        from .backend import get_backend
        from .rig import Rig
        rig = Rig.load(cid)
        if rig is None:
            return None
        be = get_backend()
        surf = be.surface(w, h)
        c = surf.getCanvas()
        c.clear(color("#cfd8df"))
        grad = skia.GradientShader.MakeRadial(skia.Point(w * 0.5, h * 0.35), h * 0.8,
                                              [color("#e3e9ee"), color("#aab6c0")])
        c.drawPaint(skia.Paint(Shader=grad))
        if rig.head_box:
            l, t, r, b = rig.head_box
        else:
            hx, hy = rig.head_center()
            l, t, r, b = hx - 90, hy - 110, hx + 90, hy + 110
        hh = b - t
        top = t - 0.22 * hh
        bottom = b + 0.85 * hh
        sc = h / (bottom - top)
        cx = (l + r) / 2
        m = skia.Matrix.Translate(w / 2, 0)
        m.preScale(sc, sc)
        m.preTranslate(-cx, -top)
        rig.draw(c, m, {}, {"eyes": "open", "brows": "neutral", "mouth": "X"})
        img = surf.makeImageSnapshot()
        return img.makeRasterImage() if img.isTextureBacked() else img
    except Exception as e:  # noqa: BLE001 — ảnh thẻ là phụ, không làm sập
        log.warning("Không vẽ được ảnh thẻ '%s': %s", spec, e)
        return None


def _silhouette(c: skia.Canvas, l: float, t: float, w: float, h: float) -> None:
    c.drawRect(skia.Rect.MakeXYWH(l, t, w, h), fill("#d9d4ca"))
    cx = l + w / 2
    c.drawCircle(cx, t + h * 0.4, w * 0.24, fill("#e8833a"))
    c.drawPath(rrect(cx - w * 0.38, t + h * 0.68, cx + w * 0.38, t + h * 1.1, w * 0.3), fill("#e8833a"))
    text(c, "?", cx, t + h * 0.47, font(w * 0.26, "extrabold"), "#ffffff", align="c")


# ====================================================================== tờ tìm người mất tích
def render_missing_poster(ov: Overlay, W: int, H: int) -> skia.Image:
    d = dict(ov.data or {})
    variant = str(d.get("variant") or "clean")
    rng = random.Random(sum(ord(ch) for ch in ov.title or "x"))
    ph = 0.84 * H
    pw = min(0.42 * W, ph * 0.76)
    s, c = _surface(W, H)
    if variant == "wall":   # tường bê tông phía sau
        c.clear(color("#5d5a55"))
        for _ in range(260):
            x, y = rng.uniform(0, W), rng.uniform(0, H)
            c.drawCircle(x, y, rng.uniform(1, 5) * H / 1080, fill(rng.choice(["#4a4743", "#6c6862"]), 0.5))
        for k in range(1, 4):
            c.drawLine(0, H * k / 4 + rng.uniform(-6, 6), W, H * k / 4, stroke("#4a4743", 2, 0.6))
        vg = skia.GradientShader.MakeRadial(skia.Point(W / 2, H / 2), W * 0.6,
                                            [color("#000000", 0.0), color("#000000", 0.6)])
        c.drawPaint(skia.Paint(Shader=vg))
    x0, y0 = (W - pw) / 2, (H - ph) / 2
    c.save()
    c.translate(x0, y0)
    # mép giấy (rách: răng cưa đáy + cạnh phải)
    pts = [(0, 0), (pw, 0)]
    if variant == "torn":
        n = 18
        for i in range(1, n):
            pts.append((pw - rng.uniform(0, 0.02 * pw) * (i % 2), ph * 0.55 + ph * 0.45 * i / n))
        for i in range(n, -1, -1):
            pts.append((pw * i / n, ph - rng.uniform(0, 0.035 * ph)))
    else:
        pts += [(pw, ph), (0, ph)]
    paper = poly(pts)
    c.save()
    c.translate(0.004 * H, 0.012 * H)
    c.drawPath(paper, _shadow_paint(0.55, 0.014 * H))
    c.restore()
    grad = skia.GradientShader.MakeLinear([skia.Point(0, 0), skia.Point(pw, ph)],
                                          [color("#f6f3ec"), color("#e8e3d8")])
    c.drawPath(paper, skia.Paint(AntiAlias=True, Shader=grad))
    c.save()
    c.clipPath(paper, skia.ClipOp.kIntersect, True)
    # dải đầu đỏ
    hy0, hh = ph * 0.045, ph * 0.13
    c.drawRect(skia.Rect.MakeXYWH(pw * 0.05, hy0, pw * 0.9, hh), fill("#c8352e"))
    head = _upper(d.get("header") or "MISSING PERSON")
    fh = fit_font(head, "extrabold", hh * 0.5, pw * 0.84)
    text(c, head, pw / 2, hy0 + hh / 2 + fh.getSize() * 0.36, fh, "#ffffff", align="c")
    # ảnh thẻ
    phw = pw * 0.44
    phh = phw * 4 / 3
    px, py = (pw - phw) / 2, hy0 + hh + ph * 0.035
    c.drawRect(skia.Rect.MakeXYWH(px - pw * 0.012, py - pw * 0.012, phw + pw * 0.024, phh + pw * 0.024), fill("#ffffff"))
    c.drawRect(skia.Rect.MakeXYWH(px - pw * 0.012, py - pw * 0.012, phw + pw * 0.024, phh + pw * 0.024),
               stroke("#cfc8bb", max(1.0, H / 900)))
    portrait = character_portrait(d.get("photo"), int(phw), int(phh))
    if portrait is not None:
        c.drawImageRect(portrait, skia.Rect.MakeXYWH(px, py, phw, phh), LIN)
        # ảnh in hơi bạc màu
        c.drawRect(skia.Rect.MakeXYWH(px, py, phw, phh), fill("#efe6d0", 0.12))
    else:
        _silhouette(c, px, py, phw, phh)
    # chữ
    y = py + phh + ph * 0.07
    name = nfc(ov.title or "UNIDENTIFIED")
    age = nfc(ov.subtitle or "")
    line1 = f"{name}, {age}" if age and len(age) < 14 else name
    fn = fit_font(line1, "extrabold", ph * 0.048, pw * 0.86)
    text(c, line1, pw / 2, y, fn, "#1d1a17", align="c")
    if age and line1 == name:
        y += ph * 0.04
        text(c, age, pw / 2, y, font(ph * 0.03, "bold"), "#1d1a17", align="c")
    desc = nfc(d.get("desc") or "Grey jacket, rode a motorbike, lost contact after a night shift.")
    fd = font(ph * 0.024, "semibold")
    for ln in wrap_text(desc, fd, pw * 0.82, 3):
        y += ph * 0.036
        text(c, ln, pw / 2, y, fd, "#6f6a62", align="c")
    dt = nfc(d.get("datetime") or "")
    if dt:
        y += ph * 0.045
        text(c, dt, pw / 2, y, fit_font(dt, "bold", ph * 0.028, pw * 0.86), "#c8352e", align="c")
    phone = nfc(d.get("phone") or "Contact: 555-01••")
    y += ph * 0.045
    text(c, phone, pw / 2, y, fit_font(phone, "extrabold", ph * 0.03, pw * 0.86), "#1d1a17", align="c")
    if variant == "crumpled":   # nếp gấp
        for _ in range(7):
            x1, y1 = rng.uniform(0, pw), rng.uniform(0, ph)
            x2, y2 = x1 + rng.uniform(-pw, pw) * 0.6, y1 + rng.uniform(-ph, ph) * 0.4
            c.drawLine(x1, y1, x2, y2, stroke("#ffffff", 0.003 * H, 0.5))
            c.drawLine(x1 + 3, y1 + 3, x2 + 3, y2 + 3, stroke("#8a8070", 0.002 * H, 0.25))
        for _ in range(4):
            q = [(rng.uniform(0, pw), rng.uniform(0, ph)) for _ in range(3)]
            c.drawPath(poly(q), fill("#000000", 0.035))
    c.restore()
    tape(c, pw * 0.06, ph * 0.0, pw * 0.22, ph * 0.045, -32)
    tape(c, pw * 0.94, ph * 0.0, pw * 0.22, ph * 0.045, 32)
    c.restore()
    return s.makeImageSnapshot()


# ====================================================================== bản đồ
def _path_from(points: list, l: float, t: float, w: float, h: float) -> skia.Path:
    from .skutil import smooth
    pts = [(l + float(p[0]) * w, t + float(p[1]) * h) for p in points]
    return smooth(pts, close=False) if len(pts) > 2 else poly(pts, close=False)


def _path_point(path: skia.Path, frac: float) -> tuple[float, float, float]:
    meas = skia.PathMeasure(path, False)
    L = meas.getLength()
    pos, tan = meas.getPosTan(L * frac)
    return pos.x(), pos.y(), math.degrees(math.atan2(tan.y(), tan.x()))


def map_card_layer(ov: Overlay, W: int, H: int, end: float) -> Layer:
    d = dict(ov.data or {})
    rng = random.Random(7)
    s, c = _surface(W, H)
    c.clear(color("#1d1f24"))
    for _ in range(9):   # khói than
        p = fill("#3a3d44", 0.18)
        p.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 0.08 * H))
        c.drawCircle(rng.uniform(0, W), rng.uniform(0, H), rng.uniform(0.1, 0.25) * H, p)
    cw, ch = 0.70 * W, 0.74 * H
    cx0, cy0 = (W - cw) / 2, (H - ch) / 2 + 0.01 * H
    card = rrect(cx0, cy0, cx0 + cw, cy0 + ch, 0.01 * H)
    c.save()
    c.translate(0, 0.012 * H)
    c.drawPath(card, _shadow_paint(0.6, 0.02 * H))
    c.restore()
    c.drawPath(card, fill("#efe7d4"))
    c.save()
    c.clipPath(card, skia.ClipOp.kIntersect, True)
    stripe = 0.022 * W
    x = cx0
    i = 0
    while x < cx0 + cw:
        if i % 2:
            c.drawRect(skia.Rect.MakeXYWH(x, cy0, stripe, ch), fill("#d9cfb8", 0.22))
        x += stripe
        i += 1
    # vùng bản đồ
    ml, mt, mw, mh = cx0 + 0.03 * W, cy0 + 0.16 * H, cw - 0.06 * W, ch - 0.2 * H
    # khối nhà / cây
    for _ in range(26):
        bx, by = ml + rng.uniform(0, mw), mt + rng.uniform(0, mh)
        bw_, bh_ = rng.uniform(0.02, 0.05) * W, rng.uniform(0.02, 0.05) * H
        c.drawPath(rrect(bx, by, bx + bw_, by + bh_, 0.003 * H), fill("#ddd1b6", 0.9))
    for _ in range(30):
        c.drawCircle(ml + rng.uniform(0, mw), mt + rng.uniform(0, mh), rng.uniform(0.006, 0.012) * H, fill("#9fb58a", 0.7))
    water_label = d.get("water_label")
    wpath_pts = d.get("water_path") or ([[0, 0.22], [0.2, 0.3], [0.45, 0.18], [0.7, 0.28], [1, 0.2]]
                                        if water_label else None)
    if wpath_pts:
        wp = _path_from(wpath_pts, ml - 0.05 * W, mt, mw + 0.1 * W, mh)
        c.drawPath(wp, stroke("#4a86c0", 0.04 * H))
        c.drawPath(wp, stroke("#6fa4d6", 0.012 * H, 0.6, PathEffect=skia.DashPathEffect.Make([0.03 * H, 0.05 * H], 0)))
        if water_label:
            x, y, ang = _path_point(wp, 0.3)
            c.save()
            c.translate(x, y - 0.03 * H)
            c.rotate(ang)
            text(c, nfc(water_label), 0, 0, hand_font(0.022 * H), "#2f5f92", align="c")
            c.restore()
    road = _path_from(d.get("road_path") or [[0, 0.66], [0.3, 0.56], [0.62, 0.7], [1, 0.6]], ml - 0.05 * W, mt,
                      mw + 0.1 * W, mh)
    c.drawPath(road, stroke("#6f6d69", 0.068 * H))
    c.drawPath(road, stroke("#8c8a86", 0.058 * H))
    c.drawPath(road, stroke("#e3b43a", 0.005 * H, PathEffect=skia.DashPathEffect.Make([0.025 * H, 0.018 * H], 0)))
    if d.get("road_label") or True:
        rl = nfc(d.get("road_label") or "Route 8")
        x, y, ang = _path_point(road, 0.18)
        c.save()
        c.translate(x, y + 0.058 * H)
        c.rotate(ang)
        spaced_text(c, _upper(rl), 0, 0, font(0.019 * H, "bold"), "#5a5650", 0.002 * H, align="c")
        c.restore()
    c.restore()
    c.drawPath(card, stroke("#b9ad94", max(1.0, H / 800)))
    # tiêu đề
    title = nfc(ov.title or "Incident area")
    c.drawString(title, cx0 + 0.03 * W, cy0 + 0.075 * H, fit_font(title, "extrabold", 0.045 * H, cw * 0.7), fill("#1f2328"))
    if ov.subtitle:
        spaced_text(c, _upper(ov.subtitle), cx0 + 0.03 * W, cy0 + 0.115 * H, font(0.018 * H, "semibold"), "#7a7266",
                    0.003 * H)
    # điểm đánh dấu
    mk = d.get("marker") if isinstance(d.get("marker"), dict) else {}
    mx = ml + float(mk.get("x", 0.58)) * mw
    my = mt + float(mk.get("y", 0.6)) * mh
    mlabel = nfc(mk.get("label") or "Incident point · 03:00")
    lx, ly = mx + 0.07 * W * (1 if mx < cx0 + cw * 0.7 else -1), my - 0.11 * H
    c.drawLine(mx, my, lx, ly + 0.01 * H, stroke("#d0302a", 0.003 * H,
                                                PathEffect=skia.DashPathEffect.Make([0.01 * H, 0.008 * H], 0)))
    fl = font(0.026 * H, "extrabold")
    tw = fl.measureText(mlabel)
    tx = lx if lx > mx else lx - tw
    c.drawPath(rrect(tx - 0.01 * H, ly - 0.032 * H, tx + tw + 0.01 * H, ly + 0.012 * H, 0.006 * H), fill("#fff8ec", 0.95))
    c.drawString(mlabel, tx, ly, fl, fill("#d0302a"))
    c.drawCircle(mx, my, 0.016 * H, fill("#ffffff"))
    c.drawCircle(mx, my, 0.011 * H, fill("#d0302a"))
    tag = d.get("tag")
    if tag:
        tg = _upper(tag)
        ft = font(0.019 * H, "bold")
        tw = spaced_width(tg, ft, 0.002 * H)
        bx, by = cx0 + 0.03 * W, cy0 + ch - 0.07 * H
        c.drawPath(rrect(bx, by, bx + tw + 0.04 * H, by + 0.042 * H, 0.021 * H), fill("#2f8a57"))
        spaced_text(c, tg, bx + 0.02 * H, by + 0.021 * H + 0.019 * H * 0.36, ft, "#ffffff", 0.002 * H)
    images = {"base": s.makeImageSnapshot()}

    def draw(layer: Layer, cv: skia.Canvas, t: float, a: float) -> None:
        u = t / max(end, 0.1)
        sc = 1.0 + 0.035 * u
        cv.save()
        cv.translate(mx, my)
        cv.scale(sc, sc)
        cv.translate(-mx, -my)
        cv.drawImage(layer.images["base"], 0, 0, LIN, skia.Paint(Alphaf=a))
        ph_ = (t % 1.2) / 1.2
        cv.drawCircle(mx, my, 0.016 * H * (1 + 2.2 * ph_), stroke("#d0302a", 0.004 * H, a * (1 - ph_)))
        cv.restore()

    return Layer(None, 0.0, end + 0.5, 0.3, 0.0, kind="map_card", draw_fn=draw, images=images, data=d)


# ====================================================================== timeline
def _faceless_figure(w: float, h: float, body: str, collar: str, hl: bool) -> skia.Image:
    """Hình nhân không mặt: đầu tròn + cổ + thân vai tròn loe nhẹ, cổ áo chữ V vàng, viền sáng mảnh."""
    s, c = _surface(w, h)
    cx = w / 2
    hr = w * 0.23
    col = shade(body, 0.22) if hl else body
    rim = shade(col, 0.25)
    top = hr * 2.55                      # vai
    neck = skia.Rect.MakeLTRB(cx - hr * 0.36, hr * 1.7, cx + hr * 0.36, top + hr * 0.2)
    c.drawRect(neck, fill(shade(col, -0.15)))
    p = skia.Path()
    p.moveTo(cx - w * 0.46, h)
    p.lineTo(cx - w * 0.4, top + w * 0.2)
    p.quadTo(cx - w * 0.38, top, cx - w * 0.2, top)
    p.lineTo(cx + w * 0.2, top)
    p.quadTo(cx + w * 0.38, top, cx + w * 0.4, top + w * 0.2)
    p.lineTo(cx + w * 0.46, h)
    p.close()
    c.drawPath(p, fill(col))
    c.drawPath(p, stroke(rim, max(1.0, w * 0.012), 0.7))
    c.drawCircle(cx, hr * 1.05, hr, fill(col))
    c.drawCircle(cx, hr * 1.05, hr, stroke(rim, max(1.0, w * 0.012), 0.7))
    c.drawCircle(cx - hr * 0.35, hr * 0.7, hr * 0.28, fill("#ffffff", 0.07))
    c.drawPath(poly([(cx - w * 0.17, top), (cx, top + w * 0.24), (cx + w * 0.17, top)]), fill(collar))
    c.drawPath(poly([(cx - w * 0.09, top), (cx, top + w * 0.13), (cx + w * 0.09, top)]), fill(col))
    return s.makeImageSnapshot()


def timeline_layer(ov: Overlay, W: int, H: int, end: float) -> Layer:
    d = dict(ov.data or {})
    items = [it if isinstance(it, dict) else {"label": str(it)} for it in (d.get("items") or [])]
    if not items:
        items = [{"label": y} for y in ("2015", "2017", "2019", "2021")] + [{"label": "Now", "highlight": True}]
    if not any(it.get("highlight") for it in items):
        items[-1]["highlight"] = True
    s, c = _surface(W, H)
    grad = skia.GradientShader.MakeRadial(skia.Point(W / 2, H * 0.45), W * 0.7,
                                          [color("#18203a"), color("#0f1320"), color("#080a12")])
    c.drawPaint(skia.Paint(Shader=grad))
    title = nfc(ov.title or "Everyone who worked the night shift")
    text(c, title, W / 2, H * 0.14, fit_font(title, "extrabold", 0.056 * H, W * 0.8), "#efe5d0", align="c")
    if ov.subtitle:
        spaced_text(c, _upper(ov.subtitle), W / 2, H * 0.195, font(0.02 * H, "semibold"), "#8a8f9c", 0.004 * H, align="c")
    steps = int(d.get("progress_steps", 6) or 6)
    done = int(d.get("progress_done", steps // 2) or 0)
    seg_w, seg_h, gap = 0.045 * W, 0.009 * H, 0.008 * W
    tot = steps * seg_w + (steps - 1) * gap
    for i in range(steps):
        x = (W - tot) / 2 + i * (seg_w + gap)
        c.drawPath(rrect(x, H * 0.235, x + seg_w, H * 0.235 + seg_h, seg_h / 2),
                   fill("#c8352e" if i < done else "#5a5e68"))
    n = len(items)
    base_y = H * 0.70
    c.drawLine(W * 0.06, base_y, W * 0.94, base_y, stroke("#c8352e", 0.005 * H))
    images: dict[str, skia.Image] = {"bg": s.makeImageSnapshot()}
    fw = min(0.085 * W, 0.7 * W / max(1, n))
    fh = 0.3 * H
    spacing = min(0.16 * W, 0.84 * W / max(1, n))
    xs = [W / 2 + (i - (n - 1) / 2) * spacing for i in range(n)]
    ftag = font(0.024 * H, "extrabold")
    for i, it in enumerate(items):
        hl = bool(it.get("highlight"))
        images[f"f{i}"] = _faceless_figure(fw, fh, "#33363f", "#d9b44a", hl)
        lab = nfc(str(it.get("label") or ""))
        f = fit_font(lab, "extrabold", 0.024 * H, spacing * 0.86)
        tw = f.measureText(lab) + 0.03 * H
        ts, tc = _surface(tw, 0.05 * H)
        tc.drawPath(rrect(0, 0, tw, 0.05 * H, 0.008 * H), fill("#c8352e" if hl else "#efe5d0"))
        text(tc, lab, tw / 2, 0.025 * H + f.getSize() * 0.36, f, "#ffffff" if hl else "#1f2328", align="c")
        images[f"t{i}"] = ts.makeImageSnapshot()
    t_first = float(d.get("first_at", 0.35))
    step_t = float(d.get("interval", 0.35))

    def draw(layer: Layer, cv: skia.Canvas, t: float, a: float) -> None:
        cv.drawImage(layer.images["bg"], 0, 0, NEAREST, skia.Paint(Alphaf=a))
        for i in range(n):
            u = (t - (t_first + i * step_t)) / 0.35
            if u <= 0:
                continue
            e = ease_out_back(min(1.0, u))
            al = a * min(1.0, u * 1.6)
            fi = layer.images[f"f{i}"]
            ti = layer.images[f"t{i}"]
            dy = (1 - e) * 0.05 * H
            cv.drawImage(fi, xs[i] - fi.width() / 2, base_y - fi.height() - 0.004 * H + dy, LIN, skia.Paint(Alphaf=al))
            cv.drawImage(ti, xs[i] - ti.width() / 2, base_y + 0.03 * H + dy * 0.5, LIN, skia.Paint(Alphaf=al))

    return Layer(None, 0.0, end + 0.5, 0.3, 0.0, kind="timeline", draw_fn=draw, images=images, data=d)


# ====================================================================== HUD lô 3 (info_card + data.variant)
# Schema không có OverlayKind riêng cho các HUD này -> dùng kind "info_card" với data.variant:
#   "knot_counter" : pill trên-phải: icon bùa + chấm (còn/đã dùng) + "xN" + chú thích ("KNOTS LEFT").
#                    data: total(5), left(3), from(None) + change_at(s) -> mất 1 nút có hiệu ứng pop; caption.
#   "countdown"    : thẻ kem, pill tối nhãn (title | data.label | "HIDE AND SEEK"), vòng tiến độ + số đếm ngược,
#                    chú thích (subtitle | data.caption | "SECONDS LEFT"). data: start(10), end(start-dur), rate(1/s),
#                    position center|tl|tr|bl|br (center làm tối nền).
#   "live_replay"  : pill trên-trái (icon tua lại đỏ + @handle từ title | data.handle + tag "REPLAY"), timestamp
#                    trên-phải (HH:MM:SS chạy theo giây), thanh tiến độ đỏ dưới đáy. data: timestamp, progress [p0, p1],
#                    tag, running (true).
# Chữ nhãn lấy từ title/subtitle/data (ngôn ngữ truyện); chú thích mặc định cố định bằng tiếng Anh.
HUD_VARIANTS = ("knot_counter", "countdown", "live_replay")


def _charm_icon(c: skia.Canvas, cx: float, cy: float, r: float) -> None:
    body = rrect(cx - r * 0.62, cy - r * 0.55, cx + r * 0.62, cy + r * 0.95, r * 0.45)
    c.drawPath(body, fill("#c8352e"))
    c.drawPath(rrect(cx - r * 0.18, cy - r * 0.3, cx + r * 0.18, cy + r * 0.7, r * 0.06), fill("#f6efe0"))
    c.drawPath(rrect(cx - r * 0.75, cy - r * 0.78, cx + r * 0.75, cy - r * 0.48, r * 0.15), fill("#a82a24"))
    c.drawCircle(cx, cy - r * 0.63, r * 0.16, fill("#e8d9b0"))
    c.drawArc(skia.Rect.MakeLTRB(cx - r * 0.25, cy - r * 1.15, cx + r * 0.25, cy - r * 0.62), 180, 180, False,
              stroke("#e8d9b0", r * 0.1))


def _knot_pill(total: int, left: int, caption: str, H: int) -> tuple[skia.Image, list[float], float]:
    """Ảnh pill + toạ độ x tâm từng chấm + y tâm chấm (để vẽ pop)."""
    ph = 0.074 * H
    pad = ph * 0.38
    ic = ph * 0.32
    dr = ph * 0.13
    gap = dr * 1.15
    fnum = font(ph * 0.52, "extrabold")
    fcap = font(ph * 0.21, "bold")
    num = f"x{left}"
    cap = _upper(caption)
    capw = spaced_width(cap, fcap, ph * 0.03)
    dots_w = total * dr * 2 + (total - 1) * gap
    w = pad + ic * 2 + pad * 0.7 + dots_w + pad * 0.8 + fnum.measureText(num) + pad * 0.5 + capw + pad
    sh = 0.02 * H
    s, c = _surface(w + sh * 2, ph + sh * 2)
    c.translate(sh, sh)
    pill = rrect(0, 0, w, ph, ph / 2)
    c.save()
    c.translate(0, 0.006 * H)
    c.drawPath(pill, _shadow_paint(0.5, sh * 0.5))
    c.restore()
    c.drawPath(pill, fill("#141418", 0.86))
    c.drawPath(rrect(1, 1, w - 1, ph - 1, ph / 2), stroke("#ffffff", max(1.0, H / 900), 0.22))
    x = pad
    _charm_icon(c, x + ic, ph / 2, ic)
    x += ic * 2 + pad * 0.7
    xs = []
    for i in range(total):
        cx = x + dr + i * (dr * 2 + gap)
        xs.append(cx + sh)
        if i < left:
            c.drawCircle(cx, ph / 2, dr, fill("#e5413a"))
            c.drawCircle(cx - dr * 0.3, ph / 2 - dr * 0.3, dr * 0.28, fill("#ffffff", 0.6))
        else:
            c.drawCircle(cx, ph / 2, dr * 0.92, stroke("#8a8d96", max(1.5, dr * 0.22)))
    x += dots_w + pad * 0.8
    x += text(c, num, x, ph / 2 + fnum.getSize() * 0.36, fnum, "#ffffff") + pad * 0.5
    spaced_text(c, cap, x, ph / 2 + fcap.getSize() * 0.36, fcap, "#f3c94e", ph * 0.03)
    return s.makeImageSnapshot(), xs, ph / 2 + sh


def knot_counter_layer(ov: Overlay, W: int, H: int, end: float, top: float) -> Layer:
    d = dict(ov.data or {})
    def num(v: Any, default: float) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    total = max(1, min(12, int(num(d.get("total"), 5))))
    left = max(0, min(total, int(num(d.get("left", d.get("count")), 3))))
    caption = str(d.get("caption") or ov.subtitle or "KNOTS LEFT")
    frm = d.get("from")
    frm = None if frm is None or num(frm, -1) < 0 else int(num(frm, 0))
    change_at = num(d.get("change_at"), 0.8)
    img1, xs, dy = _knot_pill(total, left, caption, H)
    images = {"now": img1}
    if frm is not None:
        frm = max(left, min(total, int(frm)))
        images["before"] = _knot_pill(total, frm, caption, H)[0]
    x = W - 0.035 * W - img1.width() + 0.02 * H
    y = top - 0.02 * H

    def draw(layer: Layer, cv: skia.Canvas, t: float, a: float) -> None:
        u = layer.entering(t)
        sy = (1 - ease_out(u)) * -0.05 * H
        before = "before" in layer.images and t < change_at
        img = layer.images["before" if before else "now"]
        k = 1.0
        if "before" in layer.images and change_at <= t < change_at + 0.35:
            k = 1.0 + 0.08 * math.sin((t - change_at) / 0.35 * math.pi)
        cv.save()
        cv.translate(x + img.width() / 2, y + sy + img.height() / 2)
        cv.scale(k, k)
        cv.drawImage(img, -img.width() / 2, -img.height() / 2, LIN, skia.Paint(Alphaf=a))
        cv.restore()
        if "before" in layer.images and change_at <= t < change_at + 0.6 and frm is not None:
            v = (t - change_at) / 0.6
            for i in range(left, frm):     # chấm vừa mất: vòng đỏ nở ra rồi tắt
                cx = x + xs[i]
                cv.drawCircle(cx, y + sy + dy, 0.01 * H + v * 0.03 * H,
                              stroke("#e5413a", max(1.5, 0.006 * H * (1 - v)), a * (1 - v)))

    return Layer(None, 0.15, end - 0.05, 0.35, 0.25, kind="hud_knot_counter", draw_fn=draw, images=images, data=d)


def countdown_layer(ov: Overlay, W: int, H: int, end: float, top: float) -> Layer:
    d = dict(ov.data or {})
    try:
        start = float(d.get("start", 10))
    except (TypeError, ValueError):
        start = 10.0
    try:
        rate = float(d.get("rate", 1.0) or 1.0)
    except (TypeError, ValueError):
        rate = 1.0
    try:
        stop = float(d.get("end", max(0.0, start - rate * end)))
    except (TypeError, ValueError):
        stop = max(0.0, start - rate * end)
    pos = str(d.get("position") or "center")
    center = pos == "center"
    k = 1.0 if center else 0.62
    cw, ch = 0.34 * H * k, 0.44 * H * k
    label = _upper(str(d.get("label") or ov.title or "HIDE AND SEEK"))
    caption = _upper(str(d.get("caption") or ov.subtitle or "SECONDS LEFT"))
    sh = 0.025 * H
    s, c = _surface(cw + sh * 2, ch + sh * 2)
    c.translate(sh, sh)
    card = rrect(0, 0, cw, ch, 0.03 * H * k)
    c.save()
    c.translate(0, 0.01 * H)
    c.drawPath(card, _shadow_paint(0.55, sh * 0.7))
    c.restore()
    c.drawPath(card, fill("#f3ede2"))
    c.drawPath(rrect(0, 0, cw, ch, 0.03 * H * k), stroke("#d9cfbd", max(1.0, H / 700)))
    pill_h = 0.05 * H * k
    fl = fit_font(label, "extrabold", pill_h * 0.46, cw * 0.72)
    pw = spaced_width(label, fl, pill_h * 0.05) + pill_h * 1.2
    c.drawPath(rrect((cw - pw) / 2, 0.035 * H * k, (cw + pw) / 2, 0.035 * H * k + pill_h, pill_h / 2), fill("#1c1d22"))
    spaced_text(c, label, cw / 2, 0.035 * H * k + pill_h / 2 + fl.getSize() * 0.36, fl, "#ffffff", pill_h * 0.05,
                align="c")
    rcx, rcy, rr = cw / 2, ch * 0.53, cw * 0.3
    c.drawCircle(rcx, rcy, rr, stroke("#ddd3c2", rr * 0.16))
    fcap = fit_font(caption, "bold", 0.02 * H * k, cw * 0.8)
    spaced_text(c, caption, cw / 2, ch - 0.04 * H * k, fcap, "#8a8274", 0.003 * H * k, align="c")
    img = s.makeImageSnapshot()
    if center:
        x, y = (W - img.width()) / 2, (H - img.height()) / 2 - 0.03 * H
    else:
        mx, my = 0.035 * W - sh, top - sh
        x = mx if pos.endswith("l") else W - mx - img.width()
        y = my if pos.startswith("t") else H - 0.2 * H - img.height()
    fnum = font(rr * 0.95, "extrabold")
    span = max(1e-6, abs(start - stop)) if start != stop else max(1.0, start)

    def draw(layer: Layer, cv: skia.Canvas, t: float, a: float) -> None:
        u = layer.entering(t)
        sc = 0.85 + 0.15 * ease_out_back(u) if u < 1 else 1.0
        tt = max(0.0, t - layer.t0)
        val = max(stop, start - tt * rate) if start >= stop else min(stop, start + tt * rate)
        frac = max(0.0, min(1.0, val / max(start, 1e-6)))
        n = int(math.ceil(val - 1e-6)) if start >= stop else int(math.floor(val))
        cv.save()
        cv.translate(x + img.width() / 2, y + img.height() / 2)
        cv.scale(sc, sc)
        ox, oy = -img.width() / 2, -img.height() / 2
        cv.drawImage(img, ox, oy, LIN, skia.Paint(Alphaf=a))
        cx, cy = ox + sh + rcx, oy + sh + rcy
        p = stroke("#d0302a", rr * 0.16, a)
        cv.drawArc(skia.Rect.MakeLTRB(cx - rr, cy - rr, cx + rr, cy + rr), -90, -360 * frac, False, p)
        # chấm đầu cung
        ang = math.radians(-90 - 360 * frac)
        cv.drawCircle(cx + math.cos(ang) * rr, cy + math.sin(ang) * rr, rr * 0.12, fill("#ffffff", a))
        txt = str(max(0, n))
        since = abs(start - val) % 1.0          # thời gian (đơn vị số) kể từ nhịp đổi số gần nhất
        pulse = 1.0 + 0.12 * max(0.0, 1 - since * 5) if abs(start - val) > 1e-6 else 1.0
        f = fnum if pulse == 1.0 else font(rr * 0.95 * pulse, "extrabold")
        text(cv, txt, cx, cy + f.getSize() * 0.36, f, "#1c1d22", a, align="c")
        cv.restore()

    return Layer(None, 0.1, end - 0.05, 0.3, 0.25, kind="hud_countdown", draw_fn=draw, images={"card": img},
                 backdrop="blur" if center else None, backdrop_dim=0.3, data=d)


def _rewind_icon(c: skia.Canvas, cx: float, cy: float, r: float) -> None:
    c.drawCircle(cx, cy, r, fill("#e5413a"))
    for dx in (-r * 0.42, r * 0.08):
        c.drawPath(poly([(cx + dx + r * 0.42, cy - r * 0.38), (cx + dx + r * 0.42, cy + r * 0.38), (cx + dx - r * 0.05, cy)]),
                   fill("#ffffff"))


def live_replay_layer(ov: Overlay, W: int, H: int, end: float) -> Layer:
    d = dict(ov.data or {})
    handle = nfc(str(d.get("handle") or ov.title or "@user"))
    if handle and not handle.startswith("@"):
        handle = "@" + handle
    tag = _upper(str(d.get("tag") or "REPLAY"))
    ph = 0.066 * H
    fh = font(ph * 0.4, "bold")
    ft = font(ph * 0.26, "extrabold")
    tagw = spaced_width(tag, ft, ph * 0.03) + ph * 0.5
    w = ph * 0.15 + ph * 0.86 + ph * 0.3 + fh.measureText(handle) + ph * 0.35 + tagw + ph * 0.3
    sh = 0.02 * H
    s, c = _surface(w + sh * 2, ph + sh * 2)
    c.translate(sh, sh)
    pill = rrect(0, 0, w, ph, ph / 2)
    c.save()
    c.translate(0, 0.005 * H)
    c.drawPath(pill, _shadow_paint(0.45, sh * 0.5))
    c.restore()
    c.drawPath(pill, fill("#141418", 0.82))
    _rewind_icon(c, ph * 0.15 + ph * 0.43, ph / 2, ph * 0.36)
    x = ph * 0.15 + ph * 0.86 + ph * 0.3
    x += text(c, handle, x, ph / 2 + fh.getSize() * 0.36, fh, "#ffffff") + ph * 0.35
    th = ph * 0.5
    c.drawPath(rrect(x, (ph - th) / 2, x + tagw, (ph + th) / 2, th * 0.25), fill("#e5413a"))
    spaced_text(c, tag, x + ph * 0.25, ph / 2 + ft.getSize() * 0.36, ft, "#ffffff", ph * 0.03)
    images = {"pill": s.makeImageSnapshot()}
    ts = str(d.get("timestamp") or "02:14:37")
    base = None
    m = re.match(r"^\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s*$", ts)
    if m:
        base = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3) or 0)
    running = d.get("running", True) is not False and base is not None
    prog = d.get("progress") or [0.3, 0.42]
    try:
        p0, p1 = (float(prog[0]), float(prog[1])) if isinstance(prog, (list, tuple)) else (float(prog), float(prog))
    except (TypeError, ValueError, IndexError):
        p0, p1 = 0.3, 0.42
    fts = font(0.036 * H, "bold")
    mx, my = 0.035 * W, 0.045 * H

    def draw(layer: Layer, cv: skia.Canvas, t: float, a: float) -> None:
        # dải tối mờ trên đỉnh cho HUD dễ đọc
        cv.drawRect(skia.Rect.MakeLTRB(0, 0, W, 0.16 * H), skia.Paint(Shader=skia.GradientShader.MakeLinear(
            [skia.Point(0, 0), skia.Point(0, 0.16 * H)], [color("#000000", 0.35 * a), color("#000000", 0.0)])))
        cv.drawImage(layer.images["pill"], mx - sh, my - sh, LIN, skia.Paint(Alphaf=a))
        if base is not None:
            sec = base + (int(t) if running else 0)
            s_ = f"{(sec // 3600) % 24:02d}:{(sec // 60) % 60:02d}:{sec % 60:02d}"
        else:
            s_ = nfc(ts)
        tw = fts.measureText(s_)
        tx, ty = W - mx - tw, my + ph / 2 + fts.getSize() * 0.36
        sp = _shadow_paint(0.6 * a, 0.006 * H)
        cv.drawString(s_, tx + 0.002 * H, ty + 0.003 * H, fts, sp)
        cv.drawString(s_, tx, ty, fts, fill("#ffffff", a))
        # thanh tiến độ đỏ dưới đáy
        u = max(0.0, min(1.0, t / max(end, 0.01)))
        pv = max(0.0, min(1.0, p0 + (p1 - p0) * u))
        bh = 0.008 * H
        by = H - 0.022 * H
        cv.drawRect(skia.Rect.MakeLTRB(0, by, W, by + bh), fill("#ffffff", 0.28 * a))
        cv.drawRect(skia.Rect.MakeLTRB(0, by, W * pv, by + bh), fill("#e5413a", a))
        cv.drawCircle(W * pv, by + bh / 2, bh * 1.3, fill("#e5413a", a))

    return Layer(None, 0.0, end + 0.5, 0.25, 0.0, kind="hud_live_replay", draw_fn=draw, images=images, data=d)


# ====================================================================== HUD lô 4 (info_card + data.variant)
#   "timer_hud"   : thẻ tối có góc ngoặc (bracket) trên-trái: icon vòng sáng + tên (title | data.name | "SUBJECT"),
#                   đồng hồ đỏ lớn HH:MM:SS (data.timer, đếm lùi theo giây nếu data.running != false), dòng phụ
#                   (subtitle | data.sub | "TIME LEFT"). data.position tl|tr|bl|br (mặc định tl).
#   "hex_warning" : lục giác đỏ chứa số (data.number "1") + "WARNING" (data.label) + tiêu đề (title | data.title |
#                   "SYSTEM ALERT") + "IN N SECONDS" (data.seconds, đếm lùi; data.unit "SECONDS"; data.prefix "IN").
#                   data.position center|tl|tr (mặc định center = giữa-trên).
#   "time_place"  : pill: icon vòng + "FRIDAY NIGHT | 21:12:50" (title | data.day, data.time chạy theo giây nếu
#                   data.running != false) + dòng phụ (subtitle | data.sub | "ZONE A"). data.position tl|tr|bl|br.
HUD_VARIANTS = HUD_VARIANTS + ("timer_hud", "hex_warning", "time_place")
_RING_COLS = ["#35e0ff", "#5a8cff", "#a65cff", "#ff5ab4", "#ffb04a", "#35e0ff"]


def _hud_on_top_right(d: dict[str, Any]) -> bool:
    """HUD này có chiếm góc trên-phải không (để dời watermark)."""
    v = str(d.get("variant") or "")
    if v in ("knot_counter", "live_replay"):
        return True
    if v in ("countdown", "timer_hud", "time_place", "hex_warning"):
        return str(d.get("position") or "") == "tr"
    return False


def _ring_icon(c: skia.Canvas, cx: float, cy: float, r: float, glow: bool = True) -> None:
    sh = skia.GradientShader.MakeSweep(cx, cy, [color(x) for x in _RING_COLS])
    w = r * 0.28
    if glow:
        g = skia.Paint(AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=w * 2, Shader=sh)
        g.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, max(0.5, w * 0.8)))
        g.setAlphaf(0.7)
        c.drawCircle(cx, cy, r, g)
    c.drawCircle(cx, cy, r, skia.Paint(AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=w, Shader=sh))
    c.drawCircle(cx, cy, r * 0.22, fill("#ffffff"))


def _brackets(c: skia.Canvas, l: float, t: float, r: float, b: float, ln: float, w: float, col: str,
              a: float = 1.0) -> None:
    p = stroke(col, w, a)
    p.setStrokeCap(skia.Paint.kSquare_Cap)
    for x, y, dx, dy in ((l, t, 1, 1), (r, t, -1, 1), (l, b, 1, -1), (r, b, -1, -1)):
        c.drawLine(x, y, x + dx * ln, y, p)
        c.drawLine(x, y, x, y + dy * ln, p)


def _hms(s: str) -> int | None:
    m = re.match(r"^\s*(\d{1,3}):(\d{2})(?::(\d{2}))?\s*$", str(s or ""))
    if not m:
        return None
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3) or 0)


def _fmt_hms(sec: int) -> str:
    sec = max(0, sec)
    return f"{sec // 3600:02d}:{(sec // 60) % 60:02d}:{sec % 60:02d}"


def _corner_xy(pos: str, w: float, h: float, W: int, H: int, top: float) -> tuple[float, float]:
    mx = 0.035 * W
    x = mx if not pos.endswith("r") else W - mx - w
    y = top if pos.startswith("t") else H - 0.22 * H - h
    return x, y


def timer_hud_layer(ov: Overlay, W: int, H: int, end: float, top: float) -> Layer:
    d = dict(ov.data or {})
    name = _upper(str(d.get("name") or ov.title or "SUBJECT"))
    sub = _upper(str(d.get("sub") or ov.subtitle or "TIME LEFT"))
    ts = str(d.get("timer") or "23:41:07")
    base = _hms(ts)
    running = d.get("running", True) is not False and base is not None
    cw, ch = 0.36 * H, 0.2 * H
    sh = 0.02 * H
    s, c = _surface(cw + sh * 2, ch + sh * 2)
    c.translate(sh, sh)
    box = rrect(0, 0, cw, ch, 0.008 * H)
    c.save()
    c.translate(0, 0.006 * H)
    c.drawPath(box, _shadow_paint(0.5, sh * 0.5))
    c.restore()
    c.drawPath(box, fill("#0c0e18", 0.84))
    _brackets(c, 0.004 * H, 0.004 * H, cw - 0.004 * H, ch - 0.004 * H, 0.03 * H, max(1.5, 0.004 * H), "#ffffff", 0.85)
    ir = 0.026 * H
    _ring_icon(c, 0.03 * H + ir, 0.035 * H + ir * 0.4, ir)
    fn = fit_font(name, "extrabold", 0.026 * H, cw - 0.11 * H)
    spaced_text(c, name, 0.1 * H, 0.035 * H + ir * 0.4 + fn.getSize() * 0.36, fn, "#ffffff", 0.002 * H)
    fs = fit_font(sub, "bold", 0.016 * H, cw - 0.06 * H)
    spaced_text(c, sub, 0.03 * H, ch - 0.022 * H, fs, "#9aa3bd", 0.002 * H)
    img = s.makeImageSnapshot()
    x, y = _corner_xy(str(d.get("position") or "tl"), img.width() - sh * 2, img.height() - sh * 2, W, H, top)
    x -= sh
    y -= sh
    ft = fit_font("00:00:00" if base is not None and base < 360000 else ts, "extrabold", 0.068 * H, cw - 0.06 * H)
    col = str(d.get("color") or "#ff3b3b")

    def draw(layer: Layer, cv: skia.Canvas, t: float, a: float) -> None:
        u = layer.entering(t)
        sx = (1 - ease_out(u)) * -0.04 * W
        cv.drawImage(layer.images["card"], x + sx, y, LIN, skia.Paint(Alphaf=a))
        val = _fmt_hms(base - int(max(0.0, t - layer.t0))) if running else (_fmt_hms(base) if base is not None else nfc(ts))
        tx, ty = x + sx + sh + 0.03 * H, y + sh + ch * 0.74
        gp = fill(col, 0.55 * a)
        gp.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 0.008 * H))
        cv.drawString(val, tx, ty, ft, gp)
        cv.drawString(val, tx, ty, ft, fill(col, a))

    return Layer(None, 0.1, end - 0.05, 0.3, 0.25, kind="hud_timer", draw_fn=draw, images={"card": img}, data=d)


def _hex_path(cx: float, cy: float, r: float) -> skia.Path:
    return poly([(cx + r * math.cos(math.radians(30 + 60 * k)), cy + r * math.sin(math.radians(30 + 60 * k)))
                 for k in range(6)])


def hex_warning_layer(ov: Overlay, W: int, H: int, end: float, top: float) -> Layer:
    d = dict(ov.data or {})
    num = nfc(str(d.get("number", "1")))
    label = _upper(str(d.get("label") or "WARNING"))
    title = _upper(str(d.get("title") or ov.title or "SYSTEM ALERT"))
    try:
        secs = float(d.get("seconds", 10))
    except (TypeError, ValueError):
        secs = 10.0
    counting = d.get("count", True) is not False
    prefix = _upper(str(d.get("prefix") or "IN"))
    unit = _upper(str(d.get("unit") or ov.subtitle or "SECONDS"))
    hr = 0.07 * H
    pad = 0.025 * H
    fl = font(0.022 * H, "extrabold")
    ftit = fit_font(title, "extrabold", 0.036 * H, 0.42 * H)
    fsub = font(0.02 * H, "bold")
    tw = max(spaced_width(label, fl, 0.004 * H), ftit.measureText(title),
             spaced_width(f"{prefix} 000 {unit}", fsub, 0.002 * H))
    cw, ch = pad + hr * 2 + pad + tw + pad * 1.4, hr * 2 + pad * 1.4
    sh = 0.025 * H
    s, c = _surface(cw + sh * 2, ch + sh * 2)
    c.translate(sh, sh)
    box = rrect(hr, 0.01 * H, cw, ch - 0.01 * H, 0.01 * H)
    c.save()
    c.translate(0, 0.006 * H)
    c.drawPath(box, _shadow_paint(0.5, sh * 0.5))
    c.restore()
    c.drawPath(box, fill("#140a0c", 0.88))
    c.drawPath(box, stroke("#ff3b3b", max(1.0, 0.0025 * H), 0.8))
    hx, hy = pad + hr, ch / 2
    c.drawPath(_hex_path(hx, hy, hr * 1.05), fill("#140a0c"))
    c.drawPath(_hex_path(hx, hy, hr * 0.95), fill("#e02a2a"))
    c.drawPath(_hex_path(hx, hy, hr * 0.78), stroke("#ffffff", max(1.0, 0.003 * H), 0.55))
    fnum = fit_font(num, "extrabold", hr * 0.95, hr * 1.2)
    text(c, num, hx, hy + fnum.getSize() * 0.36, fnum, "#ffffff", align="c")
    tx = pad + hr * 2 + pad
    spaced_text(c, label, tx, 0.05 * H, fl, "#ff4a4a", 0.004 * H)
    text(c, title, tx, 0.098 * H, ftit, "#ffffff")
    img = s.makeImageSnapshot()
    pos = str(d.get("position") or "center")
    if pos == "center":
        x, y = (W - img.width()) / 2, top + 0.04 * H - sh
    else:
        x, y = _corner_xy(pos, img.width() - sh * 2, img.height() - sh * 2, W, H, top)
        x -= sh
        y -= sh
    sub_y = sh + 0.14 * H

    def draw(layer: Layer, cv: skia.Canvas, t: float, a: float) -> None:
        u = layer.entering(t)
        k = 0.9 + 0.1 * ease_out_back(u) if u < 1 else 1.0
        cv.save()
        cv.translate(x + img.width() / 2, y + img.height() / 2)
        cv.scale(k, k)
        ox, oy = -img.width() / 2, -img.height() / 2
        # nhịp đập đỏ quanh lục giác
        ph = (t * 1.6) % 1.0
        cv.drawPath(_hex_path(ox + sh + hx, oy + sh + hy, hr * (1.05 + 0.35 * ph)),
                    stroke("#ff3b3b", max(1.0, 0.004 * H * (1 - ph)), a * (1 - ph)))
        cv.drawImage(layer.images["card"], ox, oy, LIN, skia.Paint(Alphaf=a))
        n = secs - (t - layer.t0) if counting else secs
        n = max(0, int(math.ceil(n - 1e-6)))
        spaced_text(cv, f"{prefix} {n} {unit}", ox + sh + tx, oy + sub_y, fsub, "#ffb0a8", 0.002 * H, a)
        cv.restore()

    return Layer(None, 0.1, end - 0.05, 0.25, 0.25, kind="hud_hex_warning", draw_fn=draw, images={"card": img}, data=d)


def time_place_layer(ov: Overlay, W: int, H: int, end: float, top: float) -> Layer:
    d = dict(ov.data or {})
    day = _upper(str(d.get("day") or ov.title or "FRIDAY NIGHT"))
    ts = str(d.get("time") or "21:12:50")
    base = _hms(ts)
    running = d.get("running", True) is not False and base is not None
    sub = _upper(str(d.get("sub") or ov.subtitle or "ZONE A"))
    ph = 0.07 * H
    fm = font(ph * 0.4, "extrabold")
    fsub = font(0.018 * H, "bold")
    sample = f"{day}  |  {_fmt_hms(base) if base is not None else nfc(ts)}"
    w = ph * 0.2 + ph * 0.7 + ph * 0.3 + fm.measureText(sample) + ph * 0.5
    sh = 0.02 * H
    s, c = _surface(w + sh * 2, ph + 0.045 * H + sh * 2)
    c.translate(sh, sh)
    pill = rrect(0, 0, w, ph, ph / 2)
    c.save()
    c.translate(0, 0.005 * H)
    c.drawPath(pill, _shadow_paint(0.45, sh * 0.5))
    c.restore()
    c.drawPath(pill, fill("#0c0e18", 0.84))
    c.drawPath(rrect(1, 1, w - 1, ph - 1, ph / 2), stroke("#ffffff", max(1.0, H / 900), 0.2))
    _ring_icon(c, ph * 0.2 + ph * 0.35, ph / 2, ph * 0.24)
    tx = ph * 0.2 + ph * 0.7 + ph * 0.3
    dw = text(c, day + "  |  ", tx, ph / 2 + fm.getSize() * 0.36, fm, "#ffffff")
    if sub:
        spaced_text(c, sub, ph * 0.5 + 0.002 * H, ph + 0.033 * H + 0.002 * H, fsub, "#000000", 0.003 * H, 0.6)
        spaced_text(c, sub, ph * 0.5, ph + 0.033 * H, fsub, "#e6e9f2", 0.003 * H)
    img = s.makeImageSnapshot()
    x, y = _corner_xy(str(d.get("position") or "tl"), img.width() - sh * 2, img.height() - sh * 2, W, H, top)
    x -= sh
    y -= sh
    col = str(d.get("time_color") or "#7ad0ff")

    def draw(layer: Layer, cv: skia.Canvas, t: float, a: float) -> None:
        u = layer.entering(t)
        sy = (1 - ease_out(u)) * -0.04 * H
        cv.drawImage(layer.images["pill"], x, y + sy, LIN, skia.Paint(Alphaf=a))
        val = _fmt_hms(base + int(max(0.0, t - layer.t0))) if running else (_fmt_hms(base) if base is not None else nfc(ts))
        text(cv, val, x + sh + tx + dw, y + sy + sh + ph / 2 + fm.getSize() * 0.36, fm, col, a)

    return Layer(None, 0.15, end - 0.05, 0.3, 0.25, kind="hud_time_place", draw_fn=draw, images={"pill": img}, data=d)


def hud_layer(ov: Overlay, W: int, H: int, end: float, top: float) -> Layer:
    v = str((ov.data or {}).get("variant") or "")
    if v == "knot_counter":
        return knot_counter_layer(ov, W, H, end, top)
    if v == "countdown":
        return countdown_layer(ov, W, H, end, top)
    if v == "timer_hud":
        return timer_hud_layer(ov, W, H, end, top)
    if v == "hex_warning":
        return hex_warning_layer(ov, W, H, end, top)
    if v == "time_place":
        return time_place_layer(ov, W, H, end, top)
    return live_replay_layer(ov, W, H, end)


# ====================================================================== thẻ thông tin / giá
def render_info_card(ov: Overlay, W: int, H: int) -> skia.Image:
    d = dict(ov.data or {})
    rows = [r for r in (d.get("rows") or []) if isinstance(r, dict)]
    if not rows:
        rows = [{"label": "Instant noodles", "value": "$0.70"}, {"label": "Water", "value": "$0.50"},
                {"label": "Customer paid", "value": "$50.00", "note": "soaking wet cash"}]
    emph = d.get("emphasis_last", True) is not False
    w = 0.31 * W
    pad = 0.028 * H
    acc = max(4.0, 6 * H / 1080)
    pill_h = 0.04 * H
    row_h = 0.058 * H
    h = pad + pill_h + 0.022 * H + sum(row_h + (0.022 * H if r.get("note") else 0) for r in rows) + \
        (0.04 * H if ov.subtitle else 0) + pad * 0.6
    h = max(h, 0.27 * H)
    sh = 0.02 * H
    s, c = _surface(w + sh * 2, h + sh * 2)
    c.translate(sh, sh)
    box = rrect(0, 0, w, h, 0.012 * H)
    c.save()
    c.translate(0, 0.008 * H)
    c.drawPath(box, _shadow_paint(0.55, sh * 0.6))
    c.restore()
    c.drawPath(box, fill("#f3ede2"))
    c.save()
    c.clipPath(box, skia.ClipOp.kIntersect, True)
    c.drawRect(skia.Rect.MakeLTRB(0, 0, acc, h), fill("#e3b43a"))
    c.restore()
    lab = _upper(ov.title or "PRICE · POS")
    fl = font(0.018 * H, "bold")
    pw = spaced_width(lab, fl, 0.0025 * H) + pill_h * 1.1
    c.drawPath(rrect(pad, pad, pad + pw, pad + pill_h, pill_h / 2), fill("#151517"))
    spaced_text(c, lab, pad + pill_h * 0.55, pad + pill_h / 2 + 0.018 * H * 0.36, fl, "#ffffff", 0.0025 * H)
    y = pad + pill_h + 0.022 * H
    for i, r in enumerate(rows):
        last = emph and i == len(rows) - 1
        y += row_h * 0.72
        lab_s = nfc(str(r.get("label") or ""))
        val = nfc(str(r.get("value") or ""))
        fl_ = font(0.026 * H, "bold" if last else "semibold")
        fv = font(0.034 * H if last else 0.028 * H, "extrabold" if last else "bold")
        colv = "#c8352e" if last else "#1f2328"
        c.drawString(lab_s, pad + 0.004 * H, y, fl_, fill("#8a1d18" if last else "#4a4540"))
        text(c, val, w - pad, y, fv, colv, align="r")
        if r.get("note"):
            y += 0.024 * H
            c.drawString(nfc(str(r["note"])), pad + 0.004 * H, y, hand_font(0.019 * H, "regular"), fill("#8a8478"))
        y += row_h * 0.28
        if i < len(rows) - 1:
            c.drawLine(pad, y, w - pad, y, stroke("#cfc6b6", max(1.0, H / 1000),
                                                  PathEffect=skia.DashPathEffect.Make([0.006 * H, 0.005 * H], 0)))
    if ov.subtitle:
        spaced_text(c, _upper(ov.subtitle), pad, h - pad * 0.8, font(0.014 * H, "semibold"), "#9a9286", 0.003 * H)
    return s.makeImageSnapshot()


# ====================================================================== tin tuyển dụng
def _shop_icon(c: skia.Canvas, x: float, y: float, s: float) -> None:
    """Icon cửa hàng chung chung (huy hiệu gốc): ô bo xanh lục bảo, mặt tiền kem, mái hiên sọc cam có diềm tròn."""
    c.drawPath(rrect(x, y, x + s, y + s, s * 0.2), fill(BRAND_GREEN))
    bx0, bx1 = x + s * 0.17, x + s * 0.83
    c.drawRect(skia.Rect.MakeLTRB(bx0 + s * 0.04, y + s * 0.42, bx1 - s * 0.04, y + s * 0.82), fill(BRAND_CREAM))
    n = 4
    sw_ = (bx1 - bx0) / n
    for i in range(n):
        col = BRAND_ORANGE if i % 2 == 0 else "#ffffff"
        c.drawRect(skia.Rect.MakeLTRB(bx0 + sw_ * i, y + s * 0.2, bx0 + sw_ * (i + 1), y + s * 0.4), fill(col))
        c.drawCircle(bx0 + sw_ * (i + 0.5), y + s * 0.4, sw_ / 2, fill(col))
    c.drawRect(skia.Rect.MakeLTRB(x + s * 0.44, y + s * 0.56, x + s * 0.6, y + s * 0.82), fill(BRAND_GREEN))
    c.drawRect(skia.Rect.MakeLTRB(x + s * 0.25, y + s * 0.56, x + s * 0.38, y + s * 0.68), fill("#9fd3c5"))


def render_job_ad(ov: Overlay, W: int, H: int) -> skia.Image:
    d = dict(ov.data or {})
    w, h = 0.46 * W, 0.62 * H
    m = 0.03 * H
    s, c = _surface(w + m * 2, h + m * 2)
    c.translate(m, m)
    card = rrect(0, 0, w, h, 0.016 * H)
    c.save()
    c.translate(0.004 * H, 0.014 * H)
    c.drawPath(card, _shadow_paint(0.55, 0.016 * H))
    c.restore()
    c.drawPath(card, fill("#ffffff"))
    c.save()
    c.clipPath(card, skia.ClipOp.kIntersect, True)
    hh = 0.2 * h
    c.drawRect(skia.Rect.MakeLTRB(0, 0, w, hh), fill("#e3b43a"))
    c.drawRect(skia.Rect.MakeLTRB(0, hh - 0.006 * H, w, hh), fill("#c99a28"))
    c.restore()
    _shop_icon(c, 0.04 * w, hh * 0.18, hh * 0.64)
    shop = _upper(d.get("shop") or "CONVENIENCE STORE")
    fs = fit_font(shop, "extrabold", hh * 0.3, w * 0.55)
    c.drawString(shop, 0.04 * w + hh * 0.8, hh * 0.5 + fs.getSize() * 0.36, fs, fill("#1f2328"))
    bw24 = hh * 0.95
    bx = w - 0.04 * w - bw24
    c.drawPath(rrect(bx, hh * 0.27, bx + bw24, hh * 0.73, hh * 0.1), fill("#1f2328"))
    text(c, "24H", bx + bw24 / 2, hh * 0.5 + hh * 0.25 * 0.36, font(hh * 0.25, "extrabold"), "#e3b43a", align="c")
    title = _upper(ov.title or "NIGHT SHIFT CLERK WANTED")
    ft = font(0.062 * H, "extrabold")
    lines = balanced_wrap(title, ft, w * 0.86)
    if any(ft.measureText(ln) > w * 0.88 for ln in lines):
        ft = font(0.062 * H * w * 0.86 / max(ft.measureText(ln) for ln in lines), "extrabold")
    y = hh + 0.085 * H
    for ln in lines:
        text(c, ln, w / 2, y, ft, "#1f2328", align="c")
        y += ft.getSize() * 1.15
    hours = nfc(ov.subtitle or "22:00 – 06:00")
    fh = font(0.04 * H, "bold")
    tw = fh.measureText(hours)
    cr = 0.018 * H
    cx = w / 2 - tw / 2 - cr * 1.4
    cy = y + 0.01 * H - fh.getSize() * 0.36
    c.drawCircle(cx, cy, cr, stroke("#4a4540", 0.004 * H))
    c.drawLine(cx, cy, cx, cy - cr * 0.6, stroke("#4a4540", 0.004 * H))
    c.drawLine(cx, cy, cx + cr * 0.5, cy, stroke("#4a4540", 0.004 * H))
    text(c, hours, w / 2 + cr, y + 0.01 * H, fh, "#4a4540", align="c")
    y += 0.07 * H
    sal = nfc(d.get("salary") or "$800 / month")
    fsal = fit_font(sal, "extrabold", 0.05 * H, w * 0.72)
    sw_ = fsal.measureText(sal) + 0.06 * H
    sh_ = 0.08 * H
    c.drawPath(rrect(w / 2 - sw_ / 2, y, w / 2 + sw_ / 2, y + sh_, sh_ / 2), fill("#c8352e"))
    text(c, sal, w / 2, y + sh_ / 2 + fsal.getSize() * 0.36, fsal, "#ffffff", align="c")
    foot = nfc(d.get("footnote") or "Start now · No experience needed · Dinner included")
    ff = fit_font(foot, "semibold", 0.02 * H, w * 0.86)
    text(c, foot, w / 2, h - 0.035 * H, ff, "#8a8478", align="c")
    tape(c, w / 2, 0.0, 0.16 * H, 0.04 * H, -4)
    return s.makeImageSnapshot()


def job_ad_layer(ov: Overlay, W: int, H: int, end: float, seed: int) -> Layer:
    img = render_job_ad(ov, W, H)
    rng = random.Random(seed)
    bits = []
    for _ in range(16):
        bits.append({"x": rng.uniform(0.05, 0.95) * W, "y": rng.uniform(0.05, 0.95) * H,
                     "w": rng.uniform(0.012, 0.035) * H, "h": rng.uniform(0.006, 0.022) * H,
                     "vx": rng.uniform(-25, 25) * H / 1080, "vy": rng.uniform(15, 45) * H / 1080,
                     "rot": rng.uniform(0, 360), "vr": rng.uniform(-90, 90),
                     "col": rng.choice(["#ffffff", "#f2ead8", "#e3b43a", "#e2d3b0", "#f6efdf"])})
    iw, ih = img.width(), img.height()
    cx, cy = W / 2, H / 2 + 0.01 * H

    def draw(layer: Layer, cv: skia.Canvas, t: float, a: float) -> None:
        tt = t - layer.t0
        for b in bits:   # mẩu giấy/băng keo bay (sau thẻ)
            x = (b["x"] + b["vx"] * tt) % W
            y = (b["y"] + b["vy"] * tt) % H
            cv.save()
            cv.translate(x, y)
            cv.rotate(b["rot"] + b["vr"] * tt)
            cv.drawRect(skia.Rect.MakeXYWH(-b["w"] / 2, -b["h"] / 2, b["w"], b["h"]), fill(b["col"], a * 0.85))
            cv.restore()
        u = min(1.0, max(0.0, tt / 0.45))
        e = ease_out_back(u, 1.3)
        dy = (1 - e) * -0.25 * H
        rot = -3 + (1 - e) * -6
        cv.save()
        cv.translate(cx, cy + dy)
        cv.rotate(rot)
        cv.drawImage(layer.images["card"], -iw / 2, -ih / 2, LIN, skia.Paint(Alphaf=a * min(1.0, u * 3)))
        cv.restore()

    return Layer(None, 0.1, end - 0.05, 0.25, 0.25, kind="job_ad", draw_fn=draw, images={"card": img},
                 backdrop="blur", backdrop_dim=0.4, data=dict(ov.data or {}))


def rule_list_layer(ov: Overlay, W: int, H: int, end: float, seed: int) -> Layer:
    d = dict(ov.data or {})
    rules = [str(r) for r in (d.get("rules") or []) if str(r).strip()]
    if not rules:
        rules = ["Do not open the door after 2 AM.", "If a customer calls your name, *don't answer*.",
                 "If the storeroom light blinks 3 times, stand still at the counter.", "Never accept wet money."]
    red = d.get("red_index")
    img = render_rule_paper(ov.title or "Night shift rules", ov.subtitle, rules, W, H,
                            red_index=int(red) if red is not None else None,
                            redact_last=bool(d.get("redact_last")), coffee_stain=bool(d.get("coffee_stain")),
                            bleed_through=bool(d.get("bleed_through")), seed=seed)
    images = {"paper": img}
    hands = bool(d.get("hands"))
    sleeve = d.get("sleeve") or BRAND_GREEN
    skin = d.get("skin") or SKIN
    blur_s = 0.0065 * H if d.get("blurred") else 0.0
    rot = float(d.get("rotation_deg", -2))
    iw, ih = img.width(), img.height()

    def draw(layer: Layer, cv: skia.Canvas, t: float, a: float) -> None:
        u = t / max(end, 0.1)
        sc = 1.0 + 0.04 * u
        dy = (0.02 - 0.06 * u) * H        # pan dọc chậm (đọc từ trên xuống)
        cv.save()
        cv.translate(W / 2, H / 2 + dy)
        cv.rotate(rot)
        cv.scale(sc, sc)
        p = skia.Paint(Alphaf=a)
        if blur_s:
            p.setImageFilter(skia.ImageFilters.Blur(blur_s, blur_s, skia.TileMode.kDecal, None))
        cv.drawImage(layer.images["paper"], -iw / 2, -ih / 2, LIN, p)
        if hands:
            hs = 0.13 * H
            mitten_hand(cv, -iw * 0.36, ih / 2 - 0.03 * H, hs, 8, skin=skin, sleeve=sleeve)
            mitten_hand(cv, iw * 0.36, ih / 2 - 0.03 * H, hs, -8, skin=skin, sleeve=sleeve, mirror=True)
        cv.restore()

    return Layer(None, 0.0, end - 0.02, 0.4, 0.25, kind="rule_list", draw_fn=draw, images=images, backdrop="blur",
                 backdrop_dim=0.6, backdrop_sigma=14.0, data=d)


# ====================================================================== watermark
def render_watermark(text_: str, H: int) -> skia.Image:
    f = font(0.024 * H, "bold")
    text_ = nfc(text_)
    w = f.measureText(text_) + 0.02 * H
    s, c = _surface(w, 0.04 * H)
    c.drawString(text_, 0.01 * H, 0.03 * H, f, fill("#ffffff", 0.42))
    return s.makeImageSnapshot()


# ====================================================================== build all
@dataclass
class BadgeSpec:
    character_id: str
    image: skia.Image
    w_frac: float          # bề rộng theo chiều cao puppet
    h_frac: float


@dataclass
class OverlaySet:
    layers: list[Layer] = field(default_factory=list)
    badges: list[BadgeSpec] = field(default_factory=list)
    cctv: dict[str, Any] | None = None       # Overlay.data của overlay cctv (compositor: lưới 4 / split)

    def upload(self, be) -> None:
        """Đưa mọi ảnh dựng sẵn lên GPU (1 lần/shot)."""
        for l in self.layers:
            if l.image is not None:
                l.image = be.texture(l.image)
            if l.images:
                l.images = {k: be.texture(v) for k, v in l.images.items()}
        for b in self.badges:
            b.image = be.texture(b.image, mipmaps=True)

    def draw(self, c: skia.Canvas, t: float, surface: skia.Surface | None = None) -> None:
        for l in self.layers:
            if l.backdrop and surface is not None:
                a = l.alpha(t)
                if a > 0.003:
                    draw_backdrop(c, surface, l.backdrop, a, l.backdrop_sigma * c.getBaseLayerSize().height() / 1080,
                                  l.backdrop_dim)
            l.draw(c, t)


def draw_backdrop(c: skia.Canvas, surface: skia.Surface, kind: str, a: float, sigma: float, dim: float) -> None:
    """Làm mờ + tối khung hiện tại phía sau overlay (crossfade theo a)."""
    size = c.getBaseLayerSize()
    if kind == "blur" and sigma > 0.3:
        snap = surface.makeImageSnapshot()
        p = skia.Paint(Alphaf=a, ImageFilter=skia.ImageFilters.Blur(sigma, sigma, skia.TileMode.kClamp, None))
        c.save()
        c.resetMatrix()
        c.drawImage(snap, 0, 0, LIN, p)
        c.restore()
    if dim > 0:
        c.drawRect(skia.Rect.MakeWH(size.width(), size.height()), fill("#000000", a * dim))


def build_overlays(shot: Shot, sb: Storyboard, tls: list[TimedLine], duration: float, W: int, H: int,
                   nametag_anchor: Callable[[str, float, int, int], tuple[float, float] | None],
                   watermark: str | None = "StoryToon", seed: int = 0) -> OverlaySet:
    """`nametag_anchor(character_id, t, w, h)` -> góc trên-trái cho nametag (hoặc None nếu nhân vật không có mặt)."""
    layers: list[Layer] = []
    full: list[Layer] = []            # overlay toàn khung (vẽ trước thẻ nhỏ)
    badges: list[BadgeSpec] = []
    cctv_data: dict[str, Any] | None = None
    margin_x, margin_y = 0.035 * W, 0.05 * H
    stack_y = margin_y
    end = duration
    cctv_present = any(o.kind == "cctv" for o in shot.overlays)
    if cctv_present:
        stack_y = margin_y + 0.13 * H   # chừa chỗ REC/CAM
    for ov in shot.overlays:
        if ov.kind in ("location_card", "time_card"):
            img = render_place_card(ov.title, ov.subtitle, H, ov.kind)
            layers.append(Layer(img, 0.2, end - 0.1, 0.4, 0.35, (margin_x - 0.01 * H, stack_y), kind=ov.kind))
            stack_y += img.height() + 0.004 * H
    for ov in shot.overlays:
        d = ov.data or {}
        try:
            if ov.kind == "rule_card":
                img = render_rule_card(ov.title, ov.subtitle, W, H, number=d.get("number"),
                                       caption=d.get("caption_en") or d.get("caption"))
                corner = str(d.get("corner") or "tl")
                x = (W - margin_x - img.width() + 0.016 * H) if corner == "tr" else margin_x - 0.016 * H
                if corner == "tr":
                    y = margin_y + (0.06 * H if cctv_present else 0.0)
                else:
                    y = stack_y
                    stack_y += img.height() + 0.006 * H
                layers.append(Layer(img, 0.3, end - 0.1, 0.35, 0.3, (x, y), kind="rule_card",
                                    slide=(0.0, -0.06 * H)))
            elif ov.kind == "chapter_card":
                if d.get("style") == "text_on_black":
                    img = render_black_title(ov.title, ov.subtitle, W, H)
                    full.append(Layer(img, 0.0, end + 0.5, 0.35, 0.0, (0.0, 0.0), kind="chapter_card"))
                else:
                    img = render_chapter_card(sb.title, ov.title, ov.subtitle, W, H)
                    layers.append(Layer(img, 0.0, end, 0.5, 0.45, ((W - img.width()) / 2, (H - img.height()) / 2 - 0.04 * H),
                                        kind="chapter_card", scale_in=0.06))
            elif ov.kind == "nametag":
                cid = ov.character_id or ""
                cdef = sb.character(cid) if cid else None
                name = ov.title or (cdef.name if cdef else cid)
                role = ov.subtitle if ov.subtitle is not None else (cdef.role if cdef else None)
                img = render_nametag(name, role, H)
                iw, ih = img.width(), img.height()

                def anchor(t: float, cid=cid, iw=iw, ih=ih) -> tuple[float, float]:
                    p = nametag_anchor(cid, t, iw, ih) if cid else None
                    return p if p else (margin_x, H * 0.62)

                layers.append(Layer(img, 0.25, end - 0.15, 0.3, 0.3, anchor=anchor, kind="nametag"))
            elif ov.kind == "badge":
                cid = ov.character_id or ""
                if not cid:
                    log.warning("Shot %s: overlay badge thiếu character_id — bỏ qua", shot.id)
                    continue
                txt = nfc(str(d.get("text") or ov.title or ""))
                img = render_badge(txt, bg=str(d.get("color") or "#ffffff"),
                                   text_color=str(d.get("text_color") or "#7a2a2a"), emblem=str(d.get("emblem") or "leaf"))
                badges.append(BadgeSpec(cid, img, float(d.get("w_char", 0.11)), float(d.get("h_char", 0.035))))
            elif ov.kind == "cctv":
                cctv_data = dict(d)
                layers.append(cctv_layer(ov, W, H, end))
            elif ov.kind == "phone_chat":
                full.append(phone_chat_layer(ov, W, H, end))
            elif ov.kind == "phone_bank":
                full.append(phone_bank_layer(ov, W, H, end))
            elif ov.kind == "missing_poster":
                img = render_missing_poster(ov, W, H)
                wall = str(d.get("variant") or "") == "wall"
                full.append(Layer(img, 0.1, end - 0.02, 0.3, 0.2, (0.0, 0.0), kind="missing_poster", scale_in=0.04,
                                  backdrop=None if wall else "blur", backdrop_dim=0.5, data=dict(d)))
            elif ov.kind == "map_card":
                full.append(map_card_layer(ov, W, H, end))
            elif ov.kind == "timeline":
                full.append(timeline_layer(ov, W, H, end))
            elif ov.kind == "info_card" and str(d.get("variant") or "") in HUD_VARIANTS:
                hud = hud_layer(ov, W, H, end, margin_y + (0.13 * H if cctv_present else 0.0))
                (layers if hud.kind != "hud_countdown" or d.get("position", "center") != "center" else full).append(hud)
            elif ov.kind == "info_card":
                img = render_info_card(ov, W, H)
                blur = d.get("blur_bg", True) is not False
                full.append(Layer(img, 0.2, end - 0.05, 0.3, 0.25, (0.06 * W - 0.02 * H, (H - img.height()) / 2),
                                  kind="info_card", slide=(-0.06 * W, 0.0), backdrop="blur" if blur else None,
                                  backdrop_dim=0.25, data=dict(d)))
            elif ov.kind == "job_ad":
                full.append(job_ad_layer(ov, W, H, end, seed))
            elif ov.kind == "rule_list":
                full.append(rule_list_layer(ov, W, H, end, seed))
        except Exception as e:  # noqa: BLE001 — overlay lỗi không làm sập cả shot
            log.warning("Shot %s: không dựng được overlay %s (%s) — bỏ qua", shot.id, ov.kind, e)
    out = full + layers
    out += subtitle_layers(shot, tls, duration, W, H)
    if watermark:
        img = render_watermark(watermark, H)
        # CCTV chiếm các góc (REC, hộp đếm, timestamp, nhãn ô) -> watermark lên giữa-trên
        # HUD lô 3 chiếm góc trên-phải (pill đếm nút, timestamp live replay, đếm ngược góc tr) -> cũng lên giữa-trên
        hud_tr = any(o.kind == "info_card" and str((o.data or {}).get("variant") or "") in HUD_VARIANTS and
                     _hud_on_top_right(o.data or {}) for o in shot.overlays)
        pos = ((W - img.width()) / 2, 0.03 * H) if (cctv_present or hud_tr) else (W - img.width() - 0.03 * W, 0.04 * H)
        out.append(Layer(img, 0.0, end + 1, 0.0, 0.0, pos, kind="watermark"))
    return OverlaySet(out, badges, cctv_data)
