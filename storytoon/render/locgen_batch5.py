"""Batch-5 library locations (provenance 'procedural_library'): hospital night-shift horror.

Original flat-vector drawings in skia (no tracing): long night ward (lit / lights-out), hospital building in the
rain (+ one red window), floor-4 corridor, nurse station wall (+ bed 12 calling at 3 AM), bed by a rainy window
(+ bed 12 behind its curtain), staff locker room, staff pantry, wooden village yard at sunset (flashback), old duty
room with a glowing radio. ALL baked text is ENGLISH and generic (Vietnamese appears only in search tags).

Registered into locgen.LIBRARY_SCENES / LIBRARY_TAGS at the end of locgen (like the inserts batches).
"""
from __future__ import annotations

import math
import random

import skia

from .locgen import (H, W, Persp, Scene, _Bake, _R, _floor_tiles, _rain, _vignette, glow, lin_paint, new_surface,
                     path_fill, tint, vgrad)
from .skutil import fill, oval, poly, rrect, stroke

WALL = "#8fb0a8"
DADO = "#4f6a64"


def _flat_slot(x, y, scale, **kw) -> dict:
    return {"x": round(x), "y": round(y), "scale": round(scale, 3), **kw}


def _bokeh(c, l, t, r, b, n, seed, cols=("#ffd27a", "#8ab8ff", "#ff9a7a", "#cfe0ff")) -> None:
    rng = random.Random(seed)
    for _ in range(n):
        x, y, rr = rng.uniform(l, r), rng.uniform(t, b), rng.uniform(8, 26)
        c.drawCircle(x, y, rr, fill(rng.choice(cols), rng.uniform(0.25, 0.7)))


def _night_window(c, l, t, r, b, seed=1, rain=True, trees=True, frame="#e6ecea") -> None:
    vgrad(c, l, t, r, b, ["#22344a", "#1a2636", "#141c28"])
    if trees:
        for (tx, tw) in ((l + (r - l) * 0.3, (r - l) * 0.22), (l + (r - l) * 0.75, (r - l) * 0.18)):
            c.drawRect(_R(tx - tw * 0.06, t + (b - t) * 0.45, tx + tw * 0.06, b), fill("#0e1820"))
            for k in range(3):
                c.drawCircle(tx + (k - 1) * tw * 0.35, t + (b - t) * 0.4, tw * 0.35, fill("#122230"))
    _bokeh(c, l, t, r, b, 40, seed)
    if rain:
        c.save()
        c.clipRect(_R(l, t, r, b))
        _rain(c, 160, seed, 0.5, l, t, r, b, "#9ab4cc", 0.02)
        c.restore()
    w = max(8.0, (r - l) * 0.025)
    c.drawRect(_R(l, t, r, b), stroke(frame, w))
    c.drawLine((l + r) / 2, t, (l + r) / 2, b, stroke(frame, w * 0.8))


