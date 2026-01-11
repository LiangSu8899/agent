#!/usr/bin/env python3
"""
End-to-end test for GLM model with the Agent.

Usage:
    1. Set your GLM API key in config.yaml
    2. Run: python tests/test_glm_e2e.py

This script will:
    1. Create a simple task ("帮我实现一个贪吃蛇")
    2. Run the agent with GLM model
    3. Verify that at least one action is successfully parsed
    4. Check that history doesn't show all fallbacks
"""
import os
import sys
import yaml
import time

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_core.orchestrator import AgentOrchestrator
from agent_core.memory.history import HistoryMemory


def main():
    print("="*60)
    print("GLM End-to-End Test")
    print("="*60)

    # Load config
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
    if not os.path.exists(config_path):
        print("[ERROR] config.yaml not found")
        return 1

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Check GLM API key
    glm_config = config.get("models", {}).get("glm-4-plus", {})
    api_key = glm_config.get("api_key", "")

    if not api_key or api_key.startswith("YOUR_"):
        print("[ERROR] GLM API key not configured")
        print("        Please set a valid API key in config.yaml under models.glm-4-plus.api_key")
        return 1

    # Ensure planner is set to GLM
    if config.get("roles", {}).get("planner") != "glm-4-plus":
        print("[INFO] Setting planner to glm-4-plus for this test")
        config["roles"]["planner"] = "glm-4-plus"

    # Create orchestrator with debug mode
    print("\n[INFO] Creating orchestrator with debug mode...")
    orchestrator = AgentOrchestrator(
        db_path="test_glm_sessions.db",
        config=config,
        headless=True,
        debug=True
    )

    # Clear history for clean test
    orchestrator.memory.clear()

    # Create task
    task = "帮我实现一个贪吃蛇"
    print(f"\n[INFO] Creating task: {task}")

    session_id = orchestrator.create_task(task)
    print(f"[INFO] Session ID: {session_id}")

    # Run the loop (with timeout)
    print("\n[INFO] Running agent loop...")
    print("-"*60)

    try:
        # Run with a timeout
        import threading

        def run_with_timeout():
            orchestrator.run_loop(session_id, max_iterations=5)

        thread = threading.Thread(target=run_with_timeout)
        thread.start()
        thread.join(timeout=60)  # 60 second timeout

        if thread.is_alive():
            print("\n[WARN] Test timed out after 60 seconds")
            orchestrator.stop_task(session_id)

    except KeyboardInterrupt:
        print("\n[INFO] Test interrupted")
        orchestrator.stop_task(session_id)

    print("-"*60)

    # Check results
    print("\n[INFO] Checking results...")

    # Get history entries
    entries = orchestrator.memory.get_recent_entries(limit=10)

    if not entries:
        print("[FAIL] No history entries recorded")
        return 1

    print(f"\n[INFO] Found {len(entries)} history entries:")

    success_count = 0
    fallback_count = 0

    for entry in entries:
        status = entry.get("status", "UNKNOWN")
        reasoning = entry.get("reasoning", "")
        command = entry.get("command", "")

        is_fallback = "Fallback" in reasoning or "parse error" in reasoning.lower()

        if is_fallback:
            fallback_count += 1
            print(f"  [FALLBACK] Step {entry['step']}: {command[:50]}...")
        else:
            success_count += 1
            print(f"  [SUCCESS]  Step {entry['step']}: {command[:50]}...")

    print(f"\n[SUMMARY]")
    print(f"  Total entries: {len(entries)}")
    print(f"  Successful parses: {success_count}")
    print(f"  Fallback parses: {fallback_count}")

    # Determine test result
    if success_count > 0:
        print(f"\n[PASS] At least {success_count} action(s) were successfully parsed!")
        print("       The GLM compatibility fix is working.")
        return 0
    elif fallback_count > 0 and fallback_count < len(entries):
        print(f"\n[WARN] Some actions used fallback parsing.")
        print("       The fix is partially working.")
        return 0
    else:
        print(f"\n[FAIL] All actions used fallback parsing.")
        print("       The GLM model output may still be incompatible.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
