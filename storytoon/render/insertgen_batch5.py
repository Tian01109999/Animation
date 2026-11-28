"""Batch-5 inserts -- extended library (provenance 'procedural_library'), same flat-vector style as insertgen.

Theme: hospital night-shift horror (nurse call panel, 3 AM wall clock, night-shift rules note, nurse roster,
call-bell log, ward patient whiteboard, beige desk phone, paper boat, unfolded "SORRY" note, torn childhood photo,
nurse cap on a plastic-wrapped bed, nurse fob watch, key ring on a belt, bed call button, vital-signs monitor, wet
footprints, plastic-wrapped bed, old glowing radio, taped "DO NOT OPEN" locker, uniform on a hanger).

Every drawing is ORIGINAL code (skia); no brands/logos. ALL baked-in text is ENGLISH and generic (people are
initials, places are generic such as "WARD 4") and comes from params (editable in the catalog or sidecar).
This source file is kept pure ASCII on purpose.

Logical 3840x2160 coordinates. Loaded by insertgen at the end of the module (like batches 2-4).
"""
from __future__ import annotations

import math
import random

import skia

from .insertgen import _lin, _rad, _shadow, _tape, text
from .insertgen_batch2 import LH, LW, _begin, _blurred, _vignette, _wood_top
from .insertgen_batch3 import _soft_glow
from .skutil import capsule, fill, oval, poly, rrect, shade, stroke

INK = "#25407a"
RED = "#c8352e"
TEAL_WALL = "#86ada5"


def _R(l, t, r, b) -> skia.Rect:
    return skia.Rect.MakeLTRB(l, t, r, b)


# =================================================================== shared helpers
def _wall(c, col=TEAL_WALL, dado=True) -> None:
    """Blurred hospital wall: teal gradient, darker dado band, soft light spot."""
    c.drawRect(_R(0, 0, LW, LH), _lin((0, 0), (0, LH), [shade(col, 0.08), col, shade(col, -0.15)]))
    if dado:
        c.drawRect(_R(0, LH * 0.8, LW, LH), fill(shade(col, -0.45)))
        c.drawRect(_R(0, LH * 0.8 - 14, LW, LH * 0.8), fill("#dfe8e4", 0.6))
    c.drawCircle(LW * 0.5, LH * 0.35, LW * 0.45, _rad(LW * 0.5, LH * 0.35, LW * 0.45, [("#ffffff", 0.18), ("#ffffff", 0.0)]))


def _clock(c, cx, cy, R, hour, minute, face="#f4f1ea", rim="#2e3438", second=None) -> None:
    c.drawCircle(cx + R * 0.05, cy + R * 0.08, R * 1.04, _blurred("#000000", 0.4, R * 0.08))
    c.drawCircle(cx, cy, R, fill(rim))
    c.drawCircle(cx, cy, R * 0.9, _rad(cx, cy - R * 0.3, R * 1.1, [shade(face, 0.06), face, shade(face, -0.1)]))
    for k in range(60):
        a = k / 60 * math.tau - math.pi / 2
        big = k % 5 == 0
        r0 = R * (0.72 if big else 0.8)
        c.drawLine(cx + math.cos(a) * r0, cy + math.sin(a) * r0, cx + math.cos(a) * R * 0.84, cy + math.sin(a) * R * 0.84,
                   stroke("#2a2c33", R * (0.035 if big else 0.012)))
    ha = math.radians((hour % 12 + minute / 60) * 30 - 90)
    ma = math.radians(minute * 6 - 90)
    for a, ln, w in ((ha, 0.48, 0.06), (ma, 0.7, 0.04)):
        c.drawLine(cx, cy, cx + math.cos(a) * R * ln, cy + math.sin(a) * R * ln, stroke("#1d1f24", R * w))
    if second is not None:
        sa = math.radians(second * 6 - 90)
        c.drawLine(cx - math.cos(sa) * R * 0.15, cy - math.sin(sa) * R * 0.15, cx + math.cos(sa) * R * 0.75,
                   cy + math.sin(sa) * R * 0.75, stroke(RED, R * 0.015))
    c.drawCircle(cx, cy, R * 0.06, fill(RED))
    c.drawArc(_R(cx - R * 0.8, cy - R * 0.8, cx + R * 0.8, cy + R * 0.8), 200, 60, False, stroke("#ffffff", R * 0.08, 0.3))


def _paper(c, l, t, r, b, rot=0.0, col="#f2ead6", tape=True) -> None:
    c.save()
    c.rotate(rot, (l + r) / 2, (t + b) / 2)
    pth = rrect(l, t, r, b, 10)
    _shadow(c, pth, 40, 24, 0.5)
    c.drawPath(pth, _lin((l, t), (r, b), [shade(col, 0.04), col, shade(col, -0.06)]))
    if tape:
        _tape(c, l + (r - l) * 0.22, t + 6, 300, 90, -3)
        _tape(c, r - (r - l) * 0.22, t + 6, 300, 90, 4)
    c.restore()


def _blur_props(c, seed=3) -> None:
    """Out-of-focus desk clutter along the bottom (files, mug)."""
    rng = random.Random(seed)
    for x0 in (300, 1500, 2900):
        w = rng.uniform(380, 640)
        c.drawPath(rrect(x0, LH - 330, x0 + w, LH - 170, 20), _blurred(rng.choice(["#e8e4da", "#3a5a8a", "#cfd6dc"]), 0.75, 30))


