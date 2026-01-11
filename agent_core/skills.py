"""
Skill System - Reusable task templates with pre-execution validation.

Skills are pre-defined task patterns that the Planner can invoke
instead of generating custom commands from scratch.
"""
import os
import re
import subprocess
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class SkillStatus(Enum):
    """Status of skill execution."""
    READY = "ready"
    PRECONDITION_FAILED = "precondition_failed"
    EXECUTED = "executed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class SkillResult:
    """Result of a skill execution."""
    status: SkillStatus
    command: str
    output: str = ""
    error: str = ""
    files_created: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0


@dataclass
class PreconditionResult:
    """Result of precondition check."""
    passed: bool
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


class Skill(ABC):
    """Base class for all skills."""

    name: str = "base_skill"
    description: str = "Base skill"
    category: str = "general"

    @abstractmethod
    def check_preconditions(self, **kwargs) -> PreconditionResult:
        """Check if preconditions are met before execution."""
        pass

    @abstractmethod
    def generate_command(self, **kwargs) -> str:
        """Generate the command to execute."""
        pass

    @abstractmethod
    def execute(self, **kwargs) -> SkillResult:
        """Execute the skill."""
        pass

    def get_help(self) -> str:
        """Get help text for this skill."""
        return f"{self.name}: {self.description}"


