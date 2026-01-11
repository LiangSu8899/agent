"""
Engineering Agent - OpenCode Style Executor with DSL-based workflow

This module provides:
1. ActionExecutor: Executes actions by step.action (whitelist only)
2. CompletionDecision: Pure logic binary decision (COMPLETED/FAILED)
3. DeliverySummary: Computed result rendering (no LLM conclusions)

CRITICAL WORKFLOW:
    Plan (JSON DSL) → Execution (by action) → Verification (fact-check) → Decision (binary) → Summary (computed)

Core Principles:
- Executor only looks at step.action, NOT Thought/Reasoning
- Verification is fact-checking from expected_state
- Completion Decision: ALL PASS = COMPLETED, ANY FAIL = FAILED
- No PARTIAL, no "roughly complete", no LLM judgment
"""
import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from .task_decomposer import (
    TaskDecomposer,
    TaskPlan,
    PlanStep,
    ActionType,
    StepStatus,
    DSLValidationError
)
from .acceptance_contract import (
    AcceptanceContract,
    VerificationResult,
    VerificationStatus,
    CommandExitVerifier,
    generate_acceptance_from_plan
)


class ExecutionStatus(Enum):
    """Execution status for a step."""
    PENDING = "pending"
    EXECUTING = "executing"
    EXECUTED = "executed"
    FAILED = "failed"


@dataclass
class ExecutionResult:
    """Result of executing a single step."""
    step_id: str
    action: str
    status: ExecutionStatus
    output: str = ""
    error: str = ""
    exit_code: Optional[int] = None
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "action": self.action,
            "status": self.status.value,
            "output": self.output[:1000] if self.output else "",
            "error": self.error,
            "exit_code": self.exit_code,
            "duration_seconds": self.duration_seconds
        }


