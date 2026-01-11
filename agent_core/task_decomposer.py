"""
Task Decomposition System - OpenCode Style Planner DSL

This module provides:
1. PlannerDSL: Strict JSON-only plan format with schema validation
2. TaskPlan: Container for validated plan with steps
3. No natural language allowed - pure JSON DSL

Core Principles:
- Planner only declares "what state I want", not "how to achieve it"
- Output must be pure JSON, no natural language
- Whitelist-only actions: git_clone, write_file, append_file, run_command, mkdir
- expected_state is the single source of truth for verification
"""
import os
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ActionType(Enum):
    """Whitelist of allowed actions - no other actions permitted."""
    GIT_CLONE = "git_clone"
    WRITE_FILE = "write_file"
    APPEND_FILE = "append_file"
    RUN_COMMAND = "run_command"
    MKDIR = "mkdir"


class StepStatus(Enum):
    """Status of a task step."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    EXECUTED = "executed"
    FAILED = "failed"


@dataclass
class ExpectedState:
    """
    Expected state after step execution.

    This is the ONLY source of truth for verification.
    Schema is fixed - no new fields allowed.
    """
    files: List[str] = field(default_factory=list)
    directories: List[str] = field(default_factory=list)
    file_contains: Optional[Dict[str, Any]] = None  # {"path": str, "patterns": [str]}
    command_exit_code: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {}
        if self.files:
            result["files"] = self.files
        if self.directories:
            result["directories"] = self.directories
        if self.file_contains:
            result["file_contains"] = self.file_contains
        if self.command_exit_code is not None:
            result["command_exit_code"] = self.command_exit_code
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExpectedState":
        """Create ExpectedState from dict, validating schema."""
        # Only allow known fields
        allowed_fields = {"files", "directories", "file_contains", "command_exit_code"}
        unknown_fields = set(data.keys()) - allowed_fields
        if unknown_fields:
            raise ValueError(f"Unknown fields in expected_state: {unknown_fields}")

        return cls(
            files=data.get("files", []),
            directories=data.get("directories", []),
            file_contains=data.get("file_contains"),
            command_exit_code=data.get("command_exit_code")
        )


@dataclass
class PlanStep:
    """
    A single step in the plan.

    Atomic definition:
    - step_id: unique identifier
    - action: whitelist enum
    - params: action parameters
    - expected_state: verification criteria
    """
    step_id: str
    action: ActionType
    params: Dict[str, Any]
    expected_state: ExpectedState
    status: StepStatus = StepStatus.PENDING
    execution_output: str = ""
    execution_error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "action": self.action.value,
            "params": self.params,
            "expected_state": self.expected_state.to_dict(),
            "status": self.status.value,
            "execution_output": self.execution_output,
            "execution_error": self.execution_error
        }


@dataclass
class TaskPlan:
    """
    A complete task plan with validated steps.

    Format:
    {
        "plan_id": "task-YYYYMMDD-HHMMSS",
        "workspace_root": ".",
        "steps": []
    }
    """
    plan_id: str
    workspace_root: str
    steps: List[PlanStep]
    original_goal: str = ""  # For reference only, not used in execution
    created_at: datetime = field(default_factory=datetime.now)
    current_step_index: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "workspace_root": self.workspace_root,
            "steps": [s.to_dict() for s in self.steps],
            "original_goal": self.original_goal,
            "created_at": self.created_at.isoformat(),
            "current_step_index": self.current_step_index
        }

    def get_current_step(self) -> Optional[PlanStep]:
        """Get the current step to execute."""
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    def advance(self) -> bool:
        """Advance to the next step. Returns False if no more steps."""
        self.current_step_index += 1
        return self.current_step_index < len(self.steps)

    def get_all_expected_states(self) -> List[ExpectedState]:
        """Get all expected states for verification."""
        return [step.expected_state for step in self.steps]


class DSLValidationError(Exception):
    """Raised when DSL validation fails."""
    pass


class PlannerDSL:
    """
    Strict DSL parser and validator for Planner output.

    Rules:
    - Only accepts JSON, no natural language
    - Validates against fixed schema
    - Whitelist-only actions
    - expected_state must use fixed schema
    """

    # Action whitelist
    ALLOWED_ACTIONS = {a.value for a in ActionType}

    # Required params for each action
    ACTION_PARAMS = {
        "git_clone": {"repo_url", "target_dir"},
        "write_file": {"path", "content"},
        "append_file": {"path", "content"},
        "run_command": {"cmd"},  # cwd is optional
        "mkdir": {"path"},
    }

    @classmethod
    def _fix_json_newlines(cls, raw_json: str) -> str:
        """
        Fix JSON strings that contain unescaped newlines.

        LLMs often output content fields with real newlines instead of \\n.
        This function escapes newlines within JSON string values.
        """
        result = []
        in_string = False
        escape_next = False
        i = 0

        while i < len(raw_json):
            char = raw_json[i]

            if escape_next:
                result.append(char)
                escape_next = False
                i += 1
                continue

            if char == '\\':
                result.append(char)
                escape_next = True
                i += 1
                continue

            if char == '"' and not escape_next:
                in_string = not in_string
                result.append(char)
                i += 1
                continue

            if in_string and char == '\n':
                result.append('\\n')
                i += 1
                continue

            if in_string and char == '\r':
                i += 1
                continue

            if in_string and char == '\t':
                result.append('\\t')
                i += 1
                continue

            result.append(char)
            i += 1

        return ''.join(result)

    @classmethod
    def _extract_json(cls, raw_response: str) -> str:
        """
        Extract JSON object from LLM response.

        Handles markdown code blocks and extra text.
        """
        json_str = raw_response.strip()

        # Remove markdown code blocks
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            parts = json_str.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("{"):
                    json_str = part
                    break

        # Find JSON object boundaries
        if not json_str.startswith("{"):
            start_idx = json_str.find("{")
            if start_idx != -1:
                brace_count = 0
                end_idx = start_idx
                for i, c in enumerate(json_str[start_idx:], start_idx):
                    if c == "{":
                        brace_count += 1
                    elif c == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            end_idx = i + 1
                            break
                json_str = json_str[start_idx:end_idx]

        return json_str

    @classmethod
    def validate_and_parse(cls, json_str: str, workspace_root: str = ".") -> TaskPlan:
        """
        Validate and parse Planner JSON output.

        Args:
            json_str: Raw JSON string from Planner
            workspace_root: Default workspace root

        Returns:
            Validated TaskPlan

        Raises:
            DSLValidationError: If validation fails
        """
        # Extract and fix JSON
        json_str = cls._extract_json(json_str)
        json_str = cls._fix_json_newlines(json_str)

        # Parse JSON
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise DSLValidationError(f"Invalid JSON: {e}")

        # Validate top-level structure
        if not isinstance(data, dict):
            raise DSLValidationError("Plan must be a JSON object")

        required_fields = {"plan_id", "steps"}
        missing = required_fields - set(data.keys())
        if missing:
            raise DSLValidationError(f"Missing required fields: {missing}")

        plan_id = data["plan_id"]
        ws_root = data.get("workspace_root", workspace_root)
        steps_data = data["steps"]

        if not isinstance(steps_data, list):
            raise DSLValidationError("steps must be an array")

        # Validate and parse each step
        steps = []
        seen_step_ids = set()

        for i, step_data in enumerate(steps_data):
            step = cls._validate_step(step_data, i, seen_step_ids)
            steps.append(step)

        return TaskPlan(
            plan_id=plan_id,
            workspace_root=ws_root,
            steps=steps,
            original_goal=data.get("original_goal", "")
        )

    @classmethod
    def _validate_step(cls, step_data: Dict[str, Any], index: int, seen_ids: set) -> PlanStep:
        """Validate a single step."""
        if not isinstance(step_data, dict):
            raise DSLValidationError(f"Step {index} must be a JSON object")

        # Required fields
        required = {"step_id", "action", "params", "expected_state"}
        missing = required - set(step_data.keys())
        if missing:
            raise DSLValidationError(f"Step {index} missing fields: {missing}")

        step_id = step_data["step_id"]
        action_str = step_data["action"]
        params = step_data["params"]
        expected_state_data = step_data["expected_state"]

        # Validate step_id uniqueness
        if step_id in seen_ids:
            raise DSLValidationError(f"Duplicate step_id: {step_id}")
        seen_ids.add(step_id)

        # Validate action is in whitelist
        if action_str not in cls.ALLOWED_ACTIONS:
            raise DSLValidationError(
                f"Step {step_id}: Invalid action '{action_str}'. "
                f"Allowed: {cls.ALLOWED_ACTIONS}"
            )

        action = ActionType(action_str)

        # Validate params for action
        if not isinstance(params, dict):
            raise DSLValidationError(f"Step {step_id}: params must be a dict")

        required_params = cls.ACTION_PARAMS.get(action_str, set())
        missing_params = required_params - set(params.keys())
        if missing_params:
            raise DSLValidationError(
                f"Step {step_id}: Missing required params for {action_str}: {missing_params}"
            )

        # Validate write_file content is complete (not placeholder)
        if action_str == "write_file":
            content = params.get("content", "")
            if not content or content == "<FULL_FILE_CONTENT>" or "to be filled" in content.lower():
                raise DSLValidationError(
                    f"Step {step_id}: write_file content must be complete, not placeholder"
                )

        # Validate expected_state
        if not isinstance(expected_state_data, dict):
            raise DSLValidationError(f"Step {step_id}: expected_state must be a dict")

        try:
            expected_state = ExpectedState.from_dict(expected_state_data)
        except ValueError as e:
            raise DSLValidationError(f"Step {step_id}: {e}")

        return PlanStep(
            step_id=step_id,
            action=action,
            params=params,
            expected_state=expected_state
        )

    @classmethod
    def create_plan_from_dict(cls, data: Dict[str, Any], workspace_root: str = ".") -> TaskPlan:
        """Create plan from already-parsed dict (for internal use)."""
        return cls.validate_and_parse(json.dumps(data), workspace_root)


class TaskDecomposer:
    """
    Task decomposer that only accepts Planner JSON DSL.

    This is a thin wrapper that:
    1. Receives JSON from Planner
    2. Validates against DSL schema
    3. Returns TaskPlan

    NO natural language processing.
    NO LLM reasoning interpretation.
    """

    def __init__(self, workspace_root: str = "."):
        self.workspace_root = os.path.abspath(workspace_root)
        self._task_counter = 0

    def _generate_plan_id(self) -> str:
        """Generate a unique plan ID."""
        self._task_counter += 1
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"task-{timestamp}"

    def decompose_from_json(self, json_str: str) -> TaskPlan:
        """
        Decompose task from Planner JSON output.

        This is the ONLY entry point for task decomposition.

        Args:
            json_str: Raw JSON string from Planner

        Returns:
            Validated TaskPlan

        Raises:
            DSLValidationError: If validation fails
        """
        return PlannerDSL.validate_and_parse(json_str, self.workspace_root)

    def decompose_from_dict(self, plan_dict: Dict[str, Any]) -> TaskPlan:
        """
        Decompose task from already-parsed dict.

        Args:
            plan_dict: Plan dictionary

        Returns:
            Validated TaskPlan
        """
        return PlannerDSL.create_plan_from_dict(plan_dict, self.workspace_root)

    def create_empty_plan(self, goal: str = "") -> TaskPlan:
        """Create an empty plan (for testing or manual construction)."""
        return TaskPlan(
            plan_id=self._generate_plan_id(),
            workspace_root=self.workspace_root,
            steps=[],
            original_goal=goal
        )

    def add_step_to_plan(
        self,
        plan: TaskPlan,
        step_id: str,
        action: str,
        params: Dict[str, Any],
        expected_state: Dict[str, Any]
    ) -> PlanStep:
        """
        Add a validated step to an existing plan.

        Args:
            plan: The plan to add to
            step_id: Unique step identifier
            action: Action type (must be in whitelist)
            params: Action parameters
            expected_state: Expected state dict

        Returns:
            The added PlanStep
        """
        step_data = {
            "step_id": step_id,
            "action": action,
            "params": params,
            "expected_state": expected_state
        }

        seen_ids = {s.step_id for s in plan.steps}
        step = PlannerDSL._validate_step(step_data, len(plan.steps), seen_ids)
        plan.steps.append(step)
        return step


# =============================================================================
# Planner Prompt Template
# =============================================================================

PLANNER_PROMPT_TEMPLATE = """You are a Planner that outputs ONLY valid JSON. No markdown, no explanation.

