"""Sinh nhân vật puppet vector phẳng (cutout) bằng skia — tham số hoá, theo docs/STYLE_GUIDE.md.

Phiên bản 2 (thư viện nguyên mẫu gốc):
- Đầu to hình trứng không viền, mắt chấm đen + chấm sáng, quầng mắt, má hồng, cổ dài có 2 nét gân,
  tay áo phồng tách rời kiểu mảnh cắt, tay găng (mitten), chân dài mảnh, tô phẳng 2 tông + gradient mép.
- Kiểu tóc / trang phục / phụ kiện theo STYLE_GUIDE §3–§5, biểu cảm + FX theo §2 (12 biểu cảm `schema.Expression`).
- Ảnh nhìn sau lưng (`view: back`) cho cảnh qua vai: head_back, hair_back_view, torso_back, backpack_back.

API công khai:
    make_character(cid, params) -> Path                         (giữ nguyên chữ ký cũ, nhận cả tham số v1)
    params_from_archetype(archetype: dict) -> CharParams
    make_archetype(archetype_id, out_root=CHARACTERS) -> Path
    make_all_archetypes(out_root=CHARACTERS) -> list[Path]
    render_portrait(cid, size=(600, 760), expression="neutral") -> skia.Image
    render_hand(kind, sleeve, skin, scale=1.0) -> skia.Image      (tay POV to, vào từ đáy khung)
    render_figure(cid, ...) -> skia.Image                         (ảnh xem trước / contact sheet)
    params_from_description(desc, gender, age) -> CharParams

Quy ước canvas (giống v1): rộng 600 đơn vị, chân ở y = 1000·height_scale (≥1000), nhân vật đứng giữa x=300.
Ảnh bộ phận vẽ gấp `image_scale` (=SS) lần. Hậu tố `_r` = tay/chân bên phải màn hình (phía nhân vật "hướng
mặt" khi facing=right), `_l` = bên trái. Nhân vật vẽ gần chính diện (hơi nghiêng 3/4 về bên phải).
"""
from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Callable, Literal

import numpy as np
import skia

from ..paths import ASSETS, CHARACTERS
from .skutil import (capsule, circle, color, diff, font, inter, mix, offset, oval, poly, rrect, save_png, smooth,
                     to_rgba, union)

log = logging.getLogger("storytoon.render")

W = 600
SS = 3                      # image_scale
GENERATOR = "puppetgen"
GENERATOR_VERSION = 2
CATALOG_FILE = ASSETS / "catalog" / "archetypes.json"

LINE_INK = "#3a2226"        # nét miệng / mí
EYE_INK = "#141016"
WHITE = "#fbfaf6"
TEETH = "#f7f3ea"
MOUTH_IN = "#3b1418"
TONGUE = "#d0646c"
SWEAT = "#a9c4dc"
DASH = "#b9d3e6"
TEAR = "#cfe6f5"
VEIN = "#d0302a"
DRIP = "#9fc3dd"
BLUSH = "#ec7f86"

HAIR_STYLES = ("spiky", "short_side_part", "buzz", "bald", "curly_short", "afro_curly", "long_straight",
               "long_ponytail", "bob_bangs", "long_over_face", "bun", "grey_short", "cap_hidden", "none_entity",
               "slick_side_part", "bowl_cut")
OUTFITS = ("polo_uniform", "hoodie", "utility_jacket", "tee", "tank", "shirt_button", "school_uniform_f",
           "school_uniform_m", "office_blouse", "floral_blouse", "ao_ba_ba", "ao_dai", "red_traditional_dress",
           "hi_vis_vest", "police_uniform", "security_uniform", "nurse_scrubs", "monk_robe", "ritual_robe",
           "pajamas", "dress", "long_sheet_shirt", "silhouette",
           # batch 2
           "khaki_uniform", "blazer_tie", "butcher_apron", "zip_jacket", "dot_blouse")
EYE_STATES = ("open", "half", "closed", "wide", "shock", "teary", "happy", "droop", "big", "wince")
BROW_STATES = ("neutral", "angry", "sad", "evil", "surprised", "worried_asym", "smirk", "low")
MOUTH_VISEMES = tuple("ABCDEFGHX")
MOUTH_EXTRA = ("flat", "smile", "frown", "wavy", "wavy_small", "o_small", "sob", "smirk", "grin", "shout", "clench",
               "laugh")
FX_SLOTS = ("fx_sweat", "fx_dashes", "fx_tears", "fx_vein", "fx_flush", "fx_eyebags_heavy", "fx_shade")

# Công thức biểu cảm: docs/STYLE_GUIDE.md §2 (eyes / brows / mouth khi im / FX bật)
EXPRESSIONS: dict[str, dict[str, Any]] = {
    "neutral": {"eyes": "open", "brows": "neutral", "mouth": "flat", "fx": []},
    "happy": {"eyes": "happy", "brows": "neutral", "mouth": "smile", "fx": ["flush"]},
    "sad": {"eyes": "droop", "brows": "sad", "mouth": "frown", "fx": []},
    "angry": {"eyes": "half", "brows": "angry", "mouth": "frown", "fx": ["vein"]},
    "scared": {"eyes": "wide", "brows": "sad", "mouth": "wavy_small", "fx": ["sweat"]},
    "evil": {"eyes": "half", "brows": "evil", "mouth": "grin", "fx": ["shade"]},
    "surprised": {"eyes": "big", "brows": "surprised", "mouth": "o_small", "fx": []},
    "nervous": {"eyes": "open", "brows": "worried_asym", "mouth": "wavy", "fx": ["dashes", "sweat"]},
    "shocked": {"eyes": "shock", "brows": "surprised", "mouth": "wavy", "fx": ["sweat"]},
    "crying": {"eyes": "teary", "brows": "sad", "mouth": "sob", "fx": ["tears", "eyebags_heavy"]},
    "tired": {"eyes": "half", "brows": "low", "mouth": "flat", "fx": ["eyebags_heavy"]},
    "smirk": {"eyes": "half", "brows": "smirk", "mouth": "smirk", "fx": []},
}
# Biểu cảm bổ sung (ngoài schema.Expression): có trong rig.expressions + profile.extra_expressions, dùng được
# qua render_figure / rig trực tiếp; pipeline chỉ gọi 12 biểu cảm chuẩn ở trên.
EXTRA_EXPRESSIONS: dict[str, dict[str, Any]] = {
    "laughing": {"eyes": "happy", "brows": "surprised", "mouth": "laugh", "fx": ["flush"]},
    "pained": {"eyes": "wince", "brows": "sad", "mouth": "clench", "fx": ["sweat"]},
    "shout_angry": {"eyes": "open", "brows": "angry", "mouth": "shout", "fx": ["vein", "flush"]},
    "wailing": {"eyes": "wince", "brows": "sad", "mouth": "shout", "fx": ["tears"]},
}


# ======================================================================= màu
def _hex(c: Any, default: str) -> str:
    if isinstance(c, str) and re.fullmatch(r"#?[0-9a-fA-F]{6}", c.strip()):
        return "#" + c.strip().lstrip("#").lower()
    return default


def mul(c: str, k: float) -> str:
    """base × k (k<1 tối hơn)."""
    return mix(c, "#000000", max(0.0, min(1.0, 1.0 - k)))


def lit(c: str, k: float) -> str:
    return mix(c, "#ffffff", k)


def _rgb(c: str) -> tuple[float, float, float]:
    c = c.lstrip("#")
    return int(c[0:2], 16) / 255, int(c[2:4], 16) / 255, int(c[4:6], 16) / 255


def desat(c: str, amount: float, tint: str | None = None, tint_k: float = 0.0) -> str:
    r, g, b = _rgb(c)
    y = 0.299 * r + 0.587 * g + 0.114 * b
    r, g, b = (r + (y - r) * amount, g + (y - g) * amount, b + (y - b) * amount)
    out = "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))
    return mix(out, tint, tint_k) if tint else out


def luma(c: str) -> float:
    r, g, b = _rgb(c)
    return 0.299 * r + 0.587 * g + 0.114 * b


def paint(c: str, a: float = 1.0) -> skia.Paint:
    return skia.Paint(AntiAlias=True, Color=color(c, a))


def pen(c: str, w: float, a: float = 1.0, cap: str = "round") -> skia.Paint:
    p = skia.Paint(AntiAlias=True, Color=color(c, a), Style=skia.Paint.kStroke_Style, StrokeWidth=w,
                   StrokeCap=skia.Paint.kRound_Cap if cap == "round" else skia.Paint.kButt_Cap,
                   StrokeJoin=skia.Paint.kRound_Join)
    return p


def _lin(p0, p1, c0: int, c1: int) -> skia.Shader:
    return skia.GradientShader.MakeLinear([skia.Point(*p0), skia.Point(*p1)], [c0, c1])


# ======================================================================= tham số
@dataclass
class CharParams:
    gender: str = "male"                     # male | female
    age: str = "adult"                       # child | young | adult | old
    build: str = "normal"                    # slim | normal | heavy
    height_scale: float = 1.0                # thực thể cao: 1.4–1.5
    skin: str = "#e9b994"
    hair_style: str = "short_side_part"      # HAIR_STYLES (+ tên v1: short, long)
    hair_color: str = "#1c1a1f"
    hair_highlight: str | None = None
    hair_tie: str | None = None
    pigtails: bool = False
    cap_color: str | None = None
    brow_color: str | None = None
    outfit_type: str | None = None           # OUTFITS; None = suy từ shirt_style (v1)
    colors: dict[str, str] = field(default_factory=dict)
    neck_style: str | None = None            # peter_pan | pointed (cổ áo sơ mi nữ sinh)
    sleeves: str | None = None               # short | long | none; None = theo trang phục
    accessories: list[str] = field(default_factory=list)
    eye_bags: bool = False
    blush: float = 0.45
    wrinkles: bool | None = None             # None = theo tuổi
    facial_hair: str = "none"                # none | stubble | mustache | white_goatee | goatee
    lip_color: str | None = None
    ghost: str | None = None                 # None | water | pale | frozen | entity
    wet: bool = False
    face: str = "normal"                     # normal | entity | none
    vest_number: str = "07"
    eye_color: str = EYE_INK
    # ---- tham số v1 (giữ để tương thích make_character cũ)
    shirt_style: str | None = None           # shirt | tshirt | tank | dress
    shirt_color: str | None = None
    pants_color: str | None = None
    shorts: bool = False
    shoe_color: str | None = None
    sandals: bool = False
    apron_color: str | None = None
    dress_color: str | None = None
    gold_chain: bool = False
    scar: bool = False
    glasses: bool = False
    outline: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "CharParams":
        names = {f.name for f in fields(cls)}
        known = {k: v for k, v in d.items() if k in names}
        unknown = sorted(set(d) - names)
        if unknown:
            log.warning("puppetgen: bỏ qua tham số không biết %s", unknown)
        return cls(**known)


def normalize(p: CharParams) -> CharParams:
    """Chuẩn hoá tham số (tên v1 -> v2, màu hợp lệ). Trả về bản sao."""
    q = CharParams(**{f.name: getattr(p, f.name) for f in fields(p)})
    q.colors = dict(p.colors or {})
    q.accessories = list(p.accessories or [])
    if q.gender not in ("male", "female"):
        q.gender = "male"
    if q.age not in ("child", "young", "adult", "old"):
        q.age = "adult"
    if q.build not in ("slim", "normal", "heavy"):
        q.build = "normal"
    q.skin = _hex(q.skin, "#e9b994")
    q.hair_color = _hex(q.hair_color, "#1c1a1f")
    q.hair_style = {"short": "short_side_part", "long": "long_straight", "curly": "curly_short",
                    "ponytail": "long_ponytail", "bob": "bob_bangs", "cap": "cap_hidden"}.get(q.hair_style, q.hair_style)
    if q.hair_style not in HAIR_STYLES:
        log.warning("puppetgen: kiểu tóc '%s' không biết — dùng short_side_part", q.hair_style)
        q.hair_style = "short_side_part"
    # ---- v1 -> v2
    if q.outfit_type is None:
        q.outfit_type = {"shirt": "shirt_button", "tshirt": "tee", "tank": "tank", "dress": "dress"}.get(
            q.shirt_style or "tshirt", "tee")
    if q.outfit_type not in OUTFITS:
        log.warning("puppetgen: trang phục '%s' không biết — dùng tee", q.outfit_type)
        q.outfit_type = "tee"
    cl = q.colors
    if q.shirt_color:
        for k in ("shirt", "tee", "blouse", "top"):
            cl.setdefault(k, q.shirt_color)
    if q.dress_color:
        cl.setdefault("dress", q.dress_color)
    if q.pants_color:
        cl.setdefault("pants", q.pants_color)
    if q.shoe_color:
        cl.setdefault("sandals" if q.sandals else "shoes", q.shoe_color)
    if q.shorts:
        cl.setdefault("shorts", cl.get("pants", "#3a5f8c"))
    if q.apron_color:
        cl.setdefault("apron", q.apron_color)
    if q.sandals and "sandals" not in cl:
        cl["sandals"] = "#7a4b2c"
    for k, v in list(cl.items()):
        cl[k] = _hex(v, "#808080")
    acc = q.accessories
    if q.gold_chain and "gold_chain_square_pendant" not in acc:
        acc.append("gold_chain_square_pendant")
    if q.glasses and not any(a.startswith(("glasses", "reading_glasses")) for a in acc):
        acc.append("glasses_black_rect")
    if q.scar and "scar" not in acc:
        acc.append("scar")
    if q.facial_hair not in ("none", "stubble", "mustache", "white_goatee", "goatee"):
        q.facial_hair = "none"
    if q.wrinkles is None:
        q.wrinkles = q.age == "old"
    q.height_scale = float(max(0.8, min(1.6, q.height_scale or 1.0)))
    return q


# ======================================================================= trang phục -> đặc tả vẽ
@dataclass
class Spec:
    top: str
    neck: str = "crew"               # crew polo shirt v peter_pan hood mandarin round wrap none
    collar: str | None = None
    sleeve: str = "short"            # short long none
    sleeve_col: str | None = None
    cuff: str | None = None
    lower: str = "pants"             # pants shorts skirt pencil dress robe aodai sheet
    lower_col: str = "#2a2a30"
    hem: float = 0.0                 # độ dài váy: 0 = gối; >0 dài hơn (phần Hf)
    shoe: str = "shoes"              # shoes sneakers flats sandals bare stick
    shoe_col: str = "#1c1b1f"
    sock: str | None = None
    belt: str | None = None
    tunic: float = 0.0               # áo dài quá eo (phần Hf)
    loose: bool = False              # tay áo rộng


def outfit_spec(p: CharParams) -> Spec:
    c = p.colors
    o = p.outfit_type
    g = lambda *ks, d="#808080": next((c[k] for k in ks if k in c), d)  # noqa: E731
    shoes = g("shoes", d="#1c1b1f")
    sandal = "sandals" in c
    shoe_kind = "sandals" if sandal else "shoes"
    shoe_col = c.get("sandals", shoes)
    if o == "polo_uniform":
        s = Spec(g("shirt", d="#1f6f5c"), "polo", g("collar", d="#f2ead8"), "short", cuff=g("collar", d="#f2ead8"),
                 lower_col=g("pants", d="#1f1f24"), shoe_col=shoes)
    elif o == "hoodie":
        hc = g("hoodie", "shirt", d="#3a3d44")
        s = Spec(hc, "hood", None, "long", cuff=g("cuffs", d=mul(hc, 0.85)), lower_col=g("pants", d="#3b5578"),
                 shoe="sneakers", shoe_col=shoes if "shoes" in c else "#e8e6e1")
    elif o == "utility_jacket":
        s = Spec(g("tee", "shirt", d="#1e1e22"), "crew", None, "long", sleeve_col=g("jacket", d="#6b7244"),
                 cuff=mul(g("jacket", d="#6b7244"), 0.9), lower_col=g("pants", d="#2c3442"), shoe="sneakers",
                 shoe_col=shoes if "shoes" in c else "#e8e6e1")
    elif o in ("tee", "tank"):
        s = Spec(g("tee", "shirt", "top", d="#4d6070"), "crew" if o == "tee" else "tank", None,
                 "short" if o == "tee" else "none", lower="shorts" if "shorts" in c else "pants",
                 lower_col=g("shorts", "pants", d="#3a3330"), shoe=shoe_kind, shoe_col=shoe_col)
    elif o == "shirt_button":
        s = Spec(g("shirt", d="#ece4cf"), "shirt", None, "short", lower_col=g("pants", d="#5a4636"),
                 shoe=shoe_kind, shoe_col=shoe_col)
    elif o == "school_uniform_f":
        s = Spec(g("shirt", d="#f5f4f0"), p.neck_style or "pointed", None, "short", lower="skirt",
                 lower_col=g("skirt", d="#1c1c22"), hem=0.03, shoe="shoes", shoe_col=g("shoes", d="#151517"),
                 sock=c.get("socks"))
    elif o == "school_uniform_m":
        s = Spec(g("shirt", d="#f4f4f1"), "shirt", None, "short", lower_col=g("pants", d="#22304a"),
                 shoe_col=g("shoes", d="#1a1a1d"))
    elif o == "office_blouse":
        s = Spec(g("blouse", "shirt", d="#efe6d6"), "v", None, "short", lower="pencil", lower_col=g("skirt", d="#5a5d66"),
                 shoe="flats", shoe_col=g("shoes", d="#2a2426"))
    elif o == "floral_blouse":
        s = Spec(g("blouse", "shirt", d="#3f5a4a"), "round", None, "short", lower_col=g("pants", d="#1c1b1f"),
                 shoe="sandals", shoe_col=g("sandals", d="#7a5a44"))
    elif o == "ao_ba_ba":
        s = Spec(g("top", "shirt", d="#8b6fa8"), "round", None, "long", lower_col=g("pants", d="#1d1b20"),
                 shoe="sandals", shoe_col=g("sandals", d="#5a7e9a"), tunic=0.05, loose=True)
    elif o in ("ao_dai", "red_traditional_dress"):
        s = Spec(g("dress", "top", d="#9e1f26"), "mandarin", g("trim", d="#b08a4a"), "long",
                 lower="aodai", lower_col=g("dress_dark", "pants", d="#6a1218"),
                 shoe="bare" if "feet" in c else "sandals", shoe_col=g("feet", "sandals", d=p.skin))
    elif o == "hi_vis_vest":
        s = Spec(g("shirt", d="#9cb7d2"), "shirt", None, "long", lower_col=g("pants", d="#2b2b30"),
                 shoe=shoe_kind, shoe_col=shoe_col if sandal else g("shoes", d="#2a2522"))
    elif o == "police_uniform":
        u = g("uniform", "shirt", d="#3d5a3a")
        s = Spec(u, "shirt", None, "short", lower_col=g("pants", "uniform", d=u), shoe_col=g("shoes", d="#151515"),
                 belt=g("belt", d="#1c1c1c"))
    elif o == "security_uniform":
        s = Spec(g("shirt", d="#8fb0d0"), "shirt", None, "long", lower_col=g("pants", d="#232a3a"),
                 shoe_col=g("shoes", d="#141414"), belt="#1b1b1e")
    elif o == "nurse_scrubs":
        sc = g("scrubs", d="#5fb2a8")
        s = Spec(sc, "v", None, "short", lower_col=sc, shoe="sneakers", shoe_col=g("shoes", d="#f0f0ee"))
    elif o in ("monk_robe", "ritual_robe"):
        rc = g("robe_monk", "robe", d="#8a5a32") if o == "monk_robe" else g("robe_ritual", d="#1f1c20")
        s = Spec(rc, "wrap", mul(rc, 0.8), "long", lower="robe", lower_col=rc, hem=0.2, shoe="sandals",
                 shoe_col=g("sandals", d="#4a3a2a"), loose=True)
    elif o in ("pajamas", "dress"):
        dc = g("dress", "top", "shirt", d="#f0a9bf")
        s = Spec(dc, "round", None, "short", lower="dress", lower_col=dc, hem=-0.035, shoe="sandals",
                 shoe_col=g("sandals", d="#e5e0d8"))
    elif o == "long_sheet_shirt":
        sc = g("shirt", "body", d="#a3a7a3")
        s = Spec(sc, "none", None, "long", lower="sheet", lower_col=g("legs", "body", d=mul(sc, 0.8)),
                 shoe="stick", shoe_col=g("legs", "body", d=mul(sc, 0.8)), loose=True)
    elif o == "silhouette":
        bc = g("body", d="#2a2b30")
        s = Spec(bc, "none", g("collar", d="#d9b44a"), "long", lower="pants", lower_col=bc, shoe="stick", shoe_col=bc)
    elif o == "khaki_uniform":
        u = g("uniform", "shirt", d="#b59c6a")
        s = Spec(u, "shirt", None, "short", lower_col=g("pants", d=mul(u, 0.72)), shoe_col=g("shoes", d="#2a2018"),
                 belt=g("belt", d="#3a2a1e"))
    elif o == "blazer_tie":
        bz = g("blazer", "jacket", d="#33363d")
        s = Spec(g("shirt", d="#f2f1ec"), "shirt", None, "long", sleeve_col=bz, cuff=mul(bz, 0.86),
                 lower_col=g("pants", d="#24262b"), shoe_col=g("shoes", d="#141416"), tunic=0.03)
    elif o == "butcher_apron":
        tank = "tank" in c
        s = Spec(g("tank", "tee", "shirt", d="#9a9c9e"), "tank" if tank else "crew", None, "none" if tank else "short",
                 lower_col=g("pants", d="#2c2a2a"), shoe="boots" if "boots" in c else shoe_kind,
                 shoe_col=g("boots", d=shoe_col))
    elif o == "zip_jacket":
        jc = g("jacket", d="#22304a")
        s = Spec(g("tee", "shirt", d="#ecebe6"), "crew", None, "long", sleeve_col=jc, cuff=mul(jc, 0.85),
                 lower_col=g("pants", d="#2a2f3a"), shoe="sneakers" if not sandal else "sandals",
                 shoe_col=shoes if ("shoes" in c or sandal) else "#e8e6e1")
        if sandal:
            s.shoe_col = shoe_col
    elif o == "dot_blouse":
        s = Spec(g("blouse", "top", d="#6d4a8c"), "round", None, "long",
                 lower="sarong" if "skirt" in c else "pants", lower_col=g("skirt", "pants", d="#3a2440"),
                 shoe="sandals", shoe_col=g("sandals", d="#5a4a44"))
    else:
        s = Spec(g("shirt", d="#4d6070"))
    # quần đùi cho áo khoác / hoodie / sơ mi (batch 2: chỉ khi archetype khai báo màu "shorts")
    if "shorts" in c and s.lower == "pants" and o in ("hoodie", "utility_jacket", "zip_jacket", "shirt_button"):
        s.lower, s.lower_col = "shorts", c["shorts"]
    if p.sleeves in ("short", "long", "none"):
        s.sleeve = p.sleeves
    if s.sleeve_col is None:
        s.sleeve_col = s.top
    return s


# ======================================================================= hình học
class Geo:
    def __init__(self, p: CharParams) -> None:
        self.p = p
        fem = p.gender == "female"
        child = p.age == "child"
        ent = p.face == "entity"
        self.fem, self.child, self.ent = fem, child, ent
        hs = p.height_scale
        self.FY = round(1000 * max(1.0, hs))
        self.CH = self.FY + 12
        base = {"child": 0.62, "young": 1.0, "adult": 1.0, "old": 0.95}[p.age] * (0.95 if fem else 1.0)
        Hf = self.Hf = 930 * base * hs
        self.b = b = {"slim": 0.88, "normal": 1.0, "heavy": 1.2}[p.build]
        self.cx = cx = W / 2
        self.top = top = self.FY - Hf
        hh = self.hh = (0.27 if child else (0.115 if ent else 0.215)) * Hf
        self.rx = hh * (0.36 if ent else 0.455) * (1.05 if p.build == "heavy" else 1.0)
        self.ry = hh * 0.5
        self.hx, self.hy = cx, top + self.ry
        self.chin = top + hh
        self.fu = 0.05                                  # lệch nét mặt về phía "hướng mặt" (3/4 nhẹ)
        neck_len = (0.03 if child else (0.085 if ent else 0.05)) * Hf
        self.shoulder_y = sy = self.chin + neck_len
        self.neck_w = self.rx * (0.16 if ent else (0.26 if p.build == "heavy" else (0.19 if fem else 0.22)))
        leg_frac = 0.40 if child else (0.50 if ent else 0.47)
        self.hip_y = self.FY - leg_frac * Hf
        self.waist_y = self.hip_y - 0.035 * Hf
        sw = (0.125 if child else (0.07 if ent else (0.095 if fem else 0.113))) * Hf
        self.sw = sw * (b if not ent else 1.0)
        self.hw = (0.12 if child else (0.07 if ent else (0.088 if fem else 0.085))) * Hf * b
        self.knee_y = self.FY - (0.21 if child else 0.255) * Hf
        self.ankle_y = self.FY - 0.035 * Hf
        self.leg_x = (0.045 if not ent else 0.03) * Hf * b
        lk = 0.92 if fem else 1.0
        self.thigh_w = (0.07 if not ent else 0.03) * Hf * b * lk
        self.shin_w = (0.052 if not ent else 0.026) * Hf * b * lk
        self.arm_w = (0.05 if not ent else 0.026) * Hf * b * (0.9 if fem else 1.0)
        self.fore_w = self.arm_w * 0.86
        self.arm_x = self.sw - self.arm_w * 0.42
        self.arm_y = sy + self.arm_w * 0.48
        up_len, lo_len = ((0.20, 0.20) if ent else (0.15, 0.135))
        self.elbow_y = self.arm_y + up_len * Hf
        self.wrist_y = self.elbow_y + lo_len * Hf
        self.hand_len = (0.11 if ent else 0.068) * Hf
        # mặt
        self.ex = {"l": self.U(self.fu - 0.36), "r": self.U(self.fu + 0.36)}
        self.ey = self.V(0.14)
        es = 1.16 if child else 1.0
        self.erx = 0.085 * self.rx * es
        self.ery = 0.12 * self.ry * es
        self.mx, self.my = self.U(self.fu), self.V(0.62 if not child else 0.6)
        self.mw = 0.2 * self.rx

    def U(self, u: float) -> float:
        return self.hx + u * self.rx

    def V(self, v: float) -> float:
        return self.hy + v * self.ry

    def P(self, u: float, v: float) -> tuple[float, float]:
        return self.U(u), self.V(v)

    def pts(self, uv) -> list[tuple[float, float]]:
        return [self.P(u, v) for u, v in uv]

    @staticmethod
    def side(s: str) -> float:
        return -1.0 if s == "l" else 1.0

    def shoulder(self, s: str) -> tuple[float, float]:
        return self.cx + self.side(s) * self.arm_x, self.arm_y

    def elbow(self, s: str) -> tuple[float, float]:
        return self.cx + self.side(s) * (self.arm_x + 0.01 * self.Hf), self.elbow_y

    def wrist(self, s: str) -> tuple[float, float]:
        return self.cx + self.side(s) * (self.arm_x + 0.016 * self.Hf), self.wrist_y

    def hipj(self, s: str) -> tuple[float, float]:
        return self.cx + self.side(s) * self.leg_x, self.hip_y

    def knee(self, s: str) -> tuple[float, float]:
        return self.cx + self.side(s) * self.leg_x * 1.02, self.knee_y

    def head_region(self) -> tuple[float, float, float, float]:
        return (self.hx - 1.9 * self.rx, self.top - 0.75 * self.hh, self.hx + 1.9 * self.rx, self.chin + 0.35 * self.hh)


# ======================================================================= tô phẳng
def flat(c: skia.Canvas, path: skia.Path, col: str, *, d: float | None = None, k: float = 0.82, rim: float = 0.32,
         edge: float = 0.0, hl: float = 0.12, bottom: float = 0.18) -> None:
    """Tô phẳng 2 tông: màu nền + mảng tối (base×k) phía trái + gradient mềm dọc mép, không viền da."""
    if path.isEmpty():
        return
    c.drawPath(path, paint(col))
    b = path.getBounds()
    w, h = b.width(), b.height()
    dd = w * 0.14 if d is None else d
    c.save()
    c.clipPath(path, doAntiAlias=True)
    if dd > 0:
        c.drawPath(diff(path, offset(path, dd, -dd * 0.12)), paint(mul(col, k)))
    if rim > 0:
        pr = skia.Paint(AntiAlias=True)
        pr.setShader(_lin((b.left(), 0), (b.left() + w * 0.32, 0), color(mul(col, 0.72), rim), color(col, 0)))
        c.drawRect(b, pr)
    if bottom > 0:
        pb = skia.Paint(AntiAlias=True)
        pb.setShader(_lin((0, b.bottom()), (0, b.bottom() - min(h * 0.3, 60)), color(mul(col, 0.75), bottom),
                          color(col, 0)))
        c.drawRect(b, pb)
    if hl > 0:
        ph = skia.Paint(AntiAlias=True)
        ph.setShader(_lin((b.right(), 0), (b.right() - w * 0.18, 0), color(lit(col, 0.35), hl), color(col, 0)))
        c.drawRect(b, ph)
    c.restore()
    if edge > 0:
        c.drawPath(path, pen(mul(col, 0.62), 1.5, edge))


