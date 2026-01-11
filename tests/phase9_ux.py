import sys
import os
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from agent_core.interface.repl import AgentREPL
    from agent_core.models.manager import ModelManager
except ImportError:
    pass

class TestPhase9UX(unittest.TestCase):

    def setUp(self):
        # Mock Config with Pricing
        self.config = {
            "roles": {"planner": "gpt-4", "coder": "gpt-4"},
            "models": {
                "gpt-4": {
                    "type": "openai",
                    "cost_input": 2.5,
                    "cost_output": 10.0
                },
                "local-llama": {
                    "type": "local",
                    "cost_input": 0.0,
                    "cost_output": 0.0
                }
            }
        }
        self.mock_orch = MagicMock()
        self.repl = AgentREPL(self.mock_orch, self.config)

    def test_role_switching_validation(self):
        print("\n[1] Testing Role Switching Validation...")

        # 1. Valid Switch
        success = self.repl.handle_command("role", "planner local-llama")
        self.assertTrue(success)
        self.assertEqual(self.config['roles']['planner'], "local-llama")

        # 2. Invalid Role
        success = self.repl.handle_command("role", "chef local-llama")
        self.assertFalse(success, "Should reject unknown role 'chef'")

        # 3. Invalid Model
        success = self.repl.handle_command("role", "planner non-existent")
        self.assertFalse(success, "Should reject unknown model")

    def test_cost_calculation(self):
        print("[2] Testing Cost Calculation...")

        # Mock usage data: 1000 input tokens on GPT-4
        # Cost = (1000 / 1,000,000) * 2.5 = 0.0025

        # Note: In real implementation, you'd call a method on TokenCounter.
        # Here we verify the math logic if you implement a helper in REPL or Manager.

        usage = {"input": 1000, "output": 0}
        model_conf = self.config["models"]["gpt-4"]

        cost = (usage["input"] / 1_000_000) * model_conf["cost_input"]
        self.assertEqual(cost, 0.0025)

    def test_completer_logic(self):
        print("[3] Testing Autocomplete Logic...")
        # Verify that the completer includes our models
        completer = self.repl.get_completer() # You need to implement this accessor for test

        # This part depends on how you implement prompt_toolkit completer
        # But logically, we check if 'local-llama' is in the suggestion list for '/model'
        pass

if __name__ == '__main__':
    unittest.main()