# =================================================================== nurse call panel
def ins_nurse_call_panel(p, size):
    """Wall-mounted nurse-call panel: dark header, 12 maroon bed buttons; lit beds glow red. Optional wall clock."""
    s, c = _begin(size)
    _wall(c)
    l, t, r, b = 420.0, 360.0, 2700.0, 1640.0
    pane = rrect(l, t, r, b, 40)
    _shadow(c, pane, 40, 26, 0.45)
    c.drawPath(pane, _lin((l, t), (l, b), ["#f1eee6", "#e2ddd2"]))
    c.drawPath(rrect(l + 60, t + 50, r - 60, t + 200, 24), fill("#4a4c52"))
    text(c, p.get("title", "NURSE CALL"), (l + r) / 2, t + 150, 84, "#f3f1ea", "bold", "center", max_w=r - l - 200)
    lit = {int(x) for x in p.get("lit", [12])}
    n = int(p.get("beds", 12))
    cols = 6
    bw, bh = 290.0, 400.0
    gx = (r - l - 120 - cols * bw) / (cols - 1)
    for i in range(n):
        row, col_ = divmod(i, cols)
        x = l + 60 + col_ * (bw + gx)
        y = t + 290 + row * (bh + 90)
        on = (i + 1) in lit
        if on:
            c.drawPath(rrect(x - 30, y - 30, x + bw + 30, y + bh + 30, 50), _blurred("#ff5a3a", 0.75, 50))
        btn = rrect(x, y, x + bw, y + bh, 34)
        c.drawPath(btn, _lin((x, y), (x, y + bh), ["#ff7a5a", "#e8432e"] if on else ["#7a2a26", "#5a1c1a"]))
        c.drawPath(rrect(x + 12, y + 12, x + bw - 12, y + bh * 0.35, 26), fill("#ffffff", 0.18 if on else 0.06))
        text(c, str(i + 1), x + bw / 2, y + bh * 0.62, 150, "#ffffff" if on else "#c98a80", "bold", "center", a=0.95)
    if p.get("clock", True):
        _clock(c, 3260, 520, 300, float(p.get("hour", 3)), float(p.get("minute", 0)))
    if p.get("soft_focus", False):
        pass
    _vignette(c, 0.45)
    return s.makeImageSnapshot()


# =================================================================== wall clock
def ins_wall_clock(p, size):
    """Wall clock on the nurse-station wall at 3 AM, out-of-focus panel and whiteboard edges at the sides."""
    s, c = _begin(size)
    _wall(c)
    c.drawPath(rrect(-120, 900, 560, 2000, 24), _blurred("#eeeae2", 0.9, 26))
    for k in range(2):
        c.drawPath(rrect(60 + k * 260, 1150, 280 + k * 260, 1450, 30), _blurred("#7a2a26", 0.9, 22))
    c.drawPath(rrect(3260, 860, 4000, 2160, 24), _blurred("#f7f7f4", 0.95, 26))
    for k in range(4):
        c.drawRect(_R(3360, 1100 + k * 230, 3460, 1180 + k * 230), _blurred("#3a5aa0", 0.6, 18))
    c.drawLine(1920, 380, 1950, 640, _blurred("#3a4a48", 0.5, 4))
    _clock(c, 1920, 1080, 480, float(p.get("hour", 3)), float(p.get("minute", 0)), second=p.get("second"))
    _vignette(c, 0.5)
    return s.makeImageSnapshot()


# =================================================================== night shift rules note
def ins_night_rules_note(p, size):
    """Cream typed notice taped to the wall: title, numbered rules, posted date and the head nurse's signature."""
    s, c = _begin(size)
    _wall(c, "#6f8c8e")
    _blur_props(c)
    l, t, r, b = 760.0, 260.0, 3080.0, 1800.0
    _paper(c, l, t, r, b, rot=float(p.get("rotation", -1.5)))
    c.save()
    c.rotate(float(p.get("rotation", -1.5)), (l + r) / 2, (t + b) / 2)
    text(c, p.get("title", "NIGHT SHIFT RULES - MEMORIAL WING 4"), (l + r) / 2, t + 230, 104, "#2a2a2a", "bold", "center",
         max_w=r - l - 220)
    c.drawLine(l + 140, t + 310, r - 140, t + 310, stroke("#6a6458", 5))
    rules = p.get("rules") or ["1. If bed 12 calls after 3 AM, do not go.",
                               "2. Never write down a patient who is not in the file.",
                               "3. Never open the curtain around bed 12.",
                               "4. After 5 AM, forget everything."]
    hi = p.get("underline")
    y = t + 520
    for i, rule in enumerate(rules):
        w = text(c, rule, l + 170, y, 86, "#2a2a2a", "semibold", max_w=r - l - 320)
        if hi is not None and int(hi) == i:
            c.drawPath(poly([(l + 160, y + 34), (l + 170 + w, y + 26), (l + 170 + w, y + 40), (l + 160, y + 46)]), fill(RED))
        y += 220
    if p.get("posted", "Posted 15 Mar 2023"):
        text(c, p.get("posted", "Posted 15 Mar 2023"), l + 170, b - 200, 62, "#7a7466", "semibold")
    text(c, p.get("signature", "Head Nurse W."), r - 200, b - 120, 84, "#2a2a3a", "semibold", "right")
    c.restore()
    _vignette(c, 0.45)
    return s.makeImageSnapshot()


# =================================================================== roster / call log tables on wood
def _table_sheet(c, l, t, r, b, title, sub, head, rows, widths, red_last=False, footer=None, rot=0.0):
    _paper(c, l, t, r, b, rot=rot, col="#f4efe4", tape=False)
    c.save()
    c.rotate(rot, (l + r) / 2, (t + b) / 2)
    text(c, title, (l + r) / 2, t + 170, 96, "#2a2a2a", "bold", "center", max_w=r - l - 160)
    y0 = t + 210
    if sub:
        text(c, sub, (l + r) / 2, t + 290, 70, "#4a4a4a", "semibold", "center", max_w=r - l - 160)
        y0 = t + 350
    xs = [l + 120]
    for w in widths:
        xs.append(xs[-1] + (r - l - 240) * w)
    rh = 170.0
    c.drawRect(_R(xs[0], y0, xs[-1], y0 + rh), fill("#e6dfcf"))
    for k, h in enumerate(head):
        text(c, h, xs[k] + 40, y0 + rh * 0.66, 66, "#3a3a3a", "semibold", max_w=xs[k + 1] - xs[k] - 60)
    for j, row in enumerate(rows):
        yy = y0 + rh * (j + 1)
        red = red_last and j == len(rows) - 1
        for k, cell in enumerate(row):
            text(c, str(cell), xs[k] + 40, yy + rh * 0.66, 76, RED if red else INK, "bold" if k else "semibold",
                 max_w=xs[k + 1] - xs[k] - 60)
    for j in range(len(rows) + 2):
        c.drawLine(xs[0], y0 + rh * j, xs[-1], y0 + rh * j, stroke("#7a746a", 4))
    for x in xs:
        c.drawLine(x, y0, x, y0 + rh * (len(rows) + 1), stroke("#7a746a", 4))
    if footer:
        text(c, footer, r - 140, b - 90, 66, INK, "semibold", "right")
    c.restore()