class GitCloneSkill(Skill):
    """Skill for cloning Git repositories."""

    name = "git_clone"
    description = "Clone a Git repository"
    category = "git"

    def check_preconditions(self, url: str, target_dir: str = None, **kwargs) -> PreconditionResult:
        """
        Check preconditions:
        1. Git is installed
        2. URL is valid and accessible
        3. Target directory doesn't exist or is empty
        """
        # Check git is installed
        try:
            result = subprocess.run(
                ["git", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                return PreconditionResult(
                    passed=False,
                    message="Git is not installed or not in PATH"
                )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return PreconditionResult(
                passed=False,
                message="Git is not installed or not in PATH"
            )

        # Validate URL format
        git_url_patterns = [
            r'^https?://[^\s]+\.git$',
            r'^https?://github\.com/[^/]+/[^/]+/?$',
            r'^https?://gitlab\.com/[^/]+/[^/]+/?$',
            r'^git@[^\s]+:[^\s]+\.git$',
        ]
        if not any(re.match(p, url) for p in git_url_patterns):
            # Try to validate by checking if URL is accessible
            try:
                # Add .git if missing for GitHub URLs
                check_url = url
                if 'github.com' in url and not url.endswith('.git'):
                    check_url = url.rstrip('/') + '.git'

                req = urllib.request.Request(check_url, method='HEAD')
                req.add_header('User-Agent', 'Mozilla/5.0')
                with urllib.request.urlopen(req, timeout=10) as response:
                    if response.status >= 400:
                        return PreconditionResult(
                            passed=False,
                            message=f"Repository URL returned status {response.status}",
                            details={"url": url, "status": response.status}
                        )
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return PreconditionResult(
                        passed=False,
                        message=f"Repository not found: {url}",
                        details={"url": url, "error": str(e)}
                    )
                # Other HTTP errors might be OK (e.g., 401 for private repos)
            except Exception as e:
                # URL validation failed, but might still work
                pass

        # Check target directory
        if target_dir:
            if os.path.exists(target_dir):
                if os.listdir(target_dir):
                    return PreconditionResult(
                        passed=False,
                        message=f"Target directory exists and is not empty: {target_dir}",
                        details={"target_dir": target_dir}
                    )

        return PreconditionResult(
            passed=True,
            message="All preconditions met",
            details={"url": url, "target_dir": target_dir}
        )

    def generate_command(self, url: str, target_dir: str = None, branch: str = None, depth: int = None, **kwargs) -> str:
        """Generate git clone command."""
        cmd_parts = ["git", "clone"]

        if branch:
            cmd_parts.extend(["--branch", branch])

        if depth:
            cmd_parts.extend(["--depth", str(depth)])

        cmd_parts.append(url)

        if target_dir:
            cmd_parts.append(target_dir)

        return " ".join(cmd_parts)

    def execute(self, url: str, target_dir: str = None, branch: str = None, depth: int = None, **kwargs) -> SkillResult:
        """Execute git clone."""
        import time
        start_time = time.time()

        # Check preconditions
        precond = self.check_preconditions(url=url, target_dir=target_dir)
        if not precond.passed:
            return SkillResult(
                status=SkillStatus.PRECONDITION_FAILED,
                command="",
                error=precond.message
            )

        # Generate and execute command
        command = self.generate_command(url=url, target_dir=target_dir, branch=branch, depth=depth)

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )

            duration = time.time() - start_time

            if result.returncode == 0:
                # Determine created directory
                if target_dir:
                    created_dir = target_dir
                else:
                    # Extract repo name from URL
                    repo_name = url.rstrip('/').split('/')[-1]
                    if repo_name.endswith('.git'):
                        repo_name = repo_name[:-4]
                    created_dir = repo_name

                return SkillResult(
                    status=SkillStatus.EXECUTED,
                    command=command,
                    output=result.stdout + result.stderr,
                    files_created=[created_dir],
                    duration_seconds=duration
                )
            else:
                return SkillResult(
                    status=SkillStatus.FAILED,
                    command=command,
                    output=result.stdout,
                    error=result.stderr,
                    duration_seconds=duration
                )

        except subprocess.TimeoutExpired:
            return SkillResult(
                status=SkillStatus.FAILED,
                command=command,
                error="Command timed out after 300 seconds"
            )
        except Exception as e:
            return SkillResult(
                status=SkillStatus.FAILED,
                command=command,
                error=str(e)
            )


class FileCreateSkill(Skill):
    """Skill for creating files with content."""

    name = "file_create"
    description = "Create a new file with content"
    category = "file"

    def check_preconditions(self, filepath: str, content: str = "", overwrite: bool = False, **kwargs) -> PreconditionResult:
        """
        Check preconditions:
        1. Parent directory exists or can be created
        2. File doesn't exist (unless overwrite=True)
        3. Path is safe (no path traversal)
        """
        # Check for path traversal
        abs_path = os.path.abspath(filepath)
        if '..' in filepath:
            return PreconditionResult(
                passed=False,
                message="Path traversal detected in filepath",
                details={"filepath": filepath}
            )

        # Check parent directory
        parent_dir = os.path.dirname(abs_path)
        if parent_dir and not os.path.exists(parent_dir):
            # Will need to create parent directory
            pass

        # Check if file exists
        if os.path.exists(abs_path) and not overwrite:
            return PreconditionResult(
                passed=False,
                message=f"File already exists: {filepath}. Use overwrite=True to replace.",
                details={"filepath": filepath, "exists": True}
            )

        return PreconditionResult(
            passed=True,
            message="All preconditions met",
            details={"filepath": filepath, "overwrite": overwrite}
        )

    def generate_command(self, filepath: str, content: str = "", **kwargs) -> str:
        """Generate file creation command."""
        # For simple content, use echo
        if '\n' not in content and len(content) < 100:
            escaped_content = content.replace("'", "'\\''")
            return f"echo '{escaped_content}' > {filepath}"
        else:
            # For complex content, use heredoc
            return f"cat > {filepath} << 'EOF'\n{content}\nEOF"

    def execute(self, filepath: str, content: str = "", overwrite: bool = False, **kwargs) -> SkillResult:
        """Execute file creation."""
        import time
        start_time = time.time()

        # Check preconditions
        precond = self.check_preconditions(filepath=filepath, content=content, overwrite=overwrite)
        if not precond.passed:
            return SkillResult(
                status=SkillStatus.PRECONDITION_FAILED,
                command="",
                error=precond.message
            )

        abs_path = os.path.abspath(filepath)

        try:
            # Create parent directory if needed
            parent_dir = os.path.dirname(abs_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir)

            # Write file
            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(content)

            duration = time.time() - start_time
            command = self.generate_command(filepath=filepath, content=content)

            return SkillResult(
                status=SkillStatus.EXECUTED,
                command=command,
                output=f"Created file: {filepath} ({len(content)} bytes)",
                files_created=[filepath],
                duration_seconds=duration
            )

        except Exception as e:
            return SkillResult(
                status=SkillStatus.FAILED,
                command=self.generate_command(filepath=filepath, content=content),
                error=str(e)
            )


class DockerBuildSkill(Skill):
    """Skill for building Docker images."""

    name = "docker_build"
    description = "Build a Docker image from Dockerfile"
    category = "docker"

    def check_preconditions(self, dockerfile_path: str = "Dockerfile", tag: str = None, context: str = ".", **kwargs) -> PreconditionResult:
        """
        Check preconditions:
        1. Docker is installed and running
        2. Dockerfile exists
        3. Build context exists
        """
        # Check Docker is installed
        try:
            result = subprocess.run(
                ["docker", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                return PreconditionResult(
                    passed=False,
                    message="Docker is not installed or not in PATH"
                )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return PreconditionResult(
                passed=False,
                message="Docker is not installed or not in PATH"
            )

        # Check Docker daemon is running
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                return PreconditionResult(
                    passed=False,
                    message="Docker daemon is not running",
                    details={"error": result.stderr}
                )
        except subprocess.TimeoutExpired:
            return PreconditionResult(
                passed=False,
                message="Docker daemon is not responding"
            )

        # Check Dockerfile exists
        dockerfile_full_path = os.path.join(context, dockerfile_path) if context != "." else dockerfile_path
        if not os.path.exists(dockerfile_full_path):
            return PreconditionResult(
                passed=False,
                message=f"Dockerfile not found: {dockerfile_full_path}",
                details={"dockerfile_path": dockerfile_full_path}
            )

        # Check context exists
        if not os.path.isdir(context):
            return PreconditionResult(
                passed=False,
                message=f"Build context directory not found: {context}",
                details={"context": context}
            )

        return PreconditionResult(
            passed=True,
            message="All preconditions met",
            details={"dockerfile_path": dockerfile_path, "tag": tag, "context": context}
        )

    def generate_command(self, dockerfile_path: str = "Dockerfile", tag: str = None, context: str = ".", **kwargs) -> str:
        """Generate docker build command."""
        cmd_parts = ["docker", "build"]

        if dockerfile_path != "Dockerfile":
            cmd_parts.extend(["-f", dockerfile_path])

        if tag:
            cmd_parts.extend(["-t", tag])

        cmd_parts.append(context)

        return " ".join(cmd_parts)

    def execute(self, dockerfile_path: str = "Dockerfile", tag: str = None, context: str = ".", **kwargs) -> SkillResult:
        """Execute docker build."""
        import time
        start_time = time.time()

        # Check preconditions
        precond = self.check_preconditions(dockerfile_path=dockerfile_path, tag=tag, context=context)
        if not precond.passed:
            return SkillResult(
                status=SkillStatus.PRECONDITION_FAILED,
                command="",
                error=precond.message
            )

        command = self.generate_command(dockerfile_path=dockerfile_path, tag=tag, context=context)

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )

            duration = time.time() - start_time

            if result.returncode == 0:
                return SkillResult(
                    status=SkillStatus.EXECUTED,
                    command=command,
                    output=result.stdout + result.stderr,
                    duration_seconds=duration
                )
            else:
                return SkillResult(
                    status=SkillStatus.FAILED,
                    command=command,
                    output=result.stdout,
                    error=result.stderr,
                    duration_seconds=duration
                )

        except subprocess.TimeoutExpired:
            return SkillResult(
                status=SkillStatus.FAILED,
                command=command,
                error="Docker build timed out after 600 seconds"
            )
        except Exception as e:
            return SkillResult(
                status=SkillStatus.FAILED,
                command=command,
                error=str(e)
            )


class PythonScriptSkill(Skill):
    """Skill for creating Python scripts with common scaffolds."""

    name = "python_script"
    description = "Create a Python script with common scaffolds"
    category = "python"

    TEMPLATES = {
        "basic": '''#!/usr/bin/env python3
"""
{description}
"""

def main():
    {code}

if __name__ == "__main__":
    main()
''',
        "cli": '''#!/usr/bin/env python3
"""
{description}
"""
import argparse

def parse_args():
    parser = argparse.ArgumentParser(description="{description}")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    return parser.parse_args()

def main():
    args = parse_args()
    {code}

if __name__ == "__main__":
    main()
''',
        "class": '''#!/usr/bin/env python3
"""
{description}
"""

class {class_name}:
    """
    {class_description}
    """

    def __init__(self):
        pass

    def run(self):
        {code}

def main():
    obj = {class_name}()
    obj.run()

if __name__ == "__main__":
    main()
''',
        "test": '''#!/usr/bin/env python3
"""
Tests for {module_name}
"""
import unittest

class Test{class_name}(unittest.TestCase):
    """Test cases for {class_name}."""

    def setUp(self):
        """Set up test fixtures."""
        pass

    def tearDown(self):
        """Tear down test fixtures."""
        pass

    def test_basic(self):
        """Test basic functionality."""
        {code}

if __name__ == "__main__":
    unittest.main()
'''
    }

    def check_preconditions(self, filepath: str, template: str = "basic", **kwargs) -> PreconditionResult:
        """Check preconditions for Python script creation."""
        # Check template exists
        if template not in self.TEMPLATES:
            return PreconditionResult(
                passed=False,
                message=f"Unknown template: {template}. Available: {list(self.TEMPLATES.keys())}",
                details={"template": template}
            )

        # Check filepath
        if not filepath.endswith('.py'):
            return PreconditionResult(
                passed=False,
                message="Python script must have .py extension",
                details={"filepath": filepath}
            )

        # Check if file exists
        if os.path.exists(filepath):
            return PreconditionResult(
                passed=False,
                message=f"File already exists: {filepath}",
                details={"filepath": filepath}
            )

        return PreconditionResult(
            passed=True,
            message="All preconditions met",
            details={"filepath": filepath, "template": template}
        )

    def generate_command(self, filepath: str, **kwargs) -> str:
        """Generate command representation."""
        return f"# Create Python script: {filepath}"

    def execute(self, filepath: str, template: str = "basic", description: str = "Python script",
                code: str = "pass", class_name: str = "MyClass", class_description: str = "",
                module_name: str = "module", **kwargs) -> SkillResult:
        """Execute Python script creation."""
        import time
        start_time = time.time()

        # Check preconditions
        precond = self.check_preconditions(filepath=filepath, template=template)
        if not precond.passed:
            return SkillResult(
                status=SkillStatus.PRECONDITION_FAILED,
                command="",
                error=precond.message
            )

        try:
            # Get template and fill in values
            template_str = self.TEMPLATES[template]
            content = template_str.format(
                description=description,
                code=code,
                class_name=class_name,
                class_description=class_description or description,
                module_name=module_name
            )

            # Create parent directory if needed
            parent_dir = os.path.dirname(filepath)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir)

            # Write file
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)

            # Make executable
            os.chmod(filepath, 0o755)

            duration = time.time() - start_time

            return SkillResult(
                status=SkillStatus.EXECUTED,
                command=self.generate_command(filepath=filepath),
                output=f"Created Python script: {filepath} (template: {template})",
                files_created=[filepath],
                duration_seconds=duration
            )

        except Exception as e:
            return SkillResult(
                status=SkillStatus.FAILED,
                command=self.generate_command(filepath=filepath),
                error=str(e)
            )


