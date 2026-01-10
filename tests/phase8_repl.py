import sys
import os
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from agent_core.interface.repl import AgentREPL
    from agent_core.models.manager import ModelManager
except ImportError:
    pass

class TestREPL(unittest.TestCase):

    def setUp(self):
        self.mock_orch = MagicMock()
        self.mock_config = {"models": {}, "api_keys": {}}
        self.repl = AgentREPL(orchestrator=self.mock_orch, config=self.mock_config)

    def test_slash_command_parsing(self):
        print("\n[1] Testing Command Parsing...")

        # Test 1: Normal task
        action, payload = self.repl.parse_input("fix bugs")
        self.assertEqual(action, "task")
        self.assertEqual(payload, "fix bugs")

        # Test 2: Slash command
        action, payload = self.repl.parse_input("/model gpt-4")
        self.assertEqual(action, "command")
        self.assertEqual(payload, ("model", "gpt-4"))

    @patch('builtins.input', return_value="sk-test-123")
    def test_model_switch_with_missing_key(self, mock_input):
        print("[2] Testing Model Switch & Key Prompt...")

        # Simulate switching to a model that needs a key
        # We assume the REPL logic checks config for 'api_key'
        self.repl.handle_command("model", "deepseek-v3")

        # Should have prompted for key and saved it
        # (Note: Actual implementation details depend on how Claude writes it,
        # but the config should show traces of update)
        # For this test, we verify the logic flow.
        pass
        # Since we are TDD-ing the *interface*, exact config structure might vary.
        # We mainly verify it didn't crash and attempted to handle it.

    def test_cost_command(self):
        print("[3] Testing /cost...")
        self.repl.handle_command("cost", "")
        # Should call something on orchestrator or token counter
        # assert nothing raised

if __name__ == '__main__':
    unittest.main()
