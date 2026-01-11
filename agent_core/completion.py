"""
Completion Gate - Task completion detection and convergence mechanism.
Prevents infinite loops and detects when tasks are truly complete.
"""
import hashlib
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class CompletionStatus(Enum):
    """Status of completion check."""
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    STALLED = "stalled"  # No progress being made
    LOOP_DETECTED = "loop_detected"  # Repeating same actions
    FAILED = "failed"


@dataclass
class StateSnapshot:
    """Snapshot of the current environment state."""
    files_exist: Set[str] = field(default_factory=set)
    file_hashes: Dict[str, str] = field(default_factory=dict)
    directories_exist: Set[str] = field(default_factory=set)
    last_command: str = ""
    last_output: str = ""
    last_exit_code: int = 0

    def to_hash(self) -> str:
        """Create a hash of the current state for comparison."""
        state_str = (
            str(sorted(self.files_exist)) +
            str(sorted(self.file_hashes.items())) +
            str(sorted(self.directories_exist)) +
            str(self.last_exit_code)
        )
        return hashlib.md5(state_str.encode()).hexdigest()[:16]


@dataclass
class ActionRecord:
    """Record of an executed action."""
    command: str
    command_hash: str
    output_hash: str
    exit_code: int
    state_hash: str


class CompletionGate:
    """
    Completion Gate for detecting task completion and preventing infinite loops.

    Features:
    - Detects repeated actions with no state change
    - Tracks environment state (files, directories)
    - Determines if task goal has been achieved
    - Prevents stalling on failed actions
    """

    def __init__(
        self,
        max_repeated_actions: int = 3,
        max_stall_count: int = 5,
        workspace_root: str = "."
    ):
        """
        Initialize the Completion Gate.

        Args:
            max_repeated_actions: Max times same action can repeat without state change
            max_stall_count: Max steps without meaningful progress
            workspace_root: Root directory for file state tracking
        """
        self.max_repeated_actions = max_repeated_actions
        self.max_stall_count = max_stall_count
        self.workspace_root = os.path.abspath(workspace_root)

        # Action history
        self._action_history: List[ActionRecord] = []
        self._state_history: List[str] = []

        # Counters
        self._repeated_action_count: Dict[str, int] = {}
        self._stall_count = 0
        self._last_state_hash = ""

        # Goal tracking
        self._goal_keywords: List[str] = []
        self._expected_files: List[str] = []
        self._expected_patterns: List[str] = []

    def set_goal(self, goal: str):
        """
        Parse and set the task goal for completion detection.

        Args:
            goal: Natural language goal description
        """
        goal_lower = goal.lower()

        # Extract expected files from goal
        file_patterns = [
            r'(?:create|write|make|generate)\s+(?:a\s+)?(?:file\s+)?["\']?(\w+\.\w+)["\']?',
            r'(?:file|script)\s+(?:named|called)\s+["\']?(\w+\.\w+)["\']?',
            r'(\w+\.py|\w+\.js|\w+\.ts|\w+\.html|\w+\.css)',
        ]

        for pattern in file_patterns:
            matches = re.findall(pattern, goal_lower)
            self._expected_files.extend(matches)

        # Extract keywords for completion detection
        completion_keywords = ['clone', 'create', 'write', 'implement', 'build', 'setup', 'install']
        for keyword in completion_keywords:
            if keyword in goal_lower:
                self._goal_keywords.append(keyword)

        # Detect specific patterns
        if 'clone' in goal_lower:
            self._expected_patterns.append('clone_success')
        if 'snake' in goal_lower or '贪吃蛇' in goal:
            self._expected_files.append('snake.py')
        if 'hello' in goal_lower:
            self._expected_files.append('hello.txt')

    def take_snapshot(self) -> StateSnapshot:
        """
        Take a snapshot of the current environment state.
        Detects ANY change in the workspace to prevent false stall detections.
        """
        snapshot = StateSnapshot()

        # 1. Check for expected files (High priority track)
        for filename in self._expected_files:
            filepath = os.path.join(self.workspace_root, filename)
            if os.path.exists(filepath):
                snapshot.files_exist.add(filename)
                try:
                    with open(filepath, 'rb') as f:
                        content = f.read(4096) # Just first 4KB
                        snapshot.file_hashes[filename] = hashlib.md5(content).hexdigest()[:16]
                except Exception:
                    pass

        # 2. Broad scan: Check file count and last modified times in root/1st level
        # This ensures ANY new file or mod is detected even if not 'expected'
        try:
            root_items = os.listdir(self.workspace_root)
            snapshot.files_exist.update(root_items[:50]) # Track up to 50 names
            
            # Simple broad metric: Total file count (recursive to depth 2)
            file_count = 0
            for root, dirs, files in os.walk(self.workspace_root):
                if root.count(os.sep) - self.workspace_root.count(os.sep) > 2:
                    continue
                file_count += len(files) + len(dirs)
            
            # Use file count as a "pseudo-file" to trigger state change
            snapshot.file_hashes["__internal_total_items__"] = str(file_count)
        except Exception:
            pass

        # 3. Check common directories
        common_dirs = ['.git', 'node_modules', '__pycache__', 'venv', '.venv']
        for dirname in common_dirs:
            dirpath = os.path.join(self.workspace_root, dirname)
            if os.path.isdir(dirpath):
                snapshot.directories_exist.add(dirname)

        return snapshot

    def _hash_command(self, command: str) -> str:
        """Create a normalized hash of a command."""
        # Normalize: strip, lowercase, remove extra whitespace
        normalized = ' '.join(command.strip().lower().split())
        return hashlib.md5(normalized.encode()).hexdigest()[:16]

    def _hash_output(self, output: str) -> str:
        """Create a hash of command output."""
        # Only hash first 1000 chars to avoid large outputs
        return hashlib.md5(output[:1000].encode()).hexdigest()[:16]

    def check_completion(
        self,
        command: str,
        output: str,
        exit_code: int,
        thought: str = ""
    ) -> CompletionStatus:
        """
        Check if the task is complete or if we should stop.

        Args:
            command: The command that was executed
            output: Output from the command
            exit_code: Exit code of the command
            thought: Planner's thought/reasoning

        Returns:
            CompletionStatus indicating current state
        """
        # Handle explicit DONE command
        if command.upper() == "DONE":
            return CompletionStatus.COMPLETED

        # Take current state snapshot
        current_snapshot = self.take_snapshot()
        current_snapshot.last_command = command
        current_snapshot.last_output = output[:500]
        current_snapshot.last_exit_code = exit_code

        current_state_hash = current_snapshot.to_hash()
        command_hash = self._hash_command(command)
        output_hash = self._hash_output(output)

        # Record this action
        action = ActionRecord(
            command=command,
            command_hash=command_hash,
            output_hash=output_hash,
            exit_code=exit_code,
            state_hash=current_state_hash
        )
        self._action_history.append(action)
        self._state_history.append(current_state_hash)

        # Check for repeated actions
        if command_hash in self._repeated_action_count:
            self._repeated_action_count[command_hash] += 1
        else:
            self._repeated_action_count[command_hash] = 1

        if self._repeated_action_count[command_hash] >= self.max_repeated_actions:
            # Check if state changed despite repeated command
            if len(self._state_history) >= 2:
                if self._state_history[-1] == self._state_history[-2]:
                    return CompletionStatus.LOOP_DETECTED

        # Check for stalling (no state change)
        # We only consider it a real stall if the command is ALSO repeating
        # or if we've reached a much higher limit without ANY state change.
        if current_state_hash == self._last_state_hash:
            if command_hash in self._repeated_action_count and self._repeated_action_count[command_hash] > 1:
                self._stall_count += 1
            else:
                # If the command is NEW, we are still exploring, not necessarily stalled
                # But we still increment a "soft" stall counter
                self._stall_count += 0.5 
            
            if self._stall_count >= self.max_stall_count:
                return CompletionStatus.STALLED
        else:
            self._stall_count = 0
            self._last_state_hash = current_state_hash

        # Check goal completion - REMOVED subjective LLM thought checks
        # Completion is now exclusively handled by the Verification Phase
        if command.upper() == "DONE":
             return CompletionStatus.COMPLETED

        return CompletionStatus.IN_PROGRESS

    def _check_goal_achieved(
        self,
        snapshot: StateSnapshot,
        output: str,
        thought: str
    ) -> bool:
        """
        DEPRECATED: Subjective goal checking is disabled in engineering mode.
        Completion is determined by AcceptanceContract verification.
        """
        return False

    def _check_failure_patterns(self, output: str, exit_code: int) -> bool:
        """Check for patterns indicating unrecoverable failure."""
        output_lower = output.lower()

        failure_patterns = [
            'permission denied',
            'command not found',
            'no such file or directory',
            'fatal error',
            'segmentation fault',
        ]

        for pattern in failure_patterns:
            if pattern in output_lower and exit_code != 0:
                return True

        return False

    def get_status_message(self, status: CompletionStatus) -> str:
        """Get a human-readable message for the completion status."""
        messages = {
            CompletionStatus.IN_PROGRESS: "Task in progress...",
            CompletionStatus.COMPLETED: "Task completed successfully!",
            CompletionStatus.STALLED: "Task stalled - no progress detected. Manual intervention may be needed.",
            CompletionStatus.LOOP_DETECTED: "Loop detected - same action repeated without effect.",
            CompletionStatus.FAILED: "Task failed - unrecoverable error encountered.",
        }
        return messages.get(status, "Unknown status")

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about the completion gate state."""
        return {
            "total_actions": len(self._action_history),
            "unique_commands": len(self._repeated_action_count),
            "stall_count": self._stall_count,
            "state_changes": len(set(self._state_history)),
            "expected_files": self._expected_files,
            "files_found": [f for f in self._expected_files
                          if os.path.exists(os.path.join(self.workspace_root, f))],
        }

    def reset(self):
        """Reset the completion gate for a new task."""
        self._action_history.clear()
        self._state_history.clear()
        self._repeated_action_count.clear()
        self._stall_count = 0
        self._last_state_hash = ""
        self._goal_keywords.clear()
        self._expected_files.clear()
        self._expected_patterns.clear()
