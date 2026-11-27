"""Ảnh chèn lô 2 — thư viện mở rộng (provenance 'procedural_library'), cùng phong cách flat-vector với insertgen.

Học PHONG CÁCH + loại đạo cụ chung chung từ khung tham khảo; mọi hình vẽ là bản GỐC bằng code (skia), không cắt/đồ
pixel, không tên/logo/cờ/hình mờ của kênh khác. MỌI chữ vẽ vào pixel là TIẾNG ANH (không dấu), bịa, chung chung,
lấy từ params (sửa được trong catalog/sidecar).

Mọi hàm vẽ trên hệ toạ độ logic 3840×2160 (canvas được scale theo kích thước ra) nên chạy đúng ở mọi cỡ 16:9.
Được insertgen nạp ở cuối module: INSERTS / SCREENS / TAGS / PROPS được trộn vào bảng của insertgen.
"""
from __future__ import annotations

import math
import random

import skia

from .insertgen import (BRAND_GREEN, INK, RED_INK, TAPE, SAMPLING, _glow, _hand, _lin, _portrait, _rad, _shadow,
                        _status_bar, _surface, _tape, _avatar_color, draw_background, draw_missing_poster,
                        draw_paper_notebook, draw_phone, text)
from .skutil import capsule, circle, fill, font, nfc, oval, poly, rrect, shade, smooth, stroke, wrap_text

LW, LH = 3840.0, 2160.0


# =================================================================== tiện ích chung
def _begin(size):
    s, c = _surface(size)
    c.scale(size[0] / LW, size[1] / LH)
    return s, c


def _vignette(c, a=0.5, cx=0.5, cy=0.5, inner=0.42) -> None:
    c.drawRect(skia.Rect.MakeWH(LW, LH), _rad(LW * cx, LH * cy, LW * 0.68, [("#000000", 0.0), ("#000000", a)], [inner, 1]))


def _blurred(col, a, sigma) -> skia.Paint:
    p = fill(col, a)
    p.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, sigma))
    return p


def _dash(col, w, on, off, a=1.0) -> skia.Paint:
    p = stroke(col, w, a)
    p.setPathEffect(skia.DashPathEffect.Make([on, off], 0))
    return p


def _spaced(s: str) -> str:
    return " ".join(nfc(s))


def _card(c, l, t, w, rows, accent="#c8352e", bg="#f6efe0", pad=44, bar=18) -> float:
    """Thẻ thông tin nền kem + vạch màu bên trái. rows: [(text, size, colour, weight)]. Trả về chiều cao."""
    h = pad * 2 + sum(r[1] * 1.25 for r in rows)
    card = rrect(l, t, l + w, t + h, 26)
    _shadow(c, card, 26, 14, 0.5)
    c.drawPath(card, fill(bg))
    c.save()
    c.clipPath(card, skia.ClipOp.kIntersect, True)
    c.drawRect(skia.Rect.MakeLTRB(l, t, l + bar, t + h), fill(accent))
    c.restore()
    y = t + pad
    for s, sz, col, wt in rows:
        y += sz * 1.25
        text(c, s, l + pad + bar, y - sz * 0.25, sz, col, wt, max_w=w - pad * 2 - bar)
    return h


def _pushpin(c, x, y, col="#d0302a", r=26) -> None:
    c.drawPath(oval(x + r * 0.5, y + r * 0.7, r * 1.0, r * 0.5), _blurred("#000000", 0.35, r * 0.3))
    c.drawCircle(x, y, r, fill(col))
    c.drawCircle(x, y, r * 0.62, fill(shade(col, 0.18)))
    c.drawCircle(x - r * 0.3, y - r * 0.3, r * 0.25, fill("#ffffff", 0.7))


_SEG = {"0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd", "6": "afgedc", "7": "abc",
        "8": "abcdefg", "9": "abcdfg", "-": "g", " ": "", "E": "afged", "A": "abcefg", "L": "fed"}


def _seven_width(s: str, h: float) -> float:
    """Bề rộng chuỗi LED 7 đoạn ở chiều cao h (khớp bước x của _seven)."""
    t = h * 0.12
    return sum(t * 2.2 if ch in ".:" else h * 0.52 + t * 1.3 for ch in s) - t * 1.3


def _seven(c, s: str, x: float, y: float, h: float, col: str, off: str | None = None, glow: bool = False) -> float:
    """Chữ số LED 7 đoạn (x trái, y đỉnh). Trả về x cuối."""
    w, t = h * 0.52, h * 0.12
    g = t * 0.18

    def seg_rects(x0):
        return {
            "a": (x0 + t * 0.5 + g, y, x0 + w - t * 0.5 - g, y + t),
            "g": (x0 + t * 0.5 + g, y + h / 2 - t / 2, x0 + w - t * 0.5 - g, y + h / 2 + t / 2),
            "d": (x0 + t * 0.5 + g, y + h - t, x0 + w - t * 0.5 - g, y + h),
            "f": (x0, y + t * 0.5 + g, x0 + t, y + h / 2 - g),
            "b": (x0 + w - t, y + t * 0.5 + g, x0 + w, y + h / 2 - g),
            "e": (x0, y + h / 2 + g, x0 + t, y + h - t * 0.5 - g),
            "c": (x0 + w - t, y + h / 2 + g, x0 + w, y + h - t * 0.5 - g),
        }
    for ch in s:
        if ch in ".:":
            ys = [y + h - t] if ch == "." else [y + h * 0.28, y + h * 0.66]
            for yy in ys:
                if glow:
                    c.drawRect(skia.Rect.MakeLTRB(x, yy, x + t, yy + t), _blurred(col, 0.6, t * 0.8))
                c.drawRect(skia.Rect.MakeLTRB(x, yy, x + t, yy + t), fill(col))
            x += t * 2.2
            continue
        on = _SEG.get(ch, "")
        for name, r in seg_rects(x).items():
            if name in on:
                if glow:
                    c.drawPath(rrect(*r, t * 0.4), _blurred(col, 0.55, t * 0.9))
                c.drawPath(rrect(*r, t * 0.4), fill(col))
            elif off:
                c.drawPath(rrect(*r, t * 0.4), fill(off))
        x += w + t * 1.3
    return x


def _crack(c, cx, cy, R, seed=3, col="#ffffff", a=0.75, w=5.0) -> None:
    """Vết nứt màn hình hình mạng nhện: tia gãy khúc + cung đứt nối các tia."""
    rng = random.Random(seed)
    n = 13
    rays = []
    for k in range(n):
        ang = (k + rng.uniform(-0.3, 0.3)) / n * math.tau
        pts = [(cx, cy)]
        r = 0.0
        while r < R:
            r += rng.uniform(0.12, 0.22) * R
            aa = ang + rng.uniform(-0.12, 0.12)
            pts.append((cx + math.cos(aa) * r, cy + math.sin(aa) * r))
        rays.append(pts)
        c.drawPath(poly(pts, close=False), stroke("#000000", w * 1.8, a * 0.35))
        c.drawPath(poly(pts, close=False), stroke(col, w, a))
    for ring in (0.22, 0.45, 0.7):
        for k in range(n):
            p0 = rays[k][min(len(rays[k]) - 1, int(ring * 5) + 1)]
            p1 = rays[(k + 1) % n][min(len(rays[(k + 1) % n]) - 1, int(ring * 5) + 1)]
            if rng.random() < 0.75:
                mx, my = (p0[0] + p1[0]) / 2 + rng.uniform(-12, 12), (p0[1] + p1[1]) / 2 + rng.uniform(-12, 12)
                c.drawPath(poly([p0, (mx, my), p1], close=False), stroke(col, w * 0.7, a * 0.8))
    c.drawCircle(cx, cy, R * 0.05, fill(col, a * 0.6))


def _fist(c, x, y, ang, s, skin, sleeve=None) -> None:
    """Nắm tay đơn giản (cầm cán): (x, y) = giữa nắm tay; cổ tay hướng +y local trước khi xoay."""
    dk = shade(skin, -0.2)
    c.save()
    c.translate(x, y)
    c.rotate(ang)
    if sleeve:
        c.drawPath(rrect(-120 * s, 140 * s, 120 * s, 1400 * s, 50 * s), fill(sleeve))
    c.drawPath(capsule(0, 100 * s, 0, 1400 * s, 210 * s, 250 * s), fill(skin))     # cẳng tay
    c.drawPath(rrect(-130 * s, -120 * s, 130 * s, 150 * s, 80 * s), fill(skin))
    for i in range(4):                                                              # 4 đốt ngón cuộn
        yy = (-95 + i * 62) * s
        c.drawPath(capsule(-60 * s, yy, 130 * s, yy, 64 * s, 60 * s), fill(shade(skin, 0.04 if i % 2 else 0.0)))
        c.drawLine(80 * s, yy - 20 * s, 80 * s, yy + 20 * s, stroke(dk, 4 * s, 0.6))
    c.drawPath(capsule(-110 * s, 90 * s, 30 * s, -60 * s, 72 * s, 60 * s), fill(shade(skin, 0.06)))   # ngón cái
    c.drawPath(rrect(-130 * s, -120 * s, 130 * s, 150 * s, 80 * s), stroke(dk, 4 * s, 0.35))
    c.restore()


def _tattoo(c, pts, s=1.0, col="#2f4a4a") -> None:
    """Hình xăm dây leo/rắn: đường cong + lá oval nhỏ."""
    c.drawPath(smooth(pts, close=False), stroke(col, 12 * s, 0.75))
    for i in range(1, len(pts) - 1):
        x, y = pts[i]
        side = 1 if i % 2 else -1
        c.save()
        c.translate(x, y)
        c.rotate(35 * side)
        c.drawPath(oval(side * 34 * s, 0, 30 * s, 13 * s), fill(col, 0.75))
        c.restore()


def _wood_top(c, base="#b48356") -> None:
    """Mặt bàn gỗ nhìn từ trên (ván ngang, vân gỗ)."""
    rng = random.Random(8)
    y = 0.0
    while y < LH:
        hh = rng.uniform(260, 380)
        col = shade(base, rng.uniform(-0.08, 0.06))
        c.drawRect(skia.Rect.MakeLTRB(0, y, LW, y + hh), fill(col))
        for _ in range(6):
            yy = y + rng.uniform(10, hh - 10)
            p = skia.Path()
            p.moveTo(0, yy)
            p.cubicTo(LW * 0.3, yy + rng.uniform(-25, 25), LW * 0.65, yy + rng.uniform(-25, 25), LW, yy)
            c.drawPath(p, stroke(shade(col, -0.18), rng.uniform(2, 5), 0.5))
        c.drawRect(skia.Rect.MakeLTRB(0, y + hh - 6, LW, y + hh), fill(shade(base, -0.4)))
        y += hh


def _concrete(c, base="#8a8781", slabs=True) -> None:
    c.drawRect(skia.Rect.MakeWH(LW, LH), fill(base))
    rng = random.Random(14)
    for _ in range(2200):
        c.drawCircle(rng.uniform(0, LW), rng.uniform(0, LH), rng.uniform(2, 7),
                     fill(rng.choice([shade(base, -0.15), shade(base, 0.12), shade(base, -0.07)]), 0.6))
    if slabs:
        for x in (1250.0, 2650.0):
            c.drawRect(skia.Rect.MakeLTRB(x, 0, x + 12, LH), fill(shade(base, -0.35)))
        c.drawRect(skia.Rect.MakeLTRB(0, 1180, LW, 1192), fill(shade(base, -0.35)))


def _tiles(c, base="#b9b4a8", step=480.0) -> None:
    """Sàn gạch vuông nhìn từ trên: ô hơi lệch sắc, ron xám đậm, vết bẩn nhẹ."""
    rng = random.Random(16)
    c.drawRect(skia.Rect.MakeWH(LW, LH), fill(shade(base, -0.35)))
    y = 0.0
    while y < LH:
        x = 0.0
        while x < LW:
            col = shade(base, rng.uniform(-0.05, 0.05))
            c.drawRect(skia.Rect.MakeLTRB(x + 7, y + 7, x + step - 7, y + step - 7), fill(col))
            c.drawRect(skia.Rect.MakeLTRB(x + 7, y + 7, x + step - 7, y + 30), fill("#ffffff", 0.08))
            x += step
        y += step
    for _ in range(900):
        c.drawCircle(rng.uniform(0, LW), rng.uniform(0, LH), rng.uniform(2, 6), fill(shade(base, -0.2), 0.35))


def _bokeh(c, base0, base1, cols, n=26, seed=4) -> None:
    c.drawRect(skia.Rect.MakeWH(LW, LH), _rad(LW * 0.5, LH * 0.45, LW * 0.75, [base0, base1]))
    rng = random.Random(seed)
    for _ in range(n):
        r = rng.uniform(70, 230)
        c.drawCircle(rng.uniform(0, LW), rng.uniform(0, LH), r, _blurred(rng.choice(cols), rng.uniform(0.18, 0.45), r * 0.18))


# =================================================================== màn hình điện thoại mới
def _bubbles(c, sl, sr, y, ybot, sw, sh, msgs, out_col="#2e7cf6", in_col="#3a3b40") -> float:
    fs = sh * 0.028
    f = font(fs, "semibold")
    pad = fs * 0.62
    maxw = sw * 0.66
    for m in msgs:
        me = m.get("from") == "me"
        if m.get("typing"):
            bw, bh = fs * 3.6, fs * 2.0
            if y + bh > ybot:
                break
            bx = sl + sw * 0.05
            c.drawPath(rrect(bx, y, bx + bw, y + bh, fs), fill(in_col))
            for k in range(3):
                c.drawCircle(bx + bw * (0.28 + k * 0.22), y + bh / 2, fs * 0.22, fill("#c9cbd1", 1.0 - k * 0.25))
            y += bh + fs * 0.7
            continue
        lines = wrap_text(m.get("text", ""), f, maxw - pad * 2)
        bw = (max(f.measureText(ln) for ln in lines) if lines else fs * 2) + pad * 2
        bh = len(lines) * fs * 1.28 + pad * 1.4
        if y + bh > ybot:
            break
        bx = sr - sw * 0.05 - bw if me else sl + sw * 0.05
        c.drawPath(rrect(bx, y, bx + bw, y + bh, fs * 0.8), fill(out_col if me else in_col))
        for i, ln in enumerate(lines):
            c.drawString(ln, bx + pad, y + pad * 0.7 + fs * (1.0 + i * 1.28), f, fill("#ffffff"))
        y += bh + fs * 0.7
        if me and m.get("failed"):
            text(c, "! Not delivered", bx + bw, y - fs * 0.25, fs * 0.6, "#ff5a4f", "semibold", "right")
            y += fs * 0.5
    return y


_SMS_DEFAULT = [{"from": "me", "text": "Where are you?"}, {"from": "me", "text": "Pick up the phone"},
                {"from": "me", "text": "Mom cried all night"}, {"from": "them", "text": "Help me"},
                {"from": "them", "typing": True}]


def _screen_sms(c, sl, st, sr, sb, d: dict) -> None:
    """SMS chế độ tối: header avatar + 'SMS · offline' + nút gọi; bong bóng; bong bóng 'đang gõ'."""
    sw, sh = sr - sl, sb - st
    c.drawRect(skia.Rect.MakeLTRB(sl, st, sr, sb), fill("#0c0d10"))
    _status_bar(c, sl, st + sh * 0.012, sr, sh * 0.045, d.get("time") or "02:47")
    hy, hh = st + sh * 0.06, sh * 0.085
    c.drawRect(skia.Rect.MakeLTRB(sl, hy, sr, hy + hh), fill("#16171b"))
    pth = skia.Path()
    pth.moveTo(sl + sw * 0.075, hy + hh * 0.32)
    pth.lineTo(sl + sw * 0.05, hy + hh * 0.5)
    pth.lineTo(sl + sw * 0.075, hy + hh * 0.68)
    c.drawPath(pth, stroke("#2e7cf6", sw * 0.012))
    name = nfc(d.get("contact") or "Sis")
    ar, ax, ay = hh * 0.32, sl + sw * 0.17, hy + hh / 2
    c.drawCircle(ax, ay, ar, fill(_avatar_color(name)))
    text(c, name[:1].upper(), ax, ay + ar * 0.38, ar * 1.05, "#ffffff", "bold", "center")
    text(c, name, ax + ar * 1.5, ay - hh * 0.02, hh * 0.27, "#ffffff", "bold", max_w=sw * 0.45)
    c.drawCircle(ax + ar * 1.62, ay + hh * 0.2, hh * 0.05, fill("#8a8d96"))
    text(c, d.get("status", "SMS · offline"), ax + ar * 1.85, ay + hh * 0.27, hh * 0.19, "#9a9ca3", "regular",
         max_w=sw * 0.45)
    # nút gọi (ống nghe)
    px, py = sr - sw * 0.1, ay
    c.save()
    c.rotate(-40, px, py)
    c.drawPath(rrect(px - hh * 0.2, py - hh * 0.06, px + hh * 0.2, py + hh * 0.06, hh * 0.05), fill("#2e7cf6"))
    c.drawPath(rrect(px - hh * 0.24, py - hh * 0.04, px - hh * 0.12, py + hh * 0.16, hh * 0.04), fill("#2e7cf6"))
    c.drawPath(rrect(px + hh * 0.12, py - hh * 0.04, px + hh * 0.24, py + hh * 0.16, hh * 0.04), fill("#2e7cf6"))
    c.restore()
    fs = sh * 0.028
    y = hy + hh + sh * 0.03
    text(c, d.get("day_label", "Today " + (d.get("time") or "02:47")), sl + sw / 2, y + fs * 0.6, fs * 0.62, "#7d8088",
         "semibold", "center")
    msgs = d.get("messages")
    if msgs is None:
        msgs = _SMS_DEFAULT
    _bubbles(c, sl, sr, y + fs * 1.6, sb - sh * 0.12, sw, sh, msgs)
    iy, ir = sb - sh * 0.085, sh * 0.024
    c.drawRect(skia.Rect.MakeLTRB(sl, iy - sh * 0.012, sr, sb), fill("#16171b"))
    c.drawCircle(sl + sw * 0.08, iy + ir, ir, fill("#2a2b30"))
    c.drawLine(sl + sw * 0.08 - ir * 0.5, iy + ir, sl + sw * 0.08 + ir * 0.5, iy + ir, stroke("#ffffff", ir * 0.2))
    c.drawLine(sl + sw * 0.08, iy + ir * 0.5, sl + sw * 0.08, iy + ir * 1.5, stroke("#ffffff", ir * 0.2))
    c.drawPath(rrect(sl + sw * 0.15, iy, sr - sw * 0.17, iy + ir * 2, ir), fill("#2a2b30"))
    text(c, d.get("placeholder", "Text message"), sl + sw * 0.19, iy + ir * 1.35, ir * 0.85, "#7d8088", "regular")
    c.drawCircle(sr - sw * 0.09, iy + ir, ir, fill("#2e7cf6"))
    c.drawPath(poly([(sr - sw * 0.09 - ir * 0.45, iy + ir * 0.55), (sr - sw * 0.09 + ir * 0.55, iy + ir),
                     (sr - sw * 0.09 - ir * 0.45, iy + ir * 1.45), (sr - sw * 0.09 - ir * 0.2, iy + ir)]), fill("#ffffff"))


