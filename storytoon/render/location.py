"""Nạp địa điểm (nền + lớp parallax + slot + biển hiệu), ảnh chèn (insert:<id>) và nền dự phòng.

- Nền có thể chỉ là 1 ảnh bg.png phẳng (ảnh có sẵn trong kho) — lớp far/mid/near là tuỳ chọn.
- Biển hiệu (signs) được vẽ thành lớp chữ trên nền (không để AI vẽ chữ) và "nướng" vào ảnh nền 1 lần.
- Không bao giờ crash vì thiếu tài sản: thiếu -> nền gradient tối + cảnh báo.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import skia

from ..paths import INSERTS, LOCATIONS
from .skutil import color, fill, font, load_image, nfc, rrect, stroke

log = logging.getLogger("storytoon.render")

IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")
DEFAULT_SIZE = (3840, 2160)
# số px nền cho 1 đơn vị canvas nhân vật khi slot.scale = 1 (nhân vật cao ~930 đv -> ~740 px trên nền 2160)
CHAR_PX_PER_UNIT = 0.80


@dataclass
class Slot:
    x: float
    y: float
    scale: float = 1.0
    clip_bottom: float | None = None   # cắt phần nhân vật dưới y này (đứng sau quầy)


@dataclass
class LocationAsset:
    id: str
    size: tuple[int, int]
    layers: list[tuple[skia.Image, float]]          # (ảnh, hệ số parallax) — vẽ phía sau nhân vật
    near: list[tuple[skia.Image, float]] = field(default_factory=list)  # tiền cảnh, vẽ đè lên nhân vật
    slots: dict[str, Slot] = field(default_factory=dict)
    floor_y: float = 1880.0
    time_of_day: str = "day"
    char_px_per_unit: float = CHAR_PX_PER_UNIT
    is_insert: bool = False
    placeholder: bool = False

    def slot(self, name: str) -> Slot:
        if name in self.slots:
            return self.slots[name]
        dflt = default_slots(self.size, self.floor_y)
        if name in dflt:
            return self.slots.get(name) or dflt[name]
        log.warning("Địa điểm '%s' không có slot '%s' — dùng 'center'", self.id, name)
        return self.slots.get("center") or dflt["center"]


def default_slots(size: tuple[int, int], floor_y: float) -> dict[str, Slot]:
    bw, _ = size
    return {
        "far_left": Slot(bw * 0.12, floor_y - 30, 0.95),
        "left": Slot(bw * 0.28, floor_y, 1.0),
        "center": Slot(bw * 0.50, floor_y, 1.0),
        "right": Slot(bw * 0.72, floor_y, 1.0),
        "far_right": Slot(bw * 0.88, floor_y - 30, 0.95),
        "counter": Slot(bw * 0.60, floor_y - 120, 0.92),
    }


# ------------------------------------------------------------------ biển hiệu
SIGN_STYLES = {
    # nền bảng, viền, màu chữ, viền chữ
    "red_board": ("#b4221b", "#e8b84a", "#ffe08a", "#5a0d08"),
    "gold_board": ("#2a1d12", "#c99a3c", "#f0c766", "#120a05"),
    "cabinet": (None, None, "#fff3c8", "#6a0e0a"),
    "neon": (None, None, "#ff6b8a", "#3a0010"),
    "white_board": ("#efe9dc", "#5c5247", "#b3261e", "#00000000"),
    "plain": (None, None, "#f4eddf", "#1a1410"),
}


def draw_sign(c: skia.Canvas, text: str, box: list[float], style: str = "red_board") -> None:
    l, t, r, b = (float(v) for v in box)
    w, h = r - l, b - t
    bg, border, txt, outline = SIGN_STYLES.get(style, SIGN_STYLES["plain"])
    if bg:
        rad = min(h * 0.08, 18)
        c.drawPath(rrect(l, t, r, b, rad), fill(bg))
        if border:
            bw = max(3.0, h * 0.045)
            c.drawPath(rrect(l + bw * 1.4, t + bw * 1.4, r - bw * 1.4, b - bw * 1.4, rad * 0.6), stroke(border, bw))
        # bóng nhẹ dưới bảng
        sh = fill("#000000", 0.25)
        c.drawRect(skia.Rect.MakeLTRB(l + 6, b, r - 6, b + h * 0.05), sh)
    text = nfc(text)
    size = h * (0.56 if bg else 0.74)
    f = font(size, "extrabold")
    tw = f.measureText(text)
    maxw = w * (0.86 if bg else 0.96)
    if tw > maxw:
        size *= maxw / tw
        f = font(size, "extrabold")
        tw = f.measureText(text)
    x = l + (w - tw) / 2
    y = t + h / 2 + size * 0.36
    blob = skia.TextBlob.MakeFromString(text, f)
    if blob is None:
        return
    if style == "neon":
        glow = fill(txt, 0.8)
        glow.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, size * 0.18))
        c.drawTextBlob(blob, x, y, glow)
    if outline and len(outline) == 7:
        c.drawTextBlob(blob, x, y, stroke(outline, max(2.0, size * 0.10)))
    c.drawTextBlob(blob, x, y, fill(txt))


# ------------------------------------------------------------------ nạp
def _find_image(folder: Path, stem: str) -> Path | None:
    for ext in IMG_EXT:
        p = folder / f"{stem}{ext}"
        if p.exists():
            return p
    return None


@lru_cache(maxsize=16)
def _load_location_cached(lid: str, root: str, _stamp: int = 0) -> LocationAsset:
    folder = Path(root) / lid
    meta_f = folder / "location.json"
    meta: dict = {}
    if meta_f.exists():
        try:
            meta = json.loads(meta_f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            log.warning("location.json lỗi (%s): %s", meta_f, e)
    size = tuple(meta.get("size") or ())
    floor_y = float(meta.get("floor_y", 0) or 0)

    layers: list[tuple[skia.Image, float]] = []
    near: list[tuple[skia.Image, float]] = []
    lay_meta = meta.get("layers") or {}
    if "far" in lay_meta and "mid" in lay_meta:
        for k in ("far", "mid", "near"):
            lm = lay_meta.get(k)
            if not lm:
                continue
            im = load_image(folder / lm.get("image", f"bg_{k}.png"))
            if im is None:
                layers, near = [], []
                break
            (near if k == "near" else layers).append((im, float(lm.get("parallax", 1.0))))
    if not layers:
        near = []
        bgp = folder / meta.get("bg", "bg.png")
        if not bgp.exists():
            bgp = _find_image(folder, "bg") or bgp
        im = load_image(bgp) if bgp.exists() else None
        if im is not None:
            layers = [(im, 1.0)]
    placeholder = not layers
    if placeholder:
        raise FileNotFoundError(f"Không có nền trong kho: {lid}")
    if not size:
        size = (layers[0][0].width(), layers[0][0].height())
    size = (int(size[0]), int(size[1]))
    # ảnh nền khác kích thước khai báo -> co về size
    layers = [(_fit(im, size), p) for im, p in layers]
    near = [(_fit(im, size), p) for im, p in near]
    if not floor_y:
        floor_y = size[1] * 0.87
    # biển hiệu nướng vào lớp mid (lớp cuối của 'layers')
    signs = meta.get("signs") or []
    if signs:
        im, p = layers[-1]
        s = skia.Surface(size[0], size[1])
        c = s.getCanvas()
        c.clear(skia.ColorTRANSPARENT)
        c.drawImage(im, 0, 0)
        for sg in signs:
            if isinstance(sg, dict) and sg.get("text") and sg.get("box"):
                draw_sign(c, sg["text"], sg["box"], sg.get("style", "red_board"))
        layers[-1] = (s.makeImageSnapshot(), p)
    slots = default_slots(size, floor_y)
    for name, sd in (meta.get("slots") or {}).items():
        try:
            slots[name] = Slot(float(sd["x"]), float(sd["y"]), float(sd.get("scale", 1.0)),
                               float(sd["clip_bottom"]) if sd.get("clip_bottom") is not None else None)
        except (KeyError, TypeError, ValueError):
            log.warning("Slot '%s' của '%s' sai định dạng — bỏ qua", name, lid)
    return LocationAsset(id=lid, size=size, layers=layers, near=near, slots=slots, floor_y=floor_y,
                         time_of_day=meta.get("time_of_day", "day"),
                         char_px_per_unit=float(meta.get("char_px_per_unit", CHAR_PX_PER_UNIT)),
                         placeholder=placeholder)


def _fit(im: skia.Image, size: tuple[int, int]) -> skia.Image:
    if (im.width(), im.height()) == size:
        return im
    s = skia.Surface(size[0], size[1])
    s.getCanvas().drawImageRect(im, skia.Rect.MakeWH(*size),
                                skia.SamplingOptions(skia.FilterMode.kLinear, skia.MipmapMode.kLinear))
    return s.makeImageSnapshot()


@lru_cache(maxsize=16)
def _load_insert_cached(iid: str, roots: tuple[str, ...]) -> LocationAsset:
    img = None
    for r in roots:
        p = _find_image(Path(r), iid)
        if p:
            img = load_image(p)
            if img is not None:
                break
    placeholder = img is None
    if placeholder:
        raise FileNotFoundError(f"Không có ảnh chèn trong kho: {iid}")
    size = (img.width(), img.height())
    return LocationAsset(id=f"insert:{iid}", size=size, layers=[(img, 1.0)], floor_y=size[1] * 0.9,
                         time_of_day="neutral", is_insert=True, placeholder=placeholder,
                         slots=default_slots(size, size[1] * 0.9))


def load_location(location: str, project_dir: Path | None = None, time_of_day: str | None = None) -> LocationAsset:
    """`location` = id địa điểm hoặc 'insert:<id>'. Tìm trong project_dir/locations trước, rồi assets/locations."""
    if location.startswith("insert:"):
        iid = location.split(":", 1)[1].strip()
        roots = tuple(str(r) for r in ([project_dir / "inserts"] if project_dir else []) + [INSERTS])
        return _load_insert_cached(iid, roots)
    root = LOCATIONS
    if project_dir and (project_dir / "locations" / location / "location.json").exists():
        root = project_dir / "locations"
    try:   # khoá cache theo mtime: sửa location.json/ảnh nền khi UI đang chạy vẫn được nạp lại
        folder = root / location
        stamp = max([folder.stat().st_mtime_ns] + [f.stat().st_mtime_ns for f in folder.iterdir()])
    except OSError:
        stamp = 0
    loc = _load_location_cached(location, str(root), stamp)
    if time_of_day and loc.placeholder:
        loc.time_of_day = time_of_day
    return loc


def clear_caches() -> None:
    _load_location_cached.cache_clear()
    _load_insert_cached.cache_clear()
