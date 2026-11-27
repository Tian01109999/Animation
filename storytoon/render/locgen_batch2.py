"""Địa điểm thư viện đợt 2 — vẽ GỐC bằng code (flat 2D vector, cùng bộ công cụ với locgen).

12 loại bối cảnh mới (bếp nhà hàng + cửa kho lạnh, bên trong kho lạnh, sân thượng bình minh, phố nhà ống
có miếu thần đất, phòng trưởng công an, phòng ICU, chợ có mái che, phòng điều tra bảng ghim, bến gỗ nhà sàn
ban đêm, tiệm tạp hoá nhỏ, mặt tiền toà án, phòng trọ có vali). Chỉ học THỂ LOẠI/bố cục chung; mọi chi tiết,
màu, biển hiệu đều bịa mới. Chữ trong ảnh hoặc lớp `signs`: TIẾNG ANH chung chung, không dấu, không cờ,
không quốc huy, không logo/thương hiệu thật.

Module tự đăng ký vào `locgen.LIBRARY_SCENES` / `LIBRARY_TAGS` khi được import (locgen import nó ở cuối file).
"""
from __future__ import annotations

import math
import random

import skia

from . import locgen as L
from .locgen import (H, W, Persp, Scene, _R, _bottle_rows, _corridor, _floor_tiles, _plastic_stool, _room_shell,
                     _tube, _vignette, box3, ellipse_glow, frac_slot, glow, hgrad, new_surface, path_fill, power_pole,
                     quad, rad_paint, round_tree, sag_wire, stars, text_center, tint, vgrad)
from .skutil import fill, oval, poly, rrect, shade, stroke


# =================================================================== đồ vật dùng chung
def _star5(cx, cy, r, ri=None) -> skia.Path:
    ri = ri or r * 0.42
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else ri
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    return poly(pts)


def _cylinder(c, cx, top, bot, r, col, cap=None) -> None:
    ry = r * 0.22
    c.drawPath(oval(cx, bot, r, ry), fill(shade(col, -0.15)))
    c.drawRect(_R(cx - r, top, cx + r, bot), fill(col))
    hgrad(c, cx - r, top, cx + r, bot, [("#000000", 0.0), ("#ffffff", 0.22), ("#000000", 0.0), ("#000000", 0.25)],
          [0, 0.3, 0.6, 1])
    for k in (0.33, 0.66):
        y = top + (bot - top) * k
        c.drawLine(cx - r, y, cx + r, y, stroke(shade(col, -0.12), max(2.0, r * 0.03)))
    c.drawPath(oval(cx, top, r, ry), fill(shade(cap or col, 0.12)))


def _suitcase(c, x, base, w, h, col, tag="#f3c94e") -> None:
    l, r, t = x - w / 2, x + w / 2, base - h
    for hx in (x - w * 0.2, x + w * 0.2):
        c.drawRect(_R(hx - w * 0.025, t - h * 0.34, hx + w * 0.025, t), fill("#5a5e66"))
    c.drawPath(rrect(x - w * 0.27, t - h * 0.38, x + w * 0.27, t - h * 0.3, h * 0.03), fill("#2f3238"))
    c.drawPath(rrect(l, t, r, base - h * 0.06, w * 0.12), fill(col))
    for k in (0.3, 0.5, 0.7):
        c.drawLine(l + w * k, t + h * 0.07, l + w * k, base - h * 0.13, stroke(shade(col, -0.18), max(2.0, w * 0.025)))
    c.drawPath(rrect(l + w * 0.05, t + h * 0.05, l + w * 0.17, base - h * 0.14, w * 0.05), fill("#ffffff", 0.22))
    for wx in (l + w * 0.16, r - w * 0.16):
        c.drawCircle(wx, base - h * 0.04, h * 0.045, fill("#1e2026"))
    c.drawLine(r - w * 0.26, t, r - w * 0.12, t + h * 0.17, stroke("#2f3238", max(2.0, w * 0.012)))
    c.save()
    c.rotate(-8, r - w * 0.1, t + h * 0.2)
    c.drawPath(rrect(r - w * 0.18, t + h * 0.15, r - w * 0.02, t + h * 0.27, w * 0.02), fill(tag))
    c.drawCircle(r - w * 0.15, t + h * 0.18, w * 0.012, fill("#2f3238"))
    c.restore()


def _carton(c, l, base, w, h, col="#c49a64") -> None:
    th = h * 0.16
    quad(c, [(l, base - h), (l + w, base - h), (l + w * 1.1, base - h - th), (l + w * 0.1, base - h - th)], shade(col, 0.12))
    quad(c, [(l + w, base - h), (l + w * 1.1, base - h - th), (l + w * 1.1, base - th), (l + w, base)], shade(col, -0.22))
    c.drawRect(_R(l, base - h, l + w, base), fill(col))
    quad(c, [(l + w * 0.45, base - h), (l + w * 0.57, base - h), (l + w * 0.67, base - h - th), (l + w * 0.55, base - h - th)],
         "#e2d3a8", 0.8)
    c.drawRect(_R(l + w * 0.45, base - h, l + w * 0.57, base - h * 0.78), fill("#e2d3a8", 0.8))
    c.drawLine(l + w * 0.12, base - h * 0.4, l + w * 0.35, base - h * 0.4, stroke(shade(col, -0.35), max(2.0, w * 0.02)))


def _bulb(c, x, y0, y1, lit=True, col="#ffd98a", r=24) -> None:
    c.drawLine(x, y0, x, y1, stroke("#18181c", 4))
    c.drawPath(rrect(x - r * 0.5, y1, x + r * 0.5, y1 + r * 1.1, 4), fill("#2a2a2e"))
    c.drawPath(oval(x, y1 + r * 2.1, r, r * 1.25), fill("#fff3cf" if lit else "#c9c4b4"))
    if lit:
        glow(c, x, y1 + r * 2.1, r * 18, col, 0.42)
        glow(c, x, y1 + r * 2.1, r * 4, "#fff6dc", 0.8)


def _shutter(c, l, t, r, b, col="#8a8e94") -> None:
    c.drawRect(_R(l, t, r, b), fill(col))
    y = t + 12
    while y < b:
        c.drawLine(l, y, r, y, stroke(shade(col, -0.18), 5))
        y += 26
    c.drawRect(_R(l - 12, t - 56, r + 12, t), fill(shade(col, -0.32)))
    c.drawRect(_R(l, b - 30, r, b), fill(shade(col, -0.25)))
    c.drawPath(rrect((l + r) / 2 - 60, b - 70, (l + r) / 2 + 60, b - 46, 8), fill(shade(col, -0.4)))


def _scooter(c, mx, my, k, col="#2f6fb0", face=-1) -> None:
    """Xe tay ga nhìn ngang (mx,my = chân giữa hai bánh; k = px/m; face=-1 đầu xe sang trái)."""
    c.save()
    c.translate(mx, 0)
    c.scale(face * -1.0, 1.0)
    c.translate(-mx, 0)
    wr = 0.26 * k
    for dx in (-0.6 * k, 0.6 * k):
        c.drawCircle(mx + dx, my - wr, wr, fill("#111216"))
        c.drawCircle(mx + dx, my - wr, wr * 0.45, fill("#9aa0a8"))
    c.drawPath(oval(mx - 0.38 * k, my - 0.6 * k, 0.36 * k, 0.17 * k), fill(col))
    c.drawPath(rrect(mx - 0.72 * k, my - 0.84 * k, mx - 0.1 * k, my - 0.72 * k, 0.05 * k), fill("#16171b"))
    c.drawRect(_R(mx - 0.12 * k, my - 0.44 * k, mx + 0.36 * k, my - 0.36 * k), fill("#3a3d44"))
    quad(c, [(mx + 0.28 * k, my - 0.36 * k), (mx + 0.5 * k, my - 0.36 * k), (mx + 0.66 * k, my - 0.98 * k),
             (mx + 0.48 * k, my - 1.04 * k)], col)
    c.drawLine(mx + 0.55 * k, my - 0.95 * k, mx + 0.6 * k, my - 1.12 * k, stroke("#16171b", max(3.0, 0.04 * k)))
    c.drawLine(mx + 0.42 * k, my - 1.12 * k, mx + 0.74 * k, my - 1.12 * k, stroke("#16171b", max(3.0, 0.035 * k)))
    c.drawCircle(mx + 0.66 * k, my - 0.9 * k, 0.06 * k, fill("#f4efe0"))
    c.drawPath(oval(mx + 0.62 * k, my - wr * 1.6, 0.18 * k, 0.07 * k), fill(shade(col, -0.2)))
    c.restore()


def _spirit_house(c, x, base, k, night) -> None:
    """Miếu thần đất nhỏ trên cột (kiểu chung chung, màu bịa)."""
    post = 1.25 * k
    c.drawRect(_R(x - 0.05 * k, base - post, x + 0.05 * k, base), fill("#e9e2d2"))
    c.drawRect(_R(x - 0.1 * k, base - 0.08 * k, x + 0.1 * k, base), fill("#c9c0ae"))
    pt = base - post
    c.drawRect(_R(x - 0.34 * k, pt - 0.05 * k, x + 0.34 * k, pt + 0.02 * k), fill("#c99a3c"))
    bt = pt - 0.42 * k
    c.drawRect(_R(x - 0.22 * k, bt, x + 0.22 * k, pt - 0.05 * k), fill("#c8352e"))
    for px_ in (x - 0.2 * k, x + 0.2 * k):
        c.drawRect(_R(px_ - 0.025 * k, bt, px_ + 0.025 * k, pt - 0.05 * k), fill("#e8c86a"))
    c.drawPath(rrect(x - 0.08 * k, bt + 0.13 * k, x + 0.08 * k, pt - 0.05 * k, 0.06 * k), fill("#4a140e"))
    c.drawPath(poly([(x - 0.33 * k, bt + 0.02 * k), (x + 0.33 * k, bt + 0.02 * k), (x, bt - 0.34 * k)]), fill("#e0b040"))
    c.drawPath(poly([(x - 0.2 * k, bt - 0.02 * k), (x + 0.2 * k, bt - 0.02 * k), (x, bt - 0.24 * k)]), fill("#c8352e"))
    c.drawLine(x, bt - 0.34 * k, x, bt - 0.52 * k, stroke("#e0b040", max(2.0, 0.025 * k)))
    for sg in (-1, 1):
        c.drawLine(x + sg * 0.33 * k, bt + 0.02 * k, x + sg * 0.42 * k, bt - 0.08 * k, stroke("#e0b040", max(2.0, 0.03 * k)))
    for j, col in enumerate(("#f3c94e", "#f08a2c", "#ffffff", "#d8423a")):
        c.drawCircle(x - 0.26 * k + j * 0.17 * k, pt - 0.09 * k, 0.04 * k, fill(col))
    for j in range(3):
        c.drawLine(x + 0.24 * k + j * 0.025 * k, pt - 0.05 * k, x + 0.22 * k + j * 0.03 * k, pt - 0.24 * k,
                   stroke("#8a3a22", max(1.5, 0.008 * k)))
    if night:
        glow(c, x, bt + 0.25 * k, 0.7 * k, "#ff8a3a", 0.5)
        c.drawCircle(x, bt + 0.25 * k, 0.03 * k, fill("#ffd07a"))


def _skyline(c, base, seed, col, lit, lit_col, hmin, hmax, wmin, wmax) -> list:
    rng = random.Random(seed)
    x, tops = -120.0, []
    while x < W + 120:
        w, h = rng.uniform(wmin, wmax), rng.uniform(hmin, hmax)
        top = base - h
        c.drawRect(_R(x, top, x + w, base), fill(col))
        if rng.random() < 0.35:
            c.drawRect(_R(x + w * 0.28, top - h * 0.1, x + w * 0.72, top), fill(col))
            top -= h * 0.1
        for wy in range(int(base - h + 30), int(base - 20), 56):
            for wx in range(int(x + 18), int(x + w - 26), 44):
                if rng.random() < lit:
                    c.drawRect(_R(wx, wy, wx + 20, wy + 28), fill(lit_col, rng.uniform(0.5, 0.95)))
        tops.append((x + w / 2, top))
        x += w + rng.uniform(-10, 30)
    return tops


def _frame(c, l, t, r, b, wood="#5a3a22", inner="#f2ead8", gold=None) -> None:
    c.drawRect(_R(l + 8, t + 10, r + 8, b + 10), fill("#000000", 0.18))
    c.drawRect(_R(l, t, r, b), fill(wood))
    bw = (r - l) * 0.08
    c.drawRect(_R(l + bw, t + bw, r - bw, b - bw), fill(inner))
    if gold:
        c.drawRect(_R(l + bw * 0.6, t + bw * 0.6, r - bw * 0.6, b - bw * 0.6), stroke(gold, max(2.0, bw * 0.12)))


def _certificate(c, l, t, r, b, seal="#c8352e") -> None:
    _frame(c, l, t, r, b, wood="#2b2420", inner="#f4efe2", gold="#c99a3c")
    w = r - l
    for j in range(5):
        y = t + (b - t) * (0.3 + j * 0.11)
        ww = w * (0.55 if j == 0 else 0.62 - (j % 2) * 0.12)
        c.drawLine(l + (w - ww) / 2, y, l + (w + ww) / 2, y, stroke("#8a8478", max(3.0, (b - t) * 0.022)))
    c.drawCircle(r - w * 0.24, b - (b - t) * 0.22, w * 0.07, fill(seal))
    c.drawCircle(r - w * 0.24, b - (b - t) * 0.22, w * 0.045, fill("#e8c86a"))


def _missing_card(c, x, y, w, h, rot, rng) -> tuple:
    """Thẻ người mất tích mini (dải đầu đỏ, khung ảnh có bóng người, các dòng). Trả toạ độ đinh ghim."""
    c.save()
    c.rotate(rot, x + w / 2, y + h / 2)
    c.drawRect(_R(x + 6, y + 8, x + w + 6, y + h + 8), fill("#000000", 0.16))
    c.drawRect(_R(x, y, x + w, y + h), fill("#f6f2e8"))
    c.drawRect(_R(x, y, x + w, y + h * 0.15), fill("#c8202a"))
    for j in range(2):
        c.drawLine(x + w * 0.2, y + h * (0.06 + j * 0.05), x + w * 0.8, y + h * (0.06 + j * 0.05), stroke("#f6f2e8", max(2.0, h * 0.02), 0.75))
    pl, pt_, pr, pb = x + w * 0.2, y + h * 0.2, x + w * 0.8, y + h * 0.62
    c.drawRect(_R(pl, pt_, pr, pb), fill("#a9adb2"))
    cx = (pl + pr) / 2
    c.drawCircle(cx, pt_ + (pb - pt_) * 0.4, (pr - pl) * 0.18, fill("#6b7078"))
    c.drawPath(oval(cx, pb, (pr - pl) * 0.36, (pb - pt_) * 0.3), fill("#6b7078"))
    c.save()
    c.clipRect(_R(pl, pt_, pr, pb))
    c.restore()
    c.drawRect(_R(pl, pb, pr, pb + 2), fill("#f6f2e8"))
    for j in range(4):
        yy = y + h * (0.7 + j * 0.07)
        c.drawLine(x + w * 0.12, yy, x + w * (0.88 - (j % 2) * 0.22), yy, stroke("#7a7a7a", max(2.0, h * 0.018)))
    c.restore()
    col = rng.choice(["#d0302a", "#2f6fb0", "#f3c94e"])
    c.drawCircle(x + w / 2, y + h * 0.05, max(6.0, w * 0.05), fill(col))
    return (x + w / 2, y + h * 0.05)


