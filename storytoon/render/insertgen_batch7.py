"""Batch-7 inserts -- old riverside kingdom under siege, time-travel story (provenance 'procedural_library').

Coconut-shell bowl with rice in water on a bamboo mat, charcoal city map drawn on wooden boards (+ route being drawn),
parchment map of an island capital ringed by three rivers (+ enemy camps / attack arrows), old canal map on a tablet,
cross-section diagram of a wall undermined by fire, chisel marks on a boat plank, hoe striking a glowing smoking hole,
gong on its frame at night, stone head in tree roots, clay oil lamps (days left), torch on a brick wall, phone with a
2 % battery lock screen (evening / morning / 3 %), dead black phone, photo of an old map with a low-battery banner.

ALL baked text is ENGLISH and generic. Pure ASCII source. Loaded by insertgen like batches 2-6.
"""
from __future__ import annotations

import math
import random

import skia

from .insertgen import _lin, _rad, _shadow, _status_bar, text
from .insertgen_batch2 import LH, LW, _begin, _blurred, _vignette, _wood_top
from . import locgen as _locgen  # noqa: F401  (load locgen first: it imports locgen_batch7 itself)
from .locgen_batch7 import _bricks, _gong, _smoke_column, _stone_head, _torch
from .skutil import fill, oval, poly, rrect, shade, stroke

RIVER = "#8fb0bc"
INKB = "#3a2a1c"
RED = "#c8352e"


def _R(l, t, r, b) -> skia.Rect:
    return skia.Rect.MakeLTRB(l, t, r, b)


def _dash(col, w, on, off, a=1.0):
    pt = stroke(col, w, a)
    pt.setPathEffect(skia.DashPathEffect.Make([on, off], 0))
    return pt


def _rough(col, w, a=1.0, seed=1):
    pt = stroke(col, w, a)
    pt.setPathEffect(skia.DiscretePathEffect.Make(18, 5, seed))
    return pt


def _with(fn, **defaults):
    def run(p, size):
        q = dict(defaults)
        q.update(p or {})
        return fn(q, size)
    run.__doc__ = fn.__doc__
    return run


# =================================================================== coconut bowl
def ins_coconut_bowl_rice(p, size):
    """Half coconut shell holding water with a few rice grains, on a diagonal bamboo mat."""
    s, c = _begin(size)
    c.drawRect(_R(0, 0, LW, LH), fill("#c8a860"))
    c.save()
    c.rotate(-28, LW / 2, LH / 2)
    for k in range(-20, 40):
        x = k * 150
        c.drawRect(_R(x, -2000, x + 128, 4000), fill(shade("#d4b46c", 0.06 * ((k % 3) - 1))))
        c.drawRect(_R(x + 128, -2000, x + 150, 4000), fill("#6a5428", 0.85))
    c.restore()
    c.drawRect(_R(0, 0, LW, LH), _rad(LW / 2, LH / 2, LW * 0.7, [("#000000", 0.0), ("#000000", 0.35)], [0.4, 1]))
    cx, cy, rw, rh = LW / 2, 1100.0, 760.0, 200.0
    c.drawPath(oval(cx + 30, 1780, 820, 120), _blurred("#000000", 0.45, 40))
    bowl = skia.Path()
    bowl.moveTo(cx - rw, cy)
    bowl.cubicTo(cx - rw, cy + 700, cx + rw, cy + 700, cx + rw, cy)
    bowl.close()
    c.drawPath(bowl, _lin((cx - rw, 0), (cx + rw, 0), ["#4a2c1a", "#7a4a2c", "#5a3420", "#3a2214"]))
    rng = random.Random(3)
    for _ in range(70):
        x = rng.uniform(cx - rw * 0.9, cx + rw * 0.9)
        y = rng.uniform(cy + 120, cy + 560)
        c.drawLine(x, y, x + rng.uniform(-30, 30), y + rng.uniform(20, 60), stroke("#a07050", 3, 0.7))
    c.drawPath(oval(cx, cy, rw, rh), fill("#5a3420"))
    c.drawPath(oval(cx, cy, rw - 24, rh - 14), fill("#3a2214"))
    c.drawPath(oval(cx, cy + 40, rw * 0.62, rh * 0.62), _rad(cx, cy + 30, rw * 0.62, ["#c8c4bc", "#9a968e"]))
    c.drawPath(oval(cx - 60, cy + 10, rw * 0.25, rh * 0.08), fill("#ffffff", 0.35))
    c.drawArc(_R(cx - rw + 10, cy - rh + 4, cx + rw - 10, cy + rh), 190, 160, False, stroke("#e8e0d0", 4, 0.6))
    for _ in range(int(p.get("grains", 11))):
        x, y = rng.uniform(cx - rw * 0.45, cx + rw * 0.45), rng.uniform(cy - rh * 0.25, cy + rh * 0.7)
        c.save()
        c.rotate(rng.uniform(0, 180), x, y)
        c.drawPath(oval(x, y, 34, 10), fill("#f6f2e8", 0.95))
        c.restore()
    return s.makeImageSnapshot()