def seam(c: skia.Canvas, pts, col: str, w: float = 1.8, a: float = 0.85, curve: bool = True,
         dash: tuple[float, float] | None = None) -> None:
    pth = smooth(pts, close=False) if (curve and len(pts) > 2) else poly(pts, close=False)
    pp = pen(col, w, a)
    if dash:
        pp.setPathEffect(skia.DashPathEffect.Make(list(dash), 0))
    c.drawPath(pth, pp)


def hair_fill(c: skia.Canvas, path: skia.Path, g: Geo, *, arc: tuple | None = None, strokes: list | None = None,
              col: str | None = None) -> None:
    """Tóc: khối phẳng + 1 cung highlight xám-xanh + vài vạch nhỏ."""
    if path.isEmpty():
        return
    hc = col or g.p.hair_color
    hl = g.p.hair_highlight or (mix(hc, "#8fa3b8", 0.62) if luma(hc) < 0.35 else lit(hc, 0.35))
    c.drawPath(path, paint(hc))
    b = path.getBounds()
    c.save()
    c.clipPath(path, doAntiAlias=True)
    pr = skia.Paint(AntiAlias=True)
    pr.setShader(_lin((b.left(), 0), (b.left() + b.width() * 0.3, 0), color(mul(hc, 0.6), 0.45), color(hc, 0)))
    c.drawRect(b, pr)
    if arc:
        c.drawPath(smooth(g.pts(arc), close=False), pen(hl, g.rx * 0.075, 0.85))
    for st in strokes or []:
        c.drawPath(smooth(g.pts(st), close=False) if len(st) > 2 else poly(g.pts(st), close=False),
                   pen(hl, g.rx * 0.03, 0.7))
    c.restore()


# ======================================================================= đầu & mặt
def face_path(g: Geo) -> skia.Path:
    p = g.p
    wide = p.age == "old" or p.build == "heavy"
    if g.ent:
        R = [(0, -1.0), (0.62, -0.9), (0.95, -0.5), (1.0, 0.05), (0.85, 0.55), (0.5, 0.92), (0, 1.02)]
    elif g.child:
        R = [(0, -1.0), (0.6, -0.92), (0.92, -0.62), (1.0, -0.15), (0.99, 0.25), (0.88, 0.6), (0.6, 0.88), (0, 1.0)]
    else:
        R = [(0, -1.0), (0.56, -0.94), (0.9, -0.66), (1.0, -0.22), (0.99, 0.18), (0.92 if wide else 0.89, 0.53),
             (0.7 if wide else 0.64, 0.85), (0.3, 0.99), (0, 1.01)]
    L = [(-u, v) for u, v in reversed(R[1:-1])]
    return smooth(g.pts(R + L), tension=0.55)


def draw_ears(c: skia.Canvas, g: Geo, back: bool = False) -> None:
    if g.ent or g.p.face == "none":
        return
    skin = g.p.skin
    for s in (-1, 1):
        ex, ey = g.P(s * 0.97, 0.16)
        ear = oval(ex + s * 0.06 * g.rx, ey, 0.17 * g.rx, 0.24 * g.ry)
        flat(c, ear, skin, d=0.05 * g.rx, rim=0.2, hl=0, bottom=0)
        seam(c, [(ex + s * 0.13 * g.rx, ey - 0.13 * g.ry), (ex + s * 0.03 * g.rx, ey - 0.02 * g.ry),
                 (ex + s * 0.09 * g.rx, ey + 0.13 * g.ry)], mul(skin, 0.7), g.rx * 0.03, 0.8)
        if not back:
            acc = g.p.accessories
            if "earrings_drop_blue" in acc or "gold_earrings" in acc:
                gold = "gold_earrings" in acc
                cc = "#e3b23c" if gold else "#4f8fd0"
                ey2 = ey + 0.26 * g.ry
                c.drawPath(circle(ex + s * 0.06 * g.rx, ey2, g.rx * 0.035), paint(cc))
                drop = smooth([(ex + s * 0.06 * g.rx, ey2), (ex + s * 0.06 * g.rx + g.rx * 0.05, ey2 + g.ry * 0.12),
                               (ex + s * 0.06 * g.rx, ey2 + g.ry * 0.17), (ex + s * 0.06 * g.rx - g.rx * 0.05,
                                                                           ey2 + g.ry * 0.12)], tension=0.5)
                c.drawPath(drop, paint(cc))
                c.drawPath(circle(ex + s * 0.06 * g.rx + g.rx * 0.015, ey2 + g.ry * 0.1, g.rx * 0.015), paint("#ffffff", 0.8))


def draw_head(c: skia.Canvas, g: Geo) -> None:
    draw_ears(c, g)
    fp = face_path(g)
    flat(c, fp, g.p.skin, d=0.16 * g.rx, rim=0.28, hl=0.1, bottom=0.12)


def draw_head_back(c: skia.Canvas, g: Geo) -> None:
    draw_ears(c, g, back=True)
    fp = face_path(g)
    flat(c, fp, g.p.skin, d=0.16 * g.rx, rim=0.3, hl=0.08, bottom=0.2)


def draw_face(c: skia.Canvas, g: Geo) -> None:
    """Chi tiết tĩnh: mũi, má hồng, quầng mắt, nếp nhăn, râu, sẹo, quầng ma."""
    p = g.p
    if p.face == "none":
        return
    skin = p.skin
    fu = g.fu
    if g.ent:
        return
    c.save()
    c.clipPath(face_path(g), doAntiAlias=True)
    # má hồng
    bl = max(0.0, min(1.0, p.blush))
    if bl > 0 and not p.ghost:
        for s in (-1, 1):
            cxb, cyb = g.P(fu + s * 0.55, 0.42)
            pb = skia.Paint(AntiAlias=True, Color=color(BLUSH, bl),
                            MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, g.rx * 0.05))
            c.drawPath(oval(cxb, cyb, 0.17 * g.rx, 0.085 * g.ry), pb)
    # quầng mắt
    if p.eye_bags or p.ghost:
        bag = "#7d8aa3" if p.ghost else "#8a6f8a"
        for s in ("l", "r"):
            ex, ey = g.ex[s], g.ey
            pth = diff(oval(ex, ey + g.ery * 1.25, g.erx * 1.9, g.ery * 0.7), oval(ex, ey + g.ery * 0.75, g.erx * 2.1,
                                                                                    g.ery * 0.75))
            c.drawPath(pth, skia.Paint(AntiAlias=True, Color=color(bag, 0.55 if p.ghost else 0.4),
                                       MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, g.rx * 0.012)))
    # mũi: chấm/oval nhỏ đậm hơn da ~12%
    c.drawPath(oval(*g.P(fu, 0.38), 0.055 * g.rx, 0.04 * g.ry), paint(mul(skin, 0.86)))
    c.drawPath(oval(*g.P(fu + 0.02, 0.355), 0.02 * g.rx, 0.012 * g.ry), paint(lit(skin, 0.4), 0.7))
    # râu
    hc = p.brow_color or p.hair_color
    if p.facial_hair == "stubble":
        st = smooth(g.pts([(-0.75, 0.48), (-0.45, 0.85), (0, 1.02), (0.45, 0.85), (0.75, 0.48), (0.4, 0.7),
                           (fu, 0.78), (-0.4, 0.7)]), tension=0.45)
        c.drawPath(st, paint(mix(skin, "#2a2420", 0.42), 0.5))
        c.drawPath(smooth(g.pts([(fu - 0.32, 0.53), (fu, 0.5), (fu + 0.32, 0.53), (fu, 0.56)]), tension=0.4),
                   paint(mix(skin, "#2a2420", 0.45), 0.55))
    if p.wrinkles:
        dk = mul(skin, 0.72)
        for v, wd in ((-0.6, 0.34), (-0.5, 0.26)):
            seam(c, g.pts([(fu - wd, v + 0.02), (fu, v - 0.02), (fu + wd, v + 0.02)]), dk, g.rx * 0.025, 0.55)
        for s in (-1, 1):  # rãnh mũi-má
            seam(c, g.pts([(fu + s * 0.2, 0.42), (fu + s * 0.3, 0.55), (fu + s * 0.32, 0.68)]), dk, g.rx * 0.025, 0.55)
            seam(c, g.pts([(fu + s * 0.6, 0.06), (fu + s * 0.7, 0.1)]), dk, g.rx * 0.02, 0.5, curve=False)
            seam(c, g.pts([(fu + s * 0.6, 0.14), (fu + s * 0.7, 0.2)]), dk, g.rx * 0.02, 0.5, curve=False)
    if "scar" in p.accessories:
        a, b2 = g.P(fu - 0.62, -0.4), g.P(fu - 0.28, 0.42)
        c.drawPath(poly([a, b2], close=False), pen("#c98a82", g.rx * 0.07, 0.8))
        c.drawPath(poly([a, b2], close=False), pen("#9a4a48", g.rx * 0.03))
        for t in (0.2, 0.42, 0.64, 0.84):
            x, y = a[0] + (b2[0] - a[0]) * t, a[1] + (b2[1] - a[1]) * t
            c.drawPath(poly([(x - g.rx * 0.07, y - 2), (x + g.rx * 0.07, y + 2)], close=False), pen("#9a4a48", g.rx * 0.022))
    if "burn_scar" in p.accessories:   # mảng sẹo bỏng quanh mắt trái màn hình (trán -> má), loang lổ, không máu
        ex = g.ex["l"]
        patch = smooth([(ex - g.rx * 0.32, g.V(-0.62)), (ex + g.rx * 0.2, g.V(-0.55)), (ex + g.rx * 0.36, g.V(-0.12)),
                        (ex + g.rx * 0.3, g.V(0.3)), (ex + g.rx * 0.08, g.V(0.62)), (ex - g.rx * 0.3, g.V(0.55)),
                        (ex - g.rx * 0.62, g.V(0.2)), (ex - g.rx * 0.6, g.V(-0.3))], tension=0.38)
        sc = mix(skin, "#b4605c", 0.42)
        c.drawPath(patch, paint(sc, 0.9))
        c.save()
        c.clipPath(patch, doAntiAlias=True)
        rng = np.random.default_rng(7)
        b = patch.getBounds()
        for _ in range(16):
            x, y = rng.uniform(b.left(), b.right()), rng.uniform(b.top(), b.bottom())
            r = g.rx * rng.uniform(0.03, 0.08)
            c.drawPath(oval(x, y, r, r * 0.7), paint(lit(sc, 0.3) if rng.random() < 0.5 else mul(sc, 0.82), 0.75))
        c.restore()
        c.drawPath(patch, pen(mul(sc, 0.72), g.rx * 0.022, 0.8))
        seam(c, [(ex - g.rx * 0.4, g.V(-0.2)), (ex - g.rx * 0.1, g.V(0.05)), (ex + g.rx * 0.15, g.V(0.38))], mul(sc, 0.7),
             g.rx * 0.018, 0.7)
    if "mole" in p.accessories:
        c.drawPath(circle(*g.P(fu + 0.52, 0.56), g.rx * 0.035), paint("#3a2622", 0.9))
    c.restore()
    if p.facial_hair in ("white_goatee", "goatee"):
        gc = "#ecebe6" if p.facial_hair == "white_goatee" else hc
        gt = smooth(g.pts([(fu - 0.2, 0.8), (fu, 0.82), (fu + 0.2, 0.8), (fu + 0.12, 1.08), (fu, 1.2),
                           (fu - 0.12, 1.08)]), tension=0.45)
        flat(c, gt, gc, d=0.03 * g.rx, rim=0.2, hl=0)
        mus = smooth(g.pts([(fu - 0.3, 0.56), (fu, 0.5), (fu + 0.3, 0.56), (fu + 0.22, 0.6), (fu, 0.56),
                            (fu - 0.22, 0.6)]), tension=0.4)
        c.drawPath(mus, paint(gc))
    elif p.facial_hair == "mustache":
        mus = smooth(g.pts([(fu - 0.34, 0.57), (fu - 0.1, 0.48), (fu, 0.5), (fu + 0.1, 0.48), (fu + 0.34, 0.57),
                            (fu + 0.22, 0.6), (fu, 0.55), (fu - 0.22, 0.6)]), tension=0.4)
        c.drawPath(mus, paint(hc))


def draw_neck(c: skia.Canvas, g: Geo) -> None:
    skin = g.p.skin
    top = g.chin - 0.3 * g.hh
    bot = g.shoulder_y + 0.04 * g.Hf
    path = rrect(g.cx - g.neck_w, top, g.cx + g.neck_w, bot, g.neck_w * 0.5)
    flat(c, path, skin, d=g.neck_w * 0.35, rim=0.3, hl=0.08, bottom=0)
    c.save()
    c.clipPath(path, doAntiAlias=True)
    c.drawPath(oval(g.cx + g.rx * 0.04, g.chin + 0.02 * g.hh, g.neck_w * 1.4, g.hh * 0.07), paint(mul(skin, 0.78), 0.9))
    c.restore()
    if g.p.face == "none":
        return
    dk = mul(skin, 0.72)
    y0, y1 = g.chin + 0.06 * g.hh, g.shoulder_y + 0.005 * g.Hf
    if y1 - y0 > 6:
        for s in (-1, 1):  # 2 nét gân cổ
            x = g.cx + s * g.neck_w * 0.42
            seam(c, [(x - s * 1.5, y0), (x, (y0 + y1) / 2), (x + s * 2.5, y1)], dk, max(1.2, g.neck_w * 0.06), 0.55)
        if g.p.wrinkles:
            for t in (0.35, 0.6):
                y = y0 + (y1 - y0) * t
                seam(c, [(g.cx - g.neck_w * 0.6, y), (g.cx, y + 2), (g.cx + g.neck_w * 0.6, y)], dk, 1.4, 0.45)


# ---------------------------------------------------------------- mắt
def draw_eyes(c: skia.Canvas, g: Geo, state: str) -> None:
    p = g.p
    if p.face == "none":
        return
    skin = p.skin
    ink = p.eye_color
    if g.ent:
        for s in ("l", "r"):  # 2 mắt oval xếch tối
            ex, ey = g.ex[s], g.ey
            sg = -1 if s == "l" else 1
            pth = smooth([(ex - g.erx * 2.2, ey + sg * g.ery * 0.2), (ex, ey - g.ery * 1.1),
                          (ex + g.erx * 2.2, ey - sg * g.ery * 0.6), (ex, ey + g.ery * 0.9)], tension=0.5)
            if state in ("closed",):
                seam(c, [(ex - g.erx * 2, ey), (ex + g.erx * 2, ey - sg * g.ery * 0.4)], ink, g.rx * 0.05)
                continue
            c.drawPath(pth, paint(ink))
        return
    lw = g.rx * 0.045
    for s in ("l", "r"):
        ex, ey, rx, ry = g.ex[s], g.ey, g.erx, g.ery
        inner = 1 if s == "l" else -1        # hướng vào giữa mặt
        if state == "closed":
            seam(c, [(ex - rx * 1.5, ey - ry * 0.1), (ex, ey + ry * 0.55), (ex + rx * 1.5, ey - ry * 0.1)], LINE_INK, lw)
            continue
        if state == "wince":     # nhắm chặt kiểu > <  (đỉnh chĩa vào giữa mặt)
            tip = (ex + inner * rx * 1.1, ey)
            seam(c, [(ex - inner * rx * 1.45, ey - ry * 0.95), tip, (ex - inner * rx * 1.45, ey + ry * 0.85)], EYE_INK,
                 lw * 1.2, curve=False)
            continue
        if state == "happy":
            seam(c, [(ex - rx * 1.5, ey + ry * 0.35), (ex, ey - ry * 0.55), (ex + rx * 1.5, ey + ry * 0.35)], LINE_INK,
                 lw * 1.1)
            continue
        if state in ("wide", "shock"):
            k = 1.0 if state == "wide" else 1.25
            scl = oval(ex, ey - ry * 0.05, rx * 1.75 * k, ry * 1.25 * k)
            c.drawPath(scl, paint(WHITE))
            c.drawPath(scl, pen(EYE_INK, lw * 0.75))
            pr = rx * (0.55 if state == "wide" else 0.32)
            c.drawPath(circle(ex + inner * rx * 0.05, ey, pr), paint(ink))
            if state == "wide":
                c.drawPath(circle(ex + inner * rx * 0.05 + pr * 0.35, ey - pr * 0.35, pr * 0.32), paint("#ffffff"))
            continue
        if state == "teary":
            # mắt bóng nước, viền đỏ, vũng nước mí dưới
            c.drawPath(oval(ex, ey + ry * 0.05, rx * 1.55, ry * 1.25), paint("#e46f6f", 0.35))
            c.drawPath(oval(ex, ey, rx * 1.12, ry * 1.08), paint(ink))
            c.drawPath(circle(ex + rx * 0.35, ey - ry * 0.4, rx * 0.36), paint("#ffffff"))
            c.drawPath(circle(ex - rx * 0.4, ey + ry * 0.35, rx * 0.2), paint("#ffffff", 0.9))
            c.drawPath(oval(ex, ey + ry * 1.0, rx * 1.6, ry * 0.32), paint(TEAR, 0.85))
            c.drawPath(oval(ex - rx * 0.3, ey + ry * 0.95, rx * 0.5, ry * 0.1), paint("#ffffff", 0.8))
            continue
        k = 1.16 if state == "big" else 1.0
        eye = oval(ex, ey, rx * k, ry * k)
        c.drawPath(eye, paint(ink))
        c.drawPath(circle(ex + rx * 0.32 * k, ey - ry * 0.38 * k, rx * 0.34 * k), paint("#ffffff"))
        if state in ("half", "droop"):
            lid = mul(skin, 0.94)
            c.save()
            c.clipPath(oval(ex, ey, rx * k * 1.25, ry * k * 1.25), doAntiAlias=True)   # mí chỉ phủ trong mắt
            if state == "half":
                cut = rrect(ex - rx * 2, ey - ry * 2.2, ex + rx * 2, ey - ry * 0.05, 1)
                c.drawPath(cut, paint(lid))
                seam(c, [(ex - rx * 1.35, ey + ry * 0.0), (ex, ey - ry * 0.12), (ex + rx * 1.35, ey + ry * 0.0)],
                     LINE_INK, lw * 0.9)
            else:   # mí trên trễ xuống phía ngoài (buồn)
                outer = -inner
                cut = poly([(ex - rx * 2, ey - ry * 2.2), (ex + rx * 2, ey - ry * 2.2),
                            (ex + rx * 2, ey - ry * (0.15 if outer > 0 else 0.9)),
                            (ex - rx * 2, ey - ry * (0.15 if outer < 0 else 0.9))])
                c.drawPath(cut, paint(lid))
                seam(c, [(ex - rx * 1.3, ey - ry * (0.1 if outer < 0 else 0.75)),
                         (ex + rx * 1.3, ey - ry * (0.1 if outer > 0 else 0.75))], LINE_INK, lw * 0.85, curve=False)
            c.restore()
        if p.gender == "female" and state in ("open", "big", "droop"):
            outer = -inner
            seam(c, [(ex + outer * rx * 0.85, ey - ry * 0.55), (ex + outer * rx * 1.45, ey - ry * 0.95)], EYE_INK,
                 lw * 0.7, curve=False)


# ---------------------------------------------------------------- mày
BROWS = {  # (dy trong, dy ngoài, độ cong) đơn vị ry; dương = thấp xuống. Bộ trái/phải nếu bất đối xứng.
    "neutral": (0.0, 0.0, -0.05),
    "angry": (0.13, -0.06, 0.0),
    "sad": (-0.13, 0.06, -0.01),
    "surprised": (-0.17, -0.12, -0.08),
    "low": (0.06, 0.06, -0.02),
    "evil": {"l": (0.14, -0.08, 0.0), "r": (-0.12, -0.2, -0.08)},
    "worried_asym": {"l": (-0.16, 0.02, -0.01), "r": (-0.07, 0.07, -0.01)},
    "smirk": {"l": (0.02, 0.03, -0.03), "r": (-0.1, -0.16, -0.08)},
}


def draw_brows(c: skia.Canvas, g: Geo, state: str) -> None:
    p = g.p
    if p.face == "none" or g.ent:
        return
    hc = p.hair_color
    if p.hair_style in ("bald", "none_entity", "cap_hidden") and not p.brow_color:
        hc = mix(hc, "#3a302c", 0.4) if luma(hc) > 0.5 else hc
    col = p.brow_color or (hc if luma(hc) < 0.6 else mix(hc, "#6a625a", 0.45))
    shp = BROWS.get(state, BROWS["neutral"])
    by = g.ey - 0.33 * g.ry
    th =g.ry * (0.085 if p.gender == "male" else 0.06) * (1.1 if p.age == "old" and p.gender == "male" else 1.0)
    for s in ("l", "r"):
        di, do, arch = shp[s] if isinstance(shp, dict) else shp
        ex = g.ex[s]
        sg = 1 if s == "l" else -1           # +x hướng vào giữa
        inner_x = ex + sg * g.erx * 1.3
        outer_x = ex - sg * g.erx * 1.75
        pi = (inner_x, by + di * g.ry)
        po = (outer_x, by + do * g.ry + 0.03 * g.ry)
        mid = ((pi[0] + po[0]) / 2, (pi[1] + po[1]) / 2 + arch * g.ry)
        c.drawPath(smooth([po, mid, pi], close=False), pen(col, th))


# ---------------------------------------------------------------- miệng
def _wave(x0: float, x1: float, y: float, amp: float, n: int) -> list[tuple[float, float]]:
    pts = []
    steps = n * 4
    for i in range(steps + 1):
        t = i / steps
        pts.append((x0 + (x1 - x0) * t, y + amp * math.sin(t * n * math.tau)))
    return pts


def draw_mouth(c: skia.Canvas, g: Geo, shape: str) -> None:
    p = g.p
    if p.face == "none":
        return
    mx, my, mw, ry = g.mx, g.my, g.mw, g.ry
    lw = g.rx * 0.042
    lipc = p.lip_color
    line_col = LINE_INK if not lipc else mul(lipc, 0.75)
    if g.ent:
        if shape in ("X", "A", "flat", "smile", "smirk", "grin", "frown", "wavy", "wavy_small"):
            seam(c, [(mx - mw * 1.6, my - ry * 0.12), (mx - mw * 0.5, my + ry * 0.05), (mx + mw * 0.6, my + ry * 0.05),
                     (mx + mw * 1.7, my - ry * 0.14)], EYE_INK, lw * 0.8)
        else:
            c.drawPath(oval(mx, my + ry * 0.04, mw * 0.5, ry * 0.12), paint(MOUTH_IN))
        return

    def opening(wf: float, hf: float, dy: float = 0.0, flat_top: float = 0.45) -> skia.Path:
        w, h = mw * wf, ry * hf
        return smooth([(mx - w, my + dy), (mx - w * 0.55, my - h * flat_top + dy), (mx + w * 0.55, my - h * flat_top + dy),
                       (mx + w, my + dy), (mx + w * 0.5, my + h * 0.62 + dy), (mx - w * 0.5, my + h * 0.62 + dy)],
                      tension=0.48)

    def fill_open(pth: skia.Path, teeth_top: float = 0.0, teeth_bot: float = 0.0, tongue: bool = True,
                  tongue_up: bool = False) -> None:
        c.drawPath(pth, paint(MOUTH_IN))
        c.save()
        c.clipPath(pth, doAntiAlias=True)
        b = pth.getBounds()
        if teeth_top > 0:
            c.drawPath(rrect(b.left() - 4, b.top() - 4, b.right() + 4, b.top() + b.height() * teeth_top, 2), paint(TEETH))
        if teeth_bot > 0:
            c.drawPath(rrect(b.left() - 4, b.bottom() - b.height() * teeth_bot, b.right() + 4, b.bottom() + 4, 2),
                       paint(TEETH, 0.95))
        if tongue:
            if tongue_up:
                c.drawPath(oval(mx, b.top() + b.height() * 0.45, b.width() * 0.22, b.height() * 0.34), paint(TONGUE))
            else:
                c.drawPath(oval(mx, b.bottom() + b.height() * 0.05, b.width() * 0.34, b.height() * 0.42), paint(TONGUE))
        c.restore()
        if lipc:
            c.drawPath(pth, pen(lipc, lw * 0.9, 0.9))

    def gap_tooth(pth: skia.Path, teeth_frac: float) -> None:
        """Răng sún (trẻ con): khoảng hở giữa hàng răng trên."""
        if "gap_tooth" not in p.accessories:
            return
        c.save()
        c.clipPath(pth, doAntiAlias=True)
        b = pth.getBounds()
        c.drawRect(skia.Rect.MakeLTRB(mx + mw * 0.02, b.top() - 2, mx + mw * 0.24, b.top() + b.height() * teeth_frac + 1),
                   paint(MOUTH_IN))
        c.restore()

    def lips_rest(pts_line: list) -> None:
        if lipc:  # môi nữ: tô nhẹ môi dưới
            c.drawPath(oval(mx, my + ry * 0.055, mw * 0.36, ry * 0.035), paint(lipc, 0.85))
        seam(c, pts_line, line_col, lw)

    if shape == "X":
        lips_rest([(mx - mw * 0.62, my - ry * 0.005), (mx, my + ry * 0.03), (mx + mw * 0.62, my - ry * 0.01)])
    elif shape == "flat":
        lips_rest([(mx - mw * 0.55, my + ry * 0.01), (mx + mw * 0.55, my + ry * 0.005)])
    elif shape == "A":
        seam(c, [(mx - mw * 0.55, my), (mx, my + ry * 0.008), (mx + mw * 0.55, my - ry * 0.004)], line_col, lw * 1.25)
        if lipc:
            c.drawPath(oval(mx, my + ry * 0.045, mw * 0.32, ry * 0.03), paint(lipc, 0.85))
    elif shape == "smile":
        o = smooth([(mx - mw * 0.95, my - ry * 0.06), (mx, my - ry * 0.01), (mx + mw * 0.95, my - ry * 0.07),
                    (mx + mw * 0.5, my + ry * 0.14), (mx - mw * 0.5, my + ry * 0.14)], tension=0.5)
        fill_open(o, teeth_top=0.42, tongue=True)
        gap_tooth(o, 0.42)
        seam(c, [(mx - mw * 1.05, my - ry * 0.1), (mx - mw * 0.92, my - ry * 0.05)], line_col, lw * 0.8, curve=False)
        seam(c, [(mx + mw * 1.05, my - ry * 0.11), (mx + mw * 0.92, my - ry * 0.06)], line_col, lw * 0.8, curve=False)
    elif shape == "frown":
        seam(c, [(mx - mw * 0.55, my + ry * 0.06), (mx, my - ry * 0.035), (mx + mw * 0.55, my + ry * 0.06)], line_col, lw)
    elif shape in ("wavy", "wavy_small"):
        k = 1.0 if shape == "wavy" else 0.62
        seam(c, _wave(mx - mw * 0.85 * k, mx + mw * 0.85 * k, my + ry * 0.02, ry * 0.035 * (0.7 + 0.3 * k),
                      2 if shape == "wavy" else 1), line_col, lw * 0.95)
    elif shape == "o_small":
        o = oval(mx, my + ry * 0.03, mw * 0.24, ry * 0.085)
        c.drawPath(o, paint(MOUTH_IN))
        c.save()
        c.clipPath(o, doAntiAlias=True)
        c.drawPath(oval(mx, my + ry * 0.1, mw * 0.2, ry * 0.05), paint(TONGUE))
        c.restore()
    elif shape == "sob":
        pts = _wave(mx - mw * 0.5, mx + mw * 0.5, my - ry * 0.03, ry * 0.015, 2)
        pts += [(mx + mw * 0.55, my + ry * 0.05), (mx + mw * 0.3, my + ry * 0.13), (mx - mw * 0.3, my + ry * 0.13),
                (mx - mw * 0.55, my + ry * 0.05)]
        o = smooth(pts, tension=0.35)
        fill_open(o, teeth_top=0.0, tongue=True)
    elif shape == "smirk":
        seam(c, [(mx - mw * 0.45, my + ry * 0.03), (mx + mw * 0.25, my + ry * 0.02), (mx + mw * 0.62, my - ry * 0.035),
                 (mx + mw * 0.78, my - ry * 0.08)], line_col, lw)
        seam(c, [(mx + mw * 0.72, my - ry * 0.1), (mx + mw * 0.86, my - ry * 0.05)], line_col, lw * 0.7, curve=False)
    elif shape == "grin":
        o = smooth([(mx - mw * 0.75, my + ry * 0.0), (mx, my - ry * 0.02), (mx + mw * 1.0, my - ry * 0.13),
                    (mx + mw * 0.55, my + ry * 0.12), (mx - mw * 0.35, my + ry * 0.08)], tension=0.45)
        fill_open(o, teeth_top=0.55, teeth_bot=0.25, tongue=False)
        c.save()
        c.clipPath(o, doAntiAlias=True)
        b = o.getBounds()
        for t in (0.3, 0.5, 0.7):
            x = b.left() + b.width() * t
            c.drawPath(poly([(x, b.top()), (x, b.bottom())], close=False), pen("#c9c0b2", 1.2))
        c.restore()
    elif shape == "shout":
        fill_open(opening(1.0, 0.36, ry * 0.04, 0.5), teeth_top=0.22, teeth_bot=0.12)
    elif shape == "clench":   # nghiến răng: hàng răng trắng kín, khoé trễ
        o = smooth([(mx - mw * 0.8, my + ry * 0.035), (mx - mw * 0.5, my - ry * 0.05), (mx + mw * 0.5, my - ry * 0.055),
                    (mx + mw * 0.8, my + ry * 0.03), (mx + mw * 0.5, my + ry * 0.085), (mx - mw * 0.5, my + ry * 0.085)],
                   tension=0.4)
        c.drawPath(o, paint(TEETH))
        c.save()
        c.clipPath(o, doAntiAlias=True)
        b = o.getBounds()
        c.drawPath(poly([(b.left(), my + ry * 0.015), (b.right(), my + ry * 0.015)], close=False), pen("#b9ada0", lw * 0.6))
        for t in (0.22, 0.4, 0.6, 0.78):
            x = b.left() + b.width() * t
            c.drawPath(poly([(x, b.top()), (x, b.bottom())], close=False), pen("#c9bfb2", lw * 0.45))
        c.restore()
        c.drawPath(o, pen(line_col, lw * 0.8))
        for s in (-1, 1):
            seam(c, [(mx + s * mw * 0.8, my + ry * 0.035), (mx + s * mw * 0.98, my + ry * 0.085)], line_col, lw * 0.75,
                 curve=False)
    elif shape == "laugh":    # cười lớn: miệng mở rộng chữ D, răng trên + lưỡi
        o = smooth([(mx - mw * 1.08, my - ry * 0.07), (mx, my - ry * 0.035), (mx + mw * 1.08, my - ry * 0.08),
                    (mx + mw * 0.62, my + ry * 0.22), (mx, my + ry * 0.29), (mx - mw * 0.62, my + ry * 0.22)], tension=0.5)
        fill_open(o, teeth_top=0.24, tongue=True)
        gap_tooth(o, 0.24)
        for s in (-1, 1):
            seam(c, [(mx + s * mw * 1.2, my - ry * 0.12), (mx + s * mw * 1.04, my - ry * 0.06)], line_col, lw * 0.8,
                 curve=False)
    elif shape == "B":
        fill_open(opening(0.72, 0.09), teeth_top=1.0, tongue=False)
        c.drawPath(poly([(mx - mw * 0.7, my + 1), (mx + mw * 0.7, my + 1)], close=False), pen("#c9c0b2", 1.2))
    elif shape == "C":
        fill_open(opening(0.78, 0.17), teeth_top=0.28)
    elif shape == "D":
        fill_open(opening(0.88, 0.3, ry * 0.02), teeth_top=0.2)
    elif shape == "E":
        fill_open(opening(0.56, 0.2), teeth_top=0.16)
    elif shape == "F":
        o = oval(mx, my + 1, mw * 0.26, ry * 0.07)
        c.drawPath(oval(mx, my + 1, mw * 0.4, ry * 0.1), paint(mul(p.skin, 0.86)))
        c.drawPath(o, paint(MOUTH_IN))
        if lipc:
            c.drawPath(o, pen(lipc, lw * 0.9))
    elif shape == "G":
        o = opening(0.7, 0.1)
        fill_open(o, tongue=False)
        c.drawPath(rrect(mx - mw * 0.45, my - ry * 0.045, mx + mw * 0.45, my + ry * 0.025, 2), paint(TEETH))
        seam(c, [(mx - mw * 0.6, my + ry * 0.045), (mx + mw * 0.6, my + ry * 0.045)], line_col, lw, curve=False)
    elif shape == "H":
        fill_open(opening(0.74, 0.17), teeth_top=0.22, tongue_up=True)