def ins_nurse_roster(p, size):
    """Ward nurse roster on a wooden desk: morning / evening / night shifts with initials and hours."""
    s, c = _begin(size)
    _wood_top(c, "#7a5236")
    night = p.get("night", "W. / P.")
    rows = [["Morning", p.get("morning", "S. / M."), "07:00-15:00"], ["Evening", p.get("evening", "A. / P."), "15:00-23:00"],
            ["Night", "" if p.get("night_blank") else night, "23:00-07:00"]]
    _table_sheet(c, 560, 120, 3280, 1820, p.get("title", "NURSE ROSTER - WARD 4, MEMORIAL WING"),
                 p.get("date", "Date: 11 Nov"), ["SHIFT", "NURSES", "HOURS"], rows, [0.24, 0.42, 0.34],
                 footer=p.get("footer", "Signed: W., head nurse"), rot=-1.0)
    _vignette(c, 0.5)
    return s.makeImageSnapshot()


def ins_call_bell_log(p, size):
    """Night call-bell log on a wooden desk; the last 03:00 / bed 12 row is in red."""
    s, c = _begin(size)
    _wood_top(c, "#6a4a32")
    rows = p.get("rows") or [["23:40", "3", "P."], ["01:20", "9", "P."], ["03:00", "12", "P. (did not go)"]]
    _table_sheet(c, 640, 300, 3200, 1560, p.get("title", "CALL BELL LOG (NIGHT SHIFT)"), "", ["TIME", "BED", "ANSWERED BY"],
                 rows, [0.3, 0.2, 0.5], red_last=bool(p.get("red_last", True)), rot=0.8)
    _vignette(c, 0.5)
    return s.makeImageSnapshot()


# =================================================================== patient whiteboard
def ins_patient_board(p, size):
    """Ward whiteboard listing patients by bed (blue marker); bed 12 shows only a red dash."""
    s, c = _begin(size)
    _wall(c, "#7d9c98")
    l, t, r, b = 220.0, 140.0, 3620.0, 2020.0
    _shadow(c, rrect(l, t, r, b, 16), 40, 24, 0.45)
    c.drawPath(rrect(l, t, r, b, 16), fill("#c9ced3"))
    c.drawRect(_R(l + 40, t + 40, r - 40, b - 40), _lin((l, t), (r, b), ["#fbfcfc", "#eef1f2", "#f8f9f9"]))
    text(c, p.get("title", "WARD 4 PATIENTS - MEMORIAL WING"), (l + r) / 2, t + 210, 110, INK, "bold", "center", max_w=r - l - 300)
    names = p.get("names") or ["Aunt B.", "Uncle S.", "Grandma P.", "Uncle C.", "Aunt L.", "Grandpa C.",
                               "", "Uncle P.", "Grandma K.", "Uncle T.", "Aunt S.", "-"]
    mid = (l + r) / 2
    for i, nm in enumerate(names[:12]):
        col_, row = divmod(i, 6)
        x = l + 160 + col_ * (mid - l)
        y = t + 430 + row * 250
        text(c, str(i + 1), x, y, 100, "#2a2c33", "bold")
        if i == 11 and nm in ("-", ""):
            c.drawRect(_R(x + 220, y - 50, x + 340, y - 32), fill(RED))
        else:
            text(c, nm, x + 220, y, 96, INK, "semibold", max_w=mid - l - 520)
        c.drawLine(x, y + 70, x + mid - l - 320, y + 70, stroke("#c9ced3", 5))
    c.drawLine(mid, t + 320, mid, b - 120, stroke("#c9ced3", 6))
    for k, col in enumerate(("#2f5fb0", RED)):
        c.drawPath(capsule(l + 260 + k * 230, b - 70, l + 440 + k * 230, b - 70, 26, 26), fill(col))
    _vignette(c, 0.4)
    return s.makeImageSnapshot()


# =================================================================== beige desk phone
def ins_desk_phone(p, size):
    """Beige push-button desk phone on the nurse-station desk, label tag on the handset cradle."""
    s, c = _begin(size)
    c.drawRect(_R(0, 0, LW, LH * 0.55), _lin((0, 0), (0, LH * 0.55), ["#6f8c86", "#86a39c"]))
    for k in range(6):
        c.drawPath(rrect(260 + k * 180, 300, 400 + k * 180, 560, 30), _blurred("#7a2a26", 0.8, 24))
    c.drawPath(rrect(2900, 280, 3700, 1100, 20), _blurred("#f4f4f0", 0.85, 30))
    c.drawRect(_R(0, LH * 0.52, LW, LH), _lin((0, LH * 0.52), (0, LH), ["#6a4630", "#4a3020"]))
    rng = random.Random(4)
    for _ in range(26):
        y = rng.uniform(LH * 0.55, LH)
        c.drawLine(0, y, LW, y + rng.uniform(-8, 8), stroke("#2a1a10", 3, 0.35))
    cx = 1920.0
    c.drawPath(oval(cx + 60, 1800, 1300, 120), _blurred("#000000", 0.5, 40))
    body = poly([(cx - 760, 1780), (cx + 760, 1780), (cx + 620, 900), (cx - 620, 900)])
    c.drawPath(body, _lin((cx - 760, 0), (cx + 760, 0), ["#d9cfb5", "#ece4cf", "#cfc4a8"]))
    c.drawRect(_R(cx - 780, 1740, cx + 780, 1800), fill("#b9ad90"))
    c.drawPath(rrect(cx - 600, 600, cx + 600, 820, 120), _lin((0, 600), (0, 820), ["#efe8d6", "#d6ccb2"]))
    for sx in (-1, 1):
        c.drawPath(oval(cx + sx * 520, 820, 160, 60), fill("#cfc4a8"))
    c.drawRect(_R(cx - 420, 820, cx + 420, 920), fill("#c9bea2"))
    lab = p.get("label", "HEAD 101")
    if lab:
        c.drawPath(rrect(cx - 260, 960, cx + 260, 1060, 14), fill("#fbf8ef"))
        text(c, lab, cx, 1036, 62, "#3a3a3a", "semibold", "center", max_w=480)
    keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"]
    for i, k in enumerate(keys):
        row, col_ = divmod(i, 3)
        x = cx - 330 + col_ * 260
        y = 1130 + row * 150
        c.drawPath(rrect(x - 95, y - 55, x + 95, y + 55, 22), fill("#f6f1e3"))
        c.drawPath(rrect(x - 95, y - 55, x + 95, y + 55, 22), stroke("#a89c80", 6))
        text(c, k, x, y + 26, 72, "#3a3a3a", "semibold", "center")
    cord = skia.Path()
    cord.moveTo(cx - 760, 1500)
    for k in range(14):
        cord.cubicTo(cx - 860, 1520 + k * 50, cx - 700, 1540 + k * 50, cx - 780, 1560 + k * 50)
    c.drawPath(cord, stroke("#cfc4a8", 26))
    _vignette(c, 0.45)
    return s.makeImageSnapshot()


