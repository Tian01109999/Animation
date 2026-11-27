"""Dựng khung hình của 1 shot và xuất mp4; ghép cả phim.

Mỗi frame: [rung nhẹ] nền (lớp far/mid theo camera, đã nướng sẵn biển hiệu + chỉnh màu + blur cận cảnh)
-> nhân vật (theo slot, sắp theo chiều sâu; view back = sau gáy) -> tiền cảnh (near) -> nhân vật qua vai (mờ)
-> mưa/sương -> vignette -> [lưới CCTV 4 ô / split] -> hậu kỳ theo shot (glow, cctv, blur, lóe, fade, chuyển cảnh)
-> overlay chữ -> film grain.
Khung được vẽ thẳng vào 1 bộ đệm numpy (skia.Surface bọc mảng) rồi đẩy sang ffmpeg qua stdin.
Hiệu ứng/chuyển cảnh: storytoon/render/effects.py. Overlay: storytoon/render/overlays.py.
"""
from __future__ import annotations

import inspect
import json
import logging
import math
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

import numpy as np
import skia

from ..config import get
from ..paths import CHARACTERS
from ..schema import CharacterInShot, Shot, Storyboard
from .actions import Animator, seed_of
from .backend import FrameTarget, get_backend
from .camera import Rect, Subject, base_rect, camera_at, clamp_rect
from .effects import ShotEffects
from .encode import FrameWriter
from .location import LocationAsset, Slot, load_location
from .overlays import OverlaySet, build_overlays
from .post import PostFX, graded_paint, grade_filter
from .rig import Rig
from .skutil import SAMPLING, SAMPLING_FAST, color, save_png
from .timing import TimedLine, shot_duration, timed_lines

log = logging.getLogger("storytoon.render")

BLUR_SIGMA = {"wide": 0.0, "medium": 0.0, "close": 4.5, "extreme_close": 7.0}  # px khung đầu ra
# bộ phận mặt bị ẩn khi nhìn sau gáy mà puppet không có ảnh "back"
FACE_PARTS = {"face", "eyes", "mouth", "brows", "nose", "glasses", "eyebags", "blush", "beard", "mustache"}
GHOST_TAGS = {"ghost", "ma", "entity", "spirit", "hon_ma", "thuc_the"}
OVER_SHOULDER_SCALE = 1.8
OVER_SHOULDER_BLUR = 10.0       # σ px @1080p


@dataclass
class Actor:
    cis: CharacterInShot
    rig: Rig
    anim: Animator
    slot: Slot
    k: float          # px nền / đơn vị canvas nhân vật
    flip: float       # +1 nhìn phải, -1 nhìn trái
    subject: Subject
    over_shoulder: bool = False
    hair: str | None = None    # màu tóc (gáy khi view=back không có ảnh sau lưng); None = trọc/không rõ

    def base_matrix(self, dx_units: float) -> skia.Matrix:
        rx, ry = self.rig.root_pivot
        m = skia.Matrix.Translate(self.slot.x + dx_units * self.k * self.flip, self.slot.y)
        m.preScale(self.k * self.flip, self.k)
        m.preTranslate(-rx, -ry)
        return m


def _cam_matrix(r: Rect, W: int) -> skia.Matrix:
    s = W / r.w
    m = skia.Matrix.Scale(s, s)
    m.preTranslate(-r.x, -r.y)
    return m


def _is_face_part(name: str) -> bool:
    n = (name or "").lower()
    return n in FACE_PARTS or n.startswith("fx_") or n.startswith("eye") or n.startswith("mouth")


