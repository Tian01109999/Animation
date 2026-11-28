"""Batch-6 inserts -- hospital night-shift story, second part (provenance 'procedural_library').

Rules note on a desk (blank + pen / full / rule 4 underlined / blurred), duty roster COPY with red stamp, desk top
with coffee + phone, patient wristband (unknown / name added), big vital-signs monitor (stable / falling SpO2 red /
flatline), phone call to the doctor, lock screen "sent a photo", handwritten letter from dad (+ as a photo on a phone),
blank browser, patient board close-up rows 9-12, empty call log, O2 / AIR wall outlet with flowmeter, belongings bag,
torn photo of a man in yellow, paper boat on a pillow, wet wheel tracks on tiles.

ALL baked text is ENGLISH and generic (people are initials). Pure ASCII source. Loaded by insertgen like batches 2-5.
"""
from __future__ import annotations

import math
import random

import skia

from .insertgen import _lin, _rad, _shadow, _status_bar, _tape, text
from .insertgen_batch2 import LH, LW, _begin, _blurred, _vignette, _wood_top
from .insertgen_batch5 import _boat, _table_sheet
from .skutil import capsule, fill, poly, rrect, shade, stroke

INK = "#25407a"
RED = "#c8352e"


def _R(l, t, r, b) -> skia.Rect:
    return skia.Rect.MakeLTRB(l, t, r, b)


def _bed_sheet(c, base="#b4c6c0") -> None:
    """Top-down hospital blanket with soft folds (background of hand close-ups)."""
    c.drawRect(_R(0, 0, LW, LH), _rad(LW * 0.45, LH * 0.4, LW * 0.75, [shade(base, 0.12), base, shade(base, -0.3)]))
    for k in range(9):
        x = -200 + k * 520
        c.drawArc(_R(x - 300, -900, x + 900, LH + 900), 160, 50, False, stroke(shade(base, -0.18), 14, 0.8))


# =================================================================== rules note on the desk
def ins_rules_note_desk(p, size):
    """Cream rules note taped on a wooden desk; params: rules (list, may be empty), underline (index), pen, blur."""
    s, c = _begin(size)
    _wood_top(c, "#5e3e28")
    c.drawCircle(LW * 0.85, LH * 0.15, LW * 0.4, _rad(LW * 0.85, LH * 0.15, LW * 0.4, [("#ffd9a0", 0.22), ("#ffd9a0", 0.0)]))
    if p.get("blur"):
        c.saveLayer(None, skia.Paint(ImageFilter=skia.ImageFilters.Blur(28, 28)))
    l, t, r, b = 1080.0, 120.0, 2780.0, 1320.0
    c.save()
    c.rotate(float(p.get("rotation", -1.0)), (l + r) / 2, (t + b) / 2)
    pth = rrect(l, t, r, b, 8)
    _shadow(c, pth, 40, 26, 0.55)
    c.drawPath(pth, _lin((l, t), (r, b), ["#f6eed6", "#efe4c6", "#e8dbb8"]))
    _tape(c, l + 320, t + 10, 340, 90, -2)
    _tape(c, r - 320, t + 10, 340, 90, 3)
    text(c, p.get("title", "NIGHT SHIFT RULES - MEMORIAL WING 4"), (l + r) / 2, t + 190, 84, "#3a342a", "bold", "center",
         max_w=r - l - 240)
    c.drawLine(l + 140, t + 260, r - 140, t + 260, stroke("#8a8270", 5))
    rules = p.get("rules")
    if rules is None:
        rules = ["1. If bed 12 calls after 3 AM, do not go.", "2. Never write down a patient who is not in the file.",
                 "3. Never open the curtain around bed 12.", "4. After 5 AM, forget everything."]
    hi = p.get("underline")
    y = t + 440
    for i, rule in enumerate(rules):
        w = text(c, rule, l + 150, y, 78, "#3a342a", "semibold", max_w=r - l - 300)
        if hi is not None and int(hi) == i:
            c.drawLine(l + 150, y + 40, l + 170 + max(w, (r - l) * 0.75), y + 28, stroke(RED, 16))
        y += 170
    text(c, p.get("signature", "Head Nurse W."), r - 160, b - 110, 78, "#3a342a", "semibold", "right")
    c.restore()
    if p.get("blur"):
        c.restore()
    if p.get("pen"):
        px, py = 2300.0, 2100.0
        c.drawPath(capsule(px, py, px + 520, py - 300, 34, 34), fill("#2f4fb0"))
        c.drawPath(capsule(px + 440, py - 250, px + 560, py - 320, 30, 26), fill("#1d2f7a"))
    _vignette(c, 0.55)
    return s.makeImageSnapshot()


