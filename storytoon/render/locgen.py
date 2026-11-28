"""Sinh nền địa điểm GỐC bằng code (flat 2D vector, không chữ AI) — gói B (docs/ASSET_PLAN.md).

- 8 địa điểm `procedural: true` trong `assets/catalog/locations.json`, mỗi cái có biến thể thời gian
  (`<id>` = biến thể đầu tiên trong `time_variants`, các biến thể còn lại là `<id>__<variant>`).
- Xuất `bg.png` 3840x2160 (plate trống, KHÔNG chữ) + khi có chiều sâu: `bg_far.png` / `bg_mid.png` / `bg_near.png`.
- `location.json`: slot px (tính từ hình học phối cảnh của chính cảnh), `signs[].box` px (chữ thật do
  `location.draw_sign` vẽ lúc nạp), chữ ngược trên kính được "nướng" sẵn (`baked_signs`, location.py chưa hỗ trợ
  `mirrored`), `profile` {label, description, kind, tags, time_variants, archetype...} cho asset_library.catalog().
- 16 địa điểm còn lại của catalog (`procedural: false`) được vẽ bằng `LIBRARY_SCENES` qua
  `make_library_location` (biến thể gốc, provenance `procedural_library`); `make_location` với các id này vẫn
  chỉ ghi stub `location.json` + `flow_prompt` như trước.
- Lô 2 (docs/reference_batch2_analysis.json): 12 cảnh thư viện mới (bep_nha_hang, kho_lanh, san_thuong_binh_minh,
  hem_nha_pho_dien [+__fog], phong_truong_cong_an, phong_icu, cho_co_mai, phong_dieu_tra, ben_go_nha_san,
  tiem_tap_hoa_dem, toa_an, phong_ky_tuc_xa). Catalog có `name_en`/`description_en` -> nhãn & mô tả song ngữ;
  `library_variants: true` -> vẽ mọi biến thể thời gian (biến thể mới 'dawn'/'fog' quy về schema dusk/day).
- Lô 3 (docs/reference_batch3_analysis.md): 10 cảnh thư viện mới (nha_ve_sinh_nu_truong [+__closeup],
  lop_hoc_cu_dem [+__side], truong_hoc_dem, sanh_tu_giay_truong, pho_dan_cu_may_ban_nuoc [+__day], loi_di_dai_dem,
  nha_tro_hai_tang [+__day], phong_chieu_tatami [+__day], bep_quan_mi, phong_ngu_tv_cu). Biến thể khung hình
  'closeup'/'side' là cảnh đêm (TOD_SCHEMA). Chữ nướng vào pixel (số buồng, COLD/HOT, thực đơn, số phòng) là tiếng Anh.
- Lô 4 (docs/reference_batch4_analysis.md): 12 cảnh thư viện mới (tang_trung_tam_dien_thoai [+__angle/__corridor/
  __closed], sanh_thang_cuon, pho_nha_pho_dem [+__rain], ham_xe_b2, quan_mi_xe_day_dem, tiem_giat_24h [+__exterior],
  trung_tam_du_lieu_dem, phong_may_chu, phong_dieu_khien_bao_dong, tram_xe_buyt_binh_minh, song_binh_minh_thanh_pho,
  quan_net_cu). Mặt tiền ki-ốt/tủ rack vẽ trong hệ cục bộ rồi chiếu phối cảnh (`_on_quad`); chữ nướng ghi qua `_Bake`.

Bản quyền: chỉ học phong cách/ngữ pháp từ khung tham khảo; mọi biển hiệu, huy hiệu, màu thương hiệu (palette
`brand_store` xanh lục bảo/kem/cam), chữ đều là bịa mới, chung chung, bối cảnh Việt Nam.
CHỮ: mọi chữ vẽ vào pixel (biển hiệu, decal, lịch, nhãn) là TIẾNG ANH chung chung, không dấu tiếng Việt.
"""
from __future__ import annotations

import json
import logging
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import skia

from ..paths import ASSETS, LOCATIONS
from .skutil import (capsule, circle, color, fill, font, mix, nfc, oval, poly, rrect, save_png, shade,
                     smooth, stroke)

log = logging.getLogger("storytoon.render")

W, H = 3840, 2160
CATALOG = ASSETS / "catalog" / "locations.json"
REF_CHAR_PX = 744.0            # px nền của nhân vật cao chuẩn ở slot.scale = 1 (930 đv × 0.8)
PERSON_M = 1.65                # chiều cao người chuẩn (m) để quy đổi scale từ phối cảnh

BRAND = {"green": "#1f6f5c", "green_dark": "#164f42", "cream": "#f2ead8", "orange": "#e8833a"}
PRODUCTS = ["#d8423a", "#f08a2c", "#f3c94e", "#4fa35a", "#3a78c2", "#c74a9a", "#ffffff"]


# =================================================================== bộ công cụ vẽ
def new_surface(w: int = W, h: int = H) -> skia.Surface:
    s = skia.Surface(w, h)
    s.getCanvas().clear(skia.ColorTRANSPARENT)
    return s


def _cols(cols, a: float = 1.0) -> list[int]:
    out = []
    for cc in cols:
        if isinstance(cc, tuple):
            out.append(color(cc[0], cc[1] * a))
        else:
            out.append(color(cc, a))
    return out


def lin_paint(p0, p1, cols, pos=None, a: float = 1.0) -> skia.Paint:
    sh = skia.GradientShader.MakeLinear([skia.Point(*p0), skia.Point(*p1)], _cols(cols, a), pos)
    return skia.Paint(AntiAlias=True, Shader=sh)


def rad_paint(cx, cy, r, cols, pos=None, a: float = 1.0) -> skia.Paint:
    sh = skia.GradientShader.MakeRadial(skia.Point(cx, cy), max(1.0, r), _cols(cols, a), pos)
    return skia.Paint(AntiAlias=True, Shader=sh)


def vgrad(c, l, t, r, b, cols, pos=None, a: float = 1.0) -> None:
    c.drawRect(skia.Rect.MakeLTRB(l, t, r, b), lin_paint((0, t), (0, b), cols, pos, a))


def hgrad(c, l, t, r, b, cols, pos=None, a: float = 1.0) -> None:
    c.drawRect(skia.Rect.MakeLTRB(l, t, r, b), lin_paint((l, 0), (r, 0), cols, pos, a))


def glow(c, x, y, r, col, a: float = 0.6, screen: bool = True) -> None:
    p = rad_paint(x, y, r, [(col, a), (col, a * 0.35), (col, 0.0)], [0, 0.35, 1])
    if screen:
        p.setBlendMode(skia.BlendMode.kScreen)
    c.drawCircle(x, y, r, p)


def ellipse_glow(c, x, y, rx, ry, col, a: float = 0.5) -> None:
    c.save()
    c.translate(x, y)
    c.scale(1.0, ry / max(rx, 1))
    glow(c, 0, 0, rx, col, a)
    c.restore()


def path_fill(c, path, col, a: float = 1.0) -> None:
    c.drawPath(path, fill(col, a))


def quad(c, pts, col, a: float = 1.0) -> None:
    c.drawPath(poly(pts), fill(col, a))


def box3(c, l, t, r, b, base, top_h: float = 0.0, side_w: float = 0.0, side: str = "right",
         top_dx: float = 0.0) -> None:
    """Khối hộp 'low-poly': mặt trước base, mặt trên base×1.12 (sáng), mặt bên base×0.78."""
    if top_h:
        quad(c, [(l, t), (r, t), (r + top_dx, t - top_h), (l + top_dx, t - top_h)], shade(base, 0.12))
    if side_w:
        if side == "right":
            quad(c, [(r, t), (r + side_w, t - top_h), (r + side_w, b - top_h), (r, b)], shade(base, -0.22))
        else:
            quad(c, [(l, t), (l - side_w, t - top_h), (l - side_w, b - top_h), (l, b)], shade(base, -0.22))
    c.drawRect(skia.Rect.MakeLTRB(l, t, r, b), fill(base))


def reflections(c, l, t, r, b, n: int = 3, a: float = 0.16, seed: int = 1, slant: float = 0.55) -> None:
    """2–3 vệt phản chiếu chéo trắng trên kính."""
    rng = random.Random(seed)
    w, h = r - l, b - t
    c.save()
    c.clipRect(skia.Rect.MakeLTRB(l, t, r, b), skia.ClipOp.kIntersect, True)
    x = l + w * rng.uniform(0.05, 0.25)
    for i in range(n):
        bw = w * rng.uniform(0.05, 0.12) * (0.5 if i % 2 else 1.0)
        dx = h * slant
        quad(c, [(x, b), (x + bw, b), (x + bw + dx, t), (x + dx, t)], "#ffffff", a * (0.6 if i % 2 else 1.0))
        x += bw + w * rng.uniform(0.04, 0.18)
    c.restore()


def stars(c, l, t, r, b, n: int, seed: int = 3, col: str = "#f4f0e0") -> None:
    rng = random.Random(seed)
    for _ in range(n):
        x, y = rng.uniform(l, r), rng.uniform(t, b)
        rr = rng.choice([1.6, 2.2, 2.8, 3.6, 5.0])
        c.drawCircle(x, y, rr, fill(col, rng.uniform(0.35, 0.95)))
        if rr >= 5.0:
            glow(c, x, y, rr * 6, col, 0.25)


def mountains(c, base_y: float, height: float, col: str, seed: int, n: int = 7, l: float = -200,
              r: float = W + 200, sharp: float = 0.5) -> None:
    rng = random.Random(seed)
    pts = [(l, base_y)]
    xs = sorted(rng.uniform(l, r) for _ in range(n * 2))
    for i, x in enumerate(xs):
        y = base_y - height * (rng.uniform(0.55, 1.0) if i % 2 == 0 else rng.uniform(0.15, 0.45))
        pts.append((x, y))
    pts += [(r, base_y), (r, H + 10), (l, H + 10)]
    if sharp >= 0.5:
        path_fill(c, poly(pts), col)
    else:
        path_fill(c, smooth(pts[:-2], close=False) if False else poly(pts), col)


def soft_hills(c, base_y: float, height: float, col: str, seed: int, n: int = 5) -> None:
    rng = random.Random(seed)
    pts = []
    x = -300.0
    while x < W + 300:
        pts.append((x, base_y - height * rng.uniform(0.3, 1.0)))
        x += W / n * rng.uniform(0.6, 1.2)
    p = skia.Path()
    p.moveTo(-300, H + 10)
    p.lineTo(*pts[0])
    for i in range(len(pts) - 1):
        (x0, y0), (x1, y1) = pts[i], pts[i + 1]
        mx = (x0 + x1) / 2
        p.cubicTo(mx, y0, mx, y1, x1, y1)
    p.lineTo(W + 300, H + 10)
    p.close()
    path_fill(c, p, col)


def tree_bare(c, x, y, h, col, seed: int = 5, w: float = 26.0) -> None:
    """Cây trơ cành (đệ quy)."""
    rng = random.Random(seed)

    def branch(x0, y0, ang, ln, wd, depth):
        x1, y1 = x0 + math.cos(ang) * ln, y0 - math.sin(ang) * ln
        c.drawPath(capsule(x0, y0, x1, y1, wd, wd * 0.62), fill(col))
        if depth <= 0 or ln < 30:
            return
        k = rng.randint(2, 3)
        for i in range(k):
            na = ang + rng.uniform(-0.75, 0.75) + (i - (k - 1) / 2) * 0.35
            branch(x1, y1, na, ln * rng.uniform(0.55, 0.78), wd * 0.62, depth - 1)

    branch(x, y, math.pi / 2 + rng.uniform(-0.08, 0.08), h * 0.42, w, 5)


def round_tree(c, x, y, r, col, trunk: str, seed: int = 1) -> None:
    rng = random.Random(seed)
    c.drawRect(skia.Rect.MakeLTRB(x - r * 0.08, y - r * 0.6, x + r * 0.08, y + r * 1.1), fill(trunk))
    for i in range(5):
        a = i / 5 * math.tau
        c.drawCircle(x + math.cos(a) * r * 0.45, y - r * 0.55 + math.sin(a) * r * 0.3, r * rng.uniform(0.55, 0.7),
                     fill(col))
    c.drawCircle(x - r * 0.2, y - r * 0.8, r * 0.35, fill(shade(col, 0.08)))


def power_pole(c, x, top, bottom, col, wd: float = 28.0) -> None:
    c.drawRect(skia.Rect.MakeLTRB(x - wd / 2, top, x + wd / 2, bottom), fill(col))
    for k, cw in ((0, 4.2), (70, 3.0)):
        c.drawRect(skia.Rect.MakeLTRB(x - wd * cw, top + 40 + k, x + wd * cw, top + 58 + k), fill(col))


def sag_wire(c, x0, y0, x1, y1, sag, col, w: float = 4.0, a: float = 1.0) -> None:
    p = skia.Path()
    p.moveTo(x0, y0)
    p.quadTo((x0 + x1) / 2, (y0 + y1) / 2 + sag * 2, x1, y1)
    c.drawPath(p, stroke(col, w, a))


def leaf_emblem(c, cx, cy, r, ring: str, leaf: str) -> None:
    """Huy hiệu gốc của thư viện: chiếc lá trong vòng tròn."""
    c.drawCircle(cx, cy, r, stroke(ring, r * 0.12))
    p = skia.Path()
    p.moveTo(cx - r * 0.45, cy + r * 0.45)
    p.cubicTo(cx - r * 0.55, cy - r * 0.25, cx + r * 0.05, cy - r * 0.6, cx + r * 0.5, cy - r * 0.5)
    p.cubicTo(cx + r * 0.55, cy + r * 0.05, cx + r * 0.15, cy + r * 0.55, cx - r * 0.45, cy + r * 0.45)
    p.close()
    path_fill(c, p, leaf)
    c.drawLine(cx - r * 0.4, cy + r * 0.4, cx + r * 0.25, cy - r * 0.25, stroke(ring if ring != leaf else "#000", r * 0.07, 0.7))


def text_center(c, text, cx, cy, size, col, weight="extrabold", a=1.0, outline: str | None = None,
                max_w: float | None = None, mirrored: bool = False) -> None:
    text = nfc(text)
    f = font(size, weight)
    tw = f.measureText(text)
    if max_w and tw > max_w:
        size *= max_w / tw
        f = font(size, weight)
        tw = f.measureText(text)
    c.save()
    if mirrored:
        c.translate(cx, 0)
        c.scale(-1, 1)
        c.translate(-cx, 0)
    x, y = cx - tw / 2, cy + size * 0.36
    if outline:
        c.drawString(text, x, y, f, stroke(outline, max(2.0, size * 0.1), a))
    c.drawString(text, x, y, f, fill(col, a))
    c.restore()


def darken(c, a: float, col: str = "#000000") -> None:
    c.drawRect(skia.Rect.MakeWH(W, H), fill(col, a))


def tint(s: skia.Surface, col: str, a: float) -> None:
    """Nhân màu (multiply) toàn lớp nhưng GIỮ alpha (vùng kính trong suốt vẫn trong suốt)."""
    img = s.makeImageSnapshot()
    c = s.getCanvas()
    c.clear(skia.ColorTRANSPARENT)
    p = skia.Paint(ColorFilter=skia.ColorFilters.Blend(color(mix("#ffffff", col, a)), skia.BlendMode.kModulate))
    c.drawImage(img, 0, 0, skia.SamplingOptions(), p)


# =================================================================== phối cảnh 1 điểm tụ
@dataclass
class Persp:
    f: float
    cx: float
    cy: float
    cam_h: float

    def p(self, x: float, y: float, z: float) -> tuple[float, float]:
        return self.cx + self.f * x / z, self.cy - self.f * (y - self.cam_h) / z

    def quad(self, pts3) -> skia.Path:
        return poly([self.p(*q) for q in pts3])

    def wall_x(self, x, z0, z1, y0, y1) -> skia.Path:       # mặt đứng song song trục z
        return self.quad([(x, y0, z0), (x, y0, z1), (x, y1, z1), (x, y1, z0)])

    def plane_y(self, y, x0, x1, z0, z1) -> skia.Path:      # sàn/trần/mặt kệ
        return self.quad([(x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)])

    def face_z(self, z, x0, x1, y0, y1) -> skia.Path:       # mặt đối diện camera
        return self.quad([(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)])

    def slot(self, x: float, z: float, **kw) -> dict:
        sx, sy = self.p(x, 0.0, z)
        sc = self.f * PERSON_M / z / REF_CHAR_PX
        return {"x": round(sx), "y": round(sy), "scale": round(sc, 3), **kw}


# =================================================================== kết quả 1 cảnh
@dataclass
class Scene:
    far: skia.Image | None
    mid: skia.Image
    near: skia.Image | None = None
    slots: dict = field(default_factory=dict)
    signs: list = field(default_factory=list)          # [{text, box[px], style}] — location.py vẽ lúc nạp
    baked_signs: list = field(default_factory=list)    # chữ đã nướng vào ảnh (vd. chữ ngược trên kính)
    lights: list = field(default_factory=list)
    floor_y: float = H * 0.87
    parallax: tuple = (0.8, 1.0, 1.15)

    def composite(self, with_signs: bool = False) -> skia.Image:
        s = new_surface()
        c = s.getCanvas()
        c.clear(color("#000000"))
        for im in (self.far, self.mid, self.near):
            if im is not None:
                c.drawImage(im, 0, 0)
        if with_signs:
            from .location import draw_sign
            for sg in self.signs:
                draw_sign(c, sg["text"], sg["box"], sg.get("style", "plain"))
        return s.makeImageSnapshot()


def sign_box(cx: float, cy: float, w: float, h: float) -> list[int]:
    return [round(cx - w / 2), round(cy - h / 2), round(cx + w / 2), round(cy + h / 2)]


def frac_slot(sd: dict) -> dict:
    """Slot phân số catalog -> px."""
    out = {"x": round(sd["x"] * W), "y": round(sd["y"] * H), "scale": sd.get("scale", 1.0)}
    if sd.get("clip_bottom") is not None:
        out["clip_bottom"] = round(sd["clip_bottom"] * H)
    return out


# =================================================================== 1. lối giữa hai kệ (1 điểm tụ)
def _shelf_products(c, P: Persp, side: int, rng: random.Random, x_face: float, z0: float, z1: float,
                    tiers: list[float], night: bool) -> None:
    """Hàng hoá trên mặt kệ hướng ra lối đi (mặt phẳng x = x_face)."""
    for ti, ty in enumerate(tiers[:-1]):
        top = tiers[ti + 1] - 0.06
        z = z1
        items = []
        while z > z0:
            wz = rng.uniform(0.16, 0.42)
            hz = (top - ty) * rng.uniform(0.62, 0.92)
            items.append((max(z0, z - wz), z, hz, rng.choice(PRODUCTS[:-1]), rng.random()))
            z -= wz + rng.uniform(0.0, 0.03)
        for za, zb, hz, col, kind in items:                  # xa trước, gần sau
            f = P.wall_x(side * x_face, za, zb, ty, ty + hz)
            path_fill(c, f, col)
            # nhãn sáng bên trong
            m = (zb - za) * 0.18
            lab = P.wall_x(side * x_face, za + m, zb - m, ty + hz * 0.38, ty + hz * 0.7)
            path_fill(c, lab, shade(col, 0.55) if col != "#ffffff" else "#e8edf2")
            if kind < 0.35:      # chai: nắp vuông
                capz = (za + zb) / 2
                cw = (zb - za) * 0.18
                path_fill(c, P.wall_x(side * x_face, capz - cw, capz + cw, ty + hz, ty + hz + 0.035), shade(col, -0.35))
            # mép tối bên (mặt bên ×0.78)
            path_fill(c, P.wall_x(side * x_face, za, za + (zb - za) * 0.12, ty, ty + hz), shade(col, -0.22))
        # gờ kệ + thẻ giá
        path_fill(c, P.wall_x(side * (x_face + 0.04), z0, z1, ty - 0.05, ty + 0.02), "#f4f6f8" if not night else "#cfd6de")
        z = z1 - 0.2
        while z > z0 + 0.1:
            tag = rng.choice(["#d8423a", "#f3c94e", "#f3c94e", "#ffffff"])
            path_fill(c, P.wall_x(side * (x_face + 0.05), z - 0.09, z, ty - 0.045, ty + 0.0), tag)
            z -= rng.uniform(0.5, 1.1)


def scene_cua_hang_loi_ke(tod: str) -> Scene:
    night = tod == "night"
    P = Persp(f=1500, cx=W / 2, cy=1150, cam_h=1.5)
    ZB, XW, YC = 9.0, 2.15, 3.6
    rng = random.Random(11)
    s = new_surface()
    c = s.getCanvas()
    wall, floor_c, ceil = "#eef0f2", "#d9dde2", "#f4f6f8"
    # trần + lưới ô + đèn huỳnh quang
    path_fill(c, P.plane_y(YC, -XW, XW, 0.4, ZB), ceil)
    for i in range(1, 7):
        x = -XW + i * (2 * XW / 7)
        c.drawPath(P.quad([(x, YC, 0.4), (x, YC, ZB), (x + 0.001, YC, ZB), (x + 0.001, YC, 0.4)]),
                   stroke("#cfd5dc", 5))
    z = 0.8
    while z < ZB:
        a, b = P.p(-XW, YC, z), P.p(XW, YC, z)
        c.drawLine(*a, *b, stroke("#cfd5dc", max(1.5, 7 / z)))
        z += 0.6
    lamps_off = {1, 4} if night else set()
    for i, zc in enumerate([1.6, 3.4, 5.2, 7.0, 8.6]):
        q = P.plane_y(YC - 0.01, -0.35, 0.35, zc - 0.55, zc + 0.55)
        if i in lamps_off:
            path_fill(c, q, "#c8ced6")
        else:
            path_fill(c, q, "#ffffff")
            x, y = P.p(0, YC, zc)
            ellipse_glow(c, x, y + 10, 900 / zc, 260 / zc, "#ffffff", 0.55)
    # tường hai bên
    for side in (-1, 1):
        path_fill(c, P.wall_x(side * XW, 0.4, ZB, 0, YC), shade(wall, -0.08 if side < 0 else -0.05))
    # sàn gạch
    path_fill(c, P.plane_y(0, -XW, XW, 0.4, ZB), floor_c)
    tiles = stroke("#c3c8cf", 4)
    x = -XW
    while x <= XW + 1e-6:
        c.drawLine(*P.p(x, 0, 0.4), *P.p(x, 0, ZB), tiles)
        x += 0.6
    z = 0.6
    while z < ZB:
        c.drawLine(*P.p(-XW, 0, z), *P.p(XW, 0, z), stroke("#c3c8cf", max(1.5, 9 / z)))
        z += 0.6
    # vệt phản chiếu đèn trên sàn
    for zc in [3.4, 5.2, 7.0]:
        x, y = P.p(0, 0, zc)
        ellipse_glow(c, x, y, 380 / zc * 2.2, 70 / zc * 2.2, "#ffffff", 0.35)
    # tường hậu + tủ lạnh 4 khoang
    path_fill(c, P.face_z(ZB, -XW, XW, 0, YC), wall)
    l, t = P.p(-1.9, 2.1, ZB)
    r, b = P.p(1.9, 0.0, ZB)
    c.drawRect(skia.Rect.MakeLTRB(l, t, r, b), fill("#2b2d33"))
    dw = (r - l) / 4
    for i in range(4):
        dl, dr = l + i * dw + 10, l + (i + 1) * dw - 10
        dt, db = t + 12, b - 16
        vgrad(c, dl, dt, dr, db, ["#f4f9fc", "#d9e6ee"] if not night else ["#dfeef8", "#b9cede"])
        rows = 5
        for k in range(rows):
            sy0 = dt + (db - dt) * k / rows
            sy1 = dt + (db - dt) * (k + 1) / rows
            c.drawRect(skia.Rect.MakeLTRB(dl, sy1 - 5, dr, sy1), fill("#9aa6b0"))
            bx = dl + 8
            brng = random.Random(i * 10 + k)
            col = brng.choice(["#3aa3a0", "#4fa35a", "#d8423a", "#f08a2c", "#3a78c2", "#f3c94e"])
            while bx < dr - 18:
                bw = brng.uniform(14, 20)
                bh = (sy1 - sy0) * brng.uniform(0.55, 0.8)
                c.drawPath(rrect(bx, sy1 - 5 - bh, bx + bw, sy1 - 5, 4), fill(col))
                c.drawRect(skia.Rect.MakeLTRB(bx + bw * 0.3, sy1 - 5 - bh - 7, bx + bw * 0.7, sy1 - 5 - bh), fill(shade(col, -0.3)))
                bx += bw + 4
                if brng.random() < 0.18:
                    col = brng.choice(["#3aa3a0", "#4fa35a", "#d8423a", "#f08a2c", "#3a78c2", "#f3c94e"])
        c.drawRect(skia.Rect.MakeLTRB(dr - 16, dt + (db - dt) * 0.35, dr - 9, dt + (db - dt) * 0.6), fill("#c9ced4"))
        reflections(c, dl, dt, dr, db, 2, 0.18, seed=i + 3)
    glow(c, W / 2, (t + b) / 2, (r - l) * 0.7, "#e6f4ff", 0.35 if not night else 0.45)
    # dải đầu xanh lục bảo + biển chữ + đồng hồ tròn
    hl, ht = P.p(-1.9, 2.5, ZB)
    hr, hb = P.p(1.9, 2.1, ZB)
    c.drawRect(skia.Rect.MakeLTRB(hl, ht, hr, hb), fill(BRAND["green"]))
    c.drawRect(skia.Rect.MakeLTRB(hl, hb - 8, hr, hb), fill(BRAND["orange"]))
    ccx, ccy = P.p(0, 3.05, ZB)
    cr = P.f * 0.24 / ZB
    c.drawCircle(ccx, ccy, cr, fill("#ffffff"))
    c.drawCircle(ccx, ccy, cr, stroke("#22252b", cr * 0.16))
    for k in range(12):
        a = k / 12 * math.tau
        c.drawLine(ccx + math.sin(a) * cr * 0.72, ccy - math.cos(a) * cr * 0.72, ccx + math.sin(a) * cr * 0.84,
                   ccy - math.cos(a) * cr * 0.84, stroke("#22252b", 3))
    c.drawLine(ccx, ccy, ccx, ccy - cr * 0.55, stroke("#22252b", 5))
    c.drawLine(ccx, ccy, ccx + cr * 0.5, ccy + cr * 0.1, stroke("#22252b", 5))
    c.drawCircle(ccx, ccy, 5, fill("#d0302a"))
    # kệ gondola hai bên
    tiers = [0.15, 0.55, 0.95, 1.35, 1.75, 1.95]
    for side in (-1, 1):
        xf, xb, z0, z1 = 1.15, 1.75, 1.05, 7.7
        path_fill(c, P.wall_x(side * xb, z0, z1, 0, 1.95), "#cdd2d8" if not night else "#aab2bc")
        for ty in tiers[:-1]:
            path_fill(c, P.plane_y(ty, side * xb, side * xf, z0, z1), "#e3e6ea" if ty < 1.5 else "#d3d8de")
        _shelf_products(c, P, side, rng, xf - 0.02, z0, z1, tiers, night)
        path_fill(c, P.wall_x(side * (xf + 0.03), z0, z1, 0, 0.15), "#9aa1aa")       # chân kệ
        path_fill(c, P.wall_x(side * (xf + 0.03), z0, z1, 1.9, 1.98), "#f6f7f9")     # nẹp đỉnh
        # đầu kệ phía xa (mặt đối diện camera)
        path_fill(c, P.face_z(z1, side * xb, side * xf, 0, 1.98), "#e9ecef")
        # đầu kệ gần camera (lấp mép khung)
        path_fill(c, P.face_z(z0, side * 2.6, side * (xf + 0.03), 0, 1.98), "#f1f3f5" if not night else "#c9d0d8")
        bl, bt = P.p(side * (xf + 0.12), 1.7, z0)
        br, bb = P.p(side * 2.4, 1.05, z0)
        c.drawRect(skia.Rect.MakeLTRB(min(bl, br), bt, max(bl, br), bb), fill(BRAND["orange"]))
        c.drawRect(skia.Rect.MakeLTRB(min(bl, br), bt, max(bl, br), bt + 26), fill(BRAND["green"]))
        for k in range(3):
            yy = bb + 30 + k * 140
            c.drawRect(skia.Rect.MakeLTRB(min(bl, br), yy, max(bl, br), yy + 110),
                       fill(PRODUCTS[(k + (side > 0)) % 6]))
    # biển treo số lối kệ
    sx0, sy0 = P.p(-0.42, 3.05, 4.6)
    sx1, sy1 = P.p(0.42, 2.7, 4.6)
    c.drawLine((sx0 + sx1) / 2 - 60, P.p(0, YC, 4.6)[1], (sx0 + sx1) / 2 - 60, sy0, stroke("#8a9099", 4))
    c.drawLine((sx0 + sx1) / 2 + 60, P.p(0, YC, 4.6)[1], (sx0 + sx1) / 2 + 60, sy0, stroke("#8a9099", 4))
    c.drawPath(rrect(sx0, sy0, sx1, sy1, 10), fill(BRAND["green"]))
    c.drawPath(rrect(sx0 + 8, sy0 + 8, sx1 - 8, sy1 - 8, 8), stroke(BRAND["cream"], 4))
    aisle_box = [round(sx0 + 14), round(sy0 + 12), round(sx1 - 14), round(sy1 - 12)]
    # biển 'sàn ướt' vàng
    wx, wy = P.p(0.95, 0, 5.8)
    wh = P.f * 0.62 / 5.8
    quad(c, [(wx - wh * 0.32, wy), (wx - wh * 0.08, wy - wh), (wx + wh * 0.08, wy - wh), (wx + wh * 0.32, wy)], "#f3c94e")
    quad(c, [(wx - wh * 0.1, wy - wh * 0.62), (wx, wy - wh * 0.8), (wx + wh * 0.1, wy - wh * 0.62)], "#22252b")
    if night:
        tint(s, "#56648a", 0.8)                  # đèn yếu, lạnh, đã tắt bớt
        g = rad_paint(W / 2, 1150, 2400, [("#000000", 0.0), ("#05070d", 0.7)], [0.25, 1])
        c.drawRect(skia.Rect.MakeWH(W, H), g)
        glow(c, W / 2, (t + b) / 2, (r - l) * 0.9, "#cfe6ff", 0.45)     # tủ lạnh vẫn sáng lạnh cuối lối
        for i, zc in enumerate([1.6, 3.4, 5.2, 7.0, 8.6]):
            if i not in lamps_off:
                x, y = P.p(0, YC, zc)
                glow(c, x, y + 20, 700 / zc, "#e8f0ff", 0.35)
    mid = s.makeImageSnapshot()
    slots = {"far_left": P.slot(-0.85, 4.6), "left": P.slot(-0.6, 3.0), "center": P.slot(0.0, 3.0),
             "right": P.slot(0.6, 3.0), "far_right": P.slot(0.85, 4.6), "vanishing": P.slot(0.0, 8.4)}
    hbox = [round(hl + (hr - hl) * 0.22), round(ht + 6), round(hr - (hr - hl) * 0.22), round(hb - 12)]
    signs = [{"text": "COLD DRINKS", "box": hbox, "style": "plain"},
             {"text": "AISLE 3", "box": aisle_box, "style": "plain"}]
    return Scene(None, mid, slots=slots, signs=signs, floor_y=slots["center"]["y"],
                 lights=[{"x": W / 2, "y": 700, "color": "#ffffff"}])


# =================================================================== 2. quầy thu ngân (nhìn từ khách)
def _night_sky(c, t, b, seed=7, top="#0b1022", bottom="#1d2742", n_stars=260):
    vgrad(c, 0, t, W, b, [top, bottom])
    stars(c, 0, t, W, t + (b - t) * 0.7, n_stars, seed)


def _dusk_sky(c, t, b, seed=7):
    vgrad(c, 0, t, W, b, ["#2e3370", "#5a4f8c", "#8a6a9a", "#c98fa6"], [0, 0.45, 0.8, 1])
    rng = random.Random(seed)
    for _ in range(9):
        x, y = rng.uniform(-200, W), rng.uniform(t + (b - t) * 0.15, t + (b - t) * 0.75)
        wl, hh = rng.uniform(500, 1300), rng.uniform(24, 60)
        c.drawPath(rrect(x, y, x + wl, y + hh, hh / 2), fill("#d9a7b5", rng.uniform(0.35, 0.7)))


def _day_sky(c, t, b, top="#9fb4c8", bottom="#dfe6ea"):
    vgrad(c, 0, t, W, b, [top, bottom])
    rng = random.Random(4)
    for _ in range(6):
        x, y = rng.uniform(-200, W), rng.uniform(t + (b - t) * 0.1, t + (b - t) * 0.55)
        wl, hh = rng.uniform(600, 1200), rng.uniform(40, 80)
        c.drawPath(rrect(x, y, x + wl, y + hh, hh / 2), fill("#ffffff", 0.35))


def scene_cua_hang_quay_thu_ngan(tod: str) -> Scene:
    day = tod == "day"
    # ---- far: nhìn ra ngoài qua vách kính
    sf = new_surface()
    c = sf.getCanvas()
    if day:
        _day_sky(c, 0, 1300, "#a9bccc", "#e1e8ec")
        soft_hills(c, 1060, 260, "#8aa37a", 21)
        soft_hills(c, 1180, 200, "#6f8d60", 22)
        c.drawRect(skia.Rect.MakeLTRB(0, 1180, W, 1400), fill("#8c8a86"))
    else:
        _night_sky(c, 0, 1300)
        glow(c, 2400, 470, 160, "#f1ead2", 0.7)
        c.drawCircle(2400, 470, 54, fill("#f1ead2"))
        mountains(c, 1080, 330, "#1a2238", 31, 6)
        mountains(c, 1160, 220, "#0f1424", 32, 8)
        c.drawRect(skia.Rect.MakeLTRB(0, 1160, W, 1400), fill("#0d111d"))
        for x in (700, 2350):
            glow(c, x, 1120, 120, "#f2c46b", 0.55)
    far = sf.makeImageSnapshot()
    # ---- mid: tường, khung kính, quầy, đồ trên quầy
    s = new_surface()
    c = s.getCanvas()
    WT, WB = 250, 1300                   # mép trên/dưới vách kính
    wall = "#dfe3e7" if day else "#c9ced4"
    c.drawRect(skia.Rect.MakeLTRB(0, 0, W, WT), fill(wall))
    vgrad(c, 0, 0, W, WT, [shade(wall, -0.12), wall])
    for x in (600, 1920, 3240):           # đèn trần
        c.drawPath(rrect(x - 300, 40, x + 300, 78, 18), fill("#ffffff"))
        ellipse_glow(c, x, 80, 520, 120, "#ffffff", 0.45)
    c.drawRect(skia.Rect.MakeLTRB(0, WB, W, 1340), fill(shade(wall, -0.1)))
    # kính: ám màu nhẹ + vệt phản chiếu
    c.drawRect(skia.Rect.MakeLTRB(0, WT, W, WB), fill("#9fb7c9" if day else "#24304a", 0.18))
    for i, (gl, gr) in enumerate(((0, 960), (960, 1920), (1920, 2880), (2880, W))):
        reflections(c, gl + 30, WT, gr - 30, WB, 3, 0.11 if not day else 0.18, seed=40 + i)
    mull = "#a9b0b6"
    for x in (0, 960, 1920, 2880, W):
        c.drawRect(skia.Rect.MakeLTRB(x - 22, WT, x + 22, WB), fill(mull))
        c.drawRect(skia.Rect.MakeLTRB(x - 22, WT, x - 10, WB), fill(shade(mull, 0.15)))
    c.drawRect(skia.Rect.MakeLTRB(0, WT - 24, W, WT + 10), fill(mull))
    c.drawRect(skia.Rect.MakeLTRB(0, WB - 14, W, WB + 8), fill(mull))
    # màn CCTV 4 ô treo góc phải
    ml, mt, mr, mb = 3300, 330, 3740, 640
    c.drawLine((ml + mr) / 2, WT - 20, (ml + mr) / 2, mt, stroke("#3a3d44", 14))
    c.drawPath(rrect(ml, mt, mr, mb, 16), fill("#1b1d22"))
    cl, ct, cr_, cb = ml + 22, mt + 22, mr - 22, mb - 40
    cw, ch = (cr_ - cl) / 2, (cb - ct) / 2
    for i in range(4):
        x0, y0 = cl + (i % 2) * cw, ct + (i // 2) * ch
        vgrad(c, x0 + 3, y0 + 3, x0 + cw - 3, y0 + ch - 3, ["#a9b6b2", "#6b7a76"])
        rng = random.Random(i)
        for _ in range(3):
            bx = x0 + rng.uniform(10, cw - 50)
            c.drawRect(skia.Rect.MakeLTRB(bx, y0 + ch * 0.35, bx + rng.uniform(20, 45), y0 + ch - 8), fill("#55625f"))
    c.drawCircle(mr - 30, mb - 20, 7, fill("#3cd06b"))
    # quầy
    CT = 1340
    quad(c, [(0, CT), (W, CT), (W, CT - 46), (0, CT - 46)], "#ffffff")
    c.drawRect(skia.Rect.MakeLTRB(0, CT, W, CT + 30), fill("#d9dcdf"))
    vgrad(c, 0, CT + 30, W, H, [BRAND["green"], shade(BRAND["green"], -0.35)])
    for x in (640, 1280, 2560, 3200):
        c.drawRect(skia.Rect.MakeLTRB(x - 3, CT + 30, x + 3, H), fill(shade(BRAND["green"], -0.25)))
    c.drawRect(skia.Rect.MakeLTRB(0, CT + 70, W, CT + 84), fill(BRAND["orange"]))
    leaf_emblem(c, 1920, 1640, 120, BRAND["cream"], BRAND["cream"])
    # bảng 'VÉ SỐ' kem (chữ do location.draw_sign vẽ)
    vl, vt, vr, vb = 2740, 1510, 3260, 1690
    c.drawPath(rrect(vl, vt, vr, vb, 16), fill(BRAND["orange"]))
    c.drawPath(rrect(vl + 12, vt + 12, vr - 12, vb - 12, 10), stroke(BRAND["cream"], 6))
    # tủ hâm xúc xích kính (trái)
    hl, ht, hr, hb = 360, 1000, 1000, CT - 46
    c.drawPath(rrect(hl, hb - 40, hr, hb, 8), fill("#b8bec4"))
    c.drawPath(rrect(hl + 10, ht, hr - 10, hb - 40, 14), fill("#e9f2f6", 0.45))
    c.drawPath(rrect(hl + 10, ht, hr - 10, hb - 40, 14), stroke("#c9d1d7", 10))
    for k in range(4):
        y = ht + 60 + k * 52
        c.drawLine(hl + 40, y, hr - 40, y, stroke("#e8833a", 8))
        glow(c, (hl + hr) / 2, y, 200, "#ff9a3a", 0.12)
        for j in range(5):
            x = hl + 80 + j * 105
            c.drawPath(capsule(x, y - 16, x + 70, y - 16, 26, 26), fill("#b0553a"))
            c.drawLine(x + 6, y - 22, x + 60, y - 22, stroke("#d07a5a", 5))
    reflections(c, hl + 10, ht, hr - 10, hb - 40, 2, 0.2, seed=5)
    # máy POS
    c.drawPath(rrect(2330, CT - 120, 2610, CT - 46, 10), fill("#2b2d33"))
    quad(c, [(2370, CT - 120), (2570, CT - 120), (2600, CT - 330), (2400, CT - 330)], "#2b2d33")
    quad(c, [(2392, CT - 140), (2552, CT - 140), (2578, CT - 312), (2418, CT - 312)], "#3fd6c2" if day else "#2fb8a6")
    # tủ hấp bánh bao 6 cái
    bl, bt, br, bb = 2760, 930, 3260, CT - 46
    box3(c, bl, bt, br, bb, "#efe4cf", top_h=40, top_dx=-30)
    c.drawPath(rrect(bl + 30, bt + 40, br - 30, bb - 50, 12), fill("#f7f2ea", 0.7))
    for row in range(2):
        for col_ in range(3):
            x = bl + 110 + col_ * 140
            y = bt + 150 + row * 120
            c.drawPath(oval(x, y, 56, 40), fill("#fbf7ef"))
            c.drawPath(oval(x, y - 10, 30, 14), fill("#ffffff"))
            c.drawCircle(x, y - 34, 6, fill("#e3d6bf"))
    reflections(c, bl + 30, bt + 40, br - 30, bb - 50, 2, 0.22, seed=9)
    c.drawRect(skia.Rect.MakeLTRB(bl, bb - 46, br, bb), fill(BRAND["green"]))
    if not day:
        tint(s, "#b9c4d8", 0.25)
    mid = s.makeImageSnapshot()
    cb_ = CT
    slots = {"counter": {"x": 1920, "y": 1728, "scale": 1.0, "clip_bottom": cb_},
             "counter_left": {"x": 1382, "y": 1728, "scale": 1.0, "clip_bottom": cb_},
             "center": {"x": 1920, "y": 1728, "scale": 1.0, "clip_bottom": cb_},
             "customer_left": frac_slot({"x": 0.12, "y": 0.98, "scale": 1.15}),
             "customer_right": frac_slot({"x": 0.86, "y": 0.98, "scale": 1.15})}
    signs = [{"text": "MINI MART 24H", "box": sign_box(1040, 1600, 820, 180), "style": "white_board"},
             {"text": "LOTTERY", "box": [vl + 30, vt + 22, vr - 30, vb - 22], "style": "plain"}]
    return Scene(far, mid, slots=slots, signs=signs, floor_y=1728, parallax=(0.85, 1.0, 1.15))


# =================================================================== 3. cửa kính nhìn từ trong
def _outside_lot(c, day: bool, horizon: float = 1120) -> None:
    if day:
        _day_sky(c, 0, horizon, "#8d9aab", "#cfd6dc")
        soft_hills(c, horizon - 20, 220, "#7f9a6a", 51)
        ground = "#7d7b77"
    else:
        _night_sky(c, 0, horizon, seed=12, n_stars=200)
        mountains(c, horizon - 10, 260, "#141b2e", 52, 6)
        mountains(c, horizon + 10, 150, "#0f1424", 53, 9)
        ground = "#1a1f2b"
    vgrad(c, 0, horizon, W, H, [ground, shade(ground, 0.06 if not day else -0.1)])
    # vạch đỗ xe phối cảnh
    P = Persp(f=1400, cx=W / 2, cy=horizon, cam_h=1.4)
    for x in (-6, -3.5, -1, 1.5, 4, 6.5):
        a, b = P.p(x, 0, 6.0), P.p(x + 0.4, 0, 14.0)
        c.drawLine(*a, *b, stroke("#e9e9e4" if day else "#8f949e", 7, 0.8))
    a, b = P.p(-9, 0, 6.0), P.p(9, 0, 6.0)
    c.drawLine(*a, *b, stroke("#e9e9e4" if day else "#8f949e", 7, 0.8))
    # cột điện + dây võng
    pc = "#3a3a40" if day else "#07090f"
    for x, top in ((620, 420), (3280, 380)):
        power_pole(c, x, top, horizon + 30, pc, 22)
    sag_wire(c, -50, 520, 620, 470, 60, pc, 4)
    sag_wire(c, 620, 470, 3280, 430, 140, pc, 4)
    sag_wire(c, 620, 540, 3280, 500, 160, pc, 3)
    sag_wire(c, 3280, 430, W + 50, 470, 50, pc, 4)
    # mái chờ xe buýt
    sl, sr = 1060, 1420
    c.drawRect(skia.Rect.MakeLTRB(sl, 930, sr, 960), fill("#5d6672" if day else "#20283a"))
    for x in (sl + 20, sr - 20):
        c.drawRect(skia.Rect.MakeLTRB(x - 7, 960, x + 7, horizon + 40), fill("#5d6672" if day else "#20283a"))
    c.drawRect(skia.Rect.MakeLTRB(sl + 40, 1100, sr - 40, 1116), fill("#5d6672" if day else "#20283a"))
    # đèn đường
    lx = 2720
    c.drawRect(skia.Rect.MakeLTRB(lx - 9, 560, lx + 9, horizon + 60), fill(pc))
    c.drawPath(capsule(lx, 566, lx - 130, 590, 14, 12), fill(pc))
    if not day:
        glow(c, lx - 140, 600, 330, "#ffd98a", 0.75)
        ellipse_glow(c, lx - 140, horizon + 120, 520, 110, "#ffd98a", 0.35)


def scene_cua_hang_cua_kinh_tu_trong(tod: str) -> Scene:
    day = tod == "day"
    sf = new_surface()
    _outside_lot(sf.getCanvas(), day)
    far = sf.makeImageSnapshot()
    s = new_surface()
    c = s.getCanvas()
    interior = "#cfd5da"
    GT, GB, GL, GR = 230, 1690, 260, W - 260
    # trần + tường hai bên + sàn
    vgrad(c, 0, 0, W, GT, ["#9aa2aa", "#b9c0c6"])
    for x in (900, 1920, 2940):
        c.drawPath(rrect(x - 260, 60, x + 260, 96, 16), fill("#ffffff"))
        ellipse_glow(c, x, 98, 420, 110, "#ffffff", 0.35)
    c.drawRect(skia.Rect.MakeLTRB(0, GT, GL, GB), fill(shade(interior, -0.12)))
    c.drawRect(skia.Rect.MakeLTRB(GR, GT, W, GB), fill(shade(interior, -0.12)))
    Pf = Persp(f=1500, cx=W / 2, cy=1150, cam_h=1.5)
    vgrad(c, 0, GB, W, H, ["#d9dde2", "#c7ccd2"])
    for x in range(-8, 9):
        c.drawLine(*Pf.p(x * 0.6, 0, 3.2), *Pf.p(x * 0.6, 0, 1.0), stroke("#b9bfc6", 4))
    for z in (1.2, 1.5, 1.9, 2.5, 3.2):
        y = Pf.p(0, 0, z)[1]
        if y > GB:
            c.drawLine(0, y, W, y, stroke("#b9bfc6", 4))
    c.drawRect(skia.Rect.MakeLTRB(0, GB, W, GB + 18), fill("#8b929a"))
    # kính: ám nhẹ, decal sọc thương hiệu, vệt phản chiếu, khung nhôm
    c.drawRect(skia.Rect.MakeLTRB(GL, GT, GR, GB), fill("#9fb7c9" if day else "#2a3550", 0.16))
    DL, DR = 1500, 2340
    for gl, gr in ((GL, 900), (900, DL), (DL, 1920), (1920, DR), (DR, 2940), (2940, GR)):
        c.drawRect(skia.Rect.MakeLTRB(gl, 1240, gr, 1262), fill(BRAND["green"], 0.85))
        c.drawRect(skia.Rect.MakeLTRB(gl, 1268, gr, 1276), fill(BRAND["orange"], 0.85))
        reflections(c, gl + 20, GT, gr - 20, GB, 2, 0.13 if not day else 0.2, seed=int(gl))
    frame = "#a9b0b6"
    for x, wdt in ((GL, 30), (900, 26), (DL, 36), (1920, 22), (DR, 36), (2940, 26), (GR, 30)):
        c.drawRect(skia.Rect.MakeLTRB(x - wdt, GT, x + wdt, GB), fill(frame))
        c.drawRect(skia.Rect.MakeLTRB(x - wdt, GT, x - wdt + 10, GB), fill(shade(frame, 0.18)))
    c.drawRect(skia.Rect.MakeLTRB(GL - 30, GT - 30, GR + 30, GT + 16), fill(frame))
    c.drawRect(skia.Rect.MakeLTRB(DL - 36, GT + 16, DR + 36, GT + 80), fill(frame))
    for x in (1920 - 70, 1920 + 70):                   # tay nắm cửa lùa
        c.drawPath(rrect(x - 10, 1000, x + 10, 1240, 8), fill("#d9dde2"))
    # cảm biến cửa (đen, đèn đỏ)
    c.drawPath(rrect(1840, GT + 24, 2000, GT + 74, 10), fill("#18191d"))
    c.drawCircle(1972, GT + 49, 9, fill("#ff3b30"))
    glow(c, 1972, GT + 49, 40, "#ff3b30", 0.6)
    # decal chữ NGƯỢC (nhìn từ trong) — nướng vào ảnh
    text_center(c, "OPEN 24H", 1920, 905, 120, "#ffffff", a=0.82, max_w=760, mirrored=True)
    # tủ đá tiền cảnh trái
    fl, ft, fr, fb = -40, 1470, 700, H + 10
    quad(c, [(fl, ft), (fr, ft), (fr - 40, ft - 110), (fl + 40, ft - 110)], "#ffffff")
    c.drawRect(skia.Rect.MakeLTRB(fl, ft, fr, fb), fill("#eef1f4"))
    c.drawRect(skia.Rect.MakeLTRB(fl, ft, fr, ft + 22), fill("#d5dbe0"))
    c.drawPath(rrect(120, 1660, 640, 1880, 24), fill("#2e6db0"))
    c.drawPath(rrect(140, 1680, 620, 1860, 16), stroke("#ffffff", 6))
    c.drawRect(skia.Rect.MakeLTRB(fl, 2010, fr, 2030), fill("#c6ccd2"))
    if not day:
        tint(s, "#aeb8cc", 0.3)
    mid = s.makeImageSnapshot()
    # ---- near: góc quầy + tủ hâm (tiền cảnh phải)
    sn = new_surface()
    c = sn.getCanvas()
    nl = 3150
    quad(c, [(nl, 1380), (W, 1380), (W, 1320), (nl + 40, 1320)], "#f4f4f2")
    vgrad(c, nl, 1380, W, H, [BRAND["green"], shade(BRAND["green"], -0.4)])
    c.drawRect(skia.Rect.MakeLTRB(nl, 1420, W, 1436), fill(BRAND["orange"]))
    c.drawRect(skia.Rect.MakeLTRB(nl, 1380, nl + 26, H), fill(shade(BRAND["green"], -0.3)))
    c.drawPath(rrect(3320, 1060, 3900, 1320, 14), fill("#e9f2f6", 0.5))
    c.drawPath(rrect(3320, 1060, 3900, 1320, 14), stroke("#c9d1d7", 12))
    for k in range(3):
        c.drawLine(3350, 1130 + k * 60, 3900, 1130 + k * 60, stroke("#e8833a", 9))
    if not day:
        tint(sn, "#aeb8cc", 0.3)
    near = sn.makeImageSnapshot()
    slots = {"door": {"x": 1920, "y": 1728, "scale": 0.85}, "glass_left": {"x": 1152, "y": 1728, "scale": 0.85},
             "glass_right": {"x": 2688, "y": 1728, "scale": 0.85}, "by_freezer": {"x": 845, "y": 1814, "scale": 0.9},
             "outside_far": {"x": 2380, "y": 1512, "scale": 0.45}, "center": {"x": 1920, "y": 1728, "scale": 0.85}}
    signs = [{"text": "ICE", "box": [150, 1690, 610, 1850], "style": "plain"}]
    baked = [{"text": "OPEN 24H", "box": sign_box(1920, 905, 780, 150), "mirrored": True}]
    return Scene(far, mid, near, slots=slots, signs=signs, baked_signs=baked, floor_y=1728,
                 parallax=(0.85, 1.0, 1.2))


# =================================================================== 4. cửa hàng ven đường – toàn cảnh đêm
def _storefront(c, l, t, r, floor, glow_col, night: bool, fascia_h=120) -> tuple:
    """Khối nhà 1 tầng mặt kính sáng. Trả về hộp dải bảng hiệu (để đặt chữ)."""
    roof_t = t - fascia_h
    c.drawRect(skia.Rect.MakeLTRB(l - 40, roof_t - 30, r + 40, roof_t), fill("#2a2f3a" if night else "#4a505c"))
    c.drawRect(skia.Rect.MakeLTRB(l - 40, roof_t, r + 40, t), fill(BRAND["green"]))
    c.drawRect(skia.Rect.MakeLTRB(l - 40, t - 16, r + 40, t), fill(BRAND["orange"]))
    vgrad(c, l, t, r, floor, [glow_col, shade(glow_col, -0.12)])
    # bên trong: kệ, quầy (bóng phẳng)
    rng = random.Random(77)
    for i in range(5):
        x = l + (r - l) * (0.12 + i * 0.16)
        top = t + (floor - t) * 0.35
        c.drawRect(skia.Rect.MakeLTRB(x, top, x + (r - l) * 0.09, floor - 8), fill("#e3e6ea"))
        for k in range(4):
            y = top + (floor - top) * (0.1 + k * 0.22)
            c.drawRect(skia.Rect.MakeLTRB(x + 6, y, x + (r - l) * 0.09 - 6, y + (floor - top) * 0.12),
                       fill(rng.choice(PRODUCTS[:-1]), 0.85))
    c.drawRect(skia.Rect.MakeLTRB(l + (r - l) * 0.03, floor - (floor - t) * 0.32, l + (r - l) * 0.2, floor),
               fill(BRAND["green"]))
    for x in (l, l + (r - l) / 3, l + (r - l) * 2 / 3, r):
        c.drawRect(skia.Rect.MakeLTRB(x - 10, t, x + 10, floor), fill("#a9b0b6" if not night else "#8a9098"))
    reflections(c, l, t, r, floor, 4, 0.12, seed=3)
    c.drawRect(skia.Rect.MakeLTRB(l - 40, floor, r + 40, floor + 26), fill("#6b707a" if night else "#9a9ea6"))
    return (l - 40, roof_t, r + 40, t - 16)


def _road(c, top, bottom, col, line_col="#d9d4c4", dashed_y=None, edge_col=None):
    c.drawRect(skia.Rect.MakeLTRB(0, top, W, bottom), fill(col))
    if edge_col:
        c.drawRect(skia.Rect.MakeLTRB(0, top, W, top + 10), fill(edge_col))
        c.drawRect(skia.Rect.MakeLTRB(0, bottom - 10, W, bottom), fill(edge_col))
    y = dashed_y if dashed_y is not None else (top + bottom) / 2
    x = -60
    while x < W:
        c.drawRect(skia.Rect.MakeLTRB(x, y - 8, x + 220, y + 8), fill(line_col))
        x += 420


def _shrine(c, x, base, night: bool):
    pole = "#3a2a22" if night else "#6b4a32"
    c.drawRect(skia.Rect.MakeLTRB(x - 14, base - 430, x + 14, base), fill(pole))
    c.drawRect(skia.Rect.MakeLTRB(x - 110, base - 470, x + 110, base - 430), fill(shade(pole, 0.1)))
    c.drawRect(skia.Rect.MakeLTRB(x - 90, base - 640, x + 90, base - 470), fill("#c8a46a" if not night else "#4a3a2c"))
    quad(c, [(x - 140, base - 630), (x + 140, base - 630), (x + 60, base - 730), (x - 60, base - 730)],
         "#8a3a2a" if not night else "#3a1a16")
    c.drawRect(skia.Rect.MakeLTRB(x - 45, base - 600, x + 45, base - 490), fill("#1a0e0a"))
    c.drawCircle(x, base - 540, 14, fill("#ff5a3a"))
    glow(c, x, base - 540, 120 if night else 60, "#ff5a3a", 0.6 if night else 0.3)


def _bus_shelter(c, l, r, top, base, night: bool, col=None):
    col = col or ("#1d2433" if night else "#5b6b7d")
    c.drawRect(skia.Rect.MakeLTRB(l - 30, top, r + 30, top + 34), fill(col))
    for x in (l + 10, r - 10):
        c.drawRect(skia.Rect.MakeLTRB(x - 9, top + 34, x + 9, base), fill(col))
    c.drawRect(skia.Rect.MakeLTRB(l + 20, top + 34, r - 20, base - 90), fill("#9fb7c9" if not night else "#2a3550", 0.25))
    c.drawRect(skia.Rect.MakeLTRB(l + 60, base - 110, r - 60, base - 90), fill(shade(col, 0.15)))
    for x in (l + 90, r - 90):
        c.drawRect(skia.Rect.MakeLTRB(x - 6, base - 90, x + 6, base), fill(shade(col, 0.15)))


def scene_cua_hang_mat_tien_dem(tod: str) -> Scene:
    dusk = tod == "dusk"
    HZ = 1050
    sf = new_surface()
    c = sf.getCanvas()
    if dusk:
        _dusk_sky(c, 0, HZ + 40, seed=8)
    else:
        _night_sky(c, 0, HZ + 40, seed=9, n_stars=340)
        glow(c, 2380, 250, 260, "#f1ead2", 0.55)
        c.drawCircle(2380, 250, 92, fill("#f1ead2"))
        c.drawCircle(2410, 235, 22, fill("#e4dcc0"))
    mountains(c, HZ - 20, 420, "#232a48" if not dusk else "#4a3f6a", 61, 6)
    mountains(c, HZ + 10, 260, "#0f1424" if not dusk else "#2c2848", 62, 9)
    # mặt hồ
    vgrad(c, 0, HZ - 6, W, HZ + 70, ["#1d2640" if not dusk else "#6a5a8a", "#0f1424" if not dusk else "#3a3560"])
    if not dusk:
        for k in range(6):
            c.drawRect(skia.Rect.MakeLTRB(2320 + k * 9, HZ + 6 + k * 10, 2440 - k * 9, HZ + 12 + k * 10),
                       fill("#f1ead2", 0.5 - k * 0.07))
    far = sf.makeImageSnapshot()
    s = new_surface()
    c = s.getCanvas()
    ground = "#1a1f2b" if not dusk else "#3a3a4a"
    vgrad(c, 0, HZ + 60, W, H, [shade(ground, 0.05), ground])
    # bụi cây xa
    for x in range(-100, W + 100, 170):
        c.drawCircle(x, HZ + 80, 95, fill("#141a22" if not dusk else "#2b3340"))
    # sân đỗ
    c.drawRect(skia.Rect.MakeLTRB(900, 1290, 3000, 1600), fill("#232a36" if not dusk else "#4a4a58"))
    for x in range(1000, 3000, 260):
        c.drawLine(x, 1330, x - 60, 1560, stroke("#cfd3da", 8, 0.55))
    ellipse_glow(c, 1920, 1330, 1000, 190, "#fff6dc", 0.4 if not dusk else 0.25)
    # cửa hàng
    glow_col = "#fff6dc" if not dusk else "#fbe9c0"
    fx = _storefront(c, 1150, 840, 2750, 1270, glow_col, True, fascia_h=150)
    glow(c, 1950, 1060, 1300, "#fff1c8", 0.28)
    # đường 2 làn tiền cảnh
    _road(c, 1640, 1960, "#2a2e36" if not dusk else "#4a4a50", "#cfc9b6", edge_col="#6b6f78")
    c.drawRect(skia.Rect.MakeLTRB(0, 1960, W, H), fill("#141a16" if not dusk else "#2f3a2e"))
    # miếu nhỏ trái
    _shrine(c, 480, 1600, True)
    # trạm chờ xe buýt + đèn đường + cây trơ cành phải
    _bus_shelter(c, 3130, 3600, 1150, 1480, True)
    lx = 2980
    c.drawRect(skia.Rect.MakeLTRB(lx - 12, 480, lx + 12, 1600), fill("#0a0d14"))
    c.drawPath(capsule(lx, 490, lx + 190, 520, 18, 14), fill("#0a0d14"))
    glow(c, lx + 200, 540, 420, "#ffd98a", 0.8)
    ellipse_glow(c, lx + 200, 1560, 520, 120, "#ffd98a", 0.35)
    tree_bare(c, 3560, 1500, 1100, "#07090d", seed=12, w=34)
    if dusk:
        tint(s, "#c9b6d6", 0.25)
    mid = s.makeImageSnapshot()
    sb = [round(fx[0] + 500), round(fx[1] + 18), round(fx[2] - 500), round(fx[3] - 10)]
    signs = [{"text": "MINI MART 24H", "box": sb, "style": "plain"}]
    slots = {"inside_counter": {"x": 1690, "y": 1258, "scale": 0.22},
             "forecourt": {"x": 2112, "y": 1512, "scale": 0.3},
             "bus_stop": {"x": 3302, "y": 1472, "scale": 0.28},
             "roadside_left": {"x": 576, "y": 1620, "scale": 0.3},
             "center": {"x": 2112, "y": 1512, "scale": 0.3}}
    return Scene(far, mid, slots=slots, signs=signs, floor_y=1512, parallax=(0.85, 1.0, 1.15),
                 lights=[{"x": lx + 200, "y": 540, "color": "#ffd98a"}])


# =================================================================== 5. mặt tiền cửa cuốn đóng
def scene_cua_hang_cua_cuon_dong(tod: str) -> Scene:
    s = new_surface()
    c = s.getCanvas()
    night, dusk = tod == "night", tod == "dusk"
    if night:
        vgrad(c, 0, 0, W, 200, ["#0b1022", "#141a2e"])
    elif dusk:
        vgrad(c, 0, 0, W, 200, ["#5a4f8c", "#c98fa6"])
    else:
        vgrad(c, 0, 0, W, 200, ["#8d9aab", "#b9c3cf"])
    # tường hai bên (cột)
    wall = "#cfc8b8"
    c.drawRect(skia.Rect.MakeLTRB(0, 160, W, 1910), fill(wall))
    # bảng hiệu dày
    FT, FB = 160, 470
    c.drawRect(skia.Rect.MakeLTRB(0, FT - 20, W, FT), fill("#3a3d44"))
    vgrad(c, 0, FT, W, FB, [BRAND["green"], shade(BRAND["green"], -0.18)])
    c.drawRect(skia.Rect.MakeLTRB(0, FB - 10, W, FB), fill(shade(BRAND["green"], -0.4)))
    c.drawRect(skia.Rect.MakeLTRB(0, FB, W, FB + 22), fill(BRAND["orange"]))
    c.drawRect(skia.Rect.MakeLTRB(0, FB + 22, W, FB + 60), fill("#e3dccb"))
    leaf_emblem(c, 560, (FT + FB) / 2, 90, BRAND["cream"], BRAND["cream"])
    leaf_emblem(c, W - 560, (FT + FB) / 2, 90, BRAND["cream"], BRAND["cream"])
    # hộp cuốn
    SL, SR = 260, W - 260
    c.drawRect(skia.Rect.MakeLTRB(SL - 20, FB + 60, SR + 20, 640), fill("#7d8086"))
    c.drawRect(skia.Rect.MakeLTRB(SL - 20, 620, SR + 20, 640), fill("#5e6166"))
    # cửa cuốn tôn sóng
    ST, SB = 640, 1880
    sh0, sh1 = "#8a8d93", "#b8babf"
    y = ST
    k = 0
    while y < SB:
        c.drawRect(skia.Rect.MakeLTRB(SL, y, SR, y + 30), fill(sh1 if k % 2 == 0 else sh0))
        c.drawRect(skia.Rect.MakeLTRB(SL, y + 26, SR, y + 30), fill(shade(sh0, -0.2)))
        y += 30
        k += 1
    for x in (SL + (SR - SL) / 4, SL + (SR - SL) / 2, SL + (SR - SL) * 3 / 4):
        yy = ST
        while yy < SB:
            c.drawLine(x, yy, x, yy + 40, stroke("#6a6d73", 5))
            yy += 70
    rng = random.Random(5)
    for _ in range(26):                      # vết gỉ
        x, yv = rng.uniform(SL, SR), rng.uniform(ST + 300, SB)
        c.drawPath(oval(x, yv, rng.uniform(14, 60), rng.uniform(6, 22)), fill("#8a5a3a", rng.uniform(0.25, 0.55)))
    for x in (SL + 30, SR - 30):
        c.drawLine(x, ST + 400, x + 8, SB, stroke("#6e5a4a", 6, 0.35))
    c.drawRect(skia.Rect.MakeLTRB(SL, SB - 40, SR, SB), fill("#6a6d73"))
    c.drawPath(rrect(1920 - 140, SB - 30, 1920 + 140, SB - 6, 10), fill("#2b2d33"))
    c.drawRect(skia.Rect.MakeLTRB(SL - 30, ST, SL, SB), fill("#5e6166"))
    c.drawRect(skia.Rect.MakeLTRB(SR, ST, SR + 30, SB), fill("#5e6166"))
    # vỉa hè + vũng nước
    vgrad(c, 0, 1880, W, H, ["#6e675d", "#4e4840"])
    c.drawRect(skia.Rect.MakeLTRB(0, 1880, W, 1900), fill("#3e3932"))
    for x, wv in ((900, 420), (2650, 560), (3500, 300)):
        c.drawPath(oval(x, 2060, wv, 38), fill("#8d9aab" if not night else "#2a3550", 0.55))
        c.drawPath(oval(x - wv * 0.2, 2052, wv * 0.4, 8), fill("#ffffff", 0.2))
    if night:
        darken(c, 0.62, "#060812")
        # hộp đèn đỏ nhỏ
        c.drawPath(rrect(3440, 700, 3520, 760, 8), fill("#d0302a"))
        glow(c, 3480, 730, 220, "#ff3b30", 0.55)
        ellipse_glow(c, 3480, 1900, 400, 60, "#ff3b30", 0.18)
    elif dusk:
        tint(s, "#c9a6c6", 0.3)
        c.drawRect(skia.Rect.MakeWH(W, H), lin_paint((0, 0), (0, H), [("#2e3370", 0.0), ("#2e3370", 0.25)]))
    mid = s.makeImageSnapshot()
    slots = {"left": frac_slot({"x": 0.30, "y": 0.92, "scale": 1.0}),
             "center": frac_slot({"x": 0.50, "y": 0.92, "scale": 1.0}),
             "right": frac_slot({"x": 0.70, "y": 0.92, "scale": 1.0})}
    signs = [{"text": "MINI MART 24H", "box": [900, FT + 40, W - 900, FB - 40],
              "style": "plain"}]
    return Scene(None, mid, slots=slots, signs=signs, floor_y=slots["center"]["y"])


# =================================================================== 6. phòng nhân viên
def scene_phong_nhan_vien(tod: str) -> Scene:
    night = tod == "night"
    P = Persp(f=1500, cx=W / 2, cy=1100, cam_h=1.5)
    XW, ZB, YC = 2.3, 4.6, 2.8
    s = new_surface()
    c = s.getCanvas()
    wall, side, floor_c, red = "#8e877c", "#6f695f", "#4a4642", "#b5332b"
    path_fill(c, P.plane_y(YC, -XW, XW, 0.3, ZB), shade(wall, -0.3))
    for sd in (-1, 1):
        path_fill(c, P.wall_x(sd * XW, 0.3, ZB, 0, YC), side)
    path_fill(c, P.plane_y(0, -XW, XW, 0.3, ZB), floor_c)
    for x in (-1.5, -0.5, 0.5, 1.5):
        c.drawLine(*P.p(x, 0, 0.6), *P.p(x, 0, ZB), stroke(shade(floor_c, -0.15), 4))
    path_fill(c, P.face_z(ZB, -XW, XW, 0, YC), wall)
    bl, bt = P.p(-XW, YC, ZB)
    br, bb = P.p(XW, 0, ZB)
    # vệt nước loang chảy dọc
    rng = random.Random(8)
    for x0 in (bl + (br - bl) * 0.58, bl + (br - bl) * 0.64, bl + (br - bl) * 0.2):
        ln = rng.uniform(0.45, 0.8) * (bb - bt)
        c.drawPath(rrect(x0, bt, x0 + rng.uniform(16, 34), bt + ln, 14), fill("#6a645a", 0.55))
        c.drawPath(oval(x0 + 12, bt + ln, 22, 30), fill("#6a645a", 0.5))
    c.drawPath(rrect(bl + (br - bl) * 0.5, bt, bl + (br - bl) * 0.72, bt + 34, 17), fill("#6a645a", 0.5))
    # lịch treo tường đầu đỏ
    cl, ct = bl + (br - bl) * 0.12, bt + (bb - bt) * 0.18
    c.drawRect(skia.Rect.MakeLTRB(cl, ct, cl + 190, ct + 250), fill("#f2ede2"))
    c.drawRect(skia.Rect.MakeLTRB(cl, ct, cl + 190, ct + 62), fill(red))
    text_center(c, "JULY", cl + 95, ct + 31, 30, "#ffffff", "bold")
    for i in range(5):
        for j in range(6):
            c.drawRect(skia.Rect.MakeLTRB(cl + 14 + j * 28, ct + 80 + i * 32, cl + 34 + j * 28, ct + 98 + i * 32),
                       fill("#9a948a" if (i, j) != (2, 3) else red))
    # tờ nội quy dán
    pl, pt = cl + 260, ct + 30
    c.save()
    c.rotate(-2, pl + 90, pt + 120)
    c.drawRect(skia.Rect.MakeLTRB(pl, pt, pl + 180, pt + 240), fill("#efe9da"))
    for i in range(7):
        c.drawLine(pl + 20, pt + 50 + i * 26, pl + 160 - (i % 3) * 20, pt + 50 + i * 26, stroke("#6b7a9a", 5))
    c.drawLine(pl + 20, pt + 26, pl + 120, pt + 26, stroke(red, 7))
    c.drawRect(skia.Rect.MakeLTRB(pl + 60, pt - 14, pl + 120, pt + 14), fill("#d9c9a0", 0.85))
    c.restore()
    # hộp cầu dao + công tắc đỏ + dây lủng lẳng
    kl, kt = bl + (br - bl) * 0.47, bt + (bb - bt) * 0.2
    c.drawPath(rrect(kl, kt, kl + 170, kt + 230, 10), fill("#9aa0a6"))
    c.drawPath(rrect(kl + 14, kt + 14, kl + 156, kt + 216, 8), fill("#7d838a"))
    for i in range(3):
        c.drawRect(skia.Rect.MakeLTRB(kl + 34 + i * 40, kt + 60, kl + 58 + i * 40, kt + 120),
                   fill("#2b2d33" if i != 1 else "#d0302a"))
    p = skia.Path()
    p.moveTo(kl + 85, kt + 230)
    p.cubicTo(kl + 60, kt + 360, kl + 160, kt + 400, kl + 120, kt + 520)
    c.drawPath(p, stroke("#1a1a1a", 7))
    c.drawPath(p, stroke("#1a1a1a", 7))
    # bóng đèn trần
    lx, ly = P.p(0, YC, 2.6)
    _, by = P.p(0, YC - 0.45, 2.6)
    c.drawLine(lx, ly, lx, by, stroke("#1a1a1a", 6))
    bulb = "#fff2c4" if not night else "#cfe0ff"
    glow(c, lx, by + 30, 1100, bulb, 0.35 if not night else 0.22)
    glow(c, lx, by + 30, 220, bulb, 0.8)
    c.drawPath(oval(lx, by + 30, 30, 38), fill("#ffffff"))
    # tủ locker đôi xanh thép (sát tường hậu, bên phải, quay ra camera)
    lk = "#4d6278"
    x0, x1, zf = 1.1, 2.2, ZB - 0.5
    path_fill(c, P.wall_x(x0, zf, ZB, 0, 1.95), shade(lk, -0.22))      # mặt bên ×0.78
    path_fill(c, P.face_z(zf, x0, x1, 0, 1.95), lk)
    ll, lt = P.p(x0, 1.95, zf)
    lr, lb = P.p(x1, 0.0, zf)
    xm = (ll + lr) / 2
    c.drawLine(xm, lt + 6, xm, lb - 6, stroke(shade(lk, -0.45), 6))
    for dl, dr in ((ll, xm), (xm, lr)):
        for k in range(4):
            yv = lt + 60 + k * 26
            c.drawLine(dl + 40, yv, dr - 40, yv, stroke(shade(lk, -0.38), 7))
        hx = dr - 34 if dl == ll else dl + 34
        c.drawPath(rrect(hx - 9, (lt + lb) / 2 - 40, hx + 9, (lt + lb) / 2 + 40, 6), fill("#c9ced4"))
        c.drawRect(skia.Rect.MakeLTRB(dl + 60, lt + 190, dr - 60, lt + 230), fill("#f2ede2", 0.9))
    c.drawRect(skia.Rect.MakeLTRB(ll, lt, ll + 10, lb), fill(shade(lk, 0.15)))
    # bàn gỗ (trái, quay ra camera)
    desk = "#6b4a32"
    dx0, dx1, dz0, dz1, dy = -2.05, -0.55, 2.4, 3.1, 0.78
    path_fill(c, P.plane_y(dy, dx0, dx1, dz0, dz1), shade(desk, 0.12))
    path_fill(c, P.face_z(dz0, dx0, dx1, 0, dy), desk)
    path_fill(c, P.face_z(dz0, dx0, dx1, dy - 0.05, dy), shade(desk, -0.25))
    path_fill(c, P.wall_x(dx1, dz0, dz1, 0, dy), shade(desk, -0.22))
    # sổ đỏ + đèn bàn
    path_fill(c, P.plane_y(dy + 0.01, -1.6, -1.25, 2.55, 2.85), red)
    path_fill(c, P.face_z(2.55, -1.6, -1.25, dy, dy + 0.035), shade(red, -0.3))
    ax, ay = P.p(-0.85, dy, 2.9)
    hx, hy = P.p(-0.8, dy + 0.45, 2.9)
    c.drawPath(oval(ax, ay, 46, 14), fill("#2b2d33"))
    c.drawLine(ax, ay, hx - 30, hy, stroke("#2b2d33", 10))
    quad(c, [(hx - 70, hy), (hx + 10, hy - 30), (hx + 40, hy + 40), (hx - 40, hy + 60)], "#2b2d33")
    glow(c, hx, hy + 80, 260, "#ffe2a0", 0.4 if not night else 0.55)
    vg = rad_paint(W / 2, 1050, 2500, [("#000000", 0.0), ("#000000", 0.6)], [0.3, 1])
    c.drawRect(skia.Rect.MakeWH(W, H), vg)
    if night:
        tint(s, "#8a96b8", 0.55)
    mid = s.makeImageSnapshot()
    # near: ghế văn phòng đen
    sn = new_surface()
    c = sn.getCanvas()
    ch = "#18191d"
    c.drawPath(rrect(80, 1520, 640, 1960, 60), fill(ch))
    c.drawPath(rrect(120, 1560, 600, 1920, 50), fill(shade(ch, 0.08)))
    c.drawPath(rrect(40, 1930, 700, 2060, 40), fill(shade(ch, 0.04)))
    c.drawRect(skia.Rect.MakeLTRB(340, 2050, 380, H), fill(ch))
    if night:
        tint(sn, "#8a96b8", 0.4)
    near = sn.makeImageSnapshot()
    desk_top = round(P.p(0, dy, dz1)[1])
    slots = {"left": P.slot(-0.55, 3.3), "center": P.slot(0.15, 3.0), "right": P.slot(0.85, 3.3),
             "desk": P.slot(-1.3, 3.6, clip_bottom=desk_top + 20)}
    return Scene(None, mid, near, slots=slots, floor_y=slots["center"]["y"])


# =================================================================== 7. chòi xe ôm ven đường
def scene_cho_xe_om_ven_duong(tod: str) -> Scene:
    night, day = tod == "night", tod == "day"
    HZ = 1240
    sf = new_surface()
    c = sf.getCanvas()
    if night:
        _night_sky(c, 0, HZ + 60, seed=15, n_stars=220)
    elif day:
        _day_sky(c, 0, HZ + 60)
    else:
        _dusk_sky(c, 0, HZ + 60, seed=16)
    tl = "#1d2a2a" if night else ("#6f8a68" if day else "#3a3a5a")
    for i, x in enumerate(range(-100, W + 200, 240)):
        round_tree(c, x, HZ - 20, 150 + (i % 3) * 30, tl, tl, seed=i)
    far = sf.makeImageSnapshot()
    s = new_surface()
    c = s.getCanvas()
    # cỏ + vỉa hè + đường
    grass = "#24301f" if night else ("#6f8a58" if day else "#3a4a3a")
    c.drawRect(skia.Rect.MakeLTRB(0, HZ, W, 1820), fill(grass))
    for x in range(-60, W, 230):
        c.drawCircle(x, HZ + 60, 120, fill("#2f4a3a" if not night else "#16241c"))
    walk = "#8a857c" if day else ("#5a5560" if not night else "#2a2a30")
    c.drawRect(skia.Rect.MakeLTRB(0, 1690, W, 1840), fill(walk))
    rng = random.Random(3)
    for _ in range(14):
        x = rng.uniform(0, W)
        c.drawPath(poly([(x, 1700), (x + rng.uniform(-40, 40), 1760), (x + rng.uniform(-30, 30), 1830)], close=False),
                   stroke(shade(walk, -0.3), 4))
    _road(c, 1840, H, "#4a4a50" if not night else "#24252a", "#e8c24a", dashed_y=2010, edge_col="#d9d4c4")
    # mặt tiền cửa hàng trái 40%
    gl = "#dfeaf3" if day else "#fff3d6"
    c.drawRect(skia.Rect.MakeLTRB(-40, 520, 1440, 1700), fill("#cfc8b8" if day else "#3a3a46"))
    c.drawRect(skia.Rect.MakeLTRB(-40, 520, 1440, 690), fill(BRAND["green"]))
    c.drawRect(skia.Rect.MakeLTRB(-40, 676, 1440, 690), fill(BRAND["orange"]))
    vgrad(c, 60, 760, 1360, 1660, [gl, shade(gl, -0.1)])
    for x in (60, 500, 940, 1360):
        c.drawRect(skia.Rect.MakeLTRB(x - 14, 760, x + 14, 1660), fill("#a9b0b6"))
    for i in range(3):
        x = 140 + i * 420
        c.drawRect(skia.Rect.MakeLTRB(x, 1000, x + 240, 1660), fill("#e3e6ea", 0.9))
        for k in range(4):
            c.drawRect(skia.Rect.MakeLTRB(x + 10, 1030 + k * 150, x + 230, 1100 + k * 150),
                       fill(PRODUCTS[(i + k) % 6], 0.8))
    reflections(c, 60, 760, 1360, 1660, 3, 0.18, seed=21)
    # tờ tìm người dán kính (không chữ đọc được: dải đỏ + ô ảnh + dòng)
    c.save()
    c.rotate(3, 1130, 980)
    c.drawRect(skia.Rect.MakeLTRB(1040, 860, 1220, 1110), fill("#f5f1e6"))
    c.drawRect(skia.Rect.MakeLTRB(1040, 860, 1220, 902), fill("#c8352e"))
    c.drawRect(skia.Rect.MakeLTRB(1080, 920, 1180, 1010), fill("#c9ccd2"))
    for i in range(3):
        c.drawLine(1065, 1035 + i * 22, 1195 - i * 20, 1035 + i * 22, stroke("#6b6b6b", 6))
    c.restore()
    c.drawRect(skia.Rect.MakeLTRB(-40, 1660, 1440, 1700), fill("#6b707a"))
    if not day:
        glow(c, 700, 1200, 900, "#fff1c8", 0.28)
    # chòi xe ôm: mái tôn nghiêng + 2 cột + bảng cam + 2 đèn chụp + bảng thông báo + ghế gỗ
    rl, rr = 1640, 2620
    post = "#7d8086" if not night else "#3a3d44"
    for x in (rl + 80, rr - 80):
        c.drawRect(skia.Rect.MakeLTRB(x - 16, 900, x + 16, 1760), fill(post))
    quad(c, [(rl - 120, 930), (rr + 120, 900), (rr + 100, 780), (rl - 100, 840)], "#8f949c" if not night else "#3f444c")
    for k in range(9):
        x = rl - 100 + k * (rr - rl + 200) / 8
        c.drawLine(x, 840 - k * 7.5 + 4, x - 8, 928 - k * 3.7, stroke("#6e737b" if not night else "#2c3036", 5))
    c.drawRect(skia.Rect.MakeLTRB(rl - 120, 930 - 4, rr + 120, 948 - 30 * 0), fill("#5e6168"))
    sgl, sgt, sgr, sgb = 1890, 742, 2370, 900
    c.drawPath(rrect(sgl, sgt, sgr, sgb, 14), fill(BRAND["orange"]))
    c.drawPath(rrect(sgl + 10, sgt + 10, sgr - 10, sgb - 10, 10), stroke("#fff1dc", 5))
    lamp_col = "#ffd98a"
    for x in (1900, 2360):
        c.drawLine(x, 940, x, 1040, stroke("#1a1a1a", 5))
        quad(c, [(x - 60, 1100), (x + 60, 1100), (x + 24, 1040), (x - 24, 1040)], "#2b2d33")
        if not day:
            glow(c, x, 1110, 260, lamp_col, 0.75)
            c.drawPath(poly([(x - 60, 1100), (x + 60, 1100), (x + 260, 1760), (x - 260, 1760)]),
                       fill(lamp_col, 0.12))
    c.drawRect(skia.Rect.MakeLTRB(2380, 1180, 2560, 1420), fill("#f0ebe0" if day else "#6a6a70"))
    for i in range(5):
        c.drawLine(2400, 1220 + i * 36, 2540 - (i % 2) * 40, 1220 + i * 36, stroke("#8a8a8a", 6))
    c.drawRect(skia.Rect.MakeLTRB(2470, 1420, 2482, 1760), fill(post))
    bench = "#8a5a3a" if not night else "#3a2a20"
    c.drawPath(rrect(1820, 1600, 2300, 1640, 8), fill(bench))
    c.drawPath(rrect(1820, 1530, 2300, 1560, 8), fill(shade(bench, -0.15)))
    for x in (1860, 2260):
        c.drawRect(skia.Rect.MakeLTRB(x - 10, 1640, x + 10, 1740), fill(shade(bench, -0.25)))
    # cột điện gỗ + dây võng + cây chết
    pole = "#5a4030" if not night else "#15100c"
    power_pole(c, 3150, 360, 1780, pole, 34)
    sag_wire(c, 3150, 420, W + 100, 520, 50, pole, 5)
    sag_wire(c, -100, 380, 3150, 420, 160, pole, 5)
    sag_wire(c, -100, 470, 3150, 490, 180, pole, 4)
    tree_bare(c, 3560, 1780, 1250, "#2a2020" if not night else "#07080a", seed=31, w=36)
    for x in range(2700, W + 100, 150):
        c.drawCircle(x, 1700, 90, fill("#2f4a3a" if not night else "#121c16"))
    # sương mặt đất
    c.drawRect(skia.Rect.MakeLTRB(0, 1450, W, 1850),
               lin_paint((0, 1450), (0, 1850), [("#e8e0f0", 0.0), ("#e8e0f0", 0.18 if not day else 0.08), ("#e8e0f0", 0.0)]))
    if night:
        tint(s, "#8a96b8", 0.35)
    mid = s.makeImageSnapshot()
    slots = {"bench": {"x": 2060, "y": 1740, "scale": 0.55}, "store_door": {"x": 845, "y": 1760, "scale": 0.55},
             "roadside": {"x": 2950, "y": 1790, "scale": 0.55}, "center": {"x": 2060, "y": 1740, "scale": 0.55}}
    signs = [{"text": "MOTO TAXI", "box": [sgl + 24, sgt + 20, sgr - 24, sgb - 20], "style": "plain"}]
    return Scene(far, mid, slots=slots, signs=signs, floor_y=1740, parallax=(0.8, 1.0, 1.15))


# =================================================================== 8. nền tối trừu tượng
def scene_nen_toi_truu_tuong(tod: str) -> Scene:
    s = new_surface()
    c = s.getCanvas()
    center, edge = ("#2c3a52", "#0c1220") if tod == "night" else ("#3a3836", "#121110")
    c.drawRect(skia.Rect.MakeWH(W, H), rad_paint(W / 2, H * 0.45, W * 0.62, [center, edge], [0, 1]))
    P = Persp(f=1500, cx=W / 2, cy=1000, cam_h=1.6)
    gp = stroke("#ffffff", 3, 0.06)
    for x in range(-12, 13):
        c.drawLine(*P.p(x * 0.8, 0, 1.2), *P.p(x * 0.8, 0, 30), gp)
    z = 1.2
    while z < 30:
        c.drawLine(*P.p(-12, 0, z), *P.p(12, 0, z), gp)
        z *= 1.25
    c.drawRect(skia.Rect.MakeLTRB(0, 0, W, 1050), lin_paint((0, 0), (0, 1050), [(edge, 0.0), (edge, 0.0)]))
    mid = s.makeImageSnapshot()
    slots = {"center": frac_slot({"x": 0.50, "y": 0.98, "scale": 1.6}),
             "left": frac_slot({"x": 0.36, "y": 0.98, "scale": 1.6}),
             "right": frac_slot({"x": 0.64, "y": 0.98, "scale": 1.6})}
    return Scene(None, mid, slots=slots, floor_y=slots["center"]["y"])


# =================================================================== THƯ VIỆN MỞ RỘNG (procedural_library)
# 16 địa điểm còn lại của catalog (procedural=false: không có trong bộ kiểm thử v1, provenance
# 'procedural_library'). Mọi chữ vẽ vào pixel đều là TIẾNG ANH chung chung; chữ biển hiệu là lớp chữ thật (signs).
def _R(l, t, r, b) -> skia.Rect:
    return skia.Rect.MakeLTRB(l, t, r, b)


def _blurred(img: skia.Image, sigma: float) -> skia.Image:
    s = new_surface()
    p = skia.Paint(ImageFilter=skia.ImageFilters.Blur(sigma, sigma, skia.TileMode.kClamp))
    s.getCanvas().drawImage(img, 0, 0, skia.SamplingOptions(), p)
    return s.makeImageSnapshot()


def _grade(s: skia.Surface, tod: str, base: str) -> None:
    """Biến thể thời gian thô (cảnh thư viện vẽ cho 1 thời điểm gốc)."""
    if tod == base:
        return
    if tod == "night":
        tint(s, "#56648a", 0.62)
    elif tod == "dusk":
        tint(s, "#c9a6c6", 0.32)
    elif tod in ("day", "indoor") and base == "night":
        tint(s, "#fff4e0", 0.05)


def _vignette(c, a: float = 0.5, r: float = W * 0.62) -> None:
    c.drawRect(_R(0, 0, W, H), rad_paint(W / 2, H * 0.48, r, [("#000000", 0.0), ("#000000", a)], [0.45, 1]))


def _bulb_string(c, x0, y0, x1, y1, sag, n, col="#ffd98a", wire="#121318", lit=True) -> None:
    sag_wire(c, x0, y0, x1, y1, sag, wire, 4)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2 + sag * 2
    for i in range(1, n):
        t = i / n
        x = (1 - t) ** 2 * x0 + 2 * t * (1 - t) * cx + t * t * x1
        y = (1 - t) ** 2 * y0 + 2 * t * (1 - t) * cy + t * t * y1
        c.drawLine(x, y, x, y + 14, stroke(wire, 3))
        c.drawCircle(x, y + 24, 12, fill(col if lit else "#6a6a66"))
        if lit:
            glow(c, x, y + 24, 80, col, 0.4)


def _tube(c, x, y, w, on=True, col="#eef6ff") -> None:
    c.drawRect(_R(x - w / 2 - 16, y - 8, x + w / 2 + 16, y + 8), fill("#6b7078"))
    c.drawPath(rrect(x - w / 2, y + 4, x + w / 2, y + 28, 12), fill(col if on else "#9aa0a8"))
    if on:
        ellipse_glow(c, x, y + 24, w * 0.9, w * 0.28, col, 0.45)


def _ceiling_fan(c, x, y, r, col="#3a3a40") -> None:
    c.drawLine(x, 0, x, y, stroke(col, 10))
    c.drawPath(oval(x, y + 10, r * 0.15, r * 0.08), fill(col))
    for sg in (-1, 1):
        c.drawPath(oval(x + sg * r * 0.55, y + 16, r * 0.46, r * 0.065), fill(shade(col, 0.12)))


def _barred_window(c, l, t, r, b, g0, g1, frame="#5a5248", bars="#2a2622", n=6) -> None:
    vgrad(c, l, t, r, b, [g0, g1])
    for i in range(1, n):
        x = l + (r - l) * i / n
        c.drawLine(x, t, x, b, stroke(bars, 9))
    c.drawLine(l, (t + b) / 2, r, (t + b) / 2, stroke(bars, 9))
    c.drawRect(_R(l, t, r, b), stroke(frame, 22))
    c.drawRect(_R(l - 30, b + 8, r + 30, b + 34), fill(shade(frame, 0.1)))


def _plastic_stool(c, x, base, h, col="#c8352e") -> None:
    top = base - h
    quad(c, [(x - h * 0.42, top), (x + h * 0.42, top), (x + h * 0.52, base), (x - h * 0.52, base)], col)
    c.drawPath(oval(x, top, h * 0.45, h * 0.09), fill(shade(col, 0.15)))
    c.drawPath(rrect(x - h * 0.16, top + h * 0.35, x + h * 0.16, top + h * 0.6, h * 0.08), fill(shade(col, -0.35)))


def _floor_tiles(c, P: Persp, x0, x1, z0, z1, step, line, wmin=1.5) -> None:
    x = x0
    while x <= x1 + 1e-6:
        c.drawLine(*P.p(x, 0, z0), *P.p(x, 0, z1), stroke(line, 4))
        x += step
    z = z0
    while z <= z1:
        c.drawLine(*P.p(x0, 0, z), *P.p(x1, 0, z), stroke(line, max(wmin, 8 / z)))
        z += step


def _person_px(scale: float) -> float:
    return REF_CHAR_PX * scale / PERSON_M        # px / mét tại 1 slot


# ------------------------------------------------------------------- 9. quầy POV (nhìn từ nhân viên)
def scene_cua_hang_quay_pov(tod: str) -> Scene:
    night = tod != "day"
    sf = new_surface()
    c = sf.getCanvas()
    if night:
        vgrad(c, 0, 0, W, 1400, ["#070b16", "#111a2c", "#1a2232"], [0, 0.6, 1])
    else:
        vgrad(c, 0, 0, W, 1400, ["#9fb0c2", "#c9d3dc", "#a9b1b8"], [0, 0.6, 1])
    c.drawRect(_R(0, 1080, W, 1400), fill("#141820" if night else "#8a8c8e"))
    glow(c, 2950, 520, 520, "#ffd98a", 0.75 if night else 0.2)
    c.drawCircle(2950, 520, 40, fill("#fff1c8"))
    ellipse_glow(c, 2900, 1180, 700, 90, "#ffd98a", 0.4 if night else 0.1)
    c.drawPath(rrect(740, 200, 900, 280, 10), fill("#2fbf62"))
    glow(c, 820, 240, 260, "#3cff7a", 0.55 if night else 0.2)
    for x in (300, 1100, 1920, 2740, 3540):
        c.drawRect(_R(x - 26, 0, x + 26, 1400), fill("#5d636c" if night else "#b9bfc5"))
    c.drawRect(_R(0, 150, W, 190), fill("#5d636c" if night else "#b9bfc5"))
    for x in (1840, 2000):
        c.drawPath(rrect(x - 10, 600, x + 10, 900, 8), fill("#8a9098"))
    reflections(c, 0, 190, W, 1400, 5, 0.1, seed=91)
    far = _blurred(sf.makeImageSnapshot(), 26)
    s = new_surface()
    c = s.getCanvas()
    CT = 1300
    top = poly([(-400, H), (W + 400, H), (W - 120, CT), (120, CT)])
    path_fill(c, top, "#eef0f2")
    c.save()
    c.clipPath(top, skia.ClipOp.kIntersect, True)
    c.drawRect(_R(0, CT, W, H), lin_paint((0, CT), (0, H), [("#ffffff", 0.3), ("#000000", 0.15)]))
    c.restore()
    c.drawRect(_R(120, CT - 8, W - 120, CT + 26), fill("#7a1f1c"))
    c.drawRect(_R(120, CT - 8, W - 120, CT), fill("#9a302a"))
    mat = poly([(1360, CT + 70), (2480, CT + 70), (2720, H - 110), (1120, H - 110)])
    path_fill(c, mat, "#1b1c20")
    c.save()
    c.clipPath(mat, skia.ClipOp.kIntersect, True)
    y = CT + 110
    while y < H - 110:
        c.drawLine(1000, y, 2900, y, stroke("#2c2d33", 7))
        y += 46 + (y - CT) * 0.06
    c.restore()
    # màn LED giá (chỉ số, không chữ)
    c.drawRect(_R(690, 1080, 730, CT), fill("#2b2d33"))
    c.drawPath(rrect(420, 860, 1000, 1090, 18), fill("#1d2226"))
    c.drawPath(rrect(452, 892, 968, 1058, 10), fill("#082424"))
    glow(c, 710, 975, 260, "#3fe0c8", 0.25)
    text_center(c, "000.00", 710, 975, 112, "#3fe0c8", "bold", max_w=480)
    # giá thẻ / kẹo nhiều ô
    c.drawPath(rrect(2860, 720, 3580, CT, 14), fill("#c9ccd2"))
    c.drawRect(_R(2860, 720, 3580, 790), fill(BRAND["green"]))
    rng = random.Random(9)
    for i in range(4):
        for j in range(5):
            x0, y0 = 2890 + j * 136, 815 + i * 118
            col = rng.choice(PRODUCTS[:-1])
            c.drawPath(rrect(x0, y0, x0 + 120, y0 + 100, 8), fill(col))
            c.drawRect(_R(x0 + 18, y0 + 30, x0 + 102, y0 + 62), fill(shade(col, 0.55)))
    # máy quét + khay tiền
    c.drawPath(rrect(1060, 1460, 1260, 1560, 16), fill("#2b2d33"))
    c.drawPath(rrect(1090, 1475, 1230, 1510, 10), fill("#ff4a3a", 0.8))
    if night:
        tint(s, "#c3cbe0", 0.22)
    mid = s.makeImageSnapshot()
    slots = {"peek": {"x": 1920, "y": 1555, "scale": 1.6, "clip_bottom": CT + 6},
             "center": {"x": 1920, "y": 1555, "scale": 1.6, "clip_bottom": CT + 6}}
    return Scene(far, mid, slots=slots, floor_y=1555, parallax=(0.85, 1.0, 1.15),
                 lights=[{"x": 2950, "y": 520, "color": "#ffd98a"}])


# ------------------------------------------------------------------- 10. tường tủ lạnh
def _bottle_rows(c, dl, dt, dr, db, seed, rows=5, cols=("#3aa3a0", "#4fa35a", "#d8423a", "#f08a2c", "#3a78c2", "#f3c94e")):
    for k in range(rows):
        sy0 = dt + (db - dt) * k / rows
        sy1 = dt + (db - dt) * (k + 1) / rows
        c.drawRect(_R(dl, sy1 - 8, dr, sy1), fill("#9aa6b0"))
        rng = random.Random(seed * 10 + k)
        col = rng.choice(cols)
        bx = dl + 10
        while bx < dr - 34:
            bw = rng.uniform(26, 38)
            bh = (sy1 - sy0) * rng.uniform(0.55, 0.8)
            c.drawPath(rrect(bx, sy1 - 8 - bh, bx + bw, sy1 - 8, 6), fill(col))
            c.drawRect(_R(bx + 4, sy1 - 8 - bh * 0.62, bx + bw - 4, sy1 - 8 - bh * 0.34), fill(shade(col, 0.5)))
            c.drawRect(_R(bx + bw * 0.3, sy1 - 8 - bh - 12, bx + bw * 0.7, sy1 - 8 - bh), fill(shade(col, -0.3)))
            bx += bw + 7
            if rng.random() < 0.2:
                col = rng.choice(cols)


def scene_cua_hang_tu_lanh(tod: str) -> Scene:
    night = tod == "night"
    s = new_surface()
    c = s.getCanvas()
    c.drawRect(_R(0, 0, W, H), fill("#dfe3e7"))
    vgrad(c, 0, 0, W, 150, ["#b9c0c6", "#dfe3e7"])
    for x in (700, 1920, 3140):
        _tube(c, x, 40, 640, not night or x != 700)
    c.drawRect(_R(100, 160, 3740, 292), fill(BRAND["green"]))
    c.drawRect(_R(100, 282, 3740, 296), fill(BRAND["orange"]))
    L, R_, T, B = 120, 3720, 310, 1690
    dw = (R_ - L) / 7
    P = Persp(f=1500, cx=W / 2, cy=1100, cam_h=1.5)
    # sàn
    vgrad(c, 0, B + 60, W, H, ["#d3d8de", "#bfc5cc"])
    c.save()
    c.clipRect(_R(0, B + 60, W, H))
    _floor_tiles(c, P, -6, 6, 1.0, 3.9, 0.6, "#b0b7bf")
    c.restore()
    c.drawRect(_R(L - 20, B, R_ + 20, B + 60), fill("#3a3d44"))
    OPEN = 4
    for i in range(7):
        dl, dr = L + i * dw, L + (i + 1) * dw
        c.drawRect(_R(dl, T, dr, B), fill("#17181c"))
        gl, gt, gr, gb = dl + 20, T + 20, dr - 20, B - 20
        if i == OPEN:      # khoang mở: hành lang sương mù phía sau
            vgrad(c, gl, gt, gr, gb, ["#8b98a6", "#c9d3dc", "#e6edf2"])
            vx, vy = (gl + gr) / 2, gt + (gb - gt) * 0.45
            for (ax, ay) in ((gl, gt), (gr, gt), (gl, gb), (gr, gb)):
                c.drawLine(ax, ay, vx + (ax - vx) * 0.25, vy + (ay - vy) * 0.25, stroke("#6b7886", 5, 0.7))
            c.drawRect(_R(vx - (gr - gl) * 0.125, vy - (gb - gt) * 0.14, vx + (gr - gl) * 0.125, vy + (gb - gt) * 0.14),
                       fill("#5d6a78", 0.55))
            glow(c, vx, vy, 340, "#ffffff", 0.45)
            continue
        vgrad(c, gl, gt, gr, gb, ["#f4f9fc", "#d9e6ee"])
        _bottle_rows(c, gl, gt, gr, gb, seed=i + 20)
        if i == 2:    # lon đỏ nổi bật tầng dưới
            c.drawPath(rrect(gl + 160, gb - 190, gl + 260, gb - 20, 14), fill("#d0302a"))
            c.drawRect(_R(gl + 160, gb - 130, gl + 260, gb - 105), fill("#ffffff"))
        rng = random.Random(i * 7)
        for _ in range(26):       # sương bám kính
            x, y = rng.uniform(gl, gr), rng.uniform(gt, gb)
            c.drawPath(oval(x, y, rng.uniform(20, 70), rng.uniform(14, 50)), fill("#ffffff", rng.uniform(0.06, 0.18)))
        c.drawRect(_R(gl, gb - 360, gr, gb), lin_paint((0, gb - 360), (0, gb), [("#ffffff", 0.0), ("#ffffff", 0.5)]))
        reflections(c, gl, gt, gr, gb, 2, 0.16, seed=i + 60)
        hx = gr - 34
        c.drawPath(rrect(hx - 9, T + 420, hx + 9, B - 520, 8), fill("#e4e8ec"))
        c.drawRect(_R(hx - 7, T + 420, hx - 2, B - 520), fill("#ffffff"))
        c.drawPath(rrect(hx - 22, T + 560, hx + 22, T + 610, 6), fill("#d0302a"))
    # cánh cửa hé mở (xoay ra phía camera)
    dl, dr = L + OPEN * dw, L + (OPEN + 1) * dw
    door = poly([(dr, T), (dr + dw * 0.42, T - 50), (dr + dw * 0.42, B + 50), (dr, B)])
    path_fill(c, door, "#17181c")
    inner = poly([(dr + 14, T + 26), (dr + dw * 0.42 - 16, T - 18), (dr + dw * 0.42 - 16, B + 18), (dr + 14, B - 26)])
    path_fill(c, inner, "#cfe0ea", 0.55)
    path_fill(c, inner, "#ffffff", 0.12)
    # sương lan ra sàn
    c.drawRect(_R(0, 1350, W, H), lin_paint((0, 1350), (0, H), [("#eef4f8", 0.0), ("#eef4f8", 0.35), ("#eef4f8", 0.1)]))
    ellipse_glow(c, (dl + dr) / 2, B + 160, 900, 150, "#ffffff", 0.4)
    glow(c, W / 2, 1000, 2200, "#e6f4ff", 0.18)
    if night:
        tint(s, "#6a7aa0", 0.55)
        for i in range(7):
            glow(c, L + (i + 0.5) * dw, 1000, 420, "#cfe6ff", 0.3)
    mid = s.makeImageSnapshot()
    slots = {"left": frac_slot({"x": 0.32, "y": 0.92, "scale": 1.1}),
             "center": frac_slot({"x": 0.50, "y": 0.92, "scale": 1.1}),
             "right": frac_slot({"x": 0.68, "y": 0.92, "scale": 1.1}),
             "open_door": {"x": round((dl + dr) / 2), "y": 1720, "scale": 0.7}}
    signs = [{"text": "COLD DRINKS", "box": [1420, 170, 2420, 280], "style": "plain"}]
    return Scene(None, mid, slots=slots, signs=signs, floor_y=slots["center"]["y"],
                 lights=[{"x": (dl + dr) / 2, "y": 1000, "color": "#e6f4ff"}])


# ------------------------------------------------------------------- 11. trạm xe buýt phố (ngày)
def _shophouse(c, l, r, base, top, col, awning, seed, night=False) -> None:
    rng = random.Random(seed)
    c.drawRect(_R(l, top, r, base), fill(col))
    c.drawRect(_R(l - 12, top - 34, r + 12, top), fill(shade(col, -0.18)))
    c.drawRect(_R(l, top, l + 14, base), fill(shade(col, -0.1)))
    aw_y = base - 360
    fl = top + 60
    while fl < aw_y - 220:            # cửa sổ các tầng
        for k in range(2):
            wl = l + (r - l) * (0.14 + k * 0.42)
            wr = wl + (r - l) * 0.3
            lit = night and rng.random() < 0.4
            c.drawRect(_R(wl, fl, wr, fl + 170), fill("#fff1c8" if lit else shade(col, -0.45)))
            c.drawRect(_R(wl - 10, fl + 170, wr + 10, fl + 186), fill(shade(col, 0.15)))
            for j in range(1, 4):
                c.drawLine(wl + (wr - wl) * j / 4, fl, wl + (wr - wl) * j / 4, fl + 170, stroke(shade(col, -0.3), 5))
        c.drawRect(_R(l + 20, fl + 230, r - 20, fl + 246), fill(shade(col, -0.25)))     # lan can ban công
        for x in range(int(l + 40), int(r - 20), 46):
            c.drawLine(x, fl + 246, x, fl + 300, stroke(shade(col, -0.25), 5))
        fl += 330
    n = max(4, int((r - l) / 70))
    for k in range(n):                 # mái hiên sọc
        x0 = l - 20 + (r - l + 40) * k / n
        x1 = l - 20 + (r - l + 40) * (k + 1) / n
        quad(c, [(x0, aw_y), (x1, aw_y), (x1 + 6, aw_y + 120), (x0 + 6, aw_y + 120)], awning if k % 2 == 0 else "#f4efe4")
    c.drawRect(_R(l + 30, aw_y + 140, r - 30, base), fill("#5d6168"))
    yy = aw_y + 150
    while yy < base:
        c.drawLine(l + 30, yy, r - 30, yy, stroke("#4a4e55", 5))
        yy += 22


def scene_ben_xe_buyt_ngay(tod: str) -> Scene:
    day = tod == "day"
    sf = new_surface()
    c = sf.getCanvas()
    if day:
        _day_sky(c, 0, 1300, "#a8b8c6", "#e2e6e6")
    else:
        _night_sky(c, 0, 1300, seed=17, n_stars=120)
    for i, x in enumerate(range(-100, W + 200, 300)):
        round_tree(c, x, 820, 140, "#93a98a" if day else "#1a2622", "#93a98a" if day else "#1a2622", seed=i + 40)
    far = sf.makeImageSnapshot()
    s = new_surface()
    c = s.getCanvas()
    pal = ["#e8c9a8", "#b9d3c8", "#e6b9b0", "#c9c3e0", "#ead9a0", "#a9c6d9"]
    aw = ["#c8352e", "#3a78c2", "#4fa35a", "#e8833a", "#c74a9a", "#3aa3a0"]
    x = -60
    i = 0
    while x < W:
        w = [560, 640, 600, 700, 580, 660][i % 6]
        _shophouse(c, x, x + w, 1260, 1260 - [980, 1120, 860, 1040, 920, 1180][i % 6], pal[i % 6], aw[i % 6],
                   seed=i, night=not day)
        x += w + 8
        i += 1
    for k, tx in enumerate((520, 1780, 3080)):
        round_tree(c, tx, 1060, 190, "#6f8d60", "#6b4a32", seed=k + 3)
    pole = "#4a4a50"
    for px in (1180, 2900):
        power_pole(c, px, 300, 1260, pole, 26)
    sag_wire(c, -60, 380, 1180, 350, 70, pole, 4)
    sag_wire(c, 1180, 350, 2900, 340, 120, pole, 4)
    sag_wire(c, 1180, 420, 2900, 410, 140, pole, 3)
    sag_wire(c, 2900, 340, W + 60, 380, 60, pole, 4)
    # đường + bó vỉa + vỉa hè
    _road(c, 1260, 1600, "#6e6e72", "#e8c24a", dashed_y=1430)
    k = 0
    for bx in range(-40, W + 80, 120):
        c.drawRect(_R(bx, 1600, bx + 120, 1650), fill("#1a1a1c" if k % 2 == 0 else "#f2f2ee"))
        k += 1
    vgrad(c, 0, 1650, W, H, ["#d8cbb2", "#c9b99c"])
    y = 1650
    step = 50
    while y < H:
        c.drawLine(0, y, W, y, stroke("#b9a98c", 4))
        step *= 1.18
        y += step
    for xx in range(-200, W + 200, 160):
        c.drawLine(xx, 1650, xx + (xx - W / 2) * 0.35, H, stroke("#b9a98c", 4))
    rng = random.Random(5)
    for _ in range(40):
        lx, ly = rng.uniform(0, W), rng.uniform(1680, H)
        c.drawPath(oval(lx, ly, rng.uniform(10, 20), rng.uniform(5, 9)), fill(rng.choice(["#c98a3a", "#a8763a", "#d9a54a"]), 0.85))
    # mái chờ xanh cong
    sl, sr = 1960, 3320
    roof = skia.Path()
    roof.moveTo(sl - 80, 1040)
    roof.quadTo((sl + sr) / 2, 900, sr + 80, 1040)
    roof.lineTo(sr + 80, 1080)
    roof.quadTo((sl + sr) / 2, 950, sl - 80, 1080)
    roof.close()
    path_fill(c, roof, "#2f6fb0")
    c.drawRect(_R(sl + 330, 950, sr - 330, 1018), fill("#1f4f86"))
    c.drawRect(_R(sl + 40, 1100, sr - 40, 1660), fill("#bcd2e2", 0.35))
    reflections(c, sl + 40, 1100, sr - 40, 1660, 3, 0.2, seed=71)
    for px in (sl + 30, sr - 30):
        c.drawRect(_R(px - 14, 1040, px + 14, 1960), fill("#7d8a96"))
    c.drawRect(_R(sl + 40, 1650, sr - 40, 1666), fill("#7d8a96"))
    # hộp quảng cáo trống (sáng)
    c.drawPath(rrect(sr - 360, 1120, sr - 70, 1820, 14), fill("#5d6a78"))
    vgrad(c, sr - 336, 1144, sr - 94, 1796, ["#f6f8fa", "#dde6ee"])
    # ghế kim loại
    bx0, bx1, seat = 2180, 2700, 1745
    c.drawPath(rrect(bx0, seat - 18, bx1, seat + 10, 8), fill("#9aa6b2"))
    for k in range(5):
        c.drawLine(bx0 + 20 + k * 120, seat - 18, bx0 + 20 + k * 120, seat - 170, stroke("#9aa6b2", 10))
    c.drawLine(bx0, seat - 170, bx1, seat - 170, stroke("#9aa6b2", 12))
    for lx in (bx0 + 40, bx1 - 40):
        c.drawRect(_R(lx - 8, seat + 10, lx + 8, 1920), fill("#7d8a96"))
    # cột biển số tuyến + thùng rác xanh
    c.drawRect(_R(1800, 900, 1816, 1960), fill("#7d8a96"))
    c.drawPath(rrect(1690, 880, 1926, 1000, 12), fill("#2f6fb0"))
    c.drawPath(rrect(1460, 1760, 1620, 1960, 18), fill("#3f8f4e"))
    c.drawPath(rrect(1440, 1740, 1640, 1790, 14), fill("#2f7a3e"))
    if not day:
        tint(s, "#7480a8", 0.5)
    mid = s.makeImageSnapshot()
    slots = {"left": frac_slot({"x": 0.25, "y": 0.90, "scale": 0.8}),
             "center": frac_slot({"x": 0.50, "y": 0.90, "scale": 0.8}),
             "right": frac_slot({"x": 0.72, "y": 0.90, "scale": 0.8}),
             "bench": frac_slot({"x": 0.62, "y": 0.88, "scale": 0.8})}
    signs = [{"text": "BUS STOP", "box": [sl + 350, 956, sr - 350, 1012], "style": "plain"},
             {"text": "12", "box": [1710, 895, 1906, 985], "style": "plain"}]
    return Scene(far, mid, slots=slots, signs=signs, floor_y=slots["center"]["y"], parallax=(0.8, 1.0, 1.15))


# ------------------------------------------------------------------- 12/13. đường quê ven kênh đêm mưa (+ xe khách)
def _rural_road(tod: str, seed: int = 0) -> tuple[skia.Image, skia.Surface]:
    dusk = tod == "dusk"
    sf = new_surface()
    c = sf.getCanvas()
    if dusk:
        _dusk_sky(c, 0, 1200, seed=seed + 3)
    else:
        vgrad(c, 0, 0, W, 1200, ["#0d1418", "#1c2a30", "#2a3a3e"], [0, 0.6, 1])
        rng = random.Random(seed + 1)
        for _ in range(14):           # mây thấp khói
            x, y = rng.uniform(-300, W), rng.uniform(120, 760)
            c.drawPath(rrect(x, y, x + rng.uniform(700, 1500), y + rng.uniform(60, 140), 70),
                       fill("#3e5054", rng.uniform(0.25, 0.5)))
    tc = "#0d1517" if not dusk else "#2c2a44"
    for i, x in enumerate(range(-120, W + 200, 260)):
        round_tree(c, x, 1060, 160 + (i % 3) * 34, tc, tc, seed=i + seed)
    far = sf.makeImageSnapshot()
    s = new_surface()
    c = s.getCanvas()
    pole = "#0a0f10" if not dusk else "#1d1a2c"
    for px in (420, 1700, 3300):
        power_pole(c, px, 360, 1200, pole, 24)
    sag_wire(c, -60, 430, 420, 410, 40, pole, 4)
    sag_wire(c, 420, 410, 1700, 400, 90, pole, 4)
    sag_wire(c, 1700, 400, 3300, 410, 110, pole, 4)
    sag_wire(c, 3300, 410, W + 60, 430, 40, pole, 4)
    c.drawRect(_R(0, 1120, W, 1200), fill("#16221c" if not dusk else "#2f3a2e"))
    road = "#1d2326" if not dusk else "#43424e"
    c.drawRect(_R(0, 1200, W, 1440), fill(road))
    c.drawRect(_R(0, 1200, W, 1210), fill("#8a9090", 0.5))
    c.drawRect(_R(0, 1430, W, 1440), fill("#8a9090", 0.5))
    x = -40
    while x < W:
        c.drawRect(_R(x, 1314, x + 200, 1326), fill("#cfc9b6", 0.75))
        x += 400
    # đèn đường cao + nón sáng + vũng sáng
    lx = 2520
    c.drawRect(_R(lx - 12, 330, lx + 12, 1205), fill(pole))
    c.drawPath(capsule(lx, 340, lx - 220, 370, 16, 12), fill(pole))
    lamp = "#ffd98a"
    c.drawPath(poly([(lx - 280, 380), (lx - 160, 380), (lx + 260, 1360), (lx - 720, 1360)]), fill(lamp, 0.13))
    glow(c, lx - 220, 385, 330, lamp, 0.8)
    c.drawPath(oval(lx - 220, 382, 46, 16), fill("#fff3cf"))
    ellipse_glow(c, lx - 230, 1330, 520, 70, lamp, 0.55)
    for k in range(5):              # vệt sáng ướt trên đường
        c.drawRect(_R(lx - 300 + k * 40, 1260 + k * 30, lx - 120 + k * 40, 1266 + k * 30), fill(lamp, 0.25))
    # bờ cỏ + kênh
    c.drawRect(_R(0, 1440, W, 1580), fill("#172219" if not dusk else "#34402f"))
    rng = random.Random(seed + 7)
    for _ in range(160):
        gx = rng.uniform(0, W)
        c.drawLine(gx, 1580, gx + rng.uniform(-14, 14), 1580 - rng.uniform(30, 90), stroke("#22322a", 5))
    water = "#0a1316" if not dusk else "#2a2a46"
    vgrad(c, 0, 1580, W, H, [shade(water, 0.08), water])
    for k in range(14):              # phản chiếu đèn
        y = 1620 + k * 36
        hw = 90 - k * 4 + rng.uniform(-20, 20)
        c.drawRect(_R(lx - 230 - hw, y, lx - 230 + hw, y + 10), fill(lamp, 0.42 - k * 0.025))
    for _ in range(18):              # lá sen
        px_, py_ = rng.uniform(0, W), rng.uniform(1700, 2120)
        r_ = rng.uniform(40, 80)
        c.drawPath(oval(px_, py_, r_, r_ * 0.3), fill("#1e3a2a"))
        c.drawPath(oval(px_ + r_ * 0.3, py_ - 3, r_ * 0.2, r_ * 0.06), fill(water))
    for bx in (60, 260, 3400, 3650):  # lau sậy
        for k in range(14):
            xx = bx + k * 14 + rng.uniform(-6, 6)
            c.drawLine(xx, H, xx + rng.uniform(-40, 40), 1640 - rng.uniform(0, 200), stroke("#13201a", 6))
    c.drawRect(_R(0, 1380, W, 1700), lin_paint((0, 1380), (0, 1700), [("#b8c8c8", 0.0), ("#b8c8c8", 0.12), ("#b8c8c8", 0.0)]))
    return far, s


def scene_duong_que_dem_mua(tod: str) -> Scene:
    far, s = _rural_road(tod)
    if tod == "night":
        tint(s, "#9ab4b4", 0.25)
    mid = s.makeImageSnapshot()
    slots = {k: frac_slot({"x": x, "y": 0.62, "scale": 0.45})
             for k, x in (("road_left", 0.30), ("road_center", 0.50), ("road_right", 0.70), ("center", 0.50))}
    return Scene(far, mid, slots=slots, floor_y=slots["center"]["y"], parallax=(0.8, 1.0, 1.15),
                 lights=[{"x": 2300, "y": 385, "color": "#ffd98a"}])


def scene_xe_khach_tren_duong(tod: str) -> Scene:
    far, s = _rural_road(tod, seed=5)
    c = s.getCanvas()
    # xe khách 16 chỗ trắng, nhìn ngang, chạy trái -> phải
    vl, vr, vt, vb = 1500, 2460, 1010, 1350
    for k in range(7):                 # vệt tốc độ phía sau
        y = vt + 40 + k * 42
        c.drawRect(_R(vl - 700 + k * 40, y, vl - 40, y + 8), lin_paint((vl - 700, 0), (vl, 0), [("#cfd8dc", 0.0), ("#cfd8dc", 0.3)]))
    body = poly([(vl, vb), (vl, vt + 40), (vl + 30, vt), (vr - 170, vt), (vr - 40, vt + 140), (vr, vt + 180), (vr, vb)])
    path_fill(c, body, "#e9ecee")
    c.drawRect(_R(vl, vb - 90, vr, vb - 70), fill("#3a78c2"))
    c.drawRect(_R(vl, vb - 64, vr, vb - 56), fill("#d8423a"))
    win_t, win_b = vt + 40, vt + 160
    xx = vl + 40
    while xx < vr - 260:
        c.drawPath(rrect(xx, win_t, xx + 140, win_b, 12), fill("#1a2230"))
        reflections(c, xx, win_t, xx + 140, win_b, 1, 0.14, seed=int(xx))
        xx += 160
    c.drawPath(poly([(vr - 250, win_t), (vr - 175, win_t), (vr - 70, win_b), (vr - 250, win_b)]), fill("#1a2230"))
    c.drawRect(_R(vr - 470, vt + 40, vr - 466, vb - 90), fill("#b9bfc5"))
    for wx in (vl + 170, vr - 190):
        c.drawCircle(wx, vb, 74, fill("#111316"))
        c.drawCircle(wx, vb, 34, fill("#8a9098"))
        c.drawPath(oval(wx, vb - 8, 96, 70), stroke("#c9ced4", 6))
    c.drawPath(oval((vl + vr) / 2, vb + 70, (vr - vl) * 0.55, 18), fill("#000000", 0.4))
    c.drawPath(rrect(vr - 30, vb - 150, vr + 6, vb - 110, 8), fill("#fff6dc"))
    beam = poly([(vr, vb - 140), (vr + 1300, vb - 260), (vr + 1300, vb + 60), (vr, vb - 116)])
    c.drawPath(beam, lin_paint((vr, 0), (vr + 1300, 0), [("#fff6dc", 0.55), ("#fff6dc", 0.0)]))
    glow(c, vr, vb - 130, 160, "#fff6dc", 0.8)
    c.drawPath(rrect(vl - 8, vb - 150, vl + 16, vb - 116, 6), fill("#ff3b30"))
    glow(c, vl, vb - 132, 90, "#ff3b30", 0.6)
    if tod == "night":
        tint(s, "#9ab4b4", 0.25)
    mid = s.makeImageSnapshot()
    slot = {"x": 1920, "y": 1253, "scale": 0.3, "clip_bottom": win_b}
    slots = {"in_van": dict(slot), "center": dict(slot),
             "roadside": frac_slot({"x": 0.18, "y": 0.64, "scale": 0.45})}
    return Scene(far, mid, slots=slots, floor_y=1330, parallax=(0.8, 1.0, 1.15),
                 lights=[{"x": 2300, "y": 385, "color": "#ffd98a"}])


# ------------------------------------------------------------------- 14. hẻm tối phố
def scene_hem_toi_pho(tod: str) -> Scene:
    night = tod != "day"
    P = Persp(f=1500, cx=W / 2, cy=1120, cam_h=1.5)
    XW, Z0, ZB, YT = 1.45, 0.45, 24.0, 9.0
    s = new_surface()
    c = s.getCanvas()
    vgrad(c, 0, 0, W, 1200, ["#070a14", "#18213a"] if night else ["#9fb0c2", "#d9dfe4"])
    stars(c, 1500, 0, 2340, 700, 40, seed=4)
    path_fill(c, P.plane_y(0, -XW, XW, Z0, ZB), "#2a2c30")
    _floor_tiles(c, P, -XW, XW, Z0, ZB, 0.5, "#232528")
    path_fill(c, P.face_z(ZB, -XW, XW, 0, 4.5), "#1c1e24")
    for k in range(4):
        wl, wt = P.p(-0.9 + k * 0.5, 3.2, ZB)
        wr, wb = P.p(-0.6 + k * 0.5, 2.6, ZB)
        c.drawRect(_R(wl, wt, wr, wb), fill("#f2c46b" if k % 2 == 0 else "#2a2c34"))
    segs = [(Z0, 3.2), (3.2, 6.6), (6.6, 10.5), (10.5, 15.5), (15.5, ZB)]
    cols = ["#5e6a6a", "#6a5e58", "#58606e", "#6e6a5a", "#5a6460", "#685a62"]
    rng = random.Random(21)
    for side in (-1, 1):
        for si, (za, zb) in enumerate(segs):
            col = cols[(si + (side > 0) * 3) % len(cols)]
            ht = YT - rng.uniform(0, 3.5)
            path_fill(c, P.wall_x(side * XW, za, zb, 0, ht), shade(col, -0.12 if side < 0 else 0))
            path_fill(c, P.wall_x(side * XW, za, zb, 0, 0.45), shade(col, -0.4))
            for _ in range(3):                  # vết loang
                zz = rng.uniform(za, zb - 0.4)
                path_fill(c, P.wall_x(side * XW, zz, zz + rng.uniform(0.2, 0.5), rng.uniform(0.6, 1.5),
                                      rng.uniform(2.0, 3.0)), "#000000", 0.12)
            # cửa sắt kéo
            ga, gb = za + 0.25, min(zb - 0.25, za + 2.2)
            if si > 0 and gb - ga > 0.4:
                path_fill(c, P.wall_x(side * XW * 0.995, ga, gb, 0, 2.5), "#3a3e44")
                zz = ga
                while zz < gb:
                    c.drawLine(*P.p(side * XW * 0.993, 0, zz), *P.p(side * XW * 0.993, 2.5, zz),
                               stroke("#262a2f", max(2.0, 30 / zz)))
                    zz += 0.12
                path_fill(c, P.wall_x(side * XW * 0.995, ga - 0.05, gb + 0.05, 2.5, 2.75), "#2a2d33")
            # cửa sổ tầng trên
            for wy in (3.4, 6.2):
                if wy + 1.2 < ht:
                    lit = night and rng.random() < 0.35
                    path_fill(c, P.wall_x(side * XW * 0.995, za + 0.4, za + 1.2, wy, wy + 1.1),
                              "#f2c46b" if lit else "#1a1c22")
                    path_fill(c, P.wall_x(side * XW * 0.995, za + 0.3, za + 1.3, wy - 0.12, wy), shade(col, 0.1))
            # bậc thềm
            path_fill(c, P.plane_y(0.16, side * XW, side * (XW - 0.3), za + 0.2, za + 1.2), shade(col, -0.2))
    # dây điện chằng chịt
    for k in range(16):
        z1, z2 = rng.uniform(1.2, 12), rng.uniform(1.2, 12)
        y1, y2 = rng.uniform(3.6, 5.6), rng.uniform(3.6, 5.6)
        a, b = P.p(-XW, y1, z1), P.p(XW, y2, z2)
        sag_wire(c, *a, *b, rng.uniform(20, 120), "#08090c", max(2.0, 14 / min(z1, z2)))
    # bóng đèn vàng treo
    zb_ = 6.0
    bx, by = P.p(0.1, 3.0, zb_)
    tx, ty = P.p(0.1, 4.2, zb_)
    c.drawLine(tx, ty, bx, by, stroke("#08090c", 4))
    glow(c, bx, by + 14, 900, "#ffcf7a", 0.38)
    glow(c, bx, by + 14, 140, "#ffe0a0", 0.85)
    c.drawPath(oval(bx, by + 14, 16, 22), fill("#fff3cf"))
    fx, fy = P.p(0.1, 0, zb_)
    ellipse_glow(c, fx, fy, 520, 90, "#ffcf7a", 0.45)
    # vũng nước
    for (px_, pz, pw) in ((-0.5, 2.4, 0.7), (0.6, 4.2, 0.5), (-0.2, 8.0, 0.6)):
        cx_, cy_ = P.p(px_, 0, pz)
        rx = P.f * pw / pz
        c.drawPath(oval(cx_, cy_, rx, rx * 0.12), fill("#3a4a62", 0.7))
        c.drawPath(oval(cx_ + rx * 0.2, cy_, rx * 0.35, rx * 0.03), fill("#ffcf7a", 0.35))
    # xe máy dựng sát tường phải
    mz = 3.6
    k_ = P.f / mz
    mx, my = P.p(XW - 0.45, 0, mz)
    wr = 0.3 * k_
    for dx in (-0.62 * k_, 0.62 * k_):
        c.drawCircle(mx + dx, my - wr, wr, fill("#0b0c10"))
        c.drawCircle(mx + dx, my - wr, wr * 0.45, fill("#3a3e46"))
    body = poly([(mx - 0.55 * k_, my - wr), (mx - 0.2 * k_, my - 0.85 * k_), (mx + 0.35 * k_, my - 0.8 * k_),
                 (mx + 0.62 * k_, my - wr * 1.2), (mx + 0.1 * k_, my - wr * 0.9)])
    path_fill(c, body, "#7a2a2a")
    c.drawPath(rrect(mx - 0.4 * k_, my - 0.98 * k_, mx + 0.25 * k_, my - 0.84 * k_, 10), fill("#151519"))
    c.drawLine(mx + 0.45 * k_, my - 0.8 * k_, mx + 0.55 * k_, my - 1.15 * k_, stroke("#151519", 10))
    c.drawLine(mx + 0.45 * k_, my - 1.15 * k_, mx + 0.72 * k_, my - 1.15 * k_, stroke("#151519", 9))
    if night:
        tint(s, "#7e8cb4", 0.4)
        glow(c, bx, by + 14, 200, "#ffe0a0", 0.5)
    mid = s.makeImageSnapshot()
    slots = {"left": P.slot(-0.45, 3.0), "center": P.slot(0.0, 3.0), "right": P.slot(0.45, 3.0),
             "far": P.slot(0.0, 7.5)}
    return Scene(None, mid, slots=slots, floor_y=slots["center"]["y"], lights=[{"x": bx, "y": by, "color": "#ffcf7a"}])


# ------------------------------------------------------------------- 15. chợ đêm
def scene_cho_dem_viet(tod: str) -> Scene:
    night = tod != "day"
    sf = new_surface()
    c = sf.getCanvas()
    _night_sky(c, 0, 1100, seed=33, n_stars=150)
    x = -40
    rng = random.Random(3)
    while x < W:
        w = rng.uniform(380, 620)
        top = rng.uniform(200, 520)
        c.drawRect(_R(x, top, x + w - 10, 1300), fill(rng.choice(["#1a1e2c", "#1e2230", "#161a26"])))
        for wy in range(int(top + 80), 1000, 190):
            for wx in (x + w * 0.2, x + w * 0.58):
                if rng.random() < 0.3:
                    c.drawRect(_R(wx, wy, wx + w * 0.2, wy + 110), fill("#f2c46b", 0.8))
        x += w
    far = sf.makeImageSnapshot()
    s = new_surface()
    c = s.getCanvas()
    vgrad(c, 0, 1640, W, H, ["#2a2a30", "#17171b"])
    tarps = ["#2f6fb0", "#c8352e", "#2f6fb0", "#3a8a5a", "#c8352e"]
    stalls = [(-80, 700), (640, 1440), (2780, 3480), (3500, 4000)]
    goods = ["#f08a2c", "#f3c94e", "#d8423a", "#4fa35a", "#f4efe4"]
    for i, (l, r) in enumerate(stalls):
        tc = tarps[i % len(tarps)]
        for px in (l + 30, r - 30):
            c.drawRect(_R(px - 10, 960, px + 10, 1660), fill("#4a4a52"))
        quad(c, [(l - 40, 1000), (r + 40, 1000), (r - 20, 860), (l + 20, 860)], tc)
        for k in range(5):
            xx = l - 40 + (r - l + 80) * (k + 0.5) / 5
            c.drawPath(oval(xx, 1004, (r - l) / 10, 22), fill(shade(tc, -0.2)))
        glow(c, (l + r) / 2, 1080, 520, "#ffcf7a", 0.35)
        c.drawRect(_R(l + 40, 1450, r - 40, 1660), fill("#6b4a32"))
        c.drawRect(_R(l + 30, 1430, r - 30, 1460), fill("#8a6444"))
        gx = l + 70
        while gx < r - 110:          # mẹt hàng
            col = rng.choice(goods)
            c.drawPath(oval(gx + 40, 1420, 58, 18), fill("#c9a46a"))
            for k in range(5):
                c.drawCircle(gx + 14 + k * 13, 1405 - (k % 2) * 10, 16, fill(col))
            gx += 130
    _bulb_string(c, -60, 820, 1960, 760, 90, 12)
    _bulb_string(c, 1960, 760, W + 60, 830, 90, 12)
    _bulb_string(c, -60, 560, W + 60, 600, 160, 22)
    # xe đẩy đồ ăn có nồi bốc khói
    cl, cr_ = 1720, 2520
    ct = 1310
    c.drawPath(rrect(cl, ct, cr_, ct + 230, 10), fill("#d9e6ee", 0.5))
    c.drawPath(rrect(cl, ct, cr_, ct + 230, 10), stroke("#c9d1d7", 10))
    reflections(c, cl, ct, cr_, ct + 230, 2, 0.22, seed=8)
    c.drawRect(_R(cl - 20, ct + 230, cr_ + 20, ct + 260), fill("#e9ecee"))
    c.drawRect(_R(cl, ct + 260, cr_, 1760), fill("#c8352e"))
    c.drawRect(_R(cl + 40, ct + 300, cr_ - 40, ct + 420), fill("#f3c94e"))
    c.drawPath(rrect(cr_ - 260, ct - 130, cr_ - 60, ct, 20), fill("#9aa0a6"))
    c.drawPath(oval(cr_ - 160, ct - 130, 104, 22), fill("#7d838a"))
    for k in range(4):
        c.drawPath(oval(cr_ - 160 + (k % 2) * 40 - 20, ct - 230 - k * 110, 80 + k * 24, 46 + k * 10),
                   fill("#f4f4f4", 0.3 - k * 0.06))
    for wx in (cl + 120, cr_ - 120):
        c.drawCircle(wx, 1780, 64, fill("#111316"))
        c.drawCircle(wx, 1780, 26, fill("#8a9098"))
    glow(c, (cl + cr_) / 2, 1400, 600, "#ffcf7a", 0.3)
    # ghế nhựa đỏ tiền cảnh
    for (sx, sb) in ((300, 2040), (560, 2080), (3250, 2050), (3560, 2090), (1400, 1880)):
        _plastic_stool(c, sx, sb, 170)
    _plastic_stool(c, 430, 1960, 150, "#3a78c2")
    if not night:
        tint(s, "#fff4e0", 0.05)
    mid = s.makeImageSnapshot()
    slots = {"left": frac_slot({"x": 0.25, "y": 0.90, "scale": 1.0}),
             "center": frac_slot({"x": 0.50, "y": 0.90, "scale": 1.0}),
             "right": frac_slot({"x": 0.75, "y": 0.90, "scale": 1.0}),
             "behind_cart": {"x": 2112, "y": 1771, "scale": 0.95, "clip_bottom": ct + 10}}
    signs = [{"text": "NOODLE SOUP", "box": [cl + 50, ct + 305, cr_ - 50, ct + 415], "style": "plain"}]
    return Scene(far, mid, slots=slots, signs=signs, floor_y=slots["center"]["y"], parallax=(0.8, 1.0, 1.15),
                 lights=[{"x": 1960, "y": 900, "color": "#ffcf7a"}])


# ------------------------------------------------------------------- 16. phòng khách nhà phố
def _room_shell(c, wall, floor_a, floor_b, back_y=1450, pattern=True) -> Persp:
    """Phòng nhìn thẳng: tường hậu tới back_y, sàn gạch phối cảnh. Trả về Persp của sàn."""
    c.drawRect(_R(0, 0, W, back_y), fill(wall))
    vgrad(c, 0, 0, W, 260, [shade(wall, -0.2), wall])
    c.drawRect(_R(0, back_y - 40, W, back_y), fill(shade(wall, -0.25)))
    P = Persp(f=1500, cx=W / 2, cy=back_y - 1500 * 1.5 / 5.0, cam_h=1.5)
    z0 = 1.5 * 1500 / (H + 40 - P.cy)
    c.drawRect(_R(0, back_y, W, H), fill(floor_a))
    step = 0.42
    xi = -12
    while xi * step < 12 * step:
        zi = 0
        z = 5.0
        while z > z0 - step:
            if (xi + zi) % 2 == 0:
                path_fill(c, P.plane_y(0, xi * step, (xi + 1) * step, z - step, z), floor_b)
                if pattern:
                    mx, mz = (xi + 0.5) * step, z - step / 2
                    path_fill(c, P.quad([(mx - step * 0.3, 0, mz), (mx, 0, mz - step * 0.3),
                                         (mx + step * 0.3, 0, mz), (mx, 0, mz + step * 0.3)]), floor_a)
            z -= step
            zi += 1
        xi += 1
    return P


def scene_nha_phong_khach(tod: str) -> Scene:
    night = tod == "night"
    day = tod == "day"
    s = new_surface()
    c = s.getCanvas()
    P = _room_shell(c, "#e6d6b8", "#c9b48e", "#8a5a42")
    # cửa sổ song sắt (ánh ngoài)
    if night:
        _barred_window(c, 2340, 360, 3060, 980, "#0d1426", "#1d2742")
    else:
        _barred_window(c, 2340, 360, 3060, 980, "#c9d8e4", "#eef2f4")
    # bàn thờ treo tường + đèn đỏ
    al, at_ = 1520, 420
    c.drawRect(_R(al, at_, al + 560, at_ + 40), fill("#6b2a1a"))
    c.drawRect(_R(al + 20, at_ + 40, al + 540, at_ + 230), fill("#8a3a22"))
    c.drawRect(_R(al, at_ + 230, al + 560, at_ + 262), fill("#6b2a1a"))
    for k in range(3):
        c.drawPath(rrect(al + 90 + k * 150, at_ + 110, al + 160 + k * 150, at_ + 230, 10), fill("#c99a3c"))
    for x in (al + 50, al + 510):
        c.drawCircle(x, at_ + 150, 20, fill("#ff3b30"))
        glow(c, x, at_ + 150, 160, "#ff3b30", 0.6)
    glow(c, al + 280, at_ + 150, 520, "#ff5a3a", 0.25)
    # lịch treo (chỉ số)
    c.drawRect(_R(820, 420, 1060, 740), fill("#f4efe4"))
    c.drawRect(_R(820, 420, 1060, 500), fill("#c8352e"))
    text_center(c, "15", 940, 610, 120, "#c8352e", "extrabold")
    # tivi cũ trên kệ
    c.drawRect(_R(200, 1080, 1000, 1440), fill("#6b4a32"))
    c.drawRect(_R(220, 1100, 980, 1150), fill(shade("#6b4a32", 0.12)))
    c.drawPath(rrect(330, 760, 870, 1080, 24), fill("#2b2d33"))
    c.drawPath(rrect(370, 800, 760, 1040, 30), fill("#41505a" if not night else "#5a7a8a"))
    if night:
        glow(c, 565, 920, 420, "#9fd0ff", 0.35)
    for k in range(3):
        c.drawCircle(815, 860 + k * 60, 16, fill("#8a9098"))
    # bộ ghế gỗ + bàn trà
    wood = "#7a4a2a"
    sl, sr, sb = 1340, 2380, 1420
    c.drawPath(rrect(sl, sb - 470, sr, sb - 220, 30), fill(shade(wood, -0.12)))
    for k in range(5):
        c.drawRect(_R(sl + 70 + k * 210, sb - 440, sl + 160 + k * 210, sb - 240), fill(shade(wood, -0.3)))
    c.drawPath(rrect(sl - 40, sb - 230, sr + 40, sb - 170, 14), fill(wood))
    c.drawRect(_R(sl - 40, sb - 170, sr + 40, sb - 130), fill(shade(wood, -0.25)))
    for x in (sl - 20, sr + 20):
        c.drawPath(rrect(x - 30, sb - 380, x + 30, sb, 14), fill(shade(wood, -0.08)))
    for x in (sl + 40, sr - 40):
        c.drawRect(_R(x - 16, sb - 130, x + 16, sb), fill(shade(wood, -0.3)))
    tl, tr, tt = 1520, 2200, 1560
    c.drawPath(rrect(tl, tt, tr, tt + 50, 16), fill(shade(wood, 0.1)))
    c.drawRect(_R(tl + 20, tt + 50, tr - 20, tt + 80), fill(shade(wood, -0.25)))
    for x in (tl + 50, tr - 50):
        c.drawRect(_R(x - 18, tt + 80, x + 18, tt + 260), fill(shade(wood, -0.3)))
    c.drawPath(oval(1760, tt - 10, 70, 16), fill("#f4efe4"))
    c.drawPath(rrect(1720, tt - 90, 1800, tt - 10, 18), fill("#f4efe4"))
    for k in range(3):
        c.drawPath(rrect(1880 + k * 70, tt - 60, 1930 + k * 70, tt - 8, 10), fill("#f4efe4"))
    _ceiling_fan(c, 1920, 180, 760)
    # ánh sáng
    if night:
        tint(s, "#5a6890", 0.55)
        glow(c, al + 280, at_ + 150, 600, "#ff5a3a", 0.35)
        glow(c, 565, 920, 380, "#9fd0ff", 0.3)
    elif day:
        glow(c, 2700, 700, 1100, "#fff6dc", 0.3)
    else:
        glow(c, 1920, 300, 1500, "#fff1c8", 0.25)
    _vignette(c, 0.4)
    mid = s.makeImageSnapshot()
    slots = {"left": frac_slot({"x": 0.28, "y": 0.88, "scale": 1.0}),
             "center": frac_slot({"x": 0.50, "y": 0.88, "scale": 1.0}),
             "right": frac_slot({"x": 0.72, "y": 0.88, "scale": 1.0}),
             "sofa": frac_slot({"x": 0.42, "y": 0.84, "scale": 0.95})}
    return Scene(None, mid, slots=slots, floor_y=slots["center"]["y"])


# ------------------------------------------------------------------- 17. phòng trọ
def scene_phong_ngu_tro(tod: str) -> Scene:
    night = tod == "night"
    s = new_surface()
    c = s.getCanvas()
    _room_shell(c, "#cfd2c4", "#9a9a90", "#8a8a80", back_y=1500, pattern=False)
    rng = random.Random(14)
    for _ in range(9):                  # tường loang
        x, y = rng.uniform(0, W), rng.uniform(200, 1300)
        c.drawPath(oval(x, y, rng.uniform(80, 260), rng.uniform(60, 200)), fill("#7a7a60", rng.uniform(0.04, 0.09)))
    _tube(c, 1760, 260, 700, on=not night)
    # cửa sổ nhỏ ánh trăng + vệt sáng xuống sàn
    wl, wt, wr, wb = 1500, 480, 1960, 880
    _barred_window(c, wl, wt, wr, wb, "#1a2a4a" if night else "#c9d8e4", "#3a5080" if night else "#eef2f4",
                   frame="#8a8a80", bars="#4a4a48", n=4)
    if night:
        c.drawCircle(1820, 600, 46, fill("#f1ead2"))
        glow(c, 1820, 600, 220, "#f1ead2", 0.5)
        c.drawPath(poly([(wl, wb), (wr, wb), (wr + 520, 2000), (wl + 200, 2000)]), fill("#bcd2ff", 0.12))
    # giường sắt + màn
    bl, br, bt = 220, 1320, 1360
    c.drawPath(rrect(bl, bt, br, bt + 120, 20), fill("#e9e2d2"))
    c.drawRect(_R(bl, bt + 120, br, bt + 160), fill("#3a5a7a"))
    for x in (bl + 20, br - 20):
        c.drawRect(_R(x - 12, 560, x + 12, 1740), fill("#4a5560"))
    c.drawLine(bl + 20, 1040, br - 20, 1040, stroke("#4a5560", 14))
    for k in range(6):
        c.drawLine(bl + 40 + k * 200, 1040, bl + 40 + k * 200, bt, stroke("#4a5560", 8))
    c.drawPath(poly([(bl - 30, 1700), (br + 30, 1700), (br - 40, 560), (bl + 40, 560)]), fill("#f4f4f0", 0.28))
    c.drawPath(poly([(bl - 30, 1700), (br + 30, 1700), (br - 40, 560), (bl + 40, 560)]), stroke("#ffffff", 4, 0.4))
    c.drawPath(rrect(bl + 80, bt - 70, bl + 380, bt + 10, 30), fill("#f4f4f0"))
    # quạt đứng
    fx_, fb = 2150, 1760
    c.drawPath(oval(fx_, fb, 130, 24), fill("#2b2d33"))
    c.drawRect(_R(fx_ - 10, 1180, fx_ + 10, fb), fill("#c9ccd2"))
    c.drawCircle(fx_, 1080, 150, stroke("#c9ccd2", 10))
    for k in range(3):
        a = k / 3 * math.tau + 0.3
        c.drawPath(oval(fx_ + math.cos(a) * 70, 1080 + math.sin(a) * 70, 62, 36), fill("#7ab0d8", 0.85))
    c.drawCircle(fx_, 1080, 26, fill("#3a78c2"))
    # tủ nhựa khoá kéo
    c.drawPath(rrect(2340, 700, 2780, 1560, 24), fill("#d77aa8"))
    c.drawRect(_R(2340, 700, 2780, 780), fill(shade("#d77aa8", -0.2)))
    c.drawLine(2560, 800, 2560, 1540, stroke("#f4efe4", 6))
    for k in range(4):
        c.drawLine(2360, 900 + k * 160, 2760, 900 + k * 160, stroke(shade("#d77aa8", -0.12), 4))
    # cửa ra vào
    dl, dr = 2960, 3420
    c.drawRect(_R(dl - 30, 520, dr + 30, 1520), fill("#6a6050"))
    c.drawRect(_R(dl, 550, dr, 1500), fill("#8a6a4a"))
    for (pt, pb) in ((620, 980), (1060, 1440)):
        c.drawRect(_R(dl + 50, pt, dr - 50, pb), stroke(shade("#8a6a4a", -0.25), 8))
    c.drawCircle(dr - 60, 1060, 16, fill("#c9ccd2"))
    # móc treo quần áo
    c.drawRect(_R(3500, 560, 3800, 580), fill("#4a4a48"))
    for k, col in enumerate(("#3a78c2", "#e8833a", "#4fa35a")):
        x = 3540 + k * 100
        quad(c, [(x - 50, 600), (x + 50, 600), (x + 60, 900), (x - 60, 900)], col)
        c.drawPath(oval(x, 600, 30, 14), fill(shade(col, -0.2)))
    if night:
        tint(s, "#34426e", 0.72)
        glow(c, 1820, 600, 260, "#f1ead2", 0.45)
        c.drawPath(poly([(wl, wb), (wr, wb), (wr + 520, 2000), (wl + 200, 2000)]), fill("#bcd2ff", 0.1))
    _vignette(c, 0.5)
    mid = s.makeImageSnapshot()
    slots = {"bed": frac_slot({"x": 0.40, "y": 0.80, "scale": 0.95}),
             "center": frac_slot({"x": 0.55, "y": 0.90, "scale": 1.0}),
             "door": frac_slot({"x": 0.82, "y": 0.90, "scale": 1.0})}
    return Scene(None, mid, slots=slots, floor_y=slots["center"]["y"],
                 lights=[{"x": 1820, "y": 600, "color": "#bcd2ff"}])


# ------------------------------------------------------------------- 18/19. hành lang 1 điểm tụ
def _corridor(c, P, XW, YC, Z0, ZB, lower, upper, dado, floor_c, ceil_c, back, right_open=False) -> None:
    path_fill(c, P.plane_y(YC, -XW, XW, Z0, ZB), ceil_c)
    for sd in (-1, 1):
        if sd > 0 and right_open:
            continue
        k = -0.07 if sd < 0 else 0.0
        path_fill(c, P.wall_x(sd * XW, Z0, ZB, 0, YC), shade(upper, k))
        path_fill(c, P.wall_x(sd * XW, Z0, ZB, 0, dado), shade(lower, k))
        path_fill(c, P.wall_x(sd * XW * 0.999, Z0, ZB, dado - 0.05, dado), shade(lower, -0.3))
    path_fill(c, P.plane_y(0, -XW, XW, Z0, ZB), floor_c)
    path_fill(c, P.face_z(ZB, -XW, XW, 0, YC), back)


def scene_hanh_lang_benh_vien(tod: str) -> Scene:
    night = tod == "night"
    P = Persp(f=1500, cx=W / 2, cy=1100, cam_h=1.55)
    XW, YC, Z0, ZB = 1.6, 2.9, 0.45, 20.0
    s = new_surface()
    c = s.getCanvas()
    _corridor(c, P, XW, YC, Z0, ZB, "#9cc4b0", "#eef0ea", 1.2, "#c9cfcc", "#e4e6e2", "#dfe4df")
    _floor_tiles(c, P, -XW, XW, Z0, ZB, 0.8, "#b4bbb7")
    # cửa cuối hành lang + biển lối thoát
    dl, dt = P.p(-0.5, 2.1, ZB)
    dr, db = P.p(0.5, 0, ZB)
    c.drawRect(_R(dl, dt, dr, db), fill("#7d9a8e"))
    c.drawLine((dl + dr) / 2, dt, (dl + dr) / 2, db, stroke("#5a7468", 4))
    el, et = P.p(-0.35, 2.55, ZB)
    er, eb = P.p(0.35, 2.28, ZB)
    c.drawRect(_R(el, et, er, eb), fill("#1f9a4e"))
    glow(c, (el + er) / 2, (et + eb) / 2, 220, "#3cff7a", 0.5)
    # cửa phòng bên trái + ghế inox bên phải
    zz = 1.6
    i = 0
    while zz < ZB - 2:
        path_fill(c, P.wall_x(-XW * 0.998, zz, zz + 1.0, 0, 2.15), "#7d9a8e" if i % 2 == 0 else "#86a296")
        path_fill(c, P.wall_x(-XW * 0.997, zz + 0.05, zz + 0.95, 2.15, 2.22), "#5a7468")
        path_fill(c, P.wall_x(-XW * 0.996, zz + 0.3, zz + 0.7, 1.75, 1.95), "#f4f6f8")
        hx, hy = P.p(-XW * 0.995, 1.0, zz + 0.85)
        c.drawCircle(hx, hy, max(2.0, 40 / zz), fill("#c9ccd2"))
        zz += 3.2
        i += 1
    zz = 3.4
    while zz < 13:
        for k in range(4):
            za = zz + k * 0.55
            path_fill(c, P.face_z(za + 0.05, XW - 0.48, XW - 0.44, 0, 0.4), "#6b7078")
            path_fill(c, P.wall_x(XW - 0.04, za, za + 0.45, 0.5, 0.95), "#a9b0b6")
            path_fill(c, P.plane_y(0.45, XW - 0.5, XW - 0.02, za, za + 0.45), "#c9d0d6")
            path_fill(c, P.face_z(za, XW - 0.5, XW - 0.02, 0.38, 0.45), "#8a9098")
        zz += 4.2
    # xe lăn bỏ trống
    wz, wx = 5.2, -0.55
    k_ = P.f / wz
    gx, gy = P.p(wx, 0, wz)
    c.drawCircle(gx, gy - 0.3 * k_, 0.3 * k_, stroke("#5a6068", max(4.0, 0.04 * k_)))
    c.drawCircle(gx + 0.42 * k_, gy - 0.1 * k_, 0.1 * k_, stroke("#5a6068", max(3.0, 0.03 * k_)))
    c.drawRect(_R(gx - 0.1 * k_, gy - 0.55 * k_, gx + 0.45 * k_, gy - 0.47 * k_), fill("#3a5a8a"))
    c.drawRect(_R(gx - 0.12 * k_, gy - 1.0 * k_, gx - 0.04 * k_, gy - 0.47 * k_), fill("#3a5a8a"))
    c.drawLine(gx - 0.08 * k_, gy - 1.0 * k_, gx - 0.25 * k_, gy - 1.0 * k_, stroke("#5a6068", max(3.0, 0.03 * k_)))
    # đèn trần (1 chập chờn)
    for j, zc in enumerate((1.5, 4.0, 7.0, 10.5, 14.5)):
        on = not (night and j == 2)
        q = P.plane_y(YC - 0.01, -0.4, 0.4, zc - 0.5, zc + 0.5)
        path_fill(c, q, "#ffffff" if on else "#b9c0bc")
        if on:
            x, y = P.p(0, YC, zc)
            ellipse_glow(c, x, y + 10, 900 / zc, 240 / zc, "#f4fff8", 0.5)
            fx_, fy_ = P.p(0, 0, zc + 0.5)
            ellipse_glow(c, fx_, fy_, 600 / zc, 90 / zc, "#ffffff", 0.3)
    if night:
        tint(s, "#6a8a8a", 0.5)
        g = rad_paint(W / 2, 1100, 2400, [("#000000", 0.0), ("#030806", 0.7)], [0.25, 1])
        c.drawRect(_R(0, 0, W, H), g)
        glow(c, (el + er) / 2, (et + eb) / 2, 260, "#3cff7a", 0.45)
    mid = s.makeImageSnapshot()
    slots = {"left": P.slot(-0.5, 3.4), "center": P.slot(0.0, 3.4), "right": P.slot(0.5, 3.4),
             "far": P.slot(0.0, 9.0)}
    signs = [{"text": "EXIT", "box": [round(el), round(et), round(er), round(eb)], "style": "plain"}]
    return Scene(None, mid, slots=slots, signs=signs, floor_y=slots["center"]["y"],
                 lights=[{"x": W / 2, "y": 700, "color": "#f4fff8"}])


def scene_hanh_lang_chung_cu(tod: str) -> Scene:
    night = tod == "night"
    P = Persp(f=1500, cx=W / 2, cy=1100, cam_h=1.55)
    XW, YC, Z0, ZB = 1.3, 2.8, 0.45, 18.0
    s = new_surface()
    c = s.getCanvas()
    # trời + nhà xa bên phải (hành lang hở)
    if night:
        _night_sky(c, 0, H, seed=41, n_stars=120)
    else:
        _day_sky(c, 0, H)
    rng = random.Random(6)
    x = 1900
    while x < W:
        w = rng.uniform(220, 420)
        top = rng.uniform(300, 900)
        c.drawRect(_R(x, top, x + w, 1500), fill("#141a2a" if night else "#8a96a6"))
        for wy in range(int(top + 50), 1400, 110):
            for wx in range(int(x + 30), int(x + w - 40), 80):
                if rng.random() < 0.25:
                    c.drawRect(_R(wx, wy, wx + 40, wy + 60), fill("#f2c46b" if night else "#c9d3dc", 0.8))
        x += w + 20
    _corridor(c, P, XW, YC, Z0, ZB, "#7a8a7a", "#c9c4b4", 1.0, "#8a8680", "#bdb8a8", "#a9a494", right_open=True)
    _floor_tiles(c, P, -XW, XW, Z0, ZB, 0.5, "#7a7670")
    # lan can + cột (bên phải)
    path_fill(c, P.wall_x(XW, Z0, ZB, 0, 1.0), "#b4ae9c")
    path_fill(c, P.plane_y(1.0, XW - 0.12, XW, Z0, ZB), "#d6d0be")
    zz = 1.2
    while zz < ZB:
        path_fill(c, P.wall_x(XW, zz, zz + 0.25, 1.0, YC), "#a9a494")
        path_fill(c, P.face_z(zz, XW - 0.25, XW, 0, YC), "#c4bfae")
        zz += 3.0
    # dãy cửa sắt xanh + dép + giấy quảng cáo
    zz = 1.4
    while zz < ZB - 1.5:
        path_fill(c, P.wall_x(-XW * 0.998, zz, zz + 0.95, 0, 2.1), "#2f6a5a")
        z2 = zz + 0.08
        while z2 < zz + 0.9:
            c.drawLine(*P.p(-XW * 0.996, 0.05, z2), *P.p(-XW * 0.996, 2.05, z2), stroke("#1f4a3e", max(2.0, 24 / z2)))
            z2 += 0.1
        path_fill(c, P.wall_x(-XW * 0.998, zz + 0.95, zz + 1.25, 1.2, 1.75), "#1a1c22")
        for k in range(rng.randint(1, 3)):
            pz = zz + 1.3 + k * 0.22
            path_fill(c, P.wall_x(-XW * 0.997, pz, pz + 0.16, 1.3 + k * 0.1, 1.55 + k * 0.1), "#f4efe4")
        sx_, sy_ = P.p(-XW + 0.25, 0, zz + 0.5)
        sw = P.f * 0.1 / (zz + 0.5)
        c.drawPath(oval(sx_, sy_, sw, sw * 0.35), fill(rng.choice(["#3a78c2", "#d8423a", "#2b2d33"])))
        c.drawPath(oval(sx_ + sw * 1.3, sy_ + sw * 0.1, sw, sw * 0.35), fill("#3a78c2"))
        zz += 2.6
    # đèn tuýp trên trần
    for j, zc in enumerate((1.6, 4.5, 8.0, 12.0)):
        on = not (night and j == 1)
        a, b = P.p(-0.5, YC - 0.02, zc), P.p(0.5, YC - 0.02, zc)
        c.drawLine(*a, *b, stroke("#ffffff" if on else "#8a9098", max(4.0, 60 / zc)))
        if on:
            ellipse_glow(c, (a[0] + b[0]) / 2, a[1] + 20, 800 / zc, 260 / zc, "#eaf6ff", 0.5)
    if night:
        tint(s, "#46557e", 0.66)
        g = rad_paint(W / 2, 1100, 2400, [("#000000", 0.0), ("#04060c", 0.65)], [0.3, 1])
        c.drawRect(_R(0, 0, W, H), g)
    mid = s.makeImageSnapshot()
    slots = {"left": P.slot(-0.45, 3.2), "center": P.slot(0.0, 3.2), "right": P.slot(0.45, 3.2),
             "far": P.slot(0.0, 8.5)}
    return Scene(None, mid, slots=slots, floor_y=slots["center"]["y"])


# ------------------------------------------------------------------- 20. lớp học
def scene_lop_hoc(tod: str) -> Scene:
    day = tod == "day"
    s = new_surface()
    c = s.getCanvas()
    _room_shell(c, "#ecdca0", "#b9a27a", "#a8916a", back_y=1420, pattern=False)
    c.drawRect(_R(0, 1100, W, 1420), fill("#d9c48a"))
    # cửa sổ chớp xanh hai bên
    for wl in (150, 3090):
        wr = wl + 600
        vgrad(c, wl, 420, wr, 1060, ["#cfe0ea", "#f2f4ee"] if day else ["#0d1426", "#1d2742"])
        for k in range(2):
            sl_ = wl + k * 300
            for j in range(12):
                y = 430 + j * 52
                quad(c, [(sl_ + 14, y), (sl_ + 286, y), (sl_ + 286, y + 30), (sl_ + 14, y + 40)], "#3f8a6a")
            c.drawRect(_R(sl_, 420, sl_ + 300, 1060), stroke("#2f6a52", 14))
        c.drawRect(_R(wl - 30, 1060, wr + 30, 1090), fill("#c9b480"))
    # khung trống trên bảng
    for fx_ in (1460, 1920, 2380):
        c.drawRect(_R(fx_ - 150, 230, fx_ + 150, 440), fill("#7a5a3a"))
        c.drawRect(_R(fx_ - 128, 252, fx_ + 128, 418), fill("#e9e2cc"))
    # bảng đen xanh
    bl, bt, br, bb = 1000, 520, 2840, 1180
    c.drawRect(_R(bl - 34, bt - 34, br + 34, bb + 34), fill("#7a5a3a"))
    vgrad(c, bl, bt, br, bb, ["#2f5a46", "#244a3a"])
    rng = random.Random(2)
    for _ in range(10):
        x, y = rng.uniform(bl + 80, br - 300), rng.uniform(bt + 60, bb - 60)
        c.drawPath(rrect(x, y, x + rng.uniform(150, 400), y + 18, 9), fill("#e6efe8", 0.1))
    c.drawRect(_R(bl - 20, bb + 34, br + 20, bb + 60), fill("#8a6a4a"))
    c.drawRect(_R(bl + 120, bb + 20, bl + 200, bb + 34), fill("#f4f4f0"))
    # bục + bàn giáo viên
    c.drawRect(_R(700, 1380, 3140, 1460), fill("#8a6a4a"))
    c.drawRect(_R(700, 1360, 3140, 1384), fill("#a8845a"))
    c.drawRect(_R(2620, 1180, 3120, 1220), fill("#9a6a42"))
    c.drawRect(_R(2640, 1220, 3100, 1380), fill("#7a5232"))
    # quạt trần
    _ceiling_fan(c, 1100, 150, 560)
    _ceiling_fan(c, 2740, 150, 560)
    # bàn ghế học sinh (hai bên, chừa lối giữa)
    for side in (-1, 1):
        for row, (y, sc) in enumerate(((1560, 0.8), (1720, 0.92), (1900, 1.05))):
            for k in range(2):
                cxk = W / 2 + side * (480 + k * 620) * sc * 1.05
                w2 = 260 * sc
                c.drawRect(_R(cxk - w2, y - 150 * sc, cxk + w2, y - 120 * sc), fill("#a8744a"))
                c.drawRect(_R(cxk - w2, y - 120 * sc, cxk + w2, y - 20 * sc), fill("#7a5232"))
                c.drawRect(_R(cxk - w2 * 0.9, y - 60 * sc, cxk + w2 * 0.9, y - 40 * sc), fill("#8a5a3a"))
                for lx in (cxk - w2 + 14, cxk + w2 - 30):
                    c.drawRect(_R(lx, y - 20 * sc, lx + 16, y + 40 * sc), fill("#5a3a22"))
    if day:
        glow(c, 450, 740, 900, "#fff6dc", 0.25)
        glow(c, 3390, 740, 900, "#fff6dc", 0.25)
    else:
        tint(s, "#4a5a8a", 0.62)
    _vignette(c, 0.35)
    mid = s.makeImageSnapshot()
    slots = {"teacher": frac_slot({"x": 0.50, "y": 0.86, "scale": 0.95}),
             "left": frac_slot({"x": 0.25, "y": 0.92, "scale": 1.05}),
             "right": frac_slot({"x": 0.75, "y": 0.92, "scale": 1.05}),
             "center": frac_slot({"x": 0.50, "y": 0.86, "scale": 0.95})}
    return Scene(None, mid, slots=slots, floor_y=slots["center"]["y"])


# ------------------------------------------------------------------- 21. phòng làm việc đồn công an
def scene_don_cong_an(tod: str) -> Scene:
    night = tod == "night"
    s = new_surface()
    c = s.getCanvas()
    _room_shell(c, "#ece4cc", "#b4b4ae", "#a4a49e", back_y=1460, pattern=False)
    c.drawRect(_R(0, 1240, W, 1460), fill("#c9bf9e"))
    _barred_window(c, 1180, 380, 1760, 900, "#0d1426" if night else "#cfdde6", "#1d2742" if night else "#eef2f4",
                   frame="#8a8070", bars="#5a5248", n=4)
    # bảng ghim giấy
    c.drawRect(_R(260, 440, 980, 900), fill("#6b4a32"))
    c.drawRect(_R(284, 464, 956, 876), fill("#c49a6a"))
    rng = random.Random(4)
    for k in range(7):
        x, y = 310 + (k % 4) * 160 + rng.uniform(-10, 10), 490 + (k // 4) * 190 + rng.uniform(-10, 10)
        c.save()
        c.rotate(rng.uniform(-6, 6), x + 60, y + 80)
        c.drawRect(_R(x, y, x + 130, y + 165), fill("#f4f1e8"))
        for j in range(4):
            c.drawLine(x + 16, y + 40 + j * 28, x + 112 - (j % 2) * 30, y + 40 + j * 28, stroke("#8a8a8a", 5))
        c.restore()
        c.drawCircle(x + 65, y + 12, 9, fill(rng.choice(["#d0302a", "#3a78c2", "#f3c94e"])))
    # quạt treo tường
    c.drawPath(rrect(2050, 380, 2110, 470, 10), fill("#3a3d44"))
    c.drawCircle(2080, 560, 120, stroke("#c9ccd2", 8))
    for k in range(3):
        a = k / 3 * math.tau
        c.drawPath(oval(2080 + math.cos(a) * 55, 560 + math.sin(a) * 55, 50, 28), fill("#5a8ab0"))
    # tủ hồ sơ kim loại
    for k in range(2):
        fl = 3050 + k * 340
        c.drawRect(_R(fl, 720, fl + 320, 1460), fill("#7d8a8e"))
        for j in range(4):
            y = 750 + j * 175
            c.drawRect(_R(fl + 20, y, fl + 300, y + 155), fill("#8d9a9e"))
            c.drawPath(rrect(fl + 120, y + 60, fl + 200, y + 84, 8), fill("#c9ccd2"))
    # bàn làm việc gỗ + máy tính cũ
    dl, dr, dt = 1880, 2880, 1500
    c.drawRect(_R(dl - 30, dt - 40, dr + 30, dt), fill("#8a5a3a"))
    c.drawRect(_R(dl, dt, dr, 1880), fill("#6b4a32"))
    c.drawRect(_R(dl + 30, dt + 40, dr - 30, 1840), stroke(shade("#6b4a32", -0.25), 8))
    c.drawPath(rrect(2000, 1180, 2380, 1450, 20), fill("#d9d4c4"))
    c.drawPath(rrect(2040, 1215, 2340, 1410, 14), fill("#2a4a5a" if not night else "#4a8aa0"))
    if night:
        glow(c, 2190, 1310, 380, "#9fd8ff", 0.35)
    c.drawRect(_R(2150, 1450, 2230, 1462), fill("#b9b4a4"))
    c.drawPath(rrect(1990, dt - 70, 2400, dt - 40, 8), fill("#e3ded0"))
    for k in range(3):
        c.drawRect(_R(2500 + k * 8, dt - 110 + k * 22, 2780 - k * 8, dt - 90 + k * 22), fill("#f4f1e8"))
    # ghế nhựa xanh cho người khai
    ch = "#2f6fb0"
    c.drawPath(rrect(1560, 1420, 1860, 1700, 30), fill(ch))
    c.drawPath(rrect(1530, 1680, 1890, 1740, 16), fill(shade(ch, 0.12)))
    for x in (1550, 1870):
        quad(c, [(x - 12, 1740), (x + 12, 1740), (x + 20 * (1 if x > 1700 else -1) + 12, 1960),
                 (x + 20 * (1 if x > 1700 else -1) - 12, 1960)], shade(ch, -0.2))
    if night:
        tint(s, "#5a6890", 0.55)
        glow(c, 2190, 1310, 420, "#9fd8ff", 0.35)
    _vignette(c, 0.35)
    mid = s.makeImageSnapshot()
    slots = {"officer": {**frac_slot({"x": 0.62, "y": 0.86, "scale": 0.95}), "clip_bottom": dt},
             "visitor": frac_slot({"x": 0.34, "y": 0.90, "scale": 1.0}),
             "center": frac_slot({"x": 0.50, "y": 0.90, "scale": 1.0})}
    slots["officer"]["x"] = round((dl + dr) / 2)
    signs = [{"text": "RECEPTION", "box": [2130, 1560, 2630, 1650], "style": "white_board"}]
    return Scene(None, mid, slots=slots, signs=signs, floor_y=slots["center"]["y"])


# ------------------------------------------------------------------- 22. sân chùa / miếu làng
def _curved_roof(c, cx, y, half, h, col, eave="#2a1a14") -> None:
    p = skia.Path()
    p.moveTo(cx - half - 60, y - 70)
    p.quadTo(cx - half * 0.6, y, cx, y)
    p.quadTo(cx + half * 0.6, y, cx + half + 60, y - 70)
    p.lineTo(cx + half * 0.8, y - h * 0.4)
    p.lineTo(cx + half * 0.55, y - h)
    p.lineTo(cx - half * 0.55, y - h)
    p.lineTo(cx - half * 0.8, y - h * 0.4)
    p.close()
    path_fill(c, p, col)
    c.drawPath(rrect(cx - half * 0.58, y - h - 18, cx + half * 0.58, y - h + 8, 8), fill(eave))
    for sg in (-1, 1):
        c.drawPath(capsule(cx + sg * half * 0.55, y - h - 4, cx + sg * (half * 0.55 + 60), y - h - 60, 16, 8), fill(eave))
        c.drawPath(capsule(cx + sg * (half + 20), y - 50, cx + sg * (half + 90), y - 130, 18, 8), fill(eave))


def scene_san_chua(tod: str) -> Scene:
    day, dusk = tod == "day", tod == "dusk"
    sf = new_surface()
    c = sf.getCanvas()
    if day:
        _day_sky(c, 0, 1400, "#a9b9c4", "#e6e8e2")
    elif dusk:
        _dusk_sky(c, 0, 1400, seed=19)
    else:
        _night_sky(c, 0, 1400, seed=19)
    for i, x in enumerate(range(-100, W + 200, 280)):
        round_tree(c, x, 1020, 170, "#7f9a6a" if day else "#1a2622", "#7f9a6a" if day else "#1a2622", seed=i + 70)
    far = sf.makeImageSnapshot()
    s = new_surface()
    c = s.getCanvas()
    base = 1380
    c.drawRect(_R(0, 1040, W, base), fill("#c9b8a0"))
    c.drawRect(_R(0, 1010, W, 1050), fill("#6a4a3a"))
    # cổng tam quan
    pil = "#8a3a2a"
    for (cx_, half, top, roof_h) in ((1920, 380, 620, 260), (1200, 260, 860, 190), (2640, 260, 860, 190)):
        c.drawRect(_R(cx_ - half, top, cx_ + half, base), fill("#e6d6b8"))
        c.drawRect(_R(cx_ - half, top, cx_ + half, top + 40), fill("#c9b48e"))
        ar = half * 0.55
        arch = skia.Path()
        arch.moveTo(cx_ - ar, base)
        arch.lineTo(cx_ - ar, top + 180 + ar)
        arch.arcTo(_R(cx_ - ar, top + 180, cx_ + ar, top + 180 + 2 * ar), 180, 180, False)
        arch.lineTo(cx_ + ar, base)
        arch.close()
        path_fill(c, arch, "#1a1410")
        for px in (cx_ - half, cx_ + half):
            c.drawRect(_R(px - 34, top - 20, px + 34, base), fill(pil))
        _curved_roof(c, cx_, top, half + 40, roof_h, "#4a3a34")
    c.drawPath(rrect(1720, 470, 2120, 560, 12), fill("#2a1d12"))
    c.drawPath(rrect(1734, 484, 2106, 546, 8), stroke("#c99a3c", 6))
    for (lx_, ly_) in ((1480, 680), (2360, 680), (960, 900), (2880, 900)):
        c.drawLine(lx_, ly_ - 80, lx_, ly_ - 40, stroke("#2a1a14", 4))
        c.drawPath(oval(lx_, ly_, 44, 56), fill("#d0302a"))
        c.drawRect(_R(lx_ - 20, ly_ - 62, lx_ + 20, ly_ - 52), fill("#c99a3c"))
        c.drawLine(lx_, ly_ + 56, lx_, ly_ + 96, stroke("#f3c94e", 4))
        if not day:
            glow(c, lx_, ly_, 200, "#ff5a3a", 0.5)
    # sân gạch
    vgrad(c, 0, base, W, H, ["#b06a4a", "#8a4e36"])
    y = base
    step = 28
    row = 0
    while y < H:
        c.drawLine(0, y, W, y, stroke("#7a4030", 4))
        off = (row % 2) * 0.5
        bw = step * 4
        xx = -bw + off * bw
        while xx < W:
            c.drawLine(xx, y, xx, y + step, stroke("#7a4030", 3))
            xx += bw
        y += step
        step *= 1.12
        row += 1
    # cây đa lớn bên phải
    trunk = "#5a4636"
    c.drawPath(poly([(3200, H - 120), (3560, H - 120), (3480, 900), (3300, 900)]), fill(trunk))
    rng = random.Random(8)
    for _ in range(14):
        rx = rng.uniform(2900, W)
        c.drawLine(rx, rng.uniform(600, 900), rx + rng.uniform(-30, 30), rng.uniform(1300, 1900), stroke(shade(trunk, -0.1), 8))
    leaf = "#4a6a3a" if day else "#1a2a1c"
    for _ in range(22):
        c.drawCircle(rng.uniform(2700, W + 200), rng.uniform(-60, 820), rng.uniform(160, 300), fill(leaf))
    for _ in range(10):
        c.drawCircle(rng.uniform(2800, W + 100), rng.uniform(0, 700), rng.uniform(80, 160), fill(shade(leaf, 0.12)))
    # lư hương lớn + khói nhang
    ix, ib = 1920, 1700
    c.drawRect(_R(ix - 230, ib - 120, ix + 230, ib), fill("#9a948a"))
    c.drawRect(_R(ix - 260, ib - 150, ix + 260, ib - 120), fill("#b4ae9e"))
    c.drawPath(rrect(ix - 190, ib - 380, ix + 190, ib - 150, 70), fill("#8a6a3a"))
    c.drawRect(_R(ix - 220, ib - 400, ix + 220, ib - 360), fill("#6a4e2a"))
    for sg in (-1, 1):
        c.drawPath(capsule(ix + sg * 190, ib - 330, ix + sg * 250, ib - 360, 26, 18), fill("#6a4e2a"))
    for k in range(7):
        x = ix - 90 + k * 30
        c.drawLine(x, ib - 400, x + (k - 3) * 6, ib - 520, stroke("#b0553a", 5))
        c.drawCircle(x + (k - 3) * 6, ib - 520, 5, fill("#ff6a3a"))
    for k in range(6):
        c.drawPath(oval(ix + math.sin(k * 1.3) * 80, ib - 600 - k * 110, 70 + k * 30, 40 + k * 10),
                   fill("#e8e8e8", 0.32 - k * 0.045))
    # tượng nhỏ bên trái
    sx = 520
    c.drawRect(_R(sx - 120, 1520, sx + 120, 1760), fill("#9a948a"))
    c.drawRect(_R(sx - 140, 1500, sx + 140, 1530), fill("#b4ae9e"))
    c.drawPath(poly([(sx - 80, 1500), (sx + 80, 1500), (sx + 50, 1260), (sx - 50, 1260)]), fill("#d9d6cc"))
    c.drawCircle(sx, 1215, 52, fill("#d9d6cc"))
    c.drawPath(oval(sx, 1300, 70, 24), fill("#c9c6bc"))
    if not day:
        tint(s, "#6a6a9a" if not dusk else "#c9a6c6", 0.55 if not dusk else 0.3)
        for (lx_, ly_) in ((1480, 680), (2360, 680), (960, 900), (2880, 900)):
            glow(c, lx_, ly_, 220, "#ff5a3a", 0.5)
    mid = s.makeImageSnapshot()
    slots = {"left": frac_slot({"x": 0.30, "y": 0.90, "scale": 0.9}),
             "center": frac_slot({"x": 0.50, "y": 0.90, "scale": 0.9}),
             "right": frac_slot({"x": 0.70, "y": 0.90, "scale": 0.9}),
             "gate": {"x": 1920, "y": base, "scale": 0.55}}
    return Scene(far, mid, slots=slots, floor_y=slots["center"]["y"], parallax=(0.8, 1.0, 1.15))


# ------------------------------------------------------------------- 23. bờ sông / bến nước đêm
def _nipa_palm(c, x, y, h, col) -> None:
    for k in range(9):
        a = math.pi * (0.12 + 0.76 * k / 8)
        tx, ty = x + math.cos(a) * h, y - math.sin(a) * h
        p = skia.Path()
        p.moveTo(x, y)
        p.quadTo((x + tx) / 2 + (ty - y) * 0.15, (y + ty) / 2 - h * 0.1, tx, ty)
        c.drawPath(p, stroke(col, 16))
        for j in range(1, 7):
            t = j / 7
            px_ = x + (tx - x) * t
            py_ = y + (ty - y) * t - h * 0.1 * math.sin(t * math.pi)
            c.drawLine(px_, py_, px_ + math.cos(a - 0.9) * h * 0.12, py_ - math.sin(a - 0.9) * h * 0.12, stroke(col, 6))
            c.drawLine(px_, py_, px_ + math.cos(a + 0.9) * h * 0.12, py_ - math.sin(a + 0.9) * h * 0.12, stroke(col, 6))


def scene_bo_song_dem(tod: str) -> Scene:
    dusk = tod == "dusk"
    HZ = 1000
    sf = new_surface()
    c = sf.getCanvas()
    if dusk:
        _dusk_sky(c, 0, HZ + 20, seed=29)
    else:
        _night_sky(c, 0, HZ + 20, seed=29, n_stars=300)
        glow(c, 2700, 300, 300, "#f1ead2", 0.55)
        c.drawCircle(2700, 300, 90, fill("#f1ead2"))
    for i, x in enumerate(range(-100, W + 200, 200)):
        round_tree(c, x, HZ - 10, 110 + (i % 3) * 20, "#0c1218" if not dusk else "#2c2848",
                   "#0c1218" if not dusk else "#2c2848", seed=i + 90)
    water = "#0b1424" if not dusk else "#3a3560"
    vgrad(c, 0, HZ, W, H, [shade(water, 0.1), water])
    if not dusk:
        rng = random.Random(1)
        for k in range(24):
            y = HZ + 30 + k * 40
            hw = 110 - k * 3 + rng.uniform(-25, 25)
            c.drawRect(_R(2700 - hw, y, 2700 + hw, y + 9), fill("#f1ead2", 0.5 - k * 0.018))
    far = sf.makeImageSnapshot()
    s = new_surface()
    c = s.getCanvas()
    rng = random.Random(12)
    c.drawRect(_R(0, 1020, W, 1500), lin_paint((0, 1020), (0, 1500), [("#c9d6e0", 0.0), ("#c9d6e0", 0.18), ("#c9d6e0", 0.0)]))
    # bờ trái + dừa nước
    bank = poly([(-50, 1380), (520, 1420), (760, 1560), (820, H + 10), (-50, H + 10)])
    path_fill(c, bank, "#121a14" if not dusk else "#2a3028")
    palm = "#162a1e" if not dusk else "#2f4a36"
    for (px_, py_, h_) in ((120, 1460, 620), (420, 1500, 520), (640, 1600, 420), (-60, 1640, 560)):
        _nipa_palm(c, px_, py_, h_, palm)
    # bến gỗ
    PL, PR, PT, PB = 560, 2260, 1620, 1760
    for x in range(PL + 60, PR, 260):
        c.drawRect(_R(x - 14, PB, x + 14, 2040), fill("#2a1e16"))
        c.drawRect(_R(x - 14, 2040, x + 14, 2120), fill("#2a1e16", 0.35))
    quad(c, [(PL, PB), (PR, PB), (PR - 40, PT), (PL + 60, PT)], "#6b4a32" if dusk else "#4a3626")
    k = 0
    for x in range(PL + 40, PR, 70):
        c.drawLine(x, PB, x - (x - 1920) * 0.02, PT, stroke("#3a2a1e" if not dusk else "#5a3e2a", 5))
        k += 1
    c.drawRect(_R(PL, PB, PR, PB + 34), fill("#2e2218"))
    for x in (PR - 60, PL + 300):
        c.drawRect(_R(x - 14, PT - 200, x + 14, PT + 20), fill("#3a2a1e"))
    # xuồng buộc
    bx0, bx1, by = 2300, 3050, 1900
    hull = skia.Path()
    hull.moveTo(bx0, by - 60)
    hull.quadTo((bx0 + bx1) / 2, by + 70, bx1, by - 80)
    hull.lineTo(bx1 - 60, by - 40)
    hull.quadTo((bx0 + bx1) / 2, by, bx0 + 60, by - 30)
    hull.close()
    path_fill(c, hull, "#3a2a1e")
    c.drawPath(oval((bx0 + bx1) / 2, by - 30, (bx1 - bx0) / 2 - 60, 26), fill("#1f160f"))
    sag_wire(c, PR - 60, PT - 180, bx0 + 50, by - 60, 30, "#c9b890", 3)
    # lục bình trôi
    for _ in range(12):
        hx, hy = rng.uniform(800, W), rng.uniform(1820, 2140)
        if PL < hx < PR and hy < 2060:
            continue
        for j in range(5):
            c.drawPath(oval(hx + j * 22 - 44, hy - (j % 2) * 12, 34, 16), fill("#1e3a26" if not dusk else "#3a5a3e"))
        c.drawCircle(hx, hy - 30, 10, fill("#8a7ac0", 0.8))
    c.drawRect(_R(0, 1700, W, H), lin_paint((0, 1700), (0, H), [("#c9d6e0", 0.0), ("#c9d6e0", 0.14)]))
    mid = s.makeImageSnapshot()
    slots = {"dock": frac_slot({"x": 0.45, "y": 0.78, "scale": 0.7}),
             "left": frac_slot({"x": 0.30, "y": 0.80, "scale": 0.7}),
             "center": frac_slot({"x": 0.45, "y": 0.78, "scale": 0.7})}
    return Scene(far, mid, slots=slots, floor_y=slots["center"]["y"], parallax=(0.85, 1.0, 1.15),
                 lights=[{"x": 2700, "y": 300, "color": "#f1ead2"}])


# ------------------------------------------------------------------- 24. cửa hàng – góc CCTV trên cao
def scene_cua_hang_cctv_tren_cao(tod: str) -> Scene:
    P = Persp(f=1100, cx=1700, cy=-260, cam_h=7.5)
    XL, XR, Z0, ZB, YW = -5.2, 6.6, 3.2, 11.0, 3.0
    s = new_surface()
    c = s.getCanvas()
    c.drawRect(_R(0, 0, W, H), fill("#cfd5da"))
    path_fill(c, P.face_z(ZB, XL, XR, 0, YW), "#dfe3e7")
    path_fill(c, P.wall_x(XL, Z0, ZB, 0, YW), "#c3c9cf")
    path_fill(c, P.wall_x(XR, Z0, ZB, 0, YW), "#c9cfd4")
    path_fill(c, P.plane_y(0, XL, XR, Z0, ZB), "#f2f4f6")
    _floor_tiles(c, P, XL, XR, Z0, ZB, 0.6, "#b9c0c8", wmin=2.0)
    # cửa nhân viên + bảng ghim trên tường hậu
    dl, dt = P.p(-4.6, 2.1, ZB)
    dr, db = P.p(-3.6, 0, ZB)
    c.drawRect(_R(dl, dt, dr, db), fill("#7d8a96"))
    c.drawCircle(dr - 16, (dt + db) / 2, 7, fill("#e4e8ec"))
    sdl, sdt = P.p(-4.5, 2.45, ZB)
    sdr, sdb = P.p(-3.7, 2.2, ZB)
    c.drawRect(_R(sdl, sdt, sdr, sdb), fill("#2b2d33"))
    kl, kt = P.p(-2.8, 2.1, ZB)
    kr, kb = P.p(-1.4, 1.2, ZB)
    c.drawRect(_R(kl, kt, kr, kb), fill("#b08a5a"))
    rng = random.Random(3)
    for _ in range(6):
        x, y = rng.uniform(kl + 6, kr - 40), rng.uniform(kt + 6, kb - 46)
        c.drawRect(_R(x, y, x + 34, y + 40), fill("#f4f1e8"))
    # tủ lạnh dọc tường hậu (phải)
    fl, ft = P.p(0.0, 2.1, ZB)
    fr, fb = P.p(6.4, 0, ZB)
    c.drawRect(_R(fl, ft, fr, fb), fill("#2b2d33"))
    nd = 8
    for i in range(nd):
        x0 = fl + (fr - fl) * i / nd + 4
        x1 = fl + (fr - fl) * (i + 1) / nd - 4
        vgrad(c, x0, ft + 6, x1, fb - 8, ["#e9f2f8", "#c9d8e2"])
        _bottle_rows(c, x0, ft + 6, x1, fb - 8, seed=i + 5, rows=4)
    # kệ đứng giữa (2 dãy)
    def box(x0, x1, z0, z1, h, front, top_c):
        if x1 < 0:          # vật bên trái camera thấy mặt phải, bên phải thấy mặt trái
            path_fill(c, P.wall_x(x1, z0, z1, 0, h), shade(front, -0.15))
        elif x0 > 0:
            path_fill(c, P.wall_x(x0, z0, z1, 0, h), shade(front, -0.15))
        path_fill(c, P.face_z(z0, x0, x1, 0, h), front)
        path_fill(c, P.plane_y(h, x0, x1, z0, z1), top_c)
    for (x0, x1) in ((-0.4, 0.4), (2.0, 2.8)):
        z0, z1 = 5.0, 9.4
        path_fill(c, P.wall_x(x0, z0, z1, 0, 1.6), "#e3e6ea")
        rng2 = random.Random(int(x0 * 10) + 50)
        for ty in (0.2, 0.65, 1.1):
            zz = z0 + 0.05
            while zz < z1 - 0.2:
                w_ = rng2.uniform(0.25, 0.5)
                path_fill(c, P.wall_x(x0 - 0.01, zz, zz + w_ - 0.04, ty, ty + 0.35), rng2.choice(PRODUCTS[:-1]))
                zz += w_
        path_fill(c, P.plane_y(1.6, x0, x1, z0, z1), "#f4f6f8")
        path_fill(c, P.face_z(z0, x0, x1, 0, 1.6), "#1f6f5c")
    # biển đầu kệ (chữ = lớp signs)
    hb1 = [P.p(-0.4, 2.2, 5.0), P.p(0.4, 1.75, 5.0)]
    hb2 = [P.p(2.0, 2.2, 5.0), P.p(2.8, 1.75, 5.0)]
    for (a, b) in (hb1, hb2):
        c.drawLine((a[0] + b[0]) / 2, a[1], (a[0] + b[0]) / 2, P.p(0, 1.6, 5.0)[1], stroke("#8a9099", 4))
        c.drawRect(_R(a[0], a[1], b[0], b[1]), fill(BRAND["green"]))
    # quầy thu ngân dưới trái
    cx0, cx1, cz0, cz1, chh = -4.6, -1.8, 3.7, 4.5, 1.0
    box(cx0, cx1, cz0, cz1, chh, "#b5332b", "#f4f6f8")
    path_fill(c, P.face_z(cz0, cx0, cx1, chh - 0.12, chh), "#3a78c2")
    path_fill(c, P.plane_y(chh + 0.01, -3.0, -2.5, 3.9, 4.3), "#2b2d33")
    # tủ đá kính bên phải
    box(3.8, 5.8, 4.0, 5.2, 0.85, "#eef1f4", "#cfe0ea")
    path_fill(c, P.plane_y(0.86, 3.9, 5.7, 4.1, 5.1), "#ffffff", 0.25)
    # biển sàn ướt vàng
    wx, wy = P.p(1.3, 0, 4.4)
    k_ = P.f / 4.4
    quad(c, [(wx - 0.22 * k_, wy), (wx - 0.06 * k_, wy - 0.62 * k_), (wx + 0.06 * k_, wy - 0.62 * k_), (wx + 0.22 * k_, wy)], "#f3c94e")
    quad(c, [(wx - 0.07 * k_, wy - 0.3 * k_), (wx, wy - 0.45 * k_), (wx + 0.07 * k_, wy - 0.3 * k_)], "#22252b")
    # vũng nước + dấu chân ướt
    px_, py_ = P.p(1.0, 0, 6.2)
    c.drawPath(oval(px_, py_, 170, 46), fill("#9fb7c9", 0.45))
    for k in range(6):
        fx_, fy_ = P.p(0.9 - k * 0.32 + (k % 2) * 0.12, 0, 6.6 + k * 0.25)
        c.drawPath(oval(fx_, fy_, 18, 9), fill("#9fb7c9", 0.35))
    # đèn trần (vệt sáng trên sàn)
    for (lx, lz) in ((-2.5, 6.0), (1.2, 6.0), (4.5, 7.5), (-0.6, 9.5)):
        gx, gy = P.p(lx, 0, lz)
        ellipse_glow(c, gx, gy, 380, 120, "#ffffff", 0.25)
    if tod == "night":
        tint(s, "#b9c4d8", 0.2)
    mid = s.makeImageSnapshot()
    slots = {"counter": P.slot(-3.2, 4.9, clip_bottom=round(P.p(-3.2, chh, cz1)[1]) + 10),
             "floor_center": P.slot(0.9, 5.4), "aisle": P.slot(1.2, 8.0), "door": P.slot(-4.1, 10.5),
             "center": P.slot(0.9, 5.4)}
    signs = [{"text": "AISLE 1", "box": [round(hb1[0][0]) + 6, round(hb1[0][1]) + 4, round(hb1[1][0]) - 6, round(hb1[1][1]) - 4], "style": "plain"},
             {"text": "AISLE 2", "box": [round(hb2[0][0]) + 6, round(hb2[0][1]) + 4, round(hb2[1][0]) - 6, round(hb2[1][1]) - 4], "style": "plain"},
             {"text": "STAFF ONLY", "box": [round(sdl) + 4, round(sdt) + 3, round(sdr) - 4, round(sdb) - 3], "style": "plain"}]
    return Scene(None, mid, slots=slots, signs=signs, floor_y=slots["center"]["y"])


# =================================================================== LÔ 2 (docs/reference_batch2_analysis.json)
# 12 cảnh thư viện mới, vẽ GỐC bằng code theo ngữ pháp chung (bếp, kho lạnh, sân thượng, hẻm nhà phố, phòng trưởng
# công an, ICU, chợ có mái, phòng điều tra, bến gỗ, tiệm tạp hoá, toà án, phòng ký túc). Không cắt/đồ lại khung
# tham khảo; không tên tiệm thật, không logo, không quốc kỳ. Chữ nướng vào ảnh (nhiệt độ, chỉ số máy) là tiếng Anh.
def _tile_grid(c, l, t, r, b, sx, sy, line, w: float = 4.0, a: float = 1.0) -> None:
    x = l
    while x <= r + 0.5:
        c.drawLine(x, t, x, b, stroke(line, w, a))
        x += sx
    y = t
    while y <= b + 0.5:
        c.drawLine(l, y, r, y, stroke(line, w, a))
        y += sy


def _persp_floor(c, top, col, line, vx=W / 2, vy=1000.0, spacing=300.0, dz=0.11, w=4.0, a=1.0) -> None:
    """Sàn nhìn ngang: nền phẳng + đường dọc hội tụ về (vx, vy) + đường ngang giãn dần về phía camera."""
    c.drawRect(_R(0, top, W, H), fill(col))
    k = (top - vy) / (H - vy)
    i = -40
    while i <= 40:
        xb = vx + i * spacing
        c.drawLine(xb, H, vx + (xb - vx) * k, top, stroke(line, w, a))
        i += 1
    j = 1
    while dz > 0:
        d = 1.0 - j * dz
        if d <= 0:
            break
        y = vy + (top - vy) / d
        if y > H:
            break
        c.drawLine(0, y, W, y, stroke(line, w * (1 + j * 0.15), a))
        j += 1


def _star(cx, cy, r, ri) -> skia.Path:
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else ri
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    return poly(pts)


def _dashed(col, w, on=22.0, off=16.0, a=1.0) -> skia.Paint:
    p = stroke(col, w, a)
    p.setPathEffect(skia.DashPathEffect.Make([on, off], 0.0))
    return p


def _soft(col, a, sigma) -> skia.Paint:
    p = fill(col, a)
    p.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, sigma))
    return p


def _suitcase(c, x, base, w, h, col, tag="#f3c94e", handle=True) -> None:
    """Vali cứng có bánh xe (x = tâm, base = mặt sàn)."""
    wr = w * 0.07
    for dx in (-w * 0.32, w * 0.32):
        c.drawCircle(x + dx, base - wr, wr, fill("#22252b"))
    bb = base - wr * 1.6
    c.drawPath(rrect(x - w / 2, bb - h, x + w / 2, bb, w * 0.12), fill(col))
    c.drawPath(rrect(x - w / 2 + w * 0.05, bb - h + h * 0.04, x - w / 2 + w * 0.2, bb - h * 0.04, w * 0.06),
               fill(shade(col, 0.12)))
    for k in (0.32, 0.5, 0.68, 0.86):
        c.drawLine(x - w / 2 + w * k, bb - h + h * 0.08, x - w / 2 + w * k, bb - h * 0.08,
                   stroke(shade(col, -0.16), max(3.0, w * 0.022)))
    c.drawLine(x - w / 2, bb - h * 0.5, x + w / 2, bb - h * 0.5, stroke(shade(col, -0.3), max(3.0, w * 0.02)))
    if handle:
        hh = h * 0.42
        for dx in (-w * 0.17, w * 0.17):
            c.drawRect(_R(x + dx - w * 0.022, bb - h - hh, x + dx + w * 0.022, bb - h), fill("#8a9098"))
        c.drawPath(rrect(x - w * 0.24, bb - h - hh - w * 0.07, x + w * 0.24, bb - h - hh + w * 0.02, w * 0.035),
                   fill("#2b2d33"))
    else:
        c.drawPath(rrect(x - w * 0.16, bb - h - w * 0.06, x + w * 0.16, bb - h + w * 0.01, w * 0.03), fill("#2b2d33"))
    tx, ty = x + w * 0.22, bb - h + h * 0.1
    c.drawLine(tx, ty, tx + w * 0.06, ty + h * 0.14, stroke("#2b2d33", 3))
    c.drawPath(rrect(tx + w * 0.0, ty + h * 0.14, tx + w * 0.16, ty + h * 0.26, 6), fill(tag))


def _skyline(c, base, seed, col, hmin, hmax, wmin=140.0, wmax=380.0, lit=None, lit_p=0.0, beacons=False,
             l=-60.0, r=W + 60.0) -> None:
    rng = random.Random(seed)
    x = l
    while x < r:
        w = rng.uniform(wmin, wmax)
        h = rng.uniform(hmin, hmax)
        top = base - h
        c.drawRect(_R(x, top, x + w, base + 6), fill(col))
        if rng.random() < 0.3:
            c.drawRect(_R(x + w * 0.2, top - h * 0.07, x + w * 0.6, top), fill(col))
        ant = rng.random() < 0.3
        if ant:
            c.drawRect(_R(x + w * 0.5 - 4, top - h * 0.22, x + w * 0.5 + 4, top), fill(col))
        if lit:
            wy = top + 30
            while wy < base - 30:
                wx = x + 18
                while wx < x + w - 30:
                    if rng.random() < lit_p:
                        c.drawRect(_R(wx, wy, wx + 16, wy + 22), fill(lit, rng.uniform(0.45, 0.95)))
                    wx += 34
                wy += 46
        if beacons and h > hmin + (hmax - hmin) * 0.6:
            by = top - (h * 0.22 if ant else 0) - 8
            c.drawCircle(x + w * 0.5, by, 9, fill("#ff3b30"))
            glow(c, x + w * 0.5, by, 60, "#ff3b30", 0.6)
        x += w + rng.uniform(-20, 30)


def _spirit_house(c, x, base, k, night: bool) -> None:
    """Miếu thờ nhỏ trên cột (chung chung, không sao chép mẫu cụ thể). k = px/mét."""
    post = "#cbbd9f" if not night else "#5a5048"
    gold = "#d9a441" if not night else "#a07a30"
    red = "#b8432f" if not night else "#7a2a20"
    c.drawRect(_R(x - 0.22 * k, base - 0.08 * k, x + 0.22 * k, base), fill(shade(post, -0.2)))
    c.drawRect(_R(x - 0.07 * k, base - 1.25 * k, x + 0.07 * k, base), fill(post))
    c.drawRect(_R(x - 0.07 * k, base - 1.25 * k, x - 0.03 * k, base), fill(shade(post, 0.1)))
    c.drawRect(_R(x - 0.44 * k, base - 1.33 * k, x + 0.44 * k, base - 1.23 * k), fill(shade(post, 0.08)))
    c.drawRect(_R(x - 0.4 * k, base - 1.23 * k, x + 0.4 * k, base - 1.19 * k), fill(shade(post, -0.25)))
    bl, br, bt, bb = x - 0.25 * k, x + 0.25 * k, base - 1.72 * k, base - 1.33 * k
    c.drawRect(_R(bl, bt, br, bb), fill("#f0e2c0" if not night else "#6a5c44"))
    for px in (bl, br):
        c.drawRect(_R(px - 0.03 * k, bt, px + 0.03 * k, bb), fill(gold))
    c.drawPath(rrect(x - 0.09 * k, bt + 0.11 * k, x + 0.09 * k, bb, 0.06 * k), fill("#2a1a12"))
    # mái 2 tầng nhọn + đầu hồi cong
    for (hw, y0, hh) in ((0.38, bt, 0.2), (0.27, bt - 0.15 * k, 0.2)):
        p = poly([(x - hw * k, y0), (x + hw * k, y0), (x + hw * 0.35 * k, y0 - hh * k), (x - hw * 0.35 * k, y0 - hh * k)])
        path_fill(c, p, red)
        c.drawLine(x - hw * k, y0, x + hw * k, y0, stroke(gold, max(3.0, 0.025 * k)))
        for sg in (-1, 1):
            c.drawPath(capsule(x + sg * hw * k, y0, x + sg * (hw + 0.07) * k, y0 - 0.1 * k, 0.025 * k, 0.012 * k), fill(gold))
    c.drawPath(capsule(x, bt - 0.3 * k, x, bt - 0.62 * k, 0.04 * k, 0.01 * k), fill(gold))
    # vòng hoa cúc + nhang + chai nước nhỏ
    for i in range(9):
        t = i / 8
        gx = bl - 0.05 * k + (br - bl + 0.1 * k) * t
        gy = bt + 0.04 * k + math.sin(t * math.pi) * 0.1 * k
        c.drawCircle(gx, gy, 0.028 * k, fill("#f08a2c" if i % 2 else "#f3c94e"))
    for dx in (-0.33, -0.27, 0.27, 0.33):
        c.drawPath(rrect(x + dx * k - 0.022 * k, base - 1.43 * k, x + dx * k + 0.022 * k, base - 1.33 * k, 0.01 * k),
                   fill("#d8423a" if dx < 0 else "#4fa35a"))
    for dx in (-0.05, 0.0, 0.05):
        c.drawLine(x + dx * k, base - 1.33 * k, x + dx * k * 1.6, base - 1.55 * k, stroke("#8a5a3a", 3))
        c.drawCircle(x + dx * k * 1.6, base - 1.55 * k, 4, fill("#ff6a3a"))
    if night:
        glow(c, x, bb - 0.1 * k, 0.6 * k, "#ffb060", 0.45)


def _scooter(c, x, base, k, col, facing: int = 1) -> None:
    """Xe tay ga nhìn ngang. x = tâm, base = mặt đất, k = px/mét."""
    def P_(u, v):
        return (x + facing * u * k, base - v * k)
    for u in (-0.6, 0.6):
        cx_, cy_ = P_(u, 0.24)
        c.drawCircle(cx_, cy_, 0.24 * k, fill("#16181d"))
        c.drawCircle(cx_, cy_, 0.11 * k, fill("#8a9098"))
    path_fill(c, poly([P_(-0.95, 0.5), P_(-0.25, 0.36), P_(0.02, 0.3), P_(0.02, 0.62), P_(-0.75, 0.74), P_(-0.97, 0.62)]), col)
    path_fill(c, poly([P_(-0.25, 0.26), P_(0.38, 0.26), P_(0.38, 0.36), P_(-0.25, 0.36)]), shade(col, -0.3))
    path_fill(c, poly([P_(0.3, 0.28), P_(0.52, 0.3), P_(0.66, 0.96), P_(0.52, 1.02), P_(0.38, 0.95)]), shade(col, 0.08))
    path_fill(c, poly([P_(0.42, 0.52), P_(0.82, 0.42), P_(0.86, 0.36), P_(0.44, 0.4)]), shade(col, -0.12))
    a, b = P_(-0.8, 0.72), P_(-0.08, 0.84)
    c.drawPath(rrect(min(a[0], b[0]), b[1], max(a[0], b[0]), a[1], 0.05 * k), fill("#1d1f24"))
    c.drawLine(*P_(0.52, 1.0), *P_(0.47, 1.14), stroke("#1d1f24", 0.05 * k))
    c.drawLine(*P_(0.36, 1.14), *P_(0.62, 1.14), stroke("#1d1f24", 0.045 * k))
    c.drawCircle(*P_(0.64, 0.86), 0.05 * k, fill("#f4efe4"))
    c.drawLine(*P_(-0.98, 0.58), *P_(-0.9, 0.58), stroke("#d8423a", 0.05 * k))


def _ecg(c, l, y, r, amp, col, w=6.0, period=260.0) -> None:
    p = skia.Path()
    p.moveTo(l, y)
    x = l
    while x < r:
        seg = [(x + period * 0.35, y), (x + period * 0.42, y - amp * 0.15), (x + period * 0.47, y),
               (x + period * 0.52, y + amp * 0.25), (x + period * 0.56, y - amp), (x + period * 0.61, y + amp * 0.35),
               (x + period * 0.66, y), (x + period * 0.8, y - amp * 0.2), (x + period, y)]
        for (px, py) in seg:
            if px > r:
                break
            p.lineTo(px, py)
        x += period
    c.drawPath(p, stroke(col, w))


def _sine(c, l, y, r, amp, col, w=6.0, period=200.0) -> None:
    p = skia.Path()
    p.moveTo(l, y)
    x = l
    while x <= r:
        p.lineTo(x, y - amp * math.sin((x - l) / period * math.tau))
        x += 6
    c.drawPath(p, stroke(col, w))


def _baked(text, cx, cy, size) -> dict:
    return {"text": text, "box": [round(cx - size * len(text) * 0.32), round(cy - size * 0.6),
                                  round(cx + size * len(text) * 0.32), round(cy + size * 0.6)]}


# ------------------------------------------------------------------- 25. bếp nhà hàng + cửa kho đông
def scene_bep_nha_hang(tod: str) -> Scene:
    night = tod != "day"
    s = new_surface()
    c = s.getCanvas()
    FB, TT = 1640, 1010
    c.drawRect(_R(0, 0, W, FB), fill("#8a9488"))
    vgrad(c, 0, 120, W, 420, ["#6a746a", "#8a9488"])
    c.drawRect(_R(0, 0, W, 120), fill("#4a524c"))
    c.drawRect(_R(0, TT, W, FB), fill("#e4e9e4"))
    _tile_grid(c, 0, TT, W, FB, 105, 105, "#bfc8c1", 4)
    c.drawRect(_R(0, TT - 18, W, TT), fill("#b4beb6"))
    rng = random.Random(25)
    for _ in range(8):
        x, y = rng.uniform(0, W), rng.uniform(260, 900)
        c.drawPath(oval(x, y, rng.uniform(60, 200), rng.uniform(80, 220)), fill("#3e463e", rng.uniform(0.05, 0.1)))
    _tube(c, 1900, 150, 900, on=True, col="#e8f4ea")
    # quạt hút
    ex, ey, es = 520, 360, 330
    c.drawRect(_R(ex - es / 2 - 26, ey - es / 2 - 26, ex + es / 2 + 26, ey + es / 2 + 26), fill("#6e766e"))
    c.drawRect(_R(ex - es / 2, ey - es / 2, ex + es / 2, ey + es / 2), fill("#232724"))
    c.drawCircle(ex, ey, es * 0.44, fill("#343a36"))
    for k in range(4):
        c.save()
        c.rotate(k * 90 + 20, ex, ey)
        c.drawPath(oval(ex + es * 0.2, ey, es * 0.2, es * 0.07), fill("#8a928c"))
        c.restore()
    c.drawCircle(ex, ey, es * 0.07, fill("#c9d0ca"))
    for k in range(7):
        y = ey - es / 2 + k * es / 6
        c.drawLine(ex - es / 2, y, ex + es / 2, y, stroke("#141615", 5, 0.6))
    c.drawPath(oval(ex + 40, ey + es / 2 + 80, 70, 40), fill("#3e3a2a", 0.18))
    # tờ thông báo
    c.save()
    c.rotate(-2.5, 1100, 450)
    c.drawRect(_R(980, 300, 1220, 620), fill("#f4f1e8"))
    c.drawRect(_R(980, 300, 1220, 350), fill("#c8352e"))
    for j in range(7):
        c.drawLine(1005, 390 + j * 30, 1195 - (j % 3) * 40, 390 + j * 30, stroke("#8a8a8a", 6))
    c.drawRect(_R(1070, 285, 1130, 310), fill("#e9dfb8", 0.9))
    c.restore()
    # kệ + lò vi sóng + hũ
    SY = 790
    c.drawRect(_R(1300, SY, 1900, SY + 26), fill("#c9d0d4"))
    for x in (1340, 1860):
        quad(c, [(x - 8, SY + 26), (x + 8, SY + 26), (x + 8, SY + 110), (x - 8, SY + 26)], "#8e989f")
    c.drawPath(rrect(1320, SY - 200, 1640, SY, 16), fill("#d9dcdc"))
    c.drawPath(rrect(1342, SY - 178, 1550, SY - 22, 10), fill("#2a2f33"))
    reflections(c, 1342, SY - 178, 1550, SY - 22, 2, 0.12, seed=4)
    for j in range(3):
        c.drawCircle(1595, SY - 150 + j * 45, 10, fill("#6e7478"))
    for i, (col, hh) in enumerate((("#3a78c2", 150), ("#c9d0d4", 120), ("#3a78c2", 170))):
        x = 1680 + i * 72
        c.drawPath(rrect(x, SY - hh, x + 60, SY, 10), fill(col))
        c.drawRect(_R(x - 4, SY - hh - 16, x + 64, SY - hh + 4), fill(shade(col, -0.25)))
    # thanh nam châm treo dao (tay cầm lên, lưỡi xuống)
    KY = 965
    for i in range(8):
        x = 2090 + i * 68
        c.drawPath(capsule(x, KY - 120, x, KY - 8, 15, 17), fill("#6b4a32"))
        c.drawCircle(x, KY - 60, 4, fill("#c9b48e"))
        if i % 2 == 0:
            c.drawRect(_R(x - 30, KY + 6, x + 30, KY + 140), fill("#cfd6dc"))
            c.drawRect(_R(x - 30, KY + 132, x + 30, KY + 140), fill("#eef3f6"))
            c.drawCircle(x + 14, KY + 34, 8, fill("#8a9488"))
        else:
            path_fill(c, poly([(x - 13, KY + 6), (x + 13, KY + 6), (x + 9, KY + 170), (x - 2, KY + 205), (x - 13, KY + 170)]), "#d9dfe4")
    c.drawPath(rrect(2045, KY - 22, 2625, KY + 22, 10), fill("#2b2d33"))
    # bàn inox trái + nồi
    TL, TR, TTop = 110, 860, 1258
    c.drawRect(_R(TL + 30, TTop + 34, TL + 54, FB + 40), fill("#9aa4ab"))
    c.drawRect(_R(TR - 54, TTop + 34, TR - 30, FB + 40), fill("#9aa4ab"))
    c.drawRect(_R(TL + 30, 1500, TR - 30, 1524), fill("#aab2b8"))
    c.drawPath(rrect(TL + 90, 1400, TL + 330, 1500, 14), fill("#8e989f"))
    c.drawRect(_R(TL, TTop, TR, TTop + 34), fill("#c9d1d7"))
    c.drawRect(_R(TL, TTop, TR, TTop + 8), fill("#eef2f4"))
    c.drawPath(rrect(200, TTop - 220, 450, TTop, 16), fill("#aab2b8"))
    c.drawRect(_R(185, TTop - 230, 465, TTop - 205), fill("#c9d0d4"))
    for sx_ in (180, 470):
        c.drawPath(rrect(sx_ - 22, TTop - 180, sx_ + 22, TTop - 150, 8), fill("#6e7478"))
    c.drawPath(rrect(520, TTop - 26, 820, TTop, 6), fill("#e9ecee"))
    # quầy sơ chế dài
    CL, CR, CT = 1000, 2780, 1240
    vgrad(c, CL, CT + 30, CR, FB + 30, ["#bcc5cb", "#8e989f"])
    for x in range(CL + 300, CR, 300):
        c.drawLine(x, CT + 50, x, FB + 20, stroke("#7d878e", 5))
        c.drawPath(rrect(x - 80, CT + 120, x - 30, CT + 136, 6), fill("#dfe5e9"))
    c.drawRect(_R(CL - 20, CT, CR + 20, CT + 36), fill("#dfe5e9"))
    c.drawRect(_R(CL - 20, CT, CR + 20, CT + 8), fill("#f6f8f9"))
    for i in range(6):
        bx_ = 1120 + i * 120
        for j in range(3 - (i % 2)):
            by_ = CT - j * 30
            quad(c, [(bx_ - 52, by_ - 34), (bx_ + 52, by_ - 34), (bx_ + 32, by_), (bx_ - 32, by_)], "#f4f6f6")
            c.drawPath(oval(bx_, by_ - 34, 52, 9), fill("#dfe3e4"))
    for (bx_, rr) in ((2250, 140), (2500, 110)):
        p = skia.Path()
        p.addArc(_R(bx_ - rr, CT - rr * 1.2, bx_ + rr, CT + rr * 0.6), 0, 180)
        path_fill(c, p, "#c9d1d7")
        c.drawPath(oval(bx_, CT - rr * 0.3, rr, rr * 0.16), fill("#9aa4ab"))
    c.drawPath(rrect(1850, CT - 22, 2120, CT, 6), fill("#f4f6f6"))
    # sàn gạch tối + rãnh thoát nước
    _persp_floor(c, FB, "#3e4440", "#2e3330", vx=1920, vy=1000, spacing=340, dz=0.13)
    c.drawRect(_R(CL, FB, CR, FB + 40), fill("#000000", 0.25))
    c.drawRect(_R(TL, FB + 30, TR, FB + 60), fill("#000000", 0.2))
    c.drawPath(oval(1920, 1960, 170, 36), fill("#1e2225"))
    for k in range(-4, 5):
        c.drawLine(1920 + k * 30, 1934, 1920 + k * 30, 1986, stroke("#3e4440", 5))
    ellipse_glow(c, 1700, 1850, 900, 120, "#c9d6d0", 0.12)
    # thớt gỗ (khúc cây) + thùng xanh + bình inox
    sx_, sb = 930, 1800
    c.drawRect(_R(sx_ - 120, sb - 300, sx_ + 120, sb), fill("#7a4e30"))
    c.drawPath(oval(sx_, sb, 120, 30), fill("#5a3a24"))
    c.drawPath(oval(sx_, sb - 300, 120, 32), fill("#c49a6a"))
    for rr in (90, 60, 30):
        c.drawPath(oval(sx_, sb - 300, rr, rr * 0.27), stroke("#9a6e44", 4))
    for (x0, x1, col, top, b_) in ((2410, 2560, "#c9d1d7", 1530, 1790), (2620, 2840, "#2f6fb0", 1480, 1830)):
        c.drawPath(rrect(x0, top, x1, b_, 22), fill(col))
        for yy in (top + (b_ - top) * 0.3, top + (b_ - top) * 0.7):
            c.drawLine(x0, yy, x1, yy, stroke(shade(col, -0.2), 8))
        c.drawPath(oval((x0 + x1) / 2, top + 8, (x1 - x0) / 2 - 6, 18), fill(shade(col, 0.15)))
        c.drawPath(oval((x0 + x1) / 2, b_ + 6, (x1 - x0) / 2 + 10, 14), fill("#000000", 0.3))
    # cửa kho đông
    DL, DR, DT = 2960, 3640, 690
    c.drawRect(_R(DL - 60, DT - 60, DR + 60, FB), fill("#9aa4ab"))
    c.drawRect(_R(DL - 60, DT - 60, DR + 60, DT - 44), fill("#c3cbd0"))
    vgrad(c, DL, DT, DR, FB - 8, ["#d5dce1", "#aeb8bf"])
    for x in range(DL + 70, DR, 90):
        c.drawLine(x, DT + 30, x, FB - 220, stroke("#c3cbd0", 5))
    c.drawRect(_R(DL, DT, DL + 14, FB - 8), fill("#3a3d42"))
    c.drawRect(_R(DR - 14, DT, DR, FB - 8), fill("#3a3d42"))
    for y in (DT + 130, FB - 330):
        c.drawPath(rrect(DL - 34, y, DL + 70, y + 110, 14), fill("#dfe5e9"))
        c.drawPath(rrect(DL - 20, y + 16, DL + 56, y + 94, 10), fill("#8e989f"))
    c.drawPath(rrect(DR - 190, 1110, DR - 40, 1280, 16), fill("#5a6066"))
    c.drawPath(capsule(DR - 160, 1195, DR - 330, 1195, 30, 22), fill("#3a3d42"))
    c.drawRect(_R(DL, FB - 210, DR, FB - 8), fill("#8e989f"))
    c.save()
    c.clipRect(_R(DL, FB - 210, DR, FB - 8))
    for k in range(-4, 12):
        x0 = DL + k * 70
        c.drawLine(x0, FB - 210, x0 + 200, FB - 8, stroke("#a9b2b8", 4))
    c.restore()
    vgrad(c, DL, FB - 120, DR, FB, [("#ffffff", 0.0), ("#ffffff", 0.35)])
    # đồng hồ nhiệt độ (chữ nướng)
    c.drawPath(rrect(3150, 540, 3450, 660, 14), fill("#5a6066"))
    c.drawPath(rrect(3166, 556, 3434, 644, 8), fill("#101214"))
    glow(c, 3300, 600, 220, "#ff3b30", 0.35)
    text_center(c, "-18°C", 3300, 600, 68, "#ff4a3a", "extrabold")
    if night:
        tint(s, "#6e7c94", 0.42)
        glow(c, 1900, 190, 700, "#e8f4ea", 0.25)
        glow(c, 3300, 600, 260, "#ff3b30", 0.4)
        text_center(c, "-18°C", 3300, 600, 68, "#ff5a4a", "extrabold")
    _vignette(c, 0.45)
    mid = s.makeImageSnapshot()
    slots = {"counter": {"x": 1800, "y": 1660, "scale": 0.95, "clip_bottom": CT + 10},
             "left": {"x": 1150, "y": 1990, "scale": 1.08},
             "center": {"x": 1920, "y": 1990, "scale": 1.08},
             "freezer_door": {"x": 3300, "y": 1960, "scale": 1.05}}
    signs = [{"text": "COLD ROOM", "box": [3120, 820, 3480, 920], "style": "white_board"}]
    return Scene(None, mid, slots=slots, signs=signs, baked_signs=[_baked("-18°C", 3300, 600, 68)],
                 floor_y=slots["center"]["y"], lights=[{"x": 1900, "y": 170, "color": "#e8f4ea"}])


# ------------------------------------------------------------------- 26. bên trong kho lạnh
def _belonging(c, kind, cx, by, k, col) -> None:
    """Đồ cá nhân bỏ lại trên kệ (túi, ba lô, mũ bảo hiểm, giày) — hình phẳng hướng về camera."""
    if kind == "backpack":
        c.drawPath(rrect(cx - 0.17 * k, by - 0.4 * k, cx + 0.17 * k, by, 0.08 * k), fill(col))
        c.drawPath(rrect(cx - 0.12 * k, by - 0.2 * k, cx + 0.12 * k, by - 0.03 * k, 0.04 * k), fill(shade(col, -0.15)))
        c.drawPath(capsule(cx - 0.06 * k, by - 0.4 * k, cx + 0.06 * k, by - 0.4 * k, 0.03 * k, 0.03 * k), fill(shade(col, -0.3)))
    elif kind == "tote":
        p = skia.Path()
        p.addArc(_R(cx - 0.1 * k, by - 0.48 * k, cx + 0.1 * k, by - 0.26 * k), 180, 180)
        c.drawPath(p, stroke(shade(col, -0.25), max(3.0, 0.025 * k)))
        quad(c, [(cx - 0.2 * k, by - 0.36 * k), (cx + 0.2 * k, by - 0.36 * k), (cx + 0.24 * k, by), (cx - 0.24 * k, by)], col)
    elif kind == "helmet":
        p = skia.Path()
        p.addArc(_R(cx - 0.17 * k, by - 0.34 * k, cx + 0.17 * k, by + 0.0 * k), 180, 180)
        p.lineTo(cx + 0.17 * k, by)
        p.lineTo(cx - 0.17 * k, by)
        p.close()
        path_fill(c, p, col)
        c.drawPath(rrect(cx - 0.12 * k, by - 0.17 * k, cx + 0.15 * k, by - 0.06 * k, 0.04 * k), fill("#1d2228"))
    elif kind == "shoes":
        for dx in (-0.08, 0.08):
            c.drawPath(oval(cx + dx * k, by - 0.04 * k, 0.07 * k, 0.045 * k), fill(col))
            c.drawRect(_R(cx + dx * k - 0.07 * k, by - 0.012 * k, cx + dx * k + 0.07 * k, by), fill("#f4f4f0"))
    else:   # handbag
        p = skia.Path()
        p.addArc(_R(cx - 0.08 * k, by - 0.34 * k, cx + 0.08 * k, by - 0.16 * k), 180, 180)
        c.drawPath(p, stroke(shade(col, -0.3), max(3.0, 0.02 * k)))
        c.drawPath(rrect(cx - 0.16 * k, by - 0.25 * k, cx + 0.16 * k, by, 0.05 * k), fill(col))
        c.drawRect(_R(cx - 0.16 * k, by - 0.25 * k, cx + 0.16 * k, by - 0.17 * k), fill(shade(col, -0.15)))
    c.drawLine(cx - 0.14 * k, by - (0.4 if kind in ("backpack", "tote") else 0.3) * k,
               cx + 0.1 * k, by - (0.4 if kind in ("backpack", "tote") else 0.3) * k, stroke("#ffffff", max(2.0, 0.015 * k), 0.55))


def scene_kho_lanh(tod: str) -> Scene:
    P = Persp(f=1500, cx=W / 2, cy=980, cam_h=1.6)
    XW, YC, Z0, ZB = 1.7, 2.7, 0.55, 7.5
    s = new_surface()
    c = s.getCanvas()
    c.drawRect(_R(0, 0, W, H), fill("#9fb0c2"))
    path_fill(c, P.plane_y(YC, -XW, XW, Z0, ZB), "#cdd8e2")
    path_fill(c, P.plane_y(0, -XW, XW, Z0, ZB), "#a9b6c2")
    path_fill(c, P.wall_x(-XW, Z0, ZB, 0, YC), "#b9c8d8")
    path_fill(c, P.wall_x(XW, Z0, ZB, 0, YC), "#b0bfcf")
    path_fill(c, P.face_z(ZB, -XW, XW, 0, YC), "#c9d6e2")
    z = Z0
    while z < ZB:
        for sd in (-1, 1):
            c.drawLine(*P.p(sd * XW, 0, z), *P.p(sd * XW, YC, z), stroke("#93a4b6", max(2.0, 12 / z)))
        c.drawLine(*P.p(-XW, YC, z), *P.p(XW, YC, z), stroke("#b4c2d0", max(2.0, 10 / z)))
        z += 0.6
    for xx in (-0.85, 0.0, 0.85):
        c.drawLine(*P.p(xx, 0, ZB), *P.p(xx, YC, ZB), stroke("#b0bfcd", 4))
    # sàn sọc chống trượt
    c.save()
    c.clipPath(P.plane_y(0, -XW, XW, Z0, ZB), skia.ClipOp.kIntersect, True)
    for i in range(-40, 40):
        x0 = i * 0.25
        c.drawLine(*P.p(x0, 0, Z0), *P.p(x0 + 3.0, 0, ZB), stroke("#9aa8b5", 6))
    c.restore()
    vgrad(c, 0, 1500, W, H, [("#ffffff", 0.0), ("#eef6ff", 0.3)])
    # dàn lạnh + băng rủ
    ul, ut = P.p(-1.0, 2.55, ZB - 0.05)
    ur, ub = P.p(1.0, 1.95, ZB - 0.05)
    c.drawPath(rrect(ul, ut, ur, ub, 12), fill("#e4ebf1"))
    k_ = P.f / ZB
    for xx in (-0.6, 0.0, 0.6):
        fx_, fy_ = P.p(xx, 2.25, ZB)
        c.drawCircle(fx_, fy_, 0.22 * k_, fill("#5a6a7a"))
        for j in range(4):
            c.drawCircle(fx_, fy_, 0.22 * k_ * (0.25 + j * 0.22), stroke("#8a9aaa", 3))
    rng = random.Random(26)
    x = ul + 8
    while x < ur - 8:
        ln = rng.uniform(14, 70)
        quad(c, [(x, ub), (x + 14, ub), (x + 6, ub + ln), (x + 5, ub + ln)], "#f4faff", 0.95)
        x += rng.uniform(16, 34)
    # bảng nhiệt độ (chữ nướng)
    tl_, tt_ = P.p(1.05, 1.65, ZB)
    tr_, tb_ = P.p(1.55, 1.38, ZB)
    c.drawPath(rrect(tl_, tt_, tr_, tb_, 6), fill("#f2f4f6"))
    c.drawPath(rrect(tl_ + 6, tt_ + 6, tr_ - 6, tb_ - 6, 4), fill("#101214"))
    text_center(c, "-18°C", (tl_ + tr_) / 2, (tt_ + tb_) / 2, (tb_ - tt_) * 0.5, "#ff4a3a")
    glow(c, (tl_ + tr_) / 2, (tt_ + tb_) / 2, 80, "#ff3b30", 0.3)
    # rãnh thoát nước
    dx_, dy_ = P.p(0, 0, 3.4)
    c.drawPath(oval(dx_, dy_, 0.18 * P.f / 3.4, 0.05 * P.f / 3.4), fill("#5a6a7a"))
    # kệ lưới hai bên, vẽ từ xa tới gần theo từng khoang
    bays = [6.8, 5.4, 4.0, 2.6, 1.2]
    levels = [0.35, 0.95, 1.55, 2.15]
    cols = ["#c74a9a", "#f3c94e", "#4fa35a", "#d8423a", "#3a78c2", "#8a5a9a", "#e8833a", "#6b4a32", "#2f7a5a"]
    kinds = ["backpack", "tote", "helmet", "shoes", "handbag"]
    for bi in range(len(bays) - 1):
        z1, z0 = bays[bi], bays[bi + 1]
        for sd in (-1, 1):
            xo, xi = sd * XW, sd * (XW - 0.55)
            for y in levels:
                path_fill(c, P.plane_y(y, min(xo, xi), max(xo, xi), z0, z1), "#d5dee6")
                for t in (0.25, 0.5, 0.75):
                    xx = xo + (xi - xo) * t
                    c.drawLine(*P.p(xx, y, z0), *P.p(xx, y, z1), stroke("#8a98a6", max(1.5, 6 / z0)))
                c.drawLine(*P.p(xi, y, z0), *P.p(xi, y, z1), stroke("#6e7c88", max(2.0, 18 / z0)))
                c.drawLine(*P.p(xi, y + 0.02, z0), *P.p(xi, y + 0.02, z1), stroke("#ffffff", max(1.5, 8 / z0), 0.6))
            for y in levels[:-1]:
                n = rng.randint(1, 2)
                for j in range(n):
                    if rng.random() < 0.2:
                        continue
                    zc = z1 - (z1 - z0) * (j + 0.5) / n
                    cx_, by_ = P.p(sd * (XW - 0.28), y + 0.01, zc)
                    _belonging(c, rng.choice(kinds), cx_, by_, P.f / zc, rng.choice(cols))
            for zz in (z0, z1):
                c.drawLine(*P.p(xi, 0, zz), *P.p(xi, 2.3, zz), stroke("#7d8a96", max(3.0, 40 / zz)))
    # thanh ray móc treo trên trần
    for xx in (-0.45, 0.45):
        c.drawLine(*P.p(xx, 2.5, 0.9), *P.p(xx, 2.5, 6.8), stroke("#7d8a96", 10))
        zz = 1.2
        while zz < 6.6:
            hx, hy = P.p(xx, 2.5, zz)
            kk = P.f / zz
            c.drawLine(hx, hy, hx, hy + 0.18 * kk, stroke("#9aa8b5", max(2.0, 0.02 * kk)))
            p = skia.Path()
            p.addArc(_R(hx - 0.06 * kk, hy + 0.14 * kk, hx + 0.06 * kk, hy + 0.26 * kk), 270, -250)
            c.drawPath(p, stroke("#9aa8b5", max(2.0, 0.02 * kk)))
            zz += 0.8
    # đèn tuýp trần
    path_fill(c, P.plane_y(YC - 0.02, -0.12, 0.12, 1.6, 5.6), "#f4fbff")
    gx, gy = P.p(0, YC, 3.0)
    ellipse_glow(c, gx, gy + 60, 900, 260, "#eef8ff", 0.35)
    # sương giá + bụi tuyết
    for _ in range(420):
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        c.drawCircle(x, y, rng.choice([2.0, 3.0, 4.0, 6.0]), fill("#ffffff", rng.uniform(0.25, 0.7)))
    for _ in range(14):
        c.drawCircle(rng.uniform(0, W), rng.uniform(200, H), rng.uniform(20, 40), _soft("#ffffff", 0.25, 10))
    for sd in (-1, 1):
        c.drawPath(P.wall_x(sd * XW, Z0, ZB, 0, 0.3), _soft("#ffffff", 0.35, 18))
    _vignette(c, 0.42)
    mid = s.makeImageSnapshot()
    slots = {"center": P.slot(0, 3.0), "left": P.slot(-0.55, 3.0), "right": P.slot(0.55, 3.0),
             "far": P.slot(0, 5.5)}
    return Scene(None, mid, slots=slots, baked_signs=[_baked("-18°C", (tl_ + tr_) / 2, (tt_ + tb_) / 2, 30)],
                 floor_y=slots["center"]["y"], lights=[{"x": gx, "y": gy, "color": "#eef8ff"}])


# ------------------------------------------------------------------- 27. sân thượng chung cư lúc bình minh
def scene_san_thuong_binh_minh(tod: str) -> Scene:
    sf = new_surface()
    c = sf.getCanvas()
    vgrad(c, 0, 0, W, 1400, ["#4a4276", "#6b5a8c", "#b48aa6", "#f2b884", "#f8d4a4"], [0, 0.32, 0.62, 0.86, 1])
    glow(c, 900, 1230, 900, "#ffd9a0", 0.55)
    c.drawCircle(900, 1240, 110, fill("#fff0cc", 0.9))
    rng = random.Random(27)
    for _ in range(8):
        x, y = rng.uniform(-200, W), rng.uniform(160, 760)
        wl, hh = rng.uniform(500, 1200), rng.uniform(24, 56)
        c.drawPath(rrect(x, y, x + wl, y + hh, hh / 2), fill("#e8b4b8", rng.uniform(0.3, 0.6)))
    _skyline(c, 1420, 5, "#9a8aae", 220, 560, lit="#ffe0b0", lit_p=0.03)
    _skyline(c, 1440, 9, "#6a5a86", 160, 820, wmin=180, wmax=420, lit="#ffd08a", lit_p=0.08, beacons=True)
    vgrad(c, 0, 1430, W, H, ["#5a4c76", "#3a3052"])        # thân các toà thấp hơn phía dưới
    far = sf.makeImageSnapshot()
    P = Persp(f=1400, cx=3000, cy=1050, cam_h=2.2)
    s = new_surface()
    c = s.getCanvas()
    XL, XR, Z0, ZE = -20.0, 1.2, 1.0, 25.0
    floor_c = "#a69cb4"
    path_fill(c, P.plane_y(0, XL, XR, Z0, ZE), floor_c)
    c.save()
    c.clipPath(P.plane_y(0, XL, XR, Z0, ZE), skia.ClipOp.kIntersect, True)
    for xx in range(-20, 2, 2):
        c.drawLine(*P.p(xx, 0, Z0), *P.p(xx, 0, ZE), stroke("#958aa4", 4))
    zz = 2.0
    while zz < ZE:
        c.drawLine(*P.p(XL, 0, zz), *P.p(XR, 0, zz), stroke("#958aa4", max(2.0, 14 / zz)))
        zz += 2.0
    for (px_, pz, pw) in ((-3.5, 6.5, 1.2), (-6.0, 11.0, 1.6)):
        cx_, cy_ = P.p(px_, 0, pz)
        rx = P.f * pw / pz
        c.drawPath(oval(cx_, cy_, rx, rx * 0.16), fill("#d9b8c6", 0.55))
    c.restore()
    path_fill(c, P.face_z(ZE, XL, XR, 0, 0.9), "#8a7f9c")
    path_fill(c, P.plane_y(0.9, XL, XR, ZE, ZE + 0.3), "#c0b6cc")
    path_fill(c, P.wall_x(XL, Z0, ZE, 0, 0.9), "#7f7494")
    path_fill(c, P.plane_y(0.9, XL, XL - 0.3, Z0, ZE), "#c0b6cc")
    path_fill(c, P.wall_x(XR, Z0, ZE, 0, 1.0), "#8d82a2")
    path_fill(c, P.plane_y(1.0, XR, XR + 0.3, Z0, ZE), "#c6bcd2")
    # chòi cầu thang
    bx0, bx1, bz0, bz1, bh = -14.0, -11.0, 15.0, 18.0, 2.6
    path_fill(c, P.wall_x(bx1, bz0, bz1, 0, bh), "#8a8098")
    path_fill(c, P.face_z(bz0, bx0, bx1, 0, bh), "#a49ab6")
    path_fill(c, P.plane_y(bh, bx0, bx1, bz0, bz1), "#c6bcd2")
    path_fill(c, P.face_z(bz0 - 0.01, bx0 + 1.0, bx0 + 2.0, 0, 2.0), "#5a4e6a")
    # cột ăng-ten
    for (ax, az, ah) in ((-9.0, 19.0, 4.5), (-5.0, 22.0, 3.5), (-16.0, 12.0, 3.8)):
        b0, t0 = P.p(ax, 0, az), P.p(ax, ah, az)
        c.drawLine(*b0, *t0, stroke("#4a4060", 6))
        for j, yy in enumerate((ah * 0.7, ah * 0.85, ah)):
            a_, b_ = P.p(ax - 0.5 + j * 0.1, yy, az), P.p(ax + 0.5 - j * 0.1, yy, az)
            c.drawLine(*a_, *b_, stroke("#4a4060", 5))
    # bồn nước trên chân
    def tank(x, z, r, h, leg, col):
        k = P.f / z
        bx, by = P.p(x, 0, z)
        for dx in (-r * 0.8, r * 0.8):
            c.drawLine(bx + dx * k, by, bx + dx * k, by - leg * k, stroke("#5a5070", max(3.0, 0.08 * k)))
        c.drawLine(bx - r * 0.8 * k, by - leg * 0.5 * k, bx + r * 0.8 * k, by - leg * 0.5 * k, stroke("#5a5070", max(2.0, 0.05 * k)))
        c.drawRect(_R(bx - r * 1.05 * k, by - leg * k - 0.06 * k, bx + r * 1.05 * k, by - leg * k), fill("#5a5070"))
        c.drawRect(_R(bx - r * k, by - (leg + h) * k, bx + r * k, by - leg * k),
                   lin_paint((bx - r * k, 0), (bx + r * k, 0), [shade(col, 0.1), col, shade(col, -0.25)], [0, 0.4, 1]))
        for j in (0.3, 0.6):
            c.drawLine(bx - r * k, by - (leg + h * j) * k, bx + r * k, by - (leg + h * j) * k, stroke(shade(col, -0.18), max(2.0, 0.03 * k)))
        c.drawPath(oval(bx, by - (leg + h) * k, r * k, r * k * 0.28), fill(shade(col, 0.15)))
        c.drawPath(oval(bx, by - (leg + h) * k - 0.05 * k, r * 0.3 * k, r * 0.08 * k), fill(shade(col, -0.2)))
    tank(-4.6, 15.0, 0.6, 1.3, 1.2, "#5a8ac8")
    tank(-7.8, 11.5, 0.7, 1.5, 1.3, "#eef0f4")
    # cục nóng điều hoà sát lan can
    for az in (9.5, 6.8):
        x0, x1, h = 0.35, 1.15, 0.65
        path_fill(c, P.face_z(az, x0, x1, 0, h), "#d9d6e0")
        path_fill(c, P.plane_y(h, x0, x1, az, az + 0.35), "#eceaf0")
        path_fill(c, P.wall_x(x0, az, az + 0.35, 0, h), "#b9b4c4")
        fx_, fy_ = P.p((x0 + x1) / 2 + 0.08, h / 2, az)
        rr = 0.22 * P.f / az
        c.drawCircle(fx_, fy_, rr, fill("#4a4458"))
        for j in range(3):
            c.drawCircle(fx_, fy_, rr * (0.35 + j * 0.25), stroke("#8a849a", 3))
    # dây phơi đồ
    pa, pb = (-6.5, 5.0), (-1.2, 10.5)
    for (px_, pz) in (pa, pb):
        c.drawLine(*P.p(px_, 0, pz), *P.p(px_, 2.0, pz), stroke("#5a5070", max(3.0, 0.06 * P.f / pz)))
    cl_cols = ["#e8833a", "#3a78c2", "#f3c94e", "#d8423a", "#f4efe4", "#c74a9a", "#4fa35a", "#7ab0d8"]
    pts = []
    for i in range(41):
        t = i / 40
        x3 = pa[0] + (pb[0] - pa[0]) * t
        z3 = pa[1] + (pb[1] - pa[1]) * t
        pts.append(P.p(x3, 1.95 - 0.25 * math.sin(t * math.pi), z3))
    pth = skia.Path()
    pth.moveTo(*pts[0])
    for q in pts[1:]:
        pth.lineTo(*q)
    c.drawPath(pth, stroke("#3a3048", 4))
    for i, t in enumerate([0.1, 0.2, 0.31, 0.42, 0.52, 0.63, 0.74, 0.85]):
        x3 = pa[0] + (pb[0] - pa[0]) * t
        z3 = pa[1] + (pb[1] - pa[1]) * t
        hx, hy = P.p(x3, 1.95 - 0.25 * math.sin(t * math.pi), z3)
        k = P.f / z3
        col = cl_cols[i % len(cl_cols)]
        kind = i % 3
        if kind == 0:     # áo
            path_fill(c, poly([(hx - 0.28 * k, hy), (hx + 0.28 * k, hy), (hx + 0.4 * k, hy + 0.18 * k), (hx + 0.24 * k, hy + 0.24 * k),
                               (hx + 0.22 * k, hy + 0.62 * k), (hx - 0.22 * k, hy + 0.62 * k), (hx - 0.24 * k, hy + 0.24 * k),
                               (hx - 0.4 * k, hy + 0.18 * k)]), col)
        elif kind == 1:   # khăn
            c.drawRect(_R(hx - 0.22 * k, hy, hx + 0.22 * k, hy + 0.7 * k), fill(col))
            c.drawRect(_R(hx - 0.22 * k, hy + 0.55 * k, hx + 0.22 * k, hy + 0.6 * k), fill(shade(col, -0.2)))
        else:             # quần
            path_fill(c, poly([(hx - 0.2 * k, hy), (hx + 0.2 * k, hy), (hx + 0.22 * k, hy + 0.75 * k), (hx + 0.04 * k, hy + 0.75 * k),
                               (hx, hy + 0.28 * k), (hx - 0.04 * k, hy + 0.75 * k), (hx - 0.22 * k, hy + 0.75 * k)]), col)
        for dx in (-0.15, 0.15):
            c.drawRect(_R(hx + dx * k - 4, hy - 10, hx + dx * k + 4, hy + 8), fill("#3a3048"))
    # ghế nhựa đỏ + chậu cây
    cx_, cy_ = P.p(-0.4, 0, 5.6)
    k = P.f / 5.6
    c.drawPath(rrect(cx_ - 0.24 * k, cy_ - 0.9 * k, cx_ + 0.24 * k, cy_ - 0.45 * k, 0.06 * k), fill("#c8352e"))
    c.drawPath(rrect(cx_ - 0.28 * k, cy_ - 0.48 * k, cx_ + 0.28 * k, cy_ - 0.4 * k, 0.03 * k), fill("#e04a3e"))
    for dx in (-0.24, 0.24):
        c.drawLine(cx_ + dx * k, cy_ - 0.42 * k, cx_ + dx * 1.1 * k, cy_, stroke("#a82a24", 0.05 * k))
    px_, py_ = P.p(0.7, 0, 3.6)
    k = P.f / 3.6
    quad(c, [(px_ - 0.22 * k, py_ - 0.42 * k), (px_ + 0.22 * k, py_ - 0.42 * k), (px_ + 0.16 * k, py_), (px_ - 0.16 * k, py_)], "#b8643a")
    for j in range(9):
        a = math.pi * (0.15 + 0.7 * j / 8)
        c.drawPath(capsule(px_, py_ - 0.42 * k, px_ + math.cos(a) * 0.6 * k, py_ - 0.42 * k - math.sin(a) * 0.7 * k,
                           0.05 * k, 0.01 * k), fill("#4a7a5a" if j % 2 else "#5a8a6a"))
    # tiền cảnh trái: két nhựa chồng + xô xanh + ống thông hơi
    for (x3, z3, nrow, col) in ((-6.2, 3.3, 3, "#3a78c2"), (-5.3, 3.0, 2, "#e8833a")):
        bx, by = P.p(x3, 0, z3)
        k = P.f / z3
        for j in range(nrow):
            t_ = by - (j + 1) * 0.3 * k
            c.drawRect(_R(bx - 0.25 * k, t_, bx + 0.25 * k, t_ + 0.3 * k), fill(shade(col, -0.04 * j)))
            c.drawRect(_R(bx - 0.25 * k, t_, bx + 0.25 * k, t_ + 0.03 * k), fill(shade(col, 0.15)))
            for i in range(4):
                c.drawRect(_R(bx - 0.2 * k + i * 0.11 * k, t_ + 0.08 * k, bx - 0.13 * k + i * 0.11 * k, t_ + 0.24 * k),
                           fill(shade(col, -0.3)))
    bx, by = P.p(-4.4, 0, 3.6)
    k = P.f / 3.6
    quad(c, [(bx - 0.16 * k, by - 0.34 * k), (bx + 0.16 * k, by - 0.34 * k), (bx + 0.12 * k, by), (bx - 0.12 * k, by)], "#4fa3c8")
    c.drawPath(oval(bx, by - 0.34 * k, 0.16 * k, 0.04 * k), fill("#2f6f90"))
    bx, by = P.p(-9.0, 0, 4.2)
    k = P.f / 4.2
    c.drawRect(_R(bx - 0.12 * k, by - 0.9 * k, bx + 0.12 * k, by), fill("#b9b4c4"))
    c.drawPath(capsule(bx, by - 0.9 * k, bx + 0.3 * k, by - 1.1 * k, 0.13 * k, 0.13 * k), fill("#cfc9d8"))
    # ánh bình minh
    c.drawRect(_R(0, 0, W, H), lin_paint((0, 0), (W, H), [("#ffcf9a", 0.18), ("#ffcf9a", 0.0)]))
    _vignette(c, 0.35)
    mid = s.makeImageSnapshot()
    slots = {"center": P.slot(-2.0, 3.2), "left": P.slot(-3.6, 3.4), "edge": P.slot(0.55, 4.4),
             "laundry": P.slot(-3.2, 6.8), "far": P.slot(-6.0, 10.0)}
    return Scene(far, mid, slots=slots, floor_y=slots["center"]["y"], parallax=(0.85, 1.0, 1.15),
                 lights=[{"x": 900, "y": 1240, "color": "#ffd9a0"}])


# ------------------------------------------------------------------- 28. hẻm nhà phố, dây điện, miếu nhỏ
def scene_hem_nha_pho_dien(tod: str) -> Scene:
    fog = tod in ("fog", "day", "dawn")
    P = Persp(f=1500, cx=W / 2, cy=1050, cam_h=1.6)
    XR, XF, Z0, ZB = 3.2, 4.4, 1.0, 46.0
    sf = new_surface()
    c = sf.getCanvas()
    if fog:
        vgrad(c, 0, 0, W, 1200, ["#bdb8b0", "#d8d2c6", "#e4ded2"])
        _skyline(c, 1100, 41, "#c9c3b8", 80, 300)
    else:
        vgrad(c, 0, 0, W, 1200, ["#1c2040", "#3c4470", "#5a5a86"])
        stars(c, 1300, 0, 2540, 600, 50, seed=28)
        _skyline(c, 1100, 41, "#262a48", 80, 320, lit="#ffd08a", lit_p=0.05)
    far = sf.makeImageSnapshot()
    s = new_surface()
    c = s.getCanvas()
    road = "#9a968e" if fog else "#3a3c4a"
    side = "#b4ada2" if fog else "#4a4a58"
    path_fill(c, P.plane_y(0, -XR, XR, Z0, ZB), road)
    for sd in (-1, 1):
        path_fill(c, P.plane_y(0.12, min(sd * XR, sd * XF), max(sd * XR, sd * XF), Z0, ZB), side)
        path_fill(c, P.wall_x(sd * XR, Z0, ZB, 0, 0.12), shade(side, -0.25))
    z = 2.0
    while z < ZB:
        path_fill(c, P.plane_y(0.001, -0.07, 0.07, z, z + 1.4), "#e8dcb0" if fog else "#c9c0a0")
        z += 3.0
    path_fill(c, P.face_z(ZB, -XF - 2, XF + 2, 0, 7.0), "#b8b0a4" if fog else "#2a2c40")
    rng = random.Random(28)
    segs = [(1.0, 5.0), (5.0, 9.0), (9.0, 13.5), (13.5, 18.0), (18.0, 23.0), (23.0, 29.0), (29.0, 36.0), (36.0, ZB)]
    pal_f = ["#d8cbb4", "#b9c4be", "#d4b8ae", "#c8c4b8", "#d9d0b0", "#b8bcc6"]
    pal_n = ["#5a5a78", "#4a5a68", "#6a5466", "#585870", "#62604e", "#4e5468"]
    awn = ["#c8352e", "#2f6fb0", "#4fa35a", "#e8833a", "#7a5aa0", "#d0a030"]
    ban_cols = ["#c8352e", "#f3c94e", "#2f6fb0", "#e8833a", "#4fa35a"]
    for sd in (-1, 1):
        for si, (za, zb) in enumerate(reversed(segs)):
            si = len(segs) - 1 - si
            col = (pal_f if fog else pal_n)[(si * 2 + (sd > 0)) % 6]
            ht = rng.uniform(8.5, 13.0)
            xf = sd * XF
            path_fill(c, P.wall_x(xf, za, zb, 0, ht), shade(col, -0.08 if sd < 0 else 0))
            path_fill(c, P.wall_x(xf, za, zb, ht - 0.4, ht), shade(col, -0.3))
            path_fill(c, P.wall_x(xf, za, za + 0.15, 0, ht), shade(col, -0.25))
            path_fill(c, P.wall_x(xf * 0.999, za + 0.3, zb - 0.3, 0, 2.7), "#8a8c90" if fog else "#33363e")
            yy = 0.12
            while yy < 2.7:
                c.drawLine(*P.p(xf * 0.998, yy, za + 0.3), *P.p(xf * 0.998, yy, zb - 0.3),
                           stroke("#74767c" if fog else "#262830", max(1.5, 9 / za)))
                yy += 0.14
            if not fog and rng.random() < 0.3 and si > 0:
                path_fill(c, P.wall_x(xf * 0.998, za + 0.6, za + 1.8, 0, 2.4), "#f2c46b", 0.9)
            ac = awn[(si + (sd > 0) * 2) % len(awn)]
            path_fill(c, P.quad([(xf, 3.1, za + 0.1), (xf, 3.1, zb - 0.1), (sd * 3.55, 2.75, zb - 0.1), (sd * 3.55, 2.75, za + 0.1)]),
                      ac if fog else shade(ac, -0.45))
            path_fill(c, P.wall_x(sd * 3.55, za + 0.1, zb - 0.1, 2.5, 2.75), shade(ac, -0.15) if fog else shade(ac, -0.55))
            for wy in (3.8, 6.8, 9.8):
                if wy + 1.6 > ht:
                    continue
                for (w0, w1) in ((za + 0.6, za + 1.7), (zb - 1.7, zb - 0.6)):
                    if w1 - w0 < 0.4 or w0 < za:
                        continue
                    lit = (not fog) and rng.random() < 0.3
                    path_fill(c, P.wall_x(xf * 0.998, w0, w1, wy, wy + 1.3), "#f2c46b" if lit else shade(col, -0.45))
                    path_fill(c, P.wall_x(xf * 0.997, w0 - 0.1, w1 + 0.1, wy - 0.14, wy), shade(col, 0.12))
                path_fill(c, P.quad([(xf, wy - 0.35, za + 0.2), (xf, wy - 0.35, zb - 0.2), (sd * 4.0, wy - 0.35, zb - 0.2),
                                     (sd * 4.0, wy - 0.35, za + 0.2)]), shade(col, -0.2))
            if 1 < si < 6:
                zc = za + 0.4
                bcol = ban_cols[(si + (sd > 0)) % len(ban_cols)]
                path_fill(c, P.face_z(zc, min(sd * 4.35, sd * 4.0), max(sd * 4.35, sd * 4.0), 3.6, 6.4),
                          bcol if fog else shade(bcol, -0.35))
    # biển hiệu nhô ra (chữ = signs)
    def board(sd, z, y0=3.4, y1=4.3):
        a_, b_ = P.p(sd * 4.35, y1, z), P.p(sd * 3.25, y0, z)
        l_, r_ = min(a_[0], b_[0]), max(a_[0], b_[0])
        c.drawLine(*P.p(sd * 4.4, y1 + 0.15, z), *P.p(sd * 3.4, y1 + 0.15, z), stroke("#2a2a30", max(3.0, 30 / z)))
        return [round(l_), round(a_[1]), round(r_), round(b_[1])]
    b1, b2 = board(-1, 4.7), board(1, 8.7)
    # cột điện + dây chằng chịt
    poles = [(-3.35, 4.6), (3.35, 7.2), (-3.35, 13.0), (3.35, 16.5), (-3.35, 24.0), (3.35, 28.0), (-3.35, 36.0)]
    wire = "#1c1c22" if not fog else "#4a4844"
    tops = []
    for (px_, pz) in reversed(poles):
        k = P.f / pz
        b0, t0 = P.p(px_, 0.12, pz), P.p(px_, 8.6, pz)
        c.drawRect(_R(b0[0] - 0.14 * k, t0[1], b0[0] + 0.14 * k, b0[1]), fill("#6e6a66" if fog else "#2a2a32"))
        cb = P.p(px_ - 0.7, 7.9, pz), P.p(px_ + 0.7, 7.9, pz)
        c.drawLine(*cb[0], *cb[1], stroke("#6e6a66" if fog else "#2a2a32", max(4.0, 0.1 * k)))
        c.drawRect(_R(b0[0] - 0.2 * k, t0[1] + 0.9 * k, b0[0] + 0.2 * k, t0[1] + 1.5 * k), fill("#7a7a7a" if fog else "#3a3a44"))
        tops.append((px_, pz))
    for i in range(len(poles)):
        for j in range(i + 1, min(i + 3, len(poles))):
            (xa, za), (xb, zb) = poles[i], poles[j]
            for n in range(4):
                ya, yb = 7.2 + n * 0.22, 7.0 + n * 0.25
                a_, b_ = P.p(xa, ya, za), P.p(xb, yb, zb)
                sag_wire(c, *a_, *b_, rng.uniform(20, 70) * 4 / min(za, zb), wire, max(2.0, 16 / min(za, zb)))
    for (px_, pz) in poles[:4]:
        k = P.f / pz
        cx_, cy_ = P.p(px_, 7.0, pz)
        for n in range(6):
            c.drawPath(oval(cx_ + rng.uniform(-0.3, 0.3) * k, cy_ + rng.uniform(-0.2, 0.3) * k, rng.uniform(0.15, 0.4) * k,
                            rng.uniform(0.06, 0.15) * k), stroke(wire, max(2.0, 0.03 * k)))
        for n in range(3):
            zz = pz + rng.uniform(-1.5, 2.5)
            sag_wire(c, cx_, cy_, *P.p(math.copysign(XF, px_), rng.uniform(4.5, 6.5), zz), 40, wire, max(2.0, 12 / pz))
    # đèn đường
    lx_, lz = -2.3, 13.0
    a_ = P.p(-3.35, 7.4, lz)
    lh = P.p(lx_, 7.1, lz)
    c.drawLine(*a_, *lh, stroke("#2a2a32" if not fog else "#6e6a66", 10))
    c.drawPath(oval(lh[0], lh[1] + 6, 26, 10), fill("#ffe0a0" if not fog else "#f4f0e0"))
    fx_, fy_ = P.p(lx_ + 0.3, 0, lz)
    if not fog:
        glow(c, lh[0], lh[1] + 10, 520, "#ffcf7a", 0.5)
        c.drawPath(poly([(lh[0] - 20, lh[1]), (lh[0] + 20, lh[1]), (fx_ + 380, fy_), (fx_ - 380, fy_)]), fill("#ffcf7a", 0.1))
        ellipse_glow(c, fx_, fy_, 520, 80, "#ffcf7a", 0.5)
    # miếu nhỏ, ghế đỏ, xe máy xanh
    sx_, sy_ = P.p(-3.85, 0.12, 3.8)
    _spirit_house(c, sx_, sy_, P.f / 3.8, not fog)
    for (mx, mz, col) in ((2.95, 6.0, "#3a6ab0"), (2.7, 4.2, "#2f86c8")):
        bx, by = P.p(mx, 0, mz)
        _scooter(c, bx, by, P.f / mz, col if fog else shade(col, -0.35), facing=-1)
    stx, sty = P.p(-2.6, 0, 3.0)
    _plastic_stool(c, stx, sty, 0.45 * P.f / 3.0, "#c8352e" if fog else "#8a2a24")
    if fog:
        vx, vy = P.cx, P.cy
        c.drawRect(_R(0, 0, W, H), rad_paint(vx, vy, 2200, [("#e8e2d6", 0.92), ("#e8e2d6", 0.55), ("#e8e2d6", 0.12)], [0, 0.35, 1]))
        for _ in range(7):
            yy = rng.uniform(800, 1700)
            c.drawPath(oval(rng.uniform(0, W), yy, rng.uniform(800, 1600), rng.uniform(60, 140)), _soft("#f2eee4", 0.35, 50))
        c.drawRect(_R(0, 0, W, H), fill("#e8e2d6", 0.1))
    else:
        tint(s, "#8a90c8", 0.3)
        glow(c, lh[0], lh[1] + 10, 160, "#ffe0a0", 0.6)
        glow(c, sx_, sy_ - 1.5 * P.f / 3.8, 200, "#ffb060", 0.4)
    _vignette(c, 0.3 if fog else 0.45)
    mid = s.makeImageSnapshot()
    slots = {"center": P.slot(0, 3.4), "left": P.slot(-1.5, 3.4), "right": P.slot(1.3, 3.4),
             "shrine": P.slot(-3.0, 3.7), "far": P.slot(0.3, 10.0)}
    signs = [{"text": "NOODLES", "box": b1, "style": "red_board"},
             {"text": "ROOMS", "box": b2, "style": "gold_board"}]
    return Scene(far, mid, slots=slots, signs=signs, floor_y=slots["center"]["y"], parallax=(0.9, 1.0, 1.1),
                 lights=[] if fog else [{"x": round(lh[0]), "y": round(lh[1]), "color": "#ffcf7a"}])


# ------------------------------------------------------------------- 29. phòng trưởng công an
def scene_phong_truong_cong_an(tod: str) -> Scene:
    night = tod == "night"
    s = new_surface()
    c = s.getCanvas()
    _room_shell(c, "#c4d2d2", "#9aa6a2", "#8e9a96", back_y=1460, pattern=False)
    c.drawRect(_R(0, 1150, W, 1460), fill("#a9bcbc"))
    c.drawRect(_R(0, 1140, W, 1160), fill("#8a9e9e"))
    c.drawRect(_R(0, 0, W, 170), fill("#dfe6e6"))
    c.drawRect(_R(0, 165, W, 180), fill("#b4c2c2"))
    for x in (1000, 2840):
        c.drawPath(rrect(x - 320, 60, x + 320, 120, 10), fill("#f4f8f8"))
        ellipse_glow(c, x, 150, 700, 160, "#ffffff", 0.3)
    c.drawCircle(1920, 90, 34, fill("#f4f6f6"))
    c.drawCircle(1920, 90, 10, fill("#d0302a"))
    # huy hiệu khiên-sao bịa (khung)
    c.drawPath(rrect(1700, 300, 2140, 800, 20), fill("#5a3a22"))
    c.drawPath(rrect(1730, 330, 2110, 770, 12), fill("#1e2a4a"))
    sh = skia.Path()
    sh.moveTo(1800, 400)
    sh.lineTo(2040, 400)
    sh.lineTo(2040, 560)
    sh.quadTo(2040, 680, 1920, 730)
    sh.quadTo(1800, 680, 1800, 560)
    sh.close()
    path_fill(c, sh, "#c99a3c")
    c.drawPath(sh, stroke("#f0c766", 8))
    path_fill(c, _star(1920, 560, 95, 40), "#1e2a4a")
    # giấy khen
    for (l_, t_) in ((820, 380), (820, 700), (2720, 380), (2720, 700)):
        c.drawRect(_R(l_, t_, l_ + 330, t_ + 250), fill("#8a6a3a"))
        c.drawRect(_R(l_ + 16, t_ + 16, l_ + 314, t_ + 234), fill("#f4efe0"))
        c.drawRect(_R(l_ + 30, t_ + 30, l_ + 300, t_ + 220), stroke("#c99a3c", 4))
        for j in range(4):
            c.drawLine(l_ + 70, t_ + 70 + j * 30, l_ + 260 - (j % 2) * 40, t_ + 70 + j * 30, stroke("#9a9488", 6))
        c.drawCircle(l_ + 250, t_ + 190, 24, fill("#c8352e"))
    # cửa sổ rèm lá
    wl, wt, wr, wb = 3200, 320, 3720, 1110
    c.drawRect(_R(wl - 24, wt - 24, wr + 24, wb + 24), fill("#e6ecec"))
    vgrad(c, wl, wt, wr, wb, ["#0d1426", "#1d2742"] if night else ["#f4f2e6", "#dfe8ea"])
    y = wt + 10
    while y < wb - 20:
        c.drawRect(_R(wl, y, wr, y + 22), fill("#d9dcd4" if not night else "#4a5468"))
        y += 40
    c.drawLine(wr - 40, wt, wr - 40, wb + 120, stroke("#9aa0a0", 4))
    # tủ hồ sơ + cúp
    c.drawRect(_R(140, 760, 620, 1500), fill("#7d8a8e"))
    for j in range(4):
        y = 790 + j * 175
        c.drawRect(_R(160, y, 600, y + 155), fill("#8d9a9e"))
        c.drawPath(rrect(330, y + 60, 430, y + 84, 8), fill("#c9ccd2"))
    for (tx, th) in ((240, 220), (390, 170), (520, 200)):
        c.drawRect(_R(tx - 45, 730, tx + 45, 760), fill("#4a3a2a"))
        quad(c, [(tx - 12, 730), (tx + 12, 730), (tx + 8, 760 - th * 0.45), (tx - 8, 760 - th * 0.45)], "#c99a3c")
        p = skia.Path()
        p.addArc(_R(tx - 50, 760 - th - 50, tx + 50, 760 - th * 0.45), 0, 180)
        p.lineTo(tx - 50, 760 - th)
        p.lineTo(tx + 50, 760 - th)
        p.close()
        path_fill(c, p, "#e0b450")
        c.drawRect(_R(tx - 50, 760 - th - 4, tx + 50, 760 - th + 6), fill("#f0c766"))
    # ghế da sau bàn
    c.drawPath(rrect(1680, 880, 2160, 1420, 60), fill("#4a2e22"))
    for (bx_, by_) in ((1780, 980), (1920, 980), (2060, 980), (1780, 1110), (1920, 1110), (2060, 1110)):
        c.drawCircle(bx_, by_, 9, fill("#2e1c14"))
    # bàn gỗ lớn
    DL, DR, DT = 1050, 2790, 1290
    c.drawRect(_R(DL - 40, DT - 50, DR + 40, DT), fill("#9a6a42"))
    c.drawRect(_R(DL - 40, DT - 50, DR + 40, DT - 40), fill("#b8845a"))
    c.drawRect(_R(DL, DT, DR, 1690), fill("#6b4a32"))
    c.drawRect(_R(DL + 40, DT + 40, DR - 40, 1650), stroke(shade("#6b4a32", -0.25), 8))
    for j in range(3):
        c.drawPath(rrect(DL + 80, DT + 70 + j * 110, DL + 500, DT + 160 + j * 110, 8), fill(shade("#6b4a32", 0.08)))
        c.drawPath(rrect(DL + 250, DT + 108 + j * 110, DL + 330, DT + 122 + j * 110, 6), fill("#c99a3c"))
    # đồ trên bàn
    lx_ = 1250
    c.drawPath(oval(lx_, DT - 52, 80, 16), fill("#c99a3c"))
    c.drawRect(_R(lx_ - 8, DT - 230, lx_ + 8, DT - 52), fill("#c99a3c"))
    p = skia.Path()
    p.addArc(_R(lx_ - 130, DT - 300, lx_ + 130, DT - 170), 180, 180)
    p.close()
    path_fill(c, p, "#2f7a5a")
    c.drawRect(_R(lx_ - 130, DT - 238, lx_ + 130, DT - 222), fill("#c99a3c"))
    glow(c, lx_, DT - 160, 260, "#fff1c8", 0.5)
    c.drawPath(rrect(1450, DT - 120, 1640, DT - 50, 14), fill("#2b2d33"))
    c.drawPath(capsule(1460, DT - 135, 1630, DT - 135, 24, 24), fill("#1d1f24"))
    for j in range(3):
        c.drawPath(rrect(2400 + j * 6, DT - 100 - j * 70, 2640 - j * 6, DT - 50 - j * 70, 8), fill("#f4f1e8"))
        c.drawRect(_R(2400 + j * 6, DT - 80 - j * 70, 2640 - j * 6, DT - 68 - j * 70), fill("#c8352e"))
    for j in range(3):
        c.drawRect(_R(2120 + j * 10, DT - 64 + j * 4, 2340 + j * 10, DT - 54 + j * 4), fill("#f4f1e8"))
    if night:
        tint(s, "#5a6890", 0.55)
        glow(c, lx_, DT - 160, 320, "#fff1c8", 0.55)
    _vignette(c, 0.35)
    mid = s.makeImageSnapshot()
    slots = {"chief": {"x": 1920, "y": 1520, "scale": 0.8, "clip_bottom": DT - 40},
             "visitor": frac_slot({"x": 0.30, "y": 0.92, "scale": 1.0}),
             "center": frac_slot({"x": 0.50, "y": 0.93, "scale": 1.02}),
             "right": frac_slot({"x": 0.76, "y": 0.92, "scale": 1.0})}
    signs = [{"text": "CHIEF", "box": [1760, DT - 120, 2080, DT - 44], "style": "gold_board"}]
    return Scene(None, mid, slots=slots, signs=signs, floor_y=slots["center"]["y"],
                 lights=[{"x": lx_, "y": DT - 200, "color": "#fff1c8"}])


# ------------------------------------------------------------------- 30. phòng hồi sức ICU
def scene_phong_icu(tod: str) -> Scene:
    night = tod == "night"
    s = new_surface()
    c = s.getCanvas()
    _room_shell(c, "#c9d6d2", "#b4c2be", "#a8b6b2", back_y=1440, pattern=False)
    c.drawRect(_R(0, 0, W, 150), fill("#e4ecea"))
    c.drawRect(_R(0, 145, W, 160), fill("#b4c4c0"))
    c.drawPath(rrect(1620, 50, 2220, 110, 10), fill("#f6fafa"))
    # cửa kính ICU
    c.drawRect(_R(180, 330, 800, 1440), fill("#8a9a9a"))
    vgrad(c, 210, 360, 770, 1440, ["#9ec4c8", "#7aa4aa"], a=0.85)
    c.drawLine(490, 360, 490, 1440, stroke("#8a9a9a", 16))
    reflections(c, 210, 360, 770, 1440, 3, 0.15, seed=30)
    c.drawRect(_R(210, 900, 770, 940), fill("#e8f0ee", 0.8))
    # thanh khí y tế
    c.drawPath(rrect(1060, 950, 2790, 1010, 10), fill("#e6ecea"))
    for i, col in enumerate(("#4fa35a", "#f4f4f0", "#3a78c2", "#f3c94e", "#2b2d33", "#4fa35a", "#3a78c2")):
        x = 1160 + i * 230
        c.drawCircle(x, 980, 22, fill(col))
        c.drawCircle(x, 980, 22, stroke("#8a9a9a", 4))
    # monitor
    ml, mt, mr, mb = 1080, 360, 1620, 760
    c.drawLine((ml + mr) / 2, mb, (ml + mr) / 2, 950, stroke("#8a9a9a", 18))
    c.drawPath(rrect(ml, mt, mr, mb, 24), fill("#9aa4a4"))
    c.drawPath(rrect(ml + 24, mt + 24, mr - 24, mb - 24, 10), fill("#0c1214"))
    _ecg(c, ml + 40, mt + 110, ml + 360, 60, "#3ad86a", 5, 160)
    _sine(c, ml + 40, mt + 210, ml + 360, 26, "#3ac8e0", 5, 120)
    _sine(c, ml + 40, mt + 300, ml + 360, 18, "#f3d04e", 5, 180)
    text_center(c, "HR 72", ml + 445, mt + 105, 46, "#3ad86a")
    text_center(c, "SpO2 97", ml + 445, mt + 200, 38, "#3ac8e0")
    text_center(c, "BP 118/76", ml + 445, mt + 290, 32, "#f3d04e")
    c.drawCircle(mr - 50, mt + 50, 10, fill("#ff3b30"))
    # cửa sổ đêm + phố
    wl, wt, wr, wb = 2960, 330, 3660, 980
    c.drawRect(_R(wl - 26, wt - 26, wr + 26, wb + 26), fill("#e6ecea"))
    c.save()
    c.clipRect(_R(wl, wt, wr, wb))
    vgrad(c, wl, wt, wr, wb, ["#0b1022", "#1d2742"] if night else ["#a9c4dc", "#e4eef4"])
    if night:
        stars(c, wl, wt, wr, wt + 300, 50, seed=31)
    _skyline(c, wb + 10, 31, "#141a30" if night else "#8a9aaa", 120, 420, wmin=70, wmax=160,
             lit="#ffd98a" if night else None, lit_p=0.25, l=wl - 20, r=wr + 20)
    c.restore()
    c.drawLine((wl + wr) / 2, wt, (wl + wr) / 2, wb, stroke("#e6ecea", 18))
    # cột truyền dịch
    ix = 1200
    c.drawPath(oval(ix, 1780, 140, 26), fill("#6e7878"))
    c.drawRect(_R(ix - 9, 500, ix + 9, 1780), fill("#c9d2d2"))
    c.drawLine(ix - 70, 520, ix + 70, 520, stroke("#c9d2d2", 10))
    c.drawPath(rrect(ix - 60, 540, ix + 40, 760, 30), fill("#e4f4f8", 0.85))
    c.drawRect(_R(ix - 40, 620, ix + 20, 740), fill("#bfe4f0", 0.8))
    p = skia.Path()
    p.moveTo(ix - 10, 760)
    p.cubicTo(ix - 10, 1000, 1400, 1100, 1560, 1360)
    c.drawPath(p, stroke("#e4f4f8", 5, 0.9))
    # máy thở
    vl, vt, vr, vb = 2590, 860, 2900, 1360
    c.drawLine((vl + vr) / 2, vb, (vl + vr) / 2, 1720, stroke("#8a9a9a", 18))
    c.drawLine(vl, 1720, vr, 1720, stroke("#6e7878", 14))
    for x in (vl, vr):
        c.drawCircle(x, 1740, 18, fill("#2b2d33"))
    c.drawPath(rrect(vl, vt, vr, vb, 22), fill("#e4eaea"))
    c.drawPath(rrect(vl + 24, vt + 30, vr - 24, vt + 220, 10), fill("#0c1214"))
    _sine(c, vl + 40, vt + 125, vr - 40, 40, "#3ac8e0", 5, 110)
    for j in range(3):
        c.drawCircle(vl + 80 + j * 75, vt + 300, 24, fill("#8a9a9a"))
    p = skia.Path()
    p.moveTo(vl, vt + 400)
    p.cubicTo(vl - 200, vt + 420, 2400, 1220, 2260, 1260)
    c.drawPath(p, stroke("#b9d4dc", 22))
    # giường
    c.drawPath(rrect(1420, 980, 2420, 1250, 30), fill("#e8eeee"))
    c.drawRect(_R(1460, 1020, 2380, 1060), fill("#c9d2d2"))
    bed = poly([(1400, 1240), (2440, 1240), (2600, 1630), (1240, 1630)])
    path_fill(c, bed, "#f4f6f6")
    c.drawPath(oval(1920, 1250, 260, 70), fill("#ffffff"))
    blank = poly([(1340, 1380), (2500, 1380), (2610, 1640), (1230, 1640)])
    path_fill(c, blank, "#e8eef8")
    c.save()
    c.clipPath(blank, skia.ClipOp.kIntersect, True)
    for i in range(-12, 13):
        x_top = 1920 + i * 60
        x_bot = 1920 + i * 74
        if i % 2 == 0:
            quad(c, [(x_top - 18, 1380), (x_top + 18, 1380), (x_bot + 22, 1640), (x_bot - 22, 1640)], "#7aa0c8")
    c.restore()
    c.drawRect(_R(1330, 1370, 2510, 1392), fill("#ffffff"))
    for sd in (-1, 1):
        x0 = 1920 + sd * 640
        c.drawLine(x0, 1300, x0 + sd * 70, 1560, stroke("#9aa4a4", 16))
    c.drawPath(rrect(1230, 1630, 2610, 1800, 24), fill("#dfe6e6"))
    c.drawRect(_R(1230, 1630, 2610, 1650), fill("#b4bebe"))
    c.drawPath(rrect(1820, 1660, 2020, 1780, 8), fill("#f4f1e8"))
    c.drawRect(_R(1880, 1650, 1960, 1672), fill("#6e7878"))
    for x in (1290, 2550):
        c.drawRect(_R(x - 14, 1800, x + 14, 1880), fill("#8a9a9a"))
        c.drawCircle(x, 1890, 22, fill("#2b2d33"))
    # ghế thăm
    ch = "#3a8a8a"
    c.drawPath(rrect(2960, 1230, 3320, 1620, 36), fill(ch))
    c.drawPath(rrect(2930, 1600, 3350, 1680, 22), fill(shade(ch, 0.12)))
    for x in (2960, 3320):
        c.drawRect(_R(x - 12, 1680, x + 12, 1960), fill("#6e7878"))
    if night:
        tint(s, "#4e5c82", 0.6)
        glow(c, (ml + mr) / 2, (mt + mb) / 2, 520, "#3ad86a", 0.18)
        glow(c, (vl + vr) / 2, vt + 125, 260, "#3ac8e0", 0.2)
        glow(c, 1920, 80, 900, "#dff4ee", 0.12)
        _ecg(c, ml + 40, mt + 110, ml + 360, 60, "#4af07a", 5, 160)
        text_center(c, "HR 72", ml + 445, mt + 105, 46, "#4af07a")
        text_center(c, "SpO2 97", ml + 445, mt + 200, 38, "#4ad8f0")
        text_center(c, "BP 118/76", ml + 445, mt + 290, 32, "#ffe05e")
        c.drawCircle(mr - 50, mt + 50, 10, fill("#ff3b30"))
        glow(c, mr - 50, mt + 50, 50, "#ff3b30", 0.6)
    _vignette(c, 0.42)
    mid = s.makeImageSnapshot()
    slots = {"bed": {"x": 1920, "y": 1600, "scale": 0.8, "clip_bottom": 1400},
             "bedside_left": frac_slot({"x": 0.22, "y": 0.92, "scale": 1.0}),
             "bedside_right": frac_slot({"x": 0.71, "y": 0.92, "scale": 1.0}),
             "center": frac_slot({"x": 0.50, "y": 0.95, "scale": 1.05}),
             "door": frac_slot({"x": 0.13, "y": 0.70, "scale": 0.82})}
    signs = [{"text": "ICU 4", "box": [270, 470, 700, 580], "style": "white_board"}]
    baked = [_baked(t, ml + 445, y, sz) for (t, y, sz) in (("HR 72", mt + 105, 46), ("SpO2 97", mt + 200, 38),
                                                          ("BP 118/76", mt + 290, 32))]
    return Scene(None, mid, slots=slots, signs=signs, baked_signs=baked, floor_y=slots["center"]["y"],
                 lights=[{"x": (ml + mr) / 2, "y": (mt + mb) / 2, "color": "#3ad86a"}])


# ------------------------------------------------------------------- 31. chợ có mái che (sáng sớm)
def scene_cho_co_mai(tod: str) -> Scene:
    night = tod == "night"
    sf = new_surface()
    c = sf.getCanvas()
    c.drawRect(_R(0, 0, W, H), fill("#5e6a66"))
    rng = random.Random(31)
    for _ in range(14):
        x, y = rng.uniform(0, W), rng.uniform(820, 1000)
        r = rng.uniform(160, 300)
        p = skia.Path()
        p.addArc(_R(x - r, y - r * 0.6, x + r, y + r * 0.6), 180, 180)
        path_fill(c, p, rng.choice(["#c8352e", "#2f6fb0", "#e8833a", "#4fa35a", "#d0a030"]))
        c.drawRect(_R(x - 6, y, x + 6, y + 500), fill("#3a403e"))
    for _ in range(18):
        x, y = rng.uniform(0, W), rng.uniform(1100, 1250)
        col = rng.choice(["#3a4a5a", "#7a4a5a", "#4a6a5a", "#8a7a5a", "#5a4a7a"])
        c.drawCircle(x, y, 44, fill("#6a5446"))
        quad(c, [(x - 60, y + 50), (x + 60, y + 50), (x + 80, y + 330), (x - 80, y + 330)], col)
    far = _blurred(sf.makeImageSnapshot(), 22)
    s = new_surface()
    c = s.getCanvas()
    # mái tôn + vì kèo
    c.drawRect(_R(0, 0, W, 700), fill("#4a5250"))
    for x in range(0, W, 38):
        c.drawLine(x, 0, x, 300, stroke("#3e4644", 10))
    vgrad(c, 0, 300, W, 700, ["#3e4644", "#525a58"])
    for x in range(0, W, 60):
        c.drawLine(x, 300, x + (x - W / 2) * 0.05, 700, stroke("#465050", 6))
    c.drawRect(_R(0, 250, W, 290), fill("#2e3432"))
    c.drawRect(_R(0, 660, W, 700), fill("#2e3432"))
    x = 0
    up = True
    while x < W:
        c.drawLine(x, 680 if up else 270, x + 200, 270 if up else 680, stroke("#2e3432", 14))
        x += 200
        up = not up
    for x in (180, 1980, 3660):
        c.drawRect(_R(x - 26, 690, x + 26, 1660), fill("#3a4240"))
    for x in (1000, 2900):
        c.drawLine(x, 700, x, 780, stroke("#1a1d1c", 4))
        _tube(c, x, 780, 520, on=True, col="#f4faf4")
    # quầy thuốc (chữ thập xanh)
    c.drawRect(_R(0, 800, 380, 1640), fill("#d9dcd4"))
    c.drawRect(_R(20, 900, 360, 1400), fill("#9ec4c8", 0.6))
    for j in range(4):
        y = 1000 + j * 100
        c.drawRect(_R(20, y, 360, y + 10), fill("#eef2f0"))
        for i in range(6):
            c.drawRect(_R(40 + i * 52, y - 60, 80 + i * 52, y), fill(rng.choice(PRODUCTS[:-1]), 0.85))
    c.drawRect(_R(110, 690, 270, 850), fill("#f4f6f4"))
    c.drawRect(_R(170, 710, 210, 830), fill("#2f9a5a"))
    c.drawRect(_R(130, 750, 250, 790), fill("#2f9a5a"))
    # sạp rau quả: mái sọc + nải chuối
    FL, FR = 430, 1500
    for i in range(10):
        x0 = FL - 30 + (FR - FL + 60) * i / 10
        x1 = FL - 30 + (FR - FL + 60) * (i + 1) / 10
        quad(c, [(x0 + 20, 820), (x1 + 20, 820), (x1, 950), (x0, 950)], "#2f8a5a" if i % 2 == 0 else "#eef2e8")
    c.drawRect(_R(FL - 30, 950, FR + 30, 970), fill("#1f5a3a"))
    for bx_ in (560, 760, 1000, 1240, 1420):
        c.drawLine(bx_, 970, bx_, 1010, stroke("#3a2a1e", 6))
        for j in range(7):
            a = (j - 3) * 0.22
            c.drawPath(capsule(bx_ + math.sin(a) * 40, 1010 + j % 2 * 20, bx_ + math.sin(a) * 90, 1150 + abs(j - 3) * 10, 18, 12),
                       fill("#f3c94e" if j % 3 else "#d9b03a"))
    c.drawRect(_R(FL, 1300, FR, 1340), fill("#9a6a42"))
    c.drawRect(_R(FL + 20, 1340, FR - 20, 1640), fill("#7a5234"))
    for y in range(1380, 1640, 60):
        c.drawLine(FL + 20, y, FR - 20, y, stroke("#5a3a24", 6))
    for (cx0, cx1, col, r) in ((FL + 40, FL + 300, "#f08a2c", 34), (FL + 320, FL + 560, "#8ac84a", 30),
                               (FL + 580, FL + 820, "#d8423a", 22), (FL + 840, FR - 30, "#b4d88a", 60)):
        for row in range(3):
            n = int((cx1 - cx0) / (r * 2)) - row
            for i in range(n):
                x = cx0 + r + row * r + i * r * 2
                c.drawCircle(x, 1300 - r - row * r * 1.6, r, fill(shade(col, -0.05 * row + rng.uniform(-0.05, 0.05))))
    # sạp thịt: quầy ốp gạch trắng
    BL, BR, BT = 1600, 2720, 1330
    c.drawLine(BL + 40, 900, BR - 40, 900, stroke("#8a9098", 14))
    for i in range(6):
        hx = BL + 140 + i * 180
        c.drawLine(hx, 900, hx, 950, stroke("#c9ccd2", 6))
        c.drawPath(rrect(hx - 55, 950, hx + 55, 1130 + (i % 2) * 40, 40), fill("#d98a80"))
        c.drawRect(_R(hx - 55, 960, hx + 55, 990), fill("#f4e4dc"))
    c.drawLine(BL + 340, 700, BL + 340, 730, stroke("#1a1d1c", 4))
    c.drawLine(BR - 340, 700, BR - 340, 730, stroke("#1a1d1c", 4))
    c.drawRect(_R(BL, BT, BR, BT + 40), fill("#dfe5e9"))
    c.drawRect(_R(BL + 10, BT + 40, BR - 10, 1640), fill("#f2f4f4"))
    _tile_grid(c, BL + 10, BT + 40, BR - 10, 1640, 70, 70, "#c9d0d4", 4)
    c.drawPath(oval(2380, BT - 30, 150, 34), fill("#c49a6a"))
    c.drawRect(_R(2230, BT - 30, 2530, BT), fill("#8a5a3a"))
    c.drawPath(oval(2380, BT - 30, 150, 34), fill("#c49a6a"))
    c.drawPath(rrect(1700, BT - 160, 1900, BT, 14), fill("#e4e8ea"))
    c.drawCircle(1800, BT - 220, 80, fill("#f4f6f6"))
    c.drawCircle(1800, BT - 220, 80, stroke("#8a9098", 10))
    c.drawLine(1800, BT - 220, 1840, BT - 270, stroke("#d0302a", 6))
    c.drawPath(rrect(1960, BT - 40, 2180, BT, 8), fill("#c9d0d4"))
    for i in range(6):
        c.drawPath(rrect(1980 + i * 32, BT - 70, 2008 + i * 32, BT - 40, 6), fill("#d98a80"))
    # sạp cá: quầy xanh + thùng xốp
    SL = 2800
    c.drawRect(_R(SL, 1340, W, 1380), fill("#5a96d8"))
    c.drawRect(_R(SL + 10, 1380, W, 1640), fill("#3a78c2"))
    for x in range(SL + 60, W, 260):
        c.drawRect(_R(x, 1160, x + 220, 1340), fill("#f4f6f6"))
        c.drawRect(_R(x, 1160, x + 220, 1190), fill("#e4e8ea"))
        for j in range(3):
            fx_, fy_ = x + 70 + j * 45, 1180 - j * 6
            c.drawPath(oval(fx_, fy_, 50, 16), fill("#9aa8b0"))
            quad(c, [(fx_ + 46, fy_), (fx_ + 76, fy_ - 18), (fx_ + 76, fy_ + 18)], "#8a98a0")
        for j in range(6):
            c.drawCircle(x + 30 + j * 32, 1168, 10, fill("#eef8ff"))
    c.drawPath(capsule(SL + 40, 1400, SL + 40, 1640, 18, 18), fill("#4fa35a"))
    # sàn ướt
    _persp_floor(c, 1640, "#7d877f", "#6e7870", vx=1920, vy=900, spacing=420, dz=0.12)
    for (px_, py_, rx) in ((900, 1880, 360), (2600, 1980, 460), (1700, 1760, 220)):
        c.drawPath(oval(px_, py_, rx, rx * 0.14), fill("#a9b8b4", 0.5))
        c.drawPath(oval(px_ + rx * 0.2, py_, rx * 0.35, rx * 0.03), fill("#ffffff", 0.35))
    if night:
        tint(s, "#5a6890", 0.55)
    else:
        tint(s, "#d4e0d8", 0.15)
    _vignette(c, 0.35)
    mid = s.makeImageSnapshot()
    slots = {"butcher": {"x": 2160, "y": 1620, "scale": 0.92, "clip_bottom": BT + 10},
             "fruit_vendor": {"x": 960, "y": 1620, "scale": 0.92, "clip_bottom": 1310},
             "left": frac_slot({"x": 0.28, "y": 0.93, "scale": 1.05}),
             "center": frac_slot({"x": 0.50, "y": 0.93, "scale": 1.05}),
             "right": frac_slot({"x": 0.75, "y": 0.93, "scale": 1.05})}
    signs = [{"text": "BUTCHER", "box": [1820, 730, 2500, 850], "style": "red_board"},
             {"text": "FISH", "box": [3120, 760, 3500, 860], "style": "red_board"},
             {"text": "FRUIT & VEG", "box": [600, 1000 - 250, 1330, 1000 - 150], "style": "white_board"}]
    return Scene(far, mid, slots=slots, signs=signs, floor_y=slots["center"]["y"], parallax=(0.9, 1.0, 1.1))


# ------------------------------------------------------------------- 32. phòng điều tra tại nhà (bảng ghim)
def scene_phong_dieu_tra(tod: str) -> Scene:
    night = tod != "day"
    s = new_surface()
    c = s.getCanvas()
    BY = 1480
    c.drawRect(_R(0, 0, W, BY), fill("#d9c9a8"))
    vgrad(c, 0, 0, W, 300, ["#b8a888", "#d9c9a8"])
    c.drawRect(_R(0, BY - 40, W, BY), fill("#a8987a"))
    _persp_floor(c, BY, "#8a6a4a", "#6e5238", vx=1920, vy=1000, spacing=230, dz=0.0)
    # bảng ghim lie
    L, T, R, B = 520, 250, 2440, 1180
    c.drawRect(_R(L, T, R, B), fill("#6b4a32"))
    c.drawRect(_R(L + 34, T + 34, R - 34, B - 34), fill("#c49a6a"))
    rng = random.Random(32)
    for _ in range(500):
        c.drawCircle(rng.uniform(L + 40, R - 40), rng.uniform(T + 40, B - 40), rng.uniform(2, 5), fill("#a87e50", 0.5))
    pins = []
    # bản đồ
    ml, mt = 1440, 300
    c.save()
    c.rotate(1.5, ml + 270, mt + 180)
    c.drawRect(_R(ml, mt, ml + 540, mt + 380), fill("#e4ecd4"))
    for (a_, b_) in (((ml, mt + 120), (ml + 540, mt + 200)), ((ml + 180, mt), (ml + 260, mt + 380)),
                     ((ml + 380, mt), (ml + 330, mt + 380)), ((ml, mt + 300), (ml + 540, mt + 260))):
        c.drawLine(*a_, *b_, stroke("#f8f6ee", 16))
    p = skia.Path()
    p.moveTo(ml, mt + 40)
    p.cubicTo(ml + 200, mt + 80, ml + 300, mt + 300, ml + 540, mt + 340)
    c.drawPath(p, stroke("#8ab8d8", 26))
    c.drawCircle(ml + 310, mt + 220, 70, _dashed("#d0202a", 7, 18, 12))
    for (dx, dy) in ((290, 200), (330, 240), (360, 190)):
        c.drawCircle(ml + dx, mt + dy, 9, fill("#d0202a"))
    c.restore()
    pins.append((ml + 270, mt + 14))
    # thẻ người mất tích
    cards = [(640, 330), (900, 360), (1160, 320), (660, 760), (940, 800), (2080, 740)]
    for (x, y) in cards:
        c.save()
        c.rotate(rng.uniform(-5, 5), x + 100, y + 140)
        c.drawRect(_R(x + 6, y + 8, x + 206, y + 288), fill("#000000", 0.15))
        c.drawRect(_R(x, y, x + 200, y + 280), fill("#f4f1e8"))
        c.drawRect(_R(x, y, x + 200, y + 46), fill("#c8352e"))
        c.drawRect(_R(x + 40, y + 62, x + 160, y + 182), fill("#9aa0a6"))
        c.drawCircle(x + 100, y + 108, 26, fill("#6e747a"))
        c.drawPath(oval(x + 100, y + 182, 48, 34), fill("#6e747a"))
        c.drawRect(_R(x + 40, y + 178, x + 160, y + 184), fill("#9aa0a6"))
        for j in range(3):
            c.drawLine(x + 24, y + 210 + j * 22, x + 176 - j * 30, y + 210 + j * 22, stroke("#8a8a8a", 6))
        c.restore()
        pins.append((x + 100, y + 14))
    # giấy note + ảnh + biên lai
    for (x, y, col) in ((1250, 760, "#f3e36a"), (1420, 820, "#f4a6c0"), (1600, 760, "#9fd0f0"), (1820, 820, "#f3e36a"),
                        (2160, 400, "#f4a6c0"), (2260, 560, "#9fd0f0")):
        c.save()
        c.rotate(rng.uniform(-8, 8), x + 70, y + 70)
        c.drawRect(_R(x, y, x + 140, y + 140), fill(col))
        for j in range(3):
            c.drawLine(x + 16, y + 40 + j * 28, x + 120 - j * 20, y + 40 + j * 28, stroke(shade(col, -0.35), 5))
        c.restore()
        pins.append((x + 70, y + 12))
    for (x, y) in ((2080, 330), (1700, 1000 - 40)):
        c.drawRect(_R(x, y, x + 170, y + 200), fill("#f4f4f0"))
        c.drawRect(_R(x + 14, y + 14, x + 156, y + 150), fill("#7a8a9a"))
        pins.append((x + 85, y + 10))
    order = [0, 1, 7, 2, 3, 9, 4, 8, 5, 6, 11, 12]
    for i in range(len(order) - 1):
        a_, b_ = pins[order[i] % len(pins)], pins[order[i + 1] % len(pins)]
        c.drawLine(*a_, *b_, stroke("#c8202a", 5))
    for (x, y) in pins:
        c.drawCircle(x, y, 14, fill("#d0302a"))
        c.drawCircle(x - 4, y - 4, 5, fill("#ff8a7a"))
    # bàn chân chữ A + laptop + đèn kỹ thuật
    DL, DR, DT = 2600, 3640, 1300
    for x in (DL + 140, DR - 140):
        c.drawLine(x - 120, 1740, x, DT + 30, stroke("#3a3a40", 22))
        c.drawLine(x + 120, 1740, x, DT + 30, stroke("#3a3a40", 22))
        c.drawLine(x - 70, 1580, x + 70, 1580, stroke("#3a3a40", 14))
    c.drawRect(_R(DL, DT, DR, DT + 40), fill("#c9a878"))
    c.drawRect(_R(DL, DT + 40, DR, DT + 56), fill("#9a7a50"))
    lpl, lpr = 2840, 3260
    quad(c, [(lpl - 30, DT), (lpr + 30, DT), (lpr, DT - 26), (lpl, DT - 26)], "#8a9098")
    quad(c, [(lpl, DT - 26), (lpr, DT - 26), (lpr - 20, DT - 300), (lpl + 20, DT - 300)], "#4a4e56")
    quad(c, [(lpl + 20, DT - 40), (lpr - 20, DT - 40), (lpr - 36, DT - 284), (lpl + 36, DT - 284)], "#bcd8f0")
    for j in range(5):
        c.drawLine(lpl + 70, DT - 240 + j * 36, lpr - 90 - (j % 2) * 60, DT - 240 + j * 36, stroke("#7a9ab8", 8))
    ax0, ay0 = 3480, DT
    c.drawPath(oval(ax0, ay0 - 10, 70, 18), fill("#2b2d33"))
    c.drawLine(ax0, ay0 - 10, ax0 - 60, ay0 - 380, stroke("#2b2d33", 14))
    c.drawLine(ax0 - 60, ay0 - 380, ax0 - 260, ay0 - 300, stroke("#2b2d33", 14))
    quad(c, [(ax0 - 300, ay0 - 330), (ax0 - 220, ay0 - 330), (ax0 - 170, ay0 - 230), (ax0 - 350, ay0 - 230)], "#c8352e")
    c.drawPath(poly([(ax0 - 350, ay0 - 230), (ax0 - 170, ay0 - 230), (ax0 - 40, DT), (ax0 - 480, DT)]), fill("#ffe0a0", 0.16))
    for j in range(4):
        c.drawRect(_R(3330 + j * 6, DT - 20 - j * 12, 3560 - j * 6, DT - 10 - j * 12), fill("#f4f1e8"))
    # ghế đỏ, thùng giấy, nệm
    _plastic_stool(c, 3050, 1800, 300, "#c8352e")
    c.drawRect(_R(1300, 1520, 1700, 1780), fill("#b8864a"))
    quad(c, [(1300, 1520), (1700, 1520), (1760, 1440), (1360, 1440)], "#c99a5a")
    quad(c, [(1300, 1520), (1240, 1440), (1300, 1430), (1340, 1520)], "#a87a40")
    c.drawRect(_R(1320, 1600, 1680, 1616), fill("#d9b87a"))
    c.drawPath(rrect(60, 1820, 1150, 1960, 30), fill("#e4dccc"))
    c.drawPath(rrect(60, 1800, 1150, 1830, 14), fill("#f0ebe0"))
    c.drawPath(rrect(400, 1760, 1150, 1900, 40), fill("#5a7aa0"))
    c.drawPath(rrect(110, 1740, 380, 1820, 30), fill("#f4f4f0"))
    if night:
        tint(s, "#4a4c78", 0.6)
        glow(c, ax0 - 260, ay0 - 250, 700, "#ffcf7a", 0.45)
        ellipse_glow(c, ax0 - 260, DT, 520, 90, "#ffe0a0", 0.4)
        glow(c, (lpl + lpr) / 2, DT - 160, 420, "#9fd0ff", 0.3)
    _vignette(c, 0.5)
    mid = s.makeImageSnapshot()
    slots = {"board": frac_slot({"x": 0.40, "y": 0.92, "scale": 1.02}),
             "desk": {"x": 3020, "y": 1930, "scale": 1.0},
             "center": frac_slot({"x": 0.55, "y": 0.93, "scale": 1.04}),
             "left": frac_slot({"x": 0.20, "y": 0.92, "scale": 1.0})}
    return Scene(None, mid, slots=slots, floor_y=slots["center"]["y"],
                 lights=[{"x": ax0 - 260, "y": ay0 - 250, "color": "#ffcf7a"}])


# ------------------------------------------------------------------- 33. bến gỗ + nhà sàn ven sông (đêm)
def _stilt_house(c, l, r, base, h, col, lit, rng, water=1220) -> None:
    c.drawRect(_R(l, base - h, r, base), fill(col))
    quad(c, [(l - 30, base - h), (r + 30, base - h), ((l + r) / 2 + 20, base - h - h * 0.55), ((l + r) / 2 - 20, base - h - h * 0.55)],
         shade(col, -0.15))
    x = l + 16
    while x < r:
        c.drawLine(x, base, x + rng.uniform(-6, 6), water + 30, stroke(col, 8))
        x += 70
    if lit:
        wl = l + (r - l) * rng.uniform(0.15, 0.55)
        c.drawRect(_R(wl, base - h * 0.7, wl + 60, base - h * 0.3), fill("#ffcf7a"))
        glow(c, wl + 30, base - h * 0.5, 120, "#ffb060", 0.4)
        for k in range(5):
            y = water + 40 + k * 26
            c.drawRect(_R(wl + rng.uniform(-20, 10), y, wl + 60 + rng.uniform(-10, 20), y + 7), fill("#ffcf7a", 0.4 - k * 0.07))


def scene_ben_go_nha_san(tod: str) -> Scene:
    dusk = tod == "dusk"
    WY = 1220
    sf = new_surface()
    c = sf.getCanvas()
    vgrad(c, 0, 0, W, WY, ["#1a1630", "#2a2440", "#4a3a5a"] if not dusk else ["#2e3370", "#6a5a8c", "#c98fa6"])
    stars(c, 0, 0, W, 700, 220, seed=33)
    glow(c, 600, 260, 220, "#f1ead2", 0.35)
    c.drawCircle(600, 260, 64, fill("#f1ead2"))
    sil = "#141022" if not dusk else "#2c2848"
    c.drawRect(_R(1060, 900, 1100, WY), fill(sil))
    c.drawPath(oval(1080, 880, 330, 150), fill(sil))
    c.drawPath(oval(980, 820, 200, 110), fill(sil))
    for (px_, h_) in ((380, 520), (1700, 460), (2350, 560)):
        p = skia.Path()
        p.moveTo(px_, WY)
        p.quadTo(px_ + 40, WY - h_ / 2, px_ + 20, WY - h_)
        c.drawPath(p, stroke(sil, 16))
        for j in range(7):
            a = math.pi * (0.1 + 0.8 * j / 6)
            tx_, ty_ = px_ + 20 + math.cos(a) * 200, WY - h_ - math.sin(a) * 90 + 60
            p2 = skia.Path()
            p2.moveTo(px_ + 20, WY - h_)
            p2.quadTo((px_ + 20 + tx_) / 2, WY - h_ - 70, tx_, ty_)
            c.drawPath(p2, stroke(sil, 14))
    rng = random.Random(33)
    x = -40
    while x < W:
        w_ = rng.uniform(260, 420)
        h_ = rng.uniform(150, 230)
        _stilt_house(c, x, x + w_, WY - rng.uniform(40, 80), h_, "#1c1828" if not dusk else "#3a3050",
                     rng.random() < 0.45, rng, WY)
        x += w_ + rng.uniform(40, 160)
    vgrad(c, 0, WY, W, H, ["#2a2440", "#120f20"] if not dusk else ["#4a3a6a", "#2a2440"])
    for k in range(30):
        y = WY + 60 + k * 30
        c.drawRect(_R(rng.uniform(0, W), y, rng.uniform(0, W), y + 5), fill("#8a7aa8", 0.15))
    far = sf.makeImageSnapshot()
    s = new_surface()
    c = s.getCanvas()
    # cầu đi bộ trên cao bên phải + đèn natri
    BD = 820
    c.drawRect(_R(2500, BD, W, BD + 60), fill("#2a2236"))
    for x in range(2560, W, 300):
        c.drawRect(_R(x - 22, BD + 60, x + 22, WY + 140), fill("#221c2e"))
    c.drawLine(2500, BD - 70, W, BD - 70, stroke("#2a2236", 10))
    for x in range(2520, W, 70):
        c.drawLine(x, BD, x, BD - 70, stroke("#2a2236", 6))
    lpx = 3150
    c.drawRect(_R(lpx - 10, 420, lpx + 10, BD), fill("#1c1626"))
    c.drawLine(lpx, 430, lpx - 120, 430, stroke("#1c1626", 10))
    c.drawPath(oval(lpx - 130, 445, 46, 16), fill("#ffd48a"))
    glow(c, lpx - 130, 450, 520, "#f0b860", 0.55)
    glow(c, lpx - 130, 450, 140, "#ffe0a0", 0.8)
    c.drawPath(poly([(lpx - 160, 455), (lpx - 100, 455), (lpx + 200, BD), (lpx - 460, BD)]), fill("#f0b860", 0.12))
    for k in range(28):
        y = WY + 50 + k * 32
        hw = 40 + k * 6 + rng.uniform(-20, 20)
        c.drawRect(_R(lpx - 130 - hw, y, lpx - 130 + hw, y + 9), fill("#f0b860", 0.55 - k * 0.018))
    # bến gỗ tiền cảnh
    PT, PB = 1700, 1770
    for x in range(40, 2700, 230):
        c.drawRect(_R(x - 20, PB, x + 20, H), fill("#2a1e18"))
        c.drawRect(_R(x - 60, 1950 + (x % 3) * 20, x + 60, 1958 + (x % 3) * 20), fill("#8a7aa8", 0.25))
    c.drawRect(_R(-20, PT, 2720, PB), fill("#5a4230"))
    for x in range(-20, 2720, 92):
        c.drawLine(x, PT, x, PB, stroke("#3a2a1e", 5))
    c.drawRect(_R(1120, PT, 1205, PB), fill("#1a1410"))
    c.drawRect(_R(-20, PT, 2720, PT + 8), fill("#7a5a40"))
    c.drawRect(_R(-20, PB, 2720, PB + 40), fill("#3a2a1e"))
    c.drawLine(2680, PT, 2720, PB + 40, stroke("#2a1e18", 8))
    for x in (120, 620, 1020, 1520, 2020, 2600):
        c.drawRect(_R(x - 16, PT - 260, x + 16, PT), fill("#4a3626"))
    c.drawLine(120, PT - 230, 1020, PT - 220, stroke("#4a3626", 14))
    sag_wire(c, 1020, PT - 220, 1520, PT - 120, 40, "#4a3626", 12)
    c.drawLine(2020, PT - 230, 2600, PT - 240, stroke("#4a3626", 14))
    for r_ in (60, 44, 28):
        c.drawPath(oval(2300, PT - 20, r_ * 1.6, r_ * 0.5), stroke("#a8946a", 9))
    c.drawPath(rrect(2420, PT - 120, 2540, PT, 14), fill("#5a6a7a"))
    c.drawPath(oval(2480, PT - 120, 60, 14), fill("#3a4a5a"))
    tint(s, "#9a8ac0", 0.35)
    glow(c, lpx - 130, 450, 160, "#ffe0a0", 0.6)
    ellipse_glow(c, 2400, PT, 900, 90, "#f0b860", 0.25)
    mid = s.makeImageSnapshot()
    slots = {"center": {"x": 1350, "y": PT + 30, "scale": 0.95}, "left": {"x": 560, "y": PT + 30, "scale": 0.95},
             "right": {"x": 2150, "y": PT + 30, "scale": 0.95}, "bridge": {"x": 3350, "y": BD + 10, "scale": 0.45}}
    return Scene(far, mid, slots=slots, floor_y=slots["center"]["y"], parallax=(0.85, 1.0, 1.15),
                 lights=[{"x": lpx - 130, "y": 450, "color": "#f0b860"}])


# ------------------------------------------------------------------- 34. tiệm tạp hoá nhỏ + cửa cuốn hai bên
def scene_tiem_tap_hoa_dem(tod: str) -> Scene:
    night = tod != "day"
    s = new_surface()
    c = s.getCanvas()
    vgrad(c, 0, 0, W, 200, ["#0b1022", "#1d2742"] if night else ["#9fb4c8", "#dfe6ea"])
    wall = "#cbbf9e"
    c.drawRect(_R(0, 110, W, 1800), fill(wall))
    c.drawRect(_R(0, 110, W, 150), fill(shade(wall, -0.2)))
    for (wl, lit) in ((300, False), (1500, True), (2900, False)):
        _barred_window(c, wl, 220, wl + 520, 440, "#ffe0a0" if (lit and night) else "#2a2c34", "#f2c46b" if (lit and night) else "#3a3e48",
                       frame=shade(wall, -0.3), bars="#3a342c", n=5)
    # cửa cuốn hai bên
    for (l_, r_) in ((60, 840), (3000, 3780)):
        c.drawRect(_R(l_ - 20, 580, r_ + 20, 680), fill("#5a5e66"))
        c.drawRect(_R(l_, 680, r_, 1800), fill("#7a7e86"))
        for y in range(690, 1800, 28):
            c.drawLine(l_, y, r_, y, stroke("#62666e", 6))
        c.drawRect(_R(l_, 1760, r_, 1800), fill("#4a4e56"))
        c.drawPath(rrect((l_ + r_) / 2 - 60, 1730, (l_ + r_) / 2 + 60, 1760, 8), fill("#3a3e46"))
    # biển hiệu kem (chữ = signs) + mái che lá sách
    c.drawRect(_R(880, 460, 2960, 710), fill("#3a342c"))
    SL, SR = 860, 2980
    for i in range(16):
        x0 = SL + (SR - SL) * i / 16
        x1 = SL + (SR - SL) * (i + 1) / 16
        quad(c, [(x0, 710), (x1, 710), (x1 + (x1 - 1920) * 0.03, 860), (x0 + (x0 - 1920) * 0.03, 860)],
             "#e8dcb8" if i % 2 == 0 else "#8a8a5a")
    # lòng tiệm
    IL, IT, IR, IB = 900, 860, 2940, 1800
    vgrad(c, IL, IT, IR, IB, ["#f3e2b8", "#d9c49a"])
    rng = random.Random(34)
    for (l_, r_) in ((1000, 1560), (1640, 2200)):
        c.drawRect(_R(l_, 940, r_, 1660), fill("#8a6a4a"))
        for j in range(5):
            y = 1000 + j * 135
            c.drawRect(_R(l_ + 10, y + 100, r_ - 10, y + 112), fill("#6b4a32"))
            x = l_ + 18
            while x < r_ - 40:
                wv = rng.uniform(40, 90)
                hv = rng.uniform(50, 96)
                col = rng.choice(PRODUCTS)
                if rng.random() < 0.3:
                    c.drawPath(rrect(x, y + 100 - hv, x + wv * 0.7, y + 100, 10), fill("#e4ecf0", 0.85))
                    c.drawRect(_R(x, y + 100 - hv - 10, x + wv * 0.7, y + 100 - hv + 6), fill(col))
                    c.drawRect(_R(x + 6, y + 100 - hv * 0.6, x + wv * 0.7 - 6, y + 96), fill(col, 0.7))
                else:
                    c.drawRect(_R(x, y + 100 - hv, x + wv, y + 100), fill(col))
                    c.drawRect(_R(x + 6, y + 100 - hv * 0.65, x + wv - 6, y + 100 - hv * 0.35), fill("#ffffff", 0.5))
                x += wv + 6
    for j in range(3):
        sx_ = 2280 + j * 50
        c.drawLine(sx_, 880, sx_, 1300, stroke("#6b6b5a", 3))
        for k in range(6):
            c.drawPath(rrect(sx_ - 18, 900 + k * 66, sx_ + 18, 950 + k * 66, 6), fill(rng.choice(PRODUCTS[:-1])))
    fl, fr = 2520, 2900
    c.drawPath(rrect(fl, 930, fr, 1790, 20), fill("#2a6aa0"))
    vgrad(c, fl + 26, 990, fr - 26, 1720, ["#eaf4fa", "#cde0ea"])
    _bottle_rows(c, fl + 26, 990, fr - 26, 1720, seed=34, rows=5)
    reflections(c, fl + 26, 990, fr - 26, 1720, 2, 0.16, seed=6)
    c.drawRect(_R(fl, 930, fr, 980), fill("#1f5a8a"))
    CL, CR, CT = 960, 1560, 1420
    c.drawRect(_R(CL, CT, CR, 1800), fill("#7a5a3c"))
    c.drawRect(_R(CL - 20, CT - 26, CR + 20, CT), fill("#9a7a52"))
    c.drawRect(_R(CL + 30, CT + 40, CR - 30, 1760), stroke("#5a3e2a", 8))
    c.drawPath(rrect(1080, CT - 210, 1330, CT - 50, 12), fill("#2b2d33"))
    c.drawPath(rrect(1100, CT - 190, 1310, CT - 70, 8), fill("#5a8aa0" if night else "#41505a"))
    c.drawRect(_R(1190, CT - 50, 1220, CT - 26), fill("#2b2d33"))
    for j in range(3):
        c.drawPath(rrect(1400 + j * 52, CT - 110, 1446 + j * 52, CT - 26, 10), fill("#e4ecf0", 0.85))
        c.drawRect(_R(1400 + j * 52, CT - 122, 1446 + j * 52, CT - 104), fill(["#d8423a", "#f3c94e", "#4fa35a"][j]))
    for bx_ in (1250, 1920, 2600):
        c.drawLine(bx_, 860, bx_, 960, stroke("#2a2622", 4))
        c.drawCircle(bx_, 980, 20, fill("#fff3cf"))
    for x in (IL, IR):
        c.drawRect(_R(x - 30, 860, x + 30, 1800), fill(shade(wall, -0.15)))
    # vỉa hè + đường
    c.drawRect(_R(0, 1800, W, 1960), fill("#8a8680"))
    _tile_grid(c, 0, 1800, W, 1960, 160, 80, "#77736e", 4)
    c.drawRect(_R(0, 1960, W, 1990), fill("#a8a49c"))
    c.drawRect(_R(0, 1990, W, H), fill("#3a3c42"))
    if night:
        tint(s, "#5a6890", 0.55)
        c.drawRect(_R(IL, IT, IR, IB), fill("#ffcf7a", 0.12))
        for bx_ in (1250, 1920, 2600):
            glow(c, bx_, 980, 220, "#ffe0a0", 0.6)
        c.drawPath(poly([(IL, 1800), (IR, 1800), (IR + 420, H), (IL - 420, H)]), fill("#ffcf7a", 0.12))
        glow(c, (fl + fr) / 2, 1300, 420, "#cfe8ff", 0.25)
    _vignette(c, 0.45)
    mid = s.makeImageSnapshot()
    slots = {"shopkeeper": {"x": 1260, "y": 1790, "scale": 0.92, "clip_bottom": CT},
             "left": frac_slot({"x": 0.16, "y": 0.94, "scale": 1.05}),
             "center": frac_slot({"x": 0.50, "y": 0.94, "scale": 1.05}),
             "right": frac_slot({"x": 0.84, "y": 0.94, "scale": 1.05})}
    signs = [{"text": "SNACKS & DRINKS", "box": [900, 480, 2940, 690], "style": "white_board"}]
    return Scene(None, mid, slots=slots, signs=signs, floor_y=slots["center"]["y"],
                 lights=[{"x": 1920, "y": 980, "color": "#ffe0a0"}])


# ------------------------------------------------------------------- 35. mặt tiền toà án (ban ngày)
def scene_toa_an(tod: str) -> Scene:
    day = tod != "night"
    sf = new_surface()
    c = sf.getCanvas()
    if day:
        _day_sky(c, 0, 1600, "#6f9ed4", "#d8e8f4")
    else:
        _night_sky(c, 0, 1600, seed=35)
    far = sf.makeImageSnapshot()
    s = new_surface()
    c = s.getCanvas()
    # cây hai bên (sau toà nhà)
    for (tx, ty, r) in ((140, 1400, 360), (420, 1460, 280), (3700, 1400, 360), (3420, 1460, 280)):
        round_tree(c, tx, ty, r, "#5a8a4a" if day else "#1a2a1c", "#4a3a2a", seed=int(tx))
    # thân nhà + hàng cột
    BL, BR, BT, BB = 520, 3320, 760, 1520
    c.drawRect(_R(0, BB - 40, W, H), fill("#9ab07a" if day else "#1e2a22"))       # bãi cỏ sau bậc thềm
    c.drawRect(_R(0, BB - 40, W, BB - 20), fill("#8aa06a" if day else "#18221c"))
    c.drawRect(_R(BL, BT, BR, BB), fill("#d9ccae"))
    n = 12
    cw = 70
    gap = (BR - BL - 120) / (n - 1)
    for i in range(n - 1):
        x0 = BL + 60 + i * gap + cw
        x1 = BL + 60 + (i + 1) * gap - 0
        ax0, ax1 = x0 + (x1 - x0) * 0.22, x1 - (x1 - x0) * 0.22
        ar = (ax1 - ax0) / 2
        p = skia.Path()
        p.moveTo(ax0, BB - 80)
        p.lineTo(ax0, BT + 180 + ar)
        p.arcTo(_R(ax0, BT + 180, ax1, BT + 180 + 2 * ar), 180, 180, False)
        p.lineTo(ax1, BB - 80)
        p.close()
        path_fill(c, p, "#2a3448")
        c.drawLine((ax0 + ax1) / 2, BT + 180, (ax0 + ax1) / 2, BB - 80, stroke("#3e4a62", 6))
    for i in range(n):
        x = BL + 60 + i * gap
        c.drawRect(_R(x, BT + 40, x + cw, BB - 60), lin_paint((x, 0), (x + cw, 0), ["#f8f0dc", "#e8dcc0", "#cfc2a2"], [0, 0.5, 1]))
        c.drawRect(_R(x - 14, BT + 20, x + cw + 14, BT + 50), fill("#efe4c8"))
        c.drawRect(_R(x - 14, BB - 70, x + cw + 14, BB - 50), fill("#efe4c8"))
    c.drawRect(_R(BL - 40, BB - 60, BR + 40, BB), fill("#e2d6b8"))
    # dải chữ navy + diềm + mái ngói cam
    c.drawRect(_R(BL - 60, 660, BR + 60, 780), fill("#efe4c8"))
    c.drawRect(_R(BL - 60, 540, BR + 60, 660), fill("#1e2a4a"))
    c.drawRect(_R(BL - 60, 650, BR + 60, 664), fill("#c99a3c"))
    roof = poly([(BL - 220, 545), (BR + 220, 545), (BR - 200, 330), (BL + 200, 330)])
    path_fill(c, roof, "#d0703a")
    c.save()
    c.clipPath(roof, skia.ClipOp.kIntersect, True)
    for y in range(340, 545, 34):
        c.drawLine(0, y, W, y, stroke("#b45a2a", 6))
    c.restore()
    gable = poly([(1320, 335), (2520, 335), (1920, 90)])
    path_fill(c, gable, "#e07e44")
    c.save()
    c.clipPath(gable, skia.ClipOp.kIntersect, True)
    for y in range(100, 340, 30):
        c.drawLine(0, y, W, y, stroke("#c0622e", 6))
    c.restore()
    path_fill(c, poly([(1500, 320), (2340, 320), (1920, 150)]), "#efe4c8")
    c.drawCircle(1920, 250, 46, fill("#c99a3c"))
    c.drawCircle(1920, 250, 30, fill("#efe4c8"))
    c.drawLine(BL - 220, 545, BR + 220, 545, stroke("#6a3a22", 14))
    c.drawLine(1320, 335, 1920, 90, stroke("#8a4a2a", 12))
    c.drawLine(2520, 335, 1920, 90, stroke("#8a4a2a", 12))
    # bậc thềm rộng
    steps = 7
    for k in range(steps):
        t = BB + k * 48
        inset = 260 - k * 30
        c.drawRect(_R(BL + inset - 200, t, BR - inset + 200, t + 48), fill("#e6dcc4" if k % 2 == 0 else "#d4c8ac"))
        c.drawRect(_R(BL + inset - 200, t + 40, BR - inset + 200, t + 48), fill("#b8ac90"))
    for sd in (-1, 1):
        x = 1920 + sd * 1300
        c.drawRect(_R(x - 70, BB - 20, x + 70, BB + steps * 48), fill("#cfc2a2"))
        c.drawRect(_R(x - 12, BB - 360, x + 12, BB - 20), fill("#2a2d33"))
        c.drawPath(rrect(x - 40, BB - 420, x + 40, BB - 350, 16), fill("#f4efe0" if day else "#ffe0a0"))
        if not day:
            glow(c, x, BB - 385, 260, "#ffcf7a", 0.5)
    PL = BB + steps * 48
    vgrad(c, 0, PL, W, H, ["#c9c0aa", "#a89e88"])
    yy = PL
    stp = 30.0
    while yy < H:
        c.drawLine(0, yy, W, yy, stroke("#a09680", 4))
        yy += stp
        stp *= 1.18
    for i in range(-20, 21):
        c.drawLine(1920 + i * 120, PL, 1920 + i * 300, H, stroke("#a09680", 3))
    for (bx_, by_) in ((260, 1720), (3580, 1720)):
        for j in range(4):
            c.drawCircle(bx_ - 120 + j * 80, by_, 90, fill("#4a7a3a" if day else "#16241a"))
    if not day:
        tint(s, "#56648a", 0.6)
    _vignette(c, 0.3)
    mid = s.makeImageSnapshot()
    slots = {"center": {"x": 1920, "y": 2010, "scale": 0.88}, "left": {"x": 1150, "y": 2010, "scale": 0.88},
             "right": {"x": 2690, "y": 2010, "scale": 0.88}, "top_steps": {"x": 1920, "y": BB + 30, "scale": 0.55}}
    signs = [{"text": "COURT", "box": [1520, 552, 2320, 648], "style": "gold_board"}]
    return Scene(far, mid, slots=slots, signs=signs, floor_y=slots["center"]["y"], parallax=(0.85, 1.0, 1.1))


# ------------------------------------------------------------------- 36. phòng ký túc xá + vali
def scene_phong_ky_tuc_xa(tod: str) -> Scene:
    night = tod == "night"
    s = new_surface()
    c = s.getCanvas()
    _room_shell(c, "#b8ab98", "#a89a86", "#9c8e7a", back_y=1480, pattern=False)
    rng = random.Random(36)
    for _ in range(8):
        x, y = rng.uniform(0, W), rng.uniform(200, 1300)
        c.drawPath(oval(x, y, rng.uniform(80, 240), rng.uniform(60, 200)), fill("#7a6a50", rng.uniform(0.04, 0.08)))
    # cửa gỗ trái
    c.drawRect(_R(160, 400, 740, 1480), fill("#6a5a46"))
    c.drawRect(_R(190, 430, 710, 1480), fill("#8a6a4a"))
    for (pt, pb) in ((500, 900), (980, 1400)):
        c.drawRect(_R(250, pt, 650, pb), stroke(shade("#8a6a4a", -0.25), 8))
    c.drawCircle(660, 1000, 18, fill("#c9ccd2"))
    # giấy ghim
    for (x, y, a) in ((860, 470, -4), (1080, 520, 3), (920, 700, 2), (1160, 760, -3)):
        c.save()
        c.rotate(a, x + 90, y + 110)
        c.drawRect(_R(x, y, x + 180, y + 220), fill("#f4f1e8"))
        for j in range(5):
            c.drawLine(x + 20, y + 40 + j * 32, x + 160 - (j % 2) * 40, y + 40 + j * 32, stroke("#9a9488", 6))
        c.drawRect(_R(x + 60, y - 12, x + 120, y + 14), fill("#e9dfb8", 0.9))
        c.restore()
    # cửa sổ mở, nhà đối diện
    wl, wt, wr, wb = 1500, 360, 2320, 1040
    c.drawRect(_R(wl - 30, wt - 30, wr + 30, wb + 30), fill("#e8e0d0"))
    c.save()
    c.clipRect(_R(wl, wt, wr, wb))
    vgrad(c, wl, wt, wr, wb, ["#0d1426", "#1d2742"] if night else ["#c9dce8", "#eef2f4"])
    c.drawRect(_R(wl + 120, wt + 80, wr + 40, wb), fill("#c9b8a0" if not night else "#2a2c3a"))
    for i in range(3):
        for j in range(3):
            x = wl + 180 + i * 230
            y = wt + 140 + j * 220
            lit = night and (i + j) % 2 == 0
            c.drawRect(_R(x, y, x + 140, y + 150), fill("#ffe0a0" if lit else "#5a6470"))
            c.drawRect(_R(x - 10, y + 150, x + 150, y + 166), fill("#e8dcc8" if not night else "#3a3c4a"))
    c.drawRect(_R(wl + 140, wt + 500, wl + 300, wt + 600), fill("#e4e8ea"))
    c.restore()
    quad(c, [(wr, wt), (wr + 160, wt + 60), (wr + 160, wb + 40), (wr, wb)], "#bcd2e0", 0.6)
    c.drawPath(poly([(wr, wt), (wr + 160, wt + 60), (wr + 160, wb + 40), (wr, wb)]), stroke("#e8e0d0", 16))
    c.drawLine((wl + wr) / 2, wt, (wl + wr) / 2, wb, stroke("#e8e0d0", 14))
    c.drawRect(_R(wl - 60, wb + 30, wr + 60, wb + 60), fill("#d4cab8"))
    if not night:
        c.drawPath(poly([(wl, wb), (wr, wb), (wr + 700, 2000), (wl + 300, 2000)]), fill("#fff6dc", 0.12))
    # bóng đèn treo
    c.drawLine(1920, 0, 1920, 260, stroke("#2a2622", 4))
    c.drawRect(_R(1900, 250, 1940, 280), fill("#3a3a40"))
    c.drawPath(oval(1920, 310, 28, 36), fill("#fff3cf" if night else "#f4efe0"))
    # bàn gấp + quạt đứng
    TL, TR, TT = 2560, 3160, 1220
    c.drawLine(TL + 40, 1640, TR - 40, TT + 30, stroke("#5a5e66", 14))
    c.drawLine(TR - 40, 1640, TL + 40, TT + 30, stroke("#5a5e66", 14))
    c.drawRect(_R(TL, TT, TR, TT + 34), fill("#d9d4c4"))
    c.drawRect(_R(TL, TT + 34, TR, TT + 46), fill("#a9a494"))
    c.drawPath(rrect(2620, TT - 160, 2760, TT, 30), fill("#c9ccd2"))
    c.drawPath(capsule(2760, TT - 120, 2810, TT - 80, 14, 10), fill("#c9ccd2"))
    c.drawPath(rrect(2860, TT - 90, 2930, TT, 12), fill("#e8833a"))
    for j in range(3):
        c.drawRect(_R(2970 + j * 6, TT - 14 - j * 10, 3130 - j * 6, TT - 4 - j * 10), fill("#f4f1e8"))
    fx_, fb = 3450, 1700
    c.drawPath(oval(fx_, fb, 130, 24), fill("#2b2d33"))
    c.drawRect(_R(fx_ - 10, 1150, fx_ + 10, fb), fill("#c9ccd2"))
    c.drawCircle(fx_, 1050, 150, stroke("#c9ccd2", 10))
    for k in range(3):
        a = k / 3 * math.tau + 0.3
        c.drawPath(oval(fx_ + math.cos(a) * 70, 1050 + math.sin(a) * 70, 62, 36), fill("#7ab0d8", 0.85))
    c.drawCircle(fx_, 1050, 26, fill("#3a78c2"))
    # thùng giấy + nệm + vali
    for (l_, t_, r_, b_) in ((2280, 1480, 2620, 1760), (2320, 1240, 2580, 1480)):
        c.drawRect(_R(l_, t_, r_, b_), fill("#b8864a"))
        c.drawRect(_R(l_, t_, r_, t_ + 16), fill("#c99a5a"))
        c.drawRect(_R((l_ + r_) / 2 - 30, t_, (l_ + r_) / 2 + 30, b_), fill("#d9b87a"))
    c.drawPath(rrect(80, 1780, 1060, 1920, 30), fill("#e4dccc"))
    c.drawPath(rrect(80, 1760, 1060, 1790, 14), fill("#f0ebe0"))
    c.drawPath(rrect(120, 1700, 380, 1780, 30), fill("#f4f4f0"))
    c.drawPath(rrect(500, 1730, 1060, 1860, 40), fill("#c87a8a"))
    _suitcase(c, 1340, 1830, 280, 420, "#e88aa8")
    _suitcase(c, 1660, 1850, 300, 470, "#5a96d8")
    _suitcase(c, 1950, 1800, 230, 330, "#f3c94e", tag="#4fa35a", handle=False)
    if night:
        tint(s, "#4a5480", 0.6)
        glow(c, 1920, 320, 700, "#fff1c8", 0.4)
    else:
        glow(c, 1920, 700, 1600, "#fff6dc", 0.15)
    _vignette(c, 0.4)
    mid = s.makeImageSnapshot()
    slots = {"center": frac_slot({"x": 0.52, "y": 0.94, "scale": 1.05}),
             "left": frac_slot({"x": 0.26, "y": 0.94, "scale": 1.05}),
             "right": frac_slot({"x": 0.76, "y": 0.94, "scale": 1.05}),
             "door": frac_slot({"x": 0.12, "y": 0.80, "scale": 0.9}),
             "window": frac_slot({"x": 0.50, "y": 0.86, "scale": 0.95})}
    return Scene(None, mid, slots=slots, floor_y=slots["center"]["y"],
                 lights=[{"x": 1920, "y": 310, "color": "#fff1c8"}])


# =================================================================== LÔ 3 (docs/reference_batch3_analysis.md)
# 10 loại cảnh mới (bối cảnh truyện ma học đường / phố dân cư đêm), vẽ GỐC bằng code. Không cắt/đồ lại khung tham
# khảo; không tên trường/tiệm thật, không logo. Chữ nướng vào pixel (số buồng, nhãn máy bán hàng, thực đơn, số
# phòng, biển địa chỉ) là TIẾNG ANH / chữ số; chữ biển lớn ("GIRLS 3F", tên trường) là lớp `signs`.
def _moon(c, x, y, r, col="#f1ead2", a=1.0) -> None:
    glow(c, x, y, r * 7, col, 0.3 * a)
    glow(c, x, y, r * 2.2, col, 0.45 * a)
    c.drawCircle(x, y, r, fill(col, a))
    for (dx, dy, rr) in ((-0.32, -0.18, 0.2), (0.28, 0.3, 0.14), (0.1, -0.42, 0.09)):
        c.drawCircle(x + dx * r, y + dy * r, rr * r, fill(shade(col, -0.08), a))


def _light_cone(c, x, y, w0, fx, fy, w1, col, a=0.14) -> None:
    """Nón sáng hình thang mờ dần về đáy."""
    p = lin_paint((x, y), (x, fy), [(col, a), (col, a * 0.25)])
    c.drawPath(poly([(x - w0, y), (x + w0, y), (fx + w1, fy), (fx - w1, fy)]), p)


def _streetlamp(c, x, base, h, k, lit=True, arm=1, col="#2a2d36", light="#ffe2a0", cone=True, pool_y=None,
                pole=True) -> tuple:
    """Cột đèn đường cần cong. k = px/mét, h = chiều cao (m). pole=False: chỉ cần + đầu đèn (gắn cột điện).
    Trả về (x, y) đầu đèn."""
    top = base - h * k
    if pole:
        c.drawRect(_R(x - 0.075 * k, top, x + 0.075 * k, base), fill(col))
        c.drawRect(_R(x - 0.13 * k, base - 0.35 * k, x + 0.13 * k, base), fill(shade(col, 0.08)))
    else:
        c.drawRect(_R(x - 0.1 * k, top + 0.15 * k, x + 0.1 * k, top + 0.4 * k), fill(col))
    hx = x + arm * 0.95 * k
    p = skia.Path()
    p.moveTo(x, top + 0.25 * k)
    p.quadTo(x, top - 0.12 * k, x + arm * 0.5 * k, top - 0.1 * k)
    p.lineTo(hx, top - 0.06 * k)
    c.drawPath(p, stroke(col, max(3.0, 0.06 * k)))
    c.drawPath(rrect(hx - 0.3 * k, top - 0.12 * k, hx + 0.3 * k, top + 0.03 * k, 0.06 * k), fill(col))
    c.drawPath(oval(hx, top + 0.04 * k, 0.24 * k, 0.05 * k), fill(light if lit else "#8a8a80"))
    if lit:
        fy = pool_y if pool_y is not None else base
        if cone:
            _light_cone(c, hx, top + 0.05 * k, 0.24 * k, hx, fy, 1.7 * k, light, 0.13)
        ellipse_glow(c, hx, fy, 1.9 * k, 0.32 * k, light, 0.45)
        glow(c, hx, top + 0.05 * k, 1.3 * k, light, 0.55)
    return hx, top


def _guard_stripes(c, l, t, r, b, k) -> None:
    """Ống bảo vệ sọc vàng-đen (chân cột điện)."""
    c.save()
    c.clipRect(_R(l, t, r, b))
    c.drawRect(_R(l, t, r, b), fill("#e8c23a"))
    step = 0.22 * k
    y = t - (r - l)
    while y < b + (r - l):
        c.drawPath(poly([(l, y), (r, y - (r - l) * 0.6), (r, y - (r - l) * 0.6 + step * 0.5), (l, y + step * 0.5)]),
                   fill("#1d1d22"))
        y += step
    c.restore()


def _util_pole(c, x, base, h, k, plate: str | None, baked: list, col="#8e8a84", trans=False) -> float:
    """Cột điện bê tông: xà ngang, sứ cách điện, ống sọc vàng-đen, biển địa chỉ xanh (chữ số)."""
    top = base - h * k
    w = 0.15 * k
    quad(c, [(x - w * 0.75, top), (x + w * 0.75, top), (x + w, base), (x - w, base)], col)
    quad(c, [(x - w * 0.75, top), (x - w * 0.35, top), (x - w * 0.5, base), (x - w, base)], shade(col, 0.1))
    for (dy, half) in ((0.45, 0.85), (1.0, 0.65)):
        y = top + dy * k
        c.drawRect(_R(x - half * k, y, x + half * k, y + 0.07 * k), fill(shade(col, -0.3)))
        for sx in (-half + 0.08, -half * 0.4, half * 0.4, half - 0.08):
            c.drawPath(rrect(x + sx * k - 0.03 * k, y - 0.11 * k, x + sx * k + 0.03 * k, y, 0.02 * k), fill("#d9d6cc"))
    if trans:
        c.drawPath(rrect(x + w, top + 1.4 * k, x + w + 0.42 * k, top + 2.2 * k, 0.08 * k), fill(shade(col, -0.15)))
        c.drawRect(_R(x + w, top + 1.5 * k, x + w + 0.42 * k, top + 1.56 * k), fill(shade(col, -0.35)))
    _guard_stripes(c, x - w * 1.25, base - 1.9 * k, x + w * 1.25, base - 0.15 * k, k)
    if plate:
        py = base - 2.55 * k
        c.drawPath(rrect(x - w * 1.1, py - 0.26 * k, x + w * 1.1, py + 0.26 * k, 0.03 * k), fill("#2f5fa0"))
        c.drawPath(rrect(x - w * 1.1, py - 0.26 * k, x + w * 1.1, py + 0.26 * k, 0.03 * k), stroke("#e8eef4", max(2.0, 0.015 * k)))
        size = 0.15 * k
        text_center(c, plate, x, py, size, "#f4f6f8", "extrabold", max_w=w * 1.9)
        baked.append(_baked(plate, x, py, size))
    return top


def _vending(c, l, base, w, h, body, night: bool, seed: int, baked: list, rows=("COLD", "COLD", "HOT")) -> None:
    """Máy bán nước nhìn thẳng: tủ kính 3 hàng lon chung chung + dải nhãn COLD/HOT, khe xu, màn số 000."""
    rng = random.Random(seed)
    r, t = l + w, base - h
    c.drawPath(oval(l + w / 2, base, w * 0.6, w * 0.05), fill("#000000", 0.35))
    c.drawPath(rrect(l, t, r, base, w * 0.03), fill(body))
    c.drawRect(_R(r - w * 0.05, t + w * 0.03, r, base), fill(shade(body, -0.2)))
    c.drawRect(_R(l, t, r, t + h * 0.035), fill(shade(body, 0.15)))
    wl, wt, wr, wb = l + w * 0.07, t + h * 0.06, r - w * 0.1, t + h * 0.55
    c.drawRect(_R(wl, wt, wr, wb), fill("#eef4f8" if night else "#dfe7ec"))
    rh = (wb - wt) / len(rows)
    can_cols = ["#d8423a", "#3a78c2", "#f3c94e", "#4fa35a", "#f08a2c", "#7a5aa0", "#e8e4dc", "#2b2d33"]
    n = 6
    cw = (wr - wl) / n
    for i, lab in enumerate(rows):
        y0 = wt + i * rh
        y1 = y0 + rh * 0.72
        for j in range(n):
            cx = wl + cw * (j + 0.5)
            col = rng.choice(can_cols)
            ch = (y1 - y0) * rng.uniform(0.62, 0.8)
            c.drawPath(rrect(cx - cw * 0.26, y1 - ch, cx + cw * 0.26, y1, cw * 0.08), fill(col))
            c.drawRect(_R(cx - cw * 0.26, y1 - ch * 0.62, cx + cw * 0.26, y1 - ch * 0.36), fill(shade(col, 0.45)))
            c.drawRect(_R(cx - cw * 0.2, y1 - ch - cw * 0.05, cx + cw * 0.2, y1 - ch + cw * 0.03), fill("#c9ccd2"))
        sc = "#2f6fd0" if lab == "COLD" else "#d8352e"
        c.drawRect(_R(wl, y1 + rh * 0.04, wr, y0 + rh * 0.98), fill(sc))
        size = rh * 0.16
        for j in range(n):
            cx = wl + cw * (j + 0.5)
            text_center(c, lab, cx, y1 + rh * 0.15, size, "#ffffff", "extrabold", max_w=cw * 0.86)
        baked.append(_baked(lab, wl + cw * 0.5, y1 + rh * 0.15, size))
    reflections(c, wl, wt, wr, wb, 3, 0.14, seed=seed)
    c.drawRect(_R(wl, wt, wr, wb), stroke(shade(body, -0.35), max(3.0, w * 0.012)))
    # bảng điều khiển
    pl = r - w * 0.3
    c.drawPath(rrect(pl, wb + h * 0.04, r - w * 0.1, wb + h * 0.2, w * 0.015), fill(shade(body, -0.25)))
    c.drawPath(rrect(pl + w * 0.03, wb + h * 0.055, r - w * 0.13, wb + h * 0.095, w * 0.01), fill("#101214"))
    size = h * 0.03
    text_center(c, "000", pl + (r - w * 0.1 - pl) / 2, wb + h * 0.075, size, "#ff5a3a", "extrabold")
    baked.append(_baked("000", pl + (r - w * 0.1 - pl) / 2, wb + h * 0.075, size))
    c.drawPath(rrect(pl + w * 0.07, wb + h * 0.12, pl + w * 0.1, wb + h * 0.17, w * 0.008), fill("#1a1a1e"))
    c.drawCircle(pl + w * 0.16, wb + h * 0.145, w * 0.02, fill("#c9ccd2"))
    c.drawPath(rrect(l + w * 0.1, wb + h * 0.06, pl - w * 0.06, wb + h * 0.24, w * 0.02), fill(shade(body, 0.12)))
    for j in range(3):
        c.drawCircle(l + w * 0.2 + j * w * 0.12, wb + h * 0.15, w * 0.035, fill(shade(body, 0.3)))
    # khe lấy hàng
    c.drawPath(rrect(l + w * 0.14, base - h * 0.2, r - w * 0.2, base - h * 0.08, w * 0.02), fill("#141518"))
    c.drawRect(_R(l + w * 0.14, base - h * 0.2, r - w * 0.2, base - h * 0.17), fill(shade(body, -0.35)))
    c.drawRect(_R(l + w * 0.05, base - h * 0.05, r - w * 0.05, base), fill(shade(body, -0.4)))
    if night:
        glow(c, (wl + wr) / 2, (wt + wb) / 2, w * 1.1, "#e8f4ff", 0.45)


def _block_wall(c, l, t, r, b, col, bw=150.0, bh=75.0) -> None:
    c.drawRect(_R(l, t, r, b), fill(col))
    y = t + bh * 0.4
    row = 0
    while y < b:
        c.drawLine(l, y, r, y, stroke(shade(col, -0.16), 4))
        x = l + (bw / 2 if row % 2 else 0)
        while x < r:
            c.drawLine(x, y, x, min(b, y + bh), stroke(shade(col, -0.16), 4))
            x += bw
        y += bh
        row += 1
    c.drawRect(_R(l - 10, t - 26, r + 10, t + 4), fill(shade(col, 0.12)))
    c.drawRect(_R(l - 10, t + 4, r + 10, t + 14), fill(shade(col, -0.25)))


def _curved_mirror(c, x, base, k, col="#e8742a") -> None:
    """Gương cầu lồi giao thông: cột cam + gương tròn viền cam."""
    top = base - 2.9 * k
    c.drawRect(_R(x - 0.045 * k, top, x + 0.045 * k, base), fill(col))
    c.drawRect(_R(x - 0.045 * k, top, x - 0.015 * k, base), fill(shade(col, 0.15)))
    my = top - 0.1 * k
    r = 0.42 * k
    c.drawCircle(x, my, r * 1.12, fill(col))
    c.drawCircle(x, my, r, rad_paint(x - r * 0.3, my - r * 0.3, r * 1.4, ["#dfe8f0", "#7f8ea0", "#3a4250"]))
    c.save()
    c.clipPath(circle(x, my, r))
    c.drawPath(oval(x, my + r * 0.5, r * 1.1, r * 0.35), fill("#4a4c58", 0.6))
    quad(c, [(x - r, my - r * 0.2), (x - r * 0.6, my - r), (x - r * 0.4, my - r), (x - r, my + 0.05 * r)], "#ffffff", 0.3)
    c.restore()
    c.drawRect(_R(x - 0.06 * k, my + r * 1.05, x + 0.06 * k, my + r * 1.35), fill(shade(col, -0.2)))


def _shrine_gate(c, x, base, k, col="#c8452e", baked: list | None = None) -> None:
    """Cổng đền nhỏ kiểu chung (2 cột, 2 xà, mái cong) + bảng 'SHRINE'."""
    hh, half = 2.7, 1.15
    for sg in (-1, 1):
        quad(c, [(x + sg * half * k - 0.08 * k, base - hh * k), (x + sg * half * k + 0.08 * k, base - hh * k),
                 (x + sg * (half + 0.05) * k + 0.1 * k, base), (x + sg * (half + 0.05) * k - 0.1 * k, base)], col)
        c.drawRect(_R(x + sg * (half + 0.05) * k - 0.13 * k, base - 0.25 * k, x + sg * (half + 0.05) * k + 0.13 * k, base),
                   fill("#2a2422"))
    ny = base - hh * k + 0.42 * k
    c.drawRect(_R(x - (half + 0.3) * k, ny, x + (half + 0.3) * k, ny + 0.16 * k), fill(col))
    ty = base - hh * k
    p = skia.Path()
    p.moveTo(x - (half + 0.6) * k, ty - 0.38 * k)
    p.quadTo(x, ty - 0.05 * k, x + (half + 0.6) * k, ty - 0.38 * k)
    p.lineTo(x + (half + 0.5) * k, ty - 0.12 * k)
    p.quadTo(x, ty + 0.15 * k, x - (half + 0.5) * k, ty - 0.12 * k)
    p.close()
    path_fill(c, p, "#2a2422")
    c.drawRect(_R(x - (half + 0.35) * k, ty - 0.05 * k, x + (half + 0.35) * k, ty + 0.12 * k), fill(col))
    c.drawRect(_R(x - 0.06 * k, ty + 0.12 * k, x + 0.06 * k, ny), fill(col))
    pw, ph = 0.5 * k, 0.26 * k
    py = (ty + 0.12 * k + ny) / 2
    c.drawPath(rrect(x - pw / 2, py - ph / 2, x + pw / 2, py + ph / 2, 0.03 * k), fill("#2a2422"))
    c.drawPath(rrect(x - pw / 2 + 0.03 * k, py - ph / 2 + 0.03 * k, x + pw / 2 - 0.03 * k, py + ph / 2 - 0.03 * k, 0.02 * k),
               stroke("#d9a441", max(2.0, 0.015 * k)))
    if baked is not None:
        size = ph * 0.4
        text_center(c, "SHRINE", x, py, size, "#f0d890", "extrabold", max_w=pw * 0.8)
        baked.append(_baked("SHRINE", x, py, size))


def _bicycle(c, x, base, k, col="#3a6ab0", basket=True, facing=1) -> None:
    """Xe đạp mini nhìn ngang. x = tâm, base = mặt đất."""
    r = 0.3 * k
    w = max(2.0, 0.035 * k)
    rx, fx = x - facing * 0.5 * k, x + facing * 0.5 * k
    for wx in (rx, fx):
        c.drawCircle(wx, base - r, r, stroke("#1d1f24", w * 1.8))
        c.drawCircle(wx, base - r, r * 0.12, fill("#8a9098"))
        for a in range(6):
            ang = a * math.pi / 6
            c.drawLine(wx - math.cos(ang) * r, base - r - math.sin(ang) * r, wx + math.cos(ang) * r,
                       base - r + math.sin(ang) * r, stroke("#8a9098", max(1.0, w * 0.3)))
    bx, by = x - facing * 0.05 * k, base - r
    sx, sy = x - facing * 0.18 * k, base - 0.85 * k
    hx, hy = fx - facing * 0.12 * k, base - 0.95 * k
    for (a, b) in (((rx, base - r), (bx, by)), ((bx, by), (sx, sy)), ((rx, base - r), (sx + facing * 0.03 * k, sy + 0.08 * k)),
                   ((bx, by), (hx - facing * 0.04 * k, hy + 0.25 * k)), ((sx, sy + 0.12 * k), (hx - facing * 0.04 * k, hy + 0.25 * k)),
                   ((fx, base - r), (hx, hy))):
        c.drawLine(*a, *b, stroke(col, w * 1.6))
    c.drawPath(rrect(sx - 0.13 * k, sy - 0.06 * k, sx + 0.1 * k, sy + 0.02 * k, 0.03 * k), fill("#1d1f24"))
    c.drawLine(hx - facing * 0.12 * k, hy - 0.02 * k, hx + facing * 0.05 * k, hy, stroke("#1d1f24", w * 1.6))
    c.drawCircle(bx, by, 0.07 * k, stroke("#5a5e66", w))
    if basket:
        bl, br = (hx + facing * 0.02 * k, hx + facing * 0.36 * k)
        c.drawPath(rrect(min(bl, br), hy - 0.02 * k, max(bl, br), hy + 0.24 * k, 0.03 * k), stroke("#9aa0a8", w))
        for i in range(1, 4):
            xx = min(bl, br) + abs(br - bl) * i / 4
            c.drawLine(xx, hy - 0.02 * k, xx, hy + 0.24 * k, stroke("#9aa0a8", max(1.0, w * 0.5)))
    c.drawPath(oval(x, base + 0.02 * k, 0.9 * k, 0.05 * k), fill("#000000", 0.25))


def _num_plate(c, cx, cy, text, size, baked, bg="#f4f1e8", fg="#2b2d36", pad=0.45) -> None:
    f = font(size, "extrabold")
    tw = f.measureText(text)
    c.drawPath(rrect(cx - tw / 2 - size * pad, cy - size * 0.72, cx + tw / 2 + size * pad, cy + size * 0.72, size * 0.18),
               fill(bg))
    text_center(c, text, cx, cy, size, fg, "extrabold")
    baked.append(_baked(text, cx, cy, size))


def _dust(c, l, t, r, b, n, seed, col="#f4f0e0") -> None:
    rng = random.Random(seed)
    for _ in range(n):
        c.drawCircle(rng.uniform(l, r), rng.uniform(t, b), rng.choice([2.0, 3.0, 4.0, 5.5]), fill(col, rng.uniform(0.15, 0.5)))


def _puddle(c, x, y, rx, ry, col="#8fa8c0", a=0.45) -> None:
    c.drawPath(oval(x, y, rx, ry), fill(shade(col, -0.35), a * 0.6))
    c.drawPath(oval(x - rx * 0.1, y - ry * 0.1, rx * 0.85, ry * 0.7), fill(col, a))
    c.drawLine(x - rx * 0.5, y - ry * 0.2, x + rx * 0.1, y - ry * 0.35, stroke("#ffffff", max(2.0, ry * 0.12), a * 0.6))


# ------------------------------------------------------------------- 37. nhà vệ sinh nữ trường học (+ cận cửa buồng)
def _stall_door(c, l, t, r, b, col, num, occupied, baked, k=1.0) -> None:
    c.drawRect(_R(l, t, r, b), fill(col))
    c.drawRect(_R(l, t, r, t + 14 * k), fill(shade(col, 0.15)))
    c.drawRect(_R(r - 16 * k, t, r, b), fill(shade(col, -0.16)))
    c.drawRect(_R(l, b - 10 * k, r, b), fill(shade(col, -0.25)))
    for hy in (t + (b - t) * 0.12, b - (b - t) * 0.12):
        c.drawPath(rrect(l - 6 * k, hy - 34 * k, l + 22 * k, hy + 34 * k, 6 * k), fill("#b9bdc4"))
    cx = (l + r) / 2
    _num_plate(c, cx, t + (b - t) * 0.13, num, 92 * k, baked, bg="#f4f1e8", fg="#3a3d48", pad=0.6)
    # khoá + chỉ báo (xanh = trống, đỏ = có người) — chỉ màu, không chữ
    ix, iy = r - 110 * k, t + (b - t) * 0.5
    c.drawPath(rrect(ix - 46 * k, iy - 30 * k, ix + 46 * k, iy + 30 * k, 10 * k), fill("#c9ccd2"))
    c.drawPath(rrect(ix - 34 * k, iy - 18 * k, ix + 34 * k, iy + 18 * k, 18 * k), fill("#d8352e" if occupied else "#2f6fd0"))
    if occupied:
        glow(c, ix, iy, 120 * k, "#ff4a3a", 0.35)
    c.drawPath(rrect(ix - 30 * k, iy + 60 * k, ix + 30 * k, iy + 150 * k, 12 * k), fill("#b9bdc4"))
    c.drawPath(capsule(ix, iy + 105 * k, ix - 70 * k, iy + 105 * k, 22 * k, 18 * k), fill("#d9dce2"))


def scene_nha_ve_sinh_nu_truong(tod: str) -> Scene:
    close = tod == "closeup"
    baked: list = []
    s = new_surface()
    c = s.getCanvas()
    tile, tline = "#bcd3cf", "#9fb8b4"
    door, frame = "#d29a98", "#b07a7a"
    if not close:
        FB = 1760
        c.drawRect(_R(0, 0, W, FB), fill(tile))
        _tile_grid(c, 0, 230, W, FB, 110, 110, tline, 4)
        vgrad(c, 0, 0, W, 230, ["#6e7c7a", "#8fa09c"])
        c.drawRect(_R(0, 220, W, 240), fill("#7f908c"))
        rng = random.Random(37)
        for _ in range(9):
            c.drawPath(oval(rng.uniform(0, W), rng.uniform(300, 1500), rng.uniform(60, 200), rng.uniform(80, 260)),
                       fill("#4a5650", rng.uniform(0.04, 0.09)))
        # ô cửa sổ nhỏ trên cao (ánh trăng)
        wl, wt, wr, wb = 1120, 290, 1440, 520
        c.drawRect(_R(wl - 24, wt - 24, wr + 24, wb + 24), fill("#e8ecea"))
        vgrad(c, wl, wt, wr, wb, ["#9fb4d8", "#dfe8f4"])
        c.drawLine((wl + wr) / 2, wt, (wl + wr) / 2, wb, stroke("#e8ecea", 14))
        for i in range(1, 6):
            c.drawLine(wl, wt + i * 38, wr, wt + i * 38, stroke("#ffffff", 3, 0.25))
        # gương + 2 bồn rửa
        ml, mt, mr, mb = 180, 560, 1080, 1060
        c.drawPath(rrect(ml - 20, mt - 20, mr + 20, mb + 20, 16), fill("#9aa4a8"))
        vgrad(c, ml, mt, mr, mb, ["#7f96a8", "#a9bccb"])
        reflections(c, ml, mt, mr, mb, 3, 0.2, seed=37)
        c.drawRect(_R(120, 1150, 1140, 1200), fill("#e8ecec"))
        c.drawRect(_R(120, 1200, 1140, 1240), fill("#b9c2c4"))
        for bx in (400, 860):
            p = skia.Path()
            p.addArc(_R(bx - 190, 1060, bx + 190, 1360), 0, 180)
            path_fill(c, p, "#f2f4f4")
            c.drawPath(oval(bx, 1170, 170, 26), fill("#c9d3d6"))
            c.drawRect(_R(bx - 14, 1040, bx + 14, 1150), fill("#c9ccd2"))
            c.drawPath(capsule(bx, 1050, bx + 70, 1060, 22, 16), fill("#c9ccd2"))
            c.drawPath(rrect(bx - 50, 1100, bx - 20, 1150, 8), fill("#dfe2e6"))
            c.drawRect(_R(bx - 20, 1340, bx + 20, FB), fill("#b9bdc4"))
        c.drawPath(rrect(1150, 1250, 1300, 1460, 18), fill("#e8eaee"))      # hộp xà phòng/giấy
        # 3 buồng
        SL, SR, ST, SB = 1600, 3780, 540, 1690
        n = 3
        sw = (SR - SL) / n
        c.drawRect(_R(SL, ST - 30, SR, ST), fill(shade(frame, 0.12)))
        for i in range(n):
            l = SL + i * sw
            c.drawRect(_R(l, ST, l + 46, SB + 60), fill(frame))
            _stall_door(c, l + 46, ST + 20, l + sw - 4, SB, door, str(i + 1), i == 2, baked)
            c.drawRect(_R(l + 46, SB, l + sw - 4, SB + 70), fill("#1a1e22"))
        c.drawRect(_R(SR - 4, ST, SR + 40, SB + 60), fill(frame))
        # sàn ướt + vũng nước
        _persp_floor(c, FB, "#8fa09e", "#76878a", vx=1920, vy=900, spacing=300, dz=0.12)
        ellipse_glow(c, 2700, 1790, 1100, 60, "#000000", 0.0)
        for (px, py, rx, ry) in ((2350, 1880, 330, 46), (3000, 2030, 420, 60), (1500, 1980, 260, 38), (3400, 1820, 210, 28)):
            _puddle(c, px, py, rx, ry, "#b9d0dc", 0.5)
        # vệt sáng chéo từ cửa sổ
        c.drawPath(poly([(wl, wt), (wr, wt), (wr - 260, H), (wl - 980, H)]), lin_paint((wl, wt), (wl - 400, H),
                   [("#e8f0ff", 0.22), ("#e8f0ff", 0.04)]))
        _dust(c, 300, 500, 1500, 1900, 70, 37)
        _tube(c, 2650, 120, 760, on=True, col="#e4f4f0")
        _tube(c, 900, 120, 600, on=False)
        tint(s, "#5a6a90", 0.55)
        glow(c, 2650, 150, 900, "#e4f4f0", 0.22)
        glow(c, (wl + wr) / 2, (wt + wb) / 2, 500, "#dfe8ff", 0.35)
        ix, iy = SL + 2 * sw + sw - 4 - 110, ST + 20 + (SB - ST - 20) * 0.5
        glow(c, ix, iy, 140, "#ff4a3a", 0.5)
        _vignette(c, 0.5)
        mid = s.makeImageSnapshot()
        slots = {"center": {"x": 1920, "y": 2010, "scale": 1.1}, "left": {"x": 800, "y": 2010, "scale": 1.1},
                 "right": {"x": 3050, "y": 2010, "scale": 1.1}, "sink": {"x": 640, "y": 1900, "scale": 1.0},
                 "stall_3": {"x": SL + 2.5 * sw, "y": 1960, "scale": 1.05}}
        slots["stall_3"]["x"] = round(slots["stall_3"]["x"])
        signs = [{"text": "GIRLS 3F", "box": [240, 270, 860, 430], "style": "white_board"}]
        return Scene(None, mid, slots=slots, signs=signs, baked_signs=baked, floor_y=2010,
                     lights=[{"x": 2650, "y": 140, "color": "#e4f4f0"}, {"x": 1280, "y": 400, "color": "#dfe8ff"}])
    # --- cận cửa buồng số 3
    k = 2.0
    c.drawRect(_R(0, 0, W, H), fill(tile))
    _tile_grid(c, 0, 0, W, H, 220, 220, tline, 6)
    DL, DR, DT, DB = 1080, 2760, 140, 1930
    c.drawRect(_R(DL - 140, 0, DL, H), fill(frame))
    c.drawRect(_R(DR, 0, DR + 140, H), fill(frame))
    c.drawRect(_R(DL - 140, 0, DL - 110, H), fill(shade(frame, 0.12)))
    c.drawRect(_R(0, 0, DL - 140, H), fill(door))
    c.drawRect(_R(DR + 140, 0, W, H), fill(door))
    c.drawRect(_R(DL - 180, 0, DL - 140, H), fill(shade(door, -0.18)))
    _stall_door(c, DL, DT, DR, DB, door, "3", True, baked, k=k)
    c.drawRect(_R(DL - 140, DB - 20, DR + 140, DB + 70), fill(shade(frame, -0.2)))
    _persp_floor(c, DB + 70, "#8fa09e", "#76878a", vx=1920, vy=700, spacing=520, dz=0.2, w=6)
    c.drawRect(_R(DL, DB, DR, DB + 70), fill("#0c0f13"))
    for x0 in (DL - 140, DR):
        c.drawRect(_R(x0, DB, x0 + 140, DB + 70), fill(frame))
    vgrad(c, 0, DB + 70, W, DB + 160, [("#000000", 0.45), ("#000000", 0.0)])
    # nước rỉ ra từ khe dưới cửa
    _puddle(c, 1900, 2070, 900, 62, "#b9d0dc", 0.55)
    _puddle(c, 1250, 2125, 320, 26, "#b9d0dc", 0.45)
    ellipse_glow(c, 1900, DB + 70, 700, 40, "#c9d8e8", 0.25)
    for x in (1300, 1700, 2250, 2500):
        c.drawPath(capsule(x, DB + 66, x + 6, DB + 120, 10, 6), fill("#b9d0dc", 0.6))
    c.drawPath(poly([(0, 0), (1400, 0), (600, H), (0, H)]), lin_paint((0, 0), (900, H), [("#e8f0ff", 0.12), ("#e8f0ff", 0.0)]))
    tint(s, "#5a6a90", 0.55)
    ix, iy = DR - 110 * k, DT + (DB - DT) * 0.5
    glow(c, ix, iy, 300, "#ff4a3a", 0.5)
    _vignette(c, 0.6, r=W * 0.55)
    mid = s.makeImageSnapshot()
    slots = {"center": {"x": 1920, "y": 2150, "scale": 1.9}, "left": {"x": 700, "y": 2150, "scale": 1.9},
             "right": {"x": 3150, "y": 2150, "scale": 1.9}}
    return Scene(None, mid, slots=slots, baked_signs=baked, floor_y=2150, lights=[{"x": round(ix), "y": round(iy), "color": "#ff4a3a"}])

# ------------------------------------------------------------------- 38. lớp học cũ ban đêm (+ góc bên có tủ)
def _wall_clock_face(c, x, y, r, hh=2, mm=40) -> None:
    c.drawCircle(x, y, r * 1.1, fill("#5a4a3a"))
    c.drawCircle(x, y, r, fill("#f2efe6"))
    for i in range(12):
        a = i / 12 * math.tau
        r0 = r * (0.78 if i % 3 == 0 else 0.86)
        c.drawLine(x + math.cos(a) * r0, y + math.sin(a) * r0, x + math.cos(a) * r * 0.93, y + math.sin(a) * r * 0.93,
                   stroke("#2b2d33", max(2.0, r * (0.06 if i % 3 == 0 else 0.03))))
    am = (mm / 60) * math.tau - math.pi / 2
    ah = ((hh % 12) / 12 + mm / 720) * math.tau - math.pi / 2
    c.drawLine(x, y, x + math.cos(ah) * r * 0.5, y + math.sin(ah) * r * 0.5, stroke("#2b2d33", max(3.0, r * 0.08)))
    c.drawLine(x, y, x + math.cos(am) * r * 0.75, y + math.sin(am) * r * 0.75, stroke("#2b2d33", max(2.0, r * 0.05)))
    c.drawCircle(x, y, r * 0.06, fill("#c8352e"))


def _tape_x(c, l, t, r, b, w, col="#d9c79a", a=0.85) -> None:
    c.drawLine(l, t, r, b, stroke(col, w, a))
    c.drawLine(r, t, l, b, stroke(col, w, a))


def _school_desk_3d(c, P: Persp, x, z, wood="#a87a4e", metal="#4a5058") -> None:
    """Bàn + ghế học sinh (phối cảnh), x = tâm, z = mép bàn phía camera. Ghế ở phía camera."""
    w, d, ht = 0.62, 0.45, 0.72
    x0, x1 = x - w / 2, x + w / 2
    for (lx, lz) in ((x0 + 0.03, z + d - 0.03), (x1 - 0.03, z + d - 0.03), (x0 + 0.03, z + 0.03), (x1 - 0.03, z + 0.03)):
        c.drawLine(*P.p(lx, 0, lz), *P.p(lx, ht - 0.12, lz), stroke(metal, max(2.0, 0.035 * P.f / lz)))
    path_fill(c, P.face_z(z + 0.02, x0 + 0.02, x1 - 0.02, ht - 0.2, ht - 0.03), shade(metal, -0.2))
    path_fill(c, P.face_z(z + 0.03, x0 + 0.06, x1 - 0.06, ht - 0.17, ht - 0.06), "#16181c")
    path_fill(c, P.plane_y(ht, x0, x1, z, z + d), shade(wood, 0.08))
    path_fill(c, P.face_z(z, x0, x1, ht - 0.035, ht), shade(wood, -0.2))
    # ghế
    cz = z - 0.32
    cw = 0.42
    c0, c1 = x - cw / 2, x + cw / 2
    for lx in (c0 + 0.03, c1 - 0.03):
        for lz in (cz + 0.33, cz + 0.03):
            c.drawLine(*P.p(lx, 0, lz), *P.p(lx, 0.42, lz), stroke(metal, max(2.0, 0.03 * P.f / lz)))
    path_fill(c, P.plane_y(0.43, c0, c1, cz, cz + 0.36), wood)
    path_fill(c, P.face_z(cz, c0, c1, 0.4, 0.43), shade(wood, -0.25))
    for lx in (c0 + 0.03, c1 - 0.03):
        c.drawLine(*P.p(lx, 0.43, cz - 0.02), *P.p(lx, 0.82, cz - 0.04), stroke(metal, max(2.0, 0.03 * P.f / cz)))
    path_fill(c, P.face_z(cz - 0.04, c0, c1, 0.6, 0.82), shade(wood, -0.08))
    path_fill(c, P.face_z(cz - 0.04, c0, c1, 0.6, 0.63), shade(wood, -0.3))


def scene_lop_hoc_cu_dem(tod: str) -> Scene:
    if tod == "side":
        return _lop_hoc_cu_side()
    P = Persp(f=1650, cx=W / 2, cy=1000, cam_h=1.45)
    XL, XR, YT, Z0, ZB = -4.6, 4.6, 3.1, 0.6, 11.5
    s = new_surface()
    c = s.getCanvas()
    wall, wood, floor_ = "#a89e88", "#a87a4e", "#7a5a40"
    path_fill(c, P.plane_y(YT, XL, XR, Z0, ZB), "#5e5a52")
    path_fill(c, P.plane_y(0, XL, XR, Z0, ZB), floor_)
    x = XL
    while x <= XR + 1e-6:
        c.drawLine(*P.p(x, 0, Z0 + 0.3), *P.p(x, 0, ZB), stroke(shade(floor_, -0.22), 4))
        x += 0.3
    path_fill(c, P.face_z(ZB, XL, XR, 0, YT), wall)
    path_fill(c, P.face_z(ZB, XL, XR, 0, 0.12), shade(wall, -0.35))
    path_fill(c, P.wall_x(XL, Z0, ZB, 0, YT), shade(wall, -0.12))
    path_fill(c, P.wall_x(XR, Z0, ZB, 0, YT), shade(wall, -0.06))
    path_fill(c, P.wall_x(XR, Z0, ZB, 0, 0.9), shade(wall, -0.2))         # ốp chân tường gỗ
    path_fill(c, P.wall_x(XL, Z0, ZB, 0, 0.9), shade(wall, -0.28))
    # trần: đèn huỳnh quang tắt
    for zz in (3.0, 6.0, 9.0):
        for xx in (-2.2, 2.2):
            path_fill(c, P.plane_y(YT - 0.01, xx - 0.7, xx + 0.7, zz, zz + 0.16), "#8a8c90")
    # bảng đen + khung chữ trống + đồng hồ
    path_fill(c, P.face_z(ZB - 0.01, -2.7, 2.7, 0.85, 2.25), "#6b4a32")
    path_fill(c, P.face_z(ZB - 0.02, -2.6, 2.6, 0.92, 2.18), "#2c4638")
    rng = random.Random(38)
    for _ in range(9):
        a_ = P.p(rng.uniform(-2.4, 2.2), rng.uniform(1.1, 2.0), ZB - 0.03)
        c.drawPath(oval(a_[0], a_[1], rng.uniform(20, 70), rng.uniform(6, 18)), fill("#e8efe8", rng.uniform(0.06, 0.14)))
    path_fill(c, P.face_z(ZB - 0.15, -2.7, 2.7, 0.82, 0.86), "#8a6a4a")
    lx_, ly_ = P.p(-1.3, 2.75, ZB - 0.02)
    rx_, ry_ = P.p(-0.25, 2.45, ZB - 0.02)
    c.drawRect(_R(lx_, ly_, rx_, ry_), fill("#5a4030"))
    c.drawRect(_R(lx_ + 8, ly_ + 8, rx_ - 8, ry_ - 8), fill("#ece4cc"))
    for j in range(3):
        yy = ly_ + 22 + j * (ry_ - ly_ - 40) / 3
        c.drawLine(lx_ + 30, yy, rx_ - 30 - (j % 2) * 30, yy, stroke("#c9bfa4", 5))
    cx_, cy_ = P.p(0.9, 2.62, ZB - 0.02)
    _wall_clock_face(c, cx_, cy_, 0.2 * P.f / ZB, 2, 44)
    # bục giảng
    path_fill(c, P.face_z(10.2, -0.55, 0.55, 0, 1.0), shade(wood, -0.15))
    path_fill(c, P.plane_y(1.0, -0.6, 0.6, 10.2, 10.6), shade(wood, 0.1))
    # cửa sổ trái (băng keo X, rèm tối)
    win_z = [(1.4, 3.3), (3.7, 5.6), (6.0, 7.9), (8.3, 10.2)]
    for (za, zb) in win_z:
        path_fill(c, P.wall_x(XL + 0.01, za - 0.06, zb + 0.06, 0.94, 2.66), "#c9c2b0")
        path_fill(c, P.wall_x(XL + 0.02, za, zb, 1.0, 2.6), "#1e2a48")
        mzc = (za + zb) / 2
        a_ = P.p(XL + 0.02, 2.1, za + 0.4)
        glow(c, a_[0], a_[1], 2.2 * P.f / za * 0.18, "#c9d8ff", 0.25)
        for (z0_, z1_) in ((za, mzc), (mzc, zb)):
            c.drawLine(*P.p(XL + 0.03, 1.0, z0_), *P.p(XL + 0.03, 2.6, z1_), stroke("#d9c79a", max(3.0, 0.06 * P.f / z0_), 0.8))
            c.drawLine(*P.p(XL + 0.03, 2.6, z0_), *P.p(XL + 0.03, 1.0, z1_), stroke("#d9c79a", max(3.0, 0.06 * P.f / z0_), 0.8))
        path_fill(c, P.wall_x(XL + 0.03, mzc - 0.03, mzc + 0.03, 1.0, 2.6), "#c9c2b0")
        path_fill(c, P.wall_x(XL + 0.03, za, zb, 1.78, 1.82), "#c9c2b0")
        path_fill(c, P.wall_x(XL + 0.06, zb - 0.45, zb + 0.1, 0.9, 2.75), "#2a2440")    # rèm gom
        path_fill(c, P.quad([(XL, 0.9, za), (XL + 0.25, 0.9, za), (XL + 0.25, 0.9, zb), (XL, 0.9, zb)]), "#c9c2b0")
    # cửa ra vào + bảng tin bên phải
    path_fill(c, P.wall_x(XR - 0.01, 9.4, 10.6, 0, 2.1), "#6b4a32")
    path_fill(c, P.wall_x(XR - 0.02, 9.55, 10.45, 1.3, 1.9), "#26304a")
    path_fill(c, P.wall_x(XR - 0.01, 4.5, 7.5, 1.3, 2.3), "#8a6a44")
    for (za, zb, yb, yt, col) in ((4.8, 5.5, 1.5, 2.1, "#ece4cc"), (5.8, 6.4, 1.6, 2.15, "#dfe6ee"), (6.7, 7.3, 1.45, 2.0, "#ece4cc")):
        path_fill(c, P.wall_x(XR - 0.02, za, zb, yb, yt), col)
    # vệt trăng trên sàn
    for (za, zb) in win_z:
        path_fill(c, P.quad([(XL + 0.9, 0.002, za + 0.4), (XL + 2.9, 0.002, za + 0.9), (XL + 2.9, 0.002, zb + 0.9),
                             (XL + 0.9, 0.002, zb + 0.4)]), "#c9d8ff", 0.16)
    # dãy bàn ghế: xa -> gần
    cols = [-3.5, -2.2, -0.9, 0.9, 2.2, 3.5]
    for z in (9.0, 7.7, 6.4, 5.1, 3.8, 2.5):
        for xx in cols:
            _school_desk_3d(c, P, xx, z, wood)
    tint(s, "#4a5a8c", 0.58)
    for (za, zb) in win_z:
        a_ = P.p(XL + 0.02, 1.8, (za + zb) / 2)
        glow(c, a_[0], a_[1], 1.4 * P.f / za * 0.3, "#c9d8ff", 0.2)
    _dust(c, 150, 1050, 1500, 2000, 70, 38, "#dfe8ff")
    _vignette(c, 0.55)
    mid = s.makeImageSnapshot()
    slots = {"center": P.slot(0, 2.6), "left": P.slot(-1.55, 3.0), "right": P.slot(1.55, 3.0),
             "board": P.slot(0.0, 9.8), "window": P.slot(-3.9, 5.2)}
    return Scene(None, mid, slots=slots, floor_y=slots["center"]["y"], lights=[])


def _lop_hoc_cu_side() -> Scene:
    s = new_surface()
    c = s.getCanvas()
    wall, wood = "#a89e88", "#a87a4e"
    FB = 1560
    c.drawRect(_R(0, 0, W, FB), fill(wall))
    vgrad(c, 0, 0, W, 240, ["#5e5a52", wall])
    c.drawRect(_R(0, FB - 380, W, FB), fill(shade(wall, -0.22)))
    # cửa sổ trái + rèm
    wl, wt, wr, wb = 160, 300, 1080, 1040
    c.drawRect(_R(wl - 28, wt - 28, wr + 28, wb + 28), fill("#c9c2b0"))
    vgrad(c, wl, wt, wr, wb, ["#121a34", "#2a3a62"])
    _moon(c, 820, 500, 70, a=0.95)
    for xx in ((wl + wr) / 2,):
        c.drawLine(xx, wt, xx, wb, stroke("#c9c2b0", 20))
    c.drawLine(wl, (wt + wb) / 2, wr, (wt + wb) / 2, stroke("#c9c2b0", 16))
    for (l_, r_) in ((wl, (wl + wr) / 2), ((wl + wr) / 2, wr)):
        _tape_x(c, l_ + 20, wt + 20, r_ - 20, (wt + wb) / 2 - 20, 22)
        _tape_x(c, l_ + 20, (wt + wb) / 2 + 20, r_ - 20, wb - 20, 22)
    for (cx_, sg) in ((wl - 40, 1), (wr + 40, -1)):
        p = skia.Path()
        p.moveTo(cx_ - 110, wt - 60)
        p.lineTo(cx_ + 110, wt - 60)
        p.quadTo(cx_ + 70 * sg + 40, (wt + wb) / 2, cx_ + 90, wb + 120)
        p.lineTo(cx_ - 90, wb + 120)
        p.close()
        path_fill(c, p, "#2a2440")
        for j in range(3):
            c.drawLine(cx_ - 60 + j * 60, wt - 50, cx_ - 50 + j * 60, wb + 110, stroke("#1c1830", 8))
    c.drawRect(_R(wl - 200, wt - 80, wr + 200, wt - 60), fill("#6e665a"))
    # bảng tin + tủ cubby dọc tường sau
    bl, bt, br, bb = 1500, 330, 2900, 820
    c.drawRect(_R(bl - 24, bt - 24, br + 24, bb + 24), fill("#6b4a32"))
    c.drawRect(_R(bl, bt, br, bb), fill("#b08a5a"))
    rng = random.Random(381)
    for i in range(7):
        x = bl + 60 + i * 190 + rng.uniform(-20, 20)
        y = bt + 50 + (i % 2) * 120 + rng.uniform(-10, 20)
        c.save()
        c.rotate(rng.uniform(-4, 4), x + 70, y + 100)
        c.drawRect(_R(x, y, x + 140, y + 190), fill(rng.choice(["#f4f1e8", "#eae0c8", "#dfe6ee"])))
        for j in range(4):
            c.drawLine(x + 18, y + 40 + j * 34, x + 120 - (j % 2) * 30, y + 40 + j * 34, stroke("#9a9488", 5))
        c.drawCircle(x + 70, y + 12, 9, fill("#c8352e"))
        c.restore()
    CL, CR, CT = 1240, 3780, 920
    c.drawRect(_R(CL - 20, CT - 30, CR + 20, CT), fill(shade(wood, 0.1)))
    c.drawRect(_R(CL, CT, CR, FB), fill(shade(wood, -0.1)))
    ncol, nrow = 12, 3
    cw, ch = (CR - CL) / ncol, (FB - 40 - CT) / nrow
    bag_cols = ["#2f4a7a", "#7a3a3a", "#3a5a3a", "#2b2d33", "#8a6a3a"]
    for i in range(ncol):
        for j in range(nrow):
            l_, t_ = CL + i * cw + 12, CT + j * ch + 12
            c.drawRect(_R(l_, t_, l_ + cw - 24, t_ + ch - 24), fill("#2a1e16"))
            if rng.random() < 0.45:
                col = rng.choice(bag_cols)
                c.drawPath(rrect(l_ + 14, t_ + ch * 0.25, l_ + cw - 38, t_ + ch - 24, 18), fill(col))
                c.drawRect(_R(l_ + 30, t_ + ch * 0.45, l_ + cw - 54, t_ + ch * 0.52), fill(shade(col, -0.3)))
            c.drawPath(rrect(l_ + cw * 0.3, t_ - 8, l_ + cw * 0.6, t_ + 6, 3), fill("#ece4cc"))
    c.drawRect(_R(CL, FB - 40, CR, FB), fill(shade(wood, -0.35)))
    _persp_floor(c, FB, "#7a5a40", "#5e4430", vx=1920, vy=700, spacing=260, dz=0.1)
    # 2 bộ bàn ghế nhìn ngang (tiền cảnh)
    def desk_side(x, base, k, flip=1):
        top = base - 0.72 * k
        c.drawRect(_R(x - 0.3 * k, top, x + 0.3 * k, top + 0.04 * k), fill(shade(wood, 0.08)))
        c.drawRect(_R(x - 0.27 * k, top + 0.04 * k, x + 0.27 * k, top + 0.18 * k), fill("#3e444c"))
        for lx in (x - 0.25 * k, x + 0.25 * k):
            c.drawRect(_R(lx - 0.02 * k, top + 0.18 * k, lx + 0.02 * k, base), fill("#4a5058"))
        c.drawRect(_R(x - 0.25 * k, base - 0.12 * k, x + 0.25 * k, base - 0.1 * k), fill("#4a5058"))
        cx = x - flip * 0.5 * k
        st = base - 0.43 * k
        c.drawRect(_R(cx - 0.2 * k, st, cx + 0.2 * k, st + 0.035 * k), fill(wood))
        for lx in (cx - 0.18 * k, cx + 0.18 * k):
            c.drawRect(_R(lx - 0.018 * k, st, lx + 0.018 * k, base), fill("#4a5058"))
        bx = cx - flip * 0.2 * k
        c.drawRect(_R(bx - 0.018 * k, st - 0.42 * k, bx + 0.018 * k, st), fill("#4a5058"))
        c.drawPath(rrect(bx - 0.03 * k, st - 0.42 * k, bx + 0.03 * k, st - 0.18 * k, 0.01 * k), fill(shade(wood, -0.1)))
        c.drawPath(oval(x, base + 0.01 * k, 0.75 * k, 0.04 * k), fill("#000000", 0.25))
    desk_side(1700, 1880, 700)
    desk_side(2800, 1880, 700)
    c.drawPath(rrect(2700, 1880 - 0.72 * 700 - 60, 2900, 1880 - 0.72 * 700, 6), fill("#e8e2d0"))
    # vệt trăng
    c.drawPath(poly([(wl, wt), (wr, wt), (wr + 1500, H), (wl + 700, H)]), lin_paint((wl, wt), (wl + 900, H),
               [("#c9d8ff", 0.16), ("#c9d8ff", 0.03)]))
    tint(s, "#4a5a8c", 0.58)
    glow(c, 820, 500, 500, "#dfe8ff", 0.3)
    _dust(c, 300, 400, 2400, 1900, 70, 39, "#dfe8ff")
    _vignette(c, 0.55)
    mid = s.makeImageSnapshot()
    slots = {"center": {"x": 2250, "y": 1990, "scale": 1.15}, "left": {"x": 1150, "y": 1990, "scale": 1.15},
             "right": {"x": 3350, "y": 1990, "scale": 1.15}, "seat_1": {"x": 1350, "y": 1890, "scale": 1.0},
             "seat_2": {"x": 2450, "y": 1890, "scale": 1.0}}
    return Scene(None, mid, slots=slots, floor_y=1990, lights=[{"x": 820, "y": 500, "color": "#dfe8ff"}])


# ------------------------------------------------------------------- 39. trường tiểu học ban đêm (ngoài)
def scene_truong_hoc_dem(tod: str) -> Scene:
    sf = new_surface()
    c = sf.getCanvas()
    _night_sky(c, 0, 1500, seed=39, top="#0b1026", bottom="#2a3360", n_stars=220)
    _moon(c, 3180, 360, 115)
    rng = random.Random(39)
    for _ in range(5):
        x, y = rng.uniform(-200, W), rng.uniform(200, 800)
        c.drawPath(rrect(x, y, x + rng.uniform(500, 1100), y + rng.uniform(26, 50), 25), fill("#3a4470", 0.5))
    _skyline(c, 1260, 391, "#141a34", 60, 200, lit="#ffd08a", lit_p=0.03)
    far = sf.makeImageSnapshot()
    s = new_surface()
    c = s.getCanvas()
    GB = 1420                       # chân toà nhà
    wall_c = "#c9c0aa"
    BL, BR, BT = 380, 3460, 760
    # cây sau
    for (tx, ty, tr) in ((300, 1150, 260), (3600, 1120, 300), (1000, 1240, 180), (2900, 1240, 200)):
        round_tree(c, tx, ty, tr, "#1a2a2a", "#141818", seed=int(tx))
    c.drawRect(_R(BL, BT, BR, GB), fill(wall_c))
    c.drawRect(_R(BL - 20, BT - 50, BR + 20, BT), fill(shade(wall_c, 0.1)))
    c.drawRect(_R(BL - 20, BT - 8, BR + 20, BT + 10), fill(shade(wall_c, -0.3)))
    fh = (GB - BT) / 3
    for f_ in range(3):
        y0 = BT + f_ * fh
        c.drawRect(_R(BL, y0 + fh - 16, BR, y0 + fh), fill(shade(wall_c, -0.18)))
        for i in range(16):
            x = BL + 70 + i * 190
            if 1700 < x + 75 and x < 2140:
                continue
            lit = (f_, i) in ((1, 3), (0, 12))
            c.drawRect(_R(x, y0 + 50, x + 130, y0 + fh - 50), fill("#e8d9a0" if lit else "#1e2844"))
            c.drawLine(x + 65, y0 + 50, x + 65, y0 + fh - 50, stroke(shade(wall_c, -0.1), 6))
            if not lit:
                quad(c, [(x + 10, y0 + fh - 50), (x + 40, y0 + fh - 50), (x + 100, y0 + 50), (x + 70, y0 + 50)], "#ffffff", 0.07)
    # tháp đồng hồ
    TL, TR, TT = 1700, 2140, 330
    c.drawRect(_R(TL, TT, TR, GB), fill(shade(wall_c, 0.05)))
    c.drawRect(_R(TR - 40, TT, TR, GB), fill(shade(wall_c, -0.15)))
    quad(c, [(TL - 40, TT), (TR + 40, TT), ((TL + TR) / 2, TT - 220)], "#4a3a3a")
    c.drawRect(_R(TL - 40, TT - 10, TR + 40, TT + 24), fill(shade(wall_c, -0.3)))
    _wall_clock_face(c, (TL + TR) / 2, TT + 190, 120, 11, 52)
    c.drawRect(_R(TL + 110, TT + 360, TR - 110, TT + 560), fill("#1e2844"))
    # sảnh + mái hiên
    c.drawRect(_R(1760, GB - 330, 2080, GB), fill("#141a2c"))
    c.drawRect(_R(1640, GB - 380, 2200, GB - 330), fill(shade(wall_c, -0.2)))
    for x in (1700, 2140):
        c.drawRect(_R(x - 18, GB - 330, x + 18, GB), fill(shade(wall_c, -0.1)))
    # sân + tường rào + hàng rào lưới
    c.drawRect(_R(0, GB, W, 1660), fill("#4a4a52"))
    FT, FBm = 1250, 1660
    c.drawRect(_R(0, FBm - 120, W, FBm), fill("#8a8478"))
    c.drawRect(_R(0, FBm - 130, W, FBm - 112), fill("#a8a294"))
    c.save()
    gate_l, gate_r = 700, 1380
    c.clipRect(_R(0, FT, W, FBm - 120))
    for x0 in range(-600, W + 600, 46):
        c.drawLine(x0, FT, x0 + (FBm - 120 - FT), FBm - 120, stroke("#9aa0a8", 3, 0.55))
        c.drawLine(x0, FBm - 120, x0 + (FBm - 120 - FT), FT, stroke("#9aa0a8", 3, 0.55))
    c.restore()
    for x in list(range(40, W, 380)):
        c.drawRect(_R(x - 10, FT - 20, x + 10, FBm - 120), fill("#6e747c"))
    c.drawRect(_R(0, FT - 14, W, FT), fill("#6e747c"))
    # cổng: 2 trụ + cửa trượt + bảng tên (signs)
    c.drawRect(_R(gate_l, FT - 40, gate_r, FBm), fill("#3a3e48"))
    c.drawRect(_R(gate_l, FT - 40, gate_r, FBm), fill("#000000", 0.0))
    c.save()
    c.clipRect(_R(gate_l, FT, gate_r, FBm))
    vgrad(c, gate_l, FT, gate_r, FBm, ["#2a3050", "#4a4a52"])
    for xx in range(gate_l, gate_r, 60):
        c.drawLine(xx, FT + 60, xx, FBm - 10, stroke("#7a8088", 8))
    c.drawLine(gate_l, FT + 60, gate_r, FT + 60, stroke("#7a8088", 12))
    c.drawLine(gate_l, FBm - 30, gate_r, FBm - 30, stroke("#7a8088", 12))
    c.restore()
    for x in (gate_l - 70, gate_r):
        c.drawRect(_R(x, FT - 160, x + 70, FBm), fill("#9a9488"))
        c.drawRect(_R(x - 10, FT - 180, x + 80, FT - 150), fill("#b0aa9c"))
    for x in (gate_r + 200, gate_r + 1000):         # 2 chân đỡ bảng tên (bảng chữ = signs)
        c.drawRect(_R(x - 14, FT - 60, x + 14, FBm - 120), fill("#5a5e66"))
    c.drawRect(_R(gate_r + 80, FT - 150, gate_r + 1120, FT - 20), fill("#2a1d12"))
    # đường + vũng nước
    c.drawRect(_R(0, FBm, W, H), fill("#2a2c36"))
    c.drawRect(_R(0, FBm, W, FBm + 30), fill("#3a3c46"))
    for x in range(100, W, 700):
        c.drawRect(_R(x, 1990, x + 380, 2010), fill("#c9c0a0", 0.5))
    _puddle(c, 1100, 1850, 420, 40, "#5a6a90", 0.5)
    _puddle(c, 2600, 2060, 560, 56, "#5a6a90", 0.5)
    c.drawPath(oval(2600, 2050, 60, 12), fill("#f1ead2", 0.35))         # trăng phản chiếu
    lx, ly = _streetlamp(c, 3050, FBm + 20, 5.2, 210, lit=True, arm=-1, pool_y=1880)
    tint(s, "#6a78b0", 0.42)
    glow(c, lx, ly + 10, 260, "#ffe2a0", 0.6)
    glow(c, (TL + TR) / 2, TT + 190, 260, "#f2efe6", 0.18)
    for (f_, i) in ((1, 3), (0, 12)):
        glow(c, BL + 70 + i * 190 + 65, BT + f_ * fh + fh / 2, 160, "#ffe2a0", 0.35)
    _vignette(c, 0.45)
    mid = s.makeImageSnapshot()
    slots = {"center": {"x": 1920, "y": 1950, "scale": 0.9}, "left": {"x": 1040, "y": 1950, "scale": 0.9},
             "right": {"x": 2700, "y": 1950, "scale": 0.9}, "gate": {"x": 1040, "y": 1680, "scale": 0.7}}
    signs = [{"text": "CITY ELEMENTARY SCHOOL", "box": [gate_r + 90, FT - 140, gate_r + 1110, FT - 30], "style": "gold_board"}]
    return Scene(far, mid, slots=slots, signs=signs, floor_y=1950, parallax=(0.85, 1.0, 1.1),
                 lights=[{"x": round(lx), "y": round(ly), "color": "#ffe2a0"}, {"x": 3180, "y": 360, "color": "#f1ead2"}])


# ------------------------------------------------------------------- 40. sảnh tủ giày trường học
def scene_sanh_tu_giay_truong(tod: str) -> Scene:
    baked: list = []
    s = new_surface()
    c = s.getCanvas()
    wall, wood = "#cfc6b0", "#9a7048"
    FB = 1620
    c.drawRect(_R(0, 0, W, FB), fill(wall))
    vgrad(c, 0, 0, W, 200, ["#6e6a60", wall])
    c.drawRect(_R(0, FB - 120, W, FB), fill(shade(wall, -0.2)))
    rng = random.Random(40)
    # 2 dãy tủ giày
    def cubbies(l, r, t, b, ncol, nrow):
        c.drawRect(_R(l - 18, t - 30, r + 18, b + 10), fill(shade(wood, -0.15)))
        c.drawRect(_R(l - 24, t - 40, r + 24, t - 20), fill(shade(wood, 0.12)))
        cw, ch = (r - l) / ncol, (b - t) / nrow
        for i in range(ncol):
            for j in range(nrow):
                x0, y0 = l + i * cw + 8, t + j * ch + 8
                x1, y1 = x0 + cw - 16, y0 + ch - 16
                c.drawRect(_R(x0, y0, x1, y1), fill("#2a2018"))
                c.drawRect(_R(x0, y0, x1, y0 + 10), fill("#140e0a"))
                c.drawPath(rrect(x0 + cw * 0.3, y0 - 6, x1 - cw * 0.3, y0 + 8, 3), fill("#ece4cc"))
                kind = rng.random()
                if kind < 0.55:            # dép đi trong nhà trắng, mũi màu
                    tip = rng.choice(["#3a78c2", "#c8352e", "#4fa35a"])
                    for k_ in (0, 1):
                        sx0 = x0 + 12 + k_ * (cw - 16) * 0.46
                        sx1 = sx0 + (cw - 16) * 0.42
                        c.drawPath(rrect(sx0, y1 - ch * 0.3, sx1, y1 - 4, 14), fill("#eeeae2"))
                        c.drawPath(rrect(sx1 - (sx1 - sx0) * 0.45, y1 - ch * 0.3, sx1, y1 - 4, 14), fill(tip))
                elif kind < 0.75:          # giày đi ngoài nâu
                    for k_ in (0, 1):
                        sx0 = x0 + 10 + k_ * (cw - 16) * 0.47
                        c.drawPath(rrect(sx0, y1 - ch * 0.36, sx0 + (cw - 16) * 0.44, y1 - 4, 18), fill("#5a3a26"))
        c.drawRect(_R(l - 18, b + 10, r + 18, b + 50), fill(shade(wood, -0.35)))
    cubbies(120, 1300, 520, 1560, 7, 6)
    cubbies(1400, 2580, 520, 1560, 7, 6)
    # bảng ghim "NOTICE"
    NL, NT, NR, NB = 2700, 520, 3240, 1100
    c.drawRect(_R(NL - 24, NT - 24, NR + 24, NB + 24), fill("#6b4a32"))
    c.drawRect(_R(NL, NT, NR, NB), fill("#b48a5a"))
    for _ in range(40):
        c.drawCircle(rng.uniform(NL, NR), rng.uniform(NT, NB), rng.uniform(3, 6), fill("#8a6a44", 0.5))
    c.drawRect(_R(NL, NT, NR, NT + 100), fill("#2f5a8a"))
    text_center(c, "NOTICE", (NL + NR) / 2, NT + 50, 62, "#f4f1e8", "extrabold")
    baked.append(_baked("NOTICE", (NL + NR) / 2, NT + 50, 62))
    for (x, y, w_, h_, a) in ((NL + 40, NT + 140, 200, 260, -3), (NL + 280, NT + 130, 210, 170, 2), (NL + 290, NT + 330, 200, 200, -2),
                              (NL + 60, NT + 420, 180, 130, 4)):
        c.save()
        c.rotate(a, x + w_ / 2, y + h_ / 2)
        c.drawRect(_R(x, y, x + w_, y + h_), fill(rng.choice(["#f4f1e8", "#f2e6b8", "#dfe6ee"])))
        for j in range(int(h_ / 40) - 1):
            c.drawLine(x + 16, y + 34 + j * 36, x + w_ - 16 - (j % 2) * 40, y + 34 + j * 36, stroke("#9a9488", 5))
        c.drawCircle(x + w_ / 2, y + 10, 9, fill("#c8352e"))
        c.restore()
    # ô dù
    c.drawRect(_R(2760, 1300, 3100, 1600), fill("#5a6066"))
    for k_, col in enumerate(("#2f4a7a", "#c8352e", "#2b2d33", "#4fa35a")):
        x = 2800 + k_ * 75
        c.drawLine(x, 1300, x + 10, 1100 + k_ * 20, stroke(col, 26))
        c.drawPath(capsule(x + 10, 1100 + k_ * 20, x + 30, 1070 + k_ * 20, 12, 10), fill("#2a2622"))
    # cửa kính đôi ra sân (đêm)
    DL, DT, DR, DB = 3330, 380, 3800, 1620
    c.drawRect(_R(DL - 30, DT - 30, W, DB), fill("#8a9098"))
    vgrad(c, DL, DT, DR, DB, ["#0e1430", "#2a3058"])
    glow(c, DL + 260, DT + 420, 260, "#ffe2a0", 0.5)
    c.drawRect(_R(DL, DB - 400, DR, DB), fill("#1a1e2a"))
    c.drawLine((DL + DR) / 2, DT, (DL + DR) / 2, DB, stroke("#8a9098", 22))
    c.drawLine(DL, DT + 520, DR, DT + 520, stroke("#8a9098", 14))
    for hx in ((DL + DR) / 2 - 40, (DL + DR) / 2 + 40):
        c.drawPath(rrect(hx - 8, DT + 600, hx + 8, DT + 820, 6), fill("#c9ccd2"))
    reflections(c, DL, DT, DR, DB, 3, 0.15, seed=40)
    # sàn: bậc gỗ trước tủ + đá xám
    _persp_floor(c, FB, "#7e7a72", "#68645e", vx=1920, vy=800, spacing=320, dz=0.12)
    c.drawRect(_R(80, FB + 20, 2620, FB + 140), fill(wood))
    c.drawRect(_R(80, FB + 20, 2620, FB + 36), fill(shade(wood, 0.15)))
    for x in range(140, 2600, 120):
        c.drawLine(x, FB + 36, x, FB + 140, stroke(shade(wood, -0.3), 6))
    c.drawRect(_R(80, FB + 140, 2620, FB + 170), fill("#000000", 0.3))
    _tube(c, 1400, 110, 900, on=True, col="#eef6ff")
    _tube(c, 3000, 110, 600, on=False)
    tint(s, "#5a6890", 0.5)
    glow(c, 1400, 140, 1000, "#eef6ff", 0.25)
    glow(c, DL + 260, DT + 420, 200, "#ffe2a0", 0.4)
    _vignette(c, 0.5)
    mid = s.makeImageSnapshot()
    slots = {"center": {"x": 1920, "y": 2010, "scale": 1.1}, "left": {"x": 900, "y": 2010, "scale": 1.1},
             "right": {"x": 2950, "y": 2010, "scale": 1.1}, "door": {"x": 3560, "y": 1960, "scale": 1.0},
             "lockers": {"x": 1350, "y": 1900, "scale": 1.05}}
    return Scene(None, mid, slots=slots, baked_signs=baked, floor_y=2010, lights=[{"x": 1400, "y": 130, "color": "#eef6ff"}])

# ------------------------------------------------------------------- 41. phố dân cư đêm: máy bán nước, cột điện, cổng đền
def _house_gable(c, l, r, base, wall_h, roof_h, wall, roof, night, rng, lit_p=0.5) -> None:
    top = base - wall_h
    c.drawRect(_R(l, top, r, base), fill(wall))
    quad(c, [(l - 60, top + 10), (r + 60, top + 10), ((l + r) / 2 + 40, top - roof_h), ((l + r) / 2 - 40, top - roof_h)], roof)
    c.drawRect(_R(l - 60, top + 4, r + 60, top + 26), fill(shade(roof, -0.3)))
    nw = max(1, int((r - l) / 330))
    for i in range(nw):
        x = l + (r - l) * (i + 0.5) / nw
        lit = night and rng.random() < lit_p
        wc = "#ffd98a" if lit else ("#2a3048" if night else "#8aa0b4")
        c.drawRect(_R(x - 90, top + 70, x + 90, top + 230), fill(wc))
        c.drawLine(x, top + 70, x, top + 230, stroke(shade(wall, -0.2), 8))
        c.drawRect(_R(x - 100, top + 230, x + 100, top + 246), fill(shade(wall, -0.15)))
        if lit:
            glow(c, x, top + 150, 220, "#ffd98a", 0.35)


def scene_pho_dan_cu_may_ban_nuoc(tod: str) -> Scene:
    night = tod != "day"
    baked: list = []
    sf = new_surface()
    c = sf.getCanvas()
    if night:
        vgrad(c, 0, 0, W, 1300, ["#151638", "#3a2f62", "#7a5288", "#b07a96"], [0, 0.45, 0.8, 1])
        stars(c, 0, 0, W, 500, 120, seed=41)
        _moon(c, 860, 330, 90)
    else:
        _day_sky(c, 0, 1300, top="#8fb0cc", bottom="#e4ecf0")
    _skyline(c, 1150, 411, "#2a2448" if night else "#a9b4bc", 60, 220, lit="#ffd08a" if night else None, lit_p=0.04)
    far = sf.makeImageSnapshot()
    s = new_surface()
    c = s.getCanvas()
    rng = random.Random(41)
    GB = 1640                       # chân tường rào / mép đường
    k = 450.0                       # px/mét ở mặt tường
    wall_cols = ["#d8cbb0", "#c9c6bc", "#d9c2a8", "#bfc6c4"] if not night else ["#6a6078", "#5e6070", "#6e5e6a", "#585e6e"]
    roof_cols = ["#3e4656", "#5a4040", "#3a4a48", "#4a4452"] if not night else ["#22263a", "#2e2230", "#1e2a30", "#28243a"]
    for i, (l, r) in enumerate(((1100, 2050), (2150, 3050), (3150, 4000))):
        _house_gable(c, l, r, 1300, 560, 240, wall_cols[i], roof_cols[i], night, rng, 0.6)
    # lối nhỏ bên trái lên đền: bậc đá + cây tối + cổng
    c.drawRect(_R(0, 700, 1000, GB), fill("#1e2a28" if night else "#5e7a5a"))
    for (tx, ty, tr) in ((180, 900, 320), (760, 860, 300), (480, 760, 260)):
        round_tree(c, tx, ty, tr, "#16221f" if night else "#4f6e4c", "#141818" if night else "#5a4636", seed=int(tx) + 4)
    for j in range(6):
        y = GB - j * 45
        c.drawRect(_R(330 + j * 22, y - 45, 830 - j * 22, y), fill(shade("#9a948a" if not night else "#4a4a56", -0.04 * j)))
        c.drawRect(_R(330 + j * 22, y - 45, 830 - j * 22, y - 36), fill(shade("#b0aa9e" if not night else "#5a5a66", 0)))
    _shrine_gate(c, 580, GB - 280, 230, "#c8452e" if not night else "#8a3a30", baked)
    # tường rào gạch block
    blk = "#b4ae9e" if not night else "#5c5a68"
    _block_wall(c, 1000, 1180, W + 20, GB, blk, bw=160, bh=80)
    c.drawRect(_R(980, 1150, 1020, GB), fill(shade(blk, -0.2)))
    # vỉa + đường
    road = "#5a5c64" if not night else "#2c2c3c"
    c.drawRect(_R(0, GB, W, H), fill(road))
    c.drawRect(_R(0, GB, W, GB + 36), fill(shade(road, 0.18)))
    c.drawRect(_R(0, GB + 70, W, GB + 86), fill("#e8e4d8" if not night else "#8a8a98"))
    c.drawPath(oval(2950, 2020, 200, 40), fill(shade(road, -0.25)))
    c.drawPath(oval(2950, 2020, 200, 40), stroke(shade(road, 0.15), 6))
    for x in range(2780, 3130, 50):
        c.drawLine(x, 2000, x + 20, 2040, stroke(shade(road, 0.1), 4))
    # 2 máy bán nước
    _vending(c, 1880, GB + 10, 460, 840, "#2f6fb0" if not night else "#2a5a98", night, 411, baked)
    _vending(c, 2380, GB + 10, 460, 840, "#e8e4dc" if not night else "#b8b8c4", night, 412, baked, rows=("COLD", "HOT", "HOT"))
    c.drawRect(_R(2850, GB - 120, 2960, GB + 10), fill("#3a7a4a"))       # thùng rác lon
    c.drawPath(rrect(2840, GB - 140, 2970, GB - 110, 10), fill("#2f6a3e"))
    c.drawCircle(2905, GB - 125, 22, fill("#141618"))
    # cột điện + dây
    poles = [(1340, "2-14"), (3560, "2-15")]
    tops = []
    for (px, plate) in poles:
        tops.append(_util_pole(c, px, GB + 20, 9.0 / 2.2, k, plate, baked, col="#9a968e" if not night else "#5e5c66",
                               trans=px > 3000))
    wire = "#1c1c24" if night else "#3a3a40"
    for n in range(4):
        y0 = tops[0] + 0.5 * k + n * 18
        sag_wire(c, -50, y0 + 60, 1340, y0, 50, wire, 5)
        sag_wire(c, 1340, y0, 3560, tops[1] + 0.5 * k + n * 18, 120, wire, 5)
        sag_wire(c, 3560, tops[1] + 0.5 * k + n * 18, W + 50, y0 + 80, 40, wire, 5)
    # đèn đường gắn cột + gương cầu
    lx, ly = _streetlamp(c, 1340 + 0.12 * k, GB + 20, 3.6, k * 0.9, lit=night, arm=1, cone=night, pool_y=1900, pole=False)
    _curved_mirror(c, 3250, GB + 30, 420)
    if night:
        tint(s, "#8a80c0", 0.35)
        glow(c, lx, ly + 10, 200, "#ffe2a0", 0.6)
        glow(c, 2110, 1150, 500, "#e8f4ff", 0.3)
        glow(c, 2610, 1150, 500, "#e8f4ff", 0.3)
        ellipse_glow(c, 2360, GB + 120, 900, 120, "#e8f4ff", 0.35)
        glow(c, 580, GB - 600, 400, "#ffb070", 0.15)
    _vignette(c, 0.45 if night else 0.3)
    mid = s.makeImageSnapshot()
    slots = {"center": {"x": 1920, "y": 1990, "scale": 1.0}, "left": {"x": 1000, "y": 1990, "scale": 1.0},
             "right": {"x": 3000, "y": 1990, "scale": 1.0}, "vending": {"x": 2360, "y": 1900, "scale": 0.95},
             "shrine": {"x": 580, "y": 1600, "scale": 0.62}}
    return Scene(far, mid, slots=slots, baked_signs=baked, floor_y=1990, parallax=(0.85, 1.0, 1.1),
                 lights=[{"x": round(lx), "y": round(ly), "color": "#ffe2a0"}] if night else [])


# ------------------------------------------------------------------- 42. lối đi dài ban đêm, hàng cột đèn
def scene_loi_di_dai_dem(tod: str) -> Scene:
    P = Persp(f=1500, cx=W / 2, cy=980, cam_h=1.6)
    XW, HW, Z0, ZB = 1.7, 2.3, 1.0, 70.0
    sf = new_surface()
    c = sf.getCanvas()
    _night_sky(c, 0, 1300, seed=42, top="#070a18", bottom="#1a2140", n_stars=200)
    _moon(c, 2900, 300, 70, a=0.9)
    _skyline(c, 1000, 421, "#0e1224", 100, 400, lit="#ffd08a", lit_p=0.02, l=-60, r=W + 60)
    far = sf.makeImageSnapshot()
    s = new_surface()
    c = s.getCanvas()
    for sd in (-1, 1):                 # cây tối sau tường
        for zz in (6, 14, 24, 40):
            bx, by = P.p(sd * (XW + 2.5), HW + 2.2, zz)
            r_ = 2.6 * P.f / zz
            c.drawCircle(bx, by, r_, fill("#0c1418"))
            c.drawCircle(bx + sd * r_ * 0.6, by + r_ * 0.3, r_ * 0.8, fill("#0c1418"))
    path_fill(c, P.plane_y(0, -XW, XW, Z0, ZB), "#3a3c48")
    z = 2.0
    while z < ZB:
        c.drawLine(*P.p(-XW, 0, z), *P.p(XW, 0, z), stroke("#2a2c36", max(1.5, 10 / z)))
        z += 2.0
    for sd in (-1, 1):
        x = sd * XW
        path_fill(c, P.wall_x(x, Z0, ZB, 0, HW), "#5a5c66" if sd < 0 else "#52545e")
        path_fill(c, P.quad([(x, HW, Z0), (x, HW, ZB), (x + sd * 0.25, HW, ZB), (x + sd * 0.25, HW, Z0)]), "#6e707a")
        z = 1.0
        while z < ZB:
            c.drawLine(*P.p(x, 0, z), *P.p(x, HW, z), stroke("#44464f", max(1.5, 8 / z)))
            z += 3.0
        y = 0.4
        while y < HW:
            c.drawLine(*P.p(x, y, Z0), *P.p(x, y, ZB), stroke("#4a4c56", 3, 0.6))
            y += 0.4
        path_fill(c, P.wall_x(x, Z0, ZB, 0, 0.15), "#2a2c34")
        rs = random.Random(420 + sd)
        for _ in range(14):                       # vệt ố / rêu trên tường
            za = rs.uniform(1.2, 30.0)
            zb = za + rs.uniform(0.6, 2.5)
            yb = rs.uniform(0.0, 1.2)
            path_fill(c, P.wall_x(x * 0.999, za, zb, yb, yb + rs.uniform(0.3, 1.0)), "#2a2e2a", rs.uniform(0.12, 0.25))
    path_fill(c, P.face_z(ZB, -XW, XW, 0, HW), "#07080e")
    # hàng cột đèn bên trái
    lamps = []
    for zz in (62.0, 50.0, 40.0, 31.0, 23.0, 16.0, 10.0, 5.2):
        k = P.f / zz
        bx, by = P.p(-XW + 0.35, 0, zz)
        hx, hy = _streetlamp(c, bx, by, 3.8, k, lit=True, arm=1, cone=True)
        lamps.append((hx, hy, k))
    c.drawRect(_R(0, 0, W, H), rad_paint(P.cx, P.cy, 900, [("#000000", 0.55), ("#000000", 0.0)], [0, 1]))
    tint(s, "#7a86b8", 0.3)
    for (hx, hy, k) in lamps:
        glow(c, hx, hy, 1.0 * k, "#ffe2a0", 0.45)
    _vignette(c, 0.6)
    mid = s.makeImageSnapshot()
    slots = {"center": P.slot(0.0, 3.6), "left": P.slot(-0.8, 3.6), "right": P.slot(0.85, 3.6),
             "far": P.slot(0.0, 14.0), "very_far": P.slot(0.1, 30.0)}
    return Scene(far, mid, slots=slots, floor_y=slots["center"]["y"], parallax=(0.9, 1.0, 1.1),
                 lights=[{"x": round(hx), "y": round(hy), "color": "#ffe2a0"} for (hx, hy, _) in lamps[-3:]])


# ------------------------------------------------------------------- 43. nhà trọ 2 tầng: cầu thang sắt ngoài, xe đạp
def scene_nha_tro_hai_tang(tod: str) -> Scene:
    night = tod != "day"
    baked: list = []
    sf = new_surface()
    c = sf.getCanvas()
    if night:
        _night_sky(c, 0, 1400, seed=43, top="#0b1022", bottom="#262e52", n_stars=200)
        _moon(c, 3500, 260, 80)
    else:
        _day_sky(c, 0, 1400, top="#8fb0cc", bottom="#e4ecf0")
    _skyline(c, 1250, 431, "#141a30" if night else "#b4bcc4", 80, 260, lit="#ffd08a" if night else None, lit_p=0.04)
    far = sf.makeImageSnapshot()
    s = new_surface()
    c = s.getCanvas()
    GB, k = 1800, 260.0
    F2 = GB - 2.6 * k                # sàn tầng 2
    RT = F2 - 2.6 * k                # mái
    BL, BR = 360, 3020
    siding = "#cdb894" if not night else "#6a6070"
    c.drawRect(_R(0, GB, W, H), fill("#8a8478" if not night else "#2e2e3a"))
    for _ in range(260):
        x, y = rng_x = random.random() * W, GB + random.random() * (H - GB)
    rng = random.Random(43)
    for _ in range(260):
        c.drawCircle(rng.uniform(0, W), rng.uniform(GB + 10, H), rng.uniform(2, 5), fill("#000000", 0.15))
    c.drawRect(_R(BL, RT, BR, GB), fill(siding))
    y = RT + 20
    while y < GB:
        c.drawLine(BL, y, BR, y, stroke(shade(siding, -0.12), 4))
        y += 34
    quad(c, [(BL - 120, RT + 30), (BR + 120, RT + 30), (BR + 40, RT - 120), (BL - 40, RT - 120)], "#3a3e48" if not night else "#1e2230")
    c.drawRect(_R(BL - 120, RT + 20, BR + 120, RT + 44), fill("#2a2e38" if not night else "#16181f"))
    # hành lang tầng 2 (sàn + lan can)
    c.drawRect(_R(BL - 40, F2 - 10, BR + 40, F2 + 40), fill("#8a8c94" if not night else "#40424e"))
    c.drawRect(_R(BL - 40, F2 + 40, BR + 40, F2 + 56), fill("#000000", 0.3))
    for x in (BL - 20, BR + 20):
        c.drawRect(_R(x - 14, F2 + 40, x + 14, GB), fill("#7a7c84" if not night else "#3a3c46"))
    doors = [(800, GB, "101"), (1800, GB, "102"), (800, F2, "201"), (1800, F2, "202")]
    door_col = "#8a6a4a" if not night else "#4a3a30"
    lamps = []
    for (dx, fy, num) in doors:
        dl, dr, dt = dx - 0.45 * k, dx + 0.45 * k, fy - 2.0 * k
        c.drawRect(_R(dl - 14, dt - 14, dr + 14, fy), fill(shade(siding, -0.25)))
        c.drawRect(_R(dl, dt, dr, fy), fill(door_col))
        c.drawRect(_R(dl + 20, dt + 20, dr - 20, dt + 60), fill(shade(door_col, -0.2)))
        c.drawCircle(dr - 30, dt + 1.05 * k, 12, fill("#c9ccd2"))
        c.drawRect(_R(dl + 40, dt + 0.75 * k, dl + 110, dt + 0.82 * k), fill("#2a2622"))   # khe thư
        _num_plate(c, dx, dt + 0.32 * k, num, 0.2 * k, baked, bg="#f4f1e8", fg="#2b2d36", pad=0.35)
        # cửa sổ song sắt cạnh cửa
        wl_, wr_ = dx + 0.75 * k, dx + 2.15 * k
        wt_, wb_ = fy - 1.75 * k, fy - 0.95 * k
        lit = night and num in ("102", "201")
        c.drawRect(_R(wl_, wt_, wr_, wb_), fill("#ffd98a" if lit else ("#22283c" if night else "#7f96a8")))
        for i in range(1, 7):
            xx = wl_ + (wr_ - wl_) * i / 7
            c.drawLine(xx, wt_, xx, wb_, stroke("#5a5e66", 6))
        c.drawRect(_R(wl_ - 10, wt_ - 10, wr_ + 10, wb_ + 10), stroke(shade(siding, -0.3), 10))
        if lit:
            glow(c, (wl_ + wr_) / 2, (wt_ + wb_) / 2, 260, "#ffd98a", 0.35)
        # đèn nhỏ trên cửa
        c.drawPath(rrect(dx - 26, dt - 70, dx + 26, dt - 26, 10), fill("#fff3cf" if night else "#e8e4dc"))
        lamps.append((dx, dt - 48))
        # máy giặt / chậu cây trước cửa
        if num in ("201", "102"):
            c.drawPath(rrect(dl - 260, fy - 0.85 * k, dl - 60, fy, 14), fill("#e8eaee" if not night else "#8a8c98"))
            c.drawCircle(dl - 160, fy - 0.45 * k, 0.22 * k, fill("#3a3e48"))
    # lan can tầng 2 (che phần dưới cửa tầng 2)
    rail = "#6e7078" if not night else "#3a3c48"
    c.drawRect(_R(BL - 40, F2 - 1.05 * k, BR + 40, F2 - 1.0 * k), fill(rail))
    c.drawRect(_R(BL - 40, F2 - 0.55 * k, BR + 40, F2 - 0.52 * k), fill(rail))
    x = BL - 30
    while x < BR + 40:
        c.drawRect(_R(x, F2 - 1.0 * k, x + 8, F2 - 10), fill(rail))
        x += 60
    # cầu thang sắt ngoài bên phải
    st = "#7a7c84" if not night else "#40424e"
    SX0, SX1 = 3060, 3700
    c.drawRect(_R(BR + 40, F2 - 10, SX0 + 40, F2 + 40), fill("#8a8c94" if not night else "#40424e"))
    nst = 13
    for i in range(nst):
        t = i / nst
        x0 = SX0 + (SX1 - SX0) * t
        y0 = F2 + (GB - F2) * t
        c.drawRect(_R(x0, y0 + 10, x0 + (SX1 - SX0) / nst + 10, y0 + 30), fill(shade(st, 0.12)))
    for off in (0, 26):
        c.drawLine(SX0, F2 + 40 + off, SX1 + 30, GB + off * 0.2, stroke(st, 18))
    c.drawLine(SX0, F2 - 1.0 * k, SX1 + 40, GB - 1.0 * k, stroke(st, 14))
    for i in range(0, nst + 1, 2):
        t = i / nst
        x0 = SX0 + (SX1 - SX0) * t
        y0 = F2 + (GB - F2) * t
        c.drawLine(x0, y0, x0, y0 - 1.0 * k, stroke(st, 8))
    c.drawRect(_R(SX1 + 20, GB - 1.0 * k, SX1 + 44, GB), fill(st))
    # hộp thư (2x2, không chữ)
    ml, mt = 2350, GB - 1.6 * k
    for i in range(2):
        for j in range(2):
            x0, y0 = ml + i * 150, mt + j * 120
            c.drawRect(_R(x0, y0, x0 + 140, y0 + 110), fill("#9aa0a8" if not night else "#5a5e6a"))
            c.drawRect(_R(x0 + 20, y0 + 20, x0 + 120, y0 + 34), fill("#2a2c34"))
    c.drawRect(_R(ml + 130, mt + 240, ml + 170, GB), fill("#6e7078" if not night else "#3a3c48"))
    # xe đạp
    _bicycle(c, 1250, GB + 60, 300, "#c8352e" if not night else "#7a2a26")
    _bicycle(c, 1500, GB + 80, 300, "#3a6ab0" if not night else "#2a4a7a", basket=False)
    _bicycle(c, 2950, GB + 40, 300, "#d9c34a" if not night else "#7a6e3a", facing=-1)
    if night:
        tint(s, "#6a78b0", 0.45)
        for (lx_, ly_) in lamps:
            glow(c, lx_, ly_, 240, "#ffe9b0", 0.55)
            _light_cone(c, lx_, ly_ + 20, 30, lx_, ly_ + 2.1 * k, 260, "#ffe9b0", 0.1)
    _vignette(c, 0.45 if night else 0.3)
    mid = s.makeImageSnapshot()
    slots = {"center": {"x": 1920, "y": 2000, "scale": 0.68}, "left": {"x": 900, "y": 2000, "scale": 0.68},
             "right": {"x": 2700, "y": 2000, "scale": 0.68}, "door_101": {"x": 800, "y": GB + 20, "scale": 0.6},
             "door_201": {"x": 800, "y": round(F2), "scale": 0.58}, "stairs": {"x": 3500, "y": 1990, "scale": 0.65}}
    return Scene(far, mid, slots=slots, baked_signs=baked, floor_y=2000, parallax=(0.85, 1.0, 1.1),
                 lights=[{"x": round(x_), "y": round(y_), "color": "#ffe9b0"} for (x_, y_) in lamps] if night else [])

# ------------------------------------------------------------------- 44. phòng chiếu tatami
def _tatami_floor(c, back_y, mat="#c2b47a", edge="#3e4a3a") -> Persp:
    P = Persp(f=1500, cx=W / 2, cy=back_y - 1500 * 1.4 / 5.6, cam_h=1.4)
    z0 = 1.4 * 1500 / (H + 40 - P.cy)
    c.drawRect(_R(0, back_y, W, H), fill(mat))
    x = -5.4
    while x < 5.4:                          # sợi dệt mảnh dọc z
        c.drawLine(*P.p(x, 0, z0), *P.p(x, 0, 5.6), stroke(shade(mat, -0.08), 2, 0.6))
        x += 0.06
    # chiếu 0.9 x 1.8: hàng ngang xen hàng dọc
    rows = [(5.6, 4.7, "h"), (4.7, 2.9, "v"), (2.9, 2.0, "h"), (2.0, 0.2, "v")]
    for (zf, zn, kind) in rows:
        if kind == "v":
            xx = -5.4
            while xx <= 5.4:
                path_fill(c, P.plane_y(0.001, xx - 0.025, xx + 0.025, max(zn, z0), zf), edge)
                xx += 0.9
        else:
            xx = -5.4
            while xx <= 5.4:
                path_fill(c, P.plane_y(0.001, xx - 0.025, xx + 0.025, max(zn, z0), zf), edge)
                xx += 1.8
        if zn > z0:
            path_fill(c, P.plane_y(0.001, -5.6, 5.6, zn - 0.025, zn + 0.025), edge)
    return P


def scene_phong_chieu_tatami(tod: str) -> Scene:
    night = tod != "day"
    baked: list = []
    s = new_surface()
    c = s.getCanvas()
    BY = 1380
    plaster, wood = "#d8cbb0", "#7a5a3c"
    c.drawRect(_R(0, 0, W, BY), fill(plaster))
    c.drawRect(_R(0, 0, W, 170), fill(shade(wood, -0.1)))
    for x in range(0, W, 120):
        c.drawLine(x, 0, x, 170, stroke(shade(wood, -0.3), 5))
    c.drawRect(_R(0, 170, W, 230), fill(wood))                      # dầm ngang
    c.drawRect(_R(0, BY - 40, W, BY), fill(shade(wood, -0.15)))     # chân tường
    for x in (60, 1460, 2620, 3760):
        c.drawRect(_R(x - 34, 170, x + 34, BY), fill(wood))
        c.drawRect(_R(x - 34, 170, x - 20, BY), fill(shade(wood, 0.12)))
    # cửa trượt fusuma (trái)
    for i, (l, r) in enumerate(((94, 776), (776, 1426))):
        c.drawRect(_R(l, 280, r, BY - 40), fill("#2e2418"))
        c.drawRect(_R(l + 22, 302, r - 22, BY - 62), fill("#ece2c8"))
        for (cx_, cy_, rr) in ((l + 200, 560, 160), (l + 420, 860, 220), (l + 150, 1100, 130)):
            c.drawPath(oval(cx_, cy_, rr * 1.6, rr * 0.35), fill("#d9cba8", 0.6))
        hx = r - 70 if i == 0 else l + 70
        c.drawPath(oval(hx, 800, 26, 34), fill("#5a4a36"))
        c.drawPath(oval(hx, 800, 16, 22), fill("#2e2418"))
    # cửa sổ: nửa trái shoji, nửa phải kính thấy trời
    wl, wt, wr, wb = 1640, 430, 2460, 1080
    c.drawRect(_R(wl - 30, wt - 30, wr + 30, wb + 30), fill(wood))
    mx = (wl + wr) / 2
    if night:
        vgrad(c, mx, wt, wr, wb, ["#0c1228", "#263058"])
        _moon(c, mx + 230, wt + 170, 55)
    else:
        vgrad(c, mx, wt, wr, wb, ["#9fbcd8", "#e4ecf0"])
        round_tree(c, mx + 280, wt + 420, 160, "#7f9a6a", "#5a4636", seed=3)
    reflections(c, mx, wt, wr, wb, 2, 0.12, seed=44)
    c.drawRect(_R(wl, wt, mx + 10, wb), fill("#f2ecdc" if not night else "#e8dcc0"))
    for i in range(1, 4):
        xx = wl + (mx - wl) * i / 4
        c.drawLine(xx, wt, xx, wb, stroke(wood, 8))
    for j in range(1, 6):
        yy = wt + (wb - wt) * j / 6
        c.drawLine(wl, yy, mx + 10, yy, stroke(wood, 8))
    c.drawRect(_R(mx, wt, mx + 20, wb), fill(wood))
    c.drawRect(_R(wl - 60, wb + 30, wr + 60, wb + 60), fill(shade(wood, 0.1)))
    # lịch treo tường: chỉ con số + lưới ô trống
    cl, ct, cr, cb = 2900, 560, 3260, 1050
    c.drawLine((cl + cr) / 2, ct - 60, (cl + cr) / 2, ct, stroke("#3a3a40", 4))
    c.drawCircle((cl + cr) / 2, ct - 62, 8, fill("#3a3a40"))
    c.drawRect(_R(cl, ct, cr, cb), fill("#f6f3ea"))
    c.drawRect(_R(cl, ct, cr, ct + 26), fill("#c8352e"))
    for i in range(9):
        c.drawCircle(cl + 30 + i * 38, ct + 12, 6, fill("#ece4cc"))
    text_center(c, "13", (cl + cr) / 2, ct + 130, 140, "#2b2d36", "extrabold")
    baked.append(_baked("13", (cl + cr) / 2, ct + 130, 140))
    for i in range(7):
        for j in range(4):
            x0 = cl + 24 + i * 45
            y0 = ct + 230 + j * 48
            c.drawRect(_R(x0, y0, x0 + 36, y0 + 38), fill("#e4ddcc" if (i + j) % 5 else "#f0c8c0"))
    # kệ thấp bên phải + bình hoa
    c.drawRect(_R(2840, 1150, 3560, BY - 40), fill(shade(wood, -0.2)))
    c.drawRect(_R(2820, 1130, 3580, 1160), fill(wood))
    c.drawPath(rrect(3380, 980, 3470, 1130, 30), fill("#3a5a6a"))
    for (dx, dy) in ((-30, -70), (10, -110), (40, -60)):
        c.drawLine(3425, 990, 3425 + dx, 980 + dy, stroke("#4a6a3a", 6))
        c.drawCircle(3425 + dx, 980 + dy, 18, fill("#e8a0a8"))
    P = _tatami_floor(c, BY)
    # bàn thấp tròn + đệm ngồi + ấm chén
    tx, ty = 1920, 1770
    c.drawPath(oval(tx, ty + 180, 640, 90), fill("#000000", 0.25))
    for dx in (-380, 380):
        c.drawRect(_R(tx + dx - 26, ty, tx + dx + 26, ty + 170), fill("#4a3020"))
    c.drawPath(oval(tx, ty + 18, 600, 120), fill("#4a3020"))
    c.drawPath(oval(tx, ty, 600, 120), fill("#7a4e30"))
    c.drawPath(oval(tx, ty - 6, 560, 100), fill("#8a5a38"))
    c.drawPath(rrect(tx - 90, ty - 140, tx + 70, ty - 20, 50), fill("#5a6a5a"))
    c.drawPath(capsule(tx + 60, ty - 100, tx + 150, ty - 120, 26, 16), fill("#5a6a5a"))
    c.drawPath(rrect(tx - 40, ty - 165, tx + 20, ty - 135, 12), fill("#4a584a"))
    for cx_ in (tx - 300, tx + 280):
        c.drawPath(rrect(cx_ - 45, ty - 70, cx_ + 45, ty - 10, 14), fill("#e8e2d4"))
    for (cx_, cy_) in ((tx - 820, 1980), (tx + 820, 1980)):
        c.drawPath(rrect(cx_ - 260, cy_ - 60, cx_ + 260, cy_ + 60, 40), fill("#8a3a4a"))
        c.drawPath(rrect(cx_ - 230, cy_ - 46, cx_ + 230, cy_ + 40, 34), fill("#a04a5a"))
    # đèn lồng giấy tròn treo trần
    lx, ly, lr = 1920, 420, 150
    c.drawLine(lx, 170, lx, ly - lr, stroke("#2a2622", 5))
    c.drawPath(rrect(lx - 40, ly - lr - 20, lx + 40, ly - lr + 10, 8), fill("#2a2622"))
    c.drawPath(oval(lx, ly, lr, lr * 0.92), fill("#fff3d6" if night else "#f2ecdc"))
    for k_ in range(-3, 4):
        c.drawPath(oval(lx, ly + k_ * lr * 0.24, lr * math.sqrt(max(0.0, 1 - (k_ * 0.26) ** 2)), 6),
                   fill(shade("#f2ecdc", -0.12), 0.6))
    c.drawPath(rrect(lx - 40, ly + lr * 0.88, lx + 40, ly + lr * 0.98, 8), fill("#2a2622"))
    if night:
        tint(s, "#4a5280", 0.55)
        glow(c, lx, ly, 900, "#ffe2b0", 0.4)
        glow(c, lx, ly, 260, "#fff3d6", 0.6)
        ellipse_glow(c, tx, ty, 900, 200, "#ffe2b0", 0.25)
        c.drawPath(oval(lx, ly, lr * 0.9, lr * 0.82), fill("#fff6e0", 0.5))
    else:
        c.drawPath(poly([(mx, wt), (wr, wt), (wr + 900, H), (mx + 300, H)]), lin_paint((mx, wt), (mx, H),
                   [("#fff6dc", 0.2), ("#fff6dc", 0.04)]))
    _vignette(c, 0.5 if night else 0.35)
    mid = s.makeImageSnapshot()
    slots = {"center": {"x": 1920, "y": 2040, "scale": 1.12}, "left": {"x": 1000, "y": 2040, "scale": 1.12},
             "right": {"x": 2850, "y": 2040, "scale": 1.12}, "door": {"x": 760, "y": 1700, "scale": 0.95},
             "seat_left": {"x": 1100, "y": 2000, "scale": 1.1}, "seat_right": {"x": 2740, "y": 2000, "scale": 1.1}}
    return Scene(None, mid, slots=slots, baked_signs=baked, floor_y=2040,
                 lights=[{"x": lx, "y": ly, "color": "#ffe2b0"}] if night else [])


# ------------------------------------------------------------------- 45. bếp quán mì nhỏ
def scene_bep_quan_mi(tod: str) -> Scene:
    baked: list = []
    s = new_surface()
    c = s.getCanvas()
    FB = 1720
    c.drawRect(_R(0, 0, W, FB), fill("#eef0ec"))
    _tile_grid(c, 0, 0, W, FB, 96, 96, "#c9d0cc", 4)
    rng = random.Random(45)
    for _ in range(10):
        c.drawPath(oval(rng.uniform(0, W), rng.uniform(300, 1200), rng.uniform(60, 180), rng.uniform(60, 200)),
                   fill("#a89a6a", rng.uniform(0.05, 0.1)))
    # dầm gỗ + thẻ thực đơn treo (chữ tiếng Anh nướng)
    c.drawRect(_R(0, 150, W, 230), fill("#6b4a32"))
    c.drawRect(_R(0, 150, W, 166), fill("#8a6a4a"))
    menu = ["RAMEN ¥800", "MISO ¥900", "GYOZA ¥400", "BEER"]
    for i, txt in enumerate(menu):
        cx_ = 2060 + i * 480
        l, r = cx_ - 220, cx_ + 220
        for xx in (l + 60, r - 60):
            c.drawLine(xx, 230, xx, 300, stroke("#3a2a1e", 5))
        c.drawPath(rrect(l, 300, r, 450, 12), fill("#e9dcb8"))
        c.drawPath(rrect(l + 10, 310, r - 10, 440, 8), stroke("#b89a68", 4))
        text_center(c, txt, cx_, 375, 64, "#2a1e16", "extrabold", max_w=390)
        baked.append(_baked(txt, cx_, 375, 64))
    # cửa ra vào + rèm noren "NOODLES"
    DL, DR, DT = 120, 820, 520
    c.drawRect(_R(DL - 40, DT - 40, DR + 40, FB), fill("#6b4a32"))
    vgrad(c, DL, DT, DR, FB, ["#1a1e2e", "#2a2e40"])
    c.drawRect(_R(DL - 60, DT - 20, DR + 60, DT + 6), fill("#4a3424"))
    nb = DT + 560
    for j in range(3):
        l = DL + j * (DR - DL) / 3 + 6
        r = DL + (j + 1) * (DR - DL) / 3 - 6
        c.drawRect(_R(l, DT + 6, r, nb), fill("#1f3a5e"))
        c.drawRect(_R(l, nb - 40, r, nb), fill("#2a4a72"))
    text_center(c, "NOODLES", (DL + DR) / 2, DT + 240, 104, "#f4f1e8", "extrabold", max_w=DR - DL - 60)
    baked.append(_baked("NOODLES", (DL + DR) / 2, DT + 240, 104))
    for j in range(1, 3):
        x = DL + j * (DR - DL) / 3
        c.drawRect(_R(x - 6, DT + 6, x + 6, nb), fill("#1a1e2e"))
    # máy hút khói + bếp + nồi nước dùng
    c.drawPath(poly([(1060, 560), (2060, 560), (2160, 820), (960, 820)]), fill("#b9c2c8"))
    c.drawRect(_R(960, 820, 2160, 860), fill("#8e989f"))
    c.drawRect(_R(1400, 0, 1720, 560), fill("#a9b2b8"))
    CT = 1300
    vgrad(c, 900, CT, 3620, FB, ["#bcc5cb", "#8e989f"])
    c.drawRect(_R(880, CT - 30, 3640, CT), fill("#dfe5e9"))
    c.drawRect(_R(880, CT - 30, 3640, CT - 22), fill("#f6f8f9"))
    for x in range(1200, 3600, 400):
        c.drawLine(x, CT + 20, x, FB, stroke("#7d878e", 5))
    for (px, pw, ph, col) in ((1250, 440, 420, "#c9d1d7"), (1880, 320, 260, "#aab2b8")):
        c.drawRect(_R(px - pw / 2 - 30, CT - 60, px + pw / 2 + 30, CT - 30), fill("#2b2d33"))
        c.drawRect(_R(px - pw / 2, CT - 60 - ph, px + pw / 2, CT - 60), fill(col))
        c.drawRect(_R(px - pw / 2, CT - 60 - ph, px - pw / 2 + 30, CT - 60), fill(shade(col, 0.15)))
        c.drawPath(oval(px, CT - 60 - ph, pw / 2, 26), fill(shade(col, -0.2)))
        c.drawPath(oval(px, CT - 60 - ph, pw / 2 - 20, 18), fill("#d9b46a"))
        for sx in (-1, 1):
            c.drawPath(rrect(px + sx * (pw / 2 + 10) - 24, CT - 60 - ph * 0.7, px + sx * (pw / 2 + 10) + 24,
                             CT - 60 - ph * 0.6, 10), fill("#6e7478"))
        for k_ in range(3):                   # hơi nước
            sx = px - pw * 0.25 + k_ * pw * 0.25
            p = skia.Path()
            p.moveTo(sx, CT - 80 - ph)
            p.cubicTo(sx - 60, CT - 200 - ph, sx + 60, CT - 280 - ph, sx - 10, CT - 400 - ph)
            c.drawPath(p, stroke("#ffffff", 26, 0.22))
    c.drawLine(1500, CT - 520, 1560, CT - 90, stroke("#6e7478", 14))       # muôi
    c.drawPath(oval(1560, CT - 90, 50, 20), fill("#6e7478"))
    # kệ trên + chồng bát viền đỏ
    SY = 860
    c.drawRect(_R(2300, SY, 3700, SY + 30), fill("#9aa4ab"))
    for x in (2360, 3640):
        c.drawLine(x, SY + 30, x - 40, SY + 130, stroke("#8e989f", 10))
    for i in range(5):
        bx = 2450 + i * 260
        for j in range(3 + (i % 2)):
            by = SY - j * 52
            quad(c, [(bx - 100, by - 50), (bx + 100, by - 50), (bx + 66, by), (bx - 66, by)], "#d9d9d0")
            quad(c, [(bx - 84, by - 26), (bx + 84, by - 26), (bx + 66, by), (bx - 66, by)], "#b9b9b0")
            c.drawRect(_R(bx - 100, by - 50, bx + 100, by - 40), fill("#c8352e"))
    for j in range(7):                                       # chồng đĩa trên quầy
        c.drawPath(oval(2400, CT - 34 - j * 18, 170, 26), fill("#e4e4dc"))
        c.drawPath(oval(2400, CT - 34 - j * 18, 170, 26), stroke("#c8352e", 6))
    for (x, col) in ((2700, "#e8c86a"), (2800, "#c8352e"), (2900, "#4a3a2a")):
        c.drawPath(rrect(x - 36, CT - 170, x + 36, CT - 30, 14), fill(col))
        c.drawRect(_R(x - 30, CT - 190, x + 30, CT - 170), fill("#2b2d33"))
    # bồn rửa + vòi
    SL, SR = 3000, 3560
    c.drawRect(_R(SL, CT - 30, SR, CT + 40), fill("#8e989f"))
    c.drawRect(_R(SL + 20, CT - 26, SR - 20, CT - 6), fill("#5a6066"))
    c.drawRect(_R(SR - 120, CT - 260, SR - 96, CT - 30), fill("#c9ccd2"))
    c.drawPath(capsule(SR - 108, CT - 250, SR - 230, CT - 250, 24, 20), fill("#c9ccd2"))
    c.drawLine(SR - 230, CT - 250, SR - 230, CT - 200, stroke("#c9ccd2", 18))
    # đèn treo ấm + sàn
    _persp_floor(c, FB, "#4a4440", "#3a3430", vx=1920, vy=900, spacing=300, dz=0.12)
    for lx in (1150, 2300):
        c.drawLine(lx, 230, lx, 520, stroke("#2a2622", 5))
        quad(c, [(lx - 40, 520), (lx + 40, 520), (lx + 120, 610), (lx - 120, 610)], "#2a2622")
        c.drawPath(oval(lx, 612, 90, 16), fill("#fff1c8"))
    tint(s, "#8a7a6a", 0.25)
    for lx in (1150, 2300):
        glow(c, lx, 620, 900, "#ffe2a0", 0.3)
        glow(c, lx, 615, 150, "#fff1c8", 0.6)
    _vignette(c, 0.5)
    mid = s.makeImageSnapshot()
    slots = {"cook": {"x": 2050, "y": 1640, "scale": 0.98, "clip_bottom": CT - 30},
             "center": {"x": 1920, "y": 2010, "scale": 1.1}, "left": {"x": 900, "y": 2010, "scale": 1.1},
             "right": {"x": 3000, "y": 2010, "scale": 1.1}, "sink": {"x": 3280, "y": 1640, "scale": 0.98, "clip_bottom": CT - 30},
             "door": {"x": 470, "y": 1880, "scale": 1.0}}
    return Scene(None, mid, slots=slots, baked_signs=baked, floor_y=2010,
                 lights=[{"x": 1150, "y": 612, "color": "#ffe2a0"}, {"x": 2300, "y": 612, "color": "#ffe2a0"}])


# ------------------------------------------------------------------- 46. phòng ngủ tối + TV CRT
def scene_phong_ngu_tv_cu(tod: str) -> Scene:
    s = new_surface()
    c = s.getCanvas()
    BY = 1460
    wall = "#8a8478"
    c.drawRect(_R(0, 0, W, BY), fill(wall))
    vgrad(c, 0, 0, W, 300, [shade(wall, -0.3), wall])
    c.drawRect(_R(0, BY - 40, W, BY), fill(shade(wall, -0.3)))
    rng = random.Random(46)
    for _ in range(8):
        c.drawPath(oval(rng.uniform(0, W), rng.uniform(200, 1300), rng.uniform(80, 240), rng.uniform(60, 200)),
                   fill("#4a4438", rng.uniform(0.03, 0.06)))
    # cửa sổ + rèm khép hờ
    wl, wt, wr, wb = 380, 380, 1260, 1080
    c.drawRect(_R(wl - 26, wt - 26, wr + 26, wb + 26), fill("#c9c2b0"))
    vgrad(c, wl, wt, wr, wb, ["#0c1228", "#22305a"])
    _moon(c, 1000, 560, 60, a=0.9)
    c.drawLine((wl + wr) / 2, wt, (wl + wr) / 2, wb, stroke("#c9c2b0", 16))
    for (l_, r_, tip) in ((wl - 120, wl + 230, wl + 260), (wr - 180, wr + 140, wr - 210)):
        p = skia.Path()
        p.moveTo(l_, wt - 70)
        p.lineTo(r_, wt - 70)
        p.quadTo(tip, (wt + wb) / 2, r_ - (r_ - l_) * 0.1, wb + 200)
        p.lineTo(l_, wb + 200)
        p.close()
        path_fill(c, p, "#4a5a7a")
        for j in range(4):
            xx = l_ + (r_ - l_) * (j + 0.5) / 4
            c.drawLine(xx, wt - 60, xx + 10, wb + 190, stroke("#3a4866", 10))
    c.drawRect(_R(wl - 220, wt - 90, wr + 220, wt - 66), fill("#5a5448"))
    # sàn gỗ
    _persp_floor(c, BY, "#5a4634", "#4a3828", vx=1920, vy=900, spacing=260, dz=0.1)
    # đệm futon gấp chồng góc phải
    fx, fb = 3420, BY + 120
    for j, col in enumerate(("#c9c2b8", "#5a7aa0", "#e8e2d4", "#a06a6a")):
        t = fb - (j + 1) * 120
        c.drawPath(rrect(fx - 360 + j * 6, t, fx + 360 - j * 6, t + 120, 40), fill(col))
        c.drawLine(fx - 330, t + 60, fx + 330, t + 60, stroke(shade(col, -0.15), 5))
    c.drawPath(rrect(fx - 220, fb - 560, fx + 200, fb - 480, 36), fill("#f0ebe0"))
    # tủ thấp + TV CRT
    CL, CR, CTp = 2180, 3080, 1300
    c.drawRect(_R(CL, CTp, CR, BY + 110), fill("#4a3424"))
    c.drawRect(_R(CL - 20, CTp - 20, CR + 20, CTp + 10), fill("#5e4430"))
    for x0 in (CL + 30, (CL + CR) / 2 + 10):
        c.drawRect(_R(x0, CTp + 50, x0 + (CR - CL) / 2 - 40, BY + 80), fill("#3a281c"))
        c.drawCircle(x0 + (CR - CL) / 4 - 20, CTp + 220, 14, fill("#8a7a5a"))
    TL, TR, TT, TB = 2300, 2960, 690, 1280
    c.drawPath(rrect(TL + 60, TT - 40, TR - 60, TB - 20, 40), fill("#4e4c52"))     # lưng TV
    c.drawPath(rrect(TL, TT, TR, TB, 34), fill("#8e8a86"))
    c.drawPath(rrect(TL + 10, TT + 10, TR - 10, TT + 40, 20), fill("#a8a49e"))
    sl, st_, sr, sb = TL + 60, TT + 60, TR - 170, TB - 70
    c.drawPath(rrect(sl - 16, st_ - 16, sr + 16, sb + 16, 40), fill("#2e2c30"))
    c.save()
    c.clipPath(rrect(sl, st_, sr, sb, 46))
    c.drawRect(_R(sl, st_, sr, sb), fill("#b8c4d4"))
    for _ in range(2600):                   # nhiễu tĩnh
        x, y = rng.uniform(sl, sr), rng.uniform(st_, sb)
        g = rng.choice(["#ffffff", "#e0e6f0", "#7a8698", "#4a5468", "#d0dae8"])
        c.drawRect(_R(x, y, x + rng.uniform(6, 22), y + rng.uniform(3, 7)), fill(g, 0.85))
    for y in range(int(st_), int(sb), 8):
        c.drawLine(sl, y, sr, y, stroke("#000000", 2, 0.12))
    c.drawRect(_R(sl, st_ + (sb - st_) * 0.55, sr, st_ + (sb - st_) * 0.6), fill("#ffffff", 0.25))
    c.restore()
    c.drawPath(rrect(sl, st_, sr, sb, 46), lin_paint((sl, st_), (sr, sb), [("#ffffff", 0.18), ("#ffffff", 0.0)]))
    for j in range(3):
        c.drawCircle(TR - 90, TT + 140 + j * 90, 26, fill("#4e4c52"))
    for j in range(6):
        c.drawLine(TR - 130, TT + 420 + j * 22, TR - 50, TT + 420 + j * 22, stroke("#5a585e", 6))
    c.drawLine(TL + 220, TT - 40, TL + 120, TT - 300, stroke("#5a585e", 8))
    c.drawLine(TL + 340, TT - 40, TL + 460, TT - 320, stroke("#5a585e", 8))
    # bàn thấp + cốc
    tx, ty = 1500, 1700
    c.drawRect(_R(tx - 420, ty, tx - 380, ty + 170), fill("#3a281c"))
    c.drawRect(_R(tx + 380, ty, tx + 420, ty + 170), fill("#3a281c"))
    c.drawRect(_R(tx - 470, ty - 40, tx + 470, ty), fill("#5e4430"))
    c.drawRect(_R(tx - 470, ty - 40, tx + 470, ty - 30), fill("#6e5440"))
    c.drawPath(rrect(tx + 120, ty - 140, tx + 200, ty - 40, 14), fill("#e8e2d4"))
    c.drawPath(rrect(tx - 260, ty - 70, tx - 60, ty - 40, 6), fill("#2b2d33"))         # điều khiển
    tint(s, "#3a4270", 0.68)
    scx, scy = (sl + sr) / 2, (st_ + sb) / 2
    glow(c, scx, scy, 1500, "#bcd4ff", 0.35)
    glow(c, scx, scy, 420, "#e8f0ff", 0.45)
    ellipse_glow(c, scx - 150, 1750, 1100, 260, "#bcd4ff", 0.22)
    glow(c, 1000, 560, 300, "#dfe8ff", 0.3)
    c.drawPath(poly([(wl, wt), (wr, wt), (wr + 700, H), (wl + 200, H)]), lin_paint((wl, wt), (wl, H),
               [("#c9d8ff", 0.12), ("#c9d8ff", 0.02)]))
    _vignette(c, 0.6)
    mid = s.makeImageSnapshot()
    slots = {"center": {"x": 1920, "y": 2040, "scale": 1.12}, "left": {"x": 900, "y": 2040, "scale": 1.12},
             "right": {"x": 2700, "y": 2040, "scale": 1.12}, "tv": {"x": 2400, "y": 1980, "scale": 1.05},
             "futon": {"x": 3300, "y": 2020, "scale": 1.1}}
    return Scene(None, mid, slots=slots, floor_y=2040, lights=[{"x": round(scx), "y": round(scy), "color": "#bcd4ff"}])


# =================================================================== LÔ 4 (docs/reference_batch4_analysis.md)
# 12 loại cảnh mới (bối cảnh thriller đô thị: trung tâm điện thoại, phố đêm, hầm xe, tiệm giặt, trung tâm dữ liệu...),
# vẽ GỐC bằng code. Không cắt/đồ lại khung tham khảo; không tên/logo thật. MỌI chữ nướng vào pixel là TIẾNG ANH
# (PHONE REPAIR, CASE SHOP, EXIT, B2, LAUNDRY 24H, RESTRICTED AREA...) và được ghi vào baked_signs -> profile.baked_text.
U4 = 200.0                       # px/mét trong toạ độ cục bộ của một mặt tiền (ki-ốt, máy giặt...)


def _quad_matrix(w: float, h: float, dst) -> skia.Matrix:
    """Ma trận phối cảnh đưa hình chữ nhật (0,0,w,h) vào tứ giác dst [TL, TR, BR, BL]."""
    m = skia.Matrix()
    m.setPolyToPoly([skia.Point(0, 0), skia.Point(w, 0), skia.Point(w, h), skia.Point(0, h)],
                    [skia.Point(*p) for p in dst])
    return m


class _Bake:
    """Ghi chữ nướng (kể cả chữ vẽ trong hệ toạ độ cục bộ đã chiếu phối cảnh) -> baked_signs px."""

    def __init__(self) -> None:
        self.items: list = []
        self.m: skia.Matrix | None = None

    def text(self, c, txt, cx, cy, size, col, weight="extrabold", max_w=None, neon=None, a=1.0) -> None:
        if neon:
            f = font(size, weight)
            tw = f.measureText(txt)
            sz = size * (max_w / tw) if (max_w and tw > max_w) else size
            f = font(sz, weight)
            tw = f.measureText(txt)
            p = fill(neon, 0.9 * a)
            p.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, sz * 0.22))
            c.drawString(txt, cx - tw / 2, cy + sz * 0.36, f, p)
        text_center(c, txt, cx, cy, size, col, weight, a=a, max_w=max_w)
        box = _baked(txt, cx, cy, size)["box"]
        if max_w:
            half = min((box[2] - box[0]) / 2, max_w / 2)
            box = [cx - half, box[1], cx + half, box[3]]
        if self.m is not None:
            pts = [self.m.mapXY(x, y) for (x, y) in ((box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3]))]
            box = [min(p.x() for p in pts), min(p.y() for p in pts), max(p.x() for p in pts), max(p.y() for p in pts)]
        self.items.append({"text": txt, "box": [round(v) for v in box]})


def _on_quad(c, bk: _Bake | None, w, h, dst, draw) -> None:
    """Vẽ draw(c) trong hệ cục bộ w×h rồi chiếu lên tứ giác dst."""
    m = _quad_matrix(w, h, dst)
    c.save()
    c.concat(m)
    c.clipRect(_R(0, 0, w, h), skia.ClipOp.kIntersect, True)
    if bk is not None:
        bk.m = m
    draw(c)
    if bk is not None:
        bk.m = None
    c.restore()


def _fire_ext(c, x, base, k) -> None:
    """Bình chữa cháy đỏ (x = tâm, base = đáy, k = px/mét)."""
    c.drawPath(rrect(x - 0.09 * k, base - 0.55 * k, x + 0.09 * k, base, 0.07 * k), fill("#d42e26"))
    c.drawRect(_R(x - 0.09 * k, base - 0.36 * k, x + 0.09 * k, base - 0.3 * k), fill("#f2ead8"))
    c.drawRect(_R(x - 0.03 * k, base - 0.66 * k, x + 0.03 * k, base - 0.55 * k), fill("#2b2d33"))
    c.drawLine(x, base - 0.62 * k, x + 0.13 * k, base - 0.58 * k, stroke("#2b2d33", max(2.0, 0.025 * k)))
    c.drawPath(capsule(x + 0.1 * k, base - 0.5 * k, x + 0.14 * k, base - 0.2 * k, 0.018 * k, 0.012 * k), fill("#1d1f24"))
    c.drawRect(_R(x - 0.06 * k, base - 0.5 * k, x - 0.035 * k, base - 0.06 * k), fill("#ff6a5a", 0.6))


def _exit_box(c, bk: _Bake, cx, cy, w, lit=True) -> None:
    h = w * 0.36
    c.drawPath(rrect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2, h * 0.12), fill("#f4f6f4"))
    c.drawPath(rrect(cx - w / 2 + h * 0.08, cy - h / 2 + h * 0.08, cx + w / 2 - h * 0.08, cy + h / 2 - h * 0.08, h * 0.08),
               fill("#19a85a" if lit else "#2a6a46"))
    bk.text(c, "EXIT", cx, cy, h * 0.5, "#ffffff", max_w=w * 0.8)
    if lit:
        glow(c, cx, cy, w * 1.2, "#3ee08f", 0.35)


# ------------------------------------------------------------------- 47. tầng trung tâm điện thoại (4 biến thể)
KIOSKS = [("PHONE REPAIR", "repair", "#2fc4ff"), ("CASE SHOP", "cases", "#ff4fa3"), ("SCREEN FILM", "film", "#3ee08f"),
          ("LAPTOP REPAIR", "laptop", "#ffb02e"), ("TOP-UP", "topup", "#b47bff")]


def _phone(c, x, y, w, h, body="#22252c", screen="#3a4a6a", cracked=False, lit=False) -> None:
    c.drawPath(rrect(x, y, x + w, y + h, w * 0.16), fill(body))
    c.drawPath(rrect(x + w * 0.08, y + h * 0.07, x + w * 0.92, y + h * 0.93, w * 0.1), fill("#7ac8ff" if lit else screen))
    if cracked:
        cx_, cy_ = x + w * 0.62, y + h * 0.35
        for (dx, dy) in ((-0.5, -0.25), (0.3, -0.3), (0.3, 0.5), (-0.4, 0.45), (0.05, 0.6)):
            c.drawLine(cx_, cy_, cx_ + dx * w, cy_ + dy * h * 0.6, stroke("#e8f0ff", max(1.0, w * 0.03), 0.85))


def _kiosk_wall(c, bk: _Bake, kind, l, t, r, b, rng, detail) -> None:
    """Tường trong ki-ốt (giữa bảng hiệu và quầy) theo loại cửa hàng."""
    if kind == "cases":
        c.drawRect(_R(l, t, r, b), fill("#ece6da"))
        y = t + 10
        while y < b - 10:
            x = l + 10
            while x < r - 10:
                c.drawCircle(x, y, 1.8, fill("#c9c0ae"))
                x += 14
            y += 14
        cols = ["#ff4fa3", "#2fc4ff", "#f3c94e", "#4fa35a", "#ff7a3a", "#b47bff", "#ffffff", "#22252c", "#e83a3a"]
        y = t + 18
        while y + 70 < b:
            x = l + 16
            while x + 34 < r:
                c.drawLine(x + 17, y - 8, x + 17, y + 2, stroke("#8a8f98", 3))
                c.drawPath(rrect(x, y, x + 34, y + 62, 7), fill(rng.choice(cols)))
                c.drawCircle(x + 9, y + 10, 4, fill("#000000", 0.35))
                x += 46
            y += 84
    elif kind == "repair":
        c.drawRect(_R(l, t, r, b), fill("#e6ebef"))
        sh_r = r - (150 if detail else 0)
        for sy in (t + 100, t + 210, b - 6):
            c.drawRect(_R(l + 8, sy, sh_r - 8, sy + 8), fill("#9aa3ad"))
            x = l + 22
            while x + 30 < sh_r - 10:
                _phone(c, x, sy - 66, 30, 62, cracked=rng.random() < 0.6, lit=rng.random() < 0.15)
                x += 44
        if detail:
            pl, pt_, pr, pb = r - 140, t + 10, r - 6, t + 200
            c.drawPath(rrect(pl, pt_, pr, pb, 6), fill("#1d2230"))
            bk.text(c, "REPAIR PRICES", (pl + pr) / 2, pt_ + 22, 15, "#ffd25a", max_w=pr - pl - 12)
            for i, row in enumerate(("SCREEN 900", "BATTERY 450", "CHARGE PORT 300", "DATA RECOVERY 500")):
                bk.text(c, row, (pl + pr) / 2, pt_ + 60 + i * 36, 12, "#f4f6f8", "bold", max_w=pr - pl - 14)
    elif kind == "film":
        c.drawRect(_R(l, t, r, b), fill("#e2eef0"))
        y = t + 14
        while y + 60 < b:
            x = l + 14
            while x + 40 < r:
                c.drawPath(rrect(x, y, x + 40, y + 58, 4), fill("#bfe4f2"))
                c.drawPath(rrect(x + 6, y + 8, x + 34, y + 50, 3), fill("#ffffff", 0.7))
                c.drawRect(_R(x, y + 48, x + 40, y + 58), fill("#3ee08f"))
                x += 52
            y += 74
    elif kind == "laptop":
        c.drawRect(_R(l, t, r, b), fill("#ebe6dc"))
        for sy in (t + 150, b - 6):
            c.drawRect(_R(l + 8, sy, r - 8, sy + 8), fill("#9aa3ad"))
            x = l + 20
            while x + 90 < r:
                c.drawPath(rrect(x, sy - 80, x + 90, sy - 10, 5), fill("#2b2d33"))
                c.drawRect(_R(x + 6, sy - 74, x + 84, sy - 16), fill(rng.choice(["#3a78c2", "#2fc4ff", "#3a4a6a", "#5a6a8a"])))
                quad(c, [(x - 6, sy - 10), (x + 96, sy - 10), (x + 104, sy), (x - 14, sy)], "#9aa0a8")
                x += 112
    else:   # topup
        c.drawRect(_R(l, t, r, b), fill("#efe8f4"))
        cols = ["#b47bff", "#2fc4ff", "#ff4fa3", "#f3c94e", "#4fa35a"]
        y = t + 16
        while y + 40 < b:
            x = l + 14
            while x + 52 < r:
                col = rng.choice(cols)
                c.drawPath(rrect(x, y, x + 52, y + 34, 4), fill(col))
                c.drawPath(rrect(x + 6, y + 8, x + 18, y + 24, 2), fill("#f3d27a"))
                x += 62
            y += 50


def _kiosk_local(c, bk: _Bake, w, h, text, kind, ncol, closed, seed, detail=False) -> None:
    """Mặt tiền 1 ki-ốt (toạ độ cục bộ, U4 px/m): bảng hiệu neon, tường hàng, quầy kính; closed -> cửa cuốn."""
    rng = random.Random(seed)
    SB = 0.55 * U4
    CT = h - 1.05 * U4
    if not closed:
        vgrad(c, 0, SB, w, h, ["#fbfaf6", "#e6e2da"])
        _kiosk_wall(c, bk, kind, 26, SB + 14, w - 26, CT - 6, rng, detail)
        c.drawRect(_R(18, CT, w - 18, h), fill("#dde6ec"))
        vgrad(c, 24, CT + 18, w - 24, h - 24, ["#d6ecf6", "#a6c6d8"])
        for sy in (CT + 70, CT + 140):
            c.drawRect(_R(24, sy, w - 24, sy + 4), fill("#ffffff", 0.7))
            x = 40
            while x + 30 < w - 40:
                col = rng.choice(["#22252c", "#ff4fa3", "#2fc4ff", "#f3c94e", "#ffffff", "#4fa35a"])
                c.drawPath(rrect(x, sy - 40, x + 24, sy - 2, 4), fill(col))
                x += rng.uniform(34, 60)
        reflections(c, 24, CT + 18, w - 24, h - 24, 3, 0.22, seed=seed)
        c.drawRect(_R(14, CT - 10, w - 14, CT + 16), fill("#f6f8fa"))
        c.drawRect(_R(14, CT + 12, w - 14, CT + 18), fill("#b9c2ca"))
        c.drawRect(_R(18, h - 22, w - 18, h), fill("#4a4e58"))
        if detail:
            # mặt quầy sửa chữa: thảm cắt xanh, đèn bàn, cốc bút, điện thoại mở nắp, tua vít
            quad(c, [(150, CT - 10), (430, CT - 10), (420, CT - 22), (160, CT - 22)], "#2f8a5a")
            _phone(c, 210, CT - 32, 70, 22, body="#3a3e48", screen="#5a6070")
            c.drawLine(330, CT - 26, 400, CT - 30, stroke("#d8423a", 6))
            c.drawLine(395, CT - 30, 420, CT - 31, stroke("#c9ccd2", 3))
            lx = 480
            c.drawPath(oval(lx, CT - 14, 34, 8), fill("#2b2d33"))
            c.drawLine(lx, CT - 16, lx + 20, CT - 120, stroke("#2b2d33", 7))
            c.drawLine(lx + 20, CT - 120, lx - 50, CT - 165, stroke("#2b2d33", 7))
            quad(c, [(lx - 30, CT - 180), (lx - 80, CT - 176), (lx - 96, CT - 136), (lx - 36, CT - 140)], "#2b2d33")
            glow(c, lx - 66, CT - 136, 90, "#fff4d0", 0.5)
            c.drawPath(rrect(90, CT - 60, 124, CT - 10, 5), fill("#3a78c2"))
            for (dx, col) in ((-8, "#d8423a"), (2, "#2b2d33"), (10, "#f3c94e")):
                c.drawLine(107 + dx, CT - 58, 107 + dx * 2, CT - 92, stroke(col, 4))
            for i in range(3):
                _phone(c, 560 + i * 34, CT - 62, 26, 50, cracked=True)
    else:
        vgrad(c, 0, SB, w, h, ["#a4aab2", "#868c96"])
        y = SB + 12
        while y < h - 20:
            c.drawLine(0, y, w, y, stroke("#6e747e", 3))
            c.drawLine(0, y + 3, w, y + 3, stroke("#c2c8d0", 1.5, 0.6))
            y += 16
        c.drawRect(_R(0, h - 26, w, h), fill("#5a606a"))
        c.drawPath(rrect(w / 2 - 22, h - 22, w / 2 + 22, h - 8, 4), fill("#2b2d33"))
        c.drawPath(rrect(w * 0.8 - 12, h - 50, w * 0.8 + 12, h - 24, 4), fill("#c9a440"))
        c.drawCircle(w * 0.8, h - 54, 9, stroke("#9aa0a8", 4))
    # bảng hiệu + khung nhôm
    c.drawRect(_R(0, 0, w, SB), fill("#15171e"))
    c.drawRect(_R(0, SB - 8, w, SB), fill(ncol if not closed else "#3a3e48"))
    if closed:
        bk.text(c, text, w / 2, SB * 0.48, SB * 0.42, shade(ncol, -0.45), max_w=w * 0.84)
    else:
        bk.text(c, text, w / 2, SB * 0.48, SB * 0.42, "#ffffff", max_w=w * 0.84, neon=ncol)
    for x0 in (0, w - 16):
        c.drawRect(_R(x0, 0, x0 + 16, h), fill("#3a3e48"))


def _mall_shell(P: Persp, s, XW, YT, KH, Z0, ZB, bk, closed, sides=(-1, 1), seed=47, kz0=1.0, step=3.7, kw=3.4, open_left=False) -> list:
    """Hành lang trung tâm thương mại 1 điểm tụ, ki-ốt hai bên. Trả về [(cx, cy, col)] ánh neon."""
    c = s.getCanvas()
    rng = random.Random(seed)
    path_fill(c, P.plane_y(YT, -XW, XW, Z0, ZB), "#eef0f2")
    path_fill(c, P.plane_y(0, -XW, XW, Z0, ZB), "#ece6da")
    _floor_tiles(c, P, -XW, XW, Z0, ZB, 0.8, "#d8d0c0")
    path_fill(c, P.face_z(ZB, -XW, XW, 0, YT), "#e3e6ea")
    for sd in ((1,) if open_left else (-1, 1)):
        path_fill(c, P.wall_x(sd * XW, Z0, ZB, KH, YT), "#f6f6f4" if sd < 0 else "#efefed")
        path_fill(c, P.wall_x(sd * XW, Z0, ZB, KH, KH + 0.08), "#c9ccd2")
        if sd not in sides:
            path_fill(c, P.wall_x(sd * XW, Z0, ZB, 0, KH), "#e8eaec")
    # cửa thoát hiểm cuối hành lang + biển EXIT + bình chữa cháy
    path_fill(c, P.face_z(ZB - 0.01, -0.8, 0.8, 0, 2.2), "#c9ccd2")
    path_fill(c, P.face_z(ZB - 0.02, -0.72, 0.72, 0, 2.12), "#8a9098")
    c.drawLine(*P.p(0, 0, ZB - 0.02), *P.p(0, 2.12, ZB - 0.02), stroke("#6a7078", 4))
    ex, ey = P.p(0, 2.55, ZB - 0.02)
    _exit_box(c, bk, ex, ey, 0.9 * P.f / ZB, lit=True)
    fx, fb = P.p(1.2, 0, ZB - 0.05)
    _fire_ext(c, fx, fb, P.f / ZB)
    # dải đèn trần
    for xx in (-1.4, 1.4):
        path_fill(c, P.plane_y(YT - 0.01, xx - 0.12, xx + 0.12, Z0, ZB), "#ffffff" if not closed else "#9aa0aa")
    z = 2.0
    while z < ZB:
        cx_, cy_ = P.p(0, YT - 0.01, z)
        c.drawPath(oval(cx_, cy_, 0.18 * P.f / z, 0.05 * P.f / z), fill("#fffbe8" if not closed else "#7a8090"))
        z += 3.0
    neons = []
    for sd in sides:
        x = sd * XW
        z = kz0
        i = rng.randrange(len(KIOSKS))
        while z + kw < ZB - 0.5:
            text, kind, ncol = KIOSKS[i % len(KIOSKS)]
            i += 1
            if sd < 0:
                dst = [P.p(x, KH, z), P.p(x, KH, z + kw), P.p(x, 0, z + kw), P.p(x, 0, z)]
            else:
                dst = [P.p(x, KH, z + kw), P.p(x, KH, z), P.p(x, 0, z), P.p(x, 0, z + kw)]
            _on_quad(c, bk, kw * U4, KH * U4, dst,
                     lambda cc, t=text, k=kind, n=ncol, sd_=rng.randrange(9999): _kiosk_local(cc, bk, kw * U4, KH * U4, t, k, n,
                                                                                        closed, sd_))
            path_fill(c, P.wall_x(x, z + kw, z + step, 0, KH), "#c9ccd2")
            if not closed:
                path_fill(c, P.quad([(x, 0.002, z + 0.3), (x - sd * 0.9, 0.002, z + 0.6), (x - sd * 0.9, 0.002, z + kw - 0.3),
                                     (x, 0.002, z + kw - 0.6)]), ncol, 0.10)
            neons.append((*P.p(x, KH - 0.25, z + kw / 2), ncol, P.f / (z + kw / 2)))
            z += step
    return neons


def _mall_corridor(tod: str) -> Scene:
    closed = tod == "closed"
    P = Persp(f=1500, cx=W / 2, cy=1000, cam_h=1.6)
    s = new_surface()
    c = s.getCanvas()
    bk = _Bake()
    neons = _mall_shell(P, s, 3.2, 4.4, 3.2, 0.8, 40.0, bk, closed)
    if closed:
        tint(s, "#4a5480", 0.6)
        for z in (6.0, 15.0, 27.0):
            cx_, cy_ = P.p(0, 0, z)
            ellipse_glow(c, cx_, cy_, 1.6 * P.f / z, 0.4 * P.f / z, "#c9d4ff", 0.35)
            hx, hy = P.p(0, 4.39, z)
            glow(c, hx, hy, 0.6 * P.f / z, "#dfe8ff", 0.5)
        ex, ey = P.p(0, 2.55, 39.9)
        glow(c, ex, ey, 260, "#3ee08f", 0.5)
        _vignette(c, 0.65)
    else:
        for (nx, ny, col, k) in neons:
            glow(c, nx, ny, 1.2 * k, col, 0.25)
        glow(c, P.cx, P.cy - 120, 1100, "#ffffff", 0.45)
        c.drawRect(_R(0, 0, W, H), fill("#ffffff", 0.06))
        _vignette(c, 0.25)
    mid = s.makeImageSnapshot()
    slots = {"center": P.slot(0, 3.2), "left": P.slot(-1.3, 3.6), "right": P.slot(1.3, 3.6),
             "far": P.slot(0.2, 10.0), "very_far": P.slot(-0.3, 20.0)}
    return Scene(None, mid, slots=slots, baked_signs=bk.items, floor_y=slots["center"]["y"],
                 lights=[{"x": round(P.cx), "y": round(P.p(0, 2.55, 39.9)[1]), "color": "#3ee08f"}] if closed else [])


def _mall_angle() -> Scene:
    P = Persp(f=1450, cx=880, cy=1000, cam_h=1.6)
    s = new_surface()
    c = s.getCanvas()
    bk = _Bake()
    # khoảng thông tầng bên trái: mặt tiền tầng đối diện xa + lan can kính
    vgrad(c, 0, 0, W, H, ["#f4f6f8", "#e2e6ea"])
    XA = -8.0
    for lvl, (y0, y1) in enumerate(((-4.0, -0.6), (0.0, 3.2), (4.4, 7.6), (8.8, 12.0))):
        path_fill(c, P.wall_x(XA, 1.0, 60.0, y1, y1 + 0.9), "#f2f2f0")
        path_fill(c, P.wall_x(XA, 1.0, 60.0, y1 + 0.9, y1 + 1.0), "#c9ccd2")
        z = 2.0
        rng = random.Random(470 + lvl)
        while z < 58:
            col = rng.choice(KIOSKS)[2]
            path_fill(c, P.wall_x(XA, z, z + 3.2, y0, y1), "#f8f6f0")
            path_fill(c, P.wall_x(XA, z, z + 3.2, y1 - 0.5, y1), "#1a1c22")
            path_fill(c, P.wall_x(XA, z + 0.3, z + 2.9, y1 - 0.36, y1 - 0.16), col, 0.85)
            z += 3.6
    c.drawRect(_R(0, 0, W, H), fill("#ffffff", 0.35))
    neons = _mall_shell(P, s, 2.4, 4.4, 3.2, 0.8, 60.0, bk, False, sides=(1,), seed=471, kz0=0.6, open_left=True)
    # bỏ tường trái: vẽ lại sàn hành lang + lan can kính
    path_fill(c, P.quad([(-2.4, 0, 0.8), (-2.4, 0, 60), (-2.42, -0.4, 60), (-2.42, -0.4, 0.8)]), "#c9ccd2")
    path_fill(c, P.wall_x(-2.4, 0.8, 60.0, 0.0, 1.05), "#cfe6ee", 0.35)
    z = 1.0
    while z < 60:
        c.drawLine(*P.p(-2.4, 0, z), *P.p(-2.4, 1.05, z), stroke("#b9c2ca", max(2.0, 30 / z)))
        z += 1.6
    c.drawLine(*P.p(-2.4, 1.08, 0.8), *P.p(-2.4, 1.08, 60), stroke("#8a9098", 10))
    for (nx, ny, col, k) in neons:
        glow(c, nx, ny, 1.2 * k, col, 0.25)
    glow(c, P.cx, P.cy - 100, 900, "#ffffff", 0.45)
    _vignette(c, 0.25)
    mid = s.makeImageSnapshot()
    slots = {"center": P.slot(0.2, 3.4), "left": P.slot(-1.2, 3.2), "right": P.slot(1.4, 3.4),
             "kiosk": P.slot(1.9, 5.5), "far": P.slot(0.0, 10.0)}
    return Scene(None, mid, slots=slots, baked_signs=bk.items, floor_y=slots["center"]["y"])


def _mall_kiosk_close() -> Scene:
    bk = _Bake()
    s = new_surface()
    c = s.getCanvas()
    FL, k = 2050, 600.0
    vgrad(c, 0, 0, W, FL, ["#f6f6f4", "#e9e9e6"])
    sc = k / U4
    kw, kh = 3.4 * U4, 3.2 * U4
    for (cx_, i, sd) in ((1920, 0, 4701), (1920 - 3.6 * k, 1, 4702), (1920 + 3.6 * k, 4, 4703)):
        text, kind, ncol = KIOSKS[i]
        l = cx_ - kw * sc / 2
        dst = [(l, FL - kh * sc), (l + kw * sc, FL - kh * sc), (l + kw * sc, FL), (l, FL)]
        _on_quad(c, bk, kw, kh, dst, lambda cc, t=text, kd=kind, n=ncol, sd_=sd, ct=cx_: _kiosk_local(
            cc, bk, kw, kh, t, kd, n, False, sd_, detail=(ct == 1920)))
        glow(c, cx_, FL - kh * sc + 0.27 * k, 1.6 * k, ncol, 0.22)
    for x in (1920 - 1.8 * k - 0.1 * k, 1920 + 1.8 * k - 0.1 * k):
        c.drawRect(_R(x, FL - 3.2 * k, x + 0.2 * k, FL), fill("#c9ccd2"))
    _persp_floor(c, FL, "#ece6da", "#d4ccbc", vx=1920, vy=1000, spacing=320, dz=0.1)
    ellipse_glow(c, 1920, FL + 80, 1500, 120, "#2fc4ff", 0.18)
    glow(c, 1920, 300, 1500, "#ffffff", 0.3)
    _vignette(c, 0.3)
    mid = s.makeImageSnapshot()
    CT = round(FL - 1.05 * k)
    slots = {"tech": {"x": 1700, "y": FL - 40, "scale": 1.25, "clip_bottom": CT},
             "center": {"x": 1920, "y": 2130, "scale": 1.45}, "left": {"x": 700, "y": 2130, "scale": 1.45},
             "right": {"x": 3150, "y": 2130, "scale": 1.45}}
    return Scene(None, mid, slots=slots, baked_signs=bk.items, floor_y=2130,
                 lights=[{"x": 1920 + 300, "y": CT - 140 * 3, "color": "#fff4d0"}])


def scene_tang_trung_tam_dien_thoai(tod: str) -> Scene:
    if tod == "angle":
        return _mall_angle()
    if tod in ("corridor", "closed"):
        return _mall_corridor(tod)
    return _mall_kiosk_close()


# ------------------------------------------------------------------- 48. sảnh thang cuốn + thang máy
def scene_sanh_thang_cuon(tod: str) -> Scene:
    bk = _Bake()
    s = new_surface()
    c = s.getCanvas()
    FL = 1720
    vgrad(c, 0, 0, W, FL, ["#eceeef", "#e2e2de"])
    c.drawRect(_R(0, 0, W, 190), fill("#f8f8f6"))
    c.drawRect(_R(0, 186, W, 200), fill("#c9ccd2"))
    for x in range(260, W, 520):
        c.drawPath(oval(x, 192, 60, 12), fill("#fffbe8"))
        glow(c, x, 200, 260, "#fff8e0", 0.35)
    for x in range(0, W, 640):
        c.drawLine(x, 200, x, FL, stroke("#d6d8da", 4))
    # tầng trên (trái) + thang cuốn đi lên sang trái
    c.drawRect(_R(0, 330, 760, 430), fill("#d4d6da"))
    c.drawRect(_R(0, 420, 760, 440), fill("#9aa0a8"))
    c.drawRect(_R(0, 160, 760, 330), fill("#cfe6ee", 0.35))
    c.drawLine(0, 160, 760, 160, stroke("#8a9098", 12))
    x0, y0, x1, y1 = 1780, FL, 640, 420
    th = 260
    quad(c, [(x0 + 240, y0), (x0, y0), (x1, y1), (x1 - 240, y1), (x1 - 240, y1 + th), (x1 + 40, y1 + th),
             (x0 - 40, y0 + 10), (x0 + 240, y0 + 10)], "#b9c0c8")
    quad(c, [(x0, y0 - 6), (x1, y1 - 6), (x1, y1 + 60), (x0, y0 + 60 - 6)], "#9aa2ac")
    n = 22
    for i in range(n):                         # bậc thang răng cưa
        t0 = i / n
        ax, ay = x0 + (x1 - x0) * t0, y0 + (y1 - y0) * t0
        bx = x0 + (x1 - x0) * (t0 + 1 / n)
        c.drawLine(ax, ay - 6, bx, ay - 6, stroke("#5a606a", 6))
    gl = 330                                   # vách kính + tay vịn đen
    quad(c, [(x0 + 120, y0 - 10), (x1 - 120, y1 - 10), (x1 - 120, y1 - gl), (x0 + 120, y0 - gl)], "#cfe6ee", 0.35)
    for t0 in (0.15, 0.4, 0.65, 0.9):
        ax, ay = x0 + (x1 - x0) * t0, y0 + (y1 - y0) * t0
        c.drawLine(ax, ay - 10, ax, ay - gl, stroke("#b9c2ca", 5))
    p = skia.Path()
    p.moveTo(x0 + 240, y0 - gl + 10)
    p.lineTo(x0 + 120, y0 - gl)
    p.lineTo(x1 - 120, y1 - gl)
    p.lineTo(x1 - 260, y1 - gl + 10)
    c.drawPath(p, stroke("#1d1f24", 22))
    c.drawPath(capsule(x0 + 120, y0 - gl, x0 + 250, y0 - 60, 14, 14), fill("#1d1f24"))
    c.drawRect(_R(x0 - 40, y0 - 4, x0 + 260, y0 + 14), fill("#c9a440"))
    # thang máy inox
    EL, ER, ET = 2080, 2780, 560
    c.drawRect(_R(EL - 70, ET - 70, ER + 70, FL), fill("#b9c0c8"))
    c.drawRect(_R(EL - 70, ET - 70, ER + 70, ET - 54), fill("#d9dee4"))
    for (l, r) in ((EL, (EL + ER) / 2), ((EL + ER) / 2, ER)):
        hgrad(c, l, ET, r, FL, ["#d4d9df", "#aab2bc", "#cfd5db"])
        reflections(c, l, ET, r, FL, 2, 0.12, seed=int(l))
    c.drawLine((EL + ER) / 2, ET, (EL + ER) / 2, FL, stroke("#6e747e", 6))
    c.drawPath(rrect((EL + ER) / 2 - 130, ET - 220, (EL + ER) / 2 + 130, ET - 100, 14), fill("#15171e"))
    bk.text(c, "3", (EL + ER) / 2 - 40, ET - 160, 80, "#ff5a3a")
    quad(c, [((EL + ER) / 2 + 50, ET - 130), ((EL + ER) / 2 + 110, ET - 130), ((EL + ER) / 2 + 80, ET - 190)], "#ff5a3a")
    c.drawPath(rrect(ER + 130, 1040, ER + 210, 1240, 12), fill("#c9ced4"))
    for (yy, up) in ((1100, True), (1180, False)):
        c.drawCircle(ER + 170, yy, 26, fill("#f4f6f8"))
        c.drawCircle(ER + 170, yy, 26, stroke("#8a9098", 4))
        quad(c, [(ER + 156, yy + (8 if up else -8)), (ER + 184, yy + (8 if up else -8)), (ER + 170, yy + (-10 if up else 10))],
             "#2b2d33")
    bk.text(c, "3F", ER + 170, 960, 60, "#5a606a")
    # hộp đèn quảng cáo dọc: vòng sáng, không chữ
    AL, AR, AT, AB = 3080, 3620, 420, 1660
    c.drawPath(rrect(AL - 24, AT - 24, AR + 24, AB + 24, 18), fill("#2b2d33"))
    vgrad(c, AL, AT, AR, AB, ["#0c1030", "#1a1450", "#0c1030"])
    acx, acy, ar = (AL + AR) / 2, AT + (AB - AT) * 0.42, 190
    glow(c, acx, acy, ar * 2.4, "#6be0ff", 0.45)
    c.drawCircle(acx, acy, ar, stroke("#bff4ff", 34))
    c.drawCircle(acx, acy, ar, stroke("#6be0ff", 60, 0.35))
    c.drawCircle(acx, acy, ar * 0.55, stroke("#c79bff", 14, 0.8))
    for j in range(3):
        c.drawPath(rrect(AL + 80, AB - 330 + j * 80, AR - 80 - j * 90, AB - 296 + j * 80, 14), fill("#6be0ff", 0.5 - j * 0.12))
    # chậu cây + biển EXIT treo
    for px in (1960, 2980):
        c.drawPath(rrect(px - 90, FL - 220, px + 90, FL, 20), fill("#e8e4dc"))
        for i in range(7):
            a = -math.pi / 2 + (i - 3) * 0.32
            c.drawPath(capsule(px, FL - 220, px + math.cos(a) * 220, FL - 220 + math.sin(a) * 300, 22, 6), fill("#3f8a52"))
    c.drawLine(1650, 200, 1650, 290, stroke("#8a9098", 6))
    _exit_box(c, bk, 1650, 340, 260)
    _persp_floor(c, FL, "#f0ebe2", "#dcd4c6", vx=1920, vy=1000, spacing=320, dz=0.1)
    ellipse_glow(c, (AL + AR) / 2, FL + 160, 500, 90, "#6be0ff", 0.25)
    for xx in (2240, 2620):
        c.drawPath(rrect(xx - 140, FL, xx + 140, FL + 300, 10),
                   lin_paint((xx, FL), (xx, FL + 300), [("#b9c0c8", 0.35), ("#b9c0c8", 0.0)]))
    glow(c, 1920, 500, 1700, "#ffffff", 0.28)
    _vignette(c, 0.25)
    mid = s.makeImageSnapshot()
    slots = {"center": {"x": 1700, "y": 2010, "scale": 1.1}, "left": {"x": 800, "y": 2010, "scale": 1.1},
             "right": {"x": 3000, "y": 2010, "scale": 1.1}, "elevator": {"x": 2430, "y": 1760, "scale": 0.98},
             "escalator": {"x": 1350, "y": 1240, "scale": 0.9}}
    return Scene(None, mid, slots=slots, baked_signs=bk.items, floor_y=2010,
                 lights=[{"x": round(acx), "y": round(acy), "color": "#6be0ff"}])


# ------------------------------------------------------------------- 49. phố nhà phố về đêm (+ mưa)
STREET_SIGNS = [("CAFE", "#c8532e"), ("HOTEL", "#2f5fa0"), ("PHARMACY", "#1f9a5a"), ("NOODLES", "#d23a2e"),
                ("BARBER", "#3a4a8a"), ("CLOTHES", "#b0428a"), ("GOLD", "#b8862a"), ("MINIMART", "#1f7a6a"),
                ("MASSAGE", "#7a3aa0")]


def _rain(c, n, seed, a=0.35, l=0, t=0, r=W, b=H, col="#cfdcff", slant=0.18) -> None:
    rng = random.Random(seed)
    for _ in range(n):
        x, y = rng.uniform(l - 200, r), rng.uniform(t, b)
        ln = rng.uniform(40, 140)
        c.drawLine(x, y, x + ln * slant, y + ln, stroke(col, rng.choice([1.5, 2.0, 3.0]), rng.uniform(0.3, 1.0) * a))


def _street_reflect(c, x, top, w, col, length, a=0.35) -> None:
    """Vệt phản chiếu dọc của nguồn sáng trên mặt đường ướt."""
    p = lin_paint((0, top), (0, top + length), [(col, a), (col, 0.0)])
    p.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, w * 0.2))
    c.drawRect(_R(x - w / 2, top, x + w / 2, top + length), p)


def scene_pho_nha_pho_dem(tod: str) -> Scene:
    rain = tod == "rain"
    bk = _Bake()
    sf = new_surface()
    c = sf.getCanvas()
    _night_sky(c, 0, 1300, seed=49, top="#070b1c" if rain else "#0b1230", bottom="#2a2a4a" if rain else "#3a3060",
               n_stars=0 if rain else 140)
    _skyline(c, 1000, 491, "#141a30", 200, 620, lit="#ffd08a", lit_p=0.08, beacons=True)
    _skyline(c, 1000, 492, "#1c2240", 80, 300, lit="#ffe0a0", lit_p=0.12)
    # biển quảng cáo trên mái (vòng sáng, không chữ)
    for (bx, by, bw, bh, col) in ((540, 300, 520, 260, "#6be0ff"), (2900, 240, 620, 300, "#ff6b8a")):
        c.drawRect(_R(bx + bw * 0.45, by + bh, bx + bw * 0.55, by + bh + 260), fill("#141826"))
        c.drawPath(rrect(bx, by, bx + bw, by + bh, 10), fill("#141826"))
        vgrad(c, bx + 14, by + 14, bx + bw - 14, by + bh - 14, ["#20184a", "#0c1030"])
        c.drawCircle(bx + bw * 0.3, by + bh / 2, bh * 0.3, stroke(col, 16))
        glow(c, bx + bw * 0.3, by + bh / 2, bh * 0.7, col, 0.45)
        for j in range(3):
            c.drawPath(rrect(bx + bw * 0.55, by + bh * (0.3 + j * 0.16), bx + bw * (0.9 - j * 0.1), by + bh * (0.38 + j * 0.16), 8),
                       fill(col, 0.6))
    # đường trên cao: mặt cầu + lan can + đèn xe
    DT = 480
    for px in range(200, W, 900):
        c.drawRect(_R(px - 50, DT + 90, px + 50, 1200), fill("#2a2e40"))
    c.drawRect(_R(-20, DT, W + 20, DT + 90), fill("#3a3e52"))
    c.drawRect(_R(-20, DT + 70, W + 20, DT + 90), fill("#2a2e40"))
    c.drawRect(_R(-20, DT - 40, W + 20, DT), fill("#4a4e62"))
    rng = random.Random(49)
    for _ in range(18):
        x = rng.uniform(0, W)
        col = rng.choice(["#fff4d0", "#ff4a3a"])
        c.drawCircle(x, DT - 18, 7, fill(col))
        glow(c, x, DT - 18, 60, col, 0.5)
    for px in range(100, W, 480):
        c.drawLine(px, DT - 40, px, DT - 170, stroke("#2a2e40", 8))
        c.drawLine(px, DT - 170, px + 60, DT - 170, stroke("#2a2e40", 8))
        glow(c, px + 60, DT - 165, 70, "#ffd890", 0.6)
    far = sf.makeImageSnapshot()
    s = new_surface()
    c = s.getCanvas()
    GB = 1600
    facades = ["#4a6a78", "#8a6a4a", "#6a5a7a", "#7a7a5a", "#5a7a6a", "#8a5a5a", "#5a6a8a", "#7a6a58", "#6a7a82"]
    heights = [3, 2, 3, 3, 2, 3, 2, 3, 3]
    hw = W / 9
    neon_pts = []
    for i in range(9):
        l, r = i * hw - 6, (i + 1) * hw + 6
        top = 300 if heights[i] == 3 else 700
        col = facades[i]
        c.drawRect(_R(l, top, r, GB), fill(col))
        c.drawRect(_R(l, top - 40, r, top), fill(shade(col, 0.12)))
        c.drawRect(_R(r - 14, top, r, GB), fill(shade(col, -0.25)))
        fy = 1100
        while fy - 400 >= top - 1:
            wy0 = fy - 330
            for (wl, wr) in ((l + 50, l + hw * 0.45), (l + hw * 0.55, r - 50)):
                lit = rng.random() < 0.45
                c.drawRect(_R(wl, wy0, wr, wy0 + 220), fill("#ffd98a" if lit else "#1c2236"))
                if lit:
                    glow(c, (wl + wr) / 2, wy0 + 110, 180, "#ffd98a", 0.25)
                for k_ in range(1, 4):
                    xx = wl + (wr - wl) * k_ / 4
                    c.drawLine(xx, wy0, xx, wy0 + 220, stroke(shade(col, -0.35), 5))
            c.drawRect(_R(l + 30, fy - 70, r - 30, fy - 60), fill(shade(col, -0.3)))
            for xx in range(int(l + 40), int(r - 30), 26):
                c.drawLine(xx, fy - 60, xx, fy - 10, stroke(shade(col, -0.35), 4))
            c.drawRect(_R(l + 30, fy - 12, r - 30, fy), fill(shade(col, -0.3)))
            if rng.random() < 0.6:
                ax = rng.choice([l + 70, r - 190])
                c.drawRect(_R(ax, fy - 170, ax + 120, fy - 80), fill("#c9ccd2"))
                c.drawCircle(ax + 60, fy - 125, 32, stroke("#8a9098", 6))
            fy -= 400
        # tầng trệt: bảng hiệu + mặt tiền
        text, scol = STREET_SIGNS[i]
        c.drawRect(_R(l + 10, 1100, r - 10, 1185), fill(scol))
        c.drawRect(_R(l + 10, 1100, r - 10, 1110), fill(shade(scol, 0.25)))
        bk.text(c, text, (l + r) / 2, 1143, 56, "#fff6e0", max_w=hw - 70, neon="#fff0c0")
        neon_pts.append(((l + r) / 2, 1143, scol))
        if i in (2, 5):
            vgrad(c, l + 24, 1190, r - 24, GB, ["#a4aab2", "#7a808a"])
            for yy in range(1200, GB, 16):
                c.drawLine(l + 24, yy, r - 24, yy, stroke("#626872", 3))
        else:
            warm = "#ffe6b0" if i % 2 else "#e8f4ff"
            vgrad(c, l + 24, 1190, r - 24, GB, [warm, shade(warm, -0.25)])
            for j in range(3):
                sx = l + 60 + j * (hw - 120) / 3
                c.drawRect(_R(sx, 1260 + (j % 2) * 30, sx + (hw - 160) / 3, 1420), fill(shade(scol, 0.1), 0.55))
            glow(c, (l + r) / 2, 1400, 320, warm, 0.4)
            neon_pts.append(((l + r) / 2, 1400, warm))
        c.drawRect(_R(l, 1185, l + 24, GB), fill(shade(col, -0.2)))
        c.drawRect(_R(r - 24, 1185, r, GB), fill(shade(col, -0.2)))
        if i in (0, 3, 7):                       # mái hiên sọc
            for j in range(8):
                x0 = l + 20 + j * (hw - 40) / 8
                quad(c, [(x0, 1190), (x0 + (hw - 40) / 8, 1190), (x0 + (hw - 40) / 8 + 6, 1260), (x0 + 6, 1260)],
                     "#e8e2d4" if j % 2 else scol)
    # biển dọc HOTEL
    vx = hw * 1 + hw - 70
    c.drawPath(rrect(vx - 50, 330, vx + 50, 900, 10), fill("#141826"))
    for j, ch in enumerate("HOTEL"):
        text_center(c, ch, vx, 400 + j * 105, 80, "#ffe8b0")
        glow(c, vx, 400 + j * 105, 70, "#ffd060", 0.35)
    bk.items.append({"text": "HOTEL", "box": [round(vx - 50), 330, round(vx + 50), 900]})
    # vỉa hè + đường
    c.drawRect(_R(0, GB, W, GB + 90), fill("#5a5e6a"))
    _tile_grid(c, 0, GB, W, GB + 90, 120, 45, "#4a4e58", 3)
    c.drawRect(_R(0, GB + 90, W, GB + 116), fill("#8a8e98"))
    c.drawRect(_R(0, GB + 116, W, H), fill("#24262f" if rain else "#2a2c36"))
    for x in range(-100, W, 420):
        c.drawRect(_R(x, 1900, x + 230, 1918), fill("#d9d4c4", 0.8))
    for (nx, ny, col) in neon_pts:
        _street_reflect(c, nx, GB + 116, 260 if rain else 180, col, 520 if rain else 300, 0.32 if rain else 0.16)
    for (sx_, col) in ((560, "#d8423a"), (1500, "#3a78c2"), (2700, "#e8e4dc"), (3400, "#4fa35a")):
        _scooter(c, sx_, GB + 70, 140, col, facing=1 if sx_ % 2 else -1)
    lamps = []
    for lx_ in (W / 9 * 3, W / 9 * 7):
        lamps.append(_streetlamp(c, lx_, GB + 70, 6.5, 150, lit=True, arm=1, cone=True, pool_y=GB + 140))
    if rain:
        tint(s, "#6a78a8", 0.35)
        for (lx_, ly_) in lamps:
            glow(c, lx_, ly_, 220, "#ffe2a0", 0.55)
        for i in range(10):
            _puddle(c, 300 + i * 360, 1780 + (i % 3) * 110, 160, 26, "#9ab0d0", 0.35)
    _vignette(c, 0.5)
    mid = s.makeImageSnapshot()
    near = None
    if rain:
        ns = new_surface()
        nc = ns.getCanvas()
        _rain(nc, 1400, 490, 0.4)
        nc.drawRect(_R(0, 0, W, H), fill("#8a9ac0", 0.06))
        near = ns.makeImageSnapshot()
    slots = {"center": {"x": 1920, "y": 2090, "scale": 1.0}, "left": {"x": 900, "y": 2090, "scale": 1.0},
             "right": {"x": 2950, "y": 2090, "scale": 1.0}, "sidewalk": {"x": 2200, "y": 1660, "scale": 0.3},
             "sidewalk_left": {"x": 1000, "y": 1660, "scale": 0.3}}
    return Scene(far, mid, near, slots=slots, baked_signs=bk.items, floor_y=2090, parallax=(0.85, 1.0, 1.1),
                 lights=[{"x": round(x), "y": round(y), "color": "#ffe2a0"} for (x, y) in lamps])


# ------------------------------------------------------------------- 50. hầm gửi xe B2
def _car_rear(c, P: Persp, x, z, col) -> None:
    path_fill(c, P.face_z(z + 0.7, x - 0.78, x + 0.78, 0.95, 1.42), shade(col, -0.1))
    path_fill(c, P.face_z(z + 0.65, x - 0.66, x + 0.66, 1.0, 1.36), "#1c2230")
    path_fill(c, P.face_z(z, x - 0.9, x + 0.9, 0.28, 1.0), col)
    path_fill(c, P.face_z(z - 0.01, x - 0.9, x + 0.9, 0.82, 1.0), shade(col, 0.12))
    for sd in (-1, 1):
        path_fill(c, P.face_z(z - 0.02, x + sd * 0.86, x + sd * 0.58, 0.68, 0.84), "#c8302a")
        path_fill(c, P.face_z(z + 0.05, x + sd * 0.86, x + sd * 0.6, 0.0, 0.3), "#121418")
    path_fill(c, P.face_z(z - 0.02, x - 0.26, x + 0.26, 0.42, 0.56), "#e8e4d8")
    path_fill(c, P.face_z(z - 0.03, x - 0.9, x + 0.9, 0.24, 0.36), "#2b2d33")


def scene_ham_xe_b2(tod: str) -> Scene:
    bk = _Bake()
    P = Persp(f=1400, cx=W / 2, cy=980, cam_h=1.5)
    XW, YT, Z0, ZB = 9.0, 2.9, 0.8, 48.0
    s = new_surface()
    c = s.getCanvas()
    con = "#6a6c70"
    path_fill(c, P.plane_y(YT, -XW, XW, Z0, ZB), "#55575c")
    path_fill(c, P.plane_y(0, -XW, XW, Z0, ZB), "#4e5054")
    path_fill(c, P.face_z(ZB, -XW, XW, 0, YT), "#5e6064")
    for sd in (-1, 1):
        path_fill(c, P.wall_x(sd * XW, Z0, ZB, 0, YT), shade(con, -0.12))
    # vết dầu loang + vạch đỗ xe
    rng = random.Random(50)
    for _ in range(40):
        x, z = rng.uniform(-8, 8), rng.uniform(1.5, 40)
        cx_, cy_ = P.p(x, 0, z)
        c.drawPath(oval(cx_, cy_, 0.6 * P.f / z, 0.12 * P.f / z), fill("#2a2c30", rng.uniform(0.15, 0.35)))
    for sd in (-1, 1):
        z = 1.2
        while z < ZB - 1:
            c.drawLine(*P.p(sd * 2.9, 0, z), *P.p(sd * 8.2, 0, z), stroke("#e8e4d8", max(2.0, 0.1 * P.f / z), 0.85))
            z += 2.6
        c.drawLine(*P.p(sd * 2.9, 0, Z0), *P.p(sd * 2.9, 0, ZB), stroke("#e8e4d8", 6, 0.7))
    z = 3.0
    while z < ZB - 4:                          # mũi tên vàng giữa làn
        a, b = P.p(-0.18, 0, z), P.p(0.18, 0, z + 1.6)
        path_fill(c, P.plane_y(0.001, -0.12, 0.12, z, z + 1.2), "#e8c23a", 0.8)
        path_fill(c, P.quad([(-0.4, 0.001, z + 1.2), (0.4, 0.001, z + 1.2), (0, 0.001, z + 1.9)]), "#e8c23a", 0.8)
        z += 7.0
    # trần: dầm ngang + ống dọc
    z = 2.0
    while z < ZB:
        path_fill(c, P.face_z(z, -XW, XW, YT - 0.35, YT), "#606266")
        path_fill(c, P.plane_y(YT - 0.35, -XW, XW, z, z + 0.4), "#47494d")
        z += 7.8
    for (xx, yy, w_, col) in ((-1.4, 2.7, 0.08, "#c8352e"), (-1.1, 2.72, 0.05, "#c8352e"), (2.2, 2.55, 0.35, "#8a8e94"),
                              (4.8, 2.7, 0.12, "#3a6ab0"), (-4.5, 2.6, 0.2, "#9a9a92")):
        path_fill(c, P.quad([(xx - w_, yy, 2.2), (xx + w_, yy, 2.2), (xx + w_, yy, ZB), (xx - w_, yy, ZB)]), shade(col, -0.2))
        path_fill(c, P.quad([(xx - w_, yy - w_, 2.2), (xx + w_, yy - w_, 2.2), (xx + w_, yy - w_, ZB), (xx - w_, yy - w_, ZB)]),
                  shade(col, -0.25))
    # tường cuối: B2 lớn + EXIT + lối dốc
    path_fill(c, P.face_z(ZB - 0.01, -2.5, 2.5, 0, 2.3), "#2a2c30")
    path_fill(c, P.quad([(-2.5, 0.01, ZB - 0.02), (2.5, 0.01, ZB - 0.02), (2.5, 1.2, ZB + 6), (-2.5, 1.2, ZB + 6)]), "#3a3c40")
    bx, by = P.p(-5.5, 1.5, ZB - 0.02)
    bk.text(c, "B2", bx, by, 1.4 * P.f / ZB, "#e8c23a")
    ex, ey = P.p(0, 2.55, ZB - 0.03)
    _exit_box(c, bk, ex, ey, 0.9 * P.f / ZB)
    # cột + xe, xa -> gần
    items = []
    z = 4.0
    while z < ZB - 2:
        for sd in (-1, 1):
            items.append((z, "pillar", sd * 2.9))
        z += 7.8
    for sd in (-1, 1):
        z = 1.2
        while z < ZB - 3:
            if rng.random() < 0.55:
                items.append((z + 0.5, "car", sd * 5.5))
            z += 2.6
    lamps = []
    for zi, kind, x in sorted(items, key=lambda t: -t[0]):
        if kind == "pillar":
            w_ = 0.35
            path_fill(c, P.wall_x(x - (w_ if x > 0 else -w_), zi, zi + 0.7, 0, YT), shade(con, -0.18))
            path_fill(c, P.face_z(zi, x - w_, x + w_, 0, YT), con)
            k = P.f / zi
            l_, t_ = P.p(x - w_, 1.0, zi)
            r_, b_ = P.p(x + w_, 0.0, zi)
            _guard_stripes(c, l_, t_, r_, b_, k)
            tx, ty = P.p(x, 1.6, zi)
            c.drawRect(_R(l_, ty - 0.28 * k, r_, ty + 0.28 * k), fill("#e8c23a"))
            bk.text(c, "B2", tx, ty, 0.36 * k, "#1d1d22", max_w=(r_ - l_) * 0.9)
        else:
            col = rng.choice(["#c9ccd2", "#2b2d33", "#8a2a2a", "#e8e4dc", "#3a4a6a", "#5a6a5a"])
            _car_rear(c, P, x, zi, col)
    # đèn tuýp trần (mờ)
    z = 3.0
    while z < ZB:
        for xx in (-4.5, 0.0, 4.5):
            path_fill(c, P.plane_y(YT - 0.37, xx - 0.6, xx + 0.6, z, z + 0.12), "#eef6e0")
            if xx == 0.0:
                lamps.append(P.p(xx, YT - 0.37, z))
        z += 7.8
    tint(s, "#9aa880", 0.4)
    for i, (lx_, ly_) in enumerate(lamps):
        k = P.f / (3.0 + i * 7.8)
        ellipse_glow(c, lx_, ly_ + 10, 1.4 * k, 0.4 * k, "#f4ffd8", 0.4)
        fx_, fy_ = P.p(0, 0, 3.0 + i * 7.8)
        ellipse_glow(c, fx_, fy_, 2.6 * k, 0.6 * k, "#f4ffd8", 0.18)
    glow(c, ex, ey, 200, "#3ee08f", 0.4)
    c.drawRect(_R(0, 0, W, H), rad_paint(P.cx, P.cy, 700, [("#000000", 0.5), ("#000000", 0.0)], [0, 1]))
    _vignette(c, 0.6)
    mid = s.makeImageSnapshot()
    slots = {"center": P.slot(0, 3.4), "left": P.slot(-1.4, 3.6), "right": P.slot(1.4, 3.6),
             "far": P.slot(0.3, 12.0), "car_left": P.slot(-3.6, 7.0)}
    return Scene(None, mid, slots=slots, baked_signs=bk.items, floor_y=slots["center"]["y"],
                 lights=[{"x": round(lx_), "y": round(ly_), "color": "#f4ffd8"} for (lx_, ly_) in lamps[:2]])


# ------------------------------------------------------------------- 51. góc chợ đêm: xe mì thuyền + ghế nhựa
def _folding_table(c, l, r, top, base, col="#c9ccd2") -> None:
    c.drawRect(_R(l, top, r, top + 22), fill(col))
    c.drawRect(_R(l, top + 22, r, top + 34), fill(shade(col, -0.3)))
    for (a, b) in ((l + 40, r - 60), (r - 40, l + 60)):
        c.drawLine(a, top + 34, b, base, stroke("#6e747e", 12))


def scene_quan_mi_xe_day_dem(tod: str) -> Scene:
    bk = _Bake()
    s = new_surface()
    c = s.getCanvas()
    rng = random.Random(51)
    vgrad(c, 0, 0, W, 400, ["#070a18", "#141a34"])
    GB = 1460
    # dãy nhà phố cửa cuốn phía sau
    cols = ["#4a4e62", "#5a5048", "#3e5058", "#584a5a", "#4e5648"]
    hw = W / 6
    for i in range(6):
        l, r = i * hw - 4, (i + 1) * hw + 4
        col = cols[i % len(cols)]
        top = 60 + (i % 2) * 120
        c.drawRect(_R(l, top, r, GB), fill(col))
        c.drawRect(_R(r - 12, top, r, GB), fill(shade(col, -0.25)))
        for wy in (top + 80, top + 420):
            for wx in (l + 80, l + hw / 2 + 30):
                lit = rng.random() < 0.35
                c.drawRect(_R(wx, wy, wx + hw / 2 - 110, wy + 230), fill("#ffcf80" if lit else "#1a1e2c"))
                if lit:
                    glow(c, wx + 100, wy + 110, 200, "#ffcf80", 0.25)
        c.drawRect(_R(l + 20, 900, r - 20, 960), fill(shade(col, -0.2)))
        vgrad(c, l + 30, 960, r - 30, GB, ["#8a909a", "#6a707a"])
        for yy in range(970, GB, 16):
            c.drawLine(l + 30, yy, r - 30, yy, stroke("#565c66", 3))
        if i in (1, 4):
            for j in range(7):
                x0 = l + 10 + j * (hw - 20) / 7
                quad(c, [(x0, 860), (x0 + (hw - 20) / 7, 860), (x0 + (hw - 20) / 7 + 10, 960), (x0 + 10, 960)],
                     "#2f6fb0" if j % 2 else "#e8e4dc")
    # dây đèn bóng tròn
    for (x0, y0, x1, y1, sag) in ((-50, 250, 1900, 330, 90), (1900, 330, W + 50, 220, 80), (-50, 520, W + 50, 480, 110)):
        _bulb_string(c, x0, y0, x1, y1, sag, 14)
    # mặt đường ướt
    vgrad(c, 0, GB, W, H, ["#22242e", "#2c2e38"])
    c.drawRect(_R(0, GB, W, GB + 20), fill("#3a3c46"))
    # xe trái cây (xa, phải)
    fl, fr, fb = 2950, 3600, GB + 40
    c.drawLine((fl + fr) / 2, fb - 420, (fl + fr) / 2, fb - 900, stroke("#2b2d33", 10))
    p = skia.Path()
    p.moveTo(fl - 120, fb - 860)
    p.quadTo((fl + fr) / 2, fb - 1060, fr + 120, fb - 860)
    p.close()
    path_fill(c, p, "#d8423a")
    c.drawRect(_R(fl, fb - 420, fr, fb - 140), fill("#5a3a2a"))
    c.drawRect(_R(fl + 20, fb - 400, fr - 20, fb - 250), fill("#dfeef4"))
    for j in range(9):
        x = fl + 60 + j * 62
        c.drawPath(rrect(x, fb - 330, x + 44, fb - 262, 8), fill(rng.choice(["#f3c94e", "#e8584a", "#8ac85a", "#f08a2c"])))
    c.drawRect(_R(fl + 20, fb - 400, fr - 20, fb - 250), stroke("#c9ccd2", 6))
    for wx in (fl + 90, fr - 90):
        c.drawCircle(wx, fb - 70, 70, fill("#1d1f24"))
        c.drawCircle(wx, fb - 70, 26, fill("#8a9098"))
    glow(c, (fl + fr) / 2, fb - 820, 260, "#ffe2a0", 0.5)
    # xe mì thuyền: thân gỗ cong + tủ kính + nồi + mái sọc đỏ trắng
    CL, CR, CB = 500, 1800, GB + 120
    CT = CB - 560
    for px in (CL + 40, CR - 40):
        c.drawRect(_R(px - 12, CT - 640, px + 12, CT), fill("#3a3e48"))
    aw_t, aw_b = CT - 700, CT - 560
    for j in range(12):
        x0 = CL - 80 + j * (CR - CL + 160) / 12
        x1 = x0 + (CR - CL + 160) / 12
        quad(c, [(x0 + 20, aw_t), (x1 + 20, aw_t), (x1, aw_b), (x0, aw_b)], "#d8352e" if j % 2 == 0 else "#f4f0e8")
        p = skia.Path()
        p.moveTo(x0, aw_b)
        p.quadTo((x0 + x1) / 2, aw_b + 50, x1, aw_b)
        p.close()
        path_fill(c, p, "#d8352e" if j % 2 == 0 else "#f4f0e8")
    c.drawRect(_R(CL - 70, aw_t - 20, CR + 90, aw_t), fill("#a8281f"))
    bulb_x = (CL + CR) / 2
    c.drawLine(bulb_x, aw_b, bulb_x, aw_b + 90, stroke("#1d1f24", 4))
    c.drawCircle(bulb_x, aw_b + 110, 22, fill("#fff1c8"))
    # nồi + tủ kính
    for (px, pw, ph) in ((CL + 260, 300, 240), (CL + 620, 220, 180)):
        c.drawRect(_R(px - pw / 2, CT - ph, px + pw / 2, CT), fill("#b9c2c8"))
        c.drawRect(_R(px - pw / 2, CT - ph, px - pw / 2 + 24, CT), fill("#d9e0e4"))
        c.drawPath(oval(px, CT - ph, pw / 2, 20), fill("#8a9298"))
        for k_ in range(3):
            sx = px - pw * 0.25 + k_ * pw * 0.25
            st = skia.Path()
            st.moveTo(sx, CT - ph - 20)
            st.cubicTo(sx - 50, CT - ph - 120, sx + 50, CT - ph - 200, sx - 10, CT - ph - 300)
            c.drawPath(st, stroke("#ffffff", 22, 0.2))
    gl, gr = CL + 820, CR - 60
    c.drawRect(_R(gl, CT - 320, gr, CT), fill("#dfeef4", 0.85))
    for j in range(2):
        yy = CT - 300 + j * 140
        c.drawRect(_R(gl + 10, yy + 110, gr - 10, yy + 118), fill("#9aa0a8"))
        for x in range(int(gl + 30), int(gr - 60), 90):
            c.drawPath(oval(x + 30, yy + 90, 34, 20), fill(rng.choice(["#f3e4c0", "#e8c890", "#c8352e", "#7ab85a"])))
    c.drawRect(_R(gl, CT - 320, gr, CT), stroke("#c9ccd2", 8))
    reflections(c, gl, CT - 320, gr, CT, 2, 0.2, seed=51)
    # thân xe
    body = poly([(CL - 120, CT), (CR + 140, CT), (CR + 40, CB - 120), (CL - 20, CB - 120)])
    path_fill(c, body, "#7a2e22")
    c.drawRect(_R(CL - 130, CT - 14, CR + 150, CT + 16), fill("#a8452e"))
    c.drawPath(rrect(CL + 200, CT + 70, CR - 200, CT + 250, 18), fill("#f4ead0"))
    c.drawPath(rrect(CL + 214, CT + 84, CR - 214, CT + 236, 12), stroke("#a8281f", 6))
    bk.text(c, "NOODLES", (CL + CR) / 2, CT + 160, 110, "#a8281f", max_w=CR - CL - 480)
    for wx in (CL + 120, CR - 120):
        c.drawCircle(wx, CB - 80, 86, fill("#1d1f24"))
        c.drawCircle(wx, CB - 80, 32, fill("#8a9098"))
    # bàn gấp + ghế nhựa đỏ / xanh (tiền cảnh)
    for (tl, tr, tt, tb) in ((1650, 2550, 1640, 1960), (2750, 3650, 1680, 2010)):
        for (sx, colr) in ((tl - 60, "#c8352e"), (tr + 60, "#2f6fb0")):
            _plastic_stool(c, sx, tb + 30, 190, colr)
        _folding_table(c, tl, tr, tt, tb)
        for j in range(3):
            bx_ = tl + 160 + j * 260
            c.drawPath(oval(bx_, tt - 4, 70, 14), fill("#e8e4dc"))
            quad(c, [(bx_ - 70, tt - 30), (bx_ + 70, tt - 30), (bx_ + 46, tt), (bx_ - 46, tt)], "#e8e4dc")
            c.drawRect(_R(bx_ - 70, tt - 30, bx_ + 70, tt - 22), fill("#c8352e"))
        c.drawPath(rrect(tr - 200, tt - 110, tr - 100, tt, 10), fill("#c9ccd2"))
        for (dx, col) in ((-30, "#d8423a"), (0, "#3a2a1e"), (30, "#f3c94e")):
            c.drawPath(rrect(tr - 150 + dx - 12, tt - 150, tr - 150 + dx + 12, tt - 60, 6), fill(col))
        c.drawPath(rrect(tl + 40, tt - 90, tl + 100, tt, 8), fill("#2f6fb0"))
        for dx in (-12, 0, 12):
            c.drawLine(tl + 70 + dx, tt - 80, tl + 70 + dx * 1.4, tt - 160, stroke("#d9b46a", 5))
    for (sx, colr) in ((1500, "#2f6fb0"), (3850, "#c8352e"), (300, "#c8352e")):
        _plastic_stool(c, sx, 2140, 230, colr)
    tint(s, "#6a70a8", 0.3)
    glow(c, bulb_x, aw_b + 110, 700, "#ffd890", 0.5)
    glow(c, bulb_x, aw_b + 110, 120, "#fff1c8", 0.7)
    ellipse_glow(c, bulb_x, GB + 200, 1300, 260, "#ffd890", 0.25)
    for x in range(200, W, 300):
        _street_reflect(c, x, GB + 30, 60, "#ffd890", 260, 0.12)
    _vignette(c, 0.5)
    mid = s.makeImageSnapshot()
    slots = {"vendor": {"x": 1150, "y": GB + 60, "scale": 0.8, "clip_bottom": CT},
             "seat_left": {"x": 1590, "y": 2000, "scale": 0.95}, "seat_right": {"x": 2610, "y": 2000, "scale": 0.95},
             "center": {"x": 2100, "y": 2100, "scale": 1.05}, "left": {"x": 700, "y": 2100, "scale": 1.05},
             "right": {"x": 3300, "y": 2100, "scale": 1.05}}
    return Scene(None, mid, slots=slots, baked_signs=bk.items, floor_y=2100,
                 lights=[{"x": round(bulb_x), "y": round(aw_b + 110), "color": "#ffd890"}])


# ------------------------------------------------------------------- 52. tiệm giặt tự động 24h (+ mặt tiền đêm)
def _washer(c, l, t, w, h, rng, dryer=False) -> None:
    body = "#f2f2ee" if not dryer else "#e4e6e8"
    c.drawPath(rrect(l, t, l + w, t + h, w * 0.04), fill(body))
    c.drawRect(_R(l + w - w * 0.05, t + w * 0.04, l + w, t + h), fill(shade(body, -0.12)))
    c.drawRect(_R(l, t, l + w, t + h * 0.16), fill(shade(body, -0.06)))
    c.drawPath(rrect(l + w * 0.08, t + h * 0.04, l + w * 0.42, t + h * 0.12, w * 0.02), fill("#1d2230"))
    c.drawRect(_R(l + w * 0.1, t + h * 0.06, l + w * 0.24, t + h * 0.1), fill("#3ee08f", 0.8))
    for j in range(3):
        c.drawCircle(l + w * (0.6 + j * 0.12), t + h * 0.08, w * 0.03, fill("#8a9098"))
    cx_, cy_, r = l + w / 2, t + h * 0.58, min(w, h) * 0.33
    c.drawCircle(cx_, cy_, r * 1.12, fill("#c9ccd2"))
    c.drawCircle(cx_, cy_, r, fill("#2a3142"))
    if rng.random() < 0.6:
        for _ in range(4):
            a = rng.uniform(0, math.tau)
            c.drawCircle(cx_ + math.cos(a) * r * 0.45, cy_ + r * 0.25 + math.sin(a) * r * 0.25, r * rng.uniform(0.25, 0.4),
                         fill(rng.choice(["#d8423a", "#3a78c2", "#f3c94e", "#e8e4dc", "#4fa35a"]), 0.8))
    c.drawPath(oval(cx_ - r * 0.3, cy_ - r * 0.35, r * 0.35, r * 0.18), fill("#ffffff", 0.35))
    c.drawCircle(cx_, cy_, r, stroke("#9aa0a8", max(2.0, w * 0.025)))


def _laundry_inside(c, bk: _Bake | None, rng, L, R, FL, k) -> None:
    """Tường máy giặt (2 tầng sấy trên, giặt dưới). k = px/mét."""
    mw = 0.72 * k
    x = L
    while x + mw <= R:
        _washer(c, x, FL - 1.0 * k, mw - 0.04 * k, 1.0 * k, rng)
        _washer(c, x, FL - 1.92 * k, mw - 0.04 * k, 0.88 * k, rng, dryer=True)
        x += mw


def _detergent_machine(c, bk: _Bake, l, base, w, h) -> None:
    t = base - h
    c.drawPath(rrect(l, t, l + w, base, w * 0.04), fill("#c8302a"))
    c.drawRect(_R(l + w - w * 0.06, t + 10, l + w, base), fill("#9a2420"))
    c.drawPath(rrect(l + w * 0.06, t + h * 0.03, l + w * 0.9, t + h * 0.13, w * 0.03), fill("#f4f0e8"))
    bk.text(c, "DETERGENT", l + w * 0.48, t + h * 0.08, h * 0.05, "#c8302a", max_w=w * 0.78)
    c.drawRect(_R(l + w * 0.08, t + h * 0.17, l + w * 0.66, t + h * 0.6), fill("#eef4f8"))
    rng = random.Random(52)
    for j in range(4):
        yy = t + h * (0.2 + j * 0.1)
        for i in range(4):
            xx = l + w * (0.11 + i * 0.135)
            c.drawPath(rrect(xx, yy, xx + w * 0.1, yy + h * 0.07, 4), fill(rng.choice(["#2f6fd0", "#f3c94e", "#4fa35a", "#f08a2c", "#ffffff"])))
        c.drawRect(_R(l + w * 0.08, yy + h * 0.075, l + w * 0.66, yy + h * 0.082), fill("#9aa0a8"))
    reflections(c, l + w * 0.08, t + h * 0.17, l + w * 0.66, t + h * 0.6, 2, 0.2, seed=52)
    c.drawPath(rrect(l + w * 0.72, t + h * 0.2, l + w * 0.9, t + h * 0.45, 6), fill("#7a1a16"))
    c.drawRect(_R(l + w * 0.75, t + h * 0.23, l + w * 0.87, t + h * 0.28), fill("#101214"))
    for j in range(3):
        c.drawCircle(l + w * 0.81, t + h * (0.33 + j * 0.035), w * 0.025, fill("#f4f0e8"))
    c.drawPath(rrect(l + w * 0.14, base - h * 0.22, l + w * 0.66, base - h * 0.1, 8), fill("#2a0e0c"))


def scene_tiem_giat_24h(tod: str) -> Scene:
    if tod == "exterior":
        return _laundry_exterior()
    bk = _Bake()
    s = new_surface()
    c = s.getCanvas()
    rng = random.Random(52)
    FL, k = 1760, 520.0
    c.drawRect(_R(0, 0, W, FL), fill("#dfeee8"))
    _tile_grid(c, 0, 820, W, FL, 104, 104, "#c4d8d0", 3)
    c.drawRect(_R(0, 0, W, 120), fill("#f4f6f4"))
    c.drawRect(_R(0, 808, W, 822), fill("#9abfb2"))
    # cửa kính trái nhìn ra phố đêm
    vgrad(c, 0, 240, 520, FL, ["#0c1430", "#1c2a48"])
    for (gx, gy, col) in ((140, 700, "#ffcf80"), (380, 900, "#ff6b8a"), (260, 1100, "#6be0ff")):
        glow(c, gx, gy, 120, col, 0.5)
    c.drawRect(_R(0, 240, 520, FL), stroke("#8a9098", 22))
    c.drawLine(260, 240, 260, FL, stroke("#8a9098", 14))
    reflections(c, 0, 240, 520, FL, 3, 0.12, seed=521)
    _laundry_inside(c, bk, rng, 640, 2780, FL, k)
    _detergent_machine(c, bk, 2930, FL, 560, 1000)
    c.drawPath(rrect(820, 300, 2600, 600, 18), fill("#2a7aa8"))
    c.drawPath(rrect(1640, 640, 1980, 760, 10), fill("#f4f6f4"))
    bk.text(c, "WASH 40  DRY 30", 1810, 700, 40, "#2a4a5a", max_w=310)
    _tube(c, 1100, 140, 700)
    _tube(c, 2700, 140, 700)
    # sàn + bàn gấp đồ + ghế + xô lau
    _persp_floor(c, FL, "#cfd2d0", "#b4b8b6", vx=1920, vy=900, spacing=280, dz=0.1)
    TL, TR, TT = 2050, 3050, 1700
    c.drawRect(_R(TL, TT, TR, TT + 40), fill("#e8e4dc"))
    c.drawRect(_R(TL, TT + 40, TR, TT + 56), fill("#b4aea2"))
    for x in (TL + 40, TR - 60):
        c.drawRect(_R(x, TT + 56, x + 20, 2040), fill("#8a9098"))
    for j, col in enumerate(("#3a78c2", "#e8e4dc", "#d8423a", "#f3c94e")):
        c.drawPath(rrect(TL + 520, TT - 40 - j * 34, TL + 800, TT - 4 - j * 34, 8), fill(col))
    c.drawPath(rrect(TL + 80, TT - 190, TL + 420, TT, 24), fill("#4fa3c8"))
    for x in range(int(TL + 110), int(TL + 400), 40):
        c.drawLine(x, TT - 170, x, TT - 20, stroke("#3a86a8", 6))
    for cx_ in (700, 1100):
        c.drawPath(rrect(cx_ - 120, 1700, cx_ + 120, 1740, 10), fill("#2f6fb0"))
        c.drawPath(rrect(cx_ - 110, 1460, cx_ + 110, 1700, 20), fill("#3a7ac0"))
        for dx in (-100, 100):
            c.drawLine(cx_ + dx, 1740, cx_ + dx * 1.1, 1960, stroke("#2a5a90", 12))
    c.drawPath(rrect(3380, 1860, 3620, 2060, 20), fill("#f3c94e"))
    c.drawRect(_R(3380, 1860, 3620, 1890), fill("#d8a830"))
    c.drawLine(3560, 1880, 3460, 1300, stroke("#8a6a4a", 14))
    c.drawPath(oval(3450, 1300, 70, 30), fill("#c9c2b0"))
    tint(s, "#e8f0ff", 0.08)
    glow(c, 1100, 160, 1000, "#eef6ff", 0.25)
    glow(c, 2700, 160, 1000, "#eef6ff", 0.25)
    _vignette(c, 0.3)
    mid = s.makeImageSnapshot()
    signs = [{"text": "LAUNDRY 24H", "box": [860, 330, 2560, 570], "style": "plain"}]
    slots = {"center": {"x": 1700, "y": 2070, "scale": 1.1}, "left": {"x": 1000, "y": 2070, "scale": 1.1},
             "right": {"x": 3300, "y": 2070, "scale": 1.1}, "machines": {"x": 1400, "y": 1850, "scale": 1.0},
             "table": {"x": 2550, "y": 2000, "scale": 1.05, "clip_bottom": TT + 40}}
    return Scene(None, mid, slots=slots, signs=signs, baked_signs=bk.items, floor_y=2070,
                 lights=[{"x": 1100, "y": 160, "color": "#eef6ff"}, {"x": 2700, "y": 160, "color": "#eef6ff"}])


def _laundry_exterior() -> Scene:
    bk = _Bake()
    sf = new_surface()
    c = sf.getCanvas()
    _night_sky(c, 0, 900, seed=521, top="#070b1c", bottom="#1e2444", n_stars=60)
    far = sf.makeImageSnapshot()
    s = new_surface()
    c = s.getCanvas()
    rng = random.Random(521)
    GB = 1620
    c.drawRect(_R(560, 80, 3280, GB), fill("#7a8088"))
    c.drawRect(_R(560, 80, 3280, 120), fill("#8a9098"))
    for wx in (760, 1560, 2360):
        lit = wx == 1560
        c.drawRect(_R(wx, 200, wx + 640, 460), fill("#ffcf80" if lit else "#1c2236"))
        c.drawRect(_R(wx - 20, 460, wx + 660, 480), fill("#5a6068"))
        if lit:
            glow(c, wx + 320, 330, 380, "#ffcf80", 0.3)
    c.drawRect(_R(3000, 260, 3160, 380), fill("#c9ccd2"))
    c.drawCircle(3080, 320, 44, stroke("#8a9098", 6))
    # bảng hiệu LAUNDRY 24H (neon)
    c.drawRect(_R(640, 560, 3200, 760), fill("#1a5a8a"))
    c.drawRect(_R(640, 740, 3200, 760), fill("#6be0ff"))
    bk.text(c, "LAUNDRY 24H", 1920, 655, 120, "#ffffff", max_w=2200, neon="#6be0ff")
    # mặt kính + bên trong
    L, R, T = 700, 3140, 800
    c.drawRect(_R(L, T, R, GB), fill("#e8f2f0"))
    _laundry_inside(c, None, rng, L + 120, R - 600, GB - 60, 330)
    _detergent_machine(c, bk, R - 470, GB - 60, 330, 640)
    c.drawRect(_R(L, GB - 60, R, GB), fill("#c9ccd0"))
    c.drawRect(_R(L, T, R, T + 40), fill("#f4f8f8"))
    for x in (L, (L + R) / 2 - 500, (L + R) / 2 + 500, R):
        c.drawRect(_R(x - 14, T, x + 14, GB), fill("#4a4e58"))
    c.drawPath(rrect(1446, 1120, 1476, 1320, 10), fill("#c9ccd2"))
    reflections(c, L, T, R, GB, 4, 0.1, seed=522)
    # hàng xóm: cửa cuốn đóng
    for (l, r) in ((-20, 560), (3280, W + 20)):
        c.drawRect(_R(l, 300, r, GB), fill("#4a4e5a"))
        vgrad(c, l + 30, 800, r - 30, GB, ["#8a909a", "#6a707a"])
        for yy in range(810, GB, 16):
            c.drawLine(l + 30, yy, r - 30, yy, stroke("#565c66", 3))
    # vỉa hè + đường + xe máy + đèn
    c.drawRect(_R(0, GB, W, GB + 140), fill("#5a5e68"))
    _tile_grid(c, 0, GB, W, GB + 140, 140, 70, "#4a4e58", 3)
    c.drawRect(_R(0, GB + 140, W, GB + 170), fill("#8a8e98"))
    c.drawRect(_R(0, GB + 170, W, H), fill("#2a2c36"))
    _scooter(c, 3500, GB + 110, 330, "#d8423a", facing=-1)
    lx, ly = _streetlamp(c, 300, GB + 120, 6.0, 170, lit=True, arm=1, cone=True, pool_y=GB + 150)
    tint(s, "#7a86b8", 0.3)
    glow(c, 1920, 1200, 1500, "#e8f4ff", 0.35)
    ellipse_glow(c, 1920, GB + 100, 1500, 200, "#e8f4ff", 0.35)
    glow(c, 1920, 655, 900, "#6be0ff", 0.2)
    glow(c, lx, ly, 200, "#ffe2a0", 0.5)
    _vignette(c, 0.5)
    mid = s.makeImageSnapshot()
    slots = {"center": {"x": 1920, "y": 2080, "scale": 1.05}, "left": {"x": 900, "y": 2080, "scale": 1.05},
             "right": {"x": 2950, "y": 2080, "scale": 1.05}, "door": {"x": 1250, "y": GB + 40, "scale": 0.73}}
    return Scene(far, mid, slots=slots, baked_signs=bk.items, floor_y=2080, parallax=(0.9, 1.0, 1.1),
                 lights=[{"x": 1920, "y": 655, "color": "#6be0ff"}, {"x": round(lx), "y": round(ly), "color": "#ffe2a0"}])


# ------------------------------------------------------------------- 53. trung tâm dữ liệu về đêm (hàng rào kẽm gai)
def _chain_fence(c, l, t, r, b, col="#9aa4b0", a=0.5, step=46) -> None:
    c.save()
    c.clipRect(_R(l, t, r, b))
    x = l - (b - t)
    while x < r:
        c.drawLine(x, b, x + (b - t), t, stroke(col, 3, a))
        c.drawLine(x, t, x + (b - t), b, stroke(col, 3, a))
        x += step
    c.restore()


def _barbed(c, l, r, y, col="#8a94a0") -> None:
    for j in range(3):
        c.drawLine(l, y - j * 34, r, y - j * 34, stroke(col, 4))
    x = l
    while x < r:
        c.drawCircle(x, y - 100, 48, stroke(col, 4, 0.85))
        x += 58
    for j in range(3):
        x = l + j * 17
        while x < r:
            c.drawLine(x - 8, y - j * 34 - 8, x + 8, y - j * 34 + 8, stroke(col, 4))
            x += 52


def scene_trung_tam_du_lieu_dem(tod: str) -> Scene:
    bk = _Bake()
    sf = new_surface()
    c = sf.getCanvas()
    _night_sky(c, 0, 1300, seed=53, top="#060a18", bottom="#1a2444", n_stars=220)
    _moon(c, 3350, 260, 70, a=0.85)
    soft_hills(c, 1180, 160, "#0e1424", 531, n=6)
    far = sf.makeImageSnapshot()
    s = new_surface()
    c = s.getCanvas()
    BL, BR, BT, BB = 820, 3440, 430, 1420
    box3(c, BL, BT, BR, BB, "#4e5666", top_h=0, side_w=320, side="left")
    quad(c, [(BL, BT), (BR, BT), (BR - 40, BT - 60), (BL - 320, BT - 60)], "#5e6676")
    for x in range(int(BL + 160), int(BR), 260):
        c.drawRect(_R(x, BT + 20, x + 40, BB - 120), fill("#5a6272"))
    for y in (620, 880, 1140):
        c.drawRect(_R(BL, y, BR, y + 14), fill("#5ad4ff"))
        glow(c, (BL + BR) / 2, y + 7, 1300, "#3ab0ff", 0.1)
        quad(c, [(BL, y), (BL - 320, y - 60 * (1 - (y - BT) / (BB - BT))), (BL - 320, y - 60 * (1 - (y - BT) / (BB - BT)) + 12),
                 (BL, y + 14)], "#3ab0e0")
        for x in range(int(BL), int(BR), 120):
            glow(c, x + 60, y + 7, 70, "#5ad4ff", 0.25)
    for (ux, uw) in ((1100, 380), (1700, 300), (2700, 420)):          # máy làm mát trên mái
        c.drawRect(_R(ux, BT - 150, ux + uw, BT - 20), fill("#3a4250"))
        for j in range(int(uw // 110)):
            c.drawCircle(ux + 60 + j * 110, BT - 85, 42, stroke("#2a303c", 8))
    # biểu tượng đồng hồ cát trừu tượng + chữ DATA CENTER
    lx, ly = 2900, 300 + BT
    quad(c, [(lx - 70, ly - 110), (lx + 70, ly - 110), (lx, ly)], "#bfeaff")
    quad(c, [(lx - 70, ly + 110), (lx + 70, ly + 110), (lx, ly)], "#5ad4ff")
    c.drawCircle(lx, ly, 150, stroke("#bfeaff", 10))
    glow(c, lx, ly, 300, "#5ad4ff", 0.35)
    bk.text(c, "DATA CENTER", 2120, ly, 96, "#e8f6ff", max_w=1100, neon="#5ad4ff")
    # cửa kính lối vào
    c.drawRect(_R(1700, BB - 360, 2340, BB), fill("#a8e0ff", 0.85))
    for x in (1860, 2020, 2180):
        c.drawLine(x, BB - 360, x, BB, stroke("#3a4250", 10))
    glow(c, 2020, BB - 180, 500, "#bfeaff", 0.35)
    # sân + cỏ
    c.drawRect(_R(0, BB, W, 1560), fill("#262a34"))
    c.drawRect(_R(0, 1560, W, H), fill("#1c2a22"))
    vgrad(c, 0, 1900, W, H, ["#2a3a2c", "#1e2a22"])
    # đèn pha trên cột
    lights = []
    for (px, aim) in ((380, 1), (3640, -1)):
        c.drawRect(_R(px - 16, 380, px + 16, 1700), fill("#2a2e38"))
        hx, hy = px + aim * 60, 400
        c.drawPath(rrect(hx - 70, hy - 40, hx + 70, hy + 40, 10), fill("#3a3e48"))
        c.drawPath(oval(hx + aim * 50, hy + 20, 26, 40), fill("#fff8e0"))
        _light_cone(c, hx + aim * 50, hy + 20, 40, hx + aim * 900, 1560, 600, "#fff8e0", 0.1)
        glow(c, hx + aim * 50, hy + 20, 240, "#fff8e0", 0.7)
        lights.append((hx + aim * 50, hy + 20))
    # hàng rào lưới B40 + kẽm gai + cổng
    FT, FB = 1010, 1960
    for x in range(-60, W + 100, 460):
        c.drawRect(_R(x - 12, FT - 120, x + 12, FB), fill("#6a7480"))
        c.drawLine(x, FT - 120, x - 60, FT - 230, stroke("#6a7480", 10))
    c.drawLine(0, FT, W, FT, stroke("#6a7480", 10))
    c.drawLine(0, FB - 20, W, FB - 20, stroke("#6a7480", 8))
    _chain_fence(c, 0, FT, W, FB)
    _barbed(c, 0, W, FT - 40)
    GL, GR = 1640, 2360
    for x in (GL, GR):
        c.drawRect(_R(x - 26, FT - 180, x + 26, FB), fill("#7a8490"))
    for (l, r) in ((GL + 30, 2000), (2000, GR - 30)):
        c.drawRect(_R(l, FT + 30, r, FB - 30), stroke("#8a94a0", 14))
        c.drawLine(l, (FT + FB) / 2, r, (FT + FB) / 2, stroke("#8a94a0", 10))
    c.drawPath(rrect(1975, (FT + FB) / 2 - 40, 2025, (FT + FB) / 2 + 40, 8), fill("#c9a440"))
    SL, SR, ST, SB_ = 1720, 2280, 1180, 1500
    c.drawPath(rrect(SL, ST, SR, SB_, 12), fill("#f4f2ec"))
    c.drawRect(_R(SL, ST, SR, ST + 140), fill("#c8302a"))
    bk.text(c, "RESTRICTED AREA", (SL + SR) / 2, ST + 70, 58, "#ffffff", max_w=SR - SL - 50)
    bk.text(c, "STAFF ONLY", (SL + SR) / 2, ST + 230, 72, "#c8302a", max_w=SR - SL - 60)
    c.drawPath(rrect(SL, ST, SR, SB_, 12), stroke("#c8302a", 10))
    # camera an ninh trên cột cổng
    c.drawPath(rrect(GR + 10, FT - 220, GR + 170, FT - 160, 14), fill("#e8e4dc"))
    c.drawCircle(GR + 170, FT - 190, 18, fill("#1d1f24"))
    c.drawCircle(GR + 150, FT - 205, 6, fill("#ff3b30"))
    tint(s, "#7a88c0", 0.3)
    for (x, y) in lights:
        glow(c, x, y, 160, "#ffffff", 0.6)
    glow(c, 2900, BT + 300, 260, "#5ad4ff", 0.3)
    _vignette(c, 0.55)
    mid = s.makeImageSnapshot()
    slots = {"center": {"x": 1920, "y": 2090, "scale": 1.0}, "left": {"x": 850, "y": 2090, "scale": 1.0},
             "right": {"x": 3000, "y": 2090, "scale": 1.0}, "fence": {"x": 1200, "y": 1970, "scale": 0.95},
             "inside": {"x": 2600, "y": 1540, "scale": 0.5}}
    return Scene(far, mid, slots=slots, baked_signs=bk.items, floor_y=2090, parallax=(0.9, 1.0, 1.1),
                 lights=[{"x": round(x), "y": round(y), "color": "#fff8e0"} for (x, y) in lights])


# ------------------------------------------------------------------- 54. lối đi phòng máy chủ (1 điểm tụ)
def _rack_local(c, w, h, seed) -> None:
    rng = random.Random(seed)
    c.drawRect(_R(0, 0, w, h), fill("#14171e"))
    c.drawRect(_R(6, 6, w - 6, h - 6), fill("#1e222b"))
    y = 22
    while y < h - 30:
        uh = rng.choice([14, 14, 28, 42])
        c.drawRect(_R(12, y, w - 12, y + uh - 3), fill(rng.choice(["#262b36", "#2c313c", "#20242e"])))
        for j in range(rng.randint(2, 6)):
            col = rng.choices(["#3ee08f", "#2fa8ff", "#ffb02e", "#ff3b30"], [6, 5, 2, 1])[0]
            c.drawCircle(18 + j * 9, y + 6, 2.6, fill(col))
        c.drawLine(w * 0.45, y + uh / 2, w - 18, y + uh / 2, stroke("#3a404c", 1.5))
        y += uh
    for x in range(10, int(w) - 6, 6):
        c.drawLine(x, 8, x, h - 8, stroke("#000000", 1.0, 0.18))
    c.drawRect(_R(w - 14, h * 0.4, w - 8, h * 0.6), fill("#8a9098"))


def scene_phong_may_chu(tod: str) -> Scene:
    bk = _Bake()
    P = Persp(f=1500, cx=W / 2, cy=1000, cam_h=1.6)
    XW, RH, YT, Z0, ZB = 1.25, 2.2, 3.3, 0.8, 30.0
    s = new_surface()
    c = s.getCanvas()
    path_fill(c, P.plane_y(YT, -4, 4, Z0, ZB), "#20242e")
    path_fill(c, P.face_z(ZB, -4, 4, 0, YT), "#262a34")
    path_fill(c, P.plane_y(0, -XW, XW, Z0, ZB), "#d4d8dc")
    _floor_tiles(c, P, -XW, XW, Z0, ZB, 0.6, "#a8aeb6")
    z = 1.2
    while z < ZB:                                # tấm sàn đục lỗ
        for xx in (-0.6, 0.0):
            q = [P.p(xx + 0.05, 0, z + 0.05), P.p(xx + 0.55, 0, z + 0.05), P.p(xx + 0.55, 0, z + 0.55), P.p(xx + 0.05, 0, z + 0.55)]
            path_fill(c, poly(q), "#9aa2ac", 0.5)
        z += 1.8
    # cửa cuối + EXIT
    path_fill(c, P.face_z(ZB - 0.01, -0.6, 0.6, 0, 2.1), "#5a6270")
    path_fill(c, P.face_z(ZB - 0.02, -0.5, 0.5, 0.9, 1.8), "#8ab8d8")
    ex, ey = P.p(0, 2.45, ZB - 0.02)
    _exit_box(c, bk, ex, ey, 0.8 * P.f / ZB)
    # hai dãy tủ rack
    leds = []
    for sd in (-1, 1):
        x = sd * XW
        path_fill(c, P.plane_y(RH, x, x + sd * 0.9, Z0, ZB - 0.5), "#101318")
        path_fill(c, P.wall_x(x, Z0, ZB - 0.5, RH, YT), "#1a1e26")
        z = Z0
        i = 0
        while z < ZB - 1.0:
            dst = ([P.p(x, RH, z), P.p(x, RH, z + 0.6), P.p(x, 0, z + 0.6), P.p(x, 0, z)] if sd < 0 else
                   [P.p(x, RH, z + 0.6), P.p(x, RH, z), P.p(x, 0, z), P.p(x, 0, z + 0.6)])
            _on_quad(c, None, 0.6 * U4, RH * U4, dst, lambda cc, sd_=530 + i * 7 + sd: _rack_local(cc, 0.6 * U4, RH * U4, sd_))
            leds.append(P.p(x, 1.2, z + 0.3))
            z += 0.62
            i += 1
        # máng cáp vàng trên trần
        tx = sd * 0.9
        for dy in (0.0, 0.12):
            c.drawLine(*P.p(tx - 0.25, 2.75 + dy, Z0), *P.p(tx - 0.25, 2.75 + dy, ZB), stroke("#e8b830", 1))
        path_fill(c, P.quad([(tx - 0.3, 2.75, Z0), (tx + 0.3, 2.75, Z0), (tx + 0.3, 2.75, ZB), (tx - 0.3, 2.75, ZB)]), "#c99a20")
        path_fill(c, P.quad([(tx - 0.3, 2.85, Z0), (tx + 0.3, 2.85, Z0), (tx + 0.3, 2.85, ZB), (tx - 0.3, 2.85, ZB)]), "#e8b830")
        z = 1.0
        while z < ZB:
            path_fill(c, P.quad([(tx - 0.3, 2.85, z), (tx + 0.3, 2.85, z), (tx + 0.3, 2.85, z + 0.06), (tx - 0.3, 2.85, z + 0.06)]),
                      "#a87a10")
            z += 0.5
        for cz in (1.5, 6.0, 12.0):
            c.drawLine(*P.p(tx, 2.85, cz), *P.p(tx, YT, cz), stroke("#5a606a", max(2.0, 0.03 * P.f / cz)))
    # dải đèn trần lạnh + biển ROW B treo
    path_fill(c, P.plane_y(YT - 0.01, -0.1, 0.1, Z0, ZB), "#eaf4ff")
    sx_, sy_ = P.p(0, 2.55, 4.0)
    k = P.f / 4.0
    c.drawLine(sx_ - 0.3 * k, P.p(0, YT, 4.0)[1], sx_ - 0.3 * k, sy_, stroke("#8a9098", 4))
    c.drawLine(sx_ + 0.3 * k, P.p(0, YT, 4.0)[1], sx_ + 0.3 * k, sy_, stroke("#8a9098", 4))
    c.drawPath(rrect(sx_ - 0.42 * k, sy_, sx_ + 0.42 * k, sy_ + 0.2 * k, 10), fill("#1a5a8a"))
    bk.text(c, "ROW B", sx_, sy_ + 0.1 * k, 0.13 * k, "#ffffff")
    tint(s, "#7a9ad8", 0.35)
    for (lx_, ly_) in leds[::3]:
        glow(c, lx_, ly_, 60, "#2fa8ff", 0.25)
    ellipse_glow(c, P.cx, P.p(0, 0, 6)[1], 900, 160, "#bfe0ff", 0.25)
    glow(c, P.cx, P.cy, 500, "#bfe0ff", 0.3)
    _vignette(c, 0.55)
    mid = s.makeImageSnapshot()
    slots = {"center": P.slot(0, 3.2), "left": P.slot(-0.6, 3.6), "right": P.slot(0.6, 3.6), "far": P.slot(0.0, 9.0),
             "very_far": P.slot(0.2, 18.0)}
    return Scene(None, mid, slots=slots, baked_signs=bk.items, floor_y=slots["center"]["y"],
                 lights=[{"x": round(P.cx), "y": round(P.p(0, YT, 6)[1]), "color": "#bfe0ff"}])


# ------------------------------------------------------------------- 55. phòng điều khiển báo động đỏ
def _monitor(c, cx, base, w, h, rng, alert=False) -> None:
    c.drawRect(_R(cx - w * 0.06, base - h * 0.2, cx + w * 0.06, base), fill("#2a2e38"))
    c.drawPath(oval(cx, base, w * 0.22, h * 0.05), fill("#2a2e38"))
    t = base - h * 0.2 - h
    c.drawPath(rrect(cx - w / 2, t, cx + w / 2, t + h, 8), fill("#15171e"))
    vgrad(c, cx - w / 2 + 10, t + 10, cx + w / 2 - 10, t + h - 10, ["#0e2a48", "#081830"])
    for j in range(5):
        yy = t + 26 + j * (h - 40) / 5
        col = "#ff4a3a" if (alert and j == 1) else rng.choice(["#3ee08f", "#2fa8ff", "#8ab8d8"])
        c.drawRect(_R(cx - w / 2 + 24, yy, cx - w / 2 + 24 + (w - 60) * rng.uniform(0.3, 0.9), yy + 10), fill(col, 0.8))
    if alert:
        c.drawRect(_R(cx - w / 2 + 10, t + 10, cx + w / 2 - 10, t + h - 10), stroke("#ff3b30", 8))


def scene_phong_dieu_khien_bao_dong(tod: str) -> Scene:
    bk = _Bake()
    s = new_surface()
    c = s.getCanvas()
    rng = random.Random(55)
    FL = 1800
    c.drawRect(_R(0, 0, W, FL), fill("#1c2030"))
    _tile_grid(c, 0, 0, W, FL, 480, 360, "#232838", 4)
    # ống đỏ
    for (y, w_) in ((110, 34), (170, 22)):
        c.drawRect(_R(0, y - w_ / 2, W, y + w_ / 2), fill("#a8281f"))
        c.drawRect(_R(0, y - w_ / 2, W, y - w_ / 2 + 6), fill("#d8453a"))
        for x in range(200, W, 600):
            c.drawRect(_R(x, y - w_ / 2 - 8, x + 24, y + w_ / 2 + 8), fill("#6a1a14"))
    for x in (240, 3600):
        c.drawRect(_R(x - 20, 110, x + 20, FL), fill("#a8281f"))
        c.drawCircle(x, 900, 46, fill("#c8302a"))
        c.drawCircle(x, 900, 46, stroke("#6a1a14", 8))
        c.drawLine(x - 40, 900, x + 40, 900, stroke("#6a1a14", 8))
    # màn hình tường lớn: danh sách trạng thái
    DL, DR, DT, DB = 700, 3140, 260, 1060
    c.drawPath(rrect(DL - 30, DT - 30, DR + 30, DB + 30, 16), fill("#0c0e14"))
    vgrad(c, DL, DT, DR, DB, ["#0a1a30", "#06101e"])
    c.drawRect(_R(DL, DT, DR, DT + 110), fill("#c8302a"))
    bk.text(c, "ALERT", DL + 260, DT + 55, 72, "#ffffff")
    bk.text(c, "SYSTEM STATUS", DR - 420, DT + 55, 52, "#ffe0d8", max_w=700)
    for j in range(7):
        yy = DT + 150 + j * 108
        if j == 3:
            c.drawRect(_R(DL + 10, yy - 14, DR - 10, yy + 70), fill("#c8302a", 0.35))
        c.drawCircle(DL + 60, yy + 28, 18, fill("#ff3b30" if j in (3, 6) else ("#ffb02e" if j == 1 else "#3ee08f")))
        c.drawRect(_R(DL + 110, yy + 14, DL + 110 + rng.uniform(300, 700), yy + 42), fill("#8ab8d8", 0.7))
        c.drawRect(_R(DL + 1000, yy + 14, DL + 1000 + rng.uniform(200, 500), yy + 42), fill("#5a7a98", 0.7))
        c.drawRect(_R(DR - 400, yy + 10, DR - 400 + rng.uniform(100, 320), yy + 46), fill("#3ee08f" if j not in (3, 6) else "#ff3b30", 0.6))
    for (l, r) in ((330, 620), (3220, 3510)):            # màn phụ: đồ thị
        c.drawPath(rrect(l, 380, r, 760, 10), fill("#0c0e14"))
        c.drawRect(_R(l + 14, 394, r - 14, 746), fill("#08142a"))
        _ecg(c, l + 20, 520, r - 20, 60, "#3ee08f", 5, 140)
        _sine(c, l + 20, 650, r - 20, 30, "#ff6a5a", 4, 90)
    glow(c, (DL + DR) / 2, (DT + DB) / 2, 1500, "#3a6ab0", 0.2)
    # đèn báo động xoay đỏ
    beacons = [(520, 60), (1920, 60), (3320, 60)]
    for i, (bx, by) in enumerate(beacons):
        c.drawRect(_R(bx - 60, by - 60, bx + 60, by - 30), fill("#2a2e38"))
        c.drawPath(rrect(bx - 50, by - 30, bx + 50, by + 50, 40), fill("#ff2a1a"))
        ang = (0.6 if i % 2 else -0.6)
        for sgn in (-1, 1):
            a = math.pi / 2 + ang + sgn * 0.22
            ex_, ey_ = bx + math.cos(a) * 2200 * (1 if i != 1 else 0.9), by + math.sin(a) * 2200
            quad(c, [(bx, by + 10), (bx + 10, by + 10), (ex_ + 300, ey_), (ex_ - 300, ey_)], "#ff2a1a", 0.06)
        glow(c, bx, by + 10, 420, "#ff2a1a", 0.7)
    # dãy bàn điều khiển + màn hình
    DKT = 1480
    for (l, r) in ((360, 1760), (2080, 3480)):
        for j, mx in enumerate(range(int(l + 230), int(r), 470)):
            _monitor(c, mx, DKT, 380, 230, rng, alert=(j == 1))
        c.drawRect(_R(l, DKT, r, DKT + 30), fill("#5a606c"))
        c.drawRect(_R(l, DKT + 30, r, FL + 40), fill("#2e323c"))
        c.drawRect(_R(l, DKT + 30, r, DKT + 44), fill("#3e4450"))
        for x in range(int(l + 160), int(r), 470):
            c.drawPath(rrect(x, DKT - 20, x + 200, DKT, 4), fill("#1d1f24"))
            for b in range(3):
                c.drawCircle(x - 40 + b * 18, DKT + 90, 7, fill(rng.choice(["#3ee08f", "#ff3b30", "#ffb02e"])))
    _persp_floor(c, FL, "#14161e", "#1e2230", vx=1920, vy=1000, spacing=320, dz=0.1)
    tint(s, "#ff8a7a", 0.35)
    for (bx, by) in beacons:
        glow(c, bx, by + 10, 900, "#ff2a1a", 0.35)
        ellipse_glow(c, bx, FL + 120, 900, 150, "#ff2a1a", 0.25)
    c.drawRect(_R(0, 0, W, H), fill("#ff1a0a", 0.06))
    _vignette(c, 0.6)
    mid = s.makeImageSnapshot()
    slots = {"operator_left": {"x": 1060, "y": 1640, "scale": 0.9, "clip_bottom": DKT},
             "operator_right": {"x": 2780, "y": 1640, "scale": 0.9, "clip_bottom": DKT},
             "center": {"x": 1920, "y": 2080, "scale": 1.1}, "left": {"x": 800, "y": 2080, "scale": 1.1},
             "right": {"x": 3050, "y": 2080, "scale": 1.1}}
    return Scene(None, mid, slots=slots, baked_signs=bk.items, floor_y=2080,
                 lights=[{"x": bx, "y": by + 10, "color": "#ff2a1a"} for (bx, by) in beacons])


# ------------------------------------------------------------------- 56. trạm xe buýt ven đường lúc bình minh + bốt điện thoại
def _dawn_sky(c, t, b, sun_x, horizon) -> None:
    vgrad(c, 0, t, W, b, ["#2e2e6a", "#6a4a90", "#c87aa8", "#f6a8a0", "#ffd2a0"], [0, 0.35, 0.65, 0.85, 1])
    glow(c, sun_x, horizon, 900, "#ffd8a0", 0.45)
    glow(c, sun_x, horizon, 260, "#fff0c8", 0.7)
    c.drawCircle(sun_x, horizon, 110, fill("#fff2d0"))
    rng = random.Random(int(sun_x))
    for _ in range(9):
        x, y = rng.uniform(0, W), rng.uniform(t + 150, horizon - 300)
        c.drawPath(oval(x, y, rng.uniform(220, 520), rng.uniform(26, 50)), fill("#f6b8c0", rng.uniform(0.25, 0.5)))


def _payphone(c, bk: _Bake, x, base, k) -> None:
    c.drawRect(_R(x - 0.05 * k, base - 1.3 * k, x + 0.05 * k, base), fill("#5a6070"))
    c.drawRect(_R(x - 0.18 * k, base - 0.06 * k, x + 0.18 * k, base), fill("#4a5060"))
    hl, hr, ht, hb = x - 0.42 * k, x + 0.42 * k, base - 2.2 * k, base - 1.15 * k
    c.drawPath(rrect(hl, ht, hr, hb, 0.08 * k), fill("#2f6fb0"))
    c.drawPath(rrect(hl - 0.04 * k, ht - 0.06 * k, hr + 0.04 * k, ht + 0.16 * k, 0.06 * k), fill("#24588e"))
    bk.text(c, "PHONE", x, ht + 0.05 * k, 0.13 * k, "#ffffff", max_w=0.7 * k)
    bl, br, bt, bb = x - 0.22 * k, x + 0.22 * k, ht + 0.25 * k, hb - 0.06 * k
    c.drawPath(rrect(bl, bt, br, bb, 0.04 * k), fill("#c9ccd2"))
    c.drawRect(_R(bl + 0.05 * k, bt + 0.06 * k, br - 0.05 * k, bt + 0.16 * k), fill("#3a5a4a"))
    for r_ in range(4):
        for cc in range(3):
            c.drawCircle(bl + 0.1 * k + cc * 0.12 * k, bt + 0.3 * k + r_ * 0.1 * k, 0.03 * k, fill("#5a606a"))
    c.drawPath(capsule(br + 0.02 * k, bt + 0.05 * k, br + 0.02 * k, bt + 0.5 * k, 0.05 * k, 0.05 * k), fill("#1d1f24"))
    c.drawLine(br + 0.02 * k, bt + 0.5 * k, br - 0.05 * k, bb - 0.05 * k, stroke("#1d1f24", max(2.0, 0.015 * k)))


def scene_tram_xe_buyt_binh_minh(tod: str) -> Scene:
    bk = _Bake()
    sf = new_surface()
    c = sf.getCanvas()
    HZ = 1180
    _dawn_sky(c, 0, HZ + 20, 3000, HZ - 40)
    soft_hills(c, HZ, 240, "#7a5a8a", 561, n=5)
    soft_hills(c, HZ + 30, 120, "#5a4a78", 562, n=7)
    far = sf.makeImageSnapshot()
    s = new_surface()
    c = s.getCanvas()
    rng = random.Random(56)
    for i in range(22):                       # hàng cây xa
        x = i * 190 + rng.uniform(-40, 40)
        round_tree(c, x, HZ + 20, rng.uniform(70, 120), "#4a3e66", "#3a3052", seed=i + 560)
    c.drawRect(_R(0, HZ + 40, W, 1300), fill("#5e5a7a"))
    c.drawRect(_R(0, 1300, W, 1560), fill("#4a4660"))
    c.drawRect(_R(0, 1300, W, 1316), fill("#8a84a0"))
    for x in range(-80, W, 400):
        c.drawRect(_R(x, 1420, x + 220, 1436), fill("#f0c45a", 0.9))
    c.drawRect(_R(0, 1544, W, 1560), fill("#d8d0dc"))
    c.drawRect(_R(0, 1560, W, 1640), fill("#8a7e78"))
    vgrad(c, 0, 1640, W, H, ["#6a7a5a", "#4a6a48"])
    for _ in range(260):
        x, y = rng.uniform(0, W), rng.uniform(1650, H)
        h_ = (y - 1600) * 0.12 + 10
        c.drawLine(x, y, x + rng.uniform(-8, 8), y - h_, stroke(rng.choice(["#7a8a60", "#5a7a50", "#8a9a6a"]), 4))
    # cột điện + dây
    tops = []
    for (px, base, h_) in ((-100, 1300, 900), (1400, 1300, 900), (2900, 1300, 900)):
        power_pole(c, px, base - h_, base, "#3a3450", 24)
        tops.append((px, base - h_ + 50))
    for i in range(len(tops) - 1):
        for dy in (0, 70):
            sag_wire(c, tops[i][0] - 90, tops[i][1] + dy, tops[i + 1][0] - 90, tops[i + 1][1] + dy, 40, "#2a2440", 4)
            sag_wire(c, tops[i][0] + 90, tops[i][1] + dy, tops[i + 1][0] + 90, tops[i + 1][1] + dy, 40, "#2a2440", 4)
    sag_wire(c, tops[-1][0] - 90, tops[-1][1], W + 50, tops[-1][1] + 30, 30, "#2a2440", 4)
    # mái chờ xe buýt
    k = 360.0
    SL, SR, SB = 520, 1500, 1660
    roof_y = SB - 2.5 * k
    for x in (SL + 40, SR - 40):
        c.drawRect(_R(x - 16, roof_y, x + 16, SB), fill("#6a7080"))
    c.drawRect(_R(SL + 60, roof_y + 120, SR - 60, SB - 0.45 * k), fill("#cfe6ee", 0.35))
    c.drawRect(_R(SL + 60, roof_y + 120, SR - 60, SB - 0.45 * k), stroke("#6a7080", 8))
    c.drawPath(rrect(SR - 360, roof_y + 180, SR - 90, SB - 0.6 * k, 10), fill("#e8e0e8"))
    c.drawCircle(SR - 225, roof_y + 360, 80, fill("#c87aa8", 0.6))
    quad(c, [(SL - 60, roof_y + 30), (SR + 60, roof_y - 20), (SR + 60, roof_y + 30), (SL - 60, roof_y + 70)], "#3a5a8a")
    quad(c, [(SL - 60, roof_y + 70), (SR + 60, roof_y + 30), (SR + 60, roof_y + 46), (SL - 60, roof_y + 86)], "#2a4068")
    c.drawRect(_R(SL + 120, SB - 0.48 * k, SR - 120, SB - 0.42 * k), fill("#8a6a4a"))
    for x in (SL + 160, SR - 160):
        c.drawRect(_R(x - 8, SB - 0.42 * k, x + 8, SB), fill("#4a5060"))
    c.drawRect(_R(SL - 80, SB - 10, SR + 80, SB + 20), fill("#a89a98"))
    # biển trạm
    px = SR + 230
    c.drawRect(_R(px - 12, SB - 2.6 * k, px + 12, SB), fill("#6a7080"))
    c.drawPath(rrect(px - 0.4 * k, SB - 2.9 * k, px + 0.4 * k, SB - 2.4 * k, 12), fill("#2f6fb0"))
    c.drawPath(rrect(px - 0.37 * k, SB - 2.87 * k, px + 0.37 * k, SB - 2.43 * k, 10), stroke("#f4f6f8", 5))
    bk.text(c, "BUS STOP", px, SB - 2.65 * k, 0.15 * k, "#ffffff", max_w=0.66 * k)
    # bốt điện thoại công cộng
    _payphone(c, bk, 2750, 1720, 380.0)
    tint(s, "#e8b8d8", 0.18)
    glow(c, 3000, HZ - 40, 1400, "#ffd8a0", 0.18)
    _vignette(c, 0.35)
    mid = s.makeImageSnapshot()
    slots = {"center": {"x": 2000, "y": 2060, "scale": 1.0}, "left": {"x": 900, "y": 2060, "scale": 1.0},
             "right": {"x": 3300, "y": 2060, "scale": 1.0}, "bench": {"x": 1010, "y": SB, "scale": 0.8},
             "phone": {"x": 2580, "y": 1730, "scale": 0.85}}
    return Scene(far, mid, slots=slots, baked_signs=bk.items, floor_y=2060, parallax=(0.85, 1.0, 1.1),
                 lights=[{"x": 3000, "y": HZ - 40, "color": "#ffd8a0"}])


# ------------------------------------------------------------------- 57. sông lúc bình minh: đường chân trời + thuyền đuôi dài
def _longtail_boat(c, x0, x1, wl, k, hull="#6a4630", stripe="#2f8ac8", canopy="#d8423a") -> None:
    """Thuyền đuôi dài nhìn ngang: mũi cong vút bên phải, máy + trục dài ở đuôi trái. wl = mực nước."""
    L = x1 - x0
    p = skia.Path()
    p.moveTo(x0, wl - 0.45 * k)
    p.lineTo(x1 - L * 0.1, wl - 0.5 * k)
    p.quadTo(x1, wl - 0.6 * k, x1 + 0.1 * k, wl - 1.3 * k)
    p.quadTo(x1 - L * 0.02, wl - 0.2 * k, x1 - L * 0.16, wl + 0.08 * k)
    p.lineTo(x0 + L * 0.06, wl + 0.08 * k)
    p.close()
    path_fill(c, p, hull)
    c.drawLine(x0 + L * 0.03, wl - 0.3 * k, x1 - L * 0.06, wl - 0.36 * k, stroke(stripe, 0.07 * k))
    c.drawPath(capsule(x1 + 0.05 * k, wl - 1.25 * k, x1 + 0.12 * k, wl - 1.4 * k, 0.04 * k, 0.02 * k), fill("#f3c94e"))
    if canopy:
        for xx in (x0 + L * 0.3, x0 + L * 0.68):
            c.drawLine(xx, wl - 0.48 * k, xx, wl - 1.5 * k, stroke("#3a2a1e", 0.04 * k))
        quad(c, [(x0 + L * 0.25, wl - 1.5 * k), (x0 + L * 0.73, wl - 1.5 * k), (x0 + L * 0.76, wl - 1.38 * k),
                 (x0 + L * 0.22, wl - 1.38 * k)], canopy)
    c.drawPath(rrect(x0 - 0.1 * k, wl - 0.95 * k, x0 + 0.45 * k, wl - 0.5 * k, 0.08 * k), fill("#4a4e58"))
    c.drawLine(x0 + 0.1 * k, wl - 0.6 * k, x0 - 1.6 * k, wl + 0.15 * k, stroke("#2a2e38", 0.06 * k))
    c.drawPath(oval(x0 - 1.6 * k, wl + 0.15 * k, 0.2 * k, 0.06 * k), fill("#ffffff", 0.4))
    c.drawPath(oval((x0 + x1) / 2, wl + 0.12 * k, L * 0.55, 0.08 * k), fill("#000000", 0.18))


def scene_song_binh_minh_thanh_pho(tod: str) -> Scene:
    sf = new_surface()
    c = sf.getCanvas()
    HZ = 1000
    SX = 2400
    _dawn_sky(c, 0, HZ + 10, SX, HZ - 60)
    _skyline(c, HZ, 571, "#4a3a6e", 120, 460, lit="#ffd8a0", lit_p=0.05, beacons=True)
    _skyline(c, HZ, 572, "#5e4a7e", 60, 220, wmin=90, wmax=220)
    # cầu dây văng bên trái
    c.drawRect(_R(-20, HZ - 80, 1500, HZ - 56), fill("#3a2e58"))
    for tx in (420, 1100):
        quad(c, [(tx - 26, HZ - 56), (tx + 26, HZ - 56), (tx + 12, HZ - 520), (tx - 12, HZ - 520)], "#3a2e58")
        for j in range(1, 8):
            c.drawLine(tx, HZ - 500 + j * 40, tx - j * 48, HZ - 80, stroke("#3a2e58", 3))
            c.drawLine(tx, HZ - 500 + j * 40, tx + j * 48, HZ - 80, stroke("#3a2e58", 3))
    sky = sf.makeImageSnapshot()
    # mặt nước: phản chiếu bầu trời (lật) + vệt nắng
    c.save()
    c.clipRect(_R(0, HZ, W, H))
    c.translate(0, 2 * HZ)
    c.scale(1, -1)
    c.drawImage(_blurred(sky, 14), 0, 0, skia.SamplingOptions(), fill("#ffffff", 0.55))
    c.restore()
    vgrad(c, 0, HZ, W, H, [("#5a4a80", 0.35), ("#2a2450", 0.8)])
    rng = random.Random(57)
    for i in range(60):
        y = HZ + 12 + (i ** 1.5) * 2.0
        if y > H:
            break
        w_ = 60 + i * 9
        c.drawRect(_R(SX - w_ * rng.uniform(0.4, 1.0), y, SX + w_ * rng.uniform(0.4, 1.0), y + 4 + i * 0.25), fill("#ffe0b0", 0.55))
    for _ in range(140):
        x, y = rng.uniform(0, W), rng.uniform(HZ + 20, H)
        c.drawLine(x, y, x + rng.uniform(40, 160) * (y - HZ) / 600, y, stroke("#d8b8e0", 3, 0.35))
    far = sf.makeImageSnapshot()
    s = new_surface()
    c = s.getCanvas()
    _longtail_boat(c, 3000, 3330, HZ + 70, 70, canopy="#2f8ac8")
    _longtail_boat(c, 2700, 3000, HZ + 40, 40, hull="#4a3424", canopy=None)
    _longtail_boat(c, 350, 1850, 1560, 330, hull="#7a4a2e", stripe="#e8c23a", canopy="#c8352e")
    # bến gỗ tiền cảnh bên phải
    DT = 1880
    for x in range(2250, W + 100, 260):
        c.drawRect(_R(x - 24, DT, x + 24, H), fill("#3a2a1e"))
    c.drawRect(_R(2150, DT - 20, W + 20, DT + 70), fill("#8a6444"))
    for x in range(2160, W, 90):
        c.drawLine(x, DT - 20, x, DT + 70, stroke("#6a4a32", 4))
    c.drawRect(_R(2150, DT + 70, W + 20, DT + 100), fill("#5a3e2a"))
    for x in range(2250, W + 100, 520):
        c.drawRect(_R(x - 16, DT - 480, x + 16, DT - 20), fill("#5a3e2a"))
    c.drawRect(_R(2150, DT - 480, W + 20, DT - 450), fill("#6a4a32"))
    c.drawRect(_R(2150, DT - 260, W + 20, DT - 240), fill("#6a4a32"))
    tint(s, "#e8b0c8", 0.22)
    glow(c, SX, HZ - 60, 1600, "#ffd8a0", 0.15)
    _vignette(c, 0.35)
    mid = s.makeImageSnapshot()
    slots = {"pier_left": {"x": 2600, "y": DT + 20, "scale": 1.0}, "pier_right": {"x": 3300, "y": DT + 20, "scale": 1.0},
             "center": {"x": 2950, "y": DT + 20, "scale": 1.0},
             "boat": {"x": 1100, "y": 1470, "scale": 0.62, "clip_bottom": 1430}}
    return Scene(far, mid, slots=slots, floor_y=DT + 20, parallax=(0.85, 1.0, 1.1),
                 lights=[{"x": SX, "y": HZ - 60, "color": "#ffd8a0"}])


# ------------------------------------------------------------------- 58. quán net cũ
def scene_quan_net_cu(tod: str) -> Scene:
    bk = _Bake()
    P = Persp(f=1500, cx=W / 2, cy=1000, cam_h=1.45)
    XW, YT, Z0, ZB = 3.6, 2.8, 0.8, 12.5
    s = new_surface()
    c = s.getCanvas()
    rng = random.Random(58)
    wall = "#8aa89a"
    path_fill(c, P.plane_y(YT, -XW, XW, Z0, ZB), "#6e6e68")
    path_fill(c, P.plane_y(0, -XW, XW, Z0, ZB), "#9a8e76")
    _floor_tiles(c, P, -XW, XW, Z0, ZB, 0.5, "#766a54")
    for _ in range(30):
        x, z = rng.uniform(-3, 3), rng.uniform(1.5, 14)
        cx_, cy_ = P.p(x, 0, z)
        c.drawPath(oval(cx_, cy_, 0.5 * P.f / z, 0.1 * P.f / z), fill("#7a6a50", rng.uniform(0.1, 0.2)))
    path_fill(c, P.face_z(ZB, -XW, XW, 0, YT), wall)
    for sd in (-1, 1):
        path_fill(c, P.wall_x(sd * XW, Z0, ZB, 0, YT), shade(wall, -0.1 if sd < 0 else -0.05))
        path_fill(c, P.wall_x(sd * XW, Z0, ZB, 0, 0.9), shade(wall, -0.25))
    # tường cuối: poster + bảng NET CAFE + quầy
    for (x0, x1, col, shape) in ((-3.2, -2.2, "#3a4a8a", "c"), (-2.0, -1.0, "#8a2a3a", "t"), (1.2, 2.2, "#2a6a4a", "c"),
                                 (2.4, 3.3, "#5a3a7a", "t")):
        path_fill(c, P.face_z(ZB - 0.01, x0, x1, 1.3, 2.6), col)
        a_ = P.p((x0 + x1) / 2, 2.0, ZB - 0.02)
        r_ = 0.3 * P.f / ZB
        if shape == "c":
            c.drawCircle(a_[0], a_[1], r_, fill("#f3c94e", 0.8))
        else:
            quad(c, [(a_[0], a_[1] - r_), (a_[0] + r_, a_[1] + r_), (a_[0] - r_, a_[1] + r_)], "#e8e4dc")
    nx, ny = P.p(0.1, 2.55, ZB - 0.02)
    k = P.f / ZB
    c.drawPath(rrect(nx - 0.9 * k, ny - 0.22 * k, nx + 0.9 * k, ny + 0.22 * k, 10), fill("#1a1d26"))
    bk.text(c, "NET CAFE", nx, ny, 0.26 * k, "#ffffff", neon="#2fc4ff", max_w=1.6 * k)
    bk.text(c, "24H", nx, ny + 0.45 * k, 0.2 * k, "#ffb02e")
    path_fill(c, P.face_z(ZB - 0.8, -0.8, 0.9, 0, 1.05), "#7a4a2e")
    path_fill(c, P.plane_y(1.05, -0.85, 0.95, ZB - 1.4, ZB - 0.8), "#9a6a44")
    mx, my = P.p(0.5, 1.05, ZB - 1.0)
    c.drawPath(rrect(mx - 0.25 * k, my - 0.4 * k, mx + 0.25 * k, my - 0.02 * k, 6), fill("#d8d0b8"))
    c.drawRect(_R(mx - 0.2 * k, my - 0.36 * k, mx + 0.2 * k, my - 0.1 * k), fill("#2a6aa8"))
    # dãy máy tính dọc hai tường (màn hình hướng ra lối đi), ghế đỏ quay lưng
    glows = []
    for sd in (-1, 1):
        xd = sd * (XW - 0.75)
        path_fill(c, P.plane_y(0.75, sd * XW, xd, Z0, ZB - 1.6), "#8a6a4a")
        path_fill(c, P.wall_x(xd, Z0, ZB - 1.6, 0.0, 0.75), "#6a4e36")
        z = ZB - 2.4
        while z > 1.0:
            zc = z + 0.45
            path_fill(c, P.quad([(sd * (XW - 0.18), 0.78, zc - 0.32), (sd * (XW - 0.18), 0.78, zc + 0.32),
                                 (sd * (XW - 0.18), 1.25, zc + 0.32), (sd * (XW - 0.18), 1.25, zc - 0.32)]), "#d8d0b8")
            scr = rng.choice(["#2a6aa8", "#3a8a5a", "#6a3a8a", "#2a8aa8", "#1a2a4a"])
            path_fill(c, P.quad([(sd * (XW - 0.2), 0.82, zc - 0.27), (sd * (XW - 0.2), 0.82, zc + 0.27),
                                 (sd * (XW - 0.2), 1.21, zc + 0.27), (sd * (XW - 0.2), 1.21, zc - 0.27)]), scr)
            glows.append((P.p(sd * (XW - 0.3), 1.0, zc), scr, P.f / zc))
            path_fill(c, P.plane_y(0.76, sd * (XW - 0.6), sd * (XW - 0.3), zc - 0.25, zc + 0.25), "#2b2d33")
            if rng.random() < 0.85:
                cxs = sd * (XW - 1.25)
                path_fill(c, P.wall_x(cxs, zc - 0.25, zc + 0.25, 0.45, 1.25), "#c8302a")
                path_fill(c, P.wall_x(cxs + sd * 0.02, zc - 0.22, zc + 0.22, 0.5, 1.2), "#a8241f")
                path_fill(c, P.plane_y(0.45, cxs, cxs + sd * 0.45, zc - 0.25, zc + 0.25), "#8a1f1a")
                c.drawLine(*P.p(cxs + sd * 0.2, 0.45, zc), *P.p(cxs + sd * 0.2, 0.05, zc), stroke("#2b2d33", max(2.0, 0.04 * P.f / zc)))
            z -= 1.0
    # quạt trần + đèn tuýp
    for zz in (3.0, 6.0, 9.0):
        hx, hy = P.p(0, YT, zz)
        k_ = P.f / zz
        c.drawLine(hx, hy, hx, hy + 0.3 * k_, stroke("#3a3a40", max(2.0, 0.04 * k_)))
        c.drawPath(oval(hx, hy + 0.32 * k_, 0.1 * k_, 0.04 * k_), fill("#3a3a40"))
        for sgn in (-1, 1):
            c.drawPath(oval(hx + sgn * 0.38 * k_, hy + 0.34 * k_, 0.32 * k_, 0.03 * k_), fill("#4a4a50"))
        for xx in (-1.8, 1.8):
            path_fill(c, P.plane_y(YT - 0.01, xx - 0.6, xx + 0.6, zz + 0.6, zz + 0.72), "#eef6ff")
    tint(s, "#3a4878", 0.55)
    darken(c, 0.22)
    for ((gx, gy), col, k_) in glows:
        glow(c, gx, gy, 0.8 * k_, "#8ac8ff", 0.4)
    glow(c, nx, ny, 700, "#2fc4ff", 0.25)
    _vignette(c, 0.55)
    mid = s.makeImageSnapshot()
    slots = {"center": P.slot(0, 2.8), "left": P.slot(-0.9, 3.4), "right": P.slot(0.9, 3.4), "far": P.slot(0.0, 9.0),
             "counter": {**P.slot(0.2, ZB - 1.6), "clip_bottom": round(P.p(0, 1.05, ZB - 0.8)[1])}}
    return Scene(None, mid, slots=slots, baked_signs=bk.items, floor_y=slots["center"]["y"],
                 lights=[{"x": round(nx), "y": round(ny), "color": "#2fc4ff"}])


LIBRARY_SCENES: dict[str, Callable[[str], Scene]] = {
    "cua_hang_quay_pov": scene_cua_hang_quay_pov,
    "cua_hang_tu_lanh": scene_cua_hang_tu_lanh,
    "ben_xe_buyt_ngay": scene_ben_xe_buyt_ngay,
    "duong_que_dem_mua": scene_duong_que_dem_mua,
    "xe_khach_tren_duong": scene_xe_khach_tren_duong,
    "hem_toi_pho": scene_hem_toi_pho,
    "cho_dem_viet": scene_cho_dem_viet,
    "nha_phong_khach": scene_nha_phong_khach,
    "phong_ngu_tro": scene_phong_ngu_tro,
    "hanh_lang_benh_vien": scene_hanh_lang_benh_vien,
    "hanh_lang_chung_cu": scene_hanh_lang_chung_cu,
    "lop_hoc": scene_lop_hoc,
    "don_cong_an": scene_don_cong_an,
    "san_chua": scene_san_chua,
    "bo_song_dem": scene_bo_song_dem,
    "cua_hang_cctv_tren_cao": scene_cua_hang_cctv_tren_cao,
    # lô 2
    "bep_nha_hang": scene_bep_nha_hang,
    "kho_lanh": scene_kho_lanh,
    "san_thuong_binh_minh": scene_san_thuong_binh_minh,
    "hem_nha_pho_dien": scene_hem_nha_pho_dien,
    "phong_truong_cong_an": scene_phong_truong_cong_an,
    "phong_icu": scene_phong_icu,
    "cho_co_mai": scene_cho_co_mai,
    "phong_dieu_tra": scene_phong_dieu_tra,
    "ben_go_nha_san": scene_ben_go_nha_san,
    "tiem_tap_hoa_dem": scene_tiem_tap_hoa_dem,
    "toa_an": scene_toa_an,
    "phong_ky_tuc_xa": scene_phong_ky_tuc_xa,
    # lô 3
    "nha_ve_sinh_nu_truong": scene_nha_ve_sinh_nu_truong,
    "lop_hoc_cu_dem": scene_lop_hoc_cu_dem,
    "truong_hoc_dem": scene_truong_hoc_dem,
    "sanh_tu_giay_truong": scene_sanh_tu_giay_truong,
    "pho_dan_cu_may_ban_nuoc": scene_pho_dan_cu_may_ban_nuoc,
    "loi_di_dai_dem": scene_loi_di_dai_dem,
    "nha_tro_hai_tang": scene_nha_tro_hai_tang,
    "phong_chieu_tatami": scene_phong_chieu_tatami,
    "bep_quan_mi": scene_bep_quan_mi,
    "phong_ngu_tv_cu": scene_phong_ngu_tv_cu,
    # lô 4
    "tang_trung_tam_dien_thoai": scene_tang_trung_tam_dien_thoai,
    "sanh_thang_cuon": scene_sanh_thang_cuon,
    "pho_nha_pho_dem": scene_pho_nha_pho_dem,
    "ham_xe_b2": scene_ham_xe_b2,
    "quan_mi_xe_day_dem": scene_quan_mi_xe_day_dem,
    "tiem_giat_24h": scene_tiem_giat_24h,
    "trung_tam_du_lieu_dem": scene_trung_tam_du_lieu_dem,
    "phong_may_chu": scene_phong_may_chu,
    "phong_dieu_khien_bao_dong": scene_phong_dieu_khien_bao_dong,
    "tram_xe_buyt_binh_minh": scene_tram_xe_buyt_binh_minh,
    "song_binh_minh_thanh_pho": scene_song_binh_minh_thanh_pho,
    "quan_net_cu": scene_quan_net_cu,
}

# Thẻ tìm kiếm song ngữ cho cảnh thư viện (metadata, không vẽ vào ảnh).
LIBRARY_TAGS: dict[str, list[str]] = {
    "cua_hang_quay_pov": ["quầy thu ngân", "góc nhìn nhân viên", "pov", "counter", "cửa hàng", "ló đầu"],
    "cua_hang_tu_lanh": ["tủ lạnh", "đồ uống", "cửa kính", "sương", "fridge", "cửa hàng"],
    "ben_xe_buyt_ngay": ["trạm xe buýt", "bus stop", "phố", "vỉa hè", "nhà phố", "ban ngày"],
    "duong_que_dem_mua": ["đường quê", "kênh", "mưa", "đèn đường", "rural road", "canal"],
    "xe_khach_tren_duong": ["xe khách", "xe 16 chỗ", "đường quê", "van", "trên xe"],
    "hem_toi_pho": ["hẻm", "ngõ", "hẻm tối", "alley", "nhà ống", "dây điện"],
    "cho_dem_viet": ["chợ đêm", "sạp", "xe đẩy", "night market", "ghế nhựa", "đèn dây"],
    "nha_phong_khach": ["phòng khách", "nhà", "bàn thờ", "tivi", "living room", "nhà phố"],
    "phong_ngu_tro": ["phòng ngủ", "phòng trọ", "giường", "màn", "bedroom", "ánh trăng"],
    "hanh_lang_benh_vien": ["bệnh viện", "hành lang", "xe lăn", "hospital", "corridor", "lối thoát"],
    "hanh_lang_chung_cu": ["chung cư", "hành lang", "nhà trọ", "apartment", "cửa sắt", "lan can"],
    "lop_hoc": ["lớp học", "trường", "bảng đen", "classroom", "school", "bàn ghế"],
    "don_cong_an": ["đồn công an", "công an", "văn phòng", "police", "khai báo", "bàn làm việc"],
    "san_chua": ["chùa", "miếu", "sân chùa", "lư hương", "temple", "pagoda", "cây đa"],
    "bo_song_dem": ["bờ sông", "bến nước", "sông", "xuồng", "river", "dừa nước", "trăng"],
    "cua_hang_cctv_tren_cao": ["camera an ninh", "cctv", "góc trên cao", "cửa hàng", "giám sát", "security camera"],
    # lô 2
    "bep_nha_hang": ["bếp", "bếp nhà hàng", "kho đông", "cửa kho lạnh", "dao thớt", "kitchen", "restaurant kitchen", "freezer door"],
    "kho_lanh": ["kho lạnh", "kho đông", "tủ đông", "băng giá", "đồ thất lạc", "cold room", "walk-in freezer", "frost"],
    "san_thuong_binh_minh": ["sân thượng", "mái nhà", "bình minh", "dây phơi", "bồn nước", "rooftop", "dawn", "skyline"],
    "hem_nha_pho_dien": ["hẻm", "phố", "dây điện", "miếu nhỏ", "xe máy", "sương mù", "alley", "shophouse", "spirit house", "fog"],
    "phong_truong_cong_an": ["công an", "trưởng đồn", "văn phòng", "bàn làm việc", "giấy khen", "police chief", "office"],
    "phong_icu": ["bệnh viện", "hồi sức", "icu", "giường bệnh", "máy thở", "monitor", "hospital room"],
    "cho_co_mai": ["chợ", "chợ có mái", "sạp thịt", "sạp cá", "rau quả", "wet market", "butcher", "market"],
    "phong_dieu_tra": ["điều tra", "bảng ghim", "dây đỏ", "người mất tích", "bàn laptop", "investigation", "cork board"],
    "ben_go_nha_san": ["bến gỗ", "nhà sàn", "bờ sông", "cầu", "đèn đường", "pier", "stilt houses", "river"],
    "tiem_tap_hoa_dem": ["tiệm tạp hoá", "cửa cuốn", "quầy", "đồ ăn vặt", "snack shop", "grocery", "shop front"],
    "toa_an": ["toà án", "mặt tiền", "hàng cột", "bậc thềm", "court", "courthouse", "government building"],
    "phong_ky_tuc_xa": ["ký túc xá", "phòng trọ", "vali", "chuyển nhà", "thùng giấy", "dorm room", "suitcases"],
    # lô 3
    "nha_ve_sinh_nu_truong": ["nhà vệ sinh", "toilet nữ", "trường học", "buồng vệ sinh", "gương", "sàn ướt", "school toilet",
                              "girls restroom", "toilet stall", "ma học đường"],
    "lop_hoc_cu_dem": ["lớp học", "lớp học cũ", "trường học", "bàn ghế", "bảng đen", "đồng hồ", "tủ cá nhân", "classroom",
                       "old classroom", "lockers", "school at night"],
    "truong_hoc_dem": ["trường học", "trường tiểu học", "tháp đồng hồ", "hàng rào", "cổng trường", "school exterior",
                       "elementary school", "clock tower", "school gate"],
    "sanh_tu_giay_truong": ["tủ giày", "sảnh trường", "lối vào", "dép đi trong nhà", "bảng thông báo", "shoe lockers",
                            "school entrance", "notice board", "glass doors"],
    "pho_dan_cu_may_ban_nuoc": ["phố dân cư", "máy bán nước", "cột điện", "đèn đường", "gương cầu", "cổng đền", "tường rào",
                                "residential street", "vending machines", "utility pole", "curved mirror", "shrine gate"],
    "loi_di_dai_dem": ["lối đi", "hẻm dài", "cột đèn", "tường bê tông", "một điểm tụ", "long walkway", "night alley",
                       "lamp posts"],
    "nha_tro_hai_tang": ["nhà trọ", "chung cư cũ", "cầu thang sắt", "xe đạp", "hộp thư", "số phòng", "apartment exterior",
                         "external stairs", "bicycles", "two-storey"],
    "phong_chieu_tatami": ["phòng chiếu", "tatami", "cửa trượt", "đèn lồng giấy", "bàn thấp", "lịch treo tường",
                           "tatami room", "sliding door", "paper lantern", "low table"],
    "bep_quan_mi": ["bếp", "quán mì", "nồi nước dùng", "thực đơn", "rèm cửa", "chồng bát", "ramen kitchen",
                    "noodle shop", "stock pot", "menu tags", "noren"],
    "phong_ngu_tv_cu": ["phòng ngủ", "phòng tối", "tivi cũ", "nhiễu sóng", "chăn nệm gấp", "dark bedroom", "crt tv",
                        "tv static", "futons"],
    # lô 4
    "tang_trung_tam_dien_thoai": ["trung tâm điện thoại", "sửa điện thoại", "ki-ốt", "ốp lưng", "dán màn hình", "nạp thẻ",
                                  "trung tâm thương mại", "cửa cuốn", "phone mall", "phone repair", "kiosk", "case shop",
                                  "mall corridor", "shutters"],
    "sanh_thang_cuon": ["thang cuốn", "thang máy", "sảnh", "trung tâm thương mại", "hộp đèn quảng cáo", "escalator",
                        "elevator", "mall lobby", "ad lightbox"],
    "pho_nha_pho_dem": ["phố", "nhà phố", "biển hiệu", "đường trên cao", "xe máy", "mưa", "city street", "shophouses",
                        "neon signs", "elevated road", "rain"],
    "ham_xe_b2": ["hầm xe", "bãi đỗ xe ngầm", "tầng hầm", "cột bê tông", "ô tô", "underground parking", "car park",
                  "basement", "b2", "pillars"],
    "quan_mi_xe_day_dem": ["chợ đêm", "xe mì", "xe đẩy", "ghế nhựa", "bàn gấp", "đèn dây", "xe trái cây", "night market",
                           "noodle cart", "street food", "plastic stools"],
    "tiem_giat_24h": ["tiệm giặt", "máy giặt", "máy sấy", "giặt tự động", "máy bán bột giặt", "laundromat", "laundry",
                      "washing machines", "storefront", "24h"],
    "trung_tam_du_lieu_dem": ["trung tâm dữ liệu", "hàng rào", "kẽm gai", "cổng", "đèn pha", "khu vực cấm", "data center",
                              "fence", "barbed wire", "restricted area", "floodlights"],
    "phong_may_chu": ["phòng máy chủ", "tủ rack", "máy chủ", "đèn led", "máng cáp", "server room", "server racks",
                      "data hall", "cable trays"],
    "phong_dieu_khien_bao_dong": ["phòng điều khiển", "báo động", "đèn đỏ", "màn hình", "ống đỏ", "control room", "alarm",
                                  "red alert", "monitors", "status wall"],
    "tram_xe_buyt_binh_minh": ["trạm xe buýt", "bốt điện thoại", "ven đường", "bình minh", "đồng cỏ", "bus stop", "payphone",
                               "roadside", "dawn", "countryside"],
    "song_binh_minh_thanh_pho": ["sông", "bình minh", "thành phố", "thuyền đuôi dài", "cầu dây văng", "bến gỗ", "river",
                                 "dawn", "skyline", "long-tail boat", "pier"],
    "quan_net_cu": ["quán net", "tiệm internet", "máy tính", "ghế đỏ", "quạt trần", "internet cafe", "pc cafe",
                    "computers", "gaming"],
}


SCENES: dict[str, Callable[[str], Scene]] = {
    "cua_hang_loi_ke": scene_cua_hang_loi_ke,
    "cua_hang_quay_thu_ngan": scene_cua_hang_quay_thu_ngan,
    "cua_hang_cua_kinh_tu_trong": scene_cua_hang_cua_kinh_tu_trong,
    "cua_hang_mat_tien_dem": scene_cua_hang_mat_tien_dem,
    "cua_hang_cua_cuon_dong": scene_cua_hang_cua_cuon_dong,
    "phong_nhan_vien": scene_phong_nhan_vien,
    "cho_xe_om_ven_duong": scene_cho_xe_om_ven_duong,
    "nen_toi_truu_tuong": scene_nen_toi_truu_tuong,
}

TOD_VI = {"day": "ban ngày", "night": "ban đêm", "dusk": "hoàng hôn", "indoor": "trong nhà đèn sáng",
          "dawn": "bình minh", "fog": "sáng sớm sương mù",
          "closeup": "ban đêm, cận cảnh", "side": "ban đêm, góc bên",
          "angle": "trong nhà, góc nghiêng", "corridor": "trong nhà, hành lang dài", "closed": "ban đêm, đã đóng cửa",
          "rain": "ban đêm, mưa", "exterior": "ban đêm, mặt tiền ngoài"}
TOD_EN = {"day": "day", "night": "night", "dusk": "dusk", "indoor": "interior", "dawn": "dawn", "fog": "foggy morning",
          "closeup": "night, close-up", "side": "night, side angle",
          "angle": "interior, side angle", "corridor": "interior, long corridor", "closed": "night, shutters down",
          "rain": "night, rain", "exterior": "night, exterior"}
# schema.LocationDef chỉ nhận day/night/dusk/indoor -> biến thể mới quy về mốc gần nhất.
# Lô 3: biến thể khung hình 'closeup' (cận cửa buồng) / 'side' (góc bên có tủ) là cảnh đêm.
TOD_SCHEMA = {"day": "day", "night": "night", "dusk": "dusk", "indoor": "indoor", "dawn": "dusk", "fog": "day",
              "closeup": "night", "side": "night",
              # lô 4: biến thể khung hình / trạng thái
              "angle": "indoor", "corridor": "indoor", "closed": "night", "rain": "night", "exterior": "night"}


# =================================================================== catalog -> thư mục tài sản
def load_catalog() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def catalog_entry(lid: str) -> dict | None:
    return next((e for e in load_catalog()["locations"] if e["id"] == lid), None)


def variant_ids(entry: dict) -> list[tuple[str, str]]:
    """[(asset_id, tod)] — biến thể đầu tiên giữ id gốc."""
    tv = entry.get("time_variants") or ["night"]
    return [(entry["id"] if i == 0 else f"{entry['id']}__{t}", t) for i, t in enumerate(tv)]


def _tags(entry: dict, tod: str) -> list[str]:
    base = [w for w in entry["kind"].split("_")]
    extra = {
        "store": ["cửa hàng", "tạp hoá", "cửa hàng tiện lợi", "24h", "shop"],
        "staff": ["phòng nhân viên", "văn phòng", "phòng sau", "kho"],
        "roadside": ["xe ôm", "trạm chờ", "ven đường", "đường quê"],
        "abstract": ["nền tối", "trừu tượng", "chèn", "thoại"],
    }
    tags = []
    for k, v in extra.items():
        if entry["kind"].startswith(k):
            tags += v
    words = {"aisle": ["lối kệ", "kệ hàng"], "counter": ["quầy", "thu ngân"], "entrance": ["cửa kính", "cửa ra vào"],
             "exterior": ["mặt tiền", "toàn cảnh", "bãi đỗ"], "shutter": ["cửa cuốn", "đóng cửa", "mặt tiền"],
             "shelter": ["chòi", "mái che"]}
    for w in base:
        tags += words.get(w, [])
    tags.append(TOD_VI.get(tod, tod))
    tags.append(tod)
    return list(dict.fromkeys(tags))


def location_meta(entry: dict, tod: str, aid: str, scene: Scene | None) -> dict:
    label = f"{entry['name_vi']} ({TOD_VI.get(tod, tod)})"
    tags = _tags(entry, tod)
    meta = {
        "id": aid,
        "name": entry["name_vi"],
        "size": [W, H],
        "time_of_day": TOD_SCHEMA.get(tod, "night"),
        "bg": "bg.png",
        "profile": {
            "label": label,
            "description": ", ".join([entry["name_vi"], TOD_VI.get(tod, tod)] + tags),
            "kind": entry["kind"],
            "tags": tags,
            "time_variants": [v for v, _ in variant_ids(entry)],
            "catalog_id": entry["id"],
            "variant": tod,
            "style": "cutout",
        },
        "flow_prompt": f"{entry['flow_prompt']}, {load_catalog().get('style_suffix', '')}".strip(", "),
        "provenance": {"kind": "procedural", "generator": "storytoon.render.locgen", "catalog_id": entry["id"]},
    }
    if scene is not None:
        meta["floor_y"] = round(scene.floor_y)
        meta["slots"] = scene.slots
        meta["signs"] = scene.signs
        if scene.baked_signs:
            meta["baked_signs"] = scene.baked_signs
        if scene.lights:
            meta["lights"] = scene.lights
        if scene.far is not None or scene.near is not None:
            lay = {}
            if scene.far is not None:
                lay["far"] = {"image": "bg_far.png", "parallax": scene.parallax[0]}
            lay["mid"] = {"image": "bg_mid.png", "parallax": scene.parallax[1]}
            if scene.near is not None:
                lay["near"] = {"image": "bg_near.png", "parallax": scene.parallax[2]}
            if "far" not in lay:      # location.py cần cả far+mid để dùng lớp -> mid là far, bg trong suốt không cần
                lay = {"far": {"image": "bg_mid.png", "parallax": 1.0}, "mid": {"image": "bg_empty.png", "parallax": 1.0},
                       "near": lay["near"]}
            meta["layers"] = lay
    return meta


def _write_scene(folder: Path, scene: Scene) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for stale in ("bg_far.png", "bg_mid.png", "bg_near.png", "bg_empty.png"):
        (folder / stale).unlink(missing_ok=True)
    save_png(scene.composite(), folder / "bg.png")
    if scene.far is not None or scene.near is not None:
        if scene.far is not None:
            save_png(scene.far, folder / "bg_far.png")
            save_png(scene.mid, folder / "bg_mid.png")
        else:
            save_png(scene.mid, folder / "bg_mid.png")
            save_png(new_surface(8, 8).makeImageSnapshot(), folder / "bg_empty.png")
        if scene.near is not None:
            save_png(scene.near, folder / "bg_near.png")


def render_scene(lid: str, tod: str | None = None) -> Scene:
    entry = catalog_entry(lid)
    if lid not in SCENES or entry is None:
        raise KeyError(f"locgen không có cảnh procedural '{lid}'")
    tod = tod or (entry.get("time_variants") or ["night"])[0]
    return SCENES[lid](tod)


def make_location(lid: str, out_root: Path = LOCATIONS) -> Path:
    """Sinh 1 địa điểm (`<id>` hoặc `<id>__<variant>`) vào out_root/<lid>/. Trả về thư mục."""
    base, _, tod = lid.partition("__")
    entry = catalog_entry(base)
    if entry is None:
        raise KeyError(f"'{base}' không có trong {CATALOG}")
    tod = tod or (entry.get("time_variants") or ["night"])[0]
    folder = Path(out_root) / lid
    if base not in SCENES:
        return make_location_stub(entry, out_root)
    scene = SCENES[base](tod)
    _write_scene(folder, scene)
    meta = location_meta(entry, tod, lid, scene)
    (folder / "location.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    log.info("locgen: %s (%s) -> %s", lid, tod, folder)
    return folder


def make_location_stub(entry: dict, out_root: Path = LOCATIONS) -> Path:
    """Địa điểm chưa vẽ bằng code: chỉ location.json + flow_prompt (chờ Google Flow tạo bg.png).
    Không ghi đè slot/bg nếu thư mục đã có ảnh nền."""
    folder = Path(out_root) / entry["id"]
    folder.mkdir(parents=True, exist_ok=True)
    tod = (entry.get("time_variants") or ["night"])[0]
    meta = location_meta(entry, tod, entry["id"], None)
    meta["slots"] = {k: frac_slot(v) for k, v in entry.get("slots", {}).items()}
    meta["floor_y"] = round(max((v["y"] for v in entry.get("slots", {}).values()), default=0.87) * H)
    meta["signs"] = []
    meta["sign_texts"] = [s["text"] for s in entry.get("signs", [])]
    meta["flow_prompts"] = _flow_prompts(entry)
    meta["status"] = "needs_image"
    meta["provenance"] = {"kind": "flow_pending", "catalog_id": entry["id"]}
    meta["profile"]["layout"] = entry.get("layout", "")
    old = folder / "location.json"
    if old.exists():
        try:
            prev = json.loads(old.read_text(encoding="utf-8"))
            if (folder / prev.get("bg", "bg.png")).exists():
                prev.setdefault("flow_prompts", meta["flow_prompts"])
                meta = prev
                meta.pop("status", None)
        except (OSError, ValueError):
            pass
    old.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return folder


TOD_FLOW = {"day": "overcast daytime light", "night": "night, deep navy darkness, few light sources",
            "dusk": "dusk, indigo to mauve sky", "indoor": "bright cold fluorescent interior light",
            "dawn": "dawn, lilac sky fading to peach horizon", "fog": "hazy early morning, thick beige-grey fog",
            "closeup": "night, tight close-up framing", "side": "night, side view",
            "angle": "bright mall interior, side angle", "corridor": "bright mall interior, long one-point corridor",
            "closed": "night, shutters down, dim security lights", "rain": "night, heavy rain, wet reflections",
            "exterior": "night, storefront exterior"}


def _flow_prompts(entry: dict) -> dict:
    suffix = load_catalog().get("style_suffix", "")
    tod = (entry.get("time_variants") or ["night"])[0]
    return {t: f"{entry['flow_prompt']}, {TOD_FLOW.get(t, '')}, {suffix}".replace(", ,", ",")
            for t in entry.get("time_variants") or [tod]}


def make_library_location(lid: str, out_root: Path = LOCATIONS) -> Path:
    """Cảnh thư viện mở rộng (catalog procedural=false nhưng có LIBRARY_SCENES): vẽ bg.png bằng code,
    chữ biển hiệu tiếng Anh ở lớp `signs`, provenance 'procedural_library'."""
    base, _, tod = lid.partition("__")
    entry = catalog_entry(base)
    if entry is None or base not in LIBRARY_SCENES:
        raise KeyError(f"locgen không có cảnh thư viện '{base}'")
    tod = tod or (entry.get("time_variants") or ["night"])[0]
    scene = LIBRARY_SCENES[base](tod)
    folder = Path(out_root) / lid
    _write_scene(folder, scene)
    meta = location_meta(entry, tod, lid, scene)
    prof = meta["profile"]
    tags = list(dict.fromkeys(LIBRARY_TAGS.get(base, []) + prof["tags"]))
    prof["tags"] = tags
    prof["description"] = ", ".join([entry["name_vi"], TOD_VI.get(tod, tod)] + tags)
    if entry.get("library_variants"):
        prof["time_variants"] = [v for v, _ in variant_ids(entry)]
    else:
        prof["time_variants"] = sorted(p.name for p in Path(out_root).glob(f"{base}*")
                                       if p.name == base or p.name.startswith(base + "__")) or [lid]
    prof["layout"] = entry.get("layout", "")
    if entry.get("name_en"):        # nhãn/mô tả song ngữ (cảnh lô 2)
        prof["label"] = f"{entry['name_vi']} / {entry['name_en']} ({TOD_VI.get(tod, tod)} / {TOD_EN.get(tod, tod)})"
        prof["label_en"] = f"{entry['name_en']} ({TOD_EN.get(tod, tod)})"
        prof["description"] = (f"{entry['name_vi']}, {TOD_VI.get(tod, tod)}. {entry.get('description_en', entry['name_en'])}"
                               f" ({TOD_EN.get(tod, tod)}). " + ", ".join(tags))
        prof["description_en"] = entry.get("description_en", entry["name_en"])
    if scene.baked_signs:
        prof["baked_text"] = list(dict.fromkeys(b["text"] for b in scene.baked_signs))
    prof["time_of_day"] = meta["time_of_day"]
    meta["flow_prompts"] = _flow_prompts(entry)
    meta["sign_texts"] = [sg["text"] for sg in scene.signs]
    meta["provenance"] = {"kind": "procedural_library", "generator": "storytoon.render.locgen", "catalog_id": base}
    (folder / "location.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    log.info("locgen: thư viện %s (%s) -> %s", lid, tod, folder)
    return folder


def make_catalog_locations(out_root: Path = LOCATIONS, only: list[str] | None = None) -> list[Path]:
    """Mọi địa điểm trong catalog: procedural -> vẽ đủ biến thể; có cảnh thư viện -> vẽ biến thể gốc;
    còn lại -> location.json chờ Flow."""
    out: list[Path] = []
    for entry in load_catalog()["locations"]:
        if only and entry["id"] not in only:
            continue
        if entry.get("procedural") and entry["id"] in SCENES:
            for aid, _tod in variant_ids(entry):
                try:
                    out.append(make_location(aid, out_root))
                except Exception as e:  # noqa: BLE001 — 1 cảnh lỗi không được chặn cả thư viện
                    log.warning("locgen: lỗi khi vẽ %s: %s", aid, e)
        elif entry["id"] in LIBRARY_SCENES:
            # cảnh thư viện: chỉ biến thể gốc, trừ khi catalog bật "library_variants" (vẽ mọi biến thể)
            ids = [aid for aid, _ in variant_ids(entry)] if entry.get("library_variants") else [entry["id"]]
            for aid in ids:
                try:
                    out.append(make_library_location(aid, out_root))
                except Exception as e:  # noqa: BLE001
                    log.warning("locgen: lỗi khi vẽ %s: %s", aid, e)
                    if aid == entry["id"]:
                        out.append(make_location_stub(entry, out_root))
        else:
            out.append(make_location_stub(entry, out_root))
    return out


def preview(lid: str, tod: str | None = None, with_signs: bool = True) -> skia.Image:
    if lid in LIBRARY_SCENES:
        entry = catalog_entry(lid) or {}
        return LIBRARY_SCENES[lid](tod or (entry.get("time_variants") or ["night"])[0]).composite(with_signs)
    return render_scene(lid, tod).composite(with_signs=with_signs)