# =================================================================== 1. long ward at night
def scene_phong_benh_chung_dem(tod: str) -> Scene:
    dark = tod == "dark"
    bk = _Bake()
    P = Persp(f=1500, cx=W / 2, cy=900, cam_h=1.6)
    XW, YT, Z0, ZB = 4.6, 3.2, 1.0, 22.0
    s = new_surface()
    c = s.getCanvas()
    path_fill(c, P.plane_y(YT, -XW, XW, Z0, ZB), "#7a948f")
    path_fill(c, P.plane_y(0, -XW, XW, Z0, ZB), "#4e6662")
    _floor_tiles(c, P, -XW, XW, Z0, ZB, 0.6, "#42585a")
    for sd in (-1, 1):
        path_fill(c, P.wall_x(sd * XW, Z0, ZB, 1.0, YT), WALL)
        path_fill(c, P.wall_x(sd * XW, Z0, ZB, 0.0, 1.0), DADO)
    path_fill(c, P.face_z(ZB, -XW, XW, 0, YT), "#9ab8b0")
    path_fill(c, P.face_z(ZB, -XW, XW, 0, 1.0), DADO)
    # back: window + bed-12 curtain bay + white cabinet
    wl, wt = P.p(-1.3, 2.5, ZB)
    wr, wb = P.p(1.3, 1.0, ZB)
    _night_window(c, wl, wt, wr, wb, seed=12, trees=False)
    bl, bt = P.p(-0.7, 2.25, ZB - 0.05)
    br, bb = P.p(0.7, 2.05, ZB - 0.05)
    c.drawPath(rrect(bl + (br - bl) * 0.3, bt, br - (br - bl) * 0.3, bb, 4), fill("#ffffff"))
    bk.text(c, "12", (bl + br) / 2, (bt + bb) / 2, (bb - bt) * 0.8, "#2a3a5a")
    cl, ct = P.p(-0.95, 2.4, ZB - 1.6)
    cr, cb = P.p(0.95, 0.15, ZB - 1.6)
    for k, (x0, x1) in enumerate(((cl, cl + (cr - cl) * 0.42), (cr - (cr - cl) * 0.42, cr))):
        c.drawRect(_R(x0, ct, x1, cb), fill("#c8dcd8", 0.88))
        for j in range(7):
            xx = x0 + (x1 - x0) * j / 7
            c.drawLine(xx, ct, xx, cb, stroke("#9ab8b4", 3))
    c.drawLine(cl, ct, cr, ct, stroke("#c9ced2", 6))
    path_fill(c, P.face_z(ZB - 0.3, 1.7, 2.7, 0, 2.0), "#eef0ee")
    c.drawLine(*P.p(2.2, 0.05, ZB - 0.3), *P.p(2.2, 2.0, ZB - 0.3), stroke("#c9ced2", 3))
    # ceiling light strips
    z = 2.0
    while z < ZB - 1:
        for lx in (-1.5, 1.5):
            path_fill(c, P.plane_y(YT - 0.01, lx - 0.65, lx + 0.65, z, z + 0.3), "#8a9894" if dark else "#eef8f4")
            if not dark:
                glow(c, *P.p(lx, YT - 0.1, z + 0.15), 900 / z, "#e8fff8", 0.35)
        z += 2.6
    # left-wall windows
    z = 2.2
    while z < ZB - 2:
        q = P.wall_x(-XW + 0.01, z, z + 1.2, 1.35, 2.6)
        path_fill(c, q, "#e6ecea")
        path_fill(c, P.wall_x(-XW + 0.02, z + 0.08, z + 1.12, 1.43, 2.52), "#1a2430")
        z += 3.0
    # beds (far -> near)
    beds = []
    zs = [3.0 + k * 3.2 for k in range(6)]
    for i, zb in enumerate(zs):
        beds.append((-1, zb, str(2 + i)))
        beds.append((1, zb, str(7 + i) if i < 5 else ""))
    for sd, zb, num in sorted(beds, key=lambda b_: -b_[1]):
        x_wall = sd * XW
        x_in = sd * (XW - 2.1)
        x0, x1 = min(x_wall, x_in), max(x_wall, x_in)
        x0 += 0.15 if sd < 0 else 0.0
        x1 -= 0.15 if sd > 0 else 0.0
        # nightstand (beige box near the wall, toward the camera)
        ns0, ns1 = (x_wall - sd * 0.15, x_wall - sd * 0.65)
        path_fill(c, P.face_z(zb - 0.1, min(ns0, ns1), max(ns0, ns1), 0, 0.85), "#d8ccb0")
        path_fill(c, P.plane_y(0.85, min(ns0, ns1), max(ns0, ns1), zb - 0.1, zb + 0.3), "#e8dcc0")
        # headboard on wall side
        hb = x_wall - sd * 0.17
        path_fill(c, P.wall_x(hb, zb + 0.15, zb + 1.05, 0.55, 1.15), "#eef0f0")
        # mattress
        path_fill(c, P.plane_y(0.62, x0, x1, zb + 0.15, zb + 1.05), "#a9c3de")
        path_fill(c, P.plane_y(0.63, hb - sd * 0.05 - (0.4 if sd > 0 else -0.4) * 0, hb - sd * 0.45, zb + 0.3, zb + 0.9), "#f4f6f6")
        path_fill(c, P.face_z(zb + 0.15, x0, x1, 0.45, 0.62), "#f2f4f4")
        for lx in (x0 + 0.1, x1 - 0.1):
            c.drawLine(*P.p(lx, 0.45, zb + 0.15), *P.p(lx, 0.05, zb + 0.15), stroke("#8a9094", max(2.0, 30 / zb)))
            c.drawCircle(*P.p(lx, 0.05, zb + 0.15), max(3.0, 60 / zb), fill("#202428"))
        # call cord + number plate
        c.drawLine(*P.p(x_wall - sd * 0.02, 1.9, zb + 0.6), *P.p(hb - sd * 0.25, 0.7, zb + 0.6), stroke("#e8ecea", max(1.5, 14 / zb)))
        c.drawCircle(*P.p(hb - sd * 0.25, 0.72, zb + 0.6), max(3.0, 50 / zb), fill("#c8352e"))
        if num:
            px, py = P.p(x_wall - sd * 0.02, 2.05, zb + 0.6)
            k = P.f / zb
            c.drawPath(rrect(px - 0.17 * k, py - 0.12 * k, px + 0.17 * k, py + 0.12 * k, 4), fill("#f8f8f6"))
            c.drawPath(rrect(px - 0.17 * k, py - 0.12 * k, px + 0.17 * k, py + 0.12 * k, 4), stroke("#2a3a5a", max(1.5, 0.012 * k)))
            bk.text(c, num, px, py, 0.17 * k, "#2a3a5a")
    # light pools on the floor
    z = 3.0
    while z < ZB - 2:
        for lx in (-1.0, 1.0):
            cx_, cy_ = P.p(lx, 0, z)
            c.drawPath(oval(cx_, cy_, 420 * 3 / z, 70 * 3 / z), fill("#b8d8d0", 0.08 if dark else 0.18))
        z += 2.6
    if dark:
        tint(s, "#30403e", 0.62)
        glow(c, *P.p(0, 1.6, ZB - 1.5), 260, "#ff3a2a", 0.45)
        _vignette(c, 0.75)
    else:
        tint(s, "#cfe4de", 0.18)
        _vignette(c, 0.5)
    slots = {"center": P.slot(0, 4.2), "left": P.slot(-1.0, 5.5), "right": P.slot(1.0, 5.5), "far": P.slot(0.1, 12.0),
             "bed12": P.slot(0.4, ZB - 2.2)}
    return Scene(None, s.makeImageSnapshot(), slots=slots, baked_signs=bk.items, floor_y=slots["center"]["y"],
                 lights=[] if dark else [{"x": round(P.cx), "y": 300, "color": "#e8fff8"}])


