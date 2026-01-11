"""
Event system for Agent execution progress reporting.
Provides real-time visibility into Agent's Think -> Act -> Observe loop.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import threading


class EventType(Enum):
    """Types of events emitted during agent execution."""
    # Agent lifecycle
    AGENT_START = "agent_start"
    AGENT_COMPLETE = "agent_complete"
    AGENT_ERROR = "agent_error"

    # Step lifecycle
    STEP_START = "step_start"
    STEP_COMPLETE = "step_complete"

    # Phase events (Think -> Act -> Observe)
    PLANNER_START = "planner_start"
    PLANNER_THINKING = "planner_thinking"
    PLANNER_RESPONSE = "planner_response"

    EXECUTOR_START = "executor_start"
    EXECUTOR_RUNNING = "executor_running"
    EXECUTOR_COMPLETE = "executor_complete"

    OBSERVER_START = "observer_start"
    OBSERVER_RESULT = "observer_result"

    # File operations
    FILE_CREATE = "file_create"
    FILE_MODIFY = "file_modify"
    FILE_DELETE = "file_delete"

    # Token usage
    TOKEN_USAGE = "token_usage"

    # Summary
    TASK_SUMMARY = "task_summary"


@dataclass
class AgentEvent:
    """An event emitted during agent execution."""
    event_type: EventType
    timestamp: datetime = field(default_factory=datetime.now)
    step: int = 0
    data: Dict[str, Any] = field(default_factory=dict)
    message: str = ""

    def __str__(self) -> str:
        return f"[{self.event_type.value}] {self.message}"


class EventEmitter:
    """
    Event emitter for agent execution progress.
    Allows subscribers to receive real-time updates.
    """

    def __init__(self):
        self._listeners: Dict[EventType, List[Callable[[AgentEvent], None]]] = {}
        self._global_listeners: List[Callable[[AgentEvent], None]] = []
        self._lock = threading.Lock()
        self._event_history: List[AgentEvent] = []
        self._max_history = 100

    def on(self, event_type: EventType, callback: Callable[[AgentEvent], None]):
        """
        Subscribe to a specific event type.

        Args:
            event_type: The type of event to listen for
            callback: Function to call when event occurs
        """
        with self._lock:
            if event_type not in self._listeners:
                self._listeners[event_type] = []
            self._listeners[event_type].append(callback)

    def on_all(self, callback: Callable[[AgentEvent], None]):
        """
        Subscribe to all events.

        Args:
            callback: Function to call for any event
        """
        with self._lock:
            self._global_listeners.append(callback)

    def off(self, event_type: EventType, callback: Callable[[AgentEvent], None]):
        """Remove a listener for a specific event type."""
        with self._lock:
            if event_type in self._listeners:
                try:
                    self._listeners[event_type].remove(callback)
                except ValueError:
                    pass

    def emit(self, event: AgentEvent):
        """
        Emit an event to all subscribers.

        Args:
            event: The event to emit
        """
        with self._lock:
            # Store in history
            self._event_history.append(event)
            if len(self._event_history) > self._max_history:
                self._event_history.pop(0)

            # Get listeners
            specific_listeners = self._listeners.get(event.event_type, []).copy()
            global_listeners = self._global_listeners.copy()

        # Call listeners outside lock
        for listener in specific_listeners:
            try:
                listener(event)
            except Exception as e:
                print(f"[EventEmitter] Error in listener: {e}")

        for listener in global_listeners:
            try:
                listener(event)
            except Exception as e:
                print(f"[EventEmitter] Error in global listener: {e}")

    def emit_simple(
        self,
        event_type: EventType,
        message: str,
        step: int = 0,
        **data
    ):
        """
        Convenience method to emit an event with simple parameters.

        Args:
            event_type: Type of event
            message: Human-readable message
            step: Current step number
            **data: Additional event data
        """
        event = AgentEvent(
            event_type=event_type,
            message=message,
            step=step,
            data=data
        )
        self.emit(event)

    def get_history(self, limit: int = 50) -> List[AgentEvent]:
        """Get recent event history."""
        with self._lock:
            return self._event_history[-limit:]

    def clear_history(self):
        """Clear event history."""
        with self._lock:
            self._event_history.clear()


# Global event emitter instance
_global_emitter: Optional[EventEmitter] = None


def get_event_emitter() -> EventEmitter:
    """Get the global event emitter instance."""
    global _global_emitter
    if _global_emitter is None:
        _global_emitter = EventEmitter()
    return _global_emitter


def reset_event_emitter():
    """Reset the global event emitter (for testing)."""
    global _global_emitter
    _global_emitter = EventEmitter()


@dataclass
class TaskSummary:
    """Summary of a completed task."""
    goal: str
    status: str
    total_steps: int
    successful_steps: int
    failed_steps: int
    files_created: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    commands_executed: List[str] = field(default_factory=list)
    total_lines_written: int = 0
    duration_seconds: float = 0.0
    error_message: Optional[str] = None
    unmet_requirements: List[str] = field(default_factory=list)
    root_cause_analysis: List[str] = field(default_factory=list)
    repair_actions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "status": self.status,
            "total_steps": self.total_steps,
            "successful_steps": self.successful_steps,
            "failed_steps": self.failed_steps,
            "files_created": self.files_created,
            "files_modified": self.files_modified,
            "commands_executed": self.commands_executed,
            "total_lines_written": self.total_lines_written,
            "duration_seconds": self.duration_seconds,
            "error_message": self.error_message,
            "unmet_requirements": self.unmet_requirements,
            "root_cause_analysis": self.root_cause_analysis,
            "repair_actions": self.repair_actions
        }
