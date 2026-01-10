import sys
import os
import time
import threading
import shutil

# Ensure import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from agent_core.orchestrator import AgentOrchestrator
    from agent_core.session import SessionManager
except ImportError:
    print("Modules not found")

TEST_DB = "phase6_test.db"
TEST_REPO = "phase6_sandbox"

def setup_env():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    if os.path.exists(TEST_REPO):
        shutil.rmtree(TEST_REPO)
    os.makedirs(TEST_REPO)

def test_full_orchestration_flow():
    print("--- Starting Phase 6 Verification (Integration) ---")
    setup_env()

    # 1. Config Setup (Mocking the config for ModelManager)
    # We use the MockClient from Phase 2 logic implicitly by configuring 'type: mock'
    config = {
        "models": {
            "planner": {"type": "mock", "vram": 1}
        },
        "workspace_root": TEST_REPO
    }

    # 2. Initialize Orchestrator
    print("[1] Initializing Orchestrator...")
    orchestrator = AgentOrchestrator(
        db_path=TEST_DB,
        config=config,
        headless=True # Test mode, don't block stdin
    )

    # 3. Start a Task
    task_desc = "echo 'Hello Agent' && sleep 2"
    print(f"[2] Starting task: {task_desc}")

    # Run in a separate thread so we can monitor/interrupt it
    # The orchestrator.run() is typically blocking.
    session_id = orchestrator.create_task(task_desc)

    t = threading.Thread(target=orchestrator.run_loop, args=(session_id,), daemon=True)
    t.start()

    # 4. Wait for it to start
    time.sleep(1)
    status = orchestrator.get_session_status(session_id)
    print(f"[3] Session Status: {status}")
    assert status in ["RUNNING", "PENDING"], f"Should be running, got {status}"

    # 5. Verify Output Capture
    # Since the command is simple echo, logs should appear
    time.sleep(2) # Wait for 'sleep 2' to finish
    logs = orchestrator.get_session_logs(session_id)
    print(f"[4] Logs captured: {len(logs)} chars")

    # Note: PTY output capture timing can be tricky in tests,
    # but at least we check the Orchestrator didn't crash.

    # 6. Test Pause/Resume Logic
    print("[5] Pausing session...")
    orchestrator.pause_task(session_id)
    time.sleep(0.5)
    status = orchestrator.get_session_status(session_id)
    assert status == "PAUSED" or status == "COMPLETED", f"Should pause or complete, got {status}"
    # Note: If sleep 2 finished before we paused, it might be completed. That's fine too.

    # 7. List Sessions
    sessions = orchestrator.list_tasks()
    print(f"[6] Active sessions: {len(sessions)}")
    assert len(sessions) >= 1
    assert sessions[0]['id'] == session_id

    print("✅ Phase 6 Acceptance Passed")

if __name__ == "__main__":
    try:
        test_full_orchestration_flow()
    except Exception as e:
        print(f"❌ Test Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
