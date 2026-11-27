"""Puppet rig: đọc character.json, forward kinematics trên cây xương, vẽ lên canvas skia bằng ma trận.

Pose = dict[bone] -> BonePose(r, x, y, sx, sy). Góc tính bằng độ (dương = theo chiều kim đồng hồ trên màn hình).
Scale của một xương KHÔNG truyền xuống xương con (chỉ dời vị trí pivot của con) — để 'sit' co đùi mà ống chân
không bị bẹp.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import skia

from ..paths import CHARACTERS
from .skutil import SAMPLING, load_image

log = logging.getLogger("storytoon.render")


@dataclass
class BonePose:
    r: float = 0.0
    x: float = 0.0
    y: float = 0.0
    sx: float = 1.0
    sy: float = 1.0


Pose = dict[str, BonePose]


@dataclass
class Part:
    name: str
    bone: str
    offset: tuple[float, float]
    images: dict[str, skia.Image]
    slot: str | None = None
    default: str = "default"
    z: float = 0.0
    view: str | None = None      # None = mọi góc nhìn; "front" / "back" = chỉ vẽ ở góc đó


@dataclass
class Bone:
    name: str
    parent: str | None
    pivot: tuple[float, float]


def _T(x: float, y: float) -> skia.Matrix:
    return skia.Matrix.Translate(x, y)


def _cat(*ms: skia.Matrix) -> skia.Matrix:
    out = ms[0]
    for m in ms[1:]:
        out = skia.Matrix.Concat(out, m)
    return out


@dataclass
class Rig:
    id: str
    bones: dict[str, Bone]
    order: list[str]
    parts: list[Part]
    expressions: dict[str, dict[str, str]]
    image_scale: float = 1.0
    height: float = 1000.0
    head_box: tuple[float, float, float, float] | None = None
    hand_prop_anchor: dict | None = None
    slot_states: dict[str, list[str]] = field(default_factory=dict)
    uploaded: bool = False
    views: tuple[str, ...] = ("front",)

    @property
    def has_back(self) -> bool:
        return "back" in self.views

    # ------------------------------------------------------------ load
    @staticmethod
    def load(cid: str, root: Path = CHARACTERS) -> "Rig | None":
        d = Path(root) / cid
        try:   # khoá cache theo mtime: puppet tạo/sửa sau lần nạp đầu (UI chạy lâu) vẫn được nạp lại
            stamp = (d / "character.json").stat().st_mtime_ns
        except OSError:
            stamp = 0
        return _load_cached(str(d), stamp)

    @property
    def root_pivot(self) -> tuple[float, float]:
        return self.bones["root"].pivot if "root" in self.bones else (300.0, 1000.0)

    def head_center(self) -> tuple[float, float]:
        if self.head_box:
            l, t, r, b = self.head_box
            return (l + r) / 2, (t + b) / 2
        hb = self.bones.get("head")
        return (hb.pivot[0], hb.pivot[1] - 90) if hb else (300.0, 150.0)

    def head_top(self) -> float:
        return self.head_box[1] if self.head_box else 60.0

    def upload(self, backend) -> None:
        """Đưa ảnh bộ phận lên GPU (có mipmap) 1 lần cho cả tiến trình. backend: render.backend.Backend."""
        if self.uploaded or not getattr(backend, "gpu", False):
            return
        for part in self.parts:
            part.images = {k: backend.texture(im, mipmaps=True) for k, im in part.images.items()}
        self.uploaded = True

    # ------------------------------------------------------------ FK
    def solve(self, pose: Pose) -> tuple[dict[str, skia.Matrix], dict[str, skia.Matrix]]:
        """Trả về (ma trận xương, ma trận vẽ bộ phận) trong hệ toạ độ canvas nhân vật."""
        bm: dict[str, skia.Matrix] = {}
        pm: dict[str, skia.Matrix] = {}
        ident = BonePose()
        for name in self.order:
            b = self.bones[name]
            bp = pose.get(name, ident)
            px, py = b.pivot
            if b.parent and b.parent in bm:
                parent_m = bm[b.parent]
                pp = pose.get(b.parent, ident)
                if pp.sx != 1.0 or pp.sy != 1.0:
                    ppx, ppy = self.bones[b.parent].pivot
                    parent_m = _cat(parent_m, _T((px - ppx) * (pp.sx - 1), (py - ppy) * (pp.sy - 1)))
            else:
                parent_m = skia.Matrix()
            m = _cat(parent_m, _T(px + bp.x, py + bp.y), skia.Matrix.RotateDeg(bp.r), _T(-px, -py))
            bm[name] = m
            if bp.sx != 1.0 or bp.sy != 1.0:
                pm[name] = _cat(m, _T(px, py), skia.Matrix.Scale(bp.sx, bp.sy), _T(-px, -py))
            else:
                pm[name] = m
        return bm, pm

    def point(self, bone_m: dict[str, skia.Matrix], bone: str, pt: tuple[float, float]) -> tuple[float, float]:
        m = bone_m.get(bone)
        if m is None:
            return pt
        p = m.mapXY(pt[0], pt[1])
        return p.x(), p.y()

    # ------------------------------------------------------------ draw
    def draw(self, canvas: skia.Canvas, base: skia.Matrix, pose: Pose, slots: dict[str, str],
             paint: skia.Paint | None = None, part_m: dict[str, skia.Matrix] | None = None,
             view: str | None = None) -> None:
        """Vẽ puppet. `base` = ma trận từ canvas nhân vật -> canvas đích. `slots` = {'eyes': 'open', ...}.

        `view` ("front" | "back" | "side"; mặc định lấy `slots['view']`, rồi "front"): bộ phận có khoá `view`
        chỉ vẽ ở góc nhìn đó. Puppet không có ảnh sau lưng -> vẽ mặt trước. "side" v1 = mặt trước.
        Slot có `default` không nằm trong `images` (vd FX "off") -> ẩn khi không bật.
        """
        if part_m is None:
            _, part_m = self.solve(pose)
        v = view or slots.get("view") or "front"
        if v != "back" or not self.has_back:
            v = "front"
        inv = 1.0 / self.image_scale
        for part in self.parts:
            if part.view and part.view != v:
                continue
            if part.slot:
                img = part.images.get(slots.get(part.slot, part.default)) or part.images.get(part.default)
            else:
                img = part.images.get("default")
            if img is None:
                continue
            m = part_m.get(part.bone)
            if m is None:
                continue
            canvas.save()
            canvas.concat(_cat(base, m, _T(*part.offset), skia.Matrix.Scale(inv, inv)))
            canvas.drawImage(img, 0, 0, SAMPLING, paint)
            canvas.restore()


@lru_cache(maxsize=64)
def _load_cached(dir_str: str, _stamp: int = 0) -> Rig | None:
    d = Path(dir_str)
    f = d / "character.json"
    if not f.exists():
        log.warning("Không tìm thấy nhân vật '%s' (%s) — bỏ qua", d.name, f)
        return None
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log.warning("character.json lỗi (%s): %s", f, e)
        return None
    bones: dict[str, Bone] = {}
    for name, b in (data.get("bones") or {}).items():
        bones[name] = Bone(name, b.get("parent"), tuple(b.get("pivot", (0, 0))))
    if "root" not in bones:
        bones["root"] = Bone("root", None, (data.get("canvas", [600, 1000])[0] / 2, data.get("height_px", 1000)))
    # thứ tự topo
    order: list[str] = []
    seen: set[str] = set()

    def visit(n: str, depth: int = 0) -> None:
        if n in seen or depth > 64:
            return
        p = bones[n].parent
        if p and p in bones:
            visit(p, depth + 1)
        elif p and p not in bones:
            bones[n].parent = "root"
            visit("root", depth + 1)
        seen.add(n)
        order.append(n)

    for n in bones:
        visit(n)

    parts: list[Part] = []
    slot_states: dict[str, list[str]] = {}
    for pd in data.get("parts", []):
        bone = pd.get("bone", "root")
        if bone not in bones:
            bone = "root"
        off = tuple(pd.get("offset", (0, 0)))
        if "images" in pd:
            imgs = {}
            for k, rel in pd["images"].items():
                im = load_image(d / rel)
                if im is not None:
                    imgs[k] = im.withDefaultMipmaps()
            if not imgs:
                continue
            slot = pd.get("slot") or pd.get("name") or bone
            if "default" in pd:   # khai báo rõ (vd FX: "off" = ẩn mặc định)
                default = str(pd["default"])
            else:
                default = {"eyes": "open", "brows": "neutral", "mouth": "X"}.get(slot) or next(iter(imgs))
                if default not in imgs:
                    default = next(iter(imgs))
            parts.append(Part(pd.get("name", slot), bone, off, imgs, slot, default, float(pd.get("z", 0)),
                              pd.get("view")))
            slot_states[slot] = list(imgs)
        elif "image" in pd:
            im = load_image(d / pd["image"])
            if im is None:
                continue
            parts.append(Part(pd.get("name", bone), bone, off, {"default": im.withDefaultMipmaps()},
                              z=float(pd.get("z", 0)), view=pd.get("view")))
    parts.sort(key=lambda p: p.z)  # sort ổn định: giữ thứ tự mảng khi z bằng nhau
    views = tuple(dict.fromkeys(["front"] + [p.view for p in parts if p.view]))
    return Rig(id=data.get("id", d.name), bones=bones, order=order, parts=parts,
               expressions=data.get("expressions") or {}, image_scale=float(data.get("image_scale", 1.0)),
               height=float(data.get("height_px", 1000)), head_box=tuple(data["head_box"]) if data.get("head_box") else None,
               hand_prop_anchor=data.get("hand_prop_anchor"), slot_states=slot_states, views=views)