# =================================================================== charcoal map on wooden boards
def ins_wood_map_city(p, size):
    """City plan drawn in charcoal on wooden boards: walls, canals, MARKET / TEMPLE / NE CORNER; route=True draws a line."""
    s, c = _begin(size)
    c.drawRect(_R(0, 0, LW, LH), fill("#6a5a3c"))
    for y in range(0, int(LH), 170):
        c.drawRect(_R(0, y, LW, y + 150), fill("#8a7550"))
        c.drawLine(0, y + 150, LW, y + 150, stroke("#2a2418", 20))
    c.save()
    c.rotate(-1.5, LW / 2, LH / 2)
    l, t, r, b = -60.0, 560.0, 3500.0, 2300.0
    c.drawRect(_R(l + 20, t + 30, r + 20, b + 30), _blurred("#000000", 0.45, 30))
    c.drawRect(_R(l, t, r, b), fill("#d4b484"))
    for k in range(1, 6):
        y = t + k * (b - t) / 6
        c.drawLine(l, y, r, y, stroke("#a88a5c", 8))
    rng = random.Random(4)
    for _ in range(40):
        y = rng.uniform(t, b)
        c.drawLine(rng.uniform(l, r), y, rng.uniform(l, r), y + rng.uniform(-6, 6), stroke("#b89868", 3, 0.7))
    c.drawPath(rrect(l + 60, t + 90, r - 120, b + 200, 60), _rough(INKB, 26, 0.9, 2))
    c.drawPath(rrect(l + 200, t + 260, r - 260, b + 200, 40), _dash(INKB, 12, 50, 36, 0.8))
    for x in (520, 1400, 2300, 3050):
        c.drawLine(x, t + 260, x + 8, b, _rough(INKB, 12, 0.85, x))
    for y in (t + 680, t + 1260):
        c.drawLine(l + 200, y, r - 260, y + 6, _rough(INKB, 12, 0.85, int(y)))
    c.drawPath(poly([(780, t + 420), (840, t + 250), (900, t + 420)]), fill(INKB))
    c.drawRect(_R(770, t + 420, 910, t + 470), fill(INKB))
    text(c, p.get("temple", "TEMPLE"), 690, t + 220, 70, INKB, "bold", "right")
    text(c, p.get("market", "MARKET"), 1900, t + 520, 90, INKB, "bold", "center")
    text(c, p.get("corner", "NE CORNER"), 2900, t + 330, 80, INKB, "bold", "center")
    for x in (2780, 2980):
        c.drawPath(poly([(x - 60, t + 560), (x, t + 400), (x + 60, t + 560)]), stroke(INKB, 14))
    if p.get("route"):
        c.drawLine(820, t + 560, 2050, t + 600, stroke("#1a120a", 46))
        c.drawCircle(820, t + 560, 60, fill("#1a120a"))
        c.drawCircle(2220, t + 610, 46, fill("#1a120a"))
        c.drawLine(2050, t + 600, 2230, t + 610, _dash("#1a120a", 10, 30, 20))
    c.restore()
    if p.get("route"):
        c.save()
        c.rotate(-35, 2060, 1150)
        c.drawPath(rrect(2030, 1150, 2090, 1700, 24), fill("#1e1a16"))
        c.drawPath(rrect(2030, 1150, 2090, 1200, 24), fill("#3a342e"))
        c.restore()
    _vignette(c, 0.5)
    return s.makeImageSnapshot()


# =================================================================== parchment map of the island capital
def _rivers(c, l, t, r, b) -> None:
    w = (r - l) * 0.04
    top = skia.Path()
    top.moveTo(l, t + (b - t) * 0.22)
    top.cubicTo(l + (r - l) * 0.3, t + (b - t) * 0.12, l + (r - l) * 0.6, t + (b - t) * 0.24, r, t + (b - t) * 0.2)
    west = skia.Path()
    west.moveTo(l + (r - l) * 0.06, t)
    west.cubicTo(l + (r - l) * 0.2, t + (b - t) * 0.4, l + (r - l) * 0.05, t + (b - t) * 0.8, l + (r - l) * 0.3, t + (b - t) * 0.88)
    west.cubicTo(l + (r - l) * 0.6, t + (b - t) * 0.95, l + (r - l) * 0.8, t + (b - t) * 0.82, r, t + (b - t) * 0.92)
    east = skia.Path()
    east.moveTo(r, t + (b - t) * 0.28)
    east.cubicTo(l + (r - l) * 0.86, t + (b - t) * 0.36, l + (r - l) * 0.9, t + (b - t) * 0.7, l + (r - l) * 0.8, t + (b - t) * 0.86)
    for pth in (top, west, east):
        c.drawPath(pth, stroke(RIVER, w, 0.85))


