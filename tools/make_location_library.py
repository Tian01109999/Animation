"""Sinh thư viện địa điểm + ảnh chèn GỐC bằng code (gói B) và tờ xem nhanh (contact sheet).

Chạy:
  runtime\\venv\\Scripts\\python.exe -X utf8 tools\\make_location_library.py              (tất cả)
  ... --locations | --inserts | --sheets       (chỉ phần đó)
  ... --only cua_hang_loi_ke wall_clock        (chỉ các id này)

Ra:  assets/locations/<id>[__<biến thể>]/  (bg.png, bg_far/mid/near.png, location.json)
     assets/locations/<id>/                    (cảnh thư viện mở rộng locgen.LIBRARY_SCENES: provenance
                                                'procedural_library'; còn lại: flow_prompt chờ Google Flow)
     Mọi chữ vẽ vào ảnh / biển hiệu đều là tiếng Anh chung chung.
     assets/inserts/<id>.png + <id>.json
     logs/asset_review/locations_sheet.png, inserts_sheet.png
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import skia  # noqa: E402

from storytoon.paths import INSERTS, LOCATIONS, LOGS  # noqa: E402
from storytoon.render import insertgen, locgen  # noqa: E402
from storytoon.render.location import _load_location_cached  # noqa: E402
from storytoon.render.skutil import fill, font, load_image, nfc, save_png  # noqa: E402

REVIEW = LOGS / "asset_review"
TW, TH = 640, 360


def _cell(c, img: skia.Image | None, x: float, y: float, label: str, sub: str = "") -> None:
    c.drawRect(skia.Rect.MakeXYWH(x, y, TW, TH), fill("#202228"))
    if img is not None:
        c.drawImageRect(img, skia.Rect.MakeXYWH(x, y, TW, TH),
                        skia.SamplingOptions(skia.FilterMode.kLinear, skia.MipmapMode.kNone))
    c.drawString(nfc(label), x + 4, y + TH + 24, font(19, "bold"), fill("#f0f0f0"))
    if sub:
        c.drawString(nfc(sub), x + 4, y + TH + 46, font(15, "regular"), fill("#9aa0aa"))


def _sheet(items: list[tuple[skia.Image | None, str, str]], out: Path, cols: int = 4) -> Path:
    rows = (len(items) + cols - 1) // cols
    gap, lab = 16, 56
    W = cols * (TW + gap) + gap
    H = rows * (TH + lab + gap) + gap
    s = skia.Surface(W, H)
    c = s.getCanvas()
    c.clear(skia.ColorSetARGB(255, 14, 15, 18))
    for i, (img, label, sub) in enumerate(items):
        x = gap + (i % cols) * (TW + gap)
        y = gap + (i // cols) * (TH + lab + gap)
        _cell(c, img, x, y, label, sub)
    save_png(s.makeImageSnapshot(), out)
    return out


def location_thumb(folder: Path) -> skia.Image | None:
    """Ảnh ghép giống lúc render (qua location.py thật: lớp + chữ biển hiệu + tiền cảnh)."""
    try:
        loc = _load_location_cached(folder.name, str(folder.parent), int(time.time()))
    except Exception:  # noqa: BLE001
        return None
    s = skia.Surface(*loc.size)
    c = s.getCanvas()
    for im, _ in loc.layers + loc.near:
        c.drawImage(im, 0, 0)
    return s.makeImageSnapshot()


def locations_sheet(root: Path = LOCATIONS, out: Path = REVIEW / "locations_sheet.png") -> Path:
    """Mọi thư mục địa điểm trong thư viện (procedural, procedural_library, cũ) — ảnh ghép kèm chữ biển hiệu."""
    items = []
    for folder in sorted(p for p in Path(root).iterdir() if (p / "location.json").is_file()):
        try:
            meta = json.loads((folder / "location.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        kind = (meta.get("provenance") or {}).get("kind", "existing_library")
        ready = (folder / meta.get("bg", "bg.png")).is_file()
        thumb = location_thumb(folder) if ready else None
        items.append((thumb, folder.name, f"{meta.get('time_of_day', '?')} · {kind}" + ("" if ready else " · MISSING")))
    return _sheet(items, out, cols=6)


BATCH2 = ["bep_nha_hang", "kho_lanh", "san_thuong_binh_minh", "hem_nha_pho_dien", "phong_truong_cong_an", "phong_icu",
          "cho_co_mai", "phong_dieu_tra", "ben_go_nha_san", "tiem_tap_hoa_dem", "toa_an", "phong_ky_tuc_xa"]


def batch_sheet(ids: list[str], root: Path = LOCATIONS, out: Path = REVIEW / "batch2_locations.png") -> Path:
    """Tờ xem nhanh cho một lô địa điểm (mọi biến thể <id> / <id>__<tod> có trên đĩa)."""
    items = []
    for base in ids:
        for folder in sorted(p for p in Path(root).glob(f"{base}*") if p.name == base or p.name.startswith(base + "__")):
            meta = json.loads((folder / "location.json").read_text(encoding="utf-8"))
            items.append((location_thumb(folder), folder.name, f"{meta.get('time_of_day', '?')} · "
                          f"{(meta.get('provenance') or {}).get('kind', '?')}"))
    return _sheet(items, out, cols=4)


def inserts_sheet(root: Path = INSERTS, out: Path = REVIEW / "inserts_sheet.png") -> Path:
    items = []
    for e in insertgen._catalog().get("inserts", []):
        if e.get("procedural") and e["id"] in insertgen.INSERTS:
            items.append((load_image(root / f"{e['id']}.png"), e["id"], e.get("name_vi", "")))
    return _sheet(items, out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--locations", action="store_true")
    ap.add_argument("--inserts", action="store_true")
    ap.add_argument("--sheets", action="store_true")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--batch2", action="store_true", help="chỉ vẽ 12 địa điểm lô 2 + logs/asset_review/batch2_locations.png")
    a = ap.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    if a.batch2:
        t = time.time()
        paths = locgen.make_catalog_locations(LOCATIONS, a.only or BATCH2)
        print(f"lô 2: {len(paths)} thư mục ({time.time() - t:.1f}s)")
        print("sheet:", batch_sheet(BATCH2))
        return
    every = not (a.locations or a.inserts or a.sheets)
    if every or a.locations:
        t = time.time()
        paths = locgen.make_catalog_locations(LOCATIONS, a.only)
        print(f"địa điểm: {len(paths)} thư mục ({time.time() - t:.1f}s)")
    if every or a.inserts:
        t = time.time()
        paths = insertgen.make_catalog_inserts(INSERTS, a.only)
        print(f"ảnh chèn: {len(paths)} file ({time.time() - t:.1f}s)")
    if every or a.sheets:
        print("sheet:", locations_sheet(), inserts_sheet())


if __name__ == "__main__":
    main()
