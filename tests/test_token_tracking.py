#!/usr/bin/env python3
"""
Test token usage tracking.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_core.events import EventType, get_event_emitter, reset_event_emitter
from agent_core.agent import DebugAgent
from agent_core.session import SessionManager
from agent_core.memory.history import HistoryMemory
from agent_core.models.client import GenerationResult


def test_token_tracking():
    """Test that token usage is properly tracked through events."""
    print("="*60)
    print("TEST: Token Usage Tracking")
    print("="*60)

    # Reset event emitter
    reset_event_emitter()
    emitter = get_event_emitter()

    # Track token usage events
    token_events = []

    def on_token_event(event):
        if event.event_type == EventType.TOKEN_USAGE:
            token_events.append(event)
            print(f"  [TOKEN_USAGE] Model: {event.data.get('model')}, "
                  f"In: {event.data.get('input_tokens')}, "
                  f"Out: {event.data.get('output_tokens')}")

    emitter.on(EventType.TOKEN_USAGE, on_token_event)

    # Create a mock planner that returns GenerationResult
    class MockPlannerWithUsage:
        def __init__(self):
            self.call_count = 0
            self.model_name = "mock-model"

        def generate(self, prompt: str) -> str:
            result = self.generate_with_usage(prompt)
            return result.content

        def generate_with_usage(self, prompt: str) -> GenerationResult:
            self.call_count += 1
            if self.call_count == 1:
                content = '{"thought": "First step", "command": "echo hello", "reasoning": "Test"}'
            else:
                content = '{"thought": "Done", "command": "DONE", "reasoning": "Complete"}'

            return GenerationResult(
                content=content,
                input_tokens=len(prompt) // 4,
                output_tokens=len(content) // 4,
                model_name=self.model_name
            )

    # Create agent
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "sessions.db")
        history_path = os.path.join(tmpdir, "history.db")

        session_manager = SessionManager(db_path=db_path)
        memory = HistoryMemory(db_path=history_path)

        agent = DebugAgent(
            session_manager=session_manager,
            memory=memory,
            max_steps=5,
            debug=False
        )
        agent.set_planner(MockPlannerWithUsage())

        print("\n  Running agent...")
        results = agent.run(initial_goal="Test task")

        print(f"\n  Steps completed: {len(results)}")
        print(f"  Token events received: {len(token_events)}")

        if len(token_events) >= 1:
            print("\n  Token usage details:")
            total_input = 0
            total_output = 0
            for event in token_events:
                input_t = event.data.get("input_tokens", 0)
                output_t = event.data.get("output_tokens", 0)
                total_input += input_t
                total_output += output_t

            print(f"    Total input tokens: {total_input}")
            print(f"    Total output tokens: {total_output}")
            print("\n  [PASS] Token usage tracking works!")
            return True
        else:
            print("\n  [FAIL] No token usage events received")
            return False


def test_token_tracking_with_glm():
    """Test token tracking with real GLM API (if configured)."""
    print("\n" + "="*60)
    print("TEST: Token Tracking with GLM API (Optional)")
    print("="*60)

    import yaml

    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
    if not os.path.exists(config_path):
        print("  [SKIP] config.yaml not found")
        return True

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    glm_config = config.get("models", {}).get("glm-4-plus", {})
    api_key = glm_config.get("api_key", "")

    if not api_key or api_key.startswith("YOUR_"):
        print("  [SKIP] GLM API key not configured")
        return True

    from agent_core.models.client import OpenAICompatibleClient

    client = OpenAICompatibleClient(
        base_url=glm_config.get("api_base", "https://open.bigmodel.cn/api/paas/v4"),
        model_name=glm_config.get("model_name", "glm-4-plus"),
        api_key=api_key
    )
    client.load()

    print("\n  Calling GLM API with token tracking...")
    result = client.generate_with_usage("Say hello in JSON format: {\"message\": \"...\"}")

    print(f"  Response: {result.content[:50]}...")
    print(f"  Input tokens: {result.input_tokens}")
    print(f"  Output tokens: {result.output_tokens}")
    print(f"  Total tokens: {result.total_tokens}")
    print(f"  Model: {result.model_name}")

    if result.input_tokens > 0 or result.output_tokens > 0:
        print("\n  [PASS] GLM token tracking works!")
        return True
    else:
        print("\n  [WARN] Token counts are zero (API may not return usage)")
        return True


if __name__ == "__main__":
    results = []
    results.append(("Token Tracking", test_token_tracking()))
    results.append(("GLM Token Tracking", test_token_tracking_with_glm()))

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        if not passed:
            all_passed = False

    sys.exit(0 if all_passed else 1)
