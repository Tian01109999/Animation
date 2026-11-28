"""Batch-7 library locations (provenance 'procedural_library'): old riverside kingdom under siege (time-travel story).

Original flat-vector drawings in skia (no tracing): boat-building shed under a stilt house (hazy day / lantern night),
deck at the shed at dusk with log benches, brick city wall with palisade and smoke columns, digging site at the foot
of the wall (+ smoking glowing hole), vaulted brick cellar with barred window and stairs (+ lit torch), timber-framed
tunnel with a fire at the end (+ blaze), ruined temple ground with a stone head in tree roots (dusk / storm), old
riverside market of thatched stilt houses, white prang temple (hazy day / dusk), village yard with a stall hut and a
stilt house. No baked text at all (Vietnamese only in search tags).

Registered into locgen.LIBRARY_SCENES / LIBRARY_TAGS at the end of locgen (like batch 5).
"""
from __future__ import annotations

import math
import random

import skia

from .locgen import H, W, Scene, _R, _rain, _vignette, glow, lin_paint, new_surface, rad_paint, vgrad
from .skutil import fill, oval, poly, rrect, shade, stroke


def _flat_slot(x, y, scale, **kw) -> dict:
    return {"x": round(x), "y": round(y), "scale": round(scale, 3), **kw}


def _blur(col, a, sigma) -> skia.Paint:
    p = fill(col, a)
    p.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, sigma))
    return p


# =================================================================== shared props
def _bricks(c, l, t, r, b, bw, bh, base, mortar, seed=1, var=0.09, gap=None) -> None:
    rng = random.Random(seed)
    c.save()
    c.clipRect(_R(l, t, r, b))
    c.drawRect(_R(l, t, r, b), fill(mortar))
    g = gap if gap is not None else max(3.0, bh * 0.14)
    y, row = t, 0
    while y < b:
        x = l - (row % 2) * bw / 2
        while x < r:
            c.drawRect(_R(x + g / 2, y + g / 2, x + bw - g / 2, y + bh - g / 2), fill(shade(base, rng.uniform(-var, var))))
            if rng.random() < 0.05:
                c.drawPath(poly([(x + bw * 0.6, y + g), (x + bw - g, y + g), (x + bw - g, y + bh * 0.5)]), fill(mortar, 0.7))
            x += bw
        y += bh
        row += 1
    c.restore()


def _arch_bricks(c, cx, cy, rx0, rx1, ry_scale, base, mortar, seed=3, n_rings=9, a0=180, a1=360) -> None:
    """Barrel-vault bricks: rings of small rotated bricks around (cx, cy), radii rx0..rx1 (y squashed by ry_scale)."""
    rng = random.Random(seed)
    for i in range(n_rings):
        rr = rx0 + (rx1 - rx0) * (i + 0.5) / n_rings
        bl = (rx1 - rx0) / n_rings * 0.86
        n = max(12, int(math.pi * rr / (bl * 2.2)))
        off = (i % 2) * 0.5
        for k in range(n):
            ang = math.radians(a0 + (a1 - a0) * (k + off) / n)
            x, y = cx + math.cos(ang) * rr, cy + math.sin(ang) * rr * ry_scale
            c.save()
            c.translate(x, y)
            c.rotate(math.degrees(ang) + 90)
            c.drawRect(_R(-bl * 1.05, -bl * 0.42, bl * 1.05, bl * 0.42), fill(mortar))
            c.drawRect(_R(-bl * 0.98, -bl * 0.36, bl * 0.98, bl * 0.36), fill(shade(base, rng.uniform(-0.1, 0.1))))
            c.restore()


def _stilt_house(c, x, gy, w, body_h, stilt_h, roof_h, wall="#9a7a58", roof="#b49a74", dark="#5a4430",
                 posts=6, door=True, ladder=False, thatch=True, window=True) -> None:
    bb = gy - stilt_h
    bt = bb - body_h
    for i in range(posts):
        px = x + w * 0.04 + i * w * 0.92 / (posts - 1)
        c.drawRect(_R(px - w * 0.013, bb, px + w * 0.013, gy), fill(dark))
        c.drawPath(oval(px, gy, w * 0.03, w * 0.006), fill("#000000", 0.15))
    c.drawRect(_R(x - w * 0.02, bb - body_h * 0.06, x + w * 1.02, bb + body_h * 0.04), fill(shade(wall, -0.25)))
    c.drawRect(_R(x, bt, x + w, bb), fill(wall))
    n = int(w / 42) + 1
    for k in range(1, n):
        xx = x + k * w / n
        c.drawLine(xx, bt, xx, bb, stroke(shade(wall, -0.12), 3))
    c.drawLine(x, bt + body_h * 0.45, x + w, bt + body_h * 0.45, stroke(shade(wall, -0.18), 5))
    if door:
        c.drawRect(_R(x + w * 0.62, bt + body_h * 0.18, x + w * 0.74, bb - body_h * 0.02), fill("#2e2218"))
    if window:
        c.drawRect(_R(x + w * 0.18, bt + body_h * 0.22, x + w * 0.27, bt + body_h * 0.48), fill("#3a2c20"))
    c.drawPath(poly([(x - w * 0.1, bt + 4), (x + w * 0.5, bt - roof_h), (x + w * 1.1, bt + 4)]), fill(roof))
    if thatch:
        for k in range(1, 9):
            f = k / 9
            y = bt - roof_h * (1 - f)
            hw = w * 0.6 * f
            c.drawLine(x + w * 0.5 - hw, y, x + w * 0.5 + hw, y, stroke(shade(roof, -0.12), 4, 0.8))
    c.drawPath(poly([(x - w * 0.1, bt + 4), (x + w * 0.5, bt - roof_h), (x + w * 1.1, bt + 4)]),
               stroke(shade(roof, -0.3), 6))
    if ladder:
        lx0, lx1 = x + w * 0.66, x + w * 0.8
        c.drawLine(lx0, bb, lx0 + w * 0.12, gy, stroke(dark, 12))
        c.drawLine(lx1, bb, lx1 + w * 0.12, gy, stroke(dark, 12))
        for k in range(1, 7):
            f = k / 7
            c.drawLine(lx0 + w * 0.12 * f, bb + (gy - bb) * f, lx1 + w * 0.12 * f, bb + (gy - bb) * f, stroke(dark, 9))


def _tree(c, x, y, r, col, seed=1, n=6) -> None:
    rng = random.Random(seed)
    for _ in range(n):
        c.drawCircle(x + rng.uniform(-r, r), y + rng.uniform(-r * 0.5, r * 0.4), r * rng.uniform(0.5, 0.8), fill(col))


def _palm(c, x, gy, h, col="#5a6a40", trunk="#6a5a40") -> None:
    c.drawLine(x, gy, x + h * 0.03, gy - h, stroke(trunk, max(6.0, h * 0.03)))
    cx, cy = x + h * 0.03, gy - h
    for a in range(0, 360, 30):
        rd = math.radians(a)
        c.drawLine(cx, cy, cx + math.cos(rd) * h * 0.18, cy + math.sin(rd) * h * 0.12 + h * 0.03, stroke(col, max(4.0, h * 0.025)))
    c.drawCircle(cx, cy, h * 0.05, fill(shade(col, -0.2)))


def _hull(c, l, r, top, depth, col="#8a6a48", tilt=0.0) -> skia.Path:
    L = r - l
    p = skia.Path()
    p.moveTo(l, top - depth * 0.35)
    p.quadTo(l + L * 0.08, top + depth * 0.02, l + L * 0.2, top)
    p.lineTo(r - L * 0.22, top - tilt)
    p.quadTo(r - L * 0.06, top - tilt, r, top - depth * 0.6 - tilt)
    p.quadTo(r - L * 0.07, top + depth * 0.85, r - L * 0.26, top + depth)
    p.lineTo(l + L * 0.2, top + depth)
    p.quadTo(l + L * 0.04, top + depth * 0.78, l, top - depth * 0.35)
    p.close()
    c.drawPath(p, lin_paint((0, top), (0, top + depth), [shade(col, 0.1), col, shade(col, -0.25)]))
    c.save()
    c.clipPath(p, doAntiAlias=True)
    for f in (0.3, 0.55, 0.78):
        c.drawLine(l, top + depth * f, r, top + depth * f - tilt * (1 - f), stroke(shade(col, -0.18), 4, 0.7))
    c.restore()
    c.drawLine(l + L * 0.2, top + 6, r - L * 0.22, top + 6 - tilt, stroke(shade(col, 0.3), 12))
    return p


