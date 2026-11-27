"""Hiệu ứng theo shot (`Shot.effects`) và chuyển cảnh (`Shot.transition`) — docs/STYLE_GUIDE.md §10,
tham số mặc định: assets/catalog/effects.json.

Thứ tự trong compositor (mỗi frame):
    frame_transform (shake_light) -> nền -> pre_chars -> nhân vật -> lớp near -> post_chars (rain, fog)
    -> vignette -> post_grade (glow, cctv, blur_in/transition blur, flash, fade_white/black, transition màu)
    -> overlay chữ -> grain.

Mọi thứ dựng sẵn 1 lần/shot (ô mưa lặp, lớp sương, scanline, shader) rồi mỗi frame chỉ vẽ ảnh/shader trên GPU.
Các hiệu ứng cần đọc lại khung (cctv, blur, glow) chụp `surface.makeImageSnapshot()` (bản sao trên GPU, ~1 ms).

Chuyển cảnh không đổi thời lượng shot: `transition` của shot N = hiệu ứng ĐẦU shot N (nửa sau) + CUỐI shot N-1
(nửa đầu, compositor truyền `next_transition`) -> tổng số frame và đồng bộ tiếng giữ nguyên tuyệt đối.

Tên hiệu ứng có thể kèm tham số sau dấu ':' — vd "flash:1.2" (lóe ở giây 1.2), "fade_black:1.0" (dài 1 s),
"blur_in:1.5", "shake_light:8" (biên độ px), "rain:600" (số vệt), "fog:0.5" (độ đậm). Tên không biết -> bỏ qua.
"""
from __future__ import annotations

import json
import logging
import math
import random
from functools import lru_cache

import numpy as np
import skia

from ..paths import ASSETS
from ..schema import SHOT_EFFECTS
from .post import grain_frames, scanlines_image, vignette_image
from .skutil import color, fill, hex2rgb, stroke

log = logging.getLogger("storytoon.render")

LIN = skia.SamplingOptions(skia.FilterMode.kLinear)

_DEFAULTS = {
    "rain": {"streaks": 300, "angle_deg": 78, "length_px": [18, 42], "alpha": 0.25, "speed_px_s": 1400, "drops": 60,
             "darken": 0.08},
    "fog": {"layers": 3, "alpha": [0.15, 0.35], "speed_px_s": [10, 20], "color": "#dfe6ee"},
    "cctv": {"desaturate": 0.9, "tint": "#9aa8a4", "tint_amount": 0.25, "scanline_px": 2, "scanline_alpha": 0.08,
             "noise": 0.06, "fisheye_k": 0.08, "vignette": 0.9},
    "flash": {"at": 0.0, "dur": 0.25, "peak_alpha": 0.9, "color": "#ffffff"},
    "fade_white": {"dur": 0.6, "bloom": True, "color": "#ffffff"},
    "fade_black": {"dur": 0.5, "color": "#000000"},
    "blur_in": {"dur": 0.8, "sigma_from": 18, "sigma_to": 0},
    "glow": {"threshold": 0.8, "sigma": 12, "alpha": 0.5},
    "shake_light": {"amp_px": 4, "freq_hz": 12},
}
_TRANSITIONS = {"cut": {"dur": 0.0}, "fade": {"dur": 0.4, "via": "#000000"}, "blur": {"dur": 0.5, "sigma": 18},
                "white": {"dur": 0.3, "via": "#ffffff"}}


@lru_cache(maxsize=1)
def catalog() -> tuple[dict, dict]:
    """(shot_effects, transitions) từ assets/catalog/effects.json, trộn với mặc định."""
    eff = {k: dict(v) for k, v in _DEFAULTS.items()}
    tr = {k: dict(v) for k, v in _TRANSITIONS.items()}
    try:
        data = json.loads((ASSETS / "catalog" / "effects.json").read_text(encoding="utf-8"))
        for k, v in (data.get("shot_effects") or {}).items():
            eff.setdefault(k, {}).update(v.get("params") or {})
        for k, v in (data.get("transitions") or {}).items():
            tr.setdefault(k, {}).update({kk: vv for kk, vv in v.items() if kk != "notes"})
    except (OSError, ValueError, AttributeError) as e:
        log.debug("Không đọc được catalog effects.json (%s) — dùng mặc định", e)
    return eff, tr