# ---------------------------------------------------------------- FX mặt
def _drop(cx: float, cy: float, h: float) -> skia.Path:
    w = h * 0.42
    return smooth([(cx, cy - h * 0.55), (cx + w * 0.55, cy + h * 0.05), (cx + w * 0.5, cy + h * 0.3),
                   (cx, cy + h * 0.45), (cx - w * 0.5, cy + h * 0.3), (cx - w * 0.55, cy + h * 0.05)], tension=0.5)


def draw_fx(c: skia.Canvas, g: Geo, kind: str) -> None:
    p = g.p
    if p.face == "none":
        return
    if kind == "sweat":
        h = g.hh * 0.11
        x, y = g.U(g.fu + 0.92), g.V(-0.38)
        d = _drop(x, y, h)
        c.drawPath(d, paint(SWEAT))
        c.drawPath(d, pen(lit(SWEAT, 0.6), g.rx * 0.02))
        c.drawPath(oval(x - h * 0.06, y + h * 0.08, h * 0.06, h * 0.1), paint("#ffffff", 0.9))
    elif kind == "dashes":
        for i, (u0, v0) in enumerate(((0.45, -1.28), (0.72, -1.18), (0.95, -1.02))):
            x0, y0 = g.P(u0, v0)
            x1, y1 = x0 + g.rx * 0.12, y0 - g.ry * 0.12
            c.drawPath(poly([(x0, y0), (x1, y1)], close=False), pen(DASH, g.rx * 0.045))
    elif kind == "tears":
        for s in ("l", "r"):
            ex, ey = g.ex[s], g.ey
            c.drawPath(oval(ex, ey + g.ery * 1.0, g.erx * 1.6, g.ery * 0.32), paint(TEAR, 0.85))
            sx = ex + (g.erx * 0.6 if s == "r" else -g.erx * 0.6)
            stream = smooth([(sx - g.rx * 0.035, ey + g.ery * 1.0), (sx + g.rx * 0.035, ey + g.ery * 1.0),
                             (sx + g.rx * 0.05, g.V(0.5)), (sx + g.rx * 0.03, g.V(0.78)), (sx - g.rx * 0.02, g.V(0.78)),
                             (sx - g.rx * 0.03, g.V(0.5))], tension=0.4)
            c.drawPath(stream, paint(TEAR, 0.8))
            c.drawPath(_drop(sx, g.V(0.92), g.hh * 0.06), paint(TEAR, 0.9))
    elif kind == "vein":
        x, y = g.P(g.fu + 0.55, -0.5)
        r = g.rx * 0.12
        for ang in (45, 135, 225, 315):
            a = math.radians(ang)
            p0 = (x + math.cos(a) * r * 0.35, y + math.sin(a) * r * 0.35)
            p1 = (x + math.cos(a) * r, y + math.sin(a) * r)
            mid = ((p0[0] + p1[0]) / 2 + math.cos(a + 1.57) * r * 0.2, (p0[1] + p1[1]) / 2 + math.sin(a + 1.57) * r * 0.2)
            c.drawPath(smooth([p0, mid, p1], close=False), pen(VEIN, g.rx * 0.045))
    elif kind == "flush":
        for s in (-1, 1):
            cxb, cyb = g.P(g.fu + s * 0.55, 0.42)
            pb = skia.Paint(AntiAlias=True, Color=color("#e5505c", 0.55),
                            MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, g.rx * 0.04))
            c.drawPath(oval(cxb, cyb, 0.19 * g.rx, 0.09 * g.ry), pb)
            for i in range(3):
                x0 = cxb - g.rx * 0.1 + i * g.rx * 0.08
                c.drawPath(poly([(x0, cyb + g.ry * 0.04), (x0 + g.rx * 0.05, cyb - g.ry * 0.05)], close=False),
                           pen("#c9404a", g.rx * 0.018, 0.8))
    elif kind == "eyebags_heavy":
        for s in ("l", "r"):
            ex, ey = g.ex[s], g.ey
            pth = diff(oval(ex, ey + g.ery * 1.3, g.erx * 2.3, g.ery * 0.95),
                       oval(ex, ey + g.ery * 0.7, g.erx * 2.5, g.ery * 0.9))
            c.drawPath(pth, skia.Paint(AntiAlias=True, Color=color("#6a4f76", 0.55),
                                       MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, g.rx * 0.015)))
    elif kind == "shade":
        fp = face_path(g)
        c.save()
        c.clipPath(fp, doAntiAlias=True)
        b = fp.getBounds()
        pr = skia.Paint(AntiAlias=True)
        pr.setShader(_lin((0, b.top()), (0, g.ey + g.ery), color("#1a1424", 0.55), color("#1a1424", 0.0)))
        c.drawRect(b, pr)
        c.restore()


def draw_drips(c: skia.Canvas, g: Geo) -> None:
    """Ma nước: giọt rơi từ đuôi tóc/cằm (tĩnh, gắn đầu)."""
    hs = g.p.hair_style
    long_ = hs in ("long_straight", "long_over_face", "long_ponytail")
    tips = [(-0.95, 1.25), (0.9, 1.2), (-0.4, 1.3)] if hs == "bob_bangs" else \
        ([(-1.0, 2.3), (0.95, 2.25), (0.2, 2.5)] if long_ else [(0.0, 1.15), (-0.7, 0.9)])
    for i, (u, v) in enumerate(tips):
        x, y = g.P(u, v)
        c.drawPath(_drop(x, y, g.hh * 0.07), paint(DRIP, 0.9))
        c.drawPath(_drop(x + g.rx * 0.02, y + g.hh * 0.14, g.hh * 0.045), paint(DRIP, 0.7))


# ======================================================================= tóc
def _cap_outer(top_v: float = -1.12, side_v: float = 0.05, w: float = 1.06) -> list[tuple[float, float]]:
    return [(-w, side_v), (-w * 1.02, -0.45), (-w * 0.78, -0.92), (0.0, top_v), (w * 0.78, -0.92), (w * 1.02, -0.45),
            (w, side_v)]


def hair_back_path(g: Geo) -> skia.Path | None:
    """Khối tóc phía sau đầu (front view: vẽ sau đầu & thân)."""
    hs = g.p.hair_style
    sy = g.shoulder_y
    if hs == "long_straight":
        bot = sy + 0.2 * g.Hf
        pts = g.pts([(-1.1, -0.55), (-0.8, -1.05), (0, -1.16), (0.8, -1.05), (1.1, -0.55)])
        pts += [(g.U(1.28), g.V(0.6)), (g.U(1.42), sy), (g.U(1.45), bot - 20), (g.U(1.1), bot), (g.U(0.4), bot - 8),
                (g.U(-0.4), bot - 8), (g.U(-1.1), bot), (g.U(-1.45), bot - 20), (g.U(-1.42), sy), (g.U(-1.28), g.V(0.6))]
        return smooth(pts, tension=0.4)
    if hs == "long_over_face":
        bot = g.waist_y - 0.02 * g.Hf
        pts = g.pts([(-1.12, -0.5), (-0.8, -1.06), (0, -1.16), (0.8, -1.06), (1.12, -0.5)])
        pts += [(g.U(1.35), g.V(0.8)), (g.U(1.55), sy + 20), (g.U(1.6), bot - 30), (g.U(1.3), bot + 10), (g.U(0.9), bot - 10),
                (g.U(0.4), bot + 14), (g.U(-0.2), bot - 6), (g.U(-0.8), bot + 12), (g.U(-1.3), bot - 8),
                (g.U(-1.6), bot - 40), (g.U(-1.55), sy + 20), (g.U(-1.35), g.V(0.8))]
        return poly(pts)
    if hs == "bob_bangs":
        pts = g.pts([(-1.15, -0.4), (-0.85, -1.04), (0, -1.16), (0.85, -1.04), (1.15, -0.4), (1.26, 0.5), (1.24, 1.08),
                     (1.0, 1.16), (-1.0, 1.16), (-1.24, 1.08), (-1.26, 0.5)])
        return smooth(pts, tension=0.35)
    if hs == "afro_curly":
        return union(*[circle(*g.P(math.cos(a) * 1.05, -0.25 + math.sin(a) * 0.95), g.rx * 0.38)
                       for a in [math.radians(x) for x in range(150, 400, 25)]])
    if hs == "long_ponytail" and not g.p.pigtails:
        tail = smooth([g.P(-0.7, -0.6), g.P(-1.05, -0.75), g.P(-1.35, -0.2), (g.U(-1.45), g.V(0.9)), (g.U(-1.3), sy + 0.06 * g.Hf),
                       (g.U(-1.05), sy + 0.1 * g.Hf), (g.U(-1.1), g.V(0.9)), g.P(-1.0, 0.0)], tension=0.45)
        return tail
    return None


def draw_hair_back(c: skia.Canvas, g: Geo) -> None:
    if "low_ponytail" in g.p.accessories:   # front view: chỉ lộ một nhúm đuôi tóc sau gáy, lệch trái
        sy = g.shoulder_y
        tail = smooth([g.P(-0.55, 0.55), g.P(-0.9, 0.7), (g.U(-1.02), sy + 0.02 * g.Hf), (g.U(-0.86), sy + 0.07 * g.Hf),
                       (g.U(-0.62), sy + 0.03 * g.Hf), g.P(-0.5, 0.95)], tension=0.45)
        hair_fill(c, tail, g, col=mul(g.p.hair_color, 0.9) if luma(g.p.hair_color) > 0.2 else g.p.hair_color)
    pth = hair_back_path(g)
    if pth is None:
        return
    hs = g.p.hair_style
    hc = mul(g.p.hair_color, 0.9) if luma(g.p.hair_color) > 0.2 else g.p.hair_color
    hair_fill(c, pth, g, col=hc)
    dk = mul(hc, 0.6) if luma(hc) > 0.1 else lit(hc, 0.12)
    if hs in ("long_straight", "long_over_face"):
        strand = g.p.colors.get("strand") or mix(hc, "#3a3a44", 0.6)
        for u in (-1.35, -1.15, 1.15, 1.35):
            seam(c, [(g.U(u), g.V(0.8)), (g.U(u * 1.04), g.shoulder_y), (g.U(u * 1.03), g.shoulder_y + 0.15 * g.Hf)],
                 strand if hs == "long_over_face" else dk, g.rx * 0.025, 0.8)
    if hs == "long_ponytail" and g.p.hair_tie:
        c.drawPath(rrect(g.U(-1.2), g.V(-0.5), g.U(-0.95), g.V(-0.32), g.rx * 0.05), paint(g.p.hair_tie))


def draw_hair_front(c: skia.Canvas, g: Geo) -> None:
    p = g.p
    hs = p.hair_style
    hc = p.hair_color
    acc = p.accessories
    if hs == "none_entity":
        return
    if hs == "bald":
        c.save()
        c.clipPath(face_path(g), doAntiAlias=True)
        c.drawPath(oval(*g.P(0.2, -0.78), 0.22 * g.rx, 0.09 * g.ry), paint("#ffffff", 0.45))
        c.restore()
        if p.age == "old":
            for s in (-1, 1):  # viền tóc bạc hai bên
                tuft = smooth(g.pts([(s * 0.9, -0.42), (s * 1.06, -0.3), (s * 1.08, 0.02), (s * 0.98, 0.12),
                                     (s * 0.93, -0.12)]), tension=0.5)
                hair_fill(c, tuft, g, col=hc)
        return
    if hs == "cap_hidden":
        cap = p.cap_color or p.colors.get("cap") or "#24365a"
        for s in (-1, 1):  # tóc mai ngắn dưới mũ
            side = smooth(g.pts([(s * 0.86, -0.4), (s * 1.06, -0.36), (s * 1.06, 0.05), (s * 0.95, 0.12),
                                 (s * 0.9, -0.1)]), tension=0.5)
            hair_fill(c, side, g)
        dome = smooth(g.pts([(-1.1, -0.3), (-1.08, -0.7), (-0.75, -1.08), (0, -1.2), (0.75, -1.08), (1.08, -0.7),
                             (1.1, -0.3), (0, -0.36)]), tension=0.42)
        flat(c, dome, cap, d=0.18 * g.rx, rim=0.3)
        band = inter(dome, rrect(g.U(-1.3), g.V(-0.48), g.U(1.3), g.V(-0.25), 0))
        c.drawPath(band, paint(mul(cap, 0.82)))
        seam(c, g.pts([(0, -1.2), (0.05, -0.75), (0, -0.42)]), mul(cap, 0.65), g.rx * 0.025, 0.8)
        seam(c, g.pts([(-0.55, -1.05), (-0.45, -0.7), (-0.5, -0.4)]), mul(cap, 0.65), g.rx * 0.02, 0.6)
        seam(c, g.pts([(0.55, -1.05), (0.5, -0.7), (0.55, -0.4)]), mul(cap, 0.65), g.rx * 0.02, 0.6)
        c.drawPath(circle(*g.P(0, -1.18), g.rx * 0.07), paint(mul(cap, 0.75)))
        brim = smooth(g.pts([(-1.02, -0.32), (-0.5, -0.4), (0.2, -0.42), (0.95, -0.36), (1.12, -0.26), (0.6, -0.06),
                             (0.05, -0.02), (-0.6, -0.1)]), tension=0.45)
        flat(c, brim, mul(cap, 0.9), d=0.1 * g.rx, rim=0.25, hl=0.2)
        c.save()
        c.clipPath(face_path(g), doAntiAlias=True)
        sh = smooth(g.pts([(-1.0, -0.12), (0.0, 0.02), (1.05, -0.12), (1.05, 0.05), (0, 0.16), (-1.0, 0.05)]))
        c.drawPath(sh, paint("#000000", 0.12))
        c.restore()
        return
    if hs == "buzz":
        outer = smooth(g.pts(_cap_outer(-1.07, -0.05, 1.03) + [(0.92, -0.35), (0.5, -0.55), (0, -0.6), (-0.5, -0.55),
                                                                (-0.92, -0.35)]), tension=0.45)
        hair_fill(c, outer, g, col=mix(hc, p.skin, 0.18), arc=[(-0.5, -0.88), (0, -0.98), (0.45, -0.9)])
        return
    if hs == "spiky":
        for s in (-1, 1):  # hai bên cạo: mảng màu da nhạt
            shave = smooth(g.pts([(s * 0.82, -0.62), (s * 1.06, -0.5), (s * 1.07, -0.02), (s * 0.95, 0.06),
                                  (s * 0.88, -0.3)]), tension=0.45)
            c.drawPath(shave, paint(mix(p.skin, hc, 0.35)))
        outer = [(-1.0, -0.5), (-1.02, -0.85), (-1.05, -1.2), (-0.72, -1.08), (-0.55, -1.45), (-0.25, -1.14),
                 (0.02, -1.52), (0.24, -1.14), (0.55, -1.42), (0.7, -1.04), (1.04, -1.18), (1.02, -0.82), (1.0, -0.5)]
        fringe = [(0.98, -0.5), (0.6, -0.56), (0.2, -0.5), (-0.12, -0.32), (-0.36, -0.05), (-0.44, -0.4), (-0.7, -0.55),
                  (-0.98, -0.52)]
        pth = poly(g.pts(outer + fringe))
        c.drawPath(pth, paint(hc, 1))
        hair_fill(c, pth, g, arc=[(-0.55, -0.95), (-0.1, -1.08), (0.4, -1.0)],
                  strokes=[[(0.5, -0.62), (0.05, -0.5), (-0.25, -0.22)], [(0.75, -0.75), (0.45, -0.72)]])
        return
    if hs == "slick_side_part":   # rẽ ngôi lệch, chải bóng ra sau: mép tóc gọn, 2 cung bóng
        inner = [(0.98, -0.05), (0.9, -0.45), (0.6, -0.66), (0.2, -0.74), (-0.22, -0.74), (-0.36, -0.9), (-0.52, -0.66),
                 (-0.88, -0.48), (-0.98, -0.05)]
        pth = smooth(g.pts(_cap_outer(-1.1, 0.0, 1.06) + inner), tension=0.42)
        hair_fill(c, pth, g, arc=[(-0.1, -1.0), (0.4, -0.95), (0.78, -0.72)],
                  strokes=[[(-0.25, -0.86), (0.25, -0.86), (0.7, -0.66)], [(-0.62, -0.92), (-0.82, -0.66)]])
        seam(c, g.pts([(-0.38, -1.08), (-0.37, -0.88)]), lit(hc, 0.25) if luma(hc) < 0.3 else mul(hc, 0.6), g.rx * 0.03, 0.9)
        return
    if hs == "bowl_cut":          # tóc bát úp: mái bằng thẳng ngang trán, hai bên phủ tai
        inner = [(1.0, 0.16), (0.94, -0.28), (0.6, -0.34), (0.2, -0.36), (-0.2, -0.36), (-0.6, -0.34), (-0.94, -0.28),
                 (-1.0, 0.16)]
        pth = smooth(g.pts(_cap_outer(-1.12, 0.16, 1.1) + inner), tension=0.36)
        hair_fill(c, pth, g, arc=[(-0.5, -0.86), (0.0, -0.98), (0.5, -0.86)],
                  strokes=[[(-0.45, -0.5), (-0.48, -0.38)], [(0.05, -0.52), (0.04, -0.4)], [(0.5, -0.5), (0.52, -0.38)]])
        return
    if hs in ("short_side_part", "grey_short"):
        rec = hs == "grey_short"
        inner = [(0.98, 0.02), (0.92, -0.38), (0.55, -0.55 if not rec else -0.68), (0.1, -0.6 if not rec else -0.74),
                 (-0.3, -0.72 if not rec else -0.8), (-0.42, -0.86), (-0.6, -0.56), (-0.92, -0.4), (-0.98, 0.02)]
        pth = smooth(g.pts(_cap_outer(-1.13, 0.06, 1.07) + inner), tension=0.42)
        hair_fill(c, pth, g, arc=[(-0.2, -1.0), (0.3, -0.98), (0.7, -0.78)],
                  strokes=[[(-0.42, -1.08), (-0.4, -0.88)], [(0.55, -0.7), (0.2, -0.66)]])
        seam(c, g.pts([(-0.44, -1.1), (-0.42, -0.86)]), mul(hc, 0.6) if luma(hc) > 0.2 else lit(hc, 0.2), g.rx * 0.03, 0.9)
        return
    if hs in ("curly_short", "afro_curly"):
        big = hs == "afro_curly"
        hl = p.hair_highlight or lit(hc, 0.3)
        blobs = []
        ring = [(-1.0, 0.05), (-1.06, -0.3), (-0.98, -0.66), (-0.72, -0.95), (-0.36, -1.12), (0.02, -1.18), (0.4, -1.12),
                (0.74, -0.95), (0.98, -0.66), (1.06, -0.3), (1.0, 0.05)]
        inner = [(-0.62, -0.62), (-0.25, -0.72), (0.15, -0.74), (0.52, -0.64)]
        r = 0.3 if not big else 0.36
        k = 1.0 if not big else 1.12
        for u, v in ring:
            blobs.append((u * k, v * k - (0.05 if big else 0), r))
        for u, v in inner:
            blobs.append((u, v - (0.08 if big else 0), r * 0.85))
        for u, v, rr in blobs:
            b = circle(*g.P(u, v), g.rx * rr)
            c.drawPath(b, paint(hc))
            c.drawPath(b, pen(mul(hc, 0.75), g.rx * 0.02, 0.6))
        for u, v, rr in blobs:  # mỗi lọn 1 cung sáng
            x, y = g.P(u, v)
            arcp = skia.Path()
            arcp.addArc(skia.Rect.MakeLTRB(x - g.rx * rr * 0.6, y - g.rx * rr * 0.6, x + g.rx * rr * 0.6, y + g.rx * rr * 0.6),
                        200, 100)
            c.drawPath(arcp, pen(hl, g.rx * 0.035, 0.85))
        return
    if hs == "bun":
        bun = circle(*g.P(0, -1.12), 0.36 * g.rx)
        hair_fill(c, bun, g, arc=[(-0.18, -1.3), (0.0, -1.38), (0.18, -1.3)])
        inner = [(0.98, 0.0), (0.9, -0.4), (0.55, -0.62), (0.0, -0.7), (-0.55, -0.62), (-0.9, -0.4), (-0.98, 0.0)]
        pth = smooth(g.pts(_cap_outer(-1.08, 0.04, 1.05) + inner), tension=0.42)
        hair_fill(c, pth, g, arc=[(-0.5, -0.86), (0.0, -0.98), (0.5, -0.86)],
                  strokes=[[(-0.3, -0.75), (-0.5, -0.95)], [(0.3, -0.75), (0.5, -0.95)]])
        if any(a.startswith("hair_clip") for a in acc):
            c.drawPath(rrect(g.U(0.45), g.V(-1.0), g.U(0.75), g.V(-0.9), g.rx * 0.04), paint(p.colors.get("clip", "#d64545")))
        return
    if hs == "long_ponytail":
        inner = [(0.98, 0.05), (0.9, -0.4), (0.5, -0.6), (0.06, -0.72), (0.0, -0.86), (-0.08, -0.72), (-0.5, -0.6),
                 (-0.9, -0.4), (-0.98, 0.05)]
        pth = smooth(g.pts(_cap_outer(-1.1, 0.08, 1.06) + inner), tension=0.42)
        hair_fill(c, pth, g, arc=[(-0.55, -0.85), (-0.2, -0.98)], strokes=[[(0.3, -0.98), (0.55, -0.82)]])
        if p.pigtails:
            tie = p.hair_tie or "#e05a7a"
            for s in (-1, 1):
                tuft = smooth(g.pts([(s * 0.95, -0.55), (s * 1.3, -0.5), (s * 1.48, -0.05), (s * 1.42, 0.45),
                                     (s * 1.25, 0.2), (s * 1.12, -0.2)]), tension=0.45)
                hair_fill(c, tuft, g, strokes=[[(s * 1.28, -0.3), (s * 1.36, 0.1)]])
                c.drawPath(circle(*g.P(s * 1.05, -0.5), g.rx * 0.1), paint(tie))
        return
    if hs == "long_straight":
        bot = (g.shoulder_y + 0.09 * g.Hf - g.hy) / g.ry
        L = [(-1.13, bot), (-1.14, -0.5), (-0.82, -1.02), (0, -1.15), (0.82, -1.02), (1.14, -0.5), (1.13, bot),
             (0.98, bot + 0.12), (0.82, bot), (0.8, 0.4), (0.84, -0.1), (0.62, -0.5), (0.25, -0.68), (0.03, -0.9),
             (-0.2, -0.66), (-0.6, -0.52), (-0.84, -0.1), (-0.8, 0.4), (-0.82, bot), (-0.98, bot + 0.12)]
        pth = smooth(g.pts(L), tension=0.35)
        hair_fill(c, pth, g, arc=[(-0.55, -0.9), (-0.15, -1.04)], strokes=[[(0.3, -1.02), (0.6, -0.9)],
                                                                          [(-1.0, 0.2), (-1.02, 0.9)],
                                                                          [(1.0, 0.2), (1.02, 0.9)]])
        if any(a.startswith("hair_clip") for a in acc):
            c.drawPath(rrect(g.U(0.5), g.V(-0.68), g.U(0.84), g.V(-0.58), g.rx * 0.04), paint(p.colors.get("clip", "#d64545")))
        return
    if hs == "bob_bangs":
        top = _cap_outer(-1.13, 0.0, 1.1)
        bangs = []
        n = 9
        for i in range(n + 1):  # mái cắt răng cưa / gợn
            u = 0.92 - 1.84 * i / n
            v = -0.3 + (0.06 if i % 2 else -0.02)
            bangs.append((u, v))
        pth = smooth(g.pts(top[:-1] + [(1.1, -0.3)] + bangs + [(-1.1, -0.3)]), tension=0.25)
        hair_fill(c, pth, g, arc=[(-0.5, -0.88), (0.0, -1.0), (0.5, -0.88)],
                  strokes=[[(-0.4, -0.55), (-0.45, -0.32)], [(0.2, -0.58), (0.18, -0.34)]])
        for s in (-1, 1):  # 2 lọn mảnh hai bên má
            lock = smooth(g.pts([(s * 0.8, -0.32), (s * 1.02, -0.3), (s * 1.0, 0.6), (s * 0.92, 0.98), (s * 0.8, 0.6),
                                 (s * 0.78, 0.1)]), tension=0.4)
            hair_fill(c, lock, g)
        if any(a.startswith("hair_clip") for a in acc):
            clip = p.colors.get("clip", "#d64545")
            r = rrect(g.U(0.42), g.V(-0.56), g.U(0.8), g.V(-0.44), g.rx * 0.05)
            c.drawPath(r, paint(clip))
            c.drawPath(rrect(g.U(0.47), g.V(-0.54), g.U(0.62), g.V(-0.5), g.rx * 0.02), paint("#ffffff", 0.55))
        return
    if hs == "long_over_face":
        bot = (g.chin + 0.4 * g.hh - g.hy) / g.ry
        strand = p.colors.get("strand") or "#3a3a44"
        pts = [(-1.15, 0.6), (-1.16, -0.5), (-0.82, -1.04), (0, -1.16), (0.82, -1.04), (1.16, -0.5), (1.15, 0.6),
               (1.08, bot)]
        n = 10
        for i in range(n + 1):
            u = 1.0 - 2.0 * i / n
            pts.append((u, bot + (0.18 if i % 2 else -0.05) + 0.06 * math.sin(i * 1.7)))
        pts.append((-1.08, bot))
        pth = poly(g.pts(pts))
        # khe tóc hẹp lộ 1 mắt + mày (mô-típ "mắt nhìn qua kẽ tóc"): giữ mặt gần như phủ kín nhưng
        # biểu cảm (shocked / tired / smirk / crying...) vẫn đọc được qua con mắt đó.
        ex, ey, erx, ery = g.ex["r"], g.ey, g.erx, g.ery
        slit = smooth([(ex + erx * 0.25, ey - ery * 5.0), (ex + erx * 1.9, ey - ery * 1.2),
                       (ex + erx * 1.5, ey + ery * 1.6), (ex + erx * 0.2, ey + ery * 2.6),
                       (ex - erx * 1.4, ey + ery * 1.5), (ex - erx * 1.9, ey - ery * 1.0),
                       (ex - erx * 0.6, ey - ery * 4.4)], tension=0.45)
        pth = diff(pth, slit)
        hair_fill(c, pth, g, arc=[(-0.4, -0.95), (0.1, -1.05)])
        c.save()
        c.clipPath(pth, doAntiAlias=True)
        for i in range(11):
            u = -0.95 + 0.19 * i
            seam(c, g.pts([(u, -0.6), (u + 0.04 * math.sin(i), 0.3), (u - 0.02, bot + 0.2)]), strand, g.rx * 0.025, 0.85)
        c.restore()
        # vài sợi tóc lòa xòa vắt ngang khe
        for k, dx in enumerate((-0.9, 0.7)):
            seam(c, [(ex + erx * dx, ey - ery * 5.2), (ex + erx * (dx + 0.35), ey - ery * 0.5),
                     (ex + erx * (dx - 0.2 + 0.5 * k), ey + ery * 3.0)], p.hair_color, g.rx * 0.022, 0.9)
        return


