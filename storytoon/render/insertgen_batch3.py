"""Ảnh chèn lô 3 — thư viện mở rộng (provenance 'procedural_library'), cùng phong cách flat-vector với insertgen.

Chủ đề: truyện đô thị kinh dị (bùa hộ mệnh thắt nút, máy bán hàng tự động, kẹo "FREE", ảnh lớp cũ, bức tranh người
đứng dưới đèn đường, bản đồ tàu điện, gõ cửa buồng vệ sinh, tay ma đeo găng, thông báo ứng dụng, đèn đường + trăng).
Mọi hình vẽ là bản GỐC bằng code (skia); không thương hiệu/logo; MỌI chữ vẽ vào pixel là TIẾNG ANH, lấy từ params.

Hệ toạ độ logic 3840×2160 (canvas scale theo cỡ ra). Được insertgen nạp ở cuối module (như insertgen_batch2):
INSERTS / SCREENS / TAGS / PROPS được trộn vào bảng của insertgen.
"""
from __future__ import annotations

import math
import random

import skia

from .insertgen import _hand, _lin, _rad, _shadow, draw_background, draw_phone, hand_tip, text
from .insertgen_batch2 import (LH, LW, _begin, _blurred, _card, _dash, _seven, _seven_width, _spaced, _vignette,
                               _wood_top)
from .skutil import capsule, fill, font, nfc, oval, poly, rrect, shade, smooth, stroke, wrap_text


# =================================================================== tiện ích chung
def _speckle(c, base, n=2600, seed=21, spread=(-0.18, 0.14), rmax=7.0, a=0.6) -> None:
    rng = random.Random(seed)
    c.drawRect(skia.Rect.MakeWH(LW, LH), fill(base))
    for _ in range(n):
        c.drawCircle(rng.uniform(0, LW), rng.uniform(0, LH), rng.uniform(1.5, rmax),
                     fill(shade(base, rng.uniform(*spread)), a))


def _night_wall(c, base="#2b3140") -> None:
    c.drawRect(skia.Rect.MakeWH(LW, LH), _rad(LW * 0.5, LH * 0.35, LW * 0.75, [shade(base, 0.12), base, shade(base, -0.5)],
                                              [0, 0.5, 1]))


def _cone(c, x, y, w0, w1, h, col="#ffe7a8", a=0.22) -> None:
    """Nón sáng hình thang từ (x, y) xuống dưới h."""
    p = _lin((x, y), (x, y + h), [(col, a), (col, 0.0)])
    p.setBlendMode(skia.BlendMode.kScreen)
    c.drawPath(poly([(x - w0 / 2, y), (x + w0 / 2, y), (x + w1 / 2, y + h), (x - w1 / 2, y + h)]), p)


def _soft_glow(c, x, y, r, col, a=0.55) -> None:
    p = _rad(x, y, r, [(col, a), (col, a * 0.35), (col, 0.0)], [0, 0.35, 1])
    p.setBlendMode(skia.BlendMode.kScreen)
    c.drawCircle(x, y, r, p)


def _sepia_layer(c, rect: skia.Rect, amt=1.0) -> None:
    m = [0.393, 0.769, 0.189, 0, 0, 0.349, 0.686, 0.168, 0, 0, 0.272, 0.534, 0.131, 0, 0, 0, 0, 0, 1, 0]
    ident = [1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0]
    mm = [ident[i] + (m[i] - ident[i]) * amt for i in range(20)]
    c.saveLayer(rect, skia.Paint(ColorFilter=skia.ColorFilters.Matrix(mm)))


# =================================================================== bùa hộ mệnh + chuỗi hạt thắt nút
def _bead_string(c, pts, beads: int, spent: int, s: float, bead_col="#c8352e", cord="#e8d9b0") -> None:
    """Dây thắt nút với `beads` hạt dọc theo đường cong pts; `spent` hạt đầu đã 'dùng' (nứt, xám)."""
    path = smooth(pts, close=False)
    c.drawPath(path, stroke("#000000", 16 * s, 0.25))
    c.drawPath(path, stroke(cord, 11 * s))
    meas = skia.PathMeasure(path, False)
    L = meas.getLength()
    r = 46 * s
    for k in range(beads):
        frac = (k + 0.7) / (beads + 0.6)
        pos, tan = meas.getPosTan(L * frac)
        x, y = pos.x(), pos.y()
        # nút thắt (knot) giữa các hạt
        kp, _ = meas.getPosTan(L * max(0.0, frac - 0.5 / (beads + 0.6)))
        c.drawCircle(kp.x(), kp.y(), 15 * s, fill(shade(cord, -0.25)))
        c.drawCircle(kp.x(), kp.y(), 9 * s, fill(shade(cord, -0.05)))
        used = k >= beads - spent
        col = "#8d8a86" if used else bead_col
        c.drawCircle(x + r * 0.18, y + r * 0.3, r, _blurred("#000000", 0.35, r * 0.3))
        c.drawCircle(x, y, r, _rad(x - r * 0.35, y - r * 0.4, r * 1.6, [shade(col, 0.45), col, shade(col, -0.4)],
                                   [0, 0.45, 1]))
        c.drawCircle(x - r * 0.35, y - r * 0.38, r * 0.2, fill("#ffffff", 0.7 if not used else 0.35))
        if used:   # vết nứt
            c.drawPath(poly([(x - r * 0.5, y - r * 0.6), (x - r * 0.05, y - r * 0.1), (x - r * 0.25, y + r * 0.2),
                             (x + r * 0.3, y + r * 0.7)], close=False), stroke("#3a3836", 5 * s))
    end, tan = meas.getPosTan(L)
    # tua cuối dây
    ex, ey = end.x(), end.y()
    c.drawPath(rrect(ex - 16 * s, ey - 6 * s, ex + 16 * s, ey + 30 * s, 8 * s), fill(shade(cord, -0.2)))
    for k in range(9):
        a = (k - 4) * 0.07
        c.drawLine(ex + (k - 4) * 3 * s, ey + 26 * s, ex + math.sin(a) * 150 * s, ey + 26 * s + math.cos(a) * 150 * s,
                   stroke(cord if k % 2 else shade(cord, -0.12), 8 * s))


def _charm(c, cx, cy, s, ang=0.0, label="CHARM", col="#c8352e", gold="#e2b34a", cord="#e8d9b0",
           loop=True) -> tuple[float, float]:
    """Túi bùa gấm đỏ (tâm thân túi tại cx, cy). Trả về điểm dưới đáy túi (để nối chuỗi hạt) theo toạ độ khung."""
    c.save()
    c.translate(cx, cy)
    c.rotate(ang)
    body = smooth([(-150 * s, -250 * s), (-215 * s, -120 * s), (-235 * s, 120 * s), (-210 * s, 300 * s),
                   (0, 345 * s), (210 * s, 300 * s), (235 * s, 120 * s), (215 * s, -120 * s), (150 * s, -250 * s),
                   (0, -235 * s)])
    q = skia.Path(body)
    q.offset(18 * s, 30 * s)
    c.drawPath(q, _blurred("#000000", 0.45, 30 * s))
    if loop:   # quai dây phía trên
        lp = skia.Path()
        lp.moveTo(-40 * s, -300 * s)
        lp.cubicTo(-120 * s, -520 * s, 120 * s, -520 * s, 40 * s, -300 * s)
        c.drawPath(lp, stroke("#000000", 22 * s, 0.25))
        c.drawPath(lp, stroke(cord, 16 * s))
    c.drawPath(body, _lin((-235 * s, 0), (235 * s, 0), [shade(col, -0.18), col, shade(col, 0.08), shade(col, -0.3)],
                          [0, 0.35, 0.6, 1]))
    # hoa văn gấm: sóng bán nguyệt vàng mảnh
    c.save()
    c.clipPath(body, skia.ClipOp.kIntersect, True)
    r = 38 * s
    row = 0
    y = -260 * s
    while y < 380 * s:
        x = -260 * s + (r if row % 2 else 0)
        while x < 280 * s:
            for k in (1.0, 0.66, 0.33):
                c.drawArc(skia.Rect.MakeLTRB(x - r * k, y - r * k, x + r * k, y + r * k), 180, 180, False,
                          stroke(gold, 3.2 * s, 0.38))
            x += 2 * r
        y += r * 0.9
        row += 1
    c.drawRect(skia.Rect.MakeLTRB(120 * s, -300 * s, 260 * s, 400 * s), fill("#000000", 0.12))
    c.restore()
    # nhãn trắng dọc
    lw, lt, lb = 92 * s, -150 * s, 250 * s
    c.drawPath(rrect(-lw / 2, lt, lw / 2, lb, 8 * s), fill("#f6efe0"))
    c.drawPath(rrect(-lw / 2 + 10 * s, lt + 10 * s, lw / 2 - 10 * s, lb - 10 * s, 5 * s), stroke(gold, 4 * s))
    lab = nfc(str(label or "")).upper()
    if lab:
        n = len(lab)
        fs = min(62 * s, (lb - lt - 50 * s) / max(1, n) / 1.05)
        f = font(fs, "extrabold")
        for i, ch in enumerate(lab):
            yy = lt + 30 * s + (i + 0.82) * (lb - lt - 60 * s) / n
            w = f.measureText(ch)
            c.drawString(ch, -w / 2, yy, f, fill("#9a1f1a"))
    # cổ túi rút dây + nơ
    c.drawPath(smooth([(-175 * s, -300 * s), (-120 * s, -250 * s), (0, -240 * s), (120 * s, -250 * s), (175 * s, -300 * s),
                       (110 * s, -330 * s), (0, -320 * s), (-110 * s, -330 * s)]), fill(shade(col, -0.12)))
    for k in range(5):   # nếp nhăn miệng túi
        x = (-120 + k * 60) * s
        c.drawLine(x, -315 * s, x * 0.8, -255 * s, stroke(shade(col, -0.35), 4 * s, 0.7))
    c.drawPath(capsule(-160 * s, -262 * s, 160 * s, -262 * s, 26 * s, 26 * s), fill(cord))
    c.drawLine(-150 * s, -262 * s, 150 * s, -262 * s, stroke(shade(cord, -0.25), 4 * s, 0.6))
    c.drawPath(oval(-40 * s, -262 * s, 50 * s, 28 * s), fill(shade(cord, -0.05)))
    c.drawPath(oval(40 * s, -262 * s, 50 * s, 28 * s), fill(shade(cord, -0.05)))
    c.drawCircle(0, -262 * s, 24 * s, fill(shade(cord, -0.18)))
    # điểm đáy (toạ độ khung)
    m = c.getTotalMatrix()
    c.restore()
    inv = skia.Matrix()
    c.getTotalMatrix().invert(inv)
    pt = skia.Matrix.Concat(inv, m).mapXY(0, 330 * s)
    return pt.x(), pt.y()