# =================================================================== 2. hospital building in the rain
def scene_toa_benh_vien_mua_dem(tod: str) -> Scene:
    bk = _Bake()
    s = new_surface()
    c = s.getCanvas()
    dusk = tod == "dusk"
    if dusk:
        vgrad(c, 0, 0, W, H, ["#4a4a7a", "#8a7aa8", "#d8a8a8", "#e8b890"])
        for k in range(3):
            c.drawPath(oval(600 + k * 1400, 240 + k * 120, 1000, 90), fill("#c8b0c8", 0.45))
    else:
        vgrad(c, 0, 0, W, H, ["#0c1630", "#1a2a4a", "#22324e"])
        for k in range(3):
            c.drawPath(oval(600 + k * 1400, 240 + k * 40, 900, 120), fill("#2a3a5a", 0.5))
    L, T, R, B = 560.0, 300.0, 3280.0, 1900.0
    rng = random.Random(11)
    c.drawRect(_R(L, T, R, B), lin_paint((L, 0), (R, 0), ["#8a8c8a", "#9fa19e", "#8e908c"]))
    c.drawRect(_R(L, T, R, T + 90), fill("#a8aaa6"))
    floors = 4
    fh = (B - T - 90) / floors
    cols = 16
    cw = (R - L - 80) / cols
    red = tod in ("redwindow", "dusk")
    for f in range(floors):
        y0 = T + 90 + f * fh
        c.drawRect(_R(L, y0 + fh - 30, R, y0 + fh - 10), fill("#b4b6b2"))
        for k in range(cols):
            x0 = L + 50 + k * cw
            wl, wt, wr, wb = x0 + 14, y0 + 40, x0 + cw - 14, y0 + fh - 60
            if f == floors - 1 and 6 <= k <= 9:
                continue                                   # entrance below
            if f == 0:
                col = "#e8a0a0" if (red and k == cols - 1) else "#bfe0dc"
                if red and k == cols - 1:
                    col = "#ff4a3a"
            else:
                col = "#f2d8a8" if rng.random() < 0.45 else "#1e2836"
            c.drawRect(_R(wl, wt, wr, wb), fill(col))
            if red and f == 0 and k == cols - 1:
                glow(c, (wl + wr) / 2, (wt + wb) / 2, 260, "#ff2a1a", 0.6)
            for j in range(1, 4):
                c.drawLine(wl + (wr - wl) * j / 4, wt, wl + (wr - wl) * j / 4, wb, stroke("#6a6c6a", 6))
            c.drawLine(wl, (wt + wb) / 2, wr, (wt + wb) / 2, stroke("#6a6c6a", 6))
    for (x0, y0, x1, y1) in ((1460, 540, 1500, 900), (1880, 700, 1860, 1100), (2400, 600, 2420, 1000)):
        c.drawLine(x0, y0, x1, y1, stroke("#6e706c", 4))           # cracks
    ex0, ex1 = L + 50 + 6 * cw, L + 50 + 10 * cw
    c.drawRect(_R(ex0, B - fh + 40, ex1, B), fill("#3e5a62"))
    c.drawRect(_R(ex0 + 30, B - fh + 120, ex1 - 30, B), fill("#2a4048"))
    c.drawPath(rrect(ex0 - 40, B - fh - 40, ex1 + 40, B - fh + 60, 6), fill("#2f5f9a"))
    bk.text(c, "MEMORIAL WING", (ex0 + ex1) / 2, B - fh + 10, 62, "#ffffff", max_w=ex1 - ex0)
    c.drawPath(rrect(1160, 40, 2680, 220, 6), fill("#ece8de"))
    bk.text(c, "DISTRICT HOSPITAL", 1920, 130, 110, "#24345a", max_w=1440)
    # trees, lamp, road, bikes
    for (tx, sc) in ((300, 1.0), (3560, 1.1)):
        c.drawRect(_R(tx - 22, 1200, tx + 22, 2000), fill("#141c24"))
        for k in range(5):
            c.drawCircle(tx - 260 + k * 130, 1180 + (k % 2) * 60, 180 * sc, fill("#1c2a34"))
    c.drawLine(1020, 2000, 1020, 1300, stroke("#2a2e34", 20))
    c.drawLine(1020, 1300, 1140, 1280, stroke("#2a2e34", 16))
    glow(c, 1150, 1295, 300, "#ffe0a8", 0.7)
    c.drawPath(oval(1150, 1295, 50, 18), fill("#fff1d0"))
    c.drawRect(_R(0, 1900, W, H), fill("#1a1e26"))
    for x in range(0, W, 520):
        c.drawRect(_R(x, 2030, x + 240, 2044), fill("#8a8e94"))
    for k, col in enumerate(("#c8352e", "#2f5fb0", "#2a2c30", "#d8dcde", "#2f8a4a")):
        bx = 2300 + k * 230
        c.drawPath(poly([(bx - 70, 1900), (bx + 70, 1900), (bx + 50, 1840), (bx - 50, 1850)]), fill(col))
        for dx in (-80, 80):
            c.drawCircle(bx + dx, 1935, 42, fill("#121418"))
    if not dusk:
        _rain(c, 1400, 7, 0.45, 0, 0, W, H, "#cfdcff", 0.08)
    tint(s, "#c8a8b8" if dusk else "#8aa0c8", 0.2)
    _vignette(c, 0.45)
    slots = {"center": _flat_slot(1260, 1960, 0.32), "entrance": _flat_slot((ex0 + ex1) / 2, 1900, 0.3),
             "left": _flat_slot(780, 1960, 0.32), "right": _flat_slot(2000, 1960, 0.32)}
    return Scene(None, s.makeImageSnapshot(), slots=slots, baked_signs=bk.items, floor_y=1960)


# =================================================================== 3. floor-4 corridor
def scene_hanh_lang_tang4_benh_vien(tod: str) -> Scene:
    bk = _Bake()
    P = Persp(f=1500, cx=W / 2, cy=880, cam_h=1.6)
    XW, YT, Z0, ZB = 1.4, 3.0, 0.9, 26.0
    s = new_surface()
    c = s.getCanvas()
    path_fill(c, P.plane_y(YT, -XW, XW, Z0, ZB), "#6f8a86")
    path_fill(c, P.plane_y(0, -XW, XW, Z0, ZB), "#7e928e")
    for sd in (-1, 1):
        path_fill(c, P.wall_x(sd * XW, Z0, ZB, 1.0, YT), "#86aaa2")
        path_fill(c, P.wall_x(sd * XW, Z0, ZB, 0.0, 1.0), "#3e5a54")
    path_fill(c, P.face_z(ZB, -XW, XW, 0, YT), "#9ab8b0")
    wl, wt = P.p(-0.6, 2.2, ZB)
    wr, wb = P.p(0.6, 1.1, ZB)
    _night_window(c, wl, wt, wr, wb, seed=4, trees=False)
    for sd in (-1, 1):                                   # doors
        for z0 in (3.0, 9.0, 15.0):
            path_fill(c, P.wall_x(sd * (XW - 0.01), z0, z0 + 1.0, 0, 2.2), "#6a8e86" if sd < 0 else "#e8ece8")
        for y in (0.9,):                                 # beige handrails
            c.drawLine(*P.p(sd * (XW - 0.06), y, Z0), *P.p(sd * (XW - 0.06), y, ZB), stroke("#d8c8a0", 1))
            q = P.quad([(sd * (XW - 0.08), y + 0.04, Z0), (sd * (XW - 0.08), y + 0.04, ZB), (sd * (XW - 0.08), y - 0.04, ZB),
                        (sd * (XW - 0.08), y - 0.04, Z0)])
            path_fill(c, q, "#dccca4")
    z = 1.6
    while z < ZB - 1:
        path_fill(c, P.plane_y(YT - 0.01, -0.45, 0.45, z, z + 0.25), "#eef8f4")
        glow(c, *P.p(0, YT - 0.1, z), 900 / z, "#e8fff8", 0.3)
        cx_, cy_ = P.p(0, 0, z + 0.6)
        c.drawPath(oval(cx_, cy_, 380 * 2.5 / z, 50 * 2.5 / z), fill("#cfe4de", 0.15))
        z += 2.2
    sx, sy = P.p(0, 2.55, 2.6)
    k = P.f / 2.6
    c.drawPath(rrect(sx - 0.55 * k, sy - 0.12 * k, sx + 0.55 * k, sy + 0.12 * k, 8), fill("#f0ece2"))
    bk.text(c, "MEMORIAL WING - FLOOR 4", sx, sy, 0.085 * k, "#2a3a6a", max_w=1.0 * k)
    lx, ly = P.p(-0.5, 2.05, 4.5)
    k2 = P.f / 4.5
    c.drawPath(rrect(lx - 0.22 * k2, ly - 0.08 * k2, lx + 0.22 * k2, ly + 0.08 * k2, 6), fill("#f0ece2"))
    bk.text(c, "FLOOR 4", lx, ly, 0.07 * k2, "#2a3a6a")
    rx, ry = P.p(0.55, 2.15, 4.0)
    k3 = P.f / 4.0
    c.drawPath(rrect(rx - 0.3 * k3, ry - 0.08 * k3, rx + 0.3 * k3, ry + 0.08 * k3, 6), fill("#2f5f9a"))
    bk.text(c, "WARD", rx, ry, 0.07 * k3, "#ffffff")
    rng = random.Random(3)
    for _ in range(140):
        zz = rng.uniform(2, ZB)
        xx, yy = P.p(rng.uniform(-XW, XW), 0, zz)
        c.drawCircle(xx, yy, max(2.0, 18 / zz), fill("#2a3a38", 0.5))
    tint(s, "#cfe4de", 0.18)
    _vignette(c, 0.6)
    slots = {"center": P.slot(0, 3.0), "left": P.slot(-0.6, 4.0), "right": P.slot(0.6, 4.0), "far": P.slot(0, 10.0)}
    return Scene(None, s.makeImageSnapshot(), slots=slots, baked_signs=bk.items, floor_y=slots["center"]["y"])


