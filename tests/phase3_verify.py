import sys
import os
import json
import sqlite3

# Ensure import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from agent_core.agent import DebugAgent
    from agent_core.memory.history import HistoryMemory
    from agent_core.analysis.classifier import ErrorClassifier
except ImportError:
    print("Modules not found (Expected for TDD start)")

# Mock the LLM Client to return predictable responses
class MockPlanner:
    def __init__(self):
        self.call_count = 0

    def generate(self, prompt, **kwargs):
        self.call_count += 1
        # Scenario:
        # Call 1: Suggest a bad command "apt-get install bad-pkg"
        # Call 2: Agent sees failure. Planner suggests "apt-get install bad-pkg" AGAIN (Simulating dumb LLM)
        # Call 3: Agent rejects it internally? Or Planner realizes?
        # Actually, the Agent logic should probably filter it or inject history into prompt so Planner knows.

        # For this test, we verify the Agent *records* the failure.
        return json.dumps({
            "thought": "I will try to install the package.",
            "command": "apt-get install bad-pkg",
            "reasoning": "Standard fix."
        })

def test_debug_loop_logic():
    print("--- Starting Phase 3 Verification ---")

    # 1. Initialize Memory
    if os.path.exists("history_test.db"):
        os.remove("history_test.db")

    memory = HistoryMemory(db_path="history_test.db")

    # 2. Test Error Classifier (Regex based)
    classifier = ErrorClassifier()
    error_log = """
    Step 1/5: Building Docker Image...
    E: Unable to locate package lib-bad-v1
    The command '/bin/sh -c apt-get install -y lib-bad-v1' returned a non-zero code: 100
    """

    cat = classifier.classify(error_log)
    print(f"[1] Classification Result: {cat}")
    assert cat == "PackageError" or cat == "BuildError", f"Should detect package/build error, got {cat}"

    # 3. Simulate an Agent Step (Manual injection to test memory logic)
    cmd = "apt-get install bad-pkg"

    # Check before
    assert memory.has_failed_before(cmd) is False

    # Record a failure
    print(f"[2] Recording failure for: {cmd}")
    memory.add_entry(
        step=1,
        command=cmd,
        output=error_log,
        exit_code=100,
        status="FAILED",
        reasoning="Attempt 1"
    )

    # Check after
    assert memory.has_failed_before(cmd) is True, "Memory should remember the failed command"

    # 4. Test Failure Retrieval
    history = memory.get_context_for_prompt()
    print(f"[3] History Context:\n{history}")
    assert "apt-get install bad-pkg" in history
    assert "FAILED" in history

    # 5. Verify Dedup Logic (Agent Level)
    # If the LLM suggests the same command again, the Agent should flag it.
    # We simulate the check logic here (since full Agent requires async loop mocking)

    next_suggested_cmd = "apt-get install bad-pkg"
    is_duplicate = memory.has_failed_before(next_suggested_cmd)

    if is_duplicate:
        print("[4] Agent successfully detected duplicate bad command.")
    else:
        print("❌ Agent failed to detect duplicate.")

    assert is_duplicate is True

    print("✅ Phase 3 Acceptance Passed")

if __name__ == "__main__":
    try:
        test_debug_loop_logic()
    except Exception as e:
        print(f"❌ Test Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