def _charm_params(p):
    return dict(label=p.get("label", "CHARM"), col=p.get("pouch_color", "#c8352e"), gold=p.get("gold", "#e2b34a"),
                cord=p.get("cord", "#e8d9b0"))


def ins_charm_pouch(p, size):
    """Túi bùa gấm đỏ nằm trên vải tối, chuỗi 5 hạt thắt nút uốn cong bên dưới."""
    s, c = _begin(size)
    _speckle(c, p.get("cloth", "#2c2a36"), n=1800, spread=(-0.12, 0.1), rmax=5)
    c.drawRect(skia.Rect.MakeWH(LW, LH), _rad(LW * 0.45, LH * 0.4, LW * 0.6, [("#ffe9c0", 0.12), ("#000000", 0.0)]))
    cp = _charm_params(p)
    bx, by = _charm(c, 1600, 900, 1.55, -14, **cp)
    n, spent = int(p.get("beads", 5)), int(p.get("spent", 0))
    _bead_string(c, [(bx, by - 20), (bx + 150, by + 220), (bx + 600, by + 330), (bx + 1050, by + 240),
                     (bx + 1400, by + 40)], n, spent, 1.6, p.get("bead_color", "#c8352e"), cp["cord"])
    _vignette(c, 0.55)
    return s.makeImageSnapshot()


def ins_charm_pouch_hand(p, size):
    """Tay POV cầm túi bùa giơ lên, chuỗi hạt thắt nút buông xuống bên cạnh."""
    s, c = _begin(size)
    _bokeh(c, p)
    sleeve, skin = p.get("sleeve_color", "#e8b830"), p.get("skin", "#e9b994")
    cp = _charm_params(p)
    hx, hy, ha, hs = 2080.0, 1960.0, -10.0, 1.6
    _hand(c, hx, hy, ha, hs, sleeve, skin, "grip", "back")
    bx, by = _charm(c, 1900, 900, 1.45, -6, **cp)
    _bead_string(c, [(bx, by - 30), (bx - 120, by + 180), (bx - 380, by + 330), (bx - 640, by + 360),
                     (bx - 820, by + 520)], int(p.get("beads", 5)), int(p.get("spent", 0)), 1.5,
                 p.get("bead_color", "#c8352e"), cp["cord"])
    _hand(c, hx, hy, ha, hs, sleeve, skin, "grip", "front")
    _vignette(c, 0.45)
    return s.makeImageSnapshot()


def ins_charm_pouch_pass(p, size):
    """Hai bàn tay: tay trái (người già) đưa túi bùa, tay phải (người trẻ) xoè ra đón — trao bùa."""
    s, c = _begin(size)
    _bokeh(c, p)
    cp = _charm_params(p)
    g_sleeve, g_skin = p.get("giver_sleeve", "#7a4a8a"), p.get("giver_skin", "#d9a77f")
    r_sleeve, r_skin = p.get("receiver_sleeve", "#e8b830"), p.get("receiver_skin", "#e9b994")
    # tay nhận: xoè ngửa, từ dưới-phải
    _hand(c, 2500, 2480, -28, 1.55, r_sleeve, r_skin, "open", "all", mirror=True)
    # tay đưa: nhón quai dây, từ trên-trái chĩa xuống
    ga, gs = 152.0, 1.5
    tx, ty = 1640.0, 420.0
    hx0, hy0 = hand_tip(0, 0, ga, gs, "pinch")
    gx, gy = tx - hx0, ty - hy0
    # quai dây treo từ đầu ngón xuống miệng túi
    pcx, pcy = 1760.0, 1000.0
    c.drawPath(poly([(tx, ty), (pcx - 30, pcy - 330), (pcx + 30, pcy - 330)]), stroke(cp["cord"], 18))
    bx, by = _charm(c, pcx, pcy, 1.25, 4, loop=False, **cp)
    _bead_string(c, [(bx, by - 20), (bx + 80, by + 160), (bx + 300, by + 270), (bx + 560, by + 240)],
                 int(p.get("beads", 5)), int(p.get("spent", 0)), 1.25, p.get("bead_color", "#c8352e"), cp["cord"])
    _hand(c, gx, gy, ga, gs, g_sleeve, g_skin, "pinch", "all")
    if p.get("glow", True):
        _soft_glow(c, pcx, pcy, 900, "#ffd27a", 0.22)
    _vignette(c, 0.45)
    return s.makeImageSnapshot()


def _bokeh(c, p) -> None:
    rng = random.Random(int(p.get("seed", 6)))
    c.drawRect(skia.Rect.MakeWH(LW, LH), _rad(LW * 0.5, LH * 0.45, LW * 0.75, [p.get("bg0", "#2a2f45"), p.get("bg1", "#0e1018")]))
    for _ in range(24):
        r = rng.uniform(80, 220)
        c.drawCircle(rng.uniform(0, LW), rng.uniform(0, LH), r,
                     _blurred(rng.choice(["#f2c46b", "#d0302a", "#6a8ad0", "#f6efe0"]), rng.uniform(0.12, 0.3), r * 0.2))


# =================================================================== máy bán hàng tự động (cặp)
def _can(c, x, y, w, h, col, band) -> None:
    c.drawPath(rrect(x, y, x + w, y + h, w * 0.18), _lin((x, 0), (x + w, 0), [shade(col, -0.25), shade(col, 0.2), col,
                                                                             shade(col, -0.3)], [0, 0.3, 0.6, 1]))
    c.drawRect(skia.Rect.MakeLTRB(x, y + h * 0.38, x + w, y + h * 0.62), fill(band))
    c.drawPath(smooth([(x + w * 0.2, y + h * 0.5), (x + w * 0.4, y + h * 0.43), (x + w * 0.6, y + h * 0.57),
                       (x + w * 0.8, y + h * 0.5)], close=False), stroke(col, w * 0.07))
    c.drawPath(rrect(x + w * 0.08, y - h * 0.03, x + w * 0.92, y + h * 0.06, w * 0.1), fill("#c9ced6"))
    c.drawRect(skia.Rect.MakeLTRB(x + w * 0.22, y + h * 0.08, x + w * 0.32, y + h * 0.9), fill("#ffffff", 0.22))