class ActionExecutor:
    """
    Executes actions based on step.action (whitelist only).

    NO interpretation of Thought/Reasoning.
    Only executes what the action specifies.
    """

    def __init__(self, workspace_root: str = "."):
        self.workspace_root = os.path.abspath(workspace_root)

    def execute(self, step: PlanStep) -> ExecutionResult:
        """
        Execute a step based on its action type.

        Args:
            step: The PlanStep to execute

        Returns:
            ExecutionResult with status and output
        """
        start_time = time.time()
        step.status = StepStatus.IN_PROGRESS

        try:
            if step.action == ActionType.GIT_CLONE:
                result = self._execute_git_clone(step)
            elif step.action == ActionType.WRITE_FILE:
                result = self._execute_write_file(step)
            elif step.action == ActionType.APPEND_FILE:
                result = self._execute_append_file(step)
            elif step.action == ActionType.RUN_COMMAND:
                result = self._execute_run_command(step)
            elif step.action == ActionType.MKDIR:
                result = self._execute_mkdir(step)
            else:
                result = ExecutionResult(
                    step_id=step.step_id,
                    action=step.action.value,
                    status=ExecutionStatus.FAILED,
                    error=f"Unknown action: {step.action.value}"
                )
        except Exception as e:
            result = ExecutionResult(
                step_id=step.step_id,
                action=step.action.value,
                status=ExecutionStatus.FAILED,
                error=str(e)
            )

        result.duration_seconds = time.time() - start_time

        # Update step status
        if result.status == ExecutionStatus.EXECUTED:
            step.status = StepStatus.EXECUTED
            step.execution_output = result.output
        else:
            step.status = StepStatus.FAILED
            step.execution_error = result.error

        return result

    def _execute_git_clone(self, step: PlanStep) -> ExecutionResult:
        """Execute git clone action."""
        params = step.params
        repo_url = params.get("repo_url", "")
        target_dir = params.get("target_dir", "")

        if not repo_url:
            return ExecutionResult(
                step_id=step.step_id,
                action="git_clone",
                status=ExecutionStatus.FAILED,
                error="Missing repo_url"
            )

        full_target = os.path.join(self.workspace_root, target_dir) if target_dir else self.workspace_root

        try:
            cmd = ["git", "clone", repo_url]
            if target_dir:
                cmd.append(target_dir)

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=self.workspace_root
            )

            if result.returncode == 0:
                return ExecutionResult(
                    step_id=step.step_id,
                    action="git_clone",
                    status=ExecutionStatus.EXECUTED,
                    output=result.stdout,
                    exit_code=0
                )
            else:
                return ExecutionResult(
                    step_id=step.step_id,
                    action="git_clone",
                    status=ExecutionStatus.FAILED,
                    error=result.stderr,
                    exit_code=result.returncode
                )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                step_id=step.step_id,
                action="git_clone",
                status=ExecutionStatus.FAILED,
                error="Git clone timed out"
            )
        except Exception as e:
            return ExecutionResult(
                step_id=step.step_id,
                action="git_clone",
                status=ExecutionStatus.FAILED,
                error=str(e)
            )

    def _execute_write_file(self, step: PlanStep) -> ExecutionResult:
        """Execute write_file action."""
        params = step.params
        path = params.get("path", "")
        content = params.get("content", "")

        if not path:
            return ExecutionResult(
                step_id=step.step_id,
                action="write_file",
                status=ExecutionStatus.FAILED,
                error="Missing path"
            )

        full_path = os.path.join(self.workspace_root, path) if not os.path.isabs(path) else path

        try:
            # Ensure parent directory exists
            parent_dir = os.path.dirname(full_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)

            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)

            return ExecutionResult(
                step_id=step.step_id,
                action="write_file",
                status=ExecutionStatus.EXECUTED,
                output=f"Written {len(content)} bytes to {path}"
            )
        except Exception as e:
            return ExecutionResult(
                step_id=step.step_id,
                action="write_file",
                status=ExecutionStatus.FAILED,
                error=str(e)
            )

    def _execute_append_file(self, step: PlanStep) -> ExecutionResult:
        """Execute append_file action."""
        params = step.params
        path = params.get("path", "")
        content = params.get("content", "")

        if not path:
            return ExecutionResult(
                step_id=step.step_id,
                action="append_file",
                status=ExecutionStatus.FAILED,
                error="Missing path"
            )

        full_path = os.path.join(self.workspace_root, path) if not os.path.isabs(path) else path

        try:
            with open(full_path, 'a', encoding='utf-8') as f:
                f.write(content)

            return ExecutionResult(
                step_id=step.step_id,
                action="append_file",
                status=ExecutionStatus.EXECUTED,
                output=f"Appended {len(content)} bytes to {path}"
            )
        except Exception as e:
            return ExecutionResult(
                step_id=step.step_id,
                action="append_file",
                status=ExecutionStatus.FAILED,
                error=str(e)
            )

    def _execute_run_command(self, step: PlanStep) -> ExecutionResult:
        """Execute run_command action."""
        params = step.params
        cmd = params.get("cmd", "")
        cwd = params.get("cwd", "")

        if not cmd:
            return ExecutionResult(
                step_id=step.step_id,
                action="run_command",
                status=ExecutionStatus.FAILED,
                error="Missing cmd"
            )

        work_dir = os.path.join(self.workspace_root, cwd) if cwd else self.workspace_root

        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=work_dir
            )

            return ExecutionResult(
                step_id=step.step_id,
                action="run_command",
                status=ExecutionStatus.EXECUTED,
                output=result.stdout,
                error=result.stderr if result.returncode != 0 else "",
                exit_code=result.returncode
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                step_id=step.step_id,
                action="run_command",
                status=ExecutionStatus.FAILED,
                error="Command timed out"
            )
        except Exception as e:
            return ExecutionResult(
                step_id=step.step_id,
                action="run_command",
                status=ExecutionStatus.FAILED,
                error=str(e)
            )

    def _execute_mkdir(self, step: PlanStep) -> ExecutionResult:
        """Execute mkdir action."""
        params = step.params
        path = params.get("path", "")

        if not path:
            return ExecutionResult(
                step_id=step.step_id,
                action="mkdir",
                status=ExecutionStatus.FAILED,
                error="Missing path"
            )

        full_path = os.path.join(self.workspace_root, path) if not os.path.isabs(path) else path

        try:
            os.makedirs(full_path, exist_ok=True)
            return ExecutionResult(
                step_id=step.step_id,
                action="mkdir",
                status=ExecutionStatus.EXECUTED,
                output=f"Created directory: {path}"
            )
        except Exception as e:
            return ExecutionResult(
                step_id=step.step_id,
                action="mkdir",
                status=ExecutionStatus.FAILED,
                error=str(e)
            )


