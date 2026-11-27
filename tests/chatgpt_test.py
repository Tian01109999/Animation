"""Verify OAuth routing, strict output, and that GPT does not call Gemini."""
import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from storytoon import chatgpt, pipeline
from storytoon.script.llm_schema import storyboard_response_schema

bd = importlib.import_module('storytoon.script.breakdown')
DEMO = Path(__file__).resolve().parents[1] / 'projects/demo/storyboard.json'


class ChatGPTTests(unittest.TestCase):
    def test_schema_is_strict_at_every_object(self):
        original = storyboard_response_schema()
        before = json.dumps(original)
        def check(node):
            if isinstance(node, dict):
                if node.get('type') == 'object':
                    self.assertIs(node['additionalProperties'], False)
                    self.assertEqual(set(node['required']), set(node.get('properties', {})))
                for value in node.values():
                    check(value)
            elif isinstance(node, list):
                for value in node:
                    check(value)
        check(chatgpt.strict_schema(original))
        self.assertEqual(json.dumps(original), before)

    def test_gpt_route_does_not_construct_gemini_client(self):
        calls = []
        def generate(contents):
            calls.append(contents)
            return DEMO.read_text(encoding='utf-8')
        result = bd.breakdown('Kịch bản thử.', generate_text=generate, provider_name='ChatGPT')
        self.assertTrue(result.shots)
        self.assertEqual(len(calls), 1)

    def test_generator_receives_json_repair_context(self):
        calls = []
        def generate(contents):
            calls.append(contents)
            return 'invalid' if len(calls) == 1 else DEMO.read_text(encoding='utf-8')
        result = bd.breakdown('Kịch bản thử.', generate_text=generate)
        self.assertTrue(result.shots)
        self.assertEqual(len(calls[1]), 3)

    def test_environment_uses_oauth_and_does_not_mutate_parent(self):
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'example', 'CODEX_API_KEY': 'example',
                                       'CODEX_ACCESS_TOKEN': 'example'}):
            env = chatgpt.environment()
            for name in ('OPENAI_API_KEY', 'CODEX_API_KEY', 'CODEX_ACCESS_TOKEN'):
                self.assertNotIn(name, env)
            self.assertIn('chatgpt-account', env['CODEX_HOME'])

    def test_api_key_login_is_not_reported_as_chatgpt(self):
        with patch.object(chatgpt, 'command', return_value=['codex']), patch.object(subprocess, 'run') as run:
            run.return_value = SimpleNamespace(returncode=0, stdout='Logged in using API key', stderr='')
            self.assertFalse(chatgpt.connected())
            run.return_value = SimpleNamespace(returncode=0, stdout='Logged in using ChatGPT', stderr='')
            self.assertTrue(chatgpt.connected())

    def test_generate_uses_stdin_and_validated_output_file(self):
        def execute(args, **kwargs):
            self.assertEqual(args[-1], '-')
            self.assertIn('--output-schema', args)
            self.assertIn('read-only', args)
            self.assertIn('Kịch bản', kwargs['input'])
            Path(args[args.index('--output-last-message') + 1]).write_text('{"ok":true}', encoding='utf-8')
            return SimpleNamespace(returncode=0, stderr='', stdout='')
        with patch.object(chatgpt, 'connected', return_value=True), patch.object(chatgpt, 'command',
                side_effect=lambda *args: ['codex', *args]), patch.object(subprocess, 'run', side_effect=execute):
            self.assertEqual(json.loads(chatgpt.generate('Kịch bản')), {'ok': True})

    def test_failed_gpt_run_keeps_existing_storyboard(self):
        with tempfile.TemporaryDirectory() as directory:
            pr = pipeline.Project(Path(directory))
            pr.script.write_text('Kịch bản', encoding='utf-8')
            pr.storyboard.write_text('existing storyboard', encoding='utf-8')
            with patch.object(pipeline.config, 'get', return_value='chatgpt'), patch.object(
                    chatgpt, 'generate', side_effect=RuntimeError('login required')):
                with self.assertRaisesRegex(pipeline.PipelineError, 'login required'):
                    pipeline.step_breakdown(pr, lambda *args: None, force=True)
            self.assertEqual(pr.storyboard.read_text(encoding='utf-8'), 'existing storyboard')


if __name__ == '__main__':
    unittest.main()
