from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from storytoon import pipeline,paths,activity

class ProjectDeleteTests(unittest.TestCase):
 def test_delete_removes_one_project_and_all_its_files(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp)/'projects';root.mkdir()
   chosen=root/'phim_1';(chosen/'shots').mkdir(parents=True)
   (chosen/'script.txt').write_text('story');(chosen/'shots/final.mp4').write_bytes(b'video')
   other=root/'demo';other.mkdir();(other/'script.txt').write_text('keep')
   with patch.object(paths,'PROJECTS',root):
    pipeline.delete_project('phim_1')
    self.assertEqual(pipeline.list_projects(),['demo'])
   self.assertFalse(chosen.exists())
   self.assertEqual((other/'script.txt').read_text(),'keep')

 def test_delete_rejects_paths_outside_project_root(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp)/'projects';root.mkdir()
   outside=Path(temp)/'keep';outside.mkdir()
   with patch.object(paths,'PROJECTS',root):
    for value in ('','..','.','../keep','..\\keep',str(outside)):
     with self.assertRaises(pipeline.PipelineError):pipeline.delete_project(value)
   self.assertTrue(outside.exists())

 def test_busy_app_cannot_delete_and_missing_project_is_clear(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/'demo').mkdir()
   with patch.object(paths,'PROJECTS',root):
    with activity.work(),self.assertRaisesRegex(RuntimeError,'đang xử lý'):
     pipeline.delete_project('demo')
    self.assertTrue((root/'demo').exists())
    pipeline.delete_project('demo')
    self.assertEqual(pipeline.list_projects(),[])
    with self.assertRaisesRegex(pipeline.PipelineError,'không còn tồn tại'):
     pipeline.delete_project('demo')

 def test_linked_project_is_rejected(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/'demo').mkdir()
   with patch.object(paths,'PROJECTS',root),patch.object(Path,'is_junction',return_value=True):
    with self.assertRaisesRegex(pipeline.PipelineError,'liên kết'):pipeline.delete_project('demo')
   self.assertTrue((root/'demo').exists())

if __name__=='__main__':unittest.main()
