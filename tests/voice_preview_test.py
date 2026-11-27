"""Persistent preview cache, fixed text and no repeat service calls."""
import importlib
import tempfile
import unittest
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from storytoon import paths
from storytoon.audio import audio_io, preview, voices


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = patch.object(paths, 'VOICE_PREVIEWS', Path(self.tmp.name))
        patcher.start(); self.addCleanup(patcher.stop)
        self.calls = []
        async def synth(text, voice, output, **kwargs):
            self.calls.append((text,voice,kwargs))
            with wave.open(str(output), 'wb') as wav:
                wav.setparams((1,2,48000,0,'NONE','not compressed'))
                wav.writeframes(b'\0\0' * 96000)
            return 2.0
        patcher = patch('storytoon.audio.tts.synth_line_async', side_effect=synth)
        patcher.start(); self.addCleanup(patcher.stop)

    def test_replay_after_reload_and_speed_change_do_not_synthesize(self):
        first = preview.get_preview('capcut','vi','BV075_streaming')
        content = first.read_bytes()
        importlib.reload(preview)  # No memory cache survives; saved WAV must be sufficient.
        second = preview.get_preview('capcut','vi','BV075_streaming')
        faster = preview.get_preview('capcut','vi','BV075_streaming','+50%')
        self.assertEqual(first, second)
        self.assertEqual(second.read_bytes(),content)
        self.assertLess(audio_io.wav_duration(faster),1.5)
        self.assertEqual(preview.get_preview('capcut','vi','BV075_streaming','50%'),faster)
        self.assertEqual(len(self.calls),1)
        self.assertEqual(self.calls[0][0],voices.SAMPLES['vi'])
        self.assertEqual(self.calls[0][2]['rate'],'+0%')

    def test_concurrent_clicks_generate_once(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _: preview.get_preview('capcut','vi','BV075_streaming'),range(2)))
        self.assertEqual(results[0],results[1])
        self.assertEqual(len(self.calls),1)

    def test_different_voices_and_languages_have_separate_samples(self):
        a=preview.get_preview('capcut','vi','BV075_streaming')
        b=preview.get_preview('capcut','vi','BV560_streaming')
        c=preview.get_preview('capcut','ko',voices.default_voice('capcut','ko'))
        self.assertEqual(len({a,b,c}),3)
        self.assertEqual(self.calls[-1][0],voices.SAMPLES['ko'])

    def test_damaged_cache_is_recreated(self):
        path=preview.get_preview('capcut','vi','BV075_streaming')
        path.write_bytes(b'incomplete')
        preview.get_preview('capcut','vi','BV075_streaming')
        self.assertTrue(preview._ready(path))
        self.assertEqual(len(self.calls),2)

    def test_ui_cannot_submit_custom_sample_text(self):
        from storytoon.ui import build_app
        app=build_app()
        sample=next(c for c in app.blocks.values() if getattr(c,'label','')=='Nội dung nghe thử (cố định)')
        self.assertFalse(sample.interactive)
        callback=next(f for f in app.fns.values() if getattr(f.fn,'__name__','')=='preview')
        self.assertNotIn(sample,callback.inputs)


if __name__ == '__main__':
    unittest.main()
