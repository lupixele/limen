"""Unit tests for agent/prompt.py following TDD."""
import unittest
from agent.prompt import SYSTEM_PROMPT, build_system_prompt, build_user_prompt


class TestPrompt(unittest.TestCase):
    def test_system_prompt_is_generic(self):
        self.assertNotIn("directory inventory", SYSTEM_PROMPT.lower())
        self.assertNotIn("file list", SYSTEM_PROMPT.lower())
        self.assertIn("agent", SYSTEM_PROMPT.lower())
        self.assertIn("tool", SYSTEM_PROMPT.lower())

    def test_build_system_prompt_with_tools(self):
        mock_tools = [
            {"function": {"name": "calculator", "description": "Safe math"}},
            {"function": {"name": "mock_lookup", "description": "Database query"}},
        ]
        prompt = build_system_prompt(mock_tools)
        self.assertIn("calculator", prompt)
        self.assertIn("mock_lookup", prompt)
        self.assertIn("decide", prompt.lower())

    def test_legacy_build_user_prompt_compatibility(self):
        # Should not throw when called with legacy signature
        res = build_user_prompt(files=[], user_instruction="calculate 2+2")
        self.assertIn("calculate 2+2", res)

        # Or called with generic text
        res2 = build_user_prompt(instruction="calculate 2+2")
        self.assertIn("calculate 2+2", res2)


if __name__ == "__main__":
    unittest.main()