# =================================================================== 4. nurse station wall
def _wall_clock(c, cx, cy, R, hour, minute) -> None:
    c.drawCircle(cx + 8, cy + 12, R * 1.04, fill("#000000", 0.25))
    c.drawCircle(cx, cy, R, fill("#2e3438"))
    c.drawCircle(cx, cy, R * 0.88, fill("#f4f1ea"))
    for k in range(12):
        a = k / 12 * math.tau
        c.drawLine(cx + math.cos(a) * R * 0.7, cy + math.sin(a) * R * 0.7, cx + math.cos(a) * R * 0.82,
                   cy + math.sin(a) * R * 0.82, stroke("#2a2c33", R * 0.05))
    ha = math.radians((hour % 12 + minute / 60) * 30 - 90)
    ma = math.radians(minute * 6 - 90)
    c.drawLine(cx, cy, cx + math.cos(ha) * R * 0.45, cy + math.sin(ha) * R * 0.45, stroke("#1d1f24", R * 0.07))
    c.drawLine(cx, cy, cx + math.cos(ma) * R * 0.68, cy + math.sin(ma) * R * 0.68, stroke("#1d1f24", R * 0.045))
    c.drawCircle(cx, cy, R * 0.07, fill("#c8352e"))


def scene_quay_truc_y_ta(tod: str) -> Scene:
    bk = _Bake()
    call = tod == "call12"
    s = new_surface()
    c = s.getCanvas()
    vgrad(c, 0, 0, W, 1460, ["#8fb4ac", "#80a69e"])
    c.drawRect(_R(0, 1440, W, 1820), fill("#3e5a54"))
    c.drawRect(_R(0, 1430, W, 1450), fill("#dfe8e4"))
    for x in (1020, 2900):
        c.drawLine(x, 0, x + 20, 1430, stroke("#7a9a92", 4))      # cracks / seams
    # call panel
    pl, pt, pr, pb = 240.0, 660.0, 1140.0, 1160.0
    c.drawPath(rrect(pl, pt, pr, pb, 16), fill("#eeeae0"))
    c.drawRect(_R(pl + 20, pt + 20, pr - 20, pt + 80), fill("#4a4c52"))
    bk.text(c, "NURSE CALL", (pl + pr) / 2, pt + 50, 40, "#f3f1ea")
    for i in range(12):
        row, col_ = divmod(i, 6)
        x = pl + 40 + col_ * 140
        y = pt + 110 + row * 180
        on = call and i == 11
        if on:
            glow(c, x + 55, y + 70, 160, "#ff4a2a", 0.7)
        c.drawPath(rrect(x, y, x + 110, y + 150, 16), fill("#ff6a4a" if on else "#7a2a26"))
        bk.text(c, str(i + 1), x + 55, y + 75, 56, "#ffffff" if on else "#d8a8a0")
    _wall_clock(c, 1540, 700, 110, 3 if call else 2, 0 if call else 40)
    # patient whiteboard
    bl, bt, br, bb = 1860.0, 620.0, 2980.0, 1300.0
    c.drawPath(rrect(bl - 16, bt - 16, br + 16, bb + 16, 10), fill("#c9ced3"))
    c.drawRect(_R(bl, bt, br, bb), fill("#fbfcfc"))
    bk.text(c, "WARD 4 PATIENTS", (bl + br) / 2, bt + 60, 50, "#2a3a6a")
    names = ["Aunt B.", "Uncle S.", "Grandma P.", "Uncle C.", "Aunt L.", "Grandpa C.", "", "Uncle P.", "Grandma K.",
             "Uncle T.", "Aunt S.", ""]
    for i, nm in enumerate(names):
        col_, row = divmod(i, 6)
        x = bl + 50 + col_ * 560
        y = bt + 150 + row * 88
        bk.text(c, str(i + 1), x, y, 36, "#2a2c33")
        if i == 11:
            c.drawRect(_R(x + 60, y - 4, x + 130, y + 6), fill("#c8352e"))
        elif nm:
            bk.text(c, nm, x + 170, y, 34, "#2f4f9a", weight="semibold")
        c.drawLine(x - 20, y + 36, x + 470, y + 36, stroke("#dde2e6", 3))
    c.drawPath(rrect(3140, 620, 3460, 1060, 8), fill("#f2e6b8"))
    for k in range(4):
        c.drawLine(3180, 720 + k * 80, 3420, 720 + k * 80, stroke("#c8352e" if k < 2 else "#5a5a5a", 6))
    for k in range(9):                                      # binders
        c.drawRect(_R(3480 + k * 40, 1080, 3510 + k * 40, 1440), fill(["#2f5fb0", "#c8352e", "#2f8a4a", "#e8c04a"][k % 4]))
    # desk counter
    c.drawRect(_R(0, 1780, W, H), lin_paint((0, 1780), (0, H), ["#5a3e2a", "#3a281a"]))
    c.drawRect(_R(0, 1760, W, 1800), fill("#8a6e52"))
    c.drawPath(rrect(560, 1620, 900, 1770, 10), fill("#d8dcde"))
    c.drawRect(_R(920, 1650, 1340, 1770), fill("#2a4a7a"))
    c.drawPath(rrect(2360, 1680, 2440, 1770, 10), fill("#f4f4f0"))
    c.drawPath(rrect(2700, 1640, 2900, 1770, 20), fill("#ece4cf"))
    c.drawPath(rrect(2730, 1610, 2870, 1650, 14), fill("#2a2c30"))
    c.drawLine(3220, 1770, 3300, 1500, stroke("#2a3430", 14))
    c.drawLine(3300, 1500, 3480, 1420, stroke("#2a3430", 14))
    c.drawPath(poly([(3420, 1380), (3560, 1430), (3500, 1490), (3380, 1450)]), fill("#2a3430"))
    glow(c, 3470, 1470, 380, "#ffe0a0", 0.6)
    tint(s, "#d8ece6", 0.12)
    _vignette(c, 0.5)
    slots = {"center": _flat_slot(1920, 2100, 1.15), "left": _flat_slot(420, 2100, 1.15),
             "right": _flat_slot(3300, 2100, 1.15), "behind_desk": _flat_slot(1700, 2160, 1.2, clip_bottom=1770)}
    return Scene(None, s.makeImageSnapshot(), slots=slots, baked_signs=bk.items, floor_y=2100)


