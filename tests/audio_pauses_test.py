"""Silence trimming, story-based pauses between sentences, and the shared error log."""
import logging
from pathlib import Path
import sys
import tempfile
import threading
import traceback
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from storytoon import errorlog
from storytoon.audio import audio_io, timing, tts
from storytoon.audio.paragraphs import line_paragraphs
from storytoon.schema import Line, Overlay, Shot, Storyboard

SCRIPT = ("Cô bạn cùng phòng của tôi tên là Lan, ham muốn chuyện ấy khá cao. Cứ cách vài hôm, cô ta lại dẫn "
          "bạn trai về phòng ký túc xá nữ qua đêm.\n\n"
          "Sáng hôm ấy, Lan mãi vẫn chưa chịu thức dậy. Tôi thấy lạ nên bước đến kéo rèm giường của cô ta ra.\n"
          "Chẳng bao lâu sau, tiếng còi xe cảnh sát đã vang lên dưới ký túc xá.")
TEXTS = ["Cô bạn cùng phòng của tôi tên là Lan.",
         "Lan ham muốn chuyện ấy khá cao.",                     # AI thêm chủ ngữ
         "Cứ cách vài hôm, cô ta lại dẫn bạn trai về ký túc xá nữ qua đêm.",
         "Sáng hôm ấy, Lan mãi vẫn chưa chịu thức dậy.",
         "Tôi thấy lạ nên bước đến kéo rèm giường của cô ta ra.",
         "Chẳng bao lâu sau, tiếng còi xe cảnh sát đã vang lên dưới ký túc xá."]


class TrimTests(unittest.TestCase):
    def test_trim_keeps_50ms_each_side(self):
        sr = audio_io.SR
        tone = 0.5 * np.sin(np.linspace(0, 2 * np.pi * 220, sr))
        data = np.concatenate([np.zeros(int(0.4 * sr)), tone, np.zeros(int(0.3 * sr))])
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'a.wav'
            audio_io.write_wav(p, data)
            dur = tts.trim_silence(p)
            self.assertAlmostEqual(dur, 1.0 + 2 * tts.TRIM_KEEP, delta=0.03)


class ParagraphTests(unittest.TestCase):
    def test_matches_rewritten_sentences_to_paragraphs(self):
        self.assertEqual(line_paragraphs(SCRIPT, TEXTS), [(0, 0), (0, 0), (0, 0), (1, 1), (1, 1), (2, 2)])

    def test_unknown_sentence_is_none(self):
        self.assertEqual(line_paragraphs(SCRIPT, ["Hoàn toàn không có trong kịch bản xyz."]), [None])


def _sb(locations, chapter_at=None):
    shots = []
    for i, (text, loc) in enumerate(zip(TEXTS, locations)):
        ov = [Overlay(kind='chapter_card', title='Chương 2')] if i == chapter_at else []
        shots.append(Shot(id=f's{i + 1:03d}', location=loc, min_duration=0.5, overlays=ov,
                          lines=[Line(text=text, duration=2.0)]))
    return Storyboard(title='t', shots=shots)


def _gaps(sb):
    offs = timing.shot_offsets(sb)
    spans = [(o + ln.start, o + ln.start + ln.duration) for o, s in zip(offs, sb.shots) for ln in s.lines]
    return [round(b[0] - a[1], 3) for a, b in zip(spans, spans[1:])]


class PauseTests(unittest.TestCase):
    def test_sentence_paragraph_scene_pauses_across_shots(self):
        sb = _sb(['phong'] * 5 + ['san'])
        pauses, matched = timing.story_pauses(sb, SCRIPT)
        self.assertEqual(matched, 6)
        timing.layout_story(sb, pauses)
        self.assertEqual(_gaps(sb), [0.35, 0.35, 0.8, 0.35, 1.2])
        self.assertAlmostEqual(sb.shots[0].lines[0].start, timing.FILM_LEAD)

    def test_chapter_card_gives_scene_pause(self):
        sb = _sb(['phong'] * 6, chapter_at=1)
        timing.layout_story(sb, timing.story_pauses(sb, SCRIPT)[0])
        self.assertEqual(_gaps(sb)[0], 1.2)

    def test_lines_inside_one_shot(self):
        sb = Storyboard(title='t', shots=[Shot(id='s001', location='phong', min_duration=0.5,
                                               lines=[Line(text=t, duration=2.0) for t in TEXTS[2:5]])])
        timing.layout_story(sb, timing.story_pauses(sb, SCRIPT)[0])
        self.assertEqual(_gaps(sb), [0.8, 0.35])

    def test_fill_timing_without_script_keeps_old_layout(self):
        shot = Shot(id='s001', location='p', lines=[Line(text='a', duration=1.0)])
        timing.layout_shot(shot)
        self.assertEqual(shot.lines[0].start, timing.FIRST_LINE_START)


class ErrorLogTests(unittest.TestCase):
    def test_record_and_print_exc_write_details_once(self):
        saved = (errorlog._handler, errorlog.LOG_FILE, sys.excepthook, threading.excepthook, traceback.print_exc)
        with tempfile.TemporaryDirectory() as d:
            try:
                errorlog._handler = None
                errorlog.LOG_FILE = Path(d) / 'errors.log'
                handler = errorlog.install()
                try:
                    raise ValueError('hỏng tệp âm thanh')
                except ValueError as exc:
                    errorlog.record('Bước Âm thanh', exc, project='phim_x')
                    errorlog.record('Bước Âm thanh', exc)            # không ghi trùng
                try:
                    raise KeyError('nút bấm')
                except KeyError:
                    with patch('sys.stderr'):
                        traceback.print_exc()                       # đường lỗi của Gradio
                handler.flush()
                text = errorlog.LOG_FILE.read_text(encoding='utf-8')
                self.assertEqual(text.count('Lỗi tại: Bước Âm thanh'), 1)   # không ghi trùng
                self.assertIn('project: phim_x', text)
                self.assertIn('Traceback', text)
                self.assertIn('nút bấm', text)
            finally:
                if errorlog._handler:
                    logging.getLogger().removeHandler(errorlog._handler)
                    errorlog._handler.close()
                (errorlog._handler, errorlog.LOG_FILE, sys.excepthook, threading.excepthook,
                 traceback.print_exc) = saved


if __name__ == '__main__':
    unittest.main()