# =================================================================== roster copy with stamp
def ins_roster_copy(p, size):
    """Nurse roster photocopy on the desk with a red COPY stamp; night shift names in bold blue."""
    s, c = _begin(size)
    _wood_top(c, "#5e3e28")
    rows = [["Morning", p.get("morning", "S. / M."), "07:00-15:00"], ["Evening", p.get("evening", "A. / P."), "15:00-23:00"],
            ["Night", p.get("night", "W. / P."), "23:00-07:00"]]
    _table_sheet(c, 500, 200, 3340, 1760, p.get("title", "NURSE ROSTER - WARD 4, MEMORIAL WING"),
                 p.get("date", "Date: 14 Mar"), ["SHIFT", "NURSES", "HOURS"], rows, [0.24, 0.42, 0.34],
                 footer=p.get("footer", "Signed ...W... head nurse"), rot=-1.0)
    c.save()
    c.rotate(-8, 2850, 640)
    c.drawPath(rrect(2560, 520, 3160, 760, 20), stroke("#d24a4a", 18, 0.85))
    text(c, p.get("stamp", "COPY"), 2860, 690, 150, "#d24a4a", "bold", "center", a=0.85)
    c.restore()
    _vignette(c, 0.5)
    return s.makeImageSnapshot()


# =================================================================== desk top: coffee + phone (+ roster copy)
def ins_desk_coffee_phone(p, size):
    """Top-down wooden desk: coffee cup on a saucer and a phone face down; optional roster copy in the corner."""
    s, c = _begin(size)
    _wood_top(c, "#5a3a24")
    c.drawCircle(LW * 0.78, LH * 0.25, LW * 0.35, _rad(LW * 0.78, LH * 0.25, LW * 0.35, [("#ffd9a0", 0.25), ("#ffd9a0", 0.0)]))
    if p.get("roster"):
        c.save()
        c.rotate(-4, 600, 380)
        c.drawPath(rrect(130, 110, 1080, 640, 6), _blurred("#000000", 0.4, 20))
        c.drawRect(_R(120, 100, 1070, 620), fill("#f2f0ea"))
        for k in range(5):
            c.drawLine(180, 260 + k * 70, 1010, 260 + k * 70, stroke("#8a8a84", 3))
        text(c, "NURSE ROSTER", 595, 200, 54, "#3a3a3a", "bold", "center")
        c.drawPath(rrect(820, 230, 1000, 310, 10), stroke("#d24a4a", 6))
        c.restore()
    cx, cy = (1400.0, 840.0) if p.get("roster") else (3000.0, 520.0)
    c.drawCircle(cx + 20, cy + 30, 220, _blurred("#000000", 0.45, 24))
    c.drawCircle(cx, cy, 210, fill("#ece8e0"))
    c.drawCircle(cx, cy, 120, fill("#f6f4ef"))
    c.drawCircle(cx, cy, 98, _rad(cx - 20, cy - 20, 110, ["#c88a50", "#8a5228"]))
    c.drawArc(_R(cx - 70, cy - 70, cx + 70, cy + 70), 200, 60, False, stroke("#ffffff", 8, 0.6))
    px, py = (2200.0, 1100.0) if p.get("roster") else (3240.0, 1500.0)
    c.save()
    c.rotate(-8, px, py)
    c.drawPath(rrect(px - 140, py - 290, px + 140, py + 290, 50), _blurred("#000000", 0.5, 20))
    c.drawPath(rrect(px - 130, py - 300, px + 130, py + 280, 48), fill("#2a2c30"))
    c.drawPath(rrect(px - 100, py - 270, px - 10, py - 180, 26), fill("#3a3c42"))
    for dx, dy in ((-75, -245), (-35, -205)):
        c.drawCircle(px + dx, py + dy, 22, fill("#15161a"))
    c.drawPath(poly([(px + 60, py - 300), (px + 130, py - 300), (px - 40, py + 280), (px - 110, py + 280)]), fill("#ffffff", 0.06))
    c.restore()
    _vignette(c, 0.55)
    return s.makeImageSnapshot()


