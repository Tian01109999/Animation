"""Kiểm tra renderer hỗ trợ MỌI tính năng mới của schema bằng ảnh tĩnh (1 khung / tính năng).

Xuất ảnh duyệt bằng mắt -> logs/asset_review/features/*.png:
  - mọi OverlayKind (cctv đơn / lưới 4 / split, phone_chat + màn khoá, phone_bank, missing_poster, map_card, timeline,
    info_card, job_ad, rule_list, rule_card, badge, nametag, location_card, chapter_card, time_card) với Overlay.data;
  - mọi Shot.effects (rain, fog, cctv, flash, fade_white, fade_black, blur_in, glow, shake_light);
  - mọi Shot.transition (fade, blur, white) — khung đầu shot sau;
  - CharacterInShot.view='back' (sau lưng + qua vai);
  - 5 biểu cảm mới (nervous/shocked/crying/tired/smirk) qua compositor + bảng tổng hợp trên MỌI nhân vật trong kho;
  - mọi ảnh chèn trong assets/inserts qua location 'insert:<id>' (sidecar JSON đủ trường);
  - chữ nướng vào ảnh chèn (params catalog + sidecar) là tiếng Anh, không dấu tiếng Việt.

Chạy:  runtime\\venv\\Scripts\\python.exe -X utf8 -m unittest tests.assets_features_test -v
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storytoon.paths import ASSETS, CHARACTERS, INSERTS, LOGS  # noqa: E402
from storytoon.schema import (CharacterDef, CharacterInShot, Line, LocationDef, Overlay, Shot,  # noqa: E402
                              Storyboard)

OUT = LOGS / "asset_review" / "features"
NEW_EXPR = ("nervous", "shocked", "crying", "tired", "smirk")
EFFECTS = (("rain", 1.0), ("fog", 1.0), ("cctv", 1.0), ("flash", 0.1), ("fade_white", 2.35), ("fade_black", 2.35),
           ("blur_in", 0.2), ("glow", 1.0), ("shake_light", 0.5))
VI_RE = re.compile("[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]", re.I)
SHOP, AISLE = "cua_hang_quay_thu_ngan", "cua_hang_loi_ke"


def _ready_loc(*cands: str) -> str:
    for c in cands:
        if (ASSETS / "locations" / c / "bg.png").is_file():
            return c
    return next(p.parent.name for p in sorted((ASSETS / "locations").glob("*/bg.png")))


def L(text: str, start: float = 0.2, dur: float = 2.0, speaker: str = "narrator") -> Line:
    return Line(speaker=speaker, text=text, start=start, duration=dur)


def build() -> tuple[Storyboard, list[tuple[str, float]]]:
    shop = _ready_loc(SHOP, "cho_dem")
    aisle = _ready_loc(AISLE, "hem_toi")
    chars = [
        CharacterDef(id="clerk", name="Minh", role="night clerk", gender="male", age="young",
                     asset_id="nam_tre_nhan_vien_ca_dem"),
        CharacterDef(id="boss", name="Mrs. Hanh", role="owner", gender="female", age="adult",
                     asset_id="ba_chu_tiem_toc_xoan"),
        CharacterDef(id="ghost", name="Wet girl", role="ghost", gender="female", age="young",
                     asset_id="nu_sinh_toc_bob_ma_nuoc"),
    ]
    locs = [LocationDef(id="shop", name="Cashier counter", time_of_day="night", asset_id=shop),
            LocationDef(id="aisle", name="Aisle", time_of_day="night", asset_id=aisle)]
    S: list[Shot] = []
    frames: list[tuple[str, float]] = []

    def add(shot: Shot, t: float | None = 1.0) -> None:
        S.append(shot)
        if t is not None:
            frames.append((shot.id, t))

    clerk = CharacterInShot(id="clerk", slot="center")
    two = [CharacterInShot(id="clerk", slot="left"), CharacterInShot(id="boss", slot="right", facing="left")]
    O = Overlay
    # ---------------- overlays (mọi OverlayKind)
    ov = {
        "nametag": [O(kind="nametag", title="Minh", subtitle="Night clerk", character_id="clerk")],
        "location_card": [O(kind="location_card", title="24H Mart", subtitle="Route 9, 02:47")],
        "chapter_card": [O(kind="chapter_card", title="Night three", subtitle="Chapter 3")],
        "chapter_card_black": [O(kind="chapter_card", title="Night three", subtitle="Chapter 3",
                                 data={"style": "text_on_black"})],
        "time_card": [O(kind="time_card", title="03:00 AM")],
        "rule_card": [O(kind="rule_card", title="Never sell to a customer *without a shadow*.", subtitle="Rule 3",
                        data={"number": 3, "caption_en": "night shift rules"})],
        "rule_list": [O(kind="rule_list", title="NIGHT SHIFT RULES", subtitle="read before your shift",
                        data={"rules": ["Do not open the shutter after 2 AM.", "If someone calls your name, *don't answer*.",
                                        "Never accept wet money.", "The last rule is…"],
                              "red_index": 1, "redact_last": True, "coffee_stain": True, "hands": True})],
        "cctv": [O(kind="cctv", title="", data={"cam": 3, "label": "Aisle 3", "timestamp": "14-03-2024 02:47:13",
                                                 "people": 2})],
        "cctv_grid4": [O(kind="cctv", title="", data={"grid": 4, "people": 1, "cells": [
            {"cam": 1, "label": "Register"}, {"cam": 2, "label": "Aisle 1"},
            {"cam": 3, "label": "Glass door", "location": "aisle"}, {"cam": 4, "label": "Back alley"}]})],
        "cctv_split": [O(kind="cctv", title="CAM 2 · Glass door", data={"split": {}, "people": 2})],
        "cctv_emphasis": [O(kind="cctv", title="", data={"people": 2, "people_emphasis": True})],
        "phone_chat": [O(kind="phone_chat", title="Mrs. Hanh", subtitle="Online", data={"time": "02:13", "hand": True,
                         "messages": [{"from": "them", "text": "Are you still at the store?"},
                                      {"from": "me", "text": "Yes, why?"},
                                      {"from": "them", "text": "The camera shows two people in the stockroom."}]})],
        "phone_lock": [O(kind="phone_chat", title="Mom", data={"lock_screen": True, "time": "03:07",
                         "notification": {"sender": "Unknown", "text": "I'm standing behind the glass."}})],
        "phone_bank": [O(kind="phone_bank", title="", data={"balance": "-$128.00", "transactions": [
            {"label": "Unknown transfer", "amount": "-$128.00", "date": "03/14 03:00"},
            {"label": "Night shift pay", "amount": "+$420.00", "date": "03/10 08:00"}]})],
        "missing_poster": [O(kind="missing_poster", title="Thu Le", subtitle="Age 19",
                             data={"photo": "character:nu_sinh_toc_bob_ma_nuoc", "datetime": "02:40 · MAR 14"})],
        "missing_poster_torn": [O(kind="missing_poster", title="Hung Pham", subtitle="Age 34",
                                  data={"photo": "blank", "variant": "torn"})],
        "map_card": [O(kind="map_card", title="", subtitle="", data={"marker": {"x": 0.6, "y": 0.6}, "tag": "400 m away"})],
        "timeline": [O(kind="timeline", title="", subtitle="nobody lasted 3 months",
                       data={"items": [{"label": "2016"}, {"label": "2019"}, {"label": "2023"},
                                       {"label": "You", "highlight": True}], "progress_done": 3})],
        "info_card": [O(kind="info_card", title="", subtitle="receipt 02:51")],
        "job_ad": [O(kind="job_ad", title="", subtitle="22:00 – 06:00")],
        "defaults_chrome": [O(kind="cctv", title="", data={"people": 1}), O(kind="rule_card", title="", data={"number": 2})],
    }
    for name, overlays in ov.items():
        add(Shot(id=f"ov_{name}", location="shop" if "cctv" in name or name in ("nametag", "rule_card") else "aisle",
                 framing="medium" if name in ("nametag", "rule_card") else "wide", duration=2.5,
                 effects=["cctv"] if name.startswith("cctv") else [],
                 characters=[clerk] if name in ("nametag", "rule_card") or name.startswith("cctv") else [],
                 overlays=overlays), 2.0 if name in ("phone_chat", "timeline") else 1.2)
    add(Shot(id="ov_badge", location="shop", framing="close", focus="clerk", duration=2.5,
             characters=[CharacterInShot(id="clerk", slot="center", action="talk")],
             lines=[L("I started yesterday.", speaker="clerk")],
             overlays=[O(kind="badge", title="MINH", character_id="clerk", data={"emblem": "leaf"})]), 1.2)
    # ---------------- effects
    for name, t in EFFECTS:
        add(Shot(id=f"fx_{name}", location="shop", framing="wide", duration=2.5, effects=[name], characters=two), t)
    # ---------------- view back
    add(Shot(id="view_back", location="aisle", framing="medium", duration=2,
             characters=[CharacterInShot(id="clerk", slot="center", view="back")]), 1.0)
    add(Shot(id="view_over_shoulder", location="shop", framing="close", focus="boss", duration=2,
             characters=[CharacterInShot(id="clerk", slot="left", view="back"),
                         CharacterInShot(id="boss", slot="right", facing="left", action="talk")]), 1.0)
    # ---------------- expressions qua compositor
    for e in NEW_EXPR:
        add(Shot(id=f"expr_{e}", location="shop", framing="close", focus="clerk", duration=1.5,
                 characters=[CharacterInShot(id="clerk", slot="center", expression=e)]), 0.6)
    # ---------------- transitions (shot a + shot b vào bằng transition)
    for tr in ("fade", "white", "blur"):
        add(Shot(id=f"tr_{tr}_a", location="shop", framing="wide", duration=1.5, characters=[clerk]), None)
        add(Shot(id=f"tr_{tr}_b", location="aisle", framing="wide", duration=1.5, transition=tr, characters=[clerk]), 0.08)
    # ---------------- ảnh chèn
    for png in sorted(INSERTS.glob("*.png")):
        add(Shot(id=f"insert_{png.stem}", location=f"insert:{png.stem}", framing="close", duration=2), 1.0)
    return Storyboard(title="Feature review", style="cutout", characters=chars, locations=locs, shots=S), frames


SB, FRAMES = build()


def render_still(sid: str, t: float) -> np.ndarray:
    from storytoon.render.compositor import ShotRenderer
    from storytoon.render.skutil import save_png
    shot = next(s for s in SB.shots if s.id == sid)
    r = ShotRenderer(shot, SB, None, validate_assets=False)
    i = min(r.n - 1, int(round(t * r.fps)))
    r.frame(i)
    rgb = r.target.rgb()
    save_png(rgb, OUT / f"{sid}.png")
    return rgb


class FeatureStillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        OUT.mkdir(parents=True, exist_ok=True)

    def test_every_feature_renders(self) -> None:
        for sid, t in FRAMES:
            with self.subTest(shot=sid):
                img = render_still(sid, t)
                if sid in ("fx_fade_black", "fx_fade_white", "tr_fade_b", "tr_white_b"):
                    continue          # khung về đen/trắng là đúng
                self.assertGreater(float(img.std()), 6.0, f"{sid}: ảnh gần như đồng màu")

    def test_schema_coverage(self) -> None:
        from typing import get_args

        from storytoon.schema import SHOT_EFFECTS, Expression, OverlayKind, Transition
        kinds = {o.kind for s in SB.shots for o in s.overlays}
        self.assertEqual(set(get_args(OverlayKind)) - kinds, set())
        self.assertEqual(set(SHOT_EFFECTS) - {e for s in SB.shots for e in s.effects}, set())
        self.assertEqual(set(get_args(Transition)) - {"cut"} - {s.transition for s in SB.shots}, set())
        self.assertTrue(set(NEW_EXPR) <= set(get_args(Expression)))

    def test_effects_change_pixels(self) -> None:
        """Mỗi hiệu ứng làm khung khác hẳn khung không hiệu ứng."""
        from storytoon.render.compositor import ShotRenderer
        base = Shot(id="fx_none", location="shop", framing="wide", duration=2.5,
                    characters=[CharacterInShot(id="clerk", slot="left"),
                                CharacterInShot(id="boss", slot="right", facing="left")])
        sb = SB.model_copy(update={"shots": SB.shots + [base]})
        for name, t in EFFECTS:
            with self.subTest(effect=name):
                imgs = []
                for sh in (base, base.model_copy(update={"id": f"fx_{name}", "effects": [name]})):
                    r = ShotRenderer(sh, sb, None, validate_assets=False)
                    r.frame(min(r.n - 1, int(round(t * r.fps))))
                    imgs.append(r.target.rgb().astype(np.int16))
                self.assertGreater(float(np.abs(imgs[0] - imgs[1]).mean()), 0.5, f"{name}: không đổi gì")

    def test_expressions_on_every_character(self) -> None:
        """Bảng: hàng = nhân vật trong kho, cột = neutral + 5 biểu cảm mới (ảnh từ assets, puppetgen.render_figure)."""
        import skia

        from storytoon.render import rig as rigmod
        from storytoon.render.puppetgen import render_figure
        from storytoon.render.skutil import save_png
        ids = sorted(p.parent.name for p in CHARACTERS.glob("*/character.json"))
        self.assertGreater(len(ids), 0)
        cols = ("neutral",) + NEW_EXPR
        cw, ch = 220, 240
        sheets = [ids[i:i + 14] for i in range(0, len(ids), 14)]
        for k, part in enumerate(sheets):
            surf = skia.Surface(cw * len(cols), ch * len(part))
            c = surf.getCanvas()
            c.clear(skia.Color4f(0.93, 0.92, 0.9, 1))
            for row, cid in enumerate(part):
                rig = rigmod.Rig.load(cid)
                self.assertIsNotNone(rig, f"{cid}: không nạp được rig")
                self.assertTrue(rig.has_back, f"{cid}: không có ảnh sau lưng (view='back')")
                for col, e in enumerate(cols):
                    with self.subTest(character=cid, expression=e):
                        if rig is not None and e != "neutral":
                            self.assertIn(e, rig.expressions, f"{cid}: thiếu biểu cảm {e}")
                        img = render_figure(cid, e, "front", height_px=ch * 2, crop="head")
                        sc = min(cw / img.width(), ch / img.height()) * 0.95
                        w, h = img.width() * sc, img.height() * sc
                        c.drawImageRect(img, skia.Rect.MakeXYWH(col * cw + (cw - w) / 2, row * ch + (ch - h) / 2, w, h),
                                        skia.SamplingOptions(skia.FilterMode.kLinear))
            save_png(surf.makeImageSnapshot(), OUT / f"expressions_sheet_{k + 1}.png")
        # khác biệt thật: mỗi biểu cảm mới khác neutral trên ít nhất phần lớn nhân vật
        for e in NEW_EXPR:
            diff = 0
            for cid in ids:
                a = render_figure(cid, "neutral", "front", height_px=300, crop="head").toarray().astype(np.int16)
                b = render_figure(cid, e, "front", height_px=300, crop="head").toarray().astype(np.int16)
                if a.shape == b.shape and np.abs(a - b).mean() > 0.05:
                    diff += 1
            with self.subTest(expression=e):
                self.assertGreaterEqual(diff, len(ids) - 2, f"{e}: giống neutral trên {len(ids) - diff} nhân vật")

    def test_insert_sidecars(self) -> None:
        pngs = sorted(INSERTS.glob("*.png"))
        self.assertGreater(len(pngs), 0)
        for png in pngs:
            with self.subTest(insert=png.stem):
                side = png.with_suffix(".json")
                self.assertTrue(side.is_file(), f"thiếu sidecar {side.name}")
                meta = json.loads(side.read_text(encoding="utf-8"))
                for key in ("label", "tags", "props", "style", "provenance"):
                    self.assertIn(key, meta)
                self.assertEqual(meta["style"], "cutout")
                self.assertTrue(meta["props"], "props rỗng")
                for p in meta["props"]:
                    self.assertRegex(p, r"^[a-z0-9]+(_[a-z0-9]+)*$", f"prop không snake_case: {p}")
                self.assertIsNone(VI_RE.search(json.dumps(meta.get("params", {}), ensure_ascii=False)),
                                  f"{png.stem}: chữ trong ảnh còn tiếng Việt")

    def test_catalog_insert_text_is_english(self) -> None:
        cat = json.loads((ASSETS / "catalog" / "inserts.json").read_text(encoding="utf-8"))["inserts"]
        for e in cat:
            with self.subTest(insert=e["id"]):
                self.assertIsNone(VI_RE.search(json.dumps(e.get("params", {}), ensure_ascii=False)))

    def test_insert_props_casting(self) -> None:
        from storytoon import asset_library
        ins = asset_library.catalog()["inserts"]
        by_prop = {}
        for e in ins:
            for p in e["props"]:
                by_prop.setdefault(p, e["id"])
        for prop, want in (("phone", "phone_chat"), ("coin", "coin_wet"), ("banknote", "banknote_wet"),
                           ("rule_paper", "rule_paper"), ("missing_poster", "missing_poster"), ("map", "map_card"),
                           ("clock", "wall_clock"), ("prayer_beads", "prayer_beads"), ("newspaper", "bao_cu")):
            with self.subTest(prop=prop):
                self.assertEqual(by_prop.get(prop), want)


if __name__ == "__main__":
    unittest.main(verbosity=2)
