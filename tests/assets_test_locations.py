"""Gói B — kiểm thử địa điểm + ảnh chèn sinh bằng code.

Chạy:  runtime\\venv\\Scripts\\python.exe -X utf8 -m unittest tests.assets_test_locations -v
(Cần đã chạy tools/make_location_library.py để có thư viện trong assets/.)
"""
from __future__ import annotations

import json
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import skia  # noqa: E402

from storytoon import asset_library  # noqa: E402
from storytoon.paths import ASSETS, INSERTS, LOCATIONS  # noqa: E402
from storytoon.render import insertgen, locgen  # noqa: E402
from storytoon.render.location import clear_caches, load_location  # noqa: E402
from storytoon.render.skutil import load_image  # noqa: E402

W, H = 3840, 2160
CAT_LOC = json.loads((ASSETS / "catalog" / "locations.json").read_text(encoding="utf-8"))["locations"]
CAT_INS = json.loads((ASSETS / "catalog" / "inserts.json").read_text(encoding="utf-8"))["inserts"]
PROC_LOC = [e for e in CAT_LOC if e.get("procedural")]
PROC_INS = [e for e in CAT_INS if e.get("procedural")]


class TestLocationLibrary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        clear_caches()
        cls.cat = asset_library.catalog()
        cls.locs = {e["id"]: e for e in cls.cat["locations"]}
        cls.ins = {e["id"]: e for e in cls.cat["inserts"]}

    def test_all_procedural_ids_have_generators(self):
        self.assertEqual(len(PROC_LOC), 8)
        for e in PROC_LOC:
            self.assertIn(e["id"], locgen.SCENES, e["id"])

    def test_variants_ready_and_valid(self):
        n = 0
        for e in PROC_LOC:
            for aid, tod in locgen.variant_ids(e):
                n += 1
                with self.subTest(aid):
                    folder = LOCATIONS / aid
                    meta = json.loads((folder / "location.json").read_text(encoding="utf-8"))
                    self.assertEqual(meta["size"], [W, H])
                    self.assertIn(meta["time_of_day"], ("day", "night", "dusk", "indoor"))
                    self.assertEqual(meta["profile"]["catalog_id"], e["id"])
                    self.assertEqual(meta["provenance"]["kind"], "procedural")
                    entry = self.locs.get(aid)
                    self.assertIsNotNone(entry, "asset_library.catalog() không thấy")
                    self.assertTrue(entry["ready"])
                    self.assertEqual(entry["style"], "cutout")
                    bg = load_image(folder / "bg.png")
                    self.assertEqual((bg.width(), bg.height()), (W, H))
                    # slot nằm trong khung, có 'center'
                    self.assertIn("center", meta["slots"])
                    for name, sd in meta["slots"].items():
                        self.assertTrue(0 <= sd["x"] <= W and 0 < sd["y"] <= H, f"{name} ngoài khung: {sd}")
                        self.assertGreater(sd["scale"], 0)
                        if sd.get("clip_bottom") is not None:
                            self.assertLess(sd["clip_bottom"], sd["y"], name)
                    for sg in meta.get("signs", []):
                        l, t, r, b = sg["box"]
                        self.assertTrue(0 <= l < r <= W and 0 <= t < b <= H, sg)
                        self.assertEqual(sg["text"], unicodedata.normalize("NFC", sg["text"]))
                    # nạp qua renderer thật
                    loc = load_location(aid)
                    self.assertFalse(loc.placeholder)
                    self.assertEqual(loc.size, (W, H))
                    self.assertTrue(loc.layers)
        self.assertGreaterEqual(n, 18)

    def test_stub_locations_have_flow_prompt(self):
        for e in CAT_LOC:
            if e.get("procedural"):
                continue
            with self.subTest(e["id"]):
                meta = json.loads((LOCATIONS / e["id"] / "location.json").read_text(encoding="utf-8"))
                self.assertIn("flow_prompt", meta)
                self.assertIn("no text", meta["flow_prompt"])
                self.assertTrue(meta.get("flow_prompts"))
                self.assertTrue(meta["slots"])
                ready = (LOCATIONS / e["id"] / meta.get("bg", "bg.png")).is_file()
                self.assertEqual(self.locs[e["id"]]["ready"], ready)

    def test_inserts_ready(self):
        for e in PROC_INS:
            with self.subTest(e["id"]):
                self.assertIn(e["id"], insertgen.INSERTS)
                entry = self.ins.get(e["id"])
                self.assertIsNotNone(entry)
                self.assertEqual(entry["style"], "cutout")
                self.assertEqual(entry["provenance"]["kind"], "procedural")
                im = load_image(INSERTS / f"{e['id']}.png")
                self.assertEqual((im.width(), im.height()), (W, H))
                self.assertFalse(load_location(f"insert:{e['id']}").placeholder)


class TestGenerators(unittest.TestCase):
    def test_render_every_insert_small(self):
        for kind in insertgen.INSERTS:
            with self.subTest(kind):
                im = insertgen.render_insert(kind, None, (480, 270))
                self.assertEqual((im.width(), im.height()), (480, 270))

    def test_unknown_kind_and_bad_params_do_not_crash(self):
        im = insertgen.render_insert("khong_co", None, (160, 90))
        self.assertEqual(im.width(), 160)
        im = insertgen.render_insert("phone_chat", {"messages": [{"from": "me"}], "time": None}, (320, 180))
        self.assertEqual(im.width(), 320)

    def test_shared_draw_functions(self):
        s = skia.Surface(800, 600)
        c = s.getCanvas()
        r = skia.Rect.MakeXYWH(100, 50, 300, 500)
        for scr in ("chat", "lock", "bank"):
            insertgen.draw_phone(c, r, scr, {})
        insertgen.draw_phone(c, (100, 50, 400, 550), "chat", {"title": "Lan", "subtitle": "vừa xong",
                                                               "messages": [{"from": "them", "text": "Ai đó?"}]})
        insertgen.draw_paper_notebook(c, r, "LUẬT", ["Một *hai* ba", "Bốn"], red_index=1, redact_last=True,
                                      blurred=True)
        insertgen.draw_missing_poster(c, r, {"title": "NGUYỄN THỊ LAN", "subtitle": "19 tuổi", "variant": "torn"})
        insertgen.draw_missing_poster(c, r, {"photo": "blank", "variant": "crumpled"})
        insertgen.draw_map_card(c, skia.Rect.MakeXYWH(0, 0, 800, 500), {"title": "Bản đồ", "marker": {"x": 0.5, "y": 0.5, "label": "đây"}})

    def test_make_into_temp_dirs(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            png = insertgen.make_insert("dong_ho_4h", "wall_clock", {"hour": 4, "minute": 20}, td, size=(640, 360))
            self.assertTrue(png.is_file())
            meta = json.loads(png.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertEqual(meta["params"]["hour"], 4)
            self.assertEqual(meta["style"], "cutout")
            folder = locgen.make_location("nen_toi_truu_tuong__indoor", td)
            self.assertTrue((folder / "bg.png").is_file())
            meta = json.loads((folder / "location.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["time_of_day"], "indoor")
            stub = locgen.make_location("lop_hoc", td)
            self.assertFalse((stub / "bg.png").exists())
            self.assertEqual(json.loads((stub / "location.json").read_text(encoding="utf-8"))["status"], "needs_image")


if __name__ == "__main__":
    unittest.main(verbosity=2)