# =================================================================== wristband
def ins_patient_wristband(p, size):
    """Patient wristband on a forearm over a blanket: printed UNKNOWN MALE ~65; optional handwritten name."""
    s, c = _begin(size)
    _bed_sheet(c)
    skin, sleeve = p.get("skin", "#b88660"), p.get("sleeve", "#a8c8b8")
    c.save()
    c.rotate(-6, 1920, 1080)
    c.drawPath(poly([(1500, 700), (2600, 820), (2580, 1320), (1480, 1200)]), _blurred("#000000", 0.25, 40))
    c.drawPath(poly([(1100, 640), (1900, 760), (1880, 1220), (1080, 1110)]), fill(sleeve))
    c.drawPath(capsule(1850, 960, 2900, 1030, 220, 200), fill(skin))
    for k in range(4):
        c.drawPath(capsule(2860, 900 + k * 70, 3380, 870 + k * 90, 46, 40), fill(skin))
    c.drawPath(capsule(2700, 820, 3000, 600, 46, 40), fill(skin))
    c.drawPath(rrect(1500, 900, 2520, 1130, 90), _blurred("#000000", 0.3, 18))
    c.drawPath(rrect(1480, 870, 2500, 1100, 90), fill("#f4f5f8"))
    c.drawPath(rrect(1760, 905, 2400, 1065, 14), stroke("#8a96b8", 5))
    text(c, p.get("label", "UNKNOWN MALE ~65"), 1800, 980, 64, "#2a3460", "bold", max_w=580)
    text(c, p.get("sub", "HN ----  ADM 2 NOV"), 1800, 1045, 40, "#5a6078", "semibold", max_w=300)
    if p.get("name"):
        text(c, p["name"], 2140, 1052, 64, "#2f4fb0", "semibold", max_w=240)
    c.restore()
    _vignette(c, 0.5)
    return s.makeImageSnapshot()


# =================================================================== big vital-signs monitor
def ins_vital_monitor_big(p, size):
    """Large bedside monitor close-up over a blurred ward: ECG trace + HR / SpO2 / NIBP. flat=True -> flatline zeros."""
    s, c = _begin(size)
    c.drawRect(_R(0, 0, LW, LH), _lin((0, 0), (0, LH), ["#3a5a44", "#2a4232", "#162218"]))
    c.drawPath(rrect(860, 1100, 1200, 1800, 20), _blurred("#cfc4a8", 0.6, 40))
    c.drawPath(rrect(1300, 1300, 2900, 1480, 40), _blurred("#cfd8d4", 0.5, 40))
    c.drawRect(_R(3300, 900, 3420, 1800), _blurred("#2f8a4a", 0.8, 30))
    c.drawCircle(1640, 230, 180, _blurred("#f0f0d0", 0.5, 60))
    l, t, r, b = 1120.0, 400.0, 2720.0, 1400.0
    _shadow(c, rrect(l, t, r, b, 40), 50, 30, 0.6)
    c.drawPath(rrect(l, t, r, b, 40), fill("#2a2e32"))
    c.drawRect(_R(l + 40, t + 40, r - 40, b - 40), fill("#0e1412"))
    flat = bool(p.get("flat"))
    trace = "#ff6a5a" if flat else "#4ae0a0"
    y0 = t + 280
    if flat:
        c.drawLine(l + 40, y0, r - 40, y0, stroke(trace, 8))
    else:
        ecg = skia.Path()
        x = l + 40
        ecg.moveTo(x, y0)
        while x < r - 140:
            ecg.lineTo(x + 90, y0)
            ecg.lineTo(x + 115, y0 - 150)
            ecg.lineTo(x + 140, y0 + 120)
            ecg.lineTo(x + 165, y0 - 30)
            ecg.lineTo(x + 190, y0)
            x += 270
        c.drawPath(ecg, _blurred(trace, 0.5, 10))
        c.drawPath(ecg, stroke(trace, 9))
    spo2_col = RED if p.get("spo2_alarm") or flat else "#4ac8ff"
    vals = [("HR", "0" if flat else str(p.get("hr", 112)), "#4ae0a0"),
            ("SpO2 %", "0" if flat else str(p.get("spo2", 85)), spo2_col if not flat else "#4ac8ff"),
            ("NIBP", "--/--" if flat else str(p.get("nibp", "92/58")), "#f0d060")]
    for k, (lab, val, col) in enumerate(vals):
        x0 = l + 130 + k * 500
        text(c, lab, x0, b - 300, 56, col if k != 1 else "#4ac8ff", "semibold")
        text(c, val, x0, b - 110, 190 if k < 2 else 130, col if not (flat and k == 1) else "#4ac8ff", "bold", max_w=440)
    _vignette(c, 0.55)
    return s.makeImageSnapshot()