def _vending(c, l, t, w, body, accent, label, temp_icon, prices, display, seed) -> None:
    r = l + w
    b = LH + 60
    _shadow(c, rrect(l, t, r, b, 40), 50, 0, 0.6)
    c.drawPath(rrect(l, t, r, b, 40), _lin((l, 0), (r, 0), [shade(body, -0.12), body, shade(body, 0.06), shade(body, -0.2)],
                                           [0, 0.15, 0.8, 1]))
    # bảng đầu (header) sáng
    c.drawPath(rrect(l + 60, t + 50, r - 60, t + 260, 24), fill(accent))
    c.drawPath(rrect(l + 60, t + 50, r - 60, t + 120, 24), fill("#ffffff", 0.15))
    text(c, label, (l + r) / 2 + 40, t + 210, 150, "#ffffff", "extrabold", "center")
    ix, iy = (l + r) / 2 - text_w(label, 150) / 2 - 80, t + 158
    if temp_icon == "cold":
        for k in range(3):
            a = math.radians(k * 60)
            c.drawLine(ix - math.cos(a) * 55, iy - math.sin(a) * 55, ix + math.cos(a) * 55, iy + math.sin(a) * 55,
                       stroke("#ffffff", 14))
    else:
        c.drawPath(smooth([(ix, iy - 70), (ix + 45, iy), (ix + 30, iy + 50), (ix - 30, iy + 50), (ix - 45, iy)]),
                   fill("#ffffff"))
        c.drawPath(smooth([(ix, iy - 10), (ix + 20, iy + 25), (ix, iy + 45), (ix - 20, iy + 25)]), fill(accent))
    # vitrine kính
    gl, gt, gr, gb = l + 70, t + 320, r - 70, t + 1400
    c.drawPath(rrect(gl, gt, gr, gb, 18), fill("#e9f1f6"))
    rng = random.Random(seed)
    cols = [("#3a78c2", "#ffffff"), ("#f3c94e", "#c8352e"), ("#4fa35a", "#f6efe0"), ("#e8833a", "#ffffff"),
            ("#c74a9a", "#f6efe0"), ("#8a5a3a", "#f3c94e"), ("#d8423a", "#ffffff"), ("#2f2f36", "#e2b34a")]
    rows, per = 3, 5
    cw = (gr - gl - 80) / per
    pi = 0
    for rr_ in range(rows):
        ry = gt + 40 + rr_ * 350
        for k in range(per):
            cc = cols[rng.randrange(len(cols))]
            _can(c, gl + 40 + k * cw + cw * 0.18, ry + 10, cw * 0.64, 220, *cc)
            # nút giá
            bx = gl + 40 + k * cw + cw * 0.5
            c.drawPath(rrect(bx - cw * 0.36, ry + 250, bx + cw * 0.36, ry + 300, 12), fill("#2a2c33"))
            text(c, prices[pi % len(prices)], bx - cw * 0.06, ry + 288, 38, "#ffe9a8", "bold", "center")
            c.drawCircle(bx + cw * 0.24, ry + 275, 13, fill("#7dff8a" if rng.random() < 0.8 else "#ff6a5a"))
            pi += 1
        c.drawRect(skia.Rect.MakeLTRB(gl, ry + 310, gr, ry + 322), fill("#b9c4cc"))
    c.drawPath(poly([(gl, gt + 900), (gl + 500, gt), (gl + 700, gt), (gl, gt + 1150)]), fill("#ffffff", 0.18))
    c.drawPath(poly([(gl + 900, gb), (gr, gt + 250), (gr, gt + 420), (gl + 1100, gb)]), fill("#ffffff", 0.1))
    c.drawPath(rrect(gl, gt, gr, gb, 18), stroke(shade(body, -0.3), 10))
    # bảng điều khiển: LED, khe xu, khe trả xu
    py = t + 1460
    c.drawPath(rrect(l + 90, py, l + 640, py + 200, 16), fill("#14161b"))
    dh = 120
    dw = _seven_width(display, dh)
    _seven(c, display, l + 365 - dw / 2, py + 40, dh, "#ff5a3a", off="#2a1c1a", glow=True)
    sx = r - 330
    c.drawPath(rrect(sx - 110, py, sx + 110, py + 260, 26), fill(shade(body, -0.2)))
    c.drawPath(rrect(sx - 18, py + 40, sx + 18, py + 170, 10), fill("#111216"))
    text(c, "COINS", sx, py + 230, 40, shade(body, -0.6), "bold", "center")
    c.drawPath(rrect(l + 700, py + 30, l + 1000, py + 110, 12), fill("#111216"))
    c.drawRect(skia.Rect.MakeLTRB(l + 720, py + 62, l + 980, py + 78), fill("#3a3c42"))
    text(c, "BILLS", l + 850, py + 170, 40, shade(body, -0.6), "bold", "center")
    # khay lấy hàng
    c.drawPath(rrect(l + 150, py + 380, r - 150, py + 560, 24), fill("#1a1c22"))
    c.drawPath(rrect(l + 170, py + 400, r - 170, py + 470, 16), fill("#2e3038"))
    text(c, "PUSH", (l + r) / 2, py + 450, 44, "#9aa0aa", "bold", "center")


def text_w(s, size, weight="extrabold") -> float:
    return font(size, weight).measureText(nfc(s))


def ins_vending_pair(p, size):
    """Cặp máy bán hàng tự động cận cảnh ban đêm: trái 'COLD' (trắng-xanh), phải 'HOT' (đỏ); lon chung chung,
    nút giá, LED '000', khe xu."""
    s, c = _begin(size)
    _speckle(c, "#4a4d55", n=1500, spread=(-0.15, 0.08))
    for y in range(0, int(LH), 240):    # tường gạch block
        c.drawRect(skia.Rect.MakeLTRB(0, y, LW, y + 8), fill("#33363d"))
    _vending(c, 180, 120, 1700, p.get("cold_body", "#eef1f4"), p.get("cold_accent", "#2f6fd0"),
             p.get("cold_label", "COLD"), "cold", p.get("prices", ["100", "120", "150"]), p.get("display", "000"), 3)
    _vending(c, 1960, 120, 1700, p.get("hot_body", "#c8352e"), p.get("hot_accent", "#8a1d18"),
             p.get("hot_label", "HOT"), "hot", p.get("prices", ["100", "120", "150"]), p.get("display", "000"), 9)
    _soft_glow(c, 1030, 900, 1400, "#dfefff", 0.18)
    _soft_glow(c, 2810, 900, 1400, "#ffd0c0", 0.14)
    _vignette(c, 0.5)
    return s.makeImageSnapshot()


# =================================================================== gói kẹo FREE + kẹo rơi trên nhựa đường
def _candy(c, x, y, ang, s, col, stripe) -> None:
    c.save()
    c.translate(x, y)
    c.rotate(ang)
    c.drawPath(oval(10 * s, 18 * s, 120 * s, 60 * s), _blurred("#000000", 0.4, 14 * s))
    for sgn in (-1, 1):   # 2 đầu xoắn
        c.drawPath(poly([(sgn * 70 * s, 0), (sgn * 150 * s, -48 * s), (sgn * 138 * s, 0), (sgn * 150 * s, 48 * s)]),
                   fill(shade(col, 0.15)))
        for k in (-26, 0, 26):
            c.drawLine(sgn * 80 * s, 0, sgn * 140 * s, k * s * 1.4, stroke(shade(col, -0.2), 3 * s, 0.6))
    c.drawPath(oval(0, 0, 90 * s, 56 * s), _rad(-25 * s, -20 * s, 110 * s, [shade(col, 0.35), col, shade(col, -0.25)]))
    c.save()
    c.clipPath(oval(0, 0, 90 * s, 56 * s), skia.ClipOp.kIntersect, True)
    for k in range(-3, 4):
        c.drawLine(k * 40 * s - 40 * s, -60 * s, k * 40 * s + 40 * s, 60 * s, stroke(stripe, 12 * s, 0.75))
    c.restore()
    c.drawPath(oval(-30 * s, -24 * s, 28 * s, 10 * s), fill("#ffffff", 0.55))
    c.restore()


def ins_candy_pack_asphalt(p, size):
    """Nhìn từ trên: gói kẹo in 'FREE' trên mặt nhựa đường ban đêm, kẹo bọc giấy xoắn rơi vãi xung quanh."""
    s, c = _begin(size)
    _speckle(c, p.get("asphalt", "#3a3b3f"), n=5200, spread=(-0.25, 0.22), rmax=6, a=0.75)
    # vạch sơn lề đường + nắp cống
    c.drawPath(poly([(0, 1840), (LW, 1640), (LW, 1700), (0, 1900)]), fill("#d9c25a", 0.8))
    rng = random.Random(5)
    for _ in range(300):
        c.drawCircle(rng.uniform(0, LW), rng.uniform(1600, 1950), rng.uniform(2, 8), fill("#3a3b3f", 0.8))
    c.drawRect(skia.Rect.MakeWH(LW, LH), _rad(LW * 0.48, LH * 0.45, LW * 0.6, [("#ffe7b0", 0.22), ("#ffe7b0", 0.0)]))
    # gói kẹo
    cx, cy, ang = 1880.0, 900.0, float(p.get("pack_angle", -10))
    pw, ph = 1300.0, 980.0
    c.save()
    c.translate(cx, cy)
    c.rotate(ang)
    body = skia.Path()
    zig = 22
    body.moveTo(-pw / 2, -ph / 2)
    for i in range(zig + 1):
        body.lineTo(-pw / 2 + pw * i / zig, -ph / 2 - (28 if i % 2 else 0))
    for i in range(zig + 1):
        body.lineTo(pw / 2 - pw * i / zig, ph / 2 + (28 if i % 2 else 0))
    body.close()
    q = skia.Path(body)
    q.offset(30, 50)
    c.drawPath(q, _blurred("#000000", 0.55, 40))
    pk = p.get("pack_color", "#f6a7c1")
    c.drawPath(body, _lin((-pw / 2, -ph / 2), (pw / 2, ph / 2), [shade(pk, 0.2), pk, shade(pk, -0.12)]))
    c.drawRect(skia.Rect.MakeLTRB(-pw / 2, -ph / 2 + 10, pw / 2, -ph / 2 + 90), fill(shade(pk, -0.15)))
    c.drawRect(skia.Rect.MakeLTRB(-pw / 2, ph / 2 - 90, pw / 2, ph / 2 - 10), fill(shade(pk, -0.15)))
    # chấm bi
    for i in range(9):
        for j in range(6):
            c.drawCircle(-pw / 2 + 80 + i * 145 + (70 if j % 2 else 0), -ph / 2 + 150 + j * 140, 22, fill("#ffffff", 0.35))
    # ngôi sao nổ + chữ FREE
    star = skia.Path()
    n = 18
    for k in range(n * 2):
        rr = 380 if k % 2 == 0 else 300
        a = math.pi * k / n
        (star.moveTo if k == 0 else star.lineTo)(math.cos(a) * rr * 1.25, math.sin(a) * rr * 0.9 - 20)
    star.close()
    c.drawPath(star, fill(p.get("burst", "#f3c94e")))
    c.drawPath(star, stroke("#ffffff", 10))
    text(c, p.get("label", "FREE"), 0, 90, 260, "#c8352e", "extrabold", "center", max_w=760, outline="#ffffff",
         outline_w=22)
    text(c, p.get("sub", "TAKE ONE"), 0, 220, 70, "#7a2a28", "extrabold", "center", max_w=620)
    c.drawPath(poly([(-pw / 2 + 40, -ph / 2 + 120), (-pw / 2 + 360, -ph / 2 + 120), (-pw / 2 + 40, ph / 2 - 200)]),
               fill("#ffffff", 0.14))
    # miệng gói bị xé + kẹo trào ra
    c.restore()
    cand = [("#c8352e", "#ffffff"), ("#3a78c2", "#f3c94e"), ("#4fa35a", "#ffffff"), ("#f3c94e", "#e8833a"),
            ("#8a5ac2", "#ffffff"), ("#e8833a", "#fff2c0")]
    rng = random.Random(int(p.get("seed", 12)))
    n = int(p.get("candies", 16))
    placed = 0
    while placed < n:
        x, y = rng.uniform(300, LW - 300), rng.uniform(250, LH - 250)
        if abs(x - cx) < 820 and abs(y - cy) < 640:
            continue
        col, st = cand[placed % len(cand)]
        _candy(c, x, y, rng.uniform(0, 360), rng.uniform(1.1, 1.6), col, st)
        placed += 1
    _vignette(c, 0.6)
    return s.makeImageSnapshot()