# =================================================================== 5. bed by a rainy window
def scene_giuong_benh_canh_cua_so(tod: str) -> Scene:
    bk = _Bake()
    cur = tod == "curtain"
    s = new_surface()
    c = s.getCanvas()
    vgrad(c, 0, 0, W, 1080, ["#7a9e98", "#86aaa2"])
    c.drawRect(_R(0, 1060, W, 1800), fill("#3e5c58"))
    c.drawRect(_R(0, 1050, W, 1072), fill("#d8e2de"))
    c.drawRect(_R(0, 1800, W, H), lin_paint((0, 1800), (0, H), ["#2e4240", "#22302e"]))
    for x in range(0, W, 300):
        c.drawLine(x, 1800, x - 200, H, stroke("#26383a", 4))
    _night_window(c, 1030, 90, 2150, 1100, seed=5)
    c.drawRect(_R(1010, 1090, 2170, 1130), fill("#d8e2de"))
    for (x0, y0, x1, y1) in ((3200, 200, 3220, 600), (2600, 300, 2650, 500), (500, 600, 560, 760)):
        c.drawLine(x0, y0, x1, y1, stroke("#6e8a84", 4))
    num = "12" if cur else "3"
    c.drawPath(rrect(830, 360, 1000, 470, 8), fill("#f8f8f6"))
    bk.text(c, num, 915, 415, 80, "#2a3a6a")
    c.drawPath(rrect(690, 610, 1040, 800, 10), fill("#eef0ee"))
    c.drawCircle(780, 720, 14, fill("#e8b830"))
    c.drawPath(rrect(880, 690, 920, 770, 10), fill("#cfe4d8"))
    c.drawCircle(900, 710, 16, fill("#3cb45a"))
    c.drawLine(980, 740, 1220, 1170, stroke("#eef0ee", 5))
    c.drawPath(rrect(1195, 1160, 1245, 1250, 14), fill("#f4f4f0"))
    c.drawCircle(1220, 1190, 14, fill("#c8352e"))
    # nightstand
    c.drawRect(_R(700, 1220, 1040, 1800), fill("#d8ccb0"))
    c.drawRect(_R(700, 1220, 1040, 1250), fill("#e8dcc0"))
    for y in (1380, 1600):
        c.drawRect(_R(760, y, 980, y + 20), fill("#8a7e66"))
    if not cur:
        c.drawRect(_R(790, 1050, 850, 1220), fill("#cfe4ec", 0.6))
        c.drawRect(_R(880, 1140, 960, 1220), fill("#f4f2ea"))
    # bed side view
    c.drawLine(1120, 1030, 1120, 1740, stroke("#c9ced2", 28))
    c.drawLine(2560, 1230, 2560, 1740, stroke("#c9ced2", 28))
    c.drawRect(_R(1120, 1380, 2560, 1500), fill("#a8aeb4"))
    c.drawPath(rrect(1120, 1340, 2560, 1420, 20), fill("#c8d8e4" if cur else "#e4eaee"))
    if cur:
        c.drawPath(rrect(1130, 1330, 2550, 1430, 20), fill("#dfe8ee", 0.6))
        c.drawLine(1300, 1350, 2400, 1360, stroke("#ffffff", 6, 0.7))
    else:
        c.drawPath(oval(1330, 1310, 230, 70), fill("#f8f8f6"))
        c.drawPath(rrect(1500, 1310, 2560, 1420, 20), fill("#9ab4d0"))
    for x in (1200, 2480):
        c.drawLine(x, 1500, x, 1740, stroke("#9aa0a6", 16))
        c.drawCircle(x, 1760, 30, fill("#1a1c20"))
    c.drawPath(oval(1840, 1790, 820, 50), fill("#000000", 0.3))
    if cur:
        c.drawRect(_R(0, 0, 1400, 1930), fill("#cfe4e0", 0.82))
        for k in range(30):
            x = k * 48
            c.drawLine(x, 0, x, 1930, stroke("#a8c4c0", 6))
    vigil = tod == "monitor"
    if vigil:                                           # IV pole + vital monitor + desk lamp + visitor chair
        c.drawLine(1080, 560, 1080, 1790, stroke("#9aa0a6", 12))
        c.drawRect(_R(1000, 1780, 1160, 1800), fill("#7a8086"))
        ml, mt, mr, mb = 780.0, 300.0, 1340.0, 640.0
        c.drawPath(rrect(ml, mt, mr, mb, 20), fill("#20252a"))
        c.drawRect(_R(ml + 24, mt + 24, mr - 24, mb - 24), fill("#0c1412"))
        ecg = skia.Path()
        x = ml + 40
        ecg.moveTo(x, mt + 130)
        while x < mr - 90:
            ecg.lineTo(x + 40, mt + 130)
            ecg.lineTo(x + 52, mt + 70)
            ecg.lineTo(x + 64, mt + 170)
            ecg.lineTo(x + 76, mt + 130)
            x += 100
        c.drawPath(ecg, stroke("#4ae0a0", 4))
        for k, (lab, val, col) in enumerate((("HR", "54", "#4ae0a0"), ("SpO2", "86", "#4ac8ff"), ("NIBP", "92/58", "#f0d060"))):
            bk.text(c, lab, ml + 90 + k * 180, mt + 230, 22, col, weight="semibold")
            bk.text(c, val, ml + 90 + k * 180, mt + 280, 48 if k < 2 else 34, col)
        c.drawLine(1260, 1250, 1380, 1080, stroke("#2e3436", 12))
        c.drawPath(poly([(1330, 1050), (1450, 1070), (1420, 1120), (1320, 1110)]), fill("#2e3436"))
        glow(c, 1400, 1120, 260, "#ffe0a0", 0.5)
        c.drawPath(rrect(2240, 1560, 2900, H + 40, 60), fill("#2f5a64"))
        c.drawPath(rrect(2260, 1580, 2880, 1700, 50), fill("#3e6c76"))
    tint(s, "#cfe4de", 0.18)
    _vignette(c, 0.5)
    slots = {"left": _flat_slot(300 if not cur else 1600, 1990, 1.0), "right": _flat_slot(3000, 1990, 1.0),
             "center": _flat_slot(2700, 1990, 1.0)}
    if vigil:
        slots["visitor_chair"] = _flat_slot(2570, 2160, 1.2, clip_bottom=1700)
        slots["in_bed"] = _flat_slot(1450, 1560, 0.9, clip_bottom=1400)
    return Scene(None, s.makeImageSnapshot(), slots=slots, baked_signs=bk.items, floor_y=1990)