def parse_effects(names: list[str]) -> list[tuple[str, float | None]]:
    out: list[tuple[str, float | None]] = []
    for raw in names or []:
        name, _, arg = str(raw).strip().partition(":")
        name = name.strip().lower()
        if name not in SHOT_EFFECTS:
            log.warning("Hiệu ứng không biết '%s' — bỏ qua", raw)
            continue
        val = None
        if arg.strip():
            try:
                val = float(arg)
            except ValueError:
                log.warning("Tham số hiệu ứng '%s' không phải số — bỏ qua tham số", raw)
        out.append((name, val))
    return out


def smoothstep(u: float) -> float:
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


# ---------------------------------------------------------------- shader CCTV (fisheye + khử màu + ám teal)
_CCTV_SKSL = """
uniform shader img;
uniform float rx;
uniform float ry;
uniform float k;
uniform float desat;
uniform float tr;
uniform float tg;
uniform float tb;
uniform float tamt;
uniform float lift;
uniform float con;
half4 main(float2 p) {
    float2 res = float2(rx, ry);
    float2 uv = p / res * 2.0 - 1.0;
    float asp = rx / ry;
    float2 v = uv * float2(asp, 1.0);
    float r2 = dot(v, v) / (asp * asp + 1.0);
    float2 src = uv * (1.0 - k * (1.0 - r2));
    half4 c = img.eval((src + 1.0) * 0.5 * res);
    half l = dot(c.rgb, half3(0.2126, 0.7152, 0.0722));
    half3 g = mix(c.rgb, half3(l), half(desat));
    half3 tn = half3(tr, tg, tb);
    tn = tn / max(dot(tn, half3(0.2126, 0.7152, 0.0722)), 0.001);
    g = mix(g, g * tn, half(tamt));
    g = (g - 0.5) * half(con) + 0.5;
    g = g * (1.0 - half(lift)) + half(lift);
    return half4(clamp(g, 0.0, 1.0), 1.0);
}
"""


@lru_cache(maxsize=1)
def _cctv_effect() -> skia.RuntimeEffect | None:
    try:
        e = skia.RuntimeEffect.MakeForShader(_CCTV_SKSL)
        return e if isinstance(e, skia.RuntimeEffect) else getattr(e, "effect", None)
    except Exception as ex:  # noqa: BLE001
        log.warning("Không dựng được shader CCTV (%s) — dùng ma trận màu", ex)
        return None


# ---------------------------------------------------------------- tài nguyên dựng sẵn
def _rain_tile(T: int, n: int, angle_deg: float, len_px: tuple[float, float], alpha: float, width: float,
               seed: int) -> skia.Image:
    """Ô vuông T×T lặp liền mạch chứa n vệt mưa chéo (alpha thay đổi theo vệt)."""
    rng = random.Random(seed)
    s = skia.Surface(T, T)
    c = s.getCanvas()
    c.clear(skia.ColorTRANSPARENT)
    a = math.radians(angle_deg)
    dx, dy = math.cos(a), math.sin(a)
    for _ in range(n):
        x, y = rng.uniform(0, T), rng.uniform(0, T)
        L = rng.uniform(*len_px)
        p = skia.Paint(AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=width * rng.uniform(0.7, 1.3),
                       StrokeCap=skia.Paint.kRound_Cap)
        sh = skia.GradientShader.MakeLinear([skia.Point(x, y), skia.Point(x + dx * L, y + dy * L)],
                                            [color("#ffffff", 0.0), color("#eef4ff", alpha * rng.uniform(0.6, 1.4))])
        p.setShader(sh)
        for ox in (-T, 0, T):
            for oy in (-T, 0, T):
                if ox or oy:
                    if not (-L < x + ox < T + L and -L < y + oy < T + L):
                        continue
                c.save()
                c.translate(ox, oy)
                c.drawLine(x, y, x + dx * L, y + dy * L, p)
                c.restore()
    return s.makeImageSnapshot()