def _log(c, x, y, L, R, ang, col="#6a4a30") -> None:
    c.save()
    c.translate(x, y)
    c.rotate(ang)
    c.drawRect(_R(0, -R, L, R), lin_paint((0, -R), (0, R), [shade(col, 0.15), col, shade(col, -0.3)]))
    for k in (-0.4, 0.1, 0.5):
        c.drawLine(L * 0.1, R * k, L * 0.8, R * k, stroke(shade(col, -0.25), 4))
    c.drawPath(oval(L, 0, R * 0.55, R), fill(shade(col, 0.25)))
    for f in (0.75, 0.45):
        c.drawPath(oval(L, 0, R * 0.55 * f, R * f), stroke(shade(col, -0.1), 4))
    c.restore()


def _gong(c, cx, top, r, frame_w, frame_h, wood="#6a4a30", bronze="#b08848", frame=True) -> None:
    gy = top + frame_h
    if frame:
        for sx in (-1, 1):
            c.drawRect(_R(cx + sx * frame_w / 2 - 22, top, cx + sx * frame_w / 2 + 22, gy), fill(wood))
        c.drawPath(rrect(cx - frame_w / 2 - 50, top - 20, cx + frame_w / 2 + 50, top + 30, 20), fill(shade(wood, 0.1)))
    gcy = top + 60 + r * 1.6
    for sx in (-0.35, 0.35):
        c.drawLine(cx + sx * r, top + 30, cx + sx * r * 0.8, gcy - r * 0.9, stroke("#d8c090", 6))
    c.drawCircle(cx, gcy, r, rad_paint(cx - r * 0.3, gcy - r * 0.3, r * 1.3, [shade(bronze, 0.25), bronze, shade(bronze, -0.4)]))
    c.drawCircle(cx, gcy, r * 0.8, stroke(shade(bronze, 0.3), max(2.0, r * 0.03)))
    c.drawCircle(cx, gcy, r * 0.3, rad_paint(cx - r * 0.08, gcy - r * 0.08, r * 0.35, [shade(bronze, 0.2), shade(bronze, -0.35)]))
    c.drawPath(oval(cx - r * 0.05, gcy - r * 0.08, r * 0.12, r * 0.07), fill("#fff0c0", 0.8))


def _shavings(c, l, t, r, b, n, seed, col="#d8c49a", a=0.75) -> None:
    rng = random.Random(seed)
    for _ in range(n):
        x, y = rng.uniform(l, r), rng.uniform(t, b)
        s = rng.uniform(10, 26) * (0.6 + (y - t) / max(1, b - t))
        st = rng.uniform(0, 360)
        c.drawArc(_R(x - s, y - s * 0.6, x + s, y + s * 0.6), st, rng.uniform(120, 260), False, stroke(col, max(2.0, s * 0.18), a))


def _torch(c, x, y, sc, lit=True) -> None:
    c.drawLine(x, y + 260 * sc, x - 20 * sc, y + 520 * sc, stroke("#3a2618", 14 * sc))
    c.drawLine(x + 12 * sc, y + 10 * sc, x - 10 * sc, y + 300 * sc, stroke("#a07a48", 26 * sc))
    for k in range(3):
        c.drawLine(x - 14 * sc, y + (60 + k * 30) * sc, x + 18 * sc, y + (56 + k * 30) * sc, stroke("#5a3a20", 8 * sc))
    if lit:
        glow(c, x, y - 60 * sc, 520 * sc, "#ffb860", 0.55)
        p = skia.Path()
        p.moveTo(x, y - 170 * sc)
        p.cubicTo(x + 60 * sc, y - 80 * sc, x + 50 * sc, y + 10 * sc, x, y + 20 * sc)
        p.cubicTo(x - 50 * sc, y + 10 * sc, x - 60 * sc, y - 80 * sc, x, y - 170 * sc)
        c.drawPath(p, fill("#ff9a3a"))
        c.drawPath(oval(x, y - 25 * sc, 22 * sc, 40 * sc), fill("#ffe8a0"))


def _smoke_column(c, x, y0, y1, w, seed, col="#5a5652", a=0.55) -> None:
    rng = random.Random(seed)
    n = 14
    for k in range(n):
        f = k / (n - 1)
        yy = y0 + (y1 - y0) * f
        ww = w * (0.6 + f * 1.2)
        c.drawCircle(x + math.sin(f * 5 + seed) * w * 0.6 * f, yy, ww * rng.uniform(0.8, 1.1), _blur(col, a * (1 - f * 0.5), ww * 0.35))


def _grass(c, l, r, y0, y1, n, seed, col="#6a6a3a", a=0.8) -> None:
    rng = random.Random(seed)
    for _ in range(n):
        x, y = rng.uniform(l, r), rng.uniform(y0, y1)
        h = rng.uniform(30, 90) * (0.6 + (y - y0) / max(1, y1 - y0))
        for d in (-0.4, 0.0, 0.35):
            c.drawLine(x, y, x + h * d, y - h, stroke(col, max(2.0, h * 0.06), a))


def _basket(c, cx, by, w, h, col="#c8a870") -> None:
    c.drawPath(poly([(cx - w / 2, by - h), (cx + w / 2, by - h), (cx + w * 0.42, by), (cx - w * 0.42, by)]), fill(col))
    for k in range(1, 6):
        y = by - h * k / 6
        c.drawLine(cx - w * 0.45, y, cx + w * 0.45, y, stroke(shade(col, -0.2), 3))
    for k in range(1, 8):
        x = cx - w / 2 + w * k / 8
        c.drawLine(x, by - h, x - (x - cx) * 0.16, by, stroke(shade(col, -0.2), 3))
    c.drawPath(oval(cx, by - h, w / 2, h * 0.08), fill(shade(col, -0.35)))
    c.drawArc(_R(cx - w * 0.45, by - h - h * 0.9, cx + w * 0.45, by - h + h * 0.4), 180, 180, False, stroke(shade(col, -0.1), 6))


def _hoe(c, x, y, L, ang, blade="#8a8e94", handle="#8a6a44") -> None:
    c.save()
    c.translate(x, y)
    c.rotate(ang)
    c.drawLine(0, 0, 0, -L, stroke(handle, max(6.0, L * 0.02)))
    c.drawPath(poly([(0, -L), (L * 0.2, -L + L * 0.02), (L * 0.22, -L + L * 0.16), (L * 0.02, -L + L * 0.12)]), fill(blade))
    c.restore()


def _mound(c, cx, by, w, h, col="#9a7a52") -> None:
    p = skia.Path()
    p.moveTo(cx - w / 2, by)
    p.quadTo(cx - w * 0.1, by - h * 1.3, cx + w / 2, by)
    p.close()
    c.drawPath(p, lin_paint((0, by - h), (0, by), [shade(col, 0.12), shade(col, -0.1)]))