def draw_hair_back_view(c: skia.Canvas, g: Geo) -> None:
    """Tóc nhìn từ sau lưng (che kín gáy)."""
    p = g.p
    hs = p.hair_style
    hc = p.hair_color
    sy = g.shoulder_y
    if hs == "none_entity":
        return
    if hs == "bald":
        c.save()
        c.clipPath(face_path(g), doAntiAlias=True)
        c.drawPath(oval(*g.P(-0.1, -0.7), 0.25 * g.rx, 0.1 * g.ry), paint("#ffffff", 0.35))
        if p.age == "old":
            band = smooth(g.pts([(-1.05, -0.2), (-0.5, 0.18), (0, 0.26), (0.5, 0.18), (1.05, -0.2), (1.0, 0.42),
                                 (0.5, 0.56), (0, 0.6), (-0.5, 0.56), (-1.0, 0.42)]), tension=0.4)
            c.drawPath(band, paint(mix(hc, p.skin, 0.15)))
            for u in (-0.6, -0.2, 0.2, 0.6):
                seam(c, g.pts([(u, 0.3 + 0.1 * (1 - abs(u))), (u * 1.05, 0.5)]), mul(hc, 0.8), g.rx * 0.02, 0.6,
                     curve=False)
        c.restore()
        return
    if hs in ("long_straight", "long_over_face"):
        bot = (sy + 0.2 * g.Hf) if hs == "long_straight" else (g.waist_y - 0.02 * g.Hf)
        pts = g.pts([(-1.12, -0.5), (-0.8, -1.05), (0, -1.16), (0.8, -1.05), (1.12, -0.5)])
        pts += [(g.U(1.25), g.V(0.7)), (g.U(1.38), sy), (g.U(1.4), bot - 20), (g.U(0.7), bot), (g.U(0), bot + 6),
                (g.U(-0.7), bot), (g.U(-1.4), bot - 20), (g.U(-1.38), sy), (g.U(-1.25), g.V(0.7))]
        pth = smooth(pts, tension=0.4)
        hair_fill(c, pth, g, arc=[(-0.5, -0.88), (0, -1.0), (0.5, -0.88)])
        dk = p.colors.get("strand") or (lit(hc, 0.15) if luma(hc) < 0.2 else mul(hc, 0.7))
        c.save()
        c.clipPath(pth, doAntiAlias=True)
        for u in (-0.9, -0.45, 0.0, 0.45, 0.9):
            seam(c, [(g.U(u), g.V(-0.2)), (g.U(u * 1.1), g.V(1.2)), (g.U(u * 1.15), bot - 10)], dk, g.rx * 0.025, 0.7)
        c.restore()
        return
    if hs == "cap_hidden":
        cap = p.cap_color or p.colors.get("cap") or "#24365a"
        nape = smooth(g.pts([(-0.98, -0.3), (0.98, -0.3), (0.95, 0.4), (0.5, 0.66), (0, 0.7), (-0.5, 0.66),
                             (-0.95, 0.4)]), tension=0.45)
        hair_fill(c, nape, g)
        dome = smooth(g.pts([(-1.1, -0.25), (-1.08, -0.7), (-0.75, -1.08), (0, -1.2), (0.75, -1.08), (1.08, -0.7),
                             (1.1, -0.25), (0, -0.2)]), tension=0.42)
        flat(c, dome, cap, d=0.18 * g.rx)
        hole = rrect(g.U(-0.28), g.V(-0.48), g.U(0.28), g.V(-0.26), g.rx * 0.1)  # lỗ chỉnh size + quai
        c.drawPath(hole, paint(mul(hc, 0.9)))
        c.drawPath(rrect(g.U(-0.32), g.V(-0.32), g.U(0.32), g.V(-0.24), g.rx * 0.03), paint(mul(cap, 0.7)))
        c.drawPath(circle(*g.P(0, -1.18), g.rx * 0.07), paint(mul(cap, 0.75)))
        if "low_ponytail" in p.accessories:   # đuôi tóc thấp luồn dưới mũ
            tail = smooth([g.P(-0.22, 0.45), g.P(0.22, 0.45), g.P(0.24, 1.0), (g.U(0.14), sy + 0.1 * g.Hf),
                           (g.U(0), sy + 0.13 * g.Hf), (g.U(-0.14), sy + 0.1 * g.Hf), g.P(-0.24, 1.0)], tension=0.45)
            hair_fill(c, tail, g, strokes=[[(0.0, 0.7), (0.02, 1.5)]])
            c.drawPath(rrect(g.U(-0.22), g.V(0.48), g.U(0.22), g.V(0.62), g.rx * 0.05), paint(p.hair_tie or "#2a2a2e"))
        return
    if hs in ("curly_short", "afro_curly"):
        big = hs == "afro_curly"
        hl = p.hair_highlight or lit(hc, 0.3)
        k = 1.12 if big else 1.0
        blobs = [(math.cos(a) * 0.95 * k, -0.15 + math.sin(a) * 0.95 * k) for a in
                 [math.radians(x) for x in range(160, 390, 22)]]
        blobs += [(-0.5, -0.2), (0, -0.25), (0.5, -0.2), (-0.35, 0.3), (0.35, 0.3), (0, 0.45), (-0.3, -0.7), (0.3, -0.7)]
        r = 0.36 if big else 0.3
        for u, v in blobs:
            c.drawPath(circle(*g.P(u, v), g.rx * r), paint(hc))
        for u, v in blobs:
            x, y = g.P(u, v)
            arcp = skia.Path()
            arcp.addArc(skia.Rect.MakeLTRB(x - g.rx * r * 0.6, y - g.rx * r * 0.6, x + g.rx * r * 0.6, y + g.rx * r * 0.6),
                        200, 100)
            c.drawPath(arcp, pen(hl, g.rx * 0.035, 0.8))
        return
    # ngắn / spiky / bun / bob / ponytail / buzz / grey
    nape_v = {"bob_bangs": 1.12, "buzz": 0.45, "spiky": 0.5}.get(hs, 0.62)
    w = 1.24 if hs == "bob_bangs" else 1.06
    pts = [(-w, -0.4), (-w * 0.8, -1.04), (0, -1.15), (w * 0.8, -1.04), (w, -0.4), (w * 0.98, nape_v * 0.7),
           (w * 0.7 if hs != "bob_bangs" else w * 0.95, nape_v), (0, nape_v + 0.05), (-(w * 0.7 if hs != "bob_bangs" else w * 0.95), nape_v),
           (-w * 0.98, nape_v * 0.7)]
    if hs == "spiky":
        pth = poly(g.pts([(-1.04, 0.3), (-1.04, -0.6), (-0.95, -1.15), (-0.62, -1.02), (-0.45, -1.42), (-0.2, -1.1),
                          (0.05, -1.48), (0.28, -1.1), (0.55, -1.4), (0.7, -1.02), (1.02, -1.15), (1.04, -0.6),
                          (1.04, 0.3), (0.6, 0.48), (0, 0.5), (-0.6, 0.48)]))
    else:
        pth = smooth(g.pts(pts), tension=0.42 if hs != "bob_bangs" else 0.3)
    col = mix(hc, p.skin, 0.18) if hs == "buzz" else hc
    hair_fill(c, pth, g, col=col, arc=[(-0.5, -0.88), (0, -1.0), (0.5, -0.88)],
              strokes=[[(-0.4, -0.55), (0.0, -0.62), (0.45, -0.52)]] if hs == "slick_side_part" else None)
    if hs == "bun":
        bun = circle(*g.P(0, -0.95), 0.4 * g.rx)
        hair_fill(c, bun, g, arc=[(-0.2, -1.15), (0, -1.22), (0.2, -1.15)])
    if hs == "long_ponytail":
        if p.pigtails:
            tie = p.hair_tie or "#e05a7a"
            for s in (-1, 1):
                tuft = smooth(g.pts([(s * 0.85, -0.4), (s * 1.3, -0.45), (s * 1.48, -0.05), (s * 1.42, 0.45),
                                     (s * 1.25, 0.2), (s * 1.0, -0.1)]), tension=0.45)
                hair_fill(c, tuft, g)
                c.drawPath(circle(*g.P(s * 0.98, -0.42), g.rx * 0.1), paint(tie))
        else:
            tail = smooth([g.P(-0.2, -0.2), g.P(0.2, -0.2), g.P(0.26, 0.6), (g.U(0.2), sy + 0.1 * g.Hf),
                           (g.U(0), sy + 0.14 * g.Hf), (g.U(-0.2), sy + 0.1 * g.Hf), g.P(-0.26, 0.6)], tension=0.45)
            hair_fill(c, tail, g, strokes=[[(0.0, 0.3), (0.02, 1.4)]])
            c.drawPath(rrect(g.U(-0.24), g.V(-0.22), g.U(0.24), g.V(-0.06), g.rx * 0.05), paint(p.hair_tie or "#c8352e"))


def draw_head_props(c: skia.Canvas, g: Geo, back: bool = False) -> None:
    """Phụ kiện trên đầu vẽ sau tóc: băng đô vải (headband), tăm ngậm khoé miệng (toothpick)."""
    p = g.p
    acc = p.accessories
    if "headband" in acc:
        hb = p.colors.get("headband", "#d24a5a")
        band = smooth(g.pts([(-1.1, -0.4), (-0.85, -0.92), (0, -1.12), (0.85, -0.92), (1.1, -0.4), (0.98, -0.32),
                             (0.75, -0.78), (0, -0.96), (-0.75, -0.78), (-0.98, -0.32)]), tension=0.4)
        flat(c, band, hb, d=0.05 * g.rx, rim=0.2, hl=0.15, bottom=0)
    if "toothpick" in acc and not back:
        x0, y0 = g.mx + g.mw * 0.55, g.my + g.ry * 0.01
        c.drawPath(poly([(x0, y0), (x0 + g.rx * 0.38, y0 - g.ry * 0.09)], close=False), pen("#e3cf9a", g.rx * 0.035))


def draw_police_cap(c: skia.Canvas, g: Geo, back: bool = False) -> None:
    cc = g.p.colors.get("cap") or g.p.colors.get("uniform") or "#3d5a3a"
    band = g.p.colors.get("cap_band") or "#a8312a"
    crown = smooth(g.pts([(-1.25, -0.95), (-0.9, -1.38), (0, -1.48), (0.9, -1.38), (1.25, -0.95), (0.98, -0.72),
                          (-0.98, -0.72)]), tension=0.35)
    flat(c, crown, cc, d=0.2 * g.rx)
    c.drawPath(rrect(g.U(-1.0), g.V(-0.8), g.U(1.0), g.V(-0.55), g.rx * 0.06), paint(band))
    if not back:
        visor = smooth(g.pts([(-0.98, -0.58), (0, -0.62), (0.98, -0.58), (0.7, -0.38), (0, -0.33), (-0.7, -0.38)]),
                       tension=0.45)
        flat(c, visor, "#16161a", d=0.05 * g.rx, rim=0.2, hl=0.3)
        c.drawPath(circle(*g.P(0, -0.98), g.rx * 0.1), paint("#d9b44a"))   # nút tròn chung (không quốc huy)


# ======================================================================= thân
def torso_path(g: Geo, bottom: float | None = None, flare: float = 1.0) -> skia.Path:
    cx, sw, Hf = g.cx, g.sw, g.Hf
    hw = g.hw * flare
    sy = g.shoulder_y
    bottom = g.waist_y + 0.035 * Hf if bottom is None else bottom
    belly = 1.08 if g.p.build == "heavy" else 1.0
    waist = (0.9 if g.fem and flare <= 1.0 else 1.0)
    R = [(cx, sy - 0.012 * Hf), (cx + sw * 0.55, sy - 0.008 * Hf), (cx + sw * 0.9, sy + 0.01 * Hf),
         (cx + sw * 0.99, sy + 0.05 * Hf), (cx + max(sw * 0.94, hw * belly), sy + 0.12 * Hf),
         (cx + max(hw * waist * belly, sw * 0.8 if not g.fem else hw * waist), (sy + bottom) / 2 + 0.05 * Hf),
         (cx + hw * 1.02, bottom - 0.012 * Hf), (cx + hw * 0.92, bottom), (cx, bottom + 1)]
    L = [(2 * cx - x, y) for x, y in reversed(R[1:-1])]
    return smooth(R + L, tension=0.32)


def _sleeve_puff(g: Geo, s: str, length: float, wide: float = 1.48) -> skia.Path:
    (x1, y1), (x2, y2) = g.shoulder(s), g.elbow(s)
    t = length
    xm, ym = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
    w = g.arm_w
    return capsule(x1, y1 - w * 0.12, xm, ym, w * wide, w * (wide - 0.12))


def _flower(c: skia.Canvas, x: float, y: float, r: float, col: str, center: str) -> None:
    for i in range(5):
        a = i * math.tau / 5 - math.pi / 2
        c.drawPath(circle(x + math.cos(a) * r * 0.6, y + math.sin(a) * r * 0.6, r * 0.45), paint(col))
    c.drawPath(circle(x, y, r * 0.3), paint(center))


