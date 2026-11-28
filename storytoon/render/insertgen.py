"""Ảnh chèn / đạo cụ cận cảnh GỐC vẽ bằng code — gói B (docs/ASSET_PLAN.md, assets/catalog/inserts.json).

- Mọi chữ/số vẽ bằng font thật (Be Vietnam Pro, NFC) từ params — không chữ AI, không thương hiệu/logo/quốc huy/
  chân dung thật. Ngân hàng, cửa hàng, số sê-ri, tên người... đều bịa, chung chung.
- API:
    INSERTS: dict[kind, Callable[[params, (w, h)], skia.Image]]
    render_insert(kind, params=None, size=(3840, 2160)) -> skia.Image        (params trộn với mặc định catalog)
    make_insert(iid, kind, params=None, out_dir=INSERTS_DIR) -> Path          (ghi <iid>.png + <iid>.json)
    make_catalog_inserts(out_dir=INSERTS_DIR) -> list[Path]
  Phần tử dùng chung (gói C vẽ overlay cùng thiết kế; chỉ vẽ lên canvas, không đọc file, không phụ thuộc Shot):
    draw_phone(c, rect, screen: "chat"|"lock"|"bank", data)
    draw_paper_notebook(c, rect, title, rules, *, red_index=None, redact_last=False, blurred=False, ...)
    draw_missing_poster(c, rect, data)
    draw_map_card(c, rect, data)
    draw_pov_hand(c, x, y, angle, scale, sleeve, skin, kind, part)
- Tay POV: thử `puppetgen.render_hand` (gói A); chưa có -> tay "ma-nơ-canh" capsule vẽ tại chỗ.
  Ảnh thẻ: thử `puppetgen.render_portrait`; chưa có -> bóng người phẳng không mặt.
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
import random
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import skia

from ..paths import ASSETS, INSERTS as INSERTS_DIR
from .skutil import (capsule, circle, color, fill, font, mix, nfc, oval, poly, rrect, save_png, shade, smooth,
                     stroke, wrap_text)

log = logging.getLogger("storytoon.render")

CATALOG = ASSETS / "catalog" / "inserts.json"
SIZE = (3840, 2160)
SAMPLING = skia.SamplingOptions(skia.FilterMode.kLinear, skia.MipmapMode.kNone)

INK = "#1f3f8a"
RED_INK = "#c8352e"
TAPE = "#e2d3b0"
BRAND_GREEN, BRAND_CREAM, BRAND_ORANGE = "#1f6f5c", "#f2ead8", "#e8833a"


# =================================================================== tiện ích
def _rect(r) -> skia.Rect:
    if isinstance(r, skia.Rect):
        return r
    l, t, rr, b = r
    return skia.Rect.MakeLTRB(l, t, rr, b)


def _lin(p0, p1, cols, pos=None) -> skia.Paint:
    cs = [color(c[0], c[1]) if isinstance(c, tuple) else color(c) for c in cols]
    return skia.Paint(AntiAlias=True, Shader=skia.GradientShader.MakeLinear([skia.Point(*p0), skia.Point(*p1)], cs, pos))


def _rad(cx, cy, r, cols, pos=None) -> skia.Paint:
    cs = [color(c[0], c[1]) if isinstance(c, tuple) else color(c) for c in cols]
    return skia.Paint(AntiAlias=True, Shader=skia.GradientShader.MakeRadial(skia.Point(cx, cy), max(r, 1), cs, pos))


def _glow(c, x, y, r, col, a=0.6) -> None:
    p = _rad(x, y, r, [(col, a), (col, a * 0.3), (col, 0.0)], [0, 0.4, 1])
    p.setBlendMode(skia.BlendMode.kScreen)
    c.drawCircle(x, y, r, p)


def text(c, s: str, x: float, y: float, size: float, col: str, weight: str = "bold", align: str = "left",
         max_w: float | None = None, a: float = 1.0, outline: str | None = None, outline_w: float = 0.0) -> float:
    """Vẽ 1 dòng chữ (baseline y). Trả về bề rộng. align: left|center|right. Tự co chữ nếu vượt max_w."""
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
    if outline:
        c.drawString(s, x, y, f, stroke(outline, outline_w or size * 0.12, a))
    c.drawString(s, x, y, f, fill(col, a))
    return w


def _tape(c, cx, cy, w, h, ang, col=TAPE, a=0.85) -> None:
    c.save()
    c.rotate(ang, cx, cy)
    p = skia.Path()
    l, t, r, b = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
    n = 6
    p.moveTo(l, t)
    p.lineTo(r, t)
    for i in range(n + 1):                      # mép xé răng cưa
        p.lineTo(r + (6 if i % 2 else -2) * h / 60, t + (b - t) * i / n)
    p.lineTo(l, b)
    for i in range(n, -1, -1):
        p.lineTo(l + (-6 if i % 2 else 2) * h / 60, t + (b - t) * i / n)
    p.close()
    c.drawPath(p, fill(col, a))
    c.restore()


def _shadow(c, path_or_rect, blur, dy=0.0, a=0.45) -> None:
    p = fill("#000000", a)
    p.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, blur))
    if isinstance(path_or_rect, skia.Path):
        q = skia.Path(path_or_rect)
        q.offset(0, dy)
        c.drawPath(q, p)
    else:
        r = _rect(path_or_rect)
        c.drawRect(r.makeOffset(0, dy), p)


def _rich_tokens(s: str, base: str, emph: str) -> list[tuple[str, str]]:
    """'abc *def* gh' -> [(word, colour)] — đoạn trong *...* là từ khoá đỏ."""
    out = []
    for i, seg in enumerate(nfc(s).split("*")):
        for wd in seg.split():
            out.append((wd, emph if i % 2 else base))
    return out


def _wrap_tokens(tokens, f: skia.Font, max_w: float) -> list[list[tuple[str, str]]]:
    lines, cur, cw = [], [], 0.0
    sp = f.measureText(" ")
    for wd, col in tokens:
        ww = f.measureText(wd)
        if cur and cw + sp + ww > max_w:
            lines.append(cur)
            cur, cw = [], 0.0
        cw += (sp if cur else 0) + ww
        cur.append((wd, col))
    if cur:
        lines.append(cur)
    return lines


def _draw_tokens(c, line, x, y, f: skia.Font) -> float:
    sp = f.measureText(" ")
    for wd, col in line:
        c.drawString(wd, x, y, f, fill(col))
        x += f.measureText(wd) + sp
    return x


def _avatar_color(name: str) -> str:
    h = int(hashlib.md5(nfc(name).encode("utf-8")).hexdigest()[:6], 16)
    return ["#3a78c2", "#c74a9a", "#4fa35a", "#e8833a", "#8a5ac2", "#2fa3a0"][h % 6]


def _surface(size) -> tuple[skia.Surface, skia.Canvas]:
    s = skia.Surface(int(size[0]), int(size[1]))
    c = s.getCanvas()
    c.clear(skia.ColorBLACK)
    return s, c


# =================================================================== nền ảnh chèn
@lru_cache(maxsize=4)
def _location_plate(lid: str, tod: str | None) -> skia.Image | None:
    try:
        from . import locgen
        return locgen.render_scene(lid, tod).composite()
    except Exception as e:  # noqa: BLE001
        log.warning("insertgen: không dựng được nền '%s': %s", lid, e)
        return None


def draw_background(c, kind: str, W: int, H: int, params: dict | None = None) -> None:
    params = params or {}
    u = H / 2160
    if kind in ("dark_vignette", "dark_gradient", "none"):
        c.drawRect(skia.Rect.MakeWH(W, H), _rad(W / 2, H * 0.46, W * 0.62, ["#2a3348", "#0b0f18"] if kind != "dark_gradient"
                                                  else ["#1c2130", "#050608"]))
    elif kind == "blur_location":
        lid = params.get("bg_location", "cua_hang_quay_thu_ngan")
        img = _location_plate(lid, params.get("bg_time"))
        if img is None:
            draw_background(c, "dark_vignette", W, H)
            return
        p = skia.Paint(ImageFilter=skia.ImageFilters.Blur(36 * u, 36 * u, skia.TileMode.kClamp))
        c.drawImageRect(img, skia.Rect.MakeWH(W, H), SAMPLING, p)
        c.drawRect(skia.Rect.MakeWH(W, H), fill("#000000", 0.35))
    elif kind == "smoke_dark":
        c.drawRect(skia.Rect.MakeWH(W, H), _rad(W / 2, H / 2, W * 0.7, ["#2a2c31", "#121316"]))
        rng = random.Random(5)
        for _ in range(14):
            x, y = rng.uniform(0, W), rng.uniform(0, H)
            p = fill("#9aa0aa", rng.uniform(0.03, 0.07))
            p.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 120 * u))
            c.drawPath(oval(x, y, rng.uniform(300, 700) * u, rng.uniform(120, 260) * u), p)
    elif kind == "wood_dark":
        c.drawRect(skia.Rect.MakeWH(W, H), fill("#3b2618"))
        rng = random.Random(3)
        y = 0.0
        while y < H:
            hh = rng.uniform(120, 260) * u
            c.drawRect(skia.Rect.MakeLTRB(0, y, W, y + hh), fill(rng.choice(["#3b2618", "#432c1c", "#352215"])))
            for _ in range(5):
                yy = y + rng.uniform(0, hh)
                pth = skia.Path()
                pth.moveTo(0, yy)
                pth.cubicTo(W * 0.3, yy + rng.uniform(-20, 20) * u, W * 0.6, yy + rng.uniform(-20, 20) * u, W, yy)
                c.drawPath(pth, stroke("#26170e", 3 * u, 0.6))
            c.drawRect(skia.Rect.MakeLTRB(0, y + hh - 4 * u, W, y + hh), fill("#1c110a"))
            y += hh
        c.drawRect(skia.Rect.MakeWH(W, H), _rad(W / 2, H / 2, W * 0.65, [("#000000", 0.0), ("#000000", 0.6)], [0.4, 1]))
    elif kind == "wall_grey":
        c.drawRect(skia.Rect.MakeWH(W, H), _rad(W * 0.45, H * 0.4, W * 0.7, ["#a39d92", "#5d5850"]))
    elif kind in ("tiles_white", "dark_tiles"):
        base, line = ("#e9ecee", "#b9bec4") if kind == "tiles_white" else ("#3a3d44", "#2a2c31")
        c.drawRect(skia.Rect.MakeWH(W, H), fill(base))
        step = 360 * u
        x = 0.0
        while x < W:
            c.drawRect(skia.Rect.MakeLTRB(x, 0, x + 6 * u, H), fill(line))
            x += step
        y = 0.0
        while y < H:
            c.drawRect(skia.Rect.MakeLTRB(0, y, W, y + 6 * u), fill(line))
            y += step
        c.drawRect(skia.Rect.MakeWH(W, H), _rad(W / 2, H / 2, W * 0.7, [("#000000", 0.0), ("#000000", 0.35)], [0.45, 1]))
    elif kind == "sidewalk":
        c.drawRect(skia.Rect.MakeWH(W, H), fill("#77726a"))
        rng = random.Random(9)
        for _ in range(900):
            x, y = rng.uniform(0, W), rng.uniform(0, H)
            c.drawCircle(x, y, rng.uniform(2, 7) * u, fill(rng.choice(["#5f5a53", "#8a857c", "#6b665e"]), 0.7))
        for k in range(4):                      # vết nứt gãy khúc ngắn
            x, y = rng.uniform(0, W), rng.uniform(0, H)
            pts = [(x, y)]
            for _ in range(7):
                x += rng.uniform(40, 120) * u
                y += rng.uniform(-60, 60) * u
                pts.append((x, y))
            c.drawPath(poly(pts, close=False), stroke("#4a463f", 4 * u, 0.55))
        c.drawRect(skia.Rect.MakeWH(W, H), _rad(W / 2, H / 2, W * 0.65, [("#000000", 0.0), ("#000000", 0.55)], [0.35, 1]))
    elif kind == "shutter":
        y = 0.0
        k = 0
        while y < H:
            c.drawRect(skia.Rect.MakeLTRB(0, y, W, y + 54 * u), fill("#b8babf" if k % 2 == 0 else "#8a8d93"))
            c.drawRect(skia.Rect.MakeLTRB(0, y + 48 * u, W, y + 54 * u), fill("#6a6d73"))
            y += 54 * u
            k += 1
        rng = random.Random(2)
        for _ in range(30):
            c.drawPath(oval(rng.uniform(0, W), rng.uniform(0, H), rng.uniform(20, 90) * u, rng.uniform(8, 30) * u),
                       fill("#8a5a3a", rng.uniform(0.2, 0.5)))
        c.drawRect(skia.Rect.MakeWH(W, H), _rad(W / 2, H / 2, W * 0.7, [("#000000", 0.0), ("#000000", 0.5)], [0.4, 1]))
    elif kind == "counter":
        c.drawRect(skia.Rect.MakeLTRB(0, 0, W, H * 0.62), _lin((0, 0), (0, H * 0.62), ["#3a4250", "#1c2028"]))
        c.drawRect(skia.Rect.MakeLTRB(0, H * 0.62, W, H), _lin((0, H * 0.62), (0, H), ["#f4f4f2", "#d9dcdf"]))
        c.drawRect(skia.Rect.MakeLTRB(0, H * 0.6, W, H * 0.625), fill(BRAND_GREEN))
        p = fill("#ffffff", 0.08)
        p.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 40 * u))
        c.drawPath(oval(W * 0.3, H * 0.25, 500 * u, 120 * u), p)
    elif kind == "dusk_road":
        c.drawRect(skia.Rect.MakeLTRB(0, 0, W, H * 0.62), _lin((0, 0), (0, H * 0.62), ["#3b2f5c", "#b4566a", "#f0a25a"],
                                                                [0, 0.6, 1]))
        rng = random.Random(11)
        x = 0.0                                   # hàng cây/mái nhà xa (bóng phẳng)
        pts = [(0, H * 0.62)]
        while x < W:
            pts.append((x, H * (0.5 + rng.uniform(-0.05, 0.04))))
            x += rng.uniform(80, 220) * u
        pts += [(W, H * 0.55), (W, H * 0.62)]
        c.drawPath(poly(pts), fill("#2b2238"))
        c.drawRect(skia.Rect.MakeLTRB(0, H * 0.62, W, H), _lin((0, H * 0.62), (0, H), ["#4a4450", "#26232b"]))
        c.drawPath(poly([(W * 0.46, H * 0.62), (W * 0.54, H * 0.62), (W * 0.9, H), (W * 0.1, H)]), fill("#35313a"))
        for k in range(5):                        # vạch giữa đường
            y0 = H * (0.64 + 0.075 * k * (1 + k * 0.25))
            hh = H * 0.02 * (1 + k * 0.6)
            ww = W * 0.004 * (1 + k * 0.8)
            c.drawRect(skia.Rect.MakeLTRB(W / 2 - ww, y0, W / 2 + ww, y0 + hh), fill("#d9cfae", 0.7))
        c.drawRect(skia.Rect.MakeWH(W, H), _rad(W / 2, H / 2, W * 0.7, [("#000000", 0.0), ("#000000", 0.45)], [0.45, 1]))
    else:
        draw_background(c, "dark_vignette", W, H)


# =================================================================== tay POV (fallback "ma-nơ-canh")
def draw_pov_hand(c, x: float, y: float, angle: float = 0.0, scale: float = 1.0, sleeve: str = BRAND_GREEN,
                  skin: str = "#c9926a", kind: str = "grip", part: str = "all", mirror: bool = False) -> None:
    """Tay to vào từ đáy khung. (x, y) = điểm cổ tay; tay hướng LÊN, xoay `angle` độ.
    part: 'back' (tay áo + lòng bàn tay + ngón phía sau vật), 'front' (ngón cái đè lên vật), 'all'.
    kind: grip (cầm cạnh vật) | pinch (nhón) | point (chỉ) | open."""
    s = scale
    dark = shade(skin, -0.18)
    nail = shade(skin, 0.45)
    c.save()
    c.translate(x, y)
    c.rotate(angle)
    if mirror:
        c.scale(-1, 1)

    def finger(x0, y0, x1, y1, w, with_nail=True):
        c.drawPath(capsule(x0 * s, y0 * s, x1 * s, y1 * s, w * s, w * 0.9 * s), fill(skin))
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        c.drawCircle(mx * s, my * s, w * 0.36 * s, fill(dark, 0.35))                 # khớp tròn
        ln = math.hypot(x1 - x0, y1 - y0) or 1
        dx, dy = (x1 - x0) / ln, (y1 - y0) / ln
        c.drawLine((mx - dy * w * 0.25) * s, (my + dx * w * 0.25) * s, (mx + dy * w * 0.25) * s,
                   (my - dx * w * 0.25) * s, stroke(dark, 3 * s, 0.6))
        if with_nail:
            nx, ny = x1 - dx * w * 0.28, y1 - dy * w * 0.28
            c.save()
            c.translate(nx * s, ny * s)
            c.rotate(math.degrees(math.atan2(dy, dx)) + 90)
            c.drawPath(rrect(-w * 0.26 * s, -w * 0.3 * s, w * 0.26 * s, w * 0.24 * s, w * 0.18 * s), fill(nail))
            c.restore()

    if part in ("back", "all"):
        # tay áo + cổ tay áo
        c.drawPath(rrect(-170 * s, 30 * s, 170 * s, 1400 * s, 60 * s), fill(sleeve))
        c.drawPath(rrect(-178 * s, 10 * s, 178 * s, 110 * s, 40 * s), fill(shade(sleeve, -0.2)))
        c.drawRect(skia.Rect.MakeLTRB(100 * s, 110 * s, 170 * s, 1400 * s), fill(shade(sleeve, -0.15)))
        # cổ tay + lòng bàn tay
        c.drawPath(rrect(-95 * s, -60 * s, 95 * s, 40 * s, 40 * s), fill(skin))
        c.drawPath(rrect(-135 * s, -280 * s, 135 * s, -20 * s, 90 * s), fill(skin))
        c.drawPath(rrect(70 * s, -270 * s, 135 * s, -30 * s, 60 * s), fill(dark, 0.45))
        if kind == "grip":
            for i in range(4):                      # 4 ngón co sau vật
                fx = -95 + i * 62
                finger(fx, -250, fx + 8, -380 - (12 if i in (1, 2) else 0), 64, with_nail=False)
        elif kind == "pinch":
            for i in range(3):
                fx = -40 + i * 58
                finger(fx, -240, fx + 30, -330, 60, with_nail=False)
            finger(-100, -250, -40, -470, 66)       # ngón trỏ
        elif kind == "point":
            for i in range(3):
                fx = -40 + i * 58
                finger(fx, -250, fx + 24, -320, 62, with_nail=False)
            finger(-100, -260, -110, -560, 66)
        else:  # open
            for i, ln in enumerate((300, 330, 320, 270)):
                fx = -95 + i * 62
                finger(fx, -250, fx + (i - 1.5) * 20, -250 - ln, 62)
    if part in ("front", "all"):
        if kind in ("grip", "pinch"):
            finger(-140, -110, -150 if kind == "grip" else -60, -350 if kind == "grip" else -450, 76)
        elif kind == "open":
            finger(-140, -110, -260, -260, 72)
    c.restore()


@lru_cache(maxsize=16)
def _a_hand_image(kind: str, sleeve: str, skin: str) -> skia.Image | None:
    """Ảnh tay POV của gói A (puppetgen.render_hand: ~900×1400, cổ tay ở đáy giữa). None nếu chưa có."""
    try:
        from . import puppetgen  # type: ignore
        rh = getattr(puppetgen, "render_hand", None)
        return rh(kind, sleeve, skin, 1.0) if rh is not None else None
    except Exception as e:  # noqa: BLE001
        log.info("puppetgen.render_hand chưa dùng được (%s) — dùng tay tạm", e)
        return None


# Quy đổi ảnh tay gói A sang hệ toạ độ tay của module này (cổ tay = gốc, lòng bàn tay rộng 270·s).
_A_WIDTH_PER_S = 270 * 900 / 330        # bề rộng ảnh A (px) / scale
_A_WRIST_FRAC = 0.78                    # cổ tay nằm ở 78% chiều cao ảnh A
_A_PINCH_TIP = (0.30, 0.42)             # điểm giữa ngón cái + trỏ của kind 'pinch' (phân số ảnh A)


def _draw_a_hand(c, img: skia.Image, x, y, angle, scale, sleeve, mirror) -> None:
    tw = _A_WIDTH_PER_S * scale
    th = img.height() * tw / max(1, img.width())
    c.save()
    c.translate(x, y)
    c.rotate(angle)
    if mirror:
        c.scale(-1, 1)
    top = -_A_WRIST_FRAC * th
    # nối dài ống tay áo xuống khỏi khung
    c.drawRect(skia.Rect.MakeLTRB(-0.225 * tw, top + th * 0.95, 0.225 * tw, top + th + 1400 * scale), fill(sleeve))
    c.drawImageRect(img, skia.Rect.MakeLTRB(-tw / 2, top, tw / 2, top + th), SAMPLING)
    c.restore()


def hand_tip(x, y, angle, scale, kind: str = "pinch", mirror: bool = False) -> tuple[float, float]:
    """Toạ độ khung của đầu ngón (để đặt đồng xu/vật nhón)."""
    if _a_hand_image(kind, BRAND_GREEN, "#c9926a") is not None:
        tw = _A_WIDTH_PER_S * scale
        th = tw * 1400 / 900
        lx, ly = (_A_PINCH_TIP[0] - 0.5) * tw, (_A_PINCH_TIP[1] - _A_WRIST_FRAC) * th
    else:
        lx, ly = -50 * scale, -455 * scale
    if mirror:
        lx = -lx
    a = math.radians(angle)
    return x + lx * math.cos(a) - ly * math.sin(a), y + lx * math.sin(a) + ly * math.cos(a)


def _hand(c, x, y, angle, scale, sleeve, skin, kind, part, mirror=False) -> None:
    """Tay POV. Có gói A -> ảnh tay A (grip: ảnh A vẽ SAU vật + ngón cái capsule đè lên vật);
    chưa có -> tay capsule tại chỗ."""
    akind = kind if kind in ("open", "point", "pinch", "hold", "grip") else "grip"
    img = _a_hand_image(akind, sleeve, skin)
    if img is None:
        draw_pov_hand(c, x, y, angle, scale, sleeve, skin, kind, part, mirror)
        return
    if kind == "grip":
        if part in ("back", "all"):
            _draw_a_hand(c, img, x, y, angle, scale, sleeve, mirror)
        if part in ("front", "all"):
            draw_pov_hand(c, x, y, angle, scale, sleeve, skin, kind, "front", mirror)
        return
    if part in ("front", "all"):
        _draw_a_hand(c, img, x, y, angle, scale, sleeve, mirror)


# =================================================================== điện thoại
def _status_bar(c, l, t, r, h, time_s: str, col: str = "#ffffff") -> None:
    text(c, time_s, l + h * 0.9, t + h * 0.68, h * 0.5, col, "semibold")
    x = r - h * 0.9
    c.drawPath(rrect(x - h * 0.9, t + h * 0.32, x, t + h * 0.68, h * 0.08), stroke(col, h * 0.05))
    c.drawRect(skia.Rect.MakeLTRB(x - h * 0.84, t + h * 0.38, x - h * 0.25, t + h * 0.62), fill(col))
    c.drawRect(skia.Rect.MakeLTRB(x + h * 0.03, t + h * 0.43, x + h * 0.09, t + h * 0.57), fill(col))
    x -= h * 1.25
    for i in range(4):
        bh = h * (0.14 + i * 0.1)
        c.drawPath(rrect(x - (3 - i) * h * 0.16 - h * 0.1, t + h * 0.68 - bh, x - (3 - i) * h * 0.16, t + h * 0.68, h * 0.03),
                   fill(col, 1.0 if i < 3 else 0.4))


def _chat_glyph(c, cx, cy, r, col="#ffffff") -> None:
    c.drawPath(oval(cx, cy - r * 0.05, r * 0.62, r * 0.5), fill(col))
    c.drawPath(poly([(cx - r * 0.35, cy + r * 0.25), (cx - r * 0.5, cy + r * 0.6), (cx - r * 0.05, cy + r * 0.38)]), fill(col))


def _screen_chat(c, sl, st, sr, sb, d: dict) -> None:
    sw, sh = sr - sl, sb - st
    c.drawRect(skia.Rect.MakeLTRB(sl, st, sr, sb), fill(d.get("screen", "#101114")))
    bar = sh * 0.045
    _status_bar(c, sl, st + sh * 0.012, sr, bar, (d.get("time") or "03:12"))
    # header
    hy = st + sh * 0.06
    hh = sh * 0.085
    c.drawRect(skia.Rect.MakeLTRB(sl, hy, sr, hy + hh), fill("#17181c"))
    c.drawLine(sl, hy + hh, sr, hy + hh, stroke("#2a2b30", 2))
    pth = skia.Path()
    pth.moveTo(sl + sw * 0.075, hy + hh * 0.32)
    pth.lineTo(sl + sw * 0.05, hy + hh * 0.5)
    pth.lineTo(sl + sw * 0.075, hy + hh * 0.68)
    c.drawPath(pth, stroke("#2e7cf6", sw * 0.012))
    name = nfc(d.get("contact") or d.get("title") or "Minh")
    ar = hh * 0.32
    ax, ay = sl + sw * 0.17, hy + hh / 2
    c.drawCircle(ax, ay, ar, fill(_avatar_color(name)))
    text(c, name[:1].upper(), ax, ay + ar * 0.38, ar * 1.05, "#ffffff", "bold", "center")
    text(c, name, ax + ar * 1.5, ay - hh * 0.02, hh * 0.27, "#ffffff", "bold", max_w=sw * 0.5)
    status = d.get("status") or d.get("subtitle") or ""
    if status:
        c.drawCircle(ax + ar * 1.62, ay + hh * 0.2, hh * 0.05, fill("#3cd06b"))
        text(c, status, ax + ar * 1.85, ay + hh * 0.27, hh * 0.19, "#9a9ca3", "regular", max_w=sw * 0.5)
    # tin nhắn
    fs = sh * 0.028
    f = font(fs, "semibold")
    y = hy + hh + sh * 0.03
    text(c, (d.get("time") or "03:12"), sl + sw / 2, y + fs * 0.6, fs * 0.62, "#7d8088", "semibold", "center")
    y += fs * 1.6
    pad = fs * 0.62
    maxw = sw * 0.66
    for m in d.get("messages", []):
        me = m.get("from") == "me"
        lines = wrap_text(m.get("text", ""), f, maxw - pad * 2)
        bw = max(f.measureText(ln) for ln in lines) + pad * 2 if lines else pad * 4
        bh = len(lines) * fs * 1.28 + pad * 1.4
        if y + bh > sb - sh * 0.12:
            break
        bx = sr - sw * 0.05 - bw if me else sl + sw * 0.05
        col = d.get("bubble_out", "#2e7cf6") if me else d.get("bubble_in", "#3a3b40")
        c.drawPath(rrect(bx, y, bx + bw, y + bh, fs * 0.8), fill(col))
        tail_x = bx + bw - fs * 0.3 if me else bx + fs * 0.3
        c.drawPath(poly([(tail_x - fs * 0.35, y + bh - fs * 0.6), (tail_x + (fs * 0.55 if me else -fs * 0.55), y + bh),
                         (tail_x + fs * 0.35 * (-1 if me else 1), y + bh - fs * 0.1)]), fill(col))
        for i, ln in enumerate(lines):
            c.drawString(ln, bx + pad, y + pad * 0.7 + fs * (1.0 + i * 1.28), f, fill("#ffffff"))
        y += bh + fs * 0.7
    # thanh nhập
    iy = sb - sh * 0.085
    c.drawRect(skia.Rect.MakeLTRB(sl, iy - sh * 0.012, sr, sb), fill("#17181c"))
    ir = sh * 0.024
    c.drawCircle(sl + sw * 0.08, iy + ir, ir, fill("#2e7cf6"))
    c.drawLine(sl + sw * 0.08 - ir * 0.5, iy + ir, sl + sw * 0.08 + ir * 0.5, iy + ir, stroke("#ffffff", ir * 0.2))
    c.drawLine(sl + sw * 0.08, iy + ir * 0.5, sl + sw * 0.08, iy + ir * 1.5, stroke("#ffffff", ir * 0.2))
    c.drawPath(rrect(sl + sw * 0.15, iy, sr - sw * 0.17, iy + ir * 2, ir), fill("#2a2b30"))
    text(c, d.get("placeholder", "Message..."), sl + sw * 0.19, iy + ir * 1.35, ir * 0.85, "#7d8088", "regular")
    c.drawCircle(sr - sw * 0.09, iy + ir, ir, fill("#2e7cf6"))
    c.drawPath(poly([(sr - sw * 0.09 - ir * 0.45, iy + ir * 0.55), (sr - sw * 0.09 + ir * 0.55, iy + ir),
                     (sr - sw * 0.09 - ir * 0.45, iy + ir * 1.45), (sr - sw * 0.09 - ir * 0.2, iy + ir)]), fill("#ffffff"))


def _screen_lock(c, sl, st, sr, sb, d: dict) -> None:
    sw, sh = sr - sl, sb - st
    c.drawRect(skia.Rect.MakeLTRB(sl, st, sr, sb), _lin((sl, st), (sr, sb), ["#1d3a4a", "#2a2448", "#120f1e"]))
    for k in range(3):
        c.drawPath(oval(sl + sw * (0.2 + k * 0.3), st + sh * (0.75 - k * 0.12), sw * 0.5, sh * 0.12),
                   fill(["#2f5a6a", "#3a3466", "#1f2d4a"][k], 0.45))
    _status_bar(c, sl, st + sh * 0.012, sr, sh * 0.045, "")
    c.drawPath(rrect(sl + sw / 2 - sw * 0.025, st + sh * 0.1, sl + sw / 2 + sw * 0.025, st + sh * 0.13, sw * 0.01),
               stroke("#ffffff", sw * 0.006))
    c.drawPath(rrect(sl + sw / 2 - sw * 0.04, st + sh * 0.125, sl + sw / 2 + sw * 0.04, st + sh * 0.165, sw * 0.008),
               fill("#ffffff"))
    text(c, d.get("date", "Monday, March 12"), sl + sw / 2, st + sh * 0.225, sh * 0.026, "#ffffff", "semibold", "center")
    text(c, (d.get("time") or "06:00"), sl + sw / 2, st + sh * 0.355, sh * 0.13, "#ffffff", "semibold", "center", max_w=sw * 0.9)
    n = d.get("notification") or {}
    if n:
        f = font(sh * 0.024, "regular")
        lines = wrap_text(n.get("text", ""), f, sw * 0.7)[:3]
        ch = sh * (0.105 + 0.03 * len(lines))
        cl, ct, cr = sl + sw * 0.05, st + sh * 0.46, sr - sw * 0.05
        c.drawPath(rrect(cl, ct, cr, ct + ch, sw * 0.05), fill("#ffffff", 0.82))
        ir = sh * 0.03
        c.drawPath(rrect(cl + sw * 0.04, ct + sh * 0.02, cl + sw * 0.04 + ir * 2, ct + sh * 0.02 + ir * 2, ir * 0.5), fill("#3cb45a"))
        _chat_glyph(c, cl + sw * 0.04 + ir, ct + sh * 0.02 + ir, ir * 0.9)
        text(c, n.get("app", "Messages").upper(), cl + sw * 0.06 + ir * 2, ct + sh * 0.045, sh * 0.018, "#5a5d66", "semibold")
        text(c, n.get("when", "now"), cr - sw * 0.05, ct + sh * 0.045, sh * 0.018, "#5a5d66", "regular", "right")
        text(c, n.get("sender", "Mom"), cl + sw * 0.05, ct + sh * 0.092, sh * 0.026, "#111216", "bold", max_w=sw * 0.8)
        for i, ln in enumerate(lines):
            c.drawString(ln, cl + sw * 0.05, ct + sh * (0.128 + i * 0.03), f, fill("#22252b"))
    for k, cx in enumerate((sl + sw * 0.18, sr - sw * 0.18)):
        c.drawCircle(cx, sb - sh * 0.08, sw * 0.065, fill("#ffffff", 0.18))
    c.drawPath(rrect(sl + sw * 0.32, sb - sh * 0.022, sr - sw * 0.32, sb - sh * 0.014, sh * 0.004), fill("#ffffff"))


def _screen_bank(c, sl, st, sr, sb, d: dict) -> None:
    sw, sh = sr - sl, sb - st
    c.drawRect(skia.Rect.MakeLTRB(sl, st, sr, sb), fill("#f2f4f8"))
    hb = st + sh * 0.36
    c.drawRect(skia.Rect.MakeLTRB(sl, st, sr, hb), _lin((sl, st), (sr, hb), [d.get("header_from", "#1e5fd0"), d.get("header_to", "#3aa0f0")]))
    _status_bar(c, sl, st + sh * 0.012, sr, sh * 0.045, (d.get("time") or "09:41"))
    # mark gốc: vòng tròn + gợn sóng (không logo thật)
    mx, my, mr = sl + sw * 0.11, st + sh * 0.095, sh * 0.026
    c.drawCircle(mx, my, mr, fill("#ffffff"))
    pth = skia.Path()
    pth.moveTo(mx - mr * 0.6, my + mr * 0.1)
    pth.cubicTo(mx - mr * 0.3, my - mr * 0.4, mx, my + mr * 0.4, mx + mr * 0.6, my - mr * 0.15)
    c.drawPath(pth, stroke(d.get("header_from", "#1e5fd0"), mr * 0.22))
    text(c, d.get("bank_name") or d.get("title") or "LOTUS BANK", mx + mr * 1.6, my + mr * 0.4, sh * 0.026,
         "#ffffff", "bold", max_w=sw * 0.7)
    text(c, "Checking account", sl + sw * 0.07, st + sh * 0.175, sh * 0.02, "#dbe8ff", "regular")
    text(c, d.get("account") or d.get("account_masked") or d.get("subtitle") or "ACCOUNT · ****2731",
         sl + sw * 0.07, st + sh * 0.205, sh * 0.021, "#ffffff", "semibold", max_w=sw * 0.86)
    text(c, "Available balance", sl + sw * 0.07, st + sh * 0.255, sh * 0.02, "#dbe8ff", "regular")
    text(c, d.get("balance", "$1,250.00"), sl + sw * 0.07, st + sh * 0.315, sh * 0.05, "#ffffff", "bold", max_w=sw * 0.86)
    # danh sách giao dịch
    c.drawPath(rrect(sl, hb - sh * 0.02, sr, sb, sw * 0.06), fill("#ffffff"))
    text(c, "Recent transactions", sl + sw * 0.07, hb + sh * 0.045, sh * 0.024, "#1a1c22", "bold")
    y = hb + sh * 0.08
    neg, pos = d.get("neg", "#d0302a"), d.get("pos", "#2f9a4a")
    for i, tr in enumerate(d.get("transactions", [])[:6]):
        amt = str(tr.get("amount", ""))
        is_neg = amt.strip().startswith("-")
        c.drawCircle(sl + sw * 0.12, y + sh * 0.035, sh * 0.024, fill("#fde4e2" if is_neg else "#e2f4e7"))
        c.drawPath(poly([(sl + sw * 0.12 - sh * 0.01, y + sh * (0.03 if is_neg else 0.04)),
                         (sl + sw * 0.12 + sh * 0.01, y + sh * (0.03 if is_neg else 0.04)),
                         (sl + sw * 0.12, y + sh * (0.045 if is_neg else 0.025))]), fill(neg if is_neg else pos))
        text(c, tr.get("label", ""), sl + sw * 0.21, y + sh * 0.03, sh * 0.022, "#1a1c22", "semibold", max_w=sw * 0.42)
        text(c, tr.get("date") or f"{12 - i:02d}/03 · 0{2 + i}:1{i}", sl + sw * 0.21, y + sh * 0.058, sh * 0.017, "#8a8d96", "regular")
        text(c, amt, sr - sw * 0.06, y + sh * 0.042, sh * 0.023, neg if is_neg else pos,
             "bold", "right", max_w=sw * 0.36)
        c.drawLine(sl + sw * 0.21, y + sh * 0.078, sr - sw * 0.06, y + sh * 0.078, stroke("#eceef2", 2))
        y += sh * 0.085
    c.drawRect(skia.Rect.MakeLTRB(sl, sb - sh * 0.07, sr, sb), fill("#ffffff"))
    c.drawLine(sl, sb - sh * 0.07, sr, sb - sh * 0.07, stroke("#e3e6ec", 2))
    for k in range(4):
        cx = sl + sw * (0.14 + k * 0.24)
        c.drawPath(rrect(cx - sh * 0.014, sb - sh * 0.05, cx + sh * 0.014, sb - sh * 0.022, sh * 0.006),
                   fill(d.get("header_from", "#1e5fd0") if k == 0 else "#b9bdc6"))


# màn hình điện thoại theo tên (insertgen_batch2 đăng ký thêm: sms, call, gps, draft)
SCREENS: dict[str, Callable] = {"chat": _screen_chat, "lock": _screen_lock, "bank": _screen_bank}


def draw_phone(c: skia.Canvas, rect, screen: str = "chat", data: dict | None = None) -> None:
    """Điện thoại hiện đại (viền đen, notch viên thuốc). screen: chat | lock | bank | sms | call | gps | draft."""
    d = data or {}
    r = _rect(rect)
    l, t, rr, b = r.left(), r.top(), r.right(), r.bottom()
    w = rr - l
    rad = w * 0.13
    body = rrect(l, t, rr, b, rad)
    _shadow(c, body, w * 0.05, w * 0.03, 0.55)
    c.drawPath(body, fill(d.get("bezel", "#0b0b0d")))
    c.drawPath(rrect(l + w * 0.006, t + w * 0.006, rr - w * 0.006, b - w * 0.006, rad * 0.97), stroke("#3a3c42", w * 0.008))
    bz = w * 0.035
    sl, st, sr, sb = l + bz, t + bz, rr - bz, b - bz
    c.save()
    c.clipPath(rrect(sl, st, sr, sb, rad * 0.75), skia.ClipOp.kIntersect, True)
    SCREENS.get(screen, _screen_chat)(c, sl, st, sr, sb, d)
    # vệt phản chiếu kính
    c.drawPath(poly([(sl, st + (sb - st) * 0.55), (sl + (sr - sl) * 0.5, st), (sl + (sr - sl) * 0.62, st),
                     (sl, st + (sb - st) * 0.66)]), fill("#ffffff", 0.05))
    c.restore()
    c.drawPath(rrect(l + w / 2 - w * 0.13, st + w * 0.02, l + w / 2 + w * 0.13, st + w * 0.075, w * 0.03), fill("#000000"))
    c.drawRect(skia.Rect.MakeLTRB(rr - 2, t + (b - t) * 0.2, rr + w * 0.012, t + (b - t) * 0.28), fill("#1a1b1f"))


def _phone_insert(screen: str, p: dict, size) -> skia.Image:
    W, H = size
    s, c = _surface(size)
    draw_background(c, p.get("bg", "dark_vignette"), W, H, p)
    ph = H * float(p.get("phone_h", 0.86))
    pw = ph * 0.49
    cx, cy = W / 2, H * 0.53
    rect = skia.Rect.MakeLTRB(cx - pw / 2, cy - ph / 2, cx + pw / 2, cy + ph / 2)
    hands = p.get("hands", True)
    sleeve, skin = p.get("sleeve_color", BRAND_GREEN), p.get("skin", "#c9926a")
    u = H / 2160
    c.save()
    c.rotate(float(p.get("tilt", -4)), cx, cy)
    if hands:
        _hand(c, cx + pw * 0.36, H + 120 * u, -16, 1.45 * u, sleeve, skin, "grip", "back", mirror=True)
    draw_phone(c, rect, screen, p)
    if hands:
        _hand(c, cx + pw * 0.36, H + 120 * u, -16, 1.45 * u, sleeve, skin, "grip", "front", mirror=True)
    c.restore()
    return s.makeImageSnapshot()


def ins_phone_chat(p, size):
    return _phone_insert("chat", p, size)


def ins_phone_lock(p, size):
    return _phone_insert("lock", p, size)


def ins_phone_bank(p, size):
    return _phone_insert("bank", p, size)


# =================================================================== giấy vở (nội quy)
def draw_paper_notebook(c: skia.Canvas, rect, title: str, rules: list[str], *, red_index: int | None = None,
                        redact_last: bool = False, blurred: bool = False, note: str | None = None,
                        coffee_stain: bool = False, bleed_through: bool = False, rotation: float = 0.0,
                        tape: bool = True, params: dict | None = None) -> None:
    """Tờ giấy vở kẻ: kem, dòng xanh nhạt, lề đỏ, băng keo be 2 góc, chữ xanh đậm; 1 luật đỏ; thanh bôi đen."""
    pp = {"paper": "#f3ead6", "lines": "#a9c4e0", "margin": "#d0302a", "ink": INK, "red_ink": RED_INK, "tape": TAPE}
    pp.update(params or {})
    r = _rect(rect)
    l, t, rr, b = r.left(), r.top(), r.right(), r.bottom()
    w, h = rr - l, b - t
    cx, cy = (l + rr) / 2, (t + b) / 2
    c.save()
    c.rotate(rotation, cx, cy)
    if blurred:
        c.saveLayer(None, skia.Paint(ImageFilter=skia.ImageFilters.Blur(h * 0.006, h * 0.006)))
    paper = rrect(l, t, rr, b, w * 0.012)
    _shadow(c, paper, h * 0.025, h * 0.012, 0.5)
    c.drawPath(paper, _lin((l, t), (rr, b), [shade(pp["paper"], 0.05), pp["paper"], shade(pp["paper"], -0.04)]))
    lh = h / 15.5
    top_line = t + lh * 3.1
    y = top_line
    while y < b - lh * 0.4:
        c.drawLine(l + w * 0.02, y, rr - w * 0.02, y, stroke(pp["lines"], max(2.0, h * 0.0022)))
        y += lh
    mx = l + w * 0.11
    c.drawRect(skia.Rect.MakeLTRB(l, t, l + w * 0.028, b), fill(pp["margin"], 0.85))
    c.drawLine(mx, t, mx, b, stroke(pp["margin"], max(2.0, h * 0.0025), 0.8))
    for k in range(int((b - t) / (lh * 2.2))):
        c.drawCircle(l + w * 0.055, t + lh * (1.4 + k * 2.2), w * 0.009, fill("#2a2620", 0.75))
    if bleed_through:
        bf = font(lh * 0.5, "semibold")
        c.save()
        c.translate(cx, 0)
        c.scale(-1, 1)
        c.translate(-cx, 0)
        for i, rule in enumerate(rules):
            c.drawString(nfc(rule), l + w * 0.2, top_line + lh * (i * 2 + 0.75), bf, fill(pp["ink"], 0.07))
        c.restore()
    if coffee_stain:
        sx, sy, sr_ = rr - w * 0.2, b - h * 0.16, w * 0.12
        c.drawCircle(sx, sy, sr_, stroke("#8a5a2e", w * 0.012, 0.22))
        c.drawCircle(sx + sr_ * 0.06, sy + sr_ * 0.04, sr_ * 0.92, fill("#a87440", 0.08))
    # tiêu đề + ghi chú
    text(c, title or "", cx + w * 0.04, t + lh * 1.55, lh * 0.95, pp["ink"], "extrabold", "center", max_w=w * 0.8)
    if note:
        text(c, note, cx + w * 0.04, t + lh * 2.55, lh * 0.45, "#6b6f7a", "regular", "center", max_w=w * 0.8)
    # luật (chữ "viết tay": xanh, xoay nhẹ từng dòng)
    fs = lh * 0.56
    f = font(fs, "semibold")
    y = top_line + lh * 0.82
    rng = random.Random(len(rules))
    last_lines = None
    for i, rule in enumerate(rules):
        col = pp["red_ink"] if red_index == i else pp["ink"]
        tokens = _rich_tokens(f"{i + 1}. {rule}", col, pp["red_ink"])
        lines = _wrap_tokens(tokens, f, rr - mx - w * 0.08)
        start_y = y
        for ln in lines:
            if y > b - lh * 0.3:
                break
            c.save()
            c.rotate(rng.uniform(-0.6, 0.6), mx + w * 0.03, y)
            _draw_tokens(c, ln, mx + w * 0.03, y, f)
            c.restore()
            y += lh
        if red_index == i:
            c.drawLine(mx + w * 0.03, y - lh * 0.82, mx + w * 0.03 + w * 0.25, y - lh * 0.82, stroke(pp["red_ink"], lh * 0.06))
        last_lines = (start_y, y, lines)
        y += lh * 0.0
    if redact_last and last_lines:
        y0, y1, lines = last_lines
        num_w = f.measureText(f"{len(rules)}. ")
        for k in range(len(lines)):
            yy = y0 + k * lh
            lw = sum(f.measureText(wd) + f.measureText(" ") for wd, _ in lines[k])
            x0 = mx + w * 0.03 + (num_w if k == 0 else 0)
            c.drawPath(rrect(x0 - fs * 0.1, yy - fs * 0.95, mx + w * 0.03 + lw + fs * 0.2, yy + fs * 0.3, fs * 0.15),
                       fill("#111114", 0.95))
    if blurred:
        c.restore()
    if tape:
        for tx, ang in ((l + w * 0.12, -32), (rr - w * 0.12, 30)):
            _tape(c, tx, t + h * 0.012, w * 0.2, h * 0.05, ang, pp["tape"])
    c.restore()


def ins_rule_paper(p, size):
    W, H = size
    s, c = _surface(size)
    draw_background(c, p.get("bg", "dark_vignette"), W, H, p)
    ph = H * 0.92
    pw = ph * 0.74
    rect = skia.Rect.MakeLTRB(W / 2 - pw / 2, H * 0.05, W / 2 + pw / 2, H * 0.05 + ph)
    draw_paper_notebook(c, rect, p.get("title", ""), p.get("rules", []), red_index=p.get("red_rule_index"),
                        redact_last=bool(p.get("redact_last")), blurred=bool(p.get("blurred")), note=p.get("note"),
                        coffee_stain=bool(p.get("coffee_stain")), bleed_through=bool(p.get("bleed_through")),
                        rotation=float(p.get("rotation", -2)))
    if p.get("hands") is True:
        _paper_hands(c, rect, p, H)
    return s.makeImageSnapshot()


def _paper_hands(c, rect: skia.Rect, p: dict, H: float, back_only=False, front_only=False) -> None:
    u = H / 2160
    sleeve, skin = p.get("sleeve_color", BRAND_GREEN), p.get("skin", "#c9926a")
    pts = ((rect.left() + rect.width() * 0.16, rect.bottom() + 150 * u, 14, False),
           (rect.right() - rect.width() * 0.16, rect.bottom() + 150 * u, -14, True))
    for x, y, ang, mir in pts:
        if not front_only:
            _hand(c, x, y, ang, 1.25 * u, sleeve, skin, "grip", "back", mirror=mir)
        if not back_only:
            _hand(c, x, y, ang, 1.25 * u, sleeve, skin, "grip", "front", mirror=mir)


def ins_hand_holding_paper(p, size):
    W, H = size
    s, c = _surface(size)
    draw_background(c, p.get("bg", "dark_vignette"), W, H, p)
    sub = merged_params(p.get("paper_insert", "rule_paper"))
    ph = H * 0.84
    pw = ph * 0.62
    rect = skia.Rect.MakeLTRB(W / 2 - pw / 2, H * 0.03, W / 2 + pw / 2, H * 0.03 + ph)
    _paper_hands(c, rect, p, H, back_only=True)
    if p.get("paper_insert", "rule_paper") == "missing_poster":
        draw_missing_poster(c, rect, sub)
    else:
        draw_paper_notebook(c, rect, sub.get("title", ""), sub.get("rules", []), red_index=sub.get("red_rule_index"),
                            redact_last=bool(sub.get("redact_last")), note=sub.get("note"),
                            coffee_stain=bool(sub.get("coffee_stain")), rotation=-1.0, tape=False)
    _paper_hands(c, rect, p, H, front_only=True)
    return s.makeImageSnapshot()


# =================================================================== tờ tìm người
def _portrait(photo: str | None, w: int, h: int) -> skia.Image | None:
    if not photo or photo == "blank":
        return None
    cid = photo.split(":", 1)[1] if ":" in photo else photo
    try:
        from . import puppetgen  # type: ignore
        rp = getattr(puppetgen, "render_portrait", None)
        if rp is not None:
            return rp(cid, size=(w, h), expression="neutral")
    except Exception as e:  # noqa: BLE001
        log.info("render_portrait chưa dùng được (%s) — bóng người phẳng", e)
    return None


def _silhouette(c, l, t, r, b, col="#8f99a8") -> None:
    w, h = r - l, b - t
    cx = (l + r) / 2
    c.drawRect(skia.Rect.MakeLTRB(l, t, r, b), _lin((0, t), (0, b), ["#dfe4ea", "#c2cad4"]))
    c.drawPath(rrect(cx - w * 0.36, t + h * 0.66, cx + w * 0.36, b + h * 0.2, w * 0.3), fill(col))
    c.drawRect(skia.Rect.MakeLTRB(cx - w * 0.07, t + h * 0.5, cx + w * 0.07, t + h * 0.7), fill(col))
    c.drawPath(oval(cx, t + h * 0.4, w * 0.2, h * 0.19), fill(col))


def draw_missing_poster(c: skia.Canvas, rect, data: dict) -> None:
    d = data or {}
    r = _rect(rect)
    l, t, rr, b = r.left(), r.top(), r.right(), r.bottom()
    w, h = rr - l, b - t
    cx = (l + rr) / 2
    variant = d.get("variant", "clean")
    paper = d.get("paper", "#f4f1ea")
    pth = skia.Path()
    if variant == "torn":
        rng = random.Random(7)
        pth.moveTo(l, t)
        pth.lineTo(rr, t)
        pth.lineTo(rr, b - h * 0.08)
        x = rr
        while x > l:
            x -= w * rng.uniform(0.03, 0.07)
            pth.lineTo(max(l, x), b - h * rng.uniform(0.0, 0.07))
        pth.lineTo(l, b - h * 0.02)
        pth.close()
    else:
        pth.addRect(skia.Rect.MakeLTRB(l, t, rr, b))
    _shadow(c, pth, h * 0.02, h * 0.01, 0.5)
    c.drawPath(pth, fill(paper))
    c.save()
    c.clipPath(pth, skia.ClipOp.kIntersect, True)
    hb = t + h * 0.13
    c.drawRect(skia.Rect.MakeLTRB(l, t, rr, hb), fill(d.get("header_bg", "#c8352e")))
    text(c, d.get("header", "MISSING PERSON"), cx, t + h * 0.088, h * 0.05, d.get("header_text", "#ffffff"),
         "extrabold", "center", max_w=w * 0.9)
    pw = w * 0.5
    ph = pw * 1.25
    pl, pt = cx - pw / 2, hb + h * 0.035
    c.drawRect(skia.Rect.MakeLTRB(pl - w * 0.015, pt - w * 0.015, pl + pw + w * 0.015, pt + ph + w * 0.015), fill("#dcd6c8"))
    img = None if variant == "blank_photo" else _portrait(d.get("photo"), int(pw), int(ph))
    if img is not None:
        c.drawRect(skia.Rect.MakeLTRB(pl, pt, pl + pw, pt + ph), fill("#e6eaef"))
        c.drawImageRect(img, skia.Rect.MakeLTRB(pl, pt, pl + pw, pt + ph), SAMPLING)
    elif variant == "blank_photo" or d.get("photo") == "blank":
        c.drawRect(skia.Rect.MakeLTRB(pl, pt, pl + pw, pt + ph), fill("#e6e2d8"))
        c.drawCircle(cx, pt + ph / 2, pw * 0.22, fill("#e8833a", 0.85))
        text(c, "?", cx, pt + ph / 2 + pw * 0.11, pw * 0.3, "#ffffff", "extrabold", "center")
    else:
        _silhouette(c, pl, pt, pl + pw, pt + ph)
    y = pt + ph + h * 0.07
    text(c, d.get("name") or d.get("title") or "", cx, y, h * 0.045, "#1a1a1e", "extrabold", "center", max_w=w * 0.88)
    y += h * 0.048
    text(c, d.get("age") or d.get("subtitle") or "", cx, y, h * 0.03, "#33363d", "bold", "center", max_w=w * 0.8)
    f = font(h * 0.024, "regular")
    for ln in wrap_text(d.get("desc", ""), f, w * 0.82)[:2]:
        y += h * 0.038
        text(c, ln, cx, y, h * 0.024, "#6b6f7a", "regular", "center")
    if d.get("datetime"):
        y += h * 0.048
        text(c, d["datetime"], cx, y, h * 0.03, "#c8352e", "bold", "center", max_w=w * 0.85)
    if d.get("phone"):
        y += h * 0.05
        text(c, f"Contact: {d['phone']}", cx, y, h * 0.026, "#1a1a1e", "semibold", "center", max_w=w * 0.85)
    if variant == "crumpled":
        rng = random.Random(4)
        for _ in range(5):
            x0, y0 = l + rng.uniform(0, w), t
            x1, y1 = l + rng.uniform(0, w), b
            c.drawPath(poly([(x0, y0), (x1, y1), (x1 + w * 0.12, y1), (x0 + w * 0.06, y0)]), fill("#000000", 0.05))
            c.drawLine(x0, y0, x1, y1, stroke("#ffffff", 3, 0.5))
        for _ in range(3):
            y0 = t + rng.uniform(0.2, 0.9) * h
            c.drawLine(l, y0, rr, y0 + rng.uniform(-0.05, 0.05) * h, stroke("#000000", 3, 0.12))
    c.restore()
    for tx, ang in ((l + w * 0.06, -35), (rr - w * 0.06, 35)):
        _tape(c, tx, t + h * 0.005, w * 0.22, h * 0.045, ang, d.get("tape", TAPE))


def ins_missing_poster(p, size):
    W, H = size
    s, c = _surface(size)
    draw_background(c, p.get("bg", "blur_location"), W, H, p)
    ph = H * 0.86
    pw = ph * 0.68
    rect = skia.Rect.MakeLTRB(W / 2 - pw / 2, H * 0.07, W / 2 + pw / 2, H * 0.07 + ph)
    c.save()
    c.rotate(float(p.get("rotation", 1.5)), W / 2, H / 2)
    draw_missing_poster(c, rect, p)
    c.restore()
    return s.makeImageSnapshot()


# =================================================================== bản đồ
def draw_map_card(c: skia.Canvas, rect, data: dict) -> None:
    d = data or {}
    r = _rect(rect)
    l, t, rr, b = r.left(), r.top(), r.right(), r.bottom()
    w, h = rr - l, b - t
    card = rrect(l, t, rr, b, h * 0.03)
    _shadow(c, card, h * 0.03, h * 0.015, 0.6)
    c.drawPath(card, fill(d.get("paper", "#efe7d4")))
    c.save()
    c.clipPath(card, skia.ClipOp.kIntersect, True)
    x = l
    k = 0
    while x < rr:
        c.drawRect(skia.Rect.MakeLTRB(x, t, x + w * 0.03, b), fill("#000000", 0.025 if k % 2 else 0.0))
        x += w * 0.03
        k += 1
    rng = random.Random(6)
    for _ in range(16):                              # khối nhà/ruộng mờ
        bx, by = l + rng.uniform(0.05, 0.9) * w, t + rng.uniform(0.2, 0.9) * h
        c.drawPath(rrect(bx, by, bx + rng.uniform(0.03, 0.08) * w, by + rng.uniform(0.03, 0.07) * h, 6),
                   fill("#d6cdb4", 0.8))
    for _ in range(26):
        c.drawCircle(l + rng.uniform(0.03, 0.97) * w, t + rng.uniform(0.2, 0.97) * h, rng.uniform(0.008, 0.016) * w,
                     fill("#a9b98e", 0.8))

    def to_px(pts):
        return [(l + px * w, t + py * h) for px, py in pts]

    water = d.get("water_path") or [[-0.05, 0.86], [0.2, 0.8], [0.45, 0.88], [0.7, 0.74], [1.05, 0.8]]
    road = d.get("road_path") or [[-0.05, 0.58], [0.25, 0.52], [0.55, 0.6], [0.8, 0.5], [1.05, 0.55]]
    if d.get("water_label", True) is not None:
        wp = smooth(to_px(water), close=False)
        c.drawPath(wp, stroke(d.get("water", "#4a86c0"), h * 0.07, 0.9))
        c.drawPath(wp, stroke("#ffffff", h * 0.006, 0.35))
        if d.get("water_label"):
            wx, wy = to_px([water[2]])[0]
            text(c, d["water_label"], wx, wy + h * 0.012, h * 0.03, "#ffffff", "bold", "center")
    rp = smooth(to_px(road), close=False)
    c.drawPath(rp, stroke("#6e6c68", h * 0.085))
    c.drawPath(rp, stroke(d.get("road", "#8c8a86"), h * 0.07))
    dash = stroke(d.get("center_line", "#e3b43a"), h * 0.008)
    dash.setPathEffect(skia.DashPathEffect.Make([h * 0.03, h * 0.025], 0))
    c.drawPath(rp, dash)
    if d.get("road_label"):
        rx, ry = to_px([road[1]])[0]
        f = font(h * 0.028, "bold")
        tw = f.measureText(nfc(d["road_label"]))
        c.drawPath(rrect(rx - tw / 2 - h * 0.02, ry - h * 0.11, rx + tw / 2 + h * 0.02, ry - h * 0.06, h * 0.025), fill("#ffffff", 0.9))
        text(c, d["road_label"], rx, ry - h * 0.074, h * 0.028, "#3a3c42", "bold", "center")
    # tiêu đề
    text(c, (d.get("subtitle") or "").upper(), l + w * 0.04, t + h * 0.07, h * 0.026, "#7a7466", "semibold")
    text(c, d.get("title", ""), l + w * 0.04, t + h * 0.14, h * 0.06, "#2a2a2e", "extrabold", max_w=w * 0.7)
    # điểm đánh dấu
    m = d.get("marker") or {}
    if m:
        mx, my = l + float(m.get("x", 0.6)) * w, t + float(m.get("y", 0.5)) * h
        red = d.get("marker_color", "#d0302a")
        c.drawCircle(mx, my, h * 0.055, fill(red, 0.18))
        c.drawCircle(mx, my, h * 0.03, fill("#ffffff"))
        c.drawCircle(mx, my, h * 0.022, fill(red))
        lx, ly = mx + w * 0.12, my - h * 0.2
        dash = stroke(red, h * 0.006)
        dash.setPathEffect(skia.DashPathEffect.Make([h * 0.015, h * 0.012], 0))
        c.drawLine(mx, my, lx, ly + h * 0.03, dash)
        f = font(h * 0.032, "bold")
        lab = nfc(m.get("label", ""))
        tw = f.measureText(lab)
        lx = min(lx, rr - tw - w * 0.05)
        c.drawPath(rrect(lx - h * 0.02, ly - h * 0.045, lx + tw + h * 0.02, ly + h * 0.03, h * 0.012), fill(red))
        c.drawString(lab, lx, ly + h * 0.004, f, fill("#ffffff"))
    if d.get("tag"):
        f = font(h * 0.028, "bold")
        tw = f.measureText(nfc(d["tag"]))
        c.drawPath(rrect(l + w * 0.04, b - h * 0.11, l + w * 0.04 + tw + h * 0.06, b - h * 0.05, h * 0.03), fill("#3a8a5a"))
        text(c, d["tag"], l + w * 0.04 + h * 0.03, b - h * 0.069, h * 0.028, "#ffffff", "bold")
    c.restore()


def ins_map_card(p, size):
    W, H = size
    s, c = _surface(size)
    draw_background(c, p.get("bg", "smoke_dark"), W, H, p)
    w, h = W * 0.7, H * 0.74
    draw_map_card(c, skia.Rect.MakeXYWH((W - w) / 2, (H - h) / 2, w, h), p)
    return s.makeImageSnapshot()


# =================================================================== đồng hồ treo tường
def ins_wall_clock(p, size):
    W, H = size
    s, c = _surface(size)
    draw_background(c, p.get("bg", "wall_grey"), W, H, p)
    cx, cy, R = W / 2, H / 2, H * 0.4
    c.save()
    if p.get("mirrored"):
        c.translate(cx, 0)
        c.scale(-1, 1)
        c.translate(-cx, 0)
    sh = fill("#000000", 0.45)
    sh.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, R * 0.06))
    c.drawCircle(cx + R * 0.03, cy + R * 0.05, R * 1.02, sh)
    c.drawCircle(cx, cy, R, fill("#16171a"))
    c.drawCircle(cx, cy, R * 0.9, fill(p.get("band_color", BRAND_GREEN)))
    c.drawCircle(cx, cy, R * 0.86, fill("#fbfaf6"))
    for k in range(60):
        a = k / 60 * math.tau
        r0 = R * (0.74 if k % 5 == 0 else 0.79)
        c.drawLine(cx + math.sin(a) * r0, cy - math.cos(a) * r0, cx + math.sin(a) * R * 0.82, cy - math.cos(a) * R * 0.82,
                   stroke("#16171a", R * (0.018 if k % 5 == 0 else 0.007)))
    for n in range(1, 13):
        a = n / 12 * math.tau
        text(c, str(n), cx + math.sin(a) * R * 0.6, cy - math.cos(a) * R * 0.6 + R * 0.06, R * 0.16, "#16171a",
             "bold", "center")
    hr, mi = float(p.get("hour", 3)) % 12, float(p.get("minute", 0))
    ah = (hr + mi / 60) / 12 * math.tau
    am = mi / 60 * math.tau
    c.drawPath(capsule(cx - math.sin(ah) * R * 0.08, cy + math.cos(ah) * R * 0.08, cx + math.sin(ah) * R * 0.42,
                       cy - math.cos(ah) * R * 0.42, R * 0.06, R * 0.045), fill("#16171a"))
    c.drawPath(capsule(cx - math.sin(am) * R * 0.1, cy + math.cos(am) * R * 0.1, cx + math.sin(am) * R * 0.66,
                       cy - math.cos(am) * R * 0.66, R * 0.045, R * 0.03), fill("#16171a"))
    if p.get("second_hand", True):
        asec = float(p.get("second", 38)) / 60 * math.tau
        c.drawLine(cx - math.sin(asec) * R * 0.16, cy + math.cos(asec) * R * 0.16, cx + math.sin(asec) * R * 0.74,
                   cy - math.cos(asec) * R * 0.74, stroke("#d0302a", R * 0.014))
    c.drawCircle(cx, cy, R * 0.035, fill("#d0302a"))
    # cung bóng góc trên-trái
    gl = skia.Path()
    gl.addArc(skia.Rect.MakeLTRB(cx - R * 0.8, cy - R * 0.8, cx + R * 0.8, cy + R * 0.8), 190, 70)
    c.drawPath(gl, stroke("#ffffff", R * 0.06, 0.35))
    c.restore()
    if p.get("frozen"):
        c.drawCircle(cx, cy, R * 0.9, fill("#cfe6f5", 0.35))
        rng = random.Random(3)
        for _ in range(30):
            a = rng.uniform(0, math.tau)
            r0 = rng.uniform(0.4, 0.95) * R
            x0, y0 = cx + math.cos(a) * r0, cy + math.sin(a) * r0
            ln = rng.uniform(0.05, 0.15) * R
            c.drawLine(x0, y0, x0 + math.cos(a + 1.2) * ln, y0 + math.sin(a + 1.2) * ln, stroke("#ffffff", 3, 0.7))
    return s.makeImageSnapshot()


# =================================================================== sổ ghi danh
def ins_ledger_book(p, size):
    W, H = size
    s, c = _surface(size)
    draw_background(c, p.get("bg", "wood_dark"), W, H, p)
    bw, bh = W * 0.78, H * 0.8
    l, t = (W - bw) / 2, (H - bh) / 2
    cover = rrect(l - W * 0.012, t - H * 0.02, l + bw + W * 0.012, t + bh + H * 0.025, H * 0.02)
    _shadow(c, cover, H * 0.03, H * 0.02, 0.65)
    c.drawPath(cover, fill("#8e2620"))
    mid = l + bw / 2
    for side in (0, 1):
        pl = l if side == 0 else mid
        c.drawRect(skia.Rect.MakeLTRB(pl, t, pl + bw / 2, t + bh), _lin((pl, 0), (pl + bw / 2, 0),
                   ["#efe6cf", "#f6efdd"] if side == 0 else ["#f6efdd", "#efe6cf"]))
    c.drawRect(skia.Rect.MakeLTRB(mid - W * 0.02, t, mid + W * 0.02, t + bh),
               _lin((mid - W * 0.02, 0), (mid + W * 0.02, 0), [("#000000", 0.0), ("#000000", 0.25), ("#000000", 0.0)]))
    text(c, p.get("title", "STAFF REGISTER"), l + bw * 0.25, t + bh * 0.09, bh * 0.04, "#8e2620", "extrabold",
         "center", max_w=bw * 0.42)
    cols = p.get("columns", [])
    rows = p.get("rows", [])
    # cột: 2 cột trang trái, phần còn lại trang phải
    split = max(1, (len(cols) + 1) // 2)
    xs = []
    for i in range(len(cols)):
        if i < split:
            xs.append(l + bw * 0.06 + i * (bw * 0.42 / split))
        else:
            xs.append(mid + bw * 0.04 + (i - split) * (bw * 0.42 / max(1, len(cols) - split)))
    hy = t + bh * 0.19
    lh = bh * 0.075
    for side in (0, 1):
        pl = l if side == 0 else mid
        y = hy + lh * 0.35
        while y < t + bh - lh * 0.3:
            c.drawLine(pl + bw * 0.03, y, pl + bw / 2 - bw * 0.03, y, stroke("#a9c4e0", 3))
            y += lh
    for i, col_name in enumerate(cols):
        text(c, col_name, xs[i], hy, bh * 0.03, "#5a5d66", "bold", max_w=bw * 0.2)
    hl = p.get("highlight_row")
    st_ = p.get("strike_row")
    for ri, row in enumerate(rows):
        y = hy + lh * (ri + 1.2)
        if hl is not None and ri == hl:
            for side in (0, 1):
                pl = l if side == 0 else mid
                c.drawRect(skia.Rect.MakeLTRB(pl + bw * 0.03, y - lh * 0.62, pl + bw / 2 - bw * 0.03, y + lh * 0.2),
                           fill("#f3d64e", 0.45))
        for ci, cell in enumerate(row[:len(cols)]):
            is_status = isinstance(cell, str) and cell.isupper() and ci > 0
            text(c, cell, xs[ci], y, bh * 0.036, "#b5332b" if is_status else "#1f2f5a",
                 "bold" if is_status else "semibold", max_w=bw * 0.2)
        if st_ is not None and ri == st_:
            f = font(bh * 0.036, "semibold")
            c.drawLine(xs[0] - bw * 0.01, y - lh * 0.22, xs[0] + f.measureText(nfc(str(row[0]))) + bw * 0.01, y - lh * 0.26,
                       stroke("#d0302a", bh * 0.008))
    return s.makeImageSnapshot()


# =================================================================== tiền / xu / ngăn kéo
def ins_cash_drawer(p, size):
    W, H = size
    s, c = _surface(size)
    u = H / 2160
    c.drawRect(skia.Rect.MakeWH(W, H), fill("#2b2d33"))
    c.drawRect(skia.Rect.MakeLTRB(W * 0.03, H * 0.04, W * 0.97, H * 0.96), fill("#3a3d44"))
    n = int(p.get("note_slots", 4))
    cols = p.get("note_colors", ["#7d5aa6", "#3a78c2", "#c8504a", "#4fa35a"])
    dens = p.get("denominations", ["500K", "200K", "100K", "50K"])
    sw = W * 0.94 / n
    for i in range(n):
        x0 = W * 0.03 + i * sw
        c.drawRect(skia.Rect.MakeLTRB(x0 + 16 * u, H * 0.06, x0 + sw - 16 * u, H * 0.58), fill("#24262b"))
        col = cols[i % len(cols)]
        for k in range(4):                         # chồng tiền giấy
            yy = H * 0.1 + k * 10 * u
            c.drawPath(rrect(x0 + 50 * u, yy, x0 + sw - 50 * u, H * 0.55, 10 * u), fill(shade(col, -0.1 * (3 - k))))
        nl, nr = x0 + 50 * u, x0 + sw - 50 * u
        c.drawPath(rrect(nl + 30 * u, H * 0.16, nr - 30 * u, H * 0.5, 16 * u), stroke(shade(col, 0.35), 6 * u))
        c.drawCircle((nl + nr) / 2, H * 0.36, sw * 0.14, fill(shade(col, 0.25)))
        c.drawCircle((nl + nr) / 2, H * 0.36, sw * 0.1, stroke(shade(col, 0.45), 5 * u))
        text(c, dens[i % len(dens)] if dens else "", (nl + nr) / 2, H * 0.24, 110 * u, "#ffffff", "extrabold", "center",
             max_w=sw * 0.7)
        # kẹp kim loại
        c.drawPath(rrect(x0 + sw * 0.3, H * 0.26, x0 + sw * 0.7, H * 0.32, 20 * u), fill("#c9ced4"))
        c.drawRect(skia.Rect.MakeLTRB(x0 + sw * 0.47, H * 0.32, x0 + sw * 0.53, H * 0.56), fill("#aeb4bb"))
    wells = int(p.get("coin_wells", 4))
    ww = W * 0.94 / wells
    rng = random.Random(4)
    for i in range(wells):
        x0 = W * 0.03 + i * ww
        c.drawPath(rrect(x0 + 20 * u, H * 0.63, x0 + ww - 20 * u, H * 0.93, 60 * u), fill("#1b1c20"))
        for k in range(9):
            cx, cy = x0 + ww * rng.uniform(0.25, 0.75), H * rng.uniform(0.7, 0.86)
            r_ = (70 + i * 10) * u
            c.drawCircle(cx, cy, r_, fill("#b7b9bc" if i % 2 else "#c9a14a"))
            c.drawCircle(cx, cy, r_ * 0.78, stroke(shade("#b7b9bc" if i % 2 else "#c9a14a", 0.3), 5 * u))
    # tay POV nhón xu
    sleeve, skin = p.get("sleeve_color", BRAND_GREEN), p.get("skin", "#c9926a")
    hx, hy = W * 0.55, H * 1.08
    _hand(c, hx, hy, -12, 1.5 * u, sleeve, skin, "pinch", "all")
    tipx, tipy = hand_tip(hx, hy, -12, 1.5 * u, "pinch")
    c.drawCircle(tipx, tipy, 70 * u, fill("#c9a14a"))
    c.drawCircle(tipx, tipy, 54 * u, stroke("#e3c06a", 6 * u))
    c.drawRect(skia.Rect.MakeWH(W, H), _rad(W / 2, H / 2, W * 0.7, [("#000000", 0.0), ("#000000", 0.45)], [0.45, 1]))
    return s.makeImageSnapshot()


def ins_coin_wet(p, size):
    W, H = size
    s, c = _surface(size)
    draw_background(c, p.get("bg", "dark_vignette"), W, H, p)
    cx, cy, R = W / 2, H / 2, H * 0.36
    _shadow(c, circle(cx + R * 0.04, cy + R * 0.06, R), R * 0.08, 0, 0.6)
    c.drawCircle(cx, cy, R, _lin((cx - R, cy - R), (cx + R, cy + R), ["#e6e8ea", "#9ea3a8", "#d4d7da"]))      # viền bạc
    c.drawCircle(cx, cy, R * 0.68, _lin((cx - R, cy - R), (cx + R, cy + R), ["#f0d27a", "#b88a2e", "#e6c46a"]))  # lõi vàng
    c.drawCircle(cx, cy, R * 0.68, stroke("#8a6a2a", R * 0.015))
    for k in range(48):                           # răng cưa viền
        a = k / 48 * math.tau
        c.drawCircle(cx + math.cos(a) * R * 0.9, cy + math.sin(a) * R * 0.9, R * 0.018, fill("#8a8f96"))
    # hoa văn gốc: bông sen cách điệu 8 cánh (không quốc huy)
    for k in range(8):
        a = k / 8 * math.tau
        c.save()
        c.translate(cx, cy - R * 0.3)
        c.rotate(math.degrees(a))
        c.drawPath(oval(0, -R * 0.11, R * 0.04, R * 0.1), fill("#a8822e", 0.8))
        c.restore()
    c.drawCircle(cx, cy - R * 0.3, R * 0.04, fill("#a8822e"))
    text(c, p.get("value", "5000"), cx, cy + R * 0.2, R * 0.32, "#7a5a1e", "extrabold", "center", max_w=R * 1.1)
    text(c, p.get("unit", "CENTS"), cx, cy + R * 0.42, R * 0.12, "#7a5a1e", "bold", "center")
    text(c, p.get("year", "1998"), cx, cy - R * 0.77, R * 0.09, "#5e6268", "bold", "center")
    rng = random.Random(8)
    if p.get("algae", True):
        for _ in range(16):
            a = rng.uniform(math.pi * 0.1, math.pi * 0.9)
            r0 = rng.uniform(0.75, 1.0) * R
            c.drawPath(oval(cx + math.cos(a) * r0, cy + math.sin(a) * r0, rng.uniform(0.05, 0.13) * R,
                            rng.uniform(0.03, 0.07) * R), fill(rng.choice(["#3f6a3a", "#5a7f3e", "#2f4f2e"]), 0.75))
    if p.get("bubbles", True):
        for _ in range(22):
            bx, by = cx + rng.uniform(-1.3, 1.3) * R, cy + rng.uniform(-1.2, 1.2) * R
            br = rng.uniform(0.015, 0.045) * R * 2
            c.drawCircle(bx, by, br, stroke("#cfe6f5", br * 0.18, 0.6))
            c.drawCircle(bx - br * 0.35, by - br * 0.35, br * 0.22, fill("#ffffff", 0.7))
    for _ in range(9):                            # giọt nước trên mặt xu
        dx, dy = cx + rng.uniform(-0.6, 0.6) * R, cy + rng.uniform(-0.6, 0.6) * R
        dr = rng.uniform(0.02, 0.05) * R
        c.drawCircle(dx, dy, dr, fill("#ffffff", 0.25))
        c.drawCircle(dx - dr * 0.3, dy - dr * 0.3, dr * 0.3, fill("#ffffff", 0.7))
    return s.makeImageSnapshot()


def ins_banknote_wet(p, size):
    W, H = size
    s, c = _surface(size)
    draw_background(c, p.get("bg", "blur_location"), W, H, p)
    col = p.get("color", "#b5734a")
    nw, nh = W * 0.66, H * 0.5
    cx, cy = W / 2, H / 2
    c.save()
    c.rotate(float(p.get("rotation", -8)), cx, cy)
    l, t, r, b = cx - nw / 2, cy - nh / 2, cx + nw / 2, cy + nh / 2
    note = rrect(l, t, r, b, nh * 0.03)
    _shadow(c, note, nh * 0.05, nh * 0.03, 0.6)
    c.drawPath(note, _lin((l, t), (r, b), [shade(col, 0.25), col, shade(col, 0.1)]))
    c.drawPath(rrect(l + nw * 0.025, t + nh * 0.04, r - nw * 0.025, b - nh * 0.04, nh * 0.02), stroke(shade(col, 0.45), nh * 0.012))
    rng = random.Random(2)
    for k in range(18):                           # hoa văn guilloche
        pth = skia.Path()
        y0 = t + nh * (0.12 + k * 0.045)
        pth.moveTo(l + nw * 0.04, y0)
        for j in range(12):
            x1 = l + nw * (0.04 + (j + 1) * 0.075)
            pth.quadTo(x1 - nw * 0.037, y0 + (nh * 0.03 if j % 2 else -nh * 0.03), x1, y0)
        c.drawPath(pth, stroke(shade(col, 0.3), 2.5, 0.35))
    # ô chân dung TRỐNG (không mặt người): oval mờ có hoa văn
    c.drawPath(oval(r - nw * 0.24, cy, nw * 0.14, nh * 0.34), fill(shade(col, 0.4), 0.85))
    for k in range(6):
        c.drawPath(oval(r - nw * 0.24, cy, nw * (0.13 - k * 0.018), nh * (0.32 - k * 0.045)), stroke(shade(col, 0.15), 3, 0.5))
    text(c, p.get("value", "20.000"), l + nw * 0.06, t + nh * 0.26, nh * 0.17, "#ffffff", "extrabold", outline=shade(col, -0.45),
         outline_w=nh * 0.012)
    text(c, p.get("value", "20.000"), r - nw * 0.05, b - nh * 0.08, nh * 0.1, shade(col, 0.55), "extrabold", "right")
    text(c, p.get("caption", "LEGAL TENDER"), l + nw * 0.06, t + nh * 0.42, nh * 0.055, shade(col, 0.6), "bold")
    text(c, p.get("serial", "KT 0317298"), l + nw * 0.06, b - nh * 0.1, nh * 0.06, "#7a1e1a", "bold")
    c.restore()
    faded = float(p.get("faded", 0.55))
    if faded > 0:                                 # bạc màu: trộn xám (giữ nền)
        c.saveLayer(None, None)
        c.restore()
    s2, c2 = _surface(size)
    img = s.makeImageSnapshot()
    m = 1 - faded * 0.6
    cm = [0.2126 * (1 - m) + m, 0.7152 * (1 - m), 0.0722 * (1 - m), 0, 0.03,
          0.2126 * (1 - m), 0.7152 * (1 - m) + m, 0.0722 * (1 - m), 0, 0.03,
          0.2126 * (1 - m), 0.7152 * (1 - m), 0.0722 * (1 - m) + m, 0, 0.04,
          0, 0, 0, 1, 0]
    c2.drawImage(img, 0, 0, skia.SamplingOptions(), skia.Paint(ColorFilter=skia.ColorFilters.Matrix(cm)))
    if p.get("drips", True):
        rng = random.Random(6)
        u = H / 2160
        for _ in range(16):                       # giọt nước đọng (giọt hình hạt lệ + điểm sáng)
            x, y = rng.uniform(W * 0.22, W * 0.78), rng.uniform(H * 0.28, H * 0.72)
            r_ = rng.uniform(10, 26) * u
            drop = skia.Path()
            drop.moveTo(x, y - r_ * 2.2)
            drop.cubicTo(x + r_ * 0.3, y - r_ * 1.2, x + r_, y - r_ * 0.6, x + r_, y)
            drop.arcTo(skia.Rect.MakeLTRB(x - r_, y - r_, x + r_, y + r_), 0, 180, False)
            drop.cubicTo(x - r_, y - r_ * 0.6, x - r_ * 0.3, y - r_ * 1.2, x, y - r_ * 2.2)
            c2.drawPath(drop, fill("#e6f2fa", 0.3))
            c2.drawPath(drop, stroke("#ffffff", 2 * u, 0.35))
            c2.drawCircle(x - r_ * 0.35, y - r_ * 0.2, r_ * 0.28, fill("#ffffff", 0.75))
    return s2.makeImageSnapshot()


# =================================================================== dấu chân ướt
def _footprint(c, x, y, ang, sc, left: bool, col="#7f96ab") -> None:
    c.save()
    c.translate(x, y)
    c.rotate(ang)
    if left:
        c.scale(-1, 1)
    p = fill(col, 0.42)
    c.drawPath(oval(0, 40 * sc, 34 * sc, 46 * sc), p)                    # gót
    c.drawPath(oval(8 * sc, -40 * sc, 44 * sc, 58 * sc), p)              # lòng bàn chân trước
    c.drawPath(capsule(-20 * sc, 30 * sc, 0, -30 * sc, 30 * sc, 46 * sc), p)
    for i, (tx, ty, tr) in enumerate(((-26, -112, 16), (-4, -122, 13), (16, -118, 12), (33, -108, 11), (46, -92, 10))):
        c.drawCircle(tx * sc, ty * sc, tr * sc, p)
    c.drawPath(oval(-4 * sc, -60 * sc, 14 * sc, 24 * sc), fill("#ffffff", 0.18))
    c.restore()


def ins_wet_footprints(p, size):
    W, H = size
    s, c = _surface(size)
    draw_background(c, p.get("bg", "tiles_white"), W, H, p)
    u = H / 2160
    steps = int(p.get("steps", 7))
    dx, dy = p.get("direction", [1, -0.6])
    ln = math.hypot(dx, dy) or 1
    dx, dy = dx / ln, dy / ln
    ang = math.degrees(math.atan2(dy, dx)) + 90
    x0, y0 = W * 0.2, H * 0.82
    if p.get("puddle", True):
        rng = random.Random(3)
        pts = [(x0 - 120 * u + math.cos(a) * 330 * u * rng.uniform(0.7, 1.15),
                y0 + 60 * u + math.sin(a) * 170 * u * rng.uniform(0.7, 1.15)) for a in [k / 12 * math.tau for k in range(12)]]
        c.drawPath(smooth(pts), fill("#7f96ab", 0.38))
        c.drawPath(oval(x0 - 180 * u, y0 + 20 * u, 120 * u, 26 * u), fill("#ffffff", 0.35))
    stride = 330 * u
    for i in range(steps):
        side = -1 if i % 2 else 1
        px = x0 + dx * stride * (i + 1) - dy * side * 60 * u
        py = y0 + dy * stride * (i + 1) + dx * side * 60 * u
        _footprint(c, px, py, ang, 1.5 * u * (1 - i * 0.03), i % 2 == 1)
        c.drawCircle(px + 70 * u, py + 30 * u, 8 * u, fill("#7f96ab", 0.4))
    if p.get("cctv"):
        c.drawRect(skia.Rect.MakeWH(W, H), fill("#9aa8a4", 0.25))
    return s.makeImageSnapshot()


# =================================================================== tràng hạt
def ins_prayer_beads(p, size):
    W, H = size
    s, c = _surface(size)
    draw_background(c, p.get("bg", "sidewalk"), W, H, p)
    n = int(p.get("count", 18))
    bead = p.get("bead_color", "#d9cfae")
    cx, cy, rx, ry = W / 2, H * 0.4, H * 0.34, H * 0.26
    pts = [(cx + math.cos(a) * rx * (1 + 0.06 * math.sin(3 * a)), cy + math.sin(a) * ry)
           for a in [k / n * math.tau + 0.3 for k in range(n)]]
    c.drawPath(smooth(pts), stroke("#6b4a32", H * 0.006))
    br = H * 0.04
    for x, y in pts:
        sh = fill("#000000", 0.4)
        sh.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, br * 0.3))
        c.drawCircle(x + br * 0.2, y + br * 0.3, br, sh)
        c.drawCircle(x, y, br, _rad(x - br * 0.35, y - br * 0.35, br * 1.5, [shade(bead, 0.4), bead, shade(bead, -0.35)], [0, 0.45, 1]))
        c.drawCircle(x - br * 0.35, y - br * 0.35, br * 0.22, fill("#ffffff", 0.75))
    gx, gy = cx, cy + ry + br * 0.6
    c.drawCircle(gx, gy, br * 1.4, _rad(gx - br * 0.4, gy - br * 0.4, br * 2, [shade(bead, 0.3), shade(bead, -0.15), shade(bead, -0.45)], [0, 0.5, 1]))
    tas = p.get("tassel", "#c8352e")
    c.drawPath(rrect(gx - br * 0.4, gy + br * 1.2, gx + br * 0.4, gy + br * 2.0, br * 0.2), fill(shade(tas, -0.2)))
    for k in range(13):
        a = (k - 6) * 0.06
        c.drawLine(gx + (k - 6) * br * 0.06, gy + br * 1.9, gx + math.sin(a) * br * 5.5, gy + br * 1.9 + math.cos(a) * br * 5.5,
                   stroke(tas if k % 3 else shade(tas, 0.2), br * 0.16))
    return s.makeImageSnapshot()


# =================================================================== thông báo dán / tin tuyển dụng / chuông / snack
def ins_taped_notice(p, size):
    W, H = size
    s, c = _surface(size)
    draw_background(c, p.get("bg", "shutter"), W, H, p)
    pw, ph = H * 0.62, H * 0.82
    cx, cy = W / 2, H * 0.52
    c.save()
    c.rotate(float(p.get("rotation", -3)), cx, cy)
    l, t, r, b = cx - pw / 2, cy - ph / 2, cx + pw / 2, cy + ph / 2
    paper = rrect(l, t, r, b, 6)
    _shadow(c, paper, ph * 0.02, ph * 0.01, 0.5)
    c.drawPath(paper, fill("#f5f2ea"))
    text(c, p.get("kicker", "NOTICE"), cx, t + ph * 0.13, ph * 0.05, "#33363d", "bold", "center")
    c.drawLine(l + pw * 0.2, t + ph * 0.17, r - pw * 0.2, t + ph * 0.17, stroke("#33363d", 4))
    f = font(ph * 0.085, "extrabold")
    y = t + ph * 0.3
    for ln in wrap_text(p.get("headline", ""), f, pw * 0.84)[:3]:
        text(c, ln, cx, y, ph * 0.085, "#b5332b", "extrabold", "center", max_w=pw * 0.88)
        y += ph * 0.1
    fb = font(ph * 0.04, "regular")
    y += ph * 0.03
    for ln in wrap_text(p.get("body", ""), fb, pw * 0.88)[:5]:
        text(c, ln, cx, y, ph * 0.04, "#33363d", "regular", "center")
        y += ph * 0.055
    if p.get("signature", "The Management"):
        text(c, p.get("signature", "The Management"), r - pw * 0.1, b - ph * 0.08, ph * 0.035, "#5a5d66", "semibold", "right")
    for tx, ang in ((l + pw * 0.08, -30), (r - pw * 0.08, 30)):
        _tape(c, tx, t + ph * 0.01, pw * 0.26, ph * 0.05, ang)
    c.restore()
    return s.makeImageSnapshot()


def ins_newspaper(p, size):
    """Trang báo cũ ngả vàng (tờ báo hư cấu, chữ tiếng Anh): masthead, tít lớn, cột chữ mờ, ô ảnh tối."""
    W, H = size
    s, c = _surface(size)
    draw_background(c, p.get("bg", "wood_dark"), W, H, p)
    pw, ph = W * 0.74, H * 0.88
    cx, cy = W / 2, H * 0.52
    c.save()
    c.rotate(float(p.get("rotation", -2)), cx, cy)
    l, t, r, b = cx - pw / 2, cy - ph / 2, cx + pw / 2, cy + ph / 2
    paper = rrect(l, t, r, b, 4)
    _shadow(c, paper, ph * 0.02, ph * 0.012, 0.55)
    c.drawPath(paper, _lin((l, t), (r, b), ["#e9dfc2", "#d8c9a0", "#c9b688"]))
    m = pw * 0.04
    text(c, p.get("masthead", "THE EVENING LEDGER"), cx, t + ph * 0.11, ph * 0.075, "#26221c", "extrabold", "center",
         max_w=pw - 2 * m)
    c.drawLine(l + m, t + ph * 0.135, r - m, t + ph * 0.135, stroke("#26221c", ph * 0.005))
    text(c, p.get("dateline", "VOL. XII · NO. 214 · LATE EDITION"), cx, t + ph * 0.165, ph * 0.022, "#4a4438", "semibold",
         "center")
    c.drawLine(l + m, t + ph * 0.18, r - m, t + ph * 0.18, stroke("#26221c", ph * 0.002))
    f = font(ph * 0.07, "extrabold")
    y = t + ph * 0.27
    for ln in wrap_text(p.get("headline", "NIGHT CLERK VANISHES FROM 24-HOUR STORE"), f, pw - 2 * m)[:2]:
        text(c, ln, l + m, y, ph * 0.07, "#1d1a15", "extrabold", max_w=pw - 2 * m)
        y += ph * 0.08
    y += ph * 0.01
    col_r = l + pw * 0.62
    photo = skia.Rect.MakeLTRB(col_r + m * 0.6, y - ph * 0.03, r - m, b - m * 2.4)
    c.drawRect(photo, fill("#5f5544"))
    c.drawRect(photo, stroke("#2d281f", ph * 0.004))
    _silhouette(c, photo.left() + photo.width() * 0.2, photo.top() + photo.height() * 0.15,
                photo.right() - photo.width() * 0.2, photo.bottom(), "#3a3329")
    text(c, p.get("photo_caption", "Last seen at 3:00 AM"), photo.centerX(), photo.bottom() + m * 0.8, ph * 0.02,
         "#4a4438", "semibold", "center", max_w=photo.width())
    rnd = random.Random(7)
    ncol = 2
    cw = (col_r - (l + m) - m * 0.6) / ncol
    for k in range(ncol):
        x0 = l + m + k * (cw + m * 0.6)
        yy = y
        while yy < b - m * 1.2:
            wfrac = 0.55 if rnd.random() < 0.12 else 1.0
            c.drawRect(skia.Rect.MakeLTRB(x0, yy, x0 + cw * wfrac, yy + ph * 0.011), fill("#7d725c", 0.85))
            yy += ph * (0.045 if wfrac < 1 else 0.026)
    # nếp gấp giữa + ố vàng
    c.drawLine(l, cy, r, cy, stroke("#a8966c", ph * 0.004, 0.6))
    for _ in range(5):
        c.drawCircle(rnd.uniform(l, r), rnd.uniform(t, b), rnd.uniform(ph * 0.03, ph * 0.08), fill("#b49a5c", 0.12))
    c.restore()
    return s.makeImageSnapshot()


def ins_job_ad_card(p, size):
    W, H = size
    s, c = _surface(size)
    draw_background(c, p.get("bg", "blur_location"), W, H, p)
    cw, ch = H * 1.08, H * 0.78
    cx, cy = W / 2, H / 2
    rng = random.Random(9)
    for _ in range(6):                            # mẩu băng keo bay
        x, y = rng.uniform(W * 0.1, W * 0.9), rng.uniform(H * 0.1, H * 0.9)
        if abs(x - cx) < cw * 0.6:
            x += cw * (0.8 if x > cx else -0.8)
        _tape(c, x, y, rng.uniform(120, 220) * H / 2160, 44 * H / 2160, rng.uniform(-60, 60), a=0.7)
    c.save()
    c.rotate(float(p.get("rotation", -3)), cx, cy)
    l, t, r, b = cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2
    card = rrect(l, t, r, b, ch * 0.03)
    _shadow(c, card, ch * 0.03, ch * 0.015, 0.55)
    c.drawPath(card, fill("#ffffff"))
    c.save()
    c.clipPath(card, skia.ClipOp.kIntersect, True)
    c.drawRect(skia.Rect.MakeLTRB(l, t, r, t + ch * 0.17), fill("#f3c94e"))
    c.restore()
    ix, iy, ir = l + cw * 0.09, t + ch * 0.085, ch * 0.045      # icon túi mua hàng
    c.drawPath(rrect(ix - ir, iy - ir * 0.6, ix + ir, iy + ir, ir * 0.2), fill(BRAND_GREEN))
    c.drawPath(rrect(ix - ir * 0.5, iy - ir * 1.2, ix + ir * 0.5, iy - ir * 0.2, ir * 0.4), stroke(BRAND_GREEN, ir * 0.18))
    text(c, p.get("shop", "24H MART"), ix + ir * 1.7, iy + ch * 0.02, ch * 0.055, "#1a1a1e", "extrabold", max_w=cw * 0.55)
    c.drawPath(rrect(r - cw * 0.2, iy - ch * 0.035, r - cw * 0.05, iy + ch * 0.035, ch * 0.035), fill(BRAND_GREEN))
    text(c, "24H", r - cw * 0.125, iy + ch * 0.018, ch * 0.045, "#ffffff", "extrabold", "center")
    f = font(ch * 0.075, "extrabold")
    y = t + ch * 0.31
    for ln in wrap_text(p.get("title", ""), f, cw * 0.86)[:2]:
        text(c, ln, cx, y, ch * 0.075, "#1a1a1e", "extrabold", "center", max_w=cw * 0.9)
        y += ch * 0.09
    y += ch * 0.02
    c.drawCircle(cx - cw * 0.2, y - ch * 0.02, ch * 0.03, stroke("#33363d", ch * 0.007))
    c.drawLine(cx - cw * 0.2, y - ch * 0.02, cx - cw * 0.2, y - ch * 0.04, stroke("#33363d", ch * 0.006))
    c.drawLine(cx - cw * 0.2, y - ch * 0.02, cx - cw * 0.19, y - ch * 0.015, stroke("#33363d", ch * 0.006))
    text(c, p.get("hours", ""), cx - cw * 0.15, y, ch * 0.05, "#33363d", "bold")
    y += ch * 0.13
    sf = font(ch * 0.08, "extrabold")
    sal = nfc(p.get("salary", ""))
    sw = sf.measureText(sal) + ch * 0.12
    c.drawPath(rrect(cx - sw / 2, y - ch * 0.08, cx + sw / 2, y + ch * 0.035, ch * 0.06), fill("#d0302a"))
    text(c, sal, cx, y, ch * 0.08, "#ffffff", "extrabold", "center")
    text(c, p.get("salary_note", "/ month"), cx, y + ch * 0.085, ch * 0.035, "#5a5d66", "semibold", "center")
    text(c, p.get("footnote", ""), cx, b - ch * 0.05, ch * 0.03, "#8a8d96", "regular", "center", max_w=cw * 0.86)
    c.restore()
    return s.makeImageSnapshot()


def ins_door_chime(p, size):
    W, H = size
    s, c = _surface(size)
    draw_background(c, p.get("bg", "dark_vignette"), W, H, p)
    c.drawRect(skia.Rect.MakeLTRB(0, H * 0.2, W, H * 0.3), _lin((0, H * 0.2), (0, H * 0.3), ["#b9c0c6", "#8b929a"]))
    c.drawRect(skia.Rect.MakeLTRB(0, H * 0.3, W, H), fill("#2a3550", 0.35))
    for x in (W * 0.25, W * 0.75):
        c.drawRect(skia.Rect.MakeLTRB(x - 24, H * 0.3, x + 24, H), fill("#a9b0b6"))
    bw, bh = H * 0.44, H * 0.3
    cx, cy = W / 2, H * 0.3 + bh / 2 + H * 0.02
    box = rrect(cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2, bh * 0.16)
    _shadow(c, box, bh * 0.08, bh * 0.06, 0.6)
    c.drawPath(box, _lin((0, cy - bh / 2), (0, cy + bh / 2), ["#f6f7f8", "#d5d9de"]))
    for i in range(7):
        for j in range(4):
            c.drawCircle(cx - bw * 0.3 + i * bw * 0.075, cy - bh * 0.18 + j * bh * 0.12, bh * 0.025, fill("#7d838a"))
    led = p.get("led", "#d0302a")
    lx, ly = cx + bw * 0.32, cy - bh * 0.18
    c.drawCircle(lx, ly, bh * 0.05, fill(led))
    _glow(c, lx, ly, bh * 0.5, led, 0.8)
    waves = int(p.get("waves", 3))
    for side in (-1, 1):
        for k in range(waves):
            rr = bw * 0.62 + k * bh * 0.32
            arc = skia.Path()
            start = -35 if side > 0 else 145
            arc.addArc(skia.Rect.MakeLTRB(cx - rr, cy - rr, cx + rr, cy + rr), start, 70)
            c.drawPath(arc, stroke("#f4eddf", bh * 0.045, 0.85 - k * 0.22))
    return s.makeImageSnapshot()


def ins_snack_bag(p, size):
    W, H = size
    s, c = _surface(size)
    draw_background(c, p.get("bg", "counter"), W, H, p)
    col = p.get("color", "#d8423a")
    bw, bh = H * 0.7, H * 0.86
    cx, cy = W / 2, H * 0.5
    l, t, r, b = cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2
    pth = skia.Path()
    n = 18
    pth.moveTo(l, t + bh * 0.05)
    for i in range(n + 1):
        pth.lineTo(l + bw * i / n, t + (0 if i % 2 else bh * 0.03))
    pth.cubicTo(r + bw * 0.04, t + bh * 0.35, r + bw * 0.04, t + bh * 0.65, r, b - bh * 0.03)
    for i in range(n, -1, -1):
        pth.lineTo(l + bw * i / n, b - (0 if i % 2 else bh * 0.03))
    pth.cubicTo(l - bw * 0.04, t + bh * 0.65, l - bw * 0.04, t + bh * 0.35, l, t + bh * 0.05)
    pth.close()
    _shadow(c, pth, bh * 0.03, bh * 0.02, 0.5)
    c.drawPath(pth, _lin((l, 0), (r, 0), [shade(col, -0.2), shade(col, 0.15), col, shade(col, -0.3)], [0, 0.35, 0.6, 1]))
    for yy in (t + bh * 0.07, b - bh * 0.07):
        c.drawRect(skia.Rect.MakeLTRB(l, yy - bh * 0.012, r, yy + bh * 0.012), fill(shade(col, -0.25)))
    # chóp sao + chữ tên
    star = []
    sx, sy, sr = cx, t + bh * 0.36, bw * 0.4
    for k in range(24):
        rr_ = sr if k % 2 == 0 else sr * 0.82
        a = k / 24 * math.tau
        star.append((sx + math.cos(a) * rr_, sy + math.sin(a) * rr_ * 0.62))
    c.drawPath(poly(star), fill("#f3c94e"))
    text(c, p.get("name", "CRUNCHY"), cx, sy + bh * 0.03, bh * 0.09, "#ffffff", "extrabold", "center", max_w=bw * 0.72,
         outline="#5a1410", outline_w=bh * 0.014)
    text(c, p.get("flavor", "spicy shrimp"), cx, sy + bh * 0.1, bh * 0.035, "#5a1410", "bold", "center")
    c.drawPath(oval(cx, t + bh * 0.7, bw * 0.3, bh * 0.12), fill("#fff4d8", 0.9))
    rng = random.Random(1)
    for _ in range(9):
        c.drawPath(oval(cx + rng.uniform(-0.2, 0.2) * bw, t + bh * 0.7 + rng.uniform(-0.06, 0.06) * bh, bw * 0.06, bh * 0.025),
                   fill("#e8b84a"))
    c.drawPath(poly([(l + bw * 0.1, t + bh * 0.1), (l + bw * 0.22, t + bh * 0.1), (l + bw * 0.12, b - bh * 0.1),
                     (l + bw * 0.06, b - bh * 0.1)]), fill("#ffffff", 0.18))
    # tem giá
    px, py = r + bw * 0.12, b - bh * 0.18
    c.drawPath(rrect(px - bh * 0.12, py - bh * 0.06, px + bh * 0.16, py + bh * 0.06, bh * 0.02), fill("#ffffff"))
    c.drawPath(rrect(px - bh * 0.12, py - bh * 0.06, px - bh * 0.09, py + bh * 0.06, bh * 0.01), fill("#d0302a"))
    text(c, str(p.get("price", "$1.50")), px + bh * 0.03, py + bh * 0.022, bh * 0.055, "#1a1a1e", "extrabold", "center")
    return s.makeImageSnapshot()


def ins_black_frame_text(p, size):
    W, H = size
    s, c = _surface(size)
    draw_background(c, "dark_gradient", W, H, p)
    if p.get("text"):
        f = font(H * 0.06, "bold")
        lines = wrap_text(p["text"], f, W * 0.7)[:3]
        y = H / 2 - (len(lines) - 1) * H * 0.04 + H * 0.02
        for ln in lines:
            text(c, ln, W / 2, y, H * 0.06, "#f4f1ea", "bold", "center")
            y += H * 0.08
    return s.makeImageSnapshot()


# =================================================================== bảng cửa / tay / tay ma / tủ lạnh / locker / miếu
def ins_door_panel(p, size):
    """Bảng điều khiển cửa tự động gắn tường: màn LED tiêu đề, nút tròn có nhãn (tiếng Anh), tay POV chỉ nút đầu."""
    W, H = size
    s, c = _surface(size)
    u = H / 2160
    draw_background(c, p.get("bg", "dark_vignette"), W, H, p)
    # mép khung cửa kính bên trái (gợi bối cảnh)
    c.drawRect(skia.Rect.MakeLTRB(W * 0.08, 0, W * 0.12, H), _lin((W * 0.08, 0), (W * 0.12, 0), ["#8b929a", "#c9ced4", "#6f767e"]))
    c.drawRect(skia.Rect.MakeLTRB(0, 0, W * 0.08, H), fill("#6a8fb0", 0.12))
    pw, ph = H * 0.6, H * 0.84
    cx, cy = W * 0.5, H * 0.47
    l, t, r, b = cx - pw / 2, cy - ph / 2, cx + pw / 2, cy + ph / 2
    plate = rrect(l, t, r, b, ph * 0.04)
    _shadow(c, plate, ph * 0.03, ph * 0.02, 0.6)
    c.drawPath(plate, _lin((l, t), (r, b), ["#e3e6ea", "#b4bac1", "#d2d6db"]))
    c.drawPath(rrect(l + pw * 0.03, t + pw * 0.03, r - pw * 0.03, b - pw * 0.03, ph * 0.03), stroke("#8c939b", 4 * u))
    for sx, sy in ((l + pw * 0.07, t + pw * 0.07), (r - pw * 0.07, t + pw * 0.07), (l + pw * 0.07, b - pw * 0.07),
                   (r - pw * 0.07, b - pw * 0.07)):
        c.drawCircle(sx, sy, pw * 0.022, fill("#7d848c"))
        c.drawLine(sx - pw * 0.014, sy, sx + pw * 0.014, sy, stroke("#4f555c", 4 * u))
    # màn LED tiêu đề
    dl, dt, dr, db = l + pw * 0.12, t + ph * 0.08, r - pw * 0.12, t + ph * 0.2
    c.drawPath(rrect(dl, dt, dr, db, ph * 0.015), fill("#0e1418"))
    text(c, p.get("title", "AUTO DOOR"), (dl + dr) / 2, (dt + db) / 2 + ph * 0.022, ph * 0.06, "#7cf0a0", "extrabold",
         "center", max_w=(dr - dl) * 0.86)
    _glow(c, (dl + dr) / 2, (dt + db) / 2, (dr - dl) * 0.5, "#7cf0a0", 0.12)
    btns = p.get("buttons") or [{"label": "UNLOCK", "color": "#3cb44b"}, {"label": "LOCK", "color": "#d0302a"}]
    btns = btns[:3]
    n = max(1, len(btns))
    br = ph * (0.085 if n <= 2 else 0.065)
    centers = []
    for i, bt in enumerate(btns):
        bx, by = cx, t + ph * (0.36 + i * (0.6 / n))
        col = bt.get("color", "#3cb44b") if isinstance(bt, dict) else "#3cb44b"
        lab = bt.get("label", "") if isinstance(bt, dict) else str(bt)
        c.drawCircle(bx, by + br * 0.08, br * 1.2, fill("#000000", 0.25))
        c.drawCircle(bx, by, br * 1.18, _lin((bx, by - br), (bx, by + br), ["#9aa1a9", "#5d636a"]))
        c.drawCircle(bx, by, br, _rad(bx - br * 0.3, by - br * 0.35, br * 1.5, [shade(col, 0.35), col, shade(col, -0.35)],
                                      [0, 0.5, 1]))
        c.drawPath(oval(bx - br * 0.25, by - br * 0.45, br * 0.45, br * 0.18), fill("#ffffff", 0.35))
        _glow(c, bx, by, br * 1.8, col, 0.25)
        text(c, lab, bx, by + br * 1.62, ph * 0.042, "#2a2e34", "extrabold", "center", max_w=pw * 0.8)
        centers.append((bx, by))
    # đèn trạng thái nhỏ
    sl = p.get("status_led", btns[-1].get("color", "#d0302a") if isinstance(btns[-1], dict) else "#d0302a")
    c.drawCircle(r - pw * 0.14, b - ph * 0.07, ph * 0.012, fill(sl))
    _glow(c, r - pw * 0.14, b - ph * 0.07, ph * 0.05, sl, 0.7)
    if p.get("pointing", True) and centers:
        tx, ty = centers[0]
        sc = 1.35 * u
        ang = -28
        hx, hy = tx + 600 * u, ty + 600 * u
        _hand(c, hx, hy, ang, sc, p.get("sleeve_color", BRAND_GREEN), p.get("skin", "#c9926a"), "point", "all")
    c.drawRect(skia.Rect.MakeWH(W, H), _rad(W / 2, H / 2, W * 0.7, [("#000000", 0.0), ("#000000", 0.45)], [0.45, 1]))
    return s.makeImageSnapshot()


def _store_wall(c, W, H, u) -> None:
    """Nền trong cửa hàng mờ tối (kệ hàng khối màu nhoè) — dùng cho cận cảnh quầy."""
    c.drawRect(skia.Rect.MakeWH(W, H), _lin((0, 0), (0, H), ["#2c3442", "#161a22"]))
    rng = random.Random(12)
    p = skia.Paint(AntiAlias=True)
    for row in range(3):
        y0 = H * (0.08 + row * 0.14)
        c.drawRect(skia.Rect.MakeLTRB(0, y0 + H * 0.1, W, y0 + H * 0.115), fill("#5a606a", 0.5))
        x = 0.0
        while x < W:
            w_ = rng.uniform(60, 140) * u
            q = fill(rng.choice(["#c8504a", "#3a78c2", "#f3c94e", "#4fa35a", "#e8833a", "#e9e6df"]), 0.35)
            q.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 18 * u))
            c.drawRect(skia.Rect.MakeLTRB(x, y0 + rng.uniform(0, 0.03) * H, x + w_ * 0.8, y0 + H * 0.1), q)
            x += w_
    del p


def ins_hand_grip_counter(p, size):
    """Tay (từ phía sau quầy) bám chặt mép quầy, nhìn từ phía khách: ngón co qua mép, khớp trắng bệch."""
    W, H = size
    s, c = _surface(size)
    u = H / 2160
    _store_wall(c, W, H, u)
    front = p.get("counter_front", BRAND_GREEN)
    top_y, edge_y = H * 0.5, H * 0.6
    c.drawRect(skia.Rect.MakeLTRB(0, top_y, W, edge_y), _lin((0, top_y), (0, edge_y), ["#cfd3d8", "#f4f5f6"]))
    c.drawRect(skia.Rect.MakeLTRB(0, edge_y, W, edge_y + 26 * u), fill("#9aa0a8"))
    c.drawRect(skia.Rect.MakeLTRB(0, edge_y + 26 * u, W, H), _lin((0, edge_y), (0, H), [front, shade(front, -0.35)]))
    for k in range(1, 6):                           # rãnh ốp mặt quầy
        c.drawRect(skia.Rect.MakeLTRB(W * k / 6 - 4 * u, edge_y + 26 * u, W * k / 6 + 4 * u, H), fill(shade(front, -0.45), 0.5))
    sleeve, skin = p.get("sleeve_color", BRAND_GREEN), p.get("skin", "#c9926a")
    # tay vào từ trên (người đứng sau quầy, hơi nhoài ra): cổ tay trên mặt quầy, ngón cuộn qua mép xuống mặt trước
    for hx, mir, ang in ((W * 0.42, False, 172), (W * 0.62, True, 186)):
        _hand(c, hx, edge_y - 470 * u, ang, 1.3 * u, sleeve, skin, "grip", "all", mirror=mir)
    # bóng ngón đổ lên mặt trước + vạch căng
    for hx in (W * 0.42, W * 0.62):
        sh = fill("#000000", 0.35)
        sh.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 20 * u))
        c.drawPath(oval(hx, edge_y + 90 * u, 190 * u, 34 * u), sh)
    for hx in (W * 0.42, W * 0.62):
        for k in range(3):
            a = math.radians(-150 + k * 25)
            c.drawLine(hx + math.cos(a) * 330 * u, edge_y - 330 * u + math.sin(a) * 330 * u,
                       hx + math.cos(a) * 420 * u, edge_y - 330 * u + math.sin(a) * 420 * u, stroke("#ffffff", 10 * u, 0.7))
    c.drawRect(skia.Rect.MakeWH(W, H), _rad(W / 2, H / 2, W * 0.7, [("#000000", 0.0), ("#000000", 0.45)], [0.45, 1]))
    return s.makeImageSnapshot()


def ins_hand_on_floor(p, size):
    """Bàn tay xoè nằm im trên sàn gạch tối (nhìn từ trên), tay áo vào từ trái."""
    W, H = size
    s, c = _surface(size)
    u = H / 2160
    draw_background(c, p.get("bg", "dark_tiles"), W, H, p)
    sleeve, skin = p.get("sleeve_color", "#3a3d44"), p.get("skin", "#c9926a")
    hx, hy, ang = W * 0.4, H * 0.58, 70
    sh = fill("#000000", 0.45)
    sh.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 40 * u))
    c.drawPath(oval(hx + 330 * u, hy - 40 * u, 520 * u, 300 * u), sh)
    c.drawRect(skia.Rect.MakeLTRB(0, hy - 210 * u, hx, hy + 260 * u), sh)
    _hand(c, hx, hy, ang, 1.45 * u, sleeve, skin, "open", "all")
    c.drawRect(skia.Rect.MakeWH(W, H), _rad(W * 0.45, H / 2, W * 0.6, [("#000000", 0.0), ("#000000", 0.6)], [0.35, 1]))
    return s.makeImageSnapshot()


def _ghost_hand(c, x, y, angle, s, skin, nails, curls=(0.25, 0.2, 0.2, 0.25), spread=1.0, arm=1300.0,
                thumb=True) -> None:
    """Tay ma gầy, ngón dài nhiều đốt, móng tối. (x, y) = cổ tay; ngón hướng LÊN rồi xoay `angle` độ.
    curls: độ cong (rad) đốt 2 của từng ngón (trỏ -> út)."""
    dk = shade(skin, -0.22)
    lt = shade(skin, 0.25)
    c.save()
    c.translate(x, y)
    c.rotate(angle)
    c.drawPath(capsule(0, 0, 0, arm * s, 150 * s, 190 * s), fill(skin))             # cẳng tay
    c.drawLine(-30 * s, 80 * s, -10 * s, arm * s, stroke(dk, 6 * s, 0.5))               # gân
    c.drawLine(35 * s, 160 * s, 55 * s, arm * s, stroke(dk, 5 * s, 0.4))
    c.drawPath(smooth([(-95 * s, -10 * s), (-120 * s, -170 * s), (-80 * s, -300 * s), (80 * s, -310 * s),
                       (120 * s, -180 * s), (80 * s, -10 * s)]), fill(skin))           # lòng bàn tay
    for i, cv in enumerate(curls[:4]):
        bx = (-75 + i * 50) * s * spread
        by = (-290 + abs(i - 1.5) * 18) * s
        a0 = math.radians((i - 1.5) * 9 * spread)
        L1 = (210 - abs(i - 1.2) * 30) * s
        L2 = (190 - abs(i - 1.2) * 28) * s
        w = (44 - i * 3) * s
        x1, y1 = bx + math.sin(a0) * L1, by - math.cos(a0) * L1
        a1 = a0 + cv
        x2, y2 = x1 + math.sin(a1) * L2, y1 - math.cos(a1) * L2
        c.drawPath(capsule(bx, by, x1, y1, w * 1.1, w), fill(skin))
        c.drawPath(capsule(x1, y1, x2, y2, w, w * 0.8), fill(skin))
        c.drawCircle(x1, y1, w * 0.62, fill(lt, 0.6))                                    # khớp xương lồi
        c.drawLine(x1 - w * 0.3, y1, x1 + w * 0.3, y1, stroke(dk, 4 * s, 0.7))
        c.save()
        c.translate(x2, y2)
        c.rotate(math.degrees(a1))
        c.drawPath(poly([(-w * 0.38, w * 0.1), (w * 0.38, w * 0.1), (w * 0.2, -w * 0.55), (0, -w * 0.75),
                         (-w * 0.2, -w * 0.55)]), fill(nails))                         # móng nhọn tối
        c.restore()
    if thumb:
        c.drawPath(capsule(-90 * s, -60 * s, -190 * s, -200 * s, 60 * s, 48 * s), fill(skin))
        c.drawPath(capsule(-190 * s, -200 * s, -215 * s, -330 * s, 48 * s, 40 * s), fill(skin))
        c.save()
        c.translate(-215 * s, -330 * s)
        c.rotate(-10)
        c.drawPath(poly([(-15 * s, 4 * s), (15 * s, 4 * s), (8 * s, -24 * s), (0, -32 * s), (-8 * s, -24 * s)]), fill(nails))
        c.restore()
    c.restore()


def _shock_lines(c, cx, cy, r0, r1, n, col, w, a=0.85, start=0.0, span=360.0) -> None:
    for k in range(n):
        ang = math.radians(start + span * (k + 0.5) / n)
        c.drawLine(cx + math.cos(ang) * r0, cy + math.sin(ang) * r0, cx + math.cos(ang) * r1, cy + math.sin(ang) * r1,
                   stroke(col, w, a))


def ins_ghost_hand_ankle(p, size):
    """Tay ma trắng bệch thò ra từ gầm kệ (trái) nắm cổ chân: ống quần xanh, giày trắng, vạch giật mình."""
    W, H = size
    s, c = _surface(size)
    u = H / 2160
    draw_background(c, p.get("bg", "dark_tiles"), W, H, p)
    shoe, pants = p.get("shoe", "#f2f2f0"), p.get("pants", "#3e6aa6")
    ghost, nails = p.get("ghost_skin", "#e4e2dc"), p.get("nails", "#4a4a52")
    # bóng tối gầm kệ bên trái
    c.drawRect(skia.Rect.MakeLTRB(0, 0, W * 0.2, H), _lin((0, 0), (W * 0.2, 0), ["#05060a", ("#05060a", 0.0)]))
    c.drawRect(skia.Rect.MakeLTRB(0, H * 0.06, W * 0.17, H * 0.1), fill("#8a8f96"))
    lx = W * 0.58
    # ống quần + cổ chân + giày
    c.drawPath(poly([(lx - 230 * u, -10), (lx + 230 * u, -10), (lx + 200 * u, H * 0.52), (lx - 200 * u, H * 0.52)]),
               _lin((lx - 230 * u, 0), (lx + 230 * u, 0), [shade(pants, -0.2), pants, shade(pants, -0.3)]))
    for k in range(3):
        c.drawLine(lx - 150 * u + k * 120 * u, H * 0.05, lx - 120 * u + k * 110 * u, H * 0.48, stroke(shade(pants, -0.35), 6 * u, 0.5))
    c.drawPath(rrect(lx - 205 * u, H * 0.49, lx + 205 * u, H * 0.55, 20 * u), fill(shade(pants, -0.25)))
    c.drawPath(rrect(lx - 120 * u, H * 0.54, lx + 120 * u, H * 0.74, 30 * u), fill("#f0f0ee"))              # tất
    sh = fill("#000000", 0.5)
    sh.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 30 * u))
    c.drawPath(oval(lx + 60 * u, H * 0.94, 420 * u, 70 * u), sh)
    sp = skia.Path()
    sp.moveTo(lx - 190 * u, H * 0.72)
    sp.cubicTo(lx - 200 * u, H * 0.82, lx - 180 * u, H * 0.92, lx - 120 * u, H * 0.93)
    sp.lineTo(lx + 400 * u, H * 0.93)
    sp.cubicTo(lx + 480 * u, H * 0.92, lx + 470 * u, H * 0.84, lx + 380 * u, H * 0.8)
    sp.cubicTo(lx + 250 * u, H * 0.76, lx + 160 * u, H * 0.73, lx + 140 * u, H * 0.7)
    sp.close()
    c.drawPath(sp, fill(shoe))
    c.drawRect(skia.Rect.MakeLTRB(lx - 200 * u, H * 0.9, lx + 470 * u, H * 0.935), fill("#c9ccd0"))
    for k in range(4):
        c.drawLine(lx + (150 + k * 50) * u, H * 0.74 + k * 12 * u, lx + (190 + k * 50) * u, H * 0.71 + k * 12 * u,
                   stroke("#9aa0a8", 7 * u))
    # tay ma từ trái, ngón quấn quanh cổ chân
    _ghost_hand(c, lx - 330 * u, H * 0.66, 98, 1.25 * u, ghost, nails, curls=(0.9, 0.95, 0.95, 0.85), spread=1.15,
                arm=2200)
    if p.get("shock_lines", True):
        _shock_lines(c, lx, H * 0.64, 430 * u, 600 * u, 10, "#ffffff", 12 * u, 0.8, start=-80, span=170)
    c.drawRect(skia.Rect.MakeWH(W, H), _rad(W * 0.55, H / 2, W * 0.62, [("#000000", 0.0), ("#000000", 0.6)], [0.4, 1]))
    return s.makeImageSnapshot()


def ins_ghost_hand_coin(p, size):
    """Tay ma xám xanh vươn từ phía khách, đầu ngón trỏ đẩy 1 đồng xu ướt lên mặt quầy; nước nhỏ giọt, vũng nước."""
    W, H = size
    s, c = _surface(size)
    u = H / 2160
    _store_wall(c, W, H, u)
    top = H * 0.42
    c.drawRect(skia.Rect.MakeLTRB(0, top, W, H), _lin((0, top), (0, H), ["#cfd3d8", "#f4f5f6"]))
    c.drawRect(skia.Rect.MakeLTRB(0, top - 18 * u, W, top), fill("#8b929a"))
    ghost = p.get("ghost_skin", "#c9ccd6")
    cx, cy = W * 0.52, H * 0.78
    if p.get("puddle", True):
        rng = random.Random(21)
        pts = [(cx + 120 * u + math.cos(a) * 560 * u * rng.uniform(0.75, 1.1),
                cy - 60 * u + math.sin(a) * 190 * u * rng.uniform(0.75, 1.1)) for a in [k / 14 * math.tau for k in range(14)]]
        c.drawPath(smooth(pts), fill("#8fb0c6", 0.35))
        c.drawPath(oval(cx - 200 * u, cy - 110 * u, 160 * u, 22 * u), fill("#ffffff", 0.4))
    # xu
    R = 170 * u
    c.drawPath(oval(cx + 10 * u, cy + 26 * u, R * 1.05, R * 0.42), fill("#000000", 0.3))
    c.drawPath(oval(cx, cy + 14 * u, R, R * 0.42), fill("#8a6a2a"))
    c.drawPath(oval(cx, cy, R, R * 0.42), _lin((cx - R, cy), (cx + R, cy), ["#f0d27a", "#b88a2e", "#e6c46a"]))
    c.drawPath(oval(cx, cy, R * 0.7, R * 0.29), stroke("#8a6a2a", 5 * u))
    for k in range(5):
        a = math.radians(200 + k * 30)
        c.drawPath(oval(cx + math.cos(a) * R * 0.85, cy + math.sin(a) * R * 0.36, 22 * u, 10 * u), fill("#3f6a3a", 0.8))
    # tay ma từ trên xuống, ngón trỏ duỗi chạm mép xu, các ngón khác co
    _ghost_hand(c, cx + 220 * u, cy - 1130 * u, 204, 1.8 * u, ghost, shade(ghost, -0.55),
                curls=(0.05, 1.2, 1.3, 1.25), spread=0.9, arm=1300, thumb=True)
    if p.get("drips", True):
        rng = random.Random(5)
        for k in range(7):
            x = cx + rng.uniform(-80, 520) * u
            y = rng.uniform(top + 40 * u, cy - 200 * u)
            r_ = rng.uniform(12, 22) * u
            drop = skia.Path()
            drop.moveTo(x, y - r_ * 2.4)
            drop.cubicTo(x + r_ * 0.3, y - r_ * 1.2, x + r_, y - r_ * 0.6, x + r_, y)
            drop.arcTo(skia.Rect.MakeLTRB(x - r_, y - r_, x + r_, y + r_), 0, 180, False)
            drop.cubicTo(x - r_, y - r_ * 0.6, x - r_ * 0.3, y - r_ * 1.2, x, y - r_ * 2.4)
            c.drawPath(drop, fill("#bcd8ea", 0.7))
            c.drawCircle(x - r_ * 0.3, y - r_ * 0.2, r_ * 0.3, fill("#ffffff", 0.85))
    p2 = fill("#9fc4dd", 0.12)
    p2.setBlendMode(skia.BlendMode.kScreen)
    c.drawRect(skia.Rect.MakeWH(W, H), p2)
    c.drawRect(skia.Rect.MakeWH(W, H), _rad(W / 2, H / 2, W * 0.7, [("#000000", 0.0), ("#000000", 0.5)], [0.4, 1]))
    return s.makeImageSnapshot()


def ins_fridge_door_close(p, size):
    """Cận cửa tủ mát kính mờ sương: khung nhôm, tay nắm, chai lon nhoè phía sau, giọt nước đọng.
    handprint=True: vết bàn tay in trên sương. impact_text: chữ tượng thanh tiếng Anh (vd 'BANG!')."""
    W, H = size
    s, c = _surface(size)
    u = H / 2160
    c.drawRect(skia.Rect.MakeWH(W, H), fill("#1a2230"))
    # hàng hoá phía sau (mờ)
    rng = random.Random(31)
    for row in range(3):
        y0 = H * (0.08 + row * 0.31)
        c.drawRect(skia.Rect.MakeLTRB(0, y0 + H * 0.25, W, y0 + H * 0.27), fill("#d9dde2", 0.6))
        x = W * 0.06
        while x < W * 0.94:
            w_ = rng.uniform(110, 170) * u
            col = rng.choice(["#c8504a", "#3a78c2", "#4fa35a", "#f3c94e", "#e8833a", "#e9e6df", "#7d5aa6"])
            hgt = rng.uniform(0.15, 0.22) * H
            q = fill(col, 0.9)
            q.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 26 * u))
            c.drawPath(rrect(x, y0 + H * 0.25 - hgt, x + w_ * 0.78, y0 + H * 0.25, 30 * u), q)
            x += w_
    glow = fill("#dff2ff", 0.25)
    glow.setBlendMode(skia.BlendMode.kScreen)
    c.drawRect(skia.Rect.MakeWH(W, H), glow)
    # sương phủ (dày ở mép dưới + hai bên)
    c.drawRect(skia.Rect.MakeWH(W, H), _lin((0, 0), (0, H), [("#e8f1f6", 0.25), ("#e8f1f6", 0.35), ("#eef5f8", 0.8)],
                                           [0, 0.5, 1]))
    c.drawRect(skia.Rect.MakeWH(W, H), _rad(W / 2, H * 0.45, W * 0.6, [("#eef5f8", 0.0), ("#eef5f8", 0.55)], [0.4, 1]))
    if p.get("handprint"):
        hx, hy = W * 0.46, H * 0.48
        cl = fill("#2a3a50", 0.45)
        c.drawPath(oval(hx, hy, 150 * u, 170 * u), cl)
        for i, (dx, ln) in enumerate(((-120, 230), (-45, 300), (35, 310), (110, 260))):
            c.drawPath(capsule(hx + dx * u, hy - 120 * u, hx + dx * 1.25 * u, hy - (120 + ln) * u, 70 * u, 60 * u), cl)
        c.drawPath(capsule(hx - 140 * u, hy + 20 * u, hx - 300 * u, hy - 110 * u, 80 * u, 66 * u), cl)
        for k in range(10):                        # vệt nước chảy từ vết tay
            x = hx + rng.uniform(-150, 150) * u
            c.drawLine(x, hy + 120 * u, x + rng.uniform(-6, 6) * u, hy + rng.uniform(300, 700) * u, stroke("#2a3a50", 10 * u, 0.35))
    for _ in range(140):                           # giọt đọng
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        r_ = rng.uniform(4, 14) * u
        c.drawCircle(x, y, r_, fill("#ffffff", 0.35))
        c.drawCircle(x - r_ * 0.3, y - r_ * 0.3, r_ * 0.35, fill("#ffffff", 0.8))
    # khung nhôm + gioăng + tay nắm
    fr = 120 * u
    al = _lin((0, 0), (W, 0), ["#9aa1a9", "#d9dde2", "#8b929a"])
    c.drawRect(skia.Rect.MakeLTRB(0, 0, fr, H), al)
    c.drawRect(skia.Rect.MakeLTRB(W - fr, 0, W, H), al)
    c.drawRect(skia.Rect.MakeLTRB(0, 0, W, fr * 0.7), _lin((0, 0), (0, fr * 0.7), ["#d9dde2", "#8b929a"]))
    c.drawRect(skia.Rect.MakeLTRB(0, H - fr * 0.9, W, H), _lin((0, H - fr), (0, H), ["#b4bac1", "#6f767e"]))
    c.drawRect(skia.Rect.MakeLTRB(fr, 0, fr + 16 * u, H), fill("#2b2d33"))
    c.drawRect(skia.Rect.MakeLTRB(W - fr - 16 * u, 0, W - fr, H), fill("#2b2d33"))
    hx = W - fr - 150 * u
    c.drawPath(rrect(hx - 40 * u, H * 0.22, hx + 40 * u, H * 0.78, 40 * u), _lin((hx - 40 * u, 0), (hx + 40 * u, 0),
                                                                              ["#e3e6ea", "#8b929a", "#c9ced4"]))
    for yy in (H * 0.24, H * 0.76):
        c.drawPath(rrect(hx - 30 * u, yy - 20 * u, hx + 90 * u, yy + 20 * u, 12 * u), fill("#8b929a"))
    imp = p.get("impact_text")
    if imp:
        _shock_lines(c, W / 2, H / 2, H * 0.26, H * 0.42, 16, "#ffffff", 14 * u, 0.85)
        text(c, imp, W / 2, H / 2 + H * 0.06, H * 0.17, "#f3c94e", "extrabold", "center", max_w=W * 0.6,
             outline="#1a1a1e", outline_w=H * 0.02)
    return s.makeImageSnapshot()


_LOCKER_ITEMS = {
    "tote_bag_olive": "#6b7a3a", "phone_dark_blue": "#1f2f5a", "black_box": "#1b1b1f",
}


def ins_locker_open(p, size):
    """Tủ locker kim loại mở cửa: kệ trong, đồ vật (túi vải, điện thoại, hộp đen...), cửa có khe thông gió + số tủ."""
    W, H = size
    s, c = _surface(size)
    u = H / 2160
    draw_background(c, p.get("bg", "dark_vignette"), W, H, p)
    body = p.get("color", "#5d7f9a")
    lw, lh = H * 0.62, H * 0.98
    l, t = W * 0.36 - lw / 2, H * 0.03
    r, b = l + lw, t + lh
    # tủ bên cạnh (đóng)
    for k, x0 in enumerate((l - lw * 1.02, r + lw * 0.92 + lw * 0.1)):
        c.drawRect(skia.Rect.MakeLTRB(x0, t, x0 + lw, b), _lin((x0, 0), (x0 + lw, 0), [shade(body, -0.15), body, shade(body, -0.25)]))
        for j in range(6):
            c.drawPath(rrect(x0 + lw * 0.3, t + lh * (0.08 + j * 0.025), x0 + lw * 0.7, t + lh * (0.088 + j * 0.025), 6 * u),
                       fill(shade(body, -0.5)))
        c.drawPath(rrect(x0 + lw * 0.8, t + lh * 0.45, x0 + lw * 0.86, t + lh * 0.55, 8 * u), fill("#c9ced4"))
    _shadow(c, skia.Rect.MakeLTRB(l, t, r, b), 30 * u, 10 * u, 0.5)
    c.drawRect(skia.Rect.MakeLTRB(l, t, r, b), fill(shade(body, -0.1)))
    il, it, ir, ib = l + lw * 0.05, t + lw * 0.05, r - lw * 0.05, b - lw * 0.05
    c.drawRect(skia.Rect.MakeLTRB(il, it, ir, ib), _lin((0, it), (0, ib), ["#1d232b", "#2a323c"]))
    c.drawRect(skia.Rect.MakeLTRB(il, it, il + lw * 0.06, ib), fill("#000000", 0.35))           # thành trái tối
    shelf_y = it + (ib - it) * 0.28
    c.drawRect(skia.Rect.MakeLTRB(il, shelf_y, ir, shelf_y + 26 * u), fill(shade(body, 0.1)))
    c.drawLine(il + (ir - il) * 0.5, it + 60 * u, il + (ir - il) * 0.5, it + 90 * u, stroke("#9aa0a8", 10 * u))   # móc
    items = p.get("items") or list(_LOCKER_ITEMS)
    iw = ir - il
    for k, it_name in enumerate(items[:3]):
        col = _LOCKER_ITEMS.get(it_name, "#7d838a")
        if "bag" in it_name:                         # túi vải treo móc
            bx, by = il + iw * 0.5, it + 90 * u
            c.drawPath(capsule(bx - 90 * u, by + 120 * u, bx, by, 26 * u, 26 * u), stroke(shade(col, -0.2), 1))
            c.drawLine(bx - 110 * u, by + 160 * u, bx, by, stroke(shade(col, -0.2), 22 * u))
            c.drawLine(bx + 110 * u, by + 160 * u, bx, by, stroke(shade(col, -0.2), 22 * u))
            c.drawPath(rrect(bx - 210 * u, shelf_y + 60 * u, bx + 210 * u, shelf_y + 560 * u, 40 * u), fill(col))
            c.drawPath(rrect(bx - 210 * u, shelf_y + 60 * u, bx + 210 * u, shelf_y + 560 * u, 40 * u), stroke(shade(col, -0.3), 8 * u))
            c.drawPath(poly([(bx - 210 * u, shelf_y + 30 * u), (bx + 210 * u, shelf_y + 30 * u), (bx + 200 * u, shelf_y + 90 * u),
                             (bx - 200 * u, shelf_y + 90 * u)]), fill(shade(col, -0.15)))
            c.drawLine(bx - 110 * u, shelf_y + 30 * u, bx - 110 * u, by + 160 * u, stroke(shade(col, -0.2), 22 * u))
            c.drawLine(bx + 110 * u, shelf_y + 30 * u, bx + 110 * u, by + 160 * u, stroke(shade(col, -0.2), 22 * u))
        elif "phone" in it_name:                     # điện thoại úp trên kệ
            px, py = il + iw * 0.22, shelf_y
            c.drawPath(rrect(px - 70 * u, py - 26 * u, px + 70 * u, py, 10 * u), fill(col))
            c.drawPath(rrect(px - 70 * u, py - 26 * u, px + 70 * u, py - 18 * u, 6 * u), fill(shade(col, 0.4)))
            _glow(c, px, py - 30 * u, 120 * u, "#6aa8ff", 0.35)
        else:                                        # hộp đen nhỏ trên kệ
            bx, by = il + iw * 0.75, shelf_y
            c.drawPath(rrect(bx - 110 * u, by - 170 * u, bx + 110 * u, by, 10 * u), fill(col))
            c.drawPath(poly([(bx - 110 * u, by - 170 * u), (bx - 70 * u, by - 200 * u), (bx + 150 * u, by - 200 * u),
                             (bx + 110 * u, by - 170 * u)]), fill(shade(col, 0.25)))
            c.drawPath(poly([(bx + 110 * u, by - 170 * u), (bx + 150 * u, by - 200 * u), (bx + 150 * u, by - 30 * u),
                             (bx + 110 * u, by)]), fill(shade(col, 0.12)))
    # cửa mở (phối cảnh, bản lề phải)
    dw = lw * 0.42
    door = poly([(r, t), (r + dw, t + lh * 0.06), (r + dw, b - lh * 0.06), (r, b)])
    _shadow(c, door, 30 * u, 0, 0.5)
    c.drawPath(door, _lin((r, 0), (r + dw, 0), [shade(body, -0.05), shade(body, 0.12)]))
    for j in range(6):
        y0 = t + lh * (0.1 + j * 0.03)
        c.drawPath(poly([(r + dw * 0.25, y0 + lh * 0.012), (r + dw * 0.8, y0 + lh * 0.03), (r + dw * 0.8, y0 + lh * 0.038),
                         (r + dw * 0.25, y0 + lh * 0.02)]), fill(shade(body, -0.45)))
    num = str(p.get("number", "07"))
    c.drawPath(poly([(r + dw * 0.3, t + lh * 0.34), (r + dw * 0.75, t + lh * 0.355), (r + dw * 0.75, t + lh * 0.42),
                     (r + dw * 0.3, t + lh * 0.415)]), fill("#f2f2f0"))
    text(c, num, r + dw * 0.52, t + lh * 0.403, lh * 0.05, "#1a1a1e", "extrabold", "center", max_w=dw * 0.4)
    c.drawPath(rrect(r + dw * 0.1, t + lh * 0.5, r + dw * 0.18, t + lh * 0.6, 8 * u), fill("#c9ced4"))
    c.drawRect(skia.Rect.MakeLTRB(r - 6 * u, t, r + 10 * u, b), fill(shade(body, -0.45)))
    c.drawRect(skia.Rect.MakeWH(W, H), _rad(W * 0.4, H / 2, W * 0.65, [("#000000", 0.0), ("#000000", 0.55)], [0.4, 1]))
    return s.makeImageSnapshot()


def ins_spirit_shrine(p, size):
    """Miếu nhỏ ven đường lúc chạng vạng: trụ đế, mái cong đỏ, bàn thờ có bát hương + khói, mâm quả, chén nước.
    Không có chữ (tránh chữ Hán/Việt) — chỉ hoạ tiết."""
    W, H = size
    s, c = _surface(size)
    u = H / 2160
    draw_background(c, p.get("bg", "dusk_road"), W, H, p)
    cx = W * 0.5
    base_b = H * 0.95
    sh = fill("#000000", 0.5)
    sh.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 30 * u))
    c.drawPath(oval(cx + 60 * u, base_b, 520 * u, 60 * u), sh)
    # trụ đế
    c.drawRect(skia.Rect.MakeLTRB(cx - 170 * u, H * 0.6, cx + 170 * u, base_b), _lin((cx - 170 * u, 0), (cx + 170 * u, 0),
                                                                                    ["#b8ada0", "#d9cfc2", "#8f857a"]))
    c.drawRect(skia.Rect.MakeLTRB(cx - 240 * u, base_b - 60 * u, cx + 240 * u, base_b), fill("#9a9083"))
    # thân miếu
    bl, br_, bt, bb = cx - 420 * u, cx + 420 * u, H * 0.3, H * 0.6
    c.drawRect(skia.Rect.MakeLTRB(bl - 30 * u, bb - 10 * u, br_ + 30 * u, bb + 50 * u), fill("#c9bfb2"))
    c.drawRect(skia.Rect.MakeLTRB(bl, bt, br_, bb), fill("#e8d9b5"))
    c.drawRect(skia.Rect.MakeLTRB(bl, bt, bl + 60 * u, bb), fill("#c8352e"))
    c.drawRect(skia.Rect.MakeLTRB(br_ - 60 * u, bt, br_, bb), fill("#c8352e"))
    il, ir_, it_, ib = bl + 90 * u, br_ - 90 * u, bt + 60 * u, bb
    c.drawRect(skia.Rect.MakeLTRB(il, it_, ir_, ib), _lin((0, it_), (0, ib), ["#3a1c14", "#5a2a1a"]))
    _glow(c, cx, ib - 120 * u, 420 * u, "#f0a25a", 0.5)
    # mái cong
    roof = skia.Path()
    rt = bt - 230 * u
    roof.moveTo(bl - 170 * u, bt - 10 * u)
    roof.quadTo(bl - 60 * u, bt - 40 * u, bl + 20 * u, bt - 120 * u)
    roof.lineTo(cx, rt)
    roof.lineTo(br_ - 20 * u, bt - 120 * u)
    roof.quadTo(br_ + 60 * u, bt - 40 * u, br_ + 170 * u, bt - 10 * u)
    roof.lineTo(br_ + 110 * u, bt + 30 * u)
    roof.lineTo(bl - 110 * u, bt + 30 * u)
    roof.close()
    c.drawPath(roof, _lin((0, rt), (0, bt + 30 * u), ["#d0402f", "#8f2219"]))
    for k in range(1, 9):
        x = bl - 100 * u + k * (br_ - bl + 200 * u) / 9
        c.drawLine(x, bt + 25 * u, cx + (x - cx) * 0.25, rt + 60 * u, stroke("#7a1c14", 6 * u, 0.6))
    c.drawCircle(cx, rt + 10 * u, 34 * u, fill("#f3c94e"))                    # chóp tròn
    for sx in (bl - 170 * u, br_ + 170 * u):
        c.drawCircle(sx, bt - 22 * u, 26 * u, fill("#f3c94e"))
    # bàn thờ trong miếu
    c.drawRect(skia.Rect.MakeLTRB(il + 30 * u, ib - 110 * u, ir_ - 30 * u, ib - 90 * u), fill("#a0522d"))
    offerings = p.get("offerings") or ["fruit", "water_cups"]
    bx, by = cx, ib - 110 * u
    c.drawPath(poly([(bx - 80 * u, by - 110 * u), (bx + 80 * u, by - 110 * u), (bx + 60 * u, by), (bx - 60 * u, by)]),
               fill("#b88a2e"))                                                    # bát hương
    c.drawPath(oval(bx, by - 110 * u, 80 * u, 18 * u), fill("#8a6a2a"))
    if p.get("incense", True):
        for k in range(3):
            x0 = bx + (k - 1) * 30 * u
            x1 = x0 + (k - 1) * 30 * u
            c.drawLine(x0, by - 110 * u, x1, by - 330 * u, stroke("#c8352e", 9 * u))
            c.drawCircle(x1, by - 330 * u, 9 * u, fill("#ff8a3a"))
            _glow(c, x1, by - 330 * u, 40 * u, "#ff8a3a", 0.9)
            sm = skia.Path()
            sm.moveTo(x1, by - 340 * u)
            yy = by - 340 * u
            xx = x1
            for j in range(6):
                sm.quadTo(xx + (40 if j % 2 else -40) * u, yy - 50 * u, xx + 10 * u, yy - 100 * u)
                xx += 10 * u
                yy -= 100 * u
            c.drawPath(sm, stroke("#e9e6df", 8 * u, 0.4))
    if "fruit" in offerings:
        fx = cx - 210 * u
        c.drawPath(oval(fx, by - 6 * u, 110 * u, 16 * u), fill("#c9ced4"))
        for k, (dx, dy, col) in enumerate(((-50, -40, "#e8833a"), (40, -40, "#f3c94e"), (0, -80, "#4fa35a"),
                                           (-10, -36, "#c8352e"))):
            c.drawCircle(fx + dx * u, by + dy * u, 40 * u, fill(col))
            c.drawCircle(fx + dx * u - 12 * u, by + dy * u - 12 * u, 10 * u, fill("#ffffff", 0.4))
    if "water_cups" in offerings:
        for k in range(3):
            wx = cx + (170 + k * 60) * u
            c.drawPath(poly([(wx - 22 * u, by - 60 * u), (wx + 22 * u, by - 60 * u), (wx + 16 * u, by), (wx - 16 * u, by)]),
                       fill("#f2f2f0"))
            c.drawPath(oval(wx, by - 60 * u, 22 * u, 6 * u), fill("#9fc4dd"))
    c.drawRect(skia.Rect.MakeWH(W, H), _rad(W / 2, H * 0.55, W * 0.7, [("#000000", 0.0), ("#000000", 0.4)], [0.5, 1]))
    return s.makeImageSnapshot()


INSERTS: dict[str, Callable[[dict, tuple[int, int]], skia.Image]] = {
    "phone_chat": ins_phone_chat,
    "phone_lock": ins_phone_lock,
    "phone_bank": ins_phone_bank,
    "cash_drawer": ins_cash_drawer,
    "coin_wet": ins_coin_wet,
    "banknote_wet": ins_banknote_wet,
    "rule_paper": ins_rule_paper,
    "missing_poster": ins_missing_poster,
    "map_card": ins_map_card,
    "wall_clock": ins_wall_clock,
    "ledger_book": ins_ledger_book,
    "hand_holding_paper": ins_hand_holding_paper,
    "wet_footprints": ins_wet_footprints,
    "prayer_beads": ins_prayer_beads,
    "taped_notice": ins_taped_notice,
    "job_ad_card": ins_job_ad_card,
    "door_chime": ins_door_chime,
    "snack_bag": ins_snack_bag,
    "black_frame_text": ins_black_frame_text,
    "newspaper": ins_newspaper,
    "door_panel": ins_door_panel,
    "hand_grip_counter": ins_hand_grip_counter,
    "hand_on_floor": ins_hand_on_floor,
    "ghost_hand_ankle": ins_ghost_hand_ankle,
    "ghost_hand_coin": ins_ghost_hand_coin,
    "fridge_door_close": ins_fridge_door_close,
    "locker_open": ins_locker_open,
    "spirit_shrine": ins_spirit_shrine,
}


# =================================================================== catalog / xuất file
@lru_cache(maxsize=1)
def _catalog() -> dict:
    try:
        return json.loads(CATALOG.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        log.warning("Không đọc được %s: %s", CATALOG, e)
        return {"inserts": []}


def catalog_entry(kind: str) -> dict:
    return next((e for e in _catalog().get("inserts", []) if e["id"] == kind), {})


def merged_params(kind: str, params: dict | None = None) -> dict:
    e = catalog_entry(kind)
    p = copy.deepcopy(e.get("params") or {})
    if e.get("bg") and e["bg"] != "none":
        p.setdefault("bg", e["bg"])
    if e.get("hands") is True:
        p.setdefault("hands", True)
    p.update(params or {})
    return p


def render_insert(kind: str, params: dict | None = None, size: tuple[int, int] = SIZE) -> skia.Image:
    """Vẽ 1 ảnh chèn. kind lạ -> khung đen + cảnh báo (không làm sập render)."""
    fn = INSERTS.get(kind)
    p = merged_params(kind, params)
    if fn is None:
        log.warning("insertgen: không biết kind '%s' — dùng khung đen", kind)
        fn = ins_black_frame_text
    try:
        return fn(p, size)
    except Exception as e:  # noqa: BLE001
        log.warning("insertgen: lỗi khi vẽ '%s': %s — dùng khung đen", kind, e)
        return ins_black_frame_text({}, size)


_TAGS = {  # metadata tìm kiếm (song ngữ) — KHÔNG vẽ vào ảnh
    "phone_chat": ["điện thoại", "tin nhắn", "chat", "phone", "message", "text"],
    "phone_lock": ["điện thoại", "màn khoá", "thông báo", "phone", "lock screen", "notification"],
    "phone_bank": ["điện thoại", "ngân hàng", "số dư", "chuyển khoản", "phone", "bank", "balance", "money"],
    "cash_drawer": ["ngăn kéo tiền", "thu ngân", "tiền", "xu", "cash", "register", "money"],
    "coin_wet": ["đồng xu", "ướt", "rêu", "nước", "coin", "wet"],
    "banknote_wet": ["tờ tiền", "ướt", "bạc màu", "banknote", "money", "wet"],
    "rule_paper": ["nội quy", "luật", "giấy", "ca đêm", "rules", "paper", "night shift"],
    "missing_poster": ["tìm người", "mất tích", "tờ rơi", "poster", "missing"],
    "map_card": ["bản đồ", "sơ đồ", "hiện trường", "map"],
    "wall_clock": ["đồng hồ", "giờ", "3 giờ sáng", "clock", "time"],
    "ledger_book": ["sổ", "danh sách", "nhân viên", "mất tích", "ledger", "register", "book"],
    "hand_holding_paper": ["tay", "cầm giấy", "nội quy", "hands", "paper"],
    "wet_footprints": ["dấu chân", "ướt", "vũng nước", "ma nước", "footprints", "puddle"],
    "prayer_beads": ["tràng hạt", "chuỗi hạt", "tâm linh", "prayer beads", "rosary"],
    "taped_notice": ["thông báo", "đóng cửa", "cửa cuốn", "notice", "closed"],
    "job_ad_card": ["tuyển dụng", "việc làm", "ca đêm", "job ad", "hiring"],
    "door_chime": ["chuông cửa", "báo khách", "tiếng chuông", "door chime", "bell"],
    "snack_bag": ["snack", "bim bim", "đồ ăn vặt", "chips"],
    "black_frame_text": ["khung đen", "chữ", "kinh dị", "black frame", "title card"],
    "newspaper": ["báo cũ", "tờ báo", "tin tức", "newspaper", "news", "headline"],
    "door_panel": ["bảng điều khiển", "cửa tự động", "nút bấm", "khoá cửa", "door panel", "button", "lock"],
    "hand_grip_counter": ["tay", "bám quầy", "căng thẳng", "sợ hãi", "hands", "grip", "counter"],
    "hand_on_floor": ["bàn tay", "trên sàn", "bất tỉnh", "hand", "floor", "unconscious"],
    "ghost_hand_ankle": ["tay ma", "nắm cổ chân", "kinh dị", "ghost hand", "ankle", "grab"],
    "ghost_hand_coin": ["tay ma", "đồng xu", "quầy", "ướt", "ghost hand", "coin", "counter"],
    "fridge_door_close": ["tủ lạnh", "tủ mát", "cửa kính", "sương", "fridge", "cooler", "frost"],
    "locker_open": ["tủ locker", "tủ đồ", "phòng nhân viên", "locker", "staff room"],
    "spirit_shrine": ["miếu", "am thờ", "ven đường", "tâm linh", "hương", "shrine", "incense"],
}
# snake_case prop names (CharacterInShot.prop) mà ảnh chèn có thể thay thế. asset_library.assign chọn insert ĐẦU TIÊN
# (theo tên file) có props ⊇ {prop} -> prop chung ("phone", "paper", "money") chỉ gán cho insert phù hợp nhất.
_PROPS = {
    "phone_chat": ["phone", "smartphone", "phone_chat", "text_message"],
    "phone_lock": ["phone", "phone_lock", "phone_notification"],
    "phone_bank": ["phone_bank", "bank_app", "bank_balance"],
    "cash_drawer": ["cash_drawer", "cash_register", "money"],
    "coin_wet": ["coin", "wet_coin"],
    "banknote_wet": ["banknote", "wet_banknote", "cash"],
    "rule_paper": ["rule_paper", "rules", "paper", "notebook_paper"],
    "hand_holding_paper": ["hand_holding_paper", "paper_in_hands"],
    "missing_poster": ["missing_poster", "poster", "flyer"],
    "map_card": ["map", "map_card"],
    "wall_clock": ["clock", "wall_clock"],
    "ledger_book": ["ledger", "ledger_book", "book", "staff_register"],
    "wet_footprints": ["footprints", "wet_footprints", "puddle"],
    "prayer_beads": ["prayer_beads", "beads", "rosary"],
    "taped_notice": ["notice", "taped_notice", "closed_sign"],
    "job_ad_card": ["job_ad", "job_ad_card", "flyer_job"],
    "door_chime": ["door_chime", "doorbell", "bell"],
    "snack_bag": ["snack", "snack_bag", "chips"],
    "black_frame_text": ["black_frame"],
    "newspaper": ["newspaper", "old_newspaper"],
    "door_panel": ["door_panel", "door_button", "control_panel", "lock_button"],
    "hand_grip_counter": ["hand_grip_counter", "gripping_counter"],
    "hand_on_floor": ["hand_on_floor", "body_on_floor"],
    "ghost_hand_ankle": ["ghost_hand_ankle", "ghost_hand", "grabbed_ankle"],
    "ghost_hand_coin": ["ghost_hand_coin", "ghost_coin"],
    "fridge_door_close": ["fridge", "fridge_door", "cooler_door", "freezer"],
    "locker_open": ["locker", "locker_open", "staff_locker"],
    "spirit_shrine": ["shrine", "spirit_shrine", "roadside_shrine", "incense"],
}
# ảnh chèn có id khác kind (id cũ được tham chiếu trong truyện/test)
ALIASES = {"bao_cu": "newspaper"}


def make_insert(iid: str, kind: str, params: dict | None = None, out_dir: Path = INSERTS_DIR,
                size: tuple[int, int] = SIZE) -> Path:
    """Ghi out_dir/<iid>.png + <iid>.json (asset_library.catalog() tự phát hiện)."""
    out_dir = Path(out_dir)
    img = render_insert(kind, params, size)
    png = out_dir / f"{iid}.png"
    save_png(img, png)
    e = catalog_entry(kind)
    meta = {
        "id": iid,
        "label": e.get("name_vi", iid),
        "label_en": e.get("name_en", iid.replace("_", " ")),
        "tags": _TAGS.get(kind, []),
        "props": _PROPS.get(kind, []),
        "style": "cutout",
        "image": png.name,
        "kind": kind,
        "camera_default": e.get("camera_default", "static"),
        "text_language": "en",
        "params": merged_params(kind, params),
        "provenance": {"kind": "procedural_library" if e.get("library") else "procedural",
                       "generator": "storytoon.render.insertgen",
                       "note": "drawn offline from code; all baked-in text is English and fictional"},
    }
    if e.get("library"):
        meta["library"] = True
    (out_dir / f"{iid}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return png


def make_catalog_inserts(out_dir: Path = INSERTS_DIR, only: list[str] | None = None) -> list[Path]:
    out = []
    for e in _catalog().get("inserts", []):
        if not (e.get("procedural") or e.get("library")) or e["id"] not in INSERTS or (only and e["id"] not in only):
            continue
        out.append(make_insert(e["id"], e["id"], None, out_dir))
    for iid, kind in ALIASES.items():
        if not only or iid in only:
            out.append(make_insert(iid, kind, None, out_dir))
    return out


# lô 2 (thư viện mở rộng, provenance 'procedural_library'): đăng ký kind + màn hình điện thoại + metadata
from . import insertgen_batch2 as _batch2  # noqa: E402

INSERTS.update(_batch2.INSERTS)
SCREENS.update(_batch2.SCREENS)
_TAGS.update(_batch2.TAGS)
_PROPS.update(_batch2.PROPS)

# lô 3 (bùa thắt nút, máy bán hàng, kẹo FREE, ảnh lớp, tranh đèn đường, bản đồ tàu, gõ cửa, tay găng, thông báo app...)
from . import insertgen_batch3 as _batch3  # noqa: E402

INSERTS.update(_batch3.INSERTS)
SCREENS.update(_batch3.SCREENS)
_TAGS.update(_batch3.TAGS)
_PROPS.update(_batch3.PROPS)

# lô 4 (app đếm ngược, màn hình chính, truy nã/livestream, vòng AI, bảng giá sửa máy, billboard, bảng hàng đợi,
# laptop, upload, thẻ nhân viên, đồng hồ cơ, bát mì, túi quần phát sáng, CCTV, tóc giả + nón, USB, xe cộ...)
from . import insertgen_batch4 as _batch4  # noqa: E402

INSERTS.update(_batch4.INSERTS)
SCREENS.update(_batch4.SCREENS)
_TAGS.update(_batch4.TAGS)
_PROPS.update(_batch4.PROPS)

# lô 5 (bệnh viện ca đêm: bảng chuông gọi, đồng hồ 3h, nội quy, lịch trực, sổ chuông, bảng bệnh nhân, điện thoại bàn,
# thuyền giấy, giấy SORRY, ảnh xé, mũ y tá, đồng hồ cài áo, chùm chìa khoá, nút gọi, máy sinh hiệu, dấu chân ướt...)
from . import insertgen_batch5 as _batch5  # noqa: E402

INSERTS.update(_batch5.INSERTS)
_TAGS.update(_batch5.TAGS)
_PROPS.update(_batch5.PROPS)

# lô 6 (bệnh viện phần 2: nội quy trên bàn, lịch trực COPY, vòng tay bệnh nhân, máy sinh hiệu lớn, cuộc gọi/thư/ảnh,
# ổ oxy, túi đồ, ảnh xé người cha, thuyền giấy trên gối, vệt bánh xe ướt)
from . import insertgen_batch6 as _batch6  # noqa: E402

INSERTS.update(_batch6.INSERTS)
SCREENS.update(_batch6.SCREENS)
_TAGS.update(_batch6.TAGS)
_PROPS.update(_batch6.PROPS)

# lô 7 (kinh đô cổ bị vây): gáo dừa, bản đồ than trên ván, bản đồ kinh đô 3 sông (+ trại địch), bản đồ trên tablet,
# sơ đồ đốt móng tường, vết đục ván thuyền, cuốc vào hố cháy, cồng đêm, đầu tượng trong rễ, đèn dầu đất, đuốc tường gạch,
# điện thoại pin 2% / tắt nguồn / ảnh bản đồ
from . import insertgen_batch7 as _batch7  # noqa: E402

_dup7 = (set(_batch7.INSERTS) & set(INSERTS)) | (set(_batch7.SCREENS) & set(SCREENS))
INSERTS.update(_batch7.INSERTS)
SCREENS.update(_batch7.SCREENS)
_TAGS.update(_batch7.TAGS)
_PROPS.update(_batch7.PROPS)


if __name__ == "__main__":  # python -m storytoon.render.insertgen [id ...]
    import sys
    for _p in make_catalog_inserts(only=sys.argv[1:] or None):
        print(_p)