def _prang(c, cx, gy, w, h, col="#efeae2", shade_col="#c8c0b4", door=True) -> None:
    """White prang tower: stepped base, stairs, niche door, tiered corncob top with petal antefixes, spire."""
    for k in range(3):
        bw = w * (1.5 - k * 0.14)
        y0 = gy - h * 0.035 * (k + 1)
        c.drawRect(_R(cx - bw / 2, y0, cx + bw / 2, y0 + h * 0.036), fill(shade(col, -0.04 * k)))
        c.drawLine(cx - bw / 2, y0, cx + bw / 2, y0, stroke(shade_col, 4))
    by = gy - h * 0.105
    bt = by - h * 0.36
    c.drawPath(poly([(cx - w * 0.5, by), (cx + w * 0.5, by), (cx + w * 0.4, bt), (cx - w * 0.4, bt)]), fill(col))
    for f in (0.25, 0.75):
        xx = cx - w * 0.5 + w * f
        c.drawLine(xx, by, xx + (cx - xx) * 0.2, bt, stroke(shade_col, 4))
    if door:
        dw, dh = w * 0.13, h * 0.16
        p = skia.Path()
        p.moveTo(cx - dw / 2, bt + h * 0.1 + dh)
        p.lineTo(cx - dw / 2, bt + h * 0.1 + dw * 0.5)
        p.quadTo(cx, bt + h * 0.1 - dw * 0.3, cx + dw / 2, bt + h * 0.1 + dw * 0.5)
        p.lineTo(cx + dw / 2, bt + h * 0.1 + dh)
        p.close()
        c.drawPath(p, fill("#4a3428"))
        c.drawPath(poly([(cx, bt + h * 0.14), (cx + dw * 0.18, bt + h * 0.19), (cx - dw * 0.18, bt + h * 0.19)]), fill("#d8a840"))
        sw_ = w * 0.13
        c.drawRect(_R(cx - sw_ / 2, bt + h * 0.1 + dh, cx + sw_ / 2, gy), fill(shade(col, -0.06)))
        for k in range(14):
            y = bt + h * 0.1 + dh + (gy - bt - h * 0.1 - dh) * k / 14
            c.drawLine(cx - sw_ / 2, y, cx + sw_ / 2, y, stroke(shade_col, 3))
    y = bt
    tw = w * 0.8
    for k in range(6):
        th = h * 0.075
        c.drawRect(_R(cx - tw / 2, y - th, cx + tw / 2, y), fill(shade(col, -0.02 * (k % 2))))
        c.drawLine(cx - tw / 2, y, cx + tw / 2, y, stroke(shade_col, 4))
        npet = 7
        for j in range(npet):
            px = cx - tw / 2 + tw * (j + 0.5) / npet
            pc = shade_col if j in (0, npet - 1) else col
            c.drawPath(poly([(px - tw * 0.045, y - th), (px, y - th - h * 0.05), (px + tw * 0.045, y - th)]), fill(pc))
            c.drawPath(poly([(px - tw * 0.03, y - th * 0.15), (px, y - th * 0.85), (px + tw * 0.03, y - th * 0.15)]),
                       stroke(shade_col, 3))
        y -= th
        tw *= 0.82
    c.drawLine(cx, y, cx, y - h * 0.08, stroke(shade_col, max(4.0, w * 0.012)))


def _chedi(c, cx, gy, w, h, col="#ece6dc", line="#c4bcb0") -> None:
    for k in range(3):
        bw = w * (1 - k * 0.14)
        y0 = gy - h * 0.06 * (k + 1)
        c.drawRect(_R(cx - bw / 2, y0, cx + bw / 2, y0 + h * 0.06), fill(shade(col, -0.03 * k)))
        c.drawLine(cx - bw / 2, y0, cx + bw / 2, y0, stroke(line, 3))
    bb = gy - h * 0.18
    p = skia.Path()
    p.moveTo(cx - w * 0.36, bb)
    p.cubicTo(cx - w * 0.36, bb - h * 0.3, cx - w * 0.14, bb - h * 0.36, cx, bb - h * 0.37)
    p.cubicTo(cx + w * 0.14, bb - h * 0.36, cx + w * 0.36, bb - h * 0.3, cx + w * 0.36, bb)
    p.close()
    c.drawPath(p, fill(col))
    c.drawPath(p, stroke(line, 3))
    y = bb - h * 0.37
    for k in range(6):
        rw = w * (0.12 - k * 0.012)
        c.drawRect(_R(cx - rw, y - h * 0.03, cx + rw, y), fill(shade(col, -0.02 * (k % 2))))
        y -= h * 0.03
    c.drawPath(poly([(cx - w * 0.04, y), (cx, gy - h), (cx + w * 0.04, y)]), fill(col))


def _vihara(c, x, gy, w, stilt, body_h, roof="#c8683a", wall="#a07a58") -> None:
    _stilt_house(c, x, gy, w, body_h, stilt, 0, wall=wall, roof=roof, posts=8, door=True, thatch=False)
    bt = gy - stilt - body_h
    for k, (dx, rh) in enumerate(((0.0, w * 0.75), (w * 0.12, w * 0.6))):
        l, r = x + dx - w * 0.06, x + w * 0.52 + dx * 0.2
        c.drawPath(poly([(l, bt + 10), (l + w * 0.1, bt - rh), (r, bt - rh), (r + w * 0.04, bt + 10)]),
                   fill(shade(roof, -0.08 * k)))
        for j in range(1, 10):
            yy = bt - rh * j / 10
            c.drawLine(l + w * 0.1 * j / 10, yy, r + w * 0.04 * (1 - j / 10), yy, stroke(shade(roof, -0.18), 3))
        c.drawLine(l + w * 0.1, bt - rh, l + w * 0.13, bt - rh - w * 0.06, stroke("#d8b050", 6))
        c.drawLine(r, bt - rh, r + w * 0.02, bt - rh - w * 0.06, stroke("#d8b050", 6))
    c.drawPath(poly([(x + w * 0.5, bt + 10), (x + w * 0.5, bt - w * 0.75), (x + w * 1.06, bt + 10)]), fill(shade(roof, -0.15)))


# =================================================================== 1. boat-building shed under a stilt house
def scene_xuong_thuyen_nha_san(tod: str) -> Scene:
    night = tod == "night"
    s = new_surface()
    c = s.getCanvas()
    if night:
        vgrad(c, 0, 0, W, 1300, ["#18223a", "#22304c", "#2a3a58"])
    else:
        vgrad(c, 0, 0, W, 1300, ["#e4e2d6", "#ecebe2", "#dcdccf"])
    far = "#2a384c" if night else "#a8b6a0"
    house = "#2c3446" if night else "#d8cfc0"
    for k, x in enumerate((-80, 700, 1500, 2350, 3150)):
        _tree(c, x + 260, 760, 260, far, seed=k + 4)
    for k, x in enumerate((150, 950, 1750, 2600, 3350)):
        _stilt_house(c, x, 1060, 380, 200, 180, 170, wall=house, roof=shade(house, 0.06), dark=shade(house, -0.2),
                     posts=5, door=False, window=True)
    vgrad(c, 0, 1040, W, 1300, ["#30405a", "#24324a"] if night else ["#cdd2c8", "#bfc6bc"])
    rng = random.Random(3)
    for _ in range(40):
        x, y = rng.uniform(0, W), rng.uniform(1080, 1290)
        c.drawLine(x, y, x + rng.uniform(60, 200), y, stroke("#5a6a88" if night else "#e8ece4", 4, 0.6))
    vgrad(c, 0, 1280, W, H, ["#4a3e32", "#2e261e"] if night else ["#9a8466", "#6e5a42"])
    # ceiling joists (converging) + main beam
    c.save()
    c.clipRect(_R(0, 0, W, 330))
    c.drawRect(_R(0, 0, W, 330), fill("#2a2018" if night else "#6a503a"))
    for k in range(-14, 15):
        c.drawLine(W / 2 + k * 70, 330, W / 2 + k * 330, -40, stroke("#3a2c20" if night else "#836448", 30))
    for y in (60, 150, 240):
        c.drawLine(0, y, W, y, stroke("#1e1812" if night else "#54402e", 10, 0.6))
    c.restore()
    c.drawRect(_R(0, 320, W, 400), fill("#30241a" if night else "#5a4230"))
    # far pillars + gong
    for x in (560, 1260, 2560, 3050):
        c.drawRect(_R(x - 40, 400, x + 40, 1290), fill("#3a2c20" if night else "#6e543c"))
    _gong(c, 1960, 620, 85, 420, 690, wood="#3e2e20" if night else "#6a4a30")
    c.drawRect(_R(400, 1180, 560, 1300), fill("#3a2c20" if night else "#6a5038"))
    _hull(c, 900, 2150, 1210, 70, "#4a3a2c" if night else "#8a7458")
    # big hull on log rollers
    _log(c, 260, 1660, 420, 70, -18, "#3e2e22" if night else "#6a4a30")
    _log(c, 2900, 1520, 420, 70, 22, "#3e2e22" if night else "#6a4a30")
    _hull(c, 40, 3640, 1140, 420, "#5a4632" if night else "#9a7a56", tilt=60)
    _shavings(c, 0, 1640, W, H, 260, 7, "#a08a68" if night else "#d8c49a")
    # near pillars
    for x, w_ in ((90, 120), (1500, 110), (3560, 130)):
        c.drawRect(_R(x - w_ / 2, 330, x + w_ / 2, H), lin_paint((x - w_ / 2, 0), (x + w_ / 2, 0),
                                                                   ["#2a1e14", "#3a2a1c", "#22180e"] if night else ["#4a3624", "#64492f", "#3e2c1c"]))
        c.drawRect(_R(x - w_ / 2, 1500, x + w_ / 2, 1520), fill("#000000", 0.25))
    if night:
        _torch(c, 3350, 560, 0.8, lit=True)
        glow(c, 2700, 900, 1600, "#ffc070", 0.25)
        _vignette(c, 0.7)
    else:
        c.drawRect(_R(0, 0, W, H), fill("#f4efe2", 0.12))
        _vignette(c, 0.45)
    slots = {"center": _flat_slot(1900, 1760, 0.95), "left": _flat_slot(900, 1760, 0.95),
             "right": _flat_slot(2800, 1760, 0.95)}
    return Scene(None, s.makeImageSnapshot(), slots=slots, floor_y=1760)


