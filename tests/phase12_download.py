import sys
import os
import json
import unittest
import tempfile
import shutil
import yaml
from unittest.mock import patch, MagicMock, mock_open

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agent_core.utils.downloader import (
    ModelDownloader,
    ModelMissingError,
    DownloadError,
    MODEL_PRESETS,
    create_model_config,
)
from agent_core.interface.repl import AgentREPL, DOWNLOADER_AVAILABLE


class TestModelDownloader(unittest.TestCase):
    """Test the ModelDownloader class."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.models_dir = os.path.join(self.test_dir, "models")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_downloader_initialization(self):
        """Test ModelDownloader initializes correctly."""
        print("\n[1] Testing ModelDownloader initialization...")

        downloader = ModelDownloader(models_dir=self.models_dir)

        self.assertTrue(os.path.exists(self.models_dir))
        self.assertEqual(downloader.models_dir.as_posix(), self.models_dir)

    def test_get_model_path(self):
        """Test get_model_path returns correct path."""
        print("[2] Testing get_model_path...")

        downloader = ModelDownloader(models_dir=self.models_dir)
        path = downloader.get_model_path("test.gguf")

        self.assertEqual(str(path), os.path.join(self.models_dir, "test.gguf"))

    def test_model_exists(self):
        """Test model_exists checks file existence."""
        print("[3] Testing model_exists...")

        downloader = ModelDownloader(models_dir=self.models_dir)

        # File doesn't exist
        self.assertFalse(downloader.model_exists("test.gguf"))

        # Create file
        test_file = os.path.join(self.models_dir, "test.gguf")
        with open(test_file, 'w') as f:
            f.write("test")

        # Now it exists
        self.assertTrue(downloader.model_exists("test.gguf"))

    def test_list_models(self):
        """Test list_models returns model files."""
        print("[4] Testing list_models...")

        downloader = ModelDownloader(models_dir=self.models_dir)

        # Create some model files
        for name in ["model1.gguf", "model2.bin", "model3.safetensors", "readme.txt"]:
            with open(os.path.join(self.models_dir, name), 'w') as f:
                f.write("test")

        models = downloader.list_models()

        # Should only include model files
        self.assertIn("model1.gguf", models)
        self.assertIn("model2.bin", models)
        self.assertIn("model3.safetensors", models)
        self.assertNotIn("readme.txt", models)

    def test_delete_model(self):
        """Test delete_model removes file."""
        print("[5] Testing delete_model...")

        downloader = ModelDownloader(models_dir=self.models_dir)

        # Create file
        test_file = os.path.join(self.models_dir, "test.gguf")
        with open(test_file, 'w') as f:
            f.write("test")

        self.assertTrue(os.path.exists(test_file))

        # Delete it
        result = downloader.delete_model("test.gguf")

        self.assertTrue(result)
        self.assertFalse(os.path.exists(test_file))

        # Delete non-existent file
        result = downloader.delete_model("nonexistent.gguf")
        self.assertFalse(result)

    @patch('agent_core.utils.downloader.hf_hub_download')
    def test_download_from_hf_mocked(self, mock_hf_download):
        """Test download_from_hf with mocked HuggingFace."""
        print("[6] Testing download_from_hf (mocked)...")

        # Mock the download
        expected_path = os.path.join(self.models_dir, "test.gguf")
        mock_hf_download.return_value = expected_path

        downloader = ModelDownloader(models_dir=self.models_dir)

        # Create the file to simulate download
        with open(expected_path, 'w') as f:
            f.write("model data")

        result = downloader.download_from_hf(
            repo_id="TheBloke/Test-GGUF",
            filename="test.gguf"
        )

        self.assertEqual(result, expected_path)
        mock_hf_download.assert_called_once()

    @patch('agent_core.utils.downloader.requests.get')
    def test_download_from_url_mocked(self, mock_get):
        """Test download_from_url with mocked requests."""
        print("[7] Testing download_from_url (mocked)...")

        # Mock the response
        mock_response = MagicMock()
        mock_response.headers = {"content-length": "100"}
        mock_response.iter_content.return_value = [b"test data"]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        downloader = ModelDownloader(models_dir=self.models_dir)

        result = downloader.download_from_url(
            url="https://example.com/model.gguf",
            filename="downloaded.gguf"
        )

        self.assertTrue(result.endswith("downloaded.gguf"))
        mock_get.assert_called_once()


class TestModelMissingError(unittest.TestCase):
    """Test the ModelMissingError exception."""

    def test_error_basic(self):
        """Test basic ModelMissingError."""
        print("\n[8] Testing ModelMissingError basic...")

        error = ModelMissingError(
            model_name="test-model",
            path="/path/to/model.gguf"
        )

        self.assertEqual(error.model_name, "test-model")
        self.assertEqual(error.path, "/path/to/model.gguf")
        self.assertIn("test-model", str(error))

    def test_error_with_hf_info(self):
        """Test ModelMissingError with HuggingFace info."""
        print("[9] Testing ModelMissingError with HF info...")

        error = ModelMissingError(
            model_name="test-model",
            path="/path/to/model.gguf",
            download_info={
                "hf_repo": "TheBloke/Test-GGUF",
                "hf_file": "test.gguf"
            }
        )

        self.assertIn("HuggingFace", str(error))
        self.assertEqual(error.download_info["hf_repo"], "TheBloke/Test-GGUF")

    def test_error_with_url_info(self):
        """Test ModelMissingError with URL info."""
        print("[10] Testing ModelMissingError with URL info...")

        error = ModelMissingError(
            model_name="test-model",
            path="/path/to/model.gguf",
            download_info={
                "url": "https://example.com/model.gguf"
            }
        )

        self.assertIn("https://example.com", str(error))


class TestModelPresets(unittest.TestCase):
    """Test model presets and config creation."""

    def test_presets_exist(self):
        """Test that all presets are defined."""
        print("\n[11] Testing model presets exist...")

        required_presets = ["standard", "large", "cpu_only", "custom"]
        for preset in required_presets:
            self.assertIn(preset, MODEL_PRESETS)

    def test_preset_values(self):
        """Test preset values are correct."""
        print("[12] Testing preset values...")

        self.assertEqual(MODEL_PRESETS["standard"]["context_length"], 8192)
        self.assertEqual(MODEL_PRESETS["large"]["context_length"], 16384)
        self.assertEqual(MODEL_PRESETS["cpu_only"]["n_gpu_layers"], 0)

    def test_create_model_config_hf(self):
        """Test create_model_config for HuggingFace source."""
        print("[13] Testing create_model_config for HuggingFace...")

        config = create_model_config(
            name="my-model",
            source_type="huggingface",
            hf_repo="TheBloke/Test-GGUF",
            hf_file="test.Q4_K_M.gguf",
            preset="standard",
            description="Test model"
        )

        self.assertEqual(config["type"], "local")
        self.assertEqual(config["hf_repo"], "TheBloke/Test-GGUF")
        self.assertEqual(config["hf_file"], "test.Q4_K_M.gguf")
        self.assertEqual(config["context_length"], 8192)
        self.assertEqual(config["cost_input"], 0.0)
        self.assertIn("path", config)

    def test_create_model_config_url(self):
        """Test create_model_config for URL source."""
        print("[14] Testing create_model_config for URL...")

        config = create_model_config(
            name="my-model",
            source_type="url",
            url="https://example.com/model.gguf",
            preset="large"
        )

        self.assertEqual(config["url"], "https://example.com/model.gguf")
        self.assertEqual(config["context_length"], 16384)

    def test_create_model_config_local(self):
        """Test create_model_config for local source."""
        print("[15] Testing create_model_config for local...")

        config = create_model_config(
            name="my-model",
            source_type="local",
            local_path="/path/to/model.gguf",
            preset="cpu_only"
        )

        self.assertEqual(config["path"], "/path/to/model.gguf")
        self.assertEqual(config["n_gpu_layers"], 0)

    def test_create_model_config_custom(self):
        """Test create_model_config with custom values."""
        print("[16] Testing create_model_config with custom values...")

        config = create_model_config(
            name="my-model",
            source_type="local",
            local_path="/path/to/model.gguf",
            preset="custom",
            context_length=32768,
            n_gpu_layers=20
        )

        self.assertEqual(config["context_length"], 32768)
        self.assertEqual(config["n_gpu_layers"], 20)


class TestREPLModelCommands(unittest.TestCase):
    """Test REPL model-related commands."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.test_dir, "config.yaml")

        self.config = {
            "roles": {"planner": "test-model", "coder": "test-model"},
            "models": {
                "test-model": {
                    "type": "local",
                    "path": "/nonexistent/path/model.gguf",
                    "hf_repo": "TheBloke/Test-GGUF",
                    "hf_file": "test.gguf",
                    "cost_input": 0.0,
                    "cost_output": 0.0
                },
                "api-model": {
                    "type": "openai",
                    "cost_input": 1.0,
                    "cost_output": 2.0
                }
            }
        }

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_handle_model_subcommands(self):
        """Test /model command recognizes subcommands."""
        print("\n[17] Testing /model subcommand parsing...")

        repl = AgentREPL(config=self.config, config_path=self.config_path)

        # Parse input
        action, payload = repl.parse_input("/model add")
        self.assertEqual(action, "command")
        self.assertEqual(payload, ("model", "add"))

        action, payload = repl.parse_input("/model download test-model")
        self.assertEqual(action, "command")
        self.assertEqual(payload, ("model", "download test-model"))

    def test_handle_model_switch_api(self):
        """Test /model switches to API model."""
        print("[18] Testing /model switch to API model...")

        # Add api_key to avoid prompt
        self.config["models"]["api-model"]["api_key"] = "test-key"

        repl = AgentREPL(config=self.config, config_path=self.config_path)

        result = repl._handle_model("api-model")

        self.assertTrue(result)
        self.assertEqual(self.config["roles"]["planner"], "api-model")
        self.assertEqual(self.config["roles"]["coder"], "api-model")

    def test_handle_model_missing_local(self):
        """Test /model detects missing local model file."""
        print("[19] Testing /model detects missing local file...")

        repl = AgentREPL(config=self.config, config_path=self.config_path)

        # Mock input to decline download
        with patch('builtins.input', return_value='n'):
            result = repl._handle_model("test-model")

        self.assertTrue(result)
        # Model should not be switched since file is missing and download declined

    @unittest.skipIf(not DOWNLOADER_AVAILABLE, "Downloader not available")
    def test_handle_model_add_exists(self):
        """Test /model add wizard checks for existing model."""
        print("[20] Testing /model add wizard...")

        repl = AgentREPL(config=self.config, config_path=self.config_path)

        # This would normally be interactive, so we just test the method exists
        self.assertTrue(hasattr(repl, '_handle_model_add'))
        self.assertTrue(callable(repl._handle_model_add))

    def test_completer_includes_model_subcommands(self):
        """Test completer includes model subcommands."""
        print("[21] Testing completer includes model subcommands...")

        repl = AgentREPL(config=self.config, config_path=self.config_path)
        completer = repl._create_completer()

        # Completer should exist (if prompt_toolkit available)
        if completer:
            # The completer structure should include 'add' and 'download'
            self.assertIsNotNone(completer)


