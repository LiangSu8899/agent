import sys
import os
import json
import unittest
from unittest.mock import patch, MagicMock
import shutil
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from agent_core.project import ProjectManager
    from agent_core.utils.paths import get_global_config_path
except ImportError:
    pass

class TestProjectManagement(unittest.TestCase):

    def setUp(self):
        # Create temp directories for testing
        self.test_dir = tempfile.mkdtemp()
        self.mock_home = os.path.join(self.test_dir, "mock_home")
        self.global_dir = os.path.join(self.mock_home, ".agent_os")
        self.project_dir = os.path.join(self.test_dir, "my_project")

        # Setup directories
        os.makedirs(self.global_dir, exist_ok=True)
        os.makedirs(self.project_dir, exist_ok=True)

        self.pm = ProjectManager(global_dir=self.global_dir)

    def tearDown(self):
        # Clean up temp directories
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_global_state_persistence(self):
        print("\n[1] Testing Last Project Persistence...")
        # Save last project
        self.pm.set_last_project(self.project_dir)

        # Check file exists
        state_file = os.path.join(self.global_dir, "state.json")
        self.assertTrue(os.path.exists(state_file))

        # Load back
        last = self.pm.get_last_project()
        self.assertEqual(last, self.project_dir)

    def test_project_initialization(self):
        print("[2] Testing Project Initialization...")
        # Init project in the temp dir
        self.pm.init_project(self.project_dir)

        # Check if .agent folder created
        dot_agent = os.path.join(self.project_dir, ".agent")
        self.assertTrue(os.path.isdir(dot_agent))

        # Check if sessions db path is correct
        db_path = self.pm.get_session_db_path(self.project_dir)
        self.assertEqual(db_path, os.path.join(dot_agent, "sessions.db"))

    @patch('builtins.input', return_value='1') # Simulate user choosing "Init here"
    def test_startup_logic_no_project(self, mock_input):
        print("[3] Testing Startup Decision Logic...")
        # This logic usually resides in main.py, but we test the helper decision function here
        # Assuming ProjectManager has a resolve_startup_project(current_dir) method

        # Test case 1: No project anywhere - should suggest init
        result = self.pm.resolve_startup_project(self.project_dir)
        self.assertEqual(result["action"], "init")
        self.assertEqual(result["path"], os.path.abspath(self.project_dir))

    def test_startup_logic_existing_project(self):
        print("[4] Testing Startup with Existing Project...")
        # Initialize project first
        self.pm.init_project(self.project_dir)

        # Now resolve should find it
        result = self.pm.resolve_startup_project(self.project_dir)
        self.assertEqual(result["action"], "load")
        self.assertEqual(result["path"], os.path.abspath(self.project_dir))

    def test_startup_logic_last_project(self):
        print("[5] Testing Startup with Last Project...")
        # Initialize and set as last project
        self.pm.init_project(self.project_dir)
        self.pm.set_last_project(self.project_dir)

        # Create a new directory without project
        new_dir = os.path.join(self.test_dir, "new_dir")
        os.makedirs(new_dir, exist_ok=True)

        # Resolve from new directory should ask
        result = self.pm.resolve_startup_project(new_dir)
        self.assertEqual(result["action"], "ask")
        self.assertEqual(result["current"], os.path.abspath(new_dir))
        self.assertEqual(result["last"], os.path.abspath(self.project_dir))

if __name__ == '__main__':
    unittest.main()
