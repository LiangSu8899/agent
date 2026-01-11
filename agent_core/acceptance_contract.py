"""
Acceptance Contract System - Auto-generated from expected_state

This module provides:
1. Verifiers: FileExistsVerifier, DirectoryExistsVerifier, FileContainsVerifier, CommandExitVerifier
2. AcceptanceContract: Auto-generated from Plan.expected_state (1:1 mapping)
3. Verification: Pure fact-checking, returns PASS/FAIL + Evidence

Core Principles:
- Acceptance = Plan.expected_state 1:1 expansion
- LLM NEVER participates in Acceptance content generation
- Verification is fact-checking, not reasoning
- Evidence is objective data (path, exists, mtime, etc.)
"""
import os
import re
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from .task_decomposer import ExpectedState, PlanStep, TaskPlan


class VerificationStatus(Enum):
    """Verification result status - only PASS or FAIL, no partial."""
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass
class Evidence:
    """
    Evidence collected during verification.

    Evidence is objective fact, not interpretation.
    """
    type: str  # e.g., "file_exists", "directory_exists", "file_contains", "command_exit"
    path: Optional[str] = None
    exists: Optional[bool] = None
    mtime: Optional[str] = None  # ISO format timestamp
    patterns_matched: Optional[List[str]] = None
    patterns_missing: Optional[List[str]] = None
    exit_code: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {"type": self.type}
        if self.path is not None:
            result["path"] = self.path
        if self.exists is not None:
            result["exists"] = self.exists
        if self.mtime is not None:
            result["mtime"] = self.mtime
        if self.patterns_matched is not None:
            result["patterns_matched"] = self.patterns_matched
        if self.patterns_missing is not None:
            result["patterns_missing"] = self.patterns_missing
        if self.exit_code is not None:
            result["exit_code"] = self.exit_code
        if self.stdout is not None:
            result["stdout"] = self.stdout
        if self.stderr is not None:
            result["stderr"] = self.stderr
        if self.extra is not None:
            result["extra"] = self.extra
        return result


@dataclass
class VerificationResult:
    """
    Result of a single verification.

    Contains:
    - status: PASS or FAIL (no other values)
    - evidence: Objective facts collected
    """
    status: VerificationStatus
    evidence: Evidence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "evidence": self.evidence.to_dict()
        }


class Verifier(ABC):
    """Abstract base class for verifiers."""

    @abstractmethod
    def verify(self, workspace: str) -> VerificationResult:
        """
        Execute verification and return result with evidence.

        Args:
            workspace: Working directory for verification

        Returns:
            VerificationResult with PASS/FAIL and Evidence
        """
        pass


class FileExistsVerifier(Verifier):
    """
    Verify that a file exists.

    Maps from: expected_state.files
    """

    def __init__(self, path: str):
        self.path = path

    def verify(self, workspace: str) -> VerificationResult:
        full_path = os.path.join(workspace, self.path) if not os.path.isabs(self.path) else self.path

        if os.path.isfile(full_path):
            stat = os.stat(full_path)
            mtime = datetime.fromtimestamp(stat.st_mtime).isoformat()
            return VerificationResult(
                status=VerificationStatus.PASS,
                evidence=Evidence(
                    type="file_exists",
                    path=self.path,
                    exists=True,
                    mtime=mtime
                )
            )
        else:
            return VerificationResult(
                status=VerificationStatus.FAIL,
                evidence=Evidence(
                    type="file_exists",
                    path=self.path,
                    exists=False
                )
            )


class DirectoryExistsVerifier(Verifier):
    """
    Verify that a directory exists.

    Maps from: expected_state.directories
    """

    def __init__(self, path: str):
        self.path = path

    def verify(self, workspace: str) -> VerificationResult:
        full_path = os.path.join(workspace, self.path) if not os.path.isabs(self.path) else self.path

        if os.path.isdir(full_path):
            stat = os.stat(full_path)
            mtime = datetime.fromtimestamp(stat.st_mtime).isoformat()
            return VerificationResult(
                status=VerificationStatus.PASS,
                evidence=Evidence(
                    type="directory_exists",
                    path=self.path,
                    exists=True,
                    mtime=mtime
                )
            )
        else:
            return VerificationResult(
                status=VerificationStatus.FAIL,
                evidence=Evidence(
                    type="directory_exists",
                    path=self.path,
                    exists=False
                )
            )


