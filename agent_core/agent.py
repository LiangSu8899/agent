"""
Debug Agent - The core Think -> Act -> Observe loop.
Connects Terminal (Phase 1) and Brain (Phase 2) with Memory (Phase 3).
"""
import json
import os
import re
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
from .events import EventEmitter, EventType, AgentEvent, TaskSummary, get_event_emitter
from .completion import CompletionGate, CompletionStatus
from .skills import get_skill_registry, SkillStatus


# GLM 专用 System Prompt - 强制 JSON 输出
GLM_SYSTEM_PROMPT = """You are a JSON-only response agent. You MUST follow these rules STRICTLY:

1. ONLY output valid JSON. No markdown, no explanations, no extra text.
2. Do NOT wrap JSON in ```json``` or any code blocks.
3. Do NOT add any text before or after the JSON.
4. The JSON must have exactly these fields: "thought", "command", "reasoning"
5. IMPORTANT: Keep "command" field SHORT and SIMPLE. Use single-line shell commands only.
   - For creating files, use: echo "content" > file.py (for short content)
   - Or use: touch file.py (then edit separately)
   - NEVER put multi-line scripts or heredocs in the command field

Example valid response:
{"thought": "I need to check the files", "command": "ls -la", "reasoning": "List files to understand the project structure"}

Example for creating a file:
{"thought": "Create a Python file", "command": "touch snake.py", "reasoning": "Create empty file first, then add content"}

Example for task completion:
{"thought": "Task is done", "command": "DONE", "reasoning": "All steps completed successfully"}

CRITICAL: Your entire response must be parseable by json.loads(). Any other format will cause errors."""


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
        planner_model: str = "planner",
        debug: bool = False,
        event_emitter: Optional[EventEmitter] = None,
        workspace_root: str = "."
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
            debug: Enable debug mode to print raw LLM outputs
            event_emitter: EventEmitter for progress reporting
            workspace_root: Root directory for file operations
        """
        self.session_manager = session_manager or SessionManager()
        self.model_manager = model_manager
        self.memory = memory or HistoryMemory()
        self.observer = observer or OutputObserver()
        self.classifier = classifier or ErrorClassifier()
        self.safety_policy = safety_policy or SafetyPolicy()

        self.max_steps = max_steps
        self.planner_model = planner_model
        self.debug = debug
        self.workspace_root = os.path.abspath(workspace_root)

        # Event emitter for progress reporting
        self.events = event_emitter or get_event_emitter()

        # Completion Gate for task completion detection
        self.completion_gate = CompletionGate(
            max_repeated_actions=3,
            max_stall_count=5,
            workspace_root=self.workspace_root
        )

        # Skill registry for reusable task templates
        self.skill_registry = get_skill_registry()

        self.state = AgentState.IDLE
        self.current_step = 0
        self.session_id: Optional[str] = None
        self._planner = None

        # Parse error tracking for circuit breaker
        self._consecutive_parse_errors = 0
        self._max_parse_errors = 3  # Circuit breaker threshold

        # Task tracking for summary
        self._task_start_time: Optional[float] = None
        self._files_created: List[str] = []
        self._files_modified: List[str] = []
        self._commands_executed: List[str] = []
        self._total_lines_written: int = 0

    def _try_skill_match(self, task: str) -> Optional[Dict[str, Any]]:
        """
        Try to match the task to a skill for direct execution.

        Args:
            task: The task description

        Returns:
            Dict with skill result if matched and executed, None otherwise
        """
        match = self.skill_registry.match_skill(task)
        if not match:
            return None

        skill, kwargs = match

        # Emit skill match event
        self.events.emit_simple(
            EventType.PLANNER_RESPONSE,
            f"Matched skill: {skill.name}",
            step=self.current_step,
            skill=skill.name,
            kwargs=kwargs
        )

        # Check preconditions
        precond = skill.check_preconditions(**kwargs)
        if not precond.passed:
            self.events.emit_simple(
                EventType.OBSERVER_RESULT,
                f"Skill precondition failed: {precond.message}",
                step=self.current_step,
                status="PRECONDITION_FAILED"
            )
            return None

        # Execute skill
        self.events.emit_simple(
            EventType.EXECUTOR_START,
            f"Executing skill: {skill.name}",
            step=self.current_step,
            skill=skill.name
        )

        result = skill.execute(**kwargs)

        # Track files
        self._files_created.extend(result.files_created)
        self._files_modified.extend(result.files_modified)
        if result.command:
            self._commands_executed.append(result.command)

        return {
            "skill": skill.name,
            "status": result.status,
            "command": result.command,
            "output": result.output,
            "error": result.error,
            "files_created": result.files_created,
            "duration": result.duration_seconds
        }

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

    def _is_glm_model(self) -> bool:
        """Check if the current planner is a GLM model."""
        model_name = self.planner_model.lower()
        return any(x in model_name for x in ['glm', 'zhipu', 'chatglm'])

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

        # Use GLM-specific prompt format for GLM models
        is_glm = self._is_glm_model()

        if is_glm:
            # GLM 专用 prompt - 更严格的 JSON 格式要求
            if is_initial:
                prompt = f"""{GLM_SYSTEM_PROMPT}