# =================================================================== ảnh lớp cũ trên bàn gỗ
def _kid(c, x, y, s, hair, uni, skin, girl, rng) -> None:
    c.drawPath(rrect(x - 70 * s, y + 70 * s, x + 70 * s, y + 260 * s, 50 * s), fill(uni))
    c.drawPath(poly([(x - 30 * s, y + 70 * s), (x, y + 120 * s), (x + 30 * s, y + 70 * s)]), fill("#f6f2ea"))
    c.drawPath(oval(x, y, 58 * s, 64 * s), fill(skin))
    hp = skia.Path()
    hp.addOval(skia.Rect.MakeLTRB(x - 62 * s, y - 72 * s, x + 62 * s, y - 4 * s))
    c.drawPath(hp, fill(hair))
    if girl:
        c.drawPath(rrect(x - 66 * s, y - 30 * s, x - 40 * s, y + 60 * s, 12 * s), fill(hair))
        c.drawPath(rrect(x + 40 * s, y - 30 * s, x + 66 * s, y + 60 * s, 12 * s), fill(hair))
    c.drawCircle(x - 20 * s, y + 8 * s, 6 * s, fill("#2a2420"))
    c.drawCircle(x + 20 * s, y + 8 * s, 6 * s, fill("#2a2420"))
    if rng.random() < 0.7:
        c.drawArc(skia.Rect.MakeLTRB(x - 14 * s, y + 18 * s, x + 14 * s, y + 38 * s), 20, 140, False,
                  stroke("#6a3a2a", 4 * s))
    else:
        c.drawLine(x - 10 * s, y + 32 * s, x + 10 * s, y + 32 * s, stroke("#6a3a2a", 4 * s))


def ins_class_photo_table(p, size):
    """Ảnh lớp cũ ố vàng (3 hàng học sinh trước toà nhà trường) nằm trên bàn gỗ, chú thích năm tiếng Anh."""
    s, c = _begin(size)
    _wood_top(c, p.get("table", "#8a5a36"))
    c.drawRect(skia.Rect.MakeWH(LW, LH), _rad(LW * 0.5, LH * 0.4, LW * 0.6, [("#ffe2a8", 0.18), ("#000000", 0.0)]))
    # mép tờ giấy khác bên dưới
    c.save()
    c.rotate(-8, 3000, 1600)
    c.drawPath(rrect(2700, 1300, 3700, 2400, 6), fill("#e9e2d0"))
    for k in range(6):
        c.drawLine(2760, 1400 + k * 70, 3600, 1400 + k * 70, stroke("#9aa3b0", 6, 0.6))
    c.restore()
    cx, cy, ang = 1820.0, 1040.0, float(p.get("angle", 3))
    w, h = 2600.0, 1720.0
    c.save()
    c.translate(cx, cy)
    c.rotate(ang)
    frame = rrect(-w / 2, -h / 2, w / 2, h / 2, 10)
    _shadow(c, frame, 34, 28, 0.6)
    c.drawPath(frame, fill("#f1e9d6"))
    pl, pt, pr, pb = -w / 2 + 90, -h / 2 + 90, w / 2 - 90, h / 2 - 260
    rect = skia.Rect.MakeLTRB(pl, pt, pr, pb)
    _sepia_layer(c, rect, float(p.get("fade", 0.85)))
    c.drawRect(rect, _lin((0, pt), (0, pb), ["#b9d4ea", "#e6eef2"]))
    # toà nhà trường phía sau
    c.drawRect(skia.Rect.MakeLTRB(pl, pt + 180, pr, pb - 300), fill("#d9cfc0"))
    for i in range(14):
        for j in range(2):
            wx = pl + 80 + i * 165
            wy = pt + 240 + j * 190
            c.drawRect(skia.Rect.MakeLTRB(wx, wy, wx + 110, wy + 130), fill("#7f99ad"))
            c.drawLine(wx + 55, wy, wx + 55, wy + 130, stroke("#d9cfc0", 6))
    c.drawRect(skia.Rect.MakeLTRB(pl, pb - 320, pr, pb), fill("#bfae92"))
    rng = random.Random(int(p.get("seed", 4)))
    hair = ["#2a2420", "#3a2a20", "#1f1c1a"]
    skins = ["#f1d3bd", "#e9b994", "#d9a77f"]
    rows = [(8, pb - 860, 0.92), (9, pb - 640, 0.98), (9, pb - 400, 1.05)]
    idx = 0
    pos_list = []
    for n, ry, sc in rows:
        span = (pr - pl) * 0.82
        for k in range(n):
            x = (pl + pr) / 2 + (k - (n - 1) / 2) * span / n
            girl = rng.random() < 0.5
            _kid(c, x, ry, sc * 1.18, rng.choice(hair), "#2b3550" if not girl else "#38405e", rng.choice(skins), girl, rng)
            pos_list.append((x, ry, sc))
            idx += 1
    # giáo viên đứng cuối hàng
    tx = pr - 150
    c.drawPath(rrect(tx - 95, pb - 880, tx + 95, pb - 380, 60), fill("#5a4a3a"))
    c.drawPath(oval(tx, pb - 960, 70, 78), fill("#e9b994"))
    hp = skia.Path()
    hp.addArc(skia.Rect.MakeLTRB(tx - 74, pb - 1045, tx + 74, pb - 905), 180, 180)
    c.drawPath(hp, fill("#3a2a20"))
    c.drawCircle(tx - 24, pb - 955, 7, fill("#2a2420"))
    c.drawCircle(tx + 24, pb - 955, 7, fill("#2a2420"))
    c.restore()
    c.drawRect(rect, _rad((pl + pr) / 2, (pt + pb) / 2, (pr - pl) * 0.7, [("#000000", 0.0), ("#3a2410", 0.5)], [0.45, 1]))
    rng2 = random.Random(9)
    for _ in range(16):   # vết xước
        x = rng2.uniform(pl, pr)
        c.drawLine(x, rng2.uniform(pt, pb), x + rng2.uniform(-60, 60), rng2.uniform(pt, pb), stroke("#ffffff", 3, 0.35))
    c.drawPath(rrect(pl, pt, pr, pb, 2), stroke("#c9bfa8", 5))
    ci = p.get("circled")
    if isinstance(ci, int) and 0 <= ci < len(pos_list):
        x, y, sc = pos_list[ci]
        c.drawPath(oval(x, y + 10, 110 * sc, 120 * sc), stroke("#d0302a", 14, 0.9))
    cap = p.get("caption", "CLASS 4-B  ·  1998")
    text(c, cap, 0, h / 2 - 110, 92, "#3a3530", "semibold", "center", max_w=w * 0.8)
    c.restore()
    _vignette(c, 0.5)
    return s.makeImageSnapshot()


