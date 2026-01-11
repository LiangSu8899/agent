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


# Default configuration template
DEFAULT_CONFIG = {
    "system": {
        "workspace_root": ".",
        "safety_policy": "strict"
    },
    "roles": {
        "planner": "mock",
        "coder": "mock"
    },
    "models": {
        "mock": {
            "type": "mock",
            "description": "Mock model for testing",
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

        Returns:
            Configuration dictionary
        """
        self._ensure_global_dir()
        config_path = self.get_global_config_path()

        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    self._config = yaml.safe_load(f) or {}
            except (yaml.YAMLError, IOError):
                self._config = DEFAULT_CONFIG.copy()
        else:
            # Create default config
            self._config = DEFAULT_CONFIG.copy()
            self.save_global_config()

        self._config_path = config_path
        return self._config

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