def _fog_tile(w: int, h: int, col: str, seed: int, band: tuple[float, float], density: int) -> skia.Image:
    """Lớp sương độ phân giải thấp (w×h), lặp ngang liền mạch, dày ở dưới."""
    rng = random.Random(seed)
    s = skia.Surface(w, h)
    c = s.getCanvas()
    c.clear(skia.ColorTRANSPARENT)
    for _ in range(density):
        y = h * rng.uniform(*band)
        x = rng.uniform(0, w)
        rx, ry = w * rng.uniform(0.08, 0.22), h * rng.uniform(0.05, 0.14)
        p = fill(col, rng.uniform(0.25, 0.6))
        p.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, ry * 0.7))
        for ox in (-w, 0, w):
            c.drawOval(skia.Rect.MakeLTRB(x + ox - rx, y - ry, x + ox + rx, y + ry), p)
    # nền sương đều ở đáy
    g = skia.GradientShader.MakeLinear([skia.Point(0, h * band[0]), skia.Point(0, h)],
                                       [color(col, 0.0), color(col, 0.55)])
    c.drawPaint(skia.Paint(Shader=g))
    return s.makeImageSnapshot()


class ShotEffects:
    """Trạng thái hiệu ứng của 1 shot. `active` = có gì phải vẽ không (không -> compositor bỏ qua toàn bộ)."""

    def __init__(self, names: list[str], transition: str, W: int, H: int, duration: float, seed: int, backend=None,
                 *, next_transition: str = "cut", end: float | None = None, fisheye: bool = True) -> None:
        self.W, self.H, self.duration, self.seed = W, H, duration, seed
        self.end = duration if end is None else end          # t của frame cuối
        self.be = backend
        self.k = H / 1080.0
        eff, trs = catalog()
        self.fx: dict[str, dict] = {}
        for name, val in parse_effects(names):
            p = dict(eff.get(name, {}))
            if val is not None:
                key = {"flash": "at", "fade_white": "dur", "fade_black": "dur", "blur_in": "dur",
                       "shake_light": "amp_px", "rain": "streaks", "fog": "strength", "glow": "alpha",
                       "cctv": "desaturate"}.get(name)
                if key:
                    p[key] = val
            self.fx[name] = p
        self.trans_in = transition if transition in trs else "cut"
        self.trans_out = next_transition if next_transition in trs else "cut"
        self.tr = trs
        self.fisheye = fisheye
        self.active = bool(self.fx) or self.trans_in != "cut" or self.trans_out != "cut"
        self.needs_surface = bool({"cctv", "blur_in", "glow", "fade_white"} & set(self.fx)) or \
            "blur" in (self.trans_in, self.trans_out)
        self._prepare()

    # ------------------------------------------------------------ dựng sẵn
    def _tex(self, img: skia.Image) -> skia.Image:
        return self.be.texture(img) if self.be is not None else img

    def _prepare(self) -> None:
        W, H, k = self.W, self.H, self.k
        if "rain" in self.fx:
            p = self.fx["rain"]
            T = max(64, int(0.5 * H))
            per_tile = float(p.get("streaks", 300)) * (T * T) / (1920 * 1080 * k * k)
            lo, hi = (p.get("length_px") or [18, 42])[:2]
            ang = float(p.get("angle_deg", 78))
            al = float(p.get("alpha", 0.25))
            self.rain = [   # (ảnh, tốc độ px/s, alpha lớp)
                (self._tex(_rain_tile(T, int(per_tile * 0.6), ang, (lo * k * 0.6, hi * k * 0.6), al * 0.8,
                                      1.0 * k, self.seed)), float(p.get("speed_px_s", 1400)) * k * 0.7, 1.0),
                (self._tex(_rain_tile(T, int(per_tile * 0.4), ang - 2, (lo * k * 1.2, hi * k * 1.4), al * 1.25,
                                      1.8 * k, self.seed + 1)), float(p.get("speed_px_s", 1400)) * k * 1.1, 1.0),
            ]
            self.rain_T = T
            self.rain_dir = (math.cos(math.radians(ang)), math.sin(math.radians(ang)))
        if "fog" in self.fx:
            p = self.fx["fog"]
            n = int(p.get("layers", 3) or 3)
            a0, a1 = (p.get("alpha") or [0.15, 0.35])[:2]
            v0, v1 = (p.get("speed_px_s") or [10, 20])[:2]
            strength = float(p.get("strength", 1.0))
            col = str(p.get("color", "#dfe6ee"))
            fw, fh = max(32, W // 4), max(18, H // 4)
            bands = [(0.55, 1.0), (0.4, 0.95), (0.7, 1.0), (0.3, 0.9)]
            self.fog = []
            for i in range(n):
                img = _fog_tile(fw, fh, col, self.seed + 11 * i, bands[i % len(bands)], 18 + 6 * i)
                a = (a0 + (a1 - a0) * (i / max(1, n - 1))) * strength
                v = (v0 + (v1 - v0) * (i / max(1, n - 1))) * k * (1 if i % 2 == 0 else -0.7)
                self.fog.append((self._tex(img), v, a))
        if "cctv" in self.fx:
            p = self.fx["cctv"]
            self.cctv_eff = _cctv_effect()
            self.scan = self._tex(scanlines_image(W, H, float(p.get("scanline_px", 2)),
                                                  float(p.get("scanline_alpha", 0.08))))
            self.noise = tuple(self._tex(g) for g in grain_frames(W, H, 6, self.seed % 1000 + 3))
            self.cctv_vig = self._tex(vignette_image(W, H, float(p.get("vignette", 0.9)), True))
        if "glow" in self.fx or ("fade_white" in self.fx and self.fx["fade_white"].get("bloom", True)):
            g = self.fx.get("glow", _DEFAULTS["glow"])
            thr = float(g.get("threshold", 0.8))
            kk = 1.0 / max(0.05, 1 - thr)
            self.glow_cf = skia.ColorFilters.Matrix([kk, 0, 0, 0, -thr * kk, 0, kk, 0, 0, -thr * kk,
                                                     0, 0, kk, 0, -thr * kk, 0, 0, 0, 1, 0])
            self.glow_small = None

    # ------------------------------------------------------------ API compositor
    def frame_transform(self, t: float) -> tuple[skia.Matrix | None, float]:
        """(ma trận rung nhẹ cho cảnh, σ blur toàn khung hiện tại)."""
        m = None
        if "shake_light" in self.fx:
            p = self.fx["shake_light"]
            amp = float(p.get("amp_px", 4)) * self.k
            f = float(p.get("freq_hz", 12))
            rng = random.Random(self.seed + 5)
            ph = [rng.uniform(0, math.tau) for _ in range(4)]
            dx = amp * (0.65 * math.sin(math.tau * f * t + ph[0]) + 0.35 * math.sin(math.tau * f * 1.73 * t + ph[1]))
            dy = amp * (0.65 * math.sin(math.tau * f * 0.91 * t + ph[2]) + 0.35 * math.sin(math.tau * f * 1.41 * t + ph[3]))
            s = 1.0 + 2.4 * amp / min(self.W, self.H)
            m = skia.Matrix.Translate(self.W / 2 + dx, self.H / 2 + dy)
            m.preScale(s, s)
            m.preTranslate(-self.W / 2, -self.H / 2)
        return m, self.blur_sigma(t)

    def blur_sigma(self, t: float) -> float:
        sig = 0.0
        if "blur_in" in self.fx:
            p = self.fx["blur_in"]
            d = float(p.get("dur", 0.8))
            s0, s1 = float(p.get("sigma_from", 18)), float(p.get("sigma_to", 0))
            if t < d:
                sig = max(sig, s0 + (s1 - s0) * smoothstep(t / d))
        if self.trans_in == "blur":
            d = float(self.tr["blur"].get("dur", 0.5)) / 2
            if t < d:
                sig = max(sig, float(self.tr["blur"].get("sigma", 18)) * (1 - smoothstep(t / d)))
        if self.trans_out == "blur":
            d = float(self.tr["blur"].get("dur", 0.5)) / 2
            u = (t - (self.end - d)) / max(1e-3, d)
            if u > 0:
                sig = max(sig, float(self.tr["blur"].get("sigma", 18)) * smoothstep(u))
        return sig * self.k

    def char_color_filter(self) -> skia.ColorFilter | None:
        """CCTV được áp ở bước post_grade cho cả khung -> không cần lọc riêng nhân vật."""
        return None

    def pre_chars(self, c: skia.Canvas, t: float) -> None:
        return None

    def post_chars(self, c: skia.Canvas, t: float, frame_index: int = 0) -> None:
        W, H = self.W, self.H
        if "fog" in self.fx:
            for img, v, a in self.fog:
                sx = W / img.width()
                sy = H / img.height()
                m = skia.Matrix.Scale(sx, sy)
                m.postTranslate((v * t) % W, 0)
                sh = img.makeShader(skia.TileMode.kRepeat, skia.TileMode.kClamp, LIN, m)
                c.drawRect(skia.Rect.MakeWH(W, H), skia.Paint(Shader=sh, Alphaf=min(1.0, a)))
        if "rain" in self.fx:
            p = self.fx["rain"]
            dk = float(p.get("darken", 0.08))
            if dk > 0:
                c.drawRect(skia.Rect.MakeWH(W, H), fill("#0a0f18", dk))
            dx, dy = self.rain_dir
            T = self.rain_T
            for img, v, a in self.rain:
                m = skia.Matrix.Translate((dx * v * t) % T, (dy * v * t) % T)
                sh = img.makeShader(skia.TileMode.kRepeat, skia.TileMode.kRepeat, LIN, m)
                c.drawRect(skia.Rect.MakeWH(W, H), skia.Paint(Shader=sh, Alphaf=a))
            # bắn nước trên mặt đất (đổi mỗi 2 frame)
            n = int(p.get("drops", 60))
            rng = random.Random(self.seed * 7919 + frame_index // 2)
            sp = stroke("#e8f0ff", 1.2 * self.k, 0.35)
            for _ in range(n):
                x = rng.uniform(0, W)
                y = rng.uniform(0.62, 1.0) * H
                r = rng.uniform(3, 9) * self.k * (0.6 + 0.6 * (y / H))
                c.drawArc(skia.Rect.MakeLTRB(x - r, y - r * 0.35, x + r, y + r * 0.35), 190, 160, False, sp)

    def _snapshot_draw(self, c: skia.Canvas, surface: skia.Surface, paint: skia.Paint) -> None:
        snap = surface.makeImageSnapshot()
        c.save()
        c.resetMatrix()
        c.drawImage(snap, 0, 0, LIN, paint)
        c.restore()

    def _glow(self, c: skia.Canvas, surface: skia.Surface, alpha: float, sigma: float) -> None:
        if alpha <= 0.003:
            return
        W, H = self.W, self.H
        if self.glow_small is None:
            mk = self.be.surface if self.be is not None else (lambda w, h: skia.Surface(w, h))
            self.glow_small = (mk(max(1, W // 4), max(1, H // 4)), mk(max(1, W // 4), max(1, H // 4)))
        a_s, b_s = self.glow_small
        snap = surface.makeImageSnapshot()
        ca = a_s.getCanvas()
        ca.clear(skia.ColorBLACK)
        ca.drawImageRect(snap, skia.Rect.MakeWH(W // 4, H // 4), LIN, skia.Paint(ColorFilter=self.glow_cf))
        cb = b_s.getCanvas()
        cb.clear(skia.ColorBLACK)
        sg = max(0.5, sigma * self.k / 4)
        cb.drawImage(a_s.makeImageSnapshot(), 0, 0, LIN,
                     skia.Paint(ImageFilter=skia.ImageFilters.Blur(sg, sg, skia.TileMode.kClamp, None)))
        c.save()
        c.resetMatrix()
        c.drawImageRect(b_s.makeImageSnapshot(), skia.Rect.MakeWH(W, H), LIN,
                        skia.Paint(BlendMode=skia.BlendMode.kScreen, Alphaf=min(1.0, alpha)))
        c.restore()

    def apply_cctv(self, c: skia.Canvas, surface: skia.Surface, t: float, frame_index: int = 0,
                   fisheye: bool | None = None) -> None:
        """Khử màu + ám teal + fisheye nhẹ (shader), scanline, nhiễu, vignette đậm."""
        if "cctv" not in self.fx:
            return
        W, H = self.W, self.H
        p = self.fx["cctv"]
        fe = self.fisheye if fisheye is None else fisheye
        eff = getattr(self, "cctv_eff", None)
        snap = surface.makeImageSnapshot()
        if eff is not None:
            tr, tg, tb = (v / 255 for v in hex2rgb(str(p.get("tint", "#9aa8a4"))))
            uni = np.array([W, H, float(p.get("fisheye_k", 0.08)) if fe else 0.0, float(p.get("desaturate", 0.9)),
                            tr, tg, tb, float(p.get("tint_amount", 0.25)), 0.035, 1.06], np.float32)
            child = snap.makeShader(skia.TileMode.kClamp, skia.TileMode.kClamp, LIN)
            try:
                shader = eff.makeShader(skia.Data.MakeWithCopy(uni.tobytes()), child, 1)
            except TypeError:
                shader = eff.makeShader(skia.Data.MakeWithCopy(uni.tobytes()), [child])
            c.save()
            c.resetMatrix()
            c.drawRect(skia.Rect.MakeWH(W, H), skia.Paint(Shader=shader))
            c.restore()
        else:
            from .post import cctv_matrix
            cf = skia.ColorFilters.Matrix(cctv_matrix(float(p.get("desaturate", 0.9)), str(p.get("tint", "#9aa8a4")),
                                                      float(p.get("tint_amount", 0.25))))
            self._snapshot_draw(c, surface, skia.Paint(ColorFilter=cf))
        c.save()
        c.resetMatrix()
        sh = self.scan.makeShader(skia.TileMode.kRepeat, skia.TileMode.kRepeat, skia.SamplingOptions())
        c.drawRect(skia.Rect.MakeWH(W, H), skia.Paint(Shader=sh))
        nz = self.noise[frame_index % len(self.noise)]
        c.drawImageRect(nz, skia.Rect.MakeWH(W, H), LIN,
                        skia.Paint(BlendMode=skia.BlendMode.kOverlay, Alphaf=min(1.0, float(p.get("noise", 0.06)) * 4)))
        c.drawImage(self.cctv_vig, 0, 0)
        c.restore()

    def post_grade(self, c: skia.Canvas, t: float, surface: skia.Surface | None = None, frame_index: int = 0,
                   *, skip_cctv: bool = False, fisheye: bool | None = None) -> None:
        W, H = self.W, self.H
        rect = skia.Rect.MakeWH(W, H)
        if surface is not None:
            if "glow" in self.fx:
                g = self.fx["glow"]
                self._glow(c, surface, float(g.get("alpha", 0.5)), float(g.get("sigma", 12)))
            if not skip_cctv:
                self.apply_cctv(c, surface, t, frame_index, fisheye)
            if "fade_white" in self.fx and self.fx["fade_white"].get("bloom", True):
                d = float(self.fx["fade_white"].get("dur", 0.6))
                u = (t - (self.end - d)) / max(1e-3, d)
                if u > 0:
                    self._glow(c, surface, 1.2 * smoothstep(u), 16)
            sig = self.blur_sigma(t)
            if sig > 0.3:
                self._snapshot_draw(c, surface, skia.Paint(
                    ImageFilter=skia.ImageFilters.Blur(sig, sig, skia.TileMode.kClamp, None)))
        # lóe trắng
        if "flash" in self.fx:
            p = self.fx["flash"]
            at, d = float(p.get("at", 0.0)), max(0.05, float(p.get("dur", 0.25)))
            u = (t - at) / d
            if 0 <= u <= 1:
                a = float(p.get("peak_alpha", 0.9)) * (u / 0.25 if u < 0.25 else (1 - u) / 0.75)
                c.drawRect(rect, fill(str(p.get("color", "#ffffff")), a))
        for name in ("fade_white", "fade_black"):
            if name in self.fx:
                p = self.fx[name]
                d = float(p.get("dur", 0.6 if name == "fade_white" else 0.5))
                u = (t - (self.end - d)) / max(1e-3, d)
                if u > 0:
                    c.drawRect(rect, fill(str(p.get("color", "#ffffff" if name == "fade_white" else "#000000")),
                                          smoothstep(u)))
        # chuyển cảnh màu (fade qua đen / white qua trắng): nửa đầu ở cuối shot trước, nửa sau ở đầu shot này
        for which, name in (("in", self.trans_in), ("out", self.trans_out)):
            if name not in ("fade", "white"):
                continue
            tp = self.tr[name]
            d = float(tp.get("dur", 0.4)) / 2
            via = str(tp.get("via", "#000000" if name == "fade" else "#ffffff"))
            if which == "in":
                u = 1 - t / max(1e-3, d)
            else:
                u = (t - (self.end - d)) / max(1e-3, d)
            if u > 0:
                c.drawRect(rect, fill(via, smoothstep(min(1.0, u))))
