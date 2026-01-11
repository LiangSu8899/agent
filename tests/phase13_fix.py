import sys
import os
import json
import unittest
import tempfile
import shutil
import yaml
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agent_core.config import ConfigManager, DEFAULT_CONFIG
from agent_core.agent import DebugAgent, AgentState, StepResult
from agent_core.orchestrator import AgentOrchestrator


class TestConfigLoadingPriority(unittest.TestCase):
    """Test that config file content takes priority over defaults."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.global_dir = os.path.join(self.test_dir, ".agent_os")
        os.makedirs(self.global_dir, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_file_models_take_priority(self):
        """Test that models from file are NOT overwritten by defaults."""
        print("\n[1] Testing file models take priority over defaults...")

        # Create a config file with custom models
        config_path = os.path.join(self.global_dir, "config.yaml")
        custom_config = {
            "models": {
                "my-custom-model": {
                    "type": "custom",
                    "description": "My custom model",
                    "cost_input": 99.99,
                    "cost_output": 99.99
                },
                "another-model": {
                    "type": "local",
                    "description": "Another model",
                    "cost_input": 0.0,
                    "cost_output": 0.0
                }
            },
            "roles": {
                "planner": "my-custom-model",
                "coder": "another-model"
            }
        }

        with open(config_path, 'w') as f:
            yaml.dump(custom_config, f)

        # Load config
        cm = ConfigManager(global_dir=self.global_dir)
        config = cm.load_global_config()

        # Custom models should be present
        self.assertIn("my-custom-model", config.get("models", {}))
        self.assertIn("another-model", config.get("models", {}))

        # Custom model values should be preserved
        self.assertEqual(config["models"]["my-custom-model"]["cost_input"], 99.99)
        self.assertEqual(config["models"]["my-custom-model"]["type"], "custom")

        # Roles should be preserved from file
        self.assertEqual(config["roles"]["planner"], "my-custom-model")
        self.assertEqual(config["roles"]["coder"], "another-model")

    def test_file_model_values_not_overwritten(self):
        """Test that existing model values are not overwritten by defaults."""
        print("[2] Testing file model values are not overwritten...")

        # Create a config with a model that has same name as default but different values
        config_path = os.path.join(self.global_dir, "config.yaml")
        custom_config = {
            "models": {
                "deepseek-v3": {
                    "type": "deepseek",
                    "description": "My modified DeepSeek",
                    "api_base": "https://my-proxy.com/v1",
                    "api_key": "my-secret-key",
                    "cost_input": 0.01,
                    "cost_output": 0.02
                }
            },
            "roles": {
                "planner": "deepseek-v3",
                "coder": "deepseek-v3"
            }
        }

        with open(config_path, 'w') as f:
            yaml.dump(custom_config, f)

        # Load config
        cm = ConfigManager(global_dir=self.global_dir)
        config = cm.load_global_config()

        # File values should take priority
        model = config["models"]["deepseek-v3"]
        self.assertEqual(model["api_base"], "https://my-proxy.com/v1")
        self.assertEqual(model["api_key"], "my-secret-key")
        self.assertEqual(model["cost_input"], 0.01)
        self.assertEqual(model["description"], "My modified DeepSeek")

    def test_defaults_fill_missing_keys(self):
        """Test that defaults fill in missing keys but don't overwrite."""
        print("[3] Testing defaults fill missing keys...")

        # Create a minimal config
        config_path = os.path.join(self.global_dir, "config.yaml")
        minimal_config = {
            "models": {
                "my-model": {
                    "type": "custom"
                }
            }
        }

        with open(config_path, 'w') as f:
            yaml.dump(minimal_config, f)

        # Load config
        cm = ConfigManager(global_dir=self.global_dir)
        config = cm.load_global_config()

        # Custom model should be present
        self.assertIn("my-model", config.get("models", {}))

        # Default sections should be filled in
        self.assertIn("system", config)
        self.assertIn("session", config)
        self.assertIn("security", config)

    def test_mock_only_config_upgraded(self):
        """Test that mock-only configs are still upgraded."""
        print("[4] Testing mock-only config upgrade...")

        # Create a mock-only config
        config_path = os.path.join(self.global_dir, "config.yaml")
        mock_config = {
            "models": {
                "mock": {
                    "type": "mock",
                    "cost_input": 0,
                    "cost_output": 0
                }
            },
            "roles": {
                "planner": "mock",
                "coder": "mock"
            }
        }

        with open(config_path, 'w') as f:
            yaml.dump(mock_config, f)

        # Load config
        cm = ConfigManager(global_dir=self.global_dir)
        config = cm.load_global_config()

        # Should have production models added
        self.assertIn("deepseek-v3", config.get("models", {}))
        self.assertIn("glm-4-plus", config.get("models", {}))