# =================================================================== 2. deck at the shed at dusk with log benches
def scene_san_xuong_thuyen_hoang_hon(tod: str) -> Scene:
    s = new_surface()
    c = s.getCanvas()
    vgrad(c, 0, 0, W, 700, ["#a88a90", "#d8aa94", "#e6c0a0"])
    for x, h in ((520, 340), (900, 260), (1300, 420), (2100, 300), (2700, 380), (3300, 280)):
        c.drawPath(poly([(x - 70, 640), (x, 640 - h), (x + 70, 640)]), fill("#e8cdb4", 0.75))
    for x in (300, 1700, 3000):
        c.drawPath(poly([(x - 260, 640), (x, 470), (x + 260, 640)]), fill("#d4a890", 0.7))
    c.drawRect(_R(0, 560, W, 1060), lin_paint((0, 560), (0, 1060), ["#c8a690", "#b89480"]))
    c.drawLine(0, 560, W, 560, stroke("#a8806c", 10))
    vgrad(c, 0, 1040, W, 1520, ["#8a6a5e", "#7a5c52"])
    rng = random.Random(5)
    for _ in range(140):
        x, y = rng.uniform(0, W), rng.uniform(1080, 1500)
        c.drawPath(oval(x, y, 14, 7), fill("#e8d8c0", 0.7))
    _grass(c, 0, W, 1060, 1500, 40, 2, "#c8a860", 0.7)
    for x, w_ in ((180, 110), (360, 70), (500, 80), (900, 90), (1020, 60), (1560, 90), (1960, 70), (3080, 100)):
        c.drawRect(_R(x - w_ / 2, 0, x + w_ / 2, 1300 + w_), fill("#6a4c48"))
        c.drawPath(oval(x, 1300 + w_, w_ * 0.8, 18), fill("#4a3430", 0.6))
    c.drawRect(_R(0, 0, W, 60), fill("#5a3e3a"))
    c.drawPath(rrect(520, 940, 1380, 990, 10), fill("#e6d6c4"))
    for x in (580, 1320):
        c.drawRect(_R(x - 20, 990, x + 20, 1200), fill("#d4c0aa"))
    c.drawPath(oval(1600, 1120, 130, 26), stroke("#e8dcc8", 10))
    _hoe(c, 2900, 1170, 460, 20, "#9a9498", "#8a6a50")
    c.save()
    c.translate(3700, 900)
    c.drawPath(oval(0, 0, 520, 140), fill("#a07c66", 0.9))
    c.restore()
    vgrad(c, 0, 1480, W, H, ["#6a4a3a", "#4a3226"])
    for y in range(1500, H, 26):
        c.drawLine(0, y, W, y, stroke("#3a261c", 6, 0.6))
    c.drawRect(_R(0, 1470, W, 1500), fill("#7a5644"))
    _log(c, 760, 1700, 1100, 120, 0, "#8a5c3e")
    _log(c, 2600, 1700, 1100, 120, 0, "#8a5c3e")
    for x in (230, 3560):
        c.drawRect(_R(x - 40, 1300, x + 40, H), fill("#5a3c32"))
    c.drawRect(_R(0, 0, W, H), fill("#d89070", 0.1))
    _vignette(c, 0.45)
    slots = {"center": _flat_slot(1900, 1880, 0.95), "left": _flat_slot(1200, 1880, 0.95, pose="sit"),
             "right": _flat_slot(3000, 1880, 0.95, pose="sit")}
    return Scene(None, s.makeImageSnapshot(), slots=slots, floor_y=1880)


# =================================================================== 3. brick city wall with palisade and smoke
def _city_wall(c, top, bottom, seed=4) -> None:
    for k in range(32):
        x = k * 125 + 40
        c.drawRect(_R(x - 34, top - 150, x + 34, top + 10), lin_paint((x - 34, 0), (x + 34, 0), ["#f2e8d6", "#d6c8b2"]))
        c.drawPath(poly([(x - 34, top - 150), (x, top - 210), (x + 34, top - 150)]), fill("#ece0cc"))
    c.drawRect(_R(0, top - 20, W, top + 20), fill("#9a5a46"))
    c.drawRect(_R(0, top + 20, W, bottom), lin_paint((0, top), (0, bottom), ["#c88a70", "#b4705a"]))
    _bricks(c, 0, top + 20, W, bottom, 46, 18, "#c27e66", "#b47460", seed=seed, var=0.04, gap=2)
    rng = random.Random(seed)
    p = skia.Path()
    p.moveTo(0, bottom - (bottom - top) * 0.42)
    x = 0
    while x < W:
        x += rng.uniform(80, 220)
        p.lineTo(x, bottom - (bottom - top) * rng.uniform(0.35, 0.62))
    p.lineTo(W, bottom)
    p.lineTo(0, bottom)
    p.close()
    c.drawPath(p, fill("#b8664e", 0.85))
    for _ in range(46):
        x, y = rng.uniform(0, W), rng.uniform(top + 60, bottom - 120)
        r = rng.uniform(16, 44)
        c.drawPath(poly([(x - r, y), (x, y - r * 0.4), (x + r, y), (x, y + r * 0.4)]), fill("#8a4e3c", 0.6))
    for _ in range(26):
        x = rng.uniform(0, W)
        y = rng.uniform(top + 40, top + 200)
        c.drawLine(x, y, x + rng.uniform(-10, 10), y + rng.uniform(80, 260), stroke("#7a4a3a", 4, 0.5))
    c.drawRect(_R(0, bottom - 30, W, bottom), fill("#8a4e3c"))


def scene_tuong_thanh_gach_khoi(tod: str) -> Scene:
    s = new_surface()
    c = s.getCanvas()
    vgrad(c, 0, 0, W, 900, ["#8aa0b8", "#b4c0c8", "#c8ccc4"])
    for x, y, w_ in ((500, 180, 300), (1500, 560, 340), (2900, 420, 280)):
        c.drawPath(oval(x, y, w_, 46), fill("#eef0ee", 0.8))
    for k, x in enumerate((450, 1100, 1950, 2500, 3350)):
        _smoke_column(c, x, 760, -100, 110, k + 2, "#5e5650", 0.5)
    _city_wall(c, 570, 1250)
    for x, y in ((1380, 640), (520, 960)):
        c.drawCircle(x, y, 90, _blur("#f8f6f0", 0.8, 30))
        c.drawCircle(x + 20, y + 30, 50, fill("#ffffff", 0.75))
    vgrad(c, 0, 1250, W, H, ["#d4c098", "#bca880"])
    _grass(c, 0, W, 1250, 1500, 70, 3, "#7a7a40", 0.7)
    for x, w_ in ((1050, 260), (2350, 360), (2960, 260)):
        _mound(c, x, 1300, w_, 70, "#a88a60")
    c.drawPath(oval(2380, 1300, 90, 22), fill("#2a1e16"))
    c.drawPath(oval(2380, 1290, 44, 28), fill("#f2ece2"))
    _basket(c, 2690, 1310, 80, 70)
    _basket(c, 3380, 1310, 80, 70)
    for x in (2500, 2900):
        _hoe(c, x, 1300, 200, -14)
    for x in (1020, 3480):
        c.drawPath(rrect(x - 40, 1220, x + 40, 1300, 20), fill("#7a5a3e"))
        c.drawPath(oval(x, 1222, 40, 10), fill("#2a1e14"))
    c.drawLine(60, 1500, 90, 760, stroke("#7a9a50", 30))
    for a in (200, 230, 260, 300, 330, 350):
        rd = math.radians(a)
        c.drawLine(90, 780, 90 + math.cos(rd) * 300, 780 + math.sin(rd) * 200 + 120, stroke("#88aa60", 40))
    _vignette(c, 0.35)
    slots = {"center": _flat_slot(1900, 1940, 1.0), "left": _flat_slot(1100, 1940, 1.0), "right": _flat_slot(2800, 1940, 1.0)}
    return Scene(None, s.makeImageSnapshot(), slots=slots, floor_y=1940)