def ins_island_city_map(p, size):
    """Parchment card: walled island capital ringed by three rivers with canals; siege=True adds camps + attack arrows."""
    s, c = _begin(size)
    c.drawRect(_R(0, 0, LW, LH), _lin((0, 0), (0, LH), ["#2a2420", "#16120e"]))
    l, t, r, b = 740.0, 170.0, 3180.0, 1730.0
    _shadow(c, rrect(l, t, r, b, 18), 40, 24, 0.6)
    c.drawPath(rrect(l, t, r, b, 18), _lin((l, t), (l, b), ["#f6ecd0", "#eedfba"]))
    c.drawRect(_R(l, t, l + 14, b), fill("#d8a838"))
    for k in range(1, 40):
        c.drawLine(l, t + k * (b - t) / 40, r, t + k * (b - t) / 40, stroke("#e2d2a8", 2, 0.6))
    c.save()
    c.clipRect(_R(l, t, r, b))
    _rivers(c, l, t, r, b)
    cl, ct, cr, cb = l + (r - l) * 0.19, t + (b - t) * 0.26, l + (r - l) * 0.83, t + (b - t) * 0.8
    c.drawPath(rrect(cl, ct, cr, cb, (cb - ct) * 0.35), fill("#ead6a4"))
    for x in (0.25, 0.5, 0.68):
        c.drawLine(cl + (cr - cl) * x, ct, cl + (cr - cl) * (x + 0.04), cb, stroke(RIVER, 12))
    c.drawLine(cl, ct + (cb - ct) * 0.5, cr, ct + (cb - ct) * 0.46, stroke(RIVER, 12))
    c.drawPath(rrect(cl, ct, cr, cb, (cb - ct) * 0.35), stroke(INKB, 10))
    c.drawPath(rrect(cl + 16, ct + 16, cr - 16, cb - 16, (cb - ct) * 0.33), _dash("#a87a5a", 12, 34, 20))
    text(c, p.get("north_river", "NORTH RIVER"), l + (r - l) * 0.5, t + (b - t) * 0.16, 52, "#3a5a6a", "bold", "center")
    for (x, y, ang, lab) in ((l + (r - l) * 0.11, t + (b - t) * 0.52, 80, p.get("west_river", "WEST RIVER")),
                             (l + (r - l) * 0.9, t + (b - t) * 0.56, 80, p.get("east_river", "EAST RIVER"))):
        c.save()
        c.rotate(ang, x, y)
        text(c, lab, x, y, 48, "#3a5a6a", "bold", "center")
        c.restore()
    if p.get("siege"):
        rng = random.Random(5)
        for (fx, fy) in ((0.62, 0.12), (0.88, 0.2), (0.12, 0.42), (0.28, 0.95), (0.85, 0.86), (0.94, 0.44)):
            x, y = l + (r - l) * fx, t + (b - t) * fy
            c.drawPath(poly([(x - 30, y + 26), (x, y - 30), (x + 30, y + 26)]), fill(RED))
        px, py = l + (r - l) * 0.78, t + (b - t) * 0.3
        for (sx, sy) in ((0.62, 0.12), (0.94, 0.44), (0.9, 0.18)):
            x0, y0 = l + (r - l) * sx, t + (b - t) * sy
            ang = math.atan2(py - y0, px - x0)
            x1, y1 = px - math.cos(ang) * 50, py - math.sin(ang) * 50
            c.drawLine(x0, y0, x1, y1, stroke(RED, 14, 0.85))
            c.drawPath(poly([(x1 + math.cos(ang) * 40, y1 + math.sin(ang) * 40),
                             (x1 + math.cos(ang + 2.5) * 50, y1 + math.sin(ang + 2.5) * 50),
                             (x1 + math.cos(ang - 2.5) * 50, y1 + math.sin(ang - 2.5) * 50)]), fill(RED))
        c.drawCircle(px, py - 30, 34, fill(RED))
        c.drawPath(poly([(px - 26, py - 16), (px, py + 30), (px + 26, py - 16)]), fill(RED))
        c.drawCircle(px, py - 30, 12, fill("#ffffff"))
        c.drawPath(rrect(px - 150, py - 190, px + 150, py - 100, 14), fill("#2a2018"))
        text(c, p.get("pin", "NE CORNER"), px, py - 128, 48, "#f2e2b0", "bold", "center")
        text(c, p.get("camps", "ENEMY CAMPS"), l + (r - l) * 0.86, t + (b - t) * 0.08, 46, RED, "bold", "center")
        _ = rng
    c.restore()
    c.drawPath(rrect(l + 50, t + 40, l + 50 + 760, t + 140, 50), fill("#1e1812"))
    c.drawPath(rrect(l + 50, t + 40, l + 50 + 760, t + 140, 50), stroke("#c8a050", 4))
    text(c, p.get("title", "OLD CAPITAL MAP"), l + 430, t + 110, 56, "#f2d890", "bold", "center", max_w=680)
    _vignette(c, 0.4)
    return s.makeImageSnapshot()


# =================================================================== old canal map on a tablet
def ins_old_map_tablet(p, size):
    """Tablet on a wooden table showing a hand-drawn old map: canal grid, temples, walls, SOUTH GATE, north arrow."""
    s, c = _begin(size)
    _wood_top(c, "#a8865a")
    c.drawRect(_R(0, 0, LW, LH), fill("#e8c890", 0.2))
    c.save()
    c.rotate(-4, LW / 2, LH / 2)
    l, t, r, b = 860.0, 160.0, 2980.0, 1820.0
    _shadow(c, rrect(l, t, r, b, 70), 40, 30, 0.5)
    c.drawPath(rrect(l, t, r, b, 70), fill("#f4f2ee"))
    c.drawPath(rrect(LW / 2 - 110, t - 30, LW / 2 + 110, t + 30, 20), fill("#3a3a3e"))
    c.drawPath(rrect(l - 50, 720, l + 20, 1180, 30), fill("#f0c850"))
    ml, mt, mr, mb = l + 80, t + 80, r - 80, b - 80
    c.drawRect(_R(ml, mt, mr, mb), _lin((ml, mt), (mr, mb), ["#efe0bc", "#e2cc9c"]))
    c.save()
    c.clipRect(_R(ml, mt, mr, mb))
    _rivers(c, ml, mt + 60, mr, mb + 60)
    gl, gt, gr, gb = ml + 300, mt + 360, mr - 300, mb - 260
    for k in range(1, 5):
        x = gl + k * (gr - gl) / 5
        c.drawLine(x, gt, x + 10, gb, stroke(RIVER, 10))
    for k in (1, 2):
        y = gt + k * (gb - gt) / 3
        c.drawLine(gl, y, gr, y - 12, stroke(RIVER, 10))
    c.drawPath(rrect(gl, gt, gr, gb, 6), _dash("#5a3a22", 14, 34, 22))
    for (fx, fy) in ((0.15, 0.2), (0.35, 0.45), (0.62, 0.12), (0.85, 0.45), (0.55, 0.75), (0.25, 0.8)):
        x, y = gl + (gr - gl) * fx, gt + (gb - gt) * fy
        c.drawPath(poly([(x - 22, y + 26), (x, y - 26), (x + 22, y + 26)]), fill("#6a5038"))
    c.drawRect(_R((gl + gr) / 2 - 18, gb - 18, (gl + gr) / 2 + 18, gb + 18), fill("#4a3020"))
    text(c, p.get("title", "OLD CAPITAL"), (ml + mr) / 2, mt + 160, 92, "#5a3a22", "semibold", "center")
    text(c, p.get("gate", "SOUTH GATE"), (gl + gr) / 2, gb + 110, 52, "#5a3a22", "semibold", "center")
    text(c, p.get("temple", "GREAT TEMPLE"), gl + (gr - gl) * 0.35, gt + (gb - gt) * 0.6, 44, "#5a3a22", "semibold", "center")
    text(c, p.get("corner", "NE CORNER"), gr - 120, gt + 70, 44, "#5a3a22", "semibold", "center")
    nx, ny = mr - 180, mb - 160
    text(c, "N", nx, ny - 110, 52, "#5a3a22", "bold", "center")
    c.drawPath(poly([(nx, ny - 90), (nx + 26, ny + 20), (nx, ny), (nx - 26, ny + 20)]), fill("#3a2a1c"))
    c.restore()
    c.restore()
    _vignette(c, 0.45)
    return s.makeImageSnapshot()