class TestNaturalLanguageEntryPoint(unittest.TestCase):
    """Test that natural language tasks go through the planner, not directly to shell."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test.db")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_agent_receives_initial_goal(self):
        """Test that DebugAgent.run() receives initial_goal parameter."""
        print("\n[5] Testing agent receives initial_goal...")

        # Create a mock planner that returns a command
        mock_planner = MagicMock()
        mock_planner.generate.return_value = json.dumps({
            "thought": "I need to create a directory for the snake game",
            "command": "mkdir snake_game",
            "reasoning": "First step is to create the project directory"
        })

        # Create agent with mock planner
        agent = DebugAgent(max_steps=1)
        agent.set_planner(mock_planner)

        # Mock session manager to avoid actual execution
        agent.session_manager = MagicMock()
        agent.session_manager.create_session.return_value = "test-session"
        agent.session_manager.get_status.return_value = "COMPLETED"
        agent.session_manager.get_logs.return_value = ""

        # Run with initial_goal
        results = agent.run(initial_goal="Help me write a snake game")

        # Verify planner was called
        self.assertTrue(mock_planner.generate.called)

        # Verify the prompt contains the goal
        call_args = mock_planner.generate.call_args[0][0]
        self.assertIn("snake game", call_args.lower())
        self.assertIn("INITIAL", call_args)

    def test_planner_converts_nl_to_command(self):
        """Test that planner converts natural language to shell command."""
        print("[6] Testing planner converts NL to command...")

        # Create a mock planner
        mock_planner = MagicMock()
        mock_planner.generate.return_value = json.dumps({
            "thought": "Creating project structure",
            "command": "mkdir -p snake_game/src",
            "reasoning": "Setting up directory structure"
        })

        agent = DebugAgent(max_steps=1)
        agent.set_planner(mock_planner)

        # Mock session manager
        agent.session_manager = MagicMock()
        agent.session_manager.create_session.return_value = "test-session"
        agent.session_manager.get_status.return_value = "COMPLETED"
        agent.session_manager.get_logs.return_value = ""

        # Run step
        result = agent.run_step("Help me write a snake game", is_initial=True)

        # Verify command is a shell command, not the NL input
        self.assertEqual(result.command, "mkdir -p snake_game/src")
        self.assertNotEqual(result.command, "Help me write a snake game")

    def test_task_not_passed_directly_to_shell(self):
        """Test that natural language is NOT passed directly to shell."""
        print("[7] Testing NL not passed directly to shell...")

        # Create a mock planner
        mock_planner = MagicMock()
        mock_planner.generate.return_value = json.dumps({
            "thought": "First step",
            "command": "echo 'Starting snake game project'",
            "reasoning": "Acknowledge the task"
        })

        agent = DebugAgent(max_steps=1)
        agent.set_planner(mock_planner)

        # Track what commands are passed to session_manager
        created_commands = []
        mock_session_manager = MagicMock()
        mock_session_manager.create_session.side_effect = lambda command: (
            created_commands.append(command) or "test-session"
        )
        mock_session_manager.get_status.return_value = "COMPLETED"
        mock_session_manager.get_logs.return_value = ""

        agent.session_manager = mock_session_manager

        # Run with NL task
        agent.run(initial_goal="Help me write a snake game")

        # Verify the NL task was NOT passed directly to shell
        for cmd in created_commands:
            self.assertNotEqual(cmd, "Help me write a snake game")
            # The command should be what the planner returned
            self.assertIn("echo", cmd)


class TestOrchestratorAgentIntegration(unittest.TestCase):
    """Test that Orchestrator properly uses DebugAgent for NL tasks."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test.db")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_orchestrator_creates_agent_for_task(self):
        """Test that orchestrator creates a DebugAgent for tasks."""
        print("\n[8] Testing orchestrator creates agent for task...")

        config = {
            "models": {
                "test-model": {"type": "mock"}
            },
            "roles": {
                "planner": "test-model",
                "coder": "test-model"
            }
        }

        orchestrator = AgentOrchestrator(db_path=self.db_path, config=config)

        # Create a task
        session_id = orchestrator.create_task("Help me write a snake game")

        # Verify agent was created
        self.assertIn(session_id, orchestrator._active_agents)
        self.assertIsInstance(orchestrator._active_agents[session_id], DebugAgent)

    def test_orchestrator_marks_task_as_nl(self):
        """Test that orchestrator marks task as natural language."""
        print("[9] Testing orchestrator marks task as NL...")

        config = {
            "models": {"test-model": {"type": "mock"}},
            "roles": {"planner": "test-model", "coder": "test-model"}
        }

        orchestrator = AgentOrchestrator(db_path=self.db_path, config=config)
        session_id = orchestrator.create_task("Help me debug this error")

        # Verify task is marked as NL
        session_info = orchestrator._active_sessions[session_id]
        self.assertTrue(session_info.get("is_natural_language", False))

    def test_orchestrator_session_command_prefixed(self):
        """Test that session command is prefixed to indicate agent task."""
        print("[10] Testing session command is prefixed...")

        config = {
            "models": {"test-model": {"type": "mock"}},
            "roles": {"planner": "test-model", "coder": "test-model"}
        }

        orchestrator = AgentOrchestrator(db_path=self.db_path, config=config)
        session_id = orchestrator.create_task("Help me write a snake game")

        # Get session from session manager
        sessions = orchestrator.session_manager.list_sessions()
        session = next((s for s in sessions if s["session_id"] == session_id), None)

        # Command should be prefixed
        self.assertIsNotNone(session)
        self.assertTrue(session["command"].startswith("[AGENT TASK]"))