# =================================================================== 10. hospital corridor side view
def scene_hanh_lang_benh_vien_ngang(tod: str) -> Scene:
    bk = _Bake()
    s = new_surface()
    c = s.getCanvas()
    vgrad(c, 0, 0, W, 520, ["#6e908a", "#86aaa2"])
    c.drawRect(_R(0, 500, W, 520), fill("#c8d8d4"))
    vgrad(c, 0, 520, W, 1330, ["#9abcb4", "#8fb0a8"])
    c.drawRect(_R(0, 1310, W, 1830), fill("#3e6a62"))
    c.drawRect(_R(0, 1310, W, 1330), fill("#dfe8e4"))
    for x in (280, 1600, 2920):
        c.drawRect(_R(x, 530, x + 580, 548), fill("#f4fbf8"))
        glow(c, x + 290, 560, 420, "#eaffff", 0.35)
    for (x0, y0, x1, y1) in ((2660, 520, 2640, 600), (2400, 740, 2330, 900), (2900, 640, 2870, 780)):
        c.drawLine(x0, y0, x1, y1, stroke("#6e8a84", 4))
    c.drawRect(_R(660, 830, 1180, 1830), fill("#e8ece4"))
    c.drawRect(_R(680, 850, 1160, 1830), fill("#3e7a6a"))
    c.drawRect(_R(1090, 1370, 1130, 1382), fill("#d8dcd8"))
    c.drawRect(_R(1520, 940, 1960, 1240), fill("#8a6a40"))
    c.drawRect(_R(1540, 960, 1940, 1220), fill("#d0a870"))
    for (x, y, col, rot) in ((1580, 990, "#f4f0e8", -2), (1700, 1040, "#f2e0a0", 3), (1860, 990, "#e8f0f4", 1),
                             (1990, 1050, "#f4d8d4", -3)):
        c.save()
        c.rotate(rot, x + 50, y + 70)
        c.drawRect(_R(x, y, x + 100 if x < 1900 else x + 90, y + 140), fill(col))
        c.restore()
    c.drawRect(_R(2700, 830, 3460, 1830), fill("#e8ece4"))
    for k in range(2):
        x0 = 2720 + k * 370
        c.drawRect(_R(x0, 850, x0 + 350, 1830), fill("#4a8a7a"))
        c.drawCircle(x0 + 175, 1140, 64, fill("#d8ece8"))
        c.drawCircle(x0 + 175, 1140, 64, stroke("#c8ccc8", 8))
        c.drawRect(_R(x0 + 145, 1380, x0 + 205, 1392), fill("#d8dcd8"))
    c.drawPath(rrect(2920, 720, 3240, 790, 8), fill("#2f5f9a"))
    bk.text(c, "WARD", 3080, 755, 44, "#ffffff")
    c.drawLine(0, 1430, W, 1430, stroke("#dcd6c4", 12))
    for x in range(60, W, 500):
        c.drawLine(x, 1430, x, 1470, stroke("#dcd6c4", 8))
    c.drawPath(rrect(3680, 1500, 3760, 1760, 36), fill("#b8282a"))
    c.drawRect(_R(3705, 1480, 3735, 1500), fill("#2a2c30"))
    c.drawRect(_R(0, 1640, 150, 1660), fill("#7a5230"))
    c.drawRect(_R(90, 1660, 110, 1820), fill("#2a2c30"))
    c.drawRect(_R(0, 1830, W, H), lin_paint((0, 1830), (0, H), ["#2e3e3c", "#1c2624"]))
    rng = random.Random(9)
    for _ in range(300):
        c.drawCircle(rng.uniform(0, W), rng.uniform(1850, H), rng.uniform(2, 5), fill("#6a807c", 0.5))
    for x in (560, 1900, 3240):
        c.drawPath(oval(x, 2000, 360, 30), fill("#a8c8c0", 0.12))
    tint(s, "#d8ece6", 0.12)
    _vignette(c, 0.5)
    slots = {"center": _flat_slot(1920, 1880, 0.9), "left": _flat_slot(500, 1880, 0.9), "right": _flat_slot(3300, 1880, 0.9),
             "door_left": _flat_slot(920, 1850, 0.88), "ward_door": _flat_slot(3080, 1850, 0.88)}
    return Scene(None, s.makeImageSnapshot(), slots=slots, baked_signs=bk.items, floor_y=1880)


# =================================================================== 6. staff locker room
def scene_phong_tu_do_nhan_vien(tod: str) -> Scene:
    bk = _Bake()
    s = new_surface()
    c = s.getCanvas()
    vgrad(c, 0, 0, W, 1340, ["#a4aca8", "#8e9692"])
    c.drawRect(_R(0, 1340, W, 1960), fill("#5a6260"))
    c.drawRect(_R(0, 1960, W, H), fill("#3a3e40"))
    for x in range(0, W, 340):
        c.drawLine(x, 1960, x - 140, H, stroke("#2a2e30", 4))
    labels = ["No.1", "No.2", "No.3", "No.4", "No.5", "No.6", "", "No.8"]
    lw = 270.0
    for i, lab in enumerate(labels):
        x0 = 360 + i * (lw + 10)
        c.drawRect(_R(x0, 700, x0 + lw, 1960), lin_paint((x0, 0), (x0 + lw, 0), ["#b4bac2", "#a2a8b0"]))
        c.drawRect(_R(x0, 700, x0 + lw, 730), fill("#c9ced6"))
        for k in range(4):
            c.drawRect(_R(x0 + 70, 800 + k * 30, x0 + lw - 70, 814 + k * 30), fill("#6a7078"))
        c.drawRect(_R(x0 + lw - 40, 1200, x0 + lw - 20, 1320), fill("#3a3e44"))
        c.drawRect(_R(x0 + 50, 1010, x0 + lw - 50, 1070), fill("#f4f4f0"))
        if lab:
            bk.text(c, lab, x0 + lw / 2, 1040, 40, "#2a3a6a", weight="semibold")
        else:
            for a in (35, -35):
                c.save()
                c.rotate(a, x0 + lw / 2, 1040)
                c.drawRect(_R(x0 - 10, 1010, x0 + lw + 10, 1070), fill("#e8c04a", 0.92))
                c.restore()
            bk.text(c, "DO NOT OPEN", x0 + lw / 2, 1240, 40, "#c8251e", max_w=lw - 30)
    c.drawRect(_R(560, 1720, 2700, 1760), fill("#8a5a38"))
    for x in (640, 2620):
        c.drawRect(_R(x - 14, 1760, x + 14, 1960), fill("#2a2c30"))
    c.drawRect(_R(2940, 800, 3500, 1180), fill("#a88050"))
    for k, col in enumerate(("#f4f4f0", "#f2e2a8", "#cfe4ec", "#f4f4f0", "#f2e2a8")):
        row, col_ = divmod(k, 3)
        c.drawRect(_R(2970 + col_ * 175, 830 + row * 175, 3110 + col_ * 175, 970 + row * 175), fill(col))
    for (x0, y0, x1, y1) in ((560, 60, 520, 400), (3700, 0, 3760, 260)):
        c.drawLine(x0, y0, x1, y1, stroke("#7a827e", 5))
    tint(s, "#d8e4e0", 0.15)
    _vignette(c, 0.5)
    slots = {"center": _flat_slot(1920, 2060, 1.05), "left": _flat_slot(300, 2060, 1.05), "right": _flat_slot(3200, 2060, 1.05)}
    return Scene(None, s.makeImageSnapshot(), slots=slots, baked_signs=bk.items, floor_y=2060)