# =================================================================== 1. bếp nhà hàng + cửa kho lạnh
def scene_bep_nha_hang(tod: str) -> Scene:
    night = tod == "night"
    s = new_surface()
    c = s.getCanvas()
    BY = 1450
    P = _room_shell(c, "#a3aca4", "#3d4441", "#363c3a", back_y=BY, pattern=False)
    TT = 860
    c.drawRect(_R(0, TT, W, BY - 40), fill("#e6ebe7"))
    for x in range(0, W + 1, 90):
        c.drawLine(x, TT, x, BY - 40, stroke("#c2cac4", 4))
    for y in range(TT, BY - 40, 90):
        c.drawLine(0, y, W, y, stroke("#c2cac4", 4))
    c.drawRect(_R(0, TT - 20, W, TT), fill("#7f8882"))
    rng = random.Random(31)
    for _ in range(16):
        x, y = rng.uniform(0, W), rng.uniform(200, 1400)
        c.drawPath(oval(x, y, rng.uniform(60, 220), rng.uniform(40, 160)), fill("#5a6050", rng.uniform(0.04, 0.08)))
    _tube(c, 1250, 110, 900)
    _tube(c, 2700, 110, 900)
    # quạt hút
    c.drawRect(_R(240, 250, 720, 730), fill("#6f7873"))
    c.drawRect(_R(272, 282, 688, 698), fill("#4f5652"))
    c.drawCircle(480, 490, 180, fill("#23272a"))
    for k in range(4):
        c.save()
        c.translate(480, 490)
        c.rotate(k * 90 + 24)
        c.drawPath(oval(92, 0, 84, 32), fill("#8a938e"))
        c.restore()
    c.drawCircle(480, 490, 30, fill("#b9c0bc"))
    for y in range(320, 670, 36):
        c.drawLine(300, y, 660, y, stroke("#9aa29d", 4, 0.6))
    # thanh nam châm dao
    c.drawPath(rrect(960, 610, 1760, 650, 10), fill("#2b2f33"))
    x, i = 1000, 0
    while x < 1700:
        if i % 2 == 0:
            c.drawPath(rrect(x, 600, x + 120, 790, 10), fill("#cdd4d8"))
            c.drawLine(x + 4, 790, x + 116, 790, stroke("#eef2f4", 6))
            c.drawCircle(x + 92, 632, 13, fill("#5a6066"))
            c.drawPath(rrect(x + 44, 790, x + 76, 930, 10), fill("#7a4a2a"))
            for ry in (830, 890):
                c.drawCircle(x + 60, ry, 5, fill("#d9d4c4"))
            x += 160
        else:
            c.drawPath(poly([(x, 800), (x + 36, 800), (x + 36, 640), (x + 10, 590)]), fill("#cdd4d8"))
            c.drawPath(rrect(x + 4, 800, x + 32, 905, 8), fill("#5a3a22"))
            x += 80
        i += 1
    # kệ + lò vi sóng
    c.drawRect(_R(2330, 780, 2780, 802), fill("#8a938e"))
    for bx in (2380, 2730):
        quad(c, [(bx - 8, 802), (bx + 8, 802), (bx + 8, 860), (bx - 8, 820)], "#6f7873")
    c.drawPath(rrect(2370, 590, 2740, 780, 14), fill("#d9dcd8"))
    c.drawPath(rrect(2392, 616, 2600, 756, 10), fill("#2a2e30"))
    c.drawRect(_R(2400, 624, 2470, 748), fill("#ffffff", 0.08))
    for j in range(4):
        c.drawCircle(2670, 640 + j * 32, 10, fill("#8a908c"))
    # quầy sơ chế inox
    CL, CR = 180, 2520
    c.drawRect(_R(CL, 1160, CR, 1202), fill("#dfe4e6"))
    c.drawRect(_R(CL, 1202, CR, 1290), fill("#aab3b8"))
    hgrad(c, CL, 1202, CR, 1290, [("#ffffff", 0.0), ("#ffffff", 0.25), ("#ffffff", 0.0)], [0, 0.4, 1])
    c.drawRect(_R(CL + 20, 1290, CR - 20, 1500), fill("#4d5458"))
    c.drawRect(_R(CL + 20, 1420, CR - 20, 1440), fill("#9aa3a8"))
    for lx in (CL + 20, CL + 1170, CR - 50):
        c.drawRect(_R(lx, 1290, lx + 30, 1500), fill("#8a9398"))
    for j, (bx, col) in enumerate(((420, "#3a78c2"), (620, "#c9d0d4"), (820, "#3a78c2"), (1500, "#c9d0d4"), (1700, "#c9d0d4"))):
        _cylinder(c, bx, 1290, 1418, 70, col)
    for j in range(5):
        _carton(c, 1900 + j * 0, 1418, 0, 0) if False else None
    _carton(c, 1960, 1418, 260, 150, "#b98e5a")
    for k, bx in enumerate((330, 520, 710, 900, 2150, 2340)):
        for st in range(1 + k % 3):
            y = 1150 - st * 26
            c.drawPath(rrect(bx - 72, y - 44, bx + 72, y + 6, 26), fill("#f4f6f4"))
            c.drawPath(oval(bx, y - 44, 72, 13), fill("#d9dfdc"))
    c.drawRect(_R(1250, 1136, 1640, 1160), fill("#b98e5a"))
    c.drawPath(rrect(1330, 1112, 1520, 1138, 6), fill("#cdd4d8"))
    # thớt gỗ (khúc cây)
    sx, sb = 2780, 1760
    c.drawPath(oval(sx, sb, 170, 42), fill("#5a3a22"))
    c.drawRect(_R(sx - 170, 1420, sx + 170, sb), fill("#7a5232"))
    for j in range(5):
        c.drawLine(sx - 150 + j * 70, 1440, sx - 150 + j * 70, sb - 10, stroke("#6a4428", 6))
    c.drawPath(oval(sx, 1420, 170, 42), fill("#c99a64"))
    for rr in (120, 80, 40):
        c.drawPath(oval(sx, 1420, rr, rr * 0.25), stroke("#a8794a", 4))
    # cửa kho lạnh
    FL, FR, FT = 2960, 3680, 800
    c.drawRect(_R(FL - 46, FT - 46, FR + 46, BY), fill("#6f797e"))
    c.drawRect(_R(FL, FT, FR, BY - 10), fill("#b4bdc2"))
    for k in range(1, 6):
        xx = FL + (FR - FL) * k / 6
        c.drawLine(xx, FT, xx, BY - 10, stroke("#a1aaaf", 6))
    hgrad(c, FL, FT, FR, BY - 10, [("#ffffff", 0.0), ("#ffffff", 0.22), ("#ffffff", 0.0)], [0.1, 0.35, 0.6])
    for hy in (FT + 110, BY - 220):
        c.drawPath(rrect(FL - 30, hy, FL + 40, hy + 90, 10), fill("#4f575c"))
    c.drawPath(rrect(FR - 150, 1030, FR - 64, 1250, 18), fill("#2b2f33"))
    c.drawPath(rrect(FR - 230, 1100, FR - 64, 1150, 14), fill("#3a3f44"))
    c.drawPath(rrect(FL + 200, FT + 80, FL + 470, FT + 250, 34), fill("#5a666e"))
    c.drawPath(rrect(FL + 214, FT + 94, FL + 456, FT + 236, 26), fill("#dfe9ef"))
    for j in range(10):
        c.drawCircle(FL + 230 + rng.uniform(0, 210), FT + 110 + rng.uniform(0, 110), rng.uniform(6, 16), fill("#ffffff", 0.7))
    vgrad(c, FL, BY - 160, FR, BY - 10, [("#ffffff", 0.0), ("#e9f4ff", 0.55)])
    c.drawPath(rrect(3150, 640, 3450, 760, 14), fill("#15171a"))
    # cống thoát sàn
    c.drawPath(oval(1900, 1880, 150, 34), fill("#1e2224"))
    for j in range(-3, 4):
        c.drawLine(1900 + j * 34, 1856, 1900 + j * 34, 1904, stroke("#4a5052", 5))
    lights = [{"x": 3300, "y": 700, "color": "#ff3b30"}]
    if night:
        tint(s, "#3a4866", 0.72)
        c.drawCircle(1500, 1250, 760, rad_paint(1500, 1250, 760, [("#f4f8ff", 0.2), ("#f4f8ff", 0.08), ("#f4f8ff", 0.0)], [0, 0.6, 1]))
        _vignette(c, 0.7)
    else:
        glow(c, 1900, 300, 1600, "#f4fff8", 0.18)
        _vignette(c, 0.35)
    text_center(c, "-18°C", 3300, 700, 80, "#ff3b30", "extrabold")
    glow(c, 3300, 700, 220, "#ff3b30", 0.4 if night else 0.2)
    mid = s.makeImageSnapshot()
    slots = {"left": P.slot(-1.6, 3.4), "center": P.slot(0.0, 3.4), "right": P.slot(1.6, 3.4),
             "at_counter": P.slot(-1.8, 4.1), "freezer_door": P.slot(4.3, 4.7)}
    signs = [{"text": "COLD ROOM", "box": [FL + 60, 1090, FL + 520, 1180], "style": "white_board"},
             {"text": "WASH HANDS", "box": [1900, 650, 2240, 760], "style": "white_board"}]
    return Scene(None, mid, slots=slots, signs=signs, floor_y=slots["center"]["y"], lights=lights,
                 baked_signs=[{"text": "-18°C", "box": [3150, 640, 3450, 760]}])


# =================================================================== 2. bên trong kho lạnh
def scene_kho_lanh_ben_trong(tod: str) -> Scene:
    P = Persp(f=1500, cx=W / 2, cy=1060, cam_h=1.55)
    XW, YC, Z0, ZB = 1.7, 2.45, 0.45, 7.0
    s = new_surface()
    c = s.getCanvas()
    c.drawRect(_R(0, 0, W, H), fill("#9fb2c4"))
    _corridor(c, P, XW, YC, Z0, ZB, "#9db0c2", "#b7c7d6", 0.12, "#8da0b2", "#c6d3df", "#a9bccd")
    _floor_tiles(c, P, -XW, XW, Z0, ZB, 0.5, "#7f92a4")
    z = 1.0
    while z < ZB:
        for sd in (-1, 1):
            c.drawLine(*P.p(sd * XW, 0, z), *P.p(sd * XW, YC, z), stroke("#93a6b8", max(2.0, 16 / z)))
        c.drawLine(*P.p(-XW, YC, z), *P.p(XW, YC, z), stroke("#aebdca", max(2.0, 16 / z)))
        z += 1.0
    # dàn lạnh trên tường hậu + nhũ băng
    rng = random.Random(8)
    path_fill(c, P.face_z(ZB - 0.02, -0.9, 0.9, 1.75, 2.3), "#d6dee6")
    l, t = P.p(-0.9, 2.3, ZB - 0.02)
    r, b = P.p(0.9, 1.75, ZB - 0.02)
    for k in range(3):
        fx = l + (r - l) * (k + 0.5) / 3
        c.drawCircle(fx, (t + b) / 2, (b - t) * 0.36, fill("#3a4652"))
        c.drawLine(fx - (b - t) * 0.36, (t + b) / 2, fx + (b - t) * 0.36, (t + b) / 2, stroke("#8a9aa8", 3))
        c.drawLine(fx, t + (b - t) * 0.14, fx, b - (b - t) * 0.14, stroke("#8a9aa8", 3))
    for i in range(16):
        x = l + (r - l) * i / 15
        quad(c, [(x - 6, b), (x + 6, b), (x, b + rng.uniform(16, 60))], "#f4fbff")
    # đèn tuýp trần
    path_fill(c, P.plane_y(YC - 0.005, -0.1, 0.1, 1.6, 5.5), "#f4fbff")
    x0, y0 = P.p(0, YC, 2.5)
    ellipse_glow(c, x0, y0 + 30, 700, 200, "#eaf6ff", 0.45)
    # ray móc treo
    for rx in (-0.7, 0.7):
        c.drawLine(*P.p(rx, YC - 0.12, 0.9), *P.p(rx, YC - 0.12, ZB - 0.2), stroke("#6d7f90", 7))
        zz = 1.3
        while zz < 6.5:
            hx, hy = P.p(rx, YC - 0.12, zz)
            k_ = P.f / zz
            p = skia.Path()
            p.moveTo(hx, hy)
            p.lineTo(hx, hy + 0.16 * k_)
            p.quadTo(hx, hy + 0.24 * k_, hx + 0.06 * k_, hy + 0.2 * k_)
            c.drawPath(p, stroke("#5d6d7c", max(2.0, 0.018 * k_)))
            zz += 0.6
    # kệ lưới hai bên + đồ đạc bỏ lại (túi, mũ bảo hiểm, giày)
    cols = ["#c74a9a", "#e8b84a", "#7a4a2a", "#3a78c2", "#5a8a4a", "#8a3a6a", "#d8423a", "#2b2d33", "#e0d6c0"]
    for sd in (-1, 1):
        xw, xf = sd * XW, sd * (XW - 0.5)
        for ty in (0.3, 0.95, 1.6, 2.2):
            path_fill(c, P.plane_y(ty, min(xw, xf), max(xw, xf), 0.8, 6.6), "#c9d3dc")
            for f_ in (0.25, 0.5, 0.75):
                xx = xw + (xf - xw) * f_
                c.drawLine(*P.p(xx, ty, 0.8), *P.p(xx, ty, 6.6), stroke("#9aabbb", 3))
        for ty in (0.3, 0.95, 1.6):
            zz = 1.0
            while zz < 6.2:
                ln = rng.uniform(0.35, 0.7)
                if rng.random() < 0.18:
                    zz += ln
                    continue
                kind = rng.choice(["bag", "bag", "box", "helmet", "shoes"])
                xi = xf + sd * 0.04
                xo = xw - sd * 0.06
                col = rng.choice(cols)
                k_ = P.f / (zz + ln / 2)
                if kind == "helmet":
                    hx, hy = P.p(xi + sd * 0.12, ty + 0.17, zz + 0.2)
                    rr = 0.16 * P.f / (zz + 0.2)
                    c.drawCircle(hx, hy, rr, fill("#3f8a4a"))
                    c.drawPath(rrect(hx - rr * 0.8 * sd if sd < 0 else hx, hy - rr * 0.3,
                                     hx if sd < 0 else hx + rr * 0.8, hy + rr * 0.25, rr * 0.2), fill("#1e2428"))
                    c.drawCircle(hx - rr * 0.35, hy - rr * 0.4, rr * 0.2, fill("#ffffff", 0.35))
                    c.drawLine(hx - rr, hy - rr * 0.15, hx + rr, hy - rr * 0.15, stroke("#f4fbff", max(2.0, rr * 0.08), 0.6))
                    zz += 0.45
                    continue
                h = {"bag": rng.uniform(0.28, 0.45), "box": rng.uniform(0.2, 0.42), "shoes": 0.12}[kind]
                path_fill(c, P.wall_x(xi, zz, zz + ln, ty, ty + h), shade(col, -0.12))
                path_fill(c, P.face_z(zz, xo, xi, ty, ty + h), col)
                if kind == "bag":
                    p = skia.Path()
                    p.moveTo(*P.p(xi, ty + h, zz + ln * 0.2))
                    p.quadTo(*P.p(xi, ty + h + 0.18, zz + ln / 2), *P.p(xi, ty + h, zz + ln * 0.8))
                    c.drawPath(p, stroke(shade(col, -0.3), max(2.0, 0.025 * k_)))
                if kind == "shoes":
                    path_fill(c, P.wall_x(xi, zz + ln * 0.5, zz + ln, ty, ty + h), shade(col, 0.1))
                c.drawLine(*P.p(xi, ty + h, zz), *P.p(xi, ty + h, zz + ln), stroke("#f4fbff", max(2.0, 0.02 * k_), 0.75))
                zz += ln + rng.uniform(0.02, 0.12)
        for zz in (1.0, 2.8, 4.6, 6.4):
            c.drawLine(*P.p(xf, 0, zz), *P.p(xf, 2.25, zz), stroke("#7d8fa0", max(3.0, 30 / zz)))
    # cống thoát + vệt băng sàn
    dx, dy = P.p(0, 0, 3.4)
    kk = P.f / 3.4
    c.drawPath(oval(dx, dy, 0.24 * kk, 0.24 * kk * 0.16), fill("#4a5a6a"))
    for j in range(-2, 3):
        c.drawLine(dx + j * 0.07 * kk, dy - 8, dx + j * 0.07 * kk, dy + 8, stroke("#2f3a46", 4))
    c.drawRect(_R(0, 0, W, H), rad_paint(W / 2, H / 2, 2600, [("#ffffff", 0.0), ("#eaf4ff", 0.4)], [0.45, 1]))
    for _ in range(320):
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        c.drawCircle(x, y, rng.choice([2.0, 3.0, 4.0, 6.0]), fill("#ffffff", rng.uniform(0.25, 0.8)))
    glow(c, W / 2, 1000, 900, "#cfe6ff", 0.25)
    mid = s.makeImageSnapshot()
    slots = {"left": P.slot(-0.5, 3.0), "center": P.slot(0.0, 3.0), "right": P.slot(0.5, 3.0), "far": P.slot(0.0, 5.5)}
    return Scene(None, mid, slots=slots, floor_y=slots["center"]["y"], lights=[{"x": W / 2, "y": 600, "color": "#eaf6ff"}])