# =================================================================== paper boat
def _boat(c, cx, cy, w, col="#e9e6dc") -> None:
    h = w * 0.35
    c.drawPath(oval(cx, cy + h * 0.75, w * 0.6, h * 0.25), _blurred("#000000", 0.35, w * 0.05))
    c.drawPath(poly([(cx - w * 0.5, cy), (cx + w * 0.5, cy), (cx + w * 0.32, cy + h), (cx - w * 0.32, cy + h)]),
               _lin((0, cy), (0, cy + h), [shade(col, -0.05), shade(col, -0.18)]))
    c.drawPath(poly([(cx - w * 0.42, cy), (cx + w * 0.02, cy - h * 1.8), (cx + w * 0.02, cy)]), fill(shade(col, -0.03)))
    c.drawPath(poly([(cx + w * 0.02, cy - h * 1.8), (cx + w * 0.3, cy), (cx + w * 0.02, cy)]), fill(shade(col, 0.06)))
    for k in (0.38, 0.62):
        c.drawLine(cx - w * 0.28, cy + h * k, cx + w * 0.28, cy + h * k, stroke("#8a96c0", w * 0.012))


def ins_paper_boat(p, size):
    """Small folded paper boat (with faint ruled lines) on a wooden desk."""
    s, c = _begin(size)
    _wood_top(c, "#6e4a30")
    c.drawCircle(3000, 400, 1200, _rad(3000, 400, 1200, [("#ffd9a0", 0.25), ("#ffd9a0", 0.0)]))
    _boat(c, 1920, 1080, 1100)
    _vignette(c, 0.55)
    return s.makeImageSnapshot()


# =================================================================== unfolded SORRY note
def ins_sorry_note(p, size):
    """Ruled paper unfolded from a paper boat: diagonal + grid fold creases, faint pencil word in the middle."""
    s, c = _begin(size)
    _wood_top(c, "#6a4530")
    l, t, r, b = 520.0, 220.0, 3320.0, 1920.0
    _shadow(c, rrect(l, t, r, b, 6), 40, 24, 0.5)
    c.drawRect(_R(l, t, r, b), _lin((l, t), (r, b), ["#f4f0e4", "#ebe5d6"]))
    for k in range(1, 15):
        y = t + k * (b - t) / 15
        c.drawLine(l + 120, y, r - 40, y, stroke("#9cb4d8", 5))
    c.drawLine(l + 100, t, l + 100, b, stroke("#e09090", 6))
    for (x0, y0, x1, y1) in ((l, t, r, b), (r, t, l, b), ((l + r) / 2, t, (l + r) / 2, b), (l, (t + b) / 2, r, (t + b) / 2),
                             (l + (r - l) * 0.25, t, l + (r - l) * 0.25, b), (l + (r - l) * 0.75, t, l + (r - l) * 0.75, b)):
        c.drawLine(x0, y0, x1, y1, stroke("#b8ae98", 5, 0.8))
    word = p.get("text", "SORRY")
    text(c, word, (l + r) / 2, (t + b) / 2 + 110, 330, "#5a5a5a", "semibold", "center", a=0.75)
    _vignette(c, 0.5)
    return s.makeImageSnapshot()


# =================================================================== torn childhood photo
def ins_torn_photo(p, size):
    """Torn old photo of a smiling little girl in a yellow dress (red hair bobbles) at sunset; left part torn off."""
    s, c = _begin(size)
    c.drawRect(_R(0, 0, LW, LH), _lin((0, 0), (LW, LH), ["#5a6070", "#7a8090", "#4a5060"]))
    for x in (500, 700):
        c.drawLine(x, 0, x + 900, LH, stroke("#ffffff", 70, 0.08))
    l, t, r, b = 1500.0, 640.0, 2360.0, 1700.0
    rot = float(p.get("rotation", 4))
    c.save()
    c.rotate(rot, (l + r) / 2, (t + b) / 2)
    rng = random.Random(7)
    edge = [(l + rng.uniform(-30, 50), t + k * (b - t) / 10) for k in range(11)]
    frame = poly([(edge[0][0], t), (r, t), (r, b), (edge[-1][0], b)] + list(reversed(edge)))
    _shadow(c, frame, 30, 30, 0.55)
    c.drawPath(frame, fill("#f4efe2"))
    il, it, ir, ib = l + 70, t + 70, r - 60, b - 140
    c.save()
    c.clipPath(frame, skia.ClipOp.kIntersect, True)
    c.drawRect(_R(il, it, ir, ib), _lin((0, it), (0, ib), ["#a8c0d0", "#e8d0a0", "#b89a70"]))
    c.drawPath(oval(il + (ir - il) * 0.5, ib - 60, 260, 50), fill("#8aa0b0", 0.8))
    gx, gy = il + (ir - il) * 0.6, it + (ib - it) * 0.36
    c.drawPath(poly([(gx - 120, gy + 140), (gx + 120, gy + 140), (gx + 170, ib - 40), (gx - 170, ib - 40)]),
               fill(p.get("dress", "#f0c848")))
    c.drawCircle(gx, gy, 110, fill("#f0c8a0"))
    c.drawPath(oval(gx, gy - 60, 110, 60), fill("#2a1f1a"))
    for sx in (-1, 1):
        c.drawCircle(gx + sx * 120, gy - 30, 46, fill("#e04a3a"))
    c.drawArc(_R(gx - 50, gy - 10, gx + 50, gy + 50), 20, 140, False, stroke("#8a2a20", 12))
    c.drawPath(capsule(gx - 340, gy + 200, gx - 160, gy + 170, 40, 36), fill("#c08860"))
    c.restore()
    c.restore()
    _vignette(c, 0.45)
    return s.makeImageSnapshot()


