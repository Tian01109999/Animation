"""Sinh thư viện địa điểm + ảnh chèn GỐC bằng code (gói B) và tờ xem nhanh (contact sheet).

Chạy:
  runtime\\venv\\Scripts\\python.exe -X utf8 tools\\make_location_library.py              (tất cả)
  ... --locations | --inserts | --sheets       (chỉ phần đó)
  ... --only cua_hang_loi_ke wall_clock        (chỉ các id này)
  ... --batch2 | --batch3 | --batch4           (chỉ lô 2 / 3 / 4 + logs/asset_review/batch{2,3,4}_locations.png)

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
BATCH3 = ["nha_ve_sinh_nu_truong", "lop_hoc_cu_dem", "truong_hoc_dem", "sanh_tu_giay_truong", "pho_dan_cu_may_ban_nuoc",
          "loi_di_dai_dem", "nha_tro_hai_tang", "phong_chieu_tatami", "bep_quan_mi", "phong_ngu_tv_cu"]
BATCH4 = ["tang_trung_tam_dien_thoai", "sanh_thang_cuon", "pho_nha_pho_dem", "ham_xe_b2", "quan_mi_xe_day_dem",
          "tiem_giat_24h", "trung_tam_du_lieu_dem", "phong_may_chu", "phong_dieu_khien_bao_dong", "tram_xe_buyt_binh_minh",
          "song_binh_minh_thanh_pho", "quan_net_cu"]
BATCH5 = ["phong_benh_chung_dem", "toa_benh_vien_mua_dem", "hanh_lang_tang4_benh_vien", "quay_truc_y_ta",
          "giuong_benh_canh_cua_so", "phong_tu_do_nhan_vien", "pantry_benh_vien", "san_nha_go_hoang_hon",
          "phong_truc_cu_radio"]
BATCH7 = ["xuong_thuyen_nha_san", "san_xuong_thuyen_hoang_hon", "tuong_thanh_gach_khoi", "cong_truong_dao_chan_tuong",
          "ham_gach_vom", "duong_ham_dot_mong", "phe_tich_cay_bo_de", "cho_ven_kenh_co", "chua_thap_prang",
          "san_lang_nha_san"]


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
    ap.add_argument("--batch3", action="store_true", help="chỉ vẽ 10 địa điểm lô 3 + logs/asset_review/batch3_locations.png")
    ap.add_argument("--batch4", action="store_true", help="chỉ vẽ 12 địa điểm lô 4 + logs/asset_review/batch4_locations.png")
    ap.add_argument("--batch5", action="store_true", help="chỉ vẽ 9 địa điểm lô 5 + logs/asset_review/batch5_locations.png")
    ap.add_argument("--batch7", action="store_true", help="chỉ vẽ 10 địa điểm lô 7 + logs/asset_review/batch7_locations.png")
    a = ap.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    if a.batch7:
        t = time.time()
        paths = locgen.make_catalog_locations(LOCATIONS, a.only or BATCH7)
        print(f"lô 7: {len(paths)} thư mục ({time.time() - t:.1f}s)")
        print("sheet:", batch_sheet(BATCH7, out=REVIEW / "batch7_locations.png"))
        return
    if a.batch5:
        t = time.time()
        paths = locgen.make_catalog_locations(LOCATIONS, a.only or BATCH5)
        print(f"lô 5: {len(paths)} thư mục ({time.time() - t:.1f}s)")
        print("sheet:", batch_sheet(BATCH5, out=REVIEW / "batch5_locations.png"))
        return
    if a.batch2:
        t = time.time()
        paths = locgen.make_catalog_locations(LOCATIONS, a.only or BATCH2)
        print(f"lô 2: {len(paths)} thư mục ({time.time() - t:.1f}s)")
        print("sheet:", batch_sheet(BATCH2))
        return
    if a.batch3:
        t = time.time()
        paths = locgen.make_catalog_locations(LOCATIONS, a.only or BATCH3)
        print(f"lô 3: {len(paths)} thư mục ({time.time() - t:.1f}s)")
        print("sheet:", batch_sheet(BATCH3, out=REVIEW / "batch3_locations.png"))
        return
    if a.batch4:
        t = time.time()
        paths = locgen.make_catalog_locations(LOCATIONS, a.only or BATCH4)
        print(f"lô 4: {len(paths)} thư mục ({time.time() - t:.1f}s)")
        print("sheet:", batch_sheet(BATCH4, out=REVIEW / "batch4_locations.png"))
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