# =================================================================== 3. sân thượng chung cư lúc bình minh
def scene_san_thuong_binh_minh(tod: str) -> Scene:
    night = tod == "night"
    P = Persp(f=1600, cx=W / 2, cy=1000, cam_h=1.6)
    ZP = 9.0
    sf = new_surface()
    c = sf.getCanvas()
    if night:
        vgrad(c, 0, 0, W, 1320, ["#0b1022", "#1d2742", "#33395e"], [0, 0.6, 1])
        stars(c, 0, 0, W, 700, 220, seed=61)
    else:
        vgrad(c, 0, 0, W, 1320, ["#3f3660", "#6b5a8c", "#b98aa6", "#f2b884"], [0, 0.38, 0.72, 1])
        glow(c, 2500, 1140, 1200, "#ffcf9a", 0.55)
        rng = random.Random(3)
        for _ in range(8):
            x, y = rng.uniform(-200, W), rng.uniform(150, 800)
            wl, hh = rng.uniform(500, 1200), rng.uniform(26, 60)
            c.drawPath(rrect(x, y, x + wl, y + hh, hh / 2), fill("#e6b2c0", rng.uniform(0.3, 0.6)))
    _skyline(c, 1320, 71, "#6a5c86" if not night else "#1c2240", 0.06 if not night else 0.22,
             "#ffd9a0" if not night else "#f2c46b", 220, 560, 120, 260)
    c.drawRect(_R(0, 0, W, 1320), fill("#f2b884" if not night else "#2c3458", 0.3))
    tops = _skyline(c, 1320, 72, "#43385f" if not night else "#10142a", 0.08 if not night else 0.3,
                    "#ffd9a0" if not night else "#f2c46b", 320, 900, 170, 340)
    for (x, t) in sorted(tops, key=lambda q: q[1])[:5]:
        c.drawLine(x, t, x, t - 90, stroke("#2a2440", 6))
        c.drawCircle(x, t - 94, 10, fill("#ff3b30"))
        glow(c, x, t - 94, 70, "#ff3b30", 0.6)
    far = sf.makeImageSnapshot()

    s = new_surface()
    c = s.getCanvas()
    roof = "#a69fb4"
    path_fill(c, P.plane_y(0, -14, 14, 0.8, ZP), roof)
    _floor_tiles(c, P, -14, 14, 0.8, ZP, 1.0, shade(roof, -0.12))
    rng = random.Random(9)
    for _ in range(10):
        x_, z_ = rng.uniform(-5, 5), rng.uniform(2.5, 8.5)
        sx_, sy_ = P.p(x_, 0, z_)
        k_ = P.f / z_
        c.drawPath(oval(sx_, sy_, rng.uniform(0.3, 0.9) * k_, rng.uniform(0.04, 0.09) * k_), fill("#6a6078", 0.18))
    par = "#8c839f"
    path_fill(c, P.face_z(ZP - 0.25, -14, 14, 0, 1.0), par)
    path_fill(c, P.plane_y(1.0, -14, 14, ZP - 0.25, ZP), shade(par, 0.2))
    for xx in range(-14, 15, 2):
        c.drawLine(*P.p(xx, 0.05, ZP - 0.25), *P.p(xx, 0.95, ZP - 0.25), stroke(shade(par, -0.12), 3))
    # toà nhà bên phải chạy theo phối cảnh
    bc = "#7a6d92"
    path_fill(c, P.wall_x(6.0, 2.0, ZP + 5, 0, 18), bc)
    zz = 2.4
    while zz < ZP + 4.5:
        for wy in (1.4, 4.4, 7.4, 10.4, 13.4, 16.0):
            lit = rng.random() < (0.35 if night else 0.12)
            path_fill(c, P.wall_x(5.99, zz, zz + 0.9, wy, wy + 1.3), "#ffd58a" if lit else shade(bc, -0.35))
        zz += 1.7
    # bồn nước
    def tank(x, z, r_m, h_m, stand_m, col):
        k = P.f / z
        cx, base = P.p(x, 0, z)
        for dx in (-r_m * 0.75, r_m * 0.75):
            c.drawRect(_R(cx + dx * k - 0.04 * k, base - stand_m * k, cx + dx * k + 0.04 * k, base), fill("#4a4458"))
        c.drawLine(cx - r_m * 0.75 * k, base - stand_m * 0.5 * k, cx + r_m * 0.75 * k, base - stand_m * k, stroke("#4a4458", 0.03 * k))
        c.drawRect(_R(cx - r_m * 0.95 * k, base - stand_m * k - 0.05 * k, cx + r_m * 0.95 * k, base - stand_m * k), fill("#5a546a"))
        _cylinder(c, cx, base - (stand_m + h_m) * k, base - stand_m * k - 0.04 * k, r_m * k, col)
        c.drawPath(oval(cx, base - (stand_m + h_m) * k - 0.08 * k, r_m * 0.3 * k, r_m * 0.08 * k), fill(shade(col, -0.2)))
    tank(-3.4, 7.2, 0.5, 1.2, 0.9, "#3a78c2")
    tank(-5.2, 6.4, 0.62, 1.5, 0.9, "#e9e6ee")
    # anten TV
    ax, ab = P.p(1.2, 0, 8.2)
    at = P.p(1.2, 3.4, 8.2)[1]
    c.drawLine(ax, ab, ax, at, stroke("#3a3448", 7))
    for j in range(4):
        y = at + j * 40
        c.drawLine(ax - 110 + j * 18, y, ax + 110 - j * 18, y, stroke("#3a3448", 5))
    # dây phơi quần áo
    pA, pB = (-2.6, 5.0), (3.0, 5.8)
    tops_ = []
    for (x, z) in (pA, pB):
        bx_, by_ = P.p(x, 0, z)
        tx_, ty_ = P.p(x, 2.0, z)
        c.drawLine(bx_, by_, tx_, ty_, stroke("#4a4458", max(4.0, 0.05 * P.f / z)))
        tops_.append((tx_, ty_))
    (x0, y0), (x1, y1) = tops_
    sag = 40
    sag_wire(c, x0, y0, x1, y1, sag, "#3a3448", 4)
    cxm, cym = (x0 + x1) / 2, (y0 + y1) / 2 + sag * 2
    clothes = ["#d8423a", "#f3c94e", "#3a78c2", "#ffffff", "#4fa35a", "#c74a9a", "#f08a2c", "#7ab0d8"]
    n = 9
    for i in range(1, n):
        t = i / n
        x = (1 - t) ** 2 * x0 + 2 * t * (1 - t) * cxm + t * t * x1
        y = (1 - t) ** 2 * y0 + 2 * t * (1 - t) * cym + t * t * y1
        k = P.f / (pA[1] + (pB[1] - pA[1]) * t)
        col = clothes[i % len(clothes)]
        kind = i % 3
        if kind == 0:      # áo thun
            w_ = 0.5 * k
            path_fill(c, poly([(x - w_ / 2, y), (x + w_ / 2, y), (x + w_ * 0.75, y + 0.15 * k), (x + w_ * 0.38, y + 0.2 * k),
                               (x + w_ * 0.38, y + 0.62 * k), (x - w_ * 0.38, y + 0.62 * k), (x - w_ * 0.38, y + 0.2 * k),
                               (x - w_ * 0.75, y + 0.15 * k)]), col)
        elif kind == 1:    # khăn
            c.drawRect(_R(x - 0.2 * k, y, x + 0.2 * k, y + 0.7 * k), fill(col))
            c.drawRect(_R(x - 0.2 * k, y + 0.58 * k, x + 0.2 * k, y + 0.63 * k), fill(shade(col, -0.2)))
        else:              # quần
            path_fill(c, poly([(x - 0.2 * k, y), (x + 0.2 * k, y), (x + 0.22 * k, y + 0.75 * k), (x + 0.04 * k, y + 0.75 * k),
                               (x, y + 0.25 * k), (x - 0.04 * k, y + 0.75 * k), (x - 0.22 * k, y + 0.75 * k)]), col)
        c.drawRect(_R(x - 0.05 * k, y - 0.03 * k, x + 0.05 * k, y + 0.02 * k), fill("#2b2d33"))
    # cục nóng điều hoà
    for (x, z, yo) in ((-2.9, 2.7, 0.0), (-2.9, 2.7, 0.72)):
        k = P.f / z
        l, b = P.p(x, yo, z)
        w_, h_ = 0.9 * k, 0.7 * k
        box3(c, l, b - h_, l + w_, b, "#d6d8d4", top_h=0.1 * k, side_w=0.12 * k, side="right")
        c.drawCircle(l + w_ * 0.4, b - h_ / 2, h_ * 0.36, fill("#4a4e55"))
        for j in range(5):
            c.drawLine(l + w_ * 0.4 - h_ * 0.36, b - h_ / 2 - h_ * 0.28 + j * h_ * 0.14,
                       l + w_ * 0.4 + h_ * 0.36, b - h_ / 2 - h_ * 0.28 + j * h_ * 0.14, stroke("#8a9098", 4))
        for j in range(6):
            c.drawLine(l + w_ * 0.78, b - h_ * 0.85 + j * h_ * 0.13, l + w_ * 0.95, b - h_ * 0.85 + j * h_ * 0.13, stroke("#a9aca8", 4))
    # chậu cây lưỡi hổ + ghế nhựa đỏ
    px_, pb_ = P.p(3.4, 0, 4.2)
    k = P.f / 4.2
    quad(c, [(px_ - 0.22 * k, pb_ - 0.4 * k), (px_ + 0.22 * k, pb_ - 0.4 * k), (px_ + 0.16 * k, pb_), (px_ - 0.16 * k, pb_)], "#b8643a")
    for j in range(9):
        a = math.pi * (0.25 + 0.5 * j / 8)
        ln = rng.uniform(0.5, 0.9) * k
        tx_, ty_ = px_ + math.cos(a) * ln * 0.5, pb_ - 0.4 * k - math.sin(a) * ln
        quad(c, [(px_ - 0.04 * k + j * 0.01 * k, pb_ - 0.4 * k), (px_ + 0.04 * k + j * 0.01 * k, pb_ - 0.4 * k), (tx_, ty_)],
             "#3f7a3a" if j % 2 else "#5a9a4a")
    cx_, cb_ = P.p(1.9, 0, 3.9)
    k = P.f / 3.9
    ch = "#d8352e"
    c.drawPath(rrect(cx_ - 0.2 * k, cb_ - 0.85 * k, cx_ + 0.2 * k, cb_ - 0.45 * k, 0.05 * k), fill(shade(ch, -0.1)))
    c.drawPath(rrect(cx_ - 0.24 * k, cb_ - 0.47 * k, cx_ + 0.24 * k, cb_ - 0.4 * k, 0.03 * k), fill(ch))
    for dx in (-0.2, 0.2):
        quad(c, [(cx_ + dx * k - 0.025 * k, cb_ - 0.4 * k), (cx_ + dx * k + 0.025 * k, cb_ - 0.4 * k),
                 (cx_ + dx * 1.15 * k + 0.025 * k, cb_), (cx_ + dx * 1.15 * k - 0.025 * k, cb_)], shade(ch, -0.2))
    if night:
        tint(s, "#4a5680", 0.6)
    else:
        tint(s, "#e8c0cc", 0.16)
        c.drawRect(_R(0, 0, W, H), lin_paint_h())
    mid = s.makeImageSnapshot()
    slots = {"center": P.slot(0.0, 3.2), "left": P.slot(-1.4, 3.4), "right": P.slot(1.4, 3.6),
             "ledge": P.slot(-0.5, 8.2), "far": P.slot(0.4, 6.5)}
    return Scene(far, mid, slots=slots, floor_y=slots["center"]["y"], parallax=(0.82, 1.0, 1.15),
                 lights=[{"x": 2500, "y": 1140, "color": "#ffcf9a" if not night else "#f2c46b"}])


def lin_paint_h() -> skia.Paint:
    """Ánh nắng sớm hắt ngang từ phải (dùng cho sân thượng bình minh)."""
    return L.lin_paint((W, 0), (W * 0.3, 0), [("#ffcf9a", 0.22), ("#ffcf9a", 0.0)])