# =================================================================== 4. digging site at the foot of the wall
def scene_cong_truong_dao_chan_tuong(tod: str) -> Scene:
    smoke = tod == "smoke"
    s = new_surface()
    c = s.getCanvas()
    _bricks(c, 0, 0, W, 1320, 108, 40, "#b87458", "#8a4e3a", seed=11, var=0.06, gap=6)
    rng = random.Random(4)
    p = skia.Path()
    p.moveTo(0, 0)
    x = 0
    p.lineTo(0, 260)
    while x < W:
        x += rng.uniform(140, 300)
        p.lineTo(x, rng.uniform(80, 340))
    p.lineTo(W, 0)
    p.close()
    c.drawPath(p, fill("#d8b4a0", 0.75))
    for _ in range(10):
        x, y = rng.uniform(0, W), rng.uniform(40, 300)
        c.drawPath(poly([(x - 90, y), (x, y - 30), (x + 110, y + 10), (x, y + 34)]), fill("#7a4e3e", 0.5))
    c.drawRect(_R(0, 1180, W, 1320), fill("#8a4a36", 0.55))
    vgrad(c, 0, 1300, W, H, ["#d8c8a6", "#c4b28e"])
    _mound(c, 600, 1500, 1000, 300, "#a8885e")
    _mound(c, 3000, 1420, 1300, 300, "#a8885e")
    hx, hy = 1900.0, 1560.0
    c.drawPath(oval(hx, hy, 420, 80), fill("#6a5a44"))
    c.drawPath(oval(hx, hy + 6, 380, 66), fill("#1a1410"))
    if smoke:
        c.drawPath(oval(hx, hy + 10, 300, 50), rad_paint(hx, hy + 10, 300, [("#ff9a40", 0.9), ("#c85a20", 0.5), ("#c85a20", 0.0)]))
        glow(c, hx, hy - 100, 900, "#ffb070", 0.35)
        _smoke_column(c, hx + 30, hy - 80, -150, 140, 7, "#4a4440", 0.55)
        for _ in range(60):
            c.drawCircle(rng.uniform(hx - 700, hx + 700), rng.uniform(200, hy), rng.uniform(3, 8), fill("#ffb060", rng.uniform(0.4, 0.9)))
    c.drawRect(_R(hx - 360, hy - 40, hx + 140, hy - 10), fill("#8a6a48"))
    for x in (hx - 330, hx + 110):
        c.drawRect(_R(x - 12, hy - 10, x + 12, hy + 60), fill("#6a5038"))
    _basket(c, 560, 1830, 240, 190)
    _basket(c, 3300, 1830, 240, 190)
    _hoe(c, 380, 1600, 640, 22)
    _hoe(c, 3500, 1560, 620, -20)
    for x, y in ((360, 1580), (3200, 1520)):
        c.drawPath(poly([(x, y), (x + 110, y - 10), (x + 120, y + 30), (x + 10, y + 36)]), fill("#b85a40"))
    _grass(c, 0, W, 1800, H, 30, 8, "#8a8250", 0.8)
    if smoke:
        c.drawRect(_R(0, 0, W, H), fill("#ffcf9a", 0.08))
    _vignette(c, 0.4)
    slots = {"center": _flat_slot(1200, 1900, 1.0), "left": _flat_slot(1000, 1900, 1.0), "right": _flat_slot(2700, 1900, 1.0)}
    return Scene(None, s.makeImageSnapshot(), slots=slots, floor_y=1900)


# =================================================================== 5. vaulted brick cellar
def scene_ham_gach_vom(tod: str) -> Scene:
    torch = tod == "torch"
    s = new_surface()
    c = s.getCanvas()
    base, mortar = "#a8604a", "#5a3226"
    _bricks(c, 0, 0, W, 1600, 150, 54, base, mortar, seed=21, var=0.1, gap=7)
    _arch_bricks(c, W / 2, 1380, 2000, 2950, 0.5, shade(base, -0.06), mortar, seed=5, n_rings=11)
    c.drawArc(_R(W / 2 - 2000, 1380 - 1000, W / 2 + 2000, 1380 + 1000), 180, 180, False, stroke("#2a160e", 30, 0.7))
    c.drawPath(oval(W / 2, 1380, 2000, 1000), _blur("#000000", 0.0, 1))
    for x in (300, 900, 2350):
        c.drawRect(_R(x, 600, x + 40, 1600), fill("#000000", 0.15))
    # barred window + stairs (right)
    wl, wt, wr, wb = 2720.0, 180.0, 3180.0, 640.0
    c.drawRect(_R(wl - 40, wt - 60, wr + 40, wt), fill("#4a2e20"))
    c.drawRect(_R(wl, wt, wr, wb), lin_paint((wl, 0), (wr, 0), ["#f2efe6", "#ffffff", "#e8e4da"]))
    for k in range(7):
        x = wl + 30 + k * (wr - wl - 60) / 6
        c.drawRect(_R(x - 16, wt, x + 16, wb), fill("#5a4030"))
    for y in (wt + 80, wb - 90):
        c.drawLine(wl, y, wr, y, stroke("#c8b890", 10))
    shaft = poly([(wl + 40, wb), (wr - 40, wb), (wr + 260, 1900), (wl + 120, 1900)])
    c.drawPath(shaft, lin_paint((0, wb), (0, 1900), [("#fff8e8", 0.38), ("#fff8e8", 0.06)]))
    vgrad(c, 0, 1560, W, H, ["#3e342c", "#2a221c"])
    steps = 9
    for k in range(steps):
        y0 = wb + 40 + k * 140
        x0 = wl - 120 - k * 40
        c.drawRect(_R(x0, y0, wr + 260, y0 + 140), fill(shade("#6a4436", -0.03 * k)))
        c.drawRect(_R(x0, y0, wr + 260, y0 + 22), fill("#8a5c48"))
    c.drawRect(_R(wr + 260, wb, W, H), fill("#4a2c20"))
    _bricks(c, wr + 260, wb, W, 1600, 120, 46, shade(base, -0.15), mortar, seed=9, var=0.08)
    # brick bench (left)
    _bricks(c, 120, 1330, 1450, 1700, 130, 48, shade(base, -0.05), mortar, seed=12, var=0.08)
    c.drawRect(_R(100, 1300, 1480, 1340), fill("#8a5a48"))
    c.drawRect(_R(120, 1340, 1450, 1360), fill("#000000", 0.25))
    c.drawPath(rrect(3520, 1480, 3720, 1700, 14), fill("#5a3e2c"))
    c.drawPath(oval(3620, 1482, 100, 22), fill("#2a1c14"))
    rng = random.Random(14)
    for _ in range(200):
        x, y = rng.uniform(200, 3400), rng.uniform(1880, H)
        a = rng.uniform(-0.6, 0.6)
        L = rng.uniform(40, 120)
        c.drawLine(x, y, x + L * math.cos(a), y + L * math.sin(a), stroke("#c8a860", 3, 0.7))
    _torch(c, 1260, 700, 0.9, lit=torch)
    if torch:
        glow(c, 1260, 640, 1800, "#ffa850", 0.35)
        c.drawRect(_R(0, 0, W, H), fill("#ffb070", 0.06))
        _vignette(c, 0.55)
    else:
        c.drawRect(_R(0, 0, W, H), fill("#10080a", 0.25))
        glow(c, (wl + wr) / 2, wb + 200, 1100, "#fff4dc", 0.2)
        _vignette(c, 0.7)
    slots = {"center": _flat_slot(1900, 1960, 1.0), "bench": _flat_slot(800, 1700, 0.95, pose="sit"),
             "stairs": _flat_slot(2900, 1180, 0.85)}
    return Scene(None, s.makeImageSnapshot(), slots=slots, floor_y=1960)