Task: {task}

{history_context}

This is the INITIAL step. Analyze the task and output the first action.
If a command has failed before, do NOT suggest it again.

Output ONLY valid JSON (no markdown, no explanation):"""
            else:
                prompt = f"""{GLM_SYSTEM_PROMPT}

Task: {task}

{history_context}

Current Output:
{current_output[:2000] if current_output else "No output yet."}

Analyze the output and decide the next action.
If task is complete, set command to "DONE".

Output ONLY valid JSON (no markdown, no explanation):"""
        else:
            # 原有的 prompt 格式（适用于其他模型）
            if is_initial:
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

    def _extract_json_from_text(self, text: str) -> Optional[str]:
        """
        Try to extract JSON from text that may contain extra content.

        Handles:
        - JSON wrapped in ```json``` code blocks
        - JSON wrapped in ``` code blocks
        - JSON with leading/trailing text
        - Multiple JSON objects (returns first valid one)
        """
        text = text.strip()

        # Method 1: Try direct parse first
        try:
            json.loads(text)
            return text
        except json.JSONDecodeError:
            pass

        # Method 2: Extract from ```json``` code block
        json_block_pattern = r'```json\s*([\s\S]*?)\s*```'
        matches = re.findall(json_block_pattern, text, re.IGNORECASE)
        for match in matches:
            try:
                json.loads(match.strip())
                return match.strip()
            except json.JSONDecodeError:
                continue

        # Method 3: Extract from ``` code block
        code_block_pattern = r'```\s*([\s\S]*?)\s*```'
        matches = re.findall(code_block_pattern, text)
        for match in matches:
            try:
                json.loads(match.strip())
                return match.strip()
            except json.JSONDecodeError:
                continue

        # Method 4: Find JSON object pattern { ... }
        # Use a more robust approach - find balanced braces
        brace_start = text.find('{')
        if brace_start != -1:
            depth = 0
            in_string = False
            escape_next = False

            for i, char in enumerate(text[brace_start:], brace_start):
                if escape_next:
                    escape_next = False
                    continue

                if char == '\\' and in_string:
                    escape_next = True
                    continue

                if char == '"' and not escape_next:
                    in_string = not in_string
                    continue

                if not in_string:
                    if char == '{':
                        depth += 1
                    elif char == '}':
                        depth -= 1
                        if depth == 0:
                            candidate = text[brace_start:i+1]
                            try:
                                json.loads(candidate)
                                return candidate
                            except json.JSONDecodeError:
                                # Try to find next JSON object
                                brace_start = text.find('{', i+1)
                                if brace_start == -1:
                                    break
                                depth = 0

        return None

    def _parse_planner_response(self, response: str) -> Dict[str, Any]:
        """
        Parse the planner's JSON response with enhanced robustness.

        Handles various LLM output formats including:
        - Pure JSON
        - JSON in markdown code blocks
        - JSON with surrounding text
        """
        original_response = response

        # Debug mode: print raw response
        if self.debug:
            print(f"\n[DEBUG] Raw LLM Response:\n{'-'*50}\n{response}\n{'-'*50}\n")

        try:
            # Try to extract JSON from the response
            json_str = self._extract_json_from_text(response)

            if json_str:
                parsed = json.loads(json_str)

                # Validate required fields
                if "command" in parsed:
                    # Reset parse error counter on success
                    self._consecutive_parse_errors = 0

                    # Ensure all expected fields exist
                    return {
                        "thought": parsed.get("thought", ""),
                        "command": parsed.get("command", ""),
                        "reasoning": parsed.get("reasoning", "")
                    }

            # If we get here, extraction failed
            raise json.JSONDecodeError("No valid JSON found", response, 0)

        except json.JSONDecodeError as e:
            # Increment parse error counter
            self._consecutive_parse_errors += 1

            # Log the parse error
            error_msg = f"JSON parse error (attempt {self._consecutive_parse_errors}/{self._max_parse_errors}): {str(e)}"
            if self.debug:
                print(f"[DEBUG] {error_msg}")
                print(f"[DEBUG] Response was: {original_response[:500]}...")

            # Check circuit breaker
            if self._consecutive_parse_errors >= self._max_parse_errors:
                # Circuit breaker triggered - return error action
                print(f"\n[ERROR] Parse error circuit breaker triggered after {self._max_parse_errors} consecutive failures!")
                print(f"[ERROR] Last raw response:\n{original_response[:1000]}")
                return {
                    "thought": f"PARSE_ERROR: Circuit breaker triggered after {self._max_parse_errors} consecutive parse failures",
                    "command": "DONE",
                    "reasoning": f"LLM output format incompatible. Last response: {original_response[:200]}..."
                }

            # Fallback: try to extract a command from the response
            # Look for common command patterns
            command_patterns = [
                r'(?:command|cmd|execute|run)["\s:]+([^\n"]+)',
                r'`([^`]+)`',  # Backtick wrapped commands
                r'^\s*(\w+\s+[^\n]+)$',  # Line that looks like a command
            ]

            for pattern in command_patterns:
                match = re.search(pattern, response, re.IGNORECASE | re.MULTILINE)
                if match:
                    extracted_cmd = match.group(1).strip()
                    # Basic validation - should look like a shell command
                    if extracted_cmd and len(extracted_cmd) < 200 and not extracted_cmd.startswith('{'):
                        return {
                            "thought": "Extracted command from non-JSON response",
                            "command": extracted_cmd,
                            "reasoning": f"Fallback extraction (parse error: {str(e)})"
                        }

            # Ultimate fallback
            return {
                "thought": "Failed to parse response",
                "command": "echo 'Parse error - please check LLM output format'",
                "reasoning": f"Fallback due to parse error: {str(e)}"
            }

    def _detect_file_operation(self, command: str) -> Optional[Dict[str, Any]]:
        """Detect if a command creates or modifies files."""
        # Patterns for file creation
        create_patterns = [
            r'touch\s+(\S+)',
            r'>\s*(\S+)',
            r'cat\s*>\s*(\S+)',
            r'echo\s+.*>\s*(\S+)',
            r'mkdir\s+(?:-p\s+)?(\S+)',
        ]

        # Patterns for file modification
        modify_patterns = [
            r'>>\s*(\S+)',
            r'sed\s+.*\s+(\S+)',
            r'echo\s+.*>>\s*(\S+)',
        ]

        for pattern in create_patterns:
            match = re.search(pattern, command)
            if match:
                return {"type": "create", "file": match.group(1)}

        for pattern in modify_patterns:
            match = re.search(pattern, command)
            if match:
                return {"type": "modify", "file": match.group(1)}

        return None

    def _count_lines_in_command(self, command: str) -> int:
        """Estimate lines of code being written in a command."""
        # Count newlines in echo commands
        if 'echo' in command and '>' in command:
            return command.count('\\n') + 1
        return 0

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

        # Emit step start event
        self.events.emit_simple(
            EventType.STEP_START,
            f"Starting step {self.current_step}",
            step=self.current_step
        )

        # THINK: Get planner's suggestion
        self.state = AgentState.THINKING
        self.events.emit_simple(
            EventType.PLANNER_START,
            "Analyzing task and planning next action...",
            step=self.current_step,
            model=self.planner_model
        )

        planner = self._get_planner()
        prompt = self._build_prompt(task, current_output, is_initial=is_initial)

        self.events.emit_simple(
            EventType.PLANNER_THINKING,
            "Waiting for planner response...",
            step=self.current_step
        )

        # Use generate_with_usage if available for token tracking
        input_tokens = 0
        output_tokens = 0
        if hasattr(planner, 'generate_with_usage'):
            result = planner.generate_with_usage(prompt)
            response = result.content
            input_tokens = result.input_tokens
            output_tokens = result.output_tokens
            model_name = result.model_name or self.planner_model

            # Emit token usage event
            self.events.emit_simple(
                EventType.TOKEN_USAGE,
                f"Tokens: {input_tokens} in / {output_tokens} out",
                step=self.current_step,
                model=model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens
            )
        else:
            response = planner.generate(prompt)

        parsed = self._parse_planner_response(response)

        thought = parsed.get("thought", "")
        command = parsed.get("command", "")
        reasoning = parsed.get("reasoning", "")

        # Emit planner response event
        self.events.emit_simple(
            EventType.PLANNER_RESPONSE,
            f"Planner decided: {command[:50]}..." if len(command) > 50 else f"Planner decided: {command}",
            step=self.current_step,
            thought=thought,
            command=command,
            reasoning=reasoning
        )

        # Check for completion
        if command.upper() == "DONE":
            self.state = AgentState.COMPLETED
            self.events.emit_simple(
                EventType.STEP_COMPLETE,
                "Task marked as complete by planner",
                step=self.current_step,
                status="COMPLETED"
            )
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
            self.events.emit_simple(
                EventType.STEP_COMPLETE,
                f"Skipped duplicate command: {command[:30]}...",
                step=self.current_step,
                status="SKIPPED"
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
            self.events.emit_simple(
                EventType.STEP_COMPLETE,
                f"Security blocked: {str(e)}",
                step=self.current_step,
                status="SECURITY_BLOCKED"
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

        # Detect file operations for tracking
        file_op = self._detect_file_operation(command)
        if file_op:
            if file_op["type"] == "create":
                self._files_created.append(file_op["file"])
                self.events.emit_simple(
                    EventType.FILE_CREATE,
                    f"Creating file: {file_op['file']}",
                    step=self.current_step,
                    file=file_op["file"]
                )
            elif file_op["type"] == "modify":
                self._files_modified.append(file_op["file"])
                self.events.emit_simple(
                    EventType.FILE_MODIFY,
                    f"Modifying file: {file_op['file']}",
                    step=self.current_step,
                    file=file_op["file"]
                )

        # Count lines being written
        lines = self._count_lines_in_command(command)
        if lines > 0:
            self._total_lines_written += lines

        # Track command
        self._commands_executed.append(command)

        # ACT: Execute the command
        self.state = AgentState.ACTING
        self.events.emit_simple(
            EventType.EXECUTOR_START,
            f"Executing: {command[:60]}..." if len(command) > 60 else f"Executing: {command}",
            step=self.current_step,
            command=command
        )

        self.session_id = self.session_manager.create_session(command=command)
        self.session_manager.start_session(self.session_id)

        # Wait for completion (with timeout)
        self.state = AgentState.WAITING
        timeout = 60  # seconds
        start_time = time.time()

        self.events.emit_simple(
            EventType.EXECUTOR_RUNNING,
            "Command running...",
            step=self.current_step
        )

        while time.time() - start_time < timeout:
            status = self.session_manager.get_status(self.session_id)
            if status in ("COMPLETED", "EXITED", "FAILED"):
                break
            time.sleep(0.5)

        # OBSERVE: Analyze the output
        self.state = AgentState.OBSERVING
        output = self.session_manager.get_logs(self.session_id)
        status = self.session_manager.get_status(self.session_id)

        self.events.emit_simple(
            EventType.EXECUTOR_COMPLETE,
            f"Command finished with status: {status}",
            step=self.current_step,
            status=status
        )

        # Determine exit code (simplified - real implementation would capture actual exit code)
        exit_code = 0 if status == "COMPLETED" else 1

        # Classify any errors
        error_category = None
        if exit_code != 0:
            error_category = self.classifier.classify(output)

        # Determine step status
        step_status = "SUCCESS" if exit_code == 0 else "FAILED"

        # Emit observer event
        self.events.emit_simple(
            EventType.OBSERVER_RESULT,
            f"Step {self.current_step} result: {step_status}",
            step=self.current_step,
            status=step_status,
            exit_code=exit_code,
            error_category=error_category
        )

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

        # Emit step complete event
        self.events.emit_simple(
            EventType.STEP_COMPLETE,
            f"Step {self.current_step} completed: {step_status}",
            step=self.current_step,
            status=step_status
        )

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

        # Reset tracking for new task
        self._task_start_time = time.time()
        self._files_created = []
        self._files_modified = []
        self._commands_executed = []
        self._total_lines_written = 0

        # Reset and configure completion gate
        self.completion_gate.reset()
        self.completion_gate.set_goal(goal)

        # Emit agent start event
        self.events.emit_simple(
            EventType.AGENT_START,
            f"Starting task: {goal}",
            goal=goal,
            max_steps=self.max_steps
        )

        results = []
        current_output = ""
        is_first_step = True
        error_message = None
        completion_status = CompletionStatus.IN_PROGRESS

        # ========== SKILL MATCHING - Try to match task to a skill first ==========
        skill_result = self._try_skill_match(goal)
        if skill_result:
            # Skill was matched and executed
            self.events.emit_simple(
                EventType.EXECUTOR_COMPLETE,
                f"Skill '{skill_result['skill']}' executed successfully",
                step=0,
                skill=skill_result['skill'],
                status=str(skill_result['status'])
            )

            # If skill has output, print it directly to terminal
            if skill_result.get('output'):
                # Print the full output to terminal
                print(skill_result.get('output', ''))

                # Also emit event for logging
                self.events.emit_simple(
                    EventType.OBSERVER_RESULT,
                    f"Skill output: {len(skill_result.get('output', ''))} chars",
                    step=0,
                    skill=skill_result['skill']
                )

            # Create a StepResult for the skill execution
            skill_step_result = StepResult(
                step_number=0,
                thought=f"Matched skill: {skill_result['skill']}",
                command=skill_result.get('command', ''),
                output=skill_result.get('output', ''),
                exit_code=0 if skill_result['status'] == SkillStatus.EXECUTED else 1,
                status="COMPLETED" if skill_result['status'] == SkillStatus.EXECUTED else "FAILED"
            )
            results.append(skill_step_result)

            # If skill executed successfully, emit completion
            if skill_result['status'] == SkillStatus.EXECUTED:
                self.events.emit_simple(
                    EventType.AGENT_COMPLETE,
                    f"Task completed via skill: {skill_result['skill']}",
                    status="COMPLETED",
                    reason="skill_execution"
                )
                return results

            # If skill failed, continue with normal flow
            current_output = skill_result.get('error', '')
        # ========== END SKILL MATCHING ==========

        try:
            while self.current_step < self.max_steps:
                # First step uses is_initial=True to trigger goal-focused planning
                result = self.run_step(goal, current_output, is_initial=is_first_step)
                results.append(result)
                is_first_step = False

                # Check explicit completion from planner
                if result.status == "COMPLETED":
                    completion_status = CompletionStatus.COMPLETED
                    break

                # Check completion gate
                completion_status = self.completion_gate.check_completion(
                    command=result.command,
                    output=result.output,
                    exit_code=result.exit_code,
                    thought=result.thought
                )

                if completion_status == CompletionStatus.COMPLETED:
                    self.events.emit_simple(
                        EventType.AGENT_COMPLETE,
                        "Task completed - goal achieved",
                        status="COMPLETED",
                        reason="completion_gate"
                    )
                    break

                if completion_status == CompletionStatus.LOOP_DETECTED:
                    error_message = "Loop detected - same action repeated without effect"
                    self.state = AgentState.FAILED
                    self.events.emit_simple(
                        EventType.AGENT_ERROR,
                        error_message,
                        error=error_message
                    )
                    break

                if completion_status == CompletionStatus.STALLED:
                    error_message = "Task stalled - no progress detected"
                    self.state = AgentState.FAILED
                    self.events.emit_simple(
                        EventType.AGENT_ERROR,
                        error_message,
                        error=error_message
                    )
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
                    error_message = "Too many consecutive failures"
                    break

        except Exception as e:
            error_message = str(e)
            self.events.emit_simple(
                EventType.AGENT_ERROR,
                f"Agent error: {error_message}",
                error=error_message
            )
            raise

        # Calculate duration
        duration = time.time() - self._task_start_time if self._task_start_time else 0

        # Determine final status
        if completion_status == CompletionStatus.COMPLETED:
            final_status = "COMPLETED"
        elif results and results[-1].status == "COMPLETED":
            final_status = "COMPLETED"
        else:
            final_status = "FAILED"

        if self.state == AgentState.FAILED:
            final_status = "FAILED"

        # Count successful and failed steps
        successful_steps = sum(1 for r in results if r.status == "SUCCESS")
        failed_steps = sum(1 for r in results if r.status in ("FAILED", "SKIPPED", "SECURITY_BLOCKED"))

        # Get completion gate statistics
        gate_stats = self.completion_gate.get_statistics()

        # Create task summary
        summary = TaskSummary(
            goal=goal,
            status=final_status,
            total_steps=len(results),
            successful_steps=successful_steps,
            failed_steps=failed_steps,
            files_created=list(set(self._files_created + gate_stats.get("files_found", []))),
            files_modified=list(set(self._files_modified)),
            commands_executed=self._commands_executed,
            total_lines_written=self._total_lines_written,
            duration_seconds=duration,
            error_message=error_message
        )

        # Emit task summary event
        self.events.emit_simple(
            EventType.TASK_SUMMARY,
            f"Task {final_status}: {goal[:50]}...",
            summary=summary.to_dict()
        )

        # Emit agent complete event
        self.events.emit_simple(
            EventType.AGENT_COMPLETE,
            f"Agent finished with status: {final_status}",
            status=final_status,
            total_steps=len(results),
            duration=duration
        )

        return results

    def reset(self):
        """Reset the agent state for a new task."""
        self.state = AgentState.IDLE
        self.current_step = 0
        self.session_id = None
        self._task_start_time = None
        self._files_created = []
        self._files_modified = []
        self._commands_executed = []
        self._total_lines_written = 0
        self._consecutive_parse_errors = 0
        self.completion_gate.reset()
