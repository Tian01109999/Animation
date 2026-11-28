"""Batch-4 inserts -- extended library (provenance 'procedural_library'), same flat-vector style as insertgen.

Theme: urban sci-fi thriller props (countdown-app phone + variants, home screen, "wanted" and live-stream screens,
AI glowing ring, repair price board, billboards, queue table screen, laptop list, upload dialog, staff badge on a
lanyard, wind-up wristwatch, boat-noodle bowl, glowing trouser pocket, CCTV cameras, disguise in a laundry basket,
USB stick into a server, public payphone, old sedan, motorbike, water-jug trolley).

Every drawing is ORIGINAL code (skia); no brands/logos. ALL baked-in text is ENGLISH and generic (no app/company/
person/place names: people are initials, places are "ZONE A" etc.) and comes from params (editable in the catalog
or sidecar). This source file is kept pure ASCII on purpose.

Logical 3840x2160 coordinates (canvas scaled to the output size). Loaded by insertgen at the end of the module (like
insertgen_batch2/3): INSERTS / SCREENS / TAGS / PROPS are merged into insertgen's tables.
"""
from __future__ import annotations

import math
import random

import skia

from .insertgen import _chat_glyph, _hand, _lin, _rad, _shadow, _silhouette, _status_bar, hand_tip, text
from .insertgen_batch2 import (LH, LW, _begin, _blurred, _bokeh, _concrete, _crack, _dash, _handset, _phone_in_hand,
                               _spaced, _tiles, _vignette, _wood_top)
from .insertgen_batch3 import _cone, _soft_glow, _speckle
from .skutil import capsule, color, fill, font, nfc, oval, poly, rrect, shade, smooth, stroke, wrap_text

RING_COLS = ["#35e0ff", "#5a8cff", "#a65cff", "#ff5ab4", "#ffb04a", "#35e0ff"]
RED_RING = ["#ff4a4a", "#ff8a5a", "#ff2f6a", "#ff4a4a"]


# =================================================================== shared helpers
def _R(l, t, r, b) -> skia.Rect:
    return skia.Rect.MakeLTRB(l, t, r, b)


def _ring(c, cx, cy, r, w=None, cols=None, glow=1.0, ticks=True) -> None:
    """Glowing gradient ring (sweep gradient + blurred halo + hot white core + faint inner tick ring)."""
    w = w or r * 0.14
    cols = cols or RING_COLS
    shader = skia.GradientShader.MakeSweep(cx, cy, [color(x) for x in cols])
    if glow > 0:
        _soft_glow(c, cx, cy, r * 2.0, cols[1], 0.4 * glow)
        p = skia.Paint(AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=w * 2.4, Shader=shader)
        p.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, w * 0.9))
        p.setAlphaf(min(1.0, 0.8 * glow))
        c.drawCircle(cx, cy, r, p)
    c.drawCircle(cx, cy, r - w * 0.5, fill("#ffffff", 0.035))
    c.drawCircle(cx, cy, r, skia.Paint(AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=w, Shader=shader))
    c.drawCircle(cx, cy, r, stroke("#ffffff", w * 0.16, 0.6))
    if ticks:
        for k in range(60):
            a = k / 60 * math.tau
            r0, r1 = r * (0.74 if k % 5 else 0.7), r * 0.8
            c.drawLine(cx + math.cos(a) * r0, cy + math.sin(a) * r0, cx + math.cos(a) * r1, cy + math.sin(a) * r1,
                       stroke("#ffffff", w * (0.09 if k % 5 else 0.14), 0.25 if k % 5 else 0.45))


def _glow_text(c, s, x, y, size, col, weight="extrabold", align="left", max_w=None, glow=0.7) -> float:
    s = nfc(str(s))
    f = font(size, weight)
    w = f.measureText(s)
    if max_w and w > max_w > 0:
        f = font(size * max_w / w, weight)
        w = f.measureText(s)
    if align == "center":
        x -= w / 2
    elif align == "right":
        x -= w
    if glow > 0:
        c.drawString(s, x, y, f, _blurred(col, glow, f.getSize() * 0.12))
    c.drawString(s, x, y, f, fill(col))
    return w


def _icon(c, kind, cx, cy, r, col="#ffffff", a=1.0) -> None:
    """Small line/flat icons: cal, pin, share, eye, heart, user, clock, check, warn, play, x."""
    w = r * 0.16
    if kind == "cal":
        c.drawPath(rrect(cx - r * 0.8, cy - r * 0.62, cx + r * 0.8, cy + r * 0.8, r * 0.18), stroke(col, w, a))
        c.drawRect(_R(cx - r * 0.8, cy - r * 0.62, cx + r * 0.8, cy - r * 0.25), fill(col, a))
        for dx in (-0.4, 0.4):
            c.drawLine(cx + dx * r, cy - r * 0.85, cx + dx * r, cy - r * 0.5, stroke(col, w, a))
        for i in range(3):
            for j in range(2):
                c.drawCircle(cx + (i - 1) * r * 0.45, cy + r * (0.08 + j * 0.38), r * 0.09, fill(col, a))
    elif kind == "pin":
        c.drawPath(smooth([(cx, cy + r), (cx - r * 0.62, cy - r * 0.05), (cx - r * 0.5, cy - r * 0.7),
                           (cx, cy - r * 0.95), (cx + r * 0.5, cy - r * 0.7), (cx + r * 0.62, cy - r * 0.05)]),
                   fill(col, a))
        c.drawCircle(cx, cy - r * 0.42, r * 0.24, fill("#000000", 0.45 * a))
    elif kind == "share":
        pts = [(cx + r * 0.55, cy - r * 0.6), (cx - r * 0.55, cy), (cx + r * 0.55, cy + r * 0.6)]
        c.drawPath(poly(pts, close=False), stroke(col, w, a))
        for x, y in pts:
            c.drawCircle(x, y, r * 0.28, fill(col, a))
    elif kind == "eye":
        e = skia.Path()
        e.moveTo(cx - r, cy)
        e.quadTo(cx, cy - r * 1.1, cx + r, cy)
        e.quadTo(cx, cy + r * 1.1, cx - r, cy)
        c.drawPath(e, stroke(col, w, a))
        c.drawCircle(cx, cy, r * 0.32, fill(col, a))
    elif kind == "heart":
        c.drawPath(_heart_path(cx, cy, r), fill(col, a))
    elif kind == "user":
        c.drawCircle(cx, cy - r * 0.35, r * 0.38, fill(col, a))
        c.drawPath(rrect(cx - r * 0.7, cy + r * 0.15, cx + r * 0.7, cy + r * 0.95, r * 0.4), fill(col, a))
    elif kind == "clock":
        c.drawCircle(cx, cy, r * 0.85, stroke(col, w, a))
        c.drawLine(cx, cy, cx, cy - r * 0.55, stroke(col, w, a))
        c.drawLine(cx, cy, cx + r * 0.4, cy + r * 0.2, stroke(col, w, a))
    elif kind == "check":
        c.drawPath(poly([(cx - r * 0.6, cy), (cx - r * 0.15, cy + r * 0.45), (cx + r * 0.65, cy - r * 0.5)],
                        close=False), stroke(col, w * 1.4, a))
    elif kind == "warn":
        tri = poly([(cx, cy - r), (cx + r * 1.05, cy + r * 0.8), (cx - r * 1.05, cy + r * 0.8)])
        c.drawPath(tri, fill(col, a))
        c.drawLine(cx, cy - r * 0.35, cx, cy + r * 0.25, stroke("#1a1a1e", w * 1.2, a))
        c.drawCircle(cx, cy + r * 0.55, w * 0.8, fill("#1a1a1e", a))
    elif kind == "play":
        c.drawPath(poly([(cx - r * 0.4, cy - r * 0.6), (cx + r * 0.6, cy), (cx - r * 0.4, cy + r * 0.6)]), fill(col, a))
    elif kind == "x":
        c.drawLine(cx - r * 0.5, cy - r * 0.5, cx + r * 0.5, cy + r * 0.5, stroke(col, w, a))
        c.drawLine(cx + r * 0.5, cy - r * 0.5, cx - r * 0.5, cy + r * 0.5, stroke(col, w, a))


def _heart_path(cx, cy, r) -> skia.Path:
    p = skia.Path()
    p.moveTo(cx, cy + r * 0.85)
    p.cubicTo(cx - r * 1.3, cy - r * 0.05, cx - r * 0.75, cy - r * 1.05, cx, cy - r * 0.4)
    p.cubicTo(cx + r * 0.75, cy - r * 1.05, cx + r * 1.3, cy - r * 0.05, cx, cy + r * 0.85)
    p.close()
    return p


def _pill_text(c, s, x, y, size, bg, fg="#ffffff", weight="extrabold", pad=0.55, align="left", a=1.0) -> float:
    """Rounded pill with spaced caps text; (x, y) = left/center/right of pill, y = vertical centre. Returns width."""
    s = _spaced(nfc(str(s)).upper())
    f = font(size, weight)
    w = f.measureText(s) + size * pad * 2 * 1.4
    h = size * 1.7
    l = x - w / 2 if align == "center" else (x - w if align == "right" else x)
    c.drawPath(rrect(l, y - h / 2, l + w, y + h / 2, h / 2), fill(bg, a))
    c.drawString(s, l + size * pad * 1.4, y + size * 0.36, f, fill(fg, a))
    return w


def _city_night(c, seed=5, sky=("#0b1030", "#24204a", "#4a2a5a"), horizon=1500.0) -> None:
    c.drawRect(_R(0, 0, LW, LH), _lin((0, 0), (0, horizon), list(sky), [0, 0.65, 1]))
    rng = random.Random(seed)
    for _ in range(90):
        c.drawCircle(rng.uniform(0, LW), rng.uniform(0, horizon * 0.6), rng.uniform(1.5, 4), fill("#ffffff", rng.uniform(0.2, 0.7)))
    for layer, (col, hmin, hmax) in enumerate((("#1a1c36", 380, 820), ("#121428", 250, 640))):
        x = -40.0
        while x < LW:
            w = rng.uniform(160, 360)
            h = rng.uniform(hmin, hmax)
            top = horizon - h + layer * 120
            c.drawRect(_R(x, top, x + w, LH), fill(col))
            for wy in range(int(top + 40), int(LH), 70):
                for wx in range(int(x + 24), int(x + w - 30), 56):
                    if rng.random() < 0.28:
                        c.drawRect(_R(wx, wy, wx + 26, wy + 34), fill(rng.choice(["#ffd27a", "#9ad0ff", "#ffe9b0"]),
                                                                    rng.uniform(0.35, 0.8)))
            x += w + rng.uniform(4, 30)
    c.drawRect(_R(0, horizon - 200, LW, LH), _lin((0, horizon - 200), (0, LH), [("#3a2a5a", 0.0), ("#3a2a5a", 0.45)]))


def _monitor(c, l, t, r, b, bezel=46, stand=True) -> tuple[float, float, float, float]:
    """Flat monitor with bezel + stand. Returns the screen rect (l, t, r, b)."""
    if stand:
        cx = (l + r) / 2
        c.drawPath(poly([(cx - 110, b - 20), (cx + 110, b - 20), (cx + 150, b + 220), (cx - 150, b + 220)]), fill("#1a1b20"))
        c.drawPath(rrect(cx - 420, b + 200, cx + 420, b + 260, 30), fill("#24262c"))
    body = rrect(l, t, r, b, 30)
    _shadow(c, body, 50, 30, 0.6)
    c.drawPath(body, fill("#121317"))
    c.drawPath(rrect(l + 6, t + 6, r - 6, b - 6, 26), stroke("#34363d", 6))
    return l + bezel, t + bezel, r - bezel, b - bezel - 30


def _glass(c, l, t, r, b, a=0.06) -> None:
    c.drawPath(poly([(l, t + (b - t) * 0.7), (l + (r - l) * 0.35, t), (l + (r - l) * 0.5, t), (l, b)]), fill("#ffffff", a))


# =================================================================== phone screens
def _screen_countdown(c, sl, st, sr, sb, d: dict) -> None:
    """Generic countdown app: glowing ring, "TIME LEFT", big red timer, date + place fields, SHARE button.
    d: timer, timer_sub (2nd line, e.g. months), matched (bool) + status, date, place, cracked."""
    sw, sh = sr - sl, sb - st
    matched = bool(d.get("matched"))
    c.drawRect(_R(sl, st, sr, sb), _lin((sl, st), (sl, sb), [d.get("screen_top", "#151b3e"), d.get("screen_bottom", "#06070e")]))
    if matched:
        c.drawRect(_R(sl, st, sr, sb), _rad(sl + sw / 2, st + sh * 0.3, sh * 0.6, [("#ff2a2a", 0.28), ("#ff2a2a", 0.0)]))
    _status_bar(c, sl, st + sh * 0.012, sr, sh * 0.045, d.get("time", "21:12"))
    text(c, _spaced(d.get("app_name", "COUNTDOWN")), sl + sw / 2, st + sh * 0.1, sh * 0.017, "#9aa6d8", "bold", "center",
         max_w=sw * 0.8)
    rcx, rcy, rr = sl + sw / 2, st + sh * 0.27, sw * 0.27
    _ring(c, rcx, rcy, rr, cols=RED_RING if matched else None, glow=1.2 if matched else 1.0)
    c.drawCircle(rcx, rcy, rr * 0.2, _blurred("#ffffff", 0.5, rr * 0.08))
    c.drawCircle(rcx, rcy, rr * 0.12, fill("#ffffff", 0.95))
    text(c, _spaced(d.get("label", "TIME LEFT")), sl + sw / 2, st + sh * 0.47, sh * 0.02, "#aeb6d6", "bold", "center",
         max_w=sw * 0.8)
    timer2 = d.get("timer_sub", "")
    tcol = d.get("timer_color", "#ff3b3b")
    _glow_text(c, d.get("timer", "23:41:07"), sl + sw / 2, st + sh * (0.545 if timer2 else 0.56),
               sh * (0.062 if timer2 else 0.078), tcol, "extrabold", "center", max_w=sw * 0.88)
    extra = 0.0
    if timer2:
        _glow_text(c, timer2, sl + sw / 2, st + sh * 0.6, sh * 0.04, tcol, "extrabold", "center", max_w=sw * 0.8, glow=0.5)
        extra = 0.035
    if matched:
        _pill_text(c, d.get("status", "MATCHED"), sl + sw / 2, st + sh * (0.605 + extra), sh * 0.022, "#ff3b3b",
                   align="center")
        extra += 0.035
    y = st + sh * (0.645 + extra)
    fh = sh * 0.072
    for icon, lab, val in (("cal", d.get("date_label", "DATE"), d.get("date", "TOMORROW 09:13")),
                           ("pin", d.get("place_label", "PLACE"), d.get("place", "ZONE A - LEVEL 2"))):
        if not val:
            continue
        c.drawPath(rrect(sl + sw * 0.07, y, sr - sw * 0.07, y + fh, sw * 0.04), fill("#ffffff", 0.07))
        c.drawPath(rrect(sl + sw * 0.07, y, sr - sw * 0.07, y + fh, sw * 0.04), stroke("#ffffff", sw * 0.004, 0.16))
        c.drawCircle(sl + sw * 0.17, y + fh / 2, fh * 0.3, fill("#ffffff", 0.1))
        _icon(c, icon, sl + sw * 0.17, y + fh / 2, fh * 0.2, "#cfd6ff")
        text(c, _spaced(lab), sl + sw * 0.27, y + fh * 0.38, sh * 0.012, "#8a93b8", "bold")
        text(c, val, sl + sw * 0.27, y + fh * 0.78, sh * 0.022, "#ffffff", "bold", max_w=sw * 0.6)
        y += fh + sh * 0.014
    if d.get("share", True):
        bt, bb = sb - sh * 0.125, sb - sh * 0.065
        btn = rrect(sl + sw * 0.12, bt, sr - sw * 0.12, bb, (bb - bt) / 2)
        c.drawPath(btn, _lin((sl, 0), (sr, 0), ["#5a8cff", "#a65cff", "#ff5ab4"]))
        lab = _spaced(d.get("share_label", "SHARE"))
        tw = font(sh * 0.022, "extrabold").measureText(nfc(lab))
        _icon(c, "share", sl + sw / 2 - tw / 2 - sh * 0.025, (bt + bb) / 2, sh * 0.012)
        text(c, lab, sl + sw / 2 + sh * 0.012, (bt + bb) / 2 + sh * 0.008, sh * 0.022, "#ffffff", "extrabold", "center")
    c.drawPath(rrect(sl + sw * 0.34, sb - sh * 0.022, sr - sw * 0.34, sb - sh * 0.015, sh * 0.004), fill("#ffffff", 0.8))
    if d.get("cracked"):
        _crack(c, sl + sw * float(d.get("crack_x", 0.62)), st + sh * float(d.get("crack_y", 0.42)), sw * 0.95,
               seed=int(d.get("crack_seed", 7)), w=sw * 0.006)


