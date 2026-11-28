"""Music/SFX library: catalog integrity, context aliases, track rotation, ambience runs, prompt + cleanup."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from storytoon import paths
from storytoon.audio import library, mixer
from storytoon.schema import Line, Shot, Storyboard
from storytoon.script import vocab

MUSIC_CAT = paths.MUSIC / 'catalog.json'
SFX_CAT = paths.SFX / 'catalog.json'
FREE_SOURCES = ('https://commons.wikimedia.org/', 'https://archive.org/details/freepd', 'https://freesound.org/')


@unittest.skipUnless(MUSIC_CAT.exists() and SFX_CAT.exists(), 'audio catalog not built')
class CatalogTests(unittest.TestCase):
    def test_every_mood_plays_a_real_free_track(self):
        cat = json.loads(MUSIC_CAT.read_text(encoding='utf-8'))['moods']
        self.assertEqual(set(cat), set(vocab.MUSIC_MOODS))
        self.assertGreaterEqual(sum(len(e['tracks']) for e in cat.values()), 25)
        library_files = {paths.MUSIC / t['file'] for e in cat.values() for t in e['tracks']}
        for mood in vocab.MUSIC_MOODS:      # mood thiếu bài mượn bài thật của mood gần nhất
            self.assertIn(mixer.resolve_music(mood, 0, 'x'), library_files, mood)
        for mood, entry in cat.items():
            self.assertTrue(entry['use'])
            for t in entry['tracks']:
                self.assertTrue((paths.MUSIC / t['file']).exists(), t['file'])
                self.assertRegex(t['license'].lower(), r'cc0|public domain|pd')
                self.assertTrue(t['source'].startswith(FREE_SOURCES), t['source'])

    def test_every_sound_exists_has_use_and_free_source(self):
        sounds = json.loads(SFX_CAT.read_text(encoding='utf-8'))['sounds']
        self.assertGreaterEqual(len(sounds), 50)
        aliases = {}
        for key, entry in sounds.items():
            self.assertTrue((paths.SFX / entry['file']).exists(), key)
            self.assertIn(entry['kind'], ('oneshot', 'ambience'))
            self.assertTrue(entry['use'], key)
            src = entry['source']
            self.assertTrue(src.get('generated') or src['page'].startswith(FREE_SOURCES), key)
            self.assertRegex(src['license'].lower(), r'cc0|public domain|pd')
            for a in entry['aliases']:
                self.assertNotIn(a, sounds, f'alias {a} shadows a sound')
                self.assertNotIn(a, aliases, f'alias {a} used twice')
                aliases[a] = key

    def test_context_names_resolve(self):
        for name, key in {'knock': 'door_knock', 'siren': 'police_siren', 'crickets': 'night_insects',
                          'storm': 'rain_storm', 'ringtone': 'phone_ringtone', 'heart': 'heartbeat',
                          'Rain': 'rain', 'server hum': 'server_room'}.items():
            self.assertEqual(library.known_sfx(name), key, name)
        self.assertIsNone(library.known_sfx('spaceship_laser_xyz'))
        self.assertEqual(library.sfx('rain').kind, 'ambience')
        self.assertEqual(library.sfx('scream').kind, 'oneshot')

    def test_music_rotates_tracks_within_a_mood(self):
        picks = [mixer.resolve_music('horror', nth, 'Phim A') for nth in range(3)]
        self.assertEqual(len(set(picks)), 3)
        self.assertEqual(mixer.resolve_music('ghost', 0, 'Phim A'), picks[0])   # alias → horror
        self.assertIn(mixer.resolve_music('police', 0, 'x'), library.music_tracks('investigation'))

    def test_prompt_lists_library_with_usage(self):
        from storytoon.script import prompts
        self.assertIn('door_knock:', prompts.SYSTEM_PROMPT)
        self.assertIn('investigation:', prompts.SYSTEM_PROMPT)
        self.assertIn('âm nền', prompts.SYSTEM_PROMPT)

    def test_postprocess_keeps_only_library_sounds(self):
        from storytoon.script.postprocess import _clean_sfx
        self.assertEqual(_clean_sfx(['Knock', 'laser_gun_xyz', 'Rain', 'rain', 'siren']), ['door_knock', 'rain'])

    def test_mood_none_is_kept_as_music_off(self):
        from storytoon.script.postprocess import _clamp_mood
        self.assertEqual(_clamp_mood('silence'), vocab.MUSIC_OFF)
        self.assertEqual(_clamp_mood('chase'), 'action')
        self.assertIsNone(_clamp_mood('banana'))


@unittest.skipUnless(SFX_CAT.exists(), 'audio catalog not built')
class AmbienceRunTests(unittest.TestCase):
    def test_consecutive_shots_merge_into_one_run(self):
        shots = [Shot(id=f's{i}', location='x', duration=2.0, sfx=s, lines=[Line(text='a')])
                 for i, s in enumerate([['rain'], ['rain', 'door_knock'], ['rainy'], [], ['rain']])]
        runs = mixer.ambience_runs(Storyboard(title='t', shots=shots))
        self.assertEqual(runs, [('rain', 0.0, 6.0), ('rain', 8.0, 10.0)])


def _shots(spec):
    return Storyboard(title='t', shots=[Shot(id=f's{i}', location='x', duration=d, min_duration=d, music_mood=m)
                                        for i, (d, m) in enumerate(spec)])


class MusicCueTests(unittest.TestCase):
    def test_cue_stops_after_max_then_silence(self):
        sb = _shots([(30, 'tense')] + [(30, None)] * 4)          # 150 s, mood đặt 1 lần
        self.assertEqual(mixer.music_segments(sb, cue_max=75, rest=20), [('tense', 0.0, 90.0)])

    def test_none_stops_and_same_mood_needs_rest(self):
        sb = _shots([(20, 'horror'), (20, 'none'), (10, 'horror'), (30, None), (20, 'horror'), (20, 'sad')])
        # horror 0-20; none → lặng; horror lại sau 0 s? cần nghỉ 20 s: tại 40 (cách 20 s) được mở lại
        self.assertEqual(mixer.music_segments(sb, cue_max=75, rest=20),
                         [('horror', 0.0, 20.0), ('horror', 40.0, 100.0), ('sad', 100.0, 120.0)])

    def test_rest_blocks_immediate_restart(self):
        sb = _shots([(80, 'tense'), (5, 'tense'), (40, None)])
        self.assertEqual(mixer.music_segments(sb, cue_max=75, rest=20), [('tense', 0.0, 80.0)])


@unittest.skipUnless(SFX_CAT.exists(), 'audio catalog not built')
class LevelTests(unittest.TestCase):
    def test_sfx_quieter_than_voice_and_clipped_to_shot(self):
        import tempfile
        import numpy as np
        from storytoon.audio import audio_io, tts
        sr = audio_io.SR
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            t = np.arange(int(2.0 * sr)) / sr
            speech = 0.25 * np.sin(2 * np.pi * 220 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 3 * t))
            audio_io.write_wav(d / 'v.wav', speech)
            shots = [Shot(id='s1', location='x', duration=3.0, min_duration=3.0, sfx=['police_siren'],
                          lines=[Line(text='a', audio='v.wav', start=0.2, duration=2.0)]),
                     Shot(id='s2', location='x', duration=3.0, min_duration=3.0)]
            out = mixer.build_soundtrack(Storyboard(title='t', shots=shots), d, d / 'mix.wav', music=False)
            x, _ = audio_io.read_wav(out)
            voice_db = mixer.active_rms_db(speech.astype(np.float32))
            tail = x[int(3.5 * sr):]                       # siren 12 s nhưng shot chỉ 3 s (+0.4 đuôi)
            self.assertLess(float(np.abs(tail).max()), 1e-3)
            siren_only = x[int(2.3 * sr):int(3.0 * sr)]     # sau lời, trước khi tắt dần
            self.assertLess(mixer.active_rms_db(siren_only), voice_db - 6)


if __name__ == '__main__':
    unittest.main()
