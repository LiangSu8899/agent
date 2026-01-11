import sys
import os
import json
import unittest
import tempfile
import shutil
import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agent_core.config import ConfigManager, DEFAULT_CONFIG, MOCK_ONLY_MODELS
from agent_core.project import ProjectManager
from agent_core.interface.repl import AgentREPL


class TestPhase11DefaultConfig(unittest.TestCase):
    """Test the updated default configuration."""

    def test_default_config_has_production_models(self):
        """Test that DEFAULT_CONFIG contains production models."""
        print("\n[1] Testing DEFAULT_CONFIG has production models...")

        models = DEFAULT_CONFIG.get("models", {})

        # Check required models exist
        required_models = [
            "deepseek-v3",
            "deepseek-coder",
            "glm-4-plus",
            "gpt-4o",
            "claude-3-5-sonnet",
            "local-deepseek-coder-v2"
        ]

        for model in required_models:
            self.assertIn(model, models, f"Missing model: {model}")

        # Check mock is NOT in default config
        self.assertNotIn("mock", models, "mock model should not be in DEFAULT_CONFIG")

    def test_default_config_roles(self):
        """Test that DEFAULT_CONFIG has correct role assignments."""
        print("[2] Testing DEFAULT_CONFIG role assignments...")

        roles = DEFAULT_CONFIG.get("roles", {})

        self.assertEqual(roles.get("planner"), "glm-4-plus")
        self.assertEqual(roles.get("coder"), "deepseek-v3")

    def test_default_config_model_prices(self):
        """Test that models have cost_input and cost_output."""
        print("[3] Testing model pricing in DEFAULT_CONFIG...")

        models = DEFAULT_CONFIG.get("models", {})

        for name, config in models.items():
            self.assertIn("cost_input", config, f"{name} missing cost_input")
            self.assertIn("cost_output", config, f"{name} missing cost_output")

            # Local models should be free
            if config.get("type") == "local":
                self.assertEqual(config["cost_input"], 0.0)
                self.assertEqual(config["cost_output"], 0.0)


class TestPhase11ConfigUpgrade(unittest.TestCase):
    """Test the config upgrade logic for mock-only configs."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.global_dir = os.path.join(self.test_dir, ".agent_os")
        os.makedirs(self.global_dir, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_mock_only_config_detection(self):
        """Test that mock-only configs are detected."""
        print("\n[4] Testing mock-only config detection...")

        cm = ConfigManager(global_dir=self.global_dir)

        # Create a mock-only config
        mock_config = {
            "models": {
                "mock": {"type": "mock", "cost_input": 0, "cost_output": 0}
            },
            "roles": {"planner": "mock", "coder": "mock"}
        }

        cm._config = mock_config
        self.assertTrue(cm._is_mock_only_config_dict(mock_config))

        # Config with real models should not be detected
        cm._config = DEFAULT_CONFIG.copy()
        self.assertFalse(cm._is_mock_only_config_dict(DEFAULT_CONFIG))

    def test_mock_config_upgrade(self):
        """Test that mock-only configs are upgraded on load."""
        print("[5] Testing mock config upgrade on load...")

        # Create a mock-only config file
        config_path = os.path.join(self.global_dir, "config.yaml")
        mock_config = {
            "models": {
                "mock": {"type": "mock", "cost_input": 0, "cost_output": 0}
            },
            "roles": {"planner": "mock", "coder": "mock"}
        }

        with open(config_path, 'w') as f:
            yaml.dump(mock_config, f)

        # Load config - should trigger upgrade
        cm = ConfigManager(global_dir=self.global_dir)
        config = cm.load_global_config()

        # Check that production models were added
        self.assertIn("deepseek-v3", config.get("models", {}))
        self.assertIn("glm-4-plus", config.get("models", {}))

        # Check roles were updated
        self.assertEqual(config["roles"]["planner"], "glm-4-plus")
        self.assertEqual(config["roles"]["coder"], "deepseek-v3")

    def test_non_mock_config_preserved(self):
        """Test that configs with real models are not overwritten."""
        print("[6] Testing non-mock config preservation...")

        # Create a config with custom models
        config_path = os.path.join(self.global_dir, "config.yaml")
        custom_config = {
            "models": {
                "my-custom-model": {"type": "openai", "cost_input": 1.0, "cost_output": 2.0}
            },
            "roles": {"planner": "my-custom-model", "coder": "my-custom-model"}
        }

        with open(config_path, 'w') as f:
            yaml.dump(custom_config, f)

        # Load config - should NOT trigger upgrade
        cm = ConfigManager(global_dir=self.global_dir)
        config = cm.load_global_config()

        # Custom model should still be there
        self.assertIn("my-custom-model", config.get("models", {}))

        # Roles should be preserved
        self.assertEqual(config["roles"]["planner"], "my-custom-model")


class TestPhase11ProjectManager(unittest.TestCase):
    """Test ProjectManager load_or_init_project method."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.global_dir = os.path.join(self.test_dir, ".agent_os")
        self.project_dir = os.path.join(self.test_dir, "my_project")

        os.makedirs(self.global_dir, exist_ok=True)
        os.makedirs(self.project_dir, exist_ok=True)

        self.pm = ProjectManager(global_dir=self.global_dir)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_load_or_init_new_project(self):
        """Test load_or_init_project initializes new project."""
        print("\n[7] Testing load_or_init_project for new project...")

        result = self.pm.load_or_init_project(self.project_dir)

        self.assertTrue(result)
        self.assertTrue(self.pm.is_initialized(self.project_dir))
        self.assertEqual(self.pm.get_current_project(), self.project_dir)

    def test_load_or_init_existing_project(self):
        """Test load_or_init_project loads existing project."""
        print("[8] Testing load_or_init_project for existing project...")

        # Initialize first
        self.pm.init_project(self.project_dir)

        # Create new PM instance
        pm2 = ProjectManager(global_dir=self.global_dir)
        result = pm2.load_or_init_project(self.project_dir)

        self.assertTrue(result)
        self.assertEqual(pm2.get_current_project(), self.project_dir)

    def test_load_or_init_nonexistent_path(self):
        """Test load_or_init_project fails for nonexistent path."""
        print("[9] Testing load_or_init_project for nonexistent path...")

        result = self.pm.load_or_init_project("/nonexistent/path")

        self.assertFalse(result)