# =================================================================== 6. timber tunnel with a fire at the end
def scene_duong_ham_dot_mong(tod: str) -> Scene:
    blaze = tod == "blaze"
    s = new_surface()
    c = s.getCanvas()
    cx, cy = W / 2, 1080.0
    c.drawRect(_R(0, 0, W, H), fill("#4a3022"))
    rng = random.Random(6)
    for k in range(40):
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        c.drawPath(oval(x, y, rng.uniform(20, 60), rng.uniform(10, 22)), fill("#5a3a28", 0.7))
    # receding frames (far -> near)
    for i in range(12, -1, -1):
        f = 1 / (1 + i * 0.55)
        hw, top, bot = 1700 * f, cy - 900 * f, cy + 1000 * f
        col = shade("#9a6a44", -0.05 * i) if not blaze else shade("#b0723e", -0.04 * i)
        post = max(10.0, 150 * f)
        c.drawPath(poly([(cx - hw * 1.25, top - post), (cx + hw * 1.25, top - post), (cx + hw, top), (cx - hw, top)]),
                   fill(shade(col, -0.2)))
        c.drawRect(_R(cx - hw - post, top - post, cx + hw + post, top), fill(col))
        for sx in (-1, 1):
            x0 = cx + sx * hw
            c.drawRect(_R(min(x0, x0 + sx * post), top, max(x0, x0 + sx * post), bot), fill(col))
            c.drawLine(x0 + sx * post * 0.5, top, x0 + sx * post * 0.5, bot, stroke(shade(col, -0.2), max(2.0, post * 0.08)))
        if i == 12:
            c.drawRect(_R(cx - hw, top, cx + hw, bot), fill("#2a1a10"))
    fx, fy = cx, cy + 120
    fire_r = 520 if blaze else 360
    glow(c, fx, fy, fire_r * 3.2, "#ff9040", 0.55 if blaze else 0.4)
    for k in range(9):
        x = fx + (k - 4) * fire_r * 0.12
        hh = fire_r * rng.uniform(0.5, 0.9)
        p = skia.Path()
        p.moveTo(x - fire_r * 0.12, fy)
        p.quadTo(x - fire_r * 0.06, fy - hh * 0.6, x + rng.uniform(-20, 20), fy - hh)
        p.quadTo(x + fire_r * 0.06, fy - hh * 0.6, x + fire_r * 0.12, fy)
        p.close()
        c.drawPath(p, fill("#ff7a2a" if k % 2 else "#ffb040", 0.9))
    c.drawPath(oval(fx, fy, fire_r * 0.6, fire_r * 0.08), fill("#ffe0a0", 0.9))
    # firewood along both sides
    for sx in (-1, 1):
        for row in range(3):
            for k in range(5):
                f = 1 / (1 + k * 0.6)
                x = cx + sx * (380 + 1300 * f)
                y = cy + 700 * f + 60 - row * 120 * f
                r = 70 * f + 20
                c.drawPath(rrect(x - sx * 260 * f - r, y - r, x + sx * 0 + r, y + r, r), fill("#3a2416"))
                c.drawCircle(x, y, r * 0.9, fill("#c88a50" if not blaze else "#e09040"))
                c.drawCircle(x, y, r * 0.5, stroke("#7a4a28", max(2.0, r * 0.08)))
    vgrad(c, 0, cy + 900, W, H, ["#3a2618", "#24160e"])
    for _ in range(90 if blaze else 50):
        c.drawCircle(rng.uniform(0, W), rng.uniform(0, H * 0.8), rng.uniform(3, 7), fill("#ffb060", rng.uniform(0.3, 0.8)))
    c.drawRect(_R(0, 0, W, H), fill("#ff8a40", 0.08 if blaze else 0.04))
    _vignette(c, 0.7)
    slots = {"center": _flat_slot(1500, 2050, 1.0), "right": _flat_slot(2400, 2050, 1.0)}
    return Scene(None, s.makeImageSnapshot(), slots=slots, floor_y=2050)


# =================================================================== 7. ruined temple ground with a stone head in tree roots
def _stone_head(c, cx, cy, r, col="#a8a29c") -> None:
    c.drawPath(rrect(cx - r * 1.18, cy - r * 0.2, cx - r * 0.92, cy + r * 0.9, r * 0.12), fill(shade(col, -0.25)))
    c.drawPath(rrect(cx + r * 0.92, cy - r * 0.2, cx + r * 1.18, cy + r * 0.9, r * 0.12), fill(shade(col, -0.25)))
    c.drawPath(oval(cx, cy + r * 0.1, r, r * 1.08), fill(col))
    for row in range(3):
        n = 6 - row
        for k in range(n):
            x = cx - r * 0.7 + r * 1.4 * (k + 0.5) / n + (r * 0.12 if row % 2 else 0) * 0
            c.drawCircle(x, cy - r * 0.95 - row * r * 0.2, r * 0.11, fill(shade(col, -0.45)))
    c.drawCircle(cx, cy - r * 1.55, r * 0.17, fill(shade(col, -0.5)))
    for sx in (-1, 1):
        c.drawArc(_R(cx + sx * r * 0.42 - r * 0.22, cy - r * 0.05, cx + sx * r * 0.42 + r * 0.22, cy + r * 0.15), 10, 160, False,
                  stroke("#4a4440", r * 0.05))
        c.drawArc(_R(cx + sx * r * 0.42 - r * 0.3, cy - r * 0.38, cx + sx * r * 0.42 + r * 0.3, cy - r * 0.05), 200, 140, False,
                  stroke("#4a4440", r * 0.04))
    c.drawLine(cx, cy - r * 0.15, cx - r * 0.05, cy + r * 0.38, stroke("#4a4440", r * 0.035))
    c.drawArc(_R(cx - r * 0.25, cy + r * 0.35, cx + r * 0.25, cy + r * 0.6), 20, 140, False, stroke("#7a3a34", r * 0.05))
    c.drawLine(cx - r * 0.6, cy + r * 0.3, cx - r * 0.45, cy + r * 0.45, stroke(shade(col, -0.3), r * 0.02))