_APP_COLS = {"phone": "#36b35a", "chat": "#2fb86a", "camera": "#5a5f6a", "photos": "#ffffff", "maps": "#3a8ae0",
             "web": "#2e7cf6", "clock": "#16171b", "news": "#e5413a", "music": "#ff4f7a", "mail": "#3a78e8",
             "notes": "#f3c94e", "weather": "#4aa8ff", "wallet": "#1c1d22", "files": "#3a9ae8", "settings": "#8a8f9a",
             "timer": "#0d0f1f", "store": "#2f8cff", "calc": "#3a3c44", "health": "#ffffff", "video": "#e8833a"}


def _app_glyph(c, name: str, cx, cy, s) -> None:
    """App icon tile (s = tile size) with an original flat glyph."""
    key = nfc(str(name)).lower()
    bg = _APP_COLS.get(key, "#6a5acd")
    tile = rrect(cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2, s * 0.24)
    c.drawPath(tile, _lin((0, cy - s / 2), (0, cy + s / 2), [shade(bg, 0.12), shade(bg, -0.08)]))
    r = s * 0.3
    W = "#ffffff"
    if key == "phone":
        _handset(c, cx, cy + r * 0.1, r * 1.6, W, 135)
    elif key == "chat":
        _chat_glyph(c, cx, cy, r * 1.4, W)
    elif key == "camera":
        c.drawPath(rrect(cx - r, cy - r * 0.6, cx + r, cy + r * 0.75, r * 0.2), fill("#d9dce2"))
        c.drawPath(rrect(cx - r * 0.35, cy - r * 0.8, cx + r * 0.35, cy - r * 0.5, r * 0.1), fill("#d9dce2"))
        c.drawCircle(cx, cy + r * 0.08, r * 0.45, fill("#2a2c33"))
        c.drawCircle(cx, cy + r * 0.08, r * 0.25, fill("#5a8cff"))
    elif key == "photos":
        for k, col in enumerate(("#ff5a5a", "#ffb04a", "#3cc46a", "#3a8ae0", "#a65cff", "#ff5ab4")):
            a = k / 6 * math.tau
            c.drawPath(oval(cx + math.cos(a) * r * 0.45, cy + math.sin(a) * r * 0.45, r * 0.42, r * 0.42), fill(col, 0.85))
    elif key == "maps":
        c.drawRect(_R(cx - s / 2, cy + r * 0.2, cx + s / 2, cy + r * 0.5), fill("#ffffff", 0.35))
        c.drawRect(_R(cx - r * 0.2, cy - s / 2, cx + r * 0.1, cy + s / 2), fill("#ffffff", 0.35))
        _icon(c, "pin", cx, cy - r * 0.1, r * 0.85, "#e5413a")
    elif key == "web":
        c.drawCircle(cx, cy, r, stroke(W, r * 0.12))
        c.drawPath(oval(cx, cy, r * 0.45, r), stroke(W, r * 0.1))
        c.drawLine(cx - r, cy, cx + r, cy, stroke(W, r * 0.1))
        c.drawLine(cx, cy - r, cx, cy + r, stroke(W, r * 0.1))
    elif key == "clock":
        c.drawCircle(cx, cy, r * 1.05, fill(W))
        for k in range(12):
            a = k / 12 * math.tau
            c.drawCircle(cx + math.cos(a) * r * 0.85, cy + math.sin(a) * r * 0.85, r * 0.06, fill("#16171b"))
        c.drawLine(cx, cy, cx + r * 0.45, cy - r * 0.3, stroke("#16171b", r * 0.12))
        c.drawLine(cx, cy, cx - r * 0.1, cy - r * 0.75, stroke("#16171b", r * 0.08))
        c.drawLine(cx, cy, cx - r * 0.5, cy + r * 0.55, stroke("#e5413a", r * 0.05))
    elif key == "news":
        c.drawPath(rrect(cx - r * 0.9, cy - r * 0.8, cx + r * 0.9, cy + r * 0.8, r * 0.12), fill(W))
        c.drawRect(_R(cx - r * 0.7, cy - r * 0.6, cx - r * 0.05, cy - r * 0.05), fill("#e5413a"))
        for k in range(4):
            yy = cy - r * 0.5 + k * r * 0.3
            c.drawLine(cx + (r * 0.12 if k < 2 else -r * 0.7), yy, cx + r * 0.7, yy, stroke("#9aa0aa", r * 0.09))
    elif key == "music":
        c.drawCircle(cx - r * 0.35, cy + r * 0.55, r * 0.3, fill(W))
        c.drawCircle(cx + r * 0.55, cy + r * 0.35, r * 0.3, fill(W))
        c.drawLine(cx - r * 0.08, cy + r * 0.55, cx - r * 0.08, cy - r * 0.7, stroke(W, r * 0.13))
        c.drawLine(cx + r * 0.82, cy + r * 0.35, cx + r * 0.82, cy - r * 0.9, stroke(W, r * 0.13))
        c.drawPath(poly([(cx - r * 0.08, cy - r * 0.7), (cx + r * 0.82, cy - r * 0.9), (cx + r * 0.82, cy - r * 0.55),
                         (cx - r * 0.08, cy - r * 0.35)]), fill(W))
    elif key == "mail":
        c.drawPath(rrect(cx - r, cy - r * 0.65, cx + r, cy + r * 0.65, r * 0.12), fill(W))
        c.drawPath(poly([(cx - r, cy - r * 0.6), (cx, cy + r * 0.1), (cx + r, cy - r * 0.6)], close=False),
                   stroke(bg, r * 0.12))
    elif key == "notes":
        c.drawRect(_R(cx - s / 2, cy - s / 2, cx + s / 2, cy - s * 0.22), fill("#ffffff", 0.0))
        c.drawPath(rrect(cx - r * 0.85, cy - r * 0.9, cx + r * 0.85, cy + r * 0.9, r * 0.1), fill("#fffbe8"))
        for k in range(4):
            c.drawLine(cx - r * 0.6, cy - r * 0.45 + k * r * 0.33, cx + r * 0.6, cy - r * 0.45 + k * r * 0.33,
                       stroke("#c8a640", r * 0.08))
    elif key == "weather":
        c.drawCircle(cx - r * 0.25, cy - r * 0.25, r * 0.5, fill("#ffd24a"))
        for (dx, dy, rr) in ((-0.2, 0.3, 0.42), (0.25, 0.15, 0.5), (0.65, 0.35, 0.35)):
            c.drawCircle(cx + dx * r, cy + dy * r, rr * r, fill(W))
        c.drawRect(_R(cx - r * 0.55, cy + r * 0.35, cx + r * 0.95, cy + r * 0.72), fill(W))
    elif key == "wallet":
        for k, col in enumerate(("#3cc46a", "#ffb04a", "#3a8ae0")):
            c.drawPath(rrect(cx - r * 0.9, cy - r * 0.8 + k * r * 0.25, cx + r * 0.9, cy - r * 0.2 + k * r * 0.25, r * 0.12),
                       fill(col))
        c.drawPath(rrect(cx - r, cy - r * 0.1, cx + r, cy + r * 0.85, r * 0.15), fill("#2e3038"))
    elif key == "files":
        c.drawPath(poly([(cx - r, cy - r * 0.6), (cx - r * 0.25, cy - r * 0.6), (cx - r * 0.05, cy - r * 0.35),
                         (cx + r, cy - r * 0.35), (cx + r, cy + r * 0.75), (cx - r, cy + r * 0.75)]), fill(W))
    elif key == "settings":
        g = skia.Path()
        for k in range(16):
            a = k / 16 * math.tau
            rr = r * (1.0 if k % 2 == 0 else 0.78)
            (g.moveTo if k == 0 else g.lineTo)(cx + math.cos(a) * rr, cy + math.sin(a) * rr)
        g.close()
        c.drawPath(g, fill("#e6e8ec"))
        c.drawCircle(cx, cy, r * 0.35, fill(bg))
    elif key == "timer":
        _ring(c, cx, cy, r * 0.8, w=r * 0.22, glow=0.6, ticks=False)
    elif key == "store":
        c.drawPath(rrect(cx - r * 0.8, cy - r * 0.35, cx + r * 0.8, cy + r * 0.85, r * 0.15), fill(W))
        c.drawArc(_R(cx - r * 0.4, cy - r * 0.85, cx + r * 0.4, cy + r * 0.05), 180, 180, False, stroke(W, r * 0.12))
    elif key == "calc":
        for i in range(2):
            for j in range(2):
                col = "#ff9f2e" if (i, j) == (1, 1) else "#8a8d96"
                c.drawCircle(cx + (i - 0.5) * r * 0.95, cy + (j - 0.5) * r * 0.95, r * 0.38, fill(col))
    elif key == "health":
        c.drawPath(_heart_path(cx, cy, r * 0.85), fill("#ff4f6a"))
    elif key == "video":
        c.drawPath(rrect(cx - r, cy - r * 0.6, cx + r * 0.45, cy + r * 0.6, r * 0.15), fill(W))
        c.drawPath(poly([(cx + r * 0.5, cy - r * 0.1), (cx + r, cy - r * 0.5), (cx + r, cy + r * 0.5), (cx + r * 0.5, cy + r * 0.1)]),
                   fill(W))
    else:
        text(c, (nfc(str(name)) or "?")[:1].upper(), cx, cy + r * 0.45, r * 1.3, W, "extrabold", "center")
    c.drawPath(rrect(cx - s / 2, cy - s / 2, cx + s / 2, cy - s * 0.05, s * 0.24), fill("#ffffff", 0.06))


_HOME_APPS = ["Clock", "Maps", "Photos", "Camera", "News", "Music", "Video", "Notes", "Weather", "Wallet", "Files",
              "Settings", "Timer", "Store", "Calc", "Health"]
_DOCK_APPS = ["Phone", "Chat", "Web", "Mail"]


