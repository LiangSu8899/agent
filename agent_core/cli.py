#!/usr/bin/env python3
"""
CLI entry point for Agent OS.

This module provides the main entry point for the agent-os and aos commands.
"""
import argparse
import os
import sys
import signal
import yaml
from typing import Optional

from .orchestrator import AgentOrchestrator
from .interface.repl import AgentREPL
from .project import ProjectManager
from .config import ConfigManager


def create_orchestrator(config: dict, project_manager: ProjectManager, debug: bool = False) -> AgentOrchestrator:
    """Create an orchestrator from config and project manager."""
    # Get project-specific paths
    db_path = project_manager.get_session_db_path()
    log_dir = project_manager.get_logs_dir()

    # Update config with project paths
    config["session"] = config.get("session", {})
    config["session"]["db_path"] = db_path
    config["session"]["log_dir"] = log_dir

    return AgentOrchestrator(
        db_path=db_path,
        config=config,
        headless=False,
        debug=debug
    )


def resolve_project(args) -> tuple:
    """
    Resolve the project to use based on current directory and state.
    Automatically restores project settings including Planner/Coder models.

    Returns:
        Tuple of (ProjectManager, ConfigManager, config_dict)
    """
    # Initialize managers
    pm = ProjectManager()
    cm = ConfigManager()

    # Load config using proximity principle (cwd first, then global)
    config = cm.load_config()

    # Get current directory
    current_dir = os.getcwd()

    # Check if current directory has .agent folder (existing project)
    agent_dir = os.path.join(current_dir, ".agent")
    if os.path.isdir(agent_dir):
        # Auto-load existing project
        pm.load_project(current_dir)
        print(f"[Auto-restored] Project: {pm.get_project_name()}")

        # Try to restore project-specific config
        project_config_path = os.path.join(agent_dir, "config.yaml")
        if os.path.exists(project_config_path):
            try:
                with open(project_config_path, 'r') as f:
                    project_config = yaml.safe_load(f) or {}

                # Merge project config into main config (project takes precedence)
                if "roles" in project_config:
                    config["roles"] = project_config["roles"]
                    planner = project_config["roles"].get("planner", "?")
                    coder = project_config["roles"].get("coder", "?")
                    print(f"[Auto-restored] Roles: Planner={planner}, Coder={coder}")

            except Exception as e:
                print(f"[Warning] Could not load project config: {e}")

        # Add to recent projects
        pm.add_to_recent_projects(current_dir)
        return pm, cm, config

    # Check startup resolution for other cases
    resolution = pm.resolve_startup_project(current_dir)

    if resolution["action"] == "load":
        # Load existing project
        pm.load_project(resolution["path"])
        print(f"[Loaded] Project: {pm.get_project_name()}")

        # Change to project directory
        if resolution["path"] != current_dir:
            try:
                os.chdir(resolution["path"])
                print(f"[Changed directory] {resolution['path']}")
            except OSError:
                pass

    elif resolution["action"] == "init":
        # No project found, initialize in current directory
        if not hasattr(args, 'no_init') or not args.no_init:
            print(f"[New project] Initializing in: {current_dir}")
            pm.init_project(current_dir)
            print(f"[Created] Project: {pm.get_project_name()}")

    elif resolution["action"] == "ask":
        # Ask user what to do
        print(f"\n[No project] Current directory: {current_dir}")
        if resolution.get('last'):
            print(f"[Last project] {resolution['last']}")
        print()
        print("Options:")
        print("  1) Initialize new project here")
        if resolution.get('last'):
            print(f"  2) Open last project ({os.path.basename(resolution['last'])})")
            print("  3) Exit")
        else:
            print("  2) Exit")
        print()

        try:
            choice = input("Choose: ").strip()
        except (EOFError, KeyboardInterrupt):
            choice = "3" if resolution.get('last') else "2"

        if choice == "1":
            pm.init_project(current_dir)
            print(f"[Created] Project: {pm.get_project_name()}")
        elif choice == "2" and resolution.get('last'):
            pm.load_project(resolution["last"])
            os.chdir(resolution["last"])
            print(f"[Loaded] Project: {pm.get_project_name()}")
        else:
            print("Exiting.")
            sys.exit(0)

    return pm, cm, config


def cmd_init(args, pm: ProjectManager, cm: ConfigManager, config: dict):
    """Initialize a new project in current directory."""
    current_dir = os.getcwd()

    if pm.is_initialized(current_dir):
        print(f"Project already initialized in: {current_dir}")
        return

    pm.init_project(current_dir)
    print(f"Project initialized: {pm.get_project_name()}")
    print(f"Data directory: {pm.get_session_db_path()}")