# =================================================================== phone screens
def _screen_letter(c, sl, st, sr, sb, d: dict) -> None:
    """Photo viewer showing a handwritten letter on ruled paper (black letterbox bars)."""
    sw, sh = sr - sl, sb - st
    c.drawRect(_R(sl, st, sr, sb), fill("#050505"))
    pt, pb = st + sh * 0.2, sb - sh * 0.2
    c.drawRect(_R(sl, pt, sr, pb), fill("#f6f4ee"))
    for k in range(1, 15):
        y = pt + k * (pb - pt) / 15
        c.drawLine(sl, y, sr, y, stroke("#a8bcd8", 2))
    c.drawLine(sl + sw * 0.07, pt, sl + sw * 0.07, pb, stroke("#e08a8a", 3))
    lines = d.get("letter") or LETTER
    for i, ln in enumerate(lines):
        text(c, ln, sl + sw * (0.12 if i == 0 else 0.16), pt + (pb - pt) * (0.13 + i * 0.085), sh * 0.028, INK, "semibold",
             max_w=sw * 0.8)
    text(c, d.get("signature", "Dad, S. S."), sl + sw * 0.62, pt + (pb - pt) * 0.66, sh * 0.034, INK, "semibold", "center")


def _screen_browser(c, sl, st, sr, sb, d: dict) -> None:
    sw, sh = sr - sl, sb - st
    c.drawRect(_R(sl, st, sr, sb), _lin((sl, st), (sl, sb), ["#15171c", "#0c0d10"]))
    _status_bar(c, sl, st + sh * 0.012, sr, sh * 0.045, d.get("time") or "13:05")
    c.drawPath(rrect(sl + sw * 0.05, st + sh * 0.08, sr - sw * 0.05, st + sh * 0.13, sh * 0.012), fill("#2a2d34"))
    c.drawCircle(sl + sw * 0.11, st + sh * 0.105, sh * 0.009, stroke("#aab0bc", sh * 0.003))
    text(c, d.get("placeholder", "Search or enter website"), sl + sw * 0.16, st + sh * 0.113, sh * 0.02, "#8a909c", "semibold",
         max_w=sw * 0.7)
    for k in range(10):
        c.drawPath(rrect(sl + sw * (0.04 + k * 0.095), sb - sh * 0.03, sl + sw * (0.115 + k * 0.095), sb - sh * 0.015,
                         sh * 0.004), fill("#3a3d44"))


SCREENS = {"letter_photo": _screen_letter, "browser": _screen_browser}

LETTER = ["To... P., my child", "I'll go and stay close to where you work.", "I won't bother you at all.",
          "Just let me be near you."]


def _phone(screen, defaults):
    from .insertgen_batch2 import _phone_in_hand

    def run(p, size):
        q = dict(defaults)
        q.update(p or {})
        return _phone_in_hand(screen, q, size)
    return run


# =================================================================== letter on desk
def ins_letter_from_dad(p, size):
    """Handwritten letter on ruled binder paper on a wooden desk, signed by dad."""
    s, c = _begin(size)
    _wood_top(c, "#4e3422")
    l, t, r, b = 1140.0, 40.0, 2700.0, 1860.0
    c.save()
    c.rotate(-1.0, (l + r) / 2, (t + b) / 2)
    _shadow(c, rrect(l, t, r, b, 4), 40, 26, 0.55)
    c.drawRect(_R(l, t, r, b), _lin((l, t), (r, b), ["#fbfbf8", "#efefea"]))
    for k in range(1, 26):
        y = t + k * (b - t) / 26
        c.drawLine(l, y, r, y, stroke("#a8c0e0", 3))
    c.drawLine(l + 180, t, l + 180, b, stroke("#e09090", 4))
    for k in range(8):
        c.drawCircle(l + 60, t + 140 + k * 215, 24, fill("#4a3a30"))
    lines = p.get("letter") or LETTER
    for i, ln in enumerate(lines):
        text(c, ln, l + (240 if i == 0 else 300), t + 300 + i * 150, 70, INK, "semibold", max_w=r - l - 380)
    text(c, p.get("from", "Dad"), l + 760, t + 1050, 42, INK, "semibold", "center")
    text(c, p.get("signature", "S. S."), l + 1000, t + 1180, 110, INK, "semibold", "center")
    c.restore()
    _vignette(c, 0.5)
    return s.makeImageSnapshot()


