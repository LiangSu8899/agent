"""
Model Manager for dynamic model loading/unloading.
Ensures only one heavy model is loaded on GPU at a time.
"""
from typing import Any, Callable, Dict, Optional

from .client import LLMClient, MockLLMClient, LlamaCppClient, OpenAICompatibleClient


class ModelManager:
    """
    Manages multiple LLM models with VRAM constraints.
    Ensures only ONE heavy model is loaded on GPU at a time.
    """

    def __init__(self, config: Dict[str, Dict[str, Any]], max_vram_gb: float = 24.0):
        """
        Initialize the ModelManager.

        Args:
            config: Dictionary mapping model names to their configurations.
                    Each config should have 'type' and type-specific params.
                    Example: {"planner": {"type": "mock", "vram": 7}}
            max_vram_gb: Maximum available VRAM in GB (default: 24GB for RTX 5090)
        """
        self.config = config
        self.max_vram_gb = max_vram_gb
        self._clients: Dict[str, LLMClient] = {}
        self._current_loaded: Optional[str] = None

        # Default factory method - can be overridden for testing
        self._create_client = self._default_create_client

    def _default_create_client(self, name: str, conf: Dict[str, Any]) -> LLMClient:
        """
        Factory method to create LLM clients based on configuration.

        Args:
            name: Model name
            conf: Model configuration

        Returns:
            LLMClient instance
        """
        model_type = conf.get("type", "mock")

        if model_type == "mock":
            vram = conf.get("vram", 8)
            return MockLLMClient(name, vram)

        elif model_type == "llama-cpp":
            return LlamaCppClient(
                model_path=conf["model_path"],
                n_ctx=conf.get("n_ctx", 4096),
                n_gpu_layers=conf.get("n_gpu_layers", -1)
            )

        elif model_type == "openai-compatible":
            return OpenAICompatibleClient(
                base_url=conf["base_url"],
                model_name=conf.get("model_name", name),
                api_key=conf.get("api_key", "not-needed")
            )

        else:
            raise ValueError(f"Unknown model type: {model_type}")

    def _get_or_create_client(self, name: str) -> LLMClient:
        """Get existing client or create a new one."""
        if name not in self._clients:
            if name not in self.config:
                raise ValueError(f"Unknown model: {name}")
            self._clients[name] = self._create_client(name, self.config[name])
        return self._clients[name]

    def get_model(self, name: str) -> LLMClient:
        """
        Get a model by name, loading it if necessary.
        If another model is currently loaded, it will be unloaded first.

        Args:
            name: Name of the model to get

        Returns:
            Loaded LLMClient instance
        """
        client = self._get_or_create_client(name)

        # If already loaded, return it
        if client.is_loaded():
            return client

        # Unload current model if one is loaded
        if self._current_loaded is not None and self._current_loaded != name:
            current_client = self._clients.get(self._current_loaded)
            if current_client and current_client.is_loaded():
                current_client.unload()

        # Load the requested model
        client.load()
        self._current_loaded = name

        return client

    def unload_all(self) -> None:
        """Unload all models to free VRAM."""
        for name, client in self._clients.items():
            if client.is_loaded():
                client.unload()
        self._current_loaded = None

    def get_current_model(self) -> Optional[str]:
        """Get the name of the currently loaded model."""
        return self._current_loaded

    def list_models(self) -> list:
        """List all available model names."""
        return list(self.config.keys())

    def get_model_info(self, name: str) -> Dict[str, Any]:
        """Get configuration info for a model."""
        if name not in self.config:
            raise ValueError(f"Unknown model: {name}")
        return self.config[name].copy()

    def get_model_cost(self, name: str) -> Dict[str, float]:
        """
        Get cost information for a model.

        Args:
            name: Model name

        Returns:
            Dict with 'cost_input' and 'cost_output' (per 1M tokens)
        """
        if name not in self.config:
            raise ValueError(f"Unknown model: {name}")

        conf = self.config[name]
        return {
            "cost_input": conf.get("cost_input", 0.0),
            "cost_output": conf.get("cost_output", 0.0)
        }

    def calculate_cost(self, name: str, input_tokens: int, output_tokens: int) -> float:
        """
        Calculate the cost for a given token usage.

        Args:
            name: Model name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Total cost in dollars
        """
        costs = self.get_model_cost(name)
        input_cost = (input_tokens / 1_000_000) * costs["cost_input"]
        output_cost = (output_tokens / 1_000_000) * costs["cost_output"]
        return input_cost + output_cost

    def has_model(self, name: str) -> bool:
        """Check if a model exists in config."""
        return name in self.config