def decide_completion(verification_results: List[VerificationResult]) -> str:
    """
    Completion Decision - Pure logic, no LLM judgment.

    Rules:
    - No results = FAILED
    - Any FAIL = FAILED
    - All PASS = COMPLETED

    No PARTIAL, no "roughly complete".

    Args:
        verification_results: List of VerificationResult from acceptance contract

    Returns:
        "COMPLETED" or "FAILED"
    """
    if not verification_results:
        return "FAILED"

    if any(r.status == VerificationStatus.FAIL for r in verification_results):
        return "FAILED"

    return "COMPLETED"


@dataclass
class DeliverySummary:
    """
    Delivery Summary - Computed result rendering.

    NO LLM conclusions.
    Summary = Verification Results Table + Unmet Requirements + Root Cause + Final Conclusion
    """
    plan_id: str
    final_status: str  # COMPLETED or FAILED
    verification_table: List[Dict[str, Any]]
    unmet_requirements: List[str]
    root_causes: List[str]
    execution_results: List[ExecutionResult]
    total_duration_seconds: float

    def render(self) -> str:
        """Render the delivery summary as text."""
        lines = []
        lines.append("=" * 60)
        lines.append("DELIVERY SUMMARY")
        lines.append("=" * 60)
        lines.append(f"Plan ID: {self.plan_id}")
        lines.append(f"Duration: {self.total_duration_seconds:.2f}s")
        lines.append("")

        # Verification Results Table
        lines.append("Verification Results")
        lines.append("-" * 40)
        for item in self.verification_table:
            status = item.get("status", "PENDING")
            step_id = item.get("step_id", "")
            desc = item.get("description", "")
            lines.append(f"- {step_id} / {status}")
            if desc:
                lines.append(f"  {desc}")
        lines.append("")

        # Unmet Requirements
        if self.unmet_requirements:
            lines.append("Unmet Requirements")
            lines.append("-" * 40)
            for req in self.unmet_requirements:
                lines.append(f"- {req}")
            lines.append("")

        # Root Cause
        if self.root_causes:
            lines.append("Root Cause")
            lines.append("-" * 40)
            for cause in self.root_causes:
                lines.append(f"- {cause}")
            lines.append("")

        # Final Conclusion
        lines.append("Final Conclusion")
        lines.append("-" * 40)
        lines.append(self.final_status)
        lines.append("=" * 60)

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "final_status": self.final_status,
            "verification_table": self.verification_table,
            "unmet_requirements": self.unmet_requirements,
            "root_causes": self.root_causes,
            "execution_results": [r.to_dict() for r in self.execution_results],
            "total_duration_seconds": self.total_duration_seconds
        }


@dataclass
class EngineeringResult:
    """Complete result of an engineering task."""
    plan: TaskPlan
    execution_results: List[ExecutionResult]
    acceptance_contract: AcceptanceContract
    verification_results: List[VerificationResult]
    final_status: str  # COMPLETED or FAILED
    summary: DeliverySummary
    error_message: Optional[str] = None


