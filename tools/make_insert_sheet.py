"""Contact sheet of every image in assets/inserts -> logs/asset_review/inserts_sheet.png (for visual review).

    python -X utf8 tools/make_insert_sheet.py [--preview id ...] [--library] [--out PATH]

--preview renders the given insert kinds fresh at low resolution (no files written to assets/) so a generator
change can be checked before regenerating the 4K PNGs.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import skia  # noqa: E402

from storytoon.paths import INSERTS  # noqa: E402
from storytoon.render import insertgen  # noqa: E402
from storytoon.render.skutil import font, load_image, save_png  # noqa: E402

TW, TH, LAB, COLS = 960, 540, 28, 3


def sheet(items: list[tuple[str, skia.Image]], out: Path) -> Path:
    rows = (len(items) + COLS - 1) // COLS
    surf = skia.Surface(TW * COLS, (TH + LAB) * rows)
    c = surf.getCanvas()
    c.clear(skia.ColorWHITE)
    f = font(20, "semibold")
    samp = skia.SamplingOptions(skia.FilterMode.kLinear, skia.MipmapMode.kNone)
    for i, (name, img) in enumerate(items):
        x, y = (i % COLS) * TW, (i // COLS) * (TH + LAB)
        c.drawString(name, x + 8, y + 21, f, skia.Paint(Color=skia.ColorBLACK, AntiAlias=True))
        c.drawImageRect(img, skia.Rect.MakeXYWH(x, y + LAB, TW, TH), samp)
    out.parent.mkdir(parents=True, exist_ok=True)
    save_png(surf.makeImageSnapshot(), out)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", nargs="*")
    ap.add_argument("--library", action="store_true",
                    help="only the library (batch-2, procedural_library) inserts listed in the catalog")
    ap.add_argument("--out", type=Path, default=ROOT / "logs" / "asset_review" / "inserts_sheet.png")
    a = ap.parse_args()
    lib = [e["id"] for e in insertgen._catalog().get("inserts", []) if e.get("library")] if a.library else None
    if a.preview is not None:
        kinds = a.preview or lib or list(insertgen.INSERTS)
        items = [(k, insertgen.render_insert(k, None, (TW, TH))) for k in kinds]
    else:
        items = []
        pngs = sorted(Path(INSERTS).glob("*.png"))
        if lib is not None:
            pngs = [Path(INSERTS) / f"{i}.png" for i in lib]
        for png in pngs:
            img = load_image(png)
            if img is not None:
                items.append((png.stem, img))
    print(sheet(items, a.out))


if __name__ == "__main__":
    main()