# =================================================================== 4. phố nhà ống (dây điện, miếu thần đất)
def scene_pho_nha_ong_hem(tod: str) -> Scene:
    day = tod == "day"
    P = Persp(f=1500, cx=W / 2, cy=1000, cam_h=1.6)
    RW, SW, Z0, ZB = 3.0, 4.7, 0.6, 80.0
    sf = new_surface()
    c = sf.getCanvas()
    if day:
        vgrad(c, 0, 0, W, 1100, ["#c4c2bc", "#d9d4c8", "#e6e0d2"])
    else:
        vgrad(c, 0, 0, W, 1100, ["#151a33", "#2a3060", "#3c4470"])
        stars(c, 1300, 0, 2600, 600, 60, seed=12)
    rng = random.Random(5)
    x = -8.0
    while x < 8:
        w = rng.uniform(1.4, 2.8)
        path_fill(c, P.face_z(ZB, x, x + w, 0, rng.uniform(8, 20)), "#a8a296" if day else "#20264a")
        x += w
    c.drawRect(_R(0, 0, W, 1100), fill("#e6e0d2" if day else "#3c4470", 0.25))
    far = sf.makeImageSnapshot()

    s = new_surface()
    c = s.getCanvas()
    path_fill(c, P.plane_y(0, -RW, RW, Z0, ZB), "#6e6c68" if day else "#3e4048")
    z = 1.0
    while z < ZB:
        path_fill(c, P.plane_y(0.001, -0.07, 0.07, z, z + 1.6), "#e9e2c8")
        z += 4.0
    for (px_, pz, pw) in ((-1.2, 2.6, 0.8), (1.0, 5.0, 0.6)):
        cx_, cy_ = P.p(px_, 0, pz)
        rx = P.f * pw / pz
        c.drawPath(oval(cx_, cy_, rx, rx * 0.12), fill("#5a6a82" if not day else "#8a8c90", 0.55))
    for sd in (-1, 1):
        lo, hi = sorted((sd * RW, sd * SW))
        path_fill(c, P.plane_y(0.15, lo, hi, Z0, ZB), "#b4ada0" if day else "#5a5852")
        path_fill(c, P.wall_x(sd * RW, Z0, ZB, 0, 0.15), "#8a857a" if day else "#44423e")
        z = 1.0
        while z < 40:
            c.drawLine(*P.p(lo, 0.15, z), *P.p(hi, 0.15, z), stroke("#8f897c" if day else "#4a4844", max(2.0, 10 / z)))
            z += 0.8
    pal = ["#e2c9a0", "#c9d6c0", "#e6b8a0", "#b8c8d8", "#e8d890", "#d8b8c8", "#c0b49c", "#a8c4b8"]
    awn = ["#c8352e", "#2f6fb0", "#3f8a4a", "#e8a030", "#8a3a6a"]
    segs = [(Z0, 4.2), (4.2, 8.5), (8.5, 13.0), (13.0, 18.5), (18.5, 25.0), (25.0, 33.0), (33.0, 44.0), (44.0, 60.0), (60.0, ZB)]
    shop_lights = []
    for sd in (-1, 1):
        for si, (za, zb) in enumerate(segs):
            col = pal[(si * 3 + (sd > 0) * 5) % len(pal)]
            ht = rng.uniform(9.5, 14.0)
            x_ = sd * SW
            path_fill(c, P.wall_x(x_, za, zb, 0, ht), shade(col, -0.08 if sd < 0 else 0.0))
            path_fill(c, P.wall_x(x_, za, zb, ht - 0.35, ht), shade(col, -0.25))
            c.drawLine(*P.p(x_, 0, za), *P.p(x_, ht, za), stroke(shade(col, -0.35), max(2.0, 30 / za)))
            ga, gb = za + 0.25, zb - 0.25
            if rng.random() < (0.35 if day else 0.5):
                path_fill(c, P.wall_x(x_ * 0.999, ga, gb, 0.15, 2.8), "#f2c46b" if not day else "#6a5a48")
                for sy in (1.0, 1.7, 2.3):
                    c.drawLine(*P.p(x_ * 0.998, sy, ga), *P.p(x_ * 0.998, sy, gb),
                               stroke("#8a5a3a" if not day else "#4a3e32", max(2.0, 14 / za)))
                mx_, my_ = P.p(x_ * 0.99, 1.2, (ga + gb) / 2)
                shop_lights.append((mx_, my_, P.f / ((ga + gb) / 2)))
            else:
                path_fill(c, P.wall_x(x_ * 0.999, ga, gb, 0.15, 2.8), "#8e9298")
                yy = 0.3
                while yy < 2.8:
                    c.drawLine(*P.p(x_ * 0.998, yy, ga), *P.p(x_ * 0.998, yy, gb), stroke("#74787e", max(1.5, 8 / za)))
                    yy += 0.2
            aw = rng.choice(awn)
            quad(c, [P.p(x_, 3.05, ga), P.p(x_, 3.05, gb), P.p(sd * (SW - 1.1), 2.78, gb), P.p(sd * (SW - 1.1), 2.78, ga)], aw)
            path_fill(c, P.wall_x(sd * (SW - 1.1), ga, gb, 2.62, 2.78), shade(aw, -0.2))
            for wy in (4.0, 7.0, 10.0):
                if wy + 1.6 < ht - 0.4:
                    wz, wz2 = za + (zb - za) * 0.18, zb - (zb - za) * 0.18
                    lit = (not day) and rng.random() < 0.4
                    path_fill(c, P.wall_x(x_ * 0.998, wz, wz2, wy, wy + 1.4), "#f2c46b" if lit else shade(col, -0.45))
                    lo, hi = sorted((x_, sd * (SW - 0.45)))
                    path_fill(c, P.plane_y(wy - 0.25, lo, hi, wz - 0.1, wz2 + 0.1), shade(col, -0.3))
                    c.drawLine(*P.p(sd * (SW - 0.45), wy + 0.55, wz - 0.1), *P.p(sd * (SW - 0.45), wy + 0.55, wz2 + 0.1),
                               stroke("#2a2a30", max(1.5, 14 / za)))
                    bz = wz
                    while bz < wz2:
                        c.drawLine(*P.p(sd * (SW - 0.45), wy - 0.25, bz), *P.p(sd * (SW - 0.45), wy + 0.55, bz),
                                   stroke("#2a2a30", max(1.0, 8 / za)))
                        bz += 0.35
            if si in (1, 3, 5) and rng.random() < 0.8:
                bl, bt = P.p(sd * (SW - 0.06), 6.4, za + 0.6)
                br, bb = P.p(sd * (SW - 0.5), 3.6, za + 0.6)
                c.drawRect(_R(min(bl, br), bt, max(bl, br), bb), fill(rng.choice(["#c8352e", "#e8b84a", "#2f6fb0", "#f4efe4"])))
    # biển hiệu nhô ra (chữ tiếng Anh ở lớp signs)
    signs = []
    for (sd, z, text, style) in ((-1, 6.2, "NOODLES", "red_board"), (-1, 14.5, "PHARMACY", "white_board"),
                                 (-1, 27.0, "HOTEL", "gold_board"), (1, 5.6, "MOBILE FIX", "gold_board"),
                                 (1, 11.8, "TAILOR", "white_board"), (1, 21.0, "BAKERY", "red_board")):
        pa = P.p(sd * (SW - 0.05), 4.5, z)
        pb = P.p(sd * (SW - 2.0), 3.4, z)
        l_, r_ = sorted((pa[0], pb[0]))
        k_ = P.f / z
        c.drawLine(pa[0], pa[1] - 0.15 * k_, pb[0], pa[1] - 0.15 * k_, stroke("#2a2a30", max(2.0, 0.04 * k_)))
        c.drawRect(_R(l_ + 4, pa[1] + 6, r_ + 4, pb[1] + 6), fill("#000000", 0.25))
        signs.append({"text": text, "box": [round(l_), round(pa[1]), round(r_), round(pb[1])], "style": style})
    # cột điện + dây
    pole_tops = {-1: [], 1: []}
    for sd, zs in ((-1, (3.6, 14.0, 30.0)), (1, (8.0, 22.0, 45.0))):
        for z in zs:
            px_ = sd * (RW + 0.45)
            bx_, by_ = P.p(px_, 0.15, z)
            ty_ = P.p(px_, 9.0, z)[1]
            power_pole(c, bx_, ty_, by_, "#2a2a30", wd=max(6.0, 0.24 * P.f / z))
            pole_tops[sd].append((bx_, ty_ + 50))
    for sd in (-1, 1):
        pts = [(sd * W * 0.6 + W / 2, -60)] + pole_tops[sd]
        for (a, b) in zip(pts, pts[1:]):
            for j in range(4):
                sag_wire(c, a[0], a[1] + j * 14, b[0], b[1] + j * 6, rng.uniform(30, 90), "#16161c", max(2.0, 6 - j))
    for a in pole_tops[-1]:
        for b in pole_tops[1][:2]:
            sag_wire(c, a[0], a[1], b[0], b[1], rng.uniform(60, 160), "#16161c", 3)
    a = pole_tops[-1][0]
    for j in range(7):
        sag_wire(c, a[0] - 40, a[1] + 20 + j * 10, -100, a[1] + rng.uniform(-200, 200), rng.uniform(40, 160), "#16161c", 4)
    # đèn đường bên phải
    lx_, lb_ = P.p(RW + 0.4, 0.15, 7.0)
    lt_ = P.p(RW + 0.4, 6.6, 7.0)[1]
    hx_, hy_ = P.p(2.0, 6.5, 7.0)
    c.drawLine(lx_, lb_, lx_, lt_, stroke("#2a2a30", 12))
    c.drawLine(lx_, lt_, hx_, hy_, stroke("#2a2a30", 9))
    c.drawPath(rrect(hx_ - 40, hy_ - 6, hx_ + 20, hy_ + 16, 8), fill("#3a3a40"))
    gx_, gy_ = P.p(1.9, 0, 7.0)
    # miếu thần đất (trước-trái) + ghế nhựa + xe máy (phải)
    sx_, sb_ = P.p(-3.95, 0.15, 3.6)
    _spirit_house(c, sx_, sb_, P.f / 3.6, not day)
    tx_, tb_ = P.p(-3.3, 0.15, 4.8)
    _plastic_stool(c, tx_, tb_, 0.45 * P.f / 4.8)
    for (x_, z_, col) in ((3.8, 6.4, "#3a6fb8"), (3.85, 5.0, "#2f5fa0")):
        mx_, my_ = P.p(x_, 0.15, z_)
        _scooter(c, mx_, my_, P.f / z_, col, face=-1)
    if day:
        tint(s, "#efe6d6", 0.1)
        fog = rad_paint(W / 2, 1000, 1900, [("#ebe5d8", 0.82), ("#ebe5d8", 0.35), ("#ebe5d8", 0.0)], [0, 0.45, 1])
        c.drawRect(_R(0, 0, W, H), fog)
    else:
        tint(s, "#6f7aa8", 0.45)
        for (mx_, my_, k_) in shop_lights:
            glow(c, mx_, my_, 1.6 * k_, "#ffcf7a", 0.35)
        glow(c, hx_ - 10, hy_ + 14, 120, "#ffe0a0", 0.85)
        glow(c, hx_, hy_ + 300, 900, "#ffcf7a", 0.3)
        ellipse_glow(c, gx_, gy_, 700, 130, "#ffcf7a", 0.45)
        _vignette(c, 0.45)
    mid = s.makeImageSnapshot()
    slots = {"center": P.slot(0.0, 3.4), "left": P.slot(-1.6, 3.6), "right": P.slot(1.6, 3.6),
             "sidewalk_left": P.slot(-3.6, 4.8), "far": P.slot(0.3, 10.0)}
    return Scene(far, mid, slots=slots, signs=signs, floor_y=slots["center"]["y"], parallax=(0.85, 1.0, 1.15),
                 lights=[] if day else [{"x": round(hx_), "y": round(hy_), "color": "#ffcf7a"}])


# =================================================================== 5. phòng trưởng công an
def scene_phong_truong_cong_an(tod: str) -> Scene:
    s = new_surface()
    c = s.getCanvas()
    P = _room_shell(c, "#c4d2d2", "#8b7a66", "#83725f", back_y=1450, pattern=False)
    c.drawRect(_R(0, 1120, W, 1410), fill("#a9bcbc"))
    c.drawRect(_R(0, 1110, W, 1124), fill("#8a9e9e"))
    c.drawRect(_R(0, 0, W, 130), fill("#e2e8e8"))
    for x in range(0, W, 320):
        c.drawLine(x, 0, x, 130, stroke("#c9d2d2", 4))
    _tube(c, 1100, 140, 700)
    _tube(c, 2800, 140, 700)
    c.drawCircle(2300, 70, 34, fill("#f4f6f6"))
    c.drawCircle(2300, 70, 8, fill("#d8423a"))
    # rèm lá sách bên phải
    bl, bt, br, bb = 2990, 330, 3640, 1060
    vgrad(c, bl, bt, br, bb, ["#dfeef6", "#f4f6ee"])
    c.drawRect(_R(bl - 24, bt - 24, br + 24, bb + 24), stroke("#e8eeee", 24))
    y = bt + 10
    while y < bb:
        c.drawRect(_R(bl, y, br, y + 22), fill("#e4e9e6"))
        c.drawLine(bl, y + 22, br, y + 22, stroke("#b4bcba", 3))
        y += 36
    c.drawLine(bl + 60, bt, bl + 60, bb + 80, stroke("#8a9090", 3))
    # giấy khen + huy hiệu khiên-sao (bịa)
    _certificate(c, 420, 360, 720, 580)
    _certificate(c, 780, 360, 1080, 580, seal="#2f6fb0")
    _certificate(c, 600, 640, 900, 860)
    ex, ey = 1920, 560
    _frame(c, ex - 200, ey - 220, ex + 200, ey + 220, wood="#4a3020", inner="#1f2a4a")
    sh = skia.Path()
    sh.moveTo(ex - 120, ey - 140)
    sh.lineTo(ex + 120, ey - 140)
    sh.lineTo(ex + 120, ey + 10)
    sh.quadTo(ex + 110, ey + 120, ex, ey + 170)
    sh.quadTo(ex - 110, ey + 120, ex - 120, ey + 10)
    sh.close()
    c.drawPath(sh, fill("#c99a3c"))
    c.save()
    c.translate(ex, ey)
    c.scale(0.82, 0.82)
    c.translate(-ex, -ey)
    c.drawPath(sh, fill("#2f4a7a"))
    c.restore()
    c.drawPath(_star5(ex, ey - 10, 70), fill("#f0d27a"))
    # tủ hồ sơ + cúp
    fl = 2520
    c.drawRect(_R(fl, 820, fl + 360, 1450), fill("#7d8a8e"))
    for j in range(4):
        y = 845 + j * 150
        c.drawRect(_R(fl + 20, y, fl + 340, y + 135), fill("#8d9a9e"))
        c.drawPath(rrect(fl + 140, y + 55, fl + 220, y + 77, 8), fill("#c9ccd2"))
    for j, (tx, th) in enumerate(((fl + 70, 170), (fl + 180, 230), (fl + 290, 150))):
        c.drawRect(_R(tx - 40, 790, tx + 40, 820), fill("#3a2a1e"))
        c.drawRect(_R(tx - 8, 820 - th * 0.55, tx + 8, 790), fill("#d9b24a"))
        c.drawPath(rrect(tx - 40, 820 - th, tx + 40, 820 - th * 0.5, 30), fill("#e8c45a"))
        c.drawPath(oval(tx, 820 - th, 40, 10), fill("#b48a2a"))
    # ghế da lưng cao
    c.drawPath(rrect(1770, 1040, 2070, 1440, 50), fill("#3a2620"))
    c.drawPath(rrect(1800, 1070, 2040, 1300, 40), fill("#4a3028"))
    # bàn gỗ lớn (tiền cảnh)
    wood = "#7a4e32"
    quad(c, [(780, 1330), (3060, 1330), (3180, 1440), (660, 1440)], shade(wood, 0.18))
    c.drawRect(_R(660, 1440, 3180, 1470), fill(shade(wood, -0.1)))
    c.drawRect(_R(700, 1470, 3140, 1910), fill(wood))
    for (pl, pr) in ((760, 1380), (1460, 2380), (2460, 3080)):
        c.drawRect(_R(pl, 1530, pr, 1850), stroke(shade(wood, -0.22), 10))
    c.drawPath(oval(1920, 1910, 1400, 40), fill("#000000", 0.15))
    # đồ trên bàn
    lx = 960
    c.drawPath(oval(lx, 1370, 90, 18), fill("#b48a2a"))
    c.drawRect(_R(lx - 8, 1220, lx + 8, 1370), fill("#c99a3c"))
    c.drawPath(rrect(lx - 130, 1170, lx + 130, 1240, 30), fill("#2f6a4a"))
    c.drawRect(_R(lx - 130, 1205, lx + 130, 1240), fill("#245a3c"))
    glow(c, lx, 1300, 380, "#ffe7a8", 0.45)
    ph = 1260
    c.drawPath(rrect(ph - 90, 1300, ph + 90, 1380, 16), fill("#2b2d33"))
    c.drawPath(rrect(ph - 110, 1270, ph + 110, 1310, 20), fill("#1e2026"))
    for j in range(3):
        c.drawRect(_R(2560 - j * 6, 1360 - j * 60, 2800 + j * 6, 1420 - j * 60), fill("#f4f1e8"))
        c.drawRect(_R(2560 - j * 6, 1380 - j * 60, 2800 + j * 6, 1396 - j * 60), fill("#c8352e"))
    c.drawPath(rrect(1450, 1352, 1720, 1380, 6), fill("#f4f1e8"))
    c.drawPath(rrect(1470, 1338, 1730, 1364, 6), fill("#e9e4d6"))
    c.drawRect(_R(2230, 1390, 2430, 1400), fill("#2f6fb0"))
    _vignette(c, 0.3)
    mid = s.makeImageSnapshot()
    chief = P.slot(0.0, 4.0, clip_bottom=1400)
    slots = {"chief": chief, "desk": dict(chief), "visitor_left": P.slot(-2.3, 2.7), "visitor_right": P.slot(2.3, 2.7),
             "center": P.slot(0.0, 2.45)}
    signs = [{"text": "CAPTAIN", "box": [1780, 1352, 2060, 1420], "style": "gold_board"}]
    return Scene(None, mid, slots=slots, signs=signs, floor_y=slots["center"]["y"],
                 lights=[{"x": lx, "y": 1240, "color": "#ffe7a8"}])


