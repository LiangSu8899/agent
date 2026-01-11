"""
Agent Orchestrator - Wires all components together.
Manages the lifecycle of debug sessions and coordinates between components.
"""
import os
import time
import threading
from typing import Any, Dict, List, Optional

from .session import SessionManager
from .models.manager import ModelManager
from .memory.history import HistoryMemory
from .analysis.observer import OutputObserver
from .analysis.classifier import ErrorClassifier
from .tools.files import FileEditor
from .tools.git import GitHandler
from .agent import DebugAgent, AgentState
from .security import SafetyPolicy


class AgentOrchestrator:
    """
    Main orchestrator that wires all agent components together.
    Manages sessions, models, memory, and tools.
    """

    def __init__(
        self,
        db_path: str = "sessions.db",
        config: Optional[Dict[str, Any]] = None,
        headless: bool = False,
        debug: bool = False
    ):
        """
        Initialize the AgentOrchestrator.

        Args:
            db_path: Path to the SQLite database for sessions
            config: Configuration dictionary with models, workspace settings
            headless: If True, run in non-interactive mode (for testing)
            debug: If True, enable debug mode (print raw LLM outputs)
        """
        self.config = config or {}
        self.headless = headless
        self.debug = debug
        self.db_path = db_path

        # Extract config sections
        models_config = self.config.get("models", {})
        roles_config = self.config.get("roles", {})
        self.workspace_root = self.config.get("system", {}).get("workspace_root", ".")
        security_config = self.config.get("security", {})
        session_config = self.config.get("session", {})

        # Initialize components
        self.session_manager = SessionManager(db_path=db_path)
        self.model_manager = ModelManager(config=models_config) if models_config else None
        self.memory = HistoryMemory(db_path=db_path.replace(".db", "_history.db"))
        self.observer = OutputObserver()
        self.classifier = ErrorClassifier()
        self.file_editor = FileEditor(root=self.workspace_root)
        self.git_handler = GitHandler(root=self.workspace_root)
        self.safety_policy = SafetyPolicy(config=security_config)

        # Store role assignments
        self.planner_model = roles_config.get("planner", "planner")
        self.coder_model = roles_config.get("coder", "coder")
        self.max_steps = session_config.get("max_steps", 50)

        # Active sessions tracking
        self._active_sessions: Dict[str, Dict[str, Any]] = {}
        self._active_agents: Dict[str, Any] = {} # Can be DebugAgent or EngineeringAgent
        self._stop_events: Dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def set_planner_role(self, model_name: str):
        """Update the planner model role."""
        self.planner_model = model_name

    def set_coder_role(self, model_name: str):
        """Update the coder model role."""
        self.coder_model = model_name

    def create_task(self, task_description: str) -> str:
        """
        Create a new task/session with a DebugAgent.

        The task_description is a natural language goal that will be passed
        to the DebugAgent, which uses the Planner LLM to convert it into
        shell commands.

        Args:
            task_description: Natural language task description (e.g., "Help me write a snake game")

        Returns:
            Session ID
        """
        # Create a blank session (not executing the task directly!)
        # The session is just for tracking - the agent will create sub-sessions for commands
        session_id = self.session_manager.create_session(
            command=f"[AGENT TASK] {task_description}"
        )

        # Create a DebugAgent for this task
        agent = DebugAgent(
            session_manager=self.session_manager,
            model_manager=self.model_manager,
            memory=self.memory,
            max_steps=self.max_steps,
            planner_model=self.planner_model,
            debug=self.debug,
            workspace_root=self.workspace_root or "."
        )

        with self._lock:
            self._active_sessions[session_id] = {
                "task": task_description,
                "created_at": time.time(),
                "step": 0,
                "is_natural_language": True  # Flag to indicate this is an NL task
            }
            self._active_agents[session_id] = agent
            self._stop_events[session_id] = threading.Event()

        return session_id

    def run_loop(self, session_id: str, max_iterations: int = 100):
        """
        Run the main orchestration loop for a session.

        For natural language tasks, this delegates to the DebugAgent which
        uses the Planner to convert the task into shell commands.

        Args:
            session_id: The session to run
            max_iterations: Maximum number of loop iterations
        """
        stop_event = self._stop_events.get(session_id)
        if not stop_event:
            return

        # Get session info
        with self._lock:
            session_info = self._active_sessions.get(session_id, {})
            agent = self._active_agents.get(session_id)

        task_description = session_info.get("task", "")
        is_nl_task = session_info.get("is_natural_language", False)

        if is_nl_task and agent:
            # Natural language task: use the DebugAgent
            self._run_agent_loop(session_id, agent, task_description, stop_event)
        else:
            # Legacy behavior: direct command execution monitoring
            # Start the session only for direct execution
            self.session_manager.start_session(session_id)
            self._run_legacy_loop(session_id, stop_event, max_iterations)

    def _run_agent_loop(
        self,
        session_id: str,
        agent: DebugAgent,
        task_description: str,
        stop_event: threading.Event
    ):
        """
        Run the DebugAgent loop for a natural language task.

        Args:
            session_id: The session ID
            agent: The DebugAgent instance
            task_description: The natural language task
            stop_event: Event to signal stop
        """
        try:
            # Add a start log to the session so it's not empty
            self.session_manager._sessions[session_id]._append_log(f"\n[AGENT] Starting goal: {task_description}\n")

            # Run the agent with the initial goal
            results = agent.run(initial_goal=task_description)

            # Update session info with results
            with self._lock:
                if session_id in self._active_sessions:
                    self._active_sessions[session_id]["results"] = results
                    self._active_sessions[session_id]["step"] = len(results)
                    self._active_sessions[session_id]["completed_at"] = time.time()

            # Determine final status
            if results and results[-1].status == "COMPLETED":
                self.session_manager.complete_session(session_id)
            elif agent.state == AgentState.FAILED:
                self.session_manager.fail_session(session_id)
            else:
                self.session_manager.complete_session(session_id)

        except Exception as e:
            # Log the error
            print(f"[Orchestrator] Error in agent loop: {e}")
            import traceback
            traceback.print_exc()
            
            with self._lock:
                if session_id in self._active_sessions:
                    self._active_sessions[session_id]["error"] = str(e)
            
            # Append error to session logs for visibility in REPL
            self.session_manager._sessions[session_id]._append_log(f"\n[ERROR] {str(e)}\n")
            self.session_manager.fail_session(session_id)

    def _run_legacy_loop(
        self,
        session_id: str,
        stop_event: threading.Event,
        max_iterations: int
    ):
        """
        Legacy loop for direct command execution (backward compatibility).

        Args:
            session_id: The session ID
            stop_event: Event to signal stop
            max_iterations: Maximum iterations
        """
        iteration = 0
        last_log_length = 0

        while iteration < max_iterations and not stop_event.is_set():
            iteration += 1

            # Check session status
            status = self.session_manager.get_status(session_id)

            if status in ("COMPLETED", "EXITED", "FAILED"):
                break

            if status == "PAUSED":
                # Wait for resume or stop
                stop_event.wait(timeout=0.5)
                continue

            # Get recent logs
            logs = self.session_manager.get_logs(session_id)

            # Check if there's new output
            if len(logs) > last_log_length:
                new_output = logs[last_log_length:]
                last_log_length = len(logs)

                # Observe the output
                events = self.observer.observe(new_output)

                # Check for errors
                errors = [e for e in events if e.event_type in ('error', 'traceback')]

                if errors and self.model_manager:
                    # Classify the error
                    error_category = self.classifier.classify(new_output)

                    # Record in memory
                    with self._lock:
                        step = self._active_sessions[session_id]["step"]
                        self._active_sessions[session_id]["step"] = step + 1

                    self.memory.add_entry(
                        step=step,
                        command=self._active_sessions[session_id]["task"],
                        output=new_output[-1000:],  # Last 1000 chars
                        exit_code=1,
                        status="ERROR_DETECTED",
                        reasoning=f"Detected {error_category}"
                    )

            # Small delay to prevent busy-waiting
            time.sleep(0.2)

        # Update session info
        with self._lock:
            if session_id in self._active_sessions:
                self._active_sessions[session_id]["completed_at"] = time.time()

    def run(self, task_description: str) -> str:
        """
        Create and run a task synchronously.

        Args:
            task_description: The command or task to execute

        Returns:
            Session ID
        """
        session_id = self.create_task(task_description)
        self.run_loop(session_id)
        return session_id

    def pause_task(self, session_id: str):
        """Pause a running task."""
        self.session_manager.pause_session(session_id)

    def resume_task(self, session_id: str):
        """Resume a paused task."""
        self.session_manager.resume_session(session_id)

        # Restart the run loop if it was stopped
        stop_event = self._stop_events.get(session_id)
        if stop_event and stop_event.is_set():
            stop_event.clear()
            t = threading.Thread(
                target=self.run_loop,
                args=(session_id,),
                daemon=True
            )
            t.start()

    def stop_task(self, session_id: str):
        """Stop a task completely."""
        stop_event = self._stop_events.get(session_id)
        if stop_event:
            stop_event.set()
        self.session_manager.terminate_session(session_id)

    def get_session_status(self, session_id: str) -> str:
        """Get the status of a session."""
        return self.session_manager.get_status(session_id)

    def get_session_logs(self, session_id: str) -> str:
        """Get logs for a session."""
        return self.session_manager.get_logs(session_id)

    def list_tasks(self) -> List[Dict[str, Any]]:
        """List all tasks/sessions."""
        sessions = self.session_manager.list_sessions()

        # Enrich with active session info
        result = []
        for session in sessions:
            session_id = session["session_id"]
            info = {
                "id": session_id,
                "command": session["command"],
                "status": session["status"],
                "created_at": session["created_at"]
            }

            with self._lock:
                if session_id in self._active_sessions:
                    info["step"] = self._active_sessions[session_id].get("step", 0)

            result.append(info)

        return result

    def create_checkpoint(self, message: str = "Pre-fix checkpoint") -> Optional[str]:
        """
        Create a Git checkpoint before making changes.

        Args:
            message: Checkpoint commit message

        Returns:
            Commit hash or None if no changes
        """
        try:
            if not self.git_handler.is_repo():
                self.git_handler.init_repo()

            if self.git_handler.has_changes():
                return self.git_handler.commit_all(f"[CHECKPOINT] {message}")
            return self.git_handler.get_current_commit()
        except Exception:
            return None

    def rollback(self, commit_hash: Optional[str] = None):
        """
        Rollback to a checkpoint.

        Args:
            commit_hash: Specific commit to rollback to, or HEAD if None
        """
        try:
            if commit_hash:
                self.git_handler.reset_hard(commit_hash)
            else:
                self.git_handler.reset_hard("HEAD")
        except Exception:
            pass

    def get_memory_context(self) -> str:
        """Get the memory context for prompts."""
        return self.memory.get_context_for_prompt()

    def cleanup(self):
        """Clean up resources."""
        # Stop all active sessions
        for session_id in list(self._stop_events.keys()):
            self.stop_task(session_id)
