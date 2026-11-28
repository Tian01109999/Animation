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


def _batch4_hud_shots(an, Overlay, Shot) -> list:
    """HUD lô 4: timer_hud, hex_warning, time_place (info_card + data.variant)."""
    return [
        (Shot(id="hud_timer_hud", location="hem", framing="medium", duration=3, characters=[an],
              overlays=[Overlay(kind="info_card", title="", data={"variant": "timer_hud", "name": "SUBJECT 01",
                                                                    "timer": "23:41:07", "sub": "TIME LEFT"})]),
         [0.15, 1.0, 2.6]),
        (Shot(id="hud_timer_hud_tr", location="cho", framing="medium", duration=2, characters=[an],
              overlays=[Overlay(kind="info_card", title="J.K.", subtitle="ZONE A - TOMORROW 09:13",
                                data={"variant": "timer_hud", "timer": "00:00:05", "position": "tr"})]), [1.5]),
        (Shot(id="hud_hex_warning", location="hem", framing="wide", duration=3, characters=[an],
              overlays=[Overlay(kind="info_card", title="LOCKDOWN", data={"variant": "hex_warning", "number": "2",
                                                                            "seconds": 30})]), [0.2, 1.4, 2.8]),
        (Shot(id="hud_hex_warning_tl", location="cho", framing="medium", duration=2, characters=[an],
              overlays=[Overlay(kind="info_card", title="", data={"variant": "hex_warning", "position": "tl",
                                                                    "seconds": 5})]), [1.0]),
        (Shot(id="hud_time_place", location="hem", framing="medium", duration=3, characters=[an],
              overlays=[Overlay(kind="info_card", title="FRIDAY NIGHT", subtitle="ZONE A - PHONE MALL",
                                data={"variant": "time_place", "time": "21:12:50"})]), [0.2, 1.2, 2.8]),
        (Shot(id="hud_time_place_combo", location="cho", framing="medium", duration=2, characters=[an],
              overlays=[Overlay(kind="info_card", title="", data={"variant": "time_place", "position": "bl"}),
                        Overlay(kind="info_card", title="", data={"variant": "timer_hud"})]), [1.2]),
    ]


def overlay_frames(out_dir: Path, batch: int = 3) -> list[Path]:
    """Khung thử HUD lô 3 (hoặc lô 4: batch=4) (info_card + data.variant) trên nền/puppet mẫu -> out_dir/*.png."""
    from storytoon.render.compositor import ShotRenderer
    from storytoon.render.skutil import save_png
    from storytoon.schema import CharacterDef, CharacterInShot, LocationDef, Overlay, Shot, Storyboard
    chars = [CharacterDef(id="an", name="An", role="", gender="male", age="young", asset_id="toi")]
    locs = [LocationDef(id="hem", name="Alley", time_of_day="night", asset_id="hem_toi"),
            LocationDef(id="cho", name="Market", time_of_day="night", asset_id="cho_dem")]
    an = CharacterInShot(id="an", slot="center")
    shots = _batch4_hud_shots(an, Overlay, Shot) if batch == 4 else [
        (Shot(id="hud_knot_counter", location="hem", framing="medium", duration=3, characters=[an],
              overlays=[Overlay(kind="info_card", title="", data={"variant": "knot_counter", "total": 5, "left": 3,
                                                                    "from": 4, "change_at": 0.8})]), [0.4, 1.0, 2.5]),
        (Shot(id="hud_knot_counter_vi", location="cho", framing="medium", duration=2, characters=[an],
              overlays=[Overlay(kind="info_card", title="", subtitle="nút còn lại",
                                data={"variant": "knot_counter", "total": 5, "left": 1})]), [1.2]),
        (Shot(id="hud_countdown_center", location="hem", framing="wide", duration=3, characters=[an],
              overlays=[Overlay(kind="info_card", title="", data={"variant": "countdown", "start": 10, "end": 7})]),
         [0.5, 1.6, 2.8]),
        (Shot(id="hud_countdown_corner", location="cho", framing="medium", duration=2.5, characters=[an],
              overlays=[Overlay(kind="info_card", title="Trốn tìm", subtitle="giây còn lại",
                                data={"variant": "countdown", "start": 30, "end": 28, "position": "tr"})]), [1.2]),
        (Shot(id="hud_live_replay", location="hem", framing="medium", duration=3, characters=[an],
              overlays=[Overlay(kind="info_card", title="@night_rider_07",
                                data={"variant": "live_replay", "timestamp": "02:14:37", "progress": [0.32, 0.4]})]),
         [0.3, 1.5, 2.8]),
    ]
    sb = Storyboard(title="HUD review", characters=chars, locations=locs, shots=[s for s, _ in shots])
    out_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for shot, ts in shots:
        r = ShotRenderer(shot, sb, None, validate_assets=False)
        for t in ts:
            i = min(r.n - 1, int(round(t * r.fps)))
            r.frame(i)
            p = out_dir / f"{shot.id}_{i:03d}.png"
            save_png(r.target.rgb(), p)
            out.append(p)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", nargs="*")
    ap.add_argument("--library", action="store_true",
                    help="only the library (batch-2, procedural_library) inserts listed in the catalog")
    ap.add_argument("--batch3", action="store_true", help="only the batch-3 library inserts (insertgen_batch3)")
    ap.add_argument("--batch4", action="store_true",
                    help="only the batch-4 library inserts (insertgen_batch4); with --overlays: batch-4 HUD frames")
    ap.add_argument("--overlays", type=Path, metavar="DIR",
                    help="also render batch-3 (or batch-4 with --batch4) HUD overlay test frames into DIR")
    ap.add_argument("--out", type=Path, default=ROOT / "logs" / "asset_review" / "inserts_sheet.png")
    a = ap.parse_args()
    if a.overlays:
        for p in overlay_frames(a.overlays, 4 if a.batch4 else 3):
            print(p)
    lib = [e["id"] for e in insertgen._catalog().get("inserts", []) if e.get("library")] if a.library else None
    if a.batch3:
        from storytoon.render import insertgen_batch3
        lib = list(insertgen_batch3.INSERTS)
    if a.batch4:
        from storytoon.render import insertgen_batch4
        lib = list(insertgen_batch4.INSERTS)
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