def scene_phe_tich_cay_bo_de(tod: str) -> Scene:
    storm = tod == "storm"
    s = new_surface()
    c = s.getCanvas()
    if storm:
        vgrad(c, 0, 0, W, 1300, ["#2a2e40", "#3a3e52", "#4a4c5a"])
        for k in range(9):
            c.drawPath(oval(k * 480 + 100, 120 + (k % 3) * 120, 420, 120), fill("#1e2232", 0.85))
    else:
        vgrad(c, 0, 0, W, 1300, ["#a888a8", "#d8a0a8", "#f0b8a0"])
    for x, h in ((1400, 330), (2200, 380), (3300, 420)):
        _palm(c, x, 1180, h, "#4a5a3a" if not storm else "#2a3428", "#5a4a3a")
    c.drawRect(_R(0, 1130, W, 1200), fill("#9a8a8a" if not storm else "#3a3c46", 0.6))
    vgrad(c, 0, 1160, W, H, ["#6a8a50", "#5a7a44"] if not storm else ["#3a4a30", "#2a3a24"])
    # ruined chedi (left)
    sx_ = 0
    bc = "#a8584a" if not storm else "#7a4840"
    for k in range(7):
        w_ = 900 - k * 90
        y = 1380 - k * 130
        c.drawRect(_R(sx_ + 380 - w_ / 2, y - 130, sx_ + 380 + w_ / 2, y), fill(shade(bc, -0.04 * (k % 2))))
        _bricks(c, sx_ + 380 - w_ / 2, y - 130, sx_ + 380 + w_ / 2, y, 60, 26, bc, shade(bc, -0.25), seed=k + 30, var=0.08, gap=3)
    c.drawPath(poly([(0, 470), (180, 330), (330, 400), (520, 300), (700, 480), (700, 600), (0, 600)]), fill(bc))
    rng = random.Random(9)
    for _ in range(18):
        c.drawPath(oval(rng.uniform(40, 720), rng.uniform(400, 1300), rng.uniform(30, 70), rng.uniform(16, 30)),
                   fill("#e8e4e0", 0.7))
    # broken walls (right)
    wc = "#a85a48" if not storm else "#7a4a40"
    c.drawRect(_R(2400, 780, W, 1230), fill(wc))
    c.drawPath(poly([(2400, 780), (2480, 520), (2540, 760), (2620, 430), (2700, 800), (2900, 820), (2940, 560), (3000, 820),
                     (3500, 820), (3560, 600), (3620, 820), (W, 820), (W, 900), (2400, 900)]), fill(wc))
    for x in (2700, 3020, 3300):
        c.drawRect(_R(x, 600, x + 90, 1230), fill(shade(wc, 0.1)))
    c.drawRect(_R(2400, 1230, W, 1270), fill(shade(wc, -0.2)))
    # big tree trunk with roots + stone head
    tl, tr = 760.0, 1400.0
    trunk = poly([(tl + 60, 0), (tr - 60, 0), (tr + 120, 1500), (tl - 140, 1500)])
    tc = "#9c9696" if not storm else "#6a6870"
    c.drawPath(trunk, lin_paint((tl, 0), (tr, 0), [shade(tc, -0.15), tc, shade(tc, 0.1), shade(tc, -0.2)]))
    for k in range(9):
        x0 = tl + 80 + k * (tr - tl - 160) / 8
        c.drawLine(x0, 0, x0 + (x0 - (tl + tr) / 2) * 0.25, 1480, stroke(shade(tc, -0.2), 8, 0.6))
    hx, hy = (tl + tr) / 2, 1180.0
    c.drawPath(oval(hx, hy + 20, 230, 260), fill(shade(tc, -0.35)))
    _stone_head(c, hx, hy + 40, 150, "#a8a29c" if not storm else "#86828a")
    for sx in (-1, 1):
        p = skia.Path()
        p.moveTo(hx + sx * 300, 700)
        p.cubicTo(hx + sx * 120, 860, hx + sx * 60, 930, hx - sx * 120, 990)
        c.drawPath(p, stroke(shade(tc, 0.05), 46))
        p2 = skia.Path()
        p2.moveTo(hx + sx * 260, 820)
        p2.cubicTo(hx + sx * 300, 1100, hx + sx * 260, 1300, hx + sx * 320, 1480)
        c.drawPath(p2, stroke(shade(tc, -0.05), 60))
    c.drawPath(oval(hx, 1500, 900, 60), fill("#000000", 0.2))
    vgrad(c, 0, 1560, W, 1700, ["#8a4a3e", "#6a382e"] if not storm else ["#5a3430", "#42262a"])
    for x in (350, 1700, 3200):
        c.drawPath(oval(x, 1640, 260, 30), stroke("#c8a89a" if not storm else "#7a6a6a", 8))
    _grass(c, 0, W, 1200, H, 60, 12, "#4a5a30" if not storm else "#2a3424", 0.8)
    if storm:
        _rain(c, 320, 7, 0.55, 0, 0, W, H, "#c8d4e8", 0.12)
        for _ in range(40):
            x, y = rng.uniform(0, W), rng.uniform(0, H)
            c.drawPath(oval(x, y, 14, 6), fill("#d8a040", 0.8))
        _vignette(c, 0.6)
    else:
        c.drawRect(_R(0, 0, W, H), fill("#ffc0a0", 0.06))
        _vignette(c, 0.4)
    slots = {"center": _flat_slot(2200, 1620, 0.85), "left": _flat_slot(500, 1620, 0.85), "right": _flat_slot(3000, 1620, 0.85)}
    return Scene(None, s.makeImageSnapshot(), slots=slots, floor_y=1620)


# =================================================================== 8. old riverside market
def scene_cho_ven_kenh_co(tod: str) -> Scene:
    s = new_surface()
    c = s.getCanvas()
    vgrad(c, 0, 0, W, 1100, ["#b8c4cc", "#d8d4c8", "#dcd2bc"])
    _prang(c, 2060, 900, 220, 900, "#e8e2d6", "#c8bcae", door=False)
    for x in (1600, 2500):
        _chedi(c, x, 920, 160, 420, "#e2dccf")
    c.drawRect(_R(0, 880, W, 1060), fill("#d0c4a8"))
    houses = ((-120, 720), (480, 860), (1450, 520), (2050, 800), (2950, 760), (3550, 640))
    for k, (x, w_) in enumerate(houses):
        _stilt_house(c, x, 1250, w_, 260, 300, w_ * 0.62, wall="#a88a68", roof="#a8906c", dark="#6a5238",
                     posts=8, door=True, ladder=k in (2, 4))
    for x, w_ in ((150, 520), (2150, 560), (3150, 480), (900, 360)):
        c.drawPath(poly([(x, 1050), (x + w_, 1050), (x + w_ + 40, 1110), (x - 40, 1110)]), fill("#b49a72"))
        for k in range(14):
            xx = x - 30 + k * (w_ + 60) / 14
            c.drawLine(xx, 1110, xx, 1150, stroke("#9a7e5a", 6))
        c.drawRect(_R(x + 20, 1170, x + w_ - 20, 1190), fill("#d8c49c"))
        for xx in (x + 40, x + w_ - 40):
            c.drawLine(xx, 1190, xx, 1250, stroke("#7a6044", 8))
        for j in range(3):
            c.drawPath(oval(x + 120 + j * (w_ - 200) / 2, 1160, 40, 16), fill(["#e8e0c8", "#c87a40", "#4a7ab0"][j]))
    c.drawRect(_R(0, 1250, W, 1290), fill("#8a6e50"))
    for x in range(0, W, 170):
        c.drawRect(_R(x, 1240, x + 18, 1340), fill("#6a5238"))
    c.drawRect(_R(3400, 1260, 3700, 1320), fill("#9a7a58"))
    vgrad(c, 0, 1320, W, H, ["#8a9a7c", "#6e8064"])
    rng = random.Random(8)
    for _ in range(80):
        x, y = rng.uniform(0, W), rng.uniform(1360, H)
        c.drawLine(x, y, x + rng.uniform(60, 220), y, stroke("#a8b498", 4, 0.6))
    for (l, r, y) in ((-60, 760, 1400), (2300, 3260, 1420)):
        _hull(c, l, r, y - 40, 70, "#9a7a58")
        c.drawPath(oval((l + r) / 2, y + 40, (r - l) * 0.45, 14), fill("#000000", 0.12))
    c.drawRect(_R(0, 0, W, H), fill("#e8dcc0", 0.12))
    _vignette(c, 0.35)
    slots = {"center": _flat_slot(1900, 1255, 0.42), "left": _flat_slot(1100, 1255, 0.42), "right": _flat_slot(2700, 1255, 0.42)}
    return Scene(None, s.makeImageSnapshot(), slots=slots, floor_y=1255)


# =================================================================== 9. white prang temple
def scene_chua_thap_prang(tod: str) -> Scene:
    dusk = tod == "dusk"
    s = new_surface()
    c = s.getCanvas()
    if dusk:
        vgrad(c, 0, 0, W, 1600, ["#6a5a7a", "#b07a8a", "#e0a08a"])
        for x, y in ((700, 300), (2300, 220), (3300, 420)):
            c.drawPath(oval(x, y, 500, 40), fill("#d08a8a", 0.6))
    else:
        vgrad(c, 0, 0, W, 1600, ["#b8c4cc", "#dcdcd2", "#e2dccc"])
    for x in range(2600, 3800, 140):
        _palm(c, x, 1640, 260, "#5a6a48" if not dusk else "#4a4040", "#6a5a48")
    vgrad(c, 0, 1560, W, H, ["#c8b896", "#a89a7a"] if not dusk else ["#8a7068", "#6a5450"])
    _chedi(c, 900, 1720, 360, 1100, "#ece6dc" if not dusk else "#d8c8c4")
    _chedi(c, 3300, 1760, 300, 800, "#ece6dc" if not dusk else "#d8c8c4")
    c.drawPath(oval(1920, 1700, 820, 90), fill("#9a8a72" if not dusk else "#6a5450"))
    _prang(c, 1920, 1680, 620, 1600, "#f2eee6" if not dusk else "#e8d8d4", "#c8c0b4" if not dusk else "#b0a0a4")
    _vihara(c, -140, 1700, 760, 160, 240, "#c8683a", "#9a7650")
    for x in (240, 520):
        c.drawPath(rrect(x - 40, 1640, x + 40, 1700, 18), fill("#7a5a40"))
    c.drawPath(oval(1750, 1620, 300, 40), fill("#e8dcc8", 0.6))
    if dusk:
        c.drawRect(_R(0, 0, W, H), fill("#ffb0a0", 0.08))
    else:
        c.drawRect(_R(0, 0, W, H), fill("#f2ece0", 0.16))
    _vignette(c, 0.35)
    slots = {"center": _flat_slot(1500, 2000, 0.7), "left": _flat_slot(700, 2000, 0.7), "right": _flat_slot(2700, 2000, 0.7)}
    return Scene(None, s.makeImageSnapshot(), slots=slots, floor_y=2000)