CRITICAL JSON RULES:
1. Output ONLY the JSON object, nothing else
2. All strings must use \\n for newlines (NOT actual line breaks inside strings)
3. Use \\" for quotes inside strings
4. content field must be a single-line string with \\n for line breaks

DSL Schema:
{{
  "plan_id": "task-YYYYMMDD-HHMMSS",
  "workspace_root": ".",
  "steps": [
    {{
      "step_id": "unique_string",
      "action": "git_clone | write_file | append_file | run_command | mkdir",
      "params": {{ ... }},
      "expected_state": {{
        "files": [],
        "directories": [],
        "file_contains": {{ "path": "...", "patterns": ["..."] }},
        "command_exit_code": 0
      }}
    }}
  ]
}}

Action Params:
- git_clone: {{ "repo_url": "...", "target_dir": "..." }}
- write_file: {{ "path": "...", "content": "line1\\nline2\\nline3" }}
- append_file: {{ "path": "...", "content": "..." }}
- run_command: {{ "cmd": "...", "cwd": "..." }}
- mkdir: {{ "path": "..." }}

EXAMPLE write_file (CORRECT):
{{
  "step_id": "write_script",
  "action": "write_file",
  "params": {{
    "path": "hello.py",
    "content": "#!/usr/bin/env python3\\nimport http.server\\n\\nif __name__ == \\"__main__\\":\\n    print(\\"Hello\\")"
  }},
  "expected_state": {{
    "files": ["hello.py"]
  }}
}}

Task:
{user_task}

Output JSON:
"""


def generate_planner_prompt(user_task: str) -> str:
    """
    Generate the Planner prompt for a given user task.

    Args:
        user_task: The user's task description

    Returns:
        Complete prompt string for the Planner LLM
    """
    return PLANNER_PROMPT_TEMPLATE.format(user_task=user_task)


# Legacy compatibility - map old names to new ones
StepType = ActionType  # Alias for backward compatibility