# =================================================================== wall undermining diagram
def ins_wall_undermine_diagram(p, size):
    """Cross-section card: brick wall on a foundation, fire burning under it at the end of a tunnel, COLLAPSE arrow."""
    s, c = _begin(size)
    c.drawRect(_R(0, 0, LW, LH), _rad(LW / 2, LH / 2, LW * 0.7, ["#5a3a28", "#24160e"]))
    l, t, r, b = 820.0, 180.0, 3000.0, 1560.0
    _shadow(c, rrect(l, t, r, b, 18), 40, 24, 0.6)
    c.drawPath(rrect(l, t, r, b, 18), fill("#f4e8c8"))
    c.drawPath(rrect(l + 22, t + 120, r - 22, b - 22, 18), stroke("#b89a68", 6))
    for k in range(1, 18):
        y = t + 120 + k * 70
        c.drawLine(l + 40, y, r - 40, y, stroke("#e2d2a8", 2, 0.7))
    gy = t + 600
    c.drawRect(_R(l + 40, gy, r - 40, b - 120), fill("#e0cc9c"))
    c.drawLine(l + 40, gy, r - 40, gy, stroke("#3a2a1c", 6))
    wl, wr, wt = 1580.0, 2050.0, t + 210
    c.drawPath(poly([(wl, gy - 10), (wr, gy - 10), (wr - 60, wt), (wl + 60, wt)]), fill("#b8705a"))
    c.save()
    c.clipPath(poly([(wl, gy - 10), (wr, gy - 10), (wr - 60, wt), (wl + 60, wt)]))
    _bricks(c, wl, wt, wr, gy, 70, 30, "#c07a60", "#7a4636", seed=2, var=0.05, gap=4)
    c.restore()
    for k in range(5):
        c.drawRect(_R(wl + 50 + k * 80, wt - 50, wl + 100 + k * 80, wt), fill("#a8604a"))
    c.drawRect(_R(wl + 30, wt - 50, wr - 30, wt - 20), fill("#a8604a"))
    c.drawPath(poly([(wl - 50, gy + 130), (wr + 50, gy + 130), (wr + 20, gy), (wl - 20, gy)]), fill("#a8604a"))
    for x in (wl + 140, wl + 300):
        c.drawPath(poly([(x, gy + 40), (x + 30, gy - 80), (x - 10, gy - 150), (x + 20, gy - 260)]), stroke("#2a1a12", 6))
    c.drawPath(rrect(wl - 30, gy + 130, r - 40, gy + 230, 50), fill("#6a4a32"))
    c.drawPath(rrect(wl - 30, gy + 130, wr + 70, gy + 230, 30), fill("#4a3020"))
    for k in range(7):
        x = wl + 20 + k * 70
        col = RED if k % 2 else "#f0a030"
        fl = skia.Path()
        fl.moveTo(x - 30, gy + 210)
        fl.quadTo(x - 30, gy + 120, x, gy + 70)
        fl.quadTo(x + 30, gy + 120, x + 30, gy + 210)
        fl.close()
        c.drawPath(fl, fill(col))
        c.drawPath(fl, stroke("#5a2a1a", 4))
    ax = 2240.0
    c.drawLine(ax, t + 180, ax, gy - 60, stroke(RED, 14))
    c.drawPath(poly([(ax - 40, gy - 90), (ax + 40, gy - 90), (ax, gy - 20)]), fill(RED))
    text(c, p.get("collapse", "COLLAPSE!"), ax + 70, t + 340, 90, RED, "extrabold")
    text(c, p.get("inside", "INSIDE THE CITY"), 1180, gy - 40, 60, "#2a2018", "bold", "center")
    text(c, p.get("outside", "OUTSIDE THE WALL"), 2650, gy - 40, 60, "#2a2018", "bold", "center")
    ox, oy = 2880.0, gy - 230
    c.drawPath(poly([(ox - 90, oy + 80), (ox, oy - 60), (ox + 90, oy + 80)]), stroke(RED, 8))
    c.drawLine(ox, oy - 60, ox, oy - 160, stroke(RED, 6))
    c.drawPath(poly([(ox, oy - 160), (ox + 70, oy - 135), (ox, oy - 110)]), fill(RED))
    text(c, p.get("fire", "FIRE UNDER THE FOUNDATION"), 1820, gy + 330, 62, RED, "bold", "center")
    text(c, p.get("tunnel", "TUNNEL"), 2600, gy + 330, 62, "#2a2018", "bold", "center")
    rng = random.Random(3)
    for _ in range(50):
        c.drawCircle(rng.uniform(l + 60, r - 60), rng.uniform(gy + 260, b - 140), rng.uniform(3, 7), fill("#a89068", 0.6))
    c.drawPath(rrect(LW / 2 - 560, t - 10, LW / 2 + 560, t + 100, 50), fill("#1e1812"))
    c.drawPath(rrect(LW / 2 - 560, t - 10, LW / 2 + 560, t + 100, 50), stroke("#c8a050", 4))
    text(c, p.get("title", "WHY THE WALL FELL"), LW / 2, t + 70, 62, "#f2c870", "bold", "center")
    return s.makeImageSnapshot()