# =================================================================== 6. phòng ICU
def scene_phong_icu(tod: str) -> Scene:
    night = tod == "night"
    s = new_surface()
    c = s.getCanvas()
    P = _room_shell(c, "#c9d6d2", "#b7c2bf", "#aeb9b6", back_y=1450, pattern=False)
    c.drawRect(_R(0, 0, W, 120), fill("#e4ebe8"))
    c.drawRect(_R(0, 1180, W, 1410), fill("#b2c4c0"))
    # cửa sổ đêm + thành phố
    wl, wt, wr, wb = 2960, 380, 3600, 1000
    vgrad(c, wl, wt, wr, wb, ["#0d1426", "#1d2742"] if night else ["#b9d0e0", "#e6eef2"])
    rng = random.Random(17)
    if night:
        stars(c, wl, wt, wr, wt + 250, 30, seed=5)
    x = wl
    while x < wr:
        w_ = rng.uniform(60, 130)
        top = rng.uniform(wt + 200, wb - 120)
        c.drawRect(_R(x, top, min(x + w_, wr), wb), fill("#141a2a" if night else "#8a96a6"))
        for wy in range(int(top + 20), int(wb - 10), 40):
            for wx in range(int(x + 10), int(min(x + w_, wr) - 14), 26):
                if rng.random() < (0.3 if night else 0.1):
                    c.drawRect(_R(wx, wy, wx + 12, wy + 18), fill("#f2c46b" if night else "#c9d3dc"))
        x += w_ + 6
    c.drawRect(_R(wl, wt, wr, wb), stroke("#e8eeec", 26))
    c.drawLine((wl + wr) / 2, wt, (wl + wr) / 2, wb, stroke("#e8eeec", 14))
    # cửa kính trái
    dl, dt, dr, db = 180, 600, 760, 1450
    c.drawRect(_R(dl - 26, dt - 26, dr + 26, db), fill("#8a9a98"))
    vgrad(c, dl, dt, dr, db, ["#a9c4cc", "#cfe0e4"], a=0.9)
    c.drawLine((dl + dr) / 2, dt, (dl + dr) / 2, db, stroke("#8a9a98", 12))
    for k in range(2):
        quad(c, [(dl + 40 + k * 300, db), (dl + 110 + k * 300, db), (dl + 230 + k * 300, dt), (dl + 160 + k * 300, dt)], "#ffffff", 0.25)
    c.drawPath(rrect(dr - 70, 1000, dr - 50, 1120, 8), fill("#c9ccd2"))
    # thanh khí y tế
    c.drawPath(rrect(820, 980, 2880, 1050, 16), fill("#e6ece9"))
    for j, col in enumerate(("#3f8a4a", "#2f6fb0", "#f3c94e", "#ffffff", "#3f8a4a", "#2f6fb0", "#f3c94e")):
        x = 950 + j * 290
        if 1520 < x < 2320:
            continue
        c.drawCircle(x, 1015, 22, fill(col))
        c.drawCircle(x, 1015, 9, fill("#4a5052"))
    # màn hình sinh hiệu
    ml, mt, mr, mb = 1040, 470, 1520, 820
    c.drawLine((ml + mr) / 2, mb, (ml + mr) / 2, 980, stroke("#8a9098", 14))
    c.drawPath(rrect(ml - 26, mt - 26, mr + 26, mb + 26, 26), fill("#8a9098"))
    c.drawPath(rrect(ml, mt, mr, mb, 10), fill("#0c1014"))
    def trace(y0, amp, col, kind):
        p = skia.Path()
        x_ = ml + 20
        p.moveTo(x_, y0)
        while x_ < ml + 300:
            if kind == "ecg":
                p.lineTo(x_ + 30, y0)
                p.lineTo(x_ + 38, y0 - amp)
                p.lineTo(x_ + 46, y0 + amp * 0.5)
                p.lineTo(x_ + 54, y0)
                x_ += 80
                p.lineTo(x_, y0)
            else:
                p.quadTo(x_ + 20, y0 - amp, x_ + 40, y0)
                p.quadTo(x_ + 60, y0 + amp * 0.3, x_ + 80, y0)
                x_ += 80
        c.drawPath(p, stroke(col, 5))
    trace(560, 60, "#3cff7a", "ecg")
    trace(680, 34, "#4fd8ff", "pleth")
    trace(770, 20, "#f3c94e", "pleth")
    text_center(c, "HR 72", 1420, 560, 46, "#3cff7a", "extrabold")
    text_center(c, "SpO2 97", 1420, 670, 34, "#4fd8ff", "bold")
    text_center(c, "BP 118/76", 1420, 770, 30, "#f3c94e", "bold")
    c.drawCircle(mr - 24, mt + 24, 10, fill("#ff3b30"))
    # giường bệnh
    c.drawPath(rrect(1560, 1060, 2280, 1360, 40), fill("#dfe5e4"))
    c.drawPath(rrect(1600, 1100, 2240, 1180, 20), fill("#c9d0cf"))
    path_fill(c, P.plane_y(0.65, -0.55, 0.55, 2.9, 4.9), "#f6f8f8")
    c.drawPath(oval(1920, 1290, 230, 52), fill("#ffffff"))
    c.drawPath(oval(1920, 1300, 230, 52), stroke("#d8e0e0", 4))
    path_fill(c, P.plane_y(0.67, -0.6, 0.6, 2.85, 4.25), "#cfe0ec")
    for j in range(7):
        xa = -0.6 + j * 0.2
        path_fill(c, P.plane_y(0.672, xa, xa + 0.09, 2.85, 4.25), "#6f9ac0")
    path_fill(c, P.face_z(2.85, -0.6, 0.6, 0.32, 0.67), "#b9d0e0")
    for j in range(7):
        xa = -0.6 + j * 0.2
        path_fill(c, P.face_z(2.849, xa, xa + 0.09, 0.32, 0.67), "#5f8ab0")
    for sd in (-1, 1):
        c.drawLine(*P.p(sd * 0.62, 0.85, 3.1), *P.p(sd * 0.62, 0.85, 4.3), stroke("#a9b4b8", 10))
        for zz in (3.2, 3.8, 4.3):
            c.drawLine(*P.p(sd * 0.62, 0.62, zz), *P.p(sd * 0.62, 0.85, zz), stroke("#a9b4b8", 8))
    for sd in (-1, 1):
        for zz in (2.95, 4.7):
            a = P.p(sd * 0.5, 0.3, zz)
            b = P.p(sd * 0.5, 0.06, zz)
            c.drawLine(*a, *b, stroke("#6b7078", 14))
            c.drawCircle(b[0], b[1], 16, fill("#2b2d33"))
    # cột truyền dịch
    ix = 1380
    c.drawLine(ix, 620, ix, 1700, stroke("#a9b0b6", 12))
    c.drawLine(ix - 70, 640, ix + 70, 640, stroke("#a9b0b6", 8))
    c.drawPath(rrect(ix + 20, 660, ix + 110, 840, 26), fill("#e6f2f6", 0.85))
    c.drawRect(_R(ix + 30, 740, ix + 100, 830), fill("#cfe8f0", 0.8))
    p = skia.Path()
    p.moveTo(ix + 65, 840)
    p.cubicTo(ix + 70, 1100, 1700, 1100, 1760, 1300)
    c.drawPath(p, stroke("#e0eef2", 4))
    for dx in (-80, 0, 80):
        c.drawLine(ix, 1700, ix + dx, 1740, stroke("#a9b0b6", 8))
    # máy thở
    vl, vt = 2460, 1060
    c.drawPath(rrect(vl, vt, vl + 320, vt + 560, 24), fill("#e9edec"))
    c.drawPath(rrect(vl + 30, vt + 30, vl + 290, vt + 200, 12), fill("#0c1014"))
    p = skia.Path()
    p.moveTo(vl + 50, vt + 120)
    for j in range(6):
        p.quadTo(vl + 70 + j * 40, vt + 60 + (j % 2) * 120, vl + 90 + j * 40, vt + 120)
    c.drawPath(p, stroke("#f3c94e", 5))
    for j in range(3):
        c.drawCircle(vl + 80 + j * 80, vt + 260, 22, fill("#8a9098"))
    p = skia.Path()
    p.moveTo(vl + 40, vt + 320)
    p.cubicTo(vl - 120, vt + 300, 2260, 1200, 2100, 1250)
    c.drawPath(p, stroke("#b9c8d0", 16))
    for dx in (40, 280):
        c.drawCircle(vl + dx, vt + 590, 26, fill("#2b2d33"))
    # ghế thăm
    ch = "#5f7a8a"
    cx_ = 3150
    c.drawPath(rrect(cx_ - 180, 1360, cx_ + 180, 1640, 30), fill(ch))
    c.drawPath(rrect(cx_ - 220, 1620, cx_ + 220, 1700, 20), fill(shade(ch, 0.12)))
    for dx in (-190, 190):
        c.drawRect(_R(cx_ + dx - 14, 1700, cx_ + dx + 14, 1900), fill(shade(ch, -0.3)))
    lights = [{"x": 1280, "y": 640, "color": "#3cff7a"}]
    if night:
        tint(s, "#4a5a7a", 0.5)
        glow(c, 1280, 640, 520, "#3cff7a", 0.22)
        glow(c, vl + 160, vt + 115, 300, "#f3c94e", 0.15)
        glow(c, 1920, 900, 700, "#dfeef0", 0.2)
        _vignette(c, 0.55)
    else:
        _vignette(c, 0.3)
    mid = s.makeImageSnapshot()
    bed = P.slot(0.0, 4.0, clip_bottom=round(P.p(0, 0.7, 4.0)[1]))
    slots = {"bed": bed, "bedside_left": P.slot(-1.0, 3.5), "bedside_right": P.slot(1.0, 3.4),
             "chair": P.slot(2.4, 2.9), "door": P.slot(-4.4, 4.8), "center": P.slot(0.0, 2.55)}
    signs = [{"text": "ICU 4", "box": [270, 470, 670, 570], "style": "white_board"}]
    return Scene(None, mid, slots=slots, signs=signs, floor_y=slots["center"]["y"], lights=lights,
                 baked_signs=[{"text": "HR 72 / SpO2 97 / BP 118/76", "box": [ml, mt, mr, mb]}])