class TestPhase11REPLPrompt(unittest.TestCase):
    """Test REPL prompt format and project commands."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.global_dir = os.path.join(self.test_dir, ".agent_os")
        self.project_dir = os.path.join(self.test_dir, "test_project")

        os.makedirs(self.global_dir, exist_ok=True)
        os.makedirs(self.project_dir, exist_ok=True)

        self.pm = ProjectManager(global_dir=self.global_dir)
        self.pm.init_project(self.project_dir)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_prompt_format(self):
        """Test that prompt shows project name and models."""
        print("\n[10] Testing REPL prompt format...")

        config = {
            "roles": {"planner": "glm-4-plus", "coder": "deepseek-v3"},
            "project": {"name": "test_project", "path": self.project_dir}
        }

        repl = AgentREPL(config=config, project_manager=self.pm)
        prompt = repl.get_prompt()

        # Check prompt contains project name
        self.assertIn("test_project", prompt)

        # Check prompt contains model names
        self.assertIn("Planner:", prompt)
        self.assertIn("Coder:", prompt)

    def test_project_command_registered(self):
        """Test that /project command is registered."""
        print("[11] Testing /project command registration...")

        self.assertIn("project", AgentREPL.COMMANDS)
        self.assertIn("projects", AgentREPL.COMMANDS)

    def test_handle_project_no_args(self):
        """Test /project with no args shows current project."""
        print("[12] Testing /project command with no args...")

        config = {
            "roles": {"planner": "test", "coder": "test"},
            "project": {"name": "test_project", "path": self.project_dir}
        }

        repl = AgentREPL(config=config, project_manager=self.pm)

        # Should return True and not crash
        result = repl._handle_project("")
        self.assertTrue(result)

    def test_handle_project_switch(self):
        """Test /project command switches project."""
        print("[13] Testing /project command project switching...")

        # Create another project directory
        other_project = os.path.join(self.test_dir, "other_project")
        os.makedirs(other_project, exist_ok=True)

        config = {
            "roles": {"planner": "test", "coder": "test"},
            "project": {"name": "test_project", "path": self.project_dir}
        }

        repl = AgentREPL(config=config, project_manager=self.pm)

        # Switch to other project
        result = repl._handle_project(other_project)
        self.assertTrue(result)

        # Check project was switched
        self.assertEqual(self.pm.get_current_project(), other_project)
        self.assertEqual(config["project"]["name"], "other_project")

    def test_handle_projects_list(self):
        """Test /projects command lists recent projects."""
        print("[14] Testing /projects command...")

        config = {
            "roles": {"planner": "test", "coder": "test"},
            "project": {"name": "test_project", "path": self.project_dir}
        }

        # Add some recent projects
        self.pm.add_to_recent_projects(self.project_dir)

        repl = AgentREPL(config=config, project_manager=self.pm)

        # Should return True and not crash
        result = repl._handle_projects("")
        self.assertTrue(result)


if __name__ == '__main__':
    unittest.main()
