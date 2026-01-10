"""
Error Classifier for categorizing errors from terminal output.
Uses regex-based pattern matching with optional LLM fallback.
"""
import re
from enum import Enum
from typing import Optional, List, Tuple


class ErrorCategory(Enum):
    """Standard error categories."""
    PACKAGE_ERROR = "PackageError"
    SYNTAX_ERROR = "SyntaxError"
    IMPORT_ERROR = "ImportError"
    TYPE_ERROR = "TypeError"
    RUNTIME_ERROR = "RuntimeError"
    PERMISSION_ERROR = "PermissionError"
    FILE_NOT_FOUND = "FileNotFound"
    NETWORK_ERROR = "NetworkError"
    TIMEOUT_ERROR = "TimeoutError"
    BUILD_ERROR = "BuildError"
    DEPENDENCY_ERROR = "DependencyError"
    CONFIGURATION_ERROR = "ConfigurationError"
    MEMORY_ERROR = "MemoryError"
    UNKNOWN = "Unknown"


class ErrorClassifier:
    """
    Classifies errors from terminal output into categories.
    Uses regex-based pattern matching for speed and reliability.
    """

    # Pattern -> Category mapping (order matters - first match wins)
    PATTERNS: List[Tuple[str, ErrorCategory]] = [
        # Package/Dependency errors
        (r'Unable to locate package', ErrorCategory.PACKAGE_ERROR),
        (r'E: Unable to locate', ErrorCategory.PACKAGE_ERROR),
        (r'No package .* available', ErrorCategory.PACKAGE_ERROR),
        (r'Package .* is not available', ErrorCategory.PACKAGE_ERROR),
        (r'Could not find a version', ErrorCategory.PACKAGE_ERROR),
        (r'No matching distribution', ErrorCategory.PACKAGE_ERROR),
        (r'ModuleNotFoundError', ErrorCategory.IMPORT_ERROR),
        (r'ImportError', ErrorCategory.IMPORT_ERROR),
        (r'cannot import name', ErrorCategory.IMPORT_ERROR),
        (r'No module named', ErrorCategory.IMPORT_ERROR),
        (r'dependency .* not found', ErrorCategory.DEPENDENCY_ERROR),
        (r'missing dependency', ErrorCategory.DEPENDENCY_ERROR),
        (r'unmet dependencies', ErrorCategory.DEPENDENCY_ERROR),
        (r'peer dep missing', ErrorCategory.DEPENDENCY_ERROR),

        # Syntax errors
        (r'SyntaxError', ErrorCategory.SYNTAX_ERROR),
        (r'IndentationError', ErrorCategory.SYNTAX_ERROR),
        (r'TabError', ErrorCategory.SYNTAX_ERROR),
        (r'unexpected token', ErrorCategory.SYNTAX_ERROR),
        (r'parsing error', ErrorCategory.SYNTAX_ERROR),
        (r'invalid syntax', ErrorCategory.SYNTAX_ERROR),

        # Type errors
        (r'TypeError', ErrorCategory.TYPE_ERROR),
        (r'type mismatch', ErrorCategory.TYPE_ERROR),
        (r'cannot convert', ErrorCategory.TYPE_ERROR),

        # File system errors
        (r'No such file or directory', ErrorCategory.FILE_NOT_FOUND),
        (r'FileNotFoundError', ErrorCategory.FILE_NOT_FOUND),
        (r'ENOENT', ErrorCategory.FILE_NOT_FOUND),
        (r'file not found', ErrorCategory.FILE_NOT_FOUND),
        (r'Permission denied', ErrorCategory.PERMISSION_ERROR),
        (r'PermissionError', ErrorCategory.PERMISSION_ERROR),
        (r'EACCES', ErrorCategory.PERMISSION_ERROR),
        (r'access denied', ErrorCategory.PERMISSION_ERROR),

        # Network errors
        (r'ConnectionError', ErrorCategory.NETWORK_ERROR),
        (r'ConnectionRefusedError', ErrorCategory.NETWORK_ERROR),
        (r'ECONNREFUSED', ErrorCategory.NETWORK_ERROR),
        (r'network unreachable', ErrorCategory.NETWORK_ERROR),
        (r'Could not resolve host', ErrorCategory.NETWORK_ERROR),
        (r'Name or service not known', ErrorCategory.NETWORK_ERROR),
        (r'Connection timed out', ErrorCategory.NETWORK_ERROR),
        (r'SSL.*error', ErrorCategory.NETWORK_ERROR),

        # Timeout errors
        (r'TimeoutError', ErrorCategory.TIMEOUT_ERROR),
        (r'timed out', ErrorCategory.TIMEOUT_ERROR),
        (r'timeout expired', ErrorCategory.TIMEOUT_ERROR),
        (r'deadline exceeded', ErrorCategory.TIMEOUT_ERROR),

        # Memory errors
        (r'MemoryError', ErrorCategory.MEMORY_ERROR),
        (r'OutOfMemoryError', ErrorCategory.MEMORY_ERROR),
        (r'out of memory', ErrorCategory.MEMORY_ERROR),
        (r'OOM', ErrorCategory.MEMORY_ERROR),
        (r'Cannot allocate memory', ErrorCategory.MEMORY_ERROR),

        # Build errors (Docker, make, etc.)
        (r'returned a non-zero code', ErrorCategory.BUILD_ERROR),
        (r'build failed', ErrorCategory.BUILD_ERROR),
        (r'compilation failed', ErrorCategory.BUILD_ERROR),
        (r'make.*Error', ErrorCategory.BUILD_ERROR),
        (r'cmake.*error', ErrorCategory.BUILD_ERROR),
        (r'npm ERR!', ErrorCategory.BUILD_ERROR),
        (r'yarn error', ErrorCategory.BUILD_ERROR),

        # Configuration errors
        (r'ConfigurationError', ErrorCategory.CONFIGURATION_ERROR),
        (r'invalid configuration', ErrorCategory.CONFIGURATION_ERROR),
        (r'config.*not found', ErrorCategory.CONFIGURATION_ERROR),
        (r'missing.*config', ErrorCategory.CONFIGURATION_ERROR),

        # Generic runtime errors
        (r'RuntimeError', ErrorCategory.RUNTIME_ERROR),
        (r'Exception', ErrorCategory.RUNTIME_ERROR),
        (r'Error:', ErrorCategory.RUNTIME_ERROR),
    ]

    def __init__(self, llm_client=None):
        """
        Initialize the classifier.

        Args:
            llm_client: Optional LLM client for fallback classification
        """
        self.llm_client = llm_client
        self._compiled_patterns = [
            (re.compile(pattern, re.IGNORECASE), category)
            for pattern, category in self.PATTERNS
        ]

    def classify(self, error_log: str) -> str:
        """
        Classify an error log into a category.

        Args:
            error_log: The error output to classify

        Returns:
            Category name as string (e.g., "PackageError", "SyntaxError")
        """
        category = self._regex_classify(error_log)

        # If unknown and LLM is available, try LLM classification
        if category == ErrorCategory.UNKNOWN and self.llm_client:
            category = self._llm_classify(error_log)

        return category.value

    def _regex_classify(self, error_log: str) -> ErrorCategory:
        """Classify using regex patterns."""
        for pattern, category in self._compiled_patterns:
            if pattern.search(error_log):
                return category
        return ErrorCategory.UNKNOWN

    def _llm_classify(self, error_log: str) -> ErrorCategory:
        """Classify using LLM (fallback)."""
        if not self.llm_client:
            return ErrorCategory.UNKNOWN

        prompt = f"""Classify the following error into one of these categories:
- PackageError: Missing packages or installation issues
- SyntaxError: Code syntax problems
- ImportError: Module import failures
- TypeError: Type-related errors
- RuntimeError: General runtime errors
- PermissionError: Permission/access issues
- FileNotFound: Missing files
- NetworkError: Network/connection issues
- TimeoutError: Timeout problems
- BuildError: Build/compilation failures
- DependencyError: Dependency conflicts
- ConfigurationError: Config issues
- MemoryError: Memory problems
- Unknown: Cannot determine

Error log:
{error_log[:1000]}

Respond with ONLY the category name (e.g., "PackageError"):"""

        try:
            response = self.llm_client.generate(prompt, max_tokens=20, temperature=0)
            response = response.strip()

            # Try to match response to a category
            for cat in ErrorCategory:
                if cat.value.lower() in response.lower():
                    return cat
        except Exception:
            pass

        return ErrorCategory.UNKNOWN

    def get_category_description(self, category: str) -> str:
        """Get a human-readable description of a category."""
        descriptions = {
            "PackageError": "Missing or unavailable package/library",
            "SyntaxError": "Code syntax error",
            "ImportError": "Failed to import a module",
            "TypeError": "Type mismatch or invalid type operation",
            "RuntimeError": "General runtime error",
            "PermissionError": "Insufficient permissions",
            "FileNotFound": "File or directory not found",
            "NetworkError": "Network or connection issue",
            "TimeoutError": "Operation timed out",
            "BuildError": "Build or compilation failure",
            "DependencyError": "Dependency conflict or missing dependency",
            "ConfigurationError": "Configuration error",
            "MemoryError": "Out of memory",
            "Unknown": "Unknown error type",
        }
        return descriptions.get(category, "Unknown error type")

    def suggest_fix(self, category: str, error_log: str) -> Optional[str]:
        """
        Suggest a potential fix based on the error category.

        Args:
            category: The error category
            error_log: The original error log

        Returns:
            Suggested fix or None
        """
        suggestions = {
            "PackageError": "Try installing the missing package with apt-get, pip, or npm",
            "SyntaxError": "Check the code for syntax errors at the indicated line",
            "ImportError": "Install the missing module or check the import path",
            "TypeError": "Check variable types and function arguments",
            "PermissionError": "Check file permissions or run with elevated privileges",
            "FileNotFound": "Verify the file path exists and is correct",
            "NetworkError": "Check network connectivity and firewall settings",
            "TimeoutError": "Increase timeout or check for blocking operations",
            "BuildError": "Review build logs and check dependencies",
            "DependencyError": "Resolve dependency conflicts or update packages",
            "ConfigurationError": "Check configuration files and environment variables",
            "MemoryError": "Reduce memory usage or increase available memory",
        }
        return suggestions.get(category)