# =================================================================== chisel marks on a boat plank
def ins_boat_plank_chisel(p, size):
    """Close-up of a boat hull plank (diagonal) with fresh chisel nicks, scratches and curled wood shavings around."""
    s, c = _begin(size)
    c.drawRect(_R(0, 0, LW, LH), fill("#5a4430"))
    rng = random.Random(7)
    for _ in range(18):
        c.drawPath(poly([(rng.uniform(0, LW), rng.uniform(0, LH)) for _ in range(4)]), fill("#6a5038", 0.5))
    c.save()
    c.rotate(-14, LW / 2, LH / 2)
    l, r, t, b = -400.0, LW + 400, 800.0, 1600.0
    c.drawRect(_R(l, t - 60, r, t), fill("#c89a66"))
    c.drawRect(_R(l, t, r, b), _lin((0, t), (0, b), ["#e2b882", "#c8965e", "#a87848"]))
    for k in range(1, 6):
        c.drawLine(l, t + k * (b - t) / 6, r, t + k * (b - t) / 6, stroke("#b8884e", 4, 0.6))
    for _ in range(int(p.get("marks", 14))):
        x = rng.uniform(800, 3000)
        y = rng.uniform(t + 120, t + 400)
        c.drawArc(_R(x - 40, y - 20, x + 40, y + 30), 200, 140, False, stroke("#fff0d0", 12))
        c.drawArc(_R(x - 40, y - 14, x + 40, y + 36), 200, 140, False, stroke("#8a6038", 4, 0.6))
    for _ in range(26):
        x = rng.uniform(300, 3600)
        y = rng.uniform(t + 80, b - 80)
        c.drawLine(x, y, x + rng.uniform(-30, 30), y + rng.uniform(120, 300), stroke("#8a6038", 4, 0.7))
    c.restore()
    for _ in range(70):
        x, y = rng.uniform(0, LW), rng.choice([rng.uniform(0, 600), rng.uniform(1700, LH)])
        sz = rng.uniform(26, 60)
        c.drawArc(_R(x - sz, y - sz * 0.7, x + sz, y + sz * 0.7), rng.uniform(0, 360), rng.uniform(160, 280), False,
                  stroke("#e8d4a8", sz * 0.25, 0.85))
    _vignette(c, 0.55)
    return s.makeImageSnapshot()


# =================================================================== hoe into a glowing hole
def ins_hoe_glowing_hole(p, size):
    """Hoe blade stuck in a dark hole that glows orange, smoke and sparks rising; brick wall at the top of frame."""
    s, c = _begin(size)
    _bricks(c, 0, 0, LW, 520, 300, 90, "#b86a50", "#7a4434", seed=4, var=0.07, gap=14)
    c.drawRect(_R(0, 420, LW, LH), _lin((0, 420), (0, LH), ["#b89a72", "#8a6e4c"]))
    rng = random.Random(2)
    for _ in range(80):
        c.drawCircle(rng.uniform(0, LW), rng.uniform(520, LH), rng.uniform(8, 24), fill("#d4bc94", 0.6))
    hole = poly([(900, 1300), (1300, 1040), (1900, 1000), (2500, 1180), (2420, 1480), (2700, 1700), (1900, 1790), (1200, 1660)])
    c.drawPath(hole, fill("#1e140e"))
    c.drawPath(oval(1780, 1440, 520, 160), _rad(1780, 1440, 520, [("#ff9a40", 0.95), ("#d85a20", 0.6), ("#d85a20", 0.0)]))
    _smoke_column(c, 1700, 1100, -200, 220, 5, "#4a4440", 0.55)
    for _ in range(60):
        c.drawCircle(rng.uniform(1300, 2300), rng.uniform(700, 1500), rng.uniform(4, 9), fill("#ffb860", rng.uniform(0.5, 1)))
    c.save()
    c.rotate(-8, 1650, 1300)
    c.drawPath(poly([(1260, 1500), (1360, 1050), (1820, 1000), (1900, 1420)]), _lin((1260, 1000), (1900, 1500), ["#9a9ea4", "#6a6e74"]))
    c.drawLine(1260, 1500, 1900, 1420, stroke("#e2e6ea", 14))
    c.drawRect(_R(1500, 1130, 1650, 1170), fill("#b86a40"))
    c.restore()
    c.drawLine(1820, 1060, 3500, -200, stroke("#c8a66a", 90))
    c.drawLine(1820, 1060, 3500, -200, stroke("#e2c48a", 24, 0.6))
    _vignette(c, 0.5)
    return s.makeImageSnapshot()


# =================================================================== gong at night
def ins_gong_night(p, size):
    """Bronze gong hanging in its wooden frame at night, stilt houses and water dark behind."""
    s, c = _begin(size)
    c.drawRect(_R(0, 0, LW, LH), _lin((0, 0), (0, LH), ["#1a2238", "#202a44", "#141a2a"]))
    for x in (300, 1300, 2700, 3500):
        c.drawPath(poly([(x - 260, 900), (x, 600), (x + 260, 900)]), fill("#2a3248"))
        c.drawRect(_R(x - 220, 900, x + 220, 1200), fill("#262e44"))
        for k in range(5):
            c.drawRect(_R(x - 210 + k * 100, 1200, x - 200 + k * 100, 1350), fill("#262e44"))
    c.drawRect(_R(2850, 960, 2940, 1060), fill("#d8a870", 0.8))
    c.drawRect(_R(0, 1350, LW, LH), fill("#121828"))
    for k in range(30):
        y = 1400 + k * 26
        c.drawLine((k * 397) % LW, y, (k * 397) % LW + 160, y, stroke("#2a3450", 4))
    c.drawRect(_R(1000, 1300, 2840, LH), _lin((0, 1300), (0, LH), ["#5a3e28", "#3a2818"]))
    for y in range(1340, int(LH), 80):
        c.drawLine(1000, y, 2840, y, stroke("#2a1c10", 6))
    _gong(c, LW / 2, 130, 440, 1720, 2100, wood="#5a3e28", bronze="#a8804a")
    glow_p = _rad(LW / 2 - 100, 900, 700, [("#ffd890", 0.25), ("#ffd890", 0.0)])
    c.drawCircle(LW / 2 - 100, 900, 700, glow_p)
    _vignette(c, 0.55)
    return s.makeImageSnapshot()


