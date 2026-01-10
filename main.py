#!/usr/bin/env python3
"""
Debug Agent CLI - Main entry point for the debug agent.

Commands:
    start "task description"  - Start a new debug session
    resume <session_id>       - Resume an existing session
    list                      - List all sessions
    logs <session_id>         - Show logs for a session
    pause <session_id>        - Pause a running session
    stop <session_id>         - Stop a session
"""
import argparse
import os
import sys
import signal
import yaml
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_core.orchestrator import AgentOrchestrator


DEFAULT_CONFIG_PATH = "config.yaml"
DEFAULT_CONFIG = {
    "models": {
        "planner": {"type": "mock", "vram": 7},
        "coder": {"type": "mock", "vram": 18}
    },
    "workspace_root": ".",
    "session": {
        "db_path": "sessions.db",
        "log_dir": "agent_core/logs",
        "max_steps": 50
    }
}


def load_config(config_path: str) -> dict:
    """Load configuration from YAML file, creating default if missing."""
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return yaml.safe_load(f) or DEFAULT_CONFIG
    else:
        # Create default config
        with open(config_path, 'w') as f:
            yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False)
        print(f"Created default config at {config_path}")
        return DEFAULT_CONFIG


def create_orchestrator(config: dict) -> AgentOrchestrator:
    """Create an orchestrator from config."""
    session_config = config.get("session", {})
    db_path = session_config.get("db_path", "sessions.db")

    return AgentOrchestrator(
        db_path=db_path,
        config=config,
        headless=False
    )


def cmd_start(args, config: dict):
    """Start a new debug session."""
    task = args.task
    if not task:
        print("Error: Task description required")
        sys.exit(1)

    orchestrator = create_orchestrator(config)

    print(f"Starting task: {task}")
    session_id = orchestrator.create_task(task)
    print(f"Session ID: {session_id}")

    # Setup signal handler for graceful pause
    def signal_handler(sig, frame):
        print("\nPausing session...")
        orchestrator.pause_task(session_id)
        print(f"Session {session_id} paused. Use 'resume {session_id}' to continue.")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    # Run the loop
    try:
        orchestrator.run_loop(session_id)
        status = orchestrator.get_session_status(session_id)
        print(f"\nSession completed with status: {status}")

        # Show final logs
        logs = orchestrator.get_session_logs(session_id)
        if logs:
            print("\n--- Session Output ---")
            print(logs[-2000:] if len(logs) > 2000 else logs)

    except KeyboardInterrupt:
        orchestrator.pause_task(session_id)
        print(f"\nSession {session_id} paused.")


def cmd_resume(args, config: dict):
    """Resume an existing session."""
    session_id = args.session_id
    if not session_id:
        print("Error: Session ID required")
        sys.exit(1)

    orchestrator = create_orchestrator(config)

    status = orchestrator.get_session_status(session_id)
    if status == "UNKNOWN":
        print(f"Error: Session {session_id} not found")
        sys.exit(1)

    print(f"Resuming session {session_id} (status: {status})")

    # Setup signal handler
    def signal_handler(sig, frame):
        print("\nPausing session...")
        orchestrator.pause_task(session_id)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    # Resume and run
    try:
        orchestrator.resume_task(session_id)
        orchestrator.run_loop(session_id)
        status = orchestrator.get_session_status(session_id)
        print(f"\nSession completed with status: {status}")

    except KeyboardInterrupt:
        orchestrator.pause_task(session_id)
        print(f"\nSession {session_id} paused.")


def cmd_list(args, config: dict):
    """List all sessions."""
    orchestrator = create_orchestrator(config)
    sessions = orchestrator.list_tasks()

    if not sessions:
        print("No sessions found.")
        return

    print(f"{'ID':<12} {'Status':<12} {'Command':<40} {'Created'}")
    print("-" * 80)

    for session in sessions:
        cmd = session['command'][:37] + "..." if len(session['command']) > 40 else session['command']
        print(f"{session['id']:<12} {session['status']:<12} {cmd:<40} {session['created_at']}")


def cmd_logs(args, config: dict):
    """Show logs for a session."""
    session_id = args.session_id
    if not session_id:
        print("Error: Session ID required")
        sys.exit(1)

    orchestrator = create_orchestrator(config)
    logs = orchestrator.get_session_logs(session_id)

    if not logs:
        print(f"No logs found for session {session_id}")
        return

    # Optionally tail the logs
    if args.tail:
        lines = logs.split('\n')
        logs = '\n'.join(lines[-args.tail:])

    print(logs)


def cmd_pause(args, config: dict):
    """Pause a running session."""
    session_id = args.session_id
    if not session_id:
        print("Error: Session ID required")
        sys.exit(1)

    orchestrator = create_orchestrator(config)
    orchestrator.pause_task(session_id)
    print(f"Session {session_id} paused.")


def cmd_stop(args, config: dict):
    """Stop a session."""
    session_id = args.session_id
    if not session_id:
        print("Error: Session ID required")
        sys.exit(1)

    orchestrator = create_orchestrator(config)
    orchestrator.stop_task(session_id)
    print(f"Session {session_id} stopped.")


def cmd_status(args, config: dict):
    """Get status of a session."""
    session_id = args.session_id
    if not session_id:
        print("Error: Session ID required")
        sys.exit(1)

    orchestrator = create_orchestrator(config)
    status = orchestrator.get_session_status(session_id)
    print(f"Session {session_id}: {status}")


def main():
    parser = argparse.ArgumentParser(
        description="Debug Agent CLI - AI-powered debugging assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        "-c", "--config",
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to config file (default: {DEFAULT_CONFIG_PATH})"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # start command
    start_parser = subparsers.add_parser("start", help="Start a new debug session")
    start_parser.add_argument("task", help="Task description or command to execute")

    # resume command
    resume_parser = subparsers.add_parser("resume", help="Resume an existing session")
    resume_parser.add_argument("session_id", help="Session ID to resume")

    # list command
    subparsers.add_parser("list", help="List all sessions")

    # logs command
    logs_parser = subparsers.add_parser("logs", help="Show logs for a session")
    logs_parser.add_argument("session_id", help="Session ID")
    logs_parser.add_argument("-n", "--tail", type=int, help="Show last N lines")

    # pause command
    pause_parser = subparsers.add_parser("pause", help="Pause a running session")
    pause_parser.add_argument("session_id", help="Session ID to pause")

    # stop command
    stop_parser = subparsers.add_parser("stop", help="Stop a session")
    stop_parser.add_argument("session_id", help="Session ID to stop")

    # status command
    status_parser = subparsers.add_parser("status", help="Get status of a session")
    status_parser.add_argument("session_id", help="Session ID")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Load config
    config = load_config(args.config)

    # Dispatch to command handler
    commands = {
        "start": cmd_start,
        "resume": cmd_resume,
        "list": cmd_list,
        "logs": cmd_logs,
        "pause": cmd_pause,
        "stop": cmd_stop,
        "status": cmd_status,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args, config)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
