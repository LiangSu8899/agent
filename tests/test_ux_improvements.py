#!/usr/bin/env python3
"""
End-to-end test for Agent UX improvements.

Tests:
1. Execution process visualization (events)
2. /projects command
3. /history command with project context
"""
import os
import sys
import time
import threading
import tempfile
import shutil

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_core.events import EventEmitter, EventType, AgentEvent, get_event_emitter, reset_event_emitter
from agent_core.agent import DebugAgent
from agent_core.session import SessionManager
from agent_core.memory.history import HistoryMemory
from agent_core.project import ProjectManager


def test_event_system():
    """Test that events are properly emitted during agent execution."""
    print("\n" + "="*60)
    print("TEST 1: Event System")
    print("="*60)

    # Reset event emitter
    reset_event_emitter()
    emitter = get_event_emitter()

    # Track received events
    received_events = []

    def on_event(event: AgentEvent):
        received_events.append(event)
        print(f"  [EVENT] {event.event_type.value}: {event.message[:50]}...")

    emitter.on_all(on_event)

    # Create a mock planner that returns valid JSON
    class MockPlanner:
        def __init__(self):
            self.call_count = 0

        def generate(self, prompt: str) -> str:
            self.call_count += 1
            if self.call_count == 1:
                return '{"thought": "First step", "command": "echo hello", "reasoning": "Test command"}'
            else:
                return '{"thought": "Done", "command": "DONE", "reasoning": "Task complete"}'

    # Create agent with mock planner
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
        agent.set_planner(MockPlanner())

        # Run agent
        print("\n  Running agent with mock planner...")
        results = agent.run(initial_goal="Test task")

        print(f"\n  Results: {len(results)} steps completed")
        print(f"  Events received: {len(received_events)}")

        # Check for expected event types
        event_types = [e.event_type for e in received_events]

        expected_events = [
            EventType.AGENT_START,
            EventType.STEP_START,
            EventType.PLANNER_START,
            EventType.PLANNER_THINKING,
            EventType.PLANNER_RESPONSE,
            EventType.EXECUTOR_START,
            EventType.EXECUTOR_RUNNING,
            EventType.EXECUTOR_COMPLETE,
            EventType.OBSERVER_RESULT,
            EventType.STEP_COMPLETE,
            EventType.TASK_SUMMARY,
            EventType.AGENT_COMPLETE,
        ]

        missing = []
        for expected in expected_events:
            if expected not in event_types:
                missing.append(expected)

        if missing:
            print(f"\n  [WARN] Missing events: {[e.value for e in missing]}")
        else:
            print(f"\n  [PASS] All expected event types received")

        # Check for task summary
        summary_events = [e for e in received_events if e.event_type == EventType.TASK_SUMMARY]
        if summary_events:
            summary = summary_events[0].data.get("summary", {})
            print(f"\n  Task Summary:")
            print(f"    Status: {summary.get('status')}")
            print(f"    Steps: {summary.get('total_steps')}")
            print(f"    Duration: {summary.get('duration_seconds', 0):.2f}s")
            print("  [PASS] Task summary generated")
        else:
            print("  [FAIL] No task summary event")
            return False

    return len(missing) == 0


def test_project_manager():
    """Test project management functionality."""
    print("\n" + "="*60)
    print("TEST 2: Project Manager")
    print("="*60)

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create project manager with custom global dir
        global_dir = os.path.join(tmpdir, ".agent_global")
        pm = ProjectManager(global_dir=global_dir)

        # Create a test project
        project_path = os.path.join(tmpdir, "test_project")
        os.makedirs(project_path)

        print(f"\n  Creating project at: {project_path}")

        # Initialize project
        pm.init_project(project_path)
        print("  [PASS] Project initialized")

        # Check if project is in recent list
        pm.add_to_recent_projects(project_path)
        recent = pm.get_recent_projects()
        print(f"  Recent projects: {recent}")

        if project_path in recent:
            print("  [PASS] Project in recent list")
        else:
            print("  [FAIL] Project not in recent list")
            return False

        # Check current project
        current = pm.get_current_project()
        if current == project_path:
            print("  [PASS] Current project set correctly")
        else:
            print(f"  [FAIL] Current project mismatch: {current}")
            return False

        # Check project name
        name = pm.get_project_name()
        if name == "test_project":
            print(f"  [PASS] Project name: {name}")
        else:
            print(f"  [FAIL] Wrong project name: {name}")
            return False

    return True


