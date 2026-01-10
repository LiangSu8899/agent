"""
Abstract base class for LLM clients.
Supports local models (llama-cpp-python) and OpenAI-compatible APIs.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class LLMClient(ABC):
    """
    Abstract base class for LLM clients.
    All model implementations must inherit from this class.
    """

    @abstractmethod
    def load(self) -> None:
        """Load the model into memory (GPU/CPU)."""
        pass

    @abstractmethod
    def unload(self) -> None:
        """Unload the model from memory to free resources."""
        pass

    @abstractmethod
    def is_loaded(self) -> bool:
        """Check if the model is currently loaded."""
        pass

    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate a response from the model.

        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters (temperature, max_tokens, etc.)

        Returns:
            Generated text response
        """
        pass


class MockLLMClient(LLMClient):
    """
    Mock LLM client for testing purposes.
    Simulates model loading/unloading without actual GPU operations.
    """

    def __init__(self, name: str, vram_usage_gb: float):
        self.name = name
        self.vram_usage = vram_usage_gb
        self._loaded = False

    def load(self) -> None:
        print(f"  [GPU] Loading {self.name} ({self.vram_usage}GB)...")
        self._loaded = True

    def unload(self) -> None:
        print(f"  [GPU] Unloading {self.name}...")
        self._loaded = False

    def is_loaded(self) -> bool:
        return self._loaded

    def generate(self, prompt: str, **kwargs) -> str:
        if not self._loaded:
            raise RuntimeError(f"Model {self.name} is not loaded!")
        return f"Mock response from {self.name}"


class LlamaCppClient(LLMClient):
    """
    Placeholder for llama-cpp-python based client.
    Requires llama-cpp-python to be installed.
    """

    def __init__(self, model_path: str, n_ctx: int = 4096, n_gpu_layers: int = -1):
        self.model_path = model_path
        self.n_ctx = n_ctx
        self.n_gpu_layers = n_gpu_layers
        self._model = None

    def load(self) -> None:
        try:
            from llama_cpp import Llama
            self._model = Llama(
                model_path=self.model_path,
                n_ctx=self.n_ctx,
                n_gpu_layers=self.n_gpu_layers,
                verbose=False
            )
        except ImportError:
            raise ImportError("llama-cpp-python is required. Install with: pip install llama-cpp-python")

    def unload(self) -> None:
        if self._model is not None:
            del self._model
            self._model = None
            # Force garbage collection to free VRAM
            import gc
            gc.collect()

    def is_loaded(self) -> bool:
        return self._model is not None

    def generate(self, prompt: str, **kwargs) -> str:
        if not self.is_loaded():
            raise RuntimeError("Model is not loaded!")

        max_tokens = kwargs.get('max_tokens', 512)
        temperature = kwargs.get('temperature', 0.7)

        output = self._model(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            echo=False
        )
        return output['choices'][0]['text']


class OpenAICompatibleClient(LLMClient):
    """
    Client for OpenAI-compatible local APIs (e.g., vLLM, text-generation-inference).
    """

    def __init__(self, base_url: str, model_name: str, api_key: str = "not-needed"):
        self.base_url = base_url.rstrip('/')
        self.model_name = model_name
        self.api_key = api_key
        self._loaded = False

    def load(self) -> None:
        # For API-based clients, "loading" means verifying connectivity
        self._loaded = True

    def unload(self) -> None:
        self._loaded = False

    def is_loaded(self) -> bool:
        return self._loaded

    def generate(self, prompt: str, **kwargs) -> str:
        if not self.is_loaded():
            raise RuntimeError("Client is not connected!")

        import urllib.request
        import json

        max_tokens = kwargs.get('max_tokens', 512)
        temperature = kwargs.get('temperature', 0.7)

        data = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature
        }

        req = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=json.dumps(data).encode('utf-8'),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
        )

        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result['choices'][0]['message']['content']
