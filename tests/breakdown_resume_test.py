"""Breakdown saves each finished chunk and resumes only the missing chunks after a failure."""
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from storytoon import chatgpt, pipeline

bd = importlib.import_module('storytoon.script.breakdown')
chunking = importlib.import_module('storytoon.script.chunking')
SAMPLE = json.dumps({'title': 'T', 'characters': [{'id': 'an', 'name': 'An'}],
                     'locations': [{'id': 'pho', 'name': 'Phố'}],
                     'shots': [{'id': 's1', 'location': 'pho', 'narration': 'An đi qua phố.'}]})


class DEMO:  # minimal stand-in for a ChatGPT reply
    @staticmethod
    def read_text(encoding='utf-8'):
        return SAMPLE
PARA = 'Đoạn văn kịch bản thử nghiệm số {}. ' * 1 + 'Nhân vật đi qua con phố tối và nghe tiếng động lạ. ' * 30


def _script() -> str:
    return '\n\n'.join(PARA.format(i) for i in range(12))


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.text = _script()
        self.n = len(chunking.split_script(self.text, target_chars=1500, max_chars=1800))
        self.assertGreaterEqual(self.n, 3)

    def test_breakdown_skips_done_parts_and_reports_new_ones(self):
        saved = []
        def ok(contents):
            return DEMO.read_text(encoding='utf-8')
        calls = []
        def failing(contents):
            calls.append(1)
            if len(calls) == 3:
                raise RuntimeError('Phiên ChatGPT cần đăng nhập lại')
            return ok(contents)
        with self.assertRaises(RuntimeError):
            bd.breakdown(self.text, chunk_chars=1500, generate_text=failing,
                         on_part=lambda i, n, d: saved.append(d))
        self.assertEqual(len(saved), 2)
        calls2 = []
        def counting(contents):
            calls2.append(1)
            return ok(contents)
        result = bd.breakdown(self.text, chunk_chars=1500, generate_text=counting, done_parts=saved)
        self.assertEqual(len(calls2), self.n - 2)
        self.assertTrue(result.shots)

    def test_pipeline_checkpoint_resume_and_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            pr = pipeline.Project(Path(directory))
            pr.script.write_text(self.text, encoding='utf-8')
            calls = []
            def failing(contents):
                calls.append(1)
                if len(calls) == 3:
                    raise RuntimeError('login required')
                return DEMO.read_text(encoding='utf-8')
            real = bd.breakdown
            small = lambda *a, **k: real(*a, chunk_chars=1500, **k)
            with patch('storytoon.script.breakdown', small), patch.object(chatgpt, 'generate', side_effect=failing):
                with self.assertRaisesRegex(pipeline.PipelineError, 'tiếp tục từ đoạn 3'):
                    pipeline.step_breakdown(pr, lambda *a: None)
            ckpt = pr.dir / 'breakdown_parts.json'
            self.assertEqual(len(json.loads(ckpt.read_text(encoding='utf-8'))['parts']), 2)
            partial_sb, done, total = pipeline.breakdown_partial(pr)
            self.assertEqual((done, total), (2, self.n))
            self.assertEqual(len(partial_sb.shots), 2)
            from storytoon import ui
            with patch.object(pipeline, 'project', return_value=pr):
                msg, rows = ui._partial_view('x')
            self.assertIn('2/', msg)
            self.assertIn('đoạn 3', msg)
            self.assertEqual(len(rows), 2)
            pr.script.write_text(self.text + '\n\nThêm đoạn mới.', encoding='utf-8')
            self.assertIsNone(pipeline.breakdown_partial(pr))   # kịch bản đổi → bỏ qua phần cũ
            pr.script.write_text(self.text, encoding='utf-8')
            calls2 = []
            def ok(contents):
                calls2.append(1)
                return DEMO.read_text(encoding='utf-8')
            with patch('storytoon.script.breakdown', small), patch.object(chatgpt, 'generate', side_effect=ok):
                sb = pipeline.step_breakdown(pr, lambda *a: None)
            self.assertEqual(len(calls2), self.n - 2)
            self.assertTrue(sb.shots)
            self.assertFalse(ckpt.exists())
            self.assertTrue(pr.storyboard.exists())


if __name__ == '__main__':
    unittest.main()