class SkillRegistry:
    """Registry for all available skills."""

    def __init__(self):
        self._skills: Dict[str, Skill] = {}
        self._register_default_skills()

    def _register_default_skills(self):
        """Register default skills."""
        self.register(GitCloneSkill())
        self.register(FileCreateSkill())
        self.register(DockerBuildSkill())
        self.register(PythonScriptSkill())

    def register(self, skill: Skill):
        """Register a skill."""
        self._skills[skill.name] = skill

    def get(self, name: str) -> Optional[Skill]:
        """Get a skill by name."""
        return self._skills.get(name)

    def list_skills(self) -> List[str]:
        """List all registered skill names."""
        return list(self._skills.keys())

    def list_by_category(self, category: str) -> List[Skill]:
        """List skills by category."""
        return [s for s in self._skills.values() if s.category == category]

    def get_help(self) -> str:
        """Get help text for all skills."""
        lines = ["Available Skills:", ""]
        for name, skill in sorted(self._skills.items()):
            lines.append(f"  {name}: {skill.description} [{skill.category}]")
        return "\n".join(lines)

    def match_skill(self, task_description: str) -> Optional[Tuple[Skill, Dict[str, Any]]]:
        """
        Try to match a task description to a skill.

        Returns:
            Tuple of (skill, kwargs) if matched, None otherwise
        """
        task_lower = task_description.lower()

        # Git clone patterns
        git_patterns = [
            r'clone\s+(?:the\s+)?(?:repo(?:sitory)?\s+)?(?:from\s+)?(https?://[^\s]+)',
            r'git\s+clone\s+(https?://[^\s]+)',
            r'clone\s+(https?://github\.com/[^\s]+)',
        ]
        for pattern in git_patterns:
            match = re.search(pattern, task_lower)
            if match:
                url = match.group(1)
                return (self._skills.get('git_clone'), {'url': url})

        # File creation patterns
        file_patterns = [
            r'create\s+(?:a\s+)?(?:file\s+)?(?:named\s+)?["\']?(\w+\.\w+)["\']?',
            r'write\s+(?:a\s+)?(?:file\s+)?(?:named\s+)?["\']?(\w+\.\w+)["\']?',
            r'make\s+(?:a\s+)?(?:file\s+)?(?:named\s+)?["\']?(\w+\.\w+)["\']?',
        ]
        for pattern in file_patterns:
            match = re.search(pattern, task_lower)
            if match:
                filepath = match.group(1)
                return (self._skills.get('file_create'), {'filepath': filepath, 'content': ''})

        # Python script patterns
        python_patterns = [
            r'create\s+(?:a\s+)?python\s+(?:script|file)\s+(?:named\s+)?["\']?(\w+\.py)["\']?',
            r'write\s+(?:a\s+)?python\s+(?:script|file)\s+(?:named\s+)?["\']?(\w+\.py)["\']?',
        ]
        for pattern in python_patterns:
            match = re.search(pattern, task_lower)
            if match:
                filepath = match.group(1)
                return (self._skills.get('python_script'), {'filepath': filepath})

        # Docker build patterns
        docker_patterns = [
            r'(?:docker\s+)?build\s+(?:the\s+)?(?:docker\s+)?image',
            r'build\s+(?:a\s+)?dockerfile',
        ]
        for pattern in docker_patterns:
            if re.search(pattern, task_lower):
                return (self._skills.get('docker_build'), {})

        return None


# Global skill registry
_skill_registry: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    """Get the global skill registry."""
    global _skill_registry
    if _skill_registry is None:
        _skill_registry = SkillRegistry()
    return _skill_registry
