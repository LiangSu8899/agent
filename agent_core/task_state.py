"""
Task State Tracker - Maintains persistent history and state of the current task.
Provides a "ground truth" for the agent to track progress and identify errors.
"""
import os
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from datetime import datetime

@dataclass
class StepState:
    """State of a single step execution."""
    step_number: int
    description: str
    status: str
    output: str = ""
    error: str = ""
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    verification_passed: bool = False
    verification_evidence: str = ""

@dataclass
class TaskState:
    """Persistent state of the entire task."""
    task_id: str
    goal: str
    workspace_root: str
    steps: List[Dict[str, Any]] = field(default_factory=list)
    current_step: int = 0
    start_time: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

class TaskStateTracker:
    """
    Manages persistent task state and history.
    Saves to .agent/task_state.json for recovery and LLM context.
    """
    
    def __init__(self, workspace_root: str, task_id: str):
        self.workspace_root = os.path.abspath(workspace_root)
        self.task_id = task_id
        self.state_dir = os.path.join(self.workspace_root, ".agent")
        self.state_path = os.path.join(self.state_dir, f"state_{task_id}.json")
        self.state: Optional[TaskState] = None
        
        # Ensure state directory exists
        os.makedirs(self.state_dir, exist_ok=True)

    def initialize(self, goal: str):
        """Initialize a new task state."""
        self.state = TaskState(
            task_id=self.task_id,
            goal=goal,
            workspace_root=self.workspace_root
        )
        self.save()

    def add_step(self, step_number: int, description: str):
        """Add a planned step to the history."""
        step_data = StepState(
            step_number=step_number,
            description=description,
            status="pending"
        )
        self.state.steps.append(asdict(step_data))
        self.save()

    def update_step(self, step_number: int, **kwargs):
        """Update an existing step's status and data."""
        if not self.state: return
        
        for step in self.state.steps:
            if step["step_number"] == step_number:
                step.update(kwargs)
                if "status" in kwargs and kwargs["status"] in ("completed", "failed"):
                    step["end_time"] = time.time()
                break
        self.save()

    def get_context_for_llm(self) -> str:
        """Format the current state as context for LLM reasoning."""
        if not self.state: return ""
        
        history = []
        for s in self.state.steps:
            status_icon = "✅" if s.get("verification_passed") else ("❌" if s.get("status") == "failed" else "⏳")
            history.append(f"Step {s['step_number']}: {s['description']} | Status: {s['status']} {status_icon}")
            if s.get("error"):
                history.append(f"  - Error: {s['error']}")
            elif s.get("verification_evidence"):
                history.append(f"  - Evidence: {s['verification_evidence'][:100]}...")
        
        return "\n".join(history)

    def get_repair_actions(self) -> List[str]:
        """Get descriptions of steps that were injected as repairs."""
        if not self.state: return []
        return [s["description"] for s in self.state.steps if "[REPAIR]" in s.get("description", "")]

    def save(self):
        """Persist state to disk."""
        if not self.state: return
        try:
            with open(self.state_path, 'w', encoding='utf-8') as f:
                json.dump(asdict(self.state), f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[TaskStateTracker] Failed to save state: {e}")

    @classmethod
    def load(cls, workspace_root: str, task_id: str) -> Optional['TaskStateTracker']:
        """Load an existing task state from disk."""
        tracker = cls(workspace_root, task_id)
        if os.path.exists(tracker.state_path):
            try:
                with open(tracker.state_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    tracker.state = TaskState(**data)
                    return tracker
            except Exception:
                pass
        return None