# =================================================================== boards / logs
def ins_patient_board_closeup(p, size):
    """Whiteboard close-up, beds 9-12 in large marker; the bed-12 name is faded (ghost writing)."""
    s, c = _begin(size)
    c.drawRect(_R(0, 0, LW, LH), _rad(LW * 0.5, LH * 0.45, LW * 0.7, ["#f6f8f8", "#dfe4e4", "#8a9290"]))
    c.drawRect(_R(0, 0, LW, 200), fill("#3a4440"))
    c.drawRect(_R(0, 180, LW, 210), fill("#c9ced0"))
    text(c, p.get("title", "WARD 4 PATIENTS"), 300, 330, 70, INK, "semibold")
    rows = p.get("rows") or [["9", "Aunt C."], ["10", "Uncle T."], ["11", "Grandma S."], ["12", "B. S."]]
    for i, (num, name) in enumerate(rows):
        y = 420 + i * 300
        text(c, num, 330, y + 200, 150, "#2a2c33", "bold", "center")
        faded = i == len(rows) - 1 and p.get("fade_last", True)
        text(c, name, 640, y + 200, 150, INK, "semibold", a=0.45 if faded else 1.0)
        c.drawLine(220, y + 290, LW - 220, y + 290, stroke("#a8aeb0", 6))
    c.drawLine(510, 400, 510, 1620, stroke("#a8aeb0", 6))
    _vignette(c, 0.45)
    return s.makeImageSnapshot()


def ins_call_log_empty(p, size):
    """Night call-bell log with headers only -- no rows left."""
    s, c = _begin(size)
    _wood_top(c, "#5e3e28")
    l, t, r, b = 820.0, 200.0, 3020.0, 860.0
    c.save()
    c.rotate(-1.5, (l + r) / 2, (t + b) / 2)
    _shadow(c, rrect(l, t, r, b, 6), 40, 26, 0.5)
    c.drawRect(_R(l, t, r, b), _lin((l, t), (r, b), ["#f6f2e6", "#ece6d6"]))
    text(c, p.get("title", "CALL BELL LOG (NIGHT SHIFT)"), l + 160, t + 200, 96, "#2a2a2a", "bold", max_w=r - l - 300)
    for k, h in enumerate(("TIME", "BED", "ANSWERED BY")):
        text(c, h, l + 160 + [0, 560, 960][k], t + 360, 62, "#5a5a5a", "semibold")
    c.drawLine(l + 160, t + 400, r - 100, t + 390, stroke("#7a746a", 5))
    c.restore()
    _vignette(c, 0.55)
    return s.makeImageSnapshot()


# =================================================================== oxygen outlet
def ins_oxygen_outlet(p, size):
    """Wall gas panel with O2 (green ring) and AIR outlets; flowmeter plugged into O2, a hand on the humidifier."""
    s, c = _begin(size)
    c.drawRect(_R(0, 0, LW, 1520), _rad(LW * 0.3, LH * 0.25, LW * 0.8, ["#6a9a98", "#4a7a78", "#2e4c4c"]))
    c.drawRect(_R(0, 1520, LW, LH), fill("#1e3030"))
    l, t, r, b = 1280.0, 300.0, 2560.0, 900.0
    _shadow(c, rrect(l, t, r, b, 40), 30, 20, 0.45)
    c.drawPath(rrect(l, t, r, b, 40), fill("#eeeeea"))
    c.drawPath(rrect(l, t, r, b, 40), stroke("#b4b8b8", 8))
    c.drawLine(l + 120, t + 50, r - 120, t + 70, stroke("#ffffff", 14, 0.8))
    for k, (lab, ring) in enumerate((("O2", "#2f9a5a"), ("AIR", "#e8e8e4"))):
        cx = l + 360 + k * 560
        c.drawCircle(cx, t + 300, 140, fill(ring))
        c.drawCircle(cx, t + 300, 140, stroke("#c9ccca", 6))
        c.drawCircle(cx, t + 300, 80, fill("#2a3a3a" if k == 0 else "#3a3e48"))
        text(c, lab, cx, t + 540, 84, ring if k == 0 else "#5a5e66", "bold", "center")
    fx = l + 360
    c.drawRect(_R(fx - 60, t + 440, fx + 60, t + 560), fill("#c9ced2"))
    c.drawPath(rrect(fx - 105, t + 560, fx + 105, t + 1240, 30), fill("#b8d0d4", 0.85))
    c.drawPath(rrect(fx - 105, t + 560, fx + 105, t + 1240, 30), stroke("#eef2f2", 8))
    for k in range(9):
        c.drawLine(fx - 80, t + 640 + k * 60, fx - 80 + (50 if k % 2 else 70), t + 640 + k * 60, stroke("#2a2e30", 8))
    c.drawCircle(fx, t + 1180, 40, fill("#2f9a5a"))
    c.drawRect(_R(fx - 130, t + 1240, fx + 130, t + 1320), fill("#9aa0a4"))
    c.drawPath(rrect(fx - 170, t + 1320, fx + 170, LH + 100, 50), fill("#3a5252", 0.9))
    c.drawPath(capsule(fx + 40, LH + 120, fx + 250, t + 1520, 120, 90), fill(p.get("skin", "#9a6a48")))
    _vignette(c, 0.5)
    return s.makeImageSnapshot()