# =================================================================== stone head in tree roots
def ins_stone_head_roots(p, size):
    """Close-up: weathered stone head with closed eyes embraced by grey tree roots."""
    s, c = _begin(size)
    c.drawRect(_R(0, 0, LW, LH), _lin((0, 0), (LW, 0), ["#7a7476", "#9c9696", "#8a8486", "#6a6466"]))
    rng = random.Random(4)
    for k in range(16):
        x = k * 260 + rng.uniform(-40, 40)
        c.drawLine(x, 0, x + rng.uniform(-80, 80), LH, stroke("#6a6466", rng.uniform(20, 50), 0.6))
    cx, cy = LW / 2, 1120.0
    c.drawPath(oval(cx, cy + 40, 640, 720), fill("#4a4446"))
    _stone_head(c, cx, cy + 80, 460, p.get("stone", "#aaa49e"))
    for sx in (-1, 1):
        pth = skia.Path()
        pth.moveTo(cx + sx * 1100, 0)
        pth.cubicTo(cx + sx * 600, 300, cx + sx * 300, 280, cx - sx * 200, 520)
        c.drawPath(pth, stroke("#8c8688", 150))
        c.drawPath(pth, stroke("#a49ea0", 40, 0.6))
        p2 = skia.Path()
        p2.moveTo(cx + sx * 760, 400)
        p2.cubicTo(cx + sx * 820, 1000, cx + sx * 700, 1600, cx + sx * 900, LH)
        c.drawPath(p2, stroke("#8a8486", 190))
        c.drawPath(p2, stroke("#a8a2a4", 50, 0.5))
    c.drawPath(oval(cx, LH, 1400, 260), fill("#3a3a30"))
    for _ in range(30):
        x = rng.uniform(0, LW)
        c.drawLine(x, LH, x + rng.uniform(-40, 40), LH - rng.uniform(80, 220), stroke("#5a6a3a", 10, 0.8))
    _vignette(c, 0.5)
    return s.makeImageSnapshot()


# =================================================================== clay oil lamps
def ins_clay_oil_lamps(p, size):
    """Row of three clay oil lamps on a dark wooden board; `lit` of them still burning (days left)."""
    s, c = _begin(size)
    c.drawRect(_R(0, 0, LW, LH), _lin((0, 0), (0, LH), ["#1e1612", "#2e2018"]))
    c.drawRect(_R(0, 1400, LW, LH), _lin((0, 1400), (0, LH), ["#4a3020", "#2a1a10"]))
    lit = int(p.get("lit", 2))
    for k in range(3):
        x, y = 1020 + k * 900, 1460.0
        if k < lit:
            c.drawCircle(x, y - 380, 700, _rad(x, y - 380, 700, [("#ffb050", 0.35), ("#ffb050", 0.0)]))
        c.drawPath(oval(x, y + 70, 380, 60), _blurred("#000000", 0.5, 20))
        bowl = skia.Path()
        bowl.moveTo(x - 360, y - 60)
        bowl.cubicTo(x - 320, y + 120, x + 320, y + 120, x + 360, y - 60)
        bowl.close()
        c.drawPath(bowl, _lin((x - 360, 0), (x + 360, 0), ["#7a4a2a", "#a8683a", "#6a3e22"]))
        c.drawPath(oval(x, y - 60, 360, 70), fill("#5a3420"))
        c.drawPath(oval(x, y - 54, 300, 52), fill("#3a2012" if k >= lit else "#6a4a22"))
        c.drawLine(x - 40, y - 60, x + 30, y - 110, stroke("#d8c8a8", 14))
        if k < lit:
            fl = skia.Path()
            fl.moveTo(x + 30, y - 380)
            fl.cubicTo(x + 110, y - 260, x + 90, y - 120, x + 30, y - 110)
            fl.cubicTo(x - 30, y - 120, x - 50, y - 260, x + 30, y - 380)
            c.drawPath(fl, fill("#ff9a30"))
            c.drawPath(oval(x + 30, y - 180, 30, 60), fill("#fff0b0"))
        else:
            for j in range(4):
                c.drawCircle(x + 30 + math.sin(j) * 30, y - 160 - j * 90, 30 + j * 12, _blurred("#8a8480", 0.3, 20))
    _vignette(c, 0.6)
    return s.makeImageSnapshot()


# =================================================================== torch on a brick wall
def ins_wall_torch_brick(p, size):
    """Burning torch in an iron bracket on a dark brick wall, warm light falloff."""
    s, c = _begin(size)
    _bricks(c, 0, 0, LW, LH, 340, 120, "#8a4a36", "#3a2018", seed=6, var=0.1, gap=16)
    c.drawRect(_R(0, 0, LW, LH), fill("#140a06", 0.45))
    tx, ty = LW / 2, 700.0
    c.drawCircle(tx, ty, 1500, _rad(tx, ty, 1500, [("#ffa040", 0.45), ("#ffa040", 0.12), ("#ffa040", 0.0)], [0, 0.4, 1]))
    c.drawRect(_R(tx - 140, ty + 820, tx + 140, ty + 900), fill("#2a2420"))
    c.drawLine(tx, ty + 860, tx - 20, ty + 700, stroke("#2a2420", 30))
    _torch(c, tx, ty, 2.4, lit=True)
    _vignette(c, 0.6)
    return s.makeImageSnapshot()


# =================================================================== phone screens
def _wallpaper_temple(c, sl, st, sr, sb) -> None:
    sw, sh = sr - sl, sb - st
    c.drawRect(_R(sl, st, sr, sb), _lin((sl, st), (sl, sb), ["#4a4870", "#8a6a88", "#d88a6a", "#e8a060"]))
    by = sb - sh * 0.1
    c.drawPath(poly([(sl + sw * 0.12, by), (sl + sw * 0.2, st + sh * 0.58), (sl + sw * 0.28, by)]), fill("#2a1c28"))
    c.drawPath(poly([(sl + sw * 0.42, by), (sl + sw * 0.48, st + sh * 0.68), (sl + sw * 0.54, by)]), fill("#2a1c28"))
    c.drawPath(oval(sl + sw * 0.86, by, sw * 0.3, sh * 0.1), fill("#2a1c28"))
    c.drawRect(_R(sl, by, sr, sb), fill("#2a1c28"))


