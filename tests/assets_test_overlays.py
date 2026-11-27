"""Test gói C: overlay mới + hiệu ứng theo shot + chuyển cảnh + view back / qua vai.

Dựng 1 storyboard tạm dùng mọi OverlayKind / Shot.effects / Shot.transition mới trên nền + puppet mẫu gốc
(cho_dem, hem_toi, chu_tu, toi, co_lan — vẽ vector của dự án, không phải ảnh tham khảo), xuất ảnh tĩnh để duyệt
bằng mắt -> logs/asset_review/overlays/*.png, rồi kiểm tra:
  - mọi overlay/effect dựng được, ảnh không rỗng, hoạt hình đổi theo t (giây CCTV, tin nhắn pop, timeline);
  - chuyển cảnh không đổi số frame (film.frame_counts) và đầu/đuôi shot đúng màu (fade -> đen, white -> trắng);
  - tên hiệu ứng lạ / data thiếu không làm sập;
  - tốc độ vẽ shot nặng (cctv + rain + fog + glow + HUD) >= 30 fps @1080p (GPU).

Chạy:  runtime\\venv\\Scripts\\python.exe -X utf8 tests\\assets_test_overlays.py [--only ID ...] [--no-perf]
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storytoon.paths import LOGS  # noqa: E402
from storytoon.schema import (CharacterDef, CharacterInShot, Line, LocationDef, Overlay, Shot,  # noqa: E402
                              Storyboard)

OUT = LOGS / "asset_review" / "overlays"
ARGS = argparse.Namespace(only=None, perf=True)


def L(text: str, start: float = 0.2, dur: float = 2.2, speaker: str = "narrator") -> Line:
    return Line(speaker=speaker, text=text, start=start, duration=dur)


def build() -> tuple[Storyboard, dict[str, list[float]]]:
    chars = [
        CharacterDef(id="chu", name="Chú Bảy", role="Chủ tạp hoá", gender="male", age="old", asset_id="chu_tu"),
        CharacterDef(id="an", name="An", role="Nhân viên ca đêm", gender="male", age="young", asset_id="toi"),
        CharacterDef(id="ma", name="Cô gái áo ướt", role="", gender="female", age="young", asset_id="co_lan",
                     tags=["ghost", "pale", "long_hair"]),
    ]
    locs = [LocationDef(id="cho", name="Chợ đêm", time_of_day="night", asset_id="cho_dem"),
            LocationDef(id="hem", name="Hẻm tối", time_of_day="night", asset_id="hem_toi")]
    S: list[Shot] = []
    times: dict[str, list[float]] = {}

    def add(shot: Shot, ts: list[float]) -> None:
        S.append(shot)
        times[shot.id] = ts

    an = CharacterInShot(id="an", slot="center", action="idle", facing="right")
    chu = CharacterInShot(id="chu", slot="center", action="talk", facing="right", expression="evil")
    # ---------------- overlays
    add(Shot(id="ov_rule_card", location="cho", framing="close", focus="chu", duration=3, characters=[chu],
             lines=[L("Luật thứ ba: không bán cho khách không có bóng.", speaker="chu")],
             overlays=[Overlay(kind="rule_card", title="Không bán hàng cho *khách không có bóng*.",
                               subtitle="Luật số 3", data={"number": 3, "caption_en": "quy định ca đêm"})]),
        [0.12, 1.5])
    add(Shot(id="ov_rule_card_tr", location="cho", framing="medium", duration=2.5,
             characters=[CharacterInShot(id="an", slot="left"), CharacterInShot(id="chu", slot="right", facing="left")],
             overlays=[Overlay(kind="rule_card", title="Nghe tiếng gõ cửa 3 lần thì *đừng mở*.", subtitle="Luật 5",
                               data={"corner": "tr"})]), [1.2])
    add(Shot(id="ov_rule_list", location="hem", framing="wide", duration=4,
             lines=[L("Tờ nội quy dán sau quầy thu ngân.")],
             overlays=[Overlay(kind="rule_list", title="NỘI QUY CA ĐÊM", subtitle="đọc kỹ trước khi nhận ca",
                               data={"rules": ["Không mở cửa cuốn sau 2 giờ sáng.",
                                               "Khách gọi đúng tên bạn: *đừng trả lời*.",
                                               "Không nhận tiền ướt, kể cả tiền xu.",
                                               "Đèn kho nháy 3 lần thì ra quầy đứng yên.",
                                               "Camera đếm 2 người mà bạn chỉ thấy 1: rời đi ngay.",
                                               "Luật cuối cùng là…"],
                                     "red_index": 2, "redact_last": True, "coffee_stain": True,
                                     "bleed_through": True, "hands": True})]), [0.6, 3.5])
    add(Shot(id="ov_rule_list_blurred", location="hem", framing="wide", duration=2,
             overlays=[Overlay(kind="rule_list", title="NỘI QUY", data={"rules": ["…"] * 5, "blurred": True})]), [1.0])
    add(Shot(id="ov_cctv", location="cho", framing="wide", duration=3, effects=["cctv"],
             characters=[CharacterInShot(id="an", slot="left"), CharacterInShot(id="ma", slot="right", facing="left")],
             overlays=[Overlay(kind="cctv", title="", data={"cam": 3, "label": "Lối kệ 3", "timestamp": "14-03-2024 02:47:13",
                                                             "people": [[0, 1], [1.2, 2]]})]), [0.3, 1.3, 2.6])
    add(Shot(id="ov_cctv_grid", location="cho", framing="wide", duration=2.5, effects=["cctv"],
             characters=[CharacterInShot(id="an", slot="center")],
             overlays=[Overlay(kind="cctv", title="", data={"grid": 4, "people": 1, "cells": [
                 {"cam": 1, "label": "Quầy thu ngân"}, {"cam": 2, "label": "Lối kệ 1"},
                 {"cam": 3, "label": "Cửa kính"}, {"cam": 4, "label": "Hẻm sau", "location": "hem"}]})]), [1.1])
    add(Shot(id="ov_cctv_split", location="cho", framing="wide", duration=2.5, effects=["cctv"],
             characters=[CharacterInShot(id="an", slot="left"), CharacterInShot(id="ma", slot="center", facing="left")],
             overlays=[Overlay(kind="cctv", title="CAM 2 · Cửa kính", data={"split": {"left_tag": "trên camera",
                                                                                     "right_tag": "bằng mắt thường"},
                                                                           "people": 2})]), [1.2])
    add(Shot(id="ov_cctv_emphasis", location="cho", framing="wide", duration=2.5, effects=["cctv"],
             characters=[CharacterInShot(id="an", slot="left")],
             overlays=[Overlay(kind="cctv", title="CAM 1 · Quầy", data={"people": 2, "people_emphasis": True})]),
        [0.15, 1.5])
    add(Shot(id="ov_phone_chat", location="hem", framing="wide", duration=4,
             overlays=[Overlay(kind="phone_chat", title="Chị Hạnh (quản lý)", subtitle="Đang hoạt động",
                               data={"time": "02:13", "hand": True, "messages": [
                                   {"from": "them", "text": "Em còn ở cửa hàng không?"},
                                   {"from": "me", "text": "Dạ còn, có chuyện gì vậy chị?"},
                                   {"from": "them", "text": "Camera thấy có 2 người trong kho."},
                                   {"from": "me", "text": "Nhưng em đang ở một mình mà…"},
                                   {"from": "them", "text": "Đừng quay lại nhìn."}]})]), [0.5, 1.6, 3.4])
    add(Shot(id="ov_phone_lock", location="hem", framing="wide", duration=2.5,
             overlays=[Overlay(kind="phone_chat", title="Mẹ", data={"lock_screen": True, "time": "03:07",
                                                                     "notification": {"sender": "Số lạ",
                                                                                      "text": "Tôi đang đứng sau cửa kính."}}
                               )]), [1.4])
    add(Shot(id="ov_phone_bank", location="hem", framing="wide", duration=2.5,
             overlays=[Overlay(kind="phone_bank", title="Ngân hàng Hoà Bình", subtitle="TRAN VAN AN",
                               data={"balance": "-1.280.000 ₫", "transactions": [
                                   {"label": "Chuyển khoản không rõ", "amount": "-1.280.000 ₫", "date": "14/03 03:00"},
                                   {"label": "Lương ca đêm", "amount": "+4.200.000 ₫", "date": "10/03 08:00"},
                                   {"label": "Tiền trọ tháng 3", "amount": "-1.500.000 ₫", "date": "05/03 19:30"}]})]),
        [1.2])
    add(Shot(id="ov_missing_poster", location="hem", framing="wide", duration=2.5,
             overlays=[Overlay(kind="missing_poster", title="Lê Thị Thu", subtitle="19 tuổi",
                               data={"photo": "character:co_lan", "desc": "Tóc dài, mặc áo bà ba trắng, đi làm ca đêm "
                                                                          "rồi không về nhà.",
                                     "datetime": "Mất tích lúc 02:40 · 14-03-2024", "phone": "Liên hệ: 09•• ••• 3•8"})]),
        [1.2])
    add(Shot(id="ov_missing_poster_torn", location="hem", framing="wide", duration=2,
             overlays=[Overlay(kind="missing_poster", title="Phạm Văn Hùng", subtitle="34 tuổi",
                               data={"photo": "blank", "variant": "torn"})]), [1.0])
    add(Shot(id="ov_missing_poster_wall", location="hem", framing="wide", duration=2,
             overlays=[Overlay(kind="missing_poster", title="Ngô Minh", subtitle="8 tuổi",
                               data={"photo": "character:toi", "variant": "wall", "datetime": "Đi lạc gần bến xe buýt"})]),
        [1.0])
    add(Shot(id="ov_map_card", location="hem", framing="wide", duration=3,
             overlays=[Overlay(kind="map_card", title="Đoạn đường ven kênh", subtitle="xã Tân Lộc · huyện Bình Thủy",
                               data={"road_label": "Tỉnh lộ 8", "water_label": "Kênh Ba Lăng",
                                     "marker": {"x": 0.6, "y": 0.62, "label": "Điểm xảy ra · 03:00"},
                                     "tag": "Cách cửa hàng 400 m"})]), [0.6, 1.0])
    add(Shot(id="ov_timeline", location="hem", framing="wide", duration=4,
             overlays=[Overlay(kind="timeline", title="Những nhân viên ca đêm trước", subtitle="không ai làm quá 3 tháng",
                               data={"items": [{"label": "2016"}, {"label": "2018"}, {"label": "2019"}, {"label": "2021"},
                                               {"label": "2023"}, {"label": "Bạn", "highlight": True}],
                                     "progress_done": 5})]), [0.9, 3.5])
    add(Shot(id="ov_info_card", location="cho", framing="medium", duration=2.5,
             characters=[CharacterInShot(id="an", slot="center")],
             overlays=[Overlay(kind="info_card", title="GIÁ · POS", subtitle="hoá đơn lúc 02:51",
                               data={"rows": [{"label": "Mì gói ×2", "value": "14.000 ₫"},
                                              {"label": "Nước suối", "value": "6.000 ₫"},
                                              {"label": "Khách đưa", "value": "500.000 ₫", "note": "tờ tiền ướt sũng"}]})]),
        [1.5])
    add(Shot(id="ov_job_ad", location="hem", framing="wide", duration=2.5,
             overlays=[Overlay(kind="job_ad", title="Tuyển nhân viên ca đêm", subtitle="22:00 – 06:00",
                               data={"shop": "Tạp hoá 24H", "salary": "9.000.000 ₫ / tháng",
                                     "footnote": "Nhận ngay · Không cần kinh nghiệm · Có phụ cấp"})]), [0.2, 1.5])
    add(Shot(id="ov_badge_nametag", location="cho", framing="close", focus="an", duration=2.5,
             characters=[CharacterInShot(id="an", slot="center", action="talk")],
             lines=[L("Em mới nhận ca hôm qua.", speaker="an")],
             overlays=[Overlay(kind="badge", title="AN", character_id="an", data={"emblem": "leaf"}),
                       Overlay(kind="nametag", title="An", subtitle="Nhân viên ca đêm", character_id="an")]), [1.4])
    add(Shot(id="ov_chapter_black", location="hem", framing="wide", duration=2,
             overlays=[Overlay(kind="chapter_card", title="Đêm thứ ba", subtitle="Chương 3",
                               data={"style": "text_on_black"})]), [1.2])
    add(Shot(id="ov_subtitle_chunks", location="cho", framing="medium", duration=4,
             characters=[CharacterInShot(id="an", slot="center")],
             lines=[L("Năm đó tôi xin vào làm ca đêm ở một tiệm tạp hoá nhỏ, ngay cạnh bến xe buýt cuối tuyến.",
                      0.2, 3.6)]), [0.5, 2.0, 3.5])
    # ---------------- effects
    for name, ts in (("rain", [1.0]), ("fog", [1.0]), ("cctv", [1.0]), ("flash", [0.15]), ("fade_white", [2.3]),
                     ("fade_black", [2.3]), ("blur_in", [0.25]), ("glow", [1.0]), ("shake_light", [0.5])):
        add(Shot(id=f"fx_{name}", location="cho", framing="wide", duration=2.5, effects=[name],
                 characters=[CharacterInShot(id="an", slot="left"), CharacterInShot(id="chu", slot="right", facing="left")]),
            ts)
    # ---------------- view back / qua vai
    add(Shot(id="view_back", location="hem", framing="medium", duration=2,
             characters=[CharacterInShot(id="an", slot="center", view="back")]), [1.0])
    add(Shot(id="view_over_shoulder", location="cho", framing="close", focus="chu", duration=2.5,
             characters=[CharacterInShot(id="an", slot="left", view="back"),
                         CharacterInShot(id="chu", slot="right", facing="left", action="talk")],
             lines=[L("Cậu thấy gì trên camera?", speaker="chu")]), [1.2])
    # ---------------- chuyển cảnh (đuôi shot trước + đầu shot sau)
    for tr in ("fade", "white", "blur"):
        add(Shot(id=f"tr_{tr}_a", location="cho", framing="wide", duration=1.5,
                 characters=[CharacterInShot(id="an", slot="center")]), [])
        add(Shot(id=f"tr_{tr}_b", location="hem", framing="wide", duration=1.5, transition=tr,
                 characters=[CharacterInShot(id="an", slot="center")]), [])
    return Storyboard(title="Ca đêm ở tạp hoá 24H", characters=chars, locations=locs, shots=S), times


SB, TIMES = build()
_RENDERERS: dict = {}


def renderer(sid: str):
    from storytoon.render.compositor import ShotRenderer
    if sid not in _RENDERERS:
        shot = next(s for s in SB.shots if s.id == sid)
        _RENDERERS.clear()          # giải phóng GPU của shot trước
        _RENDERERS[sid] = ShotRenderer(shot, SB, None, validate_assets=False)
    return _RENDERERS[sid]


def still(sid: str, t: float, save: bool = True) -> np.ndarray:
    from storytoon.render.skutil import save_png
    r = renderer(sid)
    i = min(r.n - 1, int(round(t * r.fps)))
    r.frame(i)
    rgb = r.target.rgb()
    if save:
        save_png(rgb, OUT / f"{sid}_{i:03d}.png")
    return rgb


class OverlayEffectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        OUT.mkdir(parents=True, exist_ok=True)

    def test_all_stills(self) -> None:
        """Mọi shot dựng được, ảnh không đen/đồng màu; xuất ảnh duyệt."""
        for sh in SB.shots:
            if ARGS.only and sh.id not in ARGS.only:
                continue
            for t in TIMES[sh.id]:
                with self.subTest(shot=sh.id, t=t):
                    img = still(sh.id, t)
                    self.assertGreater(float(img.std()), 6.0, f"{sh.id}@{t}: ảnh gần như đồng màu")

    def test_animated_layers_change(self) -> None:
        for sid, t0, t1 in (("ov_cctv", 0.3, 1.4), ("ov_phone_chat", 0.5, 2.0), ("ov_timeline", 0.4, 2.5),
                            ("ov_cctv_emphasis", 0.05, 1.0)):
            with self.subTest(shot=sid):
                a = still(sid, t0, save=False).astype(np.int16)
                b = still(sid, t1, save=False).astype(np.int16)
                self.assertGreater(float(np.abs(a - b).mean()), 0.3, f"{sid}: lớp động không đổi theo t")

    def test_transitions_keep_duration_and_colors(self) -> None:
        from storytoon.render.film import frame_counts
        base = SB.model_copy(update={"shots": [s.model_copy(update={"transition": "cut"}) for s in SB.shots]})
        self.assertEqual(frame_counts(SB, 30), frame_counts(base, 30))
        for tr, want in (("fade", 0), ("white", 255)):
            r = renderer(f"tr_{tr}_a")
            r.frame(r.n - 1)
            tail = r.target.rgb()
            r = renderer(f"tr_{tr}_b")
            r.frame(0)
            head = r.target.rgb()
            for name, img in (("đuôi", tail), ("đầu", head)):
                # bỏ vùng watermark/grain: so trung vị
                med = float(np.median(img))
                self.assertLess(abs(med - want), 40, f"{tr}: {name} shot không về {want} (median {med})")
        # blur: frame đầu shot b mờ hơn frame giữa
        r = renderer("tr_blur_b")
        r.frame(0)
        g0 = np.abs(np.diff(r.target.rgb().astype(np.int16), axis=1)).mean()
        r.frame(r.n // 2)
        g1 = np.abs(np.diff(r.target.rgb().astype(np.int16), axis=1)).mean()
        self.assertLess(g0, g1 * 0.8, "transition blur: đầu shot không mờ")
        from storytoon.render.skutil import save_png
        for sid, i in (("tr_fade_a", -1), ("tr_fade_b", 3), ("tr_white_b", 2), ("tr_blur_b", 3)):
            r = renderer(sid)
            j = r.n - 1 if i < 0 else i
            r.frame(j)
            save_png(r.target.rgb(), OUT / f"{sid}_{j:03d}.png")

    def test_robust_inputs(self) -> None:
        from storytoon.render.compositor import ShotRenderer
        from storytoon.render.effects import parse_effects
        self.assertEqual([n for n, _ in parse_effects(["rain", "khong_co", "flash:1.5", "fog:abc"])],
                         ["rain", "flash", "fog"])
        shot = Shot(id="robust", location="cho", framing="wide", duration=1.5, effects=["xyz", "flash:0.2"],
                    overlays=[Overlay(kind=k, title="") for k in ("cctv", "phone_chat", "phone_bank", "missing_poster",
                                                                  "map_card", "timeline", "info_card", "job_ad",
                                                                  "rule_list", "rule_card")] +
                    [Overlay(kind="badge", title="X"), Overlay(kind="cctv", title="", data={"grid": 4, "cells": "sai"}),
                     Overlay(kind="phone_chat", title="A", data={"messages": "sai kiểu"})])
        r = ShotRenderer(shot, SB, None, validate_assets=False)
        r.frame(10)

    def test_subtitle_chunks_single_line(self) -> None:
        from storytoon.render.overlays import SUB_MAX_WORDS, split_subtitle_chunks
        text = "Năm đó tôi xin vào làm ca đêm ở một tiệm tạp hoá nhỏ, ngay cạnh bến xe buýt cuối tuyến."
        ch = split_subtitle_chunks(text, 1920, 1080)
        self.assertEqual(" ".join(ch), text)
        self.assertTrue(all(len(c.split()) <= SUB_MAX_WORDS for c in ch), ch)
        self.assertTrue(any(c.endswith(",") for c in ch), ch)   # ngắt ở dấu phẩy
        self.assertEqual(split_subtitle_chunks("Em biết.", 1920, 1080), ["Em biết."])

    def test_performance(self) -> None:
        if not ARGS.perf:
            self.skipTest("--no-perf")
        from storytoon.render.backend import get_backend
        if not get_backend().gpu:
            self.skipTest("không có GPU")
        heavy = Shot(id="perf_heavy", location="cho", framing="medium", camera="push_in_slow", duration=3,
                     effects=["cctv", "rain", "fog", "glow", "shake_light"], transition="fade",
                     characters=[CharacterInShot(id="an", slot="left", action="talk"),
                                 CharacterInShot(id="chu", slot="right", facing="left")],
                     lines=[L("Camera số ba vừa đếm thêm một người.", speaker="an")],
                     overlays=[Overlay(kind="cctv", title="", data={"cam": 3, "people": [[0, 1], [1, 2]]}),
                               Overlay(kind="rule_card", title="Không nhìn vào *camera số 3*.", subtitle="Luật 4")])
        for sh, need in ((heavy, 30.0),):
            r = ShotRenderer_(sh)
            for i in range(5):
                r.frame(i)
            t = time.perf_counter()
            n = 60
            for i in range(n):
                r.frame(i % r.n)
            fps = n / (time.perf_counter() - t)
            print(f"\n{sh.id}: {fps:.1f} fps (vẽ + đọc về, 1920x1080)")
            self.assertGreaterEqual(fps, need)


def ShotRenderer_(shot: Shot):
    from storytoon.render.compositor import ShotRenderer
    return ShotRenderer(shot, SB, None, validate_assets=False)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--no-perf", action="store_true")
    a, rest = ap.parse_known_args()
    ARGS.only = a.only
    ARGS.perf = not a.no_perf
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    unittest.main(argv=[sys.argv[0]] + rest, verbosity=2)