# =================================================================== belongings bag / photo / boat / tracks
def ins_belongings_bag(p, size):
    """Clear plastic belongings bag with handles on a blanket, red printed label, a hand resting on it."""
    s, c = _begin(size)
    _bed_sheet(c, "#b4c2bc")
    l, t, r, b = 620.0, 300.0, 1720.0, 1240.0
    for sx in (l + 230, r - 230):
        c.drawArc(_R(sx - 130, t - 160, sx + 130, t + 100), 180, 180, False, stroke("#f4f6f6", 26, 0.85))
    bag = rrect(l, t, r, b, 160)
    c.drawPath(bag, fill("#ffffff", 0.55))
    c.drawPath(bag, stroke("#ffffff", 10, 0.8))
    for k in range(9):
        x = l + 150 + k * 100
        c.drawLine(x, t + 120, x + 20 * math.sin(k), b - 150, stroke("#9aa6a6", 6, 0.6))
    c.drawArc(_R(l + 160, t + 160, r - 160, t + 500), 200, 140, False, stroke("#ffffff", 16, 0.9))
    text(c, p.get("label", "BELONGINGS"), (l + r) / 2, (t + b) / 2 + 260, 90, "#e06a6a", "bold", "center", a=0.85)
    c.drawPath(capsule(LW * 0.62, 640, 1560, 720, 200, 170), fill("#2a3a5e"))
    c.drawPath(capsule(1580, 712, 1300, 720, 150, 130), fill(p.get("skin", "#e8c09a")))
    _vignette(c, 0.5)
    return s.makeImageSnapshot()


def ins_torn_photo_man(p, size):
    """Large torn photo: smiling man in a yellow shirt reaching out (the other half was torn away), sunset sky."""
    s, c = _begin(size)
    c.drawRect(_R(0, 0, LW, LH), _lin((0, 0), (LW, 0), ["#3a3e34", "#7a7e66", "#4a4e40"]))
    l, t, r = 1380.0, 60.0, 3300.0
    rng = random.Random(4)
    edge = [(r - 80 + rng.uniform(-120, 120) * (1 if k % 2 else -1), t + k * 230) for k in range(11)]
    frame = poly([(l, t), (edge[0][0], t)] + edge + [(l, LH + 50)])
    _shadow(c, frame, 40, 30, 0.6)
    c.drawPath(frame, fill("#f6f0e4"))
    c.save()
    c.clipPath(frame, skia.ClipOp.kIntersect, True)
    c.drawRect(_R(l + 190, t + 200, r, LH), _lin((0, t + 200), (0, LH), ["#a8c0d0", "#e8d4a8", "#b89a70"]))
    gx, gy = 2280.0, 780.0
    c.drawPath(poly([(gx - 400, gy + 400), (gx + 360, gy + 400), (gx + 420, LH + 60), (gx - 460, LH + 60)]),
               fill(p.get("shirt", "#e0b040")))
    c.drawCircle(gx, gy, 300, fill("#c89060"))
    c.drawPath(poly([(gx - 340, gy - 120), (gx, gy - 340), (gx + 340, gy - 120), (gx, gy - 230)]), fill("#3e3226"))
    c.drawArc(_R(gx - 130, gy + 60, gx + 130, gy + 170), 20, 140, False, stroke("#3e3226", 50))
    c.drawArc(_R(gx - 160, gy + 130, gx + 160, gy + 260), 20, 140, False, stroke("#9a5a3a", 30))
    c.drawPath(capsule(gx + 300, gy + 700, r + 200, gy + 650, 100, 100), fill("#c89060"))
    c.drawPath(poly([(3000, 1900), (3200, 1650), (3260, 1950)]), fill("#f4f4f0"))
    c.restore()
    _vignette(c, 0.5)
    return s.makeImageSnapshot()