def _screen_lowbatt(c, sl, st, sr, sb, d: dict) -> None:
    """Lock screen: date, big time, low-battery widget (ring + % + 'No signal'), temple sunset wallpaper."""
    sw, sh = sr - sl, sb - st
    _wallpaper_temple(c, sl, st, sr, sb)
    pct = str(d.get("battery", "2"))
    text(c, d.get("time") or "18:31", sl + sw * 0.12, st + sh * 0.035, sh * 0.02, "#ffffff", "semibold")
    text(c, d.get("carrier", "No service"), sr - sw * 0.33, st + sh * 0.035, sh * 0.016, "#ffffff", "semibold", "right")
    text(c, pct + "%", sr - sw * 0.2, st + sh * 0.035, sh * 0.016, "#ff4a40", "semibold", "right")
    c.drawPath(rrect(sr - sw * 0.18, st + sh * 0.02, sr - sw * 0.07, st + sh * 0.04, sh * 0.005), stroke("#ffffff", 3))
    c.drawRect(_R(sr - sw * 0.175, st + sh * 0.024, sr - sw * 0.165, st + sh * 0.036), fill("#ff4a40"))
    c.drawPath(rrect(sl + sw / 2 - sw * 0.16, st + sh * 0.012, sl + sw / 2 + sw * 0.16, st + sh * 0.045, sh * 0.016), fill("#000000"))
    text(c, d.get("date", "Sunday, April 5"), sl + sw / 2, st + sh * 0.11, sh * 0.024, "#ffffff", "semibold", "center")
    text(c, d.get("time") or "18:31", sl + sw / 2, st + sh * 0.23, sh * 0.12, "#ffffff", "bold", "center", max_w=sw * 0.9)
    cl, ct, cr, cb = sl + sw * 0.08, st + sh * 0.28, sr - sw * 0.08, st + sh * 0.37
    c.drawPath(rrect(cl, ct, cr, cb, sh * 0.02), fill("#2a2236", 0.75))
    rx, ry, rr = cl + sw * 0.13, (ct + cb) / 2, sh * 0.028
    c.drawCircle(rx, ry, rr, stroke("#5a5468", sh * 0.005))
    c.drawArc(_R(rx - rr, ry - rr, rx + rr, ry + rr), -90, 360 * max(0.04, float(pct) / 100 * 5), False, stroke("#ff4a40", sh * 0.005))
    text(c, pct + "%", rx, ry + sh * 0.006, sh * 0.016, "#ff4a40", "bold", "center")
    text(c, d.get("widget", "Low battery"), cl + sw * 0.27, ry - sh * 0.004, sh * 0.02, "#ffffff", "bold", max_w=sw * 0.55)
    text(c, d.get("signal", "x  No signal"), cl + sw * 0.3, ry + sh * 0.026, sh * 0.016, "#ff7a70", "semibold")
    for cx_ in (sl + sw * 0.18, sr - sw * 0.18):
        c.drawCircle(cx_, sb - sh * 0.065, sw * 0.07, fill("#000000", 0.35))
    c.drawPath(rrect(sl + sw * 0.32, sb - sh * 0.02, sr - sw * 0.32, sb - sh * 0.013, sh * 0.004), fill("#ffffff"))


def _screen_off(c, sl, st, sr, sb, d: dict) -> None:
    c.drawRect(_R(sl, st, sr, sb), _lin((sl, st), (sr, sb), ["#1a1616", "#0c0a0a", "#16120e"]))
    c.drawPath(poly([(sl + (sr - sl) * 0.6, st), (sr, st), (sl + (sr - sl) * 0.2, sb), (sl, sb), (sl, sb - (sb - st) * 0.1)]),
               fill("#ffffff", 0.03))


def _screen_map_photo(c, sl, st, sr, sb, d: dict) -> None:
    """Photo viewer with an old map photo, caption, red 'battery low' banner."""
    sw, sh = sr - sl, sb - st
    c.drawRect(_R(sl, st, sr, sb), fill("#0a0a0c"))
    _status_bar(c, sl, st + sh * 0.012, sr, sh * 0.045, d.get("time") or "20:13")
    text(c, "< " + d.get("back", "Photos"), sl + sw * 0.06, st + sh * 0.12, sh * 0.024, "#3a8aff", "semibold")
    text(c, d.get("title", "Old canal map"), sl + sw * 0.4, st + sh * 0.12, sh * 0.024, "#ffffff", "bold", max_w=sw * 0.56)
    pl, pt, pr, pb = sl, st + sh * 0.22, sr, st + sh * 0.56
    c.drawRect(_R(pl, pt, pr, pb), fill("#ead8b0"))
    c.save()
    c.clipRect(_R(pl, pt, pr, pb))
    _rivers(c, pl - sw * 0.05, pt, pr + sw * 0.05, pb)
    gl, gt, gr, gb = pl + sw * 0.15, pt + (pb - pt) * 0.28, pr - sw * 0.15, pb - (pb - pt) * 0.18
    for k in range(1, 4):
        c.drawLine(gl + k * (gr - gl) / 4, gt, gl + k * (gr - gl) / 4, gb, stroke(RIVER, 4))
    c.drawLine(gl, (gt + gb) / 2, gr, (gt + gb) / 2, stroke(RIVER, 4))
    c.drawPath(rrect(gl, gt, gr, gb, 4), _dash("#4a3020", 5, 14, 8))
    text(c, "OLD CAPITAL", (pl + pr) / 2, pt + (pb - pt) * 0.17, sh * 0.02, "#4a3020", "semibold", "center")
    c.drawRect(_R((gl + gr) / 2 - 8, gb - 8, (gl + gr) / 2 + 8, gb + 8), fill("#4a3020"))
    text(c, "SOUTH GATE", (gl + gr) / 2, gb + (pb - pt) * 0.1, sh * 0.012, "#4a3020", "semibold", "center")
    c.restore()
    text(c, d.get("caption", "Taken 2 years ago - Historical Park"), sl + sw / 2, st + sh * 0.62, sh * 0.017, "#9a9aa2",
         "semibold", "center", max_w=sw * 0.9)
    bl, bt, br, bb = sl + sw * 0.05, st + sh * 0.7, sr - sw * 0.05, st + sh * 0.79
    c.drawPath(rrect(bl, bt, br, bb, sh * 0.02), fill("#5a1a1a"))
    text(c, d.get("warn", "Battery 2%"), sl + sw / 2, bt + sh * 0.04, sh * 0.026, "#ff6a5a", "bold", "center")
    text(c, d.get("warn_sub", "Phone will turn off soon"), sl + sw / 2, bt + sh * 0.072, sh * 0.016, "#e8c0b8", "semibold", "center")