# =================================================================== 7. staff pantry
def scene_pantry_benh_vien(tod: str) -> Scene:
    s = new_surface()
    c = s.getCanvas()
    vgrad(c, 0, 0, W, 1400, ["#a4aaa6", "#8e9490"])
    c.drawRect(_R(0, 1350, W, H), fill("#4a4e4c"))
    for k in range(4):
        x0 = 560 + k * 680
        c.drawRect(_R(x0, 400, x0 + 670, 870), lin_paint((0, 400), (0, 870), ["#e4cfa4", "#d4bc90"]))
        c.drawRect(_R(x0 + 300, 640, x0 + 370, 660), fill("#b89c6c"))
    _night_window(c, 2740, 530, 3550, 1080, seed=8, trees=True)
    c.drawRect(_R(150, 1320, 3690, 1360), fill("#ece4d4"))
    c.drawRect(_R(150, 1360, 3690, 1600), lin_paint((0, 1360), (0, 1600), ["#a88a66", "#8a6e4e"]))
    c.drawRect(_R(0, 1590, W, 1700), fill("#3e6a68"))
    c.drawRect(_R(0, 1700, W, 1716), fill("#9aa0a2"))
    c.drawRect(_R(0, 1716, W, H), fill("#22282a"))
    for k, col in enumerate(("#f4f4f0", "#d8402e", "#3a6ab0")):
        c.drawPath(rrect(1780 + k * 110, 1230, 1860 + k * 110, 1320, 8), fill(col))
    for x in (1230, 2160):
        c.drawPath(rrect(x - 110, 1470, x + 110, 1600, 16), fill("#f4f4f0"))
        c.drawPath(oval(x, 1480, 110, 22), fill("#5a3a24"))
        c.drawPath(oval(x, 1610, 170, 26), fill("#e8e8e4"))
    tint(s, "#e0e4e0", 0.12)
    _vignette(c, 0.45)
    slots = {"seat_left": _flat_slot(1230, 2160, 1.15, clip_bottom=1600), "seat_right": _flat_slot(2160, 2160, 1.15, clip_bottom=1600),
             "center": _flat_slot(1700, 2160, 1.15, clip_bottom=1600)}
    return Scene(None, s.makeImageSnapshot(), slots=slots, floor_y=2160)


# =================================================================== 8. village yard at sunset
def scene_san_nha_go_hoang_hon(tod: str) -> Scene:
    s = new_surface()
    c = s.getCanvas()
    vgrad(c, 0, 0, W, 1400, ["#d8b8a0", "#f2c890", "#f8dca8"])
    for (cx, cy, rx) in ((900, 200, 900), (2900, 160, 700)):
        c.drawPath(oval(cx, cy, rx, 60), fill("#f8e8d0", 0.5))
    glow(c, 2720, 920, 900, "#fff0c0", 0.8)
    c.drawCircle(2720, 920, 90, fill("#fffbe8"))
    c.drawRect(_R(0, 1380, W, H), lin_paint((0, 1380), (0, H), ["#b88a58", "#8a6438"]))
    # wooden house wall (left)
    c.drawRect(_R(0, 0, 1240, 1380), fill("#7a5030"))
    for x in range(0, 1240, 170):
        c.drawRect(_R(x, 0, x + 12, 1380), fill("#5a3820"))
    for x in (120, 1000):
        c.drawRect(_R(x, 0, x + 60, 1380), fill("#5e3a20"))
    c.drawRect(_R(0, 1340, 1500, 1400), fill("#a8764a"))
    c.drawRect(_R(0, 1400, 1700, 1450), fill("#b88a5a"))
    c.drawPath(rrect(240, 1560, 760, 1820, 60), fill("#b85a3a"))
    c.drawPath(oval(500, 1830, 300, 40), fill("#000000", 0.2))
    # palm tree (right)
    c.drawLine(3500, 1400, 3440, 300, stroke("#7a8a48", 46))
    for k in range(10):
        c.drawLine(3440, 340 + k * 110, 3510, 340 + k * 110, stroke("#5a6a30", 6))
    for a in range(0, 360, 36):
        rd = math.radians(a)
        c.drawLine(3440, 300, 3440 + math.cos(rd) * 260, 300 + math.sin(rd) * 200, stroke("#7a9a48", 30))
    # puddle + grass foreground
    c.drawPath(oval(2100, 1880, 900, 170), fill("#c8b090"))
    c.drawPath(oval(2100, 1880, 860, 150), lin_paint((0, 1730), (0, 2030), ["#e8d0a0", "#b8a07a"]))
    rng = random.Random(6)
    for _ in range(80):
        x = rng.uniform(0, W)
        h = rng.uniform(150, 420)
        c.drawLine(x, H, x + rng.uniform(-60, 60), H - h, stroke("#3a2a14", rng.uniform(10, 26), 0.55))
    _vignette(c, 0.4)
    slots = {"center": _flat_slot(1700, 1760, 0.7), "left": _flat_slot(1200, 1760, 0.7), "right": _flat_slot(2900, 1900, 0.95)}
    return Scene(None, s.makeImageSnapshot(), slots=slots, floor_y=1760)


