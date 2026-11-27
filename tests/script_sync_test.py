from pathlib import Path
import sys,tempfile,unittest,json
from unittest.mock import patch
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from storytoon import pipeline,chatgpt
from storytoon.schema import Storyboard,Shot,Line

class SyncTests(unittest.TestCase):
 def test_changed_script_refreshes_saved_storyboard_unchanged_skips(self):
  with tempfile.TemporaryDirectory() as temp:
   pr=pipeline.Project(Path(temp))
   def generate(contents):
    return Storyboard(title=pr.script.read_text(encoding='utf-8'),shots=[Shot(id='s001',location='cho_dem',lines=[Line(text='Hello')])]).model_dump_json()
   with patch.object(chatgpt,'generate',side_effect=generate) as call:
    pr.script.write_text('Original script',encoding='utf-8')
    pipeline.run(pr.dir,['breakdown'])
    self.assertEqual(pipeline.load_storyboard(pr).title,'Original script')
    pipeline.run(pr.dir,['breakdown'])
    self.assertEqual(call.call_count,1)
    pr.script.write_text('Changed script',encoding='utf-8')
    pipeline.run(pr.dir,['breakdown'])
    self.assertEqual(call.call_count,2)
    self.assertEqual(pipeline.load_storyboard(pr).title,'Changed script')
    self.assertEqual(json.loads((pr.dir/'storyboard.bak.json').read_text(encoding='utf-8'))['title'],'Original script')

 def test_failed_refresh_preserves_last_valid_storyboard_and_hash(self):
  with tempfile.TemporaryDirectory() as temp:
   pr=pipeline.Project(Path(temp));pr.script.write_text('New',encoding='utf-8')
   pipeline.save_storyboard(pr,Storyboard(title='Old',shots=[]))
   original=pr.storyboard.read_bytes()
   with patch.object(chatgpt,'generate',side_effect=RuntimeError('offline')):
    with self.assertRaises(pipeline.PipelineError):pipeline.step_breakdown(pr,lambda *a:None)
   self.assertEqual(pr.storyboard.read_bytes(),original)
   self.assertIsNone(pipeline._State(pr).get('breakdown').get('input'))

 def test_logout_uses_only_app_oauth_home(self):
  with patch.object(chatgpt,'command',side_effect=lambda *a:['codex',*a]),patch.object(chatgpt,'connected',return_value=False),patch.object(chatgpt.subprocess,'run',return_value=SimpleNamespace(returncode=0)) as call:
   self.assertIn('Đã đăng xuất',chatgpt.logout())
   self.assertEqual(call.call_args.args[0],['codex','logout'])
   self.assertTrue(call.call_args.kwargs['env']['CODEX_HOME'].endswith('chatgpt-account'))

 def test_logout_cannot_interrupt_an_active_job(self):
  from storytoon import activity
  with activity.work(),patch.object(chatgpt.subprocess,'run') as call:
   self.assertIn('đang xử lý',chatgpt.logout())
   call.assert_not_called()

 def test_export_steps_check_script_even_without_breakdown_selected(self):
  with tempfile.TemporaryDirectory() as temp:
   pr=pipeline.Project(Path(temp));pr.script.write_text('Latest',encoding='utf-8')
   with patch.object(pipeline,'step_breakdown',side_effect=pipeline.PipelineError('must refresh')) as refresh,patch.object(pipeline,'step_audio') as audio:
    with self.assertRaisesRegex(pipeline.PipelineError,'must refresh'):pipeline.run(pr.dir,['audio'])
    refresh.assert_called_once()
    audio.assert_not_called()

if __name__=='__main__':unittest.main()