SCREENS = {"lowbatt": _screen_lowbatt, "off": _screen_off, "map_photo": _screen_map_photo}


def _phone(screen, defaults):
    from .insertgen_batch2 import _phone_in_hand

    def run(p, size):
        q = dict(defaults)
        q.update(p or {})
        return _phone_in_hand(screen, q, size)
    return run


# =================================================================== registration
INSERTS = {
    "coconut_bowl_rice": ins_coconut_bowl_rice,
    "wood_map_city": ins_wood_map_city,
    "wood_map_city_route": _with(ins_wood_map_city, route=True),
    "island_city_map": ins_island_city_map,
    "island_city_map_siege": _with(ins_island_city_map, siege=True, title="SIEGE CAMPS AROUND THE CITY"),
    "old_map_tablet": ins_old_map_tablet,
    "wall_undermine_diagram": ins_wall_undermine_diagram,
    "boat_plank_chisel": ins_boat_plank_chisel,
    "hoe_glowing_hole": ins_hoe_glowing_hole,
    "gong_night": ins_gong_night,
    "stone_head_roots": ins_stone_head_roots,
    "clay_oil_lamps": ins_clay_oil_lamps,
    "clay_oil_lamps_one": _with(ins_clay_oil_lamps, lit=1),
    "clay_oil_lamps_three": _with(ins_clay_oil_lamps, lit=3),
    "wall_torch_brick": ins_wall_torch_brick,
    "phone_lowbatt_lock": _phone("lowbatt", {"time": "18:31", "date": "Sunday, April 5", "battery": "2"}),
    "phone_lowbatt_lock_morning": _phone("lowbatt", {"time": "06:18", "date": "Sunday, April 5", "battery": "2"}),
    "phone_lowbatt_lock_3pct": _phone("lowbatt", {"time": "17:31", "date": "Saturday, April 4", "battery": "3"}),
    "phone_dead_black": _phone("off", {}),
    "phone_map_photo": _phone("map_photo", {"time": "20:13"}),
}

TAGS = {
    "coconut_bowl_rice": ["coconut bowl", "rice", "water", "ration", "bamboo mat", "hunger"],
    "wood_map_city": ["map", "charcoal map", "wooden boards", "city plan", "market", "temple"],
    "wood_map_city_route": ["map", "drawing route", "charcoal line", "plan", "escape route"],
    "island_city_map": ["map", "old capital", "three rivers", "island city", "canals", "walls"],
    "island_city_map_siege": ["siege map", "enemy camps", "attack arrows", "ne corner", "war"],
    "old_map_tablet": ["tablet", "old map", "canals", "south gate", "tour guide", "history"],
    "wall_undermine_diagram": ["diagram", "wall collapse", "tunnel", "fire under foundation", "siege tactic"],
    "boat_plank_chisel": ["boat plank", "chisel marks", "wood shavings", "boat building", "carving"],
    "hoe_glowing_hole": ["hoe", "digging", "glowing hole", "smoke", "embers", "tunnel found"],
    "gong_night": ["gong", "alarm", "night", "bronze gong", "wooden frame"],
    "stone_head_roots": ["stone head", "tree roots", "ruins", "statue head", "ancient"],
    "clay_oil_lamps": ["oil lamps", "days left", "countdown", "clay lamp", "flame"],
    "clay_oil_lamps_one": ["oil lamps", "one day left", "countdown", "last flame"],
    "clay_oil_lamps_three": ["oil lamps", "three days left", "countdown", "all lit"],
    "wall_torch_brick": ["torch", "brick wall", "dungeon", "firelight", "night"],
    "phone_lowbatt_lock": ["phone", "low battery", "2 percent", "lock screen", "no signal", "time travel"],
    "phone_lowbatt_lock_morning": ["phone", "low battery", "morning", "lock screen", "no signal"],
    "phone_lowbatt_lock_3pct": ["phone", "3 percent", "low battery", "lock screen", "no signal"],
    "phone_dead_black": ["phone", "dead phone", "black screen", "battery died"],
    "phone_map_photo": ["phone", "photo of map", "old map", "battery warning", "turning off"],
}

PROPS = {k: [k] for k in INSERTS}
PROPS.update({
    "coconut_bowl_rice": ["coconut_bowl", "coconut_shell_bowl", "rice_ration"],
    "wood_map_city": ["charcoal_map", "wood_map"],
    "island_city_map": ["old_capital_map", "city_map_rivers"],
    "island_city_map_siege": ["siege_map", "enemy_camps_map"],
    "gong_night": ["gong", "hanging_gong"],
    "clay_oil_lamps": ["oil_lamps", "clay_lamps", "diya"],
    "wall_torch_brick": ["wall_torch", "burning_torch"],
    "phone_dead_black": ["dead_phone", "black_phone"],
})