def _screen_home(c, sl, st, sr, sb, d: dict) -> None:
    """Home screen: wallpaper, clock widget, 4x4 app grid with English labels, dock, badges, optional glowing app."""
    sw, sh = sr - sl, sb - st
    c.drawRect(_R(sl, st, sr, sb), _lin((sl, st), (sr, sb), [d.get("wall0", "#2a3a7a"), d.get("wall1", "#7a3a8a"),
                                                             d.get("wall2", "#e07a6a")], [0, 0.6, 1]))
    for k, (x, y, rr, col) in enumerate(((0.2, 0.75, 0.5, "#ffb07a"), (0.85, 0.3, 0.45, "#5a6aff"),
                                         (0.5, 1.0, 0.6, "#ff7aa8"))):
        c.drawCircle(sl + sw * x, st + sh * y, sw * rr, _blurred(col, 0.35, sw * 0.1))
    _status_bar(c, sl, st + sh * 0.012, sr, sh * 0.045, d.get("time", "21:12"))
    text(c, d.get("clock", "21:12"), sl + sw / 2, st + sh * 0.155, sh * 0.075, "#ffffff", "semibold", "center")
    text(c, d.get("date", "Friday, June 14"), sl + sw / 2, st + sh * 0.195, sh * 0.02, "#ffffff", "semibold", "center",
         a=0.85)
    apps = list(d.get("apps") or _HOME_APPS)[:20]
    badges = d.get("badges") if isinstance(d.get("badges"), dict) else {"News": 3}
    hi = nfc(str(d.get("highlight", "Timer"))).lower()
    s = sw * 0.165
    for i, name in enumerate(apps):
        cx = sl + sw * (0.14 + 0.24 * (i % 4))
        cy = st + sh * (0.28 + 0.105 * (i // 4))
        if nfc(str(name)).lower() == hi:
            c.drawPath(rrect(cx - s * 0.62, cy - s * 0.62, cx + s * 0.62, cy + s * 0.62, s * 0.3), _blurred("#7ad0ff", 0.7, s * 0.12))
        _app_glyph(c, name, cx, cy, s)
        text(c, name, cx, cy + s * 0.5 + sh * 0.022, sh * 0.0145, "#ffffff", "semibold", "center", max_w=sw * 0.22)
        n = badges.get(name)
        if n:
            c.drawCircle(cx + s * 0.45, cy - s * 0.45, s * 0.17, fill("#ff3b30"))
            text(c, str(n), cx + s * 0.45, cy - s * 0.45 + s * 0.08, s * 0.2, "#ffffff", "bold", "center")
    for k in range(3):
        c.drawCircle(sl + sw / 2 + (k - 1) * sw * 0.035, sb - sh * 0.165, sw * 0.008, fill("#ffffff", 0.9 if k == 0 else 0.4))
    dt, db = sb - sh * 0.14, sb - sh * 0.035
    c.drawPath(rrect(sl + sw * 0.04, dt, sr - sw * 0.04, db, sw * 0.08), fill("#ffffff", 0.2))
    dock = list(d.get("dock") or _DOCK_APPS)[:4]
    for i, name in enumerate(dock):
        _app_glyph(c, name, sl + sw * (0.14 + 0.24 * i), (dt + db) / 2, s)
        n = badges.get(name)
        if n:
            cx, cy = sl + sw * (0.14 + 0.24 * i), (dt + db) / 2
            c.drawCircle(cx + s * 0.45, cy - s * 0.45, s * 0.17, fill("#ff3b30"))
            text(c, str(n), cx + s * 0.45, cy - s * 0.45 + s * 0.08, s * 0.2, "#ffffff", "bold", "center")


def _screen_wanted(c, sl, st, sr, sb, d: dict) -> None:
    """Alert screen: red header, portrait silhouette, FIND THIS MAN, REWARD, info lines, red REPORT button."""
    sw, sh = sr - sl, sb - st
    c.drawRect(_R(sl, st, sr, sb), fill("#f3f1ee"))
    hb = st + sh * 0.13
    c.drawRect(_R(sl, st, sr, hb), _lin((sl, st), (sr, hb), ["#c41f1f", "#ff4a3a"]))
    _status_bar(c, sl, st + sh * 0.012, sr, sh * 0.045, d.get("time", "21:12"))
    _icon(c, "warn", sl + sw * 0.11, st + sh * 0.09, sh * 0.016, "#ffffff")
    text(c, _spaced(d.get("header", "ALERT")), sl + sw * 0.18, st + sh * 0.1, sh * 0.024, "#ffffff", "extrabold")
    text(c, d.get("header_sub", "2 min ago"), sr - sw * 0.06, st + sh * 0.1, sh * 0.016, "#ffffff", "semibold", "right",
         a=0.85)
    pl, pt, pr, pb = sl + sw * 0.18, hb + sh * 0.035, sr - sw * 0.18, hb + sh * 0.33
    c.drawPath(rrect(pl - sw * 0.015, pt - sw * 0.015, pr + sw * 0.015, pb + sw * 0.015, sw * 0.03), fill("#ffffff"))
    c.save()
    c.clipPath(rrect(pl, pt, pr, pb, sw * 0.02), skia.ClipOp.kIntersect, True)
    _silhouette(c, pl, pt, pr, pb, d.get("silhouette", "#3a3f4a"))
    text(c, "?", (pl + pr) / 2, pt + (pb - pt) * 0.47, (pb - pt) * 0.22, "#ffffff", "extrabold", "center", a=0.85)
    c.restore()
    c.drawPath(rrect(pl, pt, pr, pb, sw * 0.02), stroke("#c41f1f", sw * 0.008))
    y = pb + sh * 0.075
    text(c, d.get("title", "FIND THIS MAN"), sl + sw / 2, y, sh * 0.042, "#16171b", "extrabold", "center", max_w=sw * 0.9)
    y += sh * 0.04
    text(c, _spaced(d.get("reward_label", "REWARD")), sl + sw / 2, y, sh * 0.017, "#8a8d96", "bold", "center")
    y += sh * 0.06
    _glow_text(c, d.get("reward", "50,000"), sl + sw / 2, y, sh * 0.058, d.get("reward_color", "#e09a1a"), "extrabold",
               "center", max_w=sw * 0.85, glow=0.25)
    y += sh * 0.03
    for ln in (d.get("lines") or ["Last seen: ZONE C", "Black jacket, glasses"])[:3]:
        y += sh * 0.032
        text(c, ln, sl + sw / 2, y, sh * 0.02, "#4a4d56", "semibold", "center", max_w=sw * 0.85)
    bt, bb = sb - sh * 0.135, sb - sh * 0.07
    c.drawPath(rrect(sl + sw * 0.1, bt + sh * 0.008, sr - sw * 0.1, bb + sh * 0.008, (bb - bt) / 2), fill("#7a0f0f"))
    c.drawPath(rrect(sl + sw * 0.1, bt, sr - sw * 0.1, bb, (bb - bt) / 2), fill("#e02a2a"))
    text(c, _spaced(d.get("button", "REPORT")), sl + sw / 2, (bt + bb) / 2 + sh * 0.009, sh * 0.026, "#ffffff",
         "extrabold", "center")
    c.drawPath(rrect(sl + sw * 0.34, sb - sh * 0.022, sr - sw * 0.34, sb - sh * 0.015, sh * 0.004), fill("#1a1b20", 0.8))


def _screen_live(c, sl, st, sr, sb, d: dict) -> None:
    """Live-stream screen: night video (bokeh + figure), LIVE tag + viewers, comment bubbles, floating hearts."""
    sw, sh = sr - sl, sb - st
    c.drawRect(_R(sl, st, sr, sb), _lin((sl, st), (sl, sb), ["#0c1030", "#2a1f48", "#120c1c"]))
    rng = random.Random(int(d.get("seed", 3)))
    for _ in range(26):
        r = rng.uniform(sw * 0.03, sw * 0.09)
        c.drawCircle(rng.uniform(sl, sr), rng.uniform(st, st + sh * 0.6), r,
                     _blurred(rng.choice(["#ffd27a", "#ff6a8a", "#6ad0ff", "#ffffff"]), rng.uniform(0.2, 0.5), r * 0.25))
    # figure (hooded, chest-up), rim-lit
    fx, fy = sl + sw * 0.5, st + sh * 0.5
    body = rrect(fx - sw * 0.36, fy + sh * 0.02, fx + sw * 0.36, sb + sh * 0.1, sw * 0.2)
    c.drawPath(body, fill("#141626"))
    c.drawPath(oval(fx, fy - sh * 0.06, sw * 0.17, sh * 0.095), fill("#141626"))
    c.drawPath(oval(fx, fy - sh * 0.04, sw * 0.11, sh * 0.07), fill("#2a2230"))
    c.drawPath(oval(fx, fy - sh * 0.06, sw * 0.17, sh * 0.095), stroke("#6ad0ff", sw * 0.008, 0.6))
    c.drawRect(_R(sl, st, sr, st + sh * 0.16), _lin((0, st), (0, st + sh * 0.16), [("#000000", 0.55), ("#000000", 0.0)]))
    c.drawRect(_R(sl, sb - sh * 0.45, sr, sb), _lin((0, sb - sh * 0.45), (0, sb), [("#000000", 0.0), ("#000000", 0.7)]))
    _status_bar(c, sl, st + sh * 0.012, sr, sh * 0.045, d.get("time", "21:12"))
    # header: avatar + handle + LIVE + viewers
    ar = sh * 0.022
    ax, ay = sl + sw * 0.1, st + sh * 0.09
    c.drawCircle(ax, ay, ar, fill("#e8833a"))
    handle = nfc(str(d.get("handle", "@night_cam")))
    text(c, handle[1:2].upper() if handle.startswith("@") else handle[:1].upper(), ax, ay + ar * 0.4, ar * 1.1, "#ffffff",
         "bold", "center")
    text(c, handle, ax + ar * 1.5, ay + ar * 0.35, sh * 0.019, "#ffffff", "bold", max_w=sw * 0.35)
    lx = sr - sw * 0.06
    vw = _pill_text(c, d.get("viewers", "12.4K"), lx, ay, sh * 0.014, "#000000", align="right", a=0.55)
    _icon(c, "eye", lx - vw - sh * 0.004, ay, sh * 0.009, "#ffffff")
    _pill_text(c, d.get("live_label", "LIVE"), lx - vw - sh * 0.022, ay, sh * 0.016, "#ff2a4a", align="right")
    # comments
    comments = d.get("comments") or [["J.P.", "where is this?"], ["S.K.", "is this real??"], ["T.N.", "look behind him"]]
    f = font(sh * 0.017, "semibold")
    y = sb - sh * 0.11 - len(comments[:4]) * sh * 0.058
    for who, msg in comments[:4]:
        tw = min(sw * 0.62, f.measureText(nfc(str(msg))))
        c.drawPath(rrect(sl + sw * 0.04, y, sl + sw * 0.17 + tw + sw * 0.04, y + sh * 0.05, sh * 0.02), fill("#000000", 0.38))
        c.drawCircle(sl + sw * 0.095, y + sh * 0.025, sh * 0.015, fill(["#3a78c2", "#c74a9a", "#4fa35a", "#e8833a"][sum(map(ord, str(who))) % 4]))
        text(c, str(who)[:1], sl + sw * 0.095, y + sh * 0.031, sh * 0.016, "#ffffff", "bold", "center")
        text(c, who, sl + sw * 0.15, y + sh * 0.02, sh * 0.013, "#cfd3dc", "bold")
        text(c, msg, sl + sw * 0.15, y + sh * 0.04, sh * 0.017, "#ffffff", "semibold", max_w=sw * 0.62)
        y += sh * 0.058
    # hearts
    hr = random.Random(9)
    for k in range(int(d.get("hearts", 9))):
        hx = sr - sw * 0.1 + hr.uniform(-sw * 0.05, sw * 0.04)
        hy = sb - sh * 0.13 - k * sh * 0.045 - hr.uniform(0, sh * 0.02)
        _icon(c, "heart", hx, hy, sh * hr.uniform(0.012, 0.022), hr.choice(["#ff3b5a", "#ff7aa8", "#ffb04a", "#ff4f7a"]),
              a=max(0.2, 1 - k * 0.09))
    # input bar
    it, ib = sb - sh * 0.085, sb - sh * 0.04
    c.drawPath(rrect(sl + sw * 0.04, it, sr - sw * 0.3, ib, (ib - it) / 2), fill("#ffffff", 0.16))
    text(c, d.get("placeholder", "Add a comment..."), sl + sw * 0.08, (it + ib) / 2 + sh * 0.006, sh * 0.016, "#ffffff",
         "regular", a=0.7)
    _icon(c, "heart", sr - sw * 0.2, (it + ib) / 2, sh * 0.016, "#ff3b5a")
    _icon(c, "share", sr - sw * 0.09, (it + ib) / 2, sh * 0.013, "#ffffff")


def _screen_ai(c, sl, st, sr, sb, d: dict) -> None:
    """Assistant screen: big glowing ring, 'speaking...' caption, waveform bars, mic + close buttons."""
    sw, sh = sr - sl, sb - st
    c.drawRect(_R(sl, st, sr, sb), _lin((sl, st), (sl, sb), ["#090b1c", "#14102c", "#050509"]))
    _status_bar(c, sl, st + sh * 0.012, sr, sh * 0.045, d.get("time", "21:12"))
    text(c, _spaced(d.get("app_name", "ASSISTANT")), sl + sw / 2, st + sh * 0.1, sh * 0.017, "#9aa6d8", "bold", "center")
    cx, cy = sl + sw / 2, st + sh * 0.36
    _ring(c, cx, cy, sw * 0.3, glow=1.3)
    _ring(c, cx, cy, sw * 0.2, w=sw * 0.012, glow=0.4, ticks=False)
    c.drawCircle(cx, cy, sw * 0.05, _blurred("#ffffff", 0.7, sw * 0.02))
    _glow_text(c, d.get("caption", "speaking..."), cx, st + sh * 0.6, sh * 0.032, "#e6e9ff", "semibold", "center",
               max_w=sw * 0.8, glow=0.4)
    sub = d.get("subcaption", "")
    if sub:
        for i, ln in enumerate(wrap_text(sub, font(sh * 0.018, "regular"), sw * 0.8)[:3]):
            text(c, ln, cx, st + sh * (0.645 + i * 0.026), sh * 0.018, "#9aa6d8", "regular", "center")
    rng = random.Random(4)
    n = 21
    for k in range(n):
        x = cx + (k - n // 2) * sw * 0.035
        h = sh * (0.012 + 0.05 * abs(math.sin(k * 0.7)) * rng.uniform(0.5, 1.0) * (1 - abs(k - n // 2) / (n * 0.6)))
        col = RING_COLS[k * (len(RING_COLS) - 1) // n]
        c.drawPath(rrect(x - sw * 0.009, st + sh * 0.76 - h, x + sw * 0.009, st + sh * 0.76 + h, sw * 0.009), fill(col, 0.9))
    for k, (x, col) in enumerate(((0.3, "#2a2c3a"), (0.7, "#e5413a"))):
        c.drawCircle(sl + sw * x, sb - sh * 0.1, sw * 0.075, fill(col))
        if k == 0:
            c.drawPath(rrect(sl + sw * x - sw * 0.018, sb - sh * 0.118, sl + sw * x + sw * 0.018, sb - sh * 0.092, sw * 0.018),
                       fill("#ffffff"))
            c.drawArc(_R(sl + sw * x - sw * 0.03, sb - sh * 0.115, sl + sw * x + sw * 0.03, sb - sh * 0.087), 0, 180, False,
                      stroke("#ffffff", sw * 0.006))
        else:
            _icon(c, "x", sl + sw * x, sb - sh * 0.1, sw * 0.05, "#ffffff")


SCREENS = {"countdown": _screen_countdown, "home": _screen_home, "wanted": _screen_wanted, "live": _screen_live,
           "ai": _screen_ai}


def _with(fn, **defaults):
    """Variant wrapper: defaults are used when params do not set the key (catalog params override)."""
    def run(p, size):
        q = dict(defaults)
        q.update(p or {})
        return fn(q, size)
    run.__doc__ = fn.__doc__
    return run


def ins_phone_countdown(p, size):
    """Phone in hand: countdown app (ring, TIME LEFT, red timer, date/place fields, SHARE)."""
    return _phone_in_hand("countdown", p, size)


def ins_phone_home(p, size):
    """Phone in hand: home screen with app grid (English labels)."""
    return _phone_in_hand("home", p, size)


def ins_phone_wanted(p, size):
    """Phone in hand: alert screen FIND THIS MAN + REWARD + REPORT."""
    return _phone_in_hand("wanted", p, size)


def ins_phone_live(p, size):
    """Phone in hand: live-stream screen (LIVE, viewers, comments, hearts)."""
    return _phone_in_hand("live", p, size)


def ins_phone_ai_speaking(p, size):
    """Phone in hand: assistant ring 'speaking...'."""
    return _phone_in_hand("ai", p, size)


# =================================================================== AI ring (standalone)
def ins_ai_ring_glow(p, size):
    """Big glowing gradient ring floating in dark space: halo, light rays, orbit particles, optional caption."""
    s, c = _begin(size)
    c.drawRect(_R(0, 0, LW, LH), _rad(LW / 2, LH / 2, LW * 0.7, [p.get("bg0", "#121636"), p.get("bg1", "#020205")]))
    rng = random.Random(int(p.get("seed", 8)))
    for _ in range(220):
        c.drawCircle(rng.uniform(0, LW), rng.uniform(0, LH), rng.uniform(1.5, 5), fill("#cfd6ff", rng.uniform(0.1, 0.6)))
    cx, cy, r = LW / 2, LH * 0.47, float(p.get("radius", 600))
    for k in range(36):
        a = k / 36 * math.tau + rng.uniform(-0.05, 0.05)
        ln = rng.uniform(1.3, 2.4) * r
        p_ = stroke(RING_COLS[k % (len(RING_COLS) - 1)], rng.uniform(6, 18), 0.12)
        p_.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 10))
        c.drawLine(cx + math.cos(a) * r * 1.05, cy + math.sin(a) * r * 1.05, cx + math.cos(a) * ln, cy + math.sin(a) * ln, p_)
    _ring(c, cx, cy, r, glow=1.5)
    _ring(c, cx, cy, r * 0.62, w=r * 0.03, glow=0.35, ticks=False)
    c.drawCircle(cx, cy, r * 0.18, _blurred("#ffffff", 0.55, r * 0.08))
    c.drawCircle(cx, cy, r * 0.07, fill("#ffffff", 0.9))
    for k in range(40):
        a = rng.uniform(0, math.tau)
        rr = r * rng.uniform(1.12, 1.35)
        c.drawCircle(cx + math.cos(a) * rr, cy + math.sin(a) * rr * 0.98, rng.uniform(4, 12),
                     fill(rng.choice(RING_COLS), rng.uniform(0.4, 0.9)))
    # floor reflection
    c.drawPath(oval(cx, LH * 0.93, r * 1.3, 60), _blurred("#7a6aff", 0.35, 40))
    lab = p.get("caption", "")
    if lab:
        _glow_text(c, _spaced(lab), cx, LH * 0.9, 90, "#e6e9ff", "bold", "center", max_w=LW * 0.7, glow=0.4)
    _vignette(c, 0.5)
    return s.makeImageSnapshot()


# =================================================================== repair price board
def _row_icon(c, kind, cx, cy, r, col="#ffffff") -> None:
    w = r * 0.14
    if kind == "screen":
        c.drawPath(rrect(cx - r * 0.5, cy - r * 0.9, cx + r * 0.5, cy + r * 0.9, r * 0.15), stroke(col, w))
        c.drawPath(poly([(cx - r * 0.3, cy - r * 0.5), (cx + r * 0.05, cy - r * 0.05), (cx - r * 0.15, cy + r * 0.2),
                         (cx + r * 0.3, cy + r * 0.6)], close=False), stroke(col, w * 0.7))
    elif kind == "battery":
        c.drawPath(rrect(cx - r * 0.45, cy - r * 0.8, cx + r * 0.45, cy + r * 0.9, r * 0.12), stroke(col, w))
        c.drawRect(_R(cx - r * 0.18, cy - r * 0.98, cx + r * 0.18, cy - r * 0.8), fill(col))
        c.drawRect(_R(cx - r * 0.28, cy + r * 0.15, cx + r * 0.28, cy + r * 0.72), fill(col))
    elif kind == "port":
        c.drawPath(rrect(cx - r * 0.35, cy - r * 0.2, cx + r * 0.35, cy + r * 0.55, r * 0.12), fill(col))
        for dx in (-0.15, 0.15):
            c.drawRect(_R(cx + dx * r - r * 0.05, cy - r * 0.6, cx + dx * r + r * 0.05, cy - r * 0.2), fill(col))
        c.drawLine(cx, cy + r * 0.55, cx, cy + r * 0.95, stroke(col, w))
    elif kind == "data":
        for k in range(3):
            c.drawPath(oval(cx, cy - r * 0.55 + k * r * 0.5, r * 0.7, r * 0.22), stroke(col, w))
        c.drawLine(cx - r * 0.7, cy - r * 0.55, cx - r * 0.7, cy + r * 0.45, stroke(col, w))
        c.drawLine(cx + r * 0.7, cy - r * 0.55, cx + r * 0.7, cy + r * 0.45, stroke(col, w))
    elif kind == "camera":
        c.drawPath(rrect(cx - r * 0.8, cy - r * 0.5, cx + r * 0.8, cy + r * 0.6, r * 0.15), stroke(col, w))
        c.drawCircle(cx, cy + r * 0.05, r * 0.3, stroke(col, w))
    else:  # drop
        c.drawPath(smooth([(cx, cy - r * 0.9), (cx + r * 0.55, cy + r * 0.2), (cx, cy + r * 0.8), (cx - r * 0.55, cy + r * 0.2)]),
                   stroke(col, w))


def ins_repair_price_board(p, size):
    """Shop price board on a mall wall: red header REPAIR PRICES, rows with icons, dotted leaders, yellow prices."""
    s, c = _begin(size)
    wall = p.get("wall", "#dfe6e4")
    c.drawRect(_R(0, 0, LW, LH), _lin((0, 0), (0, LH), [shade(wall, 0.05), shade(wall, -0.15)]))
    for x in range(0, int(LW), 24 * 4):   # pegboard holes at the sides
        for y in range(80, int(LH), 96):
            if x < 520 or x > LW - 520:
                c.drawCircle(x + 40, y, 9, fill(shade(wall, -0.35)))
    l, t, r, b = 620.0, 170.0, 3220.0, 1990.0
    board = rrect(l, t, r, b, 36)
    _shadow(c, board, 50, 30, 0.55)
    c.drawPath(board, fill("#b9bec6"))
    c.drawPath(rrect(l + 26, t + 26, r - 26, b - 26, 22), fill(p.get("board", "#1c2126")))
    c.drawPath(rrect(l + 26, t + 26, r - 26, t + 330, 22), fill(p.get("accent", "#d0302a")))
    c.drawRect(_R(l + 26, t + 300, r - 26, t + 330), fill(p.get("accent", "#d0302a")))
    text(c, p.get("title", "REPAIR PRICES"), (l + r) / 2, t + 235, 150, "#ffffff", "extrabold", "center", max_w=r - l - 300)
    for x, y in ((l + 70, t + 70), (r - 70, t + 70), (l + 70, b - 70), (r - 70, b - 70)):
        c.drawCircle(x, y, 22, fill("#d9dde3"))
        c.drawLine(x - 12, y - 12, x + 12, y + 12, stroke("#7a7f88", 6))
    rows = p.get("rows") or [["SCREEN", "900"], ["BATTERY", "450"], ["CHARGE PORT", "300"], ["DATA RECOVERY", "500"],
                             ["BACK GLASS", "350"], ["WATER DAMAGE", "ASK"]]
    icons = p.get("icons") or ["screen", "battery", "port", "data", "camera", "drop"]
    cur = p.get("currency", "")
    n = max(1, len(rows[:7]))
    y0, y1 = t + 420, b - 230
    step = (y1 - y0) / n
    fl = font(min(96, step * 0.5), "bold")
    for i, row in enumerate(rows[:7]):
        lab, price = str(row[0]), str(row[1])
        yc = y0 + step * (i + 0.5)
        _row_icon(c, icons[i % len(icons)], l + 210, yc, min(70, step * 0.33), "#9ad0ff")
        lw = text(c, lab, l + 320, yc + fl.getSize() * 0.36, fl.getSize(), "#ffffff", "bold", max_w=1300)
        pr = f"{price}{(' ' + cur) if cur and price.replace(',', '').isdigit() else ''}"
        pw = font(fl.getSize() * 1.1, "extrabold").measureText(nfc(pr))
        c.drawLine(l + 360 + lw, yc + 18, r - 220 - pw, yc + 18, _dash("#6a7280", 8, 4, 22))
        text(c, pr, r - 160, yc + fl.getSize() * 0.4, fl.getSize() * 1.1, p.get("price_color", "#f3c94e"), "extrabold", "right")
        if i < n - 1:
            c.drawLine(l + 120, yc + step / 2, r - 120, yc + step / 2, stroke("#ffffff", 3, 0.08))
    foot = p.get("footer", "30-DAY WARRANTY  |  FAST SERVICE")
    if foot:
        text(c, _spaced(foot), (l + r) / 2, b - 110, 52, "#9aa0aa", "bold", "center", max_w=r - l - 300)
    _soft_glow(c, LW / 2, -100, 1600, "#ffffff", 0.25)
    _vignette(c, 0.4)
    return s.makeImageSnapshot()


# =================================================================== billboards
def _billboard_frame(c, l, t, r, b) -> None:
    for x in (l + (r - l) * 0.25, l + (r - l) * 0.75):     # legs
        c.drawRect(_R(x - 50, b, x + 50, LH), fill("#1a1c28"))
        for y in range(int(b + 60), int(LH), 160):
            c.drawLine(x - 50, y, x + 50, y + 120, stroke("#2a2c3a", 10))
    c.drawRect(_R(l - 40, b + 20, r + 40, b + 70), fill("#22242f"))                  # catwalk
    for x in range(int(l - 40), int(r + 40), 60):
        c.drawLine(x, b + 70, x, b + 150, stroke("#22242f", 6))
    c.drawLine(l - 40, b + 150, r + 40, b + 150, stroke("#22242f", 8))
    _shadow(c, rrect(l, t, r, b, 10), 40, 10, 0.6)
    c.drawPath(rrect(l - 26, t - 26, r + 26, b + 26, 16), fill("#2a2d3a"))


def _billboard_lights(c, l, t, r) -> None:
    for k in range(4):
        x = l + (r - l) * (0.14 + k * 0.24)
        c.drawLine(x, t - 26, x, t - 170, stroke("#2a2d3a", 14))
        c.drawPath(rrect(x - 60, t - 200, x + 60, t - 150, 12), fill("#3a3d4a"))
        c.drawPath(oval(x, t - 150, 50, 12), fill("#fff6d8"))
        _cone(c, x, t - 150, 90, 900, 700, "#fff1c8", 0.16)


def ins_billboard_accuracy(p, size):
    """Night roadside billboard: dark panel with a glowing ring and '100% ACCURATE' + small sub line."""
    s, c = _begin(size)
    _city_night(c, 5)
    l, t, r, b = 420.0, 360.0, 3420.0, 1500.0
    _billboard_frame(c, l, t, r, b)
    c.save()
    c.clipRect(_R(l, t, r, b))
    c.drawRect(_R(l, t, r, b), _lin((l, t), (r, b), [p.get("panel0", "#0c1030"), p.get("panel1", "#1d1240")]))
    _ring(c, l + 620, (t + b) / 2, 360, glow=1.3)
    c.drawCircle(l + 620, (t + b) / 2, 60, fill("#ffffff", 0.9))
    tx = l + 1180
    _glow_text(c, p.get("headline", "100%"), tx, t + 560, 420, "#ffffff", "extrabold", max_w=r - tx - 120, glow=0.35)
    text(c, _spaced(p.get("title", "ACCURATE")), tx + 10, t + 800, 150, p.get("title_color", "#35e0ff"), "extrabold",
         max_w=r - tx - 140)
    sub = p.get("sub", "KNOW YOUR TIME")
    if sub:
        text(c, _spaced(sub), tx + 14, t + 960, 70, "#aeb6d6", "bold", max_w=r - tx - 140)
    c.restore()
    _billboard_lights(c, l, t, r)
    _vignette(c, 0.45)
    return s.makeImageSnapshot()


def ins_billboard_years_left(p, size):
    """Tall portrait billboard on a building side at night: silhouette portrait in a ring, big red '43' + YEARS LEFT."""
    s, c = _begin(size)
    _city_night(c, 11, horizon=1700)
    bw = p.get("building", "#2a2c3a")
    c.drawRect(_R(980, 0, 2860, LH), fill(bw))                       # building face
    for y in range(80, int(LH), 220):
        c.drawRect(_R(980, y, 2860, y + 8), fill(shade(bw, -0.2)))
    l, t, r, b = 1340.0, 140.0, 2500.0, 2020.0
    c.drawPath(rrect(l - 30, t - 30, r + 30, b + 30, 14), fill("#15161e"))
    c.save()
    c.clipRect(_R(l, t, r, b))
    c.drawRect(_R(l, t, r, b), _lin((l, t), (l, b), [p.get("panel0", "#ffe8d0"), p.get("panel1", "#f2b8a0")]))
    cx, cy = (l + r) / 2, t + 680
    _ring(c, cx, cy, 430, w=44, cols=RED_RING, glow=0.6, ticks=False)
    # silhouette portrait (head + shoulders)
    col = p.get("silhouette", "#2a2030")
    c.drawPath(rrect(cx - 330, cy + 250, cx + 330, b + 200, 240), fill(col))
    c.drawRect(_R(cx - 80, cy + 120, cx + 80, cy + 300), fill(col))
    c.drawPath(oval(cx, cy - 20, 190, 230), fill(col))
    c.drawRect(_R(l, b - 720, r, b), _lin((0, b - 720), (0, b), [("#1a0c14", 0.0), ("#1a0c14", 0.85)]))
    _glow_text(c, p.get("number", "43"), cx, b - 260, 420, p.get("number_color", "#ff3b3b"), "extrabold", "center",
               max_w=r - l - 120, glow=0.5)
    text(c, _spaced(p.get("title", "YEARS LEFT")), cx, b - 120, 110, "#ffffff", "extrabold", "center", max_w=r - l - 120)
    c.restore()
    for k in range(3):
        x = l + (r - l) * (0.2 + k * 0.3)
        c.drawLine(x, b + 30, x, b + 120, stroke("#3a3d4a", 12))
        c.drawPath(oval(x, b + 40, 46, 12), fill("#fff6d8"))
        _soft_glow(c, x, b, 300, "#fff1c8", 0.25)
    _vignette(c, 0.5)
    return s.makeImageSnapshot()


# =================================================================== queue table screen
_STATUS_COLS = {"IN PROGRESS": "#f0a43a", "PENDING": "#5a6478", "DONE": "#3cb45a", "FAILED": "#e5413a",
                "MATCHED": "#e5413a"}


def ins_queue_table_screen(p, size):
    """Control-room monitor with a QUEUE table: #, NAME (initials), TIME, PLACE (ZONE x), STATUS pills."""
    s, c = _begin(size)
    _bokeh(c, "#1a2030", "#06080c", ["#e5413a", "#3a78c2", "#2fa3a0", "#f0a43a"], n=24, seed=6)
    sl, st, sr, sb = _monitor(c, 300, 120, 3540, 1840)
    c.save()
    c.clipRect(_R(sl, st, sr, sb))
    c.drawRect(_R(sl, st, sr, sb), fill(p.get("screen", "#0d1420")))
    hh = 170
    c.drawRect(_R(sl, st, sr, st + hh), fill("#152236"))
    text(c, _spaced(p.get("title", "QUEUE")), sl + 80, st + 115, 80, "#ffffff", "extrabold")
    text(c, p.get("subtitle", "6 ACTIVE"), sl + 620, st + 112, 56, "#7ad0ff", "bold")
    text(c, p.get("clock", "21:12:50"), sr - 80, st + 112, 64, "#ffffff", "bold", "right")
    cols = p.get("columns") or ["#", "NAME", "TIME", "PLACE", "STATUS"]
    xs = [sl + 80, sl + 330, sl + 1000, sl + 1500, sl + 2220]
    y = st + hh + 110
    for x, h in zip(xs, cols):
        text(c, _spaced(h), x, y, 44, "#7a8499", "bold")
    c.drawLine(sl + 60, y + 34, sr - 60, y + 34, stroke("#2a3a52", 4))
    rows = p.get("rows") or [["01", "J.K.", "09:13", "ZONE A", "IN PROGRESS"], ["02", "M.T.", "10:40", "ZONE C", "PENDING"],
                             ["03", "S.P.", "11:05", "ZONE B", "PENDING"], ["04", "A.N.", "13:22", "ZONE A", "PENDING"],
                             ["05", "R.W.", "15:47", "ZONE D", "PENDING"], ["06", "L.C.", "18:30", "ZONE E", "PENDING"]]
    hi = p.get("highlight", 0)
    rh = min(190.0, (sb - y - 80) / max(1, len(rows[:8])))
    y += 60
    for i, row in enumerate(rows[:8]):
        yc = y + rh * 0.5
        if i == hi:
            c.drawRect(_R(sl + 40, y + 8, sr - 40, y + rh - 8), fill("#e5413a", 0.16))
            c.drawRect(_R(sl + 40, y + 8, sl + 56, y + rh - 8), fill("#e5413a"))
        elif i % 2:
            c.drawRect(_R(sl + 40, y + 8, sr - 40, y + rh - 8), fill("#ffffff", 0.03))
        for k, val in enumerate(row[:4]):
            text(c, val, xs[k], yc + 24, 66 if k == 1 else 60, "#ffffff" if k else "#7a8499", "bold" if k == 1 else "semibold",
                 max_w=(xs[k + 1] - xs[k] - 60))
        st_ = str(row[4]) if len(row) > 4 else "PENDING"
        _pill_text(c, st_, xs[4], yc, 40, _STATUS_COLS.get(st_.upper(), "#5a6478"))
        y += rh
    for yy in range(int(st), int(sb), 8):     # scanlines
        c.drawLine(sl, yy, sr, yy, stroke("#000000", 2, 0.12))
    _glass(c, sl, st, sr, sb, 0.05)
    c.restore()
    _vignette(c, 0.45)
    return s.makeImageSnapshot()


# =================================================================== laptop with list
def _laptop(c, sl, st, sr, sb) -> None:
    """Laptop seen from the front: lid around screen rect + keyboard deck in perspective below."""
    l, t, r, b = sl - 60, st - 60, sr + 60, sb + 70
    _shadow(c, rrect(l, t, r, b, 40), 60, 30, 0.6)
    c.drawPath(rrect(l, t, r, b, 40), fill("#2a2c33"))
    c.drawPath(rrect(l + 8, t + 8, r - 8, b - 8, 34), stroke("#454852", 6))
    c.drawCircle((l + r) / 2, t + 30, 9, fill("#0a0b0e"))
    dl, dr, db = l - 260, r + 260, LH + 40
    deck = poly([(l, b), (r, b), (dr, db), (dl, db)])
    c.drawPath(deck, _lin((0, b), (0, db), ["#9aa0aa", "#c9ced6"]))
    for row in range(5):
        f0 = (row + 0.6) / 6.5
        f1 = (row + 1.3) / 6.5
        y0, y1 = b + (db - b) * f0 * 0.62, b + (db - b) * f1 * 0.62
        xl0, xr0 = l + (dl - l) * f0 * 0.62, r + (dr - r) * f0 * 0.62
        xl1, xr1 = l + (dl - l) * f1 * 0.62, r + (dr - r) * f1 * 0.62
        n = 14
        for k in range(n):
            a0, a1 = (k + 0.08) / n, (k + 0.92) / n
            c.drawPath(poly([(xl0 + (xr0 - xl0) * a0 + 80, y0), (xl0 + (xr0 - xl0) * a1 + 80, y0),
                             (xl1 + (xr1 - xl1) * a1 + 80, y1), (xl1 + (xr1 - xl1) * a0 + 80, y1)]), fill("#2e3038"))
    c.drawPath(poly([((l + r) / 2 - 330, b + (db - b) * 0.72), ((l + r) / 2 + 330, b + (db - b) * 0.72),
                     ((l + r) / 2 + 400, db), ((l + r) / 2 - 400, db)]), fill("#b0b6bf"))


def ins_laptop_list(p, size):
    """Laptop on a dark desk showing a records list (initials, zone, time, status ticks), one row flagged red."""
    s, c = _begin(size)
    _wood_top(c, p.get("table", "#4a3426"))
    c.drawRect(_R(0, 0, LW, LH), fill("#000000", 0.35))
    sl, st, sr, sb = 860.0, 140.0, 2980.0, 1420.0
    _laptop(c, sl, st, sr, sb)
    c.save()
    c.clipRect(_R(sl, st, sr, sb))
    c.drawRect(_R(sl, st, sr, sb), fill("#f4f6f9"))
    c.drawRect(_R(sl, st, sr, st + 110), fill("#e3e7ee"))
    for k, col in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        c.drawCircle(sl + 60 + k * 50, st + 55, 16, fill(col))
    text(c, p.get("title", "RECORDS"), (sl + sr) / 2, st + 72, 52, "#2a2c33", "bold", "center")
    c.drawPath(rrect(sl + 60, st + 150, sl + 900, st + 240, 45), fill("#e3e7ee"))
    text(c, p.get("search", "Search..."), sl + 120, st + 210, 44, "#8a8d96", "regular")
    rows = p.get("rows") or [["J.K.", "ZONE A", "09:13", True], ["M.T.", "ZONE C", "10:40", True],
                             ["S.P.", "ZONE B", "11:05", False], ["A.N.", "ZONE A", "13:22", False],
                             ["R.W.", "ZONE D", "15:47", False], ["L.C.", "ZONE E", "18:30", False],
                             ["D.H.", "ZONE B", "20:05", False]]
    hi = p.get("highlight", 2)
    y = st + 300
    rh = (sb - y - 40) / max(1, len(rows[:9]))
    for i, row in enumerate(rows[:9]):
        if i == hi:
            c.drawRect(_R(sl, y, sr, y + rh), fill("#ffe1de"))
            c.drawRect(_R(sl, y, sl + 14, y + rh), fill("#e5413a"))
        c.drawLine(sl + 60, y + rh, sr - 60, y + rh, stroke("#dfe3ea", 3))
        done = bool(row[3]) if len(row) > 3 else False
        bx, by = sl + 90, y + rh / 2
        c.drawPath(rrect(bx - 26, by - 26, bx + 26, by + 26, 8), fill("#2e7cf6") if done else stroke("#9aa0aa", 5))
        if done:
            _icon(c, "check", bx, by, 24, "#ffffff")
        c.drawCircle(sl + 220, by, rh * 0.3, fill(["#3a78c2", "#c74a9a", "#4fa35a", "#e8833a", "#8a5ac2"][i % 5]))
        text(c, str(row[0])[:1], sl + 220, by + rh * 0.12, rh * 0.32, "#ffffff", "bold", "center")
        text(c, row[0], sl + 320, by + 20, 56, "#1a1c22", "bold")
        text(c, row[1], sl + 900, by + 20, 52, "#4a4d56", "semibold")
        text(c, row[2], sl + 1500, by + 20, 52, "#4a4d56", "semibold")
        tag = "FLAGGED" if i == hi else ("DONE" if done else "OPEN")
        _pill_text(c, tag, sr - 120, by, 34, "#e5413a" if i == hi else ("#3cb45a" if done else "#9aa0aa"), align="right")
        y += rh
    c.restore()
    _glass(c, sl, st, sr, sb, 0.05)
    # mug
    mx, my = 3460.0, 1600.0
    c.drawPath(oval(mx + 30, my + 300, 240, 50), _blurred("#000000", 0.5, 30))
    c.drawPath(rrect(mx - 200, my - 80, mx + 200, my + 300, 50), fill(p.get("mug", "#d8d2c4")))
    c.drawPath(oval(mx, my - 80, 200, 50), fill(shade(p.get("mug", "#d8d2c4"), -0.15)))
    c.drawPath(oval(mx, my - 76, 170, 38), fill("#3a2416"))
    c.drawArc(_R(mx + 160, my, mx + 320, my + 200), -90, 180, False, stroke(p.get("mug", "#d8d2c4"), 34))
    _vignette(c, 0.5)
    return s.makeImageSnapshot()


# =================================================================== file upload dialog
def _zip_icon(c, x, y, w, h) -> None:
    c.drawPath(poly([(x, y), (x + w * 0.7, y), (x + w, y + w * 0.3), (x + w, y + h), (x, y + h)]), fill("#f0b43a"))
    c.drawPath(poly([(x + w * 0.7, y), (x + w, y + w * 0.3), (x + w * 0.7, y + w * 0.3)]), fill("#c88a1a"))
    for k in range(7):
        yy = y + 30 + k * (h * 0.06)
        c.drawRect(_R(x + w * 0.42 + (12 if k % 2 else -12), yy, x + w * 0.42 + (36 if k % 2 else 12), yy + h * 0.035),
                   fill("#5a4010"))
    c.drawPath(rrect(x + w * 0.3, y + h * 0.55, x + w * 0.62, y + h * 0.75, 10), fill("#5a4010"))
    text(c, "ZIP", x + w / 2, y + h * 0.92, w * 0.22, "#5a4010", "extrabold", "center")


def ins_upload_dialog(p, size):
    """Screen close-up: UPLOAD FILE dialog over a blurred desktop: zip icon, file name + size, progress bar, buttons."""
    s, c = _begin(size)
    c.drawRect(_R(0, 0, LW, LH), _lin((0, 0), (LW, LH), ["#1d3a6a", "#3a2a6a", "#14182a"]))
    rng = random.Random(3)
    for _ in range(6):   # blurred windows behind
        x, y = rng.uniform(0, LW - 900), rng.uniform(0, LH - 600)
        c.drawPath(rrect(x, y, x + rng.uniform(700, 1300), y + rng.uniform(400, 800), 24), _blurred("#e9edf3", 0.35, 30))
    c.drawRect(_R(0, LH - 110, LW, LH), fill("#0c0e16", 0.85))
    for k in range(7):
        c.drawPath(rrect(1500 + k * 120, LH - 92, 1580 + k * 120, LH - 18, 18), fill(["#2e7cf6", "#3cb45a", "#e8833a",
                                                                                     "#8a5ac2", "#e5413a", "#2fa3a0", "#f3c94e"][k], 0.8))
    l, t, r, b = 760.0, 340.0, 3080.0, 1740.0
    dlg = rrect(l, t, r, b, 36)
    _shadow(c, dlg, 70, 40, 0.65)
    c.drawPath(dlg, fill("#fbfcfe"))
    c.save()
    c.clipPath(dlg, skia.ClipOp.kIntersect, True)
    c.drawRect(_R(l, t, r, t + 170), fill("#eef1f6"))
    c.restore()
    text(c, _spaced(p.get("title", "UPLOAD FILE")), l + 90, t + 112, 64, "#1a1c22", "extrabold")
    _icon(c, "x", r - 100, t + 88, 44, "#5a5d66")
    _zip_icon(c, l + 120, t + 300, 300, 400)
    text(c, p.get("file_name", "records.zip"), l + 520, t + 420, 110, "#1a1c22", "extrabold", max_w=r - l - 640)
    text(c, p.get("file_size", "4.7 GB"), l + 520, t + 530, 70, "#6a6d76", "semibold")
    text(c, p.get("destination", "To: SECURE DRIVE"), l + 520, t + 630, 56, "#8a8d96", "regular", max_w=r - l - 640)
    prog = max(0.0, min(1.0, float(p.get("progress", 0.67))))
    bt = t + 820
    c.drawPath(rrect(l + 120, bt, r - 120, bt + 70, 35), fill("#e3e7ee"))
    if prog > 0:
        c.drawPath(rrect(l + 120, bt, l + 120 + (r - l - 240) * prog, bt + 70, 35),
                   _lin((l, 0), (r, 0), [p.get("bar0", "#2e7cf6"), p.get("bar1", "#35e0ff")]))
        for k in range(int((r - l - 240) * prog / 80)):   # stripes
            x = l + 140 + k * 80
            c.drawLine(x, bt + 66, x + 40, bt + 4, stroke("#ffffff", 14, 0.18))
    status = p.get("status") or f"Uploading... {int(round(prog * 100))}%"
    text(c, status, l + 120, bt + 190, 66, "#1a1c22", "bold")
    text(c, p.get("eta", "about 2 min left"), r - 120, bt + 190, 56, "#6a6d76", "regular", "right")
    by = b - 230
    c.drawPath(rrect(r - 1100, by, r - 640, by + 130, 65), stroke("#9aa0aa", 6))
    text(c, _spaced(p.get("cancel", "CANCEL")), r - 870, by + 88, 52, "#4a4d56", "bold", "center")
    c.drawPath(rrect(r - 580, by, r - 120, by + 130, 65), fill("#2e7cf6"))
    text(c, _spaced(p.get("ok", "HIDE")), r - 350, by + 88, 52, "#ffffff", "bold", "center")
    # cursor
    cx, cy = r - 820, by + 100
    cur = poly([(cx, cy), (cx, cy + 150), (cx + 38, cy + 112), (cx + 70, cy + 180), (cx + 96, cy + 168), (cx + 64, cy + 102),
                (cx + 112, cy + 100)])
    c.drawPath(cur, fill("#ffffff"))
    c.drawPath(cur, stroke("#111216", 8))
    # bezel edge + glare
    c.drawRect(_R(0, 0, LW, LH), stroke("#08090c", 60))
    _glass(c, 0, 0, LW, LH, 0.04)
    _vignette(c, 0.35)
    return s.makeImageSnapshot()


# =================================================================== staff badge on lanyard
def ins_staff_badge_lanyard(p, size):
    """ID badge in a clear holder on a lanyard against a navy uniform: header, photo silhouette, role band, ID,
    chip, barcode."""
    s, c = _begin(size)
    cloth = p.get("uniform", "#1f2a44")
    c.drawRect(_R(0, 0, LW, LH), _rad(LW * 0.5, LH * 0.4, LW * 0.7, [shade(cloth, 0.12), shade(cloth, -0.35)]))
    for y in range(0, int(LH), 14):     # twill weave
        c.drawLine(0, y, LW, y + 60, stroke(shade(cloth, -0.18), 3, 0.25))
    c.drawLine(3200, 0, 3240, LH, stroke(shade(cloth, -0.3), 12))   # placket
    for y in (300, 900, 1500):
        c.drawCircle(3260, y, 34, fill(shade(cloth, 0.2)))
        c.drawCircle(3260, y, 34, stroke(shade(cloth, -0.4), 5))
    lan = p.get("lanyard", "#1f5fc0")
    cx, top = 1920.0, 560.0
    for side in (-1, 1):
        strap = poly([(cx + side * 520, -40), (cx + side * 760, -40), (cx + side * 90, top), (cx + side * 20, top)])
        c.drawPath(strap, fill(shade(lan, -0.1 if side < 0 else 0.0)))
        for k in range(14):
            u = (k + 0.5) / 14
            x = cx + side * (640 * (1 - u) + 55 * u)
            y = -40 + (top + 40) * u
            c.drawCircle(x, y, 10, fill("#ffffff", 0.6))
    c.drawPath(rrect(cx - 80, top - 40, cx + 80, top + 60, 20), fill("#c9ced6"))   # clip
    c.drawPath(rrect(cx - 40, top + 40, cx + 40, top + 170, 18), stroke("#c9ced6", 18))
    c.save()
    c.rotate(float(p.get("angle", 4)), cx, 1300)
    hl, ht, hr, hb = 1400.0, 640.0, 2440.0, 2100.0
    c.drawPath(rrect(hl, ht, hr, hb, 40), _blurred("#000000", 0.5, 40))
    c.drawPath(rrect(hl, ht, hr, hb, 40), fill("#e9f1f6", 0.35))
    c.drawPath(rrect(cx - 110, ht + 50, cx + 110, ht + 100, 25), fill(shade(cloth, -0.2)))
    l, t, r, b = hl + 50, ht + 150, hr - 50, hb - 50
    c.drawPath(rrect(l, t, r, b, 24), fill("#f8f8f6"))
    c.save()
    c.clipPath(rrect(l, t, r, b, 24), skia.ClipOp.kIntersect, True)
    c.drawRect(_R(l, t, r, t + 230), fill(p.get("header_color", "#1f3f8a")))
    c.drawPath(poly([(l + 70, t + 60), (l + 170, t + 60), (l + 120, t + 115)]), fill("#7ad0ff"))
    c.drawPath(poly([(l + 70, t + 170), (l + 170, t + 170), (l + 120, t + 115)]), fill("#7ad0ff", 0.6))
    text(c, p.get("org", "DATA CENTER"), l + 210, t + 150, 92, "#ffffff", "extrabold", max_w=r - l - 260)
    c.restore()
    pl, pt = l + 70, t + 300
    _silhouette(c, pl, pt, pl + 360, pt + 450, "#5a6478")
    c.drawRect(_R(pl, pt, pl + 360, pt + 450), stroke("#c9ced6", 6))
    tx = pl + 420
    text(c, _spaced(p.get("name_label", "NAME")), tx, pt + 50, 34, "#8a8d96", "bold")
    text(c, p.get("name", "S. K."), tx, pt + 140, 84, "#1a1c22", "extrabold", max_w=r - tx - 50)
    text(c, _spaced(p.get("id_label", "ID")), tx, pt + 240, 34, "#8a8d96", "bold")
    text(c, p.get("id", "ID 0417"), tx, pt + 320, 72, "#1a1c22", "bold", max_w=r - tx - 50)
    # chip
    gx, gy = tx, pt + 360
    c.drawPath(rrect(gx, gy, gx + 150, gy + 115, 18), _lin((gx, gy), (gx + 150, gy + 115), ["#f3d27a", "#c8962a"]))
    for k in (0.33, 0.66):
        c.drawLine(gx + 150 * k, gy + 8, gx + 150 * k, gy + 107, stroke("#9a6e1a", 4))
    c.drawLine(gx + 8, gy + 57, gx + 142, gy + 57, stroke("#9a6e1a", 4))
    ry = pt + 520
    c.drawRect(_R(l, ry, r, ry + 140), fill(p.get("role_color", "#d0302a")))
    text(c, p.get("role", "SECURITY OFFICER"), (l + r) / 2, ry + 98, 74, "#ffffff", "extrabold", "center", max_w=r - l - 100)
    rng = random.Random(int(p.get("seed", 417)))
    x = l + 90
    while x < r - 90:   # barcode
        w = rng.choice([6, 6, 10, 14])
        c.drawRect(_R(x, ry + 210, x + w, ry + 400), fill("#111216"))
        x += w + rng.choice([6, 8, 12])
    text(c, p.get("barcode_text", "0417 2291 0063"), (l + r) / 2, ry + 470, 44, "#4a4d56", "semibold", "center")
    c.drawPath(poly([(hl, ht + 500), (hl + 400, ht), (hl + 560, ht), (hl, ht + 760)]), fill("#ffffff", 0.18))
    c.drawPath(rrect(hl, ht, hr, hb, 40), stroke("#ffffff", 6, 0.5))
    c.restore()
    _vignette(c, 0.5)
    return s.makeImageSnapshot()


# =================================================================== wind-up wristwatch
def ins_wristwatch_windup(p, size):
    """Close-up of an analog wind-up wristwatch on a wrist: steel case, cream dial, 'AUTOMATIC', date window,
    red seconds hand, leather strap."""
    s, c = _begin(size)
    _bokeh(c, "#3a2a20", "#0e0a08", ["#ffd27a", "#f0a050", "#fff1c8"], n=22, seed=8)
    skin, sleeve = p.get("skin", "#e9b994"), p.get("sleeve_color", "#4a6a9a")
    arm = capsule(-200, 1180, LW + 300, 1060, 760, 700)
    c.drawPath(arm, fill(skin))
    c.drawPath(capsule(-200, 1180, LW + 300, 1060, 760, 700), stroke(shade(skin, -0.25), 8, 0.5))
    c.drawPath(capsule(-200, 980, LW + 300, 870, 120, 100), fill(shade(skin, 0.12), 0.35))
    c.drawPath(rrect(-100, 600, 700, 1800, 120), fill(sleeve))                          # cuff
    c.drawRect(_R(560, 600, 700, 1800), fill(shade(sleeve, -0.2)))
    cx, cy, R = 1980.0, 1110.0, 560.0
    strap = p.get("strap", "#6a3a1e")
    for sgn in (-1, 1):
        sp = poly([(cx - 330, cy + sgn * 420), (cx + 330, cy + sgn * 420), (cx + 300, cy + sgn * 1300),
                   (cx - 300, cy + sgn * 1300)])
        c.drawPath(sp, _lin((cx - 330, 0), (cx + 330, 0), [shade(strap, -0.2), strap, shade(strap, -0.25)]))
        for k in range(1, 6):
            y = cy + sgn * (440 + k * 160)
            c.drawLine(cx - 290, y, cx + 290, y, _dash(shade(strap, 0.3), 6, 18, 14, 0.7))
        if sgn > 0:
            for k in range(3):
                c.drawPath(oval(cx, cy + 900 + k * 120, 30, 20), fill(shade(strap, -0.45)))
    for sgn in (-1, 1):   # lugs
        c.drawPath(rrect(cx - 360, cy + sgn * 470 - 90, cx - 230, cy + sgn * 470 + 90, 40), fill("#b9bec6"))
        c.drawPath(rrect(cx + 230, cy + sgn * 470 - 90, cx + 360, cy + sgn * 470 + 90, 40), fill("#b9bec6"))
    c.drawCircle(cx + 30, cy + 40, R + 60, _blurred("#000000", 0.5, 40))
    c.drawPath(rrect(cx + R - 10, cy - 70, cx + R + 110, cy + 70, 24), fill("#c9ced6"))      # crown
    for k in range(6):
        c.drawLine(cx + R + 10 + k * 18, cy - 62, cx + R + 10 + k * 18, cy + 62, stroke("#8a8f9a", 5))
    c.drawCircle(cx, cy, R + 40, _rad(cx - R * 0.4, cy - R * 0.4, R * 1.8, ["#f4f6f9", "#b9bec6", "#6a707a"]))
    c.drawCircle(cx, cy, R - 8, fill("#7a808a"))
    dial = p.get("dial", "#f3ecdc")
    c.drawCircle(cx, cy, R - 30, _rad(cx, cy - R * 0.2, R * 1.1, [shade(dial, 0.1), dial, shade(dial, -0.12)]))
    for k in range(60):
        a = k / 60 * math.tau - math.pi / 2
        r0 = R - (100 if k % 5 == 0 else 70)
        c.drawLine(cx + math.cos(a) * r0, cy + math.sin(a) * r0, cx + math.cos(a) * (R - 50), cy + math.sin(a) * (R - 50),
                   stroke("#2a2c33", 16 if k % 5 == 0 else 5))
    for k in (0,):   # double index at 12
        c.drawLine(cx - 22, cy - R + 50, cx - 22, cy - R + 150, stroke("#2a2c33", 18))
        c.drawLine(cx + 22, cy - R + 50, cx + 22, cy - R + 150, stroke("#2a2c33", 18))
    lab = p.get("label", "AUTOMATIC")
    if lab:
        text(c, _spaced(lab), cx, cy + R * 0.42, 46, "#5a4a3a", "bold", "center", max_w=R)
    dx = cx + R * 0.55
    c.drawPath(rrect(dx - 60, cy - 42, dx + 60, cy + 42, 8), fill("#ffffff"))
    c.drawPath(rrect(dx - 60, cy - 42, dx + 60, cy + 42, 8), stroke("#8a8f9a", 6))
    text(c, str(p.get("date", "17")), dx, cy + 24, 64, "#1a1c22", "bold", "center")
    hh, mm, ss = float(p.get("hour", 9)), float(p.get("minute", 13)), float(p.get("second", 40))
    ha = math.radians((hh % 12 + mm / 60) * 30 - 90)
    ma = math.radians((mm + ss / 60) * 6 - 90)
    sa = math.radians(ss * 6 - 90)

    def hand(a, ln, w, col, alpha=1.0):
        tip = (cx + math.cos(a) * ln, cy + math.sin(a) * ln)
        nx, ny = -math.sin(a) * w, math.cos(a) * w
        c.drawPath(poly([(cx - math.cos(a) * 60 + nx * 0.5, cy - math.sin(a) * 60 + ny * 0.5), (cx + nx, cy + ny), tip,
                         (cx - nx, cy - ny), (cx - math.cos(a) * 60 - nx * 0.5, cy - math.sin(a) * 60 - ny * 0.5)]),
                   fill(col, alpha))
    c.save()
    c.translate(10, 16)
    hand(ha, R * 0.55, 34, "#000000", 0.3)
    hand(ma, R * 0.82, 24, "#000000", 0.3)
    c.restore()
    hand(ha, R * 0.55, 34, "#1f2a44")
    hand(ma, R * 0.82, 24, "#1f2a44")
    c.drawLine(cx - math.cos(sa) * 120, cy - math.sin(sa) * 120, cx + math.cos(sa) * (R - 70), cy + math.sin(sa) * (R - 70),
               stroke("#d0302a", 9))
    c.drawCircle(cx, cy, 30, fill("#d0302a"))
    c.drawCircle(cx, cy, 12, fill("#c9ced6"))
    c.drawArc(_R(cx - R + 70, cy - R + 70, cx + R - 70, cy + R - 70), 200, 70, False, stroke("#ffffff", 40, 0.25))
    _vignette(c, 0.45)
    return s.makeImageSnapshot()


# =================================================================== boat-noodle bowl
def ins_boat_noodle_bowl(p, size):
    """Small patterned noodle bowl (3/4 view) on a steel table: dark broth, rice noodles, meatballs, beef slices,
    greens, sprouts, chili oil; chopsticks resting across the rim; spoon."""
    s, c = _begin(size)
    c.drawRect(_R(0, 0, LW, LH), _lin((0, 0), (0, LH), ["#8a8f96", "#c9ced4", "#9aa0a8"]))
    rng = random.Random(5)
    for _ in range(260):     # brushed steel
        y = rng.uniform(0, LH)
        c.drawLine(0, y, LW, y + rng.uniform(-10, 10), stroke("#ffffff", rng.uniform(1, 3), 0.12))
    _bokeh_spots = [(400, 300, "#ff6a5a"), (3500, 260, "#ffd27a"), (3300, 1900, "#7ad0ff")]
    for x, y, col in _bokeh_spots:
        c.drawCircle(x, y, 260, _blurred(col, 0.2, 60))
    cx, cy, rx, ry = 1880.0, 900.0, 900.0, 400.0
    bowl = p.get("bowl", "#f4f1ea")
    band = p.get("band", "#2f5fa8")
    c.drawPath(oval(cx + 40, cy + 760, rx * 0.95, 150), _blurred("#000000", 0.45, 50))
    body = skia.Path()
    body.moveTo(cx - rx, cy)
    body.cubicTo(cx - rx * 0.95, cy + 650, cx - rx * 0.45, cy + 820, cx, cy + 820)
    body.cubicTo(cx + rx * 0.45, cy + 820, cx + rx * 0.95, cy + 650, cx + rx, cy)
    body.close()
    c.drawPath(body, _lin((cx - rx, 0), (cx + rx, 0), [shade(bowl, -0.2), bowl, shade(bowl, 0.05), shade(bowl, -0.25)],
                          [0, 0.4, 0.6, 1]))
    c.save()
    c.clipPath(body, skia.ClipOp.kIntersect, True)
    c.drawPath(oval(cx, cy + 240, rx * 1.02, ry * 0.9), stroke(band, 90))
    for k in range(18):   # dot band
        a = math.pi * (k + 0.5) / 18
        c.drawCircle(cx - math.cos(a) * rx * 0.97, cy + 430 + math.sin(a) * ry * 0.8, 26, fill(band))
    c.restore()
    c.drawPath(oval(cx, cy, rx, ry), fill(shade(bowl, -0.05)))
    c.drawPath(oval(cx, cy, rx, ry), stroke(band, 22))
    c.drawPath(oval(cx, cy + 8, rx - 50, ry - 30), _rad(cx, cy - 60, rx, [p.get("broth", "#7a3a1e"), "#3a160a"]))
    c.save()
    c.clipPath(oval(cx, cy + 8, rx - 50, ry - 30), skia.ClipOp.kIntersect, True)
    for _ in range(60):      # noodles
        x0 = rng.uniform(cx - rx * 0.8, cx + rx * 0.6)
        y0 = rng.uniform(cy - ry * 0.6, cy + ry * 0.6)
        pts = [(x0 + k * 90, y0 + math.sin(k * 1.3 + x0) * 30) for k in range(5)]
        c.drawPath(smooth(pts, close=False), stroke("#f3e6c4", 12, 0.85))
    for _ in range(9):       # chili oil
        c.drawPath(oval(rng.uniform(cx - rx * 0.7, cx + rx * 0.7), rng.uniform(cy - ry * 0.6, cy + ry * 0.6),
                        rng.uniform(30, 70), rng.uniform(10, 24)), fill("#e04a1a", 0.6))
    for (x, y, ang) in ((cx - 380, cy - 60, 20), (cx - 220, cy + 120, -10), (cx + 60, cy - 160, 35)):   # beef slices
        c.save()
        c.rotate(ang, x, y)
        c.drawPath(oval(x, y, 190, 80), fill("#8a4a3a"))
        c.drawPath(oval(x - 20, y - 10, 150, 50), fill("#a86a58"))
        c.restore()
    for (x, y) in ((cx + 250, cy + 60), (cx + 420, cy - 90), (cx + 120, cy + 190), (cx - 520, cy + 150)):   # meatballs
        c.drawCircle(x, y, 80, _rad(x - 25, y - 25, 110, ["#a8805a", "#6a4a2e"]))
        c.drawCircle(x - 25, y - 30, 18, fill("#ffffff", 0.35))
    for k in range(7):       # greens
        x, y = cx + 300 + k * 50, cy + 200 - k * 50
        c.drawLine(x, y, x + 200, y - 150, stroke("#3a8a3a", 18))
        c.drawPath(oval(x + 200, y - 150, 70, 26), fill("#4aa84a"))
    for k in range(14):      # sprouts
        x, y = rng.uniform(cx - 600, cx + 200), rng.uniform(cy - 260, cy + 80)
        c.drawLine(x, y, x + rng.uniform(-90, 90), y + rng.uniform(60, 120), stroke("#f6f2e0", 12))
    for _ in range(40):      # scallion
        c.drawCircle(rng.uniform(cx - rx * 0.7, cx + rx * 0.7), rng.uniform(cy - ry * 0.7, cy + ry * 0.7), rng.uniform(8, 16),
                     fill("#6ac04a"))
    c.drawPath(oval(cx - 200, cy - 220, 360, 60), fill("#ffffff", 0.1))
    c.restore()
    # spoon
    c.save()
    c.rotate(-24, cx - 640, cy - 120)
    c.drawPath(oval(cx - 640, cy - 120, 150, 95), fill("#f6f4ee"))
    c.drawPath(oval(cx - 640, cy - 110, 120, 70), fill("#5a2810"))
    c.drawPath(rrect(cx - 1180, cy - 150, cx - 760, cy - 90, 30), fill("#f6f4ee"))
    c.restore()
    # chopsticks across the rim
    stick = p.get("chopsticks", "#d8b07a")
    for k, off in enumerate((0, 70)):
        x0, y0, x1, y1 = cx - 300 + off, cy - ry - 80, LW + 200, cy - ry - 380 + off * 0.5
        c.drawLine(x0 + 10, y0 + 30, x1 + 10, y1 + 30, stroke("#000000", 46, 0.25))
        c.drawPath(capsule(x0, y0, x1, y1, 20, 34), fill(shade(stick, -0.05 * k)))
        c.drawLine(x0 + 20, y0 - 6, x1, y1 - 12, stroke(shade(stick, 0.25), 6, 0.7))
    _vignette(c, 0.45)
    return s.makeImageSnapshot()


# =================================================================== glowing trouser pocket
def ins_pocket_glow(p, size):
    """Close-up of a dark trouser front pocket with a phone glowing through the fabric (light leaks from the top)."""
    s, c = _begin(size)
    denim = p.get("fabric", "#232a3a")
    c.drawRect(_R(0, 0, LW, LH), _rad(LW * 0.5, LH * 0.5, LW * 0.7, [shade(denim, 0.08), shade(denim, -0.45)]))
    rng = random.Random(3)
    for y in range(0, int(LH), 10):
        c.drawLine(0, y, LW, y - 80, stroke(shade(denim, rng.uniform(-0.2, 0.15)), 4, 0.35))
    seam = p.get("stitch", "#c88a3a")
    # pocket opening curve + facing
    op = skia.Path()
    op.moveTo(900, -40)
    op.cubicTo(1100, 700, 1800, 1000, 2700, 980)
    op.lineTo(LW + 40, 980)
    c.drawPath(op, stroke(shade(denim, -0.5), 60))
    c.drawPath(op, _dash(seam, 8, 26, 16))
    o2 = skia.Path(op)
    o2.offset(0, 70)
    c.drawPath(o2, _dash(seam, 8, 26, 16))
    c.drawLine(3400, 980, 3400, LH, _dash(seam, 8, 26, 16))     # side seam
    c.drawCircle(1180, 520, 40, fill("#b98a4a"))                  # rivet
    c.drawCircle(1180, 520, 22, fill("#8a5a2a"))
    # phone glow through fabric
    gc = p.get("glow", "#7ad8ff")
    px, py, pw, ph = 2150.0, 1550.0, 560.0, 1000.0
    c.save()
    c.rotate(-12, px, py)
    for k, (grow, a) in enumerate(((260, 0.25), (140, 0.4), (40, 0.65))):
        pnt = _blurred(gc, a, 60 + k * 20)
        pnt.setBlendMode(skia.BlendMode.kScreen)
        c.drawPath(rrect(px - pw / 2 - grow, py - ph / 2 - grow, px + pw / 2 + grow, py + ph / 2 + grow, 80 + grow), pnt)
    c.drawPath(rrect(px - pw / 2, py - ph / 2, px + pw / 2, py + ph / 2, 70), stroke("#ffffff", 10, 0.35))
    c.restore()
    for y in range(0, int(LH), 10):     # weave over the glow
        c.drawLine(1400, y, 3000, y - 30, stroke(denim, 3, 0.18))
    # light leaking from pocket opening
    _soft_glow(c, 2300, 1000, 700, gc, 0.45)
    for k in range(7):
        a = math.radians(-120 + k * 12)
        c.drawLine(2300, 1000, 2300 + math.cos(a) * 900, 1000 + math.sin(a) * 900, _blurred(gc, 0.18, 20))
    _vignette(c, 0.55)
    return s.makeImageSnapshot()


# =================================================================== three CCTV cameras
def _cctv_cam(c, x, y, ang, s, body="#e9ecef", led=True) -> None:
    """Bullet camera on a wall bracket. (x, y) = wall mount; points along +x rotated by ang."""
    c.drawPath(rrect(x - 70 * s, y - 110 * s, x + 70 * s, y + 110 * s, 20 * s), fill(shade(body, -0.25)))
    c.save()
    c.translate(x, y)
    c.rotate(ang)
    c.drawPath(capsule(0, 0, 220 * s, 0, 46 * s, 40 * s), fill(shade(body, -0.35)))
    c.drawCircle(220 * s, 0, 60 * s, fill(shade(body, -0.3)))
    c.drawPath(rrect(180 * s, -150 * s, 760 * s, 120 * s, 60 * s), _lin((0, -150 * s), (0, 120 * s),
                                                                        [shade(body, 0.1), body, shade(body, -0.3)]))
    c.drawPath(rrect(160 * s, -190 * s, 820 * s, -120 * s, 30 * s), fill(shade(body, -0.08)))       # sun hood
    c.drawPath(rrect(740 * s, -125 * s, 800 * s, 105 * s, 20 * s), fill("#16171b"))
    c.drawCircle(770 * s, -10 * s, 80 * s, fill("#08090c"))
    c.drawCircle(770 * s, -10 * s, 50 * s, _rad(750 * s, -30 * s, 60 * s, ["#3a5a8a", "#0a0c14"]))
    c.drawCircle(755 * s, -28 * s, 14 * s, fill("#ffffff", 0.7))
    if led:
        c.drawCircle(700 * s, 70 * s, 14 * s, fill("#ff2a2a"))
        c.drawCircle(700 * s, 70 * s, 40 * s, _blurred("#ff2a2a", 0.6, 14 * s))
    c.restore()


def ins_cctv_cameras_wall(p, size):
    """Three bullet CCTV cameras on a concrete wall at different angles, red LEDs, cable conduit."""
    s, c = _begin(size)
    _concrete(c, p.get("wall", "#6a6c70"))
    c.drawRect(_R(0, 0, LW, LH), _lin((0, 0), (0, LH), [("#0a0c14", 0.2), ("#0a0c14", 0.6)]))
    c.drawPath(rrect(-40, 330, LW + 40, 390, 20), fill("#9a9ca0"))     # conduit
    for x in range(200, int(LW), 600):
        c.drawPath(rrect(x - 30, 315, x + 30, 405, 10), fill("#7a7c80"))
    cams = p.get("cameras") or [[330, 980, 16], [1480, 760, 28], [2640, 1060, 6]]
    for i, (x, y, ang) in enumerate(cams[:5]):
        c.drawLine(x, 390, x, y - 110, stroke("#1a1b20", 14))
        _cctv_cam(c, float(x), float(y), float(ang), 1.0, p.get("body", "#e9ecef"))
    _soft_glow(c, LW / 2, LH + 200, 2200, "#9ab4ff", 0.18)
    _vignette(c, 0.55)
    return s.makeImageSnapshot()


# =================================================================== wig + straw hat in laundry basket
def ins_laundry_basket_disguise(p, size):
    """Blue plastic laundry basket in a laundromat: folded clothes, a long brown wig, a wide straw hat and glasses."""
    s, c = _begin(size)
    _tiles(c, "#d9dcd8", 420)
    c.drawRect(_R(0, 0, LW, 700), fill("#cfd5da"))
    for k in range(4):     # washers behind (blurred)
        x = 300 + k * 900
        c.drawPath(rrect(x, -100, x + 800, 700, 30), _blurred("#eef1f3", 0.95, 18))
        c.drawCircle(x + 400, 330, 250, _blurred("#5a6a7a", 0.8, 18))
        c.drawCircle(x + 400, 330, 180, _blurred("#9ab4c8", 0.8, 18))
    c.drawRect(_R(0, 650, LW, 720), fill("#000000", 0.15))
    bl, bt, br, bb = 820.0, 900.0, 3020.0, 2120.0
    col = p.get("basket", "#2f7ad0")
    c.drawPath(oval((bl + br) / 2, bb, (br - bl) * 0.55, 80), _blurred("#000000", 0.45, 40))
    # contents above rim
    clothes = [("#e9a0b0", 1150, 880, 380), ("#f3e6c4", 1650, 860, 420), ("#7aa0c8", 2250, 870, 400),
               ("#a0c890", 2700, 900, 300)]
    for colr, x, y, r in clothes:
        c.drawPath(oval(x, y, r, r * 0.45), fill(colr))
        c.drawPath(oval(x, y - r * 0.12, r * 0.85, r * 0.22), fill(shade(colr, 0.15)))
    wig = p.get("wig", "#6a3e22")
    wp = smooth([(1250, 700), (1500, 560), (1850, 600), (2000, 780), (1950, 1050), (2100, 1300), (1700, 1250),
                 (1400, 1300), (1300, 1050)])
    c.drawPath(wp, fill(wig))
    rng = random.Random(4)
    for _ in range(40):
        x0, y0 = rng.uniform(1320, 1950), rng.uniform(620, 1100)
        c.drawPath(smooth([(x0, y0), (x0 + rng.uniform(-30, 30), y0 + 120), (x0 + rng.uniform(-40, 40), y0 + 240)],
                          close=False), stroke(shade(wig, rng.uniform(-0.3, 0.25)), 8, 0.8))
    # hat
    hx, hy = 2350.0, 640.0
    straw = p.get("straw", "#e6c77a")
    c.drawPath(oval(hx + 30, hy + 60, 760, 250), _blurred("#000000", 0.35, 30))
    c.drawPath(oval(hx, hy, 760, 260), fill(straw))
    for k in range(1, 9):
        c.drawPath(oval(hx, hy, 760 * k / 9, 260 * k / 9), stroke(shade(straw, -0.18), 5, 0.6))
    for k in range(48):
        a = k / 48 * math.tau
        c.drawLine(hx + math.cos(a) * 300, hy + math.sin(a) * 100, hx + math.cos(a) * 750, hy + math.sin(a) * 255,
                   stroke(shade(straw, 0.15), 3, 0.5))
    crown = skia.Path()
    crown.moveTo(hx - 330, hy)
    crown.cubicTo(hx - 330, hy - 360, hx + 330, hy - 360, hx + 330, hy)
    crown.close()
    c.drawPath(crown, fill(shade(straw, 0.05)))
    c.drawPath(oval(hx, hy - 20, 330, 90), fill(p.get("ribbon", "#8a2a3a")))
    c.drawPath(oval(hx, hy - 60, 330, 80), fill(shade(straw, 0.05)))
    # glasses
    gx, gy = 1600.0, 1240.0
    for dx in (-150, 150):
        c.drawCircle(gx + dx, gy, 120, stroke("#2a2420", 22))
        c.drawCircle(gx + dx, gy, 108, fill("#bfe0ff", 0.25))
    c.drawArc(_R(gx - 50, gy - 40, gx + 50, gy + 20), 200, 140, False, stroke("#2a2420", 18))
    # basket body (in front of contents)
    body = poly([(bl, bt + 200), (br, bt + 200), (br - 150, bb), (bl + 150, bb)])
    c.drawPath(body, _lin((bl, 0), (br, 0), [shade(col, -0.2), col, shade(col, 0.1), shade(col, -0.25)], [0, 0.3, 0.6, 1]))
    c.save()
    c.clipPath(body, skia.ClipOp.kIntersect, True)
    for j in range(5):
        y = bt + 340 + j * 160
        for i in range(12):
            u = (i + 0.5) / 12
            x = bl + 150 * (y - bt - 200) / (bb - bt - 200) + u * ((br - bl) - 300 * (y - bt - 200) / (bb - bt - 200))
            c.drawPath(rrect(x - 50, y, x + 50, y + 100, 26), fill(shade(col, -0.45)))
    c.restore()
    c.drawPath(rrect(bl - 40, bt + 150, br + 40, bt + 300, 40), fill(shade(col, 0.12)))
    c.drawPath(rrect(bl + 200, bt + 190, bl + 520, bt + 260, 30), fill(shade(col, -0.5)))     # handles
    c.drawPath(rrect(br - 520, bt + 190, br - 200, bt + 260, 30), fill(shade(col, -0.5)))
    _vignette(c, 0.4)
    return s.makeImageSnapshot()


# =================================================================== USB stick into a server
def ins_usb_server_plug(p, size):
    """Server front panel close-up (vents, drive bays, blinking LEDs); a hand pushes a USB stick into a port."""
    s, c = _begin(size)
    c.drawRect(_R(0, 0, LW, LH), fill("#15171c"))
    rng = random.Random(6)
    uh = 300.0
    y = -100.0
    k = 0
    while y < LH:
        c.drawPath(rrect(120, y + 10, LW - 120, y + uh - 10, 14), fill("#2a2d34" if k % 2 else "#24272d"))
        for i in range(6):    # drive bays
            x = 260 + i * 260
            c.drawPath(rrect(x, y + 50, x + 220, y + uh - 50, 10), fill("#1a1c21"))
            c.drawRect(_R(x + 20, y + 80, x + 200, y + 100), fill("#3a3d45"))
            c.drawCircle(x + 190, y + uh - 80, 12, fill(rng.choice(["#3cff6a", "#3cff6a", "#ffb03a", "#3cff6a"])))
        for i in range(26):   # vent holes
            for j in range(4):
                c.drawCircle(1950 + i * 60, y + 70 + j * 50, 14, fill("#121418"))
        for i in range(4):
            col = rng.choice(["#3cff6a", "#3a9aff", "#ffb03a"])
            cx_ = 3500 + i * 50
            c.drawCircle(cx_, y + uh / 2, 12, fill(col))
            c.drawCircle(cx_, y + uh / 2, 32, _blurred(col, 0.5, 12))
        y += uh
        k += 1
    # port panel on the unit in the middle
    py = 1040.0
    c.drawPath(rrect(1560, py - 120, 1960, py + 120, 16), fill("#1c1e24"))
    for dy in (-55, 55):
        c.drawPath(rrect(1620, py + dy - 30, 1800, py + dy + 30, 6), fill("#08090b"))
        c.drawRect(_R(1640, py + dy - 22, 1780, py + dy - 4), fill("#2e7cf6"))
    # USB stick plugged into top port (pointing left)
    sx, sy = 1700.0, py - 55
    c.drawPath(rrect(sx, sy - 34, sx + 220, sy + 34, 6), fill("#c9ced6"))
    c.drawPath(rrect(sx + 200, sy - 70, sx + 760, sy + 70, 40), fill(p.get("stick", "#2f5fa8")))
    c.drawPath(rrect(sx + 230, sy - 50, sx + 720, sy - 25, 12), fill("#ffffff", 0.25))
    c.drawCircle(sx + 690, sy + 30, 14, fill("#3cff6a"))
    c.drawCircle(sx + 690, sy + 30, 36, _blurred("#3cff6a", 0.6, 14))
    _soft_glow(c, sx + 100, sy, 300, "#3cff6a", 0.25)
    # hand pinching the stick (from bottom-right)
    ang, sc = -78.0, 1.5
    tx, ty = sx + 600, sy + 10
    hx0, hy0 = hand_tip(0, 0, ang, sc, "pinch")
    _hand(c, tx - hx0, ty - hy0, ang, sc, p.get("sleeve_color", "#2a2d33"), p.get("skin", "#e9b994"), "pinch", "all")
    _vignette(c, 0.5)
    return s.makeImageSnapshot()


# =================================================================== public payphone at dawn
def ins_payphone_public(p, size):
    """Roadside public payphone on a pole at dawn: hood with PHONE sign, handset with coiled cord, keypad, coin slot."""
    s, c = _begin(size)
    c.drawRect(_R(0, 0, LW, LH), _lin((0, 0), (0, 1500), [p.get("sky0", "#3b2f6a"), p.get("sky1", "#c86a9a"),
                                                         p.get("sky2", "#f6b28a")], [0, 0.6, 1]))
    _soft_glow(c, 3000, 1450, 900, "#ffe2a0", 0.55)
    c.drawRect(_R(0, 1400, LW, 1560), fill("#5a3a6a"))     # distant tree line
    rng = random.Random(4)
    for _ in range(40):
        x = rng.uniform(0, LW)
        c.drawCircle(x, 1400, rng.uniform(60, 160), fill("#4a2f5a"))
    c.drawRect(_R(0, 1560, LW, LH), _lin((0, 1560), (0, LH), ["#6a8a4a", "#3a5a2a"]))
    for _ in range(500):
        x, y = rng.uniform(0, LW), rng.uniform(1580, LH)
        c.drawLine(x, y, x + rng.uniform(-10, 10), y - rng.uniform(20, 60), stroke(rng.choice(["#4a6a3a", "#8aa85a"]), 5))
    body = p.get("body", "#2f5fa8")
    cx = 1920.0
    c.drawRect(_R(cx - 50, 1400, cx + 50, LH), fill("#8a8f96"))                               # pole
    c.drawRect(_R(cx - 50, 1400, cx - 20, LH), fill("#ffffff", 0.2))
    l, t, r, b = cx - 520, 260.0, cx + 520, 1460.0
    _shadow(c, rrect(l - 60, t, r + 60, b, 30), 50, 30, 0.5)
    c.drawPath(rrect(l - 80, t - 40, r + 80, t + 180, 30), fill(body))                         # hood
    c.drawPath(rrect(l - 80, t - 40, r + 80, t + 30, 30), fill(shade(body, 0.15)))
    text(c, _spaced(p.get("label", "PHONE")), cx, t + 130, 110, "#ffffff", "extrabold", "center", max_w=r - l)
    c.drawPath(rrect(l, t + 180, r, b, 30), fill(shade(body, -0.1)))                           # body
    c.drawPath(rrect(l + 60, t + 230, r - 60, b - 50, 24), _lin((l, 0), (r, 0), ["#c9ced6", "#eef1f4", "#aab0b8"]))
    # display
    c.drawPath(rrect(cx - 60, t + 290, r - 110, t + 400, 12), fill("#2a3a2a"))
    text(c, p.get("display", "INSERT COIN"), (cx - 60 + r - 110) / 2, t + 365, 44, "#9aff8a", "bold", "center", max_w=r - cx - 80)
    # keypad
    keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"]
    for i, kk in enumerate(keys):
        kx = cx + 20 + (i % 3) * 120
        ky = t + 480 + (i // 3) * 120
        c.drawPath(rrect(kx, ky, kx + 95, ky + 90, 14), fill("#3a3d45"))
        text(c, kk, kx + 47, ky + 64, 52, "#ffffff", "bold", "center")
    # coin slot + return
    c.drawPath(rrect(cx + 90, t + 990, cx + 300, t + 1050, 10), fill("#6a707a"))
    c.drawRect(_R(cx + 120, t + 1012, cx + 270, t + 1028), fill("#111216"))
    c.drawPath(rrect(cx + 60, b - 220, cx + 330, b - 90, 16), fill("#3a3d45"))
    # cradle + handset
    hx = l + 230
    c.drawPath(rrect(hx - 120, t + 300, hx + 120, t + 1100, 50), fill("#24262c"))
    c.drawPath(rrect(hx - 100, t + 260, hx + 100, t + 500, 60), fill("#16171b"))
    c.drawPath(rrect(hx - 70, t + 460, hx + 70, t + 900, 40), fill("#16171b"))
    c.drawPath(rrect(hx - 100, t + 860, hx + 100, t + 1100, 60), fill("#16171b"))
    cord = skia.Path()
    cord.moveTo(hx, t + 1100)
    for k in range(18):
        cord.quadTo(hx + (60 if k % 2 else -60), t + 1130 + k * 18, hx, t + 1140 + k * 18)
    c.drawPath(cord, stroke("#16171b", 14))
    _vignette(c, 0.4)
    return s.makeImageSnapshot()


# =================================================================== old beige sedan (side)
def _wheel(c, x, y, r, hub="#c9ced6") -> None:
    c.drawCircle(x, y, r, fill("#16171b"))
    c.drawCircle(x, y, r * 0.66, fill("#2a2c33"))
    c.drawCircle(x, y, r * 0.58, _rad(x - r * 0.2, y - r * 0.2, r * 0.8, [shade(hub, 0.3), hub, shade(hub, -0.3)]))
    for k in range(8):
        a = k / 8 * math.tau
        c.drawLine(x + math.cos(a) * r * 0.18, y + math.sin(a) * r * 0.18, x + math.cos(a) * r * 0.5, y + math.sin(a) * r * 0.5,
                   stroke(shade(hub, -0.35), r * 0.05))
    c.drawCircle(x, y, r * 0.14, fill(shade(hub, -0.2)))


def _street_bg(c, wall="#b9b0a0") -> None:
    c.drawRect(_R(0, 0, LW, 1500), _lin((0, 0), (0, 1500), [shade(wall, 0.1), shade(wall, -0.1)]))
    for x in range(0, int(LW), 640):     # shutters / shop fronts blurred
        c.drawPath(rrect(x + 60, 300, x + 560, 1500, 10), _blurred(shade(wall, -0.25), 0.7, 14))
        for y in range(330, 1500, 50):
            c.drawLine(x + 70, y, x + 550, y, stroke(shade(wall, -0.35), 4, 0.4))
    c.drawRect(_R(0, 1500, LW, 1620), fill("#9a958c"))       # curb
    c.drawRect(_R(0, 1620, LW, LH), fill("#4a4a4e"))         # road
    c.drawRect(_R(0, 1600, LW, 1630), fill("#6a6862"))


def ins_sedan_old_side(p, size):
    """Old boxy beige four-door sedan in side profile: chrome bumpers, hubcaps, pillars, door seams, faded paint."""
    s, c = _begin(size)
    _street_bg(c, p.get("wall", "#b9b0a0"))
    paint = p.get("paint", "#d9c9a0")
    c.drawPath(oval(1920, 1830, 1600, 70), _blurred("#000000", 0.55, 30))
    body = poly([(330, 1560), (330, 1300), (420, 1240), (1000, 1210), (1300, 900), (2400, 890), (2780, 1180),
                 (3420, 1220), (3520, 1300), (3520, 1560), (3300, 1700), (560, 1700)])
    c.drawPath(body, _lin((0, 890), (0, 1700), [shade(paint, 0.12), paint, shade(paint, -0.22)], [0, 0.45, 1]))
    c.drawPath(body, stroke(shade(paint, -0.4), 6))
    # windows
    win = "#3a4a5a"
    c.drawPath(poly([(1060, 1215), (1330, 950), (1830, 945), (1830, 1215)]), fill(win))
    c.drawPath(poly([(1890, 1215), (1890, 945), (2370, 945), (2700, 1200)]), fill(win))
    for wl in ((1100, 1200, 1500, 960), (1950, 1200, 2300, 960)):
        c.drawLine(wl[0], wl[1], wl[2], wl[3], stroke("#ffffff", 30, 0.12))
    c.drawRect(_R(1830, 940, 1890, 1600), fill(shade(paint, -0.35)))     # B pillar
    c.drawLine(420, 1290, 3480, 1290, stroke("#d9dde3", 16))             # chrome strip
    for x in (1060, 1860, 2700):                                          # door seams
        c.drawLine(x, 1215, x - 10 if x != 2700 else x + 20, 1620, stroke(shade(paint, -0.45), 6))
    for x in (1700, 2520):
        c.drawPath(rrect(x - 90, 1330, x + 30, 1360, 12), fill("#c9ced6"))
    # bumpers + lights
    c.drawPath(rrect(250, 1500, 700, 1590, 30), fill("#c9ced6"))
    c.drawPath(rrect(3180, 1500, 3600, 1590, 30), fill("#c9ced6"))
    c.drawPath(rrect(3440, 1310, 3540, 1420, 20), fill("#fff1c8"))
    c.drawPath(rrect(310, 1310, 400, 1440, 18), fill("#c8352e"))
    c.drawPath(rrect(2620, 1150, 2720, 1215, 14), fill("#2a2c33"))     # mirror
    # wheel arches + wheels
    for x in (1010, 2880):
        c.drawCircle(x, 1640, 300, fill("#1a1b20"))
        _wheel(c, x, 1660, 250, p.get("hubcap", "#c9ced6"))
    rng = random.Random(4)
    for _ in range(18):     # faded paint / rust spots
        c.drawPath(oval(rng.uniform(500, 3300), rng.uniform(1350, 1600), rng.uniform(10, 40), rng.uniform(6, 20)),
                   fill("#8a5a3a", rng.uniform(0.2, 0.5)))
    c.drawLine(1400, 905, 1250, 600, stroke("#2a2c33", 6))                # antenna
    _vignette(c, 0.4)
    return s.makeImageSnapshot()


# =================================================================== motorbike (side)
def ins_motorbike_side(p, size):
    """Generic step-through motorbike in side profile: leg shield, long seat, rear rack, chrome exhaust, kickstand."""
    s, c = _begin(size)
    _street_bg(c, p.get("wall", "#8a8f9a"))
    col = p.get("paint", "#c8352e")
    c.drawPath(oval(1950, 1860, 1100, 60), _blurred("#000000", 0.55, 30))
    fx, rx, wy, wr = 2850.0, 1100.0, 1600.0, 300.0
    # rear swingarm + exhaust
    c.drawLine(rx, wy, 1800, 1430, stroke("#2a2c33", 50))
    c.drawPath(capsule(900, 1450, 1750, 1420, 60, 50), _lin((0, 1380), (0, 1500), ["#f4f6f9", "#9aa0aa", "#6a707a"]))
    # wheels
    _wheel(c, rx, wy, wr, "#9aa0aa")
    _wheel(c, fx, wy, wr, "#9aa0aa")
    # engine
    c.drawPath(rrect(1650, 1300, 2150, 1560, 60), fill("#4a4d56"))
    for k in range(5):
        c.drawLine(1700 + k * 90, 1320, 1700 + k * 90, 1540, stroke("#3a3d45", 14))
    # rear body + seat + rack
    rb = smooth([(900, 1300), (1150, 1100), (1700, 1080), (2050, 1150), (2050, 1300), (1700, 1360), (1100, 1380)])
    c.drawPath(rb, _lin((0, 1080), (0, 1380), [shade(col, 0.15), col, shade(col, -0.3)]))
    c.drawPath(rrect(1150, 1000, 2000, 1110, 50), fill("#1a1b20"))
    c.drawRect(_R(820, 1060, 1180, 1085), fill("#2a2c33"))
    for x in (860, 960, 1060):
        c.drawLine(x, 1060, x + 40, 1180, stroke("#2a2c33", 16))
    c.drawPath(rrect(840, 1150, 940, 1220, 16), fill("#ff3a3a"))
    c.drawArc(_R(rx - wr - 30, wy - wr - 30, rx + wr + 30, wy + wr + 30), 200, 120, False, stroke(shade(col, -0.2), 44))
    # step-through floor + leg shield
    c.drawPath(poly([(2050, 1300), (2450, 1300), (2450, 1380), (2050, 1380)]), fill("#2a2c33"))
    shield = smooth([(2380, 1360), (2400, 1000), (2520, 760), (2640, 760), (2620, 1050), (2560, 1380)])
    c.drawPath(shield, _lin((2380, 0), (2640, 0), [shade(col, -0.25), col, shade(col, 0.15)]))
    # front fork + fender + handlebar + headlight
    c.drawLine(2600, 800, fx, wy, stroke("#9aa0aa", 46))
    c.drawArc(_R(fx - wr - 20, wy - wr - 20, fx + wr + 20, wy + wr + 20), 200, 110, False, stroke(col, 40))
    c.drawLine(2500, 700, 2780, 640, stroke("#2a2c33", 34))
    c.drawPath(rrect(2470, 660, 2580, 720, 20), fill("#1a1b20"))
    c.drawPath(rrect(2560, 660, 2800, 820, 60), fill(col))
    c.drawPath(oval(2800, 760, 50, 70), fill("#fff1c8"))
    _soft_glow(c, 2830, 760, 260, "#fff1c8", 0.4)
    c.drawLine(2620, 650, 2560, 540, stroke("#2a2c33", 10))     # mirror stalk
    c.drawPath(oval(2550, 520, 50, 34), fill("#2a2c33"))
    c.drawLine(1700, 1560, 1560, 1780, stroke("#2a2c33", 22))   # kickstand
    _vignette(c, 0.4)
    return s.makeImageSnapshot()


# =================================================================== water-jug trolley
def _jug(c, l, t, w, h, col="#5ab4e8", cap="#2f6fd0") -> None:
    """20 L water jug lying sideways (neck to the right)."""
    body = rrect(l, t, l + w, t + h, h * 0.35)
    c.drawPath(body, _lin((0, t), (0, t + h), [shade(col, 0.35), col, shade(col, -0.25)]))
    for k in range(1, 4):   # ridges
        x = l + w * k / 4
        c.drawLine(x, t + h * 0.08, x, t + h * 0.92, stroke(shade(col, -0.2), 12, 0.6))
    c.drawPath(rrect(l + w - 10, t + h * 0.3, l + w + 120, t + h * 0.7, 20), fill(shade(col, -0.1)))
    c.drawPath(rrect(l + w + 100, t + h * 0.26, l + w + 190, t + h * 0.74, 16), fill(cap))
    c.drawPath(rrect(l + 40, t + h * 0.14, l + w - 60, t + h * 0.26, 20), fill("#ffffff", 0.35))
    c.drawPath(body, stroke(shade(col, -0.35), 4, 0.6))


def ins_water_jug_trolley(p, size):
    """Hand trolley in a corridor stacked with three blue 20 L water jugs held by a yellow strap."""
    s, c = _begin(size)
    wall = p.get("wall", "#d9dde0")
    c.drawRect(_R(0, 0, LW, 1500), fill(wall))
    c.drawRect(_R(0, 1380, LW, 1500), fill(shade(wall, -0.25)))
    c.drawRect(_R(0, 1500, LW, LH), _lin((0, 1500), (0, LH), ["#b9b4a8", "#8a867c"]))
    for x in range(-400, int(LW) + 400, 420):
        c.drawLine(LW / 2 + (x - LW / 2) * 0.4, 1500, x, LH, stroke("#7a766c", 6))
    for y in (1580, 1720, 1920):
        c.drawLine(0, y, LW, y, stroke("#7a766c", 6))
    fr = "#3a3d45"
    l, r = 1400.0, 2440.0
    c.drawPath(oval((l + r) / 2, 2010, 760, 60), _blurred("#000000", 0.5, 30))
    for x in (l, r):   # uprights
        c.drawPath(rrect(x - 30, 160, x + 30, 1960, 20), fill(fr))
    c.drawPath(capsule(l, 170, r, 170, 30, 30), fill(fr))
    c.drawPath(rrect(l - 20, 90, r + 20, 180, 40), stroke(fr, 34))       # handle loop
    c.drawPath(rrect(l - 120, 1920, r + 120, 1990, 10), fill("#5a5d66"))  # nose plate
    for x in (l - 60, r + 60):
        c.drawCircle(x, 1960, 120, fill("#16171b"))
        c.drawCircle(x, 1960, 50, fill("#9aa0aa"))
    jc = p.get("jug", "#5ab4e8")
    n = int(p.get("jugs", 3))
    for k in range(n):
        t = 1910 - (k + 1) * 520
        _jug(c, l - 40, t, r - l - 60, 500, jc)
    sy = 1910 - n * 520 * 0.55
    c.drawRect(_R(l - 60, sy, r + 60, sy + 90), fill(p.get("strap", "#f3c94e")))
    c.drawPath(rrect(r - 200, sy - 20, r - 40, sy + 110, 12), fill("#5a5d66"))
    _vignette(c, 0.4)
    return s.makeImageSnapshot()


# =================================================================== registration
INSERTS = {
    "phone_countdown_app": ins_phone_countdown,
    "phone_countdown_cracked": _with(ins_phone_countdown, cracked=True),
    "phone_countdown_matched": _with(ins_phone_countdown, matched=True, timer="00:00:00", status="MATCHED"),
    "phone_countdown_years": _with(ins_phone_countdown, timer="61 YEARS", timer_sub="4 MONTHS"),
    "phone_home_grid": ins_phone_home,
    "phone_wanted_screen": ins_phone_wanted,
    "phone_live_stream": ins_phone_live,
    "phone_ai_speaking": ins_phone_ai_speaking,
    "ai_ring_glow": ins_ai_ring_glow,
    "repair_price_board": ins_repair_price_board,
    "billboard_accuracy": ins_billboard_accuracy,
    "billboard_years_left": ins_billboard_years_left,
    "queue_table_screen": ins_queue_table_screen,
    "laptop_list": ins_laptop_list,
    "upload_dialog": ins_upload_dialog,
    "staff_badge_lanyard": ins_staff_badge_lanyard,
    "wristwatch_windup": ins_wristwatch_windup,
    "boat_noodle_bowl": ins_boat_noodle_bowl,
    "pocket_glow": ins_pocket_glow,
    "cctv_cameras_wall": ins_cctv_cameras_wall,
    "laundry_basket_disguise": ins_laundry_basket_disguise,
    "usb_server_plug": ins_usb_server_plug,
    "payphone_public": ins_payphone_public,
    "sedan_old_side": ins_sedan_old_side,
    "motorbike_side": ins_motorbike_side,
    "water_jug_trolley": ins_water_jug_trolley,
}

# Search metadata (English; the Vietnamese label comes from the catalog name_vi) -- never drawn into pixels.
TAGS = {
    "phone_countdown_app": ["phone", "countdown", "timer", "time left", "app", "glowing ring", "prediction"],
    "phone_countdown_cracked": ["phone", "countdown", "cracked screen", "broken phone", "timer", "time left"],
    "phone_countdown_matched": ["phone", "countdown", "zero", "matched", "time up", "deadline", "00:00:00"],
    "phone_countdown_years": ["phone", "countdown", "years left", "lifespan", "prediction", "timer"],
    "phone_home_grid": ["phone", "home screen", "app grid", "apps", "smartphone", "icons"],
    "phone_wanted_screen": ["phone", "wanted", "reward", "find this man", "report", "alert", "manhunt"],
    "phone_live_stream": ["phone", "live stream", "livestream", "viewers", "comments", "hearts", "live"],
    "phone_ai_speaking": ["phone", "assistant", "ai", "speaking", "voice", "glowing ring"],
    "ai_ring_glow": ["ai", "glowing ring", "hologram", "assistant", "ring", "sci-fi"],
    "repair_price_board": ["price board", "phone repair", "repair shop", "price list", "mall"],
    "billboard_accuracy": ["billboard", "ad", "100% accurate", "glowing ring", "night city", "advertisement"],
    "billboard_years_left": ["billboard", "portrait", "years left", "ad", "building", "night"],
    "queue_table_screen": ["queue", "table", "monitor", "control room", "list", "schedule", "screen"],
    "laptop_list": ["laptop", "list", "records", "computer", "desk", "screen"],
    "upload_dialog": ["upload", "file", "progress bar", "computer", "zip", "data", "dialog"],
    "staff_badge_lanyard": ["id badge", "staff card", "lanyard", "security", "access card", "data center"],
    "wristwatch_windup": ["wristwatch", "watch", "analog watch", "automatic", "time", "wrist"],
    "boat_noodle_bowl": ["noodles", "noodle bowl", "soup", "street food", "chopsticks", "night market"],
    "pocket_glow": ["pocket", "trousers", "glowing phone", "light", "jeans", "glow"],
    "cctv_cameras_wall": ["cctv", "security cameras", "surveillance", "camera", "wall"],
    "laundry_basket_disguise": ["laundry basket", "wig", "straw hat", "disguise", "laundromat", "glasses"],
    "usb_server_plug": ["usb", "server", "hacking", "data center", "flash drive", "rack", "hand"],
    "payphone_public": ["payphone", "public phone", "phone booth", "dawn", "roadside"],
    "sedan_old_side": ["car", "sedan", "old car", "vehicle", "side view", "beige car"],
    "motorbike_side": ["motorbike", "motorcycle", "scooter", "vehicle", "side view"],
    "water_jug_trolley": ["water jugs", "trolley", "hand truck", "delivery", "water bottles", "cart"],
}
# snake_case props; avoid generic props already owned by the original inserts ("phone", "clock", "map", "coin"...).
PROPS = {
    "phone_countdown_app": ["countdown_phone", "countdown_app", "phone_countdown", "time_left_phone"],
    "phone_countdown_cracked": ["cracked_countdown_phone", "phone_countdown_cracked"],
    "phone_countdown_matched": ["countdown_zero_phone", "matched_phone", "phone_countdown_matched"],
    "phone_countdown_years": ["years_left_phone", "phone_countdown_years", "lifespan_phone"],
    "phone_home_grid": ["phone_home_screen", "home_screen", "app_grid"],
    "phone_wanted_screen": ["phone_wanted", "wanted_screen", "reward_alert"],
    "phone_live_stream": ["phone_live", "live_stream", "livestream_phone"],
    "phone_ai_speaking": ["phone_assistant", "ai_assistant_phone", "speaking_ring"],
    "ai_ring_glow": ["ai_ring", "glowing_ring", "hologram_ring"],
    "repair_price_board": ["price_board", "repair_price_board", "repair_prices"],
    "billboard_accuracy": ["billboard", "accuracy_billboard", "ring_billboard"],
    "billboard_years_left": ["portrait_billboard", "years_left_billboard"],
    "queue_table_screen": ["queue_screen", "queue_table", "control_screen"],
    "laptop_list": ["laptop", "laptop_list", "computer"],
    "upload_dialog": ["upload_dialog", "file_upload", "upload_progress"],
    "staff_badge_lanyard": ["staff_badge", "id_badge", "lanyard", "access_card"],
    "wristwatch_windup": ["analog_watch", "windup_watch", "automatic_watch"],
    "boat_noodle_bowl": ["noodle_bowl", "boat_noodles", "noodles", "chopsticks"],
    "pocket_glow": ["glowing_pocket", "pocket_glow", "phone_in_pocket"],
    "cctv_cameras_wall": ["cctv_camera", "cctv_cameras", "security_camera"],
    "laundry_basket_disguise": ["laundry_basket", "wig", "straw_hat", "disguise"],
    "usb_server_plug": ["usb_stick", "usb_drive", "server_usb", "flash_drive"],
    "payphone_public": ["payphone", "public_phone", "phone_booth"],
    "sedan_old_side": ["old_car", "sedan", "beige_sedan"],
    "motorbike_side": ["motorbike", "motorcycle", "scooter"],
    "water_jug_trolley": ["water_jug", "water_jugs", "hand_truck", "jug_trolley"],
}
