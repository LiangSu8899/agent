"""
Configuration Manager for loading and saving global and project configs.
"""
import os
import shutil
import yaml
from pathlib import Path
from typing import Any, Dict, Optional

from .utils.paths import (
    get_global_config_dir,
    get_global_config_path,
    ensure_global_dir_exists,
)


# Default configuration template - Ultimate Production Config
DEFAULT_CONFIG = {
    "system": {
        "workspace_root": ".",
        "safety_policy": "strict"
    },
    "roles": {
        "planner": "glm-4-plus",
        "coder": "deepseek-v3"
    },
    "models": {
        "deepseek-v3": {
            "type": "deepseek",
            "description": "DeepSeek V3 - High performance reasoning model",
            "api_base": "https://api.deepseek.com/v1",
            "model_name": "deepseek-chat",
            "cost_input": 0.27,
            "cost_output": 1.10
        },
        "deepseek-coder": {
            "type": "deepseek",
            "description": "DeepSeek Coder - Specialized for code generation",
            "api_base": "https://api.deepseek.com/v1",
            "model_name": "deepseek-coder",
            "cost_input": 0.14,
            "cost_output": 0.28
        },
        "glm-4-plus": {
            "type": "zhipu",
            "description": "GLM-4-Plus - Zhipu AI flagship model",
            "api_base": "https://open.bigmodel.cn/api/paas/v4",
            "model_name": "glm-4-plus",
            "cost_input": 0.50,
            "cost_output": 0.50
        },
        "gpt-4o": {
            "type": "openai",
            "description": "GPT-4o - OpenAI multimodal flagship",
            "api_base": "https://api.openai.com/v1",
            "model_name": "gpt-4o",
            "cost_input": 2.50,
            "cost_output": 10.00
        },
        "claude-3-5-sonnet": {
            "type": "anthropic",
            "description": "Claude 3.5 Sonnet - Anthropic balanced model",
            "api_base": "https://api.anthropic.com/v1",
            "model_name": "claude-3-5-sonnet-20241022",
            "cost_input": 3.00,
            "cost_output": 15.00
        },
        "local-deepseek-coder-v2": {
            "type": "local",
            "description": "Local DeepSeek Coder V2 via Ollama",
            "api_base": "http://localhost:11434/v1",
            "model_name": "deepseek-coder-v2:16b",
            "cost_input": 0.0,
            "cost_output": 0.0
        }
    },
    "session": {
        "max_steps": 50
    },
    "security": {
        "blocked_commands": ["rm -rf /", "mkfs"],
        "blocked_paths": ["/etc", "/usr", ".git"],
        "strict_mode": False
    }
}

# Models that indicate a mock-only config that should be upgraded
MOCK_ONLY_MODELS = {"mock"}


