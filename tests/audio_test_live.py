"""Test có mạng: edge-tts thật + Rhubarb + trộn toàn phim.
Chạy: runtime\\venv\\Scripts\\python.exe -m unittest tests.audio_test_live
Dùng projects/demo/storyboard.json nếu có (KHÔNG ghi đè nó; xuất ra thư mục tạm)."""
from __future__ import annotations

import shutil
import tempfile
import time
import unittest
from pathlib import Path

from storytoon.audio import audio_io, lipsync, mixer, timing, tts
from storytoon.paths import PROJECTS
from storytoon.schema import CharacterDef, Line, Shot, Storyboard

SENTENCES = [
    ("Đêm hôm ấy, ông Hai nghe tiếng gõ cửa ba lần.", "vi-VN-NamMinhNeural"),
    ("Cháu ơi, đừng mở cửa sau nửa đêm nhé!", "vi-VN-HoaiMyNeural"),
]


def _tiny_storyboard() -> Storyboard:
    return Storyboard(
        title="Thử", characters=[CharacterDef(id="ba_tu", name="Bà Tư", gender="female", age="old")],
        locations=[],
        shots=[
            Shot(id="s001", location="x", music_mood="tense", sfx=["wind"],
                 lines=[Line(text=SENTENCES[0][0])]),
            Shot(id="s002", location="x", sfx=["door"],
                 lines=[Line(speaker="ba_tu", text=SENTENCES[1][0]), Line(speaker="ba_tu", text="Nhớ chưa?")]),
            Shot(id="s003", location="x", music_mood="horror", sfx=["gong"], min_duration=3.0),
        ])


class LiveTests(unittest.TestCase):
    tmp: Path

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="stoon_live_Làm việc_"))

    def test_synth_vietnamese(self) -> None:
        for i, (text, voice) in enumerate(SENTENCES):
            out = self.tmp / "lines" / f"l{i}.wav"
            d = tts.synth_line(text, voice, out)
            self.assertGreater(d, 1.0)
            self.assertTrue(tts.wav16_path(out).exists())
            t = time.time()
            self.assertEqual(tts.synth_line(text, voice, out), d)  # cache
            self.assertLess(time.time() - t, 0.5)

    def test_rhubarb(self) -> None:
        self.assertIsNotNone(lipsync.ensure_rhubarb(), "Rhubarb phải tải được")
        out = self.tmp / "lines" / "rh.wav"
        tts.synth_line(SENTENCES[0][0], SENTENCES[0][1], out)
        vis = lipsync.run_rhubarb(tts.wav16_path(out))
        self.assertGreater(len(vis), 5)
        self.assertTrue(set(s for _, s in vis) - {"X"})

    def _run_project(self, sb: Storyboard, name: str) -> None:
        proj = self.tmp / name
        t = time.time()
        timing.fill_timing(sb, proj, progress=lambda m, f: None)
        print(f"\n[{name}] fill_timing {time.time() - t:.1f}s, phim dài {timing.film_duration(sb):.1f}s")
        for shot in sb.shots:
            self.assertIsNotNone(shot.duration)
            self.assertGreaterEqual(shot.duration, shot.min_duration)
            for ln in shot.lines:
                self.assertTrue((proj / ln.audio).exists())
                self.assertGreater(ln.duration, 0)
                self.assertTrue(ln.visemes)
                self.assertLessEqual(ln.start + ln.duration, shot.duration)
        self.assertTrue((proj / "subtitles.srt").read_text(encoding="utf-8").startswith("1\n"))
        t = time.time()
        wav = mixer.build_soundtrack(sb, proj, proj / "soundtrack.wav")
        print(f"[{name}] build_soundtrack {time.time() - t:.1f}s -> {wav}")
        self.assertAlmostEqual(audio_io.wav_duration(wav), timing.film_duration(sb), delta=0.1)
        # chạy lại: phải dùng cache, nhanh
        t = time.time()
        timing.fill_timing(sb, proj)
        self.assertLess(time.time() - t, 10)

    def test_tiny_project(self) -> None:
        self._run_project(_tiny_storyboard(), "tiny")

    def test_demo_project(self) -> None:
        src = PROJECTS / "demo" / "storyboard.json"
        if not src.exists():
            self.skipTest("Chưa có projects/demo/storyboard.json")
        sb = Storyboard.model_validate_json(src.read_text(encoding="utf-8"))
        self._run_project(sb, "demo")
        out = Path(tempfile.gettempdir()) / "storytoon_demo_soundtrack.wav"
        shutil.copyfile(self.tmp / "demo" / "soundtrack.wav", out)
        print(f"[demo] bản nghe thử: {out}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