# =================================================================== nurse cap on plastic
def _plastic(c, base="#b9c8c8") -> None:
    c.drawRect(_R(0, 0, LW, LH), _lin((0, 0), (0, LH), [shade(base, 0.1), base, shade(base, -0.2)]))
    rng = random.Random(9)
    for _ in range(30):
        x, y = rng.uniform(0, LW), rng.uniform(0, LH)
        c.drawLine(x, y, x + rng.uniform(-500, 500), y + rng.uniform(-80, 80), stroke("#ffffff", rng.uniform(3, 10), 0.25))
    for _ in range(40):
        x, y, r_ = rng.uniform(0, LW), rng.uniform(0, LH), rng.uniform(8, 22)
        c.drawCircle(x, y, r_, fill("#ffffff", 0.5))
        c.drawCircle(x - r_ * 0.3, y - r_ * 0.3, r_ * 0.35, fill("#ffffff", 0.9))


def _cap(c, cx, cy, w) -> None:
    h = w * 0.42
    c.drawPath(oval(cx, cy + h * 0.55, w * 0.62, h * 0.22), _blurred("#000000", 0.35, w * 0.04))
    c.drawPath(poly([(cx - w / 2, cy + h * 0.5), (cx + w / 2, cy + h * 0.5), (cx + w * 0.42, cy - h * 0.2),
                     (cx, cy - h * 0.5), (cx - w * 0.42, cy - h * 0.2)]), _lin((0, cy - h), (0, cy + h), ["#ffffff", "#dfe3e6"]))
    c.drawRect(_R(cx - w * 0.47, cy + h * 0.05, cx + w * 0.47, cy + h * 0.2), fill("#1f2328"))
    c.drawRect(_R(cx - w * 0.5, cy + h * 0.35, cx + w * 0.5, cy + h * 0.5), fill("#f4f6f7"))


def ins_nurse_cap(p, size):
    """White nurse cap with a black stripe left on a plastic-wrapped bed, water droplets around it."""
    s, c = _begin(size)
    _plastic(c)
    _cap(c, 1920, 1000, 1500)
    _vignette(c, 0.5)
    return s.makeImageSnapshot()


# =================================================================== fob watch / keys / uniform
def _fabric(c, base, stripes=True) -> None:
    c.drawRect(_R(0, 0, LW, LH), _rad(LW * 0.5, LH * 0.4, LW * 0.7, [shade(base, 0.08), base, shade(base, -0.2)]))
    if stripes:
        for k in range(10):
            x = 120 + k * 400 + 40 * math.sin(k)
            c.drawLine(x, 0, x + 30, LH, stroke(shade(base, -0.12), 14, 0.7))


def ins_fob_watch(p, size):
    """Nurse's fob watch pinned to a uniform pocket (clipped bar + chain), showing about 2:50."""
    s, c = _begin(size)
    _fabric(c, p.get("fabric", "#d6d4e2"))
    for y in (300, 900, 1500, 2100):
        c.drawCircle(3000, y, 34, fill("#eeeef4"))
        c.drawCircle(3000, y, 34, stroke("#a8a6b8", 5))
    c.drawPath(rrect(1720, 120, 2140, 360, 18), fill("#ececf2"))
    c.drawPath(rrect(1720, 120, 2140, 360, 18), stroke("#a8a6b8", 6))
    c.drawPath(poly([(1900, 360), (1960, 360), (1850, 640), (1790, 640)]), fill("#b8bcc6"))
    _clock(c, 1780, 1060, 420, float(p.get("hour", 2)), float(p.get("minute", 50)), face="#f6f4ee", rim="#9aa0aa")
    _vignette(c, 0.4)
    return s.makeImageSnapshot()


def ins_key_ring(p, size):
    """Bunch of old keys on a ring hanging from a dark belt clip over a grey uniform skirt."""
    s, c = _begin(size)
    _fabric(c, "#7a7672")
    c.drawRect(_R(0, 560, LW, 760), fill("#3a3430"))
    c.drawPath(rrect(1780, 520, 2060, 800, 16), fill("#cfc8b4"))
    c.drawCircle(1920, 1150, 300, stroke("#d8d2c4", 30))
    rng = random.Random(3)
    for k in range(6):
        a = math.radians(140 - k * 22)
        hx, hy = 1920 + math.cos(a) * 260, 1150 + math.sin(a) * 260 + 120
        col = "#d8b860" if k % 2 else "#c9ccd2"
        ex, ey = hx + math.cos(a + 0.3) * 900 * rng.uniform(0.8, 1.0), hy + math.sin(a + 0.3) * 900
        c.drawLine(hx, hy, ex, ey, stroke(col, 50))
        c.drawCircle(hx, hy, 95, fill(col))
        c.drawCircle(hx, hy, 38, fill("#2a2420"))
    _vignette(c, 0.55)
    return s.makeImageSnapshot()


