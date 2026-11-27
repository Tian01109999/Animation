"""The generator schema must preserve data fields named like JSON Schema metadata."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from storytoon.chatgpt import strict_schema
from storytoon.script.llm_schema import storyboard_response_schema


class SchemaTests(unittest.TestCase):
    def test_storyboard_and_overlay_titles_are_requested(self):
        for schema in (storyboard_response_schema(), strict_schema(storyboard_response_schema())):
            self.assertIn('title', schema['properties'])
            self.assertIn('title', schema['required'])
            overlay = schema['properties']['shots']['items']['properties']['overlays']['items']
            self.assertIn('title', overlay['properties'])
            self.assertIn('title', overlay['required'])

    def test_required_fields_always_exist_in_properties(self):
        def check(node):
            if isinstance(node, dict):
                if node.get('type') == 'object':
                    self.assertLessEqual(set(node.get('required', [])), set(node.get('properties', {})))
                for child in node.values():
                    check(child)
            elif isinstance(node, list):
                for child in node:
                    check(child)
        check(storyboard_response_schema())


if __name__ == '__main__':
    unittest.main()