class FileContainsVerifier(Verifier):
    """
    Verify that a file contains expected patterns.

    Maps from: expected_state.file_contains
    """

    def __init__(self, path: str, patterns: List[str]):
        self.path = path
        self.patterns = patterns

    def verify(self, workspace: str) -> VerificationResult:
        full_path = os.path.join(workspace, self.path) if not os.path.isabs(self.path) else self.path

        # First check file exists
        if not os.path.isfile(full_path):
            return VerificationResult(
                status=VerificationStatus.FAIL,
                evidence=Evidence(
                    type="file_contains",
                    path=self.path,
                    exists=False,
                    patterns_missing=self.patterns
                )
            )

        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()

            matched = []
            missing = []
            for pattern in self.patterns:
                if re.search(pattern, content):
                    matched.append(pattern)
                else:
                    missing.append(pattern)

            stat = os.stat(full_path)
            mtime = datetime.fromtimestamp(stat.st_mtime).isoformat()

            if missing:
                return VerificationResult(
                    status=VerificationStatus.FAIL,
                    evidence=Evidence(
                        type="file_contains",
                        path=self.path,
                        exists=True,
                        mtime=mtime,
                        patterns_matched=matched,
                        patterns_missing=missing
                    )
                )
            else:
                return VerificationResult(
                    status=VerificationStatus.PASS,
                    evidence=Evidence(
                        type="file_contains",
                        path=self.path,
                        exists=True,
                        mtime=mtime,
                        patterns_matched=matched,
                        patterns_missing=[]
                    )
                )

        except Exception as e:
            return VerificationResult(
                status=VerificationStatus.FAIL,
                evidence=Evidence(
                    type="file_contains",
                    path=self.path,
                    exists=True,
                    extra={"error": str(e)}
                )
            )


class CommandExitVerifier(Verifier):
    """
    Verify command exit code.

    Maps from: expected_state.command_exit_code
    """

    def __init__(self, expected_exit_code: int, cmd: str = "", cwd: str = ""):
        self.expected_exit_code = expected_exit_code
        self.cmd = cmd
        self.cwd = cwd
        self._actual_exit_code: Optional[int] = None
        self._stdout: str = ""
        self._stderr: str = ""

    def set_execution_result(self, exit_code: int, stdout: str = "", stderr: str = ""):
        """Set the actual execution result (called by executor after running command)."""
        self._actual_exit_code = exit_code
        self._stdout = stdout
        self._stderr = stderr

    def verify(self, workspace: str) -> VerificationResult:
        if self._actual_exit_code is None:
            return VerificationResult(
                status=VerificationStatus.FAIL,
                evidence=Evidence(
                    type="command_exit",
                    exit_code=None,
                    extra={"error": "Command not executed"}
                )
            )

        if self._actual_exit_code == self.expected_exit_code:
            return VerificationResult(
                status=VerificationStatus.PASS,
                evidence=Evidence(
                    type="command_exit",
                    exit_code=self._actual_exit_code,
                    stdout=self._stdout[:500] if self._stdout else None,
                    stderr=self._stderr[:500] if self._stderr else None
                )
            )
        else:
            return VerificationResult(
                status=VerificationStatus.FAIL,
                evidence=Evidence(
                    type="command_exit",
                    exit_code=self._actual_exit_code,
                    stdout=self._stdout[:500] if self._stdout else None,
                    stderr=self._stderr[:500] if self._stderr else None,
                    extra={"expected_exit_code": self.expected_exit_code}
                )
            )


@dataclass
class AcceptanceItem:
    """
    A single acceptance item auto-generated from expected_state.

    Each item has:
    - step_id: Reference to the plan step
    - verifier: The verifier instance
    - result: Verification result (after verification)
    """
    step_id: str
    verifier: Verifier
    description: str
    result: Optional[VerificationResult] = None

    def verify(self, workspace: str) -> VerificationResult:
        """Run verification and store result."""
        self.result = self.verifier.verify(workspace)
        return self.result

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "description": self.description,
            "result": self.result.to_dict() if self.result else None
        }