def ins_uniform_hanger(p, size):
    """Old pale-yellow nurse uniform on a wire hanger inside a locker, fob watch pinned to the pocket."""
    s, c = _begin(size)
    c.drawRect(_R(0, 0, LW, LH), _lin((0, 0), (LW, 0), ["#7a8088", "#3a3e46", "#9aa0a8"]))
    c.drawRect(_R(820, 0, 2620, LH), fill("#2e3238"))
    c.drawPath(poly([(1500, 260), (2020, 0), (2540, 260)]), stroke("#c9ced6", 16))
    col = p.get("color", "#f2e2a8")
    body = poly([(1020, 260), (2900, 260), (2780, LH + 50), (1140, LH + 50)])
    c.drawPath(body, _lin((1020, 0), (2900, 0), [shade(col, -0.08), col, shade(col, -0.2)]))
    for k in range(6):
        x = 1300 + k * 300
        c.drawLine(x, 300, x - 20, LH, stroke(shade(col, -0.12), 10, 0.6))
    c.drawLine(1900, 280, 1880, LH, stroke(shade(col, -0.2), 12))
    for y in (650, 1250, 1850):
        c.drawCircle(1890, y, 34, fill("#fbf7ea"))
    c.drawPath(rrect(2250, 1000, 2650, 1400, 10), stroke(shade(col, -0.25), 6))
    _clock(c, 2440, 1150, 110, 2, 50, rim="#9aa0aa")
    c.drawRect(_R(2620, 0, 2700, LH), fill("#000000", 0.25))
    _vignette(c, 0.5)
    return s.makeImageSnapshot()


# =================================================================== bed call button
def ins_bed_call_button(p, size):
    """Bedside call handset hanging on its cord over a white blanket, red button; a finger reaches up from below."""
    s, c = _begin(size)
    c.drawRect(_R(0, 0, LW, 1100), _lin((0, 0), (0, 1100), ["#2e4a44", "#3e5c54"]))
    c.drawRect(_R(0, 860, LW, 960), fill("#9fb1b2"))
    blanket = poly([(0, 1060), (LW, 1100), (LW, LH), (0, LH)])
    c.drawPath(blanket, _lin((0, 1060), (0, LH), ["#d8e2dc", "#a9b8b2"]))
    for x in (300, 1050, 1800, 2550, 3300):
        c.drawArc(_R(x - 500, 1100, x + 400, 3000), 190, 60, False, stroke("#8a9a96", 8))
    c.drawLine(1930, 0, 1920, 960, stroke("#e8ece8", 22))
    c.drawPath(rrect(1760, 960, 2080, 1310, 70), fill("#efede6"))
    c.drawPath(rrect(1760, 960, 2080, 1310, 70), stroke("#bdbab0", 6))
    c.drawCircle(1920, 1080, 92, fill(p.get("button", "#c8352e")))
    c.drawCircle(1890, 1050, 26, fill("#ffffff", 0.4))
    c.drawPath(rrect(1820, 1200, 2020, 1250, 14), fill("#cfccc4"))
    if p.get("finger", True):
        c.drawPath(capsule(2240, LH + 60, 2140, 1820, 70, 56), fill(p.get("skin", "#8a5a38")))
        c.drawCircle(2140, 1830, 50, fill("#a87a58"))
    _vignette(c, 0.55)
    return s.makeImageSnapshot()


# =================================================================== vital-signs monitor
def ins_vital_monitor(p, size):
    """Bedside vital-signs monitor on a pole in a dark rainy ward: ECG trace, HR / SpO2 / NIBP numbers."""
    s, c = _begin(size)
    c.drawRect(_R(0, 0, LW, LH), _lin((0, 0), (0, LH), ["#243a40", "#1a2a30"]))
    c.drawRect(_R(1700, 120, 3300, 1400), fill("#0e1a22"))
    rng = random.Random(5)
    for _ in range(90):
        x, y = rng.uniform(1720, 3280), rng.uniform(140, 1380)
        c.drawLine(x, y, x, y + rng.uniform(40, 160), stroke("#9ab0c8", 3, 0.35))
    c.drawRect(_R(1700, 120, 3300, 1400), stroke("#cdd6d4", 30))
    c.drawLine(820, 900, 820, LH, stroke("#9aa4a8", 26))
    l, t, r, b = 360.0, 420.0, 1500.0, 1180.0
    _shadow(c, rrect(l, t, r, b, 26), 30, 20, 0.6)
    c.drawPath(rrect(l, t, r, b, 26), fill("#1c1f24"))
    c.drawRect(_R(l + 40, t + 40, r - 40, b - 40), fill("#0a1416"))
    ecg = skia.Path()
    x = l + 60
    ecg.moveTo(x, t + 230)
    while x < r - 80:
        ecg.lineTo(x + 50, t + 230)
        ecg.lineTo(x + 70, t + 120)
        ecg.lineTo(x + 90, t + 300)
        ecg.lineTo(x + 110, t + 230)
        x += 170
    c.drawPath(ecg, _blurred("#3ee0a0", 0.6, 8))
    c.drawPath(ecg, stroke("#3ee0a0", 7))
    vals = [("HR", str(p.get("hr", 72)), "#3ee0a0"), ("SpO2 %", str(p.get("spo2", 97)), "#4ac8ff"),
            ("NIBP", str(p.get("nibp", "92/58")), "#f0d060")]
    for k, (lab, val, col) in enumerate(vals):
        x0 = l + 70 + k * 340
        text(c, lab, x0, b - 230, 40, col, "semibold")
        text(c, val, x0, b - 100, 130 if k < 2 else 84, col, "bold", max_w=320)
    _soft_glow(c, (l + r) / 2, (t + b) / 2, 900, "#3ee0a0", 0.12)
    _vignette(c, 0.55)
    return s.makeImageSnapshot()


