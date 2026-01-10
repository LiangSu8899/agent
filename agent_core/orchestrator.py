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


class AgentOrchestrator:
    """
    Main orchestrator that wires all agent components together.
    Manages sessions, models, memory, and tools.
    """

    def __init__(
        self,
        db_path: str = "sessions.db",
        config: Optional[Dict[str, Any]] = None,
        headless: bool = False
    ):
        """
        Initialize the AgentOrchestrator.

        Args:
            db_path: Path to the SQLite database for sessions
            config: Configuration dictionary with models, workspace settings
            headless: If True, run in non-interactive mode (for testing)
        """
        self.config = config or {}
        self.headless = headless
        self.db_path = db_path

        # Extract config sections
        models_config = self.config.get("models", {})
        workspace_root = self.config.get("workspace_root", ".")

        # Initialize components
        self.session_manager = SessionManager(db_path=db_path)
        self.model_manager = ModelManager(config=models_config) if models_config else None
        self.memory = HistoryMemory(db_path=db_path.replace(".db", "_history.db"))
        self.observer = OutputObserver()
        self.classifier = ErrorClassifier()
        self.file_editor = FileEditor(root=workspace_root)
        self.git_handler = GitHandler(root=workspace_root)

        # Active sessions tracking
        self._active_sessions: Dict[str, Dict[str, Any]] = {}
        self._stop_events: Dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def create_task(self, task_description: str) -> str:
        """
        Create a new task/session.

        Args:
            task_description: The command or task to execute

        Returns:
            Session ID
        """
        session_id = self.session_manager.create_session(command=task_description)

        with self._lock:
            self._active_sessions[session_id] = {
                "task": task_description,
                "created_at": time.time(),
                "step": 0
            }
            self._stop_events[session_id] = threading.Event()

        return session_id

    def run_loop(self, session_id: str, max_iterations: int = 100):
        """
        Run the main orchestration loop for a session.

        Args:
            session_id: The session to run
            max_iterations: Maximum number of loop iterations
        """
        stop_event = self._stop_events.get(session_id)
        if not stop_event:
            return

        # Start the session
        self.session_manager.start_session(session_id)

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