def ins_paper_boat_pillow(p, size):
    """Paper boat left on a white pillow (top view) over a pale blanket."""
    s, c = _begin(size)
    _bed_sheet(c, "#9ab8b0")
    l, t, r, b = 600.0, 340.0, 3260.0, 1760.0
    _shadow(c, rrect(l, t, r, b, 200), 40, 20, 0.35)
    c.drawPath(rrect(l, t, r, b, 200), _lin((0, t), (0, b), ["#e6e6dc", "#d8d8cc", "#c4c4b6"]))
    for y in (t + 220, b - 220):
        c.drawLine(l + 120, y, r - 120, y + 10, stroke("#bcbcae", 24))
    c.drawArc(_R(1380, 880, 2420, 1500), 200, 140, False, stroke("#c8c8ba", 60, 0.8))
    _boat(c, 1960, 1260, 980)
    _vignette(c, 0.45)
    return s.makeImageSnapshot()


def ins_wheel_tracks(p, size):
    """Two wet wheel tracks curving across dark ward tiles to the wheel of a bed (top-down)."""
    s, c = _begin(size)
    c.drawRect(_R(0, 0, LW, LH), fill("#2e4246"))
    for x in range(-400, int(LW) + 400, 330):
        c.drawLine(x, 0, x + 260, LH, stroke("#1c2a2e", 5))
    for y in range(0, int(LH), 300):
        c.drawLine(0, y, LW, y - 60, stroke("#1c2a2e", 5))
    rng = random.Random(3)
    for _ in range(400):
        c.drawCircle(rng.uniform(0, LW), rng.uniform(0, LH), rng.uniform(2, 5), fill("#8aa4a4", 0.4))
    c.drawPath(poly([(2720, 0), (LW, 0), (LW, 470), (2740, 640)]), _lin((2720, 0), (LW, 600), ["#e6eaea", "#b4bcbe"]))
    c.drawPath(poly([(2740, 600), (LW, 440), (LW, 500), (2740, 660)]), fill("#7e8a8e"))
    c.drawCircle(3270, 700, 100, fill("#1a1c20"))
    c.drawCircle(3270, 700, 40, fill("#9aa0a6"))
    for k, dx in enumerate((0, 150)):
        path = skia.Path()
        path.moveTo(780 + dx, 1960)
        path.cubicTo(1300 + dx, 1300, 2300 + dx, 900, 3160 + dx * 0.6, 760 + k * 60)
        c.drawPath(path, stroke("#7a9a9a", 58, 0.75))
        c.drawPath(path, _dash_paint("#c8dcdc", 8, 40, 30, 0.8))
    c.drawCircle(700, 1560, 420, _rad(700, 1560, 420, [("#f0e8c8", 0.35), ("#f0e8c8", 0.0)]))
    _vignette(c, 0.55)
    return s.makeImageSnapshot()


def _dash_paint(col, w, on, off, a):
    pt = stroke(col, w, a)
    pt.setPathEffect(skia.DashPathEffect.Make([on, off], 0))
    return pt


# =================================================================== registration
def _with(fn, **defaults):
    def run(p, size):
        q = dict(defaults)
        q.update(p or {})
        return fn(q, size)
    run.__doc__ = fn.__doc__
    return run