# =================================================================== wet footprints / plastic bed
def ins_wet_footprints(p, size):
    """Wet bare footprints shining on a dim ward floor, leading toward a bed wheel at the right edge."""
    s, c = _begin(size)
    c.drawRect(_R(0, 0, LW, 900), fill("#1e3034"))
    _speckle_floor = _lin((0, 860), (0, LH), ["#5a7a76", "#7a948e", "#4a5e5a"])
    c.drawPath(poly([(0, 900), (LW, 830), (LW, LH), (0, LH)]), _speckle_floor)
    rng = random.Random(2)
    for _ in range(500):
        c.drawCircle(rng.uniform(0, LW), rng.uniform(900, LH), rng.uniform(2, 6), fill("#c8d8d0", 0.35))
    steps = 7
    for k in range(steps):
        t_ = k / (steps - 1)
        x = 200 + t_ * 3300
        y = 1900 - t_ * 1100
        sc = 1.0 - t_ * 0.65
        c.drawPath(oval(x, y, 300 * sc, 85 * sc), fill("#1e2e30", 0.85))
        c.drawPath(oval(x + 360 * sc, y + 10 * sc, 90 * sc, 55 * sc), fill("#1e2e30", 0.85))
        c.drawArc(_R(x - 250 * sc, y - 60 * sc, x - 120 * sc, y + 10 * sc), 180, 90, False, stroke("#e8f4f0", 14 * sc, 0.8))
        c.drawCircle(x + 350 * sc, y - 15 * sc, 14 * sc, fill("#ffffff", 0.8))
    c.drawRect(_R(3560, 160, LW, 1000), fill("#c9cfd2"))
    c.drawCircle(3620, 1080, 60, fill("#2a2c30"))
    c.drawCircle(3620, 1080, 22, fill("#8a8f96"))
    _vignette(c, 0.55)
    return s.makeImageSnapshot()


def ins_plastic_wrapped_bed(p, size):
    """Close-up of the plastic sheet wrapping an empty bed, bulging in the shape of a body; droplets and scratches."""
    s, c = _begin(size)
    _plastic(c, "#9aa2a6")
    c.drawRect(_R(0, 0, LW, 300), fill("#2e2a30"))
    bump = skia.Path()
    bump.moveTo(800, 780)
    bump.cubicTo(1300, 600, 1700, 700, 1900, 760)
    bump.cubicTo(2200, 640, 2700, 700, 3000, 900)
    bump.cubicTo(3150, 1000, 3100, 1300, 2900, 1320)
    bump.cubicTo(2400, 1400, 1500, 1500, 860, 1420)
    bump.cubicTo(650, 1300, 650, 900, 800, 780)
    c.drawPath(bump, fill("#6a6e74", 0.45))
    c.drawPath(bump, stroke("#e6eaee", 10, 0.7))
    c.drawCircle(700, 1000, 360, _rad(700, 1000, 360, [("#4a2a30", 0.5), ("#4a2a30", 0.0)]))
    _vignette(c, 0.6)
    return s.makeImageSnapshot()


# =================================================================== old radio / locker
def ins_old_radio(p, size):
    """Vintage wooden radio glowing on a dim desk with its antenna up."""
    s, c = _begin(size)
    c.drawRect(_R(0, 0, LW, 1300), _lin((0, 0), (0, 1300), ["#2e302c", "#46483f"]))
    c.drawRect(_R(0, 1250, LW, LH), _lin((0, 1250), (0, LH), ["#8a5a38", "#4a2e1c"]))
    cx, by = 1920.0, 1340.0
    c.drawPath(oval(cx, by, 1000, 60), _blurred("#000000", 0.5, 30))
    _soft_glow(c, cx + 300, by - 400, 1300, "#ffc87a", 0.35)
    c.drawPath(rrect(cx - 820, by - 760, cx + 820, by, 60), _lin((0, by - 760), (0, by), ["#a8603a", "#7a4024"]))
    c.drawPath(rrect(cx - 740, by - 680, cx - 60, by - 80, 30), fill("#5a3220"))
    for k in range(9):
        y = by - 640 + k * 64
        c.drawLine(cx - 700, y, cx - 100, y, stroke("#2a160c", 18))
    c.drawPath(rrect(cx + 60, by - 660, cx + 700, by - 380, 24), fill("#ffd890"))
    c.drawLine(cx + 380, by - 660, cx + 380, by - 380, stroke("#a86020", 10))
    _soft_glow(c, cx + 380, by - 520, 500, "#ffd890", 0.5)
    for k in range(2):
        c.drawCircle(cx + 220 + k * 320, by - 220, 90, fill("#3a2016"))
        c.drawCircle(cx + 220 + k * 320, by - 220, 60, fill("#5a3424"))
    c.drawLine(cx + 760, by - 760, cx + 1080, by - 1700, stroke("#d8dcde", 16))
    _vignette(c, 0.6)
    return s.makeImageSnapshot()


def ins_locker_do_not_open(p, size):
    """Grey staff locker door crossed out with yellow tape, blank name tag and a red DO NOT OPEN scrawl."""
    s, c = _begin(size)
    c.drawRect(_R(0, 0, LW, LH), fill("#5e6268"))
    l, r = 1060.0, 2780.0
    c.drawRect(_R(l, 0, r, LH), _lin((l, 0), (r, 0), ["#9aa0a8", "#b9bec6", "#8e949c"]))
    c.drawRect(_R(l - 40, 0, l, LH), fill("#4a4e54"))
    c.drawRect(_R(r, 0, r + 40, LH), fill("#4a4e54"))
    for k in range(6):
        c.drawPath(rrect(1640, 200 + k * 60, 2200, 230 + k * 60, 10), fill("#5a6068"))
    c.drawPath(rrect(1700, 760, 2140, 900, 10), fill("#f4f4f0"))
    c.drawPath(rrect(2480, 1100, 2560, 1500, 20), fill("#3a3e44"))
    tape = p.get("tape", "#e8c04a")
    for a in (35, -35):
        c.save()
        c.rotate(a, 1920, 830)
        c.drawRect(_R(1380, 770, 2460, 890), fill(tape, 0.92))
        c.restore()
    text(c, p.get("text", "DO NOT OPEN"), 1920, 1320, 130, "#c8251e", "bold", "center", max_w=1300)
    _vignette(c, 0.5)
    return s.makeImageSnapshot()


# =================================================================== registration
def _with(fn, **defaults):
    def run(p, size):
        q = dict(defaults)
        q.update(p or {})
        return fn(q, size)
    run.__doc__ = fn.__doc__
    return run


