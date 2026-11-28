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
        self.assertEqual(_clean_sfx(['Knock', 'rain', 'laser_gun_xyz', 'rain', 'siren', 'thunder']),
                         ['door_knock', 'rain', 'police_siren'])


@unittest.skipUnless(SFX_CAT.exists(), 'audio catalog not built')
class AmbienceRunTests(unittest.TestCase):
    def test_consecutive_shots_merge_into_one_run(self):
        shots = [Shot(id=f's{i}', location='x', duration=2.0, sfx=s, lines=[Line(text='a')])
                 for i, s in enumerate([['rain'], ['rain', 'door_knock'], ['rainy'], [], ['rain']])]
        runs = mixer.ambience_runs(Storyboard(title='t', shots=shots))
        self.assertEqual(runs, [('rain', 0.0, 6.0), ('rain', 8.0, 10.0)])


if __name__ == '__main__':
    unittest.main()