class TestAgentPromptFlow(unittest.TestCase):
    """Test the agent prompt flow: Goal -> Planner -> Command."""

    def test_initial_prompt_contains_goal(self):
        """Test that initial prompt contains the user goal."""
        print("\n[11] Testing initial prompt contains goal...")

        agent = DebugAgent()
        prompt = agent._build_prompt(
            task="Help me write a snake game",
            current_output="",
            is_initial=True
        )

        self.assertIn("snake game", prompt.lower())
        self.assertIn("INITIAL", prompt)
        self.assertIn("User Goal", prompt)

    def test_followup_prompt_different_from_initial(self):
        """Test that follow-up prompts are different from initial."""
        print("[12] Testing follow-up prompt differs from initial...")

        agent = DebugAgent()

        initial_prompt = agent._build_prompt(
            task="Help me write a snake game",
            current_output="",
            is_initial=True
        )

        followup_prompt = agent._build_prompt(
            task="Help me write a snake game",
            current_output="Directory created successfully",
            is_initial=False
        )

        # Initial should have INITIAL marker
        self.assertIn("INITIAL", initial_prompt)

        # Follow-up should not have INITIAL marker
        self.assertNotIn("INITIAL", followup_prompt)

        # Follow-up should have current output
        self.assertIn("Directory created", followup_prompt)

    def test_first_step_uses_initial_flag(self):
        """Test that first step uses is_initial=True."""
        print("[13] Testing first step uses initial flag...")

        # Track prompts
        prompts_received = []

        mock_planner = MagicMock()
        def capture_prompt(prompt):
            prompts_received.append(prompt)
            return json.dumps({
                "thought": "Done",
                "command": "DONE",
                "reasoning": "Task complete"
            })

        mock_planner.generate.side_effect = capture_prompt

        agent = DebugAgent(max_steps=1)
        agent.set_planner(mock_planner)

        # Run
        agent.run(initial_goal="Test task")

        # First prompt should have INITIAL
        self.assertTrue(len(prompts_received) > 0)
        self.assertIn("INITIAL", prompts_received[0])


class TestBackwardCompatibility(unittest.TestCase):
    """Test backward compatibility with existing code."""

    def test_agent_run_accepts_task_parameter(self):
        """Test that agent.run() still accepts 'task' parameter."""
        print("\n[14] Testing backward compatibility with 'task' parameter...")

        mock_planner = MagicMock()
        mock_planner.generate.return_value = json.dumps({
            "thought": "Done",
            "command": "DONE",
            "reasoning": "Complete"
        })

        agent = DebugAgent(max_steps=1)
        agent.set_planner(mock_planner)

        # Should work with 'task' parameter (old style)
        results = agent.run(task="Old style task")

        self.assertTrue(len(results) > 0)
        self.assertTrue(mock_planner.generate.called)


if __name__ == '__main__':
    unittest.main()
