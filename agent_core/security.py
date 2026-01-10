"""
Safety Policy - Guardrails for agent actions.
Prevents dangerous commands and restricts file access to safe paths.
"""
import os
import re
from typing import Any, Dict, List, Optional, Set


class SecurityViolationError(Exception):
    """Raised when an action violates security policy."""

    def __init__(self, message: str, action_type: str = "unknown", details: Optional[Dict] = None):
        super().__init__(message)
        self.action_type = action_type
        self.details = details or {}


class SafetyPolicy:
    """
    Enforces security policies for agent actions.
    Validates commands and file paths before execution.
    """

    # Default dangerous command patterns (always blocked)
    DEFAULT_BLOCKED_COMMANDS = [
        r"rm\s+(-[rf]+\s+)*/?$",           # rm -rf /
        r"rm\s+(-[rf]+\s+)*/\s*$",         # rm -rf / (with trailing space)
        r"rm\s+(-[rf]+\s+)*/[^a-zA-Z]",    # rm -rf /something-dangerous
        r"mkfs",                            # Format filesystem
        r"dd\s+.*of=/dev/",                 # Direct disk write
        r":\(\)\{.*:\|:.*\};:",            # Fork bomb
        r">\s*/dev/sd[a-z]",               # Overwrite disk
        r"chmod\s+(-[rR]+\s+)*777\s+/",    # chmod 777 /
        r"chown\s+.*\s+/",                 # chown on root
        r"mv\s+.*\s+/dev/null",            # Move to /dev/null
        r"wget.*\|\s*sh",                  # Pipe wget to shell
        r"curl.*\|\s*sh",                  # Pipe curl to shell
        r"curl.*\|\s*bash",                # Pipe curl to bash
    ]

    # Default blocked system paths
    DEFAULT_BLOCKED_PATHS = [
        "/etc",
        "/usr",
        "/var",
        "/bin",
        "/sbin",
        "/boot",
        "/root",
        "/sys",
        "/proc",
        "/dev",
        ".git/objects",
        ".git/refs",
        ".git/HEAD",
        ".git/config",
        ".git/hooks",
    ]

    # Operations that modify files
    WRITE_OPERATIONS = {"write", "delete", "modify", "create", "append", "truncate"}

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the SafetyPolicy.

        Args:
            config: Configuration dictionary with security settings
        """
        self.config = config or {}
        security_config = self.config.get("security", {})

        # Load blocked commands (merge with defaults)
        custom_blocked = security_config.get("blocked_commands", [])
        self.blocked_command_patterns = self._compile_patterns(
            self.DEFAULT_BLOCKED_COMMANDS + custom_blocked
        )

        # Load blocked paths (merge with defaults)
        custom_paths = security_config.get("blocked_paths", [])
        self.blocked_paths = set(self.DEFAULT_BLOCKED_PATHS + custom_paths)

        # Allowed root directory (workspace sandbox)
        self.allowed_root = security_config.get("allowed_root")
        if self.allowed_root:
            self.allowed_root = os.path.abspath(self.allowed_root)

        # Additional settings
        self.strict_mode = security_config.get("strict_mode", False)
        self.allow_sudo = security_config.get("allow_sudo", False)

    def _compile_patterns(self, patterns: List[str]) -> List[re.Pattern]:
        """Compile regex patterns for command matching."""
        compiled = []
        for pattern in patterns:
            try:
                compiled.append(re.compile(pattern, re.IGNORECASE))
            except re.error:
                # If pattern is not valid regex, treat as literal string
                compiled.append(re.compile(re.escape(pattern), re.IGNORECASE))
        return compiled

    def validate_command(self, command: str) -> bool:
        """
        Validate a command before execution.

        Args:
            command: The command string to validate

        Returns:
            True if command is safe

        Raises:
            SecurityViolationError: If command is dangerous
        """
        if not command:
            return True

        # Normalize command
        cmd_normalized = command.strip()

        # Check for sudo if not allowed
        if not self.allow_sudo and cmd_normalized.startswith("sudo "):
            # Check if the sudo command itself is dangerous
            inner_cmd = cmd_normalized[5:].strip()
            self._check_command_patterns(inner_cmd)
            self._check_command_patterns(cmd_normalized)
        else:
            self._check_command_patterns(cmd_normalized)

        return True

    def _check_command_patterns(self, command: str):
        """Check command against blocked patterns."""
        for pattern in self.blocked_command_patterns:
            if pattern.search(command):
                raise SecurityViolationError(
                    f"Command blocked by security policy: {command}",
                    action_type="command",
                    details={"command": command, "pattern": pattern.pattern}
                )

    def validate_path(self, path: str, operation: str = "read") -> bool:
        """
        Validate a file path before access.

        Args:
            path: The file path to validate
            operation: The operation type (read, write, delete, etc.)

        Returns:
            True if path access is allowed

        Raises:
            SecurityViolationError: If path access is not allowed
        """
        if not path:
            return True

        # Normalize path
        abs_path = os.path.abspath(path)
        normalized_path = os.path.normpath(path)

        # Check for path traversal attempts
        if ".." in path:
            # Resolve and check if it escapes allowed root
            if self.allowed_root and not abs_path.startswith(self.allowed_root):
                raise SecurityViolationError(
                    f"Path traversal attempt blocked: {path}",
                    action_type="path",
                    details={"path": path, "resolved": abs_path}
                )

        # Check blocked paths (for write operations)
        is_write = operation.lower() in self.WRITE_OPERATIONS

        if is_write:
            # Check against blocked system paths
            for blocked in self.blocked_paths:
                if blocked.startswith("/"):
                    # Absolute path check
                    if abs_path.startswith(blocked) or abs_path == blocked:
                        raise SecurityViolationError(
                            f"Write access to system path blocked: {path}",
                            action_type="path",
                            details={"path": path, "blocked_path": blocked, "operation": operation}
                        )
                else:
                    # Relative path pattern (e.g., ".git")
                    if blocked in normalized_path or blocked in abs_path:
                        raise SecurityViolationError(
                            f"Write access to protected path blocked: {path}",
                            action_type="path",
                            details={"path": path, "blocked_pattern": blocked, "operation": operation}
                        )

        # Check workspace sandbox
        if self.allowed_root and is_write:
            if not abs_path.startswith(self.allowed_root):
                raise SecurityViolationError(
                    f"Path outside workspace sandbox: {path}",
                    action_type="path",
                    details={
                        "path": path,
                        "allowed_root": self.allowed_root,
                        "operation": operation
                    }
                )

        return True

    def validate_action(self, action_type: str, **kwargs) -> bool:
        """
        Generic action validation.

        Args:
            action_type: Type of action (command, file_read, file_write, etc.)
            **kwargs: Action-specific parameters

        Returns:
            True if action is allowed

        Raises:
            SecurityViolationError: If action is not allowed
        """
        if action_type == "command":
            return self.validate_command(kwargs.get("command", ""))
        elif action_type in ("file_read", "read"):
            return self.validate_path(kwargs.get("path", ""), operation="read")
        elif action_type in ("file_write", "write", "file_delete", "delete"):
            return self.validate_path(kwargs.get("path", ""), operation=action_type)
        else:
            # Unknown action type - allow in non-strict mode
            if self.strict_mode:
                raise SecurityViolationError(
                    f"Unknown action type in strict mode: {action_type}",
                    action_type=action_type
                )
            return True

    def get_blocked_commands_summary(self) -> List[str]:
        """Get a summary of blocked command patterns."""
        return [p.pattern for p in self.blocked_command_patterns]

    def get_blocked_paths_summary(self) -> List[str]:
        """Get a summary of blocked paths."""
        return list(self.blocked_paths)

    def is_path_in_sandbox(self, path: str) -> bool:
        """Check if a path is within the allowed sandbox."""
        if not self.allowed_root:
            return True
        abs_path = os.path.abspath(path)
        return abs_path.startswith(self.allowed_root)