# =================================================================== 9. old duty room with radio
def scene_phong_truc_cu_radio(tod: str) -> Scene:
    bk = _Bake()
    s = new_surface()
    c = s.getCanvas()
    vgrad(c, 0, 0, W, 1300, ["#3a3c36", "#4a4c44"])
    c.drawRect(_R(0, 1000, W, 1040), fill("#2a2c28"))
    c.drawRect(_R(0, 0, 420, 800), fill("#ece8de"))
    for row in range(4):
        for col_ in range(2):
            n = 10 + row * 7 + col_
            if n <= 31:
                bk.text(c, str(n), 60 + col_ * 130, 120 + row * 150, 70, "#2a2a2a", weight="semibold")
    c.drawRect(_R(3600, 0, W, 1100), fill("#24303a"))
    _rain(c, 60, 3, 0.6, 3600, 0, W, 1100, "#cfdcff", 0.02)
    for y in (200, 450, 700):
        c.drawRect(_R(3600, y, W, y + 30), fill("#5a6a78"))
    c.drawRect(_R(0, 1300, W, H), lin_paint((0, 1300), (0, H), ["#9a6a40", "#5a3a22"]))
    c.drawRect(_R(0, 1290, W, 1330), fill("#b07c4e"))
    for y in range(1450, H, 170):
        c.drawLine(0, y, W, y + 10, stroke("#4a2e1a", 4, 0.5))
    rx, ry = 2950.0, 1290.0
    glow(c, rx, ry - 200, 900, "#ffc87a", 0.45)
    c.drawPath(rrect(rx - 330, ry - 330, rx + 330, ry, 30), fill("#9a5a34"))
    c.drawPath(rrect(rx - 300, ry - 300, rx - 40, ry - 30, 14), fill("#5a3220"))
    for k in range(7):
        c.drawLine(rx - 280, ry - 270 + k * 36, rx - 60, ry - 270 + k * 36, stroke("#2a160c", 10))
    c.drawPath(rrect(rx + 10, ry - 290, rx + 290, ry - 170, 12), fill("#ffd890"))
    for k in range(2):
        c.drawCircle(rx + 80 + k * 140, ry - 90, 40, fill("#3a2016"))
    c.drawLine(rx + 300, ry - 330, rx + 430, ry - 820, stroke("#d8dcde", 8))
    c.drawRect(_R(80, 1180, 180, 1300), fill("#b0764a", 0.8))
    c.drawPath(oval(130, 1300, 120, 20), fill("#e8e4dc"))
    c.drawRect(_R(600, 1270, 840, 1290), fill("#f4f4f0"))
    _vignette(c, 0.6)
    slots = {"behind_desk": _flat_slot(1700, 2160, 1.3, clip_bottom=1300), "center": _flat_slot(1700, 2160, 1.3, clip_bottom=1300)}
    return Scene(None, s.makeImageSnapshot(), slots=slots, baked_signs=bk.items, floor_y=2160)


LIBRARY_SCENES = {
    "phong_benh_chung_dem": scene_phong_benh_chung_dem,
    "toa_benh_vien_mua_dem": scene_toa_benh_vien_mua_dem,
    "hanh_lang_tang4_benh_vien": scene_hanh_lang_tang4_benh_vien,
    "quay_truc_y_ta": scene_quay_truc_y_ta,
    "giuong_benh_canh_cua_so": scene_giuong_benh_canh_cua_so,
    "phong_tu_do_nhan_vien": scene_phong_tu_do_nhan_vien,
    "pantry_benh_vien": scene_pantry_benh_vien,
    "san_nha_go_hoang_hon": scene_san_nha_go_hoang_hon,
    "phong_truc_cu_radio": scene_phong_truc_cu_radio,
    "hanh_lang_benh_vien_ngang": scene_hanh_lang_benh_vien_ngang,
}

LIBRARY_TAGS = {
    "phong_benh_chung_dem": ["phòng bệnh", "phòng bệnh chung", "giường bệnh", "bệnh viện", "rèm", "giường 12", "ca đêm",
                             "hospital ward", "ward beds", "curtain", "night shift", "lights out"],
    "toa_benh_vien_mua_dem": ["bệnh viện", "toà nhà", "mặt tiền", "mưa", "đêm", "cửa sổ đỏ", "hospital building",
                              "exterior", "rain", "memorial wing"],
    "hanh_lang_tang4_benh_vien": ["hành lang", "bệnh viện", "tầng 4", "tay vịn", "biển chỉ dẫn", "hospital corridor",
                                  "floor 4", "handrails", "ward sign"],
    "quay_truc_y_ta": ["quầy trực", "y tá", "bảng chuông gọi", "đồng hồ", "bảng bệnh nhân", "nội quy", "nurse station",
                       "call panel", "patient board", "3 am"],
    "giuong_benh_canh_cua_so": ["giường bệnh", "cửa sổ", "mưa", "tủ đầu giường", "nút gọi", "rèm", "hospital bed",
                                "rainy window", "bedside", "curtain"],
    "phong_tu_do_nhan_vien": ["phòng thay đồ", "tủ đồ", "tủ khoá", "nhân viên", "băng dính chữ X", "locker room",
                              "staff lockers", "do not open", "bench"],
    "pantry_benh_vien": ["phòng nghỉ", "pantry", "quầy", "cà phê", "tủ bếp", "staff pantry", "break room", "coffee",
                         "counter"],
    "san_nha_go_hoang_hon": ["sân nhà", "nhà gỗ", "hoàng hôn", "vũng nước", "cây cau", "quê", "hồi tưởng",
                             "village yard", "wooden house", "sunset", "puddle", "flashback"],
    "hanh_lang_benh_vien_ngang": ["hành lang", "bệnh viện", "nhìn ngang", "cửa phòng", "cửa đôi", "bảng ghim",
                                  "bình chữa cháy", "tay vịn", "hospital corridor", "side view", "ward doors"],
    "phong_truc_cu_radio": ["phòng trực", "radio", "bàn gỗ", "lịch", "đêm mưa", "old duty room", "vintage radio",
                            "desk", "calendar"],
}

TOD_VI = {"monitor": "ban đêm, canh bên giường có máy theo dõi", "redwindow": "ban đêm, mưa, ô cửa đỏ", "call12": "ban đêm, giường 12 bấm chuông",
          "curtain": "ban đêm, sau rèm giường 12"}
TOD_EN = {"monitor": "night, bedside vigil with monitor", "dark": "night, lights out", "redwindow": "night, rain, red window", "call12": "night, bed 12 calling",
          "curtain": "night, behind the bed-12 curtain"}
TOD_SCHEMA = {"monitor": "night", "dark": "night", "redwindow": "night", "call12": "night", "curtain": "night"}
TOD_FLOW = {"monitor": "night, IV pole with vital monitor, visitor chair", "dark":"night, lights off, faint red glow", "redwindow": "night, heavy rain, one red-lit window",
            "call12": "night, one call light glowing red", "curtain": "night, pale translucent curtain in foreground"}
