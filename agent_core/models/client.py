"""
Abstract base class for LLM clients.
Supports local models (llama-cpp-python) and OpenAI-compatible APIs.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class GenerationResult:
    """Result of a generation call, including token usage."""
    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    model_name: str = ""

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


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

    def generate_with_usage(self, prompt: str, **kwargs) -> GenerationResult:
        """
        Generate a response and return token usage information.

        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters

        Returns:
            GenerationResult with content and token usage
        """
        # Default implementation - subclasses should override for accurate token counting
        content = self.generate(prompt, **kwargs)
        # Estimate tokens (rough approximation: 1 token ≈ 4 characters)
        input_tokens = len(prompt) // 4
        output_tokens = len(content) // 4
        return GenerationResult(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model_name=getattr(self, 'model_name', 'unknown')
        )


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
        # Track last generation's token usage
        self._last_input_tokens = 0
        self._last_output_tokens = 0

    def load(self) -> None:
        # For API-based clients, "loading" means verifying connectivity
        self._loaded = True

    def unload(self) -> None:
        self._loaded = False

    def is_loaded(self) -> bool:
        return self._loaded

    def _is_glm_model(self) -> bool:
        """Check if this is a GLM model."""
        model_lower = self.model_name.lower()
        base_lower = self.base_url.lower()
        return any(x in model_lower or x in base_lower for x in ['glm', 'zhipu', 'bigmodel'])

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate response (for backward compatibility)."""
        result = self.generate_with_usage(prompt, **kwargs)
        return result.content

    def generate_with_usage(self, prompt: str, **kwargs) -> GenerationResult:
        """Generate response with token usage tracking."""
        if not self.is_loaded():
            raise RuntimeError("Client is not connected!")

        import urllib.request
        import json

        # Use higher max_tokens for GLM to avoid truncation
        default_max_tokens = 2048 if self._is_glm_model() else 512
        max_tokens = kwargs.get('max_tokens', default_max_tokens)
        temperature = kwargs.get('temperature', 0.7)

        # Build messages - use system message for GLM models
        messages = []

        if self._is_glm_model():
            # For GLM models, add a system message to enforce JSON output
            messages.append({
                "role": "system",
                "content": "You are a JSON-only response agent. Output ONLY valid JSON with no markdown, no code blocks, no explanations. Your entire response must be parseable by json.loads(). Keep commands SHORT and SIMPLE - do not include multi-line scripts in the command field."
            })

        messages.append({"role": "user", "content": prompt})

        data = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(data).encode('utf-8'),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
        )

        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))

            content = result['choices'][0]['message']['content']

            # Extract token usage from response
            usage = result.get('usage', {})
            input_tokens = usage.get('prompt_tokens', 0)
            output_tokens = usage.get('completion_tokens', 0)

            # If API doesn't return usage, estimate
            if input_tokens == 0:
                input_tokens = len(prompt) // 4
            if output_tokens == 0:
                output_tokens = len(content) // 4

            # Store for later access
            self._last_input_tokens = input_tokens
            self._last_output_tokens = output_tokens

            return GenerationResult(
                content=content,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model_name=self.model_name
            )