INSERTS = {
    "nurse_call_panel": ins_nurse_call_panel,
    "nurse_call_panel_off": _with(ins_nurse_call_panel, lit=[], hour=2, minute=40),
    "wall_clock_3am": ins_wall_clock,
    "wall_clock_255": _with(ins_wall_clock, hour=2, minute=55),
    "night_rules_note": ins_night_rules_note,
    "night_rules_note_rule3": _with(ins_night_rules_note, underline=2, rotation=1.0),
    "nurse_roster": ins_nurse_roster,
    "nurse_roster_blank_night": _with(ins_nurse_roster, night_blank=True, date="Date: 14 Mar", footer="Signed: W., head nurse"),
    "call_bell_log": ins_call_bell_log,
    "patient_board": ins_patient_board,
    "desk_phone_beige": ins_desk_phone,
    "paper_boat": ins_paper_boat,
    "sorry_note_folded": ins_sorry_note,
    "torn_photo_girl": ins_torn_photo,
    "nurse_cap_on_plastic": ins_nurse_cap,
    "nurse_fob_watch": ins_fob_watch,
    "key_ring_belt": ins_key_ring,
    "uniform_on_hanger": ins_uniform_hanger,
    "bed_call_button": ins_bed_call_button,
    "vital_signs_monitor": ins_vital_monitor,
    "wet_footprints_trail": ins_wet_footprints,
    "plastic_wrapped_bed": ins_plastic_wrapped_bed,
    "old_radio_glow": ins_old_radio,
    "locker_do_not_open": ins_locker_do_not_open,
}

TAGS = {
    "nurse_call_panel": ["nurse call", "call bell panel", "bed 12", "hospital", "red light", "nurse station"],
    "nurse_call_panel_off": ["nurse call", "call bell panel", "hospital", "unlit", "nurse station"],
    "wall_clock_3am": ["wall clock", "3 am", "three o'clock", "night shift", "time", "hospital"],
    "wall_clock_255": ["wall clock", "2:55", "before 3 am", "night shift", "time"],
    "night_rules_note": ["rules", "night shift rules", "notice", "hospital", "do not go", "head nurse"],
    "night_rules_note_rule3": ["rules", "night shift rules", "underlined rule", "curtain", "bed 12"],
    "nurse_roster": ["roster", "duty schedule", "shift table", "nurses", "hospital"],
    "nurse_roster_blank_night": ["roster", "duty schedule", "empty night shift", "nurses", "hospital"],
    "call_bell_log": ["call log", "call bell log", "night shift", "bed 12", "did not go", "record"],
    "patient_board": ["patient board", "whiteboard", "ward list", "bed numbers", "hospital"],
    "desk_phone_beige": ["desk phone", "landline", "telephone", "nurse station", "keypad"],
    "paper_boat": ["paper boat", "origami", "boat", "childhood", "memory"],
    "sorry_note_folded": ["note", "sorry", "apology", "unfolded paper", "message", "creases"],
    "torn_photo_girl": ["photo", "torn photo", "little girl", "yellow dress", "memory", "childhood"],
    "nurse_cap_on_plastic": ["nurse cap", "plastic sheet", "bed 12", "wet", "left behind"],
    "nurse_fob_watch": ["fob watch", "nurse watch", "pinned watch", "uniform", "time"],
    "key_ring_belt": ["keys", "key ring", "belt", "head nurse", "bunch of keys"],
    "uniform_on_hanger": ["nurse uniform", "hanger", "locker", "old uniform", "fob watch"],
    "bed_call_button": ["call button", "nurse call button", "bed", "red button", "cord"],
    "vital_signs_monitor": ["vital signs", "heart monitor", "ecg", "patient monitor", "hospital"],
    "wet_footprints_trail": ["wet footprints", "footprints", "water", "floor", "ghost", "trail"],
    "plastic_wrapped_bed": ["plastic", "wrapped bed", "body shape", "bed 12", "horror"],
    "old_radio_glow": ["radio", "old radio", "vintage radio", "glow", "night"],
    "locker_do_not_open": ["locker", "do not open", "taped", "staff locker", "forbidden"],
}

PROPS = {
    "nurse_call_panel": ["nurse_call_panel", "call_bell_panel", "call_panel"],
    "nurse_call_panel_off": ["call_panel_off", "nurse_call_panel_off"],
    "wall_clock_3am": ["wall_clock_3am", "clock_3am", "three_am_clock"],
    "wall_clock_255": ["wall_clock_255", "clock_255"],
    "night_rules_note": ["night_rules", "shift_rules_note", "rules_notice"],
    "night_rules_note_rule3": ["rules_underlined", "rule_3_note"],
    "nurse_roster": ["nurse_roster", "duty_roster", "shift_roster"],
    "nurse_roster_blank_night": ["roster_blank_night", "empty_night_shift"],
    "call_bell_log": ["call_log", "call_bell_log", "bell_log"],
    "patient_board": ["patient_board", "ward_whiteboard", "patient_list"],
    "desk_phone_beige": ["desk_phone", "landline", "beige_phone"],
    "paper_boat": ["paper_boat", "origami_boat"],
    "sorry_note_folded": ["sorry_note", "apology_note", "unfolded_note"],
    "torn_photo_girl": ["torn_photo", "childhood_photo", "girl_photo"],
    "nurse_cap_on_plastic": ["nurse_cap", "cap_on_plastic"],
    "nurse_fob_watch": ["fob_watch", "nurse_watch"],
    "key_ring_belt": ["key_ring", "bunch_of_keys", "keys_on_belt"],
    "uniform_on_hanger": ["uniform_hanger", "nurse_uniform", "old_uniform"],
    "bed_call_button": ["call_button", "bed_call_button", "nurse_button"],
    "vital_signs_monitor": ["vital_monitor", "heart_monitor_screen", "patient_monitor"],
    "wet_footprints_trail": ["footprint_trail", "wet_footprint_trail"],
    "plastic_wrapped_bed": ["plastic_bed", "wrapped_bed"],
    "old_radio_glow": ["old_radio", "vintage_radio", "radio"],
    "locker_do_not_open": ["taped_locker", "forbidden_locker", "locker_x"],
}
