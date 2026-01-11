"""
Configuration Manager for loading and saving configs.

Loading Priority (Proximity Principle):
1. First check current working directory for config.yaml
2. If not found, check global directory (~/.agent_os/config.yaml)

Write Strategy (Save to Source):
- Always save back to the path where config was loaded from
"""
import os
import copy
import yaml
from pathlib import Path
from typing import Any, Dict, Optional

from .utils.paths import get_global_config_dir


# Default configuration template
# All API models use "openai" type for OpenAI-compatible API
# API keys are left empty - user must configure them
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
            "type": "openai",
            "description": "DeepSeek V3 (API) - 极致性价比",
            "api_base": "https://api.deepseek.com/v1",
            "model_name": "deepseek-chat",
            "api_key": "",
            "cost_input": 0.14,
            "cost_output": 0.28,
            "temperature": 0.0
        },
        "deepseek-coder": {
            "type": "openai",
            "description": "DeepSeek Coder V2 (API)",
            "api_base": "https://api.deepseek.com/v1",
            "model_name": "deepseek-coder",
            "api_key": "",
            "cost_input": 0.14,
            "cost_output": 0.28,
            "temperature": 0.0
        },
        "glm-4-plus": {
            "type": "openai",
            "description": "Zhipu GLM-4 Plus (API)",
            "api_base": "https://open.bigmodel.cn/api/paas/v4",
            "model_name": "glm-4.7",
            "api_key": "",
            "cost_input": 10.0,
            "cost_output": 10.0,
            "temperature": 0.5
        },
        "gpt-4o": {
            "type": "openai",
            "description": "OpenAI GPT-4o (API)",
            "api_base": "https://api.openai.com/v1",
            "model_name": "gpt-4o",
            "api_key": "",
            "cost_input": 2.5,
            "cost_output": 10.0,
            "temperature": 0.1
        },
        "claude-3-5-sonnet": {
            "type": "openai",
            "description": "Claude 3.5 Sonnet (API)",
            "api_base": "https://openrouter.ai/api/v1",
            "model_name": "claude-3-5-sonnet-20240620",
            "api_key": "",
            "cost_input": 3.0,
            "cost_output": 15.0,
            "temperature": 0.1
        },
        "local-ollama": {
            "type": "openai",
            "description": "Local model via Ollama",
            "api_base": "http://localhost:11434/v1",
            "model_name": "deepseek-coder-v2:16b",
            "api_key": "ollama",
            "cost_input": 0.0,
            "cost_output": 0.0
        },
        "local-qwen2.5-14b": {
            "type": "openai",
            "description": "Qwen 2.5 14B (Local) - 全能型 (OpenSource)",
            "api_base": "http://localhost:11434/v1",
            "model_name": "qwen2.5:14b",
            "api_key": "ollama",
            "cost_input": 0.0,
            "cost_output": 0.0
        },
        "local-deepseek-coder-v2-lite": {
            "type": "local",
            "description": "DeepSeek Coder V2 Lite (GGUF) - (OpenSource)",
            "path": "/models/deepseek-coder-v2-lite-instruct.Q6_K.gguf",
            "n_ctx": 16384,
            "n_gpu_layers": -1,
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

# Config filename
CONFIG_FILENAME = "config.yaml"


class ConfigManager:
    """
    Manages configuration with proximity-based loading and save-to-source strategy.

    Loading Priority:
    1. Current working directory (./config.yaml)
    2. Global directory (~/.agent_os/config.yaml)

    Write Strategy:
    - Always save back to the path where config was loaded from
    """

    def __init__(self, global_dir: Optional[str] = None, cwd: Optional[str] = None):
        """
        Initialize the ConfigManager.

        Args:
            global_dir: Optional custom global directory (for testing)
            cwd: Optional custom current working directory (for testing)
        """
        self.global_dir = Path(global_dir) if global_dir else get_global_config_dir()
        self.cwd = Path(cwd) if cwd else Path.cwd()
        self._config: Dict[str, Any] = {}
        self._config_path: Optional[Path] = None
        self._loaded = False

    def _get_local_config_path(self) -> Path:
        """Get the path to the local (cwd) config file."""
        return self.cwd / CONFIG_FILENAME

    def _get_global_config_path(self) -> Path:
        """Get the path to the global config file."""
        return self.global_dir / CONFIG_FILENAME

    def get_global_config_path(self) -> Path:
        """Public method to get global config path."""
        return self._get_global_config_path()

    def get_config_path(self) -> Optional[Path]:
        """Get the path where config was loaded from."""
        return self._config_path

    def load_config(self) -> Dict[str, Any]:
        """
        Load configuration using proximity principle.

        Priority:
        1. Current working directory (./config.yaml)
        2. Global directory (~/.agent_os/config.yaml)
        3. Create default in global directory if nothing exists

        Returns:
            Configuration dictionary
        """
        # Priority 1: Check current working directory
        local_path = self._get_local_config_path()
        if local_path.exists():
            return self._load_from_path(local_path)

        # Priority 2: Check global directory
        global_path = self._get_global_config_path()
        if global_path.exists():
            return self._load_from_path(global_path)

        # Priority 3: Create default config in global directory
        print(f"[Config] No config file found, creating default at: {global_path}")
        self._ensure_global_dir()
        self._config = copy.deepcopy(DEFAULT_CONFIG)
        self._config_path = global_path
        self._loaded = True
        self.save_config()
        print(f"[Config] Loaded configuration from: {global_path} (newly created)")
        return self._config

    def _load_from_path(self, path: Path) -> Dict[str, Any]:
        """
        Load configuration from a specific path.

        Args:
            path: Path to the config file

        Returns:
            Configuration dictionary
        """
        try:
            with open(path, 'r', encoding='utf-8') as f:
                file_config = yaml.safe_load(f) or {}

            # Merge with defaults to fill missing keys
            self._config = self._merge_with_defaults(file_config)
            self._config_path = path
            self._loaded = True

            model_count = len(self._config.get("models", {}))
            print(f"[Config] Loaded configuration from: {path}")
            print(f"[Config] Found {model_count} models in config")

            return self._config

        except (yaml.YAMLError, IOError) as e:
            print(f"[Config] Error loading config from {path}: {e}")
            print(f"[Config] Using default configuration")
            self._config = copy.deepcopy(DEFAULT_CONFIG)
            self._config_path = path  # Still save to this path
            self._loaded = True
            return self._config

    def _merge_with_defaults(self, file_config: Dict) -> Dict:
        """
        Merge file config with defaults.
        File content takes PRIORITY - defaults only fill missing keys.

        Args:
            file_config: Configuration loaded from file

        Returns:
            Merged configuration dictionary
        """
        # Start with a copy of defaults
        merged = copy.deepcopy(DEFAULT_CONFIG)

        # Deep merge file config ON TOP of defaults (file wins)
        # This ensuring that if a key exists in file_config, it overrides the default
        self._deep_merge(merged, file_config)

        return merged

    def _deep_merge(self, base: Dict, override: Dict):
        """
        Deep merge override into base. Override values take priority.

        Args:
            base: Base dictionary (modified in place)
            override: Override dictionary (values take priority)
        """
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def _ensure_global_dir(self):
        """Ensure the global config directory exists."""
        self.global_dir.mkdir(parents=True, exist_ok=True)

    def save_config(self, path: Optional[str] = None):
        """
        Save configuration to the source path (or specified path).

        Strategy: "Save to Source" - writes back to where config was loaded from.

        Args:
            path: Optional override path (if not specified, uses load path)
        """
        if path:
            save_path = Path(path)
        elif self._config_path:
            save_path = self._config_path
        else:
            # Fallback to global path
            save_path = self._get_global_config_path()

        # Ensure parent directory exists
        save_path.parent.mkdir(parents=True, exist_ok=True)

        with open(save_path, 'w', encoding='utf-8') as f:
            yaml.dump(self._config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        print(f"[Config] Saved configuration to: {save_path}")

    def get_config(self) -> Dict[str, Any]:
        """Get the current configuration, loading if necessary."""
        if not self._loaded:
            self.load_config()
        return self._config

    def set_config(self, config: Dict[str, Any]):
        """Set the entire configuration."""
        self._config = config

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value using dot notation.

        Args:
            key: Dot-separated key path (e.g., "models.gpt-4o.api_key")
            default: Default value if key not found

        Returns:
            Configuration value
        """
        if not self._loaded:
            self.load_config()

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
        Set a configuration value using dot notation.

        Args:
            key: Dot-separated key path
            value: Value to set
        """
        if not self._loaded:
            self.load_config()

        keys = key.split(".")
        config = self._config

        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]

        config[keys[-1]] = value

    def update_config(self, updates: Dict[str, Any]):
        """
        Update the configuration with new values.

        Args:
            updates: Dictionary of updates to apply
        """
        if not self._loaded:
            self.load_config()
        self._deep_merge(self._config, updates)

    def create_local_config(self, force: bool = False) -> Path:
        """
        Create a config.yaml in the current working directory.

        Args:
            force: If True, overwrite existing file

        Returns:
            Path to the created config file
        """
        local_path = self._get_local_config_path()

        if local_path.exists() and not force:
            print(f"[Config] Local config already exists: {local_path}")
            return local_path

        with open(local_path, 'w', encoding='utf-8') as f:
            yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        print(f"[Config] Created local config: {local_path}")
        return local_path

    def reload(self) -> Dict[str, Any]:
        """
        Reload configuration from disk.

        Returns:
            Reloaded configuration dictionary
        """
        self._loaded = False
        self._config = {}
        self._config_path = None
        return self.load_config()

    # Legacy compatibility methods

    def load_global_config(self) -> Dict[str, Any]:
        """
        Legacy method - now uses proximity-based loading.

        Returns:
            Configuration dictionary
        """
        return self.load_config()

    def save_global_config(self):
        """Legacy method - now uses save_config()."""
        self.save_config()

    def copy_default_config(self, dest_path: str):
        """
        Copy the default configuration to a destination.

        Args:
            dest_path: Destination path
        """
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)

        with open(dest, 'w', encoding='utf-8') as f:
            yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        print(f"[Config] Copied default config to: {dest}")