# =================================================================== 10. village yard with stall hut + stilt house
def scene_san_lang_nha_san(tod: str) -> Scene:
    s = new_surface()
    c = s.getCanvas()
    vgrad(c, 0, 0, W, 1100, ["#d8d4c8", "#e6ddc8"])
    for x in (420, 3300):
        _smoke_column(c, x, 900, -100, 90, 3, "#8a8680", 0.4)
    c.drawPath(poly([(200, 1000), (420, 560), (640, 1000)]), fill("#e8e0d2", 0.7))
    c.drawRect(_R(0, 960, W, 1080), fill("#d4c4a4"))
    vgrad(c, 0, 1060, W, H, ["#c8b08a", "#a88e68"])
    # stall hut
    hl, hr, ht, hb = 760.0, 2050.0, 520.0, 1620.0
    c.drawRect(_R(hl + 40, ht + 180, hr - 260, hb - 60), fill("#a8906a"))
    for k in range(9):
        x = hl + 40 + k * (hr - 260 - hl - 40) / 8
        c.drawLine(x, ht + 180, x, hb - 60, stroke("#8a7452", 6))
    for k in range(9):
        y = ht + 180 + k * (hb - 60 - ht - 180) / 8
        c.drawLine(hl + 40, y, hr - 260, y, stroke("#8a7452", 4))
    for x in (hl + 60, hr - 60):
        c.drawRect(_R(x - 14, ht + 160, x + 14, hb), fill("#d8c09a"))
    c.drawPath(poly([(hl - 160, ht + 200), (hl + 40, ht), (hr + 180, ht), (hr + 360, ht + 200)]), fill("#c8b088"))
    for k in range(5):
        y = ht + k * 40
        c.drawLine(hl + 40 - k * 40, y, hr + 180 + k * 36, y, stroke("#a8906a", 6))
    rng = random.Random(2)
    x = hl - 140
    while x < hr + 340:
        L = rng.uniform(60, 150)
        c.drawRect(_R(x, ht + 200, x + 18, ht + 200 + L), fill("#d4bc92"))
        x += rng.uniform(34, 60)
    c.drawRect(_R(hl - 60, hb - 340, hr - 120, hb - 300), fill("#d8c49e"))
    for x in (hl, hr - 180):
        c.drawRect(_R(x - 12, hb - 300, x + 12, hb), fill("#b09a74"))
    _basket(c, 1500, hb - 340, 240, 180, "#c8b088")
    c.drawPath(oval(1500, hb - 520, 100, 20), fill("#f2eee6"))
    # stilt house (right)
    _stilt_house(c, 2350, 1420, 1600, 560, 640, 0, wall="#9a7a58", roof="#8a6a48", dark="#6a4e36",
                 posts=7, door=True, ladder=True, thatch=False, window=False)
    c.drawRect(_R(2330, 0, W, 140), fill("#8a6a4a"))
    c.drawRect(_R(3200, 980, 3290, 1360), fill("#4a8a50"))
    for x in (1000, 2700, 3500):
        _grass(c, x - 60, x + 60, 1500, 1560, 3, x, "#8a8a50", 0.8)
    vgrad(c, 0, 1820, W, H, ["#6a5038", "#4a3626"])
    for x in (300, 1300, 2300, 3300):
        c.drawRect(_R(x - 40, 1700, x + 40, H), fill("#5a3e2a"))
    c.drawRect(_R(0, 1820, W, 1850), fill("#7a5a40"))
    c.drawRect(_R(0, 0, W, H), fill("#efe2c8", 0.12))
    _vignette(c, 0.35)
    slots = {"center": _flat_slot(1900, 1760, 0.75), "left": _flat_slot(700, 1760, 0.75), "right": _flat_slot(2800, 1760, 0.75),
             "stall": _flat_slot(1700, 1620, 0.7, pose="sit")}
    return Scene(None, s.makeImageSnapshot(), slots=slots, floor_y=1760)


LIBRARY_SCENES = {
    "xuong_thuyen_nha_san": scene_xuong_thuyen_nha_san,
    "san_xuong_thuyen_hoang_hon": scene_san_xuong_thuyen_hoang_hon,
    "tuong_thanh_gach_khoi": scene_tuong_thanh_gach_khoi,
    "cong_truong_dao_chan_tuong": scene_cong_truong_dao_chan_tuong,
    "ham_gach_vom": scene_ham_gach_vom,
    "duong_ham_dot_mong": scene_duong_ham_dot_mong,
    "phe_tich_cay_bo_de": scene_phe_tich_cay_bo_de,
    "cho_ven_kenh_co": scene_cho_ven_kenh_co,
    "chua_thap_prang": scene_chua_thap_prang,
    "san_lang_nha_san": scene_san_lang_nha_san,
}

LIBRARY_TAGS = {
    "xuong_thuyen_nha_san": ["xưởng đóng thuyền", "gầm nhà sàn", "thuyền gỗ", "con lăn gỗ", "cồng", "bờ sông", "làng cổ",
                             "boat shed", "boat building", "under stilt house", "wooden boat", "gong", "riverside"],
    "san_xuong_thuyen_hoang_hon": ["sân xưởng", "hoàng hôn", "khúc gỗ", "ngồi nghỉ", "sàn gỗ", "tường thành", "chùa xa",
                                   "shed deck", "dusk", "log bench", "city wall", "temple spires"],
    "tuong_thanh_gach_khoi": ["tường thành", "thành gạch", "hàng rào cọc", "khói", "bị vây", "chiến tranh", "đào đất",
                              "city wall", "brick wall", "palisade", "smoke", "siege", "ancient city"],
    "cong_truong_dao_chan_tuong": ["đào hầm", "chân tường", "hố đất", "cuốc", "sọt", "tường gạch", "khói", "than hồng",
                                   "digging", "foot of the wall", "hole", "hoe", "baskets", "undermining"],
    "ham_gach_vom": ["hầm gạch", "ngục", "vòm gạch", "cửa song", "cầu thang", "đuốc", "rơm", "bị giam",
                     "brick cellar", "vaulted dungeon", "barred window", "stairs", "torch", "prison"],
    "duong_ham_dot_mong": ["đường hầm", "khung gỗ", "lửa", "củi", "đốt móng tường", "dưới lòng đất",
                           "tunnel", "timber frames", "fire", "firewood", "underground", "undermining"],
    "phe_tich_cay_bo_de": ["phế tích", "chùa đổ", "cây bồ đề", "đầu tượng trong rễ cây", "tháp gạch", "hoàng hôn", "bão",
                           "temple ruins", "tree roots", "stone head", "brick stupa", "dusk", "storm"],
    "cho_ven_kenh_co": ["chợ cổ", "ven kênh", "nhà sàn mái tranh", "thuyền", "tháp chùa", "thời xưa", "kinh đô",
                        "old market", "canal", "thatched stilt houses", "boats", "ancient kingdom"],
    "chua_thap_prang": ["chùa", "tháp prang", "tháp trắng", "điện mái đỏ", "bảo tháp", "chuông", "kinh đô cổ",
                        "temple", "prang tower", "white tower", "stupa", "ancient temple"],
    "san_lang_nha_san": ["sân làng", "nhà sàn", "chòi bán hàng", "mái tranh", "thang", "làng cổ", "thời xưa",
                         "village yard", "stilt house", "stall hut", "thatched", "ladder"],
}

TOD_VI = {"smoke": "ban ngày, hố bốc khói đỏ lửa", "torch": "đuốc đang cháy", "blaze": "lửa bùng lớn", "storm": "chiều tối có bão"}
TOD_EN = {"smoke": "day, smoking glowing hole", "torch": "lit torch", "blaze": "big blaze", "storm": "stormy evening, rain"}
TOD_SCHEMA = {"smoke": "day", "torch": "night", "blaze": "night", "storm": "night"}
TOD_FLOW = {"smoke": "day, smoke column and orange glow from the hole, embers", "torch": "warm torchlight on brick",
            "blaze": "roaring fire at the tunnel end, flying embers", "storm": "dark storm clouds, rain, blowing leaves"}