# =================================================================== bức tranh: người đứng dưới đèn đường
def ins_painting_streetlamp(p, size):
    """Tranh sơn dầu đóng khung vàng trên tường tối, đèn rọi tranh; trong tranh: phố đêm, 1 bóng người đứng dưới
    cột đèn đường (nét cọ ngắn)."""
    s, c = _begin(size)
    wall = p.get("wall", "#3a2f2a")
    c.drawRect(skia.Rect.MakeWH(LW, LH), fill(wall))
    for x in range(0, int(LW), 320):    # sọc giấy dán tường
        c.drawRect(skia.Rect.MakeLTRB(x, 0, x + 140, LH), fill(shade(wall, 0.05)))
    c.drawRect(skia.Rect.MakeWH(LW, LH), _rad(LW / 2, 120, 1900, [("#ffe1a0", 0.35), ("#ffe1a0", 0.0)]))
    l, t, r, b = 1020.0, 260.0, 2820.0, 1860.0
    _shadow(c, rrect(l, t, r, b, 8), 50, 40, 0.7)
    for k, (col, ins) in enumerate((("#8a6420", 0), ("#d8ab3a", 34), ("#f0d48a", 70), ("#a87a28", 86),
                                    ("#d8ab3a", 110), ("#5a4018", 150))):
        c.drawRect(skia.Rect.MakeLTRB(l + ins, t + ins, r - ins, b - ins), fill(col))
    for (x, y) in ((l + 60, t + 60), (r - 60, t + 60), (l + 60, b - 60), (r - 60, b - 60)):   # hoa góc
        c.drawCircle(x, y, 44, fill("#f0d48a"))
        c.drawCircle(x, y, 22, fill("#a87a28"))
    cl, ct, cr, cb = l + 165, t + 165, r - 165, b - 165
    cw, chh = cr - cl, cb - ct
    c.save()
    c.clipRect(skia.Rect.MakeLTRB(cl, ct, cr, cb))
    c.drawRect(skia.Rect.MakeLTRB(cl, ct, cr, cb), _lin((0, ct), (0, cb), ["#141a32", "#2a2f52", "#3a3550"]))
    # trăng nhỏ + nhà xa
    c.drawCircle(cl + cw * 0.8, ct + chh * 0.18, 60, fill("#e9e0c0", 0.8))
    rng = random.Random(3)
    x = cl
    while x < cr:
        hw = rng.uniform(140, 300)
        hh = rng.uniform(250, 480)
        c.drawRect(skia.Rect.MakeLTRB(x, cb - chh * 0.32 - hh, x + hw, cb), fill(rng.choice(["#1c2036", "#22263e", "#181b2c"])))
        if rng.random() < 0.5:
            c.drawRect(skia.Rect.MakeLTRB(x + hw * 0.3, cb - chh * 0.32 - hh * 0.7, x + hw * 0.55, cb - chh * 0.32 - hh * 0.5),
                       fill("#e8c46a", 0.7))
        x += hw + rng.uniform(10, 40)
    c.drawRect(skia.Rect.MakeLTRB(cl, cb - chh * 0.32, cr, cb), fill("#2b2a34"))
    # cột đèn + nón sáng + vũng sáng
    lx, ly = cl + cw * 0.52, ct + chh * 0.2
    c.drawRect(skia.Rect.MakeLTRB(lx - 12, ly, lx + 12, cb - chh * 0.12), fill("#0e0f16"))
    c.drawPath(poly([(lx - 50, ly), (lx + 50, ly), (lx + 30, ly - 50), (lx - 30, ly - 50)]), fill("#0e0f16"))
    _cone(c, lx, ly, 80, 820, cb - chh * 0.12 - ly, "#ffdf8a", 0.4)
    _soft_glow(c, lx, ly + 10, 240, "#ffe9a8", 0.8)
    c.drawPath(oval(lx, cb - chh * 0.13, 420, 70), fill("#e8c46a", 0.45))
    # bóng người đứng một mình
    fx, fy = lx + 150, cb - chh * 0.13
    c.drawPath(rrect(fx - 40, fy - 330, fx + 40, fy - 20, 30), fill("#0a0b10"))
    c.drawCircle(fx, fy - 380, 52, fill("#0a0b10"))
    c.drawPath(capsule(fx - 18, fy - 40, fx - 22, fy + 5, 30, 26), fill("#0a0b10"))
    c.drawPath(capsule(fx + 18, fy - 40, fx + 22, fy + 5, 30, 26), fill("#0a0b10"))
    # nét cọ
    rng = random.Random(11)
    for _ in range(1400):
        x, y = rng.uniform(cl, cr), rng.uniform(ct, cb)
        a = rng.uniform(-0.6, 0.6)
        ln = rng.uniform(20, 70)
        col = rng.choice(["#ffffff", "#000000", "#8a7ac0", "#ffd27a"])
        c.drawLine(x, y, x + math.cos(a) * ln, y + math.sin(a) * ln, stroke(col, rng.uniform(5, 12), 0.05))
    c.restore()
    c.drawRect(skia.Rect.MakeLTRB(cl, ct, cr, cb), stroke("#2a1c0c", 8))
    # đèn rọi tranh
    c.drawPath(rrect(LW / 2 - 300, 140, LW / 2 + 300, 210, 30), fill("#b8923a"))
    c.drawRect(skia.Rect.MakeLTRB(LW / 2 - 10, 60, LW / 2 + 10, 140), fill("#8a6420"))
    _soft_glow(c, LW / 2, 230, 600, "#fff0c0", 0.25)
    plaque = p.get("plaque", "UNTITLED")
    if plaque:
        c.drawPath(rrect(LW / 2 - 260, b + 60, LW / 2 + 260, b + 180, 10), _lin((0, b + 60), (0, b + 180), ["#e8c870", "#a87a28"]))
        text(c, plaque, LW / 2, b + 140, 56, "#3a2a10", "bold", "center", max_w=460)
    _vignette(c, 0.55)
    return s.makeImageSnapshot()


# =================================================================== bản đồ tàu điện + ghim đỏ
def ins_rail_map_pin(p, size):
    """Thẻ bản đồ kem: sông, công viên, 3 tuyến tàu màu với ga, ga đổi tuyến, ghim đỏ + chú thích đứt nét."""
    s, c = _begin(size)
    draw_background(c, "smoke_dark", int(LW), int(LH), p)
    l, t, r, b = 300.0, 200.0, 3540.0, 1960.0
    card = rrect(l, t, r, b, 40)
    _shadow(c, card, 50, 30, 0.6)
    c.drawPath(card, fill("#f3ecdc"))
    c.save()
    c.clipPath(card, skia.ClipOp.kIntersect, True)
    for x in range(int(l), int(r), 120):
        c.drawLine(x, t, x, b, stroke("#e2d9c4", 3, 0.6))
    for y in range(int(t), int(b), 120):
        c.drawLine(l, y, r, y, stroke("#e2d9c4", 3, 0.6))
    # sông
    river = [(l - 50, 1500), (900, 1380), (1500, 1520), (2100, 1300), (2700, 1250), (r + 50, 980)]
    c.drawPath(smooth(river, close=False), stroke("#a9cde6", 130))
    c.drawPath(smooth(river, close=False), stroke("#bcd9ee", 80))
    # công viên
    c.drawPath(rrect(2350, 1420, 2950, 1700, 50), fill("#c9e0b0"))
    c.drawPath(rrect(700, 1650, 1200, 1900, 50), fill("#c9e0b0"))
    lines = p.get("lines") or [
        {"color": "#d0302a", "pts": [[600, 600], [1300, 600], [1800, 1000], [2400, 1000], [3300, 1600]]},
        {"color": "#2f6fd0", "pts": [[1800, 380], [1800, 1000], [1800, 1800]]},
        {"color": "#3a9a4a", "pts": [[500, 1200], [1100, 1200], [1500, 800], [2600, 800], [3300, 500]]},
    ]
    stations = []
    for ln in lines:
        pts = [tuple(pt) for pt in ln["pts"]]
        pth = poly(pts, close=False)
        c.drawPath(pth, stroke("#ffffff", 64))
        c.drawPath(pth, stroke(ln["color"], 40))
        for i in range(len(pts) - 1):
            for k in (0.0, 0.5):
                x = pts[i][0] + (pts[i + 1][0] - pts[i][0]) * k
                y = pts[i][1] + (pts[i + 1][1] - pts[i][1]) * k
                stations.append((x, y, ln["color"]))
        stations.append((pts[-1][0], pts[-1][1], ln["color"]))
    for x, y, col in stations:
        c.drawCircle(x, y, 30, fill("#ffffff"))
        c.drawCircle(x, y, 30, stroke("#2a2c33", 10))
    c.drawPath(rrect(1740, 960, 1860, 1040, 40), fill("#ffffff"))      # ga đổi tuyến
    c.drawPath(rrect(1740, 960, 1860, 1040, 40), stroke("#2a2c33", 12))
    c.drawPath(rrect(1740, 760, 1860, 840, 40), fill("#ffffff"))
    c.drawPath(rrect(1740, 760, 1860, 840, 40), stroke("#2a2c33", 12))
    labels = p.get("station_labels") or [[600, 540, "NORTH GATE"], [1900, 1080, "CENTRAL"], [520, 1140, "OLD TOWN"],
                                         [3300, 1680, "PORT"], [1880, 370, "HILLSIDE"], [3150, 440, "RIVERSIDE"]]
    for x, y, lab in labels:
        text(c, lab, x, y, 46, "#2a2c33", "bold", "left" if x < 3000 else "center")
    c.restore()
    # tiêu đề
    text(c, p.get("title", "CITY"), l + 90, t + 160, 120, "#1f2430", "extrabold")
    text(c, _spaced(p.get("subtitle", "RAIL MAP")), l + 96, t + 230, 40, "#7a7466", "bold")
    # la bàn
    kx, ky = r - 170, t + 170
    c.drawCircle(kx, ky, 90, stroke("#2a2c33", 6))
    c.drawPath(poly([(kx, ky - 80), (kx + 26, ky), (kx - 26, ky)]), fill("#d0302a"))
    c.drawPath(poly([(kx, ky + 80), (kx + 26, ky), (kx - 26, ky)]), fill("#2a2c33"))
    text(c, "N", kx, ky - 105, 44, "#2a2c33", "bold", "center")
    # ghim đỏ
    pin = p.get("pin", {"x": 2400, "y": 1000, "label": "LAST SEEN · 02:40"})
    px, py = float(pin.get("x", 2400)), float(pin.get("y", 1000))
    for k, rr in enumerate((210, 150, 95)):
        c.drawCircle(px, py, rr, stroke("#d0302a", 8, 0.18 + k * 0.15))
    c.drawPath(oval(px + 20, py + 10, 60, 22), _blurred("#000000", 0.4, 10))
    head = smooth([(px, py), (px - 70, py - 140), (px - 80, py - 210), (px, py - 290), (px + 80, py - 210),
                   (px + 70, py - 140)])
    c.drawPath(head, fill("#d0302a"))
    c.drawCircle(px, py - 205, 34, fill("#ffffff"))
    c.drawCircle(px - 30, py - 240, 14, fill("#ffffff", 0.5))
    lab = pin.get("label", "LAST SEEN · 02:40")
    if lab:
        lx, ly = px + 260, py - 420
        c.drawLine(px + 60, py - 260, lx, ly + 40, _dash("#d0302a", 8, 24, 16))
        f = font(60, "extrabold")
        tw = f.measureText(nfc(lab))
        c.drawPath(rrect(lx - 20, ly - 40, lx + tw + 50, ly + 60, 50), fill("#d0302a"))
        text(c, lab, lx + 15, ly + 32, 60, "#ffffff", "extrabold")
    tag = p.get("tag", "LINE 1 · 4 STOPS")
    if tag:
        f = font(54, "bold")
        tw = f.measureText(nfc(tag))
        c.drawPath(rrect(l + 80, b - 170, l + 160 + tw, b - 70, 50), fill("#1f6f5c"))
        text(c, tag, l + 120, b - 100, 54, "#ffffff", "bold")
    _vignette(c, 0.35)
    return s.makeImageSnapshot()