class AcceptanceContract:
    """
    Acceptance contract auto-generated from Plan.expected_state.

    This class:
    1. Takes a TaskPlan
    2. Expands each step's expected_state into AcceptanceItems
    3. Provides verify_all() to run all verifications

    NO LLM involvement in generation.
    """

    def __init__(self, plan: TaskPlan):
        """
        Initialize acceptance contract from plan.

        Auto-generates acceptance items from expected_state.
        """
        self.plan_id = plan.plan_id
        self.workspace = plan.workspace_root
        self.items: List[AcceptanceItem] = []

        # Auto-generate acceptance items from each step's expected_state
        for step in plan.steps:
            self._expand_expected_state(step)

    def _expand_expected_state(self, step: PlanStep):
        """
        Expand expected_state into acceptance items.

        Mapping rules:
        - files -> FileExistsVerifier
        - directories -> DirectoryExistsVerifier
        - file_contains -> FileContainsVerifier
        - command_exit_code -> CommandExitVerifier
        """
        es = step.expected_state

        # files -> FileExistsVerifier
        for file_path in es.files:
            self.items.append(AcceptanceItem(
                step_id=step.step_id,
                verifier=FileExistsVerifier(file_path),
                description=f"File exists: {file_path}"
            ))

        # directories -> DirectoryExistsVerifier
        for dir_path in es.directories:
            self.items.append(AcceptanceItem(
                step_id=step.step_id,
                verifier=DirectoryExistsVerifier(dir_path),
                description=f"Directory exists: {dir_path}"
            ))

        # file_contains -> FileContainsVerifier
        if es.file_contains:
            path = es.file_contains.get("path", "")
            patterns = es.file_contains.get("patterns", [])
            if path and patterns:
                self.items.append(AcceptanceItem(
                    step_id=step.step_id,
                    verifier=FileContainsVerifier(path, patterns),
                    description=f"File {path} contains patterns: {patterns}"
                ))

        # command_exit_code -> CommandExitVerifier
        if es.command_exit_code is not None:
            cmd = step.params.get("cmd", "")
            cwd = step.params.get("cwd", "")
            self.items.append(AcceptanceItem(
                step_id=step.step_id,
                verifier=CommandExitVerifier(es.command_exit_code, cmd, cwd),
                description=f"Command exit code: {es.command_exit_code}"
            ))

    def get_command_verifier(self, step_id: str) -> Optional[CommandExitVerifier]:
        """Get CommandExitVerifier for a step (to set execution result)."""
        for item in self.items:
            if item.step_id == step_id and isinstance(item.verifier, CommandExitVerifier):
                return item.verifier
        return None

    def verify_all(self) -> List[VerificationResult]:
        """
        Verify all acceptance items.

        Returns:
            List of VerificationResult (PASS/FAIL + Evidence)
        """
        results = []
        for item in self.items:
            result = item.verify(self.workspace)
            results.append(result)
        return results

    def get_results_table(self) -> List[Dict[str, Any]]:
        """
        Get verification results as a table.

        Format:
        [
            {"step_id": "...", "status": "PASS/FAIL", "description": "...", "evidence": {...}}
        ]
        """
        table = []
        for item in self.items:
            table.append({
                "step_id": item.step_id,
                "status": item.result.status.value if item.result else "PENDING",
                "description": item.description,
                "evidence": item.result.evidence.to_dict() if item.result else None
            })
        return table

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "workspace": self.workspace,
            "items": [item.to_dict() for item in self.items]
        }


def generate_acceptance_from_plan(plan: TaskPlan) -> AcceptanceContract:
    """
    Generate acceptance contract from plan.

    This is the ONLY way to create an AcceptanceContract.
    NO manual creation, NO LLM generation.

    Args:
        plan: Validated TaskPlan

    Returns:
        AcceptanceContract with auto-generated items
    """
    return AcceptanceContract(plan)