class ConfigManager:
    """
    Manages global and project-specific configurations.
    """

    def __init__(self, global_dir: Optional[str] = None):
        """
        Initialize the ConfigManager.

        Args:
            global_dir: Optional custom global directory (for testing)
        """
        self.global_dir = Path(global_dir) if global_dir else get_global_config_dir()
        self._config: Dict[str, Any] = {}
        self._config_path: Optional[Path] = None

    def _ensure_global_dir(self):
        """Ensure the global config directory exists."""
        self.global_dir.mkdir(parents=True, exist_ok=True)

    def get_global_config_path(self) -> Path:
        """Get the path to the global config file."""
        return self.global_dir / "config.yaml"

    def load_global_config(self) -> Dict[str, Any]:
        """
        Load the global configuration.
        Creates default config if it doesn't exist.
        Upgrades mock-only configs to production defaults.

        Returns:
            Configuration dictionary
        """
        self._ensure_global_dir()
        config_path = self.get_global_config_path()

        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    self._config = yaml.safe_load(f) or {}

                # Check if config needs upgrade (mock-only)
                if self._is_mock_only_config():
                    self._upgrade_config()
                    self.save_global_config()

            except (yaml.YAMLError, IOError):
                self._config = self._deep_copy_config(DEFAULT_CONFIG)
        else:
            # Create default config
            self._config = self._deep_copy_config(DEFAULT_CONFIG)
            self.save_global_config()

        self._config_path = config_path
        return self._config

    def _is_mock_only_config(self) -> bool:
        """
        Check if the current config only has mock models.

        Returns:
            True if config should be upgraded
        """
        models = self._config.get("models", {})
        if not models:
            return True

        # Check if all models are mock
        model_names = set(models.keys())
        return model_names.issubset(MOCK_ONLY_MODELS)

    def _upgrade_config(self):
        """
        Upgrade a mock-only config to production defaults.
        Preserves any custom settings while adding new models.
        """
        import copy

        # Merge models from default config
        default_models = DEFAULT_CONFIG.get("models", {})
        current_models = self._config.get("models", {})

        # Add all default models (don't overwrite existing non-mock models)
        for model_name, model_config in default_models.items():
            if model_name not in current_models:
                current_models[model_name] = copy.deepcopy(model_config)

        self._config["models"] = current_models

        # Update roles to use production models
        self._config["roles"] = copy.deepcopy(DEFAULT_CONFIG.get("roles", {}))

        # Preserve other settings but ensure defaults exist
        for key in ["system", "session", "security"]:
            if key not in self._config:
                self._config[key] = copy.deepcopy(DEFAULT_CONFIG.get(key, {}))

    def _deep_copy_config(self, config: Dict) -> Dict:
        """Create a deep copy of a config dictionary."""
        import copy
        return copy.deepcopy(config)

    def save_global_config(self):
        """Save the current configuration to the global config file."""
        self._ensure_global_dir()
        config_path = self.get_global_config_path()

        with open(config_path, 'w') as f:
            yaml.dump(self._config, f, default_flow_style=False, allow_unicode=True)

    def load_config(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Load configuration from a specific path or global config.

        Args:
            config_path: Optional path to config file

        Returns:
            Configuration dictionary
        """
        if config_path:
            path = Path(config_path)
            if path.exists():
                with open(path, 'r') as f:
                    self._config = yaml.safe_load(f) or {}
                self._config_path = path
                return self._config

        return self.load_global_config()

    def get_config(self) -> Dict[str, Any]:
        """Get the current configuration."""
        if not self._config:
            self.load_global_config()
        return self._config

    def set_config(self, config: Dict[str, Any]):
        """Set the configuration."""
        self._config = config

    def update_config(self, updates: Dict[str, Any]):
        """
        Update the configuration with new values.

        Args:
            updates: Dictionary of updates to apply
        """
        self._deep_update(self._config, updates)

    def _deep_update(self, base: Dict, updates: Dict):
        """Recursively update a dictionary."""
        for key, value in updates.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_update(base[key], value)
            else:
                base[key] = value

    def save_config(self, config_path: Optional[str] = None):
        """
        Save configuration to a specific path or the loaded path.

        Args:
            config_path: Optional path to save to
        """
        path = Path(config_path) if config_path else self._config_path
        if not path:
            path = self.get_global_config_path()

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            yaml.dump(self._config, f, default_flow_style=False, allow_unicode=True)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value.

        Args:
            key: Dot-separated key path (e.g., "models.gpt-4.cost_input")
            default: Default value if key not found

        Returns:
            Configuration value
        """
        if not self._config:
            self.load_global_config()

        keys = key.split(".")
        value = self._config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def set(self, key: str, value: Any):
        """
        Set a configuration value.

        Args:
            key: Dot-separated key path
            value: Value to set
        """
        if not self._config:
            self.load_global_config()

        keys = key.split(".")
        config = self._config

        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]

        config[keys[-1]] = value

    def copy_default_config(self, dest_path: str):
        """
        Copy the default configuration to a destination.

        Args:
            dest_path: Destination path
        """
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)

        with open(dest, 'w') as f:
            yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False, allow_unicode=True)