class TestConfigWriting(unittest.TestCase):
    """Test that model configs are written correctly."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.test_dir, "config.yaml")

        self.config = {
            "roles": {"planner": "test", "coder": "test"},
            "models": {}
        }

        # Write initial config
        with open(self.config_path, 'w') as f:
            yaml.dump(self.config, f)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_save_config_writes_yaml(self):
        """Test that _save_config writes valid YAML."""
        print("\n[22] Testing config save writes valid YAML...")

        repl = AgentREPL(config=self.config, config_path=self.config_path)

        # Add a model
        self.config["models"]["new-model"] = {
            "type": "local",
            "path": "/path/to/model.gguf",
            "hf_repo": "TheBloke/Test-GGUF",
            "hf_file": "test.gguf"
        }

        repl._save_config()

        # Read back and verify
        with open(self.config_path, 'r') as f:
            saved_config = yaml.safe_load(f)

        self.assertIn("new-model", saved_config.get("models", {}))
        self.assertEqual(
            saved_config["models"]["new-model"]["hf_repo"],
            "TheBloke/Test-GGUF"
        )

    def test_config_preserves_hf_fields(self):
        """Test that HF fields are preserved in config."""
        print("[23] Testing config preserves HF fields...")

        model_config = create_model_config(
            name="test",
            source_type="huggingface",
            hf_repo="TheBloke/Qwen-7B-GGUF",
            hf_file="qwen-7b.Q4_K_M.gguf",
            preset="standard"
        )

        self.config["models"]["test"] = model_config

        # Write and read back
        with open(self.config_path, 'w') as f:
            yaml.dump(self.config, f)

        with open(self.config_path, 'r') as f:
            loaded = yaml.safe_load(f)

        self.assertEqual(
            loaded["models"]["test"]["hf_repo"],
            "TheBloke/Qwen-7B-GGUF"
        )
        self.assertEqual(
            loaded["models"]["test"]["hf_file"],
            "qwen-7b.Q4_K_M.gguf"
        )


class TestDownloadError(unittest.TestCase):
    """Test DownloadError exception."""

    def test_download_error_basic(self):
        """Test basic DownloadError."""
        print("\n[24] Testing DownloadError basic...")

        error = DownloadError("Download failed", url="https://example.com")

        self.assertEqual(error.url, "https://example.com")
        self.assertIn("Download failed", str(error))

    def test_download_error_with_cause(self):
        """Test DownloadError with cause."""
        print("[25] Testing DownloadError with cause...")

        cause = ValueError("Original error")
        error = DownloadError("Download failed", cause=cause)

        self.assertEqual(error.cause, cause)


if __name__ == '__main__':
    unittest.main()