class ShotRenderer:
    """Trạng thái dựng sẵn của 1 shot. `frame(i)` trả về mảng RGBA (H, W, 4) — dùng lại cùng bộ đệm."""

    def __init__(self, shot: Shot, sb: Storyboard, project_dir: Path | None, *, width: int = 1920,
                 height: int = 1080, fps: int = 30, n_frames: int | None = None,
                 watermark: str | None = None, grain: float = 0.09, vignette: float = 0.72,
                 validate_assets: bool = True) -> None:
        self.shot, self.sb = shot, sb
        if validate_assets:
            from ..asset_library import validate
            validate(sb.model_copy(update={'shots': [shot]}))
        self.be = get_backend()
        self.W, self.H, self.fps = int(width), int(height), int(fps)
        self.duration = shot_duration(shot)
        self.n = n_frames if n_frames is not None else max(1, round(self.duration * fps))
        self.seed = seed_of(shot.id)
        ldef = sb.location(shot.location)
        location_id = (ldef.asset_id or shot.location) if ldef else shot.location
        self.loc: LocationAsset = load_location(location_id, None, ldef.time_of_day if ldef else None)
        self.tod = self.loc.time_of_day if not self.loc.is_insert else "neutral"
        if ldef and not self.loc.is_insert and ldef.time_of_day and self.loc.placeholder:
            self.tod = ldef.time_of_day
        self.tls: list[TimedLine] = timed_lines(shot)
        self.actors = [] if self.loc.is_insert else self._make_actors()
        self._mark_over_shoulder()
        self.scene_actors = [a for a in self.actors if not a.over_shoulder]
        self.os_actors = [a for a in self.actors if a.over_shoulder]
        self.focus = self._pick_focus()
        self.char_paint = graded_paint(self.tod, for_character=True)
        self.back_paint = skia.Paint(AntiAlias=True, ColorFilter=skia.ColorFilters.Compose(
            skia.ColorFilters.Matrix(_darken(0.5)), grade_filter(self.tod, True)))
        bw, bh = self.loc.size
        aspect = self.W / self.H
        if self.loc.is_insert:
            self.base = clamp_rect(_cover_rect(bw, bh, aspect), bw, bh)
            self.move = "push_in_slow" if shot.camera == "static" else shot.camera
        else:
            fx_frac = None
            if self.os_actors and self.focus is not None:
                fx_frac = 0.36 if self._os_side() > 0 else 0.64
            self.base = base_rect(shot.framing, bw, bh, aspect, [a.subject for a in self.scene_actors],
                                  self.focus.subject if self.focus else None, fx_frac)
            self.move = shot.camera
        if self.focus:
            self.anchor = (self.focus.subject.head_x, self.focus.subject.head_y)
        elif self.scene_actors:
            xs = [a.subject.head_x for a in self.scene_actors]
            self.anchor = ((min(xs) + max(xs)) / 2,
                           sum(a.subject.head_y for a in self.scene_actors) / len(self.scene_actors))
        else:
            self.anchor = None
        self.r0 = self.camera(0.0)
        # hiệu ứng + chuyển cảnh (chuyển cảnh của shot sau = phần đuôi shot này)
        idx = next((i for i, s in enumerate(sb.shots) if s.id == shot.id), None)
        nxt = sb.shots[idx + 1].transition if idx is not None and idx + 1 < len(sb.shots) else "cut"
        self.cctv_data: dict | None = None
        self._prepare_background()
        wm = watermark if watermark is not None else get("render.watermark", "StoryToon")
        self.overlays: OverlaySet = build_overlays(shot, sb, self.tls, self.duration, self.W, self.H,
                                                   self._nametag_anchor, watermark=wm or None, seed=self.seed)
        self.cctv_data = self.overlays.cctv
        self.grid = bool(self.cctv_data) and int(self.cctv_data.get("grid", 1) or 1) == 4
        self.split = isinstance((self.cctv_data or {}).get("split"), dict)
        self.fx = ShotEffects(shot.effects, shot.transition, self.W, self.H, self.duration, self.seed, self.be,
                              next_transition=nxt, end=(self.n - 1) / self.fps, fisheye=not self.grid)
        self.post = PostFX(self.W, self.H, self.tod if self.tod != "neutral" else "day", grain=grain,
                           vignette=vignette * (0.75 if self.loc.is_insert else 1.0))
        # đưa mọi ảnh dựng sẵn lên GPU 1 lần
        self.overlays.upload(self.be)
        if self.post.vig is not None:
            self.post.vig = self.be.texture(self.post.vig, cache=True)
        self.post.grain = tuple(self.be.texture(g, cache=True) for g in self.post.grain)
        self.target = FrameTarget(self.be, self.W, self.H)
        self.canvas = self.target.canvas
        self.shadow_paint = skia.Paint(AntiAlias=True, Color=skia.ColorSetARGB(120, 0, 0, 0),
                                       MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 14.0))
        self.badges = {}
        for b in self.overlays.badges:
            self.badges.setdefault(b.character_id, []).append(b)
        self.hidden_split = self._split_hidden() if self.split else set()
        self.cells = self._prepare_cells() if self.grid else []
        self.uses_surface = self.fx.needs_surface or self.grid or self.split or any(
            l.backdrop for l in self.overlays.layers)

    # ------------------------------------------------------------------ dựng
    def _make_actors(self) -> list[Actor]:
        out: list[Actor] = []
        used: dict[str, int] = {}
        for cis in self.shot.characters:
            definition = self.sb.character(cis.id)
            rig = Rig.load(definition.asset_id if definition and definition.asset_id else cis.id)
            if rig is None:
                raise FileNotFoundError(f"Shot {self.shot.id}: không đọc được asset nhân vật {cis.id}")
            slot = self.loc.slot(cis.slot)
            n = used.get(cis.slot, 0)
            used[cis.slot] = n + 1
            if n:  # hai nhân vật cùng slot -> xếp lệch nhau
                slot = Slot(slot.x + (1 if n % 2 else -1) * 260 * ((n + 1) // 2) * slot.scale, slot.y, slot.scale,
                            slot.clip_bottom)
            k = slot.scale * self.loc.char_px_per_unit
            flip = 1.0 if cis.facing == "right" else -1.0
            rx, ry = rig.root_pivot
            hx, hy = rig.head_center()
            subj = Subject(cis.id, slot.x, slot.y, slot.x + (hx - rx) * k * flip, slot.y + (hy - ry) * k,
                           slot.y + (rig.head_top() - ry) * k, rig.height * k, int(flip))
            rig.upload(self.be)
            anim = Animator(rig, cis, self.shot.id, self.tls, self.duration)
            hair = _hair_color(definition.asset_id if definition and definition.asset_id else cis.id) \
                if cis.view == "back" else None
            out.append(Actor(cis, rig, anim, slot, k, flip, subj, hair=hair))
        out.sort(key=lambda a: a.slot.y)  # xa (y nhỏ) vẽ trước
        return out

    def _mark_over_shoulder(self) -> None:
        """view='back' + framing không phải wide + có người đối diện (view≠back) -> tiền cảnh qua vai.
        `pose='over_shoulder'` ép chế độ này."""
        fronts = [a for a in self.actors if a.cis.view != "back"]
        for a in self.actors:
            if a.cis.pose == "over_shoulder" or (a.cis.view == "back" and self.shot.framing != "wide" and fronts):
                if len(self.actors) > 1:
                    a.over_shoulder = True

    def _os_side(self) -> float:
        """+1: người qua vai đặt bên phải khung; -1: bên trái (mặc định)."""
        if not self.os_actors:
            return -1.0
        a = self.os_actors[0]
        if self.focus is not None:
            return 1.0 if a.slot.x > self.focus.slot.x else -1.0
        return -1.0

    def _pick_focus(self) -> Actor | None:
        by_id = {a.cis.id: a for a in self.scene_actors}
        if self.shot.focus and self.shot.focus in by_id:
            return by_id[self.shot.focus]
        if self.shot.framing in ("close", "extreme_close", "medium"):
            for tl in self.tls:
                if tl.line.speaker in by_id:
                    return by_id[tl.line.speaker]
            if self.shot.framing != "medium" and self.scene_actors:
                return self.scene_actors[0]
            if self.os_actors and self.scene_actors:
                return self.scene_actors[0]
        return None

    def _split_hidden(self) -> set[str]:
        sp = (self.cctv_data or {}).get("split") or {}
        hide = sp.get("hide")
        if isinstance(hide, list):
            return {str(h) for h in hide}
        out = set()
        for a in self.actors:
            d = self.sb.character(a.cis.id)
            tags = {t.lower() for t in (d.tags if d else [])}
            arch = (d.archetype or "").lower() if d else ""
            if tags & GHOST_TAGS or "ghost" in arch or arch.startswith("ma_") or "entity" in arch:
                out.add(a.cis.id)
        if not out:
            log.info("Shot %s: split CCTV không có nhân vật ma (tags 'ghost' hoặc split.hide) — hai nửa như nhau",
                     self.shot.id)
        return out

    def _prepare_cells(self) -> list[tuple[skia.Image, skia.Rect]]:
        """Lưới CCTV 2×2: ô 1 = cảnh chính; ô 2-4 = plate tĩnh của location từng ô (mặc định = location shot)."""
        cells = (self.cctv_data or {}).get("cells") or []
        W2, H2 = self.W // 2, self.H // 2
        crops = [(0.5, 0.55, 0.7), (0.28, 0.6, 0.55), (0.72, 0.5, 0.6), (0.5, 0.42, 0.85)]
        out = []
        for i in range(1, 4):
            cell = cells[i] if i < len(cells) and isinstance(cells[i], dict) else {}
            lid = cell.get("location") or None
            try:
                if lid:
                    ldef = self.sb.location(lid)
                    loc = load_location((ldef.asset_id or lid) if ldef else lid, None,
                                        ldef.time_of_day if ldef else None)
                else:
                    loc = self.loc
            except FileNotFoundError as e:
                log.warning("Shot %s: ô CCTV %d thiếu nền (%s) — dùng nền shot", self.shot.id, i + 1, e)
                loc = self.loc
            bw, bh = loc.size
            ax, ay, fr = crops[i]
            if lid:
                ax, ay, fr = 0.5, 0.55, 0.9
            w = bw * fr
            h = w * self.H / self.W
            if h > bh:
                h = bh
                w = h * self.W / self.H
            r = clamp_rect(Rect(bw * ax - w / 2, bh * ay - h / 2, w, h), bw, bh)
            surf = self.be.surface(W2, H2)
            c = surf.getCanvas()
            c.clear(skia.ColorBLACK)
            tod = loc.time_of_day if not loc.is_insert else "neutral"
            for im, _par in loc.layers + loc.near:
                im = self.be.texture(im, mipmaps=True, cache=True)
                c.drawImageRect(im, skia.Rect.MakeXYWH(r.x, r.y, r.w, r.h), skia.Rect.MakeWH(W2, H2), SAMPLING,
                                graded_paint(tod), skia.Canvas.kFast_SrcRectConstraint)
            vig = self.be.texture(PostFX(W2, H2, "night", grain=0, vignette=0.8).vig)
            c.drawImage(vig, 0, 0)
            out.append((surf.makeImageSnapshot(), skia.Rect.MakeXYWH((i % 2) * W2, (i // 2) * H2, W2, H2)))
        return out

    def camera(self, t: float) -> Rect:
        bw, bh = self.loc.size
        return camera_at(self.move, self.base, t, self.duration, bw, bh, self.seed, self.anchor)

    def _prepare_background(self) -> None:
        """Co + blur + chỉnh màu các lớp nền 1 lần cho cả shot (vùng camera quét qua)."""
        bw, bh = self.loc.size
        samples = [self.camera(self.duration * i / 24) for i in range(25)]
        if self.move == "shake":
            samples += [self.camera(self.duration * i / 240) for i in range(241)]
        min_w = min(r.w for r in samples)
        self.static = self.move == "static"
        sigma_out = 0.0 if self.loc.is_insert else BLUR_SIGMA.get(self.shot.framing, 0.0)
        self.work: list[tuple[skia.Image, Rect, float, float]] = []   # (ảnh, vùng nền, scale, parallax)
        self.work_near: list[tuple[skia.Image, Rect, float, float]] = []
        r0 = self.r0
        for dst, layers in ((self.work, self.loc.layers), (self.work_near, self.loc.near)):
            for im, par in layers:
                rects = [self._par_rect(r, r0, par) for r in samples]
                x0 = max(0.0, min(r.x for r in rects) - 8)
                y0 = max(0.0, min(r.y for r in rects) - 8)
                x1 = min(float(bw), max(r.x + r.w for r in rects) + 8)
                y1 = min(float(bh), max(r.y + r.h for r in rects) + 8)
                region = Rect(x0, y0, x1 - x0, y1 - y0)
                s = min(1.0, self.W / max(1.0, min(r.w for r in rects)) * 1.0)
                sigma = sigma_out * (min_w * s) / self.W * (1.6 if dst is self.work_near else 1.0)
                dst.append((self._bake(im, region, s, sigma), region, s, par))
        if self.static:
            self.plate = self._render_layers(self.work, self.r0)
            self.plate_near = self._render_layers(self.work_near, self.r0) if self.work_near else None

    def _bake(self, im: skia.Image, region: Rect, s: float, sigma: float) -> skia.Image:
        w, h = max(1, math.ceil(region.w * s)), max(1, math.ceil(region.h * s))
        im = self.be.texture(im, mipmaps=True, cache=True)
        surf = self.be.surface(w, h)
        c = surf.getCanvas()
        c.clear(skia.ColorTRANSPARENT)
        p = graded_paint(self.tod)
        if sigma > 0.3:
            p.setImageFilter(skia.ImageFilters.Blur(sigma, sigma, skia.TileMode.kClamp, None))
        c.drawImageRect(im, skia.Rect.MakeXYWH(region.x, region.y, region.w, region.h), skia.Rect.MakeWH(w, h),
                        SAMPLING, p, skia.Canvas.kFast_SrcRectConstraint)
        return surf.makeImageSnapshot()

    @staticmethod
    def _par_rect(r: Rect, r0: Rect, par: float) -> Rect:
        if par == 1.0:
            return r
        return Rect(r0.x + (r.x - r0.x) * par, r0.y + (r.y - r0.y) * par, r0.w + (r.w - r0.w) * par,
                    r0.h + (r.h - r0.h) * par)

    def _draw_layers(self, c: skia.Canvas, layers: list[tuple[skia.Image, Rect, float, float]], r: Rect) -> None:
        r0 = self.r0
        dst = skia.Rect.MakeWH(self.W, self.H)
        for img, region, s, par in layers:
            pr = self._par_rect(r, r0, par)
            src = skia.Rect.MakeXYWH((pr.x - region.x) * s, (pr.y - region.y) * s, pr.w * s, pr.h * s)
            c.drawImageRect(img, src, dst, SAMPLING_FAST, None, skia.Canvas.kFast_SrcRectConstraint)

    def _render_layers(self, layers, r: Rect) -> skia.Image:
        surf = self.be.surface(self.W, self.H)
        c = surf.getCanvas()
        c.clear(skia.ColorTRANSPARENT)
        self._draw_layers(c, layers, r)
        return surf.makeImageSnapshot()

    # ------------------------------------------------------------------ overlay helpers
    def _nametag_anchor(self, cid: str, t: float, iw: int, ih: int) -> tuple[float, float] | None:
        a = next((x for x in self.scene_actors if x.cis.id == cid), None)
        if a is None:
            return None
        r = self.camera(t)
        s = self.W / r.w

        def walk_dx(x: Actor) -> float:  # nhân vật đang đi (walk) dịch root theo thời gian -> nametag đi theo đầu
            return x.anim.action.move_x_per_s * t * x.k * x.flip

        hx = (a.subject.head_x + walk_dx(a) - r.x) * s
        hy = (a.subject.head_y - r.y) * s
        head_w = (a.subject.height * 0.13) * s
        # cạnh đầu, ngang tầm cằm; chọn bên không đè lên nhân vật khác và còn chỗ trong khung
        mx = self.W * 0.02
        cands = [hx + head_w * 1.25, hx - head_w * 1.25 - iw]
        if hx >= self.W * 0.5:
            cands.reverse()
        others = [(o.subject.head_x + walk_dx(o) - r.x) * s for o in self.scene_actors if o is not a]

        def cost(x: float) -> float:
            out = max(0.0, mx - x) + max(0.0, x + iw - (self.W - mx))
            hit = sum(1.0 for ox in others if x - head_w < ox < x + iw + head_w)
            return out * 4 + hit * iw
        # chọn bên 1 lần cho cả shot (nhân vật đi -> không để thẻ nhảy bên giữa chừng)
        side_cache: dict[str, float] = self.__dict__.setdefault("_tag_side", {})
        if cid not in side_cache:
            best = min(cands, key=cost)  # min() ổn định: hoà thì giữ ứng viên đầu (phía giữa khung)
            side_cache[cid] = 1.0 if best > hx else -1.0
        x = hx + head_w * 1.25 if side_cache[cid] > 0 else hx - head_w * 1.25 - iw
        y = hy + head_w * 0.2 - ih / 2
        x = min(max(x, mx), self.W - iw - mx)
        y = min(max(y, self.H * 0.16), self.H * 0.72 - ih)
        return x, y

    # ------------------------------------------------------------------ vẽ
    def _draw_rig(self, c: skia.Canvas, a: Actor, base: skia.Matrix, st, paint: skia.Paint) -> None:
        """Vẽ puppet theo `cis.view`. back: dùng ảnh 'back' của puppet nếu có (hoặc Rig.draw(view=) của gói A),
        không có thì vẽ thân trước tối đi + ẩn mặt (bóng sau gáy)."""
        rig = a.rig
        if a.cis.view != "back":
            rig.draw(c, base, st.pose, st.slots, paint)
            return
        if getattr(rig, "has_back", False) and _rig_supports_view(rig):   # puppet có bộ phận view="back"
            rig.draw(c, base, st.pose, st.slots, paint, view="back")
            return
        has_back = any("back" in p.images for p in rig.parts)
        bpaint = paint if has_back else self._back_paint_for(paint)
        _, part_m = rig.solve(st.pose)
        inv = 1.0 / rig.image_scale
        for part in rig.parts:
            if getattr(part, "view", None) not in (None, "front"):
                continue
            img = part.images.get("back") if has_back else None
            if img is None:
                if _is_face_part(part.name) or _is_face_part(part.slot or ""):
                    continue
                if part.slot:
                    img = part.images.get(st.slots.get(part.slot, part.default)) or part.images.get(part.default)
                else:
                    img = part.images.get("default")
            if img is None:
                continue
            m = part_m.get(part.bone)
            if m is None:
                continue
            p = bpaint
            if not has_back and a.hair and (part.name or "").lower() == "head":
                # gáy: tô khối đầu bằng màu tóc (rồi làm tối như phần còn lại)
                p = skia.Paint(bpaint)
                p.setColorFilter(skia.ColorFilters.Compose(
                    bpaint.getColorFilter(), skia.ColorFilters.Blend(color(a.hair), skia.BlendMode.kSrcIn)))
            c.save()
            mm = skia.Matrix.Concat(base, m)
            mm.preTranslate(*part.offset)
            mm.preScale(inv, inv)
            c.concat(mm)
            c.drawImage(img, 0, 0, SAMPLING, p)
            c.restore()

    def _back_paint_for(self, paint: skia.Paint) -> skia.Paint:
        if paint is self.char_paint:
            return self.back_paint
        p = skia.Paint(paint)
        cf = paint.getColorFilter()
        dk = skia.ColorFilters.Matrix(_darken(0.5))
        p.setColorFilter(skia.ColorFilters.Compose(dk, cf) if cf is not None else dk)
        return p

    def _draw_badges(self, c: skia.Canvas, a: Actor, base: skia.Matrix, st) -> None:
        specs = self.badges.get(a.cis.id)
        if not specs or a.cis.view == "back":
            return
        rig = a.rig
        bm, _ = rig.solve(st.pose)
        torso = "torso" if "torso" in rig.bones else ("hip" if "hip" in rig.bones else "root")
        neck_b = rig.bones.get("neck") or rig.bones.get("head")
        neck_y = neck_b.pivot[1] if neck_b else rig.head_center()[1] + 90
        tor_y = rig.bones[torso].pivot[1]
        if tor_y <= neck_y + 10:
            tor_y = neck_y + rig.height * 0.18
        if rig.head_box:
            hl, _ht, hr, _hb = rig.head_box
            hw = hr - hl
        else:
            hw = rig.height * 0.17
        cx = rig.bones[torso].pivot[0]
        for i, b in enumerate(specs):
            bw = min(b.w_frac * rig.height, 0.5 * hw)
            bh = bw * b.h_frac / max(1e-3, b.w_frac)
            x = cx + 0.34 * hw
            y = neck_y + (tor_y - neck_y) * 0.42 + i * bh * 1.3
            m = skia.Matrix.Concat(base, bm.get(torso, skia.Matrix()))
            c.save()
            c.concat(m)
            c.drawImageRect(b.image, skia.Rect.MakeXYWH(x - bw / 2, y - bh / 2, bw, bh), SAMPLING, self.char_paint)
            c.restore()

    def _draw_actor(self, c: skia.Canvas, a: Actor, t: float, cam: skia.Matrix) -> None:
        st = a.anim.frame(t)
        base = skia.Matrix.Concat(cam, a.base_matrix(st.dx))
        c.save()
        c.concat(cam)
        if a.slot.clip_bottom is not None:
            c.clipRect(skia.Rect.MakeLTRB(-1e5, -1e5, 1e5, a.slot.clip_bottom), skia.ClipOp.kIntersect, True)
        else:  # bóng đổ dưới chân
            fx = a.slot.x + st.dx * a.k * a.flip
            w = 120 * a.k * (1.0 if not a.anim.action.sit else 1.3)
            self.shadow_paint.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 10 * a.k))
            c.drawOval(skia.Rect.MakeLTRB(fx - w, a.slot.y - 16 * a.k, fx + w, a.slot.y + 14 * a.k), self.shadow_paint)
        c.restore()
        c.save()
        if a.slot.clip_bottom is not None:
            c.concat(cam)
            c.clipRect(skia.Rect.MakeLTRB(-1e5, -1e5, 1e5, a.slot.clip_bottom), skia.ClipOp.kIntersect, True)
            c.resetMatrix()
        self._draw_rig(c, a, base, st, self.char_paint)
        if self.badges:
            self._draw_badges(c, a, base, st)
        c.restore()

    def _draw_over_shoulder(self, c: skia.Canvas, a: Actor, t: float, r: Rect, base_m: skia.Matrix | None) -> None:
        """Tiền cảnh qua vai: sau gáy, phóng to ×1.8 so với người đối diện, góc dưới, mờ σ≈10."""
        st = a.anim.frame(t)
        rig = a.rig
        side = self._os_side()
        if self.focus is not None:
            s = self.W / r.w * self.focus.k * OVER_SHOULDER_SCALE
        else:
            s = self.H * 1.4 / rig.height
        hx, hy = rig.head_center()
        tx = self.W * (0.83 if side > 0 else 0.17)
        ty = self.H * 0.66
        flip = -1.0 if side > 0 else 1.0       # quay mặt (lưng) về phía người đối diện
        m = skia.Matrix.Translate(tx, ty)
        m.preScale(s * flip, s)
        m.preTranslate(-hx, -hy)
        if base_m is not None:
            m = skia.Matrix.Concat(base_m, m)
        sig = OVER_SHOULDER_BLUR * self.H / 1080
        c.saveLayer(None, skia.Paint(ImageFilter=skia.ImageFilters.Blur(sig, sig, skia.TileMode.kDecal, None)))
        self._draw_rig(c, a, m, st, self.char_paint)
        c.restore()

    def _render_scene(self, c: skia.Canvas, t: float, frame_index: int, hide: set[str] | None = None) -> None:
        r = self.camera(t)
        shake_m, _ = self.fx.frame_transform(t) if self.fx.active else (None, 0.0)
        if shake_m is not None:
            c.clear(skia.ColorBLACK)
            c.save()
            c.concat(shake_m)
        if self.static:
            c.drawImage(self.plate, 0, 0)
        else:
            if shake_m is None:
                c.clear(skia.ColorBLACK)
            self._draw_layers(c, self.work, r)
        cam = _cam_matrix(r, self.W)
        if shake_m is not None:
            cam = skia.Matrix.Concat(shake_m, cam)
        if self.fx.active:
            self.fx.pre_chars(c, t)
        for a in self.scene_actors:
            if hide and a.cis.id in hide:
                continue
            if shake_m is not None:
                c.save()
                c.resetMatrix()
                self._draw_actor(c, a, t, cam)
                c.restore()
            else:
                self._draw_actor(c, a, t, cam)
        if self.work_near:
            if self.static and self.plate_near is not None:
                c.drawImage(self.plate_near, 0, 0)
            else:
                self._draw_layers(c, self.work_near, r)
        for a in self.os_actors:
            if hide and a.cis.id in hide:
                continue
            c.save()
            c.resetMatrix()
            self._draw_over_shoulder(c, a, t, r, shake_m)
            c.restore()
        if self.fx.active:
            self.fx.post_chars(c, t, frame_index)
        if shake_m is not None:
            c.restore()
        self.post.vignette(c)

    def render_at(self, t: float, frame_index: int = 0) -> np.ndarray:
        c = self.canvas
        surf = self.target.surface if self.uses_surface else None
        W, H = self.W, self.H
        if self.split:
            self._render_scene(c, t, frame_index)
            self.fx.apply_cctv(c, surf, t, frame_index)
            snap_a = surf.makeImageSnapshot()
            self._render_scene(c, t, frame_index, self.hidden_split)
            snap_b = surf.makeImageSnapshot()
            c.clear(skia.ColorBLACK)
            src = skia.Rect.MakeXYWH(W / 4, 0, W / 2, H)
            c.drawImageRect(snap_a, src, skia.Rect.MakeXYWH(0, 0, W / 2, H), SAMPLING_FAST, None,
                            skia.Canvas.kFast_SrcRectConstraint)
            c.drawImageRect(snap_b, src, skia.Rect.MakeXYWH(W / 2, 0, W / 2, H), SAMPLING_FAST, None,
                            skia.Canvas.kFast_SrcRectConstraint)
            if self.fx.active:
                self.fx.post_grade(c, t, surf, frame_index, skip_cctv=True)
        elif self.grid:
            self._render_scene(c, t, frame_index)
            snap = surf.makeImageSnapshot()
            c.clear(skia.ColorBLACK)
            c.drawImageRect(snap, skia.Rect.MakeWH(W, H), skia.Rect.MakeWH(W // 2, H // 2), SAMPLING, None,
                            skia.Canvas.kFast_SrcRectConstraint)
            for img, dst in self.cells:
                c.drawImage(img, dst.left(), dst.top())
            if self.fx.active:
                self.fx.post_grade(c, t, surf, frame_index)
            g = max(2.0, 4 * H / 1080)
            black = skia.Paint(Color=skia.ColorBLACK)
            c.drawRect(skia.Rect.MakeXYWH(W / 2 - g / 2, 0, g, H), black)
            c.drawRect(skia.Rect.MakeXYWH(0, H / 2 - g / 2, W, g), black)
        else:
            self._render_scene(c, t, frame_index)
            if self.fx.active:
                self.fx.post_grade(c, t, surf, frame_index)
        self.overlays.draw(c, t, surf)
        self.post.film_grain(c, frame_index + self.seed % 97)
        return self.target.read()

    def frame(self, i: int) -> np.ndarray:
        return self.render_at(i / self.fps, i)


def _darken(k: float) -> list[float]:
    """Ma trận làm tối (nhân k) + ám lạnh nhẹ — thân người nhìn từ sau, ngược sáng."""
    return [k * 0.95, 0, 0, 0, 0.0, 0, k * 0.98, 0, 0, 0.0, 0, 0, k * 1.06, 0, 0.0, 0, 0, 0, 1, 0]


@lru_cache(maxsize=64)
def _hair_color(asset_id: str) -> str | None:
    """Màu tóc từ character.json (generator.params / profile); None nếu trọc hoặc không rõ."""
    try:
        data = json.loads((CHARACTERS / asset_id / "character.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    params = (data.get("generator") or {}).get("params") or {}
    prof = data.get("profile") or {}
    style = str(params.get("hair_style") or prof.get("hair_style") or "")
    if style in ("bald", "none_entity"):
        return None
    col = params.get("hair_color") or prof.get("hair_color")
    return str(col) if isinstance(col, str) and col.startswith("#") else "#1c1b1f"


def _rig_supports_view(rig: Rig) -> bool:
    try:
        return "view" in inspect.signature(rig.draw).parameters
    except (TypeError, ValueError):
        return False


def _hex(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _cover_rect(bw: float, bh: float, aspect: float) -> Rect:
    if bw / bh > aspect:
        w = bh * aspect
        return Rect((bw - w) / 2, 0, w, bh)
    h = bw / aspect
    return Rect(0, (bh - h) / 2, bw, h)


# ====================================================================== API
def render_shot(shot: Shot, sb: Storyboard, project_dir: Path | None, out_mp4: Path, *, width: int = 1920,
                height: int = 1080, fps: int = 30, n_frames: int | None = None,
                progress: Callable[[int, int], None] | None = None, stills: dict[int, Path] | None = None,
                **kw) -> Path:
    """Render 1 shot ra mp4 (không tiếng). `stills` = {frame_index: png_path} để xuất thêm ảnh tĩnh."""
    t0 = time.perf_counter()
    r = ShotRenderer(shot, sb, Path(project_dir) if project_dir else None, width=width, height=height, fps=fps,
                     n_frames=n_frames, **kw)
    t_prep = time.perf_counter() - t0
    w = FrameWriter(Path(out_mp4), r.W, r.H, r.fps, pix_fmt=r.target.pix_fmt)
    try:
        for i in range(r.n):
            buf = r.frame(i)
            w.write(buf.tobytes())
            if stills and i in stills:
                save_png(r.target.rgb(), stills[i])
            if progress and (i % 15 == 0 or i == r.n - 1):
                progress(i + 1, r.n)
        w.close()
    except BaseException:
        w.abort()
        raise
    dt = time.perf_counter() - t0
    log.info("Shot %s: %d frame trong %.1fs (chuẩn bị %.2fs, %.1f fps, %s)", shot.id, r.n, dt, t_prep,
             r.n / max(1e-6, dt - t_prep), w.encoder)
    return Path(out_mp4)