def _call_icon(c, kind, cx, cy, r, col="#ffffff") -> None:
    if kind == "mute":
        c.drawPath(rrect(cx - r * 0.18, cy - r * 0.45, cx + r * 0.18, cy + r * 0.1, r * 0.18), fill(col))
        arc = skia.Path()
        arc.addArc(skia.Rect.MakeLTRB(cx - r * 0.32, cy - r * 0.3, cx + r * 0.32, cy + r * 0.26), 0, 180)
        c.drawPath(arc, stroke(col, r * 0.07))
        c.drawLine(cx, cy + r * 0.26, cx, cy + r * 0.42, stroke(col, r * 0.07))
        c.drawLine(cx - r * 0.4, cy - r * 0.45, cx + r * 0.4, cy + r * 0.4, stroke(col, r * 0.08))
    elif kind == "keypad":
        for i in range(3):
            for j in range(3):
                c.drawCircle(cx + (i - 1) * r * 0.3, cy + (j - 1) * r * 0.3, r * 0.08, fill(col))
    elif kind == "speaker":
        c.drawPath(poly([(cx - r * 0.4, cy - r * 0.14), (cx - r * 0.22, cy - r * 0.14), (cx, cy - r * 0.36),
                         (cx, cy + r * 0.36), (cx - r * 0.22, cy + r * 0.14), (cx - r * 0.4, cy + r * 0.14)]), fill(col))
        for k in (0.2, 0.36):
            a = skia.Path()
            a.addArc(skia.Rect.MakeLTRB(cx - r * k, cy - r * k, cx + r * k, cy + r * k), -50, 100)
            a.offset(r * 0.08, 0)
            c.drawPath(a, stroke(col, r * 0.06))
    elif kind == "add":
        c.drawLine(cx - r * 0.32, cy, cx + r * 0.32, cy, stroke(col, r * 0.08))
        c.drawLine(cx, cy - r * 0.32, cx, cy + r * 0.32, stroke(col, r * 0.08))
    elif kind == "video":
        c.drawPath(rrect(cx - r * 0.4, cy - r * 0.22, cx + r * 0.12, cy + r * 0.22, r * 0.08), fill(col))
        c.drawPath(poly([(cx + r * 0.14, cy - r * 0.05), (cx + r * 0.4, cy - r * 0.22), (cx + r * 0.4, cy + r * 0.22),
                         (cx + r * 0.14, cy + r * 0.05)]), fill(col))
    else:  # contacts
        c.drawCircle(cx, cy - r * 0.16, r * 0.16, fill(col))
        c.drawPath(rrect(cx - r * 0.3, cy + r * 0.05, cx + r * 0.3, cy + r * 0.38, r * 0.15), fill(col))


def _handset(c, cx, cy, r, col="#ffffff", ang=135) -> None:
    c.save()
    c.rotate(ang, cx, cy)
    arc = skia.Path()
    arc.addArc(skia.Rect.MakeLTRB(cx - r * 0.42, cy - r * 0.3, cx + r * 0.42, cy + r * 0.5), 200, 140)
    c.drawPath(arc, stroke(col, r * 0.16))
    c.restore()


