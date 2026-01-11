"""
Debug Agent - The core Think -> Act -> Observe loop.
Connects Terminal (Phase 1) and Brain (Phase 2) with Memory (Phase 3).
"""
import json
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from .session import SessionManager, SessionStatus
from .models.manager import ModelManager
from .memory.history import HistoryMemory
from .analysis.observer import OutputObserver
from .analysis.classifier import ErrorClassifier
from .security import SafetyPolicy, SecurityViolationError


class AgentState(Enum):
    """Agent execution states."""
    IDLE = "IDLE"
    THINKING = "THINKING"
    ACTING = "ACTING"
    OBSERVING = "OBSERVING"
    WAITING = "WAITING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class StepResult:
    """Result of a single agent step."""
    step_number: int
    thought: str
    command: str
    output: str
    exit_code: int
    status: str
    error_category: Optional[str] = None
    was_duplicate: bool = False
    security_error: Optional[str] = None


class DebugAgent:
    """
    Debug Agent that executes commands, watches for errors,
    and uses history memory to avoid repeating failed fixes.
    """

    def __init__(
        self,
        session_manager: Optional[SessionManager] = None,
        model_manager: Optional[ModelManager] = None,
        memory: Optional[HistoryMemory] = None,
        observer: Optional[OutputObserver] = None,
        classifier: Optional[ErrorClassifier] = None,
        safety_policy: Optional[SafetyPolicy] = None,
        max_steps: int = 10,
        planner_model: str = "planner"
    ):
        """
        Initialize the Debug Agent.

        Args:
            session_manager: SessionManager for terminal execution
            model_manager: ModelManager for LLM access
            memory: HistoryMemory for tracking actions
            observer: OutputObserver for parsing logs
            classifier: ErrorClassifier for categorizing errors
            safety_policy: SafetyPolicy for security validation
            max_steps: Maximum steps before stopping
            planner_model: Name of the planner model to use
        """
        self.session_manager = session_manager or SessionManager()
        self.model_manager = model_manager
        self.memory = memory or HistoryMemory()
        self.observer = observer or OutputObserver()
        self.classifier = classifier or ErrorClassifier()
        self.safety_policy = safety_policy or SafetyPolicy()

        self.max_steps = max_steps
        self.planner_model = planner_model

        self.state = AgentState.IDLE
        self.current_step = 0
        self.session_id: Optional[str] = None
        self._planner = None

    def set_planner(self, planner):
        """
        Set a custom planner (for testing with mocks).

        Args:
            planner: Object with a generate(prompt) method
        """
        self._planner = planner

    def _get_planner(self):
        """Get the planner model."""
        if self._planner:
            return self._planner
        if self.model_manager:
            return self.model_manager.get_model(self.planner_model)
        raise RuntimeError("No planner available. Set model_manager or use set_planner()")

    def _build_prompt(self, task: str, current_output: str = "", is_initial: bool = False) -> str:
        """
        Build the prompt for the planner model.

        Args:
            task: The task description
            current_output: Current terminal output (if any)
            is_initial: If True, this is the initial planning step (no output yet)

        Returns:
            Formatted prompt string
        """
        history_context = self.memory.get_context_for_prompt()

        if is_initial:
            # Initial prompt: focus on understanding the goal and planning first step
            prompt = f"""You are a debug agent helping to accomplish tasks.

User Goal: {task}

This is the INITIAL step. You need to:
1. Understand what the user wants to achieve
2. Plan the first shell command to start working on this goal

{history_context}

Based on the user's goal, decide the first action to take.
If a command has failed before, DO NOT suggest it again.

Respond in JSON format:
{{
    "thought": "Your reasoning about what to do first",
    "command": "The shell command to execute",
    "reasoning": "Why this command will help achieve the goal"
}}

If the task is already complete or impossible, respond with:
{{
    "thought": "Explanation",
    "command": "DONE",
    "reasoning": "Why the task is complete or cannot be done"
}}
"""
        else:
            # Follow-up prompt: analyze output and decide next step
            prompt = f"""You are a debug agent helping to accomplish tasks.

User Goal: {task}

{history_context}

Current Output:
{current_output[:2000] if current_output else "No output yet."}

Based on the history and current state, decide the next action.
If a command has failed before, DO NOT suggest it again.

Respond in JSON format:
{{
    "thought": "Your reasoning about what to do next",
    "command": "The shell command to execute",
    "reasoning": "Why this command will help"
}}

If the task is complete, respond with:
{{
    "thought": "Task completed successfully",
    "command": "DONE",
    "reasoning": "Explanation of completion"
}}
"""
        return prompt

    def _parse_planner_response(self, response: str) -> Dict[str, Any]:
        """Parse the planner's JSON response."""
        try:
            # Try to extract JSON from the response
            response = response.strip()

            # Handle markdown code blocks
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                response = response[start:end].strip()
            elif "```" in response:
                start = response.find("```") + 3
                end = response.find("```", start)
                response = response[start:end].strip()

            return json.loads(response)
        except json.JSONDecodeError:
            # Fallback: try to extract command from response
            return {
                "thought": "Failed to parse response",
                "command": response[:100] if response else "echo 'Parse error'",
                "reasoning": "Fallback due to parse error"
            }

    def run_step(self, task: str, current_output: str = "", is_initial: bool = False) -> StepResult:
        """
        Execute a single Think -> Act -> Observe step.

        Args:
            task: The task description
            current_output: Current terminal output
            is_initial: If True, this is the initial planning step

        Returns:
            StepResult with the outcome of this step
        """
        self.current_step += 1

        # THINK: Get planner's suggestion
        self.state = AgentState.THINKING
        planner = self._get_planner()
        prompt = self._build_prompt(task, current_output, is_initial=is_initial)
        response = planner.generate(prompt)
        parsed = self._parse_planner_response(response)

        thought = parsed.get("thought", "")
        command = parsed.get("command", "")
        reasoning = parsed.get("reasoning", "")

        # Check for completion
        if command.upper() == "DONE":
            self.state = AgentState.COMPLETED
            return StepResult(
                step_number=self.current_step,
                thought=thought,
                command="DONE",
                output="",
                exit_code=0,
                status="COMPLETED"
            )

        # Check if this command has failed before
        was_duplicate = self.memory.has_failed_before(command)
        if was_duplicate:
            # Record the duplicate attempt but don't execute
            self.memory.add_entry(
                step=self.current_step,
                command=command,
                output="SKIPPED: Command has failed before",
                exit_code=-1,
                status="SKIPPED",
                reasoning=f"Duplicate of failed command: {reasoning}"
            )
            return StepResult(
                step_number=self.current_step,
                thought=thought,
                command=command,
                output="SKIPPED: Command has failed before",
                exit_code=-1,
                status="SKIPPED",
                was_duplicate=True
            )

        # SECURITY CHECK: Validate command before execution
        try:
            self.safety_policy.validate_command(command)
        except SecurityViolationError as e:
            # Record the security violation but don't execute
            security_msg = f"SECURITY BLOCKED: {str(e)}"
            self.memory.add_entry(
                step=self.current_step,
                command=command,
                output=security_msg,
                exit_code=-2,
                status="SECURITY_BLOCKED",
                reasoning=f"Security violation: {reasoning}"
            )
            return StepResult(
                step_number=self.current_step,
                thought=thought,
                command=command,
                output=security_msg,
                exit_code=-2,
                status="SECURITY_BLOCKED",
                security_error=str(e)
            )

        # ACT: Execute the command
        self.state = AgentState.ACTING
        self.session_id = self.session_manager.create_session(command=command)
        self.session_manager.start_session(self.session_id)

        # Wait for completion (with timeout)
        self.state = AgentState.WAITING
        timeout = 60  # seconds
        start_time = time.time()

        while time.time() - start_time < timeout:
            status = self.session_manager.get_status(self.session_id)
            if status in ("COMPLETED", "EXITED", "FAILED"):
                break
            time.sleep(0.5)

        # OBSERVE: Analyze the output
        self.state = AgentState.OBSERVING
        output = self.session_manager.get_logs(self.session_id)
        status = self.session_manager.get_status(self.session_id)

        # Determine exit code (simplified - real implementation would capture actual exit code)
        exit_code = 0 if status == "COMPLETED" else 1

        # Classify any errors
        error_category = None
        if exit_code != 0:
            error_category = self.classifier.classify(output)

        # Determine step status
        step_status = "SUCCESS" if exit_code == 0 else "FAILED"

        # Record in memory
        self.memory.add_entry(
            step=self.current_step,
            command=command,
            output=output,
            exit_code=exit_code,
            status=step_status,
            reasoning=reasoning
        )

        self.state = AgentState.IDLE

        return StepResult(
            step_number=self.current_step,
            thought=thought,
            command=command,
            output=output,
            exit_code=exit_code,
            status=step_status,
            error_category=error_category
        )

    def run(self, task: str = None, initial_goal: str = None) -> List[StepResult]:
        """
        Run the full debug loop until completion or max steps.

        The flow is: User Goal -> Planner -> Tool/Command -> Observer -> Loop

        Args:
            task: The task description (deprecated, use initial_goal)
            initial_goal: The natural language goal from the user

        Returns:
            List of StepResults from all steps
        """
        # Support both 'task' and 'initial_goal' for backward compatibility
        goal = initial_goal or task
        if not goal:
            raise ValueError("Either 'task' or 'initial_goal' must be provided")

        results = []
        current_output = ""
        is_first_step = True

        while self.current_step < self.max_steps:
            # First step uses is_initial=True to trigger goal-focused planning
            result = self.run_step(goal, current_output, is_initial=is_first_step)
            results.append(result)
            is_first_step = False

            if result.status == "COMPLETED":
                break

            # Update current output for next iteration
            if result.output:
                current_output = result.output

            # If we've had too many failures, stop
            consecutive_failures = sum(
                1 for r in results[-3:] if r.status in ("FAILED", "SKIPPED", "SECURITY_BLOCKED")
            )
            if consecutive_failures >= 3:
                self.state = AgentState.FAILED
                break

        return results

    def reset(self):
        """Reset the agent state for a new task."""
        self.state = AgentState.IDLE
        self.current_step = 0
        self.session_id = None