# =================================================================== tay gõ cửa buồng vệ sinh
def _knock_fist(c, x, y, ang, s, skin, sleeve) -> None:
    """Nắm tay nhìn từ sau (mu bàn tay + 4 đốt ngón gập, khớp đốt lồi), cổ tay hướng +y local."""
    dk = shade(skin, -0.22)
    ol = stroke(shade(skin, -0.38), 6 * s, 0.8)
    c.save()
    c.translate(x, y)
    c.rotate(ang)
    arm = capsule(0, 200 * s, 0, 1700 * s, 250 * s, 300 * s)
    c.drawPath(arm, fill(skin))
    c.drawPath(arm, ol)
    c.drawPath(rrect(-195 * s, 420 * s, 195 * s, 1900 * s, 70 * s), fill(sleeve))
    c.drawPath(rrect(-205 * s, 400 * s, 205 * s, 520 * s, 50 * s), fill(shade(sleeve, -0.18)))
    c.drawRect(skia.Rect.MakeLTRB(110 * s, 520 * s, 195 * s, 1900 * s), fill(shade(sleeve, -0.12)))
    # 4 đốt ngón gần (proximal) gập về phía cửa: các khối bo tròn trên đỉnh mu bàn tay
    for i in range(4):
        fx = (-118 + i * 78) * s
        top = (-300 + abs(i - 1.5) * 22) * s
        seg = rrect(fx - 42 * s, top, fx + 42 * s, -120 * s, 40 * s)
        c.drawPath(seg, fill(shade(skin, 0.04 if i % 2 else 0.0)))
        c.drawPath(seg, ol)
        c.drawPath(oval(fx, top + 46 * s, 26 * s, 20 * s), fill(shade(skin, 0.22), 0.8))   # khớp lồi sáng
        c.drawLine(fx - 16 * s, top + 80 * s, fx + 16 * s, top + 80 * s, stroke(dk, 4 * s, 0.6))
    back = smooth([(-170 * s, -150 * s), (0, -170 * s), (170 * s, -150 * s), (185 * s, 20 * s),
                   (140 * s, 230 * s), (-120 * s, 240 * s), (-180 * s, 20 * s)])
    c.drawPath(back, fill(skin))
    c.drawPath(back, ol)
    c.drawPath(smooth([(80 * s, -150 * s), (170 * s, -140 * s), (180 * s, 20 * s), (135 * s, 215 * s), (90 * s, 200 * s)]),
               fill(dk, 0.3))
    for i in range(4):     # gân mu bàn tay hướng về từng đốt
        c.drawLine((-118 + i * 78) * s, -140 * s, (-40 + i * 26) * s, 160 * s, stroke(dk, 4 * s, 0.3))
    th = capsule(-150 * s, 120 * s, -205 * s, -40 * s, 96 * s, 78 * s)    # ngón cái ôm bên hông
    c.drawPath(th, fill(shade(skin, 0.03)))
    c.drawPath(th, ol)
    c.restore()

def ins_hand_knock_stall(p, size):
    """Cửa buồng vệ sinh trường học (số buồng, chốt báo đỏ/xanh), nắm tay POV gõ cửa + vạch rung."""
    s, c = _begin(size)
    # tường gạch men phía trên + vách ngăn
    c.drawRect(skia.Rect.MakeWH(LW, LH), fill("#cfd8d6"))
    for x in range(0, int(LW), 200):
        c.drawRect(skia.Rect.MakeLTRB(x, 0, x + 6, LH), fill("#b4bfbd"))
    for y in range(0, int(LH), 200):
        c.drawRect(skia.Rect.MakeLTRB(0, y, LW, y + 6), fill("#b4bfbd"))
    door = p.get("door_color", "#e6b9b4")
    dl, dt, dr, db = 640.0, 120.0, 3200.0, 2160.0
    c.drawRect(skia.Rect.MakeLTRB(dl - 140, 0, dl, LH), fill(shade(door, -0.18)))       # vách trái
    c.drawRect(skia.Rect.MakeLTRB(dr, 0, dr + 140, LH), fill(shade(door, -0.18)))
    c.drawRect(skia.Rect.MakeLTRB(dl, dt, dr, db), _lin((dl, 0), (dr, 0), [shade(door, 0.05), door, shade(door, -0.08)]))
    c.drawRect(skia.Rect.MakeLTRB(dl, dt, dr, dt + 26), fill(shade(door, 0.25)))
    c.drawPath(poly([(dl + 200, db), (dl + 900, dt), (dl + 1150, dt), (dl + 450, db)]), fill("#ffffff", 0.08))
    for hy in (dt + 260, db - 500):   # bản lề
        c.drawPath(rrect(dl + 10, hy, dl + 90, hy + 170, 12), fill("#a9b0b6"))
    num = str(p.get("stall_number", "3"))
    c.drawCircle(1920, dt + 280, 120, fill("#f6f2ea"))
    c.drawCircle(1920, dt + 280, 120, stroke(shade(door, -0.35), 10))
    text(c, num, 1920, dt + 340, 170, "#3a3c42", "extrabold", "center")
    # chốt báo có người
    occ = p.get("occupied", True)
    ix, iy = dr - 380, 1080.0
    c.drawPath(rrect(ix - 150, iy - 90, ix + 150, iy + 90, 30), fill("#a9b0b6"))
    c.drawPath(rrect(ix - 120, iy - 60, ix + 120, iy + 60, 22), fill("#d0302a" if occ else "#3a78c2"))
    text(c, p.get("indicator_text", "IN USE" if occ else "VACANT"), ix, iy + 20, 52, "#ffffff", "extrabold", "center",
         max_w=220)
    c.drawPath(rrect(ix - 60, iy + 140, ix + 60, iy + 360, 30), fill("#8a9096"))   # tay nắm
    # nắm tay gõ
    sleeve, skin = p.get("sleeve_color", "#e8b830"), p.get("skin", "#e9b994")
    fx, fy, fa, fs = 1500.0, 1180.0, 32.0, 1.35

    _knock_fist(c, fx, fy, fa, fs, skin, sleeve)
    # vạch rung quanh khớp đốt
    kx, ky = fx + math.sin(math.radians(fa)) * 190 * fs, fy - math.cos(math.radians(fa)) * 190 * fs
    for k, ang in enumerate((-160, -130, -100, -20, 10)):
        a = math.radians(ang)
        c.drawLine(kx + math.cos(a) * 260, ky + math.sin(a) * 260, kx + math.cos(a) * 400, ky + math.sin(a) * 400,
                   stroke("#ffffff", 18, 0.9))
    for k in range(3):
        c.drawArc(skia.Rect.MakeLTRB(kx - 300 - k * 90, ky - 300 - k * 90, kx + 300 + k * 90, ky + 300 + k * 90),
                  -150, 110, False, stroke("#3a3c42", 10, 0.35 - k * 0.08))
    sfx = p.get("sfx", "")
    if sfx:
        c.save()
        c.rotate(-8, 900, 520)
        text(c, sfx, 900, 560, 200, "#ffffff", "extrabold", "center", outline="#3a3c42", outline_w=26)
        c.restore()
    _vignette(c, 0.45)
    return s.makeImageSnapshot()