# =================================================================== 7. chợ có mái che
def scene_cho_co_mai_che(tod: str) -> Scene:
    sf = new_surface()
    c = sf.getCanvas()
    vgrad(c, 0, 0, W, H, ["#c9cfc4", "#a9b0a4"])
    rng = random.Random(23)
    x = -100
    while x < W:
        w_ = rng.uniform(300, 600)
        c.drawRect(_R(x, rng.uniform(250, 500), x + w_, 1300), fill(rng.choice(["#b8b0a0", "#a8b4b0", "#c4bca8"])))
        x += w_
    for _ in range(14):
        ux, uy = rng.uniform(0, W), rng.uniform(720, 900)
        ur = rng.uniform(160, 300)
        p = skia.Path()
        p.addArc(_R(ux - ur, uy - ur * 0.5, ux + ur, uy + ur * 0.5), 180, 180)
        c.drawPath(p, fill(rng.choice(["#c8352e", "#2f6fb0", "#3f8a4a", "#e8b84a", "#e6e2d8"])))
        c.drawLine(ux, uy, ux, uy + 400, stroke("#4a4a48", 8))
    for _ in range(22):
        px_, py_ = rng.uniform(0, W), rng.uniform(1050, 1200)
        col = rng.choice(["#6a5a7a", "#7a6048", "#4a5a6a", "#8a4a4a", "#5a6a4a"])
        c.drawCircle(px_, py_ - 230, 44, fill("#5a4a40"))
        c.drawPath(rrect(px_ - 70, py_ - 190, px_ + 70, py_ + 60, 50), fill(col))
    far = L._blurred(sf.makeImageSnapshot(), 22)

    s = new_surface()
    c = s.getCanvas()
    # mái tôn + kèo thép
    c.drawRect(_R(0, 0, W, 640), fill("#4f564e"))
    x = 0
    while x < W:
        c.drawRect(_R(x, 0, x + 40, 640), fill("#5c6459"))
        x += 90
    for gx in (700, 2100, 3300):
        c.drawRect(_R(gx, 0, gx + 60, 640), fill("#dfe6d8", 0.35))
    c.drawRect(_R(0, 560, W, 600), fill("#2e322c"))
    c.drawRect(_R(0, 120, W, 150), fill("#2e322c"))
    for j in range(25):
        x0 = j * 160
        c.drawLine(x0, 150, x0 + 80, 560, stroke("#2e322c", 14))
        c.drawLine(x0 + 160, 150, x0 + 80, 560, stroke("#2e322c", 14))
    for lx in (500, 1500, 2500, 3400):
        c.drawLine(lx, 600, lx, 720, stroke("#1e201c", 5))
        c.drawPath(poly([(lx - 60, 760), (lx + 60, 760), (lx + 26, 716), (lx - 26, 716)]), fill("#2f6a4a"))
        c.drawCircle(lx, 770, 20, fill("#fff3cf"))
        glow(c, lx, 780, 300, "#ffe7a8", 0.35)
    for x_ in (440, 1540, 2730):
        c.drawRect(_R(x_ - 22, 600, x_ + 22, 1620), fill("#3a3e38"))
    # tủ thuốc (trái)
    c.drawRect(_R(0, 820, 420, 1620), fill("#e9eef0"))
    for j in range(5):
        y = 860 + j * 140
        c.drawRect(_R(20, y + 110, 400, y + 122), fill("#b9c4c8"))
        xx = 30
        while xx < 380:
            ww = rng.uniform(30, 60)
            c.drawRect(_R(xx, y + 110 - rng.uniform(50, 95), xx + ww, y + 110), fill(rng.choice(["#ffffff", "#3a78c2", "#d8423a", "#4fa35a", "#f3c94e"])))
            xx += ww + 6
    c.drawRect(_R(0, 820, 420, 1620), fill("#bfe0f0", 0.18))
    c.drawPath(rrect(110, 680, 310, 800, 16), fill("#ffffff"))
    c.drawRect(_R(190, 695, 230, 785), fill("#2f9a4e"))
    c.drawRect(_R(165, 720, 255, 760), fill("#2f9a4e"))
    # sạp trái cây (mái sọc + chuối treo)
    fl, fr = 480, 1500
    n = 12
    for k in range(n):
        x0 = fl + (fr - fl) * k / n
        x1 = fl + (fr - fl) * (k + 1) / n
        quad(c, [(x0, 720), (x1, 720), (x1 + 8, 860), (x0 + 8, 860)], "#c8352e" if k % 2 == 0 else "#f4efe4")
        c.drawPath(oval((x0 + x1) / 2 + 8, 860, (x1 - x0) / 2, 22), fill("#c8352e" if k % 2 == 0 else "#f4efe4"))
    for bx in (640, 900, 1180, 1400):
        c.drawLine(bx, 880, bx, 960, stroke("#5a4a3a", 5))
        for j in range(7):
            a = -0.9 + j * 0.3
            cx_, cy_ = bx + math.sin(a) * 60, 1010 + math.cos(a) * 40
            c.drawPath(oval(cx_, cy_, 20, 62), fill("#f3c94e"))
            c.drawPath(oval(cx_ + 6, cy_ + 50, 8, 10), fill("#5a4a1a"))
    c.drawRect(_R(fl, 1300, fr, 1340), fill("#8a6a4a"))
    c.drawRect(_R(fl + 20, 1340, fr - 20, 1620), fill("#6b4a32"))
    for (cx0, fruit, fc) in ((520, "o", "#f08a2c"), (780, "o", "#4fa35a"), (1040, "d", "#d84a8a"), (1280, "o", "#f3c94e")):
        c.drawRect(_R(cx0, 1190, cx0 + 220, 1300), fill("#b98e5a"))
        for j in range(3):
            c.drawLine(cx0, 1210 + j * 30, cx0 + 220, 1210 + j * 30, stroke("#8a6a42", 5))
        for j in range(9):
            fx_, fy_ = cx0 + 30 + (j % 5) * 40, 1180 - (j // 5) * 34
            if fruit == "d":
                c.drawPath(oval(fx_, fy_, 26, 32), fill(fc))
                c.drawLine(fx_ - 10, fy_ - 20, fx_ - 20, fy_ - 36, stroke("#4fa35a", 6))
            else:
                c.drawCircle(fx_, fy_, 24, fill(fc))
                c.drawCircle(fx_ - 8, fy_ - 8, 6, fill("#ffffff", 0.4))
    # quầy thịt
    ml, mr = 1600, 2680
    c.drawRect(_R(ml, 760, mr, 790), fill("#8a9098"))
    for j in range(7):
        hx = ml + 90 + j * 150
        c.drawLine(hx, 790, hx, 860, stroke("#6b7078", 6))
        c.drawPath(rrect(hx - 50, 860, hx + 50, 1060 + (j % 3) * 30, 40), fill("#d06a6a"))
        c.drawPath(rrect(hx - 32, 890, hx + 10, 1020, 20), fill("#f0d0c8"))
    c.drawRect(_R(ml - 20, 1240, mr + 20, 1280), fill("#c9d0d4"))
    c.drawRect(_R(ml, 1280, mr, 1620), fill("#f4f6f4"))
    for x_ in range(ml, mr + 1, 90):
        c.drawLine(x_, 1280, x_, 1620, stroke("#d0d6d4", 4))
    for y_ in range(1280, 1620, 90):
        c.drawLine(ml, y_, mr, y_, stroke("#d0d6d4", 4))
    c.drawPath(oval(1900, 1230, 170, 30), fill("#7a5232"))
    c.drawRect(_R(1730, 1180, 2070, 1230), fill("#9a6a42"))
    c.drawPath(oval(1900, 1180, 170, 30), fill("#c99a64"))
    c.drawPath(rrect(1840, 1150, 2000, 1172, 4), fill("#cdd4d8"))
    c.drawPath(rrect(1990, 1152, 2050, 1170, 6), fill("#5a3a22"))
    c.drawRect(_R(2300, 1180, 2520, 1240), fill("#d8423a"))
    c.drawPath(oval(2410, 1180, 120, 22), fill("#c9d0d4"))
    c.drawCircle(2410, 1210, 22, fill("#f4f6f4"))
    for j in range(4):
        c.drawPath(rrect(2140 + j * 34, 1196 - j * 4, 2240 + j * 34, 1238, 18), fill("#d06a6a"))
    # sạp cá
    sl = 2780
    c.drawRect(_R(sl, 1240, W, 1620), fill("#2f6fb0"))
    c.drawRect(_R(sl, 1240, W, 1270), fill("#3a84c8"))
    for j in range(4):
        bx = sl + 60 + j * 260
        c.drawRect(_R(bx, 1130, bx + 220, 1250), fill("#f4f6f8"))
        c.drawRect(_R(bx + 12, 1120, bx + 208, 1150), fill("#cfe6f0"))
        for k in range(3):
            fx_ = bx + 50 + k * 60
            c.drawPath(oval(fx_, 1122, 26, 12), fill("#8a98a8"))
            quad(c, [(fx_ + 24, 1122), (fx_ + 46, 1108), (fx_ + 46, 1136)], "#7a8898")
    # sàn bê tông ướt
    vgrad(c, 0, 1620, W, H, ["#6a7068", "#7d847c"])
    c.drawRect(_R(0, 1620, W, 1640), fill("#4a4e48"))
    for (px_, py_, rx) in ((900, 1820, 300), (2300, 1960, 420), (3300, 1760, 220)):
        c.drawPath(oval(px_, py_, rx, rx * 0.14), fill("#9aa8b0", 0.5))
        c.drawPath(oval(px_ + rx * 0.2, py_, rx * 0.4, rx * 0.03), fill("#ffffff", 0.4))
    for _ in range(8):
        px_, py_ = rng.uniform(0, W), rng.uniform(1700, 2100)
        c.drawPath(oval(px_, py_, rng.uniform(20, 50), rng.uniform(8, 16)), fill("#3a6a3a", 0.6))
    tint(s, "#e8f0e0", 0.06)
    _vignette(c, 0.3)
    mid = s.makeImageSnapshot()
    slots = {"vendor_meat": {**frac_slot({"x": 0.555, "y": 0.725, "scale": 0.86}), "clip_bottom": 1250},
             "vendor_fruit": {**frac_slot({"x": 0.25, "y": 0.725, "scale": 0.86}), "clip_bottom": 1310},
             "vendor_fish": {**frac_slot({"x": 0.86, "y": 0.725, "scale": 0.86}), "clip_bottom": 1250},
             "center": frac_slot({"x": 0.50, "y": 0.92, "scale": 1.05}),
             "left": frac_slot({"x": 0.25, "y": 0.92, "scale": 1.05}),
             "right": frac_slot({"x": 0.78, "y": 0.92, "scale": 1.05})}
    signs = [{"text": "PHARMACY", "box": [10, 600, 410, 670], "style": "white_board"},
             {"text": "FRUIT", "box": [820, 620, 1160, 710], "style": "white_board"},
             {"text": "FRESH MEAT", "box": [1850, 640, 2430, 740], "style": "red_board"},
             {"text": "FISH", "box": [3100, 640, 3500, 740], "style": "white_board"}]
    return Scene(far, mid, slots=slots, signs=signs, floor_y=slots["center"]["y"], parallax=(0.9, 1.0, 1.15))


# =================================================================== 8. phòng điều tra (bảng ghim dây đỏ)
def scene_phong_dieu_tra(tod: str) -> Scene:
    night = tod == "night"
    s = new_surface()
    c = s.getCanvas()
    P = _room_shell(c, "#d9c8a8", "#8a7d6c", "#837664", back_y=1450, pattern=False)
    rng = random.Random(44)
    for _ in range(8):
        x, y = rng.uniform(0, W), rng.uniform(200, 1300)
        c.drawPath(oval(x, y, rng.uniform(80, 240), rng.uniform(60, 180)), fill("#7a6a50", rng.uniform(0.04, 0.08)))
    # bảng gỗ bần
    bl, bt, br, bb = 820, 260, 2760, 1120
    c.drawRect(_R(bl + 14, bt + 18, br + 14, bb + 18), fill("#000000", 0.2))
    c.drawRect(_R(bl, bt, br, bb), fill("#6b4a32"))
    c.drawRect(_R(bl + 30, bt + 30, br - 30, bb - 30), fill("#b98a58"))
    for _ in range(900):
        c.drawCircle(rng.uniform(bl + 34, br - 34), rng.uniform(bt + 34, bb - 34), rng.uniform(1.5, 4), fill("#8a6038", 0.5))
    pins = []
    for (x, y, rot) in ((900, 330, -4), (1150, 360, 3), (1400, 320, -2), (900, 720, 2), (1160, 760, -5), (2420, 360, 4), (2440, 740, -3)):
        pins.append(_missing_card(c, x, y, 200, 270, rot, rng))
    mx0, my0, mx1, my1 = 1700, 380, 2300, 820
    c.drawRect(_R(mx0, my0, mx1, my1), fill("#e8e4c8"))
    for j in range(6):
        c.drawLine(mx0 + rng.uniform(0, 600), my0, mx0 + rng.uniform(0, 600), my1, stroke("#ffffff", 10))
        c.drawLine(mx0, my0 + rng.uniform(0, 440), mx1, my0 + rng.uniform(0, 440), stroke("#ffffff", 8))
    p = skia.Path()
    p.moveTo(mx0, my0 + 300)
    p.cubicTo(mx0 + 200, my0 + 200, mx0 + 380, my0 + 420, mx1, my0 + 260)
    c.drawPath(p, stroke("#8ab8d8", 26))
    c.drawPath(rrect(mx0 + 120, my0 + 60, mx0 + 260, my0 + 160, 4), fill("#c9d8a8"))
    c.drawCircle(mx0 + 330, my0 + 180, 90, stroke("#c8202a", 7))
    for j in range(5):
        c.drawCircle(mx0 + 280 + j * 22, my0 + 150 + (j % 2) * 40, 9, fill("#c8202a"))
    pins.append((mx0 + 330, my0 + 30))
    c.drawCircle(mx0 + 330, my0 + 30, 11, fill("#2f6fb0"))
    # polaroid + biên lai + giấy note
    c.save()
    c.rotate(6, 1560, 960)
    c.drawRect(_R(1460, 860, 1660, 1070), fill("#f6f4ee"))
    c.drawRect(_R(1480, 880, 1640, 1020), fill("#7a8a9a"))
    c.drawCircle(1560, 940, 30, fill("#4a5a6a"))
    c.restore()
    pins.append((1560, 870))
    for (x, y, w_, h_) in ((1780, 880, 90, 200), (1900, 900, 80, 170), (2600, 900, 90, 160)):
        c.drawRect(_R(x, y, x + w_, y + h_), fill("#fbfaf4"))
        for j in range(5):
            c.drawLine(x + 10, y + 30 + j * 26, x + w_ - 14, y + 30 + j * 26, stroke("#a8a8a0", 3))
        c.drawCircle(x + w_ / 2, y + 12, 8, fill("#f3c94e"))
    for (x, y, col, rot) in ((2120, 900, "#f3e36a", 5), (2240, 960, "#f4a8c0", -6), (2000, 1000, "#a8d8f0", 3),
                             (1350, 1020, "#f3e36a", -4), (2560, 600, "#f4a8c0", 7)):
        c.save()
        c.rotate(rot, x + 50, y + 50)
        c.drawRect(_R(x, y, x + 100, y + 100), fill(col))
        c.drawLine(x + 14, y + 40, x + 80, y + 40, stroke("#6a6a6a", 3, 0.6))
        c.drawLine(x + 14, y + 62, x + 70, y + 62, stroke("#6a6a6a", 3, 0.6))
        c.restore()
    order = [0, 3, 1, 7, 4, 8, 2, 5, 6]
    pts = [pins[i] for i in order if i < len(pins)]
    for (a, b) in zip(pts, pts[1:]):
        sag_wire(c, a[0], a[1], b[0], b[1], 6, "#c8202a", 5)
    for (x, y) in pts:
        c.drawCircle(x, y, 10, fill("#e02a2a"))
    # bàn chân chữ A + laptop + đèn kiến trúc
    tl, tr, tt = 2560, 3560, 1270
    c.drawRect(_R(tl, tt, tr, tt + 34), fill("#c9b48a"))
    for x0 in (tl + 80, tr - 80):
        c.drawLine(x0 - 70, tt + 34, x0 + 50, 1720, stroke("#5a5048", 18))
        c.drawLine(x0 + 70, tt + 34, x0 - 50, 1720, stroke("#5a5048", 18))
    c.drawPath(rrect(2780, 1040, 3160, 1270, 14), fill("#2b2d33"))
    c.drawPath(rrect(2800, 1060, 3140, 1250, 8), fill("#4a7ab0" if not night else "#7ab0e0"))
    quad(c, [(2740, 1270), (3200, 1270), (3240, 1296), (2700, 1296)], "#3a3d44")
    c.drawPath(oval(3400, 1268, 80, 16), fill("#2b2d33"))
    c.drawLine(3400, 1260, 3330, 1010, stroke("#2b2d33", 12))
    c.drawLine(3330, 1010, 3240, 1100, stroke("#2b2d33", 12))
    c.drawPath(poly([(3200, 1080), (3290, 1080), (3330, 1170), (3160, 1170)]), fill("#c8352e"))
    for j in range(5):
        c.drawRect(_R(2600 + j * 6, 1250 - j * 12, 2740 - j * 6, 1262 - j * 12), fill("#f4f1e8"))
    # nệm sàn, ghế đỏ, thùng giấy
    c.drawPath(rrect(80, 1500, 900, 1640, 30), fill("#d8d4c8"))
    c.drawPath(rrect(300, 1480, 900, 1620, 30), fill("#6a7a9a"))
    c.drawPath(oval(200, 1520, 110, 40), fill("#f4f1e8"))
    _plastic_stool(c, 1250, 1840, 320)
    _carton(c, 3000, 1840, 420, 300, "#c49a64")
    _carton(c, 3080, 1540, 300, 200, "#b98e5a")
    lights = [{"x": 3245, "y": 1170, "color": "#ffd98a"}]
    if night:
        tint(s, "#5a5070", 0.55)
        ellipse_glow(c, 3245, 1270, 520, 160, "#ffd98a", 0.55)
        glow(c, 3245, 1180, 900, "#ffcf8a", 0.28)
        glow(c, 2970, 1150, 380, "#9fd0ff", 0.3)
        glow(c, 1790, 690, 1200, "#ffe2b0", 0.12)
        _vignette(c, 0.55)
    else:
        _vignette(c, 0.3)
    mid = s.makeImageSnapshot()
    slots = {"center": P.slot(0.0, 3.3), "board": P.slot(-1.2, 3.6), "desk": P.slot(2.3, 3.6),
             "left": P.slot(-2.0, 3.0), "right": P.slot(1.6, 3.0)}
    return Scene(None, mid, slots=slots, floor_y=slots["center"]["y"], lights=lights)


# =================================================================== 9. bến gỗ, nhà sàn ven sông (đêm)
def scene_ben_go_nha_san_dem(tod: str) -> Scene:
    HZ = 1150
    sf = new_surface()
    c = sf.getCanvas()
    vgrad(c, 0, 0, W, HZ, ["#1c1830", "#2a2440", "#4a3a5a"], [0, 0.55, 1])
    stars(c, 0, 0, W, 700, 240, seed=77)
    c.drawCircle(900, 260, 70, fill("#f1ead2"))
    glow(c, 900, 260, 260, "#f1ead2", 0.4)
    sil = "#15121f"
    # cây tròn lớn + dừa
    c.drawPath(oval(2250, 760, 520, 230), fill("#1a1626"))
    c.drawRect(_R(2230, 760, 2270, HZ), fill("#1a1626"))
    def coconut(x, base, h, lean):
        p = skia.Path()
        p.moveTo(x, base)
        p.quadTo(x + lean * 0.4, base - h * 0.6, x + lean, base - h)
        c.drawPath(p, stroke(sil, 20))
        tx, ty = x + lean, base - h
        for j in range(8):
            a = math.pi * (0.05 + 0.9 * j / 7)
            q = skia.Path()
            q.moveTo(tx, ty)
            q.quadTo(tx + math.cos(a) * 160, ty - math.sin(a) * 120, tx + math.cos(a) * 260, ty - math.sin(a) * 40 + 60)
            c.drawPath(q, stroke(sil, 16))
    for (x, h, lean) in ((300, 620, 60), (1350, 700, -50), (1700, 560, 40), (2700, 640, -30)):
        coconut(x, HZ - 120, h, lean)
    # dãy nhà sàn
    rng = random.Random(15)
    lits = []
    x = -60
    while x < 2900:
        w_ = rng.uniform(300, 520)
        hh = rng.uniform(220, 360)
        bot = HZ - rng.uniform(70, 110)
        top = bot - hh
        col = rng.choice(["#15121f", "#1b1728", "#120f1a"])
        c.drawRect(_R(x, top, x + w_, bot), fill(col))
        if rng.random() < 0.5:
            c.drawPath(poly([(x - 30, top), (x + w_ + 30, top), (x + w_ / 2, top - hh * 0.45)]), fill(col))
        else:
            c.drawPath(poly([(x - 30, top + 20), (x + w_ + 30, top - 60), (x + w_ + 30, top), (x - 30, top + 40)]), fill(col))
        for px_ in range(int(x + 20), int(x + w_), 90):
            c.drawRect(_R(px_, bot, px_ + 12, HZ + 20), fill(col))
        for _ in range(rng.randint(0, 2)):
            wx = rng.uniform(x + 30, x + w_ - 110)
            wy = rng.uniform(top + 40, bot - 110)
            c.drawRect(_R(wx, wy, wx + 80, wy + 70), fill("#f0b860"))
            c.drawLine(wx + 40, wy, wx + 40, wy + 70, stroke(col, 6))
            lits.append((wx + 40, wy + 35))
            glow(c, wx + 40, wy + 35, 160, "#f0b860", 0.3)
        x += w_ + rng.uniform(10, 60)
    # nước sông
    vgrad(c, 0, HZ, W, H, ["#221d38", "#120f22"])
    for (lx, ly) in lits:
        for j in range(6):
            y = HZ + 30 + j * 34
            hw = 40 - j * 4 + rng.uniform(-8, 8)
            c.drawRect(_R(lx - hw, y, lx + hw, y + 7), fill("#f0b860", 0.4 - j * 0.05))
    # cầu đi bộ trên cao bên phải + đèn natri
    c.drawRect(_R(2800, 880, W, 930), fill("#24203a"))
    for px_ in range(2840, W, 220):
        c.drawRect(_R(px_, 930, px_ + 24, HZ + 30), fill("#24203a"))
    c.drawLine(2800, 820, W, 820, stroke("#24203a", 10))
    for px_ in range(2820, W, 70):
        c.drawLine(px_, 820, px_, 880, stroke("#24203a", 6))
    c.drawRect(_R(3290, 480, 3310, 880), fill("#24203a"))
    c.drawLine(3300, 490, 3200, 470, stroke("#24203a", 10))
    c.drawPath(rrect(3150, 462, 3230, 486, 8), fill("#3a3448"))
    glow(c, 3190, 490, 600, "#f0b860", 0.45)
    glow(c, 3190, 490, 120, "#ffe0a0", 0.9)
    for j in range(16):
        y = HZ + 30 + j * 30
        hw = 120 - j * 5 + rng.uniform(-20, 20)
        c.drawRect(_R(3190 - hw, y, 3190 + hw, y + 8), fill("#f0b860", 0.5 - j * 0.028))
    far = sf.makeImageSnapshot()

    s = new_surface()
    c = s.getCanvas()
    # bờ kè bê tông nứt (trái)
    path_fill(c, poly([(-20, 1520), (980, 1540), (1040, H + 10), (-20, H + 10)]), "#3a3c4a")
    c.drawRect(_R(-20, 1500, 990, 1545), fill("#4a4c5c"))
    for _ in range(7):
        x0, y0 = rng.uniform(40, 900), rng.uniform(1560, 2100)
        p = skia.Path()
        p.moveTo(x0, y0)
        for j in range(4):
            x0 += rng.uniform(-60, 60)
            y0 += rng.uniform(20, 70)
            p.lineTo(x0, y0)
        c.drawPath(p, stroke("#25262f", 5))
    # cầu tàu gỗ
    PL, PT, PF = 960, 1600, 1760
    for px_ in range(PL + 60, W, 300):
        c.drawRect(_R(px_ - 16, PF, px_ + 16, H), fill("#1e1812"))
    quad(c, [(PL, PF), (W + 20, PF), (W + 20, PT), (PL + 40, PT)], "#5a4230")
    yy, step = PT, 22
    while yy < PF:
        c.drawLine(PL + 40 * (1 - (yy - PT) / (PF - PT)), yy, W, yy, stroke("#3e2e22", 4))
        yy += step
        step *= 1.12
    for px_ in range(PL + 140, W, 230):
        c.drawLine(px_, PT, px_ - 10, PF, stroke("#3e2e22", 5))
    c.drawRect(_R(1660, PT + 40, 1820, PT + 70), fill("#120f22"))
    c.drawRect(_R(PL, PF, W, PF + 40), fill("#2e2218"))
    c.drawPath(oval(2700, PT + 60, 90, 26), stroke("#b8a878", 12))
    c.drawPath(oval(2700, PT + 60, 55, 15), stroke("#a89868", 10))
    c.drawPath(rrect(3460, PT - 90, 3520, PT + 50, 14), fill("#2a2030"))
    c.drawPath(oval(3490, PT - 90, 34, 10), fill("#3a3040"))
    c.drawRect(_R(0, 1500, W, H), fill("#5a5a9a", 0.0))
    tint(s, "#8a86b8", 0.55)
    ellipse_glow(c, 3000, PT + 60, 900, 120, "#f0b860", 0.22)
    mid = s.makeImageSnapshot()
    slots = {"center": frac_slot({"x": 0.55, "y": 0.79, "scale": 0.95}),
             "left": frac_slot({"x": 0.36, "y": 0.79, "scale": 0.95}),
             "right": frac_slot({"x": 0.75, "y": 0.79, "scale": 0.95}),
             "embankment": frac_slot({"x": 0.13, "y": 0.86, "scale": 1.05})}
    return Scene(far, mid, slots=slots, floor_y=slots["center"]["y"], parallax=(0.85, 1.0, 1.15),
                 lights=[{"x": 3190, "y": 490, "color": "#f0b860"}])


# =================================================================== 10. tiệm tạp hoá nhỏ (mặt tiền)
def scene_tiem_tap_hoa_nho(tod: str) -> Scene:
    night = tod != "day"
    s = new_surface()
    c = s.getCanvas()
    rng = random.Random(52)
    c.drawRect(_R(0, 0, W, 1560), fill("#d9cdb4"))
    for (l, r, col) in ((0, 900, "#c9b8a0"), (2940, W, "#b8c4b8")):
        c.drawRect(_R(l, 0, r, 1560), fill(col))
        for wx in (l + 140, l + 520):
            if wx + 260 < r:
                c.drawRect(_R(wx, 180, wx + 260, 480), fill("#3a3e48" if night else "#8a9aaa"))
                c.drawRect(_R(wx - 14, 480, wx + 274, 500), fill(shade(col, 0.12)))
        _shutter(c, l + 60, 760, r - 60, 1560, "#8e9298")
    c.drawRect(_R(900, 0, 920, 1560), fill("#9a8e78"))
    c.drawRect(_R(2920, 0, 2940, 1560), fill("#9a8e78"))
    c.drawRect(_R(960, 280, 2880, 540), fill("#5a4a3a"))
    # mái hiên nan xanh
    n = 18
    for k in range(n):
        x0 = 940 + (1960) * k / n
        x1 = 940 + (1960) * (k + 1) / n
        quad(c, [(x0, 560), (x1, 560), (x1 + (x1 - 1920) * 0.06, 720), (x0 + (x0 - 1920) * 0.06, 720)],
             "#2f7a5a" if k % 2 == 0 else "#3f9a6e")
    c.drawRect(_R(880, 718, 2960, 740), fill("#245a44"))
    # bên trong
    il, ir, it, ib = 980, 2860, 760, 1560
    c.drawRect(_R(il, it, ir, ib), fill("#e8dcc0"))
    for j in range(5):
        y = 860 + j * 130
        c.drawRect(_R(il + 20, y + 100, 2300, y + 112), fill("#8a6a4a"))
        xx = il + 30
        while xx < 2280:
            ww = rng.uniform(40, 90)
            if rng.random() < 0.3:
                c.drawPath(rrect(xx, y + 30, xx + ww * 0.7, y + 100, 12), fill("#e6efe8", 0.85))
                c.drawRect(_R(xx, y + 22, xx + ww * 0.7, y + 40), fill(rng.choice(["#d8423a", "#e8b84a", "#3a78c2"])))
                xx += ww * 0.7 + 8
            else:
                c.drawRect(_R(xx, y + 100 - rng.uniform(50, 95), xx + ww, y + 100), fill(rng.choice(L.PRODUCTS[:-1])))
                xx += ww + 6
    fl, fr, ft = 2360, 2820, 820
    c.drawRect(_R(fl - 16, ft - 16, fr + 16, ib), fill("#d8dcd8"))
    c.drawRect(_R(fl, ft + 50, fr, ib - 40), fill("#cfe6ee"))
    _bottle_rows(c, fl + 10, ft + 60, fr - 10, ib - 50, seed=9, rows=5)
    c.drawRect(_R(fl, ft, fr, ft + 50), fill("#d8423a"))
    c.drawRect(_R(fl, ft + 50, fr, ib - 40), fill("#ffffff", 0.18))
    c.drawPath(rrect(1020, 1250, 1720, 1560, 10), fill("#2f6a52"))
    c.drawRect(_R(1000, 1230, 1740, 1262), fill("#d9e6ea"))
    c.drawPath(rrect(1420, 1090, 1640, 1230, 10), fill("#2b2d33"))
    c.drawPath(rrect(1436, 1104, 1624, 1210, 6), fill("#4a7ab0" if night else "#41505a"))
    c.drawRect(_R(1100, 1170, 1300, 1230), fill("#3a3d44"))
    for j in range(3):
        c.drawPath(rrect(1060 + j * 90, 1300, 1130 + j * 90, 1420, 20), fill("#f4f1e8", 0.9))
    for bx in (1200, 1700, 2200):
        _bulb(c, bx, it, it + 70, lit=night, r=22)
    for hx in (1050, 2790):
        c.drawLine(hx, 740, hx, 860, stroke("#4a3a2a", 4))
        c.drawPath(oval(hx, 890, 70, 34), fill("#8a5a3a"))
        for j in range(7):
            a = math.pi * (0.1 + 0.8 * j / 6)
            c.drawPath(oval(hx + math.cos(a) * 70, 870 - math.sin(a) * 30 + 40, 26, 50), fill("#4f9a4a" if j % 2 else "#3f7a3a"))
    # vỉa hè + bậc
    c.drawRect(_R(0, 1560, W, 1600), fill("#8a8478"))
    vgrad(c, 0, 1600, W, H, ["#b4ada0", "#a49d90"])
    for x in range(-2000, W + 2000, 240):
        c.drawLine(1920 + (x - 1920) * 0.6, 1600, x, H, stroke("#948d80", 4))
    for y in (1680, 1800, 1960):
        c.drawLine(0, y, W, y, stroke("#948d80", 4))
    _plastic_stool(c, 640, 1880, 300, "#2f6fb0")
    _plastic_stool(c, 3240, 1860, 280)
    lights = []
    if night:
        tint(s, "#45507a", 0.6)
        glow(c, 1920, 1160, 1200, "#ffcf7a", 0.3)
        for bx in (1200, 1700, 2200):
            glow(c, bx, it + 115, 360, "#ffd98a", 0.5)
            glow(c, bx, it + 115, 60, "#fff6dc", 0.9)
            lights.append({"x": bx, "y": it + 115, "color": "#ffd98a"})
        glow(c, 2590, 1180, 420, "#cfeaff", 0.28)
        ellipse_glow(c, 1920, 1640, 1300, 140, "#ffcf7a", 0.4)
        _vignette(c, 0.45)
    else:
        _vignette(c, 0.25)
    mid = s.makeImageSnapshot()
    slots = {"clerk": {**frac_slot({"x": 0.36, "y": 0.72, "scale": 0.8}), "clip_bottom": 1240},
             "doorway": frac_slot({"x": 0.52, "y": 0.72, "scale": 0.8}),
             "center": frac_slot({"x": 0.50, "y": 0.92, "scale": 1.0}),
             "left": frac_slot({"x": 0.22, "y": 0.92, "scale": 1.0}),
             "right": frac_slot({"x": 0.80, "y": 0.92, "scale": 1.0})}
    signs = [{"text": "CORNER SNACKS", "box": [990, 300, 2850, 520], "style": "white_board"}]
    return Scene(None, mid, slots=slots, signs=signs, floor_y=slots["center"]["y"], lights=lights)


# =================================================================== 11. mặt tiền toà án
def scene_toa_an_mat_tien(tod: str) -> Scene:
    sf = new_surface()
    c = sf.getCanvas()
    L._day_sky(c, 0, 1500, top="#7fb0e0", bottom="#d8e8f2")
    far = sf.makeImageSnapshot()
    s = new_surface()
    c = s.getCanvas()
    round_tree(c, 160, 1300, 320, "#4f8a4a", "#5a4030", seed=3)
    round_tree(c, 3700, 1300, 320, "#4f8a4a", "#5a4030", seed=4)
    # mái ngói cam
    roof = "#d8743a"
    p = poly([(360, 560), (3480, 560), (3150, 270), (690, 270)])
    path_fill(c, p, roof)
    c.save()
    c.clipPath(p, skia.ClipOp.kIntersect, True)
    for y in range(290, 560, 34):
        c.drawLine(0, y, W, y, stroke(shade(roof, -0.15), 6))
    for x in range(300, 3600, 60):
        c.drawLine(x, 270, x + (x - 1920) * 0.05, 560, stroke(shade(roof, -0.08), 3))
    c.restore()
    g = poly([(1260, 400), (2580, 400), (1920, 70)])
    path_fill(c, g, shade(roof, 0.08))
    path_fill(c, poly([(1380, 380), (2460, 380), (1920, 120)]), "#efe2c8")
    c.drawCircle(1920, 280, 60, stroke("#c99a3c", 10))
    c.drawLine(1260, 400, 1920, 70, stroke(shade(roof, -0.3), 16))
    c.drawLine(2580, 400, 1920, 70, stroke(shade(roof, -0.3), 16))
    c.drawRect(_R(330, 556, 3510, 580), fill("#b85a2a"))
    # dải xanh than gắn biển
    c.drawRect(_R(360, 580, 3480, 720), fill("#1f2a4a"))
    c.drawLine(360, 590, 3480, 590, stroke("#c99a3c", 5))
    c.drawLine(360, 710, 3480, 710, stroke("#c99a3c", 5))
    # hàng cột + cửa vòm
    c.drawRect(_R(380, 720, 3460, 1380), fill("#d8cba8"))
    c.drawRect(_R(380, 720, 3460, 780), fill("#e6dcc0"))
    cols_x = [460 + i * (2920 / 11) for i in range(12)]
    for i in range(11):
        a, b = cols_x[i] + 60, cols_x[i + 1] - 60
        mx_ = (a + b) / 2
        hw = (b - a) * 0.32
        p = skia.Path()
        p.moveTo(mx_ - hw, 1340)
        p.lineTo(mx_ - hw, 960)
        p.arcTo(_R(mx_ - hw, 960 - hw, mx_ + hw, 960 + hw), 180, 180, False)
        p.lineTo(mx_ + hw, 1340)
        p.close()
        path_fill(c, p, "#2f3442")
        c.drawLine(mx_, 900, mx_, 1340, stroke("#3e4454", 6))
    for x in cols_x:
        c.drawRect(_R(x - 54, 800, x + 54, 1380), fill("#f2eadb"))
        c.drawRect(_R(x + 18, 800, x + 54, 1380), fill("#d8ccb4"))
        for fx in (-30, -6):
            c.drawLine(x + fx, 820, x + fx, 1360, stroke("#e2d8c4", 4))
        c.drawRect(_R(x - 72, 780, x + 72, 812), fill("#e8dfcc"))
        c.drawRect(_R(x - 72, 1360, x + 72, 1392), fill("#e8dfcc"))
    for bx in (cols_x[5], cols_x[6]):
        c.drawRect(_R(bx - 40, 820, bx + 40, 1200), fill("#7a2a2a"))
        quad(c, [(bx - 40, 1200), (bx + 40, 1200), (bx, 1240)], "#7a2a2a")
    c.drawRect(_R(330, 1380, 3510, 1440), fill("#c9bc9c"))
    # bậc thềm rộng
    for j in range(8):
        t = 1440 + j * 46
        half = 1500 + j * 120
        c.drawRect(_R(1920 - half, t, 1920 + half, t + 46), fill("#e2d9c6" if j % 2 == 0 else "#d4cab4"))
        c.drawLine(1920 - half, t, 1920 + half, t, stroke("#b8ae98", 4))
    vgrad(c, 0, 1808, W, H, ["#cfc6b4", "#bdb4a0"])
    for x in range(-2000, W + 2000, 300):
        c.drawLine(1920 + (x - 1920) * 0.5, 1808, x, H, stroke("#aaa290", 4))
    for (bx, by) in ((520, 1810), (3320, 1810)):
        c.drawPath(rrect(bx - 120, by - 120, bx + 120, by, 20), fill("#a9a08a"))
        c.drawPath(oval(bx, by - 120, 140, 40), fill("#4f8a4a"))
    glow(c, 2600, 400, 1600, "#fff6dc", 0.15)
    mid = s.makeImageSnapshot()
    slots = {"center": frac_slot({"x": 0.50, "y": 0.90, "scale": 0.8}),
             "left": frac_slot({"x": 0.30, "y": 0.90, "scale": 0.8}),
             "right": frac_slot({"x": 0.70, "y": 0.90, "scale": 0.8}),
             "top_steps": frac_slot({"x": 0.50, "y": 0.67, "scale": 0.45})}
    signs = [{"text": "CRIMINAL COURT", "box": [1060, 600, 2780, 700], "style": "plain"}]
    return Scene(far, mid, slots=slots, signs=signs, floor_y=slots["center"]["y"], parallax=(0.9, 1.0, 1.1))


# =================================================================== 12. phòng trọ trống có vali
def scene_phong_tro_vali(tod: str) -> Scene:
    night = tod == "night"
    s = new_surface()
    c = s.getCanvas()
    P = _room_shell(c, "#b8ab98", "#9a8b76", "#928370", back_y=1450, pattern=False)
    rng = random.Random(61)
    for _ in range(10):
        x, y = rng.uniform(0, W), rng.uniform(200, 1300)
        c.drawPath(oval(x, y, rng.uniform(80, 260), rng.uniform(60, 200)), fill("#6a5e48", rng.uniform(0.04, 0.09)))
    # cửa gỗ
    dl, dr, dt = 240, 690, 820
    c.drawRect(_R(dl - 30, dt - 30, dr + 30, 1450), fill("#6a5a48"))
    c.drawRect(_R(dl, dt, dr, 1450), fill("#8a6a4a"))
    for (pt, pb) in ((870, 1100), (1150, 1400)):
        c.drawRect(_R(dl + 50, pt, dr - 50, pb), stroke(shade("#8a6a4a", -0.25), 8))
    c.drawCircle(dr - 60, 1140, 16, fill("#c9ccd2"))
    # cửa sổ mở thấy nhà đối diện
    wl, wt, wr, wb = 2560, 520, 3260, 1080
    vgrad(c, wl, wt, wr, wb, ["#cfe0ea", "#eef2f4"] if not night else ["#0d1426", "#1d2742"])
    c.drawRect(_R(wl, wt + 120, wr, wb), fill("#d8cbb0" if not night else "#2a2c3a"))
    for j in range(3):
        for k in range(3):
            c.drawRect(_R(wl + 40 + k * 230, wt + 170 + j * 140, wl + 150 + k * 230, wt + 260 + j * 140),
                       fill("#7a8a9a" if not night else ("#f2c46b" if (j + k) % 3 == 0 else "#1a1c22")))
    c.drawRect(_R(wl, wt, wr, wb), stroke("#e8e0d0", 22))
    quad(c, [(wl, wt), (wl - 170, wt + 60), (wl - 170, wb + 40), (wl, wb)], "#e8e0d0")
    quad(c, [(wl - 20, wt + 20), (wl - 150, wt + 70), (wl - 150, wb + 20), (wl - 20, wb - 20)], "#a9c4d4", 0.7)
    c.drawRect(_R(wl - 40, wb, wr + 40, wb + 30), fill("#d8d0c0"))
    # bóng đèn treo + giấy ghim
    _bulb(c, 1750, 0, 360, lit=True, r=26)
    for (x, y, rot) in ((1240, 640, -4), (1420, 610, 3), (1590, 660, -2), (1330, 820, 5)):
        c.save()
        c.rotate(rot, x + 70, y + 90)
        c.drawRect(_R(x, y, x + 140, y + 180), fill("#f4f1e8"))
        for j in range(5):
            c.drawLine(x + 16, y + 30 + j * 28, x + 120 - (j % 2) * 30, y + 30 + j * 28, stroke("#8a8a8a", 4))
        c.restore()
        c.drawCircle(x + 70, y + 10, 8, fill("#d0302a"))
    # bàn gấp + quạt đứng + nệm sàn
    c.drawRect(_R(1200, 1200, 1900, 1226), fill("#c9b48a"))
    c.drawLine(1260, 1226, 1840, 1440, stroke("#5a5048", 12))
    c.drawLine(1840, 1226, 1260, 1440, stroke("#5a5048", 12))
    c.drawRect(_R(1300, 1176, 1480, 1200), fill("#f4f1e8"))
    fx_, fb = 2200, 1450
    c.drawPath(oval(fx_, fb, 110, 22), fill("#2b2d33"))
    c.drawRect(_R(fx_ - 9, 1150, fx_ + 9, fb), fill("#c9ccd2"))
    c.drawCircle(fx_, 1080, 130, stroke("#c9ccd2", 9))
    for k in range(3):
        a = k / 3 * math.tau + 0.3
        c.drawPath(oval(fx_ + math.cos(a) * 60, 1080 + math.sin(a) * 60, 54, 30), fill("#7ab0d8", 0.85))
    c.drawCircle(fx_, 1080, 22, fill("#3a78c2"))
    c.drawPath(rrect(760, 1390, 1180, 1470, 20), fill("#e0d8c8"))
    c.drawPath(rrect(900, 1380, 1180, 1460, 20), fill("#9ab0c8"))
    _carton(c, 860, 1640, 300, 220, "#c49a64")
    _carton(c, 900, 1420, 220, 150, "#b98e5a")
    # vali (tiền cảnh)
    _suitcase(c, 2620, 1800, 300, 430, "#e88aa8")
    _suitcase(c, 3000, 1830, 330, 480, "#7ab0d8")
    _suitcase(c, 3380, 1790, 280, 400, "#f3c94e", tag="#e88aa8")
    for (x, w_) in ((2620, 300), (3000, 330), (3380, 280)):
        c.drawPath(oval(x, 1810, w_ * 0.6, 26), fill("#000000", 0.15))
    if night:
        tint(s, "#46506e", 0.6)
        glow(c, 1750, 412, 900, "#ffd98a", 0.35)
        glow(c, 1750, 412, 90, "#fff6dc", 0.9)
        _vignette(c, 0.5)
    else:
        path_fill(c, poly([(wl, wb), (wr, wb), (wr + 420, 1900), (wl + 120, 1900)]), "#fff6dc", 0.16)
        glow(c, 2900, 800, 1100, "#fff6dc", 0.22)
        _vignette(c, 0.3)
    mid = s.makeImageSnapshot()
    slots = {"center": P.slot(0.0, 3.3), "left": P.slot(-2.0, 3.3), "door": P.slot(-4.5, 4.7),
             "suitcases": P.slot(1.2, 3.6), "right": P.slot(1.2, 3.6)}
    return Scene(None, mid, slots=slots, floor_y=slots["center"]["y"], lights=[{"x": 1750, "y": 412, "color": "#ffd98a"}])


# =================================================================== đăng ký
SCENES = {
    "bep_nha_hang": scene_bep_nha_hang,
    "kho_lanh_ben_trong": scene_kho_lanh_ben_trong,
    "san_thuong_binh_minh": scene_san_thuong_binh_minh,
    "pho_nha_ong_hem": scene_pho_nha_ong_hem,
    "phong_truong_cong_an": scene_phong_truong_cong_an,
    "phong_icu": scene_phong_icu,
    "cho_co_mai_che": scene_cho_co_mai_che,
    "phong_dieu_tra": scene_phong_dieu_tra,
    "ben_go_nha_san_dem": scene_ben_go_nha_san_dem,
    "tiem_tap_hoa_nho": scene_tiem_tap_hoa_nho,
    "toa_an_mat_tien": scene_toa_an_mat_tien,
    "phong_tro_vali": scene_phong_tro_vali,
}

TAGS = {
    "bep_nha_hang": ["bếp", "bếp nhà hàng", "kitchen", "kho lạnh", "dao", "inox", "thớt", "restaurant kitchen"],
    "kho_lanh_ben_trong": ["kho lạnh", "tủ đông", "cold room", "freezer", "đồ để lại", "mũ bảo hiểm", "túi xách", "băng giá"],
    "san_thuong_binh_minh": ["sân thượng", "rooftop", "bình minh", "dawn", "dây phơi", "bồn nước", "thành phố", "skyline"],
    "pho_nha_ong_hem": ["phố", "nhà ống", "shophouse", "street", "dây điện", "miếu", "xe máy", "biển hiệu", "sương mù"],
    "phong_truong_cong_an": ["công an", "trưởng đồn", "police chief", "văn phòng", "bàn làm việc", "giấy khen", "cúp"],
    "phong_icu": ["bệnh viện", "icu", "hồi sức", "giường bệnh", "máy thở", "monitor", "hospital room"],
    "cho_co_mai_che": ["chợ", "chợ ướt", "wet market", "sạp thịt", "trái cây", "sạp cá", "mái tôn"],
    "phong_dieu_tra": ["phòng điều tra", "bảng ghim", "dây đỏ", "investigation", "người mất tích", "laptop", "cork board"],
    "ben_go_nha_san_dem": ["bến gỗ", "nhà sàn", "ven sông", "pier", "riverside", "đèn đường", "xóm nghèo"],
    "tiem_tap_hoa_nho": ["tạp hoá", "tiệm nhỏ", "snack shop", "grocery", "mặt tiền", "tủ nước", "kỷ niệm"],
    "toa_an_mat_tien": ["toà án", "court", "courthouse", "hàng cột", "bậc thềm", "phiên toà"],
    "phong_tro_vali": ["phòng trọ", "phòng trống", "vali", "suitcase", "dọn đi", "thùng giấy", "ký túc xá", "dorm"],
}

L.LIBRARY_SCENES.update(SCENES)
L.LIBRARY_TAGS.update(TAGS)