INSERTS = {
    "rules_note_desk": ins_rules_note_desk,
    "rules_note_desk_blank_pen": _with(ins_rules_note_desk, rules=[], pen=True, rotation=-2.0),
    "rules_note_desk_rule4": _with(ins_rules_note_desk, underline=3),
    "rules_note_desk_blur": _with(ins_rules_note_desk, underline=3, blur=True),
    "roster_copy_stamp": ins_roster_copy,
    "desk_coffee_phone": ins_desk_coffee_phone,
    "desk_coffee_phone_roster": _with(ins_desk_coffee_phone, roster=True),
    "patient_wristband_unknown": ins_patient_wristband,
    "patient_wristband_named": _with(ins_patient_wristband, name="S. S."),
    "vital_monitor_big": ins_vital_monitor_big,
    "vital_monitor_big_alarm": _with(ins_vital_monitor_big, hr=102, spo2=80, nibp="90/56", spo2_alarm=True),
    "vital_monitor_big_flat": _with(ins_vital_monitor_big, flat=True),
    "phone_call_doctor": _phone("call", {"contact": "Dr. T", "call_status": "00:07", "time": "01:12",
                                         "bg": "blur_location"}),
    "phone_lock_photo_msg": _phone("lock", {"time": "02:14", "date": "Friday, 2",
                                            "notification": {"app": "Chat", "sender": "Mr. N. R.", "text": "Sent a photo",
                                                             "when": "now"}, "bg": "blur_location"}),
    "phone_letter_photo": _phone("letter_photo", {"bg": "blur_location"}),
    "phone_browser_blank": _phone("browser", {"bg": "blur_location"}),
    "letter_from_dad": ins_letter_from_dad,
    "patient_board_closeup": ins_patient_board_closeup,
    "call_log_empty": ins_call_log_empty,
    "oxygen_outlet": ins_oxygen_outlet,
    "belongings_bag": ins_belongings_bag,
    "torn_photo_man": ins_torn_photo_man,
    "paper_boat_pillow": ins_paper_boat_pillow,
    "wheel_tracks_wet": ins_wheel_tracks,
}

TAGS = {
    "rules_note_desk": ["rules", "night shift rules", "note", "desk", "head nurse"],
    "rules_note_desk_blank_pen": ["blank rules", "writing rules", "pen", "note", "desk"],
    "rules_note_desk_rule4": ["rules", "rule 4", "forget everything", "underlined", "note"],
    "rules_note_desk_blur": ["rules", "blurred note", "memory", "underlined"],
    "roster_copy_stamp": ["roster", "copy", "stamp", "duty schedule", "evidence"],
    "desk_coffee_phone": ["desk", "coffee", "phone face down", "top view", "waiting"],
    "desk_coffee_phone_roster": ["desk", "coffee", "phone", "roster copy", "top view"],
    "patient_wristband_unknown": ["wristband", "patient id", "unknown patient", "hospital band"],
    "patient_wristband_named": ["wristband", "name written", "patient id", "identified"],
    "vital_monitor_big": ["vital signs", "heart monitor", "ecg", "spo2", "patient monitor"],
    "vital_monitor_big_alarm": ["vital signs", "low oxygen", "alarm", "spo2 red", "critical"],
    "vital_monitor_big_flat": ["flatline", "death", "monitor zero", "heart stopped"],
    "phone_call_doctor": ["phone call", "calling doctor", "call screen", "night"],
    "phone_lock_photo_msg": ["lock screen", "notification", "sent a photo", "message", "2 am"],
    "phone_letter_photo": ["phone", "photo of letter", "handwritten letter", "message"],
    "phone_browser_blank": ["phone", "browser", "search", "empty screen"],
    "letter_from_dad": ["letter", "handwritten", "father", "dad", "note"],
    "patient_board_closeup": ["patient board", "whiteboard", "bed 12", "faded name", "ghost"],
    "call_log_empty": ["call log", "empty log", "no entries", "night shift"],
    "oxygen_outlet": ["oxygen", "o2 outlet", "flowmeter", "wall gas panel", "hospital"],
    "belongings_bag": ["belongings", "plastic bag", "patient items", "personal effects"],
    "torn_photo_man": ["torn photo", "father", "yellow shirt", "memory", "photo half"],
    "paper_boat_pillow": ["paper boat", "pillow", "left behind", "sign", "bed"],
    "wheel_tracks_wet": ["wheel tracks", "wet floor", "bed wheel", "trail", "ghost"],
}

PROPS = {k: [k] for k in INSERTS}
PROPS.update({
    "roster_copy_stamp": ["roster_copy", "stamped_roster"],
    "patient_wristband_unknown": ["wristband", "patient_wristband", "hospital_band"],
    "vital_monitor_big": ["vital_monitor_big", "big_heart_monitor"],
    "vital_monitor_big_flat": ["flatline_monitor", "flatline"],
    "oxygen_outlet": ["oxygen_outlet", "o2_outlet", "flowmeter"],
    "belongings_bag": ["belongings_bag", "patient_belongings"],
    "letter_from_dad": ["handwritten_letter", "letter_from_dad", "father_letter"],
})