# =================================================================== tay ma đeo găng nắm cổ tay
def ins_ghost_glove_wrist(p, size):
    """Cẳng tay người (áo mưa vàng) nằm ngang; bàn tay đeo găng trắng từ trên (tay áo trench be) siết cổ tay;
    tay người xoè ngón hoảng sợ; vạch giật mình."""
    s, c = _begin(size)
    c.drawRect(skia.Rect.MakeWH(LW, LH), _rad(LW * 0.45, LH * 0.5, LW * 0.7, [p.get("bg0", "#3a2030"), "#0c0a10"]))
    sleeve, skin = p.get("sleeve_color", "#e8b830"), p.get("skin", "#e9b994")
    coat, glove = p.get("ghost_sleeve", "#c9b48e"), p.get("glove", "#f4f2ee")
    dk = shade(skin, -0.2)
    wy = 1240.0
    # cẳng tay người: vào từ phải, cổ tay tại x≈1500
    c.drawPath(rrect(2600, wy - 300, LW + 200, wy + 300, 120), fill(sleeve))
    c.drawPath(rrect(2560, wy - 320, 2720, wy + 320, 60), fill(shade(sleeve, -0.18)))
    c.drawPath(capsule(2650, wy, 1350, wy + 20, 330, 250), fill(skin))
    c.drawLine(2500, wy + 80, 1700, wy + 70, stroke(dk, 6, 0.4))
    # bàn tay người xoè, chĩa trái
    c.drawPath(smooth([(1400, wy - 150), (1100, wy - 190), (980, wy - 40), (1000, wy + 160), (1200, wy + 190),
                       (1420, wy + 150)]), fill(skin))
    fingers = [((1040, wy - 130), (720, wy - 330), 70), ((1000, wy - 50), (600, wy - 120), 74),
               ((1000, wy + 50), (610, wy + 110), 72), ((1030, wy + 140), (720, wy + 300), 64),
               ((1250, wy - 170), (1100, wy - 430), 82)]
    for (x0, y0), (x1, y1), w in fingers:
        c.drawPath(capsule(x0, y0, x1, y1, w, w * 0.85), fill(skin))
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        c.drawCircle(mx, my, w * 0.3, fill(dk, 0.3))
        c.drawCircle(x1 + (x0 - x1) * 0.1, y1 + (y0 - y1) * 0.1, w * 0.24, fill(shade(skin, 0.45)))
    # tay áo ma từ trên
    gx = 1820.0
    c.drawPath(poly([(gx - 260, -50), (gx + 330, -50), (gx + 250, wy - 520), (gx - 200, wy - 520)]),
               _lin((gx - 260, 0), (gx + 330, 0), [shade(coat, -0.2), coat, shade(coat, -0.3)]))
    c.drawPath(rrect(gx - 230, wy - 600, gx + 270, wy - 470, 40), fill(shade(coat, -0.15)))
    # găng: mu bàn tay đè lên cổ tay
    c.drawPath(capsule(gx + 20, wy - 520, gx + 10, wy - 300, 300, 330), fill(glove))
    back = smooth([(gx - 190, wy - 330), (gx + 210, wy - 340), (gx + 230, wy - 120), (gx + 150, wy + 40),
                   (gx - 150, wy + 40), (gx - 220, wy - 140)])
    c.drawPath(back, fill(glove))
    for k in range(3):   # đường may găng
        x = gx - 90 + k * 90
        c.drawLine(x, wy - 300, x + 10, wy - 60, _dash("#b9b6b0", 6, 16, 12))
    c.drawPath(rrect(gx - 170, wy - 470, gx + 210, wy - 410, 26), fill("#dcd8d0"))    # cổ găng
    # 4 ngón găng quấn xuống qua cổ tay
    for i in range(4):
        x0 = gx - 140 + i * 95
        c.drawPath(capsule(x0, wy - 20, x0 - 20, wy + 220, 92, 84), fill(glove))
        c.drawPath(capsule(x0 - 20, wy + 220, x0 - 70, wy + 300, 84, 76), fill(shade(glove, -0.06)))
        c.drawLine(x0 - 35, wy + 210, x0 - 5, wy + 215, stroke("#b9b6b0", 5))
    c.drawPath(back, stroke("#cfcbc3", 4))
    # vạch giật mình
    for k in range(12):
        a = math.radians(-170 + k * 30)
        c.drawLine(gx + math.cos(a) * 620, wy + math.sin(a) * 560, gx + math.cos(a) * 800, wy + math.sin(a) * 720,
                   stroke("#ffffff", 14, 0.75))
    _vignette(c, 0.5)
    return s.makeImageSnapshot()


# =================================================================== điện thoại + thẻ thông báo ứng dụng
def _app_icon(c, x, y, r, col="#1f9a8a") -> None:
    c.drawPath(rrect(x, y, x + r * 2, y + r * 2, r * 0.45), fill(col))
    c.drawPath(rrect(x + r * 0.45, y + r * 0.7, x + r * 1.55, y + r * 1.5, r * 0.12), fill("#ffffff"))
    c.drawPath(poly([(x + r * 0.45, y + r * 0.7), (x + r, y + r * 0.42), (x + r * 1.55, y + r * 0.7)]), fill("#ffffff"))
    c.drawRect(skia.Rect.MakeLTRB(x + r * 0.9, y + r * 0.7, x + r * 1.1, y + r * 1.5), fill(col))


def _screen_notify(c, sl, st, sr, sb, d: dict) -> None:
    """Ứng dụng giao hàng chung chung (bản đồ + danh sách) + banner thông báo trượt xuống phía trên."""
    from .insertgen import _status_bar
    sw, sh = sr - sl, sb - st
    accent = d.get("app_color", "#1f9a8a")
    c.drawRect(skia.Rect.MakeLTRB(sl, st, sr, sb), fill("#eef1f4"))
    # bản đồ mờ
    mt, mb = st + sh * 0.18, st + sh * 0.58
    c.drawRect(skia.Rect.MakeLTRB(sl, mt, sr, mb), fill("#e3e8df"))
    rng = random.Random(4)
    for _ in range(9):
        x = rng.uniform(sl, sr)
        c.drawLine(x, mt, x + rng.uniform(-80, 80), mb, stroke("#ffffff", sw * 0.025))
    for _ in range(6):
        y = rng.uniform(mt, mb)
        c.drawLine(sl, y, sr, y + rng.uniform(-60, 60), stroke("#ffffff", sw * 0.025))
    route = [(sl + sw * 0.2, mb - sh * 0.05), (sl + sw * 0.35, mt + sh * 0.25), (sl + sw * 0.65, mt + sh * 0.2),
             (sl + sw * 0.78, mt + sh * 0.08)]
    c.drawPath(poly(route, close=False), stroke(accent, sw * 0.018))
    c.drawCircle(*route[0], sw * 0.03, fill(accent))
    c.drawCircle(*route[-1], sw * 0.03, fill("#d0302a"))
    # header ứng dụng
    c.drawRect(skia.Rect.MakeLTRB(sl, st, sr, mt), fill(accent))
    _status_bar(c, sl, st + sh * 0.012, sr, sh * 0.045, d.get("time", "02:38"))
    text(c, d.get("app_name", "DELIVERY"), sl + sw * 0.07, st + sh * 0.135, sh * 0.034, "#ffffff", "extrabold",
         max_w=sw * 0.6)
    c.drawCircle(sr - sw * 0.12, st + sh * 0.12, sh * 0.024, fill("#ffffff", 0.9))
    # danh sách đơn
    y = mb + sh * 0.025
    for i, row in enumerate(d.get("orders") or [["Order #2041", "Noodle shop"], ["Order #2040", "Station exit"]]):
        c.drawPath(rrect(sl + sw * 0.05, y, sr - sw * 0.05, y + sh * 0.1, sw * 0.04), fill("#ffffff"))
        c.drawCircle(sl + sw * 0.14, y + sh * 0.05, sh * 0.025, fill(shade(accent, 0.6)))
        text(c, row[0], sl + sw * 0.22, y + sh * 0.045, sh * 0.024, "#1a1c22", "bold", max_w=sw * 0.6)
        text(c, row[1], sl + sw * 0.22, y + sh * 0.076, sh * 0.019, "#7a7d86", "regular", max_w=sw * 0.6)
        y += sh * 0.12
    # banner thông báo
    n = d.get("notification") or {}
    f = font(sh * 0.022, "regular")
    lines = wrap_text(n.get("text", "Pickup at the old school gate."), f, sw * 0.74)[:2]
    bl, bt, br = sl + sw * 0.04, st + sh * 0.055, sr - sw * 0.04
    bh = sh * (0.1 + 0.028 * len(lines))
    c.drawPath(rrect(bl, bt + sh * 0.01, br, bt + bh + sh * 0.01, sw * 0.05), _blurred("#000000", 0.35, sw * 0.03))
    c.drawPath(rrect(bl, bt, br, bt + bh, sw * 0.05), fill("#ffffff", 0.97))
    ir = sh * 0.026
    _app_icon(c, bl + sw * 0.04, bt + sh * 0.022, ir, accent)
    text(c, n.get("app", d.get("app_name", "DELIVERY")).upper(), bl + sw * 0.06 + ir * 2, bt + sh * 0.046, sh * 0.017,
         "#5a5d66", "semibold")
    text(c, n.get("when", "now"), br - sw * 0.05, bt + sh * 0.046, sh * 0.017, "#5a5d66", "regular", "right")
    text(c, n.get("title", "New order"), bl + sw * 0.05, bt + sh * 0.092, sh * 0.026, "#111216", "bold", max_w=sw * 0.8)
    for i, ln in enumerate(lines):
        c.drawString(ln, bl + sw * 0.05, bt + sh * (0.124 + i * 0.028), f, fill("#22252b"))