def cmd_start(args, pm: ProjectManager, cm: ConfigManager, config: dict):
    """Start a new debug session."""
    task = args.task
    if not task:
        print("Error: Task description required")
        sys.exit(1)

    debug = getattr(args, 'debug', False)
    orchestrator = create_orchestrator(config, pm, debug=debug)

    print(f"[{pm.get_project_name()}] Starting task: {task}")
    if debug:
        print("[DEBUG MODE ENABLED] Raw LLM outputs will be printed")
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


def cmd_resume(args, pm: ProjectManager, cm: ConfigManager, config: dict):
    """Resume an existing session."""
    session_id = args.session_id
    if not session_id:
        print("Error: Session ID required")
        sys.exit(1)

    orchestrator = create_orchestrator(config, pm)

    status = orchestrator.get_session_status(session_id)
    if status == "UNKNOWN":
        print(f"Error: Session {session_id} not found")
        sys.exit(1)

    print(f"[{pm.get_project_name()}] Resuming session {session_id} (status: {status})")

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


def cmd_list(args, pm: ProjectManager, cm: ConfigManager, config: dict):
    """List all sessions."""
    orchestrator = create_orchestrator(config, pm)
    sessions = orchestrator.list_tasks()

    print(f"Project: {pm.get_project_name()}")
    print()

    if not sessions:
        print("No sessions found.")
        return

    print(f"{'ID':<12} {'Status':<12} {'Command':<40} {'Created'}")
    print("-" * 80)

    for session in sessions:
        cmd = session['command'][:37] + "..." if len(session['command']) > 40 else session['command']
        print(f"{session['id']:<12} {session['status']:<12} {cmd:<40} {session['created_at']}")


def cmd_logs(args, pm: ProjectManager, cm: ConfigManager, config: dict):
    """Show logs for a session."""
    session_id = args.session_id
    if not session_id:
        print("Error: Session ID required")
        sys.exit(1)

    orchestrator = create_orchestrator(config, pm)
    logs = orchestrator.get_session_logs(session_id)

    if not logs:
        print(f"No logs found for session {session_id}")
        return

    # Optionally tail the logs
    if args.tail:
        lines = logs.split('\n')
        logs = '\n'.join(lines[-args.tail:])

    print(logs)


def cmd_pause(args, pm: ProjectManager, cm: ConfigManager, config: dict):
    """Pause a running session."""
    session_id = args.session_id
    if not session_id:
        print("Error: Session ID required")
        sys.exit(1)

    orchestrator = create_orchestrator(config, pm)
    orchestrator.pause_task(session_id)
    print(f"Session {session_id} paused.")


def cmd_stop(args, pm: ProjectManager, cm: ConfigManager, config: dict):
    """Stop a session."""
    session_id = args.session_id
    if not session_id:
        print("Error: Session ID required")
        sys.exit(1)

    orchestrator = create_orchestrator(config, pm)
    orchestrator.stop_task(session_id)
    print(f"Session {session_id} stopped.")


def cmd_status(args, pm: ProjectManager, cm: ConfigManager, config: dict):
    """Get status of a session."""
    session_id = args.session_id
    if not session_id:
        print("Error: Session ID required")
        sys.exit(1)

    orchestrator = create_orchestrator(config, pm)
    status = orchestrator.get_session_status(session_id)
    print(f"Session {session_id}: {status}")


def cmd_repl(args, pm: ProjectManager, cm: ConfigManager, config: dict):
    """Start interactive REPL."""
    debug = getattr(args, 'debug', False)
    orchestrator = create_orchestrator(config, pm, debug=debug)

    # Add project info to config for REPL display
    config["project"] = {
        "name": pm.get_project_name(),
        "path": pm.get_current_project()
    }

    # Use the actual config path (where config was loaded from)
    config_path = cm.get_config_path()

    if debug:
        print("[DEBUG MODE ENABLED] Raw LLM outputs will be printed")

    repl = AgentREPL(
        orchestrator=orchestrator,
        config=config,
        config_path=str(config_path) if config_path else "config.yaml",
        project_manager=pm,
        debug=debug
    )
    repl.run()


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Agent OS - AI-powered debugging assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
    repl                      - Start interactive REPL (default)
    init                      - Initialize a new project in current directory
    start "task description"  - Start a new debug session
    resume <session_id>       - Resume an existing session
    list                      - List all sessions
    logs <session_id>         - Show logs for a session
    pause <session_id>        - Pause a running session
    stop <session_id>         - Stop a session
"""
    )

    parser.add_argument(
        "--version",
        action="version",
        version="agent-os 0.1.0"
    )

    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        help="Enable debug mode (print raw LLM outputs)"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init command
    subparsers.add_parser("init", help="Initialize a new project in current directory")

    # repl command (default)
    subparsers.add_parser("repl", help="Start interactive REPL (default)")

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

    # Resolve project and load config
    pm, cm, config = resolve_project(args)

    # Default to repl if no command specified
    if not args.command:
        args.command = "repl"

    # Dispatch to command handler
    commands = {
        "init": cmd_init,
        "repl": cmd_repl,
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
        handler(args, pm, cm, config)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