def _screen_call(c, sl, st, sr, sb, d: dict) -> None:
    """Màn hình cuộc gọi: avatar chữ cái, tên, giờ gọi, lưới 3×2 nút tròn có nhãn, nút kết thúc đỏ."""
    sw, sh = sr - sl, sb - st
    c.drawRect(skia.Rect.MakeLTRB(sl, st, sr, sb), _lin((sl, st), (sl, sb), ["#263042", "#151a24", "#0b0d12"]))
    _status_bar(c, sl, st + sh * 0.012, sr, sh * 0.045, d.get("time") or "08:12")
    name = nfc(d.get("contact") or "Captain")
    ar, ax, ay = sw * 0.17, sl + sw / 2, st + sh * 0.22
    c.drawCircle(ax, ay, ar * 1.25, fill("#ffffff", 0.06))
    c.drawCircle(ax, ay, ar, fill(_avatar_color(name)))
    text(c, name[:1].upper(), ax, ay + ar * 0.36, ar * 1.0, "#ffffff", "bold", "center")
    text(c, name, ax, st + sh * 0.37, sh * 0.042, "#ffffff", "bold", "center", max_w=sw * 0.86)
    text(c, d.get("call_status", "00:00"), ax, st + sh * 0.41, sh * 0.024, "#aab0bc", "semibold", "center")
    labels = d.get("buttons") or ["Mute", "Keypad", "Speaker", "Add call", "Video", "Contacts"]
    kinds = ["mute", "keypad", "speaker", "add", "video", "contacts"]
    br = sw * 0.11
    active = int(d.get("active_button", 2))
    for k in range(6):
        bx = sl + sw * (0.22 + (k % 3) * 0.28)
        by = st + sh * (0.55 + (k // 3) * 0.15)
        on = k == active
        c.drawCircle(bx, by, br, fill("#ffffff", 0.9 if on else 0.14))
        _call_icon(c, kinds[k], bx, by, br, "#151a24" if on else "#ffffff")
        text(c, labels[k] if k < len(labels) else "", bx, by + br + sh * 0.03, sh * 0.019, "#d5d9e0", "semibold", "center",
             max_w=sw * 0.27)
    ex, ey, er = ax, sb - sh * 0.11, sw * 0.12
    c.drawCircle(ex, ey, er, fill("#e5413a"))
    _handset(c, ex, ey, er * 1.1)


def _pin(c, x, y, r, col="#e5413a") -> None:
    """Ghim bản đồ hình giọt nước, mũi ở (x, y)."""
    p = skia.Path()
    p.moveTo(x, y)
    p.cubicTo(x - r * 0.4, y - r * 0.9, x - r, y - r * 1.2, x - r, y - r * 1.8)
    p.arcTo(skia.Rect.MakeLTRB(x - r, y - r * 2.8, x + r, y - r * 0.8), 180, 180, False)
    p.cubicTo(x + r, y - r * 1.2, x + r * 0.4, y - r * 0.9, x, y)
    c.drawPath(oval(x, y, r * 0.6, r * 0.2), fill("#000000", 0.4))
    c.drawPath(p, fill(col))
    c.drawCircle(x, y - r * 1.8, r * 0.38, fill("#ffffff"))


def _screen_gps(c, sl, st, sr, sb, d: dict) -> None:
    """Bản đồ GPS tối: lưới phố, dải sông, khối xanh, tuyến xanh dương -> chấm vị trí + ghim đỏ; chip trên, thanh dưới."""
    sw, sh = sr - sl, sb - st
    c.drawRect(skia.Rect.MakeLTRB(sl, st, sr, sb), fill("#141821"))
    rng = random.Random(17)
    for k in range(9):                                       # phố dọc/ngang hơi nghiêng
        x = sl + sw * (k / 8) + rng.uniform(-20, 20)
        c.drawLine(x, st, x + sw * 0.08, sb, stroke("#262c39", sw * (0.02 if k % 3 else 0.035)))
    for k in range(12):
        y = st + sh * (k / 11) + rng.uniform(-20, 20)
        c.drawLine(sl, y, sr, y - sh * 0.03, stroke("#262c39", sw * (0.015 if k % 4 else 0.03)))
    river = smooth([(sl - 40, st + sh * 0.7), (sl + sw * 0.3, st + sh * 0.62), (sl + sw * 0.6, st + sh * 0.72),
                    (sr + 40, st + sh * 0.6)], close=False)
    c.drawPath(river, stroke("#1d3a5c", sw * 0.12))
    c.drawPath(river, stroke("#28507a", sw * 0.02, 0.6))
    gx, gy = sl + sw * 0.52, st + sh * 0.38
    c.drawPath(rrect(gx, gy, gx + sw * 0.26, gy + sh * 0.09, 12), fill("#2f7a4f", 0.55))
    c.drawPath(rrect(gx, gy, gx + sw * 0.26, gy + sh * 0.09, 12), stroke("#49c27a", 4, 0.8))
    route = [(sl + sw * 0.12, sb - sh * 0.2), (sl + sw * 0.22, st + sh * 0.6), (sl + sw * 0.4, st + sh * 0.55),
             (sl + sw * 0.45, st + sh * 0.45), (gx + sw * 0.12, gy + sh * 0.05)]
    rp = poly(route, close=False)
    c.drawPath(rp, stroke("#3d8bff", sw * 0.03, 0.35))
    c.drawPath(rp, stroke("#3d8bff", sw * 0.014))
    ex, ey = route[-1]
    for k, a in ((3.2, 0.12), (2.2, 0.2)):
        c.drawCircle(ex, ey, sw * 0.025 * k, fill("#3d8bff", a))
    c.drawCircle(ex, ey, sw * 0.03, fill("#ffffff"))
    c.drawCircle(ex, ey, sw * 0.021, fill("#3d8bff"))
    _pin(c, ex + sw * 0.07, ey - sh * 0.01, sw * 0.045)
    _status_bar(c, sl, st + sh * 0.012, sr, sh * 0.045, d.get("time") or "07:15")
    chip = nfc(d.get("chip", "Last location: Rider"))
    f = font(sh * 0.022, "semibold")
    tw = min(f.measureText(chip), sw * 0.78)
    cl, ct = sl + (sw - tw) / 2 - sw * 0.05, st + sh * 0.075
    c.drawPath(rrect(cl, ct, cl + tw + sw * 0.1, ct + sh * 0.05, sh * 0.025), fill("#ffffff", 0.94))
    c.drawCircle(cl + sw * 0.045, ct + sh * 0.025, sh * 0.009, fill("#3d8bff"))
    text(c, chip, cl + sw * 0.075, ct + sh * 0.033, sh * 0.022, "#1a1d24", "semibold", max_w=sw * 0.78)
    by = sb - sh * 0.15
    c.drawPath(rrect(sl + sw * 0.04, by, sr - sw * 0.04, sb - sh * 0.03, sh * 0.03), fill("#1d2230"))
    text(c, d.get("bottom_label", "Stopped 2 days"), sl + sw * 0.1, by + sh * 0.075, sh * 0.028, "#ffffff", "bold",
         max_w=sw * 0.5)
    c.drawPath(rrect(sr - sw * 0.34, by + sh * 0.03, sr - sw * 0.08, by + sh * 0.09, sh * 0.03), fill("#2fae5a"))
    text(c, d.get("button", "Start"), sr - sw * 0.21, by + sh * 0.071, sh * 0.024, "#ffffff", "bold", "center")


def _screen_draft(c, sl, st, sr, sb, d: dict) -> None:
    """Tin nhắn nháp chưa gửi: chú thích xám, bong bóng viên thuốc chữ to, nút gửi xanh; vết nứt màn hình."""
    sw, sh = sr - sl, sb - st
    c.drawRect(skia.Rect.MakeLTRB(sl, st, sr, sb), _lin((sl, st), (sl, sb), ["#101a30", "#070a12"]))
    _status_bar(c, sl, st + sh * 0.012, sr, sh * 0.045, d.get("time") or "07:12")
    text(c, d.get("caption", "Draft · not sent · 07:12"), sl + sw / 2, st + sh * 0.5, sh * 0.022, "#8a90a0",
         "semibold", "center", max_w=sw * 0.9)
    fs = sh * 0.04
    f = font(fs, "bold")
    lines = wrap_text(d.get("draft", "I know where they are."), f, sw * 0.62)[:3]
    bh = len(lines) * fs * 1.3 + fs * 1.2
    bl, bt = sl + sw * 0.05, st + sh * 0.53
    c.drawPath(rrect(bl, bt, sr - sw * 0.2, bt + bh, min(bh / 2, fs * 1.2)), fill("#252c3e"))
    for i, ln in enumerate(lines):
        c.drawString(ln, bl + fs * 0.8, bt + fs * 0.6 + fs * (1.0 + i * 1.3) - fs * 0.15, f, fill("#ffffff"))
    r = sw * 0.07
    sx, sy = sr - sw * 0.11, bt + bh / 2
    c.drawCircle(sx, sy, r, fill("#2e7cf6"))
    c.drawLine(sx, sy + r * 0.45, sx, sy - r * 0.45, stroke("#ffffff", r * 0.16))
    c.drawPath(poly([(sx - r * 0.4, sy - r * 0.05), (sx, sy - r * 0.5), (sx + r * 0.4, sy - r * 0.05)], close=False),
               stroke("#ffffff", r * 0.16))
    if d.get("cracked", True):
        _crack(c, sl + sw * float(d.get("crack_x", 0.66)), st + sh * float(d.get("crack_y", 0.3)), sw * 0.95,
               seed=int(d.get("crack_seed", 3)), w=sw * 0.006)


SCREENS = {"sms": _screen_sms, "call": _screen_call, "gps": _screen_gps, "draft": _screen_draft}


def _phone_in_hand(screen: str, p: dict, size, side=None):
    s, c = _begin(size)
    draw_background(c, p.get("bg", "dark_vignette"), int(LW), int(LH), p)
    ph = LH * float(p.get("phone_h", 0.86))
    pw = ph * 0.49
    cx, cy = LW * (0.64 if side else 0.5), LH * 0.53
    rect = skia.Rect.MakeLTRB(cx - pw / 2, cy - ph / 2, cx + pw / 2, cy + ph / 2)
    sleeve, skin = p.get("sleeve_color", "#2b3550"), p.get("skin", "#c9926a")
    hands = p.get("hands", True)
    c.save()
    c.rotate(float(p.get("tilt", -4)), cx, cy)
    if hands:
        _hand(c, cx + pw * 0.36, LH + 120, -16, 1.45, sleeve, skin, "grip", "back", mirror=True)
    draw_phone(c, rect, screen, p)
    if hands:
        _hand(c, cx + pw * 0.36, LH + 120, -16, 1.45, sleeve, skin, "grip", "front", mirror=True)
    c.restore()
    if side:
        side(c)
    return s.makeImageSnapshot()


def ins_phone_sms_hand(p, size):
    return _phone_in_hand("sms", p, size)


def ins_phone_call_screen(p, size):
    return _phone_in_hand("call", p, size)


def ins_phone_gps_map(p, size):
    card = p.get("card")

    def side(c):
        if card:
            _card(c, 260, 640, 1300, [(_spaced(card.get("label", "GPS")), 46, "#7a7466", "bold"),
                                      (card.get("title", "STOPPED AT SHOP 48 HRS"), 92, "#1f2430", "extrabold"),
                                      (card.get("sub", "LAST UPDATE 2 DAYS AGO"), 50, "#c8352e", "bold")],
                  accent=card.get("accent", "#3d8bff"))
    return _phone_in_hand("gps", p, size, side if card else None)


def ins_phone_draft_cracked(p, size):
    return _phone_in_hand("draft", p, size)


# =================================================================== giấy tờ
def ins_receipt_thermal(p, size):
    """Hoá đơn nhiệt mép xé + 2 thẻ số liệu bên phải."""
    s, c = _begin(size)
    draw_background(c, p.get("bg", "wood_dark"), int(LW), int(LH), p)
    l, t, r, b = 520.0, 110.0, 1640.0, 2060.0
    rng = random.Random(2)
    path = skia.Path()
    path.moveTo(l, t)
    x = l
    while x < r:
        x = min(r, x + rng.uniform(24, 44))
        path.lineTo(x, t + rng.uniform(0, 22))
    y = t
    path.lineTo(r, b)
    x = r
    while x > l:
        x = max(l, x - rng.uniform(24, 44))
        path.lineTo(x, b - rng.uniform(0, 22))
    path.close()
    c.save()
    c.rotate(-3, (l + r) / 2, (t + b) / 2)
    _shadow(c, path, 30, 18, 0.55)
    c.drawPath(path, _lin((l, t), (r, b), ["#fbfaf5", "#efece2"]))
    cx = (l + r) / 2
    ink = "#2a2a30"
    y = t + 150
    text(c, p.get("shop", "GOLDEN STEAM BUNS"), cx, y, 66, ink, "extrabold", "center", max_w=r - l - 120)
    y += 70
    text(c, p.get("address", "14 Market Lane · Open 4 AM"), cx, y, 36, "#6a6a72", "regular", "center", max_w=r - l - 120)
    y += 60
    sep = _dash("#8a8a92", 4, 16, 12)
    c.drawLine(l + 60, y, r - 60, y, sep)
    y += 80
    text(c, p.get("customer", "Customer: Mr. K"), l + 80, y, 42, ink, "semibold")
    text(c, p.get("datetime", "12/03 · 04:10"), r - 80, y, 42, ink, "semibold", "right")
    y += 60
    c.drawLine(l + 60, y, r - 60, y, sep)
    y += 90
    items = p.get("items")
    if items is None:
        items = [["Minced pork 5 kg", "750"], ["Shallots 1 bunch", "20"], ["Flour 25 kg", "640"]]
    for item, amt in items:
        text(c, item, l + 80, y, 46, ink, "regular", max_w=(r - l) * 0.62)
        text(c, amt, r - 80, y, 46, ink, "semibold", "right")
        y += 78
    y += 10
    c.drawLine(l + 60, y, r - 60, y, sep)
    y += 110
    text(c, "TOTAL", l + 80, y, 64, ink, "extrabold")
    text(c, p.get("total", "1,410"), r - 80, y, 64, ink, "extrabold", "right")
    y += 50
    c.drawLine(l + 60, y, r - 60, y, sep)
    y += 120
    text(c, p.get("footer", "THANK YOU"), cx, y, 54, ink, "bold", "center")
    for k in range(34):                                    # mã vạch
        bx = l + 220 + k * 20
        if bx > r - 220:
            break
        c.drawRect(skia.Rect.MakeLTRB(bx, y + 60, bx + (12 if k % 3 else 6), y + 190), fill(ink))
    c.restore()
    cards = p.get("cards")
    if cards is None:
        cards = [{"label": "BUNS SOLD PER DAY", "value": "500", "icon": "bun", "color": "#e8b93a", "bar": 0.9},
                 {"label": "PORK BOUGHT PER DAY", "value": "0 kg", "icon": "scale", "color": "#c8352e",
                  "value_color": "#c8352e", "bar": 0.04}]
    cy = 380.0
    for cd in cards[:2]:
        col = cd.get("color", "#e8b93a")
        h = _card(c, 2000, cy, 1500, [(_spaced(cd.get("label", "")), 40, "#7a7466", "bold"),
                                      (cd.get("value", ""), 150, cd.get("value_color", "#1f2430"), "extrabold")],
                  accent=col)
        c.drawPath(rrect(2080, cy + h - 70, 3420, cy + h - 44, 13), fill("#e3dccb"))
        c.drawPath(rrect(2080, cy + h - 70, 2080 + 1340 * float(cd.get("bar", 0.8)), cy + h - 44, 13), fill(col))
        ix, iy = 3300, cy + 190
        if cd.get("icon") == "scale":
            c.drawPath(rrect(ix - 90, iy - 10, ix + 90, iy + 90, 20), fill("#5a5f6a"))
            c.drawPath(oval(ix, iy - 30, 120, 26), fill("#9aa0aa"))
            c.drawCircle(ix, iy + 40, 34, fill("#ffffff"))
            c.drawLine(ix, iy + 40, ix + 20, iy + 18, stroke("#c8352e", 6))
        else:                                              # bánh bao
            c.drawPath(oval(ix, iy + 30, 110, 70), fill("#f4efe4"))
            c.drawPath(oval(ix, iy + 10, 90, 70), fill("#fbf8f1"))
            for k in range(5):
                a = math.radians(-150 + k * 30)
                c.drawLine(ix, iy - 50, ix + math.cos(a) * 70, iy - 50 + math.sin(a) * -40 + 50, stroke("#d9cfbc", 6))
        cy += h + 120
    _vignette(c, 0.35)
    return s.makeImageSnapshot()


def _hatch(c, clip: skia.Path, col, step=34, w=4, a=0.8) -> None:
    b = clip.getBounds()
    c.save()
    c.clipPath(clip, skia.ClipOp.kIntersect, True)
    x = b.left() - b.height()
    while x < b.right():
        c.drawLine(x, b.bottom(), x + b.height(), b.top(), stroke(col, w, a))
        x += step
    c.restore()


def _dim(c, x0, y0, x1, y1, label, col, size=40, dash=False) -> None:
    p = _dash(col, 4, 18, 12) if dash else stroke(col, 4)
    c.drawLine(x0, y0, x1, y1, p)
    ang = math.atan2(y1 - y0, x1 - x0)
    for (x, y, s_) in ((x0, y0, 1), (x1, y1, -1)):
        a1, a2 = ang + 0.4, ang - 0.4
        c.drawPath(poly([(x, y), (x + s_ * math.cos(a1) * 30, y + s_ * math.sin(a1) * 30),
                         (x + s_ * math.cos(a2) * 30, y + s_ * math.sin(a2) * 30)]), fill(col))
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    if abs(x1 - x0) > abs(y1 - y0):
        text(c, label, mx, my - 18, size, col, "bold", "center")
    else:
        text(c, label, mx + 24, my + size * 0.35, size, col, "bold")


def ins_blueprint_plan(p, size):
    """Bản vẽ kỹ thuật: mặt cắt A-A (tầng hầm gạch chéo) + mặt bằng tầng trệt + khung tên + dấu duyệt tím."""
    s, c = _begin(size)
    draw_background(c, p.get("bg", "wood_dark"), int(LW), int(LH), p)
    blue = "#2a5aa8"
    c.save()
    c.rotate(-1.5, LW / 2, LH / 2)
    sheet = skia.Rect.MakeLTRB(250, 130, 3590, 2030)
    _shadow(c, sheet, 34, 18, 0.6)
    c.drawRect(sheet, _lin((250, 130), (3590, 2030), ["#f6f8fb", "#e8eef6"]))
    for k in range(0, 3340, 120):                         # lưới mờ
        c.drawLine(250 + k, 130, 250 + k, 2030, stroke("#c9d6ea", 2, 0.5))
    for k in range(0, 1900, 120):
        c.drawLine(250, 130 + k, 3590, 130 + k, stroke("#c9d6ea", 2, 0.5))
    c.drawRect(skia.Rect.MakeLTRB(310, 190, 3530, 1970), stroke(blue, 6))
    c.drawRect(skia.Rect.MakeLTRB(330, 210, 3510, 1950), stroke(blue, 2))
    # --- mặt cắt
    gy = 1380.0
    bl, br = 560.0, 1680.0
    text(c, p.get("section_title", "SECTION A-A"), 420, 320, 64, blue, "extrabold")
    c.drawLine(420, 340, 860, 340, stroke(blue, 5))
    c.drawPath(poly([(bl - 40, 520), ((bl + br) / 2, 400), (br + 40, 520)], close=False), stroke(blue, 6))
    c.drawRect(skia.Rect.MakeLTRB(bl, 520, br, gy), stroke(blue, 6))
    for k, fy in enumerate((740.0, 960.0, 1140.0)):
        c.drawLine(bl, fy, br, fy, stroke(blue, 5))
    for k, (y0, lab) in enumerate(((520, "FL 4"), (740, "FL 3"), (960, "FL 2"))):
        text(c, lab, bl - 30, y0 + 120, 38, blue, "bold", "right")
        for wx in (bl + 160, bl + 520, bl + 880):
            c.drawRect(skia.Rect.MakeLTRB(wx, y0 + 60, wx + 200, y0 + 160), stroke(blue, 3))
    rooms = p.get("rooms") or ["SHOP", "KITCHEN", "COLD ROOM"]
    xs = [bl, bl + 373, bl + 746, br]
    for i, rm in enumerate(rooms[:3]):
        if i:
            c.drawLine(xs[i], 1140, xs[i], gy, stroke(blue, 5))
        text(c, rm, (xs[i] + xs[i + 1]) / 2, 1280, 40, blue, "bold", "center", max_w=340)
    c.drawLine(380, gy, 1860, gy, stroke(blue, 8))
    for x in range(400, 1860, 40):                       # vạch đất
        if not (xs[2] <= x <= br):
            c.drawLine(x, gy + 6, x - 26, gy + 36, stroke(blue, 3, 0.7))
    base = skia.Path()
    base.addRect(skia.Rect.MakeLTRB(xs[2], gy, br, gy + 260))
    c.drawPath(base, fill("#c8352e", 0.08))
    _hatch(c, base, RED_INK, 30, 4, 0.7)
    c.drawPath(base, _dash(RED_INK, 6, 24, 14))
    text(c, p.get("basement_label", "BASEMENT (FILLED)"), (xs[2] + br) / 2, gy + 330, 40, RED_INK, "bold", "center")
    _dim(c, br + 90, gy, br + 90, gy + 260, p.get("depth", "3.00"), RED_INK, 40)
    text(c, "GROUND LINE 0.00", 400, gy - 20, 30, blue, "semibold")
    # --- mặt bằng
    pl, pt_, pr, pb = 2050.0, 560.0, 3420.0, 1060.0
    text(c, p.get("plan_title", "GROUND FLOOR"), 2050, 320, 64, blue, "extrabold")
    c.drawLine(2050, 340, 2560, 340, stroke(blue, 5))
    c.drawRect(skia.Rect.MakeLTRB(pl, pt_, pr, pb), stroke(blue, 16))
    pxs = [pl, pl + 460, pl + 920, pr]
    for i in (1, 2):
        c.drawLine(pxs[i], pt_, pxs[i], pt_ + 300, stroke(blue, 12))
        c.drawLine(pxs[i], pt_ + 420, pxs[i], pb, stroke(blue, 12))
        arc = skia.Path()
        arc.addArc(skia.Rect.MakeLTRB(pxs[i] - 120, pt_ + 300, pxs[i] + 120, pt_ + 540), -90, 90)
        c.drawPath(arc, stroke(blue, 3))
        c.drawLine(pxs[i], pt_ + 300, pxs[i] + 120, pt_ + 420, stroke(blue, 4))
    c.drawRect(skia.Rect.MakeLTRB(pl + 140, pb - 8, pl + 360, pb + 8), fill("#f2f5f9"))
    arc = skia.Path()
    arc.addArc(skia.Rect.MakeLTRB(pl + 140, pb - 220, pl + 580, pb + 220), 180, 90)
    c.drawPath(arc, stroke(blue, 3))
    for i, rm in enumerate(rooms[:3]):
        text(c, rm, (pxs[i] + pxs[i + 1]) / 2, pt_ + 170, 40, blue, "bold", "center", max_w=400)
    c.drawRect(skia.Rect.MakeLTRB(pxs[2] + 50, pt_ + 50, pr - 50, pb - 50), _dash(RED_INK, 6, 26, 16))
    text(c, p.get("plan_note", "basement line (filled)"), (pxs[2] + pr) / 2, pb - 90, 32, RED_INK, "semibold", "center",
         max_w=420)
    _dim(c, pl, pb + 90, pr, pb + 90, p.get("length", "16.00 m"), blue, 40)
    _dim(c, pl - 90, pt_, pl - 90, pb, "", blue, 40)
    c.save()
    c.rotate(-90, pl - 120, (pt_ + pb) / 2)
    text(c, p.get("width", "4.00 m"), pl - 120, (pt_ + pb) / 2, 40, blue, "bold", "center")
    c.restore()
    # --- khung tên
    tl, tt, tr_, tb = 2050.0, 1360.0, 3460.0, 1900.0
    c.drawRect(skia.Rect.MakeLTRB(tl, tt, tr_, tb), stroke(blue, 5))
    rows = p.get("title_block") or ["DISTRICT OFFICE", "4-STOREY SHOPHOUSE", "REQUEST: FILL BASEMENT", "DATE: 1997"]
    rh = (tb - tt) / (len(rows) + 1)
    for i, row in enumerate(rows):
        y = tt + rh * (i + 1)
        c.drawLine(tl, y, tr_, y, stroke(blue, 3))
        text(c, row, tl + 40, y - rh * 0.3, rh * 0.42, blue, "bold" if i == 0 else "semibold", max_w=820)
    c.drawLine(tl + 900, tt, tl + 900, tb, stroke(blue, 3))
    text(c, "SIGNATURE", tl + 940, tb - 30, 28, blue, "semibold")
    sig = smooth([(tl + 960, tb - 120), (tl + 1020, tb - 180), (tl + 1060, tb - 110), (tl + 1120, tb - 190),
                  (tl + 1180, tb - 120), (tl + 1300, tb - 150)], close=False)
    c.drawPath(sig, stroke("#1a2a55", 6))
    # dấu duyệt
    sx, sy, sr_ = 3180.0, 1580.0, 170.0
    c.save()
    c.rotate(-14, sx, sy)
    pc = "#6a3fa0"
    c.drawCircle(sx, sy, sr_, stroke(pc, 12, 0.75))
    c.drawCircle(sx, sy, sr_ * 0.78, stroke(pc, 5, 0.75))
    text(c, p.get("stamp", "APPROVED"), sx, sy + 14, 50, pc, "extrabold", "center", a=0.8, max_w=sr_ * 1.4)
    text(c, p.get("stamp_year", "1997"), sx, sy + 80, 36, pc, "bold", "center", a=0.8)
    c.drawPath(_star(sx, sy - 75, 26), fill(pc, 0.75))
    c.restore()
    # vết cà phê
    c.drawCircle(820, 1760, 150, stroke("#8a5a2e", 14, 0.25))
    c.drawCircle(830, 1765, 138, fill("#a87440", 0.06))
    c.restore()
    _vignette(c, 0.4)
    return s.makeImageSnapshot()


def _star(cx, cy, r, n=5) -> skia.Path:
    pts = []
    for k in range(n * 2):
        a = -math.pi / 2 + k * math.pi / n
        rr = r if k % 2 == 0 else r * 0.45
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    return poly(pts)


def ins_depth_diagram(p, size):
    """Infographic mặt cắt độ sâu: 3 khối trên mặt đất, tầng hầm đỏ gạch chéo, chấm GPS, kích thước -3 m, thẻ độ cao."""
    s, c = _begin(size)
    c.drawRect(skia.Rect.MakeWH(LW, LH), _lin((0, 0), (0, LH), ["#0f1b36", "#0a1226"]))
    for x in range(0, int(LW), 120):
        c.drawLine(x, 0, x, LH, stroke("#1a2a4c", 2, 0.6))
    for y in range(0, int(LH), 120):
        c.drawLine(0, y, LW, y, stroke("#1a2a4c", 2, 0.6))
    gy = 1150.0
    c.drawRect(skia.Rect.MakeLTRB(0, gy, LW, LH), fill("#2a1f1a", 0.55))
    rng = random.Random(9)
    for _ in range(500):
        c.drawCircle(rng.uniform(0, LW), rng.uniform(gy + 20, LH), rng.uniform(3, 9), fill("#6a5240", 0.35))
    c.drawLine(300, gy, 3540, gy, stroke("#e8edf5", 8))
    text(c, p.get("ground_label", "STREET LEVEL 0 m"), 320, gy - 30, 46, "#e8edf5", "bold")
    boxes = p.get("boxes") or [["STOREFRONT", "#4fc3e8"], ["KITCHEN", "#f3c94e"], ["COLD ROOM", "#8fb8ff"]]
    x = 860.0
    bw = 620.0
    for name, col in boxes[:3]:
        r = rrect(x, 680, x + bw, gy - 12, 18)
        c.drawPath(r, fill(col, 0.12))
        c.drawPath(r, stroke(col, 8))
        text(c, name, x + bw / 2, 930, 50, col, "extrabold", "center", max_w=bw - 60)
        x += bw + 30
    c.drawRect(skia.Rect.MakeLTRB(860, 300, x - 30, 650), stroke("#5a6a8a", 4, 0.7))
    for fy in (416, 532):
        c.drawLine(860, fy, x - 30, fy, stroke("#5a6a8a", 3, 0.5))
    bl, br = x - 30 - bw, x - 30
    base = skia.Path()
    base.addRect(skia.Rect.MakeLTRB(bl, gy + 30, br, gy + 470))
    c.drawPath(base, fill("#e5413a", 0.12))
    _hatch(c, base, "#e5413a", 40, 4, 0.35)
    c.drawPath(base, _dash("#ff5a4f", 8, 30, 18))
    text(c, p.get("basement_label", "BASEMENT"), (bl + br) / 2, gy + 110, 44, "#ff8a80", "bold", "center")
    dx, dy = (bl + br) / 2, gy + 280
    for k, a in ((150, 0.12), (100, 0.22), (60, 0.35)):
        c.drawCircle(dx, dy, k, fill("#3d8bff", a))
    c.drawCircle(dx, dy, 40, fill("#ffffff"))
    c.drawCircle(dx, dy, 28, fill("#3d8bff"))
    _dim(c, br + 110, gy, br + 110, gy + 470, p.get("depth", "-3 m"), "#ff5a4f", 64, dash=True)
    text(c, p.get("caption", 'Basement 4 x 6 m · "filled 1997"'), LW / 2, 1900, 58, "#cfd8e8", "semibold", "center",
         max_w=3000)
    card = p.get("card") or {}
    _card(c, 2980, 160, 700, [(_spaced(card.get("label", "ALTITUDE")), 40, "#7a7466", "bold"),
                              (card.get("value", "-3 m"), 130, "#c8352e", "extrabold"),
                              (card.get("sub", "UNDERGROUND"), 46, "#1f2430", "bold")], accent="#3d8bff")
    return s.makeImageSnapshot()


_NAMES = ["Anna K.", "Ben T.", "Cara L.", "Dina P.", "Evan R.", "Faye M.", "Gina S.", "Hugo N.", "Iris W.", "Jade C.",
          "Kai D.", "Lena F.", "Milo G.", "Nora H.", "Owen J.", "Pia V.", "Quinn B.", "Rosa Y.", "Sam O.", "Tia Z.",
          "Uma E.", "Vic A.", "Wren I."]
_NOTES = ["bun shop", "night shift", "rider", "nursing student", "", "market", "tenant", "", "late bus", "",
          "bun shop", "student", "", "rider", "", "night shift", "", "bun shop", "", "tenant", "", "rider", "last seen"]


def ins_notebook_list_hand(p, size):
    """Sổ kẻ dòng 2 trang: danh sách người mất tích viết tay, 2 dòng đầu khoanh đỏ, ngón tay chỉ dòng cuối."""
    s, c = _begin(size)
    _wood_top(c, p.get("desk", "#9a6a42"))
    l, t, w, h = 360.0, 150.0, 3120.0, 1800.0
    mid = l + w / 2
    cover = rrect(l - 40, t - 40, l + w + 40, t + h + 50, 30)
    _shadow(c, cover, 40, 24, 0.6)
    c.drawPath(cover, fill("#2b3a5a"))
    for side in (0, 1):
        pl = l if side == 0 else mid
        c.drawRect(skia.Rect.MakeLTRB(pl, t, pl + w / 2, t + h),
                   _lin((pl, 0), (pl + w / 2, 0), ["#efe7d2", "#f8f2e2"] if side == 0 else ["#f8f2e2", "#efe7d2"]))
    c.drawRect(skia.Rect.MakeLTRB(mid - 60, t, mid + 60, t + h),
               _lin((mid - 60, 0), (mid + 60, 0), [("#000000", 0.0), ("#000000", 0.22), ("#000000", 0.0)]))
    lh = 118.0
    top = t + 250
    for side in (0, 1):
        pl = l if side == 0 else mid
        y = top
        while y < t + h - 40:
            c.drawLine(pl + 40, y, pl + w / 2 - 40, y, stroke("#a9c4e0", 3))
            y += lh
        c.drawLine(pl + 190, t, pl + 190, t + h, stroke("#d0302a", 4, 0.8))
    text(c, p.get("title", "MISSING · BLOCK 41"), l + 230, t + 150, 86, RED_INK, "extrabold", max_w=w / 2 - 300)
    n = int(p.get("count", 23))
    rows = p.get("rows") or [[_NAMES[i % len(_NAMES)], str(18 + (i * 7) % 8), f"{(i * 5) % 28 + 1:02d}/{(i % 12) + 1:02d}",
                              _NOTES[i % len(_NOTES)]] for i in range(n)]
    per = int((t + h - top) // lh)
    f = font(50, "semibold")
    rng = random.Random(4)
    boxed = set(p.get("boxed_rows", [0, 1]))
    last_pos = None
    for i, row in enumerate(rows[:per * 2]):
        side, k = divmod(i, per)
        pl = l if side == 0 else mid
        y = top + lh * (k + 1) - 26
        c.save()
        c.rotate(rng.uniform(-0.7, 0.7), pl + 60, y)
        cells = [f"{i + 1}.", row[0], row[1], row[2], row[3] if len(row) > 3 else ""]
        xs = [pl + 70, pl + 220, pl + 680, pl + 830, pl + 1100]
        for j, cell in enumerate(cells):
            col = "#b5332b" if j == 4 and cell else INK
            text(c, cell, xs[j], y, 50 if j != 4 else 42, col, "semibold", max_w=420 if j == 4 else 440)
        c.restore()
        if i in boxed:
            c.drawPath(rrect(pl + 200, y - 74, pl + w / 2 - 50, y + 26, 30), stroke(RED_INK, 7, 0.9))
        last_pos = (pl + 420, y - 20)
    for (wx, wy, wr) in ((l + 1150, t + 1500, 110), (mid + 1180, t + 420, 90)):
        c.drawCircle(wx, wy, wr, stroke("#7a9ab8", 10, 0.22))
        c.drawCircle(wx + 8, wy + 6, wr * 0.9, fill("#9ab8d6", 0.07))
    if last_pos and p.get("hands", True):
        tx, ty = last_pos
        _hand(c, tx + 380, ty + 1020, -28, 1.35, p.get("sleeve_color", "#2b3550"), p.get("skin", "#c9926a"), "point",
              "all")
    card = p.get("card") or {}
    _card(c, l + w - 600, t + 24, 520, [(_spaced(card.get("label", "MISSING")), 32, "#7a7466", "bold"),
                                        (card.get("value", str(n)), 84, "#c8352e", "extrabold")], pad=26)
    _vignette(c, 0.35)
    return s.makeImageSnapshot()


def ins_missing_poster_numbered(p, size):
    """Tờ tìm người nghiêng, dán băng keo, huy hiệu số đỏ, dải xé số điện thoại ở đáy, nền tường mờ."""
    s, c = _begin(size)
    draw_background(c, p.get("bg", "wall_grey"), int(LW), int(LH), p)
    rng = random.Random(6)
    for _ in range(9):                                     # giấy cũ mờ phía sau
        x, y = rng.uniform(0, LW), rng.uniform(0, LH)
        c.drawPath(rrect(x, y, x + rng.uniform(300, 600), y + rng.uniform(400, 700), 6), _blurred("#e9e4d8", 0.35, 18))
    pw, ph = 1250.0, 1560.0
    l, t = LW / 2 - pw / 2, 120.0
    c.save()
    c.rotate(float(p.get("rotation", -4)), LW / 2, LH / 2)
    tabs_t = t + ph
    tab_w = pw / 8
    for k in range(8):                                     # dải xé
        x0 = l + k * tab_w
        r = skia.Rect.MakeLTRB(x0 + 6, tabs_t - 4, x0 + tab_w - 6, tabs_t + 330 - (60 if k == 3 else 0))
        if k == 5:
            continue                                       # 1 dải đã bị xé
        _shadow(c, r, 12, 8, 0.35)
        c.drawRect(r, fill("#f4f1ea"))
        c.save()
        c.rotate(90, r.centerX(), r.centerY())
        text(c, p.get("phone", "555-0193"), r.centerX(), r.centerY() + 14, 40, "#1a1a1e", "bold", "center", max_w=280)
        c.restore()
        c.drawLine(x0 + tab_w - 6, tabs_t, x0 + tab_w - 6, tabs_t + 300, _dash("#9a958a", 3, 10, 8))
    pd = {"header": "M I S S I N G", "name": "MAY LIN", "age": "Age 22 · 1.58 m", "desc": "Last seen near the bun shop",
          "datetime": "11:40 PM · OCT 3", "photo": "archetype:nu_tre_van_phong"}
    pd.update({k: v for k, v in p.items() if v is not None})
    pd.pop("phone", None)                                  # số điện thoại nằm ở dải xé
    draw_missing_poster(c, skia.Rect.MakeLTRB(l, t, l + pw, t + ph), pd)
    bx, by, br = l + pw - 70, t + 290, 120.0
    c.drawCircle(bx + 8, by + 12, br, _blurred("#000000", 0.4, 14))
    c.drawCircle(bx, by, br, fill("#c8352e"))
    c.drawCircle(bx, by, br * 0.84, stroke("#ffffff", 8))
    text(c, str(p.get("number", 7)), bx, by + 56, 160, "#ffffff", "extrabold", "center")
    c.restore()
    _vignette(c, 0.5)
    return s.makeImageSnapshot()


# =================================================================== kho lạnh / đồng hồ
def _corrugated(c, base="#a9bccd") -> None:
    x = 0.0
    k = 0
    while x < LW:
        c.drawRect(skia.Rect.MakeLTRB(x, 0, x + 80, LH), _lin((x, 0), (x + 80, 0), [shade(base, -0.12), shade(base, 0.12),
                                                                                    shade(base, -0.05)]))
        x += 80
        k += 1
    c.drawRect(skia.Rect.MakeWH(LW, LH), _lin((0, 0), (0, LH), [("#ffffff", 0.55), ("#ffffff", 0.05), ("#ffffff", 0.2)],
                                            [0, 0.45, 1]))
    rng = random.Random(11)
    for _ in range(260):
        r = rng.uniform(3, 11)
        c.drawCircle(rng.uniform(0, LW), rng.uniform(0, LH), r, fill("#ffffff", rng.uniform(0.3, 0.8)))


def _frost_cap(c, l, r, y, depth=70, seed=5) -> None:
    rng = random.Random(seed)
    pts = [(l - 10, y + 10)]
    x = l
    while x < r:
        x += rng.uniform(40, 90)
        pts.append((min(x, r + 10), y - rng.uniform(10, depth)))
    pts.append((r + 10, y + 10))
    c.drawPath(smooth(pts), fill("#f6fbff"))
    for _ in range(int((r - l) / 120)):                   # nhũ băng
        ix = rng.uniform(l + 30, r - 30)
        ln = rng.uniform(40, 120)
        c.drawPath(poly([(ix - 16, y), (ix + 16, y), (ix, y + ln)]), fill("#e6f3fb", 0.95))


def ins_cold_room_alarm(p, size):
    """Bảng nhiệt kế kho lạnh trên vách tôn phủ sương: LCD đen số LED đỏ, chấm ALARM, 3 nút."""
    s, c = _begin(size)
    _corrugated(c, p.get("wall", "#a9bccd"))
    l, t, r, b = 1120.0, 420.0, 2720.0, 1840.0
    panel = rrect(l, t, r, b, 50)
    _shadow(c, panel, 40, 24, 0.55)
    c.drawPath(panel, _lin((l, t), (l, b), ["#f4f6f7", "#d9dee2"]))
    c.drawPath(rrect(l + 20, t + 20, r - 20, b - 20, 36), stroke("#b9c1c8", 6))
    for (sx, sy) in ((l + 70, t + 70), (r - 70, t + 70), (l + 70, b - 70), (r - 70, b - 70)):
        c.drawCircle(sx, sy, 20, fill("#9aa3ab"))
        c.drawLine(sx - 12, sy, sx + 12, sy, stroke("#6a737b", 5))
    text(c, p.get("label", "COLD ROOM"), (l + r) / 2, t + 210, 110, "#1d2a3a", "extrabold", "center", max_w=r - l - 300)
    ll, lt, lr, lb = l + 180, t + 300, r - 180, t + 860
    c.drawPath(rrect(ll - 20, lt - 20, lr + 20, lb + 20, 30), fill("#5a636b"))
    c.drawPath(rrect(ll, lt, lr, lb, 20), fill("#0a0c0f"))
    red = p.get("digit_color", "#ff3b2f")
    val = str(p.get("value", "-16.1"))
    unit = p.get("unit", "°C")
    uw = font(130, "bold").measureText(nfc(unit)) + 40
    dh = min(380.0, (lr - ll - 160 - uw) / max(1e-3, _seven_width(val, 1.0)))
    est = _seven_width(val, dh)
    x0 = ll + (lr - ll - est - uw) / 2
    top = lt + (lb - lt - dh) / 2
    _seven(c, val, x0, top, dh, red, off="#1c0f0f", glow=True)
    text(c, unit, x0 + est + 40, top + 130, 130, red, "bold")
    c.drawRect(skia.Rect.MakeLTRB(ll, lt, lr, lt + 60), fill("#ffffff", 0.05))
    ay = lb + 150
    c.drawCircle(ll + 60, ay - 34, 44, _blurred(red, 0.7, 26))
    c.drawCircle(ll + 60, ay - 34, 34, fill(red))
    c.drawCircle(ll + 50, ay - 44, 10, fill("#ffffff", 0.7))
    text(c, p.get("alarm", "ALARM"), ll + 130, ay, 90, red, "extrabold")
    text(c, p.get("setpoint", "SET -18.0"), lr, ay, 60, "#5a6570", "bold", "right")
    by = b - 210
    for k, lab in enumerate(("SET", "up", "down")):
        bx = (l + r) / 2 + (k - 1) * 360
        c.drawCircle(bx, by + 10, 105, fill("#9aa3ab"))
        c.drawCircle(bx, by, 100, _lin((bx, by - 100), (bx, by + 100), ["#ffffff", "#c9d0d6"]))
        if lab == "SET":
            text(c, "SET", bx, by + 26, 64, "#2a3440", "extrabold", "center")
        else:
            d = -1 if lab == "up" else 1
            c.drawPath(poly([(bx - 40, by - d * 22), (bx + 40, by - d * 22), (bx, by + d * 36)]), fill("#2a3440"))
    _frost_cap(c, l, r, t + 10)
    _vignette(c, 0.4)
    return s.makeImageSnapshot()


def ins_wristwatch_digital(p, size):
    """Cẳng tay băng gạc nằm ngang khung + đồng hồ điện tử vuông đen (không thương hiệu), LCD 7 đoạn."""
    s, c = _begin(size)
    _bokeh(c, "#24343a", "#0b1214", ["#f0a25a", "#4fc3c0", "#ffffff", "#e86a5a"], seed=5)
    skin = p.get("skin", "#c9926a")
    ay = 1180.0
    c.drawPath(capsule(-300, ay + 60, 4200, ay - 40, 600, 520), _blurred("#000000", 0.45, 40))
    c.drawPath(capsule(-300, ay, 4300, ay - 60, 560, 470), _lin((0, ay - 300), (0, ay + 300),
                                                                [shade(skin, 0.1), skin, shade(skin, -0.25)]))
    c.drawPath(smooth([(-100, ay + 120), (900, ay + 140), (1800, ay + 100), (2800, ay + 60), (4000, ay + 40)],
                      close=False), stroke(shade(skin, -0.2), 8, 0.4))
    if p.get("bandage", True):                             # băng gạc quấn chéo
        c.save()
        c.clipPath(capsule(-300, ay, 4300, ay - 60, 560, 470), skia.ClipOp.kIntersect, True)
        for k in range(7):
            x = 260 + k * 150
            band = poly([(x, ay - 330), (x + 170, ay - 330), (x + 60, ay + 330), (x - 110, ay + 330)])
            c.drawPath(band, fill("#f4f2ec" if k % 2 else "#e6e3da"))
            c.drawPath(band, stroke("#c9c5bb", 4, 0.6))
        c.restore()
    wx, wy = 2350.0, ay - 30
    c.drawRect(skia.Rect.MakeLTRB(wx - 210, ay - 330, wx + 210, ay + 300), fill("#16171b"))
    for k in range(6):
        c.drawLine(wx - 210, ay - 300 + k * 110, wx + 210, ay - 300 + k * 110, stroke("#2a2c32", 6))
    case = rrect(wx - 330, wy - 320, wx + 330, wy + 320, 90)
    _shadow(c, case, 30, 20, 0.6)
    c.drawPath(case, _lin((wx, wy - 320), (wx, wy + 320), ["#3a3c42", "#121317"]))
    c.drawPath(rrect(wx - 290, wy - 280, wx + 290, wy + 280, 70), fill("#1d1f24"))
    for (bx, by) in ((wx - 345, wy - 170), (wx - 345, wy + 170), (wx + 345, wy - 170), (wx + 345, wy + 170)):
        c.drawPath(rrect(bx - 28, by - 44, bx + 28, by + 44, 14), fill("#5a5d66"))
    text(c, p.get("top_label", "LIGHT"), wx - 200, wy - 200, 34, "#9aa0aa", "bold")
    text(c, p.get("top_label_right", "MODE"), wx + 200, wy - 200, 34, "#9aa0aa", "bold", "right")
    ll, lt, lr, lb = wx - 240, wy - 140, wx + 240, wy + 200
    c.drawPath(rrect(ll, lt, lr, lb, 26), _lin((ll, lt), (lr, lb), ["#c7d1b8", "#a9b39a"]))
    ink, off = "#1c2218", "#b3bda4"
    text(c, p.get("ampm", "PM"), ll + 40, lt + 72, 56, ink, "extrabold")
    tm = str(p.get("time", "02:45"))
    dh = min(180.0, (lr - ll - 70) / max(1e-3, _seven_width(tm, 1.0)))
    _seven(c, tm, (ll + lr - _seven_width(tm, dh)) / 2, lt + 110 + (180 - dh) / 2, dh, ink, off=off)
    text(c, p.get("date", "SAT 14"), lr - 40, lt + 72, 44, ink, "bold", "right")
    c.drawPath(rrect(ll, lt, lr, lt + 40, 20), fill("#ffffff", 0.18))
    _vignette(c, 0.45)
    return s.makeImageSnapshot()


# =================================================================== so sánh / bảng ghim / tang vật
def _tag(c, cx, cy, w, h, ang, word, num, paper="#efe4c8", ink="#2a2420") -> tuple[float, float]:
    """Thẻ giá treo dây; trả về toạ độ giữa chữ (để nối đường đỏ)."""
    c.save()
    c.rotate(ang, cx, cy)
    l, t, r, b = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
    shape = poly([(l + w * 0.22, t), (r - w * 0.22, t), (r, t + w * 0.22), (r, b), (l, b), (l, t + w * 0.22)])
    c.drawPath(smooth([(cx, t + 70), (cx + 40, t - 300), (cx - 30, t - 700), (cx + 20, -400)], close=False),
               stroke("#d8d0bd", 8))
    _shadow(c, shape, 30, 20, 0.5)
    c.drawPath(shape, fill(paper))
    c.drawCircle(cx, t + 90, 48, fill("#b8a983"))
    c.drawCircle(cx, t + 90, 26, fill("#2a2420", 0.85))
    c.save()
    c.skew(-0.22, 0)
    c.translate(0.22 * (cy + 20), 0)
    text(c, word, cx, cy + 20, h * 0.13, ink, "extrabold", "center", max_w=w * 0.84)
    text(c, num, cx, cy + h * 0.33, h * 0.21, ink, "extrabold", "center", max_w=w * 0.84)
    c.restore()
    wave = skia.Path()
    wave.moveTo(l + w * 0.14, cy + 60)
    for k in range(6):
        wave.quadTo(l + w * (0.14 + (k + 0.5) * 0.12), cy + 60 + (18 if k % 2 else -18), l + w * (0.14 + (k + 1) * 0.12),
                    cy + 60)
    c.drawPath(wave, stroke(RED_INK, 10))
    c.restore()
    a = math.radians(ang)
    return cx - math.sin(a) * 0 + math.cos(a) * 0, cy - 40


def ins_price_tags_compare(p, size):
    """Màn chia đôi: 2 thẻ giá viết tay giống nhau, nối bằng đường đỏ đứt, nhãn giữa 'SAME HANDWRITING'."""
    s, c = _begin(size)
    c.drawRect(skia.Rect.MakeLTRB(0, 0, LW / 2, LH), _rad(LW * 0.25, LH * 0.5, LW * 0.45, ["#7a5638", "#3e2a1b"]))
    c.drawRect(skia.Rect.MakeLTRB(LW / 2, 0, LW, LH), _rad(LW * 0.75, LH * 0.5, LW * 0.45, ["#5d6976", "#2e353e"]))
    c.drawRect(skia.Rect.MakeLTRB(LW / 2 - 6, 0, LW / 2 + 6, LH), fill("#f2ead8"))
    left, right = p.get("left") or {}, p.get("right") or {}
    pa = _tag(c, 960, 1180, 900, 1100, -6, left.get("word", "SPECIAL"), left.get("number", "1990"))
    pb = _tag(c, 2880, 1180, 900, 1100, 5, right.get("word", "SPECIAL"), right.get("number", "10.-"))
    c.drawPath(poly([(pa[0] + 420, pa[1]), (LW / 2, pa[1] - 120), (pb[0] - 420, pb[1])], close=False),
               _dash(RED_INK, 12, 40, 24))
    for (x, y) in ((pa[0] + 420, pa[1]), (pb[0] - 420, pb[1])):
        c.drawCircle(x, y, 22, fill(RED_INK))
    text(c, left.get("caption", "basement wall"), 960, 2020, 58, "#f2ead8", "semibold", "center", a=0.9)
    text(c, right.get("caption", "shop sign"), 2880, 2020, 58, "#f2ead8", "semibold", "center", a=0.9)
    lab = p.get("label", "SAME HANDWRITING")
    f = font(84, "extrabold")
    tw = f.measureText(nfc(lab))
    _card(c, LW / 2 - tw / 2 - 90, 130, tw + 180, [(lab, 84, "#1f2430", "extrabold")], accent=RED_INK, bg="#fbf7ee")
    return s.makeImageSnapshot()


def _mini_missing_card(c, l, t, w, h, name, ang, seed) -> tuple[float, float]:
    c.save()
    c.rotate(ang, l + w / 2, t + h / 2)
    r = skia.Rect.MakeLTRB(l, t, l + w, t + h)
    _shadow(c, r, 14, 10, 0.4)
    c.drawRect(r, fill("#f7f4ec"))
    c.drawRect(skia.Rect.MakeLTRB(l, t, l + w, t + h * 0.19), fill("#c8352e"))
    text(c, "MISSING", l + w / 2, t + h * 0.165, h * 0.075, "#ffffff", "extrabold", "center", max_w=w * 0.85)
    pl, pt, pr, pb = l + w * 0.18, t + h * 0.23, l + w * 0.82, t + h * 0.63
    c.drawRect(skia.Rect.MakeLTRB(pl, pt, pr, pb), fill("#cfd5dc"))
    cx = (pl + pr) / 2
    c.drawPath(oval(cx, pt + (pb - pt) * 0.4, (pr - pl) * 0.2, (pb - pt) * 0.2), fill("#8f99a8"))
    c.drawPath(rrect(cx - (pr - pl) * 0.34, pt + (pb - pt) * 0.66, cx + (pr - pl) * 0.34, pb + 20, 40), fill("#8f99a8"))
    c.drawRect(skia.Rect.MakeLTRB(pl, pb, pr, pb + 2), fill("#8f99a8"))
    text(c, name, l + w / 2, t + h * 0.73, h * 0.065, "#1a1a1e", "extrabold", "center", max_w=w * 0.85)
    rng = random.Random(seed)
    for k in range(3):
        c.drawRect(skia.Rect.MakeLTRB(l + w * 0.14, t + h * (0.79 + k * 0.06), l + w * rng.uniform(0.6, 0.86),
                                      t + h * (0.81 + k * 0.06)), fill("#9a9ca3"))
    c.restore()
    return l + w / 2, t + 22


def _sticky(c, x, y, col, word, ang) -> tuple[float, float]:
    c.save()
    c.rotate(ang, x, y)
    r = skia.Rect.MakeLTRB(x - 170, y - 170, x + 170, y + 170)
    _shadow(c, r, 12, 10, 0.35)
    c.drawRect(r, fill(col))
    c.drawRect(skia.Rect.MakeLTRB(x - 170, y - 170, x + 170, y - 120), fill(shade(col, -0.08)))
    c.save()
    c.skew(-0.15, 0)
    c.translate(0.15 * y, 0)
    for i, ln in enumerate(word.split("\n")[:3]):
        text(c, ln, x, y + 10 + i * 70, 58, "#1f2a4a", "bold", "center", max_w=300)
    c.restore()
    c.restore()
    return x, y - 140


def ins_cork_board(p, size):
    """Bảng ghim điều tra: khung gỗ, nền bần, thẻ mất tích đầu đỏ, bản đồ khoanh đỏ, giấy nhớ, biên lai, dây đỏ nối ghim."""
    s, c = _begin(size)
    c.drawRect(skia.Rect.MakeWH(LW, LH), fill("#d6c8ac"))
    c.drawRect(skia.Rect.MakeLTRB(200, 100, 3640, 2060), fill("#6e4a2c"))
    c.drawRect(skia.Rect.MakeLTRB(200, 100, 3640, 2060), stroke("#4a3020", 10))
    il, it, ir, ib = 270.0, 170.0, 3570.0, 1990.0
    c.drawRect(skia.Rect.MakeLTRB(il, it, ir, ib), fill("#b98a55"))
    rng = random.Random(19)
    for _ in range(3800):
        c.drawCircle(rng.uniform(il, ir), rng.uniform(it, ib), rng.uniform(2, 6),
                     fill(rng.choice(["#9a6d3e", "#cf9f68", "#a87a48", "#7e5530"]), 0.7))
    c.drawRect(skia.Rect.MakeLTRB(il, it, ir, ib), _rad(LW / 2, LH / 2, LW * 0.6, [("#000000", 0.0), ("#000000", 0.25)],
                                                      [0.5, 1]))
    pins = []
    names = p.get("names") or ["ANNA K.", "DINA P.", "JADE C.", "ROSA Y."]
    spots = [(420, 300, -4), (980, 360, 3), (420, 1200, 2), (2880, 1180, -3)]
    for k, (nm, (x, y, a)) in enumerate(zip(names, spots)):
        pins.append(_mini_missing_card(c, x, y, 440, 600, nm, a, k))
    # bản đồ
    ml, mt, mr, mb = 1600.0, 300.0, 2600.0, 1060.0
    c.save()
    c.rotate(-2, (ml + mr) / 2, (mt + mb) / 2)
    _shadow(c, skia.Rect.MakeLTRB(ml, mt, mr, mb), 16, 10, 0.4)
    c.drawRect(skia.Rect.MakeLTRB(ml, mt, mr, mb), fill("#efe7d4"))
    for k in range(7):
        c.drawLine(ml + 40 + k * 150, mt, ml + 100 + k * 140, mb, stroke("#d8ccb0", 14))
    for k in range(5):
        c.drawLine(ml, mt + 60 + k * 160, mr, mt + 30 + k * 170, stroke("#d8ccb0", 14))
    c.drawPath(smooth([(ml, mt + 560), (ml + 400, mt + 480), (ml + 700, mt + 600), (mr, mt + 520)], close=False),
               stroke("#7fb0d8", 46))
    c.drawPath(smooth([(ml + 80, mb - 80), (ml + 360, mt + 300), (ml + 640, mt + 200), (mr - 60, mt + 80)], close=False),
               stroke("#9a958a", 26))
    for (dx, dy) in ((ml + 300, mt + 260), (ml + 720, mt + 380), (ml + 520, mt + 660)):
        c.drawCircle(dx, dy, 18, fill("#c8352e"))
    c.drawCircle(ml + 600, mt + 330, 170, _dash("#c8352e", 9, 26, 18))
    c.restore()
    pins.append((ml + 500, mt + 30))
    # ảnh polaroid mặt tiền cửa hàng
    c.save()
    c.rotate(5, 2050, 1500)
    _shadow(c, skia.Rect.MakeLTRB(1780, 1200, 2320, 1820), 14, 10, 0.4)
    c.drawRect(skia.Rect.MakeLTRB(1780, 1200, 2320, 1820), fill("#f7f6f1"))
    c.drawRect(skia.Rect.MakeLTRB(1820, 1240, 2280, 1660), fill("#5a6a7a"))
    c.drawRect(skia.Rect.MakeLTRB(1860, 1400, 2240, 1660), fill("#c8a46a"))
    for k in range(6):
        c.drawRect(skia.Rect.MakeLTRB(1860 + k * 63, 1360, 1860 + k * 63 + 32, 1420), fill("#c8352e"))
    c.drawRect(skia.Rect.MakeLTRB(1900, 1460, 2200, 1660), fill("#2a2f38"))
    text(c, p.get("photo_caption", "the shop?"), 2050, 1770, 50, "#1f2a4a", "bold", "center")
    c.restore()
    pins.append((2050, 1225))
    # biên lai
    for k, (x, y, a) in enumerate(((1360, 1150, -6), (2500, 1400, 7))):
        c.save()
        c.rotate(a, x, y)
        _shadow(c, skia.Rect.MakeLTRB(x - 110, y, x + 110, y + 420), 10, 8, 0.35)
        c.drawRect(skia.Rect.MakeLTRB(x - 110, y, x + 110, y + 420), fill("#fbfaf4"))
        for j in range(8):
            c.drawRect(skia.Rect.MakeLTRB(x - 80, y + 50 + j * 42, x + rng.uniform(0, 80), y + 62 + j * 42), fill("#a2a4aa"))
        c.restore()
        pins.append((x, y + 24))
    notes = p.get("notes") or ["4 AM?", "same\nshop", "who?"]
    for k, (x, y, col, a) in enumerate(((3000, 420, "#f6dd5a", 4), (3260, 820, "#f2a2b8", -5), (1300, 1760, "#9fd0f0", 3))):
        pins.append(_sticky(c, x, y, col, notes[k % len(notes)], a))
    order = p.get("string_order") or [0, 4, 1, 5, 2, 6, 3, 8, 7, 9]
    pts = [pins[i] for i in order if i < len(pins)]
    for a_, b_ in zip(pts, pts[1:]):
        sag = skia.Path()
        sag.moveTo(*a_)
        sag.quadTo((a_[0] + b_[0]) / 2, (a_[1] + b_[1]) / 2 + 60, *b_)
        c.drawPath(sag, stroke("#000000", 10, 0.25))
        c.drawPath(sag, stroke("#c8262a", 8))
    for k, (x, y) in enumerate(pins):
        _pushpin(c, x, y, ["#d0302a", "#2f6fd0", "#f3c94e", "#2fae5a"][k % 4])
    _vignette(c, 0.35)
    return s.makeImageSnapshot()


def _silver(x0, y0, x1, y1):
    return _lin((x0, y0), (x1, y1), ["#f4f7fa", "#a9b2bc", "#e3e8ee", "#8a939d"], [0, 0.4, 0.7, 1])


def _chain(c, pts, r=12, col="#c9d0d8") -> None:
    path = smooth(pts, close=False)
    meas = skia.PathMeasure(path, False)
    L = meas.getLength()
    d = 0.0
    k = 0
    while d < L:
        pos, tan = meas.getPosTan(d)
        c.save()
        c.translate(pos.x(), pos.y())
        c.rotate(math.degrees(math.atan2(tan.y(), tan.x())) + (90 if k % 2 else 0))
        c.drawPath(oval(0, 0, r * 1.2, r * 0.7), stroke(col, r * 0.45))
        c.restore()
        d += r * 1.6
        k += 1


def _evidence_marker(c, x, y, n) -> None:
    c.drawPath(oval(x + 30, y + 10, 120, 26), _blurred("#000000", 0.5, 14))
    c.drawPath(poly([(x - 90, y), (x - 50, y - 210), (x + 50, y - 210), (x + 90, y)]), fill("#f3c32e"))
    c.drawPath(poly([(x + 50, y - 210), (x + 90, y), (x + 130, y - 20), (x + 80, y - 215)]), fill("#c99a1a"))
    c.drawRect(skia.Rect.MakeLTRB(x - 72, y - 34, x + 72, y - 20), fill("#1a1a1e"))
    text(c, str(n), x, y - 62, 120, "#1a1a1e", "extrabold", "center")


def ins_evidence_markers(p, size):
    """Bàn tang vật nền đá xám: 7 món trang sức bạc + biển số vàng 1-7 + thẻ thông tin."""
    s, c = _begin(size)
    c.drawRect(skia.Rect.MakeWH(LW, LH), _rad(LW * 0.55, LH * 0.55, LW * 0.7, ["#3a414a", "#1c2026"]))
    rng = random.Random(23)
    for _ in range(1600):
        c.drawCircle(rng.uniform(0, LW), rng.uniform(0, LH), rng.uniform(2, 6), fill(rng.choice(["#4a525c", "#2a3038"]), 0.5))
    slots = [(1150, 700), (1900, 620), (2700, 700), (3400, 760), (1300, 1500), (2150, 1520), (3000, 1520)]
    items = p.get("items") or ["pendant", "hair_clip", "bangle", "ring", "watch", "beads", "necklace"]
    for k, kind in enumerate(items[:7]):
        x, y = slots[k]
        c.drawPath(oval(x + 30, y + 40, 260, 90), _blurred("#000000", 0.45, 30))
        if kind == "pendant":
            _chain(c, [(x - 220, y - 250), (x - 120, y - 60), (x, y - 120)], 11)
            c.drawCircle(x + 20, y + 30, 150, _silver(x - 150, y - 120, x + 150, y + 180))
            c.drawCircle(x + 20, y + 30, 112, stroke("#8a939d", 8))
            text(c, p.get("pendant_letter", "M"), x + 20, y + 80, 140, "#6a737d", "extrabold", "center")
        elif kind == "hair_clip":
            c.save()
            c.rotate(-18, x, y)
            c.drawPath(rrect(x - 260, y - 60, x + 260, y + 60, 60), _silver(x, y - 60, x, y + 60))
            c.drawPath(rrect(x - 200, y - 20, x + 200, y + 20, 20), fill("#7a838d"))
            for j in range(5):
                c.drawCircle(x - 160 + j * 80, y, 22, fill("#f2a2b8"))
            c.restore()
        elif kind == "bangle":
            c.drawPath(oval(x, y, 220, 170), stroke("#8a939d", 64))
            c.drawPath(oval(x, y, 220, 170), stroke("#e3e8ee", 44))
            arc = skia.Path()
            arc.addArc(skia.Rect.MakeLTRB(x - 220, y - 170, x + 220, y + 170), 200, 80)
            c.drawPath(arc, stroke("#ffffff", 14, 0.9))
        elif kind == "ring":
            c.drawPath(oval(x, y + 20, 120, 100), stroke("#8a939d", 40))
            c.drawPath(oval(x, y + 20, 120, 100), stroke("#e3e8ee", 26))
            c.drawPath(poly([(x - 50, y - 90), (x + 50, y - 90), (x + 70, y - 60), (x, y - 10), (x - 70, y - 60)]),
                       fill("#bfe6ff"))
            c.drawPath(poly([(x - 50, y - 90), (x + 50, y - 90), (x + 70, y - 60), (x - 70, y - 60)]), fill("#e8f6ff"))
        elif kind == "watch":
            c.drawPath(rrect(x - 80, y - 300, x + 80, y + 300, 40), fill("#7a838d"))
            for j in range(10):
                c.drawLine(x - 80, y - 280 + j * 60, x + 80, y - 280 + j * 60, stroke("#5a636d", 6))
            c.drawCircle(x, y, 150, _silver(x - 150, y - 150, x + 150, y + 150))
            c.drawCircle(x, y, 118, fill("#f4f2ec"))
            for j in range(12):
                a = j / 12 * math.tau
                c.drawLine(x + math.sin(a) * 96, y - math.cos(a) * 96, x + math.sin(a) * 110, y - math.cos(a) * 110,
                           stroke("#2a2c32", 6))
            c.drawLine(x, y, x + 50, y - 40, stroke("#2a2c32", 10))
            c.drawLine(x, y, x - 10, y - 90, stroke("#2a2c32", 7))
        elif kind == "beads":
            for j in range(16):
                a = j / 16 * math.tau
                bx, by = x + math.cos(a) * 190, y + math.sin(a) * 150
                c.drawCircle(bx, by, 36, _silver(bx - 36, by - 36, bx + 36, by + 36) if j % 4 else fill("#6aa0c8"))
        else:  # necklace
            _chain(c, [(x - 330, y - 260), (x - 250, y + 20), (x, y + 140), (x + 250, y + 20), (x + 330, y - 260)], 10)
            dx, dy = x, y + 200
            c.drawPath(poly([(dx, dy - 70), (dx + 60, dy), (dx, dy + 90), (dx - 60, dy)]), fill("#bfe6ff"))
            c.drawPath(poly([(dx, dy - 70), (dx + 60, dy), (dx, dy)]), fill("#ffffff", 0.8))
        _evidence_marker(c, x - 260 if k % 2 else x + 260, y + 300, k + 1)
    card = p.get("card") or {}
    pl, pt = 120.0, 120.0
    h = _card(c, pl, pt, 900, [(" ", 60, "#000000", "bold"),
                               (card.get("title", "UNDER 25"), 120, "#1f2430", "extrabold"),
                               (card.get("sub", "SILVER JEWELLERY"), 64, "#1f2430", "extrabold")], accent="#f3c32e")
    pill = card.get("pill", "VICTIMS")
    f = font(44, "bold")
    tw = f.measureText(nfc(pill))
    c.drawPath(rrect(pl + 62, pt + 44, pl + 62 + tw + 70, pt + 120, 38), fill("#1f2430"))
    text(c, pill, pl + 97, pt + 98, 44, "#ffffff", "bold")
    hl = c.saveLayer(None, None)
    del hl
    c.drawRect(skia.Rect.MakeLTRB(pl + 60, pt + h - 100, pl + 820, pt + h - 50), fill("#f3c32e", 0.55))
    c.restore()
    text(c, card.get("sub", "SILVER JEWELLERY"), pl + 62, pt + h - 56, 64, "#1f2430", "extrabold", max_w=760)
    _vignette(c, 0.45)
    return s.makeImageSnapshot()


def _cleaver(c, x, y, ang, s=1.0) -> None:
    """Dao phay chữ nhật: (x, y) = điểm nối cán-lưỡi; lưỡi hướng +x local."""
    c.save()
    c.translate(x, y)
    c.rotate(ang)
    c.drawPath(rrect(-560 * s, -60 * s, 20 * s, 60 * s, 40 * s), _lin((0, -60 * s), (0, 60 * s), ["#8a5a32", "#5a3820"]))
    for k in range(3):
        c.drawCircle((-460 + k * 170) * s, 0, 20 * s, fill("#d9dde2"))
    blade = poly([(0, -120 * s), (1050 * s, -150 * s), (1080 * s, 480 * s), (0, 440 * s)])
    _shadow(c, blade, 30 * s, 20 * s, 0.4)
    c.drawPath(blade, _lin((0, -150 * s), (0, 480 * s), ["#d4d9df", "#aeb6be", "#8e979f"]))
    c.drawPath(poly([(0, 380 * s), (1078 * s, 420 * s), (1080 * s, 480 * s), (0, 440 * s)]), fill("#eef2f6"))
    c.drawCircle(880 * s, -40 * s, 50 * s, fill("#1f3a2c"))
    c.drawPath(poly([(0, -120 * s), (1050 * s, -150 * s), (1080 * s, 480 * s), (0, 440 * s)]), stroke("#6a737b", 6 * s))
    c.drawLine(60 * s, -60 * s, 700 * s, -80 * s, stroke("#ffffff", 14 * s, 0.5))
    c.restore()


def ins_cleaver_honing(p, size):
    """Hai cẳng tay xăm dây leo mài dao phay vào thanh liếc thép, tia lửa ở điểm chạm (không máu)."""
    s, c = _begin(size)
    c.drawRect(skia.Rect.MakeWH(LW, LH), _rad(LW * 0.55, LH * 0.45, LW * 0.7, ["#2c4a38", "#0e1a14"]))
    skin = p.get("skin", "#c08a62")
    tat = p.get("tattoo_color", "#2f4a4a")
    # thanh liếc: từ tay phải dưới-phải lên trên-trái
    rx0, ry0, rx1, ry1 = 3150.0, 1720.0, 1450.0, 420.0
    c.drawPath(capsule(rx0, ry0, rx1, ry1, 70, 46), _lin((rx1, ry1), (rx0, ry0), ["#e3e8ee", "#8e979f"]))
    for k in range(1, 26):
        t = k / 26
        x, y = rx0 + (rx1 - rx0) * t, ry0 + (ry1 - ry0) * t
        c.drawLine(x - 24, y + 30, x + 24, y - 30, stroke("#6a737b", 4, 0.7))
    c.drawPath(capsule(rx0 + 30, ry0 + 30, rx0 + 300, ry0 + 230, 150, 150), fill("#1a1a1e"))
    c.drawPath(capsule(rx0 - 40, ry0 - 40, rx0 + 40, ry0 + 60, 260, 260), fill("#2a2c32"))
    _fist(c, rx0 + 150, ry0 + 140, -53, 1.15, skin)
    _tattoo(c, [(rx0 + 330, ry0 + 380), (rx0 + 520, ry0 + 540), (rx0 + 700, ry0 + 700), (rx0 + 880, ry0 + 860)], 1.0, tat)
    # dao phay: tay trái dưới-trái
    hx, hy = 1050.0, 1450.0
    _cleaver(c, hx, hy, -28, 1.25)
    _fist(c, hx - 330, hy + 180, 62, 1.15, skin)
    _tattoo(c, [(hx - 720, hy + 400), (hx - 900, hy + 520), (hx - 1080, hy + 640), (hx - 1260, hy + 760)], 1.0, tat)
    c.drawCircle(hx - 600, hy + 390, 36, stroke("#c8a24a", 14))       # vòng tay
    sx, sy = 2150.0, 960.0
    if p.get("sparks", True):
        _glow(c, sx, sy, 260, "#ffd27a", 0.8)
        rng = random.Random(3)
        for k in range(22):
            a = rng.uniform(0, math.tau)
            r0, r1 = rng.uniform(30, 80), rng.uniform(160, 380)
            c.drawLine(sx + math.cos(a) * r0, sy + math.sin(a) * r0, sx + math.cos(a) * r1, sy + math.sin(a) * r1,
                       stroke(rng.choice(["#fff4c2", "#ffc94e", "#ff9a3a"]), rng.uniform(5, 11)))
        c.drawCircle(sx, sy, 40, fill("#ffffff"))
    _vignette(c, 0.5)
    return s.makeImageSnapshot()


def _planks(c, base="#a7774a") -> None:
    rng = random.Random(21)
    x = 0.0
    while x < LW:
        w = rng.uniform(300, 420)
        col = shade(base, rng.uniform(-0.1, 0.08))
        c.drawRect(skia.Rect.MakeLTRB(x, 0, x + w, LH), fill(col))
        for _ in range(5):
            xx = x + rng.uniform(20, w - 20)
            pth = skia.Path()
            pth.moveTo(xx, 0)
            pth.cubicTo(xx + rng.uniform(-30, 30), LH * 0.3, xx + rng.uniform(-30, 30), LH * 0.7, xx, LH)
            c.drawPath(pth, stroke(shade(col, -0.2), rng.uniform(2, 5), 0.5))
        c.drawRect(skia.Rect.MakeLTRB(x + w - 8, 0, x + w, LH), fill(shade(base, -0.5)))
        y = rng.uniform(0, LH)
        c.drawRect(skia.Rect.MakeLTRB(x, y, x + w, y + 8), fill(shade(base, -0.45)))
        x += w


def ins_flashlight_mop(p, size):
    """Sàn ván nhìn từ trên: đèn pin đen chiếu sáng + tay cầm cán chổi lau gãy lởm chởm + thẻ 'ON HAND'."""
    s, c = _begin(size)
    _planks(c)
    c.drawRect(skia.Rect.MakeWH(LW, LH), _rad(LW * 0.35, LH * 0.5, LW * 0.6, [("#000000", 0.0), ("#000000", 0.55)], [0.3, 1]))
    # đèn pin
    fx, fy, fa = 700.0, 1350.0, -12.0
    c.save()
    c.translate(fx, fy)
    c.rotate(fa)
    beam = poly([(560, -110), (2300, -620), (2300, 620), (560, 110)])
    bp = _lin((560, 0), (2300, 0), [("#fff6c8", 0.6), ("#fff6c8", 0.0)])
    bp.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 30))
    c.drawPath(beam, bp)
    c.drawPath(oval(250, 60, 380, 80), _blurred("#000000", 0.5, 24))
    c.drawPath(rrect(0, -70, 400, 70, 40), _lin((0, -70), (0, 70), ["#3a3c42", "#101114"]))
    for k in range(6):
        c.drawLine(60 + k * 40, -66, 60 + k * 40, 66, stroke("#1a1b1f", 8))
    c.drawPath(poly([(400, -80), (520, -120), (560, -120), (560, 120), (520, 120), (400, 80)]), fill("#2a2c32"))
    c.drawPath(rrect(540, -110, 580, 110, 16), fill("#fff6c8"))
    _glow(c, 570, 0, 200, "#fff6c8", 0.7)
    c.drawPath(rrect(220, -86, 300, -66, 8), fill("#5a5d66"))
    c.restore()
    # cán chổi gãy
    sleeve, skin = p.get("sleeve_color", "#2b3550"), p.get("skin", "#c9926a")
    x0, y0, x1, y1 = 3200.0, 2300.0, 1800.0, 600.0
    _hand(c, 2680, 2250, -40, 1.5, sleeve, skin, "grip", "back")
    c.drawPath(capsule(x0, y0, x1, y1, 120, 110), _lin((x1 - 60, y1), (x1 + 60, y1 + 40), ["#d9b07a", "#a67a46"]))
    ang = math.atan2(y1 - y0, x1 - x0)
    nx, ny = -math.sin(ang), math.cos(ang)
    jag = [(x1 + nx * 58, y1 + ny * 58)]
    for k in range(7):
        t = (k + 1) / 8
        ex = 90 if k % 2 == 0 else -10
        jag.append((x1 + nx * (58 - 116 * t) + math.cos(ang) * ex, y1 + ny * (58 - 116 * t) + math.sin(ang) * ex))
    jag.append((x1 - nx * 58, y1 - ny * 58))
    jag.append((x1 - math.cos(ang) * 40 - nx * 58, y1 - math.sin(ang) * 40 - ny * 58))
    jag.append((x1 - math.cos(ang) * 40 + nx * 58, y1 - math.sin(ang) * 40 + ny * 58))
    c.drawPath(poly(jag), fill("#e8c89a"))
    for k in range(4):
        t = 0.2 + k * 0.15
        c.drawLine(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, x0 + (x1 - x0) * (t + 0.1), y0 + (y1 - y0) * (t + 0.1),
                   stroke("#8a5e32", 4, 0.6))
    _hand(c, 2680, 2250, -40, 1.5, sleeve, skin, "grip", "front")
    # thẻ checklist
    items = p.get("items") or [["ok", "FLASHLIGHT x1"], ["hl", "MOP HANDLE x1"], ["no", "PHONE · NO SIGNAL"]]
    l, t, w = 2520.0, 150.0, 1160.0
    h = 150 + len(items) * 130 + 150
    card = rrect(l, t, l + w, t + h, 30)
    _shadow(c, card, 30, 16, 0.55)
    c.drawPath(card, fill("#f6efe0"))
    c.save()
    c.clipPath(card, skia.ClipOp.kIntersect, True)
    c.drawRect(skia.Rect.MakeLTRB(l, t, l + 18, t + h), fill("#e8b93a"))
    c.restore()
    text(c, _spaced(p.get("title", "ON HAND")), l + 70, t + 100, 50, "#7a7466", "bold")
    y = t + 150
    for st, lab in items:
        if st == "hl":
            c.drawPath(rrect(l + 50, y + 10, l + w - 40, y + 120, 20), fill("#f3d64e", 0.6))
        ix, iy = l + 110, y + 66
        if st == "no":
            c.drawCircle(ix, iy, 36, fill("#c8352e"))
            c.drawLine(ix - 16, iy - 16, ix + 16, iy + 16, stroke("#ffffff", 9))
            c.drawLine(ix + 16, iy - 16, ix - 16, iy + 16, stroke("#ffffff", 9))
        else:
            c.drawCircle(ix, iy, 36, fill("#2fae5a"))
            c.drawPath(poly([(ix - 17, iy), (ix - 4, iy + 14), (ix + 18, iy - 14)], close=False), stroke("#ffffff", 9))
        text(c, lab, ix + 70, iy + 22, 62, "#1f2430", "extrabold", max_w=w - 230)
        y += 130
    text(c, p.get("footer", "NO BACKUP · A TORCH · A BROKEN MOP HANDLE"), l + 70, t + h - 55, 36, "#c8352e", "bold",
         max_w=w - 110)
    return s.makeImageSnapshot()


def _drum(c, x, b, w, h, col="#2a6fd0", drip=True) -> None:
    """Thùng phuy nhựa đứng: (x, b) = giữa đáy."""
    l, r, t = x - w / 2, x + w / 2, b - h
    c.drawPath(oval(x, b, w / 2, w * 0.12), fill(shade(col, -0.4)))
    c.drawRect(skia.Rect.MakeLTRB(l, t, r, b), _lin((l, 0), (r, 0), [shade(col, -0.25), shade(col, 0.2), col,
                                                                     shade(col, -0.35)], [0, 0.3, 0.6, 1]))
    c.drawPath(oval(x, b, w / 2, w * 0.12), _lin((l, 0), (r, 0), [shade(col, -0.25), shade(col, 0.2), shade(col, -0.35)]))
    for fr in (0.3, 0.68):
        y = t + h * fr
        c.drawPath(oval(x, y, w / 2 + 6, w * 0.1), stroke(shade(col, -0.35), 22))
        c.drawPath(oval(x, y - 8, w / 2, w * 0.1), stroke(shade(col, 0.25), 6, 0.6))
    c.drawPath(oval(x, t, w / 2, w * 0.12), fill(shade(col, 0.15)))
    c.drawPath(oval(x, t, w / 2 - 26, w * 0.12 - 10), fill(shade(col, -0.1)))
    c.drawPath(oval(x - w * 0.2, t, w * 0.09, w * 0.04), fill(shade(col, -0.45)))
    c.drawPath(oval(x + w * 0.2, t, w * 0.06, w * 0.03), fill(shade(col, -0.45)))
    if drip:
        p = skia.Path()
        p.moveTo(x - w * 0.18, t + w * 0.08)
        p.cubicTo(x - w * 0.2, t + h * 0.3, x - w * 0.12, t + h * 0.5, x - w * 0.16, t + h * 0.62)
        c.drawPath(p, stroke("#2a1a1e", 16, 0.55))
        c.drawCircle(x - w * 0.16, t + h * 0.63, 14, fill("#2a1a1e", 0.55))


def ins_blue_drums_cart(p, size):
    """Xe đẩy sàn phẳng chở thùng phuy nhựa xanh (sườn gân, nắp, vệt chảy tối), hẻm đêm, chip đếm."""
    s, c = _begin(size)
    c.drawRect(skia.Rect.MakeLTRB(0, 0, LW, 1300), _lin((0, 0), (0, 1300), ["#2a2228", "#3a2c30"]))
    rng = random.Random(4)
    for row in range(14):                                   # gạch tường
        y = row * 95
        off = 0 if row % 2 else 110
        for k in range(-1, 18):
            x = k * 220 + off
            c.drawRect(skia.Rect.MakeLTRB(x + 6, y + 6, x + 214, y + 89), fill(rng.choice(["#4a3434", "#423030", "#523a38"]), 0.8))
    c.drawRect(skia.Rect.MakeLTRB(0, 1300, LW, LH), _lin((0, 1300), (0, LH), ["#4a4a50", "#26262b"]))
    _glow(c, 3300, 300, 900, "#f0b860", 0.25)
    n = int(p.get("count", 3))
    dl, dr, dt = 760.0, 3080.0, 1560.0
    c.drawPath(oval((dl + dr) / 2, 1830, 1300, 60), _blurred("#000000", 0.55, 30))
    for wx in (980.0, 2860.0):                             # bánh sau
        c.drawCircle(wx + 60, 1740, 140, fill("#141418"))
    c.drawPath(capsule(dl - 120, 700, dl - 40, dt + 40, 46, 46), fill("#7a8088"))
    c.drawPath(capsule(dl - 260, 720, dl - 20, 700, 50, 50), fill("#1a1a1e"))
    c.drawRect(skia.Rect.MakeLTRB(dl, dt, dr, dt + 70), _lin((0, dt), (0, dt + 70), ["#a3a9b0", "#6a7078"]))
    c.drawRect(skia.Rect.MakeLTRB(dl, dt + 70, dr, dt + 120), fill("#4a4f56"))
    for k in range(n):
        x = dl + (dr - dl) * (k + 0.5) / n
        _drum(c, x, dt + 20, min(640, (dr - dl) / n * 0.86), 900, p.get("drum_color", "#2a6fd0"), drip=k != 1)
    for wx in (980.0, 2860.0):
        c.drawCircle(wx, 1720, 150, fill("#1a1a1e"))
        c.drawCircle(wx, 1720, 90, fill("#9aa0a8"))
        for k in range(6):
            a = k / 6 * math.tau
            c.drawLine(wx, 1720, wx + math.cos(a) * 85, 1720 + math.sin(a) * 85, stroke("#5a5f66", 10))
        c.drawCircle(wx, 1720, 24, fill("#3a3c42"))
    chip = p.get("chip")
    if chip:
        _card(c, 140, 140, 1100, [(_spaced(chip.get("label", "BLUE DRUMS")), 44, "#7a7466", "bold"),
                                  (chip.get("value", f"{n} drums"), 110, "#c8352e", "extrabold")], accent="#2a6fd0")
    _vignette(c, 0.45)
    return s.makeImageSnapshot()


# =================================================================== ảnh cũ / hiện trường / thức ăn
def _kid_photo(c, l, t, r, b) -> None:
    """Ảnh cũ: bé trai cười híp mắt, sứt răng cửa, tóc bát úp, áo trắng cổ đỏ, giơ tay vẫy."""
    w, h = r - l, b - t
    c.drawRect(skia.Rect.MakeLTRB(l, t, r, b), _lin((l, t), (l, b), ["#9ec0d8", "#d8e4d0", "#8aa06a"], [0, 0.6, 1]))
    c.drawPath(oval(l + w * 0.2, t + h * 0.62, w * 0.3, h * 0.12), fill("#6a8a4a"))
    c.drawPath(oval(l + w * 0.85, t + h * 0.6, w * 0.25, h * 0.1), fill("#6a8a4a"))
    cx = l + w * 0.5
    skin = "#e2a878"
    c.drawPath(rrect(cx - w * 0.3, t + h * 0.66, cx + w * 0.3, b + 40, w * 0.12), fill("#f6f4ee"))
    c.drawPath(poly([(cx - w * 0.12, t + h * 0.66), (cx, t + h * 0.76), (cx + w * 0.12, t + h * 0.66)]), fill("#c8352e"))
    # tay vẫy
    c.drawPath(capsule(cx + w * 0.26, t + h * 0.72, cx + w * 0.36, t + h * 0.42, w * 0.11, w * 0.09), fill("#f6f4ee"))
    c.drawPath(capsule(cx + w * 0.36, t + h * 0.44, cx + w * 0.38, t + h * 0.3, w * 0.07, w * 0.07), fill(skin))
    c.drawPath(oval(cx + w * 0.385, t + h * 0.27, w * 0.06, h * 0.055), fill(skin))
    for k in range(4):
        fx = cx + w * (0.345 + k * 0.027)
        c.drawPath(capsule(fx, t + h * 0.26, fx + (k - 1.5) * w * 0.006, t + h * 0.2, w * 0.022, w * 0.02), fill(skin))
    c.drawPath(oval(cx + w * 0.36, t + h * 0.4, w * 0.075, h * 0.018), stroke("#c8352e", w * 0.012))
    for k in range(2):
        arc = skia.Path()
        rr = w * (0.11 + k * 0.05)
        arc.addArc(skia.Rect.MakeLTRB(cx + w * 0.385 - rr, t + h * 0.25 - rr, cx + w * 0.385 + rr, t + h * 0.25 + rr), -60, 50)
        c.drawPath(arc, stroke("#ffffff", w * 0.01, 0.8))
    # đầu
    hy = t + h * 0.45
    hr = w * 0.2
    c.drawCircle(cx - hr * 0.98, hy + hr * 0.1, hr * 0.2, fill(skin))
    c.drawCircle(cx + hr * 0.98, hy + hr * 0.1, hr * 0.2, fill(skin))
    c.drawCircle(cx, hy, hr, fill(skin))
    hair = skia.Path()
    hair.moveTo(cx - hr * 1.04, hy + hr * 0.05)
    hair.arcTo(skia.Rect.MakeLTRB(cx - hr * 1.06, hy - hr * 1.08, cx + hr * 1.06, hy + hr * 0.9), 180, 180, False)
    hair.lineTo(cx + hr * 1.04, hy - hr * 0.15)
    hair.lineTo(cx - hr * 1.04, hy - hr * 0.15)
    hair.close()
    c.drawPath(hair, fill("#1c1a1e"))
    for k in range(7):
        x = cx - hr * 0.9 + k * hr * 0.3
        c.drawPath(poly([(x, hy - hr * 0.2), (x + hr * 0.3, hy - hr * 0.2), (x + hr * 0.15, hy - hr * 0.02)]), fill("#1c1a1e"))
    for sx in (-1, 1):
        arc = skia.Path()
        arc.addArc(skia.Rect.MakeLTRB(cx + sx * hr * 0.42 - hr * 0.18, hy + hr * 0.08, cx + sx * hr * 0.42 + hr * 0.18,
                                      hy + hr * 0.3), 200, 140)
        c.drawPath(arc, stroke("#1c1a1e", hr * 0.06))
        c.drawCircle(cx + sx * hr * 0.6, hy + hr * 0.45, hr * 0.14, fill("#f08a7a", 0.6))
    m = skia.Path()
    m.moveTo(cx - hr * 0.34, hy + hr * 0.42)
    m.quadTo(cx, hy + hr * 1.0, cx + hr * 0.34, hy + hr * 0.42)
    m.close()
    c.drawPath(m, fill("#7a2a28"))
    c.drawRect(skia.Rect.MakeLTRB(cx - hr * 0.3, hy + hr * 0.42, cx - hr * 0.05, hy + hr * 0.52), fill("#ffffff"))
    c.drawRect(skia.Rect.MakeLTRB(cx + hr * 0.07, hy + hr * 0.42, cx + hr * 0.3, hy + hr * 0.52), fill("#ffffff"))
    c.drawPath(oval(cx, hy + hr * 0.75, hr * 0.14, hr * 0.06), fill("#e86a6a"))


def ins_framed_old_photo(p, size):
    """Khung gỗ nâu viền vàng, nền giấy kem, ảnh cũ bạc màu (bé trai cười vẫy tay), dấu ngày cam ở góc."""
    s, c = _begin(size)
    draw_background(c, p.get("bg", "wall_grey"), int(LW), int(LH), p)
    l, t, r, b = 1160.0, 170.0, 2680.0, 1990.0
    fr = rrect(l, t, r, b, 14)
    _shadow(c, fr, 40, 30, 0.6)
    c.drawPath(fr, _lin((l, t), (r, b), ["#7a4a2a", "#4e2e1a", "#6a3e22"]))
    for k in range(8):
        y = t + 20 + k * 230
        c.drawLine(l + 10, y, r - 10, y + 30, stroke("#3e2414", 4, 0.3))
    c.drawRect(skia.Rect.MakeLTRB(l + 110, t + 110, r - 110, b - 110), fill("#c9a24a"))
    c.drawRect(skia.Rect.MakeLTRB(l + 126, t + 126, r - 126, b - 126), fill("#efe6d0"))
    pl, pt, pr, pb = l + 260, t + 260, r - 260, b - 300
    sepia = skia.ColorFilters.Matrix([0.393, 0.769, 0.189, 0, 0, 0.349, 0.686, 0.168, 0, 0, 0.272, 0.534, 0.131, 0, 0,
                                      0, 0, 0, 1, 0])
    amt = float(p.get("fade", 0.6))
    c.saveLayer(skia.Rect.MakeLTRB(pl, pt, pr, pb), skia.Paint(ColorFilter=sepia) if amt > 0.3 else None)
    _kid_photo(c, pl, pt, pr, pb)
    c.restore()
    c.drawRect(skia.Rect.MakeLTRB(pl, pt, pr, pb), fill("#fff6e0", 0.18))
    c.drawRect(skia.Rect.MakeLTRB(pl, pt, pr, pb), _rad((pl + pr) / 2, (pt + pb) / 2, (pr - pl) * 0.75,
                                                       [("#000000", 0.0), ("#3a2410", 0.45)], [0.5, 1]))
    rng = random.Random(8)
    for _ in range(12):
        x = rng.uniform(pl, pr)
        c.drawLine(x, rng.uniform(pt, pb), x + rng.uniform(-30, 30), rng.uniform(pt, pb), stroke("#ffffff", 3, 0.35))
    stamp = p.get("date_stamp", "'90 7 14")
    sw = text(c, stamp, pr - 50, pb - 50, 90, "#ff8a3a", "bold", "right", a=0.0)
    del sw
    c.save()
    c.drawString(nfc(stamp), pr - 50 - font(90, "bold").measureText(nfc(stamp)), pb - 50, font(90, "bold"),
                 _blurred("#ff7a2a", 0.7, 10))
    c.restore()
    text(c, stamp, pr - 50, pb - 50, 90, "#ffa24a", "bold", "right")
    c.drawRect(skia.Rect.MakeLTRB(pl, pt, pr, pb), stroke("#d8ccb0", 6))
    _vignette(c, 0.45)
    return s.makeImageSnapshot()


def _sneaker(c, x, y, ang, s=1.0) -> None:
    c.save()
    c.translate(x, y)
    c.rotate(ang)
    sole = smooth([(-360 * s, 0), (-300 * s, -130 * s), (60 * s, -150 * s), (330 * s, -110 * s), (380 * s, 0),
                   (330 * s, 110 * s), (60 * s, 140 * s), (-300 * s, 120 * s)])
    c.drawPath(sole, _blurred("#000000", 0.4, 20 * s))
    c.drawPath(sole, fill("#c9ccd0"))
    upper = smooth([(-320 * s, 0), (-270 * s, -105 * s), (60 * s, -120 * s), (300 * s, -85 * s), (340 * s, 0),
                    (300 * s, 85 * s), (60 * s, 115 * s), (-270 * s, 100 * s)])
    c.drawPath(upper, fill("#f6f6f4"))
    c.drawPath(oval(-180 * s, 0, 110 * s, 70 * s), fill("#3a3c42"))
    for k in range(5):
        xx = (-40 + k * 50) * s
        c.drawLine(xx, -60 * s, xx + 20 * s, 60 * s, stroke("#b9bec4", 10 * s))
    c.drawPath(upper, stroke("#b9bec4", 6 * s))
    c.restore()


def ins_dropped_phone_floor(p, size):
    """Tang vật trên vỉa hè nhìn từ trên: điện thoại ốp hồng nứt màn hình, hộp giấy mang về có dấu đỏ, giày, vũng nước."""
    s, c = _begin(size)
    if p.get("floor", "tiles") == "concrete":
        _concrete(c)
    else:
        _tiles(c, p.get("tile_color", "#b9b4a8"))
    gl, gt, gr, gb = 2980.0, 140.0, 3620.0, 760.0               # nắp cống
    c.drawRect(skia.Rect.MakeLTRB(gl, gt, gr, gb), fill("#2a2c30"))
    for k in range(9):
        c.drawRect(skia.Rect.MakeLTRB(gl + 40 + k * 64, gt + 40, gl + 70 + k * 64, gb - 40), fill("#0e0f12"))
    c.drawRect(skia.Rect.MakeLTRB(gl, gt, gr, gb), stroke("#5a5d64", 14))
    rng = random.Random(30)
    for _ in range(18):                                          # lá khô
        x, y = rng.uniform(0, LW), rng.uniform(0, LH)
        a = rng.uniform(0, 180)
        c.save()
        c.rotate(a, x, y)
        col = rng.choice(["#8a6a3a", "#6a7a3a", "#a07a42"])
        c.drawPath(oval(x, y, 70, 30), fill(col, 0.9))
        c.drawLine(x - 70, y, x + 70, y, stroke(shade(col, -0.3), 4))
        c.restore()
    for _ in range(6):                                           # đầu lọc thuốc
        x, y = rng.uniform(200, LW - 200), rng.uniform(200, LH - 200)
        a = math.radians(rng.uniform(0, 180))
        c.drawPath(capsule(x, y, x + math.cos(a) * 60, y + math.sin(a) * 60, 22, 22), fill("#efe8d8"))
        c.drawPath(capsule(x, y, x + math.cos(a) * 22, y + math.sin(a) * 22, 23, 23), fill("#d8904a"))
    pud = smooth([(1700 + math.cos(a) * 520 * rng.uniform(0.8, 1.1), 1500 + math.sin(a) * 260 * rng.uniform(0.8, 1.1))
                  for a in [k / 12 * math.tau for k in range(12)]])
    c.drawPath(pud, fill("#5f7488", 0.55))
    c.drawPath(oval(1560, 1420, 220, 40), fill("#ffffff", 0.25))
    # hộp giấy
    bx, by = 900.0, 640.0
    c.save()
    c.rotate(-14, bx, by)
    box = skia.Rect.MakeLTRB(bx - 380, by - 300, bx + 380, by + 300)
    _shadow(c, box, 24, 16, 0.5)
    c.drawRect(box, fill("#f1ebdd"))
    c.drawRect(skia.Rect.MakeLTRB(bx - 380, by - 300, bx + 380, by - 200), fill("#e2d9c4"))
    c.drawLine(bx - 380, by - 200, bx + 380, by - 200, stroke("#c9bea6", 6))
    c.drawPath(poly([(bx + 200, by + 300), (bx + 380, by + 120), (bx + 380, by + 300)]), fill("#d8ceb8"))
    c.drawCircle(bx - 20, by + 50, 170, stroke(RED_INK, 14, 0.85))
    c.drawCircle(bx - 20, by + 50, 135, stroke(RED_INK, 5, 0.85))
    st = p.get("stamp") or ["STEAM", "HOUSE"]
    text(c, st[0], bx - 20, by + 40, 64, RED_INK, "extrabold", "center", a=0.85, max_w=230)
    if len(st) > 1:
        text(c, st[1], bx - 20, by + 110, 50, RED_INK, "bold", "center", a=0.85, max_w=230)
    c.restore()
    _sneaker(c, 2900, 1650, -28, 1.3)
    # điện thoại
    px, py = 1850.0, 1000.0
    c.save()
    c.rotate(24, px, py)
    case = rrect(px - 290, py - 560, px + 290, py + 560, 90)
    _shadow(c, case, 30, 20, 0.6)
    c.drawPath(case, fill(p.get("case_color", "#f2a2b8")))
    c.drawPath(rrect(px - 255, py - 525, px + 255, py + 525, 70), fill("#0c0d10"))
    c.save()
    c.clipPath(rrect(px - 240, py - 510, px + 240, py + 510, 60), skia.ClipOp.kIntersect, True)
    c.drawRect(skia.Rect.MakeLTRB(px - 240, py - 510, px + 240, py + 510), _lin((px, py - 510), (px, py + 510),
                                                                             ["#1a2238", "#0c0f18"]))
    _crack(c, px + 60, py - 150, 900, seed=7, w=6)
    c.restore()
    c.restore()
    _vignette(c, 0.45)
    return s.makeImageSnapshot()


def _bun_half(c, cx, cy, r, face_right: bool) -> None:
    sgn = 1 if face_right else -1
    c.drawPath(oval(cx, cy, r, r * 0.88), _rad(cx - sgn * r * 0.3, cy - r * 0.4, r * 1.4, ["#fffdf8", "#eee4d0"]))
    for k in range(3):
        arc = skia.Path()
        arc.addArc(skia.Rect.MakeLTRB(cx - r * 0.7, cy - r * (0.85 - k * 0.1), cx + r * 0.7, cy + r * 0.3), 210, 120)
        c.drawPath(arc, stroke("#e2d6bc", 6, 0.6))
    fx = cx + sgn * r * 0.55
    face = oval(fx, cy + r * 0.05, r * 0.42, r * 0.76)
    c.drawPath(face, fill("#f3ead8"))
    rng = random.Random(int(cx))
    edge = [(fx + sgn * r * 0.42 * math.cos(a) * rng.uniform(0.92, 1.05), cy + r * 0.05 + r * 0.76 * math.sin(a))
            for a in [k / 18 * math.tau for k in range(18)]]
    c.drawPath(smooth(edge), stroke("#fbf6ea", 16))
    fill_path = oval(fx + sgn * r * 0.05, cy + r * 0.08, r * 0.3, r * 0.52)
    c.drawPath(fill_path, _rad(fx, cy, r * 0.5, ["#e8a090", "#c06a5a"]))
    for _ in range(16):
        a = rng.uniform(0, math.tau)
        rr = rng.uniform(0, 0.85)
        c.drawCircle(fx + sgn * r * 0.05 + math.cos(a) * r * 0.27 * rr, cy + r * 0.08 + math.sin(a) * r * 0.47 * rr,
                     rng.uniform(5, 10), fill(rng.choice(["#3a2a24", "#5a8a3a", "#a04a3a"])))


def ins_bun_broken_hands(p, size):
    """Hai bàn tay bẻ đôi chiếc bánh bao trắng, lộ nhân thịt hồng có tiêu, hơi nóng bốc lên, nền tối ấm nhoè."""
    s, c = _begin(size)
    _bokeh(c, "#4a3424", "#140d08", ["#f0a25a", "#ffd27a", "#c8504a"], n=20, seed=9)
    sleeve, skin = p.get("sleeve_color", "#2b3550"), p.get("skin", "#c9926a")
    gap = float(p.get("gap", 170))
    L = (1920 - gap / 2 - 330, 1080)
    R = (1920 + gap / 2 + 330, 1080)
    _hand(c, L[0] - 120, 2150, 22, 1.55, sleeve, skin, "grip", "back")
    _hand(c, R[0] + 120, 2150, -22, 1.55, sleeve, skin, "grip", "back", mirror=True)
    _bun_half(c, *L, 430, True)
    _bun_half(c, *R, 430, False)
    if p.get("steam", True):
        for k in range(4):
            x = 1920 + (k - 1.5) * 90
            sm = skia.Path()
            sm.moveTo(x, 900)
            y = 900.0
            for j in range(5):
                sm.quadTo(x + (50 if (j + k) % 2 else -50), y - 70, x + 8, y - 140)
                y -= 140
                x += 8
            c.drawPath(sm, stroke("#ffffff", 18, 0.25))
    _hand(c, L[0] - 120, 2150, 22, 1.55, sleeve, skin, "grip", "front")
    _hand(c, R[0] + 120, 2150, -22, 1.55, sleeve, skin, "grip", "front", mirror=True)
    _vignette(c, 0.5)
    return s.makeImageSnapshot()


def ins_rule_note_torn(p, size):
    """Hai tay (tay áo xanh navy) xé đôi tờ giấy vở ghi luật; mép xé răng cưa, băng keo đỏ ở đỉnh."""
    s, c = _begin(size)
    draw_background(c, p.get("bg", "dark_vignette"), int(LW), int(LH), p)
    pw, ph = 1500.0, 1820.0
    rect = skia.Rect.MakeLTRB(LW / 2 - pw / 2, 150, LW / 2 + pw / 2, 150 + ph)
    rng = random.Random(12)
    tear = [(LW / 2 + rng.uniform(-50, 50), y) for y in range(80, 2100, 70)]
    left = poly([(0, 0)] + [(LW / 2, 0)] + tear + [(LW / 2, LH), (0, LH)])
    right = poly([(LW / 2, 0), (LW, 0), (LW, LH), (LW / 2, LH)] + tear[::-1])
    sleeve, skin = p.get("sleeve_color", "#1f2a4a"), p.get("skin", "#c9926a")
    gap = float(p.get("gap", 70))
    tilt = float(p.get("tilt", 5))
    for side, clip, sgn in (("L", left, -1), ("R", right, 1)):
        c.save()
        c.translate(sgn * gap, 0)
        c.rotate(sgn * tilt, LW / 2, 150 + ph)
        hx = rect.left() + 230 if side == "L" else rect.right() - 230
        _hand(c, hx, rect.bottom() + 260, sgn * 10, 1.4, sleeve, skin, "grip", "back", mirror=side == "R")
        c.save()
        c.clipPath(clip, skia.ClipOp.kIntersect, True)
        rules = p.get("rules")
        if rules is None:
            rules = ["DON'T EAT THE SPECIAL FILLING!"]
        draw_paper_notebook(c, rect, p.get("title", "RULE #1"), rules, note=p.get("note", "at Uncle's shop"),
                            red_index=p.get("red_rule_index", 0),
                            rotation=0.0, tape=False, params={"ink": p.get("ink", INK)})
        c.restore()
        c.drawPath(poly(tear, close=False), stroke("#fbf6ea", 16))
        c.drawPath(poly(tear, close=False), stroke("#d8cfbc", 4))
        _tape(c, LW / 2 + sgn * 160, rect.top() + 10, 260, 80, sgn * 14, "#d8423a", 0.9)
        _hand(c, hx, rect.bottom() + 260, sgn * 10, 1.4, sleeve, skin, "grip", "front", mirror=side == "R")
        c.restore()
    _vignette(c, 0.35)
    return s.makeImageSnapshot()


# =================================================================== thẻ ngành trên bàn / bát canh
def _felt(c, base="#2f6a4a") -> None:
    """Mặt bàn nỉ xanh có viền gỗ ở mép trên khung."""
    c.drawRect(skia.Rect.MakeWH(LW, LH), _rad(LW * 0.5, LH * 0.6, LW * 0.7, [shade(base, 0.08), shade(base, -0.3)]))
    rng = random.Random(27)
    for _ in range(2600):
        c.drawCircle(rng.uniform(0, LW), rng.uniform(0, LH), rng.uniform(1.5, 4),
                     fill(rng.choice([shade(base, 0.15), shade(base, -0.15)]), 0.35))
    c.drawRect(skia.Rect.MakeLTRB(0, 0, LW, 170), _lin((0, 0), (0, 170), ["#7a4a2a", "#4e2e1a"]))
    c.drawRect(skia.Rect.MakeLTRB(0, 160, LW, 184), fill("#2a180c"))


def _badge(c, cx, cy, r) -> None:
    """Huy hiệu lục giác vàng chung chung (ngôi sao + vòng chữ trống), không quốc huy."""
    pts = [(cx + math.cos(math.radians(60 * k - 90)) * r, cy + math.sin(math.radians(60 * k - 90)) * r) for k in range(6)]
    hexp = poly(pts)
    _shadow(c, hexp, 20, 12, 0.5)
    c.drawPath(hexp, _lin((cx - r, cy - r), (cx + r, cy + r), ["#f6d77a", "#c99a2e", "#f0c85a", "#9a7020"],
                         [0, 0.45, 0.7, 1]))
    inner = [(cx + (x - cx) * 0.8, cy + (y - cy) * 0.8) for x, y in pts]
    c.drawPath(poly(inner), stroke("#8a6418", r * 0.04))
    c.drawCircle(cx, cy, r * 0.5, fill("#e8bf50"))
    c.drawCircle(cx, cy, r * 0.5, stroke("#8a6418", r * 0.03))
    c.drawPath(_star(cx, cy, r * 0.36), fill("#9a7020"))
    c.drawPath(_star(cx - r * 0.02, cy - r * 0.02, r * 0.3), fill("#f6d77a"))


def ins_id_wallet_desk(p, size):
    """Ví thẻ ngành da nâu mở (huy hiệu vàng + thẻ 'ID CARD') bị tay áo kaki đẩy qua bàn nỉ; giấy đánh máy + chùm chìa khoá."""
    s, c = _begin(size)
    _felt(c, p.get("felt", "#2f6a4a"))
    # giấy đánh máy
    c.save()
    c.rotate(-8, 760, 1100)
    sheet = skia.Rect.MakeLTRB(200, 420, 1300, 1900)
    _shadow(c, sheet, 24, 14, 0.45)
    c.drawRect(sheet, fill("#f3f1ea"))
    text(c, p.get("sheet_title", "CASE REPORT"), 280, 560, 64, "#2a2a30", "extrabold")
    rng = random.Random(5)
    for k in range(16):
        y = 660 + k * 70
        c.drawRect(skia.Rect.MakeLTRB(280, y, 280 + rng.uniform(560, 920), y + 18), fill("#8a8c93", 0.8))
    c.restore()
    # chùm chìa khoá
    kx, ky = 3330.0, 560.0
    c.drawCircle(kx, ky, 90, stroke("#b9bec4", 16))
    for k, (ang, col) in enumerate(((20, "#c9a24a"), (70, "#b9bec4"), (115, "#9aa0a8"))):
        a = math.radians(ang)
        x0, y0 = kx + math.cos(a) * 90, ky + math.sin(a) * 90
        x1, y1 = x0 + math.cos(a) * 330, y0 + math.sin(a) * 330
        c.drawPath(capsule(x0, y0, x1, y1, 40, 30), fill(col))
        c.drawCircle(x0 + math.cos(a) * 40, y0 + math.sin(a) * 40, 70, fill(col))
        c.drawCircle(x0 + math.cos(a) * 40, y0 + math.sin(a) * 40, 22, fill(shade(p.get("felt", "#2f6a4a"), -0.2)))
        for j in range(3):
            t = 0.55 + j * 0.14
            c.drawRect(skia.Rect.MakeXYWH(x0 + (x1 - x0) * t - 12, y0 + (y1 - y0) * t - 12, 24, 40), fill(col))
    # ví
    cx, cy = 2050.0, 1060.0
    c.save()
    c.rotate(float(p.get("rotation", -6)), cx, cy)
    wl, wt, wr, wb = cx - 900, cy - 560, cx + 900, cy + 560
    body = rrect(wl, wt, wr, wb, 60)
    _shadow(c, body, 40, 26, 0.6)
    c.drawPath(body, _lin((wl, wt), (wr, wb), ["#7a4a2a", "#5a3420", "#6e4226"]))
    c.drawPath(rrect(wl + 26, wt + 26, wr - 26, wb - 26, 44), _dash("#d8b88a", 6, 22, 14, 0.8))
    c.drawRect(skia.Rect.MakeLTRB(cx - 14, wt + 10, cx + 14, wb - 10), fill("#3e2414", 0.8))
    _badge(c, cx - 450, cy, 330)
    # thẻ ID
    il, it, ir, ib = cx + 90, cy - 420, wr - 90, cy + 420
    card = rrect(il, it, ir, ib, 30)
    _shadow(c, card, 12, 6, 0.4)
    c.drawPath(card, fill("#f4f5f7"))
    c.save()
    c.clipPath(card, skia.ClipOp.kIntersect, True)
    c.drawRect(skia.Rect.MakeLTRB(il, it, ir, it + 170), _lin((il, it), (ir, it), ["#1e4fa0", "#2f74c8"]))
    for k in range(5):
        c.drawLine(il, ib - 60 - k * 18, ir, ib - 160 - k * 18, stroke("#2f74c8", 6, 0.12))
    c.restore()
    text(c, p.get("card_title", "ID CARD"), (il + ir) / 2, it + 115, 84, "#ffffff", "extrabold", "center", max_w=ir - il - 80)
    phl, pht = il + 50, it + 220
    phw, phh = 270.0, 340.0
    img = _portrait(p.get("photo"), int(phw), int(phh))
    if img is not None:
        c.drawRect(skia.Rect.MakeLTRB(phl, pht, phl + phw, pht + phh), fill("#e6eaef"))
        c.drawImageRect(img, skia.Rect.MakeLTRB(phl, pht, phl + phw, pht + phh), SAMPLING)
    else:
        c.drawRect(skia.Rect.MakeLTRB(phl, pht, phl + phw, pht + phh), _lin((0, pht), (0, pht + phh), ["#dfe4ea", "#c2cad4"]))
        c.drawPath(oval(phl + phw / 2, pht + phh * 0.38, phw * 0.22, phh * 0.17), fill("#8f99a8"))
        c.drawPath(rrect(phl + phw * 0.14, pht + phh * 0.62, phl + phw * 0.86, pht + phh + 30, 60), fill("#8f99a8"))
    c.drawRect(skia.Rect.MakeLTRB(phl, pht, phl + phw, pht + phh), stroke("#9aa0aa", 4))
    tx = phl + phw + 40
    rows = p.get("rows") or [["NAME", "K. MORAN"], ["RANK", "DETECTIVE"], ["UNIT", "INVESTIGATIONS"], ["NO.", "0417"]]
    for k, (lab, val) in enumerate(rows[:4]):
        y = pht + 40 + k * 86
        text(c, lab, tx, y, 30, "#7a808a", "bold")
        text(c, val, tx, y + 44, 44, "#1a1c22", "extrabold", max_w=ir - tx - 40)
    c.drawPath(smooth([(il + 60, ib - 70), (il + 120, ib - 120), (il + 170, ib - 60), (il + 240, ib - 130),
                       (il + 320, ib - 75)], close=False), stroke("#1a2a55", 6))
    c.restore()
    # tay đẩy (tay áo kaki) từ đáy phải
    sleeve, skin = p.get("sleeve_color", "#a08a5a"), p.get("skin", "#b9825a")
    _hand(c, 2700, 2420, -22, 1.6, sleeve, skin, "open", "all")
    if p.get("motion_lines", False):
        for k in range(4):
            y = 700 + k * 180
            c.drawLine(3140 + k * 20, y + 40, 3420 + k * 20, y + 140, stroke("#ffffff", 12, 0.35))
    _vignette(c, 0.4)
    return s.makeImageSnapshot()


def _glass_top(c, x, y, r) -> None:
    c.drawCircle(x + 20, y + 26, r, _blurred("#000000", 0.35, 20))
    c.drawCircle(x, y, r, fill("#dfeef6", 0.55))
    c.drawCircle(x, y, r, stroke("#ffffff", 10, 0.8))
    c.drawCircle(x, y, r * 0.8, fill("#b9d8ea", 0.45))
    arc = skia.Path()
    arc.addArc(skia.Rect.MakeLTRB(x - r * 0.7, y - r * 0.7, x + r * 0.7, y + r * 0.7), 200, 70)
    c.drawPath(arc, stroke("#ffffff", 14, 0.85))


def ins_soup_bowl_spoon(p, size):
    """Nhìn từ trên: bát canh trong có thịt viên + hành ngò, tay áo xanh cầm thìa từ góc trên-phải, ly nước, đĩa ớt nhỏ."""
    s, c = _begin(size)
    _wood_top(c, p.get("table", "#c4956a"))
    _vignette(c, 0.35)
    bx, by, br = 1760.0, 1180.0, 760.0
    c.drawCircle(bx + 30, by + 46, br, _blurred("#000000", 0.45, 40))
    c.drawCircle(bx, by, br, _rad(bx - 200, by - 200, br * 1.3, ["#ffffff", "#e6e8ea"]))
    c.drawCircle(bx, by, br * 0.93, stroke(p.get("rim_color", "#3a78c2"), 14, 0.8))
    c.drawCircle(bx, by, br * 0.8, _rad(bx - 120, by - 120, br * 0.9, ["#f3dfa8", "#d9b56a"]))
    c.drawCircle(bx, by, br * 0.8, stroke("#c49a4a", 8, 0.5))
    rng = random.Random(31)
    for _ in range(26):                                     # váng mỡ
        a, rr = rng.uniform(0, math.tau), rng.uniform(0, br * 0.7)
        c.drawCircle(bx + math.cos(a) * rr, by + math.sin(a) * rr, rng.uniform(10, 26), stroke("#fff3c8", 4, 0.7))
    balls = [(-260, -180), (60, -300), (300, -40), (-120, 180), (180, 300), (-360, 120)]
    for k, (dx, dy) in enumerate(balls[:int(p.get("meatballs", 6))]):
        x, y, r = bx + dx, by + dy, rng.uniform(95, 120)
        c.drawCircle(x + 10, y + 14, r, fill("#7a5a32", 0.4))
        c.drawCircle(x, y, r, _rad(x - r * 0.3, y - r * 0.3, r * 1.3, ["#b07a4a", "#7a4a2a"]))
        for _ in range(6):
            c.drawCircle(x + rng.uniform(-r, r) * 0.6, y + rng.uniform(-r, r) * 0.6, rng.uniform(5, 10), fill("#5a3420", 0.6))
        c.drawPath(oval(x - r * 0.35, y - r * 0.4, r * 0.3, r * 0.16), fill("#ffffff", 0.35))
    for _ in range(40):                                     # hành, ngò
        a, rr = rng.uniform(0, math.tau), rng.uniform(0, br * 0.72)
        x, y = bx + math.cos(a) * rr, by + math.sin(a) * rr
        if rng.random() < 0.5:
            c.drawCircle(x, y, rng.uniform(12, 20), stroke("#5aa040", 7))
        else:
            c.save()
            c.rotate(rng.uniform(0, 180), x, y)
            c.drawPath(oval(x, y, rng.uniform(16, 28), rng.uniform(8, 13)), fill("#3f8a36"))
            c.restore()
    # thìa + tay
    sleeve, skin = p.get("sleeve_color", BRAND_GREEN), p.get("skin", "#c9926a")
    hx, hy, ha, hs = 3560.0, -40.0, -138.0, 1.5
    tx, ty = _hand_tip(hx, hy, ha, hs)
    sx, sy = bx + 170, by + 60                              # lòng thìa trong bát
    ang = math.atan2(ty - sy, tx - sx)
    ex, ey = tx + math.cos(ang) * 260, ty + math.sin(ang) * 260
    c.drawPath(capsule(sx + 20, sy + 30, ex + 20, ey + 30, 50, 34), _blurred("#000000", 0.3, 16))
    c.drawPath(capsule(sx, sy, ex, ey, 46, 30), _silver(sx, sy - 40, sx, sy + 40))
    c.save()
    c.translate(sx, sy)
    c.rotate(math.degrees(ang))
    c.drawPath(oval(-40, 0, 220, 150), _silver(-260, -150, 180, 150))
    c.drawPath(oval(-50, 0, 180, 118), fill("#e8c27a", 0.85))
    c.drawCircle(-60, 10, 70, _rad(-80, -10, 90, ["#b07a4a", "#7a4a2a"]))
    c.drawPath(oval(-120, -50, 50, 16), fill("#ffffff", 0.5))
    c.restore()
    _hand(c, hx, hy, ha, hs, sleeve, skin, "pinch", "all")
    # ly nước + đĩa ớt
    _glass_top(c, 3180, 1500, 300)
    dx, dy = 560.0, 420.0
    c.drawCircle(dx + 14, dy + 20, 190, _blurred("#000000", 0.35, 20))
    c.drawCircle(dx, dy, 190, fill("#f6f6f2"))
    c.drawCircle(dx, dy, 120, fill("#e9e6dc"))
    c.drawCircle(dx, dy, 95, fill("#c8352e", 0.85))
    for _ in range(14):
        a, rr = rng.uniform(0, math.tau), rng.uniform(0, 80)
        c.drawCircle(dx + math.cos(a) * rr, dy + math.sin(a) * rr, rng.uniform(6, 12), fill("#f2d36a"))
    if p.get("steam", True):
        for k in range(3):
            x = bx - 200 + k * 200
            sm = skia.Path()
            sm.moveTo(x, by - 300)
            y = by - 300
            for j in range(4):
                sm.quadTo(x + (60 if (j + k) % 2 else -60), y - 90, x, y - 180)
                y -= 180
            c.drawPath(sm, stroke("#ffffff", 22, 0.18))
    return s.makeImageSnapshot()


def _hand_tip(x, y, angle, scale):
    from .insertgen import hand_tip
    return hand_tip(x, y, angle, scale, "pinch")


# =================================================================== đăng ký
INSERTS = {
    "phone_sms_hand": ins_phone_sms_hand,
    "phone_call_screen": ins_phone_call_screen,
    "phone_gps_map": ins_phone_gps_map,
    "phone_draft_cracked": ins_phone_draft_cracked,
    "receipt_thermal": ins_receipt_thermal,
    "blueprint_plan": ins_blueprint_plan,
    "depth_diagram": ins_depth_diagram,
    "notebook_list_hand": ins_notebook_list_hand,
    "missing_poster_numbered": ins_missing_poster_numbered,
    "cold_room_alarm": ins_cold_room_alarm,
    "wristwatch_digital": ins_wristwatch_digital,
    "price_tags_compare": ins_price_tags_compare,
    "cork_board": ins_cork_board,
    "evidence_markers": ins_evidence_markers,
    "cleaver_honing": ins_cleaver_honing,
    "flashlight_mop": ins_flashlight_mop,
    "blue_drums_cart": ins_blue_drums_cart,
    "framed_old_photo": ins_framed_old_photo,
    "dropped_phone_floor": ins_dropped_phone_floor,
    "bun_broken_hands": ins_bun_broken_hands,
    "rule_note_torn": ins_rule_note_torn,
    "id_wallet_desk": ins_id_wallet_desk,
    "soup_bowl_spoon": ins_soup_bowl_spoon,
}

# metadata tìm kiếm (song ngữ) — KHÔNG vẽ vào ảnh
TAGS = {
    "phone_sms_hand": ["điện thoại", "tin nhắn", "sms", "cầm tay", "phone", "sms", "text message", "dark mode"],
    "phone_call_screen": ["điện thoại", "cuộc gọi", "gọi điện", "phone", "call", "calling"],
    "phone_gps_map": ["điện thoại", "định vị", "bản đồ", "gps", "tracker", "location"],
    "phone_draft_cracked": ["điện thoại", "tin nháp", "chưa gửi", "màn hình vỡ", "draft", "unsent", "cracked screen"],
    "receipt_thermal": ["hoá đơn", "biên lai", "mua hàng", "receipt", "bill", "stats"],
    "blueprint_plan": ["bản vẽ", "thiết kế", "tầng hầm", "nhà phố", "blueprint", "floor plan", "basement"],
    "depth_diagram": ["sơ đồ", "mặt cắt", "độ sâu", "tầng hầm", "diagram", "cross section", "depth", "underground"],
    "notebook_list_hand": ["sổ tay", "danh sách", "mất tích", "ngón tay chỉ", "notebook", "list", "missing", "pointing"],
    "missing_poster_numbered": ["tìm người", "mất tích", "tờ rơi", "đánh số", "missing", "poster", "numbered"],
    "cold_room_alarm": ["kho lạnh", "nhiệt độ", "báo động", "cold room", "freezer", "temperature", "alarm"],
    "wristwatch_digital": ["đồng hồ đeo tay", "điện tử", "giờ", "băng gạc", "wristwatch", "digital watch", "time"],
    "price_tags_compare": ["thẻ giá", "chữ viết tay", "so sánh", "price tag", "handwriting", "compare"],
    "cork_board": ["bảng ghim", "điều tra", "dây đỏ", "cork board", "investigation", "red string"],
    "evidence_markers": ["tang vật", "trang sức", "bạc", "biển số", "evidence", "jewellery", "markers"],
    "cleaver_honing": ["dao phay", "mài dao", "đồ tể", "hình xăm", "cleaver", "honing steel", "butcher"],
    "flashlight_mop": ["đèn pin", "cán chổi", "vũ khí tạm", "flashlight", "torch", "mop handle"],
    "blue_drums_cart": ["thùng phuy", "xe đẩy", "thùng xanh", "blue drum", "barrel", "cart"],
    "framed_old_photo": ["ảnh cũ", "khung ảnh", "kỷ niệm", "trẻ con", "old photo", "framed photo", "memory"],
    "dropped_phone_floor": ["điện thoại rơi", "vỡ màn hình", "vỉa hè", "hiện trường", "dropped phone", "evidence"],
    "bun_broken_hands": ["bánh bao", "bẻ đôi", "nhân thịt", "steamed bun", "filling", "food"],
    "rule_note_torn": ["xé giấy", "nội quy", "luật", "torn note", "rule", "ripped paper"],
    "id_wallet_desk": ["thẻ ngành", "huy hiệu", "cảnh sát", "đẩy qua bàn", "id wallet", "badge", "detective", "police"],
    "soup_bowl_spoon": ["bát canh", "thịt viên", "cái thìa", "bữa ăn", "soup", "bowl", "spoon", "meatballs"],
}
# snake_case props; KHÔNG dùng prop chung ("phone", "map", "clock", "rule_paper", "missing_poster"...) để không cướp
# phép gán mặc định của các ảnh chèn gốc (asset_library chọn ảnh ĐẦU TIÊN theo tên file).
PROPS = {
    "phone_sms_hand": ["phone_sms", "sms_chat", "phone_in_hand"],
    "phone_call_screen": ["phone_call", "call_screen", "calling"],
    "phone_gps_map": ["phone_gps", "gps_tracker", "location_tracker"],
    "phone_draft_cracked": ["phone_draft", "unsent_message", "cracked_phone_screen"],
    "receipt_thermal": ["receipt", "thermal_receipt", "bill"],
    "blueprint_plan": ["blueprint", "floor_plan", "building_plan"],
    "depth_diagram": ["depth_diagram", "cross_section", "basement_diagram"],
    "notebook_list_hand": ["notebook_list", "missing_list", "handwritten_list"],
    "missing_poster_numbered": ["missing_poster_numbered", "numbered_poster"],
    "cold_room_alarm": ["cold_room_panel", "thermometer", "temperature_alarm"],
    "wristwatch_digital": ["wristwatch", "digital_watch", "watch"],
    "price_tags_compare": ["price_tag", "price_tags", "handwriting_compare"],
    "cork_board": ["cork_board", "investigation_board", "evidence_board"],
    "evidence_markers": ["evidence_markers", "jewellery", "jewelry", "evidence"],
    "cleaver_honing": ["cleaver", "honing_steel", "butcher_knife"],
    "flashlight_mop": ["flashlight", "torch", "mop_handle"],
    "blue_drums_cart": ["blue_drum", "barrel", "drum_cart", "hand_cart"],
    "framed_old_photo": ["old_photo", "framed_photo", "photo_frame"],
    "dropped_phone_floor": ["dropped_phone", "phone_on_floor", "takeout_box", "sneaker"],
    "bun_broken_hands": ["steamed_bun", "bun", "bun_filling"],
    "rule_note_torn": ["torn_note", "torn_rule_paper", "ripped_paper"],
    "id_wallet_desk": ["id_wallet", "police_badge", "badge", "id_card"],
    "soup_bowl_spoon": ["soup_bowl", "soup", "spoon", "meatball_soup"],
}