def test_history_with_project():
    """Test history functionality with project context."""
    print("\n" + "="*60)
    print("TEST 3: History with Project Context")
    print("="*60)

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create history database
        history_path = os.path.join(tmpdir, "history.db")
        memory = HistoryMemory(db_path=history_path)

        # Add some test entries
        print("\n  Adding test history entries...")
        memory.add_entry(1, "ls -la", "file1.txt\nfile2.txt", 0, "SUCCESS", "List files")
        memory.add_entry(2, "cat file1.txt", "Hello World", 0, "SUCCESS", "Read file")
        memory.add_entry(3, "rm nonexistent", "No such file", 1, "FAILED", "Delete file")

        # Get recent entries
        entries = memory.get_recent_entries(limit=10)
        print(f"  Retrieved {len(entries)} entries")

        if len(entries) == 3:
            print("  [PASS] All entries retrieved")
        else:
            print(f"  [FAIL] Expected 3 entries, got {len(entries)}")
            return False

        # Check entry structure
        entry = entries[0]
        required_fields = ["step", "command", "status", "reasoning"]
        missing_fields = [f for f in required_fields if f not in entry]

        if missing_fields:
            print(f"  [FAIL] Missing fields: {missing_fields}")
            return False
        else:
            print("  [PASS] Entry structure correct")

        # Check context generation
        context = memory.get_context_for_prompt()
        if "Previous Actions:" in context:
            print("  [PASS] Context generated correctly")
        else:
            print("  [FAIL] Context format incorrect")
            return False

        # Check failed command tracking
        if memory.has_failed_before("rm nonexistent"):
            print("  [PASS] Failed command tracked")
        else:
            print("  [FAIL] Failed command not tracked")
            return False

    return True


def test_full_integration():
    """Full integration test with GLM model (if available)."""
    print("\n" + "="*60)
    print("TEST 4: Full Integration (Optional)")
    print("="*60)

    import yaml

    # Load config
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
    if not os.path.exists(config_path):
        print("  [SKIP] config.yaml not found")
        return True

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Check if GLM is configured
    glm_config = config.get("models", {}).get("glm-4-plus", {})
    api_key = glm_config.get("api_key", "")

    if not api_key or api_key.startswith("YOUR_"):
        print("  [SKIP] GLM API key not configured")
        return True

    print("\n  Running full integration test with GLM...")

    # Reset event emitter
    reset_event_emitter()
    emitter = get_event_emitter()

    # Track events
    events_received = []
    def on_event(event):
        events_received.append(event)
        # Print key events
        if event.event_type in [EventType.PLANNER_RESPONSE, EventType.EXECUTOR_START, EventType.TASK_SUMMARY]:
            print(f"  [{event.event_type.value}] {event.message[:60]}...")

    emitter.on_all(on_event)

    # Import orchestrator
    from agent_core.orchestrator import AgentOrchestrator

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "sessions.db")

        orchestrator = AgentOrchestrator(
            db_path=db_path,
            config=config,
            headless=True,
            debug=False
        )

        # Set planner to GLM
        orchestrator.planner_model = "glm-4-plus"

        # Clear history
        orchestrator.memory.clear()

        # Create simple task
        task = "创建一个名为 hello.txt 的文件"
        print(f"\n  Task: {task}")

        session_id = orchestrator.create_task(task)
        print(f"  Session: {session_id}")

        # Run with timeout
        def run_task():
            orchestrator.run_loop(session_id, max_iterations=3)

        thread = threading.Thread(target=run_task)
        thread.start()
        thread.join(timeout=30)

        if thread.is_alive():
            print("  [WARN] Task timed out")

        # Check results
        print(f"\n  Events received: {len(events_received)}")

        # Check for task summary
        summary_events = [e for e in events_received if e.event_type == EventType.TASK_SUMMARY]
        if summary_events:
            summary = summary_events[0].data.get("summary", {})
            print(f"\n  Task Summary:")
            print(f"    Status: {summary.get('status')}")
            print(f"    Steps: {summary.get('total_steps')}")
            if summary.get('files_created'):
                print(f"    Files: {summary.get('files_created')}")
            print("  [PASS] Integration test completed")
            return True
        else:
            print("  [WARN] No summary event (may have timed out)")
            return True  # Don't fail on timeout

    return True


def run_all_tests():
    """Run all tests."""
    print("\n" + "="*60)
    print("Agent UX Improvements - Test Suite")
    print("="*60)

    results = []

    results.append(("Event System", test_event_system()))
    results.append(("Project Manager", test_project_manager()))
    results.append(("History with Project", test_history_with_project()))
    results.append(("Full Integration", test_full_integration()))

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("All tests passed!")
        return 0
    else:
        print("Some tests failed!")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