def ins_phone_app_notification(p, size):
    """Điện thoại cầm tay, ứng dụng giao hàng chung chung; banner thông báo trên màn + thẻ thông báo phóng to bên trái."""
    from .insertgen_batch2 import _phone_in_hand
    n = p.get("notification") or {}
    accent = p.get("app_color", "#1f9a8a")

    def side(c):
        if not p.get("card", True):
            return
        l, t, w = 260.0, 700.0, 1500.0
        f = font(64, "regular")
        lines = wrap_text(n.get("text", "Pickup at the old school gate."), f, w - 160)[:3]
        h = 330 + len(lines) * 84
        card = rrect(l, t, l + w, t + h, 48)
        _shadow(c, card, 40, 24, 0.55)
        c.drawPath(card, fill("#fbfbfc"))
        _app_icon(c, l + 70, t + 60, 56, accent)
        text(c, n.get("app", p.get("app_name", "DELIVERY")).upper(), l + 220, t + 132, 46, "#5a5d66", "bold")
        text(c, n.get("when", "now"), l + w - 70, t + 132, 46, "#5a5d66", "regular", "right")
        text(c, n.get("title", "New order"), l + 70, t + 260, 84, "#111216", "extrabold", max_w=w - 140)
        for i, ln in enumerate(lines):
            c.drawString(ln, l + 70, t + 350 + i * 84, f, fill("#22252b"))

    return _phone_in_hand("notify", p, size, side)


# =================================================================== đèn đường + trăng
def ins_streetlight_moon(p, size):
    """Nhìn ngước lên: trăng tròn lớn sau mây mỏng, đầu đèn đường cong phát sáng ấm, dây điện, côn trùng bay."""
    s, c = _begin(size)
    c.drawRect(skia.Rect.MakeWH(LW, LH), _lin((0, 0), (0, LH), [p.get("sky0", "#0d1330"), p.get("sky1", "#2a2f5a"),
                                                                p.get("sky2", "#4a3a6a")], [0, 0.6, 1]))
    rng = random.Random(7)
    for _ in range(160):
        c.drawCircle(rng.uniform(0, LW), rng.uniform(0, LH * 0.8), rng.uniform(2, 5), fill("#ffffff", rng.uniform(0.3, 0.9)))
    mx, my, mr = float(p.get("moon_x", 2700)), float(p.get("moon_y", 760)), 460.0
    _soft_glow(c, mx, my, mr * 3.2, "#f1ead2", 0.35)
    c.drawCircle(mx, my, mr, _rad(mx - mr * 0.3, my - mr * 0.3, mr * 1.4, ["#fbf6e4", "#f1ead2", "#d9cfae"]))
    for k in range(9):   # hố trăng
        a = rng.uniform(0, math.tau)
        rr = rng.uniform(0, mr * 0.7)
        cr = rng.uniform(30, 90)
        c.drawCircle(mx + math.cos(a) * rr, my + math.sin(a) * rr, cr, fill("#cfc5a6", 0.5))
    for k in range(3):   # mây mỏng ngang trăng
        y = my + (k - 1) * 260 + 80
        c.drawPath(oval(mx + (k - 1) * 300, y, 900, 70), _blurred("#5a5a80", 0.55, 30))
    # dây điện
    for k in range(3):
        pth = skia.Path()
        pth.moveTo(-50, 300 + k * 140)
        pth.quadTo(1900, 760 + k * 160, LW + 50, 220 + k * 130)
        c.drawPath(pth, stroke("#0a0c18", 9))
    # cột đèn cong
    pole = "#1a1d2a"
    pth = skia.Path()
    pth.moveTo(520, LH + 50)
    pth.lineTo(640, 900)
    pth.quadTo(700, 420, 1200, 380)
    pth.lineTo(1420, 400)
    c.drawPath(pth, stroke(pole, 70))
    c.drawPath(pth, stroke("#3a3f58", 16, 0.6))
    hx, hy = 1520.0, 420.0
    head = poly([(hx - 260, hy - 70), (hx + 220, hy - 40), (hx + 260, hy + 40), (hx - 220, hy + 40)])
    c.drawPath(head, fill(pole))
    c.drawPath(oval(hx, hy + 48, 220, 34), fill("#fff6d8"))
    _cone(c, hx, hy + 60, 420, 2200, LH - hy, "#ffe9a8", 0.28)
    _soft_glow(c, hx, hy + 60, 700, "#ffe2a0", 0.7)
    # côn trùng quanh đèn
    if p.get("moths", True):
        for _ in range(14):
            a = rng.uniform(0, math.tau)
            rr = rng.uniform(150, 520)
            x, y = hx + math.cos(a) * rr, hy + 120 + math.sin(a) * rr * 0.6
            c.drawPath(oval(x - 8, y, 9, 5), fill("#2a2420", 0.8))
            c.drawPath(oval(x + 8, y, 9, 5), fill("#2a2420", 0.8))
            c.drawLine(x - 20, y - 6, x + 20, y + 6, stroke("#fff6d8", 2, 0.3))
    _vignette(c, 0.5)
    return s.makeImageSnapshot()


# =================================================================== đăng ký
SCREENS = {"notify": _screen_notify}

INSERTS = {
    "charm_pouch": ins_charm_pouch,
    "charm_pouch_hand": ins_charm_pouch_hand,
    "charm_pouch_pass": ins_charm_pouch_pass,
    "vending_pair": ins_vending_pair,
    "candy_pack_asphalt": ins_candy_pack_asphalt,
    "class_photo_table": ins_class_photo_table,
    "painting_streetlamp": ins_painting_streetlamp,
    "rail_map_pin": ins_rail_map_pin,
    "hand_knock_stall": ins_hand_knock_stall,
    "ghost_glove_wrist": ins_ghost_glove_wrist,
    "phone_app_notification": ins_phone_app_notification,
    "streetlight_moon": ins_streetlight_moon,
}

TAGS = {
    "charm_pouch": ["bùa hộ mệnh", "túi bùa", "chuỗi hạt", "thắt nút", "charm", "amulet", "talisman", "knotted beads"],
    "charm_pouch_hand": ["bùa hộ mệnh", "cầm bùa", "tay", "chuỗi hạt", "charm", "amulet", "hand", "holding"],
    "charm_pouch_pass": ["trao bùa", "đưa bùa", "hai bàn tay", "bùa hộ mệnh", "charm", "passing", "giving", "hands"],
    "vending_pair": ["máy bán hàng tự động", "nóng lạnh", "đồ uống", "ban đêm", "vending machine", "drinks", "hot",
                     "cold"],
    "candy_pack_asphalt": ["gói kẹo", "kẹo miễn phí", "kẹo rơi", "mặt đường", "candy", "free candy", "sweets",
                           "asphalt"],
    "class_photo_table": ["ảnh lớp", "ảnh cũ", "kỷ yếu", "học sinh", "class photo", "old photo", "school", "yearbook"],
    "painting_streetlamp": ["bức tranh", "khung tranh", "đèn đường", "bóng người", "painting", "framed painting",
                            "streetlamp", "lone figure"],
    "rail_map_pin": ["bản đồ", "tàu điện", "ghim đỏ", "nhà ga", "rail map", "subway", "train", "pin"],
    "hand_knock_stall": ["gõ cửa", "nhà vệ sinh", "buồng vệ sinh", "trường học", "knock", "toilet stall", "door",
                         "school toilet"],
    "ghost_glove_wrist": ["tay ma", "găng tay", "nắm cổ tay", "kinh dị", "ghost hand", "glove", "wrist", "grab"],
    "phone_app_notification": ["điện thoại", "thông báo", "ứng dụng", "giao hàng", "phone", "notification", "app",
                               "delivery"],
    "streetlight_moon": ["đèn đường", "trăng", "ban đêm", "dây điện", "streetlight", "moon", "night sky", "street lamp"],
}
# snake_case props; tránh prop chung đã gán cho ảnh chèn gốc ("phone", "map", "clock", "coin"...).
PROPS = {
    "charm_pouch": ["charm", "charm_pouch", "amulet", "omamori", "knotted_beads"],
    "charm_pouch_hand": ["charm_in_hand", "holding_charm", "amulet_in_hand"],
    "charm_pouch_pass": ["charm_pass", "giving_charm", "passing_charm"],
    "vending_pair": ["vending_machine", "vending_machines", "drink_machine"],
    "candy_pack_asphalt": ["candy", "candy_pack", "free_candy", "sweets"],
    "class_photo_table": ["class_photo", "school_photo", "group_photo"],
    "painting_streetlamp": ["painting", "framed_painting", "streetlamp_painting"],
    "rail_map_pin": ["rail_map", "subway_map", "train_map", "map_pin"],
    "hand_knock_stall": ["knock", "knocking", "stall_door", "toilet_door"],
    "ghost_glove_wrist": ["ghost_glove", "gloved_hand", "grabbed_wrist", "wrist_grab"],
    "phone_app_notification": ["app_notification", "phone_notification_app", "delivery_app", "order_notification"],
    "streetlight_moon": ["streetlight", "street_lamp", "moon", "full_moon"],
}
