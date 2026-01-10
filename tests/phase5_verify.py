import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Ensure import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from agent_core.tools.browser import BrowserTool
    from agent_core.tools.docker import DockerTool
except ImportError:
    print("Modules not found (Expected for TDD start)")

class TestExternalTools(unittest.TestCase):

    def setUp(self):
        print("\n--- Testing Phase 5 Tools ---")

    @patch('agent_core.tools.browser.requests.get')
    def test_browser_tool(self, mock_get):
        print("[1] Testing BrowserTool...")
        tool = BrowserTool()

        # Mock HTML response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body><h1>Error Fix</h1><p>Do sudo apt-get update</p></body></html>"
        mock_get.return_value = mock_response

        # Test Read
        content = tool.read_page("http://fake-url.com")
        print(f"    Fetched content: {content.strip()}")

        self.assertIn("Error Fix", content)
        self.assertIn("sudo apt-get update", content)
        self.assertNotIn("<html>", content, "Should strip HTML tags")

    @patch('agent_core.tools.docker.docker')
    def test_docker_tool(self, mock_docker_module):
        print("[2] Testing DockerTool...")

        # Mock Docker Client and Image Build
        mock_client = MagicMock()
        mock_docker_module.from_env.return_value = mock_client

        # Mock build logs stream (generator)
        mock_build_logs = [
            {"stream": "Step 1/3 : FROM python:3.9\n"},
            {"stream": "Step 2/3 : RUN echo hello\n"},
            {"stream": "Successfully built abc12345\n"}
        ]
        mock_client.api.build.return_value = mock_build_logs

        # Need to also patch DOCKER_SDK_AVAILABLE
        import agent_core.tools.docker as docker_module
        original_available = docker_module.DOCKER_SDK_AVAILABLE
        docker_module.DOCKER_SDK_AVAILABLE = True

        try:
            tool = DockerTool()

            # Test Build Streaming
            print("    Simulating Docker Build...")
            logs = []
            for line in tool.build_image(path="./", tag="test-image"):
                sys.stdout.write(f"    [Docker Log] {line}")
                logs.append(line)

            self.assertTrue(len(logs) >= 3)
            self.assertIn("FROM python:3.9", logs[0])
            self.assertIn("Successfully built", logs[-1])
        finally:
            docker_module.DOCKER_SDK_AVAILABLE = original_available

if __name__ == '__main__':
    unittest.main()
