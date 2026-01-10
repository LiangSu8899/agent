import sys
import os
import time

# Ensure import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from agent_core.models.manager import ModelManager
    from agent_core.models.client import LLMClient
except ImportError:
    print("Modules not found (Expected for TDD start)")

class MockLLMClient(LLMClient):
    """Simulates a model that takes memory"""
    def __init__(self, name, vram_usage_gb):
        self.name = name
        self.vram_usage = vram_usage_gb
        self._loaded = False
        self._logs = []

    def load(self):
        print(f"  [GPU] Loading {self.name} ({self.vram_usage}GB)...")
        self._loaded = True

    def unload(self):
        print(f"  [GPU] Unloading {self.name}...")
        self._loaded = False

    def is_loaded(self):
        return self._loaded

    def generate(self, prompt, **kwargs):
        if not self._loaded:
            raise RuntimeError(f"Model {self.name} is not loaded!")
        return f"Mock response from {self.name}"

def test_model_memory_management():
    print("--- Starting Phase 2 Verification ---")

    # 1. Initialize Manager
    # Config simulates: Planner (7GB), Coder (18GB).
    # Total 25GB > 24GB VRAM, so they can't coexist.
    config = {
        "planner": {"type": "mock", "vram": 7},
        "coder":   {"type": "mock", "vram": 18}
    }

    # We override the internal factory for testing to return our MockClient
    manager = ModelManager(config=config)

    # Inject a factory method to return our MockLLMClient instead of real implementation
    def mock_factory(name, conf):
        return MockLLMClient(name, conf["vram"])
    manager._create_client = mock_factory

    print("[1] Manager Initialized")

    # 2. Load Planner
    print("[2] Requesting Planner...")
    planner = manager.get_model("planner")
    assert planner.is_loaded() is True
    print("    -> Planner is loaded")

    # 3. Load Coder (Should automatically unload Planner)
    print("[3] Requesting Coder (High VRAM)...")
    coder = manager.get_model("coder")

    assert coder.is_loaded() is True
    assert planner.is_loaded() is False, "❌ Planner should have been unloaded to free VRAM!"
    print("    -> Coder loaded, Planner unloaded (Success)")

    # 4. Switch back to Planner
    print("[4] Switching back to Planner...")
    planner_again = manager.get_model("planner")

    assert planner_again.is_loaded() is True
    assert coder.is_loaded() is False, "❌ Coder should have been unloaded"
    print("    -> Planner re-loaded, Coder unloaded")

    # 5. Test Token Counting (Basic Check)
    # Assuming the manager has a helper or the client has a helper
    from agent_core.utils.token_counter import count_tokens

    text = "Hello world"
    count = count_tokens(text)
    print(f"[5] Token count for '{text}': {count}")
    assert count > 0, "Token count should be positive"

    print("✅ Phase 2 Acceptance Passed")

if __name__ == "__main__":
    try:
        test_model_memory_management()
    except Exception as e:
        print(f"❌ Test Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
