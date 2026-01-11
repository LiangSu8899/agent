import sys
import os
import json
import unittest
import tempfile
import shutil
import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agent_core.config import ConfigManager, DEFAULT_CONFIG
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
            "local-ollama"
        ]

        for model in required_models:
            self.assertIn(model, models, f"Missing model: {model}")

        # Check mock is NOT in default config
        self.assertNotIn("mock", models, "mock model should not be in DEFAULT_CONFIG")

    def test_default_config_roles(self):
        """Test that DEFAULT_CONFIG has correct role assignments."""
        print("[2] Testing DEFAULT_CONFIG role assignments...")

        roles = DEFAULT_CONFIG.get("roles", {})

        # Both should default to deepseek-v3
        self.assertEqual(roles.get("planner"), "deepseek-v3")
        self.assertEqual(roles.get("coder"), "deepseek-v3")

    def test_default_config_model_prices(self):
        """Test that models have cost_input and cost_output."""
        print("[3] Testing model pricing in DEFAULT_CONFIG...")

        models = DEFAULT_CONFIG.get("models", {})

        for name, config in models.items():
            self.assertIn("cost_input", config, f"{name} missing cost_input")
            self.assertIn("cost_output", config, f"{name} missing cost_output")

    def test_default_config_uses_openai_type(self):
        """Test that all API models use openai type."""
        print("[4] Testing all models use openai type...")

        models = DEFAULT_CONFIG.get("models", {})

        for name, config in models.items():
            self.assertEqual(config.get("type"), "openai", f"{name} should have type=openai")


class TestPhase11ConfigProximityLoading(unittest.TestCase):
    """Test the proximity-based config loading."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.global_dir = os.path.join(self.test_dir, ".agent_os")
        self.local_dir = os.path.join(self.test_dir, "project")
        os.makedirs(self.global_dir, exist_ok=True)
        os.makedirs(self.local_dir, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_local_config_takes_priority(self):
        """Test that local config takes priority over global."""
        print("\n[5] Testing local config takes priority...")

        # Create global config
        global_config_path = os.path.join(self.global_dir, "config.yaml")
        with open(global_config_path, 'w') as f:
            yaml.dump({"roles": {"planner": "global-model"}}, f)

        # Create local config
        local_config_path = os.path.join(self.local_dir, "config.yaml")
        with open(local_config_path, 'w') as f:
            yaml.dump({"roles": {"planner": "local-model"}}, f)

        # Load config - should use local
        cm = ConfigManager(global_dir=self.global_dir, cwd=self.local_dir)
        config = cm.load_config()

        self.assertEqual(config["roles"]["planner"], "local-model")
        self.assertEqual(str(cm.get_config_path()), local_config_path)

    def test_global_config_used_when_no_local(self):
        """Test that global config is used when no local exists."""
        print("[6] Testing global config used when no local...")

        # Create only global config
        global_config_path = os.path.join(self.global_dir, "config.yaml")
        with open(global_config_path, 'w') as f:
            yaml.dump({"roles": {"planner": "global-model"}}, f)

        # Load config - should use global
        cm = ConfigManager(global_dir=self.global_dir, cwd=self.local_dir)
        config = cm.load_config()

        self.assertEqual(config["roles"]["planner"], "global-model")
        self.assertEqual(str(cm.get_config_path()), global_config_path)

    def test_save_to_source(self):
        """Test that save_config writes to the source path."""
        print("[7] Testing save to source...")

        # Create local config
        local_config_path = os.path.join(self.local_dir, "config.yaml")
        with open(local_config_path, 'w') as f:
            yaml.dump({"roles": {"planner": "original"}}, f)

        # Load, modify, save
        cm = ConfigManager(global_dir=self.global_dir, cwd=self.local_dir)
        cm.load_config()
        cm.set("roles.planner", "modified")
        cm.save_config()

        # Verify saved to local
        with open(local_config_path, 'r') as f:
            saved = yaml.safe_load(f)

        self.assertEqual(saved["roles"]["planner"], "modified")

        # Verify NOT saved to global
        global_config_path = os.path.join(self.global_dir, "config.yaml")
        self.assertFalse(os.path.exists(global_config_path))


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
        print("\n[8] Testing load_or_init_project for new project...")

        result = self.pm.load_or_init_project(self.project_dir)

        self.assertTrue(result)
        self.assertTrue(self.pm.is_initialized(self.project_dir))
        self.assertEqual(self.pm.get_current_project(), self.project_dir)

    def test_load_or_init_existing_project(self):
        """Test load_or_init_project loads existing project."""
        print("[9] Testing load_or_init_project for existing project...")

        # Initialize first
        self.pm.init_project(self.project_dir)

        # Create new PM instance
        pm2 = ProjectManager(global_dir=self.global_dir)
        result = pm2.load_or_init_project(self.project_dir)

        self.assertTrue(result)
        self.assertEqual(pm2.get_current_project(), self.project_dir)

    def test_load_or_init_nonexistent_path(self):
        """Test load_or_init_project fails for nonexistent path."""
        print("[10] Testing load_or_init_project for nonexistent path...")

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
        print("\n[11] Testing REPL prompt format...")

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
        print("[12] Testing /project command registration...")

        self.assertIn("project", AgentREPL.COMMANDS)
        self.assertIn("projects", AgentREPL.COMMANDS)

    def test_handle_project_no_args(self):
        """Test /project with no args shows current project."""
        print("[13] Testing /project command with no args...")

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
        print("[14] Testing /project command project switching...")

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


if __name__ == '__main__':
    unittest.main()
