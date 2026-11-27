"""CapCut integration contracts; no network or user project writes."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from storytoon.audio import audio_io, timing, tts, voices
from storytoon.audio.capcut import CapCutTTSEngine
from storytoon.schema import CharacterDef, Line, Shot, Storyboard


class CapCutTests(unittest.TestCase):
    def test_catalogs_and_language_boundaries(self):
        self.assertEqual([len(voices.catalog('capcut', lang)) for _,lang in voices.LANGUAGES], [32,3,3])
        self.assertFalse(voices.valid('BV075_streaming', 'capcut', 'ko'))
        for _,lang in voices.LANGUAGES:
            for engine in ('edge', 'capcut'):
                for gender in ('nam', 'nu'):
                    self.assertTrue(voices.valid(voices.default_voice(engine,lang,gender),engine,lang))
        with self.assertRaises(ValueError):
            voices.catalog('capcut','xx')

    def test_old_storyboard_voices_do_not_override_settings(self):
        board=Storyboard(title='test',characters=[
            CharacterDef(id='m',name='Nam',voice='vi-VN-NamMinhNeural'),
            CharacterDef(id='f',name='Nữ',gender='female',voice='vi-VN-HoaiMyNeural')])
        male=voices.catalog('capcut','vi')[1]['id']
        female=voices.default_voice('capcut','vi','nu')
        result=timing.build_voice_map(board,{'engine':'capcut','language':'vi',
            'default_male':male,'default_female':female,'narrator_voice':male})
        self.assertEqual(result['m'].voice,male)
        self.assertEqual(result['f'].voice,female)
        korean=timing.build_voice_map(board,{'engine':'capcut','language':'ko','default_male':male})
        self.assertTrue(voices.valid(korean['m'].voice,'capcut','ko'))

    def test_invalid_settings_rejected_before_save(self):
        voice=voices.default_voice('capcut','vi')
        self.assertEqual(voices.validate_settings('capcut','vi',voice,voice,voice,'20%'),'+20%')
        for rate in ('fast','-100%','+101%'):
            with self.assertRaises(ValueError):
                voices.validate_settings('capcut','vi',voice,voice,voice,rate)
        with self.assertRaises(ValueError):
            voices.validate_settings('capcut','ko',voice,voice,voice,'+0%')

    def test_audio_and_lipsync_cache_separated_by_engine(self):
        line=Line(text='Câu đọc');shot=Shot(id='s1',location='room')
        spec=timing.VoiceSpec('voice')
        self.assertNotEqual(timing._audio_name(shot,0,line,spec,'edge'),
                            timing._audio_name(shot,0,line,spec,'capcut:vi:v1'))

    def test_adapter_unicode_rate_cache_and_pcm_output(self):
        with tempfile.TemporaryDirectory(prefix='capcut_âm_') as tmp:
            root=Path(tmp)
            tone=root/'tone.mp3'
            audio_io.run_ffmpeg(['-f','lavfi','-i','sine=frequency=440:duration=2',str(tone)])
            payloads=[]
            real_run=subprocess.run
            def fake_node(args, **kwargs):
                if Path(args[0]).name != 'node.exe':
                    return real_run(args,**kwargs)
                payload=json.loads(kwargs['input']);payloads.append(payload)
                Path(payload['outPath']).write_bytes(tone.read_bytes())
                return subprocess.CompletedProcess(args,0,'','')
            engine=CapCutTTSEngine('vi')
            voice=voices.default_voice('capcut','vi')
            output=root/'đọc.wav'
            with patch('storytoon.audio.capcut.subprocess.run',side_effect=fake_node):
                run=lambda: tts.run_coro(tts.synth_line_async('Xin chào, tiếng Việt!',voice,output,
                                             rate='+50%',pitch='+8Hz',engine=engine))
                duration=run()
                self.assertGreater(duration,1.2);self.assertLess(duration,1.6)
                self.assertEqual(run(),duration)
            self.assertEqual(len(payloads),1)
            self.assertEqual(payloads[0]['text'],'Xin chào, tiếng Việt!')
            self.assertEqual(payloads[0]['lang'],'vi')
            self.assertTrue(tts.wav16_path(output).is_file())

    def test_errors_do_not_fall_back_to_another_voice(self):
        engine=CapCutTTSEngine('vi')
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'out.wav'
            with self.assertRaisesRegex(tts.TTSError,'ngôn ngữ'):
                tts.run_coro(engine.synth('test','not-a-voice',output,rate='+0%',pitch='+0Hz'))
            with patch('storytoon.audio.capcut.subprocess.run',return_value=subprocess.CompletedProcess([],1,'','Service unavailable')):
                with self.assertRaisesRegex(tts.TTSError,'Service unavailable'):
                    tts.run_coro(engine.synth('test','BV075_streaming',output,rate='+0%',pitch='+0Hz'))
            self.assertFalse(output.exists())


class VoiceUITests(unittest.TestCase):
    def test_select_language_refreshes_actual_voice_choices(self):
        from storytoon.ui import build_app
        app=build_app()
        refresh=next(f.fn for f in app.fns.values() if getattr(f.fn,'__name__','')=='refresh_voices')
        result=refresh('capcut','ko','vi-VN-NamMinhNeural','BV075_streaming','BV075_streaming')
        for dropdown in result[:3]:
            self.assertEqual(len(dropdown['choices']),3)
            self.assertTrue(voices.valid(dropdown['value'],'capcut','ko'))
        self.assertEqual(result[3],voices.SAMPLES['ko'])


if __name__ == '__main__':
    unittest.main()