class EngineeringAgent:
    """
    Engineering Agent with OpenCode-style DSL workflow.

    Workflow:
    1. Receive Plan (JSON DSL)
    2. Execute steps by action (no Thought/Reasoning)
    3. Verify against expected_state (fact-checking)
    4. Decide completion (binary: COMPLETED/FAILED)
    5. Generate summary (computed, no LLM)
    """

    def __init__(self, workspace_root: str = "."):
        self.workspace_root = os.path.abspath(workspace_root)
        self.decomposer = TaskDecomposer(workspace_root=self.workspace_root)
        self.executor = ActionExecutor(workspace_root=self.workspace_root)

    def run_from_json(self, plan_json: str) -> EngineeringResult:
        """
        Run engineering workflow from Planner JSON.

        Args:
            plan_json: Raw JSON string from Planner

        Returns:
            EngineeringResult with complete execution details
        """
        start_time = time.time()

        # 1. Parse and validate plan
        try:
            plan = self.decomposer.decompose_from_json(plan_json)
        except DSLValidationError as e:
            # Return failed result for invalid plan
            empty_plan = self.decomposer.create_empty_plan()
            return EngineeringResult(
                plan=empty_plan,
                execution_results=[],
                acceptance_contract=AcceptanceContract(empty_plan),
                verification_results=[],
                final_status="FAILED",
                summary=DeliverySummary(
                    plan_id="invalid",
                    final_status="FAILED",
                    verification_table=[],
                    unmet_requirements=[f"Plan validation failed: {e}"],
                    root_causes=[str(e)],
                    execution_results=[],
                    total_duration_seconds=time.time() - start_time
                ),
                error_message=str(e)
            )

        return self._run_plan(plan, start_time)

    def run_from_dict(self, plan_dict: Dict[str, Any]) -> EngineeringResult:
        """
        Run engineering workflow from plan dictionary.

        Args:
            plan_dict: Plan as dictionary

        Returns:
            EngineeringResult with complete execution details
        """
        start_time = time.time()

        try:
            plan = self.decomposer.decompose_from_dict(plan_dict)
        except DSLValidationError as e:
            empty_plan = self.decomposer.create_empty_plan()
            return EngineeringResult(
                plan=empty_plan,
                execution_results=[],
                acceptance_contract=AcceptanceContract(empty_plan),
                verification_results=[],
                final_status="FAILED",
                summary=DeliverySummary(
                    plan_id="invalid",
                    final_status="FAILED",
                    verification_table=[],
                    unmet_requirements=[f"Plan validation failed: {e}"],
                    root_causes=[str(e)],
                    execution_results=[],
                    total_duration_seconds=time.time() - start_time
                ),
                error_message=str(e)
            )

        return self._run_plan(plan, start_time)

    def _run_plan(self, plan: TaskPlan, start_time: float) -> EngineeringResult:
        """
        Execute a validated plan.

        Args:
            plan: Validated TaskPlan
            start_time: Workflow start time

        Returns:
            EngineeringResult
        """
        # 2. Generate acceptance contract from plan (auto-generated, no LLM)
        acceptance_contract = generate_acceptance_from_plan(plan)

        # 3. Execute all steps
        execution_results: List[ExecutionResult] = []
        for step in plan.steps:
            result = self.executor.execute(step)
            execution_results.append(result)

            # For run_command, update the CommandExitVerifier with actual result
            if step.action == ActionType.RUN_COMMAND and result.exit_code is not None:
                cmd_verifier = acceptance_contract.get_command_verifier(step.step_id)
                if cmd_verifier:
                    cmd_verifier.set_execution_result(
                        result.exit_code,
                        result.output,
                        result.error
                    )

        # 4. Run verification (fact-checking)
        verification_results = acceptance_contract.verify_all()

        # 5. Decide completion (binary)
        final_status = decide_completion(verification_results)

        # 6. Generate summary (computed)
        verification_table = acceptance_contract.get_results_table()

        unmet_requirements = []
        root_causes = []
        for item in verification_table:
            if item.get("status") == "FAIL":
                unmet_requirements.append(item.get("description", ""))
                evidence = item.get("evidence", {})
                if evidence:
                    if not evidence.get("exists", True):
                        root_causes.append(f"Expected {evidence.get('type', 'item')} not found: {evidence.get('path', '')}")
                    elif evidence.get("patterns_missing"):
                        root_causes.append(f"Missing patterns in {evidence.get('path', '')}: {evidence.get('patterns_missing', [])}")
                    elif evidence.get("exit_code") is not None:
                        expected = evidence.get("extra", {}).get("expected_exit_code", 0)
                        root_causes.append(f"Command exit code {evidence.get('exit_code')} != expected {expected}")

        summary = DeliverySummary(
            plan_id=plan.plan_id,
            final_status=final_status,
            verification_table=verification_table,
            unmet_requirements=unmet_requirements,
            root_causes=root_causes,
            execution_results=execution_results,
            total_duration_seconds=time.time() - start_time
        )

        return EngineeringResult(
            plan=plan,
            execution_results=execution_results,
            acceptance_contract=acceptance_contract,
            verification_results=verification_results,
            final_status=final_status,
            summary=summary
        )

    def run_with_summary(self, plan_json: str) -> EngineeringResult:
        """
        Run workflow and print delivery summary.

        Args:
            plan_json: Raw JSON string from Planner

        Returns:
            EngineeringResult
        """
        result = self.run_from_json(plan_json)
        print(result.summary.render())
        return result
