"""Test không cần mạng cho storytoon.audio. Chạy: runtime\\venv\\Scripts\\python.exe -m unittest tests.audio_test_offline"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from storytoon.audio import audio_io, lipsync, mixer, timing, tts
from storytoon.schema import CharacterDef, Line, Shot, Storyboard


def _tone_wav(path: Path, seconds: float = 2.0) -> Path:
    t = np.arange(int(seconds * 48000)) / 48000
    env = (np.sin(2 * np.pi * 3 * t) > 0).astype(np.float32)  # bật/tắt như âm tiết
    return audio_io.write_wav(path, 0.5 * np.sin(2 * np.pi * 220 * t) * env)


class OfflineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="stoon_test_Làm việc_"))

    def test_cache_key_nfc(self) -> None:
        nfd = "Đêm hôm ấy".encode("utf-8").decode("utf-8")
        import unicodedata
        self.assertEqual(tts.cache_key(unicodedata.normalize("NFD", nfd), "v"), tts.cache_key(nfd, "v"))

    def test_amplitude_visemes(self) -> None:
        wav = _tone_wav(self.tmp / "tone.wav")
        vis = lipsync.amplitude_visemes(wav)
        self.assertGreater(len(vis), 4)
        self.assertTrue(all(s in lipsync.SHAPES for _, s in vis))
        times = [t for t, _ in vis]
        self.assertEqual(times, sorted(times))
        self.assertEqual(vis[-1][1], "X")

    def test_layout_and_srt(self) -> None:
        shot = Shot(id="s1", location="x", lines=[Line(text="a", duration=1.0), Line(text="b", duration=2.0)])
        timing.layout_shot(shot)
        self.assertAlmostEqual(shot.lines[0].start, 0.25)
        self.assertAlmostEqual(shot.lines[1].start, 1.4)
        self.assertAlmostEqual(shot.duration, 1.4 + 2.0 + 0.45)
        empty = Shot(id="s2", location="x", min_duration=3.0)
        timing.layout_shot(empty)
        self.assertEqual(empty.duration, 3.0)
        sb = Storyboard(title="t", shots=[shot, empty])
        self.assertEqual(timing.shot_offsets(sb), [0.0, 3.85])
        srt = timing.write_srt(sb, self.tmp / "sub.srt").read_text(encoding="utf-8")
        self.assertIn("00:00:00,250 --> 00:00:01,250", srt)
        self.assertEqual(timing._srt_time(3725.5), "01:02:05,500")

    def test_voice_map(self) -> None:
        sb = Storyboard(title="t", characters=[
            CharacterDef(id="a", name="A", gender="male", age="adult"),
            CharacterDef(id="b", name="B", gender="male", age="adult"),
            CharacterDef(id="c", name="C", gender="female", age="child"),
        ])
        vm = timing.build_voice_map(sb, {"narrator_voice": "vi-VN-NamMinhNeural", "rate": "+5%"})
        self.assertEqual(vm["c"].voice, "vi-VN-HoaiMyNeural")
        self.assertEqual(vm["c"].rate, "+13%")
        self.assertNotEqual(vm["a"].pitch, vm["b"].pitch)
        self.assertNotEqual(vm["a"].pitch, vm["narrator"].pitch)

    def test_loop_and_duck(self) -> None:
        x = np.ones((48000, 2), dtype=np.float32)
        y = mixer.loop_to(x, 48000 * 5)
        self.assertEqual(y.shape, (48000 * 5, 2))
        self.assertLess(float(np.abs(y - 1).max()), 1e-3)  # crossfade tuyến tính giữ biên độ
        voice = np.zeros(48000 * 3, dtype=np.float32)
        voice[48000:96000] = 0.5
        g = mixer.duck_gain(voice, -12)
        self.assertAlmostEqual(float(g[1000]), 1.0, places=3)
        self.assertLess(float(g[72000]), 0.3)

    def test_music_segments(self) -> None:
        shots = [Shot(id=f"s{i}", location="x", min_duration=2.0, music_mood=m)
                 for i, m in enumerate(["tense", None, "horror", "none", None, "sad"])]
        segs = mixer.music_segments(Storyboard(title="t", shots=shots))
        self.assertEqual(segs, [("tense", 0.0, 4.0), ("horror", 4.0, 6.0), ("sad", 10.0, 12.0)])


if __name__ == "__main__":
    unittest.main()
