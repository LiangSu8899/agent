import os
import time
import sys
import shutil

# Ensure we can import agent_core from parent directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from agent_core.session import SessionManager
except ImportError:
    # Allow test to fail gracefully if module doesn't exist yet
    print("Module agent_core not found (Expected for TDD start)")

def test_long_running_interruption():
    print("--- Starting Phase 1 Verification ---")

    # Clean up previous runs
    if os.path.exists("sessions.db"):
        os.remove("sessions.db")
    if os.path.exists("agent_core/logs"):
        shutil.rmtree("agent_core/logs")

    # 1. Initialize Manager
    manager = SessionManager(db_path="sessions.db")
    print("[1] SessionManager initialized")

    # 2. Create a session simulating a long task
    # Using a shell loop to print numbers and sleep
    cmd = "for i in {1..5}; do echo \"Count $i\"; sleep 1; done"
    session_id = manager.create_session(command=cmd)
    print(f"[2] Session created: {session_id}")

    # 3. Start asynchronously
    manager.start_session(session_id)
    time.sleep(0.5) # Wait for startup

    status = manager.get_status(session_id)
    print(f"[3] Status after start: {status}")
    assert status == "RUNNING", f"Expected RUNNING, got {status}"

    # 4. Simulate user interruption (Pause)
    # Let it run for 2 seconds (should print 1, 2)
    print("[4] Let it run for 2s...")
    time.sleep(2.5)

    manager.pause_session(session_id)
    status = manager.get_status(session_id)
    print(f"[5] Status after pause: {status}")
    assert status == "PAUSED", f"Expected PAUSED, got {status}"

    # 5. Check logs (should contain 'Count 1' and 'Count 2')
    logs = manager.get_logs(session_id)
    print(f"[6] Current Logs:\n{logs}")
    assert "Count 1" in logs, "Logs should contain first output"
    assert "Count 2" in logs, "Logs should contain second output"
    assert "Count 5" not in logs, "Logs should NOT contain future output yet"

    # 6. Resume task
    print("[7] Resuming session...")
    manager.resume_session(session_id)

    # 7. Wait for completion
    # Remaining: 3, 4, 5 (approx 3s)
    time.sleep(4)

    status = manager.get_status(session_id)
    print(f"[8] Status after completion: {status}")
    # Note: Depending on implementation, it might be COMPLETED or still RUNNING if we didn't wait long enough.
    # But for a simple script, 4s should be enough for the remaining 3s.
    assert status == "COMPLETED" or status == "EXITED", f"Expected COMPLETED, got {status}"

    final_logs = manager.get_logs(session_id)
    assert "Count 5" in final_logs, "Final logs should contain the last output"

    print("✅ Phase 1 Acceptance Passed")

if __name__ == "__main__":
    try:
        test_long_running_interruption()
    except Exception as e:
        print(f"❌ Test Failed: {e}")
        sys.exit(1)