def _scatter(seed: int, n: int, bounds: skia.Rect) -> list[tuple[float, float]]:
    rng = np.random.default_rng(seed)
    out = []
    cols = max(1, int(math.sqrt(n * bounds.width() / max(1, bounds.height()))))
    rows = max(1, n // cols)
    for i in range(rows):
        for j in range(cols):
            x = bounds.left() + (j + 0.5 + rng.uniform(-0.3, 0.3)) * bounds.width() / cols
            y = bounds.top() + (i + 0.5 + rng.uniform(-0.3, 0.3)) * bounds.height() / rows
            out.append((x, y))
    return out


def draw_pattern(c: skia.Canvas, g: Geo, path: skia.Path, sp: Spec, seed: int = 1) -> None:
    """Hoa nhí 5 cánh / chấm bi / sọc ngang trên vải."""
    p = g.p
    o = p.outfit_type
    cl = p.colors
    c.save()
    c.clipPath(path, doAntiAlias=True)
    b = path.getBounds()
    if o == "floral_blouse":
        fc = cl.get("flowers", "#f1e6c8")
        for x, y in _scatter(seed, 14, b):
            _flower(c, x, y, g.Hf * 0.011, fc, mix(fc, "#d9a43a", 0.6))
    elif o in ("pajamas", "dress") and "dots" in cl:
        for x, y in _scatter(seed + 5, 16, b):
            c.drawPath(circle(x, y, g.Hf * 0.005), paint(cl["dots"], 0.95))
    elif o == "dot_blouse":
        dc = cl.get("dots", "#f4f1ea")
        step = g.Hf * 0.024
        y0 = b.top() + step * 0.4
        row = 0
        while y0 < b.bottom() + step:
            x0 = b.left() + (step * 0.5 if row % 2 else 0)
            while x0 < b.right() + step:
                c.drawPath(circle(x0, y0, g.Hf * 0.0042), paint(dc, 0.95))
                x0 += step
            y0 += step * 0.8
            row += 1
    elif o == "tee" and "stripe" in cl:
        y = g.shoulder_y + 0.06 * g.Hf
        while y < b.bottom():
            c.drawRect(skia.Rect.MakeLTRB(b.left() - 5, y, b.right() + 5, y + 0.016 * g.Hf), paint(cl["stripe"]))
            y += 0.05 * g.Hf
    c.restore()


def _collar_flaps(c: skia.Canvas, g: Geo, col: str, kind: str = "pointed") -> None:
    cx, nw = g.cx, g.neck_w
    vtop = g.shoulder_y - 0.014 * g.Hf
    for s in (-1, 1):
        if kind == "peter_pan":
            flap = smooth([(cx + s * nw * 0.2, vtop + 0.012 * g.Hf), (cx + s * nw * 1.2, vtop - 2), (cx + s * nw * 2.3, vtop + 0.008 * g.Hf),
                           (cx + s * nw * 2.1, vtop + 0.034 * g.Hf), (cx + s * nw * 0.9, vtop + 0.044 * g.Hf)], tension=0.5)
        else:
            flap = poly([(cx + s * nw * 0.15, vtop + 0.036 * g.Hf), (cx + s * nw * 1.05, vtop - 3),
                         (cx + s * nw * 2.25, vtop + 0.006 * g.Hf), (cx + s * nw * 1.6, vtop + 0.05 * g.Hf)])
        flat(c, flap, col, d=2.5, rim=0.15, hl=0, bottom=0)
        c.drawPath(flap, pen(mul(col, 0.62), 1.3, 0.55))


def draw_torso(c: skia.Canvas, g: Geo, back: bool = False) -> None:
    p = g.p
    sp = outfit_spec(p)
    cx, Hf, sy = g.cx, g.Hf, g.shoulder_y
    top = sp.top
    o = p.outfit_type
    tunic_bottom = g.waist_y + (0.035 + sp.tunic) * Hf
    if o == "long_sheet_shirt":
        tunic_bottom = g.hip_y + 0.09 * Hf
    path = torso_path(g, tunic_bottom, flare=1.25 if o == "long_sheet_shirt" else (1.05 if sp.tunic else 1.0))
    # vạt cổ: khoét cổ để thấy cổ
    vtop = sy - 0.014 * Hf
    nw = g.neck_w
    if not back:
        if sp.neck in ("v", "wrap"):
            path = diff(path, poly([(cx - nw * 1.3, vtop - 8), (cx + nw * 1.3, vtop - 8), (cx, sy + 0.06 * Hf)]))
        elif sp.neck in ("shirt", "polo", "pointed", "peter_pan"):
            path = diff(path, poly([(cx - nw * 1.05, vtop - 8), (cx + nw * 1.05, vtop - 8), (cx, sy + 0.032 * Hf)]))
        elif sp.neck in ("crew", "round", "hood"):
            path = diff(path, oval(cx, vtop - 2, nw * 1.15, 0.016 * Hf))
    flat(c, path, top, d=g.sw * 0.2, rim=0.3, edge=0.35)
    if p.outfit_type == "silhouette":
        coll = smooth([(cx - nw * 2.2, sy - 2), (cx, sy + 0.03 * Hf), (cx + nw * 2.2, sy - 2)], close=False)
        c.drawPath(coll, pen(sp.collar or "#d9b44a", 0.008 * Hf))
        return
    if not back or o == "dot_blouse":
        draw_pattern(c, g, path, sp, seed=3)
    fold = mul(top, 0.62)
    # nếp áo nhẹ
    seam(c, [(cx - g.sw * 0.55, sy + 0.15 * Hf), (cx - g.sw * 0.4, sy + 0.18 * Hf)], fold, 1.6, 0.45)
    seam(c, [(cx + g.sw * 0.6, sy + 0.16 * Hf), (cx + g.sw * 0.45, g.waist_y)], fold, 1.6, 0.4)
    if back:
        _torso_back_details(c, g, sp, path)
        return
    # ------------------------------------------------ chi tiết theo loại áo
    if o == "polo_uniform":
        col = sp.collar or "#f2ead8"
        c.drawPath(rrect(cx - nw * 0.42, vtop + 0.02 * Hf, cx + nw * 0.42, sy + 0.085 * Hf, 3), paint(col))
        for i in range(2):
            c.drawPath(circle(cx, sy + 0.045 * Hf + i * 0.024 * Hf, 0.0045 * Hf), paint(mul(col, 0.7)))
        _collar_flaps(c, g, col)
        c.drawPath(smooth([(cx - g.hw * 1.0, tunic_bottom - 0.012 * Hf), (cx, tunic_bottom - 0.009 * Hf),
                           (cx + g.hw * 1.0, tunic_bottom - 0.012 * Hf)], close=False), pen(mul(top, 0.7), 2, 0.6))
    elif o == "hoodie":
        hood = diff(smooth([(cx - nw * 3.0, sy - 0.004 * Hf), (cx, sy - 0.026 * Hf), (cx + nw * 3.0, sy - 0.004 * Hf),
                            (cx + nw * 2.6, sy + 0.04 * Hf), (cx, sy + 0.06 * Hf), (cx - nw * 2.6, sy + 0.04 * Hf)],
                           tension=0.5), oval(cx, vtop + 0.006 * Hf, nw * 1.15, 0.022 * Hf))
        flat(c, hood, mul(top, 0.9), d=4, rim=0.2, hl=0)
        strings = p.colors.get("strings", "#f1f1ef")
        for s in (-1, 1):
            x = cx + s * nw * 0.75
            seam(c, [(x, sy + 0.035 * Hf), (x + s * 2, sy + 0.1 * Hf)], strings, 0.006 * Hf)
            c.drawPath(rrect(x + s * 2 - 0.004 * Hf, sy + 0.1 * Hf, x + s * 2 + 0.004 * Hf, sy + 0.112 * Hf, 1.5),
                       paint(mul(strings, 0.8)))
        pk = smooth([(cx - g.sw * 0.55, tunic_bottom - 0.03 * Hf), (cx - g.sw * 0.42, sy + 0.15 * Hf),
                     (cx + g.sw * 0.42, sy + 0.15 * Hf), (cx + g.sw * 0.55, tunic_bottom - 0.03 * Hf)], tension=0.15)
        c.drawPath(pk, paint(mul(top, 0.92)))
        c.drawPath(pk, pen(mul(top, 0.62), 1.6, 0.7))
        c.drawRect(skia.Rect.MakeLTRB(cx - g.hw * 1.05, tunic_bottom - 0.026 * Hf, cx + g.hw * 1.05, tunic_bottom + 2),
                   paint(sp.cuff or mul(top, 0.85), 0.9))
    elif o == "utility_jacket":
        jc = sp.sleeve_col or "#6b7244"
        seam(c, [(cx - nw * 1.15, vtop + 2), (cx, vtop + 0.016 * Hf), (cx + nw * 1.15, vtop + 2)], mul(top, 0.7), 0.006 * Hf)
        for s in (-1, 1):
            panel = smooth([(cx + s * nw * 1.4, vtop - 0.004 * Hf), (cx + s * g.sw * 0.6, sy - 0.006 * Hf),
                            (cx + s * g.sw * 1.0, sy + 0.04 * Hf), (cx + s * g.hw * 1.12, tunic_bottom + 2),
                            (cx + s * g.hw * 0.35, tunic_bottom + 4), (cx + s * nw * 1.3, sy + 0.09 * Hf)], tension=0.18)
            flat(c, panel, jc, d=g.sw * 0.12, rim=0.25, edge=0.4)
            lap = poly([(cx + s * nw * 1.4, vtop - 0.004 * Hf), (cx + s * nw * 2.7, vtop + 0.004 * Hf),
                        (cx + s * nw * 2.0, sy + 0.08 * Hf), (cx + s * nw * 1.3, sy + 0.09 * Hf)])
            c.drawPath(lap, paint(mul(jc, 0.88)))
            px = cx + s * g.sw * 0.55
            pocket = rrect(px - 0.026 * Hf, sy + 0.05 * Hf, px + 0.026 * Hf, sy + 0.1 * Hf, 3)
            c.drawPath(pocket, paint(mul(jc, 0.93)))
            seam(c, [(px - 0.022 * Hf, sy + 0.054 * Hf), (px + 0.022 * Hf, sy + 0.054 * Hf),
                     (px + 0.022 * Hf, sy + 0.096 * Hf), (px - 0.022 * Hf, sy + 0.096 * Hf), (px - 0.022 * Hf, sy + 0.054 * Hf)],
                 lit(jc, 0.35), 1.2, 0.8, curve=False, dash=(4, 3))
            flap = rrect(px - 0.029 * Hf, sy + 0.044 * Hf, px + 0.029 * Hf, sy + 0.062 * Hf, 3)
            c.drawPath(flap, paint(mul(jc, 0.8)))
            c.drawPath(circle(px, sy + 0.056 * Hf, 0.004 * Hf), paint(mul(jc, 0.55)))
            seam(c, [(cx + s * nw * 1.3, sy + 0.09 * Hf), (cx + s * g.hw * 0.36, tunic_bottom)], lit(jc, 0.3), 1.2, 0.7,
                 curve=False, dash=(4, 3))
    elif o in ("tee", "tank"):
        if o == "tee":
            seam(c, [(cx - nw * 1.15, vtop + 2), (cx, vtop + 0.017 * Hf), (cx + nw * 1.15, vtop + 2)], mul(top, 0.72),
                 0.006 * Hf)
    elif o in ("shirt_button", "school_uniform_m", "school_uniform_f", "police_uniform", "security_uniform",
               "hi_vis_vest", "khaki_uniform"):
        coll = p.colors.get("collar", top) if o == "shirt_button" else top
        if o != "hi_vis_vest":
            seam(c, [(cx, sy + 0.03 * Hf), (cx, tunic_bottom - 4)], mul(top, 0.7), 1.4, 0.6, curve=False)
            for i in range(4):
                by = sy + 0.05 * Hf + i * 0.045 * Hf
                if by < tunic_bottom - 0.01 * Hf:
                    c.drawPath(circle(cx + 3, by, 0.0042 * Hf), paint(mul(top, 0.72)))
        if o in ("shirt_button", "school_uniform_m", "police_uniform", "security_uniform", "khaki_uniform"):
            for s in ((-1,) if o in ("shirt_button", "school_uniform_m", "security_uniform") else (-1, 1)):
                px = cx + s * g.sw * 0.5
                pk = rrect(px - 0.024 * Hf, sy + 0.05 * Hf, px + 0.024 * Hf, sy + 0.1 * Hf, 2)
                c.drawPath(pk, pen(mul(top, 0.66), 1.4, 0.8))
                if o in ("police_uniform", "khaki_uniform"):
                    c.drawPath(rrect(px - 0.026 * Hf, sy + 0.044 * Hf, px + 0.026 * Hf, sy + 0.062 * Hf, 3),
                               paint(mul(top, 0.86)))
        if o == "school_uniform_f":
            _collar_flaps(c, g, coll, sp.neck if sp.neck in ("peter_pan", "pointed") else "pointed")
        elif o != "hi_vis_vest":
            _collar_flaps(c, g, coll)
        if o in ("police_uniform", "security_uniform", "khaki_uniform"):
            ep = p.colors.get("epaulette") or mul(top, 0.7)
            for s in (-1, 1):
                x = cx + s * g.sw * 0.68
                c.drawPath(rrect(x - 0.03 * Hf, sy - 0.004 * Hf, x + 0.03 * Hf, sy + 0.012 * Hf, 3), paint(ep))
        if o == "hi_vis_vest":
            _collar_flaps(c, g, top)
            _draw_vest(c, g, tunic_bottom)
    elif o == "office_blouse":
        for s in (-1, 1):
            seam(c, [(cx + s * nw * 1.3, vtop), (cx + s * nw * 0.6, sy + 0.03 * Hf), (cx, sy + 0.06 * Hf)], mul(top, 0.7),
                 1.6, 0.7)
        seam(c, [(cx - g.sw * 0.3, sy + 0.08 * Hf), (cx - g.sw * 0.1, sy + 0.12 * Hf)], mul(top, 0.75), 1.4, 0.5)
    elif o == "floral_blouse":
        seam(c, [(cx - nw * 1.2, vtop + 1), (cx, vtop + 0.017 * Hf), (cx + nw * 1.2, vtop + 1)], mul(top, 0.6), 0.008 * Hf)
    elif o == "ao_ba_ba":
        seam(c, [(cx - nw * 1.15, vtop + 2), (cx, vtop + 0.016 * Hf), (cx + nw * 1.15, vtop + 2)], mul(top, 0.7),
             0.005 * Hf)
        seam(c, [(cx, vtop + 0.016 * Hf), (cx, tunic_bottom - 4)], mul(top, 0.66), 1.4, 0.7, curve=False)
        for i in range(5):
            by = sy + 0.03 * Hf + i * 0.04 * Hf
            if by < tunic_bottom - 0.01 * Hf:
                c.drawPath(circle(cx, by, 0.004 * Hf), paint(lit(top, 0.4)))
        for s in (-1, 1):  # xẻ tà hai bên
            x = cx + s * g.hw * 1.0
            seam(c, [(x, tunic_bottom - 0.04 * Hf), (x + s * 2, tunic_bottom)], mul(top, 0.6), 1.6, 0.8, curve=False)
    elif o in ("ao_dai", "red_traditional_dress"):
        trim = sp.collar or "#b08a4a"
        c.drawPath(rrect(cx - nw * 1.25, vtop - 0.012 * Hf, cx + nw * 1.25, vtop + 0.012 * Hf, 3), paint(mul(top, 0.92)))
        seam(c, [(cx - nw * 1.25, vtop + 0.012 * Hf), (cx + nw * 1.25, vtop + 0.012 * Hf)], trim, 1.6, 0.9, curve=False)
        seam(c, [(cx + nw * 1.2, vtop + 0.01 * Hf), (cx + g.sw * 0.55, sy + 0.04 * Hf), (cx + g.sw * 0.85, sy + 0.08 * Hf)],
             trim, 1.8, 0.9)
        seam(c, [(cx - g.sw * 0.4, sy + 0.12 * Hf), (cx - g.sw * 0.3, tunic_bottom)], mul(top, 0.7), 1.4, 0.5)
    elif o == "nurse_scrubs":
        seam(c, [(cx - nw * 1.3, vtop - 4), (cx, sy + 0.06 * Hf), (cx + nw * 1.3, vtop - 4)], mul(top, 0.7), 0.006 * Hf,
             curve=False)
        px = cx - g.sw * 0.5
        c.drawPath(rrect(px - 0.024 * Hf, sy + 0.06 * Hf, px + 0.024 * Hf, sy + 0.1 * Hf, 2), pen(mul(top, 0.66), 1.4, 0.8))
    elif o in ("monk_robe", "ritual_robe"):
        dk = sp.collar or mul(top, 0.8)
        seam(c, [(cx - nw * 1.4, vtop), (cx + g.sw * 0.1, sy + 0.08 * Hf), (cx + g.sw * 0.6, sy + 0.16 * Hf)], dk, 0.012 * Hf)
        seam(c, [(cx + nw * 1.4, vtop), (cx + nw * 0.2, sy + 0.05 * Hf)], dk, 0.012 * Hf)
        for dx in (-0.6, -0.2, 0.35):
            seam(c, [(cx + g.sw * dx, sy + 0.1 * Hf), (cx + g.sw * dx * 1.2, tunic_bottom)], mul(top, 0.7), 1.4, 0.45)
    elif o in ("pajamas", "dress"):
        seam(c, [(cx - nw * 1.2, vtop + 1), (cx, vtop + 0.016 * Hf), (cx + nw * 1.2, vtop + 1)], lit(top, 0.5), 0.008 * Hf)
        c.drawRect(skia.Rect.MakeLTRB(cx - g.hw * 0.95, g.waist_y - 0.012 * Hf, cx + g.hw * 0.95, g.waist_y + 0.004 * Hf),
                   paint(mul(top, 0.86)))
    elif o == "long_sheet_shirt":
        for dx in (-0.7, -0.25, 0.2, 0.65):
            seam(c, [(cx + g.sw * dx, sy + 0.05 * Hf), (cx + g.sw * dx * 1.25, tunic_bottom - 4)], mul(top, 0.72), 1.6, 0.5)
    elif o == "blazer_tie":
        _draw_blazer(c, g, sp, tunic_bottom)
    elif o == "butcher_apron":
        if sp.neck == "crew":
            seam(c, [(cx - nw * 1.15, vtop + 2), (cx, vtop + 0.017 * Hf), (cx + nw * 1.15, vtop + 2)], mul(top, 0.72),
                 0.006 * Hf)
        _draw_apron(c, g)
    elif o == "zip_jacket":
        _draw_zip_jacket(c, g, sp, tunic_bottom)
    elif o == "dot_blouse":
        seam(c, [(cx - nw * 1.15, vtop + 2), (cx, vtop + 0.016 * Hf), (cx + nw * 1.15, vtop + 2)], mul(top, 0.7),
             0.006 * Hf)
        seam(c, [(cx, vtop + 0.016 * Hf), (cx, sy + 0.09 * Hf)], mul(top, 0.66), 1.4, 0.7, curve=False)
        for i in range(3):
            c.drawPath(circle(cx, sy + 0.03 * Hf + i * 0.028 * Hf, 0.0038 * Hf), paint(lit(top, 0.45)))
    _torso_accessories(c, g, sp)


# ----------------------------------------------------------------- batch 2: áo vest / tạp dề / áo khoác khoá kéo
def _draw_blazer(c: skia.Canvas, g: Geo, sp: Spec, bottom: float) -> None:
    """Vest tối mở cúc giữa: sơ mi trắng + cà vạt mảnh lộ ở chữ V, ve áo, đường may xám nhạt."""
    p = g.p
    Hf, cx, sy, nw = g.Hf, g.cx, g.shoulder_y, g.neck_w
    vtop = sy - 0.014 * Hf
    bz = sp.sleeve_col or "#33363d"
    seam_c = mix(bz, "#c9ccd2", 0.55)
    _collar_flaps(c, g, sp.top)
    tie = p.colors.get("tie", "#1c1d22")
    knot = poly([(cx - nw * 0.36, vtop + 0.01 * Hf), (cx + nw * 0.36, vtop + 0.01 * Hf), (cx + nw * 0.22, sy + 0.03 * Hf),
                 (cx - nw * 0.22, sy + 0.03 * Hf)])
    blade = poly([(cx - nw * 0.2, sy + 0.028 * Hf), (cx + nw * 0.2, sy + 0.028 * Hf), (cx + nw * 0.36, sy + 0.2 * Hf),
                  (cx, sy + 0.225 * Hf), (cx - nw * 0.36, sy + 0.2 * Hf)])
    c.drawPath(blade, paint(tie))
    c.drawPath(knot, paint(lit(tie, 0.12)))
    btn_y = sy + 0.165 * Hf
    for s in (-1, 1):
        panel = poly([(cx + s * nw * 1.25, vtop - 0.006 * Hf), (cx + s * g.sw * 0.62, sy - 0.008 * Hf),
                       (cx + s * g.sw * 0.95, sy + 0.012 * Hf), (cx + s * g.sw * 1.0, sy + 0.05 * Hf),
                       (cx + s * g.hw * 1.12, bottom - 0.01 * Hf), (cx + s * g.hw * 1.06, bottom + 2),
                       (cx + s * nw * 0.15, bottom + 4), (cx - s * nw * 0.15, btn_y + 0.01 * Hf)])
        panel = smooth([(x, y) for x, y in _poly_pts(panel)], tension=0.12)
        flat(c, panel, bz, d=g.sw * 0.12, rim=0.25, edge=0.4)
        lapel = poly([(cx + s * nw * 1.25, vtop - 0.004 * Hf), (cx + s * nw * 2.5, vtop + 0.008 * Hf),
                       (cx + s * nw * 2.35, sy + 0.035 * Hf), (cx + s * nw * 2.0, sy + 0.05 * Hf),
                       (cx + s * nw * 0.05, btn_y)])
        c.drawPath(lapel, paint(mul(bz, 0.84)))
        c.drawPath(lapel, pen(seam_c, 1.3, 0.6))
        # túi hông (nắp) + đường may sườn
        px = cx + s * g.sw * 0.55
        seam(c, [(px - 0.026 * Hf, bottom - 0.05 * Hf), (px + 0.026 * Hf, bottom - 0.052 * Hf)], seam_c, 1.4, 0.7, curve=False)
        seam(c, [(cx + s * g.sw * 0.78, sy + 0.07 * Hf), (cx + s * g.hw * 0.95, bottom - 0.01 * Hf)], seam_c, 1.1, 0.45)
    seam(c, [(cx + g.sw * 0.4, sy + 0.075 * Hf), (cx + g.sw * 0.66, sy + 0.072 * Hf)], seam_c, 1.4, 0.7, curve=False)
    c.drawPath(circle(cx + nw * 0.05, btn_y + 0.012 * Hf, 0.005 * Hf), paint(mul(bz, 0.6)))


def _poly_pts(path: skia.Path) -> list[tuple[float, float]]:
    return [(pt.x(), pt.y()) for pt in path.getPoints(path.countPoints())]


def _draw_apron(c: skia.Canvas, g: Geo) -> None:
    """Tạp dề bếp/hàng thịt dài quá gối: yếm ngực, dây cổ, dây eo, sọc mảnh, vệt bẩn mờ (không máu)."""
    p = g.p
    Hf, cx, sy, nw = g.Hf, g.cx, g.shoulder_y, g.neck_w
    vtop = sy - 0.014 * Hf
    ac = p.colors.get("apron", "#2a2a30")
    bib_top = sy + 0.04 * Hf
    bw = nw * 2.3
    bot = g.knee_y + 0.045 * Hf
    for s in (-1, 1):
        seam(c, [(cx + s * bw * 0.85, bib_top + 4), (cx + s * nw * 1.3, sy + 0.01 * Hf), (cx + s * nw * 1.05, vtop)],
             mul(ac, 0.9), 0.009 * Hf)
    pth = smooth([(cx - bw, bib_top), (cx + bw, bib_top), (cx + bw * 1.02, sy + 0.09 * Hf),
                  (cx + g.hw * 1.1, g.waist_y - 0.01 * Hf), (cx + g.hw * 1.18, (g.waist_y + bot) / 2),
                  (cx + g.hw * 1.28, bot), (cx, bot + 3), (cx - g.hw * 1.28, bot), (cx - g.hw * 1.18, (g.waist_y + bot) / 2),
                  (cx - g.hw * 1.1, g.waist_y - 0.01 * Hf), (cx - bw * 1.02, sy + 0.09 * Hf)], tension=0.12)
    flat(c, pth, ac, d=g.hw * 0.22, rim=0.28, edge=0.4)
    c.save()
    c.clipPath(pth, doAntiAlias=True)
    b = pth.getBounds()
    if "apron_stripe" in p.colors:
        x = b.left() + 0.012 * Hf
        while x < b.right():
            c.drawRect(skia.Rect.MakeLTRB(x, b.top(), x + 0.0028 * Hf, b.bottom()), paint(p.colors["apron_stripe"], 0.75))
            x += 0.022 * Hf
    rng = np.random.default_rng(11)
    stain = p.colors.get("stain", "#7a6650")
    for _ in range(5):
        x, y = rng.uniform(cx - g.hw * 0.9, cx + g.hw * 0.9), rng.uniform(g.waist_y + 0.03 * Hf, bot - 0.03 * Hf)
        r = rng.uniform(0.008, 0.02) * Hf
        c.drawPath(oval(x, y, r * 1.3, r), paint(stain, 0.28))
    c.restore()
    # dây eo + túi ngực
    seam(c, [(cx - g.hw * 1.12, g.waist_y - 0.006 * Hf), (cx + g.hw * 1.12, g.waist_y - 0.006 * Hf)], mul(ac, 0.75),
         0.008 * Hf, 0.9, curve=False)
    tie = smooth([(cx + g.hw * 1.1, g.waist_y - 0.006 * Hf), (cx + g.hw * 1.3, g.waist_y + 0.02 * Hf),
                  (cx + g.hw * 1.22, g.waist_y + 0.07 * Hf)], close=False)
    c.drawPath(tie, pen(mul(ac, 0.8), 0.008 * Hf))
    pk = rrect(cx - nw * 1.0, sy + 0.07 * Hf, cx + nw * 1.0, sy + 0.12 * Hf, 3)
    c.drawPath(pk, pen(lit(ac, 0.25), 1.3, 0.7))


def _draw_zip_jacket(c: skia.Canvas, g: Geo, sp: Spec, bottom: float) -> None:
    """Áo khoác khoá kéo mở (track / rider / gió): 2 vạt, cổ đứng, khoá kéo, sọc dọc hoặc dải phản quang tuỳ chọn."""
    p = g.p
    Hf, cx, sy, nw = g.Hf, g.cx, g.shoulder_y, g.neck_w
    vtop = sy - 0.014 * Hf
    top = sp.top
    jc = sp.sleeve_col or "#22304a"
    seam(c, [(cx - nw * 1.15, vtop + 2), (cx, vtop + 0.017 * Hf), (cx + nw * 1.15, vtop + 2)], mul(top, 0.72), 0.006 * Hf)
    stripe = p.colors.get("stripe")
    band = p.colors.get("band")
    for s in (-1, 1):
        panel = smooth([(cx + s * nw * 1.4, vtop - 0.004 * Hf), (cx + s * g.sw * 0.6, sy - 0.006 * Hf),
                        (cx + s * g.sw * 1.0, sy + 0.04 * Hf), (cx + s * g.hw * 1.12, bottom + 2),
                        (cx + s * g.hw * 0.38, bottom + 4), (cx + s * nw * 1.25, sy + 0.09 * Hf)], tension=0.18)
        flat(c, panel, jc, d=g.sw * 0.12, rim=0.25, edge=0.4)
        c.save()
        c.clipPath(panel, doAntiAlias=True)
        if stripe:
            x = cx + s * g.sw * 0.44
            c.drawPath(poly([(x - 0.01 * Hf, sy - 0.02 * Hf), (x + 0.01 * Hf, sy - 0.02 * Hf), (x + 0.012 * Hf + s * 0.01 * Hf, bottom + 6),
                             (x - 0.008 * Hf + s * 0.01 * Hf, bottom + 6)]), paint(stripe))
        if band:
            c.drawRect(skia.Rect.MakeLTRB(cx - g.sw * 1.3, sy + 0.15 * Hf, cx + g.sw * 1.3, sy + 0.166 * Hf), paint(band))
        c.drawRect(skia.Rect.MakeLTRB(cx - g.sw * 1.3, bottom - 0.016 * Hf, cx + g.sw * 1.3, bottom + 8), paint(mul(jc, 0.84)))
        c.restore()
        seam(c, [(cx + s * nw * 1.38, vtop + 0.004 * Hf), (cx + s * nw * 1.26, sy + 0.09 * Hf), (cx + s * g.hw * 0.4, bottom)],
             lit(jc, 0.4), 0.004 * Hf, 0.85, dash=(3, 2))
        coll = poly([(cx + s * nw * 1.0, vtop - 0.014 * Hf), (cx + s * nw * 2.3, vtop - 0.006 * Hf),
                     (cx + s * nw * 2.2, vtop + 0.012 * Hf), (cx + s * nw * 1.35, vtop + 0.012 * Hf)])
        c.drawPath(coll, paint(mul(jc, 0.88)))
    c.drawPath(rrect(cx + nw * 1.0, sy + 0.1 * Hf, cx + nw * 1.0 + 0.008 * Hf, sy + 0.118 * Hf, 1.5), paint("#c9ccd1"))


def _draw_vest(c: skia.Canvas, g: Geo, bottom: float, back: bool = False) -> None:
    p = g.p
    Hf, cx, sy = g.Hf, g.cx, g.shoulder_y
    vc = p.colors.get("vest", "#f07a22")
    refl = "#dfe3e6"
    vest = torso_path(g, bottom + 0.005 * Hf, 1.04)
    vest = diff(vest, rrect(cx - g.sw * 1.3, sy - 0.05 * Hf, cx + g.sw * 1.3, sy + 0.004 * Hf, 0))
    for s in (-1, 1):  # khoét nách
        vest = diff(vest, oval(cx + s * g.sw * 1.02, sy + 0.05 * Hf, g.sw * 0.18, 0.07 * Hf))
    if not back:
        vest = diff(vest, poly([(cx - g.neck_w * 1.6, sy - 0.02 * Hf), (cx + g.neck_w * 1.6, sy - 0.02 * Hf),
                                (cx, sy + 0.11 * Hf)]))
    flat(c, vest, vc, d=g.sw * 0.15, rim=0.25, edge=0.4)
    c.save()
    c.clipPath(vest, doAntiAlias=True)
    for y in (sy + 0.15 * Hf, sy + 0.2 * Hf):
        c.drawRect(skia.Rect.MakeLTRB(cx - g.sw * 1.3, y, cx + g.sw * 1.3, y + 0.014 * Hf), paint(refl))
    c.restore()
    num = p.vest_number
    if num:
        f = font((0.06 if back else 0.036) * Hf, "extrabold")
        tw = f.measureText(num)
        y = sy + (0.135 if back else 0.142) * Hf
        x = cx - tw / 2 if back else cx + g.sw * 0.36 - tw / 2
        c.drawString(num, x, y, f, paint(p.colors.get("vest_number", "#1b1b1d")))


def _torso_back_details(c: skia.Canvas, g: Geo, sp: Spec, path: skia.Path) -> None:
    p = g.p
    o = p.outfit_type
    Hf, cx, sy = g.Hf, g.cx, g.shoulder_y
    top = sp.top
    if o == "polo_uniform":
        c.drawPath(rrect(cx - g.neck_w * 2.0, sy - 0.02 * Hf, cx + g.neck_w * 2.0, sy + 0.008 * Hf, 4), paint(sp.collar or "#f2ead8"))
    elif o == "hoodie":   # mũ trùm thả sau lưng
        hood = smooth([(cx - g.neck_w * 3.0, sy - 0.01 * Hf), (cx + g.neck_w * 3.0, sy - 0.01 * Hf),
                       (cx + g.neck_w * 2.5, sy + 0.09 * Hf), (cx, sy + 0.12 * Hf), (cx - g.neck_w * 2.5, sy + 0.09 * Hf)],
                      tension=0.5)
        flat(c, hood, mul(top, 0.92), d=5, rim=0.25)
        seam(c, [(cx - g.neck_w * 1.6, sy + 0.02 * Hf), (cx, sy + 0.08 * Hf), (cx + g.neck_w * 1.6, sy + 0.02 * Hf)],
             mul(top, 0.65), 1.6, 0.7)
    elif o == "utility_jacket":
        seam(c, [(cx, sy), (cx, g.waist_y + 0.03 * Hf)], lit(sp.sleeve_col or top, 0.3), 1.2, 0.7, curve=False, dash=(4, 3))
        jc = sp.sleeve_col or top
        flat(c, path, jc, d=g.sw * 0.2, rim=0.3, edge=0.35)
        seam(c, [(cx - g.sw * 0.8, sy + 0.08 * Hf), (cx + g.sw * 0.8, sy + 0.08 * Hf)], lit(jc, 0.3), 1.2, 0.7, curve=False,
             dash=(4, 3))
    elif o in ("shirt_button", "school_uniform_m", "school_uniform_f", "police_uniform", "security_uniform",
               "khaki_uniform"):
        coll = p.colors.get("collar", top) if o == "shirt_button" else top
        c.drawPath(rrect(cx - g.neck_w * 1.8, sy - 0.02 * Hf, cx + g.neck_w * 1.8, sy + 0.006 * Hf, 4), paint(mul(coll, 0.95)))
        seam(c, [(cx - g.sw * 0.85, sy + 0.05 * Hf), (cx, sy + 0.065 * Hf), (cx + g.sw * 0.85, sy + 0.05 * Hf)],
             mul(top, 0.7), 1.3, 0.5)
        if o == "khaki_uniform":
            ep = p.colors.get("epaulette") or mul(top, 0.7)
            for s in (-1, 1):
                x = cx + s * g.sw * 0.68
                c.drawPath(rrect(x - 0.03 * Hf, sy - 0.004 * Hf, x + 0.03 * Hf, sy + 0.012 * Hf, 3), paint(ep))
    elif o in ("blazer_tie", "zip_jacket"):
        jc = sp.sleeve_col or top
        flat(c, path, jc, d=g.sw * 0.2, rim=0.3, edge=0.35)
        lt = mix(jc, "#c9ccd2", 0.5) if o == "blazer_tie" else lit(jc, 0.35)
        c.drawPath(rrect(cx - g.neck_w * 2.0, sy - 0.022 * Hf, cx + g.neck_w * 2.0, sy + 0.01 * Hf, 5), paint(mul(jc, 0.86)))
        if o == "blazer_tie":
            seam(c, [(cx, sy + 0.12 * Hf), (cx, g.waist_y + 0.06 * Hf)], lt, 1.4, 0.7, curve=False)  # xẻ tà sau
            for s in (-1, 1):
                seam(c, [(cx + s * g.sw * 0.45, sy + 0.03 * Hf), (cx + s * g.hw * 0.7, g.waist_y + 0.05 * Hf)], lt, 1.1, 0.45)
        else:
            stripe, band = p.colors.get("stripe"), p.colors.get("band")
            c.save()
            c.clipPath(path, doAntiAlias=True)
            if stripe:
                for s in (-1, 1):
                    x = cx + s * g.sw * 0.5
                    c.drawRect(skia.Rect.MakeLTRB(x - 0.009 * Hf, sy, x + 0.009 * Hf, g.waist_y + 0.06 * Hf), paint(stripe))
            if band:
                c.drawRect(skia.Rect.MakeLTRB(cx - g.sw * 1.3, sy + 0.15 * Hf, cx + g.sw * 1.3, sy + 0.166 * Hf), paint(band))
            bottom = g.waist_y + (0.035 + sp.tunic) * Hf
            c.drawRect(skia.Rect.MakeLTRB(cx - g.sw * 1.3, bottom - 0.016 * Hf, cx + g.sw * 1.3, bottom + 8), paint(mul(jc, 0.84)))
            c.restore()
            seam(c, [(cx - g.sw * 0.8, sy + 0.07 * Hf), (cx + g.sw * 0.8, sy + 0.07 * Hf)], lt, 1.2, 0.6, curve=False,
                 dash=(3, 2))
    elif o == "butcher_apron":   # dây tạp dề bắt chéo sau lưng + nơ eo
        ac = p.colors.get("apron", "#2a2a30")
        for s in (-1, 1):
            seam(c, [(cx + s * g.neck_w * 1.1, sy - 0.012 * Hf), (cx - s * g.sw * 0.3, sy + 0.12 * Hf),
                     (cx - s * g.hw * 1.05, g.waist_y - 0.006 * Hf)], mul(ac, 0.9), 0.009 * Hf)
            side = smooth([(cx + s * g.hw * 1.12, g.waist_y - 0.01 * Hf), (cx + s * g.hw * 0.78, g.waist_y),
                           (cx + s * g.hw * 0.82, g.waist_y + 0.05 * Hf), (cx + s * g.hw * 1.15, g.waist_y + 0.05 * Hf)],
                          tension=0.3)
            c.drawPath(side, paint(ac))
        seam(c, [(cx - g.hw * 1.12, g.waist_y - 0.006 * Hf), (cx + g.hw * 1.12, g.waist_y - 0.006 * Hf)], mul(ac, 0.75),
             0.008 * Hf, 0.9, curve=False)
        for s in (-1, 1):
            loop = smooth([(cx, g.waist_y - 0.006 * Hf), (cx + s * 0.03 * Hf, g.waist_y - 0.022 * Hf),
                           (cx + s * 0.034 * Hf, g.waist_y + 0.006 * Hf)], tension=0.5)
            c.drawPath(loop, paint(mul(ac, 0.85)))
            seam(c, [(cx, g.waist_y), (cx + s * 0.012 * Hf, g.waist_y + 0.06 * Hf)], mul(ac, 0.85), 0.007 * Hf)
    elif o == "hi_vis_vest":
        _draw_vest(c, g, g.waist_y + 0.035 * Hf, back=True)
    elif o in ("ao_dai", "red_traditional_dress"):
        c.drawPath(rrect(cx - g.neck_w * 1.25, sy - 0.03 * Hf, cx + g.neck_w * 1.25, sy - 0.006 * Hf, 3), paint(mul(top, 0.92)))
    if "scarf" in p.colors:
        _draw_scarf(c, g, back=True)


def _draw_scarf(c: skia.Canvas, g: Geo, back: bool = False) -> None:
    sc = g.p.colors["scarf"]
    Hf, cx, sy = g.Hf, g.cx, g.shoulder_y
    s = 1 if not back else -1
    pth = smooth([(cx - g.sw * 0.9 * s, sy - 0.004 * Hf), (cx - g.neck_w * 0.6 * s, sy - 0.012 * Hf),
                  (cx + g.sw * 0.25 * s, sy + 0.03 * Hf), (cx + g.sw * 0.55 * s, sy + 0.17 * Hf),
                  (cx + g.sw * 0.3 * s, sy + 0.19 * Hf), (cx + g.sw * 0.05 * s, sy + 0.06 * Hf),
                  (cx - g.sw * 0.8 * s, sy + 0.03 * Hf)], tension=0.4)
    flat(c, pth, sc, d=4, rim=0.2)
    c.save()
    c.clipPath(pth, doAntiAlias=True)
    b = pth.getBounds()
    step = 0.012 * Hf
    x = b.left()
    i = 0
    while x < b.right():
        c.drawRect(skia.Rect.MakeLTRB(x, b.top(), x + step * 0.45, b.bottom()), paint("#e9e6df", 0.55))
        x += step
        i += 1
    y = b.top()
    while y < b.bottom():
        c.drawRect(skia.Rect.MakeLTRB(b.left(), y, b.right(), y + step * 0.45), paint("#e9e6df", 0.45))
        y += step
    c.restore()


def _badge_rect(g: Geo) -> tuple[float, float, float, float]:
    """Bảng tên: ngực trái nhân vật (= bên phải màn hình khi nhìn chính diện)."""
    x = g.cx + g.sw * 0.5
    y = g.shoulder_y + 0.062 * g.Hf
    w, h = 0.085 * g.Hf, 0.026 * g.Hf
    return (x - w / 2, y - h / 2, x + w / 2, y + h / 2)


def _torso_accessories(c: skia.Canvas, g: Geo, sp: Spec) -> None:
    p = g.p
    acc = p.accessories
    Hf, cx, sy, nw = g.Hf, g.cx, g.shoulder_y, g.neck_w
    vtop = sy - 0.014 * Hf
    if "scarf" in p.colors:
        _draw_scarf(c, g)
    if "towel_on_neck" in acc:
        for s in (-1, 1):
            t = smooth([(cx + s * nw * 1.0, vtop - 4), (cx + s * nw * 2.4, vtop), (cx + s * nw * 2.2, sy + 0.12 * Hf),
                        (cx + s * nw * 1.2, sy + 0.12 * Hf), (cx + s * nw * 1.0, sy + 0.02 * Hf)], tension=0.35)
            flat(c, t, "#eeeeea", d=3, rim=0.2)
            seam(c, [(cx + s * nw * 1.3, sy + 0.1 * Hf), (cx + s * nw * 2.1, sy + 0.1 * Hf)], "#7aa0c8", 2, 0.8, curve=False)
    if any(a.startswith("backpack") for a in acc):
        bc = _backpack_color(p)
        for s in (-1, 1):
            strap = capsule(cx + s * g.sw * 0.55, sy - 0.006 * Hf, cx + s * g.sw * 0.62, sy + 0.18 * Hf, 0.022 * Hf, 0.02 * Hf)
            flat(c, strap, mul(bc, 0.85), d=2, rim=0.2)
            c.drawPath(rrect(cx + s * g.sw * 0.62 - 0.014 * Hf, sy + 0.1 * Hf, cx + s * g.sw * 0.62 + 0.014 * Hf,
                             sy + 0.115 * Hf, 2), paint("#2a2a2e"))
    if "handbag" in acc:
        strap = poly([(cx - g.sw * 0.75, sy - 0.004 * Hf), (cx + g.sw * 0.9, g.waist_y)], close=False)
        c.drawPath(strap, pen("#5a3a2a", 0.012 * Hf))
    if "lanyard_card" in acc:
        lc = p.colors.get("lanyard", "#2e6db0")
        seam(c, [(cx - nw * 1.2, vtop), (cx - nw * 0.6, sy + 0.09 * Hf), (cx, sy + 0.12 * Hf)], lc, 0.008 * Hf)
        seam(c, [(cx + nw * 1.2, vtop), (cx + nw * 0.6, sy + 0.09 * Hf), (cx, sy + 0.12 * Hf)], lc, 0.008 * Hf)
        card = rrect(cx - 0.022 * Hf, sy + 0.12 * Hf, cx + 0.022 * Hf, sy + 0.175 * Hf, 3)
        c.drawPath(card, paint("#ffffff"))
        c.drawPath(rrect(cx - 0.016 * Hf, sy + 0.128 * Hf, cx + 0.016 * Hf, sy + 0.15 * Hf, 2), paint("#b9c6d8"))
        c.drawPath(card, pen("#9aa0a8", 1.2, 0.6))
    if "stethoscope" in acc:
        seam(c, [(cx - nw * 1.6, vtop), (cx - nw * 1.8, sy + 0.07 * Hf), (cx - nw * 0.8, sy + 0.12 * Hf)], "#4a4f57", 0.008 * Hf)
        seam(c, [(cx + nw * 1.6, vtop), (cx + nw * 1.8, sy + 0.07 * Hf), (cx + nw * 1.4, sy + 0.1 * Hf)], "#4a4f57", 0.008 * Hf)
        c.drawPath(circle(cx - nw * 0.7, sy + 0.125 * Hf, 0.012 * Hf), paint("#b9bec6"))
    if "name_badge" in acc:
        l, t, r, b = _badge_rect(g)
        c.drawPath(rrect(l + 1.5, t + 2, r + 1.5, b + 2, 2.5), paint("#000000", 0.2))
        c.drawPath(rrect(l, t, r, b, 2.5), paint(p.colors.get("badge", "#ffffff")))
        ink = "#8a1f22"
        seam(c, [(l + (r - l) * 0.15, t + (b - t) * 0.4), (l + (r - l) * 0.7, t + (b - t) * 0.4)], ink, (b - t) * 0.18,
             0.9, curve=False)
        seam(c, [(l + (r - l) * 0.15, t + (b - t) * 0.72), (l + (r - l) * 0.5, t + (b - t) * 0.72)], "#8a8a8a",
             (b - t) * 0.12, 0.8, curve=False)
    if "name_tag_school" in acc:
        l, t, r, b = _badge_rect(g)
        c.drawPath(rrect(l + 6, t, r - 6, b - 4, 2), paint("#ffffff"))
        c.drawPath(rrect(l + 6, t, r - 6, b - 4, 2), pen("#2f5d8a", 1.2))
        seam(c, [(l + 10, (t + b) / 2 - 2), (r - 14, (t + b) / 2 - 2)], "#2f5d8a", 1.8, 0.9, curve=False)
    if "store_emblem_leaf" in acc:   # huy hiệu gốc: chiếc lá trong vòng tròn
        x, y, r = cx - g.sw * 0.5, sy + 0.062 * Hf, 0.017 * Hf
        c.drawPath(circle(x, y, r), pen("#ffffff", r * 0.18))
        leaf = smooth([(x - r * 0.55, y + r * 0.5), (x - r * 0.4, y - r * 0.3), (x + r * 0.5, y - r * 0.55),
                       (x + r * 0.3, y + r * 0.3)], tension=0.6)
        c.drawPath(leaf, paint("#ffffff"))
        seam(c, [(x - r * 0.5, y + r * 0.5), (x + r * 0.3, y - r * 0.3)], p.colors.get("shirt", "#1f6f5c"), r * 0.1,
             curve=False)
    if "chest_pin" in acc:
        x, y = cx - g.sw * 0.48, sy + 0.06 * Hf
        c.drawPath(circle(x, y, 0.009 * Hf), paint(p.colors.get("pin", "#d9b44a")))
        c.drawPath(circle(x + 1, y - 1, 0.004 * Hf), paint("#fff3c4", 0.8))
    if "embroidery" in p.colors:     # ký hiệu sóng gốc
        x, y = cx - g.sw * 0.48, sy + 0.065 * Hf
        ec = p.colors["embroidery"]
        for i in range(2):
            seam(c, _wave(x - 0.014 * Hf, x + 0.014 * Hf, y + i * 0.008 * Hf, 0.0025 * Hf, 2), ec, 1.6)
    if "gold_chain_square_pendant" in acc:
        gold, dg = "#e0b43c", "#8a6514"
        ch = smooth([(cx - nw * 1.05, vtop), (cx - nw * 0.7, sy + 0.035 * Hf), (cx, sy + 0.05 * Hf),
                     (cx + nw * 0.7, sy + 0.035 * Hf), (cx + nw * 1.05, vtop)], close=False)
        c.drawPath(ch, pen(dg, 0.0055 * Hf))
        dash = pen(gold, 0.0038 * Hf)
        dash.setPathEffect(skia.DashPathEffect.Make([5, 3], 0))
        c.drawPath(ch, dash)
        pd = rrect(cx - 0.009 * Hf, sy + 0.05 * Hf, cx + 0.009 * Hf, sy + 0.072 * Hf, 2)
        c.drawPath(pd, paint(gold))
        c.drawPath(pd, pen(dg, 1.4))
    if "ball_chain_necklace" in acc:
        ch = smooth([(cx - nw * 1.05, vtop), (cx - nw * 0.7, sy + 0.04 * Hf), (cx, sy + 0.06 * Hf),
                     (cx + nw * 0.7, sy + 0.04 * Hf), (cx + nw * 1.05, vtop)], close=False)
        dots = pen("#d4d7db", 0.005 * Hf)
        dots.setPathEffect(skia.DashPathEffect.Make([0.1, 0.008 * Hf], 0))
        c.drawPath(ch, dots)
        c.drawPath(rrect(cx - 0.006 * Hf, sy + 0.06 * Hf, cx + 0.006 * Hf, sy + 0.08 * Hf, 2), paint("#c9ccd1"))
    if any(a.startswith("prayer_beads") for a in acc) and (p.outfit_type in ("monk_robe", "ritual_robe")
                                                          or "red_tassel" in " ".join(acc)):
        ch = smooth([(cx - nw * 1.2, vtop), (cx - nw * 1.4, sy + 0.08 * Hf), (cx, sy + 0.14 * Hf),
                     (cx + nw * 1.4, sy + 0.08 * Hf), (cx + nw * 1.2, vtop)], close=False)
        beads = pen("#6a3a22", 0.012 * Hf)
        beads.setPathEffect(skia.DashPathEffect.Make([0.1, 0.016 * Hf], 0))
        c.drawPath(ch, beads)
        if "red_tassel" in " ".join(acc):
            c.drawPath(poly([(cx, sy + 0.14 * Hf), (cx - 0.008 * Hf, sy + 0.18 * Hf), (cx + 0.008 * Hf, sy + 0.18 * Hf)]),
                       paint("#c0272d"))
    if "pearl_necklace" in acc:
        ch = smooth([(cx - nw * 1.15, vtop), (cx - nw * 0.8, sy + 0.03 * Hf), (cx, sy + 0.045 * Hf),
                     (cx + nw * 0.8, sy + 0.03 * Hf), (cx + nw * 1.15, vtop)], close=False)
        pearls = pen("#f4efe4", 0.0075 * Hf)
        pearls.setPathEffect(skia.DashPathEffect.Make([0.1, 0.011 * Hf], 0))
        c.drawPath(ch, pen("#b9b2a4", 0.009 * Hf, 0.5))
        c.drawPath(ch, pearls)
    if "glasses_on_cord" in acc:   # kính lão treo dây trước ngực
        gy = sy + 0.11 * Hf
        r = 0.014 * Hf
        for s in (-1, 1):
            seam(c, [(cx + s * nw * 1.1, vtop), (cx + s * nw * 1.3, sy + 0.06 * Hf), (cx + s * r * 2.0, gy - r * 0.3)],
                 "#d8b85a", 0.0028 * Hf, 0.9)
            ring = circle(cx + s * r * 1.15, gy, r)
            c.drawPath(ring, paint("#d9ecf5", 0.35))
            c.drawPath(ring, pen("#c9a243", 0.0028 * Hf))
        seam(c, [(cx - r * 0.2, gy - r * 0.2), (cx + r * 0.2, gy - r * 0.2)], "#c9a243", 0.0028 * Hf, curve=False)
    if "police_star_badge" in acc:   # huy hiệu gốc: sao 4 cánh vàng trong khiên tròn, không chữ
        x, y, r = cx - g.sw * 0.5, sy + 0.04 * Hf, 0.017 * Hf
        c.drawPath(circle(x, y, r), paint("#d9b44a"))
        c.drawPath(circle(x, y, r), pen(mul("#d9b44a", 0.6), r * 0.12))
        star = poly([(x, y - r * 0.75), (x + r * 0.2, y - r * 0.2), (x + r * 0.75, y), (x + r * 0.2, y + r * 0.2),
                     (x, y + r * 0.75), (x - r * 0.2, y + r * 0.2), (x - r * 0.75, y), (x - r * 0.2, y - r * 0.2)])
        c.drawPath(star, paint("#fff3c4"))
    if "name_bar" in acc:   # thẻ tên kim loại: thanh tối viền vàng, không chữ
        x, y = cx + g.sw * 0.5, sy + 0.04 * Hf
        bar = rrect(x - 0.03 * Hf, y - 0.007 * Hf, x + 0.03 * Hf, y + 0.007 * Hf, 2)
        c.drawPath(bar, paint("#1f2328"))
        c.drawPath(bar, pen("#d9b44a", 1.4))
        seam(c, [(x - 0.022 * Hf, y), (x + 0.012 * Hf, y)], "#e8e4da", 0.0035 * Hf, 0.8, curve=False)
    if "basket" in acc:   # giỏ tre đeo khuỷu tay trái màn hình (đi chợ)
        bx, by = cx - g.sw * 1.25, g.waist_y + 0.02 * Hf
        bk = smooth([(bx - 0.06 * Hf, by), (bx + 0.06 * Hf, by), (bx + 0.05 * Hf, by + 0.07 * Hf),
                     (bx - 0.05 * Hf, by + 0.07 * Hf)], tension=0.15)
        handle = smooth([(bx - 0.05 * Hf, by), (bx, by - 0.07 * Hf), (bx + 0.05 * Hf, by)], close=False)
        c.drawPath(handle, pen("#9a6a36", 0.007 * Hf))
        flat(c, bk, "#c08a4a", d=4, rim=0.25)
        c.save()
        c.clipPath(bk, doAntiAlias=True)
        for i in range(6):
            yy = by + i * 0.014 * Hf
            c.drawPath(poly([(bx - 0.07 * Hf, yy), (bx + 0.07 * Hf, yy)], close=False), pen("#8a5e2c", 1.4, 0.7))
        c.restore()
    if p.outfit_type == "police_uniform" or sp.belt:
        pass  # thắt lưng vẽ ở pelvis


def _backpack_color(p: CharParams) -> str:
    for a in p.accessories:
        if a.startswith("backpack"):
            name = a.split("_", 1)[1] if "_" in a else ""
            return p.colors.get("backpack") or {"grey": "#6d7178", "blue": "#2f5d8a", "pink": "#e58fb0",
                                                "black": "#2a2a2e"}.get(name, "#5d6470")
    return "#5d6470"


def draw_backpack_behind(c: skia.Canvas, g: Geo) -> None:
    """Front view: phần balo lộ ra hai bên thân (vẽ sau thân)."""
    if not any(a.startswith("backpack") for a in g.p.accessories):
        return
    bc = _backpack_color(g.p)
    Hf, cx, sy = g.Hf, g.cx, g.shoulder_y
    pack = rrect(cx - g.sw * 1.12, sy + 0.01 * Hf, cx + g.sw * 1.12, sy + 0.21 * Hf, 0.04 * Hf)
    flat(c, pack, mul(bc, 0.85), d=8, rim=0.3)


def draw_backpack_back(c: skia.Canvas, g: Geo) -> None:
    if not any(a.startswith("backpack") for a in g.p.accessories):
        return
    bc = _backpack_color(g.p)
    Hf, cx, sy = g.Hf, g.cx, g.shoulder_y
    pack = rrect(cx - g.sw * 0.82, sy + 0.015 * Hf, cx + g.sw * 0.82, sy + 0.23 * Hf, 0.045 * Hf)
    flat(c, pack, bc, d=g.sw * 0.18, rim=0.3, edge=0.4)
    pk = rrect(cx - g.sw * 0.55, sy + 0.12 * Hf, cx + g.sw * 0.55, sy + 0.21 * Hf, 0.02 * Hf)
    flat(c, pk, mul(bc, 0.9), d=4, rim=0.2, edge=0.4)
    seam(c, [(cx - g.sw * 0.6, sy + 0.05 * Hf), (cx + g.sw * 0.6, sy + 0.05 * Hf)], "#2a2a2e", 1.8, 0.8, curve=False)
    c.drawPath(rrect(cx - 0.02 * Hf, sy + 0.005 * Hf, cx + 0.02 * Hf, sy + 0.022 * Hf, 3), paint(mul(bc, 0.7)))


# ======================================================================= hông / chân
def draw_pelvis(c: skia.Canvas, g: Geo, back: bool = False) -> None:
    p = g.p
    sp = outfit_spec(p)
    Hf, cx, hw = g.Hf, g.cx, g.hw
    top, bot = g.waist_y - 0.012 * Hf, g.hip_y + g.thigh_w * 0.55
    lc = sp.lower_col
    knee_hem = g.knee_y + sp.hem * Hf
    if sp.lower in ("skirt", "dress"):
        flare = 1.55 if sp.lower == "dress" else 1.35
        hem = knee_hem
        sk = smooth([(cx - hw * 0.98, top), (cx - hw * 1.2, (top + hem) / 2), (cx - hw * flare, hem), (cx, hem + 4),
                     (cx + hw * flare, hem), (cx + hw * 1.2, (top + hem) / 2), (cx + hw * 0.98, top)], tension=0.25)
        flat(c, sk, lc, d=hw * 0.35, rim=0.3, edge=0.35)
        if not back:
            draw_pattern(c, g, sk, sp, seed=7)
        for dx in (-0.75, -0.25, 0.25, 0.75):   # nếp xếp ly
            seam(c, [(cx + hw * dx * 0.85, top + 0.03 * Hf), (cx + hw * dx * flare * 0.92, hem - 3)], mul(lc, 0.6), 1.6,
                 0.6, curve=False)
        if sp.lower == "skirt":
            c.drawPath(rrect(cx - hw * 1.0, top - 2, cx + hw * 1.0, top + 0.014 * Hf, 3), paint(mul(lc, 0.85)))
        return
    if sp.lower == "pencil":
        hem = g.knee_y + 0.005 * Hf
        sk = smooth([(cx - hw * 0.98, top), (cx - hw * 1.08, (top + hem) / 2), (cx - hw * 0.98, hem), (cx, hem + 2),
                     (cx + hw * 0.98, hem), (cx + hw * 1.08, (top + hem) / 2), (cx + hw * 0.98, top)], tension=0.3)
        flat(c, sk, lc, d=hw * 0.3, rim=0.3, edge=0.35)
        seam(c, [(cx, hem - 0.04 * Hf), (cx, hem)], mul(lc, 0.55), 1.6, 0.8, curve=False)
        return
    if sp.lower in ("robe", "sarong"):
        hem = g.ankle_y - 0.01 * Hf
        fl = 1.45 if sp.lower == "robe" else 1.22
        sk = smooth([(cx - hw * 1.08, top - 0.02 * Hf), (cx - hw * 1.2, (top + hem) / 2), (cx - hw * fl, hem),
                     (cx, hem + 4), (cx + hw * fl, hem), (cx + hw * 1.2, (top + hem) / 2), (cx + hw * 1.08, top - 0.02 * Hf)],
                    tension=0.25)
        flat(c, sk, lc, d=hw * 0.4, rim=0.3, edge=0.35)
        for dx in (-0.8, -0.2, 0.5):
            seam(c, [(cx + hw * dx, top + 0.05 * Hf), (cx + hw * dx * 1.3, hem - 4)], mul(lc, 0.65), 1.6, 0.5)
        if not back:
            seam(c, [(cx + hw * 0.2, top), (cx + hw * 0.5, hem)], mul(lc, 0.6), 2, 0.6, curve=False)
        return
    if sp.lower == "sheet":
        hem = g.hip_y + 0.1 * Hf
        sk = smooth([(cx - hw * 1.3, top - 0.02 * Hf), (cx - hw * 1.55, hem), (cx - hw * 0.7, hem + 0.012 * Hf), (cx, hem),
                     (cx + hw * 0.8, hem + 0.015 * Hf), (cx + hw * 1.55, hem), (cx + hw * 1.3, top - 0.02 * Hf)], tension=0.3)
        flat(c, sk, sp.top, d=hw * 0.4, rim=0.3, edge=0.3)
        for dx in (-0.9, -0.3, 0.3, 0.9):
            seam(c, [(cx + hw * dx, top), (cx + hw * dx * 1.2, hem)], mul(sp.top, 0.72), 1.6, 0.5)
        return
    if sp.lower == "aodai":
        # quần lụa + tà áo dài trước (tà sau ở chân... đơn giản: 1 tà trước)
        pants = smooth([(cx - hw, top), (cx - hw * 1.06, bot), (cx + hw * 1.06, bot), (cx + hw, top)], tension=0.2)
        flat(c, pants, lc, d=hw * 0.3, rim=0.25)
        hem = g.knee_y + 0.13 * Hf
        flap = smooth([(cx - hw * 0.95, top - 0.03 * Hf), (cx - hw * 0.98, (top + hem) / 2), (cx - hw * 0.9, hem),
                       (cx, hem + 3), (cx + hw * 0.9, hem), (cx + hw * 0.98, (top + hem) / 2), (cx + hw * 0.95, top - 0.03 * Hf)],
                      tension=0.25)
        flat(c, flap, sp.top, d=hw * 0.3, rim=0.3, edge=0.35)
        seam(c, [(cx - hw * 0.3, top + 0.04 * Hf), (cx - hw * 0.35, hem - 4)], mul(sp.top, 0.68), 1.6, 0.6, curve=False)
        if g.p.wet:
            for x in (-0.6, 0.1, 0.7):
                c.drawPath(_drop(cx + hw * x, hem + 0.02 * Hf, 0.014 * Hf), paint(DRIP, 0.9))
        return
    # quần dài / quần đùi
    pants = smooth([(cx - hw, top), (cx - hw * 1.08, (top + bot) / 2), (cx - hw * 1.04, bot), (cx - 4, bot + 4),
                    (cx + 4, bot + 4), (cx + hw * 1.04, bot), (cx + hw * 1.08, (top + bot) / 2), (cx + hw, top)], tension=0.3)
    flat(c, pants, lc, d=hw * 0.3, rim=0.3, edge=0.3)
    if not back:
        seam(c, [(cx + 3, top + 0.02 * Hf), (cx + 2, bot - 4)], mul(lc, 0.6), 1.5, 0.6, curve=False)
    if sp.belt:
        c.drawPath(rrect(cx - hw * 1.04, top - 2, cx + hw * 1.04, top + 0.014 * Hf, 3), paint(sp.belt))
        if not back:
            c.drawPath(rrect(cx - 0.012 * Hf, top - 1, cx + 0.012 * Hf, top + 0.012 * Hf, 2), pen("#c9b36a", 1.8))
        acc = p.accessories
        if "walkie_talkie" in acc:
            x = cx + hw * (0.75 if not back else -0.75)
            c.drawPath(rrect(x - 0.012 * Hf, top, x + 0.012 * Hf, top + 0.05 * Hf, 3), paint("#222226"))
            c.drawPath(poly([(x + 0.006 * Hf, top), (x + 0.006 * Hf, top - 0.025 * Hf)], close=False), pen("#222226", 3))
        if "flashlight" in acc:
            x = cx - hw * (0.8 if not back else -0.8)
            c.drawPath(rrect(x - 0.008 * Hf, top + 0.005 * Hf, x + 0.008 * Hf, top + 0.06 * Hf, 3), paint("#3a3a40"))
            c.drawPath(rrect(x - 0.011 * Hf, top + 0.045 * Hf, x + 0.011 * Hf, top + 0.065 * Hf, 3), paint("#52525a"))
    elif sp.lower == "pants" and p.outfit_type not in ("silhouette",):
        c.drawPath(rrect(cx - hw * 1.02, top - 1, cx + hw * 1.02, top + 0.01 * Hf, 3), paint(mul(lc, 0.8)))


def draw_leg_up(c: skia.Canvas, g: Geo, s: str) -> None:
    sp = outfit_spec(g.p)
    x, y = g.hipj(s)
    kx, ky = g.knee(s)
    bare = sp.lower in ("skirt", "dress", "pencil", "shorts")
    col = g.p.skin if bare else sp.lower_col
    if sp.shoe == "stick":
        col = sp.shoe_col
    pth = capsule(x, y - g.thigh_w * 0.25, kx, ky, g.thigh_w, g.thigh_w * 0.82)
    flat(c, pth, col, d=g.thigh_w * 0.18, rim=0.3, edge=0.0 if bare else 0.3)
    if sp.lower == "shorts":
        sh = inter(pth, rrect(x - 80, y - 50, x + 80, y + (ky - y) * 0.55, 0))
        flat(c, union(sh, rrect(x - g.thigh_w * 0.62, y + (ky - y) * 0.3, x + g.thigh_w * 0.62, y + (ky - y) * 0.55, 6)),
             sp.lower_col, d=g.thigh_w * 0.18, edge=0.3)
    if sp.lower == "aodai":
        pass


def draw_leg_low(c: skia.Canvas, g: Geo, s: str) -> None:
    p = g.p
    sp = outfit_spec(p)
    x, ky = g.knee(s)
    ay = g.ankle_y
    FY = g.FY
    w = g.shin_w
    bare = sp.lower in ("skirt", "dress", "pencil", "shorts")
    col = p.skin if bare else sp.lower_col
    sg = g.side(s)
    if sp.shoe == "stick":
        shin = capsule(x, ky, x + sg * 2, FY - 6, w, w * 0.7)
        flat(c, shin, sp.shoe_col, d=w * 0.2, rim=0.3)
        foot = poly([(x - w * 0.4, FY - 10), (x + sg * w * 1.6, FY - 1), (x - w * 0.3, FY)])
        c.drawPath(foot, paint(mul(sp.shoe_col, 0.85)))
        return
    shin = capsule(x, ky, x, ay, w, w * 0.82)
    flat(c, shin, col, d=w * 0.18, rim=0.3, edge=0.0 if bare else 0.3)
    if sp.sock and bare:
        sock = inter(shin, rrect(x - w, ay - 0.06 * g.Hf, x + w, ay + 20, 0))
        c.drawPath(sock, paint(sp.sock))
    if not bare and sp.lower not in ("robe", "sarong") and sp.shoe != "boots":
        cuff = rrect(x - w * 0.56, ay - 0.022 * g.Hf, x + w * 0.56, ay + 2, 5)
        c.drawPath(cuff, paint(mul(col, 0.9)))
    if sp.shoe == "boots":   # ủng cao su: ống cao tới giữa bắp chân, mũi tròn
        sc = sp.shoe_col
        toe = x + sg * w * 0.35
        top_y = ky + (ay - ky) * 0.38
        leg = rrect(x - w * 0.72, top_y, x + w * 0.72, FY - 0.02 * g.Hf, w * 0.25)
        foot = smooth([(x - w * 0.72, ay - 0.03 * g.Hf), (x + w * 0.72, ay - 0.03 * g.Hf), (toe + w * 0.9, FY - 0.02 * g.Hf),
                       (toe + w * 0.85, FY), (toe - w * 0.85, FY), (toe - w * 0.85, FY - 0.02 * g.Hf)], tension=0.35)
        flat(c, union(leg, foot), sc, d=w * 0.2, rim=0.25, hl=0.25, bottom=0)
        c.drawPath(rrect(x - w * 0.76, top_y - 2, x + w * 0.76, top_y + 0.012 * g.Hf, 3), paint(mul(sc, 0.8)))
        c.drawPath(rrect(toe - w * 0.9, FY - 0.007 * g.Hf, toe + w * 0.9, FY + 1, 3), paint(mul(sc, 0.65)))
        return
    # bàn chân / giày (front view: mũi giày chĩa ra ngoài một chút)
    toe = x + sg * w * 0.35
    if sp.shoe in ("sandals", "bare"):
        skin = p.skin if sp.shoe == "sandals" else (sp.shoe_col if sp.shoe_col.startswith("#") else p.skin)
        foot = smooth([(x - w * 0.45, ay - 4), (x + w * 0.45, ay - 4), (toe + w * 0.7, FY - 8), (toe + w * 0.6, FY),
                       (toe - w * 0.7, FY), (toe - w * 0.75, FY - 8)], tension=0.4)
        flat(c, foot, skin, d=w * 0.12, rim=0.2, bottom=0)
        if sp.shoe == "sandals":
            c.drawPath(rrect(toe - w * 0.8, FY - 4, toe + w * 0.75, FY + 2, 3), paint(mul(sp.shoe_col, 0.8)))
            c.drawPath(rrect(toe - w * 0.62, FY - 0.016 * g.Hf, toe + w * 0.6, FY - 0.006 * g.Hf, 3), paint(sp.shoe_col))
        return
    sc = sp.shoe_col
    h = 0.032 * g.Hf if sp.shoe != "flats" else 0.022 * g.Hf
    shoe = smooth([(x - w * 0.5, ay - h * 0.5), (x + w * 0.5, ay - h * 0.5), (toe + w * 0.85, FY - h * 0.35),
                   (toe + w * 0.8, FY), (toe - w * 0.8, FY), (toe - w * 0.85, FY - h * 0.4)], tension=0.35)
    flat(c, shoe, sc, d=w * 0.15, rim=0.2, hl=0.25, bottom=0)
    if sp.shoe == "sneakers":
        c.drawPath(rrect(toe - w * 0.85, FY - 0.008 * g.Hf, toe + w * 0.85, FY + 1, 3), paint(lit(sc, 0.5) if luma(sc) < 0.6
                                                                                            else mul(sc, 0.75)))
        seam(c, [(toe - w * 0.4, FY - h * 0.6), (toe + w * 0.4, FY - h * 0.5)], mul(sc, 0.55), 1.4, 0.7, curve=False)
    else:
        c.drawPath(rrect(toe - w * 0.85, FY - 0.006 * g.Hf, toe + w * 0.85, FY + 1, 3), paint(mul(sc, 0.65)))
    if p.ghost == "water" and s == "r":
        c.drawPath(_drop(toe + w, FY - 0.03 * g.Hf, 0.012 * g.Hf), paint(DRIP, 0.8))


# ======================================================================= tay
def draw_arm_up(c: skia.Canvas, g: Geo, s: str) -> None:
    p = g.p
    sp = outfit_spec(p)
    (x1, y1), (x2, y2) = g.shoulder(s), g.elbow(s)
    w = g.arm_w
    sc = sp.sleeve_col or sp.top
    if p.outfit_type == "hi_vis_vest":
        sc = sp.top
    arm = capsule(x1, y1, x2, y2, w, w * 0.92)
    if sp.sleeve == "none":
        flat(c, arm, p.skin, d=w * 0.18, rim=0.3)
        if "tattoo_arm" in p.accessories and s == "l":
            c.save()
            c.clipPath(arm, doAntiAlias=True)
            _draw_tattoo(c, g, x1, y1 + w * 0.3, x2, y2, w, 1)
            c.restore()
        return
    if sp.sleeve == "long":
        wide = 1.18 if sp.loose else 1.06
        sleeve = capsule(x1, y1, x2, y2, w * wide, w * wide * 0.96)
        flat(c, sleeve, sc, d=w * 0.2, rim=0.3, edge=0.35)
        puff = _sleeve_puff(g, s, 0.3, 1.32)
        flat(c, puff, sc, d=w * 0.22, rim=0.3, edge=0.35)
        if p.outfit_type == "dot_blouse":
            draw_pattern(c, g, union(sleeve, puff), sp, seed=21)
        seam(c, [(x2 - w * 0.3, y2 - 0.02 * g.Hf), (x2 + w * 0.1, y2 - 0.008 * g.Hf)], mul(sc, 0.62), 1.4, 0.6, curve=False)
        _sleeve_marks(c, g, s, puff)
        return
    flat(c, arm, p.skin, d=w * 0.18, rim=0.3)
    puff = _sleeve_puff(g, s, 0.42, 1.5 if p.outfit_type in ("pajamas", "dress") else 1.42)
    flat(c, puff, sc, d=w * 0.22, rim=0.3, edge=0.35)
    if p.outfit_type == "floral_blouse":
        draw_pattern(c, g, puff, sp, seed=11 if s == "l" else 13)
    if p.outfit_type in ("pajamas", "dress") and "dots" in p.colors:
        draw_pattern(c, g, puff, sp, seed=17)
    b = puff.getBounds()
    hem_y = b.bottom() - w * 0.16
    cuff = sp.cuff
    if cuff:
        band = inter(puff, rrect(b.left() - 5, hem_y - w * 0.18, b.right() + 5, b.bottom() + 5, 0))
        c.drawPath(band, paint(cuff))
    else:
        seam(c, [(b.left() + w * 0.2, hem_y), (b.right() - w * 0.2, hem_y)], mul(sc, 0.62), 1.4, 0.6, curve=False)
    _sleeve_marks(c, g, s, puff)


def _sleeve_marks(c: skia.Canvas, g: Geo, s: str, puff: skia.Path) -> None:
    """Vạch quân hàm (chevron vàng chung chung, không phù hiệu thật) trên tay áo."""
    if "chevrons" not in g.p.accessories:
        return
    b = puff.getBounds()
    x = (b.left() + b.right()) / 2
    w = b.width() * 0.32
    col = g.p.colors.get("chevron", "#d9b44a")
    for i in range(2):
        y = b.top() + b.height() * (0.42 + i * 0.17)
        c.drawPath(poly([(x - w, y), (x, y + w * 0.55), (x + w, y)], close=False), pen(col, g.Hf * 0.0045))


def _draw_tattoo(c: skia.Canvas, g: Geo, x1: float, y1: float, x2: float, y2: float, w: float, seed: int) -> None:
    """Hình xăm dây leo / rắn gốc: nét lượn sóng xanh đen dọc cánh tay + vài lá nhỏ (vẽ trong vùng tay)."""
    ink = g.p.colors.get("tattoo", "#2f4a5a")
    n = 14
    pts = []
    for i in range(n + 1):
        t = i / n
        x = x1 + (x2 - x1) * t + math.sin(t * math.tau * 1.6 + seed) * w * 0.42
        y = y1 + (y2 - y1) * t
        pts.append((x, y))
    c.drawPath(smooth(pts, close=False), pen(ink, w * 0.13, 0.85))
    for i in (3, 7, 11):
        x, y = pts[i]
        sgn = 1 if i % 2 else -1
        leaf = smooth([(x, y), (x + sgn * w * 0.32, y - w * 0.12), (x + sgn * w * 0.4, y + w * 0.12)], tension=0.5)
        c.drawPath(leaf, paint(ink, 0.8))


def draw_arm_low(c: skia.Canvas, g: Geo, s: str) -> None:
    p = g.p
    sp = outfit_spec(p)
    (x1, y1), (x2, y2) = g.elbow(s), g.wrist(s)
    w = g.fore_w
    sc = sp.sleeve_col or sp.top
    if p.outfit_type == "hi_vis_vest":
        sc = sp.top
    if sp.sleeve == "long":
        wide = 1.3 if sp.loose else 1.08
        sleeve = capsule(x1, y1, x2, y2 - 0.006 * g.Hf, w * 1.1, w * wide)
        flat(c, sleeve, sc, d=w * 0.2, rim=0.3, edge=0.35)
        if p.outfit_type == "dot_blouse":
            draw_pattern(c, g, sleeve, sp, seed=23)
        cuff = rrect(x2 - w * wide * 0.55, y2 - 0.024 * g.Hf, x2 + w * wide * 0.55, y2 + 0.002 * g.Hf, w * 0.2)
        c.drawPath(cuff, paint(sp.cuff or mul(sc, 0.88)))
    else:
        arm = capsule(x1, y1, x2, y2, w, w * 0.84)
        flat(c, arm, p.skin, d=w * 0.18, rim=0.3)
        seam(c, [(x1 - w * 0.22, y1 + 2), (x1 + w * 0.05, y1 + 6)], mul(p.skin, 0.75), 1.4, 0.6, curve=False)  # nếp khuỷu
        if "tattoo_arm" in p.accessories and s == "l":
            c.save()
            c.clipPath(arm, doAntiAlias=True)
            _draw_tattoo(c, g, x1, y1 + w * 0.2, x2, y2 - w * 0.4, w, 2.5)
            c.restore()
    acc = p.accessories
    if "wristwatch" in acc and s == "l":
        bx, by = x2, y2 - 0.016 * g.Hf
        c.drawPath(rrect(bx - w * 0.62, by - w * 0.2, bx + w * 0.62, by + w * 0.2, w * 0.1), paint("#2a2a2e"))
        c.drawPath(rrect(bx - w * 0.3, by - w * 0.3, bx + w * 0.3, by + w * 0.3, w * 0.1), paint("#c9ccd1"))
        c.drawPath(circle(bx, by, w * 0.2), paint("#f4f4f0"))
    if s == "l" and ("jade_bangle" in acc or ("prayer_beads" in acc and p.outfit_type not in ("monk_robe", "ritual_robe"))):
        jade = "jade_bangle" in acc
        bx, by = x2, y2 - 0.012 * g.Hf
        if jade:
            c.drawPath(oval(bx, by, w * 0.68, w * 0.24), pen("#3aa37a", w * 0.2))
            c.drawPath(oval(bx + w * 0.2, by - w * 0.05, w * 0.12, w * 0.05), paint("#c8f0dc", 0.8))
        else:
            dots = pen("#6a3a22", w * 0.24)
            dots.setPathEffect(skia.DashPathEffect.Make([0.1, w * 0.3], 0))
            c.drawPath(oval(bx, by, w * 0.62, w * 0.2), dots)


def draw_hand(c: skia.Canvas, g: Geo, s: str, state: str) -> None:
    p = g.p
    x, y = g.wrist(s)
    L = g.hand_len
    w = g.fore_w * 1.12
    inner = -g.side(s)                       # phía ngón cái (về giữa thân)
    skin = p.skin
    if g.ent:   # tay dài, ngón như vuốt
        col = p.colors.get("legs") or mul(skin, 0.9)
        palm = rrect(x - w * 0.45, y - 2, x + w * 0.45, y + L * 0.35, w * 0.3)
        flat(c, palm, col, d=w * 0.12, rim=0.2)
        n = 4
        for i in range(n):
            fx = x + (i - (n - 1) / 2) * w * 0.28
            spread = (i - (n - 1) / 2) * w * (0.25 if state == "open" else 0.05)
            ln = L * (1.0 if state != "fist" else 0.5)
            if state == "point" and i != 1:
                ln = L * 0.45
            c.drawPath(capsule(fx, y + L * 0.3, fx + spread, y + L * 0.3 + ln * 0.7, w * 0.16, w * 0.08), paint(col))
        return
    dk = mul(skin, 0.72)
    if state == "point":
        fist = rrect(x - w * 0.5, y - 2, x + w * 0.5, y + L * 0.62, w * 0.38)
        finger = capsule(x + inner * w * 0.14, y + L * 0.4, x + inner * w * 0.14, y + L * 1.12, w * 0.32, w * 0.28)
        flat(c, union(fist, finger), skin, d=w * 0.12, rim=0.25)
        thumb = capsule(x + inner * w * 0.45, y + L * 0.15, x + inner * w * 0.32, y + L * 0.55, w * 0.25, w * 0.22)
        flat(c, thumb, skin, d=w * 0.06, rim=0.2)
        for i in range(2):
            seam(c, [(x - inner * w * 0.42, y + L * (0.32 + i * 0.13)), (x - inner * w * 0.02, y + L * (0.32 + i * 0.13))],
                 dk, 1.4, 0.7, curve=False)
        return
    if state == "fist":
        fist = rrect(x - w * 0.52, y - 2, x + w * 0.52, y + L * 0.72, w * 0.42)
        flat(c, fist, skin, d=w * 0.12, rim=0.25)
        for i in range(3):
            seam(c, [(x - w * 0.4, y + L * (0.32 + i * 0.13)), (x + w * 0.4, y + L * (0.32 + i * 0.13))], dk, 1.4, 0.6,
                 curve=False)
        return
    # mitten (găng): lòng bàn tay + ngón cái tách
    palm = smooth([(x - w * 0.5, y - 2), (x + w * 0.5, y - 2), (x + w * 0.56, y + L * 0.55), (x + w * 0.42, y + L * 0.96),
                   (x, y + L * 1.05), (x - w * 0.42, y + L * 0.96), (x - w * 0.56, y + L * 0.55)], tension=0.45)
    thumb = capsule(x + inner * w * 0.45, y + L * 0.16, x + inner * w * 0.64, y + L * 0.6, w * 0.3, w * 0.24)
    flat(c, union(palm, thumb), skin, d=w * 0.12, rim=0.25)
    seam(c, [(x + inner * w * 0.22, y + L * 0.55), (x + inner * w * 0.2, y + L * 0.92)], dk, 1.3, 0.55, curve=False)
    if p.ghost == "water" and s == "r":
        c.drawPath(_drop(x, y + L * 1.25, g.hh * 0.06), paint(DRIP, 0.85))


# ======================================================================= xuất file
def _render(fn: Callable[[skia.Canvas], None], g: Geo,
            region: tuple[float, float, float, float] | None = None) -> tuple[np.ndarray, float, float]:
    x0, y0, x1, y1 = region if region else (0.0, 0.0, float(W), float(g.CH))
    x0, y0 = max(0.0, math.floor(x0)), max(0.0, math.floor(y0))
    x1, y1 = min(float(W), math.ceil(x1)), min(float(g.CH), math.ceil(y1))
    surf = skia.Surface(int((x1 - x0) * SS), int((y1 - y0) * SS))
    cv = surf.getCanvas()
    cv.clear(skia.ColorTRANSPARENT)
    cv.scale(SS, SS)
    cv.translate(-x0, -y0)
    fn(cv)
    return to_rgba(surf.makeImageSnapshot()), x0, y0


def _bbox(arrs: list[np.ndarray]) -> tuple[int, int, int, int] | None:
    alpha = np.zeros(arrs[0].shape[:2], dtype=bool)
    for a in arrs:
        alpha |= a[:, :, 3] > 0
    ys, xs = np.nonzero(alpha)
    if len(xs) == 0:
        return None
    pad = 2
    return (max(0, xs.min() - pad), max(0, ys.min() - pad), min(alpha.shape[1], xs.max() + pad + 1),
            min(alpha.shape[0], ys.max() + pad + 1))


class _Writer:
    def __init__(self, out: Path, g: Geo) -> None:
        self.out = out
        self.g = g
        pdir = out / "parts"
        pdir.mkdir(parents=True, exist_ok=True)
        for old in pdir.glob("*.png"):   # xoá ảnh bộ phận cũ (tạo lại toàn bộ)
            try:
                old.unlink()
            except OSError:
                pass
        self.parts: list[dict] = []

    def part(self, name: str, bone: str, fn: Callable[[skia.Canvas], None], view: str | None = None,
             region=None) -> None:
        arr, ox, oy = _render(fn, self.g, region)
        bb = _bbox([arr])
        if bb is None:
            return
        x0, y0, x1, y1 = bb
        rel = f"parts/{name}.png"
        save_png(arr[y0:y1, x0:x1], self.out / rel)
        d = {"name": name, "bone": bone, "image": rel, "offset": [round(ox + x0 / SS, 3), round(oy + y0 / SS, 3)]}
        if view:
            d["view"] = view
        self.parts.append(d)

    def slot(self, slot: str, bone: str, states: dict[str, Callable[[skia.Canvas], None]], name: str | None = None,
             view: str | None = None, default: str | None = None, region=None) -> None:
        rendered = {k: _render(f, self.g, region) for k, f in states.items()}
        arrs = {k: v[0] for k, v in rendered.items()}
        ox, oy = next(iter(rendered.values()))[1:]
        bb = _bbox(list(arrs.values()))
        if bb is None:
            return
        x0, y0, x1, y1 = bb
        imgs = {}
        nm = name or slot
        for k, a in arrs.items():
            if not (a[:, :, 3] > 0).any() and k != default:
                continue
            rel = f"parts/{nm}_{k}.png"
            save_png(a[y0:y1, x0:x1], self.out / rel)
            imgs[k] = rel
        d = {"name": nm, "bone": bone, "slot": slot, "images": imgs,
             "offset": [round(ox + x0 / SS, 3), round(oy + y0 / SS, 3)]}
        if view:
            d["view"] = view
        if default:
            d["default"] = default
        self.parts.append(d)


def _profile(cid: str, p: CharParams, meta: dict | None) -> dict:
    meta = meta or {}
    sp = outfit_spec(p)
    tags = list(dict.fromkeys(list(meta.get("tags") or []) + _auto_tags(p)))
    label = meta.get("label") or _auto_label(p)
    desc = meta.get("description") or ", ".join(tags)
    faceless = p.face == "none"
    prof = {"label": label, "gender": p.gender, "age": p.age, "description": desc, "tags": tags, "style": "cutout",
            "coverage": "full_body",
            "actions": ["idle", "talk", "walk", "sit", "point", "nod", "shake_head", "scared"],
            "lipsync": not faceless, "views": ["front", "back"], "expressions": list(EXPRESSIONS),
            "hair_style": p.hair_style, "outfit": p.outfit_type}
    for k in ("archetype", "voice", "roles", "name_vi"):
        if meta.get(k) is not None:
            prof[k] = meta[k]
    if sp.lower in ("skirt", "dress", "pencil", "robe", "aodai", "sarong"):
        prof["lower"] = sp.lower
    if meta.get("library"):   # thư viện mở rộng (lô 2): hồ sơ đầy đủ cho casting
        prof["has_back_view"] = True
        prof["extra_expressions"] = list(EXTRA_EXPRESSIONS) if not faceless else []
        prof["poses"] = list(POSE_NAMES) if not faceless else []
        prof["provenance"] = "procedural_library"
        if meta.get("description_en"):
            prof["description_en"] = meta["description_en"]
    return prof


def _auto_tags(p: CharParams) -> list[str]:
    t = [p.gender, p.age, p.hair_style, p.outfit_type]
    if p.build != "normal":
        t.append(p.build)
    if p.ghost:
        t += ["ghost", p.ghost]
    t += [a for a in p.accessories if not a.endswith("_optional")]
    return t


def _auto_label(p: CharParams) -> str:
    g = "Nữ" if p.gender == "female" else "Nam"
    a = {"child": "trẻ em", "young": "trẻ", "adult": "trưởng thành", "old": "lớn tuổi"}[p.age]
    return f"{g} {a} · {p.hair_style} · {p.outfit_type}"


def make_character(cid: str, params: CharParams | dict | None = None, out_root: Path = CHARACTERS,
                   meta: dict | None = None, preview: bool = True) -> Path:
    """Tạo puppet. Trả về đường dẫn character.json. `meta` = thông tin hồ sơ (archetype, tags, voice, label...)."""
    if params is None:
        params = CharParams()
    elif isinstance(params, dict):
        params = CharParams.from_dict(params)
    raw = params
    p = normalize(params)
    if p.ghost:
        p = _ghostify(p)
    g = Geo(p)
    out = Path(out_root) / cid
    w = _Writer(out, g)
    cx = g.cx
    hr = g.head_region()

    bones = {
        "root": {"parent": None, "pivot": [cx, g.FY]},
        "hip": {"parent": "root", "pivot": [cx, g.hip_y]},
        "torso": {"parent": "hip", "pivot": [cx, g.waist_y]},
        "neck": {"parent": "torso", "pivot": [cx, g.shoulder_y]},
        "head": {"parent": "neck", "pivot": [g.hx, g.chin - 0.06 * g.hh]},
    }
    for s in ("l", "r"):
        bones[f"arm_{s}_up"] = {"parent": "torso", "pivot": list(g.shoulder(s))}
        bones[f"arm_{s}_low"] = {"parent": f"arm_{s}_up", "pivot": list(g.elbow(s))}
        bones[f"hand_{s}"] = {"parent": f"arm_{s}_low", "pivot": list(g.wrist(s))}
        bones[f"leg_{s}_up"] = {"parent": "hip", "pivot": list(g.hipj(s))}
        bones[f"leg_{s}_low"] = {"parent": f"leg_{s}_up", "pivot": list(g.knee(s))}
    for b in bones.values():
        b["pivot"] = [round(v, 2) for v in b["pivot"]]

    face_on = p.face != "none"
    # ---- thứ tự vẽ (sau cùng ở trên)
    w.part("hair_back", "head", lambda c: draw_hair_back(c, g), view="front")
    w.part("backpack_behind", "torso", lambda c: draw_backpack_behind(c, g), view="front")
    for s in ("r", "l"):
        w.part(f"leg_{s}_up", f"leg_{s}_up", lambda c, s=s: draw_leg_up(c, g, s))
        w.part(f"leg_{s}_low", f"leg_{s}_low", lambda c, s=s: draw_leg_low(c, g, s))
    w.part("pelvis", "hip", lambda c: draw_pelvis(c, g), view="front")
    w.part("pelvis_back", "hip", lambda c: draw_pelvis(c, g, back=True), view="back")
    w.part("neck", "neck", lambda c: draw_neck(c, g))
    w.part("torso", "torso", lambda c: draw_torso(c, g), view="front")
    w.part("torso_back", "torso", lambda c: draw_torso(c, g, back=True), view="back")
    w.part("backpack_back", "torso", lambda c: draw_backpack_back(c, g), view="back")
    w.part("head", "head", lambda c: draw_head(c, g), view="front", region=hr)
    w.part("face", "head", lambda c: draw_face(c, g), view="front")
    if face_on:
        w.slot("eyes", "head", {k: (lambda c, k=k: draw_eyes(c, g, k)) for k in EYE_STATES}, view="front", region=hr)
        mouth_states = list(MOUTH_VISEMES) + list(MOUTH_EXTRA)
        w.slot("mouth", "head", {k: (lambda c, k=k: draw_mouth(c, g, k)) for k in mouth_states}, view="front", region=hr)
    brows_states = {k: (lambda c, k=k: draw_brows(c, g, k)) for k in BROW_STATES}
    over_face = p.hair_style == "long_over_face"
    # mũ lưỡi trai (archetype khai báo màu mũ): mày nằm DƯỚI vành mũ — chỉ ló ra khi hạ thấp (giận/nheo)
    brows_under = over_face or (p.hair_style == "cap_hidden" and bool(p.cap_color) and bool(meta and meta.get("library")))
    def fx_slots() -> None:
        for fx in FX_SLOTS:
            kind = fx[3:]
            w.slot(fx, "head", {"on": (lambda c, kind=kind: draw_fx(c, g, kind))}, view="front", default="off",
                   region=hr)

    if face_on and over_face and not g.ent:   # tóc phủ kín mặt: mày + FX nằm dưới tóc
        w.slot("brows", "head", brows_states, view="front", region=hr)
        fx_slots()
    elif face_on and brows_under and not g.ent:
        w.slot("brows", "head", brows_states, view="front", region=hr)
    w.part("glasses", "head", lambda c: draw_glasses(c, g), view="front")
    w.part("hair_front", "head", lambda c: draw_hair_front(c, g), view="front")
    w.part("head_props", "head", lambda c: draw_head_props(c, g), view="front", region=hr)
    if p.outfit_type == "police_uniform" or "police_cap" in p.accessories:
        w.part("police_cap", "head", lambda c: draw_police_cap(c, g), view="front", region=hr)
    if face_on and not over_face and not g.ent:
        if not brows_under:
            w.slot("brows", "head", brows_states, view="front", region=hr)
        fx_slots()
    if p.wet:
        w.part("fx_drips", "head", lambda c: draw_drips(c, g), view="front")
    w.part("head_back", "head", lambda c: draw_head_back(c, g), view="back", region=hr)
    w.part("hair_back_view", "head", lambda c: draw_hair_back_view(c, g), view="back")
    w.part("head_props_back", "head", lambda c: draw_head_props(c, g, back=True), view="back", region=hr)
    if p.outfit_type == "police_uniform" or "police_cap" in p.accessories:
        w.part("police_cap_back", "head", lambda c: draw_police_cap(c, g, back=True), view="back", region=hr)
    for s in ("r", "l"):
        w.part(f"arm_{s}_up", f"arm_{s}_up", lambda c, s=s: draw_arm_up(c, g, s))
        w.part(f"arm_{s}_low", f"arm_{s}_low", lambda c, s=s: draw_arm_low(c, g, s))
        w.slot(f"hand_{s}", f"hand_{s}", {k: (lambda c, k=k, s=s: draw_hand(c, g, s, k)) for k in ("open", "point", "fist")})

    wx, wy = g.wrist("r")
    exprs = {}
    library = bool(meta and meta.get("library"))
    for k, v in list(EXPRESSIONS.items()) + (list(EXTRA_EXPRESSIONS.items()) if library and face_on and not g.ent else []):
        e = dict(v)
        e["fx"] = [f for f in v["fx"] if face_on and not g.ent]
        exprs[k] = e
    bl = _badge_rect(g)
    data = {
        "id": cid,
        "height_px": g.FY,
        "image_scale": SS,
        "canvas": [W, g.CH],
        "head_box": [round(g.U(-1.15), 1), round(g.top - (0.25 * g.hh if p.hair_style in ("spiky", "afro_curly", "bun")
                                                         else 0.06 * g.hh), 1), round(g.U(1.15), 1), round(g.chin, 1)],
        "bones": bones,
        "parts": w.parts,
        "expressions": exprs,
        "views": ["front", "back"],
        "hand_prop_anchor": {"bone": "hand_r", "point": [round(wx, 1), round(wy + g.hand_len * 0.5, 1)]},
        "badge_anchor": {"bone": "torso", "rect": [round(v, 1) for v in bl]},
        "generator": {"kind": GENERATOR, "version": GENERATOR_VERSION, "params": asdict(raw)},
        "provenance": {"kind": "procedural_library" if library else "procedural",
                       "generator": f"{GENERATOR} v{GENERATOR_VERSION}",
                       "note": "Nhân vật gốc sinh bằng code; không dùng ảnh tham khảo."},
        "profile": _profile(cid, p, meta),
    }
    if library and face_on and not g.ent:
        data["poses"] = make_poses(g)
    if meta and meta.get("archetype"):
        data["archetype"] = meta["archetype"]
    (out / "character.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    if preview:
        try:
            img = render_figure(cid, root=out_root, height_px=760)
            save_png(img, out / "preview.png")
        except Exception as e:  # noqa: BLE001 — preview không được làm hỏng việc tạo puppet
            log.warning("Không tạo được preview cho %s: %s", cid, e)
    return out / "character.json"


def _ghostify(p: CharParams) -> CharParams:
    """Ma: khử bão hoà lạnh mọi màu áo (trừ váy đỏ — phần tử bão hoà duy nhất), da lạnh."""
    q = p
    keep = {"dress", "dress_dark", "trim"} if p.outfit_type in ("ao_dai", "red_traditional_dress") else set()
    tint = "#9fb0c8"
    amt = {"water": 0.55, "pale": 0.5, "frozen": 0.6, "entity": 1.0}.get(p.ghost or "", 0.5)
    q.colors = {k: (v if k in keep else desat(v, amt, tint, 0.12)) for k, v in p.colors.items()}
    if p.ghost == "entity":
        q.hair_color = desat(p.hair_color, 1.0)
    q.blush = 0.0
    q.lip_color = q.lip_color and desat(q.lip_color, 0.8, tint, 0.3)
    return q


# ======================================================================= kính
def draw_glasses(c: skia.Canvas, g: Geo) -> None:
    acc = g.p.accessories
    if g.p.face == "none":
        return
    rect = any(a in acc for a in ("glasses_black_rect", "glasses", "glasses_thin"))
    gold = "reading_glasses_gold_round" in acc
    if not (rect or gold):
        return
    fr = "#1b1a1e" if rect else "#c9a243"
    lw = g.rx * (0.05 if rect else 0.032)
    centers = []
    for s in ("l", "r"):
        ex, ey = g.ex[s], g.ey
        if rect:
            r = rrect(ex - g.erx * 2.7, ey - g.ery * 1.6, ex + g.erx * 2.7, ey + g.ery * 1.7, g.ery * 0.6)
        else:
            r = circle(ex, ey + g.ery * 0.1, g.ery * 2.0)
        c.drawPath(r, paint("#d9ecf5", 0.16))
        c.drawPath(r, pen(fr, lw))
        b = r.getBounds()
        seam(c, [(b.left() + b.width() * 0.6, b.top() + b.height() * 0.25), (b.left() + b.width() * 0.8, b.top() + b.height() * 0.5)],
             "#ffffff", lw * 0.6, 0.55, curve=False)
        centers.append(b)
    bl, br = centers
    y = (bl.top() + bl.bottom()) / 2 - g.ery * 0.3
    seam(c, [(bl.right(), y), ((bl.right() + br.left()) / 2, y - g.ery * 0.25), (br.left(), y)], fr, lw)
    for b, s in ((bl, -1), (br, 1)):
        x = b.left() if s < 0 else b.right()
        seam(c, [(x, y), (g.U(s * 0.98), g.V(0.08))], fr, lw * 0.8, curve=False)
    if "eyeglass_chain_dotted" in acc:
        dots = pen("#d8b85a", g.rx * 0.035)
        dots.setPathEffect(skia.DashPathEffect.Make([0.1, g.rx * 0.07], 0))
        for s in (-1, 1):
            c.drawPath(smooth([g.P(s * 0.98, 0.08), g.P(s * 1.08, 0.7), g.P(s * 0.9, 1.25),
                               (g.cx + s * g.neck_w * 1.3, g.shoulder_y + 0.01 * g.Hf)], close=False), dots)


# ======================================================================= từ catalog / mô tả
def _load_catalog() -> list[dict]:
    try:
        return json.loads(CATALOG_FILE.read_text(encoding="utf-8")).get("archetypes", [])
    except (OSError, ValueError) as e:
        log.warning("Không đọc được %s: %s", CATALOG_FILE, e)
        return []


def params_from_archetype(a: dict) -> CharParams:
    """Đọc 1 mục archetypes.json -> CharParams."""
    tags = set(a.get("tags") or [])
    hair = a.get("hair") or {}
    outfit = a.get("outfit") or {}
    desc = (outfit.get("desc") or "").lower()
    colors = {k: v for k, v in (outfit.get("colors") or {}).items() if isinstance(v, str)}
    if hair.get("strand"):
        colors["strand"] = hair["strand"]
    p = CharParams(gender=a.get("gender", "male"), age=a.get("age", "adult"))
    p.skin = _hex(a.get("skin"), p.skin)
    p.hair_style = hair.get("style", "short_side_part")
    p.hair_color = _hex(hair.get("color"), "#1c1a1f")
    p.hair_highlight = hair.get("highlight")
    p.hair_tie = hair.get("tie")
    p.cap_color = hair.get("cap")
    p.pigtails = "pigtails" in tags or "bím" in (hair.get("note") or "")
    p.outfit_type = outfit.get("type", "tee")
    p.colors = colors
    p.accessories = [x for x in (a.get("accessories") or []) if not x.endswith("_optional")]
    if "peter pan" in desc or "cổ tròn" in desc:
        p.neck_style = "peter_pan"
    if "fat" in tags:
        p.build = "heavy"
    elif "thin" in tags:
        p.build = "slim"
    if "tall" in tags:
        p.height_scale = 1.05
    p.eye_bags = bool(tags & {"eye_bags", "tired"})
    p.wrinkles = "wrinkles" in tags or p.age == "old"
    fh = hair.get("facial_hair")
    p.facial_hair = fh if fh in ("white_goatee", "goatee", "mustache", "stubble") else (
        "stubble" if "stubble" in tags else ("goatee" if "beard" in tags else "none"))
    if "entity" in tags:
        p.face = "entity"
        p.ghost = "entity"
        p.height_scale = 1.45
        p.build = "slim"
    elif "silhouette" in tags:
        p.face = "none"
        p.outfit_type = "silhouette"
    elif "ghost" in tags:
        p.ghost = "water" if "wet" in tags else "pale"
    p.wet = "wet" in tags or "water_drips_fx" in p.accessories
    if p.gender == "female":
        p.blush = 0.6 if ("blush" in tags or p.age in ("child", "young")) else 0.45
        p.lip_color = "#b3343c" if p.age == "old" and "son" in (a.get("notes") or "") else (
            "#d77c83" if p.age in ("young", "adult") else None)
    else:
        p.blush = 0.55 if ("blush" in tags or p.age == "child") else 0.22
    if p.outfit_type == "police_uniform":
        p.accessories.append("police_cap")
    if a.get("build") in ("slim", "normal", "heavy"):
        p.build = a["build"]
    if a.get("blush") is not None:
        p.blush = float(a["blush"])
    if "eye_bags" in a:
        p.eye_bags = bool(a["eye_bags"])
    return p


def make_archetype(archetype_id: str, out_root: Path = CHARACTERS, preview: bool = True) -> Path:
    arch = next((a for a in _load_catalog() if a.get("id") == archetype_id), None)
    if arch is None:
        raise KeyError(f"Không có archetype '{archetype_id}' trong {CATALOG_FILE}")
    p = params_from_archetype(arch)
    meta = {"archetype": archetype_id, "label": arch.get("name_vi"), "name_vi": arch.get("name_vi"),
            "tags": list(arch.get("tags") or []) + [arch.get("gender", ""), arch.get("age", "")],
            "description": f"{arch.get('name_vi', '')}. {(arch.get('outfit') or {}).get('desc', '')}",
            "voice": arch.get("default_voice"), "roles": arch.get("roles")}
    if arch.get("library"):   # lô 2: nhãn + mô tả song ngữ (vi + từ khoá en) cho casting
        meta["library"] = True
        meta["label"] = arch.get("label") or meta["label"]
        meta["tags"] = list(dict.fromkeys(meta["tags"] + list(arch.get("tags_en") or [])))
        if arch.get("description_en"):
            meta["description_en"] = arch["description_en"]
            meta["description"] = f"{meta['description']} | EN: {arch['description_en']}"
    return make_character(archetype_id, p, out_root, meta=meta, preview=preview)


def make_all_archetypes(out_root: Path = CHARACTERS, preview: bool = True) -> list[Path]:
    out = []
    for a in _load_catalog():
        try:
            out.append(make_archetype(a["id"], out_root, preview=preview))
        except Exception as e:  # noqa: BLE001
            log.warning("Lỗi tạo archetype %s: %s", a.get("id"), e)
    return out


def params_from_description(desc: str, gender: str = "male", age: str = "adult") -> CharParams:
    """Suy tham số thô từ mô tả tiếng Việt/Anh (từ khoá + tags)."""
    d = (desc or "").lower()
    has = lambda *ks: any(k in d for k in ks)  # noqa: E731
    p = CharParams(gender=gender if gender in ("male", "female") else "male",
                   age=age if age in ("child", "young", "adult", "old") else "adult")
    colors = {"trắng": "#ecebe4", "white": "#ecebe4", "đen": "#26231f", "black": "#26231f", "xanh dương": "#2f4a78",
              "xanh lam": "#2f4a78", "blue": "#2f4a78", "xanh lá": "#3f6b3a", "green": "#3f6b3a", "đỏ": "#a3302b",
              "red": "#a3302b", "vàng": "#e2b43a", "yellow": "#e2b43a", "nâu": "#7a4a2a", "brown": "#7a4a2a",
              "xám": "#7b7d80", "grey": "#7b7d80", "gray": "#7b7d80", "hồng": "#d98597", "pink": "#d98597",
              "tím": "#6b4a8a", "purple": "#6b4a8a", "cam": "#d9762b", "orange": "#d9762b"}
    p.outfit_type = "tee"
    for k, v in colors.items():
        if has(f"áo {k}", f"{k} shirt", f"áo sơ mi {k}", f"áo thun {k}"):
            p.colors.update(shirt=v, tee=v, blouse=v, top=v)
        if has(f"váy {k}", f"đầm {k}", f"{k} dress"):
            p.outfit_type = "dress"
            p.colors["dress"] = v
        if has(f"quần {k}", f"{k} pants"):
            p.colors["pants"] = v
    # tóc
    if has("hói", "bald", "trọc", "cạo đầu"):
        p.hair_style = "bald"
    elif has("xoăn", "curly", "uốn"):
        p.hair_style = "curly_short" if p.age == "old" or p.gender == "female" else "afro_curly"
    elif has("bob", "ngang cằm", "tóc ngắn ngang"):
        p.hair_style = "bob_bangs"
    elif has("che mặt", "phủ mặt", "over face", "xõa che"):
        p.hair_style = "long_over_face"
    elif has("đuôi ngựa", "ponytail", "buộc tóc", "bím"):
        p.hair_style = "long_ponytail"
        p.pigtails = has("bím", "pigtail", "2 túm")
    elif has("búi", "bun"):
        p.hair_style = "bun"
    elif has("tóc dài", "long hair") or (p.gender == "female" and not has("tóc ngắn", "short hair")):
        p.hair_style = "long_straight"
    elif has("dựng", "spiky", "vuốt"):
        p.hair_style = "spiky"
    elif has("đầu đinh", "buzz", "húi cua"):
        p.hair_style = "buzz"
    if has("mũ lưỡi trai", "nón lưỡi trai", "cap"):
        p.hair_style = "cap_hidden"
    if has("tóc bạc", "grey hair", "white hair", "gray hair") or (p.age == "old" and p.hair_style != "bald"):
        p.hair_color = "#c9c6c0"
        if p.hair_style == "short_side_part":
            p.hair_style = "grey_short"
    # dáng
    if has("béo", "mập", "fat", "heavy", "bụng"):
        p.build = "heavy"
    if has("gầy", "thin", "slim", "ốm"):
        p.build = "slim"
    if has("cao lêu", "cao bất thường", "tall"):
        p.height_scale = 1.05
    # trang phục
    if has("đồng phục cửa hàng", "polo", "nhân viên cửa hàng"):
        p.outfit_type = "polo_uniform"
        p.accessories += ["name_badge", "store_emblem_leaf"]
    elif has("hoodie", "áo nỉ có mũ"):
        p.outfit_type = "hoodie"
    elif has("áo khoác", "jacket"):
        p.outfit_type = "utility_jacket"
    elif has("phản quang", "hi-vis", "xe ôm"):
        p.outfit_type = "hi_vis_vest"
    elif has("công an", "cảnh sát", "police"):
        p.outfit_type = "police_uniform"
        p.accessories.append("police_cap")
    elif has("bảo vệ", "security"):
        p.outfit_type = "security_uniform"
        p.hair_style = "cap_hidden"
    elif has("y tá", "nurse", "bác sĩ"):
        p.outfit_type = "nurse_scrubs"
    elif has("sư", "monk", "áo cà sa", "thầy cúng"):
        p.outfit_type = "monk_robe"
        p.hair_style = "bald"
    elif has("áo dài"):
        p.outfit_type = "ao_dai"
    elif has("bà ba"):
        p.outfit_type = "ao_ba_ba"
    elif has("học sinh", "nữ sinh", "nam sinh", "student", "đồng phục trường"):
        p.outfit_type = "school_uniform_f" if p.gender == "female" else "school_uniform_m"
    elif has("áo hoa", "floral"):
        p.outfit_type = "floral_blouse"
    elif has("văn phòng", "office", "công sở"):
        p.outfit_type = "office_blouse" if p.gender == "female" else "shirt_button"
    elif has("sơ mi", "shirt"):
        p.outfit_type = "shirt_button"
    elif has("ba lỗ", "tank"):
        p.outfit_type = "tank"
    elif has("váy", "đầm", "dress"):
        p.outfit_type = "dress"
    if has("quần đùi", "shorts"):
        p.colors.setdefault("shorts", "#3a5f8c")
    if has("dép", "sandal"):
        p.colors.setdefault("sandals", "#7a5a44")
    # phụ kiện
    if has("kính lão", "kính tròn", "reading glasses"):
        p.accessories += ["reading_glasses_gold_round", "eyeglass_chain_dotted"]
    elif has("kính", "glasses"):
        p.accessories.append("glasses_black_rect")
    if has("dây chuyền vàng", "gold chain"):
        p.accessories.append("gold_chain_square_pendant")
    elif has("dây chuyền", "necklace"):
        p.accessories.append("ball_chain_necklace")
    if has("balo", "ba lô", "backpack"):
        p.accessories.append("backpack_grey")
    if has("tràng hạt", "chuỗi hạt", "prayer beads"):
        p.accessories.append("prayer_beads")
    if has("bảng tên", "name badge"):
        p.accessories.append("name_badge")
    if has("túi xách", "túi đeo", "handbag", "bag"):
        p.accessories.append("handbag")
    if has("sẹo", "scar"):
        p.accessories.append("scar")
    if has("râu", "mustache"):
        p.facial_hair = "mustache"
    if has("râu dê", "goatee"):
        p.facial_hair = "white_goatee" if p.age == "old" else "goatee"
    if has("râu lún phún", "stubble"):
        p.facial_hair = "stubble"
    if has("quầng mắt", "mệt mỏi", "thâm quầng", "ca đêm", "eye bags"):
        p.eye_bags = True
    # da / ma
    if has("da ngăm", "rám nắng", "tan skin", "dark skin"):
        p.skin = "#c48a62"
    if has("da trắng", "fair skin"):
        p.skin = "#f1d3bd"
    if has("ma", "ghost", "hồn", "oan hồn"):
        p.ghost = "water" if has("nước", "ướt", "chết đuối", "wet") else "pale"
        p.skin = "#c9ccd6" if p.ghost == "water" else "#e4e2dc"
        p.wet = p.ghost == "water"
    if p.gender == "female":
        p.blush = 0.6 if p.age in ("child", "young") else 0.45
        p.lip_color = "#d77c83" if p.age in ("young", "adult") else None
    return p


# ======================================================================= preset nhân vật mẫu (kiểu mới)
PRESETS: dict[str, CharParams] = {
    # chủ tiệm lớn tuổi: hói, sơ mi trắng + tạp dề nâu (v1 có tạp dề -> v2 thay bằng sơ mi + khăn vai), dây chuyền
    "chu_tu": CharParams(gender="male", age="old", build="heavy", skin="#e3ad86", hair_style="bald",
                         hair_color="#bdb7ab", brow_color="#8f887d", outfit_type="shirt_button",
                         colors={"shirt": "#eeebe2", "pants": "#3d3631", "shoes": "#2a1f1a"},
                         accessories=["gold_chain_square_pendant", "scar", "towel_on_neck"], wrinkles=True,
                         eye_bags=True, blush=0.3),
    "toi": CharParams(gender="male", age="young", skin="#ebbd98", hair_style="short_side_part", hair_color="#231813",
                      outfit_type="utility_jacket", colors={"jacket": "#2c4470", "tee": "#e9e6df", "pants": "#2f2c2a",
                                                            "shoes": "#3b2a20"}, eye_bags=True, blush=0.25),
    "co_lan": CharParams(gender="female", age="young", build="slim", skin="#f0c6a3", hair_style="long_straight",
                         hair_color="#2a1a14", outfit_type="dress", colors={"dress": "#e4b33c", "sandals": "#7a4b2c"},
                         lip_color="#c2505a", blush=0.6, accessories=["hair_clip_red"]),
}
PRESET_META: dict[str, dict] = {
    "chu_tu": {"label": "Nam lớn tuổi · hói · sơ mi trắng · dây chuyền vàng",
               "tags": ["bald", "heavy", "white shirt", "gold chain", "scar", "hói", "vết sẹo", "chủ tiệm", "old", "male"]},
    "toi": {"label": "Nam trẻ · tóc ngắn · áo khoác xanh",
            "tags": ["short hair", "jacket", "tóc ngắn", "áo khoác", "người kể", "young", "male"]},
    "co_lan": {"label": "Nữ trẻ · tóc dài · váy vàng",
               "tags": ["long dark hair", "slim", "yellow dress", "tóc dài", "váy vàng", "young", "female"]},
}


def make_presets(out_root: Path = CHARACTERS, preview: bool = True) -> list[Path]:
    return [make_character(k, v, out_root, meta=PRESET_META.get(k), preview=preview) for k, v in PRESETS.items()]


# ======================================================================= pose tĩnh (IK 2 khớp)
POSE_NAMES = ("hand_over_mouth", "hands_over_mouth", "hand_to_ear", "hands_raised")


def _arm_ik(g: Geo, s: str, target: tuple[float, float], elbow_in: bool = True, stretch: float = 1.12) -> dict:
    """Xoay arm_{s}_up / arm_{s}_low để tâm bàn tay chạm `target` (toạ độ canvas). Cẳng tay được kéo dài
    tối đa `stretch` lần (sy) — tay rối ngắn, cần chút giãn để khuỷu vẫn sát thân. Trả về {bone: {r, sy}}."""
    S, E0, W0 = g.shoulder(s), g.elbow(s), g.wrist(s)
    a = math.dist(S, E0)
    f = math.dist(E0, W0)
    h = g.hand_len * 0.5
    b = f * stretch + h
    dx, dy = target[0] - S[0], target[1] - S[1]
    d = max(1e-3, min(math.hypot(dx, dy), a + b - 1e-3))
    th = math.atan2(dy, dx)
    al = math.acos(max(-1.0, min(1.0, (a * a + d * d - b * b) / (2 * a * d))))
    sg = g.side(s)
    # elbow_in: khuỷu ở phía dưới đường vai->đích (trước ngực / sát thân); ngược lại: khuỷu dang ra ngoài, nâng lên
    cands = [th + al, th - al]
    def score(phi: float) -> float:
        ex, ey = math.cos(phi), math.sin(phi)
        return ey if elbow_in else ex * sg
    phi = max(cands, key=score)
    E = (S[0] + a * math.cos(phi), S[1] + a * math.sin(phi))
    psi = math.atan2(target[1] - E[1], target[0] - E[0])
    phi0 = math.atan2(E0[1] - S[1], E0[0] - S[0])
    psi0 = math.atan2(W0[1] - E0[1], W0[0] - E0[0])
    r_up = math.degrees(phi - phi0)
    r_low = math.degrees(psi - psi0) - r_up
    need = math.dist(E, target)
    sy = max(0.9, min(stretch, (need - h) / f))
    norm = lambda r: (r + 180) % 360 - 180  # noqa: E731
    return {f"arm_{s}_up": {"r": round(norm(r_up), 2)}, f"arm_{s}_low": {"r": round(norm(r_low), 2), "sy": round(sy, 3)}}


def make_poses(g: Geo) -> dict[str, dict]:
    """Pose tĩnh lưu trong character.json["poses"] (dùng với render_figure(pose=...) hoặc ghi đè xương khi dựng).

    hand_over_mouth  — tay phải che miệng (sốc / khóc nấc) · hands_over_mouth — hai tay che miệng
    hand_to_ear      — tay phải áp tai (nghe điện thoại / lắng nghe) · hands_raised — hai tay giơ ngang đầu (hoảng)
    Khi dùng: bật slot hand_* = "open".
    """
    mouth = (g.mx, g.my + g.ry * 0.17)
    out: dict[str, dict] = {}
    out["hand_over_mouth"] = {"bones": _arm_ik(g, "r", mouth), "slots": {"hand_r": "open"}}
    both = dict(_arm_ik(g, "r", (g.mx + g.rx * 0.18, g.my + g.ry * 0.17)))
    both.update(_arm_ik(g, "l", (g.mx - g.rx * 0.22, g.my + g.ry * 0.22)))
    out["hands_over_mouth"] = {"bones": both, "slots": {"hand_r": "open", "hand_l": "open"}}
    out["hand_to_ear"] = {"bones": _arm_ik(g, "r", g.P(1.02, 0.25), elbow_in=False, stretch=1.05),
                          "slots": {"hand_r": "open"}}
    up = dict(_arm_ik(g, "r", g.P(1.85, -0.2), elbow_in=False, stretch=1.0))
    up.update(_arm_ik(g, "l", g.P(-1.85, -0.2), elbow_in=False, stretch=1.0))
    out["hands_raised"] = {"bones": up, "slots": {"hand_r": "open", "hand_l": "open"}}
    return out


def pose_bones(cid: str, name: str, root: Path = CHARACTERS) -> dict:
    """Đọc pose `name` từ character.json -> dict bone -> {r, sy} (truyền vào render_figure(pose=...))."""
    try:
        data = json.loads((Path(root) / cid / "character.json").read_text(encoding="utf-8"))
        return dict((data.get("poses") or {}).get(name, {}).get("bones") or {})
    except (OSError, ValueError):
        return {}


# ======================================================================= render tĩnh (preview / ảnh thẻ / sheet)
def expression_slots(rig, expression: str = "neutral", view: str = "front", mouth: str | None = None) -> dict[str, str]:
    ex = rig.expressions.get(expression) or rig.expressions.get("neutral") or {}
    slots = {"eyes": ex.get("eyes", "open"), "brows": ex.get("brows", "neutral"),
             "mouth": mouth or ex.get("mouth", "X"), "view": view}
    for f in ex.get("fx") or []:
        slots[f"fx_{f}"] = "on"
    return slots


def render_figure(cid: str, expression: str = "neutral", view: str = "front", height_px: int = 760,
                  crop: str = "full", bg: str | None = None, root: Path = CHARACTERS, mouth: str | None = None,
                  pose: dict | None = None) -> skia.Image:
    """Vẽ nhân vật tĩnh (pose nghỉ). crop: full | bust (đầu + vai) | head."""
    from .rig import BonePose, Rig
    rig = Rig.load(cid, Path(root))
    if rig is None:
        raise FileNotFoundError(f"Không có nhân vật {cid}")
    cw = 600.0
    l, t, r, b = rig.head_box or (150, 60, 450, 300)
    hh = b - t
    if crop == "head":
        box = (l - hh * 0.35, t - hh * 0.3, r + hh * 0.35, b + hh * 0.25)
    elif crop == "bust":
        box = ((l + r) / 2 - hh * 1.05, t - hh * 0.28, (l + r) / 2 + hh * 1.05, b + hh * 1.25)
    else:
        # khung cố định theo người lớn (~1000 đơn vị) để trẻ em / thực thể cao giữ đúng tỉ lệ khi so sánh
        box = (0.0, min(t - 0.08 * hh, rig.height - 965), cw, rig.height + 8)
    bw, bh = box[2] - box[0], box[3] - box[1]
    k = height_px / bh
    wpx = max(1, int(round(bw * k)))
    surf = skia.Surface(wpx, int(height_px))
    c = surf.getCanvas()
    c.clear(color(bg) if bg else skia.ColorTRANSPARENT)
    base = skia.Matrix.Scale(k, k)
    base.preTranslate(-box[0], -box[1])
    pz = {n: BonePose(**v) for n, v in (pose or {}).items()}
    rig.draw(c, base, pz, expression_slots(rig, expression, view, mouth))
    return surf.makeImageSnapshot()


def render_portrait(cid: str, size: tuple[int, int] = (600, 760), expression: str = "neutral",
                    bg: str | None = "#e9e6df", root: Path = CHARACTERS) -> skia.Image:
    """Ảnh thẻ chân dung (đầu + vai) cỡ `size`, nền nhạt (missing_poster). bg=None -> nền trong suốt."""
    W_, H_ = int(size[0]), int(size[1])
    img = render_figure(cid, expression, "front", height_px=H_, crop="bust", bg=None, root=root)
    surf = skia.Surface(W_, H_)
    c = surf.getCanvas()
    c.clear(color(bg) if bg else skia.ColorTRANSPARENT)
    s = max(W_ / img.width(), H_ / img.height())
    dw, dh = img.width() * s, img.height() * s
    c.drawImageRect(img, skia.Rect.MakeXYWH((W_ - dw) / 2, H_ - dh, dw, dh),
                    skia.SamplingOptions(skia.FilterMode.kLinear, skia.MipmapMode.kNone))
    return surf.makeImageSnapshot()


# ======================================================================= tay POV to (cận cảnh)
def render_hand(kind: str = "open", sleeve: str = "#1f6f5c", skin: str = "#e9b994", scale: float = 1.0) -> skia.Image:
    """Tay POV kiểu "ma-nơ-canh gỗ": ngón capsule nối khớp tròn, móng sáng, nếp đốt; ống tay áo ở đáy.

    Ảnh RGBA ~ (900×1400)·scale, cổ tay ở đáy giữa, ngón hướng lên. kind: open | point | pinch | hold | grip.
    """
    skin = _hex(skin, "#e9b994")
    sleeve = _hex(sleeve, "#1f6f5c")
    Wd, Hd = int(900 * scale), int(1400 * scale)
    surf = skia.Surface(Wd, Hd)
    c = surf.getCanvas()
    c.clear(skia.ColorTRANSPARENT)
    c.scale(scale, scale)
    dk = mul(skin, 0.7)
    nail = lit(skin, 0.55)
    cx = 450.0
    palm_top, palm_bot = 640.0, 1060.0
    pw = 330.0

    def finger(x0: float, y0: float, ang: float, segs: list[float], w: float, curl: float = 0.0) -> None:
        """Ngón tay: chuỗi capsule; ang = góc (độ, 0 = thẳng lên), curl = gập thêm mỗi đốt."""
        x, y = x0, y0
        a = ang
        pts = [(x, y)]
        for i, L in enumerate(segs):
            r = math.radians(a)
            nx, ny = x + math.sin(r) * L, y - math.cos(r) * L
            ww = w * (1 - 0.08 * i)
            flat(c, capsule(x, y, nx, ny, ww, ww * 0.94), skin, d=ww * 0.16, rim=0.28, hl=0.15, bottom=0)
            pts.append((nx, ny))
            x, y = nx, ny
            a += curl
        for (px, py) in pts[1:-1]:   # khớp tròn + nếp đốt
            c.drawPath(circle(px, py, w * 0.5), paint(skin))
            seam(c, [(px - w * 0.25, py + 2), (px + w * 0.25, py + 2)], dk, 3.0, 0.6, curve=False)
        # móng
        r = math.radians(a - curl)
        tx, ty = pts[-1]
        bx, by = tx - math.sin(r) * w * 0.55, ty + math.cos(r) * w * 0.55
        m = skia.Matrix.RotateDeg(a - curl, skia.Point(bx, by))
        nl = rrect(bx - w * 0.3, by - w * 0.42, bx + w * 0.3, by + w * 0.18, w * 0.22)
        nl.transform(m)
        c.drawPath(nl, paint(nail))
        c.drawPath(nl, pen(mul(skin, 0.85), 2.0, 0.6))

    # ống tay áo
    slv = rrect(cx - 230, 1120, cx + 230, 1460, 40)
    flat(c, slv, sleeve, d=60, rim=0.35, edge=0.4)
    c.drawPath(rrect(cx - 235, 1110, cx + 235, 1170, 24), paint(mul(sleeve, 0.85)))
    wrist = rrect(cx - 150, 980, cx + 150, 1140, 60)
    flat(c, wrist, skin, d=40, rim=0.3, bottom=0)
    palm = smooth([(cx - pw / 2, palm_top + 40), (cx - pw * 0.25, palm_top), (cx + pw * 0.25, palm_top),
                   (cx + pw / 2, palm_top + 50), (cx + pw * 0.52, palm_bot - 80), (cx + pw * 0.3, palm_bot),
                   (cx - pw * 0.3, palm_bot), (cx - pw * 0.52, palm_bot - 80)], tension=0.4)
    xs = [cx - pw * 0.36, cx - pw * 0.12, cx + pw * 0.12, cx + pw * 0.36]
    fw = 74.0
    if kind == "open":
        for i, x in enumerate(xs):
            finger(x, palm_top + 30, (-12, -4, 4, 12)[i], [150, 110, 80][:3] if i in (1, 2) else [130, 95, 70], fw)
        flat(c, palm, skin, d=60, rim=0.3, bottom=0)
        finger(cx - pw * 0.48, palm_bot - 150, -58, [120, 95], fw * 1.08, 12)
    elif kind == "point":
        flat(c, palm, skin, d=60, rim=0.3, bottom=0)
        finger(xs[0], palm_top + 30, -6, [150, 110, 80], fw)
        for i, x in enumerate(xs[1:]):  # ngón gập: đốt ngắn quặp xuống
            kx, ky = x, palm_top + 20
            c.drawPath(circle(kx, ky, fw * 0.55), paint(mul(skin, 0.95)))
            flat(c, capsule(kx, ky, kx + 6, ky + 95, fw, fw * 0.95), skin, d=12, rim=0.25, bottom=0)
            seam(c, [(kx - 20, ky + 40), (kx + 20, ky + 40)], dk, 3, 0.6, curve=False)
        finger(cx - pw * 0.5, palm_bot - 160, -40, [110, 80], fw * 1.08, 30)
    elif kind == "pinch":
        flat(c, palm, skin, d=60, rim=0.3, bottom=0)
        for i, x in enumerate(xs[1:]):   # 3 ngón gập nhẹ
            finger(x, palm_top + 30, 4 + i * 5, [105, 70, 50], fw, -24)
        finger(xs[0], palm_top + 30, -4, [125, 85, 55], fw, -38)       # ngón trỏ cong về ngón cái
        finger(cx - pw * 0.5, palm_bot - 170, -12, [130, 105], fw * 1.08, 34)  # ngón cái hướng lên chạm trỏ
    elif kind == "hold":   # cầm mép giấy/điện thoại: ngón hơi cong, ngón cái phía trước
        for i, x in enumerate(xs):
            finger(x, palm_top + 30, (-8, -3, 3, 8)[i], [130, 95, 60], fw, -10)
        flat(c, palm, skin, d=60, rim=0.3, bottom=0)
        finger(cx - pw * 0.45, palm_bot - 130, -22, [140, 120], fw * 1.12, 8)
    else:  # grip: nắm (bám mép quầy) — hàng đốt ngón quặp trên đỉnh
        flat(c, palm, skin, d=60, rim=0.3, bottom=0)
        for i, x in enumerate(xs):
            ky = palm_top + 10 + abs(i - 1.5) * 12
            flat(c, capsule(x, ky - 50, x, ky + 70, fw, fw), skin, d=12, rim=0.25, bottom=0)
            c.drawPath(circle(x, ky - 50, fw * 0.5), paint(lit(skin, 0.08)))
            seam(c, [(x - 22, ky + 10), (x + 22, ky + 10)], dk, 3, 0.6, curve=False)
            nl = rrect(x - 22, ky + 40, x + 22, ky + 78, 14)
            c.drawPath(nl, paint(nail))
        finger(cx - pw * 0.5, palm_bot - 150, -30, [120, 90], fw * 1.08, 25)
    # nếp lòng bàn tay
    seam(c, [(cx - pw * 0.3, palm_bot - 120), (cx, palm_bot - 90), (cx + pw * 0.3, palm_bot - 140)], dk, 3, 0.4)
    return surf.makeImageSnapshot()


__all__ = ["CharParams", "EXPRESSIONS", "HAIR_STYLES", "OUTFITS", "PRESETS", "make_character", "make_presets",
           "params_from_archetype", "make_archetype", "make_all_archetypes", "params_from_description",
           "render_figure", "render_portrait", "render_hand", "expression_slots"]
