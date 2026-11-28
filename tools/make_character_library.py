"""Sinh thư viện nhân vật gốc từ assets/catalog/archetypes.json (+ preset chu_tu/toi/co_lan) và ảnh duyệt.

Chạy:
  runtime\\venv\\Scripts\\python.exe -X utf8 tools\\make_character_library.py              # tạo tất cả + ảnh duyệt
  runtime\\venv\\Scripts\\python.exe -X utf8 tools\\make_character_library.py --only be_gai,bao_ve
  runtime\\venv\\Scripts\\python.exe -X utf8 tools\\make_character_library.py --sheets-only
  ... --out <thư mục>     (mặc định assets/characters)
  ... --batch2 / --batch3 / --batch4   chỉ tạo nhân vật lô đó + ảnh duyệt logs/asset_review/batchN_characters.png

Ảnh duyệt -> logs/asset_review/:
  characters_sheet.png         mọi nhân vật: chính diện + sau lưng + 3 biểu cảm cận
  characters_expressions.png   mỗi nhân vật 1 hàng: 12 biểu cảm (đầu)
  closeup_<n>.png              cận bán thân to (6 nhân vật × 6 biểu cảm) để soi chi tiết
  pov_hands.png, portraits.png tay POV + ảnh thẻ
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from storytoon.paths import CHARACTERS, FONTS, LOGS  # noqa: E402
from storytoon.render import puppetgen as pg  # noqa: E402
from storytoon.render.skutil import to_rgba  # noqa: E402

REVIEW = LOGS / "asset_review"
BG = (46, 48, 56)
CARD = (232, 229, 222)


def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    for name in (("BeVietnamPro-Bold.ttf",) if bold else ("BeVietnamPro-Regular.ttf",)):
        f = FONTS / name
        if f.exists():
            return ImageFont.truetype(str(f), size)
    for f in ("C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"):
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def pil(img) -> Image.Image:
    return Image.fromarray(to_rgba(img), "RGBA")


def ids_in(root: Path) -> list[str]:
    ids = [a["id"] for a in pg._load_catalog()] + list(pg.PRESETS)
    return [i for i in ids if (root / i / "character.json").exists()]


def build(root: Path, only: list[str] | None) -> list[str]:
    done = []
    for a in pg._load_catalog():
        if only and a["id"] not in only:
            continue
        t = time.time()
        pg.make_archetype(a["id"], root)
        done.append(a["id"])
        print(f"  {a['id']:<30} {time.time() - t:5.1f}s")
    for k in pg.PRESETS:
        if only and k not in only:
            continue
        t = time.time()
        pg.make_character(k, pg.PRESETS[k], root, meta=pg.PRESET_META.get(k))
        done.append(k)
        print(f"  {k:<30} {time.time() - t:5.1f}s (preset)")
    return done


def sheet_overview(root: Path, ids: list[str], out: Path) -> None:
    cols = 6
    tile_w, tile_h = 520, 700
    rows = (len(ids) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * tile_w, rows * tile_h), BG + (255,))
    f1, f2 = _font(22), _font(15, False)
    for i, cid in enumerate(ids):
        x0, y0 = (i % cols) * tile_w, (i // cols) * tile_h
        d = ImageDraw.Draw(sheet)
        d.rounded_rectangle((x0 + 6, y0 + 6, x0 + tile_w - 6, y0 + tile_h - 6), 14, fill=CARD + (255,))
        front = pil(pg.render_figure(cid, root=root, height_px=480))
        back = pil(pg.render_figure(cid, view="back", root=root, height_px=480))
        sheet.alpha_composite(front, (x0 + tile_w // 2 - front.width + 10, y0 + 40))
        sheet.alpha_composite(back, (x0 + tile_w // 2 + 10, y0 + 40))
        for j, ex in enumerate(("happy", "scared", "crying")):
            h = pil(pg.render_figure(cid, expression=ex, crop="head", root=root, height_px=150))
            sheet.alpha_composite(h, (x0 + 20 + j * 165 + (150 - h.width) // 2, y0 + 530))
        d = ImageDraw.Draw(sheet)
        d.text((x0 + 18, y0 + 12), cid, font=f1, fill=(30, 30, 36))
        try:
            import json
            prof = json.loads((root / cid / "character.json").read_text(encoding="utf-8")).get("profile", {})
            d.text((x0 + 18, y0 + tile_h - 30), f"{prof.get('gender')} · {prof.get('age')} · {prof.get('hair_style')} · "
                   f"{prof.get('outfit')}", font=f2, fill=(80, 80, 90))
        except Exception:  # noqa: BLE001
            pass
    sheet.convert("RGB").save(out)


def sheet_expressions(root: Path, ids: list[str], out: Path) -> None:
    exprs = list(pg.EXPRESSIONS)
    cell = 150
    lab = 240
    sheet = Image.new("RGBA", (lab + cell * len(exprs), 40 + cell * len(ids)), CARD + (255,))
    d = ImageDraw.Draw(sheet)
    f = _font(16)
    for j, ex in enumerate(exprs):
        d.text((lab + j * cell + 10, 10), ex, font=f, fill=(40, 40, 50))
    for i, cid in enumerate(ids):
        d.text((10, 40 + i * cell + cell // 2 - 10), cid, font=f, fill=(40, 40, 50))
        for j, ex in enumerate(exprs):
            h = pil(pg.render_figure(cid, expression=ex, crop="head", root=root, height_px=cell - 6))
            sheet.alpha_composite(h, (lab + j * cell + (cell - h.width) // 2, 40 + i * cell + 3))
    sheet.convert("RGB").save(out)


def sheet_closeups(root: Path, ids: list[str], out_dir: Path) -> list[Path]:
    exprs = ("neutral", "happy", "nervous", "shocked", "angry", "tired")
    per = 6
    outs = []
    f = _font(20)
    for n in range(0, len(ids), per):
        chunk = ids[n:n + per]
        cw, ch = 330, 360
        sheet = Image.new("RGBA", (cw * len(exprs), ch * len(chunk)), (70, 72, 82, 255))
        d = ImageDraw.Draw(sheet)
        for i, cid in enumerate(chunk):
            for j, ex in enumerate(exprs):
                im = pil(pg.render_figure(cid, expression=ex, crop="bust", root=root, height_px=ch - 10, bg="#d9d4ca"))
                im = im.crop((max(0, (im.width - cw + 6) // 2), 0, max(0, (im.width - cw + 6) // 2) + cw - 6, im.height))
                sheet.alpha_composite(im, (j * cw + 3, i * ch + 5))
                d.text((j * cw + 12, i * ch + 10), f"{cid} · {ex}", font=f, fill=(20, 20, 24))
        p = out_dir / f"closeup_{n // per + 1}.png"
        sheet.convert("RGB").save(p)
        outs.append(p)
    return outs


def sheet_hands(out: Path) -> None:
    kinds = ("open", "point", "pinch", "hold", "grip")
    ims = [pil(pg.render_hand(k, sleeve="#1f6f5c", skin="#c9926a", scale=0.4)) for k in kinds]
    ims += [pil(pg.render_hand(k, sleeve="#3a3d44", skin="#f1d3bd", scale=0.4)) for k in kinds]
    w, h = ims[0].size
    sheet = Image.new("RGBA", (w * 5, h * 2), (40, 40, 46, 255))
    for i, im in enumerate(ims):
        sheet.alpha_composite(im, ((i % 5) * w, (i // 5) * h))
    sheet.convert("RGB").save(out)


def sheet_portraits(root: Path, ids: list[str], out: Path) -> None:
    pw, ph = 200, 253
    cols = 9
    rows = (len(ids) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * (pw + 10) + 10, rows * (ph + 10) + 10), (30, 30, 34, 255))
    for i, cid in enumerate(ids):
        im = pil(pg.render_portrait(cid, (pw, ph), root=root))
        sheet.alpha_composite(im, (10 + (i % cols) * (pw + 10), 10 + (i // cols) * (ph + 10)))
    sheet.convert("RGB").save(out)


def library_ids(root: Path) -> list[str]:
    """Nhân vật thư viện mở rộng (archetype có "library": true) đã tạo."""
    return [a["id"] for a in pg._load_catalog() if a.get("library") and (root / a["id"] / "character.json").exists()]


BATCH3_SHEET_EXPRS = ("neutral", "happy", "scared", "crying", "cringe", "wide_grin", "slit_smile")
BATCH4_SHEET_EXPRS = ("neutral", "laugh", "angry_vein", "hurt", "nervous", "smirk", "determined")


def sheet_batch2(root: Path, ids: list[str], out: Path, exprs: tuple[str, ...] | None = None) -> None:
    """Mỗi nhân vật 1 hàng: chính diện, sau lưng, qua vai (bán thân sau lưng), pose che miệng, 7 biểu cảm cận."""
    exprs = exprs or ("neutral", "happy", "laughing", "crying", "pained", "shocked", "smirk")
    fh, bw, cell, lab = 430, 200, 165, 34
    pose_w = 220
    W_ = 2 * bw + 260 + pose_w + cell * len(exprs) + 30
    row_h = fh + lab + 16
    sheet = Image.new("RGBA", (W_, 50 + row_h * len(ids)), BG + (255,))
    d = ImageDraw.Draw(sheet)
    f1, f2 = _font(22), _font(15, False)
    heads = ["front", "back", "over-shoulder", "hand_over_mouth"] + list(exprs)
    xs = [10, 10 + bw, 10 + 2 * bw, 10 + 2 * bw + 260] + [10 + 2 * bw + 260 + pose_w + j * cell for j in range(len(exprs))]
    for x, h in zip(xs, heads):
        d.text((x + 8, 14), h, font=f2, fill=(220, 220, 228))
    for i, cid in enumerate(ids):
        y0 = 50 + i * row_h
        d.rounded_rectangle((4, y0, W_ - 4, y0 + row_h - 8), 14, fill=CARD + (255,))
        fr = pil(pg.render_figure(cid, root=root, height_px=fh))
        bk = pil(pg.render_figure(cid, view="back", root=root, height_px=fh))
        sheet.alpha_composite(fr.crop(((fr.width - bw) // 2, 0, (fr.width + bw) // 2, fr.height)), (xs[0], y0 + lab))
        sheet.alpha_composite(bk.crop(((bk.width - bw) // 2, 0, (bk.width + bw) // 2, bk.height)), (xs[1], y0 + lab))
        os_ = pil(pg.render_figure(cid, view="back", crop="bust", root=root, height_px=340, bg="#59606e"))
        os_ = os_.crop((max(0, (os_.width - 250) // 2), 0, max(0, (os_.width - 250) // 2) + 250, 340))
        sheet.alpha_composite(os_, (xs[2], y0 + lab + 10))
        pose = pg.pose_bones(cid, "hand_over_mouth", root)
        pm = pil(pg.render_figure(cid, expression="shocked", crop="bust", root=root, height_px=300, pose=pose))
        pm = pm.crop((max(0, (pm.width - pose_w) // 2), 0, max(0, (pm.width - pose_w) // 2) + pose_w, 300))
        sheet.alpha_composite(pm, (xs[3], y0 + lab + 40))
        for j, ex in enumerate(exprs):
            h = pil(pg.render_figure(cid, expression=ex, crop="head", root=root, height_px=cell - 8))
            sheet.alpha_composite(h, (xs[4 + j] + (cell - h.width) // 2, y0 + lab + 80))
        d = ImageDraw.Draw(sheet)
        try:
            import json
            prof = json.loads((root / cid / "character.json").read_text(encoding="utf-8")).get("profile", {})
            d.text((14, y0 + 6), f"{cid}  —  {prof.get('label', '')}", font=f1, fill=(30, 30, 36))
        except Exception:  # noqa: BLE001
            d.text((14, y0 + 6), cid, font=f1, fill=(30, 30, 36))
    sheet.convert("RGB").save(out)


def make_sheets(root: Path, ids: list[str] | None = None, out_dir: Path = REVIEW) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    ids = ids or ids_in(root)
    outs = [out_dir / "characters_sheet.png", out_dir / "characters_expressions.png", out_dir / "pov_hands.png",
            out_dir / "portraits.png"]
    sheet_overview(root, ids, outs[0])
    sheet_expressions(root, ids, outs[1])
    sheet_hands(outs[2])
    sheet_portraits(root, ids, outs[3])
    outs += sheet_closeups(root, ids, out_dir)
    return outs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="danh sách id, phân cách dấu phẩy")
    ap.add_argument("--out", default=str(CHARACTERS))
    ap.add_argument("--sheets-only", action="store_true")
    ap.add_argument("--no-sheets", action="store_true")
    ap.add_argument("--review-dir", default=str(REVIEW))
    ap.add_argument("--batch2", action="store_true",
                    help="chỉ nhân vật thư viện mở rộng (library: true) + ảnh duyệt batch2_characters.png")
    ap.add_argument("--batch3", action="store_true",
                    help="chỉ nhân vật lô 3 (batch: 3) + ảnh duyệt batch3_characters.png")
    ap.add_argument("--batch4", action="store_true",
                    help="chỉ nhân vật lô 4 (batch: 4) + ảnh duyệt batch4_characters.png")
    a = ap.parse_args()
    root = Path(a.out)
    only = [x.strip() for x in a.only.split(",") if x.strip()] or None
    if a.batch4:
        lib = [x["id"] for x in pg._load_catalog() if x.get("batch") == 4]
        only = [i for i in lib if not only or i in only]
        if not a.sheets_only:
            print("Tạo nhân vật lô 4 ->", root)
            build(root, only)
        out = Path(a.review_dir) / "batch4_characters.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        sheet_batch2(root, [i for i in library_ids(root) if i in only], out, BATCH4_SHEET_EXPRS)
        print("  ảnh duyệt:", out)
        return
    if a.batch3:
        lib = [x["id"] for x in pg._load_catalog() if x.get("batch") == 3]
        only = [i for i in lib if not only or i in only]
        if not a.sheets_only:
            print("Tạo nhân vật lô 3 ->", root)
            build(root, only)
        out = Path(a.review_dir) / "batch3_characters.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        sheet_batch2(root, [i for i in library_ids(root) if i in only], out, BATCH3_SHEET_EXPRS)
        print("  ảnh duyệt:", out)
        return
    if a.batch2:
        lib = [x["id"] for x in pg._load_catalog() if x.get("library") and x.get("batch") not in (3, 4)]
        only = [i for i in lib if not only or i in only]
        if not a.sheets_only:
            print("Tạo nhân vật thư viện mở rộng ->", root)
            build(root, only)
        out = Path(a.review_dir) / "batch2_characters.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        sheet_batch2(root, [i for i in library_ids(root) if i in only], out)
        print("  ảnh duyệt:", out)
        return
    if not a.sheets_only:
        print("Tạo nhân vật ->", root)
        build(root, only)
    if not a.no_sheets:
        ids = [i for i in ids_in(root) if not only or i in only]
        for p in make_sheets(root, ids, Path(a.review_dir)):
            print("  ảnh duyệt:", p)


if __name__ == "__main__":
    main()
