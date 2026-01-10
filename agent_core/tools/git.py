"""
Git Handler for version control operations.
Ensures every change is reversible through Git.
"""
import os
import subprocess
from typing import Optional, List


class GitError(Exception):
    """Base exception for Git errors."""
    pass


class GitHandler:
    """
    Git handler for safe version control operations.
    Uses subprocess to call real git commands.
    """

    def __init__(self, root: str = "."):
        """
        Initialize the GitHandler.

        Args:
            root: Root directory for git operations
        """
        self.root = os.path.abspath(root)

    def _run_git(self, *args, check: bool = True) -> subprocess.CompletedProcess:
        """
        Run a git command.

        Args:
            *args: Git command arguments
            check: If True, raise exception on non-zero exit

        Returns:
            CompletedProcess instance
        """
        cmd = ["git"] + list(args)
        try:
            result = subprocess.run(
                cmd,
                cwd=self.root,
                capture_output=True,
                text=True,
                check=check
            )
            return result
        except subprocess.CalledProcessError as e:
            raise GitError(f"Git command failed: {' '.join(cmd)}\n{e.stderr}")

    def init_repo(self) -> None:
        """
        Initialize a new git repository.
        Also configures user name and email for commits.
        """
        self._run_git("init")
        # Configure user for commits (required for commit to work)
        self._run_git("config", "user.email", "agent@local")
        self._run_git("config", "user.name", "Debug Agent")

    def is_repo(self) -> bool:
        """Check if the root directory is a git repository."""
        git_dir = os.path.join(self.root, ".git")
        return os.path.isdir(git_dir)

    def add_all(self) -> None:
        """Stage all changes."""
        self._run_git("add", "-A")

    def add_file(self, path: str) -> None:
        """Stage a specific file."""
        self._run_git("add", path)

    def commit(self, message: str) -> str:
        """
        Create a commit with staged changes.

        Args:
            message: Commit message

        Returns:
            Commit hash
        """
        self._run_git("commit", "-m", message)
        result = self._run_git("rev-parse", "HEAD")
        return result.stdout.strip()

    def commit_all(self, message: str) -> str:
        """
        Stage all changes and commit.

        Args:
            message: Commit message

        Returns:
            Commit hash
        """
        self.add_all()
        return self.commit(message)

    def reset_hard(self, ref: str = "HEAD") -> None:
        """
        Hard reset to a reference (discards all changes).

        Args:
            ref: Git reference to reset to (default: HEAD)
        """
        self._run_git("reset", "--hard", ref)

    def reset_soft(self, ref: str = "HEAD~1") -> None:
        """
        Soft reset to a reference (keeps changes staged).

        Args:
            ref: Git reference to reset to
        """
        self._run_git("reset", "--soft", ref)

    def get_diff(self, staged: bool = False) -> str:
        """
        Get the current diff.

        Args:
            staged: If True, show staged changes. If False, show unstaged.

        Returns:
            Diff output as string
        """
        if staged:
            result = self._run_git("diff", "--cached")
        else:
            result = self._run_git("diff")
        return result.stdout

    def get_status(self) -> str:
        """Get git status output."""
        result = self._run_git("status", "--porcelain")
        return result.stdout

    def get_log(self, count: int = 10) -> str:
        """
        Get recent commit log.

        Args:
            count: Number of commits to show

        Returns:
            Log output
        """
        result = self._run_git("log", f"-{count}", "--oneline")
        return result.stdout

    def get_current_commit(self) -> str:
        """Get the current commit hash."""
        result = self._run_git("rev-parse", "HEAD")
        return result.stdout.strip()

    def create_branch(self, name: str) -> None:
        """Create a new branch."""
        self._run_git("branch", name)

    def checkout(self, ref: str) -> None:
        """Checkout a branch or commit."""
        self._run_git("checkout", ref)

    def checkout_file(self, path: str, ref: str = "HEAD") -> None:
        """
        Restore a file from a specific reference.

        Args:
            path: File path to restore
            ref: Git reference to restore from
        """
        self._run_git("checkout", ref, "--", path)

    def stash(self) -> None:
        """Stash current changes."""
        self._run_git("stash")

    def stash_pop(self) -> None:
        """Pop the most recent stash."""
        self._run_git("stash", "pop")

    def has_changes(self) -> bool:
        """Check if there are uncommitted changes."""
        status = self.get_status()
        return len(status.strip()) > 0

    def get_changed_files(self) -> List[str]:
        """Get list of changed files."""
        status = self.get_status()
        files = []
        for line in status.strip().split('\n'):
            if line:
                # Status format: "XY filename" where XY is the status code
                parts = line.split(maxsplit=1)
                if len(parts) == 2:
                    files.append(parts[1])
        return files

    def create_checkpoint(self, name: str = "checkpoint") -> str:
        """
        Create a checkpoint commit before making changes.

        Args:
            name: Checkpoint name/description

        Returns:
            Commit hash of the checkpoint
        """
        if self.has_changes():
            return self.commit_all(f"[CHECKPOINT] {name}")
        return self.get_current_commit()

    def rollback_to_checkpoint(self, commit_hash: str) -> None:
        """
        Rollback to a specific checkpoint.

        Args:
            commit_hash: The commit hash to rollback to
        """
        self.reset_hard(commit_hash)
